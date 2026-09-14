# -*- coding: utf-8 -*-
"""后台线程→主线程投递的生命周期防护（内嵌终端 + 窗格）

背景（v1.9.002 修复的缺陷）：
`TerminalView._read_loop` 在后台线程里直接 `self.output_received.emit(...)` /
`self.process_exited.emit(...)`。控件的 C++ 对象可能在读线程仍存活时被删除
（Windows 上 `pty.read` 无数据即一直阻塞，线程 join 不回来），emit 因此抛
`RuntimeError: wrapped C/C++ object of type TerminalView has been deleted`，
并可能触发 Qt 内部崩溃；同时 shell 子进程没人回收、dock 关闭后重开变成死面板。
`Pane` 的预读拍摄日期/压缩/文件操作线程同类风险，由 `Pane._emit_ui` 兜住。

测试用假 PtyBackend 替身，不真的拉起 shell。
"""
import time

import pytest
from PyQt6 import sip

from widgets import terminal_panel as tp
from widgets.terminal_panel import TerminalView


class _FakePty:
    """PTY 后端替身：read 返回空串令读线程空转，便于观察关停。"""

    instances = []

    def __init__(self, program, cwd=None, cols=100, rows=24, env=None):
        self.terminated = 0
        self.started = False
        _FakePty.instances.append(self)

    def start(self):
        self.started = True

    def read(self, size=4096):
        time.sleep(0.01)
        return ""

    def write(self, data):
        pass

    def setwinsize(self, rows, cols):
        pass

    def is_alive(self):
        return self.terminated == 0

    def terminate(self):
        self.terminated += 1


class _OneShotPty(_FakePty):
    """第一次 read 给出数据、随后 EOF：驱动 `_read_loop` 走完两条投递分支。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent = False

    def read(self, size=4096):
        if not self.sent:
            self.sent = True
            return "hello"
        raise EOFError


class _Signal:
    """记录 emit 调用的最小信号替身。"""

    def __init__(self, boom=False):
        self.calls = []
        self.boom = boom

    def emit(self, *args):
        if self.boom:
            raise RuntimeError("wrapped C/C++ object of type TerminalView has been deleted")
        self.calls.append(args)


class _EmitStub:
    """只借 `_emit_ui` 用到的三个成员，无需真造一个控件。

    `_emit_ui` 按信号**名字** emit，故替身把信号挂在 `probe` 属性上。
    """

    _emit_ui = TerminalView._emit_ui

    def __init__(self, closing, shutdown, sig):
        self._closing = closing
        self._shutdown = shutdown
        self.probe = sig


class _DeadSignalStub(_EmitStub):
    """模拟 C++ 对象已被删除的控件：状态属性仍可读（它们存在 Python 实例字典
    里），但取信号属性会抛 RuntimeError——这正是 `_emit_ui` 把 getattr 放进
    try 里的理由。"""

    def __getattribute__(self, name):
        if name == "probe":
            raise RuntimeError("wrapped C/C++ object of type TerminalView has been deleted")
        return object.__getattribute__(self, name)


@pytest.fixture
def view(qtbot, monkeypatch):
    """TerminalView：`PtyBackend` 换成替身，读线程真实运行但不碰 shell。"""
    _FakePty.instances = []
    monkeypatch.setattr(tp, "PtyBackend", _FakePty)
    v = TerminalView()
    qtbot.addWidget(v)
    v.pities = _FakePty.instances
    return v


# ---------- 跨线程投递防御 ----------

def test_emit_ui_delivers_while_session_alive():
    sig = _Signal()
    _EmitStub(False, False, sig)._emit_ui("probe", "data")
    assert sig.calls == [("data",)]


def test_emit_ui_drops_after_closing_or_shutdown():
    """会话停止/控件终态后不得再投递（读线程可能还卡在阻塞 read 里）。"""
    for closing, shutdown in ((True, False), (False, True), (True, True)):
        sig = _Signal()
        _EmitStub(closing, shutdown, sig)._emit_ui("probe", "late")
        assert sig.calls == []


def test_emit_ui_swallows_deleted_object():
    """信号本身 emit 抛 RuntimeError（对象已死）：必须吞掉，不能炸掉读线程。"""
    sig = _Signal(boom=True)
    _EmitStub(False, False, sig)._emit_ui("probe", "x")      # 不抛即通过


def test_emit_ui_swallows_dead_signal_lookup():
    """连取信号属性都会抛：`getattr` 必须在 try 内，否则防护形同虚设。

    （反面教材：调用点写 `self._emit_ui(self.output_received, data)` 时，
    RuntimeError 在进函数前的参数求值阶段就抛了。）
    """
    _DeadSignalStub(False, False, None)._emit_ui("probe", "x")


def test_read_loop_stops_after_backend_cleared(view, qtbot):
    """`close_shell()` 置空 _backend：读线程下一轮即退出，不再 emit。"""
    reader = view._reader
    assert reader is not None and view._backend is view.pities[-1]
    view.close_shell()
    qtbot.waitUntil(lambda: not view._reader.is_alive(), timeout=3000)
    assert view._reader is reader                        # 线程对象未被替换
    assert view.pities[-1].terminated == 1               # shell 已回收


# ---------- 会话关停 ----------

def test_close_shell_stops_backend_and_timers(view):
    view._alive_timer.start(500)
    view._render_timer.start(500)

    view.close_shell()

    assert view._backend is None
    assert view._closing is True and view._shutdown is False
    assert not view._alive_timer.isActive()
    assert not view._render_timer.isActive()
    assert view.pities[-1].terminated == 1
    view.close_shell()                                   # 重复调用不抛、不重复 terminate
    assert view.pities[-1].terminated == 1


def test_shutdown_blocks_restart(view):
    """主窗口关闭后的终态：不得再拉起会话（否则残留无人回收的子进程）。"""
    view.close_shell(shutdown=True)
    assert view._shutdown is True
    count = len(view.pities)

    view.restart(cwd="C:/")
    view._start_shell()
    assert view._backend is None
    assert len(view.pities) == count                     # 没有新 shell


def test_stop_without_shutdown_allows_restart(view):
    """dock 的 X 只隐藏面板：会话可重启，重开终端不该是死面板。"""
    view.close_shell()
    assert view._shutdown is False

    view.restart()
    assert len(view.pities) == 2
    assert view._backend is view.pities[-1]
    assert view._closing is False                        # _start_shell 成功后复位


def test_destroyed_hook_terminates_backend(view):
    """兜底钩子本身的行为：回收 backend + 置终态（真销毁路径见下面两个测试）。"""
    backend = view._backend
    view._on_destroyed()
    assert backend.terminated == 1
    assert view._shutdown is True and view._backend is None


def test_real_deletion_triggers_hook_and_emit_guard(qtbot, monkeypatch):
    """真删除 C++ 对象：`destroyed` 兜底钩子必须回收 shell，且 emit 防护必须吞异常。

    这正是“读线程卡在阻塞 read、主窗口已销毁”的真实场景。
    不用 qtbot.addWidget，避免测试末尾再对已删除控件做清理。
    """
    _FakePty.instances = []
    monkeypatch.setattr(tp, "PtyBackend", _FakePty)
    v = TerminalView()
    backend = v._backend
    assert backend is not None

    sip.delete(v)                                  # 立即销毁 C++ 对象
    assert v._shutdown is True and v._backend is None
    assert backend.terminated == 1                 # 兜底钩子已回收 shell

    # 模拟极端竞态：读线程刚好越过标志检查，而控件已没
    v._closing = False
    v._shutdown = False
    with pytest.raises(RuntimeError):
        getattr(v, "output_received")              # 前提：对象确实已死
    v._emit_ui("output_received", "x")             # 防护：不得抛出异常


def test_read_loop_on_deleted_widget_returns_quietly(qtbot, monkeypatch):
    """读线程跑到 emit 时控件已没：整条 `_read_loop` 必须安静返回。

    旧实现会在这里抛 RuntimeError，被线程默认 excepthook 打到 stderr（即
    全量测试里反复出现的 “wrapped C/C++ object of type TerminalView has been
    deleted”），并带走一批未渲染的终端输出。
    """
    _FakePty.instances = []
    monkeypatch.setattr(tp, "PtyBackend", _FakePty)
    v = TerminalView()
    sip.delete(v)

    data = _OneShotPty("stub")
    v._backend = data                     # Python 属性仍可写：模拟线程已持有 backend
    v._closing = False
    v._shutdown = False
    v._read_loop()                        # 不抛即通过：一次输出 + EOF 后退出
    assert data.sent is True


def test_parent_deletion_also_reclaims_shell(qtbot, monkeypatch):
    """主窗口销毁带走子控件（应用退出的真实路径）时同样回收。"""
    from PyQt6.QtWidgets import QWidget
    _FakePty.instances = []
    monkeypatch.setattr(tp, "PtyBackend", _FakePty)
    win = QWidget()
    v = TerminalView(parent=win)
    backend = v._backend
    assert backend is not None
    sip.delete(win)
    assert v._shutdown is True
    assert backend.terminated == 1


# ---------- 窗格的同类防护 ----------

def test_pane_emit_ui_survives_deleted_widget(qtbot, tmp_path):
    """Pane 后台任务（预读/压缩/复制）在窗格销毁后投递：必须静默。

    关闭标签页/退出应用时，那些线程不会也不能被“卡住等 join”，只可能带着
    已失效的 self 继续跑，所以只能靠投递入口的防护。
    """
    from core.pane import Pane
    p = Pane("t_emit", start_path=str(tmp_path))
    p._emit_ui("shot_dates_ready")                 # 存活期：正常投递不抛

    sip.delete(p)
    with pytest.raises(RuntimeError):
        getattr(p, "shot_dates_ready")             # 前提：C++ 对象确实已没
    p._emit_ui("shot_dates_ready")                 # 防护：不得抛出异常
    p._emit_ui("_file_progress", 50, "f.txt", 1, 2)
