# Pan4dex 万格 — 实现设计文档

> 本文档描述各功能的具体业务逻辑、实现要点和技术说明。

---

## 1. 核心框架实现设计

### 1.1 四窗格布局

**业务逻辑**：
- 使用两个 `QSplitter`（一个水平、一个垂直）嵌套实现 2×2 网格
- 每个窗格是独立的 `Pane` 实例，持有自己的路径状态
- 窗格 ID 标识：`pane_1`（左上）、`pane_2`（右上）、`pane_3`（左下）、`pane_4`（右下）

**实现要点**：
```python
# 布局结构
main_splitter (Vertical)
├── top_splitter (Horizontal)
│   ├── Pane(id="pane_1")
│   └── Pane(id="pane_2")
└── bottom_splitter (Horizontal)
    ├── Pane(id="pane_3")
    └── Pane(id="pane_4")
```

**说明**：
- `QSplitter` 保存/恢复用户调整的比例
- 每个 `Pane` 是独立 widget，包含路径栏 + 文件列表 + 状态栏 + 进度条

---

### 1.2 单窗格文件浏览

**业务逻辑**：
- 每个窗格持有独立的 `QFileSystemModel` 实例
- 通过 `setRootPath()` 切换目录
- `QTreeView` 显示文件列表，支持列排序

**实现要点**：
```python
class Pane(QWidget):
    def __init__(self, pane_id):
        self.model = QFileSystemModel()
        self.model.setReadOnly(False)
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(path))
```

**说明**：
- `QFileSystemModel` 异步加载大目录，不阻塞 UI
- 双击事件：如果是目录则 `setRootPath`，如果是文件则触发打开

---

### 1.3 路径栏

**业务逻辑**：
- `QComboBox`（可编辑）显示当前路径
- 输入时触发 `QCompleter` 自动补全
- 回车确认跳转，路径无效时恢复原路径
- 下拉历史记录最近 20 个访问路径

**实现要点**：
```python
class PathBar(QComboBox):
    def __init__(self):
        self.setEditable(True)
        self.completer = QCompleter()
        self.completer.setModel(QDirModel())  # 文件系统补全
        self.setCompleter(self.completer)
        self.returnPressed.connect(self.on_path_entered)
```

**说明**：
- 路径历史存储在 `QSettings` 中
- 自动补全使用 `QFileSystemModel` 过滤匹配项

---

### 1.4 窗格状态栏

**业务逻辑**：
- 每个窗格底部 `QLabel` 显示：
  - 当前路径
  - 文件总数 / 文件夹总数
  - 选中项信息（选中 N 项，共 XX MB）

**实现要点**：
```python
def update_status_bar(self):
    index = self.tree_view.currentIndex()
    path = self.model.filePath(index)
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    dirs = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    self.status_label.setText(f"{len(dirs)} 个目录, {len(files)} 个文件")
```

---

### 1.5 窗格底部进度条

**业务逻辑**：
- 每个窗格底部嵌入 `QProgressBar`
- 默认隐藏，文件操作时显示
- 操作完成后自动隐藏（带 1s 延迟）

**实现要点**：
```python
class Pane(QWidget):
    def __init__(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(3)  # 细条样式
        self.progress_bar.setTextVisible(False)  # 不显示百分比文字
        
    def show_progress(self, percent):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percent)
        
    def hide_progress(self):
        self.progress_bar.setVisible(False)
```

**说明**：
- 进度条紧贴窗格底部边框，视觉上融为一体
- 多窗格可同时显示各自进度条

---

### 1.6 拖拽目标高亮

**业务逻辑**：
- 拖拽进入窗格时，目标窗格边框变为蓝色
- 拖拽离开时恢复
- 拖拽释放时执行操作并恢复边框

**实现要点**：
```python
class Pane(QWidget):
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-pan4dex-drag"):
            self.setStyleSheet("Pane { border: 2px solid #2196F3; }")
            event.accept()
    
    def dragLeaveEvent(self, event):
        self.setStyleSheet("")  # 恢复默认样式
    
    def dropEvent(self, event):
        self.setStyleSheet("")
        # 处理拖放逻辑
```

**说明**：
- 使用 QSS 动态切换边框颜色
- 蓝色 `#2196F3` 与主题协调

---

### 1.7 主窗口框架

**业务逻辑**：
- `QMainWindow` 作为主容器
- 菜单栏：文件、编辑、视图、工具、帮助
- 工具栏：常用操作按钮
- 状态栏：全局状态信息
- 中央 widget：四窗格布局或标签页
- 可停靠区域：预览面板、收藏夹侧边栏

**实现要点**：
```python
class MainWindow(QMainWindow):
    def __init__(self):
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
        self.addToolBar(...)  # 工具栏
        self.statusBar()  # 状态栏
        self.create_docks()  # 创建可停靠面板
```

---

## 2. 文件操作实现设计

### 2.1 复制/移动文件

**业务逻辑**：
- 复制：`shutil.copy2()`（保留元数据）
- 移动：`shutil.move()`
- 大文件（>100MB）使用分块复制，每 1MB 发送一次进度信号
- 小文件直接复制，完成后发送 100% 进度

**实现要点**：
```python
class FileOperations(QThread):
    progress = pyqtSignal(int, str)  # percent, current_file
    finished = pyqtSignal(FileOperationResult)
    
    def copy_file(self, src, dst):
        size = os.path.getsize(src)
        copied = 0
        with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
            while True:
                buf = fsrc.read(1024 * 1024)  # 1MB chunks
                if not buf:
                    break
                fdst.write(buf)
                copied += len(buf)
                percent = int(copied * 100 / size)
                self.progress.emit(percent, src)
                if self.is_cancellation_requested():
                    os.remove(dst)
                    return
```

**说明**：
- 使用 `QThread` 避免阻塞 UI
- 支持取消操作（设置标志位，工作线程检测）
- 复制完成后调用 `shutil.copystat()` 保留权限和时间戳

---

### 2.2 安全删除

**业务逻辑**：
- 默认使用 `send2trash.send2trash()` 将文件移入回收站
- 回收站位置：`~/.local/share/Trash/`
- 删除失败时（如权限不足）弹出错误对话框

**实现要点**：
```python
def safe_delete(self, path):
    try:
        send2trash(path)
        return FileOperationResult(success=True)
    except Exception as e:
        return FileOperationResult(success=False, error=str(e))
```

---

### 2.3 永久删除

**业务逻辑**：
- `Shift+Delete` 触发永久删除
- 文件：`os.remove()`
- 目录：`os.rmdir()`（仅空目录）或 `shutil.rmtree()`（非空目录）
- 删除前弹出确认对话框

**实现要点**：
```python
def permanent_delete(self, path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
```

---

### 2.4 重命名

**业务逻辑**：
- 右键菜单或 `F2` 触发
- 使用 `QTreeView` 的编辑功能直接在原位修改
- 调用 `os.rename()` 执行重命名
- 重命名失败时（如目标已存在）弹出错误

**实现要点**：
```python
def rename(self, old_path, new_name):
    new_path = os.path.join(os.path.dirname(old_path), new_name)
    os.rename(old_path, new_path)
```

---

### 2.5 拖拽机制

**业务逻辑**：
- 拖拽开始：记录源窗格 ID 和选中文件路径列表
- 拖拽进入目标窗格：高亮目标窗格
- 拖拽释放：根据操作类型执行复制或移动
- 操作类型判断：
  - 同窗格 → 移动
  - 跨窗格 → 复制
  - 按住 Shift → 强制移动
  - 按住 Ctrl → 强制复制

**实现要点**：
```python
# 自定义 MIME 数据
{
    "source_pane_id": "pane_1",
    "files": ["/path/to/file1", "/path/to/file2"],
    "default_action": "copy"
}

# 拖拽事件处理
def mousePressEvent(self, event):
    if event.button() == Qt.LeftButton:
        self.drag_start_pos = event.pos()

def mouseMoveEvent(self, event):
    if event.buttons() & Qt.LeftButton:
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-pan4dex-drag", 
                         json.dumps(drag_data).encode())
        drag.setMimeData(mime_data)
        drag.exec(Qt.CopyAction | Qt.MoveAction)
```

**说明**：
- 使用自定义 MIME 类型 `application/x-pan4dex-drag`
- 拖拽结果通过 `drag.result()` 判断用户选择的操作

---

## 3. 标签页实现设计

### 3.1 多标签页

**业务逻辑**：
- `QTabWidget` 管理多个标签页
- 每个标签页是一个 `QuadPaneWidget`（包含四窗格布局）
- 新建标签页默认打开用户主目录
- 关闭标签页时如果只有一个标签页则不允许关闭

**实现要点**：
```python
class MainWindow(QMainWindow):
    def new_tab(self):
        widget = QuadPaneWidget()  # 包含四个 Pane 的 widget
        self.tab_widget.addTab(widget, "新标签页")
        self.tab_widget.setCurrentWidget(widget)
    
    def close_tab(self, index):
        if self.tab_widget.count() > 1:
            self.tab_widget.removeTab(index)
```

---

## 4. 快速预览实现设计

### 4.1 文本预览

**业务逻辑**：
- 选中文件时触发预览
- 文本文件（MIME type 以 `text/` 开头）：直接读取显示
- 大文本文件（>1MB）：只读取前 100KB
- 支持语法高亮（Python、JSON、Markdown 等）

**实现要点**：
```python
class PreviewPanel(QDockWidget):
    def preview_file(self, path):
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type and mime_type.startswith('text/'):
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(100 * 1024)  # 限制 100KB
            self.text_edit.setPlainText(content)
```

---

## 5. 文件打开配置实现设计

### 5.1 文件类型-应用映射

**业务逻辑**：
- 配置存储在 `~/.config/pan4dex/associations.json`
- 格式：`{".txt": {"app": "gedit", "args": ["--new-window"]}}`
- 未配置的类型使用 `xdg-open`
- 配置界面提供增删改功能

**实现要点**：
```python
class FileAssociations:
    def get_app_for_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in self.associations:
            return self.associations[ext]
        return {"app": "xdg-open", "args": []}
    
    def open_file(self, path):
        assoc = self.get_app_for_file(path)
        cmd = [assoc["app"]] + assoc.get("args", []) + [path]
        subprocess.Popen(cmd)
```

---

## 6. 终端集成实现设计

### 6.1 终端自动检测

**业务逻辑**：
- 按优先级检测可用终端：
  1. 用户配置的终端
  2. `x-terminal-emulator`（Debian/Ubuntu 系统链接）
  3. `gnome-terminal`（GNOME 桌面）
  4. `konsole`（KDE 桌面）
  5. `xfce4-terminal`（XFCE 桌面）
  6. `xterm`（通用 fallback）
- 检测方式：`which` 命令检查可执行文件是否存在

**实现要点**：
```python
class Terminal:
    TERMINALS = [
        "x-terminal-emulator",
        "gnome-terminal",
        "konsole", 
        "xfce4-terminal",
        "xterm"
    ]
    
    def detect_terminal(self):
        for term in self.TERMINALS:
            if shutil.which(term):
                return term
        return None
    
    def open_in_terminal(self, path):
        term = self.get_configured_terminal() or self.detect_terminal()
        if term == "gnome-terminal":
            subprocess.Popen([term, f"--working-directory={path}"])
        elif term == "konsole":
            subprocess.Popen([term, f"--workdir", path])
        else:
            # 通用方案：在终端中 cd 到目录
            subprocess.Popen([term, "-e", f"cd {shlex.quote(path)} && $SHELL"])
```

---

## 7. 主题系统实现设计

### 7.1 主题管理器

**业务逻辑**：
- `ThemeManager` 单例管理主题
- 内置主题存储在 `resources/themes/`
- 自定义主题存储在 `~/.config/pan4dex/themes/`
- 主题切换时重新加载 QSS 并应用到 `QApplication`

**实现要点**：
```python
class ThemeManager:
    def __init__(self):
        self.themes = {}
        self.current_theme = "system"
        self.load_builtin_themes()
        self.load_custom_themes()
    
    def apply_theme(self, name):
        if name not in self.themes:
            return False
        theme = self.themes[name]
        qss = self.generate_qss(theme)
        QApplication.instance().setStyleSheet(qss)
        self.current_theme = name
        return True
    
    def generate_qss(self, theme):
        return f"""
        QMainWindow {{ background-color: {theme['window_bg']}; }}
        QWidget {{ color: {theme['text_color']}; }}
        QTreeView {{ background-color: {theme['list_bg']}; }}
        QTreeView::item:selected {{ background-color: {theme['highlight']}; }}
        """
```

**说明**：
- 主题 JSON 格式：
```json
{
    "name": "dark",
    "window_bg": "#2D2D2D",
    "text_color": "#CCCCCC",
    "list_bg": "#1E1E1E",
    "highlight": "#2196F3",
    "border": "#404040"
}
```

---

## 8. 快捷键实现设计

**业务逻辑**：
- 使用 `QShortcut` 绑定快捷键
- 快捷键可配置（预留接口）
- 快捷键冲突时优先处理窗格内操作

**实现要点**：
```python
class MainWindow(QMainWindow):
    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+T"), self, self.new_tab)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close_current_tab)
        QShortcut(QKeySequence("Ctrl+Tab"), self, self.next_tab)
        QShortcut(QKeySequence("Ctrl+L"), self, self.focus_path_bar)
        QShortcut(QKeySequence("Ctrl+D"), self, self.toggle_theme)
        QShortcut(QKeySequence("Ctrl+4"), self, self.switch_to_quad)
        QShortcut(QKeySequence("Ctrl+2"), self, self.switch_to_dual)
        QShortcut(QKeySequence("F3"), self, self.toggle_preview)
        QShortcut(QKeySequence("F5"), self, self.refresh_pane)
        QShortcut(QKeySequence("Delete"), self, self.safe_delete_selected)
        QShortcut(QKeySequence("Shift+Delete"), self, self.permanent_delete_selected)
        QShortcut(QKeySequence("F2"), self, self.rename_selected)
```

---

## 9. 右键菜单实现设计

**业务逻辑**：
- 在文件/文件夹上右键弹出上下文菜单
- 菜单项根据选中内容动态调整
- 空白区域右键显示新建菜单

**实现要点**：
```python
class Pane(QWidget):
    def contextMenuEvent(self, event):
        menu = QMenu()
        
        # 获取选中项
        selected = self.tree_view.selectedIndexes()
        
        if selected:
            # 有选中项
            menu.addAction("打开", self.open_selected)
            menu.addSeparator()
            menu.addAction("复制", self.copy_selected)
            menu.addAction("剪切", self.cut_selected)
            menu.addAction("删除", self.delete_selected)
            menu.addAction("重命名", self.rename_selected)
            menu.addSeparator()
            menu.addAction("打开终端", self.open_terminal_here)
            menu.addAction("属性", self.show_properties)
        else:
            # 空白区域
            menu.addAction("新建文件夹", self.new_folder)
            menu.addAction("新建文件", self.new_file)
            menu.addSeparator()
            menu.addAction("粘贴", self.paste)
            menu.addSeparator()
            menu.addAction("打开终端", self.open_terminal_here)
        
        menu.exec(event.globalPos())
```

---

## 10. 筛选过滤实现设计

**业务逻辑**：
- 使用 `QSortFilterProxyModel` 作为中间层
- 筛选条件：扩展名列表、日期范围、大小范围
- 筛选栏输入 `*.txt,*.py` 只显示匹配文件
- 清除筛选显示全部文件

**实现要点**：
```python
class FilterProxyModel(QSortFilterProxyModel):
    def __init__(self):
        self.extensions = []
        self.min_size = None
        self.max_size = None
    
    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        file_name = self.sourceModel().fileName(index)
        
        # 扩展名筛选
        if self.extensions:
            ext = os.path.splitext(file_name)[1].lower()
            if ext not in self.extensions:
                return False
        
        return True
```

---

**文档版本**：v1.0  
**最后更新**：2026-08-26
