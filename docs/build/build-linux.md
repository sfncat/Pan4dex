# 构建 Linux 版（Docker）

> 最后更新：2026-10-19 ｜ 产物：`releases/pan4dex-<版本>-linux`（onefile ELF）
> 本文覆盖两个宿主场景，但**共用同一份 Dockerfile 和同一个构建脚本**：
> - **L1** 就在 Linux 机器上 + Docker
> - **L2** 在 Windows 上，经 WSL2 + Docker

## 为什么 Linux 要用 Docker 编（glibc 兼容性）

PyInstaller 产物动态链接宿主 glibc。**主用发行版（Ubuntu 24.04 / Fedora / Debian 12 等）glibc 版本偏高**（如 2.39），直接在其上编出的 ELF 拿到老系统就 `GLIBC_x.y not found`。解决办法：把构建钉在**低 glibc 基座**里。

Pan4dex 用 `packaging/Dockerfile-linux`，基座 `python:3.11-bullseye`（Debian 11，glibc 2.31）。产物 `file` 显示 `for GNU/Linux 3.2.0`，向后兼容性好。**这就是 Linux 版“必须用 Docker 编”的根本原因**，不是偏好。

> 因为 bullseye 已 EOL，`packaging/Dockerfile-linux` 把 apt 源改到了 `archive.debian.org` 并关 `Check-Valid-Until`（否则 `apt-get update` 一堆 `+deb11uNN` 404 → exit 100）。archive 无 security 通道——**这是编译镜像不是运行环境，可接受**。

## 关键约束：Dockerfile 唯一

L1 与 L2 **必须**用同两份东西，别为不同宿主复制：
- 构建脚本（唯一入口）：`scripts/build-linux-docker.sh`
- 镜像定义（唯一）：`packaging/Dockerfile-linux`

`build-linux-docker.sh` 对宿主是 WSL 还是裸 Linux **完全无感**：它 `docker build -f packaging/Dockerfile-linux`（带 `--network=host`）→ 起容器跑 `pyinstaller --onefile --windowed` → 产物挪到 `releases/pan4dex-<版本>-linux`。
差异**只在“前置准备/过程”**（下 L2 多出来的 WSL 网络/CRLF 处理），产物字节一致。

⚠️ `docker/` 目录（`Dockerfile`/`entrypoint.sh`/`build.sh`）是**冻结的历史副本，不参与构建**；要改构建只改 `packaging/Dockerfile-linux`。

## 通用准备：源码放原生目录 + 去 CRLF

**别在 `/mnt/c/...` 上直接构建**：跨系统 IO 慢，且从 Windows 工作树带来的 `*.sh` 常含 **CRLF**，被 WSL bash 读会崩：
`set: - invalid option`、`$'\r': command not found`、`syntax error near unexpected token $'do\r'`。

```bash
SRC=/mnt/c/workspace/Pan4dex; D=$HOME/pan4dex-build
rsync -a --exclude=.venv --exclude=releases --exclude=dist --exclude=build \
      --exclude=__pycache__ --exclude='*.log' --exclude='*.zip' --exclude=.git \
      "$SRC/" "$D/"
find "$D" -type f -name '*.sh' ! -path '*/.git/*' -exec sed -i 's/\r$//' {} +
bash -n "$D/scripts/build-linux-docker.sh" && echo SH_OK
```

> 去 CR 只准 `sed -i 's/\r$//'` 或 `tr -d '\r'`。**绝不要用 `sed 's/[\r][^X]//'`**——在 sed 里 `[\r]` 是“反斜杠**或**字母 r”，会把每个 `docker` 里的 `r` 连后一个字符一起删，直接毁脚本。
> 若用统一编排器 `python scripts/build.py linux`，它对 CRLF 工作树已自动用“去 CR 的同目录临时副本”执行，无需手动处理。

---

## L1：在 Linux 机器上 + Docker

### 前置
```bash
curl -fsSL https://get.docker.com -o /tmp/gd.sh && sudo sh /tmp/gd.sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"    # 重新登录生效；免 sudo 用 docker
docker info >/dev/null && echo OK
```
境外源慢/不可达时给 Docker 配代理（`~/.docker/config.json` 的 `proxies`，`--network=host` 已在构建脚本内）：
```json
{"proxies":{"default":{"httpProxy":"http://127.0.0.1:20170","httpsProxy":"http://127.0.0.1:20170","noProxy":"localhost,127.0.0.1,::1"}}}
```

### 构建
```bash
cd ~/pan4dex-build
bash scripts/build-linux-docker.sh           # 或： python scripts/build.py linux --env bare
bash scripts/build-linux-docker.sh 1.9.024   # 指定版本
```
首次会 `docker build` 镜像（拉 bullseye 基座 + apt + pip 装 PyQt6/PyInstaller，较慢）；之后 `pan4dex-builder-linux` 被缓存，重建只跑 PyInstaller，数分钟完成。

### 验证
```bash
file releases/pan4dex-*-linux                     # ELF 64-bit LSB executable, x86-64
QT_QPA_PLATFORM=offscreen ./releases/pan4dex-<版本>-linux --version
```

---

## L2：在 Windows 上，经 WSL2 + Docker

前提：WSL 平台 ≥ 3.0、Ubuntu 发行版、systemd 开启。

### 1) WSL 平台与发行版
```powershell
wsl --update                      # 升到 3.0.x（商店没推就 wsl --update --web-download）
wsl --install -d Ubuntu-24.04 --no-launch
```
`/etc/wsl.conf` 需 `[boot] systemd=true`（Docker 依赖），改后 `wsl --shutdown` 生效。

### 2) 网络/代理（关键，否则境外源慢到不可用）
WSL 默认 **NAT 不走** Windows 上只监听 `127.0.0.1` 的代理（如 v2rayA）。最省事：改 `%UserProfile%\.wslconfig`：
```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
```
然后 `wsl --shutdown` 再进。mirrored 让 WSL 共享宿主机回环 → WSL 与容器都能直连 `127.0.0.1:20170`，**不必把代理暴露到局域网、也不动防火墙**。并按 L1 给 `~/.docker/config.json` 配代理。**构建必须 `--network=host`**，否则容器里的 `127.0.0.1` 到不了宿主代理 → apt `exit 100`（`build-linux-docker.sh` 已带此参数）。

### 3) Docker Engine（WSL 内）+ 默认不自启
```bash
curl -fsSL https://get.docker.com -o /tmp/gd.sh && sudo sh /tmp/gd.sh
sudo usermod -aG docker "$USER"
sudo systemctl disable docker docker.socket   # 不想每次开 WSL 都拉起 dockerd（按需启动）
```
默认不自启后，跑构建前需 `sudo systemctl start docker`。`python scripts/build.py linux` 会在检测 daemon 没运行时**按需启动**（幂等）。

### 4) 构建
在 WSL 里（源码按上文放原生目录、去 CRLF）：
```bash
cd ~/pan4dex-build
python scripts/build.py linux          # env 自动判定为 wsl；确保 daemon、去 CRLF、转交 build-linux-docker.sh
# 或手动： bash scripts/build-linux-docker.sh
```

### 5) 产物 → 回 Windows
产物在 `~/pan4dex-build/releases/pan4dex-<版本>-linux`。要放回 Windows 仓库 `releases/`：
```bash
cp ~/pan4dex-build/releases/pan4dex-<版本>-linux /mnt/c/workspace/Pan4dex/releases/
```

---

## 中文：显示（已打进包） vs 输入（只能宿主）

- **显示**：`resources/fonts/NotoSansCJK-Regular.ttc` 经 `build-linux-docker.sh` 的 `ADD_SPECS` 打进 onefile，`main.py` 在 `QApplication` 创建后用 `QFontDatabase.addApplicationFont` 注册。**目标机不装中文字体也不乱码**（实测：零中文字体容器里 `fc-list :lang=zh=0`，产物仍注册内置字体并正常渲染）。
- **输入**：Qt 输入插件（`libibus`/`libcompose`）随 PyQt6 wheel 已打进包；`main.py` 启动会自动探测系统 `fcitx5`/`ibus-daemon` 并设 `QT_IM_MODULE`。但**输入法引擎（ibus/fcitx + 拼音词库）是系统服务，无法打进单文件包**——目标机需运行相应输入法才能“打字中文”。
  - 想支持 fcitx5 桌面：把对应 Qt6 插件放进 `resources/tools/qt6-im-plugins/`，构建脚本会一并打入 `PyQt6/Qt6/plugins/platforminputcontexts`。

## 运行产物（验证效果）

- **原生 WSLg 直跑**（开发最快）：Ubuntu 内 `DISPLAY=:0`，GUI 程序会直接在 Windows 弹窗；需该 Ubuntu 已装 `fonts-noto-cjk`（显示）和 `ibus ibus-libpinyin`（输入，`ibus-daemon` 跑起来）。GUI 要在**开着的终端里前台运行**。
- **运行时镜像（开箱即用/可分发）**：`packaging/Dockerfile-runtime` = ubuntu24.04 + Qt/xcb 运行库 + 字体 + ibus + libpinyin + 烘入的 app：
  ```bash
  docker build --network=host -f packaging/Dockerfile-runtime -t pan4dex-runtime:latest .
  docker run -d --name pan4dex-gui --network=host \
    -e DISPLAY=:0 -e XDG_RUNTIME_DIR="/run/user/$(id -u)" -e WAYLAND_DISPLAY=wayland-0 \
    -v /tmp/.X11-unix:/tmp/.X11-unix -v /mnt/wslg:/mnt/wslg \
    -v "/run/user/$(id -u):/run/user/$(id -u)" \
    pan4dex-runtime:latest
  ```
  窗口里 `Super + 空格` 切拼音。停止：`docker rm -f pan4dex-gui`。

## 手动/降级路线（仅 Docker 不可用时）
```bash
pyinstaller packaging/pan4dex.spec      # 注意用 packaging/ 那份；根目录同名 spec 是残件
```
差异：不带 `resources/tools/` 的 exiftool/7zz、可能缺输入法插件与内置工具，产物偏小、功能不全。**正式产物一律走 Docker。**

## 重建镜像的时机
脚本“镜像已存在就复用”。改了 `packaging/Dockerfile-linux` 后需让它重建：
```bash
docker rmi pan4dex-builder-linux && bash scripts/build-linux-docker.sh
```
（想对镜像做 A/B、不动旧 tag：`DOCKER_IMAGE=pan4dex-builder-linux:py311 bash scripts/build-linux-docker.sh`。）

相关：总则 [README.md](README.md)，Windows [build-windows.md](build-windows.md)，旧多机编排 [legacy-multimachine.md](legacy-multimachine.md)。
