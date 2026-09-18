# Pan4dex 万格 — 构建指南

本文档说明如何在不同环境下构建 Pan4dex 的 Windows 和 Linux 版本。

## 📋 概述

| 平台 | 构建方式 | 推荐场景 | 产物位置 |
|---|---|---|---|
| **Linux** | Docker 构建（唯一入口） | 所有环境（包括 Windows 主机） | `releases/pan4dex-<版本>-linux` |
| **Windows** | PyInstaller 本机构建 | 快速测试、本地开发 | `releases/pan4dex-<版本>/` + `.zip` |

**版本号来源**: `config/app_config.py` 中的 `VERSION` 常量（构建脚本会自动更新 `BUILD_TIME`）。

---

## 🐧 Linux 版本构建

### 方式一：Docker 构建（推荐，所有环境统一使用）

#### 前置条件

1. **Docker 安装**（任意支持 Docker 的环境）:
   - Windows: Docker Desktop
   - macOS: Docker Desktop  
   - Linux: `docker.io` + `docker-compose`

2. **Kali Linux 230 远程访问**（可选）:
   ```bash
   # SSH 连接到 230
   ssh kali@192.168.x.x  # 替换为实际 IP
   
   # 或使用 xrdp 图形界面
   xfreerdp /v:192.168.x.x /u:kali
   ```

#### 构建步骤

##### A. 在本地 Docker 构建（推荐）

```bash
# 1. 克隆项目
cd /home/kali/workspace/pan4dex

# 2. 确保脚本可执行
chmod +x scripts/build-linux-docker.sh

# 3. 运行构建（自动推送镜像到 230）
bash scripts/build-linux-docker.sh

# 或指定版本号
bash scripts/build-linux-docker.sh 1.9.021
```

**产物位置**: `releases/pan4dex-<版本>-linux`（在构建机本地）

##### B. 在 230 上直接构建

```bash
# 1. SSH 登录 230
ssh kali@192.168.x.x

# 2. 进入项目目录
cd /home/kali/workspace/pan4dex

# 3. 拉取最新代码（如需要）
git pull origin main

# 4. 运行构建脚本
bash scripts/build-linux-docker.sh

# 5. 查看产物
ls -lh releases/pan4dex-*-linux
```

#### Docker 镜像细节

- **基础镜像**: `python:3.11-bullseye` (glibc 2.31)
- **构建层**: `docker/Dockerfile-linux`
- **关键依赖**:
  - `pillow-heif` (HEIC 解码)
  - `exiftool` (元数据提取)
  - `7zz` (压缩工具)
  - Qt6 输入法插件

#### 构建输出

```bash
releases/
└── pan4dex-1.9.020-linux    # onefile 可执行文件 (约 82MB)
```

---

### 方式二：降级路线（仅当 Docker 不可用时）

```bash
# 注意：此方式功能不完整，缺少输入法插件和内置工具
pyinstaller packaging/pan4dex.spec
```

**差异**: 
- ❌ 不带 Qt6 输入法插件
- ❌ 不带 `resources/tools/` 下的 ExifTool 和 7zz
- ❌ 不做 Windows 侧 imageformats/winpty 处理

---

## 🪟 Windows 版本构建

### 前置条件

1. **Python 3.10+**
   ```powershell
   python --version  # 应显示 3.10.0 或更高
   ```

2. **PyInstaller 6.0+**
   ```powershell
   pip install -r requirements-dev.txt
   ```

3. **PowerShell 5.1+** 或 **Git Bash**

### 构建步骤

#### A. 标准构建（推荐）

```powershell
# 1. 进入项目目录
cd C:\workspace\Pan4dex

# 2. 激活虚拟环境（如使用）
.\.venv\Scripts\activate

# 3. 运行构建脚本
python scripts/build_windows.py

# 或指定版本号
python scripts/build_windows.py 1.9.021
```

#### B. 手动构建（调试用）

```powershell
# 1. 检查配置
Get-Content config\app_config.py | Select-String "VERSION|BUILD_TIME"

# 2. 运行 PyInstaller
pyinstaller pan4dex.spec

# 3. 验证产物
Test-Path dist\pan4dex.exe
```

### 构建输出

```bash
releases/
├── pan4dex-1.9.020/           # 解压版目录
│   ├── pan4dex.exe
│   └── _internal/             # 依赖库
└── pan4dex-1.9.020.zip        # 压缩包 (约 58MB)
```

---

## 🔧 230 Kali Linux 上的 Docker 构建详解

### 为什么推荐在 230 上构建？

1. **真机环境**: 与用户实际使用环境一致
2. **网络路径测试**: 可直接验证 SMB/NFS 等网络挂载
3. **输入法验证**: 可测试 fcitx5/ibus 输入行为
4. **Wayland/X11**: 可验证不同桌面环境兼容性

### 在 230 上构建的完整流程

#### 1. 环境准备

```bash
# SSH 登录 230
ssh kali@192.168.x.x

# 检查 Docker
docker --version
docker compose version

# 确认项目目录
cd /home/kali/workspace/pan4dex
git status
```

#### 2. 清理旧产物

```bash
# 清理构建缓存
rm -rf build/ build_onefile/ dist/ dist_onefile/

# 清理旧发布包（保留最近 3 个）
ls -lt releases/pan4dex-*-linux | tail -n +4 | awk '{print $NF}' | xargs rm
```

#### 3. 执行构建

```bash
# 方式 A: 后台构建（推荐，避免 SSH 断开）
screen -S pan4dex-build
bash scripts/build-linux-docker.sh
# Ctrl+A D 脱离 screen

# 方式 B: tmux 构建
tmux new -s pan4dex-build
bash scripts/build-linux-docker.sh
# Ctrl+B D 脱离 tmux

# 方式 C: nohup 构建
nohup bash scripts/build-linux-docker.sh > build.log 2>&1 &
```

#### 4. 监控构建进度

```bash
# 查看日志
tail -f build.log

# 或重新 attach screen/tmux
screen -r pan4dex-build
tmux attach -t pan4dex-build
```

#### 5. 验证产物

```bash
# 文件大小
ls -lh releases/pan4dex-*-linux

# 文件类型
file releases/pan4dex-*-linux

# 动态库依赖（不应有未找到）
ldd releases/pan4dex-*-linux | grep "not found"

# 启动测试（临时）
./releases/pan4dex-1.9.020-linux --help
```

#### 6. 上传到发布目录

```bash
# 创建发布目录
mkdir -p ~/pan4dex-releases/$(date +%Y%m%d)

# 复制产物
cp releases/pan4dex-*-linux ~/pan4dex-releases/$(date +%Y%m%d)/

# 生成校验和
cd ~/pan4dex-releases/$(date +%Y%m%d)
sha256sum pan4dex-*-linux > checksums.txt

# 传输回本机（可选）
scp -r ~/pan4dex-releases/ kali@192.168.x.x:/home/kali/workspace/pan4dex/releases/
```

---

## 🧪 构建后验证清单

### Linux 产物验证

```bash
# 1. 基本检查
file releases/pan4dex-*.linux
# 应显示：ELF 64-bit LSB executable, x86-64

# 2. 依赖检查
ldd releases/pan4dex-*.linux | grep "not found"
# 应为空（除系统库外）

# 3. HEIC 支持验证
python3 -c "from PIL import Image; print('pillow-heif' in str(Image.EXTENSION))"

# 4. 启动测试（无头模式）
./releases/pan4dex-1.9.020-linux --test-mode &
sleep 2
pgrep -f pan4dex
```

### Windows 产物验证

```powershell
# 1. 文件检查
Test-Path dist\pan4dex.exe

# 2. 依赖检查（使用 Dependency Walker 或 dumpbin）
dumpbin /dependents dist\pan4dex.exe

# 3. 启动测试
.\dist\pan4dex.exe --test-mode
```

---

## 🚨 常见问题

### Q1: Docker 构建失败 - "cannot find docker daemon"

**A**: 确保 Docker 服务已启动

```bash
# Linux
sudo systemctl start docker

# Windows
# 打开 Docker Desktop 应用
```

### Q2: Windows 构建卡住 - "ImportError: DLL load failed"

**A**: 检查 Python 架构是否匹配

```powershell
# 应显示 AMD64
python -c "import struct; print(struct.calcsize('P') * 8)"
```

### Q3: 产物缺少 HEIC 支持

**A**: 确认 pillow-heif 已正确安装

```bash
# Docker 内检查
docker run --rm pan4dex-build python -c "import pillow_heif; print(pillow_heif.__version__)"

# 或在 230 上重建镜像
docker system prune -a
bash scripts/build-linux-docker.sh
```

### Q4: 230 上构建速度慢

**A**: 使用镜像缓存和后台构建

```bash
# 先拉取基础镜像
docker pull python:3.11-bullseye

# 使用 screen/tmux 后台构建
screen -S build && bash scripts/build-linux-docker.sh
# 脱离后继续构建，SSH 断开也不影响
```

---

## 📊 构建时间参考

| 平台 | 首次构建 | 增量构建 | 备注 |
|---|---|---|---|
| **Linux (Docker)** | 15-20 分钟 | 5-8 分钟 | 取决于网络和 CPU |
| **Windows (本机)** | 10-15 分钟 | 3-5 分钟 | PyInstaller 打包耗时 |

---

## 🔗 相关文档

- [`docs/development-guide.md`](file:///c:/workspace/Pan4dex/docs/development-guide.md#L189-L213) - 开发指南第 5 节
- [`docker/README.md`](file:///c:/workspace/Pan4dex/docker/README.md) - Docker 镜像说明
- [`scripts/build-linux-docker.sh`](file:///c:/workspace/Pan4dex/scripts/build-linux-docker.sh) - Linux 构建脚本
- [`scripts/build_windows.py`](file:///c:/workspace/Pan4dex/scripts/build_windows.py) - Windows 构建脚本

---

**文档版本**: v1.0  
**最后更新**: 2026-09-18
