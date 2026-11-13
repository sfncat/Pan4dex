# -*- coding: utf-8 -*-
"""T8 · 「在系统文件管理器中选中」只有一份实现（core/reveal.py）。

原先窗格与高级搜索各写一份：Windows 一边 argv 列表、一边命令行字符串，Linux 两边
都只打开所在目录（不选中）。这里盯四件事：

- 三个平台拼出的 argv（**必须是列表**，不经 shell，路径里的空格/中文/UNC 才安全）
- 上限 5 与「前 5 个」文案不变（调用方负责文案，助手只负责执行）
- 回落路径要**明说没选中**，不能让用户以为文件已经高亮
- 两处调用方对同一路径拼出**同一条 argv**（这就是「合一」的观测量）

真机行为（Explorer 哪种形式能选中、dolphin/nautilus 的 --select 是否高亮）本轮
**未实测**，不在这里断言；见 docs/improvement-plan-t6-t9.md §4.5 的待实测清单。
"""
import os
import shutil
import subprocess
import sys

import pytest

from core import reveal


class FakePopen:
    """替掉 subprocess.Popen：只记下收到了什么，不真的拉起文件管理器窗口"""

    def __init__(self):
        self.calls = []          # [(argv, kwargs)]
        self.fail_first = 0      # 前 N 次抛 OSError（模拟启动失败）
        self.returncode = 1      # Explorer 即使成功也常返回 1

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.fail_first > 0:
            self.fail_first -= 1
            raise OSError("拒绝访问")
        return self

    @property
    def argvs(self):
        return [a for a, _ in self.calls]

    def wait(self, *a, **k):
        raise AssertionError("定位不该等待子进程：Explorer 成功也常返回 1，等它没有意义")

    def communicate(self, *a, **k):
        raise AssertionError("定位不该读子进程输出")


@pytest.fixture
def popen(monkeypatch):
    fake = FakePopen()
    monkeypatch.setattr(subprocess, "Popen", fake)
    return fake


@pytest.fixture
def as_platform(monkeypatch):
    """把平台/桌面环境/可执行文件可用性摆成指定样子（Linux 分支全靠这三样）"""
    def setup(name, desktop=None, kde_session=False, bins=()):
        monkeypatch.setattr(sys, "platform", name)
        monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
        monkeypatch.delenv("KDE_FULL_SESSION", raising=False)
        if desktop is not None:
            monkeypatch.setenv("XDG_CURRENT_DESKTOP", desktop)
        if kde_session:
            monkeypatch.setenv("KDE_FULL_SESSION", "true")
        monkeypatch.setattr(shutil, "which",
                            lambda cmd: f"/usr/bin/{cmd}" if cmd in bins else None)
    return setup


# --------------------------------------------------------------- 助手：拼 argv

def test_windows_uses_argv_list_not_shell_string(popen, as_platform, tmp_path):
    """带空格路径：argv 列表天然安全，字符串形式要靠引号，一旦路径里有引号就崩"""
    as_platform("win32")
    p = str(tmp_path / "My Documents" / "a b.txt")
    result = reveal.reveal_in_file_manager(p)
    assert len(popen.calls) == 1
    argv, kw = popen.calls[0]
    assert isinstance(argv, list)
    assert kw.get("shell") is not True
    assert argv == ["explorer", "/select,", os.path.normpath(p)]
    assert (result.opened, result.failed, result.selected) == (1, 0, True)


def test_windows_unifies_mixed_separators(popen, as_platform):
    as_platform("win32")
    reveal.reveal_in_file_manager("C:/照片 集/IMG 0001.jpg")
    assert popen.argvs == [["explorer", "/select,", "C:\\照片 集\\IMG 0001.jpg"]]


@pytest.mark.parametrize("given,expected", [
    ("\\\\nas\\share\\dir\\f.txt", "\\\\nas\\share\\dir\\f.txt"),   # 已正确，不动
    ("\\nas\\share\\f.txt", "\\\\nas\\share\\f.txt"),               # 单前导补回
    ("//nas/share/f.txt", "\\\\nas\\share\\f.txt"),                 # 正斜杠 UNC
    ("C:\\x\\y", "C:\\x\\y"),                                       # 盘符不受影响
])
def test_windows_unc_and_drive_paths(popen, as_platform, given, expected):
    as_platform("win32")
    reveal.reveal_in_file_manager(given)
    assert popen.argvs == [["explorer", "/select,", expected]]


def test_macos_open_reveals(popen, as_platform, tmp_path):
    as_platform("darwin")
    p = str(tmp_path / "a b.txt")
    result = reveal.reveal_in_file_manager(p)
    assert popen.argvs == [["open", "-R", os.path.normpath(p)]]
    assert result.selected is True


def test_linux_kde_dolphin_selects(popen, as_platform, tmp_path):
    as_platform("linux", desktop="KDE", bins=("dolphin",))
    p = str(tmp_path / "a.txt")
    result = reveal.reveal_in_file_manager(p)
    assert popen.argvs == [["dolphin", "--select", os.path.normpath(p)]]
    assert result.selected is True


def test_linux_kde_detected_by_session_flag(popen, as_platform, tmp_path):
    """有些 KDE 会话不设 XDG_CURRENT_DESKTOP，只设 KDE_FULL_SESSION"""
    as_platform("linux", kde_session=True, bins=("dolphin",))
    p = str(tmp_path / "a.txt")
    reveal.reveal_in_file_manager(p)
    assert popen.argvs[0][0] == "dolphin"


def test_linux_gnome_nautilus_selects(popen, as_platform, tmp_path):
    as_platform("linux", desktop="GNOME", bins=("nautilus",))
    p = str(tmp_path / "a.txt")
    result = reveal.reveal_in_file_manager(p)
    assert popen.argvs == [["nautilus", "--select", os.path.normpath(p)]]
    assert result.selected is True


def test_linux_desktop_without_binary_falls_back(popen, as_platform, tmp_path):
    """自称 KDE 但没装 dolphin：不能拼一条跑不起来的命令"""
    as_platform("linux", desktop="KDE", bins=())
    p = str(tmp_path / "sub" / "a.txt")
    result = reveal.reveal_in_file_manager(p)
    assert popen.argvs == [["xdg-open", os.path.normpath(str(tmp_path / "sub"))]]
    assert result.selected is False


def test_linux_unknown_desktop_falls_back_and_says_not_selected(popen, as_platform, tmp_path):
    as_platform("linux", desktop="XFCE", bins=("dolphin", "nautilus"))
    p = str(tmp_path / "a.txt")
    result = reveal.reveal_in_file_manager(p)
    assert popen.argvs == [["xdg-open", os.path.normpath(str(tmp_path))]]
    assert result.selected is False


# --------------------------------------------------------------- 助手：上限与失败

def test_limit_caps_the_number_of_windows(popen, as_platform, tmp_path):
    as_platform("win32")
    paths = [str(tmp_path / f"r{i}.txt") for i in range(7)]
    result = reveal.reveal_in_file_manager(paths)
    assert len(popen.calls) == reveal.REVEAL_LIMIT == 5
    assert result.opened == 5


def test_custom_limit(popen, as_platform, tmp_path):
    as_platform("win32")
    paths = [str(tmp_path / f"r{i}.txt") for i in range(4)]
    reveal.reveal_in_file_manager(paths, limit=2)
    assert len(popen.calls) == 2


def test_empty_input_launches_nothing(popen, as_platform):
    as_platform("win32")
    for given in ([], [""], ["", None]):
        result = reveal.reveal_in_file_manager(given)
        assert (result.opened, result.failed) == (0, 0)
    assert popen.calls == []


def test_launch_failure_is_returned_not_raised(popen, as_platform, tmp_path):
    """失败只回结果 + 记日志：弹窗会把测试永久挂住（gotchas #56）"""
    as_platform("win32")
    popen.fail_first = 1
    result = reveal.reveal_in_file_manager(str(tmp_path / "a.txt"))
    assert (result.opened, result.failed) == (0, 1)
    assert "拒绝访问" in result.error


def test_first_failure_reason_is_kept_and_rest_still_run(popen, as_platform, tmp_path):
    as_platform("win32")
    popen.fail_first = 1
    paths = [str(tmp_path / f"r{i}.txt") for i in range(3)]
    result = reveal.reveal_in_file_manager(paths)
    assert (result.opened, result.failed) == (2, 1)
    assert len(popen.calls) == 3


def test_exit_code_one_is_not_treated_as_failure(popen, as_platform, tmp_path):
    as_platform("win32")
    result = reveal.reveal_in_file_manager(str(tmp_path / "a.txt"))
    assert result.opened == 1 and result.failed == 0


# --------------------------------------------------------------- 窗格侧 delegate

@pytest.fixture
def pane(qtbot, tmp_path):
    from core.pane import Pane
    p = Pane("t_reveal", start_path=str(tmp_path))
    qtbot.addWidget(p)
    return p


def test_pane_reveal_goes_through_helper(pane, popen, as_platform, tmp_path):
    as_platform("win32")
    target = str(tmp_path / "a b.txt")
    pane._reveal_in_file_manager(target)
    assert popen.argvs == [["explorer", "/select,", os.path.normpath(target)]]


def test_pane_empty_path_is_noop(pane, popen, as_platform):
    as_platform("win32")
    pane._reveal_in_file_manager("")
    assert popen.calls == []


def test_pane_linux_fallback_says_not_selected(pane, popen, as_platform, tmp_path):
    """回落只打开了目录，状态栏必须说出来，不能让人以为文件已高亮"""
    as_platform("linux", bins=())
    target = str(tmp_path / "a.txt")
    pane._reveal_in_file_manager(target)
    assert popen.argvs == [["xdg-open", os.path.normpath(str(tmp_path))]]
    assert "未能选中" in pane.status_label.text()


def test_pane_failure_writes_status(pane, popen, as_platform, tmp_path):
    as_platform("win32")
    popen.fail_first = 1
    pane.status_label.setText("原来的话")
    pane._reveal_in_file_manager(str(tmp_path / "a.txt"))
    assert pane.status_label.text().startswith("无法在文件管理器中显示")
    assert "拒绝访问" in pane.status_label.text()


def test_pane_success_leaves_status_alone(pane, popen, as_platform, tmp_path):
    as_platform("win32")
    pane.status_label.setText("原来的话")
    pane._reveal_in_file_manager(str(tmp_path / "a.txt"))
    assert pane.status_label.text() == "原来的话"


@pytest.mark.parametrize("given,expected", [
    ("\\\\srv\\share\\a", "\\\\srv\\share\\a"),
    ("\\srv\\share", "\\\\srv\\share"),
    ("C:\\x\\y", "C:\\x\\y"),
])
def test_win_unc_fix_still_available_on_pane(given, expected):
    """方法名被 tests/test_phase1_shell_behavior.py 钉着，转发后仍要可用"""
    from core.pane import Pane
    assert Pane._win_unc_fix(given) == expected
    assert Pane._win_unc_fix(given) == reveal.win_unc_fix(given)


# --------------------------------------------------------------- 搜索侧 delegate

@pytest.fixture
def dlg(qtbot, tmp_path):
    from config.saved_searches import SavedSearchStore
    from widgets.advanced_search import AdvancedSearchDialog
    d = AdvancedSearchDialog(store=SavedSearchStore(config_dir=str(tmp_path / "cfg")))
    qtbot.addWidget(d)
    return d


def _rows(d, paths):
    from PyQt6.QtWidgets import QTreeWidgetItem
    for p in paths:
        d.result_tree.addTopLevelItem(QTreeWidgetItem([p, "1 B", "2026-01-01 00:00"]))
        d.result_tree.topLevelItem(d.result_tree.topLevelItemCount() - 1).setSelected(True)


def test_search_reveal_works_without_a_pane(dlg, popen, as_platform, tmp_path):
    """没连接主窗口时 pane_for_ops() 是 None —— 定位不能依赖窗格"""
    as_platform("win32")
    assert dlg.pane_for_ops() is None
    target = str(tmp_path / "a.txt")
    _rows(dlg, [target])
    dlg.reveal_in_system_manager()
    assert popen.argvs == [["explorer", "/select,", os.path.normpath(target)]]


def test_search_cap_and_wording_unchanged(dlg, popen, as_platform, tmp_path):
    as_platform("win32")
    paths = [str(tmp_path / f"r{i}.txt") for i in range(7)]
    _rows(dlg, paths)
    dlg.reveal_in_system_manager()
    assert len(popen.calls) == 5
    assert "前 5 个" in dlg.status_label.text()


def test_search_reports_failure_even_when_capped(dlg, popen, as_platform, tmp_path):
    """超过上限时也不能把失败咽掉：两条提示都要在"""
    as_platform("win32")
    popen.fail_first = 1
    paths = [str(tmp_path / f"r{i}.txt") for i in range(7)]
    _rows(dlg, paths)
    dlg.reveal_in_system_manager()
    text = dlg.status_label.text()
    assert "前 5 个" in text
    assert "定位失败" in text


def test_search_linux_fallback_says_not_selected(dlg, popen, as_platform, tmp_path):
    as_platform("linux", bins=())
    target = str(tmp_path / "a.txt")
    _rows(dlg, [target])
    dlg.reveal_in_system_manager()
    assert popen.argvs == [["xdg-open", os.path.normpath(str(tmp_path))]]
    assert "未能选中" in dlg.status_label.text()


def test_search_no_selection_launches_nothing(dlg, popen, as_platform):
    as_platform("win32")
    dlg.reveal_in_system_manager()
    assert popen.calls == []


# --------------------------------------------------------------- 「合一」的观测量

@pytest.mark.parametrize("platform_name,desktop,bins", [
    ("win32", None, ()),
    ("darwin", None, ()),
    ("linux", "KDE", ("dolphin",)),
    ("linux", "GNOME", ("nautilus",)),
    ("linux", None, ()),
])
def test_both_call_sites_build_identical_argv(pane, dlg, popen, as_platform,
                                            tmp_path, platform_name, desktop, bins):
    """同一路径、同一平台，窗格与搜索必须拼出同一条命令。

    旧实现这条必红：Windows 上窗格给 argv 列表、搜索给命令行字符串；Linux 上
    窗格走 QDesktopServices（根本不经过 Popen）、搜索走 xdg-open。
    """
    as_platform(platform_name, desktop=desktop, bins=bins)
    target = str(tmp_path / "带 空格" / "文件.txt")
    pane._reveal_in_file_manager(target)
    _rows(dlg, [target])
    dlg.reveal_in_system_manager()
    assert len(popen.calls) == 2
    assert popen.argvs[0] == popen.argvs[1]
    assert isinstance(popen.argvs[0], list)