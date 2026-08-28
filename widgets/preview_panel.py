"""
Pan4dex 万格 — 快速预览面板
"""
import os
import mimetypes
from PyQt6.QtWidgets import (
    QDockWidget, QTextEdit, QLabel, QWidget, 
    QVBoxLayout, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage


class PreviewPanel(QDockWidget):
    """快速预览面板"""
    
    def __init__(self, parent=None):
        super().__init__("预览", parent)
        
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | 
            Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.setMinimumWidth(200)
        self.setMaximumWidth(400)
        
        # 创建主容器
        self.main_widget = QWidget()
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        
        # 文件信息标签
        self.info_label = QLabel("选择一个文件以预览")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("""
            QLabel {
                color: #CCCCCC;
                font-size: 12px;
                padding: 5px;
            }
        """)
        self.layout.addWidget(self.info_label)
        
        # 分隔线
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.HLine)
        self.separator.setStyleSheet("background-color: #404040;")
        self.separator.setMaximumHeight(1)
        self.layout.addWidget(self.separator)
        
        # 预览区域
        self.preview_area = QScrollArea()
        self.preview_area.setWidgetResizable(True)
        self.preview_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
        """)
        
        # 预览内容标签
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #1E1E1E;
                color: #CCCCCC;
            }
        """)
        self.preview_area.setWidget(self.preview_label)
        
        self.layout.addWidget(self.preview_area)
        
        # 文本预览（默认隐藏）
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setVisible(False)
        self.text_preview.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        self.layout.addWidget(self.text_preview)
        
        self.setWidget(self.main_widget)
        
        # 设置样式
        self.setStyleSheet("""
            QDockWidget {
                color: #CCCCCC;
                titlebar-close-icon: url(close.png);
            }
            QDockWidget::title {
                background-color: #2D2D2D;
                padding: 5px;
                border-bottom: 1px solid #404040;
            }
        """)
    
    def preview_file(self, file_path: str):
        """预览文件"""
        if not os.path.exists(file_path):
            self.clear_preview()
            return
        
        # 更新文件信息
        self.update_file_info(file_path)
        
        # 根据文件类型选择预览方式
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type and mime_type.startswith("text/"):
            self.preview_text_file(file_path)
        elif mime_type and mime_type.startswith("image/"):
            self.preview_image_file(file_path)
        else:
            self.preview_generic_file(file_path)
    
    def update_file_info(self, file_path: str):
        """更新文件信息"""
        try:
            stat = os.stat(file_path)
            size = self.format_size(stat.st_size)
            modified = self.format_time(stat.st_mtime)
            
            info = (
                f"<b>{os.path.basename(file_path)}</b><br>"
                f"大小: {size}<br>"
                f"修改时间: {modified}<br>"
                f"类型: {mimetypes.guess_type(file_path)[0] or '未知'}"
            )
            self.info_label.setText(info)
        except Exception as e:
            self.info_label.setText(f"无法获取文件信息: {e}")
    
    def preview_text_file(self, file_path: str):
        """预览文本文件"""
        try:
            # 限制预览文件大小（100KB）
            if os.path.getsize(file_path) > 100 * 1024:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(100 * 1024)
                    self.text_preview.setPlainText("文件过大，仅显示前 100KB...\n" + content)
            else:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.text_preview.setPlainText(f.read())
            
            self.text_preview.show()
            self.preview_label.hide()
            self.preview_area.hide()
        except Exception as e:
            self.text_preview.setPlainText(f"无法预览文件: {e}")
            self.text_preview.show()
            self.preview_label.hide()
            self.preview_area.hide()
    
    def preview_image_file(self, file_path: str):
        """预览图片文件"""
        try:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                self.preview_label.setText("无法加载图片")
                self.preview_label.setVisible(True)
                self.text_preview.setVisible(False)
                return
            
            # 缩放图片以适应预览区域
            max_width = self.preview_area.width() - 20
            max_height = self.preview_area.height() - 20
            
            if pixmap.width() > max_width or pixmap.height() > max_height:
                pixmap = pixmap.scaled(
                    max_width, max_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setVisible(True)
            self.text_preview.setVisible(False)
        except Exception as e:
            self.preview_label.setText(f"无法预览图片: {e}")
            self.preview_label.setVisible(True)
            self.text_preview.setVisible(False)
    
    def preview_generic_file(self, file_path: str):
        """预览通用文件（显示文件信息）"""
        self.preview_label.setText(
            f"文件类型: {mimetypes.guess_type(file_path)[0] or '未知'}\n"
            f"大小: {self.format_size(os.path.getsize(file_path))}\n\n"
            f"此文件类型不支持预览"
        )
        self.preview_label.setVisible(True)
        self.text_preview.setVisible(False)
    
    def clear_preview(self):
        """清除预览"""
        self.info_label.setText("选择一个文件以预览")
        self.preview_label.clear()
        self.text_preview.clear()
    
    def format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    def format_time(self, timestamp: float) -> str:
        """格式化时间戳"""
        from datetime import datetime
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
