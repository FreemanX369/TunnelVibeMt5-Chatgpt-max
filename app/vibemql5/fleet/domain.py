"""Finite durable gateway references and node-owned domain dispatch.

The gateway owns command identity, not project/source history. Native work keeps
its separate fleet.native/1 journal. No caller-selected URL, shell or worker runs.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.jobs import _exclusive_file_lock
from .wire import WireError, decode_body, encode_body, fields, integer, logical_digest, text, verified
from .read_broker import target

DOMAIN_OWNER_PATHS = frozenset({
    "/fleet/v1/info", "/fleet/v1/inventory", "/fleet/v1/commands/status",
    "/fleet/v1/projects/create", "/fleet/v1/projects/enroll", "/fleet/v1/projects/get",
    "/fleet/v1/projects/default-target", "/fleet/v1/projects/freeze", "/fleet/v1/projects/resume",
    "/fleet/v1/projects/baseline", "/fleet/v1/jobs/launch", "/fleet/v1/jobs/status", "/fleet/v1/jobs/cancel", "/fleet/v1/jobs/recover",
    "/fleet/v1/artifacts/manifest", "/fleet/v1/artifacts/chunk", "/fleet/v1/principals/issue",
    "/fleet/v1/principals/revoke", "/fleet/v1/principals/assign", "/fleet/v1/principals/release", "/fleet/v1/principals/reconcile",
})
DOMAIN_PRINCIPAL_PATHS = frozenset({
    "/fleet/v1/writers/acquire", "/fleet/v1/writers/release", "/fleet/v1/sources/write",
    "/fleet/v1/worktrees/prepare", "/fleet/v1/worktrees/commit", "/fleet/v1/worktrees/retire",
})
DOMAIN_NODE_PATHS = frozenset({"/fleet/v1/native/start", "/fleet/v1/reconcile", "/fleet/v1/writers/authorize", "/fleet/v1/capacity/register", "/fleet/v1/jobs/recovery-witness"})
_QUEUED_PATHS = {
    "/fleet/v1/inventory": "INVENTORY",
    **{path: "PROJECT" for path in DOMAIN_OWNER_PATHS if "/projects/" in path},
    **{path: "ARTIFACT" for path in DOMAIN_OWNER_PATHS if "/artifacts/" in path},
    "/fleet/v1/jobs/cancel": "CANCEL",
    "/fleet/v1/writers/fence": "SOURCE",
    "/fleet/v1/writers/reconcile": "SOURCE",
    **{path: "WORKTREE" if "/worktrees/" in path else "SOURCE" for path in DOMAIN_PRINCIPAL_PATHS},
}
_SCHEMA = "fleet.domain-journal/1"
_RECORD_FIELDS = {"schema", "command_id", "operation_id", "request_sha256", "path", "payload", "node", "kind", "state", "session_id", "sequence", "result"}
_HEAD_FIELDS = {"schema", "role", "sha256", "high_water", "record_count", "unresolved_count"}
_TABLES = {
    "meta": [("id", "INTEGER", 0, None, 1), ("value", "TEXT", 1, None, 0)],
    "commands": [("operation_id", "TEXT", 1, None, 0), ("command_id", "TEXT", 0, None, 1), ("record", "TEXT", 1, None, 0)],
}


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise WireError("DOMAIN_INVALID")
    return value


def _command_id(value):
    if type(value) is not str or re.fullmatch(r"dcmd_[0-9a-f]{32}", value) is None:
        raise WireError("DOMAIN_COMMAND_INVALID")
    return value


def _record(value, role, maximum):
    fields(value, _RECORD_FIELDS)
    _command_id(value["command_id"]); text(value["operation_id"], 160); _sha(value["request_sha256"])
    node_reference(value["node"])
    if (value["schema"] != "fleet.domain-record/1" or value["path"] not in _QUEUED_PATHS
            or value["kind"] != _QUEUED_PATHS[value["path"]] or type(value["payload"]) is not dict
            or value["request_sha256"] != logical_digest({key: value[key] for key in ("path", "node", "payload")})):
        raise WireError("DOMAIN_RECORD_INVALID")
    expected = {"QUEUED": 1, "DELIVERED": 2, "EXECUTING": 3, "COMPLETED": 4, "UNKNOWN": 4}
    if (value["state"] not in expected or type(value["sequence"]) is not int
            or value["sequence"] != expected[value["state"]]
            or (role == "GATEWAY" and value["state"] == "EXECUTING")
            or (role == "NODE" and value["state"] == "QUEUED")):
        raise WireError("DOMAIN_RECORD_INVALID")
    if value["state"] == "QUEUED":
        if value["session_id"] is not None:
            raise WireError("DOMAIN_RECORD_INVALID")
    else:
        text(value["session_id"], 64)
    if value["state"] in {"COMPLETED", "UNKNOWN"}:
        if type(value["result"]) is not dict:
            raise WireError("DOMAIN_RECORD_INVALID")
    elif value["result"] is not None:
        raise WireError("DOMAIN_RECORD_INVALID")
    encode_body(value, maximum)
    return value



@dataclass(frozen=True)
class DomainPolicy:
    max_records: int
    max_payload_bytes: int
    wait_ms: int
    max_commands: int
    start_authorization_ms: int

    def __post_init__(self):
        limits = {"max_records": 65536, "max_payload_bytes": 4194304, "wait_ms": 60000,
                  "max_commands": 64, "start_authorization_ms": 30000}
        for name, maximum in limits.items():
            integer(getattr(self, name), minimum=1, maximum=maximum)


def node_reference(value):
    fields(value, {"device_id", "route_generation"})
    import re
    if type(value["device_id"]) is not str or re.fullmatch(r"dev_[0-9a-f]{32}", value["device_id"]) is None:
        raise WireError("DOMAIN_NODE_INVALID")
    integer(value["route_generation"], minimum=1)
    return copy.deepcopy(value)


class DomainJournal:
    """One cooperative owning thread per durable finite command resource.

    An interrupted node callback remains UNKNOWN. Reopen never repeats it.
    Existing node domain operation receipts may later provide reconciliation;
    timeout/heartbeat alone cannot authorize a second source/native effect.
    """
    def __init__(self, path, *, policy, role, initialize=False):
        if type(policy) is not DomainPolicy or role not in {"GATEWAY", "NODE"} or type(initialize) is not bool:
            raise WireError("DOMAIN_INVALID")
        self.path, self.policy, self.role = Path(path).resolve(), policy, role
        self._thread, self._db, self._lock = threading.get_ident(), None, None
        self._principal_authority = None
        exists = self.path.exists()
        if exists and (not self.path.is_file() or self.path.stat().st_nlink != 1):
            raise WireError("DOMAIN_STORAGE_INVALID")
        if not exists and not initialize:
            raise WireError("DOMAIN_MISSING")
        if exists and initialize:
            raise WireError("DOMAIN_EXISTS")
        self._lock = _exclusive_file_lock(self.path.with_suffix(self.path.suffix + ".owner.lock"),
                                         timeout_seconds=policy.wait_ms / 1000)
        temporary = self.path.with_name("." + self.path.name + "." + uuid.uuid4().hex + ".initialize")
        try:
            self._lock.__enter__()
            if self.path.exists() != exists:
                raise WireError("DOMAIN_STATE_CHANGED")
            self._db = sqlite3.connect(temporary if not exists else self.path, timeout=policy.wait_ms / 1000, isolation_level=None)
            self._db.execute("PRAGMA synchronous=FULL")
            if not exists:
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("BEGIN IMMEDIATE")
                self._db.execute("CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
                self._db.execute("CREATE TABLE commands (operation_id TEXT UNIQUE NOT NULL, command_id TEXT PRIMARY KEY, record TEXT NOT NULL)")
                self._db.execute("INSERT INTO meta VALUES (1,?)", (encode_body({"schema": _SCHEMA, "role": role,
                    "policy": asdict(policy), "status": "READY", "restore": None}, policy.max_payload_bytes).decode("ascii"),))
                self._db.commit()
                self._validate()
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._db.close(); self._db = None
                os.replace(temporary, self.path)
                self._db = sqlite3.connect(self.path, timeout=policy.wait_ms / 1000, isolation_level=None)
                self._db.execute("PRAGMA synchronous=FULL")
            self._validate()
            if role == "NODE":
                self._db.execute("BEGIN IMMEDIATE")
                for row in self._rows():
                    if row["state"] == "EXECUTING":
                        row.update(state="UNKNOWN", result={"schema": "fleet.domain-failure/1", "code": "DOMAIN_OUTCOME_UNKNOWN"}, sequence=row["sequence"] + 1)
                        self._save(row)
                self._db.commit()
        except BaseException as error:
            self.close()
            if isinstance(error, WireError) or not isinstance(error, Exception):
                raise
            raise WireError("DOMAIN_BUSY" if isinstance(error, TimeoutError) else "DOMAIN_STORAGE_INVALID") from None
        finally:
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(temporary) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass

    def _open(self):
        if self._thread != threading.get_ident():
            raise WireError("DOMAIN_OWNER_REQUIRED")
        if self._db is None:
            raise WireError("DOMAIN_CLOSED")

    def close(self):
        if self._thread != threading.get_ident():
            raise WireError("DOMAIN_OWNER_REQUIRED")
        if self._db is not None:
            self._db.close(); self._db = None
        if self._lock is not None:
            self._lock.__exit__(None, None, None); self._lock = None

    def _decode(self, raw):
        if type(raw) is not str:
            raise WireError("DOMAIN_STORAGE_INVALID")
        body = raw.encode("utf-8")
        value = decode_body(body, self.policy.max_payload_bytes)
        if body != encode_body(value, self.policy.max_payload_bytes):
            raise WireError("DOMAIN_STORAGE_INVALID")
        return value

    def _validate(self):
        self._open()
        try:
            objects = set(self._db.execute("SELECT type,name,tbl_name FROM sqlite_master"))
            if objects != {("table", "meta", "meta"), ("table", "commands", "commands"),
                    ("index", "sqlite_autoindex_commands_1", "commands"),
                    ("index", "sqlite_autoindex_commands_2", "commands")}:
                raise ValueError()
            expected_sql = {
                "meta": "CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)",
                "commands": "CREATE TABLE commands (operation_id TEXT UNIQUE NOT NULL, command_id TEXT PRIMARY KEY, record TEXT NOT NULL)",
            }
            if dict(self._db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")) != expected_sql:
                raise ValueError()
            for name, column in (("sqlite_autoindex_commands_1", "operation_id"), ("sqlite_autoindex_commands_2", "command_id")):
                if [row[2] for row in self._db.execute("PRAGMA index_info(" + name + ")")] != [column]:
                    raise ValueError()
            for table, expected in _TABLES.items():
                if [tuple(row[1:]) for row in self._db.execute("PRAGMA table_info(" + table + ")")] != expected:
                    raise ValueError()
            if (self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                    or self._db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal"
                    or self._db.execute("SELECT count(*) FROM meta").fetchone()[0] != 1):
                raise ValueError()
            meta = self._meta()
            fields(meta, {"schema", "role", "policy", "status", "restore"})
            if (any(meta[key] != value for key, value in {"schema": _SCHEMA, "role": self.role,
                        "policy": asdict(self.policy)}.items())
                    or meta["status"] not in {"READY", "RECONCILIATION_REQUIRED"}):
                raise ValueError()
            if meta["restore"] is None:
                if meta["status"] != "READY":
                    raise ValueError()
            else:
                fields(meta["restore"], {"coordination_sha256", "expected_head", "phase"})
                if ((meta["status"] == "READY") != (meta["restore"]["phase"] == "FINALIZED")
                        or meta["restore"]["phase"] not in {"PREPARED", "FINALIZED"}):
                    raise ValueError()
                _sha(meta["restore"]["coordination_sha256"])
                head = meta["restore"]["expected_head"]
                fields(head, _HEAD_FIELDS); _sha(head["sha256"])
                if head["schema"] != "fleet.domain-head/1" or head["role"] != self.role or head["unresolved_count"] != 0:
                    raise ValueError()
                integer(head["high_water"], maximum=self.policy.max_records * 4)
                integer(head["record_count"], maximum=self.policy.max_records)
            self._rows()
        except (sqlite3.Error, ValueError, KeyError, TypeError, UnicodeError, WireError):
            raise WireError("DOMAIN_STORAGE_INVALID") from None

    def _rows(self):
        self._open()
        count, largest = self._db.execute("SELECT count(*), coalesce(max(length(CAST(record AS BLOB))),0) FROM commands").fetchone()
        if count > self.policy.max_records or largest > self.policy.max_payload_bytes:
            raise WireError("DOMAIN_STORAGE_INVALID")
        rows = []
        for operation_id, command_id, raw in self._db.execute("SELECT operation_id,command_id,record FROM commands ORDER BY rowid"):
            value = _record(self._decode(raw), self.role, self.policy.max_payload_bytes)
            if value["operation_id"] != operation_id or value["command_id"] != command_id:
                raise WireError("DOMAIN_STORAGE_INVALID")
            rows.append(value)
        return rows

    def _meta(self):
        self._open()
        row = self._db.execute("SELECT value,length(CAST(value AS BLOB)) FROM meta WHERE id=1").fetchone()
        if row is None or row[1] > self.policy.max_payload_bytes:
            raise WireError("DOMAIN_STORAGE_INVALID")
        return self._decode(row[0])

    def assert_dispatch_ready(self):
        if self._meta()["status"] != "READY":
            raise WireError("DOMAIN_RECONCILIATION_REQUIRED")

    def bind_principal_authority(self, authority):
        from .principals import GatewayPrincipalAuthority
        from .writers import NodePrincipalRuntime
        expected = GatewayPrincipalAuthority if self.role == "GATEWAY" else NodePrincipalRuntime
        if authority is self._principal_authority:
            return
        if type(authority) is not expected or self._principal_authority is not None:
            raise WireError("DOMAIN_PRINCIPAL_AUTHORITY_INVALID")
        self._principal_authority = authority

    def _resolutions(self, rows):
        bindings, resolved = [], set()
        if self._principal_authority is None:
            return bindings, resolved
        candidates = [row for row in rows if row["path"] == "/fleet/v1/writers/reconcile" and row["state"] == "COMPLETED"]
        for original in rows:
            if original["path"] != "/fleet/v1/sources/write" or original["state"] != "UNKNOWN":
                continue
            for reconciliation in candidates:
                if reconciliation["node"] != original["node"]:
                    continue
                try:
                    binding = self._principal_authority.verify_domain_resolution(original, reconciliation)
                except Exception:
                    continue
                bindings.append({"original_command_id": original["command_id"],
                    "reconcile_command_id": reconciliation["command_id"], "binding": binding})
                resolved.add(original["command_id"])
                break
        return bindings, resolved

    def control_head(self):
        self._validate()
        rows = self._rows()
        bindings, resolved = self._resolutions(rows)
        return {"schema": "fleet.domain-head/1", "role": self.role,
            "sha256": logical_digest({"role": self.role, "policy": asdict(self.policy), "records": rows, "resolutions": bindings}),
            "high_water": sum(row["sequence"] for row in rows), "record_count": len(rows),
            "unresolved_count": sum(row["state"] != "COMPLETED" and row["command_id"] not in resolved for row in rows)}

    def assert_quiescent_head(self, expected_head):
        observed = self.control_head()
        if observed != expected_head or observed["unresolved_count"] != 0:
            raise WireError("DOMAIN_QUIESCENT_CHECKPOINT_MISMATCH")
        return observed

    def witness(self, challenge, *, device_id, route_generation, session_id):
        if self.role != "NODE":
            raise WireError("DOMAIN_ROLE_INVALID")
        text(challenge, 128); text(session_id, 64)
        node = node_reference({"device_id": device_id, "route_generation": route_generation})
        rows = self._rows()
        selected = [row for row in rows if row["node"] == node]
        if any(row["node"]["device_id"] != device_id for row in rows):
            raise WireError("DOMAIN_WITNESS_SCOPE_MISMATCH")
        return {"schema": "fleet.domain-witness/1", "challenge": challenge, "node": node,
            "session_id": session_id, "head": self.control_head(), "records": [
                {key: row[key] for key in ("command_id", "operation_id", "request_sha256", "node", "state", "sequence")}
                | {"result_sha256": logical_digest({"result": row["result"]})} for row in selected]}

    def prepare_restore(self, coordination_sha256, *, expected_head):
        _sha(coordination_sha256)
        self.assert_quiescent_head(expected_head)
        def mutation():
            meta = self._meta()
            scope = {"coordination_sha256": coordination_sha256, "expected_head": expected_head, "phase": "PREPARED"}
            if meta["status"] == "RECONCILIATION_REQUIRED" and meta["restore"] != scope:
                raise WireError("DOMAIN_RESTORE_CONFLICT")
            meta.update(status="RECONCILIATION_REQUIRED", restore=scope)
            self._db.execute("UPDATE meta SET value=? WHERE id=1", (encode_body(meta, self.policy.max_payload_bytes).decode("ascii"),))
            return scope
        return self._atomic(mutation)

    def verify_recovery_witness(self, proof, *, coordination_sha256):
        if not verified(proof) or proof.path != "/fleet/v1/reconcile":
            raise WireError("DOMAIN_WITNESS_UNVERIFIED")
        meta = self._meta()
        if meta["status"] != "RECONCILIATION_REQUIRED" or meta["restore"]["coordination_sha256"] != coordination_sha256:
            raise WireError("DOMAIN_RESTORE_CONFLICT")
        value = proof.body.get("domain_witness")
        fields(value, {"schema", "challenge", "node", "session_id", "head", "records"})
        node = {"device_id": proof.device_id, "route_generation": proof.route_generation}
        fields(value["head"], _HEAD_FIELDS)
        _sha(value["head"]["sha256"])
        integer(value["head"]["high_water"], maximum=self.policy.max_records * 4)
        integer(value["head"]["record_count"], maximum=self.policy.max_records)
        integer(value["head"]["unresolved_count"], minimum=0, maximum=0)
        if (value["head"]["schema"] != "fleet.domain-head/1" or value["head"]["role"] != "NODE"):
            raise WireError("DOMAIN_WITNESS_SCOPE_MISMATCH")
        if (value["schema"] != "fleet.domain-witness/1" or value["challenge"] != coordination_sha256
                or value["node"] != node or value["session_id"] != proof.body.get("session_id")
                or type(value["records"]) is not list or len(value["records"]) > self.policy.max_records):
            raise WireError("DOMAIN_WITNESS_SCOPE_MISMATCH")
        rows = self._rows()
        _, resolved = self._resolutions(rows)
        expected = {row["command_id"]: row for row in rows if row["node"]["device_id"] == proof.device_id}
        observed = {}
        for record in value["records"]:
            fields(record, {"command_id", "operation_id", "request_sha256", "node", "state", "sequence", "result_sha256"})
            _command_id(record["command_id"]); integer(record["sequence"], minimum=4, maximum=4)
            _sha(record["result_sha256"])
            current = expected.get(record["command_id"])
            if (current is None or record["command_id"] in observed
                    or (record["state"] != "COMPLETED" and record["command_id"] not in resolved)
                    or record["state"] != current["state"]
                    or any(record[key] != current[key] for key in ("operation_id", "request_sha256", "node"))
                    or record["result_sha256"] != logical_digest({"result": current["result"]})):
                raise WireError("DOMAIN_WITNESS_UNRESOLVED")
            observed[record["command_id"]] = record
        if (set(observed) != set(expected) or value["head"]["record_count"] != len(observed)
                or value["head"]["high_water"] != sum(record["sequence"] for record in observed.values())):
            raise WireError("DOMAIN_WITNESS_UNRESOLVED")
        return {"device_id": proof.device_id, "coordination_sha256": coordination_sha256,
                "witness_sha256": logical_digest(value), "record_count": len(observed)}

    def finalize_restore(self, coordination_sha256, *, proofs):
        _sha(coordination_sha256)
        self._validate()
        meta = self._meta()
        if (meta["restore"] is not None and meta["restore"]["phase"] == "FINALIZED"
                and meta["restore"]["coordination_sha256"] == coordination_sha256):
            return self.assert_quiescent_head(meta["restore"]["expected_head"])
        if type(proofs) is not list:
            raise WireError("DOMAIN_WITNESS_UNVERIFIED")
        devices = {row["node"]["device_id"] for row in self._rows()}
        verified_devices = {self.verify_recovery_witness(proof, coordination_sha256=coordination_sha256)["device_id"]
                            for proof in proofs}
        if not devices <= verified_devices:
            raise WireError("DOMAIN_WITNESS_UNRESOLVED")
        def mutation():
            meta = self._meta()
            if meta["restore"]["coordination_sha256"] != coordination_sha256:
                raise WireError("DOMAIN_RESTORE_CONFLICT")
            self.assert_quiescent_head(meta["restore"]["expected_head"])
            meta["status"] = "READY"
            meta["restore"]["phase"] = "FINALIZED"
            self._db.execute("UPDATE meta SET value=? WHERE id=1", (encode_body(meta, self.policy.max_payload_bytes).decode("ascii"),))
            return self.control_head()
        return self._atomic(mutation)

    def _save(self, row):
        _record(row, self.role, self.policy.max_payload_bytes)
        encoded = encode_body(row, self.policy.max_payload_bytes).decode("ascii")
        self._db.execute("UPDATE commands SET record=? WHERE command_id=?", (encoded, row["command_id"]))

    def _row(self, command_id):
        self._open(); text(command_id, 64)
        _command_id(command_id)
        size = self._db.execute("SELECT length(CAST(record AS BLOB)) FROM commands WHERE command_id=?", (command_id,)).fetchone()
        if size is not None and size[0] > self.policy.max_payload_bytes:
            raise WireError("DOMAIN_STORAGE_INVALID")
        row = self._db.execute("SELECT record FROM commands WHERE command_id=?", (command_id,)).fetchone()
        if row is None:
            raise WireError("DOMAIN_COMMAND_UNKNOWN")
        return _record(self._decode(row[0]), self.role, self.policy.max_payload_bytes)

    def get(self, command_id):
        return copy.deepcopy(self._row(command_id))

    def _atomic(self, action):
        self._open()
        try:
            self._db.execute("BEGIN IMMEDIATE")
            self._validate()
            result = action()
            self._db.commit()
            return result
        except BaseException as error:
            self._db.rollback()
            if isinstance(error, WireError) or not isinstance(error, Exception):
                raise
            raise WireError("DOMAIN_TRANSACTION_FAILED") from None

    def submit(self, path, node, payload, operation_id):
        if self.role != "GATEWAY" or path not in _QUEUED_PATHS:
            raise WireError("DOMAIN_OPERATION_INVALID")
        node = node_reference(node); text(operation_id, 160)
        if type(payload) is not dict:
            raise WireError("DOMAIN_INVALID")
        request = {"path": path, "node": node, "payload": payload}
        encode_body(request, self.policy.max_payload_bytes)
        sha = logical_digest(request)
        def mutation():
            self.assert_dispatch_ready()
            existing = self._db.execute("SELECT record FROM commands WHERE operation_id=?", (operation_id,)).fetchone()
            if existing is not None:
                row = self._decode(existing[0])
                if row["request_sha256"] != sha:
                    raise WireError("DOMAIN_OPERATION_CONFLICT")
                return row
            if len(self._rows()) >= self.policy.max_records:
                raise WireError("DOMAIN_CAPACITY")
            row = {"schema": "fleet.domain-record/1", "command_id": "dcmd_" + uuid.uuid4().hex,
                "operation_id": operation_id, "request_sha256": sha, **copy.deepcopy(request),
                "kind": _QUEUED_PATHS[path], "state": "QUEUED", "session_id": None, "sequence": 1, "result": None}
            self._db.execute("INSERT INTO commands VALUES (?,?,?)", (operation_id, row["command_id"],
                encode_body(row, self.policy.max_payload_bytes).decode("ascii")))
            return row
        return self._atomic(mutation)

    def poll(self, device_id, route_generation, session_id, limit):
        return self._poll(device_id, route_generation, session_id, limit, None)

    def poll_cancels(self, device_id, route_generation, session_id, limit, command_ids):
        if type(command_ids) is not frozenset or any(type(item) is not str for item in command_ids):
            raise WireError("DOMAIN_CANCEL_SCOPE_INVALID")
        return self._poll(device_id, route_generation, session_id, limit, command_ids)

    def _poll(self, device_id, route_generation, session_id, limit, cancel_ids):
        if self.role != "GATEWAY":
            raise WireError("DOMAIN_ROLE_INVALID")
        integer(limit, minimum=1, maximum=self.policy.max_commands); text(session_id, 64)
        def mutation():
            self.assert_dispatch_ready()
            selected = []
            for row in self._rows():
                if cancel_ids is not None and (row["kind"] != "CANCEL" or row["command_id"] not in cancel_ids):
                    continue
                if row["node"] != {"device_id": device_id, "route_generation": route_generation} or row["state"] not in {"QUEUED", "DELIVERED"}:
                    continue
                if row["session_id"] not in (None, session_id):
                    continue
                if row["state"] == "QUEUED":
                    row.update(state="DELIVERED", session_id=session_id, sequence=row["sequence"] + 1)
                    self._save(row)
                selected.append({**row, "schema": "fleet.domain-command/1"})
                if len(selected) == limit:
                    break
            return selected
        return self._atomic(mutation)

    def receive(self, command, device_id, route_generation, session_id):
        if self.role != "NODE" or type(command) is not dict or command.get("schema") != "fleet.domain-command/1":
            raise WireError("DOMAIN_COMMAND_INVALID")
        fields(command, _RECORD_FIELDS)
        record = {**copy.deepcopy(command), "schema": "fleet.domain-record/1"}
        _record(record, "NODE", self.policy.max_payload_bytes)
        if record["state"] != "DELIVERED":
            raise WireError("DOMAIN_COMMAND_INVALID")
        if (record["node"] != node_reference({"device_id": device_id, "route_generation": route_generation})
                or record["session_id"] != session_id or record["path"] not in _QUEUED_PATHS
                or record["kind"] != _QUEUED_PATHS[record["path"]]
                or record["request_sha256"] != logical_digest({key: record[key] for key in ("path", "node", "payload")})):
            raise WireError("DOMAIN_COMMAND_MISMATCH")
        def mutation():
            self.assert_dispatch_ready()
            old = self._db.execute("SELECT record FROM commands WHERE command_id=?", (record["command_id"],)).fetchone()
            if old is not None:
                prior = self._decode(old[0])
                if any(prior[key] != record[key] for key in ("request_sha256", "operation_id", "node", "session_id")):
                    raise WireError("DOMAIN_COMMAND_CONFLICT")
                return prior
            if len(self._rows()) >= self.policy.max_records:
                raise WireError("DOMAIN_CAPACITY")
            record.update(state="DELIVERED", result=None)
            self._db.execute("INSERT INTO commands VALUES (?,?,?)", (record["operation_id"], record["command_id"],
                encode_body(record, self.policy.max_payload_bytes).decode("ascii")))
            return record
        return self._atomic(mutation)

    def begin_execution(self, command_id):
        if self.role != "NODE":
            raise WireError("DOMAIN_ROLE_INVALID")
        def begin():
            self.assert_dispatch_ready()
            row = self._row(command_id)
            if row["state"] != "DELIVERED":
                return row, False
            row.update(state="EXECUTING", sequence=3)
            self._save(row)
            return row, True
        return self._atomic(begin)

    def finish_execution(self, command_id, *, sequence, state, result):
        integer(sequence, minimum=3, maximum=3)
        if self.role != "NODE" or state not in {"COMPLETED", "UNKNOWN"} or type(result) is not dict:
            raise WireError("DOMAIN_RESULT_INVALID")
        encode_body(result, self.policy.max_payload_bytes)
        def finish():
            current = self._row(command_id)
            if current["state"] != "EXECUTING" or current["sequence"] != sequence:
                raise WireError("DOMAIN_SEQUENCE_CONFLICT")
            current.update(state=state, result=copy.deepcopy(result), sequence=4)
            self._save(current)
            return current
        return self._atomic(finish)

    @staticmethod
    def failure(error):
        code = getattr(error, "code", None)
        if type(code) is not str or not code.isascii() or not code.replace("_", "").isalnum() or len(code) > 128:
            code = "DOMAIN_OUTCOME_UNKNOWN"
        return {"schema": "fleet.domain-failure/1", "code": code}

    def execute(self, command_id, dispatcher):
        row, should_execute = self.begin_execution(command_id)
        if not should_execute:
            return row
        try:
            outcome = dispatcher.apply(row)
            if type(outcome) is not dict:
                raise WireError("DOMAIN_RESULT_INVALID")
            encode_body(outcome, self.policy.max_payload_bytes)
            state = "COMPLETED"
        except Exception as error:
            outcome, state = self.failure(error), "UNKNOWN"
        return self.finish_execution(command_id, sequence=row["sequence"], state=state, result=outcome)

    def validate_result(self, value, device_id, route_generation, session_id):
        if self.role != "GATEWAY":
            raise WireError("DOMAIN_ROLE_INVALID")
        self._validate()
        fields(value, {"schema", "session_id", "command_id", "node", "request_sha256", "state", "sequence", "result"})
        if value["schema"] != "fleet.domain-result/1" or value["state"] not in {"COMPLETED", "UNKNOWN"}:
            raise WireError("DOMAIN_RESULT_INVALID")
        _command_id(value["command_id"]); _sha(value["request_sha256"])
        node_reference(value["node"]); text(value["session_id"], 64)
        integer(value["sequence"], minimum=4, maximum=4)
        if type(value["result"]) is not dict:
            raise WireError("DOMAIN_RESULT_INVALID")
        encode_body(value, self.policy.max_payload_bytes)
        row = self._row(value["command_id"])
        if (row["node"] != value["node"] or row["node"] != {"device_id": device_id, "route_generation": route_generation}
                or row["session_id"] != session_id or value["session_id"] != session_id
                or row["request_sha256"] != value["request_sha256"]):
            raise WireError("DOMAIN_RESULT_MISMATCH")
        if row["state"] in {"COMPLETED", "UNKNOWN"}:
            if row["result"] != value["result"] or row["state"] != value["state"] or row["sequence"] != value["sequence"]:
                raise WireError("DOMAIN_RESULT_CONFLICT")
        elif row["state"] != "DELIVERED":
            raise WireError("DOMAIN_RESULT_UNDELIVERED")
        return row

    def commit(self, value, device_id, route_generation, session_id):
        self.validate_result(value, device_id, route_generation, session_id)
        def mutation():
            self.assert_dispatch_ready()
            row = self.validate_result(value, device_id, route_generation, session_id)
            recovered = row["state"] in {"COMPLETED", "UNKNOWN"}
            if not recovered:
                row.update(state=value["state"], result=copy.deepcopy(value["result"]), sequence=value["sequence"])
                self._save(row)
            return {"schema": "fleet.domain-commit/1", "command_id": row["command_id"], "recovered": recovered}
        return self._atomic(mutation)


def _domain_errors(action):
    @wraps(action)
    def wrapped(*args, **kwargs):
        try:
            return action(*args, **kwargs)
        except WireError:
            raise
        except Exception as error:
            code = getattr(error, "code", None)
            if type(code) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", code) is None:
                code = "DOMAIN_OPERATION_FAILED"
            raise WireError(code) from None
    return wrapped


class GatewayDomain:
    def __init__(self, store, journal, native_journal, *, principal_authority=None, recovery=None,
                 native_signer=None, capacity_owner_public_key=None, start_authorization_ms):
        self.store, self.journal, self.native = store, journal, native_journal
        self.principals = principal_authority
        if self.principals is not None:
            journal.bind_principal_authority(self.principals)
        self.recovery, self.native_signer = recovery, native_signer
        self.capacity_owner_public_key = None if capacity_owner_public_key is None else _sha(capacity_owner_public_key)
        native_journal.bind_capacity_owner(self.capacity_owner_public_key)
        self.start_authorization_ms = integer(start_authorization_ms, minimum=1, maximum=30000)

    def close(self):
        resources = [self.recovery, self.principals, self.native, self.journal]
        error = None
        for resource in resources:
            if resource is None:
                continue
            try:
                resource.close()
            except BaseException as caught:
                error = error or caught
        if error is not None:
            raise error

    def _route(self, node):
        self.journal.assert_dispatch_ready()
        self.native.assert_dispatch_ready()
        if self.recovery is not None and not self.recovery.status()["ready"]:
            raise WireError("RECONCILIATION_REQUIRED")
        node = node_reference(node)
        route = self.store.get_route(node["device_id"])
        if route["state"] != "ACTIVE" or route["status"] != "READY_CONTROL_ONLY" or route["route_generation"] != node["route_generation"]:
            raise WireError("DOMAIN_ROUTE_STALE")
        return route

    @_domain_errors
    def handle_owner(self, path, value, *, now_ms, monotonic_ms):
        if path in {"/fleet/v1/info", "/fleet/v1/inventory"}:
            if path == "/fleet/v1/inventory" and value.get("schema") == "fleet.domain-request/1":
                fields(value, {"schema", "node", "operation_id", "payload"})
                fields(value["payload"], set())
                self._route(value["node"])
                return self.journal.submit(path, value["node"], value["payload"], value["operation_id"])
            fields(value, {"schema"})
            if value["schema"] != "fleet.domain-query/1":
                raise WireError("DOMAIN_INVALID")
            snapshot = self.store.snapshot()
            return {"schema": "fleet.domain-inventory/1", "devices": snapshot["devices"],
                "status": snapshot["status"], "revision": snapshot["revision"],
                "source": "GATEWAY_CONTROL_CACHE", "sdk_qualification": "UNQUALIFIED",
                "queried_at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
                "observation_age_ms": None, "transport_status": "NOT_OBSERVED_BY_INVENTORY",
                "projects": "NODE_OWNED", "legacy_catalog": "UNCHANGED_85"}
        if path == "/fleet/v1/commands/status":
            fields(value, {"schema", "command_id"})
            if value["schema"] != "fleet.domain-status-request/1":
                raise WireError("DOMAIN_INVALID")
            return self.journal.get(value["command_id"])
        if path == "/fleet/v1/jobs/launch":
            fields(value, {"schema", "operation_id", "request"})
            if value["schema"] != "fleet.job-launch/1":
                raise WireError("DOMAIN_INVALID")
            from .native import native_request_hash
            native_request_hash(value["request"])
            prior = self.native.get_operation(value["operation_id"], value["request"])
            if prior is not None:
                return prior
            exact = target(value["request"]["placement"]["target"])
            self._route({key: exact[key] for key in ("device_id", "route_generation")})
            return self.native.submit(value["operation_id"], value["request"])
        if path == "/fleet/v1/jobs/status":
            fields(value, {"schema", "global_job_id"})
            if value["schema"] != "fleet.job-query/1":
                raise WireError("DOMAIN_INVALID")
            return self.native.get(value["global_job_id"])
        if path == "/fleet/v1/jobs/recover":
            fields(value, {"schema", "operation_id", "global_job_id", "node", "session_id"})
            if value["schema"] != "fleet.job-recovery-request/1":
                raise WireError("DOMAIN_INVALID")
            self._route(value["node"])
            return self.native.request_terminal_recovery(value["operation_id"], value["global_job_id"],
                device_id=value["node"]["device_id"], current_route_generation=value["node"]["route_generation"],
                current_session_id=value["session_id"])
        if path.startswith("/fleet/v1/principals/"):
            if self.principals is None:
                raise WireError("PRINCIPAL_AUTHORITY_UNAVAILABLE")
            receipt = self.principals.owner_request(path, value, now_ms=now_ms)
            fences = receipt.get("fences", [])
            queued = []
            for fence in fences:
                exact = fence["body"]["target"]
                node = {key: exact[key] for key in ("device_id", "route_generation")}
                operation = "fence:" + logical_digest({"fence": fence})
                queued.append(self.journal.submit("/fleet/v1/writers/fence", node, {"fence": fence}, operation))
            approval = receipt.get("approval")
            if approval is not None:
                exact = approval["body"]["target"]
                node = {key: exact[key] for key in ("device_id", "route_generation")}
                queued.append(self.journal.submit("/fleet/v1/writers/reconcile", node, {"approval": approval},
                    "writer-reconcile:" + logical_digest({"approval": approval})))
            return {**receipt, "fence_commands": queued} if queued else receipt
        if path not in _QUEUED_PATHS or path in DOMAIN_PRINCIPAL_PATHS:
            raise WireError("DOMAIN_OPERATION_INVALID")
        fields(value, {"schema", "node", "operation_id", "payload"})
        if value["schema"] != "fleet.domain-request/1":
            raise WireError("DOMAIN_INVALID")
        self._route(value["node"])
        if path in {"/fleet/v1/jobs/cancel", "/fleet/v1/artifacts/manifest", "/fleet/v1/artifacts/chunk"}:
            rec = self.native.get(value["payload"]["global_job_id"])
            if path.startswith("/fleet/v1/artifacts/") and (value["payload"].get("local_job_id") != rec["local_job_id"]
                    or value["payload"].get("frozen_target") != rec["target"]):
                raise WireError("DOMAIN_JOB_SCOPE_MISMATCH")
            if any(rec["target"][key] != value["node"][key] for key in ("device_id", "route_generation")):
                raise WireError("DOMAIN_JOB_SCOPE_MISMATCH")
        return self.journal.submit(path, value["node"], value["payload"], value["operation_id"])

    @_domain_errors
    def handle_principal(self, path, header_pairs, value, *, body_bytes, now_ms, monotonic_ms):
        if path not in DOMAIN_PRINCIPAL_PATHS or self.principals is None:
            raise WireError("PRINCIPAL_UNVERIFIED")
        fields(value, {"schema", "node", "operation_id", "payload"})
        self._route(value["node"])
        admitted = self.principals.admit_request(path, header_pairs, value, body_bytes=body_bytes, now_ms=now_ms)
        if type(admitted) is not dict or admitted.get("node") != value["node"] or type(admitted.get("payload")) is not dict:
            raise WireError("PRINCIPAL_SCOPE_MISMATCH")
        return self.journal.submit(path, value["node"], admitted["payload"], value["operation_id"])

    @_domain_errors
    def poll_for_node(self, proof, session_id, max_commands, *, now_ms):
        self._route({"device_id": proof.device_id, "route_generation": proof.route_generation})
        capacity = self.native.capacity_for_node(proof.device_id, proof.route_generation)
        native = self.native.poll_for_node(proof.device_id, route_generation=proof.route_generation,
            session_id=session_id, max_commands=min(capacity, max_commands))
        remaining = max_commands - len(native)
        historical = self.native.poll_terminal_recoveries(proof.device_id, route_generation=proof.route_generation,
            session_id=session_id, max_commands=min(remaining, 16)) if remaining > 0 else []
        remaining -= len(historical)
        domains = self.journal.poll(proof.device_id, proof.route_generation, session_id,
            min(remaining, self.journal.policy.max_commands)) if remaining > 0 else []
        return native + historical + domains

    @_domain_errors
    def poll_cancel_for_node(self, proof, session_id, max_commands, *, now_ms):
        """Stopping admission permits only cancel of this session's active job."""
        node = {"device_id": proof.device_id, "route_generation": proof.route_generation}
        self._route(node)
        permitted = set()
        for command in self.journal._rows():
            if command["node"] != node or command["kind"] != "CANCEL" or command["state"] not in {"QUEUED", "DELIVERED"}:
                continue
            payload = command["payload"]
            fields(payload, {"global_job_id", "process_identity"})
            job = self.native.get(payload["global_job_id"])
            progress = job["result"].get("result") if type(job["result"]) is dict else None
            process = progress.get("process_identity") if type(progress) is dict else None
            if (job["state"] in {"STARTING", "RUNNING", "RESULT_PENDING"} and job["session_id"] == session_id
                    and all(job["target"][key] == node[key] for key in node) and process is not None
                    and process == payload["process_identity"]):
                permitted.add(command["command_id"])
        return self.journal.poll_cancels(proof.device_id, proof.route_generation, session_id,
            min(max_commands, self.journal.policy.max_commands), frozenset(permitted))

    @_domain_errors
    def handle_node(self, proof, value, *, now_ms, monotonic_ms):
        if proof.path == "/fleet/v1/reconcile":
            if self.recovery is None:
                raise WireError("RECONCILIATION_REQUIRED")
            result = self.recovery.accept_witness(proof, now_ms=now_ms)
            if self.recovery.status().get("phase") == "PREPARED":
                self.recovery.finalize(now_ms=now_ms)
            return {"schema": "fleet.reconcile-result/1", "result": result, "status": self.recovery.status()}
        self._route({"device_id": proof.device_id, "route_generation": proof.route_generation})
        if proof.path == "/fleet/v1/jobs/recovery-witness":
            fields(value, {"schema", "session_id", "witness"})
            if (value["schema"] != "fleet.native-recovery-envelope/1" or type(value["witness"]) is not dict
                    or value["witness"].get("body", {}).get("current") != {"device_id": proof.device_id,
                        "route_generation": proof.route_generation, "session_id": value["session_id"]}):
                raise WireError("HISTORICAL_WITNESS_SCOPE_MISMATCH")
            return self.native.commit_terminal_recovery(value["witness"], registered_public_key=proof.public_key,
                current_route_generation=proof.route_generation, current_session_id=value["session_id"])
        if proof.path == "/fleet/v1/capacity/register":
            fields(value, {"schema", "session_id", "signed_profile", "load_receipt_base64", "closure_receipt_base64"})
            if value["schema"] != "fleet.capacity-register/1" or self.capacity_owner_public_key is None:
                raise WireError("NATIVE_CAPACITY_UNQUALIFIED")
            raw = []
            for key in ("load_receipt_base64", "closure_receipt_base64"):
                text(value[key], 87384)
                try:
                    raw.append(base64.b64decode(value[key], validate=True))
                except (ValueError, TypeError):
                    raise WireError("NATIVE_CAPACITY_UNQUALIFIED") from None
                if len(raw[-1]) > 65536:
                    raise WireError("NATIVE_CAPACITY_UNQUALIFIED")
            from .scoped_resources import verify_capacity_roster
            roster = verify_capacity_roster(value["signed_profile"], device_id=proof.device_id,
                route_generation=proof.route_generation, trusted_owner_public_key=self.capacity_owner_public_key,
                load_receipt=raw[0], closure_receipt=raw[1])
            return self.native.install_capacity_roster(roster)
        if proof.path == "/fleet/v1/writers/authorize":
            if self.principals is None:
                raise WireError("PRINCIPAL_AUTHORITY_UNAVAILABLE")
            return self.principals.authorize_node(proof, value, now_ms=now_ms)
        if proof.path == "/fleet/v1/native/start":
            fields(value, {"schema", "session_id", "global_job_id", "node_operation_id", "request_sha256", "target",
                "local_job_id", "phase", "sequence", "challenge", "event", "predecessor", "process_sha256"})
            if value["schema"] != "fleet.start-authorize/1" or self.native_signer is None:
                raise WireError("DOMAIN_INVALID")
            return self.native.authorize_start(proof.device_id, route_generation=proof.route_generation,
                now_ms=now_ms, ttl_ms=self.start_authorization_ms, signer=self.native_signer,
                **{key: value[key] for key in ("session_id", "global_job_id", "node_operation_id", "request_sha256",
                    "local_job_id", "phase", "sequence", "challenge", "event", "predecessor", "process_sha256")},
                frozen_target=value["target"])
        if value.get("schema") == "fleet.native-result-envelope/1":
            fields(value, {"schema", "session_id", "payload"})
            return self.native.commit_node_result(proof.device_id, route_generation=proof.route_generation,
                session_id=value["session_id"], payload=value["payload"])
        if value.get("schema") == "fleet.domain-result/1":
            row = self.journal.validate_result(value, proof.device_id, proof.route_generation, value.get("session_id"))
            if row["state"] in {"COMPLETED", "UNKNOWN"}:
                return self.journal.commit(value, proof.device_id, proof.route_generation, value["session_id"])
            if self.principals is not None and (row["path"] in DOMAIN_PRINCIPAL_PATHS or row["path"] in {"/fleet/v1/writers/fence", "/fleet/v1/writers/reconcile"}):
                if "writer_acks" in value["result"]:
                    self.principals.acknowledge_node(proof, value["result"]["writer_acks"])
                if row["path"] in {"/fleet/v1/writers/fence", "/fleet/v1/writers/release", "/fleet/v1/writers/reconcile"} and value["state"] == "COMPLETED":
                    ack = value["result"] if row["path"] != "/fleet/v1/writers/reconcile" else value["result"].get("fence_ack")
                    if ack is not None:
                        self.principals.acknowledge_fence(proof, **{key: ack[key] for key in ("project_id", "fence_epoch", "pending_intents")})
            return self.journal.commit(value, proof.device_id, proof.route_generation, value["session_id"])
        raise WireError("DOMAIN_NODE_OPERATION_INVALID")


class NodeDomainDispatcher:
    def __init__(self, root, domain_journal, native_journal, native_adapter, *, artifacts=None,
                 principal_runtime=None, authorization_verifier=None, max_inventory_rows=None, capacity_roster=None):
        from .project_targets import FleetProjectStore
        self.root, self.journal, self.native = Path(root).resolve(), domain_journal, native_journal
        self.native_adapter, self.artifacts, self.principals = native_adapter, artifacts, principal_runtime
        self.authorization_verifier = authorization_verifier
        self.max_inventory_rows = max_inventory_rows
        self.projects = FleetProjectStore(self.root)
        if self.principals is not None:
            domain_journal.bind_principal_authority(self.principals)
        from .scoped_resources import VerifiedCapacityRoster
        if capacity_roster is not None and type(capacity_roster) is not VerifiedCapacityRoster:
            raise WireError("NATIVE_CAPACITY_UNQUALIFIED")
        self.capacity_roster = capacity_roster
        self.native_capacity = capacity_roster.profile["capacity"] if capacity_roster is not None else 1
        integer(self.native_capacity, minimum=1, maximum=64)
        self._executors = {"NATIVE": ThreadPoolExecutor(max_workers=self.native_capacity, thread_name_prefix="fleet-native"),
            "CANCEL": ThreadPoolExecutor(max_workers=1, thread_name_prefix="fleet-cancel"),
            "WRITER": ThreadPoolExecutor(max_workers=1, thread_name_prefix="fleet-writer")}
        self._futures, self._native_records, self._domain_records, self._acked = {}, {}, {}, {}
        self._rpc, self._closed = None, False

    def bind_control_transport(self, proxy):
        from .transport import NodeRpcProxy
        if type(proxy) is not NodeRpcProxy or self._rpc is not None:
            raise WireError("DOMAIN_CONTROL_TRANSPORT_INVALID")
        self._rpc = proxy
        if self.principals is not None:
            self.principals.bind_control_transport(proxy)

    def has_pending_work(self):
        # Retained real phase handles represent uncertainty even after a worker
        # returned; stopping the agent does not prove those processes closed.
        retained = self.native_adapter.has_retained_work() if callable(getattr(self.native_adapter, "has_retained_work", None)) else bool(getattr(self.native_adapter, "_active", {}))
        return bool(self._futures or self._native_records or self._domain_records or retained)

    def close(self):
        if self.has_pending_work():
            raise WireError("DOMAIN_WORKERS_ACTIVE")
        self._closed = True
        for executor in self._executors.values():
            executor.shutdown(wait=True)

    def _native_work(self, global_job_id, proxy, session_id):
        authorize = lambda row: proxy.start_authorize(session_id, row)
        row = self.native.execute(global_job_id, self.native_adapter, start_authorize=authorize,
            authorization_verifier=self.authorization_verifier)
        if row["state"] == "RUNNING":
            return self.native.observe_result(global_job_id, self.native_adapter,
                start_authorize=authorize, authorization_verifier=self.authorization_verifier)
        return row

    def dispatch_async(self, command, proxy, session_id):
        if self._closed or proxy is not self._rpc or command.get("kind") not in {"NATIVE", "CANCEL", "SOURCE", "WORKTREE"}:
            raise WireError("DOMAIN_ASYNC_INVALID")
        kind = command["kind"]
        lane = kind if kind in {"NATIVE", "CANCEL"} else "WRITER"
        key = command.get("global_job_id") if kind == "NATIVE" else command.get("command_id")
        if key in self._futures:
            return {"schema": "fleet.domain-admission/1", "command_id": key, "status": "ALREADY_ADMITTED"}
        capacity = self.native_capacity if lane == "NATIVE" else 1
        if sum(entry["lane"] == lane for entry in self._futures.values()) >= capacity:
            return {"schema": "fleet.domain-admission/1", "command_id": key, "status": "DEFERRED_CAPACITY"}
        if kind == "NATIVE":
            if (self.capacity_roster is not None and (self.capacity_roster.route_generation != proxy.route_generation
                    or self.capacity_roster.profile["device_id"] != proxy.device_id)):
                raise WireError("NATIVE_CAPACITY_ROUTE_STALE")
            row = self.native.receive(command, device_id=proxy.device_id,
                route_generation=proxy.route_generation, session_id=session_id)
            self._native_records[key] = session_id
            if row["state"] != "DELIVERED":
                return {"schema": "fleet.domain-admission/1", "command_id": key, "status": "RECORDED"}
            future = self._executors[lane].submit(self._native_work, key, proxy, session_id)
            sequence = None
        else:
            row = self.journal.receive(command, proxy.device_id, proxy.route_generation, session_id)
            self._domain_records[key] = session_id
            row, execute = self.journal.begin_execution(key)
            if not execute:
                return {"schema": "fleet.domain-admission/1", "command_id": key, "status": "RECORDED"}
            future = self._executors[lane].submit(self.apply, row)
            sequence = row["sequence"]
        self._futures[key] = {"future": future, "kind": kind, "lane": lane, "sequence": sequence}
        return {"schema": "fleet.domain-admission/1", "command_id": key, "status": "ADMITTED"}

    def flush_native_progress(self, client, session_id, global_job_id, *, deadline_monotonic):
        row = self.native.get(global_job_id)
        if (row["session_id"] != session_id or row["target"]["device_id"] != client.device_id
                or row["target"]["route_generation"] != client.route_generation):
            raise WireError("DOMAIN_JOB_SCOPE_MISMATCH")
        value = {"schema": "fleet.native-result-envelope/1", "session_id": session_id,
                 "payload": self.native.result_payload(global_job_id)}
        sha = logical_digest(value)
        if self._acked.get(global_job_id) != sha:
            response = client.domain_result(value, deadline_monotonic=deadline_monotonic)
            self._acked[global_job_id] = sha
            return response
        return {"schema": "fleet.progress-flush/1", "status": "ACKNOWLEDGED", "global_job_id": global_job_id}

    def drain(self, client, session_id):
        # Only this control owner touches DomainJournal or NodeTransportJournal.
        for key, entry in list(self._futures.items()):
            if not entry["future"].done():
                continue
            if entry["kind"] != "NATIVE":
                try:
                    outcome = entry["future"].result()
                    if type(outcome) is not dict:
                        raise WireError("DOMAIN_RESULT_INVALID")
                    encode_body(outcome, self.journal.policy.max_payload_bytes)
                    state = "COMPLETED"
                except BaseException as error:
                    outcome, state = self.journal.failure(error), "UNKNOWN"
                self.journal.finish_execution(key, sequence=entry["sequence"], state=state, result=outcome)
            else:
                # Interrupted native intents remain in their durable uncertain state.
                try:
                    entry["future"].result()
                except BaseException:
                    pass
            del self._futures[key]
        committed = []
        deadline = time.monotonic() + client.http.policy.heartbeat_interval_ms / 1000
        for key, original_session in list(self._native_records.items()):
            if len(committed) >= self.journal.policy.max_commands or time.monotonic() >= deadline:
                break
            if original_session != session_id:
                raise WireError("DOMAIN_SESSION_MISMATCH")
            row = self.native.get(key)
            if row["state"] in {"QUEUED", "DELIVERED"}:
                continue
            value = {"schema": "fleet.native-result-envelope/1", "session_id": session_id,
                     "payload": self.native.result_payload(key)}
            sha = logical_digest(value)
            if self._acked.get(key) != sha:
                response = client.domain_result(value, deadline_monotonic=deadline)
                self._acked[key] = sha
                committed.append(response)
            if row["state"] in {"SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN", "RECOVERY_REQUIRED"} and key not in self._futures:
                self._native_records.pop(key, None); self._acked.pop(key, None)
        for key, original_session in list(self._domain_records.items()):
            if len(committed) >= self.journal.policy.max_commands or time.monotonic() >= deadline:
                break
            if original_session != session_id:
                raise WireError("DOMAIN_SESSION_MISMATCH")
            row = self.journal.get(key)
            if row["state"] not in {"COMPLETED", "UNKNOWN"}:
                continue
            value = self._domain_result(row)
            sha = logical_digest(value)
            if self._acked.get(key) != sha:
                response = client.domain_result(value, deadline_monotonic=deadline)
                committed.append(response)
            self._domain_records.pop(key, None); self._acked.pop(key, None)
        return committed

    @staticmethod
    def _domain_result(row):
        return {"schema": "fleet.domain-result/1", "session_id": row["session_id"],
            **{key: row[key] for key in ("command_id", "node", "request_sha256", "state", "sequence", "result")}}

    def dispatch(self, command, client, session_id):
        if command.get("kind") == "NATIVE_RECOVERY":
            if command.get("current") != {"device_id": client.device_id, "route_generation": client.route_generation, "session_id": session_id}:
                raise WireError("HISTORICAL_WITNESS_SCOPE_MISMATCH")
            witness = self.native.terminal_recovery_witness(command, private_key=client.key)
            return client.terminal_recovery_witness(session_id, witness)
        if command.get("kind") == "NATIVE":
            rec = self.native.receive(command, device_id=client.device_id,
                route_generation=client.route_generation, session_id=session_id)
            def authorize(row):
                return client.start_authorize(session_id, row)
            self.native.execute(rec["global_job_id"], self.native_adapter, start_authorize=authorize,
                authorization_verifier=self.authorization_verifier)
            return client.domain_result({"schema": "fleet.native-result-envelope/1",
                "session_id": session_id, "payload": self.native.result_payload(rec["global_job_id"])})
        rec = self.journal.receive(command, client.device_id, client.route_generation, session_id)
        rec = self.journal.execute(rec["command_id"], self)
        return client.domain_result(self._domain_result(rec))

    def apply(self, row):
        payload, path = copy.deepcopy(row["payload"]), row["path"]
        if path == "/fleet/v1/inventory":
            fields(payload, set())
            integer(self.max_inventory_rows, minimum=1, maximum=4096)
            from .identity import IdentityRegistry
            from .reads import _inventory_rows
            registry = IdentityRegistry(self.root)
            record = registry.load()
            if record is None or record["device_id"] != row["node"]["device_id"]:
                raise WireError("DOMAIN_NODE_MISMATCH")
            terminals = _inventory_rows(self.root)
            if len(terminals) > self.max_inventory_rows:
                raise WireError("DOMAIN_INVENTORY_LIMIT")
            overlays = registry.overlay(terminals)
            rows = []
            for terminal in terminals:
                state = overlays[terminal.alias.upper()]
                exact = None
                if state["identity_status"] == "ENROLLED" and state["resource_qualification"] == "QUALIFIED":
                    exact = {"schema": "fleet.target/1", "device_id": state["device_id"],
                        "route_generation": row["node"]["route_generation"], "terminal_id": state["terminal_id"],
                        "terminal_generation": state["terminal_generation"]}
                rows.append({"alias": terminal.alias, **state, "target": exact,
                    "running": None, "connected": None, "sdk_readiness": "NOT_OBSERVED"})
            return {"schema": "fleet.node-inventory/1", "node": row["node"], "rows": rows,
                "source": "NODE_CONFIG_AND_LOCAL_PERSISTED_REGISTRY", "identity_revision": record["identity_revision"],
                "observed_at_utc": datetime.now(timezone.utc).isoformat(), "terminal_runtime_observed": False}
        if path in DOMAIN_PRINCIPAL_PATHS or path in {"/fleet/v1/writers/fence", "/fleet/v1/writers/reconcile"}:
            if self.principals is None:
                raise WireError("PRINCIPAL_UNVERIFIED")
            return self.principals.apply_command(path, payload, operation_id=row["operation_id"])
        if path == "/fleet/v1/projects/create":
            fields(payload, {"project_id", "workspace", "ea", "checkpoint_id", "active_goal"})
            return self.projects.sessions.create(**payload)
        if path == "/fleet/v1/projects/enroll":
            fields(payload, {"project_id", "owner_device_id", "expected_session_revision", "expected_session_sha256", "default_target", "strict_baseline"})
            return self.projects.enroll(**payload, operation_id=row["operation_id"])
        if path == "/fleet/v1/projects/get":
            fields(payload, {"project_id"})
            return self.projects.get(**payload)
        if path == "/fleet/v1/projects/default-target":
            fields(payload, {"project_id", "target", "expected_placement_revision"})
            return self.projects.set_default(**payload, operation_id=row["operation_id"])
        if path == "/fleet/v1/projects/freeze":
            fields(payload, {"project_id", "frozen_id", "writer_id", "expected_placement_revision", "expected_session_revision", "expected_session_sha256", "target"})
            return self.projects.freeze(**payload, operation_id=row["operation_id"])
        if path == "/fleet/v1/projects/resume":
            fields(payload, {"frozen_id"})
            return self.projects.resume(**payload)
        if path == "/fleet/v1/projects/baseline":
            from .strict_baseline import strict_compare
            fields(payload, {"baseline", "candidate"})
            return strict_compare(payload["candidate"], payload["baseline"])
        if path.startswith("/fleet/v1/artifacts/"):
            if self.artifacts is None:
                raise WireError("ARTIFACT_UNAVAILABLE")
            if path.endswith("/manifest"):
                fields(payload, {"artifact_id", "global_job_id", "local_job_id", "frozen_target", "expected_sha256"})
                return self.artifacts.manifest(**payload)
            fields(payload, {"artifact_id", "global_job_id", "local_job_id", "frozen_target", "expected_sha256", "offset", "length"})
            return self.artifacts.chunk(**payload)
        if path == "/fleet/v1/jobs/cancel":
            fields(payload, {"global_job_id", "process_identity"})
            return self.native.cancel(row["operation_id"], payload["global_job_id"],
                process_identity=payload["process_identity"], adapter=self.native_adapter,
                start_authorize=lambda value: self._rpc.start_authorize(row["session_id"], value),
                authorization_verifier=self.authorization_verifier)
        raise WireError("DOMAIN_OPERATION_INVALID")
