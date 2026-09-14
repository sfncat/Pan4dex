# -*- coding: utf-8 -*-
"""Pan4dex 万格 — 同名冲突处理对话框

复制/移动遇到目标同名项时询问"替换/跳过/保留两者"，对齐 Windows
资源管理器语义（旧实现一律静默改名 (2)，用户以为覆盖了却被悄悄改名）。
由后台操作线程经 QMetaObject.invokeMethod 在主线程弹出，因此
``chosen`` 属性在 ``ask()`` 返回后即可被 worker 线程读取。
"""
import os
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QCheckBox, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget,
)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    size = float(n)
    for unit in ('KB', 'MB', 'GB', 'TB'):
        size /= 1024.0
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


class ConflictDialog(QDialog):
    """单个冲突的询问对话框。

    用法（主线程直接调用，返回决策字符串）::

        dlg = ConflictDialog(parent, info)
        dlg.exec()
        decision = dlg.chosen   # 'replace' / 'skip' / 'keep_both' / 'cancel'
    """

    def __init__(self, parent, info: dict):
        super().__init__(parent)
        self.info = info
        self.chosen = 'cancel'
        self.setWindowTitle("同名项目冲突")
        self.setMinimumWidth(440)
        self._apply_style()
        self._build_ui()

    def _apply_style(self):
        dark = True
        try:
            win = self.parentWidget()
            while win is not None:
                bg = win.palette().color(win.background().role())
                dark = bg.lightness() < 128
                break
            # 取不到就按深色（与主题管理器默认 dark 一致）
        except Exception:
            pass
        if dark:
            self.setStyleSheet("""
                QDialog, QWidget { background-color: #1E1E1E; color: #CCCCCC; }
                QLabel { color: #DDDDDD; }
                QPushButton {
                    background-color: #3A3A3A; color: #E0E0E0;
                    border: 1px solid #555; border-radius: 4px;
                    padding: 5px 14px; min-width: 72px;
                }
                QPushButton:hover { background-color: #4A4A4A; }
                QPushButton:default { border-color: #2196F3; }
                QCheckBox { color: #CCCCCC; }
            """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        src = self.info.get('src', '')
        dst = self.info.get('dst', '')
        is_dir = self.info.get('is_dir', False)
        kind = "文件夹" if is_dir else "文件"
        name = os.path.basename(os.path.normpath(dst)) or dst

        title = QLabel(f"目标位置已存在同名{kind}：<b>{name}</b>。<br>请选择要保留的版本，或跳过。")
        title.setWordWrap(True)
        layout.addWidget(title)

        cmp_row = QHBoxLayout()
        cmp_row.setSpacing(24)
        cmp_row.addWidget(self._side_box("当前版本（将被替换）", dst,
                                         self.info.get('dst_size', 0),
                                         self.info.get('dst_mtime', 0), is_dir))
        cmp_row.addWidget(self._side_box("新版本（正在复制）", src,
                                         self.info.get('src_size', 0),
                                         self.info.get('src_mtime', 0), is_dir))
        layout.addLayout(cmp_row)

        self.apply_all = QCheckBox("对后续冲突执行相同操作")
        layout.addWidget(self.apply_all)

        btns = QHBoxLayout()
        btns.addStretch()
        # 与资源管理器同款三选项：替换 / 跳过 / 取消（“保留两者改名”
        # 作为无 UI 回调时的默认回退，不在此占用按钮）
        self._add_btn(btns, "替 换", 'replace', default=True)
        self._add_btn(btns, "跳 过", 'skip')
        self._add_btn(btns, "取 消", 'cancel')
        layout.addLayout(btns)

    def _side_box(self, header, path, size, mtime, is_dir) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        h = QLabel(header)
        h.setStyleSheet("color: #9AA7B8;")
        v.addWidget(h)
        n = QLabel(os.path.basename(os.path.normpath(path)) or path)
        n.setWordWrap(True)
        v.addWidget(n)
        meta = "—" if is_dir else _fmt_size(int(size or 0))
        if mtime:
            try:
                meta += "  " + datetime.fromtimestamp(float(mtime)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        m = QLabel(meta)
        m.setStyleSheet("color: #888;")
        v.addWidget(m)
        return w

    def _add_btn(self, row: QHBoxLayout, text: str, key: str, default: bool = False):
        b = QPushButton(text)
        b.setProperty("decision", key)
        b.setDefault(default)
        b.clicked.connect(lambda: self._choose(key))
        row.addWidget(b)

    def button(self, text: str) -> QPushButton:
        for b in self.findChildren(QPushButton):
            if b.text() == text:
                return b
        return None

    def _choose(self, key: str):
        self.chosen = key
        self.accept()

    def reject(self):
        # 关闭窗口 = 取消整个操作
        self.chosen = 'cancel'
        super().reject()
