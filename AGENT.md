# AGENT.md — Pan4dex 万格 · 索引

> 本文件只做导航与铁律，**不复制正文**。每条细节都属于下面某一份文档里的那一处：
> 同一句话写进两处，就必然有一处过期（本文件的历史版本正是这么落后的）。

## 这是什么

跨平台四窗格文件管理器（对标 Windows 的 Q-Dir）。Python 3.11+（开发机 3.13，依赖由 uv 管理）
+ PyQt6，PyInstaller 打成单文件产物。当前版本 `1.9.023`，工作分支 `dev/shell-behavior-smb-perf`。

## 去哪读

| 想知道 | 读这份 |
|---|---|
| 模块职责、数据流、关键设计决策 | `docs/architecture.md` ← 唯一持续与代码同步的架构文档 |
| 怎么构建出可安装的产物（Linux / Windows） | `docs/BUILD-GUIDE.md` ← 构建链路的当前真相 |
| 上手跑起来、日常命令 | `QUICKSTART.md` |
| 开发流程、加测试、代码规范、文档维护 | `docs/development-guide.md`；测试策略见 `docs/testing.md` |
| 某功能做没做、还剩什么 | `docs/feature-checklist.md`；Linux 半边另看 `docs/linux-gap.md` |
| 为什么不能那么写（踩过一次的都在这） | `docs/gotchas.md`（#1–#56，第六/七节是模型与生命周期） |
| 发布改了什么 | `docs/changelog.md` |
| 现在还挂着的问题 | `docs/unsolved-issues.md` |

## 代码怎么串起来

```
main.py                         入口：CLI 参数（--version/--info/--install-menu/--test-open）、
                                崩溃日志、GUI 模式下释放控制台（`free_console_in_gui_mode()`）
└─ core/main_window.py          MainWindow · QuadPaneWidget · 快捷键落点 · terminal/* 设置
   └─ core/pane.py              Pane · FileListTreeView · PaneSortProxyModel（排序+筛选同一代理）
      └─ core/dir_model.py      DirStoreModel：文件列表唯一数据源（后台枚举 + TTL 缓存 + 定向失效）
   文件操作   core/file_operations.py  纯执行层，不知道线程也不认识 Qt
              core/file_op_runner.py   后台线程 + 进度对话框 + 冲突询问 + 跨线程回投
   跨端判据   core/mounts.py     is_remote_location()
   生命周期   core/lifecycle.py  call_later() · exec_and_drain() · safe_event_filter
   UI 组件    widgets/           侧边栏 / 路径栏 / 预览 / 筛选栏 / 搜索 / 各工具对话框
   配置       config/app_config.py  VERSION · BUILD_TIME
              config/paths.py       用户级 JSON 的唯一落点（win %APPDATA%\pan4dex，其余 ~/.config/pan4dex）
              其余持久化直接走 QSettings(ORG_NAME, APP_NAME)，键由各宿主自己读写
```

依赖声明在 `pyproject.toml`（锁在 `uv.lock`）；**没有 `requirements-dev.txt`**，打包依赖在
`[project.optional-dependencies].build`、测试依赖在 `.dev`（`uv sync --extra dev`）。

## 铁律（违反即回归；出处是 `docs/gotchas.md` 的对应条号）

1. 「这个位置是不是慢位置」全仓只有一份判据 `core/mounts.py:is_remote_location()`。新增平台判据
   两端都要有真实分支，且失败一律退化成代价最小的一侧。（#43）
2. 目录监视的六条约束缺一就会闪列表或直接 AV：只监视**屏幕上看得见的本地目录**、全进程共用一个
   `_WatchHub`、通知 350ms 防抖合并、应用内改动用**类级** `_self_change` 抑制后续通知、native
   `addPath/removePath` 推到事件循环顶层一次性 flush、慢位置完全不挂。（#23、#12）
3. 排序比较与筛选判定里禁止任何碰磁盘的调用（`stat`/`isdir`），只读 `Entry` 已缓存的
   `name/is_dir/size/mtime` —— 一次排序要跑 O(n log n) 次比较。（#29、#30）
4. 不要把 Qt 对象的生死交给分代 GC：`removeTab` 之后必须握住 Python 引用再 `deleteLater`。（#28）
5. 后台 → UI 的投递：信号接收者必须就是目标 QObject（别为「判活」改成 closure）；延后执行用
   `call_later` 而不是 `QTimer.singleShot`；进程退出走 `exec_and_drain`。（#17、#20、#21、#22）
6. 快捷键与侧边栏点击的落点只认 `MainWindow.target_pane()`，且焦点在文本控件里时不去动文件系统；
   直接判 `_active_pane` 会在 Linux/X11 上静默失效。（#47、#49）
7. 改了「怎么说」就得同时改「怎么做」：删除的确认文案与是否走回收站共用同一个判据。（#50）
8. 用 `if 集合:` 守卫「清理/复位状态位」时，边界空集会静默跳过复位，新数据再被下游幂等守卫整份
   吞掉。（#55）
9. 新 UI 模块要么带上入口、要么登记成待办，**不许标 🟢**（全仓除测试外零引用的组件，产品里点不到，
   `ImportError` 只有被 import 时才炸）；发布前跑完整 `tests/`，**跑不完就是跑不过** —— 弹窗写在
   `except` 分支里会把「测试失败」变成「测试永久挂住」。（#56）

## 命令

```bash
python main.py                                  # 跑起来
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q   # GUI 测试离屏跑（Windows 上先设环境变量）
bash scripts/build-linux-docker.sh              # Linux 唯一入口 → releases/pan4dex-<版本>-linux
python scripts/build_windows.py                 # Windows 本机 → releases/pan4dex-<版本>/ + 同名 .zip
```

> 全量那条**当前会挂住**（不是慢）：只要**用两个文件路径构造 `FileCompareDialog`**，`__init__` 就立刻
> `compare()`，错误分支弹模态 `QMessageBox`，offscreen 下永不返回。踩中 9 处，在
> `tests/test_new_features.py`（6 处）**和** `tests/test_m5_tools.py`（3 处）两档里 —— 所以 `--ignore`
> 必须同时排除这两档，只排一个会在 50% 处卡住。详见 gotchas #56 与 `docs/feature-checklist.md` 第 23 节 T4/T5。

## 发布一次要动哪几处

1. `config/app_config.py` 的 `VERSION` 与 `pyproject.toml` 的 `version` 同步（末位 +1，人工控制，
   不要自动递增）。
2. `docs/changelog.md` 新增分节；功能状态变了就同步 `docs/feature-checklist.md` /
   `docs/linux-gap.md` / `docs/gotchas.md`——**状态改了正文没跟上，比没改更坏**。
3. 出产物后由 `scripts/build_windows.py` 写回 `BUILD_TIME`，单独一条 `chore(build)` 提交，保持
   「源码 BUILD_TIME == 已发布二进制」这条惯例。
4. 打 tag `v<版本>`。
5. 前置条件是**完整 `tests/` 跑得出汇总行**（不是只跑本次改动相关的文件）：`pytest tests/ -q`
   跑不完就是跑不过（#56）。

## 约定

- 提交信息：Conventional Commits（`fix(scope): 中文摘要`），正文按「现场 → 根因 → 修法 → tests →
  docs」写；修复类必须带真实复现路径。
- 测试：`tests/` 是扁平一层（**没有 `unit/` / `integration/` 子目录**），GUI 走 pytest-qt +
  offscreen，不 mock 掉被测行为本身。
- 版本号格式：`1.9.0XX`。
