"""
Pan4dex 万格 — 快捷键/菜单/侧边栏该作用在哪个窗格

`MainWindow._active_pane` 只在窗格**真的获得过焦点**时才被赋值。旧代码在十几个处理
函数里直接 `if self._active_pane:`，于是「启动后一次都还没点过窗格」这段时间里
Ctrl+L、Delete、F2、F5、目录树与收藏夹点击全部静默失灵 —— 什么也不弹、什么也不报。

Windows 上首屏焦点正好落在 pane1，所以这条一直藏着；Linux/X11 上初始焦点不在窗格里，
真机 GUI 验收第一次浏览目录就撞上了（v1.9.016）。这里把两半都钉住：
① 从未激活过时要有默认落点；② 激活过之后不能退回 pane1（否则焦点跑到预览面板上
按删除，会删错窗格）。
"""
import os
import sys

import pytest
from PyQt6 import sip

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def win(qtbot):
    from core.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    return w


def first_pane(win):
    return win.tab_widget.widget(0).pane1


class TestTargetPaneResolution:
    def test_falls_back_to_default_pane_when_never_activated(self, win):
        assert win._active_pane is None, "前提：新 MainWindow 还没有任何窗格被激活过"
        pane = win.target_pane()
        assert pane is not None, "从未激活过窗格时仍须给出落点，否则快捷键全部静默失灵"
        assert pane is first_pane(win)

    def test_keeps_the_last_activated_pane(self, win):
        """激活过别的窗格后不能退回 pane1：焦点离开窗格时操作仍要归原来那个"""
        page = win.tab_widget.widget(0)
        page._ensure_all_panes()
        win._active_pane = page.pane3
        assert win.target_pane() is page.pane3

    def test_ignores_a_deleted_active_pane(self, win):
        """握着已销毁的窗格时退回默认窗格（旧引用是死包装器，用不得）"""
        orphan = first_pane(win).parent()          # QuadPaneWidget，作为 Pane 的父级参照
        from core.pane import Pane

        throwaway = Pane(pane_id="throwaway", parent=orphan)
        win._active_pane = throwaway
        sip.delete(throwaway)
        assert win.target_pane() is first_pane(win)


class TestHandlersFollowTargetPane:
    """这些处理函数以前各自 `if self._active_pane:`，现在必须走到 target_pane()"""

    def test_ctrl_l_reaches_the_path_bar(self, win):
        pane = first_pane(win)
        hits = []
        pane.path_bar.focus_for_input = lambda: hits.append("focus")
        win.on_focus_path_bar()
        assert hits == ["focus"], "Ctrl+L 在没点过窗格时什么都没做"

    def test_delete_reaches_the_pane(self, win):
        pane = first_pane(win)
        hits = []
        pane.delete_selected = lambda: hits.append("del")
        win.on_delete()
        assert hits == ["del"]

    def test_copy_cut_paste_rename_refresh_select_all(self, win):
        pane = first_pane(win)
        calls = []
        for name in ("copy_selected", "cut_selected", "paste", "rename_selected",
                     "refresh_current", "go_back", "go_forward", "new_folder",
                     "new_file"):
            setattr(pane, name, lambda _n=name: calls.append(_n))
        pane.tree_view.selectAll = lambda: calls.append("selectAll")
        for fn in (win.on_copy, win.on_cut, win.on_paste, win.on_rename,
                   win.on_refresh, win.on_select_all, win.on_nav_back,
                   win.on_nav_forward, win.on_new_folder, win.on_new_file):
            fn()
        assert len(calls) == 10, f"只有 {len(calls)} 个动作落到了窗格上：{calls}"

    def test_tree_and_bookmark_clicks_navigate_the_default_pane(self, win):
        pane = first_pane(win)
        seen = []
        pane.navigate_to = lambda p: seen.append(p)
        win.on_tree_folder_clicked("/tmp/树里点的")
        win.on_bookmark_clicked("/tmp/收藏夹点的")
        assert seen == ["/tmp/树里点的", "/tmp/收藏夹点的"], \
            "启动后先点目录树/收藏夹时，导航没落到任何窗格"

    def test_bookmark_current_dir_follows_the_target_pane(self, win):
        pane = first_pane(win)
        pane.current_path = "/tmp/当前目录"
        assert win._target_pane_path() == "/tmp/当前目录"
        assert win.bookmark_sidebar.current_dir_provider() == "/tmp/当前目录"
