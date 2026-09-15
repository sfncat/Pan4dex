# -*- coding: utf-8 -*-
"""Pan4dex 万格 — 收藏夹（分组树）的模型与持久化（清单 8.4）

存一棵树：分组可嵌套，叶子是指向目录的链接。UI（`widgets/bookmark_sidebar.py`）只负责
画树并把用户动作翻成这里的方法，**规则全在这一层**，所以它不依赖 Qt、可以直接测。

节点两种：

    {"id": 3, "type": "link",  "name": "文档", "path": "C:\\Users\\x\\Documents"}
    {"id": 4, "type": "group", "name": "工作", "expanded": True, "children": [...]}

四条约束（改这里之前先读）：
- **id 是节点的唯一引用**。UI 侧的 `QTreeWidgetItem` 会随重排重建，行号在中间插一个
  分组后整体错位 —— 旧版正是拿 `list_widget.currentRow()` 去索引一个平铺 list，两边
  一旦不同步就会改错/删错项。所有改动的入参都是 id。
- 老格式（`[{"name","path"}]`）在 `load()` 里迁移成 v2，**读到即转换、改过才写盘**：
  一上来就覆盖用户文件的话，转换有 bug 就没有退路了。
- **不校验 path 是否存在**：网络位置（SMB）与可移动盘经常只是暂时不在，收藏时的可用
  性不等于打开时的可用性。旧版是 `if os.path.isdir(path)` 才发信号 —— 目录当下不可达
  时双击**静默无响应**，用户只当侧边栏坏了。失败要由 UI 说出来。
- 数量与深度有上限（`MAX_ITEMS` / `MAX_DEPTH`）：分组可嵌套就等于能拖出无穷套，而侧边
  栏宽 300px，第 9 层缩进已经把名字挤成一条缝，没有实用价值。
"""
from __future__ import annotations

import json
import logging
import os

from config.paths import default_config_dir

logger = logging.getLogger("pan4dex.bookmarks")

FILE_NAME = "bookmarks.json"
FORMAT_VERSION = 2                    # v1 = 平铺 list；v2 = 带分组的树
MAX_ITEMS = 500                       # 全树节点总数（分组 + 链接）
MAX_DEPTH = 8                         # 根算第 0 层
MAX_NAME_LEN = 60

ROOT_ID = 0


class BookmarkError(ValueError):
    """结构规则不满足（名字空 / id 不存在 / 成环 / 超限）。

    消息本身就是给人看的中文，UI 直接显示，不再各自拼文案。
    """


def default_nodes() -> list:
    """首次启动（配置文件不存在）给的四个常用位置

    只在**文件不存在**时用；用户把收藏删空后不会再灌回来（旧版是
    `if not self.bookmarks` 就回灌，等于「删不掉系统给的那几条」）。
    """
    from pathlib import Path
    home = Path.home()
    out = []
    for name, p in (("主目录", home), ("桌面", home / "Desktop"),
                    ("下载", home / "Downloads"), ("文档", home / "Documents")):
        out.append({"type": "link", "name": name, "path": str(p)})
    return out


class BookmarkStore:
    """收藏夹树的读写与结构规则（单文件 JSON，与关联表/已保存搜索同一目录）"""

    def __init__(self, config_dir: str = None):
        # 参数口径与 `FileAssociations` / `SavedSearchStore` 一致（都收 config 目录，
        # 文件名归本模块定），测试注入临时目录时不用猜三个类三种签名
        if config_dir is None:
            config_dir = default_config_dir()
        self.config_file = os.path.join(config_dir, FILE_NAME)
        self.root = {"id": ROOT_ID, "type": "group", "name": "",
                     "expanded": True, "children": []}
        self._next_id = 1
        self.migrated = False          # 读到的是老格式（改过时才写盘）
        try:
            os.makedirs(os.path.dirname(self.config_file) or ".", exist_ok=True)
        except OSError as e:
            logger.warning("创建收藏夹目录失败 %s: %s", self.config_file, e)
        self.load()

    # ---------------------------------------------------------------- 读

    def load(self):
        """读盘并建好整棵树（坏文件 / 坏记录一律降级处理，不抛）"""
        self.root["children"] = []
        if not os.path.exists(self.config_file):
            self._adopt(default_nodes())
            self.save()                # 首启动：把默认落盘，下次不再判空
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("收藏夹读取失败，按空表处理 %s: %s", self.config_file, e)
            return
        nodes, migrated = self._coerce_file(raw)
        self._adopt(nodes)
        self.migrated = migrated

    def _coerce_file(self, raw):
        """整份文件 → 节点列表 + 是否为待迁移的老格式"""
        if isinstance(raw, list):                       # v1：平铺 [{name,path}]
            return self._coerce_nodes(raw, 1), True
        if isinstance(raw, dict):
            if isinstance(raw.get("children"), list):   # v2：根是一个隐式分组
                return self._coerce_nodes(raw["children"], 1), False
            if isinstance(raw.get("groups"), list):     # 兼容中间态（没见过，但别炸）
                return self._coerce_nodes(raw["groups"], 1), True
        logger.warning("收藏夹文件格式不认识，按空表处理: %s", self.config_file)
        return [], False

    def _coerce_nodes(self, items, depth):
        """逐条校验：一条坏记录不该带走其余的；超长的名字截断而不是丢弃"""
        out = []
        if depth > MAX_DEPTH:
            logger.warning("收藏夹层级超过 %d 层，丢弃该层及以下", MAX_DEPTH)
            return out
        for raw in items if isinstance(items, list) else []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()[:MAX_NAME_LEN]
            kind = raw.get("type")
            if kind == "group" or isinstance(raw.get("children"), list):
                children = self._coerce_nodes(raw.get("children") or [], depth + 1)
                if not name:
                    name = "未命名分组"
                out.append({"type": "group", "name": name,
                            "expanded": bool(raw.get("expanded", True)),
                            "children": children})
            elif kind == "link" or raw.get("path"):
                path = str(raw.get("path") or "").strip()
                if not path:
                    continue
                if not name:
                    # 没名字的条目（老文件 / 手改过）用目录名兜底，不直接丢掉一条收藏
                    name = os.path.basename(path.rstrip("/\\")) or path
                out.append({"type": "link", "name": name[:MAX_NAME_LEN], "path": path})
        return out

    def _adopt(self, nodes):
        """给转换出来的节点分配 id（导入的文件里 id 一律不信任）"""
        for n in nodes:
            n["id"] = self._next_id
            self._next_id += 1
            if n["type"] == "group":
                self._adopt(n["children"])
        self.root["children"] = nodes

    # ---------------------------------------------------------------- 查

    def find(self, node_id: int, node: dict = None):
        """id → 节点（含根）；找不到返回 None"""
        node = self.root if node is None else node
        if node["id"] == node_id:
            return node
        for child in node.get("children", ()):
            got = self.find(node_id, child)
            if got is not None:
                return got
        return None

    def parent_of(self, node_id: int):
        return self._parent_search(node_id, self.root)

    def _parent_search(self, node_id, node):
        for child in node.get("children", ()):
            if child["id"] == node_id:
                return node
            got = self._parent_search(node_id, child)
            if got is not None:
                return got
        return None

    def children_of(self, node_id: int) -> list:
        node = self.find(node_id)
        return node.get("children", []) if node else []

    def depth_of(self, node_id: int) -> int:
        """根的直接子节点是第 1 层"""
        depth, node = 0, self.find(node_id)
        while node is not None and node["id"] != ROOT_ID:
            node = self.parent_of(node["id"])
            depth += 1
        return depth

    def height_of(self, node) -> int:
        """子树高度（叶子为 1）"""
        kids = node.get("children") or []
        return 1 + max((self.height_of(k) for k in kids), default=0)

    def link_count(self, node) -> int:
        """子树里有多少条链接（删分组前要拿它跟用户说清楚会带走几条）"""
        return sum(1 if k["type"] == "link" else self.link_count(k)
                   for k in node.get("children") or [])

    def contains(self, node, node_id: int) -> bool:
        """node 的子树里是否含 node_id（含自身）——拖环检查用"""
        if node["id"] == node_id:
            return True
        return any(self.contains(k, node_id) for k in node.get("children") or [])

    def count(self) -> int:
        return self._count(self.root) - 1                     # 不含根

    def _count(self, node) -> int:
        return 1 + sum(self._count(k) for k in node.get("children") or [])

    def links(self) -> list:
        """全部链接（树的视觉顺序），供状态栏计数与旧 API `get_bookmarks()`"""
        out = []
        self._collect_links(self.root, out)
        return out

    def _collect_links(self, node, out):
        for child in node.get("children") or []:
            if child["type"] == "link":
                out.append(child)
            else:
                self._collect_links(child, out)

    def groups(self) -> list:
        out = []
        self._collect_groups(self.root, out)
        return out

    def _collect_groups(self, node, out):
        for child in node.get("children") or []:
            if child["type"] == "group":
                out.append(child)
                self._collect_groups(child, out)

    # ---------------------------------------------------------------- 改

    def _clean_name(self, name) -> str:
        name = str(name or "").strip()
        if not name:
            raise BookmarkError("名字不能为空")
        if len(name) > MAX_NAME_LEN:
            raise BookmarkError(f"名字太长（最多 {MAX_NAME_LEN} 个字符）")
        return name

    def _require_group(self, parent_id, action="放入"):
        parent = self.find(ROOT_ID if parent_id is None else parent_id)
        if parent is None:
            raise BookmarkError("目标分组已不存在")
        if parent["type"] != "group":
            raise BookmarkError(f"只能{action}分组里，「{parent['name']}」是一条收藏")
        return parent

    def _require_node(self, node_id):
        node = self.find(node_id)
        if node is None:
            raise BookmarkError("这一项已不存在（可能在别的窗口里被删了）")
        return node

    def _fit_depth(self, parent, height: int):
        """把一棵高 `height` 的子树挂到 `parent` 下，会不会超层数上限"""
        if self.depth_of(parent["id"]) + height > MAX_DEPTH:
            raise BookmarkError(f"最多嵌套 {MAX_DEPTH} 层，这里放不下了")

    def add_link(self, name, path, parent_id=None, index=None) -> int:
        if self.count() >= MAX_ITEMS:
            raise BookmarkError(f"收藏已有 {MAX_ITEMS} 条，请先删掉不再用的")
        name = self._clean_name(name)
        path = str(path or "").strip()
        if not path:
            raise BookmarkError("要收藏的目录路径不能为空")
        parent = self._require_group(parent_id)
        self._fit_depth(parent, 1)
        node = {"id": self._take_id(), "type": "link", "name": name, "path": path}
        parent["children"].insert(_clamp(index, len(parent["children"])), node)
        return node["id"]

    def add_group(self, name, parent_id=None) -> int:
        if self.count() >= MAX_ITEMS:
            raise BookmarkError(f"收藏已有 {MAX_ITEMS} 条，请先删掉不再用的")
        name = self._clean_name(name)
        parent = self._require_group(parent_id)
        self._fit_depth(parent, 1)
        node = {"id": self._take_id(), "type": "group", "name": name,
                "expanded": True, "children": []}
        parent["children"].append(node)
        return node["id"]

    def rename(self, node_id, name):
        node = self._require_node(node_id)
        node["name"] = self._clean_name(name)

    def set_path(self, node_id, path):
        node = self._require_node(node_id)
        if node["type"] != "link":
            raise BookmarkError("分组没有路径可改")
        path = str(path or "").strip()
        if not path:
            raise BookmarkError("路径不能为空")
        node["path"] = path

    def set_expanded(self, node_id, expanded: bool):
        if node_id == ROOT_ID:
            return              # 根是一棵隐式分组，侧边栏不画它，记这个位没有意义
        node = self.find(node_id)
        if node is not None and node["type"] == "group":
            node["expanded"] = bool(expanded)

    def remove(self, node_id):
        """删一项；分组连带它的整棵子树（与资源管理器删文件夹一致）"""
        if node_id == ROOT_ID:
            raise BookmarkError("不能删除收藏夹本身")
        node = self._require_node(node_id)
        parent = self.parent_of(node_id)
        parent["children"].remove(node)
        return self._count(node) - 1                  # 被一起带走多少项

    def can_place(self, node_id, parent_id) -> str:
        """能不能把 `node_id` 挂到 `parent_id` 下。空串 = 可以，否则是不能的原因

        拖拽时 Qt 会在 `canDropMimeData` 里问这个（那里不能抛异常，只能回 bool），
        而 `move()` 要把同一个判断变成报错文案 —— 规则只写在这一个函数里。
        """
        if node_id == ROOT_ID:
            return "不能移动收藏夹本身"
        node = self.find(node_id)
        if node is None:
            return "这一项已不存在（可能在别的窗口里被删了）"
        parent = self.find(ROOT_ID if parent_id is None else parent_id)
        if parent is None:
            return "目标分组已不存在"
        if parent["type"] != "group":
            return f"只能放到分组里，「{parent['name']}」是一条收藏"
        if parent["id"] == node_id or self.contains(node, parent["id"]):
            return "不能把分组放到它自己的里面（会形成环）"
        if self.depth_of(parent["id"]) + self.height_of(node) > MAX_DEPTH:
            return f"最多嵌套 {MAX_DEPTH} 层，这里放不下了"
        return ""

    def move(self, node_id, parent_id=None, index=None):
        """把一项移到某分组下；`index` 是**移出之后**那个列表里的目标位置（省略 = 末尾）

        侧边栏里的拖拽不走这里（它整棵重写），这里给测试与“移到其它分组”这类
        明确动作用一个能说清的口径。
        """
        reason = self.can_place(node_id, parent_id)
        if reason:
            raise BookmarkError(reason)
        node = self.find(node_id)
        parent = self.find(ROOT_ID if parent_id is None else parent_id)
        old_parent = self.parent_of(node_id)
        old_parent["children"].remove(node)
        parent["children"].insert(_clamp(index, len(parent["children"])), node)

    def _take_id(self) -> int:
        node_id = self._next_id
        self._next_id += 1
        return node_id

    # ---------------------------------------------------------------- 盘

    def serialize(self) -> dict:
        return {"version": FORMAT_VERSION,
                "children": [self._serialize_node(c) for c in self.root["children"]]}

    def _serialize_node(self, node) -> dict:
        if node["type"] == "link":
            return {"id": node["id"], "type": "link",
                    "name": node["name"], "path": node["path"]}
        return {"id": node["id"], "type": "group", "name": node["name"],
                "expanded": bool(node.get("expanded", True)),
                "children": [self._serialize_node(c) for c in node["children"]]}

    def save(self) -> tuple:
        """写盘。返回 `(是否成功, 说明文本)` —— 写失败要让界面说得清楚，不抛"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.serialize(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("收藏夹写入失败 %s: %s", self.config_file, e)
            return False, str(e)
        self.migrated = False
        return True, ""

    def export_file(self, filepath: str) -> tuple:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.serialize(), f, ensure_ascii=False, indent=2)
            return True, ""
        except OSError as e:
            return False, str(e)

    def import_file(self, filepath: str, parent_id=None) -> tuple:
        """并入一个收藏夹文件（同路径的跳过，不造重复项）

        返回 `(added, skipped, 错误文本)`；导入失败绝不清空现有的树。
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return 0, 0, f"读取失败：{e}"
        nodes, _migrated = self._coerce_file(raw)
        parent = self._require_group(parent_id, action="导入到")
        if not nodes:
            return 0, 0, "文件里没有可用的收藏"
        # 两道护栏与界面上新增时同一套：导入不能绕过上限
        if self.count() + sum(self._count(n) for n in nodes) > MAX_ITEMS:
            return 0, 0, f"导入后会超过 {MAX_ITEMS} 条上限，先删一些"
        tallest = max(self.height_of(n) for n in nodes)
        if self.depth_of(parent["id"]) + tallest > MAX_DEPTH:
            return 0, 0, f"导入的层级超过 {MAX_DEPTH} 层，放不进这个分组"
        have = {os.path.normcase(lk["path"]) for lk in self.links()}
        kept, added, skipped = self._merge(nodes, have)
        parent["children"].extend(kept)
        if added:
            self.save()
        return added, skipped, ""

    def _merge(self, nodes, have) -> tuple:
        """解析出来的节点 → （要挂上去的列表, 新增数, 跳过数）；id 在这里统一分配

        不回写 `nodes` 而是返一个新列表：分组的孩子就住在 `node["children"]` 里，一边
        遍历它一边往它里面追加会把子项翻倍，而被判重复的那条也会留在原处 —— 两处
        都是“看起来导入成功、一存盘就炸”。
        """
        kept, added, skipped = [], 0, 0
        for node in nodes:
            node["id"] = self._take_id()
            if node["type"] == "link":
                key = os.path.normcase(node["path"])
                if key in have:
                    skipped += 1
                    continue
                have.add(key)
                added += 1
            else:
                children, inner_added, inner_skipped = self._merge(node["children"], have)
                node["children"] = children
                added += 1 + inner_added
                skipped += inner_skipped
            kept.append(node)
        return kept, added, skipped


def _clamp(index, length: int) -> int:
    if index is None:
        return length
    return max(0, min(int(index), length))
