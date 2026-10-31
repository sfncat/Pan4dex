# -*- coding: utf-8 -*-
"""目录导航定位：新建目录后视图定位到新目录；向上进入上级时定位到刚离开的目录。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QInputDialog


def test_new_folder_pends_locate(qtbot, tmp_path, monkeypatch):
    from core.pane import Pane

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    p = Pane("t_locate_nf", start_path=str(tmp_path))
    qtbot.addWidget(p)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("新目录", True)))

    p.new_folder()

    assert (tmp_path / "新目录").is_dir()
    assert p._pending_restore == ([], str(tmp_path / "新目录"))


def test_go_up_pends_locate_to_former_dir(qtbot, tmp_path):
    from core.pane import Pane

    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "x.txt").write_text("x", encoding="utf-8")
    p = Pane("t_locate_up", start_path=str(tmp_path))
    qtbot.addWidget(p)
    p.navigate_to(str(sub))
    p._pending_restore = None

    p.path_bar.go_up()

    assert os.path.normpath(p.current_path) == os.path.normpath(str(tmp_path))
    assert p._pending_restore == ([], str(sub))


def test_path_entry_does_not_pend_locate(qtbot, tmp_path):
    """手动输入路径导航不该带定位（只有向上按钮才有“刚离开的目录”）"""
    from core.pane import Pane

    sub = tmp_path / "sub"
    sub.mkdir()
    p = Pane("t_locate_path", start_path=str(tmp_path))
    qtbot.addWidget(p)
    p._pending_restore = None

    p.on_path_entered(str(sub))

    assert p._pending_restore is None
