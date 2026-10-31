# -*- coding: utf-8 -*-
"""
Pan4dex 万格 - 超大图标视图
"""
import os
import json
import logging
import time
from collections import OrderedDict
from PyQt6.QtWidgets import (QAbstractItemView, QListWidget, QListWidgetItem,
                             QApplication, QStyledItemDelegate, QStyle,
                             QStyleOptionViewItem)
from PyQt6.QtCore import (QMimeData, QSize, Qt, QTimer, QUrl, QRunnable,
                          QThreadPool, QObject, pyqtSignal)
from PyQt6.QtGui import QDrag, QPixmap, QIcon, QImage, QImageReader, QFontMetrics, QFont

from core.lifecycle import call_later

logger = logging.getLogger("pan4dex.thumbnail_view")

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico', '.tiff', '.tif', '.svg', '.heic', '.heif', '.avif', '.apng'}
CACHE_SIZE = 200

# ---- 平铺模式（Windows 资源管理器「平铺」式：图标左、名称+两行附注右）----
TILE_SIZE = QSize(288, 64)          # 单个瓦片的网格尺寸
TILE_ICON = QSize(48, 48)           # 瓦片图标尺寸
PE_EXTENSIONS = {'.exe', '.dll'}    # 有版本资源可读的扩展名（瓦片第二/三行换版本+说明）


def _tile_type_text(name: str, is_dir: bool) -> str:
    """类型附注，与列表视图「类型」列同一份实现（DirStoreModel._type_text）"""
    from core.dir_model import DirStoreModel
    from types import SimpleNamespace
    return DirStoreModel._type_text(SimpleNamespace(name=name, is_dir=is_dir))


def _tile_size_text(size: int) -> str:
    """大小附注，与列表视图「大小」列同一份实现（DirStoreModel._fmt_size）"""
    from core.dir_model import DirStoreModel
    return DirStoreModel._fmt_size(size)


class TileItemDelegate(QStyledItemDelegate):
    """平铺瓦片绘制：图标在左，右侧名称加粗 + 两行小字附注。

    背景（选中/悬停）仍走样式表的 PE_PanelItemViewItem，保证与主题、
    非活动窗格灰化令牌一致；文本部分自己画，颜色取自调色板。
    """

    MARGIN = 6
    TEXT_GAP = 8  # 图标与文本的间距

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem, opt, painter, widget)

        rect = opt.rect
        isz = opt.decorationSize
        icon_x = rect.x() + self.MARGIN
        icon_y = rect.y() + (rect.height() - isz.height()) // 2
        opt.icon.paint(painter,
                       icon_x, icon_y, isz.width(), isz.height())

        tx = icon_x + isz.width() + self.TEXT_GAP
        tw = rect.right() - tx - self.MARGIN + 1
        if tw <= 0:
            return

        palette = opt.palette
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        main_color = (palette.color(palette.ColorRole.HighlightedText) if selected
                      else palette.color(palette.ColorRole.Text))
        sub_color = (palette.color(palette.ColorRole.HighlightedText) if selected
                     else palette.color(palette.ColorRole.PlaceholderText))

        name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        line2 = index.data(Qt.ItemDataRole.UserRole + 2) or ""
        line3 = index.data(Qt.ItemDataRole.UserRole + 3) or ""
        lines = [name, line2, line3]
        if not line2 and not line3:
            lines = lines[:1]           # 文件夹：只有名称，垂直居中
        n = len(lines)
        row_h = rect.height() / n
        # 逐行用 drawText(QPoint) 画：Qt 的 drawText(QRect,…) 重载在多列
        # QListView 里第 2 列起静默不渲染（2026-10-31 实测，QPoint 重载正常）
        for i, text in enumerate(lines):
            if not text:
                continue
            font = QFont(opt.font)
            font.setBold(i == 0)
            painter.setFont(font)
            painter.setPen(main_color if i == 0 else sub_color)
            fm = QFontMetrics(font)
            elided = fm.elidedText(text, Qt.TextElideMode.ElideRight,
                                   tw if i == 0 else int(tw * 0.95))
            if n == 1:
                baseline = rect.y() + (rect.height() + fm.ascent()
                                       - fm.descent()) // 2
            else:
                baseline = int(rect.y() + (i + 0.62) * row_h)
            painter.drawText(tx, baseline, elided)


class VersionInfoSignals(QObject):
    loaded = pyqtSignal(str, object)  # (path, (version, desc) 或 None)


class VersionInfoLoader(QRunnable):
    """后台读 PE 版本资源（GetFileVersionInfo，单文件毫秒级）"""

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = VersionInfoSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            from core.file_version import get_version_info
            self.signals.loaded.emit(self.path, get_version_info(self.path))
        except Exception as e:
            logger.debug(f"version info failed for {self.path}: {e}")
            self.signals.loaded.emit(self.path, None)

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
        # 与文件列表一致：Shift/Ctrl 多选 + 空白处拖拽框选 + 拖动选中项拖出。
        # 注意 setSelectionMode 必须在 setDragDropMode 之后调（Qt 会隐式改回单选）
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._drag_source_pane = None
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(160, 190))

        # 样式由全局 ThemeManager 统一管理（qdarkstyle 深色 / 自定义浅色），
        # 不在此硬编码颜色，避免主题切换时显示异常

        self._current_path = None
        self._thumbnail_cache = OrderedDict()
        self._loading = set()
        self._item_map = {}  # path -> QListWidgetItem，O(1) 查找
        # 列表筛选条件（`widgets.filter_bar.EntryFilter`）：本视图自己扫目录，
        # 所以筛选得在这条枚举路径上再过一道，否则超大图标视图与列表不一致
        self._entry_filter = None

        # 平铺模式状态（见 set_tile_mode）：同一实例切换外观，不另建控件，
        # 窗格上超大图标视图的全部接线（选中/右键/拖拽/筛选/双击）零改动复用
        self._tile_mode = False
        self._default_delegate = self.itemDelegate()
        self._tile_delegate = TileItemDelegate(self)
        self._version_cache = OrderedDict()
        self._version_loading = set()
        
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
    
    def set_entry_filter(self, entry_filter):
        """装上/摘掉筛选条件；正显示着时立即重列，藏着时等下一次 `load_directory` 自取"""
        self._entry_filter = entry_filter if (entry_filter and entry_filter.active) else None
        if self._current_path and self.isVisible():
            self.load_directory(self._current_path)

    def set_tile_mode(self, on: bool):
        """切换平铺/超大图标外观（同一实例，不换控件）。

        只改网格、图标尺寸与绘制代理；列表内容由窗格在模式切换后
        重新 load_directory 填充（附注数据只在平铺模式下写入）。
        """
        on = bool(on)
        if on == self._tile_mode:
            return
        self._tile_mode = on
        self._lazy_timer.stop()
        self._thread_pool.clear()
        if on:
            self.setItemDelegate(self._tile_delegate)
            self.setIconSize(TILE_ICON)
            self.setSpacing(4)
        else:
            self.setItemDelegate(self._default_delegate)
            self.setIconSize(QSize(128, 128))
            self.setSpacing(15)
        size = TILE_SIZE if on else QSize(160, 190)
        self.setGridSize(size)
        for i in range(self.count()):
            it = self.item(i)
            if it:
                it.setSizeHint(size)
        self.doItemsLayout()
        self.viewport().update()

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
            filt = self._entry_filter
            # 平铺模式要显示大小附注，stat 与筛选条件一样只在此需要时补
            need_stat = (bool(filt) and filt.needs_stat) or self._tile_mode
            entries = []
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        is_dir = False
                    size, mtime = -1, 0.0
                    if need_stat:
                        try:
                            st = entry.stat()
                            size = -1 if is_dir else st.st_size
                            mtime = st.st_mtime
                        except OSError:
                            size, mtime = -1, 0.0
                    if filt is not None:
                        if not filt.matches(entry.name, is_dir, size, mtime):
                            continue
                    entries.append((entry.name, is_dir, size))
            # 目录优先，再按名称排序
            entries.sort(key=lambda x: (not x[1], x[0].lower()))

            self._item_map.clear()
            for name, is_dir, size in entries:
                full_path = os.path.join(path, name)
                item = QListWidgetItem()
                item.setText(name)
                item.setData(Qt.ItemDataRole.UserRole, full_path)
                item.setData(Qt.ItemDataRole.UserRole + 1, is_dir)
                item.setSizeHint(TILE_SIZE if self._tile_mode else QSize(160, 190))

                if self._tile_mode:
                    if is_dir:
                        line2, line3 = "", ""   # 文件夹不放附注，名称居中
                    else:
                        # exe/dll 的版本+说明异步补（VersionInfoLoader），先以大小/类型兜底
                        line2 = _tile_size_text(size)
                        line3 = _tile_type_text(name, False)
                    item.setData(Qt.ItemDataRole.UserRole + 2, line2)
                    item.setData(Qt.ItemDataRole.UserRole + 3, line3)

                if self._is_image(full_path) and full_path in self._thumbnail_cache:
                    item.setIcon(self._thumbnail_cache[full_path])
                else:
                    from core.dir_model import type_icon
                    item.setIcon(type_icon(full_path, is_dir))

                self.addItem(item)
                self._item_map[full_path] = item

            logger.info(f"[DEBUG] items added: {len(entries)}")

            if self._tile_mode:
                if any(self._is_pe(os.path.join(path, name))
                       for name, _, _ in entries):
                    call_later(self, 100, self._lazy_timer.start)
            elif any(self._is_image(os.path.join(path, name)) for name, _, _ in entries):
                call_later(self, 100, self._lazy_timer.start)

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
        if self._tile_mode:
            self._load_visible_versions()
            return
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

    def _is_pe(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in PE_EXTENSIONS

    def _load_visible_versions(self):
        """平铺模式：只对可见区域内的 exe/dll 补版本资源（复用缩略图的懒加载节拍）"""
        if not self.isVisible() or self.count() == 0:
            self._lazy_timer.stop()
            return
        vp_rect = self.viewport().rect()
        if vp_rect.isEmpty():
            return

        first_index = self.indexAt(vp_rect.topLeft())
        start_row = first_index.row() if first_index.isValid() else 0
        if start_row < 0:
            start_row = 0

        started = 0
        all_done = True
        for row in range(start_row, self.count()):
            item = self.item(row)
            if not item:
                continue
            full_path = item.data(Qt.ItemDataRole.UserRole)
            if not full_path or not self._is_pe(full_path):
                continue
            item_rect = self.visualItemRect(item)
            if item_rect.isValid() and item_rect.top() > vp_rect.bottom():
                break  # 已滚出可见区底部，后面的行不用再看
            if full_path in self._version_cache or full_path in self._version_loading:
                continue
            if not item_rect.isValid() or not item_rect.intersects(vp_rect):
                continue
            all_done = False
            self._version_loading.add(full_path)
            loader = VersionInfoLoader(full_path)
            loader.signals.loaded.connect(self._on_version_loaded)
            self._thread_pool.start(loader)
            started += 1
            if started >= 8:
                break
        if all_done and started == 0:
            self._lazy_timer.stop()

    def _on_version_loaded(self, path, info):
        self._version_loading.discard(path)
        if info is None:
            return  # 无版本资源：保留大小/类型兜底附注
        if len(self._version_cache) >= CACHE_SIZE:
            self._version_cache.popitem(last=False)
        self._version_cache[path] = info
        # 防止已切换目录后旧数据写到已回收的 item 上
        if not self._current_path or not path.startswith(self._current_path):
            return
        self._apply_version_info(path, info)

    def _apply_version_info(self, path, info):
        """把 (版本号, 文件说明) 写到对应 item 的附注数据（平铺模式）"""
        item = self._item_map.get(path)
        if item is None:
            return
        ver, desc = info
        if ver:
            item.setData(Qt.ItemDataRole.UserRole + 2, ver)
        if desc:
            item.setData(Qt.ItemDataRole.UserRole + 3, desc)
        self.viewport().update()
    
    def selected_paths(self) -> list:
        """选中项路径（按视觉行序），供窗格的复制/删除/右键菜单统一读取"""
        items = sorted(self.selectedItems(), key=self.row)
        return [p for p in (it.data(Qt.ItemDataRole.UserRole) for it in items) if p]

    def set_drag_source_pane(self, pane):
        """注入窗格引用：拖拽负载要带 source_pane_id，动作由接收端按落点算"""
        self._drag_source_pane = pane

    def _drag_mime_data(self):
        """与列表视图同一套负载：源窗格 + 全部选中项，另附 URL 供外部应用接收"""
        if self._drag_source_pane is None:
            return None
        paths = self.selected_paths()
        if not paths:
            return None
        mime = QMimeData()
        mime.setData(
            "application/x-pan4dex-drag",
            json.dumps({
                "source_pane_id": self._drag_source_pane.pane_id,
                "files": paths,
            }).encode(),
        )
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        return mime

    def startDrag(self, supportedActions):
        mime = self._drag_mime_data()
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    # 拖放事件统一转交 Pane（与 FileListTreeView 同一套逻辑），
    # 这样图标视图也能接外部拖入、以及拖到文件夹图标上
    def dragEnterEvent(self, event):
        logger.info("[drag] 图标视图 enter formats=%s",
                    event.mimeData().formats())
        if self._drag_source_pane is None:
            event.ignore()
            return
        self._drag_source_pane.dragEnterEvent(event)

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasFormat("application/x-pan4dex-drag"):
            event.acceptProposedAction()
        else:
            logger.info("[drag] 图标视图 move 忽略：mime 不含文件")
            event.ignore()

    def dragLeaveEvent(self, event):
        logger.info("[drag] 图标视图 leave")
        if self._drag_source_pane is not None:
            self._drag_source_pane._apply_drag_highlight(False)
        event.accept()

    def dropEvent(self, event):
        logger.info("[drag] 图标视图 drop pos=%s", event.position())
        if self._drag_source_pane is None:
            event.ignore()
            return
        self._drag_source_pane.dropEvent(event, view=self)

    def _is_image(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
    
    def clear(self):
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._loading.clear()
        self._version_loading.clear()
        self._item_map.clear()
        super().clear()
    
    def closeEvent(self, event):
        self._lazy_timer.stop()
        self._thread_pool.clear()
        self._thread_pool.waitForDone(1000)
        super().closeEvent(event)
