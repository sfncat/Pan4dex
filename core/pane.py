"""
Pan4dex 万格 — 单窗格组件
"""
import logging

logger = logging.getLogger("pan4dex.pane")
from PyQt6.QtGui import QFileSystemModel, QAction, QKeySequence, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QProgressBar,
    QLabel, QMenu, QMessageBox, QInputDialog, QLineEdit, QHBoxLayout, QTabWidget,
    QApplication, QSplitter
)
from PyQt6.QtCore import Qt, QDir, QMimeData, pyqtSignal, QThread, QPoint, QEvent, QSortFilterProxyModel, QModelIndex, QPersistentModelIndex
import os

from widgets.path_bar import PathBar
from widgets.pane_tree_view import PaneTreeView
from core.file_operations import FileOperations, FileOperationType, FileOperationResult


# 共享剪贴板：所有窗格（含四窗格/双窗格）共用一份，
# 解决「A 窗格复制、B 窗格粘贴」时各窗格自带空剪贴板导致粘贴失效的问题。
SHARED_CLIPBOARD: list = []
SHARED_CLIPBOARD_ACTION = None  # 'copy' / 'cut' / None


class ExifFileSystemModel(QFileSystemModel):
    """在 QFileSystemModel 的 4 列（名称/大小/类型/修改日期）之后追加「拍摄日期」列。

    直接子类化 QFileSystemModel 让源模型真正拥有 5 列，因此上层的
    PaneSortProxyModel（QSortFilterProxyModel）可以完全用内建机制排序/映射，
    无需自行实现列扩展（PyQt6 下 QSortFilterProxyModel 索引的 internalPointer()
    访问会崩溃，且其 index() 对超出源列范围的列返回无效索引，不能直接加列）。

    拍摄日期由 exiftool 读取：
    - 照片：DateTimeOriginal -> CreateDate（EXIF 拍摄时间）
    - 视频：CreateDate -> DateTimeOriginal（QuickTime mvhd.creation_time）
    仅当文件是照片/视频（含 EXIF）时显示值，否则为空。
    """

    SHOT_DATE_COLUMN = 4  # 拍摄日期列

    def columnCount(self, parent=None):
        return super().columnCount() + 1

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal and section == self.SHOT_DATE_COLUMN:
            if role == Qt.ItemDataRole.DisplayRole:
                return "拍摄日期"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return None
        return super().headerData(section, orientation, role)

    def data(self, index, role):
        if index.isValid() and index.column() == self.SHOT_DATE_COLUMN:
            if role == Qt.ItemDataRole.DisplayRole:
                return self.shot_date(index) or ""
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return None
        return super().data(index, role)

    def shot_date(self, index):
        """读取拍摄日期（仅查缓存，避免渲染时逐文件启动 exiftool 卡顿 UI）。

        缓存由 navigate_to 后的后台 prefetch 批量填充，完成后视图自动刷新。
        """
        if not index.isValid():
            return None
        path = self.filePath(index)
        if not path:
            return None
        from core.media_metadata import get_shot_date_cached
        return get_shot_date_cached(path)


class PaneSortProxyModel(QSortFilterProxyModel):
    """每个窗格独立的排序代理模型。

    四个窗格共享同一个 ExifFileSystemModel（5 列）作为数据源（性能考虑），
    但排序状态若直接作用在共享模型上，任意窗格点表头都会让所有窗格一起重排。
    通过本代理模型，让每个窗格持有独立的排序状态：点哪个窗格，只排哪个窗格。
    同时保持“目录优先”的文件管理器习惯排序。

    「拍摄日期」列（第 4 列）由源模型直接提供，本代理只需按字符串比较。
    """

    SHOT_DATE_COLUMN = 4  # 拍摄日期列（源模型第 4 列）

    def lessThan(self, left, right):
        col = left.column()
        # 拍摄日期列：按字符串比较（无拍摄日期的排最后）
        if col == self.SHOT_DATE_COLUMN:
            l = left.data(Qt.ItemDataRole.DisplayRole) or ""
            r = right.data(Qt.ItemDataRole.DisplayRole) or ""
            if l != r:
                return l < r
        # 目录始终排在文件前面（任意列排序都保持）
        l_is_dir = self._is_dir(left)
        r_is_dir = self._is_dir(right)
        if l_is_dir != r_is_dir:
            return l_is_dir
        # 名称列：不区分大小写
        if col == 0:
            return left.data(Qt.ItemDataRole.DisplayRole).lower() < right.data(Qt.ItemDataRole.DisplayRole).lower()
        # 其他列（大小/类型/修改时间/拍摄日期相同值）用默认比较
        return super().lessThan(left, right)

    def _is_dir(self, index):
        """判断是否为目录。

        注意：QSortFilterProxyModel::lessThan 传入的 left/right 是「源模型索引」
        （而非代理索引），因此直接经 sourceModel().filePath 取路径，不能 mapToSource。
        """
        try:
            if self.sourceModel() is None or index is None or not index.isValid():
                return False
            path = self.sourceModel().filePath(index)
            return bool(path) and os.path.isdir(path)
        except Exception:
            return False


class Pane(QWidget):
    """单个窗格组件"""
    
    # 信号
    path_changed = pyqtSignal(str)  # 路径变更信号
    activated = pyqtSignal(object)  # 窗格被激活信号
    shot_dates_ready = pyqtSignal()  # 后台 prefetch 拍摄日期完成（跨线程安全，自动投递主线程）
    
    def __init__(self, pane_id: str, parent=None):
        super().__init__(parent)
        
        self.pane_id = pane_id
        self.current_path = QDir.homePath()
        self.file_ops = FileOperations()
        # 剪贴板指向模块级共享对象（跨窗格复制/剪切/粘贴）
        self.clipboard = SHARED_CLIPBOARD
        self.clipboard_action = SHARED_CLIPBOARD_ACTION
        
        # 导航历史（支持前进/后退）
        self._nav_history = [self.current_path]
        self._nav_index = 0
        
        # 拖拽起始位置
        self.drag_start_pos = None
        
        # 创建 UI
        self.init_ui()
        
        # 模型已在 init_ui 中通过 _setup_shared_model 设置
        
        # 设置默认路径
        self.navigate_to(self.current_path)
    
    def focusInEvent(self, a0):
        """窗格获得焦点时发出激活信号"""
        self.activated.emit(self)
        super().focusInEvent(a0)
    
    def eventFilter(self, obj, event):
        """事件过滤器"""
        # 只记录有意义的事件，过滤掉高频的 paint/move/resize 等
        et = event.type()
        
        # 鼠标侧键导航（后退/前进）- viewport 上捕获
        if obj == self.tree_view.viewport():
            if et == QEvent.Type.MouseButtonPress:
                self.activated.emit(self)
                if hasattr(event, 'button'):
                    btn = event.button()
                    if btn == Qt.MouseButton.BackButton:
                        logger.info("Mouse back button -> go_back")
                        self.go_back()
                        return True
                    elif btn == Qt.MouseButton.ForwardButton:
                        logger.info("Mouse forward button -> go_forward")
                        self.go_forward()
                        return True
            elif et == QEvent.Type.FocusIn:
                self.activated.emit(self)
        
        # 标签栏双击检测：双击标签关闭，双击空白新建
        if et == QEvent.Type.MouseButtonDblClick:
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            if hasattr(self, '_tab_bar') and obj == self._tab_bar:
                # 事件直接到达 tab bar：tabAt 判断标签/空白
                tab_index = self._tab_bar.tabAt(pos)
                if tab_index >= 0:
                    self.close_pane_tab(tab_index)
                else:
                    self.add_pane_tab(self.current_path)
                return True
            elif hasattr(self, 'pane_tabs') and obj == self.pane_tabs:
                # 事件到达 QTabWidget：可能是 tab bar 未覆盖的空白区域
                if hasattr(self, '_tab_bar'):
                    tab_bar_pos = self._tab_bar.mapFrom(self.pane_tabs, pos)
                    if not self._tab_bar.rect().contains(tab_bar_pos):
                        # 在 tab bar 几何区域外 → 空白区域 → 新建标签
                        self.add_pane_tab(self.current_path)
                        return True
        
        return False

    def init_ui(self):
        """初始化 UI"""
        import time
        _t0 = time.perf_counter()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 路径栏
        self.path_bar = PathBar()
        logger.info(f"[启动计时] PathBar 创建: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.path_bar.path_entered.connect(self.on_path_entered)
        self.path_bar.tree_toggle_requested.connect(self.toggle_tree)
        self.path_bar.tabs_toggle_requested.connect(self.toggle_tabs)
        self.path_bar.terminal_requested.connect(self.open_terminal_here)
        self.path_bar.view_mode_requested.connect(self.on_view_mode_changed)
        self.path_bar.new_folder_requested.connect(self.new_folder)
        self.layout.addWidget(self.path_bar)
        # 固定路径栏高度：窗格较高时 QVBoxLayout 会把多余空间均分给各控件，
        # 导致 PathBar 被拉高（内部控件停在顶部、下方大片空白）
        self.path_bar.setFixedHeight(36)

        # 设置焦点策略，让 focusInEvent 能触发
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 水平容器：左侧目录树 + 右侧文件列表（QSplitter 支持拖动调宽）
        self.h_container = QSplitter(Qt.Orientation.Horizontal)
        self.h_container.setChildrenCollapsible(False)
        self.h_container.setHandleWidth(4)
        self._tree_width = 0  # 目录树宽度持久化（隐藏时记录，显示时恢复）

        # 内嵌目录树（独立模型，延迟启动扫描）
        self.pane_tree_view = PaneTreeView()
        self.pane_tree_view.folder_clicked.connect(self.on_pane_tree_clicked)
        self.pane_tree_view.setVisible(False)  # 默认隐藏
        self.h_container.addWidget(self.pane_tree_view)

        # 文件列表容器
        self.file_list_widget = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_widget)
        self.file_list_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list_layout.setSpacing(0)

        # 文件列表
        self.tree_view = QTreeView()
        self.tree_view.setRootIsDecorated(False)
        self.tree_view.setAlternatingRowColors(False)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(False)
        self.tree_view.setAllColumnsShowFocus(True)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        # 列标题右键：弹出列选择菜单，不触发窗格右键菜单
        self.tree_view.header().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.header().customContextMenuRequested.connect(self.show_column_menu)
        self.tree_view.viewport().installEventFilter(self)

        # 拖拽支持
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setDragDropMode(QTreeView.DragDropMode.DragDrop)

        self.file_list_layout.addWidget(self.tree_view)

        # 超大图标视图（独立于 QTreeView，安全处理大图标）
        from widgets.thumbnail_view import ThumbnailView
        self.thumbnail_view = ThumbnailView()
        self.thumbnail_view.setVisible(False)
        self.thumbnail_view.itemDoubleClicked.connect(self.on_thumbnail_item_double_clicked)
        self.file_list_layout.addWidget(self.thumbnail_view)

        self.h_container.addWidget(self.file_list_widget)
        self.h_container.setStretchFactor(0, 0)  # 目录树不随窗口伸缩
        self.h_container.setStretchFactor(1, 1)  # 文件列表占据剩余空间
        self.h_container.setSizes([200, 800])

        self.layout.addWidget(self.h_container, 1)  # 文件列表独占剩余空间

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(3)
        self.progress_bar.setTextVisible(False)
        self.layout.addWidget(self.progress_bar)

        # 状态栏
        self.status_label = QLabel()
        self.status_label.setContentsMargins(5, 2, 5, 2)
        self.status_label.setFixedHeight(24)  # 固定高度：避免窗格高时被拉伸
        self.layout.addWidget(self.status_label)

        # 窗格内标签页栏（默认隐藏）
        self.pane_tabs = QTabWidget()
        self.pane_tabs.setMaximumHeight(30)
        self.pane_tabs.setTabsClosable(True)
        self.pane_tabs.tabCloseRequested.connect(self.close_pane_tab)
        self.pane_tabs.currentChanged.connect(self.on_pane_tab_changed)
        self.pane_tabs.setVisible(False)
        # 标签栏右键菜单
        self.pane_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pane_tabs.customContextMenuRequested.connect(self.show_pane_tab_context_menu)
        # 双击标签栏处理 - 安装在 QTabWidget 上
        self._tab_bar = self.pane_tabs.tabBar()
        self._tab_bar.installEventFilter(self)
        self.pane_tabs.installEventFilter(self)
        self.layout.addWidget(self.pane_tabs)

        # 初始化第一个标签页
        self._pane_tab_paths = [self.current_path]
        self.pane_tabs.addTab(QLabel(), os.path.basename(self.current_path) if os.path.basename(self.current_path) else self.current_path)
        
        # 设置文件模型（使用共享模型）
        self._setup_shared_model()
        
        # 选择变化时更新预览（需要在 model 设置之后）
        self.tree_view.selectionModel().selectionChanged.connect(self.on_selection_changed)
    
    def _setup_shared_model(self):
        """设置共享的 QFileSystemModel"""
        # 使用静态共享模型，避免每个窗格都创建
        if not hasattr(Pane, '_shared_file_model') or Pane._shared_file_model is None:
            import time
            t0 = time.perf_counter()
            model = ExifFileSystemModel()
            model.setRootPath("")
            model.setFilter(
                QDir.Filter.AllDirs | 
                QDir.Filter.Files | 
                QDir.Filter.NoDotAndDotDot |
                QDir.Filter.Hidden
            )
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(f"[启动计时] QFileSystemModel 创建（首次，后续共享）: {elapsed:.1f}ms")
            Pane._shared_file_model = model
        
        self.model = Pane._shared_file_model
        # 每个窗格独立的排序代理：点表头只排序本窗格，不影响其他窗格
        self.sort_proxy = PaneSortProxyModel(self)
        self.sort_proxy.setSourceModel(self.model)
        self.tree_view.setModel(self.sort_proxy)

        # 恢复列显示状态（拍摄日期列默认隐藏；用户勾选后持久化）
        self._restore_column_visibility()

        # 后台 prefetch 完成后刷新视图（信号跨线程自动 QueuedConnection，安全）
        self.shot_dates_ready.connect(self._refresh_shot_date_column)

        # 目录异步加载完成后，若正好是当前目录则预读拍摄日期
        self.model.directoryLoaded.connect(self._on_directory_loaded_shot_dates)

        # 设置根索引
        self._set_root_index(self.current_path)

    # ---- 列显示状态（QSettings 持久化，按窗格独立）----
    _COLUMN_VISIBILITY_KEY = "pane/column_visibility"  # 形如 "1,1,1,1,0"，按窗格加后缀区分

    def _column_visibility_key(self):
        return f"{self._COLUMN_VISIBILITY_KEY}_{self.pane_id}"

    def _get_settings(self):
        from PyQt6.QtCore import QSettings
        from config.app_config import ORG_NAME, APP_NAME
        return QSettings(ORG_NAME, APP_NAME)

    def _restore_column_visibility(self):
        """恢复列可见性：无记录时默认隐藏「拍摄日期」列，其余显示。每窗格独立。"""
        try:
            raw = self._get_settings().value(self._column_visibility_key(), "")
            vis = []
            if raw:
                vis = [x == "1" for x in str(raw).split(",")]
            model = self.tree_view.model()
            n = model.columnCount() if model else 0
            default_hidden = getattr(model, 'SHOT_DATE_COLUMN', 4) if model else 4
            for col in range(n):
                visible = vis[col] if col < len(vis) else (col != default_hidden)
                self.tree_view.setColumnHidden(col, not visible)
        except Exception:
            pass

    def _save_column_visibility(self):
        try:
            model = self.tree_view.model()
            n = model.columnCount() if model else 0
            vis = ",".join(
                "1" if not self.tree_view.isColumnHidden(c) else "0"
                for c in range(n)
            )
            self._get_settings().setValue(self._column_visibility_key(), vis)
        except Exception:
            pass

    def _on_directory_loaded_shot_dates(self, path):
        """共享模型目录加载完成：若是本窗格当前目录，则预读拍摄日期。"""
        try:
            if os.path.normpath(path) == os.path.normpath(self.current_path):
                self._prefetch_shot_dates()
        except Exception:
            pass

    def _map_to_source(self, index):
        """把视图/代理模型索引映射回共享源模型（QFileSystemModel）索引"""
        if index is None or not index.isValid():
            return index
        return self.sort_proxy.mapToSource(index)

    def _set_root_index(self, path: str) -> bool:
        """经排序代理设置当前目录的根索引，成功返回 True"""
        source_index = self.model.index(path)
        if source_index.isValid():
            proxy_index = self.sort_proxy.mapFromSource(source_index)
            self.tree_view.setRootIndex(proxy_index)
            return True
        return False
        

    

    
    def get_state(self) -> dict:
        """获取窗格状态"""
        return {
            'current_path': self.current_path,
            'tree_visible': self.pane_tree_view.isVisible(),
            'tabs_visible': self.pane_tabs.isVisible(),
            'tab_paths': self._pane_tab_paths.copy(),
            'tab_current': self.pane_tabs.currentIndex() if self.pane_tabs.isVisible() else 0,
        }

    def set_state(self, state: dict):
        """恢复窗格状态"""
        if not state:
            return
        
        # 恢复标签页
        tab_paths = state.get('tab_paths', [])
        if tab_paths:
            # 清除现有标签页
            while self.pane_tabs.count() > 0:
                self.pane_tabs.removeTab(0)
            self._pane_tab_paths = []
            
            # 恢复标签页
            for path in tab_paths:
                self._pane_tab_paths.append(path)
                self.pane_tabs.addTab(QLabel(), os.path.basename(path) if os.path.basename(path) else path)
            
            # 恢复当前标签页
            current_idx = state.get('tab_current', 0)
            if 0 <= current_idx < len(tab_paths):
                self.pane_tabs.setCurrentIndex(current_idx)
                path = tab_paths[current_idx]
            else:
                path = tab_paths[0] if tab_paths else state.get('current_path', QDir.homePath())
            
            self.current_path = path
            self.path_bar.set_path(path)
            self._set_root_index(path)
            if self.pane_tree_view.isVisible():
                self.pane_tree_view.expand_to_path(path)
            self.update_status_bar()
        
        # 恢复目录树可见性
        if state.get('tree_visible', False):
            self.set_tree_visible(True)
        else:
            self.set_tree_visible(False)
        
        # 恢复标签栏可见性
        if state.get('tabs_visible', False):
            self.pane_tabs.setVisible(True)
            self.path_bar.set_tabs_button_checked(True)
        else:
            self.pane_tabs.setVisible(False)
            self.path_bar.set_tabs_button_checked(False)

    def _prefetch_shot_dates(self):
        """后台批量预读当前目录文件的拍摄日期，填充缓存后刷新视图。

        注意：Qt 模型只能在主线程访问，因此目录枚举在主线程完成，
        后台线程只调用 exiftool 子进程（纯 IO，不触碰 Qt 对象）。
        """
        try:
            model = self.model
            idx = model.index(self.current_path)
            if not idx.isValid():
                return
            paths = []
            for row in range(model.rowCount(idx)):
                child = model.index(row, 0, idx)
                # 目录/盘符不需要拍摄日期，也避免 exiftool 读取挂载点时卡住
                if model.isDir(child):
                    continue
                p = model.filePath(child)
                if p:
                    paths.append(p)
            if not paths:
                return
        except Exception:
            return

        import threading

        def work():
            try:
                from core.media_metadata import batch_get_shot_dates
                batch_get_shot_dates(paths)
                # 用信号通知主线程刷新（QTimer.singleShot 在无事件循环的后台线程调用不生效，
                # 会导致缓存已填充但视图不刷新、列一直空白的问题）
                self.shot_dates_ready.emit()
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _refresh_shot_date_column(self):
        """拍摄日期缓存就绪后重绘视图。"""
        try:
            self.tree_view.viewport().update()
        except Exception:
            pass

    def navigate_to(self, path: str):
        """导航到指定路径"""
        import os
        if os.path.isdir(path):
            self.current_path = path
            self.path_bar.set_path(path)

            # 不使用 setRootPath（会改变共享模型的根），直接用 index + setRootIndex（经排序代理映射）
            if not self._set_root_index(path):
                # 模型还没加载完，用 QTimer 延迟重试（避免重复连接 directoryLoaded 信号导致泄漏）
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, lambda: self._retry_set_root_index(path, 0))

            # 同步展开内嵌目录树到当前路径（树不可见时不扫描磁盘，显示时会重新定位）
            if self.pane_tree_view.isVisible():
                self.pane_tree_view.expand_to_path(path)

            # 更新当前标签页的名称和路径
            current_idx = self.pane_tabs.currentIndex()
            if self.pane_tabs.isVisible() and 0 <= current_idx < len(self._pane_tab_paths):
                self._pane_tab_paths[current_idx] = path
                self.pane_tabs.setTabText(current_idx, os.path.basename(path) if os.path.basename(path) else path)

            # 更新导航历史
            if self._nav_history[self._nav_index] != path:
                self._nav_history = self._nav_history[:self._nav_index + 1]
                self._nav_history.append(path)
                self._nav_index = len(self._nav_history) - 1

            self.update_status_bar()
            self.path_changed.emit(path)
            # 后台预读当前目录文件的拍摄日期（exiftool 批量一次调用）
            self._prefetch_shot_dates()
            # 超大图标模式下同步刷新缩略图视图
            if hasattr(self, 'thumbnail_view') and self.thumbnail_view.isVisible():
                self.thumbnail_view.load_directory(path)

    def _retry_set_root_index(self, path, attempt):
        """延迟重试设置 root index，直到模型加载完成或超时"""
        if attempt > 20:  # 最多重试 20 次（约 1 秒）
            return
        if self.current_path != path:
            return  # 用户已导航到其他路径，放弃
        if self._set_root_index(path):
            return
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._retry_set_root_index(path, attempt + 1))

    def go_back(self):
        """后退到上一个目录"""
        if self._nav_index > 0:
            self._nav_index -= 1
            path = self._nav_history[self._nav_index]
            self._navigate_no_history(path)

    def go_forward(self):
        """前进到下一个目录"""
        if self._nav_index < len(self._nav_history) - 1:
            self._nav_index += 1
            path = self._nav_history[self._nav_index]
            self._navigate_no_history(path)

    def _navigate_no_history(self, path: str):
        """导航但不记录历史"""
        import os
        if os.path.isdir(path):
            self.current_path = path
            self.path_bar.set_path(path)
            self._set_root_index(path)

            if self.pane_tree_view.isVisible():
                self.pane_tree_view.expand_to_path(path)

            current_idx = self.pane_tabs.currentIndex()
            if self.pane_tabs.isVisible() and 0 <= current_idx < len(self._pane_tab_paths):
                self._pane_tab_paths[current_idx] = path
                self.pane_tabs.setTabText(current_idx, os.path.basename(path) if os.path.basename(path) else path)

            self.update_status_bar()
            self.path_changed.emit(path)

    def on_pane_tree_clicked(self, path: str):
        """内嵌目录树点击 - 导航到本窗格"""
        self.navigate_to(path)

    def set_tree_visible(self, visible: bool):
        """设置内嵌目录树可见性"""
        if not visible:
            # 先记录当前树宽度再隐藏（splitter 隐藏后尺寸会变化）
            sizes = self.h_container.sizes()
            if sizes and sizes[0] > 20:
                self._tree_width = sizes[0]
        self.pane_tree_view.setVisible(visible)
        self.path_bar.set_tree_button_checked(visible)
        if visible:
            # 恢复上次宽度（默认 200），树刚显示时滚动定位才生效
            total = max(400, self.width())
            tree_w = self._tree_width or 200
            tree_w = max(180, min(tree_w, total - 200))
            self.h_container.setSizes([tree_w, total - tree_w])
            self.pane_tree_view.expand_to_path(self.current_path)

    def toggle_tree(self):
        """切换本窗格的目录树"""
        visible = self.pane_tree_view.isVisible()
        self.set_tree_visible(not visible)

    def toggle_tabs(self):
        """切换本窗格的标签页栏"""
        visible = self.pane_tabs.isVisible()
        self.pane_tabs.setVisible(not visible)
        self.path_bar.set_tabs_button_checked(not visible)

    def _on_tab_bar_double_clicked(self, index):
        """双击标签 → 关闭标签页（重命名请用右键菜单）"""
        if index >= 0:
            self.close_pane_tab(index)

    def _rename_pane_tab(self, index):
        """重命名标签页"""
        from PyQt6.QtWidgets import QInputDialog
        
        current_name = self.pane_tabs.tabText(index)
        new_name, ok = QInputDialog.getText(
            self, "重命名标签页", "新名称:", text=current_name
        )
        if ok and new_name.strip():
            self.pane_tabs.setTabText(index, new_name.strip())

    def show_pane_tab_context_menu(self, position):
        """显示窗格标签栏右键菜单"""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
        """)

        # 定位右键点中的标签
        tab_index = self.pane_tabs.tabBar().tabAt(position)

        new_tab_action = QAction("新建标签页(&N)", self)
        new_tab_action.triggered.connect(lambda: self.add_pane_tab())
        menu.addAction(new_tab_action)

        if tab_index >= 0:
            rename_tab_action = QAction("重命名标签页(&R)", self)
            rename_tab_action.triggered.connect(lambda: self._rename_pane_tab(tab_index))
            menu.addAction(rename_tab_action)

            close_tab_action = QAction("关闭标签页(&C)", self)
            close_tab_action.triggered.connect(lambda: self.close_pane_tab(tab_index))
            menu.addAction(close_tab_action)

        menu.exec(QCursor.pos())

    def close_pane_tab(self, index):
        """关闭窗格内标签页"""
        if self.pane_tabs.count() > 1:
            self.pane_tabs.removeTab(index)
            if index < len(self._pane_tab_paths):
                self._pane_tab_paths.pop(index)

    def on_pane_tab_changed(self, index):
        """窗格内标签页切换"""
        if hasattr(self, 'model') and 0 <= index < len(self._pane_tab_paths):
            path = self._pane_tab_paths[index]
            if os.path.isdir(path):
                # 更新当前路径并刷新文件列表
                self.current_path = path
                self.path_bar.set_path(path)
                self._set_root_index(path)
                if self.pane_tree_view.isVisible():
                    self.pane_tree_view.expand_to_path(path)
                self.update_status_bar()
                # 超大图标模式下同步刷新缩略图视图
                if hasattr(self, 'thumbnail_view') and self.thumbnail_view.isVisible():
                    self.thumbnail_view.load_directory(path)

    def add_pane_tab(self, path: str = None):
        """添加窗格内标签页"""
        if path is None:
            path = self.current_path
        self._pane_tab_paths.append(path)
        self.pane_tabs.addTab(QLabel(), os.path.basename(path) if os.path.basename(path) else path)
        # 添加标签页后显示标签页栏
        if not self.pane_tabs.isVisible():
            self.pane_tabs.setVisible(True)
            self.path_bar.set_tabs_button_checked(True)

    def on_path_entered(self, path: str):
        """路径栏输入处理"""
        import os
        if os.path.isdir(path):
            self.navigate_to(path)
        else:
            # 路径无效，恢复原路径
            self.path_bar.set_path(self.current_path)
    
    def on_item_double_clicked(self, index):
        """双击项目处理"""
        path = self.model.filePath(self._map_to_source(index))
        import os
        if os.path.isdir(path):
            self.navigate_to(path)
        else:
            # 打开文件
            self.open_file(path)
    
    def on_thumbnail_item_double_clicked(self, item):
        """超大图标视图双击处理"""
        path = item.data(Qt.ItemDataRole.UserRole)
        is_dir = item.data(Qt.ItemDataRole.UserRole + 1)
        if is_dir:
            self.navigate_to(path)
        else:
            self.open_file(path)
    
    def open_file(self, file_path: str):
        """打开文件"""
        # 尝试使用文件关联
        main_window = self.window()
        if hasattr(main_window, 'file_associations'):
            if main_window.file_associations.open_file(file_path):
                return
        
        # 回退到系统默认
        import subprocess
        import sys
        
        if sys.platform == "win32":
            import os
            os.startfile(file_path)
        else:
            # xdg-open 等待默认应用就绪才返回（可能 >10s），不能阻塞等待；
            # 短观察：存活视为启动中（成功），立即非零退出才回退 gio
            import shutil
            from config.file_associations import _clean_child_env
            try:
                if shutil.which("xdg-open"):
                    p = subprocess.Popen(
                        ["xdg-open", file_path],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        env=_clean_child_env(),
                    )
                    try:
                        rc = p.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        return
                    if rc == 0:
                        return
                if shutil.which("gio"):
                    subprocess.Popen(
                        ["gio", "open", file_path],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        env=_clean_child_env(),
                    )
            except Exception as e:
                logger.warning("打开文件失败 %s: %s", file_path, e)
    
    def on_selection_changed(self):
        """选择变化时更新预览"""
        indexes = self.tree_view.selectedIndexes()
        if indexes:
            path = self.model.filePath(self._map_to_source(indexes[0]))
            main_window = self.window()
            if hasattr(main_window, 'preview_panel') and main_window.preview_panel.isVisible():
                main_window.preview_panel.preview_file(path)
    
    def update_status_bar(self):
        """更新状态栏"""
        import os
        try:
            entries = os.listdir(self.current_path)
            files = [f for f in entries if os.path.isfile(os.path.join(self.current_path, f))]
            dirs = [d for d in entries if os.path.isdir(os.path.join(self.current_path, d))]
            self.status_label.setText(f"{len(dirs)} 个目录, {len(files)} 个文件")
        except PermissionError:
            self.status_label.setText("无权限访问")
    
    def show_column_menu(self, position):
        """列标题右键菜单：勾选要显示的列（名称/大小/类型/修改日期）"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
        """)
        model = self.tree_view.model()
        for col in range(model.columnCount()):
            title = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            action = menu.addAction(str(title) if title else f"列 {col + 1}")
            action.setCheckable(True)
            action.setChecked(not self.tree_view.isColumnHidden(col))
            def _set_col_visible(checked, c=col):
                self.tree_view.setColumnHidden(c, not checked)
                self._save_column_visibility()
                # 勾选显示「拍摄日期」列时：立即刷新视口，并补一次 prefetch
                # （目录可能已加载完导致 directoryLoaded 不再触发，或上次 prefetch 未完成）
                if checked and c == getattr(self.tree_view.model(), 'SHOT_DATE_COLUMN', -1):
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, self._prefetch_shot_dates)
                self.tree_view.viewport().update()
            action.toggled.connect(_set_col_visible)
        menu.exec(self.tree_view.header().mapToGlobal(position))

    def show_context_menu(self, position):
        """显示右键菜单"""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
        """)
        
        # 获取选中项
        indexes = self.tree_view.selectedIndexes()
        
        if indexes:
            # 有选中项
            open_action = QAction("打开(&O)", self)
            open_action.triggered.connect(self.open_selected)
            menu.addAction(open_action)
            
            menu.addSeparator()
            
            copy_action = QAction("复制(&C)", self)
            copy_action.setShortcut(QKeySequence("Ctrl+C"))
            copy_action.triggered.connect(self.copy_selected)
            menu.addAction(copy_action)
            
            cut_action = QAction("剪切(&X)", self)
            cut_action.setShortcut(QKeySequence("Ctrl+X"))
            cut_action.triggered.connect(self.cut_selected)
            menu.addAction(cut_action)
            
            paste_action = QAction("粘贴(&V)", self)
            paste_action.setShortcut(QKeySequence("Ctrl+V"))
            paste_action.triggered.connect(self.paste)
            menu.addAction(paste_action)
            
            menu.addSeparator()
            
            delete_action = QAction("删除(&D)", self)
            delete_action.setShortcut(QKeySequence("Delete"))
            delete_action.triggered.connect(self.delete_selected)
            menu.addAction(delete_action)
            
            rename_action = QAction("重命名(&R)", self)
            rename_action.setShortcut(QKeySequence("F2"))
            rename_action.triggered.connect(self.rename_selected)
            menu.addAction(rename_action)
            
            menu.addSeparator()
            
            # 如果选中的是目录，添加到收藏夹
            selected_path = None
            for idx in indexes:
                if idx.column() == 0:
                    path = self.model.filePath(self._map_to_source(idx))
                    if os.path.isdir(path):
                        selected_path = path
                        break
            
            if selected_path:
                add_bookmark_action = QAction("添加到收藏夹(&B)", self)
                add_bookmark_action.triggered.connect(
                    lambda: self.add_to_bookmarks(selected_path)
                )
                menu.addAction(add_bookmark_action)
            
            menu.addSeparator()
            
            terminal_action = QAction("打开终端(&T)", self)
            terminal_action.triggered.connect(self.open_terminal_here)
            menu.addAction(terminal_action)
        else:
            # 空白区域
            new_folder_action = QAction("新建文件夹(&F)", self)
            new_folder_action.triggered.connect(self.new_folder)
            menu.addAction(new_folder_action)
            
            new_file_action = QAction("新建文件(&N)", self)
            new_file_action.triggered.connect(self.new_file)
            menu.addAction(new_file_action)
            
            menu.addSeparator()
            
            paste_action = QAction("粘贴(&V)", self)
            paste_action.setShortcut(QKeySequence("Ctrl+V"))
            paste_action.triggered.connect(self.paste)
            menu.addAction(paste_action)
            
            menu.addSeparator()
            
            new_tab_action = QAction("新建标签页(&T)", self)
            new_tab_action.triggered.connect(lambda: self.add_pane_tab())
            menu.addAction(new_tab_action)
            
            menu.addSeparator()
            
            terminal_action = QAction("打开终端(&T)", self)
            terminal_action.triggered.connect(self.open_terminal_here)
            menu.addAction(terminal_action)
        
        menu.exec(QCursor.pos())
    
    def open_selected(self):
        """打开选中项"""
        indexes = self.tree_view.selectedIndexes()
        if indexes:
            path = self.model.filePath(self._map_to_source(indexes[0]))
            import os
            if os.path.isdir(path):
                self.navigate_to(path)
            else:
                self.open_file(path)
    
    def copy_selected(self):
        """复制选中项"""
        global SHARED_CLIPBOARD_ACTION
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(self._map_to_source(index)))
        
        if paths:
            SHARED_CLIPBOARD.clear()
            SHARED_CLIPBOARD.extend(paths)
            SHARED_CLIPBOARD_ACTION = 'copy'
            self.status_label.setText(f"已复制 {len(paths)} 个项目")
    
    def cut_selected(self):
        """剪切选中项"""
        global SHARED_CLIPBOARD_ACTION
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(self._map_to_source(index)))
        
        if paths:
            SHARED_CLIPBOARD.clear()
            SHARED_CLIPBOARD.extend(paths)
            SHARED_CLIPBOARD_ACTION = 'cut'
            self.status_label.setText(f"已剪切 {len(paths)} 个项目")
    
    def paste(self):
        """粘贴"""
        global SHARED_CLIPBOARD_ACTION
        if not SHARED_CLIPBOARD:
            return
        
        if SHARED_CLIPBOARD_ACTION == 'copy':
            self.file_ops.set_progress_callback(self._on_copy_progress)
            self.file_ops.copy(SHARED_CLIPBOARD, self.current_path)
            self.file_ops.set_progress_callback(None)
        elif SHARED_CLIPBOARD_ACTION == 'cut':
            self.file_ops.set_progress_callback(self._on_copy_progress)
            self.file_ops.move(SHARED_CLIPBOARD, self.current_path)
            self.file_ops.set_progress_callback(None)
            SHARED_CLIPBOARD.clear()
            SHARED_CLIPBOARD_ACTION = None
        
        self.navigate_to(self.current_path)
        self.hide_progress()
    
    def _on_copy_progress(self, percent: int, filename: str):
        """复制进度回调"""
        self.show_progress(percent)
        self.status_label.setText(f"正在复制: {filename}")
    
    def delete_selected(self):
        """删除选中项"""
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(self._map_to_source(index)))
        
        if not paths:
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {len(paths)} 个项目到回收站吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.file_ops.set_progress_callback(self._on_copy_progress)
            result = self.file_ops.delete(paths, safe=True)
            self.file_ops.set_progress_callback(None)
            
            if result.success:
                self.status_label.setText(f"已删除 {result.files_affected} 个项目")
            else:
                QMessageBox.warning(self, "删除失败", result.error)
            
            self.navigate_to(self.current_path)
            self.hide_progress()
    
    def rename_selected(self):
        """重命名选中项"""
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        path = self.model.filePath(self._map_to_source(indexes[0]))
        old_name = os.path.basename(path)
        
        new_name, ok = QInputDialog.getText(
            self, "重命名", "新名称:", QLineEdit.EchoMode.Normal, old_name
        )
        
        if ok and new_name and new_name != old_name:
            result = self.file_ops.rename(path, new_name)
            if result.success:
                self.navigate_to(self.current_path)
            else:
                QMessageBox.warning(self, "重命名失败", result.error)
    
    def add_to_bookmarks(self, path):
        """添加到收藏夹"""
        main_window = self.window()
        if main_window and hasattr(main_window, 'bookmark_sidebar'):
            main_window.bookmark_sidebar.add_bookmark_with_path(path)
    
    def new_folder(self):
        """新建文件夹"""
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "文件夹名称:", QLineEdit.EchoMode.Normal, "新建文件夹"
        )
        
        if ok and name:
            result = self.file_ops.create_folder(self.current_path, name)
            if result.success:
                self.navigate_to(self.current_path)
            else:
                QMessageBox.warning(self, "创建失败", result.error)
    
    def new_file(self):
        """新建文件"""
        name, ok = QInputDialog.getText(
            self, "新建文件", "文件名称:", QLineEdit.EchoMode.Normal, "新建文件.txt"
        )
        
        if ok and name:
            result = self.file_ops.create_file(self.current_path, name)
            if result.success:
                self.navigate_to(self.current_path)
            else:
                QMessageBox.warning(self, "创建失败", result.error)
    

    def on_view_mode_changed(self, mode: str):
        """查看模式变化"""
        from PyQt6.QtCore import QSize
        logger.info(f"[DEBUG] Pane.on_view_mode_changed: mode={mode}, current_path={self.current_path}")
        try:
            if mode == 'icon':
                self.tree_view.setVisible(True)
                self.thumbnail_view.setVisible(False)
                self.tree_view.setIconSize(QSize(48, 48))
            elif mode == 'xlarge':
                # 超大图标模式 - 使用独立的 ThumbnailView
                self.tree_view.setVisible(False)
                self.thumbnail_view.setVisible(True)
                # 强制刷新布局
                self.thumbnail_view.show()
                self.thumbnail_view.updateGeometry()
                self.file_list_widget.updateGeometry()
                self.file_list_layout.activate()
                self.file_list_widget.repaint()
                QApplication.processEvents()
                logger.info(f"[DEBUG] Calling thumbnail_view.load_directory({self.current_path})")
                self.thumbnail_view.load_directory(self.current_path)
            else:
                self.tree_view.setVisible(True)
                self.thumbnail_view.setVisible(False)
                self.tree_view.setIconSize(QSize(16, 16))
        except Exception as e:
            import logging
            logging.getLogger("pan4dex.pane").error(f"View mode change error: {e}")
        self.path_bar.set_view_mode(mode)

    def set_button_visibility(self, button_name: str, visible: bool):
        """设置工具栏按钮可见性"""
        self.path_bar.set_button_visibility(button_name, visible)

    def open_terminal_here(self):
        """在当前目录打开终端"""
        import subprocess
        import shutil
        import sys
        import os
        
        if sys.platform == "win32":
            # Windows 终端
            terminal = None
            # 按优先级检测 Windows 终端
            windows_terminals = [
                ("Windows Terminal", "wt.exe", [ "-d", "{path}"]),
                ("PowerShell 7", "pwsh.exe", ["-WorkingDirectory", "{path}"]),
                ("PowerShell", "powershell.exe", ["-NoExit", "-Command", "Set-Location '{path}'"]),
                ("Command Prompt", "cmd.exe", ["/K", "cd /d", "{path}"]),
            ]
            
            for name, exe, args_template in windows_terminals:
                if shutil.which(exe):
                    terminal = (name, exe, args_template)
                    break
            
            if terminal:
                name, exe, args_template = terminal
                args = [arg.replace("{path}", self.current_path) for arg in args_template]
                subprocess.Popen([exe] + args)
            else:
                QMessageBox.warning(self, "错误", "未找到可用的终端")
        else:
            # Linux 终端 - 按用户配置 → 系统默认 → 已安装终端 的顺序
            terminal = None
            
            # 1. 检测用户配置的终端（从配置文件读取）
            config_file = os.path.expanduser("~/.config/pan4dex/settings.json")
            if os.path.exists(config_file):
                try:
                    import json
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    user_terminal = config.get('terminal', '')
                    if user_terminal and shutil.which(user_terminal):
                        terminal = user_terminal
                except:
                    pass
            
            # 2. 检测系统默认终端
            if not terminal:
                # 检测 xdg-mime 设置的默认终端
                try:
                    result = subprocess.run(
                        ["xdg-mime", "query", "default", "x-scheme-handler/terminal"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        desktop_file = result.stdout.strip()
                        # 从 .desktop 文件获取 Exec
                        desktop_paths = [
                            "/usr/share/applications/" + desktop_file,
                            "/usr/local/share/applications/" + desktop_file,
                        ]
                        for dp in desktop_paths:
                            if os.path.exists(dp):
                                with open(dp, 'r') as f:
                                    for line in f:
                                        if line.startswith("Exec="):
                                            cmd = line.strip()[5:].split()[0]
                                            if shutil.which(cmd):
                                                terminal = cmd
                                                break
                                    if terminal:
                                        break
                except:
                    pass
            
            # 3. 按优先级检测已安装的终端
            if not terminal:
                linux_terminals = [
                    "x-terminal-emulator",  # Debian/Ubuntu 系统链接
                    "gnome-terminal",
                    "konsole",
                    "xfce4-terminal",
                    "mate-terminal",
                    "terminator",
                    "tilix",
                    "alacritty",
                    "kitty",
                    "urxvt",
                    "rxvt",
                    "xterm",
                ]
                for term in linux_terminals:
                    if shutil.which(term):
                        terminal = term
                        break
            
            if terminal:
                if terminal in ["gnome-terminal", "mate-terminal", "tilix"]:
                    subprocess.Popen([terminal, f"--working-directory={self.current_path}"])
                elif terminal == "konsole":
                    subprocess.Popen([terminal, "--workdir", self.current_path])
                elif terminal == "xfce4-terminal":
                    subprocess.Popen([terminal, f"--working-directory={self.current_path}"])
                elif terminal == "terminator":
                    subprocess.Popen([terminal, f"--working-directory={self.current_path}"])
                elif terminal == "alacritty":
                    subprocess.Popen([terminal, "--working-directory", self.current_path])
                elif terminal == "kitty":
                    subprocess.Popen([terminal, "--directory", self.current_path])
                else:
                    subprocess.Popen([terminal], cwd=self.current_path)
            else:
                QMessageBox.warning(self, "错误", "未找到可用的终端")
    
    def dragEnterEvent(self, event):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            self.setStyleSheet(self.styleSheet() + """
                QTreeView { border: 2px solid #2196F3; }
            """)
            event.accept()
        elif event.mimeData().hasFormat("application/x-pan4dex-drag"):
            self.setStyleSheet(self.styleSheet() + """
                QTreeView { border: 2px solid #2196F3; }
            """)
            event.accept()
    
    def dragLeaveEvent(self, event):
        """拖拽离开"""
        self.init_ui_style()
        event.accept()
    
    def dropEvent(self, event):
        """拖拽释放"""
        self.init_ui_style()
        
        # 处理跨窗格拖拽
        if event.mimeData().hasFormat("application/x-pan4dex-drag"):
            import json
            data = json.loads(event.mimeData().data("application/x-pan4dex-drag").data().decode())
            source_pane_id = data.get("source_pane_id", "")
            files = data.get("files", [])
            action = data.get("default_action", "copy")
            
            if files:
                if action == "copy":
                    self.file_ops.set_progress_callback(self._on_copy_progress)
                    self.file_ops.copy(files, self.current_path)
                    self.file_ops.set_progress_callback(None)
                elif action == "move":
                    self.file_ops.set_progress_callback(self._on_copy_progress)
                    self.file_ops.move(files, self.current_path)
                    self.file_ops.set_progress_callback(None)
                
                self.navigate_to(self.current_path)
                self.hide_progress()
            
            event.accept()
        elif event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            files = [url.toLocalFile() for url in urls if url.isLocalFile()]
            
            if files:
                self.file_ops.set_progress_callback(self._on_copy_progress)
                self.file_ops.copy(files, self.current_path)
                self.file_ops.set_progress_callback(None)
                self.navigate_to(self.current_path)
                self.hide_progress()
            
            event.accept()
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 处理拖拽开始"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        
        if not self.drag_start_pos:
            super().mouseMoveEvent(event)
            return
        
        # 检查是否移动了足够的距离
        if (event.pos() - self.drag_start_pos).manhattanLength() < 10:
            super().mouseMoveEvent(event)
            return
        
        # 获取选中的文件
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            super().mouseMoveEvent(event)
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(self._map_to_source(index)))
        
        if not paths:
            super().mouseMoveEvent(event)
            return
        
        # 创建拖拽对象
        from PyQt6.QtGui import QDrag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # 设置自定义 MIME 数据
        import json
        drag_data = {
            "source_pane_id": self.pane_id,
            "files": paths,
            "default_action": "copy"
        }
        mime_data.setData(
            "application/x-pan4dex-drag",
            json.dumps(drag_data).encode()
        )
        
        # 同时设置 URL 数据（兼容外部应用）
        from PyQt6.QtCore import QUrl
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime_data.setUrls(urls)
        
        drag.setMimeData(mime_data)
        
        # 执行拖拽
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
    
    def init_ui_style(self):
        """恢复默认样式"""
        self.setStyleSheet("""
            QTreeView {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                selection-background-color: #2196F3;
                outline: none;
            }
            QTreeView::item:hover {
                background-color: #2A2A2A;
            }
            QTreeView::item:selected {
                background-color: #2196F3;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #404040;
                padding: 5px;
            }
            QProgressBar {
                background-color: #2D2D2D;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
            }
            QLabel {
                color: #888888;
                font-size: 11px;
            }
        """)
    
    def show_progress(self, percent: int):
        """显示进度"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percent)
    
    def hide_progress(self):
        """隐藏进度"""
        self.progress_bar.setVisible(False)
