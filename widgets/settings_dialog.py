"""
Pan4dex 万格 — 设置对话框（主题/字体）
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFontDialog, QColorDialog, QGroupBox,
    QFormLayout, QSpinBox, QTabWidget, QWidget, QCheckBox,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QLineEdit, QFileDialog
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, QSettings

from config.app_config import (
    DEFAULT_THEME, DEFAULT_LAUNCHER_APPS, ORG_NAME, APP_NAME, VERSION)
from core.updater import DEFAULT_SERVER_URL, normalize_server_url


class SettingsDialog(QDialog):
    """设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("设置")
        self.setMinimumSize(400, 300)

        # 当前设置
        self.current_theme = DEFAULT_THEME
        self.current_font_family = "系统默认"
        self.current_font_size = 9
        self.check_requested_flag = False
        self._clear_skipped = False
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        
        # 标签页
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # 常规设置（默认打开目录）
        general_tab = self.create_general_tab()
        tabs.addTab(general_tab, "常规")

        # 主题设置
        theme_tab = self.create_theme_tab()
        tabs.addTab(theme_tab, "主题")

        # 字体设置
        font_tab = self.create_font_tab()
        tabs.addTab(font_tab, "字体")

        # 工具栏设置
        toolbar_tab = self.create_toolbar_tab()
        tabs.addTab(toolbar_tab, "工具栏")

        # 应用启动器设置
        launcher_tab = self.create_launcher_tab()
        tabs.addTab(launcher_tab, "启动器")

        # 版本更新设置
        update_tab = self.create_update_tab()
        tabs.addTab(update_tab, "更新")

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
    
    def create_general_tab(self) -> QWidget:
        """创建设置常规标签页（默认打开目录）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("启动")
        gl = QFormLayout(group)

        # 默认打开目录（空 = 用户目录）
        self.default_dir_edit = QLineEdit()
        self.default_dir_edit.setPlaceholderText("留空 = 打开用户目录")
        s = QSettings(ORG_NAME, APP_NAME)
        cur = str(s.value("default_dir", "") or "")
        self.default_dir_edit.setText(cur)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self.default_dir_edit)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_default_dir)
        dir_row.addWidget(browse_btn)
        gl.addRow("默认打开目录:", dir_row)

        hint = QLabel("启动软件时窗格打开的目录。留空则打开用户目录。")
        hint.setWordWrap(True)
        layout.addWidget(group)
        layout.addWidget(hint)

        # 启动时显示侧边栏
        side_group = QGroupBox("启动时显示侧边栏")
        side_layout = QVBoxLayout(side_group)
        s = QSettings(ORG_NAME, APP_NAME)
        self.startup_bookmark_cb = QCheckBox("显示收藏夹侧边栏")
        self.startup_bookmark_cb.setChecked(
            s.value("startup/bookmark_sidebar", False, type=bool)
        )
        self.startup_tree_cb = QCheckBox("显示目录树侧边栏")
        self.startup_tree_cb.setChecked(
            s.value("startup/tree_sidebar", False, type=bool)
        )
        side_layout.addWidget(self.startup_bookmark_cb)
        side_layout.addWidget(self.startup_tree_cb)
        layout.addWidget(side_group)
        layout.addStretch()
        return widget

    def _browse_default_dir(self):
        """浏览选择默认打开目录"""
        path = QFileDialog.getExistingDirectory(
            self, "选择默认打开目录", self.default_dir_edit.text() or ""
        )
        if path:
            self.default_dir_edit.setText(path)

    def create_theme_tab(self) -> QWidget:
        """创建设置主题标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 主题选择
        theme_group = QGroupBox("主题")
        theme_layout = QFormLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("深色 (QDarkStyle)", "dark")
        self.theme_combo.addItem("浅色 (QDarkStyle)", "light")
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addRow("主题:", self.theme_combo)
        
        layout.addWidget(theme_group)
        layout.addStretch()
        
        return widget
    
    def create_font_tab(self) -> QWidget:
        """创建设置字体标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 字体选择
        font_group = QGroupBox("字体")
        font_layout = QFormLayout(font_group)
        
        self.font_combo = QComboBox()
        self.font_combo.addItem("系统默认", None)
        self.font_combo.addItem("Microsoft YaHei UI", "Microsoft YaHei UI")
        self.font_combo.addItem("Segoe UI", "Segoe UI")
        self.font_combo.addItem("Noto Sans CJK SC", "Noto Sans CJK SC")
        self.font_combo.addItem("DejaVu Sans", "DejaVu Sans")
        self.font_combo.addItem("Consolas", "Consolas")
        self.font_combo.addItem("Courier New", "Courier New")
        self.font_combo.currentIndexChanged.connect(self.on_font_changed)
        font_layout.addRow("字体:", self.font_combo)
        
        # 字号
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(9)
        font_layout.addRow("字号:", self.font_size_spin)
        
        # 预览
        self.preview_label = QLabel("这是字体预览文本 - Pan4dex 万格")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(60)
        font_layout.addRow("预览:", self.preview_label)
        
        layout.addWidget(font_group)
        layout.addStretch()
        
        return widget
    
    def create_toolbar_tab(self) -> QWidget:
        """创建工具栏设置标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        toolbar_group = QGroupBox("工具栏按钮")
        toolbar_layout = QVBoxLayout(toolbar_group)
        
        # 定义所有按钮的 checkbox
        self.toolbar_checkboxes = {}
        btn_labels = [
            ('back', '后退'),
            ('forward', '前进'),
            ('up', '上级目录'),
            ('refresh', '刷新'),
            ('tree', '目录树'),
            ('tabs', '标签页'),
            ('view', '查看模式'),
            ('new_folder', '新建文件夹'),
            ('terminal', '终端'),
        ]
        for key, label in btn_labels:
            cb = QCheckBox(f"{label} (&{label[0]})")
            # 前进/后退默认不显示
            if key in ('back', 'forward'):
                cb.setChecked(False)
            else:
                cb.setChecked(True)
            self.toolbar_checkboxes[key] = cb
            toolbar_layout.addWidget(cb)
        
        layout.addWidget(toolbar_group)
        layout.addStretch()
        return widget

    def create_launcher_tab(self) -> QWidget:
        """创建「应用启动器」设置标签页：菜单栏右侧快捷启动按钮"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("菜单栏右侧应用启动器")
        gl = QVBoxLayout(group)

        hint = QLabel("点击按钮直接启动对应应用；可在此添加/编辑/删除。\n"
                      "命令可以是可执行文件路径，也可以是系统 PATH 中的命令名（如 notepad.exe）。")
        hint.setWordWrap(True)
        gl.addWidget(hint)

        self.launcher_list = QListWidget()
        gl.addWidget(self.launcher_list)

        # 读取现有配置（QSettings），无则用默认
        self.launcher_apps: list = []
        s = QSettings(ORG_NAME, APP_NAME)
        raw = s.value("launcher/apps", "")
        if raw:
            try:
                import json
                self.launcher_apps = json.loads(raw)
            except Exception:
                self.launcher_apps = []
        if not self.launcher_apps:
            self.launcher_apps = [dict(a) for a in DEFAULT_LAUNCHER_APPS]
        self._reload_launcher_list()

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._launcher_add)
        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(self._launcher_edit)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._launcher_delete)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        gl.addLayout(btn_row)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _reload_launcher_list(self):
        self.launcher_list.clear()
        for app in self.launcher_apps:
            name = app.get("name", "")
            cmd = app.get("command", "")
            item = QListWidgetItem(f"{name} — {cmd}" if name else cmd)
            item.setData(Qt.ItemDataRole.UserRole, app)
            self.launcher_list.addItem(item)

    def _launcher_add(self):
        name, ok = QInputDialog.getText(self, "添加启动器", "按钮名称（如：记事本）:")
        if not ok or not name.strip():
            return
        cmd, ok2 = QInputDialog.getText(self, "添加启动器", "命令或程序路径（如：notepad.exe）:")
        if not ok2 or not cmd.strip():
            return
        self.launcher_apps.append({"name": name.strip(), "command": cmd.strip()})
        self._reload_launcher_list()

    def _launcher_edit(self):
        row = self.launcher_list.currentRow()
        if row < 0 or row >= len(self.launcher_apps):
            QMessageBox.information(self, "提示", "请先选中要编辑的项")
            return
        app = self.launcher_apps[row]
        name, ok = QInputDialog.getText(self, "编辑启动器", "按钮名称:", text=app.get("name", ""))
        if not ok:
            return
        cmd, ok2 = QInputDialog.getText(self, "编辑启动器", "命令或程序路径:", text=app.get("command", ""))
        if not ok2:
            return
        app["name"] = name.strip()
        app["command"] = cmd.strip()
        self._reload_launcher_list()

    def _launcher_delete(self):
        row = self.launcher_list.currentRow()
        if row < 0 or row >= len(self.launcher_apps):
            QMessageBox.information(self, "提示", "请先选中要删除的项")
            return
        del self.launcher_apps[row]
        self._reload_launcher_list()

    def create_update_tab(self) -> QWidget:
        """创建「更新」设置标签页（更新服务器 / 启动检查 / 自动模式）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        s = QSettings(ORG_NAME, APP_NAME)

        version_group = QGroupBox("当前版本")
        vg = QVBoxLayout(version_group)
        version_label = QLabel(f"Pan4dex {VERSION}")
        version_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        vg.addWidget(version_label)
        self.update_check_btn = QPushButton("立即检查更新")
        self.update_check_btn.clicked.connect(self._on_check_update_clicked)
        vg.addWidget(self.update_check_btn)
        layout.addWidget(version_group)

        server_group = QGroupBox("更新服务器")
        sf = QFormLayout(server_group)
        self.update_server_edit = QLineEdit(
            str(s.value("update/server_url", DEFAULT_SERVER_URL) or DEFAULT_SERVER_URL))
        self.update_server_edit.setPlaceholderText(DEFAULT_SERVER_URL)
        sf.addRow("服务器地址:", self.update_server_edit)
        server_hint = QLabel("局域网更新源，例如 http://192.168.5.230:23011")
        server_hint.setWordWrap(True)
        sf.addRow("", server_hint)
        layout.addWidget(server_group)

        behavior_group = QGroupBox("检查与安装")
        bl = QVBoxLayout(behavior_group)
        self.update_startup_cb = QCheckBox("启动时在后台检查新版本")
        self.update_startup_cb.setChecked(
            s.value("update/startup_check", True, type=bool))
        self.update_auto_download_cb = QCheckBox("发现新版本后自动下载")
        self.update_auto_download_cb.setChecked(
            s.value("update/auto_download", False, type=bool))
        self.update_auto_install_cb = QCheckBox("下载完成后自动安装并重启")
        self.update_auto_install_cb.setChecked(
            s.value("update/auto_install", False, type=bool))
        self.update_auto_install_cb.setEnabled(
            self.update_auto_download_cb.isChecked())
        self.update_auto_download_cb.toggled.connect(
            self.update_auto_install_cb.setEnabled)
        self.update_auto_download_cb.toggled.connect(
            lambda on: on or self.update_auto_install_cb.setChecked(False))
        bl.addWidget(self.update_startup_cb)
        bl.addWidget(self.update_auto_download_cb)
        bl.addWidget(self.update_auto_install_cb)
        layout.addWidget(behavior_group)

        skip_group = QGroupBox("已跳过的版本")
        sg = QHBoxLayout(skip_group)
        self.skipped_label = QLabel(
            str(s.value("update/skipped_version", "") or "") or "（无）")
        sg.addWidget(self.skipped_label)
        sg.addStretch()
        self.clear_skipped_btn = QPushButton("清除")
        self.clear_skipped_btn.clicked.connect(self._on_clear_skipped)
        sg.addWidget(self.clear_skipped_btn)
        layout.addWidget(skip_group)

        layout.addStretch()
        return widget

    def _on_check_update_clicked(self):
        """保存设置并立即执行一次手动检查（由主窗口接管）"""
        self.check_requested_flag = True
        self.accept()

    def _on_clear_skipped(self):
        self._clear_skipped = True
        self.skipped_label.setText("（保存后清除）")

    def accept(self):
        """保存前校验服务器地址，避免把写坏的地址存进 QSettings"""
        url = self.update_server_edit.text().strip() or DEFAULT_SERVER_URL
        try:
            self.update_server_edit.setText(normalize_server_url(url))
        except ValueError as exc:
            QMessageBox.warning(self, "地址不合法", str(exc))
            self.update_server_edit.setFocus()
            return
        super().accept()

    def on_theme_changed(self, index):
        """主题变化"""
        self.current_theme = self.theme_combo.itemData(index)
    
    def on_font_changed(self, index):
        """字体变化"""
        self.current_font_family = self.font_combo.currentText()
        self.current_font_size = self.font_size_spin.value()
        self.update_preview()
    
    def update_preview(self):
        """更新字体预览"""
        font = QFont(self.current_font_family, self.font_size_spin.value())
        self.preview_label.setFont(font)
    
    def get_settings(self) -> dict:
        """获取设置"""
        settings = {
            'theme': self.current_theme,
            'font_family': self.font_combo.currentText(),
            'font_size': self.font_size_spin.value(),
            'default_dir': self.default_dir_edit.text().strip(),
            'startup_bookmark_sidebar': self.startup_bookmark_cb.isChecked(),
            'startup_tree_sidebar': self.startup_tree_cb.isChecked(),
        }
        # 收集工具栏按钮可见性
        if hasattr(self, 'toolbar_checkboxes'):
            settings['toolbar_buttons'] = {
                key: cb.isChecked() for key, cb in self.toolbar_checkboxes.items()
            }
        # 应用启动器配置
        if hasattr(self, 'launcher_apps'):
            settings['launcher_apps'] = list(self.launcher_apps)
        # 更新设置
        if hasattr(self, 'update_server_edit'):
            auto_download = self.update_auto_download_cb.isChecked()
            settings.update({
                'update_server_url': self.update_server_edit.text().strip(),
                'update_startup_check': self.update_startup_cb.isChecked(),
                'update_auto_download': auto_download,
                'update_auto_install': (
                    auto_download and self.update_auto_install_cb.isChecked()),
                'update_clear_skipped': self._clear_skipped,
            })
        return settings
