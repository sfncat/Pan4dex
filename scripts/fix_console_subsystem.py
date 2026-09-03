# -*- coding: utf-8 -*-
"""改为控制台子系统后的配套修改：
1. 简化 _cli_output() — 直接 print()，不再需要 AttachConsole/WriteConsoleW
2. 新增 hide_console_if_standalone() — 双击启动时隐藏控制台窗口
3. 在 GUI 初始化前调用 hide_console_if_standalone()
"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# === 1. 替换 _cli_output() 为简化版 ===
old_cli = r'def _cli_output\(\):.*?(?=\ndef )'
new_cli = '''def _cli_output():
    """控制台子系统下直接 print 输出（--version/--help/--info）"""
    import sys
    import os

    if "--version" in sys.argv or "-V" in sys.argv:
        output = f"{__app_name__} v{__version__} (build {__build_time__})"
    elif "--help" in sys.argv or "-h" in sys.argv:
        output = (
            f"{__app_name_cn__} — 跨平台四窗格文件管理器\\n\\n"
            f"用法: pan4dex [选项]\\n\\n"
            f"选项:\\n"
            f"  --version, -V   显示版本信息\\n"
            f"  --info          显示详细版本和构建信息\\n"
            f"  --help, -h      显示此帮助信息\\n"
        )
    else:
        if getattr(sys, 'frozen', False):
            exec_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            exec_dir = BASE_DIR
        lines = [
            f"version: {__version__}",
            f"build_time: {__build_time__}",
            f"platform: {sys.platform}",
            f"python: {sys.version}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"base_dir: {exec_dir}",
        ]
        output = "\\n".join(lines)

    print(output, flush=True)


def hide_console_if_standalone():
    """双击启动时（控制台为本进程创建）隐藏控制台窗口；
    从 PowerShell/cmd 启动时（控制台继承自父进程）保留，用于显示日志。"""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return

        # 检查附加到该控制台的进程数：<=1 说明控制台是为本进程创建的（双击启动）
        process_list = (ctypes.c_ulong * 4)()
        count = kernel32.GetConsoleProcessList(process_list, 4)
        if count <= 1:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


'''

content, n1 = re.subn(old_cli, new_cli, content, count=1, flags=re.DOTALL)
print(f"1. _cli_output replaced: {n1} occurrence(s)")

# === 2. 在 GUI 初始化前（install_crash_handler 之前）添加 hide_console_if_standalone() 调用 ===
# 找到 "安装全局异常处理器" 注释，在它之前插入
old_marker = r'(\n\s*# 安装全局异常处理器)'
new_marker = r'\n    hide_console_if_standalone()\n\1'
content, n2 = re.subn(old_marker, new_marker, content, count=1)
print(f"2. hide_console_if_standalone() call inserted: {n2} occurrence(s)")

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nDone. New file size: {len(content)} chars")

# 语法检查
import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
