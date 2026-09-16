# -*- coding: utf-8 -*-
"""列表筛选（`widgets/filter_bar.py` → `PaneSortProxyModel` → 窗格 / 超大图标视图）。

覆盖三层：查询文本的编译语法（纯 Python）、筛选栏交互（防抖 / 字段下拉 / Esc）、
接入真实模型与窗格后的可见行与状态栏计数。
"""
import os
import time
from datetime import datetime, timedelta

import pytest

from core.dir_model import dir_pool
from widgets.filter_bar import compile_filter, split_query


def _visible_names(proxy, root):
    return sorted(proxy.data(proxy.index(r, 0, root))
                  for r in range(proxy.rowCount(root)))


# ---------- 查询文本 → 匹配器 ----------

def test_bare_text_is_name_substring_and_case_insensitive():
    f = compile_filter("repo")
    assert f.matches("Report 2026.docx", False)
    assert not f.matches("readme.md", False)


def test_glob_matches_whole_name():
    f = compile_filter("*.log")
    assert f.matches("app.LOG", False)
    assert not f.matches("app.log.1", False)      # 通配符是「整名」而非「包含」
    assert compile_filter("?at").matches("cat", False)
    assert not compile_filter("?at").matches("cat.txt", False)


@pytest.mark.parametrize("query,name,is_dir,want", [
    ("ext:py,md", "a.py", False, True),
    ("扩展名:.txt", "b.txt", False, True),
    ("ext:py", "package", True, False),           # 扩展名条件不匹配目录
    ("type:txt", "b.txt", False, True),
    ("类型:目录", "sub", True, True),
    ("is:file", "sub", True, False),
    ("属性:文件", "a.txt", False, True),
])
def test_ext_type_and_kind_fields(query, name, is_dir, want):
    f = compile_filter(query)
    assert f.matches(name, is_dir) is want


@pytest.mark.parametrize("query,size,want", [
    ("size:>10mb", 11 * 1024 * 1024, True),
    ("size:>10mb", 10 * 1024 * 1024, False),
    ("size:>=10mb", 10 * 1024 * 1024, True),
    ("size:<1kb", 512, True),
    ("size:1mb-100mb", 50 * 1024 * 1024, True),
    ("size:1mb-100mb", 500 * 1024 * 1024, False),
    ("size:空", 0, True),
    ("size:none", 5, False),
    ("size:大型", 2 * 1024 * 1024, True),
    ("size:巨大", 2 * 1024 * 1024, False),
    ("大小:>1gb", 2 * 1024 ** 3, True),
])
def test_size_field(query, size, want):
    f = compile_filter(query)
    assert f.matches("f.bin", False, size) is want
    assert f.matches("dir", True, -1) is False    # 目录不匹配任何 size 条件


def _local_noon(days_ago=0.0):
    """N 天前的本地中午（日期预设按**日历天**算，不能从 `time.time()` 起算）

    从当前时刻起算时，“1.2 天前”在凌晨跑就是一笔跨了两个午夜 → 落在前天而不是
    昨天，用例在每天 00:00–04:48 这个窗口里必红（实测 01:2x 跑挂）。写文件的
    时间也常在夜里，那本就是要测得到的输入。
    """
    base = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    return (base - timedelta(days=days_ago)).timestamp()


def _this_monday():
    """本周一中午（“0.5 天前”在周一上午跑属于上周，同一个形状）"""
    return _local_noon(datetime.now().weekday())


def _first_of_month():
    base = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    return base.replace(day=1).timestamp()


@pytest.mark.parametrize("query,build_mtime,want", [
    ("date:今天", lambda: _local_noon(0), True),
    ("date:今天", lambda: _local_noon(1.5), False),
    ("date:昨天", lambda: _local_noon(1.2), True),
    ("date:昨天", lambda: _local_noon(0.1), False),      # 今天上午 → 是今天，不是昨天
    ("date:本周", _this_monday, True),
    ("date:本月", _first_of_month, True),
])
def test_date_presets(query, build_mtime, want):
    """时刻在**用例里**算，不在 `parametrize` 里算

    参数表在收集阶段就求值了，而 `date:今天` 的参考日在执行时才读表：一次跑
    只要跨过午夜（23:5x 收集、00:0x 执行，实测遇过三次）三条期望就集体错一天。
    """
    assert compile_filter(query).matches("f", False, 10, build_mtime()) is want


def test_date_explicit_ranges_and_operators():
    ts = lambda y, mo, d, h=12: time.mktime((y, mo, d, h, 0, 0, 0, 0, 0))
    assert compile_filter("date:>=2026-01-01").matches("f", False, 10, ts(2026, 5, 1))
    assert not compile_filter("date:>=2026-01-01").matches("f", False, 10, ts(2025, 5, 1))
    # `>` 是「整天之后」：当天 12:00 也不算（与 `<=` 包含整天对称）
    assert not compile_filter("date:>2026-01-01").matches("f", False, 10, ts(2026, 1, 1))
    assert compile_filter("date:>2026-01-01").matches("f", False, 10, ts(2026, 1, 2))
    assert compile_filter("date:<=2026-01-01").matches("f", False, 10, ts(2026, 1, 1, 23))
    assert compile_filter("date:2026-01-01..2026-03-01").matches("f", False, 10, ts(2026, 2, 15))
    assert not compile_filter("date:2026-01-01..2026-03-01").matches("f", False, 10, ts(2026, 4, 1))
    assert compile_filter("date:2026-09").matches("f", False, 10, ts(2026, 9, 30))
    assert not compile_filter("date:2026-09").matches("f", False, 10, ts(2026, 8, 30))
    # 分隔符宽容：`2026/09/13`、`2026.09.13` 与 `2026-09-13` 同义
    for text in ("date:2026-09-13", "date:2026/09/13", "date:2026.09.13"):
        assert compile_filter(text).matches("f", False, 10, ts(2026, 9, 13)), text


def test_regex_field_and_bad_regex_degrades_to_name():
    assert compile_filter("re:^report\\d+\\.txt$").matches("report12.txt", False)
    assert not compile_filter("re:^report\\d+\\.txt$").matches("xreport12.txt", False)
    bad = compile_filter("re:([unclosed")
    assert bad.bad == ("re:([unclosed",)
    assert bad.matches("re:([unclosed", False)     # 降级为「名称包含」


@pytest.mark.parametrize("query", ["date:写错了", "size:abc", "is:也许"])
def test_unparsable_value_is_recorded_and_degraded(query):
    """解析不了的条件记进 `bad` 并降级为名称匹配：不弹窗，也不静默变成「没筛」"""
    f = compile_filter(query)
    assert f.bad == (query,)
    assert f.active
    assert not f.matches("a.txt", False)


def test_multiple_terms_are_anded():
    f = compile_filter("ext:txt size:>1kb")
    assert f.matches("a.txt", False, 2048)
    assert not f.matches("a.txt", False, 10)       # 扩展名对、大小不对 → 排除
    assert not f.matches("a.md", False, 2048)


def test_quoted_phrase_stays_one_term():
    assert split_query('name:"第三季度 报告" ext:docx') == ["name:第三季度 报告", "ext:docx"]
    assert compile_filter('name:"a b"').matches("xx a b yy", False)


def test_empty_query_is_inactive_and_matches_everything():
    for text in ("", "   ", "\t"):
        f = compile_filter(text)
        assert not f.active
        assert f.matches("anything", True)


def test_needs_stat_marks_only_size_and_date():
    assert compile_filter("size:>1kb").needs_stat
    assert compile_filter("date:本周").needs_stat
    assert not compile_filter("ext:py").needs_stat
    assert not compile_filter("报告").needs_stat


# ---------- 筛选栏交互 ----------

def test_filter_bar_debounces_typing(qtbot):
    """逐字符重筛在上万行的目录里肉眼可见地卡：停手 250ms 后才发一次"""
    from widgets.filter_bar import FilterBar

    bar = FilterBar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.filter_changed, timeout=3000) as sig:
        bar.filter_edit.setText("*.txt")
    assert sig.args == ["*.txt"]


def test_filter_bar_field_mode_composes_prefix(qtbot):
    from widgets.filter_bar import FilterBar

    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.filter_type.setCurrentText("大小")
    with qtbot.waitSignal(bar.filter_changed, timeout=3000) as sig:
        bar.set_query("10mb")
    assert sig.args == ["size:10mb"]
    assert bar.query() == "size:10mb"

    # 用户自己写了字段前缀时以原文为准，下拉不再重复贴一层
    bar.filter_type.setCurrentText("名称")
    assert bar.compose_query("ext:py") == "ext:py"
    bar.filter_type.setCurrentText("自动")
    assert bar.compose_query("ext:py 报告") == "ext:py 报告"


def test_filter_bar_escape_clears_query(qtbot):
    from PyQt6.QtCore import Qt
    from widgets.filter_bar import FilterBar

    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.show()
    bar.set_query("*.log")
    assert bar.query() == "*.log"
    with qtbot.waitSignal(bar.escape_pressed, timeout=2000):
        qtbot.keyClick(bar.filter_edit, Qt.Key.Key_Escape)
    assert bar.query() == ""


def test_filter_bar_emptying_text_clears_without_debounce(qtbot):
    from widgets.filter_bar import FilterBar

    bar = FilterBar()
    qtbot.addWidget(bar)
    bar.set_query("*.log")
    with qtbot.waitSignal(bar.filter_changed, timeout=1000) as sig:
        bar.filter_edit.setText("")
    assert sig.args == [""]


# ---------- 接入模型 / 窗格 ----------

@pytest.fixture
def tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text("i")
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.md").write_text("x" * 4096)
    return tmp_path


def _load_model(tmp_path, qtbot):
    """搭起 DirStoreModel + PaneSortProxyModel，并等顶层枚举落地。

    必须转事件循环：枚举结果是从后台线程投递给模型的 queued 信号，
    光 `waitForDone` 只能保证“活干完了”，采纳还在主线程队列里。
    """
    from PyQt6.QtCore import QCoreApplication
    from core.dir_model import DirStoreModel
    from core.pane import PaneSortProxyModel

    src = DirStoreModel()
    proxy = PaneSortProxyModel()
    proxy.setSourceModel(src)
    src_root = src.set_directory(str(tmp_path))

    def _loaded():
        dir_pool().waitForDone(50)
        QCoreApplication.processEvents()
        return src.rowCount(src_root) >= 3
    qtbot.waitUntil(_loaded, timeout=5000)
    proxy_root = proxy.mapFromSource(src_root)
    return src, proxy, src_root, proxy_root


def test_proxy_hides_rows_that_do_not_match(tree, qtbot):
    """筛选挂在排序代理上：只改可见行，不动模型数据（不重扫、不发行信号）"""
    from PyQt6.QtCore import QModelIndex

    src, proxy, src_root, proxy_root = _load_model(tree, qtbot)
    assert _visible_names(proxy, proxy_root) == ["a.txt", "b.md", "sub"]

    proxy.set_entry_filter(compile_filter("*.txt"))
    assert _visible_names(proxy, proxy_root) == ["a.txt"]
    # 源模型一行没少：筛选不该造成任何重扫
    assert src.rowCount(src_root) == 3
    # 顶层节点本身永远接受，否则“筛不到东西”会变成“整个列表消失”
    assert proxy.rowCount(QModelIndex()) == 1

    proxy.set_entry_filter(None)      # 摘掉：空条件与 None 同义
    assert _visible_names(proxy, proxy_root) == ["a.txt", "b.md", "sub"]


def test_proxy_filters_by_size_using_entry_snapshot(tree, qtbot):
    """size 条件直接用模型已缓存的条目属性：不 stat、不碰网络"""
    src, proxy, src_root, proxy_root = _load_model(tree, qtbot)
    proxy.set_entry_filter(compile_filter("size:>1kb"))
    assert _visible_names(proxy, proxy_root) == ["b.md"]


def test_sorting_does_not_touch_the_filesystem(tree, qtbot, monkeypatch):
    """排序比较也不碰磁盘（与筛选同一条约束）

    `lessThan` 一次排序要跑 O(n log n) 次比较，旧实现每次一个
    `os.path.isdir` —— SMB 大目录上就是“点列头就卡一下”。
    """
    from PyQt6.QtCore import Qt
    import core.pane as pane_mod

    src, proxy, src_root, proxy_root = _load_model(tree, qtbot)
    calls = []
    monkeypatch.setattr(pane_mod.os.path, "isdir",
                        lambda p: calls.append(p) or True)

    proxy.sort(1, Qt.SortOrder.DescendingOrder)      # 按「大小」列倒序
    assert [proxy.data(proxy.index(r, 0, proxy_root))
            for r in range(proxy.rowCount(proxy_root))] == ["sub", "b.md", "a.txt"]
    assert calls == []

    proxy.sort(0, Qt.SortOrder.AscendingOrder)       # 按名称列：目录仍排在前
    assert [proxy.data(proxy.index(r, 0, proxy_root))
            for r in range(proxy.rowCount(proxy_root))] == ["sub", "a.txt", "b.md"]
    assert calls == []


def _order(proxy, proxy_root):
    return [proxy.data(proxy.index(r, 0, proxy_root))
            for r in range(proxy.rowCount(proxy_root))]


def test_sort_keeps_dirs_first_in_both_orders_and_sizes_numerically(tree, qtbot):
    """排序语义对齐资源管理器（旧写法两个都是错的）

    1. “目录在前”不能被降序反转：旧 `lessThan` 直接 `return l_is_dir`，
       降序时文件夹全部跑到最后去了；
    2. 大小列按**字节数**比，不按格式化字符串：旧实现走 `super().lessThan()`
       比的是 "5 B" / "4.0 KB"，字典序把 4 KB 排在 5 B 前面。
    """
    from PyQt6.QtCore import Qt

    src, proxy, src_root, proxy_root = _load_model(tree, qtbot)

    proxy.sort(0, Qt.SortOrder.DescendingOrder)
    assert _order(proxy, proxy_root) == ["sub", "b.md", "a.txt"]
    proxy.sort(0, Qt.SortOrder.AscendingOrder)
    assert _order(proxy, proxy_root) == ["sub", "a.txt", "b.md"]

    proxy.sort(1, Qt.SortOrder.AscendingOrder)       # 大小：5 B < 4 KB
    assert _order(proxy, proxy_root) == ["sub", "a.txt", "b.md"]
    proxy.sort(1, Qt.SortOrder.DescendingOrder)
    assert _order(proxy, proxy_root) == ["sub", "b.md", "a.txt"]


def test_pane_filter_hides_rows_and_reports_counts_in_status(qtbot, tree):
    from core.pane import Pane

    pane = Pane("t_filter", start_path=str(tree))
    qtbot.addWidget(pane)
    tv = pane.tree_view
    proxy = tv.model()

    def _loaded():
        dir_pool().waitForDone(50)          # waitForDone 返回真值，不能写 `a() or cond`
        return proxy.rowCount(tv.rootIndex()) >= 3
    qtbot.waitUntil(_loaded, timeout=5000)

    assert pane.filter_bar.isHidden()               # 默认不占列表空间
    pane.show_filter_bar()
    assert not pane.filter_bar.isHidden()

    pane.filter_bar.set_query("ext:txt")
    qtbot.waitUntil(lambda: _visible_names(proxy, tv.rootIndex()) == ["a.txt"], timeout=5000)
    assert "筛选后 1 / 3" in pane.status_label.text()

    pane.filter_bar.clear_filter()
    qtbot.waitUntil(lambda: len(_visible_names(proxy, tv.rootIndex())) == 3, timeout=5000)
    assert "筛选后" not in pane.status_label.text()
    pane.deleteLater()


def test_pane_filter_survives_navigation(qtbot, tree):
    """导航后条件保留（输入框就在列表上方，✕ 一键可清）—— 与资源管理器一致"""
    from core.pane import Pane

    pane = Pane("t_filter_nav", start_path=str(tree))
    qtbot.addWidget(pane)
    tv = pane.tree_view
    proxy = tv.model()

    def _loaded():
        dir_pool().waitForDone(50)
        return proxy.rowCount(tv.rootIndex()) >= 3
    qtbot.waitUntil(_loaded, timeout=5000)

    pane.filter_bar.set_query("ext:txt")
    qtbot.waitUntil(lambda: _visible_names(proxy, tv.rootIndex()) == ["a.txt"], timeout=5000)

    pane.navigate_to(os.path.join(str(tree), "sub"))
    qtbot.waitUntil(lambda: _visible_names(proxy, tv.rootIndex()) == ["inner.txt"],
                    timeout=5000)

    # Esc 收起筛选栏时连条件一起清掉，不留「列表凭空少了一半」的状态
    pane.hide_filter_bar()
    assert pane.filter_bar.isHidden()
    assert pane.filter_bar.query() == ""
    assert len(_visible_names(proxy, tv.rootIndex())) == 1
    pane.deleteLater()


def test_thumbnail_view_applies_the_same_filter(qtbot, tree):
    """超大图标视图自己扫目录，筛选必须在这条路径上再过一道，否则两视图不一致"""
    from widgets.thumbnail_view import ThumbnailView

    view = ThumbnailView()
    qtbot.addWidget(view)
    view.set_entry_filter(compile_filter("*.txt"))
    view.load_directory(str(tree))
    assert [view.item(i).text() for i in range(view.count())] == ["a.txt"]

    view.set_entry_filter(compile_filter("size:>1kb"))
    view.load_directory(str(tree))
    assert [view.item(i).text() for i in range(view.count())] == ["b.md"]
    view.deleteLater()
