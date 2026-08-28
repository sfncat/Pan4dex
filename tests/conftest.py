# Pan4dex 万格 — 测试配置和夹具
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """创建 QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


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
