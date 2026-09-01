"""
Pan4dex 万格 — 目录树侧边栏
"""
import os
import logging
from PyQt6.QtWidgets import (
    QDockWidget, QTreeView, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QCheckBox, QHeaderView
)
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QModelIndex, QTimer
from PyQt6.QtGui import QFileSystemModel

logger = logging.getLogger("pan4dex.tree_sidebar")


class TreeSidebar(QDockWidget):
    """目录树侧边栏"""
    
    folder_clicked = pyqtSignal(str)
    auto_expand = True
    
    _pending_path = None
    _expand_queue = []
    
    def __init__(self, parent=None):
        super().__init__("目录树", parent)
        self._main_window_ref = parent
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | 
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(250)
        self.init_ui()
        self.init_model()
    
    def init_ui(self):
        self.main_widget = QWidget()
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        
        # 工具栏 - 使用紧凑按钮
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(1)
        
        self.expand_btn = QPushButton("+")
        self.expand_btn.setFixedSize(24, 20)
        self.expand_btn.setToolTip("展开所有")
        self.expand_btn.clicked.connect(self.expand_all)
        self.toolbar.addWidget(self.expand_btn)
        
        self.collapse_btn = QPushButton("-")
        self.collapse_btn.setFixedSize(24, 20)
        self.collapse_btn.setToolTip("折叠所有")
        self.collapse_btn.clicked.connect(self.collapse_all)
        self.toolbar.addWidget(self.collapse_btn)
        
        self.follow_btn = QPushButton("📍")
        self.follow_btn.setFixedSize(32, 20)
        self.follow_btn.setToolTip("📍 跟随当前目录")
        self.follow_btn.clicked.connect(self.on_follow_clicked)
        self.toolbar.addWidget(self.follow_btn)
        
        self.toolbar.addStretch()
        
        # 自动展开放在右侧
        self.auto_chk = QCheckBox("自动")
        self.auto_chk.setChecked(True)
        self.auto_chk.toggled.connect(self._toggled_auto)
        self.toolbar.addWidget(self.auto_chk)
        
        self.layout.addLayout(self.toolbar)
        
        # 树视图
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(True)
        self.tree_view.doubleClicked.connect(self.on_item_clicked)
        self.layout.addWidget(self.tree_view)
        
        self.setWidget(self.main_widget)
        logger.info("[DEBUG] TreeSidebar init_ui done, buttons: + - 📍 自动")
    
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
    
    def _on_directory_loaded(self, path):
        if self._pending_path:
            parts = getattr(self, '_expand_queue', [])
            if parts and self._pending_path in parts:
                QTimer.singleShot(50, lambda: self._expand_parts(parts, 0))
            self._pending_path = None
    
    def on_item_clicked(self, index: QModelIndex):
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.folder_clicked.emit(path)
    
    def on_follow_clicked(self):
        mw = self._main_window_ref
        if mw and hasattr(mw, '_active_pane') and mw._active_pane:
            path = mw._active_pane.current_path
            logger.info(f"[DEBUG] TreeSidebar.follow: path={path}")
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
        logger.info(f"[DEBUG] expand: parts={parts}")
        self._expand_queue = parts
        self._expand_parts(parts, 0)
    
    def _expand_parts(self, parts: list, idx: int):
        if idx >= len(parts):
            leaf = self.model.index(parts[-1])
            if leaf.isValid():
                self.tree_view.setCurrentIndex(leaf)
                self.tree_view.scrollTo(leaf)
            return
        p = parts[idx]
        index = self.model.index(p)
        if index.isValid():
            self.tree_view.expand(index)
            QTimer.singleShot(100, lambda: self._expand_parts(parts, idx + 1))
        else:
            self._pending_path = p
            QTimer.singleShot(300, lambda: self._expand_parts(parts, idx))
    
    def expand_all(self):
        self.tree_view.expandAll()
    
    def collapse_all(self):
        self.tree_view.collapseAll()
