# Pan4dex 万格 — 更新日志

> 每次发布更新时，按分类记录变更内容。

---

## 分类说明

| 分类 | 说明 |
|---|---|
| 🚀 功能增强 | 新增功能、体验优化 |
| 🐛 缺陷修复 | Bug 修复 |
| 📝 文档更新 | 文档新增或修改 |
| 🎨 UI/UX | 界面、交互、主题变更 |
| ⚡ 性能优化 | 速度、资源占用优化 |
| 🔧 工程 | 构建、打包、CI 变更 |

---

## 更新记录

### v1.9.013 — 2026-09-17（开发分支 dev/shell-behavior-smb-perf）

#### 🐛 缺陷修复：网络/慢盘保护在 Linux 上被整体关掉（`docs/linux-gap.md` 第二批）
- 根因不是“Linux 代码缺失”，而是入口写成了 `if os.name != 'nt': return False`，而且
  这个判断当时有**两份**（`DirStoreModel._is_network` 与 `file_operations._is_network_path`）。
  在 Linux 上因此一直不生效的有：gvfs / CIFS 挂载上**不挂 watcher**、**重复导航同一目录
  强制重扫**、导航时不拿同步 `stat` 猜目录
- **删除确认框在 Linux 上给了假承诺**：`describe_removal()` 里区分网络位置的分支挂在
  `elif os.name == 'nt'` 下面，而在 Linux 上这判据本来就恒为 `False` —— 两层都坑在一起，
  在 gvfs 里按 Del 会被告知「已移到回收站」，而东西是**直接没了**

#### 🔧 工程：「是不是慢位置」全仓收敛为一份判据
- 新增 `core/mounts.py`：`is_remote_location()` 为唯一入口，Windows 走 UNC + `GetDriveTypeW`，
  POSIX 解析挂载表（`/proc/mounts` → `mount -p`）按**最长前缀**定所属挂载点、再看文件系统
  类型（cifs / smb\* / nfs\* / 任意 `fuse.\*`（含 gvfs）/ sshfs / rclone / 9p / 虚拟机共享盘…）；
  读表带 10s TTL 缓存
- 两处旧实现改为**委托**（不留第二份判据）；**任何失败一律退化为「按本地处理」** ——
  判据自己出错时不该把导航或删除一起拖失败，代价是宁可多挂一个 watcher
- 不做 `realpath`：解析符号链接要对路径每一级 `readlink`，而这条判据恰恰用在可能已经
  卡住的远端路径上；“经由符号链接访问的挂载点会被判成本地”是**写下来的取舍**

#### 🎨 UI/UX：首启动默认收藏不再写死英文（清单 8.5）
- `default_nodes()` 在 POSIX 上先读 `~/.config/user-dirs.dirs`（freedesktop 标准）——
  中文桌面的家目录里那一个叫 `~/桌面` 而不是 `~/Desktop`，旧版给的是一条永远点不开的空收藏
- 只保留**真实存在**的目录（`default_links` 逐条 `isdir`）：点不开的空收藏不如不给；
  Windows 不读该文件，行为与旧版一致；解析拆成纯函数 `parse_user_dirs()`（认 `$HOME`
  与 `~` 两种写法，不做无差别 `~` 替换）

#### 🧪 测试：全量 569 passed / 1 skipped（两轮一致）
- 新增 `tests/test_mounts.py` **82 项**：把 POSIX 判据拆成三段纯函数
  （`parse_mount_table` / `longest_matching_mount` / `posix_is_remote`）之后，Linux 的整张
  判定矩阵在 **Windows 主机上就能测满**（喂一份真的 `/proc/mounts` 文本进去）——
  推翻了“Linux 专属代码必须 Linux 才能测”这条推断
- `tests/test_m2_file_operations.py` 去掉两个 `skipif(os.name != 'nt')`、新增 2 项文案用例；
  `tests/test_bookmarks.py` 新增 `TestDefaultXdgDirs` 9 项（该文件 85 → 94）
- 修一个**测试套件的假红**：`test_date_presets` 的时刻写在 `@pytest.mark.parametrize` 的
  参数表里，参数表在**收集阶段**求值、被测函数在**执行时**才读时钟 → 跨过午夜就
  “今天/昨天”整体错一天、三条一起红（本仓连撞三次）。改为参数表里只放构造器
- 变异验证 15 条（逐条回退旧行为）：**14 条被抓住、1 条为等价变异**（`#` 注释过滤与
  键名 `startswith("XDG_")` 语义重叠，删掉不会红 —— 属代码冗余而非漏测）。首轮存活的
  两条都是真问题：最长前缀的边界检查被“更长的条目也在表里”兜底（要构一表只留
  `/` 与 `/mnt/nas` 才能单独钉住）；“只在 nt 分类”这类门控在 Windows 宿主上永远走得对
  （得 `monkeypatch.setattr(mod.os, "name", "posix")` 把宿主也当成 POSIX）

#### 📝 文档更新
- 新增 `docs/linux-gap.md`（Linux 能力对照与差距，47 处行号引用逐条核对命中）；本版的
  三项改动在它 §6「第二批」里标 ✅，§3.4 实测表同步为 v1.9.013 的口径
- `architecture.md` 新增 `mounts.py` 一行，`dir_model.py` / `bookmarks.py` 两行措辞改为真实形状；
  `AGENT.md` 新增一条「平台判据必须两边都有」的设计决策，并把“网络目录完全不挂”两处
  说法订正为“网络/慢位置”（判据两端同一个）
- `feature-checklist.md` 新增 3.5（网络/慢位置识别）与 8.5（首启动默认收藏），2.4 / 12.10
  的验证措辞改为两端都算；**补记 v1.9.012 漏写的更新记录行**
- `gotchas.md` 新增第 43 条（四个坑：最长前缀必须拼边界且根挂载特例、`\040` 是空格、
  同挂载点重复取最后一次、判据不做 `realpath`），第 39 条补“时刻写在参数表里”这
  第二种形状，审查清单补 2 项；`docs/changelog.md` 本节顺手订正上一版文档对慢盘优化的
  两处不准确说法（缓存 TTL 2s 是两端同一条规则；全仓从来没有“进度节流”这回事）

#### ❗ 仍未解决
- Linux 真机验收（L1-L15）仍需一台可达的 Linux 主机；本版新代码在真机上只验到
  「挂载表本身长什么样」这一层
- 第三批（`QFileIconProvider` 类型图标、POSIX 权限列、`dolphin/nautilus --select`）未动

### v1.9.012 — 2026-09-16（开发分支 dev/shell-behavior-smb-perf）

#### 🎨 UI/UX：拖放默认动作对齐资源管理器（清单 2.11）
- **从同一个盘往窗格拖文件，现在是「移动」**（旧版无论从哪里拖入一律复制，拖完原处
  还留一份）；从U盘/另一张盘拖入仍是复制。Ctrl 强制复制、Shift 强制移动照旧
- **源端只允许复制时，我们绝不「移动」**：外部拖入先读 `possibleActions()` 当硬约束，
  不许 move 就永远不会走到删源那一步（否则会删掉别人的文件）；源端只填了
  `proposedAction()` 的（很多外部程序就这样）退一步拿它当约束
- **同目录树内拖动总是移动**：同窗格内拖到别的目录行、或把当前目录里的东西拖到子
  目录，不按 Shift 也是移动
- 两处「落回自己所在目录」补了无操作防护（同窗格拖到空白处、外部源就在目标目录）——
  旧版会走到同名冲突询问里去，问用户「这个文件已经存在，要怎么办」

#### 🔧 工程：卷判据与跨卷移动共用一份
- `same_volume()` / `decide_drop_action()` 落在 Qt 无关的 `core/file_operations.py`（与
  `describe_removal()` 同族），窗格只做「Qt 枚举 → bool」的翻译；`FileOperations.move()`
  的跨卷分支改为复用 `same_volume()`，不留第二份 `st_dev` 比较
- 判据**拿不准一律按跨卷 = 复制**：`os.stat` 失败、UNC 路径都算不确定（Windows 上不同
  共享的 `st_dev` 可能同为 0，会被误判成同卷然后删源）。比的是源的**父目录**而不是源
  自己 —— 卷属于目录，而拖拽决策那一刻文件可能已经被别处移走
- 拖拽 MIME 负载里的 `default_action` 字段删了：动作由**接收端**按上面的规则算，源端建
  议没有约束力，留着只会让人以为它能决定动作

#### 🧪 测试
- 新增 `tests/test_drop_action.py` 12 项（真造 `QDropEvent` 打 `dropEvent`）：外部同卷→移动、
  跨卷→复制、Ctrl→复制、Shift+跨卷→移动、`possibleActions` 单允许的两条、两个都不允许→
  复制、`possible=Copy` 与 `proposed=Move` 矛盾→按约束走复制、两处落回自身目录→无操作、
  urls 分支同目录树拖动→移动，另有一项钉住「PyQt6 里 `setDropAction()` 不生效」
- `tests/test_m2_file_operations.py` 新增 `TestDropActionRules` 9 项 + `TestCrossVolumeMove` 1 项；
  跨卷那条不能靠 mtime 断言（同盘 `shutil.move` 是 rename，也保 mtime），改为监视
  `FileOperations.copy` 是否被调到
- 全量 **476 passed / 1 skipped**，随机序与 `-p no:randomly` 两轮一致；变异验证 19 条全部
  被杀（首轮存活的 2 条都是用例本身不成立，见 gotchas 第 42 条）

#### 📝 文档更新
- `architecture.md` §3.2 拖拽协议重写（含动作决策表）；`implementation.md` §2.5 同步，并
  修掉一处旧文里「用 `drag.result()` 判断动作」的错误说法
- `gotchas.md` 新增第 42 条：手工构造 `QDropEvent` 的三个坑（`setDropAction` 空操作、构造
  参数是单个 DropAction 不是集合、事件不接管 `QMimeData` 生命周期会当场 access violation），
  以及「拿不存在的 UNC 路径测判据是假故事」

### v1.9.011 — 2026-09-16（开发分支 dev/shell-behavior-smb-perf）

#### 🚀 功能增强：搜索结果列表的批量操作（清单 20.3）
- 结果列表从“只能双击→在系统文件管理器里定位”做成真的可用：**多选** + 右键菜单 +
  键位，动作有**打开**、**打开所在文件夹**、**在系统文件管理器中选中**（上限 5 个，
  一人开十个窗口是灾难）、**复制路径文本**、**复制到…／移动到…**（选目标目录）、
  **删除／永久删除**（确认框按实际后果说话）
- **`SearchResultTree`** 只接键位并发信号（Enter 打开、Ctrl+Shift+Enter 打开所在目录、
  Del 回收站、Shift+Del 永久删除、Ctrl+C 复制路径）；不接 Enter 会被 QDialog 的
  “自动默认按钮”抢走 → 按 Enter 变成关闭对话框
- **双击语义改为“打开”**（资源管理器习惯），原来的“定位”进右键菜单保留
- 对齐 Explorer 的取舍：右键压在未选中行 → 选区收到那一行；压在选区内 → 保留整组；
  多选超 5 个要确认才开；菜单项带条数；选区**按显示顺序**算（`selectedItems()` 给的
  是点选顺序，不然确认框列的“前 5 个名字”与屏幕上不一致）
- **结果列表是快照**的收尾：搬走/删掉的行从列表里移除并退回 5000 行显示额度（不退
  回来，搬完一次就再也显示不出新结果），并让相关窗格重扫（网络目录不挂 watcher）；
  重扫入口用窗格那一个 `Pane._refresh_dir_everywhere`
- 打开与导航仍只有一份语义：对话框取 `MainWindow.current_pane()`（**不能**用
  `_active_pane`，它只在窗格真的获得过焦点时才被赋值），再调 `Pane.open_file` /
  `navigate_to`；无宿主时菜单与状态栏直说“没有可用窗格”

#### 🔧 工程：后台文件操作抽成 `core/file_op_runner.py`
- 窗格私有那套（后台线程 + 进度对话框 + 同名冲突询问 + 取消 + 丢帧防护）抽为
  `FileOpRunner`，宿主只给四个钩子（`on_status` / `on_bar` / `on_bar_hide` / `on_done`）；
  窗格与搜索共用，**不抄第二份**（`Pane` 净减 ~100 行，`file_ops` 属性与完成后刷新语义不变）
- **文案与判据也一起去重**到 Qt 无关的 `core/file_operations.py`：`describe_removal()`
  （网络位置无回收站 → 说“永久删除不可恢复”，本地说“移到回收站”，正文只列前 5 个名字）
  与 `move_target_inside_sources()`（不能把目录移到它自己或子目录里）
- 进度文案前缀改用**本次操作的 note**（旧版删除/移动进行时状态栏也写“正在复制”）

#### 🐛 缺陷修复（两个读代码发现、自 v0.x 就在的长期问题）
- **进度对话框从来没出现过**：`widgets/progress_dialog.py` 写成 `Qt.TextInteractionFlags`
  （复数，Qt 6 里不存在）→ 构造当场 `AttributeError`，而窗格把建框整段
  `try/except Exception` + `logger.debug` 包着 → **包含唯一取消入口的那个框从诞生起就没了**，
  日志里连痕迹都没有。修 typo + 建框失败提为 `warning` 级 + 用例断言“框真的建起来了”
- **同名冲突里用户点的“替换”被静默丢掉**：旧代码信
  `QMetaObject.invokeMethod(..., BlockingQueuedConnection, ...)` 的返回值当槽结果，而
  PyQt6 在这里永远回 `None` → `_resolve_conflict` 认不得 None → 回退 `keep_both` →
  **文件被改名而不是替换**（窗格走的是同一段代码，同一个毛病）。改为共享对象
  `_ConflictAsk` 回写决策 + 已在主线程时直调（Blocking 会自锁）+ 决策过白名单

#### 🧪 测试
- 新增 `tests/test_file_op_runner.py` 10 项：真线程与 `done` 时机、异常变失败结果、
  进度前缀用本次 note、进度框取消真能传到 `ops.cancel`、结束后拆回调与洗 busy、
  `apply_all` 只问一次且下次操作重问、主线程问冲突不走 Blocking、坏决策降级、
  宿主销毁后丢帧不崩、窗格确实走 runner
- 新增 `tests/test_search_results.py` 36 项：选区取法与右键落点、菜单项与置灰、
  打开/定位/剪贴板实参、拒自嵌与“本来就在目标里”、完成后删行与退额度、失败不删行、
  删除的安全位与确认文案、键位接线、收尾时窗格重扫
- 新增 `TestRemovalWording`（`tests/test_m2_file_operations.py`）5 项：直接钉
  `describe_removal` 的网络/本地/永久三分支与“只列前 5 个”，以及
  `move_target_inside_sources` 的“名字前缀相同的兄弟目录不算子目录”
- 两个新测试文件都带 autouse 护栏：本文件碰到的模态入口没被替掉就当场报错（offscreen
  下真弹一个框就是整个会话挂死）
- **变异验证**： 21 处逐处改坏（选区不排序、删行不退额度、`safe` 位反了、右键不判
  选区、不拦 busy、打开不确认、定位不限量、不叫窗格重扫、菜单不写条数、取消不接线、
  进度前缀写死、不拆回调、不洗 busy、不理策略、白名单形同虚设、主线程走 Blocking、
  枚举名写回复数、文案不判网络、列满 7 个名字、子目录用裸前缀、窗格不走 runner），
  21/21 均有对应用例变红（“主线程走 Blocking”那条以挂死形式被抓住）
- 全量基线 451 passed / 1 skipped（+54），连跑两轮 rc=0；顺手把 `core/pane.py` 的
  行尾改回与全仓一致的 CRLF（拼接脚本留下的纯 LF 会让 git 持续提示转换警告）

#### 📝 文档
- `docs/gotchas.md` 新增第 40 条（PyQt6 的两个静默失败面：枚举复数名、`invokeMethod`
  拿不到槽返回值）与第 41 条（offscreen 测 Qt 的四个坑：真模态框挂死会话、
  `qtbot.addWidget` 与 `sip.delete` 不兼容、`waitUntil` 返回值、`selectedItems()` 顺序）；
  审查清单加四条（“一个行为要做两遍”、`except` 包建 UI、跨线程要答案、测对话框的护栏）
- `docs/architecture.md` 新增 `core/file_op_runner.py` 条目与第 4.5 条（为何抽成 runner）；
  重写第 3.1 节（旧图写的 `FileOperations.execute(request)` 与本仓代码根本不符）与
  第 4.3 条；改写 `file_operations.py` / `advanced_search.py` 两行
- `docs/feature-checklist.md`：20.3 转 🟢，新增 12.19（结果列表键位）与
  20.5 🟡（搜索窗口仍为模态：开着它就用不了窗格与应用内剪贴板）

---

### v1.9.010 — 2026-09-16（开发分支 dev/shell-behavior-smb-perf）

#### 🚀 功能增强：收藏夹分组管理（清单 8.4）
- 新增 **`config/bookmarks.py`**：收藏夹的树模型 + JSON 读写，**不依赖 Qt** —— 结构规则
  （成环、层级、条数上限、老格式迁移、坏记录降级）全在这一层，UI 只画树并把动作翻给
  store。节点 `{id, type: link|group, name, path|children+expanded}`，根是隐式分组
- **`widgets/bookmark_sidebar.py` 整体重写到这棵树上**：新建/重命名/删除分组、嵌套最多
  8 层（超出拒绝并说明）、拖拽重排与挪组、右键「移动到分组…」只列合法目标、展开状态
  与顺序都落盘、Del 键删条目（**只删收藏，不动磁盘**）
- 上限 500 条（只拦新增，不拦编辑）；导入按路径去重且**深入分组里面**，撞上限/超层数
  整批不进（不写一半）；写盘失败返回文案让界面说清楚，不抛
- **兼容老数据**：旧的平铺 `bookmarks.json`（v1）读到即转换，但**改过才写盘** —— 转换有
  bug 时用户原文件还在；文件里读来的 id 一律不信任（可能重复），载入时从 1 重编
- 补上清单 8.2 声称但没做的能力：**从文件列表拖一个目录进侧边栏收藏**（旧版
  `InternalMove` 根本不接外部拖放），落在光标下的分组，拖文件不收，同一路径不收两次
- 主窗口注入一份共用的 `BookmarkStore`：侧边栏、窗格右键「添加到收藏夹」、导入导出
  现在同一棵树（旧版各自读写一份列表）；工具栏「+」的默认目录取活动窗格的当前位置

#### 🐛 缺陷修复
- **行号不再参与任何计算**：旧版拿 `list_widget.currentRow()` 去索引一个平铺 list，中间
  插一个分组之后行号整体错位 → “改这条”变成“改那条”、“删这条”带走别的项；现在树项在
  `UserRole` 里存 id
- 双击一条不可达的收藏（网络盘断开）从**静默无响应**改为明说“目录当前不可达”（旧版
  `if os.path.isdir(path)` 才发信号，用户只当侧边栏坏了）；但存储本身仍**不校验 path**
  —— 存下之后目录才消失是正常事
- 拖拽完成只改 `QTreeWidget` 自己的行序、从不写回存储（旧版）：现在 `rowsMoved` 与
  `dropEvent` 两处都接，并对“顺序没变”早退；**树与模型对不上账时按模型重画且不写盘**
  （宁可弹回也不把残缺顺序写进文件）
- 自查修掉四处：`move_to_group` 把 `can_place`（回空串才是可以）判反 → 只列非法目标；
  导入去重时往**正在遍历的** `node["children"]` 里 append → 分组子项翻倍且存盘
  `KeyError: 'id'`；在 `itemCollapsed` 槽里重画整棵树 → 调用方刚拿到的 item 被删；
  `set_expanded(ROOT_ID, ...)` 真的去写根那个没人看的位
- 筛选用例的 `date:昨天` 在凌晨必红（“1.2 天前”从 `time.time()` 减 → 跨两个午夜）：
  参考时刻改成本地中午；实现侧同步修正一个日历天≠ 24 小时（跨夏令时那天 `lo + 86400`
  会漏掉或多吃一小时）

#### 🧪 测试
- 新增 `tests/test_bookmarks.py` 85 项：存储层（默认值与“删空不回灌”、坏 JSON/坏记录、
  v1 只读不写盘、id 不信任、成环/超层/超上限、`can_place` 与 `move` 同规则、子树高度参与
  层数判定、导入导出往返与去重）、侧边栏（画树/展开跟随存储/不可达弹警告/Del 不删磁盘/
  内外两路 `canDropMimeData`/手工重排落盘/对不上账不写盘/一次动作一次写盘/菜单与模型逐项
  对齐/主窗口与窗格共用同一份存储）
- 重写 `tests/test_m4_theme.py::TestBookmarkSidebar`：旧用例直接 `BookmarkSidebar()`（不注
  store），每个都在读写开发机**真实用户配置**里的 bookmarks.json；现在统一注临时目录，
  并钉一条“没碰真实目录”
- **变异验证**：把 10 处实现逐处改坏（`_read_order` 预置层、`can_place` 不判环、`_merge`
  边遍历边追加、`external_dirs` 不判 isdir、`move_to_group` 判反、展开时重画整棵树、
  拖放落点、v1 只读就写盘、`set_expanded` 不挡根、载入 id 不递增），均有对应用例变红
- 全量基线 397 passed / 2 skipped（+85），连跑两轮 rc=0

#### 📝 文档
- `docs/gotchas.md` 新增第 37 条（树形用户数据：改动一律按 id，结构规则放 Qt 之外）、
  第 38 条（PyQt6 树控件拖放的六个实测事实）、第 39 条（时间用例别从 `time.time()` 起算；
  测持久化组件必须注入临时目录）；审查清单加三条
- `docs/architecture.md` 新增 `config/bookmarks.py` 条目，改写 `bookmark_sidebar.py` 与
  `config/paths.py` 两行
- `docs/feature-checklist.md`：8.4 转 🟢，8.1–8.3 的“实现情况”按真实形状改写

---

### v1.9.009 — 2026-09-16（开发分支 dev/shell-behavior-smb-perf）

#### 🚀 功能增强：保存搜索（清单 20.4）
- 高级搜索对话框新增「已保存」一行：下拉选中一条 → 所有输入框按存下的值填回（**不自
  动开搜**）；「保存当前条件…」起名存盘（同名先问是否覆盖）；「删除」移除选中的那条
- 存储新增 `config/saved_searches.py`：`%APPDATA%\pan4dex\saved_searches.json`（与
  `associations.json` 同目录；目录规则收拢到新增的 `config/paths.py`，`FileAssociations`
  改为向它委托，不再各处各算一份）。上限 50 条、名字最长 60 字符；文件读坏当空表、
  逐条校验（一条坏记录不带走其余）；写盘失败返回 `(False, 文本)` 让界面说清楚，不抛
- **存的是真正喂给 worker 的那份 params**（字节数、归一化后的扩展名），所以「保存的
  条件」与「会执行的条件」必然同一份；开始搜索与保存共用同一个 `collect_params()`
- 只存条件、**不存结果**：文件早就变了，结果列表每次都得重扫

#### 🐛 缺陷修复
- 高级搜索非正则分支把输入 `re.escape` 后 `search` → 界面上教的 `*.txt` 被当成字面量，
  **按提示写必然 0 结果**；改为与列表筛选栏共用一份 `glob_to_regex`（整名通配），
  普通串仍是包含、勾了正则仍是 `search`
- 正则写错过去不报错，带着坏条件扫完盘返回 0，与「真的没搜到」看起来一模一样 →
  `collect_params()` 先试编译并当场报错
- 载入大小条件时两个输入框**共用一个**单位下拉：一度按「各自能整除的最大单位」填回，
  会把 1 KB 变成 1024 MB → 改为选两者都放得下且都不失真的最大单位；整除不了（只可能
  来自手改过的 JSON）时如实报「已按最接近的值填入」，不静默降级成「无限制」
- 保存时的默认名一度可能是下拉里那句占位提示 → 只在真选中某条时用它作默认名

#### 🧪 测试
- 新增 `tests/test_saved_search.py` 30 项：存储层（读写往返、排序稳定、同名覆盖、上限
  只拦新名字、坏 JSON 当空表、坏记录逐条跳过、写失败返回而不抛）、匹配语义（glob 整名
  匹配、大小写口径、正则 `search`、空模式全命中、整条 worker 链 glob 找到 5 个 txt、
  内容搜索尊重大小写选项）、对话框（校验文案、单位换算与类型归一化、`apply → collect`
  往返一模一样、上限边界 99999 KB、失真必须报、保存/载入/删除、记录被别的窗口删掉不
  炸、主窗口把自己的存储注进对话框）
- **变异验证**：把五处防护改坏（glob 分支、单位整除判定、失真说明、保存前校验正则、
  默认名的占位保护），对应 8 项测试确实变红 → 无假绿
- 全量基线 312 passed / 1 skipped（+30），连跑两轮 rc=0

#### 📝 文档
- `docs/gotchas.md` 新增第 35 条（两种匹配语义写在两处就有一处骗人）、第 36 条（把界面
  换算后的值存进配置：往返要双向可逆、表示不了要说）；审查清单加两条
- `docs/architecture.md` 补 `config/paths.py`、`config/saved_searches.py`、
  `widgets/advanced_search.py` 三行，并在 `filter_bar.py` 行写明 `glob_to_regex` 是全仓
  唯一一份通配符实现
- `docs/feature-checklist.md`：20.4 🔴→🟢；20.1 的验证方式改写为实际语义

#### ⚠️ 状态更正与已知缺口
- **20.3「搜索结果操作」原标 🟢 与代码不符，回退 🟡**：结果列表只有双击→在系统文件
  管理器中定位，没有批量复制/移动/删除（本轮查实清单时顺手发现）
- 「已保存的搜索」只挂在高级搜索；列表筛选栏（Ctrl+F）那套 `ext:`/`size:`/`date:`
  条件还没有保存入口 —— 两者条件格式不同，本轮不做统一，免得造出半套共用
- 载入时不预先校验目录：存下的目录被删/改名后照填，点搜索才报「目录不存在」（不静默
  改用户的条件）

### v1.9.008 — 2026-09-15（开发分支 dev/shell-behavior-smb-perf）

#### 🚀 功能增强：右键「打开方式」（清单 6.3）
- 单选文件右键 →「打开方式」子菜单，列出**本机**能打开该类型的程序（Windows 注册表 /
  Linux `.desktop` / macOS `Info.plist`），当前默认程序带「（默认）」标记
- 菜单项 = **只这一次**用它打开，不改默认。Windows 末项「选择其它应用…」直接调系统
  对话框（它自带「始终」按钮，等价资源管理器的完整入口）；Linux/macOS 没有可调用的
  一键系统对话框 →「选择其它应用并设为默认…」挑程序、打开一次并写进本仓关联表
  （菜单文字里写明了“并设为默认”，不静默改用户机器上的关联）
- 性能护栏：候选**只在子菜单真要显示时**枚举（实测本地注册表 2ms，但多数右键根本不
  展开这一层）；按扩展名 TTL 300s 缓存；exe 去重 + 上限 15 项；类型化兜底仅当候选
  不足 5 项时才补。候选来自本机而非被浏览的目录 → 不受 SMB 延时影响、不产生行信号

#### 🐛 缺陷修复（开发自查发现，未流到用户）
- 显示名一度取 `HKCR\<progid>` 的默认值 → 那是**文档类型描述**，实测三个 IDE 全叫
  「Text Source File」（三个同名项等于没有选项），AppX ProgID 更是一串哈希；改为只认
  `Application\ApplicationName`，其值为路径或 MUI 引用时回退 exe 文件名
- 兜底表一度不分文件类型 → `.txt` 挂上画图 / Word；改为按大类查表
- 候选枚举任何一步失败只少一项、绝不外抛（右键菜单不能因为读不到注册表而弹不出来）

#### 🧪 测试
- 新增 `tests/test_open_with.py` 24 项：命令行切分（含 `""` 字面引号）、占位符剥离、
  `.desktop` 解析与 MIME 通配、`list_apps` 的 TTL 缓存次数/去重/上限/异常吞掉；窗格侧
  「构造菜单不枚举、展开才枚举」「默认标记」「点选只打开不改默认」「枚举炸了菜单仍
  可用」「目录与多选不提供」「挑程序写关联并清缓存」「取消不动关联表」；Windows 真
  注册表冒烟（候选的 exe 必存在、显示名不等于文档类型描述）
- **变异验证**：把三处防护（提前枚举 / 不判文件 / 不兜异常）分别改坏，对应测试确实变红
- 全量基线 258 → **282 passed / 1 skipped**，两轮 rc=0

#### 📝 文档
- `docs/gotchas.md` 新增第 33 条（ProgID 默认值是文档类型描述 + 「打开方式」的三条硬
  约束）、第 34 条（测试里手工造的父 `QMenu` 被 GC 连带删掉子树），审查清单加两条
- `docs/architecture.md` 新增 `core/open_with.py` 行；`docs/feature-checklist.md` 6.3 转 🟢，
  并把 6.1 的验证方式**改写为实际可行路径**（原写「设置界面配置」，但本仓从来没有
  那个界面）

#### ⚠️ 已知缺口（本节有意不做）
- 超大图标视图（`ThumbnailView`）本身就没有右键菜单，因此也不会有「打开方式」
- 多选文件不提供「打开方式」（资源管理器会逐个应开，本仓暂不做）
- 候选项无应用图标（不为此引入 `QFileIconProvider`）

---

### v1.9.007 — 2026-09-15（开发分支 dev/shell-behavior-smb-perf）

#### 🚀 功能增强：补齐上版查实为「未实现」的三个快捷键
- **Ctrl+Tab / Ctrl+Shift+Tab 循环切换标签页**（清单 4.3 / 12.3）：到端点回绕（浏览器习惯），
  只有一个标签页时不异常；走 `setCurrentIndex`，与点击标签页同一条路径（状态保持、
  标签栏同步都不额外做）。文件菜单新增两项可见菜单项（快捷键不隐藏）
- **Ctrl+L 聚焦当前窗格路径栏**（清单 3.4 / 12.4）：`PathBar.focus_for_input()` 把现有路径
  **全文选中**（不是光标置末），按一下就能直接打新路径；窗格已销毁时静默返回
- **Ctrl+D 切换深色/浅色主题**（清单 11.2 / 11.3 / 12.5）：菜单里两个主题项改为**可勾选**
  并跟随当前主题（之前看不出现在用的是哪个），菜单项与 Ctrl+D 同源走 `set_theme()`
- **主题切换现在会持久化**：`set_theme()` 写回 QSettings `theme`。启动时读的就是这个键，
  不写回去就是“按了 Ctrl+D、重启又跳回去”（设置对话框早就在写，菜单/Ctrl+D 忘了写）

#### 🐛 缺陷修复
- **Ctrl+Tab 在没注册快捷键时“看上去已经能用”**：`Tab` 是焦点导航键，焦点一落到另一个
  标签页里的控件，`QStackedLayout` 就跟着焦点换页 —— 但换页按的是**整个窗口焦点链**
  而不是标签页顺序，一页里有 N 个可聚焦控件时要按 N 次才真翻页（余下几次“按了没反应”），
  焦点落在哪也完全随机。实测（把 QAction 的键改成 `Ctrl+Alt+Tab` 后真按 Ctrl+Tab）
  `currentIndex()` 仍然 0 → 1 而 QAction 未触发 —— 只断言索引会把这条假路当成实现
- 清单表格里 21 行多了一个前导竖线（行首写成两个竖线），渲染出来整表左边多一个
  空单元格（第 4 / 13 节等），已修正

#### 🧪 测试
- 新增 `tests/test_nav_shortcuts.py` 9 项：循环与回绕、单标签 noop、真按键事件必须
  **接到 `QAction.triggered` 计数**（防止靠焦点导航碰巧过的假绿）、路径栏全选、死窗格守卫、
  主题双向切换 + 持久化 + 菜单打勾、快捷键确实挂在 QAction 上
- **修掉一个“隔文件污染”**：合成按键（`qtbot.keyClick(..., ControlModifier)`）会把 Ctrl 留在
  `QApplication.keyboardModifiers()` 里，而 `setCurrentIndex()` 无事件时拿这个全局态算
  `selectionCommand()` → 把已选行取消，导致不相干的
  `test_pane_dir_store.py::test_refresh_preserves_selection` 挂掉。现在测试收尾抹回
  `NoModifier` 并断言（`docs/gotchas.md` 第 32 条）
- 全量套件：`258 passed / 1 skipped`（0 失败），连续 3 轮 rc=0 无硬崩

#### 📝 文档
- `docs/gotchas.md` 第 31（`Tab` 系快捷键必须用 QAction 抢在焦点导航前面）、
  第 32（带修饰键的合成按键漏给后续测试）
- `docs/feature-checklist.md`（v1.3）：3.4 / 4.3 / 11.2 / 11.3 / 12.3 / 12.4 / 12.5 转 🟢 并填实现位置

---

### v1.9.006 — 2026-09-15（开发分支 dev/shell-behavior-smb-perf）

#### ✨ 新功能：列表筛选（Ctrl+F）
- **窗格列表可按名称/扩展名/日期/大小/类型/正则筛选**（`widgets/filter_bar.py` 重写）：
  Ctrl+F 或编辑菜单「筛选当前目录…」唤出筛选栏，Esc / 行内 ✕ / 右键「清除筛选」三处可清
- **对齐资源管理器语义**：只筛**当前目录**、不递归（全盘搜索仍走「工具 → 高级搜索」）；
  空格分隔的条件之间是「且」；字段名不区分大小写并支持中文别名
  - 语法：裸文本＝名称包含；`*.log` / `?at` 整名通配符；`name:` / `名称:`；
    `ext:py,md`（目录不匹配）；`type:txt` / `类型:目录`；`is:folder|file` / `属性:文件`；
    `date:今天|昨天|本周|本月|今年` / `date:>=2026-01-01` / `date:2026-01-01..2026-03-01` /
    `date:2026-09`（`/`、`.` 归一为 `-`；`>` 是「整天之后」，`<=` 含整天）；
    `size:>10mb` / `size:1mb-100mb` / `size:空|小型|中型|大型|巨大`；`re:` 正则
  - 筛选栏左侧字段下拉负责拼前缀（自动/名称/扩展名/修改日期/大小/正则）；用户已手写
    `field:` 时以原文为准，不二次加工
- **解析不了的条件降级为「名称包含」而非丢弃**：丢弃会让用户以为筛选生效了却看到整个
  目录（比“筛出 0 项”更难解释）；降级片段记在 `EntryFilter.bad`，状态栏附「条件未识别」提示
- **两个视图一致生效**：列表走代理，超大图标视图（`ThumbnailView`）在自身枚举里过同一份
  `EntryFilter`，不会出现“列表筛过了、图标视图还是全量”
- **状态栏**显示「筛选后 M / N 项」（只问代理与模型，不扫盘）；筛选与「显示隐藏文件」
  开关叠加而非绕过

#### ⚡ 性能优化
- **筛选不碰磁盘、不重扫、不发行信号**：条件编译一次（正则/集合/区间），`filterAcceptsRow`
  逐行只做内存比较，用的全是枚举时已缓存的 `Entry.name/is_dir/size/mtime`；在 SMB 大目录
  上按行数乘网络延时的做法一整条路都没走。行信号是本仓崩溃率主因，而过滤只改视图的
  hidden 状态（`invalidateFilter()` 不增删行）
- **不叠第二层代理**：排序与过滤共用窗格已有的 `PaneSortProxyModel`，避免多一次索引映射
- 输入 **250ms 防抖**：逐字符重筛在上万行目录里肉眼可见地卡
- 图标视图只在条件真含 size/date 时才补 `entry.stat()`（`EntryFilter.needs_stat`），
  纯名称/扩展名筛选不多一次 syscall
- **列头排序也不再碰磁盘**：旧 `PaneSortProxyModel._is_dir()` 每次比较一个
  `os.path.isdir(filePath)`，而一次排序要跑 O(n log n) 次比较 —— SMB 大目录上
  “点一下列头就卡一下”正是这么来的。现在只读枚举时已缓存的 `Entry.is_dir`，
  代理里不存在任何碰磁盘的代码路径（`_is_dir()` 已删，无调用者）

#### 🐛 缺陷修复
- **列头排序两个语义错误**（与筛选同一条链路改到的，之前无任何测试覆盖）：
  1. “目录优先”被排序方向一起反转了 —— 点「大小」倒序，所有文件夹跑到最后去了；
     资源管理器的习惯是**方向只反转同类内部顺序**，目录始终在前
  2. 大小列按**格式化字符串**比（走 `super().lessThan()` 比 `"5 B"` / `"4.0 KB"`），
     字典序把 4 KB 排在 5 B 前面；现在按 `Entry.size` 字节数比，目录并列时按名称；
     修改日期列同样改为按 `Entry.mtime` 而非日期字符串
- **点“清除”后列表仍是筛过的**：防抖窗口内 `_last_query` 未更新，清空文本后“无变化”就
  不发信号。`clear_filter()` 改为先 `stop()` 防抖、再清文本、最后无条件补发一次空条件
- **`tests/test_m4_theme.py` 的 5 个长期失败查实为幻影**：用例测的是根本不存在的接口
  （`save_custom_theme` / `delete_custom_theme` / `export_theme` / `import_theme` /
  `_generate_qss`），`ThemeManager` 真实注册表只有 `name/display_name/qss`。改测真实契约
  （未知主题名返回 None），并新增反向守卫 `test_no_custom_theme_persistence_api`（`hasattr`
  卡住“没有自定义主题持久化接口”这个事实，防止清单再声称「已预留接口」）
- **陈旧断言 `test_filter_proxy_model`**（要求一个未被任何代码引用的 `FilterProxyModel`）
  改写为设计守卫 `test_filtering_lives_in_pane_sort_proxy`（断言不存在第二层代理）

#### 📝 文档更新
- `docs/gotchas.md` 第 29（筛选只改可见行：不叠代理、不碰磁盘）、第 30 条（清除必须无条件发空信号）
- `docs/architecture.md` 更新 `filter_bar.py` / `pane.py` 职责行；`AGENT.md` 新增设计决策
  「列表筛选只用一层代理」
- `docs/feature-checklist.md` 按代码实况校正（文档 v1.2）：筛选 9.1–9.7 接通；永久删除/重命名/
  操作取消/导航历史/路径补全改 🟢；**查实为未实现并标回 🔴** 的有 Ctrl+Tab、Ctrl+L、
  Ctrl+D（原清单写的「Ctrl+D 切主题」为假，主题切换实际在视图菜单）与自定义主题接口；
  新增 12.13–12.18 已实现快捷键

#### 🧪 测试
- 新增 `tests/test_filter_bar.py` 共 46 项：语法解析（含降级/引号/区间/needs_stat）、
  UI（防抖、字段下拉、Esc、清除立即生效）、集成（筛后源模型 `rowCount` 不变、状态栏计数、
  导航后筛选仍生效、图标视图同步）、排序语义（两个方向都目录在前、大小按字节数、
  排序过程一次磁盘访问都没有）
- **全量套件首次全绿**：`248 passed / 2 skipped`（0 失败），连续 3 轮无硬崩。两个 skip 是
  环境条件：系统剪贴板被其它进程占用、退出崩溃 A/B 需指定大目录

---

### v1.9.005 — 2026-09-14（开发分支 dev/shell-behavior-smb-perf）

#### ✨ 新功能
- **本地目录自动更新**：用 Explorer 或别的程序新建/删除/改名文件，窗格列表自己跟上
  （不再需要按 F5）。`DirStoreModel` 只给**当前显示的那个本地目录**挂 `QFileSystemWatcher`
  - 网络目录**一律不登记** watcher —— 那正是拖垮 SMB 的轮询源，网络仍走 TTL 2s + 定向失效
  - 监视器改为**进程级唯一** `_WatchHub`（以 `QApplication` 为父，弱引用计数：同一目录
    被多个窗格监视只占一个句柄）。per-model watcher 不行 —— 模型可被任意时刻的 GC 销毁，
    而 Windows 上目录监视共用一个全局线程，析构与在飞通知会竞态
  - **只监视看得见的那个目录，切走即摘**：监视“曾导航过的所有目录”会把句柄数与通知流量
    随会话无界堆积，实测全量测试崩溃率 0/10（不监视）→ 2/8（per-model）→ **10/10**
    （hub 监视全部）；只监视当前目录 + 登记延迟到事件循环顶层后 0/14
  - **native 登记（`addPath`/`removePath`）不在 `set_directory` 调用栈里做**：只记下目标
    路径，用 0ms 定时器推到事件循环顶层一次性 flush —— 同一轮事件里的连续导航（测试里一个
    用例能连切十几个目录）自动合并成一次登记，不会来回折腾监视线程
  - 通知经 350ms 防抖合并：一次粘贴 N 个文件只重扫一次，不会把列表反复清空重建
  - 应用内改动（粘贴/新建/删除/行内改名）用**类级** `_self_change` 时间戳抑制紧随其后的
    文件系统通知，避免同一次改动被重扫两遍（用户侧＝列表闪一下）；必须类级，因为
    跨窗格 `dirChanged` 同步会让没“改过”的窗格也收到同一次物理改动的通知
  - 代价补回：不监视的目录靠「快照 TTL 过期 + 导航回来重扫一次」保证新鲜（本地/网络
    统一 2s，以前本地快照永久新鲜）
  - 已知残余：抑制窗口 1.5s 内的**外部**改动会被一并跳过；不在屏上的本地目录最多陈旧 2s

#### 🐛 缺陷修复
- **同一次加载白发两遍枚举**（性能 + 稳定性）：`beginInsertRows` / `endRemoveRows` 内部会
  回调 `rowCount(parent)`，而 `rowCount` 里留着「顶层节点未 loaded 且未 loading → 惰性
  `_start_load`」的兼容写法；只要那一刻节点正处于「已清 loading、未置 loaded」的过渡态，
  就会多起一次枚举（新枚举的 `gen` 还把正要采纳的结果算作过期）。现在 `loading` 推至行
  插入完成后才清，并用 `_rows_signal()` 上下文包住每一对 begin/end，期间 `rowCount` /
  `canFetchMore` 不做惰性加载。实测探针：改前每个目录加载调 `_start_load` 2 次，改后 1 次
- **去掉「本地目录到达即重扫」**：刚写过一版（只要已加载就 `_reload_top`），列表行为更正确
  但崩溃率从 1/8 到 **9/10**（枚举量与行信号量翻倍，9 份 dump 全落在 `endInsertRows`）；
  换成上面的 TTL 过期作废（且只走 reset，不额外 removeRows）
- **目录枚举不再用全局线程池**：改用限流的专用池 `dir_pool()`（`_ENUM_POOL_THREADS = 4`，
  与窗格数一致）。此前 `QThreadPool.globalInstance()` 的并发数 = CPU 核数（本机 24），
  faulthandler 转储里能看到 **10 个线程同时卡在 `enumerate_dir`**：数十路并发枚举在 SMB 上
  互抢通道比串行更慢，且成倍的结果投递与条目对象同时砸回主线程（实测崩溃率 1/12 → 0/14）。
  `drain_background_pool()` 相应改为逐池排空（全局池 + 枚举池）
- **残留死窗格把测试（和新窗口）带崩成一片级联失败**：某轮全量测试从平时的 5 个失败
  变成 22 个，全部同一句 `RuntimeError: wrapped C/C++ object of type Pane has been deleted`，
  现场是 `MainWindow.create_menu_bar` → `Pane.set_show_hidden` 里在 `try` 外碰 `pane.model`。
  两个原因叠加：① 窗格在 `super().__init__()` 后就进 `_instances`，延迟建窗格失败时
  一个连 `model` 都没有的废窗格留在注册表里；② WeakSet 反映不了 C++ 侧已删（实测：
  sip 删 C++ 部分时**不清空** `__dict__`，读已有属性不报错，只有读不存在的属性才落到
  Qt 元对象上报 deleted）。现在：入册改到 `__init__` 最后一步，类级操作统一走
  `Pane._live_instances()`（用 `sip.isdeleted` 判死，这是实测唯一可靠手段）。
  生产侧等价故障是“用过一段时间后开新标签/新开窗口直接报错”
- **Qt 对象的销毁时机落在分代 GC 手里 —— 构造中途被拆掉子树**（问题 13 现场 B 的根因，
  本轮定性）：`MainWindow.close_tab` 旧写法 `removeTab` + `deleteLater` 看似确定，实际销毁
  时机完全由 GC 决定：`signal.connect(self.method)` 构成引用环（self → 子控件 → receivers
  → 绑定方法 → self），环只能等分代 GC；而 GC 会在**任意** Python 分配点执行。当一个对象
  同时满足「sip 视为 Python 拥有」+「此刻 C++ 父指针为空」（`removeTab` 正是后者），包装器
  一被回收就当场 `delete` C++ 并级联拆光子树 —— 那一刻若另一个窗格正在构造，拆掉的就是它
  正在用的东西（用户侧＝关标签页后随机崩，或 `RuntimeError: ... QVBoxLayout has been deleted`）
  - 决定性实验：`test_lifecycle + test_m1_core` 组合平时随机失败，`gc.disable()` 下 **22/22 通过**
  - 修复：`close_tab` **握住 Python 引用**（`self._closed_tabs`）+ `hide()` + `deleteLater()`，
    把时机交给事件循环；`tests/conftest.py` 在每个用例边界主动 `gc.collect()`，把由 GC
    决定的销毁集中到没有构造在飞的安全点。**只 `setParent(self)` 归还所有权拦不住**（实测）
  - `_create_remaining_panes`（250ms 延迟建窗格）入口 `sip.isdeleted(self)` 早退，并在确认
    宿主已死时吞掉 RuntimeError（其余继续上抛，不掩盖真错误）—— 旧写法会把异常丢进事件循环
- **`removeTab` 不销毁页内容 → 窗格内标签页越开越多内存只增不减**：`Pane.set_state` 清标签页
  与 `close_pane_tab` 补 `page.deleteLater()`（否则摘下来的页是无主对象，销毁时机同样在 GC 手里）
- **已经试过并回退的做法**（重要）：在生产路径的批量构造入口（`new_tab()`、
  `_create_remaining_panes()` 开头）先 `gc.collect()` 再构造 —— 实测**反而制造新故障**（主动
  回收把“已该死但拖着没死”的对象集中删掉，其中就有即将被使用的宿主：`Pane(parent=self)` 报
  `QuadPaneWidget has been deleted`，一轮从 5 passed 变 2 failed）。**回收本身不是修复，
  消除“随时会被回收”这个状态才是。**
- **条目对象生命周期**（同一段取证导出）：`createIndex(row, col, py_obj)` 交给 Qt 的是裸
  指针，PyQt **不**替我们保持引用（实测：丢引用 + `gc.collect()` 后 300 个条目当场回收，
  而视图仍有 300 行）。因此失效不能直接归还 GC：旧快照挂 `DirNode._stale`，到下一个
  安全点（`endResetModel()` / `endRemoveRows()` 之后）才由 `_drop_stale()` 释放

#### 🧪 测试
- `tests/test_dir_model.py` 新增本地目录监视 9 项：端到端外部新建、只监视本地不监视网络、
  防抖合并、自变更抑制、hub 共享与弱引用计数、死模型的登记被回收、只监视当前目录、
  连续导航句柄不累积、**同一轮多次导航只登记最后一次**；生命周期 2 项：旧快照只在安全点
  释放、节点封顶不删交出过条目的节点
- 新增枚举量约束 3 项：一次加载只发一次枚举、TTL 内导航回来不重扫、枚举池线程数限流
  （锁住上面的三个坑）
- `tests/test_pane_dir_store.py` 新增 2 项（真实 `Pane`）：外部改动自动出现在列表、
  两窗格看同目录时外部改动不互相放大成重扫循环；依赖真文件系统通知的两条端到端用例在
  通知不可用的机器上 **skip 而非假绿**（本机实测通过）
- 注册表存活过滤 2 项（均已回滚验证过判别力）：死窗格不得打断 `set_show_hidden`、
  半途死的窗格不入册
- `tests/test_lifecycle.py` 新增 2 项（均已回滚验证过判别力）：关掉的标签页 widget 必须活到
  `DeferredDelete` 派发（`del` + `gc.collect()` 后子树仍在）、宿主已销毁时延迟建窗格必须静默
  返回而不是抛进事件循环
- 修一个自身会误报的用例：`test_repeating_single_shot_semantics` 等固定 150ms 再断言回调列表，
  全量测试负载高时定时器晚到 → 偶发只剩一条（单跑永远通过）。改为 `waitUntil` + 不依赖到达顺序
- 全量测试：本版本最终设计下连续 12 轮无硬崩（旧基线 3/8；各阶段 10/10 → 9/10 → 2/12 →
  1/12 → 0/14 → 0/12，全部记入 `docs/unsolved-issues.md` 问题 13）；207 项中 201 passed
  / 1 skipped / 5 failed，5 个失败全是 `test_m4_theme` 的陈旧断言（与本版改动无关，已列入待办）

#### 📝 文档更新
- `docs/gotchas.md`：第 12 条改写（现有 watcher）、第 23 条重写为六个约束（只本地、抑制
  自变更、防抖、进程级 hub、只监视当前目录、登记推到事件循环顶层），新增第 24 条（行信号
  重入 `rowCount`）、第 25 条（不要到达即重扫）、第 26 条（枚举不用全局线程池）、
  第 27 条（类级注册表要判死 + 入册时机）+ 审查清单 4 项
- `AGENT.md`：改写“不挂 `QFileSystemWatcher`”的旧说法，新增目录监视六约束
- `docs/architecture.md`：`dir_model.py` 行补充本地 watcher / 网络不挂，并补“为何只监视
  一个目录”
- `docs/unsolved-issues.md` 问题 13：补入本段取证（完整的崩溃率 A/B 表，以及
  三个被探针否证的假设：句柄数超 `MAXIMUM_WAIT_OBJECTS`、`addPath` 跑嵌套事件循环重入、
  通知派发到模型槽才会崩）与“可迁移的结论”；**现场 B 根因已定**（销毁时机落在 GC 手里，
  含三步逐行探针取证链、三处修复、已回退的做法）
- `docs/gotchas.md` 第 28 条：不要把 Qt 对象的生死交给分代 GC —— 移出容器后握住引用再
  `deleteLater`（含三个反直觉关键点：`setParent` 归还所有权无效、`processEvents` 不处理
  deferred delete、测试边界同理）+ 审查清单 1 项

### v1.9.004 — 2026-09-14（开发分支 dev/shell-behavior-smb-perf）

#### 🐛 缺陷修复
- **关闭程序时报错 / 退出码 `0xC0000409`（`docs/unsolved-issues.md` 问题 13 的真实根因）**：
  - 事件循环结束后，`QThreadPool.globalInstance()` 上还有未派发的跨线程投递（枚举结果），
    投递事件里持有一批 Python 对象；线程池与事件队列要等 `~QCoreApplication` 才销毁，
    那时 CPython 已开始收尾，Qt 从非主线程释放它们 → fast-fail（无可捕异常）
  - 需要三者叠加才会触发：真实系统调用枚举 + 后台 `emit` + 足够大的载荷体量
    （System32 4867 条 × 200 模型：8/8 崩；纯 Python 计算的 emit：怎么都不崩）
  - 新增 `core/lifecycle.drain_background_pool()`（clear 未开始任务 → 等在飞跑完 →
    空转事件循环把投递派发完 → 再来一轮），并用 `exec_and_drain(app)` 把它与 `app.exec()`
    绑成唯一入口，`main.py` 改用它
  - **A/B 实测**：收尾不排空 8/8 fast-fail；排空后 8/8 干净退出
- **枚举结果回投到已销毁的模型**：`_on_entries_loaded` 在 `endInsertRows()` 之后读
  `self._show_hidden()` 抛 `AttributeError: 'DirStoreModel' object has no attribute
  '_filter'`（sip 在 C++ 部分销毁时会清空实例 `__dict__`）。现在槽函数先把要用的自身状态
  取完，行插入之后不再读实例状态，`directoryLoaded` 的发射带 RuntimeError 早退
- **`_LoadSignals` 改为以模型为父**：模型销毁→投递源一同销毁，在飞任务的 `emit` 会报错并
  在 `_LoadTask.run` 里被吞掉（不再静默弄死工作线程）。仍**保留绑定方法直连**：接收者必须
  是模型本身，Qt 才会在模型销毁时剔除已排队的投递（试过弱引用 closure 分发，反而直接 AV）
- **双击任何文件都打不开**（本轮冒烟时从旧日志里发现）：`Pane.open_file` 把
  `import sys` / `import os` 写在函数后半段，于是这两个名字在**整个函数**内都是局部名，
  开头的 `if sys.platform == "linux" and os.path.isfile(...)` 必抛 `UnboundLocalError`
  （Windows/Linux 都中招，异常只留在日志里，用户侧就是“双击没反应”）
  —— 删掉这两个多余的局部 import，并加一条全仓 AST 检查用例守住同类“先用后导”
- 效果：全量测试的硬崩由同命令形式下的 3/8 轮降为连续 25 轮全绿（未证明根除，继续观察）

#### 🔧 工程
- `tests/conftest.py`：每个测试边界调用 `drain_background_pool()` 排空后台线程，不留
  竞态窗口给下一个用例
- 新增 `tests/test_shutdown_drain.py`（5 项）：排空会派发挂起的枚举结果、排空后线程池空闲、
  `exec_and_drain` 的顺序契约、子进程积攒 200 轮投递后排空干净退出，以及默认跳过的退出崩溃 A/B
- `tests/test_dir_model.py` 新增 2 项生命周期用例（行插入后不读实例状态 / 在飞×模型销毁静默丢弃）
- `tests/test_regression.py` 新增 `TestNoUseBeforeLocalImport`：双击打开文件的入口用例 +
  全仓静态检查“函数内在 local import 之前用了同名模块级名字”（就是上面那个 bug 的根源）
- `qt_exceptions()` 从 `test_lifecycle.py` 上移到 `tests/conftest.py` 供各文件共用

#### 📝 文档更新
- `docs/gotchas.md` 新增第 21（退出时必须排空后台线程）、22（投递的接收者必须是目标对象）条，
  审查清单补 2 项
- `docs/unsolved-issues.md` 问题 13 由「未解决」改写为已解决，并记录被否证的 4 个假设与
  残余崩溃率的量化评估

### v1.9.003 — 2026-09-14（开发分支 dev/shell-behavior-smb-perf）

#### 🐛 缺陷修复
- **启动阶段延后初始化的回调会在对象销毁后访问已删除控件**（全量测试偶发
  `access violation` 的一类根源，实测可稳定复现
  `RuntimeError: wrapped C/C++ object of type QTabWidget has been deleted`）：
  - **根因**：`QTimer.singleShot(ms, lambda: self.…)` 的定时器不以业务对象为父，
    对象先被销毁时回调照样触发并访问子控件（主窗口启动分 0/100/250/300/400ms
    五档延后工作，“启动就关闭”“快速关标签页”正好踩到）
  - 新增 `core/lifecycle.py`：`call_later(receiver, ms, fn)` 把定时器挂为对象的子对象，
    随对象一同销毁；全仓 16 处延后调度（主窗口 / 四窗格组件 / 窗格导航重试 /
    目录树展开 / 缩略图防抖 / 终端尺寸同步 / 启动图标重设）已全部改用它
- **目录树 `expand_to_path` 遇到永远不存在的路径会以 300ms 无限自调重试**：
  现在重试上限 20 次（约 6s）后停止，不再永久占用事件循环

#### 🔧 工程
- 新增 `tests/test_lifecycle.py`（6 项）：延后回调正常触发、对象销毁/随父销毁后丢弃，
  以及一条“旧写法仍会报错”的反证基线用例；真 MainWindow 在 60ms 被销毁后跑满
  900ms 事件循环，断言无任何 Qt 事件循环内异常
- `tests/conftest.py`：每个测试后确定性回收残留顶层窗口（`sip.delete`）。它把原本
  不可读的偶发 AV 降级为带栈的 RuntimeError，是上面两条得以定位的前提
- 全量测试噪声收敛：修正前每轮固定出现 3 条 `TerminalView has been deleted`、
  约 1/3～1/4 轮直接 AV；修正后连续 8 轮无 AV、无投递异常（残余偶发 AV
  已记入 `docs/unsolved-issues.md` 问题 13）

#### 📝 文档更新
- `docs/gotchas.md` 第 20 条（`QTimer.singleShot` 不随对象销毁）+ 审查清单新增延后执行项
- `docs/architecture.md` 模块表补 `core/lifecycle.py`；`docs/unsolved-issues.md` 新增问题 13

### v1.9.002 — 2026-09-14（开发分支 dev/shell-behavior-smb-perf）

#### 🐛 缺陷修复
- **内嵌终端的线程/生命周期缺陷**（全量测试里反复出现
  `RuntimeError: wrapped C/C++ object of type TerminalView has been deleted`，也是潜在崩溃源）：
  - **根因**：后台读线程直接 `self.xxx_received.emit(...)` 向主线程投递。控件的 C++ 对象
    可能在读线程仍存活时就被删除（Windows 上 `pty.read` 无数据即一直阻塞，join 不回来），
    emit 抛异常打死读线程，并丢一批未渲染的终端输出
  - 现在：投递统一走 `_emit_ui(信号名, ...)` —— **按名字取信号并放进 try**（在已销毁对象上
    连 `self.output_received` 取值都会抛 RuntimeError，传信号对象的写法防不住），
    会话已停/控件已销毁则静默丢弃
  - `MainWindow.closeEvent` 显式 `terminal_panel.shutdown()`：不再残留 shell 子进程；
    另以 `destroyed` 兼容未走 closeEvent 的销毁路径
- **终端面板点 X 关闭后，从菜单重开是个再也没有输出的死面板**：dock 关闭不会销毁
  `QDockWidget` 对象，但旧 `closeEvent` 会杀掉 shell 且无人重启。现在隐藏即保留会话
  （与 VS Code 一致），会话终止改由主窗口关闭接管

#### 🔧 工程
- 新增 `tests/test_terminal_lifecycle.py`（12 项）：投递防护、`close_shell`/`shutdown`
  语义、真删除（`sip.delete`）后的 `destroyed` 兜底与 `_read_loop` 静默退出

### v1.9.001 — 2026-09-14（开发分支 dev/shell-behavior-smb-perf）

#### ⚡ 性能优化
- **文件列表换成自研异步模型 `DirStoreModel`，根治 SMB 卡顿**：
  - **根因**：`QFileSystemModel` 在 SMB 上逐项 `stat` + 挂 `QFileSystemWatcher` 轮询，列一个网络目录要几百次往返，
    共享模型下任一窗格导航还会把卡顿带到其它窗格
  - 现在：`core/dir_model.py` 一次只枚举一个目录（`os.scandir` 一次往返拿到 name/attr/size/mtime），
    在 `QThreadPool` 后台线程完成、主线程零阻塞；当前显示目录作为模型唯一顶层行，
    保证排序代理 `mapFromSource` 可映射
  - TTL 缓存 + 定向失效：应用内改动只失效涉及的目录，F5 只重扫当前目录；
    条目逐窗格副本，不跨窗格共享可变对象
  - 两个侧边目录树本就按需展开、非瓶颈，继续使用 `QFileSystemModel`
- 主线程去逐项 `stat`、缩略图 prefetch 按需、路径补全去全盘扫描、搜索改批量查询（同一分支前期变更）

#### 🚀 功能增强
- **F2 / 右键“重命名”统一为行内改名**（资源管理器习惯）：视图 `NoEditTriggers`，只由 F2/菜单显式 `edit()`；
  编辑委托默认选中主名不含扩展名；提交走 `setData`，**不重置模型**，排序代理自动重排
- **刷新保留选中与滚动**：F5 / 目录重扫前快照选中路径与光标项，异步加载完成后按路径恢复
- 后退/前进/刷新按钮接通、Enter 打开；独立进度对话框 + 取消入口
- 同名冲突对话框（替换/跳过/保留两者/取消 + “对后续执行相同操作”）；复制保留元数据与 symlink 处理
- 网络位置删除语义区分（无回收站→永久删除文案）+ Shift+Delete 永久删除
- 复制地址 / 在 Explorer 中显示 / 状态栏选中计数 / 拖拽修复 / 隐藏文件全局开关

#### 🐛 缺陷修复
- 应用内新建/删除/粘贴/拖放后本地目录不刷新的隐患：新模型无文件系统 watcher，
  所有改动路径统一走 `_reload_after_mutation`（失效缓存 + 重扫 + 保留选中），
  并跨窗格同步（一个窗格改名，其它显示同目录的窗格随之重扫）
- 网络路径导航判定不再多做一次同步 `stat`：改查模型已加载条目（零往返）
- 刷新 / 隐藏开关切换后偶发“新文件迟迟不出现”的竞态：同一目录的多个枚举请求并发时，
  旧快照会因幂等守卫永久占位；改为按**请求代次（gen）**作废过期结果
- `index(path)` 曾为“非当前显示目录”的条目返回索引，这类索引经排序代理映射后
  看似有效实则错行（行内改名误定位、不再导航）；现只解析当前显示目录，
  任意路径是否为目录改用 `entry_is_dir()`（纯内存）

#### 🔧 工程
- 删除 `use_new_model` 双轨开关与共享的 `ExifFileSystemModel`：文件列表唯一使用 `DirStoreModel`，
  不再有新旧模型两套代码路径
- 新增 `tests/test_pane_dir_store.py`（8 项窗格级行为：列目录/导航/隐藏开关/行内改名/
  刷新保留选中/本地改动可见/跨窗格同步），取代旧的 `tests/test_pane_new_model.py`

### v0.9.687 — 2026-09-09

#### 🐛 缺陷修复
- 修复复制粘贴大文件（几个 GB）时**界面完全无反应**的问题：
  - **根因**：复制/移动/删除在 GUI 主线程同步执行，`shutil.copy2` 大文件期间界面冻结且无任何进度反馈
  - 现在：文件操作移入**后台线程**（复制/移动/删除/粘贴/拖放全部覆盖），界面保持可操作；进度经信号回主线程实时更新
  - **大文件字节级进度**：单文件分段拷贝（1MB/次），状态栏显示实时百分比与已复制/总大小（如 `正在复制: movie.mp4 (1.2 GB/4.8 GB)`），不再只按文件数跳进度
  - 取消支持：`FileOperations.cancel()` 在下一分段拷贝前生效（保留原接口，供后续取消按钮/快捷取消使用）

### v0.9.686 — 2026-09-09

#### 🐛 缺陷修复
- 修复 Linux 下目录树展开/导航时**上下反复跳动**的问题：
  - **根因**：展开目标目录后，滚动居中逻辑会在 4.8 秒内轮询强制滚动 16 次（每 300ms 一次 `scrollTo(PositionAtCenter)`）；目录异步加载期间树高持续变化，每次强制居中都把目标行来回拉拽，表现为目录树上下蹦动多次（Windows 本地盘加载快不明显，Linux 慢路径下暴露）
  - 现在：展开后**立即滚动居中一次**，目录加载静默（稳定定时器，行插入期间重置、无新行插入 800ms 后）再**收尾居中一次**，并标记滚动已稳定，后续行插入不再触发滚动

### v0.9.685 — 2026-09-09

#### 🚀 功能增强
- Linux 右键菜单新增「运行」与「加运行权限」：
  - **运行**：直接执行可执行文件（有执行权限的文件，或 AppImage 这类明确的可执行程序）
  - **加运行权限**：为无执行权限的文件 `chmod +x`，操作后视图权限列立即刷新
- Linux 双击可执行文件（有 x 权限或 AppImage）**直接运行**，不再走 xdg-open：
  - AppImage 无执行权限时自动加权限后运行（按扩展名 `.appimage` 或文件头 `AI\x02`/`AI\x01` magic 识别）
  - 运行失败（如普通文本文件被加了 x 位）自动回退到默认打开方式

### v0.9.684 — 2026-09-09

#### 🐛 缺陷修复
- 修复 Linux 版无法输入中文：
  - **根因**：PyQt6 wheel 不携带 Qt6 输入法插件（`platforminputcontexts`），打包未包含输入法插件，且未设置 `QT_IM_MODULE`，Qt6 应用完全无法输入中文
  - 现在：构建时把系统 Qt6 输入法插件（ibus / fcitx5 / compose，`resources/tools/qt6-im-plugins/`）打入应用包；启动时在创建 QApplication 前自动检测系统输入法并设置 `QT_IM_MODULE`（优先 fcitx5 → ibus；用户已显式配置则尊重）
  - 目标机需运行对应输入法守护进程（58 上 ibus-daemon 已在运行，已验证 Qt 成功加载 `libibusplatforminputcontextplugin.so`）

#### 🔧 工程
- Linux 构建脚本新增打包 `resources/tools/qt6-im-plugins`（Qt6 输入法插件目录）

### v0.9.683 — 2026-09-08

#### 🐛 缺陷修复
- 网络路径刷新全面覆盖（不再只修"外部复制看不到"单点）：
  - 所有文件操作后的网络路径判断从 `_is_unc_path`（仅 UNC）升级为 `_is_network_path`（UNC + 映射网络驱动器），删除/重命名/新建文件夹/新建文件/粘贴（应用内+系统剪贴板）/拖放/压缩解压后，映射盘（如 `S:\`）场景同样强制重扫
  - **源窗格残留**：跨窗格拖动移动、剪切粘贴、外部拖入 Shift 强制移动后，若**源目录**是网络路径，源窗格一并强制重扫（此前只刷新目标窗格，源窗格会残留已移走的文件）
  - 超大图标（缩略图）视图在网络路径强制刷新时同步刷新（重建模型不自动触发缩略图重载）

### v0.9.682 — 2026-09-08

#### 🐛 缺陷修复
- 修复网络路径（UNC `\\server\share` 及映射网络驱动器如 `Z:\`）下看不到外部程序（其它文件管理器）复制进来的文件：
  - **根因**：QFileSystemModel 对相同路径 `setRootIndex` 直接返回缓存不重扫，且 SMB 上 QFileSystemWatcher 变更通知不可靠，手动刷新（F5）/重进目录都走相同路径导航，永远看不到外部新增文件
  - 现在：在网络路径下对**当前目录**再次导航（F5 刷新、地址栏回车、前进/后退回到原目录等）会重建共享文件模型强制重扫，外部新增/删除的文件立即可见；本地路径保持原逻辑（文件监视正常，无重建开销）
  - 新增 `_is_network_path`：识别 UNC 路径与映射网络驱动器（GetDriveTypeW = DRIVE_REMOTE），覆盖 `_is_unc_path` 不覆盖的映射盘场景

### v0.9.681 — 2026-09-08

#### 🚀 功能增强
- 设置新增「启动时显示侧边栏」两项：**显示收藏夹侧边栏**、**显示目录树侧边栏**（设置对话框 → 常规；勾选后下次启动自动打开对应侧边栏，设置保存后立即生效）

### v0.9.680 — 2026-09-08

#### 🚀 功能增强
- 标签按钮语义调整：标签栏隐藏时点击 → 显示标签栏；标签栏可见时点击 → **新建标签页**（此前为纯开关，再次点击关闭，容易与其他窗格状态混淆，出现"点哪个窗口都像只在第一个窗口建标签"的观感）
- 标签栏右键菜单新增「隐藏标签栏」；关闭全部标签页后自动隐藏标签栏

#### 🔧 工程
- `toggle_tabs`/`add_pane_tab`/PathBar 标签按钮增加 `[TABS]` 日志（含 `pane_id`），便于定位跨窗格信号路由问题

### v0.9.657 — 2026-09-05

#### 🐛 缺陷修复
- 修复 Linux 双击/右键打开文件无效（md/txt/图片等全部打不开）：
  - **根因**：PyInstaller 打包版运行时注入 `LD_LIBRARY_PATH` 指向打包目录，子进程（gedit/eog 等系统应用）加载打包的旧版 glib/gtk 库与系统版本冲突（`symbol lookup error`）后立即退出；现在启动外部应用时剔除 `LD_LIBRARY_PATH`/`LD_PRELOAD`
  - 打开顺序：用户关联 → **系统默认应用（xdg-open）** → **内置按类型候选**（gedit/gnome-text-editor/eog/evince/libreoffice/vlc 等，按常见度取第一个存在的）→ gio 兜底，不再依赖精简桌面的 xdg 关联（实测打包环境 xdg-open 返回退出码 4）
  - 子进程 stderr 落盘 `/tmp/pan4dex_open_stderr.log`，打开失败时可定位具体原因
- 修复 Windows 任务栏图标反复消失的隐患：`main.py` 函数作用域内 `os` 未绑定导致窗口图标设置失败（`local variable 'os' referenced before assignment`）
- 修复 Linux 构建版本号/编译时间错误：构建脚本在容器内强制覆盖 `VERSION`（构建现场源码可能滞后），`BUILD_TIME` 由宿主按东八区注入（容器内 `date` 为 UTC，会差 8 小时）

#### 🔧 工程
- 新增隐藏诊断入口 `--test-open <path>`：真实环境验证"用默认应用打开文件"，输出关联/候选/结果到日志，便于远程排查

### v0.9.656 — 2026-09-05

#### 🚀 功能增强
- 新增**内嵌终端面板**（视图菜单「终端面板」/ F4 开关，支持停靠**右侧或底部**，位置与可见性持久化）：
  - 真 PTY 交互式终端：Windows 走 ConPTY（pywinpty）默认 PowerShell，Linux 走标准库 pty 默认 `$SHELL`；基于 pyte 终端模拟渲染
  - 快捷键：`Ctrl+Shift+C/V` 复制/粘贴、`Ctrl+Shift+R` 重启会话；右键菜单含复制/粘贴/重启
  - 输入 `dir`/`ls` 不再出现灰色"联想参数"干扰（Windows 默认启动参数关闭 PSReadLine 内联预测）
  - 焦点进入终端时自动切换英文输入法、离开时恢复原输入法（兼容 TSF 与 IMM 输入法）
- 视图菜单新增「**更改终端程序…**」：可配置打开任意终端程序（如 `bash`、`/bin/fish` 或完整路径），**留空 = 系统默认终端**，配置持久化、改完立即重启会话

#### 🐛 缺陷修复
- 修复 Linux 终端打开即显示「进程已退出」：Linux PTY 非阻塞读，无数据返回空串被误判为进程退出，改为空读短暂等待继续读
- 修复 Windows 终端进程瞬间退出：打包补充 pywinpty 运行时文件（winpty-agent.exe / OpenConsole.exe 等）
- 修复终端**向上滚动时顶部一行重复显示、滚多远重复多少行**：pyte 0.8 历史存储"一页=一行"，行数计算误把页内字符数当行数（如 `n2573` 被拆成 5 行），重写历史缓存行数语义后无重复、顺序正确
- 修复终端历史缓存稳态洪峰时不同步（顶部丢页 + 底部加页同时发生导致内容过期），按页对象身份检测淘汰并同步缓存
- 修复长输出看不到底部与提示符（pyte 0.8.2 历史分页结构解析错误 + 滚动跟随误判）
- 修复 `dir`/`ls` 大量文件时应用长时间无响应（渲染合并 30ms、历史增量缓存、文档行数有界 2000 行）

#### 🔧 工程
- Linux 构建脚本支持 Docker 构建（`scripts/build-linux-docker.sh <版本>`，docker build 加 `--network=host` 解决容器内 DNS 失败）
- Windows 构建增加 `--collect-data=winpty` 收集终端运行时文件

### v0.9.654 — 2026-09-04

#### ⚡ 性能优化
- 启动提速约 40%（窗口显示 1.1s → 约 0.7s）：
  - 四窗格改为**首屏只创建 pane1**，pane2/3/4 在窗口显示后 250ms 延迟创建（占位替换，无布局跳动），四/双窗格切换时自动确保已创建
  - 目录树侧栏延迟到事件循环后创建（约省 220ms），首次点击切换时立即创建
  - 隐藏的窗格目录树不触发磁盘扫描（统一判断）

### v0.9.653 — 2026-09-04

#### 🚀 功能增强
- 状态栏右侧新增剪贴板操作按钮：复制 / 粘贴 / 剪切（作用于当前活动窗格）

#### 🐛 缺陷修复
- 目录树打开/跟随当前目录时，当前目录稳定显示在树可视范围**正中**，多轮修复：
  1. 展开链改为**单一推进**：父目录加载完成信号不再"从头重来"，避免与原地重试互相重置导致深层目录展开中断（此前会停在中间层级）
  2. 路径统一**正斜杠**：`os.path.dirname` 保留反斜杠导致与 `directoryLoaded` 信号路径（正斜杠）匹配不上，展开链卡死
  3. 目录树**延迟启动扫描**：树隐藏时不创建全盘扫描，只在首次显示/展开时扫描，避免四窗格 4 个模型并发扫描（含网络盘）拖慢加载
  4. 禁用视图排序（`setSortingEnabled`）：QFileSystemModel 自身按名称排序，显示顺序不变；视图排序会导致 `scrollTo` 失效/崩溃
  5. 居中滚动**轮询重试**（每 300ms × 4.5s）+ 行插入静默 800ms 后收尾居中

### v0.9.652 — 2026-09-04

#### 🚀 功能增强
- 菜单栏右侧新增「应用启动器」快捷按钮：点击直接启动配置的外部应用；设置对话框「启动器」页可添加/编辑/删除，配置持久化保存
- 设置（主题/字体/工具栏按钮/启动器）改为持久化到 QSettings，重启后自动恢复（此前仅会话内生效）

### v0.9.651 — 2026-09-04

#### 🚀 功能增强
- 「拍摄日期」列**默认隐藏**，通过列标题右键勾选「拍摄日期」显示；勾选状态保存到 QSettings，重启后保持；**四个窗格各自独立记忆列显示状态**

#### 🐛 缺陷修复
- Windows 任务栏/窗口图标加固：优先加载 `icon.ico`（ICO 原生多尺寸，任务栏提取稳定），窗口显示后再延迟重设一次图标，并直接向窗口句柄发送 `WM_SETICON`（Explorer 取任务栏图标的底层通道），三重保险根治任务栏图标偶发缺失
- 修复「拍摄日期」列勾选显示后不立即出现拍摄时间的问题：后台 prefetch 完成改用 Qt 信号跨线程通知刷新（原 QTimer.singleShot 在无事件循环的后台线程不生效），勾选显示该列时同时补一次预读
- Windows 构建改为 `--windowed`（不再带控制台黑窗），exiftool 后台调用加 `CREATE_NO_WINDOW` 静默运行，消除导航目录时终端窗口一闪而过的问题

### v0.9.650 — 2026-09-04

#### 🚀 功能增强
- 文件列表新增「拍摄日期」列（列标题右键勾选菜单中可开启）：照片读取 EXIF `DateTimeOriginal`（缺省回退 `CreateDate`）；视频读取 `CreateDate`（QuickTime mvhd.creation_time，即 exiftool 的 `QuickTime:CreateDate`），缺省回退 `DateTimeOriginal`；仅照片/视频显示，非媒体为空
- 携带 ExifTool：Windows 随身携带 `resources/tools/exiftool/exiftool.exe`（v13.59，含 Perl 运行时解压即用）；Linux 随身携带 `resources/tools/exiftool-linux/`（Perl 包 v13.59，用系统 perl 运行，不依赖目标系统预装 exiftool）
- 「关于」对话框显示携带的 ExifTool 版本号

#### 🐛 缺陷修复
- 修复「拍摄日期」列排序时崩溃：排序代理 `lessThan` 收到的是源模型索引，此前对源索引调用 `mapToSource` 造成野指针访问
- 修复拍摄日期为空时残留无效值：部分无时间戳视频的 `CreateDate` 为 `0000:00:00 00:00:00`，现过滤显示为空
- 拍摄日期改为只查缓存、由后台批量预读填充（避免浏览大目录时逐文件启动 exiftool 卡顿 UI）

### v0.9.649 — 2026-09-04

#### 🚀 功能增强
- 文件列表右键菜单（有选中项时）新增「粘贴」项：此前只有空白区域右键才有粘贴，选中文件后无法直接右键粘贴到当前目录
- 列标题右键改为「选择显示哪些列」菜单（名称/大小/类型/修改日期，可勾选/取消）：此前列标题右键误触发了窗格右键菜单（新建标签页等）

### v0.9.648 — 2026-09-04

#### 🚀 功能增强
- 目录树跟随当前目录时滚动到**上下居中**位置（`scrollTo(PositionAtCenter)`），此前只保证可见——上级目录多时当前目录会沉到视口底部甚至不可见

#### 🐛 缺陷修复
- 修复复制粘贴同名文件失败：同目录复制粘贴时目标路径等于源路径（`shutil` 抛 `SameFileError`），目标已有同名文件时也会直接覆盖。修复：复制时目标已存在则自动生成不冲突的文件名 `name (2).ext` / `name (3).ext` …（目录同理），不再失败或覆盖

### v0.9.647 — 2026-09-04

#### 🐛 缺陷修复
- 修复四窗格/多窗格下跨窗格复制粘贴失效：剪贴板此前是窗格实例属性（`self.clipboard`），在 A 窗格复制后到 B 窗格粘贴时，B 的剪贴板为空导致无反应。修复：剪贴板提升为模块级共享（`SHARED_CLIPBOARD` / `SHARED_CLIPBOARD_ACTION`），所有窗格共用一份，支持任意窗格间复制/剪切/粘贴
- 更换路径栏「打开终端」按钮图标：原用 `SP_CommandLink` 标准图标，形似「前进」箭头，容易误认。改为自绘终端图标（圆角窗口 + `>_` 提示符，`widgets/path_bar.py`），不再与前进按钮混淆

### v0.9.646 — 2026-09-04

#### 🐛 缺陷修复
- 修复 v0.9.645 统一图标后 Windows 任务栏图标再次消失的问题：窗口图标改为统一加载 `icon.png` 后，QIcon 只有单个 1024×1024 源，Windows 任务栏提取 16/32/48px 帧时需做 1024→32 的大缩放，缩放异常导致图标缺失/变默认（与 v0.9.644 修复前的现象一致）。修复：新增 `core/icon_utils.py`，从 `icon.png` 生成多尺寸 QIcon（16/24/32/48/64/128/256），`main.py` 与 `core/main_window.py` 统一使用；仍是统一图标文件 `icon.png`，但 Windows 任务栏可取到合适尺寸帧，不再做大缩放

### v0.9.645 — 2026-09-03

#### 🚀 功能增强
- 新增 `--install-menu` 命令：Linux 下一条命令即可把 Pan4dex 注册到开始菜单/应用菜单——自动把图标安装到 `~/.local/share/icons/hicolor`、生成 `.desktop` 启动器到 `~/.local/share/applications` 并刷新桌面数据库。打包版（onefile / AppImage）直接运行 `pan4dex --install-menu` 即可，无需再手动拷贝 install-linux.sh

#### 🐛 缺陷修复
- 修复 `--help` 参数未被 CLI 分发识别（此前只认 `-h`，单独传 `--help` 会误入 GUI 启动）的问题
- 修复 Linux `--install-menu` 注册后开始菜单/文件管理器仍不显示图标的根因：`~/.local/share/icons/hicolor` 缺少 `index.theme`，`gtk-update-icon-cache` 报 "No theme index file"、无法生成图标缓存，桌面环境因此找不到图标；同时安装的图标/desktop 文件被 `shutil.copy2` 保留了源文件 600 权限导致无法读取。修复：`--install-menu` 自动创建 `index.theme`（声明 256/512 尺寸目录）、图标与 desktop 统一 `chmod 644`、刷新缓存兼容 GNOME/KDE（`update-desktop-database` + `gtk-update-icon-cache` + `kbuildsycoca6`），并提示注册后注销重登或重启桌面

#### 🎨 UI/UX
- 应用图标统一与圆角化：Windows/Linux 运行时统一使用 `icon.png`（圆角），不再按平台区分 `icon.ico`/`icon.png`；`icon.png` 四角改为圆角（半径约 200px），视觉更柔和；`icon.ico` 同步重新生成多尺寸圆角版本（Windows exe 内嵌图标仍用 `.ico`，PyInstaller 平台限制，两者视觉一致）

### v0.9.644 — 2026-09-03

#### 🐛 缺陷修复
- 修复任务栏图标反复消失的问题：`MainWindow` 用单张 1024×1024 的 `icon.png` 作为窗口图标，覆盖了 `main.py` 设置的 `icon.ico`。Windows 任务栏/标题栏对窗口图标只兼容多尺寸 ICO，用大 PNG 会缩放异常甚至显示为默认/空白图标，叠加 Windows 图标缓存后表现为“反复消失”。修复：`MainWindow` 改用与 app 级一致的 `icon.ico`（含 16/24/32/48/64/128/256 七种尺寸），并给 frozen 模式的图标路径增加兜底（`_MEIPASS` 与 exe 同目录的 `resources/icons/icon.ico`）

#### 🔧 工程
- 版本号与编译时间从代码中抽离到独立配置文件 `config/app_config.py`：此前 `__version__`/`__app_name__`/`__build_time__` 硬编码在 `main.py`，构建脚本 `build_windows.py` 甚至用正则直接改写 `main.py` 注入编译时间，导致“改个版本号就得动源码、每次构建都会污染工作区”。现在 `main.py`/`core/main_window.py` 仅从 `config/app_config.py` 读取 `VERSION`/`BUILD_TIME`；改版本号只需编辑该配置文件；构建脚本改为从配置读取版本号、并把编译时间写入配置，不再改动任何源码文件。源码运行（未打包）时版本显示 `(build dev)`
- 组织名、默认窗口几何、默认主题、Qt 样式、图标文件名也统一收进 `config/app_config.py`（`ORG_NAME`/`DEFAULT_WINDOW_MIN_*`/`DEFAULT_THEME`/`APP_STYLE`/`ICON_FILE_*`），`main.py`、`core/main_window.py`、`config/theme_manager.py`、`widgets/settings_dialog.py` 均改为从配置读取，消除 `"sfncat"`、`"dark"`、`1024, 768` 等散落硬编码；图标按平台选择（Windows 用多尺寸 `icon.ico`，Linux 等平台用 `icon.png`）
- Linux 构建与图标修复：`build-linux-docker.sh` 改为从 `config/app_config.py` 读取版本号、把编译时间写入配置（不再 sed 改写 main.py），并补上 `--add-data resources:resources`（此前 Linux 构建未打包图标等资源，是 Linux 下窗口/任务栏图标不显示的根因）；`packaging/Dockerfile-linux` 补装 Qt6 运行时库（`libxcb-cursor0`、`libgtk-3-0`、`libgdk-pixbuf-2.0-0`、`libatk1.0-0`、`libglib2.0-0`），PyInstaller 将这些库收集进 onefile，目标机器无需另装；新增 `scripts/install-linux.sh` + `packaging/pan4dex.desktop`：把图标安装到 `~/.local/share/icons/hicolor`、把启动器安装到 `~/.local/share/applications`，解决 Linux 文件管理器/应用菜单中图标不显示的问题。已产出 `releases/pan4dex-0.9.644-linux`（onefile，约 69MB），xvfb 下 GUI 启动正常、图标加载无警告

### v0.9.643 — 2026-09-03

#### 🐛 缺陷修复
- 修复四窗格点列名排序全局联动的问题：四个窗格共享同一个 `QFileSystemModel`，而该模型的排序是模型级全局状态，点击任一窗格表头都会让所有窗格一起重排。修复：保持共享数据源（性能不变），为每个窗格挂独立的 `QSortFilterProxyModel` 排序代理，点哪个窗格只排哪个窗格；同时保持「目录优先」的文件管理器排序习惯（与原生行为一致：升序目录在前、名称不区分大小写）
- 修复内嵌目录树展开定时器崩溃：`PaneTreeView` 用 `QTimer.singleShot` 的 lambda 递归展开目录，控件销毁后回调仍会触发（快速导航/关闭窗口时可能崩溃）。修复：定时器改为挂在本控件下（`QTimer(self)`），控件销毁自动取消

#### 🔧 工程
- 回归测试适配 Windows 环境：布局保存测试改用 `USERPROFILE` 环境变量（`expanduser("~")` 在 Windows 取 USERPROFILE 而非 HOME）；`test_m1_core` 的路径断言改用 `os.path.normpath` 规范化，消除分隔符差异导致的误失败
- 清理 `main.py` 中大量空行：原文件 64232 行中 63885 行为空行（仅 347 行有效代码），已压缩清理为 388 行；删除所有空行后按 PEP8 恢复关键分隔空行（顶层函数间 2 空行、模块 docstring 与 import 块前后各 1 空行等）。仅移除空行与 docstring 内多余空白，代码逻辑零改动（token 级等价验证通过，`--version`/`--info` 输出一致）

### v0.9.642 — 2026-09-02

#### 🐛 缺陷修复
- 修复超大图标模式下切换窗格内标签不刷新文件列表的问题：`on_pane_tab_changed()` 和 `navigate_to()` 只更新了 tree_view，未同步更新 thumbnail_view。超大图标模式下文件列表显示在 thumbnail_view 中，导致切换标签后看到的仍是旧目录内容。修复：两个方法中均增加 `if thumbnail_view.isVisible(): load_directory(path)` 同步刷新

### v0.9.641 — 2026-09-02

#### 🐛 缺陷修复
- 修复菜单栏与内容区域之间约 25px 无用空隙的问题：根因是 `__init__` 中调用了 `create_tool_bar()`，该方法创建了一个**没有任何 action 的空 QToolBar** 并 `addToolBar()` 到主窗口，空工具栏仍占固定高度。之前多轮尝试折叠 QTabWidget 的 tabBar（setVisible/setMaximumHeight/stylesheet/自定义 CollapsibleTabBar 重写 sizeHint）均无效，因为空隙根本不是 tabBar 造成的。修复：从 `__init__` 移除 `create_tool_bar()` 调用

### v0.9.636 — 2026-09-02

#### 🚀 功能增强
- 顶层标签栏默认隐藏，可通过「视图 → 标签页栏」勾选开关显示/隐藏
- 新增自定义 `CollapsibleTabBar` 类（重写 sizeHint/minimumSizeHint 返回 0 + sizePolicy Ignored），确保标签栏隐藏时布局不留残余空间

#### 🎨 UI/UX
- 窗格内标签右键菜单新增「重命名标签页」选项
- 修复右键菜单操作目标：之前用 `currentIndex()` 导致右键点中标签 A 但操作的是当前激活标签 B，改用 `tabAt(position)` 精确定位右键点中的标签

### v0.9.634 — 2026-09-02

#### 🐛 缺陷修复
- 修复标签栏双击行为：Qt 的 `tabBarDoubleClicked` 信号只在双击标签本身时触发（index>=0），双击空白区域永远不会触发（index=-1 走不到），导致「双击空白新建标签」从未生效。pane.py 的事件过滤器则是任何双击都新建标签，不区分标签和空白
- 修复方案：给 QTabWidget 装事件过滤器（覆盖整行宽度），用 `mapFrom()` 坐标映射 + `tabAt()` 判断点击位置——在标签上则关闭标签，在空白区域则新建标签。顶层标签栏和窗格内标签栏两处统一修复
- 双击标签行为从「重命名」改为「关闭」（重命名移至右键菜单）

### v0.9.632 — 2026-09-02

#### ⚡ 性能优化
- 构建模式从 `--onefile` 切换为 `--onedir`：消除启动时 54MB 解压到临时目录的开销，启动速度提升 1-3 秒
- 排除 23 个未使用的 PyQt6 模块（QtNetwork/QtSql/QtMultimedia/QtWebEngine/QtBluetooth/QtOpenGL/QtPrintSupport 等）和 Python 标准库模块（tkinter/test/unittest），减小体积
- 产物改为文件夹 + zip 分发包：`releases/pan4dex-{version}/`（可直接运行）+ `releases/pan4dex-{version}.zip`（方便分发）

#### 🔧 工程
- `scripts/build_windows.py` 重写产物复制逻辑：onedir 模式下复制整个文件夹 + 自动打包 zip + 计算总大小
- 修复 onedir 模式下 resources 路径问题：PyInstaller 6+ onedir 把 data 文件放在 `_internal/` 子目录，但代码用 `sys._MEIPASS/resources/` 查找（指向 exe 根目录），导致图标等资源加载失败。构建脚本增加步骤：将 `_internal/resources/` 复制一份到输出根目录 `resources/`

### v0.9.631 — 2026-09-02

#### 🐛 缺陷修复
- 修复 GUI 模式下控制台窗口无法关闭的问题：`free_console_in_gui_mode()` 函数中，FreeConsole 之前的 stdout/stderr 重定向操作可能抛异常被 `except Exception: pass` 静默吞掉，导致 FreeConsole 永远执行不到。且原 stdout/stderr 文件句柄未关闭，可能阻止控制台窗口关闭
- 修复方案：FreeConsole 移到函数最前面最先执行；每步独立 try/except，一步失败不影响其他；FreeConsole 失败时回退到 `ShowWindow(SW_HIDE)` 隐藏窗口（仅新建控制台，不影响父终端）；异常写入日志文件不再静默吞掉
- stderr 重定向到 `~/.config/pan4dex/logs/pan4dex.log`，保留崩溃诊断信息

### v0.9.630 — 2026-09-02

#### 🎨 UI/UX
- 浅色主题全面扁平化 redesign（对标 Q-Dir 风格）：
  - 工具栏按钮：去掉边框和背景，hover 才显浅蓝底色（之前带边框+圆角显得笨重）
  - 树视图/列表视图：去掉 6px 圆角，改为直角；减少内边距更紧凑
  - 输入框：6px 圆角改为 2px 微圆角
  - 标签页：去掉圆角，选中标签白底+边框（与文件列表融为一体）
  - 表头：浅灰背景 + 底部边框，正常字重
  - 选中项颜色：#e8f0fe → #cfe2fc（更饱和）
  - 主窗口背景：#f8f9fa → #e8eaed（比窗格略深，营造白色卡片层次感）
  - 新增 QSplitter 分隔条样式：2px #dadce0，hover 变蓝

### v0.9.629 — 2026-09-02

#### 🎨 UI/UX
- 路径栏按钮从 Unicode 符号文字（◀▶▲▦🔄🌲📑）改为 Qt 标准图标（QStyle.StandardPixmap）：标准图标由 QStyle 绘制，自动适应深色/浅色主题，解决浅色主题下符号文字几乎看不见的问题（Unicode 符号在 Windows 上由符号字体渲染，不受 Qt 样式表 color 属性控制）
- 按钮尺寸 24×24 → 28×28，图标尺寸 16×16 → 20×20，路径输入框高度同步改为 28
- 浅色主题样式表 QToolButton 增加 `icon-size: 20px`，确保与深色主题（qdarkstyle）图标大小一致

### v0.9.625 — 2026-09-02

#### 🐛 缺陷修复
- 修复任务栏图标显示为 Windows 默认图标的问题：①未设置 Windows AppUserModelID ②Qt 未调用 `setWindowIcon()`。修复：`SetCurrentProcessExplicitAppUserModelID("com.pan4dex.app")` + `app.setWindowIcon(QIcon(icon_path))`（frozen 时从 `sys._MEIPASS/resources/icons/icon.ico` 加载）

#### ⚡ 性能优化
- Code Review 9 项性能/质量优化：
  1. `_load_visible_thumbnails()` 全量遍历 → 用 `indexAt(topLeft)` 定位首可见项，只遍历可见区域，超出底部即 break（1000 文件目录从 1000 次/轮 → ~30 次/轮）
  2. `_on_thumbnail_loaded()` 全量遍历找 item → 新增 `_item_map` 字典 O(1) 查找
  3. 移除 `load_directory()` 末尾 `QApplication.processEvents()`（防重入）
  4. `_on_thumbnail_loaded()` 加 `path.startswith(self._current_path)` 检查（防切换目录后旧缩略图设置到已回收 item）
  5. `navigate_to()` 重复 connect `directoryLoaded` lambda 但 disconnect 的是方法本身（不同对象，disconnect 永远失败，lambda 泄漏）→ 改用 `QTimer.singleShot` 重试
  6. `free_console_in_gui_mode()` stderr 重定向到 devnull → 改为重定向到日志文件（保留崩溃诊断）
  7. 缩略图视图硬编码深色样式 → 移除 `setStyleSheet`，由全局 ThemeManager 统一管理
  8. `load_directory()` 排序纯按名称 → 改为目录优先 `(not is_dir, name.lower())`
  9. main.py 有 137KB/124614 行（90% 空行）→ 压缩为 13KB/658 行

### v0.9.623 — 2026-09-02

#### 🔧 工程
- 构建环境确认：uv 虚拟环境（Python 3.13.11 + PyQt6 6.11 + PyInstaller 6.22.2 + pillow-heif 1.6.0 + qdarkstyle 3.2.3），`scripts/build_windows.py` 可直接在 venv 中运行
- 补充 `requirements.txt` 遗漏的 qdarkstyle 依赖（`config/theme_manager.py` 实际 import 但 requirements.txt 未列出，导致 venv 构建失败）

---

### v0.9.622 — 2026-09-02

#### 🐛 缺陷修复
- 修复 `--windowed` 模式 CLI 在 PowerShell 7 下完全无输出的问题：PowerShell 7 使用 ConPTY 伪控制台，GUI 子系统进程的 `AttachConsole(-1)` 永远无法附加。改为**控制台子系统构建**（`--console`），exe 启动时自动继承父控制台，`print()` 直接输出到当前终端
- GUI 模式下双击启动时自动隐藏控制台窗口：新增 `hide_console_if_standalone()`，用 `GetConsoleProcessList()` 判断控制台是否为本进程创建（双击时仅 1 个进程），是则 `ShowWindow(SW_HIDE)`；从 PowerShell/cmd 启动时保留控制台用于显示日志
- `_cli_output()` 大幅简化：移除 `AttachConsole`/`AllocConsole`/`WriteConsoleW`/`CreateFileW` 等复杂逻辑，直接 `print(output, flush=True)`

#### 🔧 工程
- `scripts/build_windows.py`：`--windowed` → `--console`
- `pan4dex.spec`：`console=False` → `console=True`
- 版本号更新为 0.9.622

### v0.9.620 — 2026-09-02

#### 🐛 缺陷修复
- 修复超大图标模式（ThumbnailView）切换后完全空白的问题：`core/pane.py` 的 `on_view_mode_changed()` 调用了 `QApplication.processEvents()` 但未 import `QApplication`，导致 xlarge 分支抛 `NameError` 被 try/except 吞掉，`load_directory()` 永远执行不到
- 修复缩略图只加载前四张的问题：`_load_visible_thumbnails()` 用 `indexAt(rect.bottomRight())` 计算可见范围末尾，IconMode+grid 下该调用经常返回 -1，导致 `end = min(-1+5, count-1) = 4`，永远只扫前 4 行。改用 `visualItemRect(item).intersects(viewport().rect())` 逐个判断可见性
- 修复缩略图加载失败时 `_loading` 集合泄漏：`ThumbnailLoader` 失败（如 HEIC 格式 Qt 不支持）时不 emit 信号，路径永远留在 `_loading` 中不再重试。新增 `failed` 信号，失败时清理 `_loading`
- 修复 `ThumbnailLoader.run()` 中 `except Exception: pass` 完全吞异常的问题，改为 `logger.debug` 记录失败原因
- 尝试修复 `--windowed` 模式 CLI 输出问题：重写 `_cli_output()` 采用 `WriteConsoleW` + `CreateFileW("CONOUT$")`，但在 PowerShell 7 (ConPTY) 下 `AttachConsole` 永远失败，最终无输出。**此方案在 v0.9.622 被控制台子系统方案取代**

#### 🚀 功能增强
- 新增 HEIC/HEIF 格式缩略图支持：Qt 默认不支持 HEIC，`ThumbnailLoader` 在 QImageReader 失败时自动回退到 Pillow + pillow-heif 解码，解码后缩放到 256px 再转 QImage
- 缩略图解码链：优先 Qt 原生 QImageReader（JPG/PNG/GIF 等）→ 失败回退 Pillow（HEIC/HEIF/AVIF）→ 两条路都失败才标记失败

#### 🔧 工程
- 新增 `pyproject.toml` 管理依赖（PyQt6, send2trash, Pillow, pillow-heif, qdarkstyle），可选构建依赖 pyinstaller
- `requirements.txt` 同步新增 pillow-heif、qdarkstyle（之前遗漏了 qdarkstyle，导致 `config/theme_manager.py` import 失败）
- 构建环境切换为 uv 虚拟环境（Python 3.13 + PyQt6 6.11 + PyInstaller 6.22），`scripts/build_windows.py` 可直接在 venv 中运行
- 新增调试脚本 `scripts/repro_issue1.py`、`repro_issue1_v2.py`、`repro_issue3.py`、`repro_loader.py`，用于复现和验证缩略图/视图切换问题

### v0.1.0 — 2026-08-26

#### 📝 文档更新
- 创建设计文档 (`docs/design.md`)
- 创建架构设计文档 (`docs/architecture.md`)
- 创建测试策略文档 (`docs/testing.md`)
- 创建开发指南 (`docs/development-guide.md`)
- 创建功能清单与规划 (`docs/feature-checklist.md`)
- 创建实现设计文档 (`docs/implementation.md`)
- 创建项目指南 (`AGENT.md`)
- 创建更新日志 (`docs/changelog.md`)

#### 🔧 工程
- 确定产品名称：**Pan4dex 万格**（Panel + 4 + Explorer）
- 项目目录从 `quad-explorer` 重命名为 `pan4dex`
- 更新所有文档中的产品名、配置目录（`~/.config/pan4dex/`）、MIME 类型（`application/x-pan4dex-drag`）
- 构建脚本发布名改为 `pan4dex-v{版本号}`

### v0.2.0 — 2026-08-26

#### 🚀 功能增强
- 完成 M1 核心框架：四窗格布局、单窗格文件浏览、路径栏、状态栏、进度条、拖拽高亮、主窗口框架
- 实现基础文件操作：新建文件夹、新建文件、重命名、删除（安全删除到回收站）
- 实现右键菜单：打开、复制、剪切、粘贴、删除、重命名、新建文件夹/文件、打开终端
- 实现多标签页：新建、关闭、切换
- 实现终端集成：自动检测可用终端（gnome-terminal/konsole/xterm）

#### 📝 文档更新
- 更新功能清单 `docs/feature-checklist.md`，第 1 章核心框架全部标记为已完成
- 新增测试文件 `tests/test_m1_core.py`，16 个测试全部通过

#### 🚀 功能增强
- 新增批量重命名功能（正则、模板、序号、大小写转换）
- 新增文件校验和（MD5/SHA256 创建与验证）
- 新增文件比较（文本 diff、二进制比较）
- 新增目录同步（双向/镜像同步）
- 新增压缩包处理（浏览/创建/解压 zip/tar）
- 新增文件分割/合并
- 新增高级搜索（文件名/内容搜索）
- 新增用户操作菜单（自定义快捷操作）

#### 📝 文档更新
- 更新功能清单 `docs/feature-checklist.md`，新增第 14-21 章工具功能
- 更新设计文档 `docs/design.md`，里程碑从 M5 扩展到 M7

### v0.3.0 — 2026-08-26

#### 🚀 功能增强
- 完成 M3：快速预览面板 + 文件打开配置
- 新增快速预览面板（文本/图片/文件信息显示）
- 新增文件类型-应用映射配置（JSON 持久化）
- 新增文件打开行为（关联应用 → xdg-open 回退）
- 新增选择变化自动更新预览

#### 📝 文档更新
- 更新功能清单，第 5-6 章标记为已完成
- 新增测试文件 `tests/test_m3_preview.py`，18 个测试全部通过

### v0.4.0 — 2026-08-26

#### 🚀 功能增强
- 完成 M4：主题系统 + 收藏夹 + 筛选
- 新增主题管理器（深色/浅色主题热切换、自定义主题 JSON 接口）
- 新增收藏夹侧边栏（添加/移除/编辑/导入导出）
- 新增筛选栏（文件名/扩展名/正则表达式筛选）
- 新增 Ctrl+B 切换收藏夹侧边栏

#### 📝 文档更新
- 更新功能清单，第 8 章（收藏夹）和第 11 章（主题系统）标记为已完成
- 新增测试文件 `tests/test_m4_theme.py`，23 个测试全部通过

### v0.5.0 — 2026-08-26

#### 🚀 功能增强
- 完成 M5：批量重命名 + 校验和 + 文件比较
- 新增批量重命名工具（模板/正则/大小写转换/实时预览）
- 新增校验和工具（MD5/SHA1/SHA256/SHA512 创建与验证）
- 新增文件比较工具（文本 diff 对比、差异高亮）
- 新增工具菜单集成（批量重命名/校验和/文件比较）

#### 📝 文档更新
- 更新功能清单，第 14-16 章标记为已完成
- 新增测试文件 `tests/test_m5_tools.py`，14 个测试全部通过

### v0.6.0 — 2026-08-26

#### 🚀 功能增强
- 完成 M6：目录同步 + 压缩包 + 文件分割 + 高级搜索
- 新增目录同步工具（双向/镜像同步、差异对比）
- 新增压缩包处理（ZIP/TAR.GZ/TAR.BZ2 创建与解压）
- 新增文件分割/合并工具（按大小/数量分割）
- 新增高级搜索工具（文件名/内容/大小/类型筛选）

#### 📝 文档更新
- 更新功能清单，第 17-20 章标记为已完成
- 新增测试文件 `tests/test_m6_tools.py`，9 个测试全部通过

### v0.7.0 — 2026-08-26

#### 🔧 工程
- M7 完成：打包配置和项目收尾
- 创建 PyInstaller spec 文件 `packaging/pan4dex.spec`
- 创建 `requirements.txt` 运行时依赖文件
- 全部 101 个测试通过 ✅

#### 📝 文档更新
- 更新功能清单，所有 P0/P1/P2 功能标记为已完成
- 更新日志记录 M6/M7 完成

### v0.8.1 — 2026-08-28

#### 🐛 缺陷修复
- 修复关于对话框版本号硬编码问题，改为动态读取 `__version__`
- 添加编译时间显示（`__build_time__`），构建时自动注入

#### 🔧 工程
- 更新构建脚本 `build.sh`/`build.bat`，打包前自动注入编译时间

### v0.8.0 — 2026-08-26

#### 🚀 功能增强
- 新增目录树侧边栏（Q-DIR 风格）
- 支持展开/折叠所有节点
- 支持自动展开开关控制
- 点击目录树节点自动导航到对应目录
- 快捷键 Ctrl+Shift+T 切换目录树

#### 📝 文档更新
- 更新功能清单，新增第 22 章目录树功能
- 更新日志记录 v0.8.0 发布

### v0.9.4 — 2026-08-29

#### 🚀 功能增强
- 新增窗格内标签页功能：每个窗格底部可显示标签页栏，独立管理多个路径
- 路径栏新增标签页按钮（📑），点击切换本窗格标签页栏显示/隐藏
- 右键菜单新增「新建标签页」选项
- 标签页支持切换、关闭，点击标签页自动导航到对应路径

#### 🎨 UI/UX
- 标签页栏位于窗格底部，高度 30px，默认隐藏
- 标签页按钮在路径栏中，与目录树按钮并列

#### 📝 文档更新
- 更新功能清单，新增 22.7（窗格内标签页）、22.8（标签页按钮）
- 更新日志记录 v0.9.4 发布

#### 🐛 缺陷修复
- 修复界面布局问题：将 QSplitter 改为 QHBoxLayout，目录树隐藏后不再留空白
- 目录树默认隐藏，界面更简洁

#### 📝 文档更新
- 更新日志记录 v0.9.3 发布

#### 🚀 功能增强
- 内嵌目录树默认隐藏，需要时点击路径栏 🌲 按钮打开

#### 📝 文档更新
- 更新日志记录 v0.9.2 发布

#### 🚀 功能增强
- 新增每窗格独立目录树（PaneTreeView），每个窗格左侧内嵌独立目录树
- 路径栏新增目录树按钮（🌲），点击切换本窗格目录树显示/隐藏
- 每个窗格的目录树独立控制，互不影响

#### 🎨 UI/UX
- 窗格内部采用水平分割器（QSplitter），左侧目录树 + 右侧文件列表
- 目录树与文件列表比例 1:3，可拖拽调整
- 内嵌目录树样式与侧边栏统一（深色主题）
- 目录树按钮在路径栏中，与后退/前进/上级/刷新按钮并列

#### 📝 文档更新
- 更新功能清单，新增 22.5（每窗格独立目录树）、22.6（目录树按钮）
- 更新日志记录 v0.9.1 发布

---

## 发布规则

### 版本号规则
- 主版本号.次版本号.修订号
- 例：`v0.1.0`（初始）、`v1.0.0`（正式版）

### 发布目录
- 发布文件存放于 `releases/` 目录
- 命名规则：`pan4dex-v{版本号}`
- 示例：`releases/pan4dex-v0.1.0`

### 发布流程
1. 确保所有测试通过
2. 更新 `docs/changelog.md` 记录本次变更
3. 更新版本号（如 `main.py` 中的版本常量）
4. 使用 `packaging/build.sh` 构建
5. 将构建产物复制到 `releases/pan4dex-v{版本号}`
6. 验证发布版本可正常运行
7. 提交代码并打 tag

---

**文档版本**：v1.0  
**最后更新**：2026-08-26
