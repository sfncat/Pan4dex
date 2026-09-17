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
2. ~~**真正断掉的是发布链路**~~ → **v1.9.015 已修**：`scripts/build-linux-docker.sh` 需要的
   4 个 `--add-data` 源在仓库里不存在（其中一个被 `.gitignore` 挡住），而 PyInstaller 对
   缺失的 add-data 源是**硬失败**（当场实测 `exit 1`）→ 新克隆的仓库构建不出 Linux 包。
   现已改为“存在才带”（`resources/icons` 除外，它缺了仍算致命），并在真机上用干净克隆
   确认不再必失败。`releases/` 里从没有 Linux 产物的局面也从本版结束（见 §3）。
3. **本机的测试证据已从“只有 Windows”变成“两端都有”**：v1.9.014 起 Linux 真机（linux230）
   跑过全量——单进程定序 1 次 + 随机序 3 次，**572 passed / 6 skipped**，与 Windows 的
   575+3 总数相等（差异全在 `skipif` 门控）。v1.9.015 再 +10 项崩溃日志/启动安全用例（Windows 585/4）。
   `_list_linux`、pty 后端、`same_volume` 的挂载点边界均已在真机测到（见 §4）。
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
7. **v1.9.016：真机 GUI 验收第一轮（§5.2）跑通了取证通道，并当场撞出两条产品缺陷**（快捷键
   落点只认 `_active_pane`、`StartupWMClass` 与 `WM_CLASS` 对不上）—— 两条的共同点是
   **只有在 X11 桌面上真的跑一次才能发现**，Windows 上的首屏焦点与 `AppUserModelID` 把它们
   各自掩盖了很多年。L5/L13/L15 已过，L11 拿到硬证据，L2/L3/L4/L9/L10/L12 仍未定论。
8. **v1.9.017：第二轮验收又撞出两条，但同一类：“焦点去哪了”**。Ctrl+L 导航后焦点卡在路径栏，
   于是后续方向键 / `Menu` / Delete 全打在输入框上 —— 它一次拦住了三轮自动化验收，而每轮的
   第一反应都是“xdotool 没送到”（四段截图**字节数完全相同**看起来就是“按键丢了”而不是
   “程序里什么也没发生”）；同时量出一个产品级缺陷：**`WindowShortcut` 会把 F2/F5/F7/F8/Ctrl+F
   从文本控件（包括内嵌终端）手里抢走**。L8 本轮已闭环，L3/L5/L10 仍待第三轮（p41），
   但现在已知“不是工具问题”，阻塞源已消除。见 gotchas 第 49 条。
9. **v1.9.018：第三轮验收（p41）两项修复都在真机自证生效，同时把「删除」这条链跑到了底**。
   回焦与 F7 守卫各自有一个「现场反证」（选中行真的跳了 / 弹框数 1 vs 0），L10（加运行权限）
   首次命中。而「Linux 本地删除没落地」查到底是**取证脚本的坑**（确认框默认按钮是 No，
   `key Return` 等于取消），顺着同一条路才摸到真的那个：**文案与行为的判据只共用了一半** ——
   `delete()` 里「走不走回收站」的门控还锁在 `os.name == 'nt'`，Linux 上删 CIFS 共享里的文件，
   弹框说「永久删除」，`send2trash` 却在共享根凭空建了 `.Trash-1000/`（p42 实测）。见 gotchas 第 50 条。

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
| 全仓在 docker 里真机出包（v1.9.015，干净克隆无 `resources/tools/`） | 修复前：必失败（上面那条 `--add-data` 硬错误）；修复后：3.10 与 3.11 镜像各自 exit 0，产物 `--version`/`--info` 正常 |
| 产物放进 root 拥有的只读目录后启动（/opt 场景） | 修复前 **exit 1**（`PermissionError` on `pan4dex_crash.log`）→ 修复后 exit 124（timeout 杀的，即活着），退路日志落在 `~/.cache/pan4dex/` |
| 全量测试（Windows，v1.9.012 基线） | 476 passed / 1 skipped（随机序与固定序两轮一致）；v1.9.013 起为 **569 passed / 1 skipped**；v1.9.015 为 **585 passed / 4 skipped**；v1.9.016 为 **599 passed / 4 skipped**（两轮一致） |

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
| 应用菜单注册 | 不适用 | `--install-menu` + `scripts/install-linux.sh` 两条路 | 🟢 **v1.9.016 真机验通**（p38 第 7 段）：`--install-menu` 生成的 `.desktop` 里 `Exec` 指向正在跑的产物、`Icon=pan4dex`、`StartupWMClass=Pan4dex`，与窗口 `WM_CLASS = "pan4dex-1.9.016-linux", "Pan4dex"` 的**第二项完全一致**，文件无 CR；两条路的字段由用例钉住一致 | `main.py:_desktop_entry_text`；`tests/test_desktop_entry.py` 6 项 |
| 任务栏分组 / 图标归属 | `AppUserModelID` | ~~`StartupWMClass=pan4dex` 与 WM_CLASS 对不上~~ → **v1.9.016 修**：Qt 在 X11 写 `(argv[0] basename, applicationName())`，匹配键只能取 `APP_NAME`（`Pan4dex`，区分大小写，不能取每版都变的产物名）；仍**未调 `setDesktopFileName`**（GNOME 上按启动器归类还差这一步） | 🟡 匹配键已对齐（真机 `xprop` 比对过），“图标真的分组了”仍待肉眼确认 | `main.py:_desktop_entry_text`、`packaging/pan4dex.desktop`；见 gotchas 第 48 条 |
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
| 回收站 | `send2trash` + `\\?\` 前缀修正 | ✅ v1.9.018：本地走 freedesktop Trash（`~/.local/share/Trash/{files,info}`，p42 真机确认会自己建），**网络位置不分平台一律永久删除** | 🟢 已修 | `core/file_operations.py:754-781`；旧行为会在 CIFS 共享根造 `.Trash-1000/` |
| 删除后果文案 | 区分「本地→回收站 / 网络→永久不可恢复」 | ✅ v1.9.013 文案不分平台；✅ v1.9.018 **行为**也跟上了同一个判据（以前只有文案改了，`delete()` 里的回收站门控还锁在 nt） | 🟢 已修 | `describe_removal()` + `_is_network_path()` 现在是同一句话的两个消费方 |
| **慢盘/网络盘识别** | UNC + `GetDriveTypeW==DRIVE_REMOTE` | ✅ v1.9.013：解析 `/proc/mounts`（macOS `mount -p`）按最长前缀找挂载点 + 慢类型表（cifs/smb/nfs/任意 `fuse.*`（含 gvfs）/sshfs/rclone/9p/虚拟机共享盘…）→ 不挂 watcher、导航强扫、删除文案一次接通 | 🟢 已验：✅ v1.9.018 真机（p40b，64 项真 `/proc/mounts`）上 CIFS 挂载命中、本地 ext4 与 `/proc` 不误判 | `core/mounts.py`（四个消费方：`_is_network_path` / `DirStoreModel._is_network` / 确认文案 / **实际删除**）|
| 跨线程进度/取消 | `FileOpRunner` | 同一套 | 🟢 | `core/file_op_runner.py` |
| 撤销（Ctrl+Z） | 未做 | 未做 | 🔴 plan §2.3 明示留二期 | — |

### 2.5 搜索与工具集

| 能力 | Windows | Linux | 判定 | 证据 |
|---|---|---|---|---|
| 高级搜索（名/内容/大小/日期） | `os.walk` | 同一套；**搜根目录会把 `/proc`、`/sys`、`/dev` 扫进去**（无跨设备开关、无排除表） | 🟡 已实测，且实测比推断更疼：**只按名字筛时无害**（`/dev` 623 项 0.01s、`/proc` 212,416 项 5.25s、`/sys` 49,011 项 1.15s，全部自然结束）；但**勾选内容搜索后 worker 会阻塞在伪文件的 `read` 里、`stop()` 叫不回来**（分别卡在 `/dev/ptmx`、`/proc/<pid>/task/<pid>/fd/9`、`/sys/kernel/security/apparmor/revision`，stop 后 3s 仍 `isRunning()`）——搜 `/` 时「可取消」这个承诺不成立。属候选缺陷（v1.9.019 素材，待拍） | `widgets/advanced_search.py:87`；p49 探针（模块级 `open` 换带日志的壳 + 逐根单进程跑）|
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

> **状态（v1.9.015）**：下表 3.1–3.5 已在真机（linux230 + docker 出包）修完并验证，标记见每行行首；
> 3.6（历史 Linux 包停在 0.9.68x）由本次出包自然终结。修的过程中又真机抓出两条
> **不在原表里**的问题，见 3.7 / 3.8。

| # | 问题 | 后果 | 证据 |
|---|---|---|---|
| 3.1 ✅已修 | `scripts/build-linux-docker.sh` 要求 4 个 `--add-data` 源：`resources/themes`、`resources/tools/exiftool-linux`、`resources/tools/7z`、`resources/tools/qt6-im-plugins` | **全部不在仓库**（`resources/` 只有 `icons/`；`/resources/tools/` 被 `.gitignore:57` 排除；`resources/themes` 连代码都不读它）→ PyInstaller 对缺失源是 `ERROR ... exit 1` → 新克隆必失败。**改法**：`themes` 那条彻底删（无人读）；tools 三项「存在才带」+ 构建末尾打印「本包不含 X」；`resources/icons` 仍视为致命（缺了产物没图标还出货） | ✅ 实测缺失即硬失败 + `git ls-files resources`；修复后干净检出出包成功（见 3.7 那次构建） |
| 3.2 ✅已修 | `packaging/Dockerfile-linux` 的 pip 列表：`PyInstaller send2trash Pillow qdarkstyle cairosvg pyte` | **缺 `pillow-heif`**（→ HEIC 静默不可用，只记一条 debug 日志）；`cairosvg` 是早年遗留项（全仓没有任何地方引用它，也没有 SVG→PNG 的调用）→ 已补 pillow-heif、删 cairosvg | 📖 与 `pyproject.toml` 依赖表逐项对 + `rg cairosvg` |
| 3.3 ✅已修 | 镜像是 `python:3.10-bullseye`，而 `pyproject.toml` 写 `requires-python = ">=3.11"`、`.python-version` 是 3.13 | 自相矛盾。静态扫过：没有 3.11+ 专属 API，3.10 确实能跑 —— 但声明与工具链不一致本身就是坑。已把镜像升 `python:3.11-bullseye`（glibc 仍 2.31，目标机 2.35 约束不变），声明与构建环境对齐 | 📖 + ✅ 3.11 镜像出包（v1.9.015-p27） |
| 3.3b ⚠️新发现 | bullseye 的 LTS support 刚结束 | `deb.debian.org/debian-security` 上的 `+deb11uNN` 包全部 404 → **旧 Dockerfile 从此不可重建**（`apt-get update` exit 100）。镜像源已改 `archive.debian.org`（main + updates），security 通道在 archive 里不存在、已删；archive 的 Release 过期，需 `-o Acquire::Check-Valid-Until=false`。代价：不再有安全更新 —— 这是编译镜像不是运行环境，可接受 | ✅ 404 原文 + archive 上 apt-get update 通过 |
| 3.4 ✅已修 | `scripts/build.sh` 仍被 `AGENT.md:131-132` 列为 Linux 构建入口 | 它取版本靠 `main.py` 的 `__version__`、注 `__build_time__` 也改 `main.py`（两者早已搬到 `config/app_config.py`）→ 版本退化成 `v0.0.0-dev`、编译时间为空；且 `pyinstaller ... main.py` 不带任何 `--add-data`（图标进不去）；产物名带 `v` 前缀，`install-linux.sh` 按 `pan4dex-<VERSION>-linux`（无前缀）去找 → 找不到。**改法**：Linux 段整段替换为转发 `build-linux-docker.sh`，版本源改 `config/app_config.py` 并去 `v` 前缀 | 📖 `scripts/build.sh:39,76-79,44` vs `scripts/install-linux.sh:19-20`（`docker/README.md:139` 已标注该脚本废弃，但 AGENT.md 没同步） |
| 3.5 ✅已修 | Linux 构建入口实际有**三条并存**：`build-linux-docker.sh`（canonical）、`packaging/pan4dex.spec`（README:132 与 `docs/development-guide.md:198` 推荐）、`scripts/build.sh`（AGENT.md 推荐，已废弃） | spec 路线今天确实能跑（✅ 实测 exit 0，还自动收了 QtSvg/imageformats/pillow_heif），但它不带 `resources/tools/*` 与输入法插件，产物能力面与 docker 路线不同；README:136 那行（Windows）**`--icon=resources/icons/pan4dex.ico` 指向不存在的文件**（现在叫 `resources/icons/icon.ico`），而缺 icon 在 PyInstaller 6 是 `FileNotFoundError` 硬失败。现在文档里只剩一条 canonical 路线，spec 明确标注为「手动/降级路线」并修掉了不存在的 `--icon` | ✅ + 📖 |
| 3.6 | `releases/` 无任何 Linux 产物；最后一次 Linux 构建工作记在 v0.9.644–v0.9.684 | 从 0.9.68x 到 1.9.012 约 50 个版本的改动**从没进过 Linux 包**，Linux 现状只能靠读代码判断 | 📖 `git log -- docker/ packaging/ scripts/*linux*` + changelog |
| 3.7 ✅已修（真机抓出） | 崩溃日志落点硬编码在 exe 同级，且 `install_signal_handlers()` 不包异常 | **Linux 装到 root 拥有的目录（`/opt`）时每次启动即死**，Windows 装 `Program Files` 同理。栈：`main()` → `install_signal_handlers` → `PermissionError: releases/pan4dex_crash.log`。安全网自己成了扳机，而且它比窗口创建还早 → 用户连错误框都看不到。已改为候选序列（exe 同级 → 用户缓存 → 临时）+ `'a'` 试探 + 缓存 + 全失败也不抛 | ✅ 真机 exit 1 → 修复后 124（`docs/gotchas.md` 第 45 条）。**顺带查出第 2 坑**：三处写入点都用 `'w'`，每次启动截断上一次的现场 —— 长期“crash 日志是空的”、拿不到段错误栈就是这个原因（直接妨碍 av-watch 与残余崩率调查）。现在三处都追加 + 超 256KB 才轮转，`setup_logging()` 也按同样标准包了 |
| 3.8 ⚠️新发现 | 构建脚本里 `docker run ... bash -c "... $DATA_ARGS ..."` 的变量未转义 | 宿主 bash 先把它展开成**数组的第 0 个元素**，容器里收到 `--add-data main.py` → PyInstaller 只报「`--add-data` 语法错」，绝不提示 `main.py` 消失了。必须写 `\$DATA_ARGS` 把展开推迟到容器侧 | ✅ p24 第一轮构建失败原文（见 gotchas 46.2） |

---

## 4. 测试覆盖的平台偏斜

| 事实 | 数字 | 影响 |
|---|---|---|
| 在 Linux 上会被 `skipif` 跳过的用例 | 6 项（回收站文案 2、注册表 2、Windows 命令行规则 1、Windows `Preferred DropEffect` 1） | 这些本来就是 Windows 专属，合理 |
| 在 Windows 上被跳过的 Linux 专属用例 | 4 项（v1.9.014 新增 3 项 + v1.9.015 的只读安装目录复刻 1 项） | Windows 开 **585 passed / 4 skipped**，Linux（已提交状态、定序与随机各一次）**583 / 6**，总数 589 吻合 —— 但 Linux 专属那几项在 Windows 上**从未执行过**，只能在真机上算测到。v1.9.016 再加 14 项（落点 8 + `.desktop` 6）后 Windows 为 **599 / 4**，Linux（已提交状态 72de75a，定序与随机各一次）**597 / 6**（差 2 项 = Windows 专属的 skipif 门控，新用例本身两端全绿）。v1.9.017 再加 20 项（快捷键作用面）后 Windows 为 **619 / 4**，Linux 侧 **617 / 6**（总数 623 吻合）。v1.9.018 再加 6 项（回收站只给本地位置）后 Windows **624 / 5**（多的那 1 项跳过是系统剪贴板被占用，环境性飘移），Linux（已提交状态 `4ad6dd1`，定序与随机各一次）**623 / 6**，总数 629 吻合 |
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
**623 passed / 6 skipped**（v1.9.018、已提交状态 `4ad6dd1`、定序与随机各一次），历史：
v1.9.015 为 583 / 6，v1.9.014 时为 572 / 6，与 Windows 同总数（差异全是 `skipif` 的平台门控）。
`python main.py` 在
offscreen 下能起，日志里 `延迟创建 pane2-4: 189.2ms` 正常完成。

第一轮摸上来的 6 个失败已全部定性（4 条是用例写死了 Windows 假设、1 条是
`_list_linux` 的内置兜底与 Windows 不一致、1 条是测试替身不完整），另有一条
`test_m4_theme` 段错误被证实是**用例之间泄漏 app 级 stylesheet** 造成的（非产品缺陷，
见 `docs/gotchas.md` 第 44 条）。单跑该模块仍有 1-3/12 的残余崩率（整场跑不复现），
继续观察。

要记的永远不止红/跳：红的那些**是不是产品错**，只有真机能回答（本轮 6 条里只有 1 条是）。

### 5.2 手工 GUI 验收（按风险从高到低）

> **v1.9.016 第一轮已完成（取证手法）**：在 linux230 的 xrdp `:10`（Xfce，2560x1440 @96dpi）
> 上跑**冻结产物**，用 venv 里的 PyQt6 `primaryScreen().grabWindow(0)` 抓全屏 PNG 拉回本机
> **亲自看图**（比任何文字断言都强）；驱动靠 `xdotool` 键盘 + `wmctrl` 最大化 + `Menu` 键
> 开上下文菜单（见 gotchas 第 48 条）。这一轮**当场撞出两条产品缺陷**，均已在 v1.9.016 修复：
>
> 1. 快捷键与侧边栏点击的落点只认 `_active_pane` → 启动后“一次都没点过窗格”期间一批快捷键
>    在 Linux/X11 上**静默失灵**（Windows 首屏焦点正好在 pane1，所以多年看不出来）
> 2. `.desktop` 的 `StartupWMClass` 与窗口的 `WM_CLASS` 两项都对不上（见 §2.1）
>
> 还翻案了一条：终端 dock 关掉后 shell 不退**是有意设计**（`TerminalPanel.closeEvent` 只隐藏、
> `shutdown()` 才杀），读 docstring 才知道 —— 真问题被改写为“Ctrl+Q 退出后 shell 是否退”。
>
> **v1.9.017 第二轮（p38）**：先用“不再点窗格、只靠 Ctrl+L 导航”自证了落点修复（shot 71：
> pane1 真到了 `/home/kali/pics`），然后第 2/3/5/6 段**全部无动作** —— 四段截图字节数完全相同。
> 个中原因不是 `xdotool`，而是**导航后焦点留在路径栏输入框**（shot 71 里看得见文本光标），
> 后续按键全打在输入框上；顺手量出了 `WindowShortcut` 抢走 F2/F5/F7/F8/Ctrl+F 这个真缺陷。
> 两条均已在 v1.9.017 修（gotchas 第 49 条），**L3/L5/L10 本身仍待第三轮（p41）**，
> 但阻塞源已消除 —— 下一轮不能再拿“工具问题”当结论。L6/L8 本轮已定论（见下表）。
> 附带发现：上一轮误关的「修改日期」列**跨重启仍在**（列状态持久化，本身不是缺陷，
> 但它是验收里的干扰项）。
>
> **v1.9.018 第三轮（p41）+ 一次代码路径探针（p42）**：两项修复各自拿到现场反证 ——
> 导航后按 Down 截图字节数变了（选中行真的跳），而焦点在路径栏时按 F7 **弹框数 0**、
> 焦点在列表时按 F7 **弹框数 1**（守卫真在拦）。L10 首次命中（`photo_2.png`
> `-rw-rw-r--` → `-rwxrwxr-x`）。L3 则拆成了两半：文案半边✅，而「本地删除没落地」
> 查到底是**取证脚本的坑**（确认框默认按钮是 No，`key Return` 等于取消），
> p42 用产品同一条代码路径证明本地 `send2trash` 完全正常 —— 但顺着同一条路撞出了
> 真缺陷：`delete()` 里回收站门控还锁在 nt，Linux 上删 CIFS 共享里的文件会在**共享根
> 目录**造一个 `.Trash-1000/`（与文案承诺的「永久删除」相反）。v1.9.018 已修 + 6 项用例。
> 另一个取证发现：高级搜索那一段 `typeit` 打进了空气（焦点不在「搜索目录」框），
> 于是弹了「请输入搜索目录（保存与搜索用同一套校验）」—— 脚本的锅，但顺手证明了
> 空目录校验在 Linux 上是中文且明确的。
>
> **v1.9.018 第四轮（p43）与第五轮（p46 / p48）—— 「删除」三条链全部闭环**。
> 第四轮改用 `alt+y` 真点 Yes，两条落地：本地删除 → 文件真的出现在
> `~/.local/share/Trash/{files,info}`；CIFS 删除 → 文件真的消失且共享根**不再**长
> `.Trash-1000/`（v1.9.018 的真机自证），而弹出来的「删除完成 / 1 个项目位于网络位置，
> 已永久删除（无法恢复）」就是 `permanent_fallbacks` 那句新文案。但 §3 整段又没执行 ——
> 原因是那个**模态的「删除完成」告知框**挡住了一切按键（p42 时代没人碰过它，因为
> Linux 上以前从不计 `permanent_fallbacks`）。第五轮于是换断言方式：**直接拿对话框标题
> 当 oracle**（`xdotool search --onlyvisible --name '^确认删除$'`，标题就是
> `describe_removal` 给的文案标题），三条全绿：本地 → Trash；CIFS → 永久且无
> `.Trash-1000`；Shift+Del → 「确认永久删除」弹框 + 文件消失且回收站里没有它。
> L9 也在第五/六轮补齐（见 gotchas 第 51 条：坐标要从 X 现读的窗口几何量，
> `QLineEdit` 重填必须先 `ctrl+a`）：搜索真跑起来、结果列表与「共 N 个，仅显示前 5000 项」
> 上限提示都正常，无效目录给「目录不存在」，而「中途停止」用 A/B 坐实：同一个查询
> （`/home/kali` + `*.txt`，全盘 130 万文件）3s 就点停止 → **503** 项，不点 → **40,944** 项
> （与 `find` 数的 40,933 吻合，说明不点那跑确实跑完了）。
>
> 第六轮另开了一个危害探针（p49）去回 §2.5 那条 ❓：“搜 `/` 会不会把 `/proc`、`/sys`、`/dev`
> 扫进去”。答案是会，而且后果比推断严重：只按名字筛时三者都能跑完（/proc 21 万项 5.25s），
> 但一旦勾选内容搜索，worker 就**卡在伪文件的 `read` 里且 `stop()` 叫不回来**（`/dev/ptmx`、
> `/proc/<pid>/task/<pid>/fd/9`、`/sys/kernel/security/apparmor/revision`）——而 `stop()` 只在
> 遍历循环里查 `_stop`，卡在系统调用里时它根本没机会查。本段只记录，不改代码。

| # | 验什么 | 判定标准 | 状态（最新一轮） |
|---|---|---|---|
| L1 | 能不能构建出来 | 不再需要手工造 `resources/tools/*`，干净检出能直接出包；产物 `--version`/`--info` 正常、能常驻 | ✅ **v1.9.015 已过**：3.10 与 3.11 两个镜像都验过，offscreen 下能常驻 |
| L2 | 挂 SMB（gvfs 或 CIFS）后浏览 | 打开 1 万个条目的共享目录：不闪、能取消、切走窗格不继续扫；**当前必然表现为按本地目录处理**（§2.4 ⚠️） | ❓ **未做**：230 上两个 CIFS 共享都太小（photos 13 项 / backupSpaceInJKJ 2 项），而**不在用户 NAS 上造 1 万个文件**；要么用 `big100k` 当本地基线 + 在真挂载上只验“判据命中”（ln6） |
| L3 | 回收站 | 本地删除进 Trash；gvfs/CIFS 上**行为**是否与文案一致 | ✅ **v1.9.018 第五轮（p46）三条链全绿（GUI 真点 Yes）**：本地 `Del` → 文件在 `~/.local/share/Trash/files/`；CIFS `Del` → 文件消失且共享根**不再**长 `.Trash-1000/`（就是本版修的那条），并弹「删除完成 / 1 个项目位于网络位置，已永久删除（无法恢复）」；`Shift+Del` → 文件消失且回收站里没有它。断言用对话框标题（确认删除 / 确认永久删除 / 删除完成），不再靠截图字节数（gotchas 第 51 条）。p41 那两段「没落地」已正名：默认按钮 No + `key Return` = 取消<br>⚠️ 待拍：要不要把确认框默认按钮翻成 Yes（资源管理器里回车就是 Yes）|
| L4 | 拖放 | 从 Nautilus/Dolphin 拖入：同分区应移动、跨分区应复制；源端不允许 move 时不得删源 | ❓ **未做**：跨程序拖拽需要真鼠标轨迹（`xdotool` 能做但极不稳），放到有人在现场的那一轮 |
| L5 | 打开方式 | 右键 → 打开方式：候选列表是否来自 `.desktop`、mime 匹配是否正确、`%f/%U` 是否被剥掉 | ✅ **v1.9.018 第三轮命中（p41 shot 96）**：对 `photo_2.png` 展开子菜单，候选是 **Image Viewer / ristretto Image Viewer / xdg-open / 选择其它应用并设为默认…**，状态栏显示解析出的 `/usr/bin/eog` —— 确实来自 `.desktop` 枚举且 mime 匹配对了，`Exec` 里的 `%f` 已被剥掉（否则会被当成文件名）。剩下：选中某一项后能不能真把图打开（p43 之后补）|
| L6 | 内嵌终端 | `$SHELL`、vim/htop 全屏程序、resize、关闭窗口后 shell 是否真退 | 🟡 **v1.9.016 查清一半，本轮补上后半**：起的确实是 `/usr/bin/zsh`；“关 dock 后 shell 不退”经读 `closeEvent` docstring 确认是**有意设计**；Ctrl+Q 后应用进程归 0，退出前 shell 子进程 1 个，`pgrep -u kali -x zsh` 的 4 个残留 etime 均为 01:29:54（**早于本次测试的会话 shell**，不是泄漏）。剩下：vim/htop 与 resize（注意：v1.9.017 之前 F2/F5/F7/F8 会被窗口抢走，这一类用例必须在新版上跑）|
| L7 | 图标与缩略图 | 确认「所有文件同图标」的实际观感；SVG/PNG/HEIC 缩略图是否出得来（qsvg 插件、pillow-heif） | 🟡 **v1.9.016 前半已确认**：非目录文件确实共用同一个通用图标（观感与 Windows 一致地差，属第三批的 `QFileIconProvider` 范围）；缩略图与 HEIC 未试（造 HEIC 靶子需要 `pillow_heif`，230 宿主 venv 里没有） |
| L8 | 桌面集成 | `--install-menu` 后应用菜单出现图标；GNOME 任务栏分组/窗口图标是否正确（WM_CLASS 那条） | ✅ **v1.9.016 修匹配键 + 本轮真机闭环**：`--install-menu` 生成的 `StartupWMClass=Pan4dex` 与运行窗口的 `WM_CLASS = "pan4dex-1.9.016-linux", "Pan4dex"` **第二项完全一致**，`Exec` 指着正跑的产物、文件无 CR。仍待的只剩 GNOME 上“图标真的分组了”的目视确认（230 是 Xfce，且未调 `setDesktopFileName`）|
| L9 | 全盘搜索 | 搜 `/` 或 `/home`：`/proc`、`/sys` 是否被扫、耗时、能否中途取消 | ✅ **v1.9.018 第五/六轮闭环（p46 §4 + p48）**：搜索对话框真跑起来（`/home/kali/pics` + `*` → 「搜索完成，共找到 3 个文件」），上限提示「共 40,944 个，仅显示前 5000 项」、空目录「请输入搜索目录」、目录不存在校验均命中；**中途停止用 A/B 坐实**：同一查询（`/home/kali` + `*.txt`，全盘 130 万文件、纯遍历 57.8s）3s 就点停止 → **503** 项，不点 → **40,944** 项（`find` 数得 40,933，吻合 —— 不点那跑确实跑完了）。⚠️ 两条量出而未改：停止与跑完的状态栏文案**一模一样**（用户看不出这是部分结果）；搜 `/` 的 `/proc`/`/sys`/`/dev` 后果见 §2.5（内容搜索下不可中断）|
| L10 | 权限 | 右键「加运行权限」后从界面能否看出生效了（现在看不出，因为没有权限列） | ✅ **v1.9.018 第三轮首次命中（p41）**：`Menu` + 4 下方向键 + Return 后，`photo_2.png` 从 `-rw-rw-r--` 变 `-rwxrwxr-x`，日志「加运行权限: /home/kali/pics/photo_2.png」。**「界面上看不出来」这条结论不变**（没有权限列，第三批补）|
| L11 | 中文输入 | ✅ v1.9.015 查清一半：PyQt6 wheel **自带的就是 `libibusplatforminputcontextplugin.so` + compose**，且它们确实进了 onefile 包（运行时解包目录里可见）→ ibus 桌面预期可用。fcitx5 的 Qt6 插件不在 wheel 里（只在系统的 `qt6/plugins/platforminputcontexts/`），而冻结后的查找路径只认包内 —— 这正是 `resources/tools/qt6-im-plugins` 该装的东西，而它仍不在仓库。剩下：ibus/fcitx5 两种桌面上真打一次字。<br>🟡 **v1.9.016 再加一条硬证据**：跑着的冻结产物 `/proc/<pid>/maps` 里**没有任何** fcitx/ibus/platforminputcontext 模块（系统里确实有 `libfcitx5platforminputcontextplugin.so`）→ 与上面的推断吻合。注意：ssh 起的进程环境里根本没有 `QT_IM_MODULE`（桌面会话才有），所以“真打一次字”必须在 `:10` 会话内做 |
| L12 | Wayland vs X11 | 两种会话下都跑一遍：高 DPI、拖拽、`QT_QPA_PLATFORM` 自动选择 | ❓ **只剩 Wayland 半边**：230 上没有 Wayland 会话（`XDG_SESSION_TYPE=x11`），本轮只覆盖了 X11 + xrdp；高 DPI 在 96dpi 下也没得验 |
| L13 | 大目录内存/CPU | 10 万条目目录（Linux 上 ext4/xfs 很常见）下列表与排序 | ✅ **v1.9.016 已过**：自造 `/home/kali/big100k`（10 万项，枚举本身 9.7s）后子进程 RSS ≈ 105MB、%CPU 6.0，列表能出、界面能继续操作（Down×30 不卡）。另 1 万项目录 0.6s 建完，导航无感 |
| L14 | 无桌面环境（纯 TTY/SSH） | 明确「不支持」还是能起（offscreen） | ✅ **v1.9.014 已答**：`QT_QPA_PLATFORM=offscreen` 下全量 583 passed、`main.py` 能常驻；但那是测试路径，面向用户的“SSH 环下转发 X”不打算支持（记为设计边界） |
| L15 | 单实例 / 多开 | Linux 上从终端起两次会怎样（两端都没做锁，记录事实即可） | ✅ **v1.9.016 已过**：起两次 = 2 个主窗口 / 4 个进程（onefile 引导 + 子进程各一对），无锁、互不干扰，与 Windows 一致 |

---

## 6. 建议的修复顺序

### 第一批：让 Linux 重新可交付（不碰功能代码）—— ✅ v1.9.015 已完成并在真机验通

1. ✅ **`build-linux-docker.sh` 的 `--add-data` 改为「目录存在才带」**；`resources/themes` 已删
   （代码里没人读它）；缺 `exiftool-linux`/`7z`/输入法插件时打印「本包不含 X，功能依赖系统安装」
   而不是构建失败；`resources/icons` 缺了仍直接 `exit 1`（那是真产品残次）。
2. ✅ **Dockerfile 补 `pillow-heif`、删 `cairosvg`**；Python 版本选“镜像升到 3.11”（不动
   `requires-python`，也不动 glibc 基线）。附带发现：bullseye LTS 已结束，镜像源必须换
   archive.debian.org，否则 Dockerfile 本身不可重建（见 3.3b）。
3. ✅ **Linux 构建入口收敛成一条**：`build-linux-docker.sh`。`scripts/build.sh` 的 Linux 段
   改成转发它（不再是第二套实现）；`AGENT.md`/README/`docs/development-guide.md` 已同步，
   spec 降为“手动/降级路线”并修掉了不存在的 `--icon=resources/icons/pan4dex.ico`。
4. ✅ `apply_windows_native_icon()` 加了 `sys.platform != "win32"` 早退。~~每次启动白抛两次~~
   —— **本条结论已推翻**：两个调用点（`main.py:584-601`）早已在 `if sys.platform == "win32":`
   块内，Linux 上根本不会被调到。现在这个守卫是防御性的（防未来新增未罩住的调用点），
   不是修 bug。

**第一批修完后真机额外抓出的（不属原计划）**：崩溃日志不可写导致启动即死（3.7）、
`$DATA_ARGS` 宿主展开（3.8）、bullseye 镜像不可重建（3.3b）—— 三条都是“不在 Linux 真机上
跑一遍构建就永远看不见”的那类。

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
