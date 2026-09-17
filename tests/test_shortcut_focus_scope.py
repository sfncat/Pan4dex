"""
Pan4dex 万格 — 快捷键的「作用面」：焦点在文本框里时不许动文件系统

菜单 `QAction` 的 `shortcutContext` 默认是 `WindowShortcut`：只要焦点落在本窗口内，快捷键就
**先于**焦点控件触发，除非控件用 `ShortcutOverride` 把键抢回去。Qt 的编辑控件只抢标准编辑键，
所以真机/本机各量一轮之后，边界长这样（v1.9.017）：

| 键 | 焦点在路径栏输入框时实际发生的事 |
|---|---|
| `Delete` / `Ctrl+A` / `Ctrl+L` | 安全：路径栏自己吃了（改文本 / 全选文本） |
| `F2` / `F5` / `F7` / `F8` / `Ctrl+F` | **被窗口快捷键抢走** → 打字时按 F7 当场建一个文件夹 |

内嵌终端是 `QPlainTextEdit`，所以同一批键在终端里也会打到窗格上 —— 而 vim/htop 真的用功能键。
这里钉住两半：① 那几个入口在文本控件有焦点时不动文件系统；② 焦点在文件列表时照常工作
（防“为了安全把快捷键整个关掉”这种假修）。
"""
import os
import sys

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QLineEdit, QPlainTextEdit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 会被窗口快捷键抢走、且会改动文件系统/界面状态的那批入口
GUARDED = {
    "on_rename": "rename_selected",
    "on_refresh": "refresh_current",
    "on_new_folder": "new_folder",
    "on_new_file": "new_file",
    "on_filter_current_dir": "show_filter_bar",
}


@pytest.fixture
def win(qtbot):
    from core.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    QApplication.processEvents()
    return w


def first_pane(win):
    return win.tab_widget.widget(0).pane1


def spy(pane, names):
    """把窗格上的动作换成记录器（`MainWindow` 每次都按名字取属性，所以替换实例属性就够）"""
    calls = []
    for n in names:
        setattr(pane, n, lambda _n=n: calls.append(_n))
    return calls


class TestFocusIsTextInput:
    def test_line_edit_counts_as_text_input(self, win):
        box = QLineEdit(win)
        box.show()
        box.setFocus()
        QApplication.processEvents()
        assert box.hasFocus()
        assert win._focus_is_text_input()

    def test_terminal_view_counts_as_text_input(self, win):
        term = QPlainTextEdit(win)
        term.show()
        term.setFocus()
        QApplication.processEvents()
        assert win._focus_is_text_input(), "内嵌终端是 QPlainTextEdit，必须算文本输入"

    def test_file_list_does_not(self, win):
        view = first_pane(win).tree_view
        view.setFocus()
        QApplication.processEvents()
        assert not win._focus_is_text_input()

    def test_editable_combo_reports_itself_not_its_line_edit(self, win):
        """路径栏的坑：`focusWidget()` 给的是 combo，不是 `lineEdit()`

        只看 `QLineEdit` 的写法在这里静默失效：前提断言 `line.hasFocus()` 仍是 True，光看过
        程看不出问题。这里把 Qt 这个行为也钉住，它哪天变了能直接报出来，而不是无声地退回 False。
        """
        line = first_pane(win).path_bar.combo_box.lineEdit()
        line.show()
        line.setFocus()
        QApplication.processEvents()
        assert line.hasFocus(), "前提：键盘输入归 lineEdit"
        assert QApplication.focusWidget() is not line, "Qt 行为变了，判定逻辑要重盘"
        assert win._focus_is_text_input()

    def test_readonly_combo_is_not_typing(self, win):
        """不可编辑的下拉框不是在打字，不能让它把快捷键整片废掉"""
        combo = QComboBox(win)
        combo.addItems(["a", "b"])
        combo.show()
        combo.setFocus()
        QApplication.processEvents()
        assert not win._focus_is_text_input()


class TestGuardedEntries:
    @pytest.mark.parametrize("handler,pane_method", sorted(GUARDED.items()))
    def test_skipped_while_typing_in_the_path_bar(self, win, handler, pane_method):
        pane = first_pane(win)
        calls = spy(pane, [pane_method])
        line = pane.path_bar.combo_box.lineEdit()
        line.show()
        line.setFocus()
        QApplication.processEvents()
        assert line.hasFocus(), "前提：焦点在路径栏输入框里"

        getattr(win, handler)()
        assert calls == [], f"{handler} 在打字时把动作打到了文件系统上"

    @pytest.mark.parametrize("handler,pane_method", sorted(GUARDED.items()))
    def test_still_works_from_the_file_list(self, win, handler, pane_method):
        """反向半：不能为了安全把快捷键整个废掉"""
        pane = first_pane(win)
        calls = spy(pane, [pane_method])
        pane.tree_view.setFocus()
        QApplication.processEvents()

        getattr(win, handler)()
        assert calls == [pane_method]


class TestShortcutReallyReachesTheWindow:
    """守卫到底有没有必要？直接盯 `QAction.triggered`：它跟处理函数无关，能证明“键确实被
    窗口快捷键抢走了”（否则这些守卫就是凭空多出来的）"""

    def action_for(self, win, key_text):
        from PyQt6.QtGui import QAction, QKeySequence

        want = QKeySequence(key_text)
        for act in win.findChildren(QAction):
            if want in act.shortcuts():
                return act
        raise AssertionError(f"没找到快捷键 {key_text} 对应的 QAction")

    def test_f7_from_the_path_bar_is_stolen_by_the_window_shortcut(self, win):
        pane = first_pane(win)
        calls = spy(pane, ["new_folder"])
        fired = []
        self.action_for(win, "F7").triggered.connect(lambda checked=False: fired.append(1))
        line = pane.path_bar.combo_box.lineEdit()
        line.show()
        line.setFocus()
        QApplication.processEvents()

        QTest.keyClick(line, Qt.Key.Key_F7)
        for _ in range(6):
            QApplication.processEvents()

        assert fired, "F7 没被窗口快捷键抢走（那守卫就是多余的）—— 若真如此，改这条断言并记下来"
        assert calls == [], "快捷键触发了，但处理函数必须被‘焦点在文本框’这道门挡住"

    def test_f2_from_the_terminal_renames_nothing(self, win):
        pane = first_pane(win)
        calls = spy(pane, ["rename_selected"])
        fired = []
        self.action_for(win, "F2").triggered.connect(lambda checked=False: fired.append(1))
        term = QPlainTextEdit(win)
        term.show()
        term.setFocus()
        QApplication.processEvents()

        QTest.keyClick(term, Qt.Key.Key_F2)
        for _ in range(6):
            QApplication.processEvents()

        assert fired, "同上：F2 在终端里也会被窗口快捷键抢走，所以才需要守卫"
        assert calls == []

    def test_delete_stays_in_the_line_edit(self, win):
        """`Delete` 是标准编辑键：Qt 让 `QLineEdit` 用 ShortcutOverride 抢回去 → 不需要守卫

        这条测的是 Qt 的行为而不是我们的代码，写下来是因为**它会随 Qt 版本变**：哪天
        Qt 不抢了，这里就会红，那时必须给 `on_delete` 补上同一道门。
        """
        pane = first_pane(win)
        calls = spy(pane, ["delete_selected"])
        line = pane.path_bar.combo_box.lineEdit()
        line.show()
        line.setText("C:\\somewhere")
        line.setFocus()
        QApplication.processEvents()

        QTest.keyClick(line, Qt.Key.Key_Delete)
        for _ in range(6):
            QApplication.processEvents()
        assert calls == []


class TestFocusReturnsToFileListAfterNavigating:
    """Ctrl+L 打完路径回车后，焦点该回到文件列表（资源管理器的行为）

    留在路径栏里时，接下来的方向键 / Delete / Ctrl+A 全部打在输入框上 —— 用户必须先点
    一下列表。真机自动化验收连撞三轮才定位到这里。
    """

    def test_navigating_from_the_path_bar_moves_focus_to_the_list(self, win, tmp_path):
        pane = first_pane(win)
        (tmp_path / "a.txt").write_text("x")
        line = pane.path_bar.combo_box.lineEdit()
        line.show()
        line.setFocus()
        QApplication.processEvents()

        pane.on_path_entered(str(tmp_path))
        for _ in range(10):
            QApplication.processEvents()

        assert pane.tree_view.hasFocus(), "导航后焦点仍卡在路径栏：后续按键送不到列表"
        assert os.path.normpath(pane.current_path) == os.path.normpath(str(tmp_path))

    def test_invalid_path_keeps_focus_in_the_path_bar(self, win, tmp_path):
        """填了个不存在的路径：把原路径填回去，焦点留在输入框里方便接着改"""
        pane = first_pane(win)
        before = pane.current_path
        line = pane.path_bar.combo_box.lineEdit()
        line.show()
        line.setFocus()
        QApplication.processEvents()

        pane.on_path_entered(str(tmp_path / "no-such-dir-here"))
        QApplication.processEvents()

        assert os.path.normpath(pane.current_path) == os.path.normpath(before)
        assert line.hasFocus()
