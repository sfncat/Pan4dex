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


def test_batch_handles_chinese_filenames(tmp_path):
    """中文文件名必须能读到拍摄日期：Windows 上 exiftool 命令行参数按系统
    ANSI 代码页解读，中文名会得到 "No matching files"——文件名必须走
    UTF-8 参数文件（-@ + -charset filename=utf8）。"""
    from core.media_metadata import _find_exiftool, batch_get_shot_dates
    exif = _find_exiftool()
    if not exif:
        pytest.skip("无 exiftool")
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("无 Pillow")

    f = tmp_path / "照片 测试.jpg"
    Image.new("RGB", (8, 8), (10, 120, 60)).save(f, quality=90)
    # 写 EXIF 同样走参数文件：命令行传中文名同样会 "No matching files"
    import subprocess
    args = tmp_path / "exif.args"
    args.write_text(
        "-overwrite_original\n-DateTimeOriginal=2023:08:15 10:30:00\n"
        f"{f}\n", encoding="utf-8")
    subprocess.run(
        [exif, "-charset", "filename=utf8", "-@", str(args)],
        capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    res = batch_get_shot_dates([str(f)])
    assert res.get(str(f)) == "2023-08-15 10:30"
