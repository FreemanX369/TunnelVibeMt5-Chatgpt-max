"""Atomic physical-resource bookkeeping under the existing native authority.

The shared native FIFO lease and durable OwnershipAuthority remain permission to
execute. A row in this database grants no independent execution capability.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..core.jobs import _exclusive_file_lock, _read_json_object
from ..core.native_ownership import OwnershipAuthority, current_identity
from .job_journal import JournalError, _id, _integer, canonical, digest

KINDS = {"compiler_deploy", "tester", "ipc", "capture", "local_agent"}
RESOURCE_FIELDS = {"executable", "data_root", "include_root", "agent_root"}


def physical_resources(binding):
    """Observe canonical paths/inodes; different strings never prove independence."""
    if not isinstance(binding, dict) or set(binding) != RESOURCE_FIELDS:
        raise JournalError("RESOURCE_BINDING_INVALID")
    observed = []
    for field in sorted(RESOURCE_FIELDS):
        raw = binding[field]
        if not isinstance(raw, str) or not raw or len(raw) > 32768 or not os.path.isabs(raw):
            raise JournalError("RESOURCE_BINDING_INVALID")
        try:
            path = Path(raw).resolve(strict=True)
            stat = path.stat()
        except OSError:
            raise JournalError("RESOURCE_INDEPENDENCE_UNPROVEN") from None
        observed.append({"kind": field, "path": os.path.normcase(str(path)),
                         "physical_key": f"{stat.st_dev}:{stat.st_ino}"})
    return observed


class ResourceAuthority:
    def __init__(self, root, *, initialize=False, capacity=1, max_records, wait_ms, fault=None):
        _integer(capacity); _integer(max_records); _integer(wait_ms)
        if capacity != 1:
            # No qualified scoped common ownership protocol exists yet.
            raise JournalError("NATIVE_CAPACITY_UNQUALIFIED")
        self.root = Path(root).resolve()
        self.path = self.root / "state" / "fleet" / "resources.sqlite"
        self.lock_path = self.path.with_suffix(".guard.lock")
        self.capacity, self.max_records, self.wait_ms = capacity, max_records, wait_ms
        self.fault = fault
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(self.lock_path, timeout_seconds=wait_ms / 1000):
            if initialize == self.path.exists():
                raise JournalError("RESOURCE_EXISTS" if initialize else "RESOURCE_MISSING")
            db = self._connect()
            try:
                if initialize:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("CREATE TABLE meta (schema TEXT, policy TEXT)")
                    db.execute("INSERT INTO meta VALUES (?,?)", ("fleet.resources/1", canonical(self._policy()).decode()))
                    db.execute("CREATE TABLE reservations (operation_id TEXT UNIQUE NOT NULL, reservation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, record TEXT NOT NULL)")
                    db.execute("COMMIT")
                self._validate(db)
            finally:
                db.close()

    def _policy(self):
        return {"capacity": self.capacity, "max_records": self.max_records, "wait_ms": self.wait_ms}

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=self.wait_ms / 1000, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=FULL")
        return db

    def _validate(self, db):
        try:
            meta = db.execute("SELECT * FROM meta").fetchall()
            if meta != [("fleet.resources/1", canonical(self._policy()).decode())] or db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError()
            for row in db.execute("SELECT * FROM reservations"):
                rec = json.loads(row[3])
                if (rec["operation_id"] != row[0] or rec["reservation_id"] != row[1]
                        or rec["request_sha256"] != row[2] or rec["status"] not in {"ACTIVE", "UNKNOWN", "RELEASED"}
                        or digest(rec["request"]) != rec["request_sha256"]):
                    raise ValueError()
        except Exception:
            raise JournalError("RESOURCE_STATE_INVALID") from None

    @contextmanager
    def transaction(self):
        with _exclusive_file_lock(self.lock_path, timeout_seconds=self.wait_ms / 1000):
            db = self._connect()
            try:
                self._validate(db); db.execute("BEGIN IMMEDIATE")
                yield db
                if self.fault: self.fault("before_commit")
                db.execute("COMMIT")
                if self.fault: self.fault("after_commit")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            finally:
                db.close()

    def reserve(self, operation_id, *, kind, resources, lease, armed_ownership):
        _id(operation_id)
        if kind not in KINDS:
            raise JournalError("RESOURCE_KIND_INVALID")
        observed = physical_resources(resources)
        request = {"operation_id": operation_id, "kind": kind, "resources": observed}
        sha = digest(request)
        authority = OwnershipAuthority(self.root)
        # All users take the core authority guard before the resource DB guard.
        with authority.transaction():
            current = authority.load()
            owner = _read_json_object(self.root / "runs" / ".active.lock", attempts=1)
            if (current != armed_ownership or current["disposition"] != "ACTIVE"
                    or current["phase"] != "ARMED" or getattr(lease, "namespace", None) != "native"
                    or getattr(lease, "released", True) or Path(lease.root).resolve() != self.root
                    or current["token"] != lease.token or current["operation_id"] != lease.operation_id
                    or owner.get("token") != lease.token or owner.get("identity") != current_identity()):
                raise JournalError("COMMON_NATIVE_AUTHORITY_REQUIRED")
            with self.transaction() as db:
                prior = db.execute("SELECT * FROM reservations WHERE operation_id=?", (operation_id,)).fetchone()
                if prior:
                    rec = json.loads(prior[3])
                    if prior[2] != sha or rec["ownership"] != current:
                        raise JournalError("RESOURCE_OPERATION_CONFLICT")
                    return rec
                all_rows = [json.loads(row[0]) for row in db.execute("SELECT record FROM reservations")]
                if len(all_rows) >= self.max_records:
                    raise JournalError("RESOURCE_CAPACITY")
                active = [row for row in all_rows if row["status"] != "RELEASED"]
                if len(active) >= self.capacity:
                    raise JournalError("RESOURCE_BUSY")
                keys = {row["physical_key"] for row in observed}
                paths = {row["path"] for row in observed}
                for held in active:
                    for row in held["request"]["resources"]:
                        if row["physical_key"] in keys or any(
                                p == row["path"] or p.startswith(row["path"] + os.sep)
                                or row["path"].startswith(p + os.sep) for p in paths):
                            raise JournalError("RESOURCE_BUSY")
                rec = {"schema": "fleet.resource-reservation/1", "reservation_id": "res_" + uuid.uuid4().hex,
                    "operation_id": operation_id, "request_sha256": sha, "request": request,
                    "ownership": current, "status": "ACTIVE", "closure": None,
                    "queue_authority": "COMMON_NATIVE_FIFO", "capacity": 1}
                db.execute("INSERT INTO reservations VALUES (?,?,?,?)", (operation_id,
                    rec["reservation_id"], sha, canonical(rec).decode()))
                return rec

    def release(self, reservation_id):
        _id(reservation_id)
        authority = OwnershipAuthority(self.root)
        with authority.transaction():
            current = authority.load()
            with self.transaction() as db:
                row = db.execute("SELECT record FROM reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
                if row is None:
                    raise JournalError("RESOURCE_UNKNOWN")
                rec = json.loads(row[0])
                expected = rec["ownership"]
                if rec["status"] == "RELEASED":
                    return rec
                if (current["disposition"] != "CLOSED" or current["phase"] != "CLOSED"
                        or current["epoch"] != expected["epoch"] or current["generation"] != expected["generation"]
                        or current["descendants"] != "NONE" or current["worker"] is not None):
                    raise JournalError("EXACT_CLOSURE_UNPROVEN")
                rec.update(status="RELEASED", closure=current)
                db.execute("UPDATE reservations SET record=? WHERE reservation_id=?", (canonical(rec).decode(), reservation_id))
                return rec

    def uncertain(self, reservation_id):
        with self.transaction() as db:
            row = db.execute("SELECT record FROM reservations WHERE reservation_id=?", (_id(reservation_id),)).fetchone()
            if row is None:
                raise JournalError("RESOURCE_UNKNOWN")
            rec = json.loads(row[0])
            if rec["status"] != "RELEASED":
                rec["status"] = "UNKNOWN"
                db.execute("UPDATE reservations SET record=? WHERE reservation_id=?", (canonical(rec).decode(), reservation_id))
            return rec

    def snapshot(self):
        with self.transaction() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT record FROM reservations ORDER BY rowid")]
