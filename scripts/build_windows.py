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
build_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
main_py = project_root / "main.py"
# Read as bytes, decode as utf-8 (handles gbk windows files)
raw = main_py.read_bytes()
try:
    content = raw.decode("utf-8")
except UnicodeDecodeError:
    content = raw.decode("gbk", errors="ignore")
content = content.replace('__build_time__ = ""', f'__build_time__ = "{build_time}"')
main_py.write_text(content, encoding="utf-8")
print(f"Build time: {build_time}")

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
os.replace(project_root / "dist" / "pan4dex.exe", dest)
print(f"Build successful: {dest}")
print(f"Size: {dest.stat().st_size} bytes")
