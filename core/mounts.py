# -*- coding: utf-8 -*-
r"""「这个位置是不是慢位置」的唯一判据 —— 网络 / 远端 / FUSE 挂载。

窗格导航、目录监视、删除确认文案问的都是同一句话：**这条路径在不在本地磁盘上**。
以前这个问题只有 Windows 有答案（另外两个平台一句 `os.name != 'nt'` 就 `return
False`），于是 Linux 上访问 gvfs / CIFS 共享时，「网络目录不挂 watcher」「重复导航
同一目录强制重扫」「网络位置没有回收站」全部失效 —— 而 gvfs 恰恰是最需要它们的那类
目录。判据收拢到这里，分两半：

- **Windows**：UNC（`\\server\share`）+ `GetDriveTypeW == DRIVE_REMOTE`（原逻辑照搬，
  一个字没改，那是被 SMB 卡顿一遍遍试出来的）
- **POSIX**：读挂载表（Linux `/proc/mounts`，macOS `mount -p`），按**最长前缀**找出
  路径所属的挂载点，再看它的文件系统类型在不在慢类型表里

解析、匹配、类型判定三段都是纯函数（喂文本进、吐结果出），所以在任何主机上都能测满；
只有「读挂载表」那一步碰盘，带 TTL 缓存，且任何失败都退化成「按本地处理」—— 也就是
本模块进场之前的行为，不会因为判据本身出问题而变慢或变崩。

已知取舍：判据**不做 `realpath`**。解析符号链接要对路径每一级做 readlink，而这条判据
恰恰要用在可能已经卡住的远端路径上；代价是「经由符号链接访问的挂载点」会被判成本地。
"""
import logging
import os
import posixpath
import sys
import time

logger = logging.getLogger("pan4dex.mounts")

MOUNT_CACHE_TTL = 10.0        # 秒；挂载表几乎不变，但用户可能在程序运行中挂上新共享

# 名字里带这些前缀的文件系统一律算「远端 / 慢」：内核和用户态都会派生变体
# （smb / smb2 / smb3、nfs / nfs4、fuse / fuse.gvfsd-fuse / fuse.sshfs、
#  davfs / webdav、ceph / cephfs、gluster / glusterfs、9p / 9pfs …）
_NETWORK_FSTYPE_PREFIXES = (
    "smb", "cifs", "ncpfs", "nfs", "afp", "dav", "webdav", "sshfs", "sftpfs",
    "ftpfs", "rclone", "fuse", "gluster", "ceph", "lustre", "ocfs2", "gfs",
    "9p", "vboxsf", "vmhgfs", "prl_fs", "afs",
)

_cache = {"ts": 0.0, "table": None}


# ------------------------------------------------------------------ 纯函数三段

def is_network_fstype(fstype: str) -> bool:
    """文件系统类型名是否属于「远端 / 慢」这一类"""
    f = (fstype or "").strip().lower()
    return any(f.startswith(p) for p in _NETWORK_FSTYPE_PREFIXES)


def unescape_mount_field(field: str) -> str:
    """还原挂载表里的八进制转义（`/proc/mounts` 把路径里的空格写成 `\\040`）"""
    if "\\" not in field:
        return field
    return _octal_unescape(field)


def _octal_unescape(field: str) -> str:
    """把 `\\040` / `\\011` / `\\012` / `\\134` 这类写法换回真字符（其余原样保留）"""
    out = []
    i = 0
    n = len(field)
    while i < n:
        if field[i] == "\\" and i + 4 <= n and field[i + 1:i + 4].isdigit():
            try:
                out.append(chr(int(field[i + 1:i + 4], 8)))
                i += 4
                continue
            except ValueError:
                pass
        out.append(field[i])
        i += 1
    return "".join(out)


def parse_mount_table(text: str) -> list:
    """挂载表文本 → `[(挂载点, 文件系统类型)]`

    两个平台的格式一致（`设备 挂载点 类型 选项…`，空白分隔、`\040` 转义），所以一个
    解析器够用。**同一挂载点出现多次时取最后一次**：后挂的会遮蔽先挂的，路径解析
    实际看到的就是它。无法解析的行（表头、空行、字段不足）直接跳过。
    """
    seen = {}
    for line in (text or "").splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        mount_point = unescape_mount_field(parts[1])
        if not mount_point.startswith("/"):
            continue
        seen[mount_point] = parts[2]
    return list(seen.items())


def longest_matching_mount(path: str, mounts: list):
    """找出 `path` 所属的挂载点（最长前缀匹配）→ `(挂载点, 类型)` 或 `None`

    必须按目录边界比，不能裸 `startswith`：`/mnt/nas2/x` 不该匹配到 `/mnt/nas`。
    根挂载 `/` 是特例（它的「子路径」不需要再拼一个 `/`）。
    """
    best = None
    for mount_point, fstype in mounts or []:
        if path == mount_point or (mount_point != "/" and path.startswith(mount_point + "/")) \
                or (mount_point == "/" and path.startswith("/")):
            if best is None or len(mount_point) > len(best[0]):
                best = (mount_point, fstype)
    return best


def normalize_posix_path(path: str) -> str:
    """`/` 风格路径规范化（去重复斜杠、`.`、`..`、尾斜杠）；相对路径原样返回"""
    if not path:
        return ""
    return posixpath.normpath(path)


def posix_is_remote(path: str, mounts: list) -> bool:
    """POSIX 判据：路径所在挂载点的类型是不是慢类型（挂载表由调用方喂进来）"""
    if not mounts:
        return False
    target = normalize_posix_path(path)
    if not target.startswith("/"):
        return False          # 相对路径判不了，按本地处理
    hit = longest_matching_mount(target, mounts)
    return bool(hit) and is_network_fstype(hit[1])


# ------------------------------------------------------------------ 碰盘的部分

def _read_raw_mounts() -> str:
    """读原始挂载表文本；读不到就返回空串（调用方会退化成「按本地处理」）"""
    try:
        if sys.platform == "linux":
            with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        if sys.platform == "darwin":
            import subprocess
            return subprocess.run(["mount", "-p"], capture_output=True, text=True,
                                  timeout=5, check=False).stdout or ""
    except Exception as e:
        logger.debug("读挂载表失败，按本地位置处理: %s", e)
    return ""


def read_mount_table(force: bool = False) -> list:
    """带 TTL 缓存的挂载表（`[(挂载点, 类型)]`）；任何失败都是空表，绝不外抛"""
    now = time.monotonic()
    table = _cache["table"]
    if table is not None and not force and (now - _cache["ts"]) < MOUNT_CACHE_TTL:
        return table
    try:
        table = parse_mount_table(_read_raw_mounts())
    except Exception as e:
        logger.debug("解析挂载表失败，按本地位置处理: %s", e)
        table = []
    _cache["table"] = table
    _cache["ts"] = now
    return table


def clear_mount_cache():
    """丢掉缓存（测试用；也供「刚挂了新共享」这类显式重读）"""
    _cache["table"] = None
    _cache["ts"] = 0.0


def win_is_remote(path: str) -> bool:
    r"""Windows 判据：UNC 共享，或 `GetDriveTypeW` 说是 `DRIVE_REMOTE` 的映射盘

    照搬原 `_is_network_path` 的实现（含 `\\?\UNC\` 这类带前缀的形式也一并算网络 ——
    send2trash 会造出那种路径）。QFileSystemWatcher 在 SMB 上不推事件、`st_dev` 在
    不同共享间可能同为 0，都依赖这个判据绕开。
    """
    try:
        p = path.replace("/", "\\")
        if p.startswith("\\\\"):
            return True
        root = os.path.splitdrive(p)[0]
        if root:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(root + "\\") == 4   # DRIVE_REMOTE
    except Exception:
        return False
    return False


def is_remote_location(path: str) -> bool:
    """这个路径是不是「慢位置」（网络 / 远端 / FUSE）—— 全仓唯一入口

    任何异常一律返回 `False`（按本地处理）：这条判据只用来决定「要不要更保守」，
    它自己出错时不该让导航或删除跟着失败。
    """
    if not path:
        return False
    try:
        if os.name == "nt":
            return win_is_remote(path)
        return posix_is_remote(path, read_mount_table())
    except Exception as e:
        logger.debug("网络位置判定失败 %s: %s", path, e)
        return False
