# Pan4dex 版本更新机制（更新服务器 + 客户端更新）

> 状态：**已实现（2026-10-30）**；服务器已部署到 230（uv + systemd），两平台真机升级联调待做（见第 10 节）
> 范围：Windows（onedir + zip）、Linux（onefile ELF）
> 本文是该机制的单一真相：服务器 API、客户端行为、部署、安全边界都只写在这里。实现落地后本文继续作为机制文档维护，不另开一份设计稿。
>
> 实现落点：`server/update-server/`（Flask + waitress + SQLite）、`core/updater.py`（纯标准库）、
> `core/update_runner.py`（后台线程）、`widgets/update_dialog.py`（状态机对话框）、
> `widgets/settings_dialog.py`「更新」页、`core/main_window.py` 帮助菜单入口与启动检查调度、
> `main.py --check-update`（无界面冒烟）。测试：`server/update-server/tests/test_app.py`、
> `tests/test_updater.py`、`tests/test_update_ui.py`。

---

## 0. 已确认的用户决策

| 决策点 | 结论 |
|---|---|
| 服务器访问范围 | **仅局域网**（192.168.5.x），走 HTTP，不做域名/证书 |
| 服务器端口 | **23011**（可在环境变量/客户端设置中改） |
| 发布说明格式 | **纯文本**，不渲染 Markdown/HTML |
| 客户端默认行为 | **启动后台检查 → 发现新版本提示 → 用户确认后下载安装** |
| Windows 替换方式 | **自动替换并重启**（临时更新脚本，失败回滚旧目录） |
| 管理页鉴权 | **单一管理口令**（会话 Cookie + CSRF） |

其余细节由本文给出；被否决的备选方案集中在第 12 节。

---

## 1. 目标与非目标

### 目标

1. 230（`kali@192.168.5.230`）上运行一个更新服务器，保存 Windows/Linux 两个平台的发布产物和版本元数据。
2. 管理端 Web 页面可以**手动上传版本**（自动计算 SHA-256、校验包结构、填写发布说明），并支持撤下（yank）/ 删除。
3. 客户端：
   - 启动时后台检查新版本（可在设置里关闭）；
   - 帮助菜单可手动检查更新；
   - 支持「提示后手动确认」和「自动下载 / 自动安装」两种模式；
   - Windows 自动替换 onedir 目录并重启，失败回滚；
   - Linux 自动替换 onefile 可执行文件并重启。
4. 覆盖断网、坏包、磁盘不可写、服务器离线、重复版本等失败路径，失败不能让客户端起不来。

### 非目标

- 增量更新（delta）、灰度/渠道（beta）、强制更新、降级安装；
- 代码签名、HTTPS/证书体系（局域网 + 管理口令 + SHA-256，见第 7 节）；
- macOS、源码运行模式的自替换；
- 自动构建/自动发布（本次仍由 Web 手动上传）。

---

## 2. 现状与约束（设计依据）

### 2.1 版本号只有一个来源

`config/app_config.py:18` 的 `VERSION` 是运行时版本号，`pyproject.toml:3` 与其保持同步；发布流程要求两者一起改（`AGENT.md:83-84`）。更新检查必须以 `VERSION` 为准，不能另建一份版本常量。

### 2.2 两个平台的产物形态完全不同

- Windows：PyInstaller `--onedir`，产物是 `releases/pan4dex-<版本>/`（含 `pan4dex.exe` 与 `_internal/`），再压成 `releases/pan4dex-<版本>.zip`，**zip 内顶层目录固定为 `pan4dex/`**（`scripts/build_windows.py:99-110`、`:197-209`）。
- Linux：PyInstaller `--onefile`，产物是单个 ELF `releases/pan4dex-<版本>-linux`（`scripts/build-linux-docker.sh:185`）。

因此客户端必须按平台走两条安装路径，服务器也要按平台分别维护「最新版本」。

### 2.3 Windows 包没有 QtNetwork

`scripts/build_windows.py:118` 显式 `--exclude-module=PyQt6.QtNetwork`。更新检查**不能用 `QNetworkAccessManager`**，统一改用标准库 `urllib.request`，在后台线程执行，避免改动打包配置。

### 2.4 客户端入口

- 帮助菜单：设置 / 关于（`core/main_window.py:719-728`）；「检查更新」放在这里。
- 关于对话框：`core/main_window.py:1425-1472`，显示 `VERSION` 与 `BUILD_TIME`。
- 设置对话框：QTabWidget 分页，现有「常规/主题/字体/工具栏/启动器」（`widgets/settings_dialog.py:38-59`）；新增「更新」页。
- CLI 参数在 GUI 导入前处理（`main.py:577-585`），可增加无界面 `--check-update` 供 230 冒烟测试。

### 2.5 线程与生命周期约定

后台→UI 必须用信号，接收者就是目标 QObject，延后执行用 `call_later`，退出走 `exec_and_drain`（`AGENT.md:55-57`；`core/lifecycle.py:69`、`:132`；`core/file_op_runner.py:44-59` 是现成范式）。更新检查/下载沿用同一模式，不引入新线程模型。

### 2.6 230 是现成的构建/测试机

`docs/build/legacy-multimachine.md:29` 记录 230 = `kali@192.168.5.230`，曾为主构建机，现用于 Linux 真机验证（`docs/linux-gap.md:84`）。更新服务器放在 230 不新增机器；Docker 已在该机用于构建。

### 2.7 安装位置与写权限

- Windows：解压 zip 得到 `pan4dex\`，可能被放到 `Program Files` 之外的任意目录；运行中的 exe 与已加载 DLL 被锁，**不能直接覆盖正在运行的目录**，必须先退出再由外部脚本替换。
- Linux：onefile 可位于仓库 `releases/`（可写）、`~/.local/bin`（可写）或 `/opt/pan4dex/`（通常 root 拥有，`scripts/install-linux.sh` 明确允许 `--install-menu` 指向 `/opt` 路径）。**必须处理不可写目录**，不能假定可以自替换。

---

## 3. 总体架构

```
                    ┌──────────────────────────────┐
                    │  230 · 192.168.5.230:23011    │
                    │  update-server (Flask+waitress)│
                    │                              │
  浏览器(管理员) ───▶│  /admin  上传/撤下/删除       │
                    │  /api/v1/latest  客户端检查    │
   Pan4dex 客户端 ──▶│  /download/...   产物下载      │
                    │  data/ pan4dex.db + releases/ │
                    └──────────────────────────────┘
```

- 服务器无状态逻辑 + 本地文件/SQLite，单容器部署；
- 客户端只读 API + 下载，不依赖服务器推送；
- 管理页与客户端 API 同一进程，端口 23011（可配置）。

---

## 4. 服务器设计

### 4.1 技术选型

- **Flask + waitress + Jinja2 + SQLite（标准库）**。
- 不选 FastAPI：需要额外 ASGI 容器与前端构建，收益为零；不选 Django：管理页只需 2-3 个页面，Django 过重；不选 nginx + 静态目录：无法在同一个页面完成上传/校验/写库。
- 上传大文件（约 100 MB）由 Flask 落盘，`MAX_CONTENT_LENGTH` 默认 500 MB，流式保存。

### 4.2 目录结构（仓库内）

```
server/update-server/
  app.py                # 工厂 + 路由
  storage.py            # SQLite / 文件 / 校验
  templates/            # base/login/index/public_releases
  static/app.css        # 设计令牌 + 组件样式
  static/app.js         # 上传进度、删除确认、复制哈希
  requirements.txt      # flask, waitress
  Dockerfile
  docker-compose.yml
  tests/test_app.py
  README.md             # 只写部署步骤，机制细节指向 docs/update.md
```

### 4.3 数据模型与存储

SQLite 表 `releases`：

| 字段 | 说明 |
|---|---|
| id | 自增主键 |
| version | `1.9.028` 形式，服务端再解析成整数元组排序 |
| platform | `windows` / `linux` |
| filename | 产物文件名（保存后不变） |
| size | 字节数 |
| sha256 | 十六进制小写 |
| notes | 发布说明（纯文本，最多 4000 字） |
| uploaded_at | UTC ISO-8601 |
| yanked | 0/1 |

- 唯一约束：`(version, platform)`；重复上传默认拒绝。
- 文件落盘：`data/releases/<platform>/<filename>`。
- 「最新版本」= 该平台 `yanked=0` 中版本号最大的那条；不单独维护 latest 指针，避免两处状态不一致。
- 磁盘统计：管理页显示各平台占用与总占用。
- **版本保留上限**：每个平台按版本号只保留最新 5 个（可用 `PAN4DEX_UPDATE_RETENTION` 改），超出的在服务启动时和每次上传成功后自动删除（数据库记录+磁盘产物一起删，yanked 的旧版本同样计入裁剪）；删除动作写入 `data/logs/admin.log`（action=`prune`）。

### 4.4 HTTP API（客户端契约，`/api/v1`）

`GET /api/v1/latest?platform=windows|linux`

- 200：

```json
{
  "version": "1.9.028",
  "platform": "windows",
  "filename": "pan4dex-1.9.028.zip",
  "size": 90212210,
  "sha256": "…64 位十六进制…",
  "published_at": "2026-10-30T08:00:00Z",
  "notes": "修复…",
  "download_url": "http://192.168.5.230:23011/download/windows/pan4dex-1.9.028.zip"
}
```

- 404 `{"error": "no_release"}`：该平台还没有任何版本；
- 响应头 `Cache-Control: no-store`，避免客户端/代理缓存旧版本。

`GET /api/v1/releases?platform=…`：返回该平台全部未撤下版本（诊断用；不含 notes 以外的敏感信息）。
`GET /download/<platform>/<filename>`：`send_file`，带 `Content-Disposition: attachment`、`X-Checksum-Sha256`；支持 Range（Flask 默认支持）。
`GET /healthz`：`{"status":"ok","server_version":"1.0.0","time":"…"}`。

### 4.5 管理端与上传校验

页面：

- `GET /`：公开下载页（按平台列出未撤下版本，可手动下载）。
- `GET /admin/login`、`POST /admin/login`、`POST /admin/logout`。
- `GET /admin`：统计卡（两平台最新版本、版本总数、磁盘占用）+ 上传表单 + 版本表（撤下/恢复/删除）。
- `POST /admin/upload`、`POST /admin/releases/<id>/yank`、`POST /admin/releases/<id>/delete`。

上传校验（任何一条失败都拒绝，不落库）：

1. 文件名匹配：
   - Windows：`pan4dex-<x.y.z>.zip`
   - Linux：`pan4dex-<x.y.z>-linux`
2. 版本号与文件名一致（不一致时以表单里显式填写并二次确认的值为准，默认禁止）。
3. 文件大小 ≤ 500 MB。
4. Windows：zip 可读，条目全部以 `pan4dex/` 开头且不含 `..`/绝对路径，必须存在 `pan4dex/pan4dex.exe`。
5. Linux：文件头为 `\x7fELF`，64 位小端、x86-64（`e_machine=62`）。
6. 计算 SHA-256 与大小并落库；重复 `(version, platform)` 拒绝，除非勾选「替换同版本」并在确认框中再次确认。
7. 上传成功返回 JSON（管理页前端无刷新提示），同时写审计日志。

删除语义：

- **撤下（yank）**：保留文件与记录，但不再作为 latest 返回；可恢复。推荐用它处理坏版本。
- **删除**：二次确认后删记录与文件，不可恢复；仅用于彻底清理。

### 4.6 鉴权与会话

- 口令来自环境变量 `PAN4DEX_UPDATE_ADMIN_PASSWORD`；未设置时服务拒绝启动（避免空口令裸奔）。
- 登录成功后签发 Flask session（HttpOnly、SameSite=Lax；HTTP 局域网下不设 Secure）；`SECRET_KEY` 来自 `PAN4DEX_UPDATE_SECRET`，未设置则生成并持久化到 `data/secret.key`（0600）。
- 口令比较用 `hmac.compare_digest`；同一 IP 连续 5 次失败锁 60 秒（内存计数即可）。
- 所有写操作校验 CSRF token（session 内随机值，表单隐藏字段/请求头）。
- 管理操作写 `data/logs/admin.log`（时间、IP、动作、版本、文件名）。

### 4.7 部署（230）

现网：**uv 管虚拟环境 + systemd 托管**，目录 `/home/kali/runSpace/pan4dex`。

- 依赖：`uv sync`（`pyproject.toml` 里 Flask + waitress；测试用 `uv sync --extra dev`）。
- 服务：`/etc/systemd/system/pan4dex-update.service`，`EnvironmentFile=.env`、`PAN4DEX_UPDATE_DATA_DIR=<目录>/data`、`ExecStart=.venv/bin/python app.py`、`Restart=always`；`systemctl enable --now pan4dex-update`。
- 数据：`<目录>/data/`（SQLite、产物、`secret.key`、`logs/admin.log`），备份拷这个目录即可。
- 防火墙只放行局域网：`ufw allow from 192.168.5.0/24 to any port 23011`（Kali 若用 nftables，按同义规则；本机 ufw 关闭时无需配置）。
- 备选：仓库内 `Dockerfile` / `docker-compose.yml` 仍可用；230 曾因拉不到 Docker Hub 基础镜像改走 uv 方案。
- 反向代理/域名不在本次范围；以后上 HTTPS 只需在客户端改 `update/server_url`。

### 4.7.1 构建一键上传（构建机）

构建脚本带 `-U` 时，产物构建完直接调用 `scripts/upload_release.py` 走管理页同一条
`/admin/upload` 通道（自动登录 + CSRF + multipart + SHA-256 由服务端计算）：

```bash
build_all.bat -U                          # Windows：两平台（Linux 走 Docker/Git Bash）
./build_all.sh -U                         # Linux/Git Bash：同上（薄封装 scripts/build_all.py）
python scripts/build_windows.py -U        # 只 Windows
bash scripts/build-linux-docker.sh -U     # 只 Linux
python scripts/upload_release.py --platform linux --file releases/pan4dex-1.9.028-linux
```

- 地址/超时/默认发布说明：`scripts/update_server.json`（入库）。
- 管理口令：环境变量 `PAN4DEX_UPDATE_ADMIN_PASSWORD` 优先，其次读
  `server/update-server/.env`（与服务器共用同一份，已被 `server/.gitignore` 排除），
  都没有时交互输入。口令不进 `scripts/update_server.json` 等入库文件。
- 同平台同版本已存在 → 上传报 409 并提示；加 `--replace` 覆盖。
- 上传失败时构建产物保留、退出码非零，发布流程不会把“构建成功”误报成“已发布”。

### 4.8 运维

- 备份：`data/` 目录整体拷贝即可（SQLite + 产物）。
- 日志：容器日志 + `data/logs/admin.log`；不记录口令与 Cookie。
- 服务器自身版本：`SERVER_VERSION = "1.0.0"`，`/healthz` 可见，便于确认部署的是哪版。

---

## 5. 客户端设计

### 5.1 模块划分

```
core/updater.py            # 版本比较、检查、下载、校验、安装（不含 UI）
core/update_runner.py      # 后台线程 → 信号回主线程（检查 / 下载 / 取消）
widgets/update_dialog.py   # 发现新版本 / 下载进度 / 安装确认
```

不新建包；沿用 `core/` + `widgets/` 的扁平结构（`AGENT.md:27-41`）。

`core/updater.py` 只依赖标准库 + `config.app_config`，**不 import Qt**；线程封装在
`core/update_runner.py`（信号接收者就是目标 QObject），便于核心逻辑单测。安装阶段启动
新进程也用标准库 `subprocess`（`start_new_session` / `DETACHED_PROCESS`），不在核心层引入 Qt。

### 5.2 检查流程

1. 平台：`sys.platform == "win32"` → `windows`，否则 `linux`。
2. `GET <server_url>/api/v1/latest?platform=…`，`urllib.request`，单值 15 s 超时（urllib 不支持
   分别设置连接/读取超时），UA `Pan4dex/<VERSION> (<platform>)`。
   服务器用 `404 + {"error": "no_release"}` 表示该平台还没有版本，客户端按「无更新」处理。
3. 校验 JSON 必填字段、版本号格式、`sha256` 为 64 位十六进制、`size > 0`。
4. 版本比较：按 `.` 拆成整数元组逐段比较；相等或本地更高 → 无更新。
5. 结果：`UpdateInfo`（version/filename/size/sha256/notes/download_url）。

**源码运行模式**（`sys.frozen` 为假）：允许检查并展示结果，但不提供安装按钮，提示「开发模式不自动更新」。这避免开发机被替换。

### 5.3 UI 流程与状态

启动检查（默认开）：

- `MainWindow` 构造完成后 `call_later(self, 3000, …)` 触发；
- 后台线程检查，成功且有新版本且不等于 `update/skipped_version` 时弹出**非模态** `UpdateDialog`（不阻塞用户继续用）；
- 检查失败只写日志，不打扰用户。

手动检查（帮助 → 检查更新…）：

- 始终忽略「跳过此版本」；无更新弹信息框；失败弹错误框（含服务器地址与错误原因）。

`UpdateDialog` 状态机：

| 状态 | 内容 | 按钮 |
|---|---|---|
| 发现新版本 | 当前版本 → 新版本、大小、发布说明（纯文本） | 立即更新 / 只下载 / 稍后 / 跳过此版本 |
| 下载中 | 进度条 + 已下载/总大小 + 速度 | 取消 |
| 校验失败 | 说明哈希不匹配，已删除临时文件 | 重试 / 关闭 |
| 已下载 | 「下载完成，重启后安装」；只下载模式额外显示包路径 | 立即重启安装 / 打开下载目录（只下载）/ 稍后 |
| 安装准备失败 | 目录不可写等具体原因 + 手动下载地址 | 打开下载页 / 关闭 |

- 「稍后」：本次关闭，下次启动仍提示；
- 「只下载」：只下载安装包不安装；完成后显示包路径，可打开下载目录；下次启动提示时本地校验通过的包直接复用，不重下；
- 「跳过此版本」：写 `update/skipped_version`，自动检查不再提示该版本；手动检查仍会显示；
- 发布说明按纯文本显示（`QMessageBox`/`QLabel` 用 `PlainText`），不渲染 HTML，防注入。

### 5.4 自动模式

设置项三个开关（默认值见 5.6）：

- `startup_check` 开、`auto_download` 关、`auto_install` 关：**默认**，提示后手动确认。
- `auto_download` 开、`auto_install` 关：启动静默下载并校验，完成后再弹「重启安装」提示。
- 两者都开：下载校验完成后直接进入安装并重启（用户事先知情）。

安装过程必须显示明确的状态（窗口内对话框），不能静默退出让用户以为崩溃。

### 5.5 Windows 安装器

安装目录 = `Path(sys.executable).parent`。

流程：

1. 预检目录可写（`os.access(target_dir, os.W_OK)`）；不可写 → 提示以管理员身份运行或手动解压，不下载。
2. 下载到 `%LOCALAPPDATA%\pan4dex\updates\pan4dex-<ver>.zip`（`.part` 临时名，完成后改名），边下边算 SHA-256；大小与哈希都匹配才继续。
3. 用 `zipfile` 预检条目：全部位于 `pan4dex/` 下、无 `..`/绝对路径、含 `pan4dex.exe`。
4. 生成 `%TEMP%\pan4dex-update-<ver>\job.json`（UTF-8）与 `apply-update.ps1`（**UTF-8 with BOM**，否则 PowerShell 5.1 会把中文路径读成 ANSI 乱码）：
   - 参数文件含：父进程 PID、zip 路径、目标目录、exe 路径、旧版本、日志路径；
   - 脚本逻辑：等待旧进程退出（宽限 15 s，超时强制结束——界面已提示「当前窗口会关闭」，避免旧进程卡住导致替换失败回滚）→ 解压到临时目录（优先 `C:\Windows\System32\tar.exe`，比 `Expand-Archive` 快数十倍；缺失或失败回退 `Expand-Archive`）→ 结束仍从安装目录运行的实例（按 exe 完整路径匹配）→ 旧目录改名为 `pan4dex.bak-<旧版本>` → 解压出的 `pan4dex` 移到目标路径 → 启动新 exe → 写 `update-ok.json`（含新版本，PS 5.1 写出带 BOM，客户端用 utf-8-sig 读取）→ 删除 zip；
   - **改名失败自动降级原地覆盖**（1.9.040）：目录改名会被外部句柄挡住（资源管理器开着该目录窗口 / 终端 cd 在里面，报「正在使用中」），但这类句柄不影响覆盖文件——降级用 `robocopy /E /R:3 /W:3` 原地覆盖，退出码 ≥8 视为失败；此路径无备份可回滚，依赖 zip 保留供重试；
   - 任一步失败：把备份目录移回原路径，写日志，保留 zip 供手动重试。
5. 用 `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` 启动 `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File …`，随后 `QApplication.quit()`。
6. 新版本启动后，检测同目录 `update-ok.json`：版本与当前 `VERSION` 一致 → 延迟 10 s 删除 `pan4dex.bak-<旧版本>` 与标记文件；不一致则保留备份，便于人工回退。

要点：

- 运行中的 exe/DLL 不能被覆盖，所以必须先退出、由独立脚本替换；脚本不依赖 Python。
- 目标目录名不假定为 `pan4dex`（用户可能解压后改名）：解压出的 `pan4dex` 目录移动到「原目标目录」的名称。
- 备份与目标必须在同一父目录（同盘改名是原子的，跨盘移动慢且可能失败）。
- 若用户在安装过程中强行关机：下次启动见 `update-ok.json` 不存在且备份存在 → 保留现状；安装器脚本失败会自行回滚，最坏情况用户从 `.bak` 目录手动启动。

### 5.6 Linux 安装器

目标 = `os.path.realpath(sys.executable)`。

1. 预检目标所在目录可写；不可写 → 弹出手动命令：
   `sudo install -m 755 <下载文件绝对路径> <目标路径>`（绝对路径加引号——只给文件名的话
   用户在任何其他目录执行都会 No such file），不尝试提权。
2. 下载到 `~/.cache/pan4dex/updates/`（`.part` 临时名，校验大小/SHA-256 与 ELF 头）。
   与安装目录跨文件系统时 `os.replace` 报 EXDEV，自动降级为拷进安装目录再原地替换。
3. `chmod 0o755` → `os.replace(part, target)`（Linux 允许替换正在运行的可执行文件）。
4. `subprocess.Popen(start_new_session=True)`（核心层不 import Qt）启动新版本，**stderr/stdout
   追加到安装目录 `pan4dex-launch.log`**——新版本起来即死（依赖/权限/显示环境问题）时死因
   在这里，没有它整条升级在日志里无痕；随后退出当前进程。
   **启动前必须剥掉 PyInstaller 父子进程标记**（`_MEI*`/`_PYI_*` 环境变量，`LD_LIBRARY_PATH`
   里指向 `_MEI` 目录的条目一并去掉）：onefile 应用进程带着 `_PYI_APPLICATION_HOME_DIR`
   （指向旧进程的 `/tmp/_MEI*` 解压目录）等标记，新进程看到就跳过解压、直接复用旧目录；
   旧进程退出时把该目录删掉，新进程 import 踩空（2026-10-31 linux231 两次实证：
   `ModuleNotFoundError: No module named 'PyQt6.QtWidgets'`，死不死取决于新旧进程退出的竞态；
   带标记复现、剥掉标记即正常，Windows 安装脚本链路同源预防）。
5. 失败（磁盘满、权限、校验不符）：删除临时文件，保留旧文件，对话框说明原因。
   全链路（target/替换/启动）打 `[update]` INFO 日志进 pan4dex.log。

注意：onefile 运行时会解压到 `/tmp`，替换原文件不影响当前进程；`.desktop` 的 `Exec` 路径不变，无需重装菜单。

### 5.7 设置项（QSettings，`ORG_NAME/APP_NAME`）

| 键 | 默认 | 含义 |
|---|---|---|
| `update/server_url` | `http://192.168.5.230:23011` | 更新服务器根地址 |
| `update/startup_check` | `true` | 启动时后台检查 |
| `update/auto_download` | `false` | 发现新版本后自动下载 |
| `update/auto_install` | `false` | 下载完成后自动安装并重启（仅当自动下载开启时可用） |
| `update/skipped_version` | 空 | 用户选择跳过的版本 |

设置页显示当前版本与「立即检查」按钮；`server_url` 非法（非 http/https 或无主机）时保存前校验。

### 5.8 失败处理原则

- 自动检查失败：静默（日志），绝不弹窗打断启动；
- 手动检查失败：明确错误（超时/404/JSON 非法/哈希不符），并显示当前服务器地址；
- 下载可取消，取消后清理 `.part`；
- 任何安装异常都必须让旧版本保持可启动；
- 服务器返回的 notes 只当文本，不当 HTML/脚本。

### 5.9 无界面检查（`--check-update`）

`python main.py --check-update [--server URL]` 只做检查并打印当前版本、服务器、新版本与
SHA-256（不初始化 Qt）。退出码：`0` 已是最新、`3` 有新版本、`1` 检查失败，供 230 部署与
发布脚本冒烟。

---

## 6. UI 设计（基于 ui-ux-pro-max）

### 6.1 设计系统（管理端 Web）

采用技能检索出的「开发者工具 / Dark Mode (OLED)」方向，令牌如下：

| 令牌 | 值 | 用途 |
|---|---|---|
| `--bg` | `#0F172A` | 页面背景 |
| `--card` | `#1B2336` | 卡片/表单 |
| `--fg` | `#F8FAFC` | 正文 |
| `--muted` | `#94A3B8` | 次要文字 |
| `--border` | `#475569` | 分隔线/输入框 |
| `--accent` | `#22C55E` | 主操作/最新版本标记 |
| `--danger` | `#EF4444` | 删除/失败 |
| `--ring` | `#F8FAFC` | 键盘焦点环 |

- 字体：`IBM Plex Sans`（界面）+ `JetBrains Mono`（版本号、SHA-256）；不引 CDN，使用系统字体回退（Segoe UI / Noto Sans CJK / ui-monospace），保证内网离线可用。
- 间距 4/8/12/16/24/32；圆角 8px；交互过渡 150-200 ms；`prefers-reduced-motion` 时关闭。
- 图标用内联 SVG（Lucide 风格），不用 emoji。
- 对比度：正文/背景 ≥ 4.5:1；主按钮绿底深色字；焦点环 2px 可见。

### 6.2 页面结构

1. 登录页：居中卡片，仅口令 + 登录按钮；错误就地显示；回车提交。
2. 控制台 `/admin`：
   - 顶部：产品名、服务器版本/健康状态、退出；
   - 统计卡：Windows 最新、Linux 最新、版本总数、磁盘占用；
   - 上传卡：平台选择（按文件名自动预选）、版本号（自动解析，可改）、发布说明 textarea、拖放/选择文件、上传进度条与结果提示；
   - 版本表：平台徽标、版本、大小、SHA-256（截断 + 复制）、上传时间、状态（最新/已撤下）、操作（撤下/恢复/删除）。
3. 公开页 `/`：两栏版本列表（Windows/Linux），最新版本置顶并高亮，提供下载与 SHA-256；无需登录。

### 6.3 响应式与可访问性

- 断点：≤640 单列，表格转卡片；768/1024/1440 逐级放宽；
- 所有输入有 `<label for>`，错误紧邻字段；
- 所有可点击元素 ≥ 44×44 px，`cursor: pointer`；
- Tab 顺序与视觉顺序一致，焦点环不被移除；
- 上传/删除操作有 loading → success/error 状态，不只靠颜色区分（图标 + 文案）。

### 6.4 客户端对话框（Qt）

- 复用现有主题（深/浅）与 `ThemeManager` 语义色令牌（`docs/ui-audit.md` W1 第一步）；
- 标题「发现新版本」、版本对比用等宽字体、发布说明用只读纯文本区（可滚动，最大高度 240 px）；
- 主按钮「立即更新」按主题 accent 色；「跳过此版本」为次要按钮；
- 进度条显示百分比 + 已下载/总量 + 速度，提供「取消」；
- 不用模态遮罩阻塞启动检查；手动检查的对话框可模态。

---

## 7. 安全与威胁模型

### 7.1 信任边界

- 局域网内、HTTP 明文；服务器文件与数据库由 230 管理员控制；
- 客户端信任「从配置的服务器拿到的 manifest」，依赖 SHA-256 保证**传输损坏/截断**不会装坏包；
- 不防「局域网内主动篡改 manifest 的中间人」——这是已知限制（第 7.4 节）。

### 7.2 上传与安装防护

- 服务端校验包结构、ELF 头、大小、哈希；文件名白名单正则；落盘路径由服务端生成，不使用用户路径（防穿越）。
- 客户端解压前用 `zipfile` 检查条目路径，安装脚本解压到临时目录后再移动，避免 zip-slip。
- 客户端只执行自己生成的 PowerShell/替换逻辑，绝不执行包内脚本。
- 管理端：口令 + 会话 + CSRF + 登录限速；上传/删除写审计日志。

### 7.3 被否决的安全方案

| 方案 | 否决原因 |
|---|---|
| 自签 HTTPS + 客户端内置 CA | 证书到期/更换都要重新发客户端；局域网收益有限 |
| Ed25519 签名 manifest | 需给客户端加 `cryptography` 依赖，还要管理私钥/轮换；当前威胁模型下性价比低 |
| HMAC 共享密钥 | 密钥必然内嵌客户端，可被提取，防不住有心人，只会造成安全假象 |
| 走 GitHub Releases | 用户明确要求服务器架在 230；且内网机器未必能访问外网 |

签名/HTTPS 留作后续增强：API 与配置已支持切换 `https://` 地址，届时只需加验签步骤。

### 7.4 已知限制

- 获取 manifest 与下载走同一 HTTP 服务器，篡改者可以同时改包与哈希；仅靠 SHA-256 不能证明来源。
- 无降级机制：客户端只认更高版本；坏版本靠管理端 yank，让尚未更新的客户端停在上一版，已更新的客户端需手动回退。
- 230 停机时自动检查静默失败；手动检查会明确报错。

---

## 8. 场景走查（日常操作）

1. **发布**：构建 1.9.029 的 Windows zip 与 Linux ELF → 打开 `http://192.168.5.230:23011/admin` → 登录 → 分别上传（版本/说明自动带出）→ 列表出现两条「最新」；公开页可下载验证。
2. **客户端启动检查**：1.9.028 启动 → 3 秒后提示 1.9.029 → 点「立即更新」→ 下载校验 → Windows 退出并由脚本替换后重启；Linux 原地替换后重启 → 关于对话框显示 1.9.029。
3. **手动检查**：无更新时提示「已是最新版本」；服务器关机时提示连接失败与服务器地址。
4. **跳过版本**：点「跳过此版本」→ 下次启动不再提示 1.9.029；1.9.030 出现时恢复提示。
5. **坏包/改包**：上传后被人工改动或下载中断 → SHA-256 不符 → 客户端删除临时文件并提示重试，不安装。
6. **安装目录不可写**：Windows 装在 `Program Files` 且非管理员 → 预检失败，提示手动解压/管理员运行；Linux `/opt` 属 root → 下载到缓存并给 `sudo install` 命令。
7. **更新失败回滚**：替换过程中脚本异常 → 旧目录移回；下次启动仍是旧版本。
8. **发现坏版本**：管理页「撤下」1.9.029 → 新检查返回 1.9.028；尚未更新的 1.9.027 客户端直接升到 1.9.028。
9. **重复上传**：同版本同平台再次上传 → 拒绝并提示勾选「替换同版本」。
10. **源码开发**：`python main.py` 手动检查能看到版本信息，但安装按钮不可用；不影响开发。
11. **230 重启**：容器 `restart: unless-stopped` 自动拉起；客户端下个周期再查。
12. **多客户端并发下载**：waitress 多线程 + 静态文件读取，100 MB 包在局域网内可接受；管理页显示服务器磁盘余量。

---

## 9. 测试计划

服务器（`server/update-server/tests/`，Flask test client + 临时数据目录）：

- 登录：错误口令、限速、CSRF 缺失拒绝；
- 上传：合法 zip/ELF、错误文件名、错误版本、zip 缺 exe、zip-slip 条目、ELF 头不符、超大文件、重复版本、替换同版本；
- 查询：latest 取最高未撤下版本；yank 后回落；删除后文件消失；
- 下载：Content-Disposition、SHA-256 头、Range；
- 路径穿越：`../` 文件名、非法 platform 参数。

客户端（`tests/test_updater.py`）：

- 版本比较（相等/更高/更低/坏格式）；
- manifest 字段校验（缺字段、哈希格式错、size 非法）；
- 下载校验（正确哈希、错误哈希、大小不符、取消清理 `.part`）；
- 跳过版本逻辑；
- 安装路径选择（Windows 目标目录、Linux realpath）；
- PowerShell 任务文件生成（BOM、路径含空格/中文转义）；
- Linux 替换逻辑用临时目录中的副本验证 `os.replace` 与权限失败分支；
- 设置项读写与非法 URL 拒绝。

手工验收（发布前）：

- Windows：1.9.028 → 1.9.029 全流程；安装目录含中文/空格；非管理员目录不可写分支；
- Linux：230 上从 `releases/` 运行与 `/opt` 只读目录各一次；`.desktop` 启动路径不变；
- 断网、服务器停机、下载中途取消、替换中途杀进程（手工模拟回滚）。

全量 `tests/` 的既有挂起问题按 `AGENT.md:76-79` 处理（同时排除 `test_new_features.py` 与 `test_m5_tools.py`），新增用例不得引入模态阻塞。

---

## 10. 实施拆分

| 阶段 | 内容 | 验收 | 状态 |
|---|---|---|---|
| 1 | 服务器：Flask 应用、SQLite、上传/撤下/删除、API、部署、测试 | 230 上服务可起，API 返回正确 manifest | ✅ 已部署 230（uv + systemd，`/healthz`、登录、`latest` 404 已验证） |
| 2 | 客户端核心：`core/updater.py`（检查/下载/校验/安装），无 UI | 单元测试全绿 | ✅ `tests/test_updater.py` 20 项 |
| 3 | 客户端 UI：菜单项、`UpdateDialog`、设置页、启动检查、CLI `--check-update` | 手工走查第 8 节 1-6、10 | ✅ `tests/test_update_ui.py` 11 项 + 本机真实 HTTP 下载链路冒烟 |
| 4 | Windows/Linux 安装器联调 + 回滚演练 | 两平台各完成一次真实升级 | ⏳ 待做 |
| 5 | 文档与发布：changelog、AGENT.md 索引、feature-checklist、版本号 1.9.029（当前工作树已有 1.9.028 的 UI 改动，版本号届时按发布流程统一） | 完整 `tests/` 出汇总行 | ⏳ 文档已同步，版本号/产物待发布流程 |

预估：服务器半天到一天；客户端核心 + UI 一天；两平台联调与回滚半天。合计约 2-3 个工作日。

---

## 11. 待确认 / 风险

1. 端口已定为 **23011**；实现前仍在 230 上 `ss -ltnp` 核对是否被占用，冲突时只改环境变量与客户端默认值。
2. 230 磁盘余量：每个平台约 100 MB/版本，需确认可用空间（建议保留 ≥ 10 GB）。
3. Windows 目标机是否有 PowerShell 5.1（Win10/11 自带；不支持 Win7）。
4. 客户端默认服务器地址确定为 `http://192.168.5.230:23011`（230 的 IP 变更时在设置页修改）。
5. 发布说明确定为纯文本，不渲染 Markdown/HTML。

---

## 12. 被否决的备选方案（汇总）

| 备选 | 否决原因 |
|---|---|
| 客户端用 QtNetwork 检查 | Windows 包已排除 `PyQt6.QtNetwork`（`scripts/build_windows.py:118`），会引入打包变更 |
| Windows 直接覆盖运行中目录 | exe/DLL 被锁，必然失败 |
| Windows 使用独立 updater.exe | 需要额外构建/签名一个可执行文件，体积与维护成本高；PowerShell 脚本足够 |
| Linux 用 AppImage/包管理器 | 当前产物是 onefile ELF，未走 AppImage/deb 体系 |
| 服务器用 FastAPI/Django/nginx | 功能不匹配，部署更重 |
| 管理页不做鉴权 | 局域网内任何设备都能发布恶意包 |
| 自动静默更新为默认 | 替换失败时用户无感知，风险高（用户已确认默认提示后手动） |
| GitHub Releases 托管 | 用户要求 230，且内网可达性不可控 |
| Ed25519/HTTPS | 见第 7.3 节，当前威胁模型下成本高于收益 |

---

## 附：与现有文档的关系

- 构建产物与发布流程：`docs/build/build-windows.md`、`docs/build/build-linux.md`（不复制到本文）。
- 线程/生命周期铁律：`AGENT.md:55-57`、`core/lifecycle.py`。
- 230 机器信息：`docs/build/legacy-multimachine.md:29`。
- 本文新增后，应在 `AGENT.md` 的「去哪读」表加一行「版本更新机制 → docs/update.md」，并在实现完成后同步 `docs/changelog.md` 与 `docs/feature-checklist.md`。
