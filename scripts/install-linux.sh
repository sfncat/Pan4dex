#!/bin/bash
# 安装 Pan4dex 桌面集成：应用图标（文件管理器/应用菜单）+ .desktop 启动器
#
# 用法:
#   ./install-linux.sh [可执行文件路径]
#   不传参数时，自动找 releases/pan4dex-<VERSION>-linux
#
# 解决的问题: Linux 文件管理器/应用菜单里不显示 Pan4dex 图标（默认图标），
# 通过把 icon.png 安装到 ~/.local/share/icons/hicolor 并把 .desktop 安装到
# ~/.local/share/applications 让桌面环境识别应用图标。
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 1) 确定可执行文件路径
APP_EXEC="${1:-}"
if [ -z "$APP_EXEC" ]; then
    VERSION="$(grep '^VERSION' "$PROJECT_ROOT/config/app_config.py" | head -1 | sed 's/.*"\([^"]*\)".*/\1/')"
    APP_EXEC="$PROJECT_ROOT/releases/pan4dex-${VERSION}-linux"
fi
if [ ! -f "$APP_EXEC" ]; then
    echo "错误: 找不到可执行文件: $APP_EXEC"
    echo "请传入路径，例如: $0 /opt/pan4dex/pan4dex"
    exit 1
fi
APP_EXEC="$(realpath "$APP_EXEC")"
chmod +x "$APP_EXEC"
echo "[1/3] 可执行文件: $APP_EXEC"

# 2) 安装图标到 hicolor 图标主题（GNOME/KDE 等桌面环境通用）
ICON_SRC="$PROJECT_ROOT/resources/icons/icon.png"
if [ ! -f "$ICON_SRC" ]; then
    echo "错误: 找不到图标 $ICON_SRC"
    exit 1
fi
for size in 256 512; do
    dest="$HOME/.local/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dest"
    install -m 644 "$ICON_SRC" "$dest/pan4dex.png"
done
echo "[2/3] 图标已安装: ~/.local/share/icons/hicolor/{256,512}x{256,512}/apps/pan4dex.png"

# 3) 安装 .desktop 启动器（用真实可执行路径替换占位符）
DESKTOP_SRC="$PROJECT_ROOT/packaging/pan4dex.desktop"
DESKTOP_DEST="$HOME/.local/share/applications/pan4dex.desktop"
mkdir -p "$(dirname "$DESKTOP_DEST")"
sed "s|__EXEC_PATH__|$APP_EXEC|g" "$DESKTOP_SRC" > "$DESKTOP_DEST"
chmod +x "$DESKTOP_DEST"
echo "[3/3] 启动器已安装: $DESKTOP_DEST"

# 4) 刷新桌面/图标数据库（命令不存在时忽略）
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -q "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo ""
echo "完成！应用菜单/文件管理器应显示 Pan4dex 图标。"
echo "若未立即刷新: 注销重登，或重启桌面（如: systemctl --user restart plasma-* 或重启 Xorg/Wayland）"
