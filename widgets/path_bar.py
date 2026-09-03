"""
Pan4dex 万格 — 路径栏组件
"""
import logging
from PyQt6.QtGui import QFileSystemModel, QAction
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QWidget,
    QHBoxLayout, QPushButton, QToolButton, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QSize

logger = logging.getLogger("pan4dex.path_bar")


class PathBar(QWidget):
    """路径栏组件"""
    
    # 类级别的共享 completer 模型（所有 PathBar 实例共享）
    _shared_completer_model = None
    
    # 信号
    path_entered = pyqtSignal(str)  # 路径输入信号
    tree_toggle_requested = pyqtSignal()  # 目录树按钮点击信号
    tabs_toggle_requested = pyqtSignal()  # 标签页按钮点击信号
    terminal_requested = pyqtSignal()  # 终端按钮点击信号
    view_mode_requested = pyqtSignal(str)  # 查看模式切换信号 ('icon' / 'list')
    new_folder_requested = pyqtSignal()  # 新建文件夹按钮点击信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        
        # 后退按钮（默认隐藏，可在设置中显示）
        self.back_btn = QToolButton()
        self.back_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.back_btn.setIconSize(QSize(20, 20))
        self.back_btn.setToolTip("后退")
        self.back_btn.setFixedSize(28, 28)
        self.back_btn.setVisible(False)
        self.layout.addWidget(self.back_btn)

        # 前进按钮（默认隐藏，可在设置中显示）
        self.forward_btn = QToolButton()
        self.forward_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.forward_btn.setIconSize(QSize(20, 20))
        self.forward_btn.setToolTip("前进")
        self.forward_btn.setFixedSize(28, 28)
        self.forward_btn.setVisible(False)
        self.layout.addWidget(self.forward_btn)

        # 上级目录按钮
        self.up_btn = QToolButton()
        self.up_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.up_btn.setIconSize(QSize(20, 20))
        self.up_btn.setToolTip("上级目录")
        self.up_btn.setFixedSize(28, 28)
        self.up_btn.clicked.connect(self.go_up)
        self.layout.addWidget(self.up_btn)

        # 刷新按钮
        self.refresh_btn = QToolButton()
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_btn.setIconSize(QSize(20, 20))
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.setFixedSize(28, 28)
        self.layout.addWidget(self.refresh_btn)

        # 目录树按钮
        self.tree_btn = QToolButton()
        self.tree_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.tree_btn.setIconSize(QSize(20, 20))
        self.tree_btn.setToolTip("目录树")
        self.tree_btn.setFixedSize(28, 28)
        self.tree_btn.setCheckable(True)
        self.tree_btn.clicked.connect(self.on_tree_clicked)
        self.layout.addWidget(self.tree_btn)

        # 标签页按钮
        self.tabs_btn = QToolButton()
        self.tabs_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.tabs_btn.setIconSize(QSize(20, 20))
        self.tabs_btn.setToolTip("标签页")
        self.tabs_btn.setFixedSize(28, 28)
        self.tabs_btn.setCheckable(True)
        self.tabs_btn.clicked.connect(self.on_tabs_clicked)
        self.layout.addWidget(self.tabs_btn)

        # 查看模式按钮（图标/超大图标/列表循环切换）
        self.view_btn = QToolButton()
        self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.view_btn.setIconSize(QSize(20, 20))
        self.view_btn.setToolTip("查看模式：图标 → 超大图标 → 列表")
        self.view_btn.setFixedSize(28, 28)
        self.view_btn.setCheckable(False)
        self._view_mode = 'icon'  # icon / xlarge / list
        self.view_btn.clicked.connect(self.on_view_clicked)
        self.layout.addWidget(self.view_btn)

        # 新建文件夹按钮（用标准文件夹图标）
        self.new_folder_btn = QToolButton()
        self.new_folder_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        )
        self.new_folder_btn.setIconSize(QSize(20, 20))
        self.new_folder_btn.setToolTip("新建文件夹")
        self.new_folder_btn.setFixedSize(28, 28)
        self.new_folder_btn.clicked.connect(self.on_new_folder_clicked)
        self.layout.addWidget(self.new_folder_btn)

        # 终端按钮
        self.terminal_btn = QToolButton()
        self.terminal_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_CommandLink))
        self.terminal_btn.setIconSize(QSize(20, 20))
        self.terminal_btn.setToolTip("打开终端")
        self.terminal_btn.setFixedSize(28, 28)
        self.terminal_btn.clicked.connect(self.on_terminal_clicked)
        self.layout.addWidget(self.terminal_btn)
        
        # 路径输入框
        self.combo_box = QComboBox()
        self.combo_box.setEditable(True)
        self.combo_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_box.setMinimumHeight(28)

        # 设置自动补全（共享模型）
        self._setup_shared_completer()

        # 信号
        self.combo_box.lineEdit().returnPressed.connect(self.on_return_pressed)
        self.combo_box.activated.connect(self.on_item_activated)
        
        self.layout.addWidget(self.combo_box)
        
        # 设置样式

    
    def _setup_shared_completer(self):
        """设置共享的 completer 模型"""
        if PathBar._shared_completer_model is None:
            PathBar._shared_completer_model = QFileSystemModel()
            PathBar._shared_completer_model.setRootPath("")
        
        self.completer = QCompleter()
        self.completer.setModel(PathBar._shared_completer_model)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.combo_box.setCompleter(self.completer)
    
    
    def set_path(self, path: str):
        """设置路径"""
        self.combo_box.setEditText(path)
        # 添加到历史
        if self.combo_box.findText(path) == -1:
            self.combo_box.addItem(path)
    
    def get_path(self) -> str:
        """获取当前路径"""
        return self.combo_box.currentText()
    
    def on_return_pressed(self):
        """回车处理"""
        path = self.combo_box.currentText().strip()
        if path:
            self.path_entered.emit(path)
    
    def on_item_activated(self, index):
        """下拉项激活"""
        path = self.combo_box.itemText(index)
        if path:
            self.path_entered.emit(path)
    
    def go_up(self):
        """返回上级目录"""
        import os
        current = self.combo_box.currentText()
        parent = os.path.dirname(current)
        if parent and parent != current:
            self.path_entered.emit(parent)

    def on_tree_clicked(self):
        """目录树按钮点击"""
        self.tree_toggle_requested.emit()

    def on_tabs_clicked(self):
        """标签页按钮点击"""
        self.tabs_toggle_requested.emit()

    def on_view_clicked(self):
        """查看模式按钮点击：循环图标 → 超大图标 → 列表"""
        modes = ['icon', 'xlarge', 'list']
        idx = modes.index(self._view_mode)
        self._view_mode = modes[(idx + 1) % len(modes)]
        logger.info(f"[DEBUG] PathBar.on_view_clicked: emitting view_mode_requested with mode={self._view_mode}")
        self.view_mode_requested.emit(self._view_mode)
        
        if self._view_mode == 'icon':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
            self.view_btn.setToolTip("当前：图标，点击切换超大图标")
        elif self._view_mode == 'xlarge':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
            self.view_btn.setToolTip("当前：超大图标（图片预览），点击切换列表")
        else:
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
            self.view_btn.setToolTip("当前：列表，点击切换图标")

    def on_new_folder_clicked(self):
        """新建文件夹按钮点击"""
        self.new_folder_requested.emit()

    def on_terminal_clicked(self):
        """终端按钮点击"""
        self.terminal_requested.emit()

    def set_tree_button_checked(self, checked: bool):
        """设置目录树按钮状态"""
        self.tree_btn.setChecked(checked)

    def set_tabs_button_checked(self, checked: bool):
        """设置标签页按钮状态"""
        self.tabs_btn.setChecked(checked)

    def set_view_mode(self, mode: str):
        """设置查看模式（更新按钮状态）"""
        self._view_mode = mode
        if mode == 'icon':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
            self.view_btn.setToolTip("当前：图标，点击切换超大图标")
        elif mode == 'xlarge':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
            self.view_btn.setToolTip("当前：超大图标（图片预览），点击切换列表")
        elif mode == 'list':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
            self.view_btn.setToolTip("当前：列表，点击切换图标")

    def set_button_visibility(self, button_name: str, visible: bool):
        """设置工具栏按钮可见性"""
        btn_map = {
            'back': self.back_btn,
            'forward': self.forward_btn,
            'up': self.up_btn,
            'refresh': self.refresh_btn,
            'tree': self.tree_btn,
            'tabs': self.tabs_btn,
            'view': self.view_btn,
            'new_folder': self.new_folder_btn,
            'terminal': self.terminal_btn,
        }
        btn = btn_map.get(button_name)
        if btn:
            btn.setVisible(visible)
