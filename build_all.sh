#!/bin/bash
# Pan4dex 双平台构建（薄封装：真正的构建逻辑在 scripts/build_all.py）
# 用法：./build_all.sh [版本号] [-U] [--replace] [--windows-only|--linux-only]
set -e
cd "$(dirname "$0")"

pick_python() {
    for candidate in .venv/bin/python .venv/Scripts/python.exe python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && \
           "$candidate" -c "pass" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

if ! PY=$(pick_python); then
    echo "✗ 找不到可用的 Python（建议先 uv sync 建 .venv）" >&2
    exit 1
fi

exec "$PY" scripts/build_all.py "$@"
