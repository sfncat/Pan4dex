# -*- coding: utf-8 -*-
"""在 --help 文本中添加 --verbose 选项"""
with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'f"  --help, -h      显示此帮助信息\\n"'
new = 'f"  --help, -h      显示此帮助信息\\n"\n            f"  --verbose, -v   保留控制台窗口显示日志（调试用）\\n"'

if old in content:
    content = content.replace(old, new, 1)
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added --verbose to help text')
else:
    print('Pattern not found')

import py_compile
py_compile.compile('main.py', doraise=True)
print('Syntax OK')
