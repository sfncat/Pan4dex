#!/bin/bash
set -e

VERSION=${1:-$(python3 -c "import re; m=re.search(r'^VERSION\s*=\s*\"([^\"]+)\"', open('config/app_config.py', encoding='utf-8').read(), re.M); print(m.group(1))")}
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
sudo docker build -t ${DOCKER_IMAGE} -f packaging/Dockerfile-linux .

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
        
        # 更新全局配置中的编译时间（写入 config/app_config.py，不再改写 main.py）
        export PYBUILD_TIME=\$(date '+%Y-%m-%d %H:%M:%S')
        sed -i \"s/^BUILD_TIME = \\\"[^\\\"]*\\\"/BUILD_TIME = \\\"\${PYBUILD_TIME}\\\"/\" config/app_config.py
        
        # 构建：必须打包 resources（图标/主题资源），否则运行时图标缺失、任务栏显示默认图标
        pyinstaller --onefile --windowed --name=pan4dex \
            --add-data resources:resources \
            main.py
        
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
