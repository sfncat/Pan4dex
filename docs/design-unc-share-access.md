# 地址栏访问局域网共享（`\\主机\共享` + 首次要口令）—— 设计稿

> 状态：**待评审**（未动产品代码）。写于 2026-11-16，基于 1.9.051（`e8f7146`）。
> 评审意见请追加在本文件末尾，原文不删。
> 需求原话：「支持在地址栏里输入 `\\XX\Y` 访问局域网内其它机器的目录，如果是头一次，需要支持输入用户名、密码」。

---

## 1. 现场：今天输入 `\\XX\Y` 会发生什么

地址栏回车/下拉选中共用一条落点（`widgets/path_bar.py:298` `on_return_pressed`、`:304`
`on_item_activated` 只 emit `path_entered`；接住它的是 `core/pane.py:378` →
`core/pane.py:1197` `Pane.on_path_entered`）：

```python
if os.path.isdir(path):        # core/pane.py:1200
    self.navigate_to(path)
    self.tree_view.setFocus()
else:
    self.path_bar.set_path(self.current_path)   # :1207-1209 静默把旧路径填回去
```

**结论：可达的共享今天就能进**（`\\127.0.0.1\C$` 实测 `os.path.isdir` = True，见 §2），
不需要新代码。**不可达的一律「什么也不发生」** —— 没有错误提示、没有对话框，路径栏上的字
被旧路径覆盖掉，用户分不清是「打错了」「对方关机了」还是「要口令」。这就是这条需求真正缺的那一半。

再往里一层也补不上：`core/dir_model.py:259` `enumerate_dir` 把
`except (PermissionError, OSError)` 吞成 `return []`（`:280-282`），所以万一台层过了、
共享拒绝访问，用户看到的是**一个空目录**而不是「拒绝访问」。枚举跑在后台线程池
（`core/dir_model.py:293` `dir_pool`），**不能**在那里弹凭据框（铁律第 5 条）。

## 2. 实测：失败面有哪几种，各是什么码（2026-11-16，Windows 开发机）

探针：`tmp/net_share_probe.py`（只读，`GetFileAttributesW` + `GetLastError`，不挂载不写盘）。
`\\ROUTE88` 那三行是对用户自己局域网里那台设备的属性查询（该机在 `net use` 里已有一条
Disconnected 的持久会话），共 3 次查询、无写入。

| 输入 | `os.path.isdir` | GetLastError | 含义 |
|---|---|---|---|
| `\\127.0.0.1\C$` | **True** | 0 | 已授权时 UNC 直接可进（今天就能用） |
| `//127.0.0.1/C$` | **True** | 0 | 正斜杠写法等价，`ntpath` 已归一，不用特殊处理 |
| `\\127.0.0.1\IPC$` | False | 50 NOT_SUPPORTED | 命名管道共享不是目录 |
| `\\127.0.0.1\nosuchshare` | False | 67 BAD_NET_NAME | **主机在、共享名不对** |
| `\\bogus-host.invalid\share` | False | 53 BAD_NETPATH | **主机名解析不了 / 机器没开机** |
| `\\ROUTE88\IPC$` | False | 50 | 首次查询耗时 **2750ms**（见 §6.4） |
| `\\ROUTE88\nosuchshare` | False | 67 | 第二次只要 248ms |
| `\\ROUTE88`（只有主机名） | False | 161 BAD_PATHNAME | **裸 `\\主机` 不是目录**，必须带共享名 |
| `\\?\UNC\NAS\photo` | — | — | `win_is_remote` = **True**（send2trash 造出的形式也被判成远端） |
| `\\`（只有两个反斜杠） | False | — | `win_is_remote` = **True** —— 判据说是远端、但根本没法导航，`parse_unc` 必须把它拒在门外 |

判据侧已就位，不用新增：`core/mounts.py:168` `win_is_remote()` 对以上所有写法
（含 `\\?\UNC\`、`//`、裸 `\\`）都返回 True（实测），`is_remote_location()` 是全仓唯一入口
（铁律第 1 条），`core/pane.py:945` `_path_is_dir()` 与 `:969` 的「同一目录重复导航强制重扫」
已经吃到这个判据。

**样本边界（2026-11-16 第二轮之后更新）**：「共享存在、但要求凭据」这一档**本轮已经取到样本**，
但它是**本机回路 + 一个不存在的本地账号**（`\\127.0.0.1\C$` + `pan4dex-no-such-user`）——
对着用户的 NAS/路由器试错口令会踩账户锁定策略，**不做**。取到的码是
**86 ERROR_INVALID_PASSWORD**（只给用户名、或用户名+口令，两档都是它）。远机同一场景
还可能回 5 / 1326，所以 §4.3 那一档标成「86 已实测（本机回路样本）/ 5、1326 待真机」，
真机那一轮（§7.3 第 1 条）不能销账。

### 2.1 第二轮实测：连接与凭据 API（2026-11-16，探针 `tmp/netapi_probe2.py`–`netapi_probe7.py`）

目标机只有 `\\127.0.0.1`（本机自己的隐藏共享），不碰用户的 NAS/路由器；凭据库只写
`pan4dex` 前缀的测试条目，每轮当场删除并全库复点（收尾 `pan4dex` 前缀剩 0 条）。

**① `WNetAddConnection2W` 的 `dwFlags`（推翻原稿）**

| flags | 结果 | 结论 |
|---|---|---|
| `0x000` | 0，`net use` 当场出现 `OK \\127.0.0.1\C$`，`cancel(flags=0)` 后**列表里干净消失** | 默认就是**本次会话**，不写登录脚本 |
| `0x400` CONNECT_TEMPORARY | **87 INVALID_PARAMETER** | 这个 flag 在 `AddConnection2` 上**根本不能用**，原稿「默认走 CONNECT_TEMPORARY」作废 |
| `0x100` CONNECT_RECONNECT | 87 | 同上，不给用 |
| `0x008` / `0x010` / `0x800` | 0（与 `flags=0` 无差别） | REDIRECT/INTERACTIVE/COMMANDLINE 在这条路上是被忽略的，没有额外好处 |
| `0x080`（原稿猜的 TEMPORARY） | 487 | 原稿那个值是**未定义位**（487 是 `ERROR_INVALID_ADDRESS`，不是「参数不对」） |
| `0x020` / `0x040` 单给 | 87 | PROMPT / PROVIDER 必须配 `0x10`，单给被拒 |
| `0x401`（TEMPORARY\|UPDATE_PROFILE） | 87 | 互斥组合也直接被拒 |

→ 实现只能用 **`flags=0`**；「记住」记的是**凭据**不是**连接**这个结论不变，但理由换成了实测的：
不传 flag 本来就是一次性会话，无需 CONNECT_TEMPORARY 兜底。

**② NETRESOURCE 各字段取值 + 会话语义**

| 试的事 | 结果 | 用在哪儿 |
|---|---|---|
| `dwScope=2(GLOBALNET) dwType=0(ANY) dwUsage=1` | 0 | 原稿 §4.2 写的 `dwScope=1`、`dwType=RESOURCE_SHARE(2)` 是错的：1 是 `RESOURCE_CONNECTED`（查询用），2 在 `dwType` 位上是 `RESOURCETYPE_PRINT` |
| `dwType=1`（RESOURCETYPE_DISK） | 0 | 两种都能连，实现取 `1`（共享目录本来就是 disk） |
| 同参数**重复连**同一路径 | 0（不是 85） | UNC 不占盘符时 `ERROR_ALREADY_ASSIGNED(85)` 不会出现；分类表仍把 85 当成功，只是它不是主路径 |
| 同机连第二个共享 `\\127.0.0.1\ADMIN$` | 0 | 「同机会话复用」成立，第二个共享不再要口令 |
| 会话已存在时**换另一套凭据** | **1219 MULTIPLE_PRIMARY_LOGONS** | 原稿猜的 1208 没有出现；§4.3「凭据冲突」那一档改成 1219 |
| 用不存在的账号连（口令对/不给） | 86 | §4.3「要凭据」档 |
| 失败之后裸查 `os.path.isdir(UNC)` | True | 一次失败的 `AddConnection` **不会**把已有会话搞坏，可以放心重试 |
| `WNetCancelConnection2` 断一条没有的连接 | 2250 `ERROR_CONNECTION_UNAVAIL` | 「断开」按钮要把 0 和 2250 都算成功，否则用户第二次点就报错 |

**③ 凭据管理器：原稿的 ctypes 结构体是错的，已量实**

`CredWriteW` 对四种 `Persist`、有无 blob、target 带不带反斜杠**一律 87**，而 `cmdkey /generic`
同一台机写得进 → 不是 Windows 挑参数。用 cmdkey 写一条内容全已知的条目再按 8 字节一字 dump：

```
+0  Flags(0) | Type(1<<32)      +24 0x01dd75cbf67dc433  ← LastWritten（真时间戳在这）
+8  TargetName 指针             +32 28                  ← CredentialBlobSize（14 字符 utf-16）
+16 0（8 字节占位，原稿少了这一格）+40 口令 blob 指针   +48 Persist   +56 AttrCount
+64 Attributes(0)               +72 UserName 指针
```

→ x64 上 `CREDENTIALW` 实测 **80 字节**（`sizeof` 老写法 72），从 `LastWritten` 起整体后移一格；
原稿把时间戳低 32 位当成长度、把口令指针当成 `Persist` 递进去，校验必然不过。
按修正布局：`Persist=1/2/3` 都写得进、**另起进程能原样读回口令**（跨进程实测通过），
`Persist=0` 被拒（87）。`%ProgramData%\Microsoft\Credentials` 目录不存在而 `Persist=2` 仍写得进
→ 实际落在 `%LOCALAPPDATA%\Microsoft\Credentials`（DPAPI 保护，不是明文）。
target 名形态：反斜杠、空格、中文、512 字符以上、`<>|"?*` **全部接受**，长度原样读回。
本机已存的 SMB 类凭据走的是 `ROUTE88` / `TERMSRV/192.168.5.x` / `iStoreOS50` 这种
**「服务器名当键」**的命名空间，`Domain.target:` 前缀 0 条；我们写 `pan4dex:` 自己的键
**系统重定向器不会自动使用** → §4.3 那句「已有存好的凭据就先静默重试一次」必须由我们自己
读出来再显式传给 `AddConnection2`，不能指望 OS 代劳。


## 3. 目标 / 非目标

**目标**
1. 地址栏输入 `\\XX\Y`（含 `//XX/Y`）能直达局域网共享目录，可达时与今天一样直接进。
2. 不可达时**说清原因**（四类文案：口令 / 共享名 / 主机 / 权限冲突），不再静默回退。
3. 头一次需要凭据时，弹一个用户名/口令对话框；连接成功即进入目录。
4. 用户勾选「记住」时凭据可跨重启复用，**口令不明文落盘**（§5.1）。
5. 不破坏既有 SMB 优化：不挂 watcher、重复导航强制重扫、删除文案说「永久删除」。

**非目标（本轮明确不做，登记待办）**
- ~~裸 `\\主机` 列出该机所有共享~~ → **2026-11-16 拍板改为「顺带做」**，但排在 `\\主机\共享`
  这一半落地之后、单独一轮验收（§5.4 已就地改写）。
- 映射网络驱动器（分一个盘符）—— 本方案故意**不占盘符**（`lpLocalName=None`）。
- 在 Linux 上代用户挂载 CIFS/SMB：本版不做，**下一版做**（拍板：Linux 也一起做，但先等目标机
  核实有没有 gvfs 的 SMB 后端，§4.6 / §9 第 2 条）；形状与本功能不同（要 root 或依赖桌面环境）。
- 搜索/书签/拖拽等其它入口的凭据询问（只在地址栏这一条路径打扰用户，§4.5）。
- 用纯 Python SMB 客户端自己走协议（§5.2 否决）。

## 4. 方案形状

### 4.1 新增模块 `core/net_share.py`（唯一新后端）

三段，前两段是纯函数（任何主机都能测满），第三段才碰系统：

```python
parse_unc(path) -> (server, share, tail) | None   # \\SRV\sh\a\b → ("SRV","sh",r"a\b")；非 UNC → None
remote_name(server, share) -> str                 # 连接粒度 = 截到共享那一层 \\SRV\sh
classify_error(win_err) -> Symbol                 # 见 §4.3 表
is_reachable(path) -> bool                        # 一次 GetFileAttributesW，带耗时日志
connect(remote, user=None, password=None) -> (ok, win_err)   # flags 恒为 0（§2.1①）
cancel_connect(remote) -> (ok, win_err)           # 0 与 2250 都算成功
saved_credential(remote) -> (user, password) | None   # Windows 凭据管理器
store_credential(remote, user, password) -> bool  # 键 = f"pan4dex:smb:{server}\\{share}"，Persist=3
forget_credential(remote) -> bool
```

`core/mounts.py` 不动：它回答的是「慢不慢」，本模块回答的是「连得上吗 / 怎么连」。
两者唯一的交集是 UNC 形态识别，本模块**复用** `win_is_remote()`，不再写第二份
（否则就是 gotchas #43 那个坑）。

### 4.2 连接 API：`WNetAddConnection2W`（mpr.dll，ctypes）

```python
class NETRESOURCEW(Structure):
    _fields_ = [("dwScope", c_uint32), ("dwType", c_uint32), ("dwDisplayType", c_uint32),
                ("dwUsage", c_uint32), ("lpLocalName", c_wchar_p), ("lpRemoteName", c_wchar_p),
                ("lpComment", c_wchar_p), ("lpProvider", c_wchar_p)]
# 实测取值（§2.1②）：dwScope=RESOURCE_GLOBALNET(2)、dwType=RESOURCETYPE_DISK(1)、
#   dwDisplayType=RESOURCEDISPLAYTYPE_SHARE(2)、dwUsage=RESOURCEUSAGE_ALL(1)
# lpLocalName=None → 不占盘符；lpProvider=None → 系统自己选（这就是 SMB）
WNetAddConnection2W(byref(nr), password, user, flags)
# flags 只能是 0：CONNECT_TEMPORARY(0x400) 与 CONNECT_RECONNECT(0x100) 实测一律 87，
#   CONNECT_UPDATE_PROFILE(0x1) 能用但会把连接写进登录脚本（不是我们要的语义）
```

- **原稿这一段的三个常量都写错了**，按 §2.1 的实测改：`dwScope` 不是 1（`RESOURCE_CONNECTED`
  是查询用的）、`dwType` 不是 2（那是 `RESOURCETYPE_PRINT`）、`CONNECT_TEMPORARY` 不是 0x80
  而且**这个 flag 压根不能传给 `AddConnection2`**。
- 「持久」不再交给系统赌：实测 `flags=0` 连上时 `net use` 里只有一条 `OK` 的当次会话，
  `WNetCancelConnection2(remote, 0, True)` 之后**列表里干净消失**，不留用户看不见的僵尸映射；
  本机 `net use` 那句 `New connections will be remembered.` 是全局默认策略的提示，
  实测它**没有**把 `flags=0` 的这次连接记进 profile。勾「记住」记住的是**凭据**不是**连接**（§5.1）。
- 同机不同共享复用同一会话：连接粒度是 `\\server\share`，但会话按 `server` 计 ——
  这两条**都实测过**：会话存在时连同机第二个共享回 0（不再要口令），
  而**换另一套凭据**回 **1219 ERROR_MULTIPLE_PRIMARY_LOGONS**（原稿猜的 1208 没出现）。
  文案必须给「先断开这台机器上的旧连接」这一支，走
  `WNetCancelConnection2W(server\share, 0, True)` 再重连 —— 这是 Windows 的经典坑，不能只报「失败」。
- `cancel` 幂等：断一条根本不存在的连接回 **2250 ERROR_CONNECTION_UNAVAIL**，
  实现里 0 和 2250 都算断开成功（否则用户第二次点「断开连接」就看见报错）。
- 口令内存处理：从 QLineEdit 取出的字符串用 `bytearray` 承载给 API，用完置零；
  **已知限制**：Python 的 `str` 不可变、无法保证清零，所以本功能不吹「内存里也安全」，
  只保证不明文落盘（诚实记在 §6.5）。

### 4.3 错误码分类与文案（分类表是这张功能的脸）

| 类别 | 码 | 用户看到的文案 | 之后做什么 |
|---|---|---|---|
| 可达 | 0 | — | 直接导航，不打扰 |
| **要凭据** | **86 已实测**（本机回路 + 不存在的本地账号，§2.1②）；5 / 1326 / 1331 / 1335 **待真机** | 「`\\XX\Y` 需要用户名和密码」 | 弹对话框；若凭据管理器里有存好的，**我们自己读出来显式传**（系统不会代劳，§2.1③），无存过的才弹框 |
| 凭据冲突 | **1219 已实测**（同机会话已存在又换一套凭据）；1208 原稿的猜测未出现 | 「这台机器上你已经用另一个账号连过 `\\XX`」 | 对话框里给「断开旧连接后重试」，实测 `cancel` 之后重连能成 |
| 已经连着 | 85 / 重复同参数连回 **0**（实测 85 在 UNC 不占盘符时不出现） | — | 两个都算成功，直接导航 |
| 共享不存在 | 67 / 53? 之 67 | 「`XX` 上没有名为 `Y` 的共享」 | **不弹**对话框（弹了只会让人改口令，其实是名字打错） |
| 主机找不到 | 53 / 1222 / 1231（后两码**未实测**） | 「找不到 `XX`，检查机器是否开机、网络是否通」 | 不弹对话框 |
| 不是目录 | 50 / 161 | 裸 `\\XX` → 「请到共享这一层，例如 `\\XX\photo`」；`IPC$` 类 → 通用失败 | 不弹对话框 |
| 未知 | 其它 | 「连不上 `\\XX\Y`（系统错误 N）」把码带上 | 不弹对话框 |

**规矩：只有「要凭据 / 凭据冲突」两档才弹模态框。** 其余一律状态栏 + 路径栏保留用户刚输入的字
（现在那句「路径无效时不抢焦点」已经是规矩，`core/pane.py:1208` 的注释写着，见 CHANGELOG
0.9.7xx 那节焦点坑）。理由：弹框是把「猜」的成本转嫁给用户，名字打错时只会更烦。

### 4.4 新增对话框 `widgets/net_credentials_dialog.py`

- 标题带远端名：`连接 \\ROUTE88\photo`；副标题说明「凭据只用于建立本次 SMB 会话」。
- 三行：域或计算机（可选，`DOMAIN\user` 也能填在用户名里，不额外加控件）、
  用户名、口令（`QLineEdit.EchoMode.Password` + 一个「显示」勾选，全仓现在**零**处口令输入，
  实测 grep `EchoMode.Password` 无命中）。
- 一个勾选：「记住这台机器的凭据」→ 只写 Windows 凭据管理器。
- 首次打开时用户名从凭据管理器的 `UserName` 预填（**不预填口令**，除非用户按下连接前不动那栏 ——
  简化为：预填用户名，口令留空，勾「记住」状态跟随是否已存在凭据）。
- 「断开连接」按钮（次要按钮）：调 `cancel_connect`，给 **1219** 那一支和「换账号」用
  （实测 `cancel` 回 0 或 2250 都算断开成功，按钮可以反复点）。
- 取消 = 什么都不发生，焦点回路径栏，用户输入的原字保留。
- 无入口不落地（铁律第 9 条）：这个对话框由 §4.5 那条唯一入口当场接上，不留孤儿模块。

### 4.5 接线点：只在 `Pane.on_path_entered` 的**失败分支**里加一段

```python
def on_path_entered(self, path):
    if os.path.isdir(path):                      # 保持现状那一行（core/pane.py:1200）
        ... 原样：导航 + tree_view.setFocus() ...
    else:
        handled = net_share.try_open_unc(path, self)   # 新：非 UNC 直接 False，零成本
        if handled:                              # 已连上并导航成功
            return
        self.update_status_bar(net_share.failure_text())   # 新：说清是哪一类失败
        self.path_bar.set_path(self.current_path)          # 保持今天的行为：文字回退、焦点留在输入框
```

两行说明：
- **不改用 `_path_is_dir()`**（`core/pane.py:945`）。那条会先查模型已加载条目再回退 `isdir`，
  是给「进入子目录/返回上级」这类**本来就可访问**的路径省往返的；地址栏这一趟要的就是
  「新鲜地问一次系统」，缓存命中反而会把「刚掉线的共享」判成可进。改它得另立理由，不夹带。
- `failure_text()` 必须在**每次** `try_open_unc` 开头复位，不能靠「上一次失败还挂着」这种守卫
  （铁律第 8 条 / gotchas #55 那一类：复位动作被空守卫静默跳过）。

**为什么不放在 `navigate_to`（`core/pane.py:963`）**：`navigate_to` 还被双击进入子目录
（`:1234`）、内嵌树点击、后退/前进、书签、搜索结果 `widgets/advanced_search.py:732` 调用。
那些路径的父级本来就可访问，不该问口令；更麻烦的是它们里有从后台/批量路径过来的，会把
模态框带进铁律第 5 条的风险面。**需求本身说的是「地址栏里输入」**，落点就照这个尺寸做。

### 4.6 Linux 侧（本版只做到「认出来 + 说人话」）

`\\XX\Y` 在 Linux 上不是可遍历路径。`core/mounts.py:118` `posix_is_remote()` 能判
**已经挂好的** CIFS/SMB 挂载点（`/mnt/nas`、gvfs 的 `smb:` 之类），也就是说
**Linux 上「已挂载的共享」本来就能进**（无实测，登记真机项）。缺的是没挂载时的引导：

```python
if not is_nt:  # POSIX 分支
    文案 = "Linux 上请先用系统把共享挂上（GNOME：文件管理器 → 其他位置 → smb://XX/Y）；
            挂好后把挂载点路径填在这里，例如 /run/user/1000/gvfs/smb-share:server=XX,share=Y"
```

不在本版做代挂载的三个理由：`mount.cifs` 要 root（会引入提权，形状完全不同）；
gvfs 只有装了才在（这台机上是否装了 `gvfs` 未实测）；`gio mount smb://` 是异步的，
要等 `gio mount --list` 出结果再导航，这条异步链路是第二个功能而不是本功能的尾巴。
→ 记成待办 `T15`（P3）。**2026-11-16 拍板**：Linux 代挂载**要做**，但排在 Windows 之后，
前置条件是目标机核实「装了什么 SMB 后端」（`gio mount smb://` 能不能用、有没有 gvfs），
口令那一半定的是**交给系统钥匙环**（§9 第 1 条）。

### 4.7 凭据读写：结构体是这段唯一容易写错的地方（照 §2.1③ 的实测布局）

```python
class CREDENTIALW(Structure):          # x64 实测 sizeof=80；网上抄来的写法是 72，会全盘 87
    _fields_ = [("Flags", DWORD), ("Type", DWORD),
                ("TargetName", LPWSTR),
                ("_unknown", c_void_p),        # ← 就是这一格，wincred.h 的常见转写漏了它
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", DWORD), ("CredentialBlob", POINTER(c_byte)),
                ("Persist", DWORD), ("AttributeCount", DWORD),
                ("Attributes", c_void_p), ("TargetAlias", LPWSTR), ("UserName", LPWSTR)]
```

三条实现约束（都有实测出处，不是风格问题）：
1. **读回来的字段要先验再看**：`CredentialBlobSize <= 5120` 且 `Persist in (1,2,3)`，
   不满足就当作「读不出」走弹框。这条是防「哪天 Windows 换了布局」把口令读成乱码再传给
   `AddConnection2`（§2.1③ 里那串 1433199856 就是错位读出的样子）。
2. **口令缓冲区必须活到调用结束**：`CredentialBlob` 指的是我们自己 `bytearray` 的内存，
   ctypes 不持有所有权，函数返回就悬空（实测把 buffer 存进模块级 `keep` 之后才稳定）。
   用完置零，且**口令不进日志**（§7.1 第 4 条用 `caplog` 断）。
3. **`CredFree` 只管 `CredReadW`/`CredEnumerateW` 给的指针**，我们自己构造的结构体不能交给它。



## 5. 决策点（每个都附被否决的备选）

### 5.1 「记住」的口令存哪 —— **需要拍板**

| 选项 | 做法 | 评价 |
|---|---|---|
| **(A) Windows 凭据管理器**（建议，已实测可行） | `advapi32.CredWriteW/CredReadW/CredDeleteW`，`CRED_TYPE_GENERIC`，`TargetName = f"pan4dex:smb:{server}\\{share}"`（连接粒度到共享那一层，所以键也到那一层），`Persist=3 ENTERPRISE`，口令是 blob | **非提权进程写得进、另一个进程能原样读回**（§2.1③ 实测）；实落 `%LOCALAPPDATA%\Microsoft\Credentials`，DPAPI 保护不是明文；用户可在「凭据管理器」里看到并删掉；与「机密禁止进配置文件」一致；不新增依赖。代价是 ctypes 结构体必须按 §4.7 那份偏移写 |
| (B) 只记在本次运行的内存里 | 会话表 `dict` | 最保守，但重启就要重输，「头一次才问」的诉求只满足一半 |
| (C) 写进 `user_operations.json` 同级的 JSON | 明文 | **否决**：口令明文落盘；`.gitignore` 不算安全措施（本项目已有这条规矩） |
| (D) 交给系统弹框 `CredUIPromptForWindowsCredentialsW` | 系统样式对话框 | **不推荐**：样式与产品不一致、「记住」语义不受我们控制（它会连**连接**一起持久化）、文案改不动；但它是「一行代码都不用写」的备选，如果只想最省就先 D，接受 UX 差异 |

建议 **A**，并且把「记住」默认**不勾**。 → **2026-11-16 拍板：就按 A**（Windows 凭据管理器，
默认不勾），Linux 那一侧对应「系统钥匙环」（§4.6、§9 第 1 条）。

还有一档实测后才冒出来的备选，一并否决掉：**用系统自己的命名空间当键**（`TargetName` 直接写
服务器名，就是本机凭据管理器里已经存在的 `ROUTE88` / `192.168.5.50` 那种形态）。好处是重定向器
会替我们做静默认证；否决理由是①我们会写进与「资源管理器 / `net use /savecred`」共用的那条记录，
用户改口令或删掉时行为不可预期，②系统那套按 **server** 计，我们的连接按 **server\share** 计，
键粒度对不上。代价说清楚：走 A 之后**系统不会自动使用我们的键**（§2.1③ 实测 `Domain.target:` 前缀
0 条、我们的 `pan4dex:` 键不在它查找范围内），所以「已有存好的凭据就先静默重试」那一步是
**我们读出凭据再显式传给 `AddConnection2`**，一次 API 调用而已，但别指望 OS 代劳。

### 5.2 协议层：**否决**纯 Python SMB 客户端（`smbprotocol` 一类）

全仓的数据源是「路径字符串 + `os.scandir`」（`core/dir_model.py:233`、预览、图标、
压缩、删除、回收站、监视、`core/reveal.py` 全都拿路径当参数）。换成自绘协议层意味着
每一条都要多一个「这条路径是模型里的还是 SMB 会话里的」分支，还要重做排序/缓存/TTL/取消。
收益只有「不用系统凭据」，代价是整个 I/O 层。走系统连接层（A）后，
`\\XX\Y` 就是一个普通路径，上述所有模块**一行都不用改**。

### 5.3 **否决**子进程 `net use \\XX\Y /user:...`

要把用户名和口令拼进命令行：口令会出现在进程命令行（别的进程读得到）、`&`/引号要做转义
（刚在 `config/user_operations.py` 上修掉的就是同一类坑）、`windowed` 产物里 `net.exe` 弹窗
会闪一下（本项目的控制台释放逻辑 `main.py:free_console_in_gui_mode` 也救不了它）。
ctypes 一次调用把这四件事全部省掉。

### 5.4 「此电脑 / 列出某机所有共享」：原稿否决，**2026-11-16 用户拍板改为「顺带做」**

原稿这段的理由**照抄留档**：裸 `\\主机` 实测是 161 BAD_PATHNAME，要 `NetShareEnum` +
一个新的列表视图，是另一条功能线（`docs/linux-gap.md` §2.3 已 🔴 挂着）。混进来会把
「地址栏能进共享」这件小事拖成两周。

拍板结论覆盖它，所以这段从「否决」改成「**范围追加，单独一节排期**」，落地形状：
- 输入只到 `\\主机`（没有共享名）时不再报「请到共享这一层」，而是 `NetShareEnum(server)`
  列该机共享 → 一个列表视图（复用窗格还是新对话框**待定**，待定项就是这条追加的主要成本）。
- 它要**同一套凭据链路**（§4.2/§4.3），所以放在本功能的**下一步**，不抢本版落地点。
- 真机验收**单独一轮**（§7.3 那张表不因此变长，另登记 L18）；`\\主机\共享` 那一半的验收
  不依赖它，可以先出包。
- 未实测的点：`NetShareEnum` 的缓冲区/`ResumeHandle` 语义、权限不足时回哪一档码（本机回路
  探针只测到 `isdir` 层面的 161），动手前先补一轮探针，别照文档旧话写。

### 5.5 决策：**首次可达性探测留在主线程**（可独立评审地反对，见 §6.4）

`is_reachable()` 是同步的（实测首次 2750ms）。选项：
- (a) 主线程同步探测 + 先让出一帧 + 状态栏「正在连接…」（建议，最小侵入）
- (b) 探测挪到 `dir_pool`，结果用信号回投（`core/lifecycle.py:call_later`），完成后再决定弹不弹框
- (c) 什么都不显示，直接同步（今天的观感，最差）

(b) 更「正确」但要求对话框只在 UI 线程弹，多一层状态机；本功能第一次落地上 (a) 够用，
并且把 (b) 记成 T15 的兄弟待办。

## 6. 铁律逐条对照

1. **#43（慢位置判据只有一份）**：本模块复用 `mounts.win_is_remote()`，不新增 UNC 识别分支；
   平台两端都有真实分支（§4.6），失败一律退化成代价最小的一侧（原静默回退）。
2. **#23/#12（六条监视约束）**：`\\XX\Y` 现在被 `is_remote_location()` 判成远端，
   watcher 本来就不挂 → 无新增风险。要防的是**新**风险：凭据框不能从监视回调里弹（不会，入口只有地址栏）。
3. **#29/#30/#60（比较器不碰磁盘）**：不受影响 —— 不改比较器。
4. **#28（Qt 对象生死）**：对话框是模态 `exec()`，用完留引用；不新增 `removeTab` 类操作。
5. **#17/#20/#21/#22（后台→UI 投递）**：凭据框**只在主线程的 `on_path_entered` 里弹**，
   绝不从 `enumerate_dir` 抛；`update_status_bar` 的失败文案走同一对象直调，不建闭包。
6. **#47/#49（快捷键与点击落点认 `target_pane()`）**：地址栏信号本来就由窗格自己接（`:378`），不涉及。
7. **#50（怎么说=怎么做）**：网络位置的删除文案已有判据，本功能不改删除链路。
8. **#55（`if 集合:` 守卫吞复位）**：`connect()` 的失败路径必须复位「上次失败类别」，
   不能靠集合非空守卫（用例覆盖 §7.1 第 6 条）。
9. **#56（新 UI 必须带入口 / 跑不完就是跑不过）**：对话框当场接上；发布前完整 `tests/` 出汇总行。
10. **#64/#65（线程池登记 / `sip.isdeleted`）**：不新增池（沿用 `dir_pool`）；若走 §5.5(b) 才要登记。

## 7. 测试计划

### 7.1 离屏可测（新增 `tests/test_net_share.py`，纯函数 + 假后端）

1. `parse_unc`：`\\SRV\sh\a`、`//SRV/sh`、`\\SRV\sh\`（尾斜杠）、含空格共享名 `\\NAS\My Docs`、
   中文共享名、`\\?\UNC\NAS\sh`（send2trash 形式，**要能识别但不当作用户可连接的 remote_name**）、
   `C:\x`/`/mnt/x`/`\\`/`` 非 UNC → None。
2. `classify_error`：§4.3 每档一条；重点是 **67/53 落在「不弹框」**、5/86/1326 落在「弹框」。
3. `connect` 的 ctypes 结构体断言（monkeypatch 模块级 `WNetAddConnection2W`，
   检查传入的 `dwScope==2`、`dwType==1`、`dwUsage==1`、`lpLocalName is None`、
   `lpRemoteName` 截到共享那一层、**`flags` 恒为 0**）—— 原稿这里写的是「`dwType==2`」和
   「`CONNECT_TEMPORARY` 与 `CONNECT_UPDATE_PROFILE` 的选用」，两处都被 §2.1 推翻，
   用例照实测值断，别照文档旧话断。注意 gotchas 里「monkeypatch 拦不到虚方法」那条，
   这里拦的是模块级可调用对象，可行。
4. 凭据读写：假 `CredWriteW/CredReadW`，断言 `TargetName` 形状（`pan4dex:smb:SRV\sh`）、
   `Persist==3`、blob 长度=口令 UTF-16 字节数、口令不出现在任何日志行（`caplog` 断言无该子串）。
   **另加一条真结构体守卫**（不碰系统，只算偏移）：`sizeof(CREDENTIALW)==80`、
   `getattr(CREDENTIALW, "LastWritten").offset==24`、`CredentialBlobSize==32`、
   `CredentialBlob==40`、`Persist==48`、`UserName==72` —— §2.1③ 就是靠这组偏移才定位到 87，
   布局写错时这条用例必须红，而不是等真机上「连不上」。
5. `Pane.on_path_entered` 接线：假后端返回「要凭据」→ 断言调用对话框一次、成功后导航到该路径、
   焦点回列表；返回「共享不存在」→ 断言**没弹框**、状态栏有那句话、焦点留在输入框、
   路径栏文字回退（三条都要断，这是铁律 #8 那类「文案改了行为没改」的反向守卫）。
6. 复位守卫：连续两次失败（第一次「要凭据」、第二次「主机找不到」）→ 第二次不许复用第一次的类别。
7. `grep` 式守卫用例：断言 `core/pane.py` 里出现 `net_share.`（铁律第 9 条「不许留孤儿组件」）。
8. 对话框自身：口令框 `EchoMode.Password`、「显示」切换改 echo mode、取消不调用 `connect`。
9. 幂等与冲突分支（实测回来的三档）：`connect` 回 **0/85** 都算成功；`cancel` 回 **0/2250**
   都算断开；回 **1219** 时分类到「凭据冲突」并且**允许**「断开后重试」那一步再走一次
   `connect`（重试路径不能复用第一次的失败类别，与第 6 条同一件事的两个方向）。

### 7.2 改前/改后对照组（本项目的硬规矩）

每组新用例都要在「把 fix 关掉」的插件里红一次（`tmp/` 里 pytest 插件，收集结束时把产品代码
还原成旧样子），否则观测量没有区分力 —— T11 第一版就是假绿（gotchas #65）。本轮至少要
覆盖 §7.1 第 5、6、7 条三组。

### 7.3 真机验收（登记成 `docs/todo.md` 的 **L17**，与 L16 并成一轮）

| # | 验的事 | 判据 |
|---|---|---|
| 1 | **§2 剩下的样本边界**：找一台**远机**要口令的共享（用户自己的 NAS，允许 2–3 次错口令） | 错口令的码落在「要凭据」档（本机回路实测是 86，远机可能是 5/1326）、文案正确、**不触发账户锁定** |
| 2 | 首次输入 `\\XX\Y` → 弹框 → 正确口令 → 直达目录 | 列表条目数与 `net use`/资源管理器一致；无静默空目录 |
| 3 | 勾「记住」后**重启程序**再输入同一共享 | **不弹框**直接进（这一条同时验 §4.7 的结构体布局与跨进程读回）；凭据管理器里能看到 `pan4dex:smb:XX\Y` 一条，删掉它之后要重新问 |
| 4 | 同机第二个共享 + 故意换账号 | 第二个共享**不重复要口令**（本机回路实测回 0）；换账号那一次要看见 **1219**，文案给「断开旧连接后重试」且真的重试成功 |
| 5 | `\\ROUTE88`（只主机名） | 文案指到共享那一层，不弹框 |
| 6 | 对方关机 | 「找不到主机」文案，不弹框，UI 不卡死超过一次探测 |
| 7 | 连上 SMB 后回归既有行为：列表不闪、外部改动靠 F5、删除文案说「永久删除」 | 与改前三条一致（判据未因新入口而漏） |
| 8 | Linux：已挂载的 CIFS/gvfs 共享能进；未挂载时文案指路 | 文案出现，不崩；「代挂载」不在本版 |

## 8. 工作量

| 块 | 估 | 说明 |
|---|---|---|
| `core/net_share.py` 纯函数 + 错误码表 + 假后端 | 0.5 天 | §7.1 第 1–2 条同步写 |
| ctypes 连接/取消 + 凭据读写 | 0.5 天 | 结构体与清零那几行要细抠 |
| 对话框 + 地址栏接线 + 文案 | 0.5 天 | §4.5 那一段的分支最多 |
| Linux 识别与指路文案 | 0.2 天 | 不代挂载 |
| 用例 + 三组对照组 + 全量门 | 0.5 天 | 出汇总行为止 |
| 文档销账 | 0.3 天 | 清单新增 **1.11**（地址栏 UNC 共享访问）+ 2.x 关联行、CHANGELOG 攒着那节、`docs/architecture.md` 模块表两行、todo 新行 T15/L17、gotchas 新条（**ctypes 手搭结构体偏移要 dump 出来别照头文件转写**、凭据冲突是 **1219** 不是 1208、主线程探测耗时） |
| **合计** | **约 2.5 天** | 不含真机那一轮（需要人在机器前） |
| （追加）`\\主机` 列共享 + 列表视图 + `NetShareEnum` 探针 | **另加 1–1.5 天** | 2026-11-16 拍板顺带做；不计进上面 2.5 天，因为它有自己的验收轮（L18）和一个待定形状（列表放哪儿）。上面「文档销账」那行的工作量按追加后口径已含在 2.5 天内，不含追加部分 |

## 9. 需要你拍板的（大白话）

> **2026-11-16 已全部拍板**，四条的答复就地写在每条后面（原文不删）。

1. **口令存哪**：建议存进 **Windows 凭据管理器**（系统帮你加密，你能在「凭据管理器」里看到并删；
   本机已实测：非管理员进程写得进、重启后另一个进程能原样读回）；「记住」默认不勾。
   要更保守就选「只记在本次运行里，重启就得重输」。不建议存进配置文件。
   → **拍板：Windows 存凭据管理器，Linux 交给系统钥匙环**。第一轮答复是「linux 怎么办」，
   追问后定的是这条。Linux 侧的落地形态（`SecretStorage` D-Bus 还是 `libsecret`、要不要为此
   新增依赖）跟 §4.6 一起推迟，**本版只做 Windows 这一半**。
2. **Linux 要不要一起做**：本版建议只做「认出写法 + 告诉你去哪挂载」，真正代挂载另立待办
   （要么提权要么依赖桌面环境）。
   → **拍板：Linux 也一起做代挂载，但排在 Windows 之后** —— 它拦在一条未实测前提上
   （目标机到底有没有 gvfs 的 SMB 后端），定的是「先 Windows 做完，Linux 待目标机核完再做」。
   所以 §4.6 那句「本版不做代挂载」读作「**本版不做、下一版做**」，待办 **T15** 编号不变、
   状态从「不做」改成「已排期」。
3. **要不要顺带支持只输 `\\主机` 就列出所有共享**：建议不做，那是「网络邻居」另一条功能线。
   → **拍板：顺带做**（答复原文「顺带做：列出该机所有共享」）。§5.4 的「否决」因此作废，
   已就地改写成「范围追加 + 单独排期」：要 `NetShareEnum` 加一个共享列表入口，
   **不和本功能共用同一轮真机验收**（工作量另算，见 §8 末尾）。
4. **首次访问一台机器要等约 2.7 秒（实测）**，期间界面会短暂没反应。
   建议这版先显示「正在连接…」并让它等一次；彻底挪到后台再单独排期。
   → **拍板：显示「正在连接」并同步等一次** —— §5.5 取 (a) 案，(b) 挪后台那条继续挂待办。


---

## 10. 评审区（意见请追加，不要删原文）

- 2026-11-16 待评审。
- 2026-11-16（同日第二轮实测，探针 `tmp/netapi_probe2.py`–`netapi_probe7.py`，结果全在 §2.1）：
  原稿**推翻四处**，均已就地改正——
  ① `CONNECT_TEMPORARY` 不是 0x80 且 0x400 实测被拒（87），`flags` 只能给 0；
  ② `NETRESOURCEW` 的 `dwScope`/`dwType` 取错了（1 是查询用的 `RESOURCE_CONNECTED`、
  `dwType=2` 是打印机类型），实测用 2/1/2/1；
  ③ 凭据冲突是 **1219** 不是 1208，「要凭据」档拿到了样本码 **86**（本机回路 + 不存在账号），
  `cancel` 的 2250 与重复连接的 0 也要按成功处理；
  ④ **`CREDENTIALW` 手搭的布局整体少了一格 8 字节**（`wincred.h` 的常见转写照抄下来
  `sizeof` 是 72，本机真实是 80）——`CredWriteW` 因此对每种参数都回 87，
  是 dump 出原始内存才定位到的；§4.7 给了修正布局与偏移守卫用例。
  实测还新增两条设计约束：系统**不会**自动使用我们自己命名空间的凭据（`Domain.target:` 前缀
  本机 0 条），所以「静默重试」要我们读出 blob 再显式传；`Persist=1/2/3` 非提权都写得进、
  跨进程能读回，实现取 **3**（与 `cmdkey` 一致），`Persist=0` 被拒。
  探针动过的东西只有本机回路的 SMB 会话（当场 `cancel`，`net use` 收尾已空）和凭据库里
  `pan4dex` 前缀的测试条目（逐条删除 + 全库复点，剩 0 条），没碰用户的 NAS/路由器、
  没往任何配置文件写字节。
- **仍等用户拍板的只剩 §9 那四条**；其中第 1 条（口令存哪）现在有了实测背书：A 可行。
- 2026-11-16 **§9 四条已全部拍板**，答复就地写进 §9，受影响的 §3 非目标 / §4.6 / §5.1 / §5.4
  与 §8 已同步改正：口令 Windows 存凭据管理器、Linux 存钥匙环；Linux 代挂载要做但排在
  Windows 之后（前置 = 目标机核实 SMB 后端）；`\\主机` 列共享**改为顺带做**（原 §5.4 的否决作废，
  单独排期 + 单独一轮真机验收 L18）；首次探测按「显示正在连接 + 同步等一次」落地。
  下一步是写 `core/net_share.py`（§4.1–§4.3、§4.7 全部照实测值，别再照旧文档的常量）。

---

## 11. 实现回执（2026-11-16，Windows 半边已落地）

用户拍板「先出 windows 版本吧」，本节记**实际落地的形状**与对设计稿的偏离。上面的评审原文一字未删。

**落地的文件**：`core/net_share.py`（后端，§4.1–§4.3/§4.7 的常量全按 §2.1 实测值）、
`widgets/net_credentials_dialog.py`（口令框）、`core/pane.py`（地址栏接线：`_try_unc_path()` +
`_ask_share_credentials()` + `_set_share_status()`）、`tests/test_net_share.py`（85 项）。
文档销账：功能表 **1.11**（🟡，真机那一半未做）、`CHANGELOG.md` 顶部 `[1.9.052] 未发布` 一节、
gotchas **#68**、待办 **L17**（Windows 真机验收）/ **T15**（Linux 代挂载）/ **T16**（列共享）。

**与设计稿的偏离（一处，是改好不是改坏）**：§4 把编排入口写成 `net_share.try_open_unc()`，
实际落在 **`Pane._try_unc_path()`**。理由是「正在连接」这句提示要在**调用之前**就上屏并
`processEvents` 一次，而 `QApplication` 与状态栏都属于窗格；让 `net_share` 保持不认识 Qt，
它才真的能被 offscreen 用例用两个假 API 驱动完整条链路（§6 的铁律 #5/#9 也是这个意思）。
`net_share` 对外只留 `plan_open()` / `retry_with_credential()` 两个编排函数 + 一组纯函数。

**实现阶段新增的三条实测**（§2.1 那批没覆盖到）：
① `CredDeleteW` 对**不存在的条目**回 `ERROR_NOT_FOUND(1168)` —— 按失败处理会让「忘记凭据」
永远报错，它是幂等成功；② 空口令写得进凭据库，但读回来 `CredentialBlobLength == 0`，
原先的 blob 形状守卫把它当损坏记录丢掉了，现在 `read()` 对 size 0 返回 `(user, "")`
（guest 共享的合法凭据）；③ `GetFileAttributesW` 不显式设 `restype` 时按 `c_int` 取返回值，
`INVALID_FILE_ATTRIBUTES(0xFFFFFFFF)` 变成 **-1**，`is_dir` 于是把每个「打不开」都判成
「是个目录」——可达性判定全线说谎且不抛错（gotchas #68 第 2 条）。

**验收口径**：全量 `tests/` **988 passed / 5 skipped**（旧基线 903 + 本次 85；2026-11-17 出 052 前重跑全量门 **142.07s**）；
对照组三轮（把修复逐条拆掉 → 对应用例变红 → 当场改回并复跑）。口令链路是**跨进程**验的：
A 进程写、新起 B 进程读回、删除、再全库复点无残留（`tmp/net_share_cred_roundtrip.py`）。
探针依旧只用 127.0.0.1 的隐藏共享，没碰用户的 NAS、没试真实账号的错口令、没往配置文件写字节。

**还空着的**：§7.3 的 Windows 真机验收（→ L17）、Linux 代挂载（→ T15，前置是钥匙环依赖拍板）、
`\\主机` 列共享（→ T16，前置是 `NetShareEnum` 的单独一轮只读探针）。
**编号更正**：§9/§10 里给列共享预留的「L18」最终按 **T16** 登记——它是代码层能闭环的实现项，
`L` 系列留给真机（§10 原文保留不动）。

**出包回执（2026-11-17）**：本功能随 **1.9.052** 出包并上传两平台（用户「出 052」）。发布前置全量
**988 passed / 5 skipped（142.07s）**；Windows zip 116,601,561 字节、Linux ELF 108,161,856 字节，
两平台 `--version` 均报 v1.9.052。冻结产物侧另核了三件：`build/pan4dex/Analysis-00.toc` 里
`core.net_share` 与 `widgets.net_credentials_dialog` 都在（源码路径 + 模块名各一条）、
`warn-pan4dex.txt` 对这两个模块 **0 命中**、Linux ELF 里 `net_share` 字节串 **1** 条（051 为 0）
—— 即「新代码真进了两平台的包」，不是只在源码树里。服务器侧不止比元数据：把两平台产物
**真下载回来逐字节哈希核对一致**，051/050 四个旧包 HEAD 200、字节数原样。
**§7.3 的真机验收（L17）仍然空着**：出包不等于验过，功能表 1.11 因此保持 🟡。

## 12. 两条待拍板事项的对比（2026-11-17，附本轮实测）

用户要求「两种方式你对对比一下让我看看吧」。本节把两道题各自的选项摊开，每条主张附出处。
**Linux 侧的能力事实全部来自本轮 ssh `linux230` 的只读探针**，完整表（已核对 / 待实测 + 自查命令）
在 `docs/linux-gap.md` §5.4，本节不复制，只引用结论。Windows 侧的代码事实逐处核到行。

### 12.1 Linux 的口令存哪：加 Python 依赖 vs 调系统命令

**先说一件实测改写了前提的事**：目标机上 gvfs 的 SMB 后端齐全（`/usr/libexec/gvfsd-smb` 在且可执行），
钥匙环服务也在跑（`org.freedesktop.secrets` 有主），而且 **`ldd gvfsd-smb` 里有 `libsecret-1.so.0`**
—— 后端自己就会用钥匙环。于是这道题多出第三个选项，而且它可能让前两个都不用选。

| | **(A) 加 `SecretStorage` 依赖** | **(B) 调系统命令 `secret-tool`** | **(C) 代挂载走 gvfs，口令交给它** |
|---|---|---|---|
| 怎么做 | D-Bus 直连 Secret Service，自己写/读/删条目，键沿用 `pan4dex:smb:服务器\共享` | `shutil.which('secret-tool')` → `store`/`lookup`/`clear` 子进程 | `gio mount smb://服务器/共享`，认证与存储都由 gvfs 做，我们只等挂点出现再导航 |
| 目标机要装什么 | **什么都不用装**（服务实测已在） | **要装 `libsecret-tools`**（实测未装，candidate 0.21.4-1build3；库 `libsecret-1-0` 已装、命令不在） | 什么都不用装（gvfs 六个包实测都在且 daemon 在跑） |
| 进不进我们的单文件 ELF | **进**（Python 依赖被 PyInstaller 收进包） | **不进**（系统命令，包里带不了） | 不进（同样是系统命令，但目标机实测已有） |
| 新增依赖与体积 | `SecretStorage 3.5.0`（wheel 0.01 MB，纯 Python）+ `jeepney 0.9.0`（0.05 MB，纯 Python）+ **`cryptography`（硬依赖，`cp39-abi3-manylinux_2_17_x86_64` wheel 实测 4.53 MB，带二进制）**；ELF 增量**待实测** | **0 新依赖**（本仓 `pyproject.toml`/`uv.lock` 里 keyring/secretstorage/jeepney/dbus/cryptography 全 0 命中） | **0 新依赖** |
| 与现有代码形状 | **最贴合**：`core/net_share.py:495` 的 `_credapi()` 就是为换实现留的唯一注出口，Linux 换一份后端即可，`plan_open()`(563)/`retry_with_credential()`(603) 与 85 项离屏用例（假 `FakeCred`）原样复用 | 也贴合 Linux 既有习惯（`core/reveal.py:52,54` 与 `core/pane.py:1343` 都是 `shutil.which` + 系统命令），同样只换 `_credapi()` | **不复用凭据链路**：连接与认证都交出去，`net_share` 在 Linux 上只剩「认写法 + 调 gio + 等挂点」 |
| 没有钥匙环服务时 | 要自己写退化（连不上总线 → 「记住」置灰 + 明说「这次不记住」） | 天然退化（`which` 找不到就置灰），与今天 Linux 上「记住」已置灰的行为一致 | 天然退化（没有 gvfs 就回到今天的指引文案） |
| 工作量（估） | 2–3 天（含打包验证 + 跨进程凭据用例） | 1–2 天 | 代挂载本身 2–3 天，**存口令这一半 0** |
| 主要风险 | `cryptography` 进 PyInstaller 的隐藏导入与体积；钥匙环 collection 锁着时的解锁提示要处理 | 每台 Linux 目标机多一个安装步骤，**打破「下载即用」**；口令经子进程传递（公开用法是从 stdin 读、不进 argv，**未实测**，两台机器上都没有这个命令） | 认证框是系统的（样式与「记住」语义不受我们控制 —— 与 §5.1 否决 D 的理由同一类）；**它到底替不替我们存口令，待实测** |

**已核对**：上表「目标机要装什么」「新增依赖与体积」「钥匙环服务在不在」三行全是本轮实测（§5.4）。
**待实测**：C 的关键一步（真挂一次共享，看 gvfs 是否弹认证框并把口令存进钥匙环）、A 的冻结产物连通性与
ELF 增量、B 的 stdin 传口令形状 —— 三条都在 `docs/linux-gap.md` §5.4 的待实测表里附了命令与判据。
本轮**没做**这三条：都要写东西或碰真共享，而探针约束是「不拿用户的 NAS 做实验」。

**建议**：**先验 C，再在 A/B 里选**。C 是唯一可能让这道题整个消失的选项，验它只要一次真挂载；
若 C 成立就不加任何依赖（也符合「现成 CLI > 改数据 > 改代码」的次序）。若 C 不成立，**选 A**：
我们的 Linux 产物是单文件 ELF，Python 依赖能进包、系统命令不能，B 等于把「先装一个包」变成每台
Linux 目标机的前置步骤，而这台目标机恰好就是没装的那个。
**被否决的备选**：自己写一份 D-Bus 客户端绕开 `cryptography`（省 4.5 MB，但要把 Secret Service 的
会话/加密与属性字典全部手写一遍，等于把 Windows 那轮 ctypes 结构体的坑在 D-Bus 上重演，gotchas #68）；
`keyring` 库（它在 Linux 上的后端就是 SecretStorage，多一层抽象却不少一个依赖）。

### 12.2 `\\主机` 列共享：摆在窗格里 vs 弹一个小框

**先更正一条我自己差点写进对比的推测**：先前以为「返回上级」在主机层会给出 `\\` 并被 `parse_unc` 拒。
本轮实测（`tmp/go_up_probe.py`，ntpath）**不成立**：`os.path.dirname(r'\\NAS')` 与
`os.path.dirname(r'\\NAS\photo')` 都**原样返回**，`widgets/path_bar.py:333` 的 `parent != current`
守卫因此不发信号 —— 这两层的「返回上级」今天就是**空操作**（ntpath 把「服务器\共享」当盘符根）。
只有 `\\NAS\photo\2026` → `\\NAS\photo\` 才真发信号。

**核到行的代码事实（A 的成本就长在这些地方）**

- `core/dir_model.py:51-63`：`Entry` 只有 `name/path/is_dir/size/mtime/hidden/is_link/node`；
  唯一入口 `set_directory()`(572) → `_ensure_node` → `_start_load`(587/612) → 后台 `os.scandir`。
  **没有注入合成条目的口子**，而且每次导航都绑着 TTL 快照判定(595)、放弃旧扫描(603)、watcher 登记(588/610)。
- `core/pane.py:1202`：地址栏先 `os.path.isdir` 才导航；`1303`：详情视图双击**现场** `os.path.isdir`，
  而缩略图视图 `1312` 读的是**缓存** `is_dir` —— 两个入口判据不一样，未连接的 `\\NAS\photo`
  在详情视图里会被当**文件**去 `open_file()`。
- `core/pane.py:848` 与 `1166`：重启恢复、标签页切换都以 `os.path.isdir` 为门 → 虚拟的「主机层」
  路径写进历史/标签后，下次恢复会被**静默跳过**（铁律 #8 那类空守卫的同一个形状）。
- `core/mounts.py`：任何 `\\` 前缀都判 remote（含裸主机）→ 不挂 watcher，这一条 A/B 都白拿。
- **窗格里列非目录条目没有先例**：搜索结果住对话框（`widgets/advanced_search.py:190`，
  `result_tree.itemDoubleClicked` 在 346，模态构造在 `core/main_window.py:1363`），
  收藏夹住侧边栏（`widgets/bookmark_sidebar.py:222`）。

| | **(A) 窗格当虚拟目录** | **(B) 弹小框选一个** |
|---|---|---|
| 改动面 | 给 `DirStoreModel` 开一条绕过 scandir/TTL/watcher 的注入通道；改 4 处 `isdir` 门（1202/1303/848/1166）+ 拖放的 isdir 判据 + `go_up` 的 UNC 语义 + 路径栏回填 | `net_share` 加主机层分支 + 枚举 API；新对话框照 `advanced_search` 的形状（列表 + 双击 → `pane.navigate_to(r'\\主机\共享')`）。**窗格与模型一行不动** |
| 风险 | 动的是**全仓唯一数据源**，铁律 #2（监视六条约束）与 #3（排序/筛选只读缓存 Entry）都压在这条链上，漏一处就是闪列表或 AV | 只有新对话框自己。已知的坑是 gotchas #56（构造时别做会弹模态框的事），照现有两个对话框的写法即可避 |
| 体验 | 与普通目录一致：能排序、能双击、能拖、能开多个标签 | 多一次点击；选完就进**真目录**，之后一切照旧（含「返回上级」今天的空操作，不新增语义） |
| 工作量（估） | 5–8 天 + 一轮真机 | 1–2 天（`NetShareEnum` 探针另计） |
| 可测性 | 要新造「虚拟节点」用例，且**改前对照组难做**（今天没有这条路径，拆掉修复看不到红） | 假 API 驱动枚举 + offscreen 对话框用例，与现有 85 项同一手法，对照组天然可做 |

**建议 B**，并且**探针先行**（T16 的前置不变：`NetShareEnum` 的缓冲区/`ResumeHandle`/权限不足回哪档码
都还没实测，已实测的 27 个码里没有它）。A 不是永远不做，是等 `\\主机\共享` 主路径真机验过（L17）、
且用户真提出「想在窗格里浏览共享列表」再排 —— 那时它的成本才有对应的收益。
**被否决的备选**：把共享列表塞进侧边栏（与收藏夹混在一起，语义不同且侧边栏没有「这台机的共享」这一层）；
用 `net view \\主机` 子进程代替 `NetShareEnum`（§5.3 否决子进程的四条理由原样适用，且输出要解析本地化文本）。

