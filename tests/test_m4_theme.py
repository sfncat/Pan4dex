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
    """测试 ThemeManager 类

    曾经有 5 个用例在测一套不存在的接口（`save_custom_theme` /
    `delete_custom_theme` / `export_theme` / `import_theme` / `_generate_qss`，
    还有「主题字典里有 `window_bg`」）：它们从 M4 早期的设想直译过来，而实现用的是
    qdarkstyle（深色）+ 一份写死的浅色 QSS，主题注册表只有 `name`/`display_name`/`qss`。
    现在按真实契约写，并把“没有持久化接口”这一事实固定在 `test_no_custom_theme_persistence_api` 里
    （`docs/feature-checklist.md` 11.4 同步改为未实现）。
    """

    def setup_method(self):
        """重置单例：不复用上一个用例改过的 `current_theme`"""
        from config.theme_manager import ThemeManager

        ThemeManager._instance = None
        self.theme_manager = ThemeManager()

    def teardown_method(self):
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
        """主题注册表契约：已知名字返回条目，未知返回 None（不抛异常）"""
        theme = self.theme_manager.get_theme("dark")

        assert theme is not None
        assert theme["name"] == "dark"
        assert theme["display_name"]                      # 设置页下拉要显示它
        assert self.theme_manager.get_theme("nope") is None
    
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
    
    def test_no_custom_theme_persistence_api(self):
        """自定义主题的保存/删除/导入导出现在**没有**实现

        实现了就把本用例改成真正的往返测（存一个 JSON → 重新载入 → 出现在
        `themes` 里）。写在这儿的目的是：不允许 `feature-checklist` 11.4 再回到
        “🟢 已预留接口”而代码里其实没有。
        """
        for name in ("save_custom_theme", "delete_custom_theme",
                     "export_theme", "import_theme"):
            assert not hasattr(self.theme_manager, name), f"ThemeManager.{name} 已存在：更新本用例"


class TestBookmarkSidebar:
    """测试 BookmarkSidebar 类（M4 冒烟：建得出、默认几条、能增删、能导出）

    分组树的结构规则与拖拽落地覆盖在 tests/test_bookmarks.py，这里不重贴。值得单独
    钉住的是**所有侧边栏都注入临时目录的 store**：旧版用例直接 BookmarkSidebar()，
    跑一轮就把用户真实配置目录里的 bookmarks.json 改了。
    """
    
    def setup_method(self):
        """每个测试前创建临时配置目录"""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """每个测试后清理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def make_sidebar(self, qtbot):
        from config.bookmarks import BookmarkStore
        from widgets.bookmark_sidebar import BookmarkSidebar

        sidebar = BookmarkSidebar(store=BookmarkStore(config_dir=self.temp_dir))
        qtbot.addWidget(sidebar)
        return sidebar
    
    def test_bookmark_sidebar_creation(self, qtbot):
        """测试收藏夹侧边栏创建"""
        sidebar = self.make_sidebar(qtbot)
        
        assert sidebar is not None
        assert sidebar.windowTitle() == "收藏夹"
        assert sidebar.store.config_file == os.path.join(self.temp_dir, "bookmarks.json")
    
    def test_default_bookmarks(self, qtbot):
        """首次启动的四条默认收藏（旧的 sidebar.bookmarks 平铺 list 已被 store 取代）"""
        sidebar = self.make_sidebar(qtbot)
        
        assert [lk["name"] for lk in sidebar.store.links()] == [
            "主目录", "桌面", "下载", "文档"]
    
    def test_add_bookmark(self, qtbot, tmp_path, monkeypatch):
        """测试添加收藏：走侧边栏入口，不是直接改 store"""
        from PyQt6.QtWidgets import QInputDialog
        
        sidebar = self.make_sidebar(qtbot)
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("测试", True)))
        before = sidebar.store.count()
        
        sidebar.add_bookmark_with_path(str(tmp_path))
        
        assert sidebar.store.count() == before + 1
        assert sidebar.get_bookmarks()[-1]["name"] == "测试"
    
    def test_remove_bookmark(self, qtbot, tmp_path, monkeypatch):
        """测试移除收藏（只删收藏夹里这一项）"""
        from PyQt6.QtWidgets import QMessageBox
        
        sidebar = self.make_sidebar(qtbot)
        node_id = sidebar.store.add_link("要删的", str(tmp_path))
        sidebar.store.save()
        sidebar.refresh_tree(select_id=node_id)
        monkeypatch.setattr(QMessageBox, "question", staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes))
        before = sidebar.store.count()
        
        sidebar.remove_selected()
        
        assert sidebar.store.count() == before - 1
        assert not any(b["name"] == "要删的" for b in sidebar.get_bookmarks())
    
    def test_writes_stay_inside_the_injected_config_dir(self, qtbot, tmp_path, monkeypatch):
        """注入 store 后，改收藏夹不得碰真实用户配置"""
        from config import bookmarks as bm
        from PyQt6.QtWidgets import QInputDialog
        
        real_file = os.path.join(bm.default_config_dir(), "bookmarks.json")
        existed_before = os.path.exists(real_file)
        sidebar = self.make_sidebar(qtbot)
        monkeypatch.setattr(QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("只进临时目录", True)))
        
        sidebar.add_bookmark_with_path(str(tmp_path))
        
        assert os.path.exists(os.path.join(self.temp_dir, "bookmarks.json"))
        assert os.path.exists(real_file) == existed_before
    
    def test_import_export_bookmarks(self, qtbot, tmp_path):
        """测试导入导出收藏"""
        sidebar = self.make_sidebar(qtbot)
        
        # 导出
        export_file = str(tmp_path / "export.json")
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
    
    def test_filtering_lives_in_pane_sort_proxy(self):
        """筛选不再有第二层代理（旧 `FilterProxyModel` 已删）

        它依赖 `sourceModel().fileName(index)`（QFileSystemModel 接口），而且与窗格
        自带的排序代理叠成两层映射。筛选现在是
        `core.pane.PaneSortProxyModel.set_entry_filter` 的职责，行为覆盖在
        `tests/test_filter_bar.py`。
        """
        from widgets import filter_bar as fb
        from core.pane import PaneSortProxyModel

        assert not hasattr(fb, "FilterProxyModel")
        assert hasattr(fb, "compile_filter")
        assert hasattr(PaneSortProxyModel, "set_entry_filter")


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
