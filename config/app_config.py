# -*- coding: utf-8 -*-
"""应用全局配置（发布元数据、应用级常量）。

集中放在本文件，不写进逻辑代码：

- 改版本号 / 应用名 / 组织名 / 默认窗口几何 / 默认主题，只需编辑本文件
- 构建脚本 scripts/build_windows.py 从本文件读取 VERSION，
  编译时间则由其在打包前生成 config/_build_info.py（未入库，打包后删除）
- main.py / core/main_window.py / config/theme_manager.py 等仅从这里 import 使用

注意：BUILD_TIME 不在本文件写死，源码开发运行时为空（显示 dev），
正式产物里是打包那一刻的编译时间。
"""

# ---- 发布元数据 ----
APP_NAME = "Pan4dex"                  # 应用英文名
APP_NAME_CN = "万格"                    # 应用中文名
VERSION = "1.9.044"                    # 版本号（开发分支 dev/shell-behavior-smb-perf 从 1.9.000 起每次发布末位 +1）

# 编译时间（YYYY-MM-DD HH:MM:SS）：构建脚本打包前生成 config/_build_info.py（已 gitignore，
# 打包后删除），让时间戳随包内嵌又不弄脏工作区；源码运行没有该文件，按 dev 显示。
try:
    from ._build_info import BUILD_TIME
except ImportError:
    BUILD_TIME = ""

# ---- 应用级常量 ----
ORG_NAME = "sfncat"                    # QSettings 组织名（决定配置写入位置）
APP_STYLE = "Fusion"                   # Qt 全局样式（跨平台一致性最好）
DEFAULT_THEME = "dark"                 # 默认主题（dark / light）

# 默认窗口几何（最小尺寸，窗口大小由 QSettings 记忆恢复）
DEFAULT_WINDOW_MIN_WIDTH = 1024
DEFAULT_WINDOW_MIN_HEIGHT = 768

# 图标文件名：统一使用 icon.png（圆角 PNG，Windows/Linux 运行时一致；
# Windows 的 exe 内嵌图标仍用 icon.ico，由构建脚本 --icon 指定，两者视觉一致）
ICON_FILE = "icon.png"

# 菜单栏右侧「应用启动器」默认配置（设置对话框可增删改，保存到 QSettings）
# 每项: {"name": 按钮显示名, "command": 可执行文件/命令（Windows 可用命令名或 exe 路径）}
import sys as _sys
if _sys.platform == "win32":
    DEFAULT_LAUNCHER_APPS = [
        {"name": "记事本", "command": "notepad.exe"},
        {"name": "计算器", "command": "calc.exe"},
        {"name": "资源管理器", "command": "explorer.exe"},
    ]
else:
    # Linux 无统一内置应用，默认留空，由用户在设置中自行添加
    DEFAULT_LAUNCHER_APPS = []
