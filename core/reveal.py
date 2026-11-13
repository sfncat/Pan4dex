# -*- coding: utf-8 -*-
"""在系统文件管理器里定位（选中）文件 —— 全仓唯一一份实现。

窗格右键「在系统文件管理器中显示」与高级搜索右键「定位」都转调这里，调用方只决定
写哪个状态栏。纯执行层：不认识窗格、不弹窗（把异常咽进模态框会让测试永久挂住，
gotchas #56），失败只返回结果 + 记日志。

**待真机实测**（本轮没有真的拉起文件管理器窗口，见 docs/improvement-plan-t6-t9.md §4.5）：
Windows 的 argv 形式能否选中带空格/UNC 路径、Linux 的 `dolphin --select` /
`nautilus --select` 能否高亮。参数按各桌面环境的公开用法拼，验完再回来改这一处。
"""
import logging
import os
import shutil
import subprocess
import sys
from typing import NamedTuple

logger = logging.getLogger("pan4dex.reveal")

REVEAL_LIMIT = 5      # 一次最多定位几个（一人开十个窗口是灾难）


class RevealResult(NamedTuple):
    opened: int       # 成功启动了几次
    failed: int       # 启动失败几次
    selected: bool    # False = 只打开了所在目录，没能选中（回落路径）
    error: str        # 第一条失败原因（供调用方写状态栏）


def win_unc_fix(norm: str) -> str:
    """统一分隔符为反斜杠，并补回单前导斜杠的 UNC 前缀。

    更正一条旧说法：本机实测 `os.path.normpath` **不会**压掉 UNC 的双前导反斜杠
    （Python 3.13 / Windows），所以这里真正还在做的是 `/` → `\\`（混合分隔符时有用）；
    补前缀那一支留着，防其它来源给出的单斜杠 UNC。
    """
    p = norm.replace('/', '\\')
    if not p.startswith('\\\\') and p.startswith('\\'):
        p = '\\' + p
    return p


def _linux_argv(norm: str):
    """Linux：挑能「选中」的文件管理器，挑不到再回落成只打开所在目录。

    回落是现状行为，但必须让调用方知道没选中（`selected=False`），别让用户以为
    文件已经高亮。D-Bus org.freedesktop.FileManager1.ShowItems 是更稳的备选，
    本轮未实测，验完再决定是否替换命令行方案。
    """
    desktop = (os.environ.get('XDG_CURRENT_DESKTOP') or '').upper()
    if ('KDE' in desktop or os.environ.get('KDE_FULL_SESSION')) and shutil.which('dolphin'):
        return ['dolphin', '--select', norm], True
    if 'GNOME' in desktop and shutil.which('nautilus'):
        return ['nautilus', '--select', norm], True
    return ['xdg-open', os.path.dirname(norm)], False


def _argv_for(norm: str):
    """返回 (argv, 能否选中)。一律 argv 列表，不经 shell：路径里的空格与特殊字符天然安全。"""
    if sys.platform == 'win32':
        return ['explorer', '/select,', win_unc_fix(norm)], True
    if sys.platform == 'darwin':
        return ['open', '-R', norm], True
    return _linux_argv(norm)


def reveal_in_file_manager(paths, limit: int = REVEAL_LIMIT) -> RevealResult:
    """逐个定位（最多 limit 个）。`paths` 可以是单个路径字符串或路径列表。

    不拿退出码判成败：Explorer 即使成功也常返回 1，而且这里根本不等待子进程。
    """
    if isinstance(paths, str):
        paths = [paths]
    paths = [p for p in paths if p]
    opened = failed = 0
    selected = True
    error = ""
    for p in paths[:limit]:
        argv, can_select = _argv_for(os.path.normpath(p))
        selected = selected and can_select
        try:
            subprocess.Popen(argv)
            opened += 1
        except OSError as e:
            failed += 1
            error = error or str(e)
            logger.warning("定位 %s 失败: %s", p, e)
    return RevealResult(opened, failed, selected, error)