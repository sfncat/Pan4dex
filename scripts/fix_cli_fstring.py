# -*- coding: utf-8 -*-
"""修复 _cli_output 中 f-string 的换行转义问题。
re.subn 替换字符串会被正则引擎处理 \n，改用 lambda 替换避免转义。
"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到当前（已损坏的）_cli_output 函数，替换为正确版本
# 用 lambda 替换，re 不会处理替换字符串中的转义
pattern = r'def _cli_output\(\):.*?(?=\ndef hide_console_if_standalone)'

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


'''

content, n = re.subn(pattern, lambda m: new_cli, content, count=1, flags=re.DOTALL)
print(f"_cli_output replaced: {n} occurrence(s)")

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 语法检查
import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
