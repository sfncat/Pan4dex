"""
Pan4dex 万格 - 超大图标视图（独立于 QTreeView，安全处理大图标）
使用 QListWidget IconMode 实现平铺 + 图片预览
分块加载，避免阻塞 UI
"""
import os
import logging
import time
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStyle, QApplication
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QImage, QImageReader

logger = logging.getLogger("pan4dex.thumbnail_view")

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico',
    '.tiff', '.tif', '.svg', '.heic', '.heif', '.avif', '.apng'
}


class ThumbnailView(QListWidget):
    """安全的超大图标视图 - 使用 QListWidget 而非 QTreeView"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(128, 128))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSpacing(15)
        self.setWordWrap(True)
        self.setWrapping(True)
        self.setMovement(QListWidget.Movement.Static)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        
        # 设置网格大小（图标 + 文字）
        self.setGridSize(QSize(160, 190))
        
        # 设置样式
        self.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                padding: 10px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item:selected {
                background: rgba(0, 120, 215, 0.3);
                border: 1px solid #0078d7;
            }
            QListWidget::item:hover {
                background: rgba(0, 120, 215, 0.1);
            }
        """)
        
        self._current_path = None
        self._thumbnail_cache = {}  # path -> QIcon
        self._pending_thumbnails = []  # (row, full_path)
        self._thumbnail_timer = QTimer()
        self._thumbnail_timer.setInterval(50)
        self._thumbnail_timer.timeout.connect(self._load_thumbnail_batch)
    
    def load_directory(self, path: str):
        """加载目录内容（分块加载，避免阻塞 UI）"""
        logger.info(f"[DEBUG] load_directory START: {path}")
        t0 = time.perf_counter()
        
        self.clear()
        self._current_path = path
        
        # 禁用更新，避免闪烁
        self.setUpdatesEnabled(False)
        
        try:
            # 快速扫描目录
            entries = []
            with os.scandir(path) as it:
                for entry in it:
                    entries.append((entry.name, entry.is_dir()))
            
            entries.sort(key=lambda x: x[0])
            logger.info(f"[DEBUG] scan done: {len(entries)} entries in {(time.perf_counter()-t0)*1000:.1f}ms")
            
            # 添加所有项目（不带图片图标）
            self._pending_thumbnails = []
            for name, is_dir in entries:
                full_path = os.path.join(path, name)
                
                item = QListWidgetItem()
                item.setText(name)
                item.setData(Qt.ItemDataRole.UserRole, full_path)
                item.setData(Qt.ItemDataRole.UserRole + 1, is_dir)
                item.setSizeHint(QSize(160, 190))
                
                if is_dir:
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                elif self._is_image(full_path):
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                    self._pending_thumbnails.append((self.count(), full_path))
                else:
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                
                self.addItem(item)
            
            self.setUpdatesEnabled(True)
            
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(f"[DEBUG] items added: {len(entries)} in {elapsed:.1f}ms")
            
            # 启动缩略图加载定时器
            if self._pending_thumbnails:
                logger.info(f"[DEBUG] starting thumbnail timer for {len(self._pending_thumbnails)} images")
                self._thumbnail_timer.start()
            
        except PermissionError:
            self.setUpdatesEnabled(True)
        
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[DEBUG] load_directory END: {elapsed:.1f}ms")
    
    def _load_thumbnail_batch(self):
        """加载一批缩略图（每次只加载少量，避免阻塞）"""
        if not self._pending_thumbnails:
            self._thumbnail_timer.stop()
            logger.info(f"[DEBUG] all thumbnails loaded")
            return
        
        # 每次只加载 3 张图片
        batch = self._pending_thumbnails[:3]
        self._pending_thumbnails = self._pending_thumbnails[3:]
        
        for row, full_path in batch:
            try:
                if full_path in self._thumbnail_cache:
                    icon = self._thumbnail_cache[full_path]
                else:
                    icon = self._load_image_icon(full_path)
                    self._thumbnail_cache[full_path] = icon
                
                item = self.item(row)
                if item and not icon.isNull():
                    item.setIcon(icon)
            except Exception as e:
                logger.debug(f"Thumbnail error: {e}")
        
        # 处理事件，保持 UI 响应
        QApplication.processEvents()
    
    def _is_image(self, path: str) -> bool:
        """判断是否为图片文件"""
        ext = os.path.splitext(path)[1].lower()
        return ext in IMAGE_EXTENSIONS
    
    def _load_image_icon(self, path: str) -> QIcon:
        """加载图片图标"""
        try:
            reader = QImageReader(path)
            if reader.canRead():
                image = reader.read()
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(
                            QSize(128, 128),
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        if scaled.width() > 128 or scaled.height() > 128:
                            x = (scaled.width() - 128) // 2
                            y = (scaled.height() - 128) // 2
                            scaled = scaled.copy(x, y, 128, 128)
                        return QIcon(scaled)
        except Exception:
            pass
        return QIcon()
    
    def clear(self):
        """清空内容"""
        if self._thumbnail_timer.isActive():
            self._thumbnail_timer.stop()
        self._pending_thumbnails.clear()
        super().clear()
