# -*- coding: utf-8 -*-
"""升级结果写进应用日志：启动时回读 %TEMP% 安装脚本日志，报过一次不再重复。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import updater


def _make_dir(tmp_path, name, log=None, job=None, mtime=None):
    d = tmp_path / name
    d.mkdir()
    if job is not None:
        (d / "job.json").write_text(
            json.dumps(job, ensure_ascii=False), encoding="utf-8")
    if log is not None:
        (d / "apply-update.log").write_text(log, encoding="utf-8")
    if mtime is not None:
        old = time.time() - mtime
        os.utime(d, (old, old))
    return d


def test_finished_install_reported_once(tmp_path):
    _make_dir(tmp_path, "pan4dex-update-a",
              log="2026-10-31 14:27:08 等待旧进程退出 pid=1\n"
                  "2026-10-31 14:27:30 完成\n",
              job={"old_version": "1.9.036", "new_version": "1.9.037"})

    lines = updater.report_pending_install_logs(base_dir=tmp_path)
    assert any("1.9.036 → 1.9.037" in ln for ln in lines)
    assert any("完成" in ln for ln in lines)
    assert updater.report_pending_install_logs(base_dir=tmp_path) == []


def test_failed_install_reported_with_rollback(tmp_path):
    _make_dir(tmp_path, "pan4dex-update-b",
              log="2026-10-31 14:27:08 解压 x.zip\n"
                  "2026-10-31 14:27:20 失败：目标目录被占用\n"
                  "2026-10-31 14:27:21 已回滚旧版本目录\n",
              job={"old_version": "1.9.036", "new_version": "1.9.037"})

    lines = updater.report_pending_install_logs(base_dir=tmp_path)
    assert any("失败：目标目录被占用" in ln for ln in lines)


def test_midrun_install_skipped_until_stale(tmp_path):
    """脚本无终态且目录还新：可能仍在安装，不报、不打标记"""
    _make_dir(tmp_path, "pan4dex-update-c",
              log="2026-10-31 14:27:08 解压 x.zip\n",
              job={"old_version": "1.9.036", "new_version": "1.9.037"})

    assert updater.report_pending_install_logs(base_dir=tmp_path) == []
    assert updater.report_pending_install_logs(base_dir=tmp_path) == []


def test_missing_log_reported_when_stale(tmp_path):
    _make_dir(tmp_path, "pan4dex-update-d",
              job={"old_version": "1.9.036", "new_version": "1.9.037"},
              mtime=7200)

    lines = updater.report_pending_install_logs(base_dir=tmp_path)
    assert any("日志缺失" in ln for ln in lines)


def test_interrupted_install_reported_when_stale(tmp_path):
    _make_dir(tmp_path, "pan4dex-update-e",
              log="2026-10-31 14:27:08 解压 x.zip\n",
              job={"old_version": "1.9.036", "new_version": "1.9.037"},
              mtime=7200)

    lines = updater.report_pending_install_logs(base_dir=tmp_path)
    assert any("无终态" in ln for ln in lines)


def test_unrelated_dirs_ignored(tmp_path):
    _make_dir(tmp_path, "some-other-dir", log="完成\n")
    assert updater.report_pending_install_logs(base_dir=tmp_path) == []
