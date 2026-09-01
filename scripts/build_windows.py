#!/usr/bin/env python3
"""Windows build script for Pan4dex - run on the Windows machine"""
import subprocess
import sys
import os
import pathlib
import datetime

# Change to project root (where this script's parent is)
script_path = pathlib.Path(__file__).resolve()
project_root = script_path.parent.parent
os.chdir(project_root)

VERSION = sys.argv[1] if len(sys.argv) > 1 else None
if not VERSION:
    with open(project_root / "main.py") as f:
        for line in f:
            if line.startswith("__version__"):
                VERSION = line.split('"')[1]
                break

print(f"Building Pan4dex {VERSION} for Windows...")
print(f"Working dir: {os.getcwd()}")
print(f"Script: {script_path}")

# Inject build time
import re
build_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
main_py = project_root / "main.py"
raw = main_py.read_bytes()
try:
    content = raw.decode("utf-8")
except UnicodeDecodeError:
    content = raw.decode("gbk", errors="ignore")
# 替换任意值的 __build_time__
content = re.sub(r'__build_time__\s*=\s*"[^"]*"', f'__build_time__ = "{build_time}"', content)
main_py.write_text(content, encoding="utf-8")
print(f"Build time: {build_time}")

# Find imageformats path dynamically
try:
    import PyQt6
    from pathlib import Path
    pyqt6_dir = Path(PyQt6.__file__).parent
    imageformats_path = pyqt6_dir / "Qt6" / "plugins" / "imageformats"
    if not imageformats_path.exists():
        # Try alternative path structure
        imageformats_path = pyqt6_dir / "plugins" / "imageformats"
    if not imageformats_path.exists():
        # Try to find it by searching
        for p in pyqt6_dir.rglob("imageformats"):
            if p.is_dir():
                imageformats_path = p
                break
    print(f"Image formats path: {imageformats_path}")
    print(f"Image format DLLs: {list(imageformats_path.glob('*.dll'))}")
except Exception as e:
    print(f"Warning: Could not find imageformats path: {e}")
    # Fallback to common locations
    imageformats_path = Path(r"C:\Python313\Lib\site-packages\PyQt6\Qt6\plugins\imageformats")
    print(f"Using fallback path: {imageformats_path}")

# Build with PyInstaller
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile", "--windowed",
    "--name=pan4dex",
    "--add-data=resources;resources",
    "--hidden-import=PyQt6.QtCore",
    "--hidden-import=PyQt6.QtGui",
    "--hidden-import=PyQt6.QtWidgets",
    "--hidden-import=qdarkstyle",
    "--hidden-import=qdarkstyle.dark",
    "--hidden-import=qdarkstyle.light",
    "--hidden-import=PyQt6.QtSvg",
    f"--add-data={imageformats_path};imageformats",
    "--icon=resources/icons/icon.ico",
    "main.py"
]

print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd)
if result.returncode != 0:
    print("Build failed!")
    sys.exit(1)

# Copy to releases
releases_dir = project_root / "releases"
releases_dir.mkdir(exist_ok=True)
dest = releases_dir / f"pan4dex-{VERSION}.exe"

# 确保 imageformats 被正确复制到 dist 目录
dist_dir = project_root / "dist"
dest_dist = dist_dir / "pan4dex.exe"
if dest_dist.exists():
    # 复制 imageformats 到 dist 目录（作为 --add-data 的备选）
    dist_imageformats = dist_dir / "imageformats"
    if imageformats_path.exists() and not dist_imageformats.exists():
        import shutil
        shutil.copytree(imageformats_path, dist_imageformats)
        print(f"Copied imageformats to {dist_imageformats}")

os.replace(dest_dist, dest)
print(f"Build successful: {dest}")
print(f"Size: {dest.stat().st_size} bytes")
