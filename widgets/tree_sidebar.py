"""
Pan4dex 万格 — 目录树侧边栏
"""
import os
from PyQt6.QtWidgets import (
    QDockWidget, QTreeView, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QToolButton, QHeaderView
)
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QModelIndex
from PyQt6.QtGui import QFileSystemModel


class TreeSidebar(QDockWidget):
    """目录树侧边栏"""
    
    folder_clicked = pyqtSignal(str)  # 文件夹点击信号
    auto_expand = True  # 是否自动展开
    
    def __init__(self, parent=None):
        super().__init__("目录树", parent)
        
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | 
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(200)
        self.setMaximumWidth(400)
        
        # 创建 UI
        self.init_ui()
        
        # 初始化模型
        self.init_model()
    
    def init_ui(self):
        """初始化 UI"""
        self.main_widget = QWidget()
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        
        # 工具栏
        self.toolbar = QHBoxLayout()
        
        self.expand_btn = QPushButton("展开")
        self.expand_btn.clicked.connect(self.expand_all)
        self.toolbar.addWidget(self.expand_btn)
        
        self.collapse_btn = QPushButton("折叠")
        self.collapse_btn.clicked.connect(self.collapse_all)
        self.toolbar.addWidget(self.collapse_btn)
        
        self.auto_expand_btn = QPushButton("自动展开: 开")
        self.auto_expand_btn.setCheckable(True)
        self.auto_expand_btn.setChecked(True)
        self.auto_expand_btn.clicked.connect(self.toggle_auto_expand)
        self.toolbar.addWidget(self.auto_expand_btn)
        
        # 跟随当前位置按钮
        self.follow_btn = QPushButton("📍 跟随")
        self.follow_btn.setToolTip("展开目录树到当前窗格所在目录")
        self.follow_btn.clicked.connect(self.on_follow_clicked)
        self.toolbar.addWidget(self.follow_btn)
        
        self.toolbar.addStretch()
        
        self.layout.addLayout(self.toolbar)
        
        # 树视图
        self.tree_view = QTreeView()
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(True)
        self.tree_view.setAllColumnsShowFocus(True)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.doubleClicked.connect(self.on_item_clicked)
        self.tree_view.expanded.connect(self.on_item_expanded)
        self.tree_view.collapsed.connect(self.on_item_collapsed)
        
        self.layout.addWidget(self.tree_view)
        
        self.setWidget(self.main_widget)
        
        # 样式
    
    def init_model(self):
        """初始化文件系统模型"""
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.setFilter(
            QDir.Filter.AllDirs | 
            QDir.Filter.NoDotAndDotDot |
            QDir.Filter.Hidden
        )
        
        self.tree_view.setModel(self.model)
        
        # 隐藏除名称外的所有列
        self.tree_view.setColumnHidden(1, True)  # 大小
        self.tree_view.setColumnHidden(2, True)  # 类型
        self.tree_view.setColumnHidden(3, True)  # 修改时间
        
        # 设置根目录
        root_index = self.model.index(QDir.homePath())
        self.tree_view.setRootIndex(root_index)
    
    def set_root_path(self, path: str):
        """设置根目录"""
        if os.path.isdir(path):
            root_index = self.model.index(path)
            self.tree_view.setRootIndex(root_index)
    
    def on_item_clicked(self, index: QModelIndex):
        """项目点击"""
        path = self.model.filePath(index)
        if os.path.isdir(path):
            self.folder_clicked.emit(path)
    
    def on_item_expanded(self, index: QModelIndex):
        """项目展开"""
        pass
    
    def on_item_collapsed(self, index: QModelIndex):
        """项目折叠"""
        pass
    
    def on_follow_clicked(self):
        """跟随当前位置按钮点击"""
        # 从 MainWindow 获取当前活动窗格的路径
        main_window = self.parent()
        if main_window and hasattr(main_window, '_active_pane') and main_window._active_pane:
            path = main_window._active_pane.current_path
            self.expand_to_path_recursive(path)
    
    def expand_to_path_recursive(self, path: str):
        """递归展开到指定路径（展开所有父级）"""
        if not os.path.isdir(path):
            return
        
        # 从根路径开始，逐级展开
        parts = []
        current = path
        while current and current != os.path.dirname(current):
            parts.append(current)
            current = os.path.dirname(current)
        
        # 从根到叶逐级展开
        for p in reversed(parts):
            index = self.model.index(p)
            if index.isValid():
                self.tree_view.expand(index)
        
        # 设置当前选中项
        leaf_index = self.model.index(path)
        if leaf_index.isValid():
            self.tree_view.setCurrentIndex(leaf_index)
    
    def expand_all(self):
        """展开所有"""
        self.tree_view.expandAll()
    
    def collapse_all(self):
        """折叠所有"""
        self.tree_view.collapseAll()
    
    def toggle_auto_expand(self):
        """切换自动展开"""
        self.auto_expand = not self.auto_expand
        self.auto_expand_btn.setText(f"自动展开: {'开' if self.auto_expand else '关'}")
    
    def expand_to_path(self, path: str):
        """递归展开到指定路径（展开所有父级）"""
        if os.path.isdir(path):
            # 从根路径开始，逐级展开
            parts = []
            current = path
            while current and current != os.path.dirname(current):
                parts.append(current)
                current = os.path.dirname(current)
            
            # 从根到叶逐级展开
            for p in reversed(parts):
                index = self.model.index(p)
                if index.isValid():
                    self.tree_view.expand(index)
            
            # 设置当前选中项
            leaf_index = self.model.index(path)
            if leaf_index.isValid():
                self.tree_view.setCurrentIndex(leaf_index)
