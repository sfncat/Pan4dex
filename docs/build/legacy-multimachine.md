# 归档：退役的多机构建/部署编排（勿作入口）

> 最后更新：2026-10-19
> 本页收纳 `BUILD-GUIDE.md` 里与**四种现行构建场景无关**的历史内容：win54/win55/gti/230 多机内网编排、并行存在的第二套脚本、以及一批断链脚本。
> 现行入口见 [README.md](README.md)。这些内容**仅留作可追溯**，不要据此操作。

## `scripts/` 与根目录脚本：谁是活的入口（2026-09-23 逐个核过）

| 状态 | 脚本 | 判定依据 |
|---|---|---|
| ✅ 现行入口 | `scripts/build.py` | 统一编排器：`linux`/`windows` 薄分发到下面两个真入口，带 `--dry-run`、CRLF 兼容、按需启动 Docker |
| ✅ 现行入口 | `scripts/build-windows` → 实为 `scripts/build_windows.py` | Windows 本机真入口，onedir→`releases/pan4dex-<版本>/`+`.zip`，打包前生成 `config/_build_info.py` 提供 `BUILD_TIME` |
| ✅ 现行入口 | `scripts/build-linux-docker.sh` | Linux 唯一真入口，镜像 `packaging/Dockerfile-linux` |
| ✅ 配套 | `packaging/Dockerfile-runtime`、`packaging/pan4dex-runtime-entry.sh`、`scripts/install-linux.sh`、`packaging/pan4dex.spec`(Linux 降级) | 运行时镜像 / 桌面集成 / 应急 spec |
| ⚠️ 半旧，只在多机内网可用 | `scripts/build.sh` | 顶部自述“win54 构建 → win55 部署、Linux 转发 Docker”。第 1 步转发已对，但第 3 步仍在 win54 找 `releases/pan4dex-<版本>.exe`——**现行 Windows 产物是目录+zip，没有这个 exe**，那段必失败；54/55/58 也早不在流程里 |
| 🔴 并行第二套，无人维护 | `scripts/build_all.py` | 又一整套“同时构建两端”，与两条真入口并行；要用就分别跑 `build.py windows` + `build.py linux` |
| 🔴 断链，别执行 | `scripts/zip_it.py` | glob 写死 `C:\workspace\pan4dex\releases\pan4dex-v*.exe`：别的机器的路径 + 旧的 `v` 前缀命名，任何情况都找不到文件 |
| 🔴 断链，别执行 | `scripts/zip_exe.py` | 写死 `releases/pan4dex-v0.9.536.exe`（早不存在），相对路径只在根目录才找得到 |
| 🔴 断链，别执行 | `scripts/extract_zip.py` | 开头 `os.chdir(r'D:\workspace\2026\pan4dex\dist')`——退役部署机 win55 的路径，别处 `FileNotFoundError` |
| 🔴 版本写死 | 根目录 `build_windows_quick.bat`、`build_linux_quick.sh` | 钉死 v1.9.020，产物早改名；双击会编出源码不匹配的旧版 |
| 🟡 一次性工具（已完成使命） | `scripts/build.bat`(示例 v0.8.7)、`deploy.bat`、`deploy.py`、`fix_*.py`×8、`repro_*.py`×4、`add_verbose_help.py`、`cleanup_blank_lines.py` | 都非构建入口。`make_icon.py` 是唯一还有用的（生成图标） |

> 这些脚本本轮**一个都没删**——删可执行入口的风险比留注释大。要清就按 🔴 那几行成批删，并同步更新本表，别出现“文档说删了但还在”或反之。

## 退役多机拓扑（背景，别再用）
- `win54`（192.168.5.54，MAC `52:54:10:73:70:cd`）：曾是 Windows 构建机，`build.sh` 里带 Wake-on-LAN 唤醒逻辑。
- `win55`（192.168.5.55，用户 `sshuser`，`D:\workspace\2026\pan4dex\dist`）：曾是 Windows 部署目标。
- `gti`/`58`：曾是 Linux 部署目标（`~/tools/pan4dex`）。
- `linux230`（kali@192.168.5.230，密钥 `~/.ssh/linux230_ed25519`）：曾经的“主构建机”。
> 现行做法：Windows 在目标机本机（或经 SSH 从 Linux 远程触发，见 build-windows.md · W2）；Linux 在你自己的 WSL/裸 Linux 用 Docker（见 build-linux.md）。不再依赖上面这批固定机器与 `build.sh`。

### 230 路线（历史留档）当年是这样
```bash
# 从 Windows 打 git bundle 传过去，在 230 上 reset --hard FETCH_HEAD
# 构建目录是 /home/kali/workspace/pan4dex-dev（不是旧的 pan4dex，那停在 0.9.68x）
# 镜像 pan4dex-builder-linux 已在机上，直接 bash scripts/build-linux-docker.sh，nohup 后台、日志放 tmp
# 产物 offscreen 验 --version，再 scp 回 Windows releases/
```
> 这套现在用 `build.py windows --remote ...`（远程 Windows）或 WSL/裸 Linux 的 `build.py linux` 替代，不必再维护那台 230。

## 与机器无关、仍然成立的传文件坑
已上移到 [build-windows.md](build-windows.md) 的 W2.3（大文件走 zip 别裸传、`tar|ssh` 灌 Windows 会 GBK 乱码、运行中 exe 删不掉、Windows `--add-data` 用 `;`）。此处不再重复。

## `docker/` 目录（已于 2026-10-19 移除）
早期 Linux 版用仓库根的 `docker/` 承载 Docker 构建。现行方案把生效定义收敛到 `packaging/Dockerfile-linux` + `scripts/build-linux-docker.sh`，`docker/` 里几件事都成了历史：
- `docker/Dockerfile`：冻结的旧镜像副本（`python:3.10` + cairosvg），与 canonical 自 v1.9.015 起故意分叉，不参与构建。
- `docker/entrypoint.sh`：其逻辑已内联进 `packaging/Dockerfile-linux`。
- `docker/build.sh`：只是 `exec scripts/build-linux-docker.sh` 的转发壳，现由 `scripts/build.py linux` 或直接跑真入口取代。
- `docker/README.md`：Docker 说明，内容已被 [build-linux.md](build-linux.md) 覆盖。
> 结论：当前场景下 `docker/` 不被任何活构建链引用，故整目录移除。需要追溯当时的 Docker 方案细节，看本文件与 `docs/changelog.md`、`docs/linux-gap.md` 里对 `docker/` 的历史引用（那些是审计留痕，保留）。

