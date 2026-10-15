"""Qualified terminal-scoped resource/producer authority.

No production marker is created by startup. Installing a signed profile is an
explicit quiet migration. Synthetic profiles never install that marker.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import os
import ntpath
import re
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..core.concurrency import ConcurrencyManager
from ..core.jobs import _exclusive_file_lock, _publish_json_exclusive
from ..core.native_ownership import OwnershipAuthority, ObservedProcess, current_identity, _identity_valid
from .job_journal import JournalError, canonical, digest, _decode, _id, _integer
from .resources import physical_resources, KINDS, RESOURCE_FIELDS

DOMAIN = b"fleet.capacity-profile/1\n"
_FIXTURE = object()
_LEASE = object()
_ROSTER = object()
CONFLICT_MATRIX = {kind: {"uses": sorted(RESOURCE_FIELDS), "per_node_serial": kind == "ipc"} for kind in sorted(KINDS)}


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise JournalError("SCOPED_PROFILE_INVALID")


def _relative(root, relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or relative.startswith("/") or any(p in {"", ".", ".."} for p in relative.split("/"))):
        raise JournalError("SCOPED_PROFILE_INVALID")
    path = Path(root) / relative
    if path.is_symlink(): raise JournalError("SCOPED_PROFILE_INVALID")
    try:
        path.resolve(strict=True).relative_to(Path(root).resolve())
    except (OSError, ValueError):
        raise JournalError("SCOPED_PROFILE_INVALID") from None
    return path


def _open_retained_read(path):
    """One read-only regular file; no final symlink/reparse redirection."""
    path = Path(path)
    if path.is_symlink(): raise OSError()
    if os.name != "nt":
        return os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    if any(getattr(part.lstat(), "st_file_attributes", 0) & 0x400 for part in (path, *path.parents)):
        raise OSError()
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [W.HANDLE], W.BOOL
    # No write/delete sharing keeps the short bounded read immutable. Scoped
    # transactions checkpoint and close their DB before the worker reads it.
    handle = kernel.CreateFileW(str(path.absolute()), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle == C.c_void_p(-1).value: raise C.WinError(C.get_last_error())
    try:
        return msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
    except BaseException:
        kernel.CloseHandle(handle); raise


def retained_file_metadata(fd):
    """Stable identity/size/times from the retained file, not host stat aliases."""
    if os.name != "nt":
        record = os.fstat(fd)
        if not stat.S_ISREG(record.st_mode): raise OSError()
        return (record.st_dev, record.st_ino, record.st_size, record.st_mtime_ns, record.st_ctime_ns)
    import ctypes as C
    from ctypes import wintypes as W
    import msvcrt
    class FileId(C.Structure):
        _fields_ = [("volume", C.c_ulonglong), ("identifier", C.c_ubyte * 16)]
    class Basic(C.Structure):
        _fields_ = [("creation", C.c_longlong), ("access", C.c_longlong), ("write", C.c_longlong),
                    ("change", C.c_longlong), ("attributes", W.DWORD)]
    class Standard(C.Structure):
        _fields_ = [("allocation", C.c_longlong), ("size", C.c_longlong), ("links", W.DWORD),
                    ("delete_pending", C.c_ubyte), ("directory", C.c_ubyte)]
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileInformationByHandleEx.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]
    kernel.GetFileInformationByHandleEx.restype = W.BOOL
    handle = msvcrt.get_osfhandle(fd)
    identity, basic, standard = FileId(), Basic(), Standard()
    for kind, record in ((18, identity), (0, basic), (1, standard)):
        if not kernel.GetFileInformationByHandleEx(handle, kind, C.byref(record), C.sizeof(record)):
            raise C.WinError(C.get_last_error())
    if basic.attributes & (0x10 | 0x400) or standard.directory or standard.delete_pending or standard.size < 0:
        raise OSError()
    return (identity.volume, bytes(identity.identifier), standard.size, basic.write, basic.change, basic.creation, basic.attributes)


def assert_retained_path(path, fd, expected):
    """Reopen the current name while retaining its original read handle."""
    if retained_file_metadata(fd) != expected: raise OSError()
    current = _open_retained_read(path)
    try:
        if retained_file_metadata(current) != expected: raise OSError()
    finally:
        os.close(current)


def _read_bounded(path, maximum):
    try:
        with os.fdopen(_open_retained_read(path), "rb") as stream:
            before = retained_file_metadata(stream.fileno())
            if before[2] > maximum: raise OSError()
            raw = stream.read(maximum + 1)
            if len(raw) > maximum or len(raw) != before[2]: raise OSError()
            assert_retained_path(path, stream.fileno(), before)
        return raw
    except OSError: raise JournalError("SCOPED_INPUT_INVALID") from None


def capacity_source_manifest():
    """Same full product bundle keys as the SDK qualification manifest."""
    package = Path(__file__).resolve().parents[1]
    paths = sorted(package.rglob("*.py"))
    project = package.parents[1]
    paths += [project / name for name in ("requirements-bootstrap.lock", "pyproject.toml") if (project / name).is_file()]
    if len(paths) > 512: raise JournalError("SCOPED_SOURCE_UNPROVEN")
    manifest, total = {}, 0
    for path in paths:
        raw = _read_bounded(path, 2 * 1024 * 1024); total += len(raw)
        if total > 16 * 1024 * 1024: raise JournalError("SCOPED_SOURCE_UNPROVEN")
        manifest[os.path.normcase(str(path.resolve()))] = hashlib.sha256(raw).hexdigest()
    return manifest


def _portable_source_bundle(manifest):
    """Compare the full product bundle across configured Windows/Linux roots."""
    result = {}
    for path, sha in manifest.items():
        pieces = path.replace("\\", "/").split("/")
        if "vibemql5" in pieces:
            index = len(pieces) - 1 - pieces[::-1].index("vibemql5")
            key = "/".join(pieces[index:])
        elif pieces[-1] in {"pyproject.toml", "requirements-bootstrap.lock"}:
            key = pieces[-1]
        else:
            raise JournalError("SCOPED_SOURCE_UNPROVEN")
        if key in result: raise JournalError("SCOPED_SOURCE_UNPROVEN")
        result[key] = sha
    return result


def _profile(profile, root, *, physical, observe=True):
    required = {"schema", "device_id", "install_epoch", "capacity", "candidate_sha256", "runtime_sha256",
                "source_manifest", "terminals", "load_receipt", "closure_receipt", "max_records", "lock_wait_ms", "conflict_matrix"}
    if (not isinstance(profile, dict) or set(profile) != required or profile["schema"] != "fleet.capacity-profile/1"
            or len(canonical(profile)) > 262144):
        raise JournalError("SCOPED_PROFILE_INVALID")
    _id(profile["device_id"], "dev_"); _sha(profile["candidate_sha256"]); _sha(profile["runtime_sha256"])
    if not isinstance(profile["install_epoch"], str) or re.fullmatch(r"[a-f0-9]{32}", profile["install_epoch"]) is None:
        raise JournalError("SCOPED_PROFILE_INVALID")
    for key in ("capacity", "max_records", "lock_wait_ms"): _integer(profile[key])
    if not 2 <= profile["capacity"] <= 16 or profile["max_records"] > 100000 or profile["lock_wait_ms"] > 60000:
        raise JournalError("SCOPED_PROFILE_INVALID")
    if not isinstance(profile["terminals"], list) or not profile["capacity"] <= len(profile["terminals"]) <= 64:
        raise JournalError("SCOPED_PROFILE_INVALID")
    seen = set()
    if profile["conflict_matrix"] != CONFLICT_MATRIX: raise JournalError("SCOPED_CONFLICT_MATRIX_INVALID")
    for row in profile["terminals"]:
        if not isinstance(row, dict) or set(row) != {"terminal_id", "terminal_generation", "resources", "physical_identities"}:
            raise JournalError("SCOPED_PROFILE_INVALID")
        _id(row["terminal_id"], "term_"); _integer(row["terminal_generation"])
        if row["terminal_id"] in seen: raise JournalError("SCOPED_PROFILE_INVALID")
        seen.add(row["terminal_id"])
        if not isinstance(row["resources"], dict) or set(row["resources"]) != RESOURCE_FIELDS:
            raise JournalError("SCOPED_PROFILE_INVALID")
        for value in row["resources"].values():
            if not isinstance(value, str) or len(value) > 32768 or not (os.path.isabs(value) or ntpath.isabs(value)):
                raise JournalError("SCOPED_PROFILE_INVALID")
        if (not isinstance(row["physical_identities"], list) or len(row["physical_identities"]) != 4
                or {p["kind"] for p in row["physical_identities"]} != RESOURCE_FIELDS):
            raise JournalError("SCOPED_PROFILE_INVALID")
        for observed in row["physical_identities"]:
            if (set(observed) != {"kind", "path", "physical_key"} or not isinstance(observed["path"], str)
                    or re.fullmatch(r"[0-9]+:[0-9]+", observed["physical_key"]) is None):
                raise JournalError("SCOPED_PROFILE_INVALID")
        if observe and physical_resources(row["resources"]) != row["physical_identities"]:
            raise JournalError("SCOPED_PHYSICAL_BINDING_CHANGED")
    if physical:
        if (not isinstance(profile["source_manifest"], dict) or profile["source_manifest"] != capacity_source_manifest()
                or profile["candidate_sha256"] != digest(profile["source_manifest"])):
            raise JournalError("SCOPED_SOURCE_UNPROVEN")
        roster_sha = digest(profile["terminals"])
        for field, schema in (("load_receipt", "fleet.capacity-load/1"), ("closure_receipt", "fleet.capacity-closure/1")):
            entry = profile[field]
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
                raise JournalError("SCOPED_PHYSICAL_QUALIFICATION_UNPROVEN")
            _sha(entry["sha256"])
            raw = _read_bounded(_relative(root, entry["path"]), 65536)
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise JournalError("SCOPED_PHYSICAL_QUALIFICATION_UNPROVEN")
            receipt = _decode(raw)
            if (receipt.get("schema") != schema or receipt.get("qualification") != "PHYSICAL_WINDOWS"
                    or any(receipt.get(k) != profile[k] for k in ("candidate_sha256", "runtime_sha256", "device_id", "install_epoch", "capacity"))
                    or receipt.get("terminal_roster_sha256") != roster_sha):
                raise JournalError("SCOPED_PHYSICAL_QUALIFICATION_UNPROVEN")
            if field == "load_receipt":
                for name in ("memory_bytes", "cpu_basis_points", "p95_phase_ms"):
                    measured, limit = receipt.get("measured", {}).get(name), receipt.get("limits", {}).get(name)
                    _integer(measured, positive=False); _integer(limit)
                    if measured > limit: raise JournalError("SCOPED_LOAD_LIMIT_FAILED")
                _integer(receipt.get("duration_ms")); _integer(receipt.get("completed_jobs"))
            elif receipt.get("descendant_boundary") not in {"WINDOWS_JOB_KILL_ON_CLOSE_VERIFIED", "EXACT_DESCENDANTS_EXITED"}:
                raise JournalError("SCOPED_CLOSURE_UNPROVEN")
    return copy.deepcopy(profile)


class ScopedResourceCoordinator:
    def __init__(self, root, profile, *, initialize=False, fixture=None, _evidence="SYNTHETIC_SCOPE_ONLY"):
        if fixture is not _FIXTURE:
            raise JournalError("SCOPED_PROFILE_UNVERIFIED")
        if _evidence not in {"SYNTHETIC_SCOPE_ONLY", "SIGNED_PHYSICAL_CAPACITY_PROFILE"}:
            raise JournalError("SCOPED_PROFILE_UNVERIFIED")
        self.root, self.profile = Path(root).resolve(), copy.deepcopy(profile)
        self.profile_sha256 = digest(profile)
        self.evidence = _evidence
        self.path = self.root / "state" / "fleet" / "scoped-resources.sqlite"
        self.guard = self.path.with_suffix(".guard.lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(self.guard, timeout_seconds=profile["lock_wait_ms"] / 1000):
            if initialize == self.path.exists(): raise JournalError("SCOPED_STORE_EXISTS" if initialize else "SCOPED_STORE_MISSING")
            db = self._db()
            try:
                if initialize:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("CREATE TABLE meta (schema TEXT, profile_sha256 TEXT)")
                    db.execute("INSERT INTO meta VALUES (?,?)", ("fleet.scoped-authority/1", self.profile_sha256))
                    db.execute("CREATE TABLE reservations (ticket INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT UNIQUE, record TEXT)")
                    db.execute("COMMIT")
                self._validate(db)
            finally: db.close()

    @classmethod
    def _for_fixture(cls, root, profile, *, initialize=False):
        profile = _profile(profile, root, physical=False)
        return cls(root, profile, initialize=initialize, fixture=_FIXTURE)

    @classmethod
    def open_installed(cls, root, *, device_id, trusted_owner_public_key, candidate_sha256, runtime_sha256):
        root = Path(root).resolve(); marker = root / "state" / "fleet" / "scoped-install.json"
        if not marker.exists() and not marker.is_symlink(): return None
        try:
            if marker.is_symlink(): raise ValueError()
            raw = _read_bounded(marker, 262144)
            signed = _decode(raw)
            if set(signed) != {"body", "signature"}: raise ValueError()
            _sha(trusted_owner_public_key)
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_owner_public_key)).verify(
                bytes.fromhex(signed["signature"]), DOMAIN + canonical(signed["body"]))
            profile = _profile(signed["body"], root, physical=True)
            if (profile["device_id"] != device_id or profile["candidate_sha256"] != candidate_sha256
                    or profile["runtime_sha256"] != runtime_sha256): raise ValueError()
            result = cls(root, profile, fixture=_FIXTURE, _evidence="SIGNED_PHYSICAL_CAPACITY_PROFILE")
            result._trust = {"device_id": device_id, "trusted_owner_public_key": trusted_owner_public_key,
                             "candidate_sha256": candidate_sha256, "runtime_sha256": runtime_sha256}
            return result
        except (ValueError, KeyError, TypeError, OSError, InvalidSignature):
            raise JournalError("SCOPED_INSTALL_INVALID") from None

    @classmethod
    def install(cls, root, signed_profile, **trusted):
        """Explicit quiet installation; never called by native/SDK startup."""
        root = Path(root).resolve(); marker = root / "state" / "fleet" / "scoped-install.json"
        if marker.exists() or marker.is_symlink(): raise JournalError("SCOPED_INSTALL_EXISTS")
        profile = _profile(signed_profile["body"], root, physical=True)
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted["trusted_owner_public_key"]))
        try: key.verify(bytes.fromhex(signed_profile["signature"]), DOMAIN + canonical(profile))
        except (ValueError, InvalidSignature): raise JournalError("SCOPED_PROFILE_UNVERIFIED") from None
        if any(profile[k] != trusted[k] for k in ("device_id", "candidate_sha256", "runtime_sha256")):
            raise JournalError("SCOPED_INSTALL_INVALID")
        with ConcurrencyManager(root).native_execution("SCOPED-INSTALL-" + uuid.uuid4().hex, kind="scoped_install", wait_seconds=0):
            with OwnershipAuthority(root).transaction():
                OwnershipAuthority(root).require_closed()
                cls(root, profile, initialize=True, fixture=_FIXTURE, _evidence="SIGNED_PHYSICAL_CAPACITY_PROFILE")
                if not _publish_json_exclusive(marker, signed_profile): raise JournalError("SCOPED_INSTALL_EXISTS")
        return cls.open_installed(root, **trusted)

    def _db(self):
        db = sqlite3.connect(str(self.path), timeout=self.profile["lock_wait_ms"] / 1000, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=FULL")
        return db

    def _validate(self, db, *, observe_resources=True):
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            objects = set(db.execute("SELECT type,name,tbl_name FROM sqlite_master"))
            if (objects != {("table", "meta", "meta"), ("table", "reservations", "reservations"),
                    ("table", "sqlite_sequence", "sqlite_sequence"), ("index", "sqlite_autoindex_reservations_1", "reservations")}
                    or tables != {"meta", "reservations", "sqlite_sequence"}
                    or [row[1] for row in db.execute("PRAGMA table_info(meta)")] != ["schema", "profile_sha256"]
                    or [row[1] for row in db.execute("PRAGMA table_info(reservations)")] != ["ticket", "operation_id", "record"]
                    or db.execute("SELECT count(*) FROM reservations").fetchone()[0] > self.profile["max_records"]
                    or db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                    or db.execute("SELECT * FROM meta").fetchall() != [("fleet.scoped-authority/1", self.profile_sha256)]): raise ValueError()
            tokens = set()
            for row in db.execute("SELECT ticket,operation_id,record FROM reservations"):
                if not isinstance(row[2], str) or len(row[2]) > 262144: raise ValueError()
                record = _decode(row[2]); _integer(row[0]); _id(row[1])
                fields = {"schema", "operation_id", "token", "reservation_id", "profile_sha256", "epoch", "request", "status", "phase", "generation", "parent", "worker", "descendants", "evidence"}
                if (not isinstance(record, dict) or set(record) != fields
                        or record["schema"] != "fleet.scoped-ownership/1"
                        or record["operation_id"] != row[1] or record["status"] not in {"WAITING", "ACQUIRED", "RELEASED", "UNKNOWN"}
                        or record["phase"] not in {"CLOSED", "ARMED", "CREATE_ATTEMPT", "BOUND"}
                        or record["profile_sha256"] != self.profile_sha256 or record["epoch"] != self.profile["install_epoch"]
                        or not isinstance(record["token"], str) or re.fullmatch(r"[a-f0-9]{32}", record["token"]) is None
                        or record["token"] in tokens or record["reservation_id"] != "scope_" + record["token"]
                        or not _identity_valid(record["parent"]) or record["evidence"] != self.evidence): raise ValueError()
                tokens.add(record["token"])
                _integer(record["generation"], positive=False)
                request = record["request"]
                if not isinstance(request, dict) or set(request) != {"kind", "terminal_id", "terminal_generation", "resources"} or request["kind"] not in KINDS:
                    raise ValueError()
                matched = next((r for r in self.profile["terminals"] if r["terminal_id"] == request["terminal_id"]
                               and r["terminal_generation"] == request["terminal_generation"]), None)
                if (matched is None or request["resources"] != matched["physical_identities"]
                        or (observe_resources and physical_resources(matched["resources"]) != matched["physical_identities"])):
                    raise ValueError()
                if record["phase"] == "CLOSED":
                    if record["worker"] is not None or record["descendants"] != "NONE": raise ValueError()
                elif record["generation"] < 1 or record["descendants"] != "UNKNOWN" or record["status"] not in {"ACQUIRED", "UNKNOWN"}:
                    raise ValueError()
                if record["phase"] == "BOUND":
                    if not _identity_valid(record["worker"]): raise ValueError()
                elif record["worker"] is not None: raise ValueError()
                if record["status"] in {"WAITING", "RELEASED"} and record["phase"] != "CLOSED": raise ValueError()
        except Exception: raise JournalError("SCOPED_STORE_INVALID") from None

    @contextmanager
    def transaction(self):
        with _exclusive_file_lock(self.guard, timeout_seconds=self.profile["lock_wait_ms"] / 1000):
            db = self._db()
            try:
                self._validate(db); db.execute("BEGIN IMMEDIATE")
                yield db
                db.execute("COMMIT")
                # Restricted workers read only a stable main-database snapshot;
                # they never create SQLite WAL/shared-memory files or a guard.
                checkpoint = db.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
                if checkpoint[0] != 0: raise JournalError("SCOPED_CHECKPOINT_UNPROVEN")
            except BaseException:
                if db.in_transaction: db.execute("ROLLBACK")
                raise
            finally: db.close()

    def roster(self): return copy.deepcopy(self.profile["terminals"])

    def verified_capacity_roster(self, route_generation):
        _integer(route_generation)
        if self.evidence != "SIGNED_PHYSICAL_CAPACITY_PROFILE" or not hasattr(self, "_trust"):
            raise JournalError("SCOPED_ROSTER_UNVERIFIED")
        current = type(self).open_installed(self.root, **self._trust)
        if current is None or current.profile_sha256 != self.profile_sha256:
            raise JournalError("SCOPED_PHYSICAL_BINDING_CHANGED")
        payload = current.registration_payload()
        return verify_capacity_roster(payload["signed_profile"], device_id=current.profile["device_id"],
            route_generation=route_generation, trusted_owner_public_key=current._trust["trusted_owner_public_key"],
            load_receipt=base64.b64decode(payload["load_receipt_base64"], validate=True),
            closure_receipt=base64.b64decode(payload["closure_receipt_base64"], validate=True))

    def registration_payload(self):
        """Configured verified installed proof for the finite outbound handshake."""
        if self.evidence != "SIGNED_PHYSICAL_CAPACITY_PROFILE" or not hasattr(self, "_trust"):
            raise JournalError("SCOPED_ROSTER_UNVERIFIED")
        current = type(self).open_installed(self.root, **self._trust)
        if current is None or current.profile_sha256 != self.profile_sha256:
            raise JournalError("SCOPED_PHYSICAL_BINDING_CHANGED")
        signed = _decode(_read_bounded(self.root / "state" / "fleet" / "scoped-install.json", 262144))
        if digest(signed["body"]) != self.profile_sha256:
            raise JournalError("SCOPED_PHYSICAL_BINDING_CHANGED")
        payload = {"signed_profile": signed}
        for field in ("load_receipt", "closure_receipt"):
            raw = _read_bounded(_relative(self.root, self.profile[field]["path"]), 65536)
            if hashlib.sha256(raw).hexdigest() != self.profile[field]["sha256"]:
                raise JournalError("SCOPED_PHYSICAL_BINDING_CHANGED")
            payload[field.replace("_receipt", "_receipt_base64")] = base64.b64encode(raw).decode("ascii")
        if len(canonical(payload)) > 262144: raise JournalError("SCOPED_INPUT_INVALID")
        return payload

    @contextmanager
    def execution(self, operation_id, *, kind, terminal_id, terminal_generation, wait_ms):
        _id(operation_id); _integer(wait_ms, positive=False)
        if kind not in KINDS or wait_ms > 60000: raise JournalError("SCOPED_REQUEST_INVALID")
        row = next((r for r in self.profile["terminals"] if r["terminal_id"] == terminal_id and r["terminal_generation"] == terminal_generation), None)
        if row is None: raise JournalError("SCOPED_TARGET_MISMATCH")
        observed = physical_resources(row["resources"])
        if observed != row["physical_identities"]: raise JournalError("SCOPED_PHYSICAL_BINDING_CHANGED")
        token = uuid.uuid4().hex; request = {"kind": kind, "terminal_id": terminal_id,
            "terminal_generation": terminal_generation, "resources": observed}
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM reservations WHERE operation_id=?", (operation_id,)).fetchone():
                raise JournalError("SCOPED_OPERATION_RECOVERY_REQUIRED")
            if db.execute("SELECT count(*) FROM reservations").fetchone()[0] >= self.profile["max_records"]:
                raise JournalError("SCOPED_CAPACITY")
            record = {"schema": "fleet.scoped-ownership/1", "operation_id": operation_id, "token": token,
                "reservation_id": "scope_" + token,
                "profile_sha256": self.profile_sha256, "epoch": self.profile["install_epoch"],
                "request": request, "status": "WAITING", "phase": "CLOSED", "generation": 0,
                "parent": current_identity(), "worker": None, "descendants": "NONE", "evidence": self.evidence}
            db.execute("INSERT INTO reservations(operation_id,record) VALUES (?,?)", (operation_id, canonical(record).decode()))
        deadline = time.monotonic() + wait_ms / 1000
        while True:
            with self.transaction() as db:
                rows = [_decode(r[0]) for r in db.execute("SELECT record FROM reservations ORDER BY ticket")]
                waiting = [r for r in rows if r["status"] == "WAITING"]
                active = [r for r in rows if r["status"] in {"ACQUIRED", "UNKNOWN"}]
                keys = {r["physical_key"] for r in observed}
                conflicts = any(keys & {r["physical_key"] for r in a["request"]["resources"]} for a in active)
                conflicts |= any(x["path"] == y["path"] or x["path"].startswith(y["path"] + os.sep)
                    or y["path"].startswith(x["path"] + os.sep) for x in observed for a in active for y in a["request"]["resources"])
                # IPC alone is serialized per node even for independent terminals.
                conflicts |= kind == "ipc" and any(a["request"]["kind"] == "ipc" for a in active)
                if waiting and waiting[0]["token"] == token and len(active) < self.profile["capacity"] and not conflicts:
                    record["status"] = "ACQUIRED"; self._save(db, record); break
                if time.monotonic() >= deadline:
                    record["status"] = "RELEASED"; self._save(db, record)
                    raise JournalError("SCOPED_LEASE_UNAVAILABLE")
            time.sleep(.01)
        scope = ScopedLease(self, record, _LEASE)
        try: yield scope
        finally:
            with self.transaction() as db:
                current = self._read(db, token)
                current["status"] = "RELEASED" if current["phase"] == "CLOSED" and current["status"] == "ACQUIRED" else "UNKNOWN"
                self._save(db, current)
            scope.released = True

    @staticmethod
    def _save(db, record):
        db.execute("UPDATE reservations SET record=? WHERE operation_id=?", (canonical(record).decode(), record["operation_id"]))

    @staticmethod
    def _read(db, token):
        for row in db.execute("SELECT record FROM reservations"):
            rec = _decode(row[0])
            if rec["token"] == token: return rec
        raise JournalError("SCOPED_REFERENCE_UNKNOWN")

    def read_scope(self, reference):
        if (not isinstance(reference, dict) or set(reference) != {"profile_sha256", "reservation_id", "token"}
                or reference["profile_sha256"] != self.profile_sha256 or reference["reservation_id"] != "scope_" + reference["token"]):
            raise JournalError("SCOPED_REFERENCE_INVALID")
        with self.transaction() as db: return self._read(db, reference["token"])


class ScopedLease:
    def __init__(self, coordinator, record, seal):
        if seal is not _LEASE: raise JournalError("SCOPED_LEASE_UNVERIFIED")
        self.coordinator, self.root, self.token = coordinator, coordinator.root, record["token"]
        self.namespace, self.authority, self.operation_id = "scoped_native", self, record["operation_id"]
        self.kind = record["request"]["kind"]
        self.released = False

    @property
    def reference(self): return {"profile_sha256": self.coordinator.profile_sha256,
                                 "reservation_id": "scope_" + self.token, "token": self.token}

    def load(self): return self.coordinator.read_scope(self.reference)

    def status(self):
        record = self.load()
        return {"schema": record["schema"], "disposition": "CLOSED" if record["phase"] == "CLOSED" else "ACTIVE",
                "phase": record["phase"], "generation": record["generation"], "status": record["status"]}

    def require_closed(self):
        record = self.load()
        if record["phase"] != "CLOSED" or record["status"] != "ACQUIRED":
            raise JournalError("SCOPED_RECOVERY_REQUIRED")
        return record

    def arm(self, lease=None):
        with self.coordinator.transaction() as db:
            rec = self.coordinator._read(db, self.token)
            if self.released or rec["status"] != "ACQUIRED" or rec["phase"] != "CLOSED" or rec["parent"] != current_identity():
                raise JournalError("SCOPED_ARM_DENIED")
            rec.update(phase="ARMED", generation=rec["generation"] + 1, descendants="UNKNOWN")
            self.coordinator._save(db, rec); return rec

    def _transition(self, expected, phase, *, worker=None, descendants="UNKNOWN"):
        with self.coordinator.transaction() as db:
            rec = self.coordinator._read(db, self.token)
            if rec != expected or rec["status"] != "ACQUIRED" or rec["parent"] != current_identity():
                raise JournalError("SCOPED_STALE_AUTHORITY")
            rec.update(phase=phase, worker=worker, descendants=descendants)
            self.coordinator._save(db, rec); return rec

    def create_attempt(self, expected):
        if expected["phase"] != "ARMED": raise JournalError("SCOPED_CREATE_ORDER_INVALID")
        return self._transition(expected, "CREATE_ATTEMPT")

    def bind_worker(self, expected, process):
        if expected["phase"] != "CREATE_ATTEMPT" or not isinstance(process, ObservedProcess) or process.exited():
            raise JournalError("SCOPED_WORKER_UNPROVEN")
        return self._transition(expected, "BOUND", worker=process.identity())

    def close_zero_attempt(self, expected):
        if expected["phase"] != "ARMED" or expected["worker"] is not None:
            raise JournalError("SCOPED_CREATION_OUTCOME_UNKNOWN")
        return self._transition(expected, "CLOSED", descendants="NONE")

    def close_owned_worker(self, expected, process, *, descendant_verifier):
        if (expected["phase"] != "BOUND" or not isinstance(process, ObservedProcess)
                or process.identity() != expected["worker"] or not process.exited()):
            raise JournalError("SCOPED_EXACT_EXIT_UNPROVEN")
        closure = descendant_verifier(process)
        if closure not in {"PREVENTED_BY_BOUNDARY", "EXACT_DESCENDANTS_EXITED"}:
            raise JournalError("SCOPED_DESCENDANTS_UNPROVEN")
        return self._transition(expected, "CLOSED", descendants="NONE")

    def uncertain(self, expected):
        with self.coordinator.transaction() as db:
            rec = self.coordinator._read(db, self.token)
            if rec != expected: raise JournalError("SCOPED_STALE_AUTHORITY")
            rec["status"] = "UNKNOWN"; self.coordinator._save(db, rec)
            return rec


def observe_bound_sdk_scope(root, scope, expected_owner, actual_self_identity, *,
                            trusted_owner_public_key, expected_profile_sha256,
                            expected_candidate_sha256=None, expected_runtime_sha256=None):
    """Read-only worker proof; no admission, producer mutation or caller flag."""
    if not isinstance(scope, dict) or scope.get("profile_sha256") != expected_profile_sha256:
        raise JournalError("SCOPED_REFERENCE_INVALID")
    marker = Path(root) / "state" / "fleet" / "scoped-install.json"
    signed = _decode(_read_bounded(marker, 262144)); profile = signed["body"]
    profile = assert_installed_sdk_scope_profile(root, device_id=profile["device_id"],
        trusted_owner_public_key=trusted_owner_public_key, expected_profile_sha256=expected_profile_sha256,
        expected_candidate_sha256=expected_candidate_sha256 or profile["candidate_sha256"],
        expected_runtime_sha256=expected_runtime_sha256 or profile["runtime_sha256"])
    # Copy a bounded, checkpointed DB snapshot into memory. No writable SQLite
    # connection, .owner/.guard lock, WAL or shared-memory file reaches the worker.
    raw = bytearray(_read_bounded(Path(root) / "state" / "fleet" / "scoped-resources.sqlite", 64 * 1024 * 1024))
    if raw[:16] != b"SQLite format 3\0": raise JournalError("SCOPED_STORE_INVALID")
    raw[18] = raw[19] = 1  # The copied checkpoint is an in-memory rollback-mode DB.
    db = sqlite3.connect(":memory:")
    try:
        db.deserialize(bytes(raw)); db.execute("PRAGMA query_only=ON")
        if (db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                or db.execute("SELECT * FROM meta").fetchall() != [("fleet.scoped-authority/1", expected_profile_sha256)]):
            raise JournalError("SCOPED_STORE_INVALID")
        view = object.__new__(ScopedResourceCoordinator)
        view.profile, view.profile_sha256 = profile, expected_profile_sha256
        view.evidence = "SIGNED_PHYSICAL_CAPACITY_PROFILE"
        view._validate(db, observe_resources=False)
        record = ScopedResourceCoordinator._read(db, scope["token"])
    except sqlite3.Error: raise JournalError("SCOPED_STORE_INVALID") from None
    finally: db.close()
    if (record["profile_sha256"] != scope["profile_sha256"] or record["reservation_id"] != scope["reservation_id"]
            or record["epoch"] != profile["install_epoch"]): raise JournalError("SCOPED_REFERENCE_INVALID")
    if (record["phase"] != "BOUND" or record["status"] != "ACQUIRED"
            or record["parent"] != expected_owner or record["worker"] != actual_self_identity):
        raise JournalError("SCOPED_EXACT_WORKER_UNPROVEN")
    return record


def assert_installed_sdk_scope_profile(root, *, device_id, trusted_owner_public_key,
        expected_profile_sha256, expected_candidate_sha256, expected_runtime_sha256):
    """Exact installed signature/source provenance, without any write access."""
    try:
        signed = _decode(_read_bounded(Path(root) / "state" / "fleet" / "scoped-install.json", 262144))
        if set(signed) != {"body", "signature"}: raise ValueError()
        _sha(trusted_owner_public_key)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_owner_public_key)).verify(
            bytes.fromhex(signed["signature"]), DOMAIN + canonical(signed["body"]))
        profile = _profile(signed["body"], root, physical=True, observe=False)
        if (digest(profile) != expected_profile_sha256 or profile["device_id"] != device_id
                or profile["candidate_sha256"] != expected_candidate_sha256 or profile["runtime_sha256"] != expected_runtime_sha256):
            raise ValueError()
        return profile
    except (ValueError, TypeError, KeyError, InvalidSignature):
        raise JournalError("SCOPED_INSTALL_INVALID") from None


class VerifiedCapacityRoster:
    def __init__(self, profile, route_generation, seal, proof=None):
        if seal is not _ROSTER: raise JournalError("SCOPED_ROSTER_UNVERIFIED")
        self._profile, self.route_generation = copy.deepcopy(profile), route_generation
        self.profile_sha256 = digest(profile)
        self._proof = copy.deepcopy(proof)

    @property
    def profile(self): return copy.deepcopy(self._profile)

    @classmethod
    def _for_fixture(cls, profile, route_generation):
        _integer(route_generation)
        return cls(_profile(profile, None, physical=False, observe=False), route_generation, _ROSTER)

    def receipt(self):
        return {"schema": "fleet.capacity-roster/1", "profile_sha256": self.profile_sha256,
                "route_generation": self.route_generation, "profile": copy.deepcopy(self.profile), "proof": copy.deepcopy(self._proof)}


def verify_capacity_roster(signed_profile, *, device_id, route_generation, trusted_owner_public_key,
                          load_receipt, closure_receipt):
    """Gateway: operator signature plus exact receipt bytes, current admitted node.

    The HTTPS event owner supplies the authenticated enrollment device/route. Physical
    observations remain the explicitly qualified node's authority, never free RAM.
    """
    try:
        _integer(route_generation); _sha(trusted_owner_public_key)
        if not isinstance(signed_profile, dict) or set(signed_profile) != {"body", "signature"}: raise ValueError()
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_owner_public_key)).verify(
            bytes.fromhex(signed_profile["signature"]), DOMAIN + canonical(signed_profile["body"]))
        profile = _profile(signed_profile["body"], None, physical=False, observe=False)
        if profile["device_id"] != device_id: raise ValueError()
        for field, raw, schema in (("load_receipt", load_receipt, "fleet.capacity-load/1"),
                                   ("closure_receipt", closure_receipt, "fleet.capacity-closure/1")):
            if not isinstance(raw, bytes) or len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != profile[field]["sha256"]:
                raise ValueError()
            receipt = _decode(raw)
            if (receipt.get("schema") != schema or receipt.get("qualification") != "PHYSICAL_WINDOWS"
                    or any(receipt.get(k) != profile[k] for k in ("candidate_sha256", "runtime_sha256", "device_id", "install_epoch", "capacity"))
                    or receipt.get("terminal_roster_sha256") != digest(profile["terminals"])): raise ValueError()
            if field == "load_receipt":
                for name in ("memory_bytes", "cpu_basis_points", "p95_phase_ms"):
                    measured, limit = receipt.get("measured", {}).get(name), receipt.get("limits", {}).get(name)
                    _integer(measured, positive=False); _integer(limit)
                    if measured > limit: raise ValueError()
                _integer(receipt.get("duration_ms")); _integer(receipt.get("completed_jobs"))
            elif receipt.get("descendant_boundary") not in {"WINDOWS_JOB_KILL_ON_CLOSE_VERIFIED", "EXACT_DESCENDANTS_EXITED"}: raise ValueError()
        manifest = profile["source_manifest"]
        if not isinstance(manifest, dict) or not 1 <= len(manifest) <= 512 or digest(manifest) != profile["candidate_sha256"]:
            raise ValueError()
        for path, sha in manifest.items():
            if not isinstance(path, str) or not (os.path.isabs(path) or ntpath.isabs(path)): raise ValueError()
            _sha(sha)
        if _portable_source_bundle(manifest) != _portable_source_bundle(capacity_source_manifest()):
            raise JournalError("SCOPED_SOURCE_UNPROVEN")
        proof = {"signed_profile": copy.deepcopy(signed_profile), "load_receipt_base64": base64.b64encode(load_receipt).decode("ascii"),
                 "closure_receipt_base64": base64.b64encode(closure_receipt).decode("ascii")}
        if len(canonical(proof)) > 262144: raise ValueError()
        return VerifiedCapacityRoster(profile, route_generation, _ROSTER, proof)
    except (ValueError, KeyError, TypeError, InvalidSignature):
        raise JournalError("SCOPED_ROSTER_UNVERIFIED") from None
