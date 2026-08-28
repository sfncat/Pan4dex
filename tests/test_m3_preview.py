"""
Pan4dex 万格 — M3 快速预览和文件关联测试
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
        panel.preview_file("/nonexistent/file.txt")
        
        # 验证
        assert panel.info_label.text() == "选择一个文件以预览"
    
    def test_clear_preview(self, qtbot):
        """测试清除预览"""
        from widgets.preview_panel import PreviewPanel
        
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        
        panel.clear_preview()
        
        assert panel.info_label.text() == "选择一个文件以预览"
        assert panel.text_preview.toPlainText() == ""
    
    def test_format_size(self, qtbot):
        """测试文件大小格式化"""
        from widgets.preview_panel import PreviewPanel
        
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        
        assert panel.format_size(100) == "100.0 B"
        assert panel.format_size(1024) == "1.0 KB"
        assert panel.format_size(1024 * 1024) == "1.0 MB"
        assert panel.format_size(1024 * 1024 * 1024) == "1.0 GB"
    
    def test_preview_large_text_file(self, qtbot, tmp_path):
        """测试预览大文本文件（超过 100KB）"""
        from widgets.preview_panel import PreviewPanel
        
        panel = PreviewPanel()
        qtbot.addWidget(panel)
        
        # 创建大文件
        test_file = tmp_path / "large.txt"
        with open(test_file, 'w') as f:
            f.write("A" * 200 * 1024)  # 200KB
        
        # 预览
        panel.preview_file(str(test_file))
        
        # 验证只显示了前 100KB
        assert "文件过大" in panel.text_preview.toPlainText()


class TestFileAssociations:
    """测试 FileAssociations 类"""
    
    def setup_method(self):
        """每个测试前创建临时配置目录"""
        self.temp_dir = tempfile.mkdtemp()
        from config.file_associations import FileAssociations
        self.associations = FileAssociations(config_dir=self.temp_dir)
    
    def teardown_method(self):
        """每个测试后清理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_default_associations_loaded(self):
        """测试默认关联已加载"""
        assert len(self.associations.associations) > 0
        assert ".txt" in self.associations.associations
    
    def test_get_association(self):
        """测试获取关联"""
        assoc = self.associations.get_association("/path/to/file.txt")
        
        assert assoc is not None
        assert "app" in assoc
        assert "args" in assoc
    
    def test_set_association(self):
        """测试设置关联"""
        self.associations.set_association(".xyz", "myapp", ["--flag"])
        
        assoc = self.associations.get_association("/path/to/file.xyz")
        assert assoc is not None
        assert assoc["app"] == "myapp"
        assert assoc["args"] == ["--flag"]
    
    def test_remove_association(self):
        """测试移除关联"""
        self.associations.set_association(".xyz", "myapp")
        self.associations.remove_association(".xyz")
        
        assoc = self.associations.get_association("/path/to/file.xyz")
        assert assoc is None
    
    def test_save_and_load(self):
        """测试保存和加载"""
        self.associations.set_association(".xyz", "myapp", ["--flag"])
        
        # 创建新实例加载
        from config.file_associations import FileAssociations
        new_associations = FileAssociations(config_dir=self.temp_dir)
        
        assoc = new_associations.get_association("/path/to/file.xyz")
        assert assoc is not None
        assert assoc["app"] == "myapp"
    
    def test_get_all_associations(self):
        """测试获取所有关联"""
        all_assoc = self.associations.get_all_associations()
        
        assert isinstance(all_assoc, dict)
        assert len(all_assoc) > 0
    
    def test_import_export(self, tmp_path):
        """测试导入导出"""
        # 导出
        export_file = str(tmp_path / "export.json")
        self.associations.export_associations(export_file)
        
        assert os.path.exists(export_file)
        
        # 导入到新实例
        new_temp_dir = tempfile.mkdtemp()
        try:
            from config.file_associations import FileAssociations
            new_associations = FileAssociations(config_dir=new_temp_dir)
            new_associations.set_association(".abc", "testapp")
            
            new_associations.import_associations(export_file)
            
            # 验证导入成功
            assoc = new_associations.get_association("/path/to/file.txt")
            assert assoc is not None
        finally:
            shutil.rmtree(new_temp_dir, ignore_errors=True)
    
    def test_open_file_with_default(self):
        """测试使用默认应用打开文件（模拟）"""
        # 创建一个不存在的文件路径，测试回退到默认
        result = self.associations._open_with_default("/nonexistent/file.txt")
        # 应该返回 False 因为文件不存在
        assert result is False
    
    def test_check_app_exists(self):
        """测试检查应用是否存在"""
        # python 应该存在
        assert self.associations._check_app_exists("python") is True
        
        # 不存在的不存在
        assert self.associations._check_app_exists("nonexistent_app_xyz") is False


class TestMainWindowPreview:
    """测试主窗口预览集成"""
    
    def test_main_window_has_preview_panel(self, qtbot):
        """测试主窗口有预览面板"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'preview_panel')
        assert window.preview_panel is not None
    
    def test_main_window_has_file_associations(self, qtbot):
        """测试主窗口有关联配置"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        assert hasattr(window, 'file_associations')
        assert window.file_associations is not None
    
    def test_toggle_preview(self, qtbot):
        """测试切换预览面板"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 初始状态：隐藏
        assert window._preview_toggle is False
        
        # 切换
        window.toggle_preview()
        assert window._preview_toggle is True
        
        # 再次切换
        window.toggle_preview()
        assert window._preview_toggle is False
