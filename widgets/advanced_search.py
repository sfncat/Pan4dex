"""
Pan4dex 万格 — 高级搜索工具

匹配语义与列表筛选栏保持一套（见 `widgets/filter_bar.py`）：通配符整名匹配、
普通字符串是名称包含、正则走 `search`。搜索条件可存为「已保存的搜索」
（`config/saved_searches.py`，清单 20.4），存的是**真正喂给 worker 的那份 params**。

结果列表（清单 20.3）可多选后右键/按键批量打开、复制、移动、删除；搬文件的
后台执行不在这儿写第二份，用 `core/file_op_runner.FileOpRunner`（窗格同一个）。
"""
import logging
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QComboBox, QCheckBox, QSpinBox, QGroupBox,
    QFileDialog, QMessageBox, QInputDialog, QMenu, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from widgets.filter_bar import glob_to_regex
from core.file_op_runner import FileOpRunner
from core.file_operations import describe_removal, move_target_inside_sources

logger = logging.getLogger("pan4dex.advanced_search")


def build_name_matcher(pattern: str, use_regex: bool, case_sensitive: bool):
    """文件名模式 → `bool(name)` 判定函数（编译一次，不在遍历循环里重编）

    - 正则：对名字 `search`（局部匹配，与旧行为一致）
    - 含 `*` / `?` 且未勾正则：整名通配匹配（`*.txt` 就是“扩展名是 txt”）
    - 其他：名称包含

    旧实现把非正则一律 `re.escape` 后 `search`，于是界面上教的 `*.txt` 被当成
    “名字里含字面 `*.txt`”——按 placeholder 写必然 0 结果（修于 v1.9.009）。
    """
    pat = (pattern or "").strip()
    flags = 0 if case_sensitive else re.IGNORECASE
    if use_regex:
        rx = re.compile(pat, flags)
        return lambda name: bool(rx.search(name)), rx.pattern
    if "*" in pat or "?" in pat:
        rx = glob_to_regex(pat, flags)
        return lambda name: bool(rx.match(name)), rx.pattern
    if case_sensitive:
        return (lambda name, p=pat: p in name), pat
    low = pat.lower()
    return (lambda name, p=low: p in name.lower()), pat


class SearchWorker(QThread):
    """搜索工作线程"""
    result = pyqtSignal(str, str, int)  # path, size, modified
    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(int)  # total found
    
    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self._stop = False
    
    def run(self):
        found = 0
        search_dir = self.params.get('directory', '')
        pattern = self.params.get('pattern', '')
        use_regex = self.params.get('use_regex', False)
        case_sensitive = self.params.get('case_sensitive', False)
        file_types = self.params.get('file_types', [])
        min_size = self.params.get('min_size', 0)
        max_size = self.params.get('max_size', 0)
        content_search = self.params.get('content', '')
        
        if not search_dir or not os.path.isdir(search_dir):
            self.finished.emit(0)
            return
        
        # 文件名匹配规则（与筛选栏一套）；正则写错直接结束，不带着坏条件去扫盘
        try:
            match_name, _shown = build_name_matcher(pattern, use_regex, case_sensitive)
        except re.error as e:
            logger.warning("搜索正则无效 %r: %s", pattern, e)
            self.finished.emit(0)
            return
        
        for root, dirs, files in os.walk(search_dir):
            if self._stop:
                break
            
            for filename in files:
                if self._stop:
                    break
                
                # 文件名匹配
                if not match_name(filename):
                    continue
                
                filepath = os.path.join(root, filename)
                
                try:
                    stat = os.stat(filepath)
                    size = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    continue
                
                # 大小筛选
                if min_size > 0 and size < min_size:
                    continue
                if max_size > 0 and size > max_size:
                    continue
                
                # 扩展名筛选
                if file_types:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in file_types:
                        continue
                
                # 内容搜索（“区分大小写”对名与内容同一个口径，不另设选项）
                if content_search:
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(1024 * 1024)  # 只读前 1MB
                    except OSError:
                        continue
                    if case_sensitive:
                        if content_search not in content:
                            continue
                    elif content_search.lower() not in content.lower():
                        continue
                
                found += 1
                self.result.emit(filepath, self.format_size(size), mtime)
        
        self.finished.emit(found)
    
    def stop(self):
        self._stop = True
    
    def format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class SearchResultTree(QTreeWidget):
    """结果列表：把用户在结果列表里预期的几个键接上（Enter / Del / Shift+Del / Ctrl+C）

    为什么要拦住 Enter：QDialog 里 Enter 会落到「自动默认按钮」上，这个对话框
    第一个按钮是「保存当前条件…」——不接就等于按 Enter 关掉对话框而不是打开文件。
    按钮动作都发信号给对话框，不在这里长逻辑。
    """

    open_requested = pyqtSignal()
    reveal_folder_requested = pyqtSignal()
    copy_paths_requested = pyqtSignal()
    remove_requested = pyqtSignal(bool)      # 参数：是否永久删除

    def keyPressEvent(self, event):
        mods = event.modifiers()
        ctrl = mods & Qt.KeyboardModifier.ControlModifier
        shift = mods & Qt.KeyboardModifier.ShiftModifier
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ctrl and shift:
                # Ctrl+Shift+Enter：资源管理器里的「打开文件位置」
                self.reveal_folder_requested.emit()
            else:
                self.open_requested.emit()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.remove_requested.emit(bool(shift))
            return
        if event.key() == Qt.Key.Key_C and ctrl:
            self.copy_paths_requested.emit()
            return
        super().keyPressEvent(event)


class AdvancedSearchDialog(QDialog):
    """高级搜索对话框"""

    # 大小单位（与 `size_unit` 下拉的项一一对应）
    _SIZE_MULT = (1024, 1024 * 1024, 1024 * 1024 * 1024)

    def __init__(self, parent=None, store=None, host=None):
        super().__init__(parent)
        
        self.setWindowTitle("高级搜索")
        self.setMinimumSize(700, 500)
        
        self.worker = None
        # 已保存搜索的存储：由主窗口注入（全仓一份，与 file_associations 同做法）；
        # 没注入时惰性建一个（单用这个对话框 / 测试时）
        self._store = store
        # 「打开 / 进入目录」要借主窗口的窗格：打开语义（文件关联、Linux 可执行
        # 文件、xdg-open 回退）只有一份，长在 `Pane.open_file` 里。没注入时取 parent。
        self._host = host
        # 结果列表里的复制/移动/删除走后台线程 + 进度对话框（与窗格同一套）
        self.runner = FileOpRunner(self, on_status=self._set_op_status)
        
        self.init_ui()
        self.reload_saved_names()
    
    def init_ui(self):
        """初始化 UI"""
        self.layout = QVBoxLayout(self)
        
        # 搜索条件
        cond_group = QGroupBox("搜索条件")
        cond_layout = QVBoxLayout(cond_group)
        
        # 已保存的搜索（清单 20.4）：选中即载入全部条件，不自动开搜
        saved_layout = QHBoxLayout()
        saved_layout.addWidget(QLabel("已保存:"))
        self.saved_combo = QComboBox()
        self.saved_combo.setToolTip(
            "选一条之前存下的条件，所有输入框会按它填好（不自动开始搜索）。\n"
            "存的是这组条件的最终值（含大小换算），载入后与原样一致")
        self.saved_combo.activated.connect(self.on_saved_selected)
        saved_layout.addWidget(self.saved_combo)
        
        self.save_saved_btn = QPushButton("保存当前条件…")
        self.save_saved_btn.setToolTip("给当前这组搜索条件起个名字存下来")
        self.save_saved_btn.clicked.connect(self.save_current_search)
        saved_layout.addWidget(self.save_saved_btn)
        
        self.del_saved_btn = QPushButton("删除")
        self.del_saved_btn.setToolTip("删掉下拉里选中的那条已保存搜索")
        self.del_saved_btn.clicked.connect(self.delete_saved_search)
        saved_layout.addWidget(self.del_saved_btn)
        saved_layout.addStretch()
        cond_layout.addLayout(saved_layout)
        
        # 搜索目录
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("搜索目录:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("输入搜索目录路径...")
        dir_layout.addWidget(self.dir_edit)
        
        self.dir_btn = QPushButton("浏览...")
        self.dir_btn.clicked.connect(self.browse_dir)
        dir_layout.addWidget(self.dir_btn)
        cond_layout.addLayout(dir_layout)
        
        # 文件名模式
        pattern_layout = QHBoxLayout()
        pattern_layout.addWidget(QLabel("文件名:"))
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("输入文件名模式，如: *.txt 或 report*")
        pattern_layout.addWidget(self.pattern_edit)
        cond_layout.addLayout(pattern_layout)
        
        # 选项
        opt_layout = QHBoxLayout()
        
        self.regex_check = QCheckBox("正则表达式")
        opt_layout.addWidget(self.regex_check)
        
        self.case_check = QCheckBox("区分大小写")
        opt_layout.addWidget(self.case_check)
        
        opt_layout.addStretch()
        
        cond_layout.addLayout(opt_layout)
        
        # 文件类型
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("文件类型:"))
        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText("扩展名，如: .txt,.py,.md（留空为所有类型）")
        type_layout.addWidget(self.type_edit)
        cond_layout.addLayout(type_layout)
        
        # 大小范围
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("大小范围:"))
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(0, 99999)
        self.min_size_spin.setSpecialValueText("最小")
        size_layout.addWidget(self.min_size_spin)
        size_layout.addWidget(QLabel("-"))
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(0, 99999)
        self.max_size_spin.setSpecialValueText("最大")
        size_layout.addWidget(self.max_size_spin)
        self.size_unit = QComboBox()
        self.size_unit.addItems(["KB", "MB", "GB"])
        size_layout.addWidget(self.size_unit)
        size_layout.addStretch()
        cond_layout.addLayout(size_layout)
        
        # 内容搜索
        content_layout = QHBoxLayout()
        content_layout.addWidget(QLabel("包含内容:"))
        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText("文件内容包含的文本（可选）")
        content_layout.addWidget(self.content_edit)
        cond_layout.addLayout(content_layout)
        
        self.layout.addWidget(cond_group)
        
        # 搜索按钮
        btn_layout = QHBoxLayout()
        self.search_btn = QPushButton("开始搜索")
        self.search_btn.clicked.connect(self.start_search)
        btn_layout.addWidget(self.search_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_search)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        
        btn_layout.addStretch()
        
        self.clear_btn = QPushButton("清除结果")
        self.clear_btn.clicked.connect(self.clear_results)
        btn_layout.addWidget(self.clear_btn)
        
        self.layout.addLayout(btn_layout)
        
        # 结果列表
        result_group = QGroupBox("搜索结果")
        result_layout = QVBoxLayout(result_group)
        
        self.result_tree = SearchResultTree()
        self.result_tree.setHeaderLabels(["文件路径", "大小", "修改时间"])
        # 多选 + 右键菜单（清单 20.3：结果里的批量复制/移动/删除）
        self.result_tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection)
        self.result_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_tree.customContextMenuRequested.connect(self.show_results_menu)
        self.result_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.result_tree.open_requested.connect(self.open_selected)
        self.result_tree.reveal_folder_requested.connect(self.open_containing_folders)
        self.result_tree.copy_paths_requested.connect(self.copy_paths_to_clipboard)
        self.result_tree.remove_requested.connect(self.delete_selected)
        result_layout.addWidget(self.result_tree)

        hint = QLabel("可多选（Ctrl/Shift）后右键或用 Enter 打开、Del 删除、"
                      "Shift+Del 永久删除、Ctrl+C 复制路径；操作只对已显示且选中的行生效")
        hint.setStyleSheet("color: #9AA7B8;")
        result_layout.addWidget(hint)

        # 结果批量缓冲：worker 每个命中都 emit 会触发一次 addTopLevelItem
        # → 布局/重绘风暴（尤其 SMB 遍历命中多时）。改为主线程侧缓冲，
        # 定时器每 150ms 一次性 addTopLevelItems（单趟布局），并设显示上限防卡死。
        self._pending_results = []
        self._shown_count = 0
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(150)
        self._flush_timer.timeout.connect(self._flush_results)
        
        self.layout.addWidget(result_group)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        self.layout.addWidget(self.status_label)
        
        # 关闭
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        self.layout.addWidget(self.close_btn)
        
        # 样式
        self.setStyleSheet("""
            QDialog { background-color: #2D2D2D; color: #CCCCCC; }
            QGroupBox { border: 1px solid #404040; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { color: #CCCCCC; subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLineEdit { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px; }
            QPushButton { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 5px 15px; }
            QPushButton:hover { background-color: #505050; }
            QTreeWidget { background-color: #1E1E1E; color: #CCCCCC; border: none; }
            QTreeWidget::item:hover { background-color: #2A2A2A; }
            QTreeWidget::item:selected { background-color: #2196F3; }
            QCheckBox { color: #CCCCCC; }
            QSpinBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
            QComboBox { background-color: #3D3D3D; color: #CCCCCC; border: 1px solid #505050; border-radius: 3px; padding: 2px 5px; }
        """)
    
    def browse_dir(self):
        """浏览目录"""
        path = QFileDialog.getExistingDirectory(self, "选择搜索目录")
        if path:
            self.dir_edit.setText(path)
    
    def collect_params(self) -> tuple:
        """界面上的条件 → worker params。返回 `(params, 错误文本)`，有错时 params 为 None

        开始搜索与「保存当前条件」共用这一函数，保证存下来的就是真正会执行的
        那份条件（含大小换算、扩展名归一化）。
        """
        directory = self.dir_edit.text().strip()
        pattern = self.pattern_edit.text().strip()

        if not directory:
            return None, "请输入搜索目录"
        if not pattern:
            return None, "请输入搜索模式"
        if not os.path.isdir(directory):
            return None, "目录不存在"

        use_regex = self.regex_check.isChecked()
        case_sensitive = self.case_check.isChecked()
        if use_regex:
            # 正则写错在旧版会“静默找到 0 个”，跟“搜不到”看起来一模一样
            try:
                build_name_matcher(pattern, True, case_sensitive)
            except re.error as e:
                return None, f"正则表达式无效：{e}"

        # 解析文件类型（与筛选栏一样：逗号/分号都可，统一带开头的点、小写）
        file_types = []
        for part in self.type_edit.text().replace("，", ",").replace(";", ",").split(","):
            t = part.strip().lower()
            if not t:
                continue
            file_types.append(t if t.startswith('.') else f".{t}")

        # 大小范围：存字节数（worker 需要的就是字节），载入时再反算单位
        multiplier = self._SIZE_MULT[self.size_unit.currentIndex()]
        min_size = self.min_size_spin.value()
        max_size = self.max_size_spin.value()

        params = {
            'directory': directory,
            'pattern': pattern,
            'use_regex': use_regex,
            'case_sensitive': case_sensitive,
            'file_types': file_types,
            'min_size': min_size * multiplier if min_size > 0 else 0,
            'max_size': max_size * multiplier if max_size > 0 else 0,
            'content': self.content_edit.text(),
        }
        return params, ""

    def start_search(self):
        """开始搜索"""
        params, err = self.collect_params()
        if err:
            QMessageBox.warning(self, "警告", err)
            return

        self.result_tree.clear()
        self._pending_results = []
        self._shown_count = 0
        self._flush_timer.start()
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("搜索中...")
        
        self.worker = SearchWorker(params)
        self.worker.result.connect(self.on_result)
        self.worker.finished.connect(self.on_search_finished)
        self.worker.start()

    # ---------- 已保存的搜索（清单 20.4） ----------

    @property
    def store(self):
        if self._store is None:
            from config.saved_searches import SavedSearchStore
            self._store = SavedSearchStore()
        return self._store

    def reload_saved_names(self, keep: str = ""):
        """重填下拉（保留 `keep` 为当前项）；第一项是占位，不算已保存项"""
        combo = self.saved_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("（选择已保存的搜索…）")
        combo.addItems(self.store.names())
        combo.setCurrentIndex(max(0, combo.findText(keep)))
        combo.blockSignals(False)
        self.del_saved_btn.setEnabled(combo.count() > 1)

    def on_saved_selected(self, index: int):
        if index <= 0:
            return
        name = self.saved_combo.itemText(index)
        params = self.store.get(name)
        if params is None:
            self.status_label.setText(f"「{name}」已不存在")
            self.reload_saved_names()
            return
        note = self.apply_params(params)
        stamp = self.store.updated(name)
        self.status_label.setText(
            f"已载入「{name}」" + (f"（存于 {stamp}）" if stamp else "") +
            note + "，点「开始搜索」运行")

    def save_current_search(self):
        params, err = self.collect_params()
        if err:
            QMessageBox.warning(self, "无法保存", err + "（保存与搜索用同一套校验）")
            return
        # 默认名：已选中的那条（没选则用文件名模式 / 目录名），不是占位那一项
        default = ""
        if self.saved_combo.currentIndex() > 0:
            default = self.saved_combo.currentText().strip()
        if not default:
            default = self.pattern_edit.text().strip() or \
                os.path.basename(os.path.normpath(self.dir_edit.text().strip()))
        name, ok = QInputDialog.getText(
            self, "保存搜索", "给这组搜索条件起个名字：", text=default)
        name = (name or "").strip()
        if not ok or not name:
            return                      # 取消：什么都不做
        if name in self.store.entries:
            if QMessageBox.question(
                    self, "覆盖已保存的搜索",
                    f"已经有一条叫「{name}」的搜索，覆盖它吗？") \
                    != QMessageBox.StandardButton.Yes:
                return
        saved, err = self.store.save_search(name, params)
        if not saved:
            QMessageBox.warning(self, "保存失败", err or "写入失败")
            return
        self.reload_saved_names(keep=name)
        self.status_label.setText(f"已保存搜索「{name}」")

    def delete_saved_search(self):
        index = self.saved_combo.currentIndex()
        if index <= 0:
            return
        name = self.saved_combo.itemText(index)
        if QMessageBox.question(self, "删除已保存的搜索",
                                f"删除「{name}」？只删条件，不影响文件。") \
                != QMessageBox.StandardButton.Yes:
            return
        self.store.remove(name)
        self.reload_saved_names()
        self.status_label.setText(f"已删除「{name}」")

    def apply_params(self, params: dict) -> str:
        """已保存的条件 → 控件（`collect_params` 的反向）

        返回值是“哪一项没能原样填回去”的说明，空串表示全部一致；调用方（载入槽）
        把它拼进状态栏 —— 宁可啰嗦一句，也不能悄悄把 1 字节变成“无限制”。
        """
        self.dir_edit.setText(str(params.get('directory') or ""))
        self.pattern_edit.setText(str(params.get('pattern') or ""))
        self.regex_check.setChecked(bool(params.get('use_regex')))
        self.case_check.setChecked(bool(params.get('case_sensitive')))
        self.type_edit.setText(",".join(params.get('file_types') or []))
        self.content_edit.setText(str(params.get('content') or ""))
        return self._restore_sizes(int(params.get('min_size') or 0),
                                   int(params.get('max_size') or 0))

    def _restore_sizes(self, min_size: int, max_size: int) -> str:
        """字节数 →（数值 + 单位）放回控件。返回失真说明（无失真时空串）

        两个输入框共用一个单位下拉（这是现有界面的形状），所以单位要选一个能让两者
        都不失真的**最大**单位。存进来的值基本都是 `collect_params` 自己算的（整数 ×
        单位），一定能整除；整除不了或超出 spin 上限的只可能来自手工改过的 JSON，
        那时必须说出来 —— 静默把 1 字节改成 0（＝无限制）比不改还糟。
        """
        spins = (self.min_size_spin, self.max_size_spin)
        values = (min_size, max_size)
        positive = [v for v in values if v > 0]
        limit = self.min_size_spin.maximum()      # 两个 spin 同一个上限（见 init_ui）
        if not positive:
            for spin, v in zip(spins, values):
                spin.setValue(min(v, spin.maximum()))
            return ""
        chosen = 0
        for i in (2, 1, 0):
            m = self._SIZE_MULT[i]
            if all(v % m == 0 and v // m <= limit for v in positive):
                chosen = i
                break
        else:
            # 整除不了：换成放得下的最小单位（粒度越细失真越小），最后如实报出
            for i in (0, 1, 2):
                m = self._SIZE_MULT[i]
                if all(v // m <= limit for v in positive):
                    chosen = i
                    break
        m = self._SIZE_MULT[chosen]
        self.size_unit.setCurrentIndex(chosen)
        lost = False
        for spin, v in zip(spins, values):
            if v:
                spin.setValue(min(max(int(round(v / m)), 0), spin.maximum()))
                if spin.value() * m != v:
                    lost = True
            else:
                spin.setValue(0)
        if lost:
            return (f"（大小范围无法按 {self.size_unit.itemText(chosen)} 原样表示，"
                    "已按最接近的值填入）")
        return ""

    
    def stop_search(self):
        """停止搜索"""
        if self.worker:
            self.worker.stop()
    
    def on_result(self, path: str, size: str, mtime: int):
        """搜索结果：先入缓冲，由定时器批量刷新（避免重绘风暴）"""
        self._pending_results.append((path, size, mtime))

    def _flush_results(self):
        """把缓冲区结果一次性插入树（单趟布局），并尊重显示上限"""
        if not self._pending_results:
            return
        batch, self._pending_results = self._pending_results, []
        max_rows = 5000
        if self._shown_count >= max_rows:
            return
        from datetime import datetime
        items = []
        for path, size, mtime in batch:
            if self._shown_count + len(items) >= max_rows:
                break
            try:
                time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except (OSError, ValueError, OverflowError):
                time_str = ""
            items.append(QTreeWidgetItem([path, size, time_str]))
        if items:
            self.result_tree.setUpdatesEnabled(False)
            self.result_tree.addTopLevelItems(items)
            self.result_tree.setUpdatesEnabled(True)
            self._shown_count += len(items)
        if self._shown_count >= max_rows and (self._pending_results or batch[len(items):]):
            self.status_label.setText(f"结果过多，仅显示前 {max_rows} 项（请缩小搜索范围）")

    def on_search_finished(self, total: int):
        """搜索完成"""
        self._flush_timer.stop()
        self._flush_results()  #  flush 最后一批
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self._shown_count >= 5000 and total > self._shown_count:
            self.status_label.setText(
                f"共 {total} 个，仅显示前 {self._shown_count} 项")
        else:
            self.status_label.setText(f"搜索完成，共找到 {total} 个文件")
    
    def clear_results(self):
        """清除结果"""
        self.result_tree.clear()
        self.status_label.setText("就绪")
    
    # ------------------------------------------------ 结果的批量操作（清单 20.3）

    @property
    def host(self):
        """提供窗格的宿主（一般是主窗口）；没注入时退回 parent"""
        return self._host if self._host is not None else self.parent()

    def pane_for_ops(self):
        """当前用来「打开文件 / 进入目录」的窗格（没有则 None，菜单会说明）"""
        getter = getattr(self.host, "current_pane", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:
            logger.exception("取当前窗格失败")
            return None

    def selected_paths(self) -> list:
        """选中行的路径，按列表里的显示顺序

        `selectedItems()` 不保证顺序（Qt 给的是它内部的选择集合顺序），不排序
        时多选后的「删除前 5 个名字」会跟屏幕上的先后不一致。
        """
        tree = self.result_tree
        items = [it for it in tree.selectedItems() if it.text(0)]
        items.sort(key=tree.indexOfTopLevelItem)
        return [it.text(0) for it in items]

    def _refuse_if_busy(self) -> bool:
        """同一个运行器上不能叠第二个操作（一个 `FileOperations` 共享取消标志）"""
        if not self.runner.busy:
            return False
        QMessageBox.information(self, "正在操作",
                                "上一个文件操作还没结束，请等它完成或在进度框里取消。")
        return True

    def _set_op_status(self, text: str):
        """runner 的状态栏钩子（这个对话框没有底部进度条，只写一行字）"""
        try:
            self.status_label.setText(text)
        except RuntimeError:
            pass                        # 对话框已销毁，操作还在后台跑

    # ------------------------------------------------------------------ 打开类

    def open_selected(self):
        """用关联程序打开选中项（双击、Enter）"""
        paths = self.selected_paths()
        if not paths:
            return
        pane = self.pane_for_ops()
        if pane is None:
            QMessageBox.information(self, "打开", "没有可用来打开文件的窗格（未连接主窗口）")
            return
        if len(paths) > 5 and QMessageBox.question(
                self, "打开多个文件",
                f"要一次打开 {len(paths)} 个文件？外部程序会被一个个启动。") \
                != QMessageBox.StandardButton.Yes:
            return
        opened = gone = failed = 0
        for p in paths:
            try:
                if not os.path.exists(p):
                    gone += 1
                    continue
                if os.path.isdir(p):
                    pane.navigate_to(p)
                else:
                    pane.open_file(p)
                opened += 1
            except Exception as e:
                logger.warning("打开 %s 失败: %s", p, e)
                failed += 1
        self.status_label.setText(self._tally(f"已打开 {opened} 项", gone, failed))

    @staticmethod
    def _tally(head: str, gone: int, failed: int) -> str:
        """把「结果列表是快照」造成的无效项与失败项说出来，不只报成功数"""
        if gone:
            head += f"，{gone} 项已不存在"
        if failed:
            head += f"，{failed} 项打开失败"
        return head

    def open_containing_folders(self):
        """在当前窗格打开选中项所在目录（Ctrl+Shift+Enter）"""
        dirs = []
        for p in self.selected_paths():
            d = os.path.dirname(p)
            if d and d not in dirs:
                dirs.append(d)
        if not dirs:
            return
        pane = self.pane_for_ops()
        if pane is None:
            QMessageBox.information(self, "打开所在文件夹", "没有可导航的窗格（未连接主窗口）")
            return
        pane.navigate_to(dirs[0])
        extra = "" if len(dirs) == 1 else f"（共 {len(dirs)} 个目录，只进了第一个）"
        self.status_label.setText(f"已打开所在目录：{dirs[0]}{extra}")

    def reveal_in_system_manager(self, paths=None):
        """在系统文件管理器里定位选中项（这是旧版双击的行为，现在进右键菜单）"""
        if paths is None:
            paths = self.selected_paths()
        if not paths:
            return
        import subprocess
        import sys
        for p in paths[:5]:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(f'explorer /select,"{p}"')
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", p])
                else:
                    subprocess.Popen(["xdg-open", os.path.dirname(p)])
            except OSError as e:
                logger.warning("定位 %s 失败: %s", p, e)
        if len(paths) > 5:
            self.status_label.setText(f"共 {len(paths)} 项，只在系统文件管理器里定位前 5 个")

    def copy_paths_to_clipboard(self):
        """把选中项的路径作为文本复制进系统剪贴板（Ctrl+C）

        不是把文件放进应用内剪贴板：高级搜索是对话框，开着它切不到窗格去
        Ctrl+V，那条路走不通；要搬文件用菜单里的「复制到…」直接选目标目录。
        """
        paths = self.selected_paths()
        if not paths:
            return
        QApplication.clipboard().setText("\n".join(paths))
        self.status_label.setText(f"已复制 {len(paths)} 条路径文本")

    # ------------------------------------------------------------------ 搬运类

    def copy_selected_to(self):
        self._transfer_selected("复制")

    def move_selected_to(self):
        self._transfer_selected("移动")

    def _transfer_selected(self, verb: str):
        paths = self.selected_paths()
        if not paths or self._refuse_if_busy():
            return
        pane = self.pane_for_ops()
        start = getattr(pane, "current_path", "") or self.dir_edit.text().strip()
        target = QFileDialog.getExistingDirectory(self, f"选择{verb}目标文件夹", start)
        if not target:
            self.status_label.setText(f"已取消{verb}")
            return
        if verb == "移动" and move_target_inside_sources(paths, target):
            QMessageBox.warning(self, "移动", "不能把目录移到它自己或它的子目录里")
            return
        norm = os.path.normpath(target)
        same = [p for p in paths if os.path.normpath(os.path.dirname(p)) == norm]
        if same:
            # 与资源管理器一致：源就在目标文件夹里，复制是同一文件报错、移动是无意义
            QMessageBox.warning(
                self, verb,
                f"有 {len(same)} 个项目本来就在目标文件夹里，已取消整个操作。")
            return
        ops = self.runner.ops
        if verb == "复制":
            fn = lambda: ops.copy(paths, target)
        else:
            fn = lambda: ops.move(paths, target)
        self.runner.run(f"正在{verb}", fn,
                        done=lambda r: self._on_transfer_done(r, verb, paths, target))

    def _on_transfer_done(self, result, verb: str, paths, target: str):
        if not result.success:
            self.status_label.setText(f"{verb}失败")
            QMessageBox.warning(self, verb, result.error or "操作失败")
            return
        self._refresh_dirs_everywhere([os.path.join(target, "x")] +
                                      (paths if verb == "移动" else []))
        text = f"已{verb} {len(paths)} 项 → {target}"
        if verb == "移动":
            # 移动后原路径已经不指向列表里的行了，留着只会让人再点一次失败；
            # 结果列表是搜出来那一刻的快照，不重新搜不会出现新位置那份
            removed = self._drop_rows(paths)
            text += f"（已从结果移除 {removed} 行，不会自动重新搜索）"
        self.status_label.setText(text)
        if result.error:
            QMessageBox.information(self, verb, result.error)

    def delete_selected(self, permanent: bool = False):
        """删除选中项：Del 走回收站，Shift+Del 直接永久删除（与窗格同一套）"""
        paths = self.selected_paths()
        if not paths or self._refuse_if_busy():
            return
        title, body = describe_removal(paths, permanent)
        if QMessageBox.question(self, title, body,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) \
                != QMessageBox.StandardButton.Yes:
            self.status_label.setText("已取消删除")
            return
        ops = self.runner.ops
        self.runner.run("正在删除", lambda: ops.delete(paths, safe=not permanent),
                        done=lambda r: self._on_delete_done(r, paths))

    def _on_delete_done(self, result, paths):
        if not result.success:
            self.status_label.setText("删除失败")
            QMessageBox.warning(self, "删除失败", result.error or "操作失败")
            return
        removed = self._drop_rows(paths)
        self._refresh_dirs_everywhere(paths)
        text = (f"已删除 {result.files_affected or len(paths)} 个项目，"
                f"从结果移除 {removed} 行（不会自动重新搜索）")
        self.status_label.setText(text)
        if result.error:
            # 网络位置回退永久删除等附带结果必须告知（窗格同样这么处理）
            QMessageBox.information(self, "删除完成", result.error)

    # ---------------------------------------------------------------- 收尾处理

    def _drop_rows(self, paths) -> int:
        """把不再指向存在文件的那些行从结果列表拿掉，并同步显示上限计数"""
        tree = self.result_tree
        wanted = set(paths)
        removed = 0
        for i in reversed(range(tree.topLevelItemCount())):
            it = tree.topLevelItem(i)
            if it is not None and it.text(0) in wanted:
                tree.takeTopLevelItem(i)        # 离开树后交给 Python，出作用域即回收
                removed += 1
        if removed:
            # 不退回 `_shown_count` 的话，那个 5000 行上限会被已删掉的行占着，
            # 剩下的结果永远进不来
            self._shown_count = max(0, self._shown_count - removed)
        return removed

    def _refresh_dirs_everywhere(self, paths):
        """让正在显示这些目录的窗格重扫（结果列表不是文件系统的眼睛）

        本地目录的 watcher 通知有系统延迟、网络目录完全不挂 watcher，所以
        应用内改动必须显式失效 —— 这里用窗格那边同一个入口。
        """
        try:
            from core.pane import Pane
            dirs = {os.path.normpath(os.path.dirname(p)) for p in paths if p}
            for d in dirs:
                Pane._refresh_dir_everywhere(d)
        except Exception:
            logger.debug("刷新受影响目录失败", exc_info=True)

    def show_results_menu(self, pos):
        """结果列表右键菜单"""
        tree = self.result_tree
        hit = tree.itemAt(pos)
        if hit is not None and not hit.isSelected():
            # 右键压在未选中的行上：选区收到只剩那一行（资源管理器习惯）；
            # 压在已有选区里则保留整个选区，不然多选删除一点菜单就只剩一项
            tree.clearSelection()
            hit.setSelected(True)
        paths = self.selected_paths()
        menu = QMenu(self)
        if not paths:
            menu.addAction("（没有选中任何结果）").setEnabled(False)
        else:
            n = len(paths)
            suffix = f"（{n} 项）" if n > 1 else ""
            menu.addAction(f"打开{suffix}", self.open_selected)
            menu.addAction("打开所在文件夹", self.open_containing_folders)
            menu.addAction("在系统文件管理器中选中", self.reveal_in_system_manager)
            menu.addAction("复制路径文本", self.copy_paths_to_clipboard)
            menu.addSeparator()
            busy = self.runner.busy
            actions = [(f"复制到…{suffix}", self.copy_selected_to),
                       (f"移动到…{suffix}", self.move_selected_to),
                       (f"删除{suffix}", lambda: self.delete_selected(False)),
                       (f"永久删除{suffix}", lambda: self.delete_selected(True))]
            for text, slot in actions:
                act = menu.addAction(text, slot)
                act.setEnabled(not busy)
                if busy:
                    act.setToolTip("上一个文件操作还没结束")
        menu.exec(tree.mapToGlobal(pos))

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击打开文件（资源管理器习惯）；定位到系统文件管理器进右键菜单"""
        if not self.result_tree.selectedItems():
            item.setSelected(True)
        self.open_selected()
