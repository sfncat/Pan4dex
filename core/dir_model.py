# -*- coding: utf-8 -*-
"""
Pan4dex 万格 — DirStoreModel：以目录节点为单位的异步文件模型

设计目标：
- 一次枚举一个目录，杜绝 QFileSystemModel 在 SMB 上的逐项 stat 与 watcher 轮询
- 后台线程枚举（QThreadPool），主线程零阻塞；未加载完成 rowCount=0，canFetchMore/
  fetchMore 驱动，加载完 begin/endInsertRows 增量插入
- TTL 缓存 + 定向失效：应用内操作后只失效涉及的目录，F5 只重扫当前目录
- 结构：当前显示目录作为 invalid 根的唯一顶层行（rowCount(invalid)=1），
  因此 pane 拿到的索引一定能被 QSortFilterProxyModel.mapFromSource 映射

作用范围：仅服务文件列表视图（tree_view / 缩略图）。两个侧边目录树
（pane_tree_view / tree_sidebar）本就按需展开、非瓶颈，继续使用 QFileSystemModel。
"""
import os
import time
import logging
from datetime import datetime

from PyQt6.QtCore import (
    QAbstractItemModel, QModelIndex, Qt, QDir, QRunnable, QThreadPool,
    QObject, pyqtSignal, pyqtSlot,
)
from PyQt6.QtWidgets import QApplication, QStyle

logger = logging.getLogger("pan4dex.dir_model")

# 列定义（名称/大小/类型/修改日期 + 拍摄日期，前 4 列沿用资源管理器习惯顺序）
COL_NAME, COL_SIZE, COL_TYPE, COL_DATE, COL_SHOT = range(5)
HEADERS = ["名称", "大小", "类型", "修改日期", "拍摄日期"]


def _key(path):
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


class Entry:
    """文件/目录条目（某个目录节点的一个子项）。"""
    __slots__ = ("name", "path", "is_dir", "size", "mtime", "hidden", "is_link", "node")

    def __init__(self, name, path, is_dir, size, mtime, hidden, is_link):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size = size          # 文件字节数；目录为 -1（大小列不显示）
        self.mtime = mtime        # 修改时间（epoch 秒）；未知为 0
        self.hidden = hidden
        self.is_link = is_link    # 符号链接 / NTFS 重分析点
        self.node = None          # 所属 DirNode（加载后回填）


class DirNode:
    """一个目录节点：持有其枚举出的条目列表与加载状态。"""
    __slots__ = ("path", "key", "entries", "loaded", "loading", "gen")

    def __init__(self, path):
        self.path = os.path.normpath(path)
        self.key = _key(path)
        self.entries = None        # None=未加载；list=已加载
        self.loaded = False
        self.loading = False
        self.gen = 0               # 枚举请求代次：只采纳最新一次的结果


# ---------- 目录枚举（纯 Python，不触碰 Qt，供后台线程调用） ----------

def _entry_hidden(path, name):
    """跨平台隐藏判断：POSIX 以 . 前缀；Windows 读 FILE_ATTRIBUTE_HIDDEN"""
    if name.startswith('.'):
        return True
    if os.name == 'nt':
        try:
            import ctypes
            attr = ctypes.windll.kernel32.GetFileAttributesW(path)
            if attr != -1 and (attr & 0x2):  # FILE_ATTRIBUTE_HIDDEN
                return True
        except Exception:
            pass
    return False


def enumerate_dir(path, show_hidden=True):
    """枚举一个目录，返回 [Entry]。

    用 os.scandir：Windows 下 DirEntry 的 stat 结果来自枚举时已获取的
    WIN32_FIND_DATA 缓存，`entry.stat(follow_symlinks=False)` 不再触发额外
    网络往返——整个目录通常一次枚举往返即可拿到 name/attr/size/mtime。
    排序：目录优先、按名称（不区分大小写）升序，作为稳定基序；列排序由
    PaneSortProxyModel 负责。
    """
    entries = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    is_dir = e.is_dir(follow_symlinks=False)
                    is_link = e.is_symlink()
                except OSError:
                    is_dir = os.path.isdir(e.path)
                    is_link = os.path.islink(e.path)
                size = -1
                mtime = 0.0
                try:
                    st = e.stat(follow_symlinks=False)
                    mtime = getattr(st, "st_mtime", 0.0) or 0.0
                    if not is_dir:
                        size = getattr(st, "st_size", 0) or 0
                except OSError:
                    pass
                hidden = _entry_hidden(e.path, e.name)
                if not show_hidden and hidden:
                    continue
                entries.append(Entry(e.name, os.path.normpath(e.path),
                                     is_dir, size, mtime, hidden, is_link))
    except (PermissionError, OSError) as exc:
        logger.debug("枚举目录失败 %s: %s", path, exc)
        return []
    entries.sort(key=lambda x: (not x.is_dir, x.name.casefold()))
    return entries


# ---------- 后台枚举任务 ----------

class _LoadSignals(QObject):
    finished = pyqtSignal(object, object, int)   # DirNode, list[Entry], gen


class _LoadTask(QRunnable):
    def __init__(self, node, gen, show_hidden, signals):
        super().__init__()
        self.node = node
        self.gen = gen
        self.show_hidden = show_hidden
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            rows = enumerate_dir(self.node.path, self.show_hidden)
        except Exception:
            rows = []
        # queued 投递回主线程（signals 属于主线程对象）。模型可能已先一步销毁，
        # 而 signals 是模型的子对象、届时自己也成了悬空包装 → emit 报 RuntimeError；
        # 丢掉这份结果即可，不能让异常死在 worker 线程里
        try:
            self.signals.finished.emit(self.node, rows, self.gen)
        except RuntimeError:
            logger.debug("枚举结果丢弃：投递目标已随模型销毁")


class DirStoreModel(QAbstractItemModel):
    """当前显示目录 = invalid 根的唯一顶层行，其子行为该目录条目。

    pane 导航时调用 `set_directory(path)` 取得顶层索引，再经排序代理
    setRootIndex，视图即展示该目录的条目列表。
    """

    SHOT_DATE_COLUMN = COL_SHOT   # pane 的「拍摄日期」列常量
    directoryLoaded = pyqtSignal(str)
    loadingStarted = pyqtSignal(str)
    dirChanged = pyqtSignal(str)   # 本模型使某目录发生变更（行内改名等），供跨窗格同步

    # 类级缓存：{dirkey: (timestamp, show_hidden, [Entry])}，跨窗格共享同一目录枚举结果
    _CACHE = {}
    _CACHE_TTL = 2.0   # 秒；网络目录 TTL，本地目录主要靠定向失效

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = {}           # dirkey -> DirNode
        self._top_node = None      # 当前显示的目录节点（作为模型唯一顶层行）
        self._top_key = ""         # 顶层节点 key
        self._filter = (QDir.Filter.AllDirs | QDir.Filter.Files |
                        QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
        self._pool = QThreadPool.globalInstance()
        # `_loader` 以本模型为父：模型销毁时它一同销毁，在飞任务的 emit 会立刻失败
        # 并被 `_LoadTask.run` 吞掉，不会留下悬空的投递源。
        # 接收者必须是本模型（所以用绑定方法直连）：只有那样 Qt 才会在模型销毁时
        # 把已排队的投递一并剔除。改成“无 QObject 归属的函数”（如弱引用 closure）
        # 后，接收者变成 sender，而 `_loader` 会被在飞任务活得比模型久，投递就在模型
        # 销毁后照旧派发 —— 实测反而把崩溃点从槽内部前推到分发处（见
        # docs/unsolved-issues.md 问题 13）。
        self._loader = _LoadSignals(self)
        self._loader.finished.connect(self._on_entries_loaded)
        self._invalid = QModelIndex()

    # ---- pane 依赖的条目/目录查询接口（与 QFileSystemModel 同名，便于替换）----
    def rootPath(self):
        return self._top_node.path if self._top_node else ""

    def setFilter(self, filters):
        self._filter = filters

    def filter(self):
        return self._filter

    def set_directory(self, path):
        """pane 导航时调用：把该目录设为模型唯一顶层节点并触发异步加载。

        返回目录节点的顶层索引——它是 invalid 根的唯一行，因此
        QSortFilterProxyModel.mapFromSource 能正确映射（与 pane 的
        `_set_root_index` 用法兼容）。切换目录时 beginResetModel 让代理
        重建根；对同一目录重复调用不重置。
        """
        path = os.path.normpath(path) if path else ""
        if not path:
            return self._invalid
        node = self._ensure_node(path)
        key = node.key
        if self._top_key == key and self._top_node is node:
            if not node.loaded and not node.loading:
                self._start_load(node)
            return self.createIndex(0, 0, node)
        self.beginResetModel()
        self._top_node = node
        self._top_key = key
        self.endResetModel()
        if not node.loaded and not node.loading:
            self._start_load(node)
        return self.createIndex(0, 0, node)

    def isDir(self, idx):
        if isinstance(idx, str):
            return os.path.isdir(idx)
        p = idx.internalPointer() if idx.isValid() else None
        if isinstance(p, DirNode):
            return True
        if isinstance(p, Entry):
            return p.is_dir
        return False

    def filePath(self, idx):
        if not idx.isValid():
            return ""
        p = idx.internalPointer()
        return p.path if p else ""

    def fileName(self, idx):
        if not idx.isValid():
            return ""
        p = idx.internalPointer()
        return getattr(p, "name", "") or (os.path.basename(p.path) if isinstance(p, DirNode) else "")

    def entry_is_dir(self, path):
        """纯内存判定路径是否为目录（零 syscall、零网络往返）。

        返回 True/False；模型尚未加载该目录（未知）时返回 None，
        由调用方决定回退方式（网络路径回退一次 os.path.isdir）。
        """
        path = os.path.normpath(path) if path else ""
        if not path:
            return None
        # 当前显示目录本身
        if _key(path) == self._top_key and self._top_node is not None:
            return True
        # 曾作为目录枚举过的节点（含已切走的）——内存里已知道它是目录
        if _key(path) in self._nodes:
            return True
        node = self._nodes.get(_key(os.path.dirname(path)))
        if node and node.loaded and node.entries:
            for e in node.entries:
                if e.path == path:
                    return e.is_dir
        return None

    # ---- 缓存 / 定向失效 ----
    @classmethod
    def _cache_get(cls, key, show_hidden):
        item = cls._CACHE.get(key)
        if not item:
            return None
        ts, sh, entries = item
        if sh != show_hidden:
            return None
        return entries

    @classmethod
    def _cache_put(cls, key, show_hidden, entries):
        cls._CACHE[key] = (time.time(), show_hidden, entries)

    @classmethod
    def _cache_invalidate(cls, path):
        cls._CACHE.pop(_key(path), None)

    @staticmethod
    def _is_network(path):
        try:
            if os.name == 'nt':
                if path.startswith('\\\\'):
                    return True
                if len(path) >= 2 and path[1] == ':':
                    import ctypes
                    DRIVE_REMOTE = 4
                    return ctypes.windll.kernel32.GetDriveTypeW(path[:2] + '\\') == DRIVE_REMOTE
            return False
        except Exception:
            return False

    @classmethod
    def notify_dir_changed(cls, path):
        """外部（其它窗格/应用内操作）改了某目录：失效缓存。

        正显示该目录的窗格由 pane 侧调用 refresh 重载（pane 负责遍历受影响窗格）。
        """
        cls._cache_invalidate(path)

    def refresh(self, index=None):
        """重扫当前显示目录（F5 / 定向失效）：清条目后异步重载，
        保留顶层节点映射（不重置模型，为保留选中/滚动留余地）。"""
        node = self._top_node
        if node is not None:
            self._reload_top(node)

    def refresh_dir(self, path):
        """失效并重扫指定目录（应用内改动后调用，本地/网络统一）。

        - 正是当前显示目录：清条目 + 异步重载（保留顶层索引映射）
        - 已加载但未显示：直接丢弃节点，导航回来时重新枚举
          （DirStoreModel 无文件系统 watcher，不丢弃则陈旧节点会让模型
          跳过重扫，新建/删除的项迟迟不可见）
        """
        self._cache_invalidate(path)
        node = self._nodes.get(_key(path))
        if node is None:
            return
        if node is self._top_node:
            self._reload_top(node)
            return
        node.entries = None
        node.loaded = False
        self._nodes.pop(node.key, None)   # 丢弃后其 in-flight 结果会被自动作废

    def _reload_top(self, node):
        self._cache_invalidate(node.path)
        if node.loaded and node.entries:
            parent_idx = self.createIndex(0, 0, node)
            self.beginRemoveRows(parent_idx, 0, len(node.entries) - 1)
            node.entries = None
            node.loaded = False
            self.endRemoveRows()
        # 重扫请求总是另起一次枚举（gen+1）， in-flight 的旧结果会被作废
        self._start_load(node)

    # ---- 节点 materialize + 异步加载 ----
    def _ensure_node(self, path):
        key = _key(path)
        node = self._nodes.get(key)
        if node is not None:
            return node
        node = DirNode(path)
        self._nodes[key] = node
        show = self._show_hidden()
        cached = self._cache_get(key, show)
        if cached is not None and self._fresh_or_local(path):
            self._copy_entries(node, cached)
            node.loaded = True
        return node

    @staticmethod
    def _adopt(node, entries):
        """后台新枚举出的条目归本节点独占（无共享，直接回填 node 反查指针）。"""
        for e in entries:
            e.node = node
        node.entries = entries
        return entries

    @staticmethod
    def _copy_entries(node, entries):
        """把类级缓存里的条目复制为本节点独占对象。

        多个窗格可能同时显示同一目录并共用缓存列表；Entry 是可变的
        （行内改名会就地改 name/path，e.node 反查用于 parent()），共享
        会造成跨窗格互相污染，故缓存只作只读模板，使用时逐份复制。
        """
        bound = []
        for e in entries:
            ne = Entry(e.name, e.path, e.is_dir, e.size, e.mtime, e.hidden, e.is_link)
            ne.node = node
            bound.append(ne)
        node.entries = bound
        return bound

    @classmethod
    def _fresh_or_local(cls, path):
        if not cls._is_network(path):
            return True
        item = cls._CACHE.get(_key(path))
        return bool(item) and (time.time() - item[0] <= cls._CACHE_TTL)

    def _show_hidden(self):
        return bool(self._filter & QDir.Filter.Hidden)

    def _start_load(self, node):
        """发起一次后台枚举；旧请求的结果按代次(gen)作废。

        隐式调用方自行判断 `not loaded and not loading`；显式刷新（_reload_top）
        会先清 loading 再调用，以保证能拿到改动后的枚举结果。
        """
        node.gen += 1
        node.loading = True
        task = _LoadTask(node, node.gen, self._show_hidden(), self._loader)
        self.loadingStarted.emit(node.path)
        self._pool.start(task)

    @pyqtSlot(object, object, int)
    def _on_entries_loaded(self, node, entries, gen):
        if gen != node.gen:
            return  # 过期结果：期间又发起过新枚举，否则旧快照会占据视图
        # 先取完要用的自身状态：本槽由后台线程的投递触发，销毁时刻不受本槽控制，
        # 实测存在“槽跑到一半 self.__dict__ 已被清空”的现场（见 __init__ 处的说明）
        show_hidden = self._show_hidden()
        node.loading = False
        if node.key not in self._nodes or self._nodes.get(node.key) is not node:
            return  # 节点已被丢弃
        if node.loaded:
            return  # 幂等：同一节点重复的完成信号不得再次插入（避免重复行）
        parent_idx = self.createIndex(0, 0, node)
        first = 0
        self.beginInsertRows(parent_idx, first, first + len(entries) - 1) \
            if entries else None
        self._adopt(node, entries)
        node.loaded = True
        self._cache_put(node.key, show_hidden, entries)
        if entries:
            self.endInsertRows()
        try:
            self.directoryLoaded.emit(node.path)
        except RuntimeError:
            pass  # 模型已在本槽执行期间被销毁：目录已加载完，不必再通知

    # ---- QAbstractItemModel 必需实现 ----
    def index(self, *args, **kwargs):
        # 路径形式：index(path_str)
        if args and isinstance(args[0], str):
            return self._index_for_path(args[0])
        # 常规形式：index(row, column, parent)
        if not args:
            return self._invalid
        row = args[0]
        column = args[1] if len(args) > 1 else kwargs.get('column', 0)
        parent = args[2] if len(args) > 2 else kwargs.get('parent', self._invalid)
        if row < 0 or column < 0:
            return self._invalid
        if not parent.isValid():
            # invalid 根的唯一行 = 当前顶层目录节点
            if row == 0 and self._top_node is not None:
                return self.createIndex(0, column, self._top_node)
            return self._invalid
        p = parent.internalPointer()
        if isinstance(p, DirNode):
            if not p.loaded or not p.entries or row >= len(p.entries):
                return self._invalid
            return self.createIndex(row, column, p.entries[row])
        return self._invalid  # 条目不再有子

    def _index_for_path(self, path):
        """路径 → 索引，仅对【当前显示目录】及其条目有效。

        其它目录的节点虽存在 `self._nodes` 里（缓存/曾导航过），但不能返回
        它们的索引：两层结构中任何 DirNode 的父都报为 invalid 根，而
        index(0, 0, invalid) 只会解出顶层节点，于是非顶层节点的条目经
        排序代理映射会得到“看似有效实则错行”的索引（误定位、误改名）。
        判定任意路径是否目录请用 `entry_is_dir()`（零 syscall）。
        """
        path = os.path.normpath(path) if path else ""
        if not path:
            return self._invalid
        node = self._top_node
        if node is None:
            return self._invalid
        if _key(path) == self._top_key:
            return self.createIndex(0, 0, node)
        if node.loaded and node.entries:
            for r, e in enumerate(node.entries):
                if e.path == path:
                    return self.createIndex(r, 0, e)
        return self._invalid

    def parent(self, index):
        if not index.isValid():
            return self._invalid
        p = index.internalPointer()
        if isinstance(p, Entry) and p.node is not None:
            return self.createIndex(0, 0, p.node)   # 条目的父 = 其目录节点
        return self._invalid                          # 顶层目录节点的父 = invalid 根

    def rowCount(self, parent=None):
        if parent is None or not parent.isValid():
            return 1 if self._top_node is not None else 0
        p = parent.internalPointer()
        if isinstance(p, DirNode):
            if p is self._top_node and not p.loaded and not p.loading:
                self._start_load(p)
            return len(p.entries) if (p.loaded and p.entries) else 0
        return 0

    def canFetchMore(self, parent):
        if not parent.isValid():
            return False
        p = parent.internalPointer()
        return (p is self._top_node and isinstance(p, DirNode)
                and not p.loaded and not p.loading)

    def fetchMore(self, parent):
        if not parent.isValid():
            return
        p = parent.internalPointer()
        if p is self._top_node and isinstance(p, DirNode) and not p.loaded and not p.loading:
            self._start_load(p)

    def columnCount(self, parent=None):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(HEADERS):
                return HEADERS[section]
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        if not index.isValid():
            return base
        e = index.internalPointer()
        if isinstance(e, Entry) and e.is_dir:
            # 目录：可作为拖放目标；是否有子项由 rowCount/canFetchMore 决定
            base |= Qt.ItemFlag.ItemIsDropEnabled
        elif isinstance(e, Entry):
            # 文件：可拖拽、确定无子项
            base |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemNeverHasChildren
        return base

    # ---- 数据角色 ----
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e = index.internalPointer()
        if not isinstance(e, Entry):
            return None
        col = index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == COL_NAME:
                return e.name
            if col == COL_SIZE:
                return "" if e.is_dir else self._fmt_size(e.size)
            if col == COL_TYPE:
                return self._type_text(e)
            if col == COL_DATE:
                return self._fmt_mtime(e.mtime)
            if col == COL_SHOT:
                return self._shot_date(e)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        elif role == Qt.ItemDataRole.DecorationRole:
            if col == COL_NAME:
                return self._icon(e)
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_NAME:
                return e.path
        return None

    # ---- 重命名（setData）----
    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole):
            return False
        if index.column() != COL_NAME:
            return False
        e = index.internalPointer()
        if not isinstance(e, Entry):
            return False
        new_name = (value or "").strip()
        if not new_name or new_name == e.name:
            return False
        old_path = e.path
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.lexists(new_path):
            return False
        try:
            os.rename(old_path, new_path)
        except OSError as exc:
            logger.info("重命名失败 %s -> %s: %s", old_path, new_name, exc)
            return False
        node = e.node
        # 就地更新条目并 emit dataChanged：不重置模型，保留选中/滚动；
        # 名称变化后 PaneSortProxyModel 的 dynamicSortFilter 会自动重排。
        e.name = new_name
        e.path = os.path.normpath(new_path)
        if node is not None:
            self._cache_invalidate(node.path)
        self.dataChanged.emit(index, index,
                              [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.dirChanged.emit(os.path.dirname(old_path))
        return True

    # ---- 辅助格式化 ----
    @staticmethod
    def _fmt_size(size):
        if size is None or size < 0:
            return ""
        s = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if s < 1024 or unit == "TB":
                return f"{int(s)} {unit}" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} PB"

    @staticmethod
    def _fmt_mtime(mtime):
        if not mtime:
            return ""
        try:
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            return ""

    @staticmethod
    def _type_text(e):
        if e.is_dir:
            return "文件夹"
        ext = os.path.splitext(e.name)[1].lower().lstrip('.')
        if ext:
            return f"{ext.upper()} 文件"
        return "文件"

    @staticmethod
    def _shot_date(e):
        if e.is_dir:
            return ""
        try:
            from core.media_metadata import get_shot_date_cached
            return get_shot_date_cached(e.path) or ""
        except Exception:
            return ""

    _ICON_CACHE = {}

    @classmethod
    def _icon(cls, e):
        from PyQt6.QtWidgets import QStyle
        style = QApplication.style()
        sp = QStyle.StandardPixmap.SP_DirIcon if e.is_dir else QStyle.StandardPixmap.SP_FileIcon
        if sp not in cls._ICON_CACHE:
            cls._ICON_CACHE[sp] = style.standardIcon(sp)
        return cls._ICON_CACHE[sp]
