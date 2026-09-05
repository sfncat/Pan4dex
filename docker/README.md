# Pan4dex Linux Docker 构建指南

基于 Debian bullseye（glibc 2.31）的 Docker 构建方案，解决 Kali Linux glibc 版本过高导致目标机无法运行的问题。

> **当前入口**：`scripts/build-linux-docker.sh`（构建镜像 `packaging/Dockerfile-linux`）
> **本 `docker/` 目录**：早期方案的历史副本（`Dockerfile`/`entrypoint.sh`）与兼容封装（`build.sh`），仅供追溯，请勿作为修改基准。

## 背景

Kali Linux 滚动版的 glibc 版本（2.39）过高，直接在 Kali 上编译的 PyInstaller 包在目标机（gti, glibc 2.35）上会报 `GLIBC_2.xx not found`。

Docker 容器使用 Debian bullseye（glibc 2.31），编译出的二进制文件可向下兼容到 glibc 2.28+ 的所有 Linux 发行版。

## 环境要求

- Docker Engine（230 已就绪；构建命令需要 `sudo`）
- 目标机 glibc ≥ 2.28（推荐 ≥ 2.31）

## 快速开始

### 1. 构建版本

```bash
cd /home/kali/workspace/pan4dex
bash scripts/build-linux-docker.sh 0.9.657
```

- 版本号参数可省略：不传时读取 `config/app_config.py` 的 `VERSION`
- 产物：`releases/pan4dex-0.9.657-linux`（单文件 ~81MB）
- 构建脚本会自动处理（详见下方「版本号与编译时间」）

### 2. 部署到目标机

```bash
scp releases/pan4dex-0.9.657-linux gti:~/tools/pan4dex/
ssh gti 'chmod +x ~/tools/pan4dex/pan4dex-0.9.657-linux'
```

## 版本号与编译时间

版本号 / 编译时间统一放在 `config/app_config.py`（不再写进 main.py 等逻辑代码）：

- 改版本号：编辑 `config/app_config.py` 的 `VERSION`（或构建时传参）
- 构建脚本在容器内执行两条 `sed` 强制覆盖：
  - `VERSION` ← 传入的版本号（**必须覆盖**：构建现场源码可能滞后，否则打包进程序的版本号与产物名不一致）
  - `BUILD_TIME` ← 宿主按 `TZ=Asia/Shanghai` 算好注入（**不能用容器内 `date`**：Docker 默认 UTC，会差 8 小时）
- 源码开发运行时 `BUILD_TIME` 保持空字符串，打包时才写入

## 构建脚本做了什么

`scripts/build-linux-docker.sh` 流程：

1. 启动 Docker（如未运行）
2. `docker build --network=host` 构建镜像 `pan4dex-builder-linux`（`packaging/Dockerfile-linux`）——`--network=host` 解决容器内 DNS 解析失败
3. `docker run` 挂载项目根目录到 `/app`，容器内：
   - `sed` 覆盖 `config/app_config.py` 的 `VERSION` / `BUILD_TIME`
   - `pyinstaller --onefile --windowed --name=pan4dex`，**显式打包资源**：
     - `resources/icons`（图标，否则任务栏/文件管理器显示默认图标）
     - `resources/themes`（主题）
     - `resources/tools/exiftool-linux`（应用内携带的 ExifTool Perl 包，拍摄日期列用系统 perl 运行）
     - **注意**：不打包 `resources/tools/exiftool`（Windows 专用 exe + Perl 运行时）
   - 产物移动到 `releases/pan4dex-${VERSION}-linux` 并加可执行位

## 目录结构

```
scripts/build-linux-docker.sh    # canonical 构建脚本（唯一维护点）
packaging/Dockerfile-linux       # canonical 构建镜像
config/app_config.py             # 版本号 / 编译时间 / 应用元数据
docker/
├── README.md                    # 本文档
├── build.sh                     # 薄封装：转发给 scripts/build-linux-docker.sh（兼容旧习惯）
├── Dockerfile                   # 历史副本，与 packaging/Dockerfile-linux 一致（勿改）
└── entrypoint.sh                # 历史入口脚本（packaging 镜像已内联同样的逻辑，仅供参考）
```

## 镜像要点

- 基础镜像 `python:3.10-bullseye`（glibc 2.31）
- Qt6 运行时库齐全，额外包含：
  - `libxcb-cursor0`：Qt6 xcb 平台插件硬依赖
  - `libgtk-3-0` / `libgdk-pixbuf-2.0-0` / `libatk1.0-0` / `libglib2.0-0`：qgtk3 主题插件；这些库会被 PyInstaller 收集进 onefile，避免目标机器缺库
- PyQt6 用 manylinux_2_28 预编译 wheel（`--only-binary=:all:`），依赖：PyInstaller / send2trash / Pillow / qdarkstyle / cairosvg / pyte
- 入口脚本内联创建：启动 Xvfb `:99` 虚拟显示后执行命令

### 为什么选 Debian bullseye？

| 发行版 | glibc | PyQt6 wheel | 兼容性 | 状态 |
|--------|-------|-------------|--------|------|
| Debian bullseye | 2.31 | ✅ manylinux_2_28 | ✅ 兼容 gti 2.35 | ✅ 使用中 |
| Debian bookworm | 2.36 | ✅ manylinux_2_28 | ❌ 不兼容 gti 2.35 | ❌ 已弃用 |
| Ubuntu 20.04 | 2.31 | ❌ 无系统 PyQt6 | ⚠️ 需 pip 编译 | ⚠️ 复杂 |
| manylinux2014 | 2.17 | ❌ 无 PyQt6 wheel | ✅ 最广泛 | ❌ yum 源 EOL |
| Kali（本机） | 2.39 | ✅ | ❌ 不兼容 gti | ❌ 问题根源 |

**关键决策点**：
1. PyQt6 官方 wheel 要求 glibc ≥ 2.28（manylinux_2_28 标签）
2. 目标机 gti glibc 2.35，需要构建环境 glibc ≤ 2.35
3. bullseye 的 glibc 2.31 满足：2.28 ≤ 2.31 ≤ 2.35
4. manylinux2014 虽然 glibc 更低（2.17），但 PyQt6 没有对应 wheel，且 yum 源已 EOL

## 常见问题

### Q: 容器内 DNS 解析失败

构建已用 `docker build --network=host`，一般不会再遇到；仍失败可检查 Docker DNS：
```bash
echo '{"dns": ["8.8.8.8", "223.5.5.5"]}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

### Q: 打包出的版本号 / 编译时间不对

- 版本号：确认构建时传了版本号（`bash scripts/build-linux-docker.sh 0.9.657`），脚本会在容器内强制覆盖 `config/app_config.py` 的 `VERSION`
- 编译时间：确认宿主是东八区（或脚本的 `TZ=Asia/Shanghai` 生效）；不要依赖容器内 `date`（UTC 差 8 小时）

### Q: 构建时找不到 PyQt6

确保使用 `--only-binary=:all:` 参数，避免 pip 尝试从源码编译：
```bash
pip install --only-binary=:all: PyQt6 PyQt6-Qt6 PyQt6-sip
```

### Q: 启动报错 `GLIBC_2.36 not found`

基础镜像 glibc 版本过高，确保使用 `python:3.10-bullseye` 而非 `python:3.10-bookworm`。

### Q: 打包版双击文件没反应 / 打开应用立即退出

PyInstaller 打包版运行时会把 `LD_LIBRARY_PATH` 指向打包目录（内含旧版 glib/gtk），子进程（gedit/eog 等系统应用）继承后会加载旧库与系统版本冲突（`symbol lookup error`）立即退出。应用内已处理：启动外部应用时剔除 `LD_LIBRARY_PATH`/`LD_PRELOAD`（`config/file_associations.py` 的 `_clean_child_env`）。若仍打不开，看子进程 stderr 落盘 `/tmp/pan4dex_open_stderr.log`。

### Q: 构建产物过大

正常产物约 75-85MB（包含 PyQt6 + Python 运行时 + 资源文件 + ExifTool）。如果只有 8-10MB，说明 PyQt6 没有正确打包。

## 历史沿革

- `docker/build.sh`（旧）：直接从 `main.py` 提取 `__version__`、sed 改写 `main.py` 的 `__build_time__`——已废弃（版本/时间改由 `config/app_config.py` 管理）
- `scripts/build.sh`：更早的远程构建方案（Linux 在 gti 远程构建）——已废弃
- 当前方案：`scripts/build-linux-docker.sh` + `packaging/Dockerfile-linux`（Linux 在 Docker 构建；Windows 仍由本机 `scripts/build_windows.py` 构建）
