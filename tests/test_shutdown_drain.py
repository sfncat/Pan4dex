"""
Pan4dex 万格 — 退出阶段后台线程收拢（drain_background_pool）回归测试

覆盖的缺陷：窗格销毁 / 进程退出时，`QThreadPool.globalInstance()` 上仍有在飞的目录
枚举任务与其未派发的跨线程投递。这些投递事件持有 Python 对象，Qt 在解释器已开始
收尾时才去销毁它们 —— Windows 上表现为无可捕异常的 fast-fail（退出码 0xC0000409），
用户侧就是「关掉程序时报错」；在测试全量连跑时则是偶发 access violation。

开发机实测（一次性探针取证，200 个模型 × 真实枚举 System32、收尾不调 drain）：
不排空 8/8 崩溃（退出码 0xC0000409），调用 `drain_background_pool()` 后 8/8 干净。
触发量与目录条目数相关，故本文件里只有下面标了 skipif 的 A/B 用例需要大目录，
其余用例用小目录也能确定性地验证契约。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QThreadPool

from core.lifecycle import drain_background_pool

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])


@pytest.fixture
def big_dir(tmp_path):
    """一个条目足够多的本地目录（保证枚举真的会「在飞」一段时间）"""
    d = tmp_path / "many"
    d.mkdir()
    for i in range(600):
        (d / f"file_{i:04d}.txt").write_text("x", encoding="utf-8")
    return str(d)


def test_drain_delivers_pending_load_result(qapp, big_dir):
    """排空后，已经算完但还没派发的枚举结果必须落到模型里（不得被丢掉）"""
    from core.dir_model import DirStoreModel

    m = DirStoreModel()
    node = m._ensure_node(big_dir)
    m._start_load(node)
    QThreadPool.globalInstance().waitForDone(10000)   # 任务跑完，但结果还挂在队列里
    assert node.loaded is False, "前置条件不成立：结果已被派发，测不到投递"

    drain_background_pool()
    assert node.loaded is True
    assert len(node.entries) == 600


def test_drain_leaves_pool_idle(qapp, big_dir):
    """排空后线程池不再有任何待执行任务"""
    from core.dir_model import DirStoreModel

    models = []
    for _ in range(30):
        m = DirStoreModel()
        m.set_directory(big_dir)
        models.append(m)          # 持有引用：不让模型先于排空被回收
    drain_background_pool()
    assert QThreadPool.globalInstance().waitForDone(0) is True


def test_exec_and_drain_drains_right_after_the_loop(monkeypatch):
    """生产退出路径的接线：事件循环一返回就必须排空，两者不得拆开

    `main.py` 里手写两行语句迟早会被新加的退出路径绕过，因此把不变式收进
    `exec_and_drain()`，在这里用假 app 验证顺序与退出码传递。
    """
    from core import lifecycle

    events = []

    class FakeApp:
        def exec(self):
            events.append("loop")
            return 7

    monkeypatch.setattr(lifecycle, "drain_background_pool",
                        lambda *a, **k: events.append("drain"))
    assert lifecycle.exec_and_drain(FakeApp()) == 7
    assert events == ["loop", "drain"]


# -- 子进程：真实复现「退出阶段崩溃」并验证修复 --------------------------------

CHILD_SOURCE = '''
import os, sys, time
sys.path.insert(0, sys.argv[1])
from PyQt6.QtCore import QCoreApplication, QThreadPool
from PyQt6.QtWidgets import QApplication

app = QApplication([])
import core.dir_model as dm

target, mode, rounds = sys.argv[2], sys.argv[3], int(sys.argv[4])
models = []
for _ in range(rounds):
    m = dm.DirStoreModel()
    # 绕过类级缓存（同一路径第 2 个模型起会直接命中缓存而不发后台任务），
    # 保证每一轮都真的产生一次后台枚举 + 一次跨线程投递
    node = m._ensure_node(target)
    node.loaded = False
    node.entries = None
    m._start_load(node)
    models.append(m)

# 只等后台跑完，**不转事件循环**：枚举结果全部以挂起的 queued 投递留在队列里
QThreadPool.globalInstance().waitForDone(30000)

if mode == "drain":
    from core.lifecycle import drain_background_pool
    drain_background_pool()
print("child done", flush=True)
'''


def _run_child(tmp_path, big_dir, mode, rounds):
    script = tmp_path / "drain_child.py"
    script.write_text(CHILD_SOURCE, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), PROJECT_ROOT, big_dir, mode, str(rounds)],
        capture_output=True, text=True, timeout=180,
    )
    return proc.returncode, proc.stdout.strip()


def test_child_with_undelivered_loads_exits_clean_after_drain(tmp_path, big_dir):
    """攒下 200 轮未派发的枚举投递后走排空退出：必须干净结束（不得挂、不得崩）"""
    rc, out = _run_child(tmp_path, big_dir, "drain", 200)
    assert "child done" in out
    assert rc == 0, f"排空后仍异常退出: {rc:#x}"


@pytest.mark.skipif(
    not os.environ.get("PAN4DEX_SHUTDOWN_CRASH_TARGET"),
    reason="需指定 PAN4DEX_SHUTDOWN_CRASH_TARGET=<一个数千条目的目录> 才跑退出崩溃 A/B"
           "（触发量与目录条目数相关，开发机上用 C:\\Windows\\System32）",
)
def test_draining_is_what_makes_the_process_exit_clean(tmp_path):
    """同一卷量下 A/B：不排空直接退出会 fast-fail；排空后必须退出码 0

    崩溃取决于“退出时残留多少未派发投递”，需要足够大的目录（实测数千条目 × 200
    模型）才能触发，在 CI/临时目录上跑不出来，因此默认跳过，只在开发机上手工打开。
    """
    target = os.environ["PAN4DEX_SHUTDOWN_CRASH_TARGET"]
    rounds = int(os.environ.get("PAN4DEX_SHUTDOWN_CRASH_ROUNDS", "200"))
    bare_rc, _ = _run_child(tmp_path, target, "bare", rounds)
    assert bare_rc != 0, f"对照组没崩（{bare_rc:#x}）：{target} 达不到触发量，A/B 无意义"
    drain_rc, out = _run_child(tmp_path, target, "drain", rounds)
    assert "child done" in out
    assert drain_rc == 0, f"排空后仍异常退出: {drain_rc:#x}"
