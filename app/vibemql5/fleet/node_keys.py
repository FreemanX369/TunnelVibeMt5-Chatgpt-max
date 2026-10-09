"""Explicit per-installation private-key files. No overwrite or secret receipts."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .wire import WireError


def _windows_validate_acl(control, aces, current_sid, owner_sid):
    # A foreign owner can later rewrite a restrictive DACL. Both facts must be
    # obtained from the same retained handle before reading private bytes.
    if owner_sid not in {current_sid, "S-1-5-18"}:
        raise WireError("NODE_KEY_STORAGE_INVALID")
    expected_aces = {(0, 0, 0x001F01FF, "S-1-5-18"), (0, 0, 0x001F01FF, current_sid)}
    # Inspect actual ACE type/flags/mask/SID, independent of SDDL aliases and
    # rights rendering. DACL_PRESENT and DACL_PROTECTED are both mandatory.
    if control & 0x1004 != 0x1004 or len(aces) != len(expected_aces) or set(aces) != expected_aces:
        raise WireError("NODE_KEY_STORAGE_INVALID")


def _windows_acl(fd, *, set_restrictive=False):
    # Operate on the already-open file handle, avoiding path-based ACL/read races.
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    adv = C.WinDLL("advapi32", use_last_error=True)
    kernel = C.WinDLL("kernel32", use_last_error=True)
    pointer = C.c_void_p
    specs = [(kernel, "GetCurrentProcess", [], W.HANDLE),
        (kernel, "CloseHandle", [W.HANDLE], W.BOOL), (kernel, "LocalFree", [pointer], pointer),
        (adv, "OpenProcessToken", [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], W.BOOL),
        (adv, "GetTokenInformation", [W.HANDLE, C.c_int, pointer, W.DWORD, C.POINTER(W.DWORD)], W.BOOL),
        (adv, "ConvertSidToStringSidW", [pointer, C.POINTER(W.LPWSTR)], W.BOOL),
        (adv, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [W.LPCWSTR, W.DWORD, C.POINTER(pointer), pointer], W.BOOL),
        (adv, "GetSecurityDescriptorDacl", [pointer, C.POINTER(W.BOOL), C.POINTER(pointer), C.POINTER(W.BOOL)], W.BOOL),
        (adv, "GetSecurityDescriptorControl", [pointer, C.POINTER(W.WORD), C.POINTER(W.DWORD)], W.BOOL),
        (adv, "GetAclInformation", [pointer, pointer, W.DWORD, C.c_int], W.BOOL),
        (adv, "GetAce", [pointer, W.DWORD, C.POINTER(pointer)], W.BOOL),
        (adv, "IsValidSid", [pointer], W.BOOL), (adv, "GetLengthSid", [pointer], W.DWORD),
        (adv, "SetSecurityInfo", [W.HANDLE, C.c_int, W.DWORD, pointer, pointer, pointer, pointer], W.DWORD),
        (adv, "GetSecurityInfo", [W.HANDLE, C.c_int, W.DWORD, pointer, pointer, pointer, pointer, C.POINTER(pointer)], W.DWORD)]
    for dll, name, arguments, result in specs:
        function = getattr(dll, name); function.argtypes, function.restype = arguments, result
    def require(value):
        if not value:
            raise WireError("NODE_KEY_STORAGE_INVALID")
        return value
    token = W.HANDLE()
    require(adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, C.byref(token)))
    try:
        needed = W.DWORD()
        adv.GetTokenInformation(token, 1, None, 0, C.byref(needed))
        buffer = C.create_string_buffer(needed.value)
        require(adv.GetTokenInformation(token, 1, buffer, needed, C.byref(needed)))
        current_sid = C.cast(buffer, C.POINTER(pointer))[0]
        sid_text = W.LPWSTR()
        require(adv.ConvertSidToStringSidW(current_sid, C.byref(sid_text)))
        try:
            sid = sid_text.value
        finally:
            kernel.LocalFree(C.cast(sid_text, pointer))
    finally:
        kernel.CloseHandle(token)
    handle = W.HANDLE(msvcrt.get_osfhandle(fd))
    if set_restrictive:
        descriptor = pointer()
        require(adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "D:P(A;;FA;;;SY)" + ("" if sid == "S-1-5-18" else "(A;;FA;;;" + sid + ")"), 1, C.byref(descriptor), None))
        try:
            present, defaulted, acl = W.BOOL(), W.BOOL(), pointer()
            require(adv.GetSecurityDescriptorDacl(descriptor, C.byref(present), C.byref(acl), C.byref(defaulted)))
            if not present.value or not acl.value or adv.SetSecurityInfo(handle, 1, 0x80000005, current_sid, None, acl, None):
                raise WireError("NODE_KEY_STORAGE_INVALID")
        finally:
            kernel.LocalFree(descriptor)
    descriptor, owner = pointer(), pointer()
    if adv.GetSecurityInfo(handle, 1, 5, C.byref(owner), None, None, None, C.byref(descriptor)):
        raise WireError("NODE_KEY_STORAGE_INVALID")
    try:
        if not owner.value:
            raise WireError("NODE_KEY_STORAGE_INVALID")
        owner_text = W.LPWSTR()
        require(adv.ConvertSidToStringSidW(owner, C.byref(owner_text)))
        try:
            owner_sid = owner_text.value
        finally:
            kernel.LocalFree(C.cast(owner_text, pointer))
        control, revision = W.WORD(), W.DWORD()
        require(adv.GetSecurityDescriptorControl(descriptor,C.byref(control),C.byref(revision)))
        present, defaulted, acl = W.BOOL(), W.BOOL(), pointer()
        require(adv.GetSecurityDescriptorDacl(descriptor,C.byref(present),C.byref(acl),C.byref(defaulted)))
        if not present.value or not acl.value:raise WireError("NODE_KEY_STORAGE_INVALID")
        class AclSize(C.Structure):
            _fields_=[("count",W.DWORD),("in_use",W.DWORD),("free",W.DWORD)]
        class AceHeader(C.Structure):
            _fields_=[("type",W.BYTE),("flags",W.BYTE),("size",W.WORD)]
        size=AclSize();require(adv.GetAclInformation(acl,C.byref(size),C.sizeof(size),2))
        if size.count>2:raise WireError("NODE_KEY_STORAGE_INVALID")
        aces=[]
        for index in range(size.count):
            ace=pointer();require(adv.GetAce(acl,index,C.byref(ace)))
            header=C.cast(ace,C.POINTER(AceHeader)).contents
            if header.type!=0 or header.size<12:raise WireError("NODE_KEY_STORAGE_INVALID")
            mask=C.cast(ace.value+4,C.POINTER(W.DWORD)).contents.value
            trustee=pointer(ace.value+8)
            require(adv.IsValidSid(trustee))
            if adv.GetLengthSid(trustee)!=header.size-8:raise WireError("NODE_KEY_STORAGE_INVALID")
            trustee_text=W.LPWSTR();require(adv.ConvertSidToStringSidW(trustee,C.byref(trustee_text)))
            try:aces.append((header.type,header.flags,mask,trustee_text.value))
            finally:kernel.LocalFree(C.cast(trustee_text,pointer))
        try:_windows_validate_acl(control.value,aces,sid,owner_sid)
        except WireError as exc:
            # Bounded public ACL evidence helps platform fixtures; product
            # error handlers expose only the unchanged finite failure code.
            exc.add_note("retained ACL: "+repr({"control":control.value,"aces":aces,"current_sid":sid,"owner_sid":owner_sid})[:1024])
            raise
        return {"control":control.value,"aces":aces,"current_sid":sid,"owner_sid":owner_sid}
    finally:
        kernel.LocalFree(descriptor)



def _windows_create(path):
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [W.HANDLE], W.BOOL
    # Request WRITE_DAC and WRITE_OWNER explicitly to assign the current user
    # and protected ACL before private bytes. No sharing/inheritance.
    handle = kernel.CreateFileW(str(path), 0xC00C0000, 0, None, 1, 0x00200080, None)
    if handle == C.c_void_p(-1).value:
        if C.get_last_error() in (80,183):
            raise FileExistsError()
        raise WireError("NODE_KEY_STORAGE_INVALID")
    try:
        return msvcrt.open_osfhandle(int(handle), os.O_RDWR | os.O_BINARY | os.O_NOINHERIT)
    except Exception:
        kernel.CloseHandle(handle)
        raise WireError("NODE_KEY_STORAGE_INVALID") from None


def _windows_hold_private_directory(path):
    """Protect fresh operator staging and retain it against rename/delete."""
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [W.HANDLE], W.BOOL
    class Attributes(C.Structure):
        _fields_ = [("attributes", W.DWORD), ("reparse_tag", W.DWORD)]
    kernel.GetFileInformationByHandleEx.argtypes = [W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
    kernel.GetFileInformationByHandleEx.restype = W.BOOL
    # Read/write sharing permits TLS to open protected children; absence of
    # FILE_SHARE_DELETE retains this directory's identity through the load.
    handle = kernel.CreateFileW(str(path), 0x800C0000, 3, None, 3, 0x02200000, None)
    if handle == C.c_void_p(-1).value:
        raise WireError("NODE_KEY_STORAGE_INVALID")
    fd = None
    try:
        info = Attributes()
        if (not kernel.GetFileInformationByHandleEx(handle, 9, C.byref(info), C.sizeof(info))
                or not info.attributes & 0x10 or info.attributes & 0x400):
            raise WireError("NODE_KEY_STORAGE_INVALID")
        fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
        _windows_acl(fd, set_restrictive=True)
        return fd
    except Exception:
        if fd is not None:
            os.close(fd)
        else:
            kernel.CloseHandle(handle)
        raise WireError("NODE_KEY_STORAGE_INVALID") from None


def _path(value):
    path = Path(value).absolute()
    if ".." in path.parts:
        raise WireError("NODE_KEY_STORAGE_INVALID")
    if "secrets" not in path.parts or not path.parent.is_dir():
        raise WireError("NODE_KEY_STORAGE_INVALID")
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400):
            raise WireError("NODE_KEY_STORAGE_INVALID")
    if os.name != "nt" and (path.parent.stat().st_mode & 0o077 or path.parent.stat().st_uid != os.getuid()):
        raise WireError("NODE_KEY_STORAGE_INVALID")
    return path


def _check(fd):
    record = os.fstat(fd)
    if not stat.S_ISREG(record.st_mode) or record.st_nlink != 1:
        raise WireError("NODE_KEY_STORAGE_INVALID")
    if os.name == "nt":
        _windows_acl(fd)
    elif record.st_mode & 0o077 or record.st_uid != os.getuid():
        raise WireError("NODE_KEY_STORAGE_INVALID")


def create_node_key(path):
    path = _path(path)
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = None
    created = False
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOINHERIT", 0)
        fd = _windows_create(path) if os.name == "nt" else os.open(path, flags, 0o600)
        created = True
        if os.name == "nt":
            _windows_acl(fd, set_restrictive=True)
        _check(fd)
        view = memoryview(private)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise WireError("NODE_KEY_STORAGE_INVALID")
            view = view[count:]
        os.fsync(fd)
    except FileExistsError:
        raise WireError("NODE_KEY_EXISTS") from None
    except (OSError, ValueError):
        raise WireError("NODE_KEY_STORAGE_INVALID") from None
    finally:
        if fd is not None:
            os.close(fd)
    # Public-only return. Private bytes never enter a report/log/JSON receipt.
    return {"schema": "fleet.node-key/1", "public_key": key.public_key().public_bytes_raw().hex()}


def load_node_key(path):
    fd = None
    try:
        path = _path(path)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOINHERIT", 0))
        _check(fd)
        content = os.read(fd, 4097)
        if len(content) > 4096:
            raise WireError("NODE_KEY_STORAGE_INVALID")
        key = serialization.load_pem_private_key(content, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise WireError("NODE_KEY_STORAGE_INVALID")
        return key
    except (OSError, ValueError, TypeError):
        raise WireError("NODE_KEY_STORAGE_INVALID") from None
    finally:
        if fd is not None:
            os.close(fd)
