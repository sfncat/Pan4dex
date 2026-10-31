# -*- coding: utf-8 -*-
"""列排序记忆：点击表头后重启，排序保持用户所选而不是回到默认。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt


def test_sort_persisted_on_indicator_change(qtbot, tmp_path):
    from core.pane import Pane

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    p = Pane("t_sort_mem", start_path=str(tmp_path))
    qtbot.addWidget(p)

    p.tree_view.sortByColumn(2, Qt.SortOrder.DescendingOrder)
    try:
        assert p._get_settings().value(p._sort_key(), "") == "2,1"
    finally:
        p._get_settings().remove(p._sort_key())


def test_sort_restored_on_new_pane(qtbot, tmp_path):
    from core.pane import Pane

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    p1 = Pane("t_sort_mem2", start_path=str(tmp_path))
    qtbot.addWidget(p1)
    p1.tree_view.sortByColumn(1, Qt.SortOrder.DescendingOrder)

    p2 = Pane("t_sort_mem2", start_path=str(tmp_path))
    qtbot.addWidget(p2)
    header = p2.tree_view.header()
    assert header.sortIndicatorSection() == 1
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder

    p1._get_settings().remove(p1._sort_key())
    p2._get_settings().remove(p2._sort_key())


def test_restore_does_not_rewrite_settings(qtbot, tmp_path):
    """恢复排序本身不能被当成用户操作又存回去"""
    from core.pane import Pane

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    p1 = Pane("t_sort_mem3", start_path=str(tmp_path))
    qtbot.addWidget(p1)
    p1.tree_view.sortByColumn(3, Qt.SortOrder.AscendingOrder)

    p2 = Pane("t_sort_mem3", start_path=str(tmp_path))
    qtbot.addWidget(p2)
    # 恢复走 sortByColumn：若没挡住 sortIndicatorChanged，值会被重写成同一内容——
    # 这里直接验证守卫标志已复位且值不变
    assert p2._restoring_sort is False
    assert p2._get_settings().value(p2._sort_key(), "") == "3,0"

    for p in (p1, p2):
        p._get_settings().remove(p._sort_key())
