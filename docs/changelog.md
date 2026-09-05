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
