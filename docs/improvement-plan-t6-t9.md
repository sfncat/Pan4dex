# T6–T9 改进方案（已落地 · 回执见 §9）

> **状态**：**2026-11-13 已按本方案落地**（用户「开工 T6 到 T11」），逐项回执、实测数字与明确不做的事见 **§9**。
> 撰写日期 2026-11-11，**那一轮的状态是「方案待评审，产品代码与测试代码一行未改」** —— 这句话现在只描述 11-11 那一轮，
> 原文保留以便对照。
> **已拍板**：T6 的验收判据由用户 2026-11-11 放宽为「单次最大停摆 < 400ms + 落地期间有忙碌提示」
> （原 200ms 作废），详见 §2.4.1。其余各项于 2026-11-13 获批并落地（**T6 只做第一步**，第二/三步等真机数字）。
> **分工**：待办的唯一正文仍是 `docs/todo.md`（T6/T7/T8/T9 四行写「做什么、怎样算销账」）；
> 本文件只写「现场实测到什么、准备怎么改、为什么否掉别的改法、怎么验」。同一句话不在两边各抄一份。
> **评审方式**：意见请写回本文件对应小节（追加「评审意见」段），**原文不删**，便于对照改前改后的判断。
> 所有数字都来自本机只读探针（脚本与日志清单见 §8），探针只在自己进程内替换类属性，不改仓库文件。

---

## 0. 先更正登记时的三条判断

登记 T6–T9 时（2026-11-10）有三条说法被本轮实测推翻或削弱。**方案按更正后的事实写**，
`docs/todo.md` 对应行同步更正（已改）。

| 原登记说法 | 实测结果 | 结论 |
|---|---|---|
| T7：「End 落给 QTreeView 的默认行为 `MoveToEndOfRow`（同一行最后一列），所以光标与滚动都不动」 | ①`QAbstractItemView.CursorAction` 在本机 PyQt6 里枚举出来是 `MoveDown/MoveEnd/MoveHome/MoveLeft/MoveNext/MovePageDown/MovePageUp/MovePrevious/MoveRight/MoveUp`，**没有 `MoveToEndOfRow` 这个成员**；②200 条目、视口 854×222，详情视图按 End：`row 5→199`、纵向滚动 `5→189`、选中 1 行（199）；简单列表与超大图标同样 `5→199` | **原前提不成立（源码版 offscreen）**。End 本来就跳到最后一条。当初那次观察有焦点混淆：`tmp/p60e_scroll_to_end.sh` 的脚本头自己写着「焦点在表头导致 End 没跳尾」。**但焦点混淆只是可能解释、未证实** —— `docs/linux-gap.md` L2 行记的是**产物版（冻结 ELF + 真 X）**里单按 End 不跳尾，与本轮 offscreen 源码版的结果不一致，这一条仍需真机复测（先点列表一行确认焦点，再按 End），已写回 linux-gap。真正的缺口是另外两个键，见 §3 |
| T8：「搜索侧未过 `_win_unc_fix`，UNC 路径定位不到」 | 本机 Python 3.13/Windows：`os.path.normpath('\\\\nas\\share\\dir\\f.txt')` 返回**原样双前导反斜杠**，并没有被压成单斜杠 | **这条理由撤回**。`_win_unc_fix`（`core/pane.py:2137`）对这种输入是空操作，搜索侧不因此坏。两份实现仍该合一（§4），但理由换成「同一件事两处写、Linux 半边确实不选中」 |
| T6：「要压下去只能分批投行 + 每批之间让出事件循环」 | 分批 500 确实把**单次插入**从 337ms 压到 13–28ms，但**批间残余随已落地行数线性涨**（9ms@500 → 131ms@10000），端到端从 362ms 变成 1986–2166ms（5–6 倍）；心跳最大停摆只从 340ms 降到 151–188ms | **分批不是首选**。最便宜的一刀在比较器上（§2.4），分批列为被否决备选并附数据 |

另：T9 的原判断**成立**，实测比登记时写的更严重（§5.1）。

---

## 1. 实测环境与口径

- 机器：Windows 11 x64，Python 3.13.11 + PyQt6 6.11，`.venv`，`QT_QPA_PLATFORM=offscreen`。
- 靶子：合成 10,000 条目（200 目录 + 9,800 文件），走**真实采纳路径**（只把 `enumerate_dir`
  换成返回预制条目，`_on_entries_loaded` / 排序代理 / 视图布局全是产品代码）。
- 三个指标分开报，不混用：
  - **单次插入最大**：一次 `endInsertRows()` 的耗时（主线程被这一趟占住多久）；
  - **心跳最大**：5ms 心跳定时器相邻两次触发的最大间隔（主线程**任意原因**停摆多久，含视图布局）；
  - **端到端**：`navigate_to` 到 `directoryLoaded` 的墙钟（不含之后的延迟布局/重绘）。
- **波动很大，必须成对比较**：同一配置在不同轮次差到 57%（312ms vs 589ms vs 610ms，
  `tmp/t6j.log`）。疑似与进程内累积的类级缓存/GC 压力有关（每轮往缓存里塞 1 万条目，跑 12 轮就是 12 万）。
  因此本文引用的**绝对值一律取冷进程第一轮**，方向性结论取**同进程交错多轮**（A/B/A/B…）。
  验收时也要照这个口径，不能拿单轮绝对值去卡阈值。
- **本机 ≠ 目标机**：L2 在 Linux 本地 ext4 同条数量到 1256ms（`docs/todo.md` L2 行），
  约为本机冷态 340ms 的 3.6 倍。**任何「本机达标」都不能外推成「Linux 达标」**，
  §2 的验收门因此设成两道。

---

## 2. T6 · 一万条目「行落地」时主线程停摆

### 2.1 现场与出处

落地点：`core/dir_model.py:1050` `_on_entries_loaded`，其中 `:1070` 一趟
`beginInsertRows(parent_idx, 0, len(entries)-1)` / `endInsertRows()` 把整份条目交给视图，
排序代理与视图布局都在这一趟里跑完。

热路径上的两处 Python 关口：

- `core/pane.py:104` `PaneSortProxyModel.lessThan`，名称列在 `:135-138`：
  ```python
  if col == 0:
      l = left.data(Qt.ItemDataRole.DisplayRole) or ""
      r = right.data(Qt.ItemDataRole.DisplayRole) or ""
      return l.lower() < r.lower()
  ```
  而 `Entry` 对象在 `:106` 就已经通过 `self._entry(left/right)` 拿到手了 —— 名称列却又往模型里
  绕一圈取 `DisplayRole`。`_entry`（`core/pane.py:70`）本身已经是直接 `internalPointer()`，
  不需要 `mapToSource`，所以绕的是 `data()` 那一段。
- `core/dir_model.py:1171` `index()`：`*args/**kwargs` 双形态（还兼容 `index(path_str)`），
  每次调用都要建元组、查字典、`len()` 三次、`isinstance` 一次。

### 2.2 代价花在哪（cProfile 归因）

一趟 1 万行排序插入 = **2,212,871 次 Python 调用**（`tmp/t6_profile.txt`）：

| 调用点 | 次数 |
|---|---|
| `dir_model.py:index` | 101,851 |
| `pane.py:_entry` | 101,798 |
| `dir_model.py:data` | 98,902 |
| `pane.py:lessThan` | 50,899 |
| `internalPointer` / `isValid` | 302,509 / 302,564 |

换成便宜比较器后总调用降到 **1,619,459**，`data` 那 98,902 次**归零**（`tmp/t6d.log`）。
剩下的头名是 `index`（105,059 次，tottime 0.175s）—— 排序代理每次比较都要向源模型要两个索引，
而源模型的 `index()` 是 Python 覆写，每次都跨一次 PyQt 边界。

**视图侧另有一份代价**，与排序无关：把详情视图隐藏后，「源已排好 + 代理不排序」的心跳最大
从 100ms 掉到 **17ms**（`tmp/t6h.log` S1/S2）。也就是说 1 万行的布局/滚动条计算本身要 ~85–145ms，
它不在 `endInsertRows` 里，而是紧随其后的另一段停摆（B1 的次大间隔 143ms，隐藏视图后只剩 25ms）。

### 2.3 各条杠杆的实测收益

冷进程第一轮 + 同进程交错三轮（`tmp/t6b.log`、`tmp/t6c.log`、`tmp/t6j.log`）：

| 方案 | 单次插入最大 | 心跳最大 | 端到端 | 备注 |
|---|---|---|---|---|
| A 现状 | 312–343ms | 314–347ms | 334–367ms | 参照 |
| **B 名称列比较器直接读 `Entry.name`** | **164–188ms** | **167–192ms** | **184–209ms** | 三轮里每一轮都比 A 快（164<312、247<589、253<610） |
| C 只把 `index()` 改显式签名 | 465–484ms | — | 491–512ms | **没有收益**，见 §2.5 |
| D = B + C | 240–241ms | — | 267–268ms | 与 B 持平，C 不加分 |
| 分批 500（现比较器） | 26–27ms | 162–188ms | 2166–2176ms | 单次好看，总时长 5–6 倍 |
| 分批 500 + B | 13–22ms | 151–167ms | 1986–2058ms | 同上 |
| 分批 250 + B | 6ms | 151ms | 3671ms | 批越细总时长越差 |
| 挂起代理排序落地 + 落完一次性重排（B 比较器） | 插入 4ms + 重排 166ms | 261ms | 191ms | 总量不变，只是挪了位置 |
| **源在后台就排好 + 代理不排序** | **4–11ms** | **100ms**（视图可见）/ **17ms**（视图隐藏） | **26–38ms** | 排序那份代价整块消失，只剩视图布局 |
| `uniformRowHeights(True)` | 无一致收益 | 160–249ms | — | 早期两轮偏慢、后一轮持平，判为噪声 |
| 落地期间关 viewport 重绘 | 无收益 | 142–165ms | — | 不是重绘的锅 |

分批为什么越分越慢，`tmp/t6d.log` 的时间线给了直接证据 —— **批间间隔随已落地行数线性涨**：

```
9ms@500 → 34@1000 → 50@3000 → 71@5000 → 96@8000 → 131@10000
```

每投一批，代理/视图都要在「已经落地的 N 行」上重新算一次位置，于是总工作量近似 O(批数 × 行数)。
把批次数从 1 提到 20，单次停摆降了 20 倍，总停摆反而涨了 5 倍。

### 2.4 推荐方案：分三步，每步带一道决策门

**第一步（小、安全，建议先做）：名称列比较不再回模型取字符串。**

`core/pane.py:135-138` 改成直接用手上的 `Entry`：

```python
if col == 0:
    if le is not None and re is not None:
        return le.name.lower() < re.name.lower()
    l = left.data(Qt.ItemDataRole.DisplayRole) or ""
    r = right.data(Qt.ItemDataRole.DisplayRole) or ""
    return l.lower() < r.lower()
```

- 语义等价：`DisplayRole` 的名称就是 `Entry.name`（`dir_model.data` 同一来源），
  目录优先与降序反转在 `:110-113` 已经处理，这一段只管同类内部。
- 保留 `le/re` 为 None 时的旧路径（顶层节点等非条目索引），不改行为面。
- **不新增状态、不新增行信号、不动模型与视图的接缝**，铁律第 3 条（比较里不碰磁盘）天然满足。
- 收益：排序那一段停摆约降一半（冷态 340→180ms）。拍摄日期列（`:129-133`）仍走 `data()`，
  因为拍摄日期不在 `Entry` 上，本轮不动它。

**第二步（测量，不改代码）：把同一套探针搬到目标机复测。**

在 Linux 本地 ext4 的 1 万条目目录（L2 用过 `/home/kali/big10k`）跑第一步改前/改后各一轮，
再跑一轮 SMB 同条数靶子作 A/B。**决策门**：改后「心跳最大」是否 < **400ms**
（判据已由用户 2026-11-11 拍板放宽，见下）。

- 若达标 → T6 到此销账，第三步不做。
- 若不达标（按 3.7 倍外推，180ms × 3.7 ≈ 660ms，**大概率仍超 400ms**）→ 进第三步。

**第三步（大改，只在第二步不达标时做）：把排序挪到后台，落地时代理不排序。**

实测这是唯一能把排序那份代价整块拿掉的杠杆（插入 4–11ms）。形状：

1. 枚举任务在后台线程里**顺带排好序**（按当前排序列与方向，用 `Entry` 已缓存的字段，
   不碰磁盘 —— 铁律第 3 条在后台同样适用）；
2. 落地时让代理处于不排序状态，按源顺序投行；
3. 列头点击 → 不再让代理即时排，而是发起一次后台重排，排完再换顺序。

**这一步的代价必须写清楚**：现在「排序 + 筛选同一个代理」是一处设计（`docs/architecture.md:36`
明写「持有 `PaneSortProxyModel`（排序 + 筛选同一个代理）」，`core/pane.py:60-62` 的注释还钉着
「筛选不增行信号」这条约束），改成「模型排序、代理只筛选」要重做：
列头排序指示器与状态持久化（`core/pane.py:740`）、选中/光标恢复（`:2649`、`:2694`）、
改名后定位（`_index_for_path`，`core/dir_model.py:1195`）、以及所有断言 `lessThan` 行为的用例。
而且**视图布局那 ~100ms 拿不掉**（§2.2），所以第三步之后本机约 100–120ms、
Linux 外推约 350–400ms —— **刚好压在 400ms 线上，能不能过要看真机实测**。

### 2.4.1 验收判据已拍板（用户 2026-11-11）

**新判据：单次最大停摆 < 400ms，且落地期间有忙碌提示。** 原登记写的 200ms 作废，
`docs/todo.md` T6 行已同步。理由：1 万条目 + 可见列表的布局代价是 Qt 自己的，
模型侧再怎么改也拿不掉；为把 0.65s 压到 0.2s 去做架构大改，性价比不成立。

**「忙碌提示」这一半其实已经有了，先验再决定要不要补**：

- `core/pane.py:1510` `update_status_bar()`：节点还没加载完时状态栏显示 **「正在读取…」**（`:1523`）；
- `core/pane.py:1538` `_on_dir_loaded_status`：`directoryLoaded` 到达后刷成「N 个目录, M 个文件」。

时序上，导航时就把「正在读取…」写进状态栏 → 后台枚举期间事件循环照常重绘（本地 ext4 一万条目
枚举约 0.23s，足够画出来）→ 落地那一下主线程被占住，提示**留在屏幕上** → 落地完刷成计数。
所以**不需要新机制**。要做的是两件事：

1. **验它真的画出来了**：探针在落地前抓一帧状态栏文本，断言是「正在读取…」而不是空白或旧计数；
   缓存命中的目录（本来就已是加载态）不走这一支，要单独确认那条路径没有落地停摆。
2. 若实测发现提示没画出来（例如导航后立刻被别的事件抢走重绘），**再**考虑在落地前显式
   `processEvents()` 一次把提示刷上去 —— 那是几行的补法，不要一上来就加新信号或新控件。

**判据放宽后第三步的定位变了**：它不再是「为了达标必须做」，而是「第一步 + 提示在目标机复测后
仍超 400ms 才做」。按外推大概率还是要做，但**先拿真机数字再决定**，不要凭外推动工。

### 2.5 被否决的备选（附数据）

| 备选 | 否决理由 |
|---|---|
| **分批插入（登记时的首选）** | 单次插入 337→13ms 好看，但批间残余 O(已落地行数)（9→131ms），端到端 362→1986ms（5.5 倍），心跳最大只从 340 降到 151ms。且行信号从 1 次变 20 次 —— 行信号量正是本项目崩溃率的主因（`docs/unsolved-issues.md` 问题 13），要做必须附带 12–14 轮全量 A/B 抽样。**代价与风险都大于收益** |
| **把 `index()` 改成显式签名 + `type()` 判定** | 三轮实测 465/484/481ms，比现状（312/589/610）没有一致收益；叠在便宜比较器上（240ms）也不比只换比较器（247ms）好。v7 那次还多套了一层包装帧，10 万次额外调用把收益淹掉 —— 这本身是个教训：**测热路径时不要给它加包装** |
| **挂起排序落地、落完一次性重排** | 插入 4ms + 重排 166ms，总量与直接排序插入（168ms）持平，心跳反而更大（261ms vs 170ms）。若还去动视图的 `setSortingEnabled(True)`，它会再排一遍（v5 量到重排 230ms + 额外 ~150ms） |
| `setUniformRowHeights(True)` | 无一致收益（早期偏慢、后期持平），不采纳 |
| 落地期间 `setUpdatesEnabled(False)` | 142 vs 158ms，在噪声内；停摆不是重绘 |
| 在比较器里缓存小写键 | 未测。`.lower()` 在 profile 里只占 0.014s/10 万次，不是大头，先不做 |

### 2.6 铁律约束与风险

- **第 3 条**（比较/筛选不碰磁盘）：第一步只读 `Entry.name`，满足；第三步在后台排序同样只读缓存字段。
- **第 8 条 / gotchas #55**（`if 集合:` 守卫吞掉复位）：第一步不涉及；第三步若分批投行，
  空批必须照样走幂等守卫与 `loading` 复位，否则新数据被整份吞掉。
- **问题 13**（崩溃率随行信号量与枚举量走）：第一步**行信号次数不变**（仍是一趟），这是它比分批安全的关键。
  第三步若配合分批，行信号 ×20，必须做全量 A/B 抽样才能说「没退化」。
- **取消链路**（L2 已验收）：第一步不动 `_LoadTask` / `_should_stop`；第三步要把排序也纳入
  同一个取消令牌，且记住 gotchas #58 —— 取消标志拦不住已经阻塞在 syscall 里的线程。
- **`directoryLoaded` 只能发一次**：`core/pane.py:2694` `_on_dir_loaded_restore` 靠它恢复选中与光标，
  任何分批方案都只能在最后一批发完时 emit，否则恢复逻辑会跑多次。
- **`DirNode.__slots__`**（`core/dir_model.py`，字段 `path/key/entries/loaded/loading/gen/_stale/ts/abandoned`）：
  第三步若要记「已落地到第几行」，必须同时改 `__slots__`，否则 `AttributeError`。
- **读路径全部以 `loaded` 为门**：`index()`（`:1171`，`not p.loaded` 直接返回 invalid）、
  `rowCount()`（`:1226`）、`_index_for_path`（`:1195`）、`loaded_counts`（`:1010`，未 loaded 返回 None）。
  分批落地时「部分行已可见但 `loaded` 还是 False」会让这些读路径整片返回空 —— 这是分批方案的隐藏成本，
  也是 §2.5 否掉它的另一条理由。

### 2.7 测试计划

**offscreen 用例（第一步）**

1. 排序等价性：同一批条目，改前/改后 `lessThan` 对名称列的判定逐对一致（含大小写混合、
   目录与文件混排、升序/降序两种方向）。
2. 1 万条目落地后读全表：行数不多不少、目录在前、同类内单调（探针里的抽查断言搬进用例）。
3. 现有排序/筛选用例全绿（`tests/test_pane_dir_store.py` 等），确认没改行为面。
4. **忙碌提示（新判据的另一半）**：导航到一个未加载的大目录后、落地之前，
   断言状态栏概要是「正在读取…」（`core/pane.py:1523`）；`directoryLoaded` 之后断言刷成计数。
   缓存命中的目录单独一条：确认它不显示「正在读取…」且没有落地停摆。

**offscreen 用例（第三步，若做）**

5. 列头点击后排序结果与改前一致；排序状态持久化往返一致。
6. 落地中途导航走：不采纳旧目录的行、`loading` 复位、`directoryLoaded` 只发一次。
7. 空目录 / 只有 1 条 / 恰好等于批大小 / 批大小+1 四个边界（gotchas #55）。
8. 改名后定位、选中恢复在 1 万行上仍命中正确行。

**真机项（记进 `docs/linux-gap.md`，不占 T 号）**

9. Linux 本地 ext4 1 万条目：改前/改后各一轮，报三个指标 + 冷进程口径，
   **按新判据卡「心跳最大 < 400ms」**，并抓一帧确认忙碌提示真的画出来了。
10. SMB 同条数靶子 A/B 一轮。
11. 若做第三步：全量 `tests/` 跑 12–14 轮抽样崩溃率，与改前基线对照（问题 13 的方法）。

**探针注意事项（写进测试文档，避免下次再踩）**

- 给 `pyqtSlot` 装饰过的槽做「读类属性→写回」会丢签名元数据，下次建模型时
  `connect() failed between _LoadSignals.finished[...] and _on_entries_loaded()`。
  要替换就**常驻一个普通函数包装**，靠开关决定行为，别反复赋值。
- 测热路径不要给它套 dispatch 包装（每层包装 = 每次调用多一帧）。
- 计时一律 `time.perf_counter()`，不要和 `time.time()` 混用。

### 2.8 工作量

- 第一步：代码 ~6 行 + 用例 2 条，**半天内**（含全量复跑）。
- 第二步：真机探针一轮，**半天**（依赖能在 230 上跑）。
- 第三步：**3–5 天**（含排序状态/恢复/定位重做 + 崩溃率抽样）。判据已拍板（§2.4.1），
  但**要不要做仍取决于第二步的真机数字**：改后心跳最大 < 400ms 就不做。

---

## 3. T7 · 文件列表键位

### 3.1 现场与出处（更正后）

`core/pane.py:209` `FileListTreeView.keyPressEvent` 只截 Ctrl+F（`:211-214`）与
Shift+Delete（`:218-222`），其余交 `super()`。End/Home/Ctrl+End/Ctrl+Home/PgUp/PgDn
全走 Qt 默认。

200 条目、视口 854×222 的实测矩阵（`tmp/t7b.log`、`tmp/t7d.log`）：

| 键 | 详情视图 | 简单列表 | 超大图标（干净实例） |
|---|---|---|---|
| End | row 5→199，选中 199 ✅ | 5→199 ✅ | 5→199 ✅ |
| **Ctrl+End** | row 5→199，**选中仍是 5** ❌ | 同 ❌ | 同 ❌ |
| Home | 5→0，选中 0 ✅ | ✅ | ✅ |
| **Ctrl+Home** | 5→0，**选中仍是 5** ❌ | 同 ❌ | 同 ❌ |
| Shift+End | 选中 5..199（195 行）✅ | ✅ | ✅ |
| PageDown | 5→16 ✅ | 5→9 ✅ | **5→5**（视口只装得下 1 行网格时） |

**PgDn 那一格不是「键没实现」**：换视口高度再量（`tmp/t7e.log`），
222px→移动 0 行、400px→5 行、600px→10 行、900px→15 行，
即 Qt 按「一页 = 可见网格行数 − 1」算，装得下 1 行时就是 0。属边界算术，不是缺失绑定。

另：超大图标那组必须用**从未进过简单列表的新实例**量。同一个实例先进简单列表再切回来，
`flow` 会残留成 `TopToBottom`，图标变成一条横带（横向滚动上限 31148、纵向 0），
键位结果跟着失真 —— 这是 §6.1 的新缺陷，与 T7 是两件事。

### 3.2 目标与验收判据

- Ctrl+End / Ctrl+Home 在**三种视图**里都「光标 + 滚动 + 选中」一起到末/首条（资源管理器习惯）。
- End / Home / Shift+End / Shift+Home 的现有行为**不变**（本来就对）。
- PgDn/PgUp 在「视口只装得下一行网格」时至少移动一行（可选，见 §3.4）。
- 真机 Windows / Linux 各一轮手测。

### 3.3 方案

在视图自己的 `keyPressEvent` 里截 Ctrl+End / Ctrl+Home，**在 `super()` 之前**：

- 详情视图：`core/pane.py:209` 的 override 里加两个分支，取代理的末行/首行索引，
  `setCurrentIndex(...)` + `selectionModel().select(..., ClearAndSelect)` + `scrollTo(...)`。
- 超大图标 / 简单列表 / 平铺：同一个 `ThumbnailView` 实例（`widgets/thumbnail_view.py`），
  加同形状的 override，用 `setCurrentRow(count()-1 / 0)`。
- 两处共用一个小助手（放 `core/pane.py` 或 `widgets/` 均可），避免又写成两份 —— T8 的教训。

**为什么不用 QShortcut**：`core/pane.py:465-471` 的注释说明 Tab 必须用 `QShortcut`，
因为 QAbstractItemView 的内建处理排在 `keyPressEvent` 之前。Ctrl+End 不同：
实测光标确实动了，而动的唯一路径就是我们 override 里的 `super().keyPressEvent(event)`，
说明这个键**到得了** Python override，直接在里面截即可。Tab 那条经验不能外推到所有键。

### 3.4 被否决的备选

| 备选 | 否决理由 |
|---|---|
| 重映射普通 End / Home | 实测本来就对，改它只会破坏 Shift+End 的范围选择与用户肌肉记忆 |
| 用 `QShortcut` 绑 Ctrl+End | 多余：键到得了 override；而且快捷键落点要守铁律第 6 条（只认 `target_pane()`），视图内处理自己的选中不涉及跨窗格落点，更简单 |
| 把 PgDn/PgUp 一律改成「移动一整页」 | 那是 Qt 的既有算术，正常视口下行为正确；只在「装得下一行」时退化。建议**只补这一种边界**（至少移动一行网格），不动其余 |
| 顺手修 flow 残留 | 是另一个缺陷（§6.1，新登记 T10），混在一起会让 T7 的验收证据被污染 |

### 3.5 测试计划

1. offscreen 键位矩阵用例：三种视图 × {End, Ctrl+End, Home, Ctrl+Home, Shift+End}，
   断言**光标行、滚动位置、选中集合**三者（只断言光标会漏掉本条真正的缺口）。
2. 超大图标用例必须用**新建实例**，并在用例里断言 `flow() == LeftToRight`，
   防止 T10 的残留把结果带偏。
3. PgDn 边界：视口高度设成「只装得下一行网格」，断言至少移动一行（若采纳 §3.4 的可选项）。
4. 真机手测一轮（Windows / Linux），记进 `docs/linux-gap.md`。
5. **产物版 End 键复测（未闭环项，优先级高于手测）**：`docs/linux-gap.md` L2 行记的是产物版
   （冻结 ELF + 真 X）单按 End 不跳尾，而本轮 offscreen 源码版三种视图都跳尾。
   复测步骤：先点列表里的一行把焦点交给列表（截图确认焦点框），再按 End，再按 Ctrl+End；
   判据是「光标 + 滚动 + 选中」三者。若产物版仍不跳尾，说明冻结产物与源码版有差异
   （PyInstaller 打包的 Qt 插件/样式或焦点策略），**另立条目**，不要混进 T7 的键位改动里。

### 3.6 工作量

代码 ~40 行（两处 override + 一个助手）+ 用例 1 组，**半天到一天**。风险低。

---

## 4. T8 · 「在系统文件管理器中选中」合一

### 4.1 现场与出处

两份实现：

- `widgets/advanced_search.py:766` `reveal_in_system_manager`：`for p in paths[:5]`，
  win32 走 `subprocess.Popen(f'explorer /select,"{p}"')`（**命令行字符串**），
  darwin 走 `["open", "-R", p]`，其余 `["xdg-open", os.path.dirname(p)]`（**只打开目录，不选中**）；
  `except OSError` → `logger.warning`；超过 5 个时状态栏写「共 N 项，只在系统文件管理器里定位前 5 个」。
  结果路径在 `:100` 由 `os.path.join(root, filename)` 拼出，定位前不做 normpath。
- `core/pane.py:2115` `_reveal_in_file_manager`：`os.path.normpath` → `_win_unc_fix`（`:2137`）
  → `subprocess.Popen(['explorer', '/select,', norm])`（**argv 列表**）；darwin 同；
  其余走 `QDesktopServices.openUrl(dirname)`（同样不选中）；失败写状态栏。

**UNC 那条理由已撤回**（§0）：本机 `normpath` 不压双前导反斜杠。`_win_unc_fix` 真正还在做的事
是把 `/` 换成 `\`（混合分隔符时有用），保留它，但不再宣称它修了 UNC 定位。

**两种 Windows 命令行形式的差异（实测到字符串层面，行为未验）**：

```
argv 形式    : explorer /select, "C:\Users\me\My Documents\a b.txt"   ← 逗号后有空格
字符串形式   : explorer /select,"C:\Users\me\My Documents\a b.txt"    ← 逗号后无空格
```

本轮**故意没有真的拉起 Explorer 窗口**（会在用户桌面上弹窗），所以「哪种形式在带空格路径 /
UNC 路径下真能选中」属**待真机实测**，不在本文里断言。

### 4.2 目标与验收判据

- 全仓只剩一处真实现（另一处是 delegate）：`grep -rn "explorer" --include=*.py core widgets`
  只命中助手模块 + 一处 delegate。
- Linux 真机 KDE `dolphin --select <path>` 或 GNOME `nautilus --select <path>`
  **至少一种能把文件高亮选中**，而不是只打开所在目录。
- 现有上限与文案不变（5 个 + 「前 5 个」），`tests/test_search_results.py:320` 保持绿。
- `tests/test_phase1_shell_behavior.py:208-210` 钉住的 `Pane._win_unc_fix` 保持可用。

### 4.3 方案

新增一个小助手（建议 `core/reveal.py`，纯执行、不认识窗格），签名形如
`reveal_in_file_manager(paths, limit=5) -> RevealResult`，返回「实际打开了几个 / 为什么没打开」，
由调用方决定写哪个状态栏。

- **Windows**：统一成**一种**形式，且用 argv 列表（不经 shell，路径里的空格与特殊字符天然安全）。
  具体选 argv 还是字符串，由 §4.5 的真机实测决定 —— **先测再定，不拍脑袋**。
  附带一条已知事实：Explorer 即使成功也常返回退出码 1，**不要拿 returncode 判成败**。
- **macOS**：`["open", "-R", path]`（两边本来就一致）。
- **Linux**：按桌面环境挑能选中的参数，挑不到再回落：
  1. KDE（`XDG_CURRENT_DESKTOP` 含 KDE 或 `KDE_FULL_SESSION`）且 `shutil.which("dolphin")`
     → `["dolphin", "--select", path]`；
  2. GNOME 且有 `nautilus` → `["nautilus", "--select", path]`；
  3. 都没有 → `["xdg-open", dirname]`（现状行为，明确告知「只打开了所在目录」）。
  参数可用性**全部标为待真机实测**，不写成既定事实。
- **两处调用方都改成 delegate**：`core/pane.py:2115` 保留方法名与 `_win_unc_fix`（用例钉着），
  内部转调助手；`widgets/advanced_search.py:766` 同样转调，上限与文案留在调用方。
- 失败处理统一：助手只返回结果，不弹窗、不写日志以外的 UI（铁律：别把异常咽进模态框，gotchas #56）。

### 4.4 被否决的备选

| 备选 | 否决理由 |
|---|---|
| 只把搜索侧改成调窗格的方法 | 搜索对话框的 `pane_for_ops()`（`widgets/advanced_search.py:671`）**可能返回 None**（未连接主窗口），那条路会直接断；助手必须不依赖窗格 |
| Linux 走 D-Bus `org.freedesktop.FileManager1.ShowItems` | 理论上比命令行参数稳（GNOME 官方接口），但需要会话总线与目标服务在跑，**本轮未实测**。列为备选，真机验完再决定是否替换命令行方案 |
| 保留两份实现、只补 Linux 参数 | 同一件事两处写就是本条待办的成因，补完还会再分叉 |
| 顺手把上限 5 改成可配置 | 超出本条范围，且有用例钉着 5；要改另立条目 |

### 4.5 测试计划

**offscreen**

1. 助手在三种平台分支下拼出的 argv 正确（monkeypatch `sys.platform` 与 `shutil.which`），
   断言**不经 shell**（`Popen` 收到的第一个参数是 list）。
2. 上限与文案：6 个路径 → 恰好 5 次调用 + 状态栏含「前 5 个」（沿用现有用例的断言形状）。
3. `pane_for_ops()` 返回 None 时搜索侧仍能定位（不依赖窗格）。
4. 带空格路径、带非 ASCII 路径、UNC 路径各一条，断言拼出的命令行字符串。
5. 现有 `tests/test_search_results.py:320` 与 `tests/test_phase1_shell_behavior.py:208-210` 保持绿。

**真机（待实测清单，逐项附自查命令）**

| # | 要验的事 | 自查命令 | 判据 |
|---|---|---|---|
| 1 | Windows argv 形式能否选中带空格路径 | `explorer /select, "C:\...\a b.txt"` | 资源管理器打开且该文件高亮 |
| 2 | Windows 字符串形式同上 | `explorer /select,"C:\...\a b.txt"` | 同上；两者取其一写进助手 |
| 3 | Windows UNC 路径能否选中 | `explorer /select,"\\nas\share\dir\f.txt"` | 同上（靶子需用户授权后造） |
| 4 | Linux KDE 选中 | `dolphin --select /path/to/f.txt` | 文件高亮，不只是打开目录 |
| 5 | Linux GNOME 选中 | `nautilus --select /path/to/f.txt` | 同上 |
| 6 | 回落路径 | `xdg-open /path/to` | 打开所在目录，且 UI 明说「未选中」 |

### 4.6 工作量

助手 ~60 行 + 两处 delegate + 用例 5 条，**一天**（不含真机验证排队）。
真机 6 项需要人在桌面环境前，记进 `docs/linux-gap.md`。

---

## 5. T9 · 拍摄日期预读改受管线程

### 5.1 现场与出处（原判断成立，且更严重）

`core/pane.py:869` `_prefetch_shot_dates`：

- 主线程遍历当前目录所有行收集路径（`:890-897`，`model.index/isDir/filePath` 逐行往返）；
- `work()` 在后台线程调 `batch_get_shot_dates(paths)`（`:908`），再 `self._emit_ui("shot_dates_ready")`（`:911`）；
- **`:915` `threading.Thread(target=work, daemon=True).start()`** —— 无池、无取消、无「窗格还在不在」的判据。
- 触发点三处：`:760`、`:983`、`:1562`（`call_later(self, 0, self._prefetch_shot_dates)`），
  即「拍摄日期列可见 + 目录加载完」每次导航都可能起一个。

`core/media_metadata.py:182` `batch_get_shot_dates` 按 `_EXIFTOOL_CHUNK = 500`（`:179`）分批，
每批 `_run_exiftool` 用 `subprocess.run(..., timeout=30)`（`:155`）。**今天没有取消参数**。

实测（`tmp/t9.log`，用 2 秒的替身顶替 exiftool）：

```
基线活跃线程 = 1
20 次快速导航：峰值活跃线程 = 17，预读发起 = 21 次
已 sip.delete(pane)，此时活跃线程 = 17
3 秒后：活跃线程 = 1，替身跑完 = 21 次，逃出去的异常 = 0
```

三条结论：

1. **并发无上限**：20 次导航堆出 17 个同时在飞的线程。换成真 exiftool，就是**最多 17 个并发子进程**
   在啃同一批文件（SMB 上尤其糟）。
2. **为死窗格白干**：窗格销毁后 21 个任务**全部跑完**，没有一个中途停下。
3. **跨线程投递本身是安全的**：`_emit_ui`（`:852`，getattr 放进 try）兜住了已销毁 QObject，
   逃出去的异常 0 个 —— 铁律第 5 条这一半已经做对了，缺的是**任务生死与并发上限**。

### 5.2 目标与验收判据

- 建 pane → 显示拍摄日期列 → 导航 → 立刻 `sip.delete(pane)` → 等预读跑完：
  **无 RuntimeError、无回投到死窗格的信号、活跃线程数回到基线**。
- 连续快速导航 20 次，**在飞线程数不超过池上限**。
- 窗格销毁或再次导航后，**旧任务不再继续啃后续批**（取消生效）。
- `tests/test_terminal_lifecycle.py:273-278` 直接调 `p._emit_ui("shot_dates_ready")`（无参），
  **信号签名不能改**。

### 5.3 方案

四件事，形状照抄已经验证过的 `dir_model` 那套（不发明新机制）：

1. **有界线程池**：新增 `shot_pool()`，`QThreadPool` 上限 **2**（与 `dir_pool()` 4 /
   `size_pool()` 2 同一风格，`core/dir_model.py:293`/`:318`）。
   落点建议 `core/media_metadata.py`（它本来就是 exiftool 的归属地，这样**并发子进程数也一并被封顶**），
   由 `core/pane.py` 延迟 import 使用。
2. **任务身份 + 代际**：窗格持一个 `_shot_gen` 计数与 `_pending_shot` 当前任务引用；
   每次导航/发起预读时 +1。任务回投时校验「代际没变 + 我还是当前任务 + 窗格还活着」，
   否则丢弃结果。这与 `_on_entries_loaded` 的 gen/任务身份守卫同构。
3. **取消令牌**：`batch_get_shot_dates(paths, cancel=None)` 增加可选取消回调，
   **每批（500 个）之间探一次**；命中就停止后续批并返回已得结果。
   令牌形状沿用 `_LoadTask.__call__ = _should_stop`（gotchas #54：方向是「该停了吗」，别写反）。
   **诚实标注局限**：gotchas #58 —— 取消标志拦不住已阻塞在 syscall 里的线程，
   所以**在飞的那一批 exiftool（≤30s 超时）会跑完**，浪费上限是 500 个文件而不是整个目录。
4. **回投走 QObject 归属**：任务持一个以窗格为父的信号对象（照 `_LoadSignals(self)` 的做法，
   `core/dir_model.py:531-532`），`done` 信号连到窗格的刷新槽。窗格销毁 → 子对象销毁 →
   已排队投递自动剔除。**不要**改成无 QObject 归属的 closure（问题 13 的实测教训写在 `:525-530` 的注释里）。
   `_emit_ui` 保留作为第二道防线，信号名与签名不变。

**顺带一处主线程开销**（可选，同属本条）：`:890-897` 逐行 `index/isDir/filePath` 收集路径，
在 1 万条目上是一次额外的主线程往返（拍摄日期列可见时才发生）。若模型已有「直接拿当前目录条目」
的访问口，改成读缓存条目即可；**没有现成访问口就不要为此新加 API**，先留着并记一笔。

### 5.4 被否决的备选

| 备选 | 否决理由 |
|---|---|
| 只加「窗格还活着吗」的判断，仍用裸线程 | 解决不了并发无上限（17 个线程 / 17 个 exiftool 子进程），也解决不了白干 |
| 用全局 `QThreadPool.globalInstance()` | 全局池并发数按 CPU 核数，`dir_model` 正是因此才另开专用池（`core/lifecycle.py:88-89` 的注释）；预读要的是**小额定并发**，不是抢全局池 |
| 每窗格一个池 | 四个窗格就是 4×N，上限又失控；预读是全局资源（exiftool 子进程），该全局封顶 |
| 给 exiftool 子进程发终止信号来「立即取消」 | 跨平台杀子进程 + 清理临时 args 文件的复杂度远超收益；批间取消已把浪费封到 500 个文件 |
| 顺手把 `_run_archive_task`（`core/pane.py:2022`）也改 | 登记时已明确排除：那是用户点一次起一个、天然有限。要改另立条目 |

### 5.5 铁律约束与风险

- **第 5 条**：信号接收者必须是目标 QObject；延后执行用 `call_later`（`core/lifecycle.py:69`）
  而不是 `QTimer.singleShot`；退出走 `exec_and_drain`。
- **退出排空必须点名新池**：`core/lifecycle.py:85` `_pools_to_drain()` 现在只列全局池 + `dir_pool()`。
  加了 `shot_pool()` 就要同时加进去，否则未派发的投递留到解释器收尾阶段被 Qt 释放 →
  Windows 上 fast-fail（0xC0000409），就是问题 13 那一类。**这一条同时暴露了现存漏洞，见 §6.2（T11）**。
- **第 4 条**：任务对象与信号对象的生死不要交给分代 GC，父子关系挂清楚。
- 风险：取消令牌方向写反（gotchas #54）会让任务**立刻全停**或**永不取消**，用例要两个方向都断言。

### 5.6 测试计划

1. **销毁窗格**：建 pane → 显示拍摄日期列 → 导航 → `sip.delete(pane)` → pump 到线程回基线；
   断言无 RuntimeError、无信号投到死窗格、替身**不再继续后续批**。
2. **并发上限**：连续快速导航 20 次，断言在飞线程数 ≤ 池上限、发起次数被合并/丢弃而不是 21 次全跑。
3. **取消两个方向**：令牌返回「该停」→ 后续批不调用；返回「继续」→ 全部批调用。
4. **代际守卫**：旧任务在新导航之后回投 → 结果被丢弃，不刷新新目录的列。
5. **信号签名不变**：`p._emit_ui("shot_dates_ready")` 无参调用仍不抛（现有用例保持绿）。
6. **退出排空**：`_pools_to_drain()` 含 `shot_pool()`（与 T11 的用例合并写）。
7. 真机：Windows / Linux 各一轮「打开拍摄日期列 → 快速切 20 个目录 → 关窗格」，
   看任务管理器里 exiftool 子进程数是否被封顶、退出是否报错。

### 5.7 工作量

代码 ~120 行（池 + 令牌 + 信号对象 + 两处接线）+ `batch_get_shot_dates` 加一个可选参数
+ 用例 6 条，**1–2 天**。与 T11 一起做最省（同一条退出排空链路）。

---

## 6. 顺带查出的两处新缺陷（不在 T6–T9 内，已另立编号）

### 6.1 T10 · 视图模式切回超大图标后 `flow` 残留，图标变成一条横带

**现场**：`widgets/thumbnail_view.py:315` `set_simple_list_mode`，
`on` 分支在 `:331` 设 `setFlow(TopToBottom)`（简单列表要多栏纵向流，这是对的），
但 `else` 分支（`:340-347`）设了 viewMode/iconSize/gridSize/spacing/wordWrap/wrapping/uniformItemSizes，
**唯独没有把 `flow` 设回 `LeftToRight`**。`set_tile_mode`（`:276`，else 分支 `:292-295`）同样没设。

**实测**（`tmp/t7c.log`、`tmp/t7d.log`）：

```
A 直接超大图标            viewMode=IconMode flow=LeftToRight  hmax=0     vmax=7380   ← 正常网格
B 简单列表                viewMode=ListMode flow=TopToBottom  hmax=17    vmax=0      ← 正常多栏
B 切回超大图标            viewMode=IconMode flow=TopToBottom  hmax=31148 vmax=0      ← 一条横带
```

**后果**：用户从「简单列表」切回「超大图标」，1 万个图标排成一行横向长带，
纵向滚动条消失、横向滚动上限 3 万多像素；End 键也跟着变成横向跳（§3.1 的矩阵污染就是它造成的）。

**方案**：两个 else 分支各补一行 `self.setFlow(QListView.Flow.LeftToRight)`。
**这是代码改动，等用户批准**（本文件只登记，不动手）。

**验收**：offscreen 用例断言「简单列表 → 超大图标」后 `flow() == LeftToRight`、
`verticalScrollBar().maximum() > 0` 且 `horizontalScrollBar().maximum() == 0`（条目数足够时）；
平铺 → 超大图标同样断言。真机看一眼图标是否恢复网格。

**工作量**：2 行 + 用例 2 条，**半小时**。建议与 T7 同一批做（T7 的键位用例正被它污染）。

### 6.2 T11 · 退出排空漏了两个线程池

**现场**：`core/lifecycle.py:85` `_pools_to_drain()` 只返回
`[QThreadPool.globalInstance(), dir_pool()]`（`:92-97`）。而仓里还有：

- `core/dir_model.py:318` `size_pool()`（目录占用计算，2 线程）—— **不在排空名单里**；
- `widgets/thumbnail_view.py:256` 每实例一个 `QThreadPool`（4 线程），
  只在 `closeEvent`（`:690`）里排空 —— 应用退出时并非每个控件都会收到 `closeEvent`。

**后果**：与问题 13 同一类 —— 未派发的跨线程投递留到 `~QCoreApplication` 之后被 Qt 释放，
那时 CPython 可能已开始 finalize，Windows 上退化为 fast-fail（0xC0000409，无可捕异常），
用户侧就是「关掉程序时报错」。`drain_background_pool` 的文档字符串（`core/lifecycle.py:101`）
把这条机理写得很清楚，只是名单没跟上。

**方案**：
1. `_pools_to_drain()` 补 `size_pool()`（与 `dir_pool()` 同样的延迟 import + try 兜底）。
2. 缩略图池：要么在模块级维护一个实例弱引用集合、退出时逐个排空，
   要么把它改成全局有界池（与 T9 的 `shot_pool()` 同一思路）。
   **两种形状各有代价**（弱引用集合要处理销毁时序；全局池要重新核对四个窗格的并发上限），
   建议**先做第 1 步**（一行、零风险），第 2 步与 T9 一起设计。
3. T9 落地时把 `shot_pool()` 一并加进名单。

**验收**：用例断言 `_pools_to_drain()` 覆盖仓内所有 `QThreadPool` 实例来源
（可用 grep 出的清单做反向守卫，防止以后新增池又漏）；退出路径真机跑一轮看有无 0xC0000409。

**工作量**：第 1 步 ~3 行 + 用例 1 条，**半小时**；第 2 步随 T9。

---

## 7. 建议次序与工作量汇总

| 次序 | 做什么 | 为什么排这里 | 工作量 | 是否需要批准 |
|---|---|---|---|---|
| 1 | **T10 flow 残留**（2 行）+ **T11 第 1 步**（3 行） | 都是几行的小修，且 T10 会污染 T7 的验收证据、T11 与 T9 同一条链路 | 半天（含用例与全量） | 代码改动需批准 |
| 2 | **T7 键位**（Ctrl+End / Ctrl+Home） | 缺口明确、风险低、用户天天按 | 半天–一天 | 需批准 |
| 3 | **T6 第一步**（名称列比较器） | 6 行换掉一半停摆，不动接缝、不加行信号 | 半天 | 需批准 |
| 4 | **T9 + T11 第 2 步**（受管池 + 取消 + 排空名单） | 一起做最省；解决 17 个并发 exiftool 与退出报错 | 1–2 天 | 需批准 |
| 5 | **T8 合一 + Linux 选中** | 需要真机验参数，代码部分可先做 | 一天 + 真机排队 | 需批准 |
| 6 | **T6 第二步**（目标机复测，卡新判据 400ms + 忙碌提示）→ 超了才做第三步 | 判据已拍板（§2.4.1）；第三步是大改，要拿真机数字再决定，不凭外推动工 | 半天；第三步 3–5 天 | 复测不需批准；第三步需批准 |

**发布口径**：以上都属「攒着尚未出包的这一批」。按 `AGENTS.md`「变更记录」一节，
使用者能感知的条目记进 `CHANGELOG.md` 的 `[1.9.049] - 未发布`，
`config/app_config.py` 的 `VERSION`、`pyproject.toml` 的 `version` 与 tag **仍停在 1.9.048**，
真正出包那一刻才 +1。任何一批做完都要跑**完整** `tests/` 并拿到汇总行
（写方案时的基线是 **800 passed / 5 skipped**；**2026-11-13 落地后是 883 passed / 5 skipped**），
跑不完就是跑不过（gotchas #56）。

> **2026-11-13 出包后记（上面这段原文保留，只补现状）**：用户同日拍板「出 049 版本包并上传」，
> 这一批**已不再是未发布**——`VERSION` 与 `pyproject` 已同步到 **1.9.049**、CHANGELOG 该节标题改成
> `2026-11-13（master）`、tag `v1.9.049`。出包时按该节自己的括注，把「用户操作配置层四处修复」
> 那条**从正式发布说明里挪掉**了：入口仍挂在 **T2** 第二步没接线，使用者摸不到，
> 不符合「只写用户能感知的变化」；修复本身已在包里，账记在 `docs/todo.md` 的 T2 行。

---

## 8. 探针与证据清单

全部在 gitignore 的 `tmp/` 里，**不入库**；**2026-11-11 那一轮**产品代码与测试代码一行未改
（11-12 的落地改动、新增用例与对照组插件见 §9）。

| 脚本 | 日志 | 证明了什么 |
|---|---|---|
| `tmp/t6_landing_probe.py` | `tmp/t6.log`、`tmp/t6_profile.txt` | 三阶段计时 + cProfile 归因（222 万次调用） |
| `tmp/t6b_lessthan_probe.py` | `tmp/t6b.log`、`tmp/t6c.log` | 便宜比较器 / 分批 500 / 分批 250 / 关重绘 / uniformRowHeights 的 A/B |
| `tmp/t6d_timeline_probe.py` | `tmp/t6d.log` | 批间残余随已落地行数线性涨（9→131ms）；调用数对比 |
| `tmp/t6e_suspend_sort_probe.py` | `tmp/t6e.log` | 挂起排序落地 + 落完重排；视图 `setSortingEnabled(True)` 会再排一遍 |
| `tmp/t6f_presort_probe.py` | `tmp/t6f.log`、`tmp/t6f_profile.txt`、`tmp/t6g_profile_presort.txt` | 只挂代理排序；源已排好的地板价；便宜比较器的 profile |
| `tmp/t6h_viewcost_probe.py` | `tmp/t6h.log` | 隐藏视图分离出视图侧 ~85–145ms；uniform / 关重绘无收益 |
| `tmp/t6i_fastindex_probe.py` | `tmp/t6i.log` | 快 index 初测（含包装帧混淆，结论由 v8 取代） |
| `tmp/t6j_interleaved_probe.py` | `tmp/t6j.log` | A/B/C/D 交错三轮：比较器方向确定有效、快 index 无收益、波动幅度 |
| `tmp/t7b_views_probe.py` | `tmp/t7b.log` | 三视图键位矩阵（End 有效、Ctrl+End 选中不动） |
| `tmp/t7c_flow_probe.py` | `tmp/t7c.log` | flow 残留隔离（T10） |
| `tmp/t7d_clean_icon_probe.py` | `tmp/t7d.log` | 干净超大图标实例的键位矩阵（排除 T10 污染） |
| `tmp/t7e_pagedown_probe.py` | `tmp/t7e.log` | PgDn 移动行数随视口高度变化（0/5/10/15），不是缺失绑定 |
| `tmp/t9_thread_probe.py` | `tmp/t9.log` | 21 次发起 / 峰值 17 线程 / 销毁后全部跑完 / 0 逃逸异常 |

**探针里出现的原型代码（`fast_lt`、`chunked_slot`、`fast_index`、`suspend_slot`）都只存在于探针进程，
不是产品改动**；本文引用的行号一律指仓库当前文件，已逐条核对。

---

## 9. 落地回执（2026-11-13，用户「开工 T6 到 T11」）

按 §7 的次序做完：T10 + T11① → T7 → T6① → T9 + T11② → T8 → 全量 + 文档同步。
**全量 `tests/` 跑出汇总行：883 passed / 5 skipped（134.15s，Windows offscreen）**，
比写方案时的基线（800 / 5）多 83 条用例。`VERSION` / `pyproject` / tag **仍停在 1.9.048**，
使用者可感知条目攒在 `CHANGELOG.md` 的 `[1.9.049] - 未发布`，**未提交**。

### 9.1 改了哪些文件

| 文件 | 改动 | 归属 |
|---|---|---|
| `widgets/thumbnail_view.py` | 两个外观 setter 的「离开本模式」分支各补 `setFlow(LeftToRight)`；模块级 `_LIVE_VIEWS`（`weakref.WeakSet`）+ `live_thumbnail_pools()`；`keyPressEvent` 调共用键位助手 | T10 / T11② / T7 |
| `core/lifecycle.py` | `_pools_to_drain()` 点名全局池 + `dir_pool()` + `size_pool()` + `shot_pool()` + `live_thumbnail_pools()`，每个来源各自 lazy import + try/except | T11①② |
| `widgets/view_keys.py`（新增） | `handle_edge_jump(view, event)`：Ctrl+End / Ctrl+Home 让光标 + 整行选中 + 滚动一起走 | T7 |
| `core/pane.py` | `FileListTreeView.keyPressEvent` 开头调助手；名称列比较器改读 `Entry.name`；`_prefetch_shot_dates` 改投受管池 + 代际守卫 + `_on_shot_dates_done`；`_reveal_in_file_manager` 与 `_win_unc_fix` 改 delegate | T7 / T6① / T9 / T8 |
| `core/media_metadata.py`（新增部分） | `shot_pool()`（上限 2）、`ShotCancel`、`ShotDateSignals`、`ShotDateTask`；`batch_get_shot_dates(paths, cancel=None)` 批间探令牌且**不往缓存写 None** | T9 |
| `core/reveal.py`（新增） | `reveal_in_file_manager(paths, limit=5) -> RevealResult`、`win_unc_fix`、三平台 argv 拼装 | T8 |
| `widgets/advanced_search.py` | `reveal_in_system_manager` 改 delegate，上限与文案留在调用方，失败/未选中两条提示不再互相吞掉 | T8 |

新增用例：`tests/test_view_keys.py` 29、`tests/test_reveal.py` 36、`tests/test_shot_prefetch.py` 8、
`tests/test_sort_landing.py` 4；`tests/test_tile_view.py` +3（12→15）、`tests/test_shutdown_drain.py` +3（5→8）。

### 9.2 逐项回执（每条都先在对照组里红一次）

对照组插件在 gitignore 的 `tmp/`（`t7/t8/t9/t10/t11_ab_plugin.py`），只在
`pytest_collection_finish` 里把产品代码还原成旧样子，跑法见 `docs/linux-gap.md` §5.3。

| 项 | 改后 | 对照组（旧样子） | 判据命中 |
|---|---|---|---|
| **T10** | `test_tile_view.py` 15 passed | 红 **4** 条用例（11 passed） | flow 回 LeftToRight、纵向滚动条 >0、横向 ==0 ✅（offscreen）；真机看一眼 → L16 |
| **T11** | `test_shutdown_drain.py` 8 passed | **4 failed / 3 passed / 1 skipped**（名单守卫两条 + 在飞送达 + 排空后池空闲） | 名单覆盖四个池来源 + 每个存活视图的池 ✅；真机退出码 → L16 |
| **T7** | `test_view_keys.py` 29 passed | 红 **9** 条（8 个 Ctrl+End/Home + 1 条独立视图） | 4 视图 × 6 键位，光标/选中/可见三个观测量 ✅（offscreen）；真机手测 → L16 |
| **T6①** | `test_sort_landing.py` 4 passed；A/B 三轮交错：旧写法插入最大 312/493/538ms、心跳最大 314/496/540ms，新写法 186/288/356ms 与 189/292/359ms | —（A/B 本身就是对照） | **每轮都赢**，最差 359ms **< 400ms**（本机）✅；忙碌提示 6/6 次运行落地前是「正在读取…」且枚举期间真收到 1 次 paint ✅；Linux 真机 → L16 |
| **T9** | `test_shot_prefetch.py` 8 passed：峰值 **≤2**、20 次导航发起 ≥15 而实际执行 <15、销毁后执行 <3 批且 0 异常、2 次导航只 **1** 次刷新 | 峰值 **6**、`sip.delete` 后 **3 批全跑完**、2 次导航 **2** 次刷新 | 用例判据全中 ✅ → **销账** |

> **峰值 6 与 §5 那个 17 不矛盾，是同一缺陷的两种测量口径**：11-11 的探针
> （`tmp/t9_thread_probe.py`）替身每批睡 **2.0s**、导航间隔 0.01s，20 次导航堆到 **17**；
> 本轮用例的替身每批只睡 **0.05s** 且每次导航都等目录加载完，重叠窗口小得多，对照组峰值 **6**。
> 两者都是**替身**测的线程数，不是真 exiftool 子进程数 —— 真机上每个在飞任务对应一个子进程，
> 所以「17 个并发子进程」是推论（§5 原文即如此措辞），不是实测。
| **T8** | `test_reveal.py` 36 passed；`grep -rn "explorer" --include=*.py core widgets` 只剩助手一处真实现 | 红 **8** 条（28 passed） | 合一 ✅、上限与「前 5 个」文案不变 ✅、两处旧钉桩用例保持绿 ✅；`--select` 真高亮 → L16 |

**T6 的忙碌提示这一半：现有机制已够，不新加控件**（§2.4.1 第 1 项就此关闭）。
抓帧口径：落地前读 `status_label.text()`、给 `status_label` 装 paint 事件计数器、落地后再读一次。

### 9.3 与方案的偏差（照实记，不掩盖）

1. **T8 的 Windows 形式：方案说「先真机测再定 argv 还是字符串」，本轮直接选了 argv 列表。**
   理由：不经 shell 的安全性可以论证（路径里的空格、引号、`&` 天然安全），而「哪种形式真能选中」
   两种都还没验。**若真机证明 argv 形式选不中、字符串形式能选中，改 `core/reveal.py` 一处即可** ——
   这正是合一的收益（旧代码要改两处）。这一项仍标**待实测**，不当既定事实写。
2. **T8 的 Linux 回落从 `QDesktopServices.openUrl` 改成 `xdg-open` 经 `Popen`。**
   窗格侧原来走 QDesktopServices，搜索侧走 xdg-open；统一成后者才能被同一批用例观测
   （`tests/test_search_results.py:320` 钉的就是 `subprocess.Popen`）。行为等价（都只打开所在目录），
   但现在**明说没选中**。
3. **T11② 选的是「模块级弱引用集合」而不是「全局有界池」**（§6.2 两种形状里的前者）：
   保留每实例一个池，不动 4 处调用与 `closeEvent`，改动面更小。
4. **T7 明确不做两件事**：`Ctrl+Shift+End` 保持 Qt 默认（实测光标到末行、选区不扩展），
   PgDn/PgUp 的「视口只装得下一行网格时移动 0 行」属 Qt 页大小算术，不另造绑定。
   两者都写进用例钉住现状，免得以后被「顺手修好」。
5. **T6 只做第一步**。第二步（Linux 真机复测）与第三步（排序搬后台，3–5 天）**没动**：
   本机已达标，外推约 660ms 仍超判据，但**不凭外推动工**（§2.4.1）。
6. **T9 多修了一处方案没写的**：批间取消命中时**不能往缓存写 None**，
   否则被取消的路径永久变成「没有拍摄日期」（用例「被取消路径不中毒」钉住，重试要跑满 4 批）。

### 9.4 取证过程里踩到的坑（已进 gotchas）

| 坑 | 条号 |
|---|---|
| 比较器里回模型取 `DisplayRole` = 一万次模型往返（铁律第 3 条据此补「也禁止回模型取 data()」） | #60 |
| Qt 的 Ctrl+移动只动光标；`Ctrl+Shift+End` 的默认行为与直觉不同，写断言前必须先量 | #61 |
| PyQt6 把 `QAbstractListModel.columnCount()` 标成私有方法 → 整行选中用 `SelectionFlag.Rows` | #62 |
| 外观 setter 只设差异项 → flow 残留成横带；另：不可达的调用序列该改用例不是改产品 | #63 |
| `sip.delete` 后 Python 包装还活着（判活要 `sip.isdeleted`）；故意销毁的控件别注册进 `qtbot` | #64 |
| 「退出排空」用例的假绿：观测量必须取**在飞**任务；`drain_background_pool` 先 `clear()` 会丢排队任务 | #65 |

铁律新增第 10 条（新增池必须进排空名单 + 判活用 `sip.isdeleted`），见 `AGENTS.md`。

### 9.5 还剩什么

- **L16**（`docs/linux-gap.md` §5.3 有逐项自查命令）：T6 改前改后 + SMB A/B、T7 四种视图手测
  与产物版单按 End 的复核、T8 六项定位参数、T10 看一眼网格、T11 退出有无 0xC0000409。
- **T6 第三步**：等 L16 的数字，超 400ms 才做。
- 待办状态：T9 ✅；T6 / T7 / T8 / T10 / T11 🟡（代码与 offscreen 闭环，真机那一半挂 L16）。
- 本文件 §1–§8 的原文**一字未删**，只在标题与状态行标了「已落地」，便于对照改前改后的判断。