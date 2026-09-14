"""
Pan4dex 万格 — Qt 对象生命周期防护

启动阶段习惯用 `QTimer.singleShot(ms, lambda: self.xxx())` 把非首屏工作推到事件
循环之后，但静态 singleShot 建的定时器不以 receiver 为父对象，回调会一直等到触发：
对象（MainWindow / QuadPaneWidget / Pane / 侧边栏）若在触发前被销毁，回调仍会运行
并访问已删除的子对象，抛
`RuntimeError: wrapped C/C++ object of type QTabWidget has been deleted`，
在更糟的时序下表现为 access violation（进程直接死，faulthandler 只能留下栈）。
测试里"建完窗口就丢"、用户快速关标签页/退出程序都会踩到。

统一改用 `call_later()`：定时器以业务对象为父对象，随对象一起销毁，回调自然不再
触发 —— 靠 Qt 的所有权语义解决，不需要在各调用点散着写 `sip.isdeleted` 守卫。
"""
from PyQt6.QtCore import QTimer

__all__ = ["call_later"]


def call_later(receiver, msec: int, fn):
    """延后 msec 毫秒执行 fn；receiver 先被销毁则本次调用作废。

    receiver 必须是 QObject（作为定时器的父对象）。只能在创建 receiver 的 GUI
    线程调用 —— QTimer 不能在其它线程启动；后台线程要回主线程请改用信号
    （见 `Pane._emit_ui` / `TerminalView._emit_ui`）。

    返回定时器对象，供需要取消的调用方持有；大多数调用方可忽略返回值。
    """
    timer = QTimer(receiver)
    timer.setSingleShot(True)
    timer.timeout.connect(fn)
    timer.start(msec)
    return timer
