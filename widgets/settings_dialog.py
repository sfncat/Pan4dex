"""
Pan4dex 万格 — 设置对话框（主题/字体）
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFontDialog, QColorDialog, QGroupBox,
    QFormLayout, QSpinBox, QTabWidget, QWidget, QCheckBox
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt

from config.app_config import DEFAULT_THEME


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("设置")
        self.setMinimumSize(400, 300)
        
        # 当前设置
        self.current_theme = DEFAULT_THEME
        self.current_font_family = "系统默认"
        self.current_font_size = 9
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        
        # 标签页
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # 主题设置
        theme_tab = self.create_theme_tab()
        tabs.addTab(theme_tab, "主题")

        # 字体设置
        font_tab = self.create_font_tab()
        tabs.addTab(font_tab, "字体")

        # 工具栏设置
        toolbar_tab = self.create_toolbar_tab()
        tabs.addTab(toolbar_tab, "工具栏")

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
    
    def create_theme_tab(self) -> QWidget:
        """创建设置主题标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 主题选择
        theme_group = QGroupBox("主题")
        theme_layout = QFormLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("深色 (QDarkStyle)", "dark")
        self.theme_combo.addItem("浅色 (QDarkStyle)", "light")
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addRow("主题:", self.theme_combo)
        
        layout.addWidget(theme_group)
        layout.addStretch()
        
        return widget
    
    def create_font_tab(self) -> QWidget:
        """创建设置字体标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 字体选择
        font_group = QGroupBox("字体")
        font_layout = QFormLayout(font_group)
        
        self.font_combo = QComboBox()
        self.font_combo.addItem("系统默认", None)
        self.font_combo.addItem("Microsoft YaHei UI", "Microsoft YaHei UI")
        self.font_combo.addItem("Segoe UI", "Segoe UI")
        self.font_combo.addItem("Noto Sans CJK SC", "Noto Sans CJK SC")
        self.font_combo.addItem("DejaVu Sans", "DejaVu Sans")
        self.font_combo.addItem("Consolas", "Consolas")
        self.font_combo.addItem("Courier New", "Courier New")
        self.font_combo.currentIndexChanged.connect(self.on_font_changed)
        font_layout.addRow("字体:", self.font_combo)
        
        # 字号
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(9)
        font_layout.addRow("字号:", self.font_size_spin)
        
        # 预览
        self.preview_label = QLabel("这是字体预览文本 - Pan4dex 万格")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(60)
        font_layout.addRow("预览:", self.preview_label)
        
        layout.addWidget(font_group)
        layout.addStretch()
        
        return widget
    
    def create_toolbar_tab(self) -> QWidget:
        """创建工具栏设置标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        toolbar_group = QGroupBox("工具栏按钮")
        toolbar_layout = QVBoxLayout(toolbar_group)
        
        # 定义所有按钮的 checkbox
        self.toolbar_checkboxes = {}
        btn_labels = [
            ('back', '后退'),
            ('forward', '前进'),
            ('up', '上级目录'),
            ('refresh', '刷新'),
            ('tree', '目录树'),
            ('tabs', '标签页'),
            ('view', '查看模式'),
            ('new_folder', '新建文件夹'),
            ('terminal', '终端'),
        ]
        for key, label in btn_labels:
            cb = QCheckBox(f"{label} (&{label[0]})")
            # 前进/后退默认不显示
            if key in ('back', 'forward'):
                cb.setChecked(False)
            else:
                cb.setChecked(True)
            self.toolbar_checkboxes[key] = cb
            toolbar_layout.addWidget(cb)
        
        layout.addWidget(toolbar_group)
        layout.addStretch()
        return widget

    def on_theme_changed(self, index):
        """主题变化"""
        self.current_theme = self.theme_combo.itemData(index)
    
    def on_font_changed(self, index):
        """字体变化"""
        self.current_font_family = self.font_combo.currentText()
        self.current_font_size = self.font_size_spin.value()
        self.update_preview()
    
    def update_preview(self):
        """更新字体预览"""
        font = QFont(self.current_font_family, self.font_size_spin.value())
        self.preview_label.setFont(font)
    
    def get_settings(self) -> dict:
        """获取设置"""
        settings = {
            'theme': self.current_theme,
            'font_family': self.font_combo.currentText(),
            'font_size': self.font_size_spin.value(),
        }
        # 收集工具栏按钮可见性
        if hasattr(self, 'toolbar_checkboxes'):
            settings['toolbar_buttons'] = {
                key: cb.isChecked() for key, cb in self.toolbar_checkboxes.items()
            }
        return settings
