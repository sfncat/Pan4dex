# Pan4dex 万格 — 开发指南

## 1. 开发环境搭建

### 1.1 系统要求
- Ubuntu 22.04+ / Kali Linux
- Python 3.10+
- Qt 6 运行时（开发时由 PyQt6 提供）

### 1.2 安装依赖

```bash
# 克隆项目
cd /home/kali/workspace/pan4dex

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装运行时依赖
pip install -r requirements.txt

# 安装开发依赖（测试、打包）
pip install -r requirements-dev.txt
```

### 1.3 requirements.txt

```
PyQt6>=6.6.0
send2trash>=1.8.0
Pillow>=10.0.0
```

### 1.4 requirements-dev.txt

```
pytest>=7.4.0
pytest-qt>=4.2.0
pytest-cov>=4.1.0
pytest-xdist>=3.3.0
PyInstaller>=6.0.0
ruff>=0.1.0
mypy>=1.5.0
```

---

## 2. 开发流程

### 2.1 TDD 开发流程

1. **编写测试**：在 `tests/unit/` 或 `tests/integration/` 中编写测试
2. **运行测试确认失败**：`pytest tests/ -v`
3. **编写实现**：在 `core/` 或 `widgets/` 中编写代码
4. **运行测试确认通过**
5. **重构**：优化代码结构
6. **覆盖率检查**：`pytest --cov --cov-report=term-missing`

### 2.2 功能开发顺序

```
M1: 核心框架 → M2: 文件操作 → M3: 标签页+预览 → M4: 主题+收藏+筛选 → M5: 打磨+打包
```

### 2.3 代码提交前检查

```bash
# 1. 运行全部测试
pytest tests/ -v --qt-api=pyqt6

# 2. 代码格式检查
ruff check core/ widgets/ config/

# 3. 类型检查
mypy core/ widgets/ config/

# 4. 覆盖率报告
pytest tests/ --cov --cov-report=term-missing
```

---

## 3. 模块开发指南

### 3.1 新增核心模块

1. 在 `core/` 下创建 `new_module.py`
2. 在 `tests/unit/` 下创建 `test_new_module.py`
3. 在 `docs/implementation.md` 中添加实现设计说明
4. 在 `docs/feature-checklist.md` 中更新状态

### 3.2 新增 UI 组件

1. 在 `widgets/` 下创建 `new_widget.py`
2. 在 `tests/integration/` 下创建 `test_new_widget.py`
3. 使用 `pytest-qt` 的 `qtbot` 进行组件测试

### 3.3 新增配置项

1. 在 `config/settings.py` 中添加 get/set 方法
2. 在 `tests/unit/test_settings.py` 中添加测试
3. 在设置界面中添加对应 UI（如有）

---

## 4. 测试指南

### 4.1 单元测试

```python
# tests/unit/test_file_operations.py
import pytest
from core.file_operations import FileOperations

class TestFileOperations:
    def test_copy_single_file(self, tmp_dir):
        """测试复制单个文件"""
        src = tmp_dir / "source.txt"
        src.write_text("hello")
        dst = tmp_dir / "dest.txt"
        
        ops = FileOperations()
        result = ops.copy(str(src), str(dst))
        
        assert result.success
        assert dst.read_text() == "hello"
    
    def test_copy_to_nonexistent_directory(self, tmp_dir):
        """测试复制到不存在的目录"""
        src = tmp_dir / "source.txt"
        src.write_text("hello")
        dst = tmp_dir / "nonexistent" / "dest.txt"
        
        ops = FileOperations()
        result = ops.copy(str(src), str(dst))
        
        assert not result.success
        assert "No such file" in result.error
```

### 4.2 集成测试

```python
# tests/integration/test_pane.py
import pytest
from widgets.pane import Pane

class TestPane:
    def test_navigate_to_directory(self, qtbot, tmp_path):
        """测试导航到目录"""
        pane = Pane(pane_id="test")
        qtbot.addWidget(pane)
        
        # 创建测试目录
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("test")
        
        # 导航
        pane.navigate_to(str(test_dir))
        
        # 验证
        assert pane.current_path == str(test_dir)
        assert pane.model.rowCount(pane.tree_view.rootIndex()) > 0
```

### 4.3 运行测试

```bash
# 全部测试
pytest tests/ -v --qt-api=pyqt6

# 仅单元测试
pytest tests/unit/ -v

# 仅集成测试
pytest tests/integration/ -v --qt-api=pyqt6

# 覆盖率
pytest tests/ --cov=core --cov=widgets --cov=config --cov-report=html --cov-report=term-missing

# 并行测试
pytest tests/ -n auto
```

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
| `docs/design.md` | 功能需求变更时 |
| `docs/architecture.md` | 架构变更时 |
| `docs/implementation.md` | 实现细节变更时 |
| `docs/testing.md` | 测试策略变更时 |
| `docs/feature-checklist.md` | 功能实现状态变更时 |
| `AGENT.md` | 项目结构/约定变更时 |

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
