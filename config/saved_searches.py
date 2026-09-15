# -*- coding: utf-8 -*-
"""Pan4dex 万格 — 已保存的搜索条件（清单 20.4）

把一组搜索条件按名字存下来供后续复用。存储的是**喂给 `SearchWorker` 的那份 params**
（字节数、扩展名列表都是最终值），所以「保存的条件」与「真正会执行的条件」必然一致 ——
不会出现存的是界面上的 `1`（MB 下拉）、执行时按另一种单位算的情况。

一条记录长这样：

    {"名字": {"params": {...}, "updated": "2026-09-15 23:58"}}

三条约束：
- 文件名 JSON 读坏了就当空表（老版本 / 手工编辑过 / 上次写到一半断电），
  不抛异常 —— 这只影响「有没有历史条件可载入」，不该把搜索对话框一起弄坏
- 同名即覆盖，覆盖由调用方先问用户（本模块不猜意图）
- 只存条件，**不存结果**：结果列表一打开就该是新的（文件早就变了）
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from config.paths import default_config_dir

logger = logging.getLogger("pan4dex.saved_searches")

MAX_ENTRIES = 50                 # 上限：几十条以后，下拉本身就没人看了
MAX_NAME_LEN = 60


class SavedSearchStore:
    """已保存搜索的读写（JSON 单文件，与 `associations.json` 同一目录）"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = default_config_dir()
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "saved_searches.json")
        self.entries: dict = {}
        try:
            os.makedirs(self.config_dir, exist_ok=True)
        except OSError as e:
            logger.warning("创建已保存搜索目录失败 %s: %s", self.config_dir, e)
        self.load()

    # ---------- 读写 ----------

    def load(self):
        self.entries = {}
        if not os.path.exists(self.config_file):
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("已保存搜索读取失败，按空表处理 %s: %s", self.config_file, e)
            return
        if not isinstance(raw, dict):
            return
        for name, item in raw.items():
            # 逐条校验：一条坏记录不该带走其余的
            params = item.get("params") if isinstance(item, dict) else None
            if isinstance(name, str) and name.strip() and isinstance(params, dict):
                self.entries[name] = {
                    "params": params,
                    "updated": (item.get("updated") or "") if isinstance(item, dict) else "",
                }

    def save(self) -> tuple:
        """写盘。返回 (是否成功, 说明文本) —— 写失败必须让调用方能在界面上说清楚"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
            return True, ""
        except OSError as e:
            logger.warning("已保存搜索写入失败 %s: %s", self.config_file, e)
            return False, str(e)

    # ---------- 查询 ----------

    def names(self) -> list:
        """按名字排序（下拉里顺序稳定，不会每次打开换个样子）"""
        return sorted(self.entries, key=lambda s: s.casefold())

    def get(self, name: str):
        item = self.entries.get(name)
        return dict(item["params"]) if item else None

    def updated(self, name: str) -> str:
        item = self.entries.get(name)
        return item["updated"] if item else ""

    # ---------- 修改 ----------

    def save_search(self, name: str, params: dict) -> tuple:
        """存一条（同名覆盖）。返回 (是否成功, 说明文本)"""
        name = (name or "").strip()
        if not name:
            return False, "名字不能为空"
        if len(name) > MAX_NAME_LEN:
            return False, f"名字太长（最多 {MAX_NAME_LEN} 个字符）"
        if not isinstance(params, dict) or not params:
            return False, "没有可保存的条件"
        if name not in self.entries and len(self.entries) >= MAX_ENTRIES:
            return False, f"已有 {MAX_ENTRIES} 条，请先删除不再使用的"
        params = json.loads(json.dumps(params, ensure_ascii=False, default=str))
        self.entries[name] = {
            "params": params,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.save()

    def remove(self, name: str) -> bool:
        if name not in self.entries:
            return False
        del self.entries[name]
        ok, _err = self.save()
        return ok
