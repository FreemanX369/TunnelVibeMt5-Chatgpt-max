from __future__ import annotations
import ctypes, os, shutil
from pathlib import Path
from ..config import load_settings, default_root

class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

def memory_info() -> tuple[int, int]:
    if os.name == "nt":
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys), int(stat.ullAvailPhys)
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page
        avail = os.sysconf("SC_AVPHYS_PAGES") * page
        return int(total), int(avail)
    except (ValueError, OSError, AttributeError):
        return 0, 0

class ResourceGuard:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.settings = load_settings(self.root)["resource_guard"]

    def status(self) -> dict:
        usage = shutil.disk_usage(self.root)
        total_mem, free_mem = memory_info()
        free_gb = usage.free / (1024**3)
        warn = float(self.settings.get("disk_warning_gb", 4))
        block = float(self.settings.get("disk_block_gb", 2))
        min_mem = int(self.settings.get("min_free_memory_mb", 256))
        free_mem_mb = free_mem / (1024**2) if free_mem else None
        if free_gb < block or (free_mem_mb is not None and free_mem_mb < min_mem):
            state = "BLOCKED"
        elif free_gb < warn:
            state = "WARNING"
        else:
            state = "READY"
        return {
            "state": state,
            "disk_free_gb": round(free_gb, 2),
            "memory_total_mb": round(total_mem/(1024**2), 1) if total_mem else None,
            "memory_free_mb": round(free_mem_mb, 1) if free_mem_mb is not None else None,
            "disk_warning_gb": warn,
            "disk_block_gb": block,
            "min_free_memory_mb": min_mem,
        }
