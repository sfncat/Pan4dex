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
    """初始化日志 - 跨平台

    文件日志写不了（HOME 未设、配置目录只读、磁盘满）时只退成“没文件日志”，
    不拖垮启动：本函数在 `import main` 时就被调用，比 `main()` 还早，在这里抛
    一下就是“双击没反应”（同一个教训见 resolve_crash_log_path 的注释）。
    """
    if sys.platform == "win32":
        # Windows: %APPDATA%\pan4dex\logs
        log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "pan4dex", "logs")
    else:
        # Linux/macOS: ~/.config/pan4dex/logs
        log_dir = os.path.expanduser("~/.config/pan4dex/logs")
    log_file = os.path.join(log_dir, "pan4dex.log")
    # 日志格式
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    # 文件处理器（记录所有级别）
    file_handler = None
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
    except OSError as exc:
        print(f"[pan4dex] 文件日志不可用（{exc}），仅输出到 stderr", file=sys.stderr)
    # 控制台处理器（只显示 INFO 以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt))
    # 根日志器
    root = logging.getLogger("pan4dex")
    root.setLevel(logging.DEBUG)
    if file_handler is not None:
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(fmt, datefmt))
        root.addHandler(file_handler)
    root.addHandler(console_handler)
    return root


logger = setup_logging()
# 支持 PyInstaller 打包后的资源路径
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 持有 Windows 原生图标句柄，防止被 GC（进程退出时系统统一清理）
_WIN_HICONS: list = []

# 崩溃日志：名字固定，实际落点由 resolve_crash_log_path() 选（不一定在 exe 旁边）
CRASH_LOG_NAME = "pan4dex_crash.log"
_CRASH_LOG_PATH: str = ""
_CRASH_LOG_FH = None            # faulthandler 用的文件句柄，不持有会被 GC 关掉
_CRASH_LOG_MAX_BYTES = 256 * 1024   # 追加写的上限，超了才另起一段（不让它无限长）


def apply_windows_native_icon(hwnd: int, ico_path: str):
    """直接向窗口句柄发送 WM_SETICON（Windows 任务栏/标题栏/Alt-Tab 最底层取图通道）。

    Qt 的 windowIcon 在少数系统/桌面环境下可能不被任务栏采纳，
    WM_SETICON 是 Explorer 取任务栏按钮图标的直接来源，双保险。

    调用点已在 `sys.platform == "win32"` 里；这里再拦一道是因为函数体依赖
    `ctypes.windll` / `ctypes.wintypes`（Linux 上 `from ctypes import wintypes` 直接
    ImportError），将来新增没罩住的调用点就会在每次启动白抛一次并留 warning 日志。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        if not hwnd or not os.path.isfile(ico_path):
            return
        global _WIN_HICONS
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SendMessageW.restype = wintypes.LPARAM
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
        h_big = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        h_small = user32.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if h_big:
            user32.SendMessageW(wintypes.HWND(hwnd), WM_SETICON, ICON_BIG, h_big)
            _WIN_HICONS.append(h_big)
        if h_small:
            user32.SendMessageW(wintypes.HWND(hwnd), WM_SETICON, ICON_SMALL, h_small)
            _WIN_HICONS.append(h_small)
    except Exception as e:
        logger.warning(f"Native icon apply failed: {e}")


def _crash_log_candidates() -> list:
    """崩溃日志的落点候选（按优先级）：可执行文件同目录 → 用户缓存目录 → 临时目录。

    首选与 exe 同级是历史约定（发布流程与文档都按 `releases/pan4dex_crash.log` 找），
    但装在只读目录里时那里根本写不进去：Linux 的 `/opt/pan4dex/pan4dex`（属 root）、
    Windows 的 `Program Files`。Linux 真机上就是这个情形：`install_signal_handlers()`
    直接 `open(<exe 同级>, 'w')` 抛 PermissionError，**应用在启动第一步就死**，
    而日志目录是 docker 以 root 身份建出来的。崩溃日志这道安全网不能反过来当扳机。
    """
    import tempfile

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    cands = [os.path.join(exe_dir, CRASH_LOG_NAME)]
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        cands.append(os.path.join(base, "pan4dex", CRASH_LOG_NAME))
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
        cands.append(os.path.join(base, "pan4dex", CRASH_LOG_NAME))
    cands.append(os.path.join(tempfile.gettempdir(), CRASH_LOG_NAME))
    return cands


def resolve_crash_log_path() -> str:
    """返一个确定能写的崩溃日志路径，解析结果固定下来给三个写入点共用。

    用 `'a'` 试探而不是直接 `'w'`：`'w'` 会当场截断已有日志，试探阶段不该破坏现场。
    一个候选都写不了时回退到第一个（调用方自己包异常），不抛 —— 抛出去就是一个
    “记录崩溃的代码把程序弄崩”的故事。
    """
    global _CRASH_LOG_PATH
    if _CRASH_LOG_PATH:
        return _CRASH_LOG_PATH
    cands = _crash_log_candidates()
    for cand in cands:
        try:
            parent = os.path.dirname(cand)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(cand, 'a', encoding='utf-8'):
                pass
        except OSError:
            continue
        _CRASH_LOG_PATH = cand
        return cand
    _CRASH_LOG_PATH = cands[0]
    return _CRASH_LOG_PATH


def _crash_log_for_append() -> str:
    """返崩溃日志路径，并为「追加写」控好尺寸。

    三处写入点必须都是追加而不是 `'w'`：`'w'` 会在**每次成功启动**时把上一次的崩溃
    现场清空，而用户的动作顺序恰恰是“崩了 → 再双击一次试试”—— 等他能来看日志时，
    最该看的那一段已经没了（本仓追偶发段错误时就反复碰到：日志文件在，内容却是空的）。
    超过 `_CRASH_LOG_MAX_BYTES` 才清空一次，不让它无限增长。
    """
    path = resolve_crash_log_path()
    try:
        if os.path.getsize(path) > _CRASH_LOG_MAX_BYTES:
            with open(path, 'w', encoding='utf-8'):
                pass
    except OSError:
        pass        # 尺寸拿不到不算事：写不写得进由上一层决定，这里不抛
    return path


def _show_error_box(title: str, text: str):
    """Windows 下弹错误对话框，其他平台什么也不做。**绝不外抛** —— 它跑在崩溃路径上。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def write_crash_log(error_msg: str):
    """写入启动崩溃日志（落点见 resolve_crash_log_path）"""
    try:
        import traceback
        import datetime
        import os
        import sys

        crash_file = _crash_log_for_append()
        exe_dir = os.path.dirname(crash_file)
        frozen_info = f"frozen=True, _MEIPASS={sys._MEIPASS}" if getattr(sys, 'frozen', False) else "frozen=False"
        with open(crash_file, "a", encoding="utf-8") as f:
            f.write(f"\n=== Pan4dex Crash Log ===\n")
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
        _show_error_box("Pan4dex 启动错误",
                        f"启动失败，错误已写入：\n{crash_file}\n\n错误信息：\n{error_msg[:500]}")
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
            crash_file = _crash_log_for_append()
            exe_dir = os.path.dirname(crash_file)
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(f"\n=== Pan4dex Crash Log ===\n")
                f.write(f"Time: {datetime.datetime.now().isoformat()}\n")
                f.write(f"Version: {VERSION}\n")
                f.write(f"Build: {BUILD_TIME}\n")
                f.write(f"Platform: {sys.platform}\n")
                f.write(f"Type: {exc_type.__name__}\n")
                f.write(f"\n--- Error ---\n")
                f.write(error_msg)
            # Windows: 弹出错误对话框
            _show_error_box("Pan4dex 错误",
                            f"发生错误，已写入：\n{crash_file}\n\n{exc_type.__name__}: {str(exc_value)[:200]}")
        except:
            pass
        # 调用默认处理
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook


def install_signal_handlers():
    """安装信号处理器，捕获段错误等

    注意：这里不得让任何异常逃出去。它在 `main()` 里比窗口创建还早，以前就是它
    把“写不了崩溃日志”变成了“应用启动即死”（Linux 装在只读目录下）。

    日志以**追加**方式打开，并给每次启动写一行起始标记：没有这道标记就无法区分
    “上一次运行留下的栈”与“本次运行的”（而前者往往才是要看的那一段）。
    """
    import faulthandler
    import datetime
    import os
    import sys

    global _CRASH_LOG_FH
    try:
        crash_file = _crash_log_for_append()
        fh = open(crash_file, 'a', encoding='utf-8')
        fh.write(f"\n=== Pan4dex {VERSION} 启动于 "
                 f"{datetime.datetime.now().isoformat(timespec='seconds')} ===\n")
        fh.flush()
    except OSError as exc:
        # 一个落点都写不了：至少把段错误打到 stderr，不能拉倒启动
        logger.warning(f"崩溃日志不可写（{exc}），faulthandler 退到 stderr")
        faulthandler.enable()
        return
    _CRASH_LOG_FH = fh          # faulthandler 不接管生命周期，必须持有引用
    faulthandler.enable(file=fh, all_threads=True)


def install_qt_plugin_path():
    """清理会泄漏给子进程的 Qt 环境变量，并保证本进程能找到图片格式插件。

    PyInstaller 的 pyi_rth_pyqt6 运行时钩子在打包程序每次启动时都会设置
    QT_PLUGIN_PATH / QML2_IMPORT_PATH 指向 bundle 内的插件目录。环境变量会被
    所有子进程继承，外部 Qt 程序（如 DB Browser for SQLite）会去扫描我们的
    插件 DLL，因 Qt 版本不匹配弹 "Invalid metadata version" 错误。
    pip 安装的 PyQt6 wheel 自带嵌入式 qt.conf，插件路径由 QLibraryInfo 自动
    解析（钩子注释亦说明这些变量主要给 conda 安装兜底），因此 frozen 模式下
    直接删除即可，本进程的 Qt 仍能找到全部插件。
    """
    import os
    import sys

    if getattr(sys, 'frozen', False):
        os.environ.pop('QT_PLUGIN_PATH', None)
        os.environ.pop('QML2_IMPORT_PATH', None)
        # 兜底：构建脚本还会在 _MEIPASS 顶层复制一份 imageformats，
        # 加进本进程的库搜索路径（addLibraryPath 只影响本进程，不会泄漏）。
        plugin_path = os.path.join(sys._MEIPASS, "imageformats")
        if os.path.exists(plugin_path):
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.addLibraryPath(sys._MEIPASS)
            logger.info(f"Qt library path added: {sys._MEIPASS}")


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


def _desktop_entry_text(exec_path: str) -> str:
    """生成 `.desktop` 启动器内容（纯函数，便于用例钉住字段）

    `StartupWMClass` 必须等于 Qt 在 X11 上写进 WM_CLASS 第二项（res_class）的那个值：
    Qt 用的是 `applicationName()`，也就是 `APP_NAME`（“Pan4dex”，**区分大小写**）。
    以前写的是小写 `pan4dex`，而 res_name 是 argv[0] 的 basename（冻结产物叫
    `pan4dex-1.9.015-linux`，每个版本都变），两项都对不上 —— 桌面环境因此无法把窗口
    归到启动器（图标/分组失效）。v1.9.016 在 230 真机上用 xprop 比对才发现。
    """
    return (
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
        f"StartupWMClass={APP_NAME}\n"
    )


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
    desktop = _desktop_entry_text(exec_path)
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


def _test_open_file(path: str):
    """诊断入口：真实环境验证用默认应用打开文件（输出到日志）"""
    import shutil

    logger.info(f"TEST-OPEN path={path}")
    try:
        from config.file_associations import FileAssociations

        fa = FileAssociations()
        assoc = fa.get_association(path)
        logger.info(f"TEST-OPEN assoc={assoc}")
        logger.info(
            f"TEST-OPEN which xdg-open={shutil.which('xdg-open')} "
            f"gio={shutil.which('gio')}"
        )
        ok = fa.open_file(path)
        logger.info(f"TEST-OPEN result={ok}")
        sys.exit(0 if ok else 1)
    except Exception:
        logger.exception("TEST-OPEN exception")
        sys.exit(2)


def main():
    """程序入口"""
    import sys
    import os
    import time

    _t0 = time.perf_counter()
    # 处理 CLI 参数（在 import GUI 库之前，秒开）
    if "--install-menu" in sys.argv:
        sys.exit(_install_menu_linux())
    if "--version" in sys.argv or "--info" in sys.argv or "-V" in sys.argv or "-h" in sys.argv or "--help" in sys.argv:
        _cli_output()
        sys.exit(0)
    # 隐藏诊断入口：真实环境验证"用默认应用打开文件"（--test-open <path>）
    if "--test-open" in sys.argv:
        _test_open_file(sys.argv[sys.argv.index("--test-open") + 1])
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
        # Linux 输入法：Qt6 必须加载输入法插件（ibus/fcitx5）才能输入中文。
        # 插件由打包脚本打入 bundle（platforminputcontexts）；这里在 QApplication
        # 创建前检测系统输入法并设置 QT_IM_MODULE（用户已显式配置则尊重）。
        if sys.platform == "linux" and not os.environ.get("QT_IM_MODULE"):
            import shutil
            if shutil.which("fcitx5"):
                os.environ["QT_IM_MODULE"] = "fcitx"
            elif shutil.which("ibus-daemon"):
                os.environ["QT_IM_MODULE"] = "ibus"
            logger.info(f"Linux 输入法模块: QT_IM_MODULE={os.environ.get('QT_IM_MODULE', '(未设置)')}")
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
        _ico_for_native = ""
        try:
            from PyQt6.QtGui import QIcon
            # Windows 优先用 icon.ico（ICO 原生多尺寸，任务栏/标题栏/Alt-Tab 提取稳定）；
            # 其他平台/无 ico 时用 icon.png 生成多尺寸 QIcon
            _icon_dirs = []
            if getattr(sys, 'frozen', False):
                _icon_dirs = [
                    os.path.join(sys._MEIPASS, "resources", "icons"),
                    os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "resources", "icons"),
                ]
            else:
                _icon_dirs = [os.path.join(BASE_DIR, "resources", "icons")]
            _icon_dir = next((d for d in _icon_dirs if os.path.isdir(d)), None)
            if _icon_dir:
                _ico = os.path.join(_icon_dir, "icon.ico")
                _ico_for_native = _ico
                _app_icon = None
                if sys.platform == "win32" and os.path.exists(_ico):
                    _app_icon = QIcon(_ico)
                if _app_icon is None or _app_icon.isNull():
                    _png = os.path.join(_icon_dir, ICON_FILE)
                    if os.path.exists(_png):
                        from core.icon_utils import load_app_icon
                        _app_icon = load_app_icon(_png)
                if _app_icon is not None and not _app_icon.isNull():
                    app.setWindowIcon(_app_icon)
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
        from core.lifecycle import exec_and_drain

        logger.info(f"[启动计时] MainWindow 导入: {(time.perf_counter()-_t0)*1000:.1f}ms")
        window = MainWindow()
        logger.info(f"[启动计时] MainWindow 实例化: {(time.perf_counter()-_t0)*1000:.1f}ms")
        window.show()
        # Windows 任务栏图标加固（三重保险）：
        # 1) app/window 级 QIcon（已设置）
        # 2) show 后立即 + 延迟 200ms 再重设 Qt 窗口图标
        # 3) 直接向窗口句柄发 WM_SETICON（Explorer 取任务栏按钮图标的底层通道）
        if sys.platform == "win32":
            from core.lifecycle import call_later

            def _reapply_window_icon():
                try:
                    _icon = window.windowIcon()
                    if _icon.isNull():
                        _icon = app.windowIcon()
                    if not _icon.isNull():
                        window.setWindowIcon(_icon)
                except Exception:
                    pass
                if _ico_for_native:
                    apply_windows_native_icon(int(window.winId()), _ico_for_native)

            if _ico_for_native:
                apply_windows_native_icon(int(window.winId()), _ico_for_native)
            call_later(window, 200, _reapply_window_icon)
        logger.info(f"[启动计时] window.show() 完成: {(time.perf_counter()-_t0)*1000:.1f}ms")
        logger.info("Main window shown, entering event loop")
        # 进事件循环必须走 exec_and_drain：app.exec() 一返回就收拢后台线程，否则
        # 未派发的跨线程投递会在解释器收尾阶段被 Qt 释放，进程以 0xC0000409
        # fast-fail 退出（用户侧表现为“关掉程序时报错”），见 core/lifecycle.py
        exit_code = exec_and_drain(app)
        logger.info("后台线程已收拢，退出")
        sys.exit(exit_code)
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
