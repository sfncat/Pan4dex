# Pan4dex 万格 — 功能清单与规划

> 本文档跟踪所有功能的实现状态，每完成/更新一个功能都要更新此文档。

**图例**：🔴 未开始 | 🟡 进行中 | 🟢 已完成 | ⚪ 暂缓

---

## 1. 核心框架

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 1.1 | 四窗格布局 | P0 | 🟢 | 启动后可见 4 个独立窗格，可拖拽调整大小 | QSplitter 2×2 网格 | main_window.py QuadPaneWidget |
| 1.2 | 单窗格文件浏览 | P0 | 🟢 | 每个窗格独立显示文件列表，双击进入目录 | QTreeView + QFileSystemModel | pane.py |
| 1.3 | 路径栏 | P0 | 🟢 | 点击路径栏可输入路径，回车跳转，支持下拉历史 | QComboBox + 自动补全 | path_bar.py |
| 1.4 | 窗格状态栏 | P0 | 🟢 | 底部显示当前路径、文件数、选中项信息 | QLabel 状态栏 | pane.py |
| 1.5 | 窗格底部进度条 | P0 | 🟢 | 文件操作时在窗格底部显示进度条 | QProgressBar 内嵌窗格底部 | pane.py |
| 1.6 | 拖拽目标高亮 | P0 | 🟢 | 跨窗格拖拽时目标窗格边框高亮（蓝色） | QSS 动态样式 | pane.py dragEnterEvent |
| 1.7 | 主窗口框架 | P0 | 🟢 | 菜单栏、工具栏、状态栏、QDockWidget 区域 | QMainWindow | main_window.py |
| 1.8 | 列头排序 | P0 | 🟢 | 点「名称/大小/修改日期」列头切换升降序；**任一方向下目录都排在文件前**；大小按字节数而非“4.0 KB”字符串 | `PaneSortProxyModel.lessThan` 只读条目缓存属性（不 stat、不碰网络） | pane.py |

## 2. 文件操作

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 2.1 | 复制文件 | P0 | 🟢 | 右键/快捷键复制与外部拖入（跨卷）→ 进度对话框显示，完成后目标窗格刷新 | shutil.copy2 + 后台线程 | file_operations.py copy() |
| 2.2 | 移动文件 | P0 | 🟢 | 窗格内拖拽移动，或剪切后粘贴；同卷跨窗格拖拽也是移动 | shutil.move + 后台线程；跨卷走「复制+删源」（保 mtime、有字节进度、可取消） | file_operations.py move() |
| 2.3 | 安全删除 | P0 | 🟢 | 右键删除 → 文件进入回收站，可恢复 | send2trash | file_operations.py delete() |
| 2.4 | 永久删除 | P1 | 🟢 | Shift+Delete 直接删除（确认框明写「不可恢复」） | 走 `delete(safe=False)`；网络位置本就无回收站，文案同样区分 —— 「是不是网络位置」两端都算（v1.9.013 前只在 Windows 上分类，见 3.5） | pane.py `FileListTreeView.keyPressEvent` → `_delete_paths(permanent=True)` → `file_operations.describe_removal()` |
| 2.5 | 重命名 | P0 | 🟢 | F2 / 右键重命名 → 行内编辑，提交走模型 setData | 新模型条目带 ItemIsEditable，内建触发器关掉以免误编辑 | pane.py `rename_selected()` |
| 2.6 | 新建文件夹 | P1 | 🟢 | 右键菜单 → 新建文件夹，自动进入重命名 | os.makedirs | file_operations.py create_folder() |
| 2.7 | 新建文件 | P1 | 🟢 | 右键菜单 → 新建空文件 | open(path, 'w') | file_operations.py create_file() |
| 2.8 | 复制/移动取消 | P1 | 🟢 | 独立进度对话框带取消；统计阶段也检查取消标志（SMB 大目录不会卡到跑完） | `cancel_requested` → `file_ops.cancel()` | widgets/progress_dialog.py / file_operations.py |
| 2.9 | 跨窗格拖拽复制 | P0 | 🟢 | 从 pane A 拖拽文件到 pane B，B 中高亮边框，松手按 2.11 的规则定动作 | 自定义 MIME 类型（只带源窗格与文件，不带动作） | pane.py mouseMoveEvent/dropEvent |
| 2.10 | 跨窗格拖拽移动 | P0 | 🟢 | 同窗格内拖动、同卷跨窗格拖拽松手即移动（不必按 Shift）；Shift 强制移动、Ctrl 强制复制 | 同上 | pane.py `_drop_action` → file_operations.decide_drop_action |
| 2.11 | 拖放默认动作对齐资源管理器 | P0 | 🟢 | 从同一个盘的 Explorer 往窗格拖文件 → 源文件消失（移动）；从U盘/另一张盘拖入 → 复制；只允许复制的外部源不会被我们“移动”掉 | Ctrl/Shift 强制 > 同目录树内拖动 > `possibleActions` 硬约束（不许 move 就绝不 move）> 同卷移动/跨卷复制（`st_dev`，UNC 一律算不确定→复制） | file_operations.py `same_volume()` / `decide_drop_action()`；tests/test_drop_action.py |

## 3. 导航

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 3.1 | 返回上级目录 | P0 | 🟢 | 点击路径栏上一级按钮或 Alt+Up | 路径栏按钮 + 主窗口 QAction | main_window.py `on_nav_up()` / path_bar.py `go_up()` |
| 3.2 | 路径自动补全 | P1 | 🟢 | 输入路径时弹出候选；只补当前一层，绝不全盘扫描 | QCompleter + QStringListModel（按需填充） | path_bar.py `_setup_completer()` |
| 3.3 | 路径历史 | P1 | 🟢 | 后退/前进按钮 + Alt+Left/Right；按窗格各自记史，前进截断正确处理 | 历史栈 `_nav_history` + `_nav_index` | pane.py `go_back()` / `go_forward()` |
| 3.4 | 快速跳转 | P1 | 🟢 | Ctrl+L 聚焦当前窗格路径栏并全选现有路径，直接键入即可跳转 | PathBar.focus_for_input() | main_window.py `on_focus_path_bar()` / path_bar.py |
| 3.5 | 网络 / 慢位置识别 | P0 | 🟢 | 同一个位置在三处得到**同一个答案**（窗格刷新、目录监视、删除文案）；Linux 上挂在 `/mnt` 的 cifs/nfs/sshfs 也算网络位置（v1.9.013 前判据写死 `os.name != 'nt'` 直接返回 False，整套保守策略在非 Windows 上从不生效） | 全仓唯一入口 `mounts.is_remote_location()`：Windows 走 UNC + `GetDriveTypeW`，POSIX 读挂载表（`/proc/mounts` / `mount -p`）按**最长前缀**定所属挂载点再看 fstype；解析/匹配/判定三段纯函数 → Linux 矩阵在 Windows 主机上就能测满；**任何失败退化为「按本地」**，不做 `realpath`（取舍见 gotchas 第 43 条） | core/mounts.py；tests/test_mounts.py 82 项 |

## 4. 标签页

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 4.1 | 多标签页 | P1 | 🟢 | Ctrl+T 新建标签页，每个标签页独立四窗格 | QTabWidget | main_window.py new_tab() |
| 4.2 | 关闭标签页 | P1 | 🟢 | Ctrl+W 关闭当前标签页，Tab 栏关闭按钮 | tabCloseRequested | main_window.py close_tab() |
| 4.3 | 标签页切换 | P1 | 🟢 | 点击标签栏切换、Ctrl+Tab / Ctrl+Shift+Tab 循环（到端点回绕）、双击空白新建、双击标签关闭 | `setCurrentIndex` 走与点击同一条路径 | main_window.py `_cycle_tab()` |
| 4.4 | 标签页状态保持 | P1 | 🟢 | 切换标签页时保留各窗格路径和选中状态 | QuadPaneWidget 独立持有 4 个 Pane | main_window.py |
| 4.5 | 标签页重命名 | P1 | 🟢 | 右键标签页 → 重命名（双击标签是关闭，不是重命名） | QInputDialog | main_window.py rename_tab() |

## 5. 快速预览

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 5.1 | 文本预览 | P1 | 🟢 | 选中文本文件，右侧面板显示内容 | QPlainTextEdit + 语法高亮 | preview_panel.py |
| 5.2 | 文件信息显示 | P1 | 🟢 | 显示大小、修改时间、权限、MIME 类型 | QLabel 信息面板 | preview_panel.py |
| 5.3 | 图片缩略图 | P2 | 🟢 | 选中图片文件，右侧显示缩略图 | QPixmap + QLabel | preview_panel.py |
| 5.4 | 预览面板开关 | P1 | 🟢 | F3 或菜单切换预览面板显示 | QDockWidget toggle | main_window.py toggle_preview() |

## 6. 文件打开配置

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 6.1 | 文件类型-应用映射 | P1 | 🟢 | 关联表 JSON 读写（无独立设置界面；改默认走 6.3 的「并设为默认」或系统对话框） | JSON 配置 | file_associations.py |
| 6.2 | 默认打开行为 | P1 | 🟢 | 双击文件按配置打开，未配置用 xdg-open | subprocess + xdg-open | file_associations.py open_file() |
| 6.3 | 右键打开方式 | P2 | 🟢 | 单选文件右键列出本机可开的程序，选一项只打开这一次；默认项带「（默认）」标记 | `core/open_with.py` 枚举本机注册信息（win 注册表 / Linux `.desktop` / macOS `Info.plist`）+ TTL 缓存，候选延迟到 `aboutToShow` 才枚举；“候选太少才补内置常用程序”为两端共用的一道门（`needs_builtin_topup()`，v1.9.014）；Windows 额外提供系统「打开方式」对话框 | open_with.py + pane._add_open_with_submenu() / _fill_open_with_menu()；tests/test_open_with.py（27 项，含 3 项 Linux 专属 —— 只能在真机上算测到） |
| 6.4 | 配置持久化 | P1 | 🟢 | 配置保存到 ~/.config/pan4dex/ | QSettings + JSON | file_associations.py |

## 7. 终端集成

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 7.1 | 终端自动检测 | P1 | 🟢 | 自动检测可用终端（Windows: wt.exe/pwsh.exe, Linux: xdg-mime/配置） | which + 配置回退 | pane.py open_terminal_here() |
| 7.2 | 在此处打开终端 | P1 | 🟢 | 右键菜单 → 在当前目录打开终端 | subprocess 启动终端 | pane.py open_terminal_here() |
| 7.3 | 终端应用配置 | P2 | 🟢 | 用户可通过 settings.json 指定自定义终端应用 | JSON 配置持久化 | pane.py 读取 settings.json |

## 8. 收藏夹

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 8.1 | 收藏夹侧边栏 | P2 | 🟢 | 侧边栏以**树**显示收藏（分组 + 条目），项在 `UserRole` 存 id 而不是靠行号 | QTreeWidget + QDockWidget，模型层 `config/bookmarks.py`（不依赖 Qt） | bookmark_sidebar.py |
| 8.2 | 添加收藏 | P2 | 🟢 | 拖拽目录到侧边栏（落在光标下的分组，拖文件不收）、工具栏「+」（默认活动窗格的当前目录）、右键「添加到收藏夹」三条路 | 外部拖入走 `dropEvent`（不是 `InternalMove`）+ 同路径去重 | bookmark_sidebar.py `add_bookmark()` / `add_paths_as_bookmarks()` |
| 8.3 | 移除收藏 | P2 | 🟢 | 右键或 Del 键；删分组时说清会带走几条，**磁盘上的目录不受影响** | 确认框 + 按 id 删（不是按行号） | bookmark_sidebar.py `remove_selected()` |
| 8.4 | 收藏分组 | P3 | 🟢 | 新建/重命名/删除分组，嵌套≤ 8 层（超出拒绝）；拖拽重排与挪组（成环不给放）、右键「移动到分组…」列合法目标；展开状态与顺序都落盘；老的平铺 bookmarks 自动迁移（改过才写盘） | `BookmarkStore.can_place` 与 `move` 共用一套规则；上限 500 条 | config/bookmarks.py + bookmark_sidebar.py；tests/test_bookmarks.py 94 项 |
| 8.5 | 首启动默认收藏 | P2 | 🟢 | 全新配置下侧边栏给出「主目录 + 桌面/下载/文档」，且**中文桌面**（`~/桌面`）不给出 `~/Desktop` 这种点不开的空项（v1.9.013 前写死英文） | POSIX 读 `~/.config/user-dirs.dirs`（`parse_user_dirs` 纯函数，认 `$HOME` 与 `~` 两种写法）；`default_links` 只留真实存在的目录；Windows 不读该文件 | config/bookmarks.py `default_nodes()`；tests/test_bookmarks.py `TestDefaultXdgDirs` |

## 9. 筛选过滤

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 9.1 | 按扩展名筛选 | P2 | 🟢 | 输入 `*.txt` 或 `ext:py,md` 只显示对应扩展名 | `filter_bar.compile_filter()` → `PaneSortProxyModel.filterAcceptsRow` | filter_bar.py / pane.py |
| 9.2 | 按日期筛选 | P3 | 🟢 | `date:本周` / `date:>=2026-01-01` / `date:2026-01-01..2026-03-01` | 同上（比较模型已缓存的 mtime，不 stat） | filter_bar.py |
| 9.3 | 按大小筛选 | P3 | 🟢 | `size:>10mb` / `size:1mb-100mb` / `size:大型` | 同上（比较条目已缓存的 size） | filter_bar.py |
| 9.4 | 清除筛选 | P2 | 🟢 | 输入框行内 ✕、Esc（同时收起筛选栏）、右键「清除筛选」 | `FilterBar.clear_filter()` 无条件补发空条件 | filter_bar.py / pane.py |
| 9.5 | 按名称/通配符/正则筛选 | P2 | 🟢 | 裸文本＝名称包含；`*.log`/`?at` 整名匹配；`re:` 正则 | 条件编译一次，逐行只做内存比较 | filter_bar.py |
| 9.6 | 只看目录 / 只看文件 | P3 | 🟢 | `is:folder` / `is:file` / `类型:目录` | 条目 `is_dir` 属性 | filter_bar.py |
| 9.7 | 筛选与隐藏文件开关、两视图一致 | P2 | 🟢 | 筛到的行同时受「显示隐藏文件」约束；超大图标视图同步生效 | 列表走代理，图标视图在自身枚举里过一道 | pane.py / thumbnail_view.py |

## 10. 布局模式

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 10.1 | 四窗格模式 | P0 | 🟢 | 默认 2×2 四窗格，每个标签页独立 | QSplitter 网格 + QuadPaneWidget | main_window.py switch_to_quad() |
| 10.2 | 双窗格模式 | P1 | 🟢 | Ctrl+2 切换到上下双窗格 | 隐藏 pane2/pane4 | main_window.py switch_to_dual() |
| 10.3 | 模式切换 | P1 | 🟢 | 菜单或快捷键切换，保留路径状态 | show()/hide() 窗格 | main_window.py |

## 11. 主题系统

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 11.1 | 系统主题 | P1 | 🟢 | 跟随桌面环境主题 | QApplication 默认样式 | theme_manager.py |
| 11.2 | 深色主题 | P1 | 🟢 | 视图菜单→「深色主题」（可勾选，打勾跟随当前主题）或 Ctrl+D 切到深色 | qdarkstyle 样式表 | theme_manager.py apply_theme() |
| 11.3 | 浅色主题 | P2 | 🟢 | 视图菜单→「浅色主题」或 Ctrl+D；切换写回 QSettings，重启后保持 | 写死的浅色 QSS | theme_manager.py apply_theme() |
| 11.4 | 自定义主题接口 | P2 | 🔴 | 未实现：主题只有内置 dark/light 两项，无 JSON 保存/导入导出 | 需先定「主题包」的文件格式 | tests/test_m4_theme.py `test_no_custom_theme_persistence_api` 卡住这个事实 |
| 11.5 | 主题热切换 | P1 | 🟢 | 切换主题无需重启 | QSS 动态加载 | theme_manager.py apply_theme() |

## 12. 快捷键

> 快捷键统一由主窗口菜单的 QAction 携带（WindowShortcut，作用于整个主窗口）；
> 只有少数需要拦在视图内部的（Shift+Delete、Ctrl+F）写在 `FileListTreeView.keyPressEvent`。

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 12.1 | Ctrl+T 新建标签页 | P1 | 🟢 | 按下后新建一个完整四窗格标签页 | 文件菜单 QAction | main_window.py `new_tab()` |
| 12.2 | Ctrl+W 关闭标签页 | P1 | 🟢 | 按下后关闭当前标签页（最后一个不关窗口） | 文件菜单 QAction | main_window.py `close_current_tab()` |
| 12.3 | Ctrl+Tab 切换标签页 | P1 | 🟢 | 真按键能切；单标签时不异常（另见 Ctrl+Shift+Tab 反向） | 文件菜单 QAction + `_cycle_tab(±1)` | main_window.py `on_next_tab()` |
| 12.4 | Ctrl+L 聚焦路径栏 | P1 | 🟢 | 按下后路径全文选中（见 3.4） | 编辑菜单 QAction | main_window.py `on_focus_path_bar()` |
| 12.5 | Ctrl+D 切换主题 | P2 | 🟢 | 深浅互切，菜单打勾与 QSettings 同步更新 | 视图菜单 QAction | main_window.py `toggle_theme()` |
| 12.6 | Ctrl+4 四窗格模式 | P1 | 🟢 | 切换到四窗格模式 | 视图菜单 QAction | main_window.py `switch_to_quad()` |
| 12.7 | Ctrl+2 双窗格模式 | P1 | 🟢 | Ctrl+2 上下双窗格、Ctrl+Shift+2 横向、Ctrl+5/Ctrl+6 上2下1/上1下2 | 视图菜单 QAction | main_window.py `switch_to_dual*()` |
| 12.8 | F3 预览面板 | P2 | 🟢 | 切换右侧预览面板显示（可勾选项） | 视图菜单 QAction | main_window.py `toggle_preview()` |
| 12.9 | F5 刷新 | P1 | 🟢 | 刷新当前窗格，保留选中与滚动位置 | 编辑菜单 QAction | main_window.py `on_refresh()` |
| 12.10 | Delete 安全删除 | P0 | 🟢 | 删除选中项到回收站；网络位置文案改为「永久删除」（该分类在 Linux 上同样生效，见 3.5） | 编辑菜单 QAction | main_window.py `on_delete()` → pane `_delete_paths` |
| 12.11 | Shift+Delete 永久删除 | P1 | 🟢 | 直接删除选中项，二次确认明写不可恢复 | 在视图 keyPressEvent 拦，不与 QAction(Delete) 双弹确认框 | pane.py `FileListTreeView.keyPressEvent` |
| 12.12 | F2 重命名 | P0 | 🟢 | 进入当前行行内编辑 | 编辑菜单 QAction | main_window.py `on_rename()` → pane `rename_selected()` |
| 12.13 | Ctrl+C / Ctrl+X / Ctrl+V | P0 | 🟢 | 复制/剪切/粘贴，与系统剪贴板互通（含 MoveEffect 识别） | 编辑菜单 QAction | main_window.py / pane.py |
| 12.14 | Ctrl+A 全选 | P1 | 🟢 | 选中当前窗格全部条目 | 编辑菜单 QAction | main_window.py `on_select_all()` |
| 12.15 | Ctrl+F 筛选当前目录 | P2 | 🟢 | 唤出筛选栏，只筛当前目录不递归；Esc 收起并清除 | 视图与菜单双入口 | main_window.py `on_filter_current_dir()` / pane.py |
| 12.16 | Ctrl+H 显示隐藏文件 | P2 | 🟢 | 全局同步切换所有窗格的隐藏文件显示 | 视图菜单可勾选项 | main_window.py `toggle_hidden_files()` |
| 12.17 | Alt+Left / Alt+Right / Alt+Up | P1 | 🟢 | 后退 / 前进 / 返回上级 | 编辑菜单 QAction | main_window.py `on_nav_back/forward/up()` |
| 12.18 | F7/F8、F4、Ctrl+B、Ctrl+Shift+T、Ctrl+Q | P2 | 🟢 | 新建文件夹/新建文件、终端面板、收藏夹、目录树、退出 | 菜单 QAction | main_window.py |
| 12.19 | 搜索结果列表键位 | P2 | 🟢 | Enter 打开、Ctrl+Shift+Enter 打开所在文件夹、Del 回收站、Shift+Del 永久删除、Ctrl+C 复制**路径文本** | 在 `QTreeWidget.keyPressEvent` 里接（不接 Enter 会被对话框的“自动默认按钮”抢走 → 变成关闭对话框） | widgets/advanced_search.py `SearchResultTree`；tests/test_search_results.py |

## 13. 右键菜单

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 13.1 | 打开 | P0 | 🟢 | 双击或右键打开文件 | 按配置应用打开 | pane.py open_selected() |
| 13.2 | 复制 | P0 | 🟢 | 右键复制，然后到目标窗格粘贴 | 剪贴板机制 | pane.py copy_selected() |
| 13.3 | 剪切 | P0 | 🟢 | 右键剪切 | 剪贴板机制 | pane.py cut_selected() |
| 13.4 | 粘贴 | P0 | 🟢 | 右键粘贴到当前目录 | 剪贴板机制 | pane.py paste() |
| 13.5 | 删除 | P0 | 🟢 | 右键删除到回收站 | send2trash | pane.py delete_selected() |
| 13.6 | 重命名 | P0 | 🟢 | 右键重命名 | 内联编辑 | pane.py rename_selected() |
| 13.7 | 新建文件夹 | P1 | 🟢 | 右键新建文件夹 | os.makedirs | pane.py create_folder() |
| 13.8 | 新建文件 | P1 | 🟢 | 右键新建文件 | open(path, 'w') | pane.py create_file() |
| 13.9 | 打开终端 | P1 | 🟢 | 右键在当前目录打开终端 | subprocess | pane.py open_terminal_here() |
| 13.11 | 添加到收藏夹 | P2 | 🟢 | 选中目录后右键添加到收藏夹 | BookmarkSidebar.add_bookmark_with_path() | pane.py |

---

## 14. 批量重命名

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 14.1 | 批量重命名 | P1 | 🟢 | 选中多个文件，打开批量重命名对话框，支持正则、模板、序号 | QDialog + 正则引擎 | batch_rename.py BatchRenameDialog |
| 14.2 | 正则替换 | P1 | 🟢 | 支持正则表达式匹配和替换 | re 模块 | batch_rename.py preview_regex() |
| 14.3 | 模板重命名 | P1 | 🟢 | 支持 [N]序号 [Y]年 [M]月 [D]日 等模板 | 模板解析器 | batch_rename.py preview_template() |
| 14.4 | 大小写转换 | P2 | 🟢 | 支持全大写/全小写/首字母大写 | str 方法 | batch_rename.py preview_case() |
| 14.5 | 预览功能 | P1 | 🟢 | 重命名前预览新文件名 | 实时预览列表 | batch_rename.py update_preview() |

## 15. 文件校验和

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 15.1 | 创建校验和 | P1 | 🟢 | 计算文件的 MD5/SHA256 校验和 | hashlib 模块 | checksum_tool.py ChecksumDialog |
| 15.2 | 验证校验和 | P1 | 🟢 | 对比文件校验和与预期值 | hashlib 模块 | checksum_tool.py verify() |
| 15.3 | 校验和文件 | P2 | 🟢 | 生成/验证 .md5/.sha256 校验和文件 | 标准校验和文件格式 | checksum_tool.py select_verify_file() |

## 16. 文件比较

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 16.1 | 文本比较 | P1 | 🟢 | 对比两个文本文件，高亮差异 | difflib + QTextEdit | file_compare.py FileCompareDialog |
| 16.2 | 二进制比较 | P2 | 🔴 | 逐字节对比两个文件 | 字节级对比 | - |
| 16.3 | 比较结果导出 | P2 | 🔴 | 导出比较结果为 HTML/文本 | 报告生成 | - |

## 17. 目录同步

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 17.1 | 目录对比 | P2 | 🟢 | 对比两个目录的文件差异 | 文件列表对比 | dir_sync.py DirSyncDialog |
| 17.2 | 双向同步 | P2 | 🟢 | 双向同步两个目录 | 同步算法 | dir_sync.py execute_sync() |
| 17.3 | 镜像同步 | P2 | 🟢 | 使目标目录与源目录完全一致 | 同步算法 | dir_sync.py execute_sync() |
| 17.4 | 同步预览 | P2 | 🟢 | 同步前预览将要执行的操作 | 操作列表预览 | dir_sync.py compare() |

## 18. 压缩包处理

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 18.1 | 浏览压缩包 | P2 | 🟢 | 像浏览目录一样浏览 zip/tar/7z 内容 | zipfile/tarfile 模块 | archive_tool.py ArchiveDialog |
| 18.2 | 解压文件 | P2 | 🟢 | 解压到指定目录 | 解压引擎 | archive_tool.py extract_archive() |
| 18.3 | 创建压缩包 | P2 | 🟢 | 将选中文件压缩为 zip/tar.gz | 压缩引擎 | archive_tool.py create_archive() |
| 18.4 | 支持 7z/rar | P3 | 🔴 | 通过 7z 命令行支持更多格式 | 外部工具调用 | - |

## 19. 文件分割/合并

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 19.1 | 文件分割 | P2 | 🟢 | 将大文件分割为指定大小的块 | 分块写入 | file_split.py SplitWorker |
| 19.2 | 文件合并 | P2 | 🟢 | 将分割的块合并为原始文件 | 顺序合并 | file_split.py merge_files() |
| 19.3 | 分割方案 | P2 | 🟢 | 支持自定义块大小、按数量分割 | 配置对话框 | file_split.py FileSplitDialog |

## 20. 高级搜索

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 20.1 | 文件名搜索 | P2 | 🟢 | 按文件名模式搜索：`*.txt` 按整名通配匹配、`report` 按包含匹配、正则勾选后走 `search` | 通配符与筛选栏共用 `filter_bar.glob_to_regex`（旧版把 `*.txt` 当字面量，按提示写必然 0 结果，v1.9.009 修） | advanced_search.py `build_name_matcher` / SearchWorker |
| 20.2 | 内容搜索 | P2 | 🟢 | 在文件内容中搜索字符串/正则 | 文件遍历 + 搜索（只读前 1MB） | advanced_search.py |
| 20.3 | 搜索结果操作 | P2 | 🟢 | 结果列表可多选；右键/按键批量**打开**、**打开所在文件夹**、**在系统文件管理器中选中**、**复制路径文本**、**复制到…／移动到…**（选目标目录 + 进度框 + 同名冲突询问 + 可取消）、**删除／永久删除**（确认框按实际后果说话）；搬走/删掉的行从结果中移除并让相关窗格重扫 | 多选 `QTreeWidget` + 右键菜单；后台执行走与窗格同一份 `core/file_op_runner.FileOpRunner`（旧版只有“双击→系统文件管理器定位”，且那个机制长在窗格私有代码里） | widgets/advanced_search.py `SearchResultTree` / `show_results_menu` / `_transfer_selected`；tests/test_search_results.py 36 项 + tests/test_file_op_runner.py 10 项 |
| 20.4 | 保存搜索 | P3 | 🟢 | 高级搜索里点「保存当前条件…」起名存下 → 下次在「已保存」下拉选中即按原值填回所有输入框（不自动开搜）；「删除」移除一条 | JSON 单文件 `saved_searches.json`（与 `associations.json` 同目录，路径规则统一到 `config/paths.py`）；存的是**真正喂给 worker 的那份 params**，`collect_params ↔ apply_params` 双向可逆 | config/saved_searches.py + widgets/advanced_search.py；tests/test_saved_search.py 30 项 |
| 20.5 | 搜索窗口非模态 | P2 | 🟡 | 搜索对话框开着时还能用窗格（切目录、用应用内剪贴板 Ctrl+C/V）并一边搜一边看结果 | `QDialog` 改非模态（`show()` + 保留任务栏入口）；现仍为 `exec()` 模态，所以结果列表只能“选目标目录搬运”，不能先复制到应用内剪贴板再到窗格粘贴 | main_window.py `open_advanced_search()` |

## 21. 用户操作菜单

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 21.1 | 自定义操作 | P3 | 🔴 | 用户定义快捷操作（如打开编辑器、转换格式） | 操作配置 | - |
| 21.2 | 操作快捷键 | P3 | 🔴 | 为自定义操作绑定快捷键 | 快捷键配置 | - |

||| 22.1 | 目录树侧边栏 | P1 | 🟢 | 左侧显示目录树，双击导航到当前活动窗格 | QTreeView + QFileSystemModel | tree_sidebar.py TreeSidebar |
||| 22.2 | 活动窗格跟踪 | P1 | 🟢 | 焦点在哪个窗格，目录树导航就作用于哪个窗格 | _active_pane + eventFilter | pane.py eventFilter() |
||| 22.3 | 自动展开控制 | P1 | 🟢 | 可开关自动展开文件夹功能 | 按钮+状态跟踪 | tree_sidebar.py toggle_auto_expand() |
||| 22.4 | 展开/折叠按钮 | P1 | 🟢 | 一键展开或折叠所有节点 | QTreeView.expandAll/collapseAll | tree_sidebar.py |
||| 22.5 | 每窗格独立目录树 | P1 | 🟢 | 每个窗格左侧内嵌独立目录树，路径栏按钮控制本窗格 | PaneTreeView | widgets/pane_tree_view.py |
||| 22.6 | 目录树按钮 | P1 | 🟢 | 路径栏目录树按钮，点击切换本窗格目录树显示/隐藏 | PathBar.tree_btn | widgets/path_bar.py |
||| 22.7 | 窗格内标签页 | P1 | 🟢 | 每个窗格底部可显示标签页栏，独立管理多个路径 | QTabWidget | core/pane.py |
||| 22.8 | 标签页按钮 | P1 | 🟢 | 路径栏标签页按钮，点击切换本窗格标签页栏显示/隐藏 | PathBar.tabs_btn | widgets/path_bar.py |

---

## 优先级说明

| 优先级 | 说明 |
|---|---|
| P0 | 核心功能，MVP 必须 |
| P1 | 重要功能，第一个可用版本应包含 |
| P2 | 增强功能，后续版本迭代 |
| P3 | 锦上添花，有时间再做 |

---

## 更新记录

| 日期 | 更新内容 | 更新人 |
|---|---|---|
| 2026-08-26 | 初始版本，列出全部功能 | - |
| 2026-08-28 | 更新标签页、目录树、终端、四窗格等功能状态；新增标签页重命名、活动窗格跟踪 | - |
| 2026-09-15 | 校正与代码不符的状态：筛选（9.1–9.7）本版接通；永久删除/重命名/取消/导航历史/路径补全改 🟢；Ctrl+Tab、Ctrl+L、Ctrl+D、自定义主题接口查实为未实现（原标 🟢 的「Ctrl+D 切主题」等为假）；新增 12.13–12.18 已实现快捷键；补上清单遗漏的 1.8 列头排序 | - |
| 2026-09-15 | 上一行查实为未实现的三项做完并转 🟢：3.4 / 12.4（Ctrl+L）、4.3 / 12.3（Ctrl+Tab 与 Ctrl+Shift+Tab）、12.5（Ctrl+D，连带主题持久化）；顺手修正表格 21 行多余前导竖线 | - |
| 2026-09-15 | 6.3（右键「打开方式」）实现并转 🟢：新增 `core/open_with.py`（三平台候选枚举 + 启动 + Windows 系统对话框）与窗格子菜单接线；6.1 的验证方式改写为实际可行路径（原写「设置界面配置」，但本仓从来没有那个界面） | - |
| 2026-09-16 | 20.4（保存搜索）实现并转 🟢：新增 `config/saved_searches.py` 与 `config/paths.py`（文件关联的配置目录规则改为向它委托）；同时修一个读代码时发现的真 bug（高级搜索非正则模式下 `*.txt` 被 `re.escape` 当字面量，按 placeholder 写必然 0 结果）；20.3 回退为 🟡（原标 🟢 与代码不符：结果列表没有批量操作） | - |
| 2026-09-16 | 8.4（收藏分组）实现并转 🟢：新增 `config/bookmarks.py`（Qt 无关的树模型 + JSON，规则全在这层）与重写的 `widgets/bookmark_sidebar.py`（分组树、拖拽重排/挪组、展开持久化、id 引用）；8.1–8.3 的“实现情况”同步改为真实形状（旧版是平铺 `QListWidget` + `currentRow()` 当下标，且 8.2 写的“拖目录进来收藏”根本没接外部拖放） | - |
| 2026-09-16 | 20.3（搜索结果批量操作）实现并转 🟢：抽出 `core/file_op_runner.py`（后台线程 + 进度框 + 冲突询问 + 取消，窗格与搜索共用一份），结果列表加多选/右键菜单/键位与复制到、移动到、删除；新增 12.19（结果列表键位）与 20.5 🟡（搜索窗口仍为模态）。顺带修两个读代码发现的真 bug：进度对话框从未弹起（`Qt.TextInteractionFlags` 不存在的 AttributeError 被 `except` + `debug` 静默咽掉）、首次同名冲突的用户决策被静默丢弃（`invokeMethod` 拿不到槽返回值） | - |
| 2026-09-16 | **补记**：v1.9.012（2.11 拖放默认动作对齐资源管理器）当时只加了 2.11 行、漏写本表记录。改动是 `file_operations.same_volume()` / `decide_drop_action()` 一份判据供窗格与 `move()` 共用，Ctrl/Shift 强制 > 同目录树内拖动 > `possibleActions` 硬约束 > 同卷移动/跨卷复制 | - |
| 2026-09-17 | Linux 第二批「判据去 `nt` 化」：新增 `core/mounts.py` 作为全仓唯一的「是不是慢位置」判据（POSIX 挂载表 + 最长前缀 + fstype），删掉两份 `if os.name != 'nt': return False` 的短路 —— 网络/慢盘的保守策略（不挂 watcher、重复导航强制重扫、删除文案说「永久删除」）在 Linux 上**第一次真的生效**；新增 3.5（判据）与 8.5（首启动默认收藏读 XDG `user-dirs.dirs`）；2.4 / 12.10 的文案分类改为两端都算。顺带修一个测试套件的假红：`test_date_presets` 的时刻写在 `parametrize` 参数表里（收集期求值），跨午夜跑必红 | - |
| 2026-09-17 | v1.9.014：**第一节在 Linux 真机（linux230 / Ubuntu 24.04）跑全量** —— 单进程 572 passed / 6 skipped（定序 1 + 随机 3），与 Windows 575+3 总数吻合。修一条产品错：`_list_linux` 无条件追加内置候选，与 Windows 的「太少才补」不一致 → 抽成两端共用的 `needs_builtin_topup()`（6.3 实现情况已补）；其余 5 个失败都是用例里写死的 Windows 假设（`E:\` 当异设备、`\` 当分隔符、找 `python` 而不是 `python3`、测试替身不完整）。那个拖很久的随机段错误定性为**用例泄漏 app 级 `stylesheet`**（`tests/conftest.py` 现在每个边界还原全局态），崩率 12/12 → 1/12，整场 0 崩；产品的 250ms 延迟建窗格经真机确认无误，保留 | - |
| 2026-09-17 | v1.9.015：**Linux 发布链路第一批（linux-gap §6）四条全部落地并在真机出包验通**。`build-linux-docker.sh` 的 `--add-data` 改为“存在才带”（`resources/icons` 缺了仍算硬错）→ 干净克隆不再必失败；Dockerfile 补 `pillow-heif`、删 `cairosvg`、镜像升 3.11（产物里现在真含 `_pillow_heif…so` + `libheif`）；Linux 构建入口收敛为 `build-linux-docker.sh` 一条（`scripts/build.sh` 改为转发，文档同步）；`apply_windows_native_icon` 加平台守卫（并**推翻**了“每次启动白抛两次”的旧结论——调用点早已门控）。真机额外拓出三个产品/工层 bug：崩溃日志不可写导致**只读安装目录下启动即死**（已修，见 4.6/45 条）、`$DATA_ARGS` 在宿主侧展开吞掉 `main.py`、bullseye LTS 结束后镜像不可重建（已改 archive.debian.org）。L1 已过，L11 查清一半（wheel 只带 ibus/compose，fcitx5 仍待带） | - |

---

**文档版本**：v1.6  
**最后更新**：2026-09-17
