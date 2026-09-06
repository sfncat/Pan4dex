"""
Pan4dex 万格 — 文件关联配置
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pan4dex.file_associations")


def _clean_child_env() -> dict:
    """子进程环境：剔除 PyInstaller 注入的库搜索路径。

    PyInstaller bootloader 会在运行时设置 LD_LIBRARY_PATH 指向打包目录
    （/proc/environ 是启动快照，看不到运行中注入的值）。子进程（gedit、
    eog 等系统 GUI 应用）继承后会用打包目录里的旧版 glib/gtk 等库，
    与目标系统版本冲突，表现为 symbol lookup error / cannot open
    display 后立即退出（退出码 127）。源码运行时无此注入，剔除无害。
    """
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    return env

# Linux 内置按类型候选应用（按常见程度排序，取第一个存在的）。
# xdg-open 在打包/精简桌面环境常返回"no method available"，因此内置
# 一份直接可用的应用候选，不依赖桌面集成；全部缺失才退回 xdg-open。
_LINUX_APP_CANDIDATES = {
    # 文本 / 代码 / 配置
    ".txt": ["gedit", "gnome-text-editor", "mousepad", "leafpad", "xed", "pluma", "kate", "kwrite"],
    ".md": ["gedit", "marktext", "typora", "gnome-text-editor", "mousepad", "xed", "kate"],
    ".log": ["gedit", "gnome-text-editor", "mousepad", "leafpad", "kate"],
    ".ini": ["gedit", "gnome-text-editor", "mousepad", "leafpad", "kate"],
    ".cfg": ["gedit", "gnome-text-editor", "mousepad", "leafpad", "kate"],
    ".conf": ["gedit", "gnome-text-editor", "mousepad", "leafpad", "kate"],
    ".csv": ["gedit", "gnome-text-editor", "mousepad", "libreoffice", "leafpad"],
    ".py": ["code", "gedit", "kate", "gnome-text-editor", "mousepad", "xed"],
    ".js": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".ts": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".json": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".xml": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".yml": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".yaml": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".toml": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    ".sh": ["code", "gedit", "kate", "gnome-text-editor", "mousepad"],
    # 图片
    ".png": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    ".jpg": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    ".jpeg": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    ".gif": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    ".bmp": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    ".webp": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    ".svg": ["eog", "gpicview", "feh", "gwenview", "viewnior", "xdg-open"],
    # 文档
    ".pdf": ["evince", "okular", "qpdfview", "mupdf", "xpdf", "xdg-open"],
    ".doc": ["libreoffice", "abiword", "xdg-open"],
    ".docx": ["libreoffice", "abiword", "xdg-open"],
    ".xls": ["libreoffice", "xdg-open"],
    ".xlsx": ["libreoffice", "xdg-open"],
    ".ppt": ["libreoffice", "xdg-open"],
    ".pptx": ["libreoffice", "xdg-open"],
    ".odt": ["libreoffice", "abiword", "xdg-open"],
    # 视频
    ".mp4": ["vlc", "mpv", "totem", "celluloid", "xdg-open"],
    ".mkv": ["vlc", "mpv", "totem", "celluloid", "xdg-open"],
    ".avi": ["vlc", "mpv", "totem", "celluloid", "xdg-open"],
    ".mov": ["vlc", "mpv", "totem", "celluloid", "xdg-open"],
    ".webm": ["vlc", "mpv", "totem", "celluloid", "xdg-open"],
    ".flv": ["vlc", "mpv", "totem", "celluloid", "xdg-open"],
    # 音频
    ".mp3": ["vlc", "rhythmbox", "audacious", "totem", "xdg-open"],
    ".wav": ["vlc", "rhythmbox", "audacious", "totem", "xdg-open"],
    ".flac": ["vlc", "rhythmbox", "audacious", "totem", "xdg-open"],
    ".ogg": ["vlc", "rhythmbox", "audacious", "totem", "xdg-open"],
    ".m4a": ["vlc", "rhythmbox", "audacious", "totem", "xdg-open"],
    # 网页
    ".html": ["firefox", "chromium", "google-chrome", "xdg-open"],
    ".htm": ["firefox", "chromium", "google-chrome", "xdg-open"],
}


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
            logger.warning("打开失败：文件不存在 %s", file_path)
            return False
        
        if sys.platform == "win32":
            # 统一转反斜杠规范化：Qt 返回的 UNC 网络盘路径是正斜杠
            # （//server/share/...），os.startfile（ShellExecute）对正斜杠
            # UNC 解析失败报 WinError 2，反斜杠标准 UNC 则可正常打开
            file_path = os.path.normpath(file_path)
        
        # 1) 用户配置的文件关联
        assoc = self.get_association(file_path)
        
        if assoc:
            app = assoc["app"]
            args = assoc.get("args", [])
            
            # 检查应用是否存在
            if self._check_app_exists(app):
                cmd = [app] + args + [file_path]
                try:
                    # xdg-open/gio 是"查找默认应用"的间接层，可能静默失败，
                    # 需短观察确认；失败则继续尝试内置候选/兜底
                    if app in ("xdg-open", "gio"):
                        if self._run_open(cmd):
                            return True
                    else:
                        self._spawn(cmd)
                        return True
                except Exception as e:
                    logger.warning("打开文件失败 %s: %s", app, e)
            else:
                logger.info("关联应用 %s 不存在，继续尝试其他方式打开 %s", app, file_path)
        
        # 2) 系统默认打开（内置按类型候选 → xdg-open/gio 兜底）
        return self._open_with_default(file_path)
    
    @staticmethod
    def _spawn(cmd):
        """启动外部程序（GUI 应用）。

        必须重定向 stdio + 独立进程组：PyInstaller 冻结环境下主程序
        stdin/stdout/stderr 可能无效，子进程（如 xdg-open）继承后写
        stderr 会直接崩溃导致"没反应"；独立会话可避免主程序退出时
        误杀刚启动的应用。
        stderr 落到临时日志，便于排查"应用启动即退出"类问题。
        """
        import tempfile
        err_path = os.path.join(tempfile.gettempdir(), "pan4dex_open_stderr.log")
        try:
            err_fd = open(err_path, "ab")
        except OSError:
            err_fd = subprocess.DEVNULL
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err_fd,
            start_new_session=True,
            env=_clean_child_env(),
        )
        try:
            err_fd.close()
        except Exception:
            pass
    
    def _check_app_exists(self, app: str) -> bool:
        """检查应用是否存在"""
        import shutil
        return shutil.which(app) is not None
    
    def _open_with_default(self, file_path: str) -> bool:
        """使用系统默认应用打开文件（内置按类型候选 → xdg-open/gio 兜底）"""
        if not os.path.exists(file_path):
            return False
        
        try:
            if sys.platform == "win32":
                os.startfile(os.path.normpath(file_path))
                return True
            if sys.platform == "darwin":
                return self._run_open(["open", file_path])
            # Linux/BSD：xdg-open 即"系统默认应用"标准入口（等价 Windows
            # startfile），优先使用；它在打包/精简桌面环境可能返回
            # "no method available"（退出码 4），失败时才用内置候选兜底
            import shutil
            if shutil.which("xdg-open"):
                if self._run_open(["xdg-open", file_path]):
                    return True
                logger.warning("xdg-open 打开失败，使用内置候选兜底: %s", file_path)
            ext = os.path.splitext(file_path)[1].lower()
            for app in _LINUX_APP_CANDIDATES.get(ext, ()):
                if self._check_app_exists(app):
                    if app in ("xdg-open", "gio"):
                        if self._run_open([app, file_path]):
                            return True
                        continue
                    self._spawn([app, file_path])
                    logger.info("内置候选打开 %s -> %s: %s", ext, app, file_path)
                    return True
            if shutil.which("gio"):
                return self._run_open(["gio", "open", file_path])
            logger.warning("无可用应用打开: %s", file_path)
            return False
        except Exception as e:
            logger.warning("使用默认应用打开失败 %s: %s", file_path, e)
            return False

    @staticmethod
    def _run_open(cmd) -> bool:
        """启动打开命令并确认没有立即失败。

        xdg-open 会等默认应用完全就绪才返回（LibreOffice 可能 >10s），
        不能阻塞等待；但找不到默认应用时它会立即退出并返回非零。
        折中：启动后短暂观察——进程存活视为"默认应用启动中"（成功），
        立即退出且非零才视为失败（回退 gio）。
        """
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=_clean_child_env(),
            )
            try:
                rc = p.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                return True  # 仍在运行 = 默认应用启动中
            if rc == 0:
                return True
            logger.warning("打开命令返回非零 %s: %s", rc, cmd)
            return False
        except Exception as e:
            logger.warning("打开命令执行失败 %s: %s", cmd[0], e)
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
