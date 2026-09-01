import zipfile, os, sys
os.chdir(r'D:\workspace\2026\pan4dex\dist')
# Remove old files
for f in ['pan4dex.exe', 'pan4dex.exe.bak', '_pan4dex_old.exe', 'pan4dex_old.exe', 'pan4dex_old3.exe']:
    try:
        os.remove(f)
    except:
        pass
# Extract new
with zipfile.ZipFile('pan4dex.zip', 'r') as z:
    z.extractall('.')
print('done')
