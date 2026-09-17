# -*- coding: utf-8 -*-
"""Pan4dex 万格 — 「打开方式」：枚举本机可打开某类文件的应用并用它启动

数据来源是本机注册信息（Windows 注册表 / Linux `.desktop` / macOS `Info.plist`），
与被浏览的目录无关，所以不涉及 SMB 延时，也不产生目录模型那套行信号。

三条硬约束（本仓一贯做法）：
- **构造右键菜单时不枚举**：等子菜单真的要显示（`QMenu.aboutToShow`）才算。多数时候
  用户根本不展开这一层，白读一次注册表/盘是纯浪费
- 结果按扩展名做 TTL 缓存：连续对多个同类型文件右键不重复扫
- 任何一步失败都只是"少一项候选"，绝不向外抛异常 —— 右键菜单不能因为枚举失败而弹不出来

选择语义：菜单里的程序行 = **只这一次**用它打开（资源管理器习惯）；是否记住为默认由
调用方决定，落到 `config.file_associations.FileAssociations`（那是本仓唯一的关联存储）。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

logger = logging.getLogger("pan4dex.open_with")

MAX_ENTRIES = 15                 # 候选上限：注册表里同类型可能挂着几十项
CACHE_TTL = 300.0                # 秒；装/卸软件后最多 5 分钟就出现在列表里
FALLBACK_TOPUP_BELOW = 5         # 已枚举候选少于此数才补内置常用程序（两端同一规则）

# 命令行里的"文件位置"占位符（`%1` / `%L` / `%U` / `%*` …）。本模块一律剥掉它们并把
# 目标路径追加到末尾 —— 少数程序要求参数在前，那种情况由调用点不适用，实践中极少
_PLACEHOLDER_RE = re.compile(r"^%[0-9A-Za-z*]+$")


@dataclass(frozen=True)
class OpenWithApp:
    """一条候选：显示名 + 可执行文件 + 固定参数"""
    name: str
    exe: str
    args: tuple = field(default_factory=tuple)
    source: str = ""             # default / mru / progid / apppaths / desktop / mac

    def argv_for(self, file_path: str) -> list:
        argv = [self.exe]
        argv.extend(a for a in self.args if not _PLACEHOLDER_RE.match(a))
        argv.append(file_path)
        return argv


# ---------------------------------------------------------------- 公共入口

_cache: dict = {}                # ext -> (时间戳, [OpenWithApp])


def clear_cache():
    """清空候选缓存（测试与"刚装完软件想立刻看到"时用）"""
    _cache.clear()


def list_apps(file_path: str) -> list:
    """列出可打开 `file_path` 的应用，按「默认程序 → 最近用过 → 其它 → 常用」排序"""
    ext = os.path.splitext(file_path)[1].lower()
    now = time.monotonic()
    hit = _cache.get(ext)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]

    apps: list = []
    try:
        if sys.platform == "win32":
            apps = _list_windows(ext)
        elif sys.platform == "darwin":
            apps = _list_macos(ext)
        else:
            apps = _list_linux(ext, file_path)
    except Exception as e:                       # 枚举失败不影响菜单弹出
        logger.warning("枚举打开方式候选失败 %s: %s", ext, e)

    # 按 exe 去重（注册表里同一个程序常以 ProgID / Applications / App Paths 三种身份出现）
    uniq, seen = [], set()
    for app in apps:
        key = (app.exe or "").lower().strip('"')
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(app)
    result = uniq[:MAX_ENTRIES]
    _cache[ext] = (now, result)
    return result


def launch(app: OpenWithApp, file_path: str) -> tuple:
    """用指定应用打开文件（不等待）。返回 (是否成功, 说明文本)"""
    from config.file_associations import _clean_child_env

    argv = app.argv_for(file_path)
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
            env=_clean_child_env(),
        )
        return True, ""
    except Exception as e:
        logger.warning("用 %s 打开 %s 失败: %s", app.exe, file_path, e)
        return False, str(e)


def has_system_dialog() -> bool:
    """是否有系统自带的「打开方式」对话框可用"""
    return sys.platform == "win32"


def open_system_dialog(file_path: str) -> bool:
    """调系统「打开方式」对话框（Windows：自带"始终"按钮，等价资源管理器完整入口）"""
    if sys.platform != "win32":
        return False
    try:
        subprocess.Popen(
            ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", os.path.normpath(file_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=False,
        )
        return True
    except Exception as e:
        logger.warning("调系统打开方式对话框失败 %s: %s", file_path, e)
        return False


# ---------------------------------------------------------------- Windows

try:                                        # 非 Windows 上根本没有这个模块
    import winreg
except ImportError:                         # pragma: no cover - 仅非 win 平台
    winreg = None


def _win_read(root, subkey, value_name=None):
    """读一个注册表值；任何失败返回 None（键不存在是常态，不是错误）"""
    try:
        with winreg.OpenKey(root, subkey) as key:
            if value_name is None:
                return winreg.QueryValue(key, None)
            return winreg.QueryValueEx(key, value_name)[0]
    except OSError:
        return None


def _win_expand(cmd: str) -> str:
    """展开 `%SystemRoot%` 这类环境变量（注册表命令串里很常见）"""
    return os.path.expandvars(cmd or "").strip()


def split_command_line(cmdline: str) -> list:
    r"""按 Windows 命令行规则切分（引号内的空格不断开，`""` 为字面引号）

    注册表里的 open command 长这样，切错了就没法把 exe 与参数分开：
      `"C:\Program Files\App\app.exe" "%1"`、`%SystemRoot%\system32\notepad.exe %1`
    """
    parts, buf, quoted = [], [], False
    i, n = 0, len(cmdline or "")
    while i < n:
        ch = cmdline[i]
        if ch == '"':
            if quoted and i + 1 < n and cmdline[i + 1] == '"':   # "" → 字面引号
                buf.append('"')
                i += 2
                continue
            quoted = not quoted
        elif ch == " " and not quoted:
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf))
    return parts


def _win_app_paths(exe_name: str):
    r"""`App Paths\<exe>` → 完整 exe 路径（HKLM 与 HKCU 都查）"""
    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        path = _win_read(root, f"{base}\\{exe_name}")
        if path:
            return _win_expand(path).strip('"')
    return None


def _win_command_for(progid: str):
    r"""ProgID → `shell\open\command` 命令行（HKCR 与 HKCU\Software\Classes 都查）"""
    if winreg is None:
        return None
    for root in (winreg.HKEY_CLASSES_ROOT, winreg.HKEY_CURRENT_USER):
        cmd = _win_read(root, f"{progid}\\shell\\open\\command")
        if cmd:
            return _win_expand(cmd)
    return None


def _win_name_for(progid: str, exe_path: str):
    r"""ProgID + 已解析出的 exe → 候选项的显示名

    **不能**用 `HKCR\<progid>` 的默认值：那是**文档类型**的描述（“Text Source File”、
    “Markdown Source File”），同一类型挂在三个不同 IDE 上就会显示三个同名项，
    用户无从选起（实测就是这样）。

    只认 `<progid>\Application\ApplicationName`（WinRAR、Chrome 等确实写了它），
    其值是路径或 MUI 引用（`@C:\...,-1234`）时回退到 exe 文件名；都没有也用 exe 文件名。
    """
    stem = _exe_stem(exe_path)
    if winreg is None:
        return stem
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_CLASSES_ROOT):
        raw = _win_read(root, rf"{progid}\Application\ApplicationName")
        if not raw:
            continue
        value = _win_expand(raw).strip('"')
        if os.path.isabs(value) or "%" in value or value.startswith("@"):
            return _exe_stem(value) if os.path.isabs(value) else stem
        value = value.strip()
        if value:
            return value
    return stem


def _exe_stem(exe_path: str) -> str:
    """exe 完整路径 → 文件名去扩展名（候选项的默认显示名）"""
    return os.path.splitext(os.path.basename(exe_path or ""))[0] or (exe_path or "")


def _win_app_from_command(cmdline: str, source: str, progid: str = None):
    """open command 命令行 → 候选项（可执行文件不存在则丢弃）

    显示名要等 exe 解析出来才能定（见 `_win_name_for`），所以这里一并处理。
    """
    parts = split_command_line(cmdline)
    if not parts:
        return None
    exe = parts[0].strip('"')
    # 展开后仍带 `%...%` 的（注册表里的 `ProgramFiles(x86)` 这类）当不可用
    if "%" in exe and not os.path.exists(exe):
        return None
    if not os.path.exists(exe):
        return None
    name = _win_name_for(progid, exe) if progid else _exe_stem(exe)
    return OpenWithApp(name=name, exe=exe, args=tuple(parts[1:]), source=source)


def _win_mru_exts(ext: str) -> list:
    r"""`FileExts\<ext>\OpenWithList` 的最近使用列表（按 `MRUList` 给的顺序）"""
    if winreg is None:
        return []
    base = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\OpenWithList"
    letters = _win_read(winreg.HKEY_CURRENT_USER, base, "MRUList") or ""
    apps = []
    for letter in letters:                       # "DCB" 之类，越靠前越近
        exe_name = _win_read(winreg.HKEY_CURRENT_USER, base, letter)
        if not exe_name:
            continue
        full = _win_app_paths(exe_name)
        if full and os.path.exists(full):
            apps.append(OpenWithApp(name=_win_name_for_exe(exe_name),
                                    exe=full, source="mru"))
    return apps


def _win_name_for_exe(exe_name: str) -> str:
    """exe 名 → 显示名：优先 App Paths 的 `ApplicationName`，否则拿 exe 名去扩展名

    特意不用解析出来的完整路径里的文件名：NTFS 不区分大小写，同一个程序会从
    不同入口分别报成 `code` 与 `Code`，列表里就成了两项。
    """
    if winreg is None:
        return exe_name
    app = _win_read(winreg.HKEY_LOCAL_MACHINE,
                    rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
                    "ApplicationName")
    if app:
        return _win_expand(app)
    return os.path.splitext(os.path.basename(exe_name))[0] or exe_name


def _win_progids_under(root_key, subkey) -> list:
    """`OpenWithProgids` 键下所有值名（值名就是 ProgID）"""
    apps = []
    if winreg is None:
        return apps
    try:
        with winreg.OpenKey(root_key, subkey) as key:
            i = 0
            while True:
                try:
                    name, _value, _type = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if name:
                    apps.append(name)
    except OSError:
        pass
    return apps


def _list_windows(ext: str) -> list:
    if not ext or winreg is None:
        return []
    apps = []

    # 1) 当前默认程序
    progid = _win_read(winreg.HKEY_CLASSES_ROOT, ext)
    if progid:
        cmd = _win_command_for(progid)
        if cmd:
            app = _win_app_from_command(cmd, "default", progid)
            if app:
                apps.append(app)

    # 2) 最近用过的
    apps.extend(_win_mru_exts(ext))

    # 3) 声明支持该扩展名的 ProgID（HKCR\<ext>\OpenWithProgids + HKCU FileExts）
    progids = _win_progids_under(winreg.HKEY_CLASSES_ROOT, rf"{ext}\OpenWithProgids")
    progids += _win_progids_under(
        winreg.HKEY_CURRENT_USER,
        rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\OpenWithProgids")
    for pid in progids:
        cmd = _win_command_for(pid)
        if not cmd:
            continue
        app = _win_app_from_command(cmd, "progid", pid)
        if app:
            apps.append(app)

    # 4) 兜底：注册表这条链上候选太少时，按类型补几个常用程序
    #    （没装的自然被 App Paths 查不到而跳过）。不补到前几项里：那会把
    #    “画图/Word”挂到 .txt 上，反而比资源管理器多一堆不相干项。
    if needs_builtin_topup(len(apps)):
        for exe_name in _windows_fallback(ext):
            full = _win_app_paths(exe_name)
            if full and os.path.exists(full):
                apps.append(OpenWithApp(name=_win_name_for_exe(exe_name),
                                        exe=full, source="apppaths"))
    return apps


# 兜底候选：按文件大类给几个肯定能用、且本机常见装过的程序
_WINDOWS_FALLBACK = {
    "text": ("notepad.exe", "wordpad.exe", "notepad++.exe", "code.exe"),
    "image": ("mspaint.exe", "msedge.exe"),
    "web": ("msedge.exe", "chrome.exe", "firefox.exe"),
    "doc": ("winword.exe", "excel.exe", "powerpnt.exe", "notepad.exe"),
    "media": ("vlc.exe", "msedge.exe"),
    "archive": ("7zFM.exe", "notepad.exe"),
}
_FALLBACK_KIND_BY_EXT = {
    ".txt": "text", ".log": "text", ".md": "text", ".rst": "text", ".csv": "text",
    ".ini": "text", ".cfg": "text", ".conf": "text", ".json": "text", ".xml": "text",
    ".yml": "text", ".yaml": "text", ".toml": "text", ".srt": "text",
    ".py": "text", ".js": "text", ".ts": "text", ".sh": "text", ".bat": "text",
    ".ps1": "text", ".c": "text", ".h": "text", ".cpp": "text", ".java": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".webp": "image", ".svg": "image", ".ico": "image", ".tif": "image",
    ".htm": "web", ".html": "web", ".mht": "web",
    ".pdf": "doc", ".doc": "doc", ".docx": "doc", ".xls": "doc", ".xlsx": "doc",
    ".ppt": "doc", ".pptx": "doc", ".odt": "doc", ".rtf": "doc",
    ".mp3": "media", ".wav": "media", ".flac": "media", ".ogg": "media", ".m4a": "media",
    ".mp4": "media", ".mkv": "media", ".avi": "media", ".mov": "media", ".webm": "media",
    ".zip": "archive", ".rar": "archive", ".7z": "archive", ".tar": "archive",
    ".gz": "archive", ".bz2": "archive", ".xz": "archive",
}


def _windows_fallback(ext: str) -> tuple:
    """该扩展名的兜底候选（认不出的类型只给记事本/VS Code，不乱猜）"""
    kind = _FALLBACK_KIND_BY_EXT.get(ext)
    if not kind:
        return ("notepad.exe", "code.exe")
    return _WINDOWS_FALLBACK[kind]


def needs_builtin_topup(count: int) -> bool:
    """系统枚举出的候选太少时，才补内置常用程序

    两端必须同一条规则：Windows 上早就有这道门（`_list_windows` 第 4 步），Linux 上
    原来是**无条件**追加，结果在真机桌面环境里 `.desktop` 已经给出 gedit/mousepad 了
    还再补一串内置项，菜单比 Windows 多出一堆不相干条目（见 `docs/linux-gap.md`）。
    """
    return count < FALLBACK_TOPUP_BELOW


# ---------------------------------------------------------------- Linux

def _linux_data_dirs() -> list:
    dirs = []
    home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    dirs.append(home)
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs.extend(p for p in system.split(os.pathsep) if p)
    return [d for d in dirs if d]


def _parse_desktop_file(text: str) -> dict:
    """取 `[Desktop Entry]` 段的若干键（够用即可，不实现完整规范）"""
    out, in_section = {}, False
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("["):
            in_section = line.strip("[]").lower() == "desktop entry"
            continue
        if not in_section or "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _mime_matches(entry_mimes: str, want: str) -> bool:
    """`MimeType=text/plain;application/pdf` 与目标 MIME 比对，支持 `text/*` 通配"""
    if not want:
        return False
    for m in entry_mimes.split(";"):
        m = m.strip().rstrip(";")
        if not m:
            continue
        if m == want:
            return True
        if m.endswith("/*") and want.startswith(m[:-1]):
            return True
    return False


def _list_linux(ext: str, file_path: str) -> list:
    import mimetypes
    apps = []
    mime = mimetypes.guess_type(file_path)[0] or ""

    for base in _linux_data_dirs():
        app_dir = os.path.join(base, "applications")
        if not os.path.isdir(app_dir):
            continue
        try:
            names = sorted(os.listdir(app_dir))
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".desktop"):
                continue
            full = os.path.join(app_dir, fn)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    entry = _parse_desktop_file(f.read())
            except OSError:
                continue
            if entry.get("NoDisplay", "").lower() == "true" or \
               entry.get("Hidden", "").lower() == "true" or \
               entry.get("Type", "Application").lower() != "application":
                continue
            if not _mime_matches(entry.get("MimeType", ""), mime):
                continue
            exec_line = entry.get("Exec", "").strip()
            if not exec_line:
                continue
            argv = _desktop_exec_argv(exec_line)
            exe = shutil.which(argv[0]) or (argv[0] if os.path.isabs(argv[0]) else None)
            if not exe or not os.path.exists(exe):
                continue
            try:
                if not os.access(exe, os.X_OK):
                    continue
            except OSError:
                continue
            name = entry.get("Name") or os.path.splitext(fn)[0]
            apps.append(OpenWithApp(name=name, exe=exe,
                                    args=tuple(argv[1:]), source="desktop"))

    # 内置候选兜底（桌面集成缺失/没装 shared-mime-info 时仍然有东西可选）。
    # 与 Windows 同一道门：`.desktop` 已经给出足够候选就不再往下堆。
    from config.file_associations import _LINUX_APP_CANDIDATES
    if needs_builtin_topup(len(apps)):
        for exe_name in _LINUX_APP_CANDIDATES.get(ext, ()):
            exe = shutil.which(exe_name)
            if exe:
                apps.append(OpenWithApp(name=exe_name, exe=exe, source="builtin"))
    return apps


def _desktop_exec_argv(exec_line: str) -> list:
    """`Exec` 行 → argv：剥掉字段码（`%f` `%U` `%i` `%c` …）与 `--` 分隔"""
    parts = exec_line.split()
    argv = [p for p in parts if p != "--" and not re.fullmatch(r"%[a-zA-Z]", p)]
    return argv


# ---------------------------------------------------------------- macOS

def _list_macos(ext: str) -> list:
    """扫 `/Applications` 与 `/System/Applications`，按 `Info.plist` 的文档类型匹配

    只扫顶层（不递归），几十个 plist；有 TTL 缓存，且只在子菜单展开时执行。
    """
    import plistlib
    apps = []
    roots = ["/Applications", "/System/Applications",
             os.path.expanduser("~/Applications")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".app"):
                continue
            bundle = os.path.join(root, fn)
            plist = os.path.join(bundle, "Contents", "Info.plist")
            if not os.path.exists(plist):
                continue
            try:
                with open(plist, "rb") as f:
                    info = plistlib.load(f)
            except Exception:
                continue
            if not _mac_supports_ext(info, ext):
                continue
            name = info.get("CFBundleDisplayName") or info.get("CFBundleName") \
                or os.path.splitext(fn)[0]
            apps.append(OpenWithApp(name=str(name), exe="/usr/bin/open",
                                    args=("-a", bundle), source="mac"))
    return apps


def _mac_supports_ext(info: dict, ext: str) -> bool:
    if not ext:
        return False
    bare = ext.lstrip(".")
    for doc in info.get("CFBundleDocumentTypes") or []:
        if not isinstance(doc, dict):
            continue
        for item in (doc.get("CFBundleTypeExtensions") or []):
            if str(item).lower() in (bare, "*", "***"):
                return True
    return False
