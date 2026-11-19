# -*- coding: utf-8 -*-
"""跨 RDP 剪贴板「虚拟文件」粘贴回归（gotchas #69）

现场：在嵌套远程桌面里复制文件，回到本机 Pan4dex 按 Ctrl+V **完全没反应**。
实测剪贴板上只有 FileGroupDescriptorW + FileContents，没有 CF_HDROP /
FileNameW / 文本 / uri-list，旧的三条路径分支全落空 → `_paste_to` 静默 return。

覆盖：
- 结构体布局守卫（sizeof 592 / cFileName +72，以真机 dump 为准，铁律 #11）
- 描述符解析（项数、>4GB 大小、目录属性、越界截断）
- 远端文件名消毒（路径穿越 / ADS 冒号 / 保留设备名 / 控制字符）
- 落盘字节一致；目录 / 字节数不符 / 超大 / 空流一律拒绝且**不留半个文件**
- 尺寸闸门在取字节**之前**（否则超限文件先读满会冻住界面）
- 窗格接线：改前空手 vs 改后拿到文件；剪切一律按复制；临时落点收尾清理
"""
import ctypes
import os
import struct
import sys
import tempfile

import pytest

from core import rdp_files

# 2026-11-19 真机 dump 的偏移，独立于被测模块写死在这里：
# 模块里的结构体若抄错（gotchas #68 的 80 vs 72 那类），这些用例才会炸。
_DESC_SIZE = 592
_OFF_FLAGS = 0
_OFF_ATTRS = 36
_OFF_SIZE_HI = 64
_OFF_SIZE_LO = 68
_OFF_NAME = 72

_FD_FILESIZE = 0x0040
_ATTR_ARCHIVE = 0x20
_ATTR_DIRECTORY = 0x10
_REAL_FLAGS = 0x4064      # 实测：PROGRESSUI|FILESIZE|WRITESTIME|ATTRIBUTES


def _descriptor(name, size=0, attrs=_ATTR_ARCHIVE, flags=_REAL_FLAGS):
    """按实测偏移手工拼一个 FILEDESCRIPTORW（不借被测模块的结构体）"""
    buf = bytearray(_DESC_SIZE)
    struct.pack_into("<I", buf, _OFF_FLAGS, flags)
    struct.pack_into("<I", buf, _OFF_ATTRS, attrs)
    struct.pack_into("<I", buf, _OFF_SIZE_HI, (size >> 32) & 0xFFFFFFFF)
    struct.pack_into("<I", buf, _OFF_SIZE_LO, size & 0xFFFFFFFF)
    encoded = name.encode("utf-16-le")[:518]      # 260 WCHAR，末尾留 NUL
    buf[_OFF_NAME:_OFF_NAME + len(encoded)] = encoded
    return bytes(buf)


def _block(*descs):
    return struct.pack("<I", len(descs)) + b"".join(descs)


# ---------- 布局守卫 ----------

def test_descriptor_layout_matches_measured_dump():
    assert rdp_files.DESCRIPTOR_SIZE == 592
    assert rdp_files.NAME_OFFSET == 72
    assert rdp_files.ATTRS_OFFSET == 36
    assert rdp_files.SIZEHIGH_OFFSET == 64
    assert rdp_files.SIZELOW_OFFSET == 68
    fd = rdp_files._FILEDESCRIPTORW
    assert ctypes.sizeof(fd()) == 592
    assert fd.dwFlags.offset == 0
    assert fd.clsid.offset == 4
    assert fd.sizel.offset == 20
    assert fd.pointl.offset == 28
    assert fd.ftCreationTime.offset == 40
    assert fd.ftLastAccessTime.offset == 48
    assert fd.ftLastWriteTime.offset == 56
    # c_wchar 在 Linux 上是 4 字节，用它会让名字字段变 1040 → 必须是 2 字节宽
    assert fd.cFileName.size == 520


# ---------- 描述符解析 ----------

def test_parse_real_sample_shape():
    """实测样本的形状：SystemUI.html / 1706 字节 / attrs 0x20 / flags 0x4064"""
    raw = _block(_descriptor("SystemUI.html", size=1706))
    assert len(raw) == 596
    files = rdp_files.parse_descriptors(raw)
    assert len(files) == 1
    assert files[0].name == "SystemUI.html"
    assert files[0].size == 1706
    assert files[0].is_dir is False
    assert files[0].size_known is True
    assert files[0].flags == _REAL_FLAGS


def test_parse_size_over_4gb_uses_high_word():
    raw = _block(_descriptor("big.bin", size=(1 << 32) + 7))
    assert rdp_files.parse_descriptors(raw)[0].size == 4294967303


def test_parse_directory_attribute():
    raw = _block(_descriptor("photos", attrs=_ATTR_DIRECTORY))
    assert rdp_files.parse_descriptors(raw)[0].is_dir is True


def test_parse_size_unknown_without_fd_filesize():
    raw = _block(_descriptor("x.txt", size=99, flags=_REAL_FLAGS & ~_FD_FILESIZE))
    f = rdp_files.parse_descriptors(raw)[0]
    assert f.size_known is False


def test_parse_multiple_items():
    raw = _block(_descriptor("a.txt", 1), _descriptor("b.txt", 2))
    files = rdp_files.parse_descriptors(raw)
    assert [f.name for f in files] == ["a.txt", "b.txt"]
    assert [f.size for f in files] == [1, 2]


def test_parse_truncated_block_stops_instead_of_raising():
    """项数说 3 个但只给了 2 个：描述符来自另一台机器，长度不可信"""
    raw = _block(_descriptor("a.txt", 1), _descriptor("b.txt", 2))
    raw = struct.pack("<I", 3) + raw[4:]
    assert [f.name for f in rdp_files.parse_descriptors(raw)] == ["a.txt", "b.txt"]


def test_parse_empty_and_short_blocks():
    assert rdp_files.parse_descriptors(b"") == []
    assert rdp_files.parse_descriptors(b"\x01\x00") == []
    assert rdp_files.parse_descriptors(struct.pack("<I", 1)) == []


def test_parse_unicode_name():
    raw = _block(_descriptor("照片 001.jpg", 3))
    assert rdp_files.parse_descriptors(raw)[0].name == "照片 001.jpg"


# ---------- 文件名消毒 ----------

@pytest.mark.parametrize("name", [
    "", ".", "..", "...", "   ", "a\nb.txt", "a<b.txt", 'a"b.txt',
    "a:b.txt", "a|b.txt", "a?b.txt", "a*b.txt",
    "NUL", "nul.txt", "CON", "con.log", "PRN", "AUX",
    "COM1", "com9.txt", "LPT1", "lpt9.log",
])
def test_unsafe_names_rejected(name):
    assert rdp_files.safe_name(name) is None


@pytest.mark.parametrize("name,want", [
    ("SystemUI.html", "SystemUI.html"),
    ("照片 001.jpg", "照片 001.jpg"),
    ("name.", "name"),                 # Windows 不允许末尾点
    ("  spaced.txt  ", "spaced.txt"),
    ("console.txt", "console.txt"),    # 不是保留名，别误杀
    ("COM10.txt", "COM10.txt"),        # 只 COM1-9 是设备名
])
def test_safe_names_kept(name, want):
    assert rdp_files.safe_name(name) == want


def test_path_traversal_cannot_escape_landing_dir(tmp_path):
    """远端给 `..\\..\\evil.txt`：落点必须仍在指定目录内"""
    payload = b"pwned"
    raw = _block(_descriptor("..\\..\\evil.txt", len(payload)))
    dest = str(tmp_path / "landing")
    paths, note = rdp_files.materialize(raw, payload, dest)
    assert len(paths) == 1
    assert os.path.dirname(paths[0]) == dest
    assert not (tmp_path / "evil.txt").exists()
    with open(paths[0], "rb") as fh:
        assert fh.read() == payload


# ---------- 落盘与拒绝 ----------

def test_materialize_bytes_identical(tmp_path):
    payload = bytes(range(256)) * 7
    raw = _block(_descriptor("SystemUI.html", len(payload)))
    dest = str(tmp_path / "landing")
    paths, note = rdp_files.materialize(raw, payload, dest)
    assert note == ""
    assert len(paths) == 1
    assert os.path.basename(paths[0]) == "SystemUI.html"
    with open(paths[0], "rb") as fh:
        assert fh.read() == payload


def test_materialize_multiple_items_takes_first_and_says_so(tmp_path):
    raw = _block(_descriptor("a.txt", 1), _descriptor("b.txt", 1))
    paths, note = rdp_files.materialize(raw, b"A", str(tmp_path / "l"))
    assert [os.path.basename(p) for p in paths] == ["a.txt"]
    assert "共 2 个" in note
    assert not (tmp_path / "l" / "b.txt").exists()


def test_directory_refused_and_nothing_written(tmp_path):
    dest = tmp_path / "landing"
    paths, note = rdp_files.materialize(
        _block(_descriptor("photos", attrs=_ATTR_DIRECTORY)), b"", str(dest))
    assert paths == []
    assert "文件夹" in note
    assert not dest.exists()


def test_size_mismatch_refused_no_half_file(tmp_path):
    dest = tmp_path / "landing"
    paths, note = rdp_files.materialize(
        _block(_descriptor("a.bin", 100)), b"only-50-bytes", str(dest))
    assert paths == []
    assert "不符" in note
    assert not dest.exists()


def test_empty_contents_refused(tmp_path):
    paths, note = rdp_files.materialize(
        _block(_descriptor("a.txt", 0)), b"", str(tmp_path / "l"))
    assert paths == []
    assert "FileContents" in note


def test_no_descriptors_refused(tmp_path):
    paths, note = rdp_files.materialize(b"", b"x", str(tmp_path / "l"))
    assert paths == [] and note


def test_oversize_gate_fires_before_reading_bytes(tmp_path):
    """尺寸闸门必须在取字节之前：contents 传 None 也要能拒绝。

    改前（先读满再判上限）这里会先去搬几个 GB 的字节流，界面冻住。
    """
    raw = _block(_descriptor("huge.bin", rdp_files.MAX_BYTES + 1))
    files, refusal = rdp_files.plan(raw)
    assert refusal and "太大" in refusal
    assert files == []          # 拒绝时不给可用计划
    paths, note = rdp_files.materialize(raw, None, str(tmp_path / "l"))
    assert paths == [] and "太大" in note
    assert not (tmp_path / "l").exists()


def test_oversize_gate_respects_custom_cap(tmp_path):
    raw = _block(_descriptor("a.bin", 11))
    paths, note = rdp_files.materialize(raw, b"x" * 11, str(tmp_path / "l"),
                                        max_bytes=10)
    assert paths == [] and "太大" in note


def test_size_unknown_skips_length_check(tmp_path):
    """描述符没带 FD_FILESIZE 时不能拿长度去卡（远端没给大小不是错）"""
    raw = _block(_descriptor("a.txt", 0, flags=_REAL_FLAGS & ~_FD_FILESIZE))
    paths, note = rdp_files.materialize(raw, b"hello", str(tmp_path / "l"))
    assert len(paths) == 1
    with open(paths[0], "rb") as fh:
        assert fh.read() == b"hello"


# ---------- 窗格接线（Windows 专用格式） ----------

win32_only = pytest.mark.skipif(sys.platform != "win32",
                                reason="RDP 虚拟文件是 Windows 剪贴板格式")


class _FakeClipboard:
    def __init__(self, mime):
        self._mime = mime

    def mimeData(self):
        return self._mime


@pytest.fixture
def install_clipboard(monkeypatch, tmp_path):
    """把假剪贴板装上去，并把临时落点收进 tmp_path、清掉应用内共享剪贴板残留"""
    from PyQt6.QtWidgets import QApplication
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("core.pane.SHARED_CLIPBOARD", [])
    monkeypatch.setattr("core.pane.SHARED_CLIPBOARD_ACTION", None)

    def _install(mime):
        monkeypatch.setattr(QApplication, "clipboard",
                            staticmethod(lambda: _FakeClipboard(mime)))
    return _install


def _rdp_mime(payload=b"hello rdp", name="SystemUI.html", **kw):
    from PyQt6.QtCore import QMimeData
    mime = QMimeData()
    mime.setData('application/x-qt-windows-mime;value="FileGroupDescriptorW"',
                 _block(_descriptor(name, len(payload), **kw)))
    mime.setData('application/x-qt-windows-mime;value="FileContents"', payload)
    return mime


def _legacy_paths(mime):
    """改前那三条分支的等价读法（urls / FileNameW / FileName），用作对照组"""
    paths = []
    if mime.hasUrls():
        for u in mime.urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if p and os.path.exists(p):
                    paths.append(p)
    for fmt, enc in (('application/x-qt-windows-mime;value="FileNameW"', "utf-16-le"),
                     ('application/x-qt-windows-mime;value="FileName"', "mbcs")):
        raw = mime.data(fmt)
        if raw:
            for p in bytes(raw).decode(enc, errors="replace").split("\x00"):
                p = p.strip()
                if p and os.path.exists(p):
                    paths.append(p)
    return paths


@win32_only
def test_paste_reads_rdp_virtual_file_where_legacy_read_got_nothing(
        qapp, install_clipboard, tmp_path):
    """改前/改后对照：同一份剪贴板，旧读法空手，新读法拿到字节一致的本地文件"""
    from core.pane import Pane
    payload = b"<html>cross-rdp</html>"
    mime = _rdp_mime(payload)
    install_clipboard(mime)

    assert _legacy_paths(mime) == []          # 改前：粘贴静默无内容

    bare = Pane.__new__(Pane)
    paths, is_move = bare._system_clipboard_paths()
    assert len(paths) == 1
    assert is_move is False
    with open(paths[0], "rb") as fh:
        assert fh.read() == payload
    landing = bare._rdp_landing
    assert landing and os.path.isdir(landing)

    bare._clear_rdp_landing()
    assert not os.path.exists(landing)
    assert bare._rdp_landing is None


@win32_only
def test_rdp_cut_is_treated_as_copy_even_if_dropeffect_says_move(qapp, install_clipboard):
    """远端剪切/复制分不出来时一律复制：猜「移动」会去删远端源文件（数据问题）"""
    from core.pane import Pane
    mime = _rdp_mime(b"data")
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"',
                 b'\x02\x00\x00\x00')
    assert Pane._clipboard_prefers_move(mime) is True   # 本机格式确实读得出「移动」
    install_clipboard(mime)
    bare = Pane.__new__(Pane)
    paths, is_move = bare._system_clipboard_paths()
    assert len(paths) == 1
    assert is_move is False
    bare._clear_rdp_landing()


@win32_only
def test_local_file_copy_not_hijacked_by_rdp_branch(qapp, install_clipboard, tmp_path):
    """本机资源管理器复制（有 urls）时不该走虚拟文件分支、不该建临时落点"""
    from core.pane import Pane
    from PyQt6.QtCore import QMimeData, QUrl
    real = tmp_path / "local.txt"
    real.write_bytes(b"local")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(real))])
    install_clipboard(mime)
    bare = Pane.__new__(Pane)
    paths, is_move = bare._system_clipboard_paths()
    assert [os.path.normcase(p) for p in paths] == [os.path.normcase(str(real))]
    assert is_move is False
    # 观测量落在文件系统上：没走虚拟文件分支就不该建临时落点
    assert list(tmp_path.glob("pan4dex-rdp-*")) == []


@win32_only
def test_directory_refusal_reaches_status_bar(qapp, install_clipboard, tmp_path):
    """拒绝要说得出声：改前 `_paste_to` 拿到空列表直接 return，用户只看到没反应"""
    from core.pane import Pane
    install_clipboard(_rdp_mime(b"", name="photos", attrs=_ATTR_DIRECTORY))
    bare = Pane.__new__(Pane)
    said = []
    bare._set_op_status = said.append
    bare._run_file_op_async = lambda *a, **k: pytest.fail("不该起文件操作")
    bare._paste_to(str(tmp_path))
    assert len(said) == 1
    assert "文件夹" in said[0]


@win32_only
def test_empty_clipboard_paste_says_something(qapp, install_clipboard, tmp_path):
    from core.pane import Pane
    from PyQt6.QtCore import QMimeData
    install_clipboard(QMimeData())
    bare = Pane.__new__(Pane)
    said = []
    bare._set_op_status = said.append
    bare._run_file_op_async = lambda *a, **k: pytest.fail("不该起文件操作")
    bare._paste_to(str(tmp_path))
    assert said and "剪贴板" in said[0]


@win32_only
def test_paste_done_clears_landing_on_success_and_failure(tmp_path):
    """成功/失败/取消都经 `_paste_done_dispatch`，临时落点不能留垃圾"""
    from core.pane import Pane

    class _Result:
        def __init__(self, success):
            self.success = success
            self.error = "" if success else "boom"

    for success in (True, False):
        bare = Pane.__new__(Pane)
        landing = tmp_path / ("landing-%s" % success)
        landing.mkdir()
        (landing / "a.txt").write_bytes(b"x")
        bare._rdp_landing = str(landing)
        bare._on_system_paste_done = lambda *a, **k: None
        bare._paste_done_dispatch('system', _Result(success), str(tmp_path),
                                  None, [str(landing / "a.txt")])
        assert not landing.exists()
        assert bare._rdp_landing is None


@win32_only
def test_multi_item_note_surfaces_in_status(qapp, install_clipboard, tmp_path):
    from core.pane import Pane
    from PyQt6.QtCore import QMimeData
    mime = QMimeData()
    mime.setData('application/x-qt-windows-mime;value="FileGroupDescriptorW"',
                 _block(_descriptor("a.txt", 1), _descriptor("b.txt", 1)))
    mime.setData('application/x-qt-windows-mime;value="FileContents"', b"A")
    install_clipboard(mime)
    bare = Pane.__new__(Pane)
    paths, _ = bare._system_clipboard_paths()
    assert len(paths) == 1 and "共 2 个" in bare._clipboard_note

    class _Label:
        def __init__(self):
            self.text = ""

        def setText(self, t):
            self.text = t

    class _Result:
        success = True
        error = ""

    bare.status_label = _Label()
    bare._reload_after_mutation = lambda *a, **k: None
    bare._on_system_paste_done(_Result(), str(tmp_path), 1, None)
    assert "共 2 个" in bare.status_label.text
    bare._clear_rdp_landing()