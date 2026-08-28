"""
Pan4dex 万格 — 单窗格组件
"""
from PyQt6.QtGui import QFileSystemModel, QAction, QKeySequence, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QProgressBar, 
    QLabel, QMenu, QMessageBox, QInputDialog, QLineEdit
)
from PyQt6.QtCore import Qt, QDir, QMimeData, pyqtSignal, QThread, QPoint, QEvent
import os

from widgets.path_bar import PathBar
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
    
    def eventFilter(self, a0, a1):
        """事件过滤器 - 检测 tree_view 获得焦点或点击"""
        if a0 == self.tree_view:
            if a1.type() == QEvent.Type.FocusIn:
                self.activated.emit(self)
            elif a1.type() == QEvent.Type.MouseButtonPress:
                self.activated.emit(self)
        return super().eventFilter(a0, a1)
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 路径栏
        self.path_bar = PathBar()
        self.path_bar.path_entered.connect(self.on_path_entered)
        self.layout.addWidget(self.path_bar)
        
        # 设置焦点策略，让 focusInEvent 能触发
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 文件列表
        self.tree_view = QTreeView()
        self.tree_view.setRootIsDecorated(False)
        # 禁用交替行颜色，避免 Windows 上白底灰字问题
        self.tree_view.setAlternatingRowColors(False)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.setItemsExpandable(False)
        self.tree_view.setAllColumnsShowFocus(True)
        self.tree_view.doubleClicked.connect(self.on_item_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        # 安装事件过滤器，检测 tree_view 获得焦点时发出 activated 信号
        self.tree_view.installEventFilter(self)
        
        # 强制设置调色板，防止 Windows 原生主题覆盖
        from PyQt6.QtGui import QPalette, QColor
        palette = self.tree_view.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#1E1E1E"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1E1E1E"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#E0E0E0"))
        self.tree_view.setPalette(palette)
        
        # 拖拽支持
        self.tree_view.setDragEnabled(True)
        self.tree_view.setAcceptDrops(True)
        self.tree_view.setDropIndicatorShown(True)
        self.tree_view.setDragDropMode(QTreeView.DragDropMode.DragDrop)
        
        self.layout.addWidget(self.tree_view)
        
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
        
        # 设置样式
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
    
    def navigate_to(self, path: str):
        """导航到指定路径"""
        import os
        if os.path.isdir(path):
            self.current_path = path
            self.path_bar.set_path(path)
            
            index = self.model.setRootPath(path)
            self.tree_view.setRootIndex(index)
            
            self.update_status_bar()
            self.path_changed.emit(path)
    
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
