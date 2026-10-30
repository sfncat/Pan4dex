"""Pan4dex 万格 — 列宽记忆回归测试

列宽按窗格独立持久化（QSettings），重启后无需再拉一遍。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dir_model import dir_pool


def _wait_rows(qtbot, tv, expected):
    proxy = tv.model()

    def _ready():
        dir_pool().waitForDone(50)
        return proxy.rowCount(tv.rootIndex()) >= expected

    qtbot.waitUntil(_ready, timeout=10000)


def test_column_widths_persist_per_pane(qtbot, tmp_path):
    """同一窗格 id：拖宽大小列后，新窗格恢复同样的列宽"""
    from core.pane import Pane

    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")

    p1 = Pane("t_col_widths", start_path=str(tmp_path))
    qtbot.addWidget(p1)
    _wait_rows(qtbot, p1.tree_view, 3)

    p1.tree_view.setColumnWidth(1, 260)
    qtbot.waitUntil(lambda: bool(
        p1._get_settings().value(p1._column_widths_key(), "")), timeout=5000)

    p2 = Pane("t_col_widths", start_path=str(tmp_path))
    qtbot.addWidget(p2)
    _wait_rows(qtbot, p2.tree_view, 3)
    # 恢复在 singleShot(0) 里异步执行，等它落到 header 上
    qtbot.waitUntil(
        lambda: p2._column_widths_loaded
        and p2.tree_view.header().sectionSize(1) == 260, timeout=5000)
    assert p2.tree_view.header().sectionSize(1) == 260

    p1._get_settings().remove(p1._column_widths_key())
