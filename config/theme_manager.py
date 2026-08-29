"""
Pan4dex 万格 — 主题管理器（基于 qdarkstyle）
"""
import os
import sys
from typing import Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont


class ThemeManager:
    """主题管理器 - 基于 qdarkstyle"""
    
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
        self.current_theme = "dark"
        self.current_font_family = "系统默认"
        self.current_font_size = 9
        
        # 可用主题
        self.themes = {
            "dark": {"name": "dark", "display_name": "深色 (QDarkStyle)", "qss": None},
            "light": {"name": "light", "display_name": "浅色 (QDarkStyle)", "qss": None},
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
    
    def apply_theme(self, name: str) -> bool:
        """应用主题"""
        if name not in self.themes:
            return False
        
        app = QApplication.instance()
        if app is None:
            return False
        
        if name == "dark":
            import qdarkstyle
            app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))
        elif name == "light":
            import qdarkstyle
            app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6', palette=self._get_light_palette()))
        else:
            app.setStyleSheet("")
        
        self.current_theme = name
        return True
    
    def _get_light_palette(self):
        """获取浅色调色板"""
        import qdarkstyle
        # qdarkstyle 自带浅色
        return qdarkstyle.LightPalette
    
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
