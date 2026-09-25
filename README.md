# Pan4dex 万格

**跨平台四窗格文件管理器** | Linux · Windows

> A cross-platform quad-pane file manager inspired by Q-Dir

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-lightgrey)

---

## 简介

Pan4dex 是一个跨平台四窗格文件管理器，功能对标 Windows 下的 Q-Dir。

**核心特性**：

* 🔲 2×2 四窗格布局（可切换为双窗格）
* 📁 跨窗格拖拽复制 / 移动文件
* 🔍 快速预览面板（文本 / 图片 / 文件信息）
* 📑 多标签页
* 🎨 深色 / 浅色主题 + 自定义主题
* ⚡ 可配置外部终端和文件关联
* 📦 单文件可执行，零依赖运行

---

## 截图

---

## 安装

发布产物在 [Releases](https://github.com/sfncat/Pan4dex/releases) 上，命名固定为两件事：
Linux 是 `pan4dex-<版本>-linux`（单文件，无扩展名），Windows 是 `pan4dex-<版本>.zip`（解压后运行其中的 `pan4dex.exe`）。

### Linux

```bash
# 取最新版本（也可以直接下 Releases 页面上的 pan4dex-<版本>-linux）
wget https://github.com/sfncat/Pan4dex/releases/latest/download/pan4dex-<版本>-linux -O pan4dex
chmod +x pan4dex
./pan4dex
```

### Windows

下载 `pan4dex-<版本>.zip`，解压到任意目录后运行 `pan4dex.exe`。

---

## 开发

### 环境要求

* Python 3.11+（仓库锁到 `.python-version` 指定的版本；Linux 构建镜像内是 3.11）
* PyQt6

### 安装依赖

```bash
# 推荐：uv（依赖与锁文件分别是 pyproject.toml / uv.lock）
uv sync --extra dev            # 运行时依赖 + pytest / pytest-qt
uv sync --extra build          # 运行时依赖 + PyInstaller

# 或手工 venv
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
pip install -r requirements.txt
pip install pytest pytest-qt pyinstaller   # 没有 requirements-dev.txt；测试依赖在 pyproject 的 .dev extra
```

### 运行

```bash
python main.py
```

### 测试

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ -q
```

无显示环境必须设离屏平台变量。**当前全量会挂住**（不是慢）：只要用两个文件路径构造
`FileCompareDialog`，它就立刻比较并在错误路径弹模态框，offscreen 下没人点 OK 就永不返回；踩中这一点
的用例在 `tests/test_new_features.py` 与 `tests/test_m5_tools.py` 两档里，**两个都要排除**才跑得完：

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ -q --ignore=tests/test_new_features.py --ignore=tests/test_m5_tools.py
```

详情见 [`docs/testing.md`](docs/testing.md) §5 与 [`docs/todo.md`](docs/todo.md) T4/T5。

### 打包

```bash
# Linux（Docker 构建，唯一入口；产物 releases/pan4dex-<版本>-linux）
bash scripts/build-linux-docker.sh

# Windows（本机 PyInstaller；产物 releases/pan4dex-<版本>/ + 同名 .zip）
python scripts/build_windows.py
```

**详细构建指南**: [`docs/BUILD-GUIDE.md`](docs/BUILD-GUIDE.md)（含 230 Kali Docker 构建详解、后台构建、验证清单）

两条命令的版本号都缺省取自 `config/app_config.py`。`pyinstaller packaging/pan4dex.spec` 是手动/降级路线，只在 Docker 不可用时应急（不带输入法插件与内置 exiftool/7zz），差异见 `docs/development-guide.md` §5.2。

---

## 📚 文档导航

| 文档 | 说明 |
|------|------|
| [`AGENT.md`](AGENT.md) | **AI 与新会话的入口索引**：项目是什么、代码怎么串、铁律、去哪读 |
| [`QUICKSTART.md`](QUICKSTART.md) | **快速开始**（一键构建、常用命令） |
| [`docs/BUILD-GUIDE.md`](docs/BUILD-GUIDE.md) | **构建指南**（Linux/Windows 构建、230 Docker 详解）← 构建的当前真相 |
| [`docs/architecture.md`](docs/architecture.md) | 模块职责、数据流、关键设计决策 |
| [`docs/development-guide.md`](docs/development-guide.md) | 开发指南（环境、加模块、代码规范、文档维护） |
| [`docs/testing.md`](docs/testing.md) | 测试策略与常用命令 |
| [`docs/feature-checklist.md`](docs/feature-checklist.md) | 功能清单与实现状态（状态表） |
| [`docs/todo.md`](docs/todo.md) | **待办唯一正文**：还剩什么、卡在哪儿、怎样算销账 |
| [`docs/linux-gap.md`](docs/linux-gap.md) | Linux 能力对照：哪些没做、哪些只是没验证 |
| [`docs/gotchas.md`](docs/gotchas.md) | 踩坑记录 #1–#56（为什么不能那么写） |
| [`docs/changelog.md`](docs/changelog.md) | 更新日志 |
| [`docs/unsolved-issues.md`](docs/unsolved-issues.md) | 还挂着的问题 |

---

## 快捷键

| 快捷键            | 功能          |
| ------------------ | ------------- |
| `Ctrl+T`           | 新建标签页     |
| `Ctrl+W`           | 关闭标签页     |
| `Ctrl+Tab`         | 切换标签页     |
| `Ctrl+L`           | 聚焦路径栏     |
| `Ctrl+D`           | 切换深色 / 浅色主题 |
| `Ctrl+4`           | 四窗格模式     |
| `Ctrl+2`           | 双窗格模式     |
| `F3`               | 切换预览面板    |
| `F5`               | 刷新           |
| `F2`               | 重命名         |
| `Delete`           | 安全删除       |
| `Shift+Delete`     | 永久删除       |

---

## 技术栈

* [Python 3.11+](https://www.python.org/)（依赖：`pyproject.toml` + `uv.lock`）
* [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — 界面
* [Pillow](https://python-pillow.org/) + [pillow-heif](https://pillow-heif.readthedocs.io/) — 图片与 HEIC 预览
* [QDarkStyle](https://github.com/QDarkStyleSheet/qdarkstyle) — 深色主题
* [send2trash](https://github.com/Sharachchandra/send2trash) — 安全删除（网络位置一律永久删除）
* [pyte](https://pyte.readthedocs.io/) + [pywinpty](https://github.com/pywinpty/pywinpty)（Windows）— 内嵌终端
* [PyInstaller](https://pyinstaller.org/) — 单文件打包

## 里程碑

M1–M5（核心框架 / 文件操作 / 标签页与预览 / 主题与收藏夹 / 打包发布）均已完成，
当前处于「对齐 Windows 资源管理器与 Q-Dir 的行为细节 + Linux 真机验收」阶段。
具体做没做看 [`docs/feature-checklist.md`](docs/feature-checklist.md)，
Linux 侧差距看 [`docs/linux-gap.md`](docs/linux-gap.md)。

---

## 贡献

欢迎提交 Issue 和 PR。

---

## 许可证

[MIT](LICENSE) © 2026 sfncat

---

## 致谢

* [Q-Dir](https://q-dir.com/) — 灵感来源
