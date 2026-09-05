#!/bin/bash
# Pan4dex Linux Docker 构建入口（薄封装）
#
# 说明：Linux Docker 构建的 canonical 脚本已迁移到
#   scripts/build-linux-docker.sh
# 构建镜像为 packaging/Dockerfile-linux，版本号/编译时间统一由
#   config/app_config.py 管理（构建时容器内强制覆盖 VERSION，
#   BUILD_TIME 由宿主按东八区注入，避免容器 UTC 差 8 小时）。
#
# 本文件保留在 docker/ 目录仅为兼容旧习惯，直接转发给新脚本。
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$DIR/scripts/build-linux-docker.sh" "$@"
