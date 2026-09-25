# Pan4dex 万格 — 快速开始

## 🚀 一键构建

### Linux 版本（推荐所有环境使用 Docker）
```bash
bash scripts/build-linux-docker.sh     # 版本号缺省取 config/app_config.py 的 VERSION
```
产物：`releases/pan4dex-<版本>-linux`

### Windows 版本（本机构建）
```powershell
python scripts/build_windows.py
```
产物：`releases/pan4dex-<版本>/` + `releases/pan4dex-<版本>.zip`

---

## 📚 完整文档

| 文档 | 说明 |
|------|------|
| [`AGENT.md`](AGENT.md) | 入口索引：代码怎么串、铁律、去哪读 |
| [`docs/BUILD-GUIDE.md`](docs/BUILD-GUIDE.md) | **详细构建指南**（含 230 Docker 构建） |
| [`docs/architecture.md`](docs/architecture.md) | 模块职责与关键设计决策 |
| [`docs/development-guide.md`](docs/development-guide.md) | 开发指南（环境、加模块、文档维护） |
| [`docs/feature-checklist.md`](docs/feature-checklist.md) | 功能清单与实现状态（状态表） |
| [`docs/todo.md`](docs/todo.md) | **待办清单**：还剩什么、卡在哪儿、销账判据 |
| [`docs/linux-gap.md`](docs/linux-gap.md) | Linux 侧差距与真机验收清单 |
| [`README.md`](README.md) | 项目简介和安装说明 |

---

## 🔧 常用命令

```bash
# 跑起来
python main.py

# 运行测试（无显示的环境用离屏平台）
QT_QPA_PLATFORM=offscreen pytest tests/ -q --ignore=tests/test_new_features.py --ignore=tests/test_m5_tools.py
#   Windows PowerShell 先执行：$env:QT_QPA_PLATFORM='offscreen'
#   ⚠️ 不加那两个 --ignore 会挂住：两档里有 9 处「用两个文件路径构造 FileCompareDialog」，
#      它在 offscreen 下弹模态框永不返回。只排一个会在 50% 处卡住。原因见 docs/testing.md §5

# 清理构建缓存
rm -rf build/ dist/ build_onefile/ dist_onefile/ .pytest_cache
```

> 测试与打包依赖都在 `pyproject.toml` 的 optional-dependencies 里，装法：
> `uv sync --extra dev`（pytest / pytest-qt）、`uv sync --extra build`（PyInstaller）。
> 仓库里**没有** `requirements-dev.txt`。
>
> 关于静态检查：仓库里**没有 ruff / mypy 的配置文件，也没有声明这两个依赖**，早前文档里的
> `ruff check ...` / `mypy ...` 照抄必然失败 —— 要用就先自己加依赖与配置。

---

## 🎯 还堵在环境上的真机验收项

只有下面三条做不了；其余状态一律以 [`docs/feature-checklist.md`](docs/feature-checklist.md)
与 [`docs/linux-gap.md`](docs/linux-gap.md) §5.2 为准（本表不维护状态，只登记阻塞原因）：

| 项 | 内容 | 为什么没做 |
|---|---|---|
| L4 | 从 Nautilus/Dolphin 跨程序拖拽 | 需要真鼠标轨迹，`xdotool` 能做但极不稳 |
| L11 | 真实桌面里的打字交互 | 需要有人在现场的桌面环境 |
| L12 | Wayland 原生支持 | 需要 Wayland 环境 |
