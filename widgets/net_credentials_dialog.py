# -*- coding: utf-8 -*-
r"""Pan4dex 万格 — 局域网共享凭据对话框

地址栏输入 `\\主机\共享` 而系统要凭据（或同机已用别的账号连着，1219）时弹出。
**只有这两档会弹**，其余失败一律只写状态栏（`core/net_share.py:may_ask_credentials`），
免得把「共享名打错」变成一次模态打断。

口令只经过这个控件与 `core/net_share`，**绝不写进任何配置文件**（用户的长期约束：
口令只来自环境变量或系统凭据库）；勾「记住」时由 net_share 写进 Windows 凭据管理器。

用法（主线程直接调用）::

    dlg = NetCredentialsDialog(parent, attempt)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        dlg.username / dlg.password / dlg.remember
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from core import net_share


class NetCredentialsDialog(QDialog):
    def __init__(self, parent, attempt):
        super().__init__(parent)
        self.attempt = attempt
        self.username = ""
        self.password = ""
        self.remember = False
        self.setWindowTitle("访问局域网共享")
        self.setMinimumWidth(420)
        self._apply_style()
        self._build_ui()

    def _apply_style(self):
        # 与 ConflictDialog 同一套：取不到父级配色就按深色（主题管理器默认 dark）
        dark = True
        try:
            win = self.parentWidget()
            if win is not None:
                dark = win.palette().color(win.background().role()).lightness() < 128
        except Exception:
            pass
        if dark:
            self.setStyleSheet("""
                QDialog, QWidget { background-color: #1E1E1E; color: #CCCCCC; }
                QLabel { color: #DDDDDD; }
                QLineEdit {
                    background-color: #2B2B2B; color: #E8E8E8;
                    border: 1px solid #555; border-radius: 3px; padding: 4px 6px;
                }
                QPushButton {
                    background-color: #3A3A3A; color: #E0E0E0;
                    border: 1px solid #555; border-radius: 4px;
                    padding: 5px 14px; min-width: 72px;
                }
                QPushButton:hover { background-color: #4A4A4A; }
                QPushButton:default { border-color: #2196F3; }
                QCheckBox { color: #CCCCCC; }
            """)

    def _header_text(self):
        unc = self.attempt.unc
        if self.attempt.category == net_share.CATEGORY_CONFLICT:
            return ("<b>\\\\%s</b> 上你已经用另一个账号连着。<br>"
                    "这次要用哪个账号？（会先断开旧连接）" % unc.server)
        return net_share.failure_text(net_share.CATEGORY_NEED_CREDENTIAL, unc) + "。"

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        head = QLabel(self._header_text())
        head.setWordWrap(True)
        layout.addWidget(head)

        hint = QLabel("账号可以是 <b>用户名</b>，也可以是 <b>域名\\用户名</b>。")
        hint.setStyleSheet("color: #9AA7B8;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("用户名")
        self.pass_edit = QLineEdit()
        self.pass_edit.setPlaceholderText("密码")
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_pass = QCheckBox("显示密码")
        self.show_pass.toggled.connect(self._toggle_echo)
        for label, widget in (("用户名", self.user_edit), ("密码", self.pass_edit)):
            row = QHBoxLayout()
            row.setSpacing(8)
            cap = QLabel(label)
            cap.setFixedWidth(52)
            row.addWidget(cap)
            row.addWidget(widget)
            layout.addLayout(row)
        echo_row = QHBoxLayout()
        echo_row.addSpacing(52)
        echo_row.addWidget(self.show_pass)
        echo_row.addStretch()
        layout.addLayout(echo_row)
        self.user_edit.textChanged.connect(self._update_enable)
        self.pass_edit.textChanged.connect(self._update_enable)

        # 只有 Windows 这版有地方存（Linux 钥匙环等目标机核实完 SMB 后端再定，
        # 见 docs/design-unc-share-access.md §9 第 1 条）。不支持时整格禁用，
        # 不给用户一个「勾了但没存上」的假象。
        self.remember_box = QCheckBox("记住这套凭据（存进系统凭据管理器）")
        self.remember_box.setEnabled(net_share.is_supported_platform())
        layout.addWidget(self.remember_box)

        btns = QHBoxLayout()
        btns.addStretch()
        self.ok_btn = QPushButton("连 接")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("取 消")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        self._prefill()
        self._update_enable()

    def _prefill(self):
        """已存过凭据就把用户名填上、口令留着空等用户敲（不把口令显示在框里）"""
        saved = net_share.saved_credential(self.attempt.unc.server,
                                            self.attempt.unc.share)
        if saved:
            self.user_edit.setText(saved[0] or "")
            self.remember_box.setChecked(True)
        self.user_edit.setFocus()

    def _toggle_echo(self, checked: bool):
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Normal if checked
                                   else QLineEdit.EchoMode.Password)

    def _update_enable(self):
        # 空口令是合法形状（guest 共享），但用户名不能空 —— 空用户名系统一律回 86，
        # 让用户白等一次不如直接不给点。
        self.ok_btn.setEnabled(bool(self.user_edit.text().strip()))

    def _accept(self):
        self.username = self.user_edit.text().strip()
        self.password = self.pass_edit.text()
        self.remember = bool(self.remember_box.isChecked()
                             and self.remember_box.isEnabled())
        self.accept()
