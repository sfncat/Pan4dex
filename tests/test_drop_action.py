# -*- coding: utf-8 -*-
"""拖放动作的 Qt 侧接线（清单 §2.3 拖拽对齐资源管理器）。

判据矩阵本身在 `test_m2_file_operations.py::TestDropActionRules`，那条不碰 GUI。
这里钉的是窗格有没有真的把 `proposedAction`、修饰键、卷边界喂进决策，以及
「外部同卷拖入终于变成移动」这条用户能直接感知的变化。

落点一律用 `indexAt` 桩返回无效索引（= 空白处，目标就是当前目录）：控件没
`show()` 时 `visualItemRect` 没有几何，真去点某一行会让用例依赖布局（见
`docs/gotchas.md` 第 41 条）。
"""
import json
import os

import pytest
from PyQt6.QtCore import QMimeData, QModelIndex, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent

COPY_MOVE = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction


def _row_index(pane, name):
    """按名字拿列表里那一行的索引（给 `indexAt` 的桩用，不靠几何）

    行是后台枚举完通过队列信号投到主线程的，所以上层要用
    `qtbot.waitUntil` 转事件循环等，只等线程池是不够的。
    """
    tv = pane.tree_view
    proxy = tv.model()
    root = tv.rootIndex()
    for r in range(proxy.rowCount(root)):
        if proxy.data(proxy.index(r, 0, root)) == name:
            return proxy.index(r, 0, root)
    return QModelIndex()


def drop_event(mime, proposed=Qt.DropAction.CopyAction, mods=Qt.KeyboardModifier.NoModifier,
               possible=COPY_MOVE):
    """造一个落点事件。

    `QDropEvent` 的构造参数是**单个** `Qt.DropAction`（传复合值会被坑回
    CopyAction），而「源端允许哪几种」是 `possibleActions()`：那个在 C++ 里由
    `QDragManager` 填、构造不出来，所以用实例属性遮蔽这个方法来注入（Python
    的属性查找优先于类型上的方法）。
    """
    evt = QDropEvent(QPointF(2, 2), proposed, mime,
                     Qt.MouseButton.LeftButton, mods)
    # `QDropEvent` 不接管 `QMimeData` 的生命周期（正常拖拽里它由 `QDrag` 持有）：
    # 直接把临时 mime 传进去会当场悬空，下一次 `mimeData()` 就是 access violation
    evt._mime = mime
    evt.possibleActions = lambda: possible
    return evt


def url_mime(paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return mime


def internal_mime(pane_id, paths):
    """我们自己的拖拽负载（只带源窗格与文件，动作由接收端算）"""
    mime = QMimeData()
    mime.setData("application/x-pan4dex-drag",
                 json.dumps({"source_pane_id": pane_id, "files": paths}).encode())
    return mime


@pytest.fixture
def pane(qtbot, tmp_path):
    """一个停在 tmp_path 的窗格，外加一个「隔壁目录」当作外部拖入的源"""
    from core.pane import Pane

    outside = tmp_path / "outside"
    outside.mkdir()
    src = outside / "a.txt"
    src.write_text("x")

    p = Pane("t_drop", start_path=str(tmp_path))
    qtbot.addWidget(p)
    # 落点＝空白处：目标是当前目录，且不依赖视图几何
    p.tree_view.indexAt = lambda pos: QModelIndex()

    calls = []
    p._run_file_op_async = lambda note, fn, done=None: calls.append(note)
    p._other_pane_id = "t_other"
    yield p, str(src), str(tmp_path), calls
    p.deleteLater()


def test_external_drag_on_the_same_volume_moves(pane):
    """旧实现外部拖入一律复制；同一个盘里从资源管理器拖文件过去是移动"""
    p, src, _target, calls = pane
    p.dropEvent(drop_event(url_mime([src])))
    assert calls == ["正在移动"]


def test_cross_volume_external_drag_copies(pane, monkeypatch):
    from core import pane as pane_mod
    p, src, _target, calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)
    p.dropEvent(drop_event(url_mime([src])))
    assert calls == ["正在复制"]


def test_control_forces_copy_even_on_the_same_volume(pane):
    p, src, _target, calls = pane
    p.dropEvent(drop_event(url_mime([src]),
                           mods=Qt.KeyboardModifier.ControlModifier))
    assert calls == ["正在复制"]


def test_shift_forces_move_even_cross_volume(pane, monkeypatch):
    from core import pane as pane_mod
    p, src, _target, calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)
    p.dropEvent(drop_event(url_mime([src]),
                           mods=Qt.KeyboardModifier.ShiftModifier))
    assert calls == ["正在移动"]


def test_a_source_that_only_offers_copy_is_not_moved(pane):
    """源端只给 COPY 时按移动做等于删掉人家的源文件（卷判断不能翻盘这条）"""
    p, src, _target, calls = pane
    p.dropEvent(drop_event(url_mime([src]),
                           possible=Qt.DropAction.CopyAction))
    assert calls == ["正在复制"]


def test_a_source_that_only_offers_move_is_moved(pane, monkeypatch):
    from core import pane as pane_mod
    p, src, _target, calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)
    p.dropEvent(drop_event(url_mime([src]),
                           possible=Qt.DropAction.MoveAction))
    assert calls == ["正在移动"]


def test_an_external_source_that_only_fills_proposed_action_is_understood(pane, monkeypatch):
    """有些外部源不填 possibleActions（只给 proposed）：退一步拿它当约束"""
    from core import pane as pane_mod
    p, src, _target, calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)
    p.dropEvent(drop_event(url_mime([src]),
                           proposed=Qt.DropAction.MoveAction,
                           possible=Qt.DropAction.IgnoreAction))
    assert calls == ["正在移动"]
    calls.clear()
    p.dropEvent(drop_event(url_mime([src]),
                           proposed=Qt.DropAction.IgnoreAction,
                           possible=Qt.DropAction.IgnoreAction))
    assert calls == ["正在复制"]              # 两边都没信息 → 复制兜底


def test_the_allowed_set_beats_the_suggested_single_action(pane):
    """两个信号矛盾时听「允许集合」：它说不许 move 就不能 move"""
    p, src, _target, calls = pane
    p.dropEvent(drop_event(url_mime([src]),
                           proposed=Qt.DropAction.MoveAction,
                           possible=Qt.DropAction.CopyAction))
    assert calls == ["正在复制"]


def test_dropping_the_same_panes_files_back_onto_its_own_folder_does_nothing(pane):
    """同窗格拖到空白处（落回自己所在目录）：什么都不做，不能弹同名冲突框"""
    p, _src, target, calls = pane
    inside = target + "/b.txt"
    with open(inside, "w") as fh:
        fh.write("y")

    p.dropEvent(drop_event(internal_mime(p.pane_id, [inside])))
    assert calls == []


def test_an_external_drop_back_onto_its_own_folder_does_nothing(pane):
    """外部拖入的源就在当前目录、落点也是当前目录：无操作（不能原地复制一份）"""
    p, _src, target, calls = pane
    inside = os.path.join(target, "c.txt")
    with open(inside, "w") as fh:
        fh.write("z")

    p.dropEvent(drop_event(url_mime([inside])))
    assert calls == []


def test_a_same_pane_drag_to_another_folder_moves_even_if_the_volume_is_unknown(qtbot, pane,
                                                                                monkeypatch):
    """同窗格拖到别的目录行：总是移动，连卷判断说不确定都不能改它

    （没这个分支的话，“同窗格拖动”会退化成靠 `same_volume`，而拖的是当前
    目录里的文件、目标也在当前目录树里，本来就不可能跨卷）
    """
    from core import pane as pane_mod
    p, _src, target, calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)

    inside = os.path.join(target, "d.txt")
    with open(inside, "w") as fh:
        fh.write("w")
    idx = QModelIndex()

    def _ready():
        nonlocal idx
        idx = _row_index(p, "outside")            # 拖到「outside」这个目录行上
        return idx.isValid()

    qtbot.waitUntil(_ready, timeout=5000)
    p.tree_view.indexAt = lambda pos: idx

    p.dropEvent(drop_event(internal_mime(p.pane_id, [inside])))
    assert calls == ["正在移动"]


def test_an_external_style_drag_inside_the_same_folder_moves_even_if_volume_is_unknown(qtbot,
                                                                                      pane,
                                                                                      monkeypatch):
    """urls 分支的同目录树内拖动（外部应用拖回同一个盘）：总是移动

    与上一条的差别只在走哪条通道：窗格自己的拖拽走 `pan4dex-drag`，
    外部应用（以及只带 urls 的兼容通道）走 urls。两个入口对同一件事
    必须给同一个答案。
    """
    from core import pane as pane_mod
    p, _src, target, calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)

    inside = os.path.join(target, "e.txt")
    with open(inside, "w") as fh:
        fh.write("v")
    idx = QModelIndex()

    def _ready():
        nonlocal idx
        idx = _row_index(p, "outside")
        return idx.isValid()

    qtbot.waitUntil(_ready, timeout=5000)
    p.tree_view.indexAt = lambda pos: idx

    p.dropEvent(drop_event(url_mime([inside])))
    assert calls == ["正在移动"]


def test_cross_pane_drag_follows_the_volume_rule(pane, monkeypatch):
    from core import pane as pane_mod
    p, src, _target, calls = pane
    p.dropEvent(drop_event(internal_mime(p._other_pane_id, [src])))
    assert calls == ["正在移动"]             # 同卷 → 移动
    calls.clear()
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)
    p.dropEvent(drop_event(internal_mime(p._other_pane_id, [src])))
    assert calls == ["正在复制"]             # 跨卷 → 复制


def test_drop_action_is_returned_not_written_back(pane, monkeypatch):
    """`_drop_action` 只把动作返回给调用方（窗格自己拿它决定跑 copy 还是 move）"""
    from core import pane as pane_mod
    p, src, _target, _calls = pane
    monkeypatch.setattr(pane_mod, "same_volume", lambda files, dst: False)

    evt = drop_event(url_mime([src]))
    assert p._drop_action([src], p.current_path, evt, same_dir_drag=False) == "copy"
    evt = drop_event(url_mime([src]))
    assert p._drop_action([src], p.current_path, evt, same_dir_drag=True) == "move"


def test_set_drop_action_does_not_stick_in_pyqt6():
    """PyQt6 实测：`QDropEvent.setDropAction()` 是**空操作**

    写进去再读回来永远是构造时那个值。所以不要指望“把我们的选择回写给源端”
    这种做法（旧版这里真写了那两行，静默无效）；动作靠 `_drop_action` 的
    返回值传出去。这条用例钉住结论，免得谁再把那两行加回来。
    """
    evt = drop_event(url_mime([r"C:\x\a.txt"]), proposed=Qt.DropAction.CopyAction)
    evt.setDropAction(Qt.DropAction.MoveAction)
    assert evt.dropAction() == Qt.DropAction.CopyAction

    evt = drop_event(url_mime([r"C:\x\a.txt"]), proposed=Qt.DropAction.MoveAction)
    evt.setDropAction(Qt.DropAction.CopyAction)
    assert evt.dropAction() == Qt.DropAction.MoveAction
