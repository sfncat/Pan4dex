# -*- coding: utf-8 -*-
"""收藏夹分组（清单 8.4）—— 模型层 `config/bookmarks.py` + 侧边栏 `widgets/bookmark_sidebar.py`

模型层不依赖 Qt，结构规则（成环、层数、条数上限、老格式迁移、坏记录）全在那一层，所以
这里一半用例是纯数据结构测；另一半测侧边栏怎么画树、怎么把拖拽结果写回盘。

旧版是「一个平铺 list + `list_widget.currentRow()` 当下标」，两边一旦不同步就会改错/
删错项；本文件里凡是按 id 说的改动，都是钉住这一点不回退。
"""
import json
import os

import pytest

from config import bookmarks as bm
from config.bookmarks import BookmarkStore, BookmarkError, ROOT_ID, FILE_NAME, MAX_NAME_LEN
from PyQt6.QtCore import QEvent, QModelIndex, QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent, QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QInputDialog, QMenu, QMessageBox,
)


# ---------------------------------------------------------------- 夹具


@pytest.fixture
def cfg(tmp_path):
    """一个干净的配置目录（`store` 与侧边栏都用它，好直接核对盘上的 JSON）"""
    return str(tmp_path / "cfg")


@pytest.fixture
def store(cfg):
    st = BookmarkStore(config_dir=cfg)
    st.root["children"] = []        # 别把「首次启动那四条默认」混进结构测
    return st


@pytest.fixture
def sb(qtbot, store, cfg):
    from widgets.bookmark_sidebar import BookmarkSidebar

    sidebar = BookmarkSidebar(store=store)
    qtbot.addWidget(sidebar)
    return sidebar


def write_raw(cfg, payload):
    os.makedirs(cfg, exist_ok=True)
    with open(os.path.join(cfg, FILE_NAME), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def read_raw(cfg):
    with open(os.path.join(cfg, FILE_NAME), "r", encoding="utf-8") as f:
        return json.load(f)


def tree_of(store):
    """整棵树 → 可比较的嵌套 tuple（比逐节点 dict 好读）"""
    def conv(node):
        if node["type"] == "link":
            return ("link", node["name"], node["path"])
        return ("group", node["name"], [conv(c) for c in node["children"]])

    return [conv(c) for c in store.root["children"]]


def drop_event(mime, action=Qt.DropAction.CopyAction, at=(2, 2)):
    return QDropEvent(QPointF(*at), action, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


# ================================================================ 读盘与默认值


def test_first_run_seeds_defaults_and_persists_them(cfg):
    st = BookmarkStore(config_dir=cfg)

    assert [n["name"] for n in st.root["children"]] == ["主目录", "桌面", "下载", "文档"]
    assert read_raw(cfg)["version"] == bm.FORMAT_VERSION


def test_deleting_everything_does_not_come_back(cfg, store):
    """旧版是「配置里空了就回灌默认四条」，等于用户删不掉系统给的那几条"""
    node_id = store.add_link("只剩这条", r"C:\only")
    store.save()
    store.remove(node_id)
    store.save()

    assert BookmarkStore(config_dir=cfg).root["children"] == []


def test_corrupt_file_is_an_empty_table_not_a_crash(cfg):
    write_raw(cfg, "这文件被截断了 {")

    assert BookmarkStore(config_dir=cfg).root["children"] == []


@pytest.mark.parametrize("payload", [
    "一个字符串",
    {"version": 999},
    {"children": "不是列表"},
    {"groups": "不是列表"},
])
def test_unknown_shapes_degrade_to_empty(cfg, payload):
    write_raw(cfg, payload)

    assert BookmarkStore(config_dir=cfg).root["children"] == []


# ================================================================ 老格式迁移


def test_v1_flat_list_migrates_on_read_only(cfg, tmp_path):
    write_raw(cfg, [{"name": "工作", "path": r"C:\work"}, {"name": "", "path": "D:/data/"}])
    path = os.path.join(cfg, FILE_NAME)
    before = open(path, encoding="utf-8").read()

    st = BookmarkStore(config_dir=cfg)

    assert [(lk["name"], lk["path"]) for lk in st.links()] == [
        ("工作", r"C:\work"), ("data", "D:/data/")]
    assert st.migrated is True
    # 只读就不动用户的文件：转换有 bug 时还有原样可退
    assert open(path, encoding="utf-8").read() == before


def test_v1_becomes_v2_only_after_an_edit(cfg):
    write_raw(cfg, [{"name": "工作", "path": r"C:\work"}])
    st = BookmarkStore(config_dir=cfg)

    st.rename(st.root["children"][0]["id"], "新名字")
    ok, err = st.save()

    assert ok and err == ""
    assert read_raw(cfg)["version"] == bm.FORMAT_VERSION
    assert st.migrated is False


def test_entries_without_a_name_fall_back_instead_of_vanishing(cfg):
    # 路径按本机分隔符造：兜底名走的是 `os.path.basename`，在 POSIX 上
    # `C:\a\b` 是一个**合法的文件名**（反斜杠不是分隔符），拿 Windows 路径来断言
    # 会得到整串 —— Linux 真机上实测就是这条差异（不是产品错，是用例假设错）
    tail = "b"
    path = rf"C:\a\{tail}" if os.name == "nt" else f"/srv/data/{tail}"
    write_raw(cfg, [{"path": path}, {"type": "group", "children": []}])

    st = BookmarkStore(config_dir=cfg)

    assert [(n["type"], n["name"]) for n in st.root["children"]] == [
        ("link", tail), ("group", "未命名分组")]


@pytest.mark.skipif(os.name == "nt", reason="POSIX 上反斜杠是普通文件名字符")
def test_posix_does_not_split_a_name_on_backslashes(cfg):
    r"""记录一条刻意的取舍：POSIX 上不把 `\` 当分隔符

    就算收藏夹里躺着 Windows 形状的路径（导出后跨系统导入会出现），也按本机规则
    取名字，不做「顺手兼容反斜杠」—— 那会把 Linux 上真叫 `a\b` 的目录切错。
    """
    write_raw(cfg, [{"path": r"C:\a\b"}])

    assert BookmarkStore(config_dir=cfg).root["children"][0]["name"] == r"C:\a\b"


def test_one_bad_record_does_not_take_the_rest(cfg):
    write_raw(cfg, [None, "字符串", {"name": "没有路径"},
                    {"name": "好这条", "path": r"C:\good"}])

    st = BookmarkStore(config_dir=cfg)

    assert [(lk["name"], lk["path"]) for lk in st.links()] == [("好这条", r"C:\good")]


def test_overlong_names_are_truncated_on_read(cfg):
    write_raw(cfg, [{"name": "长" * 300, "path": r"C:\x"}])

    assert BookmarkStore(config_dir=cfg).root["children"][0]["name"] == "长" * MAX_NAME_LEN


def test_ids_coming_from_the_file_are_never_trusted(cfg):
    """文件里的 id 可能重复（手改 / 别的机器并过来）→ 一律重新分配，否则 find 会认错节点"""
    write_raw(cfg, {"version": 2, "children": [
        {"id": 7, "type": "link", "name": "甲", "path": r"C:\a"},
        {"id": 7, "type": "link", "name": "乙", "path": r"C:\b"},
    ]})

    st = BookmarkStore(config_dir=cfg)

    assert st.find(7) is None
    ids = [lk["id"] for lk in st.links()]
    assert len(set(ids)) == 2
    assert sorted(lk["path"] for lk in st.links()) == sorted([r"C:\a", r"C:\b"])


def test_reload_assigns_ids_deterministically(cfg, store):
    group = store.add_group("组")
    store.add_link("甲", r"C:\a", group)
    store.save()

    reloaded = BookmarkStore(config_dir=cfg)

    assert reloaded.root["children"][0]["id"] == 1        # 每次载入都从 1 重编
    assert reloaded.links()[0]["id"] == 2
    new_id = reloaded.add_link("乙", r"C:\b")
    assert new_id == 3 and reloaded.count() == 3


# ================================================================ 结构规则


def test_add_link_returns_id_and_honours_index(store):
    a = store.add_link("甲", r"C:\a")
    b = store.add_link("乙", r"C:\b")
    c = store.add_link("丙", r"C:\c", index=0)

    assert [n["name"] for n in store.root["children"]] == ["丙", "甲", "乙"]
    assert store.find(c)["path"] == r"C:\c"
    assert a < b < c                                  # id 单调递增，不会撞号


def test_empty_name_or_path_is_refused(store):
    with pytest.raises(BookmarkError):
        store.add_link("   ", r"C:\a")
    with pytest.raises(BookmarkError):
        store.add_link("甲", "  ")
    with pytest.raises(BookmarkError):
        store.add_group("")
    assert store.count() == 0


def test_a_link_cannot_hold_children(store):
    link = store.add_link("甲", r"C:\a")

    with pytest.raises(BookmarkError) as e:
        store.add_group("组", link)
    assert "是一条收藏" in str(e.value)
    with pytest.raises(BookmarkError):
        store.add_link("乙", r"C:\b", link)
    assert tree_of(store) == [("link", "甲", r"C:\a")]


def test_only_links_have_a_path(store):
    group = store.add_group("组")

    with pytest.raises(BookmarkError):
        store.set_path(group, r"C:\x")


def test_unknown_id_is_reported_instead_of_silently_ignored(store):
    with pytest.raises(BookmarkError) as e:
        store.rename(4242, "改名")
    assert "已不存在" in str(e.value)
    with pytest.raises(BookmarkError):
        store.move(4242, ROOT_ID)


def test_nesting_is_capped(store, monkeypatch):
    monkeypatch.setattr(bm, "MAX_DEPTH", 3)
    first = store.add_group("1层")
    second = store.add_group("2层", first)
    third = store.add_group("3层", second)

    with pytest.raises(BookmarkError) as e:
        store.add_group("4层", third)
    assert "3 层" in str(e.value)
    assert store.count() == 3


def test_reading_a_file_deeper_than_the_cap_keeps_the_top_levels(cfg, monkeypatch):
    monkeypatch.setattr(bm, "MAX_DEPTH", 3)
    write_raw(cfg, {"version": 2, "children": [{
        "type": "group", "name": "1层",
        "children": [{"type": "group", "name": "2层", "children": [
            {"type": "group", "name": "3层", "children": [
                {"type": "link", "name": "第4层的就别要了", "path": r"C:\deep"}]}]}]}]})

    st = BookmarkStore(config_dir=cfg)

    assert [g["name"] for g in st.groups()] == ["1层", "2层", "3层"]
    assert st.links() == []


def test_moving_a_group_into_itself_or_its_own_child_is_refused(store):
    top = store.add_group("外层")
    inner = store.add_group("内层", top)

    assert store.can_place(top, top) == "不能把分组放到它自己的里面（会形成环）"
    assert "环" in store.can_place(top, inner)
    with pytest.raises(BookmarkError) as e:
        store.move(top, inner)
    assert "环" in str(e.value)
    assert tree_of(store) == [("group", "外层", [("group", "内层", [])])]


def test_move_reparents_and_the_index_is_read_after_removal(store):
    a = store.add_link("甲", r"C:\a")
    store.add_link("乙", r"C:\b")
    c = store.add_link("丙", r"C:\c")

    store.move(c, ROOT_ID, 0)
    assert [n["name"] for n in store.root["children"]] == ["丙", "甲", "乙"]
    store.move(a, ROOT_ID, 99)                      # 越界夹到末尾，不抛
    assert [n["name"] for n in store.root["children"]] == ["丙", "乙", "甲"]
    assert store.parent_of(a)["id"] == ROOT_ID


def test_can_place_and_move_share_one_rule(store, monkeypatch):
    """`can_place` 是拖拽时问的（只能回理由，不能抛），`move` 是动作（同一个理由要抛）"""
    group = store.add_group("组")
    link = store.add_link("条", r"C:\a")

    assert store.can_place(link, group) == ""
    monkeypatch.setattr(bm, "MAX_DEPTH", 1)
    assert "1 层" in store.can_place(link, group)
    with pytest.raises(BookmarkError) as e:
        store.move(link, group)
    assert "1 层" in str(e.value)


def test_moving_a_whole_subtree_counts_its_height(store, monkeypatch):
    monkeypatch.setattr(bm, "MAX_DEPTH", 3)
    first = store.add_group("1层")
    second = store.add_group("2层", first)
    store.add_group("3层", second)
    leaf = store.add_link("根下的一条", r"C:\a")

    assert store.can_place(first, ROOT_ID) == ""            # 高 3 的子树刚好放得下
    deepest = store.groups()[-1]
    assert deepest["name"] == "3层"
    assert "3 层" in store.can_place(leaf, deepest["id"])   # 3 + 1 就超了


def test_item_cap_blocks_new_entries_but_not_edits(store, monkeypatch):
    monkeypatch.setattr(bm, "MAX_ITEMS", 3)
    first = store.add_link("甲", r"C:\a")
    store.add_group("乙")
    store.add_link("丙", r"C:\c")

    with pytest.raises(BookmarkError) as e:
        store.add_link("丁", r"C:\d")
    assert "3 条" in str(e.value)
    store.rename(first, "改名不算新增")                    # 上限只管进人，不该拦编辑
    assert store.find(first)["name"] == "改名不算新增"


def test_removing_a_group_reports_what_it_took_along(store):
    group = store.add_group("组")
    store.add_link("甲", r"C:\a", group)
    inner = store.add_group("内层", group)
    store.add_link("乙", r"C:\b", inner)

    taken = store.remove(group)

    assert taken == 3                                 # 内层分组 + 两条链接
    assert store.count() == 0 and store.links() == [] and store.groups() == []


def test_the_root_cannot_be_deleted(store):
    with pytest.raises(BookmarkError):
        store.remove(ROOT_ID)


def test_expanded_flag_round_trips_through_the_file(cfg, store):
    group = store.add_group("组")
    store.add_link("甲", r"C:\a", group)
    store.set_expanded(group, False)
    store.save()

    assert BookmarkStore(config_dir=cfg).root["children"][0]["expanded"] is False


def test_remembering_expansion_for_an_unknown_id_is_harmless(store):
    store.set_expanded(4242, False)                  # 不抛：只是没有东西可记
    store.set_expanded(ROOT_ID, False)               # 根也不跟着翻

    assert store.find(ROOT_ID)["expanded"] is True


def test_save_failure_returns_text_instead_of_raising(store, tmp_path):
    store.add_link("甲", r"C:\a")
    store.config_file = str(tmp_path)                # 指向一个目录：写它必然失败

    ok, err = store.save()

    assert ok is False and err
    assert store.root["children"][0]["name"] == "甲"  # 内存里那条还在


# ================================================================ 导入导出


def test_export_then_import_round_trips_the_tree(store, tmp_path, cfg):
    group = store.add_group("组")
    store.add_link("甲", r"C:\a", group)
    store.set_expanded(group, False)
    store.save()
    path = str(tmp_path / "out.json")

    ok, err = store.export_file(path)

    assert ok and err == ""
    other = BookmarkStore(config_dir=str(tmp_path / "other"))
    other.root["children"] = []
    assert other.import_file(path) == (2, 0, "")
    assert tree_of(other) == [("group", "组", [("link", "甲", r"C:\a")])]
    assert other.root["children"][0]["expanded"] is False


def test_export_failure_returns_text(store, tmp_path):
    ok, err = store.export_file(str(tmp_path))       # 同一个目录：写不进去

    assert ok is False and err


def test_importing_twice_skips_paths_it_already_has(store, tmp_path):
    store.add_link("甲", r"C:\a")
    group = store.add_group("组")
    store.add_link("乙", r"C:\b", group)
    path = str(tmp_path / "out.json")
    store.export_file(path)

    added, skipped, err = store.import_file(path)

    # 去重按路径、也深入分组里面：两条链接都算重复，只多了一个空分组
    assert (added, skipped, err) == (1, 2, "")
    assert sorted(lk["name"] for lk in store.links()) == ["乙", "甲"]
    assert [len(g["children"]) for g in store.groups()] == [1, 0]


def test_a_failed_import_leaves_the_tree_alone(store, tmp_path):
    store.add_link("别弄丢我", r"C:\keep")
    bad = tmp_path / "bad.json"
    bad.write_text("截断了 {", encoding="utf-8")

    added, skipped, err = store.import_file(str(bad))

    assert (added, skipped) == (0, 0) and "读取失败" in err
    assert [lk["name"] for lk in store.links()] == ["别弄丢我"]


def test_importing_an_empty_file_says_so(store, tmp_path):
    path = tmp_path / "none.json"
    path.write_text("[]", encoding="utf-8")

    assert "没有可用" in store.import_file(str(path))[2]


def test_import_up_to_the_cap_is_allowed(store, tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "MAX_ITEMS", 4)
    store.add_link("甲", r"C:\a")
    path = _three_link_export(store, tmp_path)

    assert store.import_file(path) == (3, 0, "")        # 1 + 3 刚好等于上限
    assert store.count() == 4


def test_import_honours_the_item_cap(store, tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "MAX_ITEMS", 3)
    store.add_link("甲", r"C:\a")
    path = _three_link_export(store, tmp_path)

    added, skipped, err = store.import_file(path)

    assert (added, skipped) == (0, 0) and "上限" in err
    assert [lk["name"] for lk in store.links()] == ["甲"]        # 一条都不进


def _three_link_export(store, tmp_path):
    src = BookmarkStore(config_dir=str(tmp_path / "src"))
    src.root["children"] = []
    for name in ("乙", "丙", "丁"):
        src.add_link(name, rf"C:\{name}")
    path = str(tmp_path / "out.json")
    src.export_file(path)
    return path


def test_import_into_a_deep_group_checks_depth(store, tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "MAX_DEPTH", 3)
    top = store.add_group("外层")
    mid = store.add_group("中层", top)
    src = BookmarkStore(config_dir=str(tmp_path / "src"))
    src.root["children"] = []
    group = src.add_group("带一条的子组")
    src.add_link("叶子", r"C:\leaf", group)
    path = str(tmp_path / "out.json")
    src.export_file(path)

    added, skipped, err = store.import_file(path, mid)

    assert (added, skipped) == (0, 0) and "3 层" in err
    assert store.count() == 2


def test_import_rejects_a_target_that_is_a_link(store, tmp_path):
    link = store.add_link("条", r"C:\a")
    src = BookmarkStore(config_dir=str(tmp_path / "src"))
    src.root["children"] = []
    src.add_link("别的东西", r"C:\b")
    path = str(tmp_path / "out.json")
    src.export_file(path)

    with pytest.raises(BookmarkError) as e:
        store.import_file(path, link)
    assert "是一条收藏" in str(e.value)


# ================================================================ 侧边栏画树


def item_at(tree, *path):
    item = tree.topLevelItem(path[0])
    for idx in path[1:]:
        item = item.child(idx)
    return item


def top_names(tree):
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def test_tree_mirrors_the_store_tree(sb, store):
    group = store.add_group("工作")
    store.add_link("代码", r"C:\code", group)
    store.add_link("文档", r"C:\docs", group)
    store.add_link("顶层", r"C:\top")
    sb.refresh_tree()
    tree = sb.tree

    assert top_names(tree) == ["工作", "顶层"]
    assert [item_at(tree, 0, 0).text(0), item_at(tree, 0, 1).text(0)] == ["代码", "文档"]
    assert item_at(tree, 0, 0).data(0, Qt.ItemDataRole.UserRole) != \
        item_at(tree, 0, 1).data(0, Qt.ItemDataRole.UserRole)
    assert item_at(tree, 0).toolTip(0) == "分组 · 2 条收藏"
    assert item_at(tree, 1).toolTip(0) == r"C:\top"


def test_an_empty_group_says_so(sb, store):
    store.add_group("空的")
    sb.refresh_tree()

    assert item_at(sb.tree, 0).toolTip(0) == "分组（空）"


def test_rebuild_follows_the_stored_expansion(sb, store):
    group = store.add_group("工作")
    store.add_link("代码", r"C:\code", group)
    store.set_expanded(group, False)
    sb.tree.expandAll()

    sb.refresh_tree()

    assert item_at(sb.tree, 0).isExpanded() is False


def test_rebuild_selects_what_it_was_asked_to(sb, store):
    store.add_link("甲", r"C:\a")
    node_id = store.add_link("乙", r"C:\b")

    sb.refresh_tree(select_id=node_id)

    assert sb.tree.currentItem() is item_at(sb.tree, 1)


def test_clicking_a_reachable_bookmark_navigates(sb, store, tmp_path):
    real = tmp_path / "docs"
    real.mkdir()
    node_id = store.add_link("文档", str(real))
    sb.refresh_tree(select_id=node_id)
    got = []
    sb.bookmark_clicked.connect(got.append)

    sb.open_selected()

    assert got == [str(real)]


def test_an_unreachable_bookmark_says_so_instead_of_staying_silent(
        sb, store, monkeypatch):
    """旧版：`if os.path.isdir(path)` 才发信号 → 网络盘断开时双击**毫无反应**"""
    node_id = store.add_link("断开的盘", r"Z:\gone")
    sb.refresh_tree(select_id=node_id)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda parent, title, text, *a: warnings.append(text)))
    got = []
    sb.bookmark_clicked.connect(got.append)

    sb.open_selected()

    assert got == []
    assert len(warnings) == 1 and "不可达" in warnings[0] and r"Z:\gone" in warnings[0]


def test_double_click_on_a_group_only_toggles_it(sb, store):
    group = store.add_group("工作")
    store.add_link("代码", r"C:\code", group)
    sb.refresh_tree()
    item = item_at(sb.tree, 0)
    item.setExpanded(False)
    got = []
    sb.bookmark_clicked.connect(got.append)

    sb.on_item_activated(item)

    assert item.isExpanded() is True and got == []


def test_del_key_removes_the_entry_but_not_the_directory(
        sb, store, cfg, tmp_path, monkeypatch):
    real = tmp_path / "keepme"
    real.mkdir()
    node_id = store.add_link("留着", str(real))
    store.save()
    sb.refresh_tree(select_id=node_id)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    sb.tree.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                                    Qt.KeyboardModifier.NoModifier))

    assert store.links() == []
    assert real.exists()                               # 磁盘上的目录一动不动
    assert top_names(sb.tree) == []
    assert read_raw(cfg)["children"] == []


def test_removing_a_group_says_how_many_it_takes(sb, store, monkeypatch):
    asked = []
    group = store.add_group("工作")
    store.add_link("代码", r"C:\code", group)
    store.add_link("文档", r"C:\docs", group)
    sb.refresh_tree(select_id=group)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda parent, title, text, *a, **k: asked.append(text)
        or QMessageBox.StandardButton.No))

    sb.remove_selected()

    assert "还有 2 条" in asked[0]
    assert "磁盘上的目录不受影响" in asked[0]
    assert store.count() == 3                          # 回答 No → 什么都没删


def test_add_bookmark_with_path_lands_in_the_selected_group(sb, store, cfg, tmp_path,
                                                            monkeypatch):
    group = store.add_group("工作")
    store.save()
    sb.refresh_tree(select_id=group)
    asked = []
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(
        lambda parent, title, label, *a, **k: asked.append((title, k.get("text")))
        or ("我的代码", True)))

    sb.add_bookmark_with_path(str(tmp_path))

    assert asked[0][0] == "添加到收藏夹"
    assert tree_of(store) == [("group", "工作", [("link", "我的代码", str(tmp_path))])]
    assert read_raw(cfg)["children"][0]["children"][0]["name"] == "我的代码"


def test_a_selected_link_receives_new_items_in_its_own_group(sb, store, monkeypatch):
    group = store.add_group("工作")
    link = store.add_link("代码", r"C:\code", group)
    sb.refresh_tree(select_id=link)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("新来的", True)))

    sb.add_bookmark_with_path(r"C:\other")

    assert [c["name"] for c in store.find(group)["children"]] == ["代码", "新来的"]


def test_cancelling_a_prompt_changes_nothing(sb, store, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("随便", False)))

    sb.add_bookmark_with_path(r"C:\a")
    sb.new_group()
    sb.rename_selected()

    assert store.count() == 0


def test_the_plus_button_starts_at_the_active_panes_directory(sb, store, monkeypatch, tmp_path):
    picked = tmp_path / "picked"
    picked.mkdir()
    seen = {}
    sb.current_dir_provider = lambda: str(tmp_path)
    # 别用 `seen.setdefault(...) or 返回值`：setdefault 命中已有值时返回那个**真值**，
    # 弹框就再也不会返回 picked
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(
        lambda parent, title, start, *a, **k: seen.__setitem__("start", start) or str(picked)))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("选中的", True)))

    sb.add_bookmark()

    assert seen["start"] == str(tmp_path)
    assert [lk["path"] for lk in store.links()] == [str(picked)]


def test_a_broken_current_dir_provider_does_not_break_the_dialog(sb, monkeypatch):
    def boom():
        raise RuntimeError("那个窗格已经被销毁了")

    sb.current_dir_provider = boom
    seen = {}
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(
        lambda parent, title, start, *a, **k: seen.__setitem__("start", start) or ""))

    sb.add_bookmark()

    assert seen["start"] == ""


def test_new_group_button_creates_a_group(sb, store, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("生活", True)))

    sb.new_group()

    assert tree_of(store) == [("group", "生活", [])]


# ================================================================ 外部拖入收藏


def test_external_dirs_only_accepts_existing_local_directories(tmp_path):
    from widgets.bookmark_sidebar import external_dirs

    folder = tmp_path / "folder"
    folder.mkdir()
    a_file = tmp_path / "file.txt"
    a_file.write_text("x", encoding="utf-8")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder)), QUrl.fromLocalFile(str(a_file)),
                  QUrl.fromLocalFile(str(tmp_path / "nope")),
                  QUrl("http://example.com/x")])

    assert external_dirs(mime) == [str(folder)]
    assert external_dirs(QMimeData()) == []
    assert external_dirs(None) == []


def test_add_paths_as_bookmarks_skips_paths_it_already_has(sb, store, tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    store.add_link("已有的", str(first))

    added = sb.add_paths_as_bookmarks([str(first), str(second)], ROOT_ID)

    assert added == 1
    assert [(lk["name"], lk["path"]) for lk in store.links()] == [
        ("已有的", str(first)), ("b", os.path.normpath(str(second)))]


def test_add_paths_reports_a_refusal_once(sb, store, tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "MAX_ITEMS", 2)
    store.add_link("甲", r"C:\a")
    dirs = []
    for name in ("x", "y", "z"):
        folder = tmp_path / name
        folder.mkdir()
        dirs.append(str(folder))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda parent, title, text, *a: warnings.append(text)))

    added = sb.add_paths_as_bookmarks(dirs, ROOT_ID)

    assert added == 1                                  # 第一条进去，第二条撞上限
    assert len(warnings) == 1 and "2 条" in warnings[0]
    assert store.count() == 2


def test_can_drop_mime_data_judges_internal_and_external_separately(sb, store, cfg):
    store.add_link("甲", r"C:\a")
    sb.refresh_tree()
    tree = sb.tree
    index = tree.indexFromItem(tree.topLevelItem(0))
    above = QAbstractItemView.DropIndicatorPosition.AboveItem

    urls = QMimeData()
    urls.setUrls([QUrl.fromLocalFile(cfg)])
    assert tree.canDropMimeData(urls, Qt.DropAction.CopyAction, above, index, QModelIndex())
    assert not tree.canDropMimeData(QMimeData(), Qt.DropAction.CopyAction,
                                    above, index, QModelIndex())
    tree._dragging_internally = True
    tree.setCurrentItem(tree.topLevelItem(0))
    internal = tree.mimeData(tree.selectedItems())
    assert tree.canDropMimeData(internal, Qt.DropAction.MoveAction,
                                above, index, QModelIndex())
    assert not tree.canDropMimeData(internal, Qt.DropAction.CopyAction,
                                    above, index, QModelIndex())     # 内部只认移动
    tree._dragging_internally = False


def test_dropping_a_folder_from_the_file_list_bookmarks_it(sb, store, cfg, tmp_path):
    store.add_group("工作")
    store.save()
    dropped = tmp_path / "拖进来的目录"
    dropped.mkdir()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(dropped))])

    sb.tree.dropEvent(drop_event(mime))

    assert [lk["name"] for lk in store.links()] == ["拖进来的目录"]
    on_disk = read_raw(cfg)["children"]
    paths = json.dumps(on_disk, ensure_ascii=False)
    assert "拖进来的目录" in paths and "工作" in paths


def test_dropping_a_file_is_refused_without_touching_the_tree(sb, store, tmp_path):
    store.add_link("甲", r"C:\a")
    sb.refresh_tree()
    before = tree_of(store)
    a_file = tmp_path / "x.txt"
    a_file.write_text("x", encoding="utf-8")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(a_file))])

    sb.tree.dropEvent(drop_event(mime))                # 既不收藏，也不当内部移动

    assert tree_of(store) == before


def test_group_under_the_cursor_is_the_target(sb, store):
    group = store.add_group("工作")
    link = store.add_link("代码", r"C:\code", group)
    other = store.add_link("顶层的", r"C:\other")
    sb.refresh_tree()
    tree = sb.tree

    assert tree._group_under(tree.visualItemRect(item_at(tree, 0)).center()) == group
    assert tree._group_under(tree.visualItemRect(item_at(tree, 0, 0)).center()) == group
    assert tree._group_under(tree.visualItemRect(item_at(tree, 1)).center()) == ROOT_ID
    assert tree._group_under(QPoint(0, 100000)) == ROOT_ID


# ================================================================ 内部拖拽落地


def test_target_group_resolves_links_and_blank_viewport(sb, store):
    group = store.add_group("工作")
    link = store.add_link("代码", r"C:\code", group)
    sb.refresh_tree()
    tree = sb.tree
    OnItem = QAbstractItemView.DropIndicatorPosition.OnItem
    OnViewport = QAbstractItemView.DropIndicatorPosition.OnViewport

    # 落在链接上 = 插在它旁边 → 目标是它所在的分组（当成“放进一条收藏”就永远排不了序）
    assert tree._target_group(tree.indexFromItem(item_at(tree, 0, 0)), QModelIndex(),
                              OnItem) == group
    assert tree._target_group(tree.indexFromItem(item_at(tree, 0)), QModelIndex(),
                              OnItem) == group
    assert tree._target_group(QModelIndex(), QModelIndex(), OnViewport) == ROOT_ID


def test_can_place_drag_refuses_the_whole_batch(sb, store):
    top = store.add_group("外层")
    inner = store.add_group("内层", top)
    other = store.add_group("别的")
    link = store.add_link("条", r"C:\a")

    assert sb.can_place_drag([link], inner) is True
    assert sb.can_place_drag([top], inner) is False        # 成环
    assert sb.can_place_drag([link, top], other) is True
    assert sb.can_place_drag([link, top], inner) is False  # 一条不许就整批不许
    assert sb.can_place_drag([], other) is True


def test_a_manual_tree_reorder_is_written_back_and_persisted(sb, store, cfg):
    store.add_link("甲", r"C:\a")
    store.add_link("乙", r"C:\b")
    store.add_group("组")
    store.save()
    sb.refresh_tree()
    tree = sb.tree

    moved = tree.takeTopLevelItem(0)                 # Qt 内部移动留下的就是这个形状
    tree.insertTopLevelItem(2, moved)
    sb._sync_from_tree()

    assert [n["name"] for n in store.root["children"]] == ["乙", "组", "甲"]
    assert [n["name"] for n in BookmarkStore(config_dir=cfg).root["children"]] == \
        ["乙", "组", "甲"]
    assert top_names(tree) == ["乙", "组", "甲"]         # 重画后仍是那个顺序


def test_a_child_moved_between_groups_is_persisted(sb, store, cfg):
    src = store.add_group("源")
    dst = store.add_group("目标")
    link = store.add_link("要挪走", r"C:\a", src)
    store.save()
    sb.refresh_tree()
    tree = sb.tree

    src_item = item_at(tree, 0)
    moved = src_item.child(0)
    # Qt 6 的 QTreeWidgetItem 没有 `setParent`：改挂只能 removeChild + addChild
    src_item.removeChild(moved)
    item_at(tree, 1).addChild(moved)
    sb._sync_from_tree()

    assert [c["name"] for c in store.find(dst)["children"]] == ["要挪走"]
    assert store.parent_of(link)["id"] == dst
    assert tree_of(BookmarkStore(config_dir=cfg)) == [
        ("group", "源", []), ("group", "目标", [("link", "要挪走", r"C:\a")])]


def test_rows_moved_signal_is_wired_to_the_sync(sb, store, cfg):
    """Qt 内部移动到底发哪个信号不该由我们赌 —— 这条钉住 `rowsMoved` 也接住了"""
    store.add_link("甲", r"C:\a")
    store.add_link("乙", r"C:\b")
    store.save()
    sb.refresh_tree()
    tree = sb.tree
    moved = tree.takeTopLevelItem(0)
    tree.insertTopLevelItem(1, moved)

    tree.model().rowsMoved.emit(QModelIndex(), 0, 0, QModelIndex(), 1)

    assert [n["name"] for n in BookmarkStore(config_dir=cfg).root["children"]] == \
        ["乙", "甲"]


def test_sync_is_silent_when_nothing_actually_moved(sb, store, monkeypatch):
    store.add_link("甲", r"C:\a")
    store.add_group("乙")
    store.save()
    sb.refresh_tree()
    writes = []
    monkeypatch.setattr(sb.store, "save", lambda: writes.append(1) or (True, ""))

    sb._sync_from_tree()
    sb._sync_from_tree()

    assert writes == []


def test_sync_on_an_empty_sidebar_writes_nothing(sb, store, monkeypatch):
    """树与模型都空：两边形状要能对得上账，不然一次没改过的同步也会重画+写盘

    盯住 `_read_order` 预置的 `{ROOT_ID: []}`：少这一层时它与 `_model_order` 永远
    不相等，空侧边栏上随便一次同步都会白重画一次、白写一次盘。
    """
    sb.refresh_tree()
    calls = []
    monkeypatch.setattr(sb.store, "save", lambda: calls.append(1) or (True, ""))

    sb._sync_from_tree()

    assert calls == []


def test_sync_refuses_to_write_a_tree_it_cannot_account_for(sb, store, cfg, monkeypatch):
    """树与模型对不上（万一 Qt 把移动做成了复制）：按模型重画，不写残缺顺序"""
    store.add_link("甲", r"C:\a")
    store.add_group("乙")
    store.save()
    sb.refresh_tree()
    writes = []
    monkeypatch.setattr(sb.store, "save", lambda: writes.append(1) or (True, ""))
    taken = sb.tree.takeTopLevelItem(0)              # 树上少了一项，账差 1

    sb._sync_from_tree()

    assert writes == []
    assert top_names(sb.tree) == ["甲", "乙"]          # 被按模型重画回来
    assert taken is not None                          # 只是局部变量，别让 GC 提前收走
    assert [n["name"] for n in BookmarkStore(config_dir=cfg).root["children"]] == \
        ["甲", "乙"]


def test_expand_and_collapse_all_are_persisted(sb, store, cfg):
    group = store.add_group("工作")
    store.add_link("代码", r"C:\code", group)
    store.save()
    sb.refresh_tree()

    sb.collapse_all()

    assert item_at(sb.tree, 0).isExpanded() is False
    # 按盘上的形状看，不按 id 查：id 每次载入都重编，旧 id 在新 store 里认不出来
    assert read_raw(cfg)["children"][0]["expanded"] is False

    sb.expand_all()

    assert read_raw(cfg)["children"][0]["expanded"] is True


def test_toggling_one_group_persists_without_touching_the_others(sb, store, cfg, monkeypatch):
    first = store.add_group("甲")
    store.add_link("里面的", r"C:\a", first)
    second = store.add_group("乙")
    store.add_link("里面的乙", r"C:\b", second)
    store.save()
    sb.refresh_tree()
    calls = []
    real_save = sb.store.save
    # 只计数不能把 save 替掉：那样盘上永远不会更新，后面的往返断言就只是在测自己
    monkeypatch.setattr(sb.store, "save",
                        lambda: calls.append(1) or real_save())

    item_at(sb.tree, 0).setExpanded(False)

    assert len(calls) == 1                            # 一次用户动作 = 一次写盘
    reloaded = BookmarkStore(config_dir=cfg)
    assert [g["expanded"] for g in reloaded.groups()] == [False, True]


# ================================================================ 右键菜单与挪组


def test_rename_updates_both_the_tree_and_the_disk(sb, store, cfg, monkeypatch):
    node_id = store.add_link("旧名", r"C:\a")
    store.save()
    sb.refresh_tree(select_id=node_id)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("新名", True)))

    sb.rename_selected()

    assert top_names(sb.tree) == ["新名"]
    assert read_raw(cfg)["children"][0]["name"] == "新名"


def test_edit_bookmark_follows_an_auto_derived_name(sb, store, tmp_path, monkeypatch):
    old = tmp_path / "老目录"
    old.mkdir()
    new = tmp_path / "新目录"
    new.mkdir()
    node_id = store.add_link("老目录", str(old))
    store.save()
    sb.refresh_tree(select_id=node_id)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(new)))

    sb.edit_bookmark()

    link = store.links()[0]
    assert link["path"] == str(new) and link["name"] == "新目录"


def test_edit_bookmark_keeps_a_name_the_user_wrote(sb, store, tmp_path, monkeypatch):
    old = tmp_path / "老目录"
    old.mkdir()
    new = tmp_path / "新目录"
    new.mkdir()
    node_id = store.add_link("我起的名", str(old))
    store.save()
    sb.refresh_tree(select_id=node_id)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(new)))

    sb.edit_bookmark()

    assert store.links()[0]["name"] == "我起的名"


def capture_menu(monkeypatch):
    seen = {}

    def fake_exec(self, *a, **k):
        seen["items"] = [(act.text(), act.isEnabled())
                         for act in self.actions() if not act.isSeparator()]
        return 0

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    return seen


NO_TARGET_HINT = "（没有可以放入的分组）"


def test_move_to_group_lists_only_legal_targets(sb, store, monkeypatch):
    top = store.add_group("外层")
    store.add_group("内层", top)
    store.add_group("别的")
    store.save()
    sb.refresh_tree(select_id=top)
    seen = capture_menu(monkeypatch)

    sb.move_to_group()

    assert [text for text, _on in seen["items"]] == ["收藏夹根目录", "别的"]
    assert store.parent_of(top)["id"] == ROOT_ID          # 没点菜单项 → 什么都没挪


def test_move_to_group_shows_a_real_disabled_item_when_nothing_fits(
        sb, store, monkeypatch):
    """没有合法目标时那句提示必须看得见 —— 写成分隔线上等于没有"""
    monkeypatch.setattr(bm, "MAX_DEPTH", 1)
    link = store.add_link("条", r"C:\a")
    store.add_group("唯一的一个分组")          # 已在第 1 层，再往里放就超层数
    sb.refresh_tree(select_id=link)
    seen = capture_menu(monkeypatch)

    sb.move_to_group()

    assert seen["items"] == [("收藏夹根目录", True), (NO_TARGET_HINT, False)]


def test_move_to_group_offers_exactly_what_the_model_allows(sb, store, monkeypatch):
    """菜单列的目标与 `can_place` 逐条对齐（UI 不自己重判一套规则）

    这里的重点不是“某个具体组合列哪几项”（那是上一测钉的），而是四个位置都扫一遍：
    自己、自己的子树、父组、别的组。只扫一个形状时，“把条件写反”刚好也能对上。
    """
    top = store.add_group("外层")
    inner = store.add_group("内层", top)
    other = store.add_group("别的")
    link = store.add_link("条", r"C:\a", inner)
    store.save()

    for node_id in (top, inner, other, link):
        sb.refresh_tree(select_id=node_id)
        seen = capture_menu(monkeypatch)

        sb.move_to_group()

        items = [pair for pair in seen["items"] if pair[0] != NO_TARGET_HINT]
        texts = [text for text, _on in items]
        wanted = (["收藏夹根目录"] if not store.can_place(node_id, ROOT_ID) else [])
        wanted += [g["name"] for g in store.groups()
                   if not store.can_place(node_id, g["id"])]
        assert texts == wanted, node_id
        # 列出来的都是能放的；唯一可能的 disabled 项就是那句提示，已过滤
        assert all(on for _text, on in items), node_id


def test_context_menu_offers_the_group_actions(sb, store, monkeypatch):
    link = store.add_link("条", r"C:\a")
    sb.refresh_tree(select_id=link)
    seen = capture_menu(monkeypatch)
    tree = sb.tree
    position = tree.visualItemRect(item_at(tree, 0)).center()

    sb.show_context_menu(position)

    texts = [text for text, _on in seen["items"]]
    for wanted in ("打开", "新建分组…", "添加收藏…", "重命名…", "移动到分组…",
                   "删除", "导入收藏夹…", "导出收藏夹…"):
        assert wanted in texts, wanted


def test_context_menu_on_blank_space_has_no_per_item_actions(sb, store, monkeypatch):
    store.add_link("条", r"C:\a")
    sb.refresh_tree()
    seen = capture_menu(monkeypatch)

    sb.show_context_menu(QPoint(0, 100000))               # 所有项以下的空白

    texts = [text for text, _on in seen["items"]]
    assert "重命名…" not in texts and "删除" not in texts
    assert "新建分组…" in texts


# ================================================================ 兼容与接线


def test_get_bookmarks_is_a_flat_list_in_display_order(sb, store):
    group = store.add_group("组")
    store.add_link("里面", r"C:\in", group)
    store.add_link("外面", r"C:\out")
    store.add_group("空组")

    assert sb.get_bookmarks() == [{"name": "里面", "path": r"C:\in"},
                                  {"name": "外面", "path": r"C:\out"}]


def test_set_store_repaints_the_tree(qtbot, store, monkeypatch, tmp_path):
    from widgets.bookmark_sidebar import BookmarkSidebar

    monkeypatch.setattr(bm, "default_nodes", lambda: [])      # 不给新存储灌默认四条
    store.add_link("旧的", r"C:\old")
    store.save()
    sidebar = BookmarkSidebar(store=store)
    qtbot.addWidget(sidebar)
    assert top_names(sidebar.tree) == ["旧的"]
    other_dir = str(tmp_path / "other")

    sidebar.set_store(BookmarkStore(config_dir=other_dir))

    assert top_names(sidebar.tree) == []
    assert sidebar.store.config_file == os.path.join(other_dir, FILE_NAME)


def test_sidebar_without_an_injected_store_uses_the_default_dir(
        qtbot, monkeypatch, tmp_path):
    from widgets.bookmark_sidebar import BookmarkSidebar

    monkeypatch.setattr(bm, "default_config_dir", lambda: str(tmp_path / "defcfg"))

    sidebar = BookmarkSidebar()
    qtbot.addWidget(sidebar)

    assert sidebar.store.config_file == \
        os.path.join(str(tmp_path / "defcfg"), FILE_NAME)


def test_main_window_shares_one_store_with_its_sidebar(qtbot, tmp_path, monkeypatch):
    """侧边栏与窗格右键「添加到收藏夹」必须同一份，否则两边各存各的"""
    monkeypatch.setattr(bm, "default_config_dir", lambda: str(tmp_path / "cfg"))
    from core.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)

    assert win.bookmark_sidebar.store is win.bookmark_store
    assert isinstance(win.bookmark_store, BookmarkStore)


def test_pane_right_click_adds_through_the_shared_store(qtbot, tmp_path, monkeypatch):
    """窗格右键那条路（`Pane.add_to_bookmarks`）落在同一份存储上"""
    from core.main_window import MainWindow

    monkeypatch.setattr(bm, "default_config_dir", lambda: str(tmp_path / "cfg"))
    win = MainWindow()
    qtbot.addWidget(win)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("从窗格来的", True)))
    target = tmp_path / "要收的目录"
    target.mkdir()
    before = len(win.bookmark_store.links())
    pane = win.tab_widget.widget(0).pane1        # `_active_pane` 只在窗格拿到焦点时赋值

    pane.add_to_bookmarks(str(target))

    assert len(win.bookmark_store.links()) == before + 1
    assert str(target) in [lk["path"] for lk in win.bookmark_store.links()]
    assert read_raw(str(tmp_path / "cfg"))["children"][-1]["name"] == "从窗格来的"


# ---------- 首启动默认四条：XDG 本地化目录 ----------

class TestDefaultXdgDirs:
    """默认收藏项去哪找那些目录（旧版写死英文名，中文桌面上三条全指错）

    freedesktop 的 `user-dirs.dirs` 才是本地化桌面的正解（`~/桌面`、`~/下载`），
    文件格式有几个坑：值带双引号、家目录写成 `$HOME`、满屏注释行。解析做成纯
    函数，所以这些坑在 Windows 主机上一样能测到。
    """

    SAMPLE = (
        '# ~/.config/user-dirs.dirs\n'
        '# This file is written by xdg-user-dirs-update\n'
        '#XDG_DOCUMENTS_DIR="$HOME/文档"\n'
        'XDG_DESKTOP_DIR="$HOME/桌面"\n'
        'XDG_DOWNLOAD_DIR="$HOME/下载"\n'
        'XDG_TEMPLATES_DIR="$HOME/模板"\n'
        'XDG_DOCUMENTS_DIR="$HOME/Documents"\n'
        'XDG_MUSIC_DIR=$HOME/音乐\n'
        '#XDG_PICTURES_DIR="$HOME/图片"\n'
    )

    def test_expands_home_and_strips_quotes(self, tmp_path):
        home = str(tmp_path)
        got = bm.parse_user_dirs(self.SAMPLE, home)
        # 解析器不管分隔符（它是 POSIX 语义），换分隔符是 `default_links` 的事
        assert got["XDG_DESKTOP_DIR"] == home + "/桌面"
        assert got["XDG_DOCUMENTS_DIR"] == home + "/Documents"

    def test_comments_and_non_dir_keys_are_skipped(self, tmp_path):
        got = bm.parse_user_dirs(self.SAMPLE, str(tmp_path))
        # 注释掉的那行带着 `=`，只靠「跳过 `#` 开头」才不会把它当配置读进来
        assert got["XDG_DOCUMENTS_DIR"] == str(tmp_path) + "/Documents"
        assert "XDG_CONFIG_HOME" not in got
        # 只以注释形式存在的那一项不该被当成配置读进来
        assert "XDG_PICTURES_DIR" not in got
        # 没引号的值也收（上面那行 `XDG_MUSIC_DIR=$HOME/音乐` 就是这种）
        assert got["XDG_MUSIC_DIR"].endswith("音乐")

    def test_without_home_the_variable_is_left_alone(self):
        got = bm.parse_user_dirs(self.SAMPLE)
        assert got["XDG_DOWNLOAD_DIR"] == "$HOME/下载"

    def test_a_tilde_inside_a_name_is_not_mangled(self, tmp_path):
        """`~` 是合法的目录名字符，只能处理开头的 `~/`，不能无差别替换"""
        got = bm.parse_user_dirs('XDG_DESKTOP_DIR="$HOME/a~b"\n', str(tmp_path))
        assert got["XDG_DESKTOP_DIR"] == str(tmp_path) + "/a~b"

    def test_localized_names_win_over_english_ones(self, tmp_path):
        home = tmp_path
        (home / "桌面").mkdir()
        (home / "下载").mkdir()
        nodes = bm.default_links(str(home), {"XDG_DESKTOP_DIR": str(home / "桌面"),
                                             "XDG_DOWNLOAD_DIR": str(home / "下载")})
        paths = [n["path"] for n in nodes]
        assert str(home / "桌面") in paths and str(home / "下载") in paths
        assert nodes[0]["name"] == "主目录" and nodes[0]["path"] == str(home)

    def test_missing_directories_are_not_offered(self, tmp_path):
        """两条都不存在就干脆不给 —— 点不开的空收藏比缺一条更糟"""
        nodes = bm.default_links(str(tmp_path), {})
        assert [n["name"] for n in nodes] == ["主目录"]

    def test_english_fallback_when_xdg_table_is_empty(self, tmp_path):
        home = tmp_path
        (home / "Desktop").mkdir()
        (home / "Downloads").mkdir()
        nodes = bm.default_links(str(home), {})
        paths = [n["path"] for n in nodes]
        assert paths == [str(home), str(home / "Desktop"), str(home / "Downloads")]

    def test_default_nodes_reads_the_xdg_file_on_posix(self, tmp_path, monkeypatch):
        """接线：POSIX 下真的去读 `~/.config/user-dirs.dirs`（在 Windows 主机上伪造）"""
        home = tmp_path / "home"
        (home / ".config").mkdir(parents=True)
        (home / "桌面").mkdir()
        (home / ".config" / "user-dirs.dirs").write_text(
            'XDG_DESKTOP_DIR="$HOME/桌面"\n', encoding="utf-8")
        monkeypatch.setattr(bm.os, "name", "posix")     # 只改这一个用例里的平台判据
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
        paths = [n["path"] for n in bm.default_nodes(str(home))]
        assert str(home / "桌面") in paths
        assert str(home / "Desktop") not in paths

    def test_default_nodes_on_windows_ignores_the_xdg_file(self, tmp_path, monkeypatch):
        """Windows 不读 XDG（那边没有这个文件），只拼 `%USERPROFILE%` 下的英文名"""
        home = tmp_path / "winhome"
        (home / ".config").mkdir(parents=True)
        (home / ".config" / "user-dirs.dirs").write_text(
            'XDG_DESKTOP_DIR="$HOME/桌面"\n', encoding="utf-8")
        (home / "Desktop").mkdir()
        monkeypatch.setattr(bm.os, "name", "nt")
        paths = [n["path"] for n in bm.default_nodes(str(home))]
        assert str(home / "桌面") not in paths
        assert str(home / "Desktop") in paths
