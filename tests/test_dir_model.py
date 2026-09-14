# -*- coding: utf-8 -*-
"""DirStoreModel 单元测试（第二阶段 5.3）

覆盖：枚举正确性、列/角色、隐藏过滤、重命名 setData、TTL 缓存与定向失效、
快速切换目录的后台线程安全、模型销毁与在飞枚举投递的生命周期。异步枚举用
qtbot 等待目录节点加载完成。

两层结构：目录节点 index(dirPath) 为父，其条目为子项。
"""
import os
import threading

import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt, QDir, QModelIndex, QThreadPool

from conftest import qt_exceptions
from core import dir_model as dm
from core.dir_model import DirStoreModel, Entry, enumerate_dir, _key
from core.lifecycle import drain_background_pool


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

def test_stale_generation_result_ignored(qtbot, tree):
    """gen 落后的枚举结果必须作废：否则旧快照会永久占据视图，刷新看似没生效。"""
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    node = m._top_node
    assert m.rowCount(di) == 3

    stale = enumerate_dir(str(tree), True)
    stale.append(Entry("ghost.txt", str(tree / "ghost.txt"), False, 1, 0.0, False, False))

    m.refresh()                        # 另起一次枚举：gen+1、loading=True
    gen_now = node.gen
    assert node.loading is True and node.entries is None

    m._on_entries_loaded(node, stale, gen_now - 1)   # 伪造过期回调
    assert node.loading is True        # 过期结果不得误清当代 loading
    assert m.rowCount(di) == 0         # 过期结果不得插入行

    qtbot.waitUntil(lambda: node.loaded and not node.loading, timeout=5000)
    assert m.rowCount(di) == 3
    assert "ghost.txt" not in _names(m, di)


def test_refresh_after_new_file_wins(qtbot, tree):
    """建文件后重扫：新结果必须可见（即使之前有一次 in-flight 枚举）。"""
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    m.refresh()                       # 第一次重扫（未落完）
    (tree / "late.txt").write_text("x")
    m.refresh()                       # 紧接着再重扫一次
    qtbot.waitUntil(lambda: m.rowCount(di) == 4, timeout=5000)
    assert "late.txt" in _names(m, di)


def test_invalidate_drops_cache(tree):
    entries = enumerate_dir(str(tree))
    DirStoreModel._cache_put(_key(str(tree)), True, entries)
    assert _key(str(tree)) in DirStoreModel._CACHE
    DirStoreModel.notify_dir_changed(str(tree))
    assert _key(str(tree)) not in DirStoreModel._CACHE


def test_refresh_dir_drops_unseen_node(qtbot, tree, tmp_path):
    """未显示中的目录被改动后丢弃节点：导航回来时重新枚举，能看到新建项。"""
    m = DirStoreModel()
    _load(qtbot, m, tree)                      # tree 成为顶层并被加载
    other = tmp_path / "other"
    other.mkdir()
    (other / "one.txt").write_text("1")
    _load(qtbot, m, other)                     # 切走，tree 节点留在 _nodes 里
    (tree / "late.txt").write_text("new")      # 外部新建（无 watcher 可感知）
    m.refresh_dir(str(tree))
    assert _key(str(tree)) not in m._nodes
    di = _load(qtbot, m, tree)
    qtbot.waitUntil(lambda: "late.txt" in _names(m, di), timeout=5000)


# ---------- 零 syscall 目录判定 ----------

def test_entry_is_dir_from_loaded_entries(qtbot, tree):
    m = DirStoreModel()
    _load(qtbot, m, tree)
    assert m.entry_is_dir(str(tree)) is True                 # 顶层目录本身
    assert m.entry_is_dir(str(tree / "dir_a")) is True
    assert m.entry_is_dir(str(tree / "b.txt")) is False
    assert m.entry_is_dir(str(tree / "nowhere")) is None     # 未知，交调用方回退


# ---------- 每模型独占条目 ----------

def test_cache_entries_are_copied_per_node(qtbot, tree):
    """缓存只作模板：两个模型各得一份条目副本，node 反查指向各自节点。"""
    m1 = DirStoreModel()
    di1 = _load(qtbot, m1, tree)
    m2 = DirStoreModel()
    di2 = _load(qtbot, m2, tree)      # 命中 m1 填的类级缓存，走副本路径
    n1 = m1._nodes[_key(str(tree))]
    n2 = m2._nodes[_key(str(tree))]
    assert n1 is not n2
    assert all(a is not b for a, b in zip(n1.entries, n2.entries))
    assert all(e.node is n1 for e in n1.entries)
    assert all(e.node is n2 for e in n2.entries)
    assert sorted(_names(m1, di1)) == sorted(_names(m2, di2))


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
    d1_entries = m._nodes[_key(str(d1))].entries
    assert "only1.txt" in [e.name for e in d1_entries]
    assert "only1.txt" not in _names(m, di2)


def test_index_only_for_displayed_dir(qtbot, tree, tmp_path):
    """非当前显示目录的路径不得返回索引：两层结构的父链有歧义，
    这类索引经代理映射会“看似有效实则错行”。"""
    other = tmp_path.parent / "not_displayed"
    other.mkdir(exist_ok=True)
    (other / "deep.txt").write_text("d")

    m = DirStoreModel()
    _load(qtbot, m, other)                     # 先加载 other，节点留在内存里
    di = _load(qtbot, m, tree)                 # 切回 tree 显示

    assert not m.index(str(other / "deep.txt")).isValid()   # 不属于显示目录
    assert not m.index(str(other)).isValid()                # 其它目录也不能给索引
    assert m.index(str(tree)).isValid()        # 顶层目录自身 OK
    assert m.index(str(tree / "b.txt")).isValid()
    # 子目录作为当前目录的条目，仍可定位（它只是条目，不是顶层节点）
    assert m.index(str(tree / "dir_a")).isValid()
    # 判定任意路径是否目录走 entry_is_dir（不依赖索引）
    assert m.entry_is_dir(str(other)) is True
    assert m.entry_is_dir(str(tree / "dir_a")) is True


# ---------- 生命周期：模型销毁 × 在飞枚举 ----------

def test_load_slot_reads_no_self_state_after_row_insertion(qapp, tree, monkeypatch):
    """锁定现场：行插入之后不得再读实例状态（模型可能在本槽期间被销毁）

    实际抓到的异常是 `_on_entries_loaded` 在 `endInsertRows()` 之后调
    `self._show_hidden()` 报 `AttributeError: 'DirStoreModel' object has no
    attribute '_filter'`（sip 在 C++ 部分销毁时会清空实例 `__dict__`）。这里用同样
    确定的一步代表那个时刻：在 `endInsertRows` 里抹掉 `_filter`，验证剩下的流程
    不再需要它（改前写法在此用例会失败）。
    """
    m = DirStoreModel()
    node = m._ensure_node(str(tree))
    m._start_load(node)

    def wipe_and_pass(*args, **kwargs):
        del m.__dict__["_filter"]        # 模拟“槽跑到一半模型已被销毁”

    monkeypatch.setattr(m, "endInsertRows", wipe_and_pass)
    with qt_exceptions() as errors:
        assert QThreadPool.globalInstance().waitForDone(15000)
        drain_background_pool()
    assert errors == [], f"行插入后仍在读已失效的实例状态: {errors!r}"
    assert node.loaded is True           # 加载本身必须照常完成


def test_in_flight_load_after_model_death_is_dropped(qapp, tmp_path, monkeypatch):
    """契约：枚举还在飞、模型先被销毁时，投递必须安静丢弃

    用两个事件卡住 `enumerate_dir`，把“在飞”做成确定性时序（不靠 sleep 碰运气）；
    同时覆盖 `_loader` 随模型销毁后工作线程里 `emit` 报 RuntimeError 的路径。
    """
    started = threading.Event()
    release = threading.Event()
    real = dm.enumerate_dir

    def slow(path, show_hidden=False):
        started.set()
        release.wait(10)
        return real(path, show_hidden)

    monkeypatch.setattr(dm, "enumerate_dir", slow)

    m = DirStoreModel()
    node = m._ensure_node(str(tmp_path))
    m._start_load(node)
    assert started.wait(10), "后台枚举未启动，测不到在飞投递"
    sip.delete(m)                       # 模型先于枚举结果销毁
    release.set()

    with qt_exceptions() as errors:
        assert QThreadPool.globalInstance().waitForDone(15000)
        drain_background_pool()
    assert errors == [], f"销毁后的投递/emit 报了异常: {errors!r}"
    assert node.loaded is False         # 结果被丢弃，不会再写回一个死模型
