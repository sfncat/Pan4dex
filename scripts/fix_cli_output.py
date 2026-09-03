# -*- coding: utf-8 -*-
"""替换 main.py 中的 _cli_output 函数为 WriteConsoleW 版本"""
import re

NEW_FUNCTION = '''def _cli_output():
    """windowed 模式下把输出挂到调用方的控制台（WriteConsoleW 方案，绕开代码页乱码）"""
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

    # 非 Windows 或非打包模式：直接 print
    if sys.platform != "win32" or not getattr(sys, 'frozen', False):
        print(output, flush=True)
        return

    import ctypes
    kernel32 = ctypes.windll.kernel32

    # 1. 释放可能存在的控制台
    kernel32.FreeConsole()

    # 2. 尝试附加到父进程控制台（PowerShell/Windows Terminal 下可能失败，属正常）
    attached = kernel32.AttachConsole(-1)

    # 3. 如果没有控制台窗口，新建一个
    allocated = False
    if not kernel32.GetConsoleWindow():
        allocated = bool(kernel32.AllocConsole())

    # 4. 设置 UTF-8 代码页（最佳努力，WriteConsoleW 不依赖代码页）
    kernel32.SetConsoleCP(65001)
    kernel32.SetConsoleOutputCP(65001)

    # 5. 用 WriteConsoleW 直接写宽字符，完全绕开代码页/字节编码问题
    def _write_console(text):
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if not handle or handle == -1:
            return
        buf = ctypes.create_unicode_buffer(text)
        written = ctypes.c_ulong(0)
        kernel32.WriteConsoleW(handle, buf, len(text), ctypes.byref(written), None)

    _write_console(output + "\\n")

    # 6. 只有在自己新建了控制台窗口时才等待按键（附加到父控制台时不等待）
    if allocated:
        try:
            _write_console("\\n按 Enter 键退出...")
            sys.stdin = open("CONIN$", "r", encoding="utf-8")
            input()
        except Exception:
            pass
'''

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 def _cli_output 和下一个顶层 def
pattern = r'(def _cli_output\(\):.*?)(?=\ndef )'
match = re.search(pattern, content, re.DOTALL)
if not match:
    print("ERROR: could not find _cli_output function")
    sys.exit(1)

old_func = match.group(1)
print(f"Found _cli_output: {len(old_func)} chars")

new_content = content[:match.start()] + NEW_FUNCTION + content[match.end():]

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Replacement done. New file size:", len(new_content), "chars")

# 验证：语法检查
import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
