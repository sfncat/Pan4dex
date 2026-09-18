# 🚀 Pan4dex v1.9.020 构建说明

## ⚠️ 重要提示

由于当前环境限制，**请在本地 Windows 机器上执行以下命令**。

---

## 📋 快速构建步骤（Windows）

### 方法一：双击批处理文件（最简单）

1. 在文件资源管理器中，找到 `build_windows_quick.bat`
2. **双击运行**该文件
3. 等待构建完成（约 3-5 分钟）
4. 产物位置：`releases\pan4dex-1.9.020.zip`

---

### 方法二：命令行构建

打开 PowerShell，执行以下命令：

```powershell
# 进入项目目录
cd c:\workspace\Pan4dex

# 确保依赖已安装
pip install PyQt6 PyInstaller qdarkstyle pillow pillow-heif send2trash pyte

# 执行构建
python scripts\build_windows.py
```

---

## 🔍 验证构建结果

构建成功后，检查以下内容：

### 1. 检查产物文件
```powershell
# 查看 releases 目录
dir releases\pan4dex-1.9.020*

# 应该看到：
# - pan4dex-1.9.020.zip (压缩包)
# - pan4dex-1.9.020\    (解压目录)
```

### 2. 运行程序测试
```powershell
cd releases\pan4dex-1.9.020
.\pan4dex.exe
```

### 3. 测试新功能
启动程序后，测试以下功能：

- ✅ **工具 → 文件比较**
  - 选择"二进制比较"模式
  - 对比两个文件
  
- ✅ **压缩包处理**
  - 选择 7Z 或 RAR 格式
  - 创建压缩包（需安装外部工具）
  
- ✅ **工具 → 用户操作配置**
  - 添加自定义操作
  - 测试命令执行

---

## 🐧 Linux 版本构建

如果您需要构建 Linux 版本，请在一台 Linux 机器上执行：

```bash
# 进入项目目录
cd /path/to/Pan4dex

# 确保 Docker 运行
sudo systemctl start docker

# 执行构建
bash scripts/build-linux-docker.sh
```

产物位置：`releases/pan4dex-1.9.020-linux`

---

## 📊 预期结果

### Windows 版本
- **文件名**: `pan4dex-1.9.020.zip`
- **大小**: ~57 MB
- **结构**:
  ```
  pan4dex-1.9.020/
  ├── pan4dex.exe              # 主程序
  ├── _internal/               # PyInstaller 内部文件
  ├── imageformats/            # 图片插件 (10 个 DLL)
  └── resources/               # 资源文件
  ```

### Linux 版本
- **文件名**: `pan4dex-1.9.020-linux`
- **大小**: ~57 MB
- **类型**: 单文件可执行程序

---

## ❓ 常见问题

### Q: 构建失败 "Access is denied"
**A**: 以管理员身份运行 PowerShell 或 CMD

### Q: 缺少依赖错误
**A**: 先运行 `pip install -r requirements.txt`

### Q: 图片无法显示
**A**: 确保 `imageformats` 目录包含 10 个 DLL 文件

### Q: 7z/RAR 压缩不工作
**A**: 需要单独安装 7-Zip 或 WinRAR

---

## 🆘 获取帮助

- **项目主页**: https://github.com/sfncat/Pan4dex
- **问题反馈**: https://github.com/sfncat/Pan4dex/issues
- **详细指南**: docs/BUILD-GUIDE.md

---

**现在请在您的本地 Windows 机器上运行 `build_windows_quick.bat` 开始构建！** 🎉
