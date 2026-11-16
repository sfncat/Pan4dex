"""Linux 构建脚本的资源清单守卫（待办 T14）。

T14 的现场：构建机为了 Windows 包，把 7z.exe/7z.dll/License.txt 与 Linux 用的 7zz 放在
同一个 `resources/tools/7z/` 目录里；Linux 侧的 `--add-data` 是整目录，于是这三个文件被
一起打进 Linux 包（1.9.050 产物实测多 1,115,840 字节）。Linux 只用 7zz —— 见本文件
`test_linux_only_7zz_is_found_in_the_bundle`，那条是真跑 `core/archive_ops.py` 的判据。

`scripts/build-linux-docker.sh` 是 bash、不能在 Windows 测试里真跑，这里用静态断言钉住
「清单不指整目录」「暂存目录只放 7zz 且在 build/ 下」；产物侧的最终观测量（包内这三个
条目数为 0、7zz 与 exiftool-linux 仍在）记在 docs/todo.md 的 T14 行。
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import archive_ops  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "build-linux-docker.sh")

STAGE_7Z = "resources/tools/7z"


def _script():
    with open(SCRIPT, encoding="utf-8") as f:
        return f.read()


def _add_specs(text):
    """ADD_SPECS=( "src|dst|label" ... ) → [(src, dst, label)]"""
    block = re.search(r"ADD_SPECS=\((.*?)\n\)", text, re.S)
    assert block, "找不到 ADD_SPECS 清单"
    out = []
    for line in re.findall(r'"([^"]*)"', block.group(1)):
        parts = line.split("|")
        assert len(parts) == 3, f"清单条目格式应为 源|包内目标|说明，实际：{line}"
        out.append(tuple(parts))
    return out


def test_no_spec_carries_the_whole_source_7z_directory():
    specs = _add_specs(_script())
    assert [s for s in specs if s[0] == STAGE_7Z] == [], (
        "内置 7z 又退回整目录 --add-data：构建机为 Windows 包放的 7z.exe/7z.dll/"
        "License.txt 会被打进 Linux 包（T14 回归）")


def test_bundled_7z_dir_comes_from_the_staging_copy():
    specs = [s for s in _add_specs(_script()) if s[1] == STAGE_7Z]
    assert len(specs) == 1, f"包内 {STAGE_7Z} 应由唯一一条清单条目提供，实际 {len(specs)} 条"
    stage = specs[0][0]
    assert stage.startswith("build/"), (
        f"暂存目录 {stage} 不在 build/ 下：Linux 构建的 rsync 排除 build/，"
        "放外面会与工作树里的 Windows 专用文件互相污染")


def test_staging_copy_contains_only_7zz():
    text = _script()
    installs = re.findall(r'^\s*install\s+[^\n]*$', text, re.M)
    assert len(installs) == 1, f"7z 暂存应只 install 一个文件，实际 {len(installs)} 条"
    assert installs[0].strip().startswith("install -m 0755")
    assert f"{STAGE_7Z}/7zz " in installs[0], "暂存的必须是 7zz —— Linux 只找这个名字"


def test_no_windows_only_tool_is_staged_for_linux():
    """只看真正干活的那几行（注释里提 Windows 文件名是说明，不算复制）"""
    code = "\n".join(line for line in _script().splitlines()
                     if not line.lstrip().startswith("#"))
    staging = re.findall(r'^\s*(?:install|cp)\s+.*resources/tools/7z.*$', code, re.M)
    assert staging, "找不到 7z 的暂存命令"
    for line in staging:
        assert "7z.exe" not in line and "7z.dll" not in line and "License" not in line, line


def test_staging_is_reset_before_each_build():
    text = _script()
    pos_rm = text.index('rm -rf "$LINUX_7Z_STAGE"')
    pos_install = text.index("install -m 0755")
    assert pos_rm < pos_install, (
        "暂存目录没有先清空：上一次构建留下的文件会继续混进下一个包")


def test_empty_stage_dir_is_removed_when_7zz_absent():
    """7zz 不在时不能留个空目录：下面的 `[ -d "$src" ]` 会判成「带上了」，日志说假话"""
    lines = [ln.strip() for ln in _script().splitlines() if ln.strip()
             and not ln.strip().startswith("#")]
    i = lines.index('if [ -f resources/tools/7z/7zz ]; then')
    block = lines[i:lines.index("fi", i)]
    assert "else" in block, f"缺 else 分支：{block}"
    assert 'rm -rf "$LINUX_7Z_STAGE"' in block[block.index("else"):], (
        f"else 分支没清空暂存目录：{block}")


@pytest.fixture
def fake_bundle(tmp_path, monkeypatch):
    """按脚本产出的包内布局造一个 _MEIPASS，再走 archive_ops 的真实判据"""
    dst = tmp_path / "resources" / "tools" / "7z"
    dst.mkdir(parents=True)
    (dst / "7zz").write_bytes(b"ELF-stub")
    (dst / "7z.exe").write_bytes(b"MZ-stub")      # Windows 专用，Linux 不该看见
    (dst / "7z.dll").write_bytes(b"MZ-stub")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(archive_ops.os, "name", "posix")
    return dst


def test_linux_only_7zz_is_found_in_the_bundle(fake_bundle):
    """T14 的前提：Linux 分支只认 7zz，所以同目录的 Windows 文件带进包里是纯重量"""
    found = archive_ops._resource_7z()
    assert found is not None and os.path.basename(found) == "7zz"
    assert os.path.dirname(found) == str(fake_bundle)


def test_the_same_dir_still_resolves_on_windows(fake_bundle, monkeypatch):
    """反向对照：Windows 侧靠 7z.exe + 同目录 7z.dll —— 不能因为 T14 把它挪走"""
    monkeypatch.setattr(archive_ops.os, "name", "nt")
    found = archive_ops._resource_7z()
    assert found is not None and os.path.basename(found) == "7z.exe"
