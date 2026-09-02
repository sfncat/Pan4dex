"""
测试 ThumbnailView 在 QHBoxLayout 中 hide/show 切换
模拟 pane.py 的实际布局结构
"""
import sys
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QTreeView, QLabel
from PyQt6.QtCore import QTimer, QSize

app = QApplication(sys.argv)

from widgets.thumbnail_view import ThumbnailView

# 模拟 pane.py 的布局结构
file_list_widget = QWidget()
file_list_layout = QHBoxLayout(file_list_widget)
file_list_layout.setContentsMargins(0, 0, 0, 0)
file_list_layout.setSpacing(0)

tree_view = QTreeView()
thumbnail_view = ThumbnailView()

file_list_layout.addWidget(tree_view)
file_list_layout.addWidget(thumbnail_view)

# 外层容器（模拟 h_container）
h_container = QWidget()
h_layout = QHBoxLayout(h_container)
h_layout.setContentsMargins(0, 0, 0, 0)
h_layout.addWidget(file_list_widget, 1)

# 设置大小
h_container.resize(800, 600)

test_dir = "."

print("=== 测试开始 ===")
print(f"测试目录: {test_dir}")
print(f"容器大小: {h_container.size().width()}x{h_container.size().height()}")

# 第一次：显示超大图标
print("\n--- 第一次: xlarge 模式 ---")
tree_view.setVisible(False)
thumbnail_view.setVisible(True)
h_container.update()
app.processEvents()

thumbnail_view.load_directory(test_dir)
count1 = thumbnail_view.count()
size1 = thumbnail_view.size()
vis1 = thumbnail_view.isVisible()
print(f"  thumbnail 大小: {size1.width()}x{size1.height()}")
print(f"  thumbnail 可见: {vis1}")
print(f"  项目数: {count1}")

# 切换到图标模式
print("\n--- 切换到 icon 模式 ---")
tree_view.setVisible(True)
thumbnail_view.setVisible(False)
h_container.update()
app.processEvents()
print(f"  tree_view 可见: {tree_view.isVisible()}")
print(f"  thumbnail_view 可见: {thumbnail_view.isVisible()}")

# 第二次：切回超大图标
print("\n--- 第二次: xlarge 模式 ---")
tree_view.setVisible(False)
thumbnail_view.setVisible(True)
h_container.update()
app.processEvents()

thumbnail_view.load_directory(test_dir)
count2 = thumbnail_view.count()
size2 = thumbnail_view.size()
vis2 = thumbnail_view.isVisible()
print(f"  thumbnail 大小: {size2.width()}x{size2.height()}")
print(f"  thumbnail 可见: {vis2}")
print(f"  项目数: {count2}")

# 检查 viewport
vp = thumbnail_view.viewport()
if vp:
    print(f"  viewport 大小: {vp.size().width()}x{vp.size().height()}")
    print(f"  viewport 可见: {vp.isVisible()}")
else:
    print(f"  viewport: None")

if count2 == 0:
    print("\n❌ BUG 复现：项目数为 0")
elif size2.width() == 0 or size2.height() == 0:
    print(f"\n❌ BUG 复现：thumbnail 大小为 0")
else:
    print(f"\n✓ 正常：{count2} 个项目，大小 {size2.width()}x{size2.height()}")

app.processEvents()
print("\n=== 测试结束 ===")
