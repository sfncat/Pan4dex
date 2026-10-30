"""
Pan4dex 万格 — 更新 UI 的回归测试（离屏）

对话框状态机（发现/下载/校验失败/仅启动检查可跳过）、设置页「更新」标签、
帮助菜单入口，以及检查结果的跳过逻辑。不连真实更新服务器。
"""
import sys
from pathlib import Path

import pytest
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDialog

from core import updater
from core.updater import UpdateInfo


def _info(**overrides) -> UpdateInfo:
    data = dict(
        platform=updater.current_platform(),
        version="1.9.028",
        filename="pan4dex-1.9.028.zip",
        size=1024,
        sha256="a" * 64,
        download_url="http://192.168.5.230:23011/download/windows/pan4dex-1.9.028.zip",
        notes="修复若干问题\n新增更新功能",
        published_at="2026-10-30T00:00:00Z",
    )
    data.update(overrides)
    return UpdateInfo(**data)


def _make_dialog(qtbot, *, manual=False, auto_download=False, auto_install=False):
    from widgets.update_dialog import UpdateDialog
    dialog = UpdateDialog(None, _info(), "1.9.027", manual=manual,
                          auto_download=auto_download,
                          auto_install=auto_install,
                          server_url="http://192.168.5.230:23011")
    qtbot.addWidget(dialog)
    return dialog


# ------------------------------------------------------------------ 对话框


def test_dialog_found_state(qtbot):
    dialog = _make_dialog(qtbot)
    assert "发现新版本" in dialog.title_label.text()
    assert dialog.version_label.text() == "1.9.027  →  1.9.028"
    assert "修复若干问题" in dialog.notes_view.toPlainText()
    # 源码运行（未打包）：不提供自动安装
    assert not updater.can_install()
    assert dialog.primary_btn.isHidden()
    assert dialog.secondary_btn.text() == "打开下载页"
    assert not dialog.skip_btn.isHidden()
    dialog.reject()


def test_dialog_source_mode_secondary_opens_page(qtbot):
    """源码模式下「打开下载页」不能当成「稍后」直接关掉"""
    dialog = _make_dialog(qtbot)
    opened = []
    dialog._open_download_page = lambda: opened.append("page")
    dialog._on_secondary()
    assert opened == ["page"]
    assert dialog._phase == "found"
    dialog.reject()


def test_dialog_error_open_dir_button(qtbot):
    """提示「打开下载目录」时不能弹成下载页"""
    dialog = _make_dialog(qtbot)
    opened = []
    dialog._open_download_page = lambda: opened.append("page")
    dialog._open_download_dir = lambda: opened.append("dir")
    dialog._show_error("安装目录不可写", retry=False, open_dir=True)
    dialog._on_secondary()
    assert opened == ["dir"]
    dialog.reject()


def test_dialog_manual_check_has_no_skip(qtbot):
    dialog = _make_dialog(qtbot, manual=True)
    assert dialog.skip_btn.isHidden()
    assert dialog.isModal()
    dialog.reject()


def test_dialog_skip_writes_version(qtbot, monkeypatch):
    written = {}

    class FakeSettings:
        def __init__(self, *args):
            pass

        def setValue(self, key, value):
            written[key] = value

    from widgets import update_dialog as module
    monkeypatch.setattr(module, "QSettings", FakeSettings)

    dialog = _make_dialog(qtbot)
    dialog._on_skip()
    assert written == {"update/skipped_version": "1.9.028"}


def test_dialog_download_success_shows_ready(qtbot, monkeypatch, tmp_path):
    def fake_download(info, dest_dir=None, progress=None, cancel=None, timeout=60):
        path = Path(dest_dir) / info.filename
        path.write_bytes(b"x" * info.size)
        if progress:
            progress(info.size // 2, info.size)
            progress(info.size, info.size)
        return path

    monkeypatch.setattr(updater, "download_update", fake_download)
    dialog = _make_dialog(qtbot)
    monkeypatch.setattr(dialog, "_download_dir", lambda: tmp_path)
    dialog._start_download()
    qtbot.waitUntil(lambda: dialog._phase == "ready", timeout=5000)
    assert dialog.progress.value() == 100
    assert "下载完成" in dialog.title_label.text()
    dialog.reject()


def test_dialog_hash_error_offers_retry(qtbot, monkeypatch, tmp_path):
    def bad_download(info, dest_dir=None, progress=None, cancel=None, timeout=60):
        raise updater.IntegrityError("SHA-256 校验不通过")

    monkeypatch.setattr(updater, "download_update", bad_download)
    dialog = _make_dialog(qtbot)
    monkeypatch.setattr(dialog, "_download_dir", lambda: tmp_path)
    dialog._start_download()
    qtbot.waitUntil(lambda: dialog._phase == "error", timeout=5000)
    assert "SHA-256" in dialog.status_label.text()
    assert dialog.primary_btn.text() == "重试"
    dialog.reject()


def test_dialog_reuses_verified_download(qtbot, monkeypatch, tmp_path):
    """「稍后」关掉后再提示：本地已下载且校验通过的不再重下"""
    existing = tmp_path / "pan4dex-1.9.028.zip"
    existing.write_bytes(b"x" * 1024)
    monkeypatch.setattr(updater, "verify_local_file", lambda path, info: True)
    monkeypatch.setattr(
        updater, "download_update",
        lambda *a, **k: pytest.fail("不应重复下载"))

    dialog = _make_dialog(qtbot)
    monkeypatch.setattr(dialog, "_download_dir", lambda: tmp_path)
    dialog._start_download()
    assert dialog._phase == "ready"
    dialog.reject()


def test_install_accepts_before_quit(qtbot, monkeypatch):
    """安装必须先 accept() 再退出应用：模态 exec() 的嵌套循环里裸调
    QApplication.quit() 退不出去，窗口会停在更新界面直到安装脚本超时回滚"""
    monkeypatch.setattr(updater, "can_install", lambda: True)
    monkeypatch.setattr(updater, "prepare_windows_install",
                        lambda *a, **k: ("C:/fake/install.ps1", None))
    monkeypatch.setattr(updater, "launch_windows_installer", lambda script: None)

    dialog = _make_dialog(qtbot, manual=True)
    dialog._downloaded = "C:/fake/p.zip"

    calls = []
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QApplication.quit",
        staticmethod(lambda: calls.append(
            ("quit", dialog.result()))))

    dialog._install()
    assert dialog._phase == "installing"
    # quit 执行时对话框已 accept（result == Accepted），嵌套循环能返回
    assert calls == [("quit", int(QDialog.DialogCode.Accepted))]


# ---------------------------------------------------------------- 设置页


def test_settings_dialog_update_tab(qapp, qtbot):
    from widgets.settings_dialog import SettingsDialog
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)
    values = dialog.get_settings()
    assert values["update_server_url"].startswith("http")
    assert isinstance(values["update_startup_check"], bool)
    assert isinstance(values["update_auto_download"], bool)
    assert values["update_auto_install"] is False
    # 自动安装依赖自动下载
    assert not dialog.update_auto_install_cb.isEnabled()
    dialog.update_auto_download_cb.setChecked(True)
    assert dialog.update_auto_install_cb.isEnabled()
    dialog.reject()


def test_settings_dialog_rejects_invalid_server(qapp, qtbot, monkeypatch):
    from widgets import settings_dialog as module
    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning",
                        lambda *args, **kwargs: warnings.append(args[2]))
    dialog = module.SettingsDialog()
    qtbot.addWidget(dialog)
    dialog.update_server_edit.setText("192.168.5.230:23011")
    dialog.accept()
    assert warnings and "http" in warnings[0]
    assert dialog.result() != dialog.DialogCode.Accepted
    dialog.reject()


# ------------------------------------------------------------ 主窗口入口


def test_help_menu_has_check_update(qapp, qtbot):
    from core.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    texts = [action.text() for action in win.findChildren(QAction)]
    assert any("检查更新" in text for text in texts)


def test_skipped_version_ignored_by_automatic_check(qapp, qtbot):
    from core.main_window import MainWindow

    class FakeSettings:
        def value(self, key, default=None, type=None):
            if key == "update/skipped_version":
                return "1.9.028"
            return default

        def setValue(self, key, value):
            pass

        def remove(self, key):
            pass

    win = MainWindow()
    qtbot.addWidget(win)
    win.settings = FakeSettings()
    opened = []
    win._show_update_dialog = lambda info, manual: opened.append((info, manual))
    win._update_check_manual = False
    win._on_update_checked(_info(), "")
    assert opened == []
    win._update_check_manual = True
    win._on_update_checked(_info(), "")
    assert len(opened) == 1 and opened[0][1] is True


def test_update_runner_emits_check_result(qapp, qtbot, monkeypatch):
    from core.update_runner import UpdateRunner
    info = _info()
    monkeypatch.setattr(updater, "check_for_update", lambda *a, **k: info)
    runner = UpdateRunner(None)
    with qtbot.waitSignal(runner.check_done, timeout=5000) as blocker:
        assert runner.check("http://192.168.5.230:23011", "1.9.027")
    assert blocker.args[0].version == "1.9.028"
    assert blocker.args[1] == ""
