# -*- coding: utf-8 -*-
"""修复图标代码的缩进：从 4 空格改为 8 空格（在 try 块内）"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到我之前插入的代码块，修复缩进
old_block = '''    # Windows 任务栏图标支持：设置 AppUserModelID + 窗口图标
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.pan4dex.app")
        except Exception:
            pass
    try:
        from PyQt6.QtGui import QIcon
        if getattr(sys, 'frozen', False):
            _icon_path = os.path.join(sys._MEIPASS, "resources", "icons", "icon.ico")
        else:
            _icon_path = os.path.join(BASE_DIR, "resources", "icons", "icon.ico")
        if os.path.exists(_icon_path):
            app.setWindowIcon(QIcon(_icon_path))
    except Exception as e:
        logger.warning(f"Failed to set window icon: {e}")'''

new_block = '''        # Windows 任务栏图标支持：设置 AppUserModelID + 窗口图标
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.pan4dex.app")
            except Exception:
                pass
        try:
            from PyQt6.QtGui import QIcon
            if getattr(sys, 'frozen', False):
                _icon_path = os.path.join(sys._MEIPASS, "resources", "icons", "icon.ico")
            else:
                _icon_path = os.path.join(BASE_DIR, "resources", "icons", "icon.ico")
            if os.path.exists(_icon_path):
                app.setWindowIcon(QIcon(_icon_path))
        except Exception as e:
            logger.warning(f"Failed to set window icon: {e}")'''

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Fixed indentation (exact match)")
else:
    # Try regex with flexible whitespace
    print("Exact match not found, trying regex...")
    # Just add 4 spaces to every line of the inserted block
    pattern = r'(?<=\n)(    # Windows 任务栏图标支持.*?logger\.warning\(f"Failed to set window icon: \{e\}"\))'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        old = match.group(1)
        new = '\n'.join('    ' + line if line.strip() else line for line in old.split('\n'))
        content = content.replace(old, new)
        print("Fixed indentation (regex)")
    else:
        print("ERROR: Could not find inserted block")

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
