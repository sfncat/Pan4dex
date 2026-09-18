"""
Pan4dex 万格 — 用户操作配置对话框
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QTextEdit, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QGroupBox, QComboBox, QCheckBox,
    QKeySequenceValidator
)
from PyQt6.QtCore import Qt, pyqtSlot


class UserOperationsDialog(QDialog):
    """用户操作配置对话框"""
    
    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        
        self.config_manager = config_manager
        self.operations_list = []
        
        self.setWindowTitle("用户操作配置")
        self.setMinimumSize(700, 500)
        
        self.init_ui()
        self.load_operations()
    
    def init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        
        # 操作列表
        list_group = QGroupBox("已配置的操作")
        list_layout = QVBoxLayout(list_group)
        
        self.op_list = QListWidget()
        self.op_list.itemClicked.connect(self.on_operation_selected)
        list_layout.addWidget(self.op_list)
        
        layout.addWidget(list_group)
        
        # 操作详情
        detail_group = QGroupBox("操作详情")
        detail_layout = QVBoxLayout(detail_group)
        
        # 名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("操作名称，如：用 VS Code 打开")
        name_layout.addWidget(self.name_edit)
        detail_layout.addLayout(name_layout)
        
        # 命令
        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel("命令:"))
        self.cmd_edit = QLineEdit()
        self.cmd_edit.setPlaceholderText("命令格式：code {} 或 firefox {}")
        self.cmd_edit.setValidator(QKeySequenceValidator())
        cmd_layout.addWidget(self.cmd_edit)
        detail_layout.addLayout(cmd_layout)
        
        # 描述
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("描述:"))
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("操作的简要描述")
        desc_layout.addWidget(self.desc_edit)
        detail_layout.addLayout(desc_layout)
        
        # 文件类型
        file_type_layout = QHBoxLayout()
        file_type_layout.addWidget(QLabel("支持的文件类型:"))
        self.file_types_edit = QLineEdit()
        self.file_types_edit.setPlaceholderText("用逗号分隔，如：.html,.htm,.svg 或 * 表示所有")
        file_type_layout.addWidget(self.file_types_edit)
        detail_layout.addLayout(file_type_layout)
        
        # 启用复选框
        enable_layout = QHBoxLayout()
        self.enable_check = QCheckBox("启用此操作")
        self.enable_check.setChecked(True)
        enable_layout.addWidget(self.enable_check)
        enable_layout.addStretch()
        detail_layout.addLayout(enable_layout)
        
        layout.addWidget(detail_group)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("添加新操作")
        self.add_btn.clicked.connect(self.add_operation)
        btn_layout.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("编辑操作")
        self.edit_btn.clicked.connect(self.edit_operation)
        btn_layout.addWidget(self.edit_btn)
        
        self.delete_btn = QPushButton("删除操作")
        self.delete_btn.clicked.connect(self.delete_operation)
        btn_layout.addWidget(self.delete_btn)
        
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_and_close)
        btn_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        
        self.setStyleSheet("""
            QDialog { background-color: #2D2D2D; color: #CCCCCC; }
            QGroupBox { border: 1px solid #404040; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { color: #CCCCCC; subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px; }
            QPushButton { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px 15px; }
            QPushButton:hover { background-color: #505050; }
            QListWidget { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px; }
            QListWidget::item { padding: 5px; border-radius: 3px; }
            QListWidget::item:selected { background-color: #505050; }
        """)
    
    def load_operations(self):
        """加载操作列表"""
        self.op_list.clear()
        
        if not self.config_manager:
            return
        
        operations = self.config_manager.get_operations(enabled_only=False)
        
        for op in operations:
            status = "✓" if op.get('enabled', True) else "✗"
            item = QListWidgetItem(f"{status} {op['name']}")
            item.setData(Qt.ItemDataRole.UserRole, op['id'])
            self.op_list.addItem(item)
    
    @pyqtSlot(QListWidgetItem)
    def on_operation_selected(self, item):
        """选择操作时显示详情"""
        if not item:
            return
        
        op_id = item.data(Qt.ItemDataRole.UserRole)
        if not self.config_manager:
            return
        
        op = self.config_manager.get_operation_by_id(op_id)
        if op:
            self.name_edit.setText(op.get('name', ''))
            self.cmd_edit.setText(op.get('command', ''))
            self.desc_edit.setText(op.get('description', ''))
            file_types = ', '.join(op.get('file_types', ['*']))
            self.file_types_edit.setText(file_types)
            self.enable_check.setChecked(op.get('enabled', True))
    
    def add_operation(self):
        """添加新操作"""
        name = self.name_edit.text().strip()
        command = self.cmd_edit.text().strip()
        description = self.desc_edit.text().strip()
        file_types_str = self.file_types_edit.text().strip()
        
        if not name or not command:
            QMessageBox.warning(self, "警告", "请输入操作名称和命令")
            return
        
        # 解析文件类型
        if file_types_str:
            file_types = [ft.strip() for ft in file_types_str.split(',') if ft.strip()]
        else:
            file_types = ['*']
        
        operation = {
            'name': name,
            'command': command,
            'description': description,
            'file_types': file_types
        }
        
        if self.config_manager:
            op_id = self.config_manager.add_operation(operation)
            self.load_operations()
            
            # 选中新添加的操作
            for i in range(self.op_list.count()):
                item = self.op_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == op_id:
                    self.op_list.setCurrentItem(item)
                    break
            
            QMessageBox.information(self, "成功", f"操作 '{name}' 已添加")
    
    def edit_operation(self):
        """编辑当前选中的操作"""
        current_item = self.op_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "警告", "请先选择一个操作")
            return
        
        op_id = current_item.data(Qt.ItemDataRole.UserRole)
        name = self.name_edit.text().strip()
        command = self.cmd_edit.text().strip()
        description = self.desc_edit.text().strip()
        file_types_str = self.file_types_edit.text().strip()
        
        if not name or not command:
            QMessageBox.warning(self, "警告", "请输入操作名称和命令")
            return
        
        # 解析文件类型
        if file_types_str:
            file_types = [ft.strip() for ft in file_types_str.split(',') if ft.strip()]
        else:
            file_types = ['*']
        
        updates = {
            'name': name,
            'command': command,
            'description': description,
            'file_types': file_types,
            'enabled': self.enable_check.isChecked()
        }
        
        if self.config_manager:
            if self.config_manager.update_operation(op_id, updates):
                self.load_operations()
                QMessageBox.information(self, "成功", f"操作 '{name}' 已更新")
    
    def delete_operation(self):
        """删除当前选中的操作"""
        current_item = self.op_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "警告", "请先选择一个操作")
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除此操作吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            op_id = current_item.data(Qt.ItemDataRole.UserRole)
            if self.config_manager:
                if self.config_manager.delete_operation(op_id):
                    self.load_operations()
                    QMessageBox.information(self, "成功", "操作已删除")
    
    def save_and_close(self):
        """保存并关闭"""
        self.accept()
