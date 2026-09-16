# -*- coding: utf-8 -*-
"""「慢位置」判据（`core/mounts.py`）—— 网络/远端/FUSE 挂载的识别。

这条判据决定了很多事：目录监视挂不挂、重复导航要不要强制重扫、导航时能不能
省掉一次同步 `stat`、删除确认里说「移到回收站」还是「永久删除」。原先只有
Windows 有答案（`os.name != 'nt'` 一律 `False`），Linux 上访问 gvfs / CIFS 共享
就完全按本地处理 —— 正是本项目头号目标的 Linux 半边。

POSIX 侧的三段（解析挂载表、最长前缀匹配、类型判定）都是纯函数，所以**在
Windows 主机上也能把 Linux 的判定矩阵测满**：喂进真实的 `/proc/mounts` 文本，
看它把哪些路径认成慢位置。真正碰盘的只有 `read_mount_table()` 一步，单独验它
的缓存与「读不到就当本地」的退化行为。
"""
import os

import pytest

from core import mounts


@pytest.fixture(autouse=True)
def _clean_mount_cache():
    """挂载表是模块级缓存，用例之间必须互不污染（随机序下尤其）"""
    mounts.clear_mount_cache()
    yield
    mounts.clear_mount_cache()


# 一份真实感的 /proc/mounts：容器根、伪文件系统、CIFS 挂载、名字相近的本地盘、
# 以及 gvfs 那两层（tmpfs 挂着 FUSE 子挂载）。注意用 **原始字符串**：
# `\040` 要被解析器看到，不能被 Python 先换成空格。
LINUX_MOUNTS = r"""overlay / overlay rw,relatime 0 0
proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0
sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0
/dev/nvme0n1p2 /home ext4 rw,relatime 0 0
/dev/sda1 /mnt/nas2 ext4 rw,relatime 0 0
//server/share /mnt/nas cifs rw,username=u 0 0
//server/pub /mnt/pub smb3 rw 0 0
server:/export /mnt/nfs nfs4 rw 0 0
tmpfs /run/user/1000 tmpfs rw,nosuid,nodev 0 0
gvfsd-fuse /run/user/1000/gvfs fuse.gvfsd-fuse rw,nosuid,nodev 0 0
/dev/sdb1 /media/u/Data vfat rw 0 0
/dev/sdc1 /mnt/my\040disk ntfs-3g rw 0 0
"""


def _table():
    return mounts.parse_mount_table(LINUX_MOUNTS)


# ------------------------------------------------------------------ 解析

def test_parse_mount_table_reads_type_and_mount_point():
    table = dict(_table())
    assert table["/"] == "overlay"
    assert table["/mnt/nas"] == "cifs"
    assert table["/run/user/1000/gvfs"] == "fuse.gvfsd-fuse"


def test_mount_point_with_escaped_space_is_unescaped():
    """`\040` 是空格：不还原的话，带空格的挂载点会永远匹配不上"""
    table = dict(_table())
    assert table["/mnt/my disk"] == "ntfs-3g"
    assert mounts.unescape_mount_field("/mnt/my\\040disk") == "/mnt/my disk"
    # 没有转义时原样返回（不该把合法路径改坏）
    assert mounts.unescape_mount_field("/home/u/Downloads") == "/home/u/Downloads"


def test_repeated_mount_point_keeps_the_last_one():
    """同一挂载点挂两次会遮蔽前者，路径解析看到的是最后一次"""
    text = "/dev/a /data ext4 rw 0 0\n//srv/s /data cifs rw 0 0\n"
    assert mounts.parse_mount_table(text) == [("/data", "cifs")]


def test_garbage_lines_are_skipped():
    text = "\n".join([
        "# comment",
        "only two fields",
        "dev rel/path ext4 rw 0 0",        # 挂载点不是绝对路径
        "dev /ok ext4 rw 0 0",
        "",
    ])
    assert mounts.parse_mount_table(text) == [("/ok", "ext4")]


# ------------------------------------------------------------------ 类型判定

@pytest.mark.parametrize("fstype", [
    "cifs", "smb", "smb2", "smb3", "smbfs", "nfs", "nfs4", "ncpfs",
    "afp", "afpfs", "davfs", "webdav", "sshfs", "sftpfs", "rclone",
    "fuse", "fuse.gvfsd-fuse", "fuse.sshfs", "fuse.rclone", "glusterfs",
    "gluster", "cephfs", "ceph", "lustre", "ocfs2", "gfs2", "9p", "9pfs",
    "vboxsf", "vmhgfs-fuse", "prl_fs", "afs",
])
def test_slow_filesystem_types_are_recognised(fstype):
    assert mounts.is_network_fstype(fstype) is True


@pytest.mark.parametrize("fstype", [
    "ext4", "ext2", "btrfs", "xfs", "f2fs", "ntfs", "ntfs-3g", "vfat",
    "exfat", "tmpfs", "overlay", "squashfs", "zfs", "apfs", "proc", "sysfs",
    "devtmpfs", "autofs", "ramfs", "mqueue", "",
])
def test_local_and_pseudo_filesystems_are_not_network(fstype):
    assert mounts.is_network_fstype(fstype) is False


# ------------------------------------------------------------------ 匹配

def test_longest_prefix_wins():
    table = _table()
    hit = mounts.longest_matching_mount("/run/user/1000/gvfs/smb-share/x", table)
    assert hit == ("/run/user/1000/gvfs", "fuse.gvfsd-fuse")
    assert mounts.longest_matching_mount("/home/u/f", table) == ("/home", "ext4")
    assert mounts.longest_matching_mount("/var/lib/x", table) == ("/", "overlay")


def test_sibling_with_similar_name_is_not_matched():
    """`/mnt/nas2` 不能算 `/mnt/nas` 的子路径（裸 startswith 就会误判）"""
    table = _table()
    assert mounts.longest_matching_mount("/mnt/nas2/x", table) == ("/mnt/nas2", "ext4")
    assert mounts.posix_is_remote("/mnt/nas2/x", table) is False


def test_similar_name_is_not_matched_even_without_a_sibling_entry():
    """没有那个「名字相近的本地盘」时也不能误判

    上一条里「最长前缀」正好替边界检查兼了底（`/mnt/nas2` 自己也在表里），所以
    单拿它验不出「忘了拼 `/`」这个错 —— 这里只挂一个网络共享，名字多一个字符的
    子目录必须还是本地。
    """
    table = [("/", "ext4"), ("/mnt/nas", "cifs")]
    assert mounts.posix_is_remote("/mnt/nas2/x", table) is False
    assert mounts.posix_is_remote("/mnt/nas/x", table) is True
    assert mounts.posix_is_remote("/mnt/other", table) is False


def test_root_mount_matches_without_double_slash():
    """根挂载 `/` 是特例：拼 `//` 去比就什么都匹配不上了"""
    table = [("/", "overlay")]
    assert mounts.longest_matching_mount("/etc/hosts", table) == ("/", "overlay")
    assert mounts.longest_matching_mount("/", table) == ("/", "overlay")


def test_mount_point_itself_counts():
    table = _table()
    assert mounts.posix_is_remote("/mnt/nas", table) is True


# ------------------------------------------------------------------ POSIX 判据矩阵

@pytest.mark.parametrize("path,expected", [
    ("/mnt/my disk/项目/照片", False),        # 空格挂载点是本地盘（ntfs-3g）
    ("/mnt/na s/x", False),
    ("/mnt/nas/reports/2026.xlsx", True),
    ("/mnt/pub/a.txt", True),
    ("/mnt/nfs/deep/dir", True),
    ("/run/user/1000/gvfs", True),
    ("/run/user/1000/gvfs/smb-share:server=gti,share=pub/x", True),
    ("/run/user/1000", False),           # tmpfs：本地
    ("/home/sfnca/文档", False),
    ("/etc/hosts", False),               # 容器根 overlay：本地
    ("/proc/self/root", False),
    ("/mnt/nas2/data", False),           # 名字相近的本地盘
])
def test_posix_is_remote_matrix(path, expected):
    assert mounts.posix_is_remote(path, _table()) is expected


def test_relative_and_empty_paths_are_not_judged():
    table = _table()
    assert mounts.posix_is_remote("mnt/nas/x", table) is False
    assert mounts.posix_is_remote("", table) is False
    assert mounts.posix_is_remote("/mnt/nas/x", []) is False      # 空表：按本地


def test_trailing_slash_and_dotdot_are_normalised():
    table = _table()
    assert mounts.posix_is_remote("/mnt/nas/../nas/x/", table) is True
    assert mounts.posix_is_remote("/mnt//nas/./x", table) is True


# ------------------------------------------------------------------ 碰盘部分

def test_read_mount_table_is_cached(monkeypatch):
    calls = []

    def fake_read():
        calls.append(1)
        return LINUX_MOUNTS

    monkeypatch.setattr(mounts, "_read_raw_mounts", fake_read)
    assert len(mounts.read_mount_table()) == len(_table())
    mounts.read_mount_table()
    mounts.read_mount_table(force=True)
    assert len(calls) == 2          # 第二次是显式 force，TTL 内只读了一次


def test_unreadable_mount_table_falls_back_to_local(monkeypatch):
    """判据自己出错时必须退化成「按本地处理」，不能把导航或删除一起拖失败"""
    def boom():
        raise RuntimeError("不该外抛")

    monkeypatch.setattr(mounts, "_read_raw_mounts", boom)
    assert mounts.read_mount_table() == []
    assert mounts.is_remote_location("/mnt/nas/x") is False


def test_entry_point_picks_the_platform_branch(monkeypatch):
    """入口只走本平台那一半：Windows 不去读挂载表，POSIX 不碰 win32 API"""
    seen = []
    monkeypatch.setattr(mounts, "win_is_remote", lambda p: seen.append("win") or True)
    monkeypatch.setattr(mounts, "read_mount_table",
                        lambda force=False: seen.append("posix") or _table())
    mounts.is_remote_location(r"C:\Users\u\x.txt")
    assert seen == (["win"] if os.name == "nt" else ["posix"])
    assert mounts.is_remote_location("") is False       # 空串直接 False，两半都不进
    assert len(seen) == 1


# ------------------------------------------------------------------ 三处消费方共用一份判据

def test_file_operations_delegates_to_the_single_judge(monkeypatch):
    from core import file_operations as fo

    calls = []

    def fake(p):
        calls.append(p)
        return p.startswith("/mnt/nas")

    monkeypatch.setattr(mounts, "is_remote_location", fake)
    assert fo._is_network_path("/mnt/nas/x") is True
    assert fo._is_network_path("/home/u/x") is False
    assert calls == ["/mnt/nas/x", "/home/u/x"]


def test_dir_model_uses_the_same_judge(monkeypatch):
    """目录监视的「只监视本地」与删除文案必须是同一个答案，否则两处会漂"""
    from core.dir_model import DirStoreModel

    monkeypatch.setattr(mounts, "is_remote_location", lambda p: str(p) == "/mnt/nas")
    assert DirStoreModel._is_network("/mnt/nas") is True
    assert DirStoreModel._is_network("/home/u") is False


def test_dir_model_treats_judge_failure_as_local(monkeypatch):
    from core.dir_model import DirStoreModel

    def boom(p):
        raise RuntimeError("判据炸了")

    monkeypatch.setattr(mounts, "is_remote_location", boom)
    assert DirStoreModel._is_network("/mnt/nas") is False
