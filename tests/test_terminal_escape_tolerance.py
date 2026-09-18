# -*- coding: utf-8 -*-
"""内嵌终端对 pyte 未实现转义序列的容忍（v1.9.019）

真机现场（Linux 230，v1.9.018）：在内嵌终端里启动 vim，dock 完全不显示 vim 的
界面（画面停在上一条命令的 shell 历史上），而 htop / less 一切正常。产物自己的
stderr 里只有一条 traceback：

    File "widgets/terminal_panel.py", line 451, in _on_output
    File "pyte/streams.py", line 205, in feed
    File "pyte/streams.py", line 353, in _parser_fsm
    TypeError: Screen.select_graphic_rendition() got an unexpected keyword argument 'private'

pyte 派发带私有标记的 CSI 序列（`CSI ? … <字母>`）时无条件传 `private=True`，
但它自己有一批处理函数不收这个参数；vim 启动时恰好发了 `CSI ? … m`。异常逃出
`Stream.feed` 之后，pyte 重置状态机、**当前这一段 PTY 输出整段被丢** —— vim 的
首屏（整屏绘制）就此消失，此后它只发增量，画面永远错位。htop/less 不发这条
序列，所以看起来"只有 vim 不行"。

修复两层：`TerminalScreen` 把这些序列剥掉私有标记后照常执行（参数仍生效）；
`_on_output` 里的 `feed` 加容错，未来任何一帧解析失败都不许再把整段输出带走。
"""
import pytest
import pyte

from widgets import terminal_panel as tp
from widgets.terminal_panel import TerminalScreen, _private_intolerant_csi_handlers


def feed_to_screen(data, cols=80, rows=10):
    """造一个容错屏幕喂 data，返回 (screen, 渲染出的非空行列表)"""
    screen = TerminalScreen(cols, rows, history=200)
    pyte.Stream(screen).feed(data)
    rows_text = [line.rstrip() for line in screen.display]
    return screen, [line for line in rows_text if line]


# 旧版 pyte（0.8.0 / 0.8.2 实测一致）会让 `Stream.feed` 抛 TypeError 的那一类
CRASHING_SEQUENCES = [
    "\x1b[?m",              # 私有标记 + SGR：真机 vim 的肇事者（select_graphic_rendition）
    "\x1b[?0m",
    "\x1b[?7m",
    "\x1b[?6n",             # 扩展光标位置报告 DECXCPR（report_device_status）
]

# 同样冷门、但不依赖具体渲染结果的序列（不同 pyte 版本对这些的处理就不一样）
ODD_SEQUENCES = [
    "\x1b[?u",              # 光标形状：pyte 的 CSI 表里根本没有 → 走 debug 分支
    "\x1b[?4;1$y",          # 带私有标记的 `$` 系列：0.8.0 与 0.8.2 连吞不吞都不一致
    "\x1b[?1049h",          # 备用屏切换：pyte 收下但不实现
    "\x1b[>4;2m",           # 二级标记 + SGR
]


def parent_raises_about_private(seq):
    """确认这条序列在原生 `pyte.HistoryScreen` 上确实会因 `private` 抛"""
    try:
        pyte.Stream(pyte.HistoryScreen(80, 10)).feed(seq)
    except TypeError as e:
        return "private" in str(e)
    return False


# ---------- 屏幕层：序列被忽略，输出不丢 ----------

def test_private_sgr_does_not_eat_the_rest_of_the_chunk():
    """核心断言：肇事序列前后的文本都还在（旧实现里后半段随异常一起没了）。"""
    _, lines = feed_to_screen("AAA\x1b[?mBBB")
    assert lines == ["AAABBB"]


@pytest.mark.parametrize("seq", CRASHING_SEQUENCES)
def test_private_csi_is_ignored_not_fatal(seq):
    """每条会崩的私有序列单独喂都不抛，且之后的输出照常渲染。"""
    _, lines = feed_to_screen(f"{seq}after-seq")
    assert lines == ["after-seq"]


@pytest.mark.parametrize("seq", ODD_SEQUENCES)
def test_odd_sequences_never_eat_the_following_output(seq):
    """只要求「不崩 + 后续输出还在」：各 pyte 版本对这些序列的处理不一致。"""
    _, lines = feed_to_screen(f"{seq}after-seq")
    assert any("after-seq" in line for line in lines)


def test_vim_like_startup_blob_paints_its_screen():
    """按真机抓到的 vim 启动流形状造一个整屏绘制：中间夹着 `CSI ? m`、DCS、
    `CSI >c`、OSC 颜色查询、`CSI %m` 等 pyte 不认的东西，屏幕仍要画出内容。
    """
    blob = (
        "\x1b[?1049h\x1b[?1h\x1b[?2004h"                  # 进备用屏 / 应用光标键
        "\x1b[?12;?25$s" "\x1b[>c" "\x1b]10;?\x07" "\x1b]11;?\x07"
        "\x1b[2;1H\x1b[6n\x1b[2;1H  \x1b[3;1H\x1bPzz\x1b\\"
        "\x1b[0m\x1b[?m\x1b[6n\x1b[3;1H           \x1b[1;1H"   # ← 肇事的那一条就在中间
        "AAA-line\r\nBBB-line\r\nCCC-line"
        "\x1b[94m~\x1b[m\x1b[4;1H" "\x1b]1;vim\x07"
        '"~/tmp/f.txt" 3L, 27B'
    )
    _, lines = feed_to_screen(blob)
    assert "AAA-line" in lines[0]
    assert "BBB-line" in lines[1]
    assert "CCC-line" in lines[2]
    assert any("~/tmp/f.txt" in line for line in lines)


@pytest.mark.parametrize("attr", _private_intolerant_csi_handlers())
def test_every_tolerated_handler_now_accepts_private(attr):
    """把 18 个处理函数逐个按 `private=True` 点一遍：不再因 `private` 抛。

    不通过转义序列走，是为了不依赖每个函数的参数个数（它们本身就不一样）；
    缺参数是 pyte 一贯的行为，不是本次要修的东西。
    """
    screen = TerminalScreen(80, 10, history=200)
    try:
        getattr(screen, attr)(private=True)
    except TypeError as e:
        assert "private" not in str(e), f"{attr} 仍然不接 private：{e}"


@pytest.mark.parametrize("seq", CRASHING_SEQUENCES)
def test_parents_raise_where_we_tolerate(seq):
    """反面确认现场仍然成立：同样的输入给 `pyte.HistoryScreen` 就是要抛。

    上游若哪天修好，本用例转为 skip —— 我们的容错变成空转，不算回归。
    """
    if not parent_raises_about_private(seq):
        pytest.skip(f"这版 pyte 对 {seq!r} 已经不抛，容错层对它是空转")


def test_every_selected_handler_is_actually_wrapped():
    """筛出来的名单必须真的挂到了子类上（签名变了也不能静默失效）。"""
    names = _private_intolerant_csi_handlers()
    assert names, "按签名筛出空名单：pyte 结构变了，容错层已经不起作用"
    missing = [n for n in names if n not in TerminalScreen.__dict__]
    assert missing == []
    # 名单只可能来自 pyte 自己的 CSI 表，不会误伤别的方法
    assert set(names) <= set(pyte.Stream.csi.values())


# ---------- 控件层：一帧解析失败不许带走输出、不许逃进 Qt ----------

class _BoomStream:
    def __init__(self):
        self.calls = 0

    def feed(self, data):
        self.calls += 1
        raise RuntimeError("模拟 pyte 解析失败")


class _FakePty:
    def __init__(self, program, cwd=None, cols=100, rows=24, env=None):
        pass

    def start(self):
        pass

    def read(self, size=4096):
        return ""

    def write(self, data):
        pass

    def setwinsize(self, rows, cols):
        pass

    def is_alive(self):
        return True

    def terminate(self):
        pass


@pytest.fixture
def view(qtbot, monkeypatch):
    monkeypatch.setattr(tp, "PtyBackend", _FakePty)
    v = tp.TerminalView()
    qtbot.addWidget(v)
    return v


def test_feed_failure_never_escapes_the_slot(view):
    """`_on_output` 是 Qt 槽：异常逃出去就被 excepthook 吞掉，那一帧永久丢失。"""
    view._stream = _BoomStream()
    view._on_output("whatever")                     # 不抛即通过
    assert view._stream.calls == 1
    assert view._feed_errors == 1


def test_feed_failure_still_schedules_a_render(view):
    """崩了也要重绘：pyte 在抛之前已经处理掉的那部分得画出来。"""
    view._render_pending = False
    view._render_timer.stop()
    view._stream = _BoomStream()
    view._on_output("whatever")
    assert view._render_pending is True
    assert view._render_timer.isActive()


def test_good_frames_still_render_after_a_bad_one(view):
    """丢一帧不等于终端报废：后续正常输出照常上屏。"""
    view._stream = _BoomStream()
    view._on_output("boom")
    view._stream = pyte.Stream(view._screen)
    view._on_output("ls /tmp\r\n")
    view._force_render()
    assert "ls /tmp" in view.toPlainText()


def test_restart_rebuilds_the_tolerant_screen(view):
    view._feed_errors = 7
    view.restart()
    assert isinstance(view._screen, TerminalScreen)
    assert view._feed_errors == 0
