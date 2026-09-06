"""
Pan4dex 万格 — 主窗口
"""
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QSplitter, QWidget, 
    QVBoxLayout, QStatusBar, QMenuBar, QTabBar,
    QToolBar, QLabel, QApplication, QMenu, QDialog
)
from PyQt6.QtCore import Qt, QSettings, QSize, QPoint, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QCursor

logger = logging.getLogger("pan4dex.window")


class CollapsibleTabBar(QTabBar):
    """可折叠标签栏：隐藏时 sizeHint 返回 0 + sizePolicy Ignored，确保 QTabWidget 内部布局不留空隙"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._normal_size_policy = self.sizePolicy()

    def setCollapsed(self, collapsed: bool):
        self._collapsed = collapsed
        if collapsed:
            from PyQt6.QtWidgets import QSizePolicy
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.setFixedHeight(0)
            self.setMaximumHeight(0)
            self.setMinimumHeight(0)
        else:
            self.setSizePolicy(self._normal_size_policy)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
        self.updateGeometry()

    def sizeHint(self):
        if self._collapsed:
            return QSize(0, 0)
        return super().sizeHint()

    def minimumSizeHint(self):
        if self._collapsed:
            return QSize(0, 0)
        return super().minimumSizeHint()

from core.pane import Pane
from widgets.preview_panel import PreviewPanel
from widgets.bookmark_sidebar import BookmarkSidebar
from widgets.tree_sidebar import TreeSidebar
from config.file_associations import FileAssociations
from config.theme_manager import ThemeManager
from config.app_config import (
    APP_NAME,
    ORG_NAME,
    VERSION,
    BUILD_TIME,
    DEFAULT_THEME,
    DEFAULT_WINDOW_MIN_WIDTH,
    DEFAULT_WINDOW_MIN_HEIGHT,
    ICON_FILE,
    DEFAULT_LAUNCHER_APPS,
)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Pan4dex 万格")
        self.setMinimumSize(DEFAULT_WINDOW_MIN_WIDTH, DEFAULT_WINDOW_MIN_HEIGHT)
        
        # 设置应用图标：Windows 优先用 icon.ico（ICO 原生多尺寸，任务栏提取稳定），
        # 否则用 icon.png 生成多尺寸 QIcon（Linux 等平台统一圆角 PNG）
        from PyQt6.QtGui import QIcon
        import sys
        import os
        _icon_name = ICON_FILE
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后：_MEIPASS 指向 _internal，兜底到 exe 同目录
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, 'resources', 'icons', _icon_name)
        if not os.path.exists(icon_path) and getattr(sys, 'frozen', False):
            icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), 'resources', 'icons', _icon_name)
        _win_icon = None
        if sys.platform == 'win32':
            _ico_path = os.path.join(os.path.dirname(icon_path), 'icon.ico')
            if os.path.exists(_ico_path):
                _win_icon = QIcon(_ico_path)
        if (_win_icon is None or _win_icon.isNull()) and os.path.exists(icon_path):
            from core.icon_utils import load_app_icon
            _win_icon = load_app_icon(icon_path)
        if _win_icon is not None and not _win_icon.isNull():
            self.setWindowIcon(_win_icon)
        
        # 恢复窗口位置和大小
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.restore_geometry()
        
        # 文件关联
        self.file_associations = FileAssociations()
        
        # 主题管理器
        self.theme_manager = ThemeManager()
        
        # 预览面板状态
        self._preview_toggle = False
        
        import time
        _t0 = time.perf_counter()
        
        self._active_pane = None

        # 创建 UI
        self.create_menu_bar()
        logger.info(f"[启动计时] 菜单栏: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.create_status_bar()
        logger.info(f"[启动计时] 状态栏: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.create_central_widget()
        logger.info(f"[启动计时] 中央widget(含四窗格): {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.create_preview_panel()
        logger.info(f"[启动计时] 预览面板: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.create_bookmark_sidebar()
        logger.info(f"[启动计时] 收藏夹侧栏: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        self.create_tree_sidebar()
        logger.info(f"[启动计时] 目录树侧栏: {(time.perf_counter()-_t0)*1000:.1f}ms")

        # 终端面板延迟创建（见 create_terminal_panel，事件循环后 400ms）
        self.create_terminal_panel()

        # 延迟应用主题和恢复布局（避免阻塞启动）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._deferred_init)
        logger.info(f"[启动计时] 延迟初始化已调度: {(time.perf_counter()-_t0)*1000:.1f}ms")
    
    def _deferred_init(self):
        """延迟初始化（在事件循环开始后执行）"""
        import time
        _t0 = time.perf_counter()
        
        # 应用主题（QSettings 有记录则恢复，否则默认）
        saved_theme = self.settings.value("theme", "")
        theme = saved_theme if saved_theme else DEFAULT_THEME
        self.theme_manager.apply_theme(theme)
        logger.info(f"[启动计时] 主题应用: {(time.perf_counter()-_t0)*1000:.1f}ms")

        # 恢复字体设置
        try:
            ff = self.settings.value("font_family", "")
            fs = int(self.settings.value("font_size", 9) or 9)
            if ff and ff != "系统默认":
                from PyQt6.QtGui import QFont
                QApplication.instance().setFont(QFont(ff, fs))
        except Exception:
            pass

        # 恢复工具栏按钮可见性
        try:
            tb = self.settings.value("toolbar_buttons", {})
            if tb:
                self.apply_toolbar_buttons(tb)
        except Exception:
            pass
        
        # 自动恢复上次的布局
        self._auto_load_layout()
        logger.info(f"[启动计时] 布局恢复: {(time.perf_counter()-_t0)*1000:.1f}ms")
    
    def _auto_load_layout(self):
        """自动加载上次保存的布局"""
        import json
        import os
        
        layout_file = os.path.expanduser("~/.config/pan4dex/layout.json")
        
        if not os.path.exists(layout_file):
            return
        
        try:
            with open(layout_file, 'r', encoding='utf-8') as f:
                layout = json.load(f)
        except Exception:
            return
        
        # 等待 UI 初始化完成后恢复布局
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._apply_layout(layout))
    
    def _apply_layout(self, layout: dict):
        """应用布局配置"""
        current_widget = self.tab_widget.currentWidget()
        if not isinstance(current_widget, QuadPaneWidget):
            return
        
        # 先恢复布局模式（决定哪些窗格可见），再恢复各窗格状态
        mode = layout.get('mode', 'quad')
        try:
            current_widget.set_layout_mode(mode)
        except Exception:
            current_widget.switch_to_quad()
        
        panes_layout = layout.get('panes', {})
        if not panes_layout:
            self.status_bar.showMessage("已恢复上次布局")
            return
        
        for pane_name, state in panes_layout.items():
            pane = getattr(current_widget, pane_name, None)
            if pane:
                pane.set_state(state)
        
        self.status_bar.showMessage("已恢复上次布局")
    
    def create_preview_panel(self):
        """创建预览面板"""
        self.preview_panel = PreviewPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.preview_panel)
        self.preview_panel.setVisible(False)
        self._preview_visible = False
        
        # 连接预览面板到窗格
        self.preview_panel.visibilityChanged.connect(self.on_preview_visibility_changed)
    
    def create_bookmark_sidebar(self):
        """创建收藏夹侧边栏"""
        self.bookmark_sidebar = BookmarkSidebar(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.bookmark_sidebar)
        self.bookmark_sidebar.setVisible(False)
        
        # 连接收藏夹点击信号
        self.bookmark_sidebar.bookmark_clicked.connect(self.on_bookmark_clicked)
    
    def create_tree_sidebar(self):
        """创建目录树侧边栏（延迟到事件循环后，避免阻塞首屏显示；约省 220ms）"""
        self.tree_sidebar = None
        self._tree_sidebar_ready = False
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, self._create_tree_sidebar_lazy)
    
    def _create_tree_sidebar_lazy(self):
        """延迟创建目录树侧边栏"""
        if self._tree_sidebar_ready:
            return
        self.tree_sidebar = TreeSidebar(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_sidebar)
        self.tree_sidebar.setVisible(False)
        # 连接目录树点击信号 - 导航到当前活动窗格
        self.tree_sidebar.folder_clicked.connect(self.on_tree_folder_clicked)
        self._tree_sidebar_ready = True
        # 若在创建前用户已触发切换，补同步显示状态
        if getattr(self, '_tree_toggle', False):
            self.tree_sidebar.setVisible(True)
    
    def on_tree_folder_clicked(self, path: str):
        """目录树文件夹点击 - 导航到当前活动窗格"""
        if self._active_pane:
            self._active_pane.navigate_to(path)
    
    def on_bookmark_clicked(self, path: str):
        """收藏夹点击 - 导航到当前活动窗格"""
        if self._active_pane:
            self._active_pane.navigate_to(path)
    
    def on_preview_visibility_changed(self, visible):
        """预览面板可见性变化"""
        if not visible:
            self.preview_panel.clear_preview()

    # ------------------------------------------------------------------
    # 内嵌终端面板（延迟创建；位置与可见性持久化到 QSettings）
    # ------------------------------------------------------------------
    def create_terminal_panel(self):
        """创建终端面板（延迟到事件循环后，不阻塞首屏）"""
        self.terminal_panel = None
        self._terminal_ready = False
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(400, self._create_terminal_panel_lazy)

    def _create_terminal_panel_lazy(self):
        """延迟创建终端面板"""
        if getattr(self, '_terminal_ready', False):
            return
        from widgets.terminal_panel import TerminalPanel
        # 用户配置的终端程序（terminal/program，空 = 系统默认 shell）
        cfg_program = self.settings.value("terminal/program", "") or None
        self.terminal_panel = TerminalPanel(program=cfg_program, parent=self)
        pos = str(self.settings.value("terminal/position", "bottom") or "bottom")
        area = (Qt.DockWidgetArea.BottomDockWidgetArea if pos == "bottom"
                else Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(area, self.terminal_panel)
        self.terminal_panel.setVisible(False)
        self._terminal_ready = True
        # 用户直接点 dock 的 X 关闭时同步菜单勾选与配置
        self.terminal_panel.visibilityChanged.connect(self.on_terminal_visibility_changed)
        # 恢复上次可见状态
        saved_vis = self.settings.value("terminal/visible", False)
        if saved_vis in (True, "true", "True", "1"):
            self.terminal_panel.setVisible(True)
            if hasattr(self, 'terminal_action'):
                self.terminal_action.setChecked(True)

    def on_terminal_visibility_changed(self, visible):
        """终端面板可见性变化（含 dock 关闭按钮）"""
        if hasattr(self, 'terminal_action'):
            self.terminal_action.setChecked(visible)
        self.settings.setValue("terminal/visible", visible)

    def configure_terminal_program(self):
        """配置终端程序（空 = 系统默认 shell），保存并重启终端会话"""
        from PyQt6.QtWidgets import QInputDialog
        current = str(self.settings.value("terminal/program", "") or "")
        text, ok = QInputDialog.getText(
            self, "更改终端程序",
            "输入终端程序命令（留空 = 系统默认终端）：\n"
            "例：bash、zsh、/bin/fish、\"C:\\Program Files\\Git\\bin\\bash.exe\"",
            text=current,
        )
        if not ok:
            return
        program = text.strip()
        self.settings.setValue("terminal/program", program)
        if getattr(self, 'terminal_panel', None) is not None:
            self.terminal_panel.set_program(program or None)

    def toggle_terminal(self):
        """切换终端面板显示"""
        if getattr(self, 'terminal_panel', None) is None:
            self._create_terminal_panel_lazy()
        vis = not self.terminal_panel.isVisible()
        self.terminal_panel.setVisible(vis)
        self.settings.setValue("terminal/visible", vis)
        self.terminal_action.setChecked(vis)

    def set_terminal_position(self, pos: str):
        """终端停靠右侧/底部（配置持久化）"""
        if getattr(self, 'terminal_panel', None) is None:
            self._create_terminal_panel_lazy()
        self.settings.setValue("terminal/position", pos)
        area = (Qt.DockWidgetArea.BottomDockWidgetArea if pos == "bottom"
                else Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(area, self.terminal_panel)
        if self.terminal_panel.isVisible():
            self.terminal_panel.show()

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        new_tab_action = QAction("新建标签页(&T)", self)
        new_tab_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tab_action.triggered.connect(self.new_tab)
        file_menu.addAction(new_tab_action)
        
        close_tab_action = QAction("关闭标签页(&W)", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.triggered.connect(self.close_current_tab)
        file_menu.addAction(close_tab_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")
        
        copy_action = QAction("复制(&C)", self)
        copy_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_action.triggered.connect(self.on_copy)
        edit_menu.addAction(copy_action)
        
        cut_action = QAction("剪切(&X)", self)
        cut_action.setShortcut(QKeySequence("Ctrl+X"))
        cut_action.triggered.connect(self.on_cut)
        edit_menu.addAction(cut_action)
        
        paste_action = QAction("粘贴(&V)", self)
        paste_action.setShortcut(QKeySequence("Ctrl+V"))
        paste_action.triggered.connect(self.on_paste)
        edit_menu.addAction(paste_action)
        
        edit_menu.addSeparator()
        
        select_all_action = QAction("全选(&A)", self)
        select_all_action.setShortcut(QKeySequence("Ctrl+A"))
        select_all_action.triggered.connect(self.on_select_all)
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        delete_action = QAction("删除(&D)", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self.on_delete)
        edit_menu.addAction(delete_action)
        
        rename_action = QAction("重命名(&R)", self)
        rename_action.setShortcut(QKeySequence("F2"))
        rename_action.triggered.connect(self.on_rename)
        edit_menu.addAction(rename_action)
        
        edit_menu.addSeparator()
        
        refresh_action = QAction("刷新(&F)", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.on_refresh)
        edit_menu.addAction(refresh_action)
        
        edit_menu.addSeparator()
        
        new_folder_action = QAction("新建文件夹(&N)", self)
        new_folder_action.setShortcut(QKeySequence("F7"))
        new_folder_action.triggered.connect(self.on_new_folder)
        edit_menu.addAction(new_folder_action)
        
        new_file_action = QAction("新建文件(&E)", self)
        new_file_action.setShortcut(QKeySequence("F8"))
        new_file_action.triggered.connect(self.on_new_file)
        edit_menu.addAction(new_file_action)
        
        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")
        
        quad_mode_action = QAction("四窗格模式(&4)", self)
        quad_mode_action.setShortcut(QKeySequence("Ctrl+4"))
        quad_mode_action.triggered.connect(self.switch_to_quad)
        view_menu.addAction(quad_mode_action)
        
        dual_mode_action = QAction("双窗格模式(&2)", self)
        dual_mode_action.setShortcut(QKeySequence("Ctrl+2"))
        dual_mode_action.triggered.connect(self.switch_to_dual)
        view_menu.addAction(dual_mode_action)

        dual_h_mode_action = QAction("双窗格横向(&H)", self)
        dual_h_mode_action.setShortcut(QKeySequence("Ctrl+Shift+2"))
        dual_h_mode_action.triggered.connect(self.switch_to_dual_horizontal)
        view_menu.addAction(dual_h_mode_action)

        mode_2_1_action = QAction("上2下1(&5)", self)
        mode_2_1_action.setShortcut(QKeySequence("Ctrl+5"))
        mode_2_1_action.triggered.connect(self.switch_to_2_1)
        view_menu.addAction(mode_2_1_action)

        mode_1_2_action = QAction("上1下2(&6)", self)
        mode_1_2_action.setShortcut(QKeySequence("Ctrl+6"))
        mode_1_2_action.triggered.connect(self.switch_to_1_2)
        view_menu.addAction(mode_1_2_action)
        
        view_menu.addSeparator()
        
        bookmark_action = QAction("收藏夹(&B)", self)
        bookmark_action.setShortcut(QKeySequence("Ctrl+B"))
        bookmark_action.setCheckable(True)
        bookmark_action.triggered.connect(self.toggle_bookmark_sidebar)
        view_menu.addAction(bookmark_action)
        self.bookmark_action = bookmark_action
        
        tree_action = QAction("目录树(&T)", self)
        tree_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        tree_action.setCheckable(True)
        tree_action.triggered.connect(self.toggle_tree_sidebar)
        view_menu.addAction(tree_action)
        self.tree_action = tree_action

        preview_action = QAction("预览面板(&P)", self)
        preview_action.setShortcut(QKeySequence("F3"))
        preview_action.setCheckable(True)
        preview_action.setChecked(False)
        preview_action.triggered.connect(self.toggle_preview)
        view_menu.addAction(preview_action)
        self.preview_action = preview_action

        terminal_action = QAction("终端面板(&M)", self)
        terminal_action.setShortcut(QKeySequence("F4"))
        terminal_action.setCheckable(True)
        terminal_action.triggered.connect(self.toggle_terminal)
        view_menu.addAction(terminal_action)
        self.terminal_action = terminal_action

        # 终端停靠位置子菜单（右侧/底部，配置持久化）
        term_pos_menu = view_menu.addMenu("终端位置(&L)")
        act_right = QAction("停靠右侧(&R)", self)
        act_right.setCheckable(True)
        act_bottom = QAction("停靠底部(&B)", self)
        act_bottom.setCheckable(True)
        _saved_pos = str(self.settings.value("terminal/position", "bottom") or "bottom")
        act_right.setChecked(_saved_pos == "right")
        act_bottom.setChecked(_saved_pos == "bottom")
        act_right.triggered.connect(lambda: (act_bottom.setChecked(False), self.set_terminal_position("right")))
        act_bottom.triggered.connect(lambda: (act_right.setChecked(False), self.set_terminal_position("bottom")))
        term_pos_menu.addAction(act_right)
        term_pos_menu.addAction(act_bottom)
        self.term_pos_actions = (act_right, act_bottom)

        # 配置终端程序（默认系统终端，配置持久化）
        term_prog_action = QAction("更改终端程序…(&P)", self)
        term_prog_action.triggered.connect(self.configure_terminal_program)
        view_menu.addAction(term_prog_action)

        tab_bar_action = QAction("标签页栏(&B)", self)
        tab_bar_action.setCheckable(True)
        tab_bar_action.setChecked(False)
        tab_bar_action.triggered.connect(self.toggle_tab_bar)
        view_menu.addAction(tab_bar_action)
        self.tab_bar_action = tab_bar_action

        view_menu.addSeparator()
        
        dark_theme_action = QAction("深色主题(&D)", self)
        dark_theme_action.triggered.connect(lambda: self.set_theme("dark"))
        view_menu.addAction(dark_theme_action)
        
        light_theme_action = QAction("浅色主题(&L)", self)
        light_theme_action.triggered.connect(lambda: self.set_theme("light"))
        view_menu.addAction(light_theme_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")
        
        batch_rename_action = QAction("批量重命名(&R)...", self)
        batch_rename_action.triggered.connect(self.open_batch_rename)
        tools_menu.addAction(batch_rename_action)
        
        checksum_action = QAction("校验和工具(&C)...", self)
        checksum_action.triggered.connect(self.open_checksum)
        tools_menu.addAction(checksum_action)
        
        timestamp_action = QAction("时间戳转换(&T)...", self)
        timestamp_action.triggered.connect(self.open_timestamp_tool)
        tools_menu.addAction(timestamp_action)
        
        compare_action = QAction("文件比较(&M)...", self)
        compare_action.triggered.connect(self.open_file_compare)
        tools_menu.addAction(compare_action)
        
        dir_sync_action = QAction("目录同步(&S)...", self)
        dir_sync_action.triggered.connect(self.open_dir_sync)
        tools_menu.addAction(dir_sync_action)
        
        archive_action = QAction("压缩包处理(&A)...", self)
        archive_action.triggered.connect(self.open_archive)
        tools_menu.addAction(archive_action)
        
        split_action = QAction("文件分割/合并(&P)...", self)
        split_action.triggered.connect(self.open_file_split)
        tools_menu.addAction(split_action)
        
        search_action = QAction("高级搜索(&F)...", self)
        search_action.triggered.connect(self.open_advanced_search)
        tools_menu.addAction(search_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        settings_action = QAction("设置(&S)...", self)
        settings_action.triggered.connect(self.open_settings)
        help_menu.addAction(settings_action)
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # 菜单栏右侧：应用启动器按钮（可配置直接启动外部应用）
        self.create_launcher_bar()

    def create_launcher_bar(self):
        """菜单栏右侧应用启动器：一组快捷启动外部应用的按钮。

        配置来自 QSettings "launcher/apps"（JSON 数组），无配置时用
        DEFAULT_LAUNCHER_APPS；设置对话框「启动器」页可增删改。
        """
        import json
        from PyQt6.QtWidgets import QWidget, QHBoxLayout, QToolButton
        apps = []
        raw = self.settings.value("launcher/apps", "")
        if raw:
            try:
                apps = json.loads(raw)
            except Exception:
                apps = []
        if not apps:
            apps = [dict(a) for a in DEFAULT_LAUNCHER_APPS]
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(4, 2, 6, 2)
        lay.setSpacing(4)
        self._launcher_container = container
        self._launcher_layout = lay
        self._launcher_apps = apps
        for app in apps:
            name = str(app.get("name", "")).strip()
            cmd = str(app.get("command", "")).strip()
            if not cmd:
                continue
            btn = QToolButton()
            btn.setText(name[:2] if name else "…")
            btn.setToolTip(f"{name}\n{cmd}" if name else cmd)
            btn.setFixedSize(30, 24)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda checked=False, c=cmd: self._launch_app(c))
            lay.addWidget(btn)
        lay.addStretch()
        self.menuBar().setCornerWidget(container, Qt.Corner.TopRightCorner)

    def refresh_launcher_buttons(self):
        """设置变更后重建启动器按钮（复用现有菜单栏 corner widget）"""
        try:
            old = self.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
            if old is not None:
                old.deleteLater()
            self.create_launcher_bar()
        except Exception:
            pass

    def _launch_app(self, command: str):
        """启动外部应用（命令名或路径）"""
        import shutil
        import subprocess
        import os
        try:
            if os.name == "nt":
                # ShellExecute：可解析 PATH 命令名与 .exe/.lnk 等关联
                os.startfile(command)
            else:
                exe = shutil.which(command) or (command if os.path.exists(command) else None)
                if not exe:
                    self.status_bar.showMessage(f"找不到应用: {command}")
                    return
                subprocess.Popen([exe])
            self.status_bar.showMessage(f"已启动: {command}")
        except Exception as e:
            self.status_bar.showMessage(f"启动失败: {command} ({e})")
    
    def create_tool_bar(self):
        """创建工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        from PyQt6.QtCore import QSize
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
    
    def create_central_widget(self):
        """创建中央 widget"""
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        # 使用可折叠自定义 TabBar，隐藏时不留空隙
        self._custom_tab_bar = CollapsibleTabBar()
        self.tab_widget.setTabBar(self._custom_tab_bar)
        # 默认隐藏标签栏，可通过视图菜单显示
        self._tab_bar_visible = False
        self._apply_tab_bar_visibility()
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        # 右键菜单支持
        self.tab_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.customContextMenuRequested.connect(self.show_tab_context_menu)
        
        # 双击标签关闭，双击空白新建
        self.tab_widget.installEventFilter(self)
        self.tab_widget.tabBarDoubleClicked.connect(self.on_tab_bar_double_clicked)
        
        self.setCentralWidget(self.tab_widget)
        
        # 创建第一个标签页
        self.new_tab()
    
    def create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        # 状态栏右侧：剪贴板操作按钮（作用于当前活动窗格）
        self.create_status_bar_actions()

    def create_status_bar_actions(self):
        """状态栏右侧按钮：复制 / 粘贴 / 剪切（作用于当前活动窗格）"""
        from PyQt6.QtWidgets import QToolButton
        for label, tip, handler in (
            ("复制", "复制选中项 (Ctrl+C)", self.on_copy),
            ("粘贴", "粘贴剪贴板 (Ctrl+V)", self.on_paste),
            ("剪切", "剪切选中项 (Ctrl+X)", self.on_cut),
        ):
            btn = QToolButton()
            btn.setText(label)
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            btn.setStyleSheet(
                "QToolButton { padding: 2px 8px; border: 1px solid transparent; border-radius: 3px; }"
                "QToolButton:hover { border-color: #5A5A5A; }"
            )
            btn.clicked.connect(handler)
            self.status_bar.addPermanentWidget(btn)
    
    def new_tab(self):
        """新建标签页"""
        quad_widget = QuadPaneWidget(self)
        # 连接活动窗格信号
        quad_widget.pane_activated.connect(self.on_pane_activated)
        index = self.tab_widget.addTab(quad_widget, "新标签页")
        self.tab_widget.setCurrentIndex(index)
    
    def close_tab(self, index):
        """关闭标签页"""
        if self.tab_widget.count() > 1:
            widget = self.tab_widget.widget(index)
            self.tab_widget.removeTab(index)
            widget.deleteLater()
    
    def close_current_tab(self):
        """关闭当前标签页"""
        self.close_tab(self.tab_widget.currentIndex())
    
    def eventFilter(self, obj, event):
        """事件过滤器：检测标签栏空白区域双击"""
        if obj == self.tab_widget and event.type() == event.Type.MouseButtonDblClick:
            tab_bar = self.tab_widget.tabBar()
            pos = event.position().toPoint()
            # 映射到 tab bar 坐标
            tab_bar_pos = tab_bar.mapFrom(self.tab_widget, pos)
            if tab_bar.rect().contains(tab_bar_pos):
                tab_index = tab_bar.tabAt(tab_bar_pos)
                if tab_index == -1:
                    # 双击空白区域 → 新建标签
                    self.new_tab()
                    return True
        return super().eventFilter(obj, event)

    def on_tab_bar_double_clicked(self, index):
        """双击标签 → 关闭标签页（重命名请用右键菜单）"""
        if index >= 0:
            self.close_tab(index)
    
    def show_tab_context_menu(self, position):
        """显示标签栏右键菜单"""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
        """)
        
        new_tab_action = QAction("新建标签页(&T)", self)
        new_tab_action.triggered.connect(self.new_tab)
        menu.addAction(new_tab_action)
        
        # 坐标转换：从 tab widget 坐标 → tab bar 坐标
        tab_bar = self.tab_widget.tabBar()
        pos_in_bar = tab_bar.mapFrom(self.tab_widget, position)
        tab_index = tab_bar.tabAt(pos_in_bar)
        if tab_index >= 0:
            rename_tab_action = QAction("重命名标签页(&R)", self)
            rename_tab_action.triggered.connect(lambda: self.rename_tab(tab_index))
            menu.addAction(rename_tab_action)
            
            close_tab_action = QAction("关闭标签页(&W)", self)
            close_tab_action.triggered.connect(lambda: self.close_tab(tab_index))
            menu.addAction(close_tab_action)
        
        menu.exec(QCursor.pos())
    
    def rename_tab(self, index):
        """重命名标签页"""
        from PyQt6.QtWidgets import QInputDialog
        current_name = self.tab_widget.tabText(index)
        new_name, ok = QInputDialog.getText(
            self, "重命名标签页", "输入新名称:", text=current_name
        )
        if ok and new_name.strip():
            self.tab_widget.setTabText(index, new_name.strip())
    
    def on_tab_changed(self, index):
        """标签页切换时更新状态栏"""
        if index >= 0:
            widget = self.tab_widget.widget(index)
            if widget:
                self.status_bar.showMessage(f"当前标签页: {self.tab_widget.tabText(index)}")
    
    def on_copy(self):
        """复制操作"""
        if self._active_pane:
            self._active_pane.copy_selected()

    def on_cut(self):
        """剪切操作"""
        if self._active_pane:
            self._active_pane.cut_selected()

    def on_paste(self):
        """粘贴操作"""
        if self._active_pane:
            self._active_pane.paste()

    def on_delete(self):
        """删除操作"""
        if self._active_pane:
            self._active_pane.delete_selected()

    def on_rename(self):
        """重命名操作"""
        if self._active_pane:
            self._active_pane.rename_selected()

    def on_select_all(self):
        """全选操作"""
        if self._active_pane:
            self._active_pane.tree_view.selectAll()

    def on_refresh(self):
        """刷新操作"""
        if self._active_pane:
            self._active_pane.navigate_to(self._active_pane.current_path)

    def on_new_folder(self):
        """新建文件夹"""
        if self._active_pane:
            self._active_pane.new_folder()

    def on_new_file(self):
        """新建文件"""
        if self._active_pane:
            self._active_pane.new_file()

    def on_pane_activated(self, pane):
        """窗格被激活（获得焦点）"""
        self._active_pane = pane
    
    def toggle_preview(self):
        """切换预览面板"""
        current = getattr(self, '_preview_toggle', False)
        self._preview_toggle = not current
        self.preview_panel.setVisible(self._preview_toggle)
        self.preview_action.setChecked(self._preview_toggle)
    
    def toggle_bookmark_sidebar(self):
        """切换收藏夹侧边栏"""
        current = getattr(self, '_bookmark_toggle', False)
        self._bookmark_toggle = not current
        self.bookmark_sidebar.setVisible(self._bookmark_toggle)
        self.bookmark_action.setChecked(self._bookmark_toggle)
    
    def toggle_tree_sidebar(self):
        """切换目录树侧边栏"""
        current = getattr(self, '_tree_toggle', False)
        self._tree_toggle = not current
        if self.tree_sidebar is None:
            self._create_tree_sidebar_lazy()
        self.tree_sidebar.setVisible(self._tree_toggle)
        self.tree_action.setChecked(self._tree_toggle)

    def _apply_tab_bar_visibility(self):
        """应用标签栏显示/隐藏状态"""
        self._custom_tab_bar.setCollapsed(not self._tab_bar_visible)
        self._custom_tab_bar.setVisible(self._tab_bar_visible)

    def toggle_tab_bar(self):
        """切换标签页栏显示/隐藏"""
        self._tab_bar_visible = not self._tab_bar_visible
        self._apply_tab_bar_visibility()
        self.tab_bar_action.setChecked(self._tab_bar_visible)
    
    def set_theme(self, name: str):
        """设置主题"""
        if self.theme_manager.apply_theme(name):
            theme_info = self.theme_manager.get_theme(name)
            display_name = theme_info['display_name'] if theme_info else name
            self.status_bar.showMessage(f"已切换到 {display_name}")
    
    def open_batch_rename(self):
        """打开批量重命名"""
        from widgets.batch_rename import BatchRenameDialog
        
        # 获取当前选中的文件
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            pane = current_widget.get_active_pane()
            if pane:
                indexes = pane.tree_view.selectedIndexes()
                files = []
                for index in indexes:
                    if index.column() == 0:
                        files.append(pane.model.filePath(pane._map_to_source(index)))
                
                if files:
                    dialog = BatchRenameDialog(files, self)
                    dialog.exec()
                    pane.navigate_to(pane.current_path)
                else:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.information(self, "提示", "请先选择要重命名的文件")
    
    def open_checksum(self):
        """打开校验和工具"""
        from widgets.checksum_tool import ChecksumDialog
        dialog = ChecksumDialog(parent=self)
        dialog.exec()

    def open_timestamp_tool(self):
        """打开时间戳转换工具"""
        from widgets.timestamp_tool import TimestampToolDialog
        dialog = TimestampToolDialog(parent=self)
        dialog.exec()
    
    def open_file_compare(self):
        """打开文件比较"""
        from widgets.file_compare import FileCompareDialog
        dialog = FileCompareDialog(parent=self)
        dialog.exec()
    
    def open_dir_sync(self):
        """打开目录同步"""
        from widgets.dir_sync import DirSyncDialog
        dialog = DirSyncDialog(parent=self)
        dialog.exec()
    
    def open_archive(self):
        """打开压缩包处理"""
        from widgets.archive_tool import ArchiveDialog
        dialog = ArchiveDialog(parent=self)
        dialog.exec()
    
    def open_file_split(self):
        """打开文件分割/合并"""
        from widgets.file_split import FileSplitDialog
        dialog = FileSplitDialog(parent=self)
        dialog.exec()
    
    def open_advanced_search(self):
        """打开高级搜索"""
        from widgets.advanced_search import AdvancedSearchDialog
        dialog = AdvancedSearchDialog(parent=self)
        dialog.exec()
    
    def switch_to_quad(self):
        """切换到四窗格模式"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            current_widget.switch_to_quad()
    
    def switch_to_dual(self):
        """切换到双窗格模式（上下两个）"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            current_widget.switch_to_dual()

    def switch_to_dual_horizontal(self):
        """切换到双窗格横向模式（左右两个）"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            current_widget.switch_to_dual_horizontal()

    def switch_to_2_1(self):
        """切换到上2下1模式"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            current_widget.switch_to_2_1()

    def switch_to_1_2(self):
        """切换到上1下2模式"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            current_widget.switch_to_1_2()
    
    def save_layout(self):
        """保存当前布局到配置文件"""
        import json
        import os
        
        config_dir = os.path.expanduser("~/.config/pan4dex")
        os.makedirs(config_dir, exist_ok=True)
        layout_file = os.path.join(config_dir, "layout.json")
        
        # 获取当前标签页的布局
        current_widget = self.tab_widget.currentWidget()
        if not isinstance(current_widget, QuadPaneWidget):
            return
        
        layout = {
            'version': '1.0',
            'mode': current_widget.get_layout_mode(),
            'panes': {}
        }
        
        for pane_name in ['pane1', 'pane2', 'pane3', 'pane4']:
            pane = getattr(current_widget, pane_name, None)
            if pane:
                layout['panes'][pane_name] = pane.get_state()
        
        try:
            with open(layout_file, 'w', encoding='utf-8') as f:
                json.dump(layout, f, ensure_ascii=False, indent=2)
            self.status_bar.showMessage(f"布局已保存到 {layout_file}")
        except Exception as e:
            self.status_bar.showMessage(f"保存布局失败: {e}")

    def load_layout(self):
        """从配置文件恢复布局"""
        import json
        import os
        
        layout_file = os.path.expanduser("~/.config/pan4dex/layout.json")
        
        if not os.path.exists(layout_file):
            self.status_bar.showMessage("未找到布局配置文件")
            return
        
        try:
            with open(layout_file, 'r', encoding='utf-8') as f:
                layout = json.load(f)
        except Exception as e:
            self.status_bar.showMessage(f"加载布局失败: {e}")
            return
        
        # 恢复当前标签页的布局
        current_widget = self.tab_widget.currentWidget()
        if not isinstance(current_widget, QuadPaneWidget):
            return
        
        panes_layout = layout.get('panes', {})
        for pane_name, state in panes_layout.items():
            pane = getattr(current_widget, pane_name, None)
            if pane:
                pane.set_state(state)
        
        self.status_bar.showMessage("布局已恢复")

    def show_about(self):
        """显示关于对话框"""
        from PyQt6.QtWidgets import QMessageBox
        import sys
        import os
        
        # 版本号和编译时间（来自全局配置，顶部已导入）
        try:
            if BUILD_TIME:
                version_str = f"版本: {VERSION} ({BUILD_TIME})"
            else:
                version_str = f"版本: {VERSION}"
            build_str = f"<p>编译时间: {BUILD_TIME}</p>" if BUILD_TIME else ""
        except ImportError:
            version_str = "版本: 0.9.4"
            build_str = ""

        # 携带/使用的 ExifTool 版本（用于拍摄日期列）
        try:
            from core.media_metadata import exiftool_version
            _exif_ver = exiftool_version()
            exif_str = f"<p>Exif 工具: ExifTool {_exif_ver}</p>" if _exif_ver else ""
        except Exception:
            exif_str = ""

        # 使用/携带的 7-Zip 版本（压缩/解压；系统优先，内置兜底）
        try:
            from core import archive_ops
            _v7, _src = archive_ops.version_source()
            _7z_str = f"<p>7-Zip: {_v7}（{_src}）</p>" if _v7 else ""
            if _v7 and _src == '系统':
                _b7 = archive_ops.builtin_version()
                if _b7:
                    _7z_str += f"<p>内置 7-Zip: {_b7}</p>"
        except Exception:
            _7z_str = ""

        QMessageBox.about(
            self,
            "关于 Pan4dex 万格",
            f"<h2>Pan4dex 万格</h2>"
            f"<p>跨平台四窗格文件管理器</p>"
            f"<p>{version_str}</p>"
            f"<p>{build_str}</p>"
            f"{exif_str}"
            f"{_7z_str}"
            f"<p>许可证: MIT</p>"
        )
    
    def open_settings(self):
        """打开设置对话框"""
        from widgets.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 应用设置
            settings = dialog.get_settings()

            # 持久化到 QSettings（主题/字体/工具栏/启动器）
            import json
            self.settings.setValue("theme", settings.get('theme', DEFAULT_THEME))
            self.settings.setValue("font_family", settings.get('font_family'))
            self.settings.setValue("font_size", settings.get('font_size', 9))
            self.settings.setValue("toolbar_buttons", settings.get('toolbar_buttons', {}))
            self.settings.setValue("launcher/apps", json.dumps(settings.get('launcher_apps', [])))

            # 应用主题
            theme = settings.get('theme', DEFAULT_THEME)
            self.theme_manager.apply_theme(theme)
            
            # 应用字体
            font_family = settings.get('font_family')
            font_size = settings.get('font_size', 9)
            if font_family and font_family != "系统默认":
                from PyQt6.QtGui import QFont
                font = QFont(font_family, font_size)
                QApplication.instance().setFont(font)
            
            # 应用工具栏按钮可见性
            toolbar_buttons = settings.get('toolbar_buttons', {})
            self.apply_toolbar_buttons(toolbar_buttons)

            # 刷新菜单栏右侧启动器按钮
            self.refresh_launcher_buttons()
            
            self.status_bar.showMessage("设置已应用")
    
    def apply_toolbar_buttons(self, config: dict):
        """应用工具栏按钮可见性"""
        for tab_index in range(self.tab_widget.count()):
            quad = self.tab_widget.widget(tab_index)
            if hasattr(quad, 'pane1'):
                for pane in [quad.pane1, quad.pane2, quad.pane3, quad.pane4]:
                    if pane is None:
                        continue
                    for btn_name, visible in config.items():
                        pane.set_button_visibility(btn_name, visible)

    def save_geometry(self):
        """保存窗口位置和大小"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
    
    def restore_geometry(self):
        """恢复窗口位置和大小"""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        window_state = self.settings.value("windowState")
        if window_state:
            self.restoreState(window_state)
    
    def closeEvent(self, event):
        """关闭窗口时保存状态"""
        self.save_geometry()
        self._auto_save_layout()
        super().closeEvent(event)
    
    def _auto_save_layout(self):
        """自动保存当前布局"""
        import json
        import os
        
        config_dir = os.path.expanduser("~/.config/pan4dex")
        os.makedirs(config_dir, exist_ok=True)
        layout_file = os.path.join(config_dir, "layout.json")
        
        current_widget = self.tab_widget.currentWidget()
        if not isinstance(current_widget, QuadPaneWidget):
            return
        
        layout = {
            'version': '1.0',
            'mode': current_widget.get_layout_mode(),
            'panes': {}
        }
        
        for pane_name in ['pane1', 'pane2', 'pane3', 'pane4']:
            pane = getattr(current_widget, pane_name, None)
            if pane:
                layout['panes'][pane_name] = pane.get_state()
        
        try:
            with open(layout_file, 'w', encoding='utf-8') as f:
                json.dump(layout, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


class QuadPaneWidget(QWidget):
    """四窗格组件 - 每个标签页包含四个独立窗格"""
    
    # 信号：窗格被激活
    pane_activated = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout_mode = "quad"  # 当前布局模式：quad/dual/dual_h/2_1/1_2
        
        # 创建四窗格
        self.create_quad_panes()
    
    def create_quad_panes(self):
        """创建四窗格布局"""
        # 目录树使用独立模型 + 延迟启动（隐藏的树不扫描磁盘），
        # 避免 QFileSystemModel 共享给多视图时 Qt 内部崩溃/滚动失效
        # 主分割器（垂直）
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 上部分割器（水平）
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        # 下部分割器（水平）
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 首屏只创建 pane1（加快窗口显示）；pane2/3/4 在事件循环启动后
        # 延迟创建（Pane 构造含 PathBar/文件模型/排序代理等，单个约 80ms）
        self.pane1 = Pane(pane_id="pane_1", parent=self)
        self.pane1.activated.connect(self.on_pane_activated)
        self.pane2 = None
        self.pane3 = None
        self.pane4 = None
        self._all_panes_created = False
        
        # 占位控件：延迟创建时用 replaceWidget 替换为真实窗格
        self._placeholder2 = QWidget()
        self._placeholder3 = QWidget()
        self._placeholder4 = QWidget()
        
        # 添加到分割器
        self.top_splitter.addWidget(self.pane1)
        self.top_splitter.addWidget(self._placeholder2)
        self.bottom_splitter.addWidget(self._placeholder3)
        self.bottom_splitter.addWidget(self._placeholder4)
        
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)
        
        # 设置初始比例
        self.main_splitter.setSizes([50, 50])
        self.top_splitter.setSizes([50, 50])
        self.bottom_splitter.setSizes([50, 50])
        
        self.layout.addWidget(self.main_splitter)
        
        # 事件循环启动后延迟创建其余窗格
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(250, self._create_remaining_panes)
    
    def _create_remaining_panes(self):
        """延迟创建 pane2/3/4（首屏显示后执行）"""
        if getattr(self, '_all_panes_created', False):
            return
        import time
        _t0 = time.perf_counter()
        self.pane2 = Pane(pane_id="pane_2", parent=self)
        self.pane3 = Pane(pane_id="pane_3", parent=self)
        self.pane4 = Pane(pane_id="pane_4", parent=self)
        self.pane2.activated.connect(self.on_pane_activated)
        self.pane3.activated.connect(self.on_pane_activated)
        self.pane4.activated.connect(self.on_pane_activated)
        # 用真实窗格替换占位
        self.top_splitter.replaceWidget(1, self.pane2)
        self.bottom_splitter.replaceWidget(0, self.pane3)
        self.bottom_splitter.replaceWidget(1, self.pane4)
        self._placeholder2.deleteLater()
        self._placeholder3.deleteLater()
        self._placeholder4.deleteLater()
        self._all_panes_created = True
        logger.info(f"[启动计时] 延迟创建 pane2-4: {(time.perf_counter()-_t0)*1000:.1f}ms")
    
    def _ensure_all_panes(self):
        """确保四个窗格都已创建（四窗格/双窗格切换等立即操作时调用）"""
        if not getattr(self, '_all_panes_created', False):
            self._create_remaining_panes()
    
    def on_pane_activated(self, pane):
        """窗格被激活"""
        self.pane_activated.emit(pane)
    
    def get_active_pane(self):
        """获取当前活动的窗格"""
        # 返回最后激活的窗格
        focus_widget = QApplication.focusWidget()
        for pane in [self.pane1, self.pane2, self.pane3, self.pane4]:
            if pane is not None and (pane == focus_widget or pane.isAncestorOf(focus_widget)):
                return pane
        return self.pane1
    
    def switch_to_quad(self):
        """四窗格模式（2×2）"""
        self._ensure_all_panes()
        self.pane1.show()
        self.pane2.show()
        self.pane3.show()
        self.pane4.show()
        self.top_splitter.show()
        self.bottom_splitter.show()
        self.layout_mode = "quad"
    
    def switch_to_dual(self):
        """双窗格竖向模式（上、下两个全宽）"""
        self._ensure_all_panes()
        self.pane1.show()
        self.pane3.show()
        self.pane2.hide()
        self.pane4.hide()
        self.top_splitter.show()
        self.bottom_splitter.show()
        self.layout_mode = "dual"

    def switch_to_dual_horizontal(self):
        """双窗格横向模式（左、右两个全高）"""
        self._ensure_all_panes()
        self.pane1.show()
        self.pane2.show()
        self.pane3.hide()
        self.pane4.hide()
        self.top_splitter.show()
        self.bottom_splitter.hide()  # 只保留上排，下排隐藏后上排占满全高
        self.layout_mode = "dual_h"

    def switch_to_2_1(self):
        """上2下1模式（上排两个并排，下排一个全宽）"""
        self._ensure_all_panes()
        self.pane1.show()
        self.pane2.show()
        self.pane3.show()
        self.pane4.hide()
        self.top_splitter.show()
        self.bottom_splitter.show()
        self.layout_mode = "2_1"

    def switch_to_1_2(self):
        """上1下2模式（上排一个全宽，下排两个并排）"""
        self._ensure_all_panes()
        self.pane1.show()
        self.pane3.show()
        self.pane4.show()
        self.pane2.hide()
        self.top_splitter.show()
        self.bottom_splitter.show()
        self.layout_mode = "1_2"

    def get_layout_mode(self):
        """当前布局模式"""
        return getattr(self, 'layout_mode', 'quad')

    def set_layout_mode(self, mode: str):
        """按名称切换布局模式（布局保存/恢复用）"""
        fn = {
            'quad': self.switch_to_quad,
            'dual': self.switch_to_dual,
            'dual_h': self.switch_to_dual_horizontal,
            '2_1': self.switch_to_2_1,
            '1_2': self.switch_to_1_2,
        }.get(mode)
        if fn:
            fn()
