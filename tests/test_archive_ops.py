"""包内 7-Zip 兜底（待办 T13）：没装系统 7-Zip 的机器也要能压缩/解压。

观测量取「find_7z() 究竟解析到哪个可执行文件」，改前改后有区分力：
包内什么都不带时返回 None —— 那正是 1.9.049 及之前 Windows 包的实况。
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import archive_ops

pytestmark = pytest.mark.skipif(os.name != "nt", reason="包内 Windows 版兜底只在 nt 分支上有意义")


@pytest.fixture
def bundled(tmp_path, monkeypatch):
    """把非冻结根目录指到 tmp，并屏蔽系统 PATH 与 Program Files 里的 7-Zip。"""
    (tmp_path / "core").mkdir()
    monkeypatch.setattr(archive_ops, "__file__", str(tmp_path / "core" / "archive_ops.py"))
    monkeypatch.setattr(archive_ops.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.setattr(archive_ops, "_7Z_PATH", None)
    monkeypatch.setattr(archive_ops, "_7Z_VERSION", None)
    z = tmp_path / "resources" / "tools" / "7z"
    z.mkdir(parents=True)
    return z


def test_nothing_bundled_means_no_7z(bundled):
    assert archive_ops.find_7z() is None


def test_bundled_full_7z_is_found(bundled):
    (bundled / "7z.exe").write_bytes(b"stub")
    (bundled / "7z.dll").write_bytes(b"stub")
    assert archive_ops.find_7z() == str(bundled / "7z.exe")


def test_bundled_standalone_7za_is_found(bundled):
    (bundled / "7za.exe").write_bytes(b"stub")
    assert archive_ops.find_7z() == str(bundled / "7za.exe")


def test_full_7z_wins_over_standalone(bundled):
    for name in ("7z.exe", "7z.dll", "7za.exe"):
        (bundled / name).write_bytes(b"stub")
    assert archive_ops.find_7z() == str(bundled / "7z.exe")


def test_7z_exe_without_dll_is_skipped(bundled):
    (bundled / "7z.exe").write_bytes(b"stub")
    assert archive_ops.find_7z() is None


def test_7z_exe_without_dll_falls_back_to_7za(bundled):
    (bundled / "7z.exe").write_bytes(b"stub")
    (bundled / "7za.exe").write_bytes(b"stub")
    assert archive_ops.find_7z() == str(bundled / "7za.exe")