# -*- coding: utf-8 -*-
import hashlib
import io
import re
import zipfile

import pytest

from app import create_app


def make_zip(entries: dict[str, bytes] | None = None) -> bytes:
    entries = entries or {
        "pan4dex/pan4dex.exe": b"MZ-fake-exe",
        "pan4dex/_internal/base_library.zip": b"fake",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def make_elf(size: int = 128) -> bytes:
    head = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + b"\x00" * 7 + b"\x02\x00" + b"\x3e\x00"
    return head + b"\x00" * max(0, size - len(head))


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path / "data"),
            "ADMIN_PASSWORD": "test-password",
            "SECRET_KEY": "test-secret",
            "PUBLIC_BASE_URL": "http://192.168.5.230:23011",
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "页面里没有 CSRF token"
    return match.group(1)


def login(client, password: str = "test-password"):
    page = client.get("/admin/login")
    token = extract_csrf(page.get_data(as_text=True))
    return client.post(
        "/admin/login",
        data={"password": password, "csrf_token": token},
        follow_redirects=False,
    )


def admin_csrf(client) -> str:
    page = client.get("/admin")
    assert page.status_code == 200
    return extract_csrf(page.get_data(as_text=True))


def upload(client, *, platform="windows", version="1.9.028", content=None, filename=None, notes="", replace=False):
    if filename is None:
        filename = f"pan4dex-{version}.zip" if platform == "windows" else f"pan4dex-{version}-linux"
    if content is None:
        content = make_zip() if platform == "windows" else make_elf()
    data = {
        "platform": platform,
        "version": version,
        "notes": notes,
        "artifact": (io.BytesIO(content), filename),
    }
    if replace:
        data["replace"] = "1"
    return client.post(
        "/admin/upload",
        data=data,
        content_type="multipart/form-data",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": admin_csrf(client),
        },
    )


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_public_pages_and_empty_latest(client):
    assert client.get("/").status_code == 200
    latest = client.get("/api/v1/latest?platform=windows")
    assert latest.status_code == 404
    assert latest.get_json()["error"] == "no_release"
    assert client.get("/api/v1/latest?platform=darwin").status_code == 400


def test_admin_requires_login(client):
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_login_rejects_wrong_password_and_locks_after_five(client):
    for _ in range(4):
        assert login(client, "wrong").status_code == 401
    fifth = login(client, "wrong")
    assert fifth.status_code == 401
    assert "锁定" in fifth.get_data(as_text=True)
    assert login(client, "test-password").status_code == 429


def test_upload_requires_csrf_and_login(client):
    assert client.post("/admin/upload").status_code == 302
    assert login(client).status_code == 302
    response = client.post(
        "/admin/upload",
        data={"platform": "windows", "version": "1.9.028"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 400


def test_upload_windows_and_latest_api(client):
    assert login(client).status_code == 302
    content = make_zip()
    response = upload(client, notes="修复若干问题")
    assert response.status_code == 201, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["release"]["sha256"] == hashlib.sha256(content).hexdigest()

    latest = client.get("/api/v1/latest?platform=windows").get_json()
    assert latest["version"] == "1.9.028"
    assert latest["size"] == len(content)
    assert latest["notes"] == "修复若干问题"
    assert latest["download_url"].endswith("/download/windows/pan4dex-1.9.028.zip")


def test_upload_linux_and_platform_separation(client):
    assert login(client).status_code == 302
    assert upload(client, platform="linux", version="1.9.028").status_code == 201
    assert client.get("/api/v1/latest?platform=linux").get_json()["version"] == "1.9.028"
    assert client.get("/api/v1/latest?platform=windows").status_code == 404


def test_latest_picks_highest_version(client):
    assert login(client).status_code == 302
    for version in ("1.9.028", "1.9.029", "1.9.030"):
        assert upload(client, version=version).status_code == 201
    assert client.get("/api/v1/latest?platform=windows").get_json()["version"] == "1.9.030"


def test_duplicate_requires_replace_and_replace_updates_hash(client):
    assert login(client).status_code == 302
    first = upload(client)
    assert first.status_code == 201
    duplicate = upload(client)
    assert duplicate.status_code == 409

    new_content = make_zip({"pan4dex/pan4dex.exe": b"MZ-new"})
    replaced = upload(client, content=new_content, notes="替换", replace=True)
    assert replaced.status_code == 200
    assert replaced.get_json()["release"]["sha256"] == hashlib.sha256(new_content).hexdigest()
    assert replaced.get_json()["release"]["notes"] == "替换"


def test_rejects_bad_filename_and_cross_platform_name(client):
    assert login(client).status_code == 302
    bad_name = upload(client, filename="pan4dex-1.9.028.zip.bak")
    assert bad_name.status_code == 400
    cross = upload(client, platform="linux", filename="pan4dex-1.9.028.zip")
    assert cross.status_code == 400


def test_rejects_zip_without_exe_and_zip_slip(client):
    assert login(client).status_code == 302
    missing = upload(client, content=make_zip({"pan4dex/_internal/x.txt": b"x"}))
    assert missing.status_code == 400
    slip = upload(
        client,
        content=make_zip(
            {
                "pan4dex/pan4dex.exe": b"MZ",
                "pan4dex/../evil.exe": b"evil",
            }
        ),
    )
    assert slip.status_code == 400


def test_rejects_non_elf_linux_payload(client):
    assert login(client).status_code == 302
    response = upload(client, platform="linux", content=b"#!/bin/sh\necho hi\n")
    assert response.status_code == 400


def test_rejects_too_long_notes(client):
    assert login(client).status_code == 302
    response = upload(client, notes="x" * 4001)
    assert response.status_code == 400


def test_yank_falls_back_to_previous_version_and_keeps_download(client):
    assert login(client).status_code == 302
    older = upload(client, version="1.9.028").get_json()["release"]
    newer_response = upload(client, version="1.9.029")
    newer = newer_response.get_json()["release"]
    assert client.get("/api/v1/latest?platform=windows").get_json()["version"] == "1.9.029"

    token = admin_csrf(client)
    yank = client.post(
        f"/admin/releases/{newer['id']}/yank",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert yank.status_code == 303
    assert client.get("/api/v1/latest?platform=windows").get_json()["version"] == "1.9.028"
    # 撤下只影响 latest，不影响已缓存的下载链接
    assert client.get(f"/download/windows/{newer['filename']}").status_code == 200

    unyank = client.post(
        f"/admin/releases/{newer['id']}/unyank",
        data={"csrf_token": admin_csrf(client)},
        follow_redirects=False,
    )
    assert unyank.status_code == 303
    assert client.get("/api/v1/latest?platform=windows").get_json()["version"] == "1.9.029"
    assert older["version"] == "1.9.028"


def test_delete_removes_file_and_record(client):
    assert login(client).status_code == 302
    release = upload(client).get_json()["release"]
    token = admin_csrf(client)
    response = client.post(
        f"/admin/releases/{release['id']}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/api/v1/latest?platform=windows").status_code == 404
    assert client.get(f"/download/windows/{release['filename']}").status_code == 404


def test_retention_keeps_only_newest_five_per_platform(app, client):
    assert login(client).status_code == 302
    for i in range(7):
        version = f"1.9.0{40 + i}"
        assert upload(client, platform="windows", version=version).status_code == 201
        assert upload(client, platform="linux", version=version).status_code == 201

    storage = app.extensions["storage"]
    releases = client.get("/api/v1/releases?platform=windows").get_json()["releases"]
    versions = [r["version"] for r in releases]
    assert versions == ["1.9.046", "1.9.045", "1.9.044", "1.9.043", "1.9.042"]
    assert len(client.get("/api/v1/releases?platform=linux").get_json()["releases"]) == 5

    # 被裁掉的版本连产物文件一起删除
    assert not (storage.releases_dir / "windows" / "pan4dex-1.9.040.zip").exists()
    assert (storage.releases_dir / "windows" / "pan4dex-1.9.046.zip").exists()
    assert not (storage.releases_dir / "linux" / "pan4dex-1.9.040-linux").exists()


def test_retention_override_via_config(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(tmp_path / "data"),
            "ADMIN_PASSWORD": "test-password",
            "SECRET_KEY": "test-secret",
            "RETENTION": 2,
        }
    )
    client = app.test_client()
    assert login(client).status_code == 302
    for i in range(4):
        version = f"1.9.0{30 + i}"
        assert upload(client, platform="windows", version=version).status_code == 201
    releases = client.get("/api/v1/releases?platform=windows").get_json()["releases"]
    assert [r["version"] for r in releases] == ["1.9.033", "1.9.032"]


def test_startup_prune_deletes_existing_excess(tmp_path):
    from storage import Storage

    data_dir = tmp_path / "data"
    Storage(data_dir)  # 先建库
    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(data_dir),
            "ADMIN_PASSWORD": "test-password",
            "SECRET_KEY": "test-secret",
        }
    )
    storage = app.extensions["storage"]
    for i in range(7):
        storage.add_release(
            version=f"1.9.0{50 + i}",
            platform="windows",
            filename=f"pan4dex-1.9.0{50 + i}.zip",
            size=1,
            sha256="a" * 64,
            notes="",
        )
        platform_dir = storage.releases_dir / "windows"
        platform_dir.mkdir(parents=True, exist_ok=True)
        artifact = platform_dir / f"pan4dex-1.9.0{50 + i}.zip"
        artifact.write_bytes(b"x")

    restarted = create_app(
        {
            "TESTING": True,
            "DATA_DIR": str(data_dir),
            "ADMIN_PASSWORD": "test-password",
            "SECRET_KEY": "test-secret",
        }
    )
    restarted_storage = restarted.extensions["storage"]
    versions = [r.version for r in restarted_storage.list_releases("windows")]
    assert versions == ["1.9.056", "1.9.055", "1.9.054", "1.9.053", "1.9.052"]
    assert not (restarted_storage.releases_dir / "windows" / "pan4dex-1.9.050.zip").exists()
    assert not (restarted_storage.releases_dir / "windows" / "pan4dex-1.9.051.zip").exists()


def test_download_headers_and_path_traversal(client):
    assert login(client).status_code == 302
    content = make_zip()
    upload(client, content=content)
    response = client.get("/download/windows/pan4dex-1.9.028.zip")
    assert response.status_code == 200
    assert response.data == content
    assert response.headers["X-Checksum-Sha256"] == hashlib.sha256(content).hexdigest()
    assert "attachment" in response.headers["Content-Disposition"]

    assert client.get("/download/windows/..%2Fpan4dex.sqlite3").status_code == 404
    assert client.get("/download/darwin/pan4dex-1.9.028.zip").status_code == 404


def test_releases_api_lists_versions(client):
    assert login(client).status_code == 302
    upload(client, version="1.9.028")
    upload(client, platform="linux", version="1.9.028")
    payload = client.get("/api/v1/releases?platform=windows").get_json()
    assert len(payload["releases"]) == 1
    assert payload["releases"][0]["version"] == "1.9.028"
