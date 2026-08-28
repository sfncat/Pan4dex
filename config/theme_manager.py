"""
Pan4dex 万格 — 主题管理器
"""
import json
import os
from pathlib import Path
from typing import Optional


class ThemeManager:
    """主题管理器"""
    
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
        self.themes = {}
        self.custom_themes_dir = self._get_custom_themes_dir()
        
        # 加载内置主题
        self._load_builtin_themes()
        
        # 加载自定义主题
        self._load_custom_themes()
    
    def _get_custom_themes_dir(self) -> str:
        """获取自定义主题目录"""
        import sys
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", "")
        else:
            base = str(Path.home() / ".config")
        
        themes_dir = os.path.join(base, "pan4dex", "themes")
        os.makedirs(themes_dir, exist_ok=True)
        return themes_dir
    
    def _load_builtin_themes(self):
        """加载内置主题"""
        self.themes["dark"] = {
            "name": "dark",
            "display_name": "深色主题",
            "window_bg": "#1E1E1E",
            "window_text": "#E0E0E0",
            "menubar_bg": "#2D2D2D",
            "menubar_text": "#E0E0E0",
            "menubar_hover": "#404040",
            "menubar_item_selected": "#404040",
            "toolbar_bg": "#2D2D2D",
            "toolbar_border": "#404040",
            "statusbar_bg": "#2D2D2D",
            "statusbar_text": "#E0E0E0",
            "statusbar_border": "#404040",
            "list_bg": "#1E1E1E",
            "list_text": "#E0E0E0",
            "list_hover": "#3A3A3A",
            "list_selected": "#0D6EFD",
            "list_border": "none",
            "header_bg": "#2D2D2D",
            "header_text": "#E0E0E0",
            "header_border": "#404040",
            "progress_bg": "#2D2D2D",
            "progress_chunk": "#0D6EFD",
            "label_text": "#AAAAAA",
            "combo_bg": "#3D3D3D",
            "combo_text": "#E0E0E0",
            "combo_border": "#505050",
            "combo_hover_border": "#0D6EFD",
            "toolbtn_bg": "#3D3D3D",
            "toolbtn_text": "#E0E0E0",
            "toolbtn_border": "#505050",
            "toolbtn_hover_bg": "#505050",
            "toolbtn_hover_border": "#0D6EFD",
            "dock_title_bg": "#2D2D2D",
            "dock_title_text": "#E0E0E0",
            "scroll_bg": "#1E1E1E",
            "border": "#404040"
        }
        
        self.themes["light"] = {
            "name": "light",
            "display_name": "浅色主题",
            "window_bg": "#F5F5F5",
            "window_text": "#212121",
            "menubar_bg": "#F5F5F5",
            "menubar_text": "#212121",
            "menubar_hover": "#E0E0E0",
            "menubar_item_selected": "#E0E0E0",
            "toolbar_bg": "#F5F5F5",
            "toolbar_border": "#CCCCCC",
            "statusbar_bg": "#F5F5F5",
            "statusbar_text": "#212121",
            "statusbar_border": "#CCCCCC",
            "list_bg": "#FFFFFF",
            "list_text": "#212121",
            "list_hover": "#E8E8E8",
            "list_selected": "#0D6EFD",
            "list_border": "none",
            "header_bg": "#F5F5F5",
            "header_text": "#212121",
            "header_border": "#CCCCCC",
            "progress_bg": "#E0E0E0",
            "progress_chunk": "#0D6EFD",
            "label_text": "#666666",
            "combo_bg": "#FFFFFF",
            "combo_text": "#212121",
            "combo_border": "#CCCCCC",
            "combo_hover_border": "#0D6EFD",
            "toolbtn_bg": "#FFFFFF",
            "toolbtn_text": "#212121",
            "toolbtn_border": "#CCCCCC",
            "toolbtn_hover_bg": "#E0E0E0",
            "toolbtn_hover_border": "#0D6EFD",
            "dock_title_bg": "#F5F5F5",
            "dock_title_text": "#212121",
            "scroll_bg": "#FFFFFF",
            "border": "#CCCCCC"
        }
    
    def _load_custom_themes(self):
        """加载自定义主题"""
        if not os.path.exists(self.custom_themes_dir):
            return
        
        for filename in os.listdir(self.custom_themes_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.custom_themes_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        theme = json.load(f)
                    
                    if "name" in theme:
                        self.themes[theme["name"]] = theme
                except (json.JSONDecodeError, IOError):
                    pass
    
    def get_theme(self, name: str) -> Optional[dict]:
        """获取主题"""
        return self.themes.get(name)
    
    def get_all_themes(self) -> dict:
        """获取所有主题"""
        return self.themes.copy()
    
    def apply_theme(self, name: str) -> bool:
        """
        应用主题
        
        Args:
            name: 主题名称
        
        Returns:
            bool: 是否成功应用
        """
        from PyQt6.QtWidgets import QApplication
        
        theme = self.get_theme(name)
        if not theme:
            return False
        
        qss = self._generate_qss(theme)
        QApplication.instance().setStyleSheet(qss)
        
        self.current_theme = name
        return True
    
    def _generate_qss(self, theme: dict) -> str:
        """生成 QSS 样式表"""
        return f"""
        QMainWindow {{
            background-color: {theme.get('window_bg', '#2D2D2D')};
            color: {theme.get('window_text', '#CCCCCC')};
        }}
        
        QMenuBar {{
            background-color: {theme.get('menubar_bg', '#2D2D2D')};
            color: {theme.get('menubar_text', '#CCCCCC')};
            border-bottom: 1px solid {theme.get('border', '#404040')};
        }}
        
        QMenuBar::item:selected {{
            background-color: {theme.get('menubar_item_selected', '#404040')};
        }}
        
        QMenu {{
            background-color: {theme.get('menubar_bg', '#2D2D2D')};
            color: {theme.get('menubar_text', '#CCCCCC')};
            border: 1px solid {theme.get('border', '#404040')};
        }}
        
        QMenu::item:selected {{
            background-color: {theme.get('menubar_item_selected', '#404040')};
        }}
        
        QToolBar {{
            background-color: {theme.get('toolbar_bg', '#2D2D2D')};
            border-bottom: 1px solid {theme.get('toolbar_border', '#404040')};
            spacing: 5px;
            padding: 3px;
        }}
        
        QStatusBar {{
            background-color: {theme.get('statusbar_bg', '#2D2D2D')};
            color: {theme.get('statusbar_text', '#CCCCCC')};
            border-top: 1px solid {theme.get('statusbar_border', '#404040')};
        }}
        
        QTreeView {{
            background-color: {theme.get('list_bg', '#1E1E1E')};
            color: {theme.get('list_text', '#CCCCCC')};
            border: {theme.get('list_border', 'none')};
            selection-background-color: {theme.get('list_selected', '#2196F3')};
            outline: none;
        }}
        
        QTreeView::item:hover {{
            background-color: {theme.get('list_hover', '#2A2A2A')};
        }}
        
        QTreeView::item:selected {{
            background-color: {theme.get('list_selected', '#2196F3')};
            color: #FFFFFF;
        }}
        
        QHeaderView::section {{
            background-color: {theme.get('header_bg', '#2D2D2D')};
            color: {theme.get('header_text', '#CCCCCC')};
            border: 1px solid {theme.get('header_border', '#404040')};
            padding: 5px;
        }}
        
        QProgressBar {{
            background-color: {theme.get('progress_bg', '#2D2D2D')};
            border: none;
        }}
        
        QProgressBar::chunk {{
            background-color: {theme.get('progress_chunk', '#2196F3')};
        }}
        
        QLabel {{
            color: {theme.get('label_text', '#888888')};
            font-size: 11px;
        }}
        
        QComboBox {{
            background-color: {theme.get('combo_bg', '#3D3D3D')};
            color: {theme.get('combo_text', '#CCCCCC')};
            border: 1px solid {theme.get('combo_border', '#505050')};
            border-radius: 3px;
            padding: 2px 5px;
        }}
        
        QComboBox:hover {{
            border-color: {theme.get('combo_hover_border', '#2196F3')};
        }}
        
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        
        QToolButton {{
            background-color: {theme.get('toolbtn_bg', '#3D3D3D')};
            color: {theme.get('toolbtn_text', '#CCCCCC')};
            border: 1px solid {theme.get('toolbtn_border', '#505050')};
            border-radius: 3px;
        }}
        
        QToolButton:hover {{
            background-color: {theme.get('toolbtn_hover_bg', '#505050')};
            border-color: {theme.get('toolbtn_hover_border', '#2196F3')};
        }}
        
        QDockWidget {{
            color: {theme.get('dock_title_text', '#CCCCCC')};
        }}
        
        QDockWidget::title {{
            background-color: {theme.get('dock_title_bg', '#2D2D2D')};
            padding: 5px;
            border-bottom: 1px solid {theme.get('border', '#404040')};
        }}
        
        QScrollArea {{
            border: none;
            background-color: {theme.get('scroll_bg', '#1E1E1E')};
        }}
        
        QSplitter::handle {{
            background-color: {theme.get('border', '#404040')};
        }}
        
        QSplitter::handle:horizontal {{
            width: 2px;
        }}
        
        QSplitter::handle:vertical {{
            height: 2px;
        }}
        """
    
    def save_custom_theme(self, theme: dict, filename: str):
        """保存自定义主题"""
        if not filename.endswith(".json"):
            filename += ".json"
        
        filepath = os.path.join(self.custom_themes_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(theme, f, ensure_ascii=False, indent=2)
        
        # 重新加载
        self._load_custom_themes()
    
    def delete_custom_theme(self, name: str):
        """删除自定义主题"""
        if name in ("dark", "light"):
            return  # 不能删除内置主题
        
        theme_file = os.path.join(self.custom_themes_dir, f"{name}.json")
        if os.path.exists(theme_file):
            os.remove(theme_file)
            if name in self.themes:
                del self.themes[name]
    
    def export_theme(self, name: str, filepath: str):
        """导出主题"""
        theme = self.get_theme(name)
        if theme:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(theme, f, ensure_ascii=False, indent=2)
    
    def import_theme(self, filepath: str):
        """导入主题"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                theme = json.load(f)
            
            if "name" in theme:
                self.themes[theme["name"]] = theme
                return True
        except (json.JSONDecodeError, IOError):
            pass
        
        return False
