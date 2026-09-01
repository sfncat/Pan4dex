# Pan4dex 待解决难点（2026-09-02）

以下问题反复尝试修复，均未解决。需要更有经验的 PyQt6/Windows GUI 开发者协助。

---

## 问题 1：超大图标模式（ThumbnailView）第二次切换后不显示

**现象**：
- 第一次切换到超大图标模式：正常显示 107 个项目
- 切换到列表/图标模式，再切回超大图标：一片空白
- 日志显示 `load_directory` 执行成功（107 items added），但 GUI 不绘制

**环境**：
- Windows 10, PyQt6 (Python 3.13), PyInstaller --windowed
- 本地 Linux offscreen 测试正常，仅 Windows 上复现

**已尝试**：
1. `hide()` → `clear()` → `show()` + `doItemsLayout()` + `scheduleDelayedItemsLayout()` — 无效
2. `setUpdatesEnabled(False/True)` 包裹 — 无效
3. 强制刷新父布局链 `parent.updateGeometry()` + `layout().activate()` — 无效
4. 加 `viewport().update()` + `repaint()` + `QApplication.processEvents()` — 无效
5. 日志显示 `parent is hidden!` 警告（父级链上有隐藏 widget），但本地测试也有此警告却正常

**相关文件**：
- `widgets/thumbnail_view.py` — ThumbnailView (QListWidget + IconMode)
- `core/pane.py:788` — `on_view_mode_changed()` 切换逻辑

**核心代码**：
```python
# pane.py on_view_mode_changed
elif mode == 'xlarge':
    self.tree_view.setVisible(False)
    self.thumbnail_view.setVisible(True)
    self.thumbnail_view.load_directory(self.current_path)

# thumbnail_view.py load_directory
self.clear()
self._current_path = path
# ... addItem(item) for each entry
self.doItemsLayout()
self.viewport().update()
QApplication.processEvents()
```

**可能根因**：
- QListWidget 在 Windows 上 hide/show 后，内部 viewport 的 paint device 可能未正确恢复
- 或者 QVBoxLayout 中两个 widget（tree_view + thumbnail_view）的可见性切换导致布局计算异常

---

## 问题 2：--windowed 模式 CLI 输出（AttachConsole 失败）

**现象**：
- `pan4dex.exe --version` 从 PowerShell 启动时，弹出新的终端窗口
- 新窗口中显示乱码（UTF-8 代码页未设置）
- 不会输出到当前 PowerShell 窗口

**已尝试**：
1. `AttachConsole(-1)` 挂父进程控制台 — 在 PowerShell 下失败（返回 0）
2. `AllocConsole()` 兜底 + `SetConsoleCP(65001)` — 会新建窗口，但仍有乱码
3. `os.fdopen(os.open("CONOUT$", os.O_WRONLY), "w")` — 无效（closefd 报错）
4. `open("CONOUT$", "w", encoding="utf-8")` — 乱码

**相关文件**：
- `main.py:196` — `_cli_output()`

**可能根因**：
- PyInstaller `--windowed` 模式下，`sys.stdout` 被设为 `None` 或重定向到 NUL
- `AttachConsole(-1)` 在 PowerShell 下的行为可能与 cmd.exe 不同

---

## 问题 3：图片预览（缩略图）不显示

**现象**：
- 超大图标模式下，图片文件显示为默认文件图标，不显示缩略图
- 日志没有 `ThumbnailLoader` 相关输出，说明懒加载未触发

**已尝试**：
1. 打包 Qt 图片插件（qjpeg.dll, qpng.dll 等）— DLL 已确认存在
2. 设置 `QT_PLUGIN_PATH` 到 `sys._MEIPASS/imageformats` — 确认 True
3. `QImageReader` 读取 + `QThreadPool` 后台加载 — 无日志输出
4. 检查 `_is_image()` 扩展名匹配 — 正常

**相关文件**：
- `widgets/thumbnail_view.py:177` — `_load_visible_thumbnails()`
- `main.py` — `install_qt_plugin_path()`

**可能根因**：
- `_lazy_timer.start()` 在 `load_directory` 里启动了，但 `_load_visible_thumbnails` 可能因为 `self.isVisible()` 为 False 而直接 return
- 或者 `QThreadPool` 任务在 PyInstaller 环境下无法正常执行

---

## 问题 4：QTreeView 大图标 GDI 崩溃

**现象**：
- `QTreeView.setIconSize(QSize(128, 128))` + 自定义 `QStyledItemDelegate` → Windows GDI 级崩溃
- 无 Python 异常，无崩溃日志

**已尝试**：
1. 不用自定义委托，用 `QStyledItemDelegate` — 仍崩溃
2. 用 `QListWidget + IconMode` 替代 — 引入问题 1

**可能根因**：
- Windows GDI 资源限制，大图标句柄泄漏
- PyQt6 的 QTreeView 在 Windows 上的 icon size 有隐式上限

---

## 部署脚本（已可用）

`scripts/deploy.py` 一键部署，带验证：

```bash
python scripts/deploy.py 0.9.618
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

---

## 环境信息

| 机器 | 系统 | 角色 |
|------|------|------|
| kali (本地) | Linux | 开发机 |
| win54 (192.168.5.54) | Windows 10, Python 3.13 | 构建机 |
| win55 (192.168.5.55) | Windows 10 | 部署目标 |

**技术栈**：Python 3.13 + PyQt6 + PyInstaller --onefile --windowed + qdarkstyle
