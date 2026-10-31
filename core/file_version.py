# -*- coding: utf-8 -*-
"""Windows PE 文件版本资源读取（平铺视图的瓦片附注用）。

只读版本资源（VS_VERSIONINFO）：文件版本号 + 文件说明。与资源管理器
「平铺」视图对 exe/dll 展示的两个字段同源，不走 exiftool。非 Windows、
非 PE（无版本资源）或读取失败一律返回 None，由调用方回退到大小/类型。
"""
import ctypes
import os
import struct
import sys
from ctypes import wintypes

_version = None  # version.dll，win32 下首次调用时加载


class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [(n, wintypes.DWORD) for n in (
        "dwSignature", "dwStrucVersion",
        "dwFileVersionMS", "dwFileVersionLS",
        "dwProductVersionMS", "dwProductVersionLS",
        "dwFileFlagsMask", "dwFileFlags",
        "dwFileOS", "dwFileType", "dwFileSubtype",
        "dwFileDateMS", "dwFileDateLS")]


def _ensure_version_dll():
    global _version
    if _version is None:
        _version = ctypes.WinDLL("version")
    return _version


def _query_string(data, key):
    """按第一个翻译表（lang/codepage）取 StringFileInfo 字符串，找不到回退到
    0409 两个常见代码页。返回 str 或 None。"""
    v = _ensure_version_dll()
    buf = ctypes.c_void_p()
    blen = wintypes.UINT()
    if not v.VerQueryValueW(data, "\\VarFileInfo\\Translation",
                            ctypes.byref(buf), ctypes.byref(blen)) or blen.value < 4:
        return None
    lang, cp = struct.unpack_from("<HH", ctypes.string_at(buf, 4))
    for l, c in ((lang, cp), (0x0409, 0x04B0), (0x0409, 0x04E4)):
        sub = f"\\StringFileInfo\\{l:04x}{c:04x}\\{key}"
        if v.VerQueryValueW(data, sub, ctypes.byref(buf), ctypes.byref(blen)) \
                and blen.value and buf:
            s = ctypes.wstring_at(buf)
            if s:
                return s
    return None


def get_version_info(path):
    """返回 (版本号, 文件说明)；无版本资源/非 Windows/失败返回 None。"""
    if sys.platform != "win32" or not os.path.isfile(path):
        return None
    try:
        v = _ensure_version_dll()
        size = v.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        data = ctypes.create_string_buffer(size)
        if not v.GetFileVersionInfoW(str(path), 0, size, data):
            return None

        buf = ctypes.c_void_p()
        blen = wintypes.UINT()
        ver = None
        if v.VerQueryValueW(data, "\\", ctypes.byref(buf), ctypes.byref(blen)) \
                and blen.value >= ctypes.sizeof(_VS_FIXEDFILEINFO) and buf:
            fi = ctypes.cast(buf, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
            if fi.dwSignature == 0xFEEF04BD:
                ms, ls = fi.dwFileVersionMS, fi.dwFileVersionLS
                ver = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"

        desc = _query_string(data, "FileDescription")
        if ver is None:
            ver = _query_string(data, "FileVersion")
        if not ver and not desc:
            return None
        return (ver or "", desc or "")
    except Exception:
        return None
