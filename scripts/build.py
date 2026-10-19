#!/usr/bin/env python3
"""Pan4dex 构建统一编排器（thin dispatcher）

不重新实现任何构建逻辑，只按“目标平台 + 宿主环境”把请求转交给现行唯一入口：
  - Linux（wsl 或 bare，共用同一份 packaging/Dockerfile-linux） -> scripts/build-linux-docker.sh
  - Windows 本机                                                  -> scripts/build_windows.py
  - Windows 远程（在 Linux 上经 SSH 到 Windows 机器构建，再回拉 zip）-> ssh + build_windows.py + scp

用法：
  python scripts/build.py linux   [--version V] [--env auto|wsl|bare] [--dry-run]
  python scripts/build.py windows [--version V] [--dry-run]
  python scripts/build.py windows --remote user@host --remote-path "C:\\workspace\\Pan4dex" [--dry-run]

设计约束：Dockerfile 唯一（packaging/Dockerfile-linux）。--env 只影响 Linux 的“前置检查/启动”，
构建过程与产物完全一致；因此不需要、也不应该为不同 Linux 宿主复制 Dockerfile。
"""
import argparse
import pathlib
import subprocess
import sys

# Windows 控制台默认非 UTF-8（如 cp1252），本脚本有中文输出会 UnicodeEncodeError；强制 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read_version() -> str | None:
    cfg = ROOT / "config" / "app_config.py"
    try:
        for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("VERSION"):
                return line.split('"')[1]
    except FileNotFoundError:
        pass
    return None


def is_wsl() -> bool:
    try:
        v = pathlib.Path("/proc/version").read_text(errors="ignore").lower()
        return "microsoft" in v or "wsl" in v
    except OSError:
        return False


def show(cmd) -> str:
    return " ".join(map(str, cmd))


def run(cmd, dry: bool, **kw) -> int:
    print("$", show(cmd))
    if dry:
        return 0
    return subprocess.run(cmd, **kw).returncode


def _ensure_docker_running(dry: bool, env: str) -> bool:
    if dry:
        print(f"(dry-run) 会检查并在需要时启动 Docker daemon（env={env}）")
        return True
    if subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        print("Docker daemon 运行中")
        return True
    print("Docker daemon 未运行")
    hint = "（本 WSL 环境 Docker 已设为默认不自启）" if env == "wsl" else ""
    print(f"  尝试按需启动：sudo systemctl start docker {hint}")
    if run(["sudo", "systemctl", "start", "docker"], dry) != 0:
        print("  启动失败：请确认 Docker Engine 已安装（见 docs/build/build-linux.md）")
        return False
    return True


def build_linux(args) -> int:
    env = args.env if args.env != "auto" else ("wsl" if is_wsl() else "bare")
    ver = args.version or read_version()
    print(f"== Linux 构建  env={env}  version={ver} ==")
    print("   wsl / bare 共用同一入口与镜像：scripts/build-linux-docker.sh + packaging/Dockerfile-linux")
    if not _ensure_docker_running(args.dry_run, env):
        return 1

    script = ROOT / "scripts" / "build-linux-docker.sh"
    if args.dry_run:
        print("$", show(["bash", str(script)] + ([ver] if ver else [])))
        return 0
    # 兼容 Windows CRLF 工作树：必要时用去 CR 的同目录临时副本执行，执行后删除
    data = script.read_bytes()
    target = script
    tmp = None
    if b"\r\n" in data:
        tmp = script.with_name("_lf_" + script.name)
        tmp.write_bytes(data.replace(b"\r\n", b"\n"))
        target = tmp
    try:
        return subprocess.run(["bash", str(target)] + ([ver] if ver else []), cwd=str(ROOT)).returncode
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def build_windows_local(args) -> int:
    ver = args.version or read_version()
    cmd = [sys.executable, str(ROOT / "scripts" / "build_windows.py")]
    if args.version:
        cmd.append(ver)  # 仅在显式指定时传版本；否则由脚本自读 config
    print(f"== Windows 本机构建 (scripts/build_windows.py)  version={ver} ==")
    return run(cmd, args.dry_run, cwd=str(ROOT))


def build_windows_remote(args) -> int:
    if not (args.remote and args.remote_path):
        print("使用 --remote 时必须同时给 --remote-path（远端仓库绝对路径）")
        return 2
    ver = args.version or read_version() or "<version>"
    rp = args.remote_path.rstrip("\\")
    # 在远端 Windows 上执行本机构建脚本；OpenSSH 下用 cmd /c 切目录再跑 python
    build = f'cmd /c "cd /d {rp} && python scripts\\build_windows.py"'
    zip_rel = f"{rp}\\releases\\pan4dex-{ver}.zip"
    print(f"== Windows 远程构建：从本机 SSH 到 {args.remote} 执行 build_windows.py，再回拉 zip ==")
    rc = run(["ssh", args.remote, build], args.dry_run)
    if rc == 0:
        run(["scp", f"{args.remote}:{zip_rel}", str(ROOT / "releases")], args.dry_run)
    return rc


def main() -> None:
    ap = argparse.ArgumentParser(description="Pan4dex 构建编排器（复用共享入口与唯一 Dockerfile）")
    ap.add_argument("target", choices=["linux", "windows"])
    ap.add_argument("--version", help="覆盖版本号；缺省读 config/app_config.py 的 VERSION")
    ap.add_argument("--env", choices=["auto", "wsl", "bare"], default="auto",
                    help="Linux 宿主类型；仅影响前置检查，构建过程一致（默认按 /proc/version 自动判定）")
    ap.add_argument("--remote", help="windows：远端 Windows 的 user@host，经 SSH 远程构建")
    ap.add_argument("--remote-path", help="windows：远端仓库绝对路径，如 C:\\workspace\\Pan4dex")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令，不真正构建")
    args = ap.parse_args()

    (ROOT / "releases").mkdir(exist_ok=True)

    if args.target == "linux":
        rc = build_linux(args)
    else:
        rc = build_windows_remote(args) if args.remote else build_windows_local(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
