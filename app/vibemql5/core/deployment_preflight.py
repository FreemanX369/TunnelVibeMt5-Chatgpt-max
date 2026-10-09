"""Finite read-only observations, never ownership admission or host qualification."""
from __future__ import annotations

from importlib import metadata
import json
import os
from pathlib import Path
import re
import stat
import sys

from .native_ownership import OwnershipAuthority, OwnershipBlocked
from .provenance import sha256_bytes

RECORD_LIMIT = 64 * 1024
SOURCE_LIMIT = 1024 * 1024


def _facts(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _unsafe(value):
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & 0x400)


def _parents(path):
    facts = []
    for parent in path.parents:
        try:
            value = parent.lstat()
        except FileNotFoundError:
            continue
        if _unsafe(value) or not stat.S_ISDIR(value.st_mode):
            raise ValueError("UNSAFE_PATH")
        facts.append((parent, _facts(value)))
    return facts


def _presence(path):
    """Scoped installation is only a presence fence; never open its contents."""
    try:
        parents = _parents(path)
        try:
            value = path.lstat()
        except FileNotFoundError:
            return {"status": "MISSING", "parents": parents}
        if _unsafe(value) or not stat.S_ISREG(value.st_mode):
            return {"status": "UNSAFE_PATH"}
        return {"status": "PRESENT", "facts": _facts(value), "parents": parents}
    except ValueError:
        return {"status": "UNSAFE_PATH"}
    except OSError:
        return {"status": "READ_FAILED"}


def _handle_facts(descriptor):
    if os.name != "nt":
        return _facts(os.fstat(descriptor))
    # CPython Windows path/fd stat IDs use different representations. Compare
    # retained and fresh path handles through the same read-only Win32 API.
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    class Information(C.Structure):
        _fields_ = [("attributes", W.DWORD), ("created", W.FILETIME),
                    ("accessed", W.FILETIME), ("written", W.FILETIME),
                    ("volume", W.DWORD), ("size_high", W.DWORD), ("size_low", W.DWORD),
                    ("links", W.DWORD), ("index_high", W.DWORD), ("index_low", W.DWORD)]
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileType.argtypes, kernel.GetFileType.restype = [W.HANDLE], W.DWORD
    kernel.GetFileInformationByHandle.argtypes = [W.HANDLE, C.POINTER(Information)]
    kernel.GetFileInformationByHandle.restype = W.BOOL
    handle = W.HANDLE(msvcrt.get_osfhandle(descriptor))
    info = Information()
    if (kernel.GetFileType(handle) != 1 or not kernel.GetFileInformationByHandle(handle, C.byref(info))
            or info.attributes & 0x410 or not (info.index_high or info.index_low)):
        raise OSError("FILE_IDENTITY_UNAVAILABLE")
    return (info.volume, info.index_high, info.index_low, info.attributes,
            info.size_high, info.size_low, info.written.dwHighDateTime, info.written.dwLowDateTime)


def _snapshot(path, limit):
    """Capped reads of fixed paths; retain no content in the public observation."""
    try:
        parents = _parents(path)
        try:
            before = path.lstat()
        except FileNotFoundError:
            return {"status": "MISSING"}
        if _unsafe(before) or not stat.S_ISREG(before.st_mode):
            return {"status": "UNSAFE_PATH"}
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            held = _handle_facts(stream.fileno())
            if os.name != "nt" and held != _facts(before):
                return {"status": "CHANGED"}
            data = stream.read(limit + 1)
            if held != _handle_facts(stream.fileno()):
                return {"status": "CHANGED"}
            if os.name == "nt":
                # Retain the first lifetime handle until path identity readback.
                current = os.open(path, flags)
                try:
                    if held != _handle_facts(current):
                        return {"status": "CHANGED"}
                finally:
                    os.close(current)
            if (_facts(before) != _facts(path.lstat())
                    or any(_facts(parent.lstat()) != facts for parent, facts in parents)):
                return {"status": "CHANGED"}
        if len(data) > limit:
            return {"status": "TOO_LARGE"}
        return {"status": "PRESENT", "data": data, "sha256": sha256_bytes(data),
                "bytes": len(data), "facts": held}
    except FileNotFoundError:
        return {"status": "CHANGED"}
    except ValueError:
        return {"status": "UNSAFE_PATH"}
    except OSError:
        return {"status": "READ_FAILED"}


def _public(snapshot):
    return {key: snapshot[key] for key in ("status", "sha256", "bytes") if key in snapshot}


def _passes(paths, limit, *, presence_names=()):
    def read(name, path):
        return _presence(path) if name in presence_names else _snapshot(path, limit)
    first = {name: read(name, path) for name, path in paths.items()}
    second = {name: read(name, path) for name, path in paths.items()}
    concurrent = first != second or any(row["status"] == "CHANGED" for row in second.values())
    return second, concurrent


def _object(snapshot):
    return json.loads(snapshot["data"].decode("utf-8"))


def _ownership(root):
    authority = OwnershipAuthority(root)
    paths = {"installation": authority.marker_path, "authority": authority.path,
             "scoped_installation": Path(root) / "state" / "fleet" / "scoped-install.json"}
    snapshots, concurrent = _passes(paths, RECORD_LIMIT, presence_names=("scoped_installation",))
    result = {"observation": "OBSERVED", "reason_code": None,
              "consistency": "TWO_PASSES_NON_ATOMIC_NO_LOCK",
              "evidence_scope": "SNAPSHOT_ONLY_NOT_ADMISSION_OR_QUALIFICATION",
              "files": {name: _public(row) for name, row in snapshots.items()}}
    if concurrent:
        return {**result, "observation": "CONCURRENT", "reason_code": "SNAPSHOT_CHANGED"}
    if any(row["status"] not in {"PRESENT", "MISSING"} for row in snapshots.values()):
        return {**result, "observation": "INCOMPLETE", "reason_code": "SNAPSHOT_UNAVAILABLE"}
    try:
        if snapshots["scoped_installation"]["status"] == "PRESENT":
            raise OwnershipBlocked("SCOPED_OWNERSHIP_REQUIRED")
        if snapshots["installation"]["status"] == "MISSING":
            raise OwnershipBlocked("INSTALL_MISSING")
        try:
            marker = _object(snapshots["installation"])
        except (ValueError, UnicodeError, RecursionError):
            raise OwnershipBlocked("INSTALL_INVALID") from None
        authority.validate_marker(marker)
        if snapshots["authority"]["status"] == "MISSING":
            raise OwnershipBlocked("AUTHORITY_MISSING")
        try:
            state = _object(snapshots["authority"])
        except (ValueError, UnicodeError, RecursionError):
            raise OwnershipBlocked("AUTHORITY_INVALID") from None
        state = authority.validate_snapshot(marker, state)
        result.update(disposition=state["disposition"], phase=state["phase"], generation=state["generation"])
        result["reason_code"] = "OBSERVED_CLOSED" if state["disposition"] == "CLOSED" else "ACTIVE_RECOVERY_REQUIRED"
    except OwnershipBlocked as error:
        result["reason_code"] = error.reason
    return result


def _package(name, minimum, maximum, constraint):
    result = {"observation": "UNEVALUATED", "version": None, "constraint": constraint,
              "constraint_observation": "UNKNOWN", "evidence_scope": "DISTRIBUTION_METADATA_ONLY"}
    try:
        version = metadata.version(name)
    except metadata.PackageNotFoundError:
        return {**result, "observation": "MISSING", "reason_code": "METADATA_MISSING"}
    except Exception:
        return {**result, "reason_code": "METADATA_READ_FAILED"}
    if not isinstance(version, str) or len(version) > 128 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version):
        return {**result, "reason_code": "VERSION_FORMAT_NOT_EVALUATED"}
    release = tuple(int(part) for part in version.split("."))
    result.update(observation="OBSERVED", version=version, reason_code="NORMAL_RELEASE_METADATA",
                  constraint_observation="IN_RANGE" if minimum <= release < maximum else "OUT_OF_RANGE")
    return result


def deployment_preflight(root):
    """Observe fixed records and package metadata; no locks, initialization or effects."""
    package = Path(__file__).parent.parent
    paths = {"observer": Path(__file__), "ownership_validator": Path(__file__).with_name("native_ownership.py"),
             "source_hash_helper": Path(__file__).with_name("provenance.py"), "mcp_adapter": package / "adapters" / "mcp.py"}
    source, changed = _passes(paths, SOURCE_LIMIT)
    python = tuple(sys.version_info[:3])
    return {"schema": "deployment.preflight/1", "scope": "READ_ONLY_OBSERVATION",
            "physical_qualification": "NOT_RUN", "activation": "NOT_QUALIFIED", "ownership": _ownership(Path(root)),
            "runtime_metadata": {"python": {"version": ".".join(map(str, python)), "constraint": ">=3.12,<3.13",
                "constraint_observation": "IN_RANGE" if (3, 12) <= python < (3, 13) else "OUT_OF_RANGE",
                "evidence_scope": "EXECUTING_INTERPRETER_VERSION_ONLY"},
                "mcp": _package("mcp", (2, 1), (3,), ">=2.1,<3"),
                "cryptography": _package("cryptography", (50,), (51,), ">=50,<51")},
            "source_identity": {"evidence_scope": "CURRENT_ON_DISK_NOT_LOADED_CODE_IDENTITY",
                "consistency": "TWO_PASSES_NON_ATOMIC_NO_LOCK", "observation": "CONCURRENT" if changed else
                    "OBSERVED" if all(row["status"] == "PRESENT" for row in source.values()) else "INCOMPLETE",
                "files": {name: _public(row) for name, row in source.items()}}}
