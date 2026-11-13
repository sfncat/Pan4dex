# AGENTS.md — Pan4dex 万格 · 索引

> 本文件只做导航与铁律，**不复制正文**。每条细节都属于下面某一份文档里的那一处：
> 同一句话写进两处，就必然有一处过期（本文件的历史版本正是这么落后的）。

## 项目进度上报

- 本项目根目录的 `PROJECT_STATUS.md` 是进度上报文件，由本项目自己维护，供上层汇总只读取用。
- **每次改动收尾时更新**，不要等想起来再补。
- 结构：front matter（`project` / `path` / `status`(active|paused|done) / `owner_ai` / `updated`）+ 四段正文：`## 当前进展` / `## 等你决策` / `## TOP 待办` / `## 最近完成`。
- `## 当前进展` 一两句说清做到哪、卡在哪；`## 等你决策` 只放需要用户拍板的事，没有就写「暂无」，**这一段不许省略**；`## TOP 待办` 只放不依赖用户、AI 自己能推进的事，最多 5 条，行顺序即优先级；`## 最近完成` 倒序。
- 只写能确认的事实，未知写「待补充」，不编造。
- 动笔前先读规范：技能 `agents-md-authoring` 的 `references/project-status.md`。

## 变更记录

- 根目录 `CHANGELOG.md` 是本项目的变更记录，面向使用者，按版本组织，**最新在最上面**。
- 每次发版前更新；日常小改动不必逐条写，攒到发版时归并。
- **攒着尚未出包的这一批**：顶部写一个「计划版本号」小节（如 `## [1.9.049] - 未发布（攒下一批一起出包）`），
  条目照常按 `Added` / `Changed` / `Fixed` / `Removed` 分类。此时 `config/app_config.py` 的 `VERSION`、
  `pyproject.toml` 的 `version` 与 tag **都仍停在最后一个已出包版本**，不要在写这一节时就 +1；
  真正出包时再把「未发布」改成 `YYYY-MM-DD（master）` 并同步版本与 tag。摸不到入口的功能
  （待办里挂着「没接线」的）要在这条下面括注清楚，免得使用者以为已经能用。
- 格式：`## [版本号] - YYYY-MM-DD`，下面按 `Added` / `Changed` / `Fixed` / `Removed` 分类；只写用户能感知的变化，不写实现细节，也不写「优化代码结构」这类空话。
- 与 `PROJECT_STATUS.md` 的 `## 最近完成`、`git log` 分工不同，不要互相复制。
- 动笔前先读规范：技能 `agents-md-authoring` 的 `references/changelog.md`。

## 这是什么

跨平台四窗格文件管理器（对标 Windows 的 Q-Dir）。Python 3.11+（开发机 3.13，依赖由 uv 管理）
+ PyQt6，PyInstaller 冻结产物（Linux 单文件 ELF / Windows onedir + zip）。当前版本 `1.9.050`，
开发分支就是 `master`（2026-09-24 起不再走 `dev/*`，动手前先 `git pull --ff-only`）。

## 去哪读

| 想知道 | 读这份 |
|---|---|
| 模块职责、数据流、关键设计决策 | `docs/architecture.md` ← 唯一持续与代码同步的架构文档 |
| 怎么构建出可安装的产物（Linux / Windows） | `docs/BUILD-GUIDE.md` ← 构建链路的当前真相 |
| 上手跑起来、日常命令 | `QUICKSTART.md` |
| 开发流程、加测试、代码规范、文档维护 | `docs/development-guide.md`；测试策略见 `docs/testing.md` |
| 某功能做没做、还剩什么 | `docs/feature-checklist.md`（状态表）；**待办看 `docs/todo.md`**；Linux 半边另看 `docs/linux-gap.md` |
| 为什么不能那么写（踩过一次的都在这） | `docs/gotchas.md`（#1–#65，第六/七节是模型与生命周期） |
| 发布改了什么 | `CHANGELOG.md` |
| 版本更新机制（230 更新服务器 + 客户端自动更新） | `docs/update.md` |
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
   系统定位   core/reveal.py     reveal_in_file_manager()（窗格与高级搜索共用这一份）
   视图键位   widgets/view_keys.py  handle_edge_jump()（详情视图与缩略图/平铺共用）
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
3. 排序比较与筛选判定里禁止任何碰磁盘的调用（`stat`/`isdir`），**也禁止回模型取 `data()`**，
   只读 `Entry` 已缓存的 `name/is_dir/size/mtime` —— 一次排序要跑 O(n log n) 次比较，
   每次模型往返都是一趟白工（名称列这一刀实测把落地停摆砍掉一半）。（#29、#30、#60）
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
10. 新增后台线程池必须同时登记进 `core/lifecycle.py:_pools_to_drain()`（**含每个控件自带的池**），
    否则退出时未派发的跨线程投递留到解释器收尾阶段被 Qt 释放 → Windows fast-fail（0xC0000409）。
    判「Qt 对象还活着」要 `sip.isdeleted`，weakref 判不出 `sip.delete`。（#64、#65）

## 命令

```bash
python main.py                                  # 跑起来
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q   # GUI 测试离屏跑（Windows 上先设环境变量）
bash scripts/build-linux-docker.sh              # Linux 唯一入口 → releases/pan4dex-<版本>-linux
python scripts/build_windows.py                 # Windows 本机 → releases/pan4dex-<版本>/ + 同名 .zip
```

> 全量那条**现在跑得完**，无需 `--ignore`（2026-11-13 基线：**895 passed / 5 skipped**，
> 见 `docs/testing.md` §5）。历史：v1.9.020–027 曾因「用两个文件路径构造 `FileCompareDialog`」
> 弹模态框挂住 `test_new_features.py` / `test_m5_tools.py` 两档，v1.9.028 修复、T4/T5 已销账
> （gotchas #56）。规矩没变：**跑不完就是跑不过**，报「全量通过」必须真拿到汇总行。

## 发布一次要动哪几处

1. `config/app_config.py` 的 `VERSION` 与 `pyproject.toml` 的 `version` 同步（末位 +1，人工控制，
   不要自动递增）。**这两处只在真正出包那一刻动**；文档提前按某个计划版本号记账时（见「变更记录」
   一节）不要顺手 +1。
2. `CHANGELOG.md` 新增分节；出包时把攒着的那节标题里的「未发布（攒下一批一起出包）」改成
   `YYYY-MM-DD（master）`；功能状态变了就同步 `docs/feature-checklist.md`（状态表）、
   `docs/todo.md`（销账那条改 ✅ 但**保留整行**）、`docs/linux-gap.md` / `docs/gotchas.md`——
   **状态改了正文没跟上，比没改更坏**。
3. `BUILD_TIME` 不回写源码：构建脚本打包前生成 `config/_build_info.py`（已 gitignore），
   打包后删除；仓库保持干净，也不再发 `chore(build)` 时间戳提交。
4. 打 tag `v<版本>`。
5. 前置条件是**完整 `tests/` 跑得出汇总行**（不是只跑本次改动相关的文件）：`pytest tests/ -q`
   跑不完就是跑不过（#56）。

## 约定

- 提交信息：Conventional Commits（`fix(scope): 中文摘要`），正文按「现场 → 根因 → 修法 → tests →
  docs」写；修复类必须带真实复现路径。
- 测试：`tests/` 是扁平一层（**没有 `unit/` / `integration/` 子目录**），GUI 走 pytest-qt +
  offscreen，不 mock 掉被测行为本身。
- 版本号格式：`1.9.0XX`。
