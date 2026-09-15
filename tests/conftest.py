# Pan4dex 万格 — 测试配置和夹具
import sys
from contextlib import contextmanager

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication


@contextmanager
def qt_exceptions():
    """收集 PyQt6 在 Qt 事件循环 / 工作线程里捕获的未处理 Python 异常。

    槽函数里抛出的异常不会传回调用方，而是交给 `sys.excepthook`；不接管它就只是
    打印到 stderr，测试里抓不到。定义在这里供各测试文件共用。
    """
    saved = sys.excepthook
    errors = []
    sys.excepthook = lambda etype, value, tb: errors.append(value)
    try:
        yield errors
    finally:
        sys.excepthook = saved


@pytest.fixture(scope="session")
def qapp():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reap_top_level_widgets(qapp):
    """每个测试结束后立即销毁残留的顶层窗口（含 MainWindow），并收拢后台线程。

    测试里创建的窗口如果不显式销毁，C++ 对象会一直活到后面的测试，删除时机由
    GC 决定；而 `QApplication.setStyleSheet`（应用主题，MainWindow 的 0ms 延迟
    初始化会调）会遍历 polish 全部存活控件，撞上这种“半回收”窗口会偶发
    access violation（Windows 下 faulthandler 只能打印栈，进程直接死）。

    `drain_background_pool()` 是同一类问题的另一半：窗格销毁时后台枚举可能仍在飞，
    未派发的投递带着 Python 对象残留到下个测试（甚至残留到进程退出），实测会偶发
    fast-fail / AV；在每个测试边界上把它们排空，就不留竞态窗口。
    """
    yield
    import gc
    from PyQt6 import sip
    from core.lifecycle import drain_background_pool
    for w in list(qapp.topLevelWidgets()):
        try:
            w.hide()
        except RuntimeError:
            continue          # 已被删除
        try:
            sip.delete(w)
        except RuntimeError:
            pass
    drain_background_pool()
    QCoreApplication.processEvents()
    # 把“由循环 GC 决定时机的 Qt 对象销毁”集中到这个安全点：业务对象之间有
    # 信号→绑定方法的引用环，包装器只能等分代 GC 回收；而 GC 会在**任意** Python
    # 分配点执行，那时若另一个窗口正在构造，sip 的 delete 会级联拆掉它正在用的子树
    # （Windows 下 ~QWidget 还要 DestroyWindow → 重入消息派发）。实测（一轮
    # `test_lifecycle + test_m1_core`）：不禁用/不前置 GC 时随机报 `QVBoxLayout has
    # been deleted` 与 access violation，`gc.disable()` 下 22/22 通过。
    gc.collect()
    QCoreApplication.processEvents()


@pytest.fixture
def tmp_dir(tmp_path):
    """创建临时目录结构"""
    # 创建测试目录结构
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    
    # 创建文件
    (test_dir / "file1.txt").write_text("Hello World")
    (test_dir / "file2.py").write_text("print('hello')")
    
    # 创建子目录
    subdir = test_dir / "subdir"
    subdir.mkdir()
    (subdir / "file3.md").write_text("# Title")
    
    return test_dir
