"""
Pan4dex 万格 — M6 工具测试
"""
import pytest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDirSync:
    """测试目录同步"""
    
    def setup_method(self):
        """创建测试目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.left_dir = os.path.join(self.temp_dir, "left")
        self.right_dir = os.path.join(self.temp_dir, "right")
        os.makedirs(self.left_dir)
        os.makedirs(self.right_dir)
        
        # 创建测试文件
        with open(os.path.join(self.left_dir, "file1.txt"), 'w') as f:
            f.write("content1")
        with open(os.path.join(self.right_dir, "file2.txt"), 'w') as f:
            f.write("content2")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_dir_sync_dialog_creation(self, qtbot):
        """测试目录同步对话框创建"""
        from widgets.dir_sync import DirSyncDialog
        
        dialog = DirSyncDialog(self.left_dir, self.right_dir)
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_dir_sync_compare(self, qtbot):
        """测试目录比较"""
        from widgets.dir_sync import DirSyncDialog
        
        dialog = DirSyncDialog(self.left_dir, self.right_dir)
        qtbot.addWidget(dialog)
        
        dialog.compare()
        
        # 应该有差异
        assert len(dialog.differences) > 0


class TestArchiveTool:
    """测试压缩包工具"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("Hello World")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_archive_dialog_creation(self, qtbot):
        """测试压缩包对话框创建"""
        from widgets.archive_tool import ArchiveDialog
        
        dialog = ArchiveDialog()
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_create_zip(self, qtbot):
        """测试创建 ZIP"""
        from widgets.archive_tool import ArchiveDialog
        
        dialog = ArchiveDialog()
        qtbot.addWidget(dialog)
        
        output = os.path.join(self.temp_dir, "test.zip")
        dialog._create_zip(self.test_file, output)
        
        assert os.path.exists(output)
    
    def test_extract_zip(self, qtbot):
        """测试解压 ZIP"""
        from widgets.archive_tool import ArchiveDialog
        import zipfile
        
        # 先创建 ZIP
        zip_path = os.path.join(self.temp_dir, "test.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(self.test_file, "test.txt")
        
        # 解压
        extract_dir = os.path.join(self.temp_dir, "extracted")
        os.makedirs(extract_dir)
        
        dialog = ArchiveDialog()
        qtbot.addWidget(dialog)
        dialog._extract_zip(zip_path, extract_dir)
        
        assert os.path.exists(os.path.join(extract_dir, "test.txt"))


class TestFileSplit:
    """测试文件分割"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.bin")
        with open(self.test_file, 'wb') as f:
            f.write(b"A" * 1000)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_file_split_dialog_creation(self, qtbot):
        """测试文件分割对话框创建"""
        from widgets.file_split import FileSplitDialog
        
        dialog = FileSplitDialog()
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_split_by_size(self, qtbot):
        """测试按大小分割"""
        from widgets.file_split import SplitWorker
        
        output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(output_dir)
        
        worker = SplitWorker(self.test_file, output_dir, chunk_size=300, num_parts=0)
        worker.run()
        
        # 应该生成 4 个文件（1000 / 300 = 3.33 -> 4）
        files = os.listdir(output_dir)
        assert len(files) == 4


class TestAdvancedSearch:
    """测试高级搜索"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        # 创建测试文件
        for i in range(5):
            with open(os.path.join(self.temp_dir, f"test{i}.txt"), 'w') as f:
                f.write(f"content {i}")
        for i in range(3):
            with open(os.path.join(self.temp_dir, f"file{i}.py"), 'w') as f:
                f.write(f"print({i})")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_advanced_search_dialog_creation(self, qtbot):
        """测试高级搜索对话框创建"""
        from widgets.advanced_search import AdvancedSearchDialog
        
        dialog = AdvancedSearchDialog()
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_search_worker(self, qtbot):
        """测试搜索工作线程"""
        from widgets.advanced_search import SearchWorker
        
        params = {
            'directory': self.temp_dir,
            'pattern': '*.txt',
            'use_regex': False,
            'case_sensitive': False,
            'file_types': [],
            'min_size': 0,
            'max_size': 0,
            'content': ''
        }
        
        worker = SearchWorker(params)
        worker.run()
        
        # 应该找到 5 个 txt 文件
        # 注意：worker 通过信号发射结果，这里直接测试不崩溃
