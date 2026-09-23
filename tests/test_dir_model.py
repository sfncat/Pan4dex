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
import time
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


def test_refresh_empty_dir_after_new_file_visible(qtbot, tmp_path):
    """回归：刷新一个「当前为空的已加载目录」后，刚出现的文件必须可见。

    现场：新建目录→导航进去（空，rowCount=0）→往里复制一个文件→状态栏数到
    1 个文件但列表空，F5 刷新仍空。根因：`_reload_top` 的清行块被
    `if node.loaded and node.entries` 挡住（空目录 entries==[] 为假），没把
    `node.loaded` 复位，新枚举结果在采纳端撞上「幂等：node.loaded」守卫被整份丢弃。
    """
    empty = tmp_path / "tmp_test"
    empty.mkdir()
    m = DirStoreModel()
    di = _load(qtbot, m, empty, expected=0)        # 空目录，加载完 0 行
    assert m.rowCount(di) == 0
    (empty / "copied.xlsx").write_text("x")         # 模拟复制进来的文件
    m.refresh()                                     # F5
    qtbot.waitUntil(lambda: m.rowCount(di) == 1, timeout=5000)
    assert _names(m, di) == ["copied.xlsx"]


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

    def slow(path, show_hidden=False, cancel=None):
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


# ---------- 可中断的枚举（L2：切走窗格不继续扫 / 枚举能取消） ----------

def test_enumerate_dir_cancel_token_stops_mid_scan(tmp_path):
    """取消令牌置位后，`enumerate_dir` 必须**抛** `_EnumerationAborted` 而不是交回半截列表

    半截列表与「目录本来就这么多项」在采纳端分不开；分不开就会被当成完整快照
    写进视图，用户在万条目共享上看到的是一个安静的、看不出的截断列表。
    """
    from core.dir_model import _EnumerationAborted

    for i in range(600):                # > _ENUM_CANCEL_CHECK_EVERY(256)，能命中中途
        (tmp_path / f"f{i}.txt").write_text("x")

    hits = []

    def token():
        hits.append(1)
        return len(hits) >= 2           # 第二次被问时才是「该停了」

    with pytest.raises(_EnumerationAborted):
        dm.enumerate_dir(str(tmp_path), True, cancel=token)
    assert 1 <= len(hits) < 600, f"取消探测没起作用：{len(hits)}"

    # 不传 cancel 时行为与改前完全一致（完整列表、不抛）
    assert len(dm.enumerate_dir(str(tmp_path), True)) == 600


# 替身扫描的控住门，按路径各一扇：一份替身要顶替好几个目录的扫描（切走的与被
# 切到的），共用手门会让「放行 A」把 B 也放出去、「停 A」也把 B 停掉。
_gates = {}


class _Gate:
    __slots__ = ("barrier", "release")

    def __init__(self):
        self.barrier = threading.Event()   # 告知主线程「本目录的扫描真的在飞了」
        self.release = threading.Event()   # 主线程放行，worker 继续


class _ScanHold:
    """替身扫描的现场：每个目录各扫了几项

    计数**按路径分**：一份替身要顶替好几个目录的扫描（切走的与被切到的），全局计数
    会把「本地那份不该被中断」答到另一份扫描的数字上。而「该不该停」一律问
    `check()`（= 产品自己的 `_Enumerator` + `_LoadTask`），替身不自带一套取消判据
    —— 自己实现一判据就只能测到自己那套（本轮踩过：拿旧任务当全局令牌，把
    F5 后的新扫描也误判为过期，测出来的是假红）。
    """
    __slots__ = ("visited", "by_task")

    def __init__(self):
        self.visited = {}
        self.by_task = {}          # (dirkey, id(task)) -> 本任务扫了几项

    def count(self, path):
        return self.visited.get(_key(path), 0)

    def count_task(self, path, task):
        return self.by_task.get((_key(path), id(task)), 0)


class _FakeSlow:
    """把若干目录扮成「慢位置」，不碰真挂载表（`_is_network` 在 Linux 上读 /proc/mounts）"""

    def __init__(self, slow_paths):
        slow = {_key(p) for p in slow_paths}

        def probe(path):
            return _key(path) in slow
        self.probe = staticmethod(probe)


def _patch_scan(monkeypatch, total=4000, stop_at=100):
    """把扫描主体换成「逐项 + 可设堵」的替身，不靠 sleep 碰时序。

    只替 `_scan_into`（它不接收 `cancel` 参数），所以 `_Enumerator.check` 的探测与
    `_EnumerationAborted` 的抛出都在被测路径上：替身**只数项与设堵**，要不要停全由
    `check()` 决定。worker 扫到 `stop_at` 项时**控住**（置本目录的 `barrier`、等
    `release`），于是「在飞」成了确定事实 —— 不控住就是拿主线程与 worker 赛跑，
    一个空转的 4000 项扫描很可能在我们标记之前就扫完了。
    """
    hold = _ScanHold()

    def fake(path, entries, show_hidden, check=None, _h=hold, _t=total, _at=stop_at):
        key = _key(path)
        gate = _gates.setdefault(key, _Gate())
        # `check` 是产品的 `_Enumerator.check`（绑定方法）；`check.__self__._cancel` 就是
        # 本次扫描的取消令牌（= 拥有它的 `_LoadTask`），据此按任务分开计数（同一
        # 目录被超越的两代扫描不会混到一个数字上）。
        owner = id(getattr(getattr(check, "__self__", None), "_cancel", None))
        for i in range(_t):
            if check is not None:
                check()                    # 产品的取消判据：该停就抛 `_EnumerationAborted`
            if _at is not None and i == _at:
                gate.barrier.set()
                assert gate.release.wait(10), "主线程未放行，替身扫描卡住了"
            _h.visited[key] = _h.visited.get(key, 0) + 1
            _h.by_task[(key, owner)] = _h.by_task.get((key, owner), 0) + 1
        return None

    _gates.clear()
    monkeypatch.setattr(dm, "_scan_into", fake)
    return hold


def _navigate_in_flight(m, path, hold=None, timeout=10.0):
    """导航到 `path` 并等到后台**真的在逐项扫**（控住中），返回在飞的那个任务"""
    key = _key(str(path))
    if m._pending.get(key) is None:
        m.set_directory(str(path))
    gate = _gates.get(key)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if gate is not None and gate.barrier.wait(0.05):
            task = m._pending.get(key)
            if task is not None:
                return task
        time.sleep(0.001)
        gate = _gates.get(key)
    pytest.skip("后台枚举未进入在飞状态，测不到中断")


def _settle():
    """放行所有控住的扫描，等在飞任务跑完并把排队投递派发干净

    只能控住在飞的那一份扫描：新发起的扫描若在 `waitForDone` **之后**才跑到门，
    拿到的已是一个被放行过的门（`release` 是电平信号），不会卡住 —— 需要控住的
    新扫描请单独 `_navigate_in_flight`，不要指望本函数替它控。
    """
    for gate in _gates.values():
        gate.barrier.set()
        gate.release.set()
    assert dir_pool().waitForDone(15000), "后台枚举没跑完：取消逻辑可能把任务锁死了"
    with qt_exceptions() as errors:
        drain_background_pool()
    assert errors == [], f"中断/采纳链路上报了异常: {errors!r}"


def test_superseded_scan_is_aborted_and_does_not_hurt_new_request(qapp, tmp_path, monkeypatch):
    """gen 变了就不再扫、也不回投；而迟到的中断通知不得误清当代请求的 loading

    这是 gotchas 24「别把一次枚举发起两遍」的反面：F5 之后旧扫描得让路，但它那句
    「我停了」的回报不能把当代请求的 `loading=True` 抹掉 —— 抹掉了同一个目录会被
    并发扫两遍，而旧快照还可能洗白当代快照。旧扫描不经过 `abandoned` 标志，
    单靠 gen 自停，这条就是那个分支的回归防护。
    """
    a = tmp_path / "a"
    a.mkdir()
    hold = _patch_scan(monkeypatch, total=4000, stop_at=600)

    m = DirStoreModel()
    m.set_directory(str(a))                 # refresh() 只重扫「当前显示」的目录
    old_task = _navigate_in_flight(m, a, hold)
    node = m._top_node
    gen_old = old_task.gen

    m.refresh()                             # 显式重扫：gen+1 并另起一次枚举
    new_task = m._pending.get(_key(str(a)))
    assert new_task is not old_task and new_task.gen == gen_old + 1
    _gates[_key(str(a))].release.set()      # 放行：旧的一放行就早退，新的照常跑完

    _settle()

    # 两代扫同一目录：按任务分计数，才能分清「新的跑完 / 旧的让路」而不被求和掩盖
    assert hold.count_task(a, new_task) == 4000, "新扫描没跑完"
    assert hold.count_task(a, old_task) < 4000, "旧扫描没在 gen 变化后早退"
    assert old_task.abandoned is False     # 它靠 gen 自停，不经过 abandoned 标志
    assert node.loaded is True and node.loading is False
    assert node.gen == gen_old + 1
    assert new_task.abandoned is False     # 迟到的一代没把当代标记成放弃
    assert m._pending.get(_key(str(a))) is None


def test_navigating_away_from_slow_location_stops_the_scan(qapp, tmp_path, monkeypatch):
    """L2 主案：切走窗格后，慢位置上的在飞枚举要停，且结果不得回投主线程采纳"""
    slow = tmp_path / "nas_big10k"
    quiet = tmp_path / "local"
    slow.mkdir()
    quiet.mkdir()
    hold = _patch_scan(monkeypatch, total=4000, stop_at=300)
    monkeypatch.setattr(DirStoreModel, "_is_network", _FakeSlow([slow]).probe)

    m = DirStoreModel()
    task = _navigate_in_flight(m, slow, hold)

    m.set_directory(str(quiet))          # 导航离开慢位置
    assert task.abandoned is True, \
        "切走的慢位置扫描未被放弃（`_drop_stale_scans` 没认出刚离开的那个节点）"

    _settle()

    assert 0 < hold.count(slow) < 4000, \
        f"要么一项都没扫（{hold.count(slow)}），要么扫完了全部"
    node = m._nodes[_key(str(slow))]
    assert node.loaded is False          # 没被采纳（一次 `beginInsertRows` 也没跑）
    assert node.entries is None          # 手里那份条目根本没交给模型
    assert node.loading is False         # 复位了：导航回来能重新发起
    assert node.abandoned is False       # 结清后回到中性态
    assert m._pending.get(_key(str(slow))) is None


def test_navigating_away_from_local_dir_is_not_interrupted(qapp, tmp_path, monkeypatch):
    """反向守卫：本地目录不因「切走」而中断 —— 否则本地万条目会被扫两遍

    只中断慢位置是刻意的：本地一次扫描最多几百毫秒，让它跑完不浪费；而一个 SMB
    共享能扫十几秒（实测 10.08s），白耗那一整段的正是 L2 查出的缺口。
    """
    a = tmp_path / "local_a"
    b = tmp_path / "local_b"
    a.mkdir()
    b.mkdir()
    hold = _patch_scan(monkeypatch, total=200, stop_at=100)
    monkeypatch.setattr(DirStoreModel, "_is_network", _FakeSlow([]).probe)

    m = DirStoreModel()
    task = _navigate_in_flight(m, a, hold)
    _gates[_key(str(b))] = _Gate()       # 预先放行 b 的门：它的扫描可能在
                                         # `waitForDone` 之后才跑到门，不能让它卡住
    _settle()                            # 放行并等 a 扫完（本地位 → 不该被标记放弃）
    assert task.abandoned is False, "本地扫描被无谓中断了（慢位置判据越界）"
    assert hold.count(a) == 200          # 一跑到黑，结果照常回投
    assert m._nodes[_key(str(a))].loaded is True

    m.set_directory(str(b))               # b 从未在飞，替身对它无令牌 → 不会早退
    _settle()
    assert hold.count(b) == 200, "切到新目录后，本地那份扫描也不该被中断"
    assert m._nodes[_key(str(a))].loaded is True   # 切走之后也不因迟到通知被改回未加载


def test_cancel_load_stops_scan_and_allows_reload(qtbot, tmp_path, monkeypatch):
    """显式取消入口（L2「能取消」的产品侧答案）：停扫 + 复位 loading + 回来能重扫"""
    a = tmp_path / "big"
    a.mkdir()
    hold = _patch_scan(monkeypatch, total=6000, stop_at=200)

    m = DirStoreModel()
    node = m._ensure_node(str(a))
    m._start_load(node)
    task = _navigate_in_flight(m, a, hold)
    m.cancel_load(str(a))                # 不分本地/远端，一律停
    assert task.abandoned is True, \
        "任务必须留在 `_pending` 里等自己投 cancelled 除名（现在就弹掉则 loading 复位不了）"
    assert hold.count(a) < 6000, "取消后替身扫描没早退"

    _settle()                            # 放行 worker 正控住的那扇门（旧 gate）：
                                         # 它一被放行就探到 abandoned → 早退，不回投

    assert node.loaded is False and node.loading is False
    assert m._pending.get(_key(str(a))) is None

    def no_stop(path, entries, show_hidden, check=None):
        for i in range(3):
            entries.append(Entry(f"g{i}.txt", os.path.join(path, f"g{i}.txt"),
                                 False, 1, 0.0, False, False))
        return None

    monkeypatch.setattr(dm, "_scan_into", no_stop)
    di = _load(qtbot, m, a, expected=3)
    assert _names(m, di) == ["g0.txt", "g1.txt", "g2.txt"]


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
