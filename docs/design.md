# Pan4dex 万格 Linux 版 — 设计文档

## 1. 项目概述

开发一个跨平台四窗格文件管理器，功能对标 Windows 下的 Q-Dir。支持 Linux（Ubuntu/Kali）和 Windows，通过 PyInstaller 打包为独立可执行文件，运行时零依赖。

---

## 2. 技术选型

| 组件 | 选择 | 理由 |
|---|---|---|
| GUI 框架 | PyQt6 | 跨平台（Linux/Windows/macOS），QFileSystemModel/QTreeView 开箱即用 |
| Python 版本 | 3.10+ | 跨平台支持好 |
| 打包工具 | PyInstaller | 支持 Linux 和 Windows 打包 |
| 额外依赖 | `send2trash`、`Pillow` | 安全删除、图片预览（均跨平台） |

---

## 3. 功能需求

### 3.1 核心功能

#### 3.1.1 四窗格布局

- 使用 `QSplitter` 实现 2×2 网格布局，每个窗格独立持有路径状态
- 每个窗格包含：
  - 路径栏（`QComboBox`，支持下拉历史 + 手动输入 + 回车跳转）
  - 文件列表（`QTreeView` + `QFileSystemModel`）
  - 状态栏（显示当前路径、文件数、选中项信息）
- 窗格之间可拖拽边框调整大小

#### 3.1.2 文件导航

- 双击进入文件夹
- 返回上级目录按钮
- 路径栏支持自动补全（输入时弹出匹配路径列表）
- 支持书签/收藏夹快速跳转

#### 3.1.3 文件操作

| 操作 | 实现方式 |
|---|---|
| 复制 | 跨窗格拖拽，或右键菜单 → 复制到目标窗格 |
| 移动 | 跨窗格拖拽（Shift+拖拽） |
| 删除 | 右键菜单 → 删除，调用 `send2trash` 安全删除 |
| 重命名 | 右键菜单 → 重命名，`QTreeView` 内联编辑 |
| 新建文件夹 | 右键菜单 → 新建文件夹 |
| 新建文件 | 右键菜单 → 新建文件 |

#### 3.1.4 拖拽机制

- **窗格内拖拽**：移动文件/文件夹
- **跨窗格拖拽**：复制文件/文件夹到目标窗格
- **拖拽时按住 Shift**：强制移动而非复制
- **拖拽时按住 Ctrl**：强制复制
- 拖拽时显示进度对话框（大文件/多文件）

### 3.2 高级功能

#### 3.2.1 标签页

- 主窗口顶部 `QTabWidget`
- 每个标签页保持独立的 4 窗格布局 + 各自路径状态
- 支持新建标签页、关闭标签页、标签页拖拽排序
- 快捷键：`Ctrl+T` 新建、`Ctrl+W` 关闭、`Ctrl+Tab` 切换

#### 3.2.2 快速预览

- 右侧 `QDockWidget` 预览面板
- **文本预览**：直接显示文件内容，支持语法高亮（`QSyntaxHighlighter`）
- **文件信息显示**：大小、修改时间、权限、MIME 类型
- **图片预览**：`QPixmap` 显示缩略图

#### 3.2.3 文件打开配置

- 设置界面中配置「文件类型 → 打开应用」映射
- 示例：
  ```
  .txt → xdg-open（系统默认）
  .py  → code（VS Code）
  .pdf → evince
  ```
- 未配置的类型使用 `xdg-open`（系统默认应用）
- 配置持久化（`QSettings` 或 JSON 配置文件）

#### 3.2.4 终端集成

- 右键菜单 → 在此处打开终端
- 可配置终端应用（默认检测：`gnome-terminal` → `konsole` → `xfce4-terminal` → `xterm`）
- 或使用系统默认终端（`x-terminal-emulator`）

#### 3.2.5 目录热表/收藏夹

- 侧边栏 `QListWidget` 显示收藏路径
- 支持拖拽添加、右键移除
- 分组收藏（常用目录、项目目录等）

#### 3.2.6 筛选过滤

- 每个窗格可独立设置筛选规则
- 支持按扩展名、日期、大小过滤
- 使用 `QSortFilterProxyModel` 实现

---

## 4. 布局模式说明

### 4.1 四窗格模式（默认）

```
┌─────────────┬─────────────┐
│   Pane 1    │   Pane 2    │
│  /home/user │  /tmp       │
│             │             │
├─────────────┼─────────────┤
│   Pane 3    │   Pane 4    │
│  /var/log   │  /opt       │
│             │             │
└─────────────┴─────────────┘
```

**适用场景**：多目录同时操作，比如从 3 个不同源目录复制文件到同一个目标目录。

### 4.2 双窗格模式

```
┌─────────────────────────────┐
│        Source Pane          │
│        /home/user           │
│                             │
├─────────────────────────────┤
│       Destination Pane      │
│       /backup               │
│                             │
└─────────────────────────────┘
```

**适用场景**：类似 Total Commander 的经典双面板操作，专注于源 → 目标的复制/同步。

### 4.3 模式切换

- 菜单栏「视图」→「四窗格模式」/「双窗格模式」
- 快捷键：`Ctrl+4` / `Ctrl+2`
- 切换时保留当前路径状态

---

## 5. 主题系统

### 5.1 内置主题

| 主题 | 说明 |
|---|---|
| 系统主题 | 跟随桌面环境（GTK/Qt 主题） |
| 深色主题 | 自定义深色配色方案 |
| 浅色主题 | 自定义浅色配色方案 |

### 5.2 主题架构

```
ThemeManager（单例）
├── current_theme: str          # 当前主题名称
├── themes: dict[str, Theme]    # 主题注册表
├── apply_theme(name: str)      # 应用主题
├── register_theme(name, Theme) # 注册自定义主题
└── load_custom_theme(path)     # 从文件加载自定义主题
```

- `Theme` 类包含：窗口背景、文字颜色、选中高亮、边框颜色、字体等
- 自定义主题通过 JSON 文件定义，放置于 `~/.config/pan4dex/themes/`
- 预留接口，后续可扩展 CSS 样式表支持

---

## 6. 项目结构

```
pan4dex/
├── main.py                  # 程序入口
├── core/
│   ├── __init__.py
│   ├── main_window.py       # 主窗口（标签页 + 布局管理）
│   ├── pane.py              # 单个窗格（路径栏 + 文件列表）
│   ├── file_model.py        # 文件系统模型封装
│   ├── file_operations.py   # 复制/移动/删除/重命名
│   ├── drag_drop.py         # 拖拽逻辑
│   └── terminal.py          # 终端检测与启动
├── widgets/
│   ├── __init__.py
│   ├── path_bar.py          # 路径栏组件
│   ├── preview_panel.py     # 快速预览面板
│   ├── bookmark_sidebar.py  # 收藏夹侧边栏
│   └── filter_bar.py        # 筛选栏
├── config/
│   ├── __init__.py
│   ├── settings.py          # 设置管理（QSettings 封装）
│   ├── file_associations.py # 文件类型-应用映射
│   └── theme_manager.py     # 主题管理器
├── resources/
│   ├── icons/               # 图标资源
│   └── themes/              # 内置主题 JSON
├── docs/                    # 文档
│   ├── design.md            # 本文档
│   ├── architecture.md      # 架构设计
│   ├── testing.md           # 测试策略
│   └── development-guide.md # 开发指南
├── tests/                   # 测试
│   ├── conftest.py
│   ├── unit/                # 单元测试
│   ├── integration/         # 集成测试
│   └── fixtures/            # 测试夹具
├── scripts/                 # 辅助脚本
├── packaging/               # 打包配置
├── requirements.txt         # 运行时依赖
├── requirements-dev.txt     # 开发依赖
├── pyproject.toml           # 项目配置
└── AGENT.md                 # AI/开发者指南
```

---

## 7. 数据流设计

### 7.1 文件操作流程

```
用户操作（拖拽/右键菜单）
    ↓
Pane 捕获事件，获取源文件路径列表
    ↓
FileOperations 执行操作
    ├── 复制：shutil.copy2() + 进度回调
    ├── 移动：shutil.move() + 进度回调
    ├── 删除：send2trash() 或 os.remove()
    └── 重命名：os.rename()
    ↓
操作完成后刷新相关窗格的 QFileSystemModel
```

### 7.2 拖拽数据格式

- 使用 `QMimeData` 携带源窗格 ID + 文件路径列表
- 拖拽时记录操作类型（复制/移动）
- 目标窗格根据拖拽来源决定是否接受

---

## 8. 配置持久化

| 配置项 | 存储位置 | 格式 |
|---|---|---|
| 窗口大小/位置 | `QSettings` | INI |
| 收藏夹列表 | `~/.config/pan4dex/bookmarks.json` | JSON |
| 文件打开关联 | `~/.config/pan4dex/associations.json` | JSON |
| 主题设置 | `QSettings` | INI |
| 终端应用 | `QSettings` | INI |
| 自定义主题 | `~/.config/pan4dex/themes/*.json` | JSON |

---

## 9. 打包与分发

### 9.1 PyInstaller 打包

**Linux：**
```bash
pyinstaller pan4dex.spec
```

**Windows：**
```bash
pyinstaller pan4dex.spec --icon=resources/icons/pan4dex.ico
```

spec 文件关键配置：
- `--onefile`：单文件可执行
- `--windowed`：无控制台窗口
- 包含 Qt 插件（`platforms`、`styles`、`iconengines`）
- 包含资源文件（图标、主题）

### 9.2 分发方式

| 平台 | 格式 | 说明 |
|---|---|---|
| Linux | 可执行文件 | 零依赖，下载即用 |
| Linux | `.deb` 包（可选） | 方便 Ubuntu/Kali 安装 |
| Linux | `.AppImage`（可选） | 更 Linux 风格 |
| Windows | `.exe` 可执行文件 | 零依赖，下载即用 |
| Windows | 安装包（`.msi`/`.exe`，可选） | 标准 Windows 安装体验 |

### 9.3 跨平台注意事项

| 方面 | Linux | Windows |
|---|---|---|
| 配置目录 | `~/.config/pan4dex/` | `%APPDATA%\pan4dex\` |
| 回收站 | `~/.local/share/Trash/` | `shell:RecycleBinFolder`（通过 `send2trash` 抽象） |
| 终端 | `gnome-terminal`/`konsole`/`xterm` | `cmd`/`PowerShell`/`Windows Terminal` |
| 文件关联 | `xdg-open` | `os.startfile()` 或 ShellExecute |
| 路径分隔符 | `/` | `\`（使用 `pathlib.Path` 统一处理） |
| 权限 | `os.access()` + `chmod` | ACL + `attrib` |

---

## 10. 开发里程碑

| 阶段 | 内容 | 预计产出 |
|---|---|---|
| M1 | 核心框架：四窗格布局 + 基础导航 | 可浏览文件的四窗格窗口 |
| M2 | 文件操作：复制/移动/删除/重命名 + 拖拽 | 完整的文件操作能力 |
| M3 | 标签页 + 快速预览 + 文件打开配置 | 接近可用的版本 |
| M4 | 主题系统 + 收藏夹 + 筛选 + 终端集成 | 功能完整版（MVP） |
| M5 | 批量重命名 + 校验和 + 文件比较 | 工具增强版 |
| M6 | 目录同步 + 压缩包 + 分割合并 + 高级搜索 | 高级版 |
| M7 | 打磨 + 打包 + 测试 | 可发布的版本 |

---

## 11. 风险与注意事项

| 风险 | 应对方案 |
|---|---|
| Qt 主题在部分桌面环境显示异常 | 提供内置主题作为 fallback |
| 大文件复制时 UI 卡顿 | 使用 `QThread` 后台执行，主线程更新进度 |
| 不同发行版终端应用不同 | 自动检测 + 用户可配置 |
| PyInstaller 打包后体积大 | 正常现象（~50-80MB），可接受 |
| 权限问题（系统目录操作） | 提示用户需要权限，不强行操作 |

---

## 12. 后续扩展（非当前范围）

- 文件同步（双向/镜像同步）
- 批量重命名
- 文件校验（MD5/SHA256）
- 插件系统
- 网络位置支持（SFTP/SMB）
- 压缩/解压集成

---

**文档版本**：v1.0  
**最后更新**：2026-08-26
