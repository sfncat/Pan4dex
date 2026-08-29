"""
Pan4dex 万格 — 回归测试
确保新增功能不会导致启动失败或基础功能异常
"""
import pytest
import os
import sys
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStartupRegression:
    """启动回归测试 — 确保应用能正常启动不崩溃"""
    
    def test_main_window_startup(self, qtbot):
        """测试主窗口启动不崩溃"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 验证窗口基本状态
        assert window.windowTitle() == "Pan4dex 万格"
        assert window.tab_widget.count() >= 1
    
    def test_quad_pane_widget_creation(self, qtbot):
        """测试四窗格组件创建"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        # 验证四个窗格都存在
        assert hasattr(widget, 'pane1')
        assert hasattr(widget, 'pane2')
        assert hasattr(widget, 'pane3')
        assert hasattr(widget, 'pane4')
    
    def test_all_panes_startup(self, qtbot):
        """测试所有窗格能正常启动"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        # 验证每个窗格的必要属性都存在
        for pane in [widget.pane1, widget.pane2, widget.pane3, widget.pane4]:
            assert hasattr(pane, 'tree_view')
            assert hasattr(pane, 'model')
            assert hasattr(pane, 'path_bar')
            assert hasattr(pane, 'pane_tree_view')
            assert hasattr(pane, 'pane_tabs')
            assert hasattr(pane, '_tab_bar')
            assert hasattr(pane, '_pane_tab_paths')
    
    def test_pane_event_filter_no_crash(self, qtbot):
        """测试窗格事件过滤器不会崩溃"""
        from core.main_window import QuadPaneWidget
        from PyQt6.QtCore import QEvent, QPointF
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import Qt
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        # 模拟各种事件不会崩溃
        for pane in [widget.pane1, widget.pane2, widget.pane3, widget.pane4]:
            # tree_view 事件
            focus_event = QEvent(QEvent.Type.FocusIn)
            pane.eventFilter(pane.tree_view, focus_event)
            
            # 鼠标事件（使用 QMouseEvent）
            mouse_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                     Qt.KeyboardModifier.NoModifier)
            pane.eventFilter(pane.tree_view, mouse_event)
            
            # 鼠标侧键事件
            back_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                                    Qt.MouseButton.BackButton, Qt.MouseButton.BackButton,
                                    Qt.KeyboardModifier.NoModifier)
            pane.eventFilter(pane.tree_view, back_event)
            
            forward_event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                                       Qt.MouseButton.ForwardButton, Qt.MouseButton.ForwardButton,
                                       Qt.KeyboardModifier.NoModifier)
            pane.eventFilter(pane.tree_view, forward_event)


class TestPaneTabsRegression:
    """窗格标签页回归测试"""
    
    def test_toggle_tabs_no_crash(self, qtbot):
        """测试切换标签页不崩溃"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        for pane in [widget.pane1, widget.pane2, widget.pane3, widget.pane4]:
            # 切换标签页不崩溃
            pane.toggle_tabs()
            pane.toggle_tabs()
    
    def test_add_pane_tab(self, qtbot):
        """测试添加标签页"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        pane = widget.pane1
        pane.toggle_tabs()
        
        initial_count = pane.pane_tabs.count()
        pane.add_pane_tab("/tmp")
        
        assert pane.pane_tabs.count() == initial_count + 1
    
    def test_close_pane_tab(self, qtbot):
        """测试关闭标签页"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        pane = widget.pane1
        pane.toggle_tabs()
        
        # 添加两个标签页
        pane.add_pane_tab("/tmp")
        pane.add_pane_tab("/home")
        initial_count = pane.pane_tabs.count()
        
        # 关闭最后一个
        pane.close_pane_tab(pane.pane_tabs.count() - 1)
        assert pane.pane_tabs.count() == initial_count - 1
    
    def test_rename_pane_tab(self, qtbot, monkeypatch):
        """测试重命名标签页"""
        from core.main_window import QuadPaneWidget
        from PyQt6.QtWidgets import QInputDialog
        
        def mock_getText(*args, **kwargs):
            return ("新名称", True)
        
        monkeypatch.setattr(QInputDialog, "getText", mock_getText)
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        pane = widget.pane1
        pane.toggle_tabs()
        
        # 重命名标签页不崩溃
        pane._rename_pane_tab(0)
        assert pane.pane_tabs.count() >= 1
    
    def test_pane_get_state(self, qtbot):
        """测试获取窗格状态"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        pane = widget.pane1
        state = pane.get_state()
        
        assert 'current_path' in state
        assert 'tree_visible' in state
        assert 'tabs_visible' in state
        assert 'tab_paths' in state
        assert 'tab_current' in state
    
    def test_pane_set_state(self, qtbot):
        """测试恢复窗格状态"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        widget.show()
        
        pane = widget.pane1
        original_path = pane.current_path
        
        # 构造一个状态
        state = {
            'current_path': '/tmp',
            'tree_visible': False,
            'tabs_visible': True,
            'tab_paths': ['/tmp', '/home'],
            'tab_current': 0,
        }
        
        pane.set_state(state)
        
        assert pane.current_path == '/tmp'
        assert pane.pane_tabs.isVisible() == True
        assert len(pane._pane_tab_paths) == 2
    
    def test_pane_set_state_empty(self, qtbot):
        """测试恢复空状态不崩溃"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        pane = widget.pane1
        
        # 空状态
        pane.set_state({})
        pane.set_state(None)
        
        # 应该保持原状态不崩溃
        assert pane is not None


class TestLayoutSaveLoadRegression:
    """布局保存/恢复回归测试"""
    
    def test_save_layout_no_crash(self, qtbot, tmpdir):
        """测试保存布局不崩溃"""
        from core.main_window import MainWindow
        import json
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 临时修改配置目录
        import os
        old_home = os.environ.get('HOME')
        os.environ['HOME'] = str(tmpdir)
        
        try:
            window._auto_save_layout()
            layout_file = os.path.join(str(tmpdir), '.config', 'pan4dex', 'layout.json')
            assert os.path.exists(layout_file)
            
            # 验证 JSON 格式正确
            with open(layout_file, 'r') as f:
                layout = json.load(f)
            assert 'panes' in layout
        finally:
            if old_home:
                os.environ['HOME'] = old_home
    
    def test_load_layout_no_crash(self, qtbot, tmpdir):
        """测试加载布局不崩溃"""
        from core.main_window import MainWindow
        import json
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        import os
        old_home = os.environ.get('HOME')
        os.environ['HOME'] = str(tmpdir)
        
        try:
            # 创建一个无效的布局文件
            config_dir = os.path.join(str(tmpdir), '.config', 'pan4dex')
            os.makedirs(config_dir, exist_ok=True)
            layout_file = os.path.join(config_dir, 'layout.json')
            
            # 测试各种异常情况
            with open(layout_file, 'w') as f:
                f.write('invalid json')
            window._auto_load_layout()  # 不应该崩溃
            
            with open(layout_file, 'w') as f:
                json.dump({}, f)
            window._auto_load_layout()  # 不应该崩溃
            
            with open(layout_file, 'w') as f:
                json.dump({'panes': {}}, f)
            window._auto_load_layout()  # 不应该崩溃
        finally:
            if old_home:
                os.environ['HOME'] = old_home


class TestPathBarButtonsRegression:
    """路径栏按钮回归测试"""
    
    def test_tree_button(self, qtbot):
        """测试目录树按钮"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        widget.show()  # 需要显示窗口才能正确检测子控件可见性
        
        pane = widget.pane1
        
        # 切换目录树按钮
        pane.path_bar.tree_btn.click()
        assert pane.pane_tree_view.isVisible() == True
        
        pane.path_bar.tree_btn.click()
        assert pane.pane_tree_view.isVisible() == False
    
    def test_tabs_button(self, qtbot):
        """测试标签页按钮"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        widget.show()  # 需要显示窗口才能正确检测子控件可见性
        
        pane = widget.pane1
        
        # 切换标签页按钮
        pane.path_bar.tabs_btn.click()
        assert pane.pane_tabs.isVisible() == True
        
        pane.path_bar.tabs_btn.click()
        assert pane.pane_tabs.isVisible() == False
    
    def test_button_states_sync(self, qtbot):
        """测试按钮状态与面板状态同步"""
        from core.main_window import QuadPaneWidget
        
        widget = QuadPaneWidget()
        qtbot.addWidget(widget)
        
        pane = widget.pane1
        
        # 初始状态：都隐藏
        assert pane.pane_tree_view.isVisible() == False
        assert pane.pane_tabs.isVisible() == False
        assert pane.path_bar.tree_btn.isChecked() == False
        assert pane.path_bar.tabs_btn.isChecked() == False
        
        # 打开目录树
        pane.set_tree_visible(True)
        assert pane.path_bar.tree_btn.isChecked() == True
        
        # 打开标签栏
        pane.toggle_tabs()
        assert pane.path_bar.tabs_btn.isChecked() == True
