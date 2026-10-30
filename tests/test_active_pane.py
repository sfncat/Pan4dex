# -*- coding: utf-8 -*-
"""UI 审查修复回归（docs/ui-audit.md Critical #1/#2）：

- 活动窗格必须视觉可辨：路径栏下 2px 主色指示条随焦点切换（此前两个窗格
  选中色相同，无法分辨 Delete/Ctrl+C 会作用于哪个窗格）
- Tab（无修饰键）把焦点从文件列表交给同窗口下一个窗格；Ctrl+Tab 仍归
  「切换标签页」，不得被窗格吞掉
"""
import pytest
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from config.theme_manager import ThemeManager


@pytest.fixture
def two_panes(qapp, qtbot):
    """顶层容器挂 pane1/pane2：_focus_sibling_pane 靠 window() 的 paneN 属性找兄弟"""
    from core.pane import Pane

    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    p1 = Pane("pane_1", parent=host)
    p2 = Pane("pane_2", parent=host)
    layout.addWidget(p1)
    layout.addWidget(p2)
    host.pane1 = p1
    host.pane2 = p2
    host.resize(900, 700)
    host.show()
    return host, p1, p2


def test_tab_moves_focus_between_panes_and_wraps(two_panes, qtbot):
    host, p1, p2 = two_panes
    p1.focus_file_list()
    assert host.focusWidget() is p1.tree_view

    qtbot.keyClick(p1.tree_view, Qt.Key.Key_Tab)
    assert host.focusWidget() is p2.tree_view, "Tab 应把焦点交给下一个窗格"

    # 循环：p2 再按 Tab 回到 p1
    qtbot.keyClick(QApplication.focusWidget() or p2.tree_view,
                   Qt.Key.Key_Tab)
    assert host.focusWidget() is p1.tree_view


def test_ctrl_tab_is_not_swallowed(two_panes, qtbot):
    """Ctrl+Tab 归主窗口「切换标签页」：窗格不得拦截，焦点也不得被切走"""
    host, p1, p2 = two_panes
    p1.focus_file_list()
    qtbot.keyClick(p1.tree_view, Qt.Key.Key_Tab,
                   Qt.KeyboardModifier.ControlModifier)
    assert host.focusWidget() is p1.tree_view


def test_tab_works_in_the_thumbnail_view(two_panes, qtbot):
    host, p1, p2 = two_panes
    p1.thumbnail_view.setVisible(True)
    p1.thumbnail_view.setFocus()
    assert host.focusWidget() is p1.thumbnail_view

    qtbot.keyClick(p1.thumbnail_view, Qt.Key.Key_Tab)
    assert host.focusWidget() is p2.tree_view, "超大图标视图里的 Tab 也要切窗格"


def test_active_indicator_follows_the_switch(two_panes):
    host, p1, p2 = two_panes
    accent = ThemeManager.color("accent")

    p1.set_active_visual(True)
    assert p1.is_active_visual()
    assert accent in p1.active_indicator.styleSheet()

    p1.set_active_visual(False)
    assert not p1.is_active_visual()
    assert "transparent" in p1.active_indicator.styleSheet()


def test_active_pane_tints_path_bar_and_grays_inactive_selection(two_panes):
    """活动窗格：路径栏着色；非活动窗格：选中项灰化（ui-audit C1 增强）"""
    host, p1, p2 = two_panes

    p1.set_active_visual(True)
    assert "panePathBar" in p1.path_bar.styleSheet()
    assert ThemeManager.color("accent_soft") in p1.path_bar.styleSheet()
    assert p1.tree_view.styleSheet() == "", "活动窗格选中项应交给主题原色"

    p1.set_active_visual(False)
    assert p1.path_bar.styleSheet() == ""
    assert ThemeManager.color("inactive_selection_bg") in p1.tree_view.styleSheet()
    assert ThemeManager.color("inactive_selection_bg") in p1.thumbnail_view.styleSheet()


def test_main_window_lights_up_only_the_active_pane(qapp, qtbot, tmp_path):
    """主窗口联动：新窗格点亮、旧窗格熄灭（真 MainWindow，pane2-4 强制建齐）"""
    from core.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    win.show()
    page = win.tab_widget.widget(0)
    page._ensure_all_panes()          # pane2-4 默认延迟创建，测试里强制建齐
    p1, p2 = page.pane1, page.pane2

    win.on_pane_activated(p1)
    assert p1.is_active_visual() and not p2.is_active_visual()
    win.on_pane_activated(p2)
    assert p2.is_active_visual() and not p1.is_active_visual()
