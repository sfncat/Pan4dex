"""
Pan4dex 万格 — 客户端更新核心的回归测试（不启动 GUI）

覆盖 `core/updater.py` 的检查 / 下载 / 校验 / 安装预检：版本比较、服务器
契约校验、SHA-256 与大小不符时的清理、取消、Windows zip 预检与 PowerShell
脚本生成（UTF-8 BOM）、Linux ELF 预检与原子替换。
"""
import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from core import updater


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def http_server():
    """按路径返回预置响应的本地 HTTP 服务（模拟 230 更新源）"""
    routes = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            entry = routes.get(self.path)
            if entry is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status, headers, body = entry
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", routes
    finally:
        server.shutdown()
        server.server_close()


def _latest_payload(**overrides):
    payload = {
        "platform": "windows",
        "version": "1.9.028",
        "filename": "pan4dex-1.9.028.zip",
        "size": 4,
        "sha256": hashlib.sha256(b"test").hexdigest(),
        "download_url": "/download/windows/pan4dex-1.9.028.zip",
        "notes": "发布说明",
        "published_at": "2026-10-30T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _make_zip(path: Path, entries: dict[str, bytes]):
    import zipfile
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def _elf_bytes(machine: int = 62) -> bytes:
    # e_ident(16) + e_type(2) + e_machine(2)
    header = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    header += b"\x02\x00" + machine.to_bytes(2, "little")
    return header + b"payload"


# -------------------------------------------------------------------- 版本


def test_parse_version_and_compare():
    assert updater.parse_version("1.9.028") == (1, 9, 28)
    assert updater.is_newer("1.9.028", "1.9.027")
    assert updater.is_newer("1.10.0", "1.9.99")
    assert not updater.is_newer("1.9.027", "1.9.027")
    assert not updater.is_newer("1.8.999", "1.9.0")
    with pytest.raises(ValueError):
        updater.parse_version("1.9")


def test_normalize_server_url():
    assert updater.normalize_server_url(" http://192.168.5.230:23011/ ") == \
        "http://192.168.5.230:23011"
    for bad in ("", "192.168.5.230:23011", "ftp://host", "http://"):
        with pytest.raises(ValueError):
            updater.normalize_server_url(bad)


# -------------------------------------------------------------------- 检查


def test_check_for_update_returns_info(http_server):
    base, routes = http_server
    routes["/api/v1/latest?platform=windows"] = (
        200, {"Content-Type": "application/json"},
        json.dumps(_latest_payload()).encode())
    info = updater.check_for_update(base, current_version="1.9.027",
                                    platform="windows")
    assert info is not None
    assert info.version == "1.9.028"
    # 相对下载地址按服务器根地址补全
    assert info.download_url == f"{base}/download/windows/pan4dex-1.9.028.zip"


def test_check_for_update_same_or_older_returns_none(http_server):
    base, routes = http_server
    routes["/api/v1/latest?platform=windows"] = (
        200, {}, json.dumps(_latest_payload(version="1.9.027")).encode())
    assert updater.check_for_update(base, "1.9.027", "windows") is None
    assert updater.check_for_update(base, "1.9.030", "windows") is None


def test_check_for_update_no_release(http_server):
    base, routes = http_server
    routes["/api/v1/latest?platform=linux"] = (
        404, {}, json.dumps({"error": "no_release", "message": "暂无"}).encode())
    assert updater.check_for_update(base, "1.9.027", "linux") is None


def test_check_for_update_errors(http_server):
    base, routes = http_server
    with pytest.raises(updater.CheckError):
        updater.check_for_update(base, "1.9.027", "windows")   # 404 未注册
    routes["/api/v1/latest?platform=windows"] = (200, {}, b"not json")
    with pytest.raises(updater.CheckError):
        updater.check_for_update(base, "1.9.027", "windows")
    routes["/api/v1/latest?platform=windows"] = (
        200, {}, json.dumps(_latest_payload(sha256="xyz")).encode())
    with pytest.raises(updater.CheckError):
        updater.check_for_update(base, "1.9.027", "windows")


def test_parse_update_info_rejects_bad_fields():
    for bad in (
        {"platform": "macos"},
        {"version": "1.9"},
        {"size": 0},
        {"filename": "../evil.zip"},
        {"download_url": ""},
        {"sha256": "0" * 63},
    ):
        with pytest.raises(updater.CheckError):
            updater.parse_update_info(_latest_payload(**bad), "http://host")


# -------------------------------------------------------------------- 下载


def _info_for(body: bytes, filename="pan4dex-1.9.028.zip", **overrides):
    kwargs = dict(
        platform="windows", version="1.9.028", filename=filename,
        size=len(body), sha256=hashlib.sha256(body).hexdigest(),
        download_url=f"/download/windows/{filename}")
    kwargs.update(overrides)
    return updater.UpdateInfo(**kwargs)


def test_download_verifies_and_reports_progress(http_server, tmp_path):
    base, routes = http_server
    body = os.urandom(1024)
    routes["/download/windows/pan4dex-1.9.028.zip"] = (
        200, {"Content-Type": "application/zip"}, body)
    calls = []
    path = updater.download_update(
        _info_for(body, download_url=f"{base}/download/windows/pan4dex-1.9.028.zip"),
        dest_dir=tmp_path, progress=lambda done, total: calls.append((done, total)))
    assert path == tmp_path / "pan4dex-1.9.028.zip"
    assert path.read_bytes() == body
    assert not (tmp_path / "pan4dex-1.9.028.zip.part").exists()
    assert calls and calls[-1] == (len(body), len(body))


def test_download_size_mismatch_cleans_part(http_server, tmp_path):
    base, routes = http_server
    body = b"12345"
    routes["/download/windows/pan4dex-1.9.028.zip"] = (200, {}, body)
    with pytest.raises(updater.IntegrityError):
        updater.download_update(
            _info_for(body, size=99,
                      download_url=f"{base}/download/windows/pan4dex-1.9.028.zip"),
            dest_dir=tmp_path)
    assert not (tmp_path / "pan4dex-1.9.028.zip.part").exists()
    assert not (tmp_path / "pan4dex-1.9.028.zip").exists()


def test_download_hash_mismatch_cleans_part(http_server, tmp_path):
    base, routes = http_server
    body = b"abc"
    routes["/download/windows/pan4dex-1.9.028.zip"] = (200, {}, body)
    with pytest.raises(updater.IntegrityError):
        updater.download_update(
            _info_for(body, sha256="0" * 64,
                      download_url=f"{base}/download/windows/pan4dex-1.9.028.zip"),
            dest_dir=tmp_path)
    assert not (tmp_path / "pan4dex-1.9.028.zip.part").exists()


def test_download_cancel_cleans_part(http_server, tmp_path):
    base, routes = http_server
    body = b"x" * 1024
    routes["/download/windows/pan4dex-1.9.028.zip"] = (200, {}, body)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(updater.DownloadCancelled):
        updater.download_update(
            _info_for(body, download_url=f"{base}/download/windows/pan4dex-1.9.028.zip"),
            dest_dir=tmp_path, cancel=cancel)
    assert not (tmp_path / "pan4dex-1.9.028.zip.part").exists()


# ------------------------------------------------------- Windows 安装预检


def test_validate_windows_zip_accepts_valid_package(tmp_path):
    archive = _make_zip(tmp_path / "ok.zip", {
        "pan4dex/pan4dex.exe": b"MZ",
        "pan4dex/_internal/base_library.zip": b"zip",
    })
    updater.validate_windows_zip(archive)


def test_validate_windows_zip_rejects_bad_packages(tmp_path):
    cases = {
        "traversal.zip": {"pan4dex/../evil.exe": b"x"},
        "missing.zip": {"pan4dex/other.exe": b"x"},
        "toplevel.zip": {"pan4dex-1.9.028/pan4dex.exe": b"x"},
        "absolute.zip": {"/etc/passwd": b"x"},
    }
    for name, entries in cases.items():
        archive = _make_zip(tmp_path / name, entries)
        with pytest.raises(updater.InstallError):
            updater.validate_windows_zip(archive)
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    with pytest.raises(updater.InstallError):
        updater.validate_windows_zip(broken)


def test_prepare_windows_install_writes_script_and_job(tmp_path, monkeypatch):
    target = tmp_path / "pan4dex"
    target.mkdir()
    (target / "pan4dex.exe").write_bytes(b"MZ")
    archive = _make_zip(tmp_path / "pan4dex-1.9.028.zip", {
        "pan4dex/pan4dex.exe": b"MZ",
    })
    script, job = updater.prepare_windows_install(
        archive, "1.9.028", "1.9.027", target_dir=target)
    try:
        assert script.name == "apply-update.ps1"
        # PowerShell 5.1 需要 BOM，否则中文路径按 ANSI 解读
        assert script.read_bytes().startswith(b"\xef\xbb\xbf")
        assert "pan4dex.exe" in script.read_text(encoding="utf-8-sig")
        # 宽限 15 秒后强杀旧进程：卡死的旧版本不能让安装等满超时后回滚
        text = script.read_text(encoding="utf-8-sig")
        assert "WaitForExit(15000)" in text and "Stop-Process" in text
        data = json.loads((script.parent / "job.json").read_text(encoding="utf-8"))
        assert data["target_dir"] == str(target)
        assert data["new_version"] == "1.9.028"
        assert data["old_version"] == "1.9.027"
        assert Path(data["zip_path"]) == archive
    finally:
        import shutil
        shutil.rmtree(script.parent, ignore_errors=True)


def test_prepare_windows_install_rejects_missing_exe_or_bad_zip(tmp_path):
    archive = _make_zip(tmp_path / "pan4dex-1.9.028.zip", {"pan4dex/pan4dex.exe": b"MZ"})
    empty_target = tmp_path / "empty"
    empty_target.mkdir()
    with pytest.raises(updater.InstallError):
        updater.prepare_windows_install(archive, "1.9.028", "1.9.027", empty_target)

    target = tmp_path / "pan4dex"
    target.mkdir()
    (target / "pan4dex.exe").write_bytes(b"MZ")
    bad = _make_zip(tmp_path / "bad.zip", {"evil.exe": b"x"})
    with pytest.raises(updater.InstallError):
        updater.prepare_windows_install(bad, "1.9.028", "1.9.027", target)


# --------------------------------------------------------- Linux 安装预检


def test_validate_linux_elf_accepts_x86_64(tmp_path):
    path = tmp_path / "pan4dex-1.9.028-linux"
    path.write_bytes(_elf_bytes())
    updater.validate_linux_elf(path)


def test_validate_linux_elf_rejects_wrong_files(tmp_path):
    for name, data in {
        "text": b"#!/bin/sh\necho hi\n",
        "truncated": b"\x7fELF",
        "arm": _elf_bytes(machine=183),
    }.items():
        path = tmp_path / name
        path.write_bytes(data)
        with pytest.raises(updater.InstallError):
            updater.validate_linux_elf(path)


def test_apply_linux_update_replaces_target(tmp_path):
    target = tmp_path / "pan4dex"
    target.write_bytes(b"old")
    download = tmp_path / "pan4dex-1.9.028-linux"
    download.write_bytes(_elf_bytes())
    result = updater.apply_linux_update(download, target, launch=False)
    assert result == target
    assert target.read_bytes() == _elf_bytes()
    assert not download.exists()
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o755


def test_apply_linux_update_rejects_non_elf(tmp_path):
    target = tmp_path / "pan4dex"
    target.write_bytes(b"old")
    download = tmp_path / "pan4dex-1.9.028-linux"
    download.write_bytes(b"#!/bin/sh")
    with pytest.raises(updater.InstallError):
        updater.apply_linux_update(download, target, launch=False)
    assert target.read_bytes() == b"old"


# ---------------------------------------------------------- 安装后清理


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 有目录备份")
def test_cleanup_after_update_removes_matching_backup(tmp_path, monkeypatch):
    install = tmp_path / "pan4dex"
    install.mkdir()
    backup = tmp_path / "pan4dex.bak-1.9.027"
    backup.mkdir()
    marker = install / "update-ok.json"
    marker.write_text(json.dumps({
        "version": "1.9.028", "backup": str(backup)}), encoding="utf-8")
    monkeypatch.setattr(updater, "windows_install_dir", lambda: install)

    updater.cleanup_after_update("1.9.027")     # 版本不符：保留
    assert backup.exists() and marker.exists()

    updater.cleanup_after_update("1.9.028")     # 版本一致：清理
    assert not backup.exists()
    assert not marker.exists()
