#!/bin/bash
set -e

VERSION=${1:-$(python3 -c "import re; m=re.search(r'^VERSION\s*=\s*\"([^\"]+)\"', open('config/app_config.py', encoding='utf-8').read(), re.M); print(m.group(1))")}
RELEASES_DIR="$(pwd)/releases"
# 镜像可用 DOCKER_IMAGE 覆盖：改了 packaging/Dockerfile-linux 后想先拿新镜像做 A/B
# （不动旧镜像）时，构一个 `pan4dex-builder-linux:py311` 之类的临时 tag 再传进来。
DOCKER_IMAGE="${DOCKER_IMAGE:-pan4dex-builder-linux}"
CONTAINER_NAME="pan4dex-build-linux"

# 能直接访问 docker daemon 时不要 sudo（docker 在用户组里、或已在容器/root 环境下时，
# sudo 可能不存在也可能要密码 —— 要密码会在 set -e 里把构建挂住）
if docker info >/dev/null 2>&1; then
    DOCKER="docker"
else
    DOCKER="sudo docker"
fi

echo "=========================================="
echo "  Pan4dex Linux Docker 构建"
echo "  版本: ${VERSION}"
echo "=========================================="

# 确保 Docker 运行（daemon 已可访问就不碰 systemctl：在非 privileged 环境里
# `sudo systemctl` 本身可能失败，而它并不是必需的）
if $DOCKER info >/dev/null 2>&1; then
    echo "[1/6] Docker 已运行"
else
    echo "[1/6] 启动 Docker..."
    sudo systemctl start docker
    sleep 2
fi

# 构建镜像：仅当镜像不存在时构建（构建环境固定，每次重建无意义且浪费时间/网络）。
# 改了 packaging/Dockerfile-linux 后必须让它重建：要么先删 tag（$DOCKER rmi ...），
# 要么用一个新 tag 做 A/B（DOCKER_IMAGE=pan4dex-builder-linux:py311 bash scripts/build-linux-docker.sh）。
if $DOCKER image inspect ${DOCKER_IMAGE} >/dev/null 2>&1; then
    echo "[2/6] 使用已有镜像 ${DOCKER_IMAGE}（如需重建：$DOCKER rmi ${DOCKER_IMAGE}）"
else
    echo "[2/6] 构建 Docker 镜像 ${DOCKER_IMAGE}..."
    $DOCKER build --network=host -t ${DOCKER_IMAGE} -f packaging/Dockerfile-linux .
fi

# 清理旧容器
$DOCKER rm -f ${CONTAINER_NAME} 2>/dev/null || true

# 资源打包清单：只带仓库里真存在的目录。
# 为何不能写死：`resources/tools/` 整目录被 .gitignore 排除（二进制不入库），新克隆上
# 根本不存在，而 PyInstaller 6 对缺失的 --add-data 源是 `ERROR: Unable to find ...` +
# exit 1（不是警告）—— 写死四条会让 Linux 构建在干净检出上必失败。
# 缺工具不是错误：exiftool / 7z 在代码里都是「优先用系统安装，找不到才用应用内携带的」
# （core/media_metadata.py、core/archive_ops.py），本包没带就退到系统版本；但要把话说
# 在构建日志里，否则没人知道这个产物和老产物的能力面不一样。
# resources/themes 是早年遗留项（主题实际来自 qdarkstyle 包，代码不读该目录），已删。
# 格式：源目录|包内目标|人话名字（缺了会少什么能力）
ADD_SPECS=(
    "resources/icons|resources/icons|应用图标（缺了只剩任务栏默认图标）"
    "resources/tools/exiftool-linux|resources/tools/exiftool-linux|内置 ExifTool（拍摄日期元数据）"
    "resources/tools/7z|resources/tools/7z|内置 7zz（压缩/解压兜底）"
    "resources/tools/qt6-im-plugins|PyQt6/Qt6/plugins/platforminputcontexts|Qt6 输入法插件（不带则无法输入中文）"
)
DATA_ARGS=()
MISSING=()
for spec in "${ADD_SPECS[@]}"; do
    IFS='|' read -r src dst label <<< "$spec"
    if [ -d "$src" ]; then
        DATA_ARGS+=(--add-data "$src:$dst")
    elif [ "$src" = "resources/icons" ]; then
        echo "  ✗ $src 不存在：图标不在仓库里，源码树不完整" >&2
        exit 1
    else
        MISSING+=("$src（$label）")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "  ! 本包不含：${MISSING[*]}"
    echo "  ! 这些能力仍可用，但依赖目标系统自行安装（exiftool / p7zip / 系统输入法）"
fi

# 运行构建
echo "[3/6] 运行构建容器..."
$DOCKER run --name ${CONTAINER_NAME} \
    -v "$(pwd):/app" \
    -e "VERSION=${VERSION}" \
    -e "DATA_ARGS=${DATA_ARGS[*]}" \
    -e "PYBUILD_TIME=$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S')" \
    ${DOCKER_IMAGE} \
    bash -c "
        set -e
        cd /app
        
        # 版本号 + 编译时间写入 config/app_config.py：
        # - VERSION 必须用传入的版本号覆盖（构建现场源码可能滞后，否则
        #   打包进程序的版本号与产物名不一致）
        # - BUILD_TIME 由宿主按东八区算好传入（容器内 date 是 UTC，直接
        #   取会差 8 小时）
        sed -i \"s/^VERSION = \\\"[^\\\"]*\\\"/VERSION = \\\"\${VERSION}\\\"/\" config/app_config.py
        sed -i \"s/^BUILD_TIME = \\\"[^\\\"]*\\\"/BUILD_TIME = \\\"\${PYBUILD_TIME}\\\"/\" config/app_config.py
        
        # 构建：资源清单由宿主算好、经 DATA_ARGS 环境变量传进来（上面那段「目录存在才
        # 带」）。下面故意写 \$DATA_ARGS：这块整体是个双引号字符串，不转义就会被宿主
        # 先展开，而宿主那边 DATA_ARGS 是数组、不加花括号只得到第一个元素 --add-data，
        # 于是 main.py 被当成 --add-data 的值吞掉（PyInstaller 只报 “Wrong syntax,
        # should be --add-data=SOURCE:DEST”，不报缺 scriptname）—— 本仓已踩过一次。
        # 转义后由容器里的 shell 取环境变量，词分割才发生在正确的一侧；路径都是仓库内
        # 相对路径、无空格，依赖词分割是安全的。
        # 不带 --icon：Linux 下可执行文件本身不显示图标，任务栏图标是运行时
        # setWindowIcon 从 resources/icons 读的 —— 所以图标目录必须在，.ico 文件不必要。
        pyinstaller --onefile --windowed --name=pan4dex \
            \$DATA_ARGS \
            main.py
        
        # 移动到 releases
        mkdir -p /app/releases
        mv dist/pan4dex /app/releases/pan4dex-${VERSION}-linux
        chmod +x /app/releases/pan4dex-${VERSION}-linux
    "

echo "[4/6] 清理容器..."
$DOCKER rm -f ${CONTAINER_NAME} 2>/dev/null || true

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
