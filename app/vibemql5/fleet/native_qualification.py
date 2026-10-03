"""Installed operator approval of exact dedicated Windows native controls.

Signature validation proves operator provenance, not the truth of physical evidence.
No request flag, fixture result or environment variable installs this capability.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from types import MappingProxyType

from .project_targets import canonical, read_record, exact_target
from .identity import normalize_path
from .wire import https_origin

DOMAIN = b"fleet.native.operator-approval/1\0"
RUNTIME_DOMAIN = b"fleet.native.runtime/1\0"
CONTROLS = frozenset({"COMPILE_PASS", "COMPILE_FAIL", "TEST_FULL_PERIOD", "WRONG_ROOT", "STALE_TARGET",
                     "CHILD_CONTAINMENT", "PARENT_CRASH", "EXACT_CLEANUP", "NO_BROKER_ESCAPE", "INTERACTIVE_SESSION"})
_SEAL = object()


class QualificationError(RuntimeError):
    def __init__(self):
        self.code = "NATIVE_QUALIFICATION_UNAVAILABLE"
        super().__init__(self.code)


def file_hash(path, maximum=512 * 1024 * 1024):
    path = Path(path)
    try:
        def unsafe():
            return any(part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400) for part in (path, *path.parents))
        if unsafe() or not path.is_file(): raise ValueError()
        result, total = hashlib.sha256(), 0
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > maximum: raise ValueError()
            while True:
                chunk = stream.read(min(1024 * 1024, maximum - total + 1))
                if not chunk: break
                total += len(chunk)
                if total > maximum: raise ValueError()
                result.update(chunk)
            after = os.fstat(stream.fileno())
        metadata = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if total != before.st_size or metadata(before) != metadata(after) or metadata(after) != metadata(path.stat()) or unsafe(): raise ValueError()
        return result.hexdigest()
    except Exception: raise QualificationError() from None


def source_manifest():
    # Capacity, native and SDK gates share the complete installed product bundle.
    from .scoped_resources import capacity_source_manifest
    try: return capacity_source_manifest()
    except Exception: raise QualificationError() from None


def _hash(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _absolute(value):
    return type(value) is str and normalize_path(value) == value


def _integer(value, minimum=1, maximum=(1 << 31) - 1):
    return type(value) is int and minimum <= value <= maximum


def validate_approval(envelope, operator_public_key, *, expected_payload, now_ms):
    """Verify signed metadata and installed files; does not enable an OS driver."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        if type(envelope) is not dict or set(envelope) != {"body", "signature"}: raise ValueError()
        body, signature = envelope["body"], envelope["signature"]
        if not _hash(operator_public_key) or type(signature) is not str or re.fullmatch(r"[a-f0-9]{128}", signature) is None: raise ValueError()
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(operator_public_key)).verify(bytes.fromhex(signature), DOMAIN + canonical(body))
        fields = {"schema", "scope", "approved_at_ms", "expires_at_ms", "payload", "installation", "controls", "policy"}
        if type(body) is not dict or set(body) != fields or body["schema"] != "fleet.native.operator-approval/1" or body["scope"] != "DEDICATED_TESTER_SYNC_OWNED": raise ValueError()
        if not _integer(now_ms, 0, (1 << 63) - 1) or not _integer(body["approved_at_ms"], 0, now_ms) or not _integer(body["expires_at_ms"], now_ms + 1, (1 << 63) - 1): raise ValueError()
        if body["payload"] != expected_payload or not expected_payload: raise ValueError()
        for path, sha in expected_payload.items():
            if not _absolute(path) or not _hash(sha) or file_hash(path) != sha: raise ValueError()
        install = body["installation"]
        fields = {"authority_root", "target", "binding", "metaeditor", "terminal_build", "compiler_build", "binary_hashes",
                  "python", "python_sha256", "windows_build", "session_id", "gateway_public_key", "gateway_audience", "include_root", "agent_root"}
        if type(install) is not dict or set(install) != fields: raise ValueError()
        target = exact_target(install["target"])
        if not _integer(target.get("route_generation")): raise ValueError()
        binding = install["binding"]
        if type(binding) is not dict or set(binding) != {"executable", "data_root"} or not all(_absolute(path) for path in binding.values()): raise ValueError()
        for field in ("authority_root", "metaeditor", "python", "include_root", "agent_root"):
            if not _absolute(install[field]): raise ValueError()
        if not all(_integer(install[field]) for field in ("terminal_build", "compiler_build", "windows_build", "session_id")): raise ValueError()
        if not _hash(install["gateway_public_key"]): raise ValueError()
        https_origin(install["gateway_audience"])
        binaries = install["binary_hashes"]
        if type(binaries) is not dict or set(binaries) != {binding["executable"], install["metaeditor"]}: raise ValueError()
        for path, sha in binaries.items():
            if not _hash(sha) or file_hash(path) != sha: raise ValueError()
        if not _hash(install["python_sha256"]) or file_hash(install["python"]) != install["python_sha256"]: raise ValueError()
        # Resource roots are operator selected and actual observed paths, not aliases.
        for field in ("data_root",):
            if not Path(binding[field]).is_dir(): raise ValueError()
        if not all(Path(install[field]).is_dir() for field in ("include_root", "agent_root")): raise ValueError()
        if Path(install["include_root"]).resolve() != (Path(binding["data_root"]) / "MQL5" / "Include").resolve(): raise ValueError()
        controls = body["controls"]
        if type(controls) is not dict or set(controls) != CONTROLS: raise ValueError()
        evidence_root = Path(install["authority_root"]) / "state" / "fleet" / "native-qualification-evidence"
        for case, receipt in controls.items():
            if type(receipt) is not dict or set(receipt) != {"path", "sha256"} or not _absolute(receipt["path"]) or not _hash(receipt["sha256"]): raise ValueError()
            path = Path(receipt["path"])
            path.resolve().relative_to(evidence_root.resolve())
            if file_hash(path, 262144) != receipt["sha256"]: raise ValueError()
            evidence = read_record(path)
            if (evidence.get("schema") != "fleet.native.control/1" or evidence.get("case") != case
                    or evidence.get("evidence") != "REAL_MT5" or evidence.get("result") != "PASS"
                    or evidence.get("target") != target or evidence.get("payload_sha256") != hashlib.sha256(canonical(expected_payload)).hexdigest()): raise ValueError()
        policy = body["policy"]
        if type(policy) is not dict or set(policy) != {"compile_timeout_seconds", "test_timeout_seconds", "resource_max_records", "resource_wait_ms"}: raise ValueError()
        if not all(_integer(value) for value in policy.values()): raise ValueError()
        return body
    except Exception:
        raise QualificationError() from None


class NativeInstallation:
    def __init__(self, body, seal, operator_public_key, runtime_body=None):
        if seal is not _SEAL: raise QualificationError()
        self._body = body
        self.operator_public_key = operator_public_key
        self.candidate_sha256 = hashlib.sha256(canonical(body["payload"])).hexdigest()
        install = body["installation"]
        runtime = {key: install[key] for key in ("python", "python_sha256", "windows_build", "session_id", "binary_hashes", "terminal_build", "compiler_build")}
        self.runtime_sha256 = hashlib.sha256(canonical(runtime_body if runtime_body is not None else runtime)).hexdigest()
        self.runtime_body = runtime_body
        self.installation = MappingProxyType(body["installation"])
        self.policy = MappingProxyType(body["policy"])


def qualification_path(root, target, *, scoped):
    target = exact_target(target)
    if not scoped: return Path(root) / "state" / "fleet" / "native-qualification.json"
    # Fixed validated identity selection; no directory scan or fallback to another target.
    return Path(root) / "state" / "fleet" / "native-qualifications" / (target["terminal_id"] + "-g" + str(target["terminal_generation"]) + ".json")


def validate_runtime(envelope, operator_public_key, *, root, expected_payload):
    """Verify one common signed physical-runtime roster for every scoped target."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from .resources import physical_resources
        if type(envelope) is not dict or set(envelope) != {"body", "signature"} or not _hash(operator_public_key) or type(envelope["signature"]) is not str or re.fullmatch(r"[a-f0-9]{128}", envelope["signature"]) is None: raise ValueError()
        body = envelope["body"]
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(operator_public_key)).verify(bytes.fromhex(envelope["signature"]), RUNTIME_DOMAIN + canonical(body))
        fields = {"schema", "authority_root", "candidate_sha256", "payload", "python", "python_sha256", "windows_build", "session_id", "terminals"}
        if type(body) is not dict or set(body) != fields or body["schema"] != "fleet.native.runtime/1" or body["authority_root"] != normalize_path(str(Path(root).resolve())) or body["payload"] != expected_payload or body["candidate_sha256"] != hashlib.sha256(canonical(expected_payload)).hexdigest(): raise ValueError()
        if not _absolute(body["python"]) or not _hash(body["python_sha256"]) or file_hash(body["python"]) != body["python_sha256"] or not _integer(body["windows_build"]) or not _integer(body["session_id"]): raise ValueError()
        rows = body["terminals"]
        if type(rows) is not list or not 2 <= len(rows) <= 16: raise ValueError()
        seen, identities, paths = set(), set(), []
        for row in rows:
            required = {"terminal_id", "terminal_generation", "binding", "metaeditor", "binary_hashes", "terminal_build", "compiler_build", "include_root", "agent_root"}
            if type(row) is not dict or set(row) != required or re.fullmatch(r"term_[a-f0-9]{32}", row["terminal_id"]) is None or row["terminal_id"] in seen or not _integer(row["terminal_generation"]): raise ValueError()
            seen.add(row["terminal_id"])
            binding = row["binding"]
            if type(binding) is not dict or set(binding) != {"executable", "data_root"} or not all(_absolute(value) for value in binding.values()): raise ValueError()
            for field in ("metaeditor", "include_root", "agent_root"):
                if not _absolute(row[field]): raise ValueError()
            if not _integer(row["terminal_build"]) or not _integer(row["compiler_build"]): raise ValueError()
            if type(row["binary_hashes"]) is not dict or set(row["binary_hashes"]) != {binding["executable"], row["metaeditor"]}: raise ValueError()
            for path, sha in row["binary_hashes"].items():
                if not _hash(sha) or file_hash(path) != sha: raise ValueError()
            if Path(row["include_root"]).resolve() != (Path(binding["data_root"]) / "MQL5" / "Include").resolve(): raise ValueError()
            resources = {**binding, "include_root": row["include_root"], "agent_root": row["agent_root"]}
            observed = physical_resources(resources)
            editor = Path(row["metaeditor"]).stat()
            keys = {entry["physical_key"] for entry in observed} | {f"{editor.st_dev}:{editor.st_ino}"}
            row_paths = [entry["path"] for entry in observed] + [row["metaeditor"]]
            if identities & keys or any(left == right or left.startswith(right + os.sep) or right.startswith(left + os.sep) for left in row_paths for right in paths): raise ValueError()
            identities.update(keys); paths.extend(row_paths)
        return body
    except Exception: raise QualificationError() from None


def scoped_installation_match(body, runtime):
    """Each per-target approval must match its exact common runtime roster entry."""
    try:
        install = body["installation"]
        if any(install[field] != runtime[field] for field in ("authority_root", "python", "python_sha256", "windows_build", "session_id")): raise ValueError()
        target = install["target"]
        row = next(row for row in runtime["terminals"] if row["terminal_id"] == target["terminal_id"] and row["terminal_generation"] == target["terminal_generation"])
        if any(install[field] != row[field] for field in ("binding", "metaeditor", "binary_hashes", "terminal_build", "compiler_build", "include_root", "agent_root")): raise ValueError()
        return row
    except Exception: raise QualificationError() from None


def binary_build(path):
    """Read actual installed executable FileVersion build through Windows version API."""
    if os.name != "nt": raise QualificationError()
    import ctypes as C
    from ctypes import wintypes as W
    version = C.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes, version.GetFileVersionInfoSizeW.restype = [W.LPCWSTR, C.POINTER(W.DWORD)], W.DWORD
    version.GetFileVersionInfoW.argtypes, version.GetFileVersionInfoW.restype = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p], W.BOOL
    version.VerQueryValueW.argtypes, version.VerQueryValueW.restype = [C.c_void_p, W.LPCWSTR, C.POINTER(C.c_void_p), C.POINTER(W.UINT)], W.BOOL
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size: raise QualificationError()
    buffer = C.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer): raise QualificationError()
    pointer, length = C.c_void_p(), W.UINT()
    if not version.VerQueryValueW(buffer, "\\", C.byref(pointer), C.byref(length)) or length.value < 52: raise QualificationError()
    fields = C.cast(pointer, C.POINTER(W.DWORD))
    if fields[0] != 0xFEEF04BD: raise QualificationError()
    return int(fields[3] >> 16)


def _read_installed(path):
    """Read owner-controlled installed authority through a protected retained fd."""
    descriptor = None
    try:
        from .node_keys import _check
        from .wire import decode_body
        path = Path(path)
        if any(part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400) for part in (path, *path.parents)): raise ValueError()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOINHERIT", 0))
        _check(descriptor)
        before = os.fstat(descriptor)
        if before.st_size > 262144: raise ValueError()
        raw = bytearray()
        while len(raw) <= 262144:
            block = os.read(descriptor, min(65536, 262145 - len(raw)))
            if not block: break
            raw.extend(block)
        _check(descriptor)
        after = os.fstat(descriptor)
        metadata = lambda record: (record.st_dev, record.st_ino, record.st_size, record.st_mtime_ns, record.st_ctime_ns)
        if len(raw) > 262144 or metadata(before) != metadata(after) or metadata(after) != metadata(path.stat()) or path.is_symlink(): raise ValueError()
        return decode_body(bytes(raw), 262144)
    except Exception: raise QualificationError() from None
    finally:
        if descriptor is not None: os.close(descriptor)


def load_installation(root, request, *, now_ms=None):
    """The sole production activation path, fixed installed trust and approval files."""
    try:
        from ..core.tester import TesterDriver
        root = Path(root).resolve()
        trust = _read_installed(root / "config" / "fleet-native-trust.json")
        if type(trust) is not dict or set(trust) != {"schema", "operator_public_key"} or trust["schema"] != "fleet.native.trust/1": raise ValueError()
        target = exact_target(request["placement"]["target"])
        marker = root / "state" / "fleet" / "scoped-install.json"
        scoped = marker.exists() or marker.is_symlink()
        envelope = _read_installed(qualification_path(root, target, scoped=scoped))
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        body = validate_approval(envelope, trust["operator_public_key"], expected_payload=source_manifest(), now_ms=now_ms)
        runtime = None
        if scoped:
            runtime = validate_runtime(_read_installed(root / "state" / "fleet" / "native-runtime.json"), trust["operator_public_key"], root=root, expected_payload=body["payload"])
            scoped_installation_match(body, runtime)
        install, placement = body["installation"], request["placement"]
        if os.name != "nt" or install["authority_root"] != normalize_path(str(root)) or install["python"] != normalize_path(str(Path(sys.executable).resolve())): raise ValueError()
        if install["target"] != placement["target"] or install["binding"] != placement["binding"]: raise ValueError()
        context = TesterDriver._execution_context()
        if context.get("interactive_session") is not True or context.get("session_id") != install["session_id"]: raise ValueError()
        if sys.getwindowsversion().build != install["windows_build"]: raise ValueError()
        if binary_build(install["binding"]["executable"]) != install["terminal_build"] or binary_build(install["metaeditor"]) != install["compiler_build"]: raise ValueError()
        return NativeInstallation(body, _SEAL, trust["operator_public_key"], runtime)
    except Exception:
        raise QualificationError() from None
