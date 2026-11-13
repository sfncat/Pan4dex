# -*- coding: utf-8 -*-
"""媒体拍摄日期提取：基于 ExifTool。

字段取值规则（与设备端 MvhdReader 一致）：
- 视频：CreateDate → DateTimeOriginal（QuickTime mvhd.creation_time 即 exiftool 的 QuickTime:CreateDate）
- 照片：DateTimeOriginal → CreateDate（EXIF 拍摄时间）

exiftool 查找顺序：
1. 应用内携带（Windows：resources/tools/exiftool/exiftool.exe，含 Perl 运行时，解压即用）
2. 系统 PATH（Linux 发行版通常自带 exiftool）

结果为缓存式：同一路径只读取一次，避免反复启动 exiftool 进程。
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

logger = logging.getLogger("pan4dex.media_metadata")

# Windows 下后台运行控制台子进程（exiftool）时不弹出终端黑窗：
# 打包后为 windowed 应用（无控制台），默认会为控制台子进程新建窗口，一闪而过。
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# 全局状态
_EXIFTOOL_PATH = None      # None=未探测，''=未找到，其他=路径
_EXIFTOOL_VERSION = None   # None=未探测，''=未知
_CACHE: dict = {}          # {path: 'YYYY-MM-DD HH:MM' 或 None}
_CACHE_LOCK = threading.Lock()
_VERSION_LOCK = threading.Lock()

# ---------- 拍摄日期预读专用线程池（限流） ----------

_SHOT_POOL = None
_SHOT_POOL_THREADS = 2   # 一个任务拉起一个 exiftool 子进程，并发必须封顶


def shot_pool():
    """拍摄日期预读专用的全进程线程池（**不用**全局池，也不每窗格一个）。

    旧实现是裸 daemon 线程：实测 20 次快速导航堆出 17 个同时在飞的线程 ——
    换成真 exiftool 就是 17 个并发子进程啃同一批文件（SMB 上尤其糟），而且窗格
    销毁后 21 个任务全部照跑完。上限取 2：与目录占用池同一量级，既给子进程数封顶，
    又不至于让一个慢目录把预读全堵死。每窗格一个池会让四窗格变成 4×N，同样失控。
    """
    global _SHOT_POOL
    if _SHOT_POOL is None:
        pool = QThreadPool()
        pool.setMaxThreadCount(_SHOT_POOL_THREADS)
        pool.setObjectName("pan4dex.shotpool")
        _SHOT_POOL = pool
    return _SHOT_POOL


def _find_exiftool():
    """定位 exiftool 可执行文件（应用内携带优先，其次系统 PATH）。

    - Windows：应用内 resources/tools/exiftool/exiftool.exe（自带 Perl 运行时）
    - Linux/其他：应用内 resources/tools/exiftool-linux/exiftool（Perl 脚本，
      用系统 perl 运行）；找不到再回退系统 exiftool
    """
    global _EXIFTOOL_PATH
    if _EXIFTOOL_PATH is not None:
        return _EXIFTOOL_PATH or None

    is_windows = os.name == 'nt'
    sub = 'exiftool' if is_windows else 'exiftool-linux'
    name = 'exiftool.exe' if is_windows else 'exiftool'

    candidates = []
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', '')
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # onefile: _MEIPASS 是解包目录；onedir: _MEIPASS 指向 _internal，exe 同目录也有 resources
        for root in (base, exe_dir):
            if root:
                candidates.append(os.path.join(root, 'resources', 'tools', sub, name))
    else:
        candidates.append(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'resources', 'tools', sub, name,
            )
        )

    for c in candidates:
        if c and os.path.isfile(c):
            _EXIFTOOL_PATH = c
            return c

    found = shutil.which('exiftool')
    if found:
        _EXIFTOOL_PATH = found
        return found

    _EXIFTOOL_PATH = ''  # 缓存"未找到"
    return None


def _exiftool_cmd(extra_args):
    """构造 exiftool 调用命令。

    Windows：直接运行 exiftool.exe（自带 Perl）；
    Linux：携带版是 Perl 脚本，用系统 perl 解释执行。
    """
    exif = _find_exiftool()
    if not exif:
        return None
    if os.name == 'nt':
        return [exif] + extra_args
    # Linux：优先用 perl 运行应用内脚本；系统 exiftool（shebang 可执行）直接跑
    if os.path.basename(exif) == 'exiftool' and not exif.startswith('/usr') and not exif.startswith('/bin'):
        perl = shutil.which('perl')
        if perl:
            return [perl, exif] + extra_args
    return [exif] + extra_args


def exiftool_version():
    """返回 exiftool 版本号（如 '13.59'），无则 None。"""
    global _EXIFTOOL_VERSION
    with _VERSION_LOCK:
        if _EXIFTOOL_VERSION is not None:
            return _EXIFTOOL_VERSION or None
    exif = _find_exiftool()
    if not exif:
        with _VERSION_LOCK:
            _EXIFTOOL_VERSION = ''
        return None
    try:
        out = subprocess.run(_exiftool_cmd(['-ver']), capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW)
        with _VERSION_LOCK:
            _EXIFTOOL_VERSION = out.stdout.strip() or ''
    except Exception as e:
        logger.warning(f"exiftool -ver failed: {e}")
        with _VERSION_LOCK:
            _EXIFTOOL_VERSION = ''
    return _EXIFTOOL_VERSION or None


def _clean_date(v):
    """过滤无效日期（如 '0000:00:00 00:00:00'，无时间戳视频的占位值）。"""
    if not v:
        return None
    v = str(v).strip()
    if not v or v.startswith('0000:'):
        return None
    return v


def _run_exiftool(paths):
    """调用 exiftool 批量读取，返回 JSON 列表。

    文件名走 UTF-8 参数文件（-@ + -charset filename=utf8）：Windows 上命令行
    参数按系统 ANSI 代码页解读，中文文件名会变成 "No matching files"。
    输出按 UTF-8 解码（exiftool 的 -json 恒为 UTF-8，text=True 的 locale 解码
    遇中文会 UnicodeDecodeError 使整批失败）。
    """
    cmd = _exiftool_cmd(['-charset', 'filename=utf8', '-json',
                         '-d', '%Y-%m-%d %H:%M',
                         '-DateTimeOriginal', '-CreateDate'])
    if not cmd:
        return None
    args_file = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', suffix='.args',
                prefix='pan4dex-exif-', delete=False) as fh:
            args_file = fh.name
            for p in paths:
                fh.write(p + '\n')
        cmd = cmd + ['-@', args_file]
        proc = subprocess.run(cmd, capture_output=True, timeout=30,
                              creationflags=_NO_WINDOW)
        if proc.returncode != 0:
            logger.debug(f"exiftool rc={proc.returncode}: {proc.stderr[:200]}")
        out = proc.stdout.decode('utf-8', errors='replace')
        if not out.strip():
            return []
        return json.loads(out)
    except Exception as e:
        logger.warning(f"exiftool failed ({len(paths)} files): {e}")
        return None
    finally:
        if args_file:
            try:
                os.unlink(args_file)
            except OSError:
                pass


def _norm(path: str) -> str:
    """统一缓存键：Windows 下正斜杠/反斜杠归一。"""
    return os.path.normpath(path)


_EXIFTOOL_CHUNK = 500  # 单次 exiftool 调用最多处理文件数（防命令行超长）


def batch_get_shot_dates(paths, cancel=None) -> dict:
    """批量获取拍摄日期，返回 {path: 'YYYY-MM-DD HH:MM' 或 None}。

    只对未缓存的文件发起 exiftool 调用（按 500 个一批），结果入缓存。
    `cancel` 是「该停了吗」令牌（可调用或带 `abandoned` 属性），**每批之间**探一次：
    命中就不再啃后续批，返回已得结果。局限要清楚（gotchas #58）：取消标志拦不住
    已经阻塞在子进程调用里的那一批，所以浪费上限是 500 个文件（≤30s 超时），
    不是整个目录。被取消时**不给未处理的路径写 None 缓存**，否则它们再也不会被重试。
    """
    paths = [p for p in paths if p]
    if not paths:
        return {}

    keys = {p: _norm(p) for p in paths}
    with _CACHE_LOCK:
        todo = [p for p in paths if keys[p] not in _CACHE]
    if not todo:
        with _CACHE_LOCK:
            return {p: _CACHE.get(keys[p]) for p in paths}

    aborted = False
    for i in range(0, len(todo), _EXIFTOOL_CHUNK):
        if cancel is not None:
            aborted = bool(cancel()) if callable(cancel) else bool(cancel.abandoned)
            if aborted:
                break
        chunk = todo[i:i + _EXIFTOOL_CHUNK]
        data = _run_exiftool(chunk)
        if data is None:
            continue
        norm_to_path = {_norm(p): p for p in chunk}
        for item in data:
            src = _norm(item.get('SourceFile', ''))
            orig = norm_to_path.get(src)
            if orig is not None:
                with _CACHE_LOCK:
                    _CACHE[src] = _clean_date(item.get('DateTimeOriginal') or item.get('CreateDate'))

    with _CACHE_LOCK:
        if not aborted:
            for p in todo:
                if keys[p] not in _CACHE:
                    _CACHE[keys[p]] = None  # 失败也缓存，避免反复调用
        return {p: _CACHE.get(keys[p]) for p in paths}


class ShotCancel:
    """「该停了吗」令牌（方向见 gotchas #54：返回真 = 该停，别写反）。

    只持窗格弱引用与一个代际整数，不碰 Qt 对象，worker 线程读它安全。
    窗格没了（Python 对象被回收，或 C++ 对象已 sip.delete）、或又发起了一次新预读
    （代际变了），旧任务就该停下后续批。**两种「没了」都要判**：sip.delete 之后
    Python 包装对象可能还被别处引用着，只看弱引用会漏掉这一支。
    """
    __slots__ = ("_pane", "_gen", "abandoned")

    def __init__(self, pane, gen):
        self._pane = weakref.ref(pane)
        self._gen = gen
        self.abandoned = False

    def __call__(self):
        if self.abandoned:
            return True
        pane = self._pane()
        if pane is None or sip.isdeleted(pane):
            return True
        return pane._shot_gen != self._gen


class ShotDateSignals(QObject):
    """预读结果回投：**以窗格为父**，窗格销毁时已排队的投递被 Qt 一并剔除。

    接收者必须是窗格这个 QObject（同 `dir_model._LoadSignals(self)` 的理由，见
    docs/unsolved-issues.md 问题 13）：改成无 QObject 归属的 closure，投递就会在
    窗格销毁后照旧派发，实测把崩溃点从槽内部前推到分发处。
    """
    done = pyqtSignal(int)      # 发起预读时的代际


class ShotDateTask(QRunnable):
    """一次拍摄日期预读：后台只跑 exiftool 子进程，不触碰 Qt 模型。"""

    def __init__(self, paths, signals, gen, cancel):
        super().__init__()
        self.paths = paths
        self.signals = signals
        self.gen = gen
        self.cancel = cancel
        self.setAutoDelete(True)

    def run(self):
        try:
            batch_get_shot_dates(self.paths, cancel=self.cancel)
        except Exception as e:
            logger.debug(f"拍摄日期预读失败: {e}")
        try:
            self.signals.done.emit(self.gen)
        except RuntimeError:
            pass        # 窗格已销毁：投递目标没了，丢掉这一帧


def get_shot_date_cached(path) -> str | None:
    """只查缓存，不触发 exiftool（供 UI 渲染路径使用，避免卡顿）。

    值由后台 prefetch（batch_get_shot_dates）填充，填充后视图刷新即显示。
    """
    key = _norm(path)
    with _CACHE_LOCK:
        return _CACHE.get(key)


def get_shot_date(path) -> str | None:
    """懒加载单个文件的拍摄日期（优先 DateTimeOriginal，其次 CreateDate）。"""
    key = _norm(path)
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]
    data = _run_exiftool([path])
    date = None
    if data:
        for item in data:
            if _norm(item.get('SourceFile', '')) == key:
                date = _clean_date(item.get('DateTimeOriginal') or item.get('CreateDate'))
                break
    with _CACHE_LOCK:
        _CACHE[key] = date
    return date
