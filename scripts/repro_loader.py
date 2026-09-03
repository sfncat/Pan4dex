# -*- coding: utf-8 -*-
"""直接单测 ThumbnailLoader：真实 PNG 能否在后台线程加载并发出 loaded 信号"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThreadPool, QTimer
from widgets.thumbnail_view import ThumbnailLoader

IMG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "test_media", "201556.jpg")
FAKE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "test_media", "3.jpg")  # 真实
FAKE2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "test_media", "227607.jpg")  # 真实


def main():
    app = QApplication(sys.argv)

    # 主线程先读一次真实图，确保插件已加载
    from PyQt6.QtGui import QImageReader
    r = QImageReader(IMG)
    print("main-thread canRead:", r.canRead(), "size:", r.size(), flush=True)

    results = {}

    def on_loaded(path, image):
        results[path] = ("loaded", not image.isNull())
        print(f"SIGNAL loaded: {os.path.basename(path)} isNull={image.isNull()}", flush=True)

    def on_error(path):
        results[path] = ("error", None)
        print(f"ERROR: {os.path.basename(path)}", flush=True)

    def start():
        pool = QThreadPool()
        pool.setMaxThreadCount(4)
        for p in [IMG, FAKE2]:
            loader = ThumbnailLoader(p)
            loader.signals.loaded.connect(on_loaded)
            pool.start(loader)
        print("started 2 loaders; pool.activeThreadCount()=", pool.activeThreadCount(), flush=True)
        QTimer.singleShot(3000, report)

    def report():
        print("final results:", results, flush=True)
        print("waitForDone:", flush=True)
        app.quit()

    QTimer.singleShot(200, start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
