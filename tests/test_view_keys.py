# -*- coding: utf-8 -*-
"""T7 · 文件列表键位：Ctrl+End / Ctrl+Home 要让「光标 + 滚动 + 选中」一起走。

Qt 默认把带 Ctrl 的移动当成「只动光标不动选中」，跳到底之后按 Delete/Ctrl+C
作用的仍是跳之前选中的那批文件。普通 End/Home 与 Shift 组合本来就对，一并钉住防回归。

观测量取三个（只断言光标会漏掉本条真正的缺口）：光标行、选中行集合、目标行是否
真的滚进了视口。超大图标/平铺用**新建实例**量，并断言 flow 没被简单列表带歪（T10）。
"""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListView

from widgets.thumbnail_view import ThumbnailView

MODES = ['list', 'simple_list', 'xlarge', 'tile']
ROWS = 200
START = 5


@pytest.fixture
def many_dir(tmp_path):
    d = tmp_path / "keys"
    d.mkdir()
    for i in range(ROWS):
        (d / f"{i:03d}.txt").write_text("x")
    return d


def _view_for(pane, mode):
    return pane.tree_view if mode == 'list' else pane.thumbnail_view


def _state(view):
    """(光标行, 选中行集合, 目标行是否可见) —— 两种视图同一套取法"""
    sel = sorted({i.row() for i in view.selectionModel().selectedIndexes()})
    return view.currentIndex().row(), sel


def _visible(view, row):
    idx = view.model().index(row, 0, view.rootIndex())
    return view.visualRect(idx).intersects(view.viewport().rect())


@pytest.fixture
def pane_at(qtbot, many_dir):
    def build(mode):
        from core.pane import Pane
        pane = Pane("t_view_keys", start_path=str(many_dir))
        qtbot.addWidget(pane)
        pane.resize(854, 400)
        pane.show()
        qtbot.waitExposed(pane)
        pane.on_view_mode_changed(mode)
        view = _view_for(pane, mode)
        if mode == 'list':
            qtbot.waitUntil(
                lambda: view.model().rowCount(view.rootIndex()) == ROWS, timeout=15000)
        else:
            qtbot.waitUntil(lambda: view.count() == ROWS, timeout=15000)
            if mode != 'simple_list':
                # T10 的 flow 残留会把图标排成横带，键位结果跟着失真
                # （简单列表本来就该是 TopToBottom，不在此列）
                assert view.flow() == QListView.Flow.LeftToRight
        view.setFocus()
        view.setCurrentIndex(view.model().index(START, 0, view.rootIndex()))
        view.scrollTo(view.model().index(START, 0, view.rootIndex()))
        return pane, view
    return build


# (键, 修饰键, 期望光标行, 期望选中行)
CASES = [
    (Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier, ROWS - 1, [ROWS - 1]),
    (Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier, ROWS - 1, [ROWS - 1]),
    (Qt.Key.Key_Home, Qt.KeyboardModifier.NoModifier, 0, [0]),
    (Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier, 0, [0]),
    (Qt.Key.Key_End, Qt.KeyboardModifier.ShiftModifier, ROWS - 1,
     list(range(START, ROWS))),
    # Ctrl+Shift+End 不在本条范围内：助手见到 Shift 就让路，保持 Qt 默认
    # （实测 Qt 只把光标移到末行、不扩展选中）。钉住「没被我们改动」这一事实。
    (Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
     ROWS - 1, [START]),
]
IDS = ['End', 'Ctrl+End', 'Home', 'Ctrl+Home', 'Shift+End', 'Ctrl+Shift+End']


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('key,mods,want_row,want_sel', CASES, ids=IDS)
def test_edge_keys_move_cursor_selection_and_scroll(
        qtbot, pane_at, mode, key, mods, want_row, want_sel):
    pane, view = pane_at(mode)
    assert _state(view) == (START, [START]), "前置条件不成立：起点不是第 5 行"

    qtbot.keyClick(view, key, mods)
    # 合成事件会把修饰键态留在 QApplication 里（真键盘松开时不会），不抹掉会污染
    # 后面的用例：Ctrl 粘住后 setCurrentIndex 被当成 Ctrl+点击 → 取消已选行（gotchas #32）
    if mods & Qt.KeyboardModifier.ControlModifier:
        qtbot.keyClick(view, Qt.Key.Key_Control)
    if mods & Qt.KeyboardModifier.ShiftModifier:
        qtbot.keyClick(view, Qt.Key.Key_Shift)

    row, sel = _state(view)
    assert row == want_row, f"{mode}: 光标没到 {want_row}"
    assert sel == want_sel, f"{mode}: 选中没跟着走"
    assert _visible(view, want_row), f"{mode}: 目标行没滚进视口"


@pytest.mark.parametrize('mode', MODES)
def test_ctrl_end_on_empty_dir_is_noop(qtbot, tmp_path, mode):
    """空目录里按 Ctrl+End 不得抛异常，也不得凭空选中一行"""
    from core.pane import Pane
    empty = tmp_path / "empty"
    empty.mkdir()
    pane = Pane("t_keys_empty", start_path=str(empty))
    qtbot.addWidget(pane)
    pane.resize(854, 400)
    pane.show()
    qtbot.waitExposed(pane)
    pane.on_view_mode_changed(mode)
    view = _view_for(pane, mode)
    qtbot.waitUntil(lambda: pane.model.loaded_counts(str(empty)) == (0, 0), timeout=15000)
    view.setFocus()

    qtbot.keyClick(view, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(view, Qt.Key.Key_Control)
    assert _state(view)[1] == []


def test_thumbnail_view_handles_edge_keys_without_pane(qtbot, many_dir):
    """视图单独使用时也生效（助手不依赖 Pane，两种视图共用同一份）"""
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.resize(854, 400)
    v.show()
    qtbot.waitExposed(v)
    v.load_directory(str(many_dir))
    assert v.count() == ROWS
    v.setCurrentRow(START)

    qtbot.keyClick(v, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(v, Qt.Key.Key_Control)
    assert _state(v) == (ROWS - 1, [ROWS - 1])
    assert _visible(v, ROWS - 1)

    qtbot.keyClick(v, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(v, Qt.Key.Key_Control)
    assert _state(v) == (0, [0])
    assert _visible(v, 0)