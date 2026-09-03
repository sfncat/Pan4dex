# -*- coding: utf-8 -*-
"""修复 free_console_in_gui_mode: stderr 重定向到日志文件而非 devnull"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 匹配 sys.stderr = open(os.devnull, "w") 这一行（忽略周围空行）
old = r'sys\.stderr = open\(os\.devnull, "w"\)'
new = '''# stderr 重定向到日志文件，保留未捕获异常的崩溃诊断
        _log_dir = os.path.expanduser("~/.config/pan4dex/logs")
        os.makedirs(_log_dir, exist_ok=True)
        sys.stderr = open(os.path.join(_log_dir, "pan4dex.log"), "a", encoding="utf-8")'''

content, n = re.subn(old, new, content)
print(f"Replaced stderr redirect: {n} occurrence(s)")

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
