"""崩溃日志落点的选择逻辑（main.py 的 resolve_crash_log_path / install_signal_handlers）

起因是 Linux 真机：把产物放进 root 拥有的目录后，`install_signal_handlers()` 里那句
`open(<exe 同级>/pan4dex_crash.log, 'w')` 抛 PermissionError，而它是 `main()` 里比窗口
创建还早的一步 —— 崩溃日志这道安全网反过来成了启动即死的扳机。Windows 装在
`Program Files` 下是同一件事，只是本机从没那么装过所以没人看见。

这些用例钉的是两条不变式：

1. **永远找一个能写的地方，且绝不抛**（启动第一步就得活着）；
2. **日志只追加、不截断**（只有追加，才能活过“崩了 → 再双击一次”这个用户动作），
   同时有尺寸上限；同一类不变式也适用于文件日志（`setup_logging`）。
"""
import os
import sys
import logging
import tempfile
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


# ---- 追加而不是截断：重启不得清空上一次的崩溃现场 ------------------------------------

def test_restart_keeps_previous_crash_scene(tmp_path, monkeypatch):
    """上一次的栈必须还在：用户的顺序是“崩了 → 再双击一次试试”，重启会洗掉现场

    以前三处写入点都用 `'w'`，每次成功启动就把上一次崩溃日志截成 0 字节 —— 本仓追
    偶发段错误时反复看到的“日志文件在、内容是空的”就是这么来的。
    """
    log = tmp_path / main.CRASH_LOG_NAME
    scene = "Windows fatal exception: access violation\n\nThread 0x00001a2c:\n"
    log.write_text(scene, encoding="utf-8")
    monkeypatch.setattr(main, "_crash_log_candidates", lambda: [str(log)])
    was_enabled = faulthandler.is_enabled()
    try:
        main.install_signal_handlers()
    finally:
        if not was_enabled:
            faulthandler.disable()

    kept = log.read_text(encoding="utf-8")
    assert scene in kept, "启动截断了上一次的崩溃现场"
    assert "启动于" in kept, "没写本次启动的起始标记，无法区分哪一段是哪次运行留下的"


def test_write_crash_log_appends(tmp_path, monkeypatch):
    """启动失败时写的新崩溃，也不能顶掉已有的旧崩溃"""
    log = tmp_path / main.CRASH_LOG_NAME
    log.write_text("旧的一次崩溃\n", encoding="utf-8")
    monkeypatch.setattr(main, "_crash_log_candidates", lambda: [str(log)])
    # 错误对话框在用例里必须不能真弹（Win 上会阻塞整个会话）
    monkeypatch.setattr(main, "_show_error_box", lambda title, text: None)

    got = main.write_crash_log("新的崩溃：PermissionDenied")

    assert got == str(log)
    kept = log.read_text(encoding="utf-8")
    assert "旧的一次崩溃" in kept and "新的崩溃：PermissionDenied" in kept


def test_crash_log_size_is_bounded(tmp_path, monkeypatch):
    """追加写不等于无限增长：超过上限才另起一段"""
    log = tmp_path / main.CRASH_LOG_NAME
    log.write_text("x" * (main._CRASH_LOG_MAX_BYTES + 1024), encoding="utf-8")
    monkeypatch.setattr(main, "_crash_log_candidates", lambda: [str(log)])
    was_enabled = faulthandler.is_enabled()
    try:
        main.install_signal_handlers()
    finally:
        if not was_enabled:
            faulthandler.disable()

    assert os.path.getsize(str(log)) < main._CRASH_LOG_MAX_BYTES, "该轮转时没轮转"


# ---- 同一类不变式推广到日志系统本身 -------------------------------------------------

def test_setup_logging_survives_unwritable_log_dir(monkeypatch, capsys):
    """文件日志写不了时只退成“没文件日志”，不能报错退出

    `setup_logging()` 在 `import main` 时就跑，比 `main()` 还早；HOME 未设 / 配置目录
    只读 / 磁盘满 都会让 `makedirs` 与 `FileHandler` 抛 OSError，那又是同一个
    “日志把程序弄死”的故事。只验不抛在这里也不够（函数自己包了异常），所以同时
    验“logger 仍可用、stderr 上能看见降级提示”。
    """
    root = logging.getLogger("pan4dex")
    before = list(root.handlers)
    base = tempfile.mkdtemp()
    a_file = os.path.join(base, "blocker.bin")
    with open(a_file, "wb"):
        pass
    blocked = os.path.join(a_file, "nope")                 # 父目录是普通文件 → 必写不了
    try:
        if sys.platform == "win32":
            monkeypatch.setenv("APPDATA", blocked)
        else:
            monkeypatch.setenv("HOME", blocked)

        logger = main.setup_logging()                      # 这里抛出来就是回归
        assert logger is root
        logger.info("降级后仍可用")
        assert not any(
            isinstance(h, logging.FileHandler) and blocked in h.baseFilename
            for h in root.handlers
        ), "写不了的 FileHandler 不应再挂到 logger 上"
        assert "文件日志不可用" in capsys.readouterr().err
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass
