# -*- coding: utf-8 -*-
"""内嵌终端面板

架构：PTY（Windows: pywinpty / Linux: 标准库 pty）+ pyte 终端模拟器解析 +
QPlainTextEdit 渲染与键盘转发。真正的交互式终端（支持彩色转义剥离、
方向键/历史命令、vim/ssh 等全屏程序），不是简单的命令行管道。
"""
import os
import sys
import time
import platform
import threading
import logging
import shutil

from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout, QMenu, QDockWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QAction, QKeySequence

import pyte

from core.lifecycle import call_later

logger = logging.getLogger("pan4dex.terminal")

# ---------------------------------------------------------------------------
# Windows 输入法（IMM）辅助：焦点进入终端自动切英文，离开时恢复原状态
# 仅 win32 有效；Linux 输入法框架（fcitx/ibus）差异大，暂不处理
# ---------------------------------------------------------------------------
_IME_READY = False
_imm32 = None
_user32 = None
IME_CMODE_ALPHANUMERIC = 0x0000  # 英文
IME_CMODE_NATIVE = 0x0001        # 中文


def _ime_init():
    global _IME_READY, _imm32, _user32
    if _IME_READY or sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import windll, wintypes
        _imm32 = windll.imm32
        _user32 = windll.user32
        # 显式声明参数类型/返回值，避免 64 位句柄截断
        _imm32.ImmGetConversionStatus.argtypes = [
            wintypes.HKL, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ]
        _imm32.ImmGetConversionStatus.restype = wintypes.BOOL
        _imm32.ImmSetConversionStatus.argtypes = [
            wintypes.HKL, wintypes.DWORD, wintypes.DWORD,
        ]
        _imm32.ImmSetConversionStatus.restype = wintypes.BOOL
        _user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        _user32.GetKeyboardLayout.restype = wintypes.HKL
        _user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        _user32.PostMessageW.restype = wintypes.BOOL
        _IME_READY = True
    except Exception as e:
        logger.warning(f"输入法 API 初始化失败: {e}")


def _ime_get_conversion() -> int:
    """读取当前输入法转换状态（中文=1/英文=0）。

    返回 None 表示该输入法不支持 IMM 查询（TSF 输入法如 Win10/11 微软拼音），
    此时应改用键盘布局切换（_ime_activate_layout）。
    """
    _ime_init()
    if not _IME_READY:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        hkl = _user32.GetKeyboardLayout(0)
        conv = wintypes.DWORD()
        sent = wintypes.DWORD()
        if not _imm32.ImmGetConversionStatus(hkl, ctypes.byref(conv), ctypes.byref(sent)):
            return None
        return conv.value
    except Exception:
        return None


def _ime_set_conversion(conv_value: int):
    """设置输入法转换状态（IMM 输入法）"""
    _ime_init()
    if not _IME_READY:
        return
    try:
        hkl = _user32.GetKeyboardLayout(0)
        _imm32.ImmSetConversionStatus(hkl, conv_value, 0)
    except Exception:
        pass


WM_INPUTLANGCHANGEREQUEST = 0x0050


def _ime_switch_layout(hwnd: int, hkl: int):
    """通过 WM_INPUTLANGCHANGEREQUEST 切换焦点窗口的键盘布局/输入法。

    对 TSF 输入法（Win10/11 微软拼音等）有效；异步发送，由窗口消息循环处理。
    """
    _ime_init()
    if not _IME_READY or not hwnd:
        return
    try:
        _user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
    except Exception:
        pass


def _ime_current_layout() -> int:
    _ime_init()
    if not _IME_READY:
        return 0
    try:
        return _user32.GetKeyboardLayout(0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# PTY 后端：统一接口 spawn / read / write / setwinsize / isalive / terminate
# ---------------------------------------------------------------------------
class PtyBackend:
    """跨平台伪终端后端"""

    def __init__(self, program: str, cwd: str = None, cols: int = 100, rows: int = 24, env: dict = None):
        self.program = program
        self.cwd = cwd or os.path.expanduser("~")
        self.cols, self.rows = cols, rows
        self.env = env  # 额外注入的环境变量（如 zsh 禁用 autosuggestions 的 ZDOTDIR）
        self._proc = None
        self._master_fd = None  # Linux only

    # -- 生命周期 ----------------------------------------------------------
    def start(self):
        if sys.platform == "win32":
            from winpty import PtyProcess
            argv = self.program if isinstance(self.program, (list, tuple)) else [self.program]
            kwargs = dict(cwd=self.cwd, dimensions=(self.rows, self.cols))
            if self.env:
                kwargs["env"] = self.env
            self._proc = PtyProcess.spawn(argv, **kwargs)
        else:
            import pty
            import subprocess
            import fcntl
            import termios
            import struct

            self._termios = termios
            master, slave = pty.openpty()
            self._master_fd = master
            shell = self.program if isinstance(self.program, list) else [self.program]
            env = dict(os.environ)
            env.setdefault("TERM", "xterm-256color")
            if self.env:
                env.update(self.env)
            self._proc = subprocess.Popen(
                shell,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=self.cwd,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
            os.close(slave)
            # 非阻塞读
            flags = fcntl.fcntl(master, fcntl.F_GETFL)
            fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            self.setwinsize(self.rows, self.cols)

    def is_alive(self) -> bool:
        if self._proc is None:
            return False
        if sys.platform == "win32":
            try:
                return self._proc.isalive()
            except Exception:
                return False
        return self._proc.poll() is None

    def terminate(self):
        try:
            if sys.platform == "win32":
                self._proc.terminate(force=True)
            else:
                self._proc.terminate()
        except Exception:
            pass
        # 清理 zsh 禁用 autosuggestions 时创建的临时 ZDOTDIR
        zdot = (self.env or {}).get("ZDOTDIR", "")
        if zdot and os.path.basename(zdot).startswith("pan4dex-zdot-") and os.path.isdir(zdot):
            shutil.rmtree(zdot, ignore_errors=True)

    # -- IO ---------------------------------------------------------------
    def read(self, size: int = 4096) -> str:
        """读取终端输出，无数据返回空字符串（统一返回 str）"""
        if sys.platform == "win32":
            try:
                data = self._proc.read(size)
                return data if data else ""
            except EOFError:
                return ""
        else:
            try:
                data = os.read(self._master_fd, size)
                return data.decode("utf-8", errors="replace")
            except BlockingIOError:
                return ""
            except OSError:
                return ""

    def write(self, data: str):
        if sys.platform == "win32":
            self._proc.write(data)
        else:
            os.write(self._master_fd, data.encode("utf-8", errors="replace"))

    def setwinsize(self, rows: int, cols: int):
        self.rows, self.cols = rows, cols
        if rows <= 0 or cols <= 0:
            return
        try:
            if sys.platform == "win32":
                self._proc.setwinsize(rows, cols)
            else:
                import fcntl
                import termios
                import struct
                fcntl.ioctl(
                    self._master_fd,
                    termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0),
                )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# pyte 屏幕：把 pyte 认不出的转义序列「剥掉标记继续走」而不是「炸掉」
# ---------------------------------------------------------------------------
def _private_intolerant_csi_handlers():
    """筛出 pyte CSI 派发表里不接 `private` 关键字参数的处理函数名。

    pyte 的 `Stream._parser_fsm` 碰到带私有标记的序列（`CSI ? … <字母>`）时，
    会无条件给目标函数传 `private=True`；而它自己的 CSI 表里有十来个函数不收
    这个参数（实测 0.8.0 / 0.8.2 各 18 个，`select_graphic_rendition` 即 SGR
    就是其中之一）。按签名筛而不是写死名单，是为了让这份容忍在 pyte 升级、
    表项增删之后依然成立。
    """
    import inspect
    names = []
    for attr in sorted(set(pyte.Stream.csi.values())):
        fn = getattr(pyte.Screen, attr, None)
        if fn is None or not callable(fn):
            continue
        params = inspect.signature(fn).parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            continue                                   # 有 **kwargs，自己就能吞
        if "private" in params:
            continue                                   # 本来就实现了私有标记
        names.append(attr)
    return names


class TerminalScreen(pyte.HistoryScreen):
    """`pyte.HistoryScreen` + 对未实现序列的容错。

    与父类的唯一差别：带私有标记而 pyte 没实现的那些 CSI 序列，先剥掉
    `private` 标记再按普通序列执行（参数仍然生效），而不是抛
    `TypeError: ... got an unexpected keyword argument 'private'`。真机上这条
    异常正是「内嵌终端里 vim 完全不显示」的引信（htop/less 不发该序列所以
    正常），详见 docs/gotchas.md 与 docs/changelog.md v1.9.019。
    """


def _install_private_tolerance():
    """把上面筛出来的处理函数逐个包一层（模块导入时执行一次）。"""
    for attr in _private_intolerant_csi_handlers():
        base = getattr(pyte.HistoryScreen, attr)

        def tolerant(self, *args, _base=base, **kwargs):
            kwargs.pop("private", None)
            return _base(self, *args, **kwargs)

        tolerant.__name__ = attr
        setattr(TerminalScreen, attr, tolerant)


_install_private_tolerance()


# ---------------------------------------------------------------------------
# 终端视图
# ---------------------------------------------------------------------------
class TerminalView(QPlainTextEdit):
    """内嵌终端显示控件"""

    output_received = pyqtSignal(str)   # 读线程 -> 主线程：终端输出
    process_exited = pyqtSignal()       # 读线程 -> 主线程：进程结束

    def __init__(self, program: str = None, cwd: str = None, parent=None):
        super().__init__(parent)
        # 等宽字体
        font = QFont("Consolas" if sys.platform == "win32" else "Monospace", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setUndoRedoEnabled(False)
        self.setReadOnly(False)
        self.setMouseTracking(True)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

        self._program, self._program_env = self._resolve_program(program)
        self._cwd = cwd or os.path.expanduser("~")
        self._cols, self._rows = 100, 24
        self.MAX_RENDER_LINES = 2000  # 渲染文档行数上限（防止超长输出无限增长）
        self._hist_cache = []         # 历史行文本增量缓存
        self._cache_pages = []        # 缓存对应的页快照（用于检测顶部丢页）
        self._screen = TerminalScreen(self._cols, self._rows, history=2000)
        self._stream = pyte.Stream(self._screen)
        self._backend = None
        self._feed_errors = 0      # 解析失败次数（只用于日志限流）
        self._last_text = ""
        self._user_scrolled_up = False
        self._resize_pending = False
        self._reader = None          # 后台读线程
        self._closing = False        # 会话已停止：不再投递信号、不再提示退出
        self._shutdown = False       # 控件即将销毁：禁止再启动会话与任何投递
        self._ime_restore_conv = None  # 进入终端前的输入法状态（离开时恢复）
        self._ime_restore_hkl = None   # TSF 输入法：进入前的键盘布局

        # 读线程输出 -> 主线程渲染（pywinpty read 无数据时阻塞，必须放后台线程）
        self.output_received.connect(self._on_output)
        self.process_exited.connect(self._on_process_exited)
        # 渲染合并：输出洪峰时（dir/ls 大量文件）不逐条全量重建文档，
        # 30ms 窗口内只渲染一次，避免 UI 线程被渲染风暴占满导致无响应
        self._render_pending = False
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._redraw)
        # 退出检测（后端已死但线程可能尚未返回）
        self._alive_timer = QTimer(self)
        self._alive_timer.timeout.connect(self._check_alive)

        # 用户滚动时记录位置（滚到底部即恢复跟随）
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        # 兜底：控件被销毁但未走 closeEvent（如直接丢弃主窗口）时，关掉 shell 并置
        # 终态，避免残留子进程与读线程访问已删除对象。
        # 必须用 lambda 包一层：Qt 在发射 destroyed 前已断开“接收者是本对象”的
        # 连接，绑定方法槽（self._on_destroyed）永远不会被调用；而槽内只做
        # Python 级操作（不碰已消失的 C++ 对象），因此安全。
        self.destroyed.connect(lambda *_: self._on_destroyed())

        self._start_shell()

    def _on_destroyed(self, *args):
        """控件已销毁：不能再启动会话、不能再向主线程投递，并回收 shell 子进程。

        只能碰 Python 属性与 `PtyBackend`（纯 Python）；任何 Qt 调用都会抛
        `RuntimeError: wrapped C/C++ object ... has been deleted`。
        """
        self._shutdown = True
        self._closing = True
        backend, self._backend = self._backend, None
        if backend is not None:
            try:
                backend.terminate()
            except Exception:
                pass

    # -- 默认终端程序 ------------------------------------------------------
    @staticmethod
    def _resolve_program(program):
        """解析终端程序与需要注入的环境变量，返回 (program, env)。

        program 为空时使用系统默认 shell，并统一关闭 shell 的「预测/补齐
        建议」（灰色半透明文本）：
        - Windows PowerShell：PSReadLine -PredictionSource None
        - Linux zsh：临时 ZDOTDIR 包装——source 用户 zshrc 后调用
          zsh-autosuggestions 的内部禁用函数（配置存在才调用，不报错），
          不改动用户配置文件；bash 无预测建议无需处理。
        """
        if program:
            return (program, None)
        if sys.platform == "win32":
            # 关闭 PSReadLine 内联预测：预测文本以半透明样式输出，终端模拟器
            # 无法渲染其灰色样式，会显示成"真实输入"的干扰内容（Tab 补全不受影响）。
            import shutil
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
            return ([shell, "-NoLogo", "-NoExit", "-Command",
                     "Set-PSReadLineOption -PredictionSource None"], None)
        shell = os.environ.get("SHELL", "/bin/bash")
        if os.path.basename(shell).startswith("zsh"):
            import tempfile
            import shlex
            zdotdir = tempfile.mkdtemp(prefix="pan4dex-zdot-")
            lines = []
            # 先还原 ZDOTDIR 语义再加载用户配置（避免用户 zshrc 依赖临时目录）
            lines.append("unset ZDOTDIR")
            user_rc = os.path.expanduser("~/.zshrc")
            if os.path.exists(user_rc):
                lines.append(f"source {shlex.quote(user_rc)}")
            # 禁用 zsh-autosuggestions 灰色补齐（函数存在才调用）
            lines.append("(( $+functions[_zsh_autosuggest_disable] )) && _zsh_autosuggest_disable")
            with open(os.path.join(zdotdir, ".zshrc"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return ([shell], {"ZDOTDIR": zdotdir})
        return ([shell], None)

    def _start_shell(self):
        if self._shutdown:
            return
        try:
            self._backend = PtyBackend(self._program, self._cwd, self._cols, self._rows,
                                       env=getattr(self, '_program_env', None))
            self._backend.start()
            self._closing = False
            self._alive_timer.start(500)
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            logger.info(f"终端已启动: program={self._program} cwd={self._cwd}")
        except Exception as e:
            logger.error(f"终端启动失败: {e}", exc_info=True)
            self.setPlainText(f"终端启动失败: {e}\n程序: {self._program}")

    def set_program(self, program: str):
        """更换终端程序并重启会话（None/空 = 系统默认 shell）"""
        self._program, self._program_env = self._resolve_program(program)
        self.restart()

    def restart(self, cwd: str = None):
        """重启终端会话（cwd 指定后以该目录启动 shell）"""
        if self._shutdown:
            return
        if cwd is not None:
            self._cwd = cwd
        if self._backend is not None:
            self._backend.terminate()
            self._backend = None
        self._reader = None
        self._screen = TerminalScreen(self._cols, self._rows, history=2000)
        self._stream = pyte.Stream(self._screen)
        self._hist_cache = []
        self._feed_errors = 0
        self._cache_pages = []
        self._last_text = ""
        self._exited_shown = False
        self.clear()
        self._start_shell()

    # -- 读线程 ------------------------------------------------------------
    def _emit_ui(self, signal_name: str, *args):
        """从读线程向主线程投递信号（对控件销毁做防御）。

        后台线程无法与控件销毁同步：Windows 上 `pty.read` 无数据时一直阻塞，
        `terminate()` 后线程仍可能卡在 read 里，join 不回来。若此时控件的 C++
        对象已被删除，emit 会抛 `RuntimeError: wrapped C/C++ object of type
        TerminalView has been deleted`，甚至触发 Qt 内部崩溃。故：会话已停则丢弃，
        否则吞掉 RuntimeError——丢一帧终端输出远好过让应用崩掉。

        参数是信号**名字**而不是信号对象：在已销毁的 QObject 上取
        `self.output_received` 就会抛 RuntimeError，写成 `getattr` 放进 try 里
        才能真正兜住（调用点必须写 `self._emit_ui("output_received", data)`）。
        """
        if self._closing or self._shutdown:
            return
        try:
            getattr(self, signal_name).emit(*args)
        except RuntimeError:
            pass

    def _read_loop(self):
        """后台线程：阻塞读 PTY 输出并转发到主线程。

        Windows（pywinpty read 无数据即阻塞）返回数据或 EOF；
        Linux（os.read 非阻塞）无数据返回空串，需短暂等待再读，
        否则循环会立即退出并误报"进程已退出"。
        """
        backend = self._backend
        while backend is not None and backend is self._backend and not self._closing:
            try:
                data = backend.read(65536)
                if data:
                    self._emit_ui("output_received", data)
                    continue
                # 无数据：Linux 非阻塞读返回空，稍候再读（Windows 阻塞读不至此）
                time.sleep(0.03)
            except EOFError:
                break
            except Exception:
                break
        self._emit_ui("process_exited")

    # -- 输出渲染 ----------------------------------------------------------
    def _on_output(self, data: str):
        # 解析失败不许带走这一帧，也不许把异常抛回 Qt 事件循环。pyte 一旦在
        # `feed` 里抛，它会重置状态机并丢掉当前这段 PTY 输出的剩余部分；对 vim
        # 这种「首屏整屏绘制 + 之后只发增量」的程序，丢一段就等于画面永久错位，
        # 而调用方（读线程投递的 Qt 槽）根本无从知晓。屏幕能画多少画多少。
        try:
            self._stream.feed(data)
        except Exception as e:
            self._feed_errors += 1
            if self._feed_errors <= 3 or self._feed_errors % 200 == 0:
                logger.warning(
                    f"终端输出解析失败，已跳过这一段（累计 {self._feed_errors} 次）: "
                    f"{e!r} 片段起 {data[:40]!r}", exc_info=True)
        # 合并渲染：仅在空闲时调度一次，30ms 内的连续输出合并为一次重绘
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start(30)

    def _force_render(self):
        """立即渲染（取消合并窗口），用于需要即时反馈的场景"""
        self._render_timer.stop()
        self._render_pending = False
        self._redraw()

    def _check_alive(self):
        if self._backend is None:
            self._alive_timer.stop()
            return
        # pywinpty 的 read 在进程退出后可能不返回也不抛 EOF（线程卡死），
        # 因此以"后端进程已死"为准直接提示，不等待读线程退出
        if not self._backend.is_alive():
            self._alive_timer.stop()
            logger.info("终端进程已退出")
            self._on_process_exited()

    def _on_process_exited(self):
        """进程退出：提示重启"""
        if self._closing or getattr(self, '_exited_shown', False):
            return
        self._exited_shown = True
        try:
            self.appendPlainText("\r\n[进程已退出，按 Ctrl+Shift+R 或右键重启]")
        except Exception:
            pass

    def _render_text(self) -> str:
        """屏幕 + 历史行拼接为纯文本。

        pyte 0.8 的 history.top 是 deque[页]（maxlen=history，**一页=一行**），
        页是 {列号: Char}，Char.data 为单字符，需按列拼接成行文本。
        历史行按页增量缓存（只拼接新增行），渲染文本有界（MAX_RENDER_LINES），
        超长输出（dir/ls 大量文件）时重绘成本固定，避免 UI 线程被渲染风暴占满。
        """
        self._sync_hist_cache()
        lines = self._hist_cache[-self.MAX_RENDER_LINES:] + [
            ln.rstrip() for ln in self._screen.display
        ]
        # 去掉顶部连续空行
        while lines and not lines[0]:
            lines.pop(0)
        return "\n".join(lines)

    @staticmethod
    def _page_text(page, cols) -> str:
        """把历史页（一行，{列号: Char}）拼成行文本"""
        return "".join(page[x].data for x in range(cols)).rstrip()

    def _sync_hist_cache(self):
        """增量维护历史行文本缓存：新行总在最后一页，只拼接新增部分。

        稳态（输出洪峰）时新增行数≈丢弃行数，总行数不变，仅凭行数无法察觉
        顶部丢页；因此用页对象身份检测 deque 左侧被淘汰的页，同步删除缓存
        中对应的旧行，避免滚动查看历史时出现过期/重复行。
        注意：pyte 0.8 每页=一行，页数是行数（页键数只是列数，不能当行数）。
        """
        pages = self._screen.history.top
        cache = self._hist_cache
        cur_pages = list(pages)
        prev_pages = self._cache_pages
        if prev_pages and cur_pages and prev_pages[0] is not cur_pages[0]:
            # 顶部被淘汰：找到当前首页在旧快照中的位置，删除其前的行
            cut = len(prev_pages)
            for i, p in enumerate(prev_pages):
                if p is cur_pages[0]:
                    cut = i
                    break
            removed = cut  # 一页=一行
            if removed:
                del cache[:removed]
        self._cache_pages = cur_pages
        total = len(cur_pages)  # 页数 = 历史行数
        # 兜底（如 reset 清空 history）
        if len(cache) > total:
            del cache[: len(cache) - total]
        # 追加新增行：从右往左收集缺失页，再反转回正序
        missing = total - len(cache)
        if missing > 0:
            collected = []
            for page in reversed(cur_pages):
                collected.append(self._page_text(page, self._cols))
                missing -= 1
                if missing == 0:
                    break
            cache.extend(reversed(collected))

    def _redraw(self):
        self._render_pending = False
        text = self._render_text()
        if text == self._last_text:
            return
        self._last_text = text
        # 跟随逻辑：只要用户没有主动滚离底部，新输出就自动滚到底
        follow = not self._user_scrolled_up
        self.setPlainText(text)
        if follow:
            # 定位光标并滚到底（用户滚离底部时不动光标，避免把视图拽回）
            cur = self._screen.cursor
            hist_top = len(self._screen.history.top)
            line_no = hist_top + cur.y
            doc = self.document()
            block = doc.findBlockByLineNumber(min(max(line_no, 0), doc.blockCount() - 1))
            c = self.textCursor()
            pos = block.position() + min(cur.x, block.length() - 1)
            c.setPosition(pos)
            self.setTextCursor(c)
            sb = self.verticalScrollBar()
            sb.setValue(sb.maximum())

    # -- 键盘输入 ----------------------------------------------------------
    def keyPressEvent(self, e):
        if self._backend is None:
            return
        # Ctrl+Shift+R 重启终端（Ctrl+Shift+T 已用于目录树）
        if e.matches(QKeySequence.StandardKey.Refresh) or (
            e.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and e.key() == Qt.Key.Key_R
        ):
            self.restart()
            return

        key = e.key()
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        keymap = {
            Qt.Key.Key_Return: "\r",
            Qt.Key.Key_Enter: "\r",
            Qt.Key.Key_Backspace: "\x7f",
            Qt.Key.Key_Tab: "\t",
            Qt.Key.Key_Escape: "\x1b",
            Qt.Key.Key_Up: "\x1b[A",
            Qt.Key.Key_Down: "\x1b[B",
            Qt.Key.Key_Right: "\x1b[C",
            Qt.Key.Key_Left: "\x1b[D",
            Qt.Key.Key_Home: "\x1b[H",
            Qt.Key.Key_End: "\x1b[F",
            Qt.Key.Key_Insert: "\x1b[2~",
            Qt.Key.Key_Delete: "\x1b[3~",
            Qt.Key.Key_PageUp: "\x1b[5~",
            Qt.Key.Key_PageDown: "\x1b[6~",
        }
        # Ctrl+Shift+C/V 走复制粘贴（不发给终端）
        if ctrl and shift and key == Qt.Key.Key_C:
            self.copy(); return
        if ctrl and shift and key == Qt.Key.Key_V:
            self.paste_into_terminal(); return

        if key in keymap and not (ctrl and key in (Qt.Key.Key_C, Qt.Key.Key_D)):
            self._backend.write(keymap[key])
            return

        # Ctrl+字母控制字符（Ctrl+A=\x01 ...）
        if ctrl and not alt and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            self._backend.write(chr(key - Qt.Key.Key_A.value + 1))
            return

        text = e.text()
        if text:
            if alt:
                text = "\x1b" + text
            self._backend.write(text)

    def paste_into_terminal(self):
        from PyQt6.QtWidgets import QApplication
        clip = QApplication.clipboard().text()
        if clip and self._backend is not None:
            # 终端粘贴：换行统一为 \r
            self._backend.write(clip.replace("\r\n", "\n").replace("\n", "\r"))

    # -- 右键菜单：复制/粘贴/重启 -------------------------------------------
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        act_copy = QAction("复制 (Ctrl+Shift+C)", self)
        act_paste = QAction("粘贴 (Ctrl+Shift+V)", self)
        act_restart = QAction("重启终端 (Ctrl+Shift+R)", self)
        act_copy.triggered.connect(self.copy)
        act_paste.triggered.connect(self.paste_into_terminal)
        act_restart.triggered.connect(self.restart)
        menu.addAction(act_copy)
        menu.addAction(act_paste)
        menu.addSeparator()
        menu.addAction(act_restart)
        menu.exec(e.globalPos())

    # -- 尺寸同步 PTY ------------------------------------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._resize_pending:
            self._resize_pending = True
            call_later(self, 80, self._sync_pty_size)

    def _sync_pty_size(self):
        self._resize_pending = False
        fm = self.fontMetrics()
        viewport_h = self.viewport().height()
        viewport_w = self.viewport().width()
        char_w = max(fm.horizontalAdvance("M"), 1)
        char_h = max(fm.height(), 1)
        cols = max(20, viewport_w // char_w - 1)
        rows = max(5, viewport_h // char_h - 1)
        if cols != self._cols or rows != self._rows:
            self._cols, self._rows = cols, rows
            if self._backend is not None:
                self._backend.setwinsize(rows, cols)
            # pyte 屏幕尺寸跟随
            try:
                self._screen.resize(rows, cols)
            except Exception:
                pass

    # -- 滚动跟随 ----------------------------------------------------------
    def _on_scroll(self, value):
        sb = self.verticalScrollBar()
        self._user_scrolled_up = value < sb.maximum() - 2

    def wheelEvent(self, e):
        super().wheelEvent(e)
        # 滚回底部时恢复自动跟随
        sb = self.verticalScrollBar()
        if sb.value() >= sb.maximum() - 2:
            self._user_scrolled_up = False

    # -- 输入法（Windows）：进入终端自动切英文，离开恢复原状态 -------------
    def focusInEvent(self, e):
        super().focusInEvent(e)
        if sys.platform != "win32":
            return
        # 记录进入前状态：IMM 输入法记中英状态，TSF 输入法记键盘布局
        self._ime_restore_conv = _ime_get_conversion()
        self._ime_restore_hkl = _ime_current_layout()
        hwnd = int(self.winId())
        if self._ime_restore_conv is not None:
            _ime_set_conversion(IME_CMODE_ALPHANUMERIC)  # IMM：切英文
        else:
            _ime_switch_layout(hwnd, 0x04090409)         # TSF：切英语(美国)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if sys.platform != "win32":
            return
        hwnd = int(self.winId())
        if self._ime_restore_conv is not None:
            _ime_set_conversion(self._ime_restore_conv)
        elif self._ime_restore_hkl:
            _ime_switch_layout(hwnd, self._ime_restore_hkl)
        self._ime_restore_conv = None
        self._ime_restore_hkl = None

    def close_shell(self, shutdown: bool = False):
        """停止 shell 会话（杀子进程 + 停定时器 + 让读线程自然退出）。

        `shutdown=True` 用于控件/主窗口销毁：置终态标志，之后 `_start_shell`
        直接返回、跨线程投递全部丢弃，因此不会残留 shell 进程，也不会在
        控件被删除后再 emit。
        """
        if shutdown:
            self._shutdown = True
        self._closing = True
        for timer in (self._alive_timer, self._render_timer):
            try:
                timer.stop()
            except RuntimeError:
                pass
        backend, self._backend = self._backend, None   # 置空后读线程循环自然终止
        if backend is not None:
            backend.terminate()


class TerminalPanel(QDockWidget):
    """终端面板（QDockWidget，可停靠右侧/底部）"""

    def __init__(self, program: str = None, cwd: str = None, parent=None):
        super().__init__("终端", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.view = TerminalView(program=program, cwd=cwd, parent=self)
        self.setWidget(self.view)

    def restart(self):
        self.view.restart()

    def set_program(self, program: str):
        """更换终端程序并重启会话（None/空 = 系统默认 shell）"""
        self.view.set_program(program)

    def open_in(self, cwd: str):
        """以指定目录重启终端会话（内置终端中打开目录）"""
        self.view.restart(cwd=cwd)

    def shutdown(self):
        """彻底结束会话：主窗口关闭前调用（避免残留 shell 子进程与悬空投递）"""
        self.view.close_shell(shutdown=True)

    def closeEvent(self, e):
        """点 dock 的 X 只是隐藏面板，**不**杀 shell。

        dock 关闭不会销毁 QDockWidget 对象，若在此 `close_shell()`，用户从菜单
        重新打开终端会看到一个永远不会再有输出的死面板（面板对象还活着，
        会话却已被终止且无人重启）。会话的生命周期改由主窗口关闭接管。
        """
        super().closeEvent(e)
