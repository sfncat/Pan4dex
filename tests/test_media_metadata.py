"""
Pan4dex 万格 — 拍摄日期（ExifTool）测试
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_clean_date():
    """无效日期（无时间戳视频占位值）应被过滤为空。"""
    from core.media_metadata import _clean_date
    assert _clean_date(None) is None
    assert _clean_date("") is None
    assert _clean_date("0000:00:00 00:00:00") is None
    assert _clean_date("0000:00:00") is None
    assert _clean_date("2023-08-15 10:30") == "2023-08-15 10:30"


def test_shot_date_plain_file(tmp_path):
    """无 EXIF 的普通文件返回 None（缓存后不再重复调用）。"""
    from core.media_metadata import batch_get_shot_dates
    f = tmp_path / "plain.txt"
    f.write_text("x")
    res = batch_get_shot_dates([str(f)])
    assert res.get(str(f)) is None
    # 再次调用应命中缓存，结果一致
    res2 = batch_get_shot_dates([str(f)])
    assert res2.get(str(f)) is None
