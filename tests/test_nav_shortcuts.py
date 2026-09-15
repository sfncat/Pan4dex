# -*- coding: utf-8 -*-
"""标签页 / 路径栏 / 主题三个快捷键（Ctrl+Tab、Ctrl+Shift+Tab、Ctrl+L、Ctrl+D）。

这几项此前在 `docs/feature-checklist.md` 里被写成「已实现」而实际没做（或反过来：
「Ctrl+D 切主题」写成快捷键、实际只有菜单项）。测试把「清单上写的就是真的」钉住：
既测行为，也测 QAction 上真挂了那个键。
"""
import pytest

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication


@pytest.fixture
def win(qapp, qtbot, tmp_path):
    """一个 MainWindow，`settings` 换成临时 ini。

    必须换：主题切换现在会写 QSettings "theme"（重启后保持），不隔离掉就把
    开发者机器上的真实偏好改掉了。
    """
    from core.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    return window


def _quad(window, index=0):
    return window.tab_widget.widget(index)


def _find_action(window, seq):
    """按快捷键找菜单里的 QAction（拿 `toString()` 比，QKeySequence 不可哈希）"""
    target = seq.toString()
    for top in window.menuBar().actions():
        menu = top.menu()
        if menu is None:
            continue
        for item in menu.actions():
            if item.shortcut().toString() == target:
                return item
    raise AssertionError(f"找不到快捷键 {target}")


# ---------- Ctrl+Tab / Ctrl+Shift+Tab ----------

def test_ctrl_tab_cycles_forward_and_wraps(win, qtbot):
    win.new_tab()
    win.new_tab()
    assert win.tab_widget.count() == 3
    win.tab_widget.setCurrentIndex(0)

    win.on_next_tab()
    assert win.tab_widget.currentIndex() == 1
    win.on_next_tab()
    win.on_next_tab()                       # 到端点回绕，而不是卡住
    assert win.tab_widget.currentIndex() == 0


def test_ctrl_shift_tab_cycles_backward_and_wraps(win, qtbot):
    win.new_tab()
    win.new_tab()
    win.tab_widget.setCurrentIndex(0)

    win.on_prev_tab()                       # 0 - 1 → 最后一个
    assert win.tab_widget.currentIndex() == 2
    win.on_prev_tab()
    win.on_prev_tab()
    assert win.tab_widget.currentIndex() == 0


def test_cycling_with_single_tab_is_noop(win):
    """只有一个标签页时不能异常、也不能把索引算成 -1"""
    assert win.tab_widget.count() == 1
    win.on_next_tab()
    win.on_prev_tab()
    assert win.tab_widget.currentIndex() == 0


def test_ctrl_tab_key_press_reaches_the_action(win, qtbot):
    """真按一次 Ctrl+Tab：不能半路被窗格的键盘处理／焦点导航吃掉

    `Tab` 系快捷键比字母键容易出这个问题（焦点导航本身就抢 Tab），
    所以光测 `on_next_tab()` 不够。
    """
    from PyQt6.QtCore import Qt

    win.show()
    qtbot.wait(60)
    win.new_tab()
    win.new_tab()
    win.tab_widget.setCurrentIndex(0)
    win.activateWindow()                    # 快捷键只对「活动窗口」生效
    QApplication.processEvents()

    tree = _quad(win).pane1.tree_view
    hits = []
    act = _find_action(win, QKeySequence("Ctrl+Tab"))
    act.triggered.connect(lambda: hits.append(1))
    qtbot.keyClick(tree, Qt.Key.Key_Tab, Qt.ControlModifier)
    assert hits == [1], "Ctrl+Tab 没触发到 QAction（被焦点导航/窗格抢走了）"
    assert win.tab_widget.currentIndex() == 1

    # 合成事件会把修饰键态留在 `QApplication.keyboardModifiers()` 里（真键盘松开时
    # 不会），不抹掉会留给后面的测试：Ctrl 粘住后 `setCurrentIndex()` 被
    # `selectionCommand()` 当成 Ctrl+点击→ 把已选行**取消**，导致不相干的
    # `test_pane_dir_store.py::test_refresh_preserves_selection` 隔一个文件挂掉（见 gotchas 第 32 条）
    qtbot.keyClick(tree, Qt.Key.Key_Control)
    assert QApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier


# ---------- Ctrl+L ----------

def test_focus_path_bar_selects_whole_path(win, qtbot):
    """按下后路径全文选中：直接键入即可换目录（不必先手动删旧的）"""
    win.show()
    qtbot.wait(60)                          # 让 0ms 的延迟初始化落地
    pane = _quad(win).pane1
    win._active_pane = pane
    current = pane.path_bar.get_path()
    assert current

    win.on_focus_path_bar()
    QApplication.processEvents()
    line = pane.path_bar.combo_box.lineEdit()
    assert line.hasFocus()
    assert line.selectedText() == current


def test_focus_path_bar_is_silent_when_pane_is_dead(win):
    """`_active_pane` 可能握着已销毁的窗格包装器：访问属性就抛 RuntimeError"""
    class _Dead:
        @property
        def path_bar(self):
            raise RuntimeError("wrapped C/C++ object of type Pane has been deleted")

    win._active_pane = _Dead()
    win.on_focus_path_bar()                 # 不抛即通过


# ---------- Ctrl+D ----------

def test_toggle_theme_flips_both_ways_and_persists(win):
    win.theme_manager.apply_theme("dark")
    win.toggle_theme()
    assert win.theme_manager.current_theme == "light"
    assert win.settings.value("theme") == "light"
    assert win.light_theme_action.isChecked()
    assert not win.dark_theme_action.isChecked()

    win.toggle_theme()
    assert win.theme_manager.current_theme == "dark"
    assert win.settings.value("theme") == "dark"
    assert win.dark_theme_action.isChecked()
    assert not win.light_theme_action.isChecked()


def test_menu_theme_items_follow_programmatic_change(win):
    """菜单项打勾状态只认 `set_theme`（Ctrl+D 与菜单、设置对话框同源）"""
    win.set_theme("light")
    assert win.light_theme_action.isChecked()
    win.set_theme("nonexistent-theme")      # 应用失败时不该改状态
    assert win.light_theme_action.isChecked()


# ---------- 快捷键确实挂在 QAction 上 ----------

def test_expected_shortcuts_are_registered(win):
    """清单 12.3 / 12.4 / 12.5 的键必须真存在（写成 🟢 却按不动最坑）"""
    # 比 `toString()` 而不是比对象：PyQt6 的 QKeySequence 不可哈希，进不了集合
    wanted = {QKeySequence(s).toString()
              for s in ("Ctrl+Tab", "Ctrl+Shift+Tab", "Ctrl+L", "Ctrl+D", "Ctrl+F")}
    found = set()
    for act in win.menuBar().actions():
        menu = act.menu()
        if menu is None:
            continue
        for item in menu.actions():
            seq = item.shortcut()
            if not seq.isEmpty():
                found.add(seq.toString())
    missing = wanted - found
    assert not missing, f"未注册的快捷键：{sorted(missing)}"
