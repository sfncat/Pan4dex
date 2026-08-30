"""
Pan4dex 万格 — 时间戳转换工具
"""
import time
import calendar
from datetime import datetime, timezone, timedelta
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QTextEdit,
    QGroupBox, QGridLayout, QWidget, QApplication
)
from PyQt6.QtCore import Qt, QTimer


class TimestampToolDialog(QDialog):
    """时间戳转换对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("时间戳转换工具")
        self.setMinimumSize(550, 450)
        self.init_ui()
        self.update_current_time()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ── 当前时间 ──
        current_group = QGroupBox("当前时间")
        current_layout = QGridLayout(current_group)

        self.current_ts = QLineEdit()
        self.current_ts.setReadOnly(True)
        self.current_ts.setStyleSheet("font-family: Consolas, Monaco, monospace; font-size: 14px;")
        current_layout.addWidget(QLabel("Unix 时间戳:"), 0, 0)
        current_layout.addWidget(self.current_ts, 0, 1)

        self.current_utc = QLineEdit()
        self.current_utc.setReadOnly(True)
        self.current_utc.setStyleSheet("font-family: Consolas, Monaco, monospace; font-size: 14px;")
        current_layout.addWidget(QLabel("UTC 时间:"), 1, 0)
        current_layout.addWidget(self.current_utc, 1, 1)

        self.current_local = QLineEdit()
        self.current_local.setReadOnly(True)
        self.current_local.setStyleSheet("font-family: Consolas, Monaco, monospace; font-size: 14px;")
        current_layout.addWidget(QLabel("本地时间:"), 2, 0)
        current_layout.addWidget(self.current_local, 2, 1)

        layout.addWidget(current_group)

        # ── 时间戳 → 日期 ──
        ts_to_date_group = QGroupBox("时间戳 → 日期时间")
        ts_to_date_layout = QGridLayout(ts_to_date_group)

        ts_to_date_layout.addWidget(QLabel("时间戳:"), 0, 0)
        self.ts_input = QLineEdit()
        self.ts_input.setPlaceholderText("输入 Unix 时间戳（秒）或毫秒（13位）")
        self.ts_input.textChanged.connect(self.on_ts_changed)
        ts_to_date_layout.addWidget(self.ts_input, 0, 1)

        ts_to_date_layout.addWidget(QLabel("UTC:"), 1, 0)
        self.ts_utc_result = QLineEdit()
        self.ts_utc_result.setReadOnly(True)
        self.ts_utc_result.setStyleSheet("font-family: Consolas, Monaco, monospace;")
        ts_to_date_layout.addWidget(self.ts_utc_result, 1, 1)

        ts_to_date_layout.addWidget(QLabel("本地:"), 2, 0)
        self.ts_local_result = QLineEdit()
        self.ts_local_result.setReadOnly(True)
        self.ts_local_result.setStyleSheet("font-family: Consolas, Monaco, monospace;")
        ts_to_date_layout.addWidget(self.ts_local_result, 2, 1)

        ts_to_date_layout.addWidget(QLabel("相对:"), 3, 0)
        self.ts_relative = QLineEdit()
        self.ts_relative.setReadOnly(True)
        self.ts_relative.setStyleSheet("font-family: Consolas, Monaco, monospace; color: #2196F3;")
        ts_to_date_layout.addWidget(self.ts_relative, 3, 1)

        layout.addWidget(ts_to_date_group)

        # ── 日期 → 时间戳 ──
        date_to_ts_group = QGroupBox("日期时间 → 时间戳")
        date_to_ts_layout = QGridLayout(date_to_ts_group)

        date_to_ts_layout.addWidget(QLabel("格式:"), 0, 0)
        fmt_layout = QHBoxLayout()
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems([
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y年%m月%d日 %H:%M:%S",
        ])
        self.fmt_combo.setEditable(True)
        fmt_layout.addWidget(self.fmt_combo)

        self.now_btn = QPushButton("当前")
        self.now_btn.clicked.connect(self.fill_current_datetime)
        fmt_layout.addWidget(self.now_btn)
        date_to_ts_layout.addLayout(fmt_layout, 0, 1)

        date_to_ts_layout.addWidget(QLabel("日期:"), 1, 0)
        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("输入日期时间字符串")
        self.date_input.textChanged.connect(self.on_date_changed)
        date_to_ts_layout.addWidget(self.date_input, 1, 1)

        date_to_ts_layout.addWidget(QLabel("时间戳(秒):"), 2, 0)
        self.date_ts_result = QLineEdit()
        self.date_ts_result.setReadOnly(True)
        self.date_ts_result.setStyleSheet("font-family: Consolas, Monaco, monospace;")
        date_to_ts_layout.addWidget(self.date_ts_result, 2, 1)

        date_to_ts_layout.addWidget(QLabel("时间戳(毫秒):"), 3, 0)
        self.date_ts_ms_result = QLineEdit()
        self.date_ts_ms_result.setReadOnly(True)
        self.date_ts_result.setStyleSheet("font-family: Consolas, Monaco, monospace;")
        date_to_ts_layout.addWidget(self.date_ts_ms_result, 3, 1)

        layout.addWidget(date_to_ts_group)

        # ── 常用时间参考 ──
        ref_group = QGroupBox("常用参考")
        ref_layout = QVBoxLayout(ref_group)
        self.ref_text = QTextEdit()
        self.ref_text.setReadOnly(True)
        self.ref_text.setMaximumHeight(80)
        self.ref_text.setStyleSheet("font-family: Consolas, Monaco, monospace; font-size: 11px;")
        ref_layout.addWidget(self.ref_text)
        layout.addWidget(ref_group)

        # ── 按钮 ──
        btn_layout = QHBoxLayout()
        self.copy_ts_btn = QPushButton("复制时间戳")
        self.copy_ts_btn.clicked.connect(lambda: self.copy_to_clipboard(self.current_ts.text()))
        btn_layout.addWidget(self.copy_ts_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        # 定时器：每秒更新当前时间
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_current_time)
        self.timer.start(1000)

    def update_current_time(self):
        """更新当前时间显示"""
        now = time.time()
        self.current_ts.setText(f"{int(now)}  ({now:.3f})")

        dt_utc = datetime.fromtimestamp(now, tz=timezone.utc)
        self.current_utc.setText(dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC"))

        dt_local = datetime.fromtimestamp(now)
        self.current_local.setText(dt_local.strftime("%Y-%m-%d %H:%M:%S %Z"))

        # 更新参考
        refs = (
            f"0 → 1970-01-01 00:00:00 UTC    "
            f"86400 → 1天    "
            f"3600 → 1小时    "
            f"1000000000 → 2001-09-09    "
            f"1700000000 → 2023-11-14    "
            f"1800000000 → 2027-01-15"
        )
        self.ref_text.setPlainText(refs)

    def on_ts_changed(self):
        """时间戳输入变化时更新结果"""
        text = self.ts_input.text().strip()
        if not text:
            self.ts_utc_result.clear()
            self.ts_local_result.clear()
            self.ts_relative.clear()
            return

        try:
            ts = float(text)
            # 自动检测毫秒时间戳（13位）
            if ts > 1e12:
                ts = ts / 1000.0

            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_local = datetime.fromtimestamp(ts)

            self.ts_utc_result.setText(dt_utc.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC")
            self.ts_local_result.setText(dt_local.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " Local")

            # 相对时间
            now = time.time()
            diff = ts - now
            if abs(diff) < 60:
                rel = "刚刚" if abs(diff) < 1 else f"{abs(diff):.1f}秒{'前' if diff < 0 else '后'}"
            elif abs(diff) < 3600:
                rel = f"{abs(diff)/60:.1f}分钟{'前' if diff < 0 else '后'}"
            elif abs(diff) < 86400:
                rel = f"{abs(diff)/3600:.1f}小时{'前' if diff < 0 else '后'}"
            else:
                rel = f"{abs(diff)/86400:.1f}天{'前' if diff < 0 else '后'}"
            self.ts_relative.setText(rel)

        except (ValueError, OSError, OverflowError):
            self.ts_utc_result.setText("无效的时间戳")
            self.ts_local_result.clear()
            self.ts_relative.clear()

    def on_date_changed(self):
        """日期输入变化时更新时间戳"""
        text = self.date_input.text().strip()
        fmt = self.fmt_combo.currentText().strip()
        if not text:
            self.date_ts_result.clear()
            self.date_ts_ms_result.clear()
            return

        try:
            dt = datetime.strptime(text, fmt)
            ts = dt.timestamp()
            self.date_ts_result.setText(str(int(ts)))
            self.date_ts_ms_result.setText(str(int(ts * 1000)))
        except ValueError:
            self.date_ts_result.setText("格式不匹配")
            self.date_ts_ms_result.clear()

    def fill_current_datetime(self):
        """填充当前日期时间"""
        now = datetime.now()
        fmt = self.fmt_combo.currentText().strip()
        self.date_input.setText(now.strftime(fmt))

    def copy_to_clipboard(self, text):
        """复制到剪贴板"""
        if text:
            QApplication.clipboard().setText(text)

    def closeEvent(self, event):
        """关闭时停止定时器"""
        self.timer.stop()
        super().closeEvent(event)
