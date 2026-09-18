"""
Pan4dex 万格 — 用户操作配置管理
支持自定义操作和快捷键绑定
"""
import json
import os
from pathlib import Path


class UserOperationsConfig:
    """用户操作配置管理器"""
    
    def __init__(self, config_dir=None):
        """初始化配置管理器"""
        if config_dir is None:
            config_dir = Path.home() / ".config" / "pan4dex"
        
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
            return self.default_operations.copy()
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 启用所有操作
                for op in data:
                    op['enabled'] = True
                return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载配置失败：{e}")
            return self.default_operations.copy()
    
    def _save_config(self, operations):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(operations, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"保存配置失败：{e}")
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
        """执行命令"""
        import subprocess
        
        # 替换占位符
        cmd = command.replace('{}', file_path)
        
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return False, result.stderr
            return True, result.stdout
        except subprocess.TimeoutExpired:
            return False, "命令执行超时"
        except Exception as e:
            return False, str(e)
