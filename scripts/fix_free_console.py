"""Rewrite free_console_in_gui_mode to be more robust."""
import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = '''def free_console_in_gui_mode():
    """GUI 模式下释放控制台窗口。

    控制台子系统 exe 启动时会继承/创建控制台。GUI 模式下不需要控制台，
    调用 FreeConsole() 释放：
    - 从终端启动：断开与父控制台的关联，终端立即返回不阻塞
    - 双击启动：释放新建的控制台窗口，窗口自动关闭

    --verbose/-v 参数保留控制台用于调试。
    """
    import sys
    import os
    import logging

    if sys.platform != "win32":
        return

    if "--verbose" in sys.argv or "-v" in sys.argv:
        return  # 调试模式保留控制台

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        # 1. 最先释放控制台 — 这是最关键的一步
        result = kernel32.FreeConsole()
        if not result:
            # FreeConsole 失败时，尝试隐藏窗口（仅新建控制台，不隐藏父终端）
            try:
                hwnd = kernel32.GetConsoleWindow()
                if hwnd:
                    import ctypes.wintypes
                    process_list = (ctypes.wintypes.DWORD * 4)()
                    count = kernel32.GetConsoleProcessList(process_list, 4)
                    if count <= 1:
                        # 只有自己一个进程 → 是新建控制台，可以安全隐藏
                        ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
            except Exception:
                pass

        # 2. 移除控制台日志 handler（FreeConsole 后 stdout 无效）
        try:
            root = logging.getLogger("pan4dex")
            for h in list(root.handlers):
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                    root.removeHandler(h)
        except Exception:
            pass

        # 3. 重定向 stdout 到空设备
        try:
            sys.stdout = open(os.devnull, "w")
        except Exception:
            pass

        # 4. stderr 重定向到日志文件，保留崩溃诊断
        try:
            _log_dir = os.path.expanduser("~/.config/pan4dex/logs")
            os.makedirs(_log_dir, exist_ok=True)
            sys.stderr = open(os.path.join(_log_dir, "pan4dex.log"), "a", encoding="utf-8")
        except Exception:
            try:
                sys.stderr = open(os.devnull, "w")
            except Exception:
                pass

    except Exception as e:
        # 最后兜底：写日志文件
        try:
            _log_dir = os.path.expanduser("~/.config/pan4dex/logs")
            os.makedirs(_log_dir, exist_ok=True)
            with open(os.path.join(_log_dir, "pan4dex.log"), "a", encoding="utf-8") as f:
                f.write(f"[free_console] Error: {e}\\n")
        except Exception:
            pass
'''

# Replace from 'def free_console_in_gui_mode():' to the next 'def ' at same level
pattern = r'def free_console_in_gui_mode\(\):.*?(?=\ndef [a-zA-Z_])'
match = re.search(pattern, content, re.DOTALL)
if match:
    content = content[:match.start()] + new_func + content[match.end():]
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Replaced function at chars {match.start()}-{match.end()}")
else:
    print("ERROR: Could not find function pattern")
