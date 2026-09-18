# Pan4dex 万格 — 快速开始

## 🚀 一键构建

### Linux 版本（推荐所有环境使用 Docker）
```bash
bash scripts/build-linux-docker.sh
```
产物：`releases/pan4dex-<版本>-linux`

### Windows 版本（本机构建）
```powershell
python scripts/build_windows.py
```
产物：`releases/pan4dex-<版本>/` + `.zip`

---

## 📚 完整文档

| 文档 | 说明 |
|------|------|
| [`docs/build-guide.md`](docs/build-guide.md) | **详细构建指南**（含 230 Docker 构建） |
| [`docs/development-guide.md`](docs/development-guide.md) | 开发指南（测试、打包、代码规范） |
| [`docs/feature-checklist.md`](docs/feature-checklist.md) | 功能清单与实现状态 |
| [`README.md`](README.md) | 项目简介和安装说明 |

---

## 🔧 常用命令

```bash
# 运行测试
pytest tests/ -v --qt-api=pyqt6

# 代码检查
ruff check core/ widgets/ config/
mypy core/ widgets/ config/

# 清理构建缓存
rm -rf build/ dist/ build_onefile/ dist_onefile/
```

---

## 🎯 待办事项

| 任务 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| L2 | 万条目真共享 | 🔴 | 需要用户 NAS 环境 |
| L4 | 真鼠标拖拽 | 🔴 | 需要有人在现场 |
| L7 | HEIC 缩略图支持 | ✅ | v1.9.019 已验证 |
| L11 | 桌面真打字 | 🔴 | 需要真实桌面环境 |
| L12 | Wayland 原生支持 | 🔴 | 需 Wayland 环境 |

---

**当前版本**: v1.9.020  
**最后更新**: 2026-09-18
