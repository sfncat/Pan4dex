"""
测试 ThumbnailView hide/show 切换是否导致内容丢失
运行方式：QT_QPA_PLATFORM=offscreen python test_thumbnail.py
"""
import sys
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout
from PyQt6.QtCore import QTimer

app = QApplication(sys.argv)

from widgets.thumbnail_view import ThumbnailView

# 模拟 pane 的两个视图
container = QWidget()
layout = QHBoxLayout(container)
tree_view = QWidget()  # 模拟 tree_view
thumbnail_view = ThumbnailView()
layout.addWidget(tree_view)
layout.addWidget(thumbnail_view)

# 找一个有图片的测试目录
test_dir = "D:/workspace/2026/PhotosFrame/test_media" if os.path.exists("D:/workspace/2026/PhotosFrame/test_media") else "."

print("=== 测试开始 ===")
print(f"测试目录: {test_dir}")

# 第一次加载
print("\n--- 第一次: 显示 thumbnail_view ---")
thumbnail_view.setVisible(True)
thumbnail_view.load_directory(test_dir)
count1 = thumbnail_view.count()
print(f"项目数: {count1}")

# 切换到 tree_view（隐藏 thumbnail_view）
print("\n--- 切换到 tree_view（隐藏 thumbnail_view）---")
tree_view.setVisible(True)
thumbnail_view.setVisible(False)

# 切换回 thumbnail_view
print("\n--- 切换回 thumbnail_view（第二次）---")
tree_view.setVisible(False)
thumbnail_view.setVisible(True)
thumbnail_view.load_directory(test_dir)
count2 = thumbnail_view.count()
print(f"项目数: {count2}")

if count2 == 0:
    print("\n❌ BUG 复现：第二次加载项目数为 0")
else:
    print(f"\n✓ 正常：第二次加载项目数为 {count2}")

app.processEvents()
print("\n=== 测试结束 ===")
