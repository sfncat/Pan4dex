#!/usr/bin/env bash
# Pan4dex 万格 — 构建脚本
# Linux 在 gti 上打包，Windows 在 win59 上打包
# 用法: ./scripts/build.sh [版本号]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RELEASES_DIR="${PROJECT_ROOT}/releases"

# 目标机配置
TARGET_HOST="gti"
TARGET_BUILD_DIR="~/pan4dex-build"
TARGET_DIST_DIR="~/tools/pan4dex"

# Windows 配置
WIN_HOST="win59"
WIN_BUILD_DIR="C:\\Users\\sshuser\\pan4dex"

# 获取版本号
VERSION="${1:-}"
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
echo "=========================================="

# 1. 同步源码到目标机
echo "[1/6] 同步源码到目标机..."
rsync -avz --exclude='.venv' --exclude='build' --exclude='dist' --exclude='__pycache__' \
    --exclude='*.pyc' --exclude='.git' --exclude='releases' \
    "${PROJECT_ROOT}/" "${TARGET_HOST}:${TARGET_BUILD_DIR}/" 2>&1 | tail -3

# 2. 清理旧构建
echo "[2/6] 清理旧构建..."
ssh "${TARGET_HOST}" "cd ${TARGET_BUILD_DIR} && rm -rf build dist"

# 3. 在目标机上打包 Linux 版本
echo "[3/6] 构建 Linux 版本（在 ${TARGET_HOST} 上）..."
BUILD_TIME=$(date '+%Y-%m-%d %H:%M:%S')
# 注入编译时间到 main.py（目标机上）
ssh "${TARGET_HOST}" "cd ${TARGET_BUILD_DIR} && sed -i 's|__build_time__ = \"\"|__build_time__ = \"${BUILD_TIME}\"|' main.py && ~/.local/bin/pyinstaller --onefile --windowed --name=pan4dex main.py 2>&1 | tail -3"

# 4. 安装到目标机
echo "[4/6] 安装到 ${TARGET_DIST_DIR}..."
ssh "${TARGET_HOST}" "rm -f ${TARGET_DIST_DIR}/pan4dex; mkdir -p ${TARGET_DIST_DIR} && cp ${TARGET_BUILD_DIR}/dist/pan4dex ${TARGET_DIST_DIR}/pan4dex && chmod +x ${TARGET_DIST_DIR}/pan4dex"

# 5. 构建 Windows 版本
echo "[5/6] 构建 Windows 版本（在 ${WIN_HOST} 上）..."
scp -r "${PROJECT_ROOT}/" "${WIN_HOST}:${WIN_BUILD_DIR}\\" 2>&1 | tail -2
ssh "${WIN_HOST}" "cmd /c 'cd ${WIN_BUILD_DIR} && build.bat ${VERSION}'" 2>&1 | tail -3

# 6. 复制到本机 releases 目录
echo "[6/6] 备份到本地 releases 目录..."
mkdir -p "${RELEASES_DIR}"
scp "${TARGET_HOST}:${TARGET_BUILD_DIR}/dist/pan4dex" "${RELEASES_DIR}/pan4dex-${VERSION}-linux"
chmod +x "${RELEASES_DIR}/pan4dex-${VERSION}-linux"
scp "${WIN_HOST}:${WIN_BUILD_DIR}\\releases\\pan4dex-${VERSION}.exe" "${RELEASES_DIR}/" 2>/dev/null || true

# 验证
echo ""
echo "  ✓ 构建成功"
echo "  ✓ 版本: ${VERSION}"
echo "  ✓ Linux: ${TARGET_HOST}:${TARGET_DIST_DIR}/pan4dex"
echo "  ✓ 本机 Linux: ${RELEASES_DIR}/pan4dex-${VERSION}-linux"
if [ -f "${RELEASES_DIR}/pan4dex-${VERSION}.exe" ]; then
    echo "  ✓ 本机 Windows: ${RELEASES_DIR}/pan4dex-${VERSION}.exe"
fi
echo ""
echo "=========================================="
echo "  构建完成: pan4dex-${VERSION}"
echo "=========================================="
