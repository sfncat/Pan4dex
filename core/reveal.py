# -*- coding: utf-8 -*-
"""在系统文件管理器里定位（选中）文件 —— 全仓唯一一份实现。

窗格右键「在系统文件管理器中显示」与高级搜索右键「定位」都转调这里，调用方只决定
写哪个状态栏。纯执行层：不认识窗格、不弹窗（把异常咽进模态框会让测试永久挂住，
gotchas #56），失败只返回结果 + 记日志。

真机记录：231 上 Nautilus 46.4 与 Thunar 4.18.8 的选中效果已验；其它平台/管理器见
`docs/gotchas.md` #71、#74、#75。
"""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger("pan4dex.reveal")

REVEAL_LIMIT = 5      # 一次最多定位几个（一人开十个窗口是灾难）

# PATH 里常见文件管理器；第二项是额外的「选中该文件」参数。
# Thunar 直接接收文件路径即可选中，不需要额外参数。
_LINUX_FILE_MANAGERS = (
    ("nautilus", ("--select",)),
    ("dolphin", ("--select",)),
    ("nemo", ("--select",)),
    ("caja", ("--select",)),
    ("pcmanfm", ("--select",)),
    ("thunar", ()),
)


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
    """Linux：必须落到真实文件管理器，绝不把目录扔给 xdg-open 的 MIME 默认程序。

    旧实现只认 KDE/GNOME，桌面环境没识别出来（XFCE/LXDE/精简桌面/SSH 会话）
    就回落 `xdg-open 父目录`——本机实测这条会把 `inode/directory` 交给浏览器，
    于是「在文件管理器中显示」变成开浏览器。现在按三层挑：

    1. 桌面环境精确匹配（KDE→dolphin、GNOME→nautilus、XFCE→thunar，保留原行为）；
    2. 不管桌面环境写什么，按 PATH 探测 _LINUX_FILE_MANAGERS 里真实存在的一个；
    3. 都不在 PATH（如 Flatpak 版）走 freedesktop 标准 D-Bus ShowItems。

    只有三层全空才退回 xdg-open，且明说 `selected=False`（只打开、未选中）。
    """
    desktop = (os.environ.get('XDG_CURRENT_DESKTOP') or '').upper()
    if ('KDE' in desktop or os.environ.get('KDE_FULL_SESSION')) and shutil.which('dolphin'):
        return ['dolphin', '--select', norm], True
    if 'GNOME' in desktop and shutil.which('nautilus'):
        return ['nautilus', '--select', norm], True
    if 'XFCE' in desktop and shutil.which('thunar'):
        return ['thunar', norm], True

    # 桌面环境变量不可信/没设：按可执行文件本身挑，不再走 xdg-open
    for name, select_args in _LINUX_FILE_MANAGERS:
        if shutil.which(name):
            return [name, *select_args, norm], name == 'thunar' or bool(select_args)

    # 文件管理器不在 PATH：让正在运行的 FM 通过标准接口自己高亮
    if shutil.which('gdbus'):
        try:
            uri = Path(norm).absolute().as_uri()
            return [
                'gdbus', 'call', '--session',
                '--dest', 'org.freedesktop.FileManager1',
                '--object-path', '/org/freedesktop/FileManager1',
                '--method', 'org.freedesktop.FileManager1.ShowItems',
                json.dumps([uri]), '',
            ], True
        except (ValueError, OSError):
            pass

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
    popen_kwargs = {}
    if sys.platform == 'linux':
        env = os.environ.copy()
        bundle_dir = getattr(sys, '_MEIPASS', '')
        if bundle_dir and env.get('LD_LIBRARY_PATH'):
            # 外部 GTK 程序不能继承 onefile 的私有 GLib，否则会 symbol lookup error。
            bundle_dir = os.path.normpath(bundle_dir)
            entries = [p for p in env['LD_LIBRARY_PATH'].split(':')
                       if os.path.normpath(p) != bundle_dir]
            if entries:
                env['LD_LIBRARY_PATH'] = ':'.join(entries)
            else:
                env.pop('LD_LIBRARY_PATH')
        popen_kwargs['env'] = env
    for p in paths[:limit]:
        argv, can_select = _argv_for(os.path.normpath(p))
        selected = selected and can_select
        try:
            subprocess.Popen(argv, **popen_kwargs)
            opened += 1
        except OSError as e:
            failed += 1
            error = error or str(e)
            logger.warning("定位 %s 失败: %s", p, e)
    return RevealResult(opened, failed, selected, error)