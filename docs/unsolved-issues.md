# Pan4dex 待解决难点（2026-09-14 更新）

> 2026-09-02 更新：原始问题 1、2、3、4 全部已解决。后续新增问题（控制台窗口、任务栏图标、浅色主题、标签栏行为、菜单栏空隙、超大图标切换、onedir 构建）也全部已解决。
>
> 2026-09-14 更新：新增问题 13（全量测试偶发 access violation）。
>
> 2026-09-14 追更：问题 13 已定位并修复（v1.9.004）—— 根因不在“模型被销毁”，而在
> **退出阶段还有未派发的跨线程投递**。运行中偶发 AV 的触发路径也已收敛（改后连续 25 轮
> 全量抽样 0 次崩溃），但未证明根除，量化评估见问题 13 末尾。

---

## ✅ 已解决（v1.9.004）

### 问题 13：全量测试偶发 access violation / 关闭程序时报错（退出时未派发的后台投递）

**现象**：
- `pytest tests -q` 跑全量时偶发进程直接崩溃，faulthandler 打印
  `Windows fatal exception: access violation`，无 Python 异常可捕
- 崩溃率：修复延迟回调生命周期前约 1/3～1/4 次运行；v1.9.003 后抽样 8 次全绿、
  另一次抽样 12 次中出现 1 次（残余但已显著降低）
- 只在测试全量连跑时复现；单跑 `test_m1_core + test_lifecycle + test_dir_model`
  10 次全绿；加 `-v`（改变输出/时序）时较难复现
- 同一机制在生产路径上的表现是退出码 `0xC0000409`（CPython fast-fail）—— 用户侧就是
  “关掉程序时报错”，所以这不是纯粹的测试环境问题

**已取得的证据**（faulthandler 全线程转储）：

```
Current thread (主线程):
  pytestqt/plugin.py:220  _process_events        # 崩在 Qt C++ 事件处理内部，无 Python 帧
其它线程:
  core/dir_model.py:97 / :122  enumerate_dir     # 2 个后台枚举在飞
  core/dir_model.py:146        _LoadTask.run -> signals.finished.emit(...)
```

此前同一类崩溃的栈顶是 `config/theme_manager.py:392 app.setStyleSheet` ←
`main_window.py:_deferred_init`（`QApplication.setStyleSheet` 会遍历 polish 全部存活控件）。

**已排除/已修掉的部分**：
1. `MainWindow`/`QuadPaneWidget`/`Pane`/`TreeSidebar`/`ThumbnailView` 的
   `QTimer.singleShot(ms, lambda: self.…)` 延后初始化 —— 定时器不属于对象，对象先被
   销毁时回调照跑（实测复现
   `RuntimeError: wrapped C/C++ object of type QTabWidget has been deleted`）。
   已统一改用 `core/lifecycle.call_later()`（定时器以业务对象为父），并由
   `tests/test_lifecycle.py` 锁定（含反证基线用例）。修后 `TerminalView has been
   deleted` 一类噪声完全消失。
2. 终端读线程向已删除控件投递信号 —— 见 `docs/gotchas.md` 第七节。
3. 测试里窗口只建不销、GC 随机时刻删除 —— `tests/conftest.py` 加 autouse
   `_reap_top_level_widgets` 确定性回收（它本身不是修复，而是把 AV 降级成可见的
   RuntimeError，才使得上面两条可定位）。

**根因（二分定位）**：崩在**解释器收尾阶段**，不是运行中的竞态。后台枚举任务
（`_LoadTask`）在子线程 `emit` 结果，事件循环一旦结束，这些 queued 投递可能还没派发；
投递事件里持有着一批 Python 对象（枚举条目、目录节点），而 `QThreadPool.globalInstance()`
和事件队列要等 `~QCoreApplication`（甚至更晚的静态析构）才销毁 —— 那时 CPython 已开始
finalize，Qt 从非主线程释放这些对象 → 直接 fast-fail。

**被否证的假设**（都曾写进过候选方案）：
- “投递的接收者已被销毁” → 控制实验：把 emit 目标换成 `sip.delete` 后的对象，200 轮
  全部 exit 0。Qt 的自动断连确实可靠，问题不在这里。
- “删窗格 / 销毁模型触发的” → pane 模式（真建真删 Pane）exit 0，只有 model 模式崩。
- “后台线程在收尾时还在跑就够了” → 纯 Python 计算的 emit 完全不崩，必须叠加真实
  系统调用（os.scandir / entry.stat / ctypes.windll）才会；且触发量还取决于**载荷体量**：
  System32 4867 条 × 200 模型（≈ 100 万对象）8/8 崩，600 条 × 200 不崩。
- “引用环把销毁时刻交给循环 GC” → 探针否证：PyQt6 的信号连接不在 Python 层强引用
  `__self__`，绑定方法直连不会形成引用环（`del` 后 weakref 立即失效，与无环 QObject 一致）。
- “改成弱引用 closure 分发更安全” → **反而更差**：实测在 pytest-qt teardown 的
  `_process_events` 里直接 AV，当前线程帧就落在 `_deliver`。原因是接收者不是模型时，
  Qt 不会在模型销毁时剔除已排队的投递，而 `_loader` 会被在飞任务活得比模型久。已改回
  绑定方法直连（接收者必须就是模型），并保留 `_loader` 随模型销毁。

**同时修掉的现场**：全量跑里抓到过一条指向同一类问题的可见异常 ——
`_on_entries_loaded` 在 `endInsertRows()` 之后调 `self._show_hidden()` 报
`AttributeError: 'DirStoreModel' object has no attribute '_filter'`（sip 在 C++ 部分
销毁时会清空实例 `__dict__`，即投递落在一个已销毁的模型上）。现在槽函数先把要用的自身
状态取完，行插入之后不再读实例状态，`directoryLoaded` 的发射也包了 RuntimeError 早退；
该用例已锁定，并用临时探针确认改前写法在同一场景下必报同样的 AttributeError。

**修复**：退出路径显式排空 —— `core/lifecycle.exec_and_drain(app)` 把 `app.exec()` 与
`drain_background_pool()` 绑成一个入口（clear 未开始的任务 → 等在飞的跑完 → 空转事件
循环把投递派发完 → 因派发可能触发新加载，再来一轮）；`tests/conftest.py` 在每个测试边界
也调一次，不留竞态窗口给下一个用例。同时收紧 `DirStoreModel` 的投递链路：`_loader` 以模型
为父（模型销毁→投递源一同销毁，在飞任务的 `emit` 会报错并被 `_LoadTask.run` 吞掉），
接收者保持为模型本身，槽内不再在行插入之后读实例状态。

**A/B 实测**：同一探针脚本、200 轮真实枚举，收尾不调 drain → 8/8 fast-fail；调 drain
→ 8/8 干净退出。

**未做**：没有给每个 `DirStoreModel` 加析构 `waitForDone`，也没有改线程模型 —— 既然触发
点不在“模型先亡”，这两条都解决不了问题，反而引入卡 UI 的风险（网络盘上一次枚举可能数秒）。

**相关文件**：`core/lifecycle.py`（`drain_background_pool` / `exec_and_drain`）、
`core/dir_model.py`（`_LoadTask` / `_LoadSignals` / `_on_entries_loaded`）、`main.py`、
`tests/conftest.py`、`tests/test_shutdown_drain.py`、`tests/test_dir_model.py`、
`docs/gotchas.md` 第 21、22 条

**遗留的度量缺口**：A/B 那条测试需要数千条目的目录才能触发，默认跳过
（`PAN4DEX_SHUTDOWN_CRASH_TARGET`），因此在普通机器上它不会运行；防回归主要靠契约测试
+ conftest 边界排空。

**残余与量化**：运行中（测试 teardown 阶段）的硬崩，修复前同一命令形式下 3/8 轮；修复后
25 轮（12 + 8 + 5，两种输出形式）全绿。若残余触发率仍是 3/8，25 轮全绿的概率只有约 10⁻⁵
—— 改善是真的；但样本不足以证明根除，继续在全量跑中观察，一旦再现先取 faulthandler
全线程转储（本轮的 `_deliver` 帧就是这么来的）。

**v1.9.005 追更：崩溃率与「后台枚举量」单调相关，不是与监视器数量相关**

接本地 watcher 时做了成批 A/B（每轮 = 全量 `pytest tests -q`，约 25s）：

| 配置 | 崩溃轮数 |
|---|---|
| 不挂任何监视（v1.9.004） | 0/10 |
| per-model 监视“曾导航过的所有目录” | 2/8 |
| 进程级 hub，监视“曾导航过的所有目录” | **10/10** |
| hub 注册但不把 `directoryNotice` 连到模型 | 4/4 |
| hub 存在但 `add()` 直接 return（不 addPath） | 0/4 |
| hub 注册但从不 `removePath` | 4/4 |
| hub + **只监视当前显示目录**（去掉重复枚举、TTL 判鲜） | 0/6 → 2/12 |
| 再加“本地目录到达即重扫” | **9/10** |
| HEAD（v1.9.004，无 watcher）同期对照 | 0/10 |
| 上表基础上：native 登记延迟到事件循环顶层 | 1/12 |
| 再叠加：枚举改**限流专用池**（4 线程） | **0/14** |
| 加上两个生命周期新用例后（未处理销毁时机） | 4/10 → 4/12（并多一个固定失败） |
| 再叠加：测试边界主动回收 + 关标签页握住引用 | **0/12**（5 failed 均为无关的主题幻影） |

上表已否证了三个新假设（都有探针/实验支撑，后人不必重走）：
1. “Windows 监视句柄 > 64 超 `MAXIMUM_WAIT_OBJECTS` 越界” → 单 watcher 登记 40/100/200
   个目录 + churn 通知，三组全部 rc=0。
2. “`addPath` 内部跑 `QWindowsSystemEventDispatcher` 嵌套事件循环导致重入” → 忙监视线程
   + 200 目录下 `addPath` 期间 0ms 定时器是否插入：6 次全 `during: []`。
3. “崩在通知派发到模型槽” → 只注册 native、不连模型的 `directoryNotice`，4/4 仍崩；
   而不 `addPath` 时 0/4 不崩。触发条件是 `addPath` 带来的**监视目录数量与通知流量**，
   不是一段 Python 回调代码。

真正的机制在前几组对比里：崩溃率跟着**枚举量（以及行信号量）**走。查下去发现
`beginInsertRows` 内部会回调 `rowCount(parent)`，而 `rowCount` 的惰性加载条件在
「已清 loading、未置 loaded」的过渡态下成立 → 以前**每个目录加载都白起两次枚举**
（见 `docs/gotchas.md` 第 24 条）。去掉重复枚举 + 只监视当前目录后降到 2/12，现场变成
`core/pane.py:431 setModel(sort_proxy)` ← 250ms `call_later` 的延迟建窗格。

把剩下的两个现场拆开看，又各指向一个**放大因子**：
1. **同一轮事件里多次 `addPath`/`removePath`**。native 登记原先在 `set_directory` 的调用栈
   里同步执行，导航测试里一个用例能连做十几次 `set_directory` → 登记来回抖动。改成“记目标 +
   0ms 定时器，事件循环顶层一次性 flush”后，同一轮的多次导航自动合并成一次登记：2/12 → 1/12。
2. **并发枚举线程数**。faulthandler 转储里同时有 **10 个线程**卡在 `enumerate_dir` —— 全局
   `QThreadPool.globalInstance()` 的并发数等于核数（本机 24 核）。目录枚举换成本地常量 4 线程
   的专用池 `dir_pool()`（一屏最多 4 个窗格，再多并发对 SMB 反而互抢通道）后 0/14。

9/10 那轮的 9 份 dump 完全一致（与其他轮的现场不同）：

```
Current thread (主线程):
  core/dir_model.py:689  _on_entries_loaded -> self.endInsertRows()
  pytestqt/plugin.py:220 _process_events     <- pytest_runtest_teardown
其它线程:
  core/dir_model.py  enumerate_dir / _entry_hidden / _LoadTask.run
```

即“行插入进行中目标对象失效”。试过两种 `sip.isdeleted` 守卫：入口判活 4/6 仍崩
（销毁发生在槽执行期间，不在入口）；在 `endInsertRows` 前判活早退则退化为
`0xC0000409` 并卡死（留下未闭合的 begin/end）。两条都已删，现在靠“不把枚举量
放大”避开，而不是靠守卫。**结论：“槽执行中途对象失效”仍未被根治**，只能保证
不再主动把它放大到必现；再现时先取 faulthandler 转储，并先查当下的枚举量。

**当时的 WER 记录**：故障模块 `Qt6Core.dll 6.11.2.0`，偏移 `0x3c0330`（与加 watcher
之前同一偏移）与 `0x324026`，异常码 `0xc0000005`。`pytest -v`（改变输出/时序）下不崩。

**可迁移的结论**：崩溃率 ≈ f(后台枚举量, 并发枚举线程数, 行信号量, native 登记抖动,
**对象销毁时机是否落在 GC 手里**)，而不是某个具体调用写错了。所以调优方向是**少扫、
串行一点、少发信号、别把生死交给 GC**；在“哪个调用写错了”这一层找，或加 `sip.isdeleted`
守卫，只会把 AV 换成 `0xC0000409` 或卡死。

**现场 B（延迟建窗格）的根因：已定 —— 销毁时机由循环 GC 决定**（v1.9.005 后续取证）。

取证链：该现场在另一种时序下不崩，而是抛可读的 `RuntimeError: wrapped C/C++ object of
type QVBoxLayout has been deleted`（`Pane.init_ui` 里 `self.layout.addWidget`），于是能拿到
完整 Python 栈：`pytestqt _process_events` → 250ms 定时器 → `_create_remaining_panes` →
`Pane.__init__` → `init_ui` 第 N 行。用逐行探针夹 `sip.isdeleted` 检查点，得到三个硬结果：

1. 进入回调时宿主 `QuadPaneWidget` **未死**，pane2/pane3 也都建成了，到 pane3/pane4 的
   `init_ui` **中途**窗格自己的 C++ 部分才消失 —— 不是“拿着死宿主开干”这么简单。
2. 死的确切时刻在一行**纯 Python 语句**上（`Entry(...)` 构造，即普通对象分配），而不是
   任何 Qt 调用 —— 排除嵌套事件循环，指向**分代 GC**。
3. 决定性实验：同一组合（`tests/test_lifecycle.py + tests/test_m1_core.py`）在 `gc.disable()`
   下 **22/22 通过**，平时则随机报 `... has been deleted`。机制至此确定。

**为什么 GC 能删掉正在用的东西**：`signal.connect(self.method)` 这类用法天然构成引用环
（self → button → button.receivers → 绑定方法 → self），包装器只能等分代 GC 回收，而 GC
可以在**任意** Python 分配点执行。当一个 Qt 对象同时满足“sip 当作 Python 拥有”与
“此刻 C++ 父指针为空”（典型来源：`QTabWidget.removeTab` 正是后者），它的包装器一被回收
就当场 `delete` C++ 对象，级联拆掉整棵子树 —— 若那一刻另一个窗格正在构造，拆掉的就是它
正在用的东西（Windows 下 `~QWidget` 还要 `DestroyWindow` → 重入消息派发，于是从“报错”
升级为“AV”）。`close_tab` 就在这个坑上：旧写法 `removeTab` + `deleteLater` 看似确定，实际
销毁时机完全在 GC 手里。

**修复（三处，已否证一种看似合理的写法）**：
- `MainWindow.close_tab`：**握住 Python 引用**（`self._closed_tabs`）+ `hide()` + `deleteLater()`，
  把销毁时机交给事件循环。注意：**只 `setParent(self)` 归还所有权拦不住**（实测包装器被
  回收时 C++ 照旧被删）。
- `_create_remaining_panes`：入口 `sip.isdeleted(self)` 直接放弃，并在构造失败且确认宿主已死
  时吞掉 RuntimeError（其余 RuntimeError 继续上抛，不掩盖真错误）。
- `tests/conftest.py`：每个用例结束时（`sip.delete` 顶层窗口 + 排空后台池之后）**主动
  `gc.collect()`**，把“由 GC 决定的销毁”集中到没有构造在飞的安全点。

**已经试过并回退的做法**（重要，后人别再试）：在生产路径的批量构造入口（`new_tab()`、
`_create_remaining_panes()` 开头）先 `gc.collect()` 再构造。理论上“把不确定时机换成确定
时机”，实测**反而制造新故障**：主动回收会把“已该死但拖着没死”的对象集中删掉，其中就有
即将被使用的宿主，同一个组合从 5 passed 变成 2 failed（`Pane(parent=self)` 报
`QuadPaneWidget has been deleted`）。**回收本身不是修复，消除“随时会被回收”这个状态才是。**

另：半途死的窗格已在 `Pane._instances` 里、后续每个 `MainWindow()` 都因它报 RuntimeError
（实测一轮 22 个级联失败）—— 这条已修（入册改到 `__init__` 末尾 + `Pane._live_instances()`
过滤），详见 `docs/gotchas.md` 第 27 条；本条的销毁时机问题写在第 28 条。

**取证时必知的一个细节**（实测，能省很多时间）：sip 删除对象的 C++ 部分时**不清空**
`__dict__`。所以在死 QObject 上读一个已赋值的属性不会报错，只有读**不存在**的属性才会
落到 Qt 元对象并报 `RuntimeError: ... has been deleted`。推论：用“读属性试死活”写守卫
不可靠，必须用 `sip.isdeleted()`。

---

## ✅ 已解决（近期）

### 问题 5：GUI 模式下控制台窗口无法关闭 / 空终端窗口

**现象**：
- 改为控制台子系统构建后，GUI 模式启动时仍弹出控制台窗口
- 窗口内无日志输出（空终端），关闭终端会同时关闭应用
- `free_console_in_gui_mode()` 调用后控制台仍不消失

**根因**：
`free_console_in_gui_mode()` 函数中，FreeConsole 之前的 stdout/stderr 重定向操作可能抛异常（如 `os` 未在函数内 import、文件路径问题等），被外层 `except Exception: pass` 静默吞掉，导致 FreeConsole **永远执行不到**。且原 stdout/stderr 文件句柄未关闭，可能阻止控制台窗口关闭。

**解决方案**：
1. FreeConsole 移到函数最前面，最先执行（最关键）
2. 每步独立 try/except，一步失败不影响后续步骤
3. FreeConsole 失败时回退到 `ShowWindow(SW_HIDE)` 隐藏窗口（用 `GetConsoleProcessList` 判断是否为新建控制台，仅隐藏新建的，不影响父终端）
4. 异常写入 `~/.config/pan4dex/logs/pan4dex.log`，不再静默吞掉
5. stderr 重定向到日志文件，保留崩溃诊断信息

**验证**：双击启动无控制台窗口；从 PowerShell 启动不阻塞终端；`--verbose/-v` 参数保留控制台显示日志。

**相关文件**：`main.py` — `free_console_in_gui_mode()` 重写

---

### 问题 6：任务栏图标显示为 Windows 默认图标

**现象**：
- 应用启动后，操作系统任务栏上显示的是 Windows 默认图标，而非应用图标
- 图标文件已存在于 `resources/icons/icon.ico`

**根因**：
①未设置 Windows AppUserModelID（Windows 用它来关联任务栏图标和应用）②Qt 未调用 `setWindowIcon()` 设置窗口图标。

**解决方案**：
1. `SetCurrentProcessExplicitAppUserModelID("com.pan4dex.app")`
2. `app.setWindowIcon(QIcon(icon_path))`（frozen 时从 `sys._MEIPASS/resources/icons/icon.ico` 加载）

**相关文件**：`main.py` — 应用初始化部分

---

### 问题 7：浅色主题下路径栏按钮图标看不见

**现象**：
- 切换到浅色主题后，路径栏的 ◀▶▲▦🔄🌲📑 等按钮几乎看不见
- 深色主题下按钮正常可见

**根因**：
路径栏按钮使用 Unicode 符号文字（◀▶▲▦🔄🌲📑），这些符号在 Windows 上由符号字体（Segoe UI Symbol 等）渲染，**不受 Qt 样式表 `color` 属性控制**——所以无论怎么改全局主题的按钮文字颜色都没用。浅色主题背景浅，符号文字颜色也浅，导致几乎看不见。

此外，qdarkstyle（深色主题）设置了更大的 icon-size，浅色主题用默认小图标，导致两边图标大小不一致。

**解决方案**：
1. 全部按钮换成 **Qt 标准图标**（QStyle.StandardPixmap），由 QStyle 绘制，自动适应深色/浅色主题
2. 按钮尺寸 24×24 → 28×28，图标尺寸 16×16 → 20×20
3. 浅色主题样式表 QToolButton 增加 `icon-size: 20px`，确保与深色主题一致

**相关文件**：`widgets/path_bar.py` — 全部按钮改为标准图标；`config/theme_manager.py` — 浅色主题 icon-size

---

### 问题 8：浅色主题整体难看（与 Q-Dir 对比）

**现象**：
- 浅色主题下按钮带边框+圆角，显得笨重
- 四个窗格之间没有明显分隔，整体扁平缺乏层次感
- 选中状态不够明显

**解决方案（浅色主题扁平化 redesign）**：
1. 工具栏按钮：去掉边框和背景，hover 才显浅蓝底色（Q-Dir 风格）
2. 树视图/列表视图：去掉 6px 圆角，改为直角；减少内边距
3. 主窗口背景：#f8f9fa → #e8eaed（比窗格略深，营造白色卡片层次感）
4. 选中项颜色：#e8f0fe → #cfe2fc（更饱和）
5. 新增 QSplitter 分隔条样式：2px #dadce0，hover 变蓝
6. 表头：浅灰背景 + 底部边框

**相关文件**：`config/theme_manager.py` — 浅色主题全面重写

---

### 问题 9：标签栏双击行为不正确

**现象**：
- 双击标签旁边空白区域无反应（不新建标签）
- 双击标签触发重命名（用户希望关闭）
- 顶层标签栏和窗格内标签栏行为不一致

**根因**：
Qt 的 `tabBarDoubleClicked` 信号**只在双击标签本身时触发**（index>=0），双击空白区域永远不会触发（index=-1 走不到），所以「双击空白新建标签」从未生效。pane.py 的事件过滤器则是任何双击都新建标签，不区分标签和空白。

**解决方案**：
1. 给 QTabWidget 装事件过滤器（覆盖整行宽度），用 `mapFrom()` 坐标映射 + `tabAt()` 判断点击位置
2. 双击标签 → 关闭标签；双击空白区域 → 新建标签
3. 重命名功能移至右键菜单
4. 顶层标签栏和窗格内标签栏两处统一修复

**相关文件**：`core/main_window.py`、`core/pane.py` — 事件过滤器 + 双击行为

---

### 问题 10：菜单栏与内容区域之间约 25px 无用空隙

**现象**：
- 菜单栏（文件/编辑/视图...）与四窗格内容之间有一条约 25px 的深色空隙
- 尝试折叠 QTabWidget 的 tabBar（setVisible/setMaximumHeight/stylesheet/自定义 CollapsibleTabBar 重写 sizeHint）均无效

**根因**：
空隙**不是 tabBar 造成的**，而是一个**空的 QToolBar**。`__init__` 中调用了 `create_tool_bar()`，该方法创建了一个没有任何 action 的空工具栏并 `addToolBar()` 到主窗口，空工具栏仍占固定高度（约 25px）。之前搜方法名时搜的是 `create_toolbar`（无下划线），漏掉了实际的 `create_tool_bar`（有下划线），导致多轮误诊。

**解决方案**：从 `__init__` 移除 `create_tool_bar()` 调用。

**相关文件**：`core/main_window.py` — 移除空工具栏调用

---

### 问题 11：超大图标模式下切换窗格内标签不刷新文件列表

**现象**：
- 切换到超大图标（xlarge）模式后，点击其它窗格内标签，文件列表不变，仍保持前一个标签的内容
- 只有切换显示模式（图标/超大图标/列表）才会刷新

**根因**：
`on_pane_tab_changed()` 和 `navigate_to()` 只更新了 tree_view（树视图）和路径栏，**没有同步更新 thumbnail_view（缩略图视图）**。超大图标模式下文件列表显示在 thumbnail_view 中（QListWidget + IconMode），所以切换标签后树视图更新了但缩略图视图仍是旧目录内容。thumbnail_view 只在切换到超大图标模式时加载一次目录（`on_view_mode_changed` 中调用 `load_directory`），之后导航和切换标签都不更新。

**解决方案**：
在 `on_pane_tab_changed()` 和 `navigate_to()` 中增加判断：如果 `thumbnail_view.isVisible()`（即超大图标模式），调用 `thumbnail_view.load_directory(path)` 同步刷新。

**相关文件**：`core/pane.py` — `on_pane_tab_changed()`、`navigate_to()`

---

### 问题 12：启动慢 / onefile 解压开销 / onedir 资源路径

**现象**：
- 应用启动较慢（onefile 模式每次启动需解压 54MB 到临时目录）
- 切换到 onedir 后，图标等资源文件加载失败（任务栏图标消失）

**根因**：
1. onefile 模式：PyInstaller 将所有文件打包进单个 exe，启动时解压到 `%TEMP%`，耗时 1-3 秒
2. onedir 模式：PyInstaller 6+ 把 data 文件（`--add-data`）放在 `_internal/` 子目录，但代码用 `sys._MEIPASS/resources/` 查找（指向 exe 根目录），路径不匹配导致资源加载失败

**解决方案**：
1. 构建模式从 `--onefile` 切换为 `--onedir`，消除解压开销，启动速度提升 1-3 秒
2. 排除 23 个未使用的 PyQt6 模块和 Python 标准库模块，减小体积
3. 构建脚本增加步骤：将 `_internal/resources/` 复制一份到输出根目录 `resources/`（和已有的 imageformats 处理方式一致）
4. 产物改为文件夹 + zip 分发包

**相关文件**：`scripts/build_windows.py` — onedir 模式 + 资源复制 + 模块排除

---

## ✅ 已解决（原始 4 问题）

### 问题 1：超大图标模式（ThumbnailView）切换后不显示

**现象**：
- 切换到超大图标模式后一片空白
- 日志显示 `View mode change error: name 'QApplication' is not defined`

**根因（2026-09-02 定位）**：
`core/pane.py` 的 `on_view_mode_changed()` 第 807 行调用了 `QApplication.processEvents()`，但整个文件**没有 import `QApplication`**。每次切超大图标都抛 `NameError`，被外层 `try/except` 吞掉，导致第 809 行的 `load_directory()` **永远执行不到** → xlarge 必然空白。

> 注：旧版本部署到 win54/55 时的"第一次正常、第二次空白"是另一个问题（旧版 PyQt6 的 QListView IconMode hide/show 后 flow 布局不重排），升级到 PyQt6 6.11 后本机不复现。

**解决方案**：
1. 在 `core/pane.py` 的 `from PyQt6.QtWidgets import (...)` 中加入 `QApplication`
2. 升级 PyQt6 到最新版（6.11+），旧版的 hide/show 布局 bug 已修复
3. 本机验证：PyQt6 6.11 + Python 3.13 下，真实 Pane + test_media（107 项），三次切换超大图标都正常显示

**相关文件**：
- `core/pane.py` — 已修复 import
- `widgets/thumbnail_view.py` — ThumbnailView 实现

---

### 问题 3：图片预览（缩略图）不显示 / 只显示前四张

**现象**：
- 超大图标模式下，图片文件只显示默认文件图标，不显示缩略图
- 后续表现为"前四张有缩略图，空几张没有，再四张有"的块状间隔

**根因（2026-09-02 定位）**：

**根因 A — 可见范围计算错误（只加载前四张）**：
`_load_visible_thumbnails()` 用 `indexAt(rect.bottomRight())` 计算可见范围的末尾行。在 IconMode + setGridSize 下，`indexAt` 对落在 item 间距/空白区的坐标经常返回 -1，导致：
```python
end = min(last.row() + 5, self.count() - 1)
    = min(-1 + 5, 106) = 4
```
永远只扫描 row 0~4 → 只有前四张有缩略图。

**根因 B — `_loading` 集合泄漏**：
`ThumbnailLoader.run()` 中，当 QImageReader 失败（如 HEIC 格式 Qt 不支持）时，代码走 `if not reader.canRead(): return` 分支，**不 emit 任何信号**。路径永远留在 `_loading` 集合中，`_load_visible_thumbnails()` 遇到 `if full_path in self._loading: continue` 就跳过，再也不会重试。

**根因 C — 异常完全吞掉**：
`except Exception: pass` 导致 loader 失败时无任何日志，无法诊断。

**根因 D — HEIC 格式 Qt 默认不支持**：
test_media 目录中有大量 .HEIC 文件，Qt 的 QImageReader 无法解码，需要 Pillow + pillow-heif 回退。

**解决方案**：
1. **可见范围判断改用 `visualItemRect`**：遍历所有 item，用 `self.visualItemRect(item).intersects(self.viewport().rect())` 判断可见性，不再依赖 `indexAt`
2. **新增 `failed` 信号**：`ThumbnailSignals` 增加 `failed = pyqtSignal(str)`，loader 失败时 emit，`_on_thumbnail_failed()` 中 `self._loading.discard(path)` 清理
3. **异常改为日志**：`except Exception as e: logger.debug(...)` 记录失败原因
4. **Pillow 回退解码 HEIC**：QImageReader 失败时，自动注册 pillow-heif 的 `register_heif_opener()`，用 Pillow 打开并 `thumbnail((256,256))` 缩尺寸，转 `QImage.copy()`（确保数据所有权安全）
5. 新增依赖 `pillow-heif>=0.16.0`，写入 `pyproject.toml` 和 `requirements.txt`

**本机验证**：
- test_media 可见区域 15 张图片（13 JPG + 2 HEIC）全部缓存成功
- HEIC 文件从 MISS → CACHED（解码尺寸 192×256 / 256×192）
- `_loading` 从泄漏状态（3 个卡住）→ 0（正常清理）
- 所有可见图片加载完后 timer 正常停止（all_done）

**相关文件**：
- `widgets/thumbnail_view.py` — 已全部修复
- `pyproject.toml` / `requirements.txt` — 新增 pillow-heif 依赖

---

### 问题 4：QTreeView 大图标 GDI 崩溃

**状态**：已通过架构变更规避。

**根因分析**：
旧的 `ThumbnailDelegate`（`core/thumbnail_delegate.py`）在 `paint()` 中用 `QPixmap(file_path)` 加载**全分辨率**图片（一张 20MP 照片 ≈ 80MB GDI DIB），单帧 paint 中可见区域几十张 → GDI 资源耗尽硬崩溃，无 Python 异常。

**解决方案**：
放弃 QTreeView + 自定义委托的大图标方案，改用独立的 `ThumbnailView`（`QListWidget + IconMode`），缩略图用 `QImageReader.setScaledSize(256)` 预缩放后再转 QPixmap，避免全分辨率 GDI DIB。

**注意**：如果未来要回 QTreeView 大图标方案，必须用 QImageReader 预缩放 + LRU 缓存，绝不能在 paint() 里直接 `QPixmap(file_path)` 加载全分辨率图。

---

### 问题 2：--windowed 模式 CLI 输出（AttachConsole 失败 / 乱码 / 无输出）

**状态**：已解决（2026-09-02，改为控制台子系统构建）。

**现象**：
- `pan4dex.exe --version` 从 PowerShell 7 启动时，什么都不输出
- 或弹出新的终端窗口一闪而过
- 不会输出到当前 PowerShell 窗口

**根因**：
PowerShell 7（pwsh）使用 **ConPTY 伪控制台**，GUI 子系统（`--windowed`）进程的 `AttachConsole(-1)` **永远无法附加**到 ConPTY——这是 Windows 控制台架构的根本限制，不是代码 bug。

之前尝试的 `WriteConsoleW` + `CreateFileW("CONOUT$")` 方案也失败了：`AttachConsole` 失败后走 `AllocConsole` 弹窗，`input()` 等待失败导致窗口一闪而过，用户看不到任何输出。

**解决方案**：
**改为控制台子系统构建**（`--console` 替代 `--windowed`），从根本上解决：

1. **构建配置**：`scripts/build_windows.py` 中 `--windowed` → `--console`；`pan4dex.spec` 中 `console=False` → `console=True`
2. **CLI 输出简化**：`_cli_output()` 不再需要 `AttachConsole`/`AllocConsole`/`WriteConsoleW`，直接 `print(output, flush=True)`——控制台子系统进程启动时自动继承父控制台
3. **GUI 模式隐藏控制台**：新增 `hide_console_if_standalone()`，用 `GetConsoleProcessList()` 判断控制台是否为本进程创建（双击启动时只有 1 个进程），是则 `ShowWindow(hwnd, SW_HIDE)` 隐藏；从 PowerShell/cmd 启动时（多个进程共享控制台）保留，用于显示日志

**验证**：
- PowerShell 7.6.5 中 `.\pan4dex-0.9.622.exe --version` → 直接输出 `Pan4dex v0.9.622 (build ...)`，不弹窗、不挂起 ✅
- `.\pan4dex-0.9.622.exe --info` → 输出 version/build_time/platform/python/frozen/base_dir ✅
- 双击启动 → 控制台窗口自动隐藏，GUI 正常显示 ✅
- 从 PowerShell 启动 GUI 模式 → 控制台保留，显示运行日志 ✅

**相关文件**：
- `main.py` — `_cli_output()` 简化为 print；新增 `hide_console_if_standalone()`；`main()` 中 GUI 初始化前调用隐藏
- `scripts/build_windows.py` — `--windowed` → `--console`
- `pan4dex.spec` — `console=False` → `console=True`
- `scripts/fix_console_subsystem.py` — 控制台子系统配套修改脚本

---

## 部署脚本（已可用）

`scripts/deploy.py` 一键部署，带验证：

```bash
python scripts/deploy.py 0.9.620
```

功能：
1. 验证本地版本号
2. scp 到 win54 + 每个文件验证存在
3. 构建 + 验证大小 >30MB
4. 打包 zip
5. 部署到 55
6. 验证 55 上文件存在

**已知陷阱**：
- `scp file win54:C:/workspace/pan4dex/` 会放到根目录，必须写全路径
- 不要通过 SSH 执行 pan4dex CLI（会阻塞 SSH 到超时）
- Windows SSH 输出是 GBK 编码

**构建环境（2026-09-02 更新）**：
- 本机使用 uv 虚拟环境：Python 3.13.11 + PyQt6 6.11 + PyInstaller 6.22.2 + pillow-heif 1.6.0 + qdarkstyle 3.2.3
- 构建命令：`.venv\Scripts\python.exe scripts\build_windows.py <版本号>`
- 产物：`releases/pan4dex-<版本号>/`（文件夹，直接运行 `pan4dex.exe`，约 140MB）+ `releases/pan4dex-<版本号>.zip`（分发包，约 53MB）
- 构建模式：`--onedir --console`（已从 `--onefile --windowed` 切换，消除启动解压开销 + 解决 CLI 输出问题）
- 排除模块：23 个未使用的 PyQt6 模块（QtNetwork/QtSql/QtMultimedia/QtWebEngine 等）+ tkinter/test/unittest

---

## 环境信息

| 机器 | 系统 | 角色 |
|------|------|------|
| 本机 (开发/构建) | Windows 10, Python 3.13 (uv venv) | 开发 + 构建 |
| win54 (192.168.5.54) | Windows 10, Python 3.13 | 构建机（旧） |
| win55 (192.168.5.55) | Windows 10 | 部署目标 |

**技术栈**：Python 3.13 + PyQt6 6.11 + PyInstaller --onedir --console + qdarkstyle + pillow-heif + send2trash

---

## 调试脚本（2026-09-02 新增）

位于 `scripts/` 目录，用于复现和验证问题：

| 脚本 | 用途 |
|------|------|
| `repro_issue1.py` | 最小复现：QListWidget IconMode hide/show 切换 |
| `repro_issue1_v2.py` | 使用真实 Pane 类复现视图切换 |
| `repro_issue3.py` | 验证懒加载缩略图链路（缓存数、loading 状态、逐项状态） |
| `repro_loader.py` | 直接单测 ThumbnailLoader（QImageReader + 信号） |

运行方式：`py -3.11 scripts\repro_xxx.py` 或 `.venv\Scripts\python.exe scripts\repro_xxx.py`
