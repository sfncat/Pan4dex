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

# Build with PyInstaller (onedir mode — faster startup, no extraction overhead)
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir", "--console",
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
    # 排除未使用的 PyQt6 模块，减小体积加快加载
    "--exclude-module=PyQt6.QtNetwork",
    "--exclude-module=PyQt6.QtSql",
    "--exclude-module=PyQt6.QtMultimedia",
    "--exclude-module=PyQt6.QtMultimediaWidgets",
    "--exclude-module=PyQt6.QtWebEngineCore",
    "--exclude-module=PyQt6.QtWebEngineWidgets",
    "--exclude-module=PyQt6.QtWebChannel",
    "--exclude-module=PyQt6.QtBluetooth",
    "--exclude-module=PyQt6.QtPositioning",
    "--exclude-module=PyQt6.QtSensors",
    "--exclude-module=PyQt6.QtSerialPort",
    "--exclude-module=PyQt6.QtTest",
    "--exclude-module=PyQt6.QtOpenGL",
    "--exclude-module=PyQt6.QtOpenGLWidgets",
    "--exclude-module=PyQt6.QtPrintSupport",
    "--exclude-module=PyQt6.QtHelp",
    "--exclude-module=PyQt6.QtDesigner",
    "--exclude-module=PyQt6.QtAxContainer",
    "--exclude-module=PyQt6.QtPdf",
    "--exclude-module=PyQt6.QtPdfWidgets",
    "--exclude-module=PyQt6.QtUiTools",
    # 排除未使用的 Python 标准库模块
    "--exclude-module=tkinter",
    "--exclude-module=test",
    "--exclude-module=unittest",
    "main.py"
]

print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd)
if result.returncode != 0:
    print("Build failed!")
    sys.exit(1)

# Copy to releases (onedir mode: copy entire folder + create zip)
releases_dir = project_root / "releases"
releases_dir.mkdir(exist_ok=True)

dist_dir = project_root / "dist"
src_folder = dist_dir / "pan4dex"
dest_folder = releases_dir / f"pan4dex-{VERSION}"

if not src_folder.exists():
    print(f"ERROR: Build output not found at {src_folder}")
    sys.exit(1)

# 确保 imageformats 在输出目录中
dist_imageformats = src_folder / "imageformats"
if imageformats_path.exists() and not dist_imageformats.exists():
    import shutil
    shutil.copytree(imageformats_path, dist_imageformats)
    print(f"Copied imageformats to {dist_imageformats}")

# 确保 resources 在输出根目录（PyInstaller 6+ onedir 把 data 放 _internal/ 里，
# 但代码用 sys._MEIPASS/resources/ 查找，需要复制一份到根目录）
dist_resources = src_folder / "resources"
internal_resources = src_folder / "_internal" / "resources"
if internal_resources.exists() and not dist_resources.exists():
    import shutil
    shutil.copytree(internal_resources, dist_resources)
    print(f"Copied resources to {dist_resources}")
elif (project_root / "resources").exists() and not dist_resources.exists():
    import shutil
    shutil.copytree(project_root / "resources", dist_resources)
    print(f"Copied resources (from project) to {dist_resources}")

# 复制整个文件夹到 releases
import shutil
if dest_folder.exists():
    shutil.rmtree(dest_folder)
shutil.copytree(src_folder, dest_folder)
print(f"Copied to {dest_folder}")

# 计算文件夹总大小
total_size = sum(f.stat().st_size for f in dest_folder.rglob("*") if f.is_file())
print(f"Size: {total_size} bytes ({total_size / 1024 / 1024:.1f} MB)")

# 打包 zip 方便分发
zip_path = releases_dir / f"pan4dex-{VERSION}.zip"
if zip_path.exists():
    zip_path.unlink()
shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=releases_dir, base_dir=f"pan4dex-{VERSION}")
zip_size = zip_path.stat().st_size
print(f"Zip: {zip_path} ({zip_size / 1024 / 1024:.1f} MB)")
print(f"\nBuild successful!")
print(f"  Folder: {dest_folder}")
print(f"  Zip:    {zip_path}")
print(f"  Run:    {dest_folder / 'pan4dex.exe'}")
