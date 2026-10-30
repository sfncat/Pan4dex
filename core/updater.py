"""
Pan4dex 万格 — 客户端更新核心（检查 / 下载 / 校验 / 安装）

只依赖标准库与 `config.app_config`，**不 import Qt**：线程与对话框放在 UI 层
（`widgets/update_dialog.py`），这样整条更新链路可以在无 GUI 的环境里单测。

两个平台的安装形态不同，必须分开处理：

- Windows：PyInstaller onedir + zip（zip 顶层固定 `pan4dex/`）。运行中的 exe 不能
  被覆盖，所以生成一个 PowerShell 脚本，等本进程退出后再替换目录、重启、失败回滚。
- Linux：PyInstaller onefile。同目录 `.part` 下载 → 校验 → `os.replace` 原子替换
  （Linux 允许替换正在运行的可执行文件）→ 重启新进程。

设计细节与失败路径见 `docs/update.md` 第 5 节。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from config.app_config import VERSION

logger = logging.getLogger("pan4dex.updater")

DEFAULT_SERVER_URL = "http://192.168.5.230:23011"
LATEST_PATH = "/api/v1/latest"
PLATFORMS = ("windows", "linux")

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_CHUNK = 256 * 1024
_ELF_MAGIC = b"\x7fELF"
_UA = f"Pan4dex/{VERSION}"


class UpdateError(Exception):
    """更新链路的基础异常"""


class CheckError(UpdateError):
    """检查更新失败（网络 / 服务器 / 数据格式）"""


class DownloadError(UpdateError):
    """下载失败"""


class DownloadCancelled(DownloadError):
    """用户取消下载"""


class IntegrityError(UpdateError):
    """大小或 SHA-256 不匹配"""


class InstallError(UpdateError):
    """安装准备或安装执行失败"""


@dataclass(frozen=True)
class UpdateInfo:
    """服务器返回的一个可用版本"""

    platform: str
    version: str
    filename: str
    size: int
    sha256: str
    download_url: str
    notes: str = ""
    published_at: str = ""


# --------------------------------------------------------------------- 版本


def current_platform() -> str:
    """客户端平台标识（与服务器 API 的 platform 取值一致）"""
    return "windows" if sys.platform == "win32" else "linux"


def parse_version(value: str) -> tuple[int, int, int]:
    """把 `x.y.z` 解析成整数元组；格式不对抛 ValueError"""
    match = _VERSION_RE.match(str(value).strip())
    if not match:
        raise ValueError(f"版本号格式不合法: {value!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_newer(remote: str, local: str) -> bool:
    """远端版本是否比本地新（相等或更旧都不算）"""
    return parse_version(remote) > parse_version(local)


def normalize_server_url(url: str) -> str:
    """校验并规范化服务器根地址（去掉末尾斜杠）"""
    url = (url or "").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("更新服务器地址必须是 http:// 或 https:// 开头的完整地址")
    return url.rstrip("/")


# --------------------------------------------------------------------- 检查


def _http_get(url: str, timeout: float):
    request = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    return urllib.request.urlopen(request, timeout=timeout)


def _read_json(url: str, timeout: float) -> dict:
    try:
        with _http_get(url, timeout) as response:
            raw = response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        # 服务器用 404 + {"error": "no_release"} 表达「该平台还没有版本」，
        # 错误体仍是 JSON，交给调用方按 error 字段判断
        try:
            raw = exc.read(64 * 1024)
            data = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise CheckError(f"更新服务器返回 HTTP {exc.code}") from exc
        if isinstance(data, dict) and data.get("error"):
            return data
        raise CheckError(f"更新服务器返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise CheckError(f"无法连接更新服务器: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckError("更新服务器返回的数据不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise CheckError("更新服务器返回的数据格式不对")
    return data


def parse_update_info(payload: dict, base_url: str) -> UpdateInfo:
    """校验 `/api/v1/latest` 的字段并组装 `UpdateInfo`"""
    platform = str(payload.get("platform") or "")
    if platform not in PLATFORMS:
        raise CheckError(f"更新数据里的平台不合法: {platform!r}")
    version = str(payload.get("version") or "")
    try:
        parse_version(version)
    except ValueError as exc:
        raise CheckError(f"更新数据里的版本号不合法: {version!r}") from exc
    sha256 = str(payload.get("sha256") or "")
    if not _SHA256_RE.match(sha256):
        raise CheckError("更新数据里的 SHA-256 不合法")
    try:
        size = int(payload.get("size") or 0)
    except (TypeError, ValueError) as exc:
        raise CheckError("更新数据里的大小不合法") from exc
    if size <= 0:
        raise CheckError("更新数据里的大小必须大于 0")
    filename = str(payload.get("filename") or "")
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        raise CheckError("更新数据里的文件名不合法")
    download_url = str(payload.get("download_url") or "")
    if not download_url:
        raise CheckError("更新数据里缺少下载地址")
    # 服务器可能返回相对路径（反向代理场景），按服务器根地址补全
    download_url = urllib.parse.urljoin(base_url + "/", download_url)
    return UpdateInfo(
        platform=platform,
        version=version,
        filename=filename,
        size=size,
        sha256=sha256.lower(),
        download_url=download_url,
        notes=str(payload.get("notes") or ""),
        published_at=str(payload.get("published_at") or ""),
    )


def check_for_update(server_url: str | None = None,
                     current_version: str = VERSION,
                     platform: str | None = None,
                     timeout: float = 15.0) -> UpdateInfo | None:
    """查询服务器最新版本；没有新版本（含服务器上没有该平台产物）返回 None"""
    base_url = normalize_server_url(server_url or DEFAULT_SERVER_URL)
    target_platform = platform or current_platform()
    if target_platform not in PLATFORMS:
        raise ValueError(f"不支持的平台: {target_platform!r}")
    url = f"{base_url}{LATEST_PATH}?platform={urllib.parse.quote(target_platform)}"
    payload = _read_json(url, timeout)
    if payload.get("error"):
        if payload.get("error") == "no_release":
            return None
        raise CheckError(str(payload.get("message") or payload.get("error")))
    info = parse_update_info(payload, base_url)
    if not is_newer(info.version, current_version):
        return None
    return info


# --------------------------------------------------------------------- 下载


def default_download_dir() -> Path:
    """临时下载目录（Windows 用 LOCALAPPDATA，Linux 用 XDG cache）"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "pan4dex" / "updates"
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "pan4dex" / "updates"


def _emit_progress(progress, done: int, total: int) -> None:
    if progress is None:
        return
    try:
        progress(done, total)
    except Exception:      # UI 已销毁等：下载继续，别让回调拖垮安装
        logger.debug("更新进度回调异常", exc_info=True)


def download_update(info: UpdateInfo,
                    dest_dir: Path | str | None = None,
                    progress=None,
                    cancel: threading.Event | None = None,
                    timeout: float = 60.0) -> Path:
    """下载并校验产物，返回最终文件路径。

    - 先写 `<文件名>.part`，大小与 SHA-256 都匹配才改名；任何失败都清理 `.part`；
    - `progress(downloaded, total)` 在调用线程（通常是后台线程）里回调；
    - `cancel` 置位后抛 `DownloadCancelled`。
    """
    dest = Path(dest_dir) if dest_dir else default_download_dir()
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / info.filename
    part = dest / (info.filename + ".part")
    if part.exists():
        part.unlink()
    hasher = hashlib.sha256()
    downloaded = 0
    request = urllib.request.Request(
        info.download_url, headers={"User-Agent": _UA, "Accept": "*/*"})
    try:
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"下载失败：HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DownloadError(f"下载失败：{exc}") from exc
        with response, open(part, "wb") as handle:
            total = int(response.headers.get("Content-Length") or info.size)
            total = total if total > 0 else info.size
            while True:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled("下载已取消")
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)
                if downloaded > max(info.size * 2, info.size + 16 * 1024 * 1024):
                    raise IntegrityError("下载内容超过服务器声明的大小，已中止")
                _emit_progress(progress, downloaded, total)
        if downloaded != info.size:
            raise IntegrityError(
                f"下载大小不符：期望 {info.size} 字节，实际 {downloaded} 字节")
        if hasher.hexdigest() != info.sha256:
            raise IntegrityError("SHA-256 校验不通过，更新包可能已损坏")
        _emit_progress(progress, downloaded, downloaded)
        os.replace(part, final)
        return final
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise


def verify_local_file(path: Path | str, info: UpdateInfo) -> bool:
    """本地已下载的文件是否与服务器声明的一致（供「稍后安装」复用）"""
    target = Path(path)
    try:
        if target.stat().st_size != info.size:
            return False
        hasher = hashlib.sha256()
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                hasher.update(chunk)
        return hasher.hexdigest() == info.sha256
    except OSError:
        return False


# ------------------------------------------------------------------ 安装环境


def can_install() -> bool:
    """源码运行模式（未打包）不允许自替换，避免开发机被更新流程改掉"""
    return bool(getattr(sys, "frozen", False)) and sys.platform in ("win32", "linux")


def windows_install_dir() -> Path:
    """Windows 安装目录 = 当前 exe 所在目录"""
    return Path(sys.executable).resolve().parent


def linux_target() -> Path:
    """Linux 目标 = 当前可执行文件的真实路径（onefile 本体）"""
    return Path(os.path.realpath(sys.executable))


def can_write_dir(path: Path | str) -> bool:
    """真实探测目录写权限（`os.access` 在 Windows 上看 ACL 不可靠）"""
    directory = Path(path)
    if not directory.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".pan4dex-w-", delete=True):
            return True
    except OSError:
        return False


def launch_detached(path: Path | str) -> subprocess.Popen:
    """脱离当前进程启动新版本（不继承控制台/管道）"""
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen([str(path)], **kwargs)


# ------------------------------------------------------------- Windows 安装器

_PS_SCRIPT = r"""$ErrorActionPreference = 'Stop'
$job = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'job.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$log = $job.log_path

function Write-Log([string]$Message) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

$backup = '{0}.bak-{1}' -f $job.target_dir, $job.old_version
$extract = Join-Path $job.work_dir 'extract'
$started = $false

try {
    Write-Log ('等待旧进程退出 pid={0}' -f $job.pid)
    $proc = Get-Process -Id $job.pid -ErrorAction SilentlyContinue
    if ($proc -and (-not $proc.WaitForExit(15000))) {
        # 界面已提示「当前窗口会关闭」：宽限 15 秒后强杀，避免旧进程卡住
        # 导致 120 秒超时后替换失败回滚
        Write-Log ('宽限超时，强制结束旧进程 pid={0}' -f $job.pid)
        Stop-Process -Id $job.pid -Force -ErrorAction SilentlyContinue
        $proc.WaitForExit(10000) | Out-Null
    }

    Write-Log ('解压 {0}' -f $job.zip_path)
    if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $job.zip_path -DestinationPath $extract -Force
    $newDir = Join-Path $extract 'pan4dex'
    if (-not (Test-Path -LiteralPath (Join-Path $newDir 'pan4dex.exe'))) {
        throw '解压结果里没有 pan4dex\pan4dex.exe'
    }

    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
    Write-Log ('备份旧目录到 {0}' -f $backup)
    Move-Item -LiteralPath $job.target_dir -Destination $backup
    Move-Item -LiteralPath $newDir -Destination $job.target_dir

    $marker = Join-Path $job.target_dir 'update-ok.json'
    @{ version = $job.new_version; previous = $job.old_version; backup = $backup;
       time = (Get-Date).ToString('s') } |
        ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8

    Write-Log ('已安装 {0}，启动新版本' -f $job.new_version)
    Start-Process -FilePath $job.exe_path -WorkingDirectory $job.target_dir
    $started = $true
    Start-Sleep -Seconds 2
    Remove-Item -LiteralPath $job.zip_path -Force -ErrorAction SilentlyContinue
    Write-Log '完成'
} catch {
    Write-Log ('失败：{0}' -f $_.Exception.Message)
    if ((Test-Path -LiteralPath $backup) -and (-not $started)) {
        if (Test-Path -LiteralPath $job.target_dir) {
            Remove-Item -LiteralPath $job.target_dir -Recurse -Force
        }
        Move-Item -LiteralPath $backup -Destination $job.target_dir
        Write-Log '已回滚旧版本目录'
    }
    exit 1
}
"""


def validate_windows_zip(zip_path: Path | str) -> None:
    """安装前预检 zip：全部条目位于 `pan4dex/` 下、无穿越、包含 pan4dex.exe"""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise InstallError(f"更新包不是有效的 zip: {exc}") from exc
    if not names:
        raise InstallError("更新包是空的")
    for name in names:
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts:
            raise InstallError(f"更新包含非法路径: {name}")
        if not pure.parts or pure.parts[0] != "pan4dex":
            raise InstallError(f"更新包结构不对（顶层必须是 pan4dex/）: {name}")
    if "pan4dex/pan4dex.exe" not in names:
        raise InstallError("更新包里没有 pan4dex/pan4dex.exe")


def prepare_windows_install(zip_path: Path | str,
                            new_version: str,
                            current_version: str = VERSION,
                            target_dir: Path | str | None = None) -> tuple[Path, dict]:
    """生成安装脚本与 job.json，返回 (脚本路径, 作业信息)；不启动脚本"""
    target = Path(target_dir).resolve() if target_dir else windows_install_dir()
    if not target.is_dir():
        raise InstallError(f"安装目录不存在: {target}")
    exe_path = target / "pan4dex.exe"
    if not exe_path.is_file():
        raise InstallError(f"安装目录里没有 pan4dex.exe: {target}")
    if not can_write_dir(target):
        raise InstallError(f"安装目录不可写，无法自动更新: {target}")
    validate_windows_zip(zip_path)

    work_dir = Path(tempfile.mkdtemp(prefix="pan4dex-update-"))
    job = {
        "pid": os.getpid(),
        "zip_path": str(Path(zip_path).resolve()),
        "target_dir": str(target),
        "exe_path": str(exe_path),
        "old_version": current_version,
        "new_version": new_version,
        "work_dir": str(work_dir),
        "log_path": str(work_dir / "apply-update.log"),
    }
    (work_dir / "job.json").write_text(
        json.dumps(job, ensure_ascii=False), encoding="utf-8")
    # PowerShell 5.1 没有 BOM 时按 ANSI 读脚本，中文路径会变乱码
    script = work_dir / "apply-update.ps1"
    script.write_text(_PS_SCRIPT, encoding="utf-8-sig")
    return script, job


def _powershell_exe() -> str:
    if sys.platform == "win32":
        default = Path(os.environ.get("SystemRoot", r"C:\Windows")) / \
            "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if default.is_file():
            return str(default)
    found = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not found:
        raise InstallError("找不到 PowerShell，无法自动安装")
    return found


def launch_windows_installer(script: Path | str) -> subprocess.Popen:
    """启动安装脚本（隐藏窗口、脱离当前进程），调用方随后应退出应用"""
    powershell = _powershell_exe()
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", str(script)],
        **kwargs)


# --------------------------------------------------------------- Linux 安装器


def validate_linux_elf(path: Path | str) -> None:
    """预检 ELF 头：x86-64 / 小端，防止把错误文件替换成主程序"""
    try:
        with open(path, "rb") as handle:
            header = handle.read(20)
    except OSError as exc:
        raise InstallError(f"无法读取更新文件: {exc}") from exc
    if len(header) < 20 or header[:4] != _ELF_MAGIC:
        raise InstallError("更新文件不是 ELF 可执行文件")
    if header[4] != 2 or header[5] != 1:
        raise InstallError("更新文件不是 64 位小端 ELF")
    if int.from_bytes(header[18:20], "little") != 62:
        raise InstallError("更新文件不是 x86-64 架构")


def linux_manual_command(downloaded: Path | str, target: Path | str | None = None) -> str:
    """目标目录不可写时给用户的手动安装命令"""
    dest = Path(target) if target else linux_target()
    return f"sudo install -m 755 {Path(downloaded).name} {dest}"


def apply_linux_update(downloaded: Path | str,
                       target: Path | str | None = None,
                       launch: bool = True) -> Path:
    """把下载好的 ELF 原子替换到目标路径并（默认）启动新版本，返回目标路径"""
    source = Path(downloaded)
    dest = Path(target) if target else linux_target()
    if not source.is_file():
        raise InstallError(f"更新文件不存在: {source}")
    if not dest.is_file():
        raise InstallError(f"当前可执行文件不存在: {dest}")
    if not can_write_dir(dest.parent):
        raise InstallError(f"安装目录不可写: {dest.parent}")
    validate_linux_elf(source)
    try:
        os.chmod(source, 0o755)
        os.replace(source, dest)
    except OSError as exc:
        raise InstallError(f"替换可执行文件失败: {exc}") from exc
    if launch:
        launch_detached(dest)
    return dest


# ------------------------------------------------------------ 安装后清理


def cleanup_after_update(current_version: str = VERSION) -> None:
    """Windows 新版本启动后删除旧目录备份与标记文件；版本不符时保留备份"""
    if sys.platform != "win32":
        return
    install_dir = windows_install_dir()
    marker = install_dir / "update-ok.json"
    if not marker.is_file():
        return
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("update-ok.json 读取失败，保留备份目录")
        return
    if str(data.get("version") or "") != current_version:
        logger.info("更新标记版本 %s 与当前 %s 不符，保留备份",
                    data.get("version"), current_version)
        return
    backup = Path(str(data.get("backup") or ""))
    if backup.is_dir() and backup.parent == install_dir.parent:
        shutil.rmtree(backup, ignore_errors=True)
        logger.info("已清理旧版本备份: %s", backup)
    try:
        marker.unlink()
    except OSError:
        pass
