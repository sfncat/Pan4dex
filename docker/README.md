# Pan4dex Docker 构建指南

基于 Debian bullseye（glibc 2.31）的 Docker 构建方案，解决 Kali Linux glibc 版本过高导致目标机无法运行的问题。

## 背景

Kali Linux 滚动版的 glibc 版本（2.39）过高，直接在 Kali 上编译的 PyInstaller 包在目标机（gti, glibc 2.35）上会报 `GLIBC_2.xx not found`。

Docker 容器使用 Debian bullseye（glibc 2.31），编译出的二进制文件可向下兼容到 glibc 2.28+ 的所有 Linux 发行版。

## 环境要求

- Docker Engine（已安装并配置 DNS）
- 目标机 glibc ≥ 2.28（推荐 ≥ 2.31）

## 目录结构

```
docker/
├── README.md              # 本文档
├── Dockerfile             # 基于 Debian bullseye 的构建镜像
├── build.sh               # 一键构建脚本
└── entrypoint.sh          # 容器入口脚本（Xvfb 虚拟显示）
```

## 快速开始

### 1. 安装 Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io

# 配置 DNS（解决容器内域名解析失败）
sudo mkdir -p /etc/docker
echo '{"dns": ["8.8.8.8", "223.5.5.5"]}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker

# 设置默认不启动
sudo systemctl disable docker.service docker.socket

# 添加当前用户到 docker 组
sudo usermod -aG docker $USER
# 重新登录后生效，或执行：
sg docker -c "docker run hello-world"
```

### 2. 构建镜像

```bash
cd /home/kali/workspace/pan4dex
sudo docker build -t pan4dex-builder-linux -f docker/Dockerfile .
```

### 3. 构建版本

```bash
cd /home/kali/workspace/pan4dex
bash docker/build.sh v0.9.50
```

产物：`releases/pan4dex-v0.9.50-linux`

### 4. 部署到目标机

```bash
scp releases/pan4dex-v0.9.50-linux gti:~/tools/pan4dex/pan4dex
ssh gti 'chmod +x ~/tools/pan4dex/pan4dex'
```

## Dockerfile 说明

```dockerfile
FROM python:3.10-bullseye

ENV QT_QPA_PLATFORM=offscreen

# 安装 Qt6 运行时库（glibc 2.31 ≤ gti 2.35，兼容）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-dev \
    libxkbcommon-dev \
    libxkbcommon-x11-0 \
    libegl1-mesa-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libx11-dev \
    libx11-xcb-dev \
    libxext-dev \
    libxfixes-dev \
    libxi-dev \
    libxrender-dev \
    libxcb1-dev \
    libxcb-glx0-dev \
    libxcb-keysyms1-dev \
    libxcb-image0-dev \
    libxcb-shm0-dev \
    libxcb-icccm4-dev \
    libxcb-sync-dev \
    libxcb-xfixes0-dev \
    libxcb-shape0-dev \
    libxcb-randr0-dev \
    libxcb-render-util0-dev \
    libdbus-1-dev \
    libssl-dev \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 用 pip 安装 PyQt6 预编译 wheel（manylinux_2_28，glibc 2.28+ 可运行）
RUN pip install --no-cache-dir --only-binary=:all: PyQt6 PyQt6-Qt6 PyQt6-sip && \
    pip install --no-cache-dir PyInstaller send2trash Pillow qdarkstyle cairosvg

WORKDIR /app
COPY . .

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
```

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

```bash
# 配置 Docker DNS
echo '{"dns": ["8.8.8.8", "223.5.5.5"]}' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

### Q: 构建时找不到 PyQt6

确保使用 `--only-binary=:all:` 参数，避免 pip 尝试从源码编译：
```bash
pip install --only-binary=:all: PyQt6 PyQt6-Qt6 PyQt6-sip
```

### Q: 启动报错 `GLIBC_2.36 not found`

基础镜像 glibc 版本过高，确保使用 `python:3.10-bullseye` 而非 `python:3.10-bookworm`。

### Q: 构建产物过大

正常产物约 55-65MB（包含 PyQt6 + Python 运行时 + 资源文件）。如果只有 8-10MB，说明 PyQt6 没有正确打包。

## 与 build.sh 的关系

- `scripts/build.sh`：旧方案，Linux 在 gti 远程构建，Windows 在 192.168.5.55 构建
- `docker/build.sh`：新方案，Linux 在本机构建（Docker），Windows 仍需 192.168.5.55

建议：Linux 包用 Docker 构建更方便，Windows 包仍用远程机器。
