"""
Pan4dex 万格 — 更新对话框（发现新版本 / 下载进度 / 安装确认）

状态机（详见 `docs/update.md` 5.3）：

    发现新版本 → 下载中 → 下载完成 → 安装并重启
                     ↘ 校验失败（重试）      ↘ 安装准备失败（手动下载）

启动检查用的对话框是非模态的，不阻塞继续使用；帮助菜单手动检查是模态的。
发布说明只当纯文本显示，不渲染 HTML。
"""
import logging
import sys
import time

from PyQt6.QtCore import QSettings, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QVBoxLayout,
)

from config.app_config import APP_NAME, ORG_NAME, VERSION
from core import updater
from core.lifecycle import call_later
from core.update_runner import UpdateRunner

logger = logging.getLogger("pan4dex.update_dialog")

_PHASE_FOUND = "found"
_PHASE_DOWNLOADING = "downloading"
_PHASE_READY = "ready"
_PHASE_ERROR = "error"
_PHASE_INSTALLING = "installing"


def fmt_size(value: float) -> str:
    """人类可读大小（与进度对话框/服务器管理页保持同一套单位）"""
    units = ("B", "KB", "MB", "GB")
    for index, unit in enumerate(units):
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if index == 0 else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class UpdateDialog(QDialog):
    """更新对话框；`manual=True` 时模态、不显示「跳过此版本」"""

    def __init__(self, parent, info: updater.UpdateInfo,
                 current_version: str = VERSION,
                 manual: bool = False,
                 auto_download: bool = False,
                 auto_install: bool = False,
                 server_url: str = ""):
        super().__init__(parent)
        self.info = info
        self.current_version = current_version
        self.manual = manual
        self.auto_download = auto_download
        self.auto_install = auto_install and auto_download
        self.server_url = server_url

        self._phase = _PHASE_FOUND
        self._started = False
        self._downloaded = None
        self._dest_dir = None
        self._speed = None
        self._last_time = None
        self._last_bytes = 0
        self._download_only = False
        self._error_retry = False
        self._error_open = None                 # "page" / "dir" / None

        self.setWindowTitle("软件更新")
        self.setMinimumWidth(560)
        self.setModal(manual)

        self._runner = UpdateRunner(self)
        self._runner.download_progress.connect(self._on_progress)
        self._runner.download_done.connect(self._on_download_done)
        self._runner.download_cancelled.connect(self._on_download_cancelled)

        self._build_ui()
        self._show_found()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        self.version_label = QLabel()
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(self.version_label.font().pointSize())
        self.version_label.setFont(mono)
        self.version_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.version_label)

        self.notes_caption = QLabel("发布说明")
        layout.addWidget(self.notes_caption)
        self.notes_view = QPlainTextEdit()
        self.notes_view.setReadOnly(True)
        self.notes_view.setPlainText(self.info.notes)
        self.notes_view.setMaximumHeight(220)
        self.notes_view.setMinimumHeight(80)
        layout.addWidget(self.notes_view)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.detail_label = QLabel()
        self.detail_label.setFont(mono)
        self.detail_label.setWordWrap(True)
        self.detail_label.hide()
        layout.addWidget(self.detail_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.primary_btn = QPushButton("立即更新")
        self.primary_btn.setDefault(True)
        self.primary_btn.clicked.connect(self._on_primary)
        buttons.addWidget(self.primary_btn)
        self.download_btn = QPushButton("只下载")
        self.download_btn.clicked.connect(self._on_download_only)
        buttons.addWidget(self.download_btn)
        self.secondary_btn = QPushButton("稍后")
        self.secondary_btn.clicked.connect(self._on_secondary)
        buttons.addWidget(self.secondary_btn)
        self.skip_btn = QPushButton("跳过此版本")
        self.skip_btn.clicked.connect(self._on_skip)
        buttons.addWidget(self.skip_btn)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

    def _set_buttons(self, *, primary=None, secondary=None, skip=False,
                     close=True, close_text="关闭", download=False):
        if primary:
            self.primary_btn.setText(primary[0])
            self.primary_btn.show()
        else:
            self.primary_btn.hide()
        self.download_btn.setVisible(bool(download))
        if secondary:
            self.secondary_btn.setText(secondary[0])
            self.secondary_btn.show()
        else:
            self.secondary_btn.hide()
        self.skip_btn.setVisible(bool(skip) and not self.manual)
        self.close_btn.setVisible(close)
        self.close_btn.setText(close_text)

    def _show_found(self):
        self._phase = _PHASE_FOUND
        self._download_only = False
        self.title_label.setText("发现新版本")
        self.version_label.setText(f"{self.current_version}  →  {self.info.version}")
        self.status_label.setText(
            f"安装包 {fmt_size(self.info.size)}，下载后会自动校验 SHA-256。")
        has_notes = bool(self.info.notes.strip())
        self.notes_caption.setVisible(has_notes)
        self.notes_view.setVisible(has_notes)
        self.progress.hide()
        self.detail_label.hide()
        if updater.can_install():
            self._set_buttons(primary=("立即更新",), secondary=("稍后",),
                              skip=True, close=False, download=True)
        else:
            # 源码运行模式：允许查看更新，但不替换开发环境
            self._set_buttons(primary=None, secondary=("打开下载页",), skip=True)
            self.status_label.setText(
                "当前是源码运行模式，不会自动安装。\n"
                "可以打开下载页手动获取安装包。")

    def _show_downloading(self):
        self._phase = _PHASE_DOWNLOADING
        self.title_label.setText("正在下载更新")
        self.notes_caption.hide()
        self.notes_view.hide()
        self.progress.setRange(0, 0 if self.info.size <= 0 else 100)
        self.progress.setValue(0)
        self.progress.show()
        self.detail_label.show()
        self.detail_label.setText(f"0 B / {fmt_size(self.info.size)}")
        self.status_label.setText("正在连接更新服务器…")
        self._set_buttons(primary=None, secondary=None, skip=False,
                          close=True, close_text="取消下载")

    def _show_ready(self):
        self._phase = _PHASE_READY
        self.title_label.setText("下载完成")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.show()
        self.detail_label.setText(
            f"{fmt_size(self.info.size)} · SHA-256 校验通过")
        if self._download_only:
            self.status_label.setText(
                f"更新包已下载到：{self._downloaded}\n"
                "可现在安装，也可保持现状——下次启动提示时校验通过的包直接复用。")
            self._set_buttons(primary=("立即安装并重启",),
                              secondary=("打开下载目录",),
                              skip=False, close=True, close_text="稍后")
        else:
            self.status_label.setText("新版本已下载完成，安装过程中 Pan4dex 会重启。")
            self._set_buttons(primary=("立即安装并重启",), secondary=("稍后",),
                              skip=False, close=False)

    def _show_error(self, message: str, *, retry: bool, open_page: bool = False,
                    open_dir: bool = False):
        self._phase = _PHASE_ERROR
        self._error_retry = retry
        self._error_open = "page" if open_page else ("dir" if open_dir else None)
        self.title_label.setText("更新未完成")
        self.progress.hide()
        self.detail_label.hide()
        self.status_label.setText(message)
        secondary = None
        if open_page:
            secondary = ("打开下载页",)
        elif open_dir:
            secondary = ("打开下载目录",)
        self._set_buttons(primary=("重试",) if retry else None,
                          secondary=secondary, skip=False)

    # -------------------------------------------------------------- 动作

    def _on_primary(self):
        if self._phase == _PHASE_FOUND:
            self._start_download()
        elif self._phase == _PHASE_READY:
            self._install()
        elif self._phase == _PHASE_ERROR:
            if self._error_retry:
                self._start_download()
            else:
                self.accept()

    def _on_secondary(self):
        if self._phase == _PHASE_FOUND:
            if updater.can_install():
                self.reject()                   # 稍后：下次启动仍提示
            else:
                self._open_download_page()      # 源码模式只能手动下载
        elif self._phase == _PHASE_READY:
            if self._download_only:
                self._open_download_dir()
            else:
                self.reject()                   # 已下载的文件保留，下次可复用
        elif self._phase == _PHASE_ERROR:
            if self._error_open == "dir":
                self._open_download_dir()
            else:
                self._open_download_page()

    def _on_download_only(self):
        self._download_only = True
        self._start_download()

    def _on_skip(self):
        QSettings(ORG_NAME, APP_NAME).setValue(
            "update/skipped_version", self.info.version)
        logger.info("用户跳过版本 %s", self.info.version)
        self.reject()

    def _open_download_page(self):
        """发布页不可用（老服务器没填 download_url）时退回打开下载目录"""
        if self.info.download_url:
            QDesktopServices.openUrl(QUrl(self.info.download_url))
        else:
            self._open_download_dir()

    def _open_download_dir(self):
        folder = self._dest_dir or updater.default_download_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ---------------------------------------------------------- 下载

    def _download_dir(self):
        """Windows 放缓存目录；Linux 放目标同目录，才能原子替换"""
        if sys.platform == "win32" or not updater.can_install():
            return updater.default_download_dir()
        target = updater.linux_target()
        if target.is_file() and updater.can_write_dir(target.parent):
            return target.parent
        return updater.default_download_dir()

    def _start_download(self):
        self._dest_dir = self._download_dir()
        self._speed = None
        self._last_time = None
        self._last_bytes = 0
        existing = self._dest_dir / self.info.filename
        if existing.is_file() and updater.verify_local_file(existing, self.info):
            logger.info("复用已下载的更新包: %s", existing)
            self._on_download_done(existing, "")
            return
        self._show_downloading()
        if not self._runner.download(self.info, self._dest_dir):
            self._show_error("已有下载任务在进行，请稍候。", retry=True)

    def _on_progress(self, done: int, total: int):
        if self._phase != _PHASE_DOWNLOADING:
            return
        total = total or self.info.size
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(done * 100 / total)))
        now = time.monotonic()
        if self._last_time is None:
            self._last_time, self._last_bytes = now, done
        elif now - self._last_time >= 0.3:
            instant = (done - self._last_bytes) / max(now - self._last_time, 1e-6)
            self._speed = instant if self._speed is None else \
                self._speed * 0.6 + instant * 0.4
            self._last_time, self._last_bytes = now, done
        speed = f" · {fmt_size(self._speed)}/s" if self._speed else ""
        self.detail_label.setText(
            f"{fmt_size(done)} / {fmt_size(total)}{speed}")
        self.status_label.setText("正在下载更新…")

    def _on_download_done(self, path, error: str):
        if error:
            self._show_error(f"{error}\n\n可以重试；下载失败不会影响当前版本。",
                             retry=True)
            return
        self._downloaded = path
        self._show_ready()
        if self.auto_install and not self._download_only:
            self.status_label.setText("下载完成，正在安装并重启…")
            call_later(self, 800, self._install)

    def _on_download_cancelled(self):
        if self._downloaded is not None:
            self._show_ready()
        else:
            self._show_found()

    # ---------------------------------------------------------- 安装

    def _install(self):
        if self._downloaded is None:
            self._show_error("没有可安装的更新包，请重新下载。", retry=True)
            return
        if not updater.can_install():
            self._show_error(
                "当前是源码运行模式，不能自动安装。\n"
                "请从下载页获取安装包，或手动替换可执行文件。",
                retry=False, open_page=True)
            return
        self._phase = _PHASE_INSTALLING
        self.title_label.setText("正在安装更新")
        self.status_label.setText("正在准备安装，完成后 Pan4dex 会自动重启…")
        self._set_buttons(primary=None, secondary=None, skip=False, close=False)
        self.progress.show()
        try:
            if sys.platform == "win32":
                script, _job = updater.prepare_windows_install(
                    self._downloaded, self.info.version, self.current_version)
                updater.launch_windows_installer(script)
            else:
                target = updater.linux_target()
                if not updater.can_write_dir(target.parent):
                    self._show_manual_install(target)
                    return
                updater.apply_linux_update(self._downloaded, target, launch=True)
        except updater.InstallError as exc:
            logger.warning("更新安装准备失败: %s", exc)
            self._show_error(f"{exc}\n\n当前版本未受影响，可继续使用。",
                             retry=False, open_page=True)
            return
        except Exception as exc:
            logger.exception("更新安装失败")
            self._show_error(f"安装失败: {exc}\n\n当前版本未受影响。",
                             retry=False, open_page=True)
            return
        self.status_label.setText("新版本即将启动，当前窗口会关闭…")
        QApplication.processEvents()
        # 手动「检查更新」打开的本对话框是模态 exec()：在嵌套事件循环里裸调
        # quit() 退不出去，窗口会一直停在更新界面（安装脚本等满超时后替换失败
        # 回滚）。先 accept() 让嵌套循环返回，再退出应用；非模态路径无副作用。
        self.accept()
        QApplication.quit()

    def _show_manual_install(self, target):
        """Linux 安装目录不可写：给出需要管理员权限的手动命令"""
        command = updater.linux_manual_command(self._downloaded, target)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("需要手动安装")
        box.setText("安装目录不可写，无法自动替换。")
        box.setInformativeText(
            f"更新包已下载到：\n{self._downloaded}\n\n"
            f"请在终端执行：\n{command}\n\n"
            "然后重新启动 Pan4dex。")
        copy_btn = box.addButton("复制命令", QMessageBox.ButtonRole.ActionRole)
        box.addButton("关闭", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is copy_btn:
            QApplication.clipboard().setText(command)
        self._show_error(
            "安装目录不可写，已保留下载的更新包。\n"
            f"手动安装命令：{command}",
            retry=False, open_dir=True)

    # ---------------------------------------------------------- 生命周期

    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = True
            if self.auto_download and self._phase == _PHASE_FOUND:
                call_later(self, 0, self._start_download)

    def closeEvent(self, event):
        if self._phase == _PHASE_DOWNLOADING:
            self._runner.cancel()
        super().closeEvent(event)

    def reject(self):
        if self._phase == _PHASE_INSTALLING:
            return                              # 安装/重启过程中不允许关掉对话框
        if self._phase == _PHASE_DOWNLOADING:
            self._runner.cancel()
        super().reject()
