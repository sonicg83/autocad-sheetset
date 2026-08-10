import ctypes
from pathlib import Path


class FileLockError(OSError):
    code = "BLOCKED_FILE_LOCK"


class WindowsWriteLocks:
    """允许读取和删除，但拒绝其他进程取得写访问；发布时可原子替换。"""

    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def __init__(self, paths: list[Path]):
        self.paths = sorted({path.resolve() for path in paths}, key=lambda item: str(item).casefold())
        self.handles: list[int] = []

    def __enter__(self):
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        for path in self.paths:
            handle = kernel32.CreateFileW(str(path), self.GENERIC_READ, self.FILE_SHARE_READ | self.FILE_SHARE_DELETE, None, self.OPEN_EXISTING, self.FILE_ATTRIBUTE_NORMAL, None)
            if handle == self.INVALID_HANDLE_VALUE:
                error = ctypes.get_last_error()
                self.__exit__(None, None, None)
                raise FileLockError(error, f"文件被占用，无法取得写阻断锁：{path}")
            self.handles.append(handle)
        return self

    def __exit__(self, *_):
        kernel32 = ctypes.windll.kernel32
        while self.handles:
            kernel32.CloseHandle(self.handles.pop())
