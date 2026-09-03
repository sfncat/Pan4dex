# -*- coding: utf-8 -*-
"""清理 main.py 中过量的连续空行（3+ 连续空行压缩为 1 行）"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

original_size = len(content)
original_lines = content.count('\n') + 1

# 将 3+ 连续空行（只含空白字符的行）压缩为 1 个空行
# \n\s*\n\s*\n(?:\s*\n)* 匹配 3+ 连续空行
new_content = re.sub(r'\n[ \t]*\n[ \t]*\n(?:[ \t]*\n)*', '\n\n', content)

new_size = len(new_content)
new_lines = new_content.count('\n') + 1

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"Original: {original_size} bytes, {original_lines} lines")
print(f"After:    {new_size} bytes, {new_lines} lines")
print(f"Reduced:  {original_size - new_size} bytes ({(1 - new_size/original_size)*100:.1f}%)")

import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
