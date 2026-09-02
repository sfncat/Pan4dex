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
