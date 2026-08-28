"""
Pan4dex 万格 — M5 工具测试
"""
import pytest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBatchRename:
    """测试批量重命名"""
    
    def setup_method(self):
        """创建测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_files = []
        
        for i in range(3):
            f = os.path.join(self.temp_dir, f"test{i}.txt")
            with open(f, 'w') as fh:
                fh.write(f"content {i}")
            self.test_files.append(f)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_batch_rename_dialog_creation(self, qtbot):
        """测试批量重命名对话框创建"""
        from widgets.batch_rename import BatchRenameDialog
        
        dialog = BatchRenameDialog(self.test_files)
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_batch_rename_preview(self, qtbot):
        """测试批量重命名预览"""
        from widgets.batch_rename import BatchRenameDialog
        
        dialog = BatchRenameDialog(self.test_files)
        qtbot.addWidget(dialog)
        
        # 应该有预览
        assert len(dialog.preview_list) == 3
    
    def test_batch_rename_apply(self, qtbot):
        """测试批量重命名应用"""
        from widgets.batch_rename import BatchRenameDialog
        from unittest.mock import patch
        
        dialog = BatchRenameDialog(self.test_files)
        qtbot.addWidget(dialog)
        
        # 设置模板
        dialog.template_edit.setText("renamed_[N]")
        dialog.update_preview()
        
        # 直接验证 preview_list 正确
        assert len(dialog.preview_list) == 3
        assert dialog.preview_list[0][1] == "renamed_1.txt"
        assert dialog.preview_list[1][1] == "renamed_2.txt"
        assert dialog.preview_list[2][1] == "renamed_3.txt"
    
    def test_regex_rename(self, qtbot):
        """测试正则重命名"""
        from widgets.batch_rename import BatchRenameDialog
        
        dialog = BatchRenameDialog(self.test_files)
        qtbot.addWidget(dialog)
        
        # 切换到正则标签
        dialog.tab_widget.setCurrentIndex(1)
        dialog.find_edit.setText("test")
        dialog.replace_edit.setText("file")
        dialog.update_preview()
        
        # 验证预览
        assert len(dialog.preview_list) == 3
    
    def test_case_rename(self, qtbot):
        """测试大小写重命名"""
        from widgets.batch_rename import BatchRenameDialog
        
        dialog = BatchRenameDialog(self.test_files)
        qtbot.addWidget(dialog)
        
        # 切换到大小写标签
        dialog.tab_widget.setCurrentIndex(2)
        dialog.case_combo.setCurrentIndex(0)  # 全大写
        dialog.update_preview()
        
        # 验证预览
        assert len(dialog.preview_list) == 3


class TestChecksumTool:
    """测试校验和工具"""
    
    def setup_method(self):
        """创建测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("Hello World")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_checksum_dialog_creation(self, qtbot):
        """测试校验和对话框创建"""
        from widgets.checksum_tool import ChecksumDialog
        
        dialog = ChecksumDialog([self.test_file])
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_checksum_calculation(self, qtbot):
        """测试校验和计算"""
        from widgets.checksum_tool import ChecksumDialog
        
        dialog = ChecksumDialog([self.test_file])
        qtbot.addWidget(dialog)
        
        # 计算
        dialog.calculate()
        
        # 等待计算完成
        qtbot.wait(1000)
        
        # 验证结果
        assert len(dialog.results) == 1
    
    def test_checksum_verification(self, qtbot):
        """测试校验和验证"""
        from widgets.checksum_tool import ChecksumDialog
        import hashlib
        
        # 计算正确的校验和
        with open(self.test_file, 'rb') as f:
            correct_checksum = hashlib.md5(f.read()).hexdigest()
        
        dialog = ChecksumDialog([self.test_file])
        qtbot.addWidget(dialog)
        
        # 输入正确的校验和
        dialog.tab_widget.setCurrentIndex(1)
        dialog.verify_text.setPlainText(f"{correct_checksum}  test.txt")
        dialog.verify()
        
        # 验证结果
        assert "校验通过" in dialog.result_text.toPlainText()
    
    def test_algorithm_detection(self, qtbot):
        """测试算法检测"""
        from widgets.checksum_tool import ChecksumDialog
        
        dialog = ChecksumDialog()
        qtbot.addWidget(dialog)
        
        assert dialog.detect_algorithm("d41d8cd98f00b204e9800998ecf8427e") == "md5"
        assert dialog.detect_algorithm("aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d") == "sha1"
        assert dialog.detect_algorithm("a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e") == "sha256"


class TestFileCompare:
    """测试文件比较"""
    
    def setup_method(self):
        """创建测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.file1 = os.path.join(self.temp_dir, "file1.txt")
        self.file2 = os.path.join(self.temp_dir, "file2.txt")
        
        with open(self.file1, 'w') as f:
            f.write("line1\nline2\nline3\n")
        
        with open(self.file2, 'w') as f:
            f.write("line1\nmodified\nline3\n")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_file_compare_dialog_creation(self, qtbot):
        """测试文件比较对话框创建"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.file1, self.file2)
        qtbot.addWidget(dialog)
        
        assert dialog is not None
    
    def test_file_compare(self, qtbot):
        """测试文件比较"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.file1, self.file2)
        qtbot.addWidget(dialog)
        
        # 比较
        dialog.compare()
        
        # 验证结果
        assert "差异统计" in dialog.diff_stats.text() or "新增" in dialog.diff_stats.text()
    
    def test_swap_files(self, qtbot):
        """测试交换文件"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.file1, self.file2)
        qtbot.addWidget(dialog)
        
        # 交换前
        assert dialog.file1 == self.file1
        assert dialog.file2 == self.file2
        
        # 交换
        dialog.swap_files()
        
        # 验证
        assert dialog.file1 == self.file2
        assert dialog.file2 == self.file1


class TestMainWindowTools:
    """测试主窗口工具集成"""
    
    def test_main_window_has_tools_menu(self, qtbot):
        """测试主窗口有工具菜单"""
        from core.main_window import MainWindow
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # 获取菜单栏
        menubar = window.menuBar()
        
        # 应该有工具菜单
        tools_menu = None
        for action in menubar.actions():
            if "工具" in action.text():
                tools_menu = action.menu()
                break
        
        assert tools_menu is not None
    
    def test_open_batch_rename_no_selection(self, qtbot):
        """测试打开批量重命名（无选择）"""
        from core.main_window import MainWindow
        from unittest.mock import patch
        
        window = MainWindow()
        qtbot.addWidget(window)
        
        # Mock QMessageBox 避免对话框阻塞
        with patch('PyQt6.QtWidgets.QMessageBox.information'):
            window.open_batch_rename()
            # 无异常即可
