# Pan4dex v1.9.020 构建指南

## 📋 概述

本文档说明如何构建 Windows 和 Linux 版本的 Pan4dex v1.9.020。

---

## 🎯 版本信息

- **版本号**: v1.9.020
- **发布日期**: 2026-09-18
- **Git 标签**: v1.9.020
- **Git Commit**: b949648

---

## 🔧 系统要求

### Windows 构建环境

- **操作系统**: Windows 10/11
- **Python**: 3.13.x
- **依赖包**: 
  - PyQt6 >= 6.6.0
  - PyInstaller >= 6.0
  - send2trash
  - Pillow + pillow-heif
  - qdarkstyle
  - pyte
  - pywinpty (Windows 专用)

### Linux 构建环境

- **操作系统**: Ubuntu 24.04 或类似
- **Docker**: 已安装并运行
- **Python**: 3.11+
- **Docker 镜像**: pan4dex-builder-linux

---

## 🚀 快速构建

### 方法一：使用自动化脚本（推荐）

#### Windows:
```bash
cd c:\workspace\Pan4dex
python scripts\build_all.py
```

#### Linux:
```bash
cd /path/to/Pan4dex
python3 scripts/build_all.py
```

该脚本会自动检测操作系统并构建相应版本。

---

### 方法二：手动构建 Windows 版本

#### Step 1: 克隆代码
```bash
git clone https://github.com/sfncat/Pan4dex.git
cd Pan4dex
git checkout v1.9.020
```

#### Step 2: 安装依赖
```bash
pip install -r requirements.txt
pip install pyinstaller
```

#### Step 3: 运行构建脚本
```bash
python scripts\build_windows.py
```

#### Step 4: 验证产物
构建完成后，产物位于：
```
releases/pan4dex-1.9.020/
├── pan4dex.exe
├── imageformats/
└── resources/
```

---

### 方法三：手动构建 Linux 版本

#### Step 1: 克隆代码
```bash
git clone https://github.com/sfncat/Pan4dex.git
cd Pan4dex
git checkout v1.9.020
```

#### Step 2: 确保 Docker 运行
```bash
docker info
```

如果未运行：
```bash
sudo systemctl start docker
```

#### Step 3: 运行 Docker 构建脚本
```bash
bash scripts/build-linux-docker.sh
```

#### Step 4: 验证产物
构建完成后，产物位于：
```
releases/pan4dex-1.9.020-linux
```

添加执行权限：
```bash
chmod +x releases/pan4dex-1.9.020-linux
```

---

## 📦 构建产物说明

### Windows 版本

**类型**: 单目录应用（onedir）

**位置**: `releases/pan4dex-1.9.020/`

**结构**:
```
pan4dex-1.9.020/
├── pan4dex.exe           # 主程序
├── _internal/            # PyInstaller 内部文件
├── imageformats/         # 图片格式插件
│   ├── qgif.dll
│   ├── qjpeg.dll
│   └── ... (10 个 DLL)
├── resources/           # 资源文件
│   └── icons/
│       └── icon.ico
└── ...
```

**打包为 ZIP**:
```bash
# 自动完成，生成：
releases/pan4dex-1.9.020.zip (~57 MB)
```

---

### Linux 版本

**类型**: 单文件应用（onefile）

**位置**: `releases/pan4dex-1.9.020-linux`

**大小**: ~57 MB

**运行方式**:
```bash
./releases/pan4dex-1.9.020-linux
```

或使用 desktop 文件：
```bash
xdg-open pan4dex.desktop
```

---

## ⚠️ 常见问题

### Q1: Windows 构建失败 "Access is denied"

**原因**: PyInstaller 钩子需要访问系统资源

**解决方案**:
1. 以管理员身份运行 PowerShell/CMD
2. 或关闭杀毒软件/防火墙
3. 检查 temp 目录权限

### Q2: Linux 构建找不到 Docker

**原因**: Docker 未安装或未在 PATH 中

**解决方案**:
```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker
sudo systemctl start docker

# 将当前用户加入 docker 组（避免 sudo）
sudo usermod -aG docker $USER
# 注销后重新登录
```

### Q3: 缺少 imageformats 插件

**原因**: PyQt6 的 imageformats 目录未正确复制

**解决方案**:
```bash
# 手动复制
cp -r $(python -c "import PyQt6; print(Path(PyQt6.__file__).parent / 'Qt6' / 'plugins' / 'imageformats')" ) \
      releases/pan4dex-1.9.020/imageformats/
```

### Q4: 二进制比较功能不工作

**原因**: 可能缺少必要的依赖

**解决方案**:
- 确保 Pillow 已安装：`pip install Pillow pillow-heif`
- 检查 HEIC 支持：测试文件 `test_media/20180406_IMG_8002.HEIC`

---

## 🔍 验证构建

### Windows 验证

1. **运行程序**:
   ```cmd
   cd releases\pan4dex-1.9.020
   pan4dex.exe
   ```

2. **检查版本号**:
   - 帮助 → 关于
   - 应显示：v1.9.020

3. **测试新功能**:
   - 工具 → 文件比较（新增）
   - 压缩包处理 → 7Z/RAR（需安装外部工具）
   - 工具 → 用户操作配置（新增）

### Linux 验证

1. **运行程序**:
   ```bash
   ./releases/pan4dex-1.9.020-linux
   ```

2. **检查控制台输出**:
   ```bash
   ./releases/pan4dex-1.9.020-linux 2>&1 | head -20
   ```

3. **测试新功能**:
   - 工具菜单 → 文件比较
   - 压缩包处理 → 压缩格式选择
   - 工具 → 用户操作配置

---

## 📊 构建统计

### Windows 构建
- **构建时间**: ~3-5 分钟
- **产物大小**: ~57 MB (ZIP)
- **解压后**: ~120 MB

### Linux 构建
- **构建时间**: ~5-8 分钟（含 Docker 镜像拉取）
- **产物大小**: ~57 MB
- **类型**: 单文件可执行

---

## 🔄 CI/CD 集成建议

### GitHub Actions 示例

创建 `.github/workflows/build.yml`:

```yaml
name: Build Pan4dex

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller
      
      - name: Build Windows
        run: python scripts/build_windows.py
      
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: pan4dex-windows
          path: releases/pan4dex-${{ github.ref_name }}.zip

  build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Linux (Docker)
        run: bash scripts/build-linux-docker.sh
      
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: pan4dex-linux
          path: releases/pan4dex-${{ github.ref_name }}-linux
```

---

## 📝 发布清单

构建完成后，请确认以下内容：

- [ ] Windows 版本 (`pan4dex-1.9.020.zip`)
- [ ] Linux 版本 (`pan4dex-1.9.020-linux`)
- [ ] 发布说明 (`RELEASE-v1.9.020.md`)
- [ ] Git 标签 (`v1.9.020`)
- [ ] 更新 CHANGELOG.md
- [ ] 测试所有新功能
- [ ] 上传到 GitHub Releases

---

## 🆘 获取帮助

- **项目主页**: https://github.com/sfncat/Pan4dex
- **问题反馈**: https://github.com/sfncat/Pan4dex/issues
- **讨论区**: https://github.com/sfncat/Pan4dex/discussions

---

**最后更新**: 2026-09-18  
**版本**: v1.9.020
