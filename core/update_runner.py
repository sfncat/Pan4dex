"""
Pan4dex 万格 — 更新检查 / 下载的后台线程封装

`core/updater.py` 是纯标准库的核心逻辑；本模块只做「丢到后台线程 → 信号回主线程」，
沿用 `core/file_op_runner.py` 的约定：信号接收者就是目标 QObject，宿主销毁时丢帧不崩。
"""
import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from core import updater

logger = logging.getLogger("pan4dex.update_runner")

__all__ = ["UpdateRunner"]


class UpdateRunner(QObject):
    """一个宿主对应一个运行器；同一时刻只跑一个检查或下载"""

    check_done = pyqtSignal(object, str)        # (UpdateInfo | None, 错误文本)
    download_progress = pyqtSignal(int, int)    # (已下载字节, 总字节)
    download_done = pyqtSignal(object, str)     # (下载文件 Path | None, 错误文本)
    download_cancelled = pyqtSignal()

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self._checking = False
        self._downloading = False
        self._cancel = None

    @property
    def busy(self) -> bool:
        return self._checking or self._downloading

    def check(self, server_url: str, current_version: str,
              platform: str | None = None) -> bool:
        """后台检查更新；返回 False 表示已有任务在跑"""
        if self._checking:
            return False
        self._checking = True

        def worker():
            info, error = None, ""
            try:
                info = updater.check_for_update(server_url, current_version, platform)
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                logger.warning("检查更新失败: %s", exc)
            finally:
                self._checking = False
            self._emit("check_done", info, error)

        threading.Thread(target=worker, daemon=True,
                         name="pan4dex-update-check").start()
        return True

    def download(self, info: updater.UpdateInfo,
                 dest_dir=None) -> bool:
        """后台下载并校验；进度与结果经信号回主线程"""
        if self._downloading:
            return False
        self._downloading = True
        cancel = threading.Event()
        self._cancel = cancel

        def worker():
            path, error, cancelled = None, "", False
            try:
                path = updater.download_update(
                    info, dest_dir=dest_dir, cancel=cancel,
                    progress=lambda done, total: self._emit(
                        "download_progress", int(done), int(total)))
            except updater.DownloadCancelled:
                cancelled = True
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                logger.warning("下载更新失败: %s", exc)
            finally:
                self._downloading = False
                self._cancel = None
            if cancelled:
                self._emit("download_cancelled")
            else:
                self._emit("download_done", path, error)

        threading.Thread(target=worker, daemon=True,
                         name="pan4dex-update-download").start()
        return True

    def cancel(self):
        if self._cancel is not None:
            self._cancel.set()

    def _emit(self, signal_name: str, *args):
        """宿主销毁后信号对象本身会抛 RuntimeError，丢一帧远好过崩溃"""
        try:
            getattr(self, signal_name).emit(*args)
        except RuntimeError:
            pass
