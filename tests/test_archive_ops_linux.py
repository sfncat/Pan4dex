# -*- coding: utf-8 -*-
"""Linux 压缩/解压兜底：目标机没装系统 7z 时，必须能用仓库内的 7zz。

root cause：find_7z() 原来三级兜底全空（系统 PATH 没有 + 内置 7zz 未入库），
菜单项还在但一点就报「未找到 7-Zip」——用户看到的就是「功能没了」。
这里既钉运行时查找逻辑，也钉「7zz 与 LGPL 许可证确实进了仓库」这件事本身。
"""
import os
import pathlib

from core import archive_ops

_REPO_7Z = pathlib.Path(__file__).resolve().parents[1] / "resources" / "tools" / "7z"


def _isolate(monkeypatch, tmp_path):
    """把非冻结根目录指到 tmp，屏蔽系统 PATH 与 Windows 安装目录。"""
    (tmp_path / "core").mkdir(exist_ok=True)
    monkeypatch.setattr(archive_ops, "__file__", str(tmp_path / "core" / "archive_ops.py"))
    monkeypatch.setattr(archive_ops.shutil, "which", lambda name: None)
    monkeypatch.setattr(archive_ops, "_7Z_PATH", None)
    monkeypatch.setattr(archive_ops, "_7Z_VERSION", None)
    monkeypatch.setattr(os, "name", "posix")
    return tmp_path / "resources" / "tools" / "7z"


def test_bundled_7zz_is_found_when_system_has_none(monkeypatch, tmp_path):
    """对照区分力：不入库时 find_7z() 返回 None（旧行为），入库后命中内置路径"""
    z = _isolate(monkeypatch, tmp_path)
    assert archive_ops.find_7z() is None          # 空目录：复现旧故障

    exe = z / "7zz"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"stub")
    monkeypatch.setattr(archive_ops, "_7Z_PATH", None)  # 真实进程只探测一次，这里模拟新进程重启
    found = archive_ops.find_7z()
    assert found == str(exe)
    assert os.access(exe, os.X_OK), "打包解出的 7zz 可能丢执行位，find_7z 必须补回来"


def test_repository_actually_carries_7zz():
    """守卫入库本身：.gitignore 放行规则若被改回去，这条立刻红"""
    exe = _REPO_7Z / "7zz"
    assert exe.is_file(), "resources/tools/7z/7zz 必须入库，否则 Linux 包无兜底"
    assert exe.stat().st_size > 1_000_000, "7zz 不像完整的官方二进制"
    with exe.open("rb") as f:
        assert f.read(4) == b"\x7fELF", "7zz 必须是 Linux ELF，不能是下载页/占位文件"


def test_repository_carries_lgpl_license():
    """7-Zip 是 LGPL，分发二进制要随附许可证"""
    assert (_REPO_7Z / "License-7zip-linux.txt").is_file()
