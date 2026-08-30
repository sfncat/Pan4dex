#!/bin/bash
# Pan4dex Docker 构建入口脚本
# 启动 Xvfb 虚拟显示环境，然后执行命令

Xvfb :99 -screen 0 1024x768x24 &>/dev/null &
export DISPLAY=:99
sleep 1
exec "$@"
