"""
Pan4dex 万格 — M2 文件操作测试
"""
import pytest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFileOperations:
    """测试 FileOperations 类"""
    
    def setup_method(self):
        """每个测试前创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.dest_dir = os.path.join(self.temp_dir, "dest")
        os.makedirs(self.source_dir)
        os.makedirs(self.dest_dir)
        
        # 创建测试文件
        self.test_file = os.path.join(self.source_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("Hello World")
        
        # 创建子目录和文件
        self.subdir = os.path.join(self.source_dir, "subdir")
        os.makedirs(self.subdir)
        self.subfile = os.path.join(self.subdir, "sub.txt")
        with open(self.subfile, 'w') as f:
            f.write("Sub file")
        
        from core.file_operations import FileOperations
        self.ops = FileOperations()
    
    def teardown_method(self):
        """每个测试后清理临时目录"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_copy_single_file(self):
        """测试复制单个文件"""
        result = self.ops.copy([self.test_file], self.dest_dir)
        
        assert result.success
        assert os.path.exists(os.path.join(self.dest_dir, "test.txt"))
        assert open(os.path.join(self.dest_dir, "test.txt")).read() == "Hello World"
    
    def test_copy_directory(self):
        """测试复制目录"""
        result = self.ops.copy([self.source_dir], self.dest_dir)
        
        assert result.success
        assert os.path.exists(os.path.join(self.dest_dir, "source", "test.txt"))
        assert os.path.exists(os.path.join(self.dest_dir, "source", "subdir", "sub.txt"))
    
    def test_copy_multiple_files(self):
        """测试复制多个文件"""
        file2 = os.path.join(self.source_dir, "test2.txt")
        with open(file2, 'w') as f:
            f.write("File 2")
        
        result = self.ops.copy([self.test_file, file2], self.dest_dir)
        
        assert result.success
        assert result.files_affected == 2
    
    def test_copy_to_nonexistent_dest(self):
        """测试复制到不存在的目标目录"""
        result = self.ops.copy([self.test_file], "/nonexistent/path")
        
        assert not result.success
        assert "不存在" in result.error
    
    def test_move_file(self):
        """测试移动文件"""
        result = self.ops.move([self.test_file], self.dest_dir)
        
        assert result.success
        assert os.path.exists(os.path.join(self.dest_dir, "test.txt"))
        assert not os.path.exists(self.test_file)
    
    def test_move_directory(self):
        """测试移动目录"""
        result = self.ops.move([self.source_dir], self.dest_dir)
        
        assert result.success
        assert os.path.exists(os.path.join(self.dest_dir, "source", "test.txt"))
        assert not os.path.exists(self.source_dir)
    
    def test_delete_file(self):
        """测试删除文件"""
        result = self.ops.delete([self.test_file], safe=False)
        
        assert result.success
        assert not os.path.exists(self.test_file)
    
    def test_delete_directory(self):
        """测试删除目录"""
        result = self.ops.delete([self.subdir], safe=False)
        
        assert result.success
        assert not os.path.exists(self.subdir)
    
    def test_delete_nonexistent(self):
        """测试删除不存在的文件"""
        result = self.ops.delete(["/nonexistent/file.txt"], safe=False)
        
        assert not result.success
    
    def test_rename_file(self):
        """测试重命名文件"""
        result = self.ops.rename(self.test_file, "renamed.txt")
        
        assert result.success
        assert os.path.exists(os.path.join(self.source_dir, "renamed.txt"))
        assert not os.path.exists(self.test_file)
    
    def test_rename_to_existing_name(self):
        """测试重命名为已存在的名称"""
        # 创建目标文件
        existing = os.path.join(self.source_dir, "existing.txt")
        with open(existing, 'w') as f:
            f.write("existing")
        
        result = self.ops.rename(self.test_file, "existing.txt")
        
        assert not result.success
        assert "已存在" in result.error
    
    def test_create_folder(self):
        """测试创建文件夹"""
        result = self.ops.create_folder(self.source_dir, "new_folder")
        
        assert result.success
        assert os.path.exists(os.path.join(self.source_dir, "new_folder"))
    
    def test_create_folder_avoid_duplicate(self):
        """测试创建文件夹避免重名"""
        # 先创建第一个
        self.ops.create_folder(self.source_dir, "new_folder")
        
        # 再创建同名
        result = self.ops.create_folder(self.source_dir, "new_folder")
        
        assert result.success
        assert os.path.exists(os.path.join(self.source_dir, "new_folder (1)"))
    
    def test_create_file(self):
        """测试创建文件"""
        result = self.ops.create_file(self.source_dir, "new_file.txt")
        
        assert result.success
        assert os.path.exists(os.path.join(self.source_dir, "new_file.txt"))
    
    def test_create_file_avoid_duplicate(self):
        """测试创建文件避免重名"""
        # 先创建第一个
        self.ops.create_file(self.source_dir, "new_file.txt")
        
        # 再创建同名
        result = self.ops.create_file(self.source_dir, "new_file.txt")
        
        assert result.success
        assert os.path.exists(os.path.join(self.source_dir, "new_file (1).txt"))
    
    def test_progress_callback(self):
        """测试进度回调（契约：callback(percent, filename, copied_bytes, total_bytes)）"""
        progress_values = []

        def on_progress(percent, filename, copied_bytes=0, total_bytes=0):
            progress_values.append(percent)

        self.ops.set_progress_callback(on_progress)
        self.ops.copy([self.test_file], self.dest_dir)

        assert len(progress_values) > 0
        assert progress_values[-1] == 100
    
    def test_calculate_checksum_md5(self):
        """测试计算 MD5 校验和"""
        checksum = self.ops.calculate_checksum(self.test_file, "md5")
        
        assert len(checksum) == 32  # MD5 长度为 32
        assert all(c in '0123456789abcdef' for c in checksum)
    
    def test_calculate_checksum_sha256(self):
        """测试计算 SHA256 校验和"""
        checksum = self.ops.calculate_checksum(self.test_file, "sha256")
        
        assert len(checksum) == 64  # SHA256 长度为 64
    
    def test_copy_with_subdirectories(self):
        """测试复制包含子目录的目录结构"""
        # 创建深层目录结构
        deep_dir = os.path.join(self.subdir, "deep")
        os.makedirs(deep_dir)
        deep_file = os.path.join(deep_dir, "deep.txt")
        with open(deep_file, 'w') as f:
            f.write("deep")
        
        result = self.ops.copy([self.source_dir], self.dest_dir)
        
        assert result.success
        assert os.path.exists(os.path.join(self.dest_dir, "source", "subdir", "deep", "deep.txt"))


class TestPaneFileOperations:
    """测试 Pane 中的文件操作集成"""
    
    def test_pane_has_file_ops(self, qtbot):
        """测试窗格有 file_ops 实例"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test")
        qtbot.addWidget(pane)
        
        assert hasattr(pane, 'file_ops')
        assert pane.file_ops is not None
    
    def test_pane_has_clipboard(self, qtbot):
        """测试窗格有剪贴板"""
        from core.pane import Pane
        
        pane = Pane(pane_id="test")
        qtbot.addWidget(pane)
        
        assert hasattr(pane, 'clipboard')
        assert pane.clipboard == []
        assert pane.clipboard_action is None


class TestRemovalWording:
    """删除确认文案与「目标在源内部」判据（两个入口共用，故直接测函数本身）

    这两段话原先长在 `Pane` 里，搜索结果列表做删除时只有两条路：抄第二份（文案
    一定会漂）或者说错话（网络位置没有回收站，却写「移到回收站」）。抽到
    `core/file_operations.py` 后，措辞的对错就归这几个用例管。
    """

    @pytest.mark.skipif(os.name != "nt", reason="回收站/网络盘说法是 Windows 特有")
    def test_local_wording_says_recycle_bin(self, tmp_path):
        from core.file_operations import describe_removal
        paths = [os.path.join(str(tmp_path), f"f{i}.txt") for i in range(3)]
        title, body = describe_removal(paths)
        assert title == "确认删除"
        assert "移到回收站" in body and "永久删除" not in body
        assert "f0.txt" in body and "3" in body

    @pytest.mark.skipif(os.name != "nt", reason="回收站/网络盘说法是 Windows 特有")
    def test_network_paths_are_reported_as_permanent(self, monkeypatch):
        """网络位置没有回收站：必须说明是永久删除，不能承诺可恢复"""
        from core import file_operations as fo
        monkeypatch.setattr(fo, "_is_network_path", lambda p: p.startswith("\\\\srv"))
        title, body = fo.describe_removal([r"\\srv\share\a.txt",
                                           r"\\srv\share\b.txt",
                                           r"C:\local\c.txt"])
        assert title == "确认删除"
        assert "网络位置的 2 个项目将被永久删除" in body
        assert "本地的 1 个项目将移到回收站" in body

    def test_permanent_wording_applies_to_local_paths(self, tmp_path):
        from core.file_operations import describe_removal
        title, body = describe_removal([os.path.join(str(tmp_path), "a.txt")],
                                        permanent=True)
        assert title == "确认永久删除"
        assert "不可恢复" in body and "回收站" not in body

    def test_only_the_first_five_names_are_listed(self, tmp_path):
        from core.file_operations import describe_removal
        paths = [os.path.join(str(tmp_path), f"n{i}.txt") for i in range(7)]
        _title, body = describe_removal(paths)
        assert "n4.txt" in body and "n5.txt" not in body
        assert "等共 7 项" in body

    def test_move_into_own_subtree_is_detected(self, tmp_path):
        from core.file_operations import move_target_inside_sources
        outer = os.path.join(str(tmp_path), "outer")
        inner = os.path.join(outer, "inner")
        os.makedirs(inner)
        a_file = os.path.join(str(tmp_path), "a.txt")
        open(a_file, "w").close()
        assert move_target_inside_sources([outer], inner) is True
        assert move_target_inside_sources([outer], outer) is True
        # 文件不是目录：它没有「内部」可言，不该被当成源目录
        assert move_target_inside_sources([a_file], inner) is False
        # 名字以源为前缀的兄弟目录不是子目录（用 `startswith(源)` 判就会误拦）
        sibling = os.path.join(str(tmp_path), "outer_backup")
        os.makedirs(sibling)
        assert move_target_inside_sources([outer], sibling) is False
