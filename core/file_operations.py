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


def _is_unc_path(p: str) -> bool:
    """判断路径是否为 Windows UNC 网络共享路径：server 共享形式（正斜杠
    //server/share 或反斜杠形式），以及 send2trash 生成的带长路径前缀的
    UNC 形式。"""
    if os.name != 'nt':
        return False
    return p.replace('/', '\\').startswith('\\\\')


def _is_network_path(p: str) -> bool:
    """判断路径是否为网络路径（Windows）：UNC 共享（\\server\\share）或
    映射到网络共享的驱动器（如 Z:\\，GetDriveTypeW 返回 DRIVE_REMOTE=4）。

    QFileSystemModel 对网络路径的目录缓存不可靠（QFileSystemWatcher 变更
    通知在 SMB 上经常失效），外部程序复制/删除的文件不会自动出现在列表里，
    需要强制重建模型重扫，因此要能识别这类路径。
    """
    if os.name != 'nt':
        return False
    p = p.replace('/', '\\')
    if p.startswith('\\\\'):
        return True
    root = os.path.splitdrive(p)[0]
    if root:
        try:
            import ctypes
            t = ctypes.windll.kernel32.GetDriveTypeW(root + '\\')
            return t == 4  # DRIVE_REMOTE
        except Exception:
            pass
    return False

def _normalize_unc(p: str) -> str:
    """把 UNC 路径规范成普通的 server 共享形式（去掉 send2trash 加的
    长路径前缀、统一反斜杠），供 os.remove / shutil.rmtree 使用。"""
    p = p.replace('/', '\\')
    prefix = '\\\\?\\UNC\\'
    if p.startswith(prefix):
        p = '\\\\' + p[len(prefix):]
    return p


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


class _OperationCancelled(Exception):
    """内部：复制被取消（分段拷贝循环中抛出，由 copy() 统一转为结果）"""
    pass


class FileOperations:
    """文件操作类"""
    
    def __init__(self):
        self._cancelled = False
        self._progress_callback: Optional[Callable[[int, str, int, int], None]] = None
    
    def set_progress_callback(self, callback: Callable[[int, str, int, int], None]):
        """设置进度回调函数(percent, filename, copied_bytes, total_bytes)"""
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
        
        total_files, total_bytes = self._count_files_and_size(sources)
        files_copied = 0
        copied_bytes = 0
        
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
                result = self._copy_single(source, destination, total_files, total_bytes, files_copied, copied_bytes)
                if isinstance(result, FileOperationResult):
                    return result
                files_copied, copied_bytes = result
            except _OperationCancelled:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.COPY,
                    source=source,
                    destination=destination,
                    error="操作已取消",
                    files_affected=files_copied
                )
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

    def _copy_single(self, source: str, destination: str, total_files: int, total_bytes: int,
                    current_files: int, current_bytes: int):
        """复制单个文件/目录，返回 (已复制文件数, 已复制字节数)；取消时返回 FileOperationResult"""
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
                        files_affected=current_files
                    )
                
                item_path = os.path.join(source, item)
                if os.path.isdir(item_path):
                    result = self._copy_single(item_path, dest_path, total_files, total_bytes,
                                               current_files, current_bytes)
                    if isinstance(result, FileOperationResult):
                        return result
                    current_files, current_bytes = result
                else:
                    copied = self._copy_file_with_progress(
                        item_path, os.path.join(dest_path, item),
                        total_bytes, current_files, current_bytes)
                    current_files += 1
                    current_bytes += copied
                    self._report_progress(current_files, total_files, item, current_bytes, total_bytes)
        else:
            # 复制文件（字节级进度）
            copied = self._copy_file_with_progress(
                source, dest_path, total_bytes, current_files, current_bytes)
            current_files += 1
            current_bytes += copied
            self._report_progress(current_files, total_files, source_name, current_bytes, total_bytes)
        
        return current_files, current_bytes
    
    def _copy_file_with_progress(self, src: str, dst: str, total_bytes: int,
                                 base_files: int, base_bytes: int) -> int:
        """分段拷贝单个文件并实时报告字节级进度；返回该文件字节数。

        每 1MB 报告一次，大文件（几个 GB）也能看到持续进度；
        支持取消（_cancelled 置位后在下一次分段拷贝前抛出）。
        """
        src_size = os.path.getsize(src)
        copied = 0
        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while True:
                if self._cancelled:
                    raise _OperationCancelled()
                chunk = fsrc.read(1024 * 1024)
                if not chunk:
                    break
                fdst.write(chunk)
                copied += len(chunk)
                done_bytes = base_bytes + copied
                self._report_progress(0, 0, os.path.basename(src), done_bytes, total_bytes)
        return copied
    
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
        
        # 移动按源项计数即可（同卷 rename 瞬时完成；对 SMB 大目录递归
        # os.walk 统计会阻塞主线程，且进度粒度与 files_moved 不一致）
        total_files = len(sources)
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
                    if os.name == 'nt' and _is_unc_path(path):
                        # 网络共享没有回收站（资源管理器同样直接删除），且
                        # send2trash 内部生成的 \\?\UNC\... 前缀 Shell API
                        # 不识别，会报 Errno 2 找不到文件。直接永久删除。
                        target = _normalize_unc(path)
                        if os.path.isdir(target):
                            shutil.rmtree(target)
                        else:
                            os.remove(target)
                    elif os.name == 'nt':
                        # send2trash 的 Windows 实现会给路径加 \\?\ 长路径前缀，
                        # 但不会把正斜杠转反斜杠（\\?\C:/x 不被 Win32 识别，报
                        # Errno 2）。Qt 传入的是正斜杠路径，必须先规范化。
                        send2trash.send2trash(os.path.normpath(path))
                    else:
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
    
    def _count_files_and_size(self, paths: list[str]) -> tuple:
        """计算文件总数与总字节数（复制进度按字节显示用）"""
        count = 0
        total = 0
        for path in paths:
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    count += len(files)
                    for f in files:
                        try:
                            total += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
            else:
                count += 1
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
        return count, total
    
    def _report_progress(self, current: int, total: int, filename: str,
                          copied_bytes: int = 0, total_bytes: int = 0):
        """报告进度：有字节统计时按字节（大文件实时），否则按文件数"""
        if not self._progress_callback:
            return
        if total_bytes > 0:
            percent = min(100, int(copied_bytes * 100 / total_bytes))
            self._progress_callback(percent, filename, copied_bytes, total_bytes)
        elif total > 0:
            percent = int(current * 100 / total)
            self._progress_callback(percent, filename, 0, 0)
