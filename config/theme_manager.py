"""
Pan4dex 万格 — 主题管理器（基于 qdarkstyle + 缓存优化）
"""
import os
import sys
import logging
from typing import Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

logger = logging.getLogger("pan4dex.theme")

from .app_config import DEFAULT_THEME


class ThemeManager:
    """主题管理器 - 基于 qdarkstyle（缓存解析结果，避免每次加载 CSS）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.current_theme = DEFAULT_THEME
        self.current_font_family = "系统默认"
        self.current_font_size = 9
        
        # 缓存 qdarkstyle 解析后的样式表（避免每次重新解析 CSS）
        self._stylesheet_cache = {}
        
        # 可用主题
        self.themes = {
            "dark": {"name": "dark", "display_name": "深色 (QDarkStyle)", "qss": None},
            "light": {"name": "light", "display_name": "浅色 (现代)", "qss": None},
        }
        
        # 可用字体
        self.fonts = {
            "系统默认": None,
            "Microsoft YaHei UI": "Microsoft YaHei UI",
            "Segoe UI": "Segoe UI",
            "Noto Sans CJK SC": "Noto Sans CJK SC",
            "DejaVu Sans": "DejaVu Sans",
            "Consolas": "Consolas",
            "Courier New": "Courier New",
        }
    
    def get_theme(self, name: str) -> Optional[dict]:
        """获取主题"""
        return self.themes.get(name)
    
    def get_all_themes(self) -> dict:
        """获取所有主题"""
        return self.themes.copy()
    
    def _load_stylesheet(self, name: str) -> str:
        """加载样式表（带缓存）"""
        if name in self._stylesheet_cache:
            return self._stylesheet_cache[name]
        
        import time
        t0 = time.perf_counter()
        
        if name == "dark":
            import qdarkstyle
            stylesheet = qdarkstyle.load_stylesheet(qt_api='pyqt6')
        elif name == "light":
            # 自定义现代浅色主题（比 qdarkstyle LightPalette 更美观）
            stylesheet = self._get_light_stylesheet()
        else:
            stylesheet = ""
        
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(f"[启动计时] qdarkstyle CSS 解析 ({name}): {elapsed:.1f}ms")
        self._stylesheet_cache[name] = stylesheet
        return stylesheet
    
    def _get_light_stylesheet(self) -> str:
        """自定义现代浅色主题"""
        return """
/* 全局背景 */
QWidget {
    background-color: #f8f9fa;
    color: #212529;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 9pt;
}

/* 主窗口背景 — 比窗格略深，营造层次感 */
QMainWindow {
    background-color: #e8eaed;
}

/* 中央部件背景 */
QMainWindow > QWidget {
    background-color: #e8eaed;
}

/* 菜单栏 */
QMenuBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    padding: 2px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #e8f0fe;
    color: #1a73e8;
}

/* 菜单 */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #e8f0fe;
    color: #1a73e8;
}

/* 工具栏 */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    padding: 4px;
    spacing: 4px;
}

/* 按钮 — 扁平无边框，hover 才显底色（Q-Dir 风格） */
QToolButton, QPushButton {
    background-color: transparent;
    color: #3c4043;
    border: none;
    border-radius: 4px;
    padding: 4px 6px;
    min-height: 20px;
    icon-size: 20px;
}
QToolButton:hover, QPushButton:hover {
    background-color: #e8f0fe;
    color: #1967d2;
}
QToolButton:pressed, QPushButton:pressed {
    background-color: #d2e3fc;
    color: #1967d2;
}
QToolButton:checked {
    background-color: #d2e3fc;
    color: #1967d2;
}

/* 输入框 */
QLineEdit, QComboBox {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 2px;
    padding: 2px 6px;
    min-height: 24px;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #1a73e8;
}

/* 树视图 */
QTreeView {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 0;
    outline: 0;
    padding: 2px;
}
QTreeView::item {
    padding: 3px 6px;
    border-radius: 0;
}
QTreeView::item:hover {
    background-color: #f1f3f4;
}
QTreeView::item:selected {
    background-color: #cfe2fc;
    color: #1967d2;
}
QTreeView::branch {
    background: transparent;
}

/* 表头 */
QHeaderView::section {
    background-color: #f5f5f5;
    color: #3c4043;
    border: none;
    border-bottom: 1px solid #d0d0d0;
    border-right: 1px solid #e0e0e0;
    padding: 4px 8px;
    font-weight: normal;
}
QHeaderView::section:hover {
    background-color: #e8eaed;
}

/* 列表视图（QListWidget） */
QListWidget {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 0;
    outline: 0;
    padding: 4px;
}
QListWidget::item {
    padding: 2px;
    border-radius: 0;
}
QListWidget::item:hover {
    background-color: #f1f3f4;
}
QListWidget::item:selected {
    background-color: #cfe2fc;
    color: #1967d2;
}

/* 状态栏 */
QStatusBar {
    background-color: #e8eaed;
    color: #5f6368;
    border-top: 1px solid #dadce0;
}

/* 滚动条 */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #dadce0;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #bdc1c6;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #dadce0;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #bdc1c6;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* 分隔条 — 窗格之间的可见分隔 */
QSplitter::handle {
    background-color: #dadce0;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}
QSplitter::handle:hover {
    background-color: #1a73e8;
}

/* 标签页 */
QTabWidget::pane {
    border: 1px solid #d0d0d0;
    border-radius: 0;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    border: none;
    padding: 4px 12px;
    margin-right: 1px;
    border-radius: 0;
}
QTabBar::tab:hover {
    background: #f1f3f4;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1967d2;
    border: 1px solid #d0d0d0;
    border-bottom: none;
}

/* 分组框 */
QGroupBox {
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #5f6368;
}

/* 复选框 */
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #dadce0;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #1a73e8;
    border-color: #1a73e8;
}

/* 进度条 */
QProgressBar {
    border: none;
    border-radius: 2px;
    background: #e0e0e0;
    max-height: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background: #1a73e8;
    border-radius: 2px;
}

/* 停靠窗口 */
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QDockWidget::title {
    background: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    padding: 8px;
}

/* 工具提示 */
QToolTip {
    background: #3c4043;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
}
"""
    
    def apply_theme(self, name: str) -> bool:
        """应用主题（从缓存获取样式表）"""
        if name not in self.themes:
            return False
        
        app = QApplication.instance()
        if app is None:
            return False
        
        stylesheet = self._load_stylesheet(name)
        app.setStyleSheet(stylesheet)
        self.current_theme = name
        return True
    
    def apply_theme_with_font(self, theme_name: str, font_family: str = None, font_size: int = None) -> bool:
        """应用主题和字体"""
        if font_family:
            self.current_font_family = font_family
        if font_size:
            self.current_font_size = font_size
        
        # 先应用主题
        ok = self.apply_theme(theme_name)
        
        # 再应用字体
        app = QApplication.instance()
        if app and self.current_font_family and self.fonts.get(self.current_font_family):
            font = QFont(self.current_font_family, self.current_font_size)
            app.setFont(font)
        
        return ok
    
    def get_fonts(self) -> dict:
        """获取可用字体"""
        return self.fonts.copy()
