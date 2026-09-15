#!/usr/bin/env python3
"""TIP-026R3 Windows runtime capture prototype.

Security property: there is intentionally NO --pid, --process-name, --address or --command
argument. The only target authority is a short-lived HMAC-signed record emitted by the
trusted TunnelVibeMQL5 bridge for an exact running tester job.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time

try:
    from .authority import (
        AuthorityError,
        AuthorityRecord,
        validate_live_binding,
        validate_static,
        verify_signature,
    )
except ImportError:  # direct script execution
    from authority import (
        AuthorityError,
        AuthorityRecord,
        validate_live_binding,
        validate_static,
        verify_signature,
    )

PROCESS_VM_READ = 0x0010
PROCESS_CREATE_PROCESS = 0x0080
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_DUP_HANDLE = 0x0040
PROCESS_QUERY_INFORMATION = 0x0400
STILL_ACTIVE = 259

PSS_CAPTURE_VA_CLONE = 0x00000001
PSS_CAPTURE_THREADS = 0x00000080
PSS_CAPTURE_VA_SPACE = 0x00000800
PSS_QUERY_VA_CLONE_INFORMATION = 1

PSS_CREATE_BREAKAWAY_OPTIONAL = 0x04000000
PSS_CREATE_BREAKAWAY = 0x08000000
PSS_CREATE_USE_VM_ALLOCATIONS = 0x20000000

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

MINIDUMP_WITH_DATA_SEGS = 0x00000001
MINIDUMP_WITH_FULL_MEMORY = 0x00000002
MINIDUMP_WITH_HANDLE_DATA = 0x00000004
MINIDUMP_WITH_UNLOADED_MODULES = 0x00000020
MINIDUMP_WITH_PROCESS_THREAD_DATA = 0x00000100
MINIDUMP_WITH_PRIVATE_READ_WRITE_MEMORY = 0x00000200
MINIDUMP_WITH_FULL_MEMORY_INFO = 0x00000800
MINIDUMP_WITH_THREAD_INFO = 0x00001000
MINIDUMP_WITH_CODE_SEGS = 0x00002000
MINIDUMP_WITH_PRIVATE_WRITE_COPY_MEMORY = 0x00010000
MINIDUMP_IGNORE_INACCESSIBLE_MEMORY = 0x00020000

GENERIC_WRITE = 0x40000000
CREATE_ALWAYS = 2
FILE_ATTRIBUTE_NORMAL = 0x80
PAGE_SIZE = 4096
STREAM_CHUNK_SIZE = 1024 * 1024
MAX_PRIVATE_CAPTURE_BYTES = 256 * 1024 * 1024
MAX_PRIVATE_CAPTURE_SECONDS = 15.0

class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

class PSS_VA_CLONE_INFORMATION(ctypes.Structure):
    _fields_ = [("VaCloneHandle", wintypes.HANDLE)]

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]

def configure_apis(kernel32, dbghelp) -> None:
    """Declare x64-safe WinAPI signatures; ctypes defaults would truncate HANDLE values."""
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE,ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME)]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.PssCaptureSnapshot.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.c_void_p)]
    kernel32.PssCaptureSnapshot.restype = wintypes.DWORD
    kernel32.PssQuerySnapshot.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel32.PssQuerySnapshot.restype = wintypes.DWORD
    kernel32.PssFreeSnapshot.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.PssFreeSnapshot.restype = wintypes.DWORD
    kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE,ctypes.c_void_p,ctypes.POINTER(MEMORY_BASIC_INFORMATION),ctypes.c_size_t]
    kernel32.VirtualQueryEx.restype = ctypes.c_size_t
    kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    dbghelp.MiniDumpWriteDump.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def filetime_to_int(ft: FILETIME) -> int:
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)

def load_key() -> bytes:
    raw = os.environ.get("VIBEMQL5_RUNTIME_AUTH_KEY_HEX", "")
    if len(raw) < 64:
        raise AuthorityError("VIBEMQL5_RUNTIME_AUTH_KEY_HEX missing/too short")
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise AuthorityError("invalid runtime authority key encoding") from exc

def query_process_facts(kernel32, handle) -> tuple[str, int]:
    exit_code = wintypes.DWORD(0)
    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
        raise OSError(ctypes.get_last_error(), "GetExitCodeProcess failed")
    if exit_code.value != STILL_ACTIVE:
        raise AuthorityError("bound testing agent is no longer running")
    buf = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buf))
    if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        raise OSError(ctypes.get_last_error(), "QueryFullProcessImageNameW failed")
    creation = FILETIME(); exit_ft = FILETIME(); kernel_ft = FILETIME(); user_ft = FILETIME()
    if not kernel32.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exit_ft),ctypes.byref(kernel_ft),ctypes.byref(user_ft)):
        raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
    return buf.value, filetime_to_int(creation)

def open_bound_process(kernel32, pid: int):
    rights = PROCESS_CREATE_PROCESS | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
    handle = kernel32.OpenProcess(rights, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        image_path, creation_time = query_process_facts(kernel32, handle)
        return handle, image_path, creation_time
    except Exception:
        kernel32.CloseHandle(handle)
        raise

def capture_snapshot(kernel32, process_handle):
    snapshot = ctypes.c_void_p()
    flags = PSS_CAPTURE_VA_CLONE
    rc = kernel32.PssCaptureSnapshot(process_handle, flags, 0, ctypes.byref(snapshot))
    if rc != 0:
        raise OSError(rc, f"PssCaptureSnapshot failed flags=0x{flags:08X}")
    clone_info = PSS_VA_CLONE_INFORMATION()
    rc = kernel32.PssQuerySnapshot(snapshot,PSS_QUERY_VA_CLONE_INFORMATION,ctypes.byref(clone_info),ctypes.sizeof(clone_info))
    if rc != 0 or not clone_info.VaCloneHandle:
        kernel32.PssFreeSnapshot(kernel32.GetCurrentProcess(), snapshot)
        raise OSError(rc or 6, "PssQuerySnapshot(VA_CLONE) failed")
    return snapshot, clone_info.VaCloneHandle

def is_readable_private(mbi: MEMORY_BASIC_INFORMATION) -> bool:
    if mbi.State != MEM_COMMIT or mbi.Type != MEM_PRIVATE: return False
    if mbi.Protect & PAGE_GUARD: return False
    if mbi.Protect & PAGE_NOACCESS: return False
    return True

def dump_private_pages(kernel32, process_handle, out_dir: Path) -> tuple[int, int, bool, str]:
    mem_path = out_dir / "private-regions.bin"; pages_path = out_dir / "page-hashes.jsonl"; regions_path = out_dir / "regions.jsonl"
    address = 0; max_address = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1; sidecar_offset = 0; region_count = 0; page_count = 0
    started = time.perf_counter(); truncated = False; truncate_reason = ""
    with mem_path.open("wb") as mem_out, pages_path.open("w", encoding="utf-8") as page_out, regions_path.open("w", encoding="utf-8") as region_out:
        mbi = MEMORY_BASIC_INFORMATION()
        while address < max_address:
            if sidecar_offset >= MAX_PRIVATE_CAPTURE_BYTES: truncated=True; truncate_reason="BYTE_CAP"; break
            if time.perf_counter()-started >= MAX_PRIVATE_CAPTURE_SECONDS: truncated=True; truncate_reason="TIME_CAP"; break
            got = kernel32.VirtualQueryEx(process_handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not got: break
            base=int(mbi.BaseAddress or 0); size=int(mbi.RegionSize)
            if size<=0: break
            if is_readable_private(mbi):
                region_count += 1
                region_out.write(json.dumps({"base_address":hex(base),"size":size,"protect":int(mbi.Protect),"type":int(mbi.Type),"state":int(mbi.State)},sort_keys=True)+"\n")
                end_addr=base+size; cursor=base
                while cursor < end_addr:
                    if sidecar_offset >= MAX_PRIVATE_CAPTURE_BYTES: truncated=True; truncate_reason="BYTE_CAP"; break
                    if time.perf_counter()-started >= MAX_PRIVATE_CAPTURE_SECONDS: truncated=True; truncate_reason="TIME_CAP"; break
                    budget=MAX_PRIVATE_CAPTURE_BYTES-sidecar_offset; want=min(STREAM_CHUNK_SIZE,end_addr-cursor,budget)
                    if want<=0: truncated=True; truncate_reason="BYTE_CAP"; break
                    buf=ctypes.create_string_buffer(want); read=ctypes.c_size_t(0)
                    ok=kernel32.ReadProcessMemory(process_handle,ctypes.c_void_p(cursor),buf,want,ctypes.byref(read))
                    if ok and read.value>0:
                        chunk=buf.raw[:read.value]; off=0
                        while off < len(chunk):
                            page_data=chunk[off:off+PAGE_SIZE]; page_address=cursor+off
                            mem_out.write(page_data)
                            page_out.write(json.dumps({"address":hex(page_address),"size":len(page_data),"sha256":hashlib.sha256(page_data).hexdigest(),"type":"MEM_PRIVATE","protect":int(mbi.Protect),"sidecar_offset":sidecar_offset},sort_keys=True)+"\n")
                            sidecar_offset += len(page_data); page_count += 1; off += len(page_data)
                        cursor += int(read.value)
                    else:
                        cursor += PAGE_SIZE
                if truncated: break
            next_address=base+size
            if next_address<=address: break
            address=next_address
    return region_count,page_count,truncated,truncate_reason

def minidump_flags(profile: str) -> int:
    private = (MINIDUMP_WITH_DATA_SEGS|MINIDUMP_WITH_UNLOADED_MODULES|MINIDUMP_WITH_PROCESS_THREAD_DATA|MINIDUMP_WITH_PRIVATE_READ_WRITE_MEMORY|MINIDUMP_WITH_FULL_MEMORY_INFO|MINIDUMP_WITH_THREAD_INFO|MINIDUMP_WITH_PRIVATE_WRITE_COPY_MEMORY|MINIDUMP_IGNORE_INACCESSIBLE_MEMORY)
    if profile == "private": return private
    if profile == "miniplus": return private | MINIDUMP_WITH_HANDLE_DATA | MINIDUMP_WITH_CODE_SEGS
    if profile == "full": return private | MINIDUMP_WITH_FULL_MEMORY | MINIDUMP_WITH_HANDLE_DATA | MINIDUMP_WITH_CODE_SEGS
    raise ValueError(f"unsupported profile: {profile}")

def write_minidump(kernel32, dbghelp, clone_handle, profile: str, path: Path) -> None:
    invalid_handle = ctypes.c_void_p(-1).value
    hfile = kernel32.CreateFileW(str(path),GENERIC_WRITE,0,None,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,None)
    if hfile == invalid_handle: raise OSError(ctypes.get_last_error(), "CreateFileW failed")
    try:
        clone_pid = kernel32.GetProcessId(clone_handle)
        if not clone_pid: raise OSError(ctypes.get_last_error(), "GetProcessId(VA clone) failed")
        ok = dbghelp.MiniDumpWriteDump(clone_handle,clone_pid,hfile,minidump_flags(profile),None,None,None)
        if not ok: raise OSError(ctypes.get_last_error(), "MiniDumpWriteDump failed")
    finally:
        kernel32.CloseHandle(hfile)

def consume_nonce(out_root: Path, nonce: str) -> None:
    ledger = out_root / ".runtime-capture-nonces"; ledger.mkdir(parents=True, exist_ok=True)
    marker = ledger / hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    try:
        fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise AuthorityError("authority nonce already used") from exc
    else:
        os.close(fd)

def _failure_code(stage: str, exc: BaseException) -> str:
    message = str(exc or "").strip(); head = message.split(":", 1)[0].strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", head): return head
    mapping = {"authority_load":"AUTHORITY_LOAD_FAILED","authority_key":"AUTHORITY_KEY_FAILED","authority_signature":"AUTHORITY_SIGNATURE_FAILED","authority_static":"AUTHORITY_STATIC_FAILED","open_process":"AGENT_OPEN_FAILED","live_binding_pre":"AGENT_LIVE_BINDING_FAILED","nonce_consume":"AUTHORITY_NONCE_FAILED","pss_capture":"PSS_CAPTURE_FAILED","private_pages":"PRIVATE_PAGE_DUMP_FAILED","minidump":"MINIDUMP_FAILED","live_binding_post":"POST_CAPTURE_BINDING_FAILED","manifest":"MANIFEST_WRITE_FAILED"}
    if "authority nonce already used" in message.lower(): return "AUTHORITY_REPLAY"
    return mapping.get(stage, "CAPTURE_HELPER_EXCEPTION")

def _failure_payload(stage: str, exc: BaseException) -> dict:
    code = getattr(exc, "winerror", None)
    if code is None: code = getattr(exc, "errno", None)
    try: numeric = int(code) if code is not None else None
    except Exception: numeric = None
    message = ""
    if numeric is not None:
        try: message = ctypes.FormatError(numeric).strip()
        except Exception: message = ""
    payload = {"status":"FAILED","complete":False,"stage":stage,"error_code":_failure_code(stage, exc),"error":str(exc),"exception_type":type(exc).__name__}
    if numeric is not None: payload["win32_error"] = numeric
    if message: payload["win32_message"] = message
    return payload

def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status":"FAILED","complete":False,"stage":"platform","error_code":"WINDOWS_REQUIRED","error":"runtime_capture_windows.py requires Windows"}), file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser(); ap.add_argument("--authority", type=Path, required=True); ap.add_argument("--out-root", type=Path, required=True); ap.add_argument("--profile", choices=("private","miniplus","full"), default="private"); ap.add_argument("--allowed-agent-root", action="append", required=True); args = ap.parse_args()
    process_handle = None; snapshot = None; stage = "authority_load"
    try:
        record = AuthorityRecord.from_dict(json.loads(args.authority.read_text(encoding="utf-8")))
        stage = "authority_key"; key = load_key(); stage = "authority_signature"; verify_signature(record, key); stage = "authority_static"; validate_static(record, args.allowed_agent_root)
        stage = "winapi_load"; kernel32 = ctypes.WinDLL("kernel32", use_last_error=True); dbghelp = ctypes.WinDLL("Dbghelp", use_last_error=True); configure_apis(kernel32, dbghelp)
        started = time.perf_counter(); started_at = datetime.now(timezone.utc)
        stage = "open_process"; process_handle, image_path, creation_time = open_bound_process(kernel32, record.agent_pid)
        stage = "live_binding_pre"; validate_live_binding(record,observed_pid=record.agent_pid,observed_creation_time_100ns=creation_time,observed_image_path=image_path)
        stage = "nonce_consume"; consume_nonce(args.out_root, record.nonce)
        stage = "pss_capture"; snapshot, clone_handle = capture_snapshot(kernel32, process_handle)
        stage = "pss_release_before_stream"; frc = int(kernel32.PssFreeSnapshot(kernel32.GetCurrentProcess(), snapshot))
        if frc != 0: raise OSError(frc, "PssFreeSnapshot failed before stream")
        snapshot = None
        capture_id = "RTC-" + started_at.strftime("%Y%m%d-%H%M%S-") + record.nonce[:8].upper(); out_dir = args.out_root / capture_id; out_dir.mkdir(parents=True, exist_ok=False)
        stage = "private_pages"; region_count, page_count, stream_truncated, stream_truncate_reason = dump_private_pages(kernel32, process_handle, out_dir)
        if page_count <= 0: raise AuthorityError("PRIVATE_PAGE_STREAM_EMPTY")
        stage = "live_binding_post"
        try:
            image_after, creation_after = query_process_facts(kernel32, process_handle)
            validate_live_binding(record,observed_pid=record.agent_pid,observed_creation_time_100ns=creation_after,observed_image_path=image_after)
            post_capture_binding_lifecycle = "LIVE_EXACT"
        except AuthorityError as exc:
            if str(exc) != "bound testing agent is no longer running": raise
            post_capture_binding_lifecycle = "EXITED_AFTER_SNAPSHOT"
        stage = "manifest"; helper_path = Path(__file__).resolve(); private_path = out_dir / "private-regions.bin"; completed_at = datetime.now(timezone.utc)
        manifest = {"schema":"1.0","capture_id":capture_id,"job_id":record.job_id,"terminal_id":record.terminal_id,"ea_binary_ref":record.ea_binary_ref,"ea_sha256":record.ea_sha256.lower(),"agent_pid":record.agent_pid,"agent_creation_time_100ns":record.agent_creation_time_100ns,"agent_image_path":image_path,"agent_image_sha256":sha256_file(Path(image_path)),"post_capture_binding_lifecycle":post_capture_binding_lifecycle,"profile":args.profile,"capture_started_at":started_at.isoformat().replace("+00:00","Z"),"capture_completed_at":completed_at.isoformat().replace("+00:00","Z"),"capture_duration_ms":int((time.perf_counter()-started)*1000),"helper_version":"1.0.5-r37-low-commit-stream","capture_mode":"PSS_PROOF_PLUS_BOUND_LIVE_STREAM","helper_sha256":sha256_file(helper_path),"dump_sha256":None,"dump_bytes":0,"minidump_status":"OMITTED_DIAGNOSTIC","private_memory_sha256":sha256_file(private_path),"private_memory_bytes":private_path.stat().st_size,"region_count_private":region_count,"private_page_count":page_count,"private_stream_truncated":stream_truncated,"private_stream_truncate_reason":stream_truncate_reason,"private_stream_byte_cap":MAX_PRIVATE_CAPTURE_BYTES,"private_stream_time_cap_seconds":MAX_PRIVATE_CAPTURE_SECONDS,"pss_snapshot_lifecycle":"PROVED_AND_FREED_BEFORE_STREAM","pss_flags":"VA_CLONE","pss_flags_hex":"0x00000001","pss_target_process_access":"0x00001090","complete":True}
        (out_dir / "capture-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"status":"COMPLETED", **manifest}, sort_keys=True)); return 0
    except Exception as exc:
        print(json.dumps(_failure_payload(stage, exc), sort_keys=True), file=sys.stderr); return 1
    finally:
        if snapshot:
            try: kernel32.PssFreeSnapshot(kernel32.GetCurrentProcess(), snapshot)
            except Exception: pass
        if process_handle:
            try: kernel32.CloseHandle(process_handle)
            except Exception: pass

if __name__ == "__main__":
    raise SystemExit(main())
