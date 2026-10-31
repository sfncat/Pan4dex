# -*- coding: utf-8 -*-
"""平铺视图（tile 模式）：ThumbnailView 的平铺开关、瓦片附注与窗格接线"""
import os
import sys

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QListWidget, QListView

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
    for expected in ('tile', 'xlarge', 'list', 'simple_list', 'icon', 'tile'):
        bar.on_view_clicked()
        assert seen[-1] == expected
        assert bar._view_mode == expected


def test_refresh_preserving_selection_reloads_thumbnail_view(qtbot, tmp_dir):
    """F5/刷新按钮必须重扫平铺视图：它自己 scandir 填充，不走模型"""
    from core.pane import Pane
    pane = Pane("t_refresh_tv", start_path=str(tmp_dir))
    qtbot.addWidget(pane)
    pane.show()
    pane.on_view_mode_changed('tile')

    (tmp_dir / "late.txt").write_text("x")
    pane._refresh_preserving_selection()
    assert os.path.join(str(tmp_dir), "late.txt") in pane.thumbnail_view._item_map


def test_drop_done_reloads_thumbnail_view_when_target_is_current_dir(qtbot, tmp_dir):
    """拖入当前目录完成后平铺视图必须立即显示新文件（原来只有重进目录才出现）"""
    from core.pane import Pane
    pane = Pane("t_drop_tv", start_path=str(tmp_dir))
    qtbot.addWidget(pane)
    pane.show()
    pane.on_view_mode_changed('tile')

    (tmp_dir / "dropped.txt").write_text("x")

    class _Result:
        success = True
        error = None

    pane._on_drop_done(_Result(), str(tmp_dir), None)
    assert os.path.join(str(tmp_dir), "dropped.txt") in pane.thumbnail_view._item_map


def test_simple_list_mode_switches_view_mode(qtbot, tile_dir):
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.load_directory(str(tile_dir))

    v.set_simple_list_mode(True)
    assert v._simple_list_mode is True
    assert v.viewMode() == QListWidget.ViewMode.ListMode
    # 资源管理器「列表」式多栏：纵向流 + 自动换列
    assert v.isWrapping() is True
    assert v.flow() == QListView.Flow.TopToBottom
    assert v.iconSize() == QSize(16, 16)
    assert v.gridSize() == QSize()
    # uniformItemSizes 会把所有条目压成第一个条目的宽度，长名全被截断
    assert v.uniformItemSizes() is False
    # 拖入链路不能被换外观破坏（setMovement/setViewMode 关 viewport 拖放的坑）
    assert v.viewport().acceptDrops() is True

    v.set_simple_list_mode(False)
    assert v._simple_list_mode is False
    assert v.viewMode() == QListWidget.ViewMode.IconMode
    assert v.gridSize() == QSize(160, 190)
    assert v.uniformItemSizes() is True
    assert v.viewport().acceptDrops() is True


def test_simple_list_items_sized_by_name(qtbot, tile_dir):
    (tile_dir / "2024-01-02_拍照归档目录").mkdir()
    (tile_dir / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    v = ThumbnailView()
    qtbot.addWidget(v)
    v.set_simple_list_mode(True)
    v.load_directory(str(tile_dir))

    long_name = "2024-01-02_拍照归档目录"
    txt = v._item_map[os.path.join(str(tile_dir), long_name)]
    # 行宽必须按名称实际宽度撑开，不能塌成几个字符宽（否则全成「20…」）
    from PyQt6.QtGui import QFontMetrics
    fm = QFontMetrics(v.font())
    expect = 16 + 6 + fm.horizontalAdvance(long_name) + 16
    assert txt.sizeHint().width() == expect
    # 图片也不进懒加载线程池
    qtbot.wait(300)
    assert not v._lazy_timer.isActive()
    assert os.path.join(str(tile_dir), "pic.png") not in v._loading


def test_pane_view_mode_simple_list_wiring(qtbot, tmp_dir):
    from core.pane import Pane
    pane = Pane("t_simple", start_path=str(tmp_dir))
    qtbot.addWidget(pane)

    # 先进平铺，再切列表：验证两种外观互斥恢复
    pane.on_view_mode_changed('tile')
    pane.on_view_mode_changed('simple_list')
    assert pane.thumbnail_view._simple_list_mode is True
    assert pane.thumbnail_view._tile_mode is False
    assert not pane.thumbnail_view.isHidden()
    assert pane.tree_view.isHidden()
    assert pane.thumbnail_view.viewMode() == QListWidget.ViewMode.ListMode
    assert pane.path_bar._view_mode == 'simple_list'

    # 列表 → 超大图标：ListMode 要退回 IconMode
    pane.on_view_mode_changed('xlarge')
    assert pane.thumbnail_view._simple_list_mode is False
    assert pane.thumbnail_view.viewMode() == QListWidget.ViewMode.IconMode

    # 列表 → 详细信息：树视图回来，缩略图视图隐藏
    pane.on_view_mode_changed('list')
    assert pane.thumbnail_view.isHidden()
    assert not pane.tree_view.isHidden()
