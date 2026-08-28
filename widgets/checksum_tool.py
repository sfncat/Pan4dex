"""
Pan4dex 万格 — 校验和工具
"""
import os
import hashlib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QComboBox, QTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar,
    QTabWidget, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class ChecksumWorker(QThread):
    """校验和计算工作线程"""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)
    
    def __init__(self, files: list[str], algorithm: str):
        super().__init__()
        self.files = files
        self.algorithm = algorithm
    
    def run(self):
        """执行计算"""
        results = {}
        total = len(self.files)
        
        for i, file_path in enumerate(self.files):
            try:
                hash_func = hashlib.new(self.algorithm)
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_func.update(chunk)
                results[file_path] = hash_func.hexdigest()
            except Exception as e:
                results[file_path] = f"错误: {e}"
            
            percent = int((i + 1) * 100 / total)
            self.progress.emit(percent, os.path.basename(file_path))
        
        self.finished.emit(results)


class ChecksumDialog(QDialog):
    """校验和对话框"""
    
    def __init__(self, files: list[str] = None, parent=None):
        super().__init__(parent)
        
        self.files = files or []
        self.results = {}
        
        self.setWindowTitle("校验和工具")
        self.setMinimumSize(600, 500)
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 标签页
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        
        # 创建校验和标签页
        self.create_tab = QWidget()
        self.init_create_tab()
        self.tab_widget.addTab(self.create_tab, "创建校验和")
        
        # 验证校验和标签页
        self.verify_tab = QWidget()
        self.init_verify_tab()
        self.tab_widget.addTab(self.verify_tab, "验证校验和")
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        # 结果区域
        result_group = QGroupBox("结果")
        result_layout = QVBoxLayout(result_group)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(150)
        result_layout.addWidget(self.result_text)
        
        self.layout.addWidget(result_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("保存到文件")
        self.save_btn.clicked.connect(self.save_results)
        btn_layout.addWidget(self.save_btn)
        
        btn_layout.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
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
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QProgressBar {
                background-color: #2D2D2D;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
            }
        """)
    
    def init_create_tab(self):
        """初始化创建标签页"""
        layout = QVBoxLayout(self.create_tab)
        
        # 算法选择
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("算法:"))
        
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(["md5", "sha1", "sha256", "sha512"])
        algo_layout.addWidget(self.algo_combo)
        
        algo_layout.addStretch()
        
        self.add_file_btn = QPushButton("添加文件")
        self.add_file_btn.clicked.connect(self.add_files)
        algo_layout.addWidget(self.add_file_btn)
        
        self.add_folder_btn = QPushButton("添加目录")
        self.add_folder_btn.clicked.connect(self.add_folder)
        algo_layout.addWidget(self.add_folder_btn)
        
        layout.addLayout(algo_layout)
        
        # 文件列表
        self.file_list = QTextEdit()
        self.file_list.setReadOnly(True)
        self.file_list.setMaximumHeight(100)
        self.file_list.setPlaceholderText("要计算校验和的文件...")
        layout.addWidget(self.file_list)
        
        # 计算按钮
        self.calc_btn = QPushButton("计算校验和")
        self.calc_btn.clicked.connect(self.calculate)
        layout.addWidget(self.calc_btn)
        
        layout.addStretch()
    
    def init_verify_tab(self):
        """初始化验证标签页"""
        layout = QVBoxLayout(self.verify_tab)
        
        # 校验和文件输入
        layout.addWidget(QLabel("校验和文件（.md5/.sha256）或粘贴校验和："))
        
        self.verify_text = QTextEdit()
        self.verify_text.setPlaceholderText(
            "格式: <校验和>  <文件名>\n"
            "例如: d41d8cd98f00b204e9800998ecf8427e  example.txt"
        )
        self.verify_text.setMaximumHeight(100)
        layout.addWidget(self.verify_text)
        
        # 选择文件
        verify_btn_layout = QHBoxLayout()
        
        self.select_verify_file_btn = QPushButton("选择校验和文件")
        self.select_verify_file_btn.clicked.connect(self.select_verify_file)
        verify_btn_layout.addWidget(self.select_verify_file_btn)
        
        verify_btn_layout.addStretch()
        
        self.verify_btn = QPushButton("验证")
        self.verify_btn.clicked.connect(self.verify)
        verify_btn_layout.addWidget(self.verify_btn)
        
        layout.addLayout(verify_btn_layout)
        
        layout.addStretch()
    
    def add_files(self):
        """添加文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "", "所有文件 (*.*)"
        )
        
        if files:
            self.files.extend(files)
            self.update_file_list()
    
    def add_folder(self):
        """添加目录"""
        folder = QFileDialog.getExistingDirectory(self, "选择目录")
        
        if folder:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    self.files.append(os.path.join(root, f))
            
            self.update_file_list()
    
    def update_file_list(self):
        """更新文件列表"""
        self.file_list.clear()
        for f in self.files:
            self.file_list.append(os.path.basename(f))
    
    def calculate(self):
        """计算校验和"""
        if not self.files:
            QMessageBox.warning(self, "警告", "请先添加文件")
            return
        
        algorithm = self.algo_combo.currentText()
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.calc_btn.setEnabled(False)
        
        self.worker = ChecksumWorker(self.files, algorithm)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_calculation_finished)
        self.worker.start()
    
    def on_progress(self, percent: int, filename: str):
        """进度更新"""
        self.progress_bar.setValue(percent)
        self.result_text.setPlainText(f"正在计算: {filename}...")
    
    def on_calculation_finished(self, results: dict):
        """计算完成"""
        self.results = results
        self.progress_bar.setVisible(False)
        self.calc_btn.setEnabled(True)
        
        # 显示结果
        text = ""
        for file_path, checksum in results.items():
            text += f"{checksum}  {os.path.basename(file_path)}\n"
        
        self.result_text.setPlainText(text)
    
    def verify(self):
        """验证校验和"""
        text = self.verify_text.toPlainText().strip()
        
        if not text:
            QMessageBox.warning(self, "警告", "请输入校验和")
            return
        
        # 解析校验和
        lines = text.split('\n')
        results = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                expected_checksum = parts[0].lower()
                filename = parts[1]
                
                # 查找文件
                file_path = None
                for f in self.files:
                    if os.path.basename(f) == filename:
                        file_path = f
                        break
                
                if file_path and os.path.exists(file_path):
                    # 计算实际校验和
                    algo = self.detect_algorithm(expected_checksum)
                    hash_func = hashlib.new(algo)
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_func.update(chunk)
                    actual_checksum = hash_func.hexdigest()
                    
                    if actual_checksum == expected_checksum:
                        results.append(f"✓ {filename}: 校验通过")
                    else:
                        results.append(f"✗ {filename}: 校验失败 (期望: {expected_checksum}, 实际: {actual_checksum})")
                else:
                    results.append(f"? {filename}: 文件未找到")
        
        self.result_text.setPlainText('\n'.join(results) if results else "没有可验证的校验和")
    
    def detect_algorithm(self, checksum: str) -> str:
        """根据校验和长度检测算法"""
        length = len(checksum)
        if length == 32:
            return "md5"
        elif length == 40:
            return "sha1"
        elif length == 64:
            return "sha256"
        elif length == 128:
            return "sha512"
        return "sha256"
    
    def select_verify_file(self):
        """选择校验和文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择校验和文件", "", "校验和文件 (*.md5 *.sha1 *.sha256 *.sha512);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.verify_text.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法读取文件: {e}")
    
    def save_results(self):
        """保存结果到文件"""
        if not self.results:
            QMessageBox.warning(self, "警告", "没有可保存的结果")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存校验和", "", "校验和文件 (*.md5 *.sha256);;文本文件 (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    for file_path_orig, checksum in self.results.items():
                        f.write(f"{checksum}  {os.path.basename(file_path_orig)}\n")
                
                QMessageBox.information(self, "保存成功", f"校验和已保存到: {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "保存失败", str(e))
