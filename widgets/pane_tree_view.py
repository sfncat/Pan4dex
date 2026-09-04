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
    
    _pending_path = None
    _expand_queue = []
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._pane_ref = None
        p = parent
        while p:
            if hasattr(p, 'current_path'):
                self._pane_ref = p
                break
            p = p.parent()
        
        self.setMinimumWidth(180)
        self.setMaximumWidth(300)
        
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
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(True)
        self.tree_view.doubleClicked.connect(self.on_item_clicked)
        self.main_layout.addWidget(self.tree_view)
        
        self.init_model()
        logger.info("[DEBUG] PaneTreeView init done")
    
    def _toggled_auto(self, checked):
        self.auto_expand = checked
    
    def init_model(self):
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot
        )
        self.model.directoryLoaded.connect(self._on_directory_loaded)
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
        if self._pending_path:
            parts = getattr(self, '_expand_queue', [])
            if parts and self._pending_path in parts:
                self._schedule_expand(50, lambda: self._expand_parts(parts, 0))
            self._pending_path = None
    
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
    
    def expand_to_path(self, path: str):
        if not path or not os.path.isdir(path):
            return
        parts = []
        current = path
        while current and current != os.path.dirname(current):
            parts.append(current)
            current = os.path.dirname(current)
        parts.reverse()
        logger.info(f"[DEBUG] PaneTreeView.expand: parts={parts}")
        self._expand_queue = parts
        self._expand_parts(parts, 0)
    
    def _expand_parts(self, parts: list, idx: int):
        if idx >= len(parts):
            leaf = self.model.index(parts[-1])
            if leaf.isValid():
                self.tree_view.setCurrentIndex(leaf)
                # 滚动到目录树上下居中的位置，而不是只保证可见
                self.tree_view.scrollTo(leaf, QAbstractItemView.ScrollHint.PositionAtCenter)
            return
        p = parts[idx]
        index = self.model.index(p)
        if index.isValid():
            self.tree_view.expand(index)
            self._schedule_expand(100, lambda: self._expand_parts(parts, idx + 1))
        else:
            self._pending_path = p
            self._schedule_expand(300, lambda: self._expand_parts(parts, idx))
