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
| `main_window.py` | 主窗口管理、标签页、布局切换、菜单栏、状态栏。**快捷键与侧边栏点击的落点只认 `target_pane()`**：优先最后激活且未销毁的窗格，从未激活过时退回当前页默认窗格（不能直接用 `_active_pane` —— 它只在窗格真拿到焦点时才有值，Linux/X11 上初始焦点不在窗格里，见 gotchas 第 47 条）；`current_pane()` 是它给外部宿主（搜索对话框）的同源入口。**作用面另一道门是 `_focus_is_text_input()`**：焦点在路径栏 / 内嵌终端 / 筛选栏这些文本控件里时，F2·F5·F7·F8·Ctrl+F 不去动文件系统（菜单 QAction 默认 `WindowShortcut`，会抢在焦点控件之前触发，见 gotchas 第 49 条）|
| `pane.py` | 单个窗格的完整功能：路径栏、文件列表、导航、上下文菜单（单选文件时挂「打开方式」子菜单，候选延迟到 `aboutToShow` 才枚举）；持有 `PaneSortProxyModel`（排序 + 筛选同一个代理）与 `FilterBar`（Ctrl+F 唤出，状态栏显示「筛选后 M / N 项」）。**拖拽没有独立模块**：`dragEnterEvent` / `dropEvent` 与拖拽高亮（`_apply_drag_highlight`，进前快照样式、离开精确还原）都住在 `FileListTreeView`/`Pane` 里，自定义 MIME `application/x-pan4dex-drag` 只携带源窗格与文件列表（动作由接收端算，见 §3.2）。`on_path_entered()` 导航成功后把焦点交回文件列表（无效路径时不抢，留在输入框里方便接着改）—— 否则后续按键全打在路径栏上 |
| `dir_model.py` | `DirStoreModel`：以目录为单位的异步文件模型（后台枚举走限流专用线程池 `dir_pool()` + TTL 缓存 + 定向失效；只给**当前显示的本地目录**挂 `QFileSystemWatcher` 自动重扫，监视器是全进程唯一的 `_WatchHub`，网络/慢位目录不挂 —— “慢位置”由 `mounts.is_remote_location()` 定，两端同一个判据），文件列表专用 |
| `lifecycle.py` | `call_later(obj, ms, fn)`：以业务对象为父的延后回调，避免 `QTimer.singleShot` 在对象销毁后回调已删除子对象；`exec_and_drain(app)` / `drain_background_pool()`：退出时排空后台线程，避免未派发的跨线程投递在解释器收尾阶段被释放（退码 0xC0000409）；`safe_event_filter`：事件过滤器装饰器，三个 `eventFilter`（`Pane` / `MainWindow` / `FilterBar`）全部包上 —— Python 侧抛异常时 sip 不会给 C++ 的 `bool` 返回值赋值，Qt 就在一个未定义的值上继续派发（包上不保证不崩，只是为了不让异常未定义地进 C++；有结构守卫用例钉住“不得新增没包的过滤器”，见 `docs/gotchas.md` 44） |
| `file_operations.py` | 文件复制/移动/删除/重命名，支持进度回调和取消（**纯执行层**：不知道有线程、也没有 UI）。删除的回收站门控与确认文案共用同一个 `_is_network_path`：**网络位置无论 `safe` 是多少都是永久删除**（两端一致 —— Linux 上让 `send2trash` 动手会在共享根凭空建一个 `.Trash-1000/`，见 gotchas 第 50 条）；另住几个 Qt 无关的共用判据：`describe_removal()`（删除确认文案，按“网络位置没有回收站”说实际后果）、`move_target_inside_sources()`（“不能把目录移到它自己的子目录里”的唯一判据）、`same_volume()` + `decide_drop_action()`（拖放该复制还是移动：同卷移动、跨卷复制，见 §3.2；`move()` 的跨卷分支也共用 `same_volume`，不留第二份 `st_dev` 比较）—— 窗格与搜索结果列表两个入口不能各写一份 |
| `file_op_runner.py` | `FileOpRunner`：把 `FileOperations` 丢到后台线程，并配齐一整套主线程配合 —— 进度对话框（速度/剩余时间/取消）、同名冲突询问（含「对后续同样处理」只问一次）、跨线程回投、宿主已销毁时丢帧不崩。宿主只给四个可选钩子（`on_status` / `on_bar` / `on_bar_hide` / `on_done`）：窗格与高级搜索共用这一份（见第 4.5 条）。“同一时刻只跑一个”由 `busy` 说出口，入口在宿主（菜单置灰 / 直接拒） |
| （没有 `drag_drop.py` / `terminal.py`） | 旧表里这两行是假的，本仓从来没有这两个文件：拖拽与 MIME 住在 `pane.py`（`dragEnterEvent` / `dropEvent` / `_apply_drag_highlight`）与 `widgets/bookmark_sidebar.py`；终端候选与启动命令住在 `widgets/terminal_panel.py`，窗格只经 `main_window.open_terminal_at()` 转给它 |
| `open_with.py` | 「打开方式」候选枚举 + 启动：Windows 读注册表（默认 ProgID / `FileExts\*\OpenWithList` MRU / 两处 `OpenWithProgids` / `App Paths` 兜底）、Linux 扫 `.desktop`（XDG 目录 + `MimeType` 匹配）、macOS 扫顶层 `.app` 的 `Info.plist`；按扩展名 TTL 缓存 + exe 去重 + 上限 15 项，任何一步失败只少候选、绝不外抛；**“枚举出的候选太少才补内置常用程序”两端共用一道门（`needs_builtin_topup()` / `FALLBACK_TOPUP_BELOW`）—— Linux 原先是无条件追加，富桌面上 `.txt` 会被 gedit/mousepad/kate 一串不相干项刷满；Windows 另可 `OpenAs_RunDLL` 调系统对话框 |
| `mounts.py` | 「这个位置是不是慢位置」的**唯一判据**（`is_remote_location()`）：Windows 走 UNC + `GetDriveTypeW == DRIVE_REMOTE`，POSIX 解析挂载表（`/proc/mounts` / `mount -p`）后按**最长前缀**找所属挂载点、再看文件系统类型（cifs / smb* / nfs* / 任意 `fuse.*`（含 gvfs）/ sshfs / rclone / 9p / 虚拟机共享盘…）。三个环节都是纯函数（`parse_mount_table` / `longest_matching_mount` / `posix_is_remote`）→ Linux 的判定矩阵在 Windows 主机上就能测满；读表带 10s TTL 缓存，**任何失败都退化成「按本地处理」**（宁可多挂一个 watcher，也不能因判据本身出错而让导航/删除跟着失败）；不做 `realpath`（见 `docs/gotchas.md` 第 43 条）。消费方：`file_operations._is_network_path`（窗格刷新、`describe_removal` 确认文案、**`delete()` 实际走不走回收站**）与 `DirStoreModel._is_network`（监视），四处不允许各写一份 —— 只改文案不改行为会得到更难查的「假一致」|

### 2.2 widgets/ — UI 组件

| 模块 | 职责 |
|---|---|
| `path_bar.py` | 可编辑路径栏，支持自动补全、历史下拉、书签按钮 |
| `preview_panel.py` | 快速预览面板：文本显示、语法高亮、图片缩略图 |
| `bookmark_sidebar.py` | 收藏夹侧边栏（`QTreeWidget` 画 `BookmarkStore` 的树，项在 `UserRole` 存 **id**）：增删/重命名/改目录/新建分组、右键“移动到分组”（候选目标回 store 的 `can_place` 判，不在 UI 重算）、展开与顺序都落盘。两种拖放：本树内部重排/挪组，以及**从文件列表拖一个目录进来收藏**（`DragDrop` 而非 `InternalMove`，`dropEvent` 里分内/外两条路）；`canDropMimeData` 的 `parent` 是 `QModelIndex`（见 gotchas 第 38 条） |
| `filter_bar.py` | 筛选栏 UI（字段下拉 + 250ms 防抖 + Esc/行内 ✕ 清除）与**查询编译器** `compile_filter()` → `EntryFilter`：名称包含、`*.log` 通配符、`ext:`/`date:`/`size:`/`type:`/`is:`/`re:`（中英字段别名），条件编译一次、逐行只做内存比较；筛选在 `PaneSortProxyModel.filterAcceptsRow` 生效（不叠第二层代理、不发行信号），解析不了的条件降级为名称包含并在状态栏提示。`glob_to_regex()` 是全仓**唯一**一份通配符→正则实现（高级搜索也用它） |
| `advanced_search.py` | 高级搜索对话框：`collect_params()`（界面 → worker 条件，含大小换算与扩展名归一化）与 `apply_params()`（反向填回）共用一套语义；`build_name_matcher()` 定“正则 → `search` / 含 `*?` → 整名通配 / 否则 → 包含”；「已保存的搜索」下拉（存/载入/删，清单 20.4）读写 `config/saved_searches.py`，存储由 `MainWindow` 注入。**结果列表可多选并批量操作**（清单 20.3）：`SearchResultTree` 只接键位（Enter / Ctrl+Shift+Enter / Del / Shift+Del / Ctrl+C）并发信号，动作长在对话框里（打开类借 `MainWindow.current_pane()` 的窗格语义，搬运与删除走 `FileOpRunner`）；双击从“系统文件管理器定位”改为“打开”，定位进右键菜单 |

### 2.3 config/ — 配置管理

| 模块 | 职责 |
|---|---|
| `app_config.py` | 应用级常量与发布元数据（`APP_NAME` / `VERSION` / `BUILD_TIME` / 默认主题 / 窗口最小尺寸）；`BUILD_TIME` 由构建脚本写盘。**没有 QSettings 封装层**（旧表里的 `settings.py` 不存在）：主窗口、窗格、设置对话框各自直接 `QSettings(ORG_NAME, APP_NAME)` 读写自己的键 |
| `paths.py` | `default_config_dir()`：用户级 JSON 存储的唯一落点（win `%APPDATA%/pan4dex`，其余 `~/.config/pan4dex`），文件关联、已保存搜索与收藏夹共用 |
| `file_associations.py` | 文件类型 → 应用映射的增删改查（配置目录向 `paths.py` 委托） |
| `saved_searches.py` | `SavedSearchStore`：已保存的搜索条件（清单 20.4）单文件 JSON，存的是真正喂给 worker 的 params；读坏当空表、逐条校验、上限 50 条、写失败返回 (False, 文本) 而不抛 |
| `bookmarks.py` | `BookmarkStore`：收藏夹树的模型层 + 单文件 JSON（`bookmarks.json`，format v2），**不依赖 Qt**。节点 `{id, type: link|group, name, path|children+expanded}`，根是隐式分组；结构规则全在这层：`can_place`（拖拽与 `move` 共用的一套理由：成环/超 8 层/目标是链接）、500 条上限、v1 平铺列表只读转换（改过才写盘）、坏记录逐条降级、文件里的 id 不信任。侧边栏与窗格右键共用 `MainWindow` 注入的那一份。首启动默认四条（`default_nodes`）不写死英文目录名：POSIX 先读 `~/.config/user-dirs.dirs`（`parse_user_dirs` → 中文环境的桌面叫 `~/桌面`），`default_links` 只留**真实存在**的目录（点不开的空收藏不如不给），Windows 不读该文件 |
| `theme_manager.py` | 主题注册、切换、自定义主题加载 |

## 3. 数据流设计

### 3.1 文件操作流程

```
用户操作（拖拽 / 右键菜单 / 快捷键 / 搜索结果列表的批量动作）
    ↓
宿主（Pane 或 AdvancedSearchDialog）组好路径与目标，交给 FileOpRunner.run(note, fn, done)
    ↓
后台 threading.Thread 跑 FileOperations.copy/move/delete（主线程不阻塞）
    ↓
进度回调 → `_progress_ui` 信号 → 主线程刷新状态栏与 FileProgressDialog（含取消）
同名冲突 → `_on_conflict` →（共享对象 `_ConflictAsk`）→ 主线程弹 ConflictDialog → 决策写回
    ↓
`_op_done` 信号 → 主线程收尾：拆回调、洗 busy、关进度框、`done(result)`
    ↓
宿主使涉及的目录失效并重扫（`DirStoreModel.refresh_dir` / `Pane._refresh_dir_everywhere`）
      + 更新状态栏（搜索列表额外把已搬走/已删的行从快照里移除）
```

### 3.2 拖拽数据协议

```python
# 自定义 MIME 类型（只给窗格自己看）
MIME_TYPE = "application/x-pan4dex-drag"

# 数据格式（JSON）
{
    "source_pane_id": "pane_1",
    "files": ["/home/user/file1.txt", "/home/user/file2.txt"],
}
```

负载里**没有动作字段**：做什么由接收端按落点算（`Pane._drop_action` →
`core.file_operations.decide_drop_action`），与资源管理器一致：

| 情形 | 动作 |
|---|---|
| 按住 Ctrl / Shift | 强制复制 / 强制移动（覆盖一切） |
| 同窗格内拖动（目标是别的目录行） | 移动 |
| 源端 `proposedAction` 只允许一种 | 就按那一种（只允许 COPY 时不得移动，否则会删掉人家的源） |
| 其余（外部拖入 / 跨窗格） | **同卷移动、跨卷复制**（`same_volume` 比 `st_dev`） |

`same_volume` 拿不准（stat 失败、UNC 共享）时一律回答“不同卷”→ 复制；`FileOperations.move`
的跨卷分支也用同一个判据，不保留第二份 `st_dev` 比较。

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

### 4.3 文件操作为什么用后台线程？

大文件复制/移动会阻塞主线程，导致 UI 卡顿。现在统一由 `FileOpRunner` 安排：
- 工作线程执行文件操作（`daemon=True` 的 `threading.Thread`，不在 Qt 线程对象上赌生命周期）
- 主线程接收进度信号更新 UI（进度对话框 0.2s 节流，不被事件风暴刷爆）
- 支持取消（进度框的取消按钮是全仓唯一入口，它接的是 `FileOperations.cancel`）

旧版这段机制只长在 `Pane._run_file_op_async` 里；现在窗格也只是一个宿主（见第 4.5 条）。

### 4.4 拖拽操作为什么用自定义 MIME 类型？

默认的 `text/uri-list` 只携带文件路径，无法区分：
- 拖拽来自哪个窗格
- 用户意图是复制还是移动

自定义 MIME 类型可以携带完整的上下文信息。

### 4.5 为什么把“后台执行 + 进度 + 取消 + 冲突询问”抽成 `FileOpRunner`？

**诱因**：搜索结果列表要做批量复制/移动/删除（清单 20.3）。只有两条路：
1. 在主线程同步跑 —— 大文件与 SMB 上就是把界面冻住，正是本轮花力气消掉的东西；
2. 把窗格那 ~120 行抄第二份 —— 两份一定会漂（取消语义、冲突记忆策略、进度文案各留一份）。

**所以**：机制（线程、进度框、冲突询问、跨线程回投、丢帧防护）只留一份在
`core/file_op_runner.py`，宿主只保留“状态栏写什么、进度条怎么跳、完了刷新谁”四个钩子。
`Pane` 净减 ~100 行，`file_ops` 属性与完成后的刷新语义不变（`self.file_ops is self.op_runner.ops`）。
**文案与判据也一起去重**：删除确认措辞与“目标在源内部”进了 Qt 无关的
`core/file_operations.py`（`describe_removal` / `move_target_inside_sources`），
“网络位置删除即永久删除”这种话不会再说错一处漏一处。

抽取过程中修掉两个长期潜伏的真 bug（进度框从未弹起、首次冲突决策被丢），经
`tests/test_file_op_runner.py` 钉住，详见 `docs/gotchas.md` 第 40 条。

### 4.6 为什么崩溃日志的落点在运行时选，而不是写死在 exe 旁边？

崩溃日志是**安全网**，它在 `main()` 里比窗口创建还早。写死在 exe 同级目录时，
“能不能写这个文件”就变成了“能不能启动”：Linux 装 `/opt`（root 拥有）、Windows 装
`Program Files` 都是每次启动必死，而用户在启动器上只会看到“双击没反应”（linux230
真机出的第一个产物就踩上了，见 `docs/gotchas.md` 第 45 条）。

现在的做法：`main.py: _crash_log_candidates()` 给候选序列（exe 同级 → 用户缓存 → 临时），
`resolve_crash_log_path()` 取**第一个能写的**（用 `'a'` 试探，不截断上一次的现场）并缓存，
三个写入点共用同一个结果。选不到可写落点时也不抛，`faulthandler` 退到 stderr。

这条不是“加个 try”能代替的：try 只保住了启动，但日志一个字都没落盘 ——
所以配套不变式是“永远找一个能写的地方，且绝不抛”，由
`tests/test_crash_log_path.py` 钉住（含一条真只读目录的 POSIX 用例）。

同一个函数上还有第二条约定：**日志只追加、不截断**（超 256KB 才另起一段）。
三处写入点原本都用 `'w'`，而启动那次 `open(..., 'w')` 会把上一次的崩溃现场清空 ——
用户“崩了 → 再双击一次试试”的第二个动作就把证据洗掉了（偶发段错误长期“日志在、
内容是空的”就是这个原因）。现在启动时写一行分段标记，靠它区分哪一段是哪次运行留下的。

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
| 大文件复制 | 后台线程执行（`FileOpRunner`），进度对话框 0.2s 节流、字节统计缺失时降级按百分比 |
| 频繁导航 | 路径栏自动补全使用缓存，避免重复文件系统查询 |
| 主题切换 | 预编译样式表，避免运行时解析 |

## 7. 安全考量

- 删除操作默认使用 `send2trash`（安全删除到回收站），但**仅限本地位置**：网络位置
  （UNC / 映射网络盘 / Linux 的 CIFS、NFS、gvfs 挂载）没有回收站，一律永久删除，
  确认文案与实际行为共用 `mounts.is_remote_location()` 一个判据
- 永久删除需要显式操作（Shift+Delete）
- 不执行任何 shell 命令拼接（避免命令注入）
- 文件操作前检查权限，不足时提示而非静默失败
