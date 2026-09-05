#!/bin/bash
# Pan4dex Docker 构建入口脚本（历史副本，仅供参考）
#
# ⚠️ canonical 位置：packaging/Dockerfile-linux 内联创建（内容与本文件一致）。
# 构建镜像已内联同样的逻辑，本文件不再被引用，仅保留用于追溯。
# 启动 Xvfb 虚拟显示环境，然后执行命令。

Xvfb :99 -screen 0 1024x768x24 &>/dev/null &
export DISPLAY=:99
sleep 1
exec "$@"
