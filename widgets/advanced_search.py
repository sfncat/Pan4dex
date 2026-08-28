"""
Pan4dex 万格 — 高级搜索工具
"""
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QComboBox, QCheckBox, QSpinBox, QGroupBox,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class SearchWorker(QThread):
    """搜索工作线程"""
    result = pyqtSignal(str, str, int)  # path, size, modified
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(int)  # total found
    
    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self._stop = False
    
    def run(self):
        found = 0
        search_dir = self.params.get('directory', '')
        pattern = self.params.get('pattern', '')
        use_regex = self.params.get('use_regex', False)
        case_sensitive = self.params.get('case_sensitive', False)
        file_types = self.params.get('file_types', [])
        min_size = self.params.get('min_size', 0)
        max_size = self.params.get('max_size', 0)
        content_search = self.params.get('content', '')
        
        if not search_dir or not os.path.isdir(search_dir):
            self.finished.emit(0)
            return
        
        # 编译正则
        flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            try:
                regex = re.compile(pattern, flags)
            except re.error:
                self.finished.emit(0)
                return
        else:
            regex = re.compile(re.escape(pattern), flags)
        
        for root, dirs, files in os.walk(search_dir):
            if self._stop:
                break
            
            for filename in files:
                if self._stop:
                    break
                
                # 文件名匹配
                if not regex.search(filename):
                    continue
                
                filepath = os.path.join(root, filename)
                
                try:
                    stat = os.stat(filepath)
                    size = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    continue
                
                # 大小筛选
                if min_size > 0 and size < min_size:
                    continue
                if max_size > 0 and size > max_size:
                    continue
                
                # 扩展名筛选
                if file_types:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in file_types:
                        continue
                
                # 内容搜索
                if content_search:
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(1024 * 1024)  # 只读前 1MB
                            if content_search not in content:
                                continue
                    except:
                        continue
                
                found += 1
                self.result.emit(filepath, self.format_size(size), mtime)
        
        self.finished.emit(found)
    
    def stop(self):
        self._stop = True
    
    def format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class AdvancedSearchDialog(QDialog):
    """高级搜索对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("高级搜索")
        self.setMinimumSize(700, 500)
        
        self.worker = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 搜索条件
        cond_group = QGroupBox("搜索条件")
        cond_layout = QVBoxLayout(cond_group)
        
        # 搜索目录
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("搜索目录:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("输入搜索目录路径...")
        dir_layout.addWidget(self.dir_edit)
        
        self.dir_btn = QPushButton("浏览...")
        self.dir_btn.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.dir_btn)
        cond_layout.addLayout(dir_layout)
        
        # 文件名模式
        pattern_layout = QHBoxLayout()
        pattern_layout.addWidget(QLabel("文件名:"))
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("输入文件名模式，如: *.txt 或 report*")
        pattern_layout.addWidget(self.pattern_edit)
        cond_layout.addLayout(pattern_layout)
        
        # 选项
        opt_layout = QHBoxLayout()
        
        self.regex_check = QCheckBox("正则表达式")
        opt_layout.addWidget(self.regex_check)
        
        self.case_check = QCheckBox("区分大小写")
        opt_layout.addWidget(self.case_check)
        
        opt_layout.addStretch()
        
        cond_layout.addLayout(opt_layout)
        
        # 文件类型
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("文件类型:"))
        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText("扩展名，如: .txt,.py,.md（留空为所有类型）")
        type_layout.addWidget(self.type_edit)
        cond_layout.addLayout(type_layout)
        
        # 大小范围
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("大小范围:"))
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(0, 99999)
        self.min_size_spin.setSpecialValueText("最小")
        size_layout.addWidget(self.min_size_spin)
        size_layout.addWidget(QLabel("-"))
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(0, 99999)
        self.max_size_spin.setSpecialValueText("最大")
        size_layout.addWidget(self.max_size_spin)
        self.size_unit = QComboBox()
        self.size_unit.addItems(["KB", "MB", "GB"])
        size_layout.addWidget(self.size_unit)
        size_layout.addStretch()
        cond_layout.addLayout(size_layout)
        
        # 内容搜索
        content_layout = QHBoxLayout()
        content_layout.addWidget(QLabel("包含内容:"))
        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText("文件内容包含的文本（可选）")
        content_layout.addWidget(self.content_edit)
        cond_layout.addLayout(content_layout)
        
        self.layout.addWidget(cond_group)
        
        # 搜索按钮
        btn_layout = QHBoxLayout()
        self.search_btn = QPushButton("开始搜索")
        self.search_btn.clicked.connect(self.start_search)
        btn_layout.addWidget(self.search_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_search)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        
        btn_layout.addStretch()
        
        self.clear_btn = QPushButton("清除结果")
        self.clear_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(self.clear_btn)
        
        self.layout.addLayout(btn_layout)
        
        # 结果列表
        result_group = QGroupBox("搜索结果")
        result_layout = QVBoxLayout(result_group)
        
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["文件路径", "大小", "修改时间"])
        self.result_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        result_layout.addWidget(self.result_tree)
        
        self.layout.addWidget(result_group)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        self.layout.addWidget(self.status_label)
        
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
            QTreeWidget { background-color: #1E1E1E; color: #CCCCCC; border: none; }
            QTreeWidget::item:hover { background-color: #2A2A2A; }
            QTreeWidget::item:selected { background-color: #2196F3; }
            QCheckBox { color: #CCCCCC; }
            QSpinBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
            QComboBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
        """)
    
    def browse_dir(self):
        """浏览目录"""
        path = QFileDialog.getExistingDirectory(self, "选择搜索目录")
        if path:
            self.dir_edit.setText(path)
    
    def start_search(self):
        """开始搜索"""
        directory = self.dir_edit.text()
        pattern = self.pattern_edit.text()
        
        if not directory:
            QMessageBox.warning(self, "警告", "请输入搜索目录")
            return
        
        if not pattern:
            QMessageBox.warning(self, "警告", "请输入搜索模式")
            return
        
        if not os.path.isdir(directory):
            QMessageBox.warning(self, "错误", "目录不存在")
            return
        
        # 解析文件类型
        type_text = self.type_edit.text().strip()
        file_types = []
        if type_text:
            file_types = [t.strip() if t.strip().startswith('.') else f".{t.strip()}" for t in type_text.split(",")]
        
        # 计算大小范围
        min_size = self.min_size_spin.value()
        max_size = self.max_size_spin.value()
        unit = self.size_unit.currentIndex()
        multipliers = [1024, 1024*1024, 1024*1024*1024]
        multiplier = multipliers[unit]
        
        if min_size > 0:
            min_size *= multiplier
        if max_size > 0:
            max_size *= multiplier
        
        params = {
            'directory': directory,
            'pattern': pattern,
            'use_regex': self.regex_check.isChecked(),
            'case_sensitive': self.case_check.isChecked(),
            'file_types': file_types,
            'min_size': min_size,
            'max_size': max_size,
            'content': self.content_edit.text()
        }
        
        self.result_tree.clear()
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("搜索中...")
        
        self.worker = SearchWorker(params)
        self.worker.result.connect(self.on_result)
        self.worker.finished.connect(self.on_search_finished)
        self.worker.start()
    
    def stop_search(self):
        """停止搜索"""
        if self.worker:
            self.worker.stop()
    
    def on_result(self, path: str, size: str, mtime: int):
        """搜索结果"""
        from datetime import datetime
        time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        item = QTreeWidgetItem([path, size, time_str])
        self.result_tree.addTopLevelItem(item)
    
    def on_search_finished(self, total: int):
        """搜索完成"""
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"搜索完成，共找到 {total} 个文件")
    
    def clear_results(self):
        """清除结果"""
        self.result_tree.clear()
        self.status_label.setText("就绪")
    
    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击打开文件所在目录"""
        path = item.text(0)
        if os.path.exists(path):
            import subprocess
            import sys
            if sys.platform == "win32":
                subprocess.Popen(f'explorer /select,"{path}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
