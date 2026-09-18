#!/bin/bash
# Pan4dex Linux Docker 构建脚本（用于 Kali Linux 230）
# 使用方法：chmod +x build-pan4dex-linux.sh && ./build-pan4dex-linux.sh

set -e

echo "=========================================="
echo "  Pan4dex Linux Docker 构建（230 专用）"
echo "=========================================="

# 1. 进入项目目录
cd /home/kali/workspace/pan4dex || { echo "❌ 无法进入项目目录"; exit 1; }

# 2. 拉取最新代码（可选）
echo "[1/5] 同步最新代码..."
git pull origin main 2>/dev/null || echo "  ⚠️  跳过 git pull（可能已在最新状态）"

# 3. 检查 Docker
echo "[2/5] 检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装："
    echo "   apt update && apt install -y docker.io docker-compose"
    exit 1
fi

docker info >/dev/null 2>&1 || {
    echo "⚠️  Docker 服务未运行，尝试启动..."
    sudo systemctl start docker || { echo "❌ Docker 启动失败"; exit 1; }
}

# 4. 执行构建
echo "[3/5] 开始构建 Docker 镜像并打包..."
bash scripts/build-linux-docker.sh

# 5. 验证产物
echo "[4/5] 验证产物..."
LINUX_BIN=$(ls releases/pan4dex-*-linux 2>/dev/null | head -1)
if [ -z "$LINUX_BIN" ]; then
    echo "❌ 未找到 Linux 可执行文件"
    exit 1
fi

echo "✅ 找到产物：$LINUX_BIN"
echo "   大小：$(du -h "$LINUX_BIN" | cut -f1)"
echo "   类型：$(file "$LINUX_BIN")"

# 6. 检查依赖
echo "[5/5] 检查动态库依赖..."
NEEDED=$(ldd "$LINUX_BIN" | grep "not found" | wc -l)
if [ "$NEEDED" -gt 0 ]; then
    echo "⚠️  发现 $NEEDED 个未找到的依赖（可能是系统库，正常）"
    ldd "$LINUX_BIN" | grep "not found" | head -5
else
    echo "✅ 所有依赖已满足"
fi

echo ""
echo "=========================================="
echo "  ✅ 构建成功！"
echo "=========================================="
echo "  产物位置：$LINUX_BIN"
echo "  SHA256: $(sha256sum "$LINUX_BIN" | cut -d' ' -f1)"
echo ""
echo "📦 下一步："
echo "  1. 测试运行：./$LINUX_BIN --help"
echo "  2. 上传到发布目录或 GitHub Releases"
echo "  3. 清理旧版本：ls -lt releases/pan4dex-*-linux | tail -n +4 | awk '{print \$NF}' | xargs rm"
echo ""
