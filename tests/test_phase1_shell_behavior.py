# -*- coding: utf-8 -*-
"""第一阶段（Shell 行为修复 + SMB 止血）回归测试

覆盖不依赖真实网络/跨卷环境即可验证的逻辑：
- 系统剪贴板 MoveEffect 写回 + 识别往返（1.1）
- 复制保留文件元数据 mtime（1.3）
- 同名冲突决策 skip/replace/keep_both（1.4）
- 移动到自身所在目录 no-op（1.3 附带修复）
- 大目录统计可中断（2.2）
- UNC 前导斜杠还原（2.3）
- PathBar 补全仅列当前目录一层、不递归（3.3）
- 隐藏文件过滤开关切换共享模型 filter（2.3）
"""
import os
import sys
import shutil

import pytest
from PyQt6.QtCore import QDir


# ---------- 1.1 系统剪贴板 Preferred DropEffect 往返 ----------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用 DropEffect 格式")
def test_clipboard_cut_roundtrip_prefers_move(qapp):
    from core.pane import Pane
    from PyQt6.QtWidgets import QApplication
    # _write_system_clipboard 不引用实例属性，用裸实例验证写回→识别往返
    bare = Pane.__new__(Pane)
    paths = [os.path.join(os.path.expanduser("~"), "_pan4dex_cb_probe_a.txt")]
    # 写回“剪切”状态
    bare._write_system_clipboard(paths, is_cut=True)
    mime = QApplication.clipboard().mimeData()
    assert Pane._clipboard_prefers_move(mime) is True
    # 写回“复制”状态
    bare._write_system_clipboard(paths, is_cut=False)
    mime2 = QApplication.clipboard().mimeData()
    assert Pane._clipboard_prefers_move(mime2) is False


def test_clipboard_prefers_move_none_and_garbage():
    from core.pane import Pane
    assert Pane._clipboard_prefers_move(None) is False
    # 无相关格式的空 MIME 应返回 False 而非抛异常
    from PyQt6.QtCore import QMimeData
    assert Pane._clipboard_prefers_move(QMimeData()) is False


# ---------- 1.3 / 1.4 复制元数据 + 冲突决策 ----------

@pytest.fixture
def ops(tmp_path):
    from core.file_operations import FileOperations
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir(); dst.mkdir()
    f = src / "a.txt"
    f.write_text("hello")
    old = 1_000_000_000  # 2001 年
    os.utime(str(f), (old, old))
    o = FileOperations()
    yield o, str(src), str(dst), str(f), old
    shutil.rmtree(str(tmp_path), ignore_errors=True)


def test_copy_preserves_mtime(ops):
    o, src, dst, f, old = ops
    r = o.copy([f], dst)
    assert r.success
    copied = os.path.join(dst, "a.txt")
    assert abs(os.path.getmtime(copied) - old) < 2


def test_conflict_skip(ops):
    o, src, dst, f, old = ops
    o.copy([f], dst)                    # 先创建 dst/a.txt
    o.set_conflict_callback(lambda info: "skip")
    before = set(os.listdir(dst))
    o.copy([f], dst)
    assert set(os.listdir(dst)) == before  # 跳过 → 无新增


def test_conflict_keep_both(ops):
    o, src, dst, f, old = ops
    o.copy([f], dst)
    o.set_conflict_callback(lambda info: "keep_both")
    o.copy([f], dst)
    assert os.path.exists(os.path.join(dst, "a (2).txt"))


def test_conflict_replace(ops):
    o, src, dst, f, old = ops
    # 目标放一个内容不同、mtime 很新的同名文件
    tgt = os.path.join(dst, "a.txt")
    with open(tgt, "w") as fh:
        fh.write("OLD")
    o.set_conflict_callback(lambda info: "replace")
    r = o.copy([f], dst)
    assert r.success
    assert open(tgt).read() == "hello"
    assert abs(os.path.getmtime(tgt) - old) < 2  # 替换后仍是源的时间


# ---------- 1.3 移动到自身所在目录 no-op ----------

def test_move_to_same_dir_noop(ops):
    o, src, dst, f, old = ops
    r = o.move([f], src)               # 移回它自己所在目录
    assert r.success
    assert os.path.exists(f)           # 源文件仍在，未被删除/报错


# ---------- 2.2 统计阶段可中断 ----------

def test_count_interruptible(tmp_path):
    from core.file_operations import FileOperations
    big = tmp_path / "big"
    big.mkdir()
    for i in range(30):
        (big / f"f{i}.dat").write_bytes(b"0" * 1024)
    o = FileOperations()
    o.cancel()
    with pytest.raises(Exception) as ei:
        o._count_files_and_size([str(big)])
    assert type(ei.value).__name__ == "_OperationCancelled"


# ---------- 2.3 UNC 前导斜杠还原 ----------

@pytest.mark.parametrize("given,expected", [
    ("\\\\srv\\share\\a", "\\\\srv\\share\\a"),   # 已正确，不动
    ("\\srv\\share", "\\\\srv\\share"),           # 被压掉的前补回
    ("C:\\x\\y", "C:\\x\\y"),                     # 盘符路径不受影响
])
def test_win_unc_fix(given, expected):
    from core.pane import Pane
    assert Pane._win_unc_fix(given) == expected


# ---------- 3.3 PathBar 补全仅列一层 ----------

def test_completer_non_recursive(qapp, tmp_path):
    from widgets.path_bar import PathBar
    (tmp_path / "keepme.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("y")
    pb = PathBar()
    pb.set_path(str(tmp_path))
    cand = list(pb._completer_model.stringList())
    names = {os.path.basename(c) for c in cand}
    assert "keepme.txt" in names
    assert "sub" in names
    assert "deep.txt" not in names  # 不递归展开子目录


# ---------- 2.3 隐藏文件过滤开关 ----------

def test_show_hidden_filter(qapp, tmp_path):
    from core.pane import Pane
    pane = Pane("t_hidden", start_path=str(tmp_path))
    model = pane.model
    Pane.set_show_hidden(True)
    assert bool(model.filter() & QDir.Filter.Hidden)
    Pane.set_show_hidden(False)
    assert not bool(model.filter() & QDir.Filter.Hidden)
    Pane.set_show_hidden(True)
