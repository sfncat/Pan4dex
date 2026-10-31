# -*- coding: utf-8 -*-
"""core/file_version.py：Windows PE 版本资源读取（平铺视图瓦片附注）"""
import os
import re
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 版本资源")


def test_system_dll_reports_version_and_description():
    p = r"C:\Windows\System32\kernel32.dll"
    if not os.path.isfile(p):
        pytest.skip("没有 kernel32.dll")
    from core.file_version import get_version_info
    info = get_version_info(p)
    assert info is not None
    ver, desc = info
    assert re.match(r"^\d+(\.\d+)+$", ver), f"版本号格式异常: {ver!r}"
    assert desc.strip()


def test_explorer_exe_reports_version():
    p = r"C:\Windows\explorer.exe"
    if not os.path.isfile(p):
        pytest.skip("没有 explorer.exe")
    from core.file_version import get_version_info
    info = get_version_info(p)
    assert info is not None
    ver, _ = info
    assert re.match(r"^\d+(\.\d+)+$", ver)


def test_non_pe_file_returns_none(tmp_path):
    from core.file_version import get_version_info
    f = tmp_path / "plain.txt"
    f.write_text("not a PE")
    assert get_version_info(str(f)) is None


def test_missing_file_returns_none():
    from core.file_version import get_version_info
    assert get_version_info(r"C:\definitely\missing.dll") is None
