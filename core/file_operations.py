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


def describe_removal(paths, permanent: bool = False) -> tuple:
    """删除确认文案 → `(标题, 正文)`（不依赖 Qt：窗格与搜索结果列表共用一份）

    措辞按**实际后果**区分：网络位置（UNC/映射网络盘）没有回收站，删除即
    永久删除不可恢复，不能仍写“到回收站”误导用户；`permanent=True`
    （Shift+Delete）时本地也直接永久删除。正文列出前 5 个名字，多了只报条数。
    """
    paths = list(paths)
    count = len(paths)
    if permanent:
        title = "确认永久删除"
        verb = f"确定要永久删除 {count} 个项目吗？此操作不可恢复！"
    elif os.name == 'nt':
        net_count = sum(1 for p in paths if _is_network_path(p))
        local_count = count - net_count
        parts = []
        if net_count:
            parts.append(f"网络位置的 {net_count} 个项目将被永久删除、无法恢复（网络位置没有回收站）")
        if local_count:
            parts.append(f"本地的 {local_count} 个项目将移到回收站")
        title = "确认删除"
        verb = '，；'.join(parts) + "。"
    else:
        title = "确认删除"
        verb = f"确定要删除 {count} 个项目吗？"
    names = '\n'.join(os.path.basename(p) or p for p in paths[:5])
    if count > 5:
        names += f"\n… 等共 {count} 项"
    return title, f"{verb}\n\n{names}"


def move_target_inside_sources(sources, target_dir: str) -> bool:
    """移动目标是否位于任一源目录内部（或就是源本身）

    把目录移到它自己的子目录里会让 shutil 递归复制下去卡死，所以调用方
    （窗格拖放、搜索结果列表的「移动到…」）都先问这一句。抽到这里是因为
    两个入口必须给同一个答案。
    """
    t = os.path.normpath(target_dir)
    for f in sources:
        if not os.path.isdir(f):
            continue
        s = os.path.normpath(f)
        if t == s:
            return True
        if t.startswith(s + os.sep) or t.startswith(s + "/"):
            return True
    return False


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
        # 同名冲突询问回调：fn(info) -> 'replace'/'skip'/'keep_both'/'cancel'
        # info = {src, dst, src_size, src_mtime, dst_size, dst_mtime, is_dir}
        # None 时保持旧行为（自动改名“保留两者”），供无 UI 的调用方/测试使用
        self._conflict_callback: Optional[Callable[[dict], str]] = None
    
    def set_progress_callback(self, callback: Callable[[int, str, int, int], None]):
        """设置进度回调函数(percent, filename, copied_bytes, total_bytes)"""
        self._progress_callback = callback
    
    def set_conflict_callback(self, callback: Optional[Callable[[dict], str]]):
        """设置同名冲突处理回调（在后台操作线程被调用，UI 层需自行回主线程）"""
        self._conflict_callback = callback
    
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
        
        try:
            total_files, total_bytes = self._count_files_and_size(sources)
        except _OperationCancelled:
            return FileOperationResult(
                success=False,
                operation=FileOperationType.COPY,
                source=str(sources),
                destination=destination,
                error="操作已取消",
                files_affected=0
            )
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

    def _count_files_and_size(self, paths: list[str]) -> tuple:
        """计算文件总数与总字节数（复制进度按字节显示用）；可被取消中断。

        SMB 大目录上 os.walk 要遍历数分钟且期间无任何反馈，这里每层目录
        检查一次取消标志，用户点取消后秒级退出而非等统计跑完。
        """
        count = 0
        total = 0
        for path in paths:
            if self._cancelled:
                raise _OperationCancelled()
            if os.path.islink(path):
                count += 1
                continue
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    if self._cancelled:
                        raise _OperationCancelled()
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
    
    @staticmethod
    def _is_reparse_dir(path: str) -> bool:
        """目录是否为符号链接/junction/其它重分析点（调用方须先确认是目录）。

        非 Windows 直接看 islink；Windows 上 os.walk 对 junction 不报 islink，
        用 FILE_ATTRIBUTE_REPARSE_POINT 兼顾 symlink 与 junction。
        递归时跳过它们的子树（与 Explorer 复制行为一致），避免成环死循环。
        """
        try:
            if os.name != 'nt':
                return os.path.islink(path)
            import ctypes
            FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            st = ctypes.windll.kernel32.GetFileAttributesW(os.path.normpath(path))
            return st != -1 and bool(st & FILE_ATTRIBUTE_REPARSE_POINT)
        except Exception:
            return False

    def _resolve_conflict(self, src: str, dst: str) -> str:
        """目标已存在时的处理：返回 'replace'/'skip'/'keep_both'。

        旧行为一律静默改名 (2)；现在若设了冲突回调（UI 弹框询问）按其决策，
        无回调/异常时回退旧行为，不改变无 UI 调用方的语义。
        """
        if self._conflict_callback is None:
            return 'keep_both'
        try:
            is_dir = os.path.isdir(src)
            info = {
                'src': src, 'dst': dst, 'is_dir': is_dir,
                'src_size': 0 if is_dir else os.path.getsize(src),
                'src_mtime': os.path.getmtime(src),
                'dst_size': 0 if os.path.isdir(dst) else (os.path.getsize(dst) if os.path.isfile(dst) else 0),
                'dst_mtime': os.path.getmtime(dst),
            }
            decision = self._conflict_callback(info)
            if decision in ('replace', 'skip', 'keep_both', 'cancel'):
                return decision
        except _OperationCancelled:
            raise
        except Exception:
            pass
        return 'keep_both'

    def _copy_single(self, source: str, destination: str, total_files: int, total_bytes: int,
                    current_files: int, current_bytes: int):
        """复制单个文件/目录，返回 (已复制文件数, 已复制字节数)；取消时返回 FileOperationResult"""
        source_name = os.path.basename(source)
        
        # 符号链接本身复制（与 Explorer 一致），不解引用目标内容
        if os.path.islink(source):
            dest_link = self._unique_dest_path(destination, source_name)
            if os.path.exists(dest_link):
                return current_files, current_bytes
            try:
                os.symlink(os.readlink(source), dest_link,
                           target_is_directory=os.path.isdir(source))
            except (OSError, NotImplementedError):
                # Windows 无创建符号链接权限（需开发者模式/管理员）：
                # 退回复制链接目标内容，不阻断整个操作
                pass
            else:
                return current_files + 1, current_bytes
        
        dest_path = os.path.join(destination, source_name)
        action = 'keep_both'
        if os.path.exists(dest_path):
            action = self._resolve_conflict(source, dest_path)
            if action == 'skip':
                return current_files, current_bytes
            if action == 'cancel':
                raise _OperationCancelled()
            if action == 'keep_both':
                dest_path = self._unique_dest_path(destination, source_name)
        
        if os.path.isdir(source):
            # 复制目录：os.walk 扁平递归（避免深层递归栈风险），
            # 先建子目录结构（跳过 symlink/junction 子树）再逐文件复制
            if action == 'replace' and os.path.isdir(dest_path):
                # 替换：不删整个目标目录（Explorer 语义也是合并覆盖），
                # makedirs(exist_ok) 后同名文件逐个覆盖
                pass
            for root, dirnames, filenames in os.walk(source, topdown=True):
                if self._cancelled:
                    return FileOperationResult(
                        success=False,
                        operation=FileOperationType.COPY,
                        source=source,
                        destination=destination,
                        error="操作已取消",
                        files_affected=current_files
                    )
                # 就地过滤，阻止进入链接目录（防环）
                kept = []
                for d in dirnames:
                    full = os.path.join(root, d)
                    if self._is_reparse_dir(full) and not os.path.islink(full):
                        # junction/symlink 目录：在目标建同名链接不可靠，
                        # 与 Explorer 一致直接跳过子树（空目录也不建）
                        continue
                    kept.append(d)
                dirnames[:] = kept
                
                rel = os.path.relpath(root, source)
                dst_root = dest_path if rel == '.' else os.path.join(dest_path, rel)
                os.makedirs(dst_root, exist_ok=True)
                for name in filenames:
                    if self._cancelled:
                        return FileOperationResult(
                            success=False,
                            operation=FileOperationType.COPY,
                            source=source,
                            destination=destination,
                            error="操作已取消",
                            files_affected=current_files
                        )
                    item_path = os.path.join(root, name)
                    dst_item = os.path.join(dst_root, name)
                    if os.path.islink(item_path):
                        try:
                            if os.path.lexists(dst_item):
                                os.remove(dst_item)
                            os.symlink(os.readlink(item_path), dst_item,
                                       target_is_directory=os.path.isdir(item_path))
                            current_files += 1
                            continue
                        except (OSError, NotImplementedError):
                            pass  # 无权限时退回复制内容
                    if os.path.isdir(item_path):
                        continue  # 由下一层 walk 处理
                    copied = self._copy_file_with_progress(
                        item_path, dst_item,
                        total_bytes, current_files, current_bytes)
                    current_files += 1
                    current_bytes += copied
                    self._report_progress(current_files, total_files, name, current_bytes, total_bytes)
            # 目录属性（mtime/只读等）最后统一保留
            try:
                shutil.copystat(source, dest_path, follow_symlinks=False)
            except OSError:
                pass
        else:
            # 复制文件（字节级进度 + 元数据保留）；replace 时先移除已存在目标
            if os.path.lexists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            copied = self._copy_file_with_progress(
                source, dest_path, total_bytes, current_files, current_bytes)
            current_files += 1
            current_bytes += copied
            self._report_progress(current_files, total_files, source_name, current_bytes, total_bytes)
        
        return current_files, current_bytes
    
    def _copy_tree_into(self, source: str, dst_root: str, total_files: int, total_bytes: int,
                        base_files: int, base_bytes: int):
        """把 source 目录树复制到已确定的目标路径（不再过 _unique_dest_path 改名），
        返回 (files, bytes)。跨卷移动用：复用同一套分块复制 + copystat + 取消逻辑。"""
        for root, dirnames, filenames in os.walk(source, topdown=True):
            if self._cancelled:
                raise _OperationCancelled()
            dirnames[:] = [d for d in dirnames
                           if not (self._is_reparse_dir(os.path.join(root, d))
                                   and not os.path.islink(os.path.join(root, d)))]
            rel = os.path.relpath(root, source)
            dst_dir = dst_root if rel == '.' else os.path.join(dst_root, rel)
            os.makedirs(dst_dir, exist_ok=True)
            for name in filenames:
                if self._cancelled:
                    raise _OperationCancelled()
                item = os.path.join(root, name)
                dst_item = os.path.join(dst_dir, name)
                if os.path.islink(item):
                    try:
                        if os.path.lexists(dst_item):
                            os.remove(dst_item)
                        os.symlink(os.readlink(item), dst_item,
                                   target_is_directory=os.path.isdir(item))
                        base_files += 1
                        continue
                    except (OSError, NotImplementedError):
                        pass  # 无符号链接权限：退回复制内容
                if os.path.isdir(item):
                    continue
                copied = self._copy_file_with_progress(item, dst_item, total_bytes,
                                                       base_files, base_bytes)
                base_files += 1
                base_bytes += copied
                self._report_progress(base_files, total_files, name, base_bytes, total_bytes)
        try:
            shutil.copystat(source, dst_root, follow_symlinks=False)
        except OSError:
            pass
        return base_files, base_bytes

    def _delete_tree(self, source: str):
        """删除源树（跨卷移动的第二阶段）：链接/重分析点只删自身不进入。"""
        if os.path.islink(source) or (os.path.isdir(source) and self._is_reparse_dir(source)):
            os.remove(source)
            return
        for root, dirnames, filenames in os.walk(source, topdown=False):
            for name in filenames:
                p = os.path.join(root, name)
                try:
                    os.remove(p)
                except OSError:
                    pass
            for name in dirnames:
                p = os.path.join(root, name)
                try:
                    if os.path.islink(p) or self._is_reparse_dir(p):
                        os.remove(p)
                    else:
                        os.rmdir(p)
                except OSError:
                    pass
        os.rmdir(source)

    def _copy_file_with_progress(self, src: str, dst: str, total_bytes: int,
                                 base_files: int, base_bytes: int) -> int:
        """分段拷贝单个文件并实时报告字节级进度；返回该文件字节数。

        每 1MB 报告一次，大文件（几个 GB）也能看到持续进度；
        支持取消（_cancelled 置位后在下一次分段拷贝前抛出）；
        完成后 copystat 保留时间戳/只读等元数据（资源管理器同样保留；
        旧实现手写分块不落元数据，复制后修改时间变成“现在”）。
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
        try:
            shutil.copystat(src, dst, follow_symlinks=True)
        except OSError:
            pass  # 跨文件系统/权限受限时元数据写入失败不影响内容已复制的事实
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
                # 同名冲突：旧实现直接 shutil.move，目标已有同名目录时被静默
                # 合并（Explorer 会询问）；现在走统一的冲突决策
                name = os.path.basename(os.path.normpath(source))
                dest_path = os.path.join(destination, name)
                same_dir = os.path.normpath(os.path.dirname(os.path.abspath(source))) == \
                    os.path.normpath(os.path.abspath(destination))
                if not same_dir and os.path.lexists(dest_path):
                    action = self._resolve_conflict(source, dest_path)
                    if action == 'skip':
                        continue
                    if action == 'cancel':
                        raise _OperationCancelled()
                    if action == 'keep_both':
                        dest_path = self._unique_dest_path(destination, name)
                    elif os.path.isdir(dest_path):
                        shutil.rmtree(dest_path)
                    else:
                        os.remove(dest_path)
                if same_dir:
                    # 同目录移动：重命名语义，目标名等于源时直接跳过
                    # （旧实现把目录本身传给 shutil.move 会报
                    # SpecialFileError/DestinationHasSameName，粘贴到自己所在目录即失败）
                    if os.path.normpath(dest_path) == os.path.normpath(source):
                        continue
                    if os.path.lexists(dest_path):
                        action = self._resolve_conflict(source, dest_path)
                        if action == 'skip':
                            continue
                        if action == 'cancel':
                            raise _OperationCancelled()
                        if action == 'keep_both':
                            dest_path = self._unique_dest_path(destination, name)
                        elif os.path.isdir(dest_path):
                            shutil.rmtree(dest_path)
                        else:
                            os.remove(dest_path)
                # 跨卷移动（如本地→SMB 映射盘）：shutil.move 内部复制不落
                # 元数据、无字节进度；改为组合 copy（复用冲突处理/copystat/
                # 字节进度/取消）+ 删源，与 Explorer 跨盘移动行为一致
                try:
                    cross_volume = os.stat(os.path.dirname(os.path.abspath(source))).st_dev != \
                        os.stat(destination).st_dev
                except OSError:
                    cross_volume = False
                if cross_volume:
                    tmp_ops = FileOperations()
                    tmp_ops._cancelled = False
                    tmp_ops._progress_callback = self._progress_callback
                    tmp_ops._conflict_callback = self._conflict_callback
                    cp = tmp_ops.copy([source], destination)
                    if tmp_ops._cancelled:
                        self._cancelled = True
                    if not cp.success:
                        return FileOperationResult(
                            success=False,
                            operation=FileOperationType.MOVE,
                            source=source,
                            destination=destination,
                            error=cp.error,
                            files_affected=files_moved
                        )
                    # 删源：链接/重分析点只删自身，不能 rmtree 进入目标
                    if os.path.islink(source):
                        os.remove(source)
                    elif os.path.isdir(source) and self._is_reparse_dir(source):
                        os.rmdir(source)
                    elif os.path.isdir(source):
                        shutil.rmtree(source)
                    else:
                        os.remove(source)
                else:
                    shutil.move(source, dest_path)
                files_moved += 1
                self._report_progress(files_moved, total_files, os.path.basename(source))
            except _OperationCancelled:
                return FileOperationResult(
                    success=False,
                    operation=FileOperationType.MOVE,
                    source=source,
                    destination=destination,
                    error="操作已取消",
                    files_affected=files_moved
                )
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
        permanent_fallbacks = 0  # 本想进回收站但实际被永久删除的项数
        
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
                        try:
                            send2trash.send2trash(os.path.normpath(path))
                        except OSError:
                            # 映射网络驱动器（Z:\ 等）同样没有回收站，
                            # send2trash 会抛异常；与资源管理器行为一致回退为
                            # 永久删除，并在结果中标记供 UI 提示
                            if _is_network_path(path):
                                if os.path.isdir(path):
                                    shutil.rmtree(path)
                                else:
                                    os.remove(path)
                                permanent_fallbacks += 1
                            else:
                                raise
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
            files_affected=files_deleted,
            error=(f"{permanent_fallbacks} 个项目位于网络位置，已永久删除（无法恢复）"
                   if permanent_fallbacks else "")
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
