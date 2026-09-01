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

## 六、回归防护机制

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
- [ ] 切换可见性后是否 `update()` + `repaint()`
- [ ] 导航是否用 `setRootIndex` 而不是 `setRootPath`
- [ ] QDockWidget 是否保存了显式 parent 引用
