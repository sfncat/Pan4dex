# packaging/pan4dex.spec
# PyInstaller spec file for Pan4dex 万格

block_cipher = None

a = Analysis(
    ['../main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../resources', 'resources'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtNetwork',
        'qdarkstyle',
        'qdarkstyle.dark',
        'qdarkstyle.light',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 排除新版库，使用系统版本以兼容旧 glibc
a.binaries = [b for b in a.binaries if 'libstdc++' not in b[0]]
a.binaries = [b for b in a.binaries if 'libxcb-cursor' not in b[0]]
a.binaries = [b for b in a.binaries if 'libxkbcommon' not in b[0]]
a.binaries = [b for b in a.binaries if 'libfontconfig' not in b[0]]
a.binaries = [b for b in a.binaries if 'libfreetype' not in b[0]]
a.binaries = [b for b in a.binaries if 'libpng' not in b[0]]
a.binaries = [b for b in a.binaries if 'libharfbuzz' not in b[0]]
a.binaries = [b for b in a.binaries if 'libglib' not in b[0]]
a.binaries = [b for b in a.binaries if 'libpcre' not in b[0]]
a.binaries = [b for b in a.binaries if 'libX11' not in b[0]]
a.binaries = [b for b in a.binaries if 'libXau' not in b[0]]
a.binaries = [b for b in a.binaries if 'libXdmcp' not in b[0]]
a.binaries = [b for b in a.binaries if 'libxcb' not in b[0]]
a.binaries = [b for b in a.binaries if 'libxkbcommon' not in b[0]]
# 不排除 XCB 平台插件（需要支持 X11 显示）
# a.binaries = [b for b in a.binaries if 'platforms/libqxcb' not in b[0]]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pan4dex',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='pan4dex.ico',
)
