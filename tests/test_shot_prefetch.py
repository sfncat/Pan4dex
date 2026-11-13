# -*- coding: utf-8 -*-
"""T9 · 拍摄日期预读改受管线程池：并发封顶、取消生效、代际守卫、销毁不白干。

旧实现是裸 daemon 线程（无池、无取消、无「窗格还在不在」的判据）。实测 20 次快速导航
堆出 17 个同时在飞的线程 —— 换成真 exiftool 就是 17 个并发子进程啃同一批文件，
而且窗格销毁后 21 个任务全部照跑完（tmp/t9.log）。

exiftool 一律用替身：真子进程会让用例慢且依赖环境，而本条要验的是**任务生死与并发上限**，
不是 exiftool 本身（那由 tests/test_media_metadata.py 覆盖）。
"""
import threading
import time
import types

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication

import core.media_metadata as mm
from core.media_metadata import shot_pool

from conftest import qt_exceptions


class FakeExif:
    """顶替 `_run_exiftool`：记录每批文件数、在飞并发峰值，可加延迟造出「在飞」窗口"""

    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay
        self._lock = threading.Lock()
        self._live = 0
        self.peak = 0

    def __call__(self, paths):
        with self._lock:
            self._live += 1
            self.peak = max(self.peak, self._live)
            self.calls.append(len(paths))
        try:
            if self.delay:
                time.sleep(self.delay)
            return []
        finally:
            with self._lock:
                self._live -= 1


@pytest.fixture
def fake_exif(monkeypatch):
    def install(delay=0.0):
        fake = FakeExif(delay)
        monkeypatch.setattr(mm, "_run_exiftool", fake)
        monkeypatch.setattr(mm, "_CACHE", {})   # 缓存是模块级全局，不隔离就测不到批
        return fake
    return install


def _files(d, n, ext=".jpg"):
    d.mkdir()
    for i in range(n):
        (d / f"f{i:04d}{ext}").touch()
    return d


def _pane(qtbot, path, name="t_shot", register=True):
    from core.pane import Pane
    pane = Pane(name, start_path=str(path))
    if register:
        # 要 sip.delete 的用例不能登记：pytest-qt 收尾会对已销毁对象调 close()
        qtbot.addWidget(pane)
    pane.tree_view.setColumnHidden(pane.model.SHOT_DATE_COLUMN, False)
    return pane


def _wait_loaded(pane, path, files, qtbot):
    def _ready():
        QCoreApplication.processEvents()
        return pane.model.loaded_counts(path) == (0, files)
    qtbot.waitUntil(_ready, timeout=20000)


def _wait_pool_idle(qtbot):
    def _idle():
        QCoreApplication.processEvents()
        return shot_pool().waitForDone(50)
    qtbot.waitUntil(_idle, timeout=30000)
    QCoreApplication.processEvents()


# ---------- 取消令牌：两个方向都要断言（gotchas #54 方向写反会全停或永不停） ----------

def test_cancel_false_runs_every_chunk(tmp_path, fake_exif):
    fake = fake_exif()
    paths = [str(p) for p in _files(tmp_path / "d", 1200).iterdir()]
    mm.batch_get_shot_dates(paths, cancel=lambda: False)
    assert fake.calls == [500, 500, 200]


def test_cancel_true_stops_before_next_chunk(tmp_path, fake_exif):
    fake = fake_exif()
    paths = [str(p) for p in _files(tmp_path / "d", 1200).iterdir()]
    mm.batch_get_shot_dates(paths, cancel=lambda: len(fake.calls) >= 1)
    assert fake.calls == [500], "命中取消后还在啃后续批"


def test_cancel_accepts_abandoned_attribute(tmp_path, fake_exif):
    """令牌形状与 `calc_dir_size` 一致：可调用，或带 abandoned 属性"""
    fake = fake_exif()
    paths = [str(p) for p in _files(tmp_path / "d", 1200).iterdir()]
    mm.batch_get_shot_dates(paths, cancel=types.SimpleNamespace(abandoned=True))
    assert fake.calls == []


def test_cancelled_paths_are_not_poisoned_in_cache(tmp_path, fake_exif):
    """被取消的路径不许写 None 缓存，否则它们再也不会被重试"""
    fake = fake_exif()
    d = _files(tmp_path / "d", 1200)
    paths = [str(p) for p in d.iterdir()]
    mm.batch_get_shot_dates(paths, cancel=lambda: len(fake.calls) >= 1)
    assert mm._CACHE == {}

    mm.batch_get_shot_dates(paths)          # 重来一次：三批都要跑到
    assert fake.calls == [500, 500, 500, 200]
    assert set(mm._CACHE) == {mm._norm(p) for p in paths}


# ---------- 窗格接线：并发上限 / 销毁 / 代际 ----------

def test_rapid_navigation_caps_concurrency(qtbot, tmp_path, fake_exif):
    """连续快速导航 20 次：在飞线程不超过池上限，且多数任务被取消而不是全跑"""
    fake = fake_exif(delay=0.05)
    dirs = [_files(tmp_path / f"d{i:02d}", 3) for i in range(20)]
    pane = _pane(qtbot, tmp_path)
    for d in dirs:
        pane.navigate_to(str(d))
        _wait_loaded(pane, str(d), 3, qtbot)
    submitted = pane._shot_gen
    _wait_pool_idle(qtbot)

    assert shot_pool().maxThreadCount() == 2
    assert fake.peak <= 2, f"并发失控：峰值 {fake.peak}"
    assert submitted >= 15, f"前置条件不成立：只发起了 {submitted} 次预读"
    assert len(fake.calls) < submitted, "被取代的任务照样把活全干了"


def test_destroying_pane_stops_remaining_chunks(qtbot, tmp_path, fake_exif):
    """窗格销毁后旧任务不再啃后续批，也不得有异常逃出去 / 投递到死窗格"""
    fake = fake_exif(delay=0.15)
    d = _files(tmp_path / "many", 1200)
    pane = _pane(qtbot, tmp_path, register=False)
    pane.navigate_to(str(d))
    _wait_loaded(pane, str(d), 1200, qtbot)
    qtbot.waitUntil(lambda: bool(fake.calls), timeout=10000)   # 第一批已在飞

    with qt_exceptions() as errors:
        sip.delete(pane)
        _wait_pool_idle(qtbot)
    assert errors == []
    assert len(fake.calls) < 3, f"窗格销毁后还在啃后续批：{fake.calls}"


def test_stale_generation_result_is_discarded(qtbot, tmp_path, fake_exif):
    """旧导航的预读回投必须丢弃：不去刷新新目录的列"""
    fake = fake_exif(delay=0.1)
    a = _files(tmp_path / "a", 2)
    b = _files(tmp_path / "b", 2)
    pane = _pane(qtbot, tmp_path)
    hits = []
    pane.shot_dates_ready.connect(lambda: hits.append(1))

    pane.navigate_to(str(a))
    _wait_loaded(pane, str(a), 2, qtbot)
    qtbot.waitUntil(lambda: bool(fake.calls), timeout=10000)   # A 的任务已在飞
    pane.navigate_to(str(b))
    _wait_loaded(pane, str(b), 2, qtbot)
    _wait_pool_idle(qtbot)

    assert pane._shot_gen == 2
    assert len(hits) == 1, f"旧代际的结果没被丢弃（刷新了 {len(hits)} 次）"


def test_emit_ui_signal_signature_unchanged(qtbot, tmp_path):
    """`_emit_ui("shot_dates_ready")` 无参调用仍不抛（外部接线与既有用例都照旧）"""
    pane = _pane(qtbot, tmp_path)
    hits = []
    pane.shot_dates_ready.connect(lambda: hits.append(1))
    pane._emit_ui("shot_dates_ready")
    assert hits == [1]