# Pan4dex 万格 — 测试策略

## 1. 测试哲学

- **可回归**：每次代码变更自动运行测试套件，防止回归
- **可测试**：业务逻辑与 UI 解耦，便于单元测试
- **覆盖率目标**：核心模块 ≥ 85%，UI 模块 ≥ 60%

## 2. 测试层级

### 2.1 单元测试（unit/）

| 测试对象 | 工具 | Mock 策略 |
|---|---|---|
| FileOperations | pytest | Mock shutil/os 调用，不碰真实文件系统 |
| FileModel | pytest | Mock QFileSystemModel |
| DragDrop | pytest | Mock QMimeData/QDragEvent |
| Terminal | pytest | Mock subprocess |
| Settings | pytest | 使用临时 QSettings |
| FileAssociations | pytest | 使用临时 JSON 文件 |
| ThemeManager | pytest | 使用临时主题文件 |

### 2.2 集成测试（integration/）

| 测试对象 | 工具 | 说明 |
|---|---|---|
| Pane 组件 | pytest-qt | 测试窗格导航、路径跳转、文件选择 |
| MainWindow | pytest-qt | 测试标签页、布局切换 |
| 导航流程 | pytest-qt | 测试完整的用户操作流程 |

### 2.3 E2E 测试（e2e/，可选）

| 测试对象 | 工具 | 说明 |
|---|---|---|
| 完整用户流程 | pytest-qt | 模拟真实用户操作序列 |

## 3. 测试夹具（Fixtures）

```python
# conftest.py 核心 fixtures

@pytest.fixture
def tmp_dir(tmp_path):
    """提供临时目录结构用于文件操作测试"""
    # 创建: file1.txt, file2.txt, subdir/, subdir/file3.txt
    ...

@pytest.fixture
def mock_file_system():
    """Mock 文件系统操作，不触碰真实磁盘"""
    ...

@pytest.fixture
def qt_app(qapp):
    """提供 QApplication 实例（pytest-qt 内置）"""
    ...

@pytest.fixture
def pane(qtbot):
    """创建并返回一个 Pane 实例"""
    ...
```

## 4. 关键测试场景

### 4.1 file_operations

| 场景 | 验证点 |
|---|---|
| 复制单个文件 | 目标文件存在，内容一致，原文件不变 |
| 复制目录（递归） | 目录结构完整，所有文件一致 |
| 覆盖已存在文件 | 用户确认后覆盖，内容更新 |
| 复制到无权限目录 | 抛出 PermissionError，不崩溃 |
| 复制过程中取消 | 操作中止，目标文件可能部分写入 |
| 移动文件 | 原位置文件消失，新位置文件存在 |
| 安全删除 | 文件进入回收站（send2trash） |
| 永久删除 | 文件彻底删除 |

### 4.2 file_model

| 场景 | 验证点 |
|---|---|
| 路径变更后刷新 | 文件列表正确更新 |
| 排序（名称/大小/日期） | 顺序正确 |
| 过滤（扩展名） | 只显示匹配文件 |
| 大目录（>10k 文件） | 不阻塞，可取消 |

### 4.3 drag_drop

| 场景 | 验证点 |
|---|---|
| 窗格内拖拽 | 触发移动操作 |
| 跨窗格拖拽 | 触发复制操作 |
| Shift+拖拽 | 强制移动 |
| Ctrl+拖拽 | 强制复制 |
| 拖拽取消 | 无操作发生 |

### 4.4 terminal

| 场景 | 验证点 |
|---|---|
| 检测到 gnome-terminal | 使用 gnome-terminal |
| 无已知终端 | 回退到 xterm |
| 用户自定义终端 | 使用用户配置 |
| 路径包含空格 | 正确转义 |

### 4.5 settings

| 场景 | 验证点 |
|---|---|
| 保存/读取窗口位置 | 重启后恢复 |
| 配置文件损坏 | 回退到默认值 |
| 并发写入 | 不崩溃，最后一次写入生效 |

### 4.6 file_associations

| 场景 | 验证点 |
|---|---|
| 已配置类型 | 使用指定应用打开 |
| 未配置类型 | 使用 xdg-open |
| 应用不存在 | 回退到 xdg-open |
| 配置热加载 | 修改配置后立即生效 |

### 4.7 theme_manager

| 场景 | 验证点 |
|---|---|
| 切换内置主题 | UI 颜色更新 |
| 加载自定义主题 | 应用新颜色 |
| 主题文件损坏 | 保持当前主题，不崩溃 |
| 自定义主题接口 | 预留接口可用 |

## 5. 测试命令

```bash
# 运行全部测试
pytest tests/ -v

# 运行单元测试
pytest tests/unit/ -v

# 运行集成测试
pytest tests/integration/ -v --qt-api=pyqt6

# 生成覆盖率报告
pytest tests/ --cov=core --cov=widgets --cov=config --cov-report=html --cov-report=term-missing

# 运行特定测试
pytest tests/unit/test_file_operations.py::test_copy_single_file -v
```

## 6. 持续集成（可选）

```yaml
# .github/workflows/test.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements-dev.txt
      - run: xvfb-run pytest tests/ --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

## 7. 测试数据管理

- `tests/fixtures/sample_files/`：测试用文件（小文本、图片等）
- `tests/fixtures/mock_data/`：模拟的配置文件、主题文件
- 测试运行时创建的临时文件使用 `tmp_path`（pytest 内置），测试后自动清理
