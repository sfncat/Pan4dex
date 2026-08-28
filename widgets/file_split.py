"""
Pan4dex 万格 — 文件分割/合并工具
"""
import os
import math
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QSpinBox, QComboBox,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class SplitWorker(QThread):
    """分割工作线程"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, file_path: str, output_dir: str, chunk_size: int = 0, num_parts: int = 0):
        super().__init__()
        self.file_path = file_path
        self.output_dir = output_dir
        self.chunk_size = chunk_size
        self.num_parts = num_parts
    
    def run(self):
        try:
            file_size = os.path.getsize(self.file_path)
            
            if self.chunk_size > 0:
                num_parts = math.ceil(file_size / self.chunk_size)
                actual_chunk_size = self.chunk_size
            else:
                num_parts = self.num_parts
                actual_chunk_size = math.ceil(file_size / num_parts)
            
            base_name = os.path.basename(self.file_path)
            
            with open(self.file_path, 'rb') as f:
                for i in range(num_parts):
                    chunk = f.read(actual_chunk_size)
                    output_path = os.path.join(self.output_dir, f"{base_name}.part{i+1:03d}")
                    
                    with open(output_path, 'wb') as out:
                        out.write(chunk)
                    
                    percent = int((i + 1) * 100 / num_parts)
                    self.progress.emit(percent)
            
            self.finished.emit(True, f"成功分割为 {num_parts} 个文件")
        except Exception as e:
            self.finished.emit(False, str(e))


class FileSplitDialog(QDialog):
    """文件分割/合并对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("文件分割/合并")
        self.setMinimumSize(450, 300)
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 分割区域
        split_group = QGroupBox("分割文件")
        split_layout = QVBoxLayout(split_group)
        
        # 选择文件
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择要分割的文件...")
        file_layout.addWidget(self.file_edit)
        
        self.file_btn = QPushButton("浏览...")
        self.file_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_btn)
        split_layout.addLayout(file_layout)
        
        # 分割方式
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("分割方式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["按大小分割", "按数量分割"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        split_layout.addLayout(mode_layout)
        
        # 大小设置
        self.size_widget = QWidget()
        self.size_layout = QHBoxLayout(self.size_widget)
        self.size_layout.addWidget(QLabel("每块大小:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 99999)
        self.size_spin.setValue(10)
        self.size_layout.addWidget(self.size_spin)
        self.size_unit = QComboBox()
        self.size_unit.addItems(["MB", "KB", "GB"])
        self.size_layout.addWidget(self.size_unit)
        self.size_layout.addStretch()
        split_layout.addWidget(self.size_widget)
        
        # 数量设置（默认隐藏）
        self.num_widget = QWidget()
        self.num_layout = QHBoxLayout(self.num_widget)
        self.num_layout.addWidget(QLabel("分割数量:"))
        self.num_spin = QSpinBox()
        self.num_spin.setRange(2, 999)
        self.num_spin.setValue(2)
        self.num_layout.addWidget(self.num_spin)
        self.num_layout.addStretch()
        self.num_widget.setVisible(False)
        split_layout.addWidget(self.num_widget)
        
        # 输出目录
        out_layout = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("输出目录...")
        out_layout.addWidget(self.out_edit)
        
        self.out_btn = QPushButton("浏览...")
        self.out_btn.clicked.connect(self.browse_output)
        out_layout.addWidget(self.out_btn)
        split_layout.addLayout(out_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        split_layout.addWidget(self.progress_bar)
        
        # 分割按钮
        self.split_btn = QPushButton("开始分割")
        self.split_btn.clicked.connect(self.split_file)
        split_layout.addWidget(self.split_btn)
        
        self.layout.addWidget(split_group)
        
        # 合并区域
        merge_group = QGroupBox("合并文件")
        merge_layout = QVBoxLayout(merge_group)
        
        # 选择第一个分块
        part_layout = QHBoxLayout()
        self.part_edit = QLineEdit()
        self.part_edit.setPlaceholderText("选择第一个分块文件（如 .part001）...")
        part_layout.addWidget(self.part_edit)
        
        self.part_btn = QPushButton("浏览...")
        self.part_btn.clicked.connect(self.browse_part)
        part_layout.addWidget(self.part_btn)
        merge_layout.addLayout(part_layout)
        
        # 输出文件
        merge_out_layout = QHBoxLayout()
        self.merge_out_edit = QLineEdit()
        self.merge_out_edit.setPlaceholderText("合并后的文件路径...")
        merge_out_layout.addWidget(self.merge_out_edit)
        
        self.merge_out_btn = QPushButton("浏览...")
        self.merge_out_btn.clicked.connect(self.browse_merge_output)
        merge_out_layout.addWidget(self.merge_out_btn)
        merge_layout.addLayout(merge_out_layout)
        
        # 合并按钮
        self.merge_btn = QPushButton("开始合并")
        self.merge_btn.clicked.connect(self.merge_files)
        merge_layout.addWidget(self.merge_btn)
        
        self.layout.addWidget(merge_group)
        
        # 关闭
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        self.layout.addWidget(self.close_btn)
        
        # 样式
        self.setStyleSheet("""
            QDialog { background-color: #2D2D2D; color: #CCCCCC; }
            QGroupBox { border: 1px solid #404040; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { color: #CCCCCC; subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px; }
            QPushButton { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px 15px; }
            QPushButton:hover { background-color: #505050; }
            QSpinBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
            QComboBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
            QProgressBar { background-color: #2D2D2D; border: none; }
            QProgressBar::chunk { background-color: #2196F3; }
        """)
    
    def on_mode_changed(self, index: int):
        """分割方式变化"""
        self.size_widget.setVisible(index == 0)
        self.num_widget.setVisible(index == 1)
    
    def browse_file(self):
        """浏览文件"""
        path, _ = QFileDialog.getOpenFileName(self, "选择要分割的文件")
        if path:
            self.file_edit.setText(path)
            # 自动设置输出目录
            self.out_edit.setText(os.path.dirname(path))
    
    def browse_output(self):
        """浏览输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.out_edit.setText(path)
    
    def browse_part(self):
        """浏览分块"""
        path, _ = QFileDialog.getOpenFileName(self, "选择第一个分块")
        if path:
            self.part_edit.setText(path)
            # 自动设置合并输出路径
            base = path.replace(".part", "").rsplit(".", 1)[0]
            self.merge_out_edit.setText(base)
    
    def browse_merge_output(self):
        """浏览合并输出"""
        path, _ = QFileDialog.getSaveFileName(self, "保存合并文件")
        if path:
            self.merge_out_edit.setText(path)
    
    def split_file(self):
        """分割文件"""
        file_path = self.file_edit.text()
        output_dir = self.out_edit.text()
        
        if not file_path or not output_dir:
            QMessageBox.warning(self, "警告", "请选择文件和输出目录")
            return
        
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "错误", "文件不存在")
            return
        
        # 计算块大小
        if self.mode_combo.currentIndex() == 0:  # 按大小
            size = self.size_spin.value()
            unit = self.size_unit.currentIndex()
            multipliers = [1024*1024, 1024, 1024*1024*1024]
            chunk_size = size * multipliers[unit]
            num_parts = 0
        else:  # 按数量
            chunk_size = 0
            num_parts = self.num_spin.value()
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.split_btn.setEnabled(False)
        
        self.worker = SplitWorker(file_path, output_dir, chunk_size, num_parts)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_split_finished)
        self.worker.start()
    
    def on_split_finished(self, success: bool, message: str):
        """分割完成"""
        self.progress_bar.setVisible(False)
        self.split_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "失败", message)
    
    def merge_files(self):
        """合并文件"""
        part_path = self.part_edit.text()
        output_path = self.merge_out_edit.text()
        
        if not part_path or not output_path:
            QMessageBox.warning(self, "警告", "请选择分块和输出路径")
            return
        
        if not os.path.exists(part_path):
            QMessageBox.warning(self, "错误", "分块文件不存在")
            return
        
        try:
            # 查找所有分块
            base_dir = os.path.dirname(part_path)
            base_name = os.path.basename(part_path)
            # 移除 .partXXX 后缀
            prefix = base_name.split(".part")[0]
            
            parts = []
            for f in os.listdir(base_dir):
                if f.startswith(prefix) and ".part" in f:
                    parts.append(f)
            
            parts.sort()
            
            # 合并
            with open(output_path, 'wb') as out:
                for part in parts:
                    part_path = os.path.join(base_dir, part)
                    with open(part_path, 'rb') as f:
                        out.write(f.read())
            
            QMessageBox.information(self, "成功", f"已合并 {len(parts)} 个分块到: {output_path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))
