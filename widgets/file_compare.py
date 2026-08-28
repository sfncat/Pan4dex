"""
Pan4dex 万格 — 文件比较工具
"""
import os
import difflib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QFileDialog, QMessageBox,
    QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt


class FileCompareDialog(QDialog):
    """文件比较对话框"""
    
    def __init__(self, file1: str = None, file2: str = None, parent=None):
        super().__init__(parent)
        
        self.file1 = file1
        self.file2 = file2
        
        self.setWindowTitle("文件比较")
        self.setMinimumSize(800, 600)
        
        self.init_ui()
        
        if self.file1 and self.file2:
            self.compare()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 文件选择区域
        file_group = QGroupBox("选择文件")
        file_layout = QHBoxLayout(file_group)
        
        # 文件1
        file1_layout = QVBoxLayout()
        self.file1_label = QLabel("文件 1:")
        file1_layout.addWidget(self.file1_label)
        
        file1_btn_layout = QHBoxLayout()
        self.file1_path = QTextEdit()
        self.file1_path.setMaximumHeight(30)
        self.file1_path.setReadOnly(True)
        if self.file1:
            self.file1_path.setPlainText(self.file1)
        file1_btn_layout.addWidget(self.file1_path)
        
        self.file1_btn = QPushButton("选择...")
        self.file1_btn.clicked.connect(lambda: self.select_file(1))
        file1_btn_layout.addWidget(self.file1_btn)
        
        file1_layout.addLayout(file1_btn_layout)
        file_layout.addLayout(file1_layout)
        
        # 文件2
        file2_layout = QVBoxLayout()
        self.file2_label = QLabel("文件 2:")
        file2_layout.addWidget(self.file2_label)
        
        file2_btn_layout = QHBoxLayout()
        self.file2_path = QTextEdit()
        self.file2_path.setMaximumHeight(30)
        self.file2_path.setReadOnly(True)
        if self.file2:
            self.file2_path.setPlainText(self.file2)
        file2_btn_layout.addWidget(self.file2_path)
        
        self.file2_btn = QPushButton("选择...")
        self.file2_btn.clicked.connect(lambda: self.select_file(2))
        file2_btn_layout.addWidget(self.file2_btn)
        
        file2_layout.addLayout(file2_btn_layout)
        file_layout.addLayout(file2_layout)
        
        self.layout.addWidget(file_group)
        
        # 比较按钮
        btn_layout = QHBoxLayout()
        self.compare_btn = QPushButton("比较")
        self.compare_btn.clicked.connect(self.compare)
        btn_layout.addWidget(self.compare_btn)
        
        btn_layout.addStretch()
        
        self.swap_btn = QPushButton("交换文件")
        self.swap_btn.clicked.connect(self.swap_files)
        btn_layout.addWidget(self.swap_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        self.layout.addLayout(btn_layout)
        
        # 比较结果区域
        result_group = QGroupBox("比较结果")
        result_layout = QVBoxLayout(result_group)
        
        # 分割器
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 文件1内容
        self.file1_content = QTextEdit()
        self.file1_content.setReadOnly(True)
        self.file1_content.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        self.splitter.addWidget(self.file1_content)
        
        # 文件2内容
        self.file2_content = QTextEdit()
        self.file2_content.setReadOnly(True)
        self.file2_content.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        self.splitter.addWidget(self.file2_content)
        
        result_layout.addWidget(self.splitter)
        self.layout.addWidget(result_group)
        
        # 差异统计
        self.diff_stats = QLabel("")
        self.layout.addWidget(self.diff_stats)
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: #2D2D2D;
                color: #CCCCCC;
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
            }
        """)
    
    def select_file(self, file_num: int):
        """选择文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"选择文件 {file_num}", "", "所有文件 (*.*)"
        )
        
        if file_path:
            if file_num == 1:
                self.file1 = file_path
                self.file1_path.setPlainText(file_path)
            else:
                self.file2 = file_path
                self.file2_path.setPlainText(file_path)
    
    def swap_files(self):
        """交换文件"""
        self.file1, self.file2 = self.file2, self.file1
        self.file1_path.setPlainText(self.file1 or "")
        self.file2_path.setPlainText(self.file2 or "")
        self.compare()
    
    def compare(self):
        """比较文件"""
        if not self.file1 or not self.file2:
            QMessageBox.warning(self, "警告", "请先选择两个文件")
            return
        
        if not os.path.exists(self.file1):
            QMessageBox.warning(self, "错误", f"文件不存在: {self.file1}")
            return
        
        if not os.path.exists(self.file2):
            QMessageBox.warning(self, "错误", f"文件不存在: {self.file2}")
            return
        
        try:
            # 读取文件内容
            with open(self.file1, 'r', encoding='utf-8', errors='replace') as f:
                content1 = f.read()
            
            with open(self.file2, 'r', encoding='utf-8', errors='replace') as f:
                content2 = f.read()
            
            # 显示内容
            self.file1_content.setPlainText(content1)
            self.file2_content.setPlainText(content2)
            
            # 计算差异
            diff = list(difflib.unified_diff(
                content1.splitlines(keepends=True),
                content2.splitlines(keepends=True),
                fromfile=os.path.basename(self.file1),
                tofile=os.path.basename(self.file2)
            ))
            
            # 高亮差异
            self.highlight_diffs(content1, content2)
            
            # 更新统计
            added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
            removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
            
            self.diff_stats.setText(
                f"差异统计: +{added} 行新增, -{removed} 行删除"
            )
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"比较失败: {e}")
    
    def highlight_diffs(self, content1: str, content2: str):
        """高亮差异"""
        # 使用简单的行比较
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()
        
        matcher = difflib.SequenceMatcher(None, lines1, lines2)
        
        # 构建带高亮的HTML
        html1_parts = []
        html2_parts = []
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for line in lines1[i1:i2]:
                    html1_parts.append(f"<pre style='margin:0;'>{self.escape_html(line)}</pre>")
                    html2_parts.append(f"<pre style='margin:0;'>{self.escape_html(line)}</pre>")
            elif tag == 'replace':
                for line in lines1[i1:i2]:
                    html1_parts.append(f"<pre style='margin:0; background-color: #3D1F1F;'>{self.escape_html(line)}</pre>")
                for line in lines2[j1:j2]:
                    html2_parts.append(f"<pre style='margin:0; background-color: #1F3D1F;'>{self.escape_html(line)}</pre>")
            elif tag == 'delete':
                for line in lines1[i1:i2]:
                    html1_parts.append(f"<pre style='margin:0; background-color: #3D1F1F;'>{self.escape_html(line)}</pre>")
            elif tag == 'insert':
                for line in lines2[j1:j2]:
                    html2_parts.append(f"<pre style='margin:0; background-color: #1F3D1F;'>{self.escape_html(line)}</pre>")
        
        self.file1_content.setHtml(''.join(html1_parts))
        self.file2_content.setHtml(''.join(html2_parts))
    
    def escape_html(self, text: str) -> str:
        """转义HTML特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))
