@echo off
REM Pan4dex 万格 — Windows 构建脚本
REM 用法: build.bat [版本号]
REM 示例: build.bat v0.8.7

setlocal enabledelayedexpansion

set VERSION=%1
if "%VERSION%"=="" (
    for /f "tokens=2 delims==" %%a in ('findstr /C:"__version__" main.py') do (
        set VERSION=%%a
        set VERSION=!VERSION:"=!
        set VERSION=!VERSION:'=!
        set VERSION=!VERSION: =!
    )
)
if "%VERSION%"=="" set VERSION=v0.0.0-dev

if not "%VERSION:~0,1%"=="v" set VERSION=v%VERSION%

echo ==========================================
echo   Pan4dex 构建
echo   版本: %VERSION%
echo ==========================================

REM 1. 检查依赖
echo [1/4] 检查依赖...
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller 未安装
    echo 运行: pip install pyinstaller
    exit /b 1
)

REM 2. 清理旧构建
echo [2/4] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 注入编译时间
for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value') do set "dt=%%a"
set "BUILD_TIME=%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%:%dt:~12,2%"
powershell -Command "(Get-Content main.py) -replace '__build_time__ = \"\"', '__build_time__ = \"%BUILD_TIME%\"' | Set-Content main.py"

REM 3. PyInstaller 打包
echo [3/4] 打包...
pyinstaller --onefile --windowed --name=pan4dex --add-data "resources;resources" --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtGui --hidden-import=PyQt6.QtWidgets --manifest packaging\pan4dex.manifest main.py
if errorlevel 1 (
    echo ERROR: 打包失败
    exit /b 1
)

REM 4. 复制到发布目录
echo [4/4] 复制到发布目录...
if not exist releases mkdir releases
copy dist\pan4dex.exe releases\pan4dex-%VERSION%.exe

echo.
echo   ✓ 构建成功
echo   ✓ 版本: %VERSION%
echo   ✓ 位置: releases\pan4dex-%VERSION%.exe
echo ==========================================
