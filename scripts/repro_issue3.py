# -*- coding: utf-8 -*-
"""
问题 3 验证：修复 NameError 后，xlarge 下懒加载缩略图是否真的触发并填充缓存。
用法: py -3.11 scripts/repro_issue3.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QSplitter, QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer, Qt

from core.pane import Pane

TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_media")


def main():
    app = QApplication(sys.argv)
    h = QWidget()
    h.setWindowTitle("Issue3 probe")
    h.resize(900, 700)
    lay = QVBoxLayout(h)
    lay.setContentsMargins(0, 0, 0, 0)
    sp = QSplitter(Qt.Orientation.Vertical)
    pane = Pane(pane_id="pane_1", parent=h)
    sp.addWidget(pane)
    lay.addWidget(sp)
    h.show()

    def step1():
        pane.navigate_to(TEST_DIR)
        print(f"navigated to {TEST_DIR}: current_path={pane.current_path}", flush=True)
        pane.on_view_mode_changed('xlarge')
        print(f"xlarge: count={pane.thumbnail_view.count()} visible={pane.thumbnail_view.isVisible()} "
              f"lazy_active={pane.thumbnail_view._lazy_timer.isActive()} "
              f"loading={len(pane.thumbnail_view._loading)} cache={len(pane.thumbnail_view._thumbnail_cache)}",
              flush=True)
        QTimer.singleShot(5000, step2)

    def step2():
        v = pane.thumbnail_view
        print(f"after 5s: lazy_active={v._lazy_timer.isActive()} "
              f"loading={len(v._loading)} cache={len(v._thumbnail_cache)}",
              flush=True)
        # 统计：有缩略图的图片数 / 总图片数 / 失败数
        total_img = 0
        has_thumb = 0
        default_icon = 0
        for i in range(v.count()):
            it = v.item(i)
            p = it.data(Qt.ItemDataRole.UserRole)
            if not p or not v._is_image(p):
                continue
            total_img += 1
            if p in v._thumbnail_cache:
                has_thumb += 1
            elif it.icon().isNull() or it.icon().pixmap(32).isNull():
                default_icon += 1
        print(f"  total_images={total_img} has_thumbnail={has_thumb} default_icon={default_icon}",
              flush=True)
        # 打印前 20 个图片项的状态
        shown = 0
        for i in range(v.count()):
            it = v.item(i)
            p = it.data(Qt.ItemDataRole.UserRole)
            if not p or not v._is_image(p):
                continue
            status = "CACHED" if p in v._thumbnail_cache else ("LOADING" if p in v._loading else "MISS")
            print(f"  [{i:3d}] {status} {os.path.basename(p)}", flush=True)
            shown += 1
            if shown >= 25:
                break
        app.quit()

    QTimer.singleShot(300, step1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
