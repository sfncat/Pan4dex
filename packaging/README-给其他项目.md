# 给其他 Qt6 项目：复用 PyQt6 Linux 构建基座

> 配套文件：`Dockerfile-qt6-builder`（本目录）。要共享基座，**只需拷这一个文件**（或推送镜像给对方）。
> 基座实测环境：Debian 11 bullseye / **glibc 2.31**、Python 3.11.13。

## 这是什么 / 解决什么
一个**通用 PyQt6 Linux 构建底座**。任何 PyQt6 项目 `FROM` 它，就能在**低 glibc(2.31)** 环境里用 PyInstaller 编 out onefile，产物向后兼容老系统；不必各自重搭 Qt6/xcb 运行库，也不必处理 bullseye EOL 的 apt 换源（基座里已解决）。

## 基座里【有】什么（版本已锁，可复现）
- `python:3.11-bullseye`（Python 3.11.13，glibc 2.31）
- Qt6 构建运行库（apt）：`libxcb* / libxkbcommon-x11 / libgl1/libegl-mesa / libfontconfig1 / libfreetype6 / libx11-xcb / libxi/libxrender / libdbus / libssl / libgtk-3 / libgdk-pixbuf / libatk / libglib` + `xvfb`
- pip（锁版本）：`PyQt6==6.9.1`、`PyQt6-Qt6==6.9.2`、`PyQt6-sip==13.12.0`、`PyInstaller==6.22.3`
- 自动把 apt 源指向 `archive.debian.org`（bullseye 已 EOL）并带重试/精简索引，规避“Unable to locate package”
- `QT_QPA_PLATFORM=offscreen` + `ENTRYPOINT` 起 `Xvfb :99`（PyInstaller 分析期 import Qt 需要 display）

## 基座里【没有】什么（各项目自备）
- ❌ 你的 Python 依赖（numpy/requests/你的库…）——在你自己的 Dockerfile 里 `pip install`
- ❌ 中文字体——要中文显示：自行“打进产物”或“运行镜像装 `fonts-noto-cjk`”
- ❌ 输入法引擎(ibus/fcitx)、运行时环境、`.dockerignore`、构建编排脚本——各自按项目写

## 快速接入（三步）
```bash
# 1) 建基座（在有外网/或按需代理的构建机上）
docker build --network=host -f Dockerfile-qt6-builder -t qt6-builder-bullseye:py311 .
```
```dockerfile
# 2) 你的 Dockerfile
FROM qt6-builder-bullseye:py311
WORKDIR /app
RUN pip install --only-binary=:all: "你的依赖==版本" ...
COPY . .
```
```bash
# 3) 打包（示例；换成你项目的入口/参数）
docker run --rm -v "$PWD":/app <你的镜像> \
  pyinstaller --onefile --windowed --name=yourapp yourapp.py
```

## 两种共享方式（二选一）
1. **拷文件**：把 `Dockerfile-qt6-builder` 放进对方仓库，对方自己 `docker build`。
2. **推镜像**：你 `docker build` 后 `docker push registry/你的空间/qt6-builder-bullseye:py311`，对方直接 `FROM` 该地址，连文件都不用拿。

## 为什么用 bullseye / glibc 2.31
PyInstaller 产物动态链接构建机的 glibc。新发行版（Ubuntu 22.04=2.35、Debian 12=2.36…）直接编会把高版本 glibc 烧进产物，老机跑不了。锁 bullseye(2.31) → 产物能跑在 glibc ≥ 2.31 的系统（Ubuntu 20.04 / Debian 11 及以上）。想更保守可换 Debian 10 buster(2.28，但更 EOL、apt 更难)；能接受 ≥2.35 则可换 bookworm/jammy（在支持期、apt 更顺）。

## 注意事项 / FAQ
- **`--network=host`**：构建时需要能出网（apt 从 archive、pip 从 PyPI、pull python 基础镜像）。在配了本机代理的环境里，**别给容器配 `127.0.0.1` 回环代理**（容器到不了宿主机 loopback，会把 apt 卡成“索引残缺”）。直连够快就直连；必须走代理就用容器可达地址（`host.docker.internal` + `--add-host=...:host-gateway`，且代理要监听 LAN）。
- **换 Qt/PyInstaller 版本**：直接改 `Dockerfile-qt6-builder` 里的 pin；或 fork 一份你自己的 tag。基座刻意保持“只含通用件”，别把项目依赖塞回来。
- **产物缺字体/输入法**：那是“显示/输入”的运行时问题，跟能否构建无关；见上面“没有”清单自行补齐。
- 本文件与基座源自 Pan4dex 项目实践，通用部分已剥离项目耦合，可直接复用。
