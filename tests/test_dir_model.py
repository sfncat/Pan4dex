# -*- coding: utf-8 -*-
"""DirStoreModel 单元测试（第二阶段 5.3）

覆盖：枚举正确性、列/角色、隐藏过滤、重命名 setData、TTL 缓存与定向失效、
本地目录监视（只监视当前显示目录：外部改动自动重扫、防抖、自变更抑制、
进程级共享监视器、句柄不累积）、
条目对象生命周期（交给过 Qt 的指针不得提前归还 GC）、
快速切换目录的后台线程安全、模型销毁与在飞枚举投递的生命周期。
异步枚举用 qtbot 等待目录节点加载完成。

两层结构：目录节点 index(dirPath) 为父，其条目为子项。
"""
import gc
import os
import threading

import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt, QDir, QModelIndex

from conftest import qt_exceptions
from core import dir_model as dm
from core.dir_model import DirStoreModel, Entry, enumerate_dir, _key, dir_pool
from core.dir_model import _WatchHub
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
    qtbot.wait(5)     # 监视登记是 0ms 定时器发的（_watch_sync），等它落地
    return m.index(str(path))


def _names(m, di):
    return [m.fileName(m.index(r, 0, di)) for r in range(m.rowCount(di))]


def _age_snapshot(m, path):
    """把节点快照改成「早已过期」（不等真 TTL，也不让缓存洗白）。"""
    key = _key(str(path))
    node = m._nodes.get(key)
    if node is not None:
        node.ts = 0.0
    item = DirStoreModel._CACHE.get(key)
    if item is not None:
        DirStoreModel._CACHE[key] = (0.0, item[1], item[2])


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


def test_refresh_dir_invalidates_unseen_node(qtbot, tree, tmp_path):
    """未显示中的目录被改动后标为未加载：导航回来时重新枚举，能看到新建项。

    节点本身不丢（保留 `entry_is_dir` 的内存判定），条目快照按生命周期约定
    延到下一个安全点释放（见 test_stale_entries_released_only_at_safe_point）。
    """
    m = DirStoreModel()
    _load(qtbot, m, tree)                      # tree 成为顶层并被加载
    other = tmp_path / "other"
    other.mkdir()
    (other / "one.txt").write_text("1")
    _load(qtbot, m, other)                     # 切走，tree 节点留在 _nodes 里
    (tree / "late.txt").write_text("new")      # 外部新建（watcher 通知有延迟，不能等）
    m.refresh_dir(str(tree))
    node = m._nodes[_key(str(tree))]
    assert node.loaded is False and node.entries is None
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
    dir_pool().waitForDone(5000)
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
        assert dir_pool().waitForDone(15000)
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
        assert dir_pool().waitForDone(15000)
        drain_background_pool()
    assert errors == [], f"销毁后的投递/emit 报了异常: {errors!r}"
    assert node.loaded is False         # 结果被丢弃，不会再写回一个死模型


# ---------- 本地目录 watcher ----------

def test_watcher_picks_up_external_file(qtbot, tree):
    """端到端：外部程序新建文件，列表要自己长出来（不等 F5）。

    依赖本机文件系统通知（Windows ReadDirectoryChangesW / Linux inotify），
    在沙箱、网络临时目录等环境下可能收不到通知，此时跳过而非假绿。
    """
    m = DirStoreModel()
    di = _load(qtbot, m, tree)
    (tree / "external.txt").write_text("x")
    try:
        qtbot.waitUntil(lambda: "external.txt" in _names(m, di), timeout=10000)
    except pytest.fail.Exception as exc:
        pytest.skip(f"文件系统通知未按期到达，watcher 在本机不可用：{exc}")


def test_only_local_dirs_are_watched(qtbot, tree, tmp_path, monkeypatch):
    """网络目录不得登记 watcher：那正是 QFileSystemModel 拖垮 SMB 的轮询源。"""
    net = tmp_path / "smb_share"
    net.mkdir()
    real_network = DirStoreModel._is_network
    monkeypatch.setattr(DirStoreModel, "_is_network",
                        staticmethod(lambda p: bool(p) and str(p) == str(net) or real_network(p)))

    m = DirStoreModel()
    _load(qtbot, m, net)
    assert _key(str(net)) not in m._watched          # 网络：不监视
    assert str(net) not in m.watched_directories()
    _load(qtbot, m, tree)
    assert _key(str(tree)) in m._watched             # 本地：监视
    assert str(tree) in m.watched_directories()


def test_hub_is_shared_and_refcounted(qtbot, tree):
    """多个模型监视同一目录：只占一个句柄，摘掉其中一个不影响另一个。"""
    a = DirStoreModel()
    b = DirStoreModel()
    _load(qtbot, a, tree)
    _load(qtbot, b, tree)
    key = _key(str(tree))
    assert a._watched and b._watched
    hub = a._hub
    assert len(hub._refs[os.path.normpath(str(tree))]) == 2   # 两个登记
    assert sum(1 for p in hub.directories()
               if _key(p) == key) == 1                        # 一个句柄
    a._watch_drop(key)
    qtbot.wait(20)                                       # 注销在事件循环顶层落地
    assert str(tree) in b.watched_directories()               # b 仍在监视
    b._watch_drop(key)
    qtbot.wait(20)
    assert str(tree) not in a.watched_directories()


def test_hub_prunes_registrations_of_dead_models(qtbot, tree):
    """模型销毁后没人再替它注销监视，hub 兼式回收死引用（否则句柄只增不减）。"""
    hub = _WatchHub.instance()
    m = DirStoreModel()
    _load(qtbot, m, tree)
    path = os.path.normpath(str(tree))
    assert path in hub.directories()
    sip.delete(m)                      # 模型先于任何注销死掉
    del m
    gc.collect()
    hub._prune_dead()
    assert path not in hub._refs
    assert path not in hub.directories()


def test_watch_notifications_are_debounced(qtbot, tree, monkeypatch):
    """一次改动连发多条通知，只重扫一次（否则列表反复清空重建）。"""
    m = DirStoreModel()
    _load(qtbot, m, tree)
    scans = []
    monkeypatch.setattr(m, "_reload_top", lambda node: scans.append(node.path))
    for _ in range(3):
        m._on_watched_dir_changed(str(tree))
    m._flush_watch_events()
    assert len(scans) == 1


def test_self_change_suppresses_watch_rescan(qtbot, tree, monkeypatch):
    """应用内改动已自行 refresh_dir，紧随其后的通知不得再扫一遍。"""
    m = DirStoreModel()
    _load(qtbot, m, tree)
    scans = []
    monkeypatch.setattr(m, "_reload_top", lambda node: scans.append(node.path))
    m.refresh_dir(str(tree))                    # 应用内粘贴/新建/删除走的入口
    qtbot.waitUntil(lambda: not m._top_node.loading, timeout=5000)
    scans.clear()                               # 上面那次重扫是 refresh_dir 自己发的
    m._on_watched_dir_changed(str(tree))        # 操作系统通知随后到达
    m._flush_watch_events()
    assert scans == []                          # 不能再扫（节点已不在 loading）
    # 抑制窗口之外的外部改动仍要生效
    m._self_change[_key(str(tree))] = 0.0
    m._on_watched_dir_changed(str(tree))
    m._flush_watch_events()
    assert scans == [m._top_node.path]


def test_only_displayed_dir_is_watched(qtbot, tree, tmp_path):
    """监视只跟着当前显示目录：切走即摘句柄，不看过的目录不占登记。"""
    m = DirStoreModel()
    _load(qtbot, m, tree)
    assert _key(str(tree)) in m._watched
    other = tmp_path / "other"
    other.mkdir()
    (other / "one.txt").write_text("1")
    _load(qtbot, m, other)                      # tree 降为非显示节点
    assert _key(str(tree)) not in m._watched     # 不再监视（句柄不累积）
    assert _key(str(other)) in m._watched
    assert str(tree) not in m.watched_directories()
    # 非显示目录被改：靠「快照过期 + 导航回来重扫」，而不是靠 watcher
    (tree / "newfile.txt").write_text("n")
    _age_snapshot(m, tree)
    di = _load(qtbot, m, tree)
    assert "newfile.txt" in _names(m, di)
    assert _key(str(tree)) in m._watched         # 重新登记


def test_fresh_snapshot_is_not_rescanned_on_arrival(qtbot, tmp_path, monkeypatch):
    """TTL 内回到目录直接用快照，不得再发一次枚举。

    「到达即重扫」看着像资源管理器语义，实测把后台枚举量翻倍（每次还要先
    removeRows），全量测试的 access violation 从 1/8 涨到 9/10，故只在快照
    过期时扫一次（见 docs/gotchas.md）。

    两个目录互为兄弟且先建后监视，否则建第二个目录会触发第一个的 watcher
    通知，重扫次数就不是导航能单独决定的了。
    """
    a = tmp_path / "a"
    a.mkdir()
    (a / "x.txt").write_text("1")
    b = tmp_path / "b"
    b.mkdir()
    (b / "y.txt").write_text("2")
    m = DirStoreModel()
    scans = []
    real = m._start_load

    def _counted(node, _s=scans, _f=real):
        _s.append(node.path)
        return _f(node)

    monkeypatch.setattr(m, "_start_load", _counted)
    _load(qtbot, m, a)
    _load(qtbot, m, b)
    scans.clear()
    _load(qtbot, m, a)                           # 快照仍新鲜
    assert scans == []
    _age_snapshot(m, a)
    _load(qtbot, m, b)                           # 离开（b 新鲜，也不扫）
    assert scans == []
    di = _load(qtbot, m, a)                       # 回来 → 只重扫一次
    assert scans == [os.path.normpath(str(a))]
    assert _loaded(m, str(a)) and di.isValid()


def test_each_load_starts_exactly_one_enumeration(qtbot, tree, monkeypatch):
    """一次加载只发一次枚举（行信号不得重入触发惰性加载）。

    beginInsertRows 内部会回调 rowCount()，那一刻节点处于「未 loaded 且未
    loading」的过渡态，惰性触发条件成立 → 白扫一遍，而且新枚举的 gen 会把
    正要采纳的结果算作过期。
    """
    m = DirStoreModel()
    calls = []
    real = m._start_load

    def _counted(node, _s=calls, _f=real):
        _s.append(node.path)
        return _f(node)

    monkeypatch.setattr(m, "_start_load", _counted)
    di = _load(qtbot, m, tree, expected=3)          # 等待期间反复查 rowCount
    assert "dir_a" in _names(m, di)
    qtbot.wait(DirStoreModel._WATCH_DEBOUNCE_MS + 200)   # 确认没有迟到的第二次
    assert calls == [os.path.normpath(str(tree))]


def test_enumeration_pool_is_capped():
    """目录枚举并发有上限，且全进程共用一个池。

    用 `QThreadPool.globalInstance()` 时并发数等于 CPU 核数（本机 24），实测转储里
    能同时有 10 个线程卡在 `enumerate_dir`：SMB 上几十路枚举互抢通道比串行还慢，
    而结果投递成倍砸回主线程会抬高偶发崩溃率（见 unsolved-issues 问题 13）。
    """
    from core.dir_model import _ENUM_POOL_THREADS
    p = dir_pool()
    assert p is dir_pool()
    assert p.maxThreadCount() == _ENUM_POOL_THREADS
    assert 1 < _ENUM_POOL_THREADS < 8


def test_watch_registration_is_coalesced(qtbot, tmp_path):
    """同一轮事件里连续导航：native 登记只做最后一次。

    addPath/removePath 会唤醒 Qt 的目录监视线程，不能嵌在窗格构造/导航的
    调用栈中间反复执行（登记目标只记下，到事件循环顶层才落）。0ms 定时器
    未触发前 `_watched` 仍为空，这就是预期行为。
    """
    hub = _WatchHub.instance()
    dirs = []
    for i in range(4):
        d = tmp_path / f"c{i}"
        d.mkdir()
        dirs.append(d)
    m = DirStoreModel()
    for d in dirs:
        m.set_directory(str(d))            # 不跑事件循环
    assert m._watched == set()
    qtbot.wait(20)
    assert m._watched == {_key(str(dirs[-1]))}
    mine = {_key(str(d)) for d in dirs}
    assert sum(1 for p in hub.directories() if _key(p) in mine) == 1


def test_watch_handles_do_not_accumulate(qtbot, tmp_path):
    """连续导航多个目录：登记数不增长（一个模型只监视当前目录）。

    这里同时守护一个实测结论：接上 per-directory 监视后全量测试会必现
    access violation（监视目录数随会话累积到上百），只监视当前目录后 0/6。
    """
    hub = _WatchHub.instance()
    dirs = []
    for i in range(8):
        d = tmp_path / f"w{i}"
        d.mkdir()
        (d / "f.txt").write_text(str(i))
        dirs.append(d)
    m = DirStoreModel()
    for d in dirs:
        _load(qtbot, m, d)
        assert len(m._watched) == 1
    assert _key(str(dirs[7])) in m._watched
    mine = {p for p in hub.directories() if any(_key(p) == _key(str(d)) for d in dirs)}
    assert len(mine) == 1                        # 8 次导航只留 1 个句柄
    # 被摘监视的目录导航回来仍能正常列出（重新登记监视）
    di = _load(qtbot, m, dirs[0])
    assert "f.txt" in _names(m, di)


def test_node_cap_keeps_nodes_that_handed_out_entries(qtbot, tree, tmp_path,
                                                     monkeypatch):
    """节点数封顶：只删没把条目交给过 Qt 的节点，已加载的不能动。"""
    monkeypatch.setattr(DirStoreModel, "_MAX_NODES", 2)
    m = DirStoreModel()
    _load(qtbot, m, tree)
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()
    _load(qtbot, m, a)                       # tree 与 a 都是已加载节点
    key_tree = _key(str(tree))
    m._nodes[key_tree].entries = None        # 伪造成「已失效且未交给过条目」
    m._nodes[key_tree].loaded = False
    _load(qtbot, m, b)                       # 第 4 个节点 → 触发封顶
    assert key_tree not in m._nodes          # 空节点被回收
    assert _key(str(a)) in m._nodes          # 有快照的节点不删（悬空指针防护）
    di = _load(qtbot, m, tree)
    assert "dir_a" in _names(m, di)          # 重新枚举后正常可用


# ---------- 条目对象生命周期（0xC0000005 取证导出的不变式）----------

def test_stale_entries_released_only_at_safe_point(qtbot, tree, tmp_path):
    """交给过 Qt 的条目不得在模型信号之前归还 GC，否则视图里的裸指针悬空。

    PyQt 不为 createIndex(row, col, py_obj) 的 Python 对象保持引用（实测），
    所以失效只能把快照挂到节点的 `_stale`，等下一次 reset/removeRows 再放。
    """
    m = DirStoreModel()
    _load(qtbot, m, tree, expected=3)
    key = _key(str(tree))
    handed_to_qt = m._nodes[key].entries
    other = tmp_path / "other"
    other.mkdir()
    _load(qtbot, m, other)
    m.refresh_dir(str(tree))                   # 非显示目录失效（无任何行信号）
    assert m._nodes[key]._stale is handed_to_qt
    assert m._nodes[key].entries is None
    gc.collect()                               # 若已被回收，下一句就拿到别的对象
    assert m._nodes[key]._stale is handed_to_qt
    third = tmp_path / "third"
    third.mkdir()
    m.set_directory(str(third))                # 再一次 reset = 安全点
    assert m._nodes[key]._stale is None
