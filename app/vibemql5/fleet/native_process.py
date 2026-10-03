"""Exact Windows owned process lifecycle for qualified dedicated tester work.

No terminal/SDK is started by import. This factory is reachable only through the
installed operator qualification gate; legacy drivers keep their original launch.
"""
from __future__ import annotations

import ctypes as C
import os
import subprocess
import time
from .identity import normalize_path
from pathlib import Path
from ..core.native_ownership import ObservedProcess, OwnershipBlocked


class OwnedWindowsLaunch:
    def __init__(self, authority, armed, revalidate, on_bound=None, should_cancel=None, complete=None, require_current=None):
        if os.name != "nt":
            raise OwnershipBlocked("WINDOWS_NATIVE_BOUNDARY_UNAVAILABLE")
        from ctypes import wintypes as W
        self.W, self.authority, self.expected, self.revalidate = W, authority, armed, revalidate
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.complete = complete
        self.require_current = require_current
        self.on_bound = on_bound
        self.should_cancel, self.cancelled = should_cancel, False
        self.process, self.observed, self.job, self.thread = None, None, None, None
        self._configure()

    def _configure(self):
        W, k = self.W, self.kernel
        class Basic(C.Structure):
            _fields_ = [("PerProcessUserTimeLimit", C.c_longlong), ("PerJobUserTimeLimit", C.c_longlong),
                ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", C.c_size_t), ("MaximumWorkingSetSize", C.c_size_t),
                ("ActiveProcessLimit", W.DWORD), ("Affinity", C.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]
        class IO(C.Structure):
            _fields_ = [(name, C.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(C.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO), ("ProcessMemoryLimit", C.c_size_t),
                ("JobMemoryLimit", C.c_size_t), ("PeakProcessMemoryUsed", C.c_size_t), ("PeakJobMemoryUsed", C.c_size_t)]
        class Accounting(C.Structure):
            _fields_ = [(name, C.c_longlong) for name in ("TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")] + [
                (name, W.DWORD) for name in ("TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]
        class Startup(C.Structure):
            _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR), ("lpTitle", W.LPWSTR)] + [
                (name, W.DWORD) for name in ("dwX", "dwY", "dwXSize", "dwYSize", "dwXCountChars", "dwYCountChars", "dwFillAttribute", "dwFlags")] + [
                ("wShowWindow", W.WORD), ("cbReserved2", W.WORD), ("lpReserved2", C.c_void_p),
                ("hStdInput", W.HANDLE), ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]
        class ProcessInfo(C.Structure):
            _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]
        self.Extended, self.Accounting, self.Startup, self.ProcessInfo = Extended, Accounting, Startup, ProcessInfo
        specs = [("CreateJobObjectW", [C.c_void_p, W.LPCWSTR], W.HANDLE),
            ("SetInformationJobObject", [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            ("QueryInformationJobObject", [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            ("AssignProcessToJobObject", [W.HANDLE, W.HANDLE], W.BOOL),
            ("CreateProcessW", [W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL, W.DWORD,
                                C.c_void_p, W.LPCWSTR, C.POINTER(Startup), C.POINTER(ProcessInfo)], W.BOOL),
            ("ResumeThread", [W.HANDLE], W.DWORD), ("TerminateJobObject", [W.HANDLE, W.UINT], W.BOOL),
            ("TerminateProcess", [W.HANDLE, W.UINT], W.BOOL), ("CloseHandle", [W.HANDLE], W.BOOL),
            ("WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
            ("GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL)]
        for name, arguments, result in specs:
            fn = getattr(k, name); fn.argtypes, fn.restype = arguments, result

    def __call__(self, command, *, cwd, **_kwargs):
        if self.process is not None or self.expected["phase"] != "ARMED":
            raise OwnershipBlocked("NATIVE_CREATE_RETRY_FORBIDDEN")
        k, W = self.kernel, self.W
        self.job = k.CreateJobObjectW(None, None)
        if not self.job: raise OwnershipBlocked("NATIVE_JOB_CREATE_FAILED")
        limits = self.Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE; neither breakaway flag is set.
        if not k.SetInformationJobObject(self.job, 9, C.byref(limits), C.sizeof(limits)):
            raise OwnershipBlocked("NATIVE_JOB_LIMITS_UNPROVEN")
        observed_limits = self.Extended()
        if not k.QueryInformationJobObject(self.job, 9, C.byref(observed_limits), C.sizeof(observed_limits), None) or observed_limits.BasicLimitInformation.LimitFlags != 0x2000:
            raise OwnershipBlocked("NATIVE_JOB_LIMITS_UNPROVEN")
        self.revalidate("process_create")
        startup, info = self.Startup(), self.ProcessInfo()
        startup.cb = C.sizeof(startup)
        self.expected = self.authority.create_attempt(self.expected)  # Durable before CreateProcess.
        text = C.create_unicode_buffer(subprocess.list2cmdline(command))
        if self.require_current: self.require_current("process_create")
        if not k.CreateProcessW(str(Path(command[0]).resolve()), text, None, None, False, 0x4,
                                None, str(cwd), C.byref(startup), C.byref(info)):
            raise OwnershipBlocked("NATIVE_CREATE_OUTCOME_UNCERTAIN")
        self.process, self.thread, self.pid, self.args = info.hProcess, info.hThread, int(info.dwProcessId), list(command)
        if not k.AssignProcessToJobObject(self.job, self.process):
            k.TerminateProcess(self.process, 1)
            raise OwnershipBlocked("NATIVE_JOB_ASSIGN_UNPROVEN")
        self.observed = ObservedProcess(self.pid)
        if normalize_path(self.observed.identity()["image"]) != normalize_path(str(Path(command[0]).resolve())):
            raise OwnershipBlocked("NATIVE_IMAGE_MISMATCH")
        self.expected = self.authority.bind_worker(self.expected, self.observed)
        if self.on_bound: self.on_bound(self.observed.identity())
        if self.complete: self.complete("process_create")
        self.revalidate("process_resume")
        if k.ResumeThread(self.thread) != 1:
            raise OwnershipBlocked("NATIVE_RESUME_UNCERTAIN")
        k.CloseHandle(self.thread); self.thread = None
        if self.complete: self.complete("process_resume")
        return self

    @property
    def returncode(self):
        return self.poll()

    def poll(self):
        if self.process is None: return None
        wait = self.kernel.WaitForSingleObject(self.process, 0)
        if wait == 258: return None
        if wait != 0: raise OwnershipBlocked("EXACT_WORKER_EXIT_UNPROVEN")
        code = self.W.DWORD()
        if not self.kernel.GetExitCodeProcess(self.process, C.byref(code)):
            raise OwnershipBlocked("EXACT_WORKER_EXIT_UNPROVEN")
        return int(code.value)

    def wait(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + max(0, timeout)
        while True:
            code = self.poll()
            if code is not None: return code
            if self.should_cancel is not None and not self.cancelled and self.should_cancel():
                self.revalidate("owned_terminate")
                self.terminate()
                if self.complete: self.complete("owned_terminate")
                self.cancelled = True
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            if remaining == 0: raise subprocess.TimeoutExpired(self.args, timeout)
            milliseconds = (0xFFFFFFFF if remaining is None else min(0xFFFFFFFE, int(remaining * 1000))) if self.should_cancel is None else min(100, 100 if remaining is None else int(remaining * 1000))
            wait = self.kernel.WaitForSingleObject(self.process, milliseconds)
            if wait == 0: return self.poll()
            if wait != 258: raise OwnershipBlocked("EXACT_WORKER_EXIT_UNPROVEN")

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.job, 1):
            raise OwnershipBlocked("EXACT_JOB_TERMINATION_UNPROVEN")

    kill = terminate

    def _descendants(self, process):
        if process is not self.observed or self.job is None:
            raise OwnershipBlocked("DESCENDANTS_UNPROVEN")
        active = self.Accounting()
        if not self.kernel.QueryInformationJobObject(self.job, 1, C.byref(active), C.sizeof(active), None):
            raise OwnershipBlocked("DESCENDANTS_UNPROVEN")
        if active.ActiveProcesses != 0:
            raise OwnershipBlocked("DESCENDANTS_UNPROVEN")
        return "EXACT_DESCENDANTS_EXITED"

    def finish(self):
        # Close only after a retained same-process handle and held Job Object prove exit.
        if self.process is None:
            if self.expected["phase"] == "ARMED":
                return self.authority.close_zero_attempt(self.expected)
            raise OwnershipBlocked("NATIVE_CREATE_OUTCOME_UNCERTAIN")
        if self.poll() is None:
            raise OwnershipBlocked("EXACT_WORKER_EXIT_UNPROVEN")
        # Never terminate because authorization expired. Normal driver cancellation
        # owns the exact Job handle and needs a fresh signed cancel authorization.
        return self.authority.close_owned_worker(self.expected, self.observed, descendant_verifier=self._descendants)

    def close_handles(self):
        if self.observed is not None: self.observed.close(); self.observed = None
        for attr in ("thread", "process", "job"):
            handle = getattr(self, attr, None)
            if handle is not None:
                self.kernel.CloseHandle(handle); setattr(self, attr, None)


def assert_installation_idle(executable, metaeditor, *, owned_identity=None):
    """Read-only exact-image census; only the adapter's retained worker is allowed."""
    if os.name != "nt": raise OwnershipBlocked("WINDOWS_NATIVE_BOUNDARY_UNAVAILABLE")
    from ctypes import wintypes as W
    class Entry(C.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
            ("th32DefaultHeapID", C.c_size_t), ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
            ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260)]
    k = C.WinDLL("kernel32", use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes, k.CreateToolhelp32Snapshot.restype = [W.DWORD, W.DWORD], W.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        getattr(k, name).argtypes, getattr(k, name).restype = [W.HANDLE, C.POINTER(Entry)], W.BOOL
    k.CloseHandle.argtypes, k.CloseHandle.restype = [W.HANDLE], W.BOOL
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == C.c_void_p(-1).value or not snapshot: raise OwnershipBlocked("NATIVE_IDLE_UNPROVEN")
    expected = {normalize_path(executable), normalize_path(metaeditor)}
    names = {Path(value).name.casefold() for value in expected}
    entry = Entry(); entry.dwSize = C.sizeof(entry)
    try:
        ok = k.Process32FirstW(snapshot, C.byref(entry))
        if not ok: raise OwnershipBlocked("NATIVE_IDLE_UNPROVEN")
        while ok:
            if entry.szExeFile.casefold() in names:
                observed = ObservedProcess(int(entry.th32ProcessID))
                try:
                    identity = observed.identity()
                    if normalize_path(identity["image"]) in expected and identity != owned_identity:
                        raise OwnershipBlocked("NATIVE_INSTALLATION_BUSY")
                finally: observed.close()
            ok = k.Process32NextW(snapshot, C.byref(entry))
        if C.get_last_error() != 18: raise OwnershipBlocked("NATIVE_IDLE_UNPROVEN")
    finally: k.CloseHandle(snapshot)
