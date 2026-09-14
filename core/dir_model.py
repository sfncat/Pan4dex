# -*- coding: utf-8 -*-
"""
Pan4dex 万格 — DirStoreModel：以"当前目录"为单位的扁平异步文件模型

设计目标（第二阶段根治 SMB 性能）：
- 一次枚举一个目录，杜绝 QFileSystemModel 在 SMB 上的逐项 stat 与 watcher 轮询
- 后台线程枚举（QThreadPool），主线程零阻塞；未加载完成时 rowCount=0 并发 loading 信号
- TTL 缓存 + 定向失效：应用内操作后只失效涉及的目录，F5 只重扫当前目录
- 提供 QFileSystemModel 兼容的角色/接口，可挂在 PaneSortProxyModel 之下

作用范围：仅服务文件列表视图（tree_view / 缩略图）。两个侧边目录树
（pane_tree_view / tree_sidebar）本就按需展开、非瓶颈，继续使用 QFileSystemModel。
"""
import os
import logging
from datetime import datetime

from PyQt6.QtCore import (
    QAbstractItemModel, QModelIndex, Qt, QDir, QRunnable, QThreadPool,
    QObject, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QStyle

logger = logging.getLogger("pan4dex.dir_model")

# 列定义（与 QFileSystemModel 前 4 列 + ExifFileSystemModel 拍摄日期对齐）
COL_NAME, COL_SIZE, COL_TYPE, COL_DATE, COL_SHOT = range(5)
HEADERS = ["名称", "大小", "类型", "修改日期", "拍摄日期"]

# 目录条目
class Entry:
    __slots__ = ("name", "path", "is_dir", "size", "mtime", "hidden", "is_link")

    def __init__(self, name, path, is_dir, size, mtime, hidden, is_link):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size = size          # 文件字节数；目录为 -1（不显示）
        self.mtime = mtime        # 修改时间（epoch 秒）；未知为 0
        self.hidden = hidden
        self.is_link = is_link    # 符号链接 / NTFS 重分析点


# ---------- 目录枚举（纯 Python，不触碰 Qt，供后台线程调用） ----------

def _entry_hidden(path, name, is_dir):
    """跨平台隐藏判断：POSIX 以 . 前缀；Windows 读 FILE_ATTRIBUTE_HIDDEN"""
    if name.startswith('.'):
        return True
    if os.name == 'nt':
        try:
            import ctypes
            attr = ctypes.windll.kernel32.GetFileAttributesW(path)
            if attr != -1 and (attr & 0x2):  # FILE_ATTRIBUTE_HIDDEN
                return True
        except Exception:
            pass
    return False


def enumerate_dir(path, show_hidden=True):
    """枚举一个目录，返回 [Entry]。

    用 os.scandir：Windows 下 DirEntry 的 stat 结果来自枚举时已获取的
    WIN32_FIND_DATA 缓存，`entry.stat(follow_symlinks=False)` 不再触发额外
    网络往返——整个目录通常一次枚举往返即可拿到 name/attr/size/mtime。
    排序：目录优先、按名称（不区分大小写）升序，作为稳定基序；列排序由
    PaneSortProxyModel 负责。
    """
    entries = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    is_dir = e.is_dir(follow_symlinks=False)
                    is_link = e.is_symlink()
                except OSError:
                    is_dir = os.path.isdir(e.path)
                    is_link = os.path.islink(e.path)
                size = -1
                mtime = 0.0
                try:
                    st = e.stat(follow_symlinks=False)
                    mtime = getattr(st, "st_mtime", 0.0) or 0.0
                    if not is_dir:
                        size = getattr(st, "st_size", 0) or 0
                except OSError:
                    pass
                hidden = _entry_hidden(e.path, e.name, is_dir)
                if not show_hidden and hidden:
                    continue
                entries.append(Entry(e.name, os.path.normpath(e.path),
                                     is_dir, size, mtime, hidden, is_link))
    except (PermissionError, OSError) as exc:
        logger.debug("枚举目录失败 %s: %s", path, exc)
        return []
    entries.sort(key=lambda x: (not x.is_dir, x.name.casefold()))
    return entries


# ---------- 后台枚举任务 ----------

class _LoadSignals(QObject):
    finished = pyqtSignal(str, object)   # dir_path, list[Entry]


class _LoadTask(QRunnable):
    def __init__(self, path, show_hidden, signals):
        super().__init__()
        self.path = path
        self.show_hidden = show_hidden
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            rows = enumerate_dir(self.path, self.show_hidden)
        except Exception:
            rows = []
        # queued 投递回主线程（signals 属于主线程对象）
        self.signals.finished.emit(self.path, rows)


class DirStoreModel(QAbstractItemModel):
    """每窗格独立的扁平文件模型，根（invalid index）= 当前目录。"""

    directoryLoaded = pyqtSignal(str)   # 加载完成（含空目录），供 pane 同步 UI
    loadingStarted = pyqtSignal(str)    # 开始后台加载

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir = ""
        self._entries: list[Entry] = []
        self._loaded = False
        self._filter = (QDir.Filter.AllDirs | QDir.Filter.Files |
                        QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
        self._loading_token = 0          # 递增，用于丢弃过期加载结果
        self._pending = {}               # token -> path
        self._pool = QThreadPool.globalInstance()
        self._loader = _LoadSignals()
        self._loader.finished.connect(self._on_entries_loaded)
        self._invalid = QModelIndex()

    # ---- 兼容 QFileSystemModel 的接口 ----
    def rootPath(self):
        return self._dir

    def setFilter(self, filters):
        self._filter = filters

    def filter(self):
        return self._filter

    def _show_hidden(self):
        return bool(self._filter & QDir.Filter.Hidden)

    def isDir(self, index_or_path):
        if isinstance(index_or_path, str):
            return os.path.isdir(index_or_path)
        if not index_or_path.isValid():
            return True  # 根即当前目录，是目录
        e = index_or_path.internalPointer()
        return bool(e and e.is_dir)

    def filePath(self, index):
        if not index.isValid():
            return ""
        e = index.internalPointer()
        return e.path if e else ""

    def fileName(self, index):
        if not index.isValid():
            return ""
        e = index.internalPointer()
        return e.name if e else ""

    # ---- 目录切换 / 刷新 / 失效 ----
    def set_directory(self, path, force=False):
        """导航到 path：命中新鲜缓存则同步填充，否则清空并后台枚举。"""
        path = os.path.normpath(path) if path else ""
        if not path or not os.path.isdir(path):
            return False
        cached = None if force else self._cache_get(path)
        self.beginResetModel()
        self._dir = path
        if cached is not None:
            self._entries = cached
            self._loaded = True
        else:
            self._entries = []
            self._loaded = False
        self.endResetModel()
        if cached is None:
            self._start_load(path)
        self.directoryLoaded.emit(path)
        return True

    def refresh(self, _index=None):
        """重扫当前目录（F5）。index 参数仅为兼容旧调用签名。"""
        if self._dir:
            self._cache_invalidate(self._dir)
            self.set_directory(self._dir, force=True)

    # ---- 缓存（TTL + 定向失效）----
    # 类级缓存：{path: (timestamp, [Entry])}，跨窗格共享同一目录的枚举结果
    _CACHE = {}
    _CACHE_TTL = 2.0  # 秒；网络目录 TTL，本地目录主要靠定向失效

    @classmethod
    def _cache_get(cls, path):
        item = cls._CACHE.get(path)
        if not item:
            return None
        import time as _t
        if _t.time() - item[0] > cls._CACHE_TTL and cls._is_network(path):
            return None
        return item[1]

    @classmethod
    def _cache_put(cls, path, entries):
        import time as _t
        cls._CACHE[path] = (_t.time(), entries)

    @classmethod
    def _cache_invalidate(cls, path):
        cls._CACHE.pop(os.path.normpath(path), None)

    @staticmethod
    def _is_network(path):
        try:
            if os.name == 'nt':
                if path.startswith('\\\\'):
                    return True
                drive = path[:2]
                if drive[1] == ':':
                    import ctypes
                    DRIVE_REMOTE = 4
                    return ctypes.windll.kernel32.GetDriveTypeW(drive + '\\') == DRIVE_REMOTE
            return False
        except Exception:
            return False

    @classmethod
    def notify_dir_changed(cls, path):
        """外部（其它窗格/应用内操作）改了某目录：失效缓存，令正显示它的模型重载。"""
        cls._cache_invalidate(path)
        # 由 pane 侧遍历受影响的窗格调用 refresh；此处仅清缓存

    # ---- 后台加载 ----
    def _start_load(self, path):
        self._loading_token += 1
        token = self._loading_token
        self._pending[token] = path
        self.loadingStarted.emit(path)
        task = _LoadTask(path, self._show_hidden(), self._loader)
        self._pool.start(task)

    @pyqtSlot(str, object)
    def _on_entries_loaded(self, path, entries):
        # 只接受当前目录的结果（用户可能已切走）
        if os.path.normpath(path) != self._dir:
            self._pending.pop(self._loading_token, None)
            return
        # 合并"拍摄日期"缓存列无关（懒查），此处直接落数据
        self.beginResetModel()
        self._entries = entries
        self._loaded = True
        self.endResetModel()
        DirStoreModel._cache_put(self._dir, entries)
        self.directoryLoaded.emit(self._dir)

    # ---- QAbstractItemModel 必需实现（扁平：根 = 当前目录）----
    def index(self, row, column=0, parent=None):
        if row < 0 or column < 0:
            return self._invalid
        if parent is not None and parent.isValid():
            return self._invalid  # 扁平模型：目录不作为可展开父节点
        if row >= len(self._entries):
            return self._invalid
        return self.createIndex(row, column, self._entries[row])

    def parent(self, index):
        return self._invalid  # 所有条目的父即 invisible root（当前目录）

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(HEADERS):
                return HEADERS[section]
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        if not index.isValid():
            return base
        e = index.internalPointer()
        if e and e.is_dir:
            base |= Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemHasChildren
        else:
            base |= Qt.ItemFlag.ItemIsDragEnabled
        return base

    # ---- 数据角色 ----
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e = index.internalPointer()
        if e is None:
            return None
        col = index.column()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == COL_NAME:
                return e.name
            if col == COL_SIZE:
                return "" if e.is_dir else self._fmt_size(e.size)
            if col == COL_TYPE:
                return self._type_text(e)
            if col == COL_DATE:
                return self._fmt_mtime(e.mtime)
            if col == COL_SHOT:
                return self._shot_date(e)
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        elif role == Qt.ItemDataRole.DecorationRole:
            if col == COL_NAME:
                return self._icon(e)
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_NAME:
                return e.path
        elif role == Qt.ItemDataRole.FontRole:
            pass
        return None

    # ---- 重命名（setData）----
    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole):
            return False
        if index.column() != COL_NAME:
            return False
        e = index.internalPointer()
        new_name = (value or "").strip()
        if not new_name or new_name == e.name:
            return False
        old_path = e.path
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.lexists(new_path):
            return False
        try:
            os.rename(old_path, new_path)
        except OSError as exc:
            logger.info("重命名失败 %s -> %s: %s", old_path, new_name, exc)
            return False
        row = index.row()
        self.beginResetModel()  # 最简单可靠：整目录重载（rename 低频，代价可接受）
        e.name = new_name
        e.path = os.path.normpath(new_path)
        self.endResetModel()
        DirStoreModel._cache_invalidate(self._dir)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        return True

    # ---- 辅助格式化 ----
    @staticmethod
    def _fmt_size(size):
        if size is None or size < 0:
            return ""
        s = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if s < 1024 or unit == "TB":
                return f"{int(s)} {unit}" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} PB"

    @staticmethod
    def _fmt_mtime(mtime):
        if not mtime:
            return ""
        try:
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError, OverflowError):
            return ""

    @staticmethod
    def _type_text(e):
        if e.is_dir:
            return "文件夹"
        ext = os.path.splitext(e.name)[1].lower().lstrip('.')
        if ext:
            return f"{ext.upper()} 文件"
        return "文件"

    @staticmethod
    def _shot_date(e):
        if e.is_dir:
            return ""
        try:
            from core.media_metadata import get_shot_date_cached
            return get_shot_date_cached(e.path) or ""
        except Exception:
            return ""

    _ICON_CACHE = {}

    @classmethod
    def _icon(cls, e):
        style = QApplication.style()
        if e.is_dir:
            sp = QStyle.StandardPixmap.SP_DirIcon
        else:
            sp = QStyle.StandardPixmap.SP_FileIcon
        if sp not in cls._ICON_CACHE:
            cls._ICON_CACHE[sp] = style.standardIcon(sp)
        return cls._ICON_CACHE[sp]
