#!/bin/bash
# Pan4dex 万格 - 启动脚本
# 自动创建虚拟环境并安装依赖

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# 创建虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "首次运行，正在创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -q PyQt6 send2trash Pillow
    echo "虚拟环境创建完成"
else
    source "$VENV_DIR/bin/activate"
fi

# 启动 Pan4dex
cd "$SCRIPT_DIR"
python3 main.py
