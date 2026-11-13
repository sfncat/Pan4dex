# 构建 Windows 版

> 最后更新：2026-10-30 ｜ 产物：`releases/pan4dex-<版本>/`（onedir）+ `releases/pan4dex-<版本>.zip`
> zip 包内顶层目录固定为 `pan4dex`（不带版本号），解压即得到可直接运行的 `pan4dex/`；版本号只出现在压缩包文件名上。
> 铁律：PyInstaller **不能跨平台**。`.exe` 及依赖 DLL 只能在 Windows 上生成。所谓“在 Linux 上编 Windows 版”，本质是**从 Linux 用 SSH 驱动一台 Windows 去编，再把产物拉回来**（见 W2）。

## 前置（所有 Windows 场景通用）

- Windows 10/11。
- Python 3.11+（与 `pyproject.toml` 的 `requires-python` 一致），架构 x64：
  ```powershell
  python --version
  python -c "import struct; print(struct.calcsize('P')*8)"   # 应 64
  ```
- 构建依赖：`pip install pyinstaller PyQt6 qdarkstyle pillow pillow-heif send2trash pyte`
  （或在 venv 里 `pip install -e .` / 按 `requirements.txt`）。
- 源码在 Windows 上（如 `C:\workspace\Pan4dex`），虚拟环境可选。

---

## 内置工具（构建机本地部署，**不入库**）

`resources/tools/` 整体被 `.gitignore` 排除，PyInstaller 用 `--add-data=resources;resources` 全量打入。
**缺了构建照样成功，只是产物静默少一项能力**，所以脚本打包前会逐条打印警告（`_missing_tool_warnings`）：

| 放什么 | 缺了会怎样 |
|---|---|
| `resources/tools/exiftool/exiftool.exe`（Windows 版 ExifTool，含 Perl 运行时） | 「拍摄日期」列不可用 |
| `resources/tools/7z/7z.exe` + **同目录** `7z.dll`（完整版，支持 RAR 等），或 `7z/7za.exe`（独立版兜底） | 没装系统 7-Zip 的机器上压缩/解压不可用（`core/archive_ops.py:find_7z()` 三级兜底全空） |

Windows 版 7-Zip 从本机安装目录复制即可（本机装的是 7-Zip 26.04，`License.txt` 一并带上）：

```powershell
Copy-Item 'C:\Program Files\7-Zip\7z.exe','C:\Program Files\7-Zip\7z.dll','C:\Program Files\7-Zip\License.txt' resources\tools\7z\
```

> `7z.exe` 少了同目录 `7z.dll` 会被 `find_7z()` 跳过，等于没带；脚本的警告用的是同一判据。
> Linux 专用的 `exiftool-linux/` 与 `7z/7zz` 不进 Windows 包（构建时临时移出，**失败也还原**）。
> 1.9.049 及之前的 Windows 包一直没有内置 7-Zip（构建机只部署了 Linux 的 `7zz`）；待办 T13 已修，
> **从 1.9.050 起 Windows 包内置 7-Zip**（构建机已部署 `7z.exe` + `7z.dll`，见上表）。

---

## W1：直接在那台 Windows 本机编

```powershell
cd C:\workspace\Pan4dex
.\.venv\Scripts\Activate.ps1        # 若用 venv
python scripts\build.py windows      # 或直接：python scripts\build_windows.py [版本号]
```

`build.py windows` 只是转发到 `build_windows.py`，并会自读版本号。它做四件事：
1. 打包前生成 `config/_build_info.py`（编译时间，已 gitignore，打包后删除），时间戳随产物进「关于」；
2. 检查构建机本地部署的内置工具，缺哪样打印哪条警告（**缺失不失败**，见上面「内置工具」）；
3. 临时移出 Linux 专用二进制（`resources/tools/exiftool-linux`、`7z/7zz`）后跑 PyInstaller `--onedir --windowed`；
   还原写在 `finally` 里，**构建失败也会还原** —— 否则 Linux 二进制留在 `build/`，而 Linux 构建的 rsync 排除 `build/`，
   下一个 Linux 包就静默缺 ExifTool（gotchas #66、待办 T12）；
4. 产物拷到 `releases/pan4dex-<版本>/`，并压成 `releases/pan4dex-<版本>.zip`（包内顶层目录为 `pan4dex`，不带版本号）。

**验证**：
```powershell
Test-Path releases\pan4dex-<版本>\pan4dex.exe
.\releases\pan4dex-<版本>\pan4dex.exe --version
```

> 不要用仓库**根目录**那份 `pan4dex.spec`——那是 PyInstaller 自动生成的残件，里面硬写了某台机器的 `.venv` 绝对路径，换机即废。Windows 走 `build_windows.py`（它不读 spec）。

---

## W2：人在 Linux，经 SSH 到一台 Windows 上编

适用：你日常用 Linux，但产物需要 Windows `.exe`。思路 = 让那台 Windows 装好 W1 的全部前置（Python + PyInstaller + 源码），你在 Linux 侧通过 SSH 远程触发它的构建，再把 zip 拉回来。

### W2.1 Windows 侧一次性准备
1. 装 **OpenSSH Server**（设置 → 可选功能 → OpenSSH 服务器），并确保服务在跑：
   ```powershell
   # 在 Windows 上
   Get-Service sshd | Start-Service; Set-Service -Name sshd -StartupType Automatic
   ```
2. 放置公钥：
   - **普通用户** → `%USERPROFILE%\.ssh\authorized_keys`
   - **Administrators 组成员** → 必须放 `C:\ProgramData\ssh\administrators_authorized_keys`
     （该文件权限要收紧：`icacls ...administrators_authorized_keys /remove "NT AUTHORITY\Authenticated Users"` 后仅保留 SYSTEM/Administrators），**放用户目录的 authorized_keys 对管理员账户无效**。
3. 该 Windows 上 clone/放好仓库、装好 Python + 构建依赖（同 W1）。

### W2.2 在 Linux 侧触发构建 + 回拉产物
```bash
# 用统一编排器（推荐）：远程执行 build_windows.py，再把 releases/pan4dex-<ver>.zip 拉回本地
python scripts/build.py windows \
  --remote sshuser@192.168.5.54 \
  --remote-path 'C:\workspace\Pan4dex' \
  --version 1.9.027
# 先加 --dry-run 可看到将执行的 ssh/scp 命令
```
手工等价：
```bash
ssh sshuser@192.168.5.54 'cmd /c "cd /d C:\workspace\Pan4dex && python scripts\build_windows.py 1.9.027"'
scp 'sshuser@192.168.5.54:C:\workspace\Pan4dex\releases\pan4dex-1.9.027.zip' ./releases/
```

### W2.3 跨机传源码/产物的坑（务必知道）
- **传大文件走 zip，别裸传二进制**：zip 带 CRC 校验，长链路不易悄悄损坏。Windows 产物本就是 `.zip`，直接传它。
- **不要用 `tar | ssh` 往 Windows 灌源码**：落地会按 GBK 码页，带中文注释的源文件变乱码，触发
  `UnicodeDecodeError: 'utf-8' can't decode byte 0x94`。要同步源码用 `git`(bundle/pull) 或 `rsync/scp`，
  且 `build_windows.py` 读 `config/app_config.py` 已做 utf-8→gbk 回退解码兜底。
- **运行中的 exe 删不掉**：`dist\pan4dex\` 被正在运行的产物占住时，PyInstaller 清目录会报
  `PermissionError: [WinError 5]`。**别急着 `taskkill /F /IM pan4dex*` 掉用户正在用的程序** ——
  给 PyInstaller 传 `--distpath` 指到另一个目录（如 `build/dist-<版本>`）即可绕开，产物照样拷进 `releases/`。
  只有真要替换那份正在运行的产物时，才先关掉它。（2026-11-13 出 1.9.049 时实测，gotchas #66）
- **Windows 侧 PyInstaller 的 `--add-data` 分隔符是 `;` 不是 `:`**（`build_windows.py` 内部已处理，别手改 Linux 那套）。

### W2.4 验证（拉回本机后）
```bash
unzip -l releases/pan4dex-1.9.027.zip | grep pan4dex.exe   # 结构对
# 实际运行需在 Windows 上验证
```

---

## 构建时间参考
| 场景 | 首次 | 增量 | 备注 |
|---|---|---|---|
| Windows 本机/远程 | 10–15 分钟 | 3–5 分钟 | PyInstaller 打包为主 |

相关：总则见 [README.md](README.md)，Linux 构建见 [build-linux.md](build-linux.md)。
