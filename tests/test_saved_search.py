# -*- coding: utf-8 -*-
"""已保存的搜索条件（清单 20.4）与高级搜索的匹配语义。

20.4 存的是「真正喂给 `SearchWorker` 的那份 params」，所以核心不变式是
`collect_params → apply_params → collect_params` **必须一模一样** —— 大小换算最容易
在来回中变形（两个输入框共用一个单位下拉，1024 字节可能被还原成 1024 MB）。

另一批测试盯住本轮读代码时发现的真 bug：非正则模式下，界面上教的 `*.txt` 被
`re.escape` 当成字面量匹配，**按提示写必然搜不到任何东西**。
"""
import json
import os
import re

import pytest

from config.saved_searches import MAX_ENTRIES, MAX_NAME_LEN, SavedSearchStore


@pytest.fixture
def store(tmp_path):
    return SavedSearchStore(config_dir=str(tmp_path / "cfg"))


def params(**over):
    base = {
        'directory': r"C:\work",
        'pattern': "*.log",
        'use_regex': False,
        'case_sensitive': False,
        'file_types': [".log"],
        'min_size': 1024,
        'max_size': 1024 * 1024,
        'content': "todo",
    }
    base.update(over)
    return base


def dp(tmp_path, **over):
    """`params()` 但目录指向真的临时目录 —— 对话框的校验要求目录存在"""
    return params(directory=str(tmp_path), **over)


# ---------------------------------------------------------------- 存储层

def test_save_and_read_back(store):
    ok, err = store.save_search("日志", params())
    assert (ok, err) == (True, "")
    assert store.names() == ["日志"]
    assert store.get("日志") == params()
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d$", store.updated("日志"))


def test_names_are_sorted_stably(store):
    for name in ("beta", "Alpha", "gz"):
        store.save_search(name, params())
    assert store.names() == ["Alpha", "beta", "gz"]      # 不区分大小写的字典序


def test_same_name_overwrites_and_others_survive(store):
    store.save_search("日志", params(pattern="*.log"))
    store.save_search("别的", params())
    store.save_search("日志", params(pattern="*.txt"))
    assert store.get("日志")['pattern'] == "*.txt"
    assert len(store.entries) == 2


def test_reload_from_disk(store):
    store.save_search("日志", params())
    again = SavedSearchStore(config_dir=store.config_dir)
    assert again.get("日志") == params()


def test_remove(store):
    store.save_search("日志", params())
    assert store.remove("日志") is True
    assert store.get("日志") is None
    assert store.remove("日志") is False
    assert SavedSearchStore(config_dir=store.config_dir).names() == []


def test_invalid_names_rejected(store):
    assert store.save_search("   ", params())[0] is False
    assert store.save_search("x" * (MAX_NAME_LEN + 1), params())[0] is False
    assert store.save_search("名字", {})[0] is False           # 没有条件可存
    assert store.entries == {}


def test_entry_cap_blocks_new_names_only(store):
    for i in range(MAX_ENTRIES):
        assert store.save_search(f"s{i}", params())[0] is True
    ok, err = store.save_search("再多一条", params())
    assert ok is False and str(MAX_ENTRIES) in err
    # 达到上限后覆盖已有的仍然可以（不该把人锁死）
    assert store.save_search("s0", params(pattern="*.txt"))[0] is True
    assert len(store.entries) == MAX_ENTRIES


def test_broken_file_is_treated_as_empty(tmp_path):
    cfg = tmp_path / "cfg2"
    cfg.mkdir(parents=True)
    (cfg / "saved_searches.json").write_text("{这不是 json", encoding="utf-8")
    assert SavedSearchStore(config_dir=str(cfg)).names() == []

    (cfg / "saved_searches.json").write_text('["列表也不行"]', encoding="utf-8")
    assert SavedSearchStore(config_dir=str(cfg)).names() == []


def test_bad_records_skipped_good_kept(tmp_path):
    cfg = tmp_path / "cfg3"
    cfg.mkdir(parents=True)
    (cfg / "saved_searches.json").write_text(json.dumps({
        "好的一条": {"params": params()},
        "没有params": {"updated": "x"},
        "  ": {"params": params()},
        "params不是字典": {"params": [1, 2]},
    }), encoding="utf-8")
    got = SavedSearchStore(config_dir=str(cfg))
    assert got.names() == ["好的一条"]


def test_write_failure_reported_not_raised(store, monkeypatch):
    def boom(*a, **k):
        raise OSError("磁盘满了")

    monkeypatch.setattr("builtins.open", boom)
    ok, err = store.save_search("日志", params())
    assert ok is False and "磁盘满了" in err
    # 内存里已经改过：调用方要用错开盘的后果时能看懂状态
    assert store.get("日志") == params()


# ---------------------------------------------------------------- 匹配语义

def test_glob_pattern_matches_by_extension():
    """界面上教的 `*.txt` 必须真的能用（旧实现 re.escape 后必然 0 结果）"""
    from widgets.advanced_search import build_name_matcher

    match, _ = build_name_matcher("*.txt", use_regex=False, case_sensitive=False)
    assert match("report.txt")
    assert match("REPORT.TXT")                     # 不区分大小写
    assert not match("report.txt.bak")             # 整名匹配，不是包含
    assert not match("txt")


def test_glob_is_case_sensitive_when_asked():
    from widgets.advanced_search import build_name_matcher

    match, _ = build_name_matcher("*.TXT", use_regex=False, case_sensitive=True)
    assert match("A.TXT")
    assert not match("a.txt")


def test_plain_text_is_substring_match():
    from widgets.advanced_search import build_name_matcher

    match, _ = build_name_matcher("report", use_regex=False, case_sensitive=False)
    assert match("Q3 report final.docx")
    assert not match("notes.md")


def test_regex_uses_partial_search_and_can_be_rejected():
    from widgets.advanced_search import build_name_matcher

    match, _ = build_name_matcher(r"rep\d+", use_regex=True, case_sensitive=False)
    assert match("xxrep42yy")
    with pytest.raises(re.error):
        build_name_matcher(r"rep(", use_regex=True, case_sensitive=False)


def test_empty_pattern_matches_everything():
    from widgets.advanced_search import build_name_matcher

    match, _ = build_name_matcher("   ", use_regex=False, case_sensitive=False)
    assert match("anything.bin")


def test_worker_finds_files_with_glob(tmp_path):
    """整条 worker 链：glob 找到 5 个 txt（旧代码在这里返回 0）"""
    from widgets.advanced_search import SearchWorker

    for i in range(5):
        (tmp_path / f"t{i}.txt").write_text("hello", encoding="utf-8")
    for i in range(3):
        (tmp_path / f"p{i}.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "backup.txt.bak").write_text("no", encoding="utf-8")

    found = []
    worker = SearchWorker(params(directory=str(tmp_path), pattern="*.txt",
                                 file_types=[], min_size=0, max_size=0,
                                 content="", use_regex=False))
    worker.result.connect(lambda path, size, mtime: found.append(path))
    worker.run()
    assert len(found) == 5
    assert all(os.path.basename(p).endswith(".txt") for p in found)


def test_worker_content_search_honours_case_option(tmp_path):
    from widgets.advanced_search import SearchWorker

    (tmp_path / "a.txt").write_text("TODO 修一下", encoding="utf-8")
    (tmp_path / "b.txt").write_text("todo 修一下", encoding="utf-8")

    def run(content, case_sensitive):
        got = []
        w = SearchWorker(params(directory=str(tmp_path), pattern="",
                               file_types=[], min_size=0, max_size=0,
                               content=content, case_sensitive=case_sensitive))
        w.result.connect(lambda path, size, mtime: got.append(os.path.basename(path)))
        w.run()
        return sorted(got)

    assert run("TODO", False) == ["a.txt", "b.txt"]
    assert run("TODO", True) == ["a.txt"]


# ---------------------------------------------------------------- 对话框

@pytest.fixture
def dlg(qtbot, tmp_path, store):
    from widgets.advanced_search import AdvancedSearchDialog

    d = AdvancedSearchDialog(store=store)
    qtbot.addWidget(d)
    d.dir_edit.setText(str(tmp_path))
    d.pattern_edit.setText("*.log")
    return d


def collect(d):
    got, err = d.collect_params()
    assert err == "", err
    return got


def test_collect_params_validates(dlg, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda parent, title, text, *a: warns.append(text)))

    dlg.dir_edit.setText("")
    dlg.start_search()
    assert warns == ["请输入搜索目录"]

    warns.clear()
    dlg.dir_edit.setText(str(tmp_path / "不存在"))
    dlg.start_search()
    assert warns == ["目录不存在"]

    # 正则写错：以前会“静默找到 0 个”，与“真的没搜到”看起来一模一样
    warns.clear()
    dlg.dir_edit.setText(str(tmp_path))
    dlg.pattern_edit.setText("rep(")
    dlg.regex_check.setChecked(True)
    dlg.start_search()
    assert warns and warns[0].startswith("正则表达式无效")


def test_collect_params_converts_units_and_types(dlg):
    dlg.type_edit.setText("txt，.py; md")
    dlg.min_size_spin.setValue(5)
    dlg.max_size_spin.setValue(0)
    dlg.size_unit.setCurrentIndex(1)             # MB
    got = collect(dlg)
    assert got['min_size'] == 5 * 1024 * 1024
    assert got['max_size'] == 0                   # 0 不参与换算（“最大”哨兵值）
    assert got['file_types'] == [".txt", ".py", ".md"]


def test_round_trip_params_to_widgets_and_back(dlg, tmp_path):
    """存进去再载入，条件必须一模一样（两个框共用一个单位下拉，最容易走形）"""
    KB, MB, GB = 1024, 1024 * 1024, 1024 * 1024 * 1024
    cases = [
        (KB, MB),                         # 1 KB 与 1 MB → 只能按 KB
        (5 * MB, 100 * MB),               # 都是 MB 的整数倍 → 按 MB
        (KB, 99999 * KB),                 # 上限边界：99999 KB 刚好放得下
        (0, 2 * GB),                      # 一侧无限制
    ]
    for lo, hi in cases:
        dlg.apply_params(dp(tmp_path, min_size=lo, max_size=hi))
        got = collect(dlg)
        assert got['min_size'] == lo, (lo, hi, 'min')
        assert got['max_size'] == hi, (lo, hi, 'max')


def test_round_trip_picks_a_unit_both_sides_fit_in(dlg, tmp_path):
    """按 KB 会溢出 spin 上限时：取两者都放得下的最大单位"""
    MB, GB = 1024 * 1024, 1024 * 1024 * 1024
    lo, hi = MB, 3 * GB
    note = dlg.apply_params(dp(tmp_path, min_size=lo, max_size=hi))
    assert note == "", note                      # 按 MB 能原样表示（3072 / 1）
    assert dlg.size_unit.currentText() == "MB"
    assert collect(dlg)['min_size'] == lo
    assert collect(dlg)['max_size'] == hi


def test_unrepresentable_sizes_say_so_instead_of_quietly_changing(dlg, tmp_path):
    """1 字节无法用 KB 粒度表示：不能静默变成“无限制”，要报出来

    `collect_params` 存出去的值一定是“整数 × 单位”，所以这种值只可能来自手工
    改过的 JSON；但一旦存了就说明它存在，载入时默默丢掉条件比难看得多。
    """
    note = dlg.apply_params(dp(tmp_path, min_size=1, max_size=0))
    assert "最接近" in note
    assert dlg.min_size_spin.value() == 0        # 确实只能归到 0
    assert collect(dlg)['min_size'] == 0         # 与界面显示一致（没骗界面）

    # 载入槽把这句拼进状态栏，不能只返回值却没人看
    dlg.store.save_search("奇怪的条件", dp(tmp_path, min_size=1, max_size=0))
    dlg.reload_saved_names(keep="奇怪的条件")
    dlg.on_saved_selected(dlg.saved_combo.currentIndex())
    assert "最接近" in dlg.status_label.text()


def test_apply_params_fills_every_field(dlg):
    p = params(directory=r"D:\notes", pattern="report*", use_regex=False,
               case_sensitive=True, file_types=[".md", ".txt"],
               min_size=0, max_size=0, content="重要")
    dlg.apply_params(p)
    assert dlg.dir_edit.text() == r"D:\notes"
    assert dlg.pattern_edit.text() == "report*"
    assert dlg.regex_check.isChecked() is False
    assert dlg.case_check.isChecked() is True
    assert dlg.type_edit.text() == ".md,.txt"
    assert dlg.content_edit.text() == "重要"


def test_save_current_search_stores_and_lists_name(dlg, store, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("每周日志", True)))
    dlg.save_current_search()

    assert store.names() == ["每周日志"]
    assert store.get("每周日志") == collect(dlg)
    assert dlg.saved_combo.findText("每周日志") > 0
    assert "每周日志" in dlg.status_label.text()


def test_save_uses_placeholder_free_default_name(dlg, store, monkeypatch):
    """默认名不能是下拉里那句占位提示"""
    from PyQt6.QtWidgets import QInputDialog

    asked = []
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda parent, title, label, **k:
                                     (asked.append(k.get("text")) or ("", False))))
    dlg.save_current_search()
    assert asked == ["*.log"]
    assert store.names() == []                 # 取消了：什么都没存


def test_save_overwrite_asks_and_respects_no(dlg, store, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox

    store.save_search("每周日志", params(pattern="旧条件"))
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("每周日志", True)))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    dlg.save_current_search()
    assert store.get("每周日志")['pattern'] == "旧条件"

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dlg.save_current_search()
    assert store.get("每周日志")['pattern'] == "*.log"


def test_saved_item_loads_fields_without_starting_search(dlg, store, qtbot):
    store.save_search("每周日志", params(directory=r"E:\reports", pattern="*.pdf",
                                        content="预算"))
    dlg.reload_saved_names(keep="每周日志")
    dlg.on_saved_selected(dlg.saved_combo.currentIndex())

    assert dlg.dir_edit.text() == r"E:\reports"
    assert dlg.pattern_edit.text() == "*.pdf"
    assert dlg.content_edit.text() == "预算"
    assert dlg.worker is None, "载入不该顺手开搜"
    assert "已载入" in dlg.status_label.text()


def test_delete_saved_search_removes_and_relists(dlg, store, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    store.save_search("每周日志", params())
    dlg.reload_saved_names(keep="每周日志")
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dlg.delete_saved_search()
    assert store.names() == []
    assert dlg.saved_combo.count() == 1        # 只剩占位项
    assert dlg.del_saved_btn.isEnabled() is False


def test_missing_record_does_not_crash(dlg, store):
    store.save_search("每周日志", params())
    dlg.reload_saved_names(keep="每周日志")
    store.entries.clear()                       # 另一个窗口把它删了
    dlg.on_saved_selected(1)
    assert "已不存在" in dlg.status_label.text()
    assert dlg.saved_combo.count() == 1


def test_main_window_injects_its_store(qtbot, tmp_path, monkeypatch):
    """主窗口必须把自己的存储注进对话框（否则对话框会往用户真实配置目录里写）"""
    import widgets.advanced_search as adv
    from core.main_window import MainWindow
    from PyQt6.QtCore import QSettings

    win = MainWindow()
    qtbot.addWidget(win)
    win.settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)

    seen = {}

    class Recorder:
        def __init__(self, parent=None, store=None):
            seen['store'] = store

        def exec(self):
            return 0

    monkeypatch.setattr(adv, "AdvancedSearchDialog", Recorder)
    win.open_advanced_search()
    assert seen['store'] is win.saved_searches
