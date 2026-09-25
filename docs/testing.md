# Pan4dex 万格 — 测试策略

## 1. 测试哲学

- **可回归**：改动前先写一条能复现问题的用例（修复前应失败、修复后转绿），这是本仓每个
  缺陷类提交的固定动作，比覆盖率数字有用。
- **不 mock 被测行为**：文件操作用 `tmp_path` 下**真实**的目录与文件，模型用例真的走
  `os.scandir` 与真实 Qt 模型信号。历史上 mock 掉文件系统让迁移/删除类缺陷整批漏过。
- **覆盖率目前没有度量**：仓库无 CI、无 `[tool.coverage]` 配置，「核心 ≥ 85% / UI ≥ 60%」
  是早期设想，没有任何一次实测支撑。要恢复先装 `pytest-cov` 并加配置，别按这两个数字自评。

## 2. 实际存在的三层

### 2.1 纯逻辑用例（不建任何 Qt 控件）

| 被测对象 | 所在文件 | 手法 |
|---|---|---|
| `FileOperations`（复制/移动/删除） | `tests/test_m2_file_operations.py`、`test_file_op_runner.py` | `tmp_path` 真实文件；断 `FileOperationResult` |
| `DirStoreModel` 枚举/缓存/取消 | `tests/test_dir_model.py` | 真 `os.scandir` + 真线程池，`dir_pool().waitForDone()` 等收敛 |
| 慢位置判据 `mounts.py` | `tests/test_mounts.py` | 喂挂载表文本，纯函数三段（`parse_mount_table` / `longest_matching_mount` / `posix_is_remote`）在 Windows 主机上就能测满 |
| 筛选编译 `compile_filter()` | `tests/test_filter_bar.py` | 只测编译出的谓词，不起视图 |
| 生命周期 `call_later` / `exec_and_drain` | `tests/test_lifecycle.py` | 真实 `QCoreApplication`，测销毁时序 |
| 收藏夹树 `BookmarkStore` | `tests/test_bookmarks.py` | 注入临时目录做 JSON 落盘（gotchas 第 39 条：测持久化组件必须注入临时目录） |
| 文件关联 / 已保存搜索 | `tests/test_saved_search.py`、`test_search_results.py`、`test_open_with.py` | 临时目录注入做 JSON 落盘（gotchas 第 39 条）；`test_open_with.py` 在 Windows 上真读注册表 |
| 崩溃日志落点 | `tests/test_crash_log_path.py` | 只读安装目录时要能退到用户级落点（gotchas 第 45 条） |
| 各工具对话框（比较/预览/操作） | `tests/test_new_features.py`、`tests/test_m5_tools.py` | ⚠️ **这两档当前会把整场测试挂住**：合计 9 处「用两个文件路径构造 `FileCompareDialog`」即撞模态错误框，见 §5 顶部的当前状态说明与 `docs/todo.md` T4/T5 |

（`DragDrop` / `Terminal` / `Settings` / `FileModel` 这些**模块在本仓不存在**，旧表里那几行
是按设想写的。拖放判据实际住在 `file_operations.decide_drop_action()`，终端住在
`widgets/terminal_panel.py`，配置住在 `config/` 各 store + 直接 `QSettings`。）

### 2.2 控件用例（pytest-qt + 离屏）

| 被测对象 | 所在文件 | 说明 |
|---|---|---|
| `Pane` + `DirStoreModel` 接线 | `test_pane_dir_store.py`、`test_pane_target.py` | 等后台回填用 `qtbot.waitUntil`，别 `QTest.qWait` 硬等 |
| 快捷键落点与焦点 | `test_shortcut_focus_scope.py`、`test_nav_shortcuts.py` | 合成按键的修饰键态会漏给下一个用例（gotchas 第 32 条） |
| 拖放默认动作 | `test_drop_action.py` | 手工构造 `QDropEvent` 的三个坑见 gotchas 第 42 条 |
| 打开方式 / 预览 / 主题 | `test_open_with.py`、`test_m3_preview.py`、`test_m4_theme.py` | offscreen 下的四个反复坑见 gotchas 第 41 条 |
| 退出与崩溃防护 | `test_shutdown_drain.py`、`test_terminal_lifecycle.py` | app 级状态泄漏会伪装成产品随机崩溃（gotchas 第 44 条） |

### 2.3 真机验收（单测覆盖不到的那一层）

Linux 真机（230 Kali + X + 真 NAS）上跑产物，结论写进 `docs/linux-gap.md` §5.2 与
`docs/gotchas.md`，取证脚本历史上放在 `tmp/`（p46…p60 系列）——**`tmp/` 已在 `.gitignore` 里，脚本本身不入库**，
文档只留脚本编号与实测数字，别人复现按那几条结论自己写探针。跨进程剪贴板时序、真鼠标轨迹、
Wayland 这三类**只能**在这一层定论 —— 单测转绿不等于真机通过。

## 3. 测试夹具（`tests/conftest.py` 实际有的）

```python
@pytest.fixture(scope="session")
def qapp():                       # 全跑共用一个 QApplication
    ...

@pytest.fixture(autouse=True)
def _reap_top_level_widgets(qapp):  # 每个用例后收干净顶层窗口，防状态泄漏
    ...

@pytest.fixture
def tmp_dir(tmp_path):            # 文件操作用的临时目录别名
    ...

def qt_exceptions():              # 收集 Qt 抛出的 Python 异常
    ...
```

没有 `mock_file_system`、没有 `pane` 夹具、也没有 `tests/fixtures/` 目录：控件在自己用例里
现造（`Pane("t_nav", start_path=...)`），靶子文件在 `tmp_path` 下现建。

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
| 自定义主题接口 | **没有这个接口可测**：主题只有 `theme_manager.py` 内嵌的两套（dark/light），不存在外置 JSON 主题加载（2026-09-23 核查，见 `docs/architecture.md` §3.3） |

## 5. 测试命令

`tests/` 是扁平一层，**没有 `unit/` / `integration/` 子目录**，分层靠用例本身（纯函数用例不建
Qt 对象，控件用例用 `qtbot`）。

```bash
# 运行全部测试（无显示的环境必须离屏）
QT_QPA_PLATFORM=offscreen pytest tests/ -q
```

> **当前状态（2026-09-23 实测）**：上面这条**不会返回**。触发点是**「用两个文件路径构造
> `FileCompareDialog`」**这个动作本身：`__init__` 里两个路径都给就立刻 `self.compare()`，走错误分支
> 弹 `QMessageBox.warning`，模态框在 offscreen 下没人点 OK，进程就此停住。全仓 9 处踩中，分属两档
> ——`tests/test_new_features.py` 6 处（:59 :76 :93 :121 :145 :581）、`tests/test_m5_tools.py` 3 处
> （:191 :200 :213）。
>
> **所以 `--ignore` 只列一个文件没用**（我第一次就这么错过）：加 `--ignore=tests/test_new_features.py`
> 后全量能跑到 50%，然后原样卡在 `tests/test_m5_tools.py::TestFileCompare::test_file_compare_dialog_creation`。
> 两档都要排除才跑得完：
> `QT_QPA_PLATFORM=offscreen pytest tests/ -q --ignore=tests/test_new_features.py --ignore=tests/test_m5_tools.py`。
> 2026-09-23 本机实测这条：Windows / Python 3.13 / offscreen → **644 passed, 4 skipped in 85.56s**
> （`tmp/p62_fullsuite_minus2.log`，日志不入库）。
> 根因与销账条件写在 `docs/todo.md` T4/T5、`docs/gotchas.md` 第 56 条。
> **修好之前别在任何文档里写「全量通过」** —— v1.9.020 起就没有过一次跑完的 `tests/`；
> 排除两档跑出的数字是「次全量」，报的时候要照实写排除了什么。

```bash
# 按文件 / 按用例
pytest tests/test_dir_model.py -v
pytest tests/test_dir_model.py::test_refresh_empty_dir_after_new_file_visible -v

# 生成覆盖率报告（pytest-cov 未在依赖清单里，先装）
pytest tests/ --cov=core --cov=widgets --cov=config --cov-report=term-missing

# Windows 上设离屏变量
#   $env:QT_QPA_PLATFORM='offscreen'
```

## 6. 持续集成（**目前不存在**）

仓库里没有 `.github/workflows/`，也没有任何 CI 配置，下面这份是**待写入的草案**，不是现状：

```yaml
# .github/workflows/test.yml —— 草案，仓库中尚无此文件
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt && pip install pytest pytest-qt pytest-cov
      - run: xvfb-run pytest tests/ --cov --cov-report=xml
```

## 7. 测试数据管理

- **没有 `tests/fixtures/` 目录**。需要文件的用例一律用 pytest 内置的 `tmp_path` / `tmp_dir`
  （`tests/conftest.py` 里 `tmp_dir` 就是 `tmp_path` 的别名），跑完自动清理。
- 唯一的仓内靶子是 `test_media/20180406_IMG_8002.HEIC`（HEIC 缩略图用），缺文件时相关用例
  自己 `skip`（见 `tests/test_m3_preview.py:63`），不会红。
- 需要真目录树的用例（收藏夹、拖放、模型）在 `tmp_path` 下现造，不落仓内数据。
