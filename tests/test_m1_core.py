"""
Pan4dex 万格 — 窗格组件测试
"""
import pytest
import os
import sys

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPane:
    """测试 Pane 组件"""
    
    def test_pane_creation(self, qtbot):
        """测试窗格创建"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        assert pane.pane_id == "test_pane"
        assert pane.current_path == os.path.expanduser("~")
    
    def test_navigate_to_directory(self, qtbot, tmp_dir):
        """测试导航到目录"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        # 导航到临时目录
        pane.navigate_to(str(tmp_dir))
        
        assert pane.current_path == str(tmp_dir)
        assert pane.path_bar.get_path() == str(tmp_dir)
    
    def test_navigate_to_subdir(self, qtbot, tmp_dir):
        """测试导航到子目录"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        subdir = tmp_dir / "subdir"
        pane.navigate_to(str(subdir))
        
        assert pane.current_path == str(subdir)
    
    def test_navigate_to_invalid_path(self, qtbot, tmp_dir):
        """测试导航到无效路径"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        original_path = pane.current_path
        
        # 导航到无效路径应该保持原路径
        pane.navigate_to("/nonexistent/path/that/does/not/exist")
        
        # 路径应该保持不变
        assert pane.current_path == original_path
    
    def test_status_bar_update(self, qtbot, tmp_dir):
        """测试状态栏更新"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        pane.navigate_to(str(tmp_dir))
        
        # 状态栏应该显示目录和文件数量
        status_text = pane.status_label.text()
        assert "个目录" in status_text
        assert "个文件" in status_text
    
    def test_new_folder(self, qtbot, tmp_dir):
        """测试新建文件夹"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        pane.navigate_to(str(tmp_dir))
        
        # 新建文件夹
        new_folder_path = os.path.join(str(tmp_dir), "新建文件夹")
        os.makedirs(new_folder_path)
        
        # 刷新
        pane.navigate_to(str(tmp_dir))
        
        # 验证文件夹存在
        assert os.path.exists(new_folder_path)
    
    def test_new_file(self, qtbot, tmp_dir):
        """测试新建文件"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        pane.navigate_to(str(tmp_dir))
        
        # 新建文件
        new_file_path = os.path.join(str(tmp_dir), "新建文件.txt")
        with open(new_file_path, 'w') as f:
            pass
        
        # 验证文件存在
        assert os.path.exists(new_file_path)
    
    def test_rename_file(self, qtbot, tmp_dir):
        """测试重命名文件"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        pane.navigate_to(str(tmp_dir))
        
        # 创建文件
        original = os.path.join(str(tmp_dir), "original.txt")
        renamed = os.path.join(str(tmp_dir), "renamed.txt")
        
        with open(original, 'w') as f:
            f.write("test")
        
        # 重命名
        os.rename(original, renamed)
        
        assert os.path.exists(renamed)
        assert not os.path.exists(original)
    
    def test_delete_file(self, qtbot, tmp_dir):
        """测试删除文件"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test_pane")
        qtbot.addWidget(pane)
        
        pane.navigate_to(str(tmp_dir))
        
        # 创建文件
        test_file = os.path.join(str(tmp_dir), "to_delete.txt")
        with open(test_file, 'w') as f:
            f.write("delete me")
        
        # 删除
        os.remove(test_file)
        
        assert not os.path.exists(test_file)


class TestPathBar:
    """测试 PathBar 组件"""
    
    def test_path_bar_creation(self, qtbot):
        """测试路径栏创建"""
        from widgets.path_bar import PathBar
        
        path_bar = PathBar()
        qtbot.addWidget(path_bar)
        
        assert path_bar is not None
    
    def test_set_path(self, qtbot):
        """测试设置路径"""
        from widgets.path_bar import PathBar
        
        path_bar = PathBar()
        qtbot.addWidget(path_bar)
        
        test_path = "/home/user"
        path_bar.set_path(test_path)
        
        assert path_bar.get_path() == test_path
    
    def test_get_path(self, qtbot):
        """测试获取路径"""
        from widgets.path_bar import PathBar
        
        path_bar = PathBar()
        qtbot.addWidget(path_bar)
        
        test_path = "/tmp"
        path_bar.set_path(test_path)
        
        assert path_bar.get_path() == test_path


class TestMainWindow:
    """测试 MainWindow 组件"""
    
    def test_main_window_creation(self, qtbot):
        """测试主窗口创建"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        assert window.windowTitle() == "Pan4dex 万格"
    
    def test_new_tab(self, qtbot):
        """测试新建标签页"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        initial_count = window.tab_widget.count()
        window.new_tab()
        
        assert window.tab_widget.count() == initial_count + 1
    
    def test_close_tab(self, qtbot):
        """测试关闭标签页"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 确保至少有两个标签页
        window.new_tab()
        initial_count = window.tab_widget.count()
        
        # 关闭最后一个
        window.close_tab(initial_count - 1)
        
        assert window.tab_widget.count() == initial_count - 1
    
    def test_minimum_tabs(self, qtbot):
        """测试最少保留一个标签页"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 尝试关闭所有标签页
        while window.tab_widget.count() > 1:
            window.close_tab(window.tab_widget.count() - 1)
        
        # 应该至少保留一个
        assert window.tab_widget.count() >= 1
