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

def _clipboard_write_landed(clip, paths):
    """确认我们写的 URI 确实落到了系统剪贴板（否则说明被其它进程占着）。"""
    urls = clip.mimeData().urls()
    got = {os.path.normcase(u.toLocalFile()) for u in urls}
    want = {os.path.normcase(p) for p in paths}
    return want <= got


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用 DropEffect 格式")
def test_clipboard_cut_roundtrip_prefers_move(qapp):
    import time
    from core.pane import Pane
    from PyQt6.QtWidgets import QApplication
    # _write_system_clipboard 不引用实例属性，用裸实例验证写回→识别往返
    bare = Pane.__new__(Pane)
    paths = [os.path.join(os.path.expanduser("~"), "_pan4dex_cb_probe_a.txt")]

    def _landed_write(is_cut):
        # Windows 剪贴板为全局锁：可能被其它进程/窗口占用，OpenClipboard 会失败。
        # 多次重试；若始终无法写入则判定环境不可用（返回 False），而非误报逻辑失败。
        for _ in range(5):
            bare._write_system_clipboard(paths, is_cut=is_cut)
            qapp.processEvents()
            if _clipboard_write_landed(QApplication.clipboard(), paths):
                return True
            time.sleep(0.1)
        return False

    # 写回“剪切”状态
    if not _landed_write(True):
        pytest.skip("系统剪贴板被其它进程占用，无法完成端到端写入验证")
    assert Pane._clipboard_prefers_move(QApplication.clipboard().mimeData()) is True
    # 写回“复制”状态
    assert _landed_write(False)
    assert Pane._clipboard_prefers_move(QApplication.clipboard().mimeData()) is False



def test_clipboard_prefers_move_none_and_garbage():
    from core.pane import Pane
    assert Pane._clipboard_prefers_move(None) is False
    # 无相关格式的空 MIME 应返回 False 而非抛异常
    from PyQt6.QtCore import QMimeData
    assert Pane._clipboard_prefers_move(QMimeData()) is False


# ---------- 粘贴源裁决：应用内条过期时被外部复制翻盘 ----------

def test_stale_internal_clipboard_loses_to_newer_system_copy():
    """回归（用户现场）：在 pan4dex 复制后，去系统文件管理器复制一张照片，
    Ctrl+V 应粘照片（系统剪贴板），不能再粘应用内那份过期条。

    应用内复制会同步写回系统剪贴板，所以「系统条与内部条不一致」只能
    是外部程序后复制所致 —— 此时必须听系统的。"""
    from core.pane import Pane
    photo = os.path.join(os.path.expanduser("~"), "photo.jpg")
    inner = os.path.join(os.path.expanduser("~"), "doc.txt")
    paths, action, is_move = Pane.choose_paste_source(
        [inner], 'copy', [photo])
    assert paths == [photo]
    assert action == 'system'
    assert is_move is False


def test_matching_system_clipboard_keeps_internal_action_semantics():
    """系统条与内部条一致 = 内部条仍是最新一次复制，沿用内部动作语义
    （内部剪切的 move 靠 Preferred DropEffect 回读会误判，内部条更可信）"""
    from core.pane import Pane
    a = os.path.join(os.path.expanduser("~"), "a.txt")
    b = os.path.join(os.path.expanduser("~"), "b.txt")
    paths, action, is_move = Pane.choose_paste_source([a, b], 'cut', [b, a])
    assert paths == [a, b]
    assert action == 'cut'
    assert is_move is True


def test_non_file_system_clipboard_keeps_internal_priority():
    """系统剪贴板是纯文本/图片（无文件条）时，维持旧优先级用内部条"""
    from core.pane import Pane
    inner = os.path.join(os.path.expanduser("~"), "doc.txt")
    paths, action, _ = Pane.choose_paste_source([inner], 'copy', [])
    assert paths == [inner] and action == 'copy'
    # 两边都空：无粘贴源
    assert Pane.choose_paste_source([], None, []) == ([], None, False)


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
