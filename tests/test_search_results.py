# -*- coding: utf-8 -*-
"""搜索结果列表的批量操作（清单 20.3）。

结果列表原先只有「双击 → 在系统文件管理器里定位」，多选与复制/移动/删除都没有。
这些用例盯三件事：

- 选区的取法（显示顺序、右键压在哪儿）
- 动作到底把哪些路径交给了谁（复制到 / 移动到 / 删除的实参与安全位）
- 「结果列表是快照」的收尾（移走/删掉的行要消失、显示上限计数要退回来）

真线程不在这里测（见 `tests/test_file_op_runner.py`），这里把 runner 换成桩。
"""
import os

import pytest
from PyQt6.QtCore import QPoint, Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QTreeWidgetItem, QTreeWidget)

from core.file_operations import FileOperationResult, FileOperationType


class RecordingPane:
    """假窗格：只记下「被要求打开/导航了什么」"""

    def __init__(self, current_path=""):
        self.current_path = current_path
        self.opened = []
        self.navigated = []

    def open_file(self, path):
        self.opened.append(path)

    def navigate_to(self, path):
        self.navigated.append(path)


class FakeHost:
    def __init__(self, pane):
        self._pane = pane

    def current_pane(self):
        return self._pane


class StubRunner:
    """替掉真线程运行器：当场执行操作，结果由用例决定"""

    def __init__(self, result=None):
        self.busy = False
        self.note = None
        self.calls = []                       # [(op, sources, 目标或 safe)]
        self.result = result or FileOperationResult(
            True, FileOperationType.COPY, "", files_affected=1)
        self.done_results = []

    @property
    def ops(self):
        return self

    def copy(self, sources, destination):
        self.calls.append(("copy", list(sources), destination))
        return self.result

    def move(self, sources, destination):
        self.calls.append(("move", list(sources), destination))
        return self.result

    def delete(self, paths, safe=True):
        self.calls.append(("delete", list(paths), safe))
        return self.result

    def run(self, note, fn, done=None):
        self.note = note
        result = fn()
        self.done_results.append(result)
        if done is not None:
            done(result)


@pytest.fixture(autouse=True)
def no_real_dialogs(monkeypatch):
    """把本文件会碰到的模态框全换成「用例没替掉就当场报错」

    offscreen 下真弹一个 `QMessageBox` 会永久阻塞（整个测试会话挂死），宁可
    红掉也不能等。用例自己再用 monkeypatch 覆盖对应那一个就行。
    """
    from PyQt6.QtWidgets import QFileDialog

    def boom(*a, **k):
        raise AssertionError(f"用例没有替掉这个对话框：{a[:3]}")

    monkeypatch.setattr(QMessageBox, "question", staticmethod(boom))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(boom))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(boom))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", boom)
    monkeypatch.setattr(QMenu, "exec", boom)


@pytest.fixture
def pane():
    return RecordingPane()


@pytest.fixture
def files(tmp_path):
    made = []
    for i in range(3):
        f = tmp_path / f"f{i}.txt"
        f.write_text("x", encoding="utf-8")
        made.append(os.path.normpath(str(f)))
    return made


@pytest.fixture
def dlg(qtbot, tmp_path, pane):
    from config.saved_searches import SavedSearchStore
    from widgets.advanced_search import AdvancedSearchDialog

    d = AdvancedSearchDialog(store=SavedSearchStore(config_dir=str(tmp_path / "cfg")),
                             host=FakeHost(pane))
    qtbot.addWidget(d)
    d.runner = StubRunner()
    d.stub = d.runner
    d.pane = pane
    d.out = str(tmp_path / "out")
    os.makedirs(d.out, exist_ok=True)
    return d


def add_rows(d, paths):
    for p in paths:
        d.result_tree.addTopLevelItem(QTreeWidgetItem([p, "1 B", "2026-01-01 00:00"]))
    d._shown_count = d.result_tree.topLevelItemCount()
    return paths


def select(d, paths):
    """按给定顺序点选对应行（这个顺序故意不等于显示顺序，否则测不出排不排序）"""
    tree = d.result_tree
    tree.clearSelection()
    by_path = {tree.topLevelItem(i).text(0): tree.topLevelItem(i)
               for i in range(tree.topLevelItemCount())}
    picked = [by_path[p] for p in paths]
    for it in picked:
        it.setSelected(True)
    return picked


def capture_menu(monkeypatch):
    """拦住 `QMenu.exec`（它会阻塞），把菜单项按 (文案, 是否可用) 收下来"""
    seen = []

    def fake_exec(self, *a, **k):
        seen.append([(act.text(), act.isEnabled()) for act in self.actions()])
        return 0

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    return seen


def menu_items(seen, index=0):
    return [text for text, _on in seen[index] if text]


def open_menu(dlg, monkeypatch, hit=None):
    """在「压在 `hit` 这一行上」的位置弹菜单

    控件没显示时 `visualItemRect` 算不出真实位置，所以把 `itemAt` 换掉，
    只测「压在选区内 / 选区外 / 空行」三种落点的行为。
    """
    seen = capture_menu(monkeypatch)
    monkeypatch.setattr(dlg.result_tree, "itemAt", lambda pos: hit)
    dlg.show_results_menu(QPoint(4, 4))
    return seen


# ------------------------------------------------------------------ 选区

def test_result_list_is_multi_selectable(dlg):
    assert dlg.result_tree.selectionMode() == QTreeWidget.SelectionMode.ExtendedSelection


def test_selected_paths_come_back_in_display_order(dlg, files):
    add_rows(dlg, files)
    select(dlg, [files[2], files[0]])                    # 先点最后一行再点第一行
    raw = [it.text(0) for it in dlg.result_tree.selectedItems()]
    assert dlg.selected_paths() == [files[0], files[2]]
    # 前提：Qt 给的选择顺序就是点选顺序（不然这条用例什么也没盯住）
    assert raw != [files[0], files[2]]


def test_right_click_on_an_unselected_row_narrows_the_selection(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, files[:2])
    hit = dlg.result_tree.topLevelItem(2)
    seen = open_menu(dlg, monkeypatch, hit)
    assert menu_items(seen)[0] == "打开"                # 只对那一行生效
    assert dlg.selected_paths() == [files[2]]


def test_right_click_inside_a_selection_keeps_the_whole_selection(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, files)
    seen = open_menu(dlg, monkeypatch, dlg.result_tree.topLevelItem(0))
    assert dlg.selected_paths() == files
    assert menu_items(seen)[0] == f"打开（{len(files)} 项）"


def test_menu_on_empty_list_says_nothing_is_selected(dlg, monkeypatch):
    seen = open_menu(dlg, monkeypatch, None)
    assert menu_items(seen) == ["（没有选中任何结果）"]


def test_menu_lists_the_batch_actions_with_counts(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, files)
    seen = open_menu(dlg, monkeypatch, dlg.result_tree.topLevelItem(0))
    assert menu_items(seen) == [
        f"打开（{len(files)} 项）",
        "打开所在文件夹",
        "在系统文件管理器中选中",
        "复制路径文本",
        f"复制到…（{len(files)} 项）",
        f"移动到…（{len(files)} 项）",
        f"删除（{len(files)} 项）",
        f"永久删除（{len(files)} 项）",
    ]


def test_menu_shows_no_count_for_a_single_row(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, [files[0]])
    seen = open_menu(dlg, monkeypatch, dlg.result_tree.topLevelItem(0))
    assert menu_items(seen)[0] == "打开"


def test_transfer_and_delete_are_disabled_while_an_operation_runs(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, files)
    dlg.runner.busy = True
    seen = open_menu(dlg, monkeypatch, dlg.result_tree.topLevelItem(0))
    for text, enabled in seen[0]:
        if not text:
            continue                                    # 分隔线
        if text.startswith(("复制到", "移动到", "删除", "永久删除")):
            assert enabled is False, text
        else:
            assert enabled is True, text


# ------------------------------------------------------------------ 打开类

def test_open_selected_asks_the_pane_to_open_each_file(dlg, files):
    add_rows(dlg, files)
    select(dlg, files)
    dlg.open_selected()
    assert dlg.pane.opened == files
    assert dlg.status_label.text() == "已打开 3 项"


def test_open_selected_counts_rows_that_vanished(dlg, files, tmp_path):
    gone = os.path.normpath(str(tmp_path / "gone.txt"))     # 搜完之后被别处删了
    add_rows(dlg, files + [gone])
    select(dlg, files + [gone])
    dlg.open_selected()
    assert dlg.pane.opened == files
    assert "1 项已不存在" in dlg.status_label.text()


def test_opening_many_files_needs_a_confirmation(dlg, tmp_path, monkeypatch):
    paths = add_rows(dlg, [os.path.normpath(str(tmp_path / f"m{i}.txt")) for i in range(7)])
    (tmp_path / "m0.txt").write_text("x", encoding="utf-8")
    select(dlg, paths)
    answers = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: answers.append(a) or
                                     QMessageBox.StandardButton.No))
    dlg.open_selected()
    assert answers and "7" in answers[0][2]
    assert dlg.pane.opened == []                            # 点了否：一个都不开


def test_open_without_a_pane_says_so(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, files)
    dlg._host = None
    dlg.setParent(None)
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a: told.append(a[2])))
    dlg.open_selected()
    assert told and "窗格" in told[0]
    assert dlg.pane.opened == []


def test_open_containing_folders_dedupes_and_navigates(dlg, tmp_path):
    other = tmp_path / "sub"
    other.mkdir()
    paths = [os.path.normpath(str(tmp_path / "a.txt")),
             os.path.normpath(str(tmp_path / "b.txt")),
             os.path.normpath(str(other / "c.txt"))]
    add_rows(dlg, paths)
    select(dlg, paths)
    dlg.open_containing_folders()
    assert dlg.pane.navigated == [os.path.normpath(str(tmp_path))]
    assert "2 个目录" in dlg.status_label.text()


def test_double_click_now_opens_the_file(dlg, files, monkeypatch):
    """双击改为「打开」（资源管理器习惯），定位改由右键菜单承担"""
    add_rows(dlg, files)
    called = []
    monkeypatch.setattr(dlg, "open_selected", lambda: called.append("open"))
    dlg.on_item_double_clicked(dlg.result_tree.topLevelItem(2), 0)
    assert called == ["open"]


def test_reveal_in_system_manager_still_works_but_is_capped(dlg, tmp_path, monkeypatch):
    """定位逐条启动系统文件管理器，多了只处理前 5 个（一人开十个窗口是灾难）"""
    started = []
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    more = [os.path.normpath(str(tmp_path / f"r{i}.txt")) for i in range(7)]
    add_rows(dlg, more)
    select(dlg, more)
    dlg.reveal_in_system_manager()
    assert len(started) == 5
    assert "前 5 个" in dlg.status_label.text()


def test_copy_paths_puts_one_path_per_line_in_display_order(dlg, files, monkeypatch):
    text = []

    class Clip:
        def setText(self, t):
            text.append(t)

    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: Clip()))
    add_rows(dlg, files)
    select(dlg, [files[2], files[1]])
    dlg.copy_paths_to_clipboard()
    assert text == ["\n".join([files[1], files[2]])]


# ------------------------------------------------------------------ 复制 / 移动

def choose_target(target):
    def fake(parent, title, start="", *a, **k):
        return target
    return staticmethod(fake)


def test_transfer_is_cancelled_when_no_folder_chosen(dlg, files, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_target(""))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.copy_selected_to()
    assert dlg.stub.calls == []
    assert dlg.status_label.text() == "已取消复制"


def test_copy_refuses_a_target_that_already_holds_the_files(dlg, files, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        choose_target(str(tmp_path)))
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a: warns.append(a[2])))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.copy_selected_to()
    assert warns and "本来就在目标文件夹里" in warns[0]
    assert dlg.stub.calls == []


def test_move_refuses_into_itself(dlg, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    folder = tmp_path / "big"
    (folder / "inner").mkdir(parents=True)
    (folder / "x.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        choose_target(str(folder / "inner")))
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a: warns.append(a[2])))
    add_rows(dlg, [os.path.normpath(str(folder))])
    select(dlg, [os.path.normpath(str(folder))])
    dlg.move_selected_to()
    assert warns and "子目录" in warns[0]
    assert dlg.stub.calls == []


def test_copy_to_runs_a_copy_and_keeps_the_rows(dlg, files, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_target(dlg.out))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.copy_selected_to()
    assert dlg.stub.note == "正在复制"
    assert dlg.stub.calls == [("copy", files, dlg.out)]
    assert dlg.result_tree.topLevelItemCount() == 3
    assert dlg.status_label.text() == f"已复制 3 项 → {dlg.out}"


def test_move_to_drops_the_rows_and_gives_the_display_budget_back(dlg, files, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_target(dlg.out))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.move_selected_to()
    assert dlg.stub.calls == [("move", files, dlg.out)]
    assert dlg.result_tree.topLevelItemCount() == 0
    # 上限计数不退回来，5000 行的结果列表搬完一次就再也显示不出新结果
    assert dlg._shown_count == 0


def test_a_failed_move_keeps_every_row(dlg, files, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_target(dlg.out))
    dlg.stub.result = FileOperationResult(False, FileOperationType.MOVE, "",
                                          error="目标不可写")
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a: warns.append(a[2])))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.move_selected_to()
    assert warns == ["目标不可写"]
    assert dlg.result_tree.topLevelItemCount() == 3
    assert dlg._shown_count == 3


def test_side_effects_are_reported_even_on_success(dlg, files, monkeypatch):
    """失败以外的情况也要说话（网络位置回退永久删除就是这种「成功但有话」）"""
    add_rows(dlg, files)
    select(dlg, files)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dlg.stub.result = FileOperationResult(True, FileOperationType.DELETE, "",
                                          error="网络位置没有回收站，已永久删除",
                                          files_affected=3)
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a: told.append(a[2])))
    dlg.delete_selected()
    assert told == ["网络位置没有回收站，已永久删除"]


def test_second_operation_is_refused_while_one_runs(dlg, files, monkeypatch):
    add_rows(dlg, files)
    select(dlg, files)
    dlg.runner.busy = True
    told = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a: told.append(a[2])))
    dlg.copy_selected_to()
    assert dlg.stub.calls == []
    assert told and "还没结束" in told[0]


# ------------------------------------------------------------------ 删除

def test_delete_asks_with_the_shared_wording(dlg, files, monkeypatch):
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda parent, title, body, *a, **k: asked.append((title, body))
                     or QMessageBox.StandardButton.Yes))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.delete_selected()
    assert asked[0][0] in ("确认删除", "确认永久删除")
    assert "f0.txt" in asked[0][1] and "3" in asked[0][1]
    assert dlg.stub.calls == [("delete", files, True)]      # safe=True → 回收站


def test_shift_delete_is_permanent(dlg, files, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.delete_selected(permanent=True)
    assert dlg.stub.calls == [("delete", files, False)]
    assert dlg.stub.note == "正在删除"


def test_declining_the_confirmation_deletes_nothing(dlg, files, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.delete_selected()
    assert dlg.stub.calls == []
    assert dlg.result_tree.topLevelItemCount() == 3
    assert dlg.status_label.text() == "已取消删除"


def test_failed_delete_keeps_the_rows(dlg, files, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    dlg.stub.result = FileOperationResult(False, FileOperationType.DELETE, "",
                                          error="正在被其它程序占用")
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a: warns.append(a[2])))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.delete_selected()
    assert warns == ["正在被其它程序占用"]
    assert dlg.result_tree.topLevelItemCount() == 3


def test_actions_on_an_empty_selection_do_nothing(dlg):
    for action in (dlg.open_selected, dlg.open_containing_folders,
                   dlg.copy_paths_to_clipboard, dlg.reveal_in_system_manager):
        action()
    assert dlg.pane.opened == [] and dlg.pane.navigated == []
    assert dlg.stub.calls == []


# ------------------------------------------------------------------ 键位接线

def press(tree, key, mods=Qt.KeyboardModifier.NoModifier):
    event = QKeyEvent(QEvent.Type.KeyPress, key, mods)
    tree.keyPressEvent(event)
    return event


def test_enter_key_opens_the_selection(dlg, files):
    add_rows(dlg, files)
    select(dlg, files)
    press(dlg.result_tree, Qt.Key.Key_Return)
    assert dlg.pane.opened == files


def test_ctrl_shift_enter_opens_the_containing_folder(dlg, files):
    add_rows(dlg, files)
    select(dlg, [files[0]])
    press(dlg.result_tree, Qt.Key.Key_Return,
          Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert dlg.pane.navigated == [os.path.dirname(files[0])]


def test_delete_key_sends_the_selection_to_the_recycle_bin(dlg, files, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    add_rows(dlg, files)
    select(dlg, files)
    press(dlg.result_tree, Qt.Key.Key_Delete)
    assert dlg.stub.calls == [("delete", files, True)]
    assert dlg.result_tree.topLevelItemCount() == 0     # 删成功的行不再留在结果里


def test_shift_delete_key_asks_for_permanent_removal(dlg, files, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    add_rows(dlg, files)
    select(dlg, files)
    press(dlg.result_tree, Qt.Key.Key_Delete, Qt.KeyboardModifier.ShiftModifier)
    assert dlg.stub.calls == [("delete", files, False)]


def test_ctrl_c_on_the_list_copies_paths(dlg, files, monkeypatch):
    text = []

    class Clip:
        def setText(self, t):
            text.append(t)

    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: Clip()))
    add_rows(dlg, files)
    select(dlg, [files[0]])
    press(dlg.result_tree, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert text == [files[0]]


def test_other_keys_still_go_to_the_tree(dlg, files):
    """不能把列表里正常的操作（方向键、Ctrl+A 等）一起吃掉"""
    add_rows(dlg, files)
    press(dlg.result_tree, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert dlg.pane.opened == [] and dlg.pane.navigated == []
    assert dlg.stub.calls == []


# ------------------------------------------------------------------ 收尾

def test_delete_makes_the_panes_rescan_the_affected_dirs(dlg, files, monkeypatch):
    from core.pane import Pane
    seen = []
    monkeypatch.setattr(Pane, "_refresh_dir_everywhere",
                        staticmethod(lambda path, *a, **k: seen.append(path)))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.delete_selected()
    assert os.path.normpath(os.path.dirname(files[0])) in seen


def test_copy_makes_the_destination_dir_rescan(dlg, files, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from core.pane import Pane
    seen = []
    monkeypatch.setattr(Pane, "_refresh_dir_everywhere",
                        staticmethod(lambda path, *a, **k: seen.append(path)))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_target(dlg.out))
    add_rows(dlg, files)
    select(dlg, files)
    dlg.copy_selected_to()
    assert os.path.normpath(dlg.out) in seen
