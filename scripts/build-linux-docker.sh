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
sudo docker build --network=host -t ${DOCKER_IMAGE} -f packaging/Dockerfile-linux .

# 清理旧容器
sudo docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

# 运行构建
echo "[3/6] 运行构建容器..."
sudo docker run --name ${CONTAINER_NAME} \
    -v "$(pwd):/app" \
    -e "VERSION=${VERSION}" \
    -e "PYBUILD_TIME=$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')" \
    ${DOCKER_IMAGE} \
    bash -c "
        cd /app
        
        # 版本号 + 编译时间写入 config/app_config.py：
        # - VERSION 必须用传入的版本号覆盖（构建现场源码可能滞后，否则
        #   打包进程序的版本号与产物名不一致）
        # - BUILD_TIME 由宿主按东八区算好传入（容器内 date 是 UTC，直接
        #   取会差 8 小时）
        sed -i \"s/^VERSION = \\\"[^\\\"]*\\\"/VERSION = \\\"\${VERSION}\\\"/\" config/app_config.py
        sed -i \"s/^BUILD_TIME = \\\"[^\\\"]*\\\"/BUILD_TIME = \\\"\${PYBUILD_TIME}\\\"/\" config/app_config.py
        
        # 构建：打包 resources/icons + resources/themes（图标/主题资源），
        # 否则运行时图标缺失、任务栏显示默认图标。
        # 同时打包 resources/tools/exiftool-linux（应用内携带的 ExifTool Perl 包，
        # 用系统 perl 运行，避免目标系统未装 exiftool 时拍摄日期列不可用）。
        # 注意：不打包 resources/tools/exiftool（Windows 专用 exe + Perl 运行时）。
        pyinstaller --onefile --windowed --name=pan4dex \
            --add-data resources/icons:resources/icons \
            --add-data resources/themes:resources/themes \
            --add-data resources/tools/exiftool-linux:resources/tools/exiftool-linux \
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
