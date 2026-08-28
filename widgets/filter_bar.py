"""
Pan4dex 万格 — 筛选栏
"""
import os
import re
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QLabel,
    QComboBox, QCompleter
)
from PyQt6.QtCore import Qt, pyqtSignal, QSortFilterProxyModel, QRegularExpression


class FilterBar(QWidget):
    """筛选栏"""
    
    filter_changed = pyqtSignal(str)  # 筛选条件变化信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(5)
        
        # 筛选标签
        self.filter_label = QLabel("筛选:")
        self.layout.addWidget(self.filter_label)
        
        # 筛选输入框
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("输入筛选条件，如: *.txt,*.py")
        self.filter_edit.returnPressed.connect(self.apply_filter)
        self.filter_edit.textChanged.connect(self.on_text_changed)
        self.layout.addWidget(self.filter_edit)
        
        # 筛选类型选择
        self.filter_type = QComboBox()
        self.filter_type.addItems(["文件名", "扩展名", "正则表达式"])
        self.filter_type.currentIndexChanged.connect(self.apply_filter)
        self.layout.addWidget(self.filter_type)
        
        # 清除按钮
        self.clear_btn = QLabel("✕")
        self.clear_btn.setStyleSheet("color: #888888; cursor: pointer;")
        self.clear_btn.mousePressEvent = lambda e: self.clear_filter()
        self.layout.addWidget(self.clear_btn)
        
        # 设置样式
        self.setStyleSheet("""
            QLineEdit {
                background-color: #3D3D3D;
                color: #CCCCCC;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 2px 5px;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
            QLabel {
                color: #888888;
            }
            QComboBox {
                background-color: #3D3D3D;
                color: #CCCCCC;
                border: 1px solid #505050;
                border-radius: 3px;
                padding: 2px 5px;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
        """)
    
    def on_text_changed(self, text: str):
        """文本变化时自动应用筛选"""
        if not text:
            self.clear_filter()
    
    def apply_filter(self):
        """应用筛选"""
        pattern = self.filter_edit.text().strip()
        filter_type = self.filter_type.currentIndex()
        
        if not pattern:
            self.filter_changed.emit("")
            return
        
        # 根据筛选类型构建正则表达式
        if filter_type == 0:  # 文件名
            # 支持通配符 * 和 ?
            regex = pattern.replace(".", "\\.")
            regex = regex.replace("*", ".*")
            regex = regex.replace("?", ".")
            regex = f".*{regex}.*"
        elif filter_type == 1:  # 扩展名
            # 解析扩展名列表
            exts = [e.strip().lstrip('.') for e in pattern.split(",")]
            exts = [e for e in exts if e]
            if exts:
                regex = f".*\\.({'|'.join(exts)})$"
            else:
                regex = ".*"
        else:  # 正则表达式
            regex = pattern
        
        self.filter_changed.emit(regex)
    
    def clear_filter(self):
        """清除筛选"""
        self.filter_edit.clear()
        self.filter_changed.emit("")
    
    def get_filter(self) -> str:
        """获取当前筛选条件"""
        return self.filter_edit.text().strip()


class FilterProxyModel(QSortFilterProxyModel):
    """筛选代理模型"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_regex = ""
    
    def set_filter(self, regex: str):
        """设置筛选正则"""
        self._filter_regex = regex
        self.invalidateFilter()
    
    def filterAcceptsRow(self, source_row, source_parent):
        """行过滤"""
        if not self._filter_regex:
            return True
        
        index = self.sourceModel().index(source_row, 0, source_parent)
        file_name = self.sourceModel().fileName(index)
        
        try:
            pattern = QRegularExpression(self._filter_regex)
            match = pattern.match(file_name)
            return match.hasMatch()
        except:
            return True
