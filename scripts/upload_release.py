#!/usr/bin/env python3
"""把构建产物上传到 Pan4dex 更新服务器（管理页同一条 /admin/upload 通道）。

构建脚本带 `-U` 时调用这里；也可以单独用：

    python scripts/upload_release.py --platform windows releases/pan4dex-1.9.028.zip

服务器地址读 `scripts/update_server.json`；管理口令按优先级取
环境变量 PAN4DEX_UPDATE_ADMIN_PASSWORD > `server/update-server/.env`
（与服务器同一份格式，已被 server/.gitignore 排除）> 交互输入。
口令只放在被 gitignore 的 .env 或环境变量里，不写入任何入库文件。
只用标准库，构建机不需要额外依赖。
"""
from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.cookiejar import CookieJar
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("update_server.json")
# 与更新服务器共用同一份 .env（server/.gitignore 已排除），口令不另存
DOTENV_PATH = Path(__file__).resolve().parent.parent / "server" / "update-server" / ".env"

DEFAULT_CONFIG = {
    "server_url": "http://192.168.5.230:23011",
    "notes_template": "Pan4dex {version} 自动构建",
    "timeout_seconds": 900,
    "replace": False,
}

_VERSION_RE = re.compile(r"pan4dex-(\d+\.\d+\.\d+)")
_CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def _utf8_console() -> None:
    """管道/重定向时按 ANSI 代码页编码，中文直接抛 UnicodeEncodeError"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


class UploadError(RuntimeError):
    """上传失败（登录、网络、服务器拒绝）"""


class AlreadyExists(UploadError):
    """服务器上同版本同平台已存在（需 --replace）"""


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.is_file():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise UploadError(f"配置文件读取失败 {CONFIG_PATH}: {exc}") from exc
    return config


def _read_dotenv(path: Path) -> dict:
    """读 KEY=VALUE 形式的 .env（支持注释、export、单双引号）"""
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _admin_password(config: dict) -> str:
    password = os.environ.get("PAN4DEX_UPDATE_ADMIN_PASSWORD", "").strip()
    if password:
        return password
    password = _read_dotenv(DOTENV_PATH).get("PAN4DEX_UPDATE_ADMIN_PASSWORD", "").strip()
    if password:
        return password
    if not sys.stdin or not sys.stdin.isatty():
        raise UploadError(
            "没有管理口令：请设置环境变量 PAN4DEX_UPDATE_ADMIN_PASSWORD，"
            f"或把 PAN4DEX_UPDATE_ADMIN_PASSWORD 写进 {DOTENV_PATH}")
    password = getpass.getpass("更新服务器管理口令: ")
    if not password:
        raise UploadError("管理口令为空")
    return password


def _csrf(text: str, where: str) -> str:
    match = _CSRF_RE.search(text)
    if not match:
        raise UploadError(f"{where} 页面没有 CSRF token（服务器版本不匹配？）")
    return match.group(1)


class Client:
    """带 cookie 的最小客户端：登录取 session，再上传"""

    def __init__(self, server_url: str, timeout: float):
        self.base = server_url.rstrip("/")
        if not self.base.startswith(("http://", "https://")):
            raise UploadError(f"更新服务器地址不合法: {server_url}")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()))

    def _get(self, path: str) -> str:
        with self.opener.open(f"{self.base}{path}", timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _post_form(self, path: str, data: dict) -> str:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base}{path}", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.opener.open(request, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def login(self, password: str) -> None:
        token = _csrf(self._get("/admin/login"), "登录")
        try:
            body = self._post_form(
                "/admin/login", {"csrf_token": token, "password": password})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                raise UploadError("管理口令不正确") from exc
            if exc.code == 429:
                raise UploadError("登录失败次数过多，服务器已临时锁定") from exc
            raise UploadError(f"登录失败 HTTP {exc.code}: {detail[:200]}") from exc
        if 'name="password"' in body:
            raise UploadError("登录失败：服务器仍返回登录页（口令或地址不对）")

    def upload(self, file_path: Path, platform: str, version: str,
               notes: str, replace: bool) -> dict:
        token = _csrf(self._get("/admin"), "管理页")
        boundary = f"----pan4dex{uuid.uuid4().hex}"
        fields = {
            "csrf_token": token,
            "platform": platform,
            "version": version,
            "notes": notes,
            "replace": "1" if replace else "0",
        }
        body_path = Path(tempfile.mkstemp(prefix="pan4dex-upload-", suffix=".part")[1])
        try:
            with open(body_path, "wb") as body:
                for key, value in fields.items():
                    body.write(
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                        f"{value}\r\n".encode("utf-8"))
                filename = file_path.name
                content_type = (mimetypes.guess_type(filename)[0]
                                or "application/octet-stream")
                body.write(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="artifact"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
                with open(file_path, "rb") as source:
                    shutil.copyfileobj(source, body, 1024 * 1024)
                body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))

            # body 必须构造时传入：Request.data 的 setter 事后赋值会删掉
            # Content-Length（urllib issue 16464），请求变成 chunked，服务器直接拒收
            with open(body_path, "rb") as body:
                request = urllib.request.Request(
                    f"{self.base}/admin/upload",
                    data=body,
                    method="POST",
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Content-Length": str(body_path.stat().st_size),
                        "X-CSRF-Token": token,
                        "X-Requested-With": "XMLHttpRequest",
                    })
                try:
                    with self.opener.open(request, timeout=self.timeout) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    payload = exc.read().decode("utf-8", errors="replace")
                    try:
                        message = json.loads(payload).get("message", payload)
                    except ValueError:
                        message = payload[:300]
                    if exc.code == 409:
                        raise AlreadyExists(message) from exc
                    raise UploadError(
                        f"服务器拒绝上传（HTTP {exc.code}）：{message}") from exc
        finally:
            try:
                body_path.unlink()
            except OSError:
                pass


def upload_artifact(file_path: str | Path, platform: str, version: str,
                    notes: str | None = None, replace: bool | None = None,
                    config: dict | None = None) -> dict:
    """上传单个产物；成功返回服务器 JSON，失败抛 UploadError"""
    _utf8_console()
    file_path = Path(file_path)
    if not file_path.is_file():
        raise UploadError(f"产物不存在: {file_path}")
    if platform not in ("windows", "linux"):
        raise UploadError(f"未知平台: {platform}")
    config = config or load_config()
    if replace is None:
        replace = bool(config.get("replace", False))
    if notes is None:
        notes = str(config.get("notes_template", "Pan4dex {version}")).format(
            version=version)
    client = Client(str(config.get("server_url", DEFAULT_CONFIG["server_url"])),
                    float(config.get("timeout_seconds", 900)))
    size_mb = file_path.stat().st_size / 1024 / 1024
    print(f"上传 {file_path.name}（{size_mb:.1f} MB，{platform} {version}）"
          f" → {client.base}")
    started = time.monotonic()
    client.login(_admin_password(config))
    result = client.upload(file_path, platform, version, notes, replace)
    elapsed = time.monotonic() - started
    print(f"上传完成：{result.get('message', 'ok')}（{elapsed:.1f}s）")
    return result


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(description="上传 Pan4dex 构建产物到更新服务器")
    parser.add_argument("--platform", choices=("windows", "linux"), required=True)
    parser.add_argument("--file", required=True, help="产物路径")
    parser.add_argument("--version", help="版本号；默认从文件名推断")
    parser.add_argument("--notes", help="发布说明（纯文本）")
    parser.add_argument("--replace", action="store_true", help="覆盖同平台同版本")
    parser.add_argument("--server", help="覆盖配置里的服务器地址")
    args = parser.parse_args(argv)

    version = args.version
    if not version:
        match = _VERSION_RE.search(Path(args.file).name)
        if not match:
            print(f"无法从文件名推断版本号: {args.file}", file=sys.stderr)
            return 1
        version = match.group(1)
    config = load_config()
    if args.server:
        config["server_url"] = args.server
    try:
        upload_artifact(args.file, args.platform, version, notes=args.notes,
                        replace=True if args.replace else None, config=config)
    except AlreadyExists as exc:
        print(f"未上传：{exc}\n如需覆盖请加 --replace", file=sys.stderr)
        return 2
    except UploadError as exc:
        print(f"上传失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
