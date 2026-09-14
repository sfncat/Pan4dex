# -*- coding: utf-8 -*-
"""DirStoreModel 单元测试（第二阶段 5.3）

覆盖：枚举正确性、列/角色、隐藏过滤、重命名 setData、TTL 缓存与定向失效、
快速切换目录的后台线程安全。异步枚举用 qtbot 等待 directoryLoaded。
"""
import os

import pytest
from PyQt6.QtCore import Qt, QDir, QModelIndex, QThreadPool

from core.dir_model import DirStoreModel, Entry, enumerate_dir


@pytest.fixture
def tree(tmp_path):
    """构造：子目录 dir_a/、普通文件 b.txt(内容 5B, 旧 mtime)、隐藏 .hidden"""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_a" / "inner.txt").write_text("x")
    f = tmp_path / "b.txt"
    f.write_text("hello")
    old = 1_000_000_000
    os.utime(str(f), (old, old))
    (tmp_path / ".hidden").write_text("h")
    return tmp_path


def _load(qtbot, model, path):
    model.set_directory(str(path))
    qtbot.waitUntil(lambda: model._loaded, timeout=5000)
    return model


# ---------- 枚举后端 ----------

def test_enumerate_dir_basic(tree):
    entries = enumerate_dir(str(tree), show_hidden=True)
    names = {e.name for e in entries}
    assert {"dir_a", "b.txt", ".hidden"} <= names
    by = {e.name: e for e in entries}
    assert by["dir_a"].is_dir and by["dir_a"].size == -1
    assert not by["b.txt"].is_dir
    assert by["b.txt"].size == 5
    assert abs(by["b.txt"].mtime - 1_000_000_000) < 2
    assert by[".hidden"].hidden and not by["b.txt"].hidden
    # 目录优先排序
    assert entries[0].is_dir


def test_enumerate_dir_hidden_filter(tree):
    shown = enumerate_dir(str(tree), show_hidden=True)
    hidden = enumerate_dir(str(tree), show_hidden=False)
    assert any(e.name == ".hidden" for e in shown)
    assert all(e.name != ".hidden" for e in hidden)


def test_enumerate_missing_dir():
    assert enumerate_dir(os.path.join(os.path.sep, "__no_such_dir_xyz__")) == []


# ---------- 模型基本加载与角色 ----------

def test_model_load_and_rows(qtbot, tree):
    m = DirStoreModel()
    _load(qtbot, m, tree)
    assert m.rowCount(QModelIndex()) == 3
    assert m.columnCount() == 5
    idx0 = m.index(0, 0)
    assert m.isDir(idx0) and m.filePath(idx0).endswith("dir_a")
    # 名称/类型/日期
    assert m.data(m.index(0, 0), Qt.ItemDataRole.DisplayRole) == "dir_a"
    assert m.data(m.index(0, 2), Qt.ItemDataRole.DisplayRole) == "文件夹"
    # 目录大小列为空，文件有字节
    bidx = next(r for r in range(m.rowCount()) if m.fileName(m.index(r, 0)) == "b.txt")
    assert m.data(m.index(bidx, 1), Qt.ItemDataRole.DisplayRole) == "5 B"
    assert m.data(m.index(0, 1), Qt.ItemDataRole.DisplayRole) == ""  # dir_a 目录大小为空
    assert m.data(m.index(bidx, 2), Qt.ItemDataRole.DisplayRole) == "TXT 文件"
    assert "2001" in m.data(m.index(bidx, 3), Qt.ItemDataRole.DisplayRole)


def test_model_headerData(qtbot, tree):
    m = DirStoreModel()
    hdr = m.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
    assert hdr == "名称"


def test_model_index_parent_flat(qtbot, tree):
    m = DirStoreModel()
    _load(qtbot, m, tree)
    idx = m.index(0, 0)
    assert not m.parent(idx).isValid()   # 扁平：父即根
    assert not m.index(0, 0, idx).isValid()  # 目录不可作为父展开


# ---------- 隐藏过滤经模型 setFilter 生效 ----------

def test_model_filter_hidden(qtbot, tree):
    m = DirStoreModel()
    m.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
    _load(qtbot, m, tree)
    names = {m.fileName(m.index(r, 0)) for r in range(m.rowCount())}
    assert ".hidden" not in names
    m.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files |
                QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
    DirStoreModel._cache_invalidate(str(tree))
    _load(qtbot, m, tree)
    names2 = {m.fileName(m.index(r, 0)) for r in range(m.rowCount())}
    assert ".hidden" in names2


# ---------- 重命名 setData ----------

def test_rename_via_setdata(qtbot, tree):
    m = DirStoreModel()
    _load(qtbot, m, tree)
    r = next(r for r in range(m.rowCount()) if m.fileName(m.index(r, 0)) == "b.txt")
    idx = m.index(r, 0)
    ok = m.setData(idx, "renamed.txt", Qt.ItemDataRole.EditRole)
    assert ok
    assert (tree / "renamed.txt").exists()
    assert not (tree / "b.txt").exists()
    _load(qtbot, m, tree)  # 重载后新名可见
    names = {m.fileName(m.index(i, 0)) for i in range(m.rowCount())}
    assert "renamed.txt" in names and "b.txt" not in names


def test_rename_reject_collision(qtbot, tree):
    m = DirStoreModel()
    _load(qtbot, m, tree)
    r = next(r for r in range(m.rowCount()) if m.fileName(m.index(r, 0)) == "b.txt")
    ok = m.setData(m.index(r, 0), "dir_a", Qt.ItemDataRole.EditRole)  # 与已有目录同名
    assert ok is False
    assert (tree / "b.txt").exists()


# ---------- 定向失效 ----------

def test_invalidate_drops_cache(tree):
    entries = enumerate_dir(str(tree))
    DirStoreModel._cache_put(str(tree), entries)
    assert str(tree) in DirStoreModel._CACHE
    DirStoreModel.notify_dir_changed(str(tree))
    assert str(tree) not in DirStoreModel._CACHE


# ---------- 快速切换目录的线程安全 ----------

def test_rapid_switch_only_last(qtbot, tmp_path):
    d1 = tmp_path / "d1"; d2 = tmp_path / "d2"
    d1.mkdir(); d2.mkdir()
    (d1 / "only1.txt").write_text("1")
    for i in range(3):
        (d2 / f"x{i}.txt").write_text("2")
    m = DirStoreModel()
    # 连续快速切换，只最终目录应落定
    m.set_directory(str(d1))
    m.set_directory(str(d2))
    qtbot.waitUntil(lambda: m._loaded and m.rowCount() == 3, timeout=5000)
    assert m.rootPath() == os.path.normpath(str(d2))
    names = sorted(m.fileName(m.index(r, 0)) for r in range(m.rowCount()))
    assert names == ["x0.txt", "x1.txt", "x2.txt"]
    # 等待后台池排空，避免过期结果在断言后乱入
    QThreadPool.globalInstance().waitForDone(5000)
    # 过期结果不得污染当前目录
    assert all(m.fileName(m.index(r, 0)).startswith("x") for r in range(m.rowCount()))
