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

同一类的另一半问题发生在**进程退出时**：后台枚举任务的跨线程投递还没派发完，解释器
就开始收尾。用 `exec_and_drain()` 进入事件循环可保证循环一返回就排空后台线程。

第三类发生在 **C++ 往 Python 回调的路上**（事件过滤器）：那里抛出的异常不但没人接，
sip 连返回值都不会被赋值 —— 见 `safe_event_filter`。Linux 真机取证时它确实撞上了
一个拖了很久的随机崩溃，**但不是它造成的**（兜住异常后崩率 12/12 不变）；包它是因为
“异常不该逃进 C++ 派发栈”本身就成立。
"""
import functools
import logging

from PyQt6.QtCore import QCoreApplication, QThreadPool, QTimer

__all__ = ["call_later", "drain_background_pool", "exec_and_drain",
           "safe_event_filter"]

logger = logging.getLogger("pan4dex.lifecycle")


def safe_event_filter(fn):
    """事件过滤器装饰器：任何异常都不准逃进 C++ 的事件派发栈

    `bool QObject::eventFilter(QObject*, QEvent*)` 的返回值是个 `bool`。Python
    侧抛异常时 sip 无法给它赋值，Qt 就在一个未定义的值上继续派发：当成“事件已
    被吃掉”就会跳过它本来要做的清理（焦点/销毁通知）。现场能观测到的就是
    `RuntimeError: wrapped C/C++ object of type ... has been deleted` 从 Qt 事件
    循环里报出来（Linux 上 pytest-qt 会把它拼到“Exceptions caught in Qt event loop”，
    Windows 上则多表现为随机的 access violation）。

    注意：它不是包了就不崩。本仓那个拖很久的段错误根源另有其人（跨用例泄漏的
    app 级 stylesheet，见 `tests/conftest.py`），包上它只为了不让异常未定义地进 C++。

    拆子树时的“对象一半已死”是常态而不是 bug，所以一律当成“没过滤”放行；
    同一个过滤器只报一次警告（拆窗时每个事件都会走到这里，不限制就会刷屏）。
    """
    warned = set()

    @functools.wraps(fn)
    def wrapper(self, obj, event):
        try:
            return bool(fn(self, obj, event))
        except Exception as exc:                       # RuntimeError（对象已删）是主项
            key = (type(self).__name__, type(exc).__name__)
            if key in warned:
                logger.debug("事件过滤器异常已忽略 %s: %s", key, exc)
            else:
                warned.add(key)
                logger.warning("事件过滤器异常已按“没过滤”处理（否则会把随机值交给 Qt）%s: %s",
                               key, exc)
            return False

    return wrapper


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


def _pools_to_drain():
    """需要收拢的线程池：全局池 + 目录枚举专用池。

    `dir_model` 不再用全局池（并发数按 CPU 核数，对 SMB 和稳定性都是负担，见
    `dir_model.dir_pool`），所以排空要逐个点名，不能只照顾一个。
    延迟 import：`dir_model` 也属于核心层，不在模块级互相依赖。
    """
    pools = [QThreadPool.globalInstance()]
    try:
        from core.dir_model import dir_pool
        pools.append(dir_pool())
    except Exception:         # 核心模块不可用时（单测/早期崩溃）只要有全局池就行
        pass
    return pools


def drain_background_pool(wait_ms: int = 5000, spin: int = 5) -> None:
    """退出前收拢后台线程：丢弃/等待在飞任务，并把挂起的跨线程投递派发完。

    不能留给析构阶段去做：线程池（全局池与目录枚举专用池）要等 `~QCoreApplication`
    （甚至更晚的静态析构）才销毁，那时 CPython 可能已开始 finalize；而未派发的 queued
    投递事件里持有着一批 Python 对象（枚举出的条目、目录节点），Qt 销毁它们时
    会从非主线程触碰已死的解释器状态。Windows 上实测退化为 fast-fail（退出码
    0xC0000409，无可捕异常），用户侧就是“关掉程序时报错”。

    只做三件事，按顺序：先丢弃尚未开始的排队任务（`clear`，已经开始的无法收回），
    再等在飞任务跑完（它们的 emit 会堆出更多投递），最后空转几次事件循环把投递
    派发干净。事件处理本身可能又触发新加载（导航/失效），所以再来一轮。

    只能在退出路径（事件循环已停 / 测试 teardown）调用，不要在运行中调：`waitForDone`
    会阻塞主线程，网络盘上一个枚举可能耗时数秒。
    """
    app = QCoreApplication.instance()
    for p in _pools_to_drain():
        p.clear()
        p.waitForDone(wait_ms)
    if app is None:
        return
    for _ in range(spin):
        app.processEvents()
    for p in _pools_to_drain():
        p.clear()
        p.waitForDone(1000)
    for _ in range(spin):
        app.processEvents()


def exec_and_drain(app) -> int:
    """进入事件循环，并在退出循环时收拢后台线程，返回退出码。

    生产入口唯一允许的「跑事件循环」写法：`app.exec()` 返回后必须排空后台线程，
    否则未派发的跨线程投递会留到解释器收尾阶段被 Qt 释放，进程以 fast-fail 退出
    （见 `drain_background_pool`）。把两件事绑成一个函数，避免以后新增退出路径时
    漏掉排空。
    """
    code = app.exec()
    drain_background_pool()
    return code
