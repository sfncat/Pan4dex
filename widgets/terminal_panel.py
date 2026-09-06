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

from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout, QMenu, QDockWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QAction, QKeySequence

import pyte

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

    def __init__(self, program: str, cwd: str = None, cols: int = 100, rows: int = 24):
        self.program = program
        self.cwd = cwd or os.path.expanduser("~")
        self.cols, self.rows = cols, rows
        self._proc = None
        self._master_fd = None  # Linux only

    # -- 生命周期 ----------------------------------------------------------
    def start(self):
        if sys.platform == "win32":
            from winpty import PtyProcess
            argv = self.program if isinstance(self.program, (list, tuple)) else [self.program]
            self._proc = PtyProcess.spawn(
                argv, cwd=self.cwd, dimensions=(self.rows, self.cols)
            )
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

        self._program = program or self._default_shell()
        self._cwd = cwd or os.path.expanduser("~")
        self._cols, self._rows = 100, 24
        self.MAX_RENDER_LINES = 2000  # 渲染文档行数上限（防止超长输出无限增长）
        self._hist_cache = []         # 历史行文本增量缓存
        self._cache_pages = []        # 缓存对应的页快照（用于检测顶部丢页）
        self._screen = pyte.HistoryScreen(self._cols, self._rows, history=2000)
        self._stream = pyte.Stream(self._screen)
        self._backend = None
        self._last_text = ""
        self._user_scrolled_up = False
        self._resize_pending = False
        self._reader = None          # 后台读线程
        self._closing = False
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

        self._start_shell()

    # -- 默认终端程序 ------------------------------------------------------
    @staticmethod
    def _default_shell():
        if sys.platform == "win32":
            # 优先 PowerShell 7 (pwsh)，回退 Windows PowerShell。
            # 关闭 PSReadLine 内联预测：预测文本以半透明样式输出，终端模拟器
            # 无法渲染其灰色样式，会显示成"真实输入"的干扰内容（Tab 补全不受影响）。
            import shutil
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
            return [shell, "-NoLogo", "-NoExit", "-Command",
                    "Set-PSReadLineOption -PredictionSource None"]
        return os.environ.get("SHELL", "/bin/bash")

    def _start_shell(self):
        try:
            self._backend = PtyBackend(self._program, self._cwd, self._cols, self._rows)
            self._backend.start()
            self._alive_timer.start(500)
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            logger.info(f"终端已启动: program={self._program} cwd={self._cwd}")
        except Exception as e:
            logger.error(f"终端启动失败: {e}", exc_info=True)
            self.setPlainText(f"终端启动失败: {e}\n程序: {self._program}")

    def set_program(self, program: str):
        """更换终端程序并重启会话（None/空 = 系统默认 shell）"""
        self._program = program or self._default_shell()
        self.restart()

    def restart(self, cwd: str = None):
        """重启终端会话（cwd 指定后以该目录启动 shell）"""
        if cwd is not None:
            self._cwd = cwd
        if self._backend is not None:
            self._backend.terminate()
            self._backend = None
        self._reader = None
        self._screen = pyte.HistoryScreen(self._cols, self._rows, history=2000)
        self._stream = pyte.Stream(self._screen)
        self._hist_cache = []
        self._cache_pages = []
        self._last_text = ""
        self._exited_shown = False
        self.clear()
        self._start_shell()

    # -- 读线程 ------------------------------------------------------------
    def _read_loop(self):
        """后台线程：阻塞读 PTY 输出并转发到主线程。

        Windows（pywinpty read 无数据即阻塞）返回数据或 EOF；
        Linux（os.read 非阻塞）无数据返回空串，需短暂等待再读，
        否则循环会立即退出并误报"进程已退出"。
        """
        backend = self._backend
        while backend is not None and backend is self._backend:
            try:
                data = backend.read(65536)
                if data:
                    self.output_received.emit(data)
                    continue
                # 无数据：Linux 非阻塞读返回空，稍候再读（Windows 阻塞读不至此）
                time.sleep(0.03)
            except EOFError:
                break
            except Exception:
                break
        if not self._closing:
            self.process_exited.emit()

    # -- 输出渲染 ----------------------------------------------------------
    def _on_output(self, data: str):
        self._stream.feed(data)
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
            QTimer.singleShot(80, self._sync_pty_size)

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

    def close_shell(self):
        self._closing = True
        if self._backend is not None:
            self._backend.terminate()
            self._backend = None


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

    def closeEvent(self, e):
        self.view.close_shell()
        super().closeEvent(e)
