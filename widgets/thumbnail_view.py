# -*- coding: utf-8 -*-
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

# pillow-heif 懒加载注册（只注册一次）
_heif_registered = False


def _ensure_heif_opener() -> bool:
    """注册 pillow-heif 的 HEIF 打开器，返回是否可用"""
    global _heif_registered
    if _heif_registered:
        return True
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
        _heif_registered = True
        logger.debug("pillow-heif opener registered")
        return True
    except Exception as e:
        logger.debug(f"pillow-heif not available: {e}")
        return False


def _load_with_pillow(path: str):
    """用 Pillow 解码（HEIC/HEIF 等 Qt 不支持的格式），返回 QImage 或 None"""
    try:
        from PIL import Image
        pil_img = Image.open(path)
        # 缩放到 256px，避免全分辨率 HEIC 占大量内存
        pil_img.thumbnail((256, 256), Image.LANCZOS)
        pil_img = pil_img.convert("RGBA")
        data = pil_img.tobytes("raw", "RGBA")
        qimg = QImage(
            data, pil_img.width, pil_img.height,
            pil_img.width * 4, QImage.Format.Format_RGBA8888
        )
        # copy() 让 QImage 拥有自己的数据副本，不依赖 pil_img/data 的生命周期
        return qimg.copy()
    except Exception as e:
        logger.debug(f"Pillow decode failed for {path}: {e}")
        return None


class ThumbnailSignals(QObject):
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str)


class ThumbnailLoader(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = ThumbnailSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            # 优先用 Qt 原生 QImageReader
            reader = QImageReader(self.path)
            if reader.canRead():
                size = reader.size()
                if size.isValid() and (size.width() > 256 or size.height() > 256):
                    reader.setScaledSize(QSize(256, 256))
                image = reader.read()
                if not image.isNull():
                    self.signals.loaded.emit(self.path, image)
                    return

            # Qt 解码失败，回退到 Pillow（HEIC/HEIF/AVIF 等）
            if _ensure_heif_opener():
                image = _load_with_pillow(self.path)
                if image and not image.isNull():
                    self.signals.loaded.emit(self.path, image)
                    return

            logger.debug(f"ThumbnailLoader: all decoders failed for {self.path}")
            self.signals.failed.emit(self.path)
        except Exception as e:
            logger.debug(f"ThumbnailLoader exception for {self.path}: {e}")
            self.signals.failed.emit(self.path)


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

        # 样式由全局 ThemeManager 统一管理（qdarkstyle 深色 / 自定义浅色），
        # 不在此硬编码颜色，避免主题切换时显示异常

        self._current_path = None
        self._thumbnail_cache = OrderedDict()
        self._loading = set()
        self._item_map = {}  # path -> QListWidgetItem，O(1) 查找
        
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
        
        # 停止懒加载和清空线程池
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
            # 目录优先，再按名称排序
            entries.sort(key=lambda x: (not x[1], x[0].lower()))

            self._item_map.clear()
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
                self._item_map[full_path] = item

            logger.info(f"[DEBUG] items added: {len(entries)}")

            if any(self._is_image(os.path.join(path, name)) for name, _ in entries):
                QTimer.singleShot(100, lambda: self._lazy_timer.start())

        except PermissionError:
            pass

        self.doItemsLayout()
        self.viewport().update()
        
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[DEBUG] load_directory END: {elapsed:.1f}ms, count={self.count()}")
    
    def _on_scroll_changed(self):
        self._lazy_timer.stop()
        self._scroll_timer.start()
    
    def _start_lazy_load(self):
        self._lazy_timer.start()
    
    def _load_visible_thumbnails(self):
        if not self.isVisible() or self.count() == 0:
            return
        vp_rect = self.viewport().rect()
        if vp_rect.isEmpty():
            return

        # 用 indexAt 估算首个可见项的 row，只遍历可见区域（性能关键）
        first_index = self.indexAt(vp_rect.topLeft())
        start_row = first_index.row() if first_index.isValid() else 0
        if start_row < 0:
            start_row = 0

        loaded_count = 0
        for row in range(start_row, self.count()):
            item = self.item(row)
            if not item:
                continue
            full_path = item.data(Qt.ItemDataRole.UserRole)
            if not full_path or not self._is_image(full_path):
                continue
            if full_path in self._thumbnail_cache or full_path in self._loading:
                continue
            # 用 visualItemRect 判断可见性，比 indexAt 在 IconMode 下可靠
            item_rect = self.visualItemRect(item)
            if item_rect.isValid():
                if not item_rect.intersects(vp_rect):
                    # 已超出可见区域底部，停止遍历
                    if item_rect.top() > vp_rect.bottom():
                        break
                    continue
            self._loading.add(full_path)
            loader = ThumbnailLoader(full_path)
            loader.signals.loaded.connect(self._on_thumbnail_loaded)
            loader.signals.failed.connect(self._on_thumbnail_failed)
            self._thread_pool.start(loader)
            loaded_count += 1
            if loaded_count >= 4:
                break

        # 停止条件：所有图片要么已缓存、要么加载中
        all_done = True
        for row in range(start_row, self.count()):
            it = self.item(row)
            if not it:
                continue
            p = it.data(Qt.ItemDataRole.UserRole)
            if not p or not self._is_image(p):
                continue
            item_rect = self.visualItemRect(it)
            if item_rect.isValid() and item_rect.top() > vp_rect.bottom():
                break
            if p not in self._thumbnail_cache and p not in self._loading:
                all_done = False
                break
        if all_done:
            self._lazy_timer.stop()
    
    def _on_thumbnail_loaded(self, path, image):
        self._loading.discard(path)
        # 防止用户已切换目录后旧缩略图设置到已回收的 item 上
        if not self._current_path or not path.startswith(self._current_path):
            return
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
        # 用字典 O(1) 查找，不再遍历全部 item
        item = self._item_map.get(path)
        if item:
            item.setIcon(icon)

    def _on_thumbnail_failed(self, path):
        """加载失败时清理 _loading，避免泄漏导致该路径永远不再重试"""
        self._loading.discard(path)
    
    def _is_image(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
    
    def clear(self):
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._loading.clear()
        self._item_map.clear()
        super().clear()
    
    def closeEvent(self, event):
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._thread_pool.waitForDone(1000)
        super().closeEvent(event)
