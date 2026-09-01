#!/usr/bin/env python3
"""
Pan4dex 万格 — 跨平台四窗格文件管理器
"""

__version__ = "0.9.563"
__app_name__ = "Pan4dex"
__app_name_cn__ = "万格"
__build_time__ = "2026-08-30 06:01:16"  # 构建时自动注入，格式：YYYY-MM-DD HH:MM:SS

import sys
import os
import logging

# 日志配置
def setup_logging():
    """初始化日志 - 跨平台"""
    if sys.platform == "win32":
        # Windows: %APPDATA%\pan4dex\logs
        log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "pan4dex", "logs")
    else:
        # Linux/macOS: ~/.config/pan4dex/logs
        log_dir = os.path.expanduser("~/.config/pan4dex/logs")
    
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "pan4dex.log")
    
    # 日志格式
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    
    # 文件处理器（记录所有级别）
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt))
    
    # 控制台处理器（只显示 INFO 以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt))
    
    # 根日志器
    root = logging.getLogger("pan4dex")
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    
    return root

logger = setup_logging()

# 支持 PyInstaller 打包后的资源路径
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def write_crash_log(error_msg: str):
    """写入启动崩溃日志到可执行文件旁边"""
    try:
        import traceback
        import datetime
        import os
        import sys
        
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            exe_dir = os.path.dirname(os.path.abspath(__file__))
        
        crash_file = os.path.join(exe_dir, "pan4dex_crash.log")
        
        frozen_info = f"frozen=True, _MEIPASS={sys._MEIPASS}" if getattr(sys, 'frozen', False) else "frozen=False"
        
        with open(crash_file, "w", encoding="utf-8") as f:
            f.write(f"=== Pan4dex Crash Log ===\n")
            f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
            f.write(f"Version: {__version__}\n")
            f.write(f"Build: {__build_time__}\n")
            f.write(f"Platform: {sys.platform}\n")
            f.write(f"Exe dir: {exe_dir}\n")
            f.write(f"Base dir: {BASE_DIR}\n")
            f.write(f"{frozen_info}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"\n--- Error ---\n")
            f.write(error_msg)
            f.write(f"\n\n--- Traceback ---\n")
            f.write(traceback.format_exc())
        
        # Windows: 弹出错误对话框
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"启动失败，错误已写入：\n{crash_file}\n\n错误信息：\n{error_msg[:500]}",
                    "Pan4dex 启动错误",
                    0x10  # MB_ICONERROR
                )
            except:
                pass
        
        return crash_file
    except Exception as e:
        return None


def install_crash_handler():
    """安装全局异常处理器，捕获未处理异常并写入崩溃日志"""
    import sys
    import traceback
    import datetime
    import os
    
    def excepthook(exc_type, exc_value, exc_tb):
        try:
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_value))
            
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            else:
                exe_dir = os.path.dirname(os.path.abspath(__file__))
            
            crash_file = os.path.join(exe_dir, "pan4dex_crash.log")
            
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(f"=== Pan4dex Crash Log ===\n")
                f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Version: {__version__}\n")
                f.write(f"Build: {__build_time__}\n")
                f.write(f"Platform: {sys.platform}\n")
                f.write(f"Type: {exc_type.__name__}\n")
                f.write(f"\n--- Error ---\n")
                f.write(error_msg)
            
            # Windows: 弹出错误对话框
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        f"发生错误，已写入：\n{crash_file}\n\n{exc_type.__name__}: {str(exc_value)[:200]}",
                        "Pan4dex 错误",
                        0x10
                    )
                except:
                    pass
        except:
            pass
        # 调用默认处理
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    
    sys.excepthook = excepthook


def install_signal_handlers():
    """安装信号处理器，捕获段错误等"""
    import faulthandler
    import os
    import sys
    
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    
    crash_file = os.path.join(exe_dir, "pan4dex_crash.log")
    # 启用 faulthandler，将段错误写入崩溃日志
    faulthandler.enable(file=open(crash_file, 'w', encoding='utf-8'), all_threads=True)


def install_qt_plugin_path():
    """设置 Qt 插件路径，确保能找到图片格式插件"""
    import os
    import sys
    
    if getattr(sys, 'frozen', False):
        # onefile 模式：文件解压到 _MEIPASS 临时目录
        plugin_path = os.path.join(sys._MEIPASS, "imageformats")
        logger.info(f"[DEBUG] _MEIPASS: {sys._MEIPASS}")
        logger.info(f"[DEBUG] plugin_path: {plugin_path}")
        logger.info(f"[DEBUG] plugin_path exists: {os.path.exists(plugin_path)}")
        if os.path.exists(plugin_path):
            os.environ["QT_PLUGIN_PATH"] = sys._MEIPASS
            logger.info(f"[DEBUG] QT_PLUGIN_PATH set to: {sys._MEIPASS}")
        else:
            logger.info(f"[DEBUG] plugin_path does not exist, listing _MEIPASS:")
            try:
                for f in os.listdir(sys._MEIPASS):
                    logger.info(f"[DEBUG]   {f}")
            except:
                pass


def _cli_output():
    """windowed 模式下把输出挂到调用方的控制台"""
    import sys
    
    if "--version" in sys.argv or "-V" in sys.argv:
        output = f"{__app_name__} v{__version__} (build {__build_time__})"
    elif "--help" in sys.argv or "-h" in sys.argv:
        output = (
            f"{__app_name_cn__} — 跨平台四窗格文件管理器\n\n"
            f"用法: pan4dex [选项]\n\n"
            f"选项:\n"
            f"  --version, -V   显示版本信息\n"
            f"  --info          显示详细版本和构建信息\n"
            f"  --help, -h      显示此帮助信息\n"
        )
    else:
        lines = [
            f"version: {__version__}",
            f"build_time: {__build_time__}",
            f"platform: {sys.platform}",
            f"python: {sys.version}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"base_dir: {BASE_DIR}",
        ]
        output = "\n".join(lines)
    
    # sys.stdout is None 是判断 windowed 模式最可靠的信号
    if sys.stdout is None and sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # -1 即 ATTACH_PARENT_PROCESS：挂到启动它的那个控制台
        attached = kernel32.AttachConsole(-1)
        if not attached:
            # 兜底：没有父控制台就新建一个
            kernel32.AllocConsole()
        # windowed 模式下 stdout/stderr 是 None，必须先恢复
        import os
        if sys.stdout is None:
            sys.stdout = os.fdopen(os.open("CONOUT$", os.O_WRONLY), "w")
        if sys.stderr is None:
            sys.stderr = os.fdopen(os.open("CONOUT$", os.O_WRONLY), "w")
    
    print(output, flush=True)
    
    # 如果是新建的控制台（不是挂载的），等待用户按 Enter 后再关闭
    if sys.platform == "win32" and getattr(sys, 'frozen', False):
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # 检查是否是挂载到父控制台（如果是，不需要等待）
        # 通过检查标准句柄来判断
        stdin_handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        if stdin_handle == -1 or stdin_handle is None:
            # 没有标准输入，说明是新建的控制台，需要等待
            try:
                input("\n按 Enter 键退出...")
            except:
                pass


def main():
    """程序入口"""
    import sys
    import time
    _t0 = time.perf_counter()
    
    # 处理 CLI 参数（在 import GUI 库之前，秒开）
    if "--version" in sys.argv or "--info" in sys.argv or "-V" in sys.argv or "-h" in sys.argv:
        _cli_output()
        sys.exit(0)
    
    # 安装全局异常处理器
    install_crash_handler()
    install_signal_handlers()
    install_qt_plugin_path()
    
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        
        logger.info(f"Pan4dex v{__version__} starting...")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Build time: {__build_time__ or 'N/A'}")
        logger.info(f"Base dir: {BASE_DIR}")
        logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
        logger.info(f"[启动计时] Python 模块导入耗时: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        # Windows DPI 适配 - 必须在创建 QApplication 之前设置
        if sys.platform == "win32":
            import os
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PerMonitorV2
            except:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except:
                    pass
        
        # 启用高 DPI 支持
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        app = QApplication(sys.argv)
        logger.info(f"[启动计时] QApplication 创建: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        app.setApplicationName(__app_name__)
        app.setApplicationVersion(__version__)
        app.setOrganizationName("sfncat")
        
        # 设置默认样式为 Fusion（跨平台一致性最好）
        app.setStyle("Fusion")
        
        # Windows 字体修复
        if sys.platform == "win32":
            from PyQt6.QtGui import QFont
            font = QFont("Microsoft YaHei UI", 9)
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            app.setFont(font)
        
        from core.main_window import MainWindow
        logger.info(f"[启动计时] MainWindow 导入: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        window = MainWindow()
        logger.info(f"[启动计时] MainWindow 实例化: {(time.perf_counter()-_t0)*1000:.1f}ms")
        
        window.show()
        logger.info(f"[启动计时] window.show() 完成: {(time.perf_counter()-_t0)*1000:.1f}ms")
        logger.info("Main window shown, entering event loop")
        sys.exit(app.exec())
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"启动失败: {error_msg}", exc_info=True)
        
        # 写入崩溃日志到可执行文件旁边
        crash_file = write_crash_log(error_msg)
        if crash_file:
            print(f"\n启动失败！崩溃日志已写入: {crash_file}\n错误: {error_msg}", file=sys.stderr)
        else:
            print(f"\n启动失败！错误: {error_msg}", file=sys.stderr)
        
        # 确保退出
        os._exit(1)


if __name__ == "__main__":
    main()
