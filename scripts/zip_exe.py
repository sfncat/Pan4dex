import zipfile, os
z = zipfile.ZipFile('pan4dex.zip', 'w')
z.write('releases/pan4dex-v0.9.536.exe', 'pan4dex.exe')
z.close()
print('zip created')
