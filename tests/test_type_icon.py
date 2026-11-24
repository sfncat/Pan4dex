# -*- coding: utf-8 -*-
"""type_icon 的文件类型图标查询（gotchas #70）。

核心回归：Windows 上按扩展名取图标必须走 SHGetFileInfoW + 伪文件名 +
SHGFI_USEFILEATTRIBUTES，绝不把真实（可能是 SMB/UNC）路径交给 shell——
真实路径会让 shell 逐个调用注册的图标覆盖处理器（OneDrive/百度网盘等），
任一处理器的跨进程 COM RPC 卡住，UI 线程就跟着无限等待。

系统调用经 core.dir_model._SHELL_ICON_API 惰性单例注入口出去，测试塞假 API
即可断言「交给 shell 的到底是什么」，不依赖真机装了哪些云盘、也不碰用户 NAS。
"""
import ctypes

import pytest
from PyQt6.QtGui import QIcon, QPixmap, QImage

from conftest import qt_exceptions  # noqa: F401 —— 全局 Qt 异常钩子
from core import dir_model as dm


class _FakeShellIconApi:
    """记录每次 icon_for_ext 收到的扩展名，返回可配置的 QIcon。"""

    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def icon_for_ext(self, ext):
        self.calls.append(ext)
        return self.result


@pytest.fixture
def icon_state():
    """隔离类型图标的缓存与注入口（两者都是类级/模块级单例）。"""
    old_cache = dict(dm.DirStoreModel._ICON_CACHE)
    old_api = dm._SHELL_ICON_API[0]
    dm.DirStoreModel._ICON_CACHE.clear()
    dm._SHELL_ICON_API[0] = None
    yield
    dm.DirStoreModel._ICON_CACHE.clear()
    dm.DirStoreModel._ICON_CACHE.update(old_cache)
    dm._SHELL_ICON_API[0] = old_api


def _solid_icon():
    return QIcon(QPixmap(8, 8))


def test_type_icon_passes_only_extension_not_real_path(icon_state):
    """交给 shell API 的只有扩展名——真实 UNC 路径绝不外泄给图标覆盖处理器。"""
    api = _FakeShellIconApi(result=_solid_icon())
    dm._SHELL_ICON_API[0] = api
    unc = r"\\192.168.5.206\4t_tp3\Album\OurLife\photo.JPG"

    dm.type_icon(unc, False)

    assert api.calls == [".jpg"], "必须按扩展名缓存、且只把扩展名交给 shell，不得传真实路径"


def test_type_icon_caches_per_extension(icon_state):
    """同一扩展名只查一次 shell；不同扩展名各查一次；目录完全不查。"""
    api = _FakeShellIconApi(result=_solid_icon())
    dm._SHELL_ICON_API[0] = api

    dm.type_icon(r"N:\a\one.txt", False)
    dm.type_icon(r"\\192.168.5.58\share\two.txt", False)   # 同扩展名、不同慢位置
    dm.type_icon(r"C:\three.jpg", False)
    dm.type_icon(r"C:\a_dir", True)                        # 目录走 StandardPixmap

    assert api.calls == [".txt", ".jpg"]


def test_type_icon_falls_back_when_api_returns_none(icon_state):
    """shell 查询失败（无关联/异常）回退通用文件图标，不返回 None、不往外抛。"""
    dm._SHELL_ICON_API[0] = _FakeShellIconApi(result=None)
    icon = dm.type_icon(r"N:\weird.unknownext", False)
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_type_icon_falls_back_when_api_raises(icon_state):
    """假 API 抛异常时安全网生效：仍返回非空图标，列表不受影响。"""

    class _RaisingApi:
        def icon_for_ext(self, ext):
            raise OSError("shell overlay RPC hung")

    dm._SHELL_ICON_API[0] = _RaisingApi()
    icon = dm.type_icon(r"\\192.168.5.206\x.psd", False)
    assert not icon.isNull()


def test_directory_never_touches_shell_api(icon_state):
    """目录图标走 Qt 内置 StandardPixmap，任何情况下都不查 shell。"""
    class _BoomApi:
        def icon_for_ext(self, ext):
            raise AssertionError("目录图标不许调 shell")

    dm._SHELL_ICON_API[0] = _BoomApi()
    icon = dm.type_icon(r"\\192.168.5.206\4t_tp3", True)
    assert not icon.isNull()


def test_shfileinfo_layout_dump():
    """结构体偏移以探针 dump 为准（#68），不按头文件手抄。"""
    if not hasattr(ctypes, "WinDLL") or dm.sys.platform != "win32":
        pytest.skip("SHFILEINFOW 仅在 Windows 上实例化")
    assert ctypes.sizeof(dm._SHFILEINFOW) == 696
    assert dm._SHFILEINFOW.hIcon.offset == 0
    assert dm._SHFILEINFOW.iIcon.offset == 8
    assert dm._SHFILEINFOW.dwAttributes.offset == 12
    assert dm._SHFILEINFOW.szDisplayName.offset == 16
    assert dm._SHFILEINFOW.szTypeName.offset == 536


def test_windows_api_uses_fake_name_and_use_file_attributes(icon_state, monkeypatch):
    """决定性用例：Windows 路径下传给 SHGetFileInfoW 的是伪名 + USEFILEATTRIBUTES。

    对照组（把实现换回 QFileIconProvider.icon(QFileInfo(真实路径))）时，此用例
    因捕获不到 _get 调用而红——证明用例对这些码有区分力。
    """
    if dm.sys.platform != "win32":
        pytest.skip("仅 Windows")

    api = dm._WindowsShellIconApi()
    captured = []
    real_get = api._get

    def _spy(fname, attrs, info_ptr, size, flags):
        captured.append((fname, attrs, flags))
        return real_get(fname, attrs, info_ptr, size, flags)

    monkeypatch.setattr(api, "_get", _spy)
    dm._SHELL_ICON_API[0] = api

    icon = dm.type_icon(r"\\\\192.168.5.206\\4t_tp3\\a.jpg", False)

    assert captured, "必须真的调了 SHGetFileInfoW"
    assert len(captured) == 2, "大/小图标各查一次"
    for fname, attrs, flags in captured:
        assert "192.168" not in fname and "\\" not in fname
        assert fname.endswith(".jpg")
        assert attrs == 0x80                                   # FILE_ATTRIBUTE_NORMAL
        assert flags & 0x10                                    # SHGFI_USEFILEATTRIBUTES
        assert flags & 0x100                                   # SHGFI_ICON
    assert not icon.isNull()
