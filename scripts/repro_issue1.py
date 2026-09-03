# -*- coding: utf-8 -*-
"""
问题 1 最小复现脚本：
在 QVBoxLayout 里放置 tree_view(隐藏) + thumbnail_view，循环切换可见性，
检查第二次切换到 xlarge 后是否空白。
用法: py -3.11 scripts/repro_issue1.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTreeView)
from PyQt6.QtCore import QTimer, QSize

from widgets.thumbnail_view import ThumbnailView

TEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根，107+ 个条目


class Toggler(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Issue1 repro")
        self.resize(900, 700)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.tree_view = QTreeView()
        self.layout.addWidget(self.tree_view)
        self.thumbnail_view = ThumbnailView()
        self.thumbnail_view.setVisible(False)
        self.layout.addWidget(self.thumbnail_view)
        self.mode = 'icon'
        self.toggle_count = 0

    def switch(self):
        """模拟 on_view_mode_changed: icon -> xlarge -> icon -> xlarge ..."""
        self.toggle_count += 1
        if self.mode == 'icon':
            self.mode = 'xlarge'
            self.tree_view.setVisible(False)
            self.thumbnail_view.setVisible(True)
            self.thumbnail_view.show()
            self.thumbnail_view.load_directory(TEST_DIR)
        else:
            self.mode = 'icon'
            self.tree_view.setVisible(True)
            self.thumbnail_view.setVisible(False)
        self.report(self.mode)

    def report(self, mode):
        v = self.thumbnail_view
        item0 = v.item(0)
        rect0 = v.visualItemRect(item0) if item0 else None
        vp = v.viewport()
        print(f"[{self.toggle_count}] mode={mode} count={v.count()} "
              f"isVisible={v.isVisible()} viewport={vp.size().width()}x{vp.size().height()} "
              f"item0_rect={rect0} item0_icon_null={item0.icon().isNull() if item0 else None}",
              flush=True)
        # 抓图检测空白（有内容时像素应有差异）
        pm = v.grab()
        img = pm.toImage()
        w, h = img.width(), img.height()
        samples = []
        for x in range(0, w, max(1, w // 8)):
            for y in range(0, h, max(1, h // 8)):
                samples.append(img.pixelColor(x, y))
        uniq = len({(c.red(), c.green(), c.blue()) for c in samples})
        print(f"    grab={w}x{h} unique_sample_colors={uniq} (<=2 表示空白)", flush=True)


def main():
    app = QApplication(sys.argv)
    t = Toggler()
    t.show()
    steps = [
        ("切到超大图标(第一次)", lambda: t.switch()),
        ("切回图标", lambda: t.switch()),
        ("再切超大图标(第二次-问题点)", lambda: t.switch()),
        ("切回图标", lambda: t.switch()),
        ("第三次切超大图标", lambda: t.switch()),
    ]
    def run(i=0):
        if i >= len(steps):
            app.quit()
            return
        name, fn = steps[i]
        print(f"--- {name} ---", flush=True)
        fn()
        QTimer.singleShot(400, lambda: run(i + 1))
    QTimer.singleShot(200, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
