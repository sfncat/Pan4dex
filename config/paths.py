# -*- coding: utf-8 -*-
"""用户级配置目录 —— JSON 存储的统一落点。

文件关联（`associations.json`）与已保存搜索（`saved_searches.json`）必须落在同一个
地方，所以这条规则只写在这一个函数里；`FileAssociations` 也改为向它委托（此前它自己
算了一份，再加一类存储就会出现两处各自演化的路径规则）。
"""
import os
import sys


APP_DIR_NAME = "pan4dex"


def default_config_dir() -> str:
    """Windows：`%APPDATA%\\pan4dex`；其它平台：`~/.config/pan4dex`。

    具体算式照搬原先 `FileAssociations._get_default_config_dir()`（含用 `Path.home()`
    而不是 `expanduser`）：规则本身不值得改，改了就等于让老用户的配置“搬家”。
    """
    from pathlib import Path
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", ""), APP_DIR_NAME)
    return os.path.join(str(Path.home()), ".config", APP_DIR_NAME)
