"""
Pan4dex 万格 — 设置对话框
"""
import json
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QComboBox, QGroupBox,
    QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        
        # 配置文件路径
        self.config_dir = os.path.expanduser("~/.config/pan4dex")
        self.config_file = os.path.join(self.config_dir, "settings.json")
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 终端设置
        terminal_group = QGroupBox("终端设置")
        terminal_layout = QFormLayout()
        
        self.terminal_combo = QComboBox()
        self.terminal_combo.setEditable(True)
        self.terminal_combo.addItems([
            "自动检测",
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "mate-terminal",
            "terminator",
            "tilix",
            "alacritty",
            "kitty",
            "xterm",
            "x-terminal-emulator",
        ])
        self.terminal_combo.setPlaceholderText("输入终端命令或选择预设")
        
        terminal_layout.addRow("终端应用:", self.terminal_combo)
        
        hint = QLabel("设置后右键「打开终端」将使用此应用")
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        terminal_layout.addRow("", hint)
        
        terminal_group.setLayout(terminal_layout)
        layout.addWidget(terminal_group)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_settings(self):
        """加载设置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                terminal = config.get('terminal', '')
                if terminal:
                    self.terminal_combo.setCurrentText(terminal)
            except:
                pass
    
    def save_settings(self):
        """保存设置"""
        terminal = self.terminal_combo.currentText().strip()
        if terminal == "自动检测":
            terminal = ""
        
        config = {"terminal": terminal}
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.accept()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "保存失败", f"无法保存设置: {e}")
