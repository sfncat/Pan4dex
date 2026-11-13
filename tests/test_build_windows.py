"""构建脚本的两条回归守卫（待办 T12/T13）。

scripts/build_windows.py 顶层就会真跑构建，不能 import；这里用 ast 取真实源码来验，
不 mock 被测行为本身。
"""
import ast
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_windows.py"


def _tree():
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


def _called(stmts):
    names = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    names.add(func.attr)
    return names


def _load_function(name):
    node = next(n for n in _tree().body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {"pathlib": pathlib}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SCRIPT), "exec"), namespace)
    return namespace[name]


def test_restore_runs_even_when_pyinstaller_fails():
    """T12：还原必须在覆盖 PyInstaller 调用的 finally 里，失败路径才执行得到。"""
    tries = [n for n in ast.walk(_tree())
             if isinstance(n, ast.Try) and "run" in _called(n.body)]
    assert tries, "找不到跑 PyInstaller 的 try 块"
    assert any("_restore_linux_binaries" in _called(t.finalbody) for t in tries), (
        "_restore_linux_binaries() 不在 finally 里：构建失败时 Linux 二进制留在 build/，"
        "下一次 Linux 包静默缺 ExifTool（gotchas #66）")


@pytest.fixture
def tools_dir(tmp_path):
    d = tmp_path / "tools"
    (d / "exiftool").mkdir(parents=True)
    (d / "exiftool" / "exiftool.exe").write_bytes(b"stub")
    (d / "7z").mkdir()
    return d


def _warnings(tools_dir):
    return _load_function("_missing_tool_warnings")(tools_dir)


def test_warns_when_only_linux_7zz_is_deployed(tools_dir):
    """T13 现场：构建机只部署了 Linux 的 7zz，Windows 包的第三级兜底为空。"""
    (tools_dir / "7z" / "7zz").write_bytes(b"stub")
    msgs = _warnings(tools_dir)
    assert any("7-Zip" in m for m in msgs)
    assert not any("ExifTool" in m for m in msgs)


def test_no_warning_with_standalone_7za(tools_dir):
    (tools_dir / "7z" / "7za.exe").write_bytes(b"stub")
    assert _warnings(tools_dir) == []


def test_no_warning_with_full_7z(tools_dir):
    (tools_dir / "7z" / "7z.exe").write_bytes(b"stub")
    (tools_dir / "7z" / "7z.dll").write_bytes(b"stub")
    assert _warnings(tools_dir) == []


def test_7z_exe_without_dll_still_warns(tools_dir):
    """_resource_7z() 会跳过缺 7z.dll 的完整版，检查必须用同一判据。"""
    (tools_dir / "7z" / "7z.exe").write_bytes(b"stub")
    assert any("7-Zip" in m for m in _warnings(tools_dir))


def test_warns_when_exiftool_missing(tools_dir):
    (tools_dir / "exiftool" / "exiftool.exe").unlink()
    (tools_dir / "7z" / "7za.exe").write_bytes(b"stub")
    msgs = _warnings(tools_dir)
    assert any("ExifTool" in m for m in msgs)
    assert not any("7-Zip" in m for m in msgs)