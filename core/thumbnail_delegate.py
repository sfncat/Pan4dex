"""
Pan4dex 万格 - 图片缩略图委托（安全版本）
用于超大图标模式下的图片预览
"""
import logging
import os
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QPainter, QPixmap, QFont

logger = logging.getLogger("pan4dex.thumbnail")


class ThumbnailDelegate(QStyledItemDelegate):
    """图片缩略图委托 - 为图片文件显示预览缩略图（带异常保护）"""

    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico',
        '.tiff', '.tif', '.svg', '.heic', '.heif', '.raw', '.cr2',
        '.nef', '.arw', '.dng', '.psd', '.avif', '.apng'
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumbnail_cache = {}  # path -> QPixmap
        self._max_cache_size = 100
        self._paint_error_count = 0

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """绘制项目（带异常保护）"""
        try:
            painter.save()

            # 获取文件路径
            model = index.model()
            if model is None:
                painter.restore()
                return

            file_path = ""
            try:
                file_path = model.filePath(index)
            except:
                pass

            # 判断是否为图片
            if file_path and self._is_image(file_path):
                self._paint_thumbnail(painter, option, index, file_path)
            else:
                # 非图片文件，使用默认绘制
                super().paint(painter, option, index)

            painter.restore()
        except Exception as e:
            self._paint_error_count += 1
            if self._paint_error_count <= 3:
                logger.error(f"ThumbnailDelegate paint error: {e}")
            # 出错时使用默认绘制
            try:
                super().paint(painter, option, index)
            except:
                pass

    def _paint_thumbnail(self, painter: QPainter, option: QStyleOptionViewItem, index, file_path: str):
        """绘制图片缩略图"""
        icon_size = 128
        padding = 8
        text_height = 30

        # 绘制背景
        try:
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
                painter.setPen(option.palette.highlightedText().color())
            elif option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, option.palette.button())
                painter.setPen(option.palette.buttonText().color())
            else:
                painter.fillRect(option.rect, option.palette.base())
                painter.setPen(option.palette.text().color())
        except:
            pass

        # 获取或生成缩略图
        try:
            pixmap = self._get_thumbnail(file_path)
        except:
            pixmap = None

        # 计算缩略图居中位置
        x = option.rect.x() + (option.rect.width() - icon_size) // 2
        y = option.rect.y() + padding

        if pixmap and not pixmap.isNull():
            try:
                # 保持宽高比缩放
                scaled = pixmap.scaled(
                    QSize(icon_size, icon_size),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                # 居中绘制
                px = x + (icon_size - scaled.width()) // 2
                py = y + (icon_size - scaled.height()) // 2
                painter.drawPixmap(px, py, scaled)
            except:
                pass
        else:
            # 如果图片加载失败，使用默认图标
            try:
                icon = index.data(Qt.ItemDataRole.DecorationRole)
                if icon and not icon.isNull():
                    icon.paint(painter, QRect(x, y, icon_size, icon_size))
            except:
                pass

        # 绘制文件名
        try:
            file_name = index.data(Qt.ItemDataRole.DisplayRole)
            if file_name:
                text_rect = QRect(
                    option.rect.x(),
                    y + icon_size + 4,
                    option.rect.width(),
                    text_height
                )
                font = QFont()
                font.setPointSize(8)
                painter.setFont(font)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    file_name
                )
        except:
            pass

    def _get_thumbnail(self, file_path: str):
        """获取缩略图（带缓存）"""
        if not file_path or not os.path.exists(file_path):
            return None
            
        if file_path in self._thumbnail_cache:
            return self._thumbnail_cache[file_path]

        # 缓存过大时清理
        if len(self._thumbnail_cache) >= self._max_cache_size:
            # 清理一半缓存
            keys = list(self._thumbnail_cache.keys())[:self._max_cache_size // 2]
            for key in keys:
                del self._thumbnail_cache[key]

        try:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                return None

            # 缓存缩略图
            self._thumbnail_cache[file_path] = pixmap
            return pixmap
        except:
            return None

    def _is_image(self, file_path: str) -> bool:
        """判断文件是否为图片"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            return ext in self.IMAGE_EXTENSIONS
        except:
            return False

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        """返回项目大小"""
        return QSize(144, 170)  # 宽度, 高度(128 + padding + text)

    def clear_cache(self):
        """清理缩略图缓存"""
        self._thumbnail_cache.clear()
