# 给其他 Qt6 项目：复用 PyQt6 Linux 构建基座

> 配套文件：`Dockerfile-qt6-builder`（本目录）。要共享基座，**只需拷这一个文件**（或推送镜像给对方）。
> 基座实测环境：Debian 12 bookworm / **glibc 2.36**、Python 3.11.x。

## 这是什么 / 解决什么
一个**通用 PyQt6 Linux 构建底座**。任何 PyQt6 项目 `FROM` 它，就能在**低 glibc(2.36)** 环境里用 PyInstaller 编 out onefile，产物向后兼容（glibc ≥ 2.36）；不必各自重搭 Qt6/xcb 运行库。

## 基座里【有】什么（版本已锁，可复现）
- `python:3.11-bookworm`（Python 3.11.x，glibc 2.36）
- Qt6 构建运行库（apt）：`libxcb* / libxkbcommon-x11 / libgl1/libegl-mesa / libfontconfig1 / libfreetype6 / libx11-xcb / libxi/libxrender / libdbus / libssl / libgtk-3 / libgdk-pixbuf / libatk / libglib` + `xvfb`
- pip（锁版本）：`PyQt6==6.12.0`、`PyQt6-Qt6==6.12.0`、`PyQt6-sip==13.13.0`、`PyInstaller==6.22.3`
- `QT_QPA_PLATFORM=offscreen` + `ENTRYPOINT` 起 `Xvfb :99`（PyInstaller 分析期 import Qt 需要 display）

## 基座里【没有】什么（各项目自备）
- ❌ 你的 Python 依赖（numpy/requests/你的库…）——在你自己的 Dockerfile 里 `pip install`
- ❌ 中文字体——要中文显示：自行“打进产物”或“运行镜像装 `fonts-noto-cjk`”
- ❌ 输入法引擎(ibus/fcitx)、运行时环境、`.dockerignore`、构建编排脚本——各自按项目写

## 快速接入（三步）
```bash
# 1) 建基座（在有外网/或按需代理的构建机上）
docker build --network=host -f Dockerfile-qt6-builder -t qt6-builder-bookworm:py311 .
```
```dockerfile
# 2) 你的 Dockerfile
FROM qt6-builder-bookworm:py311
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
2. **推镜像**：你 `docker build` 后 `docker push registry/你的空间/qt6-builder-bookworm:py311`，对方直接 `FROM` 该地址，连文件都不用拿。

## 为什么用 bookworm / glibc 2.36
PyInstaller 产物动态链接构建机的 glibc。锁 bookworm(2.36) → 产物能跑在 glibc ≥ 2.36 的系统（Debian 12 / Ubuntu 23.04+ / Fedora 37+）。基线不能再往下降：PyQt6 6.12 的 Linux wheel 只有 `manylinux_2_34`/`manylinux_2_39`，bullseye(2.31) 根本装不上。要覆盖 Debian 11 / Ubuntu 20.04/22.04 只能把 PyQt6 留在 6.9.x。

## 注意事项 / FAQ
- **`--network=host`**：构建时需要能出网（apt 从 deb.debian.org、pip 从 PyPI、pull python 基础镜像）。在配了本机代理的环境里，**别给容器配 `127.0.0.1` 回环代理**（容器到不了宿主机 loopback，会把 apt 卡成“索引残缺”）。直连够快就直连；必须走代理就用容器可达地址（`host.docker.internal` + `--add-host=...:host-gateway`，且代理要监听 LAN）。
- **换 Qt/PyInstaller 版本**：直接改 `Dockerfile-qt6-builder` 里的 pin；或 fork 一份你自己的 tag。基座刻意保持“只含通用件”，别把项目依赖塞回来。
- **产物缺字体/输入法**：那是“显示/输入”的运行时问题，跟能否构建无关；见上面“没有”清单自行补齐。
- 本文件与基座源自 Pan4dex 项目实践，通用部分已剥离项目耦合，可直接复用。
