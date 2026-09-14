# Pan4dex 万格 — 测试配置和夹具
import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reap_top_level_widgets(qapp):
    """每个测试结束后立即销毁残留的顶层窗口（含 MainWindow）。

    测试里创建的窗口如果不显式销毁，C++ 对象会一直活到后面的测试，删除时机由
    GC 决定；而 `QApplication.setStyleSheet`（应用主题，MainWindow 的 0ms 延迟
    初始化会调）会遍历 polish 全部存活控件，撞上这种“半回收”窗口会偶发
    access violation（Windows 下 faulthandler 只能打印栈，进程直接死）。
    确定性回收同时会停掉窗口里挂着的定时器/后台线程，避免污染后续测试。
    """
    yield
    from PyQt6 import sip
    for w in list(qapp.topLevelWidgets()):
        try:
            w.hide()
        except RuntimeError:
            continue          # 已被删除
        try:
            sip.delete(w)
        except RuntimeError:
            pass
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
