#!/bin/bash
set -e

VERSION=${1:-$(python3 -c "exec(open('main.py').read().split('__version__ = ')[1].split(chr(34))[1]); print(__version__)")}
RELEASES_DIR="$(pwd)/releases"
DOCKER_IMAGE="pan4dex-builder-linux"
CONTAINER_NAME="pan4dex-build-linux"

echo "=========================================="
echo "  Pan4dex Linux Docker 构建"
echo "  版本: ${VERSION}"
echo "=========================================="

# 确保 Docker 运行
if ! sudo systemctl is-active --quiet docker; then
    echo "[1/6] 启动 Docker..."
    sudo systemctl start docker
    sleep 2
else
    echo "[1/6] Docker 已运行"
fi

# 构建镜像
echo "[2/6] 构建 Docker 镜像..."
sudo docker build -t ${DOCKER_IMAGE} -f docker/Dockerfile .

# 清理旧容器
sudo docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

# 运行构建
echo "[3/6] 运行构建容器..."
sudo docker run --name ${CONTAINER_NAME} \
    -v "$(pwd):/app" \
    -e "VERSION=${VERSION}" \
    ${DOCKER_IMAGE} \
    bash -c "
        cd /app
        
        # 注入构建时间
        export PYBUILD_TIME=\$(date '+%Y-%m-%d %H:%M:%S')
        sed -i \"s/__build_time__ = \\\"\\\"/__build_time__ = \\\"\${PYBUILD_TIME}\\\"/\" main.py
        
        # 构建
        pyinstaller --onefile --windowed --name=pan4dex main.py
        
        # 移动到 releases
        mkdir -p /app/releases
        mv dist/pan4dex /app/releases/pan4dex-${VERSION}-linux
        chmod +x /app/releases/pan4dex-${VERSION}-linux
    "

echo "[4/6] 清理容器..."
sudo docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

# 验证
echo ""
if [ -f "${RELEASES_DIR}/pan4dex-${VERSION}-linux" ]; then
    echo "  ✓ 构建成功"
    echo "  ✓ 版本: ${VERSION}"
    echo "  ✓ 文件: ${RELEASES_DIR}/pan4dex-${VERSION}-linux"
    ls -lh "${RELEASES_DIR}/pan4dex-${VERSION}-linux"
else
    echo "  ✗ 构建失败"
    exit 1
fi

echo ""
echo "=========================================="
echo "  构建完成: pan4dex-${VERSION}"
echo "=========================================="
