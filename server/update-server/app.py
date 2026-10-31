# -*- coding: utf-8 -*-
"""Pan4dex 更新服务器。

局域网内部使用：管理页上传版本、客户端查询最新版本并下载产物。
机制说明见仓库 docs/update.md，本文件只负责 HTTP 层。
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
import shutil
import time
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from storage import (
    MAX_NOTES_LENGTH,
    PLATFORMS,
    Storage,
    ValidationError,
    detect_platform,
    expected_filename,
    now_iso,
    parse_version,
    sha256_file,
    validate_artifact,
)

SERVER_VERSION = "1.0.0"
DEFAULT_PORT = 23011
DEFAULT_MAX_UPLOAD_MB = 500
DEFAULT_RETENTION = 5
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 60


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _load_or_create_secret(data_dir: Path) -> str:
    secret_file = data_dir / "secret.key"
    if secret_file.is_file():
        return secret_file.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    secret_file.write_text(secret, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return secret


def create_app(overrides: dict | None = None) -> Flask:
    overrides = dict(overrides or {})
    app = Flask(__name__, template_folder="templates", static_folder="static")

    data_dir = Path(overrides.pop("DATA_DIR", os.environ.get("PAN4DEX_UPDATE_DATA_DIR") or Path(__file__).parent / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    testing = bool(overrides.pop("TESTING", False))
    admin_password = overrides.pop("ADMIN_PASSWORD", os.environ.get("PAN4DEX_UPDATE_ADMIN_PASSWORD", ""))
    if not admin_password and not testing:
        raise RuntimeError(
            "未设置 PAN4DEX_UPDATE_ADMIN_PASSWORD；拒绝以空口令启动更新服务器"
        )
    secret_key = overrides.pop("SECRET_KEY", os.environ.get("PAN4DEX_UPDATE_SECRET", ""))
    if not secret_key:
        secret_key = "test-secret" if testing else _load_or_create_secret(data_dir)

    max_upload_mb = int(overrides.pop("MAX_UPLOAD_MB", os.environ.get("PAN4DEX_UPDATE_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)))
    retention = int(overrides.pop("RETENTION", os.environ.get("PAN4DEX_UPDATE_RETENTION", DEFAULT_RETENTION)))
    public_base_url = str(overrides.pop("PUBLIC_BASE_URL", os.environ.get("PAN4DEX_UPDATE_PUBLIC_BASE_URL", ""))).rstrip("/")

    app.config.update(
        DATA_DIR=str(data_dir),
        ADMIN_PASSWORD=admin_password,
        SECRET_KEY=secret_key,
        MAX_CONTENT_LENGTH=max_upload_mb * 1024 * 1024 + 2 * 1024 * 1024,
        MAX_UPLOAD_MB=max_upload_mb,
        RETENTION=retention,
        PUBLIC_BASE_URL=public_base_url,
        TESTING=testing,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="pan4dex_update_session",
        PERMANENT_SESSION_LIFETIME=8 * 60 * 60,
        TEMPLATES_AUTO_RELOAD=testing,
    )

    storage = Storage(data_dir)
    app.extensions["storage"] = storage
    app.extensions["login_failures"] = {}

    # ---------- 通用工具 ----------

    def get_csrf() -> str:
        token = session.get("csrf")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf"] = token
        return token

    def require_csrf() -> None:
        expected = session.get("csrf")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="CSRF 校验失败，请刷新页面重试")

    def wants_json() -> bool:
        return request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    def audit(action: str, detail: str) -> None:
        try:
            addr = request.remote_addr if has_request_context() else "-"
            line = f"{now_iso()}\t{addr or '-'}\t{action}\t{detail}\n"
            with open(storage.log_dir / "admin.log", "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    for pruned in storage.prune(retention):
        audit(f"prune (启动保留最新 {retention} 个)", f"{pruned.platform} {pruned.version}")

    def download_url(release) -> str:
        path = url_for("download", platform=release.platform, filename=release.filename)
        return f"{public_base_url}{path}" if public_base_url else url_for("download", platform=release.platform, filename=release.filename, _external=True)

    def release_payload(release) -> dict:
        return {
            "version": release.version,
            "platform": release.platform,
            "filename": release.filename,
            "size": release.size,
            "sha256": release.sha256,
            "published_at": release.uploaded_at,
            "notes": release.notes,
            "download_url": download_url(release),
        }

    def respond_upload(ok: bool, message: str, status: int, release=None):
        if wants_json():
            payload = {"ok": ok, "message": message}
            if release is not None:
                payload["release"] = release.to_dict()
            return jsonify(payload), status
        flash(message, "success" if ok else "error")
        return redirect(url_for("admin"), code=303)

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": get_csrf,
            "server_version": SERVER_VERSION,
            "is_admin": bool(session.get("admin")),
            "platforms": PLATFORMS,
            "max_upload_mb": app.config["MAX_UPLOAD_MB"],
            "now_year": time.strftime("%Y"),
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    # ---------- 公开页面与 API ----------

    @app.get("/")
    def public_index():
        releases = storage.list_releases()
        latest = {platform: storage.latest(platform) for platform in PLATFORMS}
        grouped = {platform: [r for r in releases if r.platform == platform] for platform in PLATFORMS}
        return render_template(
            "public.html",
            latest=latest,
            grouped=grouped,
            total_size=storage.total_size(),
        )

    @app.get("/api/v1/latest")
    def api_latest():
        platform = (request.args.get("platform") or "").strip().lower()
        if platform not in PLATFORMS:
            return jsonify(error="invalid_platform", message="platform 只能是 windows 或 linux"), 400
        release = storage.latest(platform)
        if release is None:
            return jsonify(error="no_release", message=f"{platform} 还没有可用版本"), 404
        response = jsonify(release_payload(release))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/releases")
    def api_releases():
        platform = (request.args.get("platform") or "").strip().lower() or None
        if platform is not None and platform not in PLATFORMS:
            return jsonify(error="invalid_platform"), 400
        releases = [release_payload(r) for r in storage.list_releases(platform)]
        response = jsonify(releases=releases)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/download/<platform>/<path:filename>")
    def download(platform: str, filename: str):
        if platform not in PLATFORMS:
            abort(404)
        release = storage.find_by_filename(platform, filename)
        if release is None:
            abort(404)
        directory = storage.release_dir(platform)
        if not (directory / release.filename).is_file():
            abort(404)
        response = send_from_directory(
            directory,
            release.filename,
            as_attachment=True,
            download_name=release.filename,
            conditional=True,
        )
        response.headers["X-Checksum-Sha256"] = release.sha256
        return response

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok", server_version=SERVER_VERSION, time=now_iso())

    # ---------- 登录 ----------

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            require_csrf()
            ip = request.remote_addr or "-"
            failures = app.extensions["login_failures"]
            count, locked_until = failures.get(ip, (0, 0.0))
            if locked_until > time.time():
                error = "尝试次数过多，请稍后再试"
                return render_template("login.html", error=error), 429
            supplied = request.form.get("password", "")
            expected = app.config["ADMIN_PASSWORD"]
            if expected and hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
                session.clear()
                session["admin"] = True
                session["csrf"] = secrets.token_urlsafe(32)
                session.permanent = True
                failures.pop(ip, None)
                audit("login_ok", "管理员登录")
                return redirect(url_for("admin"))
            count += 1
            locked_until = time.time() + LOGIN_LOCK_SECONDS if count >= LOGIN_MAX_FAILURES else 0.0
            failures[ip] = (count, locked_until)
            error = "口令不正确" + ("，已锁定 60 秒" if locked_until else "")
            audit("login_fail", f"第 {count} 次")
            return render_template("login.html", error=error), 401
        return render_template("login.html", error=error)

    @app.post("/admin/logout")
    def logout():
        require_csrf()
        session.clear()
        return redirect(url_for("public_index"))

    # ---------- 管理页 ----------

    @app.get("/admin")
    @login_required
    def admin():
        releases = storage.list_releases()
        latest = {platform: storage.latest(platform) for platform in PLATFORMS}
        grouped = {platform: [r for r in releases if r.platform == platform] for platform in PLATFORMS}
        usage = shutil.disk_usage(storage.data_dir)
        return render_template(
            "admin.html",
            latest=latest,
            grouped=grouped,
            release_count=len(releases),
            total_size=storage.total_size(),
            disk_free=usage.free,
            max_upload_mb=app.config["MAX_UPLOAD_MB"],
        )

    @app.post("/admin/upload")
    @login_required
    def upload():
        require_csrf()
        uploaded = request.files.get("artifact")
        if uploaded is None or not uploaded.filename:
            return respond_upload(False, "没有选择文件", 400)

        filename = os.path.basename(uploaded.filename.replace("\\", "/"))
        platform = (request.form.get("platform") or detect_platform(filename) or "").strip().lower()
        version = (request.form.get("version") or "").strip()
        if not version:
            match = re.search(r"pan4dex-(\d+\.\d+\.\d+)", filename)
            version = match.group(1) if match else ""
        notes = (request.form.get("notes") or "").strip()
        replace = request.form.get("replace") == "1"

        if platform not in PLATFORMS:
            return respond_upload(False, "无法判断平台，请选择 windows 或 linux", 400)
        try:
            parse_version(version)
        except ValidationError as exc:
            return respond_upload(False, str(exc), 400)
        if len(notes) > MAX_NOTES_LENGTH:
            return respond_upload(False, f"发布说明不能超过 {MAX_NOTES_LENGTH} 字", 400)
        expected = expected_filename(version, platform)
        if filename != expected:
            return respond_upload(
                False,
                f"文件名应为 {expected}（当前 {filename}）",
                400,
            )

        tmp_path = storage.tmp_dir / f"upload-{secrets.token_hex(8)}"
        try:
            uploaded.save(tmp_path)
            size = tmp_path.stat().st_size
            if size <= 0:
                return respond_upload(False, "上传文件为空", 400)
            validate_artifact(tmp_path, platform, filename)
            digest = sha256_file(tmp_path)
        except ValidationError as exc:
            tmp_path.unlink(missing_ok=True)
            return respond_upload(False, str(exc), 400)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            return respond_upload(False, f"保存上传文件失败：{exc}", 500)

        existing = storage.find(version, platform)
        if existing is not None and not replace:
            tmp_path.unlink(missing_ok=True)
            return respond_upload(False, f"{version}（{platform}）已存在；如需覆盖请勾选「替换同版本」", 409)

        final_path = storage.release_dir(platform) / filename
        try:
            os.replace(tmp_path, final_path)
            if existing is not None:
                release = storage.replace_release(existing.id, size=size, sha256=digest, notes=notes)
                audit("replace", f"{platform} {version} {filename} {digest}")
                return respond_upload(True, f"已替换 {version}（{platform}）", 200, release)
            release = storage.add_release(
                version=version,
                platform=platform,
                filename=filename,
                size=size,
                sha256=digest,
                notes=notes,
            )
            audit("upload", f"{platform} {version} {filename} {digest}")
            for pruned in storage.prune(app.config["RETENTION"]):
                audit(f"prune (上传后保留最新 {app.config['RETENTION']} 个)", f"{pruned.platform} {pruned.version}")
            return respond_upload(True, f"已上传 {version}（{platform}）", 201, release)
        except (ValidationError, OSError) as exc:
            if existing is None and storage.find(version, platform) is None:
                final_path.unlink(missing_ok=True)
            return respond_upload(False, f"保存版本失败：{exc}", 500)

    @app.post("/admin/releases/<int:release_id>/<action>")
    @login_required
    def release_action(release_id: int, action: str):
        require_csrf()
        release = storage.get(release_id)
        if release is None:
            abort(404)
        if action == "yank":
            storage.set_yanked(release_id, True)
            audit("yank", f"{release.platform} {release.version}")
            message = f"已撤下 {release.version}（{release.platform}）"
        elif action == "unyank":
            storage.set_yanked(release_id, False)
            audit("unyank", f"{release.platform} {release.version}")
            message = f"已恢复 {release.version}（{release.platform}）"
        elif action == "delete":
            storage.delete_release(release_id)
            audit("delete", f"{release.platform} {release.version} {release.filename}")
            message = f"已删除 {release.version}（{release.platform}）"
        else:
            abort(404)
        flash(message, "success")
        return redirect(url_for("admin"), code=303)

    # ---------- 错误页 ----------

    @app.errorhandler(400)
    def bad_request(exc):
        message = getattr(exc, "description", "请求不合法")
        if wants_json():
            return jsonify(ok=False, message=message), 400
        return render_template("error.html", code=400, message=message), 400

    @app.errorhandler(404)
    def not_found(_exc):
        if wants_json():
            return jsonify(ok=False, message="未找到"), 404
        return render_template("error.html", code=404, message="未找到请求的资源"), 404

    @app.errorhandler(413)
    def too_large(_exc):
        message = f"文件超过 {app.config['MAX_UPLOAD_MB']} MB 上限"
        if wants_json():
            return jsonify(ok=False, message=message), 413
        return render_template("error.html", code=413, message=message), 413

    return app


def _serve() -> None:
    from waitress import serve

    app = create_app()
    port = int(os.environ.get("PAN4DEX_UPDATE_PORT", DEFAULT_PORT))
    serve(app, host="0.0.0.0", port=port, threads=8)


if __name__ == "__main__":
    _serve()
