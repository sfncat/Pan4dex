#!/usr/bin/env python3
"""
Pan4dex 自动化构建脚本
同时构建 Windows 和 Linux 版本
"""
import subprocess
import sys
import os
import pathlib
import shutil
from datetime import datetime

# 切换到项目根目录
script_path = pathlib.Path(__file__).resolve()
project_root = script_path.parent
os.chdir(project_root)

print("=" * 60)
print(" Pan4dex 自动化构建脚本")
print("=" * 60)

# 获取版本号
VERSION = None
cfg_file = project_root / "config" / "app_config.py"
with open(cfg_file, encoding="utf-8") as f:
    for line in f:
        if line.startswith("VERSION"):
            VERSION = line.split('"')[1]
            break

if not VERSION:
    print("错误：无法获取版本号")
    sys.exit(1)

print(f"\n版本：{VERSION}")
print(f"工作目录：{os.getcwd()}")
print(f"构建时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 检查环境
WINDOWS_BUILD = False
LINUX_BUILD = False

# 检测操作系统
if sys.platform == "win32":
    WINDOWS_BUILD = True
    print("\n✓ 检测到 Windows 环境")
elif sys.platform.startswith("linux"):
    LINUX_BUILD = True
    print("\n✓ 检测到 Linux 环境")
else:
    print(f"\n⚠ 未知平台：{sys.platform}")
    print("  将尝试构建所有可用版本")

def build_windows():
    """构建 Windows 版本"""
    print("\n" + "=" * 60)
    print("  Windows 版本构建")
    print("=" * 60)
    
    try:
        # 运行 Windows 构建脚本
        build_script = project_root / "scripts" / "build_windows.py"
        if not build_script.exists():
            print(f"错误：构建脚本不存在 {build_script}")
            return False
        
        print(f"执行脚本：{build_script}")
        result = subprocess.run(
            [sys.executable, str(build_script)],
            cwd=str(project_root),
            capture_output=False
        )
        
        if result.returncode != 0:
            print(f"Windows 构建失败，返回码：{result.returncode}")
            return False
        
        print("✓ Windows 版本构建成功")
        return True
        
    except Exception as e:
        print(f"Windows 构建异常：{e}")
        return False

def build_linux():
    """构建 Linux 版本"""
    print("\n" + "=" * 60)
    print("  Linux 版本构建")
    print("=" * 60)
    
    try:
        # 检查 Docker
        docker_check = subprocess.run(
            ["docker", "--version"],
            capture_output=True
        )
        
        if docker_check.returncode != 0:
            print("错误：Docker 未安装或未在 PATH 中")
            print("请确保已安装 Docker 并运行")
            return False
        
        # 运行 Linux 构建脚本
        build_script = project_root / "scripts" / "build-linux-docker.sh"
        if not build_script.exists():
            print(f"错误：构建脚本不存在 {build_script}")
            return False
        
        print(f"执行脚本：{build_script}")
        
        # 设置执行权限（Linux）
        if sys.platform.startswith("linux"):
            os.chmod(build_script, 0o755)
        
        result = subprocess.run(
            [build_script],
            cwd=str(project_root),
            capture_output=False
        )
        
        if result.returncode != 0:
            print(f"Linux 构建失败，返回码：{result.returncode}")
            return False
        
        print("✓ Linux 版本构建成功")
        return True
        
    except Exception as e:
        print(f"Linux 构建异常：{e}")
        return False

def verify_builds():
    """验证构建产物"""
    print("\n" + "=" * 60)
    print("  验证构建产物")
    print("=" * 60)
    
    releases_dir = project_root / "releases"
    
    if not releases_dir.exists():
        print("错误：releases 目录不存在")
        return False
    
    builds_found = []
    
    # 查找 Windows 版本
    for item in releases_dir.iterdir():
        if item.is_dir() and item.name.startswith("pan4dex-"):
            exe_file = item / "pan4dex.exe"
            if exe_file.exists():
                builds_found.append(("Windows", item.name, exe_file))
                print(f"✓ Windows: {item.name} ({exe_file.stat().st_size / 1024 / 1024:.1f} MB)")
        
        # 查找 Linux 版本
        linux_exe = item / "pan4dex-*-linux"
        if linux_exe.exists():
            builds_found.append(("Linux", item.name, linux_exe))
            print(f"✓ Linux: {item.name} ({linux_exe.stat().st_size / 1024 / 1024:.1f} MB)")
    
    if not builds_found:
        print("⚠ 未找到构建产物")
        return False
    
    print(f"\n共找到 {len(builds_found)} 个构建产物")
    return True

# 主流程
try:
    windows_success = False
    linux_success = False
    
    # Windows 构建
    if WINDOWS_BUILD or not LINUX_BUILD:
        windows_success = build_windows()
    
    # Linux 构建
    if LINUX_BUILD or not WINDOWS_BUILD:
        linux_success = build_linux()
    
    # 验证构建
    if windows_success or linux_success:
        verify_builds()
        
        # 打印总结
        print("\n" + "=" * 60)
        print("  构建总结")
        print("=" * 60)
        
        if windows_success:
            print("✓ Windows 版本构建成功")
        else:
            print("✗ Windows 版本构建失败")
        
        if linux_success:
            print("✓ Linux 版本构建成功")
        else:
            print("✗ Linux 版本构建失败")
        
        print("\n构建产物位置:")
        print(f"  {project_root / 'releases'}")
        
    else:
        print("\n✗ 所有构建都失败了")
        sys.exit(1)
        
except KeyboardInterrupt:
    print("\n\n构建被用户中断")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ 构建过程发生异常：{e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
