# -*- coding: utf-8 -*-
"""将 1024x1024 PNG 转换为多尺寸 Windows .ico"""
from PIL import Image
import os

img = Image.open('resources/icons/icon_1024.png')
sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
img.save('resources/icons/icon.ico', format='ICO', sizes=sizes)
print(f'icon.ico: {os.path.getsize("resources/icons/icon.ico")} bytes')
ico = Image.open('resources/icons/icon.ico')
print(f'ICO sizes: {ico.info.get("sizes", "unknown")}')
