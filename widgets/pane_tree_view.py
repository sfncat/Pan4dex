"""
Pan4dex 万格 — 窗格内嵌目录树
"""
import os
import logging
from PyQt6.QtWidgets import QTreeView, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QAbstractItemView
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QModelIndex, QTimer
from PyQt6.QtGui import QFileSystemModel

logger = logging.getLogger("pan4dex.pane_tree_view")


class PaneTreeView(QWidget):
    """窗格内嵌目录树"""
    
    folder_clicked = pyqtSignal(str)
    auto_expand = True
    
    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        
        self._pane_ref = None
        p = parent
        while p:
            if hasattr(p, 'current_path'):
                self._pane_ref = p
                break
            p = p.parent()
        
        # 延迟启动标志：树隐藏时不扫描磁盘，首次显示/展开时才 setRootPath，
        # 避免四窗格 4 个模型同时全盘扫描（含网络盘）拖慢目录加载
        self._model_started = False
        
        # 实例属性：每个目录树独立的展开状态（避免多窗格互相覆盖导致展开链断裂）
        self._pending_path = None
        self._pending_idx = 0
        self._expand_queue = []
        self._expand_done = False
        self._stable_timer = None
        
        self.setMinimumWidth(180)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 工具栏
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(1)
        
        self.follow_btn = QPushButton("📍")
        self.follow_btn.setFixedSize(32, 20)
        self.follow_btn.setToolTip("📍 跟随当前目录")
        self.follow_btn.clicked.connect(self.on_follow_clicked)
        self.toolbar.addWidget(self.follow_btn)
        
        self.toolbar.addStretch()
        
        self.auto_chk = QCheckBox("自动")
        self.auto_chk.setChecked(True)
        self.auto_chk.toggled.connect(self._toggled_auto)
        self.toolbar.addWidget(self.auto_chk)
        
        self.main_layout.addLayout(self.toolbar)
        
        # 树视图
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        # 注意：不能开启视图排序（setSortingEnabled(True)）——
        # QFileSystemModel 自身按名称排序，显示顺序不受影响；
        # 而视图排序 + 四窗格共享同一模型时，scrollTo 会触发 Qt 崩溃/失效
        self.tree_view.setSortingEnabled(False)
        self.tree_view.setItemsExpandable(True)
        self.tree_view.doubleClicked.connect(self.on_item_clicked)
        self.main_layout.addWidget(self.tree_view)
        
        self.init_model()
        logger.info("[DEBUG] PaneTreeView init done")
    
    def _toggled_auto(self, checked):
        self.auto_expand = checked
    
    def init_model(self):
        self.model = QFileSystemModel()
        # 不立即 setRootPath：延迟到首次显示/展开时（见 _ensure_model_started）
        self.model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot
        )
        self.model.directoryLoaded.connect(self._on_directory_loaded)
        # 目录加载过程中行持续插入（树高度不断变化）：
        # 每次插入后都重新把当前目录滚到正中，直到树稳定
        self.model.rowsInserted.connect(self._on_rows_inserted)
        self.tree_view.setModel(self.model)
        self.tree_view.setColumnHidden(1, True)
        self.tree_view.setColumnHidden(2, True)
        self.tree_view.setColumnHidden(3, True)
        root_index = self.model.index("")
        self.tree_view.setRootIndex(root_index)
    
    def _schedule_expand(self, msec: int, fn):
        """延迟执行展开回调。定时器挂在本控件下，控件销毁时自动取消，避免回调访问已删除对象。"""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: (fn(), timer.deleteLater()))
        timer.start(msec)

    def _on_directory_loaded(self, path):
        # 目录加载完成：只推进当前挂起的那一步（不从头重来，避免展开序列被反复重置）
        if self._pending_path and path == self._pending_path:
            self._pending_path = None
            idx = self._pending_idx
            parts = self._expand_queue
            self._schedule_expand(30, lambda: self._expand_parts(parts, idx))
    
    def on_item_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.folder_clicked.emit(path)
    
    def on_follow_clicked(self):
        pane = self._pane_ref
        if pane and hasattr(pane, 'current_path'):
            path = pane.current_path
            logger.info(f"[DEBUG] PaneTreeView.follow: path={path}")
            self.expand_to_path(path)
    
    def _ensure_model_started(self):
        """首次使用时才启动磁盘扫描（树隐藏时不扫描，加快启动）"""
        if not self._model_started:
            self.model.setRootPath("")
            self._model_started = True

    def expand_to_path(self, path: str):
        if not path or not os.path.isdir(path):
            return
        self._ensure_model_started()
        # 统一为正斜杠：os.path.dirname 会保留用户输入的分隔符，
        # 而 QFileSystemModel 的 directoryLoaded 信号/索引统一用正斜杠，
        # 不归一化会导致"父目录加载完成"信号永远匹配不上，展开链卡死
        path = path.replace("\\", "/")
        parts = []
        current = path
        while current and current != os.path.dirname(current):
            parts.append(current)
            current = os.path.dirname(current)
        parts.reverse()
        logger.info(f"[DEBUG] PaneTreeView.expand: parts={parts}")
        self._expand_queue = parts
        self._pending_path = None
        self._expand_done = False
        self._expand_parts(parts, 0)
    
    def _on_rows_inserted(self, *args):
        """目录加载/展开使树高度变化后，把当前目录重新滚到正中。

        只处理展开已完成的树（目标索引此时才有效）；
        直接 scrollTo，不排队列延迟，避免高频插入时 timer 堆积。
        """
        if self._expand_done and self._expand_queue:
            # 行还在插入（树高度未稳定）：重置稳定定时器，稍后再居中
            self._restart_stable_scroll()

    def _expand_parts(self, parts: list, idx: int):
        if idx >= len(parts):
            leaf_path = parts[-1]
            leaf = self.model.index(leaf_path)
            if leaf.isValid():
                self._expand_done = True
                self.tree_view.setCurrentIndex(leaf)
                # 滚动到目录树上下居中的位置
                self._scroll_to_center(leaf_path)
            return
        p = parts[idx]
        index = self.model.index(p)
        if index.isValid():
            self.tree_view.expand(index)
            # 立即推进下一步；子目录尚未加载时，下一步会自行挂起等待加载信号
            self._schedule_expand(60, lambda: self._expand_parts(parts, idx + 1))
        else:
            # 该级目录尚未被模型加载（父目录还在异步扫描）：挂起，等父目录加载完成
            self._pending_path = os.path.dirname(p)
            self._pending_idx = idx
            # 兜底：加载信号未触发（或已错过）时重试本步，确保最终推进
            self._schedule_expand(800, lambda: self._expand_parts(parts, idx))

    def _scroll_to_center(self, path: str):
        """滚动到树上下居中的位置。

        QFileSystemModel 异步加载，目录展开后树高度还会继续增长，
        只滚动一次会导致当前目录掉出可视范围。因此按路径多次延迟重定位
        （每次重新取索引，避免旧索引失效），直到树高度稳定，
        最终当前目录保持在可视范围正中。
        """
        index = self.model.index(path)
        if not index.isValid():
            return
        self.tree_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        # 目录树模型异步加载：滚动目标行的"视图行"可能在加载过程中尚未布局。
        # 轮询重试（每 300ms 一次，持续 4.5s）——每次 scrollTo 都会触发视图布局，
        # 行就绪后自然收敛到正中；rowsInserted 的稳定定时器负责加载结束后的收尾
        for i in range(1, 16):
            self._schedule_expand(300 * i, lambda: self._do_scroll(path))
        self._restart_stable_scroll()

    def _do_scroll(self, path: str):
        idx = self.model.index(path)
        if idx.isValid():
            self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _restart_stable_scroll(self):
        """重启"加载静默"定时器：目录加载持续插入行时会不断重置，
        直到 1.2s 内没有新行插入（树高度稳定）才执行最终居中。
        """
        if self._stable_timer is not None:
            self._stable_timer.stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_stable_timeout)
        timer.start(800)
        self._stable_timer = timer

    def _on_stable_timeout(self):
        self._stable_timer = None
        if self._expand_done and self._expand_queue:
            # 无条件居中（推算 rect 时 scrollTo 会触发 Qt 内部布局重算）
            self._do_scroll(self._expand_queue[-1])
