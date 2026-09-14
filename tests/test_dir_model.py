# -*- coding: utf-8 -*-
"""DirStoreModel 单元测试（第二阶段 5.3）

覆盖：枚举正确性、列/角色、隐藏过滤、重命名 setData、TTL 缓存与定向失效、
快速切换目录的后台线程安全。异步枚举用 qtbot 等待目录节点加载完成。

两层结构：目录节点 index(dirPath) 为父，其条目为子项。
"""
import os

import pytest
from PyQt6.QtCore import Qt, QDir, QModelIndex, QThreadPool

from core.dir_model import DirStoreModel, enumerate_dir, _key


@pytest.fixture
def tree(tmp_path):
    """构造：子目录 dir_a/、普通文件 b.txt(内容 5B, 旧 mtime)、隐藏 .hidden"""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_a" / "inner.txt").write_text("x")
    f = tmp_path / "b.txt"
    f.write_text("hello")
    os.utime(str(f), (1_000_000_000, 1_000_000_000))
    (tmp_path / ".hidden").write_text("h")
    return tmp_path


def _loaded(m, path):
    return bool(m._nodes.get(_key(path)) and m._nodes[_key(path)].loaded)


def _load(qtbot, m, path, expected=None):
    m.set_directory(str(path))
    if expected is None:
        qtbot.waitUntil(lambda: _loaded(m, str(path)), timeout=5000)
    else:
        qtbot.waitUntil(lambda: _loaded(m, str(path)) and m.rowCount(m.index(str(path))) == expected,
                        timeout=5000)
    return m.index(str(path))


def _names(m, di):
    return [m.fileName(m.index(r, 0, di)) for r in range(m.rowCount(di))]


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
    assert entries[0].is_dir   # 目录优先


def test_enumerate_dir_hidden_filter(tree):
    shown = enumerate_dir(str(tree), show_hidden=True)
    hidden = enumerate_dir(str(tree), show_hidden=False)
    assert any(e.name == ".hidden" for e in shown)
    assert all(e.name != ".hidden" for e in hidden)


def test_enumerate_missing_dir():
    assert enumerate_dir(os.path.join(os.path.sep, "__no_such_dir_xyz__")) == []


# ---------- 模型加载 / 两层结构 ----------

def test_model_load_and_rows(qtbot, tree):
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    assert m.rowCount(di) == 3
    assert m.columnCount() == 5
    idx0 = m.index(0, 0, di)
    assert m.isDir(idx0) and m.filePath(idx0).endswith("dir_a")
    assert m.data(idx0, Qt.ItemDataRole.DisplayRole) == "dir_a"
    assert m.data(m.index(0, 2, di), Qt.ItemDataRole.DisplayRole) == "文件夹"
    bidx = next(r for r in range(m.rowCount(di)) if m.fileName(m.index(r, 0, di)) == "b.txt")
    assert m.data(m.index(bidx, 1, di), Qt.ItemDataRole.DisplayRole) == "5 B"
    assert m.data(m.index(0, 1, di), Qt.ItemDataRole.DisplayRole) == ""   # 目录大小为空
    assert m.data(m.index(bidx, 2, di), Qt.ItemDataRole.DisplayRole) == "TXT 文件"
    assert "2001" in m.data(m.index(bidx, 3, di), Qt.ItemDataRole.DisplayRole)


def test_root_index_holds_current_dir(qtbot, tree):
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    # invalid 根的唯一行 = 当前顶层目录节点，供排序代理映射
    assert m.rowCount(QModelIndex()) == 1
    top = m.index(0, 0)
    assert top.isValid() and m.isDir(top)
    assert os.path.normpath(m.filePath(top)) == os.path.normpath(str(tree))
    assert top == di


def test_parent_maps_entry_to_dir(qtbot, tree):
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    child = m.index(0, 0, di)
    assert m.parent(child) == di   # 条目的父回指目录节点
    assert m.parent(di).isValid() is False


def test_proxy_map_from_source_valid(qtbot, tree):
    """回归锁：顶层目录索引必须能被 QSortFilterProxyModel.mapFromSource 映射，
    否则 pane 的 _set_root_index 会得到无效代理索引、导航后列表空白。"""
    from PyQt6.QtCore import QSortFilterProxyModel
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(m)
    pi = proxy.mapFromSource(di)
    assert pi.isValid()
    qtbot.waitUntil(lambda: proxy.rowCount(pi) == 3, timeout=5000)
    names = sorted(proxy.data(proxy.index(r, 0, pi)) for r in range(proxy.rowCount(pi)))
    assert names == [".hidden", "b.txt", "dir_a"]


def test_isdir_for_dir_path(qtbot, tree):
    m = DirStoreModel()
    _load(qtbot, m, tree)
    # pane._path_is_dir 依赖：index(dirPath) 有效且 isDir 为真
    idx = m.index(str(tree / "dir_a"))
    assert idx.isValid() and m.isDir(idx)


# ---------- 隐藏过滤 ----------

def test_model_filter_hidden(qtbot, tree):
    m = DirStoreModel()
    m.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
    di = _load(qtbot, m, tree)
    assert ".hidden" not in _names(m, di)
    m.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files |
                QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
    m.refresh()   # 清缓存重载
    di2 = _load(qtbot, m, tree)
    assert ".hidden" in _names(m, di2)


# ---------- 重命名 ----------

def test_rename_via_setdata(qtbot, tree):
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    r = next(r for r in range(m.rowCount(di)) if m.fileName(m.index(r, 0, di)) == "b.txt")
    ok = m.setData(m.index(r, 0, di), "renamed.txt", Qt.ItemDataRole.EditRole)
    assert ok
    assert (tree / "renamed.txt").exists() and not (tree / "b.txt").exists()


def test_rename_reject_collision(qtbot, tree):
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    r = next(r for r in range(m.rowCount(di)) if m.fileName(m.index(r, 0, di)) == "b.txt")
    assert m.setData(m.index(r, 0, di), "dir_a", Qt.ItemDataRole.EditRole) is False
    assert (tree / "b.txt").exists()


# ---------- 定向失效 ----------

def test_invalidate_drops_cache(tree):
    entries = enumerate_dir(str(tree))
    DirStoreModel._cache_put(_key(str(tree)), True, entries)
    assert _key(str(tree)) in DirStoreModel._CACHE
    DirStoreModel.notify_dir_changed(str(tree))
    assert _key(str(tree)) not in DirStoreModel._CACHE


# ---------- 快速切换线程安全 ----------

def test_rapid_switch_only_last(qtbot, tmp_path):
    d1 = tmp_path / "d1"; d2 = tmp_path / "d2"
    d1.mkdir(); d2.mkdir()
    (d1 / "only1.txt").write_text("1")
    for i in range(3):
        (d2 / f"x{i}.txt").write_text("2")
    m = DirStoreModel()
    m.set_directory(str(d1))
    m.set_directory(str(d2))
    QThreadPool.globalInstance().waitForDone(5000)
    di2 = m.index(str(d2))
    qtbot.waitUntil(lambda: m.rowCount(di2) == 3, timeout=5000)
    assert sorted(_names(m, di2)) == ["x0.txt", "x1.txt", "x2.txt"]
    # d1 的过期结果不得混入 d2 视图
    di1 = m.index(str(d1))
    assert "only1.txt" in _names(m, di1)
    assert "only1.txt" not in _names(m, di2)
