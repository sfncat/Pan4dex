# -*- coding: utf-8 -*-
"""T6① · 名称列排序改用 Entry.name + 一万条目落地完整性 + 落地期间的忙碌提示。

排序那一段停摆的一半花在「每次比较都回模型取一趟 DisplayRole」上（一万条目约 5 万次
比较，见 docs/improvement-plan-t6-t9.md §2.2）。换成手上已有的 Entry.name 后语义必须
一字不差，所以这里钉的是**等价性**与**落地完整性**，不是耗时（耗时的 A/B 在探针里量，
放用例里会随机器快慢假红假绿）。

忙碌提示是新判据的另一半（用户 2026-11-11 拍板：单次最大停摆 < 400ms + 落地期间有提示）：
提示本来就由 `Pane.update_status_bar()` 的「正在读取…」提供，这里验它真的在落地前出现、
落地后刷成计数，以及缓存命中那条路径不走这一支。
"""
import pytest
from PyQt6.QtCore import QCoreApplication, Qt

from core.dir_model import DirStoreModel, dir_pool
from core.pane import PaneSortProxyModel


def _load(path, qtbot, expect):
    """搭起 DirStoreModel + PaneSortProxyModel 并等顶层枚举落地（必须转事件循环：
    枚举结果是后台线程投递来的 queued 信号，光 waitForDone 只保证活干完了）"""
    src = DirStoreModel()
    proxy = PaneSortProxyModel()
    proxy.setSourceModel(src)
    src_root = src.set_directory(str(path))

    def _loaded():
        dir_pool().waitForDone(50)
        QCoreApplication.processEvents()
        return src.rowCount(src_root) >= expect

    qtbot.waitUntil(_loaded, timeout=30000)
    return src, proxy, src_root, proxy.mapFromSource(src_root)


def _names(proxy, root):
    return [proxy.data(proxy.index(r, 0, root)) for r in range(proxy.rowCount(root))]


@pytest.fixture
def mixed_dir(tmp_path):
    """大小写混排 + 目录与文件混排（名字在大小写不敏感的盘上也不许撞）"""
    (tmp_path / "Zebra").mkdir()
    (tmp_path / "apple").mkdir()
    for n in ("Beta.txt", "alpha.TXT", "gamma.md", "Delta.log", "epsilon"):
        (tmp_path / n).write_text("x")
    return tmp_path


def test_name_sort_equivalent_to_display_role_order(mixed_dir, qtbot):
    """换数据源不改语义：DisplayRole 与 Entry.name 同源，两个方向都逐行一致"""
    src, proxy, src_root, proxy_root = _load(mixed_dir, qtbot, expect=7)
    entries = src._top_node.entries
    for r, e in enumerate(entries):
        assert src.data(src.index(r, 0, src_root)) == e.name

    for order, reverse in ((Qt.SortOrder.AscendingOrder, False),
                           (Qt.SortOrder.DescendingOrder, True)):
        proxy.sort(0, order)
        dirs = sorted([e.name for e in entries if e.is_dir], key=str.lower, reverse=reverse)
        files = sorted([e.name for e in entries if not e.is_dir], key=str.lower, reverse=reverse)
        # 目录在前不能被降序反转（gotchas：降序只反转同类内部）
        assert _names(proxy, proxy_root) == dirs + files


@pytest.fixture
def big_dir(tmp_path):
    d = tmp_path / "big10k"
    d.mkdir()
    for i in range(200):
        (d / f"dir_{i:04d}").mkdir()
    for i in range(9800):
        (d / f"file_{i:05d}.txt").touch()
    return d


def test_ten_thousand_rows_land_complete_and_sorted(big_dir, qtbot):
    """一万条目一趟落地：行数不多不少、无重复、目录在前、同类内单调"""
    src, proxy, src_root, proxy_root = _load(big_dir, qtbot, expect=10000)
    assert src.rowCount(src_root) == 10000
    proxy.sort(0, Qt.SortOrder.AscendingOrder)
    assert proxy.rowCount(proxy_root) == 10000

    names = _names(proxy, proxy_root)
    assert len(names) == 10000
    assert len(set(names)) == 10000, "落地有重复行"
    assert all(n.startswith("dir_") for n in names[:200])
    assert all(n.startswith("file_") for n in names[200:])
    assert names[:200] == sorted(names[:200], key=str.lower)
    assert names[200:] == sorted(names[200:], key=str.lower)


def _pane(qtbot, path, name):
    from core.pane import Pane
    pane = Pane(name, start_path=str(path))
    qtbot.addWidget(pane)
    return pane


def _wait_counts(pane, path, want, qtbot):
    def _ready():
        dir_pool().waitForDone(50)
        QCoreApplication.processEvents()
        return pane.model.loaded_counts(path) == want
    qtbot.waitUntil(_ready, timeout=30000)


def test_status_shows_reading_until_rows_land(qtbot, tmp_path, big_dir):
    """落地前状态栏是「正在读取…」，落地后刷成计数（新判据的「有忙碌提示」那一半）"""
    pane = _pane(qtbot, tmp_path, "t_busy")
    _wait_counts(pane, str(tmp_path), (1, 0), qtbot)

    pane.navigate_to(str(big_dir))
    # 同步断言：导航里就写了状态栏，此刻后台枚举还在飞，行还没落地
    assert pane.model.loaded_counts(str(big_dir)) is None
    assert pane._status_summary == "正在读取…"
    assert "正在读取…" in pane.status_label.text()

    _wait_counts(pane, str(big_dir), (200, 9800), qtbot)
    assert pane._status_summary == "200 个目录, 9800 个文件"


def test_cache_hit_shows_counts_without_reading(qtbot, tmp_path, monkeypatch):
    """缓存命中的目录本就是已加载态：立即给计数，不该闪一下「正在读取…」"""
    # TTL 只有 2s，拉长它才能把「缓存命中」这条路径与机器快慢解耦
    monkeypatch.setattr(DirStoreModel, "_CACHE_TTL", 60.0)
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d, n in ((a, "one.txt"), (b, "two.txt")):
        d.mkdir()
        (d / n).touch()

    pane = _pane(qtbot, a, "t_cache")
    _wait_counts(pane, str(a), (0, 1), qtbot)
    pane.navigate_to(str(b))
    _wait_counts(pane, str(b), (0, 1), qtbot)

    pane.navigate_to(str(a))
    assert pane.model.loaded_counts(str(a)) == (0, 1)
    assert pane._status_summary == "0 个目录, 1 个文件"