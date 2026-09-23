# -*- coding: utf-8 -*-
"""
Pan4dex 万格 — DirStoreModel：以目录节点为单位的异步文件模型

设计目标：
- 一次枚举一个目录，杜绝 QFileSystemModel 在 SMB 上的逐项 stat 与 watcher 轮询
- 后台线程枚举（QThreadPool），主线程零阻塞；未加载完成 rowCount=0，canFetchMore/
  fetchMore 驱动，加载完 begin/endInsertRows 增量插入
- 在飞的枚举**可中断**：导航离开一个慢位置（`core/mounts.py` 判据）时，那个再也不会
  出现在屏幕上的目录不再被扫完，被中断的扫描也不回投条目（否则万条目会在主线程
  采纳，见 `_LoadTask` / `_drop_stale_scans`；显式入口 `cancel_load`）
- TTL 缓存 + 定向失效：应用内操作后只失效涉及的目录，F5 只重扫当前目录
- 本地目录挂 QFileSystemWatcher（只挂「当前显示的那一个」，外部程序改动时自动重扫）；
  监视器全进程共用一个 _WatchHub；网络目录一律不挂 watcher（那正是拖垮 SMB 的
  轮询源），靠 TTL + 定向失效；不显示的本地目录靠快照 TTL 过期后重扫
- 结构：当前显示目录作为 invalid 根的唯一顶层行（rowCount(invalid)=1），
  因此 pane 拿到的索引一定能被 QSortFilterProxyModel.mapFromSource 映射

作用范围：仅服务文件列表视图（tree_view / 缩略图）。两个侧边目录树
（pane_tree_view / tree_sidebar）本就按需展开、非瓶颈，继续使用 QFileSystemModel。
"""
import os
import time
import logging
import contextlib
import weakref as _weakref
from datetime import datetime

from core import mounts

from PyQt6.QtCore import (
    QAbstractItemModel, QCoreApplication, QModelIndex, Qt, QDir,
    QFileSystemWatcher, QTimer, QRunnable, QThreadPool, QObject,
    pyqtSignal, pyqtSlot,
)
from PyQt6.QtWidgets import QApplication, QStyle

logger = logging.getLogger("pan4dex.dir_model")

# 列定义（名称/大小/类型/修改日期 + 拍摄日期，前 4 列沿用资源管理器习惯顺序）
COL_NAME, COL_SIZE, COL_TYPE, COL_DATE, COL_SHOT = range(5)
HEADERS = ["名称", "大小", "类型", "修改日期", "拍摄日期"]


def _key(path):
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


class Entry:
    """文件/目录条目（某个目录节点的一个子项）。"""
    __slots__ = ("name", "path", "is_dir", "size", "mtime", "hidden", "is_link", "node")

    def __init__(self, name, path, is_dir, size, mtime, hidden, is_link):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size = size          # 文件字节数；目录为 -1（大小列不显示）
        self.mtime = mtime        # 修改时间（epoch 秒）；未知为 0
        self.hidden = hidden
        self.is_link = is_link    # 符号链接 / NTFS 重分析点
        self.node = None          # 所属 DirNode（加载后回填）


class DirNode:
    """一个目录节点：持有其枚举出的条目列表与加载状态。"""
    __slots__ = ("path", "key", "entries", "loaded", "loading", "gen", "_stale", "ts",
                 "abandoned")

    def __init__(self, path):
        self.path = os.path.normpath(path)
        self.key = _key(path)
        self.entries = None        # None=未加载；list=已加载
        self.loaded = False
        self.loading = False
        self.gen = 0               # 枚举请求代次：只采纳最新一次的结果
        self.abandoned = False     # 在飞枚举被放弃（导航离开慢位置 / 显式取消）→ 该停扫
        self._stale = None         # 上一代条目快照（见 _discard_node：不能直接还给 GC）
        self.ts = 0.0              # 快照生成时刻，判过期用（见 _snapshot_fresh）


# ---------- 进程级目录监视器 ----------

class _WatchHub(QObject):
    """全进程唯一的 QFileSystemWatcher，以 QApplication 为父。

    为何不用 per-model watcher：模型（窗格）可被任意时刻的 GC 销毁，而 Qt 在
    Windows 上的目录监视共用一个全局线程，析构与在飞的变更通知会竞态。实测
    接上 per-model watcher（监视所有曾导航过的目录）后全量测试 2/8 轮 access
    violation；改成 hub 但依旧监视全部目录 → 10/10 必崩；hub + 只监视当前显示
    目录 → 0/6（见 docs/gotchas.md 第 23 条与 unsolved-issues 问题 13）。
    监视器随应用生灭（时刻确定），模型只做登记/注销；通知经本类的
    `directoryNotice` 转发，接收者是模型本身→模型销毁时 Qt 自动断连。

    登记用弱引用计数：同一目录可被多个窗格监视，最后一个监视者消失时摘句柄；
    模型被 GC 后条目变空，由 _prune_dead 回收（不靠模型的析构钩子）。
    """

    directoryNotice = pyqtSignal(str)
    _INSTANCE = None
    _MAX_PATHS = 64      # 上限护栏：正常用不会碰（只监视当前显示目录，每窗格 1 个）

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self.directoryNotice)
        self._refs = {}   # normpath -> {id(model): weakref(model)}

    @classmethod
    def instance(cls):
        app = QCoreApplication.instance()
        if app is None:
            return None
        hub = cls._INSTANCE
        if hub is None or hub._app is not app:
            hub = cls(app)
            cls._INSTANCE = hub
        return hub

    def add(self, path, owner):
        if len(self._refs) > self._MAX_PATHS:
            self._prune_dead()
        refs = self._refs.setdefault(path, {})
        for mid, r in list(refs.items()):   # id 会重用，先洗掉本路径的死引用
            if r() is None:
                refs.pop(mid, None)
        first = not refs
        refs[id(owner)] = _weakref.ref(owner)
        if not first:
            return True
        try:
            ok = self._watcher.addPath(path)
        except (RuntimeError, OSError):
            ok = False
        if not ok:
            self._refs.pop(path, None)
        return ok

    def remove(self, path, owner):
        refs = self._refs.get(path)
        if refs is None:
            return
        ref = refs.get(id(owner))
        if ref is not None:
            refs.pop(id(owner), None)
        if refs:
            return
        self._refs.pop(path, None)
        try:
            self._watcher.removePath(path)
        except (RuntimeError, OSError):
            pass

    def directories(self):
        return list(self._watcher.directories())

    def _prune_dead(self):
        """模型已被 GC：它的监视登记没人再注销，由本方法兼式回收。"""
        for path in list(self._refs.keys()):
            refs = self._refs[path]
            alive = {mid: r for mid, r in refs.items() if r() is not None}
            if alive:
                self._refs[path] = alive
                continue
            self._refs.pop(path, None)
            try:
                self._watcher.removePath(path)
            except (RuntimeError, OSError):
                pass


# ---------- 目录枚举（纯 Python，不触碰 Qt，供后台线程调用） ----------

def _entry_hidden(path, name):
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


class _EnumerationAborted(Exception):
    """枚举被主动放弃（切走窗格 / 另起一次枚举）——与「目录为空」「没权限」区分开"""


# 每读这么多个目录项探一次取消标志。取 2 的幂：`&` 比 `%` 便宜，而在远端挂载上
# 逐项 stat 本身就是几十毫秒量级，这个间隔下取消延迟可忽略，开销量不出来。
_ENUM_CANCEL_CHECK_EVERY = 256


class _Enumerator:
    """`enumerate_dir` 的扫描主体：持有取消令牌，按固定间隔探一次该不该停。

    取消令牌可以是一个可调用的「还要不要这份结果」（`_LoadTask` 就是这么喂的，它把
    `abandoned` 与 gen 校验一并报回来），也可以是一个只带 `abandoned` 布尔属性的对象
    （测试桩与探针更搭这样）。**判定在调用方**，本类只负责「问」与「停」—— 早退发生
    在调用方的线程上，不跨线程改任何共享状态。
    """

    __slots__ = ("_cancel", "_n")

    def __init__(self, cancel):
        self._cancel = cancel
        self._n = 0

    def check(self):
        cancel = self._cancel
        if cancel is None:
            return
        self._n += 1
        if self._n & (_ENUM_CANCEL_CHECK_EVERY - 1):
            return
        aborted = bool(cancel()) if callable(cancel) else cancel.abandoned
        if aborted:
            raise _EnumerationAborted()


def _scan_into(path, entries, show_hidden, check=None):
    """把 `path` 的目录项读进 `entries`；`check` 是 `_Enumerator.check`（可为 None）。

    只读单项属性、不额外 stat：`os.scandir` 已经把这些信息带在 `WIN32_FIND_DATA`
    / POSIX dirent 的返回结果里，这是「一个目录一次往返」这个设计目标的前提。
    """
    with os.scandir(path) as it:
        for e in it:
            if check is not None:
                check()
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
            hidden = _entry_hidden(e.path, e.name)
            if not show_hidden and hidden:
                continue
            entries.append(Entry(e.name, os.path.normpath(e.path),
                                 is_dir, size, mtime, hidden, is_link))


def enumerate_dir(path, show_hidden=True, cancel=None):
    """枚举一个目录，返回 [Entry]。

    用 os.scandir：Windows 下 DirEntry 的 stat 结果来自枚举时已获取的
    WIN32_FIND_DATA 缓存，`entry.stat(follow_symlinks=False)` 不再触发额外
    网络往返——整个目录通常一次枚举往返即可拿到 name/attr/size/mtime。
    排序：目录优先、按名称（不区分大小写）升序，作为稳定基序；列排序由
    PaneSortProxyModel 负责。

    `cancel` 非空时是一个「该停了吗」的令牌（带 `abandoned` 属性或可调用）：每
    `_ENUM_CANCEL_CHECK_EVERY` 项探一次，命中就抛 `_EnumerationAborted` 而不是返回
    半截列表 —— 半截列表与「这个目录本来就这么多项」在调用方根本分不开，而分不开
    的结果一旦被采纳，用户在万条目共享上看到的就是一个安静的、看不出的截断列表。
    """
    entries = []
    enumerator = _Enumerator(cancel) if cancel is not None else None
    check = enumerator.check if enumerator is not None else None
    try:
        _scan_into(path, entries, show_hidden, check)
    except _EnumerationAborted:
        raise
    except (PermissionError, OSError) as exc:
        logger.debug("枚举目录失败 %s: %s", path, exc)
        return []
    entries.sort(key=lambda x: (not x.is_dir, x.name.casefold()))
    return entries


# ---------- 枚举专用线程池（限流）----------

_ENUM_POOL_THREADS = 4        # 一屏最多 4 个窗格，再多并发枚举无益
_DIR_POOL = None


def dir_pool():
    """目录枚举专用的全进程线程池（**不用** `QThreadPool.globalInstance()`）。

    全局池默认按 CPU 核数起线程（本机 24 核），一次开四个窗格 + 快速导航就能把
    几十个 `os.scandir` 同时丢出去（实测 faulthandler 转储里 10 个线程全卡在
    `enumerate_dir`）。代价有两重：SMB 上几十路并发枚举互抢通道、比串行更慢；
    结果投递与新建的条目对象成倍砸回主线程，直接抬高偶发 access violation 的
    概率（崩溃率与在飞枚举量单调相关，见 docs/unsolved-issues.md 问题 13）。
    上限取 4：等于窗格数，足够保证“一个盘卡住不会让其它窗格转不了”。
    """
    global _DIR_POOL
    if _DIR_POOL is None:
        pool = QThreadPool()
        pool.setMaxThreadCount(_ENUM_POOL_THREADS)
        pool.setObjectName("pan4dex.dirpool")
        _DIR_POOL = pool
    return _DIR_POOL


# ---------- 后台枚举任务 ----------

class _LoadSignals(QObject):
    finished = pyqtSignal(object, object, int, object)   # DirNode, list[Entry], gen, task
    cancelled = pyqtSignal(object, int, object)          # DirNode, gen, task


class _LoadTask(QRunnable):
    """一次后台枚举。它自己就是取消令牌（`abandoned`）。

    三个停扫条件（都在 worker 线程里逐项探，见 `_Enumerator`）：
    - `gen != node.gen`：期间又发起过新枚举（F5 / 到达即重扫），这次结果注定不采纳
    - `node.abandoned`：导航已离开这个目录，或节点已被丢弃（见 `_drop_stale_scans`）
    - 两项都在主线程设置，worker 只读布尔；GIL 保证可见性，不依赖跨线程写共享结构

    被中断时**不回投条目**，只投一个 `cancelled(gen, task)`：光把 `node.loading`
    改回 False 不够 —— 用户可能在 worker 还没注意到标志时就导航回来了，那时
    `set_directory` 见 `loading` 为真会拒绝重扫，视图就永久停在空列表上。
    """

    def __init__(self, node, gen, show_hidden, signals):
        super().__init__()
        self.node = node
        self.gen = gen
        self.show_hidden = show_hidden
        self.signals = signals
        self.abandoned = False     # 由模型在主线程置位（与 node.abandoned 同步）
        self.self_id = id(self)    # 采纳端认任务身份用（见 `_on_entries_loaded`）
        self.setAutoDelete(True)

    def _still_wanted(self):
        """这次枚举还有没有人要。只读主线程写好的几个布尔，不碰盘、不改状态。"""
        node = self.node
        return (not self.abandoned) and (not node.abandoned) and (node.gen == self.gen)

    def _should_stop(self):
        # `_Enumerator.check` 的令牌约定是「返回 True = 该停了」（与测试里那个
        # `return len(hits) >= 2` 的令牌一致），而 `_still_wanted` 是「还要这份结果 =
        # 继续扫」—— 两者相反。直接把 `_still_wanted` 当 `__call__` 会让每个健康扫描
        # 在第一次探测就自杀（本轮踩过），令牌必须报「停」的方向。
        return not self._still_wanted()

    __call__ = _should_stop
    # ↑ 任务本身就是 `enumerate_dir` 的取消令牌：除了带 `abandoned` 属性（上面那条
    # 路径），它还可调 = 「该不该停扫」。把 gen 校验也接进扫描循环才能真省
    # 下那一段盘（只靠 `abandoned` 的话，被 F5 超越的旧扫描仍会一路扫到黑）；
    # 而对测试桩与探针来说，`cancel=` 喂进去的东西一律可用。

    def run(self):
        node = self.node
        rows = None
        why = ""
        try:
            if not self._still_wanted():
                why = "开工前已过期"          # 排队期间就被导航走了：一个目录项都不该读
            else:
                try:
                    rows = enumerate_dir(node.path, self.show_hidden, cancel=self)
                except TypeError:
                    # 被替身接管的 `enumerate_dir` 不认识 cancel（测试桩 / 探针）：
                    # 重跑一次不带的，不拿签名不匹配当枚举失败把空目录交给用户
                    rows = enumerate_dir(node.path, self.show_hidden)
                if not self._still_wanted():
                    rows, why = None, "扫描期间被放弃"
        except _EnumerationAborted:
            why = "枚举早退"                  # 交回线程池槽位，不拿半截列表去采纳
        except Exception:
            rows, why = [], "枚举异常"
        # 无论哪条分支，都要给主线程一个交代（`cancelled` 只用来复位 `loading`，
        # 带 gen 与任务身份，迟到的通知不会误伤当代请求）
        try:
            if rows is not None:
                # queued 投递回主线程（signals 属于主线程对象）。模型可能已先一步销毁，
                # 而 signals 是模型的子对象、届时自己也成了悬空包装 → emit 报 RuntimeError；
                # 丢掉这份结果即可，不能让异常死在 worker 线程里
                self.signals.finished.emit(node, rows, self.gen, self)
            else:
                logger.debug("枚举放弃 %s gen=%s：%s", node.path, self.gen, why)
                self.signals.cancelled.emit(node, self.gen, self)
        except RuntimeError:
            logger.debug("枚举结果丢弃：投递目标已随模型销毁")


class DirStoreModel(QAbstractItemModel):
    """当前显示目录 = invalid 根的唯一顶层行，其子行为该目录条目。

    pane 导航时调用 `set_directory(path)` 取得顶层索引，再经排序代理
    setRootIndex，视图即展示该目录的条目列表。
    """

    SHOT_DATE_COLUMN = COL_SHOT   # pane 的「拍摄日期」列常量
    directoryLoaded = pyqtSignal(str)
    loadingStarted = pyqtSignal(str)
    dirChanged = pyqtSignal(str)   # 本模型使某目录发生变更（行内改名等），供跨窗格同步

    # 类级缓存：{dirkey: (timestamp, show_hidden, [Entry])}，跨窗格共享同一目录枚举结果
    _CACHE = {}
    _CACHE_TTL = 2.0   # 秒；本地/网络通用。监视只跟当前显示目录，切走期间的
                       # 改动靠「快照过期 + 到达时重扫」兜底，故本地快照也非永久有效
    # 类级「应用内刚改过该目录」时间戳：用于抑制紧随其后的文件系统通知，
    # 避免同一次改动被重扫两遍（列表闪一下）。跨窗格共享——一个窗格改动会
    # 经 refresh_dir 刷所有窗格，各窗格的 watcher 通知届时都该被跳过
    _self_change = {}
    _SELF_CHANGE_SUPPRESS = 1.5   # 秒
    _WATCH_DEBOUNCE_MS = 350      # 通知合并窗口：一次粘贴 N 个文件只重扫一次
    _MAX_NODES = 96               # 节点上限（只删把条目交还了 GC 的，见 _prune_nodes）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes = {}           # dirkey -> DirNode
        self._top_node = None      # 当前显示的目录节点（作为模型唯一顶层行）
        self._top_key = ""         # 顶层节点 key
        self._filter = (QDir.Filter.AllDirs | QDir.Filter.Files |
                        QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
        self._pool = dir_pool()
        # `_loader` 以本模型为父：模型销毁时它一同销毁，在飞任务的 emit 会立刻失败
        # 并被 `_LoadTask.run` 吞掉，不会留下悬空的投递源。
        # 接收者必须是本模型（所以用绑定方法直连）：只有那样 Qt 才会在模型销毁时
        # 把已排队的投递一并剔除。改成“无 QObject 归属的函数”（如弱引用 closure）
        # 后，接收者变成 sender，而 `_loader` 会被在飞任务活得比模型久，投递就在模型
        # 销毁后照旧派发 —— 实测反而把崩溃点从槽内部前推到分发处（见
        # docs/unsolved-issues.md 问题 13）。
        self._loader = _LoadSignals(self)
        self._loader.finished.connect(self._on_entries_loaded)
        self._loader.cancelled.connect(self._on_load_cancelled)
        # dirkey -> 在飞的 `_LoadTask`。只由主线程写（注册在 `_start_load`、除名在
        # 两个采纳槽里），worker 只读自己那个任务的布尔 —— 字典不会跨线程改动。
        self._pending = {}
        self._invalid = QModelIndex()
        # begin/end 行信号嵌套深度（见 _rows_signal）
        self._rows_changing = 0
        # 本地目录监视：全进程共用一个监视器（见 _WatchHub），本模型只登记路径。
        # 通知的接收者是本模型 → 模型销毁时 Qt 自动断连，不会有悬空投递。
        self._hub = _WatchHub.instance()
        self._watched = set()        # 已登记监视的 dirkey（本模型至多 1 个）
        self._watch_path = ""        # 当前已在 hub 里登记的 normpath
        self._want_watch = ""        # 下一次 flush 要登记的目标（空＝不监视）
        self._pending_watch = set()  # 防抖期间攒下的 dirkey
        if self._hub is not None:
            self._hub.directoryNotice.connect(self._on_watched_dir_changed)
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(self._WATCH_DEBOUNCE_MS)
        self._watch_timer.timeout.connect(self._flush_watch_events)
        # 登记/注销动作推到事件循环顶层（见 _watch_sync）
        self._watch_op_timer = QTimer(self)
        self._watch_op_timer.setSingleShot(True)
        self._watch_op_timer.setInterval(0)
        self._watch_op_timer.timeout.connect(self._flush_watch_ops)

    # ---- pane 依赖的条目/目录查询接口（与 QFileSystemModel 同名，便于替换）----
    def rootPath(self):
        return self._top_node.path if self._top_node else ""

    def setFilter(self, filters):
        self._filter = filters

    def filter(self):
        return self._filter

    def set_directory(self, path):
        """pane 导航时调用：把该目录设为模型唯一顶层节点并触发异步加载。

        返回目录节点的顶层索引——它是 invalid 根的唯一行，因此
        QSortFilterProxyModel.mapFromSource 能正确映射（与 pane 的
        `_set_root_index` 用法兼容）。切换目录时 beginResetModel 让代理
        重建根；对同一目录重复调用不重置。
        """
        path = os.path.normpath(path) if path else ""
        if not path:
            return self._invalid
        node = self._ensure_node(path)
        key = node.key
        if self._top_key == key and self._top_node is node:
            if not node.loaded and not node.loading:
                self._start_load(node)
            self._watch_add(path)      # 目标不变时不会重发登记（_watch_sync 会合并）
            return self.createIndex(0, 0, node)
        prev = self._top_node
        # 快照过期（离开期间目录可能被外部改过）：在 reset **之前**作废，视图随
        # reset 直接看到空列表，随后一次枚举插回。放在 reset 之后要走
        # removeRows + insertRows 两趟，实测这种「到达即重扫」把后台枚举量翻倍，
        # access violation 触发率从 1/8 涨到 9/10（见 docs/gotchas.md 第 25 条）
        if node.loaded and not self._snapshot_fresh(node):
            self._discard_node(key)
        self.beginResetModel()
        self._top_node = node
        self._top_key = key
        self.endResetModel()
        # 导航离开的那个目录如果还在被扫（它可能正卡在 SMB 上十几秒），把它的枚举
        # 放弃掉：不回投 = 不在主线程采纳，同时交还线程池槽位（见 _drop_stale_scans）
        self._drop_stale_scans(prev)
        # reset 已通知所有视图丢弃索引 → 上一代条目可以归还 GC 了（见 _drop_stale）
        self._drop_stale()
        # 监视跟随「屏幕上看得见的那个目录」：只监视顶层，切走即摘。
        # 登记只记下目标，真正的 addPath/removePath 在事件循环顶层做（见 _watch_sync）
        if prev is not None and prev.key != key:
            self._watch_drop(prev.key)
        self._watch_add(path)
        if not node.loaded and not node.loading:
            self._start_load(node)
        return self.createIndex(0, 0, node)

    def isDir(self, idx):
        if isinstance(idx, str):
            return os.path.isdir(idx)
        p = idx.internalPointer() if idx.isValid() else None
        if isinstance(p, DirNode):
            return True
        if isinstance(p, Entry):
            return p.is_dir
        return False

    def filePath(self, idx):
        if not idx.isValid():
            return ""
        p = idx.internalPointer()
        return p.path if p else ""

    def fileName(self, idx):
        if not idx.isValid():
            return ""
        p = idx.internalPointer()
        return getattr(p, "name", "") or (os.path.basename(p.path) if isinstance(p, DirNode) else "")

    def entry_is_dir(self, path):
        """纯内存判定路径是否为目录（零 syscall、零网络往返）。

        返回 True/False；模型尚未加载该目录（未知）时返回 None，
        由调用方决定回退方式（网络路径回退一次 os.path.isdir）。
        """
        path = os.path.normpath(path) if path else ""
        if not path:
            return None
        # 当前显示目录本身
        if _key(path) == self._top_key and self._top_node is not None:
            return True
        # 曾作为目录枚举过的节点（含已切走的）——内存里已知道它是目录
        if _key(path) in self._nodes:
            return True
        node = self._nodes.get(_key(os.path.dirname(path)))
        if node and node.loaded and node.entries:
            for e in node.entries:
                if e.path == path:
                    return e.is_dir
        return None

    # ---- 缓存 / 定向失效 ----
    @classmethod
    def _cache_get(cls, key, show_hidden):
        item = cls._CACHE.get(key)
        if not item:
            return None
        ts, sh, entries = item
        if sh != show_hidden:
            return None
        return entries

    @classmethod
    def _cache_put(cls, key, show_hidden, entries):
        cls._CACHE[key] = (time.time(), show_hidden, entries)

    @classmethod
    def _cache_invalidate(cls, path):
        cls._CACHE.pop(_key(path), None)

    @staticmethod
    def _is_network(path):
        """该目录是否位于「慢位置」（不配挂 watcher 的那一类）

        判据全仓一份（`core/mounts.py`）：Windows 看 UNC / `DRIVE_REMOTE`，
        POSIX 看挂载表的文件系统类型（gvfs / CIFS / NFS / 任意 FUSE）。
        失败一律当本地：宁可多挂一个 watcher，也不能因判据本身出错而少监视。
        """
        try:
            return mounts.is_remote_location(path)
        except Exception:
            return False

    @classmethod
    def notify_dir_changed(cls, path):
        """外部（其它窗格/应用内操作）改了某目录：失效缓存。

        正显示该目录的窗格由 pane 侧调用 refresh 重载（pane 负责遍历受影响窗格）。
        """
        cls._cache_invalidate(path)

    @classmethod
    def _mark_self_change(cls, path):
        """记下「应用内刚刚改过该目录」，用于抑制随后的文件系统通知。"""
        cls._self_change[_key(path)] = time.time()

    # ---- 本地目录监视：只监视「当前显示的那个目录」，登记动作延迟执行 ----
    def _watch_add(self, path):
        self._watch_sync(path)

    def _watch_drop(self, key):
        if self._watch_path and _key(self._watch_path) == key:
            self._watch_sync("")

    def _watch_sync(self, path):
        """记下「本模型要监视哪个目录」，真正的 addPath/removePath 等事件循环顶层再做。

        网络目录直接归为空目标（不监视）——SMB 上的 watcher 正是要根治的轮询源。
        同一轮事件里的多次导航只留最后一个目标，所以窗格构造/快速切换不会
        把 native 调用嵌在 `QWidget::setModel` 这类构造栈中间执行。
        """
        want = ""
        if path and not self._is_network(path):
            want = os.path.normpath(path)   # 与 DirNode.path 同形，对比时才能对上
        self._want_watch = want
        if not self._watch_op_timer.isActive():
            self._watch_op_timer.start()

    def _flush_watch_ops(self):
        """执行 `_watch_sync` 定下的目标：摘旧加新（本模型至多监视一个目录）。"""
        want = self._want_watch
        cur = self._watch_path
        if want == cur or self._hub is None:
            return
        if cur:
            try:
                self._hub.remove(cur, self)
            except (RuntimeError, OSError):
                pass
            self._watched.discard(_key(cur))
            self._pending_watch.discard(_key(cur))
            self._watch_path = ""
        if not want:
            return
        try:
            ok = self._hub.add(want, self)
        except (RuntimeError, OSError):
            ok = False      # 监视器正在销毁
        if ok:
            self._watch_path = want
            self._watched.add(_key(want))
        else:
            logger.debug("无法监视目录（已删除或无权限）: %s", want)

    def watched_directories(self):
        """当前登记的监视路径（本模型与其它模型共用监视器）。"""
        return self._hub.directories() if self._hub is not None else []

    def _prune_nodes(self):
        """节点数封顶：只删「没把条目对象交给过 Qt」的节点。

        判据：未加载、无旧快照、不在加载中、不是当前显示目录。否则视图/排序代理
        里的裸指针会悬空（见 _discard_node）。旧快照本身活到下一次
        reset/removeRows（见 _drop_stale），不会随会话无界堆积。
        """
        if len(self._nodes) <= self._MAX_NODES:
            return
        for key in list(self._nodes.keys()):
            if len(self._nodes) <= self._MAX_NODES:
                break
            node = self._nodes.get(key)
            if (node is None or node is self._top_node or node.loading
                    or node.entries or node._stale):
                continue      # 条目指针已交给 Qt，现在不能释放
            self._watch_drop(key)
            self._nodes.pop(key, None)
            self._CACHE.pop(key, None)

    def _discard_node(self, key):
        """让一个不再显示的目录节点失效（下次导航回来重新枚举）。

        **不能把条目对象直接放给 GC**：`createIndex()` 交给 Qt 的是这些 Python
        对象的裸指针，而 PyQt 不替我们保持引用（实测：模型丢引用 + gc.collect()
        后 300 个条目当场回收，而视图/排序代理里仍留着指向它们的指针，解引用就
        是 access violation，见 docs/unsolved-issues.md 问题 13）。所以旧快照挂到
        节点自身的 `_stale` 上，直到下一个「安全点」（_drop_stale）才释放。
        """
        node = self._nodes.get(key)
        if node is None:
            return
        if node.entries:
            node._stale = node.entries
        node.entries = None
        node.loaded = False
        self._CACHE.pop(key, None)

    def _drop_stale(self, node=None):
        """安全点：模型刚通过信号告知视图索引不再有效，可释放旧条目快照。

        只能在 `endResetModel()` / `endRemoveRows()` **之后**调用——那之前视图里的
        指针仍然有效，归还 GC 就是悬空指针。默认清全部节点（reset 让所有索引作废），
        传 node 表示只有该节点的行被移除过。保留期因此限定在「失效 → 下次切换目录」
        之间，不会随会话无限增长。
        """
        for n in ((node,) if node is not None else self._nodes.values()):
            n._stale = None

    def _on_watched_dir_changed(self, path):
        """文件系统通知：先攒进待处理集，防抖窗口结束后统一重扫。

        一次粘贴 N 个文件会连发多条通知，逐条重扫会让列表反复清空重建。
        """
        key = _key(path)
        if key not in self._nodes:
            return
        self._pending_watch.add(key)
        if not self._watch_timer.isActive():
            self._watch_timer.start()

    def _flush_watch_events(self):
        """防抖窗口结束：对攒下的目录各重扫一次（本地目录的外部改动）。"""
        pending = self._pending_watch
        self._pending_watch = set()
        now = time.time()
        rescanned = []
        for key in pending:
            # 应用内改动（粘贴/新建/删除/行内改名）已经显式 refresh_dir 过，
            # 紧随其后的通知会再扫一遍，跳过
            if now - self._self_change.get(key, 0.0) < self._SELF_CHANGE_SUPPRESS:
                continue
            node = self._nodes.get(key)
            if node is None or node.loading:
                continue
            if node is not self._top_node:
                # 不再显示的目录：标为未加载（条目快照由节点留着，见 _discard_node）
                self._discard_node(key)
                continue
            self._reload_top(node)
            rescanned.append(node.path)
        for path in rescanned:
            try:
                self.dirChanged.emit(path)  # 让其它显示同一目录的窗格一并跟上
            except RuntimeError:
                return  # 模型已在本次处理中销毁

    def refresh(self, index=None):
        """重扫当前显示目录（F5 / 定向失效）：清条目后异步重载，
        保留顶层节点映射（不重置模型，为保留选中/滚动留余地）。"""
        node = self._top_node
        if node is not None:
            self._reload_top(node)

    def refresh_dir(self, path):
        """失效并重扫指定目录（应用内改动后调用，本地/网络统一）。

        - 正是当前显示目录：清条目 + 异步重载（保留顶层索引映射）
        - 已加载但未显示：标为未加载（条目快照延到安全点释放），导航回来时
          重新枚举（不失效则陈旧节点会让模型跳过重扫，新建/删除的项迟迟不可见；
          watcher 只监视当前显示的目录，代劳不了这里）
        """
        self._cache_invalidate(path)
        self._mark_self_change(path)
        node = self._nodes.get(_key(path))
        if node is None:
            return
        if node is self._top_node:
            self._reload_top(node)
            return
        # 不再显示的目录：标为未加载，下次导航回来重新枚举
        self._discard_node(node.key)

    def _reload_top(self, node):
        self._cache_invalidate(node.path)
        with self._rows_signal():
            if node.loaded and node.entries:
                parent_idx = self.createIndex(0, 0, node)
                self.beginRemoveRows(parent_idx, 0, len(node.entries) - 1)
                node.entries = None
                node.loaded = False
                self.endRemoveRows()
                self._drop_stale(node)   # 行已按信号移除，旧快照此刻才可释放
            else:
                # 目录当前为空（entries==[]）或尚未 loaded：没有旧行要移除，但
                # 仍必须把 loaded 复位——否则新枚举结果会在采纳端撞上
                # `_on_entries_loaded` 的「幂等：node.loaded」守卫被整份丢弃，
                # 表现为：新建目录→进去（空）→复制文件进去→F5 刷新，状态栏数得到
                # 那个文件但列表永远为空（空目录刷新看不到新文件的回归）。
                node.entries = None
                node.loaded = False
            # 重扫请求总是另起一次枚举（gen+1）， in-flight 的旧结果会被作废
            self._start_load(node)

    @contextlib.contextmanager
    def _rows_signal(self):
        """包住一对 begin/end 行信号，期间挡住 `rowCount` 的惰性加载。

        `beginInsertRows` / `endRemoveRows` 内部会回调 `rowCount(parent)`（实测），
        而那一刻节点正处于「未 loaded 且未 loading」的过渡态，惰性触发条件成立
        → 白发起一次多余的枚举，且新枚举的 gen 会把正要采纳的结果算作过期。
        """
        self._rows_changing += 1
        try:
            yield
        finally:
            self._rows_changing -= 1

    # ---- 节点 materialize + 异步加载 ----
    def _ensure_node(self, path):
        key = _key(path)
        node = self._nodes.get(key)
        if node is not None:
            return node
        node = DirNode(path)
        self._nodes[key] = node
        self._prune_nodes()
        show = self._show_hidden()
        cached = self._cache_get(key, show)
        if cached is not None and self._cache_fresh(key):
            self._copy_entries(node, cached)
            node.ts = self._CACHE[key][0]   # 沿用缓存生成时刻，不把陈旧快照洗白
            node.loaded = True   # 调用方（set_directory）按 TTL 决定要不要再扫一次
        return node

    @classmethod
    def _cache_fresh(cls, key):
        """类级缓存条目是否仍在 TTL 内（本地/网络同一规则）。"""
        item = cls._CACHE.get(key)
        return bool(item) and (time.time() - item[0] <= cls._CACHE_TTL)

    @classmethod
    def _snapshot_fresh(cls, node):
        """节点已有快照时，它算不算新到可以直接给用户看。

        监视只覆盖「当前显示的目录」，切走期间的外部改动收不到通知，靠的就是
        这里判过期、到达时重扫一次。本地枚举很便宜，网络枚举受 TTL 约束。
        """
        return (time.time() - node.ts) <= cls._CACHE_TTL

    @staticmethod
    def _adopt(node, entries):
        """后台新枚举出的条目归本节点独占（无共享，直接回填 node 反查指针）。"""
        for e in entries:
            e.node = node
        node.entries = entries
        node.ts = time.time()
        return entries

    @staticmethod
    def _copy_entries(node, entries):
        """把类级缓存里的条目复制为本节点独占对象。

        多个窗格可能同时显示同一目录并共用缓存列表；Entry 是可变的
        （行内改名会就地改 name/path，e.node 反查用于 parent()），共享
        会造成跨窗格互相污染，故缓存只作只读模板，使用时逐份复制。
        """
        bound = []
        for e in entries:
            ne = Entry(e.name, e.path, e.is_dir, e.size, e.mtime, e.hidden, e.is_link)
            ne.node = node
            bound.append(ne)
        node.entries = bound
        node.ts = time.time()
        return bound

    def _show_hidden(self):
        return bool(self._filter & QDir.Filter.Hidden)

    def _start_load(self, node):
        """发起一次后台枚举；旧请求的结果按代次(gen)作废，并且旧请求本身会被中断。

        隐式调用方自行判断 `not loaded and not loading`；显式刷新（_reload_top）
        会先清 loading 再调用，以保证能拿到改动后的枚举结果。

        入册必须在 `self._pool.start()` **之前**：任务一旦交给线程池就可能立刻跑起来，
        而它随时可能被导航放弃，那时 `_drop_stale_scans` 得能在 `_pending` 里找到它。
        """
        node.gen += 1
        node.loading = True
        node.abandoned = False
        task = _LoadTask(node, node.gen, self._show_hidden(), self._loader)
        self._pending[node.key] = task
        self.loadingStarted.emit(node.path)
        self._pool.start(task)

    def _drop_stale_scans(self, prev=None):
        """放弃「本次导航已经不再显示」的在飞枚举，只放走慢位置的那批。

        只在 `set_directory` 切完顶层之后调，并把**刚离开的那个节点**交给它 ——
        届时 `_top_node` 已是新目录，光拿 `_top_node` 比对永远认不出刚切走的那个
        （p59e 现场里卡 23.2s 的正是它）。
        命中条件两条全部成立才中断（宁可少停不可错停）：
        1. 任务对应的节点就是刚离开的那个，或已不是当前显示的顶层
        2. 那个目录在慢位置上（复用 `_is_network`，判据一份，都在主线程调）

        不中断的那批照常回投，由 `_on_entries_loaded` 的现有 gen / 节点归属校验处理
        —— 本次改动不拿它开刀，本地万条目目录的采纳延迟（实测 1256ms）与存储无关，
        是「行落地」的通用代价，得另案（分批插入）才能压下去。
        """
        for key, task in list(self._pending.items()):
            node = task.node
            if node is not prev and node is self._top_node:
                continue                       # 还在屏幕上显示着，扫完就是给用户看的
            if not self._is_network(node.path):
                continue
            task.abandoned = True
            node.abandoned = True
            logger.debug("放弃在飞枚举（导航离开慢位置）：%s", node.path)

    def cancel_load(self, path=None):
        """中断一个目录的在飞枚举（产品侧唯一的枚举取消入口，也是它的手工验证入口）。

        `path=None` 时放弃本模型全部在飞枚举。被中断的扫描不回投条目，因此不会
        在主线程采纳；`loading` 经 `cancelled` 投递复位，所以用户马上再导航回来会
        重新枚举（代价是重扫，不是永久空列表）。

        与 `_drop_stale_scans` 的分工：那里按慢位置判据选择性停扫，这里是显式指令，
        不分本地/远端一律停（调用方已经明确表示不要这份结果了）。
        任务**留在 `_pending` 里**等它自己投 `cancelled` 来除名 —— 现在就弹掉的话，
        复位投递会被身份校验挡掉，`loading` 永远停在 True。
        """
        targets = list(self._pending.values()) if path is None \
            else [t for k, t in self._pending.items() if k == _key(path)]
        for task in targets:
            task.abandoned = True
            task.node.abandoned = True

    def _forget_scan(self, node, task):
        """主线程除名：本代次的枚举已有交代（采纳、丢弃或中断），不再跟踪。

        不按 key 弹：若 F5 已为同一节点入册了新任务，旧的交代不能把新的踢出
        登记表，否则新任务再也过不了采纳端的身份校验，它的结果会被丢一次。
        """
        if self._pending.get(node.key) is task:
            self._pending.pop(node.key, None)

    @pyqtSlot(object, object, int, object)
    def _on_entries_loaded(self, node, entries, gen, task=None):
        if gen != node.gen:
            return  # 过期结果：期间又发起过新枚举，否则旧快照会占据视图
        if task is not None and self._pending.get(node.key) is not task:
            return  # 不是本节点当前跟踪的那次枚举（F5 后迟到的旧投递）：不动状态
        # 先取完要用的自身状态：本槽由后台线程的投递触发，销毁时刻不受本槽控制，
        # 实测存在“槽跑到一半 self.__dict__ 已被清空”的现场（见 __init__ 处的说明）
        show_hidden = self._show_hidden()
        if node.key not in self._nodes or self._nodes.get(node.key) is not node:
            node.loading = False
            self._forget_scan(node, task)
            return  # 节点已被丢弃
        if node.loaded:
            node.loading = False
            self._forget_scan(node, task)
            return  # 幂等：同一节点重复的完成信号不得再次插入（避免重复行）
        parent_idx = self.createIndex(0, 0, node)
        first = 0
        with self._rows_signal():
            if entries:
                self.beginInsertRows(parent_idx, first, first + len(entries) - 1)
            self._adopt(node, entries)
            node.loaded = True
            self._cache_put(node.key, show_hidden, entries)
            if entries:
                self.endInsertRows()
        # loading 最后才清：过渡态不能对任何重入查询暴露（同 _rows_signal 的理由）
        node.loading = False
        self._forget_scan(node, task)
        try:
            self.directoryLoaded.emit(node.path)
        except RuntimeError:
            pass  # 模型已在本槽执行期间被销毁：目录已加载完，不必再通知

    @pyqtSlot(object, int, object)
    def _on_load_cancelled(self, node, gen, task=None):
        """一次枚举被中断/放弃：复位 `loading`，让导航回来时能重新发起。

        两道校验缺一不可：
        - `gen < node.gen`：F5 已另起新枚举，它的 `loading=True` 属于当代，不能清
          （清了就会同一目录并发扫两遍，见 gotchas 24「别把一次枚举发起两遍」）
        - 任务身份：`cancelled` 是排队投递，可能「新任务已入册」之后才派发到位，
          那时 gen 相同而归属不同，按 gen 判仍会把当代的 loading 误清
        两个条件都不满足时才认作「当代请求的结清」。
        """
        if gen != node.gen:
            return                             # 迟到或被超越：当代自己会交代
        if task is not None and self._pending.get(node.key) is not task:
            return
        node.loading = False
        node.abandoned = False   # 本代次已结清，节点回到「可被重新发起」的中性态
        self._forget_scan(node, task)

    # ---- QAbstractItemModel 必需实现 ----
    def index(self, *args, **kwargs):
        # 路径形式：index(path_str)
        if args and isinstance(args[0], str):
            return self._index_for_path(args[0])
        # 常规形式：index(row, column, parent)
        if not args:
            return self._invalid
        row = args[0]
        column = args[1] if len(args) > 1 else kwargs.get('column', 0)
        parent = args[2] if len(args) > 2 else kwargs.get('parent', self._invalid)
        if row < 0 or column < 0:
            return self._invalid
        if not parent.isValid():
            # invalid 根的唯一行 = 当前顶层目录节点
            if row == 0 and self._top_node is not None:
                return self.createIndex(0, column, self._top_node)
            return self._invalid
        p = parent.internalPointer()
        if isinstance(p, DirNode):
            if not p.loaded or not p.entries or row >= len(p.entries):
                return self._invalid
            return self.createIndex(row, column, p.entries[row])
        return self._invalid  # 条目不再有子

    def _index_for_path(self, path):
        """路径 → 索引，仅对【当前显示目录】及其条目有效。

        其它目录的节点虽存在 `self._nodes` 里（缓存/曾导航过），但不能返回
        它们的索引：两层结构中任何 DirNode 的父都报为 invalid 根，而
        index(0, 0, invalid) 只会解出顶层节点，于是非顶层节点的条目经
        排序代理映射会得到“看似有效实则错行”的索引（误定位、误改名）。
        判定任意路径是否目录请用 `entry_is_dir()`（零 syscall）。
        """
        path = os.path.normpath(path) if path else ""
        if not path:
            return self._invalid
        node = self._top_node
        if node is None:
            return self._invalid
        if _key(path) == self._top_key:
            return self.createIndex(0, 0, node)
        if node.loaded and node.entries:
            for r, e in enumerate(node.entries):
                if e.path == path:
                    return self.createIndex(r, 0, e)
        return self._invalid

    def parent(self, index):
        if not index.isValid():
            return self._invalid
        p = index.internalPointer()
        if isinstance(p, Entry) and p.node is not None:
            return self.createIndex(0, 0, p.node)   # 条目的父 = 其目录节点
        return self._invalid                          # 顶层目录节点的父 = invalid 根

    def rowCount(self, parent=None):
        if parent is None or not parent.isValid():
            return 1 if self._top_node is not None else 0
        p = parent.internalPointer()
        if isinstance(p, DirNode):
            if (p is self._top_node and not p.loaded and not p.loading
                    and not self._rows_changing):
                self._start_load(p)
            return len(p.entries) if (p.loaded and p.entries) else 0
        return 0

    def canFetchMore(self, parent):
        if not parent.isValid():
            return False
        p = parent.internalPointer()
        return (p is self._top_node and isinstance(p, DirNode)
                and not p.loaded and not p.loading and not self._rows_changing)

    def fetchMore(self, parent):
        if not parent.isValid():
            return
        p = parent.internalPointer()
        if p is self._top_node and isinstance(p, DirNode) and not p.loaded and not p.loading:
            self._start_load(p)

    def columnCount(self, parent=None):
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
        if isinstance(e, Entry) and e.is_dir:
            # 目录：可作为拖放目标；是否有子项由 rowCount/canFetchMore 决定
            base |= Qt.ItemFlag.ItemIsDropEnabled
        elif isinstance(e, Entry):
            # 文件：可拖拽、确定无子项
            base |= Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemNeverHasChildren
        return base

    # ---- 数据角色 ----
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e = index.internalPointer()
        if not isinstance(e, Entry):
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
        return None

    # ---- 重命名（setData）----
    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole):
            return False
        if index.column() != COL_NAME:
            return False
        e = index.internalPointer()
        if not isinstance(e, Entry):
            return False
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
        node = e.node
        # 就地更新条目并 emit dataChanged：不重置模型，保留选中/滚动；
        # 名称变化后 PaneSortProxyModel 的 dynamicSortFilter 会自动重排。
        e.name = new_name
        e.path = os.path.normpath(new_path)
        if node is not None:
            self._cache_invalidate(node.path)
            self._mark_self_change(node.path)
        self.dataChanged.emit(index, index,
                              [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.dirChanged.emit(os.path.dirname(old_path))
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
        from PyQt6.QtWidgets import QStyle
        style = QApplication.style()
        sp = QStyle.StandardPixmap.SP_DirIcon if e.is_dir else QStyle.StandardPixmap.SP_FileIcon
        if sp not in cls._ICON_CACHE:
            cls._ICON_CACHE[sp] = style.standardIcon(sp)
        return cls._ICON_CACHE[sp]
