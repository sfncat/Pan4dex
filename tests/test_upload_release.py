"""build -U 上传通道的回归测试：登录、CSRF、multipart 字段与 409 处理。

用本地假服务器模拟更新服务器的 /admin/login、/admin、/admin/upload 契约，
不连 230（契约变化时这里先红，再去核对 server/update-server/app.py）。
"""
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import upload_release  # noqa: E402
from upload_release import AlreadyExists, UploadError, upload_artifact  # noqa: E402

_CSRF = "csrf-test-token"
_LOGIN_PAGE = (
    '<html><form method="post" action="/admin/login">'
    f'<input type="hidden" name="csrf_token" value="{_CSRF}">'
    '<input name="password" type="password"></form></html>'
)
_ADMIN_PAGE = (
    f'<html><form><input type="hidden" name="csrf_token" value="{_CSRF}">'
    "</form></html>"
)


class _State:
    password = "secret"
    conflict = False
    uploads = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body: str, content_type="text/html", extra=None):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/admin/login":
            self._send(200, _LOGIN_PAGE)
        elif self.path == "/admin":
            self._send(200, _ADMIN_PAGE)
        else:
            self._send(404, "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/admin/login":
            form = body.decode("utf-8")
            if f"password={_State.password}" in form:
                self._send(303, "", extra={"Location": "/admin"})
            else:
                self._send(401, _LOGIN_PAGE)
            return
        if self.path == "/admin/upload":
            if self.headers.get("X-CSRF-Token") != _CSRF:
                self._send(400, '{"error":"csrf"}', "application/json")
                return
            if b'name="platform"\r\n\r\nwindows' not in body:
                self._send(400, '{"error":"platform"}', "application/json")
                return
            if b'name="artifact"; filename="pan4dex-1.9.028.zip"' not in body:
                self._send(400, '{"error":"artifact"}', "application/json")
                return
            _State.uploads.append(body)
            if _State.conflict:
                self._send(409, '{"ok":false,"message":"版本已存在"}',
                           "application/json")
            else:
                self._send(201, '{"ok":true,"message":"已上传"}',
                           "application/json")
            return
        self._send(404, "not found")


@pytest.fixture(autouse=True)
def _isolate_dotenv(tmp_path, monkeypatch):
    """别读到仓库里真实存在的 server/update-server/.env"""
    monkeypatch.setattr(upload_release, "DOTENV_PATH", tmp_path / "missing.env")


@pytest.fixture()
def server(monkeypatch):
    _State.password = "secret"
    _State.conflict = False
    _State.uploads = []
    monkeypatch.setenv("PAN4DEX_UPDATE_ADMIN_PASSWORD", _State.password)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _artifact(tmp_path) -> Path:
    path = tmp_path / "pan4dex-1.9.028.zip"
    path.write_bytes(b"PK\x03\x04" + b"x" * 2048)
    return path


def test_upload_logs_in_and_posts_multipart(server, tmp_path):
    result = upload_artifact(
        _artifact(tmp_path), "windows", "1.9.028", notes="修复若干问题",
        config={"server_url": server, "timeout_seconds": 10})
    assert result["ok"] is True
    body = _State.uploads[0]
    assert b'name="version"\r\n\r\n1.9.028' in body
    assert "修复若干问题".encode("utf-8") in body
    assert body.endswith(b"--\r\n")


def test_upload_conflict_raises_already_exists(server, tmp_path):
    _State.conflict = True
    with pytest.raises(AlreadyExists):
        upload_artifact(_artifact(tmp_path), "windows", "1.9.028",
                        config={"server_url": server, "timeout_seconds": 10})


def test_upload_rejects_wrong_password(server, tmp_path, monkeypatch):
    monkeypatch.setenv("PAN4DEX_UPDATE_ADMIN_PASSWORD", "wrong")
    with pytest.raises(UploadError, match="口令"):
        upload_artifact(_artifact(tmp_path), "windows", "1.9.028",
                        config={"server_url": server, "timeout_seconds": 10})


def test_upload_requires_password_outside_tty(server, tmp_path, monkeypatch):
    monkeypatch.delenv("PAN4DEX_UPDATE_ADMIN_PASSWORD", raising=False)
    with pytest.raises(UploadError, match="管理口令"):
        upload_artifact(_artifact(tmp_path), "windows", "1.9.028",
                        config={"server_url": server})


def test_password_from_dotenv(server, tmp_path, monkeypatch):
    """仓库里的 server/update-server/.env 与服务器共用，不另存明文到 json"""
    monkeypatch.delenv("PAN4DEX_UPDATE_ADMIN_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# 注释\n"
        'export PAN4DEX_UPDATE_ADMIN_PASSWORD="secret"\n'
        "PAN4DEX_UPDATE_PUBLIC_BASE_URL=http://192.168.5.230:23011\n",
        encoding="utf-8")
    monkeypatch.setattr(upload_release, "DOTENV_PATH", env_file)
    result = upload_artifact(_artifact(tmp_path), "windows", "1.9.028",
                             config={"server_url": server, "timeout_seconds": 10})
    assert result["ok"] is True


def test_env_var_wins_over_dotenv(server, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PAN4DEX_UPDATE_ADMIN_PASSWORD=wrong\n", encoding="utf-8")
    monkeypatch.setattr(upload_release, "DOTENV_PATH", env_file)
    monkeypatch.setenv("PAN4DEX_UPDATE_ADMIN_PASSWORD", "secret")
    result = upload_artifact(_artifact(tmp_path), "windows", "1.9.028",
                             config={"server_url": server, "timeout_seconds": 10})
    assert result["ok"] is True
