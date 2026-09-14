"""
Pan4dex 万格 — 单窗格组件
"""
import logging

logger = logging.getLogger("pan4dex.pane")
from PyQt6.QtGui import QFileSystemModel, QAction, QKeySequence, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QProgressBar,
    QLabel, QMenu, QMessageBox, QInputDialog, QLineEdit, QHBoxLayout, QTabWidget,
    QApplication, QSplitter, QDialog, QTableWidget, QHeaderView, QPushButton
)
from PyQt6.QtCore import Qt, QDir, QMimeData, pyqtSignal, pyqtSlot, QThread, QPoint, QEvent, QSortFilterProxyModel, QModelIndex, QPersistentModelIndex, QUrl, QByteArray, QMetaObject, Q_ARG
import os
import sys

from widgets.path_bar import PathBar
from widgets.pane_tree_view import PaneTreeView
from core.file_operations import FileOperations, FileOperationType, FileOperationResult, _is_network_path
from core import archive_ops


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


class FileListTreeView(QTreeView):
    """文件列表树视图：拖放事件统一委托给 Pane 的自定义逻辑。

    QTreeView 内部拖放（DragDrop 模式）走 Qt 自带路径，对 UNC/自定义
    MIME/同窗格移动语义不可控，因此禁用它，由本类把事件转发给 Pane。
    """

    def __init__(self, pane):
        super().__init__()
        self._pane = pane

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pane.drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._pane._start_drag_from_mouse(event.position().toPoint()):
                return
        super().mouseMoveEvent(event)

    # 以下拖放虚函数由 QAbstractItemView 内部路由调用（DragDrop 模式），
    # 均不调用 super()，阻止 Qt 内置 model.dropMimeData 路径，转交 Pane 逻辑。
    def dragEnterEvent(self, event):
        self._pane.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasFormat("application/x-pan4dex-drag"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._pane._apply_drag_highlight(False)
        event.accept()

    def dropEvent(self, event):
        self._pane.dropEvent(event)

    def keyPressEvent(self, event):
        # Shift+Delete 永久删除（Windows 习惯）；普通 Delete 不在此拦截，
        # 仍由主窗口 QAction(Delete) → delete_selected 走回收站路径，
        # 避免两条入口同时触发弹两次确认框
        if event.key() == Qt.Key.Key_Delete and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            paths = self._pane._paths_from_selection()
            if paths:
                self._pane._delete_paths(paths, permanent=True)
            return
        super().keyPressEvent(event)


class Pane(QWidget):
    """单个窗格组件"""
    
    # 所有窗格实例（weakref，用于重建共享文件模型时统一刷新）
    _instances = None  # 延迟初始化 weakref.WeakSet
    
    # 信号
    path_changed = pyqtSignal(str)  # 路径变更信号
    activated = pyqtSignal(object)  # 窗格被激活信号
    shot_dates_ready = pyqtSignal()  # 后台 prefetch 拍摄日期完成（跨线程安全，自动投递主线程）
    _archive_done = pyqtSignal(bool, str, str)  # 压缩/解压完成(ok, message, note)；跨线程 emit 自动投递主线程
    _file_progress = pyqtSignal(int, str, int, int)  # 文件操作进度(percent, filename, copied_bytes, total_bytes)；worker 线程 emit 自动投递主线程
    _file_op_done = pyqtSignal(object, str, object)  # 文件操作完成(result, note, done_handler)；worker 线程 emit 自动投递主线程
    
    def __init__(self, pane_id: str, parent=None, start_path: str = None):
        super().__init__(parent)
        
        import weakref
        if Pane._instances is None:
            Pane._instances = weakref.WeakSet()
        Pane._instances.add(self)
        
        self.pane_id = pane_id
        # 默认打开目录：设置了有效目录用之，否则用户目录
        if start_path and os.path.isdir(start_path):
            self.current_path = start_path
        else:
            self.current_path = QDir.homePath()
        self.file_ops = FileOperations()
        # 第二阶段双轨开关：True 时本窗格文件列表用自研异步模型 DirStoreModel
        from config.app_config import use_new_model
        self._use_new_model = use_new_model()
        # 同名冲突记忆策略（“对后续冲突执行相同操作”，仅本次操作内有效）
        self._conflict_policy = None
        self._file_progress.connect(self._on_file_progress_ui)
        self._file_op_done.connect(self._on_file_op_done)
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
        self._archive_done.connect(self._on_archive_done)

        # 路径栏
        self.path_bar = PathBar()
        logger.info(f"[启动计时] PathBar 创建: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.path_bar.path_entered.connect(self.on_path_entered)
        self.path_bar.back_requested.connect(self.go_back)
        self.path_bar.forward_requested.connect(self.go_forward)
        self.path_bar.refresh_requested.connect(self.refresh_current)
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
        # 目录树右键：与文件列表右键菜单一致
        self.pane_tree_view.tree_view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.pane_tree_view.tree_view.customContextMenuRequested.connect(
            self.show_tree_context_menu)
        self.h_container.addWidget(self.pane_tree_view)

        # 文件列表容器
        self.file_list_widget = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_widget)
        self.file_list_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list_layout.setSpacing(0)

        # 文件列表
        self.tree_view = FileListTreeView(self)
        # 拖拽（setDragDropMode 会隐式改成 SingleSelection）之后必须显式
        # 恢复多选：支持 Shift/Ctrl 连续多选
        from PyQt6.QtWidgets import QAbstractItemView
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_view.setRootIsDecorated(False)
        self.tree_view.setAlternatingRowColors(False)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(False)
        self.tree_view.setAllColumnsShowFocus(True)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        # Enter 打开（Windows 习惯：Enter 等价于双击）：QTreeView 对 Enter 只发
        # activated 不发 doubleClicked，旧版未连接导致 Enter 无反应；
        # Ctrl+Enter 是 Qt 内建的“打开持续编辑器”，不劫持
        self.tree_view.activated.connect(self._on_item_activated)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        # 列标题右键：弹出列选择菜单，不触发窗格右键菜单
        self.tree_view.header().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.header().customContextMenuRequested.connect(self.show_column_menu)
        self.tree_view.viewport().installEventFilter(self)

        # 拖拽支持：保持 DragDrop 框架让 Qt 把 drop 事件投递到 viewport（内部路由
        # 会调用 FileListTreeView 的拖放虚函数），但子类重写不调用 super()，
        # 阻止 Qt 内置 model.dropMimeData 路径，全部转交 Pane 的统一处理逻辑
        self.tree_view.setDragDropMode(QTreeView.DragDropMode.DragDrop)
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)

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
    
    @classmethod
    def _file_filter(cls):
        """根据“显示隐藏文件”开关构造 QDir.Filter（默认显示，保持旧行为）"""
        base = (QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        if getattr(cls, '_show_hidden', True):
            base |= QDir.Filter.Hidden
        return base

    @classmethod
    def set_show_hidden(cls, show: bool):
        """全局切换隐藏文件过滤（所有窗格同步生效）。

        旧共享模型：直接改共享模型 filter。新模型（DirStoreModel）：
        逐窗格设自己的模型 filter 并重扫。
        """
        Pane._show_hidden = bool(show)
        filt = cls._file_filter()
        model = getattr(Pane, '_shared_file_model', None)
        if model is not None:
            model.setFilter(filt)
        for pane in list(getattr(cls, '_instances', None) or ()):
            if getattr(pane, '_use_new_model', False) and pane.model is not None:
                try:
                    pane.model.setFilter(filt)
                    pane.model.refresh()
                except RuntimeError:
                    pass  # 窗格已销毁

    def _setup_shared_model(self):
        """设置文件列表模型：新模型开关开则每窗格独立 DirStoreModel，
        否则沿用共享 ExifFileSystemModel。"""
        if getattr(self, '_use_new_model', False):
            self._setup_dir_store_model()
            return
        # 使用静态共享模型，避免每个窗格都创建
        if not hasattr(Pane, '_shared_file_model') or Pane._shared_file_model is None:
            import time
            t0 = time.perf_counter()
            model = ExifFileSystemModel()
            model.setRootPath("")
            model.setFilter(self._file_filter())
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

    def _setup_dir_store_model(self):
        """第二阶段：为本窗格创建独立的异步 DirStoreModel（不共享）。

        目录枚举在后台线程完成、主线程零阻塞；每个窗格一个模型，
        便于按窗格独立回退与定向刷新。排序仍由每窗格独立的
        PaneSortProxyModel 负责（与旧路径一致的视图/代理结构）。
        """
        from core.dir_model import DirStoreModel
        import time
        t0 = time.perf_counter()
        model = DirStoreModel()
        model.setFilter(self._file_filter())
        self.model = model
        self.sort_proxy = PaneSortProxyModel(self)
        self.sort_proxy.setSourceModel(model)
        self.tree_view.setModel(self.sort_proxy)
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[启动计时] DirStoreModel 创建（窗格 {self.pane_id}）: {elapsed:.1f}ms")

        # 恢复列显示状态（拍摄日期列默认隐藏；用户勾选后持久化）
        self._restore_column_visibility()

        # 后台 prefetch 完成后刷新视图
        self.shot_dates_ready.connect(self._refresh_shot_date_column)
        # 目录异步加载完成后，若正好是当前目录则预读拍摄日期
        model.directoryLoaded.connect(self._on_directory_loaded_shot_dates)

        # 设置根索引
        self._set_root_index(self.current_path)

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
        if getattr(self, '_use_new_model', False):
            # 新模型：把 path 设为唯一顶层节点（触发异步加载），返回可映射的顶层索引
            source_index = self.model.set_directory(path)
        else:
            source_index = self.model.index(path)
        if source_index.isValid():
            proxy_index = self.sort_proxy.mapFromSource(source_index)
            if proxy_index.isValid():
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

        性能：拍摄日期列默认隐藏，而主线程枚举整表 + 拉起 exiftool 子进程
        在 SMB 上代价极高。故仅在该列真正可见时才预读；列隐藏时直接返回。
        """
        try:
            shot_col = getattr(self.model, 'SHOT_DATE_COLUMN', 4)
            if self.tree_view.isColumnHidden(shot_col):
                return
        except Exception:
            pass
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

    def _path_is_dir(self, path: str) -> bool:
        """判断路径是否为目录，优先利用共享模型已加载的缓存（内存查询，
        零 syscall），避免每次导航都对网络路径做同步 stat。

        - 本地路径：直接 os.path.isdir（本地 stat 极快）
        - 网络路径：先查模型（已加载则 isDir 不额外往返）；未加载时
          回退一次 os.path.isdir 保证正确性（不误入文件）
        """
        if not _is_network_path(path):
            return os.path.isdir(path)
        try:
            idx = self.model.index(path)
            if idx.isValid():
                # isValid 不代表已填充；rowCount 为 0 且未加载时不能断定是目录，
                # 用 fileInfo 的缓存属性（QFileSystemModel 拉到条目后不额外 syscall）
                return self.model.isDir(idx)
        except Exception:
            pass
        return os.path.isdir(path)

    def navigate_to(self, path: str):
        """导航到指定路径"""
        import os
        if self._path_is_dir(path):
            # 网络路径（UNC/映射网络驱动器）下 QFileSystemModel 缓存同一目录
            # 不重扫：外部程序（如其它文件管理器）复制/删除的文件看不到，
            # 且 QFileSystemWatcher 在 SMB 上变更通知不可靠，重建共享模型强制重扫
            if path == self.current_path and _is_network_path(path):
                self._force_refresh_current_dir()
                # 超大图标模式下同步刷新缩略图视图（重建模型不自动触发）
                if hasattr(self, 'thumbnail_view') and self.thumbnail_view.isVisible():
                    self.thumbnail_view.load_directory(path)
                return
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

            # 更新当前标签页的名称和路径（标签栏隐藏时也更新，
            # 否则隐藏期间导航后标签名与实际目录脱节）
            current_idx = self.pane_tabs.currentIndex()
            if 0 <= current_idx < len(self._pane_tab_paths):
                self._pane_tab_paths[current_idx] = path
                self.pane_tabs.setTabText(current_idx, os.path.basename(path) if os.path.basename(path) else path)

            # 更新导航历史
            if self._nav_history[self._nav_index] != path:
                self._nav_history = self._nav_history[:self._nav_index + 1]
                self._nav_history.append(path)
                self._nav_index = len(self._nav_history) - 1

            self.update_status_bar()
            self.path_changed.emit(path)
            self._sync_nav_buttons()
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
            self._sync_nav_buttons()

    def go_forward(self):
        """前进到下一个目录"""
        if self._nav_index < len(self._nav_history) - 1:
            self._nav_index += 1
            path = self._nav_history[self._nav_index]
            self._navigate_no_history(path)
            self._sync_nav_buttons()

    def _navigate_no_history(self, path: str):
        """导航但不记录历史"""
        import os
        if self._path_is_dir(path):
            if path == self.current_path and _is_network_path(path):
                self._force_refresh_current_dir()
                return
            self.current_path = path
            self.path_bar.set_path(path)
            self._set_root_index(path)

            if self.pane_tree_view.isVisible():
                self.pane_tree_view.expand_to_path(path)

            current_idx = self.pane_tabs.currentIndex()
            if 0 <= current_idx < len(self._pane_tab_paths):
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
        """标签按钮点击：标签栏隐藏→显示；已显示→新建标签页

        早期行为是纯开关（再次点击关闭标签栏），用户习惯"点标签按钮=创建标签"，
        且关闭后容易与其他窗格状态混淆。现改为：点击总是产生"标签"（显示标签栏
        或新建标签页）；关闭标签栏通过标签栏右键菜单「隐藏标签栏」或关闭全部
        标签页完成。
        """
        if not self.pane_tabs.isVisible():
            logger.info(f"[TABS] pane_id={self.pane_id} toggle_tabs: hidden -> show tabs bar")
            self.pane_tabs.setVisible(True)
            self.path_bar.set_tabs_button_checked(True)
        else:
            logger.info(f"[TABS] pane_id={self.pane_id} toggle_tabs: visible -> add tab")
            self.add_pane_tab(self.current_path)

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

        hide_tabs_action = QAction("隐藏标签栏(&H)", self)
        hide_tabs_action.triggered.connect(self.hide_tabs_bar)
        menu.addAction(hide_tabs_action)

        if tab_index >= 0:
            rename_tab_action = QAction("重命名标签页(&R)", self)
            rename_tab_action.triggered.connect(lambda: self._rename_pane_tab(tab_index))
            menu.addAction(rename_tab_action)

            close_tab_action = QAction("关闭标签页(&C)", self)
            close_tab_action.triggered.connect(lambda: self.close_pane_tab(tab_index))
            menu.addAction(close_tab_action)

        menu.exec(QCursor.pos())

    def hide_tabs_bar(self):
        """隐藏标签页栏（标签按钮语义改为创建标签后，关闭走这里/关完自动隐藏）"""
        self.pane_tabs.setVisible(False)
        self.path_bar.set_tabs_button_checked(False)
        logger.info(f"[TABS] pane_id={self.pane_id} hide_tabs_bar")

    def close_pane_tab(self, index):
        """关闭窗格内标签页；关到 0 个时自动隐藏标签栏"""
        if self.pane_tabs.count() <= 0:
            return
        self.pane_tabs.removeTab(index)
        if index < len(self._pane_tab_paths):
            self._pane_tab_paths.pop(index)
        if self.pane_tabs.count() == 0:
            self.hide_tabs_bar()

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
        logger.info(f"[TABS] pane_id={self.pane_id} add_pane_tab path={path}")
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
    
    def _on_item_activated(self, index):
        """Enter/双击同样打开；Ctrl+Enter 保留 Qt 内建行为不处理"""
        if index.isValid() and not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier):
            self.on_item_double_clicked(index)

    def refresh_current(self):
        """刷新当前目录（F5 / 刷新按钮）：网络路径强制重扫，本地走常规导航"""
        self.navigate_to(self.current_path)

    def _sync_nav_buttons(self):
        """后退/前进按钮按历史栈位置置灰"""
        try:
            self.path_bar.set_nav_enabled(
                self._nav_index > 0,
                self._nav_index < len(self._nav_history) - 1)
        except Exception:
            pass

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
        # Linux：可执行文件（有执行权限，或 AppImage 这类明确的可执行程序）
        # 双击直接运行，而不是用 xdg-open 打开
        if sys.platform == "linux" and os.path.isfile(file_path):
            if os.access(file_path, os.X_OK) or self._is_appimage(file_path):
                if self._run_executable(file_path):
                    return
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

    @staticmethod
    def _is_appimage(path: str) -> bool:
        """判断是否为 AppImage：扩展名，或 magic bytes（类型1: AI\\x02 / 类型2: AI\\x01）"""
        if path.lower().endswith(".appimage"):
            return True
        try:
            with open(path, "rb") as f:
                magic = f.read(3)
            return magic in (b"AI\x02", b"AI\x01")
        except OSError:
            return False

    def _run_executable(self, file_path: str) -> bool:
        """直接运行可执行文件（Linux）。

        AppImage 无执行权限时自动 chmod +x（用户意图即运行）；
        启动失败（无 shebang 的普通文件被加了 x 位等）返回 False，由调用方回退。
        """
        import subprocess
        from config.file_associations import _clean_child_env
        if self._is_appimage(file_path) and not os.access(file_path, os.X_OK):
            try:
                os.chmod(file_path, os.stat(file_path).st_mode | 0o111)
                logger.info("AppImage 自动加运行权限: %s", file_path)
            except OSError as e:
                logger.warning("AppImage 自动加运行权限失败 %s: %s", file_path, e)
                return False
        try:
            subprocess.Popen(
                [file_path],
                cwd=os.path.dirname(file_path) or None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=_clean_child_env(),
            )
            logger.info("运行可执行文件: %s", file_path)
            return True
        except OSError as e:
            logger.warning("运行可执行文件失败 %s: %s", file_path, e)
            return False

    def _chmod_add_exec(self, file_path: str):
        """为文件加运行权限（chmod +x）"""
        try:
            os.chmod(file_path, os.stat(file_path).st_mode | 0o111)
            logger.info("加运行权限: %s", file_path)
        except OSError as e:
            QMessageBox.warning(self, "加运行权限", f"无法设置运行权限:\n{e}")
            return
        # 刷新模型让权限列立即更新（QFileSystemModel.refresh 对已存在路径重扫元数据）
        try:
            idx = self.model.index(file_path)
            self.model.refresh(idx)
        except Exception:
            pass
    
    def on_selection_changed(self):
        """选择变化：更新预览 + 状态栏选中计数"""
        indexes = [i for i in self.tree_view.selectedIndexes() if i.column() == 0]
        if indexes:
            path = self.model.filePath(self._map_to_source(indexes[0]))
            main_window = self.window()
            if hasattr(main_window, 'preview_panel') and main_window.preview_panel.isVisible():
                main_window.preview_panel.preview_file(path)
        self._update_selection_status()
    
    def _update_selection_status(self):
        """状态栏追加“已选 N 项”（无选中时回退到目录概要）。

        只显计数不算选中大小：大小需递归遍历，在 SMB 上会阻塞主线程（
        且 QFileSystemModel 不缓存目录大小），异步统计待第二阶段随新模型落地。
        """
        try:
            n = len([i for i in self.tree_view.selectedIndexes() if i.column() == 0])
            base = getattr(self, '_status_summary', '') or ''
            if n:
                self.status_label.setText(f"{base}    已选 {n} 项" if base else f"已选 {n} 项")
            elif base:
                self.status_label.setText(base)
        except Exception:
            pass
    
    def update_status_bar(self):
        """更新状态栏

        旧实现先 os.listdir 再对每个条目 os.path.isfile/isdir 二次 stat，
        在 SMB 上等于双倍网络往返。改用 os.scandir：一次枚举、DirEntry
        自带类型缓存，is_dir() 通常不额外 syscall。结果存为概要基串，
        供选中计数拼接使用。
        """
        try:
            dirs = files = 0
            with os.scandir(self.current_path) as it:
                for entry in it:
                    try:
                        if entry.is_dir():
                            dirs += 1
                        else:
                            files += 1
                    except OSError:
                        files += 1
            self._status_summary = f"{dirs} 个目录, {files} 个文件"
        except PermissionError:
            self._status_summary = "无权限访问"
        except OSError:
            self._status_summary = ""
        self._update_selection_status()
    
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
            paths = self._paths_from_selection()
            single_path = paths[0] if len(paths) == 1 else None
            is_arc = (single_path is not None and os.path.isfile(single_path)
                      and archive_ops.is_archive(single_path))
            
            open_action = QAction("打开(&O)", self)
            open_action.triggered.connect(self.open_selected)
            menu.addAction(open_action)
            
            # 压缩包操作（仅单选压缩包时）
            if is_arc:
                menu.addSeparator()
                open_arc_action = QAction("打开压缩包(&P)", self)
                open_arc_action.triggered.connect(lambda: self.open_archive(single_path))
                menu.addAction(open_arc_action)
                extract_here_action = QAction("解压到当前目录(&X)", self)
                extract_here_action.triggered.connect(
                    lambda: self.extract_to_current(single_path))
                menu.addAction(extract_here_action)
                extract_named_action = QAction("解压到文件目录(&E)", self)
                extract_named_action.triggered.connect(
                    lambda: self.extract_to_named(single_path))
                menu.addAction(extract_named_action)
            
            menu.addSeparator()
            
            # 压缩选中项（目录/多选/单文件）
            compress_action = QAction("压缩文件目录(&Z)", self)
            compress_action.triggered.connect(self.compress_selected)
            menu.addAction(compress_action)
            
            # Linux：可执行文件 - 运行 / 加运行权限
            if sys.platform == "linux" and single_path is not None and os.path.isfile(single_path):
                has_x = os.access(single_path, os.X_OK)
                is_ai = self._is_appimage(single_path)
                menu.addSeparator()
                if has_x or is_ai:
                    run_action = QAction("运行(&R)", self)
                    run_action.triggered.connect(lambda: self._run_executable(single_path))
                    menu.addAction(run_action)
                if not has_x:
                    chmod_action = QAction("加运行权限(&X)", self)
                    chmod_action.triggered.connect(lambda: self._chmod_add_exec(single_path))
                    menu.addAction(chmod_action)
            
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
            
            # 复制选中项绝对路径（到系统剪贴板，多行）
            copy_path_action = QAction("复制文件地址(&A)", self)
            copy_path_action.triggered.connect(lambda: self._copy_paths_to_clipboard(paths))
            menu.addAction(copy_path_action)
            
            # 在系统文件管理器中定位（Windows explorer /select）
            reveal_text = "在资源管理器中显示(&E)" if sys.platform == 'win32' else "在文件管理器中显示(&E)"
            reveal_action = QAction(reveal_text, self)
            reveal_action.triggered.connect(
                lambda: self._reveal_in_file_manager(single_path or self.current_path))
            menu.addAction(reveal_action)
            
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
            
            internal_terminal_action = QAction("在内置终端中打开(&I)", self)
            internal_terminal_action.triggered.connect(self.open_internal_terminal_here)
            menu.addAction(internal_terminal_action)
            
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
    
    def show_tree_context_menu(self, position):
        """目录树右键菜单：与文件列表右键菜单一致"""
        tree_view = self.pane_tree_view.tree_view
        index = tree_view.indexAt(position)
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
        
        if index.isValid():
            path = self.pane_tree_view.model.filePath(index)
            is_arc = os.path.isfile(path) and archive_ops.is_archive(path)
            
            open_action = QAction("打开(&O)", self)
            open_action.triggered.connect(lambda: self._open_path(path))
            menu.addAction(open_action)
            
            # 压缩包操作（右键压缩包时）
            if is_arc:
                menu.addSeparator()
                open_arc_action = QAction("打开压缩包(&P)", self)
                open_arc_action.triggered.connect(lambda: self.open_archive(path))
                menu.addAction(open_arc_action)
                extract_here_action = QAction("解压到当前目录(&X)", self)
                extract_here_action.triggered.connect(
                    lambda: self.extract_to_current(path))
                menu.addAction(extract_here_action)
                extract_named_action = QAction("解压到文件目录(&E)", self)
                extract_named_action.triggered.connect(
                    lambda: self.extract_to_named(path))
                menu.addAction(extract_named_action)
            
            menu.addSeparator()
            
            # 压缩该项
            compress_action = QAction("压缩文件目录(&Z)", self)
            compress_action.triggered.connect(lambda: self.compress_paths([path]))
            menu.addAction(compress_action)
            
            menu.addSeparator()
            
            copy_action = QAction("复制(&C)", self)
            copy_action.triggered.connect(lambda: self._copy_paths([path]))
            menu.addAction(copy_action)
            
            cut_action = QAction("剪切(&X)", self)
            cut_action.triggered.connect(lambda: self._cut_paths([path]))
            menu.addAction(cut_action)
            
            if os.path.isdir(path):
                paste_action = QAction("粘贴(&V)", self)
                paste_action.triggered.connect(lambda: self._paste_to(path))
                menu.addAction(paste_action)
            else:
                paste_action = QAction("粘贴(&V)", self)
                paste_action.triggered.connect(self.paste)
                menu.addAction(paste_action)
            
            menu.addSeparator()
            
            delete_action = QAction("删除(&D)", self)
            delete_action.triggered.connect(lambda: self._delete_paths([path]))
            menu.addAction(delete_action)
            
            rename_action = QAction("重命名(&R)", self)
            rename_action.triggered.connect(lambda: self._rename_path(path))
            menu.addAction(rename_action)
            
            menu.addSeparator()
            
            if os.path.isdir(path):
                add_bookmark_action = QAction("添加到收藏夹(&B)", self)
                add_bookmark_action.triggered.connect(
                    lambda: self.add_to_bookmarks(path)
                )
                menu.addAction(add_bookmark_action)
            
            menu.addSeparator()
            
            internal_terminal_action = QAction("在内置终端中打开(&I)", self)
            internal_terminal_action.triggered.connect(self.open_internal_terminal_here)
            menu.addAction(internal_terminal_action)
            
            terminal_action = QAction("打开终端(&T)", self)
            terminal_action.triggered.connect(self.open_terminal_here)
            menu.addAction(terminal_action)
        else:
            # 空白区域：在当前目录新建/粘贴
            new_folder_action = QAction("新建文件夹(&F)", self)
            new_folder_action.triggered.connect(self.new_folder)
            menu.addAction(new_folder_action)
            
            new_file_action = QAction("新建文件(&N)", self)
            new_file_action.triggered.connect(self.new_file)
            menu.addAction(new_file_action)
            
            menu.addSeparator()
            
            paste_action = QAction("粘贴(&V)", self)
            paste_action.triggered.connect(self.paste)
            menu.addAction(paste_action)
            
            menu.addSeparator()
            
            new_tab_action = QAction("新建标签页(&T)", self)
            new_tab_action.triggered.connect(lambda: self.add_pane_tab())
            menu.addAction(new_tab_action)
            
            menu.addSeparator()
            
            internal_terminal_action = QAction("在内置终端中打开(&I)", self)
            internal_terminal_action.triggered.connect(self.open_internal_terminal_here)
            menu.addAction(internal_terminal_action)
            
            terminal_action = QAction("打开终端(&T)", self)
            terminal_action.triggered.connect(self.open_terminal_here)
            menu.addAction(terminal_action)
        
        menu.exec(QCursor.pos())
    
    # ------------------------------------------------------------------
    # 压缩 / 解压（内置 7-Zip + 系统 7-Zip 优先）
    # ------------------------------------------------------------------
    def open_archive(self, archive_path):
        """打开压缩包：列出内容对话框"""
        entries = archive_ops.list_entries(archive_path)
        if entries is None:
            QMessageBox.warning(self, "打开压缩包",
                                f"无法读取压缩包内容：\n{archive_path}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"压缩包内容 - {os.path.basename(archive_path)}")
        dlg.resize(600, 460)
        lay = QVBoxLayout(dlg)
        table = QTableWidget(len(entries), 2, dlg)
        table.setHorizontalHeaderLabels(["名称", "大小"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, (name, size) in enumerate(entries):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(self._fmt_size(size)))
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(table)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()
    
    def extract_to_current(self, archive):
        """解压到窗格当前目录"""
        self._run_archive_task(
            "正在解压", lambda: archive_ops.extract(archive, self.current_path))
    
    def extract_to_named(self, archive):
        """解压到压缩包所在目录的同名文件夹（解压到文件目录）"""
        base = os.path.basename(archive)
        stem = base
        for ext in ('.tar.gz', '.tar.bz2', '.tar.xz'):
            if base.lower().endswith(ext):
                stem = base[:-len(ext)]
                break
        else:
            stem = os.path.splitext(base)[0]
        dest = os.path.join(os.path.dirname(archive) or '.', stem)
        self._run_archive_task(
            "正在解压", lambda: archive_ops.extract(archive, dest))
    
    def compress_selected(self):
        """压缩选中项（目录/多选/单文件）"""
        self.compress_paths(self._paths_from_selection())
    
    def compress_paths(self, paths):
        """压缩指定路径列表，弹窗确认压缩包名称"""
        if not paths:
            return
        if len(paths) == 1:
            p = paths[0].rstrip(os.sep)
            default_dir = os.path.dirname(p)
            default_name = os.path.basename(p) + '.7z'
        else:
            default_dir = self.current_path
            default_name = 'archive.7z'
        name, ok = QInputDialog.getText(
            self, "压缩文件目录", "压缩包名称:",
            QLineEdit.EchoMode.Normal, default_name)
        if not ok or not name.strip():
            return
        name = name.strip()
        if not os.path.splitext(name)[1]:
            name += '.7z'
        out = os.path.join(default_dir, name)
        if os.path.exists(out):
            QMessageBox.warning(self, "压缩文件目录", f"目标已存在: {out}")
            return
        self._run_archive_task(
            "正在压缩", lambda: archive_ops.compress(out, paths))
    
    def _run_archive_task(self, note, fn):
        """后台线程执行压缩/解压，完成通过信号回主线程"""
        self.status_label.setText(f"{note}...")
        
        def worker():
            try:
                ok, msg = fn()
            except Exception as e:
                ok, msg = False, str(e)
            self._archive_done.emit(ok, msg, note)
        
        import threading
        threading.Thread(target=worker, daemon=True).start()
    
    def _on_archive_done(self, ok, msg, note):
        """压缩/解压完成（主线程）：刷新 + 提示"""
        if ok:
            self.status_label.setText(f"{note}完成: {msg}")
            self.navigate_to(self.current_path)
        else:
            self.status_label.setText("操作失败")
            QMessageBox.warning(self, "操作失败", msg)
    
    @staticmethod
    def _fmt_size(size):
        """字节数格式化为可读字符串"""
        try:
            size = int(size)
        except (TypeError, ValueError):
            return ''
        if size < 1024:
            return f"{size} B"
        for unit in ('KB', 'MB', 'GB', 'TB'):
            size /= 1024.0
            if size < 1024:
                return f"{size:.1f} {unit}"
        return f"{size:.1f} PB"
    
    def open_selected(self):
        """打开选中项"""
        indexes = self.tree_view.selectedIndexes()
        if indexes:
            path = self.model.filePath(self._map_to_source(indexes[0]))
            self._open_path(path)
    
    def _open_path(self, path):
        """按路径打开：目录→导航，文件→关联应用"""
        import os
        if os.path.isdir(path):
            self.navigate_to(path)
        else:
            self.open_file(path)
    
    def _copy_paths_to_clipboard(self, paths):
        """把选中项绝对路径写入系统剪贴板（多行），供外部粘贴"""
        if not paths:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            text = '\n'.join(os.path.normpath(p) for p in paths)
            QApplication.clipboard().setText(text)
            self.status_label.setText(f"已复制 {len(paths)} 个文件地址")
        except Exception:
            pass
    
    def _reveal_in_file_manager(self, path):
        """在系统文件管理器中选中并显示该项"""
        if not path:
            return
        try:
            import subprocess
            norm = os.path.normpath(path)
            if sys.platform == 'win32':
                # os.path.normpath 会去掉 UNC 前缀双斜杠（\\server → \server），
                # explorer 不识别，需还原
                norm = self._win_unc_fix(norm)
                subprocess.Popen(['explorer', '/select,', norm])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', norm])
            else:
                from PyQt6.QtGui import QDesktopServices
                url = QUrl.fromLocalFile(os.path.dirname(norm) if os.path.exists(norm) else norm)
                QDesktopServices.openUrl(url)
        except Exception as e:
            self.status_label.setText(f"无法在文件管理器中显示: {e}")
    
    @staticmethod
    def _win_unc_fix(norm):
        """还原被 normpath 压掉的 UNC 双前导斜杠"""
        p = norm.replace('/', '\\')
        if not p.startswith('\\\\') and p.startswith('\\'):
            p = '\\' + p
        return p
    
    def _paths_from_selection(self) -> list:
        """从文件列表选中项提取路径列表"""
        paths = []
        for index in self.tree_view.selectedIndexes():
            if index.column() == 0:
                paths.append(self.model.filePath(self._map_to_source(index)))
        return paths
    
    def copy_selected(self):
        """复制选中项"""
        self._copy_paths(self._paths_from_selection())
    
    def cut_selected(self):
        """剪切选中项"""
        self._cut_paths(self._paths_from_selection())
    
    def _copy_paths(self, paths):
        """复制指定路径列表到共享剪贴板"""
        global SHARED_CLIPBOARD_ACTION
        if not paths:
            return
        SHARED_CLIPBOARD.clear()
        SHARED_CLIPBOARD.extend(paths)
        SHARED_CLIPBOARD_ACTION = 'copy'
        self._write_system_clipboard(paths, is_cut=False)
        self.status_label.setText(f"已复制 {len(paths)} 个项目")
    
    def _cut_paths(self, paths):
        """剪切指定路径列表到共享剪贴板"""
        global SHARED_CLIPBOARD_ACTION
        if not paths:
            return
        SHARED_CLIPBOARD.clear()
        SHARED_CLIPBOARD.extend(paths)
        SHARED_CLIPBOARD_ACTION = 'cut'
        self._write_system_clipboard(paths, is_cut=True)
        self.status_label.setText(f"已剪切 {len(paths)} 个项目")
    
    def paste(self):
        """粘贴到当前目录（应用内剪贴板优先，其次系统剪贴板）"""
        self._paste_to(self.current_path)

    def _system_clipboard_paths(self) -> tuple:
        """读取系统剪贴板中的文件路径（从系统文件管理器复制/剪切的文件）。

        系统复制进 Pan4dex 时应用内剪贴板为空，文件在系统剪贴板
        （Windows CF_HDROP / Linux text/uri-list，QClipboard 统一为 URLs）。
        只收集存在的本地文件，忽略网页链接等非本地 URL。

        返回 (paths, is_move)：Windows 资源管理器“剪切”会在
        Preferred DropEffect 格式里写 DROPEFFECT_MOVE(2)，不读它就会把
        剪切误判成复制、源文件留在原地（用户以为已移走，属数据问题）。
        Linux 对应 x-special/gnome-copied-files（首行 move/copy）。
        """
        from PyQt6.QtWidgets import QApplication
        mime = QApplication.clipboard().mimeData()
        if mime is None:
            return [], False
        paths = []
        if mime.hasUrls():
            for u in mime.urls():
                if u.isLocalFile():
                    p = u.toLocalFile()
                    if p and os.path.exists(p):
                        paths.append(p)
        # Windows 真实资源管理器复制：Qt 可能只暴露 CF_HDROP 的封装格式
        # （application/x-qt-windows-mime;value="FileNameW"），hasUrls 为 False。
        # 数据为 UTF-16LE、以 \0 分隔的完整路径列表。
        if not paths and sys.platform == "win32":
            raw = mime.data('application/x-qt-windows-mime;value="FileNameW"')
            if raw:
                try:
                    text = bytes(raw).decode("utf-16-le", errors="replace")
                    for p in text.split("\x00"):
                        p = p.strip()
                        if p and os.path.exists(p):
                            paths.append(p)
                except Exception:
                    pass
            # 兜底：单字节版 FileName（ANSI 路径）
            if not paths:
                raw_a = mime.data('application/x-qt-windows-mime;value="FileName"')
                if raw_a:
                    try:
                        text = bytes(raw_a).decode("mbcs", errors="replace")
                        for p in text.split("\x00"):
                            p = p.strip()
                            if p and os.path.exists(p):
                                paths.append(p)
                    except Exception:
                        pass
        return paths, self._clipboard_prefers_move(mime)

    @staticmethod
    def _clipboard_prefers_move(mime) -> bool:
        """判断剪贴板 MIME 数据是否标记为“剪切/移动”。"""
        if mime is None:
            return False
        try:
            if sys.platform == "win32":
                # Preferred DropEffect：DWORD，低位可为 4 或 8 字节，
                # 取前 4 字节小端无符号整数判 DROPEFFECT_MOVE(0x02)
                raw = mime.data('application/x-qt-windows-mime;value="Preferred DropEffect"')
                if not raw or len(bytes(raw)) < 4:
                    return False
                import struct
                val = struct.unpack('<I', bytes(raw)[:4])[0]
                return bool(val & 0x02)
            else:
                raw = mime.data('x-special/gnome-copied-files')
                if raw and bytes(raw).startswith(b'move'):
                    return True
                raw = mime.data('application/x-kde-dropdata-actions')
                if raw:
                    import struct
                    b = bytes(raw)
                    # 格式：默认动作(int) + 可用动作列表(int...)；Private(2) 表示移动
                    if len(b) >= 4 and struct.unpack('<i', b[:4])[0] == 2:
                        return True
                return False
        except Exception:
            return False

    def _write_system_clipboard(self, paths: list, is_cut: bool):
        """把应用内复制/剪切写回系统剪贴板，使资源管理器等外部程序可粘贴。

        失败（剪贴板被占用等）不影响应用内剪贴板，仅放弃外部可见性。
        """
        try:
            from PyQt6.QtWidgets import QApplication
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
            mime.setText('\n'.join(paths))
            if is_cut:
                # Windows：Explorer 读 Preferred DropEffect 显示灰色剪切外观
                # （PyQt6 无 QByteArray.fromRawData，setData 直接收 bytes）
                if sys.platform == "win32":
                    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"',
                                 b'\x02\x00\x00\x00')
                else:
                    mime.setData('x-special/gnome-copied-files', b'move\n' +
                                 '\n'.join(QUrl.fromLocalFile(p).toString() for p in paths).encode())
            QApplication.clipboard().setMimeData(mime)
        except Exception:
            pass

    def _paste_to(self, target_dir):
        """粘贴到指定目录：应用内剪贴板优先，其次系统剪贴板（后台线程执行，不阻塞界面）"""
        global SHARED_CLIPBOARD_ACTION
        
        if SHARED_CLIPBOARD:
            was_cut = (SHARED_CLIPBOARD_ACTION == 'cut')
            src_paths = list(SHARED_CLIPBOARD) if was_cut else []
            # 快照源列表：worker 线程复制期间主线程可能清理剪贴板
            clip_snapshot = list(SHARED_CLIPBOARD)
            if SHARED_CLIPBOARD_ACTION == 'copy':
                self._run_file_op_async(
                    "正在复制",
                    lambda: self.file_ops.copy(clip_snapshot, target_dir),
                    lambda result: self._on_paste_done(result, target_dir, None))
            elif SHARED_CLIPBOARD_ACTION == 'cut':
                self._run_file_op_async(
                    "正在移动",
                    lambda: self.file_ops.move(clip_snapshot, target_dir),
                    lambda result: self._on_paste_done(result, target_dir, src_paths))
            return
        
        # 应用内剪贴板为空：尝试系统剪贴板（从系统文件管理器复制/剪切进来）
        system_paths, system_is_move = self._system_clipboard_paths()
        if system_paths:
            if system_is_move:
                self._run_file_op_async(
                    "正在移动",
                    lambda: self.file_ops.move(list(system_paths), target_dir),
                    lambda result: self._on_system_paste_done(
                        result, target_dir, len(system_paths), system_paths))
            else:
                self._run_file_op_async(
                    "正在复制",
                    lambda: self.file_ops.copy(system_paths, target_dir),
                    lambda result: self._on_system_paste_done(result, target_dir, len(system_paths), None))
            return
    
    def _on_paste_done(self, result, target_dir, src_paths):
        """粘贴完成（应用内剪贴板，主线程）：刷新视图 + 清理剪切剪贴板"""
        global SHARED_CLIPBOARD_ACTION
        if result.success:
            self.status_label.setText("粘贴完成")
            if src_paths is not None:
                # 剪切移动完成：清空应用内剪贴板
                SHARED_CLIPBOARD.clear()
                SHARED_CLIPBOARD_ACTION = None
            self.navigate_to(target_dir)
            if _is_network_path(target_dir):
                self._force_refresh_current_dir()
            elif src_paths:
                # 剪切移动：源目录若为网络路径，源窗格显示残留需一并重扫
                self._refresh_network_sources(src_paths)
        else:
            self.status_label.setText("粘贴失败")
            QMessageBox.warning(self, "粘贴", result.error or "操作失败")
    
    def _on_system_paste_done(self, result, target_dir, count, moved_srcs):
        """系统剪贴板粘贴完成（主线程）。

        moved_srcs 非空说明来自资源管理器的“剪切”：粘贴后源已被移走，
        按 Windows 习惯清空系统剪贴板（再粘贴无意义），并一并刷新源目录
        所在窗格，避免网络路径上源窗格残留已移走的条目。
        """
        if result.success:
            self.status_label.setText(f"已从系统剪贴板粘贴 {count} 个项目")
            if moved_srcs:
                try:
                    from PyQt6.QtWidgets import QApplication
                    QApplication.clipboard().clear()
                except Exception:
                    pass
                self._refresh_network_sources(moved_srcs)
            self.navigate_to(target_dir)
            if _is_network_path(target_dir):
                self._force_refresh_current_dir()
        else:
            self.status_label.setText("粘贴失败")
            QMessageBox.warning(self, "粘贴", result.error or "操作失败")
    
    def _run_file_op_async(self, note, fn, done_handler=None):
        """后台线程执行文件操作（复制/移动/删除）。

        大文件复制不再阻塞主线程；进度经 _file_progress 信号回主线程更新
        状态栏进度条，完成经 _file_op_done 信号回主线程刷新视图。
        同名冲突经 _ask_conflict_slot 回主线程弹框询问（“对后续同样
        处理”记入 _conflict_policy，本次操作剩余冲突不再询问）。
        """
        self.status_label.setText(f"{note}...")
        self.show_progress(0)
        self.file_ops.set_progress_callback(self._on_copy_progress)
        self._conflict_policy = None
        self.file_ops.set_conflict_callback(self._handle_file_conflict)
        # 独立进度对话框（速度/剩余时间/取消）；上一任务遗留的对话框先销毁
        old_dlg = getattr(self, '_op_dlg', None)
        if old_dlg is not None:
            try:
                old_dlg.close()
                old_dlg.deleteLater()
            except Exception:
                pass
        try:
            from widgets.progress_dialog import FileProgressDialog
            self._op_dlg = FileProgressDialog(self, note)
            self._op_dlg.cancel_requested.connect(self.file_ops.cancel)
            self._op_dlg.show()
        except Exception:
            self._op_dlg = None
        def worker():
            try:
                result = fn()
            except Exception as e:
                result = FileOperationResult(
                    success=False, operation=FileOperationType.COPY,
                    source="", error=str(e))
            self._file_op_done.emit(result, note, done_handler)
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _handle_file_conflict(self, info: dict) -> str:
        """冲突回调（后台操作线程调用）：有记忆策略直接用，否则回主线程询问"""
        if self._conflict_policy:
            return self._conflict_policy
        try:
            return QMetaObject.invokeMethod(
                self, "_ask_conflict_slot", Qt.ConnectionType.BlockingQueuedConnection,
                Q_ARG(str, info.get('src', '')), Q_ARG(str, info.get('dst', '')),
                Q_ARG(bool, bool(info.get('is_dir', False))))
        except Exception:
            return 'keep_both'

    @pyqtSlot(str, str, bool, result=str)
    def _ask_conflict_slot(self, src, dst, is_dir):
        """主线程弹冲突对话框，返回决策；勾选“对后续同样处理”则记入策略"""
        try:
            from widgets.conflict_dialog import ConflictDialog
            info = dict(src=src, dst=dst, is_dir=is_dir)
            try:
                info['src_size'] = 0 if is_dir else os.path.getsize(src)
            except OSError:
                info['src_size'] = 0
            try:
                info['src_mtime'] = os.path.getmtime(src)
            except OSError:
                info['src_mtime'] = 0
            try:
                info['dst_size'] = 0 if os.path.isdir(dst) else os.path.getsize(dst)
            except OSError:
                info['dst_size'] = 0
            try:
                info['dst_mtime'] = os.path.getmtime(dst)
            except OSError:
                info['dst_mtime'] = 0
            dlg = ConflictDialog(self, info)
            dlg.exec()
            decision = dlg.chosen
            try:
                if dlg.apply_all.isChecked():
                    self._conflict_policy = decision
            except Exception:
                pass
            return decision
        except Exception:
            return 'keep_both'

    def _on_copy_progress(self, percent: int, filename: str, copied_bytes: int = 0, total_bytes: int = 0):
        """文件操作进度回调（worker 线程调用）：经信号转发主线程更新 UI"""
        self._file_progress.emit(percent, filename, copied_bytes, total_bytes)

    def _on_file_progress_ui(self, percent: int, filename: str, copied_bytes: int, total_bytes: int):
        """进度 UI 更新（主线程）：状态栏 + 进度对话框"""
        self.show_progress(percent)
        if total_bytes > 0:
            self.status_label.setText(
                f"正在复制: {filename} ({self._fmt_size(copied_bytes)}/{self._fmt_size(total_bytes)})")
        else:
            self.status_label.setText(f"正在复制: {filename}")
        dlg = getattr(self, '_op_dlg', None)
        if dlg is not None:
            try:
                dlg.update_progress(percent, filename, copied_bytes, total_bytes)
            except RuntimeError:
                pass  # 对话框已被关闭/销毁

    def _on_file_op_done(self, result, note, handler):
        """文件操作完成（主线程）：清理回调 + 刷新视图"""
        self.file_ops.set_progress_callback(None)
        self.file_ops.set_conflict_callback(None)
        self._conflict_policy = None
        self.hide_progress()
        dlg = getattr(self, '_op_dlg', None)
        self._op_dlg = None
        if dlg is not None:
            try:
                dlg.mark_finished()
                dlg.close()
                dlg.deleteLater()
            except RuntimeError:
                pass
        if handler is not None:
            handler(result)
        elif result.success:
            self.status_label.setText(f"{note}完成")
            self.navigate_to(self.current_path)
        else:
            self.status_label.setText(f"{note}失败")
            QMessageBox.warning(self, note, result.error or "操作失败")

    @staticmethod
    def _fmt_size(n: int) -> str:
        """字节数人性化显示（GB/MB/KB）"""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return "0 B"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024 or unit == "TB":
                return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
            n /= 1024
        return "0 B"
    
    def delete_selected(self):
        """删除选中项"""
        self._delete_paths(self._paths_from_selection())
    
    def _delete_paths(self, paths, permanent: bool = False):
        """删除指定路径列表（带确认）。

        文案按实际后果区分：网络位置（UNC/映射网络盘）没有回收站，
        删除即永久删除不可恢复，不能仍写“到回收站”误导用户；
        permanent=True（Shift+Delete）时本地也直接永久删除。
        """
        if not paths:
            return
        
        names = '\n'.join(os.path.basename(p) or p for p in paths[:5])
        if len(paths) > 5:
            names += f"\n… 等共 {len(paths)} 项"
        
        if permanent:
            title, verb = "确认永久删除", f"确定要永久删除 {len(paths)} 个项目吗？此操作不可恢复！"
        elif os.name == 'nt':
            net_count = sum(1 for p in paths if _is_network_path(p))
            local_count = len(paths) - net_count
            parts = []
            if net_count:
                parts.append(f"网络位置的 {net_count} 个项目将被永久删除、无法恢复（网络位置没有回收站）")
            if local_count:
                parts.append(f"本地的 {local_count} 个项目将移到回收站")
            verb = '，；'.join(parts) + "。"
            title = "确认删除"
        else:
            verb = f"确定要删除 {len(paths)} 个项目吗？"
            title = "确认删除"
        
        reply = QMessageBox.question(
            self, title, f"{verb}\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            safe = not permanent
            self._run_file_op_async(
                "正在删除",
                lambda: self.file_ops.delete(paths, safe=safe),
                lambda result: self._on_delete_done(result))
    
    def _on_delete_done(self, result):
        """删除完成（主线程）"""
        if result.success:
            self.status_label.setText(f"已删除 {result.files_affected} 个项目")
            if result.error:
                # 网络位置回退永久删除等需告知用户的附带结果
                QMessageBox.information(self, "删除完成", result.error)
            self.navigate_to(self.current_path)
            if _is_network_path(self.current_path):
                # SMB 网络共享上 QFileSystemWatcher 变化通知不可靠，
                # 模型不会自动移除已删项，强制重扫当前目录
                self._force_refresh_current_dir()
        else:
            self.status_label.setText("删除失败")
            QMessageBox.warning(self, "删除失败", result.error)
    
    def _force_refresh_current_dir(self):
        """强制刷新当前目录显示。

        旧共享模型（QFileSystemModel）：SMB/UNC 上 QFileSystemWatcher 目录
        变化通知不可靠，只能重建共享模型全量重扫。
        新模型（DirStoreModel）：只需失效并重扫当前目录（异步、不阻塞），
        无需全量重建。
        """
        if getattr(self, '_use_new_model', False):
            try:
                self.model.refresh()
            except Exception:
                pass
            return
        Pane._rebuild_shared_model()

    def _refresh_network_sources(self, paths):
        """移动/剪切后刷新可能残留的源窗格。

        跨窗格移动或剪切粘贴时，文件从源目录消失；若源目录是网络路径
        （UNC/映射网络驱动器），QFileSystemModel 缓存不会自动移除，
        目标窗格的 navigate_to 只重建当前窗格所在模型（实际重建共享模型
        会让所有窗格一并重扫，但仅当目标路径也是网络路径时才触发）。
        这里主动检查源目录：任一源目录是网络路径就重建共享模型，所有
        窗格（含显示源目录的窗格）一并强制重扫。
        """
        try:
            src_dirs = {os.path.normpath(os.path.dirname(p)) for p in (paths or []) if p}
            for d in src_dirs:
                if _is_network_path(d):
                    self._force_refresh_current_dir()
                    return
        except Exception:
            pass
    
    @classmethod
    def _rebuild_shared_model(cls):
        """重建共享 ExifFileSystemModel，并让所有窗格重新绑定、重设根索引。

        仅在 UNC 目录文件操作后调用（本地目录文件监视正常，无需重建）。
        """
        old = getattr(cls, '_shared_file_model', None)
        import time
        t0 = time.perf_counter()
        model = ExifFileSystemModel()
        model.setRootPath("")
        model.setFilter(cls._file_filter())
        cls._shared_file_model = model
        logger.info(f"重建共享文件模型: {((time.perf_counter() - t0) * 1000):.1f}ms")
        for pane in list(cls._instances or ()):
            try:
                pane.model = model
                pane.sort_proxy.setSourceModel(model)
                model.directoryLoaded.connect(pane._on_directory_loaded_shot_dates)
                if pane.current_path:
                    pane._set_root_index(pane.current_path)
            except RuntimeError:
                pass  # 窗格已销毁
        if old is not None:
            old.deleteLater()
    
    def rename_selected(self):
        """重命名选中项"""
        indexes = self.tree_view.selectedIndexes()
        if indexes:
            self._rename_path(self.model.filePath(self._map_to_source(indexes[0])))
    
    def _rename_path(self, path):
        """重命名指定路径"""
        old_name = os.path.basename(path)
        
        new_name, ok = QInputDialog.getText(
            self, "重命名", "新名称:", QLineEdit.EchoMode.Normal, old_name
        )
        
        if ok and new_name and new_name != old_name:
            result = self.file_ops.rename(path, new_name)
            if result.success:
                self.navigate_to(self.current_path)
                if _is_network_path(self.current_path):
                    self._force_refresh_current_dir()
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
                if _is_network_path(self.current_path):
                    self._force_refresh_current_dir()
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
                if _is_network_path(self.current_path):
                    self._force_refresh_current_dir()
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
                # PyInstaller 打包版会注入 LD_LIBRARY_PATH（指向打包目录），
                # 系统终端（gnome-terminal/xterm 等）继承后加载打包目录里的
                # 旧 glib/gtk 库会崩溃/无反应，必须剔除
                from config.file_associations import _clean_child_env
                env = _clean_child_env()
                try:
                    if terminal in ["gnome-terminal", "mate-terminal", "tilix"]:
                        subprocess.Popen([terminal, f"--working-directory={self.current_path}"],
                                         env=env, start_new_session=True)
                    elif terminal == "konsole":
                        subprocess.Popen([terminal, "--workdir", self.current_path],
                                         env=env, start_new_session=True)
                    elif terminal == "xfce4-terminal":
                        subprocess.Popen([terminal, f"--working-directory={self.current_path}"],
                                         env=env, start_new_session=True)
                    elif terminal == "terminator":
                        subprocess.Popen([terminal, f"--working-directory={self.current_path}"],
                                         env=env, start_new_session=True)
                    elif terminal == "alacritty":
                        subprocess.Popen([terminal, "--working-directory", self.current_path],
                                         env=env, start_new_session=True)
                    elif terminal == "kitty":
                        subprocess.Popen([terminal, "--directory", self.current_path],
                                         env=env, start_new_session=True)
                    else:
                        subprocess.Popen([terminal], cwd=self.current_path,
                                         env=env, start_new_session=True)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"启动终端失败: {e}")
            else:
                QMessageBox.warning(self, "错误", "未找到可用的终端")
    
    def open_internal_terminal_here(self):
        """在内置终端面板中打开当前目录"""
        mw = self.window()
        if mw is not None and hasattr(mw, 'open_terminal_at'):
            mw.open_terminal_at(self.current_path)
        else:
            QMessageBox.warning(self, "错误", "内置终端不可用")
    
    def _apply_drag_highlight(self, on: bool):
        """拖拽经过/离开时高亮边框。

        旧实现 dragEnter 用 `self.setStyleSheet(self.styleSheet() + ...)` 累加、
        dragLeave 调 init_ui_style()（内含硬编码 #1E1E1E 深色）恢复——浅色
        主题下拖一次文件进来背景就变黑且累加不可控。改为进入前快照原
        样式、离开时精确还原，不依赖主题、不重复累加。
        """
        if on:
            if getattr(self, '_drag_highlight_on', False):
                return
            self._pre_drag_style = self.styleSheet()
            self._drag_highlight_on = True
            self.setStyleSheet(self._pre_drag_style + "\nQTreeView { border: 2px solid #2196F3; }")
        else:
            if not getattr(self, '_drag_highlight_on', False):
                return
            self._drag_highlight_on = False
            self.setStyleSheet(getattr(self, '_pre_drag_style', '') or '')

    def dragEnterEvent(self, event):
        """拖拽进入"""
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pan4dex-drag"):
            self._apply_drag_highlight(True)
            event.accept()
    
    def dragLeaveEvent(self, event):
        """拖拽离开"""
        self._apply_drag_highlight(False)
        event.accept()
    
    def dropEvent(self, event):
        """拖拽释放。

        - 跨窗格（pan4dex-drag）：按默认动作复制/移动到目标目录
        - 文件拖拽（urls）：拖到目录行则目标为该目录；源在当前目录
          （同窗格拖动）→ 移动，外部拖入 → 复制；
          Ctrl=强制复制，Shift=强制移动
        """
        self._apply_drag_highlight(False)
        target_dir = self.current_path
        pos = event.position().toPoint()
        idx = self.tree_view.indexAt(pos)
        if idx.isValid():
            p = self.model.filePath(self._map_to_source(idx))
            if p and os.path.isdir(p):
                target_dir = p

        # 跨窗格拖拽
        if event.mimeData().hasFormat("application/x-pan4dex-drag"):
            import json
            data = json.loads(event.mimeData().data("application/x-pan4dex-drag").data().decode())
            files = data.get("files", [])
            action = data.get("default_action", "copy")
            # 同窗格拖动 → 移动（与文件拖动语义一致；dragStart 固定写 copy，
            # 跨窗格才按 default_action 复制）
            if data.get("source_pane_id") == self.pane_id:
                action = "move"
            if files:
                if action == "move" and self._move_target_inside_sources(files, target_dir):
                    # 不能把目录移到它自己或它的子目录里（shutil 会递归复制卡死）
                    event.ignore()
                    return
                self._run_file_op_async(
                    "正在移动" if action == "move" else "正在复制",
                    (lambda: self.file_ops.move(files, target_dir)) if action == "move"
                    else (lambda: self.file_ops.copy(files, target_dir)),
                    lambda result: self._on_drop_done(
                        result, target_dir, files if action == "move" else None))
            event.accept()
            return

        # 文件拖拽（本窗格内部拖动 / 外部文件管理器拖入）
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if not files:
            event.ignore()
            return

        src_in_current = all(
            os.path.normpath(os.path.dirname(f)) == os.path.normpath(self.current_path)
            for f in files
        )
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            do_move = False
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            do_move = True
        else:
            # 同窗格拖动（源在当前目录、目标为其他目录）→ 移动；外部拖入 → 复制
            do_move = src_in_current and target_dir != self.current_path

        if src_in_current and target_dir == self.current_path:
            # 拖到自身所在目录：无操作
            event.ignore()
            return

        if do_move and self._move_target_inside_sources(files, target_dir):
            # 不能把目录移到它自己或它的子目录里（shutil 会递归复制卡死）
            event.ignore()
            return

        self._run_file_op_async(
            "正在移动" if do_move else "正在复制",
            (lambda: self.file_ops.move(files, target_dir)) if do_move
            else (lambda: self.file_ops.copy(files, target_dir)),
            lambda result: self._on_drop_done(
                result, target_dir, files if (do_move and not src_in_current) else None))
        event.accept()

    def _on_drop_done(self, result, target_dir, moved_srcs):
        """拖放操作完成（主线程）"""
        if result.success:
            self.status_label.setText("拖放完成")
            self.navigate_to(self.current_path)
            if _is_network_path(target_dir):
                self._force_refresh_current_dir()
            elif moved_srcs:
                # 跨窗格/外部移动：源目录若为网络路径，源窗格残留需重扫
                self._refresh_network_sources(moved_srcs)
        else:
            self.status_label.setText("拖放失败")
            QMessageBox.warning(self, "移动/复制", result.error or "操作失败")
    
    @staticmethod
    def _move_target_inside_sources(files, target_dir):
        """移动目标是否位于任一源目录内部或等于源（防止目录移到自身子目录导致递归复制）"""
        t = os.path.normpath(target_dir)
        for f in files:
            if not os.path.isdir(f):
                continue
            s = os.path.normpath(f)
            if t == s:
                return True
            if t.startswith(s + os.sep) or t.startswith(s + "/"):
                return True
        return False
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 处理拖拽开始（Pane 自身，实际拖拽在 viewport 事件过滤器）"""
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._start_drag_from_mouse(event.position().toPoint()):
                return
        super().mouseMoveEvent(event)
    
    def _start_drag_from_mouse(self, pos) -> bool:
        """从鼠标位置启动拖拽（viewport MouseMove 事件过滤器 / mouseMoveEvent 共用）。

        返回 True 表示已启动拖拽并消费事件。
        """
        if not self.drag_start_pos:
            return False
        
        # 检查是否移动了足够的距离
        if (pos - self.drag_start_pos).manhattanLength() < 10:
            return False
        
        # 获取选中的文件
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return False
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(self._map_to_source(index)))
        
        if not paths:
            return False
        
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
        
        # 执行拖拽（阻塞直到释放）
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        return True
    
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
