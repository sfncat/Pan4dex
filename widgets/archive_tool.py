"""
Pan4dex 万格 — 压缩包处理工具
"""
import os
import zipfile
import tarfile
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QGroupBox, QComboBox
)
from PyQt6.QtCore import Qt


class ArchiveDialog(QDialog):
    """压缩包处理对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("压缩包处理")
        self.setMinimumSize(500, 400)
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 创建压缩包
        create_group = QGroupBox("创建压缩包")
        create_layout = QVBoxLayout(create_group)
        
        # 选择文件/目录
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择要压缩的文件或目录...")
        file_layout.addWidget(self.file_edit)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_source)
        file_layout.addWidget(self.browse_btn)
        create_layout.addLayout(file_layout)
        
        # 压缩格式
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["ZIP", "TAR.GT", "TAR.BZ2"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        create_layout.addLayout(format_layout)
        
        # 输出路径
        out_layout = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("输出路径...")
        out_layout.addWidget(self.out_edit)
        
        self.out_btn = QPushButton("浏览...")
        self.out_btn.clicked.connect(self.browse_output)
        out_layout.addWidget(self.out_btn)
        create_layout.addLayout(out_layout)
        
        self.create_btn = QPushButton("创建压缩包")
        self.create_btn.clicked.connect(self.create_archive)
        create_layout.addWidget(self.create_btn)
        
        self.layout.addWidget(create_group)
        
        # 解压压缩包
        extract_group = QGroupBox("解压压缩包")
        extract_layout = QVBoxLayout(extract_group)
        
        # 选择压缩包
        arch_layout = QHBoxLayout()
        self.arch_edit = QLineEdit()
        self.arch_edit.setPlaceholderText("选择要解压的压缩包...")
        arch_layout.addWidget(self.arch_edit)
        
        self.arch_btn = QPushButton("浏览...")
        self.arch_btn.clicked.connect(self.browse_archive)
        arch_layout.addWidget(self.arch_btn)
        extract_layout.addLayout(arch_layout)
        
        # 解压路径
        ex_path_layout = QHBoxLayout()
        self.ex_path_edit = QLineEdit()
        self.ex_path_edit.setPlaceholderText("解压到...")
        ex_path_layout.addWidget(self.ex_path_edit)
        
        self.ex_path_btn = QPushButton("浏览...")
        self.ex_path_btn.clicked.connect(self.browse_extract_path)
        ex_path_layout.addWidget(self.ex_path_btn)
        extract_layout.addLayout(ex_path_layout)
        
        self.extract_btn = QPushButton("解压")
        self.extract_btn.clicked.connect(self.extract_archive)
        extract_layout.addWidget(self.extract_btn)
        
        self.layout.addWidget(extract_group)
        
        # 关闭按钮
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
            QComboBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
        """)
    
    def browse_source(self):
        """浏览源文件"""
        path = QFileDialog.getExistingDirectory(self, "选择要压缩的目录")
        if path:
            self.file_edit.setText(path)
            # 自动设置输出路径
            self.out_edit.setText(path + ".zip")
    
    def browse_output(self):
        """浏览输出路径"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存压缩包", "", "ZIP (*.zip);;TAR.GZ (*.tar.gz);;TAR.BZ2 (*.tar.bz2)"
        )
        if path:
            self.out_edit.setText(path)
    
    def browse_archive(self):
        """浏览压缩包"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择压缩包", "", "压缩包 (*.zip *.tar.gz *.tar.bz2 *.tar)"
        )
        if path:
            self.arch_edit.setText(path)
    
    def browse_extract_path(self):
        """浏览解压路径"""
        path = QFileDialog.getExistingDirectory(self, "选择解压目录")
        if path:
            self.ex_path_edit.setText(path)
    
    def create_archive(self):
        """创建压缩包"""
        source = self.file_edit.text()
        output = self.out_edit.text()
        
        if not source or not output:
            QMessageBox.warning(self, "警告", "请选择源和输出路径")
            return
        
        if not os.path.exists(source):
            QMessageBox.warning(self, "错误", "源路径不存在")
            return
        
        try:
            fmt = self.format_combo.currentIndex()
            
            if fmt == 0:  # ZIP
                self._create_zip(source, output)
            elif fmt == 1:  # TAR.GZ
                self._create_tar(source, output, "gz")
            elif fmt == 2:  # TAR.BZ2
                self._create_tar(source, output, "bz2")
            
            QMessageBox.information(self, "成功", f"压缩包已创建: {output}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"创建失败: {e}")
    
    def _create_zip(self, source: str, output: str):
        """创建 ZIP"""
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.isdir(source):
                for root, dirs, files in os.walk(source):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, source)
                        zf.write(full, rel)
            else:
                zf.write(source, os.path.basename(source))
    
    def _create_tar(self, source: str, output: str, compression: str):
        """创建 TAR"""
        mode = f"w:{compression}"
        if not output.endswith(f".tar.{compression}"):
            output = f"{output}.tar.{compression}"
        
        with tarfile.open(output, mode) as tf:
            tf.add(source, arcname=os.path.basename(source))
    
    def extract_archive(self):
        """解压压缩包"""
        archive = self.arch_edit.text()
        output = self.ex_path_edit.text()
        
        if not archive or not output:
            QMessageBox.warning(self, "警告", "请选择压缩包和解压路径")
            return
        
        if not os.path.exists(archive):
            QMessageBox.warning(self, "错误", "压缩包不存在")
            return
        
        try:
            if archive.endswith(".zip"):
                self._extract_zip(archive, output)
            elif archive.endswith(".tar.gz") or archive.endswith(".tgz"):
                self._extract_tar(archive, output, "gz")
            elif archive.endswith(".tar.bz2"):
                self._extract_tar(archive, output, "bz2")
            elif archive.endswith(".tar"):
                self._extract_tar(archive, output, "")
            else:
                QMessageBox.warning(self, "错误", "不支持的压缩格式")
                return
            
            QMessageBox.information(self, "成功", f"已解压到: {output}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"解压失败: {e}")
    
    def _extract_zip(self, archive: str, output: str):
        """解压 ZIP"""
        with zipfile.ZipFile(archive, 'r') as zf:
            zf.extractall(output)
    
    def _extract_tar(self, archive: str, output: str, compression: str):
        """解压 TAR"""
        mode = f"r:{compression}" if compression else "r:"
        with tarfile.open(archive, mode) as tf:
            tf.extractall(output)
