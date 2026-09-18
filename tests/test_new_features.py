"""
Pan4dex 万格 — 新功能测试
测试二进制比较、压缩格式扩展和用户操作配置
"""
import pytest
import os
import sys
import tempfile
import shutil
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBinaryCompare:
    """测试二进制文件比较功能"""
    
    def setup_method(self):
        """创建测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建两个相同的文件
        self.same_file1 = os.path.join(self.temp_dir, "same1.bin")
        self.same_file2 = os.path.join(self.temp_dir, "same2.bin")
        
        with open(self.same_file1, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09')
        
        with open(self.same_file2, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09')
        
        # 创建两个不同的文件
        self.diff_file1 = os.path.join(self.temp_dir, "diff1.bin")
        self.diff_file2 = os.path.join(self.temp_dir, "diff2.bin")
        
        with open(self.diff_file1, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09')
        
        with open(self.diff_file2, 'wb') as f:
            f.write(b'\x00\x01\xFF\x03\x04\x05\x06\x07\x08\x09')  # 第 3 个字节不同
        
        # 创建大小不同的文件
        self.size_diff_file1 = os.path.join(self.temp_dir, "size_diff1.bin")
        self.size_diff_file2 = os.path.join(self.temp_dir, "size_diff2.bin")
        
        with open(self.size_diff_file1, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09')
        
        with open(self.size_diff_file2, 'wb') as f:
            f.write(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B')
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_binary_compare_same_files(self, qtbot):
        """测试相同文件的二进制比较"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.same_file1, self.same_file2)
        qtbot.addWidget(dialog)
        
        # 切换到二进制模式
        dialog.mode_combo.setCurrentIndex(1)
        
        # 比较
        dialog.compare()
        
        # 验证结果 - 应该没有差异
        result_text = dialog.binary_result.toPlainText()
        assert "完全相同" in result_text or "0 处差异" in result_text
    
    def test_binary_compare_different_files(self, qtbot):
        """测试不同文件的二进制比较"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.diff_file1, self.diff_file2)
        qtbot.addWidget(dialog)
        
        # 切换到二进制模式
        dialog.mode_combo.setCurrentIndex(1)
        
        # 比较
        dialog.compare()
        
        # 验证结果 - 应该有差异
        result_text = dialog.binary_result.toPlainText()
        assert "差异" in result_text or "发现" in result_text
    
    def test_binary_compare_size_mismatch(self, qtbot):
        """测试大小不同的文件比较"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.size_diff_file1, self.size_diff_file2)
        qtbot.addWidget(dialog)
        
        # 切换到二进制模式
        dialog.mode_combo.setCurrentIndex(1)
        
        # 比较
        dialog.compare()
        
        # 验证结果 - 应该提示大小不同
        result_text = dialog.binary_result.toPlainText()
        assert "大小不同" in result_text or "文件大小" in result_text
    
    def test_format_size(self):
        """测试文件大小格式化"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog()
        
        assert "B" in dialog.format_size(100)
        assert "KB" in dialog.format_size(1024 * 100)
        assert "MB" in dialog.format_size(1024 * 1024 * 100)
        assert "GB" in dialog.format_size(1024 * 1024 * 1024 * 100)
    
    def test_export_html_report(self, qtbot):
        """测试导出 HTML 报告"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.diff_file1, self.diff_file2)
        qtbot.addWidget(dialog)
        
        # 切换到二进制模式并比较
        dialog.mode_combo.setCurrentIndex(1)
        dialog.compare()
        
        # 导出为 HTML
        html_path = os.path.join(self.temp_dir, "report.html")
        dialog._export_html(html_path)
        
        # 验证文件存在且包含内容
        assert os.path.exists(html_path)
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "<html" in content.lower()
            assert "文件比较报告" in content
            assert self.diff_file1 in content
            assert self.diff_file2 in content
    
    def test_export_text_report(self, qtbot):
        """测试导出文本报告"""
        from widgets.file_compare import FileCompareDialog
        
        dialog = FileCompareDialog(self.diff_file1, self.diff_file2)
        qtbot.addWidget(dialog)
        
        # 切换到二进制模式并比较
        dialog.mode_combo.setCurrentIndex(1)
        dialog.compare()
        
        # 导出为文本
        txt_path = os.path.join(self.temp_dir, "report.txt")
        dialog._export_text(txt_path)
        
        # 验证文件存在且包含内容
        assert os.path.exists(txt_path)
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "文件比较报告" in content
            assert self.diff_file1 in content
            assert self.diff_file2 in content


class TestArchiveFormatSupport:
    """测试扩展的压缩格式支持"""
    
    def setup_method(self):
        """创建测试目录和文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        
        with open(self.test_file, 'w') as f:
            f.write("Test content for archive")
        
        self.subdir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(self.subdir)
        
        self.subfile = os.path.join(self.subdir, "subfile.txt")
        with open(self.subfile, 'w') as f:
            f.write("Subdirectory file content")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_find_7z_tool(self, qtbot):
        """测试查找 7z 工具"""
        from widgets.archive_tool import ArchiveDialog
        
        dialog = ArchiveDialog()
        
        # _find_7z 可能返回 None（如果未安装），但不应崩溃
        result = dialog._find_7z()
        assert result is None or os.path.exists(result)
    
    def test_find_rar_tool(self, qtbot):
        """测试查找 rar 工具"""
        from widgets.archive_tool import ArchiveDialog
        
        dialog = ArchiveDialog()
        
        # _find_rar 可能返回 None（如果未安装），但不应崩溃
        result = dialog._find_rar()
        assert result is None or os.path.exists(result)
    
    def test_create_zip_archive(self, qtbot):
        """测试创建 ZIP 压缩包"""
        from widgets.archive_tool import ArchiveDialog
        
        output_zip = os.path.join(self.temp_dir, "test.zip")
        
        dialog = ArchiveDialog()
        dialog.file_edit.setText(self.temp_dir)
        dialog.out_edit.setText(output_zip)
        dialog.format_combo.setCurrentIndex(0)  # ZIP
        
        # 直接调用内部方法
        dialog._create_zip(self.temp_dir, output_zip)
        
        # 验证 ZIP 文件创建成功
        assert os.path.exists(output_zip)
        
        # 验证可以打开
        import zipfile
        with zipfile.ZipFile(output_zip, 'r') as zf:
            assert len(zf.namelist()) > 0
    
    def test_create_tar_gz_archive(self, qtbot):
        """测试创建 TAR.GZ 压缩包"""
        from widgets.archive_tool import ArchiveDialog
        
        output_tar = os.path.join(self.temp_dir, "test.tar.gz")
        
        dialog = ArchiveDialog()
        dialog.format_combo.setCurrentIndex(1)  # TAR.GZ
        
        # 直接调用内部方法
        dialog._create_tar(self.temp_dir, output_tar, "gz")
        
        # 验证 TAR.GZ 文件创建成功
        assert os.path.exists(output_tar)
    
    def test_browse_output_with_format(self, qtbot):
        """测试浏览输出路径时自动添加扩展名"""
        from widgets.archive_tool import ArchiveDialog
        
        dialog = ArchiveDialog()
        
        # 设置格式为 7Z
        dialog.format_combo.setCurrentIndex(3)
        
        # 测试 browse_output 逻辑
        fmt = dialog.format_combo.currentText()
        ext_map = {
            "ZIP": ".zip",
            "TAR.GZ": ".tar.gz",
            "TAR.BZ2": ".tar.bz2",
            "7Z": ".7z",
            "RAR": ".rar"
        }
        
        default_ext = ext_map.get(fmt, ".zip")
        assert default_ext == ".7z"
    
    def test_invalid_format_handling(self, qtbot):
        """测试不支持的格式处理"""
        from widgets.archive_tool import ArchiveDialog
        from unittest.mock import patch
        
        dialog = ArchiveDialog()
        
        # 模拟不支持的格式
        with patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
            dialog.create_archive()  # 无输入，应显示警告
            assert mock_warning.called


class TestUserOperationsConfig:
    """测试用户操作配置管理"""
    
    def setup_method(self):
        """创建临时配置目录"""
        self.temp_config_dir = tempfile.mkdtemp()
        self.config_manager = None
        
        # 导入时使用临时目录
        from config.user_operations import UserOperationsConfig
        self.config_manager = UserOperationsConfig(self.temp_config_dir)
    
    def teardown_method(self):
        if self.config_manager:
            shutil.rmtree(self.temp_config_dir, ignore_errors=True)
    
    def test_config_initialization(self):
        """测试配置初始化"""
        assert self.config_manager is not None
        assert os.path.exists(self.config_manager.config_dir)
        assert hasattr(self.config_manager, 'operations')
    
    def test_default_operations(self):
        """测试默认操作加载"""
        operations = self.config_manager.get_operations()
        assert len(operations) >= 2  # 至少有两个默认操作
    
    def test_add_operation(self):
        """测试添加新操作"""
        operation = {
            'name': 'Test Operation',
            'command': 'echo {}',
            'description': 'A test operation',
            'file_types': ['.txt']
        }
        
        op_id = self.config_manager.add_operation(operation)
        
        assert op_id is not None
        assert isinstance(op_id, str)
        
        # 验证操作已添加
        all_ops = self.config_manager.get_operations(enabled_only=False)
        op_ids = [op['id'] for op in all_ops]
        assert op_id in op_ids
    
    def test_update_operation(self):
        """测试更新操作"""
        # 先添加一个操作
        operation = {
            'name': 'Original Name',
            'command': 'original {}',
            'description': 'Original description',
            'file_types': ['.txt']
        }
        
        op_id = self.config_manager.add_operation(operation)
        
        # 更新操作
        updates = {
            'name': 'Updated Name',
            'description': 'Updated description'
        }
        
        result = self.config_manager.update_operation(op_id, updates)
        assert result is True
        
        # 验证更新
        updated_op = self.config_manager.get_operation_by_id(op_id)
        assert updated_op['name'] == 'Updated Name'
        assert updated_op['description'] == 'Updated description'
    
    def test_delete_operation(self):
        """测试删除操作"""
        # 先添加一个操作
        operation = {
            'name': 'ToDelete',
            'command': 'test {}',
            'description': 'To delete',
            'file_types': ['.txt']
        }
        
        op_id = self.config_manager.add_operation(operation)
        
        # 删除操作
        result = self.config_manager.delete_operation(op_id)
        assert result is True
        
        # 验证操作已删除
        deleted_op = self.config_manager.get_operation_by_id(op_id)
        assert deleted_op is None
    
    def test_enable_disable_operation(self):
        """测试启用/禁用操作"""
        # 添加操作
        operation = {
            'name': 'Toggle Op',
            'command': 'test {}',
            'description': 'Toggle test',
            'file_types': ['.txt']
        }
        
        op_id = self.config_manager.add_operation(operation)
        
        # 禁用操作
        self.config_manager.enable_operation(op_id, enabled=False)
        ops = self.config_manager.get_operations(enabled_only=True)
        op_ids = [op['id'] for op in ops]
        assert op_id not in op_ids
        
        # 重新启用
        self.config_manager.enable_operation(op_id, enabled=True)
        ops = self.config_manager.get_operations(enabled_only=True)
        op_ids = [op['id'] for op in ops]
        assert op_id in op_ids
    
    def test_execute_command(self):
        """测试执行命令"""
        # 创建一个简单的测试命令
        command = 'echo test_success'
        
        success, output = self.config_manager.execute_command(command, '/dev/null')
        
        # 命令执行应成功
        assert success is True
    
    def test_unique_operation_id(self):
        """测试生成唯一操作 ID"""
        # 添加多个同名操作
        for i in range(3):
            operation = {
                'name': f'Duplicate Op {i}',
                'command': f'test{i} {{}}',
                'description': 'Duplicate test',
                'file_types': ['.txt']
            }
            self.config_manager.add_operation(operation)
        
        # 所有操作应有唯一的 ID
        all_ops = self.config_manager.get_operations(enabled_only=False)
        op_ids = [op['id'] for op in all_ops]
        assert len(op_ids) == len(set(op_ids))  # 无重复


class TestUserOperationsDialog:
    """测试用户操作配置对话框"""
    
    def setup_method(self):
        """创建配置管理器"""
        self.temp_config_dir = tempfile.mkdtemp()
        from config.user_operations import UserOperationsConfig
        self.config_manager = UserOperationsConfig(self.temp_config_dir)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_config_dir, ignore_errors=True)
    
    def test_dialog_creation(self, qtbot):
        """测试对话框创建"""
        from widgets.user_operations_dialog import UserOperationsDialog
        
        dialog = UserOperationsDialog(self.config_manager)
        qtbot.addWidget(dialog)
        
        assert dialog is not None
        assert dialog.windowTitle() == "用户操作配置"
    
    def test_dialog_load_operations(self, qtbot):
        """测试加载操作列表"""
        from widgets.user_operations_dialog import UserOperationsDialog
        
        # 先添加一些操作
        for i in range(3):
            operation = {
                'name': f'Test Op {i}',
                'command': f'test{i} {{}}',
                'description': f'Description {i}',
                'file_types': ['.txt']
            }
            self.config_manager.add_operation(operation)
        
        dialog = UserOperationsDialog(self.config_manager)
        qtbot.addWidget(dialog)
        
        # 等待 UI 更新
        qtbot.wait(100)
        
        # 验证操作列表中有条目
        assert dialog.op_list.count() >= 3
    
    def test_dialog_add_operation(self, qtbot):
        """测试对话框添加操作"""
        from widgets.user_operations_dialog import UserOperationsDialog
        
        dialog = UserOperationsDialog(self.config_manager)
        qtbot.addWidget(dialog)
        
        # 填写表单
        dialog.name_edit.setText("New Test Operation")
        dialog.cmd_edit.setText("new_test {}")
        dialog.desc_edit.setText("New test description")
        dialog.file_types_edit.setText(".txt,.log")
        
        # 点击添加按钮
        dialog.add_operation()
        
        # 验证操作已添加
        operations = self.config_manager.get_operations()
        names = [op['name'] for op in operations]
        assert "New Test Operation" in names
    
    def test_dialog_edit_operation(self, qtbot):
        """测试对话框编辑操作"""
        from widgets.user_operations_dialog import UserOperationsDialog
        
        # 先添加一个操作
        operation = {
            'name': 'Original Name',
            'command': 'original {}',
            'description': 'Original',
            'file_types': ['.txt']
        }
        self.config_manager.add_operation(operation)
        
        dialog = UserOperationsDialog(self.config_manager)
        qtbot.addWidget(dialog)
        
        # 选择第一个操作
        dialog.op_list.setCurrentRow(0)
        qtbot.wait(100)
        
        # 修改字段
        dialog.name_edit.setText("Edited Name")
        dialog.cmd_edit.setText("edited {}")
        
        # 点击编辑按钮
        dialog.edit_operation()
        
        # 验证操作已更新
        edited_op = self.config_manager.get_operation_by_id(operation['id'])
        assert edited_op['name'] == "Edited Name"
    
    def test_dialog_delete_operation(self, qtbot):
        """测试对话框删除操作"""
        from widgets.user_operations_dialog import UserOperationsDialog
        from PyQt6.QtWidgets import QMessageBox
        
        # 先添加一个操作
        operation = {
            'name': 'ToDelete',
            'command': 'delete {}',
            'description': 'Delete me',
            'file_types': ['.txt']
        }
        self.config_manager.add_operation(operation)
        
        dialog = UserOperationsDialog(self.config_manager)
        qtbot.addWidget(dialog)
        
        # 选择要删除的操作
        dialog.op_list.setCurrentRow(0)
        
        # Mock 确认对话框
        with qtbot.waitSignal(QMessageBox.buttonClicked, timeout=1000) as signal:
            # 模拟点击 Yes
            QMessageBox.button = lambda self, parent, caption, standardButtons: QMessageBox.StandardButton.Yes
            dialog.delete_operation()
        
        # 验证操作已删除
        deleted_op = self.config_manager.get_operation_by_id(operation['id'])
        assert deleted_op is None


class TestIntegration:
    """集成测试"""
    
    def setup_method(self):
        """创建测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        
        # 创建测试文件
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("Integration test content")
        
        # 创建配置
        self.temp_config = tempfile.mkdtemp()
        from config.user_operations import UserOperationsConfig
        self.config = UserOperationsConfig(self.temp_config)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.temp_config, ignore_errors=True)
    
    def test_full_workflow(self, qtbot):
        """测试完整工作流程"""
        from widgets.file_compare import FileCompareDialog
        
        # 1. 创建另一个文件进行比较
        other_file = os.path.join(self.temp_dir, "other.txt")
        with open(other_file, 'w') as f:
            f.write("Different content")
        
        # 2. 比较文件
        dialog = FileCompareDialog(self.test_file, other_file)
        qtbot.addWidget(dialog)
        dialog.compare()
        
        # 3. 验证有差异
        assert "差异" in dialog.diff_stats.text() or "新增" in dialog.diff_stats.text()
        
        # 4. 导出报告
        report_path = os.path.join(self.temp_dir, "integration_report.html")
        dialog._export_html(report_path)
        assert os.path.exists(report_path)
    
    def test_user_op_integration(self, qtbot):
        """测试用户操作集成"""
        # 1. 添加自定义操作
        operation = {
            'name': 'Integration Test Op',
            'command': 'cat {}',
            'description': 'Integration test',
            'file_types': ['.txt']
        }
        
        op_id = self.config.add_operation(operation)
        assert op_id is not None
        
        # 2. 获取操作并验证
        ops = self.config.get_operations()
        assert any(op['id'] == op_id for op in ops)
        
        # 3. 执行命令
        success, output = self.config.execute_command(operation['command'], self.test_file)
        assert success is True
