# Pan4dex 更新服务器

局域网内部的发布源：管理页手动上传 Windows/Linux 产物，客户端通过 `/api/v1/latest` 检查更新。
机制、客户端行为与安全边界见仓库 [`docs/update.md`](../../docs/update.md)，本页只讲部署与操作。

- 默认端口：**23011**
- 默认地址：`http://192.168.5.230:23011`
- 数据目录：部署目录下的 `data/`（SQLite + 产物 + 审计日志；容器里是 `/data`）

## 在 230 上部署（uv + systemd）

现网就是这样跑的：`/home/kali/runSpace/pan4dex`，由 `pan4dex-update` systemd 服务托管。

```bash
cd /home/kali/runSpace/pan4dex
cp .env.example .env
vi .env                      # 必须修改 PAN4DEX_UPDATE_ADMIN_PASSWORD

uv sync                      # 建 .venv 并安装 Flask/waitress
sudo systemctl restart pan4dex-update
curl -s http://127.0.0.1:23011/healthz
```

一次性的 systemd unit（`/etc/systemd/system/pan4dex-update.service`）：

```ini
[Unit]
Description=Pan4dex update server
After=network-online.target

[Service]
User=kali
WorkingDirectory=/home/kali/runSpace/pan4dex
EnvironmentFile=/home/kali/runSpace/pan4dex/.env
Environment=PAN4DEX_UPDATE_DATA_DIR=/home/kali/runSpace/pan4dex/data
ExecStart=/home/kali/runSpace/pan4dex/.venv/bin/python app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

放行局域网端口（Kali 若用 ufw）：

```bash
sudo ufw allow from 192.168.5.0/24 to any port 23011
```

首次打开 `http://192.168.5.230:23011/admin` 用 `.env` 里的口令登录。
未设置 `PAN4DEX_UPDATE_ADMIN_PASSWORD` 时服务会拒绝启动，不会以空口令运行。

## 另一条路：Docker Compose

仓库里的 `Dockerfile` / `docker-compose.yml` 仍然可用（`docker compose up -d --build`）。
230 当前拉不到 Docker Hub 基础镜像，所以现网用的是上面的 uv 方案。

放行局域网端口（Kali 若用 ufw）：

```bash
ufw allow from 192.168.5.0/24 to any port 23011
```

首次打开 `http://192.168.5.230:23011/admin` 用 `.env` 里的口令登录。
未设置 `PAN4DEX_UPDATE_ADMIN_PASSWORD` 时服务会拒绝启动，不会以空口令运行。

## 上传版本

1. 构建产物：
   - Windows：`releases/pan4dex-<版本>.zip`（zip 内顶层必须是 `pan4dex/`）
   - Linux：`releases/pan4dex-<版本>-linux`
2. 登录 `/admin`，选择平台与版本（文件名会自动带出版本/平台），填写纯文本发布说明，选择文件上传。
3. 服务端会校验文件名、包结构（Windows zip 必须含 `pan4dex/pan4dex.exe`，Linux 必须是 x86-64 ELF），并计算 SHA-256。
4. 同一平台同一版本重复上传会拒绝；确需覆盖时勾选「替换同版本」。
5. 发现坏版本用「撤下」而不是「删除」：撤下后客户端 latest 回落到上一版，已缓存的下载链接仍可用。

发布说明只按纯文本展示，不渲染 Markdown/HTML。

构建脚本可以直接上传，省掉手动选择文件：

```bash
python scripts/build_all.py -U          # 两平台构建并上传
python scripts/build_windows.py -U      # 只 Windows
bash scripts/build-linux-docker.sh -U   # 只 Linux
```

服务器地址在 `scripts/update_server.json`；管理口令放
`scripts/update_server.local.json`（已 gitignore）或环境变量
`PAN4DEX_UPDATE_ADMIN_PASSWORD`。同版本重复上传会报 409，需要时加 `--replace`。

## 客户端接口

```bash
curl "http://192.168.5.230:23011/api/v1/latest?platform=windows"
curl "http://192.168.5.230:23011/api/v1/latest?platform=linux"
curl -O "http://192.168.5.230:23011/download/windows/pan4dex-1.9.028.zip"
```

`latest` 返回 `version/size/sha256/notes/download_url`；没有版本时返回 404 `no_release`。
下载响应带 `X-Checksum-Sha256` 头。

## 临时前台运行（调试）

```bash
uv sync
PAN4DEX_UPDATE_DATA_DIR=./data \
PAN4DEX_UPDATE_ADMIN_PASSWORD='临时口令' \
uv run python app.py
```

正式环境用上面的 systemd 服务，进程退出后自动拉起。

## 数据与备份

- 备份整个 `data/` 目录（SQLite、产物、`secret.key`、`logs/admin.log`）。
- 每个平台约 100 MB/版本；管理页显示磁盘余量。
- 审计日志：`data/logs/admin.log`（时间、IP、动作、版本、SHA-256）。

## 测试

```bash
cd server/update-server
uv sync --extra dev
uv run pytest -q
```

## 安全说明

- 仅用于局域网，默认 HTTP；管理口令 + 会话 + CSRF + 登录限速，上传/删除写审计日志。
- 客户端依赖 SHA-256 防止坏包；不防局域网内主动篡改 manifest 的中间人（见 `docs/update.md` 第 7 节）。
- 不要把 23011 映射到公网。
