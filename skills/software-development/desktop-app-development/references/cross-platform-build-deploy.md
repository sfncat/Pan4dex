# Cross-Platform Build & Deploy Workflow

Pan4dex pattern: build on target machines, deploy via SSH/rsync.

## Architecture

```
Dev Machine (kali)
├── Source code
├── scripts/build.sh (orchestrator)
├── releases/ (backup)
│   ├── pan4dex-v{version}-linux
│   └── pan4dex-v{version}.exe
│
├── SSH → gti (192.168.5.58) — Linux build target
│   ├── ~/pan4dex-build/ (synced source)
│   ├── pyinstaller builds dist/pan4dex
│   └── ~/tools/pan4dex/pan4dex (deployed)
│
└── SSH → win (192.168.5.55) — Windows build target
    ├── D:\\workspace\\2026\\pan4dex\\ (synced source)
    ├── pyinstaller builds dist\\pan4dex.exe
    └── releases\\pan4dex-v{version}.exe
```

## Build Script Flow

```bash
#!/usr/bin/env bash
VERSION=$1

# 1. rsync source to Linux target
rsync -avz --exclude='.venv' --exclude='build' --exclude='dist' \
    --exclude='__pycache__' --exclude='.git' --exclude='releases' \
    ./ gti:~/pan4dex-build/

# 2. Build Linux (on target)
ssh gti "cd ~/pan4dex-build && pyinstaller packaging/pan4dex.spec --noconfirm"

# 3. Deploy to target's tools dir
ssh gti "cp ~/pan4dex-build/dist/pan4dex ~/tools/pan4dex/pan4dex && chmod +x ..."

# 4. Sync source to Windows target (MUST clean first!)
ssh win "rd /s /q D:\\workspace\\2026\\pan4dex"
ssh win "mkdir D:\\workspace\\2026\\pan4dex"
scp -r . win:D:/workspace/2026/pan4dex/

# 5. Build Windows
ssh win "cmd /c 'cd /d D:\\workspace\\2026\\pan4dex && pyinstaller --onefile --windowed --name=pan4dex --add-data=resources;resources --hidden-import=qdarkstyle --icon=D:\\workspace\\2026\\pan4dex\\packaging\\pan4dex.ico main.py'"

# 6. Pull artifacts back to releases/
scp gti:~/pan4dex-build/dist/pan4dex releases/pan4dex-${VERSION}-linux
scp win:D:/workspace/2026/pan4dex/releases/pan4dex-${VERSION}.exe releases/
```

## Deploying to Remote Windows Target

Problem: `scp` from kali directly to sshuser@192.168.5.55 can fail with permission issues, and binary files may get corrupted during transfer.

**Reliable pattern: build → zip → deploy**

1. On Windows build host (win54): zip the exe
2. Download zip to kali: `scp win54:C:/.../pan4dex.zip local.zip`
3. Upload zip to deploy host (win55): `scp local.zip sshuser@192.168.5.55:D:/workspace/2026/pan4dex/dist/pan4dex.zip`
4. Extract on deploy host: `powershell -Command Expand-Archive -LiteralPath pan4dex.zip -DestinationPath . -Force`

```bash
# Kill running app, replace, restart
ssh sshuser@192.168.5.55 'cmd /c "taskkill /F /IM pan4dex* /T 2>nul & cd /d D:\workspace\2026\pan4dex\dist & del /F pan4dex.exe 2>nul & powershell -Command Expand-Archive -LiteralPath pan4dex.zip -DestinationPath . -Force"'
```

**Why zip?** Direct scp of large binary files can corrupt them. ZIP provides CRC verification.

## Windows Build Machine (win54) to Deploy Target (win55)

```bash
# Build on win54 (192.168.5.54, kali user)
ssh win54 'cmd /c "cd C:\workspace\pan4dex && python scripts/build_windows.py v0.9.X"'

# Zip the output
ssh win54 'cmd /c "cd C:\workspace\pan4dex && python scripts/zip_it.py"'

# Pull zip to kali
scp win54:C:/workspace/pan4dex/releases/pan4dex.zip /local/path/

# Push to win55
scp /local/path/pan4dex.zip sshuser@192.168.5.55:D:/workspace/2026/pan4dex/dist/pan4dex.zip

# Extract and verify
ssh sshuser@192.168.5.55 'cmd /c "cd /d D:\workspace\2026\pan4dex\dist && powershell -Command Expand-Archive -LiteralPath pan4dex.zip -DestinationPath . -Force && dir pan4dex.exe"'
```

## Key Pitfalls

| Pitfall | Solution |
|---------|----------|
| Windows `scp` path escaping | Use single quotes around Windows paths: `'win59:C:\\path'` |
| `rsync` to Windows fails | Use `tar` + `scp` or `scp -r` for Windows targets |
| `build.bat` needs `cmd /c` | Windows SSH default is PowerShell; prefix with `cmd /c` |
| `sed` injection quoting | Use pipe delimiter: `sed 's|old|new|'` to avoid slash conflicts |
| `chmod +x` after deploy | Always chmod after copying to target |
| Windows binary copy back to Linux | `scp` fails with Windows paths; use `ssh win 'cmd /c copy ...'` or `scp win:D:/path/file ./` |
| **Windows build uses old source** | Build script MUST `rd /s /q` the Windows source dir first, then re-sync. scp without clean leaves stale files |
| **Windows --add-data separator** | Windows uses semicolon: `--add-data=resources;resources` (not colon) |
| **Windows build host** | Current: `192.168.5.55` (SS_MB6P, sshuser), path `D:\\workspace\\2026\\pan4dex\\` |
| **Binary size check** | A normal build with PyQt6 is ~36MB. If you see ~8MB, PyQt6 was NOT packaged (forgot `pip install PyQt6` on Windows) |
| **Version number discipline** | NEVER auto-increment `__version__` in main.py. User explicitly controls version numbers. |
| **Windows icon path** | Use absolute path for `--icon`: `--icon=D:\\workspace\\2026\\pan4dex\\packaging\\pan4dex.ico` |
| **scp corrupts binary EXE** | Large EXE files can get corrupted during direct scp. Use ZIP transfer (build → zip → scp → unzip) to preserve integrity |
| **Cannot delete running EXE** | Windows locks running executables. Must `taskkill /F /IM pan4dex.exe` before replacing |

## Build-Time Metadata Injection

```bash
# Inject build timestamp before pyinstaller
BUILD_TIME=$(date '+%Y-%m-%d %H:%M:%S')
ssh gti "sed -i 's|__build_time__ = \"\"|__build_time__ = \"${BUILD_TIME}\"|' main.py && pyinstaller ..."
```

## Version Bump Checklist

1. Update `__version__` in `main.py`
2. Update `docs/changelog.md` with new entry
3. Update `docs/feature-checklist.md` if features changed — **MUST be in same commit as code**
4. Run `bash scripts/build.sh v{version}`
5. Verify both artifacts in `releases/`
6. Verify deployment on target machines
