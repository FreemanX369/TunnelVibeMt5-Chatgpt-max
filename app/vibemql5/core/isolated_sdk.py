"""Fixed operator-qualified Windows SDK worker creation boundary.

Win32 structures, handle identity and ACL readback reuse reviewed Q1 mechanics.
No arbitrary executable/argv, inherited handle, runtime ACL grant or proof import.
"""
from __future__ import annotations
import ctypes as C
import hashlib
import os
import subprocess
import time
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

class ACL(C.Structure):
    _fields_ = [("revision", W.BYTE), ("reserved", W.BYTE), ("size", W.WORD),
                ("count", W.WORD), ("reserved2", W.WORD)]

class ACE_HEADER(C.Structure):
    _fields_ = [("kind", W.BYTE), ("flags", W.BYTE), ("size", W.WORD)]

def require(value):
    if not value:
        raise C.WinError(C.get_last_error())
    return value

class Windows:
    def __init__(self):
            if os.name != "nt":
                raise RuntimeError("LIVE_ATTACH_ONLY_UNPROVEN")
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
                (self.advapi, "GetAce", [P, W.DWORD, C.POINTER(P)], W.BOOL),
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

    def token_observation(self, process_handle=None):
            token = W.HANDLE()
            handle = self.kernel.GetCurrentProcess() if process_handle is None else process_handle
            require(self.advapi.OpenProcessToken(handle, 0x8, C.byref(token)))
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
                observation = {"sddl": text.value, "security_information": "DACL_AND_LABEL"}
                present, defaulted, sacl = W.BOOL(), W.BOOL(), P()
                require(self.advapi.GetSecurityDescriptorSacl(descriptor, C.byref(present), C.byref(sacl), C.byref(defaulted)))
                labels = {"present": bool(present.value), "defaulted": bool(defaulted.value),
                          "null_acl": not bool(sacl.value), "label_aces": [],
                          "disposition": "ABSENT_SELECTED_LABEL_DESCRIPTOR" if not present.value else "NULL_SELECTED_LABEL_ACL"}
                if present.value and sacl.value:
                    acl = C.cast(sacl, C.POINTER(ACL)).contents
                    if acl.size < C.sizeof(ACL):
                        raise RuntimeError("LABEL_DESCRIPTOR_ACL_SIZE_INVALID")
                    labels.update(acl_bytes=acl.size, ace_count=acl.count,
                                  raw_acl_sha256=hashlib.sha256(C.string_at(sacl, acl.size)).hexdigest(),
                                  parse_limit_aces=64, truncated=acl.count > 64,
                                  disposition="TRUNCATED_LABEL_PARSE_NO_QUALIFICATION" if acl.count > 64 else "OBSERVED_SELECTED_LABEL_ACL_ONLY")
                    for index in range(min(acl.count, 64)):
                        ace = P()
                        require(self.advapi.GetAce(sacl, index, C.byref(ace)))
                        if not ace.value or not sacl.value + C.sizeof(ACL) <= ace.value or ace.value + C.sizeof(ACE_HEADER) > sacl.value + acl.size:
                            raise RuntimeError("LABEL_DESCRIPTOR_ACE_POINTER_INVALID")
                        header = C.cast(ace, C.POINTER(ACE_HEADER)).contents
                        if header.size < C.sizeof(ACE_HEADER):
                            raise RuntimeError("LABEL_DESCRIPTOR_ACE_INVALID")
                        if ace.value + header.size > sacl.value + acl.size:
                            raise RuntimeError("LABEL_DESCRIPTOR_ACE_OUTSIDE_ACL")
                        if header.kind == 0x11:  # SYSTEM_MANDATORY_LABEL_ACE
                            if header.size < 20:
                                raise RuntimeError("MANDATORY_LABEL_ACE_TOO_SHORT")
                            subauthorities = C.c_ubyte.from_address(ace.value + 9).value
                            if not subauthorities or 16 + subauthorities * 4 > header.size:
                                raise RuntimeError("MANDATORY_LABEL_SID_OUTSIDE_ACE")
                            revision = C.c_ubyte.from_address(ace.value + 8).value
                            authority = C.string_at(ace.value + 10, 6)
                            if revision != 1 or subauthorities != 1 or authority != b"\0\0\0\0\0\x10":
                                raise RuntimeError("MANDATORY_LABEL_SID_INVALID")
                            mask = C.cast(ace.value + 4, C.POINTER(C.c_uint32)).contents.value
                            labels["label_aces"].append({"index": index, "flags": header.flags, "mask": mask,
                                                        "sid": self.sid_string(ace.value + 8)})
                observation["selected_label_descriptor"] = labels
                return observation
            finally:
                if text:
                    self.kernel.LocalFree(C.cast(text, P))
                self.kernel.LocalFree(descriptor)

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
            raise RuntimeError(f"SDK_EXIT_STATUS_UNKNOWN:{wait}")
        return wait == 0

    def wait(self, milliseconds=5000):
        wait = self.windows.kernel.WaitForSingleObject(self.handle, milliseconds)
        if wait != 0:
            raise RuntimeError(f"SDK_WAIT_NOT_PROVEN:{wait}")
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


def restriction_observation(windows, handle):
    kernel = windows.kernel
    kernel.GetProcessMitigationPolicy.argtypes = [W.HANDLE, C.c_int, P, SIZE]
    kernel.GetProcessMitigationPolicy.restype = W.BOOL
    flags = W.DWORD()
    require(kernel.GetProcessMitigationPolicy(handle, 13, C.byref(flags), C.sizeof(flags)))
    facts = windows.token_observation(handle)
    token, size = W.HANDLE(), W.DWORD()
    require(windows.advapi.OpenProcessToken(handle, 0x8, C.byref(token)))
    try:
        windows.advapi.GetTokenInformation(token, 30, None, 0, C.byref(size))
        buffer = C.create_string_buffer(size.value)
        require(windows.advapi.GetTokenInformation(token, 30, buffer, size, C.byref(size)))
        capabilities = C.cast(buffer, C.POINTER(W.DWORD))[0]
        windows.advapi.GetTokenInformation(token, 31, None, 0, C.byref(size))
        buffer = C.create_string_buffer(size.value)
        require(windows.advapi.GetTokenInformation(token, 31, buffer, size, C.byref(size)))
        sid = windows.sid_string(C.cast(buffer, C.POINTER(P))[0])
    finally:
        require(windows.kernel.CloseHandle(token))
    return {"appcontainer": facts["appcontainer"], "capabilities": int(capabilities),
            "integrity_sid": facts["integrity_sid"], "appcontainer_sid": sid,
            "child_policy_flags": flags.value, "inherits_handles": False,
            "source": "ACTUAL_TOKEN_AND_MITIGATION_FIXED_CREATE_NO_HANDLE_INHERITANCE"}


def current_restrictions():
    windows = Windows()
    return restriction_observation(windows, windows.kernel.GetCurrentProcess())


class OwnedSdkProcess(Process):
    def verify_observation(self, observation, *, require_live=True):
        created, actual = self.identity(), observation.identity()
        if ((require_live and (observation.exited() or self.exited()))
                or actual != {"pid": created["pid"], "creation": str(created["creation_100ns"]),
                              "image": os.path.normcase(os.path.realpath(created["image"]))}):
            raise RuntimeError("CREATED_PROCESS_LIFETIME_MISMATCH")

    def allow_resume(self, authority, expected, observation):
        self.verify_observation(observation)
        if authority.load() != expected or expected["phase"] != "BOUND" or observation.identity() != expected["worker"]:
            raise RuntimeError("DURABLE_BIND_REQUIRED")
        self._resume_binding = authority, dict(expected), observation

    def resume(self):
        authority, expected, observation = getattr(self, "_resume_binding", (None, None, None))
        if authority is None or authority.load() != expected:
            raise RuntimeError("DURABLE_BIND_REQUIRED")
        self.verify_observation(observation)
        super().resume()


class SdkBoundary:
    def __init__(self, root, installation):
        from ..fleet.sdk_qualification import QualifiedSdkInstallation, QualificationError
        if type(installation) is not QualifiedSdkInstallation:
            raise QualificationError()
        installation.assert_current()
        self.root, self.installation = Path(root).resolve(), installation
        self.windows, self.sid = Windows(), P()
        profile = installation.installation
        derive = self.windows.userenv.DeriveAppContainerSidFromAppContainerName
        derive.argtypes, derive.restype = [W.LPCWSTR, C.POINTER(P)], C.c_long
        result = derive(profile["profile_name"], C.byref(self.sid))
        if result < 0 or not self.sid:
            raise QualificationError()
        try:
            if self.windows.sid_string(self.sid) != profile["profile_sid"]:
                raise QualificationError()
            self._grant_ipc_root()
        except BaseException:
            self.close()
            raise

    def _grant_ipc_root(self):
        # Only the unique disposable IPC directory is modified. Runtime and
        # terminal ACLs must already match the operator-qualified installation.
        user, app = self.windows.user_sid(), self.windows.sid_string(self.sid)
        sddl = f"D:(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;0x1201bf;;;{app})S:(ML;;NW;;;LW)"
        descriptor = P()
        require(self.windows.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, C.byref(descriptor), None))
        try:
            dacl, sacl, present, defaulted = P(), P(), W.BOOL(), W.BOOL()
            require(self.windows.advapi.GetSecurityDescriptorDacl(descriptor, C.byref(present), C.byref(dacl), C.byref(defaulted)))
            require(self.windows.advapi.GetSecurityDescriptorSacl(descriptor, C.byref(present), C.byref(sacl), C.byref(defaulted)))
            result = self.windows.advapi.SetNamedSecurityInfoW(str(self.root), 1, 0x4 | 0x10, None, None, dacl, sacl)
            if result:
                raise C.WinError(result)
        finally:
            self.windows.kernel.LocalFree(descriptor)

    def spawn(self, request, output, public_key_file):
        from ..fleet.sdk_qualification import QualificationError
        self.installation.assert_current()
        paths = [Path(path).resolve() for path in (request, output, public_key_file)]
        if any(path.parent != self.root for path in paths) or [p.name for p in paths] != ["request.json", "result.json", "operator-public.key"]:
            raise QualificationError()
        approved = self.installation.installation
        startup, size = STARTUPINFOEX(), SIZE()
        startup.startup.cb = C.sizeof(startup)
        attributes, initialized, process = None, False, None
        capabilities, policy = SECURITY_CAPABILITIES(self.sid, None, 0, 0), W.DWORD(1)
        try:
            self.windows.kernel.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
            attributes = C.create_string_buffer(size.value)
            require(self.windows.kernel.InitializeProcThreadAttributeList(attributes, 2, 0, C.byref(size)))
            initialized, startup.attributes = True, C.cast(attributes, P)
            require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009, C.byref(capabilities), C.sizeof(capabilities), None, None))
            require(self.windows.kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000E, C.byref(policy), C.sizeof(policy), None, None))
            # -I suppresses caller environment/PYTHONPATH and user site. The pinned
            # dedicated Python/site/runtime configuration is part of real Q2 approval.
            command = C.create_unicode_buffer(subprocess.list2cmdline([
                approved["python"], "-I", approved["worker"], str(paths[0]), str(paths[1]),
                str(self.installation.approval_path), str(paths[2])]))
            info = PROCESS_INFORMATION()
            require(self.windows.kernel.CreateProcessW(approved["python"], command, None, None,
                False, 0x4 | 0x80000, None, str(self.root), C.byref(startup), C.byref(info)))
            process = OwnedSdkProcess(self.windows, info.process, info.thread)
            process.identity()
            process.restrictions = restriction_observation(self.windows, process.handle)
            self.installation.assert_restrictions(process.restrictions)
            return process
        except BaseException:
            if process is not None:
                try:
                    if not process.exited():
                        require(self.windows.kernel.TerminateProcess(process.handle, 92))
                    process.wait(5000)
                finally:
                    process.close()
            raise
        finally:
            if initialized:
                self.windows.kernel.DeleteProcThreadAttributeList(attributes)

    def prove_closure(self, process, observation):
        self.installation.assert_current()
        self.installation.assert_restrictions(process.restrictions)
        process.verify_observation(observation, require_live=False)
        if not process.exited() or not observation.exited():
            raise RuntimeError("EXACT_WORKER_EXIT_UNPROVEN")
        # This disposition relies on the signed operator approval of the exact
        # real Q2 no-start/escape matrix, not worker shutdown or a fixture string.
        return "PREVENTED_BY_BOUNDARY"

    def close(self):
        if self.sid:
            self.windows.advapi.FreeSid(self.sid)
            self.sid = P()  # The pre-qualified installed profile is not deleted.


def probe_terminal(executable, *, deadline, clock=time.monotonic):
    """Read-only fixed-name Toolhelp discovery plus independently retained identity."""
    from .native_ownership import ObservedProcess
    windows = Windows()
    class ENTRY(C.Structure):
        _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("pid", W.DWORD),
            ("heap", SIZE), ("module", W.DWORD), ("threads", W.DWORD), ("parent", W.DWORD),
            ("priority", W.LONG), ("flags", W.DWORD), ("name", W.WCHAR * 260)]
    kernel = windows.kernel
    for name, args, result in [
        ("CreateToolhelp32Snapshot", [W.DWORD, W.DWORD], W.HANDLE),
        ("Process32FirstW", [W.HANDLE, C.POINTER(ENTRY)], W.BOOL),
        ("Process32NextW", [W.HANDLE, C.POINTER(ENTRY)], W.BOOL)]:
        getattr(kernel, name).argtypes, getattr(kernel, name).restype = args, result
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == P(-1).value:
        raise RuntimeError("LIVE_PROCESS_UNAVAILABLE")
    retained = []
    try:
        entry = ENTRY()
        entry.size = C.sizeof(entry)
        ok = kernel.Process32FirstW(snapshot, C.byref(entry))
        while ok:
            if clock() >= deadline:
                raise RuntimeError("LIVE_DEADLINE_EXCEEDED")
            if entry.name.casefold() == "terminal64.exe":
                observed = ObservedProcess(int(entry.pid))
                try:
                    actual = observed.identity()
                    if actual["image"] == os.path.normcase(os.path.realpath(executable)):
                        retained.append(observed)
                        observed = None
                finally:
                    if observed is not None:
                        observed.close()
            ok = kernel.Process32NextW(snapshot, C.byref(entry))
        if C.get_last_error() != 18 or len(retained) != 1:
            raise RuntimeError("TERMINAL_NOT_RUNNING" if not retained else "LIVE_BINDING_MISMATCH")
        return retained.pop()
    finally:
        require(kernel.CloseHandle(snapshot))
        for observed in retained:
            observed.close()
