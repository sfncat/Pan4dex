"""
Pan4dex 万格 — 批量重命名工具
"""
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QCheckBox, QMessageBox, QGroupBox,
    QSpinBox, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt


class BatchRenameDialog(QDialog):
    """批量重命名对话框"""
    
    def __init__(self, files: list[str], parent=None):
        super().__init__(parent)
        
        self.files = files
        self.preview_list = []
        
        self.setWindowTitle("批量重命名")
        self.setMinimumSize(600, 500)
        
        self.init_ui()
        self.update_preview()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 标签页
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        
        # 模板标签页
        self.template_tab = QWidget()
        self.init_template_tab()
        self.tab_widget.addTab(self.template_tab, "模板")
        
        # 正则标签页
        self.regex_tab = QWidget()
        self.init_regex_tab()
        self.tab_widget.addTab(self.regex_tab, "正则替换")
        
        # 大小写标签页
        self.case_tab = QWidget()
        self.init_case_tab()
        self.tab_widget.addTab(self.case_tab, "大小写转换")
        
        # 预览区域
        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_list_widget = QListWidget()
        self.preview_list_widget.setMaximumHeight(150)
        preview_layout.addWidget(self.preview_list_widget)
        
        self.layout.addWidget(preview_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("刷新预览")
        self.preview_btn.clicked.connect(self.update_preview)
        btn_layout.addWidget(self.preview_btn)
        
        btn_layout.addStretch()
        
        self.ok_btn = QPushButton("应用")
        self.ok_btn.clicked.connect(self.apply_rename)
        btn_layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        self.layout.addLayout(btn_layout)
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D2D;
                color: #CCCCCC;
            }
            QTabWidget::pane {
                border: 1px solid #404040;
            }
            QTabBar::tab {
                background-color: #2D2D2D;
                color: #CCCCCC;
                padding: 8px 16px;
                border: 1px solid #404040;
            }
            QTabBar::tab:selected {
                background-color: #2196F3;
            }
            QLineEdit {
                background-color: #3D3D3D;
                color: #CCCCCC;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 5px;
            }
            QPushButton {
                background-color: #3D3D3D;
                color: #CCCCCC;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #2196F3;
            }
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
            }
            QGroupBox {
                border: 1px solid #404040;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                color: #CCCCCC;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
    
    def init_template_tab(self):
        """初始化模板标签页"""
        layout = QVBoxLayout(self.template_tab)
        
        # 模板输入
        template_label = QLabel("模板（支持以下占位符）：")
        layout.addWidget(template_label)
        
        # 占位符说明
        placeholder_info = QLabel(
            "[N] - 序号（从 1 开始）\n"
            "[N:001] - 序号（3 位补零）\n"
            "[Y] - 年  [M] - 月  [D] - 日\n"
            "[h] - 时  [m] - 分  [s] - 秒\n"
            "[name] - 原文件名（不含扩展名）\n"
            "[ext] - 原扩展名"
        )
        placeholder_info.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(placeholder_info)
        
        self.template_edit = QLineEdit()
        self.template_edit.setText("[N:001]_[name]")
        self.template_edit.textChanged.connect(self.update_preview)
        layout.addWidget(self.template_edit)
        
        # 起始序号
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("起始序号:"))
        self.start_spin = QSpinBox()
        self.start_spin.setMinimum(0)
        self.start_spin.setMaximum(9999)
        self.start_spin.setValue(1)
        self.start_spin.valueChanged.connect(self.update_preview)
        start_layout.addWidget(self.start_spin)
        start_layout.addStretch()
        layout.addLayout(start_layout)
        
        layout.addStretch()
    
    def init_regex_tab(self):
        """初始化正则标签页"""
        layout = QVBoxLayout(self.regex_tab)
        
        # 查找
        find_label = QLabel("查找（正则表达式）：")
        layout.addWidget(find_label)
        
        self.find_edit = QLineEdit()
        self.find_edit.textChanged.connect(self.update_preview)
        layout.addWidget(self.find_edit)
        
        # 替换
        replace_label = QLabel("替换为：")
        layout.addWidget(replace_label)
        
        self.replace_edit = QLineEdit()
        self.replace_edit.textChanged.connect(self.update_preview)
        layout.addWidget(self.replace_edit)
        
        layout.addStretch()
    
    def init_case_tab(self):
        """初始化大小写标签页"""
        layout = QVBoxLayout(self.case_tab)
        
        case_label = QLabel("转换方式：")
        layout.addWidget(case_label)
        
        self.case_combo = QComboBox()
        self.case_combo.addItems([
            "全大写",
            "全小写",
            "首字母大写",
            "每个单词首字母大写"
        ])
        self.case_combo.currentIndexChanged.connect(self.update_preview)
        layout.addWidget(self.case_combo)
        
        layout.addStretch()
    
    def update_preview(self):
        """更新预览"""
        self.preview_list = []
        self.preview_list_widget.clear()
        
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:  # 模板
            self.preview_template()
        elif current_tab == 1:  # 正则
            self.preview_regex()
        elif current_tab == 2:  # 大小写
            self.preview_case()
        
        # 更新预览列表
        for old_name, new_name in self.preview_list:
            item = QListWidgetItem(f"{old_name} → {new_name}")
            if old_name == new_name:
                item.setForeground(Qt.GlobalColor.gray)
            self.preview_list_widget.addItem(item)
    
    def preview_template(self):
        """模板预览"""
        template = self.template_edit.text()
        start = self.start_spin.value()
        
        for i, file_path in enumerate(self.files):
            old_name = os.path.basename(file_path)
            name, ext = os.path.splitext(old_name)
            
            # 替换占位符
            new_name = template
            new_name = new_name.replace("[N:001]", f"{start + i:03d}")
            new_name = new_name.replace("[N:01]", f"{start + i:02d}")
            new_name = new_name.replace("[N]", str(start + i))
            new_name = new_name.replace("[name]", name)
            new_name = new_name.replace("[ext]", ext)
            
            # 日期时间
            from datetime import datetime
            now = datetime.now()
            new_name = new_name.replace("[Y]", now.strftime("%Y"))
            new_name = new_name.replace("[M]", now.strftime("%m"))
            new_name = new_name.replace("[D]", now.strftime("%d"))
            new_name = new_name.replace("[h]", now.strftime("%H"))
            new_name = new_name.replace("[m]", now.strftime("%M"))
            new_name = new_name.replace("[s]", now.strftime("%S"))
            
            new_name = new_name + ext
            self.preview_list.append((old_name, new_name))
    
    def preview_regex(self):
        """正则预览"""
        pattern = self.find_edit.text()
        replacement = self.replace_edit.text()
        
        if not pattern:
            for file_path in self.files:
                old_name = os.path.basename(file_path)
                self.preview_list.append((old_name, old_name))
            return
        
        try:
            for file_path in self.files:
                old_name = os.path.basename(file_path)
                new_name = re.sub(pattern, replacement, old_name)
                self.preview_list.append((old_name, new_name))
        except re.error:
            for file_path in self.files:
                old_name = os.path.basename(file_path)
                self.preview_list.append((old_name, old_name))
    
    def preview_case(self):
        """大小写预览"""
        case_type = self.case_combo.currentIndex()
        
        for file_path in self.files:
            old_name = os.path.basename(file_path)
            name, ext = os.path.splitext(old_name)
            
            if case_type == 0:  # 全大写
                new_name = name.upper() + ext
            elif case_type == 1:  # 全小写
                new_name = name.lower() + ext
            elif case_type == 2:  # 首字母大写
                new_name = name.capitalize() + ext
            else:  # 每个单词首字母大写
                new_name = name.title() + ext
            
            self.preview_list.append((old_name, new_name))
    
    def apply_rename(self):
        """应用重命名"""
        if not self.preview_list:
            return
        
        # 检查是否有重命名冲突
        new_names = [new for _, new in self.preview_list]
        if len(new_names) != len(set(new_names)):
            QMessageBox.warning(
                self, "重命名冲突",
                "重命名后存在重复的文件名，请检查模板设置。"
            )
            return
        
        # 执行重命名
        renamed = 0
        errors = []
        
        for file_path, new_name in zip(self.files, new_names):
            old_name = os.path.basename(file_path)
            if old_name == new_name:
                continue
            
            new_path = os.path.join(os.path.dirname(file_path), new_name)
            
            try:
                if os.path.exists(new_path):
                    errors.append(f"{old_name} → {new_name}: 目标文件已存在")
                else:
                    os.rename(file_path, new_path)
                    renamed += 1
            except Exception as e:
                errors.append(f"{old_name} → {new_name}: {e}")
        
        if errors:
            QMessageBox.warning(
                self, "部分重命名失败",
                f"成功重命名 {renamed} 个文件，{len(errors)} 个失败：\n" + "\n".join(errors[:5])
            )
        else:
            QMessageBox.information(
                self, "重命名完成",
                f"成功重命名 {renamed} 个文件。"
            )
        
        self.accept()
