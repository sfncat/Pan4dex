# Pan4dex 开发踩坑记录（回归防护用）

每次出问题，必须：1) 修 bug 2) 写测试防护 3) 更新本文档

---

## 一、构建部署类

### 1. scp 目录结构错误

**现象**：`scp core/pane.py win54:C:/workspace/pan4dex/` 文件到 `pan4dex/pane.py` 而非 `pan4dex/core/pane.py`。

**解决**：`scp` 目标路径必须写全 `win54:C:/workspace/pan4dex/core/pane.py`。

**防护**：`scripts/deploy.py` 每个文件 scp 后 `if exist` 验证。

```bash
# 测试命令
python scripts/deploy.py 0.9.XXX
```

### 2. 不验证部署结果

**现象**：55 上文件存在但版本是旧的，或者文件根本没传过去。

**解决**：`deploy.py` 在 55 上用 `if exist` 验证文件存在，并检查 win54 构建输出大小。

**防护**：`deploy.py` 步骤 6 验证 + 构建大小 >30MB。

### 3. SSH 执行 Windows CLI 阻塞

**现象**：`ssh 55 'pan4dex.exe --version'` 永远不返回（GUI 程序阻塞 SSH）。

**解决**：不通过 SSH 执行 pan4dex CLI，改用 `dir` 验证文件大小/时间戳。

**防护**：`deploy.py` 用 `if exist` 而不是运行 exe。

---

## 二、Qt 多窗格类

### 4. QFileSystemModel.setRootPath() 共享模型陷阱

> **状态（v1.9.001）**：文件列表已改为每窗格独立的 `DirStoreModel`，本条作为历史保留；
> 两个侧边目录树仍用 `QFileSystemModel`，该陷阱在树里依然成立。

**现象**：导航到一个目录后，其他窗格的文件列表变成该目录的内容。

**根因**：四个窗格共享同一个 `QFileSystemModel`，`setRootPath()` 改变了模型的根目录，所有绑定该模型的视图都受影响。

**解决**：导航时用 `model.index(path)` + `setRootIndex(index)`，不用 `setRootPath()`。

**测试**：

```python
def test_shared_model():
    pane1.navigate_to("/dir/a")
    pane2.navigate_to("/dir/b")
    assert pane1.current_path == "/dir/a"
    assert pane2.current_path == "/dir/b"
    assert pane1.tree_view.rootIndex() != pane2.tree_view.rootIndex()
```

### 5. QDockWidget.parent() 不可靠

**现象**：TreeSidebar 里 `self.parent()` 不是 MainWindow，跟随按钮拿不到 `_active_pane`。

**解决**：`__init__` 里显式保存 `self._main_window_ref = parent`。

**防护**：所有需要访问父窗口的组件，都在 `__init__` 里保存引用。

---

## 三、异步加载类

### 6. QFileSystemModel 异步加载 + expand_to_path

**现象**：`expand_to_path("D:/a/b/c")` 时，模型还没索引到 `c`，`model.index(p)` 返回无效值，展开失败。

**解决**：逐级展开 + `directoryLoaded` 信号 + QTimer 延迟重试。

```python
def _expand_parts(self, parts, idx):
    if idx >= len(parts):
        return  # 完成
    index = self.model.index(parts[idx])
    if index.isValid():
        self.tree_view.expand(index)
        QTimer.singleShot(100, lambda: self._expand_parts(parts, idx + 1))
    else:
        self._pending_path = parts[idx]
        QTimer.singleShot(300, lambda: self._expand_parts(parts, idx))
```

**防护**：所有涉及 QFileSystemModel 的操作都要处理异步。

### 7. ThumbnailView 第二次加载不显示

**现象**：第一次切换到超大图标正常，再切换到列表/图标再切回超大图标，一片空白。

**根因**：QListWidget 在 `hide()` + `clear()` + `show()` 后，内部布局状态没有正确重置。

**解决**：`load_directory` 里先 `hide()` → `clear()` → 重建 → `show()` + `doItemsLayout()` + `scheduleDelayedItemsLayout()`。

**防护**：切换可见性后必须强制刷新布局。

---

## 四、Windows 平台类

### 8. --windowed 模式 CLI 输出

**现象**：`pan4dex.exe --version` 从 PowerShell 启动时弹窗、新建终端、乱码。

**根因**：`AttachConsole(-1)` 在 PowerShell 下失败，`AllocConsole()` 新建窗口，代码页不是 UTF-8。

**解决**：`FreeConsole()` + `AttachConsole(-1)` 尝试挂父控制台，失败则 `AllocConsole()` + `SetConsoleCP(65001)`。输出用 `open("CONOUT$", "w", encoding="utf-8")` 而不是 `os.fdopen(os.open(...))`。

**状态**：还有乱码问题，待进一步研究。

### 9. SSH 输出编码

**现象**：`ssh win54 'cmd /c "..."'` 输出中文乱码或 UnicodeDecodeError。

**解决**：`r.stdout.decode("gbk", errors="replace")` 解码 Windows 输出。

**防护**：`deploy.py` 的 `sh()` 函数统一用 GBK 解码。

---

## 五、UI 交互类

### 10. QTreeView.setIconSize(128) GDI 崩溃

**现象**：`QTreeView` + `QStyledItemDelegate` + 128px 图标 → Windows GDI 级崩溃，无 Python 异常。

**解决**：放弃 QTreeView 大图标，改用独立的 `QListWidget + IconMode`（ThumbnailView）。

### 11. QSS 样式被主题覆盖

**现象**：应用 qdarkstyle 后，自定义的 QListWidget 背景色不生效。

**解决**：用 `rgba()` 半透明色值 + `border: none`，避免与主题冲突。

---

## 六、DirStoreModel（文件列表异步模型）类

### 12. 应用内改动必须显式重扫（watcher 只覆盖“当前显示的本地目录”）

**现象**：新建/删除/粘贴/拖放后条目不可见，只有按 F5 才刷新（本地目录也一样）。

**根因**：为避开 SMB 上的 watcher 轮询，`DirStoreModel` 早期版本完全不挂文件监视；
旧共享模型时代 `QFileSystemModel` 会自己发现本地变更，删掉它之后这份“免费午餐”就
没了。又因为旧缓存对本地目录永久新鲜（`_fresh_or_local()` 恒为 True），陈旧节点
不丢弃就永远不重扫。

**解决**：两层。① pane 侧所有改动完成回调统一走 `_reload_after_mutation(path)`
（`refresh_dir` 失效并重扫 + `navigate_to`），不区分本地/网络；② 模型只给**当前显示的
本地目录**挂 watcher（见第 23 条），本地快照改成 TTL 过期，导航回来时过期就重扫一次。

**测试**：`tests/test_pane_dir_store.py::test_local_mutation_visible_after_reload`、
`tests/test_dir_model.py::test_only_displayed_dir_is_watched`

### 13. 同一目录并发枚举：旧快照会永久占位

**现象**：刷新 / 切换隐藏文件开关后，新文件迟迟不出现；直接单步调
`model.refresh_dir(path)` 却能立刻看到。

**根因**：同一节点上叠加了多个 in-flight  `_LoadTask`，旧枚举结果先回到主线程，
`if node.loaded: return` 的幂等守卫让它当成“已完成”而永久占据视图，新结果反而被丢弃。

**解决**：`DirNode.gen` 请求代次——`_start_load` 先 `gen += 1`，回调首行
`if gen != node.gen: return`（在清 `loading` 之前），只采纳最新一次结果。

**测试**：`tests/test_dir_model.py::test_stale_generation_result_ignored`、
`test_refresh_after_new_file_wins`

### 14. 两层结构下 `index(path)` 只能给“当前显示目录”的索引

**现象**：对未加载/已切走的目录做行内改名时，窗格不导航到父目录，`current_path` 停在原地。

**根因**：模型里任何 `DirNode` 的 `parent()` 都报为 invalid 根，而
`index(0, 0, invalid)` 只会解出顶层节点；为非显示目录的条目返回索引，经排序代理
`mapFromSource` 后会得到“看似有效实则错行”的索引。

**解决**：`_index_for_path` 只解析 top 节点及其条目；判定任意路径是否目录改用
`entry_is_dir(path)`（纯内存，未知返回 None 由调用方回退 `os.path.isdir`）。

**测试**：`tests/test_dir_model.py::test_index_only_for_displayed_dir`

### 15. 类级 `_CACHE` 只能当只读模板

**现象**：一个窗格改名，另一个窗格同目录的条目文字跟着变；`e.node` 反查指向别的窗格节点。

**根因**：`Entry` 是可变的（行内改名就地改 `name`/`path`，`node` 用于 `parent()`），
而跨窗格缓存命中时直接把同一个列表/对象挂到两个节点上。

**解决**：缓存命中走 `_copy_entries`（逐份复制并重新回填 `node`），后台新枚举结果
走 `_adopt`（本节点独占）。

**测试**：`tests/test_dir_model.py::test_cache_entries_are_copied_per_node`、
`tests/test_pane_dir_store.py::test_cross_pane_rename_syncs`

### 16. Qt6 枚举/接口的写法陷阱（写模型时踩过）

- `Qt.ItemFlag` 没有 `ItemHasChildren`：目录用 `rowCount`/`canFetchMore` 表达，
  肯定无子项的文件用 `ItemNeverHasChildren`。
- 判断是否在编辑：`tv.state() == QAbstractItemView.State.EditingState`，
  不存在 `tv.state.EditingState`。
- PyQt6 未暴露 `cancelEditing()`：测试里用 `QTest.keyPress(tv, Qt.Key.Key_Escape)` 收起编辑框。
- `tv.reset()` 会连 `rootIndex` 一起重置，破坏文件列表视图，不可用于“取消编辑”。

---

## 七、Qt 对象生命周期与后台线程类

### 17. 后台线程不得直接 emit（控件可能已被删除）

**现象**：stderr 反复出现 `RuntimeError: wrapped C/C++ object of type TerminalView
has been deleted`，终端输出偶发不再刷新；极端情况下直接段错误。

**根因**：`threading.Thread` 里 `self.some_signal.emit(...)`。主线程删除控件的
C++ 对象时不会通知 Python 线程；Windows 上 `pty.read` 无数据即永远阻塞，`join()`
也等不回来，因此“先停线程再销毁”从根本上做不通。

**解决**：统一经 `_emit_ui(信号名, *args)`：先查停止标志，再
`try: getattr(self, name).emit(...) except RuntimeError: pass`。

关键细节：**参数必须是信号名（字符串），不能是信号对象** ——
`self._emit_ui(self.output_received, data)` 的 `self.output_received` 在进函数前的
求值阶段就抛 RuntimeError，try 完全盖不到。

**测试**：`tests/test_terminal_lifecycle.py`

### 18. `self.destroyed.connect(self._slot)` 不会被调用

**现象**：给控件挂了 `destroyed` 兜底槽，控件销毁后槽没跑（清理逻辑静默失效）。

**根因**：Qt 在发射 `destroyed()` 前已断开“接收者是本对象”的所有连接，绑定方法槽
（receiver == 该对象）永远收不到；lambda / 普通函数没有 receiver，会被调用。

**解决**：`self.destroyed.connect(lambda *_: self._on_destroyed())`；槽内只能做
Python 级操作（写实例属性、调纯 Python 对象），不能碰任何 Qt 调用。

**另注**：测试里 `widget.destroy()` 对 QWidget **并不会**删除 C++ 对象（信号也不发），
要用 `from PyQt6 import sip; sip.delete(obj)` 才能真正删除并触发 `destroyed`。

### 19. QDockWidget 的 closeEvent 不等于销毁

**现象**：终端面板点 X 关掉再从菜单打开，是个再也没有输出的死面板。

**根因**：`DockWidgetClosable` 的 X 只是 `hide()`，`QDockWidget` 对象还活着；
而旧 `closeEvent` 里 `close_shell()` 把会话杀了且无人重启。

**解决**：dock 自己关面板时不回收会话（隐藏即保留）；会话终止放到
`MainWindow.closeEvent` → `terminal_panel.shutdown()`（终态：不再启动、不再投递）。

### 20. `QTimer.singleShot(ms, lambda: self.…)` 不随对象销毁

**现象**：测试全量连跑偶发 `access violation`，也能退化为
`RuntimeError: wrapped C/C++ object of type QTabWidget has been deleted`；现场在
`main_window.py:232` 的 100ms 布局轮询里读 `self.tab_widget`。用户侧对应“启动就
关闭”“快速关标签页”。

**根因**：静态 `QTimer.singleShot` 建的定时器**不以 receiver 为父对象**，回调持有
`self` 且一定会等到触发；对象的 C++ 部分先被销毁（测试里 `sip.delete`、GC 随机时刻，
真实程序里关窗口）后，回调照旧运行并访问已删除的子对象。

**解决**：统一用 `core.lifecycle.call_later(receiver, msec, fn)` —— 定时器以业务对象
为父，随对象一起销毁，回调自然不再触发（靠 Qt 所有权语义，不在各调用点写
`sip.isdeleted` 守卫）。新增延后初始化一律用 `call_later`，不要用
`QTimer.singleShot`（`scripts/` 下的复现脚本除外）。

**测试**：`tests/test_lifecycle.py`（含一条“旧写法仍会报错”的反证基线用例）。

**关联**：`tests/conftest.py` 的 `_reap_top_level_widgets` 会在每个测试后销毁残留
窗口 —— 它不是修复，但把不可读的 AV 降级成带栈的 RuntimeError，是定位这类问题的前提。

### 21. 退出时还有未派发的跨线程投递 → 进程 fast-fail（0xC0000409）

**现象**：用户侧「关掉程序时报错」，退出码 `0xC0000409`
（STATUS_STACK_BUFFER_OVERRUN，实为 CPython fatal error 走 `__fastfail`），
faulthandler 也打不出可读的 Python 栈；测试全量连跑时的偶发 access violation 同一根源。

**根因**：线程池上的枚举任务在后台线程 `emit` 结果，事件循环
一旦结束，这些 queued 投递可能还没派发；投递事件里持有着一批 Python 对象（枚举条目、
目录节点）。而线程池/事件队列要等 `~QCoreApplication`（甚至更晚的静态析构）才销毁，
那时 CPython 已开始 finalize，Qt 从非主线程释放这些对象 → 硬崩。

**否证过的假设**：不是“接收者已被删除”—— 把 emit 目标换成 `sip.delete` 后的对象，
200 轮仍 exit 0。真正的触发条件是：后台做**真实系统调用**（os.scandir / entry.stat /
ctypes）+ 后台 emit，且退出时残留的**载荷体量足够大**（System32 4867 条 × 200 模型
≈ 100 万对象：8/8 崩；600 条 × 200：不崩；纯 Python 计算的 emit 怎么都不崩）。

**解决**：退出路径显式排空 —— `main.py` 用 `exec_and_drain(app)`（`app.exec()` 一返回
就 `drain_background_pool()`：逐池 clear → waitForDone → 空转事件循环把投递派发完 → 再来
一轮）。池不止一个（全局池 + 目录枚举专用池，见第 26 条），所以排空走 `_pools_to_drain()`，
**新增线程池时必须加进去**。测试边界（`conftest._reap_top_level_widgets`）也调一次，
不留竞态窗口给下一个用例。

**注意**：`drain_background_pool()` 只能在退出/teardown 调；运行中调会阻塞主线程，
网络盘上一次枚举可能耗时数秒。

**测试**：`tests/test_shutdown_drain.py`（A/B 那条默认跳过，需
`PAN4DEX_SHUTDOWN_CRASH_TARGET` 指向一个数千条目的目录才能复现）。

### 22. 后台投递的接收者必须是目标对象本身（别为“判活”改成 closure）

**现象**：为了让枚举结果不落到已销毁的模型上，把
`loader.finished.connect(self._on_entries_loaded)` 换成“弱引用 closure + `sip.isdeleted`
判活”；结果反而崩得更快 —— faulthandler 显示当前线程帧就落在那个 closure 里。

**根因**：连接的目标如果是普通可调用对象（没有指向 QObject 的 `__self__`），Qt 认定的
**接收者是 sender**。接收者不是模型时，模型销毁并不会剔除已排队的投递；而 `_LoadSignals`
会被在飞任务（`QRunnable` 持有它）活得比模型久，投递就照旧派发 → 在悬空的模型上调方法。
绑定方法直连时接收者就是模型，`~QObject` 会 disconnect + `removePostedEvents` —— 这才是
Qt 提供的保护，Python 层的判活抢不过它。

**解决**：投递仍用绑定方法直连，同时 `_LoadSignals(self)` 以模型为父（模型销毁→投递源
一同销毁，worker 里的 `emit` 报 RuntimeError，在 `_LoadTask.run` 里吞掉）。“判活”不放在
接收者上，而是放在槽自己的写法上：**先把要用的实例状态取完，begin/endInsertRows 之后
不再读 self**（sip 在 C++ 部分销毁时会清空实例 `__dict__`，那时读 `self._filter` 就是
AttributeError）。

**测试**：`tests/test_dir_model.py::test_load_slot_reads_no_self_state_after_row_insertion`
（临时探针确认改前写法在同一场景下必报同样的 AttributeError）、
`::test_in_flight_load_after_model_death_is_dropped`。

### 23. 文件列表的 watcher 只能监视本地的「当前显示目录」

**背景**：换掉 `QFileSystemModel` 后拿到一次净赚：SMB 上不再有后台轮询。但代价是
本地目录也失去了自动更新 —— 用 Explorer 新建/删除/改名一个文件，Pan4dex 的列表
不会变。补回这个能力时要绕开六个坑（前四个是功能语义，后两个是命）：

1. **只登记本地目录**。网络目录一律不登记（`_is_network()` 为真直接 return）——
   那正是当初拖垮 SMB 的轮询源，网络目录仍走 TTL 2s + 定向失效。
2. **必须抑制应用内自己的改动**。应用内粘贴/新建/删除会先 `refresh_dir()`（已重扫），
   紧接着操作系统又发 `directoryChanged` → 不抑制就会再扫一遍，用户看到列表闪一下。
   标记要放**类级**（`DirStoreModel._self_change`）而非实例级：一个窗格重扫后经
   `dirChanged` 让其它窗格也 `refresh_dir`，而其它窗格的 watcher 收到的是同一次物理
   改动的通知，它们自己并未“改过”——只有共享标记能断掉这层放大。
3. **通知要防抖合并**。一次粘贴 N 个文件会连发 N 条通知，逐条重扫 = 列表反复清空
   重建；攒到待处理集里等 350ms 窗口结束后统一扫（`_flush_watch_events`）。
4. **监视器要进程级共享**（`_WatchHub`，以 `QApplication` 为父）。per-model watcher 看起来
   各管各的，但模型（窗格）可在任意时刻被 GC 销毁，而 Qt 在 Windows 上的目录监视
   共用一个全局线程，析构与在飞通知会竞态；hub 随应用生灭（时刻确定），模型只做
   登记/注销（弱引用计数，同一目录多窗格只占一个句柄）。
5. **只监视屏幕上看得见的那个目录**，切走即摘（`set_directory` 里 drop 旧 top / add 新
   top）。这不是偷工：监视“曾导航过的所有目录”会把句柄数和通知流量随会话无界堆
   积，实测全量测试的 access violation 触发率从 0/10 → 2/8 → **10/10**（必崩）；只监视
   当前目录（再叠加第 24、26 条）后回到 0/14。看不见的目录靠「快照 TTL 过期 + 导航回来
   重扫一次」保证新鲜（见第 25 条）。
6. **`addPath` / `removePath` 不在 `set_directory` 的调用栈里同步做**。只记下目标路径
   （`_watch_sync`），用 0ms 定时器推到事件循环顶层一次性 flush（`_flush_watch_ops`）。
   否则导航密集时（一个测试用例能连切十几个目录）会在同一轮事件里反复 add/remove，
   而 Windows 上目录监视共用一个全局线程 —— 登记抖动本身就是崩溃源（实测 2/12 → 1/12）。
   副作用：登记延迟一个事件循环周期，测试里得先 `qtbot.wait(20)` 再断言 `watched_directories()`。

**残余风险**（已知并接受）：抑制窗口 1.5s 内的**外部**改动会被一并当作应用内改动跳过；
不在屏上的本地目录最多陈旧 `_CACHE_TTL`（2s）后重扫。

**测试**：`tests/test_dir_model.py` 的“本地目录 watcher”一节（端到端、只监视本地、防抖、
自变更抑制、只监视当前目录、hub 共享与计数、句柄不累积、同一轮导航合并登记）、
`tests/test_pane_dir_store.py` 的
`test_pane_updates_on_external_change` 与 `test_external_change_syncs_panes_without_rescan_loop`。
依赖真文件系统通知的两条在通知不可用的机器上 **skip 而非假绿**。

### 24. 行信号会重入 `rowCount()`：一次加载白发两遍枚举

**现象**：同一个目录每次加载都枚举两次；加“到达即重扫”后全量测试的 access violation
从 1/8 涨到 9/10，而堆回枚举量就能重现。

**根因**：`beginInsertRows` / `endRemoveRows` 内部会回调 `rowCount(parent)`（实测，
`_start_load` 的调用栈就落在 `beginInsertRows` 里）。而 `rowCount` 里留着
「顶层节点未 loaded 且未 loading → 惰性 `_start_load`」的兼容写法；只要那一刻节点正处于
「已清 loading、未置 loaded」的过渡态，条件就成立 → 多起一次枚举，而且新枚举的 `gen`
会把正要采纳的结果算作过期。

**解决**：① `_on_entries_loaded` 把 `node.loading = False` 推至 `endInsertRows()` 之后；
② 一对 begin/end 用 `_rows_signal()` 上下文包住，`_rows_changing` 非零时 `rowCount` /
`canFetchMore` 不做惰性加载。

**测试**：`tests/test_dir_model.py::test_each_load_starts_exactly_one_enumeration`
（故意在等待期间反复查 `rowCount`）。改前实测 `_start_load` 调用次数翻倍。

### 25. 不要为了“像资源管理器”而在每次导航回来时重扫

**现象**：为补回“不监视非显示目录”的陈旧感，写成 `set_directory` 里“本地目录只要已加载
就 `_reload_top`”——列表行为正确，但崩溃率从 1/8 到 9/10，dump 全落在 `endInsertRows`。

**根因**：刚加载完的节点也会被立刻 removeRows + 重扫，枚举量和行信号量翻倍，
把本就存在的“销毁与投递竞态”从偶发推到必现（见 unsolved-issues 问题 13）。

**解决**：改成快照带时间戳（`DirNode.ts`）+ 本地/网络统一 TTL：过期才重扫，而且重扫
走 `beginResetModel` 前的 `_discard_node`（视图随 reset 看到空列表，只一趟 insertRows，
不再额外 removeRows）。

**测试**：`tests/test_dir_model.py::test_fresh_snapshot_is_not_rescanned_on_arrival`

### 26. 目录枚举不要用 `QThreadPool.globalInstance()`

**现象**：加 watcher 后偶发 access violation 的最后一种 dump：主线程在测试 teardown 的
`_process_events` 里，同时 **10 个线程全卡在 `enumerate_dir` / `_entry_hidden`**。

**根因**：全局池的并发数 = CPU 核数（本机 24）。目录枚举是“系统调用 + 造一堆 Python
条目对象 + 投回主线程”的活，并发放大后：① 结果投递与条目对象成倍砸回主线程；
② SMB 上几十路并发枚举互抢通道，比串行更慢（并发不是免费的，它只是把等待换成了争抢）。

**解决**：枚举走专用池 `dir_pool()`，`_ENUM_POOL_THREADS = 4`（一屏最多 4 个窗格，再多
无益）。该池必须被 `_pools_to_drain()` 覆盖（见第 21 条）。

**测试**：`tests/test_dir_model.py::test_enumeration_pool_is_capped`；`tests/test_pane_dir_store.py`、
`tests/test_shutdown_drain.py` 里的等待/排空均改指 `dir_pool()`（若哪天忘了切池，这几处会失败）。

### 27. 类级窗格注册表：要过滤死包装器，且注册必须放在构造完成之后

**现象**：全量测试某轮突然 22 个失败（而不是平时的 5 个），错误全部同一句：

```
core/main_window.py:569 create_menu_bar -> Pane.set_show_hidden(...)
core/pane.py:410        if pane.model is not None:
RuntimeError: wrapped C/C++ object of type Pane has been deleted
```

而同一个时刻的另一个（偶发的、早就见过的）现场：延迟建窗格的回调在
`Pane.init_ui` 中途抛 `RuntimeError: wrapped C/C++ object of type QVBoxLayout has been deleted`。

**根因**（两件事叠在一起才会炸成一片）：
1. 半途死掉的窗格仍然**已经在注册表里**：旧代码在 `super().__init__(parent)` 后立刻
   `Pane._instances.add(self)`，于是 `init_ui` 中途抛异常时，一个连 `model` 属性都没有的
   废窗格留到了 WeakSet 里。
2. `set_show_hidden` 在 `try` **外面**碰 `pane.model`。关键细节（实测）：sip 删除 C++ 部分
   时**不清空** `__dict__`，所以死窗格上读已有属性不报错；只有读一个**不存在**的属性时，
   查找落到 Qt 元对象上 → 报 `RuntimeError: ... Pane has been deleted`。因此 `pane_id`、
   `model`（已赋值过的）都探不出死活，**只有 `sip.isdeleted()` 能**。

而 `set_show_hidden` 是在**新建** MainWindow 的启动路径（`create_menu_bar`）上调的：一个
残留死窗格 → 每个后续建窗口的用例全挂（测试里是 17 项级联失败；生产里是“用过一段时间
后开新标签/新开窗口直接报错”）。

**解决**（两条都做，不只靠守卫）：
- `Pane.__init__` 把注册移到**最后一步**（`navigate_to` 之后）：半途死的窗格根本不会入册。
- 类级操作一律走 `Pane._live_instances()`（用 `sip.isdeleted` 过滤），不在各调用点散写
  判活；`set_show_hidden` / `_refresh_dir_everywhere` 都改成这个入口，并把属性访问放进 `try`。

**注意**：第 20 条说“不要用 `sip.isdeleted` 守卫”是针对**延后回调**（那个靠 Qt 父子关
系就能解决）。注册表迭代不同：WeakSet 只能反映 Python 侧引用，反映不了 C++ 侧已删，
这里 `sip.isdeleted` 是唯一可靠手段。

**测试**：`tests/test_pane_dir_store.py::test_dead_pane_does_not_break_global_pane_operations`
（直接造出“已删 + 无 `model` 属性”的注册表残留，并断言存活窗格仍被同步）、
`::test_pane_dying_mid_construction_is_not_registered`。两条都已回滚验证过：改前报的就是
上面那条 RuntimeError / 断言失败。

**写测试时的一个坑**（本条取证过程中踩到）：不要在 `init_ui` 中途把窗格拆坏来模拟
“半途死掉”（例如 mock 掉 `_setup_model`）—— 那会留下一个“子控件已删、父窗格还在”的
半成品子树，Qt 往它投递事件时就报 `wrapped C/C++ object of type FileListTreeView has been
deleted`，现场看起来像“另一个用例偶然挂了”。要测“构造未跑完就不该入册”，就在
**最后一步之前**抛（mock `navigate_to`），并给半成品一个显式父 `holder`、用例末尾
`sip.delete(holder)`，别把它留给 GC（时机不定，会干扰其他用例）。

### 28. 不要把 Qt 对象的生死交给分代 GC：握住引用 + `deleteLater`

**现象**：一堆“查不下去”的偶发故障共用一个根：某个窗格构造到一半，它自己的 C++ 部分
不见了（`Pane.init_ui` 报 `wrapped C/C++ object of type QVBoxLayout has been deleted`），
或直接 access violation。崩溃时刻在一行**纯 Python 语句**上（普通对象分配），与 Qt 调用
无关；`gc.disable()` 下同一用例组合 22/22 通过（完整取证见 unsolved-issues 问题 13）。

**根因**：`signal.connect(self.method)` 天然构成引用环（self → 子控件 → 接收者列表 →
绑定方法 → self），环只能等分代 GC，而 GC 会在**任意** Python 分配点执行。一个 Qt 对象
只要同时满足“sip 当作 Python 拥有”与“此刻 C++ 父指针为空”，它的包装器一旦被回收，
sip 就当场 `delete` C++ 对象，级联拆光子树；若那一刻有另一个窗口正在构造，拆的就是它
正在用的东西（Windows 下 `~QWidget` 还要 `DestroyWindow` → 重入消息派发，报错升级为 AV）。
典型制造这种状态的动作：`QTabWidget.removeTab`（把页内容的 C++ 父指针置空）。

**解决**：移除后先**握住 Python 引用**，再由 `deleteLater()` 在事件循环里确定性销毁：
```python
widget = self.tab_widget.widget(index)
self.tab_widget.removeTab(index)
self._closed_tabs = [w for w in self._closed_tabs if not sip.isdeleted(w)]
self._closed_tabs.append(widget)      # ← 关键：不握住引用，销毁时机就在 GC 手里
widget.hide()
widget.deleteLater()
```

**三个反直觉的关键点**（都是实测）：
1. **只 `widget.setParent(self)` 归还所有权拦不住** —— 试过，包装器被回收时 C++ 照旧被删。
2. **在“批量构造前主动 `gc.collect()`”不是修复，反而制造新故障** —— 主动回收会把“已该死
   但拖着没死”的对象集中删掉，其中就有即将被使用的宿主（同一个用例组合从 22 passed
   变成 20 passed + 2 failed：`Pane(parent=self)` 报 `QuadPaneWidget has been deleted`）。
   该做法已回退。**要消除的是“随时会被回收”这个状态，不是把回收调得更频繁。**
3. `QCoreApplication.processEvents()` **不**处理 deferred delete；要让 `deleteLater` 落地得显式
   `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)`（测试里需要）。

**测试边界同理**：`tests/conftest.py` 在每个用例结束时 `gc.collect()`，把“由 GC 决定的销毁”
集中到没有构造在飞的安全点（否则上一个用例的残环会在下一个用例中途被回收）。

**测试**：`tests/test_lifecycle.py::test_closed_tab_widget_outlives_its_python_wrapper`
（已回滚验证：去掉 `append` 那一行就在 `gc.collect()` 那一步报“随包装器一起被删”）、
`::test_delayed_pane_creation_on_dead_host_is_silent`（旧写法在 `Pane(parent=self)` 抛
`QuadPaneWidget has been deleted`，即生产侧的 AV 现场）。

---

### 29. 筛选只改“可见行”：别叠第二层代理，也别在过滤判断里碰磁盘

**背景**：新模型（`DirStoreModel`）把目录内容挂在 `Entry` 对象上，窗格已经有一个
`PaneSortProxyModel` 做排序。加“按名称/扩展名/日期/大小筛选”时，最顺手的写法是
再叠一层 `QSortFilterProxyModel`（旧 `widgets/filter_bar.py` 里就躺着这么一个未被引用的
`FilterProxyModel`，它依赖 `sourceModel().fileName(index)`，新模型根本没这个方法）。

**为何不这样写**：
1. **两层代理 = 两次索引映射**。本模型只有“一个顶层节点 + 条目”两层，视图/代理/源模型
   之间的 mapping 越长，错行、`internalPointer()` 拿到意外类型、选中恢复找不到行这些风险
   叠得越多。排序和过滤本来就是同一个视图层职责，合并进 `filterAcceptsRow` 即可。
2. **`filterAcceptsRow` 每轮重筛会对每一行都跑一遍**，在里面 `os.stat()`/`os.path.isdir()`
   等于把 SMB 目录的延迟按行数乘回来（大目录上万行 × 网络往返）。条目上的
   `size`/`mtime`/`is_dir` 在枚举时已经缓存，筛选必须只吃内存里的字段。
3. **筛选不得发行信号**。本仓崩溃率的主因是行信号量（见 `docs/unsolved-issues.md` 问题 13），
   而过滤只该改 `QAbstractItemView` 的 hidden 状态 —— `invalidateFilter()` 不增删行，
   正是想要的语义。因此“源模型 `rowCount` 在筛选前后不变”写进了测试（
   `tests/test_filter_bar.py::test_proxy_hides_rows_that_do_not_match`），防止哪天“优化”成重建模型。

**顺手一个易漏点**：超大图标视图（`ThumbnailView`）不走这个代理，它自己枚举。要么让它
接受同一个 `EntryFilter`（已做），要么会出现“列表筛过了、图标视图还是全量”的不一致。
它拿不到缓存属性时才用 `entry.stat()` 补，且只在条件真含 size/date 时（`EntryFilter.needs_stat`）。

**同一条约束也适用于 `lessThan`（而且更严格）**：一次排序要做 O(n log n) 次比较，
旧 `PaneSortProxyModel._is_dir()` 每次比较一个 `os.path.isdir(filePath)` —— “点一下列头
排序界面停一下”就是这么来的（SMB 上按比较次数乘网络延时）。现在排序与过滤一样只读
`Entry` 缓存属性，代理里**不存在**任何碰磁盘的代码路径（旧 `_is_dir()` 已删，
`tests/test_filter_bar.py::test_sorting_does_not_touch_the_filesystem` 把 `os.path.isdir`
换成计数器后断言一次排序也没调用过）。

### 30. “清除”必须无条件补发一次空条件

**现象**：筛选栏有 250ms 防抖。用户连续输入后马上点行内 ✕，旧写法是“清空文本，
等防抖定时器触发”，结果 `_last_query` 已是新值、和空串比较后认为“没变化”而不发信号
—— 输入框空了，列表还是筛过的状态（比“没筛”更难诊断，因为用户看见的就是“没筛”）。

**写法**：`clear_filter()` 先 `stop()` 防抖定时器，再清文本，最后 `_emit("", force=True)`；
`_emit(query, force=False)` 只有在 `force` 或“文本真变了”时发射。任何“手动清零”的入口
（Esc、右键菜单“清除筛选”）都走 `clear_filter()`，不要直接 `lineEdit.clear()`。

### 31. `Tab` 系快捷键必须用 QAction 抢在焦点导航前面

**现象**：标签页「Ctrl+Tab 循环切换」在没注册快捷键时看上去也已经能用 —— 按一下确实
换了页。实测（把 QAction 的键改成 `Ctrl+Alt+Tab` 后再真按 Ctrl+Tab）：`currentIndex()`
仍然 0 → 1，而 QAction **没被触发**。也就是说“看起来对了”，但走的是另一条路。

**机制**：`Tab` 是焦点导航键，控件不接就沿父链往上做 `focusNextChild`；焦点一落到
另一个标签页里的控件，`QStackedLayout`（`QTabWidget` 内部）会**跟着焦点换当前页**。
但这条路的换页是副作用：它按的是**整个窗口焦点链**的顺序，而不是标签页顺序 ——
实测焦点会停在工具栏某个 `QToolButton` 上；而一页里有 N 个可聚焦控件时，按 Ctrl+Tab
要 N 次才真的跳到下一页，其余几次只“在同一页里换控件焦点”（看起来就是“按了没反应”）。

**写法**：`Ctrl+Tab` / `Ctrl+Shift+Tab` 这类与焦点导航同键的快捷键，一定要挂成窗口作
用域的 QAction（本仓是文件菜单里 `on_next_tab`/`on_prev_tab` → `_cycle_tab(±1)`），让它
抢在键事件进入焦点导航之前。测试也不能只调 `on_next_tab()`（那测不到抢键），得用
`qtbot.keyClick` 真发一次 `Key_Tab + ControlModifier`，并**接住 `QAction.triggered` 计数**
断言确实是 QAction 干的（`tests/test_nav_shortcuts.py::test_ctrl_tab_key_press_reaches_the_action`）。

另两个约束：`QKeySequence` 在 **QtGui**（不在 QtCore，从 QtCore 导是 ImportError），且
不可哈希（进不了 set，比较用 `toString()`）；快捷键只对“活动窗口”生效，测试里先
`win.activateWindow()` + `processEvents()`。

### 32. 测试里发带修饰键的合成按键，会把修饰键态漏给后面的测试

**现象**：新加一个真按 `Ctrl+Tab` 的测试后，隔一个文件的
`test_pane_dir_store.py::test_refresh_preserves_selection` 开始挂 —— 它在**自己**
的 `assert` 第一行就失败（刚 `select()` 完，`selectedIndexes()` 就是空）。单独跑那个
文件又全绿；只看失败信息会去查选中恢复逻辑，方向完全错。

**机制**：`qtbot.keyClick(w, key, modifier)` 发的 press 与 release **都带着修饰键掩码**，
所以 `QApplication.keyboardModifiers()` 在整个测试结束后仍是 `ControlModifier`（真键盘
不会：物理松开时掩码为空）。而 `QAbstractItemView::setCurrentIndex()` 在没有按键事件时
会拿**全局** `keyboardModifiers()` 去算 `selectionCommand()` —— Ctrl 在场就按
“Ctrl+点击 = 切换选中”处理，于是把刚选上的那一行**取消**了。选中本来就没坏，
坏在测试之间的全局态。

**写法**：任何用带修饰键的合成按键的测试，收尾补一次不带修饰键的同一个键把态归零，
并断言归零成功（不然下次又没人发现）：
```python
qtbot.keyClick(tree, Qt.Key.Key_Tab, Qt.ControlModifier)
...
qtbot.keyClick(tree, Qt.Key.Key_Control)          # 抹回 NoModifier
assert QApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier
```
适用范围：`qtbot.keyClick` / `QTest.keyClick` 全都算（它们走同一套合成事件）；
`keyClick` 不带修饰键时无此问题。排查这类“隔文件挂”的线索：先打
`QApplication.keyboardModifiers()`，再怀疑业务逻辑。

### 33. ProgID 在 `HKCR\<progid>` 的默认值是**文档类型描述**，不是程序名

**现象**：给「打开方式」列候选时，若拿 `HKCR\.txt` → ProgID → `HKCR\<progid>` 的默认值
当显示名，本机装了三个能开 `.txt` 的 IDE 就会显示三个同名项（实测都叫
“Text Source File”）—— 用户看到三个一模一样的选项，等于没有选项。AppX 安装
（UWP）的 ProgID 更糟：显示名是一串哈希。

**写法**（`core/open_with.py::_win_name_for`）：只认 `<progid>\Application\ApplicationName`，
并且该值本身还可能是路径或 MUI 引用（`@C:\...,-1234`），这两种都**不能**直接显示，
回退到 exe 文件名（`_exe_stem`）。MRU 那一路没有 ProgID，用 `App Paths\<exe>` 的
`ApplicationName`，否则用 exe 名去扩展名 —— 特意不用解析出的完整路径里的文件名：
NTFS 不区分大小写，同一个程序会从不同入口分别报成 `code` 与 `Code`。

同类坑（一并记在此）：**兜底候选必须分文件类型**。无脑补“记事本/画图/Word/VLC”
会让 `.txt` 挂上画图与 Word，比资源管理器多一堆不相干项；现在按大类查
`_WINDOWS_FALLBACK`，且**只在注册表那条链给的候选少于 5 项时**才补。

另三条硬约束（右键菜单的实现前提，改动时别退回去）：候选**只在子菜单 `aboutToShow`
时枚举**（构造菜单就扫注册表是纯浪费）；结果按扩展名做 TTL 缓存（300s）；枚举
任何一步失败只准“少一项候选”，绝不向外抛 —— 右键菜单不能弹不出来。
分别由 `tests/test_open_with.py` 的 `test_submenu_defers_enumeration_until_about_to_show`、
`test_list_apps_caches_per_extension_until_ttl_expires`、
`test_enumeration_failure_keeps_the_menu_usable` 盯住。

### 34. 测试里手工造的父 `QMenu` / 父 widget 一返回就被 GC，子对象先没

**现象**：写“建一个菜单 → 取它的子菜单 → 断言子菜单里的项”的测试，如果辅助函数只
`return submenu`，会在下一行读到 `RuntimeError: wrapped C/C++ object of type QMenu has
been deleted`。子菜单没被删过，是它的**父菜单**（一个函数局部变量）在辅助函数返回时
被回收，Qt 的父子关系连带删掉了整个子树。

**写法**：辅助函数把父对象一并返回，让调用方的栈帧握住它（`menu, submenu, _ = _fill(...)`）；
或让夹具持有。这与第 28 条是同族问题（Qt 对象的销毁时机由 Python 引用决定），区别在
这里是“**父**没了连带删子”，不是“子的 deleteLater 落进 GC”。

### 35. 两种匹配语义（glob / 正则）写在两处，就会有一处默默骗人

**现象**：高级搜索的文件名框 placeholder 教用户写 `*.txt`，而非正则分支的实现是把输入
`re.escape` 后 `search` —— 于是 `*.txt` 被当成“名字里含字面 `*.txt`”（转义后 `*\.`），
**按提示写必然 0 结果**，与“这个目录真的没文件”看起来一模一样。列表筛选栏早就把
`*.log` 做成了整名通配匹配，两处各写一份就各演化一套。

**写法**：全仓只留一份 `widgets/filter_bar.py::glob_to_regex`（`*`→`.*`、`?`→`.`、其余
`re.escape`、锚定整名、默认不区分大小写），高级搜索由 `build_name_matcher` 调它。
语义分工写在那个函数的 docstring 里：勾了正则 → `search`（局部匹配，旧行为）；
含 `*`/`?` 且未勾正则 → 整名通配；否则 → 名称包含。

另两条同类硬约束（改动时别退回去）：**匹配器在遍历循环外编译一次**，不在每个文件上
重编（`build_name_matcher` 返回 `bool(name)` 闭包）；**正则写错必须在开始搜索时就
报错**（`collect_params` 先试编译），不能带着坏条件去扫盘然后返回 0。
分别由 `tests/test_saved_search.py` 的 `test_glob_pattern_matches_by_extension`、
`test_worker_finds_files_with_glob`、`test_collect_params_validates` 盯住。

### 36. 把界面换算后的值存进配置：往返要双向可逆，表示不了要说

**现象**（设计阶段发现，未上线就算掉）：大小条件是“数值 spin × 单位下拉”，存字节数就
必须能反算回去 —— 而两个输入框**共用一个**单位下拉。若反算时给每个框各选一个“能
整除的最大单位”，min=1 KB 与 max=1 MB 会被填回 KB / MB 两种单位，再采集时按下拉里
最后那个单位统一乘回去 → 1 KB 变成 1024 MB。不报错、不丢字段，只是搜不到东西。

**写法**（`widgets/advanced_search.py`）：① 存的是**真正喂给 worker 的那份 params**
（字节数、归一化后的扩展名），不是界面上的 `1`；② 开始搜索与保存共用同一个
`collect_params`，两边不可能不一致；③ 反算时选“能让两者都整除且不超 spin 上限的**最大**
单位”（`_restore_sizes`），整除不了就退到放得下的最小单位并**返回一句失真说明**，由
载入槽拼进状态栏 —— 静默把 1 字节归到 0（＝无限制）比不改还糟。

测试的核心不变式就是这一条：`apply_params → collect_params` 与原值逐项相等
（`test_round_trip_params_to_widgets_and_back`，含“一侧无限制”与“上限边界 99999 KB”），
失真路径单独由 `test_unrepresentable_sizes_say_so_instead_of_quietly_changing` 盯。
另：`FileAssociations` 与 `SavedSearchStore` 的配置目录规则收拢到 `config/paths.py`，
再加一类 JSON 存储不再多算一份路径。

### 37. 树形用户数据：改动一律按 id，结构规则放在 Qt 之外

**背景**：收藏夹旧版是“一个平铺 list + `list_widget.currentRow()` 当下标”。在中间插一个
分组之后行号就整体错位，于是“改这条”变成“改那条”、“删这条”带走别的项 —— 而它只在
树上长到两层、并且能被拖拽重排时才暴露，日常难发现。

**写法**（`config/bookmarks.py` + `widgets/bookmark_sidebar.py`）：
1. **节点只用 id 引用**（树项在 `UserRole` 里存 id，行号不参与任何计算）；
2. **规则全在模型层**（成环、层数、条数上限、老格式迁移、坏记录逐条降级），UI 只把动作
   翻给 store —— Qt 无关，因而可不用事件循环直接测；
3. `can_place(node, parent) -> 空串|理由` 与 `move()` 共用一个函数：拖拽时 Qt 只能回 bool
   （不能抛），而菜单与错误文案要同一套理由，不能两边各写一遍；
4. **子树高度参与层数判定**：`depth_of(parent) + height_of(node) > MAX_DEPTH`。只按被挪
   节点自身算层，就能把一棵三层子树挂到第六层下面；
5. 迁移只在读时做，**改过才写盘**（`store.migrated`）：转换有 bug 时用户原文件还在；
6. 文件里读来的 id 一律不信任（可能重复 / 手改过），载入时从 1 重编；不校验 path 是否
   存在（存下来之后目录才消失是正常事），但**双击不可达必须说话**（旧版静默无响应，
   用户只当侧边栏坏了）。

**一个当场踩到的写法错**：导入去重时递归地“往正在遍历的 `node["children"]` 里 append”
→ 分组子项翻倍，而且被判重复的那条仍留在列表里且没有 id → 存盘 `KeyError: 'id'`。
必须**返回新列表**再由调用方赋值回去（`_merge` 返 `(kept, added, skipped)`）。

### 38. PyQt6 树控件拖放：六个实测事实（不核实就会写出不存在的 API）

1. `canDropMimeData(data, action, position, index, parent)` 的 **`parent` 是 `QModelIndex`**
   不是 `QTreeWidgetItem`。直接拿它 `data(0, role)` 会 TypeError（`QModelIndex.data` 只接
   一个参数）—— 要 `itemFromIndex()` 过一道。
2. `QTreeWidget` 上**没有** `setDropActions` / `setSupportedDropActions`（写了就是
   AttributeError）。默认 `supportedDropActions()` 就是 `Copy|Move`；“能接哪些拖放”只能在
   `canDropMimeData` 里判（那里才能拿到 mime 内容）。
3. `DragDropMode.InternalMove` **不接外部拖放**。要“从文件列表拖一个目录进来收藏”就得用
   `DragDrop`，并在 `dropEvent` 里自己分内部/外部两条路（内部才 `super().dropEvent()`）。
4. **同树内部移动到底发哪些信号不该赌**：实测 `takeTopLevelItem` + `insertTopLevelItem`
   不发 `rowsMoved`；`model().moveRow()` 会被我们自己的 `canDropMimeData` 拒（因为
   `_dragging_internally` 为假）；直接调 `dropMimeData` 会把移动做成**复制**。所以落地钩子
   接两处（`rowsMoved` + `dropEvent` 结尾）并对“顺序没变”早退；对不上账（项数不等 / 未知
   id / 重复 id）就**按模型重画且不写盘**，宁可弹回也不把残缺顺序写进文件。
5. `QTreeWidgetItem` **没有 `setParent`**（Qt 6）：改挂只能 `removeChild` + `addChild`。
6. `QUrl.toLocalFile()` 在 Windows 上返回**正斜杠**路径（`C:/x/y`），与窗格/地址栏拿到的
   形状不一致；入库前 `os.path.normpath` 一下（否则同一个目录两种写法，去重也判不出来）。

**另一个现场错**：在 `itemCollapsed` 槽里 `save + refresh_tree()`（=`tree.clear()`）→ Qt 此刻
正在遍历行做展开，拆自己的模型是未定义行为，实测会把调用方刚拿到的 item 包装器删掉
（`wrapped C/C++ object of type QTreeWidgetItem has been deleted`）。展开/折叠这种“树已经
是对的”的改动**只存盘不重画**（`_save_only` 与 `_commit` 分开）。

### 39. 时间相关用例别从 `time.time()` 起算；测持久化组件必须注入临时目录

**现象**：`date:昨天` 的筛选用例在凌晨必红（实测 01:2x）：“1.2 天前”从当前时刻减，
凌晨跑会**跨两个午夜** → 落在前天而不是昨天（那本来就是一个合法输入，不该测得随机）。
同一类：“0.5 天前”算本周，在周一上午属于上周。

**写法**：把参考时刻定在**本地中午**（`datetime.now().replace(hour=12, ...)`）再往前减天，
并用 `timedelta` 做日历天算术（而不是减 `N * 86400` 秒）。实现侧同理：一个日历天在跨夏令
时的那天不等于 24 小时，区间的右界要取“今天零点”而不是 `lo + 86400`。

**同一个陷阱的第二种形状（2026-09-17 实测）**：中午参考系定好了，但把时刻写在
`@pytest.mark.parametrize` 的参数表里 —— 参数表在**收集阶段**就求值，而被测的
`date:今天` 在**执行时**才读表。一次跑只要跨过午夜（23:5x 收集、00:0x 执行）就
“今天/昨天”整体错一天，三条一起红（本仓连撞三次：构建到 23:1x 后跑全量）。
做法：参数表里只放**构造器**（`lambda: _local_noon(1.2)` 或直接传函数），时刻在用例
体内算；同理不要在参数表里调任何读时钟、读盘、读环境变量的函数。

**同时修掉的卫生问题**：旧的 `TestBookmarkSidebar` 直接 `BookmarkSidebar()`（不注入 store），
每个用例都会读写开发机 **真实用户配置**里的 bookmarks.json（测“默认四条”时还把它们存
进了用户盘）。新增任何写盘的组件（收藏 / 已保存搜索 / 文件关联）都必须能注入配置目录，
并在用例里注临时目录 + 钉一句“没碰真实目录”。

### 40. PyQt6 的两个静默失败面：不存在的枚举复数名、拿不到的槽返回值

两个都是实测，共同点是**不报错、只是默默不做**，所以可以潜伏很多个版本：

1. **`Qt.TextInteractionFlags`（复数）不存在**，正确名是 `Qt.TextInteractionFlag`（单数）。
   写错不是“样式不对”，是 `FileProgressDialog()` 构造当场 `AttributeError`。真正让事情
   变糟的是调用方：窗格把建框整段 `try/except Exception` + `logger.debug` 包着 → 进度
   对话框（含全仓唯一的取消入口）**从诞生起到 v1.9.010 从来没出现过**，日志里连一条
   痕迹都没有。规矩：为“建 UI 控件”写 `except` 时，失败至少 `warning` 级；并且要有用例
   断言控件**真的建起来了**（`assert runner._dlg is not None`），而不是只测“调了不抛”。
   同理适用于本仓其它枚举：Qt 6 的枚举带命名空间且**只有单数名**（`Qt.AlignmentFlag`、
   `QPalette.ColorRole`），凭 Qt 5 印象写的复数形（`Qt.AlignmentFlags`）都是 AttributeError。

2. **`QMetaObject.invokeMethod(..., BlockingQueuedConnection, Q_ARG(...))` 拿不到槽的
   返回值**（PyQt6 实测永远回 `None`）。旧代码拿它的返回值当“用户在冲突框里选了什么”，
   而 `FileOperations._resolve_conflict` 把“不在已知选项里”的值当异常处理 → 回退
   `keep_both` → **用户点的「替换」被静默丢掉，文件被改名了**。跨线程要答案的正确形状：
   一个共享对象（`_ConflictAsk(info)`）+ Blocking 的同步保证，槽把答案**写回对象**；
   并且必须带两个防护：① **主线程调用时直调**（`self.thread() is QThread.currentThread()`），
   否则 Blocking 就是主线程等主线程 → 整个应用冻死；② 答案过**白名单**，空串/脏值
   一律降级为最安全的选项（这里是 `keep_both`，不是 `replace`）。

### 41. offscreen 测 Qt：四个会反复坑人的地方

本节新写了两个测试文件（runner + 搜索结果），四条都是当场踩到的：

1. **真模态框会把整个会话卡死**：offscreen 下 `QMessageBox.question` / `QMenu.exec` 真的
   弹一个没人看得见的框 → pytest 直接没输出直到超时。每个测对话框的模块加一个 autouse
   夹具，把本文件会碰到的模态入口全替成 `raise AssertionError("用例没有替掉这个对话框")` ——
   宁可当场红也不能等，用例需要哪个再自己覆盖那一个。
2. **`qtbot.addWidget()` 与 `sip.delete()` 不能用在同一个对象上**：qtbot 收尾要 `close()`，
   对已销毁对象报错还会污染下一句（“previous item was not torn down properly”）。测“宿主
   先没、后台还在投递”的用例不注册 qtbot，自己造裸 `QWidget`。
3. **`qtbot.waitUntil` 的回调只能返 None/True/False**：写 `lambda: runner.done_results`
   直接 `ValueError`（返了个 `[]`），要 `lambda: bool(...)`。
4. **`QTreeWidget.selectedItems()` 返的是点选顺序，不是显示顺序**。两个后果：要按显示
   顺序处理（删除确认框列前 5 个名字）必须自己 `sort(key=tree.indexOfTopLevelItem)`；
   而测排序的夹具得**故意按乱序点选**，再钉一句“Qt 给的就是乱序”，否则用例在断言一
   个自己已经排好的东西，什么也没盯住。

另：控件没 `show()` 时 `visualItemRect(item)` 算不出几何 → 测右键菜单不要造真实坐标，
直接把 `itemAt` 换掉，只测“压在选区内 / 选区外 / 空行”三种落点。

### 42. 手工构造 `QDropEvent` 的三个坑（拖拽默认动作那一节当场踩到）

1. **`setDropAction()` 是空操作**：写进去再 `dropAction()` 读回来永远是构造时
   那个值（三种初始动作都试过，全部不生效）。所以“把我们选的动作回写给源端”
   这种写法在 PyQt6 下会静默无效 —— 动作只能靠函数返回值传给调用方，别指望
   事件对象能携带它。已钉成用例 `test_set_drop_action_does_not_stick_in_pyqt6`。
2. **构造参数是单个 `Qt.DropAction`，不是集合**：传 `CopyAction | MoveAction`（=3）
   会被削成 `CopyAction`，于是“源端允许两种动作”这种情形根本造不出来，用例
   会以为自己测过了、其实测的是“只允许复制”。`possibleActions()` 在 C++ 里由
   `QDragManager` 填、构造不出来 → 用实例属性遮蔽这个方法注入（Python 属性查找
   优先于类型上的方法）。顺带记住两个枚举的分工：`possibleActions()` 是源端
   **允许**哪些（硬约束，不许 move 就不能 move），`proposedAction()` 是源端
   **建议**哪一个。
3. **`QDropEvent` 不接管 `QMimeData` 的生命周期**：把函数返回的临时 mime 直接传
   进构造函数，下一句 `event.mimeData()` 就是 `Windows fatal exception: access
   violation`（真拖拽里 mime 由 `QDrag` 持有，手工造事件时没人持有）。必须
   `evt._mime = mime` 留个引用，否则整个 pytest 会话当场没了、连 traceback 都没有。

另：拿“不存在的 UNC 路径”测 UNC 判据是**假故事** —— 它会因为 `os.stat` 抛
`OSError` 而通过，把判据删掉用例也不会红。要么让假路径的 `os.stat` 也能成功，
要么这判据就没被盯住（变异验证时这条就是存活的，改完才杀掉）。

### 43. 「是不是慢位置」只能有一份答案，而且必须两边都有（判据去 `nt` 化）

**现象**：网络/慢盘的那套保守策略（不挂 watcher、重复导航强制重扫、删除前说
“这里没有回收站”）在 Linux 上全部不生效 —— 不是因为 Linux 代码缺失，而是入口
写成了 `if os.name != 'nt': return False`。同一个问题当时还有**两份实现**（
`file_operations._is_network_path` 与 `DirStoreModel._is_network`），两份都是这句，
所以“修一处”永远不够。

**四个坑（缺一就会写出一套测不到的判据）**：

1. **最长前缀匹配必须拼边界**：`path.startswith(mount_point)` 会把 `/mnt/nas2/x`
   认成 `/mnt/nas` 的子路径（一个误判就把本地盘当远端，或反过来）。要
   `path == mp or path.startswith(mp + "/")`，并且根挂载 `/` 单独处理。
   测的时候**别只留一个名字相近的条目**：两条都在表里时“最长前缀赢”会替边界
   检查兜底，删掉 `+ "/"` 变异也不会红（本仓第一轮变异就是这条存活）。
2. **挂载表里 `\040` 是空格**：不解码的话，带空格的挂载点永远匹配不上（用
   **原始字符串**写测试数据，否则 Python 会先把 `\040` 换成真空格，测的就不是
   解析器而是它自己）。
3. **同一挂载点挂两次取最后一次**：后挂的遮蔽先挂的，`dict[k] = v` 而不是
   `setdefault`；顺序反了就会拿被遮蔽的那个类型回答。
4. **判据不做 `realpath`**：解析符号链接要对路径每一级 `readlink`，而这条判据恰恰
   用在可能已经卡住的远端路径上。代价是“经由符号链接访问的挂载点”会被判成本地
   —— 这是**写下来的取舍**，不是没想到。同理：失败一律返回 `False`（按本地处理），
   判据自己出错时不该把导航或删除一起拖失败。

**写测试的收获**：把 POSIX 判据拆成三个纯函数（`parse_mount_table` /
`longest_matching_mount` / `posix_is_remote`）后，Linux 的整张判定矩阵在 **Windows
主机上就能测满**（喂一份真的 `/proc/mounts` 文本进去），不再需要“Linux 分支
本机执行 0 次”。而“只在 nt 分类”这类门控，在 Windows 主机上永远验不到它被拆掉
—— 得在用例里 `monkeypatch.setattr(mod.os, "name", "posix")` 把宿主也当成 POSIX。

### 44. app 级全局状态泄漏给下一个用例，会伪装成“产品随机崩溃”

**现象**：Linux 真机（linux230 / Ubuntu 24.04）上 `pytest tests/test_m4_theme.py -q`
稳定段错误（基线 8/10，本轮改动后测得 **12/12**），栈落在 `Pane.init_ui` /
`_setup_model`，调用者是 `_create_remaining_panes`（250ms 延迟建窗格），而且**崩点会
漂移**（一次在 `addWidget`，一次在 `_setup_model`）。同一类现场在 Windows 上只表现为
偶发 access violation，所以一直没能定位。

**A/B 数据**（每格单跑 `test_m4_theme.py` 12 次，命令行完全一致）：

| 变体 | 崩率 |
| --- | --- |
| 现状（apt Qt 6.4.2 / PyQt 6.6.1） | 12/12 |
| 换成发布用的 PyQt 6.9.1 / Qt 6.9.2 | 12/12（**不是旧 Qt 的 bug**） |
| 先兜住 `Pane.eventFilter` 抛进 C++ 的 `RuntimeError` | 11/12（**因果假设当场被否**） |
| 窗格改在构造函数里同步创建（不延迟） | **0/12** |
| 延迟改 0ms（仍走定时器） | 12/12（载体是“从定时器回调里建树”，不是 250ms 跨过用例边界） |
| conftest 在每个用例边界还原 app 级 stylesheet/font | host 1/12、release Qt 3/12；**整场全量 4 次 0 崩** |

**真凶在测试里**：`TestThemeManager.test_apply_theme` 把 qdarkstyle `setStyleSheet` 到
`QApplication` 上就不管了，之后每个用例都在“样式表缓存里挂着已销毁控件”的状态下
建窗格树。修法是测试侧的（`tests/conftest.py` 的 `_reap_top_level_widgets` 现在顺手
还原 stylesheet/font）；产品的 250ms 延迟建窗格**保留不改**：真机
`QT_QPA_PLATFORM=offscreen python main.py` 跑 10s × 3 次全部正常，日志里
`延迟创建 pane2-4: 476.3ms` 正常完成 —— 先确认产品在真实环境下是否真坏，再决定要不要
改产品代码。

**四条可复用的教训**：

1. `skipif sys.platform == "win32"` 的用例在 Windows 开发机上**一次都不会执行**。
   本仓新加的那条 open_with Linux 用例就是带着一条写错的断言上机才发现的（4 个
   desktop 候选却断言 `["desktop", "builtin"]`）。Linux-only 用例必须在真机上跑一遍才算完。
2. 崩点在别的对象上时，**先拿崩率再下因果结论**：`eventFilter` 里那个 `RuntimeError`
   是真的、也确实该兜（异常不该逃进 C++ 派发栈），但它不是那次段错误的原因。
   防护仍然保留，并用结构守卫用例钉住“所有 `eventFilter` 必须已包装”
   （`tests/test_lifecycle.py`）—— 因为崩点会漂，逐条盯住不现实。
3. 拿“插打印”排查时记得 pytest 默认 `--capture=fd` 会吞掉**通过用例**的 stderr；要么
   加 `-s`，否则打印白打（探针变体一度显示 0/12，其实是打印拖慢时序造成的 Heisenbug）。
4. `gdb` / `-v` / 插打印都会把 250ms 定时器推到别的事件批次里，**观测工具本身改变复现
   率**；所以崩率必须在同一条命令行下反复跑。宿主的 apport 虽然有 crash 文件，但
   `ulimit -c` 为 0、`StacktraceTop` 为空，想拿 C++ 栈得先解决核心转储与符号。

### 45. 崩溃日志写不了，会让应用“启动即死”（安全网不能当扳机）

**现象**（linux230 实测）：Linux 产物在 `--version` / `--info` 都正常的情况下，一旦真起
GUI 就 exit 1，栈在 `main.py: install_signal_handlers`：
`PermissionError: [Errno 13] ... releases/pan4dex_crash.log` —— 因为 `releases/` 是 docker
以 root 身份建的。同一个二进制拷到 `/opt/pan4dex/`（root 拥有，系统级安装的常规位置）
就是**每次启动都死**，而且用户在启动器上只会看到“双击没反应”。Windows 装进
`Program Files` 是同一件事，只是开发机一直把 exe 放在自己可写的 `releases/` 里，所以躲过了。

**根因**：三处写日志的代码（`write_crash_log`、`excepthook`、`install_signal_handlers`）各自
硬编码“exe 同级目录”，而 `install_signal_handlers` 那处没包异常 —— 它在 `main()` 里比窗口
创建还早，于是“能不能写崩溃日志”成了“能不能启动”。

**写法**（`main.py: _crash_log_candidates` / `resolve_crash_log_path`）：

1. 候选按优先级：exe 同级（历史约定，文档与发布流程都按 `releases/pan4dex_crash.log` 找）
   → 用户缓存目录（Windows `%LOCALAPPDATA%\pan4dex`、POSIX `$XDG_CACHE_HOME`/`~/.cache`）
   → 临时目录；取**第一个能写的**，解析结果缓存下来给三处共用（否则三个写入点各写一个文件）。
2. 探测用 `'a'` 而不是 `'w'`：`'w'` 会在“只是看看能不能写”的阶段就把上一次的崩溃现场清空。
3. `install_signal_handlers` 全包 `OSError`：一个落点都写不了时 `faulthandler.enable()` 退到
   stderr，**不抛**。另外要自己握住文件句柄（`_CRASH_LOG_FH`）：faulthandler 不接管生命
   周期，句柄被 GC 关掉之后段错误就无处可写了。

**写测试的收获**：只断言“不抛异常”不够 —— `install_signal_handlers` 自己包了 `OSError`，
哪怕退路完全失效它也“不抛”，但那时用户一个字都拿不到，与没修一样。必须再钉一条
“日志真的落在某个文件里、且 faulthandler 接的就是那个文件”
（`tests/test_crash_log_path.py::test_signal_handlers_log_still_lands_somewhere`）。变异验证：
把“逐候选试探”删掉（直接返第一个）时，这两条一起红；而光有“不抛”那条不会红。
跨平台的“写不了”用普通文件当父目录（`tmp/blocker.bin/sub/x.log`）造，比 `chmod` 可靠
（Windows 上 chmod 不拦写）；真只读目录那条用 `0o500` 复刻，只在 POSIX 跑。

**同一道安全网上的第二个坑（顺着这条线再查出来的）**：三处写入点全都用 `'w'` 打开，
而 `install_signal_handlers` 在**每次成功启动**时都会跑 —— 于是上一次的崩溃现场在用户
“崩了→再双击一次试试”的第二个动作里就被截成 0 字节。这恰好解释了我们追偶发段错误时
反复遇到的现象：“crash 文件在，内容是空的”。现在：

- 三处一律追加（`_crash_log_for_append()`），启动时写一行 `=== Pan4dex <ver> 启动于 <时间> ===`
  作为分段标记（没它就无法区分哪一段是哪次运行留下的）；
- 超过 `_CRASH_LOG_MAX_BYTES`（256KB）才先清空一次，不让它无限增长；
- `setup_logging()`（在 `import main` 时就跑，比 `main()` 还早）也按同样标准包了：
  文件日志写不了（HOME 未设 / 配置目录只读 / 磁盘满）就只退成“没文件日志”，
  往 stderr 打一句降级提示，不再 `makedirs` 一抛就是“双击没反应”。

这类代码的判据只有一条：**它是用来记录失败的，所以它自己不准成为失败。**

### 46. Linux 发布链路：三条只在真机出包时才暴露的坑

这一节的三条全部来自“真的跑一次 `docker build` + 真的跑一次产物”，读代码看不出来：

1. **`--add-data` 指向不入库的目录，干净检出上必失败**。`/resources/tools/` 被 `.gitignore`
   排除（二进制不入库），而 PyInstaller 6 对缺失的 `--add-data` 源是 `ERROR ... exit 1`；
   写得死的四条让 Linux 构建在新克隆上根本过不去。**同一件事在 spec 路线里却是另一样**：
   `Analysis(datas=[...])` 里缺目录是静默跳过（所以 `pan4dex.spec` 多年“能跑”）。
   写法：存在才带，缺工具时报一句“本包不含 X，该能力依赖系统安装”（exiftool/7z 代码里
   本来就是“系统优先、应用内兜底”），但图标缺了就是硬错（源码树不完整）。
2. **`bash -c "... $VAR ..."` 会把变量在宿主侧先展开**。把资源清单从宿主传进容器时，
   `$DATA_ARGS` 是个数组，不加花括号只展开为第 0 个元素 `--add-data`，于是 `main.py` 被
   当成 `--add-data` 的值吞掉；PyInstaller 只报 “Wrong syntax, should be --add-data=SOURCE:DEST”，
   **完全不提真正的错处**（参数在宿主侧就错了一个字）。同族：`for x in "a"⟨换行⟩"b"; do` 是
   语法错 —— `for` 的 in 列表里换行就是结束符，多行字面量必须用数组。
3. **镜像不可重建：bullseye 的 LTS 刚结束**。`deb.debian.org` 上的 `bullseye-security`
   归档已被搬走，Dockerfile 原样的 `apt-get update` 会拿到一堆 `+deb11uNN` 的 404（exit 100）。
   改法：换 `archive.debian.org`、删掉 security 源那一行、`-o Acquire::Check-Valid-Until=false`
   （EOL 发行版没有 security 通道，这是“还要兼容旧 glibc 目标机”的代价，不是能在这层修好的）。

**方法论**：“镜像存在”不等于“Dockerfile 能构建”。构建脚本里的“镜像已存在就跳过构建”
正好把这个坏状态藏住了 —— 只要不主动 `docker rmi`，没人会知道它早就建不出来了。
所以验证发布链路必须至少跑一次 `docker build`（或者显式打个新 tag）。

### 47. 快捷键的落点不能只认 `_active_pane`：Windows 的首屏焦点把它掩盖了很多年

`MainWindow._active_pane` 由 `on_pane_activated()`（窗格**真的拿到焦点**）写入，不是「当前
该操作哪个窗格」。于是 `if self._active_pane:` 这种写法把十几个入口（Ctrl+L / Delete / F2 /
F5 / Ctrl+C·X·V / Ctrl+A / 后退·前进·上级 / 新建 / 目录树与收藏夹点击）全挂在了一个**只在
特定时机才非空**的变量上：程序刚起来、用户一次都还没点过窗格的那段时间里，这些快捷键
一个都不起作用 —— 而且**无提示、无日志**，看上去和“根本没绑快捷键”一模一样。

- **为什么 Windows 上多年看不出来**：首屏焦点正好落在 pane1 里，`_active_pane` 一启动就有值。
  Linux/X11（至少 xrdp + Xfce 这套）初始焦点不在窗格里，一上来就是 None —— v1.9.016 真机
  GUI 验收第一次浏览目录就撞上了，当时第一反应是“xdotool 没把按键送进来”，直到发现 11–15 号
  截图与基线**字节数完全相同**才意识到程序里真没发生任何事
- **落点规则只有一份**：`target_pane()` = 优先**最后激活且未销毁**的窗格，否则退回当前标签页
  默认窗格。两个方向不能翻：先默认后激活的话，焦点在预览面板/终端上按 Delete 会删错窗格
- 同一个坑已经踩过一次：`current_pane()` 的 docstring 写的就是这件事，但只有搜索对话框用了它。
  **一个已经写下来的规则，如果没有入口强制大家走它，就等于没有** —— 新代码继续抄旧写法
- 测这类“默认落点”必须把「从未激活过」当成一个独立用例（直接构造 `MainWindow`、不点任何东西
  就调 `on_xxx()`），只测“激活 pane2 后作用于 pane2”是抓不到的

### 48. X11 下窗口归类只认 `StartupWMClass`，而它等于 `applicationName()`、不是产物名

Qt 在 X11 上写的 `WM_CLASS` 是 `(argv[0] 的 basename, applicationName())`，桌面环境拿
`.desktop` 的 `StartupWMClass` 去比**第二项**（`res_class`）。于是两条约定同时成立：

1. 匹配键**区分大小写**，必须与 `APP_NAME` 同源（写小写 `pan4dex` 而应用名是 `Pan4dex` → 永远对不上）
2. 拿产物名当匹配键每发布一次就失效（冻结产物叫 `pan4dex-1.9.016-linux`）；也不能靠 `res_name`，
   那是第一条里变的项

不匹配的后果很安静：图标不分组、点应用菜单又起一个实例，没有任何报错。取证只要两条命令：
`xprop -id <win> WM_CLASS` 与 `grep StartupWMClass ~/.local/share/applications/pan4dex.desktop`，
**亲眼对一下**（本仓长期“以为这条已验证”）。

附带的 `.desktop` 坑：仓库里存 LF，但从 Windows 工作树拷过去的副本带 CRLF，解析时 `\r` 会连在
值上（`StartupWMClass` 匹配不上、部分桌面环境直接拒收文件）；安装脚本里加 `tr -d '\r'`。反过来，
**测试不能断“工作树文件无 CR”**（那测的是 checkout 方式，`core.autocrlf` 下必红）。

真机驱动 GUI 的两条取证经验（同属这类“不亲自跑就不知道”）：

- `xdotool getwindowgeometry` 对 reparented 窗口给的是**相对父框架**的坐标，不能用来推绝对
  落点；窗口每次启动位置又不同。开上下文菜单用 `key Menu`（坐标无关）、菜单项用方向键 +
  Return，比像素点击可靠得多
- 模态对话框（`dialog.exec()`）会吞掉之后**所有**按键 —— 验收脚本每一步都要显式 Escape/关闭
  再确认界面回到了预期状态，否则后面的结论全是假的
- 取证命令自己也会造假信号：`pytest -q | tail -4` 在 nohup 重定向下会把**汇总行整条吞掉**
  （只剩点号，退出码也丢），看起来像“跑完但没结果”，实际什么结论都没拿到。必须
  `pytest ... > file 2>&1; echo RC=$?` 再读文件 —— 带管道的“只留几行尾”适合看日志，不适合取证
  （同一类：`grep -c pat f || echo 0` 在 grep 命中 0 时会输出两行）

### 49. `WindowShortcut` 会抢走文本控件的功能键，而 `focusWidget()` 对可编辑 combo 报的是 combo

两件事合在一起，花了三轮验收才拆开（v1.9.017）：

**一、菜单 QAction 的快捷键默认 `shortcutContext = WindowShortcut`**：只要焦点在本窗口内，
快捷键就**先于**焦点控件触发，除非控件自己用 `ShortcutOverride` 把键抢回去。Qt 的编辑控件
只抢标准编辑键，实测边界（Windows / Qt 6.11，写探针量的，不是推的）：

- 安全：`Delete`、`Ctrl+A`、`Ctrl+L`（`QLineEdit` 自己吃了：删字符 / 全选文本）
- **被抢走**：`F2`（重命名）、`F5`（刷新）、`F7`（新建文件夹）、`F8`（新建文件）、`Ctrl+F`（筛选）

内嵌终端 `TerminalView` 是 `QPlainTextEdit`，同一批键在终端里也会打到窗格上 —— 而 vim / htop /
micro 真的用功能键。所以症状不是“删错文件”（那个反而显眼），而是**在路径栏里打字时顺手改了
文件系统**，普通用户根本说不清是怎么发生的。修法是在入口前加一道 `_focus_is_text_input()`，
而不是改 `shortcutContext`：那些动作的宿主是整个主窗口，窗格里的列表也得能触发。

不能只看“按了没反应”就判“Qt 不抢”：要钉这件事，得监听 **`QAction.triggered`**（与处理函数
无关），它能证明“键确实被窗口拿走了”；否则守卫看起来就是凭空多出来的。

**二、`QApplication.focusWidget()` 对可编辑 `QComboBox` 报的是 combo 本身**，不是它的
`lineEdit()`（路径栏就是这个结构），而且 `lineEdit().focusProxy()` 还反指回 combo：

```
line.hasFocus()               = True     ← 键盘输入真的归 lineEdit
QApplication.focusWidget()    = QComboBox
lineEdit().focusProxy()       = QComboBox   ← 两者分叉，不是“焦点控件就是它”
```

所以 `isinstance(focusWidget(), (QLineEdit, QPlainTextEdit, QTextEdit))` 在路径栏上**静默返
False**，而测试的前提断言 `line.hasFocus()` 仍是 True —— 全红方向不会告诉你原因，只能专门
打一次 `type(QApplication.focusWidget())`。这类“两个 API 对焦点的说法不一致”的地方，
判据必须包含 combo（认 `isEditable()`，只读下拉框不是在打字）。

**三、同一个现场背后的第三条**：Ctrl+L 打完路径回车后焦点留在输入框（`on_return_pressed` 只
emit、`on_path_entered` 不动焦点），于是接下来的方向键 / `Menu` / Delete 全部打在输入框上。
自动化验收里它表现为“四段截图字节数完全相同”，极易误判为“按键没送进来”（真的误判了两轮）。
区别办法：看截图里**输入框有没有文本光标**；或先按一次 `Tab`/点一下列表再重跑，现象消失就是它。

### 50. 改了「怎么说」就得同时改「怎么做」：`describe_removal` 去 `nt` 化了，`delete()` 没有

v1.9.013 把删除确认文案的网络分支从 `os.name == 'nt'` 里放出来（Linux 上以前无论挂的
是什么都说「移到回收站」），当时以为「措辞与行为共用一个判据」就已经做到了 —— 其实
`FileOperations.delete()` 里那扇**真决定走不走回收站**的门还锁在 nt 上。后果在 230 真机
上一撞就中（p42）：

- 弹框说「网络位置的 1 个项目将被永久删除、无法恢复」，代码却照旧 `send2trash(path)`
- 而 `send2trash` 对非 home 设备的路径，会在**该挂载点根**建一个 `.Trash-1000/`（freedesktop
  规范就是这么写的，Nautilus 也这么干）—— 在用户的 NAS 共享根上凭空多一个目录，
  而我们的 UI 没有任何地方能看到它、恢复它

写这类「一个判据、多个消费方」的重构时，把消费方**逐条列完**再动手（本仓 `_is_network_path`
的四个消费方：窗格刷新、watcher 登记、确认文案、**实际删除** —— 前三个当时都改了，第四个没改）。
只抽文案不抽行为，得到的不是「一致」，而是一个更难查的假一致：日志与弹框都在说真话，
只有磁盘上的结果在说谎。

两个取证手法上的坑（同一个现场撞出来的）：

- **确认框的默认按钮是 `No`**，所以 `xdotool key Return` 等于点「取消」。p41 段 6 因此报了
  一次假故障（「Linux 回收站没落地」）。真要点 Yes：`xdotool key alt+y`（Qt 标准按钮是
  `&Yes`，中文界面下按钮文字仍是英文 Yes/No —— 没装 QTranslator）。更根本的教训：
  **自动化的每一步“确认”，都要用磁盘上的结果反证，不能只看弹框弹了**
- 测「谁进了回收站」不能真用 `send2trash`（会污染开发机的回收站）：用
  `monkeypatch.setitem(sys.modules, "send2trash", fake)` 替模块，只记不删；再反方向钉一条
  「本地文件必须递进去」，否则把整个分支改成「一律 `os.remove`」也能全绿

### 51. GUI 真机验收：拿**对话框标题当 oracle**，别拿截图字节数当 oracle

p43（第四轮）报了「§3 Shift+Del 没落地」，事后看截图才发现根本不是产品的问题 ——
§2 删完 CIFS 文件后弹出一个**模态的「删除完成」告知框**（`Pane._on_delete_done`：
`result.error` 非空就 `QMessageBox.information`），它把所有后续按键都吃掉了，于是
`navto` 打的字全进了空气，一整段脚本静默空转。之前三轮都靠「截图字节数变了没」判断
动作有没有生效，而**模态框恰好会让截图变、却让按键不变** —— 这个断言方式在弹窗类
交互上是瞎的。第五轮（p46）换成三条硬断言，一次全绿：

- **对话框标题当 oracle**：`xdotool search --onlyvisible --name '^确认删除$'`。
  标题就是 `describe_removal()` 给出来的那几个（确认删除 / 确认永久删除 / 删除完成 / 警告），
  「查得到某个标题」= 产品真的走到了那个分支，比任何像素比较都强，而且它同时是
  文案断言与路径断言。每一步前先 `dismiss_box()` 把可能挡路的告知框清掉。
- **坐标必须从 X 现读几何量**：`eval "$(xdotool getwindowgeometry --shell "$DW")"` 拿原点，
  再加从上一轮截图量出来的偏移（对话框行距 40px：搜索目录 Y+59、文件名 Y+99、
  按钮行 Y+300）。p43 用 `Y+92` 打「搜索目录」，实际命中的是「文件名」，路径被拼进
  pattern 里 —— 偏移只能靠裁图量（`build/crop_shot.py`，2560x1440 全屏图不放大根本看不清字）。
- **`QLineEdit` 获得焦点不会选中旧内容**，重填必须先 `ctrl+a`。p47 的 B 跑因此把路径拼成
  `/home/kali/big100k/home/kali/big100k`（反而成正面证据：「目录不存在」校验有效）。

两条附带事实：**主窗口开着模态搜索对话框时 `Ctrl+Q` 退不掉**（p47 退出后还剩 2 个进程，
得手工 `pkill`）—— 这是挂账项「20.5 搜索窗口改非模态」的又一条理由；**A/B 要有差别，
靶子得足够慢** —— p47 拿 10 万项目录比「1.5s 点停止 vs 不点」完全比不出（1.5s 内已经遍历完），
换 130 万项 / 57.8s 的 `/home/kali` 才拿到 503 与 40,944 的差别。

### 52. 一次解析异常吃掉一整帧：为什么「只有 vim 在内嵌终端里不显示」

现象本身就排除了一大片嫌疑：同一个终端 dock 里 htop、less 正常，只有 vim 完全不画，
画面停在上一条命令的 shell 历史上；而 `pgrep -x vim` 有 1 个、敲 `:q!` 它真退 ——
**输入链、PTY、子进程全好，坏的只是「屏幕」**。两条直觉解释都是错的：不是截图时机
（2s/4s/6s 三张字节完全相同 289540），也不是「备用屏没实现」（那只会让退出后残留，
不会让首屏根本不出现）。

**根因链（三层，缺一条都不会成这个现场）**：

1. vim 启动时发了一条带私有标记的 SGR（`CSI ? … m`）。pyte 的 `Stream._parser_fsm` 对
   `CSI ? x` **无条件**传 `private=True`，而它自己的 CSI 表里有 **18/23 个处理函数不收这个
   参数**（`select_graphic_rendition` 就是其中一个；`report_device_status` 即 `CSI ? 6n` 同病）。
2. `Stream.feed` 抛 `TypeError`。pyte 在 `_send_to_parser` 里接住它、**重置状态机、再往上抛**，
   于是 `feed` 末尾那句 `self._taking_plain_text = ...` 根本执行不到 —— **当前这一整段
   PTY 输出被丢**。vim 是「首屏整屏绘制 + 之后只发增量」的程序，丢一段就是永久错位。
3. 产品侧 `_on_output` 里 `self._stream.feed(data)` **没有 try/except**，而它是个 Qt 槽：
   异常逃出去被 excepthook 吞掉，没人知道那一帧没了。

**修法是两层，缺一层都不行**：只加 try/except → 不崩了，但那一段依旧丢，vim 依旧黑；
只容忍 `private` → 抵得住 vim，抵不住下一个发冷僻序列的程序。所以：`TerminalScreen`
按**函数签名**筛出那批处理函数并包一层（写死名单会在 pyte 升级后静默失效），把
冷僻序列**剥掉私有标记后照常执行**（参数仍生效，不是整条吞掉），同时
`_on_output` 给 `feed` 加容错（带计数与限流日志），一帧解析失败只丢那一帧、不拿整条
终端链陪葬。

**四条取证纪律（本条现场撞出来的）**：

- **给 GUI 程序的自动化验收必须把 stderr 落盘**（`nohup … > run.log 2>&1`），跑完先
  `grep -c Traceback run.log`。本条的定案证据就一行：改前恒为 1，改后恒为 0 —— 比任何
  像素比较都便宜。另外：**槽函数里的异常不进崩溃日志文件**（`pan4dex_crash.log` 里只有
  「启动于」标记），只出现在 stderr，拿日志文件当唯一 oracle 会看漏。
- **第三方解析库的版本必须与产物对齐**。230 宿主 venv 是 pyte 0.8.0，而产物捆的是 0.8.2
  （builder 镜像 `pip install pyte` 不锁版本，`packaging/Dockerfile-linux:61`）；两版对
  `CSI ? … $y` 的处理就不一样（0.8.0 多画一个 `y`）。用 `pip install --target … pyte==0.8.2`
  + `sys.path.insert(0, …)` 才能拿产物视角复现。用例也因此分两组：会崩的那组断精确渲染，
  冷僻那组只断「后续输出还在」。
- **`pkill -f "pan4dex-1.9.018-linux"` 会亲手杀掉自己的 ssh 会话**（模式出现在自己的
  cmdline 里），而且不报错 —— 那一轮看起来「跑了」其实根本没启动。要么用括号技巧
  `pan4dex-1.9.01[8]-linux`，要么先 `pgrep` 确认目标存在再动手。
- **“连拍几张截图是否相同”不是可靠判据**。本条的验收脚本里有一条「三张截图不再完全
  相同」，因为改前是 289540/289540/289540；p53（源码版）得到 278637/278616/278616 判为通过。
  但 p54（产物版）得到 **272714/272714/272714** —— 脚本报 🟡，而肉眼核对裁图：vim 首屏
  （`aaa/bbb/ccc` + `~` 列 + 状态行 `"~/p54/vimfile.txt" 3L, 12B  1,1 All`）**明明已经画出来了**。
  原因：vim 进入静止状态后屏幕本来就不变，p53 那三张不同只是因为第一张（2s）拍在首屏
  画完之前。改前可疑是因为那张定格画面**内容是 shell 的历史行**，而不是因为“帧间无差异”
  这个形式属性。拿形式属性当判据，同一个 bug 修好了会误报 🟡，反过来一个真定格也可能误报 ✅。
  要断就断**内容**：字节数与改前的差异、图上有没有目标程序的标志行（最好亲眼核一次裁图）。

**一个仍然存在的坑（没修）**：pyte 压根没有备用屏概念 —— `\x1b[?1049h` 只是把
`1049 >> 5 == 32` 这个位记到 `screen.mode` 里（p52b 实测私有模式集合含 32），无人消费。
后果：vim 退出后 `~` 行与状态行会残留在 shell 屏幕上。已记进 unsolved-issues 问题 14。

### 53. 验「排序有没有生效」：取样取错行会连着骗人两次，而驱动冻结产物另有三个坑

L2 这一轮里，「点列头后 1 万行一行没动」这个现场被误判成产品缺陷**两次**，
两次都是探针自己的错。把它拆开写，因为每一条都能单独复现。

**一、不能只看前 N 行（p59b 的错）**。「表头指示已变、可见顺序未变」看起来铁证如山，
但靶子是 200 目录 + 9,800 文件，而 `PaneSortProxyModel.lessThan`（`core/pane.py:117`）
明文规定**大小列下目录之间比名称而不比 size** —— 前 200 行全是目录，切「大小」列时
它们**本来就不该动**。用 `lessThan` 计数器一问，那次排序其实调了 115,476 次比较。
判据要改成：读**全部**可见行、按目录块/文件块**各自**断言单调，并且先证明
「顺序真的变了」，再拿「0 次 stat」当性能达成 —— 否则就是把空转当成了优化生效。

**二、方向也要断言（p59e v1 的错）**。修完第一条又报了一条假违例：我断言「大小」降序下
目录块按名称**升**序。但 `lessThan` 只固定「目录在前」这一件事，降序时 Qt 反转比较结果，
同类内部跟着反向 —— 目录块是名称**降**序才对。所以单调断言必须带 `reverse` 参数，
升/降两套比较器分别给。

**三、`_entry()` 只吃源索引**。把代理索引喂进去会在 `isinstance(e, Entry)` 那行**段错误**
（exit 139，core dumped）。它的 docstring 写明了要源索引：取法只能是
`mapToSource(proxy.index(i, col, root)).row()` → `model.index(srow, col, model.index(0, 0))`
→ `_entry(...)`。**崩在产品代码里不等于产品有 bug**：靠 `faulthandler.enable()` +
每步先打一行日志（p59c）就能看出崩在探针的哪一步。

**四、Qt6 改了属性名**：`recursiveSortingEnabled` → `recursiveFilteringEnabled`
（`setRecursiveSortingEnabled` 同）。按 Qt5 名字调 `isRecursiveSortingEnabled()` 直接
`AttributeError`，两个名字都探测一下再下结论。

**五、offscreen 下的合成点击不可靠**。`QTest.mouseClick(header, ...)` 在
`QT_QPA_PLATFORM=offscreen` 下**没被表头接收**：指示停在「列 0」，`lessThan` 0 次。
这不能当成「产品不响应点击」的证据 —— 判之前必须先读 `sortIndicatorSection()` 确认
点击真进了事件循环。要真点击就上 `:10` 用 xdotool。

**驱动冻结产物（Linux）的三个坑**（p60b 一整轮作废换来的）：

- **`xdotool search --pid $父pid` 拿到的是根窗口**。PyInstaller 的 Linux 产物是父进程
  fork 出真正跑 Qt 的子进程，窗口属于**子 pid**；按父 pid 搜必然搜不到，于是键鼠全发给
  空气。这种空转几乎无声响，唯一的外在表现就是「连拍 N 张截图 md5 完全相同」。
  定位改用**启动前后 `wmctrl -l` 的窗口 id 差集**，与 pid 无关。
- **`xdotool click 1 --clearmodifiers` 是非法语法**（`click` 不认这个选项），报
  `Unknown command` 之后一下都没点，而脚本继续往下跑、后面的截图照样变（鼠标移动也会
  引起 hover 变化）→ 差点把「什么都没点」报成「点了没反应」。
- **从渲染后的截图估屏幕坐标会被缩放骗**。按看到的图估的 `y=540` 去裁状态栏，实际裁到了
  列表行（屏幕真高 1440，渲染图只有 810）。而且**焦点在表头时单按 `End` 不动列表**，
  要先点一行把焦点交给列表。稳妥流程：先裁一大块（目标 + 上下文）看图核对，再定精确点击点。

**最后一条是方法论**：单个数字不能归因。只量到「SMB 1 万条目主线程停摆 1256ms」时，
顺理成章的结论是「SMB 慢」；补一个**本地 ext4 同条数**对照（扫描 0.23s vs 10.08s，
停摆仍是 1256ms）才知道那一下跟存储无关，是「1 万行落地」的通用代价。A/B 的差别
必须落在被测变量上，条数也要对齐（拿 10 万条本地目录去比 1 万条 SMB 什么都比不出来）。



### 54. 枚举取消令牌：布尔谓词的「方向」错了会让健康扫描自我了断，而替身不能自带一套取消判据

v1.9.020 修 L2「能取消 / 切走窗格不继续扫」时踩到两个坑，都记下来，因为两者都能单独复现。

**一、令牌契约是「返回 True = 该停了」，别把「还要这份结果」直接当 `__call__`**。为了把
 gen 校验接进扫描循环，把 `_LoadTask` 本身喂给 `enumerate_dir(cancel=...)` 作取消令牌，
 直觉上会写 `__call__ = _still_wanted`。错。`_Enumerator.check` 的约定是
 `aborted = bool(cancel())` —— 令牌返回 True 代的是「停」，而 `_still_wanted()` 返回 True
 代的是「继续」。两者相反，接错的结果是：一个完全健康的扫描，在第一次真探测
 （第 256 项）就自杀，万条目一条都出不来。修法：另给一个 `_should_stop() = not
 _still_wanted()` 作 `__call__`，`run()` 里继续用 `_still_wanted()`（那里是「继续」语义）。
 **教训**：一个布尔谓词被当回调接时，名字不算契约，方向才算；接前先拿一个已知应该
 「继续」的场景跑一遍，看会不会一上来就早退。

**二、测试替身不要自造一套取消判据，要停全问产品的 `check()`**。一开始在替身扫描里
 拿「旧任务存个全局令牌 + 自己写 `stale()` 比 `node.gen != tok.gen`」来驱动中断，结果
 F5 后新发起的扫描一开始，`_pending[key]` 已是新任务而我那个令牌还指着旧任务，新扫描
 被误判为过期立即中止 —— 测出来的是个假红（旧扫描本该让路、新扫描该跑完，却被断成 601）。
 止血：删掉替身里的 `stale()`，fake 循环里只调 `check()`（它走的是产品的
 `_Enumerator` + `_LoadTask.__call__`），要不要停全由被测代码决定；计数改成按任务分
 （`check.__self__._cancel` = 拥有该扫描的任务），否则同目录被超越的两代扫描会求和到一个
 数字上（新 4000 + 旧 767 = 4767，断不了谁跑完谁让路）。**教训**：替身自带判据只能测到
 自己那套；真契约得让被测代码自己报，替身只负责「递工具」与「控时序」。

**三、计时用「逐项 + 每目录一栏阀（barrier/release）」把在飞做成确定事实**。一个空转的
 4000 项扫描很可能在主线程标记前就扫完了，靠 sleep 碰运气测不到中断；fake 扫到第 N 项置
 barrier 告知主线程「真在飞了」、再等 release；放行只能放住当前在飞那栏，新发起的扫描若
 在 `waitForDone` 之后才跑到门，拿到的是已放行的门不会卡住。另外，不要为了「预先放行重扫」
 而拿新 Gate 覆盖旧 Key：worker 进的是旧那扇门，覆盖后 `_settle()` 放行的是新门，worker
 卡在旧门上 `release.wait(10)` 超时→ AssertionError 被 `run()` 当成枚举异常→ 把空列表采纳
 了（loaded 变 True）。要放行就去放行 worker 正在控制的那扇现有门。





---

## 八、回归防护机制

### 部署脚本
```bash
python scripts/deploy.py 0.9.618
```
自动验证：本地版本号 → 文件同步 → 构建大小 → 部署验证。

### Post-Deploy Checklist（手动验证）

- [ ] 四窗格正常显示
- [ ] 导航到其他目录，其他窗格不受影响
- [ ] 目录树侧栏 📍 跟随功能
- [ ] 超大图标模式多次切换正常
- [ ] 图片预览显示
- [ ] 后退/前进按钮默认隐藏

### 代码审查清单

- [ ] 新增的 Qt widget 是否考虑了共享模型
- [ ] 涉及 QFileSystemModel 的是否处理了异步加载
- [ ] 涉及 `DirStoreModel` 的：新路径是否走 `entry_is_dir()` 而不是 `index(path)`？
      改动文件系统后是否调了 `refresh_dir` / `_reload_after_mutation`？
- [ ] 碰目录监视的：是否只登记本地、只登记当前显示的目录？新增的重扫入口是否经
      `_mark_self_change` 抑制紧随其后的文件系统通知？会不会把监视器改回 per-model？
      native 登记是否仍在 `set_directory` 调用栈里同步做（应推到事件循环顶层，见第 23 条第 6 项）？
- [ ] 新增后台线程池：是否加入了 `_pools_to_drain()`？并发数是否显式限流（不用
      `QThreadPool.globalInstance()` 默认的核数级并发，见第 26 条）？
- [ ] 新增跨窗格类级操作：是否走 `Pane._live_instances()`（而不是直接迭代 `_instances`）？
      注册/入册是否在对象**构造完成之后**（见第 27 条）？
- [ ] 从容器里移出 widget（`removeTab` / `take*` / `setParent(None)`）后：是否握住 Python 引用
      再 `deleteLater()`（否则销毁时机落在 GC 手里，会拆坏其他在构造的窗口，见第 28 条）？
- [ ] 改行信号（begin/endInsertRows、begin/endRemoveRows）：是否包在 `_rows_signal()` 里？
      新加的枚举入口是否会把同一次加载重复发起两遍（见第 24 条）？
- [ ] 后台枚举结果是否按 `gen` 校验代次（不得直接信任回调）
- [ ] 从 `threading.Thread` 向主线程投递：是否只走 `_emit_ui(名字, ...)` 这类带
      RuntimeError 防护的路径（不得直接 `self.sig.emit(...)`）
- [ ] 后台结果回投主线程：信号连接的**接收者是否就是目标 QObject**（绑定方法直连；
      不得为了判活改成 closure，那样 Qt 会在 sender 侧派发，模型销毁也不剔除投递）
- [ ] 新增常驻子进程/后台任务：是否在 `MainWindow.closeEvent` 里显式关停（不能依赖 GC）
- [ ] 延后执行（启动分阶段 / 防抖 / 轮询）：是否用 `call_later(obj, ms, fn)` 而不是
      `QTimer.singleShot`（后者在对象销毁后仍会触发）
- [ ] 新增后台线程/线程池任务：进程退出是否走 `exec_and_drain(app)`（而非裸 `app.exec()`），
      保证事件循环一返回就排空未派发的投递
- [ ] 新增 UI 入口（菜单项 / 对话框 / 工具栏）：枚举本机信息（注册表、`.desktop`、
      扫盘）是否**延迟到真要显示时** + 带 TTL 缓存 + 失败只少一项不外抛（见第 33 条）？
- [ ] 测试里手工造的父 `QMenu` / 父 widget：是否被调用方握住（只返回子对象会被 GC
      连带删掉整棵子树，见第 34 条）？
- [ ] 写盘的用户条件/偏好：存的是“界面上的数字”还是“真正参与执行的那份值”？能否
      `apply → collect` 原样回到同一个值（单位换算、共用下拉，见第 36 条）？
- [ ] 新增树形/可排序的用户数据：改动是否按 **id** 而不是行号？结构规则（成环/层数/上限/
      老格式迁移）是否住在 Qt 无关的那一层（见第 37 条）？写盘组件是否可注入配置目录，
      测试里是否注的就是临时目录（见第 39 条）？
- [ ] 碰拖放的：`canDropMimeData` 的 `parent` 是否当 `QModelIndex` 用？内部移动是否接了
      `rowsMoved` **与** `dropEvent` 两处，并对“对不上账”退回不写盘（见第 38 条）？
- [ ] 用例里的“N 天前/N 小时前”是否从本地中午起算（不从 `time.time()`），是否依赖“今天
      是周几/几号”（见第 39 条）？时刻是否在用例**体内**算（放进 `parametrize` 参数表
      就是收集时求值，跨午夜必假红，见第 39 条第二种形状）？
- [ ] 同一类文本匹配（glob / 正则 / 包含）是否只有一份实现？新写的匹配器是否在遍历
      循环外编译、正则写错时是否当场报错而不是返回 0 结果（见第 35 条）？
- [ ] “一个行为要做两遍”时：抽出来的是**机制**还是只是复制粘贴？后台执行 + 进度 +
      取消 + 冲突询问这类配合是否只有一个 `FileOpRunner`（宿主只给钩子，见
      `docs/architecture.md` 第 4.5 条），确认文案与“目标在源内部”这类判据是否也住在
      Qt 无关层（`describe_removal` / `move_target_inside_sources`）而不是两个入口各写一份？
- [ ] 写了 `except Exception` 包住“建 UI 控件”的：失败是否至少 `warning` 级日志？有没有
      用例断言控件**真的建起来了**（而不是只测“调了不抛”，见第 40 条）？
- [ ] 跨线程要“答案”：是否用了共享对象回写而不是信 `invokeMethod` 的返回值？是否
      处好了“已在主线程时直调”（Blocking 会自锁）与决策白名单降级（见第 40 条）？
- [ ] 新增测对话框/菜单的用例文件：是否替掉了全部模态入口（真弹一下就是整个会话挂死，
      见第 41 条）？用了 `sip.delete` 的对象是否没交给 `qtbot.addWidget`？
- [ ] 改 `docs/architecture.md` 的模块表：表里的文件名是否逐个与盘上对过账？本仓曾长期
      挂着三行讲不存在模块的条目（`core/drag_drop.py`、`core/terminal.py`、
      `config/settings.py`）—— 拿 `git ls-files` 过一遍比眼睛可靠
- [ ] 碰拖放的：动作判据是否走 `decide_drop_action`（窗格内部拖拽 / 外部拖入 / 搜
      索结果将来都共用一份）？`possibleActions` 不含 Move 时是否绝不 move（否则会
      删掉外部的源）？手工造 `QDropEvent` 的用例是否自己持住了 `QMimeData`（见第 42 条）？
- [ ] 碰“网络/慢位置”判据的：是否只有一处实现（`core/mounts.py`），窗格刷新与目录
      监视与删除文案与实际删除是否拿的同一个答案？有没有新写 `os.name != 'nt'` 这种
      “非 Windows 就 `return False`”的门控（见第 43 条）？平台专属的用例是否在假宿主上
      跑了一遍？改文案时行为那一半同步改了吗（第 50 条）？
- [ ] 新增“安全网”性质的代码（崩溃日志、日志系统、诊断转储、上报）：它自己有没有
      致命失败路径？写不了文件时是否能退到下一个落点而不外抛（它在 `main()` 里可能比
      窗口创建还早，抛一下就是“双击没反应”，见第 45 条）？它的用例是否只断了
      “不抛”（那盖不住退路失效）？
- [ ] 改构建/发布脚本：是否在**干净克隆**上跑过一次（本地工作树里有而被 `.gitignore`
      排除的文件，是这类脚本最常见的隐性依赖）？`docker run ... bash -c "..."` 里的变量
      是否明确知道它在**哪一侧**展开（见第 46 条）？
- [ ] 断言「排序/刷新生效」的探针：是否读**全部**可见行并按目录块/文件块各自断言？
      是否方向感知（降序会反转同类内部顺序）？是否先证明顺序真的变了，再拿「0 次
      stat」当性能达成（否则就是把空转当生效，见第 53 条）？
- [ ] 驱动冻结产物做 GUI 自动化：窗口是否按**启动前后窗口列表差集**定位（按父 pid 搜会
      搜到根窗口，键鼠全发给空气，见第 53 条）？`xdotool` 选项语法是否核对过？
- [ ] 切换可见性后是否 `update()` + `repaint()`
- [ ] 导航是否用 `setRootIndex` 而不是 `setRootPath`
- [ ] QDockWidget 是否保存了显式 parent 引用
