"""
Pan4dex 万格 — 延迟回调（call_later）的生命周期回归测试

覆盖的缺陷：启动阶段用 `QTimer.singleShot(ms, lambda: self.xxx())` 排定的延后
工作，其定时器不属于业务对象；对象在回调触发前被销毁时回调照跑，访问已删除的
子对象抛 `RuntimeError: wrapped C/C++ object of type ... has been deleted`
（表现为偶发 access violation）。`core.lifecycle.call_later` 把定时器作为对象
的子对象，随对象一起销毁。
"""
import sys
from contextlib import contextmanager

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QWidget

from core.lifecycle import call_later


@pytest.fixture
def fired():
    """记录回调是否执行（回调抛异常时也记录，便于断言“安静地不执行”）"""
    calls = []
    yield calls
    calls.clear()


@contextmanager
def qt_exceptions():
    """收集 PyQt6 在 Qt 事件循环里捕获的未处理 Python 异常。

    槽函数里抛出的异常不会传播回调用方，而是交给 sys.excepthook；不接管它就会
    只是打印到 stderr，测试里看不住。
    """
    saved = sys.excepthook
    errors = []
    sys.excepthook = lambda etype, value, tb: errors.append(value)
    try:
        yield errors
    finally:
        sys.excepthook = saved


def test_callback_runs_when_receiver_alive(qapp, qtbot, fired):
    w = QWidget()
    call_later(w, 10, lambda: fired.append(1))
    qtbot.wait(120)
    assert fired == [1]


def test_repeating_single_shot_semantics(qapp, qtbot, fired):
    """多个延后回调各自独立触发（替换 QTimer.singleShot 后语义不变）"""
    w = QWidget()
    call_later(w, 10, lambda: fired.append("a"))
    call_later(w, 30, lambda: fired.append("b"))
    qtbot.wait(150)
    assert fired == ["a", "b"]


def test_callback_dropped_when_receiver_deleted(qapp, qtbot, fired):
    """对象销毁后回调不再触发 —— 直接访问子控件也不会在已删除对象上执行"""
    w = QWidget()
    child = QLabel("x", w)

    def cb():
        fired.append(child.text())

    call_later(w, 20, cb)
    sip.delete(w)
    qtbot.wait(150)
    assert fired == []


def test_callback_dropped_when_receiver_deleted_with_parent(qapp, qtbot, fired):
    """随父窗口销毁（而非自己被关闭）同样要丢弃回调"""
    parent = QWidget()
    w = QWidget(parent)
    call_later(w, 20, lambda: fired.append(1))
    sip.delete(parent)
    qtbot.wait(150)
    assert fired == []


def test_static_single_shot_is_the_broken_baseline(qapp, qtbot, fired):
    """反证：不挂父对象的 QTimer.singleShot 在对象销毁后照样触发并抛错

    这条记录的是修复前的行为，用于说明 call_later 的必要性（若哪天 PyQt/Qt
    改变了语义，此测试会先失败并提醒我们复核）。
    """
    w = QWidget()
    child = QLabel("x", w)
    QTimer.singleShot(20, lambda: fired.append(child.text()))
    sip.delete(w)
    with qt_exceptions() as errors:
        qtbot.wait(150)
    assert fired == []                 # 回调确实触发了
    assert errors, "基线行为已变化：singleShot 不再对已删除对象执行回调"
    assert "has been deleted" in str(errors[0])


def test_main_window_pending_callbacks_after_deletion(qapp, qtbot):
    """真机路径：主窗口在延迟初始化（250/300/400ms）完成前被销毁，不得报错

    覆盖 core/main_window.py 的全部延后调度点（_deferred_init /
    _create_remaining_panes / _create_tree_sidebar_lazy /
    _create_terminal_panel_lazy / _restore_splitter_sizes / 布局轮询）。
    """
    from core.main_window import MainWindow

    win = MainWindow()
    win.show()
    qtbot.wait(60)                      # 让 0ms 的 _deferred_init 先落地
    sip.delete(win)
    with qt_exceptions() as errors:
        qtbot.wait(900)                 # 跨过最长的 400ms 调度 + 布局轮询
    assert errors == [], f"延迟回调在已销毁窗口上执行: {errors!r}"
