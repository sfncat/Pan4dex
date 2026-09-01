import zipfile, os, glob

# Find the latest exe by modification time
exe_files = glob.glob(r'C:\workspace\pan4dex\releases\pan4dex-v*.exe')
if not exe_files:
    raise FileNotFoundError("No exe found")

latest = max(exe_files, key=os.path.getmtime)
z = zipfile.ZipFile(r'C:\workspace\pan4dex\releases\pan4dex.zip', 'w')
z.write(latest, 'pan4dex.exe')
z.close()
print(f'Zipped {latest} -> pan4dex.zip')
