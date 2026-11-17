# -*- coding: utf-8 -*-
r"""地址栏访问局域网共享（core/net_share.py + widgets/net_credentials_dialog.py）。

这里盯四件事，每件都有对应的「改前」对照组：

1. **常量与错误码是实测那一份**：`NETRESOURCEW` 四个字段、`CONNECT_FLAGS=0`、
   `CREDENTIALW` 的 x64 偏移。当初照常见转写抄，`CredWriteW` 会对每种参数一律回 87，
   而报错只会出现在运行时的返回值里 —— 所以偏移必须有守卫用例，改错了先在这里炸。
2. **分类表**：只有「要凭据 / 1219 冲突」两档允许弹模态框，其余一律状态栏。
   弹错档的代价是把「共享名打错」变成一次打断。
3. **系统不会替我们用存好的凭据**（实测），所以「已存过 → 自己读出来静默重试」这一支
   必须真的带上 user/password 调 connect；没存过时**不许**盲调。
4. **接线层**：成功路径一个字没动（`os.path.isdir` 那一刀在前面）；失败保留用户输入；
   非 UNC 的手误不该看见「正在连接」，也不该被接管。

凭据库与网络一律走假对象（`_netapi` / `_credapi` / `is_supported_platform` 三个出口），
测试期间不真连任何机器、不写任何凭据。
"""
import ctypes

import pytest
from PyQt6.QtWidgets import QDialog, QLabel

from core import net_share as ns
from core.pane import Pane


# ------------------------------------------------------------------ 假出口


class FakeNet(object):
    """`_netapi()` 的替身：只记账，不碰网络"""

    def __init__(self, connect_code=ns.ERROR_INVALID_PASSWORD, cancel_code=0,
                 reachable=False, codes=None, flip_on_connect=False):
        self.connect_code = connect_code
        self.codes = list(codes or [])    # 非空时按顺序取，用于「两次调用回不同码」
        self.cancel_code = cancel_code
        self.reachable = reachable
        # 真机上「连上之后路径才变得可达」，假对象要能复现这一先后：连成功才翻牌
        self.flip_on_connect = flip_on_connect
        self.calls = []            # [(方法, 参数)]，顺序即调用顺序

    def is_dir(self, path):
        self.calls.append(("is_dir", path))
        return self.reachable

    def connect(self, remote, user=None, password=None):
        self.calls.append(("connect", remote, user, password))
        code = self.codes.pop(0) if self.codes else self.connect_code
        if self.flip_on_connect and code in ns._CONNECT_OK:
            self.reachable = True
        return code

    def cancel(self, remote):
        self.calls.append(("cancel", remote))
        return self.cancel_code

    def names(self):
        return [c[0] for c in self.calls]

    def connect_calls(self):
        return [c for c in self.calls if c[0] == "connect"]


class FakeCred(object):
    """`_credapi()` 的替身：内存里一条，绝不落盘"""

    def __init__(self, saved=None):
        self.saved = saved              # {target: (user, password)}
        self.log = []

    def read(self, target):
        self.log.append(("read", target))
        return dict(self.saved).get(target) if self.saved else None

    def write(self, target, user, password):
        self.log.append(("write", target, user))
        self.saved[target] = (user, password)
        return True

    def delete(self, target):
        self.log.append(("delete", target))
        self.saved.pop(target, None)
        return True

    def writes(self):
        return [e for e in self.log if e[0] == "write"]

    def deletes(self):
        return [e for e in self.log if e[0] == "delete"]


@pytest.fixture
def fakes(monkeypatch):
    """装好三个出口，并把平台切到 Windows（Linux CI 上也要走这套分支）"""
    net, cred = FakeNet(), FakeCred(saved={})
    monkeypatch.setattr(ns, "_netapi", lambda: net)
    monkeypatch.setattr(ns, "_credapi", lambda: cred)
    monkeypatch.setattr(ns, "is_supported_platform", lambda: True)
    return net, cred


# ------------------------------------------------------------------ 1. 纯函数


@pytest.mark.parametrize("path, expected", [
    (r"\\NAS\photo\a\b", ns.UncPath("NAS", "photo", "a\\b")),
    (r"//NAS/photo/a/b", ns.UncPath("NAS", "photo", "a\\b")),
    (r"\\NAS\photo", ns.UncPath("NAS", "photo", "")),
    ("\\\\NAS\\photo\\", ns.UncPath("NAS", "photo", "")),   # 尾斜杠（raw 串写不了这条）
    (r"\\NAS", ns.UncPath("NAS", "", "")),
    (r"\\192.168.5.50\c$\Windows", ns.UncPath("192.168.5.50", "c$", "Windows")),
    (r"\\?\UNC\NAS\photo", ns.UncPath("NAS", "photo", "", device=True)),
])
def test_parse_unc_takes_apart_without_touching_disk(path, expected):
    assert ns.parse_unc(path) == expected


@pytest.mark.parametrize("path", [
    "\\\\", "\\\\\\\\", "", None, "C:\\Users", "C:/Users", "/mnt/nas/photo",
    r"nas\photo", "相对\\路径",
])
def test_parse_unc_returns_none_for_everything_else(path):
    # 裸 `\\` 会被 mounts 判据说成远端，但它没法导航 —— 必须在这里就否掉
    assert ns.parse_unc(path) is None


def test_remote_name_is_cut_at_the_share():
    assert ns.remote_name("NAS", "photo") == "\\\\NAS\\photo"
    assert ns.full_path(ns.UncPath("NAS", "photo", "2024\\1月")) == \
        "\\\\NAS\\photo\\2024\\1月"
    assert ns.full_path(ns.UncPath("NAS", "photo", "")) == "\\\\NAS\\photo"


def test_credential_target_uses_our_own_namespace():
    """自己的前缀，不是系统那套按服务器名当键（`TERMSRV/x`）—— 后者与 net use /savecred 共用一条"""
    assert ns.credential_target("NAS", "photo") == "pan4dex:smb:NAS\\photo"
    assert not ns.credential_target("NAS", "photo").startswith("TERMSRV")


def test_netresource_fields_are_the_measured_ones():
    """设计稿初版就是照常见转写把 dwScope/dwType 抄反了（那是查询用的类型 + 打印机）"""
    f = ns.netresource_fields("\\\\NAS\\photo")
    assert f["dwScope"] == ns.RESOURCE_GLOBALNET == 2
    assert f["dwType"] == ns.RESOURCETYPE_DISK == 1
    assert f["dwDisplayType"] == ns.RESOURCEDISPLAYTYPE_SHARE == 2
    assert f["dwUsage"] == ns.RESOURCEUSAGE_ALL == 1
    # 对照组：错的那两个取值确实不是这里用的
    assert f["dwScope"] != ns.RESOURCE_CONNECTED
    assert f["dwType"] != ns.RESOURCETYPE_PRINT
    assert f["lpLocalName"] is None and f["lpProvider"] is None
    assert f["lpRemoteName"] == "\\\\NAS\\photo"


def test_connect_flags_must_be_zero():
    """CONNECT_TEMPORARY / CONNECT_RECONNECT 实测一律被拒回 87；
    CONNECT_UPDATE_PROFILE 会把连接写进登录脚本。"""
    assert ns.CONNECT_FLAGS == 0
    assert ns.CANCEL_FLAGS == 0


def test_credential_struct_offsets_guard():
    """x64 真实 sizeof = 80。少一格 8 字节变 72 → CredWriteW 对所有参数回 87。

    这一条不测行为，测的是「别照着 wincred.h 的常见转写把 `_pad0` 删掉」。
    """
    api = ns._WindowsCredApi()
    cred_t = api.CREDENTIALW
    assert ctypes.sizeof(cred_t) == 80
    for name, offset in (("LastWritten", 24), ("CredentialBlobSize", 32),
                         ("CredentialBlob", 40), ("Persist", 48), ("UserName", 72)):
        assert getattr(cred_t, name).offset == offset, name
    assert ctypes.sizeof(ns._WindowsNetApi().NETRESOURCEW) == 48


@pytest.mark.parametrize("size, persist, ok", [
    (0, 3, True),          # guest 共享的空口令是合法形状
    (12, 3, True),
    (5 * 512, 1, True),
    (5 * 512 + 1, 3, False),
    (-1, 3, False),
    (12, 0, False),        # Persist=0 实测写不进去，读回 0 说明偏移又错位了
    (12, 4, False),
    ("12", 3, False),
])
def test_credential_blob_shape_guard(size, persist, ok):
    assert ns.credential_blob_shape_ok(size, persist) is ok


# ------------------------------------------------------------------ 2. 分类表


@pytest.mark.parametrize("code, category", [
    (0, ns.CATEGORY_OK),
    (85, ns.CATEGORY_OK),                       # 已连着，不算失败
    (86, ns.CATEGORY_NEED_CREDENTIAL),          # (m) 实测样本值
    (5, ns.CATEGORY_NEED_CREDENTIAL),
    (1326, ns.CATEGORY_NEED_CREDENTIAL),
    (1331, ns.CATEGORY_NEED_CREDENTIAL),
    (1335, ns.CATEGORY_NEED_CREDENTIAL),
    (1219, ns.CATEGORY_CONFLICT),               # (m) 实测到的那一档
    (1208, ns.CATEGORY_CONFLICT),               # 原稿猜测，本轮没复现，仍按冲突处理
    (67, ns.CATEGORY_SHARE_NOT_FOUND),         # (m)
    (53, ns.CATEGORY_HOST_NOT_FOUND),          # (m)
    (1231, ns.CATEGORY_HOST_NOT_FOUND),
    (1222, ns.CATEGORY_HOST_NOT_FOUND),
    (161, ns.CATEGORY_NOT_SHARE_LEVEL),        # (m) 裸 \\主机
    (50, ns.CATEGORY_NOT_SHARE_LEVEL),
    (None, ns.CATEGORY_UNKNOWN),               # API 都没调成
    (2250, ns.CATEGORY_UNKNOWN),               # 只属于 cancel 的码，不该出现在 connect
])
def test_classify_error_table(code, category):
    assert ns.classify_error(code) == category


def test_only_two_categories_may_open_a_modal():
    """模态框只挡在「要凭据 / 冲突」两档前 —— 其它失败一律状态栏"""
    may = [c for c in (ns.CATEGORY_OK, ns.CATEGORY_NEED_CREDENTIAL, ns.CATEGORY_CONFLICT,
                       ns.CATEGORY_SHARE_NOT_FOUND, ns.CATEGORY_HOST_NOT_FOUND,
                       ns.CATEGORY_NOT_SHARE_LEVEL, ns.CATEGORY_UNSUPPORTED_PLATFORM,
                       ns.CATEGORY_UNKNOWN) if ns.may_ask_credentials(c)]
    assert may == [ns.CATEGORY_NEED_CREDENTIAL, ns.CATEGORY_CONFLICT]


@pytest.mark.parametrize("category, must_contain", [
    (ns.CATEGORY_NEED_CREDENTIAL, "需要用户名和密码"),
    (ns.CATEGORY_CONFLICT, "另一个账号"),
    (ns.CATEGORY_SHARE_NOT_FOUND, "没有名为 photo 的共享"),
    (ns.CATEGORY_HOST_NOT_FOUND, "找不到 NAS"),
    (ns.CATEGORY_UNSUPPORTED_PLATFORM, "smb://NAS/photo"),
])
def test_failure_text_names_the_machine(category, must_contain):
    text = ns.failure_text(category, ns.parse_unc(r"\\NAS\photo"))
    assert must_contain in text


def test_failure_text_for_bare_host_points_at_the_share_level():
    unc = ns.parse_unc(r"\\NAS")
    assert r"请到共享这一层" in ns.failure_text(ns.CATEGORY_NOT_SHARE_LEVEL, unc)
    # 对照组：到了共享那一层却不可浏览（命名管道）时不该说这句
    other = ns.failure_text(ns.CATEGORY_NOT_SHARE_LEVEL,
                            ns.parse_unc(r"\\NAS\IPC$"))
    assert "请到共享这一层" not in other and "命名管道" in other


def test_failure_text_unknown_carries_the_code_and_none_is_silent():
    unc = ns.parse_unc(r"\\NAS\photo")
    assert "系统错误 1219" in ns.failure_text(ns.CATEGORY_UNKNOWN, unc, 1219)
    assert ns.failure_text(ns.CATEGORY_UNKNOWN, unc, None) == "连不上 \\\\NAS\\photo"
    assert ns.failure_text(ns.CATEGORY_OK, unc) == ""
    assert ns.failure_text(ns.CATEGORY_NEED_CREDENTIAL, None) == ""


# ------------------------------------------------------------------ 3. 编排


def test_reachable_share_never_reaches_connect(fakes):
    """来宾共享 / 系统里已经连着：`is_reachable` 说行就完事，一次连接都不该发起"""
    net, cred = fakes
    net.reachable = True
    a = ns.plan_open(r"\\NAS\photo\2024")
    assert a.ok and a.target_path == "\\\\NAS\\photo\\2024"
    assert net.connect_calls() == []
    assert cred.log == []


def test_unreachable_without_saved_credential_probes_once_without_user(fakes):
    net, cred = fakes
    net.reachable = False
    a = ns.plan_open(r"\\NAS\photo")
    assert a.category == ns.CATEGORY_NEED_CREDENTIAL and a.win_err == 86
    assert net.connect_calls() == [("connect", "\\\\NAS\\photo", None, None)]


def test_saved_credential_is_replayed_by_us_not_by_the_system(fakes):
    """系统重定向器不会自动用我们的键（实测），所以这一支必须自己把 user/password 递进去"""
    net, cred = fakes
    net.reachable = False
    net.flip_on_connect = True          # 真机：连上之后路径才变得可达
    net.connect_code = 0
    cred.saved[ns.credential_target("NAS", "photo")] = ("u1", "pw")
    a = ns.plan_open(r"\\NAS\photo")
    assert a.ok
    assert net.connect_calls() == [("connect", "\\\\NAS\\photo", "u1", "pw")]
    assert ("read", "pan4dex:smb:NAS\\photo") in cred.log


def test_stale_saved_credential_reports_the_new_code(fakes):
    net, cred = fakes
    net.reachable = False
    net.connect_code = 1326
    cred.saved[ns.credential_target("NAS", "photo")] = ("u1", "pw")
    a = ns.plan_open(r"\\NAS\photo")
    assert a.category == ns.CATEGORY_NEED_CREDENTIAL and a.win_err == 1326
    assert a.may_ask is True


def test_bare_host_stops_at_the_share_level_without_connecting(fakes):
    """`\\主机` 本版不列共享（排在主路径真机验过之后），所以这里连一次都不该试"""
    net, cred = fakes
    a = ns.plan_open(r"\\NAS")
    assert a.category == ns.CATEGORY_NOT_SHARE_LEVEL
    assert a.win_err == ns.ERROR_BAD_PATHNAME
    assert net.connect_calls() == [] and cred.log == []


def test_device_prefixed_unc_is_left_to_the_caller(fakes):
    r"""`\\?\UNC\` 是别的库造出来的形状，不当作用户想连的共享"""
    net, cred = fakes
    a = ns.plan_open("\\\\?\\UNC\\NAS\\photo")
    assert a.is_unc is False
    assert net.names() == []


def test_non_windows_gets_guidance_and_no_syscall(monkeypatch):
    net = FakeNet(reachable=False)
    cred = FakeCred(saved={})
    monkeypatch.setattr(ns, "_netapi", lambda: net)
    monkeypatch.setattr(ns, "_credapi", lambda: cred)
    monkeypatch.setattr(ns, "is_supported_platform", lambda: False)
    a = ns.plan_open(r"\\NAS\photo")
    assert a.category == ns.CATEGORY_UNSUPPORTED_PLATFORM
    assert net.connect_calls() == [] and cred.log == []
    assert "Linux" in ns.failure_text(a.category, a.unc)


def test_connect_success_but_path_still_dark_is_not_reported_ok(fakes):
    """连上了但系统还没认下这个路径 —— 不能说「成功」然后导航到一团黑"""
    net, cred = fakes
    net.reachable = False            # is_dir 永远 False
    net.connect_code = 0
    a = ns.plan_open(r"\\NAS\photo")
    assert not a.ok and a.category == ns.CATEGORY_UNKNOWN


def test_retry_with_conflict_disconnects_first(fakes):
    """1219 那一档必须先断开：同机已用别的账号连着时，直接换凭据永远回同一句"""
    net, cred = fakes
    net.connect_code = 0
    net.reachable = True
    unc = ns.parse_unc(r"\\NAS\photo")
    ok, category, code = ns.retry_with_credential(unc, "u2", "pw2",
                                                  ns.CATEGORY_CONFLICT)
    assert ok and category == ns.CATEGORY_OK
    assert net.names()[:2] == ["cancel", "connect"]


def test_retry_with_wrong_password_does_not_disconnect(fakes):
    """对照组：要凭据那一档不该顺手把用户现有的会话拆掉"""
    net, cred = fakes
    net.connect_code = 86
    unc = ns.parse_unc(r"\\NAS\photo")
    ok, category, code = ns.retry_with_credential(unc, "u2", "pw2",
                                                  ns.CATEGORY_NEED_CREDENTIAL)
    assert not ok and category == ns.CATEGORY_NEED_CREDENTIAL and code == 86
    assert "cancel" not in net.names()


@pytest.mark.parametrize("code, ok", [(0, True), (2250, True), (86, False), (53, False)])
def test_cancel_treats_already_gone_as_success(fakes, code, ok):
    """(m) 2250 = 本来就没连着；与 0 同等成功，所以「断开」可以反复点"""
    net, cred = fakes
    net.cancel_code = code
    assert ns.cancel_connect("\\\\NAS\\photo")[0] is ok


@pytest.mark.parametrize("code, ok", [(0, True), (85, True), (86, False), (1219, False)])
def test_connect_idempotent_codes(fakes, code, ok):
    net, cred = fakes
    net.connect_code = code
    assert ns.connect("\\\\NAS\\photo", "u", "p")[0] is ok


def test_api_exception_degrades_to_unknown_not_a_crash(monkeypatch):
    class Boom(object):
        def connect(self, *a):
            raise OSError("mpr.dll 打不开")

        def cancel(self, *a):
            raise OSError("mpr.dll 打不开")

        def is_dir(self, path):
            return False

    monkeypatch.setattr(ns, "_netapi", lambda: Boom())
    assert ns.connect("\\\\NAS\\photo") == (False, None)
    assert ns.cancel_connect("\\\\NAS\\photo") == (False, None)
    assert ns.is_reachable("\\\\NAS\\photo") is False


# ------------------------------------------------------------------ 4. 接线（离屏 GUI）


@pytest.fixture
def pane_q(qapp, tmp_path):
    p = Pane("t_net_share", start_path=str(tmp_path))
    p.show()
    return p


class FakeDialog(object):
    """替掉凭据对话框：不 exec（CI 里弹不动），按控制器脚本交回结果"""

    def __init__(self, parent, attempt, control):
        self.attempt = attempt
        self.parent = parent
        self._control = control

    def exec(self):
        return self._control.result

    # 窗格在 exec 之后才读这三格，所以必须跟着控制器走，不能在构造时定死
    @property
    def username(self):
        return self._control.username

    @property
    def password(self):
        return self._control.password

    @property
    def remember(self):
        return self._control.remember


class DialogControl(object):
    """每次弹框都读这里的脚本，测试可以先改再触发下一次回车"""

    def __init__(self):
        self.made = []
        self.result = QDialog.DialogCode.Rejected
        self.username = "typed_user"
        self.password = "typed_pw"
        self.remember = False


@pytest.fixture
def dialog_stub(monkeypatch):
    control = DialogControl()

    def factory(parent, attempt):
        d = FakeDialog(parent, attempt, control)
        control.made.append(d)
        return d

    monkeypatch.setattr("core.pane.NetCredentialsDialog", factory)
    return control


def type_into_path_bar(pane, path):
    """照实做一遍「用户在地址栏敲完回车」：文本先进框，再走 returnPressed 发信号

    直接调 `on_path_entered(path)` 是不够的 —— 那样地址栏里还留着旧路径，
    「失败后有没有保住用户输入」这条根本没有观测量。
    """
    pane.path_bar.combo_box.setEditText(path)
    pane.path_bar.on_return_pressed()


def _accepted(control, remember=False):
    control.result = QDialog.DialogCode.Accepted
    control.remember = remember


def test_unc_failure_keeps_what_the_user_typed(pane_q, fakes, dialog_stub):
    """改前会 `set_path(current_path)` 把输入抹掉：共享名打错就得整串重打"""
    net, cred = fakes
    net.connect_code = 67                       # 共享不存在 —— 不弹框那一档
    pane_q.navigate_to = lambda p: pytest.fail("不该导航")
    type_into_path_bar(pane_q, r"\\NAS\photos")
    assert pane_q.path_bar.get_path() == r"\\NAS\photos"
    assert "没有名为 photos 的共享" in pane_q.status_label.text()
    assert dialog_stub.made == []               # 这一档绝不弹模态框


def test_non_unc_typo_is_not_taken_over(pane_q, fakes, dialog_stub):
    """对照组：本地手误维持今天的行为（恢复原路径），且不闪「正在连接」"""
    net, cred = fakes
    before = pane_q.current_path
    type_into_path_bar(pane_q, "C:\\definitely_not_here_xyz")
    assert pane_q.path_bar.get_path() == before
    assert not pane_q.status_label.text().startswith("正在连接")
    assert net.names() == [] and cred.log == []
    assert dialog_stub.made == []


def test_need_credential_opens_the_dialog_once(pane_q, fakes, dialog_stub):
    net, cred = fakes
    pane_q.navigate_to = lambda p: pytest.fail("没拿到凭据不该导航")
    type_into_path_bar(pane_q, r"\\NAS\photo")
    assert len(dialog_stub.made) == 1
    assert dialog_stub.made[0].attempt.category == ns.CATEGORY_NEED_CREDENTIAL
    assert isinstance(dialog_stub.made[0].parent, Pane)


def test_dialog_cancel_explains_why_it_asked(pane_q, fakes, dialog_stub):
    net, cred = fakes
    type_into_path_bar(pane_q, r"\\NAS\photo")    # 默认 Rejected
    assert "需要用户名和密码" in pane_q.status_label.text()
    assert cred.writes() == [] and cred.deletes() == []   # 取消 = 什么都没存


def test_dialog_accept_stores_only_when_checked(pane_q, fakes, dialog_stub):
    net, cred = fakes
    net.flip_on_connect = True
    navigated = []
    pane_q.navigate_to = lambda p: navigated.append(p)

    net.codes = [86]
    type_into_path_bar(pane_q, r"\\NAS\photo")    # 第一次取消：不存、不导航
    assert cred.writes() == [] and navigated == []

    net.codes = [86, 0]                           # 探测被拒 → 拿到凭据后连上
    _accepted(dialog_stub, remember=True)
    type_into_path_bar(pane_q, r"\\NAS\photo")
    assert ("write", "pan4dex:smb:NAS\\photo", "typed_user") in cred.log
    assert navigated == ["\\\\NAS\\photo"]

    navigated.clear()
    dialog_stub.remember = False
    type_into_path_bar(pane_q, r"\\NAS\photo")    # 已经可达：不该再弹框、再存
    assert cred.writes() == [("write", "pan4dex:smb:NAS\\photo", "typed_user")]
    assert navigated == ["\\\\NAS\\photo"] and len(dialog_stub.made) == 2


def test_unchecked_remember_clears_the_stale_entry(pane_q, fakes, dialog_stub):
    """没勾「记住」时删掉旧条目，否则下次 plan_open 拿旧口令白试一次"""
    net, cred = fakes
    cred.saved[ns.credential_target("NAS", "photo")] = ("old", "oldpw")
    net.flip_on_connect = True
    net.codes = [86, 0]                           # 旧口令被拒 → 新口令连上
    _accepted(dialog_stub, remember=False)
    type_into_path_bar(pane_q, r"\\NAS\photo")
    assert ("delete", "pan4dex:smb:NAS\\photo") in cred.log
    assert cred.saved == {}


def test_conflict_retry_disconnects_then_reports_the_new_reason(pane_q, fakes,
                                                                dialog_stub):
    """改前那版会把弹框前的旧文案再印一遍；换过凭据之后原因可能变了（1219 → 86）"""
    net, cred = fakes
    net.codes = [1219, 86]                 # 探测回冲突，断开后重连回口令不对
    _accepted(dialog_stub)
    type_into_path_bar(pane_q, r"\\NAS\photo")
    assert net.names() == ["is_dir", "connect", "cancel", "connect"]
    assert "需要用户名和密码" in pane_q.status_label.text()
    assert "另一个账号" not in pane_q.status_label.text()


# ------------------------------------------------------------------ 5. 真对话框控件


def _real_dialog(attempt, monkeypatch, platform=True, saved=None):
    from widgets.net_credentials_dialog import NetCredentialsDialog
    net = FakeNet(reachable=False)
    cred = FakeCred(saved=dict(saved or {}))
    monkeypatch.setattr(ns, "_netapi", lambda: net)
    monkeypatch.setattr(ns, "_credapi", lambda: cred)
    monkeypatch.setattr(ns, "is_supported_platform", lambda: platform)
    return NetCredentialsDialog(None, attempt)


def test_real_dialog_widgets(qapp, monkeypatch):
    """弹框本身在 CI 里 exec 不动，但控件状态必须查：默认按钮、空用户名、显示口令"""
    from PyQt6.QtWidgets import QLineEdit
    attempt = ns.ShareAttempt(ns.parse_unc(r"\\NAS\photo"),
                              ns.CATEGORY_NEED_CREDENTIAL, 86, r"\\NAS\photo")
    dlg = _real_dialog(attempt, monkeypatch)
    assert dlg.user_edit.isEnabled() and dlg.pass_edit.isEnabled()
    assert dlg.pass_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dlg.ok_btn.isEnabled() is False          # 用户名空着不许点
    dlg.show_pass.toggle()
    assert dlg.pass_edit.echoMode() == QLineEdit.EchoMode.Normal
    dlg.show_pass.toggle()
    assert dlg.pass_edit.echoMode() == QLineEdit.EchoMode.Password
    dlg.user_edit.setText("u")
    assert dlg.ok_btn.isEnabled() is True
    # 口令格留空是可以点的：guest 共享就是这个形状
    dlg._accept()
    assert dlg.username == "u" and dlg.password == "" and dlg.remember is False


def test_real_dialog_prefers_our_stored_user_name(qapp, monkeypatch):
    target = ns.credential_target("NAS", "photo")
    attempt = ns.ShareAttempt(ns.parse_unc(r"\\NAS\photo"),
                              ns.CATEGORY_NEED_CREDENTIAL, 86, r"\\NAS\photo")
    dlg = _real_dialog(attempt, monkeypatch, saved={target: ("domain\\bob", "pw")})
    assert dlg.user_edit.text() == "domain\\bob"
    assert dlg.pass_edit.text() == ""              # 口令绝不回填到框里
    assert dlg.remember_box.isChecked() is True


def test_real_dialog_disables_remember_off_windows(qapp, monkeypatch):
    """Linux 这版没有地方存：整格禁用，不给「勾了但没存上」的假象"""
    attempt = ns.ShareAttempt(ns.parse_unc(r"\\NAS\photo"),
                              ns.CATEGORY_NEED_CREDENTIAL, 86, r"\\NAS\photo")
    dlg = _real_dialog(attempt, monkeypatch, platform=False)
    assert dlg.remember_box.isEnabled() is False
    dlg.remember_box.setChecked(True)              # 用户/测试强行勾上也不作数
    dlg.user_edit.setText("u")
    dlg._accept()
    assert dlg.remember is False


def test_real_dialog_conflict_header_asks_which_account(qapp, monkeypatch):
    attempt = ns.ShareAttempt(ns.parse_unc(r"\\NAS\photo"),
                              ns.CATEGORY_CONFLICT, 1219, r"\\NAS\photo")
    dlg = _real_dialog(attempt, monkeypatch)
    assert "另一个账号" in dlg._header_text()
    assert "另一个账号" in dlg.findChild(QLabel).text()


def test_guest_share_navigation_unchanged_by_the_feature(pane_q, fakes, dialog_stub):
    """成功路径一个字没动：isdir 说行就直接导航，net_share 一次都不该被叫"""
    net, cred = fakes
    navigated = []
    pane_q.navigate_to = lambda p: navigated.append(p)
    type_into_path_bar(pane_q, pane_q.current_path)
    assert navigated == [pane_q.current_path]
    assert net.names() == [] and cred.log == [] and dialog_stub.made == []
