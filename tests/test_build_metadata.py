# -*- coding: utf-8 -*-
"""编译时间机制：值来自构建脚本生成的 config/_build_info.py，源码模式回落为空。"""
import pathlib
import shutil
import subprocess
import sys

APP_CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config" / "app_config.py"


def _load(tmp_path, build_time):
    pkg = tmp_path / "cfg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy(APP_CONFIG, pkg / "app_config.py")
    if build_time is not None:
        (pkg / "_build_info.py").write_text(
            f'BUILD_TIME = "{build_time}"\n', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", "import cfg.app_config as m; print(m.BUILD_TIME)"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_build_time_from_generated_module(tmp_path):
    assert _load(tmp_path, "2026-10-30 12:00:00") == "2026-10-30 12:00:00"


def test_build_time_empty_in_source_mode(tmp_path):
    assert _load(tmp_path, None) == ""