"""
Pan4dex 万格 — 窗格内嵌目录树
"""
import os
from PyQt6.QtWidgets import QTreeView, QWidget, QVBoxLayout
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

    def expand_to_path(self, path: str):
        """展开到指定路径"""
        if os.path.isdir(path):
            index = self.model.index(path)
            self.tree_view.expand(index)
            self.tree_view.setCurrentIndex(index)
