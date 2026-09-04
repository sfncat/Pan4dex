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
import threading

logger = logging.getLogger("pan4dex.media_metadata")

# 全局状态
_EXIFTOOL_PATH = None      # None=未探测，''=未找到，其他=路径
_EXIFTOOL_VERSION = None   # None=未探测，''=未知
_CACHE: dict = {}          # {path: 'YYYY-MM-DD HH:MM' 或 None}
_CACHE_LOCK = threading.Lock()
_VERSION_LOCK = threading.Lock()


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
        out = subprocess.run(_exiftool_cmd(['-ver']), capture_output=True, text=True, timeout=20)
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
    """调用 exiftool 批量读取，返回 JSON 列表。"""
    cmd = _exiftool_cmd(['-json', '-d', '%Y-%m-%d %H:%M', '-DateTimeOriginal', '-CreateDate'] + paths)
    if not cmd:
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            logger.debug(f"exiftool rc={proc.returncode}: {proc.stderr[:200]}")
        if not proc.stdout.strip():
            return []
        return json.loads(proc.stdout)
    except Exception as e:
        logger.warning(f"exiftool failed ({len(paths)} files): {e}")
        return None


def _norm(path: str) -> str:
    """统一缓存键：Windows 下正斜杠/反斜杠归一。"""
    return os.path.normpath(path)


_EXIFTOOL_CHUNK = 500  # 单次 exiftool 调用最多处理文件数（防命令行超长）


def batch_get_shot_dates(paths) -> dict:
    """批量获取拍摄日期，返回 {path: 'YYYY-MM-DD HH:MM' 或 None}。

    只对未缓存的文件发起 exiftool 调用（按 500 个一批），结果入缓存。
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

    for i in range(0, len(todo), _EXIFTOOL_CHUNK):
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
        for p in todo:
            if keys[p] not in _CACHE:
                _CACHE[keys[p]] = None  # 失败也缓存，避免反复调用
        return {p: _CACHE.get(keys[p]) for p in paths}


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
