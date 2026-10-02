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
            (self.kernel, "CreateFileW", [W.LPCWSTR, W.DWORD, W.DWORD, P, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE),
            (self.kernel, "WriteFile", [W.HANDLE, P, W.DWORD, C.POINTER(W.DWORD), P], W.BOOL),
            (self.kernel, "FlushFileBuffers", [W.HANDLE], W.BOOL),
            (self.advapi, "OpenProcessToken", [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], W.BOOL),
            (self.advapi, "GetTokenInformation", [W.HANDLE, C.c_int, P, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
            (self.advapi, "ConvertSidToStringSidW", [P, C.POINTER(W.LPWSTR)], W.BOOL),
            (self.advapi, "FreeSid", [P], P),
            (self.advapi, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [W.LPCWSTR, W.DWORD, C.POINTER(P), P], W.BOOL),
            (self.advapi, "GetSecurityDescriptorDacl", [P, C.POINTER(W.BOOL), C.POINTER(P), C.POINTER(W.BOOL)], W.BOOL),
            (self.advapi, "GetSecurityDescriptorSacl", [P, C.POINTER(W.BOOL), C.POINTER(P), C.POINTER(W.BOOL)], W.BOOL),
            (self.advapi, "SetNamedSecurityInfoW", [W.LPWSTR, C.c_int, W.DWORD, P, P, P, P], W.DWORD),
            (self.advapi, "GetNamedSecurityInfoW", [W.LPWSTR, C.c_int, W.DWORD] + [C.POINTER(P)] * 5, W.DWORD),
            (self.advapi, "ConvertSecurityDescriptorToStringSecurityDescriptorW", [P, W.DWORD, W.DWORD, C.POINTER(W.LPWSTR), C.POINTER(W.DWORD)], W.BOOL),
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

    def token_observation(self):
        token = W.HANDLE()
        require(self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x8, C.byref(token)))
        try:
            values = {}
            for kind, name in ((1, "user_sid"), (25, "integrity_sid")):
                size = W.DWORD()
                self.advapi.GetTokenInformation(token, kind, None, 0, C.byref(size))
                buffer = C.create_string_buffer(size.value)
                require(self.advapi.GetTokenInformation(token, kind, buffer, size, C.byref(size)))
                values[name] = self.sid_string(C.cast(buffer, C.POINTER(P))[0])
            for kind, name in ((29, "appcontainer"), (20, "elevated")):
                value, size = W.DWORD(), W.DWORD()
                require(self.advapi.GetTokenInformation(token, kind, C.byref(value), C.sizeof(value), C.byref(size)))
                values[name] = value.value
            return values
        finally:
            require(self.kernel.CloseHandle(token))

    def security_observation(self, path):
        descriptor = P()
        # DACL + mandatory label only. Never enable privileges or request a full SACL.
        result = self.advapi.GetNamedSecurityInfoW(str(path), 1, 0x4 | 0x10,
                                                 None, None, None, None, C.byref(descriptor))
        if result:
            return {"win32_error": int(result)}
        text, size = W.LPWSTR(), W.DWORD()
        try:
            require(self.advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor, 1, 0x4 | 0x8, C.byref(text), C.byref(size)))
            # The in-memory SACL contains only the label requested above. Formatting
            # that selected data does not query a full SACL or enable a privilege.
            return {"sddl": text.value, "security_information": "DACL_AND_LABEL"}
        finally:
            if text:
                self.kernel.LocalFree(C.cast(text, P))
            self.kernel.LocalFree(descriptor)

    def write_observation(self, path):
        handle = self.kernel.CreateFileW(str(path), 0x40000000, 1, None, 1, 0x80, None)
        if handle == W.HANDLE(-1).value:
            return {"create_error": int(C.get_last_error()), "write_attempted": False}
        result = {"create_error": 0, "write_attempted": True}
        try:
            data, written = C.create_string_buffer(b"{}\n"), W.DWORD()
            ok = self.kernel.WriteFile(handle, data, 3, C.byref(written), None)
            result.update(write_error=0 if ok else int(C.get_last_error()), written_bytes=written.value)
            flushed = self.kernel.FlushFileBuffers(handle)
            result["flush_error"] = 0 if flushed else int(C.get_last_error())
            return result
        finally:
            require(self.kernel.CloseHandle(handle))


class Process:
    def __init__(self, windows, process, thread=None):
        self.windows, self.handle, self.thread = windows, process, thread
        self._live_identity = None
        self._identity_handle = None

    def lifetime(self):
        times = [W.FILETIME() for _ in range(4)]
        require(self.windows.kernel.GetProcessTimes(self.handle, *(C.byref(t) for t in times)))
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return {"pid": int(require(self.windows.kernel.GetProcessId(self.handle))),
                "creation_100ns": created}

    def identity(self):
        lifetime = self.lifetime()
        signaled = self.exited()
        if self._live_identity is not None:
            if self._identity_handle != self.handle or any(
                    self._live_identity[key] != value for key, value in lifetime.items()):
                raise RuntimeError("EXACT_PROCESS_IDENTITY_MISMATCH")
            # A retained kernel handle identifies one process lifetime. The image was
            # queried while this handle was live; do not query a dead executable path.
            return dict(self._live_identity)
        if signaled:
            raise RuntimeError("LIVE_IMAGE_NOT_CAPTURED_BEFORE_EXIT")
        image = C.create_unicode_buffer(32768)
        length = W.DWORD(len(image))
        require(self.windows.kernel.QueryFullProcessImageNameW(self.handle, 0, image, C.byref(length)))
        if self.exited():
            raise RuntimeError("LIVE_IMAGE_CAPTURE_RACED_EXIT")
        self._live_identity = {**lifetime, "image": os.path.normcase(image.value)}
        self._identity_handle = self.handle
        return dict(self._live_identity)

    def resume(self):
        if self.windows.kernel.ResumeThread(self.thread) == 0xFFFFFFFF:
            raise C.WinError(C.get_last_error())

    def exited(self):
        wait = self.windows.kernel.WaitForSingleObject(self.handle, 0)
        if wait == 0xFFFFFFFF:
            raise C.WinError(C.get_last_error())
        if wait not in (0, 0x102):
            raise RuntimeError(f"FIXTURE_EXIT_STATUS_UNKNOWN:{wait}")
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
        if not self.exited() or self.identity() != expected:
            raise RuntimeError("EXACT_PROCESS_EXIT_NOT_PROVEN")
        return (time.monotonic() - started) * 1000

    def close(self):
        if self.thread:
            require(self.windows.kernel.CloseHandle(self.thread))
            self.thread = None
        if self.handle:
            require(self.windows.kernel.CloseHandle(self.handle))
            self.handle = None
            self._live_identity = None
            self._identity_handle = None

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
              inherit=False, setup_fault=False, before_create=None, no_console=False):
        attributes, initialized = None, False
        size = SIZE()
        startup = STARTUPINFOEX()
        startup.startup.cb = C.sizeof(startup) if restricted or setup_fault else C.sizeof(STARTUPINFO)
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
            flags = 0x4  # Retain the prior working console startup by default.
            if no_console:  # Focused matched diagnostic only; not the default proof path.
                flags |= 0x08000000
            if initialized:
                flags |= 0x80000
            require(self.windows.kernel.CreateProcessW(str(executable), command, None, None,
                                                      bool(inherit), flags, None,
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
