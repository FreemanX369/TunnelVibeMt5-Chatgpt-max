"""Durable fleet jobs. Delivery is never proof of native execution.

These journals do not replace the local JobStore or its legacy request index.
Native adapters are trusted local objects; no transport input selects executable code.
"""
from __future__ import annotations

import base64
import hashlib
import json
import ntpath
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..core.jobs import _exclusive_file_lock, new_job_id
from ..core.native_ownership import ObservedProcess

STATES = {"QUEUED", "DELIVERED", "RESERVED", "STARTING", "RUNNING", "RESULT_PENDING",
          "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN", "RECOVERY_REQUIRED"}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
_CAPACITY_FIXTURE = object()


class JournalError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (ValueError, TypeError, RecursionError):
        raise JournalError("INVALID_JOURNAL_INPUT") from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _id(value, prefix=None):
    pattern = r"[A-Za-z0-9_.:-]{1,128}" if prefix is None else prefix + r"[a-f0-9]{32}"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise JournalError("INVALID_JOURNAL_INPUT")
    return value


def _integer(value, *, positive=True):
    if type(value) is not int or value < int(positive) or value > 2**63 - 1:
        raise JournalError("INVALID_JOURNAL_INPUT")
    return value


def _absolute_path(value):
    return (isinstance(value, str) and 0 < len(value) <= 32768
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        and (os.path.isabs(value) or (ntpath.isabs(value) and bool(ntpath.splitdrive(value)[0]))))


def _identity_valid(value):
    """Portable DTO shape only; actual process proof remains ObservedProcess."""
    return (isinstance(value, dict) and set(value) == {"pid", "creation", "image"}
        and type(value["pid"]) is int and 0 < value["pid"] <= 2**63 - 1
        and isinstance(value["creation"], str) and 0 < len(value["creation"]) <= 32
        and value["creation"].isascii() and value["creation"].isdigit() and int(value["creation"]) > 0
        and _absolute_path(value["image"]))


def _decode(raw):
    if not isinstance(raw, (str, bytes)) or len(raw if isinstance(raw, bytes) else raw.encode("utf-8")) > 262144:
        raise JournalError("JOURNAL_INVALID")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise JournalError("JOURNAL_INVALID")
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, RecursionError):
        raise JournalError("JOURNAL_INVALID") from None


def target(value):
    if not isinstance(value, dict) or set(value) != {"schema", "device_id", "terminal_id",
            "route_generation", "terminal_generation"} or value["schema"] != "fleet.target/1":
        raise JournalError("TARGET_MISMATCH")
    _id(value["device_id"], "dev_"); _id(value["terminal_id"], "term_")
    _integer(value["route_generation"]); _integer(value["terminal_generation"])
    return _decode(canonical(value))


def request_hash(request):
    # M2 owns validation/normalization. The legacy hashing implementation is untouched.
    from .native import native_request_hash
    try:
        value = native_request_hash(request)
        target(request["placement"]["target"])
        return value
    except Exception:
        raise JournalError("INVALID_NATIVE_REQUEST") from None


def terminal_closure(value, rec):
    fields = {"schema", "local_job_id", "request_sha256", "target", "evidence", "phases", "lease_release"}
    if (not isinstance(value, dict) or set(value) != fields or value["schema"] != "fleet.native.closure/1"
            or any(value[k] != rec[k] for k in ("local_job_id", "request_sha256", "target"))
            or value["evidence"] not in {"OPERATOR_APPROVED_REAL_NATIVE", "SYNTHETIC_NATIVE_ONLY"}
            or value["lease_release"] != "RETURNED" or not isinstance(value["phases"], list)
            or not 1 <= len(value["phases"]) <= 8):
        raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
    for phase in value["phases"]:
        if (not isinstance(phase, dict) or set(phase) != {"phase", "ownership_record", "process", "descendants"}
                or phase["phase"] not in {"compile", "deploy", "test", "start", "result", "cancel"}
                or phase["descendants"] not in {"NONE", "EXACT_DESCENDANTS_EXITED", "PREVENTED_BY_BOUNDARY"}
                or not isinstance(phase["ownership_record"], dict)):
            raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        closed = phase["ownership_record"]
        if closed.get("phase") != "CLOSED" or closed.get("worker") is not None or closed.get("descendants") != "NONE":
            raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        _integer(closed.get("generation"))
        if closed.get("schema") == "native.ownership/1":
            if (set(closed) != {"schema", "epoch", "generation", "disposition", "phase", "token", "operation_id", "kind", "parent", "worker", "descendants"}
                    or closed["disposition"] != "CLOSED" or closed["parent"] is not None
                    or any(closed[k] != "" for k in ("token", "operation_id", "kind"))):
                raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        elif closed.get("schema") == "fleet.scoped-ownership/1":
            if (set(closed) != {"schema", "operation_id", "token", "reservation_id", "profile_sha256", "epoch", "request", "status", "phase", "generation", "parent", "worker", "descendants", "evidence"}
                    or closed["status"] not in {"ACQUIRED", "RELEASED"} or not _identity_valid(closed["parent"])
                    or not isinstance(closed["request"], dict) or set(closed["request"]) != {"kind", "terminal_id", "terminal_generation", "resources"}
                    or any(closed["request"][k] != rec["target"][k] for k in ("terminal_id", "terminal_generation"))):
                raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
            _id(closed["operation_id"])
            if (not isinstance(closed["token"], str) or re.fullmatch(r"[a-f0-9]{32}", closed["token"]) is None
                    or closed["reservation_id"] != "scope_" + closed["token"]
                    or not isinstance(closed["profile_sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", closed["profile_sha256"]) is None
                    or closed["evidence"] not in {"SIGNED_PHYSICAL_CAPACITY_PROFILE", "SYNTHETIC_SCOPE_ONLY"}):
                raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
            from .resources import KINDS, RESOURCE_FIELDS
            resources = closed["request"]["resources"]
            if (closed["request"]["kind"] not in KINDS or not isinstance(resources, list) or len(resources) != 4
                    or any(not isinstance(p, dict) or set(p) != {"kind", "path", "physical_key"} for p in resources)
                    or {p["kind"] for p in resources} != RESOURCE_FIELDS): raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
            for resource in resources:
                if (not _absolute_path(resource["path"])
                        or not isinstance(resource["physical_key"], str) or len(resource["physical_key"]) > 128
                        or re.fullmatch(r"[0-9]+:[0-9]+", resource["physical_key"]) is None):
                    raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        else:
            raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        _id(closed["epoch"])
        if phase["process"] is not None and not _identity_valid(phase["process"]):
            raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        if (phase["process"] is None) != (phase["descendants"] == "NONE"):
            raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
        if value["evidence"] == "OPERATOR_APPROVED_REAL_NATIVE" and (phase["process"] is None or phase["descendants"] != "EXACT_DESCENDANTS_EXITED"):
            raise JournalError("TERMINAL_CLOSURE_UNPROVEN")
    return _decode(canonical(value))


def _zero_effect_denial(rec):
    return (rec.get("state") == "FAILED" and isinstance(rec.get("result"), dict)
        and set(rec["result"]) == {"status", "reason_code"}
        and rec["result"].get("status") == "DENIED"
        and rec["result"].get("reason_code") == "NATIVE_QUALIFICATION_UNAVAILABLE")


def outcome_projection(rec):
    if rec["state"] not in TERMINAL or not isinstance(rec["result"], dict):
        raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    raw = rec["result"]
    evidence = "NO_NATIVE_EFFECTS" if _zero_effect_denial(rec) else {
        "SYNTHETIC_NATIVE_ONLY": "SYNTHETIC_TEST", "OPERATOR_APPROVED_REAL_NATIVE": "OPERATOR_APPROVED_REAL_NATIVE"}.get(raw.get("evidence"))
    if evidence is None: raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    if evidence != "NO_NATIVE_EFFECTS": terminal_closure(rec.get("terminal_closure"), rec)
    process = rec.get("active_process") or raw.get("process_identity")
    if process is None and rec.get("terminal_closure"):
        process = rec["terminal_closure"]["phases"][-1]["process"]
    if process is not None and not _identity_valid(process): raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    return {"schema": "fleet.native-outcome-evidence/1", "state": rec["state"], "evidence": evidence,
            "receipt_sha256": digest(raw), "process_identity": process}


def _validate_projection(value, rec):
    if (not isinstance(value, dict) or set(value) != {"schema", "state", "evidence", "receipt_sha256", "process_identity"}
            or value["schema"] != "fleet.native-outcome-evidence/1" or value["state"] != rec["state"]
            or value["state"] not in TERMINAL or value["evidence"] not in {"NO_NATIVE_EFFECTS", "SYNTHETIC_TEST", "OPERATOR_APPROVED_REAL_NATIVE"}
            or not isinstance(value["receipt_sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", value["receipt_sha256"]) is None
            or (value["process_identity"] is not None and not _identity_valid(value["process_identity"]))):
        raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    if value["evidence"] == "NO_NATIVE_EFFECTS":
        if (value["state"] != "FAILED" or value["process_identity"] is not None
                or value["receipt_sha256"] != digest({"status": "DENIED", "reason_code": "NATIVE_QUALIFICATION_UNAVAILABLE"})):
            raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    else:
        closed = terminal_closure(rec.get("terminal_closure"), rec)
        expected = "SYNTHETIC_NATIVE_ONLY" if value["evidence"] == "SYNTHETIC_TEST" else "OPERATOR_APPROVED_REAL_NATIVE"
        process = rec.get("active_process") or closed["phases"][-1]["process"]
        if closed["evidence"] != expected or value["process_identity"] != process:
            raise JournalError("JOURNAL_WITNESS_UNRESOLVED")


def _validate_witness_record(observed, expected):
    required = {"schema", "global_job_id", "operation_id", "node_operation_id", "request_sha256", "request", "target", "state", "sequence",
        "local_job_id", "session_id", "result", "quarantined_evidence", "journal_high_water"}
    optional = {"start_authorization", "authorization_challenges", "active_process", "terminal_closure"}
    if (not isinstance(observed, dict) or not required <= set(observed) or set(observed) - required - optional
            or observed["schema"] != "fleet.job/1" or observed["request"] != expected["request"]
            or request_hash(observed["request"]) != observed["request_sha256"]
            or observed["operation_id"] != expected["node_operation_id"]
            or any(observed[k] != expected[k] for k in ("global_job_id", "node_operation_id", "request_sha256", "target"))
            or observed["quarantined_evidence"] != [] or not isinstance(observed["result"], dict)):
        raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    for name in ("global_job_id", "operation_id", "node_operation_id", "local_job_id", "session_id"): _id(observed[name])
    _integer(observed["sequence"]); _integer(observed["journal_high_water"])
    if "active_process" in observed and not _identity_valid(observed["active_process"]): raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    if "authorization_challenges" in observed:
        from .native_authorization import PHASES
        challenges = observed["authorization_challenges"]
        if (not isinstance(challenges, dict) or set(challenges) != PHASES
                or any(not isinstance(v, str) or re.fullmatch(r"[a-f0-9]{32}", v) is None for v in challenges.values())):
            raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    if "start_authorization" in observed:
        value = observed["start_authorization"]
        if (not isinstance(value, dict) or set(value) != {"phase", "challenge"} or value["phase"] != "start"
                or value["challenge"] != observed.get("authorization_challenges", {}).get("start")):
            raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
    if "terminal_closure" in observed: terminal_closure(observed["terminal_closure"], observed)
    _validate_projection(observed["result"], observed)


class _Journal:
    def __init__(self, path, *, initialize=False, max_records, max_payload_bytes,
                 wait_ms, fault=None, capacity_owner_public_key=None, _capacity_fixture=None):
        for value in (max_records, max_payload_bytes, wait_ms):
            _integer(value)
        if max_records > 100000 or max_payload_bytes > 262144 or wait_ms > 60000:
            raise JournalError("JOURNAL_POLICY_INVALID")
        self.path = Path(path).resolve()
        self.policy = {"max_records": max_records, "max_payload_bytes": max_payload_bytes,
                       "wait_ms": wait_ms}
        self.fault = fault
        if (capacity_owner_public_key is not None and (not isinstance(capacity_owner_public_key, str)
                or re.fullmatch(r"[a-f0-9]{64}", capacity_owner_public_key) is None)):
            raise JournalError("NATIVE_CAPACITY_TRUST_INVALID")
        self.capacity_owner_public_key = capacity_owner_public_key
        self._capacity_fixture = _capacity_fixture is _CAPACITY_FIXTURE
        self._mutex = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _exclusive_file_lock(self.path.with_name(self.path.name + ".owner.lock"),
                                         timeout_seconds=wait_ms / 1000)
        self._lock.__enter__()
        self._db = None
        temporary = self.path.with_name(self.path.name + ".initialize-" + uuid.uuid4().hex) if initialize else None
        try:
            if initialize == self.path.exists():
                raise JournalError("JOURNAL_EXISTS" if initialize else "JOURNAL_MISSING")
            self._db = sqlite3.connect(str(temporary or self.path), timeout=wait_ms / 1000,
                                       isolation_level=None, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            if initialize:
                with self.transaction():
                    self._db.execute("CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    self._db.execute("CREATE TABLE jobs (operation_id TEXT UNIQUE NOT NULL, global_job_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, record TEXT NOT NULL)")
                    self._db.execute("CREATE TABLE cancels (operation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, receipt TEXT NOT NULL)")
                    self._db.execute("CREATE TABLE starts (authorization_key TEXT PRIMARY KEY, receipt TEXT NOT NULL)")
                    self._db.execute("CREATE TABLE effects (global_job_id TEXT NOT NULL, sequence INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(global_job_id,sequence))")
                    self._db.execute("CREATE TABLE recoveries (operation_id TEXT UNIQUE NOT NULL, recovery_id TEXT PRIMARY KEY, record TEXT NOT NULL)")
                    for name, value in {"schema": "fleet.jobs/1", "role": self.role,
                            "policy": self.policy, "high_water": 0, "restore": None, "coordinated_restore": None, "capacity_rosters": {}}.items():
                        self._meta(name, value)
            self._validate()
            if initialize:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._db.close(); self._db = None
                os.link(temporary, self.path)
                temporary.unlink()
                self._db = sqlite3.connect(str(self.path), timeout=wait_ms / 1000,
                    isolation_level=None, check_same_thread=False)
                self._db.row_factory = sqlite3.Row
                self._db.execute("PRAGMA journal_mode=WAL"); self._db.execute("PRAGMA synchronous=FULL")
        except BaseException as error:
            self.close()
            if isinstance(error, sqlite3.Error):
                raise JournalError("JOURNAL_INVALID") from None
            raise
        finally:
            if temporary:
                for suffix in ("", "-wal", "-shm"):
                    Path(str(temporary) + suffix).unlink(missing_ok=True)

    def close(self):
        if self._db is not None:
            self._db.close(); self._db = None
        if self._lock is not None:
            self._lock.__exit__(None, None, None); self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _hit(self, phase):
        if self.fault:
            self.fault(phase)

    @contextmanager
    def transaction(self):
        with self._mutex:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._hit("before_commit")
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            self._hit("after_commit")

    def _meta(self, name, value=...):
        if value is ...:
            return _decode(self._db.execute("SELECT value FROM meta WHERE name=?", (name,)).fetchone()[0])
        self._bound(value)
        self._db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (name, canonical(value).decode()))

    def _validate(self):
        try:
            tables = {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {"meta": ["name", "value"], "jobs": ["operation_id", "global_job_id", "request_sha256", "record"],
                       "cancels": ["operation_id", "request_sha256", "receipt"], "starts": ["authorization_key", "receipt"],
                       "effects": ["global_job_id", "sequence", "record"], "recoveries": ["operation_id", "recovery_id", "record"]}
            if (tables != {"meta", "jobs", "cancels", "starts", "effects", "recoveries"}
                    or self._db.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('trigger','view') OR (type='index' AND sql IS NOT NULL)").fetchone()[0]
                    or any([r[1] for r in self._db.execute("PRAGMA table_info(" + name + ")")] != expected
                           for name, expected in columns.items())
                    or any(self._db.execute("SELECT count(*) FROM " + name).fetchone()[0] > self.policy["max_records"]
                           for name in ("jobs", "cancels", "starts", "effects", "recoveries"))
                    or any(self._db.execute("SELECT count(*) FROM " + name + " WHERE length(CAST(" + column + " AS BLOB))>?",
                           (self.policy["max_payload_bytes"],)).fetchone()[0] for name, column in
                           (("meta", "value"), ("jobs", "record"), ("starts", "receipt"), ("cancels", "receipt"), ("effects", "record"), ("recoveries", "record")))
                    or {r[0] for r in self._db.execute("SELECT name FROM meta")} != {"schema", "role", "policy", "high_water", "restore", "coordinated_restore", "capacity_rosters"}
                    or self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                    or self._meta("schema") != "fleet.jobs/1" or self._meta("role") != self.role
                    or self._meta("policy") != self.policy):
                raise ValueError()
            _integer(self._meta("high_water"), positive=False)
            restore = self._meta("restore")
            if restore is not None:
                if (not isinstance(restore, dict) or set(restore) != {"schema", "challenge", "export_generation", "devices", "reconciled"}
                        or restore["schema"] != "fleet.restore/1" or re.fullmatch(r"[a-f0-9]{32}", restore["challenge"]) is None
                        or not restore["devices"] or len(set(restore["devices"])) != len(restore["devices"])
                        or len(set(restore["reconciled"])) != len(restore["reconciled"])
                        or not set(restore["reconciled"]) <= set(restore["devices"])):
                    raise ValueError()
                _integer(restore["export_generation"])
                for device in restore["devices"]:
                    _id(device, "dev_")
            coordinated = self._meta("coordinated_restore")
            if coordinated is not None:
                if (not isinstance(coordinated, dict) or coordinated["schema"] != "fleet.job-restore-receipt/1"
                        or coordinated["phase"] not in {"PREPARING", "PREPARED", "FINALIZED"}
                        or coordinated["coordination_sha256"] != digest(coordinated["scope"])
                        or not isinstance(coordinated["witnesses"], dict)
                        or (coordinated["phase"] != "FINALIZED" and restore is None)):
                    raise ValueError()
            rosters = self._meta("capacity_rosters")
            if not isinstance(rosters, dict) or len(rosters) > self.policy["max_records"]: raise ValueError()
            for device, roster in rosters.items():
                _id(device, "dev_"); self._bound(roster); _integer(roster["route_generation"])
                if (roster["schema"] != "fleet.capacity-roster/1" or roster["profile"]["device_id"] != device
                        or roster["profile_sha256"] != digest(roster["profile"])): raise ValueError()
                self._verify_capacity_receipt(roster)
            count = 0
            for row in self._db.execute("SELECT * FROM jobs"):
                count += 1
                rec = _decode(row["record"])
                self._bound(rec)
                required = {"schema", "global_job_id", "operation_id", "node_operation_id", "request_sha256", "request",
                    "target", "state", "sequence", "local_job_id", "session_id", "result", "quarantined_evidence", "journal_high_water"}
                if not required <= set(rec) or set(rec) - required - {"node_sequence", "start_authorization", "authorization_challenges", "active_process", "terminal_closure"}:
                    raise ValueError()
                if (rec["global_job_id"] != row["global_job_id"] or rec["operation_id"] != row["operation_id"]
                        or rec["request_sha256"] != row["request_sha256"]
                        or request_hash(rec["request"]) != rec["request_sha256"]
                        or rec["target"] != rec["request"]["placement"]["target"] or rec["state"] not in STATES):
                    raise ValueError()
                _integer(rec["sequence"]); _id(rec["node_operation_id"])
                _id(rec["global_job_id"], "fjob_"); _id(rec["operation_id"])
                _integer(rec["journal_high_water"])
                if rec["journal_high_water"] > self._meta("high_water") or rec["schema"] != "fleet.job/1":
                    raise ValueError()
                if rec["local_job_id"] is not None:
                    _id(rec["local_job_id"])
                if rec["session_id"] is not None:
                    _id(rec["session_id"])
                if not isinstance(rec["quarantined_evidence"], list) or (rec["result"] is not None and not isinstance(rec["result"], dict)):
                    raise ValueError()
                if "node_sequence" in rec:
                    _integer(rec["node_sequence"])
                if "terminal_closure" in rec:
                    terminal_closure(rec["terminal_closure"], rec)
            if count > self.policy["max_records"]:
                raise ValueError()
            for row in self._db.execute("SELECT * FROM starts"):
                signed = _decode(row["receipt"]); self._bound(signed)
                grant = signed["body"]
                rec = self._row(grant["global_job_id"])
                if (grant["schema"] != "fleet.native.authorization/1" or any(grant[k] != rec[k] for k in
                        ("global_job_id", "node_operation_id", "request_sha256", "target", "session_id"))):
                    raise ValueError()
                _id(grant["authorization_id"]); _integer(grant["issued_ms"], positive=False); _integer(grant["expires_ms"])
                if grant["expires_ms"] <= grant["issued_ms"]:
                    raise ValueError()
                from .native_authorization import FIELDS, effect_event
                if (set(grant) != FIELDS | {"schema", "authorization_id", "issued_ms", "expires_ms"}
                        or row["authorization_key"] != digest({"global_job_id": grant["global_job_id"],
                            "phase": grant["phase"], "sequence": grant["sequence"]})):
                    raise ValueError()
                effect_event(grant["phase"], grant["event"])
            if (self._db.execute("SELECT count(*) FROM starts").fetchone()[0] > self.policy["max_records"]
                    or self._db.execute("SELECT count(*) FROM effects").fetchone()[0] > self.policy["max_records"]):
                raise ValueError()
            from .native_authorization import completion_receipt, effect_event
            for row in self._db.execute("SELECT * FROM effects"):
                step = _decode(row["record"]); self._bound(step)
                if (set(step) != {"schema", "global_job_id", "sequence", "phase", "event", "challenge", "state", "grant_sha256", "completion", "predecessor_sha256"}
                        or step["schema"] != "fleet.native-effect-intent/1"
                        or row["global_job_id"] != step["global_job_id"] or row["sequence"] != step["sequence"]
                        or step["state"] not in {"INTENT", "CONSUMED", "COMPLETED", "NOT_ATTEMPTED", "UNKNOWN"}):
                    raise ValueError()
                self._row(step["global_job_id"]); _integer(step["sequence"])
                effect_event(step["phase"], step["event"])
                if re.fullmatch(r"[a-f0-9]{32}", step["challenge"]) is None:
                    raise ValueError()
                if step["grant_sha256"] is not None and re.fullmatch(r"[a-f0-9]{64}", step["grant_sha256"]) is None:
                    raise ValueError()
                if step["predecessor_sha256"] is not None and re.fullmatch(r"[a-f0-9]{64}", step["predecessor_sha256"]) is None:
                    raise ValueError()
                if step["completion"] is not None:
                    completion = completion_receipt(step["completion"])
                    if (any(completion[k] != step[k] for k in ("phase", "event", "sequence", "challenge", "grant_sha256"))
                            or completion["outcome"] != step["state"]): raise ValueError()
                elif step["state"] in {"COMPLETED", "NOT_ATTEMPTED"}: raise ValueError()
            for row in self._db.execute("SELECT * FROM cancels"):
                _id(row["operation_id"])
                if re.fullmatch(r"[a-f0-9]{64}", row["request_sha256"]) is None:
                    raise ValueError()
                self._bound(_decode(row["receipt"]))
            for row in self._db.execute("SELECT * FROM recoveries"):
                receipt = _decode(row["record"]); self._bound(receipt)
                if (set(receipt) != {"schema", "operation_id", "recovery_id", "challenge", "original", "current", "state", "result", "witness_sha256"}
                        or receipt["schema"] != "fleet.native-recovery/1" or receipt["state"] not in {"ISSUED", "COMPLETED"}
                        or receipt["operation_id"] != row["operation_id"] or receipt["recovery_id"] != row["recovery_id"]
                        or re.fullmatch(r"[a-f0-9]{32}", receipt["challenge"]) is None): raise ValueError()
                _id(receipt["operation_id"]); _id(receipt["recovery_id"], "frecovery_")
                if (set(receipt["original"]) != {"global_job_id", "local_job_id", "node_operation_id", "request_sha256", "target", "session_id"}
                        or set(receipt["current"]) != {"device_id", "route_generation", "session_id"}): raise ValueError()
                rec = self._row(receipt["original"]["global_job_id"])
                if any(receipt["original"][k] != rec[k] for k in receipt["original"]): raise ValueError()
                _id(receipt["current"]["device_id"], "dev_"); _integer(receipt["current"]["route_generation"]); _id(receipt["current"]["session_id"])
                if receipt["current"]["device_id"] != rec["target"]["device_id"]: raise ValueError()
                if (receipt["state"] == "ISSUED") != (receipt["result"] is None and receipt["witness_sha256"] is None): raise ValueError()
        except Exception:
            raise JournalError("JOURNAL_INVALID") from None

    def _bound(self, value):
        if len(canonical(value)) > self.policy["max_payload_bytes"]:
            raise JournalError("PAYLOAD_LIMIT")

    def _effect_history(self, global_job_id):
        return [_decode(row[0]) for row in self._db.execute(
            "SELECT record FROM effects WHERE global_job_id=? ORDER BY sequence", (global_job_id,))]

    def recovery_head(self):
        """Bounded streaming head of all authoritative data, not restore phases."""
        with self._mutex:
            self._validate()
            head = hashlib.sha256(b"fleet.job-recovery-head/1\n")
            queries = (("meta", "SELECT * FROM meta WHERE name NOT IN ('restore','coordinated_restore') ORDER BY name"),
                ("jobs", "SELECT * FROM jobs ORDER BY global_job_id"),
                ("starts", "SELECT * FROM starts ORDER BY authorization_key"),
                ("cancels", "SELECT * FROM cancels ORDER BY operation_id"),
                ("effects", "SELECT * FROM effects ORDER BY global_job_id,sequence"),
                ("recoveries", "SELECT * FROM recoveries ORDER BY recovery_id"))
            for table, query in queries:
                head.update(canonical({"table": table}) + b"\n")
                for row in self._db.execute(query):
                    head.update(canonical(dict(row)) + b"\n")
            return {"schema": "fleet.job-recovery-head/1", "sha256": head.hexdigest()}

    def _save_effect(self, step, *, insert=False):
        self._bound(step)
        if insert:
            if self._db.execute("SELECT count(*) FROM effects").fetchone()[0] >= self.policy["max_records"]:
                raise JournalError("JOURNAL_CAPACITY")
            self._db.execute("INSERT INTO effects VALUES (?,?,?)",
                (step["global_job_id"], step["sequence"], canonical(step).decode()))
        else:
            self._db.execute("UPDATE effects SET record=? WHERE global_job_id=? AND sequence=?",
                (canonical(step).decode(), step["global_job_id"], step["sequence"]))

    def _ready(self):
        if self._meta("restore") is not None:
            raise JournalError("RECONCILIATION_REQUIRED")

    def _row(self, global_job_id):
        row = self._db.execute("SELECT record FROM jobs WHERE global_job_id=?", (_id(global_job_id),)).fetchone()
        if row is None:
            raise JournalError("JOB_UNKNOWN")
        return _decode(row[0])

    def get(self, global_job_id):
        # Read only: never calls local get_job/restoration.
        with self._mutex:
            return self._row(global_job_id)

    def assert_dispatch_ready(self):
        with self._mutex: self._ready()

    def get_operation(self, operation_id, request=None):
        _id(operation_id)
        with self._mutex:
            row = self._db.execute("SELECT record FROM jobs WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None: return None
            rec = _decode(row[0])
            if request is not None and request_hash(request) != rec["request_sha256"]:
                raise JournalError("IDEMPOTENCY_CONFLICT")
            return rec

    def _save(self, record):
        self._bound(record)
        high_water = self._meta("high_water") + 1
        record["journal_high_water"] = high_water
        self._db.execute("UPDATE jobs SET record=? WHERE global_job_id=?",
                         (canonical(record).decode(), record["global_job_id"]))
        self._meta("high_water", high_water)
        return _decode(canonical(record))

    def _insert(self, record):
        if self._db.execute("SELECT count(*) FROM jobs").fetchone()[0] >= self.policy["max_records"]:
            raise JournalError("JOURNAL_CAPACITY")
        self._db.execute("INSERT INTO jobs VALUES (?,?,?,?)", (record["operation_id"],
            record["global_job_id"], record["request_sha256"], canonical(record).decode()))
        return self._save(record)

    def backup(self, destination):
        destination = Path(destination).resolve()
        if destination.exists() or destination == self.path:
            raise JournalError("BACKUP_EXISTS")
        with self._mutex:
            self._validate()
            db = sqlite3.connect(str(destination))
            try:
                self._db.backup(db)
            finally:
                db.close()


class GatewayJobJournal(_Journal):
    role = "GATEWAY"

    @classmethod
    def _for_fixture(cls, *args, **kwargs):
        return cls(*args, _capacity_fixture=_CAPACITY_FIXTURE, **kwargs)

    def bind_capacity_owner(self, trusted_owner_public_key):
        if trusted_owner_public_key is not None and (not isinstance(trusted_owner_public_key, str)
                or re.fullmatch(r"[a-f0-9]{64}", trusted_owner_public_key) is None):
            raise JournalError("NATIVE_CAPACITY_TRUST_INVALID")
        with self._mutex:
            old = self.capacity_owner_public_key
            self.capacity_owner_public_key = trusted_owner_public_key
            try:
                for receipt in self._meta("capacity_rosters").values(): self._verify_capacity_receipt(receipt)
            except Exception:
                self.capacity_owner_public_key = old; raise

    def _verify_capacity_receipt(self, receipt):
        from .scoped_resources import verify_capacity_roster
        if (not isinstance(receipt, dict) or set(receipt) != {"schema", "profile_sha256", "route_generation", "profile", "proof"}
                or receipt["profile_sha256"] != digest(receipt["profile"])):
            raise JournalError("NATIVE_CAPACITY_UNQUALIFIED")
        proof = receipt["proof"]
        if self._capacity_fixture and proof is None:
            return receipt
        if self.capacity_owner_public_key is None:
            raise JournalError("NATIVE_CAPACITY_TRUST_UNAVAILABLE")
        if not isinstance(proof, dict) or set(proof) != {"signed_profile", "load_receipt_base64", "closure_receipt_base64"}:
            raise JournalError("NATIVE_CAPACITY_UNQUALIFIED")
        self._bound(receipt)
        try:
            raws = []
            for field in ("load_receipt_base64", "closure_receipt_base64"):
                value = proof[field]
                if not isinstance(value, str) or len(value) > 87384: raise ValueError()
                raw = base64.b64decode(value, validate=True)
                if base64.b64encode(raw).decode("ascii") != value or len(raw) > 65536: raise ValueError()
                raws.append(raw)
            verified = verify_capacity_roster(proof["signed_profile"], device_id=receipt["profile"]["device_id"],
                route_generation=receipt["route_generation"], trusted_owner_public_key=self.capacity_owner_public_key,
                load_receipt=raws[0], closure_receipt=raws[1])
            if verified.receipt() != receipt: raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise JournalError("NATIVE_CAPACITY_UNQUALIFIED") from None
        return receipt

    def request_terminal_recovery(self, operation_id, global_job_id, *, device_id,
                                  current_route_generation, current_session_id):
        """Issue read-only historical challenge; never change the original job."""
        _id(operation_id); _id(device_id, "dev_"); _integer(current_route_generation); _id(current_session_id)
        with self.transaction():
            self._ready(); rec = self._row(global_job_id)
            if rec["target"]["device_id"] != device_id or rec["local_job_id"] is None or rec["session_id"] is None:
                raise JournalError("HISTORICAL_RECOVERY_UNAVAILABLE")
            original = {k: rec[k] for k in ("global_job_id", "local_job_id", "node_operation_id", "request_sha256", "target", "session_id")}
            current = {"device_id": device_id, "route_generation": current_route_generation, "session_id": current_session_id}
            old = self._db.execute("SELECT record FROM recoveries WHERE operation_id=?", (operation_id,)).fetchone()
            if old:
                receipt = _decode(old[0])
                if receipt["original"] != original or receipt["current"] != current:
                    raise JournalError("IDEMPOTENCY_CONFLICT")
                return receipt
            if self._db.execute("SELECT count(*) FROM recoveries").fetchone()[0] >= self.policy["max_records"]:
                raise JournalError("JOURNAL_CAPACITY")
            receipt = {"schema": "fleet.native-recovery/1", "operation_id": operation_id,
                "recovery_id": "frecovery_" + uuid.uuid4().hex, "challenge": uuid.uuid4().hex,
                "original": original, "current": current, "state": "ISSUED", "result": None, "witness_sha256": None}
            self._bound(receipt)
            self._db.execute("INSERT INTO recoveries VALUES (?,?,?)", (operation_id, receipt["recovery_id"], canonical(receipt).decode()))
            return receipt

    def poll_terminal_recoveries(self, device_id, *, route_generation, session_id, max_commands):
        _id(device_id, "dev_"); _integer(route_generation); _id(session_id); _integer(max_commands)
        if max_commands > 16: raise JournalError("INVALID_RECOVERY_COMMAND")
        with self._mutex:
            self._ready(); commands = []
            for row in self._db.execute("SELECT record FROM recoveries ORDER BY rowid"):
                recovery = _decode(row[0])
                if recovery["state"] != "ISSUED" or recovery["current"] != {"device_id": device_id, "route_generation": route_generation, "session_id": session_id}: continue
                commands.append({"schema": "fleet.native-recovery-command/1", "kind": "NATIVE_RECOVERY",
                    "command_id": recovery["recovery_id"], **{k: recovery[k] for k in ("recovery_id", "challenge", "original", "current")}})
                if len(commands) == max_commands: break
            return commands

    def commit_terminal_recovery(self, witness, *, registered_public_key, current_route_generation, current_session_id):
        try:
            if not isinstance(witness, dict) or set(witness) != {"body", "signature"}: raise ValueError()
            body = witness["body"]; self._bound(body)
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(registered_public_key)).verify(
                bytes.fromhex(witness["signature"]), b"fleet.native-terminal-witness/1\n" + canonical(body))
            if set(body) != {"schema", "recovery_id", "challenge", "original", "current", "record", "effect_head_sha256"} or body["schema"] != "fleet.native-terminal-witness/1": raise ValueError()
        except (TypeError, ValueError, KeyError, InvalidSignature):
            raise JournalError("HISTORICAL_WITNESS_INVALID") from None
        with self.transaction():
            self._ready()
            old = self._db.execute("SELECT record FROM recoveries WHERE recovery_id=?", (_id(body["recovery_id"], "frecovery_"),)).fetchone()
            if old is None: raise JournalError("HISTORICAL_WITNESS_INVALID")
            recovery = _decode(old[0]); rec = self._row(recovery["original"]["global_job_id"])
            if (body["challenge"] != recovery["challenge"] or body["original"] != recovery["original"]
                    or body["current"] != recovery["current"]
                    or body["current"]["route_generation"] != current_route_generation
                    or body["current"]["session_id"] != current_session_id):
                raise JournalError("HISTORICAL_WITNESS_SCOPE_MISMATCH")
            observed = body["record"]
            required = {"schema", "global_job_id", "operation_id", "node_operation_id", "request_sha256", "request", "target", "state", "sequence",
                "local_job_id", "session_id", "result", "quarantined_evidence", "journal_high_water"}
            if (not isinstance(observed, dict) or not required <= set(observed)
                    or set(observed) - required - {"start_authorization", "authorization_challenges", "active_process", "terminal_closure"}
                    or observed["schema"] != "fleet.job/1" or observed["request"] != rec["request"]
                    or observed["operation_id"] != rec["node_operation_id"]
                    or any(observed.get(k) != v for k, v in recovery["original"].items())
                    or observed.get("state") not in TERMINAL or not isinstance(observed.get("result"), dict)):
                raise JournalError("HISTORICAL_WITNESS_UNRESOLVED")
            _integer(observed["sequence"]); _integer(observed["journal_high_water"])
            _validate_witness_record(observed, rec)
            if re.fullmatch(r"[a-f0-9]{64}", body["effect_head_sha256"]) is None: raise JournalError("HISTORICAL_WITNESS_INVALID")
            if recovery["state"] == "COMPLETED":
                if recovery["witness_sha256"] != digest(witness): raise JournalError("HISTORICAL_WITNESS_CONFLICT")
                return recovery["result"]
            result = {"schema": "fleet.historical-native-result/1", "recovery_id": recovery["recovery_id"],
                "original": recovery["original"], "current": recovery["current"], "record": observed,
                "classification": "HISTORICAL_QUARANTINED", "witness_sha256": digest(witness)}
            self._bound(result); recovery.update(state="COMPLETED", result=result, witness_sha256=digest(witness))
            self._db.execute("UPDATE recoveries SET record=? WHERE recovery_id=?", (canonical(recovery).decode(), recovery["recovery_id"]))
            return result

    def install_capacity_roster(self, verified_roster):
        from .scoped_resources import VerifiedCapacityRoster
        if type(verified_roster) is not VerifiedCapacityRoster:
            raise JournalError("SCOPED_ROSTER_UNVERIFIED")
        receipt = verified_roster.receipt(); self._bound(receipt)
        self._verify_capacity_receipt(receipt)
        with self.transaction():
            self._ready(); rosters = self._meta("capacity_rosters")
            device = receipt["profile"]["device_id"]
            old = rosters.get(device)
            if old is not None and old["route_generation"] > receipt["route_generation"]:
                raise JournalError("STALE_ROUTE_GENERATION")
            if device not in rosters and len(rosters) >= self.policy["max_records"]:
                raise JournalError("JOURNAL_CAPACITY")
            rosters[device] = receipt; self._meta("capacity_rosters", rosters)
            return receipt

    def capacity_for_node(self, device_id, route_generation):
        with self._mutex:
            roster = self._meta("capacity_rosters").get(device_id)
            if roster is not None: self._verify_capacity_receipt(roster)
            return roster["profile"]["capacity"] if roster and roster["route_generation"] == route_generation else 1

    def mapping_sha256(self):
        with self._mutex:
            mappings = [{k: rec[k] for k in ("operation_id", "global_job_id", "node_operation_id", "request_sha256", "target")}
                for rec in [_decode(r[0]) for r in self._db.execute("SELECT record FROM jobs ORDER BY global_job_id")]]
            return digest(mappings)

    def restore_state(self):
        with self._mutex:
            return self._meta("restore")

    def coordinated_restore_receipt(self):
        with self._mutex:
            return self._meta("coordinated_restore")

    def prepare_coordinated_restore(self, coordination_sha256, jointscope):
        if (not isinstance(jointscope, dict) or jointscope.get("schema") != "fleet.joint-restore/1"
                or coordination_sha256 != digest(jointscope)
                or jointscope.get("job_mapping_sha256") != self.mapping_sha256()
                or not isinstance(jointscope.get("devices"), list) or not jointscope["devices"]):
            raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
        devices = [row["device_id"] for row in jointscope["devices"]]
        for device in devices: _id(device, "dev_")
        if len(set(devices)) != len(devices): raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
        _integer(jointscope["job_export_generation"])
        if re.fullmatch(r"[a-f0-9]{32}", jointscope.get("challenge", "")) is None:
            raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
        with self.transaction():
            old = self._meta("coordinated_restore")
            if old is not None:
                if old["coordination_sha256"] != coordination_sha256:
                    raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
                return old
            scope = self._meta("restore")
            if scope is not None and (scope["challenge"] != jointscope["challenge"]
                    or set(scope["devices"]) != set(devices)):
                raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
            self._meta("restore", {"schema": "fleet.restore/1", "challenge": jointscope["challenge"],
                "export_generation": jointscope["job_export_generation"], "devices": sorted(devices), "reconciled": []})
            receipt = {"schema": "fleet.job-restore-receipt/1", "phase": "PREPARING",
                "coordination_sha256": coordination_sha256, "scope": jointscope,
                "mapping_sha256": self.mapping_sha256(), "witnesses": {}}
            self._bound(receipt); self._meta("coordinated_restore", receipt)
            return receipt

    def finalize_coordinated_restore(self, control_commit):
        from .restore_coordination import ControlRestoreCommit
        if not isinstance(control_commit, ControlRestoreCommit):
            raise JournalError("CONTROL_COMMIT_UNVERIFIED")
        control_commit.assert_for(self)
        with self.transaction():
            receipt = self._meta("coordinated_restore")
            if receipt is None or receipt["phase"] not in {"PREPARED", "FINALIZED"}:
                raise JournalError("JOINT_RESTORE_UNPREPARED")
            receipt["phase"] = "FINALIZED"
            self._meta("coordinated_restore", receipt); self._meta("restore", None)
            return receipt

    def authorize_start(self, device_id, *, route_generation, session_id, global_job_id,
                        node_operation_id, request_sha256, frozen_target, now_ms, ttl_ms,
                        signer, local_job_id, phase, sequence, challenge, event="phase_admission", predecessor=None,
                        process_sha256=None):
        """One durable start authorization, supplied over authenticated HTTPS.

        The service event owner rechecks enrollment immediately before this call.
        An expired/lost grant is uncertainty, never permission to issue a new grant.
        """
        _integer(now_ms, positive=False); _integer(ttl_ms); _id(session_id); _id(local_job_id); _integer(sequence)
        from .native_authorization import PHASES, effect_event, completion_receipt, advance_effect
        if phase not in PHASES:
            raise JournalError("NATIVE_AUTHORIZATION_INVALID")
        parsed = effect_event(phase, event)
        if predecessor is not None: predecessor = completion_receipt(predecessor)
        if parsed is None and predecessor is not None: raise JournalError("NATIVE_EFFECT_GRAPH_INVALID")
        authorization_key = digest({"global_job_id": global_job_id, "phase": phase, "sequence": sequence})
        with self.transaction():
            self._ready(); rec = self._row(global_job_id)
            if (rec["target"] != target(frozen_target) or rec["node_operation_id"] != node_operation_id
                    or rec["request_sha256"] != request_sha256 or rec["session_id"] != session_id
                    or rec["target"]["device_id"] != device_id or rec["target"]["route_generation"] != route_generation):
                raise JournalError("JOB_BINDING_MISMATCH")
            if rec["local_job_id"] not in (None, local_job_id):
                raise JournalError("JOB_BINDING_MISMATCH")
            if phase == "cancel":
                progress = (rec["result"] or {}).get("result") if isinstance(rec["result"], dict) else None
                observed = progress.get("process_identity") if isinstance(progress, dict) else None
                if (not _identity_valid(observed) or process_sha256 != digest(observed)
                        or rec["state"] not in {"STARTING", "RUNNING", "RESULT_PENDING"}):
                    raise JournalError("PROCESS_IDENTITY_UNPROVEN")
            elif process_sha256 is not None:
                raise JournalError("NATIVE_AUTHORIZATION_INVALID")
            old = self._db.execute("SELECT receipt FROM starts WHERE authorization_key=?", (authorization_key,)).fetchone()
            if old:
                grant = _decode(old[0])
                body = grant["body"]
                if (body["local_job_id"] != local_job_id or body["challenge"] != challenge
                        or body["sequence"] != sequence or body["event"] != event
                        or body["process_sha256"] != process_sha256):
                    raise JournalError("NATIVE_AUTHORIZATION_MISMATCH")
                if parsed is not None:
                    step = next((s for s in self._effect_history(global_job_id) if s["sequence"] == sequence), None)
                    if step is None or step["predecessor_sha256"] != (digest(predecessor) if predecessor else None):
                        raise JournalError("NATIVE_AUTHORIZATION_MISMATCH")
                if now_ms < body["issued_ms"]:
                    raise JournalError("CLOCK_ROLLBACK")
                if now_ms >= body["expires_ms"]:
                    raise JournalError("START_AUTHORIZATION_UNRESOLVED")
                return grant
            if rec["state"] not in {"DELIVERED", "RESERVED", "STARTING", "RUNNING", "RESULT_PENDING"}:
                raise JournalError("START_AUTHORIZATION_UNAVAILABLE")
            if self._db.execute("SELECT count(*) FROM starts").fetchone()[0] >= self.policy["max_records"]:
                raise JournalError("JOURNAL_CAPACITY")
            if parsed is not None:
                history = self._effect_history(global_job_id)
                lane = [s for s in history if effect_event(s["phase"], s["event"])["lane"] == parsed["lane"]]
                if history and sequence <= history[-1]["sequence"]:
                    raise JournalError("NATIVE_EFFECT_GRAPH_INVALID")
                if lane:
                    if predecessor is None: raise JournalError("NATIVE_EFFECT_UNRESOLVED")
                    self._complete_gateway_effect(global_job_id, predecessor, expected=lane[-1])
                    history = self._effect_history(global_job_id)
                elif predecessor is not None:
                    raise JournalError("NATIVE_EFFECT_GRAPH_INVALID")
                advance_effect(history, phase, event)
            grant = signer.issue(issued_ms=now_ms, expires_ms=_integer(now_ms + ttl_ms),
                authorization_id="start_" + uuid.uuid4().hex, audience=signer.audience,
                global_job_id=global_job_id, local_job_id=local_job_id, node_operation_id=node_operation_id,
                request_sha256=request_sha256, target=rec["target"], session_id=session_id,
                phase=phase, sequence=sequence, challenge=challenge, event=event, process_sha256=process_sha256)
            if rec["local_job_id"] is None:
                rec.update(local_job_id=local_job_id, sequence=rec["sequence"] + 1)
                self._save(rec)
            self._db.execute("INSERT INTO starts VALUES (?,?)", (authorization_key, canonical(grant).decode()))
            if parsed is not None:
                self._save_effect({"schema": "fleet.native-effect-intent/1", "global_job_id": global_job_id,
                    "sequence": sequence, "phase": phase, "event": event, "challenge": challenge,
                    "state": "INTENT", "grant_sha256": digest(grant), "completion": None,
                    "predecessor_sha256": digest(predecessor) if predecessor else None}, insert=True)
            return grant

    def _complete_gateway_effect(self, global_job_id, completion, *, expected=None):
        from .native_authorization import completion_receipt
        completion = completion_receipt(completion)
        step = expected or next((s for s in self._effect_history(global_job_id)
            if s["sequence"] == completion["sequence"]), None)
        if step is None or any(step[k] != completion[k] for k in ("sequence", "phase", "event", "challenge", "grant_sha256")):
            raise JournalError("NATIVE_EFFECT_COMPLETION_INVALID")
        if step["completion"] is not None and step["completion"] != completion:
            raise JournalError("NATIVE_EFFECT_COMPLETION_CONFLICT")
        key = digest({"global_job_id": global_job_id, "phase": step["phase"], "sequence": step["sequence"]})
        issued = self._db.execute("SELECT receipt FROM starts WHERE authorization_key=?", (key,)).fetchone()
        if issued is None or digest(_decode(issued[0])) != completion["grant_sha256"]:
            raise JournalError("NATIVE_EFFECT_COMPLETION_INVALID")
        step.update(state=completion["outcome"], completion=completion)
        self._save_effect(step)
        return step

    @classmethod
    def restore_backup(cls, backup_path, destination, *, devices, export_generation, **policy):
        """Supported restore fences a temporary copy before publishing its path."""
        destination = Path(destination).resolve()
        if destination.exists():
            raise JournalError("RESTORE_EXISTS")
        temporary = destination.with_name(destination.name + ".restore-" + uuid.uuid4().hex)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with cls(backup_path, **policy) as original:
                original.backup(temporary)
            with cls(temporary, **policy) as restored:
                restored.begin_restore(devices=devices, export_generation=export_generation)
            os.link(temporary, destination)
            return cls(destination, **policy)
        finally:
            temporary.unlink(missing_ok=True)

    def submit(self, operation_id, request):
        _id(operation_id); sha = request_hash(request); self._bound(request)
        with self.transaction():
            self._ready()
            row = self._db.execute("SELECT record FROM jobs WHERE operation_id=?", (operation_id,)).fetchone()
            if row:
                rec = _decode(row[0])
                if rec["request_sha256"] != sha:
                    raise JournalError("IDEMPOTENCY_CONFLICT")
                return rec
            return self._insert({"schema": "fleet.job/1", "operation_id": operation_id,
                "global_job_id": "fjob_" + uuid.uuid4().hex, "node_operation_id": "fop_" + uuid.uuid4().hex,
                "request_sha256": sha, "request": _decode(canonical(request)), "target": target(request["placement"]["target"]),
                "state": "QUEUED", "sequence": 1, "local_job_id": None, "session_id": None,
                "result": None, "quarantined_evidence": []})

    def poll_for_node(self, device_id, *, route_generation, session_id, max_commands=1):
        _id(device_id, "dev_"); _integer(route_generation); _id(session_id); _integer(max_commands)
        with self.transaction():
            self._ready()
            roster = self._meta("capacity_rosters").get(device_id)
            if roster is not None: self._verify_capacity_receipt(roster)
            if roster is not None and roster["route_generation"] != route_generation: roster = None
            capacity = roster["profile"]["capacity"] if roster else 1
            if max_commands > capacity:
                raise JournalError("NATIVE_CAPACITY_UNQUALIFIED")
            commands = []
            records = [_decode(r[0]) for r in self._db.execute("SELECT record FROM jobs ORDER BY rowid")]
            active = [rec for rec in records if rec["target"]["device_id"] == device_id
                      and rec["state"] not in TERMINAL | {"QUEUED"}]
            # Unknown/revoked/in-flight work retains the node's one workload slot.
            if active and (len(active) > capacity or any(r["target"]["route_generation"] != route_generation for r in active)):
                return []
            if capacity == 1 and active and active[0]["state"] != "DELIVERED": return []
            selected = list(active)
            def resource_row(record):
                if roster is None: return None
                return next((row for row in roster["profile"]["terminals"]
                    if row["terminal_id"] == record["target"]["terminal_id"]
                    and row["terminal_generation"] == record["target"]["terminal_generation"]), None)
            def compatible(candidate):
                row = resource_row(candidate)
                if row is None: return False
                binding = candidate["request"]["placement"]["binding"]
                if any(binding.get(k) != row["resources"][k] for k in ("executable", "data_root")): return False
                for held in selected:
                    other = resource_row(held)
                    if other is None: return False
                    keys = {r["physical_key"] for r in row["physical_identities"]}
                    if keys & {r["physical_key"] for r in other["physical_identities"]}: return False
                    for x in row["physical_identities"]:
                        for y in other["physical_identities"]:
                            a, b = x["path"].replace("\\", "/").casefold(), y["path"].replace("\\", "/").casefold()
                            if a == b or a.startswith(b + "/") or b.startswith(a + "/"): return False
                return True
            delivered = [r for r in active if r["state"] == "DELIVERED"]
            queued = [r for r in records if r["state"] == "QUEUED"]
            for rec in delivered + queued:
                if (rec["target"]["device_id"] != device_id or rec["target"]["route_generation"] != route_generation
                        or rec["state"] not in {"QUEUED", "DELIVERED"}):
                    continue
                if rec["session_id"] not in (None, session_id):
                    raise JournalError("SESSION_MISMATCH")
                if rec["state"] == "QUEUED":
                    if len(selected) >= capacity: continue
                    if capacity > 1 and not compatible(rec): continue
                    rec.update(state="DELIVERED", sequence=rec["sequence"] + 1, session_id=session_id)
                    self._save(rec)
                    selected.append(rec)
                commands.append({"schema": "fleet.native-command/1", "kind": "NATIVE",
                    **{key: rec[key] for key in ("global_job_id", "node_operation_id", "request_sha256",
                         "request", "target", "session_id", "sequence")}, "command_id": rec["global_job_id"]})
                if len(commands) >= max_commands: break
            return commands

    def commit_node_result(self, device_id, *, route_generation, session_id, payload):
        if not isinstance(payload, dict) or set(payload) != {"schema", "global_job_id", "node_operation_id",
                "request_sha256", "target", "sequence", "local_job_id", "state", "result"} or payload["schema"] != "fleet.native-result/1":
            raise JournalError("INVALID_NATIVE_RESULT")
        self._bound(payload); target(payload["target"]); _integer(payload["sequence"])
        if payload["state"] not in STATES - {"QUEUED", "DELIVERED"}:
            raise JournalError("INVALID_NATIVE_RESULT")
        with self.transaction():
            rec = self._row(payload["global_job_id"])
            if any(payload[key] != rec[key] for key in ("node_operation_id", "request_sha256", "target")):
                raise JournalError("JOB_BINDING_MISMATCH")
            if device_id != rec["target"]["device_id"] or session_id != rec["session_id"]:
                raise JournalError("JOB_BINDING_MISMATCH")
            if route_generation != rec["target"]["route_generation"]:
                # Authenticated current-generation evidence can preserve an old result,
                # but cannot promote that result or start another effect.
                evidence = {"sha256": digest(payload), "reason": "REVOKED_GENERATION", "payload": payload}
                if evidence not in rec["quarantined_evidence"]:
                    rec["quarantined_evidence"].append(evidence); self._save(rec)
                return {"status": "QUARANTINED", "global_job_id": rec["global_job_id"]}
            self._ready()
            if rec["result"] == payload:
                return rec
            if rec["result"] is not None and rec["state"] in TERMINAL:
                if rec["result"] == payload:
                    return rec
                projection = rec["result"].get("result") if isinstance(rec["result"], dict) else None
                receipt = dict(payload["result"]) if isinstance(payload["result"], dict) else None
                if receipt is not None: receipt.pop("effect_completion", None)
                if (isinstance(projection, dict) and projection.get("schema") == "fleet.native-outcome-evidence/1"
                        and receipt is not None and digest(receipt) == projection["receipt_sha256"]
                        and payload["state"] == rec["state"] and payload["sequence"] == rec.get("node_sequence")
                        and payload["local_job_id"] == rec["local_job_id"]):
                    # Correlation fills the same observed receipt. It grants no
                    # effect and changes no outcome/target/sequence/capacity.
                    rec["result"] = payload
                    return self._save(rec)
                raise JournalError("RESULT_CONFLICT")
            if payload["sequence"] <= rec.get("node_sequence", 0):
                raise JournalError("RESULT_CONFLICT" if payload["sequence"] == rec.get("node_sequence", 0) else "STALE_SEQUENCE")
            if rec["local_job_id"] is not None and rec["local_job_id"] != payload["local_job_id"]:
                raise JournalError("JOB_BINDING_MISMATCH")
            if isinstance(payload["result"], dict) and "effect_completion" in payload["result"]:
                self._complete_gateway_effect(rec["global_job_id"], payload["result"]["effect_completion"])
            rec.update(state=payload["state"], local_job_id=payload["local_job_id"],
                       node_sequence=payload["sequence"], sequence=rec["sequence"] + 1, result=payload)
            return self._save(rec)

    def begin_restore(self, *, devices, export_generation):
        if not isinstance(devices, list) or not devices or len(set(devices)) != len(devices):
            raise JournalError("INVALID_RESTORE_SCOPE")
        for device in devices:
            _id(device, "dev_")
        _integer(export_generation)
        with self.transaction():
            if self._meta("restore") is not None:
                raise JournalError("RECONCILIATION_REQUIRED")
            scope = {"schema": "fleet.restore/1", "challenge": uuid.uuid4().hex,
                     "export_generation": export_generation, "devices": sorted(devices), "reconciled": []}
            self._meta("restore", scope)
            return scope

    def reconcile_node(self, witness, *, registered_public_key, current_route_generation, current_session_id):
        """Trusted service supplies freshly registered key/route, never caller flags.

        The signature covers the fresh restore challenge and every durable node row.
        Missing, unknown or unmapped rows keep dispatch fenced.
        """
        witness = self.validate_recovery_witness(witness, registered_public_key=registered_public_key,
            current_route_generation=current_route_generation, current_session_id=current_session_id)
        try:
            body, signature = witness["body"], bytes.fromhex(witness["signature"])
            if set(witness) != {"body", "signature"} or body["schema"] != "fleet.node-journal-witness/1":
                raise ValueError()
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(registered_public_key)).verify(
                signature, b"fleet.node-journal-witness/1\n" + canonical(body))
        except (ValueError, KeyError, TypeError, InvalidSignature):
            raise JournalError("WITNESS_INVALID") from None
        self._bound(body)
        with self.transaction():
            scope = self._meta("restore")
            coordinated = self._meta("coordinated_restore")
            if (scope is None or body.get("challenge") != scope["challenge"]
                    or body.get("export_generation") != scope["export_generation"]
                    or body.get("device_id") not in scope["devices"]
                    or body.get("route_generation") != current_route_generation
                    or body.get("session_id") != current_session_id
                    or not isinstance(body.get("records"), list)
                    or (not body["records"] and coordinated is None)):
                raise JournalError("WITNESS_SCOPE_MISMATCH")
            _integer(body.get("high_water"), positive=bool(body["records"]))
            body_fields = {"schema", "challenge", "export_generation", "device_id", "route_generation", "session_id", "high_water", "records"}
            if coordinated is not None:
                body_fields |= {"coordination_sha256", "joint_scope_sha256"}
                if (body.get("coordination_sha256") != coordinated["coordination_sha256"]
                        or body.get("joint_scope_sha256") != digest(coordinated["scope"])):
                    raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
            if set(body) != body_fields:
                raise JournalError("WITNESS_SCOPE_MISMATCH")
            prior_witness = coordinated["witnesses"].get(body["device_id"]) if coordinated is not None else None
            if prior_witness is not None and prior_witness != digest(witness):
                raise JournalError("JOURNAL_WITNESS_CONFLICT")
            seen = set()
            for observed in body["records"]:
                rec = self._row(observed["global_job_id"])
                if (observed["global_job_id"] in seen or any(observed[k] != rec[k] for k in
                        ("target", "node_operation_id", "request_sha256"))
                        or observed["target"]["device_id"] != body["device_id"]
                        or observed["state"] not in TERMINAL | {"RUNNING", "RESULT_PENDING"}
                        or observed["target"]["route_generation"] != current_route_generation
                        or observed["session_id"] != current_session_id
                        or type(observed["journal_high_water"]) is not int
                        or observed["journal_high_water"] > body["high_water"]):
                    raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
                seen.add(observed["global_job_id"])
                adopted = {"schema": "fleet.native-result/1", **{k: observed[k] for k in
                    ("global_job_id", "node_operation_id", "request_sha256", "target", "sequence", "local_job_id", "state", "result")}}
                previous = rec["result"].get("result") if isinstance(rec["result"], dict) else None
                if (isinstance(previous, dict) and previous.get("schema") != "fleet.native-outcome-evidence/1"
                        and digest({k: v for k, v in previous.items() if k != "effect_completion"}) == observed["result"]["receipt_sha256"]):
                    adopted["result"] = previous
                if prior_witness is not None:
                    if (rec["state"] != observed["state"] or rec["local_job_id"] != observed["local_job_id"]
                            or rec.get("node_sequence") != observed["sequence"] or rec["result"] != adopted):
                        raise JournalError("JOURNAL_WITNESS_CHANGED")
                    continue
                rec.update(state=observed["state"], local_job_id=observed["local_job_id"],
                    node_sequence=observed["sequence"], sequence=rec["sequence"] + 1,
                    result=adopted)
                self._save(rec)
            expected = {_decode(r[0])["global_job_id"] for r in self._db.execute("SELECT record FROM jobs")
                        if _decode(r[0])["target"]["device_id"] == body["device_id"]}
            if seen != expected:
                raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
            if prior_witness is not None:
                return {"status": "RECONCILIATION_REQUIRED"}
            if body["device_id"] not in scope["reconciled"]:
                scope["reconciled"].append(body["device_id"])
            complete = set(scope["reconciled"]) == set(scope["devices"])
            if coordinated is not None:
                coordinated["witnesses"][body["device_id"]] = digest(witness)
                if complete:
                    coordinated["phase"] = "PREPARED"
                self._meta("coordinated_restore", coordinated)
            self._meta("restore", None if complete and coordinated is None else scope)
            return {"status": "RECONCILED" if self._meta("restore") is None else "RECONCILIATION_REQUIRED"}

    def validate_recovery_witness(self, witness, *, registered_public_key, current_route_generation, current_session_id):
        """Pure finite admission check before a coordinator persists an envelope."""
        try:
            self._bound(witness)
            if (not isinstance(witness, dict) or set(witness) != {"body", "signature"}
                    or not isinstance(witness["signature"], str) or re.fullmatch(r"[a-f0-9]{128}", witness["signature"]) is None): raise ValueError()
            body = witness["body"]
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(registered_public_key)).verify(
                bytes.fromhex(witness["signature"]), b"fleet.node-journal-witness/1\n" + canonical(body))
            with self._mutex:
                scope, coordinated = self._meta("restore"), self._meta("coordinated_restore")
                fields = {"schema", "challenge", "export_generation", "device_id", "route_generation", "session_id", "high_water", "records"}
                if coordinated is not None: fields |= {"coordination_sha256", "joint_scope_sha256"}
                if (not isinstance(body, dict) or set(body) != fields or body["schema"] != "fleet.node-journal-witness/1"
                        or scope is None or body["challenge"] != scope["challenge"] or body["export_generation"] != scope["export_generation"]
                        or body["device_id"] not in scope["devices"] or body["route_generation"] != current_route_generation
                        or body["session_id"] != current_session_id or not isinstance(body["records"], list)
                        or len(body["records"]) > self.policy["max_records"] or (not body["records"] and coordinated is None)):
                    raise JournalError("WITNESS_SCOPE_MISMATCH")
                _integer(body["high_water"], positive=bool(body["records"]))
                if coordinated is not None and (body["coordination_sha256"] != coordinated["coordination_sha256"]
                        or body["joint_scope_sha256"] != digest(coordinated["scope"])): raise JournalError("JOINT_RESTORE_SCOPE_MISMATCH")
                seen = set()
                for observed in body["records"]:
                    expected = self._row(observed["global_job_id"])
                    _validate_witness_record(observed, expected)
                    if (observed["global_job_id"] in seen or observed["state"] not in TERMINAL
                            or observed["target"]["device_id"] != body["device_id"]
                            or observed["target"]["route_generation"] != current_route_generation
                            or observed["session_id"] != current_session_id or observed["journal_high_water"] > body["high_water"]):
                        raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
                    seen.add(observed["global_job_id"])
                expected = {_decode(row[0])["global_job_id"] for row in self._db.execute("SELECT record FROM jobs")
                    if _decode(row[0])["target"]["device_id"] == body["device_id"]}
                if seen != expected: raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
            return _decode(canonical(witness))
        except (ValueError, TypeError, KeyError, InvalidSignature):
            raise JournalError("WITNESS_INVALID") from None


class NodeJobJournal(_Journal):
    role = "NODE"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A crash may have crossed a callback boundary. Reopening never retries it.
        with self.transaction():
            for row in self._db.execute("SELECT record FROM jobs").fetchall():
                rec = _decode(row[0])
                if rec["state"] in {"RESERVED", "STARTING"}:
                    rec.update(state="UNKNOWN", sequence=rec["sequence"] + 1)
                    self._save(rec)
            for row in self._db.execute("SELECT record FROM effects").fetchall():
                step = _decode(row[0])
                if step["state"] in {"INTENT", "CONSUMED"}:
                    step["state"] = "UNKNOWN"; self._save_effect(step)

    def receive(self, command, *, device_id, route_generation, session_id):
        required = {"schema", "kind", "global_job_id", "command_id", "node_operation_id", "request_sha256",
                    "request", "target", "session_id", "sequence"}
        if not isinstance(command, dict) or set(command) != required or command["schema"] != "fleet.native-command/1" or command["kind"] != "NATIVE":
            raise JournalError("INVALID_NATIVE_COMMAND")
        sha = request_hash(command["request"]); frozen = target(command["target"])
        if (sha != command["request_sha256"] or frozen != command["request"]["placement"]["target"]
                or command["global_job_id"] != command["command_id"]
                or frozen["device_id"] != device_id or frozen["route_generation"] != route_generation
                or command["session_id"] != session_id):
            raise JournalError("JOB_BINDING_MISMATCH")
        _id(command["global_job_id"]); _id(command["node_operation_id"]); _integer(command["sequence"])
        with self.transaction():
            self._ready()
            row = self._db.execute("SELECT record FROM jobs WHERE global_job_id=?", (command["global_job_id"],)).fetchone()
            if row:
                rec = _decode(row[0])
                if any(rec[k] != command[k] for k in ("request_sha256", "node_operation_id", "target", "session_id")):
                    raise JournalError("IDEMPOTENCY_CONFLICT")
                return rec
            return self._insert({"schema": "fleet.job/1", "operation_id": command["node_operation_id"],
                **{key: command[key] for key in ("global_job_id", "node_operation_id", "request_sha256",
                     "request", "target", "session_id")}, "state": "DELIVERED", "sequence": 1,
                "local_job_id": None, "result": None, "quarantined_evidence": []})

    def execute(self, global_job_id, adapter, *, start_authorize, authorization_verifier, now_ms=None):
        now_ms = now_ms or (lambda: int(time.time() * 1000))
        with self.transaction():
            self._ready(); rec = self._row(global_job_id)
            if rec["state"] != "DELIVERED":
                return rec
            rec.update(state="RESERVED", sequence=rec["sequence"] + 1, local_job_id=new_job_id(),
                authorization_challenges={phase: uuid.uuid4().hex for phase in
                    ("reserve", "deploy", "start", "test", "capture", "cancel", "result")})
            self._save(rec)
        try:
            authorization_sequence = rec["sequence"]
            def authorize_phase(phase, expected=None):
                value = {**rec, "authorization_phase": phase,
                         "authorization_challenge": rec["authorization_challenges"][phase],
                         "authorization_sequence": authorization_sequence,
                         "authorization_event": "phase_admission", "authorization_predecessor": None,
                         "authorization_process_sha256": None}
                grant = start_authorize(value)
                binding = {"audience": authorization_verifier.audience, "request_sha256": rec["request_sha256"],
                    "target": rec["target"], "phase": phase, "node_operation_id": rec["node_operation_id"],
                    "global_job_id": rec["global_job_id"], "local_job_id": rec["local_job_id"],
                    "session_id": rec["session_id"], "sequence": authorization_sequence,
                    "challenge": rec["authorization_challenges"][phase], "event": "phase_admission", "process_sha256": None}
                if expected is not None and expected != binding:
                    raise JournalError("NATIVE_AUTHORIZATION_MISMATCH")
                return authorization_verifier.verify(grant, **binding)
            reserve_proof = authorize_phase("reserve")
            self._hit("before_reserve")
            fence = {"target": rec["target"], "session_id": rec["session_id"],
                "global_job_id": rec["global_job_id"], "node_operation_id": rec["node_operation_id"],
                "local_job_id": rec["local_job_id"], "journal_sequence": rec["sequence"], "sequence": rec["sequence"],
                "phase": "reserve", "challenge": rec["authorization_challenges"]["reserve"], "authorization": reserve_proof,
                "authorization_provider": authorize_phase,
                "begin_effect": lambda phase, event: self.begin_effect(global_job_id, phase, event,
                    start_authorize=start_authorize, authorization_verifier=authorization_verifier),
                "complete_effect": lambda phase, event, proof, **kwargs: self.complete_effect(global_job_id,
                    phase, event, proof, **kwargs),
                "publish_process": lambda observed, phase: self.publish_bound_process(rec["global_job_id"],
                    observed, phase=phase, local_job_id=rec["local_job_id"], request_sha256=rec["request_sha256"]),
                "session_sha256": rec["request"]["placement"]["session"]["revision_sha256"]}
            reservation = adapter.reserve(rec["request"], rec["node_operation_id"], exact_fence=fence)
            self._hit("after_reserve")
            if reservation.get("status") == "DENIED":
                return self._outcome(rec, "FAILED", reservation)
            local_job_id = _id(reservation["local_job_id"])
            if local_job_id != rec["local_job_id"]:
                raise JournalError("JOB_BINDING_MISMATCH")
            proof = authorize_phase("start")
            with self.transaction():
                current = self._row(global_job_id)
                if current["state"] != "RESERVED":
                    raise JournalError("STALE_SEQUENCE")
                current.update(local_job_id=local_job_id, state="STARTING", sequence=current["sequence"] + 1,
                               start_authorization={"phase": "start", "challenge": rec["authorization_challenges"]["start"]})
                rec = self._save(current)
            self._hit("before_start")
            fence.update(authorization=proof, phase="start", challenge=rec["authorization_challenges"]["start"],
                         authorization_provider=authorize_phase)
            result = adapter.start_reserved(local_job_id, rec["request"], fence)
            self._hit("after_start")
            if result.get("schema") == "fleet.native.effect/1" and result.get("phase") == "start":
                payload = result.get("payload", {})
                execution_status = payload.get("execution", {}).get("status")
                completion_reason = payload.get("execution", {}).get("completion_reason", "")
                if isinstance(completion_reason, str) and completion_reason.startswith("CANCEL_REQUESTED"):
                    outcome = "CANCELLED"
                elif result.get("evidence") == "OPERATOR_APPROVED_REAL_NATIVE":
                    outcome = "SUCCEEDED" if execution_status == "COMPLETED" else "FAILED"
                else:
                    outcome = {"COMPLETED": "SUCCEEDED", "FAILED": "FAILED"}.get(execution_status, "RUNNING")
                result = {**result, "state": outcome, "process_identity": payload.get("process")}
            state = result.get("state", "FAILED" if result.get("status") == "DENIED" else "UNKNOWN")
            if state not in TERMINAL | {"RUNNING", "RESULT_PENDING", "UNKNOWN", "RECOVERY_REQUIRED"}:
                state = "UNKNOWN"
            if state in TERMINAL and callable(getattr(adapter, "terminal_closure", None)):
                closed = terminal_closure(adapter.terminal_closure(local_job_id, rec["request"]), rec)
                with self.transaction():
                    current = self._row(global_job_id); current["terminal_closure"] = closed; self._save(current)
            return self._outcome(rec, state, result)
        except Exception as error:
            if getattr(error, "code", None) == "NATIVE_QUALIFICATION_UNAVAILABLE":
                return self._outcome(rec, "FAILED", {"status": "DENIED", "reason_code": "NATIVE_QUALIFICATION_UNAVAILABLE"})
            return self._outcome(rec, "UNKNOWN", {"reason_code": "EXECUTION_OUTCOME_UNKNOWN"})

    def _outcome(self, rec, state, result):
        with self.transaction():
            current = self._row(rec["global_job_id"])
            if state in TERMINAL and isinstance(result, dict) and result.get("evidence") == "OPERATOR_APPROVED_REAL_NATIVE":
                from .native_authorization import effect_event
                native = [s for s in self._effect_history(rec["global_job_id"])
                    if effect_event(s["phase"], s["event"])["lane"] == "native"]
                if not native or native[-1]["event"] != "result_promote:0001" or native[-1]["completion"] is None:
                    state = "UNKNOWN"
            current.update(state=state, sequence=current["sequence"] + 1, result=result)
            return self._save(current)

    def begin_effect(self, global_job_id, phase, event, *, start_authorize, authorization_verifier):
        """Persist a finite producer intent, then consume its fresh exact proof.

        Repeating this callback never repeats an action. An interrupted intent is
        UNKNOWN and can only be reconciled; clocks cannot advance the event graph.
        """
        from .native_authorization import effect_event, advance_effect
        parsed = effect_event(phase, event)
        if parsed is None: raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
        with self.transaction():
            self._ready(); rec = self._row(global_job_id)
            if rec["state"] not in {"RESERVED", "STARTING", "RUNNING", "RESULT_PENDING"}:
                raise JournalError("NATIVE_EFFECT_UNAVAILABLE")
            history = self._effect_history(global_job_id)
            advance_effect(history, phase, event)
            lane = [s for s in history if effect_event(s["phase"], s["event"])["lane"] == parsed["lane"]]
            predecessor = lane[-1]["completion"] if lane else None
            process = rec.get("active_process") or (rec["result"].get("process_identity") if isinstance(rec["result"], dict) else None)
            if phase == "cancel" and not _identity_valid(process):
                raise JournalError("PROCESS_IDENTITY_UNPROVEN")
            process_sha256 = digest(process) if phase == "cancel" else None
            sequence = max([rec["sequence"]] + [s["sequence"] for s in history]) + 1
            step = {"schema": "fleet.native-effect-intent/1", "global_job_id": global_job_id,
                "sequence": sequence, "phase": phase, "event": event, "challenge": uuid.uuid4().hex,
                "state": "INTENT", "grant_sha256": None, "completion": None,
                "predecessor_sha256": digest(predecessor) if predecessor else None}
            self._save_effect(step, insert=True)
            rec.update(sequence=rec["sequence"] + 1); self._save(rec)
        try:
            self._hit("before_effect_authorization")
            grant = start_authorize({**rec, "authorization_phase": phase, "authorization_event": event,
                "authorization_sequence": sequence, "authorization_challenge": step["challenge"],
                "authorization_predecessor": predecessor, "authorization_process_sha256": process_sha256})
            binding = {"audience": authorization_verifier.audience, "request_sha256": rec["request_sha256"],
                "target": rec["target"], "phase": phase, "node_operation_id": rec["node_operation_id"],
                "global_job_id": global_job_id, "local_job_id": rec["local_job_id"], "session_id": rec["session_id"],
                "sequence": sequence, "challenge": step["challenge"], "event": event, "process_sha256": process_sha256}
            proof = authorization_verifier.verify(grant, **binding)
            with self.transaction():
                current = next(s for s in self._effect_history(global_job_id) if s["sequence"] == sequence)
                if current["state"] != "INTENT": raise JournalError("NATIVE_EFFECT_UNRESOLVED")
                # This durable consumption precedes the producer's actual call.
                # The producer also rechecks proof.require at that call boundary.
                current.update(state="CONSUMED", grant_sha256=proof.grant_sha256)
                self._save_effect(current)
            self._hit("after_effect_consumption")
            return proof
        except Exception:
            with self.transaction():
                current = next(s for s in self._effect_history(global_job_id) if s["sequence"] == sequence)
                current["state"] = "UNKNOWN"; self._save_effect(current)
            raise

    def complete_effect(self, global_job_id, phase, event, proof, *, outcome="COMPLETED", evidence=None):
        from .native_authorization import NativeAuthorization, completion_receipt
        if type(proof) is not NativeAuthorization:
            raise JournalError("NATIVE_AUTHORIZATION_UNVERIFIED")
        binding = proof.binding
        if binding["global_job_id"] != global_job_id or binding["phase"] != phase or binding["event"] != event:
            raise JournalError("NATIVE_AUTHORIZATION_MISMATCH")
        descriptor = {"phase": phase, "event": event, "outcome": outcome} if evidence is None else evidence
        if len(canonical(descriptor)) > 1024: raise JournalError("NATIVE_EFFECT_COMPLETION_INVALID")
        receipt = completion_receipt({"schema": "fleet.native-effect-completion/1",
            "grant_sha256": proof.grant_sha256, "phase": phase, "event": event,
            "sequence": binding["sequence"], "challenge": binding["challenge"], "outcome": outcome,
            "evidence": {"kind": "NO_NATIVE_ATTEMPT" if outcome == "NOT_ATTEMPTED" else "PRODUCER_RETURNED",
                         "sha256": digest(descriptor)}})
        with self.transaction():
            history = self._effect_history(global_job_id)
            step = next((s for s in history if s["sequence"] == binding["sequence"]), None)
            if step is None or any(step[k] != receipt[k] for k in ("phase", "event", "challenge", "grant_sha256")):
                raise JournalError("NATIVE_EFFECT_COMPLETION_INVALID")
            if step["completion"] is not None:
                if step["completion"] != receipt: raise JournalError("NATIVE_EFFECT_COMPLETION_CONFLICT")
                return step["completion"]
            if step["state"] != "CONSUMED": raise JournalError("NATIVE_EFFECT_UNRESOLVED")
            # Truth can be recorded after expiry: no new action uses this proof.
            step.update(state=outcome, completion=receipt); self._save_effect(step)
            rec = self._row(global_job_id); rec.update(sequence=rec["sequence"] + 1); self._save(rec)
        self._hit("after_effect_completion")
        return receipt

    def publish_bound_process(self, global_job_id, observed, *, phase, local_job_id, request_sha256):
        if not isinstance(observed, ObservedProcess) or phase not in {"compile", "test"} or observed.exited():
            raise JournalError("PROCESS_IDENTITY_UNPROVEN")
        identity = observed.identity()
        with self.transaction():
            rec = self._row(global_job_id)
            if (rec["state"] != "STARTING" or rec["local_job_id"] != local_job_id
                    or rec["request_sha256"] != request_sha256):
                raise JournalError("JOB_BINDING_MISMATCH")
            rec.update(active_process=identity, sequence=rec["sequence"] + 1,
                result={"schema": "fleet.native-progress/1", "phase": phase,
                    "process_identity": identity, "evidence": "BOUND_NODE_PROCESS_IDENTITY"})
            return self._save(rec)

    def result_payload(self, global_job_id):
        rec = self.get(global_job_id)
        if rec["state"] in {"DELIVERED", "QUEUED"}:
            raise JournalError("RESULT_UNAVAILABLE")
        payload = {"schema": "fleet.native-result/1", **{k: rec[k] for k in
            ("global_job_id", "node_operation_id", "request_sha256", "target", "sequence",
             "local_job_id", "state", "result")}}
        with self._mutex:
            history = self._effect_history(global_job_id)
            if history and history[-1]["completion"] is not None and isinstance(payload["result"], dict):
                payload["result"] = {**payload["result"], "effect_completion": history[-1]["completion"]}
        return payload

    def _effect_fence(self, rec, phase, start_authorize, authorization_verifier, *, process=None):
        def provider(selected_phase, expected=None):
            grant = start_authorize({**rec, "authorization_phase": selected_phase,
                "authorization_sequence": rec["sequence"], "authorization_challenge": rec["authorization_challenges"][selected_phase],
                "authorization_event": "phase_admission", "authorization_predecessor": None,
                "authorization_process_sha256": digest(process) if selected_phase == "cancel" and _identity_valid(process) else None})
            binding = {"audience": authorization_verifier.audience, "request_sha256": rec["request_sha256"],
                "target": rec["target"], "phase": selected_phase, "node_operation_id": rec["node_operation_id"],
                "global_job_id": rec["global_job_id"], "local_job_id": rec["local_job_id"],
                "session_id": rec["session_id"], "sequence": rec["sequence"], "challenge": rec["authorization_challenges"][selected_phase],
                "event": "phase_admission", "process_sha256": digest(process) if selected_phase == "cancel" and _identity_valid(process) else None}
            if expected is not None and expected != binding: raise JournalError("NATIVE_AUTHORIZATION_MISMATCH")
            return authorization_verifier.verify(grant, **binding)
        proof = provider(phase)
        return {"target": rec["target"], "session_id": rec["session_id"], "node_operation_id": rec["node_operation_id"],
            "global_job_id": rec["global_job_id"], "local_job_id": rec["local_job_id"], "sequence": rec["sequence"],
            "challenge": rec["authorization_challenges"][phase], "phase": phase, "authorization": proof,
            "authorization_provider": provider, "process": process,
            "begin_effect": lambda selected_phase, event: self.begin_effect(rec["global_job_id"], selected_phase, event,
                start_authorize=start_authorize, authorization_verifier=authorization_verifier),
            "complete_effect": lambda selected_phase, event, proof, **kwargs: self.complete_effect(rec["global_job_id"],
                selected_phase, event, proof, **kwargs),
            "session_sha256": rec["request"]["placement"]["session"]["revision_sha256"]}

    def observe_result(self, global_job_id, adapter, *, start_authorize, authorization_verifier):
        with self.transaction():
            self._ready(); rec = self._row(global_job_id)
            if rec["state"] != "RUNNING":
                return rec
            process = rec["result"].get("process_identity")
            if not _identity_valid(process):
                raise JournalError("PROCESS_IDENTITY_UNPROVEN")
            rec.update(state="RESULT_PENDING", sequence=rec["sequence"] + 1)
            self._save(rec)
        try:
            fence = self._effect_fence(rec, "result", start_authorize, authorization_verifier, process=process)
            result = adapter.effect(rec["local_job_id"], "result", rec["request"], fence)
            state = result.get("payload", {}).get("state", "UNKNOWN")
            if state in TERMINAL and callable(getattr(adapter, "terminal_closure", None)):
                closed = terminal_closure(adapter.terminal_closure(rec["local_job_id"], rec["request"]), rec)
                with self.transaction():
                    current = self._row(global_job_id); current["terminal_closure"] = closed; self._save(current)
            return self._outcome(rec, state if state in TERMINAL else "UNKNOWN", result)
        except Exception:
            return self._outcome(rec, "UNKNOWN", {"reason_code": "RESULT_OUTCOME_UNKNOWN"})

    def cancel(self, operation_id, global_job_id, *, process_identity, adapter,
               start_authorize, authorization_verifier):
        _id(operation_id)
        if not _identity_valid(process_identity):
            raise JournalError("PROCESS_IDENTITY_UNPROVEN")
        logical = {"global_job_id": global_job_id, "process_identity": process_identity}
        sha = digest(logical)
        with self.transaction():
            prior = self._db.execute("SELECT * FROM cancels WHERE operation_id=?", (operation_id,)).fetchone()
            if prior:
                if prior["request_sha256"] != sha:
                    raise JournalError("IDEMPOTENCY_CONFLICT")
                return _decode(prior["receipt"])
            self._ready(); rec = self._row(global_job_id)
            exact_process = rec.get("active_process") or (rec["result"].get("process_identity") if isinstance(rec["result"], dict) else None)
            if exact_process != process_identity:
                raise JournalError("PROCESS_IDENTITY_UNPROVEN")
            receipt = {"status": "UNKNOWN", "reason_code": "CANCEL_OUTCOME_UNKNOWN", **logical}
            self._db.execute("INSERT INTO cancels VALUES (?,?,?)", (operation_id, sha, canonical(receipt).decode()))
        try:
            fence = self._effect_fence(rec, "cancel", start_authorize, authorization_verifier, process=process_identity)
            result = adapter.effect(rec["local_job_id"], "cancel", rec["request"], fence)
        except Exception:
            return receipt
        self._bound(result)
        with self.transaction():
            self._db.execute("UPDATE cancels SET receipt=? WHERE operation_id=?", (canonical(result).decode(), operation_id))
        return result

    def witness(self, scope, *, device_id, route_generation, session_id, private_key):
        with self._mutex:
            # A terminal job cannot conceal an uncertain separate cancel lane or
            # an unacknowledged producer boundary in the signed recovery witness.
            if any(_decode(row[0])["state"] in {"INTENT", "CONSUMED", "UNKNOWN"}
                    for row in self._db.execute("SELECT record FROM effects")):
                raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
            if any(_decode(row[0]).get("status") == "UNKNOWN"
                    for row in self._db.execute("SELECT receipt FROM cancels")):
                raise JournalError("JOURNAL_WITNESS_UNRESOLVED")
            records = [_decode(r[0]) for r in self._db.execute("SELECT record FROM jobs ORDER BY global_job_id")]
            records = [{**rec, "result": outcome_projection(rec)} for rec in records]
            body = {"schema": "fleet.node-journal-witness/1", "challenge": scope["challenge"],
                "export_generation": scope["export_generation"], "device_id": device_id,
                "route_generation": route_generation, "session_id": session_id,
                "high_water": self._meta("high_water"), "records": records}
            if "coordination_sha256" in scope:
                body["coordination_sha256"] = scope["coordination_sha256"]
                body["joint_scope_sha256"] = digest(scope["joint_scope"])
            self._bound(body)
            return {"body": body, "signature": private_key.sign(b"fleet.node-journal-witness/1\n" + canonical(body)).hex()}

    def terminal_recovery_witness(self, command, *, private_key):
        fields = {"schema", "kind", "command_id", "recovery_id", "challenge", "original", "current"}
        if (not isinstance(command, dict) or set(command) != fields
                or command["schema"] != "fleet.native-recovery-command/1" or command["kind"] != "NATIVE_RECOVERY"
                or command["command_id"] != command["recovery_id"]): raise JournalError("INVALID_RECOVERY_COMMAND")
        self._bound(command); _id(command["recovery_id"], "frecovery_")
        with self.transaction():
            self._ready(); rec = self._row(command["original"]["global_job_id"])
            if (any(rec.get(k) != v for k, v in command["original"].items())
                    or set(command["original"]) != {"global_job_id", "local_job_id", "node_operation_id", "request_sha256", "target", "session_id"}
                    or set(command["current"]) != {"device_id", "route_generation", "session_id"}
                    or command["current"]["device_id"] != rec["target"]["device_id"]
                    or rec["state"] not in TERMINAL): raise JournalError("HISTORICAL_WITNESS_UNRESOLVED")
            _id(command["current"]["session_id"]); _integer(command["current"]["route_generation"])
            if re.fullmatch(r"[a-f0-9]{32}", command["challenge"]) is None: raise JournalError("INVALID_RECOVERY_COMMAND")
            old = self._db.execute("SELECT record FROM recoveries WHERE recovery_id=?", (command["recovery_id"],)).fetchone()
            if old:
                stored = _decode(old[0])
                if any(stored[k] != command[k] for k in ("original", "current", "challenge")):
                    raise JournalError("HISTORICAL_WITNESS_CONFLICT")
                return stored["result"]
            history = self._effect_history(rec["global_job_id"])
            if any(s["completion"] is None for s in history): raise JournalError("HISTORICAL_WITNESS_UNRESOLVED")
            if any(_decode(row[0]).get("status") == "UNKNOWN" and _decode(row[0]).get("global_job_id") == rec["global_job_id"]
                    for row in self._db.execute("SELECT receipt FROM cancels")):
                raise JournalError("HISTORICAL_WITNESS_UNRESOLVED")
            if not _zero_effect_denial(rec): terminal_closure(rec.get("terminal_closure"), rec)
            body = {"schema": "fleet.native-terminal-witness/1", **{k: command[k] for k in ("recovery_id", "challenge", "original", "current")},
                "record": {**rec, "result": outcome_projection(rec)}, "effect_head_sha256": digest(history)}
            self._bound(body)
            signed = {"body": body, "signature": private_key.sign(b"fleet.native-terminal-witness/1\n" + canonical(body)).hex()}
            stored = {"schema": "fleet.native-recovery/1", "operation_id": command["recovery_id"],
                **{k: command[k] for k in ("recovery_id", "challenge", "original", "current")},
                "state": "COMPLETED", "result": signed, "witness_sha256": digest(signed)}
            if self._db.execute("SELECT count(*) FROM recoveries").fetchone()[0] >= self.policy["max_records"]:
                raise JournalError("JOURNAL_CAPACITY")
            self._bound(stored)
            self._db.execute("INSERT INTO recoveries VALUES (?,?,?)", (stored["operation_id"], stored["recovery_id"], canonical(stored).decode()))
            return signed
