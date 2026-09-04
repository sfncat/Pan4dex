"""
Pan4dex 万格 — 文件操作模块
"""
import os
import shutil
import hashlib
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class FileOperationType(Enum):
    """文件操作类型"""
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"
    RENAME = "rename"


class FileOperationStatus(Enum):
    """文件操作状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class FileOperationResult:
    """文件操作结果"""
    success: bool
    operation: FileOperationType
    source: str
    destination: str = ""
    error: str = ""
    files_affected: int = 0


class FileOperations:
    """文件操作类"""
    
    def __init__(self):
        self._cancelled = False
        self._progress_callback: Optional[Callable[[int, str], None]] = None
    
    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """设置进度回调函数"""
        self._progress_callback = callback
    
    def cancel(self):
        """取消操作"""
        self._cancelled = True
    
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._cancelled
    
    def copy(self, sources: list[str], destination: str) -> FileOperationResult:
        """
        复制文件/目录到目标目录
        
        Args:
            sources: 源文件/目录路径列表
            destination: 目标目录路径
        
        Returns:
            FileOperationResult: 操作结果
        """
        self._cancelled = False
        
        if not os.path.isdir(destination):
            return FileOperationResult(
                success=False,
                operation=FileOperationType.COPY,
                source=str(sources),
                destination=destination,
                error="目标目录不存在"
            )
        
        total_files = self._count_files(sources)
        files_copied = 0
        
        for source in sources:
            if self._cancelled:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.COPY,
                    source=source,
                    destination=destination,
                    error="操作已取消",
                    files_affected=files_copied
                )
            
            try:
                result = self._copy_single(source, destination, total_files, files_copied)
                if isinstance(result, FileOperationResult):
                    return result
                files_copied = result
            except Exception as e:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.COPY,
                    source=source,
                    destination=destination,
                    error=str(e),
                    files_affected=files_copied
                )
        
        return FileOperationResult(
            success=True,
            operation=FileOperationType.COPY,
            source=str(sources),
            destination=destination,
            files_affected=files_copied
        )
    
    def _unique_dest_path(self, destination: str, source_name: str) -> str:
        """目标已存在时生成不冲突的目标路径：name (2).ext / name (3).ext …

        解决同目录复制粘贴时 dest == source（shutil 抛 SameFileError）以及
        目标目录已有同名文件时静默覆盖的问题。
        """
        dest_path = os.path.join(destination, source_name)
        if not os.path.exists(dest_path):
            return dest_path
        base, ext = os.path.splitext(source_name)
        counter = 2
        while True:
            candidate = os.path.join(destination, f"{base} ({counter}){ext}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _copy_single(self, source: str, destination: str, total: int, current: int) -> int | FileOperationResult:
        """复制单个文件/目录"""
        source_name = os.path.basename(source)
        dest_path = self._unique_dest_path(destination, source_name)
        
        if os.path.isdir(source):
            # 复制目录
            if not os.path.exists(dest_path):
                os.makedirs(dest_path)
            
            # 递归复制子目录和文件
            for item in os.listdir(source):
                if self._cancelled:
                    return FileOperationResult(
                        success=False,
                        operation=FileOperationType.COPY,
                        source=source,
                        destination=destination,
                        error="操作已取消",
                        files_affected=current
                    )
                
                item_path = os.path.join(source, item)
                if os.path.isdir(item_path):
                    result = self._copy_single(item_path, dest_path, total, current)
                    if isinstance(result, FileOperationResult):
                        return result
                    current = result
                else:
                    shutil.copy2(item_path, dest_path)
                    current += 1
                    self._report_progress(current, total, item)
        else:
            # 复制文件
            shutil.copy2(source, dest_path)
            current += 1
            self._report_progress(current, total, source_name)
        
        return current
    
    def move(self, sources: list[str], destination: str) -> FileOperationResult:
        """
        移动文件/目录到目标目录
        
        Args:
            sources: 源文件/目录路径列表
            destination: 目标目录路径
        
        Returns:
            FileOperationResult: 操作结果
        """
        self._cancelled = False
        
        if not os.path.isdir(destination):
            return FileOperationResult(
                success=False,
                operation=FileOperationType.MOVE,
                source=str(sources),
                destination=destination,
                error="目标目录不存在"
            )
        
        total_files = self._count_files(sources)
        files_moved = 0
        
        for source in sources:
            if self._cancelled:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.MOVE,
                    source=source,
                    destination=destination,
                    error="操作已取消",
                    files_affected=files_moved
                )
            
            try:
                shutil.move(source, destination)
                files_moved += 1
                self._report_progress(files_moved, total_files, os.path.basename(source))
            except Exception as e:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.MOVE,
                    source=source,
                    destination=destination,
                    error=str(e),
                    files_affected=files_moved
                )
        
        return FileOperationResult(
            success=True,
            operation=FileOperationType.MOVE,
            source=str(sources),
            destination=destination,
            files_affected=files_moved
        )
    
    def delete(self, paths: list[str], safe: bool = True) -> FileOperationResult:
        """
        删除文件/目录
        
        Args:
            paths: 要删除的文件/目录路径列表
            safe: 是否安全删除（使用回收站）
        
        Returns:
            FileOperationResult: 操作结果
        """
        self._cancelled = False
        
        files_deleted = 0
        
        for path in paths:
            if self._cancelled:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.DELETE,
                    source=path,
                    error="操作已取消",
                    files_affected=files_deleted
                )
            
            try:
                if safe:
                    import send2trash
                    send2trash.send2trash(path)
                else:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                
                files_deleted += 1
                self._report_progress(files_deleted, len(paths), os.path.basename(path))
            except Exception as e:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.DELETE,
                    source=path,
                    error=str(e),
                    files_affected=files_deleted
                )
        
        return FileOperationResult(
            success=True,
            operation=FileOperationType.DELETE,
            source=str(paths),
            files_affected=files_deleted
        )
    
    def rename(self, path: str, new_name: str) -> FileOperationResult:
        """
        重命名文件/目录
        
        Args:
            path: 原文件/目录路径
            new_name: 新名称
        
        Returns:
            FileOperationResult: 操作结果
        """
        try:
            parent = os.path.dirname(path)
            new_path = os.path.join(parent, new_name)
            
            if os.path.exists(new_path):
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.RENAME,
                    source=path,
                    destination=new_path,
                    error="目标名称已存在"
                )
            
            os.rename(path, new_path)
            
            return FileOperationResult(
                success=True,
                operation=FileOperationType.RENAME,
                source=path,
                destination=new_path
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                operation=FileOperationType.RENAME,
                source=path,
                error=str(e)
            )
    
    def create_folder(self, path: str, name: str) -> FileOperationResult:
        """创建文件夹"""
        try:
            new_path = os.path.join(path, name)
            
            # 避免重名
            if os.path.exists(new_path):
                base, ext = os.path.splitext(name)
                counter = 1
                while os.path.exists(os.path.join(path, f"{base} ({counter}){ext}")):
                    counter += 1
                new_path = os.path.join(path, f"{base} ({counter}){ext}")
            
            os.makedirs(new_path)
            
            return FileOperationResult(
                success=True,
                operation=FileOperationType.COPY,
                source=path,
                destination=new_path
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                operation=FileOperationType.COPY,
                source=path,
                error=str(e)
            )
    
    def create_file(self, path: str, name: str) -> FileOperationResult:
        """创建文件"""
        try:
            new_path = os.path.join(path, name)
            
            # 避免重名
            if os.path.exists(new_path):
                base, ext = os.path.splitext(name)
                counter = 1
                while os.path.exists(os.path.join(path, f"{base} ({counter}){ext}")):
                    counter += 1
                new_path = os.path.join(path, f"{base} ({counter}){ext}")
            
            with open(new_path, 'w') as f:
                pass
            
            return FileOperationResult(
                success=True,
                operation=FileOperationType.COPY,
                source=path,
                destination=new_path
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                operation=FileOperationType.COPY,
                source=path,
                error=str(e)
            )
    
    def calculate_checksum(self, path: str, algorithm: str = "md5") -> str:
        """计算文件校验和"""
        hash_func = hashlib.new(algorithm)
        
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _count_files(self, paths: list[str]) -> int:
        """计算文件总数"""
        count = 0
        for path in paths:
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    count += len(files)
            else:
                count += 1
        return count
    
    def _report_progress(self, current: int, total: int, filename: str):
        """报告进度"""
        if self._progress_callback and total > 0:
            percent = int(current * 100 / total)
            self._progress_callback(percent, filename)
