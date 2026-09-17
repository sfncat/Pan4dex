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

    def test_local_wording_says_recycle_bin(self, tmp_path):
        """本地位置的文案两端一致（以前这个判据只在 Windows 上做）"""
        from core.file_operations import describe_removal
        paths = [os.path.join(str(tmp_path), f"f{i}.txt") for i in range(3)]
        title, body = describe_removal(paths)
        assert title == "确认删除"
        assert "移到回收站" in body and "永久删除" not in body
        assert "f0.txt" in body and "3" in body

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

    def test_the_network_branch_is_not_windows_only(self, monkeypatch):
        """同一个分类在 POSIX 路径上也要跑（gvfs / CIFS 挂载）

        旧实现把这段锁在 `os.name == 'nt'` 里，Linux 上无论挂的是什么都说
        “移到回收站”—— 而那恰恰是 send2trash 会报错、用户只看到裸 errno 的场景。
        """
        from core import file_operations as fo
        monkeypatch.setattr(fo, "_is_network_path",
                            lambda p: p.startswith("/run/user/1000/gvfs") or p.startswith("/mnt/nas"))
        # 把宿主也当成 POSIX：否则这个用例在 Windows 上跑时，旧版那个
        # `os.name == 'nt'` 门控会“正确”地走进去，测不到它已被打掉
        monkeypatch.setattr(fo.os, "name", "posix")
        title, body = fo.describe_removal([
            "/run/user/1000/gvfs/smb-share:server=gti,share=pub/a.docx",
            "/mnt/nas/b.xlsx",
            "/home/sfnca/c.txt",
        ])
        assert title == "确认删除"
        assert "网络位置的 2 个项目将被永久删除" in body
        assert "本地的 1 个项目将移到回收站" in body
        assert "a.docx" in body and "c.txt" in body

    def test_all_network_paths_never_promise_a_recycle_bin(self, monkeypatch):
        """全是网络位置时不能给出“移到回收站”这个承诺"""
        from core import file_operations as fo
        monkeypatch.setattr(fo, "_is_network_path", lambda p: True)
        _title, body = fo.describe_removal(["/mnt/nas/a", "/mnt/nas/b"])
        assert "移到回收站" not in body and "本地的" not in body
        assert "网络位置的 2 个项目将被永久删除" in body

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


class _FakeTrash:
    """替掉 `send2trash` 模块：记下被丢进来的路径，但不碰真实的回收站"""

    def __init__(self):
        self.calls = []

    def send2trash(self, path):
        self.calls.append(path)


class TestTrashIsForLocalPathsOnly:
    """回收站只给本地位置（行为的半边必须跟上了文案的那半边）

    `describe_removal` 早就开始对网络位置说「将被永久删除、无法恢复」，但
    `delete()` 里走不走回收站的门控还锁在 `os.name == 'nt'`：Linux 上删 CIFS
    共享里的文件，文案说永久删除，代码却把文件丢进 `send2trash` —— 230 真机
    实测它在共享根凭空建了一个 `.Trash-1000/`，既没按承诺删掉，也不是任何
    桌面能看到的回收站。这几个用例钉的是「谁进回收站」而不是「怎么说」。
    """

    @pytest.fixture
    def fake_trash(self, monkeypatch):
        fake = _FakeTrash()
        monkeypatch.setitem(sys.modules, "send2trash", fake)
        return fake

    def test_network_paths_are_never_sent_to_trash(self, tmp_path, monkeypatch, fake_trash):
        from core import file_operations as fo
        f = tmp_path / "on_share.txt"
        f.write_text("x")
        monkeypatch.setattr(fo, "_is_network_path", lambda p: True)

        result = fo.FileOperations().delete([str(f)], safe=True)

        assert result.success and fake_trash.calls == []
        assert not f.exists(), "网络位置该被直接删掉，不是留在原地"
        assert "永久删除" in result.error

    def test_the_no_trash_branch_is_not_windows_only(self, tmp_path, monkeypatch, fake_trash):
        """把宿主当成 POSIX：旧实现在这里会掉进 `send2trash`，新实现不分平台"""
        from core import file_operations as fo
        f = tmp_path / "cifs.txt"
        f.write_text("x")
        monkeypatch.setattr(fo.os, "name", "posix")
        monkeypatch.setattr(fo, "_is_network_path",
                            lambda p: p.startswith(str(tmp_path)))

        result = fo.FileOperations().delete([str(f)], safe=True)

        assert result.success
        assert fake_trash.calls == [], "Linux 上的网络挂载不能走 send2trash"
        assert not f.exists()

    def test_network_directory_is_removed_recursively(self, tmp_path, monkeypatch, fake_trash):
        from core import file_operations as fo
        d = tmp_path / "share_dir"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "a.txt").write_text("x")
        monkeypatch.setattr(fo, "_is_network_path", lambda p: True)

        result = fo.FileOperations().delete([str(d)], safe=True)

        assert result.success and fake_trash.calls == []
        assert not d.exists()

    def test_local_paths_still_go_to_trash(self, tmp_path, monkeypatch, fake_trash):
        """反方向也要钉住：本地文件不能被误当成网络位置而绕过回收站"""
        from core import file_operations as fo
        f = tmp_path / "local.txt"
        f.write_text("x")
        monkeypatch.setattr(fo, "_is_network_path", lambda p: False)

        result = fo.FileOperations().delete([str(f)], safe=True)

        assert result.success
        assert fake_trash.calls == [str(f)]
        assert f.exists(), "回收站由 send2trash 负责搬，我们不该自己删"
        assert result.error == "", "本地删除不该报「网络位置已永久删除」"

    def test_permanent_delete_never_touches_trash(self, tmp_path, monkeypatch, fake_trash):
        from core import file_operations as fo
        f = tmp_path / "shift_del.txt"
        f.write_text("x")
        monkeypatch.setattr(fo, "_is_network_path", lambda p: False)

        result = fo.FileOperations().delete([str(f)], safe=False)

        assert result.success and fake_trash.calls == [] and not f.exists()

    def test_send2trash_prefix_is_normalized_before_removal(self, tmp_path, monkeypatch, fake_trash):
        r"""`\\?\UNC\...`（send2trash 造出的形式）先还原再删

        真 UNC 路径在测试机上造不出来，所以盯「递给 `os.remove` 的是哪个字符串」：
        还原掉长路径前缀这一步是 Windows 分支原有的能力，不能因为改判据而丢。
        """
        from core import file_operations as fo
        seen = []
        # `_is_unc_path` 本身只在 nt 下说事，不伪造宿主就测不到那条还原
        monkeypatch.setattr(fo.os, "name", "nt")
        monkeypatch.setattr(fo, "_is_network_path", lambda p: True)
        monkeypatch.setattr(fo.os.path, "isdir", lambda p: False)
        monkeypatch.setattr(fo.os, "remove", lambda p: seen.append(p))

        fo.FileOperations().delete([r"\\?\UNC\srv\share\a.txt"], safe=True)

        assert seen == [r"\\srv\share\a.txt"]


class TestDropActionRules:
    """拖放默认动作的判据矩阵（对齐资源管理器：同卷移动、跨卷复制）

    旧实现是「外部拖入一律复制」：从同一个盘里的 Explorer 往窗格拖文件，
    资源管理器给的是移动，我们给的是复制（源文件留在原地）。判据抽成两个
    Qt 无关的函数，矩阵本身完全不碰 GUI 就能测满。
    """

    def test_modifier_keys_beat_everything_else(self):
        from core.file_operations import decide_drop_action as decide
        # Ctrl/Shift 盖过同窗格拖动与同卷（它们就是用户的显式意图）
        assert decide(force_copy=True, same_dir_drag=True, same_vol=True) == "copy"
        assert decide(force_move=True, same_vol=False) == "move"

    def test_same_volume_moves_and_cross_volume_copies(self):
        from core.file_operations import decide_drop_action as decide
        assert decide(same_vol=True) == "move"
        assert decide(same_vol=False) == "copy"

    def test_a_drag_inside_one_folder_moves_even_if_volume_is_unknown(self):
        from core.file_operations import decide_drop_action as decide
        assert decide(same_dir_drag=True, same_vol=False) == "move"

    def test_a_source_that_only_allows_copy_is_never_moved(self):
        """只允许 COPY 的源（只读介质、不支持移动的外部应用）被我们「移动」
        掉就是删人家的东西，卷判断不能翻盘这条"""
        from core.file_operations import decide_drop_action as decide
        assert decide(same_vol=True, allows_move=False, allows_copy=True) == "copy"
        assert decide(same_vol=False, allows_move=True, allows_copy=False) == "move"

    def test_a_source_that_allows_nothing_falls_back_to_copy(self):
        from core.file_operations import decide_drop_action as decide
        assert decide(same_vol=True, allows_move=False, allows_copy=False) == "copy"

    def test_same_volume_is_true_inside_one_directory_tree(self, tmp_path):
        from core.file_operations import same_volume
        sub = os.path.join(str(tmp_path), "sub")
        os.makedirs(sub)
        src = os.path.join(str(tmp_path), "a.txt")
        open(src, "w").close()
        assert same_volume([src], sub) is True
        # 拖的是目录行：拿它的父目录比卷
        assert same_volume([sub], str(tmp_path)) is True
        # 文件本身还不存在也能定卷：卷属于目录，不属于文件
        # （拖拽决策时源可能已被别处动过，这里不能因此退化成复制）
        assert same_volume([os.path.join(str(tmp_path), "not-yet.txt")], sub) is True

    def test_an_unstatable_path_is_not_reported_as_same_volume(self, tmp_path):
        """拿不准就当跨卷（调用方靠这个答案决定要不要删源）

        比卷用的是**父目录**（被拖的文件可能此刻已被别处移走，父目录还在
        就能定卷），所以这里要让不存在的是一整级父目录而不是文件名。
        """
        from core.file_operations import same_volume
        good = os.path.join(str(tmp_path), "a.txt")
        open(good, "w").close()
        ghost_dir = os.path.join(str(tmp_path), "gone", "a.txt")
        assert same_volume([ghost_dir], str(tmp_path)) is False
        assert same_volume([good], os.path.join(str(tmp_path), "nowhere")) is False
        assert same_volume([], str(tmp_path)) is False
        # 多个源：都在同一棵目录树里仍算同卷（只要有一个跨卷就整体不算）
        other = os.path.join(str(tmp_path), "other")
        os.makedirs(other)
        assert same_volume([good, os.path.join(other, "b.txt")], other) is True

    def test_a_path_on_another_device_is_not_the_same_volume(self, tmp_path, monkeypatch):
        r"""`st_dev` 不同 = 不同卷（Windows 上是盘号，Linux 上是设备号）

        旧写法用“路径以 `E:` 开头”伪造另一个卷，但 `same_volume` 会先做
        `dirname(abspath(src))`：POSIX 上 `E:\media\a.mp4` 是个相对目录名，前缀被抹掉，
        假卷根本没造出来（Linux 真机上实测就报 `True is False`）。改为在路径里放
        一段能原样穿过 abspath/dirname 的标记。
        """
        from core import file_operations as fo
        real_stat = os.stat

        class _St:
            def __init__(self, dev):
                self.st_dev = dev

        MARK = "other-device"
        other_dev = real_stat(str(tmp_path)).st_dev + 7

        def fake_stat(path, *a, **k):
            # 带标记的那一条假装在另一台设备上
            return _St(other_dev) if MARK in str(path) else real_stat(path)

        monkeypatch.setattr(fo.os, "stat", fake_stat)
        far = os.path.join(str(tmp_path), MARK, "media", "a.mp4")
        assert fo.same_volume([far], str(tmp_path)) is False
        assert fo.same_volume([str(tmp_path / "a.mp4")], str(tmp_path)) is True
        # 多个源要逐个比：只查第一个会把跨卷的一批说成同卷
        assert fo.same_volume([str(tmp_path / "a.mp4"), far], str(tmp_path)) is False

    def test_unc_paths_are_never_reported_as_same_volume(self, tmp_path, monkeypatch):
        """Windows 上不同共享的 st_dev 可能同为 0，会把两个共享误判成同卷

        得让 UNC 形状的路径**也能 stat 成功**：真机上 `\\srv\\share` 根本不存在，
        靠 OSError 就能返回 False，那样把 UNC 判据删掉用例也不会红（测的是
        个假故事）。
        """
        from core import file_operations as fo
        real_stat = os.stat
        monkeypatch.setattr(fo, "_is_unc_path",
                            lambda p: p.replace('/', '\\').startswith('\\\\srv'))
        dev = real_stat(str(tmp_path)).st_dev
        monkeypatch.setattr(fo.os, "stat",
                            lambda p, *a, **k: type("_S", (), {"st_dev": dev})())
        assert fo.same_volume([r"\\srv\share\a.txt"], str(tmp_path)) is False
        assert fo.same_volume([r"C:\local\a.txt"], r"\\srv\share\dst") is False


class TestCrossVolumeMove:
    """跨卷移动走「复制 + 删源」那条路（判据与拖放共用 `same_volume`）

    `shutil.move` 的跨卷分支不落 mtime、没有字节进度、也看不到取消标志 ——
    用户「本地→SMB 映射盘」丢的就是这三样。既然判据现在是共用的，就得有用例
    盯住「判据说不确定时走的是哪条路」。
    """

    def test_a_cross_volume_move_keeps_mtime_and_removes_the_source(self, tmp_path,
                                                                   monkeypatch):
        from core import file_operations as fo
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        f = src_dir / "a.txt"
        f.write_text("hello")
        old = 1600000000
        os.utime(str(f), (old, old))

        # 光看结果区分不了两条路（同盘 `shutil.move` 也是 rename，mtime 自然保住），
        # 所以还要盯住它走的是「复制 + 删源」那条
        seen = []
        real_copy = fo.FileOperations.copy

        def spy(self, sources, target):
            seen.append(([os.path.normpath(s) for s in sources], target))
            return real_copy(self, sources, target)

        monkeypatch.setattr(fo.FileOperations, "copy", spy)
        monkeypatch.setattr(fo, "same_volume", lambda sources, target: False)
        res = fo.FileOperations().move([str(f)], str(dst_dir))

        assert res.success, res.error
        assert seen == [([os.path.normpath(str(f))], str(dst_dir))]
        assert not f.exists()                       # 是移动，不是复制
        moved = dst_dir / "a.txt"
        assert moved.exists()
        assert abs(int(moved.stat().st_mtime) - old) <= 1   # 走 shutil.move 会丢这个
