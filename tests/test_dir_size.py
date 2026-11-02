# -*- coding: utf-8 -*-
"""右键「计算目录大小」集成测试（pane → DirStoreModel → 大小列）。

模型层单测见 tests/test_dir_model.py 的「目录占用计算」一节；这里锁 pane 侧
接线：`_calc_dir_sizes` 触发后台统计、状态栏反馈、排序代理下大小列的实际文本。
"""
import os
import sys

import pytest
from PyQt6.QtWidgets import QApplication

from core.dir_model import DirStoreModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def win(qtbot):
    from core.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    QApplication.processEvents()
    return w


@pytest.fixture
def _clean_dir_sizes():
    """目录占用缓存/在算集合是类级共享状态，测试前后清干净，不串其它用例。"""
    DirStoreModel._DIR_SIZES.clear()
    DirStoreModel._SIZE_PENDING.clear()
    yield
    DirStoreModel._DIR_SIZES.clear()
    DirStoreModel._SIZE_PENDING.clear()


def test_pane_calc_dir_size_end_to_end(qtbot, win, tmp_path, _clean_dir_sizes):
    from test_shortcut_focus_scope import first_pane
    pane = first_pane(win)
    (tmp_path / "big").mkdir()
    (tmp_path / "big" / "f.bin").write_bytes(b"x" * 2048)
    (tmp_path / "small").mkdir()
    (tmp_path / "small" / "s.txt").write_text("x")
    pane.on_path_entered(str(tmp_path))
    qtbot.waitUntil(lambda: pane.model.rowCount(pane.model.index(str(tmp_path))) == 2,
                    timeout=5000)

    pane._calc_dir_sizes([str(tmp_path / "big"), str(tmp_path / "small")])
    assert "正在计算 2 个目录" in pane.status_label.text()
    qtbot.waitUntil(lambda: len(DirStoreModel._DIR_SIZES) == 2, timeout=5000)
    # 两个目录并发计算，完成顺序不定：状态栏报的是后完成那个
    qtbot.waitUntil(lambda: "的占用空间" in pane.status_label.text(), timeout=5000)

    # 大小列文本（经排序代理取，与屏幕上看到的一致）
    proxy = pane.sort_proxy
    root = proxy.mapFromSource(pane.model.index(str(tmp_path)))
    texts = {}
    for r in range(proxy.rowCount(root)):
        texts[proxy.data(proxy.index(r, 0, root))] = proxy.data(proxy.index(r, 1, root))
    assert texts == {"big": "2.0 KB", "small": "1 B"}
