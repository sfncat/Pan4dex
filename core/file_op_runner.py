"""
Pan4dex 万格 — 文件操作运行器（后台线程 + 进度对话框 + 同名冲突询问）

把 `FileOperations` 放到后台线程执行，配好一整套 UI 配合：进度对话框（速度 /
剩余时间 / 取消）、同名冲突询问（含「对后续冲突同样处理」记忆）、跨线程回投、
宿主已销毁时丢帧不崩。

这套东西原先只长在窗格里（`Pane._run_file_op_async`）。搜索结果列表要做批量
复制/移动/删除时只有两条路：在主线程同步跑（大文件、SMB 上就是把界面冻住，
正是第一阶段花力气消掉的东西），或者把那 ~120 行抄第二份 —— 两份一定会漂
（取消语义、冲突记忆策略、进度文案各留一份）。所以抽出来：宿主只保留
「状态栏写什么、进度条怎么跳、完了刷新谁」。
"""
import logging
import os
import threading

from PyQt6.QtCore import (
    Qt, QObject, QThread, QMetaObject, pyqtSignal, pyqtSlot, Q_ARG)

from core.file_operations import (
    FileOperations, FileOperationType, FileOperationResult)

logger = logging.getLogger("pan4dex.file_op_runner")

# 同名冲突对话框能给出的决策（与 `FileOperations._resolve_conflict` 认的一整套）
_CONFLICT_DECISIONS = ('replace', 'skip', 'keep_both', 'cancel')


class _ConflictAsk:
    """一次同名冲突询问：后台线程放进去、主线程把决策写回来

    不用信号带可变对象（跨线程投递后两边同时读改同一个字典容易被理解为
    「共享可变状态是设计」），这里只靠 `BlockingQueuedConnection` 的同步保证。
    """

    def __init__(self, info: dict):
        self.info = info
        self.decision = ""


class FileOpRunner(QObject):
    """一个宿主（窗格 / 搜索对话框 …）对应一个运行器，同一时刻跑一个操作。

    用法::

        runner = FileOpRunner(host_widget, on_status=host.set_status,
                              on_bar=host.show_progress, on_bar_hide=host.hide_progress)
        runner.run("正在复制", lambda: runner.ops.copy(paths, dest),
                   done=lambda result: ...)

    `run()` 立刻返回（操作在后台线程），完成后 `done(result)` 在主线程被调用。
    不传 `done` 时由 `on_done` 钩子决定收尾（窗格用它在完成后刷新目录）。
    """

    _progress_ui = pyqtSignal(int, str, int, int)   # (percent, filename, copied, total)
    _op_done = pyqtSignal(object, str, object)       # (result, note, done_handler)

    def __init__(self, host, on_status=None, on_bar=None, on_bar_hide=None,
                 on_done=None):
        """
        Args:
            host: 宿主 widget（进度/冲突对话框挂在它下面，随它一起销毁）
            on_status: `fn(text)` 写宿主状态栏（可空）
            on_bar / on_bar_hide: `fn(percent)` / `fn()` 驱动宿主进度条（可空）
            on_done: `fn(result, note, done_handler)` 收尾（可空；空则直接调 done_handler）
        """
        super().__init__(host)
        self.host = host
        self.ops = FileOperations()
        self.on_status = on_status
        self.on_bar = on_bar
        self.on_bar_hide = on_bar_hide
        self.on_done = on_done
        self._policy = None          # 「对后续冲突同样处理」，仅本次操作内有效
        self._dlg = None
        self._note = ""
        self._running = False
        self._progress_ui.connect(self._update_ui)
        self._op_done.connect(self._finish_ui)

    # ------------------------------------------------------------------ 对外

    @property
    def busy(self) -> bool:
        """是否有操作在跑（同一个 `ops` 上再起一个会让取消互相打架）"""
        return self._running

    def cancel(self):
        """请求取消当前操作"""
        self.ops.cancel()

    def run(self, note: str, fn, done=None):
        """后台执行 `fn()`（返回 `FileOperationResult`），完成回 `done(result)`。

        `note` 是进度对话框标题与状态栏前缀（「正在复制」这样）。
        """
        self._running = True
        self._note = note
        self._set_status(f"{note}...")
        if self.on_bar is not None:
            self.on_bar(0)
        self.ops.set_progress_callback(self._on_progress)
        self._policy = None
        self.ops.set_conflict_callback(self._on_conflict)
        self._show_dialog(note)

        def worker():
            try:
                result = fn()
            except Exception as e:
                logger.exception("%s 失败", note)
                result = FileOperationResult(
                    success=False, operation=FileOperationType.COPY,
                    source="", error=str(e))
            self._emit_ui("_op_done", result, note, done)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------- 后台线程侧钩子

    def _on_progress(self, percent: int, filename: str,
                     copied_bytes: int = 0, total_bytes: int = 0):
        """进度回调（后台线程调用）：经信号转主线程"""
        self._emit_ui("_progress_ui", percent, filename, copied_bytes, total_bytes)

    def _on_conflict(self, info: dict) -> str:
        """冲突回调（后台线程调用）：有记忆策略直接用，否则回主线程询问

        答案从共享对象里取，不取 `invokeMethod` 的返回值：PyQt6 在这里拿不到槽
        的返回值（实测第一次冲突得到 None，而 `FileOperations._resolve_conflict`
        把「不在已知选项里」的值当异常处理 → 回退「保留两者」，等于用户在冲突
        框里点的「替换」被静默丢掉。窗格以前走的是同一段代码，同一个毛病。
        """
        if self._policy:
            return self._policy
        ask = _ConflictAsk(info)
        if self.thread() is QThread.currentThread():
            self._ask_conflict_slot(ask)      # 已在主线程：直接问，Blocking 会自锁
        else:
            try:
                QMetaObject.invokeMethod(
                    self, "_ask_conflict_slot", Qt.ConnectionType.BlockingQueuedConnection,
                    Q_ARG(object, ask))
            except Exception:
                logger.exception("冲突询问投递失败")
        return ask.decision if ask.decision in _CONFLICT_DECISIONS else 'keep_both'

    @pyqtSlot(object)
    def _ask_conflict_slot(self, ask):
        """主线程弹冲突对话框，把决策写回 `ask`（勾了「对后续同样处理」则记入策略）"""
        info = dict(ask.info)
        src, dst, is_dir = info.get('src', ''), info.get('dst', ''), bool(info.get('is_dir'))
        try:
            from widgets.conflict_dialog import ConflictDialog
            try:
                info['src_size'] = 0 if is_dir else os.path.getsize(src)
            except OSError:
                info['src_size'] = 0
            try:
                info['src_mtime'] = os.path.getmtime(src)
            except OSError:
                info['src_mtime'] = 0
            try:
                info['dst_size'] = 0 if os.path.isdir(dst) else os.path.getsize(dst)
            except OSError:
                info['dst_size'] = 0
            try:
                info['dst_mtime'] = os.path.getmtime(dst)
            except OSError:
                info['dst_mtime'] = 0
            dlg = ConflictDialog(self.host, info)
            dlg.exec()
            ask.decision = dlg.chosen
            try:
                if dlg.apply_all.isChecked():
                    self._policy = dlg.chosen
            except Exception:
                pass
        except Exception:
            logger.exception("冲突对话框没弹起来")
            ask.decision = 'keep_both'

    # ----------------------------------------------------------- 主线程收尾

    def _update_ui(self, percent: int, filename: str,
                   copied_bytes: int, total_bytes: int):
        """进度（主线程）：刷新宿主状态栏与进度对话框

        前缀用本次操作的 note，不是写死的「正在复制」—— 旧版删除、移动进行时，
        窗格状态栏也写「正在复制: xxx」。
        """
        from widgets.progress_dialog import _fmt_size
        if total_bytes > 0:
            self._set_status(
                f"{self._note}: {filename} "
                f"({_fmt_size(copied_bytes)}/{_fmt_size(total_bytes)})")
        else:
            self._set_status(f"{self._note}: {filename}")
        dlg = self._dlg
        if dlg is not None:
            try:
                dlg.update_progress(percent, filename, copied_bytes, total_bytes)
            except RuntimeError:
                pass        # 对话框已被用户关掉/销毁

    def _finish_ui(self, result, note: str, done):
        self._running = False
        self.ops.set_progress_callback(None)
        self.ops.set_conflict_callback(None)
        self._policy = None
        if self.on_bar_hide is not None:
            self.on_bar_hide()
        self._close_dialog()
        if self.on_done is not None:
            self.on_done(result, note, done)
        elif done is not None:
            done(result)

    # ------------------------------------------------------------- 内部细节

    def _set_status(self, text: str):
        if self.on_status is not None:
            try:
                self.on_status(text)
            except RuntimeError:
                pass            # 宿主已销毁

    def _show_dialog(self, note: str):
        """弹进度对话框（非模态）；上一任务遗留的先销毁"""
        self._close_dialog()
        try:
            from widgets.progress_dialog import FileProgressDialog
            self._dlg = FileProgressDialog(self.host, note)
            self._dlg.cancel_requested.connect(self.cancel)
            self._dlg.show()
        except Exception:
            # 建不起来就接着跑操作，但必须说得出声：旧版窗格把这句默默吃了，
            # 于是进度对话框（含唯一的取消入口）从来没出现过也没人发现
            logger.warning("进度对话框创建失败，本次操作没有进度与取消入口",
                           exc_info=True)
            self._dlg = None

    def _close_dialog(self):
        dlg, self._dlg = self._dlg, None
        if dlg is not None:
            try:
                dlg.mark_finished()
                dlg.close()
                dlg.deleteLater()
            except RuntimeError:
                pass

    def _emit_ui(self, signal_name: str, *args):
        """后台线程向主线程投递信号（对宿主销毁做防御）。

        与 `core/pane.py`、`widgets/terminal_panel.py` 的同名方法同一动机：
        关闭对话框、退出应用会把宿主的 C++ 对象删掉，此时 `self.xxx.emit(...)`
        抛 `RuntimeError: wrapped C/C++ object ... has been deleted`；连取信号对象
        本身都会抛，所以参数是信号**名字**、放在 try 里 getattr。
        丢一帧进度或一次完成通知，远好过让应用崩溃。
        """
        try:
            getattr(self, signal_name).emit(*args)
        except RuntimeError:
            pass
