# Pan4dex 万格 — 待办（TODO）

> 本文件是**待办的唯一正文**：做什么、卡在哪儿、怎样才算销账，都写在这里。
> 功能状态表 `docs/feature-checklist.md` 只给每条功能标 🟢/🟡/🔴 并指向本表的编号，
> 同一件事不在两边各抄一份。现在还挂着的问题（区别于「待办」）看 `docs/unsolved-issues.md`。

**图例**：🔴 未开始 | 🟡 进行中 | ✅ 已闭环（做完的条目**不删行**，它同时是验收证据）
**优先级**的定义（P0 核心 / P1 首个可用版本 / P2 迭代 / P3 有空再做）见
`docs/feature-checklist.md` 的「优先级说明」。

**编号规矩**：`L<n>` = 需要真实环境或人手的验证项，编号与 `docs/linux-gap.md` §5.2 的矩阵一一对应；
`T<n>` = 代码层就能闭环的任务。新增条目**续号，不复用旧号**。

---

## 1. 待办表

| # | 任务 | 优先级 | 状态 | 验证方式 | 说明 |
|---|---|---|---|---|---|
| L2 | 万条目真共享（靶子经用户授权后在 NAS 上造，验完删） | P0 | ✅ | 真 CIFS/SMB3.1.1 上的 10,000 条目目录（9,800 文件 + 200 目录）逐条对三判据，源码版（offscreen 探针 p57/p59e/p59f）与 **v1.9.020 产物版（`:10` 真 X + xdotool 真键鼠，p60c–p60e）**各一轮；本地 ext4 同条数目录作 A/B 对照；v1.9.021 修复枚举取消链路后 p59e/p59f 复跑（SMB 与本地 ext4 `/home/kali/big10k` 同条数） | **三条判据原两条不成立，v1.9.021 修复后全部成立（余一项另案）**。✅ 判据命中 26/26（不挂 watcher / 永久删除文案 / 跳服务器判跳卷）；✅ 不闪：主线程最大停摆 1256ms，而本地同条数对照（扫描 0.23s vs 10.08s）**也是 1256ms** → 那是「1 万行落地」的通用代价、与 SMB 无关，产物版状态栏真读得到「200 个目录, 9800 个文件」；✅ 列头排序在 1 万条目上读全表断单调、0 次文件系统查询（清单 1.8 至此才算真验过）。✅ 「能取消」（v1.9.021 修）：`enumerate_dir(cancel=...)` + `_Enumerator` 每 256 项探一次取消令牌（令牌即 `_LoadTask`，`__call__`=「该停了吗」，含 gen 与 abandoned 校验），命中抛 `_EnumerationAborted`、只投 `cancelled` 不回投条目；显式入口 `DirStoreModel.cancel_load(path)`。✅ 「切走窗格不继续扫」（v1.9.021 修）：`set_directory` 切换后 `_drop_stale_scans` 复用慢位置判据（`_is_network`→`mounts.is_remote_location`）放弃离开目录的在飞枚举——复测 p59e [C]：被放弃的枚举在切走后 **0.24s 停扫**、经 `cancelled` 回报未采纳，心跳最大 10.3ms、视图仍是小目录 1 行（对照改前 23.2s 返回并被采纳、主线程阻塞 1388ms）。⏳ 残余（另案）：前景「盯着目录」时 1 万条目采纳仍在主线程停摆 ~1.2s（p59f A/B：SMB 1220ms vs 本地 ext4 1209ms，扫描差 47 倍而停摆同量级）→ 是「行落地」通用代价，需分批插入才压得下，与取消链路无关。另：NAS 靶子本轮借它复测仍未删（用户要求先留），收尾脚本 `tmp/p58z_cleanup_nas_target.py`（在 `tmp/` 里，不入库）带四道安全闸待执行 |
| L4 | 真鼠标拖拽 | P0 | 🔴 | 在真实设备上测试跨窗格拖拽性能 | 需要有人在现场 |
| L7 | HEIC 缩略图支持 | P1 | ✅ | Windows/Linux 两端产物 + 本机探针 + 用例 | v1.9.019 已验证，p56 脚本真机截图 |
| L11 | 桌面真打字 | P2 | 🔴 | 在真实 Wayland/X11 环境下测试输入法 | 需要真实桌面环境 |
| L12 | Wayland 原生支持 | P2 | 🔴 | 在 Wayland 会话下运行并验证 | 需 Wayland 环境 |
| T1 | `test_m4_theme` 的 5 条陈旧断言（changelog 早期版本记为「已列入待办」） | P2 | ✅ | 本机 offscreen 单跑 `pytest tests/test_m4_theme.py -q` → **21 passed**；连同 `test_bookmarks` / `test_filter_bar` / `test_pane_dir_store` 合并跑 → **173 passed / 1 skipped**（查跨用例 app 级全局态泄漏，见 gotchas 44 条），2026-09-22 复跑结果一致 | 那 5 条测的是根本不存在的接口（`save_custom_theme`/`delete_custom_theme`/`export_theme`/`import_theme`/`_generate_qss`），已改测真实契约并加反向守卫 `test_no_custom_theme_persistence_api`；本行是把 changelog 里那条「待办」正式闭环，登记时它从未进过待办表 |
| T2 | 用户操作菜单：先让对话框能被 import，再谈接入（清单 21.1 入口 + 21.2 快捷键） | P3 | 🟡 | **第一步已达成（v1.9.028）**：`QT_QPA_PLATFORM=offscreen python -c "import widgets.user_operations_dialog"` 不再 `ImportError`，`pytest tests/test_new_features.py::TestUserOperationsDialog -q` 5 条转绿（2026-11-10 全量复核 793 passed）。**第二步（接入，未做）才是剩余验收**：主窗口菜单与窗格右键各有一处入口能打开它并保存生效，配置里的操作能被快捷键真的触发；`grep -rn "UserOperations" --include=*.py .` 除 `config/`、`widgets/`、`tests/` 外要出现 `core/main_window.py` 或 `core/pane.py` 的命中 | 2026-09-23 核查两层：①`widgets/user_operations_dialog.py:4` 从 `PyQt6.QtWidgets` 导入 `QKeySequenceValidator`，该名字在 QtWidgets/Gui 里都不存在 → 模块 import 即硬错，配套 5 条测试全红；②就算能 import，全仓除测试外也零引用。**①已在 v1.9.028 修掉**（去掉无效引用，add/edit/delete 成功不再弹模态框），import 与 5 条用例转绿；**②仍成立** —— 2026-11-10 grep 复核产品侧依旧零引用，没有入口、没有 shortcut 字段。剩余要做：入口（菜单/右键 + 落到当前窗格选中项）→ 快捷键绑定。清单 21.1 因此是 🟡（组件好了没接线）、21.2 仍 🔴 |
| T3 | TreeSidebar 两处仍直接判 `_active_pane`（gotchas 第 47/49 条同一类） | P2 | 🔴 | 改完后 `grep -n "_active_pane" widgets/tree_sidebar.py` 无命中；用例：启动后一次都没点过窗格，直接对目录树节点右键，菜单要出得来（Linux/X11 offscreen 或真机各一轮） | `widgets/tree_sidebar.py:121` `_show_context_menu` 与 `:180` `on_follow_clicked` 用 `getattr(mw, '_active_pane', None)` 取落点。`_active_pane` 只在窗格被点过时才被赋值，所以「启动后还没点过窗格」这一段在 Linux/X11 上会静默失效（右键菜单不出现、「跟随当前目录」不动），铁律第 6 条要求落点统一走 `MainWindow.target_pane()`。属一行改一行的低风险修复，登记时只记录未动代码 |
| T4 | `FileCompareDialog` 调了两个不存在的方法（清单 16.1 文本比较 / 16.3 HTML 导出全废） | P2 | ✅ | **2026-11-10 验收**：`pytest tests/test_new_features.py tests/test_m5_tools.py -q` 两档跑完（含在全量 **793 passed / 4 skipped** 里，不再挂住）；文本比较出差异高亮、HTML/文本导出真的写出报告（`test_export_html_report` / `test_export_text_report` 绿） | **v1.9.028 修复**：补上 `highlight_diffs()`（`file_compare.py:332`，两栏互不对应的行加底色、与 difflib 差异统计同源）；`escape_html` 改 `html_lib.escape`，HTML 模板的 `str.format` 花括号占位符问题（`KeyError: ' font-family'`）改标记替换；二进制报告补「文件大小不同」提示。原三层后果（`AttributeError` → `except` 弹模态框 → offscreen 永久挂住，9 处两档）随之消失；「别把异常咽进模态框」的规矩留在 gotchas 第 56 条（含销账追记）。二进制比较那一半本来就是好的（16.2） |
| T5 | 全量测试自 v1.9.020 起就没跑完过（清单 21.x/16.x 的错判都源于此） | P1 | ✅ | **2026-11-10 验收**：`QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/ -q` 出汇总行 **793 passed / 4 skipped（111.06s，Windows offscreen）**，不再需要 `--ignore` 任何一档；红名单为空（T4 两档与 T2 的 5 条用例都绿），数字与命令见 `docs/testing.md` §5 | 根因是 T4 的模态框把 `test_new_features.py` 与 `test_m5_tools.py` 两档卡死（9 处两文件构造）、`TestUserOperationsDialog` 另有 5 条 `ImportError` —— 两者都在 v1.9.028 修掉后，全量恢复可跑完。历史对照：2026-09-23 排除两档才出 **644 passed / 4 skipped**；changelog 最后一次全量绿曾停在 v1.9.019（Windows 662 / 4 + Linux 660 / 6）。铁律不变：**发布前必须跑完整 `tests/`，跑不完就是跑不过** |

**这批待办的来历**：L7、T1 已完成；L2 逐条实测后由 🔴 经 🟡 升 ✅，原两条能力缺口（枚举不可取消、
切走仍扫完）由 v1.9.021 的枚举取消链路闭合，残余的「前景 1 万条目采纳 ~1.2s 停摆」属「行落地」通用
代价（本地同条数也一样），另案记在分批插入；L4/L11/L12 依赖真实环境或人手，无法在代码层闭环，证据与
阻塞原因见 `docs/linux-gap.md` §5.2。T2/T4/T5 与 L 系列不同，它们是 2026-09-23 文档审计时**跑代码**
跑出来的：v1.9.020 那批「中优先级功能」从未进过一次全量测试，清单因此把 16.1/16.3/21.1 从 🟢 改判 🔴
（16.2 实测可用、留 🟢）。T3 是同一轮审计顺带查到、只登记未修的真实缺陷。
2026-11-10 更新：T4/T5 销账（根因在 v1.9.028 修复，当天全量 793 passed / 4 skipped 复核），
T2 推进到 🟡（import 与 5 条用例已绿，入口接线仍缺）；清单 16.1/16.3 回 🟢、21.1 改 🟡。

---

## 2. 销账与新登记的规矩

1. **做完一条**：本表状态改 ✅ 且**保留整行**（行里的验证方式就是它的验收记录），同时把
   `docs/feature-checklist.md` 对应功能行的状态**与正文**一起改掉 —— 只改状态不改正文比没改更坏。
2. **影响发布的**：写进 `CHANGELOG.md` 对应版本一节。
3. **教训类**：根因与规矩进 `docs/gotchas.md`，本表只留一句结论加条号引用（不要两边都写长文）。
4. **新登记一条**：先跑代码拿证据再写，别从旧文档抄。写清「现场 → 判据 → 修法」，判据要能被下一个人
   照抄执行（命令、grep 式、期望输出）。
5. 待办与「问题」的分工：**能排期做的进本表**；现象还在、根因未定的进
   `docs/unsolved-issues.md`，两边不重复正文，用编号互指。

---

## 3. 本表变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-24 | 从 `docs/feature-checklist.md` 第 23 节整表搬出，独立成本文件；清单原节改为指向此处的占位（保留编号，历史引用不断链）。此前的账目变动仍记在清单的「更新记录」里（2026-09-22 销 T1、2026-09-22 量 L2、2026-09-23 登记 T2–T5 那三条），此处只记其后的变动 |
| 2026-11-10 | 销账 **T4/T5**：两处根因（file_compare 幽灵方法、user_operations_dialog 无效 import）均已在 v1.9.028 修复，当天全量 `pytest tests/ -q`（offscreen，venv python）复跑得出 **793 passed / 4 skipped（111.06s）**，不再需要 `--ignore`；**T2** 由 🔴 推进 🟡（第一步达成，入口接线未做）。同步回写清单 16.1/16.3→🟢、21.1→🟡、24.5/24.6→🟢，gotchas 第 56 条补销账追记，testing/development-guide/AGENTS 等处的「全量会挂住」警告一并刷新 |
