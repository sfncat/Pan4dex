# win54 Windows Build Host Setup

## Machine Profile

| Property | Value |
|----------|-------|
| **Hostname** | win54 |
| **IP** | 192.168.5.54 |
| **User** | kali (Administrators group) |
| **Python** | 3.13.0 (`C:\Python313\`) |
| **Build dir** | `C:\workspace\pan4dex\` |
| **WOL MAC** | `52:54:10:73:70:cd` |
| **Role** | Windows build host |

## Deploy Target

After building on win54, copy artifacts to win55 (192.168.5.55, sshuser):
`D:\workspace\2026\pan4dex\dist\pan4dex-v0.9.51.exe`

## SSH Key Auth (Windows OpenSSH Admin)

**Critical**: Admin users must use `C:\ProgramData\ssh\administrators_authorized_keys`, NOT user-level `.ssh\authorized_keys`.

```python
# paramiko-based upload script
client.connect(host, username="kali", password=PASS)
sftp = client.open_sftp()

# Check admin
stdin, stdout, client.exec_command("whoami /groups")
output = stdout.read().decode("gbk", errors="ignore")
is_admin = "Administrators" in output

if is_admin:
    auth_path = r"C:\ProgramData\ssh\administrators_authorized_keys"
else:
    auth_path = r"C:\Users\kali\.ssh\authorized_keys"

# Append pubkey
with sftp.open(auth_path, "a") as f:
    f.write(pubkey + "\n")

# Set ACL for admin file
if is_admin:
    client.exec_command(f'icacls "{auth_path}" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"')

# Restart sshd
client.exec_command("Restart-Service sshd -Force")
```

**Note**: `whoami /groups` output is GBK-encoded on Chinese Windows — use `decode("gbk", errors="ignore")`.

## Wake-on-LAN Behavior

| State | WOL Works | Notes |
|-------|-----------|-------|
| **Sleep (30 min idle)** | ✅ | Default behavior |
| **Full shutdown** | ❌ | WOL magic packet ignored |

```bash
# Send WOL
wakeonlan 52:54:10:73:70:cd

# Wait for boot + SSH (up to 120s total)
for i in $(seq 1 12); do
    sleep 5
    if ping -c 1 -W 2 192.168.5.54 &>/dev/null; then
        echo "win54 online"
        break
    fi
done

# Wait for SSH service
for i in $(seq 1 12); do
    sleep 5
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 win54 'echo OK' &>/dev/null; then
        echo "SSH ready"
        break
    fi
done
```

If win54 is fully powered off, WOL won't work — must enable "Wake on LAN" in BIOS/UEFI and网卡 driver power management.

## Source Sync: Encoding Issue

**Problem**: `tar cf - . | ssh win54 'tar xf -'` creates files with GBK encoding on Windows (default codepage). Python source with Chinese comments (e.g., `Pan4dex 万格 — 跨平台四窗格文件管理器`) becomes garbled.

**Symptom**: `pathlib.Path.read_text()` raises `UnicodeDecodeError: 'utf-8' can't decode byte 0x94`.

**Fix in build script**: Read bytes, then decode with fallback:

```python
raw = main_py.read_bytes()
try:
    content = raw.decode("utf-8")
except UnicodeDecodeError:
    content = raw.decode("gbk", errors="ignore")
content = content.replace(...)
main_py.write_text(content, encoding="utf-8")
```

## Build Script (`scripts/build_windows.py`)

```python
import pathlib, datetime, subprocess, sys, os

script_path = pathlib.Path(__file__).resolve()
project_root = script_path.parent.parent
os.chdir(project_root)

VERSION = sys.argv[1] if len(sys.argv) > 1 else None
# ... (auto-detect from main.py if not provided)

# Inject build time (handle encoding)
build_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
main_py = project_root / "main.py"
raw = main_py.read_bytes()
try:
    content = raw.decode("utf-8")
except UnicodeDecodeError:
    content = raw.decode("gbk", errors="ignore")
content = content.replace('__build_time__ = ""', f'__build_time__ = "{build_time}"')
main_py.write_text(content, encoding="utf-8")

# PyInstaller
subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--onefile", "--windowed", "--name=pan4dex",
    "--add-data=resources;resources",
    "--hidden-import=PyQt6.QtCore",
    "--hidden-import=PyQt6.QtGui",
    "--hidden-import=PyQt6.QtWidgets",
    "--hidden-import=qdarkstyle",
    "--hidden-import=qdarkstyle.dark",
    "--hidden-import=qdarkstyle.light",
    "--icon=resources/icons/icon.ico",
    "main.py"
])

# Move to releases/
(project_root / "releases").mkdir(exist_ok=True)
os.replace(project_root / "dist" / "pan4dex.exe",
          project_root / "releases" / f"pan4dex-{VERSION}.exe")
```

## Remote Build Command

```bash
# Sync source
tar cf - . | ssh win54 'cmd /c "cd /d C:\workspace\pan4dex && tar xf -"'

# Build
ssh win54 'cmd /c "cd C:\workspace\pan4dex && python scripts/build_windows.py v0.9.51"'

# Retrieve artifact
scp win54:'C:/workspace/pan4dex/releases/pan4dex-v0.9.51.exe' releases/

# Deploy to win55
scp releases/pan4dex-v0.9.51.exe sshuser@192.168.5.55:'D:/workspace/2026/pan4dex/dist/'
```

## Dependency Installation

Win54 may lack dependencies:

```bash
ssh win54 'pip install PyQt6 PyInstaller send2trash Pillow qdarkstyle cairosvg'
```

## SSH Config

```
Host win54
    HostName 192.168.5.54
    User kali
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

## --skip-windows Flag

Build script supports `--skip-windows` to skip Windows build when win54 is offline:

```bash
bash scripts/build.sh --skip-windows v0.9.51
```
