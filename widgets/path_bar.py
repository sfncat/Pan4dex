"""
Pan4dex 万格 — 路径栏组件
"""
from PyQt6.QtGui import QFileSystemModel, QAction
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QWidget, 
    QHBoxLayout, QPushButton, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QDir


class PathBar(QWidget):
    """路径栏组件"""
    
    # 信号
    path_entered = pyqtSignal(str)  # 路径输入信号
    tree_toggle_requested = pyqtSignal()  # 目录树按钮点击信号
    tabs_toggle_requested = pyqtSignal()  # 标签页按钮点击信号
    terminal_requested = pyqtSignal()  # 终端按钮点击信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        
        # 后退按钮
        self.back_btn = QToolButton()
        self.back_btn.setText("◀")
        self.back_btn.setToolTip("后退")
        self.back_btn.setFixedSize(24, 24)
        self.layout.addWidget(self.back_btn)
        
        # 前进按钮
        self.forward_btn = QToolButton()
        self.forward_btn.setText("▶")
        self.forward_btn.setToolTip("前进")
        self.forward_btn.setFixedSize(24, 24)
        self.layout.addWidget(self.forward_btn)
        
        # 上级目录按钮
        self.up_btn = QToolButton()
        self.up_btn.setText("▲")
        self.up_btn.setToolTip("上级目录")
        self.up_btn.setFixedSize(24, 24)
        self.up_btn.clicked.connect(self.go_up)
        self.layout.addWidget(self.up_btn)
        
        # 刷新按钮
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("🔄")
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.setFixedSize(24, 24)
        self.layout.addWidget(self.refresh_btn)
        
        # 目录树按钮
        self.tree_btn = QToolButton()
        self.tree_btn.setText("🌲")
        self.tree_btn.setToolTip("目录树")
        self.tree_btn.setFixedSize(24, 24)
        self.tree_btn.setCheckable(True)
        self.tree_btn.clicked.connect(self.on_tree_clicked)
        self.layout.addWidget(self.tree_btn)
        
        # 标签页按钮
        self.tabs_btn = QToolButton()
        self.tabs_btn.setText("📑")
        self.tabs_btn.setToolTip("标签页")
        self.tabs_btn.setFixedSize(24, 24)
        self.tabs_btn.setCheckable(True)
        self.tabs_btn.clicked.connect(self.on_tabs_clicked)
        self.layout.addWidget(self.tabs_btn)
        
        # 终端按钮
        self.terminal_btn = QToolButton()
        self.terminal_btn.setText("🖥")
        self.terminal_btn.setToolTip("打开终端")
        self.terminal_btn.setFixedSize(24, 24)
        self.terminal_btn.clicked.connect(self.on_terminal_clicked)
        self.layout.addWidget(self.terminal_btn)
        
        # 路径输入框
        self.combo_box = QComboBox()
        self.combo_box.setEditable(True)
        self.combo_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_box.setMinimumHeight(24)
        
        # 设置自动补全
        self.completer = QCompleter()
        self.completer_model = QFileSystemModel()
        self.completer_model.setRootPath("")
        self.completer.setModel(self.completer_model)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.combo_box.setCompleter(self.completer)
        
        # 信号
        self.combo_box.lineEdit().returnPressed.connect(self.on_return_pressed)
        self.combo_box.activated.connect(self.on_item_activated)
        
        self.layout.addWidget(self.combo_box)
        
        # 设置样式

    
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

    def on_terminal_clicked(self):
        """终端按钮点击"""
        self.terminal_requested.emit()

    def set_tree_button_checked(self, checked: bool):
        """设置目录树按钮状态"""
        self.tree_btn.setChecked(checked)

    def set_tabs_button_checked(self, checked: bool):
        """设置标签页按钮状态"""
        self.tabs_btn.setChecked(checked)
