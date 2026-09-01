#!/usr/bin/env python3
"""
Pan4dex 可靠部署脚本 - 简化版
"""
import subprocess, sys, os, re

WIN54 = "win54"
WIN55 = "sshuser@192.168.5.55"
WIN55_DEPLOY = "D:/workspace/2026/pan4dex/dist"  # 用正斜杠
LOCAL = "/home/kali/workspace/pan4dex"

FILES = [
    "main.py",
    "core/pane.py",
    "core/main_window.py",
    "config/theme_manager.py",
    "widgets/path_bar.py",
    "widgets/thumbnail_view.py",
    "widgets/tree_sidebar.py",
    "widgets/pane_tree_view.py",
    "widgets/settings_dialog.py",
    "scripts/build_windows.py",
    "scripts/zip_it.py",
    "scripts/extract_zip.py",
]

def sh(cmd, timeout=30):
    print(f"  $ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
    # Windows 输出用 GBK
    try:
        out = r.stdout.decode("gbk", errors="replace")
    except:
        out = r.stdout.decode("utf-8", errors="replace")
    err = r.stderr.decode("gbk", errors="replace") if r.stderr else ""
    if r.returncode != 0:
        print(f"  ERR: {err.strip()}")
        raise RuntimeError(f"失败: {cmd}")
    return out.strip()

def sh_win55(cmd, timeout=30):
    """在 55 上执行（也是 Windows GBK）"""
    return sh(f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {WIN55} '{cmd}'", timeout)

def main():
    ver = sys.argv[1].lstrip("v")
    ver_v = f"v{ver}"
    print(f"=== 部署 {ver_v} ===\n")

    # 1. 本地版本号
    print("[1] 确认版本号")
    main_py = open(f"{LOCAL}/main.py").read()
    if f'"{ver}"' not in main_py:
        raise RuntimeError(f"main.py 版本号不是 {ver}")
    print(f"  ✓ {ver_v}")

    # 2. 同步到 win54
    print("\n[2] 同步到 win54")
    for f in FILES:
        sh(f"scp {LOCAL}/{f} {WIN54}:C:/workspace/pan4dex/{f}")
        # 验证
        out = sh(f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {WIN54} 'cmd /c \"if exist C:/workspace/pan4dex/{f} (echo OK) else (echo MISSING)\"'")
        if "OK" not in out:
            raise RuntimeError(f"同步失败: {f}")
    print("  ✓ 全部同步成功")

    # 3. 构建
    print("\n[3] 构建")
    build_out = sh(f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {WIN54} 'cmd /c \"cd C:\\workspace\\pan4dex && python scripts/build_windows.py {ver_v}\"'", timeout=180)
    m = re.search(r"Size:\s*([\d,]+)", build_out)
    if m:
        size = int(m.group(1).replace(",", ""))
        print(f"  ✓ 构建成功: {size:,} bytes")
    else:
        print(f"  ✓ 构建成功")

    # 4. 打包
    print("\n[4] 打包")
    sh(f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {WIN54} 'cmd /c \"cd C:\\workspace\\pan4dex && python scripts/zip_it.py\"'")

    # 5. 部署到 55
    print("\n[5] 部署到 55")
    sh(f"scp {WIN54}:C:/workspace/pan4dex/releases/pan4dex.zip {LOCAL}/releases/pan4dex_{ver_v}.zip")
    sh(f"scp {LOCAL}/releases/pan4dex_{ver_v}.zip {WIN55}:{WIN55_DEPLOY}/pan4dex.zip")
    sh_win55(f'cmd /c "taskkill /F /IM pan4dex* /T 2>nul & timeout /t 2 & del {WIN55_DEPLOY}/pan4dex-v*.exe 2>nul & cd /d {WIN55_DEPLOY} & python extract_zip.py"')
    sh_win55(f'cmd /c "cd /d {WIN55_DEPLOY} & ren pan4dex.exe pan4dex-{ver_v}.exe"')

    # 6. 验证
    print("\n[6] 验证")
    out = sh_win55(f'cmd /c "if exist {WIN55_DEPLOY}/pan4dex-{ver_v}.exe (echo OK) else (echo MISSING)"')
    if "OK" not in out:
        raise RuntimeError("55 上找不到部署文件")
    print(f"  ✓ pan4dex-{ver_v}.exe 已部署")

    print(f"\n=== 完成 {ver_v} ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ {e}")
        sys.exit(1)
