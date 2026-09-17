"""
Pan4dex 万格 — Linux 桌面集成（.desktop 启动器）

`StartupWMClass` 是桌面环境把「已运行的窗口」归到「应用启动器」的唯一线索：它必须等于
窗口 WM_CLASS 的某一项。Qt 在 X11 上写的两项分别是

    res_name  = argv[0] 的 basename      → 冻结产物叫 pan4dex-1.9.016-linux，每版都变
    res_class = applicationName()        → 就是 APP_NAME = "Pan4dex"（区分大小写）

以前模板里写的是小写 `pan4dex`，两项都对不上（v1.9.016 在 230 真机上 `xprop` 一比才发现）：
任务栏里窗口与图标不分组、应用菜单点了图标又起一个实例。这里钉住「与 APP_NAME 同源」，
并顺手钉住两条同样只有真机才会暴露的约定。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main                                                    # noqa: E402
from config.app_config import APP_NAME, APP_NAME_CN            # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_entries(text):
    """`.desktop` → dict（只取 Desktop Entry 段的 `Key=Value`）"""
    return dict(re.findall(r"^([A-Za-z]+(?:\[[a-z_]+\])?)=(.*)$", text, re.M))


class TestGeneratedDesktopEntry:
    def test_startup_wmclass_comes_from_app_name(self):
        """匹配键必须与 Qt 写进 res_class 的那个值同源，不能各写一份字面量"""
        got = parse_entries(main._desktop_entry_text("/opt/pan4dex/pan4dex"))
        assert got["StartupWMClass"] == APP_NAME

    def test_startup_wmclass_does_not_depend_on_the_binary_name(self):
        """匹配键不能取自产物名：冻结产物名带版本号，每发布一次就悄悄失效"""
        a = parse_entries(main._desktop_entry_text("/opt/pan4dex-1.9.016-linux"))
        b = parse_entries(main._desktop_entry_text("/opt/pan4dex-2.0.001-linux"))
        assert a["StartupWMClass"] == b["StartupWMClass"] == APP_NAME

    def test_icon_key_matches_the_name_installed_into_hicolor(self):
        """`Icon=pan4dex` 要能查到：安装时写进去的就是 `<Icon 键>.png`"""
        got = parse_entries(main._desktop_entry_text("/usr/bin/pan4dex"))
        assert got["Icon"] == "pan4dex"

    def test_required_keys_present_and_exec_passed_through(self):
        exec_path = "/home/kali/workspace/pan4dex-dev/releases/pan4dex-1.9.016-linux"
        got = parse_entries(main._desktop_entry_text(exec_path))
        for key in ("Type", "Name", "Exec", "Icon", "Categories"):
            assert got.get(key), f"缺 {key}，桌面环境不会把它当应用"
        assert got["Exec"] == exec_path
        assert got["Name"] == f"{APP_NAME} {APP_NAME_CN}"


class TestPackagedTemplateAgreesWithGeneratedOne:
    """`packaging/pan4dex.desktop` 是另一条安装路（scripts/install-linux.sh）用的模板

    两条路各写一份字段，改一处忘另一处就会「有的桌面能用、有的不能用」，所以直接比对。
    """

    def _template(self):
        with open(os.path.join(REPO, "packaging", "pan4dex.desktop"),
                  encoding="utf-8", newline="") as f:
            return f.read()

    def test_template_and_generated_text_have_the_same_keys(self):
        tmpl = set(parse_entries(self._template()).keys())
        gen = set(parse_entries(main._desktop_entry_text("X")).keys())
        # 模板里 Exec 是占位符 __EXEC_PATH__，两边键集应完全一致
        assert tmpl == gen, f"模板与生成串字段不一致：只在模板 {tmpl - gen}，只在生成串 {gen - tmpl}"

    def test_template_values_survive_a_crlf_checkout(self):
        """从 Windows 工作树拷过去的副本常带 CRLF：值里混进 `\r` 就匹配不上

        仓库里存的是 LF，所以不能直接断工作树文件无 CR（那测的是 checkout 方式，
        Windows 上 `core.autocrlf` 会把它变成 CRLF）；安装脚本里有一道 `tr -d '\r'`，
        这里钉住“剔 CR 后各键仍与生成串一致”。
        """
        raw = self._template().replace("\r", "")
        tmpl = parse_entries(raw)
        gen = parse_entries(main._desktop_entry_text("X"))
        for key in ("StartupWMClass", "Icon", "Type", "Categories"):
            assert tmpl[key] == gen[key], f"{key} 两边不一致：{tmpl[key]!r} vs {gen[key]!r}"
