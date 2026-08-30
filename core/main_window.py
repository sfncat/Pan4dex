"""
Pan4dex 万格 — 主窗口
"""
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QSplitter, QWidget, 
    QVBoxLayout, QStatusBar, QMenuBar,
    QToolBar, QLabel, QApplication, QMenu, QDialog
)
from PyQt6.QtCore import Qt, QSettings, QSize, QPoint, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QCursor

from core.pane import Pane
from widgets.preview_panel import PreviewPanel
from widgets.bookmark_sidebar import BookmarkSidebar
from widgets.tree_sidebar import TreeSidebar
from config.file_associations import FileAssociations
from config.theme_manager import ThemeManager


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Pan4dex 万格")
        self.setMinimumSize(1024, 768)
        
        # 设置应用图标
        from PyQt6.QtGui import QIcon
        import sys
        import os
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, 'resources', 'icons', 'icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 恢复窗口位置和大小
        self.settings = QSettings("sfncat", "Pan4dex")
        self.restore_geometry()
        
        # 文件关联
        self.file_associations = FileAssociations()
        
        # 主题管理器
        self.theme_manager = ThemeManager()
        
        # 预览面板状态
        self._preview_toggle = False
        
        # 当前活动窗格（目录树导航目标）
        self._active_pane = None

        # 创建 UI
        self.create_menu_bar()
        self.create_tool_bar()
        self.create_status_bar()
        self.create_central_widget()
        self.create_preview_panel()
        self.create_bookmark_sidebar()
        self.create_tree_sidebar()

        # 应用默认主题
        self.theme_manager.apply_theme("dark")
        
        # 自动恢复上次的布局
        self._auto_load_layout()
    
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
        panes_layout = layout.get('panes', {})
        if not panes_layout:
            return
        
        current_widget = self.tab_widget.currentWidget()
        if not isinstance(current_widget, QuadPaneWidget):
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
        """创建目录树侧边栏"""
        self.tree_sidebar = TreeSidebar(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_sidebar)
        self.tree_sidebar.setVisible(False)
        
        # 连接目录树点击信号 - 导航到当前活动窗格
        self.tree_sidebar.folder_clicked.connect(self.on_tree_folder_clicked)
    
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
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        # 右键菜单支持
        self.tab_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.customContextMenuRequested.connect(self.show_tab_context_menu)
        
        # 双击空白区域创建新标签页
        self.tab_widget.tabBarDoubleClicked.connect(self.on_tab_bar_double_clicked)
        
        self.setCentralWidget(self.tab_widget)
        
        # 创建第一个标签页
        self.new_tab()
    
    def create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
    
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
    
    def on_tab_bar_double_clicked(self, index):
        """双击标签栏空白区域创建新标签页，双击标签则重命名"""
        if index == -1:
            self.new_tab()
        else:
            self.rename_tab(index)
    
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
        self.tree_sidebar.setVisible(self._tree_toggle)
        self.tree_action.setChecked(self._tree_toggle)
    
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
                        files.append(pane.model.filePath(index))
                
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
        """切换到双窗格模式"""
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            current_widget.switch_to_dual()
    
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
        
        # 动态获取版本号和编译时间
        try:
            from main import __version__, __build_time__
            if __build_time__:
                version_str = f"版本: {__version__} ({__build_time__})"
            else:
                version_str = f"版本: {__version__}"
            build_str = f"<p>编译时间: {__build_time__}</p>" if __build_time__ else ""
        except ImportError:
            version_str = "版本: 0.9.4"
            build_str = ""
        
        QMessageBox.about(
            self,
            "关于 Pan4dex 万格",
            f"<h2>Pan4dex 万格</h2>"
            f"<p>跨平台四窗格文件管理器</p>"
            f"<p>{version_str}</p>"
            f"<p>{build_str}</p>"
            f"<p>许可证: MIT</p>"
        )
    
    def open_settings(self):
        """打开设置对话框"""
        from widgets.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 应用设置
            settings = dialog.get_settings()
            
            # 应用主题
            theme = settings.get('theme', 'dark')
            self.theme_manager.apply_theme(theme)
            
            # 应用字体
            font_family = settings.get('font_family')
            font_size = settings.get('font_size', 9)
            if font_family and font_family != "系统默认":
                from PyQt6.QtGui import QFont
                font = QFont(font_family, font_size)
                QApplication.instance().setFont(font)
            
            self.status_bar.showMessage("设置已应用")
    
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
        
        # 创建四窗格
        self.create_quad_panes()
    
    def create_quad_panes(self):
        """创建四窗格布局"""
        # 主分割器（垂直）
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 上部分割器（水平）
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        # 下部分割器（水平）
        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 创建四个窗格
        self.pane1 = Pane(pane_id="pane_1", parent=self)
        self.pane2 = Pane(pane_id="pane_2", parent=self)
        self.pane3 = Pane(pane_id="pane_3", parent=self)
        self.pane4 = Pane(pane_id="pane_4", parent=self)
        
        # 连接激活信号
        self.pane1.activated.connect(self.on_pane_activated)
        self.pane2.activated.connect(self.on_pane_activated)
        self.pane3.activated.connect(self.on_pane_activated)
        self.pane4.activated.connect(self.on_pane_activated)
        
        # 添加到分割器
        self.top_splitter.addWidget(self.pane1)
        self.top_splitter.addWidget(self.pane2)
        self.bottom_splitter.addWidget(self.pane3)
        self.bottom_splitter.addWidget(self.pane4)
        
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)
        
        # 设置初始比例
        self.main_splitter.setSizes([50, 50])
        self.top_splitter.setSizes([50, 50])
        self.bottom_splitter.setSizes([50, 50])
        
        self.layout.addWidget(self.main_splitter)
    
    def on_pane_activated(self, pane):
        """窗格被激活"""
        self.pane_activated.emit(pane)
    
    def get_active_pane(self):
        """获取当前活动的窗格"""
        # 返回最后激活的窗格
        focus_widget = QApplication.focusWidget()
        for pane in [self.pane1, self.pane2, self.pane3, self.pane4]:
            if pane == focus_widget or pane.isAncestorOf(focus_widget):
                return pane
        return self.pane1
    
    def switch_to_quad(self):
        """切换到四窗格模式"""
        self.pane1.show()
        self.pane2.show()
        self.pane3.show()
        self.pane4.show()
    
    def switch_to_dual(self):
        """切换到双窗格模式"""
        self.pane1.show()
        self.pane3.show()
        self.pane2.hide()
        self.pane4.hide()
