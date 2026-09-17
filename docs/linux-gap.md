# Pan4dex 万格 — Linux 能力对照与差距

> 背景：本仓最初就是 **Linux 版**（`docs/design.md` 第一行：「Pan4dex 万格 Linux 版」，为
> Ubuntu/Kali 写，后来才对齐 Windows 的 Q-Dir）。本文回答一个问题：**现在这些能力在
> Linux 上还剩下多少，哪些是真的没做、哪些只是没验证。**

**生成**：2026-09-16，分支 `dev/shell-behavior-smb-perf`，版本 v1.9.012

---

## 0. 结论摘要

1. **功能代码层面 Linux 并不落后**：平台分支一共 67 处，分布在 14 个源码文件
   （`main.py` + `core/`、`widgets/`、`config/`），Linux 侧基本都有对应实现，
   而且好几处比 Windows 做得更细（真 PTY、AppImage、`LD_LIBRARY_PATH` 清洗、
   `.desktop` 枚举、`xdg-open → 内置候选 → gio` 三级兜底）。**没有发现「Linux 一启动就崩」级别的死路。**
2. **真正断掉的是发布链路**：`scripts/build-linux-docker.sh` 需要的 4 个 `--add-data`
   源目录在仓库里根本不存在（其中一个被 `.gitignore` 挡住），PyInstaller 对缺失的
   add-data 源是**硬失败**（当场实测 `exit 1`）→ 新克隆的仓库构建不出 Linux 包。
   `releases/` 里也没有任何 Linux 产物，最后一次 Linux 构建工作停在 v0.9.68x（≈50 个版本前）。
3. **本机的测试证据大部分还是 Windows 的**：569 项用例在 Windows 上跑。v1.9.013 之后，
   POSIX 的「慢位置」判定矩阵已经能在 Windows 主机上测满（判据是纯函数，喂挂载表
   文本进去）；仍未执行过的 Linux 分支：`_list_linux`、pty 后端、`same_volume` 的
   挂载点边界 —— `tests/test_open_with.py:33-35` 按**宿主平台**挑要替换的枚举函数。
4. ~~**两处「Windows 特化判据」把 Linux 挡在功能外面**~~ → **v1.9.013 已修**：
   网络/慢盘判定（`os.name != 'nt'` 直接 `return False`）与删除后果文案（只有 nt 分支
   区分网络位置）现在两端都算，判据收拢到 `core/mounts.py` 一份。这次修完真正生效的是：
   gvfs / CIFS 挂载上**不挂 watcher**、**重复导航同一目录强制重扫**、导航时不拿
   同步 `stat` 猜目录、删除前说「这里没有回收站」（缓存 TTL 2s 本来就是两端同一条
   规则，不在这次的范围内）。
5. **三项在 Linux 上缺得更狠的功能，两端其实都没做**：文件类型图标
   （`dir_model._icon()` 永远只有「文件夹/文件」两张图）、POSIX 权限与所有者
   （右键「加运行权限」执行后**界面上看不到任何变化**，代码注释里承诺的「权限列」从来没有）、
   挂载点/网络位置入口（plan §7 的「此电脑」欠账）。
6. 语义不对等的一处：「在系统文件管理器中显示」Windows 是 `explorer /select,` **选中那一个文件**，
   Linux 是 `xdg-open 父目录`——只打开、不选中。

---

## 1. 取证方法与置信度

**边界（重要）**：本次分析在 Windows 11 主机上做，**没有任何 Linux 运行时**——
`docker` 未安装、`wsl` 无发行版、文档里的 Linux 目标机 `gti (192.168.5.58)` ping 不通。
所以下面每条结论标三种来源之一：

| 标记 | 含义 |
|---|---|
| ✅ 实测 | 本会话当场跑出来的（只有 4 条，见下表） |
| 📖 代码 | 读到的分支确实如此（可复核到行号） |
| ❓ 待真机 | 只能推断，必须在 Linux 上跑一遍才算数 |

| 实测项 | 结果 |
|---|---|
| PyInstaller 6.22 遇到不存在的 `--add-data` 源 | `ERROR: Unable to find ...`，**exit 1**（不是警告） |
| PyInstaller 6.22 遇到不存在的 `--icon` | `FileNotFoundError: Icon input file ... not found`，exit 1 |
| `pyinstaller packaging/pan4dex.spec`（在仓库根目录） | **exit 0，产物 54.6MB**：spec 仍能跑，且自动带上 QtSvg/imageformats/pillow_heif |
| 全量测试（Windows，v1.9.012 基线） | 476 passed / 1 skipped（随机序与固定序两轮一致）；v1.9.013 起为 **569 passed / 1 skipped**，两轮同样一致 |

「代码取证」的判定标准：一个功能只有走到 `sys.platform == "win32"` 的分支里才算 Windows 专属；
如果 Linux 分支存在但没跑过，一律记 🟡/❓ 而不是 🟢。

---

## 2. 能力对照表

图例：🟢 两端一致且可信 | 🟡 Linux 有实现但降级/未验证 | 🔴 Linux 缺失 | ⚠️ 判据把 Linux 挡在外面

### 2.1 启动与桌面集成

| 能力 | Windows 现状 | Linux 现状 | 判定 | 证据 |
|---|---|---|---|---|
| 启动、四窗格、主题、快捷键 | 正常 | 同一套代码 | 🟡 offscreen 真机已跑通（v1.9.014：全量 572 passed、`main.py` 能起），**桌面会话待 L12** | 全仓平台分支不影响这些路径；§5.1 |
| 崩溃日志 / faulthandler | 有（+ MessageBoxW 弹窗） | 有（写 `~/.config/pan4dex/logs`） | 🟢 | `main.py:24-50`、`main.py:100-190` |
| 释放控制台 | `FreeConsole()` | 直接 return（本来就无台） | 🟢 | `main.py:369-382` |
| 应用菜单注册 | 不适用 | `--install-menu` + `scripts/install-linux.sh` 两条路 | 🟡 未真机 | `main.py:265-366` |
| 任务栏分组 / 图标归属 | `AppUserModelID` | `.desktop` 写 `StartupWMClass=pan4dex`，但 `setApplicationName("Pan4dex")` 决定的 WM_CLASS 是 `Pan4dex`，且**从未调 `setDesktopFileName`** | ❓ 待真机 | `main.py:344`、`main.py:523`、`packaging/pan4dex.desktop` |
| 原生图标兜底 | `WM_SETICON` | 同一个函数在 Linux 抛异常被 `except` 吞掉 → 每次启动 2 条 `Native icon apply failed` warning | ⚠️ 小坑（该加平台守卫） | `main.py:64-97`、`main.py:533-600` |
| 中文输入 | — | 启动时探测 fcitx5/ibus 设 `QT_IM_MODULE`；但 **Qt6 wheel 不带输入法插件**，需外部提供 `platforminputcontexts` 插件 | 🟡 依赖打包 | `main.py:511-520`、`scripts/build-linux-docker.sh:59-62` |
| 默认字体 | `Microsoft YaHei UI`（仅 win32 设置） | 走系统默认 + QSS 的 `sans-serif` 兜底 | 🟢 | `main.py:566-572`、`config/theme_manager.py:93` |
| 应用启动器默认项 | 记事本/计算器/资源管理器 | **空列表**，用户自配 | 🟡 有意为之 | `config/app_config.py:37-45` |

### 2.2 浏览与显示

| 能力 | Windows | Linux | 判定 | 证据 |
|---|---|---|---|---|
| 目录枚举、排序、筛选 | `os.scandir` + 后台池 | 同一套 | 🟢 | `core/dir_model.py` |
| 隐藏文件判定 | `.` 前缀 + `FILE_ATTRIBUTE_HIDDEN` | `.` 前缀（属性分支在 nt 才走） | 🟢 | `core/dir_model.py:169-181` |
| **文件类型图标** | 只有「文件夹/文件」两张 QStyle 图 | 同样只有两张：可执行文件无齿轮、符号链接无箭头、png/py/zip 无区分 | 🔴 两端都缺，**Linux 观感损失更大** | `core/dir_model.py:984-993` |
| 图片缩略图 | Qt `QImageReader` + Pillow | 同一套 | 🟢 | `widgets/thumbnail_view.py:74-` |
| HEIC/HEIF 预览 | 打包带 `_pillow_heif` | 代码有，但 **Docker 构建镜像的 pip 列表里没有 `pillow-heif`**；缺了只记一条 debug 日志 | 🟡 静默降级 | `widgets/thumbnail_view.py:24-37`、`packaging/Dockerfile-linux` |
| 类型列文案 | 「PNG 文件」「文件夹」（不是 shell 描述） | 相同 | 🟢 一致但都弱 | `core/dir_model.py:966-972` |
| 符号链接识别 | `islink` + 重分析点 | `os.path.islink`（非 nt 直接用它） | 🟢 | `core/file_operations.py:353-363` |
| 拍摄日期列 | 系统/内置 exiftool | `resources/tools/exiftool-linux/`（**未入库**）或系统 exiftool | 🟡 | `core/media_metadata.py:36-98` |
| **POSIX 权限 / 所有者显示** | 概念不适用 | **完全没有**；「加运行权限」的注释写着「让权限列立即更新」，但列表只有 5 列、没有权限列 | 🔴 | `core/pane.py:1247-1258`、`core/dir_model.py:37` |
| 属性对话框 | 未做 | 未做（Linux 更需要：权限/所有者/符号链接目标） | 🔴 plan §7 欠账 | — |

### 2.3 导航

| 能力 | Windows | Linux | 判定 | 证据 |
|---|---|---|---|---|
| 收藏夹默认项 | `~\Desktop`/`Downloads`/`Documents` 真实存在 | ✅ v1.9.013：读 `~/.config/user-dirs.dirs`（本地化桌面是 `~/桌面`、`~/下载`），读不到退英文名，并且只留真实存在的目录 | 🟢 已修 | `config/bookmarks.py` `parse_user_dirs` / `default_links` |
| 「此电脑」/挂载点/网络邻居 | 未做 | 未做（Linux 侧需 mount 表 / `QStorageInfo`，不是盘符） | 🔴 plan §7 欠账 | 全仓无 `QStorageInfo` |
| 面包屑地址栏 | 未做 | 未做 | 🔴 plan §7 欠账 | — |
| 路径补全 | 当前目录一层 | 同（`QDir` + `/`） | 🟢 | `widgets/path_bar.py:214-245` |
| 在系统文件管理器中显示 | `explorer /select,` **选中该文件** | `xdg-open 父目录`：只打开不选中，语义不对等（KDE 有 `dolphin --select`，GNOME 有 `nautilus --select`） | 🟡 | `core/pane.py:1854-1865`、`widgets/advanced_search.py:761-767` |
| 在终端中打开 | `wt`/`pwsh`/`cmd` | `xdg-mime query default x-scheme-handler/terminal` + 12 个候选终端扫描 | 🟢 反而更全 | `core/pane.py:2488-2535` |

### 2.4 文件操作

| 能力 | Windows | Linux | 判定 | 证据 |
|---|---|---|---|---|
| 复制/移动/删除/重命名/新建 | 🟢 | 同一套 `FileOperations` | 🟢 | `core/file_operations.py` |
| 拖放默认动作（同卷移动/跨卷复制） | 🟢 v1.9.012 | 判据跨平台（`st_dev` 在 Linux 就是设备号，挂载点边界天然正确；UNC 排除只影响 Windows） | 🟢 | `same_volume()` / `decide_drop_action()` |
| 同名冲突 | `os.path.exists` | 同一判据 → Linux 上 `A.txt` 与 `a.txt` 正确视为两个文件（没有 Windows 化的大小写折叠） | 🟢 | 全仓无对路径做 `lower()` 比较 |
| 符号链接复制 | 建链失败降级为复制（需开发者模式） | `os.symlink` 正常 | 🟢 | `core/file_operations.py:399-410` |
| 回收站 | `send2trash` + `\\?\` 前缀修正 | `send2trash(path)`（freedesktop Trash） | 🟢 | `core/file_operations.py:761-792` |
| 删除后果文案 | 区分「本地→回收站 / 网络→永久不可恢复」 | ✅ v1.9.013：同一个分类不分平台，gvfs/CIFS 上不再承诺“移到回收站” | 🟢 已修 | `describe_removal()` + `core/mounts.py` |
| **慢盘/网络盘识别** | UNC + `GetDriveTypeW==DRIVE_REMOTE` | ✅ v1.9.013：解析 `/proc/mounts`（macOS `mount -p`）按最长前缀找挂载点 + 慢类型表（cifs/smb/nfs/任意 `fuse.*`（含 gvfs）/sshfs/rclone/9p/虚拟机共享盘…）→ 不挂 watcher、导航强扫、删除文案一次接通 | 🟢 代码与纯函数矩阵已验，❓ 真机挂载待跑 | `core/mounts.py`（两个消费方：`_is_network_path` / `DirStoreModel._is_network`）|
| 跨线程进度/取消 | `FileOpRunner` | 同一套 | 🟢 | `core/file_op_runner.py` |
| 撤销（Ctrl+Z） | 未做 | 未做 | 🔴 plan §2.3 明示留二期 | — |

### 2.5 搜索与工具集

| 能力 | Windows | Linux | 判定 | 证据 |
|---|---|---|---|---|
| 高级搜索（名/内容/大小/日期） | `os.walk` | 同一套；但**搜根目录会把 `/proc`、`/sys`、`/dev` 扫进去**（无跨设备开关、无排除表） | ❓ 待真机 | `widgets/advanced_search.py:87` |
| 搜索结果批量操作 | 🟢 v1.9.011 | 共用 `FileOpRunner` | 🟢 | `widgets/advanced_search.py` |
| 压缩/解压（7z 后端） | 系统 7-Zip → 内置 `resources/tools/7z/7z.exe` | 系统 `7z/7za/7zz/7zr` → 内置 `7zz`（**未入库**）→ 都没有则功能不可用 | 🟡 | `core/archive_ops.py:48-113` |
| 校验和 / 批量改名 / 文件比较 / 目录同步 / 分割合并 / 时间戳 | 纯 Python | 平台无关 | 🟢 | `widgets/*.py`（这些文件里平台分支数 = 0） |
| 内嵌终端 | `pywinpty`（winpty 层，历史上脆弱） | `pty` + `fcntl` + `termios` 真 PTY；zsh 补齐噪声用临时 `ZDOTDIR` 关掉 | 🟢 **Linux 路径更正** | `widgets/terminal_panel.py:143-245,341-362` |
| 终端内自动切英文输入法 | IMM/TSF 双路径 | 无（IBus/fcitx 不管） | 🟡 可接受降级 | `widgets/terminal_panel.py:37-127,684-707` |
| 右键「打开方式」列表 | 注册表 ProgID / OpenWithList MRU | `freedesktop .desktop` 解析 + mime 匹配 + Exec 字段码剥离；内置兜底改为**与 Windows 共用一道门**（v1.9.014） | 🟡 枚举逻辑真机已测满（`test_open_with` 23 passed），界面里的观感仍待 L5 | `core/open_with.py`（`needs_builtin_topup()` / `_list_linux`）|
| 系统「打开方式」对话框 | `ShellExecute` 系统对话框 | 无对应 API，只能用自研列表 | 🟡 设计如此 | `core/open_with.py:114-121` |
| 「设为默认应用」 | 只写我们自己的 `associations.json` | 同（不碰 `xdg-mime default`） | 🟢 两端一致 | `core/pane.py:1155-1200` |

### 2.6 只有 Linux 有、Windows 没有的能力

这些是「软件一开始是给 Linux 写的」留下的痕迹，都是**踩过真机才会写出来的代码**：

- 双击可执行文件（有 `X_OK` 位）**直接运行**而不是交给 `xdg-open`；AppImage 认 magic
  bytes（`AI\x01`/`AI\x02`）并在无执行权限时自动 `chmod +x`（`core/pane.py:1053-1060,1205-1245`）
- `_clean_child_env()` 剔掉 PyInstaller 注入的 `LD_LIBRARY_PATH`/`LD_PRELOAD`，
  否则子进程（gedit/eog）会用打包目录里的旧 glib/gtk，表现为 `symbol lookup error` 后 127 退出
  （`config/file_associations.py:16-28`，`Pane.open_file` 的兜底路径也用了它）
- `xdg-open` 会等默认应用就绪才返回（LibreOffice >10s）→ 「短观察：仍存活即算成功」
  （`config/file_associations.py:293-315`）
- 44 个扩展名的 Linux 候选应用表（gedit/gnome-text-editor/mousepad/leafpad/xed/kate…），
  不依赖桌面集成（`config/file_associations.py:33-80`）
- `--install-menu` 会先补 `hicolor/index.theme`——没有它 `gtk-update-icon-cache` 报
  "No theme index file"、桌面环境找不到图标（`main.py:283-306`）
- Linux 的 zsh 补齐预测文本用临时 `ZDOTDIR` 包一层关掉（`widgets/terminal_panel.py:348-362`）

---

## 3. 阻断项：Linux 的构建与发布链路今天跑不通

| # | 问题 | 后果 | 证据 |
|---|---|---|---|
| 3.1 | `scripts/build-linux-docker.sh` 要求 4 个 `--add-data` 源：`resources/themes`、`resources/tools/exiftool-linux`、`resources/tools/7z`、`resources/tools/qt6-im-plugins` | **全部不在仓库**（`resources/` 只有 `icons/`；`/resources/tools/` 被 `.gitignore:57` 排除；`resources/themes` 连代码都不读它）→ PyInstaller 对缺失源是 `ERROR ... exit 1` → 新克隆必失败 | ✅ 实测缺失即硬失败 + `git ls-files resources` |
| 3.2 | `packaging/Dockerfile-linux` 的 pip 列表：`PyInstaller send2trash Pillow qdarkstyle cairosvg pyte` | **缺 `pillow-heif`**（→ HEIC 静默不可用，只记一条 debug 日志）；`cairosvg` 是早年遗留项（全仓没有任何地方引用它，也没有 SVG→PNG 的调用） | 📖 与 `pyproject.toml` 依赖表逐项对 + `rg cairosvg` |
| 3.3 | 镜像是 `python:3.10-bullseye`，而 `pyproject.toml` 写 `requires-python = ">=3.11"`、`.python-version` 是 3.13 | 自相矛盾：要么构建环境低于声明下限，要么声明是虚的（静态扫过：没有 3.11+ 专属 API，理论上能跑） | 📖 + ❓ |
| 3.4 | `scripts/build.sh` 仍被 `AGENT.md:131-132` 列为 Linux 构建入口 | 它取版本靠 `main.py` 的 `__version__`、注 `__build_time__` 也改 `main.py`（两者早已搬到 `config/app_config.py`）→ 版本退化成 `v0.0.0-dev`、编译时间为空；且 `pyinstaller ... main.py` 不带任何 `--add-data`（图标进不去）；产物名带 `v` 前缀，`install-linux.sh` 按 `pan4dex-<VERSION>-linux`（无前缀）去找 → 找不到 | 📖 `scripts/build.sh:39,76-79,44` vs `scripts/install-linux.sh:19-20`（`docker/README.md:139` 已标注该脚本废弃，但 AGENT.md 没同步） |
| 3.5 | Linux 构建入口实际有**三条并存**：`build-linux-docker.sh`（canonical）、`packaging/pan4dex.spec`（README:132 与 `docs/development-guide.md:198` 推荐）、`scripts/build.sh`（AGENT.md 推荐，已废弃） | spec 路线今天确实能跑（✅ 实测 exit 0，还自动收了 QtSvg/imageformats/pillow_heif），但它不带 `resources/tools/*` 与输入法插件，产物能力面与 docker 路线不同；README:136 那行（Windows）**`--icon=resources/icons/pan4dex.ico` 指向不存在的文件**（现在叫 `resources/icons/icon.ico`），而缺 icon 在 PyInstaller 6 是 `FileNotFoundError` 硬失败 | ✅ + 📖 |
| 3.6 | `releases/` 无任何 Linux 产物；最后一次 Linux 构建工作记在 v0.9.644–v0.9.684 | 从 0.9.68x 到 1.9.012 约 50 个版本的改动**从没进过 Linux 包**，Linux 现状只能靠读代码判断 | 📖 `git log -- docker/ packaging/ scripts/*linux*` + changelog |

---

## 4. 测试覆盖的平台偏斜

| 事实 | 数字 | 影响 |
|---|---|---|
| 在 Linux 上会被 `skipif` 跳过的用例 | 6 项（回收站文案 2、注册表 2、Windows 命令行规则 1、Windows `Preferred DropEffect` 1） | 这些本来就是 Windows 专属，合理 |
| 在 Windows 上被跳过的 Linux 专属用例 | 3 项（v1.9.014 新增） | Windows 开 **575 passed / 3 skipped**，Linux 开 **572 / 6**，总数 578 吻合 —— 但这三项用例在 Windows 上**从未执行过**，只能在真机上算测到 |
| `core/open_with.py` 的 Linux 枚举 `_list_linux` | ✅ v1.9.014 起在 linux230 真机上测满（`test_open_with` 23 passed），并在真机上抓出它与 Windows 不一致的兜底门控 | 真实桌面环境里的目录优先级、`Exec` 里的 `%f/%U`、mime-info 缓存路径都验过了；剩下的是界面里的观感（L5） |
| `PtyBackend` 的 Linux 分支（`pty`/`fcntl`/`termios`） | 本机 0 次（Windows 走 winpty）；真机上 `test_terminal_lifecycle` 13 passed | 终端在 Linux 上“代码看着最正”已有自动化证据，但 vim/htop 这类全屏程序的实测仍在 L6 |
| `same_volume()` 的正向跨挂载点判定 | ✅ v1.9.014：真机（两个 CIFS 挂载 + 一堆系统挂载）上 `test_m2_file_operations` 38 passed；用例不再写死 `E:\` | 拖放动作决策在 Linux 上的正确性不再靠推断；真挂载上的耗时仍在 L2/L4 |
| 「慢位置」判定的 Linux 矩阵 | ✅ v1.9.013 起在 Windows 主机上测满（`tests/test_mounts.py`，82 项：喂真实 `/proc/mounts` 文本验解析/匹配/类型三段） | 这类判据拆成纯函数后，“Linux 专属”不等于“必须 Linux 才能测”；剩下要真机的只有「挂载表本身长什么样」 |

---

## 5. 需要 Linux 真机才能定论的问题（验收清单）

### 5.1 一条命令先摸底盘 —— ✅ v1.9.014 已在真机跑完（linux230 / Ubuntu 24.04）

```bash
# 仓库根目录
python3 -m venv .venv && .venv/bin/pip install -e . pytest pytest-qt pytest-randomly \
    pillow-heif    # ← 后两个 pyproject 里有，但 Docker 镜像缺，先补齐再测
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --tb=short 2>&1 | tail -30
```

**实测结果**（宿主 `~/venv-pan4dex`，发布用的 PyQt 6.9.1 / Qt 6.9.2）：单进程全量
**572 passed / 6 skipped**，定序 1 次 + 随机序 3 次全部 exit 0（与 Windows 的
575+3 总数相等，差异全是 `skipif` 的平台门控）。`python main.py` 在 offscreen 下
能起，日志里 `延迟创建 pane2-4: 476.3ms` 正常完成。

第一轮摸上来的 6 个失败已全部定性（4 条是用例写死了 Windows 假设、1 条是
`_list_linux` 的内置兜底与 Windows 不一致、1 条是测试替身不完整），另有一条
`test_m4_theme` 段错误被证实是**用例之间泄漏 app 级 stylesheet** 造成的（非产品缺陷，
见 `docs/gotchas.md` 第 44 条）。单跑该模块仍有 1-3/12 的残余崩率（整场跑不复现），
继续观察。

要记的永远不止红/跳：红的那些**是不是产品错**，只有真机能回答（本轮 6 条里只有 1 条是）。

### 5.2 手工 GUI 验收（按风险从高到低）

| # | 验什么 | 判定标准 |
|---|---|---|
| L1 | 能不能构建出来 | 先手工建 `resources/{themes,tools/exiftool-linux,tools/7z,tools/qt6-im-plugins}` 或改脚本为「存在才带」，`build-linux-docker.sh` 走完 |
| L2 | 挂 SMB（gvfs 或 CIFS）后浏览 | 打开 1 万个条目的共享目录：不闪、能取消、切走窗格不继续扫；**当前必然表现为按本地目录处理**（§2.4 ⚠️） |
| L3 | 回收站 | 本地删除进 Trash；gvfs 上删除的**文案**是否骗人（说「移到回收站」实则失败） |
| L4 | 拖放 | 从 Nautilus/Dolphin 拖入：同分区应移动、跨分区应复制；源端不允许 move 时不得删源 |
| L5 | 打开方式 | 右键 → 打开方式：候选列表是否来自 `.desktop`、mime 匹配是否正确、`%f/%U` 是否被剥掉 |
| L6 | 内嵌终端 | `$SHELL`、vim/htop 全屏程序、resize、关闭窗口后 shell 是否真退 |
| L7 | 图标与缩略图 | 确认「所有文件同图标」的实际观感；SVG/PNG/HEIC 缩略图是否出得来（qsvg 插件、pillow-heif） |
| L8 | 桌面集成 | `--install-menu` 后应用菜单出现图标；GNOME 任务栏分组/窗口图标是否正确（WM_CLASS 那条） |
| L9 | 全盘搜索 | 搜 `/` 或 `/home`：`/proc`、`/sys` 是否被扫、耗时、能否中途取消 |
| L10 | 权限 | 右键「加运行权限」后从界面能否看出生效了（现在看不出，因为没有权限列） |
| L11 | 中文输入 | 地址栏/重命名/搜索框里能否打中文（依赖 ibus/fcitx5 插件是否进包） |
| L12 | Wayland vs X11 | 两种会话下都跑一遍：高 DPI、拖拽、`QT_QPA_PLATFORM` 自动选择 |
| L13 | 大目录内存/CPU | 10 万条目目录（Linux 上 ext4/xfs 很常见）下列表与排序 |
| L14 | 无桌面环境（纯 TTY/SSH） | 明确「不支持」还是能起（offscreen） |
| L15 | 单实例 / 多开 | Linux 上从终端起两次会怎样（两端都没做锁，记录事实即可） |

---

## 6. 建议的修复顺序

### 第一批：让 Linux 重新可交付（不碰功能代码）

1. **`build-linux-docker.sh` 的 `--add-data` 改为「目录存在才带」**（`[ -d ... ] && ARGS="$ARGS --add-data ..."`），
   并把 `resources/themes` 这条彻底删掉（代码里没有人读它）；缺 `exiftool-linux`/`7z` 时
   打印「本包不含 X，功能依赖系统安装」而不是构建失败。
2. **Dockerfile 补 `pillow-heif`、删 `cairosvg`**；明确 Python 版本（要么镜像升 3.11+，
   要么 `requires-python` 降回 3.10 —— 二选一，别一边写 3.13 一边构建 3.10）。
3. **Linux 构建入口收敛成一条**：`build-linux-docker.sh`；`AGENT.md` 的 build.sh 行改掉，
   README 与 `docs/development-guide.md` 的 `pyinstaller packaging/pan4dex.spec` 要么删要么标注
   为「手动/降级路线，不含 tools 资源」；顺带修 README 里不存在的 `--icon=resources/icons/pan4dex.ico`。
4. `apply_windows_native_icon()` 加 `sys.platform == "win32"` 守卫（现在是靠异常吞掉，
   每次启动白抛两次并留 warning 日志）。

### 第二批：把 Windows 特化判据改成真正的跨平台判据 —— ✅ v1.9.013 已完成

5. ✅ `_is_network_path()` / `DirStoreModel._is_network()` 在 POSIX 上补了判据：解析
   挂载表按最长前缀找挂载点，慢类型（cifs/smb/nfs/`fuse.*` 含 gvfs/sshfs/9p/…）
   一律算远端 → 一次性接通不挂 watcher、导航强扫、删除文案。**这是头号目标的 Linux 半边。**
6. ✅ `describe_removal()` 的网络分支去 `os.name == 'nt'` 化（与第 5 条共用同一个判据）。
7. ✅ 收藏夹默认项改读 XDG：`~/.config/user-dirs.dirs` 的 `XDG_DESKTOP_DIR` 等，读不到
   再退 `~/Desktop`，并且只留真实存在的目录（Windows 不读该文件，行为不变）。

这一批未做的：真机挂载表本身（L2/L3）。“不做 `realpath`”是写下来的取舍：
经由符号链接访问的挂载点会被判成本地（见 `docs/gotchas.md` 第 43 条）。

### 第三批：补「两端都缺、Linux 更疼」的显示能力

8. **一份 `QFileIconProvider` 覆盖两端图标**（Windows 得到 shell 类型图标，Linux 得到
   freedesktop mime 图标），再叠两个自绘角标：符号链接、可执行位；顺手用
   `provider.icon(IconType.Computer/DiskDrive)` 解决 plan §7 的「此电脑/挂载点」树根。
9. **属性对话框**（plan §7）里带上 POSIX 权限/所有者，兑现 `_chmod_add_exec` 注释里承诺的「权限列」。
10. 「在系统文件管理器中显示」按桌面环境试 `dolphin --select` / `nautilus --select`，
    失败才退 `xdg-open 父目录`（并在文案里说清只是打开目录）。

### 不做（本轮明确排除）

- SMB 真机性能验收（plan §8，用户自行验收，见 todo `smb-accept`）
- 撤销 Ctrl+Z（plan §2.3 明示二期）
- 搜索窗口非模态（清单 20.5，仍 PENDING）

---

## 7. 顺带发现的清单不准（与 Linux 无关，记账）

- `docs/feature-checklist.md` 18.4「支持 7z/rar」标 🔴，但 `core/archive_ops.py` 早已
  通过 7z 命令行支持 7z/zip/tar/rar（读系统或内置 7z）—— 状态应为 🟢/🟡，待 5.x 真机确认 rar 分支。
- `AGENT.md` 整体落后：技术栈表写 Python 3.10+（`.python-version` 是 3.13）、目录结构缺
  `dir_model.py`/`dir_pool.py`/`lifecycle.py`/`open_with.py`/`file_op_runner.py`/`bookmarks.py`
  等十余个模块、版本号规则仍写 `0.9.5XX`、构建入口指向已废弃的 `build.sh`。
