# -*- coding: utf-8 -*-
"""视图内「跳到首/末条」的共用键位处理。

详情视图（`core/pane.FileListTreeView`）与缩略图/平铺/简单列表
（`widgets/thumbnail_view.ThumbnailView`）共用这一份，避免写成两套。
"""
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QAbstractItemView


def handle_edge_jump(view, event) -> bool:
    """Ctrl+End / Ctrl+Home：光标、滚动、选中一起到末/首条；命中并处理返回 True。

    Qt 默认把带 Ctrl 的移动当成「只动光标、不动选中」（内部用 NoUpdate 设当前索引），
    而资源管理器的习惯是选中跟着走 —— 否则跳到底后按 Delete/Ctrl+C 作用的仍是跳之前
    选中的那批文件。普通 End/Home 与 Shift 组合不在此拦截，仍走 Qt 默认。
    """
    mods = event.modifiers()
    if not (mods & Qt.KeyboardModifier.ControlModifier):
        return False
    if mods & Qt.KeyboardModifier.ShiftModifier:
        return False        # Ctrl+Shift+End 是「选到末尾」，语义不同，交给 Qt
    to_end = event.key() == Qt.Key.Key_End
    if not to_end and event.key() != Qt.Key.Key_Home:
        return False
    model = view.model()
    if model is None:
        return False
    root = view.rootIndex()
    rows = model.rowCount(root)
    if rows <= 0:
        return False
    row = rows - 1 if to_end else 0
    idx = model.index(row, 0, root)
    if not idx.isValid():
        return False
    # 整行选中（详情视图 SelectRows 下只选第 0 格会只亮一格）；用 Rows 标志展开，
    # 不去问 columnCount —— PyQt6 把 QAbstractListModel.columnCount 标成私有方法
    view.setCurrentIndex(idx)
    view.selectionModel().select(
        idx,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows)
    view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
    event.accept()
    return True