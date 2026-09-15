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
- [ ] 切换可见性后是否 `update()` + `repaint()`
- [ ] 导航是否用 `setRootIndex` 而不是 `setRootPath`
- [ ] QDockWidget 是否保存了显式 parent 引用
