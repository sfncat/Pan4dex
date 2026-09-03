# -*- coding: utf-8 -*-
"""
问题 1 复现脚本 v2：使用真实 Pane 类 + 120 个条目的目录，模拟真实切换。
用法: py -3.11 scripts/repro_issue1.py  (会先跑 v2)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QSplitter, QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer, Qt

from core.pane import Pane

TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".repro_tmp")


class Host(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Issue1 repro v2 (real Pane)")
        self.resize(900, 700)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.pane = Pane(pane_id="pane_1", parent=self)
        self.splitter.addWidget(self.pane)
        self.layout.addWidget(self.splitter)
        self.mode = 'icon'
        self.toggle_count = 0

    def switch(self):
        self.toggle_count += 1
        if self.mode == 'icon':
            self.mode = 'xlarge'
            self.pane.on_view_mode_changed('xlarge')
        else:
            self.mode = 'icon'
            self.pane.on_view_mode_changed('icon')
        self.report(self.mode)

    def report(self, mode):
        v = self.pane.thumbnail_view
        item0 = v.item(0)
        itemN = v.item(v.count() - 1)
        r0 = v.visualItemRect(item0) if item0 else None
        rN = v.visualItemRect(itemN) if itemN else None
        vp = v.viewport()
        pm = v.grab()
        img = pm.toImage()
        w, h = img.width(), img.height()
        samples = []
        for x in range(0, w, max(1, w // 10)):
            for y in range(0, h, max(1, h // 10)):
                samples.append(img.pixelColor(x, y))
        uniq = len({(c.red(), c.green(), c.blue()) for c in samples})
        print(f"[{self.toggle_count}] mode={mode} count={v.count()} "
              f"isVisible={v.isVisible()} pane_visible={self.pane.isVisible()} "
              f"vp={vp.size().width()}x{vp.size().height()} "
              f"item0_rect={r0} itemN_rect={rN} grab_unique={uniq}",
              flush=True)


def main():
    app = QApplication(sys.argv)
    h = Host()
    h.show()
    steps = [
        ("切到超大图标(第一次)", lambda: h.switch()),
        ("切回图标", lambda: h.switch()),
        ("再切超大图标(第二次-问题点)", lambda: h.switch()),
        ("切回图标", lambda: h.switch()),
        ("第三次切超大图标", lambda: h.switch()),
    ]
    def run(i=0):
        if i >= len(steps):
            app.quit()
            return
        name, fn = steps[i]
        print(f"--- {name} ---", flush=True)
        fn()
        QTimer.singleShot(500, lambda: run(i + 1))
    QTimer.singleShot(300, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
