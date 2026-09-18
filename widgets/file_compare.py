"""
Pan4dex 万格 — 文件比较工具
"""
import os
import difflib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
    QPushButton, QTextEdit, QFileDialog, QMessageBox,
    QSplitter, QGroupBox, QComboBox, QProgressBar, QTabWidget, QApplication
)
from PyQt6.QtCore import Qt, QDateTime


class FileCompareDialog(QDialog):
    """文件比较对话框"""
    
    # 比较模式枚举
    MODE_TEXT = "text"
    MODE_BINARY = "binary"
    
    def __init__(self, file1: str = None, file2: str = None, parent=None):
        super().__init__(parent)
        
        self.file1 = file1
        self.file2 = file2
        self.compare_mode = self.MODE_TEXT  # 默认文本比较
        
        self.setWindowTitle("文件比较")
        self.setMinimumSize(900, 700)
        
        self.init_ui()
        
        if self.file1 and self.file2:
            self.compare()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 文件选择区域
        file_group = QGroupBox("选择文件")
        file_layout = QHBoxLayout(file_group)
        
        # 文件 1
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
        
        # 文件 2
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
        
        # 比较模式选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("比较模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("文本比较 (Text)", self.MODE_TEXT)
        self.mode_combo.addItem("二进制比较 (Binary)", self.MODE_BINARY)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        btn_layout.addLayout(mode_layout)
        
        self.compare_btn = QPushButton("比较")
        self.compare_btn.clicked.connect(self.compare)
        btn_layout.addWidget(self.compare_btn)
        
        btn_layout.addStretch()
        
        self.swap_btn = QPushButton("交换文件")
        self.swap_btn.clicked.connect(self.swap_files)
        btn_layout.addWidget(self.swap_btn)
        
        # 导出按钮
        self.export_btn = QPushButton("导出报告")
        self.export_btn.clicked.connect(self.export_report)
        btn_layout.addWidget(self.export_btn)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        
        self.layout.addLayout(btn_layout)
        
        # 结果区域 - 使用标签页
        result_group = QGroupBox("比较结果")
        result_layout = QVBoxLayout(result_group)
                
        self.tabs = QTabWidget()
                
        # 文本比较标签页
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
                
        # 分割器
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
                
        # 文件 1 内容
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
                
        # 文件 2 内容
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
                
        text_layout.addWidget(self.splitter)
        self.tabs.addTab(text_tab, "文本比较")
                
        # 二进制比较标签页
        binary_tab = QWidget()
        binary_layout = QVBoxLayout(binary_tab)
                
        self.binary_result = QTextEdit()
        self.binary_result.setReadOnly(True)
        self.binary_result.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        binary_layout.addWidget(self.binary_result)
        self.tabs.addTab(binary_tab, "二进制比较")
                
        result_layout.addWidget(self.tabs)
        self.layout.addWidget(result_group)
                
        # 差异统计和进度
        stats_layout = QHBoxLayout()
                
        self.diff_stats = QLabel("")
        stats_layout.addWidget(self.diff_stats)
                
        stats_layout.addStretch()
                
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        stats_layout.addWidget(self.progress)
                
        self.layout.addLayout(stats_layout)
        
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
    
    def on_mode_changed(self, index):
        """比较模式切换"""
        self.compare_mode = self.mode_combo.currentData()
        # 清空结果显示区
        self.file1_content.clear()
        self.file2_content.clear()
        self.binary_result.clear()
        self.diff_stats.setText("")
    
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
            QMessageBox.warning(self, "错误", f"文件不存在：{self.file1}")
            return
        
        if not os.path.exists(self.file2):
            QMessageBox.warning(self, "错误", f"文件不存在：{self.file2}")
            return
        
        try:
            # 显示进度条
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)  # 无限进度
            QApplication.processEvents()
            
            if self.compare_mode == self.MODE_BINARY:
                self.compare_binary()
            else:
                self.compare_text()
            
            # 隐藏进度条
            self.progress.setVisible(False)
            
        except Exception as e:
            self.progress.setVisible(False)
            QMessageBox.warning(self, "错误", f"比较失败：{e}")
    
    def compare_text(self):
        """文本比较"""
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
                f"差异统计：+{added} 行新增，-{removed} 行删除"
            )
            
        except UnicodeDecodeError:
            QMessageBox.warning(self, "警告", "无法作为文本文件打开，请尝试二进制比较")
            self.binary_result.setPlainText("⚠ 此文件包含二进制数据，无法进行文本比较")
    
    def compare_binary(self):
        """二进制比较 - 逐字节对比"""
        file1_size = os.path.getsize(self.file1)
        file2_size = os.path.getsize(self.file2)
        
        self.diff_stats.setText(f"文件大小：文件 1={self.format_size(file1_size)}, 文件 2={self.format_size(file2_size)}")
        
        # 如果大小不同，先指出
        if file1_size != file2_size:
            self.diff_stats.setText(
                f"⚠ 文件大小不同！\n"
                f"文件 1: {self.format_size(file1_size)}\n"
                f"文件 2: {self.format_size(file2_size)}\n\n"
                f"开始逐字节对比..."
            )
        
        # 逐字节比较
        differences = []
        block_size = 1024 * 1024  # 1MB 块
        total_blocks = max(1, file1_size // block_size + 1)
        
        try:
            with open(self.file1, 'rb') as f1, open(self.file2, 'rb') as f2:
                offset = 0
                for block_num in range(total_blocks):
                    if self.progress.maximum() == 0:  # 无限进度模式
                        self.progress.setValue(block_num * 100 // total_blocks)
                    
                    data1 = f1.read(block_size)
                    data2 = f2.read(block_size)
                    
                    if not data1 and not data2:
                        break
                    
                    # 比较当前块
                    for i, (b1, b2) in enumerate(zip(data1, data2)):
                        if b1 != b2:
                            abs_offset = offset + i
                            differences.append({
                                'offset': abs_offset,
                                'file1_byte': b1,
                                'file2_byte': b2,
                                'context_start': max(0, i - 16),
                                'context_end': min(len(data1), i + 16)
                            })
                    
                    # 如果一个文件更长
                    if len(data1) != len(data2):
                        longer_data = data1 if len(data1) > len(data2) else data2
                        start_offset = min(len(data1), len(data2))
                        for i, b in enumerate(longer_data[start_offset:]):
                            abs_offset = offset + start_offset + i
                            existing = data1 if len(data1) > len(data2) else data2
                            other = data2 if len(data1) > len(data2) else data1
                            b1 = existing[offset + start_offset + i] if offset + start_offset + i < len(existing) else None
                            b2 = other[offset + start_offset + i] if offset + start_offset + i < len(other) else None
                            differences.append({
                                'offset': abs_offset,
                                'file1_byte': b1,
                                'file2_byte': b2,
                                'context_start': 0,
                                'context_end': 0
                            })
                    
                    offset += block_size
                    QApplication.processEvents()  # 保持界面响应
            
            # 显示结果
            self.show_binary_results(differences, file1_size, file2_size)
            
        except Exception as e:
            raise Exception(f"二进制比较失败：{e}")
    
    def show_binary_results(self, differences, size1, size2):
        """显示二进制比较结果"""
        output = []
        output.append("=" * 80)
        output.append("二进制比较报告")
        output.append("=" * 80)
        output.append(f"文件 1: {self.file1}")
        output.append(f"文件 2: {self.file2}")
        output.append(f"文件 1 大小：{self.format_size(size1)}")
        output.append(f"文件 2 大小：{self.format_size(size2)}")
        output.append("")
        
        if not differences:
            output.append("✅ 两个文件完全相同!")
        else:
            output.append(f"❌ 发现 {len(differences)} 处差异:")
            output.append("")
            
            # 分组显示相邻的差异
            groups = self._group_differences(differences, gap_threshold=64)
            
            for idx, group in enumerate(groups, 1):
                output.append(f"--- 差异组 {idx}/{len(groups)} ---")
                output.append(f"起始偏移：0x{group['start_offset']:08X} ({group['start_offset']})")
                output.append(f"差异数量：{len(group['diffs'])} 处")
                output.append("")
                
                # 显示十六进制和 ASCII
                output.extend(self._format_hex_dump(group))
                output.append("")
        
        output.append("=" * 80)
        output.append("报告结束")
        output.append("=" * 80)
        
        result_text = "\n".join(output)
        self.binary_result.setPlainText(result_text)
        
        # 更新统计
        self.diff_stats.setText(
            f"二进制差异：{len(differences)} 处不同字节"
        )
    
    def _group_differences(self, differences, gap_threshold=64):
        """将相邻的差异分组"""
        if not differences:
            return []
        
        groups = []
        current_group = {'diffs': [differences[0]], 'start_offset': differences[0]['offset']}
        
        for diff in differences[1:]:
            if diff['offset'] - (current_group['diffs'][-1]['offset'] + 1) < gap_threshold:
                current_group['diffs'].append(diff)
            else:
                groups.append(current_group)
                current_group = {'diffs': [diff], 'start_offset': diff['offset']}
        
        groups.append(current_group)
        return groups
    
    def _format_hex_dump(self, group):
        """格式化十六进制转储"""
        lines = []
        diffs = group['diffs']
        
        # 确定显示范围
        start_offset = diffs[0]['offset'] - diffs[0]['context_start']
        end_offset = diffs[-1]['offset'] + (16 - diffs[-1]['context_start'])
        
        # 限制最大显示行数
        max_lines = 64
        if end_offset - start_offset > max_lines * 16:
            end_offset = start_offset + max_lines * 16
        
        lines.append("偏移量 (Offset)          十六进制 (Hex)                      ASCII")
        lines.append("-" * 80)
        
        offset = start_offset
        while offset < end_offset:
            # 构建该行
            hex_parts = []
            ascii_parts = []
            
            for i in range(16):
                curr_offset = offset + i
                byte_val = None
                
                # 查找这个位置是否有差异
                for diff in diffs:
                    if diff['offset'] == curr_offset:
                        byte_val = diff
                        break
                
                if byte_val:
                    # 有差异的字节用高亮标记
                    b1 = byte_val['file1_byte']
                    b2 = byte_val['file2_byte']
                    hex_str = f"{b1:02X}/{b2:02X}" if b1 is not None and b2 is not None else "??/??"
                    hex_parts.append(f"[{hex_str}]")  # 括号标记差异
                    
                    c1 = chr(b1) if b1 is not None and 32 <= b1 < 127 else '.'
                    c2 = chr(b2) if b2 is not None and 32 <= b2 < 127 else '.'
                    ascii_parts.append(f"{c1}->{c2}")
                else:
                    # 无差异的字节（从任一文件读取均可）
                    try:
                        with open(self.file1, 'rb') as f:
                            f.seek(curr_offset)
                            b = f.read(1)[0]
                    except:
                        b = 0
                    
                    hex_parts.append(f"{b:02X}")
                    ascii_parts.append(chr(b) if 32 <= b < 127 else '.')
            
            lines.append(f"0x{offset:08X}  {' '.join(hex_parts)}  {''.join(ascii_parts)}")
            offset += 16
        
        return lines
    
    def format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def export_report(self):
        """导出比较报告"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出比较报告", "", "HTML 文件 (*.html);;文本文件 (*.txt);;所有文件 (*.*)"
        )
        
        if not file_path:
            return
        
        try:
            if file_path.endswith('.html'):
                self._export_html(file_path)
            else:
                self._export_text(file_path)
            
            QMessageBox.information(self, "成功", f"报告已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导出失败：{e}")
    
    def _export_html(self, file_path: str):
        """导出为 HTML 格式"""
        html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>文件比较报告</title>
    <style>
        body { font-family: 'Consolas', monospace; padding: 20px; background-color: #1E1E1E; color: #CCCCCC; }
        h1 { color: #4CAF50; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
        .summary { background-color: #2D2D2D; padding: 15px; border-radius: 5px; margin: 20px 0; }
        pre { white-space: pre-wrap; word-wrap: break-word; margin: 5px 0; }
    </style>
</head>
<body>
<h1>📄 文件比较报告</h1>
<div class='summary'>
<p><strong>文件 1:</strong> {}</p>
<p><strong>文件 2:</strong> {}</p>
<p><strong>比较模式:</strong> {}</p>
<p><strong>生成时间:</strong> {}</p>
</div>
""".format(self.file1, self.file2, self.mode_combo.currentText(), 
           QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss'))
        
        if self.compare_mode == self.MODE_BINARY:
            html_content += "<h2>二进制比较结果</h2>\n"
            html_content += "<pre>{}</pre>".format(self.escape_html(self.binary_result.toPlainText()))
        else:
            html_content += "<h2>文本差异统计</h2>\n"
            html_content += "<p>{}</p>\n".format(self.diff_stats.text())
            html_content += "<h3>文件 1 内容</h3>\n"
            html_content += "<pre>{}</pre>\n".format(self.escape_html(self.file1_content.toPlainText()))
            html_content += "<h3>文件 2 内容</h3>\n"
            html_content += "<pre>{}</pre>\n".format(self.escape_html(self.file2_content.toPlainText()))
        
        html_content += "</body>\n</html>\n"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _export_text(self, file_path: str):
        """导出为纯文本格式"""
        text_content = []
        text_content.append("=" * 80)
        text_content.append("文件比较报告")
        text_content.append("=" * 80)
        text_content.append(f"文件 1: {self.file1}")
        text_content.append(f"文件 2: {self.file2}")
        text_content.append(f"比较模式：{self.mode_combo.currentText()}")
        text_content.append(f"生成时间：{QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}")
        text_content.append("")
        
        if self.compare_mode == self.MODE_BINARY:
            text_content.append(self.binary_result.toPlainText())
        else:
            text_content.append(f"差异统计：{self.diff_stats.text()}")
            text_content.append("")
            text_content.append("文件 1 内容:")
            text_content.append(self.file1_content.toPlainText())
            text_content.append("")
            text_content.append("文件 2 内容:")
            text_content.append(self.file2_content.toPlainText())
        
        text_content.append("")
        text_content.append("=" * 80)
        text_content.append("报告结束")
        text_content.append("=" * 80)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(text_content))
