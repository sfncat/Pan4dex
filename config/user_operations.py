"""
Pan4dex 万格 — 用户操作配置管理
支持自定义操作和快捷键绑定
"""
import json
import logging
from pathlib import Path

from config.paths import default_config_dir

logger = logging.getLogger("pan4dex.user_operations")


def split_command(command: str) -> list:
    """命令模板 → 词元列表

    `shlex.split(posix=False)` 保住 Windows 路径里的反斜杠（posix 模式会把
    反斜杠序列当转义吃掉），代价是包裹引号留在词元上，所以再去掉成对的引号。
    """
    import shlex
    toks = []
    for tok in shlex.split(command, posix=False):
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ('"', "'"):
            tok = tok[1:-1]
        toks.append(tok)
    return toks


def fill_token(token: str, file_path: str) -> str:
    """词元里的 `{}` 占位符换成文件路径（整词或内嵌如 `--out={}` 都支持）"""
    return token.replace('{}', file_path)


class UserOperationsConfig:
    """用户操作配置管理器"""

    def __init__(self, config_dir=None):
        """初始化配置管理器"""
        if config_dir is None:
            config_dir = default_config_dir()

        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "user_operations.json"

        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 默认操作列表
        self.default_operations = [
            {
                "id": "open_with_code",
                "name": "用代码编辑器打开",
                "command": "code {}",
                "description": "使用 VS Code 打开选中文件",
                "file_types": ["*"],
                "enabled": True
            },
            {
                "id": "open_with_browser",
                "name": "在浏览器中打开",
                "command": "firefox {}",
                "description": "在 Firefox 浏览器中打开",
                "file_types": [".html", ".htm", ".svg"],
                "enabled": True
            }
        ]

        # 加载或创建配置
        self.operations = self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if not self.config_file.exists():
            # 创建默认配置
            self._save_config(self.default_operations)
            return [dict(op) for op in self.default_operations]

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                # enabled 原样保留 —— 读盘时强制改回 True 会让「禁用」活不过重启
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("加载用户操作配置失败：%s", e)
            return [dict(op) for op in self.default_operations]

    def _save_config(self, operations):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(operations, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            logger.warning("保存用户操作配置失败：%s", e)
            return False

    def get_operations(self, enabled_only=True):
        """获取操作列表"""
        if enabled_only:
            return [op for op in self.operations if op.get('enabled', True)]
        return self.operations.copy()

    def add_operation(self, operation):
        """添加新操作"""
        # 生成唯一 ID
        base_id = operation.get('id', 'custom').replace(' ', '_').lower()
        new_id = base_id
        counter = 1
        while any(op['id'] == new_id for op in self.operations):
            new_id = f"{base_id}_{counter}"
            counter += 1

        operation['id'] = new_id
        operation['enabled'] = True

        self.operations.append(operation)
        self._save_config(self.operations)
        return new_id

    def update_operation(self, op_id, updates):
        """更新操作"""
        for i, op in enumerate(self.operations):
            if op['id'] == op_id:
                self.operations[i].update(updates)
                self._save_config(self.operations)
                return True
        return False

    def delete_operation(self, op_id):
        """删除操作"""
        for i, op in enumerate(self.operations):
            if op['id'] == op_id:
                del self.operations[i]
                self._save_config(self.operations)
                return True
        return False

    def enable_operation(self, op_id, enabled=True):
        """启用/禁用操作"""
        return self.update_operation(op_id, {'enabled': enabled})

    def get_operation_by_id(self, op_id):
        """根据 ID 获取操作"""
        for op in self.operations:
            if op['id'] == op_id:
                return op.copy()
        return None

    def execute_command(self, command, file_path):
        """执行命令：`{}` 换成文件路径，路径永远独立成一个参数

        不经 shell 解释 —— 含空格/引号/& 的文件名既不会被拆碎，也不会被当成
        命令语法执行（旧写法 `command.replace('{}', path)` + `shell=True` 两条都占）。
        argv[0] 先过 `shutil.which`：Windows 上 `code` 这类 .cmd 垫片也能解析到
        全路径；找不到时原样交给 CreateProcess。
        """
        import shutil
        import subprocess

        argv = [fill_token(tok, file_path) for tok in split_command(command)]
        if not argv:
            return False, "命令为空"
        argv[0] = shutil.which(argv[0]) or argv[0]
        try:
            result = subprocess.run(argv, shell=False, capture_output=True,
                                    text=True, timeout=300)
            if result.returncode != 0:
                return False, result.stderr
            return True, result.stdout
        except subprocess.TimeoutExpired:
            return False, "命令执行超时"
        except (OSError, ValueError) as e:
            return False, str(e)
