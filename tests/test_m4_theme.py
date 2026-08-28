"""
Pan4dex 万格 — M4 主题、收藏夹、筛选测试
"""
import pytest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestThemeManager:
    """测试 ThemeManager 类"""
    
    def setup_method(self):
        """每个测试前创建临时配置目录"""
        self.temp_dir = tempfile.mkdtemp()
        from config.theme_manager import ThemeManager
        
        # 重置单例
        ThemeManager._instance = None
        self.theme_manager = ThemeManager()
        self.theme_manager.custom_themes_dir = self.temp_dir
    
    def teardown_method(self):
        """每个测试后清理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        from config.theme_manager import ThemeManager
        ThemeManager._instance = None
    
    def test_singleton(self):
        """测试单例模式"""
        from config.theme_manager import ThemeManager
        
        tm1 = ThemeManager()
        tm2 = ThemeManager()
        
        assert tm1 is tm2
    
    def test_builtin_themes_loaded(self):
        """测试内置主题已加载"""
        assert "dark" in self.theme_manager.themes
        assert "light" in self.theme_manager.themes
    
    def test_get_theme(self):
        """测试获取主题"""
        theme = self.theme_manager.get_theme("dark")
        
        assert theme is not None
        assert theme["name"] == "dark"
        assert "window_bg" in theme
    
    def test_get_all_themes(self):
        """测试获取所有主题"""
        themes = self.theme_manager.get_all_themes()
        
        assert isinstance(themes, dict)
        assert len(themes) >= 2
    
    def test_apply_theme(self, qapp):
        """测试应用主题"""
        result = self.theme_manager.apply_theme("dark")
        
        assert result is True
        assert self.theme_manager.current_theme == "dark"
    
    def test_apply_nonexistent_theme(self, qapp):
        """测试应用不存在的主题"""
        result = self.theme_manager.apply_theme("nonexistent")
        
        assert result is False
    
    def test_save_custom_theme(self):
        """测试保存自定义主题"""
        custom_theme = {
            "name": "custom",
            "display_name": "自定义主题",
            "window_bg": "#123456"
        }
        
        self.theme_manager.save_custom_theme(custom_theme, "custom.json")
        
        assert "custom" in self.theme_manager.themes
    
    def test_delete_custom_theme(self):
        """测试删除自定义主题"""
        custom_theme = {
            "name": "custom",
            "display_name": "自定义主题",
            "window_bg": "#123456"
        }
        
        self.theme_manager.save_custom_theme(custom_theme, "custom.json")
        self.theme_manager.delete_custom_theme("custom")
        
        assert "custom" not in self.theme_manager.themes
    
    def test_export_import_theme(self, tmp_path):
        """测试导出导入主题"""
        # 导出
        export_file = str(tmp_path / "exported.json")
        self.theme_manager.export_theme("dark", export_file)
        
        assert os.path.exists(export_file)
        
        # 导入
        result = self.theme_manager.import_theme(export_file)
        assert result is True
    
    def test_generate_qss(self):
        """测试生成 QSS"""
        theme = self.theme_manager.get_theme("dark")
        qss = self.theme_manager._generate_qss(theme)
        
        assert "QMainWindow" in qss
        assert "#2D2D2D" in qss


class TestBookmarkSidebar:
    """测试 BookmarkSidebar 类"""
    
    def setup_method(self):
        """每个测试前创建临时配置目录"""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """每个测试后清理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_bookmark_sidebar_creation(self, qtbot):
        """测试收藏夹侧边栏创建"""
        from widgets.bookmark_sidebar import BookmarkSidebar
        
        sidebar = BookmarkSidebar()
        qtbot.addWidget(sidebar)
        
        assert sidebar is not None
        assert sidebar.windowTitle() == "收藏夹"
    
    def test_default_bookmarks(self, qtbot):
        """测试默认收藏"""
        from widgets.bookmark_sidebar import BookmarkSidebar
        
        sidebar = BookmarkSidebar()
        qtbot.addWidget(sidebar)
        
        # 应该有默认收藏
        assert len(sidebar.bookmarks) > 0
    
    def test_add_bookmark(self, qtbot):
        """测试添加收藏"""
        from widgets.bookmark_sidebar import BookmarkSidebar
        
        sidebar = BookmarkSidebar()
        qtbot.addWidget(sidebar)
        
        initial_count = len(sidebar.bookmarks)
        sidebar.bookmarks.append({"name": "测试", "path": "/tmp"})
        sidebar.save_bookmarks()
        
        assert len(sidebar.bookmarks) == initial_count + 1
    
    def test_remove_bookmark(self, qtbot):
        """测试移除收藏"""
        from widgets.bookmark_sidebar import BookmarkSidebar
        
        sidebar = BookmarkSidebar()
        qtbot.addWidget(sidebar)
        
        initial_count = len(sidebar.bookmarks)
        if initial_count > 0:
            sidebar.bookmarks.pop(0)
            sidebar.save_bookmarks()
            assert len(sidebar.bookmarks) == initial_count - 1
    
    def test_import_export_bookmarks(self, qtbot, tmp_path):
        """测试导入导出收藏"""
        from widgets.bookmark_sidebar import BookmarkSidebar
        
        sidebar = BookmarkSidebar()
        qtbot.addWidget(sidebar)
        
        # 导出
        export_file = str(tmp_path / "bookmarks.json")
        sidebar.export_bookmarks(export_file)
        
        assert os.path.exists(export_file)


class TestFilterBar:
    """测试 FilterBar 类"""
    
    def test_filter_bar_creation(self, qtbot):
        """测试筛选栏创建"""
        from widgets.filter_bar import FilterBar
        
        filter_bar = FilterBar()
        qtbot.addWidget(filter_bar)
        
        assert filter_bar is not None
    
    def test_apply_filter(self, qtbot):
        """测试应用筛选"""
        from widgets.filter_bar import FilterBar
        
        filter_bar = FilterBar()
        qtbot.addWidget(filter_bar)
        
        # 连接信号
        received = []
        filter_bar.filter_changed.connect(lambda r: received.append(r))
        
        # 设置筛选条件
        filter_bar.filter_edit.setText("*.txt")
        filter_bar.apply_filter()
        
        assert len(received) > 0
    
    def test_clear_filter(self, qtbot):
        """测试清除筛选"""
        from widgets.filter_bar import FilterBar
        
        filter_bar = FilterBar()
        qtbot.addWidget(filter_bar)
        
        received = []
        filter_bar.filter_changed.connect(lambda r: received.append(r))
        
        filter_bar.filter_edit.setText("*.txt")
        filter_bar.clear_filter()
        
        assert filter_bar.filter_edit.text() == ""
        assert len(received) > 0
        assert received[-1] == ""
    
    def test_filter_proxy_model(self, qtbot):
        """测试筛选代理模型"""
        from widgets.filter_bar import FilterProxyModel
        
        proxy = FilterProxyModel()
        
        # 初始状态接受所有行
        assert proxy._filter_regex == ""
        
        # 设置筛选
        proxy.set_filter(".*\\.txt$")
        assert proxy._filter_regex == ".*\\.txt$"


class TestMainWindowTheme:
    """测试主窗口主题集成"""
    
    def test_main_window_has_theme_manager(self, qtbot):
        """测试主窗口有主题管理器"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'theme_manager')
        assert window.theme_manager is not None
    
    def test_main_window_has_bookmark_sidebar(self, qtbot):
        """测试主窗口有收藏夹侧边栏"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'bookmark_sidebar')
        assert window.bookmark_sidebar is not None
    
    def test_toggle_bookmark_sidebar(self, qtbot):
        """测试切换收藏夹侧边栏"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 使用内部状态变量（offscreen 平台 isVisible 不准）
        initial = getattr(window, '_bookmark_toggle', False)
        window.toggle_bookmark_sidebar()
        after = getattr(window, '_bookmark_toggle', False)
        
        assert after != initial
    
    def test_set_theme(self, qtbot):
        """测试设置主题"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        window.set_theme("light")
        assert window.theme_manager.current_theme == "light"
        
        window.set_theme("dark")
        assert window.theme_manager.current_theme == "dark"
