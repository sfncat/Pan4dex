# -*- coding: utf-8 -*-
"""窗格接入异步模型 DirStoreModel（文件列表唯一数据源）。

验证真实 Pane 用每窗格独立的 DirStoreModel 作为文件列表模型，能通过排序代理
列出目录、异步加载完成后条目可见、导航进入子目录，以及行内改名与刷新保留选中。
"""
import os

import pytest
from PyQt6.QtCore import QThreadPool


def _wait_rows(qtbot, tv, expected):
    proxy = tv.model()

    def _ready():
        QThreadPool.globalInstance().waitForDone(50)
        return proxy.rowCount(tv.rootIndex()) >= expected

    qtbot.waitUntil(_ready, timeout=5000)


def _names(tv):
    proxy = tv.model()
    root = tv.rootIndex()
    return sorted(proxy.data(proxy.index(r, 0, root))
                  for r in range(proxy.rowCount(root)))


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("i")
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.md").write_text("x")
    return tmp_path


def test_pane_uses_per_pane_dir_store_model(qtbot, tree):
    """每个窗格一个独立 DirStoreModel 实例，不再共享源模型。"""
    from core.pane import Pane
    from core.dir_model import DirStoreModel

    p1 = Pane("t_p1", start_path=str(tree))
    p2 = Pane("t_p2", start_path=str(tree))
    qtbot.addWidget(p1)
    qtbot.addWidget(p2)
    try:
        assert isinstance(p1.model, DirStoreModel)
        assert p1.model is not p2.model
        assert p1.sort_proxy is not p2.sort_proxy
    finally:
        p1.deleteLater()
        p2.deleteLater()


def test_pane_lists_and_navigates(qtbot, tree):
    from core.pane import Pane

    pane = Pane("t_nav", start_path=str(tree))
    qtbot.addWidget(pane)

    _wait_rows(qtbot, pane.tree_view, 3)
    assert _names(pane.tree_view) == ["a.txt", "b.md", "sub"]

    sub = os.path.join(str(tree), "sub")
    pane.navigate_to(sub)
    _wait_rows(qtbot, pane.tree_view, 1)
    assert _names(pane.tree_view) == ["inner.txt"]
    assert os.path.normpath(pane.current_path) == os.path.normpath(sub)
    pane.deleteLater()


def test_pane_hidden_filter_toggle(qtbot, tree):
    from core.pane import Pane

    (tree / ".hidden").write_text("h")
    pane = Pane("t_hidden", start_path=str(tree))
    qtbot.addWidget(pane)
    try:
        Pane.set_show_hidden(True)
        _wait_rows(qtbot, pane.tree_view, 4)
        assert ".hidden" in _names(pane.tree_view)

        Pane.set_show_hidden(False)
        qtbot.waitUntil(lambda: ".hidden" not in _names(pane.tree_view), timeout=5000)
    finally:
        Pane.set_show_hidden(True)  # 复位，避免污染其他用例
        pane.deleteLater()


def _proxy_name_col_index(tv, row):
    return tv.model().index(row, 0, tv.rootIndex())


def _row_of(tv, name):
    proxy = tv.model()
    root = tv.rootIndex()
    for r in range(proxy.rowCount(root)):
        if proxy.data(proxy.index(r, 0, root)) == name:
            return r
    return -1


def test_inline_rename_via_setdata_updates_view(qtbot, tree):
    """F2 行内改名：模型 setData 就地更新，列表不重置、行数不变、旧名消失新名出现。"""
    from core.pane import Pane
    from PyQt6.QtCore import Qt

    pane = Pane("t_rename", start_path=str(tree))
    qtbot.addWidget(pane)
    _wait_rows(qtbot, pane.tree_view, 3)

    tv = pane.tree_view
    r = _row_of(tv, "a.txt")
    assert r >= 0
    pi = _proxy_name_col_index(tv, r)
    si = pane.sort_proxy.mapToSource(pi)
    assert pane.model.setData(si, "renamed.txt", Qt.ItemDataRole.EditRole) is True
    assert (tree / "renamed.txt").exists() and not (tree / "a.txt").exists()
    # 未重置模型：仍为 3 行，新名在视图内可见
    assert tv.model().rowCount(tv.rootIndex()) == 3
    assert _row_of(tv, "renamed.txt") >= 0
    assert _row_of(tv, "a.txt") == -1
    pane.deleteLater()


def test_refresh_preserves_selection(qtbot, tree):
    """刷新当前目录后，之前选中的项按路径恢复选中。"""
    from core.pane import Pane
    from PyQt6.QtCore import QItemSelectionModel

    pane = Pane("t_preserve", start_path=str(tree))
    qtbot.addWidget(pane)
    _wait_rows(qtbot, pane.tree_view, 3)

    tv = pane.tree_view
    r = _row_of(tv, "b.md")
    pi = _proxy_name_col_index(tv, r)
    sm = tv.selectionModel()
    sm.select(pi, QItemSelectionModel.SelectionFlag.ClearAndSelect |
              QItemSelectionModel.SelectionFlag.Rows)
    tv.setCurrentIndex(pi)
    assert os.path.join(str(tree), "b.md") in pane._paths_from_selection()

    pane._refresh_preserving_selection()

    # reload 完成后仍为 3 行，且 b.md 仍被选中
    _wait_rows(qtbot, tv, 3)
    qtbot.waitUntil(
        lambda: os.path.join(str(tree), "b.md") in pane._paths_from_selection(),
        timeout=5000)
    pane.deleteLater()


def test_rename_selected_starts_inline_editor(qtbot, tree, monkeypatch):
    """F2 走 rename_selected：不弹输入框对话框，而是让视图进入就地编辑状态。"""
    from core.pane import Pane
    from PyQt6.QtWidgets import QAbstractItemView, QInputDialog
    from PyQt6.QtCore import QItemSelectionModel

    # 旧路径会弹 QInputDialog；若被调用直接报错，确保走的是行内编辑
    def _boom(*a, **k):
        raise AssertionError("不应弹出改名对话框")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(_boom), raising=False)

    pane = Pane("t_f2", start_path=str(tree))
    qtbot.addWidget(pane)
    _wait_rows(qtbot, pane.tree_view, 3)

    tv = pane.tree_view
    r = _row_of(tv, "a.txt")
    pi = _proxy_name_col_index(tv, r)
    tv.selectionModel().select(
        pi, QItemSelectionModel.SelectionFlag.ClearAndSelect |
        QItemSelectionModel.SelectionFlag.Rows)
    pane.rename_selected()
    assert tv.state() == QAbstractItemView.State.EditingState
    pane.deleteLater()


def test_local_mutation_visible_after_reload(qtbot, tree):
    """应用内新建（模型无 watcher）：_reload_after_mutation 后本地目录也能看到新项。"""
    from core.pane import Pane

    pane = Pane("t_mut", start_path=str(tree))
    qtbot.addWidget(pane)
    _wait_rows(qtbot, pane.tree_view, 3)

    (tree / "late.txt").write_text("x")
    pane._reload_after_mutation(str(tree))
    _wait_rows(qtbot, pane.tree_view, 4)
    assert "late.txt" in _names(pane.tree_view)
    pane.deleteLater()


def test_cross_pane_rename_syncs(qtbot, tree):
    """一个窗格行内改名，另一窗格（同目录）靠 dirChanged 重扫同步，不共条目对象。"""
    from core.pane import Pane
    from PyQt6.QtCore import Qt

    p1 = Pane("t_x1", start_path=str(tree))
    p2 = Pane("t_x2", start_path=str(tree))
    qtbot.addWidget(p1)
    qtbot.addWidget(p2)
    _wait_rows(qtbot, p1.tree_view, 3)
    _wait_rows(qtbot, p2.tree_view, 3)

    pi = _proxy_name_col_index(p1.tree_view, _row_of(p1.tree_view, "a.txt"))
    si = p1.sort_proxy.mapToSource(pi)
    assert p1.model.setData(si, "c.txt", Qt.ItemDataRole.EditRole) is True
    assert _row_of(p1.tree_view, "c.txt") >= 0

    qtbot.waitUntil(lambda: "c.txt" in _names(p2.tree_view), timeout=5000)
    assert "a.txt" not in _names(p2.tree_view)
    # 两个窗格不共用可变条目对象（同步靠重扫，不靠别名）
    p2_nodes = p2.model._nodes[os.path.normcase(os.path.normpath(str(tree)))]
    assert all(e is not si.internalPointer() for e in p2_nodes.entries)
    p1.deleteLater()
    p2.deleteLater()
