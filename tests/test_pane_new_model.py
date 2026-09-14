# -*- coding: utf-8 -*-
"""第二阶段 §6：窗格接入 DirStoreModel 双轨开关。

验证 use_new_model 打开时，真实 Pane 用每窗格独立的 DirStoreModel 作为文件
列表模型，能通过排序代理列出目录、异步加载完成后条目可见，并能导航进入子目录。
默认关闭时保持旧的共享 ExifFileSystemModel 路径不变。
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


def test_pane_uses_shared_model_by_default(qtbot, monkeypatch, tree):
    import config.app_config as cfg
    monkeypatch.setattr(cfg, "use_new_model", lambda: False)
    from core.pane import Pane, ExifFileSystemModel
    pane = Pane("t_off", start_path=str(tree))
    qtbot.addWidget(pane)
    assert pane._use_new_model is False
    assert isinstance(pane.model, ExifFileSystemModel)
    pane.deleteLater()


def test_pane_new_model_lists_and_navigates(qtbot, monkeypatch, tree):
    import config.app_config as cfg
    monkeypatch.setattr(cfg, "use_new_model", lambda: True)
    from core.pane import Pane
    from core.dir_model import DirStoreModel

    pane = Pane("t_on", start_path=str(tree))
    qtbot.addWidget(pane)
    assert pane._use_new_model is True
    assert isinstance(pane.model, DirStoreModel)
    # 源模型设为独立实例，不与共享模型混用
    assert pane.model is not getattr(Pane, "_shared_file_model", None)

    _wait_rows(qtbot, pane.tree_view, 3)
    assert _names(pane.tree_view) == ["a.txt", "b.md", "sub"]

    sub = os.path.join(str(tree), "sub")
    pane.navigate_to(sub)
    _wait_rows(qtbot, pane.tree_view, 1)
    assert _names(pane.tree_view) == ["inner.txt"]
    assert os.path.normpath(pane.current_path) == os.path.normpath(sub)
    pane.deleteLater()


def test_pane_new_model_hidden_filter_toggle(qtbot, monkeypatch, tree):
    import config.app_config as cfg
    monkeypatch.setattr(cfg, "use_new_model", lambda: True)
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
