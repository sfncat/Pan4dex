# -*- coding: utf-8 -*-
""".md 双击走系统默认应用：去掉硬编码 gedit + 老配置一次性迁移。

改前：默认表把 .md 写成 gedit，open_file() 「用户关联优先」直接 spawn gedit
并 return，_open_with_default() 的 xdg-open 永远没机会跑——用户在系统里换了
默认 Markdown 应用也不生效。这里钉住「无 .md 关联」这个新语义。
"""
import json
import os

from config.file_associations import FileAssociations


def _write(cfg_dir, data):
    os.makedirs(cfg_dir, exist_ok=True)
    path = os.path.join(cfg_dir, "associations.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_fresh_config_has_no_hardcoded_md(tmp_path):
    fa = FileAssociations(config_dir=str(tmp_path))
    assert ".md" not in fa.associations
    assert ".md" not in _read(fa.config_file)


def test_legacy_gedit_entry_is_migrated_once(tmp_path):
    path = _write(str(tmp_path), {".md": {"app": "gedit", "args": []},
                                  ".txt": {"app": "gedit", "args": []}})
    fa = FileAssociations(config_dir=str(tmp_path))
    assert ".md" not in fa.associations
    assert ".md" not in _read(path)
    assert fa.associations[".txt"]["app"] == "gedit"   # 别的关联不动


def test_user_chosen_md_app_is_preserved(tmp_path):
    chosen = {"app": "typora", "args": ["--flag"]}
    path = _write(str(tmp_path), {".md": chosen})
    fa = FileAssociations(config_dir=str(tmp_path))
    assert fa.associations[".md"] == chosen
    assert _read(path)[".md"] == chosen


def test_md_without_association_goes_to_system_default(tmp_path, monkeypatch):
    """没有 .md 关联时 open_file 必须落到 _open_with_default（xdg-open 入口）"""
    path = str(tmp_path / "note.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# hi")
    fa = FileAssociations(config_dir=str(tmp_path / "cfg"))
    assert ".md" not in fa.associations

    called = []
    monkeypatch.setattr(fa, "_open_with_default", lambda p: called.append(p) or True)
    assert fa.open_file(path) is True
    assert called == [path]


def test_migration_does_not_rewrite_config_on_every_start(tmp_path, monkeypatch):
    """迁移只应发生一次：第二次启动读到干净配置，不该再触发 save"""
    path = _write(str(tmp_path), {".md": {"app": "gedit", "args": []}})
    FileAssociations(config_dir=str(tmp_path))

    saves = []
    monkeypatch.setattr(FileAssociations, "save", lambda self: saves.append(1))
    FileAssociations(config_dir=str(tmp_path))
    assert saves == []
