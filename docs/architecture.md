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
| `pane.py` | 单个窗格的完整功能：路径栏、文件列表、导航、上下文菜单（单选文件时挂「打开方式」子菜单，候选延迟到 `aboutToShow` 才枚举）；持有 `PaneSortProxyModel`（排序 + 筛选同一个代理）与 `FilterBar`（Ctrl+F 唤出，状态栏显示「筛选后 M / N 项」） |
| `dir_model.py` | `DirStoreModel`：以目录为单位的异步文件模型（后台枚举走限流专用线程池 `dir_pool()` + TTL 缓存 + 定向失效；只给**当前显示的本地目录**挂 `QFileSystemWatcher` 自动重扫，监视器是全进程唯一的 `_WatchHub`，网络目录不挂），文件列表专用 |
| `lifecycle.py` | `call_later(obj, ms, fn)`：以业务对象为父的延后回调，避免 `QTimer.singleShot` 在对象销毁后回调已删除子对象；`exec_and_drain(app)` / `drain_background_pool()`：退出时排空后台线程，避免未派发的跨线程投递在解释器收尾阶段被释放（退码 0xC0000409） |
| `file_operations.py` | 文件复制/移动/删除/重命名，支持进度回调和取消 |
| `drag_drop.py` | 拖拽事件处理、MIME 数据传输、操作类型判断 |
| `terminal.py` | 终端应用检测、命令构造、启动外部终端 |
| `open_with.py` | 「打开方式」候选枚举 + 启动：Windows 读注册表（默认 ProgID / `FileExts\*\OpenWithList` MRU / 两处 `OpenWithProgids` / `App Paths` 兜底）、Linux 扫 `.desktop`（XDG 目录 + `MimeType` 匹配）、macOS 扫顶层 `.app` 的 `Info.plist`；按扩展名 TTL 缓存 + exe 去重 + 上限 15 项，任何一步失败只少候选、绝不外抛；Windows 另可 `OpenAs_RunDLL` 调系统对话框 |

### 2.2 widgets/ — UI 组件

| 模块 | 职责 |
|---|---|
| `path_bar.py` | 可编辑路径栏，支持自动补全、历史下拉、书签按钮 |
| `preview_panel.py` | 快速预览面板：文本显示、语法高亮、图片缩略图 |
| `bookmark_sidebar.py` | 收藏夹侧边栏，支持拖拽添加、分组管理 |
| `filter_bar.py` | 筛选栏 UI（字段下拉 + 250ms 防抖 + Esc/行内 ✕ 清除）与**查询编译器** `compile_filter()` → `EntryFilter`：名称包含、`*.log` 通配符、`ext:`/`date:`/`size:`/`type:`/`is:`/`re:`（中英字段别名），条件编译一次、逐行只做内存比较；筛选在 `PaneSortProxyModel.filterAcceptsRow` 生效（不叠第二层代理、不发行信号），解析不了的条件降级为名称包含并在状态栏提示。`glob_to_regex()` 是全仓**唯一**一份通配符→正则实现（高级搜索也用它） |
| `advanced_search.py` | 高级搜索对话框：`collect_params()`（界面 → worker 条件，含大小换算与扩展名归一化）与 `apply_params()`（反向填回）共用一套语义；`build_name_matcher()` 定“正则 → `search` / 含 `*?` → 整名通配 / 否则 → 包含”；「已保存的搜索」下拉（存/载入/删，清单 20.4）读写 `config/saved_searches.py`，存储由 `MainWindow` 注入 |

### 2.3 config/ — 配置管理

| 模块 | 职责 |
|---|---|
| `settings.py` | QSettings 封装，提供类型安全的 get/set |
| `paths.py` | `default_config_dir()`：用户级 JSON 存储的唯一落点（win `%APPDATA%/pan4dex`，其余 `~/.config/pan4dex`），文件关联与已保存搜索共用 |
| `file_associations.py` | 文件类型 → 应用映射的增删改查（配置目录向 `paths.py` 委托） |
| `saved_searches.py` | `SavedSearchStore`：已保存的搜索条件（清单 20.4）单文件 JSON，存的是真正喂给 worker 的 params；读坏当空表、逐条校验、上限 50 条、写失败返回 (False, 文本) 而不抛 |
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
Pane 使涉及的目录失效并重扫（`DirStoreModel.refresh_dir`）+ 更新状态栏
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

QTreeView 支持列排序（名称、大小、修改时间），文件列表模型（`DirStoreModel`）按列提供数据，配合每窗格独立的排序代理。QListView 只能单列显示。

### 4.2 为什么文件列表用自研 `DirStoreModel`，且每窗格一个实例？

**不用 `QFileSystemModel` 的原因（SMB 场景）**：它对一个目录里的每一项都 `stat`，
并给每个目录挂 `QFileSystemWatcher`；在网络位置上这是几百次往返，列一个目录要十几秒。

**`DirStoreModel` 的做法**：一次只枚举一个目录（`os.scandir` 一次往返拿到
name/attr/size/mtime），在专用线程池 `dir_pool()`（限 4 线程，不用按核数并发的
`QThreadPool.globalInstance()`，见 `docs/gotchas.md` 第 26 条）后台完成，主线程零阻塞；
当前显示目录作为模型唯一顶层行，保证排序代理 `mapFromSource` 可映射。

**为何每窗格独立实例**：每个窗格需要独立的当前路径、排序规则、过滤规则与选中状态；
共享模型除了状态冲突，还会让任一窗格的导航/重扫把卡顿带到其它窗格。
跨窗格一致性由显式信号保证（`dirChanged` / `Pane._refresh_dir_everywhere`）；
文件系统 watcher 只能作为**补充**（它只覆盖当前显示的本地目录，且有防抖延迟）。

**为什么只监视一个目录**（而不是监视所有导航过的目录）：实测崩溃率跟监视目录数/通知
流量单调相关（全部监视 → 10/10 轮必崩；只监视当前显示目录、且枚举限流后 → 0/14）；
看不见的目录靠「快照 TTL 过期 + 导航回来重扫一次」保证新鲜。native 登记也不在
`set_directory` 的调用栈里做，而是推到事件循环顶层合并（避开同一轮反复 add/remove）。
详见 `docs/gotchas.md` 第 23、25、26 条。

> 两个侧边目录树（`pane_tree_view.py` / `tree_sidebar.py`）本就按需展开、非瓶颈，
> 继续使用 `QFileSystemModel`。

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
| 大目录（10k+ 文件） | `DirStoreModel` 一次只枚举一个目录且在后台线程完成，主线程不阻塞 |
| 大文件复制 | QThread 后台执行，进度信号节流（每 50ms 更新一次） |
| 频繁导航 | 路径栏自动补全使用缓存，避免重复文件系统查询 |
| 主题切换 | 预编译样式表，避免运行时解析 |

## 7. 安全考量

- 删除操作默认使用 `send2trash`（安全删除到回收站）
- 永久删除需要显式操作（Shift+Delete）
- 不执行任何 shell 命令拼接（避免命令注入）
- 文件操作前检查权限，不足时提示而非静默失败
