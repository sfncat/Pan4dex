# -*- coding: utf-8 -*-
"""文件操作运行器（`core/file_op_runner.py`）。

它把 `FileOperations` 丢到后台线程，再配一整套主线程 UI：进度对话框、同名冲突
询问、状态栏、取消。这些配合只能靠真起线程来测，所以用例都用 `qtbot.waitUntil`
等它跑完，不 sleep。

这套东西原来是窗格私有的（`Pane._run_file_op_async`），抽出来是为了搜索结果
列表能做批量复制/移动/删除；因此这里也钉住「窗格确实在用它」。
"""
import os
import threading

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QWidget

from core.file_op_runner import FileOpRunner
from core.file_operations import FileOperationResult, FileOperationType


def ok_result(files=1):
    return FileOperationResult(success=True, operation=FileOperationType.COPY,
                               source="", files_affected=files)


@pytest.fixture
def env(qtbot):
    """`(host, runner, 状态文字列表, 进度条数值列表)` —— 钩子都记成列表好断言"""
    host = QWidget()
    qtbot.addWidget(host)
    status, bars = [], []
    runner = FileOpRunner(host, on_status=status.append, on_bar=bars.append,
                          on_bar_hide=lambda: bars.append("hide"))
    return host, runner, status, bars


def wait_done(qtbot, pred, timeout=5000):
    """等后台任务把结果投回主线程（`done` 钩子在队列信号里，需要转事件循环）"""
    qtbot.waitUntil(pred, timeout=timeout)


def test_run_executes_off_the_main_thread_and_reports_done(env, qtbot):
    _, runner, status, bars = env
    main_thread = threading.get_ident()
    where = {}
    done = []

    def fn():
        where["thread"] = threading.get_ident()
        return ok_result(3)

    runner.run("正在复制", fn, done=done.append)
    wait_done(qtbot, lambda: bool(done))

    assert where["thread"] != main_thread
    assert done[0].files_affected == 3
    assert status[0] == "正在复制..."
    assert bars[0] == 0 and bars[-1] == "hide"
    assert runner.busy is False
    # 完成后必须拆回调：不然一个已结束的 runner 还会往宿主写状态栏
    assert runner.ops._progress_callback is None
    assert runner.ops._conflict_callback is None


def test_done_is_not_called_before_the_thread_finishes(env, qtbot):
    """操作没跑完之前不能提前回调（也不能把主线程堵住）"""
    _, runner, _, _ = env
    release = threading.Event()
    done = []

    def fn():
        release.wait(5)
        return ok_result()

    runner.run("正在删除", fn, done=done.append)
    assert runner.busy is True
    assert done == []
    release.set()
    wait_done(qtbot, lambda: bool(done))
    assert runner.busy is False


def test_exception_inside_the_operation_becomes_a_result(env, qtbot):
    """worker 抛异常要变成失败结果：否则进度框会一直挂着、`busy` 永远不洗"""
    _, runner, _, _ = env
    done = []

    def boom():
        raise OSError("盘上出错了")

    runner.run("正在复制", boom, done=done.append)
    wait_done(qtbot, lambda: bool(done))
    assert done[0].success is False
    assert "盘上出错了" in done[0].error
    assert runner.busy is False


def test_progress_status_uses_this_operations_verb(env, qtbot):
    """进度文案前缀取本次的 note（旧实现写死「正在复制」，删除时也显示「正在复制」）"""
    _, runner, status, _ = env

    def fn():
        runner.ops._progress_callback(50, "a.bin", 500, 1000)
        return ok_result()

    runner.run("正在删除", fn)
    wait_done(qtbot, lambda: any("正在删除: a.bin" in s for s in status))
    assert not any(s.startswith("正在复制") for s in status)


def test_progress_dialog_cancel_reaches_the_operation(env, qtbot):
    """进度框的「取消」要真的能传到 `FileOperations.cancel`（旧代码里它就长在窗格）"""
    _, runner, _, _ = env
    release = threading.Event()

    def fn():
        release.wait(5)
        return ok_result()

    runner.run("正在复制", fn)
    assert runner._dlg is not None
    runner._dlg.cancel_requested.emit()
    assert runner.ops.is_cancelled() is True
    release.set()
    wait_done(qtbot, lambda: not runner.busy)
    assert runner._dlg is None                 # 收完尾，进度框不能留在屏幕上


def test_apply_all_policy_stops_asking_again(env, qtbot, monkeypatch):
    """勾选「对后续冲突执行相同操作」后同一批剩下的不再逐个问，下次操作重新问"""
    import widgets.conflict_dialog as cd

    _, runner, _, _ = env
    asked = []

    class CheckBox:
        def isChecked(self):
            return True

    class FakeConflictDialog:
        def __init__(self, parent, info):
            asked.append(info)
            self.chosen = "skip"
            self.apply_all = CheckBox()

        def exec(self):
            return 0

    monkeypatch.setattr(cd, "ConflictDialog", FakeConflictDialog)
    got = []

    def fn():
        for i in range(3):
            got.append(runner._on_conflict({"src": f"s{i}", "dst": f"d{i}",
                                            "is_dir": False}))
        return ok_result()

    runner.run("正在复制", fn)
    wait_done(qtbot, lambda: len(got) == 3)
    assert got == ["skip"] * 3
    assert len(asked) == 1
    wait_done(qtbot, lambda: not runner.busy)
    assert runner._policy is None              # 记忆只在本次操作内有效


def test_frames_after_the_host_is_gone_are_dropped():
    """宿主先没、任务还在跑：投递必须静默丢帧，不能把应用崩掉

    不用 `env` fixture：它把宿主交给了 qtbot，qtbot 收尾时要 `close()` 一个
    已被 `sip.delete` 的对象，会在自己这里报错过。
    """
    host = QWidget()
    runner = FileOpRunner(host, on_status=lambda text: None)
    sip.delete(host)
    runner._emit_ui("_op_done", ok_result(), "正在复制", None)
    runner._on_progress(50, "f.bin", 1, 2)


def test_conflict_asked_on_the_main_thread_does_not_use_a_blocking_call(env, monkeypatch):
    """已在主线程时不能走 `BlockingQueuedConnection`：那是主线程等主线程，永久自锁

    调用者不一定是后台线程（窗格在主线程里同步删文件也会问冲突）。这里不
    真让 `invokeMethod` 去阻塞（一旦回归就是整个会话挂住），而是直接断言它没被调用。
    """
    import widgets.conflict_dialog as cd
    from core import file_op_runner as fr

    _, runner, _, _ = env
    invoked = []

    class NoInvoke:
        @staticmethod
        def invokeMethod(*a, **k):
            invoked.append(a)
            return True

    class FakeConflictDialog:
        def __init__(self, parent, info):
            self.chosen = "replace"
            self.apply_all = None

        def exec(self):
            return 0

    monkeypatch.setattr(fr, "QMetaObject", NoInvoke)
    monkeypatch.setattr(cd, "ConflictDialog", FakeConflictDialog)

    assert runner._on_conflict({"src": "s", "dst": "d", "is_dir": False}) == "replace"
    assert invoked == []


def test_an_unparsable_decision_falls_back_instead_of_silently_replacing(env, monkeypatch):
    """对话框没弹起来时不能把用户没点过的「替换」当默认值（旧代码就是丢答案）"""
    import widgets.conflict_dialog as cd

    _, runner, _, _ = env

    class BrokenDialog:
        def __init__(self, parent, info):
            raise RuntimeError("对话框创建不了")

    monkeypatch.setattr(cd, "ConflictDialog", BrokenDialog)
    assert runner._on_conflict({"src": "s", "dst": "d", "is_dir": False}) == "keep_both"


def test_pane_runs_its_operations_through_the_runner(qtbot, tmp_path, monkeypatch):
    """窗格确实走这个 runner（不然「抽出来了」只是名义上的，仍是两份实现）"""
    from core.pane import Pane

    pane = Pane("t_runner", start_path=str(tmp_path))
    qtbot.addWidget(pane)
    seen = []
    monkeypatch.setattr(pane.op_runner, "run",
                        lambda note, fn, done=None: seen.append((note, done)))

    handler = lambda result: None
    pane._run_file_op_async("正在复制", lambda: None, done_handler=handler)

    assert seen == [("正在复制", handler)]
    assert pane.file_ops is pane.op_runner.ops
