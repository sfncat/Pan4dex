# -*- coding: utf-8 -*-
"""修复 _cli_output 中 _write_console 的句柄获取：
--windowed 进程 AttachConsole 后 GetStdHandle(-11) 仍为 NULL，
需用 CreateFileW("CONOUT$") 显式打开控制台输出句柄。
"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换整个 _write_console 函数体
old_pattern = r'def _write_console\(text\):.*?kernel32\.WriteConsoleW\(handle, buf, len\(text\), ctypes\.byref\(written\), None\)'

new_func = '''def _write_console(text):
        # --windowed 进程 AttachConsole 后 GetStdHandle(-11) 仍为 NULL，
        # 必须用 CreateFileW("CONOUT$") 显式打开控制台输出句柄
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 1
        FILE_SHARE_WRITE = 2
        OPEN_EXISTING = 3
        handle = kernel32.CreateFileW(
            "CONOUT$", GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )
        if not handle or handle == -1:
            return
        buf = ctypes.create_unicode_buffer(text)
        written = ctypes.c_ulong(0)
        kernel32.WriteConsoleW(handle, buf, len(text), ctypes.byref(written), None)
        kernel32.CloseHandle(handle)'''

new_content, count = re.subn(old_pattern, new_func, content, flags=re.DOTALL)
print(f"Replaced {count} occurrence(s)")

if count == 0:
    print("ERROR: pattern not found")
    import sys
    sys.exit(1)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Done. Verifying syntax...")
import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
