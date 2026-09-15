"""
Pan4dex 万格 — 路径栏组件
"""
import logging
import sys
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QWidget,
    QHBoxLayout, QPushButton, QToolButton, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QSize, QRectF, QPointF, QStringListModel

logger = logging.getLogger("pan4dex.path_bar")


def _make_terminal_icon(size: int = 20) -> QIcon:
    """绘制终端图标（圆角窗口 + >_ 提示符），替代 SP_CommandLink（形似前进箭头）。

    size 为逻辑像素，按 2x 渲染保证高分屏清晰。
    """
    dpr = 2
    px = QPixmap(size * dpr, size * dpr)
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(1.5, 1.5, size - 3.0, size - 3.0)
    # 终端窗口主体
    p.setPen(QPen(QColor(190, 205, 225), 1.3))
    p.setBrush(QColor(42, 48, 60))
    p.drawRoundedRect(rect, 3.5, 3.5)
    # 提示符 >_
    p.setPen(QColor(235, 240, 248))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(max(10, int(size * 0.58)))
    p.setFont(f)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ">_")
    p.end()
    return QIcon(px)


def _make_up_icon(size: int = 20) -> QIcon:
    """绘制浅色「上级目录」箭头图标。

    Windows 深色主题下 SP_ArrowUp / SP_FileDialogToParent 渲染出的都是
    黑色箭头（深色按钮上近乎黑块，观感差），自绘浅灰圆角箭头替代。
    size 为逻辑像素，按 2x 渲染保证高分屏清晰。
    """
    dpr = 2
    px = QPixmap(size * dpr, size * dpr)
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(210, 216, 226)  # 浅灰，深色主题下清晰可见
    cx = size / 2.0
    # 竖线
    pen = QPen(color, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(cx, size * 0.80), QPointF(cx, size * 0.44))
    # 箭头头部（实心三角）
    tri = QPolygonF([
        QPointF(cx - size * 0.30, size * 0.44),
        QPointF(cx + size * 0.30, size * 0.44),
        QPointF(cx, size * 0.16),
    ])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPolygon(tri)
    p.end()
    return QIcon(px)


class PathBar(QWidget):
    """路径栏组件"""
    
    # 类级别的共享 completer 模型（所有 PathBar 实例共享）
    _shared_completer_model = None
    
    # 信号
    path_entered = pyqtSignal(str)  # 路径输入信号
    back_requested = pyqtSignal()   # 后退按钮点击信号
    forward_requested = pyqtSignal()  # 前进按钮点击信号
    refresh_requested = pyqtSignal()  # 刷新按钮点击信号
    tree_toggle_requested = pyqtSignal()  # 目录树按钮点击信号
    tabs_toggle_requested = pyqtSignal()  # 标签页按钮点击信号
    terminal_requested = pyqtSignal()  # 终端按钮点击信号
    view_mode_requested = pyqtSignal(str)  # 查看模式切换信号 ('icon' / 'list')
    new_folder_requested = pyqtSignal()  # 新建文件夹按钮点击信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        
        # 后退/前进：接入导航历史（旧版创建了按钮但未连任何信号、默认隐藏，
        # 导致后退只有鼠标侧键能用）；能否导航由 set_nav_enabled 同步置灰
        self.back_btn = QToolButton()
        self.back_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.back_btn.setIconSize(QSize(20, 20))
        self.back_btn.setToolTip("后退 (Alt+Left)")
        self.back_btn.setFixedSize(28, 28)
        self.back_btn.setEnabled(False)
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.layout.addWidget(self.back_btn)

        self.forward_btn = QToolButton()
        self.forward_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.forward_btn.setIconSize(QSize(20, 20))
        self.forward_btn.setToolTip("前进 (Alt+Right)")
        self.forward_btn.setFixedSize(28, 28)
        self.forward_btn.setEnabled(False)
        self.forward_btn.clicked.connect(self.forward_requested.emit)
        self.layout.addWidget(self.forward_btn)

        # 上级目录按钮
        self.up_btn = QToolButton()
        if sys.platform == "win32":
            # Windows 深色主题下 SP_ArrowUp/SP_FileDialogToParent 均为黑色
            # 箭头（按钮上近乎黑块），自绘浅色箭头图标
            self.up_btn.setIcon(_make_up_icon(20))
        else:
            self.up_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.up_btn.setIconSize(QSize(20, 20))
        self.up_btn.setToolTip("上级目录")
        self.up_btn.setFixedSize(28, 28)
        self.up_btn.clicked.connect(self.go_up)
        self.layout.addWidget(self.up_btn)

        # 刷新按钮（重扫当前目录，网络路径下强制刷新）
        self.refresh_btn = QToolButton()
        self.refresh_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_btn.setIconSize(QSize(20, 20))
        self.refresh_btn.setToolTip("刷新 (F5)")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.layout.addWidget(self.refresh_btn)

        # 目录树按钮
        self.tree_btn = QToolButton()
        self.tree_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.tree_btn.setIconSize(QSize(20, 20))
        self.tree_btn.setToolTip("目录树")
        self.tree_btn.setFixedSize(28, 28)
        self.tree_btn.setCheckable(True)
        self.tree_btn.clicked.connect(self.on_tree_clicked)
        self.layout.addWidget(self.tree_btn)

        # 标签页按钮
        self.tabs_btn = QToolButton()
        self.tabs_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.tabs_btn.setIconSize(QSize(20, 20))
        self.tabs_btn.setToolTip("标签页")
        self.tabs_btn.setFixedSize(28, 28)
        self.tabs_btn.setCheckable(True)
        self.tabs_btn.clicked.connect(self.on_tabs_clicked)
        self.layout.addWidget(self.tabs_btn)

        # 查看模式按钮（图标/超大图标/列表循环切换）
        self.view_btn = QToolButton()
        self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.view_btn.setIconSize(QSize(20, 20))
        self.view_btn.setToolTip("查看模式：图标 → 超大图标 → 列表")
        self.view_btn.setFixedSize(28, 28)
        self.view_btn.setCheckable(False)
        self._view_mode = 'icon'  # icon / xlarge / list
        self.view_btn.clicked.connect(self.on_view_clicked)
        self.layout.addWidget(self.view_btn)

        # 新建文件夹按钮（用标准文件夹图标）
        self.new_folder_btn = QToolButton()
        self.new_folder_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        )
        self.new_folder_btn.setIconSize(QSize(20, 20))
        self.new_folder_btn.setToolTip("新建文件夹")
        self.new_folder_btn.setFixedSize(28, 28)
        self.new_folder_btn.clicked.connect(self.on_new_folder_clicked)
        self.layout.addWidget(self.new_folder_btn)

        # 终端按钮（自绘终端图标，避免 SP_CommandLink 形似前进箭头）
        self.terminal_btn = QToolButton()
        self.terminal_btn.setIcon(_make_terminal_icon())
        self.terminal_btn.setIconSize(QSize(20, 20))
        self.terminal_btn.setToolTip("打开终端")
        self.terminal_btn.setFixedSize(28, 28)
        self.terminal_btn.clicked.connect(self.on_terminal_clicked)
        self.layout.addWidget(self.terminal_btn)
        
        # 路径输入框
        self.combo_box = QComboBox()
        self.combo_box.setEditable(True)
        self.combo_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_box.setMinimumHeight(28)

        # 设置自动补全（共享模型）
        self._setup_shared_completer()

        # 信号
        self.combo_box.lineEdit().returnPressed.connect(self.on_return_pressed)
        self.combo_box.activated.connect(self.on_item_activated)
        
        self.layout.addWidget(self.combo_box)
        
        # 设置样式

    
    def _setup_shared_completer(self):
        """设置路径补全模型。

        旧实现用共享 `QFileSystemModel().setRootPath("")` 作为补全模型：
        root="" 会触发后台线程递归枚举所有盘符/网络共享，本地冷盘与
        SMB 上都会引起明显卡顿。改为基于当前目录的非递归子项列表
        （QStringListModel），导航时只列当前目录一层，零全盘扫描。
        """
        self._completer_model = QStringListModel(self)
        self.completer = QCompleter()
        self.completer.setModel(self._completer_model)
        self.completer.setModelSorting(QCompleter.ModelSorting.UnsortedModel)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setMaxVisibleItems(20)
        self.combo_box.setCompleter(self.completer)

    def _refresh_completions(self, path: str):
        """把补全候选刷新为 path 下的一层子项完整路径（非递归，不展开子目录）"""
        try:
            d = QDir(path)
            if not d.exists():
                self._completer_model.setStringList([])
                return
            filters = (QDir.Filter.AllDirs | QDir.Filter.Files |
                       QDir.Filter.NoDotAndDotDot)
            entries = d.entryList(filters, QDir.SortFlag.Name)
            sep = '/'
            base = d.absolutePath().rstrip(sep)
            self._completer_model.setStringList([base + sep + e for e in entries])
        except Exception:
            pass
    
    
    def set_path(self, path: str):
        """设置路径"""
        self.combo_box.setEditText(path)
        # 刷新当前目录一层子项作为补全候选（非递归，零全盘扫描）
        self._refresh_completions(path)
        # 添加到历史
        if self.combo_box.findText(path) == -1:
            self.combo_box.addItem(path)
    
    def get_path(self) -> str:
        """获取当前路径"""
        return self.combo_box.currentText()
    
    def on_return_pressed(self):
        """回车处理"""
        path = self.combo_box.currentText().strip()
        if path:
            self.path_entered.emit(path)
    
    def on_item_activated(self, index):
        """下拉项激活"""
        path = self.combo_box.itemText(index)
        if path:
            self.path_entered.emit(path)
    
    def set_nav_enabled(self, can_back: bool, can_forward: bool):
        """按导航历史同步后退/前进按钮可用态"""
        self.back_btn.setEnabled(can_back)
        self.forward_btn.setEnabled(can_forward)

    def focus_for_input(self):
        """Ctrl+L：聚焦路径输入框并全选现有路径

        全选而不是光标置末：资源管理器的习惯是按一下就能直接打新路径，
        不必先手动删掉旧的。
        """
        line = self.combo_box.lineEdit()
        if line is None:                # 不可编辑时会返回 None
            self.combo_box.setFocus()
            return
        line.setFocus()
        line.selectAll()

    def go_up(self):
        """返回上级目录"""
        import os
        current = self.combo_box.currentText()
        parent = os.path.dirname(current)
        if parent and parent != current:
            self.path_entered.emit(parent)

    def on_tree_clicked(self):
        """目录树按钮点击"""
        self.tree_toggle_requested.emit()

    def on_tabs_clicked(self):
        """标签页按钮点击"""
        logger.info(f"[TABS] PathBar.on_tabs_clicked emitting tabs_toggle_requested")
        self.tabs_toggle_requested.emit()

    def on_view_clicked(self):
        """查看模式按钮点击：循环图标 → 超大图标 → 列表"""
        modes = ['icon', 'xlarge', 'list']
        idx = modes.index(self._view_mode)
        self._view_mode = modes[(idx + 1) % len(modes)]
        logger.info(f"[DEBUG] PathBar.on_view_clicked: emitting view_mode_requested with mode={self._view_mode}")
        self.view_mode_requested.emit(self._view_mode)
        
        if self._view_mode == 'icon':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
            self.view_btn.setToolTip("当前：图标，点击切换超大图标")
        elif self._view_mode == 'xlarge':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
            self.view_btn.setToolTip("当前：超大图标（图片预览），点击切换列表")
        else:
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
            self.view_btn.setToolTip("当前：列表，点击切换图标")

    def on_new_folder_clicked(self):
        """新建文件夹按钮点击"""
        self.new_folder_requested.emit()

    def on_terminal_clicked(self):
        """终端按钮点击"""
        self.terminal_requested.emit()

    def set_tree_button_checked(self, checked: bool):
        """设置目录树按钮状态"""
        self.tree_btn.setChecked(checked)

    def set_tabs_button_checked(self, checked: bool):
        """设置标签页按钮状态"""
        self.tabs_btn.setChecked(checked)

    def set_view_mode(self, mode: str):
        """设置查看模式（更新按钮状态）"""
        self._view_mode = mode
        if mode == 'icon':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
            self.view_btn.setToolTip("当前：图标，点击切换超大图标")
        elif mode == 'xlarge':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
            self.view_btn.setToolTip("当前：超大图标（图片预览），点击切换列表")
        elif mode == 'list':
            self.view_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
            self.view_btn.setToolTip("当前：列表，点击切换图标")

    def set_button_visibility(self, button_name: str, visible: bool):
        """设置工具栏按钮可见性"""
        btn_map = {
            'back': self.back_btn,
            'forward': self.forward_btn,
            'up': self.up_btn,
            'refresh': self.refresh_btn,
            'tree': self.tree_btn,
            'tabs': self.tabs_btn,
            'view': self.view_btn,
            'new_folder': self.new_folder_btn,
            'terminal': self.terminal_btn,
        }
        btn = btn_map.get(button_name)
        if btn:
            btn.setVisible(visible)
