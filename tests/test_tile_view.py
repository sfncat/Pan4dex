# -*- coding: utf-8 -*-
"""平铺视图（tile 模式）：ThumbnailView 的平铺开关、瓦片附注与窗格接线"""
import os
import sys

import pytest
from PyQt6.QtCore import QSize, Qt

from widgets.thumbnail_view import TILE_SIZE, TileItemDelegate, ThumbnailView


@pytest.fixture
def tile_dir(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("hello world")  # 11 B
    return tmp_path


def test_tile_mode_switches_delegate_and_grid(qtbot, tile_dir):
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.load_directory(str(tile_dir))
    default_delegate = v.itemDelegate()

    v.set_tile_mode(True)
    assert v._tile_mode is True
    assert v.itemDelegate() is v._tile_delegate
    assert v.gridSize() == TILE_SIZE
    assert v.iconSize() == QSize(48, 48)

    v.set_tile_mode(False)
    assert v._tile_mode is False
    assert v.itemDelegate() is default_delegate
    assert v.gridSize() == QSize(160, 190)


def test_tile_items_carry_size_and_type_annotation(qtbot, tile_dir):
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.set_tile_mode(True)
    v.load_directory(str(tile_dir))

    txt = v._item_map[os.path.join(str(tile_dir), "a.txt")]
    assert txt.sizeHint() == TILE_SIZE
    assert txt.data(Qt.ItemDataRole.UserRole + 2) == "11 B"
    assert txt.data(Qt.ItemDataRole.UserRole + 3) == "TXT 文件"

    sub = v._item_map[os.path.join(str(tile_dir), "sub")]
    # 文件夹不放附注（名称垂直居中显示）
    assert sub.data(Qt.ItemDataRole.UserRole + 2) in (None, "")
    assert sub.data(Qt.ItemDataRole.UserRole + 3) in (None, "")


def test_non_tile_mode_writes_no_annotation(qtbot, tile_dir):
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.load_directory(str(tile_dir))
    txt = v._item_map[os.path.join(str(tile_dir), "a.txt")]
    assert txt.data(Qt.ItemDataRole.UserRole + 2) is None
    assert txt.data(Qt.ItemDataRole.UserRole + 3) is None


def test_version_info_updates_annotation(qtbot, tile_dir):
    """VersionInfoLoader 异步补的 (版本, 说明) 应覆盖大小/类型兜底附注"""
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.set_tile_mode(True)
    v.load_directory(str(tile_dir))
    path = os.path.join(str(tile_dir), "a.txt")
    v._apply_version_info(path, ("1.2.3.4", "Test Library"))
    txt = v._item_map[path]
    assert txt.data(Qt.ItemDataRole.UserRole + 2) == "1.2.3.4"
    assert txt.data(Qt.ItemDataRole.UserRole + 3) == "Test Library"


def test_pe_starts_lazy_timer_plain_dir_does_not(qtbot, tile_dir):
    (tile_dir / "x.dll").write_bytes(b"MZ")
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.set_tile_mode(True)
    v.show()
    v.load_directory(str(tile_dir))
    # call_later 100ms 后才 start，不能同步断言
    qtbot.waitUntil(lambda: v._lazy_timer.isActive(), timeout=2000)

    plain = tile_dir / "plain"
    plain.mkdir()
    v2 = ThumbnailView()
    qtbot.addWidget(v2)
    v2.set_tile_mode(True)
    v2.show()
    v2.load_directory(str(plain))
    qtbot.wait(300)  # 给 call_later 的 100ms 一个机会，确认没被调度
    assert not v2._lazy_timer.isActive()


def test_pane_view_mode_tile_wiring(qtbot, tmp_dir):
    from core.pane import Pane
    pane = Pane("t_tile", start_path=str(tmp_dir))
    qtbot.addWidget(pane)

    pane.on_view_mode_changed('tile')
    assert pane.thumbnail_view._tile_mode is True
    assert not pane.thumbnail_view.isHidden()
    assert pane.tree_view.isHidden()
    assert isinstance(pane.thumbnail_view.itemDelegate(), TileItemDelegate)
    assert pane.path_bar._view_mode == 'tile'

    pane.on_view_mode_changed('xlarge')
    assert pane.thumbnail_view._tile_mode is False
    assert pane.path_bar._view_mode == 'xlarge'

    pane.on_view_mode_changed('list')
    assert pane.thumbnail_view.isHidden()


def test_path_bar_mode_cycle(qtbot):
    from widgets.path_bar import PathBar
    bar = PathBar()
    qtbot.addWidget(bar)
    seen = []
    bar.view_mode_requested.connect(seen.append)
    for expected in ('tile', 'xlarge', 'list', 'icon', 'tile'):
        bar.on_view_clicked()
        assert seen[-1] == expected
        assert bar._view_mode == expected
