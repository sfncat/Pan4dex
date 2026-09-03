# Pan4dex 万格

**跨平台四窗格文件管理器** | Linux · Windows

> A cross-platform quad-pane file manager inspired by Q-Dir



![Python](https://img.shields.io/badge/Python-3.10%2B-blue)



![PyQt6](https://img.shields.io/badge/PyQt6-6.6%2B-green)



![License](https://img.shields.io/badge/License-MIT-yellow)



![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-lightgrey)



***

## 简介

Pan4dex 是一个跨平台四窗格文件管理器，功能对标 Windows 下的 Q-Dir。

**核心特性**：



* 🔲 2×2 四窗格布局（可切换为双窗格）

* 📁 跨窗格拖拽复制 / 移动文件

* 🔍 快速预览面板（文本 / 图片 / 文件信息）

* 📑 多标签页

* 🎨 深色 / 浅色主题 + 自定义主题

* ⚡ 可配置外部终端和文件关联

* 📦 单文件可执行，零依赖运行



***

## 截图



***

## 安装

### Linux



```
\# 直接下载可执行文件

wget https://github.com/sfncat/Pan4dex/releases/latest/download/pan4dex-linux -O pan4dex

chmod +x pan4dex

./pan4dex
```

### Windows

从 [Releases](https://github.com/sfncat/Pan4dex/releases) 下载 `pan4dex-windows.exe` 即可运行。



***

## 开发

### 环境要求



* Python 3.10+

* PyQt6

### 安装依赖



```
python3 -m venv venv

source venv/bin/activate  # Linux/Mac

\# 或 venv\Scripts\activate  # Windows

pip install -r requirements.txt

pip install -r requirements-dev.txt
```

### 运行



```
python main.py
```

### 测试



```
pytest tests/ -v --qt-api=pyqt6
```

### 打包



```
\# Linux

pyinstaller packaging/pan4dex.spec

\# Windows

pyinstaller packaging/pan4dex.spec --icon=resources/icons/pan4dex.ico
```



***

## 快捷键



| 快捷键            | 功能          |
| -------------- | ----------- |
| `Ctrl+T`       | 新建标签页       |
| `Ctrl+W`       | 关闭标签页       |
| `Ctrl+Tab`     | 切换标签页       |
| `Ctrl+L`       | 聚焦路径栏       |
| `Ctrl+D`       | 切换深色 / 浅色主题 |
| `Ctrl+4`       | 四窗格模式       |
| `Ctrl+2`       | 双窗格模式       |
| `F3`           | 切换预览面板      |
| `F5`           | 刷新          |
| `F2`           | 重命名         |
| `Delete`       | 安全删除        |
| `Shift+Delete` | 永久删除        |



***

## 技术栈



* [Python 3.10+](https://www.python.org/)

* [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)

* [PyInstaller](https://pyinstaller.org/)

* [send2trash](https://github.com/Sharachchandra/send2trash)

* [Pillow](https://python-pillow.org/)



***

## 路线图



* [ ] M1: 核心框架（四窗格布局 + 基础导航）

* [ ] M2: 文件操作（复制 / 移动 / 删除 + 拖拽）

* [ ] M3: 标签页 + 快速预览

* [ ] M4: 主题系统 + 收藏夹 + 筛选

* [ ] M5: 打磨 + 打包发布



***

## 贡献

欢迎提交 Issue 和 PR。



***

## 许可证

[MIT](LICENSE) © 2026 sfncat



***

## 致谢



* [Q-Dir](https://q-dir.com/) — 灵感来源