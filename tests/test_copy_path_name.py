# -*- coding: utf-8 -*-
"""右键「复制路径 / 复制文件名」：Windows 与 Linux 共用同一套菜单构造。

改前只有「复制文件地址」且目录树右键没有对应入口；这里钉住两项都在、
写进系统剪贴板的是纯文本（多行、basename），且旧文案不再出现。
"""
import re

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QMenu


@pytest.fixture
def pane(qtbot, tmp_path):
    from core.pane import Pane
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    p = Pane("t_copy_names", start_path=str(tmp_path))
    qtbot.addWidget(p)
    return p


def _labels(menu):
    """Qt 的 action.text() 保留 & 助记符，比较前去掉"""
    return [re.sub(r"\(&.\)", "", a.text())
            for a in menu.actions() if not a.isSeparator()]


def _capture_menu(monkeypatch):
    captured = {}
    monkeypatch.setattr(QMenu, "exec",
                        lambda self, *a, **k: captured.setdefault("menu", self) or 0)
    return captured


class _Clip:
    def __init__(self):
        self.text = None

    def setText(self, t):
        self.text = t


def test_file_context_menu_has_both_copy_items(pane, tmp_path, monkeypatch):
    captured = _capture_menu(monkeypatch)
    pane._show_file_context_menu([str(tmp_path / "a.txt"), str(tmp_path / "b.md")])
    labels = _labels(captured["menu"])
    assert "复制路径" in labels
    assert "复制文件名" in labels
    assert "复制文件地址" not in labels      # 旧文案已被替换


def test_copy_names_writes_basename_per_line(pane, tmp_path, monkeypatch):
    clip = _Clip()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clip))
    pane._copy_names_to_clipboard(
        [str(tmp_path / "a.txt"), str(tmp_path / "sub" / "b.md")])
    assert clip.text == "a.txt\nb.md"
    assert "个文件名" in pane.status_label.text()


def test_copy_paths_still_writes_full_paths(pane, tmp_path, monkeypatch):
    clip = _Clip()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clip))
    paths = [str(tmp_path / "a.txt"), str(tmp_path / "b.md")]
    pane._copy_paths_to_clipboard(paths)
    assert clip.text == "\n".join(paths)
    assert "条路径" in pane.status_label.text()


def test_empty_selection_is_noop(pane, monkeypatch):
    clip = _Clip()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clip))
    pane._copy_names_to_clipboard([])
    pane._copy_paths_to_clipboard([])
    assert clip.text is None
