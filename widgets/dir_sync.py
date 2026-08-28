"""
Pan4dex 万格 — 目录同步工具
"""
import os
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QComboBox, QMessageBox, QGroupBox, QHeaderView
)
from PyQt6.QtCore import Qt


class DirSyncDialog(QDialog):
    """目录同步对话框"""
    
    def __init__(self, left_path: str = "", right_path: str = "", parent=None):
        super().__init__(parent)
        
        self.left_path = left_path
        self.right_path = right_path
        self.differences = []
        
        self.setWindowTitle("目录同步")
        self.setMinimumSize(700, 500)
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 路径选择
        path_group = QGroupBox("选择目录")
        path_layout = QHBoxLayout(path_group)
        
        # 左侧目录
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("左侧目录:"))
        left_btn_layout = QHBoxLayout()
        self.left_edit = QLineEdit(self.left_path)
        left_btn_layout.addWidget(self.left_edit)
        self.left_btn = QPushButton("浏览...")
        self.left_btn.clicked.connect(lambda: self.browse_dir("left"))
        left_btn_layout.addWidget(self.left_btn)
        left_layout.addLayout(left_btn_layout)
        path_layout.addLayout(left_layout)
        
        # 右侧目录
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("右侧目录:"))
        right_btn_layout = QHBoxLayout()
        self.right_edit = QLineEdit(self.right_path)
        right_btn_layout.addWidget(self.right_edit)
        self.right_btn = QPushButton("浏览...")
        self.right_btn.clicked.connect(lambda: self.browse_dir("right"))
        right_btn_layout.addWidget(self.right_btn)
        right_layout.addLayout(right_btn_layout)
        path_layout.addLayout(right_layout)
        
        self.layout.addWidget(path_group)
        
        # 同步模式
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("同步模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "双向同步（合并两侧差异）",
            "镜像同步（左→右，使右与左一致）",
            "镜像同步（右→左，使左与右一致）",
            "仅显示差异（不执行操作）"
        ])
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        
        self.compare_btn = QPushButton("比较")
        self.compare_btn.clicked.connect(self.compare)
        mode_layout.addWidget(self.compare_btn)
        
        self.layout.addLayout(mode_layout)
        
        # 差异列表
        diff_group = QGroupBox("差异")
        diff_layout = QVBoxLayout(diff_group)
        
        self.diff_tree = QTreeWidget()
        self.diff_tree.setHeaderLabels(["文件名", "状态", "左侧大小", "右侧大小"])
        self.diff_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        diff_layout.addWidget(self.diff_tree)
        
        self.layout.addWidget(diff_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        self.sync_btn = QPushButton("执行同步")
        self.sync_btn.clicked.connect(self.execute_sync)
        btn_layout.addWidget(self.sync_btn)
        
        btn_layout.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        self.layout.addLayout(btn_layout)
        
        # 样式
        self.setStyleSheet("""
            QDialog { background-color: #2D2D2D; color: #CCCCCC; }
            QGroupBox { border: 1px solid #404040; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { color: #CCCCCC; subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px; }
            QPushButton { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px 15px; }
            QPushButton:hover { background-color: #505050; }
            QTreeWidget { background-color: #1E1E1E; color: #CCCCCC; border: none; }
            QTreeWidget::item:hover { background-color: #2A2A2A; }
            QTreeWidget::item:selected { background-color: #2196F3; }
            QHeaderView::section { background-color: #2D2D2D; color: #CCCCCC; border: 1px solid #404040; padding: 5px; }
            QComboBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
        """)
    
    def browse_dir(self, side: str):
        """浏览目录"""
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            if side == "left":
                self.left_edit.setText(path)
                self.left_path = path
            else:
                self.right_edit.setText(path)
                self.right_path = path
    
    def compare(self):
        """比较目录"""
        self.left_path = self.left_edit.text()
        self.right_path = self.right_edit.text()
        
        if not self.left_path or not self.right_path:
            QMessageBox.warning(self, "警告", "请先选择两个目录")
            return
        
        if not os.path.isdir(self.left_path) or not os.path.isdir(self.right_path):
            QMessageBox.warning(self, "错误", "目录不存在")
            return
        
        self.diff_tree.clear()
        self.differences = []
        
        left_files = self._get_all_files(self.left_path)
        right_files = self._get_all_files(self.right_path)
        
        all_files = set(left_files.keys()) | set(right_files.keys())
        
        for rel_path in sorted(all_files):
            left_info = left_files.get(rel_path)
            right_info = right_files.get(rel_path)
            
            if left_info and right_info:
                if left_info['size'] != right_info['size']:
                    status = "大小不同"
                elif left_info['mtime'] != right_info['mtime']:
                    status = "修改时间不同"
                else:
                    status = "相同"
            elif left_info:
                status = "仅左侧存在"
            else:
                status = "仅右侧存在"
            
            self.differences.append({
                'path': rel_path,
                'status': status,
                'left': left_info,
                'right': right_info
            })
            
            item = QTreeWidgetItem([
                rel_path,
                status,
                self.format_size(left_info['size']) if left_info else "-",
                self.format_size(right_info['size']) if right_info else "-"
            ])
            self.diff_tree.addTopLevelItem(item)
        
        self.setWindowTitle(f"目录同步 - 发现 {len(self.differences)} 个差异")
    
    def execute_sync(self):
        """执行同步"""
        if not self.differences:
            QMessageBox.information(self, "提示", "请先比较目录")
            return
        
        mode = self.mode_combo.currentIndex()
        
        if mode == 3:  # 仅显示差异
            QMessageBox.information(self, "提示", "当前为仅显示差异模式，不会执行操作")
            return
        
        reply = QMessageBox.question(
            self, "确认同步",
            f"确定要执行同步吗？模式: {self.mode_combo.currentText()}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        synced = 0
        errors = []
        
        for diff in self.differences:
            if diff['status'] == "相同":
                continue
            
            try:
                if mode == 0:  # 双向同步
                    if diff['left'] and not diff['right']:
                        # 复制左到右
                        src = os.path.join(self.left_path, diff['path'])
                        dst = os.path.join(self.right_path, diff['path'])
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                        synced += 1
                    elif diff['right'] and not diff['left']:
                        # 复制右到左
                        src = os.path.join(self.right_path, diff['path'])
                        dst = os.path.join(self.left_path, diff['path'])
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                        synced += 1
                    elif diff['left'] and diff['right']:
                        # 复制较新的一侧到另一侧
                        if diff['left']['mtime'] > diff['right']['mtime']:
                            src = os.path.join(self.left_path, diff['path'])
                            dst = os.path.join(self.right_path, diff['path'])
                            shutil.copy2(src, dst)
                        else:
                            src = os.path.join(self.right_path, diff['path'])
                            dst = os.path.join(self.left_path, diff['path'])
                            shutil.copy2(src, dst)
                        synced += 1
                
                elif mode == 1:  # 镜像左→右
                    if diff['left'] and not diff['right']:
                        src = os.path.join(self.left_path, diff['path'])
                        dst = os.path.join(self.right_path, diff['path'])
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                        synced += 1
                    elif diff['right'] and not diff['left']:
                        # 删除右侧多余文件
                        os.remove(os.path.join(self.right_path, diff['path']))
                        synced += 1
                    elif diff['left'] and diff['right']:
                        src = os.path.join(self.left_path, diff['path'])
                        dst = os.path.join(self.right_path, diff['path'])
                        shutil.copy2(src, dst)
                        synced += 1
                
                elif mode == 2:  # 镜像右→左
                    if diff['right'] and not diff['left']:
                        src = os.path.join(self.right_path, diff['path'])
                        dst = os.path.join(self.left_path, diff['path'])
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                        synced += 1
                    elif diff['left'] and not diff['right']:
                        # 删除左侧多余文件
                        os.remove(os.path.join(self.left_path, diff['path']))
                        synced += 1
                    elif diff['left'] and diff['right']:
                        src = os.path.join(self.right_path, diff['path'])
                        dst = os.path.join(self.left_path, diff['path'])
                        shutil.copy2(src, dst)
                        synced += 1
            
            except Exception as e:
                errors.append(f"{diff['path']}: {e}")
        
        if errors:
            QMessageBox.warning(self, "部分同步失败", f"成功 {synced} 项，失败 {len(errors)} 项")
        else:
            QMessageBox.information(self, "同步完成", f"成功同步 {synced} 项")
        
        self.compare()  # 刷新
    
    def _get_all_files(self, base_path: str) -> dict:
        """获取目录下所有文件信息"""
        files = {}
        for root, dirs, filenames in os.walk(base_path):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, base_path)
                stat = os.stat(full_path)
                files[rel_path] = {
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                }
        return files
    
    def format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
