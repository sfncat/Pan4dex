# Pan4dex 万格 — 功能清单与规划

> 本文档跟踪所有功能的实现状态，每完成/更新一个功能都要更新此文档。

**图例**：🔴 未开始 | 🟡 进行中 | 🟢 已完成 | ⚪ 暂缓

---

## 1. 核心框架

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 1.1 | 四窗格布局 | P0 | 🟢 | 启动后可见 4 个独立窗格，可拖拽调整大小 | QSplitter 2×2 网格 | main_window.py QuadPaneWidget |
| 1.2 | 单窗格文件浏览 | P0 | 🟢 | 每个窗格独立显示文件列表，双击进入目录 | QTreeView + QFileSystemModel | pane.py |
| 1.3 | 路径栏 | P0 | 🟢 | 点击路径栏可输入路径，回车跳转，支持下拉历史 | QComboBox + 自动补全 | path_bar.py |
| 1.4 | 窗格状态栏 | P0 | 🟢 | 底部显示当前路径、文件数、选中项信息 | QLabel 状态栏 | pane.py |
| 1.5 | 窗格底部进度条 | P0 | 🟢 | 文件操作时在窗格底部显示进度条 | QProgressBar 内嵌窗格底部 | pane.py |
| 1.6 | 拖拽目标高亮 | P0 | 🟢 | 跨窗格拖拽时目标窗格边框高亮（蓝色） | QSS 动态样式 | pane.py dragEnterEvent |
| 1.7 | 主窗口框架 | P0 | 🟢 | 菜单栏、工具栏、状态栏、QDockWidget 区域 | QMainWindow | main_window.py |

## 2. 文件操作

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 2.1 | 复制文件 | P0 | 🟢 | 跨窗格拖拽复制，进度条显示，完成后目标窗格刷新 | shutil.copy2 + QThread | file_operations.py copy() |
| 2.2 | 移动文件 | P0 | 🟢 | 窗格内拖拽移动，或 Shift+跨窗格拖拽 | shutil.move + QThread | file_operations.py move() |
| 2.3 | 安全删除 | P0 | 🟢 | 右键删除 → 文件进入回收站，可恢复 | send2trash | file_operations.py delete() |
| 2.4 | 永久删除 | P1 | 🔴 | Shift+Delete 直接删除，不可恢复 | os.remove / os.rmdir | - |
| 2.5 | 重命名 | P0 | 🟢 | 右键重命名，QTreeView 内联编辑 | os.rename | file_operations.py rename() |
| 2.6 | 新建文件夹 | P1 | 🟢 | 右键菜单 → 新建文件夹，自动进入重命名 | os.makedirs | file_operations.py create_folder() |
| 2.7 | 新建文件 | P1 | 🟢 | 右键菜单 → 新建空文件 | open(path, 'w') | file_operations.py create_file() |
| 2.8 | 复制/移动取消 | P1 | 🔴 | 进度条显示取消按钮，点击后中止操作 | QThread 安全终止 | - |
| 2.9 | 跨窗格拖拽复制 | P0 | 🟢 | 从 pane A 拖拽文件到 pane B，B 中高亮边框，松手复制 | 自定义 MIME 类型 | pane.py mouseMoveEvent/dropEvent |
| 2.10 | 跨窗格拖拽移动 | P0 | 🟢 | Shift+拖拽从 A 到 B，源文件消失，目标出现 | 自定义 MIME 类型 | pane.py mouseMoveEvent/dropEvent |

## 3. 导航

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 3.1 | 返回上级目录 | P0 | 🔴 | 点击按钮或 Alt+Up 返回上级 | QFileSystemModel.setRootPath | - |
| 3.2 | 路径自动补全 | P1 | 🔴 | 输入路径时弹出匹配列表 | QCompleter + QDir | - |
| 3.3 | 路径历史 | P1 | 🔴 | 前进/后退按钮，记录导航历史 | 历史栈 | - |
| 3.4 | 快速跳转 | P1 | 🔴 | Ctrl+L 聚焦路径栏 | 快捷键 | - |

## 4. 标签页

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
|| 4.1 | 多标签页 | P1 | 🟢 | Ctrl+T 新建标签页，每个标签页独立四窗格 | QTabWidget | main_window.py new_tab() |
|| 4.2 | 关闭标签页 | P1 | 🟢 | Ctrl+W 关闭当前标签页，Tab 栏关闭按钮 | tabCloseRequested | main_window.py close_tab() |
|| 4.3 | 标签页切换 | P1 | 🟢 | Ctrl+Tab 切换到下一个标签页，双击空白新建 | tabBarDoubleClicked | main_window.py |
|| 4.4 | 标签页状态保持 | P1 | 🟢 | 切换标签页时保留各窗格路径和选中状态 | QuadPaneWidget 独立持有 4 个 Pane | main_window.py |
|| 4.5 | 标签页重命名 | P1 | 🟢 | 右键菜单或双击标签页，弹出输入对话框 | QInputDialog | main_window.py rename_tab() |

## 5. 快速预览

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 5.1 | 文本预览 | P1 | 🟢 | 选中文本文件，右侧面板显示内容 | QPlainTextEdit + 语法高亮 | preview_panel.py |
| 5.2 | 文件信息显示 | P1 | 🟢 | 显示大小、修改时间、权限、MIME 类型 | QLabel 信息面板 | preview_panel.py |
| 5.3 | 图片缩略图 | P2 | 🟢 | 选中图片文件，右侧显示缩略图 | QPixmap + QLabel | preview_panel.py |
| 5.4 | 预览面板开关 | P1 | 🟢 | F3 或菜单切换预览面板显示 | QDockWidget toggle | main_window.py toggle_preview() |

## 6. 文件打开配置

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 6.1 | 文件类型-应用映射 | P1 | 🟢 | 设置界面配置扩展名→应用映射 | JSON 配置 | file_associations.py |
| 6.2 | 默认打开行为 | P1 | 🟢 | 双击文件按配置打开，未配置用 xdg-open | subprocess + xdg-open | file_associations.py open_file() |
| 6.3 | 右键打开方式 | P2 | 🔴 | 右键菜单列出可用应用 | QMenu 动态生成 | - |
| 6.4 | 配置持久化 | P1 | 🟢 | 配置保存到 ~/.config/pan4dex/ | QSettings + JSON | file_associations.py |

## 7. 终端集成

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
|| 7.1 | 终端自动检测 | P1 | 🟢 | 自动检测可用终端（Windows: wt.exe/pwsh.exe, Linux: xdg-mime/配置） | which + 配置回退 | pane.py open_terminal_here() |
|| 7.2 | 在此处打开终端 | P1 | 🟢 | 右键菜单 → 在当前目录打开终端 | subprocess 启动终端 | pane.py open_terminal_here() |
|| 7.3 | 终端应用配置 | P2 | 🟢 | 用户可通过 settings.json 指定自定义终端应用 | JSON 配置持久化 | pane.py 读取 settings.json |

## 8. 收藏夹

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 8.1 | 收藏夹侧边栏 | P2 | 🟢 | 侧边栏显示收藏路径列表 | QListWidget + QDockWidget | bookmark_sidebar.py |
| 8.2 | 添加收藏 | P2 | 🟢 | 拖拽目录到侧边栏或右键添加 | 拖拽 + 右键菜单 | bookmark_sidebar.py add_bookmark() |
| 8.3 | 移除收藏 | P2 | 🟢 | 右键移除收藏项 | 右键菜单 | bookmark_sidebar.py remove_bookmark() |
| 8.4 | 收藏分组 | P3 | 🔴 | 支持分组管理收藏 | 树形结构 | - |

## 9. 筛选过滤

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 9.1 | 按扩展名筛选 | P2 | 🔴 | 输入 *.txt 只显示 txt 文件 | QSortFilterProxyModel | - |
| 9.2 | 按日期筛选 | P3 | 🔴 | 只显示指定日期范围的文件 | QSortFilterProxyModel | - |
| 9.3 | 按大小筛选 | P3 | 🔴 | 只显示指定大小范围的文件 | QSortFilterProxyModel | - |
| 9.4 | 清除筛选 | P2 | 🔴 | 一键清除筛选条件，显示全部 | 重置 proxy model | - |

## 10. 布局模式

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
|| 10.1 | 四窗格模式 | P0 | 🟢 | 默认 2×2 四窗格，每个标签页独立 | QSplitter 网格 + QuadPaneWidget | main_window.py switch_to_quad() |
|| 10.2 | 双窗格模式 | P1 | 🟢 | Ctrl+2 切换到上下双窗格 | 隐藏 pane2/pane4 | main_window.py switch_to_dual() |
|| 10.3 | 模式切换 | P1 | 🟢 | 菜单或快捷键切换，保留路径状态 | show()/hide() 窗格 | main_window.py |

## 11. 主题系统

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 11.1 | 系统主题 | P1 | 🟢 | 跟随桌面环境主题 | QApplication 默认样式 | theme_manager.py |
| 11.2 | 深色主题 | P1 | 🟢 | Ctrl+D 切换到深色主题 | QSS 样式表 | theme_manager.py |
| 11.3 | 浅色主题 | P2 | 🟢 | 切换到浅色主题 | QSS 样式表 | theme_manager.py |
| 11.4 | 自定义主题接口 | P2 | 🟢 | 预留接口，支持 JSON 主题文件 | ThemeManager 注册机制 | theme_manager.py |
| 11.5 | 主题热切换 | P1 | 🟢 | 切换主题无需重启 | QSS 动态加载 | theme_manager.py apply_theme() |

## 12. 快捷键

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 12.1 | Ctrl+T 新建标签页 | P1 | 🔴 | 按下后新建空白标签页 | QShortcut | - |
| 12.2 | Ctrl+W 关闭标签页 | P1 | 🔴 | 按下后关闭当前标签页 | QShortcut | - |
| 12.3 | Ctrl+Tab 切换标签页 | P1 | 🔴 | 按下后切换到下一个标签页 | QShortcut | - |
| 12.4 | Ctrl+L 聚焦路径栏 | P1 | 🔴 | 按下后光标定位到当前窗格路径栏 | QShortcut | - |
| 12.5 | Ctrl+D 切换主题 | P2 | 🔴 | 按下后在深色/浅色间切换 | QShortcut | - |
| 12.6 | Ctrl+4 四窗格模式 | P1 | 🔴 | 切换到四窗格模式 | QShortcut | - |
| 12.7 | Ctrl+2 双窗格模式 | P1 | 🔴 | 切换到双窗格模式 | QShortcut | - |
| 12.8 | F3 预览面板 | P2 | 🔴 | 切换预览面板显示 | QShortcut | - |
| 12.9 | F5 刷新 | P1 | 🔴 | 刷新当前窗格 | QShortcut | - |
| 12.10 | Delete 安全删除 | P0 | 🔴 | 删除选中项到回收站 | QShortcut | - |
| 12.11 | Shift+Delete 永久删除 | P1 | 🔴 | 直接删除选中项 | QShortcut | - |
| 12.12 | F2 重命名 | P0 | 🔴 | 进入重命名模式 | QShortcut | - |

## 13. 右键菜单

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
|| 13.1 | 打开 | P0 | 🟢 | 双击或右键打开文件 | 按配置应用打开 | pane.py open_selected() |
|| 13.2 | 复制 | P0 | 🟢 | 右键复制，然后到目标窗格粘贴 | 剪贴板机制 | pane.py copy_selected() |
|| 13.3 | 剪切 | P0 | 🟢 | 右键剪切 | 剪贴板机制 | pane.py cut_selected() |
|| 13.4 | 粘贴 | P0 | 🟢 | 右键粘贴到当前目录 | 剪贴板机制 | pane.py paste() |
|| 13.5 | 删除 | P0 | 🟢 | 右键删除到回收站 | send2trash | pane.py delete_selected() |
|| 13.6 | 重命名 | P0 | 🟢 | 右键重命名 | 内联编辑 | pane.py rename_selected() |
|| 13.7 | 新建文件夹 | P1 | 🟢 | 右键新建文件夹 | os.makedirs | pane.py create_folder() |
|| 13.8 | 新建文件 | P1 | 🟢 | 右键新建文件 | open(path, 'w') | pane.py create_file() |
|| 13.9 | 打开终端 | P1 | 🟢 | 右键在当前目录打开终端 | subprocess | pane.py open_terminal_here() |
|| 13.11 | 添加到收藏夹 | P2 | 🟢 | 选中目录后右键添加到收藏夹 | BookmarkSidebar.add_bookmark_with_path() | pane.py |

---

## 14. 批量重命名

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 14.1 | 批量重命名 | P1 | 🟢 | 选中多个文件，打开批量重命名对话框，支持正则、模板、序号 | QDialog + 正则引擎 | batch_rename.py BatchRenameDialog |
| 14.2 | 正则替换 | P1 | 🟢 | 支持正则表达式匹配和替换 | re 模块 | batch_rename.py preview_regex() |
| 14.3 | 模板重命名 | P1 | 🟢 | 支持 [N]序号 [Y]年 [M]月 [D]日 等模板 | 模板解析器 | batch_rename.py preview_template() |
| 14.4 | 大小写转换 | P2 | 🟢 | 支持全大写/全小写/首字母大写 | str 方法 | batch_rename.py preview_case() |
| 14.5 | 预览功能 | P1 | 🟢 | 重命名前预览新文件名 | 实时预览列表 | batch_rename.py update_preview() |

## 15. 文件校验和

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 15.1 | 创建校验和 | P1 | 🟢 | 计算文件的 MD5/SHA256 校验和 | hashlib 模块 | checksum_tool.py ChecksumDialog |
| 15.2 | 验证校验和 | P1 | 🟢 | 对比文件校验和与预期值 | hashlib 模块 | checksum_tool.py verify() |
| 15.3 | 校验和文件 | P2 | 🟢 | 生成/验证 .md5/.sha256 校验和文件 | 标准校验和文件格式 | checksum_tool.py select_verify_file() |

## 16. 文件比较

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 16.1 | 文本比较 | P1 | 🟢 | 对比两个文本文件，高亮差异 | difflib + QTextEdit | file_compare.py FileCompareDialog |
| 16.2 | 二进制比较 | P2 | 🔴 | 逐字节对比两个文件 | 字节级对比 | - |
| 16.3 | 比较结果导出 | P2 | 🔴 | 导出比较结果为 HTML/文本 | 报告生成 | - |

## 17. 目录同步

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 17.1 | 目录对比 | P2 | 🟢 | 对比两个目录的文件差异 | 文件列表对比 | dir_sync.py DirSyncDialog |
| 17.2 | 双向同步 | P2 | 🟢 | 双向同步两个目录 | 同步算法 | dir_sync.py execute_sync() |
| 17.3 | 镜像同步 | P2 | 🟢 | 使目标目录与源目录完全一致 | 同步算法 | dir_sync.py execute_sync() |
| 17.4 | 同步预览 | P2 | 🟢 | 同步前预览将要执行的操作 | 操作列表预览 | dir_sync.py compare() |

## 18. 压缩包处理

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 18.1 | 浏览压缩包 | P2 | 🟢 | 像浏览目录一样浏览 zip/tar/7z 内容 | zipfile/tarfile 模块 | archive_tool.py ArchiveDialog |
| 18.2 | 解压文件 | P2 | 🟢 | 解压到指定目录 | 解压引擎 | archive_tool.py extract_archive() |
| 18.3 | 创建压缩包 | P2 | 🟢 | 将选中文件压缩为 zip/tar.gz | 压缩引擎 | archive_tool.py create_archive() |
| 18.4 | 支持 7z/rar | P3 | 🔴 | 通过 7z 命令行支持更多格式 | 外部工具调用 | - |

## 19. 文件分割/合并

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 19.1 | 文件分割 | P2 | 🟢 | 将大文件分割为指定大小的块 | 分块写入 | file_split.py SplitWorker |
| 19.2 | 文件合并 | P2 | 🟢 | 将分割的块合并为原始文件 | 顺序合并 | file_split.py merge_files() |
| 19.3 | 分割方案 | P2 | 🟢 | 支持自定义块大小、按数量分割 | 配置对话框 | file_split.py FileSplitDialog |

## 20. 高级搜索

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 20.1 | 文件名搜索 | P2 | 🟢 | 按文件名模式搜索 | glob/正则 | advanced_search.py SearchWorker |
| 20.2 | 内容搜索 | P2 | 🟢 | 在文件内容中搜索字符串/正则 | 文件遍历 + 搜索 | advanced_search.py |
| 20.3 | 搜索结果操作 | P2 | 🟢 | 对搜索结果进行批量操作 | 结果列表 + 操作菜单 | advanced_search.py |
| 20.4 | 保存搜索 | P3 | 🔴 | 保存搜索条件供后续使用 | 搜索配置持久化 | - |

## 21. 用户操作菜单

| # | 功能 | 优先级 | 状态 | 验证方式 | 说明 | 实现情况 |
|---|---|---|---|---|---|---|
| 21.1 | 自定义操作 | P3 | 🔴 | 用户定义快捷操作（如打开编辑器、转换格式） | 操作配置 | - |
| 21.2 | 操作快捷键 | P3 | 🔴 | 为自定义操作绑定快捷键 | 快捷键配置 | - |

|| 22.1 | 目录树侧边栏 | P1 | 🟢 | 左侧显示目录树，双击导航到当前活动窗格 | QTreeView + QFileSystemModel | tree_sidebar.py TreeSidebar |
|| 22.2 | 活动窗格跟踪 | P1 | 🟢 | 焦点在哪个窗格，目录树导航就作用于哪个窗格 | _active_pane + eventFilter | pane.py eventFilter() |
|| 22.3 | 自动展开控制 | P1 | 🟢 | 可开关自动展开文件夹功能 | 按钮+状态跟踪 | tree_sidebar.py toggle_auto_expand() |
|| 22.4 | 展开/折叠按钮 | P1 | 🟢 | 一键展开或折叠所有节点 | QTreeView.expandAll/collapseAll | tree_sidebar.py |

---

## 优先级说明

| 优先级 | 说明 |
|---|---|
| P0 | 核心功能，MVP 必须 |
| P1 | 重要功能，第一个可用版本应包含 |
| P2 | 增强功能，后续版本迭代 |
| P3 | 锦上添花，有时间再做 |

---

## 更新记录

| 日期 | 更新内容 | 更新人 |
|---|---|---|
| 2026-08-26 | 初始版本，列出全部功能 | - |
| 2026-08-28 | 更新标签页、目录树、终端、四窗格等功能状态；新增标签页重命名、活动窗格跟踪 | - |

---

**文档版本**：v1.1  
**最后更新**：2026-08-28
