#!/usr/bin/env python3

"""
Pan4dex 万格 — 跨平台四窗格文件管理器
"""


from config.app_config import (
    APP_NAME,
    APP_NAME_CN,
    VERSION,
    BUILD_TIME,
    ORG_NAME,
    APP_STYLE,
    ICON_FILE,
)

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
            f.write(f"Version: {VERSION}\n")
            f.write(f"Build: {BUILD_TIME}\n")
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
                f.write(f"Version: {VERSION}\n")
                f.write(f"Build: {BUILD_TIME}\n")
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
    """控制台子系统下直接 print 输出（--version/--help/--info）"""
    import sys
    import os

    if "--version" in sys.argv or "-V" in sys.argv:
        # 源码运行（未打包）时 BUILD_TIME 为空，显示 dev 标记
        _build = BUILD_TIME or "dev"
        output = f"{APP_NAME} v{VERSION} (build {_build})"
    elif "--help" in sys.argv or "-h" in sys.argv:
        output = (
            f"{APP_NAME_CN} — 跨平台四窗格文件管理器\n\n"
            f"用法: pan4dex [选项]\n\n"
            f"选项:\n"
            f"  --version, -V   显示版本信息\n"
            f"  --info          显示详细版本和构建信息\n"
            f"  --install-menu  Linux: 注册应用到开始菜单/应用菜单（安装 .desktop + 图标）\n"
            f"  --help, -h      显示此帮助信息\n"
            f"  --verbose, -v   保留控制台窗口显示日志（调试用）\n"
        )
    else:
        if getattr(sys, 'frozen', False):
            exec_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            exec_dir = BASE_DIR
        lines = [
            f"version: {VERSION}",
            f"build_time: {BUILD_TIME}",
            f"platform: {sys.platform}",
            f"python: {sys.version}",
            f"frozen: {getattr(sys, 'frozen', False)}",
            f"base_dir: {exec_dir}",
        ]
        output = "\n".join(lines)
    print(output, flush=True)


def _install_menu_linux():
    """Linux：把应用注册到开始菜单/应用菜单（安装 .desktop 启动器 + 图标）。

    用法: pan4dex --install-menu
    - 把图标安装到 ~/.local/share/icons/hicolor（文件管理器/应用菜单识别）
    - 把 .desktop 启动器安装到 ~/.local/share/applications（开始菜单/应用菜单入口）
    适合打包后的 onefile / AppImage 版本；源码运行时也可用（Exec 指向 python main.py）。
    """
    if sys.platform != "linux":
        print("--install-menu 仅支持 Linux。")
        return 1
    import shutil
    import subprocess

    home = os.path.expanduser("~")
    icons_base = os.path.join(home, ".local", "share", "icons", "hicolor")
    apps_dir = os.path.join(home, ".local", "share", "applications")

    # 0) 确保 hicolor 有 index.theme——没有它 GTK 不认这是有效图标主题，
    #    gtk-update-icon-cache 会报 "No theme index file"，桌面环境找不到图标
    index_theme = os.path.join(icons_base, "index.theme")
    os.makedirs(icons_base, exist_ok=True)
    if not os.path.exists(index_theme):
        with open(index_theme, "w", encoding="utf-8") as f:
            f.write(
                "[Icon Theme]\n"
                "Name=Hicolor\n"
                "Comment=Fallback icon theme\n"
                "Hidden=true\n"
                "Directories=256x256/apps,512x512/apps\n"
                "\n"
                "[256x256/apps]\n"
                "Size=256\n"
                "Type=Directories\n"
                "Context=Apps\n"
                "\n"
                "[512x512/apps]\n"
                "Size=512\n"
                "Type=Directories\n"
                "Context=Apps\n"
            )
        os.chmod(index_theme, 0o644)

    # 图标源：Linux 用 icon.png
    if getattr(sys, "frozen", False):
        icon_src = os.path.join(sys._MEIPASS, "resources", "icons", "icon.png")
    else:
        icon_src = os.path.join(BASE_DIR, "resources", "icons", "icon.png")
    if not os.path.exists(icon_src):
        print(f"错误: 找不到图标 {icon_src}")
        return 1

    # 1) 安装图标到 hicolor 图标主题（chmod 644：源文件可能被 copy2 保留 600，桌面环境读不了）
    for size in ("256", "512"):
        dest = os.path.join(icons_base, f"{size}x{size}", "apps")
        os.makedirs(dest, exist_ok=True)
        icon_dst = os.path.join(dest, "pan4dex.png")
        shutil.copy2(icon_src, icon_dst)
        os.chmod(icon_dst, 0o644)
    print(f"[1/3] 图标已安装: ~/.local/share/icons/hicolor/{{256,512}}x{{256,512}}/apps/pan4dex.png")

    # 2) 生成 .desktop 启动器
    if getattr(sys, "frozen", False):
        exec_path = os.path.abspath(sys.executable)
    else:
        exec_path = f"{sys.executable} {os.path.join(BASE_DIR, 'main.py')}"
    desktop = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME} {APP_NAME_CN}\n"
        f"Name[en]={APP_NAME}\n"
        "GenericName=File Manager\n"
        "Comment=跨平台四窗格文件管理器\n"
        "Comment[en]=Cross-platform quad-pane file manager\n"
        f"Exec={exec_path}\n"
        "Icon=pan4dex\n"
        "Terminal=false\n"
        "Categories=Utility;FileManager;System;\n"
        "Keywords=file;manager;pane;quad;browser;\n"
        "StartupWMClass=pan4dex\n"
    )
    os.makedirs(apps_dir, exist_ok=True)
    desktop_path = os.path.join(apps_dir, "pan4dex.desktop")
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write(desktop)
    os.chmod(desktop_path, 0o644)
    print(f"[2/3] 启动器已安装: {desktop_path}")

    # 3) 刷新桌面/图标数据库（兼容 GNOME/KDE，命令缺失时忽略）
    for cmd in (
        ["update-desktop-database", apps_dir],
        ["gtk-update-icon-cache", "-f", "-q", icons_base],
        ["kbuildsycoca6", "--nosignal"],
    ):
        try:
            subprocess.run(cmd, capture_output=True, timeout=20)
        except Exception:
            pass
    print("[3/3] 注册完成。")
    print("提示: 若应用菜单/文件管理器仍未显示图标，请注销重登或重启桌面"
          "（或运行: gtk-update-icon-cache -f ~/.local/share/icons/hicolor）。")
    return 0


def free_console_in_gui_mode():
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
                f.write(f"[free_console] Error: {e}\n")
        except Exception:
            pass


def main():
    """程序入口"""
    import sys
    import time

    _t0 = time.perf_counter()
    # 处理 CLI 参数（在 import GUI 库之前，秒开）
    if "--install-menu" in sys.argv:
        sys.exit(_install_menu_linux())
    if "--version" in sys.argv or "--info" in sys.argv or "-V" in sys.argv or "-h" in sys.argv or "--help" in sys.argv:
        _cli_output()
        sys.exit(0)
    free_console_in_gui_mode()
    # 安装全局异常处理器
    install_crash_handler()
    install_signal_handlers()
    install_qt_plugin_path()
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt

        logger.info(f"Pan4dex v{VERSION} starting...")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Build time: {BUILD_TIME or 'N/A'}")
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
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(VERSION)
        # Windows 任务栏图标支持：设置 AppUserModelID + 窗口图标
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.pan4dex.app")
            except Exception:
                pass
        try:
            from PyQt6.QtGui import QIcon

            _icon_name = ICON_FILE
            if getattr(sys, 'frozen', False):
                _icon_path = os.path.join(sys._MEIPASS, "resources", "icons", _icon_name)
                # onedir 下 _MEIPASS 指向 _internal，兜底到 exe 同目录的 resources
                if not os.path.exists(_icon_path):
                    _icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "resources", "icons", _icon_name)
            else:
                _icon_path = os.path.join(BASE_DIR, "resources", "icons", _icon_name)
            if os.path.exists(_icon_path):
                app.setWindowIcon(QIcon(_icon_path))
        except Exception as e:
            logger.warning(f"Failed to set window icon: {e}")
        app.setOrganizationName(ORG_NAME)
        # 设置默认样式（跨平台一致性最好，取自全局配置）
        app.setStyle(APP_STYLE)
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
