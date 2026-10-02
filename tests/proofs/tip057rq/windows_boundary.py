"""Minimal AppContainer launcher for the harmless Q1 fixture, not a runtime sandbox."""
from __future__ import annotations

import ctypes as C
import os
import subprocess
import time
import uuid
from ctypes import wintypes as W
from pathlib import Path

P = C.c_void_p
SIZE = C.c_size_t


class STARTUPINFO(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR),
                ("title", W.LPWSTR), ("x", W.DWORD), ("y", W.DWORD),
                ("xsize", W.DWORD), ("ysize", W.DWORD), ("xchars", W.DWORD),
                ("ychars", W.DWORD), ("fill", W.DWORD), ("flags", W.DWORD),
                ("show", W.WORD), ("reserved_count", W.WORD), ("reserved_bytes", P),
                ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class STARTUPINFOEX(C.Structure):
    _fields_ = [("startup", STARTUPINFO), ("attributes", P)]


class PROCESS_INFORMATION(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE),
                ("pid", W.DWORD), ("tid", W.DWORD)]


class SECURITY_CAPABILITIES(C.Structure):
    _fields_ = [("sid", P), ("capabilities", P), ("count", W.DWORD), ("reserved", W.DWORD)]


def require(value):
    if not value:
        raise C.WinError(C.get_last_error())
    return value


class Windows:
    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("REAL_WINDOWS_REQUIRED")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.advapi = C.WinDLL("advapi32", use_last_error=True)
        self.userenv = C.WinDLL("userenv", use_last_error=True)
        specs = [
            (self.kernel, "CloseHandle", [W.HANDLE], W.BOOL),
            (self.kernel, "GetCurrentProcess", [], W.HANDLE),
            (self.kernel, "GetProcessId", [W.HANDLE], W.DWORD),
            (self.kernel, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            (self.kernel, "GetProcessTimes", [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4, W.BOOL),
            (self.kernel, "QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            (self.kernel, "WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD),
            (self.kernel, "TerminateProcess", [W.HANDLE, W.UINT], W.BOOL),
            (self.kernel, "GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
            (self.kernel, "ResumeThread", [W.HANDLE], W.DWORD),
            (self.kernel, "SetHandleInformation", [W.HANDLE, W.DWORD, W.DWORD], W.BOOL),
            (self.kernel, "InitializeProcThreadAttributeList", [P, W.DWORD, W.DWORD, C.POINTER(SIZE)], W.BOOL),
            (self.kernel, "UpdateProcThreadAttribute", [P, W.DWORD, SIZE, P, SIZE, P, P], W.BOOL),
            (self.kernel, "DeleteProcThreadAttributeList", [P], None),
            (self.kernel, "CreateProcessW", [W.LPCWSTR, W.LPWSTR, P, P, W.BOOL, W.DWORD, P, W.LPCWSTR, P, C.POINTER(PROCESS_INFORMATION)], W.BOOL),
            (self.kernel, "LocalFree", [P], P),
            (self.advapi, "OpenProcessToken", [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], W.BOOL),
            (self.advapi, "GetTokenInformation", [W.HANDLE, C.c_int, P, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            (self.advapi, "ConvertSidToStringSidW", [P, C.POINTER(W.LPWSTR)], W.BOOL),
            (self.advapi, "FreeSid", [P], P),
            (self.advapi, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [W.LPCWSTR, W.DWORD, C.POINTER(P), P], W.BOOL),
            (self.advapi, "GetSecurityDescriptorDacl", [P, C.POINTER(W.BOOL), C.POINTER(P), C.POINTER(W.BOOL)], W.BOOL),
            (self.advapi, "GetSecurityDescriptorSacl", [P, C.POINTER(W.BOOL), C.POINTER(P), C.POINTER(W.BOOL)], W.BOOL),
            (self.advapi, "SetNamedSecurityInfoW", [W.LPWSTR, C.c_int, W.DWORD, P, P, P, P], W.DWORD),
            (self.userenv, "CreateAppContainerProfile", [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, P, W.DWORD, C.POINTER(P)], C.c_long),
            (self.userenv, "DeleteAppContainerProfile", [W.LPCWSTR], C.c_long),
        ]
        for dll, name, arguments, result in specs:
            function = getattr(dll, name)
            function.argtypes, function.restype = arguments, result

    def sid_string(self, sid):
        text = W.LPWSTR()
        require(self.advapi.ConvertSidToStringSidW(sid, C.byref(text)))
        try:
            return text.value
        finally:
            self.kernel.LocalFree(C.cast(text, P))

    def user_sid(self):
        token = W.HANDLE()
        require(self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x8, C.byref(token)))
        try:
            size = W.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, C.byref(size))
            buffer = C.create_string_buffer(size.value)
            require(self.advapi.GetTokenInformation(token, 1, buffer, size, C.byref(size)))
            return self.sid_string(C.cast(buffer, C.POINTER(P))[0])
        finally:
            self.kernel.CloseHandle(token)

    def privileged_inheritable_parent(self):
        handle = require(self.kernel.OpenProcess(0x80 | 0x20 | 0x1000, True, os.getpid()))
        try:
            require(self.kernel.SetHandleInformation(handle, 1, 1))
            return handle
        except BaseException:
            self.kernel.CloseHandle(handle)
            raise


class Process:
    def __init__(self, windows, process, thread=None):
        self.windows, self.handle, self.thread = windows, process, thread

    def identity(self):
        times = [W.FILETIME() for _ in range(4)]
        require(self.windows.kernel.GetProcessTimes(self.handle, *(C.byref(t) for t in times)))
        image = C.create_unicode_buffer(32768)
        length = W.DWORD(len(image))
        require(self.windows.kernel.QueryFullProcessImageNameW(self.handle, 0, image, C.byref(length)))
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return {"pid": int(require(self.windows.kernel.GetProcessId(self.handle))),
                "creation_100ns": created, "image": os.path.normcase(image.value)}

    def resume(self):
        if self.windows.kernel.ResumeThread(self.thread) == 0xFFFFFFFF:
            raise C.WinError(C.get_last_error())

    def exited(self):
        wait = self.windows.kernel.WaitForSingleObject(self.handle, 0)
        if wait == 0xFFFFFFFF:
            raise C.WinError(C.get_last_error())
        return wait == 0

    def wait(self, milliseconds=5000):
        wait = self.windows.kernel.WaitForSingleObject(self.handle, milliseconds)
        if wait != 0:
            raise RuntimeError(f"FIXTURE_WAIT_NOT_PROVEN:{wait}")
        code = W.DWORD()
        require(self.windows.kernel.GetExitCodeProcess(self.handle, C.byref(code)))
        return code.value

    def terminate_exact(self, expected):
        if self.identity() != expected:
            raise RuntimeError("EXACT_PROCESS_IDENTITY_MISMATCH")
        started = time.monotonic()
        if not self.exited():
            require(self.windows.kernel.TerminateProcess(self.handle, 92))
        self.wait()
        assert self.exited() and self.identity() == expected
        return (time.monotonic() - started) * 1000

    def close(self):
        if self.thread:
            require(self.windows.kernel.CloseHandle(self.thread))
            self.thread = None
        if self.handle:
            require(self.windows.kernel.CloseHandle(self.handle))
            self.handle = None

    @classmethod
    def open_expected(cls, windows, expected):
        handle = require(windows.kernel.OpenProcess(0x1000 | 0x100000 | 1, False, expected["pid"]))
        process = cls(windows, handle)
        try:
            if process.identity() != expected:
                raise RuntimeError("EXACT_PROCESS_IDENTITY_MISMATCH")
            return process
        except BaseException:
            process.close()
            raise


class Boundary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.windows = Windows()
        self.name = "tip057rq." + uuid.uuid4().hex
        self.sid = P()
        result = self.windows.userenv.CreateAppContainerProfile(
            self.name, self.name, "Isolated harmless Q1 fixture", None, 0, C.byref(self.sid))
        if result < 0:
            raise RuntimeError(f"APP_CONTAINER_SETUP_FAILED:0x{result & 0xFFFFFFFF:08x}")
        try:
            self._grant_fixture_root()
        except BaseException:
            self.close()
            raise

    def _grant_fixture_root(self):
        user = self.windows.user_sid()
        app = self.windows.sid_string(self.sid)
        sddl = f"D:(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;0x1201bf;;;{app})S:(ML;OICI;NW;;;LW)"
        descriptor = P()
        require(self.windows.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, C.byref(descriptor), None))
        try:
            dacl, sacl = P(), P()
            present, defaulted = W.BOOL(), W.BOOL()
            require(self.windows.advapi.GetSecurityDescriptorDacl(descriptor, C.byref(present), C.byref(dacl), C.byref(defaulted)))
            require(self.windows.advapi.GetSecurityDescriptorSacl(descriptor, C.byref(present), C.byref(sacl), C.byref(defaulted)))
            # Only the unique temporary fixture root is modified; never the checkout/system.
            result = self.windows.advapi.SetNamedSecurityInfoW(str(self.root), 1, 0x4 | 0x10, None, None, dacl, sacl)
            if result:
                raise C.WinError(result)
        finally:
            self.windows.kernel.LocalFree(descriptor)

    def spawn(self, executable, mode, parent_pid, privileged_handle=0, *, restricted=True,
              inherit=False, setup_fault=False, before_create=None):
        attributes, initialized = None, False
        size = SIZE()
        startup = STARTUPINFOEX()
        startup.startup.cb = C.sizeof(startup)
        capabilities = SECURITY_CAPABILITIES(self.sid, None, 0, 0)
        policy = W.DWORD(1)
        try:
            if restricted or setup_fault:
                self.windows.kernel.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
                attributes = C.create_string_buffer(size.value)
                require(self.windows.kernel.InitializeProcThreadAttributeList(attributes, 2, 0, C.byref(size)))
                initialized = True
                startup.attributes = C.cast(attributes, P)
                if setup_fault:
                    require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0xFFFFFFFF,
                                                                         C.byref(policy), C.sizeof(policy), None, None))
                    raise RuntimeError("INVALID_ATTRIBUTE_UNEXPECTEDLY_ACCEPTED")
                require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009,
                                                                     C.byref(capabilities), C.sizeof(capabilities), None, None))
                require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000E,
                                                                     C.byref(policy), C.sizeof(policy), None, None))
            process = PROCESS_INFORMATION()
            command = C.create_unicode_buffer(subprocess.list2cmdline(
                [str(executable), str(self.root), mode, str(parent_pid), str(privileged_handle)]))
            # Creation attributes are effective before any instruction; suspension permits
            # durable PID+creation identity to be committed before fixture work can start.
            if before_create is not None:
                before_create()
            require(self.windows.kernel.CreateProcessW(str(executable), command, None, None,
                                                      bool(inherit), 0x80000 | 0x4, None,
                                                      str(self.root), C.byref(startup), C.byref(process)))
            return Process(self.windows, process.process, process.thread)
        finally:
            if initialized:
                self.windows.kernel.DeleteProcThreadAttributeList(attributes)

    def close(self):
        if self.sid:
            result = self.windows.userenv.DeleteAppContainerProfile(self.name)
            self.windows.advapi.FreeSid(self.sid)
            self.sid = P()
            if result < 0:
                raise RuntimeError(f"OWNED_PROFILE_CLEANUP_FAILED:0x{result & 0xFFFFFFFF:08x}")
