"""
Pan4dex 万格 — 窗格内嵌目录树
"""
import os
from PyQt6.QtWidgets import QTreeView, QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QModelIndex
from PyQt6.QtGui import QFileSystemModel


class PaneTreeView(QWidget):
    """窗格内嵌目录树 - 每个窗格左侧的独立目录树"""
    
    folder_clicked = pyqtSignal(str)  # 文件夹点击信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setMinimumWidth(150)
        self.setMaximumWidth(300)
        
        # 布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 工具栏
        self.toolbar = QHBoxLayout()
        
        # 跟随当前位置按钮
        self.follow_btn = QPushButton("📍 跟随")
        self.follow_btn.setToolTip("展开目录树到当前目录")
        self.follow_btn.clicked.connect(self.on_follow_clicked)
        self.toolbar.addWidget(self.follow_btn)
        
        self.toolbar.addStretch()
        self.main_layout.addLayout(self.toolbar)
        
        # 树视图
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(True)
        self.tree_view.setAllColumnsShowFocus(True)
        self.tree_view.doubleClicked.connect(self.on_item_clicked)
        
        self.main_layout.addWidget(self.tree_view)
        
        # 模型
        self.init_model()
        
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
    
    def on_follow_clicked(self):
        """跟随当前位置按钮点击"""
        # 从父级 Pane 获取当前路径
        pane = self.parent()
        while pane and not hasattr(pane, 'current_path'):
            pane = pane.parent()
        
        if pane and hasattr(pane, 'current_path'):
            self.expand_to_path_recursive(pane.current_path)
    
    def expand_to_path_recursive(self, path: str):
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
    
    def expand_to_path(self, path: str):
        """递归展开到指定路径（展开所有父级）"""
        self.expand_to_path_recursive(path)
