# Pan4dex 万格 — 架构设计文档

## 1. 系统架构概览

```
┌─────────────────────────────────────────────────────┐
│                    Main Window                       │
│  ┌───────────────────────────────────────────────┐  │
│  │                 Tab Widget                     │  │
│  │  ┌─────────────────┬─────────────────┐        │  │
│  │  │     Pane 1      │     Pane 2      │        │  │
│  │  │  Path Bar       │  Path Bar       │        │  │
│  │  │  File List      │  File List      │        │  │
│  │  │  Status Bar     │  Status Bar     │        │  │
│  │  ├─────────────────┼─────────────────┤        │  │
│  │  │     Pane 3      │     Pane 4      │        │  │
│  │  │  Path Bar       │  Path Bar       │        │  │
│  │  │  File List      │  File List      │        │  │
│  │  │  Status Bar     │  Status Bar     │        │  │
│  │  └─────────────────┴─────────────────┘        │  │
│  └───────────────────────────────────────────────┘  │
│  ┌─────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │Bookmark │  │ Preview Dock │  │  Filter Bar   │  │
│  │Sidebar  │  │              │  │               │  │
│  └─────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────┘
```

## 2. 模块职责

### 2.1 core/ — 核心业务逻辑

| 模块 | 职责 |
|---|---|
| `main_window.py` | 主窗口管理、标签页、布局切换、菜单栏、状态栏 |
| `pane.py` | 单个窗格的完整功能：路径栏、文件列表、导航、上下文菜单 |
| `file_model.py` | 封装 QFileSystemModel，提供排序、过滤、目录监听 |
| `file_operations.py` | 文件复制/移动/删除/重命名，支持进度回调和取消 |
| `drag_drop.py` | 拖拽事件处理、MIME 数据传输、操作类型判断 |
| `terminal.py` | 终端应用检测、命令构造、启动外部终端 |

### 2.2 widgets/ — UI 组件

| 模块 | 职责 |
|---|---|
| `path_bar.py` | 可编辑路径栏，支持自动补全、历史下拉、书签按钮 |
| `preview_panel.py` | 快速预览面板：文本显示、语法高亮、图片缩略图 |
| `bookmark_sidebar.py` | 收藏夹侧边栏，支持拖拽添加、分组管理 |
| `filter_bar.py` | 筛选栏，按扩展名/日期/大小过滤 |

### 2.3 config/ — 配置管理

| 模块 | 职责 |
|---|---|
| `settings.py` | QSettings 封装，提供类型安全的 get/set |
| `file_associations.py` | 文件类型 → 应用映射的增删改查 |
| `theme_manager.py` | 主题注册、切换、自定义主题加载 |

## 3. 数据流设计

### 3.1 文件操作流程

```
用户操作（拖拽/右键菜单/快捷键）
    ↓
Pane.eventFilter() 捕获事件
    ↓
Pane 构造 FileOperationRequest（源路径列表 + 目标路径 + 操作类型）
    ↓
FileOperations.execute(request) → 在 QThread 中执行
    ↓
progress_signal.emit(percent, current_file) → 进度对话框
    ↓
result_signal.emit(FileOperationResult) → Pane 处理结果
    ↓
Pane 刷新 QFileSystemModel + 更新状态栏
```

### 3.2 拖拽数据协议

```python
# 自定义 MIME 类型
MIME_TYPE = "application/x-pan4dex-drag"

# 数据格式（JSON）
{
    "source_pane_id": "pane_1",
    "files": ["/home/user/file1.txt", "/home/user/file2.txt"],
    "default_action": "copy"  # or "move"
}
```

### 3.3 主题系统数据流

```
ThemeManager.load_theme("dark")
    ↓
读取 themes/dark.json
    ↓
ThemeManager.apply_theme(theme_data)
    ↓
QApplication.setStyleSheet(style_sheet)
    ↓
各组件响应样式变更
```

## 4. 关键设计决策

### 4.1 为什么用 QTreeView 而不是 QListView？

QTreeView 支持列排序（名称、大小、修改时间），且 QFileSystemModel 天然适配。QListView 只能单列显示。

### 4.2 为什么每个窗格独立 QFileSystemModel？

每个窗格需要独立的：
- 当前路径
- 排序规则
- 过滤规则
- 选中状态

共享模型会导致状态冲突。

### 4.3 文件操作为什么用 QThread？

大文件复制/移动会阻塞主线程，导致 UI 卡顿。使用 QThread + 信号槽：
- 工作线程执行文件操作
- 主线程接收进度信号更新 UI
- 支持取消操作

### 4.4 拖拽操作为什么用自定义 MIME 类型？

默认的 `text/uri-list` 只携带文件路径，无法区分：
- 拖拽来自哪个窗格
- 用户意图是复制还是移动

自定义 MIME 类型可以携带完整的上下文信息。

## 5. 扩展点

### 5.1 插件接口（预留）

```python
class PluginInterface:
    def name(self) -> str: ...
    def init(self, main_window): ...
    def menu_items(self) -> list[QAction]: ...
    def context_menu_items(self, file_path: str) -> list[QAction]: ...
```

### 5.2 自定义主题

JSON 格式定义颜色变量，放置于 `~/.config/pan4dex/themes/`。

### 5.3 文件关联配置

```json
{
  ".txt": {"app": "gedit", "args": ["--new-window"]},
  ".py": {"app": "code", "args": ["--goto"]},
  ".pdf": {"app": "xdg-open", "args": []}
}
```

## 6. 性能考量

| 场景 | 策略 |
|---|---|
| 大目录（10k+ 文件） | QFileSystemModel 原生支持懒加载，无需额外处理 |
| 大文件复制 | QThread 后台执行，进度信号节流（每 50ms 更新一次） |
| 频繁导航 | 路径栏自动补全使用缓存，避免重复文件系统查询 |
| 主题切换 | 预编译样式表，避免运行时解析 |

## 7. 安全考量

- 删除操作默认使用 `send2trash`（安全删除到回收站）
- 永久删除需要显式操作（Shift+Delete）
- 不执行任何 shell 命令拼接（避免命令注入）
- 文件操作前检查权限，不足时提示而非静默失败
