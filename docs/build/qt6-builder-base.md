# 通用 PyQt6 构建基座 `qt6-builder-bookworm`

> 最后更新：2026-10-29 ｜ 定义文件：`packaging/Dockerfile-qt6-builder`
> 作用：给**任何 PyQt6 项目**提供一个「低 glibc(2.36) + Qt6/xcb 运行库 + PyInstaller」的现成构建底座，新项目不必从零搭。

## 为什么要有它
在 Linux 上编 PyQt6 单文件，两件事最费神：
1. **glibc 兼容**：直接在 Ubuntu 24.04+/新 Debian 上编，产物 glibc 要求高，拿不到老机器跑。要用低 glibc 基座（本基座 = Debian 12 bookworm / glibc 2.36）。
2. **wheel 的平台下限**：PyQt6 6.12 起 Linux wheel 只有 `manylinux_2_34`/`manylinux_2_39`（要 glibc ≥ 2.34），Debian 11 bullseye(2.31) 已装不上；能用 6.12 的最低受支持发行版就是 bookworm(2.36)。

基座把这两块**一次性固化**，上层项目只管装自己的 Python 依赖。

## 基座里有什么（锁版本，可复现）
| 类别 | 内容 |
|---|---|
| 基座 | `python:3.11-bookworm`（Python 3.11.x，**glibc 2.36**） |
| apt（运行/构建库） | xcb 全家桶、`libxcb-cursor0`、`libxkbcommon(-x11)`、`libgl1/libegl-mesa`、`libfontconfig1/libfreetype6`、`libgtk-3/libgdk-pixbuf/libatk/libglib`、`libdbus/libssl`、`xvfb` |
| pip（通用工具链） | `PyQt6==6.12.0` `PyQt6-Qt6==6.12.0` `PyQt6-sip==13.13.0` `PyInstaller==6.22.3` |
| 环境 | `QT_QPA_PLATFORM=offscreen`；`ENTRYPOINT` 起 `Xvfb :99` 后 `exec "$@"`（分析期 import Qt 需要 display） |

## 基座里**没有**什么（故意的）
- ❌ **项目专属 Python 库**（如 Pan4dex 的 `pillow-heif/qdarkstyle/send2trash/pyte`）——各自 `FROM` 后自己 `pip install`。
- ❌ **中文输入引擎**（ibus/fcitx + 词库）。它是**运行时**系统服务，不属于构建镜像。产物里带的是 wheel 自带的 Qt 输入插件（`libibus`/`libcompose`）；能否“打字中文”取决于**运行目标机**装了 ibus/fcitx。
- ❌ **中文字体**。中文显示要么把字体打进产物（`resources/fonts` + `QFontDatabase.addApplicationFont`），要么在运行镜像里装 `fonts-noto-cjk`。

## 怎么用（新项目三步）
1. 构建基座（一次）：
   ```bash
   docker build --network=host -f packaging/Dockerfile-qt6-builder -t qt6-builder-bookworm:py311 .
   ```
2. 你的项目 Dockerfile：
   ```dockerfile
   FROM qt6-builder-bookworm:py311
   WORKDIR /app
   RUN pip install --only-binary=:all: "你的依赖==x.y" ...   # 锁自己的版本
   COPY . .
   ```
3. 在你的 CI/脚本里用 `docker run --rm -v "$PWD":/app <your-image> pyinstaller --onefile --windowed ...` 出包。
   （Pan4dex 就是 `scripts/build-linux-docker.sh` 这么干的，可参考。）

> **网络两场景（详见 [build-linux.md](build-linux.md) §2）**：① 能直连就别配任何 Docker 代理（WSL mirrored 下直连境外源一般已够快）；② 要走本机代理就用**容器可达的地址**（`host.docker.internal` 或 WSL 端口转发），**永远别在 `~/.docker/config.json` 写 `http_proxy=http://127.0.0.1:…`**——容器（含 `--network=host`）到不了宿主机回环，会把 `apt-get update` 卡成“索引残缺 → Unable to locate package / exit 100”。`--network=host` 本身只是让 DNS/网络更稳，与是否走代理无关。

## 版本与共享
- 想换 Qt/PyInstaller 版本：改 `Dockerfile-qt6-builder` 里的 pin 并 `docker rmi` 旧 tag 重建；或 fork 一份自己 tag 的基座。基座刻意选的是 **PyQt6 6.12 能跑的最低可用组合（bookworm / glibc 2.36）**，别在基座里塞项目的怪版本。
- 跨机器共享基座：把它 `docker push` 到你们的镜像仓库（如 `registry.example.com/qt6-builder-bookworm:py311`），各项目 `FROM` 该地址；不方便用仓库时，就共享这个 `Dockerfile-qt6-builder` 文件，各自本地 build（结果一致，因为版本已锁）。
- 想更兼容老系统：PyQt6 6.12 已经做不到（Linux wheel 要 glibc ≥ 2.34）；真要覆盖 Debian 11 / Ubuntu 20.04/22.04，只能把 PyQt6 留在 6.9.x 并继续用 bullseye(2.31) 基座。

## 相关
- Pan4dex 自己的构建镜像：`packaging/Dockerfile-linux`（`FROM` 本基座 + Pan4dex 专属依赖）。
- Linux 构建总览：[build-linux.md](build-linux.md)。
- 运行期“开箱即用带中文/输入法”的镜像是另一个东西：`packaging/Dockerfile-runtime`（ubuntu24.04 + fonts-noto-cjk + ibus + libpinyin + 产物）。
