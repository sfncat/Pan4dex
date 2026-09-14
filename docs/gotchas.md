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

### 12. 没有 QFileSystemWatcher → 改动后必须显式重扫

**现象**：新建/删除/粘贴/拖放后条目不可见，只有按 F5 才刷新（本地目录也一样）。

**根因**：为避开 SMB 上的 watcher 轮询，`DirStoreModel` 不挂文件监视；旧共享模型时代
`QFileSystemModel` 会自己发现本地变更，删掉它之后这份“免费午餐”就没了。又因为
`_fresh_or_local()` 对本地路径恒为 True，陈旧节点不丢弃就永远不重扫。

**解决**：pane 侧所有改动完成回调统一走 `_reload_after_mutation(path)`
（`refresh_dir` 失效并重扫 + `navigate_to`），不再区分本地/网络。

**测试**：`tests/test_pane_dir_store.py::test_local_mutation_visible_after_reload`

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
- [ ] 后台枚举结果是否按 `gen` 校验代次（不得直接信任回调）
- [ ] 从 `threading.Thread` 向主线程投递：是否只走 `_emit_ui(名字, ...)` 这类带
      RuntimeError 防护的路径（不得直接 `self.sig.emit(...)`）
- [ ] 新增常驻子进程/后台任务：是否在 `MainWindow.closeEvent` 里显式关停（不能依赖 GC）
- [ ] 延后执行（启动分阶段 / 防抖 / 轮询）：是否用 `call_later(obj, ms, fn)` 而不是
      `QTimer.singleShot`（后者在对象销毁后仍会触发）
- [ ] 切换可见性后是否 `update()` + `repaint()`
- [ ] 导航是否用 `setRootIndex` 而不是 `setRootPath`
- [ ] QDockWidget 是否保存了显式 parent 引用
