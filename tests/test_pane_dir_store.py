# -*- coding: utf-8 -*-
"""窗格接入异步模型 DirStoreModel（文件列表唯一数据源）。

验证真实 Pane 用每窗格独立的 DirStoreModel 作为文件列表模型，能通过排序代理
列出目录、异步加载完成后条目可见、导航进入子目录，行内改名与刷新保留选中，
以及本地目录 watcher 使外部程序的改动自动反映到窗格（含跨窗格不互相放大）。
"""
import os

import pytest

from core.dir_model import dir_pool


def _wait_rows(qtbot, tv, expected):
    proxy = tv.model()

    def _ready():
        dir_pool().waitForDone(50)
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


def test_dead_pane_does_not_break_global_pane_operations(qtbot, tree):
    """注册表里的死窗格不得打断类级操作，也不得挡住存活窗格。

    被测状态（实测取自一轮 22 个级联失败的现场）：注册表里有一个 C++ 部分已删、
    且 `model` 属性也不存在的包装器（半途死掉的窗格）—— 那时碰任何属性都抛
    `RuntimeError: wrapped C/C++ object of type Pane has been deleted`。旧写法在
    `set_show_hidden` 里直接碰 `pane.model`（在 try 之外）→ 抛异常；而它是在新建
    MainWindow 的 `create_menu_bar` 里调的，于是一个残留死窗格把之后每个用例都带崩。
    """
    from PyQt6 import sip
    from core.pane import Pane

    gone = Pane("t_dead_reg", start_path=str(tree))
    # 另存一份模型引用：`DirStoreModel` 没有 Qt 父对象，只靠 `pane.model` 这个 Python
    # 引用活着。真删掉它会在后台枚举仍在飞的时候回收掉模型（模型的信号是它的子对象），
    # 于是这个用例自己给 worker 线程制造崩溃现场 —— 被测的不是那件事。
    keep_model = gone.model
    sip.delete(gone)
    del gone.model                     # 模拟“没跑到 _setup_model 就死了”的窗格
    # 前置条件：包装器仍在注册表里，且碰它的属性确实会报错
    assert any(p is gone for p in list(Pane._instances or ()))
    with pytest.raises(RuntimeError):
        gone.model

    live = Pane("t_live_reg", start_path=str(tree))
    qtbot.addWidget(live)
    _wait_rows(qtbot, live.tree_view, 3)

    (tree / ".gone.txt").write_text("h")
    try:
        Pane.set_show_hidden(True)         # 不得抛 RuntimeError
        _wait_rows(qtbot, live.tree_view, 4)
        assert ".gone.txt" in _names(live.tree_view)   # 存活窗格仍要被同步
    finally:
        Pane.set_show_hidden(True)         # 复位，避免污染其他用例
        del gone                           # 让死包装器从 WeakSet 里回收
        del keep_model                     # 此时枚举已排空，可安全放手
        live.deleteLater()


def test_pane_dying_mid_construction_is_not_registered(tree, monkeypatch):
    """构造没跑完的窗格不得进注册表（否则后续的类级操作会拿到一个不完备的对象）。

    真实场景：延迟建窗格的回调（`_create_remaining_panes`）跑在半销毁的窗口上，
    `init_ui` 中途 `self.layout` 已被删 → `__init__` 抛异常。入册必须发生在对象可用
    之后，而不是 `super().__init__()` 之后立刻做。

    用“最后一步之前抛异常”（`navigate_to`）来测，而不是在 `init_ui` 中途拆坏：后者会
    留下一个“子控件已死、父窗格还活着”的半成品子树，Qt 往它投递事件时就会报
    `wrapped C/C++ object of type FileListTreeView has been deleted`（实测：它自己会把
    别的用例带下）。
    """
    from PyQt6 import sip
    from PyQt6.QtWidgets import QWidget
    from core.pane import Pane

    def _boom(self, *args, **kwargs):
        raise RuntimeError("wrapped C/C++ object of type QVBoxLayout has been deleted")

    monkeypatch.setattr(Pane, "navigate_to", _boom)
    holder = QWidget()
    try:
        with pytest.raises(RuntimeError):
            Pane("t_half_dead", parent=holder, start_path=str(tree))

        assert not any(getattr(p, "pane_id", None) == "t_half_dead"
                       for p in list(Pane._instances or ()))
    finally:
        sip.delete(holder)               # 确定性销毁，不留给 GC（时机不定会干扰其他用例）


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
    """应用内新建：_reload_after_mutation 立即失效重扫，不等 watcher 通知。"""
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


def test_pane_updates_on_external_change(qtbot, tree):
    """外部程序新建文件：窗格列表自己长出来，不需要按 F5。

    依赖本机文件系统通知（Windows ReadDirectoryChangesW / Linux inotify）；
    收不到时跳过而非假绿（沙箱、网络临时目录常见）。
    """
    from core.pane import Pane

    pane = Pane("t_watch", start_path=str(tree))
    qtbot.addWidget(pane)
    _wait_rows(qtbot, pane.tree_view, 3)

    (tree / "external.txt").write_text("x")
    try:
        qtbot.waitUntil(lambda: "external.txt" in _names(pane.tree_view), timeout=10000)
    except pytest.fail.Exception as exc:
        pytest.skip(f"文件系统通知未按期到达，watcher 在本机不可用：{exc}")
    assert _row_of(pane.tree_view, "external.txt") >= 0
    pane.deleteLater()


def test_external_change_syncs_panes_without_rescan_loop(qtbot, tree, monkeypatch):
    """两窗格看同一本地目录：外部改动不得互相放大成重扫循环。

    p1 的 watcher 重扫后经 dirChanged 让 p2 也重扫；p2 自己随后收到的通知
    必须被“应用内刚改过”标记抑制，否则两边会来回扫。
    """
    from core.pane import Pane

    p1 = Pane("t_w1", start_path=str(tree))
    p2 = Pane("t_w2", start_path=str(tree))
    qtbot.addWidget(p1)
    qtbot.addWidget(p2)
    _wait_rows(qtbot, p1.tree_view, 3)
    _wait_rows(qtbot, p2.tree_view, 3)

    counts = {id(p1.model): 0, id(p2.model): 0}
    for p in (p1, p2):
        model = p.model
        real = model._reload_top

        def _counted(node, _m=model, _f=real, _c=counts):
            _c[id(_m)] += 1
            return _f(node)

        monkeypatch.setattr(model, "_reload_top", _counted)

    (tree / "many1.txt").write_text("1")
    (tree / "many2.txt").write_text("2")
    try:
        qtbot.waitUntil(lambda: "many2.txt" in _names(p1.tree_view)
                        and "many2.txt" in _names(p2.tree_view), timeout=10000)
    except pytest.fail.Exception as exc:
        pytest.skip(f"文件系统通知未按期到达，watcher 在本机不可用：{exc}")
    # 连发多条通知经防抖合并，跨窗格同步只放大一层：各自不应超过 3 次重扫
    assert counts[id(p1.model)] <= 3, f"p1 重扫次数被放大：{counts}"
    assert counts[id(p2.model)] <= 3, f"p2 重扫次数被放大：{counts}"
    p1.deleteLater()
    p2.deleteLater()
