# -*- coding: utf-8 -*-
"""压缩/解压操作：内置 7-Zip（resources/tools/7z）+ 系统 7-Zip 优先。

查找顺序：
1. 系统 7-Zip（PATH 的 7z/7za/7zz/7zr，Windows 下 Program Files\7-Zip\7z.exe）
   ——完整功能（含 RAR 等更多格式）
2. 应用内携带（Windows：resources/tools/7z/7za.exe；Linux：resources/tools/7z/7zz）
   ——主流格式（7z/zip/gzip/bzip2/tar 等）兜底

结果为缓存式：同一进程只探测一次。
"""
import logging
import os
import re
import shutil
import subprocess
import sys
import threading

logger = logging.getLogger("pan4dex.archive_ops")

# Windows 下后台运行控制台子进程（7za）时不弹出终端黑窗
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# 压缩包扩展名集合（小写；双后缀 .tar.gz/.tar.bz2/.tar.xz 单独判断）
_ARCHIVE_EXTS = {
    '.7z', '.zip', '.rar', '.tar', '.gz', '.bz2', '.xz', '.z',
    '.tgz', '.tbz2', '.txz', '.lzh', '.lha', '.cab', '.iso', '.arj',
    '.wim', '.swm', '.cpio', '.rpm', '.deb', '.001',
}

_7Z_PATH = None      # None=未探测，''=未找到，其他=路径
_7Z_VERSION = None   # None=未探测，''=未知，其他=版本号
_LOCK = threading.Lock()


def is_archive(path: str) -> bool:
    """判断路径是否为受支持的压缩包（文件存在 + 扩展名匹配，含 .tar.gz 双后缀）。"""
    if not path or not os.path.isfile(path):
        return False
    p = path.lower()
    for ext in ('.tar.gz', '.tar.bz2', '.tar.xz'):
        if p.endswith(ext):
            return True
    return os.path.splitext(p)[1] in _ARCHIVE_EXTS


def _resource_7z():
    """应用内携带的 7z 可执行文件路径（无则 None）。

    Windows：7z.exe（完整版，需同目录 7z.dll，支持 RAR 等更多格式）优先，
    7za.exe（独立版）兜底；Linux：7zz（完整版，支持 RAR）。
    """
    sub = '7z'
    if os.name == 'nt':
        names = ('7z.exe', '7za.exe')
    else:
        names = ('7zz',)
    candidates = []
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', '')
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        for root in (base, exe_dir):
            if root:
                for name in names:
                    candidates.append((os.path.join(root, 'resources', 'tools', sub, name), name))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in names:
            candidates.append((os.path.join(base, 'resources', 'tools', sub, name), name))
    for c, name in candidates:
        if c and os.path.isfile(c):
            if name == '7z.exe':
                # 完整版依赖同目录 7z.dll；缺失则跳过（用 7za 兜底）
                if os.path.isfile(os.path.join(os.path.dirname(c), '7z.dll')):
                    return c
                continue
            return c
    return None


def find_7z():
    """定位 7z 可执行文件：系统优先（完整功能），应用内携带兜底。"""
    global _7Z_PATH
    if _7Z_PATH is not None:
        return _7Z_PATH or None

    # 1) 系统 PATH
    for name in ('7z', '7za', '7zz', '7zr'):
        found = shutil.which(name)
        if found:
            _7Z_PATH = found
            return found
    # 2) Windows 标准安装目录
    if os.name == 'nt':
        for pf in (os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', '')):
            p = os.path.join(pf, '7-Zip', '7z.exe')
            if pf and os.path.isfile(p):
                _7Z_PATH = p
                return p
    # 3) 应用内携带
    res = _resource_7z()
    if res:
        if os.name != 'nt':
            try:
                os.chmod(res, 0o755)  # 打包解出后可能丢失执行位
            except OSError:
                pass
        _7Z_PATH = res
        return res

    _7Z_PATH = ''
    return None


def version():
    """返回 7-Zip 版本号（如 '26.03'），未找到则 None。"""
    global _7Z_VERSION
    with _LOCK:
        if _7Z_VERSION is not None:
            return _7Z_VERSION or None
    sevenz = find_7z()
    if not sevenz:
        with _LOCK:
            _7Z_VERSION = ''
        return None
    try:
        out = subprocess.run([sevenz], capture_output=True, text=True, timeout=10,
                             errors='replace', creationflags=_NO_WINDOW)
        text = (out.stdout or '') + (out.stderr or '')
        ver = ''
        for line in text.splitlines():
            m = re.search(r'(\d+\.\d+)', line)
            if m:
                ver = m.group(1)
                break
        with _LOCK:
            _7Z_VERSION = ver
    except Exception as e:
        logger.warning("7-Zip 版本读取失败: %s", e)
        with _LOCK:
            _7Z_VERSION = ''
    return _7Z_VERSION or None


def version_source():
    """返回 (版本号, 来源)。来源为 '系统' 或 '内置'；未找到则 (None, None)。"""
    ver = version()
    if not ver:
        return None, None
    sevenz = find_7z()
    src = '内置' if sevenz and sevenz == _resource_7z() else '系统'
    return ver, src


def builtin_version():
    """返回应用内携带 7-Zip 的版本号（无则 None）。"""
    res = _resource_7z()
    if not res:
        return None
    try:
        out = subprocess.run([res], capture_output=True, text=True, timeout=10,
                             errors='replace', creationflags=_NO_WINDOW)
        text = (out.stdout or '') + (out.stderr or '')
        for line in text.splitlines():
            m = re.search(r'(\d+\.\d+)', line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def _run(cmd):
    """运行 7z 命令并返回 (returncode, stdout, stderr)。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600,
                              errors='replace', creationflags=_NO_WINDOW)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 1, '', '操作超时'
    except Exception as e:
        return 1, '', str(e)


def compress(output_path, items):
    """压缩指定路径列表到 output_path（格式由后缀决定）。

    Returns: (ok, message)；ok=True 时 message 为输出文件绝对路径。
    """
    sevenz = find_7z()
    if not sevenz:
        return False, '未找到 7-Zip（系统或内置）'
    if not items:
        return False, '没有可压缩的项目'
    out_dir = os.path.dirname(output_path) or '.'
    if not os.path.isdir(out_dir):
        return False, f'输出目录不存在: {out_dir}'
    cmd = [sevenz, 'a', '-y', os.path.abspath(output_path)]
    cmd += [os.path.abspath(i) for i in items]
    rc, out, err = _run(cmd)
    if rc == 0 and os.path.isfile(output_path):
        return True, os.path.abspath(output_path)
    return False, (err or out or '压缩失败').strip()


def extract(archive, dest_dir):
    """解压压缩包到 dest_dir（保留内部目录结构）。

    Returns: (ok, message)；ok=True 时 message 为目标目录绝对路径。
    """
    sevenz = find_7z()
    if not sevenz:
        return False, '未找到 7-Zip（系统或内置）'
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as e:
        return False, f'无法创建目标目录: {e}'
    cmd = [sevenz, 'x', '-y', f'-o{os.path.abspath(dest_dir)}', os.path.abspath(archive)]
    rc, out, err = _run(cmd)
    if rc == 0:
        return True, os.path.abspath(dest_dir)
    return False, (err or out or '解压失败').strip()


def list_entries(archive):
    """列出压缩包内容，返回 [(name, size), ...]；失败返回 None。"""
    sevenz = find_7z()
    if not sevenz:
        return None
    cmd = [sevenz, 'l', '-slt', os.path.abspath(archive)]
    rc, out, err = _run(cmd)
    if rc != 0:
        logger.warning("7z 列内容失败 %s: %s", archive, (err or out).strip()[:300])
        return None
    entries = []
    name = None
    size = 0
    archive_abs = os.path.abspath(archive).lower()
    archive_base = os.path.basename(archive).lower()
    for line in out.splitlines():
        if line.startswith('Path = '):
            name = line[len('Path = '):].strip()
        elif line.startswith('Size = '):
            try:
                size = int(line[len('Size = '):].strip())
            except ValueError:
                size = 0
        elif line.strip() == '' and name is not None:
            # 跳过压缩包自身的块（7z l -slt 第一个块是归档文件本身）
            if name.lower() not in (archive_abs, archive_base):
                entries.append((name, size))
            name = None
            size = 0
    if name is not None and name.lower() not in (archive_abs, archive_base):
        entries.append((name, size))
    return entries
