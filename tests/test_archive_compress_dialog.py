import os
import tarfile
import zipfile

import pytest
from PyQt6.QtWidgets import QDialog

from core import archive_ops


@pytest.fixture
def pane(qtbot, tmp_path):
    from core.pane import Pane

    p = Pane("t_archive_name", start_path=str(tmp_path))
    qtbot.addWidget(p)
    return p


def _choose_format(monkeypatch, suffix=".7z", name=None, accepted=True):
    from widgets.archive_tool import CompressArchiveDialog

    captured = {}

    def fake_exec(dialog):
        captured["dialog"] = dialog
        if not accepted:
            return QDialog.DialogCode.Rejected
        if name is not None:
            dialog.name_edit.setText(name)
        index = dialog.format_combo.findData(suffix)
        assert index >= 0
        dialog.format_combo.setCurrentIndex(index)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CompressArchiveDialog, "exec", fake_exec)
    return captured


def _capture_compress(monkeypatch):
    calls = []
    monkeypatch.setattr(
        archive_ops, "compress",
        lambda output, items: calls.append((output, items)) or (True, output))
    return calls


def test_single_file_uses_its_name_without_typing(pane, tmp_path, monkeypatch):
    source = tmp_path / "report.txt"
    source.write_text("report", encoding="utf-8")
    chosen = _choose_format(monkeypatch, ".zip")
    calls = _capture_compress(monkeypatch)
    monkeypatch.setattr(pane, "_run_archive_task", lambda note, fn: fn())

    pane.compress_paths([str(source)])

    assert chosen["dialog"].name_edit.text() == "report.txt"
    assert calls == [(str(tmp_path / "report.txt.zip"), [str(source)])]


def test_directory_with_trailing_separator_uses_directory_name(pane, tmp_path, monkeypatch):
    source = tmp_path / "project"
    source.mkdir()
    chosen = _choose_format(monkeypatch, ".tar.gz")
    calls = _capture_compress(monkeypatch)
    monkeypatch.setattr(pane, "_run_archive_task", lambda note, fn: fn())

    pane.compress_paths([str(source) + os.sep])

    assert chosen["dialog"].name_edit.text() == "project"
    assert calls == [(str(tmp_path / "project.tar.gz"), [str(source) + os.sep])]


def test_multiple_items_default_to_archive_in_current_directory(pane, tmp_path, monkeypatch):
    sources = []
    for name in ("a.txt", "b.txt"):
        source = tmp_path / name
        source.write_text(name, encoding="utf-8")
        sources.append(str(source))
    chosen = _choose_format(monkeypatch, ".tar.xz")
    calls = _capture_compress(monkeypatch)
    monkeypatch.setattr(pane, "_run_archive_task", lambda note, fn: fn())

    pane.compress_paths(sources)

    assert chosen["dialog"].name_edit.text() == "archive"
    assert calls == [(str(tmp_path / "archive.tar.xz"), sources)]


def test_format_change_updates_default_output_name(qtbot, tmp_path):
    from widgets.archive_tool import CompressArchiveDialog

    dialog = CompressArchiveDialog(str(tmp_path), "report.txt")
    qtbot.addWidget(dialog)
    assert dialog.output_path == str(tmp_path / "report.txt.7z")

    for suffix in (".zip", ".tar.gz", ".tar.xz", ".tar.bz2", ".tar"):
        index = dialog.format_combo.findData(suffix)
        dialog.format_combo.setCurrentIndex(index)
        assert dialog.output_path == str(tmp_path / ("report.txt" + suffix))


def test_custom_name_remains_optional(qtbot, tmp_path):
    from widgets.archive_tool import CompressArchiveDialog

    dialog = CompressArchiveDialog(str(tmp_path), "report.txt")
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("custom")
    dialog.format_combo.setCurrentIndex(dialog.format_combo.findData(".tar.gz"))

    assert dialog.output_path == str(tmp_path / "custom.tar.gz")


def test_cancel_does_not_start_compression(pane, tmp_path, monkeypatch):
    source = tmp_path / "a.txt"
    source.write_text("a", encoding="utf-8")
    _choose_format(monkeypatch, accepted=False)
    calls = _capture_compress(monkeypatch)

    pane.compress_paths([str(source)])

    assert calls == []


@pytest.mark.parametrize("suffix", [".zip", ".tar", ".tar.gz", ".tar.bz2", ".tar.xz"])
def test_selected_format_creates_a_readable_archive(tmp_path, suffix):
    source = tmp_path / "sample.txt"
    source.write_text("format test", encoding="utf-8")
    output = tmp_path / ("sample.txt" + suffix)

    ok, message = archive_ops.compress(str(output), [str(source)])

    assert ok, message
    assert output.is_file()
    if suffix == ".zip":
        with zipfile.ZipFile(output) as archive:
            assert archive.read("sample.txt") == b"format test"
    else:
        mode = {
            ".tar": "r:",
            ".tar.gz": "r:gz",
            ".tar.bz2": "r:bz2",
            ".tar.xz": "r:xz",
        }[suffix]
        with tarfile.open(output, mode) as archive:
            member = archive.getmember("sample.txt")
            assert archive.extractfile(member).read() == b"format test"


def test_selected_format_preserves_directory_structure(tmp_path):
    source = tmp_path / "project"
    (source / "nested").mkdir(parents=True)
    (source / "a.txt").write_text("a", encoding="utf-8")
    (source / "nested" / "b.txt").write_text("b", encoding="utf-8")
    output = tmp_path / "project.tar.gz"

    ok, message = archive_ops.compress(str(output), [str(source)])

    assert ok, message
    with tarfile.open(output, "r:gz") as archive:
        assert set(archive.getnames()) == {
            "project", "project/nested", "project/a.txt", "project/nested/b.txt"}
