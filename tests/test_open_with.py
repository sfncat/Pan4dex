# -*- coding: utf-8 -*-
"""「打开方式」（右键子菜单）：候选枚举 + 启动 + 菜单接线。

这一节的风险点只有两个，测试也都盯着它们：
1. 候选枚举必须**延迟到子菜单真要显示时** —— 构造右键菜单时读注册表/扫盘是纯浪费；
2. 枚举任何一步失败只准「少一项候选」，不准把整个右键菜单弄坏（右键必须弹得出来）。

其余是纯解析逻辑（命令行切分、占位符剥离、`.desktop` 解析），以及 Windows 上
拿真注册表做一次冒烟（候选的 exe 必须真的存在、显示名不能是文档类型描述）。
"""
import os
import sys
import time

import pytest

from core import open_with
from core.dir_model import dir_pool


@pytest.fixture(autouse=True)
def _fresh_cache():
    """候选缓存是模块级的：不清掉就会跨测试（甚至跨断言）串味。"""
    open_with.clear_cache()
    yield
    open_with.clear_cache()


def _app(name, exe, args=(), source="progid"):
    return open_with.OpenWithApp(name=name, exe=exe, args=tuple(args), source=source)


# list_apps 按 sys.platform 分派，测试里要替换的是「本机真正被调用的那个」枚举函数
_CURRENT_LIST_FUNC = {"win32": "_list_windows",
                      "darwin": "_list_macos"}.get(sys.platform, "_list_linux")


# ---------------------------------------------------------------- 命令行解析

def test_split_command_line_keeps_quoted_path_together():
    got = open_with.split_command_line(
        r'"C:\Program Files\App\a.exe" --flag "%1"')
    assert got == [r"C:\Program Files\App\a.exe", "--flag", "%1"]


def test_split_command_line_expands_none_but_keeps_double_quote():
    # `""` 在引号内表示一个字面引号，不是「结束 + 开始」
    got = open_with.split_command_line(r'"C:\a.exe" "say ""hi""" tail')
    assert got == [r"C:\a.exe", 'say "hi"', "tail"]


def test_argv_for_strips_placeholders_and_appends_path_last():
    app = _app("a", "C:\\x\\a.exe", args=("--flag", "%1", "-n", "%*"))
    assert app.argv_for("D:\\d\\note.txt") == [
        "C:\\x\\a.exe", "--flag", "-n", "D:\\d\\note.txt"]


def test_exe_stem_falls_back_to_input_when_no_filename():
    # 路径用 `/` 分隔：`ntpath` 与 `posixpath` 都认，同一份断言两端能跑
    # （写死 `C:\Windows\...` 在 Linux 上会得到整串 —— `\` 不是 POSIX 分隔符）
    assert open_with._exe_stem("/opt/bin/notepad.exe") == "notepad"
    assert open_with._exe_stem("") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="只有 Windows 用反斜杠路径")
def test_exe_stem_on_a_windows_path():
    assert open_with._exe_stem(r"C:\Windows\System32\notepad.exe") == "notepad"


def test_windows_fallback_is_type_aware():
    """.txt 的兜底不该冒出画图/Word（那是比资源管理器多一堆不相干项的来源）"""
    text = open_with._windows_fallback(".txt")
    assert "notepad.exe" in text
    assert not any(e in text for e in ("mspaint.exe", "winword.exe", "vlcrc.exe"))
    assert open_with._windows_fallback(".png") == open_with._WINDOWS_FALLBACK["image"]
    # 认不出的类型只给通用编辑器，不乱猜
    assert open_with._windows_fallback(".qqq") == ("notepad.exe", "code.exe")


# ---------------------------------------------------------------- Linux 解析

def test_parse_desktop_file_reads_only_desktop_entry_section():
    entry = open_with._parse_desktop_file(
        "[Desktop Entry]\nName=编辑器\nExec=editor %U\nMimeType=text/plain;\n"
        "[Desktop Action New]\nName=不该被读到\n")
    assert entry["Name"] == "编辑器"
    assert entry["Exec"] == "editor %U"
    assert entry["Name"] != "不该被读到"


def test_mime_matches_supports_exact_and_wildcard():
    assert open_with._mime_matches("text/plain;application/pdf", "text/plain")
    assert open_with._mime_matches("text/*", "text/markdown")
    assert not open_with._mime_matches("image/*", "text/plain")
    assert not open_with._mime_matches("text/plain", "")


def test_desktop_exec_argv_strips_field_codes_and_separator():
    assert open_with._desktop_exec_argv("editor --lang en -- %f") == [
        "editor", "--lang", "en"]


def test_builtin_topup_gate_is_one_rule_for_both_platforms():
    """「候选太少才补内置常用程序」这道门两端共用一份

    Windows 上早就有这道门（写死在 `_list_windows` 里），Linux 上原来是
    无条件追加；抽成 `needs_builtin_topup` 后两边不可能各自漂移。
    """
    assert open_with.needs_builtin_topup(0) is True
    assert open_with.needs_builtin_topup(open_with.FALLBACK_TOPUP_BELOW - 1) is True
    assert open_with.needs_builtin_topup(open_with.FALLBACK_TOPUP_BELOW) is False
    assert open_with.needs_builtin_topup(open_with.MAX_ENTRIES) is False


# ---------------------------------------------------------------- list_apps 护栏

def test_list_apps_caches_per_extension_until_ttl_expires(monkeypatch):
    calls = []

    def fake(ext, *a):
        calls.append(ext)
        return [_app("A", "A.exe")]

    monkeypatch.setattr(open_with, _CURRENT_LIST_FUNC, fake)
    assert len(open_with.list_apps(r"C:\d\one.txt")) == 1
    assert len(open_with.list_apps(r"C:\d\two.txt")) == 1
    assert calls == [".txt"], "同扩展名应命中 TTL 缓存，只枚举一次"

    assert len(open_with.list_apps(r"C:\d\one.md")) == 1
    assert calls == [".txt", ".md"], "不同扩展名不能共用缓存"

    stamp = open_with._cache[".txt"][0]
    open_with._cache[".txt"] = (stamp - open_with.CACHE_TTL - 1,
                               [_app("过期", "old.exe")])
    assert open_with.list_apps(r"C:\d\one.txt")[0].name == "A"
    assert calls == [".txt", ".md", ".txt"], "超过 TTL 必须重新枚举"


def test_list_apps_dedupes_by_exe_and_caps_entries(monkeypatch):
    many = [_app(f"名{i}", f"C:\\a{i}.exe") for i in range(open_with.MAX_ENTRIES + 6)]
    # 同一个程序常以 ProgID / Applications / App Paths 三种身份出现（大小写还不同）
    dup = _app("重复项", "C:\\a0.EXE", source="apppaths")
    monkeypatch.setattr(open_with, _CURRENT_LIST_FUNC,
                        lambda ext, *a: many + [dup])
    got = open_with.list_apps("x.bin")
    assert len(got) == open_with.MAX_ENTRIES
    assert sum(1 for a in got if a.name == "名0") == 1, "同一 exe 只能留一项"
    assert [a.name for a in got] == [f"名{i}" for i in range(open_with.MAX_ENTRIES)]


def test_list_apps_swallows_enumeration_failure(monkeypatch):
    def boom(ext, *a):
        raise OSError("注册表读不了")

    monkeypatch.setattr(open_with, _CURRENT_LIST_FUNC, boom)
    assert open_with.list_apps("any.xyz") == []      # 不抛异常，只是没候选


# ---------------------------------------------------------------- Linux 集成


def test_linux_lists_desktop_entries_matching_mime(tmp_path, monkeypatch):
    apps_dir = tmp_path / "share" / "applications"
    apps_dir.mkdir(parents=True)
    (apps_dir / "editor.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=文本编辑器\n"
        f"Exec={(apps_dir / 'editor.bin')} %U\nMimeType=text/plain;\n",
        encoding="utf-8")
    (apps_dir / "hidden.desktop").write_text(
        "[Desktop Entry]\nType=Application\nNoDisplay=true\nName=藏起来\n"
        "MimeType=text/plain;\n", encoding="utf-8")
    (apps_dir / "other.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=图片查看\nMimeType=image/png;\n"
        f"Exec={apps_dir / 'view.bin'}\n", encoding="utf-8")
    exe = apps_dir / "editor.bin"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)

    monkeypatch.setattr(open_with, "_linux_data_dirs",
                        lambda: [str(tmp_path / "share")])
    # 内置兜底候选在真机上是命中的（gnome-text-editor / mousepad 确实装了），
    # 这条用例要盯的是 `.desktop` 的筛选，把兜底清空再说
    monkeypatch.setattr("config.file_associations._LINUX_APP_CANDIDATES", {})
    names = [a.name for a in open_with._list_linux(".txt", "note.txt")]
    assert names == ["文本编辑器"], "只列 MIME 匹配且可见的项"


@pytest.mark.skipif(sys.platform == "win32", reason="走的是 Linux 的 .desktop 枚举分支")
def test_linux_skips_builtin_topup_once_desktop_entries_are_enough(tmp_path, monkeypatch):
    """`.desktop` 已给出足够候选时不再补内置项（Linux 真机跑出来的差异）

    一台富桌面上 `text/plain` 能匹配到一堆 `.desktop`，旧代码还在后面接着追
    gedit/mousepad/kate …；这些程序的本机名字只有内置列表知道，列出来就是一屏
    不相干项。Windows 上不会这样，所以这道门得两端共用。
    """
    apps_dir = tmp_path / "share" / "applications"
    apps_dir.mkdir(parents=True)
    exe = tmp_path / "e.bin"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)

    def write_entries(n):
        for old in apps_dir.glob("*.desktop"):
            old.unlink()
        for i in range(n):
            (apps_dir / f"e{i}.desktop").write_text(
                f"[Desktop Entry]\nType=Application\nName=编辑器{i}\n"
                f"Exec={exe}\nMimeType=text/plain;\n", encoding="utf-8")

    def fake_which(name, *a, **k):
        if name == "builtin-editor":
            return str(exe)
        return name if os.path.isabs(name) and os.path.exists(name) else None

    monkeypatch.setattr(open_with, "_linux_data_dirs",
                        lambda: [str(tmp_path / "share")])
    monkeypatch.setattr(open_with.shutil, "which", fake_which)
    monkeypatch.setattr("config.file_associations._LINUX_APP_CANDIDATES",
                        {".txt": ["builtin-editor"]})

    write_entries(open_with.FALLBACK_TOPUP_BELOW)
    sources = [a.source for a in open_with._list_linux(".txt", "note.txt")]
    assert sources == ["desktop"] * open_with.FALLBACK_TOPUP_BELOW, "够数了还补内置项"

    # 删到门槛以下：没装桌面集成时仍然要有东西可选，兜底必须回来
    write_entries(open_with.FALLBACK_TOPUP_BELOW - 1)
    sources = [a.source for a in open_with._list_linux(".txt", "note.txt")]
    assert sources == ["desktop"] * (open_with.FALLBACK_TOPUP_BELOW - 1) + ["builtin"], \
        "候选不足时兜底没回来（或回来后顺序变了）"


# ---------------------------------------------------------------- Windows 真注册表冒烟

@pytest.mark.skipif(sys.platform != "win32", reason="只有 Windows 有注册表")
def test_windows_real_registry_candidates_are_launchable():
    apps = open_with.list_apps(r"C:\Any\readme.txt")
    assert apps, "记事本必然在，.txt 不该空"
    assert len(apps) <= open_with.MAX_ENTRIES
    assert all(os.path.exists(a.exe) for a in apps), "候选的 exe 必须真实存在"
    assert len({a.name for a in apps}) == len(apps), \
        "同名候选会让用户无从选起（ProgID 默认值就是文档类型描述，会撞名）"


@pytest.mark.skipif(sys.platform != "win32", reason="只有 Windows 有注册表")
def test_windows_display_name_is_not_the_doc_type_description():
    progid = open_with._win_read(open_with.winreg.HKEY_CLASSES_ROOT, ".txt")
    if not progid:
        pytest.skip("这台机器没注册 .txt 的 ProgID")
    desc = open_with._win_read(open_with.winreg.HKEY_CLASSES_ROOT, progid)
    has_real_name = open_with._win_read(
        open_with.winreg.HKEY_CLASSES_ROOT,
        rf"{progid}\Application\ApplicationName")
    name = open_with._win_name_for(progid, r"C:\Windows\System32\notepad.exe")
    assert name
    if desc and not has_real_name:
        assert name != desc, "没有 ApplicationName 时用文档类型描述当程序名是错的"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 命令行规则")
def test_win_app_from_command_requires_existing_exe():
    assert open_with._win_app_from_command(
        r'"C:\不存在\x.exe" "%1"', "progid", "No.ProgID") is None
    app = open_with._win_app_from_command(
        f'"{sys.executable}" "%1" --wait', "default")
    assert app.exe == sys.executable
    # 占位符先原样留着（记录注册表里真实命令行），到 argv_for 才换上目标路径
    assert app.args == ("%1", "--wait")
    assert app.name == os.path.splitext(os.path.basename(sys.executable))[0]


# ---------------------------------------------------------------- 窗格接线

@pytest.fixture
def pane(qtbot, tmp_path):
    from core.pane import Pane

    (tmp_path / "note.txt").write_text("hi")
    (tmp_path / "sub").mkdir()
    p = Pane("t_open_with", start_path=str(tmp_path))
    qtbot.addWidget(p)
    _wait_rows(qtbot, p.tree_view, 2)
    p.file_associations = None          # 默认：没记过任何关联
    yield p
    p.deleteLater()


def _wait_rows(qtbot, tv, expected):
    proxy = tv.model()

    def _ready():
        dir_pool().waitForDone(50)
        return proxy.rowCount(tv.rootIndex()) >= expected

    qtbot.waitUntil(_ready, timeout=5000)


def _fill(pane, path, monkeypatch, apps):
    """建子菜单 + 触发 aboutToShow，返回 (父菜单, 子菜单, 枚举次数列表)

    父菜单必须跟着一起返回并握在调用方手里：`menu` 是局部变量，`_fill` 一返回
    它就被 GC，而子菜单是它的 Qt 子对象 —— C++ 侧先被删，下一行读它就炸。
    """
    from PyQt6.QtWidgets import QMenu

    calls = []
    monkeypatch.setattr(open_with, "list_apps",
                        lambda p: (calls.append(p), list(apps))[1])
    menu = QMenu()
    submenu = pane._add_open_with_submenu(menu, path)
    submenu.aboutToShow.emit()
    return menu, submenu, calls


def _labels(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_submenu_defers_enumeration_until_about_to_show(pane, tmp_path, monkeypatch):
    """构造右键菜单时不枚举：多数时候用户根本不展开这一层。"""
    from PyQt6.QtWidgets import QMenu

    calls = []
    monkeypatch.setattr(open_with, "list_apps",
                        lambda p: (calls.append(p), [_app("记事本", "notepad.exe")])[1])
    menu = QMenu()
    submenu = pane._add_open_with_submenu(menu, str(tmp_path / "note.txt"))
    assert calls == [], "构造菜单时就枚举是白读注册表"
    assert submenu.actions() == []

    submenu.aboutToShow.emit()
    assert calls == [str(tmp_path / "note.txt")]
    assert _labels(submenu)[0] == "记事本"


def test_submenu_marks_default_and_offers_more_apps(pane, tmp_path, monkeypatch):
    default = _app("记事本", "C:\\Windows\\notepad.exe", source="default")
    other = _app("VS Code", "C:\\code\\Code.exe")
    by_exe = _app("记事程序", "D:\\tools\\np.exe")
    menu, submenu, _ = _fill(pane, str(tmp_path / "note.txt"), monkeypatch,
                             [default, other, by_exe])
    labels = _labels(submenu)
    assert labels[0] == "记事本（默认）"
    assert "VS Code" in labels
    tail = "选择其它应用…" if open_with.has_system_dialog() else "选择其它应用并设为默认…"
    assert labels[-1] == tail


def test_submenu_marks_the_association_table_default(pane, tmp_path, monkeypatch):
    """「（默认）」的依据除注册表 default 外还有本仓关联表里记的程序"""
    from config.file_associations import FileAssociations

    assoc = FileAssociations(config_dir=str(tmp_path / "cfg"))
    assoc.set_association(".txt", r"D:\tools\np.exe")
    pane.file_associations = assoc

    menu, submenu, _ = _fill(pane, str(tmp_path / "note.txt"), monkeypatch,
                             [_app("记事本", "C:\\Windows\\notepad.exe"),
                              _app("记事程序", r"D:\tools\np.exe")])
    assert menu                      # 父菜单必须被握住，否则子菜单会被连带删掉
    # 本仓关联表里记的程序也算默认（菜单里标出来，与用户之前的选择一致）
    assert _labels(submenu)[0] == "记事本"
    assert _labels(submenu)[1] == "记事程序（默认）"


def test_picking_an_entry_launches_it_without_touching_associations(
        pane, tmp_path, monkeypatch):
    from config.file_associations import FileAssociations

    assoc = FileAssociations(config_dir=str(tmp_path / "cfg2"))
    pane.file_associations = assoc
    before = dict(assoc.associations)
    apps = [_app("记事本", "C:\\Windows\\notepad.exe", source="default"),
            _app("VS Code", "C:\\code\\Code.exe")]
    launched = []
    monkeypatch.setattr(open_with, "launch",
                        lambda a, p: launched.append((a.name, p)) or (True, ""))
    menu, submenu, _ = _fill(pane, str(tmp_path / "note.txt"), monkeypatch, apps)

    target = next(a for a in submenu.actions() if a.text() == "VS Code")
    target.trigger()
    assert launched == [("VS Code", str(tmp_path / "note.txt"))]
    assert assoc.associations == before, \
        "菜单里选一次只改「这次用什么打开」，不改默认"


def test_enumeration_failure_keeps_the_menu_usable(pane, tmp_path, monkeypatch):
    """枚举炸了也不能炸掉右键菜单 —— 至少还剩系统对话框那一项"""
    def boom(_path):
        raise RuntimeError("注册表炸了")

    monkeypatch.setattr(open_with, "list_apps", boom)
    from PyQt6.QtWidgets import QMenu

    menu = QMenu()
    submenu = pane._add_open_with_submenu(menu, str(tmp_path / "note.txt"))
    submenu.aboutToShow.emit()                    # 不抛异常
    assert _labels(submenu), "没有候选时也要有可用项（选择其它应用）"


def test_no_candidates_on_linux_still_shows_disabled_hint(pane, tmp_path, monkeypatch):
    monkeypatch.setattr(open_with, "has_system_dialog", lambda: False)
    menu, submenu, _ = _fill(pane, str(tmp_path / "note.txt"), monkeypatch, [])
    labels = _labels(submenu)
    assert labels == ["没有可用的应用程序", "选择其它应用并设为默认…"]
    assert submenu.actions()[0].isEnabled() is False


def test_context_menu_has_open_with_only_for_a_single_file(
        pane, tmp_path, monkeypatch):
    """单选文件才有「打开方式」；目录与多选不提供"""
    from PyQt6.QtWidgets import QMenu
    from PyQt6.QtCore import QItemSelectionModel

    submenu_titles = lambda menu: [m.title() for m in menu.findChildren(QMenu)]
    captured = {}
    monkeypatch.setattr(QMenu, "exec",
                        lambda self, *a, **k: captured.__setitem__("menu", self) or 0)

    def selected_one():
        tv = pane.tree_view
        idx = tv.model().index(0, 0, tv.rootIndex())
        tv.selectionModel().select(
            idx, QItemSelectionModel.SelectionFlag.ClearAndSelect |
            QItemSelectionModel.SelectionFlag.Rows)
        return idx

    selected_one()
    note = str(tmp_path / "note.txt")
    monkeypatch.setattr(pane, "_paths_from_selection", lambda: [note])
    pane.show_context_menu(pane.tree_view.viewport().rect().center())
    assert any(t.startswith("打开方式") for t in submenu_titles(captured["menu"]))

    monkeypatch.setattr(pane, "_paths_from_selection",
                        lambda: [str(tmp_path / "sub")])
    pane.show_context_menu(pane.tree_view.viewport().rect().center())
    assert not any(t.startswith("打开方式") for t in submenu_titles(captured["menu"])), \
        "目录没有「打开方式」"

    monkeypatch.setattr(pane, "_paths_from_selection", lambda: [note, note])
    pane.show_context_menu(pane.tree_view.viewport().rect().center())
    assert not any(t.startswith("打开方式") for t in submenu_titles(captured["menu"])), \
        "多选暂不提供「打开方式」"


def test_pick_app_for_opens_once_and_records_default(pane, tmp_path, monkeypatch):
    """没有系统对话框的平台：挑程序 → 打开一次 → 记进关联表并清候选缓存"""
    from PyQt6.QtWidgets import QFileDialog
    from config.file_associations import FileAssociations

    exe = tmp_path / "myeditor.exe"
    exe.write_text("fake")
    target = tmp_path / "doc.md"
    target.write_text("x")

    assoc = FileAssociations(config_dir=str(tmp_path / "cfg3"))
    pane.file_associations = assoc
    launched = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(exe), "")))
    monkeypatch.setattr(open_with, "launch",
                        lambda a, p: launched.append((a.name, p)) or (True, ""))
    open_with._cache[".md"] = (time.monotonic(), [])       # 脏缓存，必须被清掉

    pane._pick_app_for(str(target))

    assert launched == [(exe.stem, str(target))]
    assert assoc.get_association(str(target))["app"] == str(exe)
    assert ".md" not in open_with._cache, "默认变了，缓存里那份旧标记要作废"


def test_pick_app_for_cancelled_does_nothing(pane, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from config.file_associations import FileAssociations

    assoc = FileAssociations(config_dir=str(tmp_path / "cfg4"))
    pane.file_associations = assoc
    before = dict(assoc.associations)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    launched = []
    monkeypatch.setattr(open_with, "launch",
                        lambda a, p: launched.append(a) or (True, ""))

    pane._pick_app_for(str(tmp_path / "doc.md"))
    assert launched == []
    assert assoc.associations == before
