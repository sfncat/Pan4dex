# Pan4dex 界面审查报告（UI Audit）

> 2026-10-29，qt-ui-design skill 审查流程产出。
> 审查前提：桌面应用（Windows/Linux）、PyQt6 + Fusion 样式、qdarkstyle 深色 / 手写 CSS 浅色双主题、中文为主、鼠标+键盘输入。
> 分级：🔴 Critical（必须修）｜🟡 Warning（应修）｜🟢 Opportunity（做得好/可增强）。
> 每条标注修复状态：✅ 已修（v1.9.027）｜⬜ 未修。

---

## 🔴 Critical

### C1. 焦点不可见 + 无活动窗格视觉指示 ✅ 已修

双窗格管理器必须回答「操作作用于哪个窗格」，审查时两条线索都被堵死：

- 焦点环被样式表系统性移除：浅色主题 `theme_manager.py` 对 `QTreeView`/`QListWidget` 写了 `outline: 0`（违反 WCAG 2.4.7 Focus Visible）。
- `MainWindow.on_pane_activated` 只记账 `_active_pane`，不做任何视觉变化。
- 结果：两个窗格同时有选中项时，选中色完全相同（深色都是 `#2196F3`），用户无法分辨 Delete/Ctrl+C 会打到哪边。`target_pane()` 的「焦点跑到预览/终端后操作仍归原窗格」设计更依赖可见的活动窗格指示，否则用户心智模型对不上。

**修复**（v1.9.027）：
- 每个窗格路径栏下新增 2px 指示条，活动窗格点亮主题主色、非活动透明（`Pane.set_active_visual`，主窗口 `on_pane_activated` 联动点亮/熄灭；切主题重涂）。
- 浅色主题 `QTreeView:focus / QListWidget:focus` 边框换主色（宽度不变零抖动），键盘焦点重新可见。
- 深色主题 qdarkstyle 自带焦点视觉，未额外覆盖。

### C2. 没有键盘快捷键在双窗格间切换 ✅ 已修

全仓 `Key_Tab` 只有两处命中：`Ctrl+Tab` = 切换标签页、终端面板输出制表符。TC 用户的肌肉记忆是「Tab = 切换左右窗格」，当时只能靠鼠标点击。

**修复**（v1.9.027）：`QShortcut(Tab, WidgetShortcut)` 挂在文件列表与超大图标视图上，按 pane 编号在同窗口可见窗格间循环（1→2→1，四窗格 1→2→3→4→1）。实现要点：**不能用重写 keyPressEvent 实现**——`QAbstractItemView` 内建 Tab 处理（`moveCursor`）先于 keyPressEvent 生效，重写永远不执行（回归时实测）；`QShortcut` 走 ShortcutOverride 优先级更高。Ctrl+Tab 仍归「切换标签页」，Shift+Tab 走原生反向导航，QLineEdit 里的 Tab 不受影响（WidgetShortcut 作用域不覆盖输入框）。

---

## 🟡 Warning

### W1. 颜色令牌不成体系 ⬜ 部分（第一步已落）

- 浅色主题是手写 Google-Material 蓝系 hex（`#1a73e8`/`#cfe2fc`/`#1967d2`，`theme_manager.py`），深色是 qdarkstyle 加 pane 内散落 hex（`#2196F3`/`#1E1E1E`/`#2A2A2A`）。
- 交互色与装饰色未分离：拖拽高亮复用选中蓝 `#2196F3`，训练用户「蓝色=可交互」的联想被稀释。

**已落第一步**（v1.9.027）：`ThemeManager.color(token)` 语义色 API（accent / inactive_selection_bg / inactive_selection_fg，深浅两套），拖拽高亮改走令牌。**后续**：新样式一律从令牌取色；存量散落 hex 按触点逐步收编，浅色 CSS 本身视为浅色令牌表。

### W2. `init_ui_style()` 死代码埋雷 ✅ 已修

`pane.py` 里硬编码深色 + `outline: none` 的「恢复默认样式」方法，全仓无调用点。历史上真因它发生过「浅色主题拖拽后变黑」（`_apply_drag_highlight` 的注释记录了快照修复）。留着就是给未来的自己埋雷。

**修复**（v1.9.027）：整段删除，注释改为记录历史教训。

### W3. 字号硬编码 px ✅ 已修（随 W2 消除）

`init_ui_style()` 内 `QLabel { font-size: 11px }`——像素字号不随系统「大字体/缩放」走，且低于 12px 正文下限。全局浅色 CSS 用的是 pt ✔。

**修复**：随死代码删除一并消除。后续新增样式遵守：字号用 pt、每屏不超过 3-4 个档位。

---

## 🟢 Opportunity

### O1. 危险操作文案是范本（保持）

`file_operations.py` 网络位置删除明示「永久删除、无法恢复（网络位置没有回收站）」，本地/网络分列数量，回收站与 Shift+Del 双路径清晰。这是同类工具里少见的严谨文案，保持。

### O2. 进度反馈符合 Doherty 阈值（保持）

非模态进度框 + 速度/剩余时间 + 取消 + 1MB 分块进度回调（`progress_dialog.py`、`file_operations.py`）。操作进行中关闭被忽略并最小化、结束后才可关闭，避免了「进度框一关后台任务就失控」的误解。

### O3. 鼠标侧键前进/后退（保持）

窗格事件过滤器处理 XButton1/XButton2，符合资源管理器习惯。

---

## 未实施（后续可选）

- **非活动窗格选中色灰化**（TC/资源管理器惯例）：指示条已解决「分不清作用窗格」的主诉求；若后续仍嫌不够，可给非活动窗格的 `::item:selected` 加灰化令牌（`inactive_selection_bg/fg` 已备好）。
- **深色主题焦点边框**：qdarkstyle 自带视觉，暂不覆盖；若用户反馈键盘导航仍难辨认，再按浅色同法处理。
- **W1 存量收编**：浅色主题 CSS 重构为程序化令牌表（涉及全部选择器，单独排期）。

## 回归保障

`tests/test_active_pane.py`（5 条）：
- Tab 在窗格间循环切换（文件列表 ↔ 文件列表）
- Ctrl+Tab 不被窗格吞掉、焦点不被切走
- 超大图标视图里 Tab 同样切窗格
- 指示条随激活状态点亮/熄灭（断言令牌主色）
- 真 MainWindow 联动：新窗格点亮、旧窗格熄灭

全量：654 passed, 4 skipped（排除 `tests/test_new_features.py`、`tests/test_m5_tools.py` 两档模态对话框会挂住的用例）。
