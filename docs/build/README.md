# Pan4dex 构建文档（总入口）

> 最后更新：2026-10-19
> 本目录是构建文档的**唯一权威入口**。旧 `docs/BUILD-GUIDE.md` 已收敛为指向这里的重定向。

## 一句话总览

Pan4dex 有两个产物，受两条正交的约束决定“怎么编”：

| 产物 | 只能在哪编译 | 为什么 |
|---|---|---|
| **Windows**（onedir + `.zip`） | **必须在 Windows** | PyInstaller 不能跨平台，Windows 的 `.exe`/DLL 只能在 Windows 生成 |
| **Linux**（onefile ELF） | **用 Docker 在任何能跑 Docker 的宿主上** | 主用 Linux 发行版 glibc 版本偏高，直接编出的产物向后兼容差；Docker 把构建钉在 `python:3.11-bookworm`（glibc 2.36，PyQt6 6.12 wheel 的最低平台）上 |

所以“四种场景”其实是 **{Windows, Linux} × {本机, 借另一台/另一环境}**：

## 决策树：我该照哪篇文档做？

| 我要产出 | 我在哪操作 | 用哪条命令 | 详见 |
|---|---|---|---|
| Windows 版 | 直接在那台 Windows 上 | `python scripts/build.py windows` | [build-windows.md](build-windows.md) · W1 |
| Windows 版 | 人在 Linux，用 SSH 连到某台 Windows 编 | `python scripts/build.py windows --remote U@WIN --remote-path 'C:\workspace\Pan4dex'` | [build-windows.md](build-windows.md) · W2 |
| Linux 版 | 就在 Linux 机器上 | `bash scripts/build-linux-docker.sh`（或 `build.py linux`） | [build-linux.md](build-linux.md) · L1 |
| Linux 版 | 在 Windows 上，走 WSL2 + Docker | `python scripts/build.py linux`（WSL 里） | [build-linux.md](build-linux.md) · L2 |
| **两平台一起** | Windows（Linux 走 Docker，经 Git Bash 调起） | `build_all.bat` / `./build_all.sh`（薄封装 `scripts/build_all.py`） | 本页下文 |

退役的多机内网编排（win54/win55/gti/230、`build.sh`、断链脚本）见 [legacy-multimachine.md](legacy-multimachine.md)——**不要再当入口用**（`build_all.py` 已重写为双平台入口，不再是退役件）。

## 双平台入口

根目录 `build_all.bat`（Windows）与 `build_all.sh`（Linux/Git Bash）只是薄封装：
选好解释器后执行 `scripts/build_all.py`，参数原样透传（版本号、`-U`、`--replace`、
`--windows-only` / `--linux-only`）。双击 `.bat` 且不带参数时会停住窗口。

## 构建后上传更新服务器（`-U`）

`build.py`、`build_all.py`、`build_windows.py`、`build-linux-docker.sh` 都接受
`-U/--upload`（`build_windows.py`/`build-linux-docker.sh` 也认裸 `U`）：构建完成后经
`scripts/upload_release.py` 走管理页同一条 `/admin/upload` 上传，`--replace` 覆盖同版本。

- 服务器地址/超时：`scripts/update_server.json`（入库）。
- 管理口令：环境变量 `PAN4DEX_UPDATE_ADMIN_PASSWORD` > `scripts/update_server.local.json`（已 gitignore）> 交互输入。
- 上传失败不会删产物，脚本以非零退出码收尾。

## 两个“版本”别混淆

- **WSL1 / WSL2**：发行版的**运行架构**，看 `wsl -l -v` 的 `VERSION` 列（本项目是 `2`）。
- **WSL 平台版本**（如 `3.0.1`）：WSL 应用自身版本，看 `wsl --version`。升到 3.0 是升平台，**发行版仍是 WSL2 架构**。Linux 构建只需 WSL2 + Docker，平台 ≥ 3.0 只是带来更好的网络(mirrored)/WSLg/容器能力。

## Linux 构建的关键设计：Dockerfile 唯一

L1（裸 Linux）与 L2（WSL）**共用完全相同的两份东西**：
- 构建脚本 `scripts/build-linux-docker.sh`（唯一入口，对宿主是 WSL 还是裸 Linux 无感）
- 镜像定义 `packaging/Dockerfile-linux`（唯一镜像，bookworm/glibc 2.36 基座）

差异**只在“前置准备/过程”**：WSL 要多做“装 Docker Engine + 配代理/网络 + CRLF 处理”，裸 Linux 只要装好 Docker。产物字节、版本、命令完全一致。**不要因为环境不同去复制 Dockerfile**——需要区分的是过程脚本，不是镜像定义。

## 快速上手（用统一编排器 `scripts/build.py`）

`build.py` 是薄分发器，只做“选对入口 + 前置检查”，不重新实现构建逻辑；带 `--dry-run` 先看要跑什么。

```bash
# 先干跑看命令（不真构建）
python scripts/build.py linux   --env wsl  --dry-run
python scripts/build.py linux   --env bare --dry-run
python scripts/build.py windows --dry-run
python scripts/build.py windows --remote builder@10.0.0.5 --remote-path 'C:\workspace\Pan4dex' --dry-run

# 实跑（去掉 --dry-run）。版本号缺省读 config/app_config.py 的 VERSION，可用 --version 覆盖
python scripts/build.py linux
```

产物一律落在 `releases/`：Windows 是 `pan4dex-<ver>/` + `pan4dex-<ver>.zip`；Linux 是 `pan4dex-<ver>-linux`。

## 文档清单

- [README.md](README.md)：本页，决策树与总则。
- [build-windows.md](build-windows.md)：W1 本机、W2 从 Linux 经 SSH 远程到 Windows。
- [build-linux.md](build-linux.md)：L1 裸 Linux+Docker、L2 Windows+WSL+Docker，共用镜像，中文与验证。
- [legacy-multimachine.md](legacy-multimachine.md)：退役多机编排与断链脚本归档。
- [qt6-builder-base.md](qt6-builder-base.md)：通用 PyQt6 构建基座 `qt6-builder-bookworm`（可共享给其他 Qt6 项目）。

## 相关源文件

`build_all.bat` / `build_all.sh`（双平台薄封装）、`scripts/build_all.py`、`scripts/build.py`、`scripts/build_windows.py`、`scripts/build-linux-docker.sh`、`scripts/upload_release.py`（`-U` 上传）、`packaging/Dockerfile-qt6-builder`（通用基座）、`packaging/Dockerfile-linux`、`packaging/Dockerfile-runtime`、`packaging/pan4dex.spec`（Linux 降级路线）、`resources/fonts/`、`main.py`（内置字体注册 + 输入法探测）。
