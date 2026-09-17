"""
Pan4dex 万格 — 列表筛选（查询文本 → 匹配器 + 筛选栏 UI）

与资源管理器搜索框的习惯对齐：只筛**当前目录**（不递归，不跨盘搜索），多个条件之间是「且」。

查询语法（空格分隔；字段名不区分大小写，支持中文别名）：

| 写法                                        | 含义                             |
|---------------------------------------------|----------------------------------|
| `报告` / `report.txt`                       | 名称包含（不区分大小写）         |
| `*.log` / `foo?ar`                          | 名称按通配符整体匹配             |
| `name:报告` / `名称:报告`                   | 同上，显式字段                   |
| `ext:py,js` / `扩展名:.txt`                 | 扩展名列表（目录一律不匹配）     |
| `type:txt` / `类型:目录`                     | 值是 目录/文件 → 按类型，否则按扩展名 |
| `is:folder` / `is:file` / `属性:文件`       | 只看目录 / 只看文件              |
| `date:今天` / `date:本周` / `date:本月` / `date:今年` / `date:昨天` | 修改日期预设 |
| `date:2026-09-13` / `date:>=2026-09-01` / `date:2026-01-01..2026-03-01` / `date:2026-09` | 修改日期区间 |
| `size:>10mb` / `size:<1kb` / `size:1mb-100mb` / `size:空` / `size:大型` | 大小 |
| `re:^report\\d+\\.txt$`                      | 正则（对名称做 search）          |

解析不了的片段（`date:瞎写`）**降级成「名称包含」**而不是忽略：忽略会让用户以为筛选生效了
却看到整个目录，比“筛出 0 项”更难解释。降级过的片段记在 `EntryFilter.bad` 里供界面提示。

过滤动作在 `core/pane.py:PaneSortProxyModel.filterAcceptsRow`（排序 + 过滤同一个代理，
不再叠一层 `QSortFilterProxyModel`，避免两次索引映射）。
"""
import os
import re
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QEvent, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QLabel, QComboBox,
)

from core.lifecycle import safe_event_filter


# ---------- 值解析 ----------

_SIZE_UNITS = {
    "": 1, "b": 1, "byte": 1, "bytes": 1,
    "k": 1024, "kb": 1024, "kib": 1024,
    "m": 1024 ** 2, "mb": 1024 ** 2, "mib": 1024 ** 2,
    "g": 1024 ** 3, "gb": 1024 ** 3, "gib": 1024 ** 3,
    "t": 1024 ** 4, "tb": 1024 ** 4, "tib": 1024 ** 4,
}

# 资源管理器「大小」预设（闭区间，None = 无上限）。目录不匹配任何 size 条件。
_SIZE_PRESETS = {
    "空": (0, 0), "none": (0, 0), "empty": (0, 0),
    "小型": (1, 102400), "small": (1, 102400),
    "中型": (102400, 1048576), "medium": (102400, 1048576),
    "大型": (1048576, 16777216), "large": (1048576, 16777216),
    "巨大": (16777216, None), "huge": (16777216, None),
}

_DIR_WORDS = {"folder", "dir", "directory", "目录", "文件夹"}
_FILE_WORDS = {"file", "文件"}

_FIELD_ALIASES = {
    "name": "name", "名称": "name", "文件名": "name",
    "ext": "ext", "扩展名": "ext", "后缀": "ext",
    "type": "type", "类型": "type",
    "is": "is", "属性": "is", "kind": "is",
    "date": "date", "日期": "date", "修改日期": "date", "修改时间": "date",
    "size": "size", "大小": "size",
    "re": "re", "正则": "re",
}

_NUM_UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$")
_DATE_RANGE_RE = re.compile(r"^(.+?)(?:\.\.|~)(.+)$")
_DATE_OP_RE = re.compile(r"^(>=|<=|>|<|≥|≤)\s*(.+)$")


def _parse_size_token(value: str):
    """`>10mb` / `1mb-100mb` / `空` → (下限, 上限) 闭区间；解析失败返回 None"""
    v = value.strip().lower().replace(",", "").replace("，", "")
    if not v:
        return None
    if v in _SIZE_PRESETS:
        lo, hi = _SIZE_PRESETS[v]
        return lo, hi

    def one(text):
        m = _NUM_UNIT_RE.match(text.strip())
        if not m:
            return None
        return float(m.group(1)) * _SIZE_UNITS.get(m.group(2), 1)

    # 区间：`1mb-100mb`（左侧不能带比较符，所以只在没有比较符时按区间处理）
    if not v[0] in "<>=：:":
        m = re.match(r"^(.+?)[-~](.+)$", v)
        if m:
            lo, hi = one(m.group(1)), one(m.group(2))
            if lo is not None and hi is not None:
                return (min(lo, hi), max(lo, hi))
            return None
    m = re.match(r"^(>=|<=|>|<|≥|≤)?\s*(.+)$", v)
    op, rest = m.group(1), m.group(2)
    num = one(rest)
    if num is None:
        return None
    if op in (">", "≥"):
        return num + 1, None
    if op in (">=", None):
        return num, None
    if op in ("<", "≤"):
        return 0, max(0, num - 1)
    return 0, num


def _start_of_day(base: datetime) -> float:
    return base.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _norm_date(text: str) -> str:
    """`2026/09/13`、`2026.09.13` 归一为 `2026-09-13`（先别拆区间，否则 `..` 会被洗坏）"""
    return text.strip().replace("/", "-").replace(".", "-")


def _date_token_to_range(value: str):
    """`今天` / `2026-09-13` / `>=2026-01-01` / `a..b` / `2026-09` → (lo, hi) 左闭右开"""
    v = value.strip()
    if not v:
        return None
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    key = v.lower()
    if key in ("今天", "today"):
        return today.timestamp(), (today + timedelta(days=1)).timestamp()
    if key in ("昨天", "yesterday"):
        lo = (today - timedelta(days=1)).timestamp()
        # 右界取「今天零点」而不是 `lo + 86400`：跨夏令时的那天，24 小时会比一个
        # 日历天多/少一小时，「昨天」就会漏掉或多吃一个小时
        return lo, today.timestamp()
    if key in ("本周", "thisweek", "this week", "这周"):
        lo = today - timedelta(days=today.weekday())
        return lo.timestamp(), (lo + timedelta(days=7)).timestamp()
    if key in ("本月", "thismonth", "this month"):
        lo = today.replace(day=1)
        nxt = (lo.replace(day=28) + timedelta(days=4)).replace(day=1)
        return lo.timestamp(), nxt.timestamp()
    if key in ("今年", "thisyear", "this year"):
        lo = today.replace(month=1, day=1)
        return lo.timestamp(), lo.replace(year=lo.year + 1).timestamp()

    def day(text, end=False):
        """`2026-09-13` → 当天 0 点 / 次日 0 点；`2026-09` → 整月；`2026` → 整年"""
        t = _norm_date(text)
        try:
            d = datetime.strptime(t, "%Y-%m-%d")
        except ValueError:
            pass
        else:
            lo = d.replace(hour=0, minute=0, second=0, microsecond=0)
            if not end:
                return lo.timestamp()
            return (lo + timedelta(days=1)).timestamp()
        if re.match(r"^\d{4}-\d{1,2}$", t):
            lo = datetime.strptime(t, "%Y-%m").replace(day=1)
            nxt = (lo.replace(day=28) + timedelta(days=4)).replace(day=1)
            return (nxt if end else lo).timestamp()
        if re.match(r"^\d{4}$", t):
            lo = datetime(int(t), 1, 1)
            return (datetime(int(t) + 1, 1, 1) if end else lo).timestamp()
        return None

    m = _DATE_RANGE_RE.match(v)
    if m:
        lo, hi = day(m.group(1)), day(m.group(2), end=True)
        if lo is not None and hi is not None:
            return lo, max(lo, hi)
        return None
    m = _DATE_OP_RE.match(v)
    if m:
        op, rest = m.group(1), m.group(2)
        if op in (">", "≥"):
            lo = day(rest, end=True)
            return (lo, None) if lo is not None else None
        if op == ">=":
            lo = day(rest)
            return (lo, None) if lo is not None else None
        if op in ("<", "≤"):
            hi = day(rest)
            return (0, hi) if hi is not None else None
        hi = day(rest, end=True)
        return (0, hi) if hi is not None else None

    single, end = day(v), day(v, end=True)
    if single is not None and end is not None:
        return single, end
    return None


def glob_to_regex(pattern: str, flags=re.IGNORECASE):
    """`*.log` 之类 → 整名匹配（全仓一套通配符语义，高级搜索也用它）"""
    out = []
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    return re.compile("^" + "".join(out) + "$", flags)


def _ext_list(value: str):
    exts = set()
    for part in value.replace("，", ",").replace(";", ",").split(","):
        p = part.strip().lower().lstrip("*").lstrip(".").strip()
        if p:
            exts.add(p)
    return exts


class EntryFilter:
    """编译后的筛选条件集合（条件之间为「且」）。

    `matches` 只吃调用方已经拿到的属性，绝不自己 stat / 不碰网络 —— 列表侧
    （`DirStoreModel`）已经有 size/mtime，超大图标视图只有 name/is_dir
    （`needs_stat` 为真时它才补一次 `entry.stat()`）。
    """
    __slots__ = ("terms", "bad", "raw")

    def __init__(self, terms=(), bad=(), raw=""):
        self.terms = tuple(terms)
        self.bad = tuple(bad)
        self.raw = raw

    @property
    def active(self) -> bool:
        return bool(self.terms)

    @property
    def needs_stat(self) -> bool:
        """含 size/date 条件 —— 调用方需要提供 mtime/size（列表侧白拿，图标侧要 stat）"""
        return any(k in ("size", "date") for k, _ in self.terms)

    def __bool__(self):
        return self.active

    def __repr__(self):
        return f"EntryFilter(raw={self.raw!r}, terms={len(self.terms)})"

    def matches(self, name: str, is_dir: bool, size: int = -1, mtime: float = 0.0) -> bool:
        for kind, payload in self.terms:
            if not _test(kind, payload, name, is_dir, size, mtime):
                return False
        return True


def _test(kind, payload, name, is_dir, size, mtime) -> bool:
    if kind == "name":
        return payload[0].lower() in name.lower() if payload[1] is None else bool(payload[1].match(name))
    if kind == "ext":
        if is_dir:
            return False
        dot = name.rfind(".")
        return dot > 0 and name[dot + 1:].lower() in payload
    if kind == "is_dir":
        return is_dir == payload
    if kind == "size":
        if is_dir or size is None or size < 0:
            return False
        lo, hi = payload
        return size >= lo and (hi is None or size <= hi)
    if kind == "date":
        if not mtime:
            return False
        lo, hi = payload
        return mtime >= lo and (hi is None or mtime < hi)
    if kind == "re":
        return bool(payload.search(name))
    return True


_EMPTY = EntryFilter()


def split_query(text: str):
    """按空格切分，双引号内算一个片段（`name:"第三季度 报告"`）"""
    out, cur, in_quote = [], "", False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
            continue
        if ch.isspace() and not in_quote:
            if cur:
                out.append(cur)
            cur = ""
            continue
        cur += ch
    if cur:
        out.append(cur)
    return out


def _add_term(terms, bad, kind, value):
    """把一个 `字段:值` 片段编译成 term；返回 False 表示无法解析（调用方降级为名称匹配）"""
    if kind == "name":
        v = value.strip()
        if not v:
            return False
        if "*" in v or "?" in v:
            terms.append(("name", (v, glob_to_regex(v))))
        else:
            terms.append(("name", (v, None)))
        return True
    if kind in ("ext", "type"):
        low = value.strip().lower()
        if kind == "type" and (low in _DIR_WORDS or low in _FILE_WORDS or
                                value.strip() in ("目录", "文件夹", "文件")):
            terms.append(("is_dir", low in _DIR_WORDS or value.strip() in ("目录", "文件夹")))
            return True
        exts = _ext_list(value)
        if not exts:
            return False
        terms.append(("ext", exts))
        return True
    if kind == "is":
        low = value.strip().lower()
        if low in _DIR_WORDS or value.strip() in ("目录", "文件夹"):
            terms.append(("is_dir", True))
            return True
        if low in _FILE_WORDS or value.strip() == "文件":
            terms.append(("is_dir", False))
            return True
        return False
    if kind == "size":
        rng = _parse_size_token(value)
        if rng is None:
            return False
        terms.append(("size", rng))
        return True
    if kind == "date":
        rng = _date_token_to_range(value)
        if rng is None:
            return False
        terms.append(("date", rng))
        return True
    if kind == "re":
        try:
            rx = re.compile(value, re.IGNORECASE)
        except re.error:
            return False
        terms.append(("re", rx))
        return True
    return False


def compile_filter(text: str) -> EntryFilter:
    """查询文本 → `EntryFilter`。空文本 / 全空白 → 恒真（`active` 为 False）"""
    text = (text or "").strip()
    if not text:
        return _EMPTY
    terms, bad = [], []
    for token in split_query(text):
        field, sep, value = token.partition(":")
        kind = _FIELD_ALIASES.get(field.strip().lower()) if sep else None
        if kind is not None and _add_term(terms, bad, kind, value):
            continue
        if kind is not None:
            # 字段认得但值写错了（如 `date:写错了`）：记一笔供界面提示，再降级
            bad.append(token)
        # 无字段前缀、字段不认识、或值解析不了 → 按名称匹配
        if _add_term(terms, bad, "name", token):
            continue
        bad.append(token)
    return EntryFilter(terms, bad, text)


# ---------- UI ----------

class FilterBar(QWidget):
    """筛选栏：一个查询输入框 + 字段下拉（帮不熟语法的人拼条件）+ 清除。

    `filter_changed` 发射的是**编译前的查询文本**（空串＝无筛选），具体语法由
    `compile_filter` 解释。字段下拉只在前缀缺失时补上 `size:` / `date:` 之类，
    用户自己写了 `字段:值` 时以原文为准 —— 两处都能写、不打架。
    """

    filter_changed = pyqtSignal(str)     # 组合后的查询文本（""＝清除）
    escape_pressed = pyqtSignal()        # Esc：由窗格决定收起筛选栏并把焦点还给列表

    _DEBOUNCE_MS = 250                   # 逐字符重筛在上万行的目录里肉眼可见地卡

    # (显示名, 字段前缀)。"自动" 不补前缀
    MODES = (("自动", ""), ("名称", "name:"), ("扩展名", "ext:"),
             ("修改日期", "date:"), ("大小", "size:"), ("正则表达式", "re:"))

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(5)

        self.filter_label = QLabel("筛选:")
        self.layout.addWidget(self.filter_label)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "筛选当前目录：*.log  ext:py,md  size:>10mb  date:本周  类型:目录    （空格＝且）")
        self.filter_edit.setToolTip(
            "只筛当前目录（不递归）。条件之间是「且」，空格分隔：\n"
            "  报告 / *.log / foo?ar      名称包含或通配符\n"
            "  ext:py,js                  扩展名\n"
            "  类型:目录 / is:file        只看目录 / 只看文件\n"
            "  date:今天 昨天 本周 本月 今年 / date:>=2026-09-01 / date:2026-01-01..2026-03-01\n"
            "  size:>10mb  <1kb  1mb-100mb  空  小型 中型 大型 巨大\n"
            "  re:^report\\d+\\.txt$          正则\n"
            "Esc 清除并收起筛选栏（或点输入框行内的 ✕）")
        self.filter_edit.setClearButtonEnabled(True)   # 行内 ✕：四窗格下横向空间紧张，不再另加按钮
        self.filter_edit.returnPressed.connect(self.apply_filter)
        self.filter_edit.textChanged.connect(self._on_text_changed)
        self.filter_edit.installEventFilter(self)
        self.layout.addWidget(self.filter_edit)

        self.filter_type = QComboBox()
        self.filter_type.setToolTip("按字段筛选：帮不记得语法的人补上前缀（选「自动」＝完全按输入解释）")
        for label, _prefix in self.MODES:
            self.filter_type.addItem(label)
        self.filter_type.currentIndexChanged.connect(self._on_mode_changed)
        self.layout.addWidget(self.filter_type)

        # 逐字符筛＝每键一次全表重过滤，防抖到停手之后再落地
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._DEBOUNCE_MS)
        self._timer.timeout.connect(self.apply_filter)

        self._last_query = ""
        # 样式由全局 ThemeManager 统一管理（不在此硬编码颜色，避免主题切换时显示异常）

    # ---- 事件 ----
    @safe_event_filter
    def eventFilter(self, obj, event):
        """Esc：清除并让窗格收起筛选栏（ QLineEdit 内部会先吃掉 Esc，故用过滤器）"""
        if obj is self.filter_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Escape,):
                self._timer.stop()
                self.clear_filter()
                self.escape_pressed.emit()
                return True
        return super().eventFilter(obj, event)

    def _on_text_changed(self, text: str):
        if not text.strip():
            self._timer.stop()
            self._emit("")
            return
        self._timer.start()

    def _on_mode_changed(self, _index: int):
        # 换字段时不重编查询：等下一次 textChanged / apply_filter 生效
        if self.filter_edit.text().strip():
            self.apply_filter()

    # ---- 对外 ----
    def compose_query(self, text: str = None) -> str:
        """输入文本 + 字段下拉 → 实际查询文本（纯函数，单测覆盖）"""
        text = self.filter_edit.text() if text is None else text
        text = text.strip()
        if not text:
            return ""
        prefix = self.MODES[self.filter_type.currentIndex()][1]
        if not prefix:
            return text                     # 「自动」：完全按用户写的解释
        if any(":" in tok for tok in split_query(text)):
            return text                     # 已显式写了字段前缀，以原文为准
        return f"{prefix}{text}"

    def apply_filter(self):
        query = self.compose_query()
        self._timer.stop()
        self._emit(query)

    def clear_filter(self):
        """清空输入并**无条件**补发一次「无筛选」。

        不能走「文本没变就不发」那个护栏：防抖未落地时 `_last_query` 还是旧值，
        不强制发就会留下「点了清除、旧条件还在」的状态。
        """
        self._timer.stop()
        self.filter_edit.clear()
        self._emit("", force=True)

    def query(self) -> str:
        """当前生效的查询文本（空串＝无筛选）"""
        return self._last_query

    def set_query(self, text: str, apply_now: bool = True):
        self.filter_edit.setText(text or "")
        if apply_now:
            self.apply_filter()

    def focus_input(self):
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()

    def _emit(self, query: str, force: bool = False):
        if query == self._last_query and not force:
            return
        self._last_query = query
        self.filter_changed.emit(query)
