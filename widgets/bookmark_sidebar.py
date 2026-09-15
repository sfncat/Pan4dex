"""
Pan4dex 万格 — 收藏夹侧边栏（分组树，清单 8.4）

这里只画树、把用户动作翻给 `config/bookmarks.py`；结构规则（成环、层数、上限、老格式
迁移）全在那一层。树用 `QTreeWidget`（收藏是几十到几百项，不是几万项，不值得上模型层），
每一项在 `UserRole` 里存节点的 **id** —— 行号在中间插一个分组之后就整体错位，id 不会
（旧版正是拿 `list_widget.currentRow()` 去索引一个平铺 list）。

两种拖拽：本树内部重排/挪组（规则回 store 问），以及从文件列表**拖一个目录进来**
→ 收藏到光标下的分组（清单 8.2 写的是这个能力，旧版 `InternalMove` 根本不收外部拖放）。
"""
import logging
import os

from PyQt6.QtWidgets import (
    QAbstractItemView, QDockWidget, QFileDialog, QHBoxLayout, QInputDialog,
    QLineEdit, QMenu, QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal

from config.bookmarks import BookmarkStore, BookmarkError, ROOT_ID

logger = logging.getLogger("pan4dex.bookmark_sidebar")


def external_dirs(mime) -> list:
    """拖放的 mime → 可以收藏的本地目录列表

    只收**存在的目录**：拖进来的是文件时不知道要收藏它的父目录还是什么，与其猜
    不如不收。注意这与 store “不校验 path” 不矛盾 —— 那说的是**存下来之后**目录
    可能才消失，而这里要定的是“这个手势到底算不算收藏一个位置”。
    """
    if mime is None or not mime.hasUrls():
        return []
    out = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        if not path:
            continue
        # `toLocalFile()` 在 Windows 上给的是正斜杠（实测 `C:/x/y`），与别处从
        # `QDir.path()` / 窗格拿到的形状不一致，收藏进去会同一目录两种写法
        path = os.path.normpath(path)
        if os.path.isdir(path):
            out.append(path)
    return out


class _BookmarkTree(QTreeWidget):
    """只加两件事：拖放的合法性交给 store 判（不在 UI 里重算一套规则）+ Del 删收藏"""

    def __init__(self, sidebar):
        super().__init__()
        self._sidebar = sidebar
        self._dragging_internally = False

    def startDrag(self, supportedActions):
        # `canDropMimeData` 无法从 mime 里认出“这是本树的内部移动”，用这个标志兜住：
        # 否则从文件列表拖文件（Shift 拖＝MoveAction）会被当成收藏重排而通过校验
        self._dragging_internally = True
        try:
            super().startDrag(supportedActions)
        finally:
            self._dragging_internally = False

    def canDropMimeData(self, data, action, position, index, parent):
        if self._dragging_internally:
            if action != Qt.DropAction.MoveAction:
                return False
            ids = [it.data(0, Qt.ItemDataRole.UserRole) for it in self.selectedItems()]
            ids = [i for i in ids if i is not None]
            if not ids:
                return False
            return self._sidebar.can_place_drag(
                ids, self._target_group(index, parent, position))
        return bool(external_dirs(data))

    def dropEvent(self, event):
        """外部拖入 = 收藏；内部重排交给 Qt，落地后立刻把树的顺序写回存储

        不只靠 `rowsMoved` 信号：同树内部移动走的是 QTreeWidget 自己的 `xferItems`，
        它到底发哪些信号不该由我们赌（赌输了就是“拖完看似成功、重启弹回原样”，
        与旧版同一个 bug）。`_sync_from_tree` 对“顺序没变”会直接返回，两处都接不会
        多写一次盘。
        """
        if not self._dragging_internally:
            dirs = external_dirs(event.mimeData())
            if dirs:
                self._sidebar.add_paths_as_bookmarks(
                    dirs, self._group_under(event.position().toPoint()))
                event.acceptProposedAction()
            return                      # 拖进来的不是目录：不接，也别往下走内部移动
        super().dropEvent(event)
        self._sidebar._sync_from_tree()

    def _group_under(self, pos):
        """外部拖放的落点分组：光标在分组上=它，在链接上=它的父组，空白=根"""
        item = self.itemAt(pos)
        if item is None:
            return ROOT_ID
        node = self._sidebar.store.find(item.data(0, Qt.ItemDataRole.UserRole))
        if node is None:
            return ROOT_ID
        if node["type"] == "group":
            return node["id"]
        grp = self._sidebar.store.parent_of(node["id"])
        return grp["id"] if grp else ROOT_ID

    def _target_group(self, index, parent, position):
        """放置位置 → 目标分组的 id

        - `OnItem` 落在分组上：放进这个分组
        - `OnItem` 落在**链接**上：Qt 是把拖来的项插在它旁边（不是插进它里
          面），所以目标是它所在的分组；当成“放进一条收藏”拒掉的话，就再也
          没法把一项拖到一条收藏旁边
        - `AboveItem` / `BelowItem`：与参照项同级 → 参照项的父组
        - `OnViewport`（空白处）：根

        `index` / `parent` 都是 **QModelIndex**（parent 不是项），得过 `itemFromIndex`
        才能读 `UserRole`；直接当 `QTreeWidgetItem` 用会在 `data(0, role)` 上报
        TypeError（`QModelIndex.data` 只接一个参数）。
        """
        store = self._sidebar.store
        item = self.itemFromIndex(index) if index.isValid() else None
        if item is None and parent.isValid():
            item = self.itemFromIndex(parent)
        if item is None:
            return ROOT_ID
        node = store.find(item.data(0, Qt.ItemDataRole.UserRole))
        if node is None:
            return ROOT_ID
        if position == QAbstractItemView.DropIndicatorPosition.OnItem \
                and node["type"] == "group":
            return node["id"]
        grp = store.parent_of(node["id"])
        return grp["id"] if grp else ROOT_ID

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self._sidebar.remove_selected()     # 删收藏，不删磁盘上的目录（确认框里写明）
            event.accept()
            return
        super().keyPressEvent(event)


class BookmarkSidebar(QDockWidget):
    """收藏夹侧边栏：可嵌套分组的树（拖拽排序/挪组，顺序与展开状态都落盘）"""

    bookmark_clicked = pyqtSignal(str)          # 点到一条收藏（链接）时发目标目录

    def __init__(self, parent=None, store=None, current_dir_provider=None):
        super().__init__("收藏夹", parent)

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(150)
        self.setMaximumWidth(300)

        # 存储由主窗口注入（与 file_associations / saved_searches 同做法）；
        # `current_dir_provider` 取活动窗格的当前目录，作为「添加收藏」的默认路径
        self.store = store if store is not None else BookmarkStore()
        self.current_dir_provider = current_dir_provider
        self._rebuilding = False
        self._persist_expansion = True

        self.init_ui()
        self.refresh_tree()

    # ---------------------------------------------------------------- UI

    def init_ui(self):
        self.main_widget = QWidget()
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        self.toolbar = QHBoxLayout()
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(24, 24)
        self.add_btn.setToolTip("添加收藏…（选一个目录收藏，默认是活动窗格的当前目录）")
        self.add_btn.clicked.connect(self.add_bookmark)
        self.toolbar.addWidget(self.add_btn)

        self.group_btn = QPushButton("分组")
        self.group_btn.setFixedHeight(24)
        self.group_btn.setToolTip("新建一个分组（可以嵌套，拖拽即可挪动）")
        self.group_btn.clicked.connect(self.new_group)
        self.toolbar.addWidget(self.group_btn)

        self.remove_btn = QPushButton("-")
        self.remove_btn.setFixedSize(24, 24)
        self.remove_btn.setToolTip("删除选中的收藏/分组（只删收藏夹里的这一项，不动磁盘）")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.toolbar.addWidget(self.remove_btn)

        self.toolbar.addStretch()
        self.layout.addLayout(self.toolbar)

        self.tree = _BookmarkTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setExpandsOnDoubleClick(False)      # 双击：链接=打开，分组=展开/折叠
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        # 不是 InternalMove：那个模式不接外部拖放，而清单 8.2 要的正是
        # “从文件列表拖一个目录进来收藏”
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.tree.setDragDropOverwriteMode(False)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)   # 内部重排只认 Move
        # 能接哪些拖放在 `canDropMimeData` 里判（要看 mime 内容），Qt 6 没提供
        # setDropActions，而它默认就是 Move|Copy
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemDoubleClicked.connect(self.on_item_activated)
        self.tree.itemExpanded.connect(lambda it: self._on_expand_changed(it, True))
        self.tree.itemCollapsed.connect(lambda it: self._on_expand_changed(it, False))
        # 拖拽完成后把树的实际顺序写回存储；dropEvent 里也接了一道（两处对
        # “顺序没变”都是 no-op，不会多写一次盘）
        self.tree.model().rowsMoved.connect(self._sync_from_tree)
        self.layout.addWidget(self.tree)

        self.setWidget(self.main_widget)

    def refresh_tree(self, select_id=None):
        """按 store 重建树（唯一的“画”入口，改完都走这里）"""
        self._rebuilding = True
        try:
            self.tree.clear()
            for node in self.store.root["children"]:
                self.tree.addTopLevelItem(self._make_item(node))
            for item, node in self._walk():
                item.setExpanded(bool(node.get("expanded", True)))
            if select_id is not None:
                item = self._item_of(select_id)
                if item is not None:
                    self.tree.setCurrentItem(item)
                    self.tree.scrollToItem(item)
        finally:
            self._rebuilding = False

    def _make_item(self, node) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node["name"]])
        item.setData(0, Qt.ItemDataRole.UserRole, node["id"])
        item.setData(0, Qt.ItemDataRole.UserRole + 1, node["type"])
        if node["type"] == "link":
            item.setToolTip(0, node["path"])
        else:
            kids = self.store.link_count(node)
            item.setToolTip(0, f"分组 · {kids} 条收藏" if kids else "分组（空）")
        for child in node.get("children") or []:
            item.addChild(self._make_item(child))
        return item

    def _walk(self, parent=None):
        """(item, node) 成对产出（深度优先，与显示顺序一致）"""
        items = (range(parent.childCount()) if parent is not None
                 else range(self.tree.topLevelItemCount()))
        get = (lambda i: parent.child(i)) if parent is not None else self.tree.topLevelItem
        for i in items:
            item = get(i)
            node = self.store.find(item.data(0, Qt.ItemDataRole.UserRole))
            if node is None:
                continue
            yield item, node
            yield from self._walk(item)

    def _item_of(self, node_id):
        for item, node in self._walk():
            if node["id"] == node_id:
                return item
        return None

    # ------------------------------------------------------------ 拖拽同步

    def can_place_drag(self, node_ids, parent_id) -> bool:
        """Qt 问“这里能不能放”：一条不许就不许（宁可不给放，也别放出一棵还原不了的树）"""
        for node_id in node_ids:
            if self.store.can_place(node_id, parent_id):
                return False
        return True

    def _sync_from_tree(self):
        """拖拽落地后：按树里的实际顺序重写模型并落盘

        不这么做的话，拖拽只改了 `QTreeWidget` 自己的行序，下次重建树就弹回原样
        （旧版就是这样：`InternalMove` 拖完从不写回 bookmarks，重启顺序全丢）。
        """
        if self._rebuilding:
            return
        order = self._read_order()                  # 父 id -> [子 id]（含根）
        by_id = {n["id"]: n for n in self._iter_nodes()}
        seen = [cid for ids in order.values() for cid in ids]
        if (len(seen) != len(by_id) - 1                      # 每项恰好挂一个父
                or any(cid not in by_id for cid in seen)
                or len(set(seen)) != len(seen)):
            # 树与模型对不上（不该发生）：以模型为准重画，不把残缺的顺序写进文件
            # —— 万一 Qt 把移动做成了复制（子项 id 会重复），也是走这条退回
            logger.warning("收藏夹拖拽同步时对不上账，按存储重建（树 %s 项 / 模型 %s 项）",
                           len(seen), len(by_id) - 1)
            self.refresh_tree()
            return
        if order == self._model_order():
            return                                  # 原地放下：什么都没变，不必写盘
        self._rebuilding = True
        try:
            for gid, kids in order.items():
                by_id[gid]["children"] = [by_id[cid] for cid in kids]
            for group in (n for n in by_id.values()
                          if n["type"] == "group" and n["id"] not in order):
                group["children"] = []              # 树里这个分组已经被拖空了
        finally:
            self._rebuilding = False
        self._persist_expansion = False            # 重排不许顺带改展开状态
        try:
            self.refresh_tree()
        finally:
            self._persist_expansion = True
        self._commit()

    def _read_order(self) -> dict:
        """树里的实际顺序 → `{父 id: [子 id]}`（顶级项挂在 `ROOT_ID` 名下）

        顶级项不挂在任何一个 `QTreeWidgetItem` 下，所以它也要有一笔记账（用
        `setdefault` 开父层），否则“两个顶级项互换”这种拖拽在账上缺一整层。
        预置 `{ROOT_ID: []}` 则是为了下面那个早退：树与模型都是空的时候，两边形
        状要能对得上，一次“什么都没改”的同步不该重画 + 写盘。根没有
        QTreeWidgetItem，用 None 当它。
        """
        order = {ROOT_ID: []}

        def walk(item, parent_id):
            count = (item.childCount() if item is not None
                     else self.tree.topLevelItemCount())
            for i in range(count):
                child = item.child(i) if item is not None else self.tree.topLevelItem(i)
                node_id = child.data(0, Qt.ItemDataRole.UserRole)
                if node_id is None:
                    return {}                      # 树里有来路不明的项，不抢写
                order.setdefault(parent_id, []).append(node_id)
                walk(child, node_id)

        walk(None, ROOT_ID)
        return order

    def _model_order(self) -> dict:
        """存储里的顺序 → 与 `_read_order` 同形状（为了“没变就一行也不写”）"""
        order = {ROOT_ID: [c["id"] for c in self.store.root["children"]]}
        for node in self._iter_nodes():
            if node["type"] == "group" and node["children"]:
                order[node["id"]] = [c["id"] for c in node["children"]]
        return order

    def _iter_nodes(self, node=None):
        node = self.store.root if node is None else node
        yield node
        for child in node.get("children") or []:
            yield from self._iter_nodes(child)

    # ------------------------------------------------------------ 展开状态

    def _on_expand_changed(self, item, expanded: bool):
        if self._rebuilding or not self._persist_expansion:
            return
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        self.store.set_expanded(node_id, expanded)
        # 只存盘，不重画：重画得从 `itemCollapsed` 里当场 `tree.clear()`，而 Qt 此
        # 刻正在遍历行做展开；在信号里拆自己的模型是未定义行为（实测会把刚拿到的
        # item 包装器删掉，调用方再用它就是 `wrapped C/C++ object ... has been deleted`）
        self._save_only()

    def expand_all(self):
        self._bulk_expand(lambda: self.tree.expandAll())

    def collapse_all(self):
        self._bulk_expand(lambda: self.tree.collapseAll())

    def _bulk_expand(self, do):
        self._persist_expansion = False
        try:
            do()
        finally:
            self._persist_expansion = True
        for item, node in self._walk():
            if node["type"] == "group":
                node["expanded"] = item.isExpanded()
        self._save_only()

    # ------------------------------------------------------------ 交互

    def _selected_id(self):
        item = self.tree.currentItem()
        return None if item is None else item.data(0, Qt.ItemDataRole.UserRole)

    def _target_group_id(self):
        """新增/导入落在哪：选中分组=它，选中链接=它的父组，什么都没选=根"""
        node_id = self._selected_id()
        if node_id is None:
            return ROOT_ID
        node = self.store.find(node_id)
        if node is None:
            return ROOT_ID
        if node["type"] == "group":
            return node_id
        parent = self.store.parent_of(node_id)
        return parent["id"] if parent else ROOT_ID

    def on_item_activated(self, item):
        if item is None:
            return
        node = self.store.find(item.data(0, Qt.ItemDataRole.UserRole))
        if node is None:
            return
        if node["type"] == "group":
            item.setExpanded(not item.isExpanded())
            return
        path = node["path"]
        # 旧版这里是 `if os.path.isdir(path)` 才发信号 —— 网络盘暂时断开时双击**静默
        # 无响应**，用户只当侧边栏坏了。打不开要说出来。
        if not os.path.isdir(path):
            QMessageBox.warning(self, "打不开这个位置",
                                f"目录当前不可达：\n{path}\n\n"
                                "（网络位置断开？可移动盘未插入？收藏本身没有被删）")
            return
        self.bookmark_clicked.emit(path)

    def open_selected(self):
        self.on_item_activated(self.tree.currentItem())

    def _default_dir(self) -> str:
        try:
            return str((self.current_dir_provider or (lambda: ""))() or "")
        except Exception as e:                      # provider 抓到的窗格可能已销毁
            logger.debug("取当前目录失败: %s", e)
            return ""

    def add_bookmark(self):
        """工具栏「+」：先选目录（默认活动窗格的当前目录），再起名字"""
        path = QFileDialog.getExistingDirectory(self, "选择要收藏的目录", self._default_dir())
        if path:
            self.add_bookmark_with_path(path)

    def add_bookmark_with_path(self, path):
        """窗格右键「添加到收藏夹」走这里（签名保持不变）"""
        name, ok = QInputDialog.getText(
            self, "添加到收藏夹", "名称:", QLineEdit.EchoMode.Normal,
            os.path.basename(os.path.normpath(path)) or path)
        if not ok:
            return
        try:
            node_id = self.store.add_link(name, path, self._target_group_id())
        except BookmarkError as e:
            QMessageBox.warning(self, "无法添加收藏", str(e))
            return
        self._commit(select_id=node_id)

    def add_paths_as_bookmarks(self, paths, parent_id=None) -> int:
        """把若干目录收进某个分组（外部拖入走这里；右键那条要问名字，不走这里）

        同一个路径不收两次（拖两回同一个目录不该出现两条）；被拒的原因（条数/层数
        上限）只报一次，而不是一串弹窗。返实际新增几条。
        """
        parent_id = ROOT_ID if parent_id is None else parent_id
        have = {os.path.normcase(lk["path"]) for lk in self.store.links()}
        added = 0
        first_error = ""
        last_id = None
        for path in paths:
            norm = os.path.normpath(str(path))
            if os.path.normcase(norm) in have:
                continue
            try:
                last_id = self.store.add_link(
                    os.path.basename(norm) or norm, norm, parent_id)
            except BookmarkError as e:
                first_error = first_error or str(e)
                break                       # 撞的是上限，再试下面几条也白试
            have.add(os.path.normcase(norm))
            added += 1
        if added:
            self._commit(select_id=last_id)
        if first_error:
            QMessageBox.warning(self, "无法添加收藏", first_error)
        return added

    def new_group(self):
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称:",
                                        QLineEdit.EchoMode.Normal, "")
        if not ok:
            return
        try:
            node_id = self.store.add_group(name, self._target_group_id())
        except BookmarkError as e:
            QMessageBox.warning(self, "无法新建分组", str(e))
            return
        self._commit(select_id=node_id)

    def rename_selected(self):
        node_id = self._selected_id()
        if node_id is None:
            return
        node = self.store.find(node_id)
        name, ok = QInputDialog.getText(self, "重命名", "新名称:",
                                        QLineEdit.EchoMode.Normal, node["name"])
        if not ok:
            return
        try:
            self.store.rename(node_id, name)
        except BookmarkError as e:
            QMessageBox.warning(self, "无法重命名", str(e))
            return
        self._commit(select_id=node_id)

    def edit_bookmark(self):
        """只换目录（改名是另一个菜单项）

        名字还是老目录的尾巴时顺手跟着换（当初是自动填的），否则用户得再确认一次
        一个他根本没改过的名字。不叠第二个输入框：那会把一个简单动作变成两次提问。
        """
        node_id = self._selected_id()
        if node_id is None:
            return
        node = self.store.find(node_id)
        if node["type"] == "group":
            self.rename_selected()
            return
        old_path, old_name = node["path"], node["name"]
        path = QFileDialog.getExistingDirectory(self, "收藏哪个目录", old_path)
        if not path:
            return
        try:
            self.store.set_path(node_id, path)
            if old_name == os.path.basename(os.path.normpath(old_path)):
                self.store.rename(node_id, os.path.basename(os.path.normpath(path)) or path)
        except BookmarkError as e:
            QMessageBox.warning(self, "无法修改", str(e))
            return
        self._commit(select_id=node_id)

    def remove_selected(self):
        """删收藏项（**不删磁盘上的目录**）；分组连带子树"""
        node_id = self._selected_id()
        if node_id is None:
            return
        node = self.store.find(node_id)
        kids = self.store.link_count(node) if node["type"] == "group" else 0
        detail = f"分组「{node['name']}」里还有 {kids} 条收藏，会一起删除。" if kids \
            else f"删除「{node['name']}」。"
        if QMessageBox.question(
                self, "删除收藏",
                detail + "\n只删收藏夹里的这一项，磁盘上的目录不受影响。") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.remove(node_id)
        except BookmarkError as e:
            QMessageBox.warning(self, "无法删除", str(e))
            return
        self._commit()

    def move_to_group(self):
        """不开拖拽也能挪：列一个目标分组清单（自己与自己的子树不给选）"""
        node_id = self._selected_id()
        if node_id is None:
            return
        menu = QMenu(self)
        # `can_place` 回**空串**才是可以放（回的是不能放的理由）。反过来判等于只
        # 列出非法目标：成环的分组照样可点，真正能放的地方一个都不给
        if not self.store.can_place(node_id, ROOT_ID):
            menu.addAction("收藏夹根目录", lambda: self._do_move(node_id, ROOT_ID))
            menu.addSeparator()
        listed = 0
        for group in self.store.groups():
            if not self.store.can_place(node_id, group["id"]):
                menu.addAction(group["name"],
                               lambda _c=False, g=group: self._do_move(node_id, g["id"]))
                listed += 1
        if not listed:
            # 另加一项而不是改最后一条：分隔线也是一个 QAction，把文案写上去
            # 根本看不见（用户只会觉得菜单“没反应”）
            disabled = menu.addAction("（没有可以放入的分组）")
            disabled.setEnabled(False)
        menu.exec(self.tree.viewport().mapToGlobal(
            self.tree.visualItemRect(self.tree.currentItem()).center()))

    def _do_move(self, node_id, parent_id):
        try:
            self.store.move(node_id, parent_id)
        except BookmarkError as e:
            QMessageBox.warning(self, "无法移动", str(e))
            return
        self._commit(select_id=node_id)

    def export_bookmarks(self, filepath: str = None):
        """导出整棵树到文件（右键菜单在叫「导出收藏夹…」；不传路径时弹保存框）"""
        if filepath is None:
            filepath, _flt = QFileDialog.getSaveFileName(
                self, "导出收藏夹", "bookmarks.json", "JSON (*.json)")
            if not filepath:
                return
        ok, err = self.store.export_file(filepath)
        if not ok:
            QMessageBox.warning(self, "导出失败", err)

    def import_bookmarks(self, filepath: str = None):
        """并入一个收藏夹文件（同路径的跳过；失败不会清空现有的树）"""
        if filepath is None:
            filepath, _flt = QFileDialog.getOpenFileName(
                self, "导入收藏夹", "", "JSON (*.json)")
            if not filepath:
                return
        added, skipped, err = self.store.import_file(filepath, self._target_group_id())
        self.refresh_tree()
        if err:
            QMessageBox.warning(self, "导入失败", err)
        else:
            QMessageBox.information(
                self, "导入完成",
                f"新增 {added} 项，跳过重复 {skipped} 项")

    # ------------------------------------------------------------ 右键菜单

    def show_context_menu(self, position):
        menu = QMenu(self)
        item = self.tree.itemAt(position)
        node = self.store.find(item.data(0, Qt.ItemDataRole.UserRole)) if item else None

        if node is not None:
            if node["type"] == "link":
                menu.addAction("打开", self.open_selected)
                menu.addSeparator()
            menu.addAction("新建分组…", self.new_group)
            menu.addAction("添加收藏…", self.add_bookmark)
            menu.addSeparator()
            menu.addAction("重命名…", self.rename_selected)
            if node["type"] == "link":
                menu.addAction("更改收藏的目录…", self.edit_bookmark)
            menu.addAction("移动到分组…", self.move_to_group)
            menu.addSeparator()
            menu.addAction("删除", self.remove_selected)
            menu.addSeparator()
        else:
            menu.addAction("新建分组…", self.new_group)
            menu.addAction("添加收藏…", self.add_bookmark)
            menu.addSeparator()
        menu.addAction("展开全部", self.expand_all)
        menu.addAction("折叠全部", self.collapse_all)
        menu.addSeparator()
        menu.addAction("导入收藏夹…", self.import_bookmarks)
        menu.addAction("导出收藏夹…", self.export_bookmarks)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------ 兼容旧 API

    def get_bookmarks(self) -> list:
        """扁平的 [{name, path}]（树里的视觉顺序）"""
        return [{"name": lk["name"], "path": lk["path"]} for lk in self.store.links()]

    def set_store(self, store):
        """换一份存储（主窗口在测试里注入临时目录用），换完重画"""
        self.store = store
        self.refresh_tree()

    # ------------------------------------------------------------ 落盘

    def _save_only(self):
        """只落盘（树已经是对的，重画反而会打断当前动作）"""
        ok, err = self.store.save()
        if not ok:
            QMessageBox.warning(
                self, "无法保存收藏夹",
                err + "\n（改动只在本次会话里有效，重启会回到上次的样子）")

    def _commit(self, select_id=None):
        self._save_only()
        self.refresh_tree(select_id=select_id)
