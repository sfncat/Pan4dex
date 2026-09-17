"""
Pan4dex 万格 — 延迟回调（call_later）的生命周期回归测试

覆盖的缺陷：启动阶段用 `QTimer.singleShot(ms, lambda: self.xxx())` 排定的延后
工作，其定时器不属于业务对象；对象在回调触发前被销毁时回调照跑，访问已删除的
子对象抛 `RuntimeError: wrapped C/C++ object of type ... has been deleted`
（表现为偶发 access violation）。`core.lifecycle.call_later` 把定时器作为对象
的子对象，随对象一起销毁。
"""
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QWidget

from conftest import qt_exceptions
from core.lifecycle import call_later


@pytest.fixture
def fired():
    """记录回调是否执行（回调抛异常时也记录，便于断言“安静地不执行”）"""
    calls = []
    yield calls
    calls.clear()


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
    # 不等固定时长：全量测试负载高时定时器会晚于 150ms 到（实测偶发只剩一条），
    # 也不能断言到达顺序（同一轮里两个定时器谁先派发不保证）
    qtbot.waitUntil(lambda: len(fired) >= 2, timeout=3000)
    assert sorted(fired) == ["a", "b"]


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


def test_closed_tab_widget_outlives_its_python_wrapper(qapp, qtbot):
    """关掉的标签页不得因为“Python 包装器被回收”就当场销毁 C++ 对象。

    `removeTab` 把 widget 的 C++ 父指针置空，从那刻起 sip 按“Python 拥有它”处理：
    包装器一被回收就 delete C++，级联拆光它的子控件。而包装器何时回收不确定（信号→
    绑定方法的引用环要等分代 GC，GC 又可以在任意 Python 分配点执行）—— 实测：它插在
    另一个窗格的构造途中，就报随机的 `wrapped C/C++ object of type QVBoxLayout has been
    deleted`，更坏时直接 access violation。正确做法：握住 Python 引用 + `deleteLater`，
    把销毁时机交给事件循环（实测：只 `setParent` 归还所有权拦不住）。
    """
    import gc
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent
    from core.main_window import MainWindow, QuadPaneWidget

    win = MainWindow()
    qtbot.addWidget(win)
    win.new_tab()
    idx = win.tab_widget.count() - 1
    assert idx >= 1
    victim = win.tab_widget.widget(idx)
    win.close_tab(idx)
    # 前置条件：已从标签里移出（不再属于 tab_widget），但对象还活着
    assert victim not in [win.tab_widget.widget(i)
                          for i in range(win.tab_widget.count())]
    assert not sip.isdeleted(victim)

    before = len(win.findChildren(QuadPaneWidget))
    del victim                          # 测试侧唯一的引用消失
    gc.collect()                        # 旧写法：C++ 对象就在这一步被删
    assert len(win.findChildren(QuadPaneWidget)) == before, \
        "标签页 widget 随 Python 包装器一起被删（销毁时机交给了 GC）"

    # 销毁由事件循环确定：`processEvents()` 不处理 deferred delete，要显式派发
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
    assert len(win.findChildren(QuadPaneWidget)) == before - 1


def test_delayed_pane_creation_on_dead_host_is_silent(qapp, qtbot):
    """宿主已被删时，延迟建窗格要安静放弃，而不是把异常丢进事件循环。

    这个回调由 250ms 定时器排定，用户在这段时间里关掉标签页/关窗口，宿主
    `QuadPaneWidget` 的 C++ 部分就没了；旧写法直接往下走去 `Pane(parent=self)`，
    抛 `wrapped C/C++ object of type QuadPaneWidget has been deleted`（从 Qt 事件
    循环里报出，在真实使用中更坏时就是 access violation）。
    """
    from core.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    quad = win.tab_widget.widget(0)
    quad._all_panes_created = False            # 假装 pane2-4 还没建（首屏只有 pane1）
    sip.delete(quad)                           # 窗口在这 250ms 内被拆掉

    quad._create_remaining_panes()             # 旧写法：在这一步抛 RuntimeError
    # `sip.delete` 不清 `__dict__`，所以死包装器上的 Python 属性仍可读（实测）
    assert quad._all_panes_created is False, "已销毁的宿主不该被标成建好了"


# ---------------------------------------------------------------- 事件过滤器

def test_a_raising_event_filter_returns_false_instead_of_garbage():
    """过滤器里的异常必须在 Python 侧咽掉

    `bool QObject::eventFilter()` 的返回值由 sip 写入：Python 抛异常时它根本没被
    赋值，Qt 读到的是未初始化的随机值（当成“已过滤”就会跳过焦点/销毁通知的清理）。
    Linux 真机的实测链：拆窗时 `Pane.eventFilter` 碰已删的 `tree_view` 抛
    RuntimeError → 几毫秒后新建窗格的 `pane_tabs.addTab` 段错误。
    """
    from core.lifecycle import safe_event_filter

    @safe_event_filter
    def boom(self, obj, event):
        raise RuntimeError("wrapped C/C++ object of type FileListTreeView has been deleted")

    class Host:
        eventFilter = boom

    assert Host().eventFilter(None, None) is False


def test_safe_event_filter_keeps_the_original_return_values():
    """包上去了不能改变语义：过滤为真还是真，返回 None（没过滤）仍算假"""
    from core.lifecycle import safe_event_filter

    @safe_event_filter
    def yes(self, obj, event):
        return True

    @safe_event_filter
    def no(self, obj, event):
        return None

    class Host:
        pass

    Host.yes = yes
    Host.no = no
    assert Host().yes(None, None) is True
    assert Host().no(None, None) is False


def test_the_filter_warning_is_logged_once_per_kind(caplog):
    """拆一棵子树时每个事件都会踩到这里，不限频就会把日志冲干净"""
    import logging

    from core.lifecycle import safe_event_filter

    @safe_event_filter
    def boom(self, obj, event):
        raise RuntimeError("gone")

    class Host:
        eventFilter = boom

    h = Host()
    with caplog.at_level(logging.WARNING, logger="pan4dex.lifecycle"):
        for _ in range(5):
            assert h.eventFilter(None, None) is False
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 1, f"同一类异常只该报一次，实际 {len(warned)} 次"


def test_every_widget_event_filter_in_the_app_is_wrapped():
    """结构守卫：任何一个 `eventFilter` 都必须套上 `safe_event_filter`

    这一类缺陷不需要每个过滤器各自踩一次才被发现：逃进 C++ 派发栈的异常
    崩溃点不在自己这里（Linux 实测崩在下一个窗格的 `addTab`），报上来的栈完全看不
    到真凶，所以直接钉住“全部已包装”。
    """
    from core.main_window import MainWindow
    from core.pane import Pane
    from widgets.filter_bar import FilterBar

    for cls in (Pane, MainWindow, FilterBar):
        fn = cls.__dict__["eventFilter"]        # 取本类自己定义的那个（不是继承来的）
        assert hasattr(fn, "__wrapped__"), f"{cls.__name__}.eventFilter 没被 safe_event_filter 包住"
