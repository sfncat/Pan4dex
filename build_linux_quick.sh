#!/bin/bash
# Pan4dex v1.9.020 Linux 版本快速构建脚本
# 需要 Docker 环境

set -e

echo "=========================================="
echo "  Pan4dex v1.9.020 Linux 构建"
echo "=========================================="
echo ""

cd "$(dirname "$0")"

echo "[1/3] 检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo "错误：未找到 Docker，请先安装 Docker"
    echo "参考：https://docs.docker.com/get-docker/"
    exit 1
fi

docker info > /dev/null 2>&1 || {
    echo "错误：Docker 未运行"
    echo "请执行：sudo systemctl start docker"
    exit 1
}

echo "[2/3] 安装依赖（Python）..."
pip3 install -q PyQt6 PyInstaller qdarkstyle pillow pillow-heif send2trash pyte

echo "[3/3] 开始构建..."
echo ""
bash scripts/build-linux-docker.sh

echo ""
echo "=========================================="
echo "  构建完成！"
echo "=========================================="
echo ""
echo "产物位置：releases/pan4dex-1.9.020-linux"
echo ""
ls -lh releases/pan4dex-1.9.020-linux
echo ""
