"""Signed operator approval of exact real Q2 evidence, not a physical-proof oracle.

No synthetic/harmless evidence creates an executable installation. The operator
trust anchor is local configuration, never request metadata or an approval field.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path
from types import MappingProxyType

from .sdk_protocol import canonical, digest, read_bounded, validate_request, ProtocolError, MAX_EVIDENCE_BYTES

DOMAIN = b"fleet.sdk.operator-approval/1\0"
CONTROL_CASES = frozenset({"LOAD", "ATTACH_A", "ATTACH_B", "STOPPED_A", "STOPPED_B",
    "RACE_A", "RACE_B", "ESCAPE_CHILD", "ESCAPE_BROKER", "PARENT_CRASH",
    "EXACT_CLEANUP", "MATCHED_UNRESTRICTED_CONTROLS"})
RESTRICTIONS = {"appcontainer": 1, "capabilities": 0, "child_policy": 1,
                "integrity_sid": "S-1-16-4096", "inherits_handles": False}
_TOKEN = object()


class QualificationError(RuntimeError):
    def __init__(self):
        super().__init__("LIVE_ATTACH_ONLY_UNPROVEN")


def _read_evidence(path):
    return read_bounded(path, max_bytes=MAX_EVIDENCE_BYTES)


def canonical_path(path):
    return os.path.normcase(str(Path(path).resolve()))


def file_hash(path, *, max_bytes=512 * 1024 * 1024):
    """Hash the exact retained regular file and re-opened pathname identity.

    Windows handle/path stat aliases are not comparable on Python 3.12. Reuse
    the owned Win32 metadata reader; no write/delete sharing or reparse follows.
    """
    from .scoped_resources import _open_retained_read, retained_file_metadata, assert_retained_path
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise QualificationError()
    value, total = hashlib.sha256(), 0
    try:
        with os.fdopen(_open_retained_read(path), "rb") as stream:
            before = retained_file_metadata(stream.fileno())
            if before[2] > max_bytes:
                raise QualificationError()
            while True:
                chunk = stream.read(min(1024 * 1024, max_bytes - total + 1))
                if not chunk: break
                total += len(chunk)
                if total > max_bytes: raise QualificationError()
                value.update(chunk)
            if total != before[2]: raise QualificationError()
            assert_retained_path(path, stream.fileno(), before)
    except OSError:
        raise QualificationError() from None
    return value.hexdigest()


def validate_runtime_acl(sddl, *, profile_sid, trusted_user_sid=None):
    """Conservative filesystem allow-ACE parser: app capability remains read-only.

    Owner/SYSTEM/admin write authority is external to the restricted worker. Unknown
    ACE grammars and write grants to other principals fail closed, even if signed.
    """
    if type(sddl) is not str or not 1 <= len(sddl) <= 8192 or "D:" not in sddl:
        raise QualificationError()
    dacl = sddl.split("D:", 1)[1].split("S:", 1)[0]
    allowed_writers = {"SY", "BA"}
    if trusted_user_sid is not None:
        allowed_writers.add(trusted_user_sid)
    rights_map = {"GA": 0x10000000, "GW": 0x40000000, "GR": 0x80000000, "GX": 0x20000000,
                  "FA": 0x1F01FF, "FW": 0x120116, "FR": 0x120089, "FX": 0x1200A0,
                  "RC": 0x20000, "SD": 0x10000, "WD": 0x40000, "WO": 0x80000}
    write_mask = 0x10000000 | 0x40000000 | 0x10000 | 0x40000 | 0x80000 | 0x2 | 0x4 | 0x10 | 0x100
    matches = list(re.finditer(r"\(([^()]*)\)", dacl))
    if not matches or len(matches) > 64:
        raise QualificationError()
    remainder = re.sub(r"\([^()]*\)", "", dacl)
    if remainder not in ("", "P", "AI", "AR", "PAI", "PAR", "AIAR", "PAIAR"):
        raise QualificationError()
    profile_read = False
    for match in matches:
        fields = match.group(1).split(";")
        if len(fields) != 6 or fields[0] not in {"A", "D"} or fields[3] or fields[4]:
            raise QualificationError()
        rights = fields[2]
        if rights.startswith("0x"):
            if re.fullmatch(r"0x[a-fA-F0-9]{1,8}", rights) is None:
                raise QualificationError()
            mask = int(rights, 16)
        else:
            if len(rights) % 2 or any(rights[i:i+2] not in rights_map for i in range(0, len(rights), 2)):
                raise QualificationError()
            mask = 0
            for i in range(0, len(rights), 2): mask |= rights_map[rights[i:i+2]]
        sid = fields[5]
        if fields[0] == "A" and mask & write_mask and sid not in allowed_writers:
            raise QualificationError()
        if fields[0] == "A" and sid == profile_sid:
            if mask & write_mask:
                raise QualificationError()
            profile_read |= bool(mask & (0x80000000 | 0x1)) and "IO" not in fields[1]
    if not profile_read:
        raise QualificationError()


def payload_manifest():
    """Concrete installed source identities; no caller-supplied hash is trusted."""
    package = Path(__file__).resolve().parents[1]
    paths = sorted(package.rglob("*.py"))
    root = package.parents[1]
    paths += [root / name for name in ("requirements-bootstrap.lock", "pyproject.toml") if (root / name).is_file()]
    return {canonical_path(path): file_hash(path) for path in paths}



def _hashes(value, *, maximum=512):
    if type(value) is not dict or not 1 <= len(value) <= maximum:
        raise QualificationError()
    for path, sha in value.items():
        if (type(path) is not str or not os.path.isabs(path) or canonical_path(path) != path
                or type(sha) is not str or re.fullmatch(r"[a-f0-9]{64}", sha) is None):
            raise QualificationError()
        if file_hash(path) != sha:
            raise QualificationError()


def validate_operator_approval(path, trusted_operator_public_key, expected_payload_manifest, *, now_ms=None):
    """Validate the operator's signed evidence approval, without activating SDK."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        envelope = _read_evidence(path)
        if type(envelope) is not dict or set(envelope) != {"approval", "signature"}:
            raise QualificationError()
        approval, signature = envelope["approval"], envelope["signature"]
        if type(trusted_operator_public_key) is not bytes or len(trusted_operator_public_key) != 32:
            raise QualificationError()
        if type(signature) is not str or re.fullmatch(r"[a-f0-9]{128}", signature) is None:
            raise QualificationError()
        Ed25519PublicKey.from_public_bytes(trusted_operator_public_key).verify(
            bytes.fromhex(signature), DOMAIN + canonical(approval))
        fields = {"schema", "scope", "operations", "approved_at_ms", "expires_at_ms",
                  "payload", "installation", "controls", "summary"}
        if (type(approval) is not dict or set(approval) != fields
                or approval["schema"] != "fleet.sdk.operator-approval/1"
                or approval["scope"] != "REAL_Q2_NO_START_STATE_ACCOUNT"
                or approval["operations"] != ["state", "account"]):
            raise QualificationError()
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        if (type(now_ms) is not int or type(approval["approved_at_ms"]) is not int
                or type(approval["expires_at_ms"]) is not int
                or not 0 <= approval["approved_at_ms"] <= now_ms < approval["expires_at_ms"] <= (1 << 63) - 1):
            raise QualificationError()
        actual_payload = payload_manifest()
        if expected_payload_manifest != actual_payload or approval["payload"] != actual_payload:
            raise QualificationError()
        _hashes(approval["payload"])
        installation = approval["installation"]
        if (type(installation) is not dict or set(installation) != {"platform", "os_build", "session_id",
                "target", "executable", "data_root", "python", "worker", "runtime_files", "restrictions", "runtime_resource_manifest", "profile_name", "profile_sid", "authority_root", "sdk_wheel", "sdk_dll", "python_dll", "scope_authority"}
                or installation["platform"] != "Windows" or type(installation["os_build"]) is not str
                or re.fullmatch(r"[0-9]{1,10}", installation["os_build"]) is None
                or type(installation["session_id"]) is not int or not 0 <= installation["session_id"] <= 0xFFFFFFFF
                or type(installation["restrictions"]) is not dict or installation["restrictions"] != RESTRICTIONS
                or any(type(installation["restrictions"][key]) is not type(expected) for key, expected in RESTRICTIONS.items())):
            raise QualificationError()
        scope = installation["scope_authority"]
        if scope is not None and (type(scope) is not dict
                or set(scope) != {"profile_sha256", "owner_public_key", "candidate_sha256", "runtime_sha256"}
                or any(type(scope[k]) is not str or re.fullmatch(r"[a-f0-9]{64}", scope[k]) is None for k in scope)):
            raise QualificationError()
        if (type(installation["profile_name"]) is not str or re.fullmatch(r"vibemql5\.sdk\.[a-f0-9]{32}", installation["profile_name"]) is None
                or type(installation["profile_sid"]) is not str or re.fullmatch(r"S-1-15-2-(?:[0-9]+-){5,8}[0-9]+", installation["profile_sid"]) is None):
            raise QualificationError()
        for key in ("executable", "data_root", "python", "worker", "authority_root", "sdk_wheel", "sdk_dll", "python_dll"):
            value = installation[key]
            if type(value) is not str or not os.path.isabs(value) or canonical_path(value) != value:
                raise QualificationError()
        if installation["worker"] != canonical_path(Path(__file__).with_name("sdk_worker.py")):
            raise QualificationError()
        _hashes(installation["runtime_files"])
        if not {installation[k] for k in ("python", "executable", "sdk_wheel", "sdk_dll", "python_dll")} <= set(installation["runtime_files"]):
            raise QualificationError()
        _hashes(installation["runtime_resource_manifest"], maximum=1)
        resource = _read_evidence(next(iter(installation["runtime_resource_manifest"])))
        if type(resource) is not dict or set(resource) != {"schema", "resources"} or resource["schema"] != "fleet.sdk.runtime-acl/1":
            raise QualificationError()
        if type(resource["resources"]) is not dict or not 1 <= len(resource["resources"]) <= 512:
            raise QualificationError()
        required_roots = set(actual_payload) | set(installation["runtime_files"]) | {installation["python"], canonical_path(Path(installation["python"]).parent), installation["worker"],
                          installation["executable"], installation["data_root"],
                          installation["authority_root"], canonical_path(Path(__file__).resolve().parents[1]),
                          canonical_path(Path(path).resolve().parent), canonical_path(path),
                          canonical_path(Path(installation["authority_root"]) / "state" / "concurrency")}
        if scope is not None:
            required_roots.add(canonical_path(Path(installation["authority_root"]) / "state" / "fleet"))
            required_roots |= {canonical_path(Path(installation["authority_root"]) / "state" / "fleet" / name)
                for name in ("scoped-install.json", "scoped-resources.sqlite", "scoped-resources.guard.lock")}
        else:
            required_roots |= {canonical_path(Path(installation["authority_root"]) / "state" / "concurrency" / name)
                for name in ("native-ownership-install.json", "native-ownership.json", ".native-ownership.lock")}
        required_roots |= {canonical_path(Path(file).parent) for file in required_roots}
        if not required_roots <= set(resource["resources"]):
            raise QualificationError()
        for root, descriptor in resource["resources"].items():
            if (type(root) is not str or not os.path.isabs(root) or canonical_path(root) != root
                    or type(descriptor) is not str or not 1 <= len(descriptor) <= 8192):
                raise QualificationError()
        controls = approval["controls"]
        if type(controls) is not dict or set(controls) != CONTROL_CASES:
            raise QualificationError()
        candidate = digest({"payload": actual_payload, "installation": installation})
        for case, record in controls.items():
            if type(record) is not dict or set(record) != {"path", "sha256"}:
                raise QualificationError()
            _hashes({record["path"]: record["sha256"]}, maximum=1)
            raw = _read_evidence(record["path"])
            if (type(raw) is not dict or set(raw) != {"schema", "case", "evidence", "outcome", "candidate_sha256", "raw_artifacts"}
                    or raw["schema"] != "fleet.sdk.q2.control/1" or raw["case"] != case
                    or raw["evidence"] != "REAL_Q2" or raw["outcome"] != "PASS"
                    or raw["candidate_sha256"] != candidate):
                raise QualificationError()
            _hashes(raw["raw_artifacts"])
        _hashes(approval["summary"], maximum=1)
        summary = _read_evidence(next(iter(approval["summary"])))
        if (type(summary) is not dict or set(summary) != {"schema", "evidence", "candidate_sha256", "cases"}
                or summary["schema"] != "fleet.sdk.q2.summary/1" or summary["evidence"] != "REAL_Q2"
                or summary["candidate_sha256"] != candidate or summary["cases"] != sorted(CONTROL_CASES)):
            raise QualificationError()
        # Target grammar is shared with the actual worker, not a separate permissive parser.
        target = installation["target"]
        template = {"schema": "fleet.sdk.read.request/1", "operation": "state", "nonce": "0" * 32,
            "target": target, "qualification_sha256": digest(approval), "budget_ms": 10000, "scope": None,
            "owner": {"epoch": "qualification", "generation": 1, "token": "qualification", "parent": {"pid": 1, "creation": "1", "image": installation["python"]}, "operation_id": "qualification", "kind": "qualification"},
            "binding": {"executable": installation["executable"], "data_root": installation["data_root"],
                        "alias": "QUALIFICATION", "process": {"pid": 1, "creation": "1", "image": installation["executable"]}}}
        validate_request(template)
        if target.get("route_generation") is not None:
            raise QualificationError()  # Gateway routing is not local installation qualification.
        return approval
    except QualificationError:
        raise
    except Exception:
        raise QualificationError() from None


class QualifiedSdkInstallation:
    __slots__ = ("_approval", "_path", "_key", "_sha")

    def __init__(self, approval, path, key, *, _token=None):
        if _token is not _TOKEN:
            raise QualificationError()
        self._approval = canonical(approval)
        self._path, self._key, self._sha = Path(path).resolve(), key, digest(approval)

    @classmethod
    def from_operator_manifest(cls, path, trusted_operator_public_key, expected_payload_manifest):
        approval = validate_operator_approval(path, trusted_operator_public_key, expected_payload_manifest)
        cls._host(approval["installation"])
        installation = cls(approval, path, trusted_operator_public_key, _token=_TOKEN)
        installation.assert_current_scope()
        return installation

    @staticmethod
    def _host(installation):
        if os.name != "nt" or str(sys.getwindowsversion().build) != installation["os_build"]:
            raise QualificationError()
        import ctypes
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.ProcessIdToSessionId.argtypes = [W.DWORD, ctypes.POINTER(W.DWORD)]
        kernel.ProcessIdToSessionId.restype = W.BOOL
        session = W.DWORD()
        if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)) or session.value != installation["session_id"]:
            raise QualificationError()
        from ..core.isolated_sdk import Windows
        windows = Windows()
        resource = _read_evidence(next(iter(installation["runtime_resource_manifest"])))
        for path, sddl in resource["resources"].items():
            observed = windows.security_observation(path)
            if observed.get("sddl") != sddl or observed.get("selected_label_descriptor", {}).get("truncated"):
                raise QualificationError()
            validate_runtime_acl(sddl, profile_sid=installation["profile_sid"], trusted_user_sid=windows.user_sid())

    @property
    def sha256(self):
        return self._sha

    @property
    def approval_path(self):
        return self._path

    @property
    def operator_public_key(self):
        return self._key

    @property
    def installation(self):
        import json
        return MappingProxyType(json.loads(self._approval)["installation"])

    def assert_current(self):
        approval = validate_operator_approval(self._path, self._key, payload_manifest())
        if digest(approval) != self._sha:
            raise QualificationError()
        self._host(approval["installation"])
        self.assert_current_scope()

    def assert_current_scope(self):
        """Read-only scope approval check suitable for the restricted worker."""
        fixed = self.installation
        approved = fixed["scope_authority"]
        if approved is None:
            marker = Path(fixed["authority_root"]) / "state" / "fleet" / "scoped-install.json"
            if marker.exists() or marker.is_symlink():
                raise QualificationError()
            return
        from .scoped_resources import assert_installed_sdk_scope_profile
        try:
            assert_installed_sdk_scope_profile(fixed["authority_root"], device_id=fixed["target"]["device_id"],
                trusted_owner_public_key=approved["owner_public_key"], expected_profile_sha256=approved["profile_sha256"],
                expected_candidate_sha256=approved["candidate_sha256"], expected_runtime_sha256=approved["runtime_sha256"])
        except Exception:
            raise QualificationError() from None

    def scope_coordinator(self):
        """Reopen signed installed scope authority; never silently change namespace."""
        fixed = self.installation
        marker = Path(fixed["authority_root"]) / "state" / "fleet" / "scoped-install.json"
        approved = fixed["scope_authority"]
        if approved is None:
            if marker.exists() or marker.is_symlink():
                raise QualificationError()
            return None
        from .scoped_resources import ScopedResourceCoordinator
        try:
            coordinator = ScopedResourceCoordinator.open_installed(fixed["authority_root"],
                device_id=fixed["target"]["device_id"], trusted_owner_public_key=approved["owner_public_key"],
                candidate_sha256=approved["candidate_sha256"], runtime_sha256=approved["runtime_sha256"])
            if (coordinator is None or coordinator.evidence != "SIGNED_PHYSICAL_CAPACITY_PROFILE"
                    or coordinator.profile_sha256 != approved["profile_sha256"]):
                raise QualificationError()
            return coordinator
        except Exception:
            raise QualificationError() from None

    def assert_request(self, request):
        validate_request(request)
        self.assert_current()
        fixed = self.installation
        target = {key: value for key, value in request["target"].items() if key != "route_generation"}
        expected = {key: value for key, value in fixed["target"].items() if key != "route_generation"}
        if (request["qualification_sha256"] != self.sha256 or target != expected
                or request["binding"]["executable"] != fixed["executable"]
                or request["binding"]["data_root"] != fixed["data_root"]):
            raise QualificationError()
        scope = request["scope"]
        if ((fixed["scope_authority"] is None) != (scope is None)
                or (scope is not None and scope["profile_sha256"] != fixed["scope_authority"]["profile_sha256"])):
            raise QualificationError()

    def assert_restrictions(self, actual):
        if (type(actual) is not dict or actual.get("appcontainer") != 1
                or type(actual.get("appcontainer")) is not int or actual.get("capabilities") != 0
                or type(actual.get("capabilities")) is not int or actual.get("integrity_sid") != "S-1-16-4096"
                or type(actual.get("child_policy_flags")) is not int or actual["child_policy_flags"] != 1
                or actual.get("inherits_handles") is not False
                or actual.get("appcontainer_sid") != self.installation["profile_sid"]):
            raise QualificationError()

    def assert_worker(self, request):
        self.assert_request(request)
        from ..core.native_ownership import OwnershipAuthority, current_identity
        if request["scope"] is not None:
            from .scoped_resources import observe_bound_sdk_scope
            approved = self.installation["scope_authority"]
            state = observe_bound_sdk_scope(self.installation["authority_root"], request["scope"],
                request["owner"]["parent"], current_identity(),
                trusted_owner_public_key=approved["owner_public_key"],
                expected_profile_sha256=approved["profile_sha256"],
                expected_candidate_sha256=approved["candidate_sha256"],
                expected_runtime_sha256=approved["runtime_sha256"])
            if (any(state[k] != request["owner"][k] for k in ("epoch", "generation", "token", "operation_id", "parent"))
                    or state["request"]["kind"] != request["owner"]["kind"]):
                raise QualificationError()
            return
        state = OwnershipAuthority(Path(self.installation["authority_root"])).load()
        if (state["phase"] != "BOUND" or state["disposition"] != "ACTIVE"
                or state["worker"] != current_identity()
                or any(state[k] != request["owner"][k] for k in request["owner"])):
            raise QualificationError()


def main(argv=None):
    """Explicit later-operator CLI; no key generation, SDK import or process effect."""
    import argparse
    parser = argparse.ArgumentParser(description="Validate/sign exact operator SDK evidence approval")
    sub = parser.add_subparsers(dest="operation", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("approval", type=Path)
    validate.add_argument("--public-key", type=Path, required=True)
    sign = sub.add_parser("sign")
    sign.add_argument("unsigned_approval", type=Path)
    sign.add_argument("--private-key", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    written = False
    try:
        if args.operation == "validate":
            with args.public_key.open("rb") as stream:
                key = stream.read(33)
            validate_operator_approval(args.approval, key, payload_manifest())
            print("OPERATOR_APPROVAL_VALIDATED_NO_SDK_ACTIVATION")
        else:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from .sdk_protocol import write_bounded
            with args.private_key.open("rb") as stream:
                private_bytes = stream.read(33)
            if len(private_bytes) != 32:
                raise QualificationError()
            key = Ed25519PrivateKey.from_private_bytes(private_bytes)
            approval = _read_evidence(args.unsigned_approval)
            envelope = {"approval": approval, "signature": key.sign(DOMAIN + canonical(approval)).hex()}
            # No output overwrite and no persistent invalid approval on validation failure.
            write_bounded(args.output, envelope, max_bytes=MAX_EVIDENCE_BYTES)
            written = True
            validate_operator_approval(args.output, key.public_key().public_bytes_raw(), payload_manifest())
            print("OPERATOR_APPROVAL_SIGNED_NO_SDK_ACTIVATION")
        return 0
    except Exception:
        if written:
            try:
                args.output.unlink()
            except OSError:
                pass
        print("LIVE_ATTACH_ONLY_UNPROVEN")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
