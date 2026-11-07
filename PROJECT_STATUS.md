---
project: Pan4dex
path: C:\workspace\Pan4dex
status: active
owner_ai: Trae
updated: 2026-11-07
---

## 当前进展

v1.9.048（2026-11-03）发布目录大小统计，Qt 6.12 升级已随 1.9.025（2026-10-29）发布。2026-09-23 的文档审计跑代码查出三处挂账：`FileCompareDialog` 调两个不存在的方法、用户操作菜单只建组件未接入、全量测试自 v1.9.020 起跑不完（排除两档后 644 passed / 4 skipped）；L11/L12 仍需真实 Wayland/X11 环境验证。

## 等你决策

- **L4 真鼠标拖拽是否安排现场验收**：卡在需要有人在真实设备前操作；选项：安排一次现场（跨窗格拖拽 + 性能记录）/ 先跳过；不决会挡住 P0 项销账。建议安排一次 30 分钟内的现场走查。

## TOP 待办

| # | 任务 | 状态 | 负责 AI | 备注 |
| --- | --- | --- | --- | --- |
| 1 | T4 修 `FileCompareDialog` 两个不存在的方法（`highlight_diffs` / `escape_html`） | 待开始 | 待补充 | 不修则文本比较报错、测试模态框永久挂住 |
| 2 | T5 全量测试跑完并逐项销账（P1） | 阻塞 | 待补充 | 阻塞于 T4 与 T2 的 ImportError |
| 3 | T3 `TreeSidebar` 两处改用 `MainWindow.target_pane()`（P2） | 待开始 | 待补充 | 未点过窗格时右键菜单在 Linux/X11 静默失效 |
| 4 | T2 用户操作菜单接入主窗口（P3） | 待开始 | 待补充 | 先修 `QKeySequenceValidator` ImportError，再加入口与快捷键 |

## 最近完成

- 2026-11-03 1.9.048 空白处右键「计算所有目录大小」
- 2026-11-03 1.9.047 大小列显示目录占用（后台递归、独立线程池）
- 2026-10-29 1.9.025 Qt 6.12 升级（Linux 基座 bookworm / glibc 2.36）
- 2026-10-19 构建文档重组，新增 WSL2 + Docker 的 Linux 构建路径
