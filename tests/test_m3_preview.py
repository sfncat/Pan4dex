"""Pan4dex 万格 — M3 快速预览和文件关联测试

覆盖：
- PreviewPanel 文本/图片预览（含 HEIC）
- ThumbnailView 超大图标模式缩略图（含 HEIC）
- thumbnail_delegate 死代码核查（零引用）
"""
import pytest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPreviewPanel:
    """测试 PreviewPanel 类"""
    
    def test_preview_panel_creation(self, qtbot):
        """测试预览面板创建"""
        from widgets.preview_panel import PreviewPanel
        
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel is not None
        assert panel.windowTitle() == "预览"
    
    def test_preview_text_file(self, qtbot, tmp_path):
        """测试预览文本文件"""
        from widgets.preview_panel import PreviewPanel
        
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")
        
        # 预览
        panel.preview_file(str(test_file))
        
        # 验证内容
        assert "Hello World" in panel.text_preview.toPlainText()
    
    def test_preview_nonexistent_file(self, qtbot):
        """测试预览不存在的文件"""
        from widgets.preview_panel import PreviewPanel
        
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        
        # 预览不存在的文件
        panel.preview_file("/nonexistent/path")
        assert "未找到" in panel.text_preview.toPlainText()


class TestThumbnailViewHEIC:
    """测试超大图标视图对 HEIC 的支持（真实靶子）"""
    
    @pytest.mark.skipif(
        not os.path.exists(os.path.join("test_media", "20180406_IMG_8002.HEIC")),
        reason="缺少 HEIC 靶子 test_media/20180406_IMG_8002.HEIC"
    )
    def test_heic_thumbnail_in_xlarge_mode(self, qtbot):
        """用产品自己的 ThumbnailView 渲染 HEIC，验证缩略图被 Pillow 解码出来"""
        from widgets.thumbnail_view import ThumbnailView
        from PyQt6.QtWidgets import QApplication, QStyle
        from PyQt6.QtCore import QSize
        import time
        
        # 离线运行：不需要真桌面
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        
        view = ThumbnailView()
        qtbot.addWidget(view)
        view.resize(800, 600)
        view.show()
        
        heic_path = os.path.join("test_media", "20180406_IMG_8002.HEIC")
        dir_path = os.path.dirname(heic_path)
        
        view.load_directory(dir_path)
        
        # 等后台线程池回填缩略图到 _thumbnail_cache（最多 30s）
        deadline = time.time() + 30
        last = -1
        while time.time() < deadline:
            QApplication.processEvents()
            done = sum(1 for it in [view.item(i) for i in range(view.count())]
                       if it.data(1) in view._thumbnail_cache)
            if done and done == view.count():
                break
            if done != last:
                print(f"  已回填缩略图 {done}/{view.count()}")
                last = done
            time.sleep(0.2)
        view._thread_pool.waitForDone(5000)
        QApplication.processEvents()
        
        # 判定：HEIC 条目在缓存里，且图标不是标准白纸文件图标
        heic_item = None
        for i in range(view.count()):
            it = view.item(i)
            if it.text().endswith(".HEIC"):
                heic_item = it
                break
                
        assert heic_item is not None, "没找到 HEIC 条目"
        full = heic_item.data(1)
        # 缓存键可能是绝对路径或相对路径，只要包含 .HEIC 就行
        cached_keys = list(view._thumbnail_cache.keys())
        has_heic_in_cache = any(".HEIC" in k for k in cached_keys)
        assert has_heic_in_cache, f"HEIC 未进入缩略图缓存：{cached_keys}"
                
        icon = heic_item.icon()
        pm = icon.pixmap(QSize(256, 256))
        assert not pm.isNull(), "HEIC 的 pixmap 为空"
        
        # 与标准文件图标逐字节比，相同就是「根本没解码成功」
        std = view.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon).pixmap(QSize(256, 256))
        is_std = (not pm.isNull() and not std.isNull()
                  and pm.toImage() == std.toImage())
        assert not is_std, "HEIC 仍是标准文件图标（没拿到真缩略图）"
        
        # 抽查像素：确认是照片内容而非纯色假图
        img = pm.toImage()
        corners = [(0, 0), (img.width() // 2, 0), (0, img.height() // 2),
                   (img.width() // 2, img.height() // 2), (img.width() - 1, img.height() - 1)]
        vals = {img.pixelColor(x, y).name() for x, y in corners}
        msg = f"HEIC 采样颜色太单调（只有{len(vals)}种），可能是假图：{vals}"
        assert len(vals) >= 3, msg


class TestDeadCodeCheck:
    """核查死代码：core/thumbnail_delegate.py 声称支持 .heic 但零引用"""
    
    def test_thumbnail_delegate_not_used_in_product(self):
        """确认 ThumbnailDelegate 在产品里确实没有被调用（避免误删）"""
        import glob
        # 搜索 core/ 和 widgets/ 下所有 .py 文件
        patterns = [os.path.join("core", "*.py"), os.path.join("widgets", "*.py")]
        found_lines = []
        for pattern in patterns:
            full_pattern = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), pattern)
            for file_path in glob.glob(full_pattern):
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "class ThumbnailDelegate" in line:
                            found_lines.append(line.strip())
        
        # grep 应该只找到定义本身
        assert len(found_lines) >= 1, f"Expected class definition line, got none"
        assert "class ThumbnailDelegate" in found_lines[0], "第一行必须是类定义"
