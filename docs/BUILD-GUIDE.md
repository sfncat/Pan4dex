# Pan4dex 万格 — 构建指南

本文档说明如何在不同环境下构建 Pan4dex 的 Windows 和 Linux 版本。

## 📋 概述

| 平台 | 构建方式 | 推荐场景 | 产物位置 |
|---|---|---|---|
| **Linux** | Docker 构建（唯一入口） | 所有环境（包括 Windows 主机） | `releases/pan4dex-<版本>-linux` |
| **Windows** | PyInstaller 本机构建 | 快速测试、本地开发 | `releases/pan4dex-<版本>/` + `.zip` |

**版本号来源**: `config/app_config.py` 中的 `VERSION` 常量（构建脚本会自动更新 `BUILD_TIME`）。

---

## 🧭 仓库里脚本那么多，哪一条是入口

`scripts/` 与根目录攒了一堆构建/部署脚本，其中只有一小部分是活的。**2026-09-23 逐个打开核过**，
下表按「能不能拿来当入口」分类；判定依据写在括号里，别凭文件名猜。

| 状态 | 脚本 | 为什么 |
|---|---|---|
| ✅ 现行入口 | `scripts/build-linux-docker.sh` | Linux 唯一入口，产物 `releases/pan4dex-<版本>-linux` |
| ✅ 现行入口 | `scripts/build_windows.py` | Windows 本机入口；onedir，产物 `releases/pan4dex-<版本>/` + 同名 `.zip`，并把 `BUILD_TIME` 写回 `config/app_config.py` |
| ✅ 配套 | `scripts/install-linux.sh`、`packaging/pan4dex.spec`、`packaging/Dockerfile-linux` | 安装脚本 / 降级路线 spec / 镜像定义 |
| ⚠️ 半旧，只在多机内网可用 | `scripts/build.sh` | 顶部自述「跨机构建/部署编排（win54 构建 → win55 部署、Linux 转发给 Docker 入口）」。第 1 步转发已经改对了，但第 4 步仍在 win54 上找 `releases/pan4dex-<版本>.exe` —— 现行 Windows 产物是**目录 + zip，根本没有这个 exe**，那一段必然失败。这些机器（54/55/58）也早已不在当前流程里 |
| 🔴 断链，别执行 | `scripts/zip_it.py` | glob 写死 `C:\workspace\pan4dex\releases\pan4dex-v*.exe`：路径是另一台机器的、命名规则（带 `v` 前缀的 exe）也是旧的，任何情况下都找不到文件 |
| 🔴 断链，别执行 | `scripts/zip_exe.py` | 写死 `releases/pan4dex-v0.9.536.exe`（那个产物早不存在），且是相对路径，只在项目根目录执行才找得到 |
| 🔴 断链，别执行 | `scripts/extract_zip.py` | 开头 `os.chdir(r'D:\workspace\2026\pan4dex\dist')` —— 那是已退役部署机 win55 上的路径，在别的机器上直接 `FileNotFoundError` |
| 🔴 第三套入口 | `scripts/build_all.py` | 又一整套「同时构建两端」的编排，与上面两条入口并行存在、无人维护；要用就分别跑两条现行入口 |
| 🔴 版本写死 | `build_windows_quick.bat`、`build_linux_quick.sh`（根目录） | 里面钉着 v1.9.020，产物早改名了；双击它会构建出一个源码已不匹配的旧版本 |
| 🟡 一次性工具 | `scripts/build.bat`（示例还是 v0.8.7）、`scripts/deploy.bat`、`scripts/deploy.py`、`fix_*.py`×8、`repro_*.py`×4、`add_verbose_help.py`、`cleanup_blank_lines.py`、`make_icon.py` | 当年修某个具体问题留下的，都已完成使命；留着只为可追溯，**都不是构建入口**。`make_icon.py` 是唯一还有用的（生成图标） |

需要说明的取舍：这些脚本本轮**一个都没删** —— 删可执行入口的风险比删文档大（谁在别的机器上
手动跑过无从知晓），所以先把话说死在这里。真要清，建议按上表 🔴 那几行成批删，删完这条表格
同步改掉，别留下「文档说删了但还在」或反之。

---

## 🐧 Linux 版本构建

### 方式一：Docker 构建（推荐，所有环境统一使用）

#### 前置条件

1. **Docker 安装**（任意支持 Docker 的环境）:
   - Windows: Docker Desktop
   - macOS: Docker Desktop  
   - Linux: `docker.io` + `docker-compose`

2. **Kali Linux 230（linux230，主构建机）**:
   ```bash
   # 本机 ~/.ssh/config 已配好别名，直接连
   ssh linux230            # = kali@192.168.5.230，密钥 ~/.ssh/linux230_ed25519

   # 或使用 xrdp 图形界面
   xfreerdp /v:192.168.5.230 /u:kali
   ```

#### 构建步骤

##### A. 在本地 Docker 构建（任何有 Docker 的环境；正式发版仍推荐 230 路线 B）

```bash
# 1. 进入项目目录
cd pan4dex

# 2. 确保脚本可执行
chmod +x scripts/build-linux-docker.sh

# 3. 运行构建（首次会自动 docker build 镜像，约 15~20 分钟）
bash scripts/build-linux-docker.sh

# 或指定版本号
bash scripts/build-linux-docker.sh 1.9.021
```

**产物位置**: `releases/pan4dex-<版本>-linux`（在构建机本地）

##### B. 在 230 上构建（v1.9.x 标准路线，已验证）

关键事实：
- 构建目录是 **`/home/kali/workspace/pan4dex-dev`**（旧目录 `/home/kali/workspace/pan4dex` 停在 0.9.68x，不要用它）
- Docker 镜像 `pan4dex-builder-linux`（另有 `:py311`）已在机上，**不需要重建、也不需要另写构建脚本**，直接跑仓内唯一的 `scripts/build-linux-docker.sh`
- 230 的 origin 不是 GitHub，是本机打过去的 git bundle（`/home/kali/probe/pan4dex-dev.bundle`）

源码同步 + 构建完整流程（从 Windows 本机发起）：

```powershell
# 1. 本机打 bundle（在 c:\workspace\Pan4dex）
git bundle create build\pan4dex-dev.bundle dev/shell-behavior-smb-perf

# 2. 传到 230，覆盖旧 bundle
scp build\pan4dex-dev.bundle linux230:/home/kali/probe/pan4dex-dev.bundle
```

```bash
# 3. 在 230 上同步源码（脏 diff 多为 CRLF 噪音，reset --hard 安全）
ssh linux230
cd /home/kali/workspace/pan4dex-dev
git fetch origin dev/shell-behavior-smb-perf
git reset --hard FETCH_HEAD

# 4. 构建（长任务，后台跑；日志统一放 tmp，不污染 /home/kali）
mkdir -p /home/kali/workspace/pan4dex/tmp
nohup bash scripts/build-linux-docker.sh > /home/kali/workspace/pan4dex/tmp/build-<版本>.log 2>&1 &
tail -f /home/kali/workspace/pan4dex/tmp/build-<版本>.log

# 5. 验证产物（offscreen 下跑 --version）
QT_QPA_PLATFORM=offscreen ./releases/pan4dex-<版本>-linux --version
```

```powershell
# 6. 拉回本机 releases/
scp linux230:/home/kali/workspace/pan4dex-dev/releases/pan4dex-<版本>-linux releases\
```

#### 跨机传源码 / 传产物仍然成立的几条坑

（2026-09-23 从 `skills/` 下那份已废弃的 win54/win55/gti 多机构建参考里挑出来的，其余内容随那两份
文档一起删了；这几条与用哪台机器无关。）

- **大二进制不要裸 scp**：链路长了可能悄悄损坏，走 zip（有 CRC 校验）再解包。Windows 侧现行产物本就
  是 `releases/pan4dex-<版本>.zip`，直接传它。
- **运行中的 exe 删不掉**：Windows 会锁住正在执行的文件，替换前先 `taskkill /F /IM pan4dex*`。
- **`tar | ssh` 往 Windows 灌源码会按 GBK 码页落地**，带中文注释的源文件读出来就是乱码，症状是
  `UnicodeDecodeError: 'utf-8' can't decode byte 0x94`。防御写法是先 `read_bytes()` 再按 utf-8→gbk
  回退解码；`scripts/build_windows.py` 开头改 `BUILD_TIME` 的那一段（`read_bytes()` → utf-8 失败再走
  gbk）保留的就是这一手。
- **Windows 侧的两个平台差异**：PyInstaller 的 `--add-data` 分隔符是 `;` 不是 `:`；OpenSSH 里属于
  Administrators 组的账户，公钥必须放 `C:\ProgramData\ssh\administrators_authorized_keys`（用户目录下的
  `authorized_keys` 不生效），且判管理员用的 `whoami /groups` 输出是 GBK 编码。

#### Docker 镜像细节

- **镜像**: `pan4dex-builder-linux:latest`，基座 `python:3.11-bullseye`（`packaging/Dockerfile-linux:6`；
  历史上曾是 3.10，`3.3b` 那条记过 bullseye 镜像不可重建的坑），另有 `:py311` 变体用于 A/B
- **构建层**: `packaging/Dockerfile-linux`
- **关键依赖**:
  - `pillow-heif` (HEIC 解码，已实测随产物捆绑)
  - Qt6 imageformats 插件
- **注意**: `resources/tools/` 下的 exiftool / 7zz / Qt6 输入法插件不入库，镜像里没有时构建会明确提示“本包不含”并继续（目标系统自装则功能可用）

#### 构建输出

```bash
releases/
└── pan4dex-<版本>-linux    # onefile 可执行文件 (约 70MB)
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

1. **Python 3.11+**（与 `pyproject.toml` 的 `requires-python` 一致）
   ```powershell
   python --version  # 应显示 3.11.0 或更高
   ```

2. **PyInstaller 6.0+**
   ```powershell
   pip install pyinstaller        # 仓库里没有 requirements-dev.txt，别照抄那条
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

# 2. 运行 PyInstaller —— 用 packaging/ 那份
pyinstaller packaging\pan4dex.spec
#    ⚠️ 仓库根目录还有一份同名 `pan4dex.spec`，那是 PyInstaller 自动生成的残件：里面硬写着
#    `C:/workspace/Pan4dex/.venv/...` 的绝对路径，换机器直接失败。**别用它**。
#    另：降级 spec 仍是 `console=False`，与 canonical 路线（`--console` + 运行时释放控制台）
#    不一致，应急产物在 CLI 输出上与主路线有差异。

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

### 在 230 上构建的补充说明

> 完整流程见上文「方式一 · B」，不重复。这里只补监控/清理的碎片。

#### 1. 环境检查

```bash
# SSH 登录 230（本机 ~/.ssh/config 已配别名）
ssh linux230

# 检查 Docker 与镜像
docker images | grep pan4dex

# 确认构建目录（注意是 pan4dex-dev）
cd /home/kali/workspace/pan4dex-dev
git log --oneline -1
```

#### 2. 清理旧产物

```bash
# 清理旧发布包（保留最近 3 个）
ls -lt releases/pan4dex-*-linux | tail -n +4 | awk '{print $NF}' | xargs rm
```

#### 3. 执行构建（后台，日志放 tmp）

```bash
mkdir -p /home/kali/workspace/pan4dex/tmp
nohup bash scripts/build-linux-docker.sh > /home/kali/workspace/pan4dex/tmp/build-<版本>.log 2>&1 &
```

#### 4. 监控构建进度

```bash
tail -f /home/kali/workspace/pan4dex/tmp/build-<版本>.log
```

#### 5. 验证产物

```bash
# 文件类型
file releases/pan4dex-*-linux

# 启动测试（无头模式验版本号，GUI 真机验收另见 docs/linux-gap.md）
QT_QPA_PLATFORM=offscreen ./releases/pan4dex-<版本>-linux --version
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

# 传回 Windows 本机（在 Windows 上执行）
# scp linux230:/home/kali/workspace/pan4dex-dev/releases/pan4dex-<版本>-linux releases\
```

---

## 🧪 构建后验证清单

### Linux 产物验证

```bash
# 1. 基本检查（产物命名是 `-linux`，不是 `.linux`）
file releases/pan4dex-*-linux
# 应显示：ELF 64-bit LSB executable, x86-64

# 2. 依赖检查
ldd releases/pan4dex-*-linux | grep "not found"
# 应为空（除系统库外）

# 3. HEIC 支持验证 —— 注意这条只测**宿主解释器**，不能证明产物里带没带 pillow-heif
python3 -c "from PIL import Image; print('pillow-heif' in str(Image.EXTENSION))"
#   产物侧要看构建日志里是否收了 `_pillow_heif*.so`（`packaging/Dockerfile-linux:61` 的 pip
#   列表是源头），真机渲染结论见 docs/linux-gap.md §5.2 L7

# 4. 启动测试（没有 `--test-mode` 这个参数；离屏常驻才是判据）
./releases/pan4dex-*-linux --version      # 打印版本号与构建时间
QT_QPA_PLATFORM=offscreen ./releases/pan4dex-<版本>-linux &
sleep 3
pgrep -f pan4dex                          # 还在 = 没启动即死
```

### Windows 产物验证

```powershell
# 1. 文件检查
Test-Path dist\pan4dex.exe

# 2. 依赖检查（使用 Dependency Walker 或 dumpbin）
dumpbin /dependents dist\pan4dex.exe

# 3. 启动测试（没有 `--test-mode`；能打印版本、能常驻即可）
.\dist\pan4dex.exe --version
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

**A**: 确认镜像里装了 pillow-heif

```bash
# 镜像内检查（镜像名是 pan4dex-builder-linux，不是新建的）
docker run --rm pan4dex-builder-linux python -c "import pillow_heif; print(pillow_heif.__version__)"

# 确实缺了（改了 packaging/Dockerfile-linux）才重建镜像：先删旧 tag，下次构建会自动重建
# docker rmi pan4dex-builder-linux && bash scripts/build-linux-docker.sh
```

### Q4: 230 上构建速度慢

**A**: 镜像已在机上（脚本检测到已存在会直接复用，不会重新 build），慢主要在 PyInstaller 打包阶段，正常 5~10 分钟；后台跑即可：

```bash
nohup bash scripts/build-linux-docker.sh > /home/kali/workspace/pan4dex/tmp/build-<版本>.log 2>&1 &
# SSH 断开不影响，回来 tail 日志看结果
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
