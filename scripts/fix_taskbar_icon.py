# -*- coding: utf-8 -*-
"""添加任务栏图标支持：AppUserModelID + setWindowIcon"""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 在 app.setApplicationVersion 之后插入图标和 AppUserModelID 设置
old_marker = r'app\.setApplicationVersion\(__version__\)'
new_code = '''app.setApplicationVersion(__version__)

    # Windows 任务栏图标支持：设置 AppUserModelID + 窗口图标
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

content, n = re.subn(old_marker, lambda m: new_code, content, count=1)
print(f"Inserted icon/AppUserModelID code: {n} occurrence(s)")

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 语法检查
import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
