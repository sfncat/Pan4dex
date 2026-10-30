@echo off
REM Pan4dex 双平台构建（薄封装：真正的构建逻辑在 scripts\build_all.py）
REM 用法：build_all.bat [版本号] [-U] [--replace] [--windows-only^|--linux-only]
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" scripts\build_all.py %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo 构建未全部成功（退出码 %RC%）
)

REM 双击运行（无参数）时停住看结果；命令行传参时不 pause，方便脚本调用
if "%~1"=="" pause

exit /b %RC%
