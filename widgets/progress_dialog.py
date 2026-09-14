# -*- coding: utf-8 -*-
"""Pan4dex 万格 — 文件操作进度对话框

复制/移动/删除任务的独立进度窗口，对齐资源管理器体验：
百分比 + 字节数 + 速度 + 剩余时间 + 取消按钮 + 最小化到状态栏。
旧实现只有窗格底部 3px 进度条和状态栏文字，大文件传输期间
看不到速度、无处取消（FileOperations.cancel 早已实现但无 UI 入口）。
"""
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)


def _fmt_size(n: float) -> str:
    size = float(n)
    if size < 1024:
        return f"{int(size)} B"
    for unit in ('KB', 'MB', 'GB', 'TB'):
        size /= 1024.0
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def _fmt_eta(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} 秒"
    if s < 3600:
        return f"{s // 60} 分 {s % 60:02d} 秒"
    return f"{s // 3600} 小时 {s % 3600 // 60:02d} 分"


class FileProgressDialog(QDialog):
    """单个文件操作任务的进度对话框（非模态，不挡其他窗格操作）。

    用法::

        dlg = FileProgressDialog(parent, "正在复制")
        dlg.set_total_bytes(total)          # 可选；无字节统计时按文件数
        dlg.update_progress(percent, name, copied, total)
        dlg.cancel_requested.connect(ops.cancel)
        dlg.finish()                        # 操作结束（成功后调用）
    """

    cancel_requested = pyqtSignal()

    def __init__(self, parent, title: str = "正在复制"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint)
        self.setMinimumWidth(420)
        self._t0 = time.monotonic()
        self._cancelling = False
        self._finished = False
        self._last_ui_ts = 0.0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.file_label = QLabel("准备中…")
        self.file_label.setWordWrap(True)
        # 长文件名截断显示（保留尾部，扩展名可见）
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlags.NoTextInteraction)
        layout.addWidget(self.file_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        self.stat_label = QLabel("")
        self.stat_label.setStyleSheet("color: #9AA7B8;")
        layout.addWidget(self.stat_label)

        row = QHBoxLayout()
        row.addStretch()
        self.min_btn = QPushButton("最小化(&M)")
        self.min_btn.setToolTip("隐藏此窗口（状态栏进度条继续显示），点工具栏恢复")
        self.min_btn.clicked.connect(self.hide)
        row.addWidget(self.min_btn)
        self.cancel_btn = QPushButton("取 消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        row.addWidget(self.cancel_btn)
        layout.addLayout(row)

    def _on_cancel(self):
        if self._cancelling:
            return
        self._cancelling = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("正在取消…")
        self.stat_label.setText("等待当前文件段完成后取消…")
        self.cancel_requested.emit()

    def update_progress(self, percent: int, filename: str,
                        copied_bytes: int = 0, total_bytes: int = 0):
        """worker 线程经信号转发到主线程调用；0.2s 节流防事件风暴。"""
        now = time.monotonic()
        final = percent >= 100
        if not final and not self._cancelling and (now - self._last_ui_ts) < 0.2:
            return
        self._last_ui_ts = now
        name = filename or ""
        if len(name) > 70:
            name = name[:36] + '…' + name[-30:]
        self.file_label.setText(name)
        if total_bytes > 0:
            self.bar.setValue(min(100, max(self.bar.value(), int(percent))))
            elapsed = time.monotonic() - self._t0
            speed = copied_bytes / elapsed if elapsed > 0.2 else 0.0
            parts = [f"{_fmt_size(copied_bytes)} / {_fmt_size(total_bytes)}"
                     f"  ({self.bar.value()}%)"]
            if speed > 0:
                parts.append(f"速度 {_fmt_size(speed)}/s")
                remain = (total_bytes - copied_bytes) / speed
                parts.append(f"剩余 {_fmt_eta(remain)}")
            self.stat_label.setText("    ".join(parts))
        else:
            # 无字节统计（按文件数进度）
            self.bar.setValue(min(100, max(self.bar.value(), int(percent))))
            self.stat_label.setText(f"{percent}%")
        if percent >= 100 and self.isVisible():
            self.stat_label.setText(self.stat_label.text() + "    即将完成…")

    def mark_finished(self):
        """操作结束：取消按钮失效，允许关闭（调用方随后 close/删除）"""
        self._finished = True
        self.cancel_btn.setText("关闭")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.close)

    def closeEvent(self, event):
        # 操作进行中点 X 等同于最小化：不允许关掉唯一进度入口；
        # 已结束则正常关闭
        if not getattr(self, '_finished', False):
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)
