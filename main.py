#!/usr/bin/env python3
"""
Pan4dex 万格 — 跨平台四窗格文件管理器
"""

__version__ = "0.8.1"
__app_name__ = "Pan4dex"
__app_name_cn__ = "万格"
__build_time__ = ""  # 构建时自动注入，格式：YYYY-MM-DD HH:MM:SS

import sys
import os

# 支持 PyInstaller 打包后的资源路径
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    """程序入口"""
    import sys
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    
    # Windows DPI 适配 - 必须在创建 QApplication 之前设置
    if sys.platform == "win32":
        import os
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        # 启用 Windows 原生 DPI 感知
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PerMonitorV2
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass
    
    # 启用高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("sfncat")
    
    # 设置默认样式为 Fusion（跨平台一致性最好）
    app.setStyle("Fusion")
    
    # Windows 字体修复
    if sys.platform == "win32":
        from PyQt6.QtGui import QFont
        font = QFont("Microsoft YaHei UI", 9)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        app.setFont(font)
    
    from core.main_window import MainWindow
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
