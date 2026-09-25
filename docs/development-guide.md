# Pan4dex 万格 — 开发指南

## 1. 开发环境搭建

### 1.1 系统要求
- Ubuntu 22.04+ / Kali Linux，或 Windows 10/11
- Python 3.11+（`pyproject.toml` 的 `requires-python`；开发机的 `.python-version` 是 3.13，
  Linux 构建镜像内是 3.11）
- Qt 6 运行时（开发时由 PyQt6 提供）
- 依赖与锁文件：`pyproject.toml` + `uv.lock`（用 uv 就 `uv sync`；`requirements.txt` 只是
  运行时依赖的另一份抄本，两边要保持一致）

### 1.2 安装依赖

```bash
# 克隆项目
cd /c/workspace/Pan4dex        # Linux 上按自己的路径

# 推荐：uv（依赖与锁的真相在 pyproject.toml / uv.lock）
uv sync --extra dev            # 运行时依赖 + pytest / pytest-qt
uv sync --extra build          # 再加 PyInstaller（打产物时）

# 不用 uv 的等价做法
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-qt pyinstaller
```

### 1.3 requirements.txt（运行时，与 `pyproject.toml` 的 dependencies 一致）

```
PyQt6>=6.6.0
send2trash>=1.8.0
Pillow>=10.0.0
pillow-heif>=0.16.0      # HEIC/HEIF 预览
qdarkstyle>=3.2.0        # 深色主题
pyte>=0.8.0              # 内嵌终端的终端仿真
pywinpty>=3.0.0; sys_platform == "win32"   # 内嵌终端的 PTY
```

### 1.4 开发依赖的现状（2026-09-23 更新）

* 测试：`pytest` + `pytest-qt` —— 已写进 `pyproject.toml` 的 `[project.optional-dependencies].dev`，
  装法 `uv sync --extra dev`。**本轮之前**它是「实际在用但清单里没有」：`uv sync` 会把 `.venv` 里
  没声明的包同步掉，所以「本机装过」不构成安装方式。
* 打包：`pyinstaller` —— 声明在 `pyproject.toml` 的 `[project.optional-dependencies].build`，
  `uv sync --extra build` 能装上。
* 顺带发现：跑 `uv lock` 之前，`uv.lock` 里本包版本还钉在 **0.9.619**（源码早已是 1.9.023），
  锁与 `pyproject.toml` 脱钩了很久 —— 改了依赖不重跑 `uv lock`，`uv sync` 就会静默按旧锁走。
  改完依赖顺手 `uv lock --check`。
* 静态检查：`ruff` / `mypy` —— **仓库里既没有配置文件也没有依赖**，旧文档里那两条命令是历史
  设想，照抄必失败。要引入就先加 `ruff.toml` / `[tool.mypy]` 并补依赖。
* 覆盖率 / 并行：`pytest-cov` / `pytest-xdist` 同样未声明，用之前先装。

---

## 2. 开发流程

### 2.1 TDD 开发流程

1. **编写测试**：在 `tests/` 下按模块建 `test_<模块>.py`（`tests/` 是扁平一层）
2. **运行测试确认失败**：先单跑新加的那条（`pytest tests/test_xxx.py::test_yyy -q`），确认它
   确实是因为缺陷而红
3. **编写实现**：在 `core/` 或 `widgets/` 中编写代码
4. **运行测试确认通过**：还是单跑，然后补一轮**相关模块**的用例
5. **重构**：优化代码结构
6. **提交前跑全量**：`QT_QPA_PLATFORM=offscreen pytest tests/ -q`（当前需把挂住的两档一起
   `--ignore` 掉，见 §2.3）。**别拿第 4 步的单跑当「测试通过」** ——
   gotchas 第 56 条那次回归就是因为只跑了针对性文件

覆盖率检查这一步暂时没有：`pytest-cov` 未声明（§1.4）。

### 2.2 功能开发顺序

M1–M5 是项目早期的排期口径，**已经全部走完**（四窗格核心、文件操作、标签页+预览、主题+收藏+筛选、
打包发布）。现在按「版本 + 清单」排：状态看 `docs/feature-checklist.md`、**还剩什么看
`docs/todo.md`**（待办唯一正文），Linux 那半边看 `docs/linux-gap.md`。

### 2.3 代码提交前检查

```bash
# 1. 先只跑受本次改动影响的文件（反馈快）
QT_QPA_PLATFORM=offscreen pytest tests/test_dir_model.py -q

# 2. 再补一轮全量 —— 顺序别反，只跑第 1 步就是 gotchas 第 56 条那次回归的成因
QT_QPA_PLATFORM=offscreen pytest tests/ -q
```

> **第 2 步当前跑不完**：`tests/test_new_features.py` 与 `tests/test_m5_tools.py` 里共 9 处「用两个文件
> 路径构造 `FileCompareDialog`」，会弹模态框把套件挂死（只排除前者会在 50% 处卡在后者上）。当前能跑到
> 汇总行的命令，以及销账条件，都在 `docs/testing.md` §5 与 `docs/todo.md` T4/T5。

```bash
# 3. 静态检查：仓库里既没有 ruff/mypy 配置也没有这两个依赖（见 §1.4）。
#    想引入就单独开一条 chore 提交，把配置与依赖一起补上，别在提交说明里写「已过 ruff 检查」——
#    本机根本没装。历史上这条命令是设想，不是现状。
```

**没有覆盖率这一步**：`pytest-cov` 同样未声明，`--cov` 参数会直接报错。

---

## 3. 模块开发指南

### 3.1 新增核心模块

1. 在 `core/` 下创建 `new_module.py`
2. 在 `tests/` 下创建 `test_<模块>.py`（`tests/` 是扁平一层，没有 `unit/` / `integration/` 子目录）
3. 在 `docs/architecture.md` §2 补一行模块职责；踩过坑的写进 `docs/gotchas.md`
4. 在 `docs/feature-checklist.md` 中更新状态；没做完的部分登记到 `docs/todo.md`（编号续 `T<n>`）

### 3.2 新增 UI 组件

1. 在 `widgets/` 下创建 `new_widget.py`
2. 在 `tests/` 下创建 `test_<组件>.py`，用 `pytest-qt` 的 `qtbot` 测组件
   （离屏跑：`QT_QPA_PLATFORM=offscreen`）

### 3.3 新增配置项

没有统一的设置封装层，按数据性质二选一：

1. **结构化用户数据**（JSON 文件）：在 `config/` 下新建 store，配置目录向
   `config/paths.py:default_config_dir()` 委托，别自己再算一份路径
2. **界面/窗口偏好**：宿主直接 `QSettings(ORG_NAME, APP_NAME)` 读写自己的键（见
   `core/main_window.py`、`widgets/settings_dialog.py`）
3. 需要在设置界面里可改的，再往 `widgets/settings_dialog.py` 加对应 UI

---

## 4. 测试指南

### 4.1 不碰 UI 的用例（模型层、判据、纯函数）

```python
# tests/test_file_operations.py
from core.file_operations import FileOperations

class TestFileOperations:
    def test_copy_single_file(self, tmp_dir):
        src_dir = tmp_dir / "src"
        src_dir.mkdir()
        (src_dir / "source.txt").write_text("hello")
        dst_dir = tmp_dir / "dst"
        dst_dir.mkdir()

        result = FileOperations().copy([str(src_dir / "source.txt")], str(dst_dir))

        assert result.success
        assert (dst_dir / "source.txt").read_text() == "hello"

    def test_copy_to_nonexistent_directory(self, tmp_dir):
        src = tmp_dir / "source.txt"
        src.write_text("hello")
        result = FileOperations().copy([str(src)], str(tmp_dir / "nonexistent"))
        assert not result.success
```

`copy` / `move` 的签名是 `(sources: list[str], destination: str)`，`delete` 是
`(paths: list[str], safe: bool = True)`，都返回 `FileOperationResult`（`success` / `error` / …）。
旧文档里 `ops.copy(src, dst)` 那种「单个源 → 目标文件」的写法在代码里不存在。

### 4.2 需要控件的用例

```python
# tests/test_pane.py（节选）
from core.pane import Pane          # 注意：Pane 在 core/，不在 widgets/

def test_navigate_to_directory(qtbot, tmp_path):
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("test")

    pane = Pane("t_nav", start_path=str(test_dir))   # 构造签名：(pane_id, parent, start_path)
    qtbot.addWidget(pane)

    tv = pane.tree_view                              # 视图上挂的是 PaneSortProxyModel
    qtbot.waitUntil(lambda: tv.model().rowCount(tv.rootIndex()) == 1, timeout=5000)
    assert pane.current_path == str(test_dir)
```

写 GUI 用例前先读 gotchas 第 41 条（离屏测 Qt 的四个坑）与第 32 条（合成按键的修饰键态会
漏给下一个用例）；`tests/conftest.py` 只给了 `qapp`（session 级）、`tmp_dir`、
`_reap_top_level_widgets`（autouse，防状态泄漏）和 `qt_exceptions` 四个夹具。

### 4.3 运行测试

```bash
# 全部（无显示的环境必须离屏）—— 少一个 --ignore 就会挂住，见 §2.3 与 testing.md §5
QT_QPA_PLATFORM=offscreen pytest tests/ -q --ignore=tests/test_new_features.py --ignore=tests/test_m5_tools.py

# 按文件 / 按用例
pytest tests/test_dir_model.py -v
pytest tests/test_dir_model.py::test_refresh_empty_dir_after_new_file_visible -v
```

覆盖率（`--cov`）与并行（`-n auto`）这两条**现在都用不了**：`pytest-cov` / `pytest-xdist` 没写进任何
依赖清单（§1.4），装了才有；覆盖率策略本身见 `docs/testing.md` §1。

---

## 5. 打包指南

### 5.1 正式构建入口

| 平台 | 命令 | 产物 |
|---|---|---|
| Linux | `bash scripts/build-linux-docker.sh [版本号]` | `releases/pan4dex-<版本>-linux`（onefile） |
| Windows | `python scripts/build_windows.py [版本号]` | `releases/pan4dex-<版本>/` + 同名 `.zip` |

版本号缺省从 `config/app_config.py` 的 `VERSION` 读（构建时会连 `BUILD_TIME` 一起写回源码，
构建完由发布提交还原）。Linux 走 Docker（镜像 `packaging/Dockerfile-linux`，
`python:3.11-bullseye` / glibc 2.31）是为了不把构建机的新 glibc 烧进产物，细节见
`docker/README.md`。

### 5.2 手动 / 降级路线：`packaging/pan4dex.spec`

```bash
pyinstaller packaging/pan4dex.spec        # 输出在 dist/pan4dex
```

跑得通，但它只是一份“把 `resources/` 整目录 + 一批 hiddenimports 收进去”的最小配置，
与正式入口的差集：不带 Qt6 输入法插件、不带 `resources/tools/` 下的内置 ExifTool 与 7zz
（那个目录本就不入库，见 `.gitignore`），也不做 Windows 侧 imageformats / winpty 的处理。
用它出包 = 一个能力面更小的包，只在 Docker 不可用时应急。

关键片段（与文件实际内容一致）：

```python
# packaging/pan4dex.spec
a = Analysis(
    ['../main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../resources', 'resources'),
    ],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
                   'PyQt6.QtNetwork', 'qdarkstyle', 'qdarkstyle.dark',
                   'qdarkstyle.light'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# 随后有一串 a.binaries 过滤：排掉 libstdc++/libxcb/libglib 等系统库，让产物用目标机的版本
```

### 5.3 测试打包结果

```bash
# 运行打包后的可执行文件
./dist/pan4dex

# 检查依赖
ldd dist/pan4dex | grep "not found"
```

---

## 6. 代码风格指南

### 6.1 导入顺序

```python
# 1. 标准库
import os
import sys
from pathlib import Path

# 2. 第三方库
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QTreeView

# 3. 本项目模块
from core.file_operations import FileOperations
from config.settings import Settings
```

### 6.2 命名约定

| 类型 | 约定 | 示例 |
|---|---|---|
| 类名 | 大驼峰 | `FileOperations` |
| 函数/方法 | 小写下划线 | `copy_files` |
| 常量 | 全大写下划线 | `MAX_RETRIES` |
| 私有方法 | 单下划线前缀 | `_internal_method` |
| 信号 | 过去时态 | `fileCopied` |

### 6.3 类型注解

```python
def copy_files(
    sources: list[str],
    destination: str,
    progress_callback: Callable[[int, str], None] | None = None
) -> FileOperationResult:
    """复制文件到目标目录"""
    ...
```

### 6.4 Docstring 风格

```python
def copy_files(sources: list[str], destination: str) -> FileOperationResult:
    """复制文件到目标目录。
    
    Args:
        sources: 源文件路径列表。
        destination: 目标目录路径。
    
    Returns:
        FileOperationResult: 操作结果，包含成功/失败状态和错误信息。
    
    Raises:
        PermissionError: 当没有权限写入目标目录时。
        FileNotFoundError: 当源文件不存在时。
    """
    ...
```

---

## 7. 调试技巧

### 7.1 使用 pdb 调试

```python
import breakpoint

def problematic_function():
    breakpoint()  # 程序会在这里暂停
    # 检查变量，单步执行等
```

### 7.2 使用 debugpy 远程调试

```python
import debugpy
debugpy.listen(("127.0.0.1", 5678))
debugpy.wait_for_client()  # 等待 VS Code 连接
```

### 7.3 常见问题排查

| 问题 | 排查方法 |
|---|---|
| Qt 组件不显示 | 检查是否在创建了 QApplication 之前创建组件 |
| 信号槽不生效 | 检查信号是否已连接，槽函数签名是否匹配 |
| 测试中 GUI 不响应 | 使用 `qtbot.wait()` 或 `qtbot.waitSignal()` |
| 打包后资源找不到 | 使用 `sys._MEIPASS` 获取打包路径 |

---

## 8. 文档维护

### 8.1 需要维护的文档

| 文档 | 何时更新 |
|---|---|
| `AGENT.md` | 只改导航与铁律条目，**不往里复制正文** |
| `docs/architecture.md` | 模块职责、数据流、关键设计决策变更时 |
| `docs/gotchas.md` | 每踩过一个会复发的坑，当场记一条（编号连续，别插空号） |
| `docs/changelog.md` | 每次发布新增一节 |
| `docs/feature-checklist.md` | 功能实现状态变更时（改了状态要连正文一起改） |
| `docs/todo.md` | 待办的唯一正文：登记新条目、销账时状态改 ✅ 但**保留整行**（它是验收记录） |
| `docs/linux-gap.md` | Linux 侧缺口关闭或真机验收有结论时 |
| `docs/BUILD-GUIDE.md` | 构建/发布链路变更时（构建的当前真相） |
| `docs/testing.md` | 测试策略变更时 |

### 8.2 更新记录格式

```markdown
## 更新记录

| 日期 | 更新内容 | 更新人 |
|---|---|---|
| 2026-08-26 | 初始版本 | - |
| 2026-08-27 | 完成核心框架 M1 | - |
```

---

**文档版本**：v1.0  
**最后更新**：2026-08-26
