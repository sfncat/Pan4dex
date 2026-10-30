# -*- coding: utf-8 -*-
"""超大图标视图拖拽：多选拖出的负载与列表视图一致，图标视图也能作为落点。"""
import json
import os

from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QAbstractItemView

COPY_MOVE = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction


def _internal_mime(pane_id, paths):
    mime = QMimeData()
    mime.setData("application/x-pan4dex-drag",
                 json.dumps({"source_pane_id": pane_id, "files": paths}).encode())
    return mime


def _drop_event(mime):
    evt = QDropEvent(QPointF(2, 2), Qt.DropAction.CopyAction, mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    # QDropEvent 不接管 QMimeData 的生命周期，留着引用防悬空
    evt._mime = mime
    evt.possibleActions = lambda: COPY_MOVE
    return evt


def _pane(qtbot, tmp_path, pane_id="t_icon"):
    from core.pane import Pane

    p = Pane(pane_id, start_path=str(tmp_path))
    qtbot.addWidget(p)
    return p


def test_icon_view_keeps_extended_selection_with_drag_enabled(qtbot):
    """setDragDropMode 会把选择模式改回单选，必须在其后恢复多选"""
    from widgets.thumbnail_view import ThumbnailView

    view = ThumbnailView()
    qtbot.addWidget(view)
    assert view.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    assert view.dragEnabled() is True
    assert view.acceptDrops() is True


def test_drag_payload_contains_every_selected_item(qtbot, tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("a")
    b = tmp_path / "b.txt"
    b.write_text("b")
    p = _pane(qtbot, tmp_path)
    view = p.thumbnail_view
    view.load_directory(str(tmp_path))
    for row in range(view.count()):
        view.item(row).setSelected(True)

    mime = view._drag_mime_data()
    payload = json.loads(mime.data("application/x-pan4dex-drag").data().decode())
    assert payload["source_pane_id"] == "t_icon"
    assert sorted(payload["files"]) == sorted([str(a), str(b)])
    assert {os.path.normpath(u.toLocalFile()) for u in mime.urls()} == {
        os.path.normpath(p) for p in payload["files"]}


def test_drop_on_a_folder_icon_targets_that_folder(qtbot, tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    src = src_dir / "x.txt"
    src.write_text("x")

    p = _pane(qtbot, tmp_path, "t_icon2")
    view = p.thumbnail_view
    view.load_directory(str(tmp_path))
    index = view.indexFromItem(view._item_map[str(dst_dir)])
    assert index.isValid()
    view.indexAt = lambda pos: index  # 落点不依赖视图几何

    calls = []
    monkeypatch.setattr(p, "_run_file_op_async",
                        lambda note, fn, done=None: (calls.append(note), fn()))
    monkeypatch.setattr(p.file_ops, "move",
                        lambda files, target: calls.append((files, target)))

    p.dropEvent(_drop_event(_internal_mime("t_other", [str(src)])), view=view)

    assert calls[0] == "正在移动"
    assert calls[1] == ([str(src)], str(dst_dir))