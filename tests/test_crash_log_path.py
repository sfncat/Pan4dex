"""崩溃日志落点的选择逻辑（main.py 的 resolve_crash_log_path / install_signal_handlers）

起因是 Linux 真机：把产物放进 root 拥有的目录后，`install_signal_handlers()` 里那句
`open(<exe 同级>/pan4dex_crash.log, 'w')` 抛 PermissionError，而它是 `main()` 里比窗口
创建还早的一步 —— 崩溃日志这道安全网反过来成了启动即死的扳机。Windows 装在
`Program Files` 下是同一件事，只是本机从没那么装过所以没人看见。

这些用例钉的是「**永远找一个能写的地方，且绝不抛**」这条不变式。
"""
import os
import sys
import faulthandler

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_resolved_path():
    """解析结果与文件句柄都是模块级状态，用例之间必须清干净"""
    main._CRASH_LOG_PATH = ""
    yield
    main._CRASH_LOG_PATH = ""
    fh, main._CRASH_LOG_FH = main._CRASH_LOG_FH, None
    if fh is not None:
        faulthandler.enable()          # 先把段错误输出改回 stderr，再关文件
        try:
            fh.close()
        except OSError:
            pass


def _under_a_file(tmp_path, name="pan4dex_crash.log"):
    """造一个必定写不了的落点：父目录是一段普通文件的路径（跨平台，不用 chmod）"""
    blocker = tmp_path / "blocker.bin"
    blocker.write_bytes(b"")
    return str(blocker / "sub" / name)


def test_candidate_order_exe_dir_first(tmp_path, monkeypatch):
    """首选仍是可执行文件同目录（发布流程与文档都按 releases/pan4dex_crash.log 找）"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "pan4dex"))
    (tmp_path / "bin").mkdir()

    cands = main._crash_log_candidates()
    assert cands[0] == os.path.join(str(tmp_path / "bin"), main.CRASH_LOG_NAME)
    assert len(cands) >= 2, "至少要有一个退路"
    assert all(c != cands[0] for c in cands[1:])


def test_falls_back_when_exe_dir_unwritable(tmp_path, monkeypatch):
    """第一个落点写不了就退到下一个，而不是抛出去"""
    ok = str(tmp_path / "ok" / main.CRASH_LOG_NAME)
    monkeypatch.setattr(main, "_crash_log_candidates",
                        lambda: [_under_a_file(tmp_path), ok])

    assert main.resolve_crash_log_path() == ok
    # 结果被缓存：后续调用不能再换地方（三个写入点必须写到同一个文件）
    assert main.resolve_crash_log_path() == ok


def test_never_raises_when_nothing_is_writable(tmp_path, monkeypatch):
    """一个候选都写不了时也不抛 —— 返回第一个，让调用方自己包写入异常"""
    bad = _under_a_file(tmp_path)
    monkeypatch.setattr(main, "_crash_log_candidates", lambda: [bad])

    assert main.resolve_crash_log_path() == bad


def test_probe_does_not_truncate_existing_log(tmp_path, monkeypatch):
    """试探阶段用 'a'：解析路径不能把上一次的崩溃日志清空（那是唯一的事发现场）"""
    log = tmp_path / main.CRASH_LOG_NAME
    log.write_text("现场：上一次的段错误栈\n", encoding="utf-8")
    monkeypatch.setattr(main, "_crash_log_candidates", lambda: [str(log)])

    main.resolve_crash_log_path()

    assert log.read_text(encoding="utf-8") == "现场：上一次的段错误栈\n"


def test_signal_handlers_survive_unwritable_log(tmp_path, monkeypatch):
    """启动第一步就得活着：写不了崩溃日志时 faulthandler 退到 stderr，不抛异常"""
    monkeypatch.setattr(main, "_crash_log_candidates",
                        lambda: [_under_a_file(tmp_path)])
    was_enabled = faulthandler.is_enabled()
    try:
        main.install_signal_handlers()          # 这里抛出来就是回归
        assert faulthandler.is_enabled(), "退到 stderr 也要保持段错误可捕获"
    finally:
        if not was_enabled:
            faulthandler.disable()


def test_signal_handlers_log_still_lands_somewhere(tmp_path, monkeypatch):
    """首选写不了时，崩溃日志仍必须落在文件里

    只验“不抛异常”不够：`install_signal_handlers` 自己包了 OSError，哪怕退路完全
    失效它也能“不抛”—— 但那时用户什么日志都拿不到，与没修一样。
    """
    ok = tmp_path / "ok" / main.CRASH_LOG_NAME
    monkeypatch.setattr(main, "_crash_log_candidates",
                        lambda: [_under_a_file(tmp_path), str(ok)])
    was_enabled = faulthandler.is_enabled()
    try:
        main.install_signal_handlers()
        assert ok.exists(), "退路没生效：崩溃日志一个字都没写"
        # 看项目自己持有的那个句柄（faulthandler.get_file() 在当前 Python 上没有，
        # 而 _CRASH_LOG_FH 本来就是为了“别让文件被 GC 关掉”而存在的引用）
        fh = main._CRASH_LOG_FH
        assert fh is not None and os.path.samefile(fh.name, str(ok)), \
            "faulthandler 没接到退路上的文件"
    finally:
        if not was_enabled:
            faulthandler.disable()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 权限语义：Windows 上 chmod 不拦写")
def test_read_only_install_dir_falls_back_posix(tmp_path, monkeypatch):
    """真机场景原样复刻：exe 同级目录只读（如 /opt 下 root 拥有的安装目录）"""
    install = tmp_path / "opt" / "pan4dex"
    install.mkdir(parents=True)
    (install / "pan4dex").write_bytes(b"")
    os.chmod(str(install), 0o500)               # r-x：属主也写不了
    first = str(install / main.CRASH_LOG_NAME)
    orig = main._crash_log_candidates
    monkeypatch.setattr(main, "_crash_log_candidates",
                        lambda: [first] + orig())

    try:
        got = main.resolve_crash_log_path()
    finally:
        os.chmod(str(install), 0o700)

    assert got != first, "只读安装目录里写不了日志，必须退到别处而不是抛"
    assert os.access(os.path.dirname(got), os.W_OK)
