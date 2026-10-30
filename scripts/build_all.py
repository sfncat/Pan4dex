#!/usr/bin/env python3
"""一次构建两个平台：Windows（本机 PyInstaller）+ Linux（Docker）。

    python scripts/build_all.py [版本号] [-U|--upload] [--replace]
                                [--windows-only | --linux-only]

- Windows 构建必须在 Windows 上跑；Linux 构建走 scripts/build-linux-docker.sh
  （Windows 上通过 Git Bash 调起，需要 Docker Desktop 在运行）。
- `-U` 会把两个平台的产物分别上传到更新服务器，地址见
  scripts/update_server.json，口令取环境变量或 server/update-server/.env。
- 任一平台构建或上传失败，脚本以非零退出码结束；已成功的产物保留。
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import time
import zipfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
CFG_FILE = PROJECT_ROOT / "config" / "app_config.py"


def read_version() -> str | None:
    for line in CFG_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split('"')[1]
    return None


def run(cmd: list[str], title: str) -> bool:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print("执行：" + " ".join(cmd))
    started = time.monotonic()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        print(f"\n✗ {title}失败，返回码 {result.returncode}（{elapsed:.0f}s）")
        return False
    print(f"\n✓ {title}完成（{elapsed:.0f}s）")
    return True


def build_windows(version: str, flags: list[str]) -> bool:
    if sys.platform != "win32":
        print("✗ Windows 构建只能在 Windows 上执行（当前平台：%s）" % sys.platform)
        return False
    cmd = [sys.executable, str(SCRIPTS_DIR / "build_windows.py"), version, *flags]
    return run(cmd, "Windows 版本构建")


def build_linux(version: str, flags: list[str]) -> bool:
    script = SCRIPTS_DIR / "build-linux-docker.sh"
    bash = shutil.which("bash")
    if not bash:
        print("✗ 找不到 bash，无法运行 Linux Docker 构建脚本（Windows 上请装 Git Bash）")
        return False
    if not shutil.which("docker"):
        print("✗ 找不到 docker 命令：Linux 版需要 Docker（Windows 上装 Docker Desktop 或 WSL2）")
        return False
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        print("✗ Docker 不可用，请先启动 Docker Desktop / docker 服务")
        return False
    if sys.platform != "win32" and not script.stat().st_mode & 0o111:
        script.chmod(0o755)
    return run([bash, str(script), version, *flags], "Linux 版本构建")


def verify(version: str) -> bool:
    print("\n" + "=" * 60)
    print("  验证构建产物")
    print("=" * 60)
    releases = PROJECT_ROOT / "releases"
    ok = True

    zip_path = releases / f"pan4dex-{version}.zip"
    if zip_path.is_file():
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        entry = "pan4dex/pan4dex.exe"
        if entry in names:
            print(f"✓ Windows: {zip_path.name} "
                  f"({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
        else:
            print(f"✗ Windows: {zip_path.name} 里没有 {entry}")
            ok = False
    else:
        print(f"✗ Windows: 缺少 {zip_path.name}")
        ok = False

    linux_path = releases / f"pan4dex-{version}-linux"
    if linux_path.is_file():
        with open(linux_path, "rb") as fh:
            header = fh.read(20)
        if header[:4] == b"\x7fELF" and header[4] == 2 and header[18] == 62:
            print(f"✓ Linux: {linux_path.name} "
                  f"({linux_path.stat().st_size / 1024 / 1024:.1f} MB)")
        else:
            print(f"✗ Linux: {linux_path.name} 不是 x86-64 ELF")
            ok = False
    else:
        print(f"✗ Linux: 缺少 {linux_path.name}")
        ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(description="Pan4dex 双平台构建")
    parser.add_argument("version", nargs="?", help="版本号；默认取 config/app_config.py")
    parser.add_argument("-U", "--upload", action="store_true",
                        help="构建后上传到更新服务器")
    parser.add_argument("--replace", action="store_true",
                        help="上传时覆盖服务器上的同平台同版本")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--windows-only", action="store_true")
    group.add_argument("--linux-only", action="store_true")
    args = parser.parse_args(argv)

    version = args.version or read_version()
    if not version:
        print("错误：无法获取版本号", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  Pan4dex 双平台构建")
    print("=" * 60)
    print(f"版本：{version}")
    print(f"目录：{PROJECT_ROOT}")
    print(f"上传：{'是' if args.upload else '否'}"
          + ("（覆盖同版本）" if args.replace else ""))

    flags: list[str] = []
    if args.upload:
        flags.append("-U")
    if args.replace:
        flags.append("--replace")

    results: dict[str, bool] = {}
    if not args.linux_only:
        results["Windows"] = build_windows(version, flags)
    if not args.windows_only:
        results["Linux"] = build_linux(version, flags)

    verified = verify(version) if len(results) == 2 else True

    print("\n" + "=" * 60)
    print("  构建总结")
    print("=" * 60)
    for platform, success in results.items():
        print(f"{'✓' if success else '✗'} {platform}")
    print(f"产物目录：{PROJECT_ROOT / 'releases'}")
    if len(results) == 2 and not verified:
        print("✗ 产物校验未通过")
    return 0 if all(results.values()) and verified else 1


if __name__ == "__main__":
    sys.exit(main())
