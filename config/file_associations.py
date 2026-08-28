"""
Pan4dex 万格 — 文件关联配置
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


class FileAssociations:
    """文件类型-应用映射管理"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = self._get_default_config_dir()
        
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "associations.json")
        self.associations: dict[str, dict] = {}
        
        # 确保配置目录存在
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 加载配置
        self.load()
    
    def _get_default_config_dir(self) -> str:
        """获取默认配置目录"""
        if sys.platform == "win32":
            return os.path.join(os.environ.get("APPDATA", ""), "pan4dex")
        else:
            return os.path.join(Path.home(), ".config", "pan4dex")
    
    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.associations = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.associations = {}
        else:
            # 默认关联
            self.associations = self._get_default_associations()
            self.save()
    
    def save(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.associations, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存配置失败: {e}")
    
    def _get_default_associations(self) -> dict:
        """获取默认文件关联"""
        defaults = {
            ".txt": {"app": "gedit", "args": []},
            ".md": {"app": "gedit", "args": []},
            ".py": {"app": "code", "args": []},
            ".json": {"app": "code", "args": []},
            ".html": {"app": "xdg-open", "args": []},
            ".pdf": {"app": "xdg-open", "args": []},
            ".png": {"app": "xdg-open", "args": []},
            ".jpg": {"app": "xdg-open", "args": []},
            ".mp4": {"app": "xdg-open", "args": []},
            ".mp3": {"app": "xdg-open", "args": []},
        }
        
        # Windows 平台调整
        if sys.platform == "win32":
            defaults.update({
                ".txt": {"app": "notepad", "args": []},
                ".py": {"app": "python", "args": []},
            })
        
        return defaults
    
    def get_association(self, file_path: str) -> Optional[dict]:
        """获取文件关联"""
        ext = os.path.splitext(file_path)[1].lower()
        return self.associations.get(ext)
    
    def set_association(self, ext: str, app: str, args: list = None):
        """设置文件关联"""
        if not ext.startswith('.'):
            ext = '.' + ext
        
        self.associations[ext] = {
            "app": app,
            "args": args or []
        }
        self.save()
    
    def remove_association(self, ext: str):
        """移除文件关联"""
        if not ext.startswith('.'):
            ext = '.' + ext
        
        if ext in self.associations:
            del self.associations[ext]
            self.save()
    
    def open_file(self, file_path: str) -> bool:
        """
        使用关联应用打开文件
        
        Returns:
            bool: 是否成功打开
        """
        if not os.path.exists(file_path):
            return False
        
        assoc = self.get_association(file_path)
        
        if assoc:
            app = assoc["app"]
            args = assoc.get("args", [])
            
            # 检查应用是否存在
            if self._check_app_exists(app):
                cmd = [app] + args + [file_path]
                try:
                    subprocess.Popen(cmd)
                    return True
                except Exception as e:
                    print(f"打开文件失败: {e}")
        
        # 回退到系统默认
        return self._open_with_default(file_path)
    
    def _check_app_exists(self, app: str) -> bool:
        """检查应用是否存在"""
        import shutil
        return shutil.which(app) is not None
    
    def _open_with_default(self, file_path: str) -> bool:
        """使用系统默认应用打开文件"""
        import os
        if not os.path.exists(file_path):
            return False
        
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
            else:
                subprocess.Popen(["xdg-open", file_path])
            return True
        except Exception as e:
            print(f"使用默认应用打开失败: {e}")
            return False
    
    def get_all_associations(self) -> dict:
        """获取所有关联"""
        return self.associations.copy()
    
    def import_associations(self, config_file: str):
        """从文件导入关联"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                self.associations.update(data)
                self.save()
        except (json.JSONDecodeError, IOError) as e:
            print(f"导入配置失败: {e}")
    
    def export_associations(self, config_file: str):
        """导出关联到文件"""
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.associations, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"导出配置失败: {e}")
