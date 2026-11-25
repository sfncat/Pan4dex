---
project: Pan4dex
path: C:\workspace\Pan4dex
status: active
owner_ai: Trae
updated: 2026-11-25
---

## 当前进展

**1.9.054 已发布并上传（2026-11-25）：修复「点一下整个界面转圈」的文件图标卡死**（用户报「本机 pan4dex 卡死，点一下就转圈，应该是 SMB 相关」）。原生栈定位到根因不在 SMB 读取，而在取文件图标：`type_icon()` 旧实现把真实路径交给 `QFileIconProvider`，Windows shell 逐项调用注册的云盘图标覆盖处理器（本机 25+ 个：OneDrive/百度网盘/Google Drive 等），其中跨进程 COM RPC 卡住 → UI 线程在 `QAbstractFileIconEngine::scaledPixmap → QWaitCondition::wait` 同步等死。已改成 `SHGetFileInfoW` + 伪文件名 + `SHGFI_USEFILEATTRIBUTES`，只按扩展名查关联、不碰真实文件；非 Windows 沿用原路径。新增 `tests/test_type_icon.py` 7 条，对照组（换回旧实现）3 条红、恢复全绿。改动仅落 `core/dir_model.py` + 测试，未动配置/视图。**本版已翻牌为正式版本：`VERSION` / `pyproject.toml` / `AGENTS.md` 同步 1.9.054，CHANGELOG 顶部改为 `2026-11-25（master）`，tag `v1.9.054`。**

**同批落地四条 Linux/跨平台问题**（用户列 4 项）：① Linux 右键「在文件管理器中显示」变浏览器——`core/reveal.py` 旧回落 `xdg-open 父目录` 把 `inode/directory` 交给了 MIME 默认程序，改成桌面匹配 → PATH 探测真实文件管理器 → D-Bus `ShowItems` → 最后才 xdg-open（gotchas #71）；② Linux 压缩/解压「功能没了」——菜单在但 `find_7z()` 三级兜底全空，官方 7zz 25.01 + LGPL 许可证已入库并精确放行 `.gitignore`、Linux 构建随附许可证（gotchas #72）；③ Linux 双击 `.md` 不走系统默认——默认表写死 gedit 且 `open_file()` 关联优先，删掉硬编码并对老配置里恰好是旧默认值的做一次性迁移（gotchas #73）；④ 文件视图/目录树右键新增「复制路径」「复制文件名」（原「复制文件地址」更名），搜索右键补「复制文件名」，多选逐行写剪贴板。四条均有新用例与对照组（reveal 红 3 / md 红 3 / 图标红 3）；构建脚本加许可证时引入内层 `if` 撞上既有守卫的解析假设，已改成单行 `&&` 并补守卫。

**卡在哪 / 验证结果**：全量第一次跑崩在 `EXIT=139`——非产品代码问题：卡死的老进程（PID 32680，31 小时）仍握着 `%APPDATA%\pan4dex\logs\pan4dex.log` 句柄，测试里 `TimedRotatingFileHandler` 跨天轮转 `os.rename` 撞 `[WinError 32]`，每条 logger 都重试一次把 pytest-qt 拖到段错误。未擅自杀用户进程，改用隔离 `APPDATA` + 全新 `TMPDIR` 重跑（config/paths.py 与 main.py 都读 APPDATA）：中途那轮 **1046 passed / 6 skipped / 2 failed** 的 2 条（`test_bookmarks`、`test_m4_theme` 默认收藏）是隔离环境缺 `~/Desktop` 导致「桌面」条目被跳过；补建 Desktop 后那轮全量 1048 passed / 6 skipped。叠加本轮四项修复后发布前置全量为 **1065 passed / 6 skipped（215.04s，EXIT=0）**；本次双平台出包在隔离 `APPDATA` + 全新 `TMPDIR` 下复跑为 **1066 passed / 5 skipped（159.46s，EXIT=0，0 失败）**。之前 1.9.053 基线 1042 passed / 5 skipped。

## 等你决策

- **地址栏访问局域网共享：Windows 半边已落地，剩下两条各挡住一项待办**（原来四条决策的答复记在
  `docs/design-unc-share-access.md` §9，实现回执在 §11，**两条待定项的逐项对比在 §12**）：
  1. **Linux 那半边的口令谁来存**。决定什么：原先以为是「加一个 Python 依赖还是调系统命令」二选一，
     本轮上目标机只读实测后**多出第三条、而且它可能让前两条都不用选** —— 那台机的共享挂载后端
     （gvfs）自己就带着钥匙环客户端，口令很可能由它存，我们一行都不用写。拍完会怎样：
     Linux 侧「记住」这一格才填得上；不拍就按「Linux 每次重开都要重输」发布，功能照用。
     建议：**先真挂一次共享验证第三条**（只要一次挂载就能出结论，本轮没做是因为不拿你的 NAS 做实验）；
     若它不替我们存，再选「加 Python 依赖」那条 —— 我们的 Linux 产物是单文件，依赖能打进包、
     系统命令不能，而目标机恰好没装那个命令。对比与实测出处：设计稿 §12.1、`docs/linux-gap.md` §5.4。
  2. **列出某台机器所有共享的界面放哪儿**。决定什么：输入只到 `\\主机` 时，共享列表是摆在**当前窗格**里
     （像普通目录一样能排序、双击进入），还是弹一个**小对话框**挑一个再进去。拍完会怎样：
     前者体验统一，但本轮核到行后发现窗格的数据源**没有塞入「不是真目录」条目的口子**，
     要改四处「这是不是目录」的判断外加「返回上级」的语义（5–8 天）；后者窗格与数据源一行不动，
     照现有搜索对话框的形状做（1–2 天）。建议：**先用对话框这一版**，等 `\\主机\共享` 主路径真机验过
     再考虑搬进窗格。两条路的改动面/风险/可测性对比在设计稿 §12.2；无论选哪条，都要先补一轮
     列共享 API 的只读探针（已实测的 27 个错误码里没有它）。
- **真机复测什么时候安排**：有些事必须有人在机器前才验得了 —— 大目录在 Linux 上到底卡多久（决定要不要把排序整个搬到后台）、四种视图的 Ctrl+End 手测、Linux 与 Windows 上「在文件管理器中显示」能不能真把文件高亮选中、切回超大图标看一眼是不是网格、关程序时还报不报错、Linux 上「拍摄日期」列现在能不能真读出日期，以及本轮新加的**「包内 `7zz` 到底有没有执行位」**（构建时已补 `install -m 0755`，但 PyInstaller 是否把执行位带进包内还没实测；判据 = 一台不装系统 7z/p7zip 的 Linux 机器上压缩/解压能用）。选项：安排一轮 30–60 分钟 / 先跳过。不定会挡住这七项销账。建议安排，其中「关程序报错」和「压缩/解压能不能用」是用户真能感知的。逐项自查命令已写进 `docs/linux-gap.md` §5.3，包内计数的查法写进 `docs/build/build-linux.md`「内置工具」一节。
- **「用户操作」菜单要不要接上入口**：对话框与配置层都修好了，产品里仍点不到（待办 T2，从 020 起就是这样）。接上才算一条完整功能；已按「摸不到入口」的规矩把它挪出发布说明。不定会挡住这条功能转 🟢。建议接。
- **大目录那一步大改要不要先排期**：本机实测最差一次卡 0.359 秒，已低于你定的 0.4 秒；Linux 按倍率外推约 0.66 秒仍超。选项：(a) 等真机数字再定；(b) 现在就动手（3–5 天）。不定会挡住 T6 收尾。建议 (a)，不凭外推动工。
- **跨窗格真鼠标拖拽的现场验收**：仍卡在需要有人在现场操作（旧条，未变）。建议与上面的真机复测并成同一轮。

## TOP 待办

| # | 任务 | 状态 | 负责 AI | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 备齐 **L18**（跨 RDP 粘贴真机验收）的自查说明，并写好 **T18**（反向：本机复制 → RDP 里粘贴）的**只读**探针脚本 | 待开始 | 待补充 | 本版修复的真机那一格还空着（复跑时剪贴板已空）。判据 5 条已写进待办 L18，要整理成用户照着点就能出结论的表；反向探针只枚举剪贴板格式、**绝不写剪贴板**（会冲掉用户正在用的那份），得请用户先复制好再跑 |
| 2 | 备齐 **L17**（地址栏共享的 Windows 真机验收）的自查说明：把设计稿 §7.3 的清单整理成用户照着点就能出结论的表（每条附「关掉这处修复会看到什么」） | 待开始 | 待补充 | 真机那一下必须用户在机器前做，但判据与步骤可以先排好；没这份清单，L17 会退化成「你试一下看看」 |
| 3 | `NetShareEnum` 一轮**只读**探针（缓冲区/`ResumeHandle`/权限不足回哪档码），为 T16「列共享」铺路 | 待开始 | 待补充 | 探针未做之前不动那半边的产品代码（已实测的 27 个码里没有它，凭文档转写正是 gotchas #68 那条坑）；界面形状挂在「等你决策」第 2 条 |
| 4 | 核 `core/net_share.py` 在**非 Windows** 上的导入安全：模块 import 不碰 `windll`、`is_supported_platform()` 返回 False、对话框「记住」置灰、`failure_text` 走指引文案 | 待开始 | 待补充 | 现在只有 offscreen 的 Windows 侧用例证明过；Linux 上真起一次（或把 `sys.platform` 打成 `linux` 跑一遍用例）才算闭环，Linux 那半边按拍板排在后面 |
| 5 | 审指向 `core/pane.py` / `widgets/*` / `config/*` 的行号指针（051 那轮只清了 `main.py` 与构建脚本 12 处，同一类问题在别的文件上还没扫） | 待开始 | 待补充 | 同类旧活，一并挂着；本轮 `core/pane.py` 插入了新方法，旧行号指针又漂了一批 |

## 最近完成

- 2026-11-25 **1.9.054 双平台出包并本地核验**（用户「出054版本，双平台，linux使用wsl里的docker编译」）。
  全量 **1066 passed / 5 skipped（159.46s，EXIT=0）**。Linux 在 WSL2 原生目录
  `/root/pan4dex-release-054.YqebVh` 用 Docker 29.8.2 + 缓存基座构建，ELF **108,207,536 字节**，
  SHA-256 `3a959b29bc39aa1adbf44f12fa92c641f6f6b41d0cadb7ae6dfd70ea84e6d25a`；`--version`
  报 v1.9.054，`--info` 报 frozen True，ELF 为 x86-64、权限 755。Windows onedir
  **272,282,209 字节**，zip **116,647,078 字节**，SHA-256
  `0d6f4ac76f726473430ee7caa460869cbd1e8a435895ede56a4eb9a34cf22aa2`；`--version`/`--info`
  同为 054 + frozen True，zip 1277 条全部通过 CRC 且顶层均为 `pan4dex/`。包内 7-Zip 26.04 与
  ExifTool 13.60 均实跑成功；Linux 包 `7zz`/LGPL 许可证各 1、ExifTool 247，Windows 专用三件为 0；
  Windows 包内置 7z.exe/7z.dll/exiftool.exe，无 Linux 二进制残留，归档清单含 net_share、
  net_credentials_dialog、rdp_files、reveal、file_associations。构建临时文件已还原，工作树无构建污染。
  **已上传更新服务器**：Windows 4.9s / Linux 2.7s；两端 latest 均为 1.9.054，version/size/SHA-256
  与本地一致，`X-Checksum-Sha256` 也一致，并把两个产物真下载回来逐字节哈希核对一致，临时副本已删除。
  050–053 四个旧包 HEAD 均 200 且字节数原样；049 按每平台保留 5 版策略裁为 404。远端 master 与
  tag `v1.9.054` 已存在于 `37b5201`；本次回执提交与推送结果另行记入 git log。

- 2026-11-25 **Linux 四项修复 + 跨平台右键复制（1.9.054 的内容）**（用户列 4 条）：
  **①** 右键「在文件管理器中显示」在 Linux 弹浏览器——`core/reveal.py:_linux_argv()` 只认
  KDE/GNOME，未识别桌面就 `xdg-open 父目录`，而本机 `inode/directory` 关联到浏览器。改成三层：
  桌面精确匹配（dolphin/nautilus）→ 不管环境变量按 PATH 探测真实文件管理器
  （nautilus/dolphin/nemo/caja/pcmanfm/thunar，Thunar 明说未选中）→ Flatpak 版走 freedesktop
  D-Bus `ShowItems`，三层全空才回落 xdg-open。`tests/test_reveal.py` 39 条，对照组 3 红。
  **②** Linux 压缩/解压「功能没了」——菜单无任何平台屏蔽，是 `find_7z()` 三级兜底全空：
  系统无 7z、`resources/tools/7z/7zz` 从未入库（被 `/resources/tools/` 排除）。从 7-zip 官网
  取 25.01 的 7zz（2,878,000 B，sha256 `a1860fdf…2f`）与 Linux 版 LGPL 许可证入库，
  `.gitignore` 精确只放行这两个文件；Linux 构建脚本把许可证一起暂存进包（单行 `&&` 写法，
  避免内层 `fi` 破坏既有守卫对 else 分支的定位）。新增 `tests/test_archive_ops_linux.py`
  3 条（含 ELF 魔数守卫）+ `test_build_linux_docker.py` 1 条；踩到 `find_7z()` 把「没找到」
  缓存成空串的语义，测试要重置 `_7Z_PATH` 模拟新进程。
  **③** Linux 双击 `.md` 不走系统默认——`config/file_associations.py` 默认表写死 gedit，
  `open_file()` 关联优先直接 spawn 并 return，`_open_with_default()` 的 xdg-open 没机会跑。
  删掉硬编码 + `load()` 一次性迁移「恰好还是旧默认值 gedit」的条目（用户自选的 typora 等保留）。
  `tests/test_file_associations_default.py` 5 条，对照组 3 红。
  **④** `core/pane.py` 文件视图与目录树右键、以及高级搜索右键增加「复制路径」「复制文件名」
  （原「复制文件地址」更名），多选逐行写入系统剪贴板；新增 `tests/test_copy_path_name.py`
  4 条 + 搜索侧 1 条，同步更新钉着旧菜单文案的既有用例。文档：gotchas **#71–#73**、
  CHANGELOG `[1.9.054]` 补 Added/Fixed 共 4 条（出包时已翻牌）、`docs/linux-gap.md` 两处表格与两处正文。
  版本/pyproject/tag 已随本版同步。发布前置全量 **1065 passed / 6 skipped（215.04s，EXIT=0）**；
  双平台出包复跑 **1066 passed / 5 skipped（159.46s，EXIT=0）**。
- 2026-11-24 **文件图标卡死修复（1.9.054 的内容）**（用户「本机 pan4dex 处于卡死状态，
  点一下就转圈，应该是 SMB 相关」）。不动正在跑的进程，先 `procdump` 抓转圈那一刻的完整 dump，
  自写 PE/栈解析器把两条线程的原生栈翻成符号：主线程
  `QTreeView::drawRow → QStyledItemDelegate::paint → QIcon::paint → QAbstractFileIconEngine::scaledPixmap
  → QWaitCondition::wait`（UI 同步等图标加载），图标线程
  `SHGetFileInfoW → SHELL32_GetIconOverlayManager → Ndr64AsyncClientCall → CoWaitForMultipleHandles`
  （跨进程 COM RPC 卡住）。**更正用户的猜测**：SMB 只是放大器，根因是取图标时把真实路径交给了
  shell，触发本机注册的 25+ 个图标覆盖处理器（OneDrive 7 / 百度网盘 7 / Google Drive 4 / IDM /
  Adobe CoreSync / Offline Files），任一 RPC 卡死就拖死 UI。实测对照：新路径伪文件名 +
  `SHGFI_USEFILEATTRIBUTES` 稳态 1–3ms，旧 `QFileIconProvider.icon(真实 UNC 路径)` 对 NetworkDrive
  返回 null 且 216ms。修法落 `core/dir_model.py`：Windows 走 `_WindowsShellIconApi`（伪文件名 +
  USEFILEATTRIBUTES，大/小图标各一次塞 QIcon），非 Windows 沿用 QFileIconProvider；系统调用收进
  `_SHELL_ICON_API` 惰性单例注入口（仿 `net_share._netapi()`），`SHFILEINFOW` 偏移按探针 dump
  （sizeof 696）。新增 `tests/test_type_icon.py` **7 条**，其中真 Win32 用例抓到两个假 API 用例
  盖不住的实现坑（常量漏 `_` 前缀、`QImage.fromHICON` 传 c_void_p 静默 null）；对照组换回旧实现
  **3 条红**、恢复全绿。文档：gotchas **#70**、CHANGELOG `[1.9.054]`。版本/pyproject/tag 已随本版同步。
- 2026-11-19 **跨 RDP 粘贴修复落地（1.9.053 的内容）**（用户「pan4dex 现在在复制粘贴上最大的问题，
  跨 rdp 复制，粘贴都不正常」→「修改，出版本」）。先只读探针把根因钉死：本机 `pan4dex.exe` 跑在
  **RDP-Tcp#0 / session 2**（一开始误判成 Linux xrdp 会话，`wmctrl -l` 与 `tasklist` 对照后当场更正），
  剪贴板里只有 `FileGroupDescriptorW`（596 字节 = 4 + 1×**592**，`cFileName` 在 **+72**，样本
  `SystemUI.html` / 1706 字节 / flags `0x4064` / attrs `0x20`）+ `FileContents` + `DropEffect`；
  裸 `GetClipboardData(FileContents)` 返回 **NULL** 而 Qt `mime.data` 拿到 **1706 字节**，
  真调 `Pane._system_clipboard_paths()` 得 **0 条路径** → `choose_paste_source([],None,[])` →
  静默 `return`。读取耗时 0.014–0.032s，排除「界面冻住」假设。日志侧也核了：
  `%APPDATA%\pan4dex\logs\pan4dex.log` 里 grep `paste|clipboard|剪贴|粘贴` **0 命中** ——
  这条路径以前一行日志都不写。修法 = 新增 `core/rdp_files.py`（纯执行层）+ 窗格一条虚拟文件分支，
  复制/冲突询问/进度/刷新全部复用；尺寸闸门提到取字节之前（否则 2GB 文件先读满会冻住界面）；
  远端剪切一律按复制；文件名消毒 + 字节数对账，不符整份拒绝。新增 `tests/test_rdp_clipboard.py`
  **54 条**（含结构体偏移守卫、独立偏移拼描述符、改前读法对照组），全量 **1042 passed / 5 skipped
  （104.90s）**；关掉修复的对照组红 **4** 条。文档：gotchas **#69**、待办 **T17**（多文件/文件夹/
  大文件同步读）、**T18**（反向未测）、**L18**（真机端到端，本轮剪贴板已空**没做成**）、
  功能表 12.13/13.4、CHANGELOG `[1.9.053] 未发布`、测试基线 988→1042。
- 2026-11-17 **两条待拍板事项出了逐项对比，并把 Linux 侧的前提实测了一遍**（用户「两种方式你对对比
  一下让我看看吧」）。上目标机 `linux230` 做**只读**探针（没装包、没挂载、没读写凭据内容、没碰同机的
  更新服务器），量到：系统是 **Ubuntu 24.04.5 LTS**（`kali` 只是用户名，`docs/testing.md` 那句「230 Kali」
  已更正）、Xfce 会话；gvfs SMB 后端齐全且 `gvfsd-smb` **自己链接 `libsecret-1.so.0`**、钥匙环服务
  `org.freedesktop.secrets` 在跑；`mount.cifs` 与 `secret-tool` **都缺**（`libsecret-1-0` 库在、命令不在）；
  本仓依赖树里 keyring/secretstorage/jeepney/dbus/cryptography **全 0 命中**；PyPI 实测 wheel
  SecretStorage 0.01 MB + jeepney 0.05 MB（均纯 Python）+ **cryptography 4.53 MB（带二进制，硬依赖）**。
  据此给钥匙环那道题补了**第三条路**（代挂载走 gvfs，口令可能根本不用我们存），建议先验它。
  列共享那道题核到行后确认：窗格数据源没有注入合成条目的口子，摆进窗格要改 4 处 `isdir` 门
  （`core/pane.py:1202/1303/848/1166`）+ `go_up` 语义，5–8 天；弹小框照现有搜索对话框形状 1–2 天，
  建议后者。**另实测更正一条自己差点写进对比的推测**：`\\主机` 与 `\\主机\共享` 两层的「返回上级」
  今天就是**空操作**（ntpath 把「服务器\共享」当盘符根，`dirname` 原样返回 → `path_bar.py:333` 的
  `parent != current` 守卫不发信号），不是先前以为的「给出 `\\` 被拒」。产出：设计稿 **§12**（两表 +
  被否决备选 + 已核对/待实测分列）、`docs/linux-gap.md` **§5.4**（能力表 + 4 条待实测各附自查命令与判据）、
  todo T15/T16 前置更新、testing 环境更正。**产品代码一行未动**，T15/T16 仍 🔴 待拍板。
- 2026-11-17 **1.9.052 出包并上传两平台**（用户「出 052」）。发布前置全量 **988 passed / 5 skipped
  （142.07s）**；`VERSION` 与 `pyproject` 同步 052、CHANGELOG「未发布」翻牌成 `2026-11-17（master）`。
  产物：Windows onedir 272,216,572 字节 → zip **116,601,561** 字节；Linux ELF **108,161,856** 字节
  （比 051 +23,096）。两平台 `--version` 均报 v1.9.052。**包内计数改用「同法对照上一版」**而不是拿
  旧文档数字比：`7z.exe`/`7z.dll`/`License.txt` 051 与 052 都是 0、`7zz` 都是 4、`exiftool-linux`
  都是 247，052 多出 `net_share` 1 条（051 为 0）—— 顺带纠正了旧记录里「`7zz` 计 1」的口径差异。
  Windows 侧另核：包内 `7z.exe` 实跑 7-Zip 26.04、`Analysis-00.toc` 含 `core.net_share` 与
  `widgets.net_credentials_dialog`、warn 文件对这两个模块 0 命中、`--info` 报 frozen True。
  上传 windows 11.0s / linux 10.1s（口令取自既有 gitignored `server/update-server/.env`，未打印、
  未写入任何入库文件）；服务器 version/size/SHA-256 与本地现算一致，**并把两平台产物真下载回来
  逐字节哈希核对一致**，临时副本当场删除；051/050 四个旧包 HEAD 200 且字节数原样。构建前用户
  自己关掉了正在跑的 `dist/pan4dex/pan4dex.exe`（PID 18348，与构建输出目录重合），**没有杀用户
  进程**；Windows 构建两条「Restored exiftool-linux / 7zz」日志都在，`config/_build_info.py` 已删。
  测试基线同步：`docs/testing.md` §5 与 `AGENTS.md` 改 **988**（原 903）。**L17 真机验收仍空**，
  故功能表 1.11 保持 🟡。
- 2026-11-16 **地址栏访问局域网共享（Windows 半边）落地**（用户「先出 windows 版本吧」）。新增
  `core/net_share.py`：`parse_unc()` 认写法 → `plan_open()` 编排「可达 → 静默重放已存凭据 → 匿名试探拿
  错误码」→ `retry_with_credential()` 带口令重连（**只有 1219 这一档先 cancel**）；错误码分档、
  「能不能问口令」的判据、状态栏文案各只有一处（`classify_error` / `may_ask_credentials` / `failure_text`）；
  系统调用只经 `_netapi()`/`_credapi()` 两个注入口出去，所以 offscreen 用例塞两个假 API 就能驱动整条链，
  不需要真共享。新增 `widgets/net_credentials_dialog.py`（只出 `username`/`password`/`remember` 三个属性，
  预填永不回填口令、非 Windows 上「记住」置灰）。接线在 `core/pane.py:_try_unc_path()`（偏离设计稿 §4：
  「正在连接」要在调用前上屏 + `processEvents` 一次，属窗格的事；`net_share` 保持不认识 Qt）+
  `_ask_share_credentials()` + `_set_share_status()`；顺带修了**地址栏输入打不开时不再抹回原路径**。
  新增 `tests/test_net_share.py` **85 项**（含 ctypes 结构体偏移守卫：`CREDENTIALW` sizeof 80 + 五个字段
  偏移 + `NETRESOURCEW` 48），三轮改前/改后对照组各有区分力，全量 **988 passed / 5 skipped（142.07s）**
  （旧基线 903）。凭据链路按项目规矩**跨进程**验：A 写 → 新起 B 读回 → 删 → 全库复点无残留；实现阶段
  新量到三条并写进 gotchas **#68**：`CredDeleteW` 对不存在条目回 1168 是幂等成功、空口令读回来 blob
  长度 0 是合法记录（guest 共享）、`GetFileAttributesW` 不设 `restype` 会把 `0xFFFFFFFF` 读成 -1 从而
  把「打不开」判成「是个目录」。文档销账：功能表 **1.11** 🟡、CHANGELOG 顶部 `[1.9.052] 未发布`（**版本
  号/pyproject/tag 都没动**，按规矩等出包那一刻）、`docs/architecture.md` 两条模块行、`AGENTS.md` 代码地图
  + 铁律新增第 11 条（ctypes 偏移要 dump 不要转写）、待办 **L17**（Windows 真机验收：探针阶段没碰用户的
  NAS，所以「连真共享」这一格是空的）/ **T15**（Linux 代挂载，前置 = 钥匙环依赖拍板）/ **T16**（列共享，
  前置 = `NetShareEnum` 只读探针）、设计稿新增 §11 实现回执（含列共享的编号从「L18」改为 T16 的更正）。
- 2026-11-16 **地址栏访问局域网共享：实现前的 API 事实全部量实并回写设计稿**（`docs/design-unc-share-access.md` §2.1 新增，§4.2/§4.3/§4.6/§4.7/§5.1/§5.4/§7/§8/§9/§10 就地改正；产品代码仍未动）。六轮探针（`tmp/netapi_probe2.py`–`netapi_probe7.py`，`tmp/` 不入库）推翻原稿四处：① `CONNECT_TEMPORARY` 不是 0x80 且真值 0x400 实测被 `WNetAddConnection2` 拒（87），`CONNECT_RECONNECT` 同样拒，**flags 只能给 0**，而实测 `flags=0` 本来就是一次性会话（`net use` 里连上时可见、`cancel` 后干净消失，不留 profile 条目）；② `NETRESOURCEW` 的 `dwScope=1`/`dwType=2` 取错（那是查询用的 `RESOURCE_CONNECTED` 和 `RESOURCETYPE_PRINT`），实测用 2/1/2/1；③ 同机会话已存在又换一套凭据回 **1219 MULTIPLE_PRIMARY_LOGONS**（原稿猜的 1208 没出现），「要凭据」档取到样本码 **86**（用本机回路 `\\127.0.0.1\C$` + 一个不存在的本地账号，故意不碰用户 NAS 以免踩账户锁定），`cancel` 不存在的连接回 **2250**、重复同参数连回 **0** 而非 85；④ **`CredWriteW` 对所有参数一律 87 的根因是手搭的 `CREDENTIALW` 少了一格 8 字节** —— 靠 `cmdkey` 写一条内容全已知的条目再按 8 字节一字 dump 原始内存才定位（x64 真实 `sizeof` 80：`LastWritten` 在 +24、`CredentialBlobSize` +32、`Persist` +48、`UserName` +72），修正后非提权进程 `Persist=1/2/3` 都写得进、**另起进程原样读回口令**（`Persist=0` 被拒），实落 `%LOCALAPPDATA%\Microsoft\Credentials`（`%ProgramData%` 侧目录都不存在），target 名带反斜杠/空格/中文/超 512 字符全部接受。另外查明：系统重定向器**不会**自动使用我们自己命名空间的凭据（本机 `Domain.target:` 前缀 0 条，用户既有的是 `ROUTE88`/`192.168.5.50`/`TERMSRV/…` 那种「按服务器名当键」的条目，本轮只读枚举、未改动），所以「静默重试」必须我们自己读 blob 再显式传给 `AddConnection2`；§7.1 相应补了**结构体偏移守卫用例**和第 9 条幂等/冲突分支。**探针动过的东西已核销**：本机回路 SMB 会话当场 `cancel`（收尾 `net use` 为空）、凭据库里 `pan4dex` 前缀的测试条目逐条删除 + 全库复点剩 **0 条**（中途有一轮脚本崩在 `ctypes.cast` 上，靠按自己前缀兜底清扫才敢报已清干净），没碰用户的 NAS/路由器、没往任何配置文件写字节。**同日 §9 四条决策全部拍板**并已记进文档：Windows 存凭据管理器 / Linux 存钥匙环、Linux 代挂载排在 Windows 之后（前置 = 目标机核实 SMB 后端）、`\\主机` 列共享改为顺带做（§5.4 否决作废，单独排期与单独一轮真机验收）、首次探测「显示正在连接 + 同步等一次」。
- 2026-11-16 **1.9.051 出包并上传两平台**，内容是 **T14 销账**（Linux 包不再整目录捎带 Windows 版 7-Zip）：构建脚本先把 `7zz` 以 `install -m 0755` 暂存到 `build/7z-linux-only/`，打包清单改指暂存目录，`7zz` 不在时删掉空目录以免日志说假话。判据用包内字节计数（不是体积猜）：`7z.exe`/`7z.dll`/`License.txt` **1 → 0**、`7zz` 仍 **1**、ExifTool 仍 **247**，Linux 产物 109,255,808 → **108,138,760** 字节。Windows 侧无回归（zip 116,579,022 字节，`Restored exiftool-linux`/`Restored 7zz` 都在）。新增 `tests/test_build_linux_docker.py` 8 条（每组规矩都配了改前对照组），全量 **903 passed / 5 skipped**。两平台 `--version` 均报 v1.9.051；上传走 `scripts/upload_release.py` → 配置里的真实地址（windows 12.6s / linux 11.5s），服务器 version/size/SHA-256 与本地逐字节一致，050/049 保持原样。顺带把「包内 `7zz` 到底有没有执行位」登记成 **L16 的第 7 项**（还没实测）。gotchas 新增 **#67**（两平台共用资源目录时清单不能取整目录、「存在才带」不能按目录判）
- 2026-11-16 清理文档里指向代码的过期行号：全仓 grep 到 12 处（11 处指 `main.py`、1 处指 `build-linux-docker.sh`），改成符号锚点（如 `main.py:_install_menu_linux`）并逐处核到实现；顺带把「原生图标兜底」一行的状态从「该加平台守卫」更正为已加（v1.9.015，代码 `main.py:95` 与 feature-checklist 对得上）；`CHANGELOG.md` 历史分节里的 1 处按惯例保留不动
- 2026-11-13 **1.9.050 出包并上传两平台**：Windows 构建仍用 `--distpath` 绕开正在运行的 `pan4dex.exe`（PID 9700，**没有动用户正在跑的程序**）；日志无缺工具警告、`Restored exiftool-linux`/`Restored 7zz` 都在、`build/` 无残留。两平台 `--version` 均报 v1.9.050，包内 `7z.exe` 实测能跑（7-Zip 26.04）。上传走 `scripts/upload_release.py` → 配置里的真实地址（linux 10.7s / windows 11.2s），服务器两侧 version/size/SHA-256 与本地逐字节一致，049 保持原样。提交 `1c1dbd2`/`de03ef1`/`b06792b` 已推送 master。新登记 **T14**（Linux 包多带 Windows 版 7-Zip，+1,115,840 B）
- 2026-11-13 **销账 T12/T13**：T12 把「还原临时移出的 Linux 二进制」挪进 `finally`，失败也还原（守卫用例 + 同一判据的改前/改后对照组 + 真造一次失败构建）；T13 给构建机部署本机 7-Zip 26.04 的 `7z.exe`/`7z.dll`/`License.txt`（与源 sha256 一致，未走外网），并新增缺工具警告。新增 12 条用例，全量 **895 passed / 5 skipped**。顺带按包内字节计数查清：**1.9.038–1.9.046 的 Linux 包一个 ExifTool 都没有**（036/037/049 各 247 个），已补记进 CHANGELOG 049 与 linux-gap
- 2026-11-13 **1.9.049 出包并上传两平台**：Windows zip 114,336,974 字节、Linux ELF 108,139,968 字节，服务器两侧核对一致，tag `v1.9.049` 已打并推送。出包过程踩到「Windows 构建失败不还原临时移出的文件」，导致第一次 Linux 包静默缺 ExifTool（101,097,672 字节 → 手工补救重跑 108,139,968 字节，+7.0 MB 就是观测量），据此登记 T12/T13 与 gotchas **#66**
- 2026-11-13 T6–T11 落地批：**T9 销账**（拍摄日期预读改有界池 2 + 代际守卫 + 批间取消）；T6 第一步（名称列比较器不再回模型取字符串，最差一轮停摆 540→359ms）、T7（Ctrl+End/Home 让选中跟着走）、T8（定位合一到 `core/reveal.py`）、T10（切回超大图标恢复网格）、T11（退出排空补齐所有池）代码与离屏用例闭环。新增 83 条用例，每条都跑对照组证明区分力；gotchas 新增 #60–#65，铁律补第 3 条、新增第 10 条；新登记 **L16**
- 2026-11-11 T6–T9 改进方案出文档：`docs/improvement-plan-t6-t9.md`（现场实测/判据/方案与被否决备选/铁律约束/测试计划/工作量）。更正登记时三条被推翻的说法，T9 实测确认更严重（峰值 17 线程）；新登记 T10/T11。**用户同日拍板**：T6 判据放宽为「单次停摆 < 0.4 秒 + 落地期间有忙碌提示」
- 2026-11-10 第二轮批量收尾：销账 T3；修用户操作配置层四处、状态栏改读模型（gotchas #59）、内容搜索伪文件防护（gotchas #58）、搜索停止文案、删除确认框默认按钮 Yes；登记 T6–T9；全量 **800 passed / 5 skipped**