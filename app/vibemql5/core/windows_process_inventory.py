"""Read-only Win32 process observation; unknown never means an idle terminal."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import os

class ProcessObservationUnavailable(RuntimeError):
    def __init__(self):super().__init__('TERMINAL_PROCESS_OBSERVATION_UNAVAILABLE')

class _Entry(C.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),('th32DefaultHeapID',C.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]

def _last_error():return C.get_last_error()

def _api():
    if os.name!='nt':raise ProcessObservationUnavailable()
    k=C.WinDLL('kernel32',use_last_error=True)
    for name,args,result in [('CreateToolhelp32Snapshot',[W.DWORD,W.DWORD],W.HANDLE),('Process32FirstW',[W.HANDLE,C.POINTER(_Entry)],W.BOOL),('Process32NextW',[W.HANDLE,C.POINTER(_Entry)],W.BOOL),('OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE),('QueryFullProcessImageNameW',[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)],W.BOOL),('CloseHandle',[W.HANDLE],W.BOOL)]:
        f=getattr(k,name);f.argtypes=args;f.restype=result
    return k

def terminal_paths():
    """Observe executable paths without PowerShell, WMI, signalling or launch."""
    k=_api();snapshot=k.CreateToolhelp32Snapshot(2,0)
    if snapshot in (None,0,C.c_void_p(-1).value):raise ProcessObservationUnavailable()
    paths=set();entry=_Entry();entry.dwSize=C.sizeof(entry)
    try:
        present=k.Process32FirstW(snapshot,C.byref(entry))
        while present:
            if entry.szExeFile.casefold()=='terminal64.exe':
                handle=k.OpenProcess(0x1000,False,entry.th32ProcessID)
                if not handle:
                    if _last_error()!=87:raise ProcessObservationUnavailable()
                else:
                    try:
                        path=C.create_unicode_buffer(32768);size=W.DWORD(len(path))
                        if not k.QueryFullProcessImageNameW(handle,0,path,C.byref(size)) or not path.value:raise ProcessObservationUnavailable()
                        paths.add(path.value)
                    finally:k.CloseHandle(handle)
            present=k.Process32NextW(snapshot,C.byref(entry))
        if _last_error()!=18:raise ProcessObservationUnavailable()
        return paths
    finally:k.CloseHandle(snapshot)
