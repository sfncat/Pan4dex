# AGENT.md — Pan4dex 万格 项目指南

> AI 助手和开发者阅读此文件后应能快速理解项目结构、开发流程和约定。

---

## 项目简介

Pan4dex 万格 是一个跨平台四窗格文件管理器，功能对标 Windows 下的 Q-Dir。支持 Linux（Ubuntu/Kali）和 Windows，使用 Python + PyQt6 开发，通过 PyInstaller 打包为单文件可执行。

**核心功能**：
- 2×2 网格四窗格布局（可切换为双窗格）
- 跨窗格拖拽复制/移动文件
- 标签页支持（新建/关闭/重命名/独立四窗格）
- 快速预览面板（文本/图片/文件信息）
- 文件类型 → 打开应用映射
- 可配置外部终端（图形化设置界面）
- 收藏夹侧边栏（右键目录直接添加）
- 目录树侧边栏（双击导航到当前活动窗格）
- 深色/浅色主题 + 自定义主题接口
- 批量重命名、校验和、文件比较、目录同步、压缩包处理、文件分割/合并、高级搜索

---

## 技术栈

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.10+ | Ubuntu 22.04+ 自带 |
| PyQt6 | 最新稳定版 | GUI 框架 |
| pytest | 最新 | 测试框架 |
| pytest-qt | 最新 | PyQt 组件测试 |
| pytest-cov | 最新 | 覆盖率 |
| send2trash | 最新 | 安全删除 |
| Pillow | 最新 | 图片预览 |
| PyInstaller | 最新 | 打包 |

---

## 项目目录结构

```
pan4dex/
├── main.py                   # 程序入口（版本号、构建时间）
├── core/                     # 核心业务逻辑
│   ├── __init__.py
│   ├── main_window.py        # 主窗口（标签页 + 布局管理 + 设置对话框入口）
│   ├── pane.py               # 单窗格（路径栏 + 文件列表 + 右键菜单 + 终端启动）
│   └── file_operations.py    # 复制/移动/删除/重命名
├── widgets/                  # UI 组件
│   ├── __init__.py
│   ├── path_bar.py           # 路径栏组件
│   ├── preview_panel.py      # 快速预览面板
│   ├── bookmark_sidebar.py   # 收藏夹侧边栏
│   ├── tree_sidebar.py       # 目录树侧边栏
│   ├── settings_dialog.py    # 设置对话框
│   ├── batch_rename.py       # 批量重命名工具
│   ├── checksum_tool.py      # 文件校验和工具
│   ├── file_compare.py       # 文件比较工具
│   ├── dir_sync.py           # 目录同步工具
│   ├── archive_tool.py       # 压缩包处理工具
│   ├── file_split.py         # 文件分割/合并工具
│   └── advanced_search.py    # 高级搜索工具
├── config/                   # 配置管理
│   ├── __init__.py
│   ├── file_associations.py  # 文件类型-应用映射
│   └── theme_manager.py      # 主题管理器
├── docs/                     # 文档目录
│   ├── design.md             # 设计文档
│   ├── architecture.md       # 架构设计
│   ├── development-guide.md  # 开发指南
│   ├── testing.md            # 测试策略
│   ├── implementation.md     # 实现设计
│   ├── feature-checklist.md  # 功能清单与规划
│   └── changelog.md          # 更新日志
├── tests/                    # 测试目录
│   ├── conftest.py           # pytest 配置和 fixtures
│   ├── test_m1_core.py       # M1 核心框架测试
│   ├── test_m3_preview.py    # M3 快速预览测试
│   ├── test_m4_theme.py      # M4 主题系统测试
│   ├── test_m5_tools.py      # M5 工具功能测试
│   └── test_m6_tools.py      # M6 工具功能测试
├── scripts/                  # 辅助脚本
│   ├── build.sh              # Linux 构建脚本（gti 远程打包）
│   ├── build_windows.py      # Windows 构建脚本（win54 远程打包）
│   ├── zip_it.py             # 打包 zip（自动找最新 exe）
│   └── extract_zip.py        # 解压部署到目标机器
├── packaging/                # 打包配置
│   └── pan4dex.spec          # PyInstaller spec 文件
├── resources/                # 资源文件（图标等）
├── requirements.txt          # 运行时依赖
├── AGENT.md                  # 本文件
└── pyproject.toml            # 项目配置
```

---

## 开发约定

### 代码风格
- 遵循 PEP 8
- 类型注解尽可能完整
- 函数和类的 docstring 使用 Google 风格
- 行长度不超过 100 字符

### 命名约定
- 模块：小写 + 下划线（`file_operations.py`）
- 类：大驼峰（`FileOperations`）
- 函数/方法：小写 + 下划线（`copy_files`）
- 常量：全大写下划线（`MAX_RETRIES`）
- 私有方法前缀：单下划线（`_internal_method`）

### Git 约定
- 功能分支：`feature/<功能名>`
- 修复分支：`fix/<问题描述>`
- 提交信息：`[模块] 动词 + 描述`，例如 `[file-ops] 修复大文件复制进度显示异常`

### 测试约定
- 每个模块有对应的测试文件
- 测试命名：`test_<模块>_<场景>`
- 单元测试不依赖 GUI（mock Qt 组件）
- 集成测试使用 `pytest-qt` 的 `qtbot`
- 目标覆盖率：核心模块 ≥ 85%，UI 模块 ≥ 60%

---

## 构建与部署

### 构建脚本
```bash
# Linux 版本（在 gti 192.168.5.58 上打包）
./scripts/build.sh v{版本号}

# Windows 版本（在 win54 192.168.5.54 上打包）
scp {同步文件} win54:C:/workspace/pan4dex/
ssh win54 'cmd /c "cd C:\workspace\pan4dex && python scripts/build_windows.py v{版本号}"'
ssh win54 'cmd /c "cd C:\workspace\pan4dex && python scripts/zip_it.py"'
```

### 机器配置
| 机器 | IP | 用户 | 用途 | 路径 |
|---|---|---|---|---|
| win54 | 192.168.5.54 | kali | Windows 构建机 | C:\workspace\pan4dex\ |
| 55 | 192.168.5.55 | sshuser | Windows 部署目标 | D:\workspace\2026\pan4dex\dist\ |
| gti | 192.168.5.58 | kali | Linux 部署目标 | ~/tools/pan4dex/ |

### win54 唤醒
```bash
wakeonlan -i 192.168.5.50 -p 9 52:54:10:73:70:cd
# 等待 SSH 就绪（可能需要 2-3 分钟）
```

### 文件同步清单
每次必须同步的文件：
- `main.py`（版本号）
- `widgets/path_bar.py`
- `widgets/thumbnail_view.py`
- `core/pane.py`
- `core/main_window.py`
- `config/theme_manager.py`
- `scripts/build_windows.py`
- `scripts/zip_it.py`
- `scripts/extract_zip.py`

### 构建要求
`build_windows.py` 必须包含：
- `--hidden-import=PyQt6.QtSvg`
- `--collect-all=PyQt6`
- `--add-data=...imageformats;imageformats`（图片格式插件）

### 55 上解压部署
```bash
ssh sshuser@192.168.5.55 'cmd /c "taskkill /F /IM pan4dex* /T 2>nul & timeout /t 2 /nobreak >nul & cd /d D:\workspace\2026\pan4dex\dist & python extract_zip.py"'
```

### 常见错误
| 错误 | 原因 | 解决 |
|------|------|------|
| 55 上版本号不对 | zip_it.py 硬编码了旧版本 | 修复 zip_it.py 为自动查找最新 |
| 图片无法显示 | 缺少 Qt 图片格式插件 | 确保 build_windows.py 包含 `--add-data=imageformats` |
| 应用崩溃 | QTreeView setIconSize(128) | 使用独立 ThumbnailView |
| win54 SSH 超时 | 机器睡眠 | 先 WOL 唤醒，等待 2-3 分钟 |
| 55 上文件被占用 | 应用正在运行 | 先 taskkill 再替换 |

### 版本号规则
- 格式：`0.9.5XX`（三位小版本号）
- 用户手动控制，不要自动递增
- 构建时间由 `build_windows.py` 自动注入

---

## 架构要点

### 数据流

```
用户操作 → Pane 捕获 → FileOperations 执行 → 回调更新 UI
                                ↓
                       进度信号 → 窗格底部进度条
```

### 关键设计决策
- 每个窗格持有独立的 `QFileSystemModel` 实例
- 每个标签页持有独立的 `QuadPaneWidget`（包含 4 个 Pane）
- 跨窗格拖拽使用自定义 MIME 类型 `application/x-pan4dex-drag`
- 文件操作在 `QThread` 中执行，避免阻塞 UI
- 主题系统支持运行时切换，无需重启
- 目录树导航通过 `_active_pane` 跟踪当前活动窗格
- 窗格焦点通过 `eventFilter` 监听 `FocusIn` 和 `MouseButtonPress` 事件

### 活动窗格机制
- `Pane` 安装事件过滤器到 `tree_view`
- 当 `tree_view` 获得焦点或鼠标点击时，发出 `activated` 信号
- `MainWindow` 的 `_active_pane` 总是指向最后交互的窗格
- 目录树/收藏夹导航作用于 `_active_pane`

### 终端配置
- 优先级：用户配置 → xdg-mime 系统默认 → 自动检测已安装终端
- 配置文件：`~/.config/pan4dex/settings.json`
- 设置界面：帮助 → 设置
- Windows 支持：wt.exe、pwsh.exe、powershell.exe、cmd.exe
- Linux 支持：gnome-terminal、konsole、xfce4-terminal、alacritty、kitty 等

---

## 配置系统

### 配置文件位置
- Linux: `~/.config/pan4dex/`
- Windows: `%APPDATA%\pan4dex\`

### 配置文件
| 文件 | 用途 |
|---|---|
| `settings.json` | 终端应用等全局设置 |
| `bookmarks.json` | 收藏夹列表 |
| `associations.json` | 文件类型-应用映射 |

### settings.json 示例
```json
{
    "terminal": "gnome-terminal"
}
```

---

## 常见问题

**Q: PyQt6 在 headless 测试环境中无法初始化？**
A: 使用 `xvfb-run` 或设置 `QT_QPA_PLATFORM=offscreen`

**Q: 如何处理不同发行版的终端差异？**
A: 通过设置界面配置，或自动检测：用户配置 → xdg-mime → 已安装终端扫描

**Q: 打包后图标/资源找不到？**
A: PyInstaller spec 中正确配置 `datas`，运行时使用 `sys._MEIPASS` 定位资源

**Q: 目录树双击导航到错误的窗格？**
A: 确保先点击目标窗格使其获得焦点，_directory tree 导航总是作用于 `_active_pane`

**Q: 标签页右键菜单坐标偏移？**
A: `customContextMenuRequested` 的坐标是相对 `QTabWidget` 的，需要用 `tabBar.mapFrom()` 转换

---

**文档版本**: v1.2  
**最后更新**: 2026-08-31
