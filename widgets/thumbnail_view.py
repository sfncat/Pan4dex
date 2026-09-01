"""
Pan4dex 万格 - 超大图标视图
"""
import os
import logging
import time
from collections import OrderedDict
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStyle, QApplication
from PyQt6.QtCore import QSize, Qt, QTimer, QRunnable, QThreadPool, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QImage, QImageReader

logger = logging.getLogger("pan4dex.thumbnail_view")

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico', '.tiff', '.tif', '.svg', '.heic', '.heif', '.avif', '.apng'}
CACHE_SIZE = 200


class ThumbnailSignals(QObject):
    loaded = pyqtSignal(str, object)


class ThumbnailLoader(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = ThumbnailSignals()
        self.setAutoDelete(True)
    
    def run(self):
        try:
            reader = QImageReader(self.path)
            if reader.canRead():
                size = reader.size()
                if size.width() > 256 or size.height() > 256:
                    reader.setScaledSize(QSize(256, 256))
                image = reader.read()
                if not image.isNull():
                    self.signals.loaded.emit(self.path, image)
        except Exception:
            pass


class ThumbnailView(QListWidget):
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
        self.setGridSize(QSize(160, 190))
        
        self.setStyleSheet("""
            QListWidget { background: transparent; border: none; padding: 10px; }
            QListWidget::item { border-radius: 6px; padding: 4px; }
            QListWidget::item:selected { background: rgba(0, 120, 215, 0.3); border: 1px solid #0078d7; }
            QListWidget::item:hover { background: rgba(0, 120, 215, 0.1); }
        """)
        
        self._current_path = None
        self._thumbnail_cache = OrderedDict()
        self._loading = set()
        
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(4)
        
        self._lazy_timer = QTimer()
        self._lazy_timer.setInterval(100)
        self._lazy_timer.timeout.connect(self._load_visible_thumbnails)
        
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.verticalScrollBar().rangeChanged.connect(self._on_scroll_changed)
        self._scroll_timer = QTimer()
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(200)
        self._scroll_timer.timeout.connect(self._start_lazy_load)
    
    def load_directory(self, path: str):
        logger.info(f"[DEBUG] load_directory START: {path}")
        t0 = time.perf_counter()
        
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._loading.clear()
        
        self.clear()
        self._current_path = path
        
        try:
            entries = []
            with os.scandir(path) as it:
                for entry in it:
                    entries.append((entry.name, entry.is_dir()))
            entries.sort(key=lambda x: x[0])
            
            for name, is_dir in entries:
                full_path = os.path.join(path, name)
                item = QListWidgetItem()
                item.setText(name)
                item.setData(Qt.ItemDataRole.UserRole, full_path)
                item.setData(Qt.ItemDataRole.UserRole + 1, is_dir)
                item.setSizeHint(QSize(160, 190))
                
                if self._is_image(full_path) and full_path in self._thumbnail_cache:
                    item.setIcon(self._thumbnail_cache[full_path])
                elif is_dir:
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                else:
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                
                self.addItem(item)
            
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(f"[DEBUG] items added: {len(entries)} in {elapsed:.1f}ms")
            
            if any(self._is_image(os.path.join(path, name)) for name, _ in entries):
                QTimer.singleShot(100, lambda: self._lazy_timer.start())
            
        except PermissionError:
            pass
        
        # 关键：强制重新布局
        self.scheduleDelayedItemsLayout()
        self.doItemsLayout()
        self.updateGeometries()
        self.viewport().update()
        self.repaint()
        QApplication.processEvents()
        
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[DEBUG] load_directory END: {elapsed:.1f}ms")
    
    def _on_scroll_changed(self):
        self._lazy_timer.stop()
        self._scroll_timer.start()
    
    def _start_lazy_load(self):
        self._lazy_timer.start()
    
    def _load_visible_thumbnails(self):
        visible_region = self.viewport().visibleRegion()
        if visible_region.isEmpty():
            return
        rect = visible_region.boundingRect()
        first = self.indexAt(rect.topLeft())
        last = self.indexAt(rect.bottomRight())
        if first.row() == -1:
            return
        start = max(0, first.row() - 5)
        end = min(last.row() + 5, self.count() - 1)
        
        loaded_count = 0
        for row in range(start, end + 1):
            item = self.item(row)
            if not item:
                continue
            full_path = item.data(Qt.ItemDataRole.UserRole)
            if not full_path or not self._is_image(full_path):
                continue
            if full_path in self._thumbnail_cache or full_path in self._loading:
                continue
            self._loading.add(full_path)
            loader = ThumbnailLoader(full_path)
            loader.signals.loaded.connect(self._on_thumbnail_loaded)
            self._thread_pool.start(loader)
            loaded_count += 1
            if loaded_count >= 4:
                break
        
        if all(not self._is_image(self.item(r).data(Qt.ItemDataRole.UserRole)) or
               self.item(r).data(Qt.ItemDataRole.UserRole) in self._thumbnail_cache or
               self.item(r).data(Qt.ItemDataRole.UserRole) in self._loading
               for r in range(self.count()) if self.item(r)):
            self._lazy_timer.stop()
    
    def _on_thumbnail_loaded(self, path, image):
        self._loading.discard(path)
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(QSize(128, 128), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        if scaled.width() > 128 or scaled.height() > 128:
            scaled = scaled.copy((scaled.width() - 128) // 2, (scaled.height() - 128) // 2, 128, 128)
        icon = QIcon(scaled)
        if len(self._thumbnail_cache) >= CACHE_SIZE:
            self._thumbnail_cache.popitem(last=False)
        self._thumbnail_cache[path] = icon
        for row in range(self.count()):
            item = self.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(icon)
                break
    
    def _is_image(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
    
    def clear(self):
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._loading.clear()
        super().clear()
    
    def closeEvent(self, event):
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._thread_pool.waitForDone(1000)
        super().closeEvent(event)
