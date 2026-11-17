# -*- coding: utf-8 -*-
r"""地址栏访问局域网共享（`\\主机\共享`）：连接、失败分类、凭据读写 —— 全仓唯一一份。

本模块回答「连得上吗 / 连不上是因为什么 / 用哪套凭据连」。**「这个位置是不是慢位置」仍然只有
`core/mounts.py:is_remote_location()` 那一份判据**（铁律第 1 条，gotchas #43），这里不复写
UNC 识别分支，只复用它的结论再拆一次字符串。

本版只做 Windows 的存凭据（2026-11-16 拍板：Linux 只给指路文案，代挂载与钥匙环排在目标机
核实完 SMB 后端之后 —— `docs/design-unc-share-access.md` §9 第 1、2 条）。

分层：`parse_unc` / `remote_name` / `credential_target` / `netresource_fields` /
`classify_error` / `failure_text` 全是纯函数，任何主机都能测满；碰系统的两段统一从
`_netapi()` 与 `_credapi()` 取，测试里预先塞假对象即可，不需要真连。

**常量与错误码一律照 §2.1 的实测值**（2026-11-16 六轮探针 `tmp/netapi_probe2.py`–
`netapi_probe7.py`）。不要按 winnetwk.h / wincred.h 的「常见转写」改回去 —— 设计稿初版四处
错误就是这么来的，其中 `CREDENTIALW` 少一格 8 字节会让 `CredWriteW` 对每种参数都回 87。
"""
import ctypes
import logging
import os
import time

logger = logging.getLogger("pan4dex.net_share")

# ---------------------------------------------------------------------- 错误码
# 注释里标 (m) 的是本轮探针实测拿到的；其余按 winerror.h 归类，等真机样本回来再校正。
ERROR_OK = 0
ERROR_ACCESS_DENIED = 5
ERROR_NOT_SUPPORTED = 50
ERROR_BAD_NETWORK_PATH = 52
ERROR_BAD_NETPATH = 53            # (m) 主机名解析不了 / 机器没开机
ERROR_SERVER_IS_SHUTDOWN = 58
ERROR_NETWORK_ACCESS_DENIED = 64
ERROR_BAD_NET_NAME = 67           # (m) 主机在、共享名不对
ERROR_ALREADY_ASSIGNED = 85
ERROR_INVALID_PASSWORD = 86       # (m) 账号或口令不对（本机回路样本）
ERROR_BAD_PATHNAME = 161          # (m) 裸 `\\主机`，没到共享那一层
ERROR_INVALID_ADDRESS = 487
ERROR_NOT_FOUND = 1168            # (m) 凭据库里没有这一条（CredDeleteW）
ERROR_SESSION_CREDENTIAL_CONFLICT = 1208   # 原稿的猜测，本轮没能复现，留着不挡路
ERROR_MULTIPLE_PRIMARY_LOGONS = 1219       # (m) 同机已连着 + 又换一套凭据
ERROR_NO_NETWORK = 1222
ERROR_NO_LOGON_SESSION = 1223
ERROR_REMOTE_UNREACHABLE = 1231
ERROR_BAD_ACCOUNT_NAME = 1315
ERROR_LOGON_FAILURE = 1326
ERROR_ACCOUNT_RESTRICTION = 1327
ERROR_INVALID_PASSWORD_AT_LOGON = 1328
ERROR_ACCOUNT_DISABLED = 1331
ERROR_NO_SUCH_DOMAIN = 1334
ERROR_PASSWORD_EXPIRED = 1335
ERROR_CONNECTION_UNAVAIL = 2250   # (m) 断一条本来就没有的连接

# ---------------------------------------------------------------------- 分类档
# 这张表就是本功能的脸：只有 NEED_CREDENTIAL / CONFLICT 两档允许弹模态框（§4.3）。
CATEGORY_OK = "ok"
CATEGORY_NEED_CREDENTIAL = "need_credential"
CATEGORY_CONFLICT = "conflict"
CATEGORY_SHARE_NOT_FOUND = "share_not_found"
CATEGORY_HOST_NOT_FOUND = "host_not_found"
CATEGORY_NOT_SHARE_LEVEL = "not_share_level"
CATEGORY_UNSUPPORTED_PLATFORM = "unsupported_platform"
CATEGORY_UNKNOWN = "unknown"

_NEED_CREDENTIAL_CODES = frozenset({
    ERROR_ACCESS_DENIED, ERROR_NETWORK_ACCESS_DENIED, ERROR_INVALID_PASSWORD,
    ERROR_BAD_ACCOUNT_NAME, ERROR_LOGON_FAILURE, ERROR_ACCOUNT_RESTRICTION,
    ERROR_INVALID_PASSWORD_AT_LOGON, ERROR_ACCOUNT_DISABLED, ERROR_NO_LOGON_SESSION,
    ERROR_PASSWORD_EXPIRED,
})
# 1208 未实测（本轮造不出「两个不同用户在同机同时连」的样本），1219 实测到了。
_CONFLICT_CODES = frozenset({ERROR_SESSION_CREDENTIAL_CONFLICT,
                             ERROR_MULTIPLE_PRIMARY_LOGONS})
_HOST_CODES = frozenset({ERROR_BAD_NETPATH, ERROR_NO_NETWORK, ERROR_REMOTE_UNREACHABLE,
                         ERROR_SERVER_IS_SHUTDOWN, ERROR_NO_SUCH_DOMAIN})
_NOT_SHARE_LEVEL_CODES = frozenset({ERROR_NOT_SUPPORTED, ERROR_BAD_PATHNAME,
                                    ERROR_BAD_NETWORK_PATH})

# (m) UNC 不占盘符时 connect 只会回 0/86/1219 这类；85 是占盘符才有的。两个都算成功，
# 免得把「已经连着」显示成失败。
_CONNECT_OK = frozenset({ERROR_OK, ERROR_ALREADY_ASSIGNED})
# (m) 2250 = 「本来就没连着」，与 0 同等成功，所以「断开」这一格可以反复点。
_CANCEL_OK = frozenset({ERROR_OK, ERROR_CONNECTION_UNAVAIL})

# ---------------------------------------------------------------------- NETRESOURCE
RESOURCE_CONNECTED = 1            # 只给 WNetEnumResource 查询用，连接时给它就是错 (m)
RESOURCE_GLOBALNET = 2
RESOURCETYPE_ANY = 0
RESOURCETYPE_DISK = 1
RESOURCETYPE_PRINT = 2            # (m) dwType 位上写 2 是连打印机 —— 原稿的坑
RESOURCEDISPLAYTYPE_SHARE = 2
RESOURCEUSAGE_ALL = 1

# (m) CONNECT_TEMPORARY(0x400) 与 CONNECT_RECONNECT(0x100) 一律被 WNetAddConnection2 拒回
# 87；CONNECT_UPDATE_PROFILE(0x1) 会把连接写进登录脚本，等于悄悄改用户的登录环境。
# flags=0 实测本来就是一次性会话：`net use` 里连上时可见、cancel 后干净消失。
CONNECT_FLAGS = 0
CANCEL_FLAGS = 0

# ---------------------------------------------------------------------- 纯函数段


class UncPath(object):
    r"""`parse_unc` 的结果。`share` 为空串 = 只到 `\\主机` 那一层（本版不列共享）。

    `device` 表示 `\\?\UNC\主机\共享` 这种 send2trash 会造出来的设备前缀形式：认得它，
    但不拿它当用户想连的目标（§7.1 第 1 条）。
    """

    __slots__ = ("server", "share", "tail", "device")

    def __init__(self, server, share, tail, device=False):
        self.server = server
        self.share = share
        self.tail = tail
        self.device = device

    def __eq__(self, other):
        if not isinstance(other, UncPath):
            return NotImplemented
        return ((self.server, self.share, self.tail, self.device)
                == (other.server, other.share, other.tail, other.device))

    def __hash__(self):
        return hash((self.server, self.share, self.tail, self.device))

    def __repr__(self):
        return "UncPath(server=%r, share=%r, tail=%r, device=%r)" % (
            self.server, self.share, self.tail, self.device)


_DEVICE_PREFIX = "\\\\?\\UNC\\"


def parse_unc(path):
    r"""`\\SRV\sh\a\b` → `UncPath("SRV", "sh", "a\b")`；不是 UNC → None

    纯字符串拆分：不碰磁盘、不 `normpath`（设备前缀与混合分隔符都得自己判，拆开反而看得清）。
    正斜杠写法 `//SRV/sh` 与反斜杠等价（§2 实测 `os.path.isdir` 两边都是 True），一并认。
    裸 `\\` 返回 None：判据会说它是远端，但它根本没法导航（§2）。
    """
    if not path or not isinstance(path, str):
        return None
    p = path.replace("/", "\\")
    if not p.startswith("\\\\"):
        return None
    device = p.startswith(_DEVICE_PREFIX)
    rest = p[len(_DEVICE_PREFIX):] if device else p[2:]
    parts = rest.split("\\")
    server = parts[0].strip()
    if not server:
        return None
    share = parts[1].strip() if len(parts) > 1 else ""
    return UncPath(server, share, "\\".join(parts[2:]), device)


def remote_name(server, share):
    r"""连接粒度 = 截到共享这一层 `\\SRV\sh`（会话按主机计，连接按共享计，§2.1②）"""
    return "\\\\%s\\%s" % (server, share)


def full_path(unc):
    r"""把拆开的三段拼回一个可 `isdir` 的路径（共享下面还有子目录时用）。"""
    path = remote_name(unc.server, unc.share)
    if unc.tail:
        path += "\\" + unc.tail
    return path


def credential_target(server, share):
    r"""凭据管理器里的键：`pan4dex:smb:SRV\sh`

    (m) 实测反斜杠、空格、中文、超 512 字符的 target 名系统都收。故意用自己的前缀，而不是
    系统那套「按服务器名当键」（`ROUTE88` / `TERMSRV/192.168.5.50` 那种）—— 后者与资源管理器、
    `net use /savecred` 共用一条记录，我们写进去等于替别人的程序改了凭据（§5.1）。
    代价也说清楚：(m) **系统重定向器不会自动使用我们这个命名空间的键**，所以「先静默用存好的
    凭据试一次」必须由我们自己读 blob 再显式传给 `connect()`。
    """
    return "pan4dex:smb:%s\\%s" % (server, share)


def netresource_fields(remote):
    """`WNetAddConnection2W` 要喂的 `NETRESOURCEW` 字段（纯函数，用例照实测值断言）"""
    return {
        "dwScope": RESOURCE_GLOBALNET,           # 不是 1
        "dwType": RESOURCETYPE_DISK,             # 不是 2
        "dwDisplayType": RESOURCEDISPLAYTYPE_SHARE,
        "dwUsage": RESOURCEUSAGE_ALL,
        "lpLocalName": None,                     # 不占盘符
        "lpRemoteName": remote,
        "lpComment": None,
        "lpProvider": None,                      # 让系统自己挑（这就是 SMB）
    }


def classify_error(win_err):
    """系统错误码 → 分类档。`None` = 没能拿到码（连 API 都没调成）→ 只写状态栏。"""
    if win_err in _CONNECT_OK:
        return CATEGORY_OK
    if win_err in _CONFLICT_CODES:
        return CATEGORY_CONFLICT
    if win_err in _NEED_CREDENTIAL_CODES:
        return CATEGORY_NEED_CREDENTIAL
    if win_err == ERROR_BAD_NET_NAME:
        return CATEGORY_SHARE_NOT_FOUND
    if win_err in _HOST_CODES:
        return CATEGORY_HOST_NOT_FOUND
    if win_err in _NOT_SHARE_LEVEL_CODES:
        return CATEGORY_NOT_SHARE_LEVEL
    return CATEGORY_UNKNOWN


def may_ask_credentials(category):
    """只有这两档允许弹模态框（§4.3）；其余一律状态栏 —— 弹框会把「名字打错」变成打扰。"""
    return category in (CATEGORY_NEED_CREDENTIAL, CATEGORY_CONFLICT)


def failure_text(category, unc, win_err=None):
    """状态栏文案。改文案只改这一处。"""
    if unc is None:
        return ""
    remote = remote_name(unc.server, unc.share) if unc.share else "\\\\%s" % unc.server
    if category == CATEGORY_NEED_CREDENTIAL:
        return "%s 需要用户名和密码" % remote
    if category == CATEGORY_CONFLICT:
        return "这台机器上你已经用另一个账号连着 \\\\%s，先断开旧连接再试" % unc.server
    if category == CATEGORY_SHARE_NOT_FOUND:
        return "%s 上没有名为 %s 的共享" % (unc.server, unc.share)
    if category == CATEGORY_HOST_NOT_FOUND:
        return "找不到 %s，检查它是否开机、网络是否通" % unc.server
    if category == CATEGORY_NOT_SHARE_LEVEL:
        if not unc.share:
            return r"请到共享这一层，例如 \\%s\photo" % unc.server
        return "%s 不是一个可以浏览的共享（可能是命名管道）" % remote
    if category == CATEGORY_UNSUPPORTED_PLATFORM:
        return (r"这一版 Linux 还不支持直接连共享：请先用系统把它挂上（GNOME：文件管理器 → "
                r"其他位置 → smb://%s/%s），然后填挂载点路径"
                % (unc.server, unc.share or "share"))
    if category == CATEGORY_OK:
        return ""
    if win_err is None:
        return "连不上 %s" % remote
    return "连不上 %s（系统错误 %s）" % (remote, win_err)


def is_supported_platform():
    return os.name == "nt"


# ---------------------------------------------------------------------- 碰系统的部分


class _WindowsNetApi(object):
    """`mpr.dll` + `kernel32.dll` 的窄封装。只在 Windows 分支 import 这些。"""

    def __init__(self):
        from ctypes import wintypes
        self._wt = wintypes

        class NETRESOURCEW(ctypes.Structure):
            _fields_ = [("dwScope", wintypes.DWORD), ("dwType", wintypes.DWORD),
                        ("dwDisplayType", wintypes.DWORD), ("dwUsage", wintypes.DWORD),
                        ("lpLocalName", wintypes.LPCWSTR), ("lpRemoteName", wintypes.LPCWSTR),
                        ("lpComment", wintypes.LPCWSTR), ("lpProvider", wintypes.LPCWSTR)]

        self.NETRESOURCEW = NETRESOURCEW
        self.mpr = ctypes.WinDLL("mpr")
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.mpr.WNetAddConnection2W.argtypes = [ctypes.POINTER(NETRESOURCEW),
                                                 wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                 wintypes.DWORD]
        self.mpr.WNetAddConnection2W.restype = wintypes.DWORD
        self.mpr.WNetCancelConnection2W.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                                    wintypes.BOOL]
        self.mpr.WNetCancelConnection2W.restype = wintypes.DWORD
        # restype 必须是 DWORD：默认 c_int 会把 0xFFFFFFFF 读成 -1，
        # 于是 `attr == INVALID_FILE_ATTRIBUTES` 永不成立、失败被当成「是个目录」。
        self.k32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        self.k32.GetFileAttributesW.restype = wintypes.DWORD

    def _build(self, remote):
        r = self.NETRESOURCEW()
        for key, value in netresource_fields(remote).items():
            setattr(r, key, value)
        return r

    def connect(self, remote, user=None, password=None):
        return int(self.mpr.WNetAddConnection2W(ctypes.byref(self._build(remote)),
                                                password, user, CONNECT_FLAGS))

    def cancel(self, remote):
        return int(self.mpr.WNetCancelConnection2W(remote, CANCEL_FLAGS, True))

    def is_dir(self, path):
        """一次 `GetFileAttributesW` 判可达（§5.5：首次连一台机器可能要 2.7 秒，调用方负责提示）。"""
        INVALID, ACCESS_DENIED = 0xFFFFFFFF, ERROR_ACCESS_DENIED
        attr = self.k32.GetFileAttributesW(path)
        if attr == INVALID:
            if ctypes.get_last_error() == ACCESS_DENIED:
                # 拒绝访问时属性查询给不了原因，退回 Python 的判断，
                # 别把「要凭据」读成「这个位置不存在」
                return os.path.isdir(path)
            return False
        return bool(attr & 0x10)      # FILE_ATTRIBUTE_DIRECTORY


class _PosixNetApi(object):
    """非 Windows：不碰任何连接 API，可达性沿用 Python 的判断（挂载点本来就是普通目录）。"""

    def connect(self, remote, user=None, password=None):
        return None

    def cancel(self, remote):
        return None

    def is_dir(self, path):
        return os.path.isdir(path)


_NET_API = [None]


def _netapi():
    if _NET_API[0] is None:
        _NET_API[0] = _WindowsNetApi() if is_supported_platform() else _PosixNetApi()
    return _NET_API[0]


def is_reachable(path):
    start = time.perf_counter()
    try:
        result = bool(_netapi().is_dir(path))
    except Exception as e:
        logger.debug("可达性探测 %s 异常: %s", path, e)
        result = False
    logger.debug("可达性探测 %s -> %s（%.0fms）", path, result,
                 (time.perf_counter() - start) * 1000)
    return result


def connect(remote, user=None, password=None):
    r"""建立到 `\\SRV\sh` 的会话（不占盘符、不进登录 profile）。返回 `(ok, win_err)`。

    口令只走参数，绝不进日志。API 都没调成时 `win_err` 是 None → 分类成 unknown，
    状态栏说「连不上」，然后由调用方回落到今天的行为。
    """
    try:
        code = _netapi().connect(remote, user, password)
    except Exception as e:
        logger.debug("连接 %s 异常: %s", remote, e)
        return False, None
    if code is None:
        return False, None
    return code in _CONNECT_OK, code


def cancel_connect(remote):
    """断开会话。0 与 2250 都算成功，所以这一格可以反复点（§2.1②）。"""
    try:
        code = _netapi().cancel(remote)
    except Exception as e:
        logger.debug("断开 %s 异常: %s", remote, e)
        return False, None
    if code is None:
        return False, None
    return code in _CANCEL_OK, code


# ---------------------------------------------------------------------- 凭据读写

CRED_TYPE_GENERIC = 1
# (m) 非提权进程 Persist=1/2/3 都写得进、另起进程能原样读回；Persist=0 被拒。
# 取 3（ENTERPRISE）与系统 cmdkey 一致：按用户持久，不落 ProgramData。
CRED_PERSIST = 3
# (m) target 名带中文/空格/超 512 字符都收，所以这里不给 target 长度设限；
# blob 上限按微软文档 CRED_MAX_CREDENTIAL_BLOB_SIZE = 5*512。口令不可能到这一格，
# 越过它只可能是「结构体偏移又不对了」→ 判读失败，别把乱码当口令递出去（§4.7）。
CRED_BLOB_MAX = 5 * 512
CRED_PERSIST_ALLOWED = (1, 2, 3)
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


def credential_blob_shape_ok(size, persist):
    """读回的 blob 形状是否可信。

    (m) 结构体偏移一错位，`CredentialBlobSize`/`Persist` 就会读成相邻指针的低 32 位
    （几十亿的 size、从没见过的 persist）—— 宁可当作读不出、重新问一次，也不把乱码
    当口令递给连接 API。`size == 0` 是合法形状（guest 共享的空口令）。
    """
    return (isinstance(size, int) and isinstance(persist, int)
            and 0 <= size <= CRED_BLOB_MAX and persist in CRED_PERSIST_ALLOWED)


class _WindowsCredApi(object):
    """`advapi32` 的凭据三段。

    `_pad0` **不是历史包袱**：x64 上 `TargetName` 之后真有 8 字节空位。少这一格 sizeof 从
    80 变 72，`CredWriteW` 对每种参数一律回 87、读回来的是相邻指针的低 32 位
    （(m) 靠 dump `cmdkey` 写好的条目原始内存才定位）。别照 wincred.h 的常见转写删掉它，
    也别顺手「修正」字段顺序 —— `tests/test_net_share.py` 有偏移守卫用例守着。
    """

    def __init__(self):
        from ctypes import wintypes

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR),
                        ("_pad0", ctypes.c_void_p),
                        ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

        self.CREDENTIALW = CREDENTIALW
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self.advapi32.CredWriteW.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.advapi32.CredWriteW.restype = wintypes.BOOL
        self.advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                            wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        self.advapi32.CredReadW.restype = wintypes.BOOL
        self.advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                              wintypes.DWORD]
        self.advapi32.CredDeleteW.restype = wintypes.BOOL
        self.advapi32.CredFree.argtypes = [ctypes.c_void_p]

    def write(self, target, user, password):
        text = password or ""
        blob = bytearray(text.encode("utf-16-le"))
        c = self.CREDENTIALW()
        c.Type = CRED_TYPE_GENERIC
        c.TargetName = target
        c.UserName = user or ""
        c.CredentialBlobSize = len(blob)
        # ctypes 不持有缓冲区所有权：buf 与 blob 必须活到 CredWriteW 返回，
        # 否则 CredentialBlob 指向已释放内存（写进去的是垃圾，读回来也是垃圾）
        buf = (ctypes.c_byte * max(len(blob), 1)).from_buffer(blob) if blob else None
        c.CredentialBlob = buf
        c.Persist = CRED_PERSIST
        try:
            return bool(self.advapi32.CredWriteW(ctypes.byref(c), 0))
        finally:
            for i in range(len(blob)):
                blob[i] = 0          # 用完就地清零，别在 Python 堆上多留一份口令

    def read(self, target):
        holder = ctypes.c_void_p()
        if not self.advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0,
                                       ctypes.byref(holder)):
            return None
        try:
            c = ctypes.cast(holder, ctypes.POINTER(self.CREDENTIALW)).contents
            size = int(c.CredentialBlobSize)
            persist = int(c.Persist)
            if not credential_blob_shape_ok(size, persist):
                logger.debug("凭据 %s 读回的形状不对（size=%s persist=%s），按读不出处理",
                             target, size, persist)
                return None
            if size == 0:
                # 空口令是合法形状（guest 共享），不是「形状不对」；不碰 blob 指针（可能为 NULL）
                return (c.UserName or "", "")
            raw = bytes(ctypes.cast(c.CredentialBlob,
                                   ctypes.POINTER(ctypes.c_byte * size)).contents)
            return (c.UserName or "", raw.decode("utf-16-le", "replace"))
        finally:
            self.advapi32.CredFree(holder)   # 只释放 API 给的指针

    def delete(self, target):
        if self.advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
            return True
        # (m) 条目本来就不存在时系统回 1168 ERROR_NOT_FOUND。这一档算成功：
        # 「不再记住」按钮可以反复点，不该在第二次报失败。
        return ctypes.get_last_error() == ERROR_NOT_FOUND


class _PosixCredApi(object):
    """非 Windows 本版不接钥匙环（拍板：等目标机核实 SMB 后端后连同依赖一起定，§9 第 1 条）。"""

    def write(self, target, user, password):
        return False

    def read(self, target):
        return None

    def delete(self, target):
        return False


_CRED_API = [None]


def _credapi():
    if _CRED_API[0] is None:
        _CRED_API[0] = _WindowsCredApi() if is_supported_platform() else _PosixCredApi()
    return _CRED_API[0]


def saved_credential(server, share):
    """读回 `(user, password)`；没存过 / 读不出 / 形状不对 → None（当作没存过，重新问）。"""
    try:
        return _credapi().read(credential_target(server, share))
    except Exception as e:
        logger.debug("读凭据 %s 异常: %s", server, e)
        return None


def store_credential(server, share, user, password):
    """返回是否写进系统凭据库。写失败不拦路：口令照样用一次，只是下次还要问。"""
    try:
        return bool(_credapi().write(credential_target(server, share), user, password))
    except Exception as e:
        logger.debug("存凭据 %s 异常: %s", server, e)
        return False


def forget_credential(server, share):
    try:
        return bool(_credapi().delete(credential_target(server, share)))
    except Exception as e:
        logger.debug("删凭据 %s 异常: %s", server, e)
        return False


# ---------------------------------------------------------------------- 编排（不碰 UI）


class ShareAttempt(object):
    """一次「地址栏里敲了 UNC」的结论，交给窗格决定导航 / 弹框 / 只写状态栏。

    `is_unc` 为 False 时其余字段都别读 —— 调用方保持今天的行为。
    没有「上一次失败」这类模块全局状态：每次结论都在这个对象里，调用方拿着它回传
    （gotchas #55 / 铁律第 8 条那种「边界空集跳过复位」的坑在这里根本没机会出现）。
    """

    __slots__ = ("unc", "category", "win_err", "target_path")

    def __init__(self, unc, category, win_err, target_path):
        self.unc = unc
        self.category = category
        self.win_err = win_err
        self.target_path = target_path

    @property
    def is_unc(self):
        return self.unc is not None

    @property
    def may_ask(self):
        return may_ask_credentials(self.category)

    @property
    def ok(self):
        return self.category == CATEGORY_OK

    def __repr__(self):
        return "ShareAttempt(category=%r, win_err=%r, target=%r)" % (
            self.category, self.win_err, self.target_path)


def plan_open(path):
    r"""把用户在地址栏敲的一串翻译成一次可执行的尝试。**不弹窗、不导航、不写状态栏**。

    判序（§4.5）：
    1. 不是 UNC → `ShareAttempt(None, ...)`
    2. 只到 `\\主机`（没到共享）或设备前缀形式 → 状态栏档（本版不列共享，
       「顺带做」那一半排在主路径真机验过之后，§5.4）
    3. 目标路径已经可达（来宾共享 / 上一轮已授权 / 系统里已连着）→ `CATEGORY_OK`
    4. 我们自己存过这套凭据 → 显式读出来再静默连一次（系统不会代劳）
    5. 否则不带凭据试一次，只为拿到真实错误码做分类
    """
    unc = parse_unc(path)
    if unc is None:
        return ShareAttempt(None, CATEGORY_UNKNOWN, None, path)
    if unc.device:
        # 设备前缀是别的库造出来的形状，不当作用户想连的共享（§7.1 第 1 条）
        return ShareAttempt(None, CATEGORY_UNKNOWN, None, path)
    if not unc.share:
        return ShareAttempt(unc, CATEGORY_NOT_SHARE_LEVEL, ERROR_BAD_PATHNAME, path)
    if not is_supported_platform():
        return ShareAttempt(unc, CATEGORY_UNSUPPORTED_PLATFORM, None, path)

    target = full_path(unc)
    remote = remote_name(unc.server, unc.share)
    if is_reachable(target):
        return ShareAttempt(unc, CATEGORY_OK, None, target)

    saved = saved_credential(unc.server, unc.share)
    if saved:
        ok, code = connect(remote, saved[0], saved[1])
    else:
        ok, code = connect(remote)
    if ok:
        # 连上之后目标路径可能还没被系统认下来，再探一次，别把「刚连上」说成可达
        if is_reachable(target):
            return ShareAttempt(unc, CATEGORY_OK, None, target)
        return ShareAttempt(unc, CATEGORY_UNKNOWN, None, target)
    return ShareAttempt(unc, classify_error(code), code, target)


def retry_with_credential(unc, user, password, category=None):
    """对话框拿到凭据后的唯一落点。`category` 用 `plan_open` 那次的结论原样传回来。

    1219 那一档必须先断开旧会话：同机已用另一个账号连着时，直接换凭据 Windows 永远回
    同一句 1219（§2.1②）。断开失败不拦路 —— 后面照样试一次连接，把结果告诉用户。
    返回 `(ok, category, win_err)`。
    """
    remote = remote_name(unc.server, unc.share)
    if category == CATEGORY_CONFLICT:
        cancel_connect(remote)
    ok, code = connect(remote, user, password)
    if not ok:
        return False, classify_error(code), code
    target = full_path(unc)
    if not is_reachable(target):
        return False, CATEGORY_UNKNOWN, code
    return True, CATEGORY_OK, code
