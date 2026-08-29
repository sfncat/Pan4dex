"""
Pan4dex 万格 — 单窗格组件
"""
import logging

logger = logging.getLogger("pan4dex.pane")
from PyQt6.QtGui import QFileSystemModel, QAction, QKeySequence, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QProgressBar,
    QLabel, QMenu, QMessageBox, QInputDialog, QLineEdit, QHBoxLayout, QTabWidget
)
from PyQt6.QtCore import Qt, QDir, QMimeData, pyqtSignal, QThread, QPoint, QEvent
import os

from widgets.path_bar import PathBar
from widgets.pane_tree_view import PaneTreeView
from core.file_operations import FileOperations, FileOperationType, FileOperationResult


class Pane(QWidget):
    """单个窗格组件"""
    
    # 信号
    path_changed = pyqtSignal(str)  # 路径变更信号
    activated = pyqtSignal(object)  # 窗格被激活信号
    
    def __init__(self, pane_id: str, parent=None):
        super().__init__(parent)
        
        self.pane_id = pane_id
        self.current_path = QDir.homePath()
        self.file_ops = FileOperations()
        self.clipboard = []  # 剪贴板：存储复制的文件路径
        self.clipboard_action = None  # 'copy' or 'cut'
        
        # 导航历史（支持前进/后退）
        self._nav_history = [self.current_path]
        self._nav_index = 0
        
        # 拖拽起始位置
        self.drag_start_pos = None
        
        # 创建 UI
        self.init_ui()
        
        # 初始化模型
        self.init_model()
        
        # 设置默认路径
        self.navigate_to(self.current_path)
    
    def focusInEvent(self, a0):
        """窗格获得焦点时发出激活信号"""
        self.activated.emit(self)
        super().focusInEvent(a0)
    
    def eventFilter(self, obj, event):
        """事件过滤器"""
        logger.debug(f"eventFilter: obj={obj.__class__.__name__}, event={event.type()}")
        
        # 鼠标侧键导航（后退/前进）- viewport 上捕获
        if obj == self.tree_view.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                self.activated.emit(self)
                if hasattr(event, 'button'):
                    btn = event.button()
                    logger.debug(f"viewport mouse press: button={btn}")
                    if btn == Qt.MouseButton.BackButton:
                        logger.info("Mouse back button -> go_back")
                        self.go_back()
                        return True
                    elif btn == Qt.MouseButton.ForwardButton:
                        logger.info("Mouse forward button -> go_forward")
                        self.go_forward()
                        return True
            elif event.type() == QEvent.Type.FocusIn:
                self.activated.emit(self)
        
        # 标签栏双击检测
        if hasattr(self, '_tab_bar') and event.type() == QEvent.Type.MouseButtonDblClick:
            if obj == self._tab_bar:
                pos = event.pos()
                index = self._tab_bar.tabAt(pos)
                logger.debug(f"tabBar doubleClick: index={index}")
                self._on_tab_bar_double_clicked(index)
                return True
            elif obj == self.pane_tabs:
                logger.debug(f"paneTabs doubleClick -> add tab")
                self.add_pane_tab()
                return True
        
        return super().eventFilter(obj, event)
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 路径栏
        self.path_bar = PathBar()
        self.path_bar.path_entered.connect(self.on_path_entered)
        self.path_bar.tree_toggle_requested.connect(self.toggle_tree)
        self.path_bar.tabs_toggle_requested.connect(self.toggle_tabs)
        self.layout.addWidget(self.path_bar)

        # 设置焦点策略，让 focusInEvent 能触发
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 水平容器：左侧目录树 + 右侧文件列表
        self.h_container = QWidget()
        self.h_layout = QHBoxLayout(self.h_container)
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(0)

        # 内嵌目录树
        self.pane_tree_view = PaneTreeView()
        self.pane_tree_view.folder_clicked.connect(self.on_pane_tree_clicked)
        self.pane_tree_view.setVisible(False)  # 默认隐藏
        self.h_layout.addWidget(self.pane_tree_view)

        # 文件列表容器
        self.file_list_widget = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_widget)
        self.file_list_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list_layout.setSpacing(0)

        # 文件列表
        self.tree_view = QTreeView()
        self.tree_view.setRootIsDecorated(False)
        self.tree_view.setAlternatingRowColors(False)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(False)
        self.tree_view.setAllColumnsShowFocus(True)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_view.viewport().installEventFilter(self)



        # 拖拽支持
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setDragDropMode(QTreeView.DragDropMode.DragDrop)

        self.file_list_layout.addWidget(self.tree_view)

        self.h_layout.addWidget(self.file_list_widget, 1)  # 文件列表占据剩余空间

        self.layout.addWidget(self.h_container)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(3)
        self.progress_bar.setTextVisible(False)
        self.layout.addWidget(self.progress_bar)

        # 状态栏
        self.status_label = QLabel()
        self.status_label.setContentsMargins(5, 2, 5, 2)
        self.layout.addWidget(self.status_label)

        # 窗格内标签页栏（默认隐藏）
        self.pane_tabs = QTabWidget()
        self.pane_tabs.setMaximumHeight(30)
        self.pane_tabs.setTabsClosable(True)
        self.pane_tabs.tabCloseRequested.connect(self.close_pane_tab)
        self.pane_tabs.currentChanged.connect(self.on_pane_tab_changed)
        self.pane_tabs.setVisible(False)
        # 标签栏右键菜单
        self.pane_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pane_tabs.customContextMenuRequested.connect(self.show_pane_tab_context_menu)
        # 双击标签栏处理 - 安装在 QTabWidget 上
        self._tab_bar = self.pane_tabs.tabBar()
        self._tab_bar.installEventFilter(self)
        self.pane_tabs.installEventFilter(self)
        self.layout.addWidget(self.pane_tabs)

        # 初始化第一个标签页
        self._pane_tab_paths = [self.current_path]
        self.pane_tabs.addTab(QLabel(), os.path.basename(self.current_path) if os.path.basename(self.current_path) else self.current_path)
        

    
    def init_model(self):
        """初始化文件系统模型"""
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.model.setFilter(
            QDir.Filter.AllDirs | 
            QDir.Filter.Files | 
            QDir.Filter.NoDotAndDotDot |
            QDir.Filter.Hidden
        )
        
        self.tree_view.setModel(self.model)
        
        # 选择变化时更新预览（需要在 model 设置之后）
        self.tree_view.selectionModel().selectionChanged.connect(self.on_selection_changed)
    
    def get_state(self) -> dict:
        """获取窗格状态"""
        return {
            'current_path': self.current_path,
            'tree_visible': self.pane_tree_view.isVisible(),
            'tabs_visible': self.pane_tabs.isVisible(),
            'tab_paths': self._pane_tab_paths.copy(),
            'tab_current': self.pane_tabs.currentIndex() if self.pane_tabs.isVisible() else 0,
        }

    def set_state(self, state: dict):
        """恢复窗格状态"""
        if not state:
            return
        
        # 恢复标签页
        tab_paths = state.get('tab_paths', [])
        if tab_paths:
            # 清除现有标签页
            while self.pane_tabs.count() > 0:
                self.pane_tabs.removeTab(0)
            self._pane_tab_paths = []
            
            # 恢复标签页
            for path in tab_paths:
                self._pane_tab_paths.append(path)
                self.pane_tabs.addTab(QLabel(), os.path.basename(path) if os.path.basename(path) else path)
            
            # 恢复当前标签页
            current_idx = state.get('tab_current', 0)
            if 0 <= current_idx < len(tab_paths):
                self.pane_tabs.setCurrentIndex(current_idx)
                path = tab_paths[current_idx]
            else:
                path = tab_paths[0] if tab_paths else state.get('current_path', QDir.homePath())
            
            self.current_path = path
            self.path_bar.set_path(path)
            index = self.model.setRootPath(path)
            self.tree_view.setRootIndex(index)
            self.pane_tree_view.expand_to_path(path)
            self.update_status_bar()
        
        # 恢复目录树可见性
        if state.get('tree_visible', False):
            self.set_tree_visible(True)
        else:
            self.set_tree_visible(False)
        
        # 恢复标签栏可见性
        if state.get('tabs_visible', False):
            self.pane_tabs.setVisible(True)
            self.path_bar.set_tabs_button_checked(True)
        else:
            self.pane_tabs.setVisible(False)
            self.path_bar.set_tabs_button_checked(False)

    def navigate_to(self, path: str):
        """导航到指定路径"""
        import os
        if os.path.isdir(path):
            self.current_path = path
            self.path_bar.set_path(path)

            index = self.model.setRootPath(path)
            self.tree_view.setRootIndex(index)

            # 同步展开内嵌目录树到当前路径
            self.pane_tree_view.expand_to_path(path)

            # 更新当前标签页的名称和路径
            current_idx = self.pane_tabs.currentIndex()
            if self.pane_tabs.isVisible() and 0 <= current_idx < len(self._pane_tab_paths):
                self._pane_tab_paths[current_idx] = path
                self.pane_tabs.setTabText(current_idx, os.path.basename(path) if os.path.basename(path) else path)

            # 更新导航历史
            if self._nav_history[self._nav_index] != path:
                # 截断前进历史
                self._nav_history = self._nav_history[:self._nav_index + 1]
                self._nav_history.append(path)
                self._nav_index = len(self._nav_history) - 1

            self.update_status_bar()
            self.path_changed.emit(path)

    def go_back(self):
        """后退到上一个目录"""
        if self._nav_index > 0:
            self._nav_index -= 1
            path = self._nav_history[self._nav_index]
            self._navigate_no_history(path)

    def go_forward(self):
        """前进到下一个目录"""
        if self._nav_index < len(self._nav_history) - 1:
            self._nav_index += 1
            path = self._nav_history[self._nav_index]
            self._navigate_no_history(path)

    def _navigate_no_history(self, path: str):
        """导航但不记录历史"""
        import os
        if os.path.isdir(path):
            self.current_path = path
            self.path_bar.set_path(path)

            index = self.model.setRootPath(path)
            self.tree_view.setRootIndex(index)

            self.pane_tree_view.expand_to_path(path)

            current_idx = self.pane_tabs.currentIndex()
            if self.pane_tabs.isVisible() and 0 <= current_idx < len(self._pane_tab_paths):
                self._pane_tab_paths[current_idx] = path
                self.pane_tabs.setTabText(current_idx, os.path.basename(path) if os.path.basename(path) else path)

            self.update_status_bar()
            self.path_changed.emit(path)

    def on_pane_tree_clicked(self, path: str):
        """内嵌目录树点击 - 导航到本窗格"""
        self.navigate_to(path)

    def set_tree_visible(self, visible: bool):
        """设置内嵌目录树可见性"""
        self.pane_tree_view.setVisible(visible)
        self.path_bar.set_tree_button_checked(visible)
        if visible:
            self.pane_tree_view.setFixedWidth(200)
            self.h_layout.setStretch(0, 0)
            self.h_layout.setStretch(1, 1)
        else:
            self.h_layout.setStretch(0, 0)
            self.h_layout.setStretch(1, 1)

    def toggle_tree(self):
        """切换本窗格的目录树"""
        visible = self.pane_tree_view.isVisible()
        self.set_tree_visible(not visible)

    def toggle_tabs(self):
        """切换本窗格的标签页栏"""
        visible = self.pane_tabs.isVisible()
        self.pane_tabs.setVisible(not visible)
        self.path_bar.set_tabs_button_checked(not visible)

    def _on_tab_bar_double_clicked(self, index):
        """双击标签栏"""
        if index == -1:
            # 双击空白处新建标签
            self.add_pane_tab()
        else:
            # 双击标签重命名
            self._rename_pane_tab(index)

    def _rename_pane_tab(self, index):
        """重命名标签页"""
        from PyQt6.QtWidgets import QInputDialog
        
        current_name = self.pane_tabs.tabText(index)
        new_name, ok = QInputDialog.getText(
            self, "重命名标签页", "新名称:", text=current_name
        )
        if ok and new_name.strip():
            self.pane_tabs.setTabText(index, new_name.strip())

    def show_pane_tab_context_menu(self, position):
        """显示窗格标签栏右键菜单"""
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
        
        new_tab_action = QAction("新建标签页(&N)", self)
        new_tab_action.triggered.connect(lambda: self.add_pane_tab())
        menu.addAction(new_tab_action)
        
        close_tab_action = QAction("关闭标签页(&C)", self)
        close_tab_action.triggered.connect(lambda: self.close_pane_tab(self.pane_tabs.currentIndex()))
        menu.addAction(close_tab_action)
        
        menu.exec(QCursor.pos())

    def close_pane_tab(self, index):
        """关闭窗格内标签页"""
        if self.pane_tabs.count() > 1:
            self.pane_tabs.removeTab(index)
            if index < len(self._pane_tab_paths):
                self._pane_tab_paths.pop(index)

    def on_pane_tab_changed(self, index):
        """窗格内标签页切换"""
        if hasattr(self, 'model') and 0 <= index < len(self._pane_tab_paths):
            path = self._pane_tab_paths[index]
            if os.path.isdir(path):
                # 更新当前路径并刷新文件列表
                self.current_path = path
                self.path_bar.set_path(path)
                idx = self.model.setRootPath(path)
                self.tree_view.setRootIndex(idx)
                self.pane_tree_view.expand_to_path(path)
                self.update_status_bar()

    def add_pane_tab(self, path: str = None):
        """添加窗格内标签页"""
        if path is None:
            path = self.current_path
        self._pane_tab_paths.append(path)
        self.pane_tabs.addTab(QLabel(), os.path.basename(path) if os.path.basename(path) else path)
        # 添加标签页后显示标签页栏
        if not self.pane_tabs.isVisible():
            self.pane_tabs.setVisible(True)
            self.path_bar.set_tabs_button_checked(True)

    def on_path_entered(self, path: str):
        """路径栏输入处理"""
        import os
        if os.path.isdir(path):
            self.navigate_to(path)
        else:
            # 路径无效，恢复原路径
            self.path_bar.set_path(self.current_path)
    
    def on_item_double_clicked(self, index):
        """双击项目处理"""
        path = self.model.filePath(index)
        import os
        if os.path.isdir(path):
            self.navigate_to(path)
        else:
            # 打开文件
            self.open_file(path)
    
    def open_file(self, file_path: str):
        """打开文件"""
        # 尝试使用文件关联
        main_window = self.window()
        if hasattr(main_window, 'file_associations'):
            if main_window.file_associations.open_file(file_path):
                return
        
        # 回退到系统默认
        import subprocess
        import sys
        
        if sys.platform == "win32":
            import os
            os.startfile(file_path)
        else:
            subprocess.Popen(["xdg-open", file_path])
    
    def on_selection_changed(self):
        """选择变化时更新预览"""
        indexes = self.tree_view.selectedIndexes()
        if indexes:
            path = self.model.filePath(indexes[0])
            main_window = self.window()
            if hasattr(main_window, 'preview_panel') and main_window.preview_panel.isVisible():
                main_window.preview_panel.preview_file(path)
    
    def update_status_bar(self):
        """更新状态栏"""
        import os
        try:
            entries = os.listdir(self.current_path)
            files = [f for f in entries if os.path.isfile(os.path.join(self.current_path, f))]
            dirs = [d for d in entries if os.path.isdir(os.path.join(self.current_path, d))]
            self.status_label.setText(f"{len(dirs)} 个目录, {len(files)} 个文件")
        except PermissionError:
            self.status_label.setText("无权限访问")
    
    def show_context_menu(self, position):
        """显示右键菜单"""
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
        
        # 获取选中项
        indexes = self.tree_view.selectedIndexes()
        
        if indexes:
            # 有选中项
            open_action = QAction("打开(&O)", self)
            open_action.triggered.connect(self.open_selected)
            menu.addAction(open_action)
            
            menu.addSeparator()
            
            copy_action = QAction("复制(&C)", self)
            copy_action.setShortcut(QKeySequence("Ctrl+C"))
            copy_action.triggered.connect(self.copy_selected)
            menu.addAction(copy_action)
            
            cut_action = QAction("剪切(&X)", self)
            cut_action.setShortcut(QKeySequence("Ctrl+X"))
            cut_action.triggered.connect(self.cut_selected)
            menu.addAction(cut_action)
            
            menu.addSeparator()
            
            delete_action = QAction("删除(&D)", self)
            delete_action.setShortcut(QKeySequence("Delete"))
            delete_action.triggered.connect(self.delete_selected)
            menu.addAction(delete_action)
            
            rename_action = QAction("重命名(&R)", self)
            rename_action.setShortcut(QKeySequence("F2"))
            rename_action.triggered.connect(self.rename_selected)
            menu.addAction(rename_action)
            
            menu.addSeparator()
            
            # 如果选中的是目录，添加到收藏夹
            selected_path = None
            for idx in indexes:
                if idx.column() == 0:
                    path = self.model.filePath(idx)
                    if os.path.isdir(path):
                        selected_path = path
                        break
            
            if selected_path:
                add_bookmark_action = QAction("添加到收藏夹(&B)", self)
                add_bookmark_action.triggered.connect(
                    lambda: self.add_to_bookmarks(selected_path)
                )
                menu.addAction(add_bookmark_action)
            
            menu.addSeparator()
            
            terminal_action = QAction("打开终端(&T)", self)
            terminal_action.triggered.connect(self.open_terminal_here)
            menu.addAction(terminal_action)
        else:
            # 空白区域
            new_folder_action = QAction("新建文件夹(&F)", self)
            new_folder_action.triggered.connect(self.new_folder)
            menu.addAction(new_folder_action)
            
            new_file_action = QAction("新建文件(&N)", self)
            new_file_action.triggered.connect(self.new_file)
            menu.addAction(new_file_action)
            
            menu.addSeparator()
            
            paste_action = QAction("粘贴(&V)", self)
            paste_action.setShortcut(QKeySequence("Ctrl+V"))
            paste_action.triggered.connect(self.paste)
            menu.addAction(paste_action)
            
            menu.addSeparator()
            
            new_tab_action = QAction("新建标签页(&T)", self)
            new_tab_action.triggered.connect(lambda: self.add_pane_tab())
            menu.addAction(new_tab_action)
            
            menu.addSeparator()
            
            terminal_action = QAction("打开终端(&T)", self)
            terminal_action.triggered.connect(self.open_terminal_here)
            menu.addAction(terminal_action)
        
        menu.exec(QCursor.pos())
    
    def open_selected(self):
        """打开选中项"""
        indexes = self.tree_view.selectedIndexes()
        if indexes:
            path = self.model.filePath(indexes[0])
            import os
            if os.path.isdir(path):
                self.navigate_to(path)
            else:
                self.open_file(path)
    
    def copy_selected(self):
        """复制选中项"""
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(index))
        
        if paths:
            self.clipboard = paths
            self.clipboard_action = 'copy'
            self.status_label.setText(f"已复制 {len(paths)} 个项目")
    
    def cut_selected(self):
        """剪切选中项"""
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(index))
        
        if paths:
            self.clipboard = paths
            self.clipboard_action = 'cut'
            self.status_label.setText(f"已剪切 {len(paths)} 个项目")
    
    def paste(self):
        """粘贴"""
        if not self.clipboard:
            return
        
        if self.clipboard_action == 'copy':
            self.file_ops.set_progress_callback(self._on_copy_progress)
            self.file_ops.copy(self.clipboard, self.current_path)
            self.file_ops.set_progress_callback(None)
        elif self.clipboard_action == 'cut':
            self.file_ops.set_progress_callback(self._on_copy_progress)
            self.file_ops.move(self.clipboard, self.current_path)
            self.file_ops.set_progress_callback(None)
            self.clipboard = []
            self.clipboard_action = None
        
        self.navigate_to(self.current_path)
        self.hide_progress()
    
    def _on_copy_progress(self, percent: int, filename: str):
        """复制进度回调"""
        self.show_progress(percent)
        self.status_label.setText(f"正在复制: {filename}")
    
    def delete_selected(self):
        """删除选中项"""
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(index))
        
        if not paths:
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {len(paths)} 个项目到回收站吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.file_ops.set_progress_callback(self._on_copy_progress)
            result = self.file_ops.delete(paths, safe=True)
            self.file_ops.set_progress_callback(None)
            
            if result.success:
                self.status_label.setText(f"已删除 {result.files_affected} 个项目")
            else:
                QMessageBox.warning(self, "删除失败", result.error)
            
            self.navigate_to(self.current_path)
            self.hide_progress()
    
    def rename_selected(self):
        """重命名选中项"""
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            return
        
        path = self.model.filePath(indexes[0])
        old_name = os.path.basename(path)
        
        new_name, ok = QInputDialog.getText(
            self, "重命名", "新名称:", QLineEdit.EchoMode.Normal, old_name
        )
        
        if ok and new_name and new_name != old_name:
            result = self.file_ops.rename(path, new_name)
            if result.success:
                self.navigate_to(self.current_path)
            else:
                QMessageBox.warning(self, "重命名失败", result.error)
    
    def add_to_bookmarks(self, path):
        """添加到收藏夹"""
        main_window = self.window()
        if main_window and hasattr(main_window, 'bookmark_sidebar'):
            main_window.bookmark_sidebar.add_bookmark_with_path(path)
    
    def new_folder(self):
        """新建文件夹"""
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "文件夹名称:", QLineEdit.EchoMode.Normal, "新建文件夹"
        )
        
        if ok and name:
            result = self.file_ops.create_folder(self.current_path, name)
            if result.success:
                self.navigate_to(self.current_path)
            else:
                QMessageBox.warning(self, "创建失败", result.error)
    
    def new_file(self):
        """新建文件"""
        name, ok = QInputDialog.getText(
            self, "新建文件", "文件名称:", QLineEdit.EchoMode.Normal, "新建文件.txt"
        )
        
        if ok and name:
            result = self.file_ops.create_file(self.current_path, name)
            if result.success:
                self.navigate_to(self.current_path)
            else:
                QMessageBox.warning(self, "创建失败", result.error)
    
    def paste(self):
        """粘贴"""
        pass  # TODO
    
    def open_terminal_here(self):
        """在当前目录打开终端"""
        import subprocess
        import shutil
        import sys
        import os
        
        if sys.platform == "win32":
            # Windows 终端
            terminal = None
            # 按优先级检测 Windows 终端
            windows_terminals = [
                ("Windows Terminal", "wt.exe", [ "-d", "{path}"]),
                ("PowerShell 7", "pwsh.exe", ["-WorkingDirectory", "{path}"]),
                ("PowerShell", "powershell.exe", ["-NoExit", "-Command", "Set-Location '{path}'"]),
                ("Command Prompt", "cmd.exe", ["/K", "cd /d", "{path}"]),
            ]
            
            for name, exe, args_template in windows_terminals:
                if shutil.which(exe):
                    terminal = (name, exe, args_template)
                    break
            
            if terminal:
                name, exe, args_template = terminal
                args = [arg.replace("{path}", self.current_path) for arg in args_template]
                subprocess.Popen([exe] + args)
            else:
                QMessageBox.warning(self, "错误", "未找到可用的终端")
        else:
            # Linux 终端 - 按用户配置 → 系统默认 → 已安装终端 的顺序
            terminal = None
            
            # 1. 检测用户配置的终端（从配置文件读取）
            config_file = os.path.expanduser("~/.config/pan4dex/settings.json")
            if os.path.exists(config_file):
                try:
                    import json
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                    user_terminal = config.get('terminal', '')
                    if user_terminal and shutil.which(user_terminal):
                        terminal = user_terminal
                except:
                    pass
            
            # 2. 检测系统默认终端
            if not terminal:
                # 检测 xdg-mime 设置的默认终端
                try:
                    result = subprocess.run(
                        ["xdg-mime", "query", "default", "x-scheme-handler/terminal"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        desktop_file = result.stdout.strip()
                        # 从 .desktop 文件获取 Exec
                        desktop_paths = [
                            "/usr/share/applications/" + desktop_file,
                            "/usr/local/share/applications/" + desktop_file,
                        ]
                        for dp in desktop_paths:
                            if os.path.exists(dp):
                                with open(dp, 'r') as f:
                                    for line in f:
                                        if line.startswith("Exec="):
                                            cmd = line.strip()[5:].split()[0]
                                            if shutil.which(cmd):
                                                terminal = cmd
                                                break
                                    if terminal:
                                        break
                except:
                    pass
            
            # 3. 按优先级检测已安装的终端
            if not terminal:
                linux_terminals = [
                    "x-terminal-emulator",  # Debian/Ubuntu 系统链接
                    "gnome-terminal",
                    "konsole",
                    "xfce4-terminal",
                    "mate-terminal",
                    "terminator",
                    "tilix",
                    "alacritty",
                    "kitty",
                    "urxvt",
                    "rxvt",
                    "xterm",
                ]
                for term in linux_terminals:
                    if shutil.which(term):
                        terminal = term
                        break
            
            if terminal:
                if terminal in ["gnome-terminal", "mate-terminal", "tilix"]:
                    subprocess.Popen([terminal, f"--working-directory={self.current_path}"])
                elif terminal == "konsole":
                    subprocess.Popen([terminal, "--workdir", self.current_path])
                elif terminal == "xfce4-terminal":
                    subprocess.Popen([terminal, f"--working-directory={self.current_path}"])
                elif terminal == "terminator":
                    subprocess.Popen([terminal, f"--working-directory={self.current_path}"])
                elif terminal == "alacritty":
                    subprocess.Popen([terminal, "--working-directory", self.current_path])
                elif terminal == "kitty":
                    subprocess.Popen([terminal, "--directory", self.current_path])
                else:
                    subprocess.Popen([terminal], cwd=self.current_path)
            else:
                QMessageBox.warning(self, "错误", "未找到可用的终端")
    
    def dragEnterEvent(self, event):
        """拖拽进入"""
        if event.mimeData().hasUrls():
            self.setStyleSheet(self.styleSheet() + """
                QTreeView { border: 2px solid #2196F3; }
            """)
            event.accept()
        elif event.mimeData().hasFormat("application/x-pan4dex-drag"):
            self.setStyleSheet(self.styleSheet() + """
                QTreeView { border: 2px solid #2196F3; }
            """)
            event.accept()
    
    def dragLeaveEvent(self, event):
        """拖拽离开"""
        self.init_ui_style()
        event.accept()
    
    def dropEvent(self, event):
        """拖拽释放"""
        self.init_ui_style()
        
        # 处理跨窗格拖拽
        if event.mimeData().hasFormat("application/x-pan4dex-drag"):
            import json
            data = json.loads(event.mimeData().data("application/x-pan4dex-drag").data().decode())
            source_pane_id = data.get("source_pane_id", "")
            files = data.get("files", [])
            action = data.get("default_action", "copy")
            
            if files:
                if action == "copy":
                    self.file_ops.set_progress_callback(self._on_copy_progress)
                    self.file_ops.copy(files, self.current_path)
                    self.file_ops.set_progress_callback(None)
                elif action == "move":
                    self.file_ops.set_progress_callback(self._on_copy_progress)
                    self.file_ops.move(files, self.current_path)
                    self.file_ops.set_progress_callback(None)
                
                self.navigate_to(self.current_path)
                self.hide_progress()
            
            event.accept()
        elif event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            files = [url.toLocalFile() for url in urls if url.isLocalFile()]
            
            if files:
                self.file_ops.set_progress_callback(self._on_copy_progress)
                self.file_ops.copy(files, self.current_path)
                self.file_ops.set_progress_callback(None)
                self.navigate_to(self.current_path)
                self.hide_progress()
            
            event.accept()
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动 - 处理拖拽开始"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        
        if not self.drag_start_pos:
            super().mouseMoveEvent(event)
            return
        
        # 检查是否移动了足够的距离
        if (event.pos() - self.drag_start_pos).manhattanLength() < 10:
            super().mouseMoveEvent(event)
            return
        
        # 获取选中的文件
        indexes = self.tree_view.selectedIndexes()
        if not indexes:
            super().mouseMoveEvent(event)
            return
        
        paths = []
        for index in indexes:
            if index.column() == 0:
                paths.append(self.model.filePath(index))
        
        if not paths:
            super().mouseMoveEvent(event)
            return
        
        # 创建拖拽对象
        from PyQt6.QtGui import QDrag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # 设置自定义 MIME 数据
        import json
        drag_data = {
            "source_pane_id": self.pane_id,
            "files": paths,
            "default_action": "copy"
        }
        mime_data.setData(
            "application/x-pan4dex-drag",
            json.dumps(drag_data).encode()
        )
        
        # 同时设置 URL 数据（兼容外部应用）
        from PyQt6.QtCore import QUrl
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime_data.setUrls(urls)
        
        drag.setMimeData(mime_data)
        
        # 执行拖拽
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
    
    def init_ui_style(self):
        """恢复默认样式"""
        self.setStyleSheet("""
            QTreeView {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                selection-background-color: #2196F3;
                outline: none;
            }
            QTreeView::item:hover {
                background-color: #2A2A2A;
            }
            QTreeView::item:selected {
                background-color: #2196F3;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: #CCCCCC;
                border: 1px solid #404040;
                padding: 5px;
            }
            QProgressBar {
                background-color: #2D2D2D;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
            }
            QLabel {
                color: #888888;
                font-size: 11px;
            }
        """)
    
    def show_progress(self, percent: int):
        """显示进度"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percent)
    
    def hide_progress(self):
        """隐藏进度"""
        self.progress_bar.setVisible(False)
