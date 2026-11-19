# -*- coding: utf-8 -*-
"""跨机器剪贴板里的「虚拟文件」：只有描述符 + 字节流，没有本机路径。

远程桌面（mstsc）里复制文件时，剪贴板上**没有** CF_HDROP，只有
`FileGroupDescriptorW`（文件名/大小/属性）与 `FileContents`（按项索引的字节流）。
2026-11-19 在嵌套 RDP 会话（session 2）里实测：裸 Win32 `GetClipboardData(FileContents)`
返回 **NULL**（它是 OLE 流格式，不是全局内存块），而 Qt 的
`mime.data('application/x-qt-windows-mime;value="FileContents"')` 能拿到整份字节
（1706 字节，与描述符里的文件大小吻合），耗时 0.032s。所以取字节这一步交给 Qt，
本模块只做解析 / 消毒 / 落盘。

纯执行层：不认识 Qt、不读剪贴板、不弹窗。调用方把两段字节取来交给我们，
离屏用例塞两段合成字节就能驱动整条链（与 `core/net_share.py` 同一手法）。
"""

import ctypes
import logging
import os
import struct

logger = logging.getLogger("pan4dex.rdp_files")

# 布局以 2026-11-19 真机 dump 为准（sizeof 592、cFileName 在 +72），不按头文件转写
# （铁律 #11 / gotchas #68）。名字字段用 c_uint16 而不是 c_wchar：后者在 Linux 上是
# 4 字节，会让 sizeof 变样，而这份布局要两端都能测。SIZE/POINT/FILETIME 一律拆成
# 两个 4 字节成员，避免 c_int64 的 8 字节对齐插出空洞。
class _FILEDESCRIPTORW(ctypes.Structure):
    _fields_ = [
        ("dwFlags", ctypes.c_uint32),
        ("clsid", ctypes.c_byte * 16),
        ("sizel", ctypes.c_int32 * 2),
        ("pointl", ctypes.c_int32 * 2),
        ("dwFileAttributes", ctypes.c_uint32),
        ("ftCreationTime", ctypes.c_uint32 * 2),
        ("ftLastAccessTime", ctypes.c_uint32 * 2),
        ("ftLastWriteTime", ctypes.c_uint32 * 2),
        ("nFileSizeHigh", ctypes.c_uint32),
        ("nFileSizeLow", ctypes.c_uint32),
        ("cFileName", ctypes.c_uint16 * 260),
    ]


DESCRIPTOR_SIZE = ctypes.sizeof(_FILEDESCRIPTORW)      # 实测 592
NAME_OFFSET = _FILEDESCRIPTORW.cFileName.offset        # 实测 72
ATTRS_OFFSET = _FILEDESCRIPTORW.dwFileAttributes.offset
SIZEHIGH_OFFSET = _FILEDESCRIPTORW.nFileSizeHigh.offset
SIZELOW_OFFSET = _FILEDESCRIPTORW.nFileSizeLow.offset

FD_ATTRIBUTES = 0x0004
FD_WRITESTIME = 0x0020
FD_FILESIZE = 0x0040
FILE_ATTRIBUTE_DIRECTORY = 0x0010

# 整份字节要先进内存才落盘，所以给一个上限；超了就走共享/重定向驱动器，别把界面撑死。
MAX_BYTES = 256 * 1024 * 1024

_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {"COM%d" % i for i in range(1, 10)}
    | {"LPT%d" % i for i in range(1, 10)}
)


class VirtualFile:
    """描述符里的一项（名字来自另一台机器，未消毒）"""
    __slots__ = ("name", "size", "is_dir", "flags")

    def __init__(self, name, size, is_dir, flags):
        self.name = name
        self.size = size
        self.is_dir = is_dir
        self.flags = flags

    @property
    def size_known(self):
        return bool(self.flags & FD_FILESIZE)


def parse_descriptors(raw):
    """解析 FILEGROUPDESCRIPTORW：首 4 字节是项数，其后每项 DESCRIPTOR_SIZE 字节。

    越界就停在上一项并记日志 —— 描述符来自另一台机器，长度不可信。
    """
    if not raw or len(raw) < 4:
        return []
    count = struct.unpack_from("<I", raw, 0)[0]
    files = []
    for i in range(count):
        off = 4 + i * DESCRIPTOR_SIZE
        if off + DESCRIPTOR_SIZE > len(raw):
            logger.warning("文件描述符第 %d 项越界（块长 %d），只取前 %d 项",
                           i, len(raw), len(files))
            break
        fd = _FILEDESCRIPTORW.from_buffer_copy(raw[off:off + DESCRIPTOR_SIZE])
        name = bytes(fd.cFileName).decode("utf-16-le", errors="replace").split("\x00", 1)[0]
        size = (fd.nFileSizeHigh << 32) | fd.nFileSizeLow
        files.append(VirtualFile(name, size,
                                 bool(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY),
                                 fd.dwFlags))
    return files


def safe_name(name):
    """把远端给的名字收成一个安全的 basename；不安全就返回 None。

    描述符里的名字来自另一台机器，`..\\..\\x` 这种能写到落点目录外面去；
    盘符与 ADS 冒号会让 open() 落到别的位置；Windows 保留设备名（NUL 等）
    写进去会静默丢弃内容。
    """
    if not name:
        return None
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = base.strip().rstrip(". ")
    if not base or base in (".", ".."):
        return None
    if any(c in base for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in base):
        return None
    if base.split(".")[0].upper() in _RESERVED_NAMES:
        return None
    return base


def plan(raw, max_bytes=MAX_BYTES):
    """只看描述符就能下的判断，返回 (files, refusal)。refusal 非空 = 别去取字节流，
    此时 files 为空（没有可用计划）。

    尺寸闸门必须在**读字节之前**：字节流是同步取的，先读满再判上限的话，
    一个 2GB 的文件会把界面冻住，上限也形同虚设。
    """
    files = parse_descriptors(raw)
    if not files:
        return [], "剪贴板里没有文件描述符，取不到跨机器的文件"
    first = files[0]
    if first.is_dir:
        return [], ("跨 RDP 复制文件夹暂不支持（剪贴板里只有字节流、没有目录树），"
                    "请进到文件夹里复制文件")
    if safe_name(first.name) is None:
        return [], "远端给的文件名不安全（%r），已拒绝落盘" % first.name
    if first.size_known and first.size > max_bytes:
        return [], ("文件太大（%d 字节，上限 %d）：跨 RDP 剪贴板要把整份读进内存，"
                    "请改用共享或重定向驱动器" % (first.size, max_bytes))
    return files, ""


def materialize(raw, contents, dest_dir, max_bytes=MAX_BYTES):
    """把描述符 + 字节流落成一个本地文件，返回 (paths, note)。

    note 是要说给用户听的话（空串 = 一切正常）。拒绝时 paths 为空、note 说明原因，
    **绝不写半个文件**：字节数与描述符不符就整份拒绝。
    """
    files, refusal = plan(raw, max_bytes)
    if refusal:
        return [], refusal

    first = files[0]
    name = safe_name(first.name)
    if not contents:
        return [], "剪贴板里有文件描述符，但取不到字节流（FileContents）"
    if first.size_known and len(contents) != first.size:
        return [], ("取到的字节数（%d）与描述符里的文件大小（%d）不符，"
                    "已拒绝落盘以免写出半个文件" % (len(contents), first.size))

    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    with open(dest, "wb") as fh:
        fh.write(contents)

    note = ""
    if len(files) > 1:
        # 字节流是按项索引取的，Qt 那个接口只给第 0 项（多文件要按索引走 OLE，另案）
        note = ("跨 RDP 剪贴板一次只取到第 1 个文件（共 %d 个），其余请逐个复制"
                % len(files))
    return [dest], note