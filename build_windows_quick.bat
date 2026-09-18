@echo off
REM Pan4dex v1.9.020 Windows 版本快速构建脚本
REM 双击运行或命令行执行

echo ========================================
echo   Pan4dex v1.9.020 Windows 构建
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] 检查 Python...
python --version
if errorlevel 1 (
    echo 错误：未找到 Python，请先安装 Python 3.13+
    pause
    exit /b 1
)

echo [2/3] 安装依赖...
pip install -q PyQt6 PyInstaller qdarkstyle pillow pillow-heif send2trash pyte

echo [3/3] 开始构建...
echo.
python scripts\build_windows.py

echo.
echo ========================================
echo   构建完成！
echo ========================================
echo.
echo 产物位置：releases\pan4dex-1.9.020.zip
echo.
pause
