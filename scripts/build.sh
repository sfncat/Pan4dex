#!/usr/bin/env bash
# Pan4dex 万格 — 统一构建脚本
# Linux: Docker 本机构建（Debian bullseye, glibc 2.31）→ 部署到 gti (58)
# Windows: win54 (54) 构建 → 部署到 win55 (55)
# 用法: ./scripts/build.sh [--skip-windows] [版本号]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RELEASES_DIR="${PROJECT_ROOT}/releases"

# 解析参数
SKIP_WINDOWS=false
VERSION=""
for arg in "$@"; do
    case "$arg" in
        --skip-windows) SKIP_WINDOWS=true ;;
        -*) echo "未知选项: $arg"; exit 1 ;;
        *) VERSION="$arg" ;;
    esac
done

# 目标机配置
GTI_HOST="gti"
GTI_DIST_DIR="~/tools/pan4dex"

# Windows 构建机（构建在这台机器上执行）
WIN_BUILD_HOST="win54"
WIN_BUILD_MAC="52:54:10:73:70:cd"  # WOL MAC 地址
WIN_BUILD_IP="192.168.5.54"
# Windows 部署目标（构建完成后复制到这里）
WIN_DEPLOY_HOST="192.168.5.55"
WIN_DEPLOY_USER="sshuser"
WIN_DEPLOY_DIR="D:\\workspace\\2026\\pan4dex\\dist"

# 获取版本号
if [ -z "$VERSION" ]; then
    VERSION=$(grep -oP '__version__\s*=\s*["\x27]([^"\x27]+)["\x27]' "${PROJECT_ROOT}/main.py" 2>/dev/null | grep -oP '["\x27]([^"\x27]+)["\x27]' | tr -d '"' | tr -d "'")
fi
if [ -z "$VERSION" ]; then
    VERSION="v0.0.0-dev"
fi
[[ "$VERSION" != v* ]] && VERSION="v${VERSION}"

echo "=========================================="
echo "  Pan4dex 构建"
echo "  版本: ${VERSION}"
echo "  Windows: $([ "$SKIP_WINDOWS" = true ] && echo "跳过" || echo "启用")"
echo "=========================================="

# ── 1. Linux Docker 构建 ──
echo "[1/5] Linux Docker 构建..."

# 确保 Docker 运行
if ! sudo systemctl is-active --quiet docker; then
    echo "  启动 Docker..."
    sudo systemctl start docker
    sleep 2
fi

# 构建镜像 + 运行构建
DOCKER_IMAGE="pan4dex-builder-linux"
CONTAINER_NAME="pan4dex-build-linux"

sudo docker build -t ${DOCKER_IMAGE} -f docker/Dockerfile . 2>&1 | tail -3
sudo docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

sudo docker run --name ${CONTAINER_NAME} \
    -v "$(pwd):/app" \
    -e "VERSION=${VERSION}" \
    ${DOCKER_IMAGE} \
    bash -c "
        cd /app
        export PYBUILD_TIME=\$(date '+%Y-%m-%d %H:%M:%S')
        sed -i \"s/__build_time__ = \\\"\\\"/__build_time__ = \\\"\${PYBUILD_TIME}\\\"/\" main.py
        pyinstaller --onefile --windowed --name=pan4dex main.py
        mkdir -p /app/releases
        mv dist/pan4dex /app/releases/pan4dex-${VERSION}-linux
        chmod +x /app/releases/pan4dex-${VERSION}-linux
    " 2>&1 | tail -5

sudo docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

# 验证 Linux 产物
LINUX_BIN="${RELEASES_DIR}/pan4dex-${VERSION}-linux"
if [ ! -f "${LINUX_BIN}" ]; then
    echo "  ✗ Linux 构建失败"
    exit 1
fi
echo "  ✓ Linux: $(ls -lh ${LINUX_BIN} | awk '{print $5}')"

# ── 2. Windows 构建（win54） ──
WIN_EXE="pan4dex-${VERSION}.exe"
if [ "$SKIP_WINDOWS" = true ]; then
    echo "[2/5] Windows 构建已跳过"
else
    echo "[2/5] Windows 构建（${WIN_BUILD_HOST}）..."

    # 检查 win54 是否在线，不在线则唤醒
    if ! ping -c 1 -W 2 ${WIN_BUILD_IP} &>/dev/null; then
        echo "  win54 不在线，发送 Wake-on-LAN..."
        wakeonlan -i 192.168.5.50 -p 9 ${WIN_BUILD_MAC} 2>&1
        echo "  等待 win54 启动（最多 60 秒）..."
        for i in $(seq 1 12); do
            sleep 5
            if ping -c 1 -W 2 ${WIN_BUILD_IP} &>/dev/null; then
                echo "  win54 已启动"
                break
            fi
            echo "  等待中... (${i}x5s)"
        done
        if ! ping -c 1 -W 2 ${WIN_BUILD_IP} &>/dev/null; then
            echo "  ✗ win54 唤醒失败，请检查网络或手动开机"
            exit 1
        fi
        # 等系统完全就绪 + SSH 服务启动
        echo "  等待 SSH 服务就绪..."
        for i in $(seq 1 12); do
            sleep 5
            if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${WIN_BUILD_HOST} 'echo OK' &>/dev/null; then
                echo "  SSH 就绪"
                break
            fi
            echo "  等待 SSH... (${i}x5s)"
        done
    fi

    # 同步源码到 win54（用 tar 管道确保完全覆盖）
    cd "${PROJECT_ROOT}"
    tar cf - . | ssh ${WIN_BUILD_HOST} 'cmd /c "cd /d C:\workspace\pan4dex && tar xf -"' 2>&1 | tail -3

    # 在 win54 上执行构建
    ssh ${WIN_BUILD_HOST} "cmd /c \"cd C:\\workspace\\pan4dex && python scripts/build_windows.py ${VERSION}\"" 2>&1 | tail -5

    # 验证 Windows 产物
    WIN_EXE="pan4dex-${VERSION}.exe"
    if ! ssh ${WIN_BUILD_HOST} "cmd /c \"if exist C:\\workspace\\pan4dex\\releases\\${WIN_EXE} echo OK\"" 2>&1 | grep -q "OK"; then
        echo "  ✗ Windows 构建失败"
        exit 1
    fi
    echo "  ✓ Windows: ${WIN_EXE}"

    # ── 3. 部署 Windows 到 win55 (55) ──
    echo "[3/5] 部署 Windows 到 ${WIN_DEPLOY_HOST}..."
    # 先从 win54 拉到本地
    scp "${WIN_BUILD_HOST}:C:/workspace/pan4dex/releases/${WIN_EXE}" "${RELEASES_DIR}/" 2>&1 | tail -1
    # 再从本地推到 win55
    scp "${RELEASES_DIR}/${WIN_EXE}" "${WIN_DEPLOY_USER}@${WIN_DEPLOY_HOST}:${WIN_DEPLOY_DIR}/" 2>&1 | tail -1
    echo "  ✓ Windows 已部署到 ${WIN_DEPLOY_HOST}:${WIN_DEPLOY_DIR}/${WIN_EXE}"
fi

# ── 4. 部署 Linux 到 gti (58) ──
echo "[4/5] 部署 Linux 到 ${GTI_HOST}..."
scp "${LINUX_BIN}" "${GTI_HOST}:${GTI_DIST_DIR}/pan4dex" 2>&1 | tail -1
ssh ${GTI_HOST} "chmod +x ${GTI_DIST_DIR}/pan4dex" 2>&1
echo "  ✓ Linux 已部署到 ${GTI_HOST}:${GTI_DIST_DIR}/pan4dex"

# ── 5. 备份到本地 releases ──
echo "[5/5] 备份到本地..."
mkdir -p "${RELEASES_DIR}"
echo "  ✓ ${RELEASES_DIR}/pan4dex-${VERSION}-linux"
if [ "$SKIP_WINDOWS" = false ] && [ -f "${RELEASES_DIR}/${WIN_EXE}" ]; then
    chmod +x "${RELEASES_DIR}/${WIN_EXE}" 2>/dev/null || true
    echo "  ✓ ${RELEASES_DIR}/${WIN_EXE}"
fi

# 验证
echo ""
echo "  ✓ 构建成功"
echo "  ✓ 版本: ${VERSION}"
echo "  ✓ Linux: ${GTI_HOST}:${GTI_DIST_DIR}/pan4dex"
if [ "$SKIP_WINDOWS" = false ]; then
    echo "  ✓ Windows: ${WIN_DEPLOY_HOST}:${WIN_DEPLOY_DIR}/${WIN_EXE}"
fi
echo ""
echo "=========================================="
echo "  构建完成: pan4dex-${VERSION}"
echo "=========================================="
