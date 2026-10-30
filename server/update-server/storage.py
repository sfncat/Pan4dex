# -*- coding: utf-8 -*-
"""更新服务器的存储与产物校验。

只做两件事：SQLite 元数据、磁盘产物；所有包结构校验都在这里，
路由层不直接碰文件系统路径拼接。
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import struct
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PLATFORMS = ("windows", "linux")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ZIP_EXE_ENTRY = "pan4dex/pan4dex.exe"
MAX_NOTES_LENGTH = 4000


class ValidationError(ValueError):
    """上传产物或元数据不合法（由路由层转成 400/409）。"""


def parse_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not VERSION_RE.match(value):
        raise ValidationError(f"版本号格式应为 x.y.z：{value!r}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Release:
    id: int
    version: str
    platform: str
    filename: str
    size: int
    sha256: str
    notes: str
    uploaded_at: str
    yanked: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "platform": self.platform,
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
            "notes": self.notes,
            "uploaded_at": self.uploaded_at,
            "yanked": self.yanked,
        }


def expected_filename(version: str, platform: str) -> str:
    if platform == "windows":
        return f"pan4dex-{version}.zip"
    if platform == "linux":
        return f"pan4dex-{version}-linux"
    raise ValidationError(f"未知平台：{platform}")


def detect_platform(filename: str) -> str | None:
    if filename.endswith(".zip"):
        return "windows"
    if filename.endswith("-linux"):
        return "linux"
    return None


def validate_artifact(path: Path, platform: str, filename: str) -> None:
    """校验产物文件名与内容；不通过一律抛 ValidationError。"""
    if platform not in PLATFORMS:
        raise ValidationError("平台只能是 windows 或 linux")
    if Path(filename).name != filename or "\\" in filename or "/" in filename:
        raise ValidationError("文件名不能包含路径")
    match = re.fullmatch(r"pan4dex-(\d+\.\d+\.\d+)(-linux)?(\.zip)?", filename)
    if not match:
        raise ValidationError(f"文件名不符合发布命名：{filename}")
    file_platform = "linux" if filename.endswith("-linux") else "windows"
    if file_platform != platform:
        raise ValidationError(f"文件名表示的平台是 {file_platform}，与选择的 {platform} 不一致")
    parse_version(match.group(1))

    if platform == "windows":
        _validate_windows_zip(path)
    else:
        _validate_linux_elf(path)


def _validate_windows_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        raise ValidationError("不是有效的 zip 文件") from exc
    if not names:
        raise ValidationError("zip 是空的")
    for name in names:
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValidationError(f"zip 含非法路径：{name}")
        if not normalized.startswith("pan4dex/"):
            raise ValidationError(f"zip 顶层目录必须是 pan4dex/：{name}")
    if ZIP_EXE_ENTRY not in {name.replace("\\", "/") for name in names}:
        raise ValidationError(f"zip 缺少 {ZIP_EXE_ENTRY}")


def _validate_linux_elf(path: Path) -> None:
    with open(path, "rb") as fh:
        head = fh.read(20)
    if len(head) < 20 or head[:4] != b"\x7fELF":
        raise ValidationError("不是 ELF 可执行文件")
    ei_class, ei_data = head[4], head[5]
    if ei_class != 2:
        raise ValidationError("只接受 64 位 ELF（当前是 32 位）")
    if ei_data != 1:
        raise ValidationError("只接受小端 ELF")
    e_machine = struct.unpack("<H", head[18:20])[0]
    if e_machine != 62:
        raise ValidationError("只接受 x86-64 ELF")


class Storage:
    """元数据在 SQLite，产物在 data/releases/<platform>/。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.releases_dir = self.data_dir / "releases"
        self.tmp_dir = self.data_dir / "tmp"
        self.log_dir = self.data_dir / "logs"
        for directory in (self.data_dir, self.releases_dir, self.tmp_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "pan4dex.sqlite3"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    uploaded_at TEXT NOT NULL,
                    yanked INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(version, platform)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_releases_platform ON releases(platform)"
            )

    @staticmethod
    def _row_to_release(row: sqlite3.Row) -> Release:
        return Release(
            id=row["id"],
            version=row["version"],
            platform=row["platform"],
            filename=row["filename"],
            size=row["size"],
            sha256=row["sha256"],
            notes=row["notes"],
            uploaded_at=row["uploaded_at"],
            yanked=bool(row["yanked"]),
        )

    def artifact_path(self, release: Release) -> Path:
        # filename 已在上传时校验过，这里再按平台目录拼一次，杜绝路径穿越
        return self.releases_dir / release.platform / Path(release.filename).name

    def list_releases(self, platform: str | None = None) -> list[Release]:
        query = "SELECT * FROM releases"
        args: tuple = ()
        if platform is not None:
            query += " WHERE platform = ?"
            args = (platform,)
        with self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        releases = [self._row_to_release(row) for row in rows]
        releases.sort(key=lambda r: (r.platform, parse_version(r.version)), reverse=True)
        return releases

    def latest(self, platform: str) -> Release | None:
        candidates = [r for r in self.list_releases(platform) if not r.yanked]
        if not candidates:
            return None
        return max(candidates, key=lambda r: parse_version(r.version))

    def find(self, version: str, platform: str) -> Release | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM releases WHERE version = ? AND platform = ?",
                (version, platform),
            ).fetchone()
        return self._row_to_release(row) if row else None

    def get(self, release_id: int) -> Release | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM releases WHERE id = ?", (release_id,)).fetchone()
        return self._row_to_release(row) if row else None

    def find_by_filename(self, platform: str, filename: str) -> Release | None:
        if platform not in PLATFORMS or Path(filename).name != filename:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM releases WHERE platform = ? AND filename = ?",
                (platform, filename),
            ).fetchone()
        return self._row_to_release(row) if row else None

    def add_release(
        self,
        *,
        version: str,
        platform: str,
        filename: str,
        size: int,
        sha256: str,
        notes: str,
        uploaded_at: str | None = None,
    ) -> Release:
        parse_version(version)
        if platform not in PLATFORMS:
            raise ValidationError("平台只能是 windows 或 linux")
        if not SHA256_RE.match(sha256):
            raise ValidationError("sha256 格式不正确")
        if size <= 0:
            raise ValidationError("文件大小必须大于 0")
        uploaded_at = uploaded_at or now_iso()
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO releases (version, platform, filename, size, sha256, notes, uploaded_at, yanked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (version, platform, filename, size, sha256, notes, uploaded_at),
                )
                release_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("该版本已存在（同平台）") from exc
        release = self.get(release_id)
        assert release is not None
        return release

    def replace_release(
        self,
        release_id: int,
        *,
        size: int,
        sha256: str,
        notes: str,
        uploaded_at: str | None = None,
    ) -> Release:
        uploaded_at = uploaded_at or now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE releases
                   SET size = ?, sha256 = ?, notes = ?, uploaded_at = ?, yanked = 0
                 WHERE id = ?
                """,
                (size, sha256, notes, uploaded_at, release_id),
            )
        release = self.get(release_id)
        assert release is not None
        return release

    def set_yanked(self, release_id: int, yanked: bool) -> Release | None:
        with self._connect() as conn:
            conn.execute("UPDATE releases SET yanked = ? WHERE id = ?", (1 if yanked else 0, release_id))
        return self.get(release_id)

    def delete_release(self, release_id: int) -> Release | None:
        release = self.get(release_id)
        if release is None:
            return None
        with self._connect() as conn:
            conn.execute("DELETE FROM releases WHERE id = ?", (release_id,))
        try:
            self.artifact_path(release).unlink(missing_ok=True)
        except OSError:
            # 记录已删、文件删不掉（权限/占用）时不让管理操作 500；日志由路由层写
            pass
        return release

    def total_size(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(SUM(size), 0) AS total FROM releases").fetchone()
        return int(row["total"])

    def release_dir(self, platform: str) -> Path:
        if platform not in PLATFORMS:
            raise ValidationError("未知平台")
        directory = self.releases_dir / platform
        directory.mkdir(parents=True, exist_ok=True)
        return directory
