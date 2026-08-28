"""
Pan4dex 万格 — 收藏夹侧边栏
"""
import json
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QListWidget, QListWidgetItem, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QMenu, QInputDialog,
    QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QMimeData


class BookmarkSidebar(QDockWidget):
    """收藏夹侧边栏"""
    
    bookmark_clicked = pyqtSignal(str)  # 收藏项点击信号
    
    def __init__(self, parent=None):
        super().__init__("收藏夹", parent)
        
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | 
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(150)
        self.setMaximumWidth(300)
        
        # 收藏列表
        self.bookmarks = []
        self.config_file = self._get_config_file()
        
        # 创建 UI
        self.init_ui()
        
        # 加载收藏
        self.load_bookmarks()
    
    def _get_config_file(self) -> str:
        """获取收藏配置文件路径"""
        import sys
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", "")
        else:
            base = str(Path.home() / ".config")
        
        config_dir = os.path.join(base, "pan4dex")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "bookmarks.json")
    
    def init_ui(self):
        """初始化 UI"""
        # 主容器
        self.main_widget = QWidget()
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        
        # 工具栏
        self.toolbar = QHBoxLayout()
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(24, 24)
        self.add_btn.setToolTip("添加收藏")
        self.add_btn.clicked.connect(self.add_bookmark)
        self.toolbar.addWidget(self.add_btn)
        
        self.remove_btn = QPushButton("-")
        self.remove_btn.setFixedSize(24, 24)
        self.remove_btn.setToolTip("移除收藏")
        self.remove_btn.clicked.connect(self.remove_bookmark)
        self.toolbar.addWidget(self.remove_btn)
        
        self.toolbar.addStretch()
        
        self.layout.addLayout(self.toolbar)
        
        # 收藏列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        # 拖拽支持
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        
        self.layout.addWidget(self.list_widget)
        
        self.setWidget(self.main_widget)
        
        # 设置样式
        self.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #2A2A2A;
            }
            QListWidget::item:hover {
                background-color: #2A2A2A;
            }
            QListWidget::item:selected {
                background-color: #2196F3;
            }
            QPushButton {
                background-color: #3D3D3D;
                color: #CCCCCC;
                border: 1px solid #505050;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
    
    def load_bookmarks(self):
        """加载收藏"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.bookmarks = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.bookmarks = []
        
        # 默认收藏
        if not self.bookmarks:
            self.bookmarks = [
                {"name": "主目录", "path": str(Path.home())},
                {"name": "桌面", "path": str(Path.home() / "Desktop")},
                {"name": "下载", "path": str(Path.home() / "Downloads")},
                {"name": "文档", "path": str(Path.home() / "Documents")},
            ]
            self.save_bookmarks()
        
        self.refresh_list()
    
    def save_bookmarks(self):
        """保存收藏"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存收藏失败: {e}")
    
    def refresh_list(self):
        """刷新列表"""
        self.list_widget.clear()
        for bookmark in self.bookmarks:
            item = QListWidgetItem(bookmark["name"])
            item.setData(Qt.ItemDataRole.UserRole, bookmark["path"])
            self.list_widget.addItem(item)
    
    def add_bookmark(self):
        """添加收藏"""
        name, ok = QInputDialog.getText(
            self, "添加收藏", "名称:", QLineEdit.EchoMode.Normal, ""
        )
        
        if ok and name:
            # 默认路径为主目录
            path = str(Path.home())
            self._add_bookmark_internal(name, path)
    
    def add_bookmark_with_path(self, path):
        """添加收藏（指定路径）"""
        name, ok = QInputDialog.getText(
            self, "添加到收藏夹", "名称:", QLineEdit.EchoMode.Normal, os.path.basename(path)
        )
        
        if ok and name:
            self._add_bookmark_internal(name, path)
    
    def _add_bookmark_internal(self, name, path):
        """内部添加收藏方法"""
        self.bookmarks.append({"name": name, "path": path})
        self.save_bookmarks()
        self.refresh_list()
    
    def remove_bookmark(self):
        """移除收藏"""
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            reply = QMessageBox.question(
                self, "确认移除",
                f"确定要移除收藏 '{self.bookmarks[current_row]['name']}' 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.bookmarks.pop(current_row)
                self.save_bookmarks()
                self.refresh_list()
    
    def on_item_double_clicked(self, item):
        """双击收藏项"""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isdir(path):
            self.bookmark_clicked.emit(path)
    
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
        
        # 获取当前项
        current_item = self.list_widget.currentItem()
        
        if current_item:
            open_action = menu.addAction("打开")
            open_action.triggered.connect(lambda: self.on_item_double_clicked(current_item))
            
            menu.addSeparator()
            
            edit_action = menu.addAction("编辑")
            edit_action.triggered.connect(self.edit_bookmark)
            
            remove_action = menu.addAction("移除")
            remove_action.triggered.connect(self.remove_bookmark)
        
        menu.addSeparator()
        
        add_action = menu.addAction("添加收藏")
        add_action.triggered.connect(self.add_bookmark)
        
        menu.exec(self.list_widget.mapToGlobal(position))
    
    def edit_bookmark(self):
        """编辑收藏"""
        current_row = self.list_widget.currentRow()
        if current_row < 0:
            return
        
        bookmark = self.bookmarks[current_row]
        
        name, ok = QInputDialog.getText(
            self, "编辑收藏", "名称:", QLineEdit.EchoMode.Normal, bookmark["name"]
        )
        
        if ok and name:
            self.bookmarks[current_row]["name"] = name
            self.save_bookmarks()
            self.refresh_list()
    
    def get_bookmarks(self) -> list:
        """获取所有收藏"""
        return self.bookmarks.copy()
    
    def import_bookmarks(self, filepath: str):
        """导入收藏"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                bookmarks = json.load(f)
            
            if isinstance(bookmarks, list):
                self.bookmarks.extend(bookmarks)
                self.save_bookmarks()
                self.refresh_list()
        except (json.JSONDecodeError, IOError) as e:
            print(f"导入收藏失败: {e}")
    
    def export_bookmarks(self, filepath: str):
        """导出收藏"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"导出收藏失败: {e}")
