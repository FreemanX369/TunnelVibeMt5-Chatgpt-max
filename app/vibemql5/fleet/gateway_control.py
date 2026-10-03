"""Trusted local gateway control state. This module does not authenticate requests."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.jobs import _exclusive_file_lock
from ..errors import VibeMQL5Error

SCHEMA = "fleet.gateway.control/1"
RECOVERY_SCHEMA = "fleet.gateway.control/2"
_MAX = (1 << 63) - 1
_DEVICE = re.compile(r"dev_[a-f0-9]{32}\Z")
_KEY = re.compile(r"[a-f0-9]{64}\Z")
_GRANT = re.compile(r"grant_[a-f0-9]{32}\Z")
_CODES = frozenset({
    "CONTROL_INVALID", "CONTROL_MISSING", "CONTROL_EXISTS", "CONTROL_BUSY",
    "CONTROL_POLICY_MISMATCH", "CONTROL_CORRUPT", "CONTROL_REVISION_CONFLICT",
    "CONTROL_OPERATION_CONFLICT", "CONTROL_CAPACITY", "CONTROL_GRANT_INVALID",
    "CONTROL_GRANT_EXPIRED", "CONTROL_GRANT_USED", "CONTROL_ROUTE_MISMATCH",
    "CONTROL_REVOKED", "CONTROL_REPLAY", "CONTROL_TIME_INVALID",
    "CONTROL_CLOCK_ROLLBACK", "CONTROL_RECONCILIATION_REQUIRED",
    "CONTROL_STORAGE_FAILED", "CONTROL_TRANSACTION_FAILED",
    "CONTROL_COMMIT_UNCERTAIN", "CONTROL_CLOSED",
})


class GatewayControlError(VibeMQL5Error):
    def __init__(self, code: str):
        self.code = code if code in _CODES else "CONTROL_STORAGE_FAILED"
        super().__init__(self.code)


def _fail(code):
    raise GatewayControlError(code)


def _integer(value, *, positive=False, code="CONTROL_INVALID"):
    if type(value) is not int or not (1 if positive else 0) <= value <= _MAX:
        _fail(code)
    return value


def _match(value, pattern):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail("CONTROL_INVALID")
    return value


def _text(value, limit):
    if type(value) is not str or not value or value != value.strip() or "\0" in value:
        _fail("CONTROL_INVALID")
    try:
        if len(value.encode("utf-8")) > limit:
            _fail("CONTROL_INVALID")
    except UnicodeError:
        _fail("CONTROL_INVALID")
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value):
    return hashlib.sha256(_json(value).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Policy:
    singleton_wait_ms: int
    sqlite_busy_timeout_ms: int
    grant_ttl_ms: int
    clock_skew_ms: int
    nonce_retention_ms: int
    grant_secret_bytes: int
    max_devices: int
    max_grants: int
    max_nonces: int
    max_operations: int
    max_nonce_bytes: int
    max_operation_id_bytes: int

    def __post_init__(self):
        for name, value in asdict(self).items():
            _integer(value, positive=name != "clock_skew_ms")
        # Mechanism ceilings bound allocation/storage/waits. These are not a
        # deployment profile: every actual value remains a required input.
        bounds = {
            "singleton_wait_ms": 60_000, "sqlite_busy_timeout_ms": 60_000,
            "grant_ttl_ms": 604_800_000, "clock_skew_ms": 300_000,
            "nonce_retention_ms": 604_800_000, "grant_secret_bytes": 64,
            "max_devices": 4096, "max_grants": 65536, "max_nonces": 65536,
            "max_operations": 65536, "max_nonce_bytes": 4096,
            "max_operation_id_bytes": 1024,
        }
        if any(getattr(self, name) > maximum for name, maximum in bounds.items()):
            _fail("CONTROL_INVALID")
        if self.grant_secret_bytes < 32:
            _fail("CONTROL_INVALID")
        if self.nonce_retention_ms < 2 * self.clock_skew_ms:
            _fail("CONTROL_INVALID")
        # SQLite's busy_timeout pragma uses a signed 32-bit millisecond count.
        if self.sqlite_busy_timeout_ms > (1 << 31) - 1:
            _fail("CONTROL_INVALID")


_SQL = (
    "CREATE TABLE control (singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), status TEXT NOT NULL, policy TEXT NOT NULL, last_wall_ms INTEGER NOT NULL CHECK(last_wall_ms>=0))",
    "CREATE TABLE devices (device_id TEXT PRIMARY KEY, public_key TEXT NOT NULL, route_generation INTEGER NOT NULL CHECK(route_generation>0), state TEXT NOT NULL CHECK(state IN ('ACTIVE','REVOKED')))",
    "CREATE TABLE grants (grant_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, public_key TEXT NOT NULL, expected_route_generation INTEGER, expires_ms INTEGER NOT NULL CHECK(expires_ms>=0), secret_sha256 TEXT NOT NULL, consumed INTEGER NOT NULL CHECK(consumed IN (0,1)))",
    "CREATE TABLE nonces (device_id TEXT NOT NULL, route_generation INTEGER NOT NULL CHECK(route_generation>=0), nonce_sha256 TEXT NOT NULL, request_sha256 TEXT NOT NULL, timestamp_ms INTEGER NOT NULL CHECK(timestamp_ms>=0), received_ms INTEGER NOT NULL CHECK(received_ms>=0), retain_until_ms INTEGER NOT NULL CHECK(retain_until_ms>=0), purpose TEXT NOT NULL CHECK(purpose IN ('NODE_ROUTE','PAIR')), PRIMARY KEY(device_id,route_generation,nonce_sha256))",
    "CREATE TABLE operations (operation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, receipt TEXT NOT NULL)",
)
_TABLES = {"control", "devices", "grants", "nonces", "operations"}
_SCHEMA_OBJECTS = {
    **{("table", statement.split()[2]): (statement.split()[2], statement) for statement in _SQL},
    **{("index", "sqlite_autoindex_" + name + "_1"): (name, None)
       for name in ("devices", "grants", "nonces", "operations")},
}
_RECOVERY_SQL = "CREATE TABLE recovery (singleton INTEGER PRIMARY KEY CHECK(singleton=1), record TEXT NOT NULL)"
_RECEIPT_FIELDS = {"schema", "operation_id", "operation", "revision", "device_id",
                   "route_generation", "public_key", "grant_id", "expires_ms", "state",
                   "evidence", "authentication", "dispatch_enabled"}


class GatewayControlStore:
    """One cooperative writer for one canonical SQLite resource, held until close.

    The owner invokes these internal APIs after applying its own trust boundary.
    Persisted public keys are references, not proof of Ed25519 possession. Receipts
    never authorize dispatch. Use one owning thread; no MCP adapter opens a store.
    """

    def __init__(self, path, policy, lock, db, fault):
        self.path, self.policy = path, policy
        self._lock, self._db, self._fault = lock, db, fault
        self._owner_thread = threading.get_ident()

    @staticmethod
    def _path(path):
        try:
            result = Path(path).resolve()
            if result.exists() and (not result.is_file() or result.stat().st_nlink != 1):
                _fail("CONTROL_INVALID")
            return result
        except GatewayControlError:
            raise
        except (OSError, ValueError, TypeError, RuntimeError):
            _fail("CONTROL_INVALID")

    @staticmethod
    def _policy(policy):
        if type(policy) is not Policy:
            _fail("CONTROL_INVALID")
        policy.__post_init__()

    @classmethod
    def _acquire(cls, path, policy):
        cls._policy(policy)
        path = cls._path(path)
        lock = _exclusive_file_lock(path.with_name(path.name + ".owner.lock"),
                                    timeout_seconds=policy.singleton_wait_ms / 1000)
        try:
            lock.__enter__()
        except TimeoutError:
            _fail("CONTROL_BUSY")
        except (OSError, ValueError, OverflowError):
            _fail("CONTROL_STORAGE_FAILED")
        return path, lock

    @staticmethod
    def _connect(path, policy):
        db = sqlite3.connect(path, timeout=policy.sqlite_busy_timeout_ms / 1000,
                             isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute(f"PRAGMA busy_timeout={policy.sqlite_busy_timeout_ms}")
            db.execute("PRAGMA synchronous=FULL")
            return db
        except BaseException:
            db.close()
            raise

    @staticmethod
    def _dispose(db, lock):
        # Preserve a sanitized primary error (or an interrupt), while always
        # releasing the OS resource even if SQLite cleanup itself fails.
        try:
            if db is not None:
                db.close()
        except sqlite3.Error:
            pass
        finally:
            try:
                lock.__exit__(None, None, None)
            except OSError:
                pass

    @classmethod
    def initialize(cls, path, *, policy, fault=None):
        path, lock = cls._acquire(path, policy)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.initialize")
        db = None
        published = False
        try:
            if path.exists():
                _fail("CONTROL_EXISTS")
            db = cls._connect(temporary, policy)
            if db.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
                _fail("CONTROL_STORAGE_FAILED")
            store = cls(path, policy, lock, db, fault)
            with store._transaction("initialize", faults=False):
                for statement in _SQL:
                    db.execute(statement)
                db.execute("PRAGMA user_version=1")
                db.execute("INSERT INTO control VALUES (1,?,?,?,?,?)",
                           (SCHEMA, 1, "READY_CONTROL_ONLY", _json(asdict(policy)), 0))
                store._inject("initialize:before_commit")
            store._validate()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.close()
            db = None
            # Cooperative ownership excludes a second initializer. Publish only
            # the complete database, so a crash cannot expose a half-schema file.
            os.replace(temporary, path)
            published = True
            db = cls._connect(path, policy)
            store = cls(path, policy, lock, db, fault)
            store._validate()
            store._inject("initialize:after_commit")
            return store
        except GatewayControlError:
            cls._dispose(db, lock)
            raise
        except (sqlite3.Error, OSError, ValueError, OverflowError):
            cls._dispose(db, lock)
            _fail("CONTROL_COMMIT_UNCERTAIN" if published else "CONTROL_STORAGE_FAILED")
        except BaseException:
            cls._dispose(db, lock)
            raise
        finally:
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(temporary) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass

    @classmethod
    def open_existing(cls, path, *, policy, fault=None):
        cls._policy(policy)
        path = cls._path(path)
        if not path.is_file():
            _fail("CONTROL_MISSING")
        path, lock = cls._acquire(path, policy)
        db = None
        try:
            if not path.is_file():
                _fail("CONTROL_MISSING")
            db = cls._connect(path, policy)
            store = cls(path, policy, lock, db, fault)
            store._validate()
            if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                _fail("CONTROL_CORRUPT")
            return store
        except GatewayControlError:
            cls._dispose(db, lock)
            raise
        except (sqlite3.Error, OSError, ValueError, OverflowError):
            cls._dispose(db, lock)
            _fail("CONTROL_CORRUPT")
        except BaseException:
            cls._dispose(db, lock)
            raise

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *_):
        self.close()

    def _open(self):
        if self._db is None:
            _fail("CONTROL_CLOSED")
        if threading.get_ident() != self._owner_thread:
            _fail("CONTROL_BUSY")

    def close(self):
        if self._db is None:
            return
        self._open()
        db, lock = self._db, self._lock
        try:
            db.close()
        except sqlite3.Error:
            _fail("CONTROL_STORAGE_FAILED")
        self._db = self._lock = None
        try:
            lock.__exit__(None, None, None)
        except OSError:
            _fail("CONTROL_STORAGE_FAILED")

    @contextmanager
    def _transaction(self, operation, *, faults=True):
        self._open()
        committed = False
        try:
            self._db.execute("BEGIN IMMEDIATE")
            yield
            if faults:
                self._inject(operation + ":before_commit")
            self._db.commit()
            committed = True
            if faults:
                self._inject(operation + ":after_commit")
        except GatewayControlError:
            if not committed:
                self._rollback()
            raise
        except Exception:
            if not committed:
                try:
                    self._rollback()
                except sqlite3.Error:
                    pass
            _fail("CONTROL_COMMIT_UNCERTAIN" if committed else "CONTROL_TRANSACTION_FAILED")
        except BaseException:
            if not committed:
                try:
                    self._rollback()
                except GatewayControlError:
                    pass
            raise

    def _rollback(self):
        try:
            self._db.rollback()
        except sqlite3.Error:
            self.close()
            _fail("CONTROL_STORAGE_FAILED")

    def _inject(self, point):
        if self._fault:
            try:
                self._fault(point)
            except Exception:
                _fail("CONTROL_COMMIT_UNCERTAIN" if point.endswith(":after_commit") else "CONTROL_TRANSACTION_FAILED")

    def _control(self):
        row = self._db.execute("SELECT * FROM control WHERE singleton=1").fetchone()
        if row is None:
            _fail("CONTROL_CORRUPT")
        return dict(row)

    def _ready(self):
        if self._control()["status"] != "READY_CONTROL_ONLY":
            _fail("CONTROL_RECONCILIATION_REQUIRED")

    def _validate(self):
        try:
            if self._db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                _fail("CONTROL_CORRUPT")
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {1, 2}:
                _fail("CONTROL_CORRUPT")
            tables = {row[0] for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != _TABLES | ({"recovery"} if version == 2 else set()):
                _fail("CONTROL_CORRUPT")
            objects = {(row["type"], row["name"]): (row["tbl_name"], row["sql"])
                       for row in self._db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master")}
            expected_objects = {**_SCHEMA_OBJECTS, **({("table", "recovery"): ("recovery", _RECOVERY_SQL)} if version == 2 else {})}
            if objects != expected_objects:
                _fail("CONTROL_CORRUPT")
            if self._db.execute("SELECT count(*) FROM control").fetchone()[0] != 1:
                _fail("CONTROL_CORRUPT")
            control = self._control()
            if control["schema"] != (SCHEMA if version == 1 else RECOVERY_SCHEMA) or control["status"] not in {"READY_CONTROL_ONLY", "RECONCILIATION_REQUIRED"}:
                _fail("CONTROL_CORRUPT")
            _integer(control["revision"], positive=True, code="CONTROL_CORRUPT")
            _integer(control["last_wall_ms"], code="CONTROL_CORRUPT")
            if version == 2:
                self._validate_recovery_record(control)
            if control["policy"] != _json(asdict(self.policy)):
                try:
                    parsed = json.loads(control["policy"])
                    Policy(**parsed)
                except Exception:
                    _fail("CONTROL_CORRUPT")
                _fail("CONTROL_POLICY_MISMATCH")
            for table in ("devices", "grants", "nonces", "operations"):
                if self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > getattr(self.policy, "max_" + table):
                    _fail("CONTROL_CORRUPT")
            devices = {row["device_id"]: dict(row) for row in self._db.execute("SELECT * FROM devices")}
            for row in devices.values():
                _match(row["device_id"], _DEVICE); _match(row["public_key"], _KEY)
                _integer(row["route_generation"], positive=True)
                if row["state"] not in {"ACTIVE", "REVOKED"}:
                    _fail("CONTROL_CORRUPT")
            grants = {row["grant_id"]: dict(row) for row in self._db.execute("SELECT * FROM grants")}
            for row in grants.values():
                _match(row["grant_id"], _GRANT); _match(row["device_id"], _DEVICE)
                _match(row["public_key"], _KEY); _match(row["secret_sha256"], _KEY)
                _integer(row["expires_ms"])
                if row["expected_route_generation"] is not None:
                    _integer(row["expected_route_generation"], positive=True)
                if row["consumed"] not in (0, 1):
                    _fail("CONTROL_CORRUPT")
            for row in self._db.execute("SELECT * FROM nonces"):
                _match(row["device_id"], _DEVICE); _match(row["nonce_sha256"], _KEY)
                _match(row["request_sha256"], _KEY); _integer(row["route_generation"])
                if row["purpose"] not in {"NODE_ROUTE", "PAIR"} or (row["route_generation"] == 0 and row["purpose"] != "PAIR"):
                    _fail("CONTROL_CORRUPT")
                for name in ("timestamp_ms", "received_ms", "retain_until_ms"):
                    _integer(row[name])
                if row["device_id"] not in devices or row["route_generation"] > devices[row["device_id"]]["route_generation"]:
                    _fail("CONTROL_CORRUPT")
                if row["retain_until_ms"] < max(row["received_ms"] + self.policy.nonce_retention_ms,
                                                row["timestamp_ms"] + self.policy.clock_skew_ms):
                    _fail("CONTROL_CORRUPT")
                if row["received_ms"] > control["last_wall_ms"] or abs(row["timestamp_ms"] - row["received_ms"]) > self.policy.clock_skew_ms:
                    _fail("CONTROL_CORRUPT")
            pair_routes, issued_grants, paired_grants, revisions = set(), set(), set(), set()
            history = {device_id: [] for device_id in devices}
            for row in self._db.execute("SELECT * FROM operations"):
                _text(row["operation_id"], self.policy.max_operation_id_bytes)
                _match(row["request_sha256"], _KEY)
                receipt = json.loads(row["receipt"])
                self._validate_receipt(receipt, control["revision"])
                if row["receipt"] != _json(receipt):
                    _fail("CONTROL_CORRUPT")
                if receipt["operation_id"] != row["operation_id"]:
                    _fail("CONTROL_CORRUPT")
                if row["operation_id"].startswith("nodepair:") and receipt["operation"] != "PAIR":
                    _fail("CONTROL_CORRUPT")
                if receipt["revision"] in revisions:
                    _fail("CONTROL_CORRUPT")
                revisions.add(receipt["revision"])
                if receipt["operation"] in {"ISSUE_GRANT", "PAIR"}:
                    grant = grants.get(receipt["grant_id"])
                    if grant is None or any(receipt[name] != grant[name] for name in ("device_id", "public_key", "expires_ms")):
                        _fail("CONTROL_CORRUPT")
                    if receipt["operation"] == "ISSUE_GRANT":
                        if receipt["grant_id"] in issued_grants or receipt["route_generation"] != grant["expected_route_generation"]:
                            _fail("CONTROL_CORRUPT")
                        issued_grants.add(receipt["grant_id"])
                    else:
                        expected = 1 if grant["expected_route_generation"] is None else grant["expected_route_generation"] + 1
                        if not grant["consumed"] or receipt["route_generation"] != expected or receipt["grant_id"] in paired_grants:
                            _fail("CONTROL_CORRUPT")
                        paired_grants.add(receipt["grant_id"])
                if receipt["operation"] != "ISSUE_GRANT":
                    if receipt["device_id"] not in history:
                        _fail("CONTROL_CORRUPT")
                    history[receipt["device_id"]].append(receipt)
                if receipt["operation"] == "PAIR":
                    pair_routes.add((receipt["device_id"], receipt["route_generation"] - 1))
            if issued_grants != set(grants) or paired_grants != {key for key, value in grants.items() if value["consumed"]}:
                _fail("CONTROL_CORRUPT")
            for device_id, receipts in history.items():
                previous = None
                for receipt in sorted(receipts, key=lambda value: value["revision"]):
                    if receipt["route_generation"] != (1 if previous is None else previous["route_generation"] + 1):
                        _fail("CONTROL_CORRUPT")
                    operation = receipt["operation"]
                    if previous is None and operation != "PAIR":
                        _fail("CONTROL_CORRUPT")
                    if operation in {"REVOKE", "ROTATE"}:
                        if previous["state"] != "ACTIVE":
                            _fail("CONTROL_CORRUPT")
                        same_key = receipt["public_key"] == previous["public_key"]
                        if same_key != (operation == "REVOKE"):
                            _fail("CONTROL_CORRUPT")
                    previous = receipt
                if previous is None or any(devices[device_id][name] != previous[name] for name in ("public_key", "route_generation", "state")):
                    _fail("CONTROL_CORRUPT")
            for row in self._db.execute("SELECT device_id,route_generation FROM nonces WHERE purpose='PAIR'"):
                if (row["device_id"], row["route_generation"]) not in pair_routes:
                    _fail("CONTROL_CORRUPT")
        except GatewayControlError as exc:
            if exc.code == "CONTROL_POLICY_MISMATCH":
                raise
            _fail("CONTROL_CORRUPT")
        except (sqlite3.Error, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            _fail("CONTROL_CORRUPT")

    def _validate_receipt(self, receipt, revision):
        if type(receipt) is not dict or set(receipt) != _RECEIPT_FIELDS:
            _fail("CONTROL_CORRUPT")
        _text(receipt["operation_id"], self.policy.max_operation_id_bytes)
        _match(receipt["device_id"], _DEVICE); _match(receipt["public_key"], _KEY)
        _integer(receipt["revision"], positive=True)
        if not 2 <= receipt["revision"] <= revision or receipt["schema"] != "fleet.control.receipt/1":
            _fail("CONTROL_CORRUPT")
        if receipt["operation"] not in {"ISSUE_GRANT", "PAIR", "REVOKE", "ROTATE"}:
            _fail("CONTROL_CORRUPT")
        if receipt["state"] not in {"GRANT_ISSUED", "ACTIVE", "REVOKED"}:
            _fail("CONTROL_CORRUPT")
        if receipt["route_generation"] is not None:
            _integer(receipt["route_generation"], positive=True)
        if receipt["grant_id"] is not None:
            _match(receipt["grant_id"], _GRANT)
        if receipt["expires_ms"] is not None:
            _integer(receipt["expires_ms"])
        operation = receipt["operation"]
        if operation in {"ISSUE_GRANT", "PAIR"}:
            if receipt["grant_id"] is None or receipt["expires_ms"] is None:
                _fail("CONTROL_CORRUPT")
        elif receipt["grant_id"] is not None or receipt["expires_ms"] is not None:
            _fail("CONTROL_CORRUPT")
        if receipt["state"] != {"ISSUE_GRANT": "GRANT_ISSUED", "PAIR": "ACTIVE", "REVOKE": "REVOKED", "ROTATE": "ACTIVE"}[operation]:
            _fail("CONTROL_CORRUPT")
        if operation != "ISSUE_GRANT" and receipt["route_generation"] is None:
            _fail("CONTROL_CORRUPT")
        if receipt["evidence"] != "CONTROL_STATE_ONLY" or receipt["authentication"] != "NOT_VERIFIED" or receipt["dispatch_enabled"] is not False:
            _fail("CONTROL_CORRUPT")

    def snapshot(self):
        self._open()
        try:
            self._db.execute("BEGIN")
            self._validate()
            control = self._control()
            result = {"schema": control["schema"], "revision": control["revision"],
                      "status": control["status"], "policy": asdict(self.policy),
                      "last_wall_ms": control["last_wall_ms"],
                      "evidence": "CONTROL_STATE_ONLY", "authentication": "NOT_VERIFIED",
                      "dispatch_enabled": False}
            for table in ("devices", "grants", "nonces", "operations"):
                result[table] = [dict(row) for row in self._db.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
            for row in result["operations"]:
                row["receipt"] = json.loads(row["receipt"])
            self._db.commit()
            return result
        except GatewayControlError:
            self._rollback()
            raise
        except (sqlite3.Error, ValueError, TypeError):
            self._rollback()
            _fail("CONTROL_CORRUPT")
        except BaseException:
            self._rollback()
            raise

    def control_head(self):
        """Exact ledger head, excluding recovery/runtime status metadata."""
        value = self.snapshot()
        ledger = {key: value[key] for key in ("revision", "policy", "last_wall_ms",
                                              "devices", "grants", "nonces", "operations")}
        ledger["schema"] = "fleet.control-ledger/1"
        return {"schema": "fleet.control-head/1", "revision": value["revision"],
                "sha256": _digest(ledger)}

    def _recovery_record(self):
        if self._db.execute("PRAGMA user_version").fetchone()[0] != 2:
            _fail("CONTROL_RECONCILIATION_REQUIRED")
        rows = self._db.execute("SELECT record FROM recovery WHERE singleton=1").fetchall()
        if len(rows) != 1:
            _fail("CONTROL_CORRUPT")
        value = json.loads(rows[0]["record"])
        if rows[0]["record"] != _json(value):
            _fail("CONTROL_CORRUPT")
        return value

    def _validate_recovery_record(self, control):
        value = self._recovery_record()
        fields = {"schema", "anchor", "anchor_wall_ms", "phase", "coordination_sha256", "control_commit_revision", "ready_revision"}
        if type(value) is not dict or set(value) != fields or value["schema"] != "fleet.control-recovery/1":
            _fail("CONTROL_CORRUPT")
        anchor = value["anchor"]
        if type(anchor) is not dict or set(anchor) != {"schema", "revision", "sha256"} or anchor["schema"] != "fleet.control-head/1":
            _fail("CONTROL_CORRUPT")
        _integer(anchor["revision"], positive=True); _match(anchor["sha256"], _KEY)
        _integer(value["anchor_wall_ms"])
        if value["anchor_wall_ms"] > control["last_wall_ms"]:
            _fail("CONTROL_CORRUPT")
        if anchor["revision"] >= control["revision"]:
            _fail("CONTROL_CORRUPT")
        if value["phase"] not in {"FENCED", "CONTROL_RECONCILIATION_COMMITTED", "CONTROL_READY"}:
            _fail("CONTROL_CORRUPT")
        if value["phase"] == "FENCED":
            if value["control_commit_revision"] is not None or value["ready_revision"] is not None:
                _fail("CONTROL_CORRUPT")
        else:
            _integer(value["control_commit_revision"], positive=True)
            if value["control_commit_revision"] > control["revision"]:
                _fail("CONTROL_CORRUPT")
            _match(value["coordination_sha256"], _KEY)
        if value["coordination_sha256"] is not None:
            _match(value["coordination_sha256"], _KEY)
        if value["phase"] == "CONTROL_READY":
            _integer(value["ready_revision"], positive=True)
            if not value["control_commit_revision"] < value["ready_revision"] <= control["revision"] or control["status"] != "READY_CONTROL_ONLY":
                _fail("CONTROL_CORRUPT")
        elif control["status"] != "RECONCILIATION_REQUIRED" or value["ready_revision"] is not None:
            _fail("CONTROL_CORRUPT")

    def restored_control_anchor(self):
        self._open()
        self._validate()
        return dict(self._recovery_record()["anchor"])

    def assert_restored_ledger(self):
        value, record = self.snapshot(), self._recovery_record()
        ledger = {key: value[key] for key in ("revision", "policy", "last_wall_ms",
                                              "devices", "grants", "nonces", "operations")}
        ledger.update(schema="fleet.control-ledger/1", revision=record["anchor"]["revision"],
                      last_wall_ms=record["anchor_wall_ms"])
        if _digest(ledger) != record["anchor"]["sha256"]:
            _fail("CONTROL_RECONCILIATION_REQUIRED")
        return record["anchor"]

    def recovery_state(self):
        self._open()
        self._validate()
        if self._db.execute("PRAGMA user_version").fetchone()[0] == 1:
            return None
        return self._recovery_record()

    def commit_coordinated_recovery(self, coordinator):
        from .restore_coordination import RestoreCoordinator
        if type(coordinator) is not RestoreCoordinator:
            _fail("CONTROL_RECONCILIATION_REQUIRED")
        scope_sha = coordinator.assert_control_commit(self)
        with self._transaction("commit_coordinated_recovery"):
            value = self._recovery_record()
            if value["coordination_sha256"] not in {None, scope_sha}:
                _fail("CONTROL_OPERATION_CONFLICT")
            if value["phase"] == "FENCED":
                revision = self._control()["revision"] + 1
                if revision > _MAX:
                    _fail("CONTROL_CAPACITY")
                value.update(phase="CONTROL_RECONCILIATION_COMMITTED", coordination_sha256=scope_sha,
                             control_commit_revision=revision)
                self._db.execute("UPDATE recovery SET record=? WHERE singleton=1", (_json(value),))
                self._db.execute("UPDATE control SET revision=? WHERE singleton=1", (revision,))
        return self.recovery_state()

    def complete_coordinated_recovery(self, coordinator):
        from .restore_coordination import RestoreCoordinator
        if type(coordinator) is not RestoreCoordinator:
            _fail("CONTROL_RECONCILIATION_REQUIRED")
        scope_sha = coordinator.assert_control_ready(self)
        with self._transaction("complete_coordinated_recovery"):
            value = self._recovery_record()
            if value["coordination_sha256"] != scope_sha or value["phase"] == "FENCED":
                _fail("CONTROL_RECONCILIATION_REQUIRED")
            if value["phase"] != "CONTROL_READY":
                revision = self._control()["revision"] + 1
                if revision > _MAX:
                    _fail("CONTROL_CAPACITY")
                value.update(phase="CONTROL_READY", ready_revision=revision)
                self._db.execute("UPDATE recovery SET record=? WHERE singleton=1", (_json(value),))
                self._db.execute("UPDATE control SET status='READY_CONTROL_ONLY',revision=? WHERE singleton=1", (revision,))
        return self.recovery_state()

    def get_route(self, device_id):
        """Return control inventory for signature lookup, never admission authority."""
        self._open()
        _match(device_id, _DEVICE)
        self._validate()
        current = self._device(device_id)
        if current is None:
            _fail("CONTROL_ROUTE_MISMATCH")
        control = self._control()
        return {"schema": "fleet.control.route/1", **current,
                "revision": control["revision"], "status": control["status"],
                "evidence": "CONTROL_STATE_ONLY", "authentication": "NOT_VERIFIED",
                "dispatch_enabled": False}

    def _capacity(self, table):
        if self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] >= getattr(self.policy, "max_" + table):
            _fail("CONTROL_CAPACITY")

    def _observe_wall(self, now_ms):
        # A denied expired grant must still remember the observed server time;
        # otherwise a later rollback could resurrect it. This observation changes
        # only metadata, never a revision, route, grant, nonce or operation.
        with self._transaction("observe_wall", faults=False):
            self._ready()
            control = self._control()
            if now_ms < control["last_wall_ms"]:
                _fail("CONTROL_CLOCK_ROLLBACK")
            self._db.execute("UPDATE control SET last_wall_ms=? WHERE singleton=1", (now_ms,))

    def _device(self, device_id):
        row = self._db.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
        return dict(row) if row is not None else None

    def _route(self, device_id, expected):
        current = self._device(device_id)
        if (None if current is None else current["route_generation"]) != expected:
            _fail("CONTROL_ROUTE_MISMATCH")
        return current

    def _receipt(self, operation_id, operation, device_id, public_key, *, route=None,
                 grant_id=None, expires_ms=None, state="ACTIVE"):
        return {"schema": "fleet.control.receipt/1", "operation_id": operation_id,
                "operation": operation, "revision": self._control()["revision"] + 1,
                "device_id": device_id, "route_generation": route, "public_key": public_key,
                "grant_id": grant_id, "expires_ms": expires_ms, "state": state,
                "evidence": "CONTROL_STATE_ONLY", "authentication": "NOT_VERIFIED",
                "dispatch_enabled": False}

    def _admin(self, operation, operation_id, request, expected_revision, now_ms, body):
        self._open()
        self._validate()
        _text(operation_id, self.policy.max_operation_id_bytes)
        if operation_id.startswith("nodepair:"):
            _fail("CONTROL_INVALID")
        _integer(expected_revision, positive=True)
        _integer(now_ms, code="CONTROL_TIME_INVALID")
        digest = _digest({"operation": operation, **request, "expected_revision": expected_revision})
        self._ready()
        prior = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if prior is not None:
            if prior["request_sha256"] != digest:
                _fail("CONTROL_OPERATION_CONFLICT")
            receipt = json.loads(prior["receipt"])
            self._validate_receipt(receipt, self._control()["revision"])
            return {"receipt": receipt, "idempotent_recovered": True}
        self._observe_wall(now_ms)
        with self._transaction(operation):
            self._ready()
            self._capacity("operations")
            control = self._control()
            if expected_revision != control["revision"]:
                _fail("CONTROL_REVISION_CONFLICT")
            if control["revision"] == _MAX:
                _fail("CONTROL_CAPACITY")
            receipt, extra = body()
            self._db.execute("INSERT INTO operations VALUES (?,?,?)", (operation_id, digest, _json(receipt)))
            self._db.execute("UPDATE control SET revision=? WHERE singleton=1", (receipt["revision"],))
        return {"receipt": receipt, "idempotent_recovered": False, **extra}

    def issue_grant(self, device_id, public_key, *, expected_route_generation,
                    expected_revision, operation_id, now_ms):
        _match(device_id, _DEVICE); _match(public_key, _KEY)
        if expected_route_generation is not None:
            _integer(expected_route_generation, positive=True)
        def body():
            self._route(device_id, expected_route_generation)
            self._capacity("grants")
            if now_ms > _MAX - self.policy.grant_ttl_ms:
                _fail("CONTROL_TIME_INVALID")
            grant_id = "grant_" + uuid.uuid4().hex
            secret = secrets.token_hex(self.policy.grant_secret_bytes)
            secret_digest = hashlib.sha256(bytes.fromhex(secret)).hexdigest()
            expiry = now_ms + self.policy.grant_ttl_ms
            self._db.execute("INSERT INTO grants VALUES (?,?,?,?,?,?,0)",
                             (grant_id, device_id, public_key, expected_route_generation, expiry, secret_digest))
            receipt = self._receipt(operation_id, "ISSUE_GRANT", device_id, public_key,
                                    route=expected_route_generation, grant_id=grant_id,
                                    expires_ms=expiry, state="GRANT_ISSUED")
            return receipt, {"secret": secret}
        result = self._admin("issue_grant", operation_id,
                             {"device_id": device_id, "public_key": public_key,
                              "expected_route_generation": expected_route_generation},
                             expected_revision, now_ms, body)
        result.setdefault("secret", None)
        return result

    def consume_grant(self, grant_id, secret, device_id, public_key, *, expected_revision,
                      operation_id, now_ms):
        _match(grant_id, _GRANT); _match(device_id, _DEVICE); _match(public_key, _KEY)
        if type(secret) is not str or len(secret) != 2 * self.policy.grant_secret_bytes or re.fullmatch(r"[a-f0-9]+", secret) is None:
            _fail("CONTROL_GRANT_INVALID")
        secret_digest = hashlib.sha256(bytes.fromhex(secret)).hexdigest()
        def body():
            row = self._db.execute("SELECT * FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
            if row is None or row["device_id"] != device_id or row["public_key"] != public_key or not secrets.compare_digest(row["secret_sha256"], secret_digest):
                _fail("CONTROL_GRANT_INVALID")
            if row["consumed"]:
                _fail("CONTROL_GRANT_USED")
            if now_ms >= row["expires_ms"]:
                _fail("CONTROL_GRANT_EXPIRED")
            current = self._route(device_id, row["expected_route_generation"])
            if current is None:
                self._capacity("devices")
            generation = 1 if current is None else current["route_generation"] + 1
            if generation > _MAX:
                _fail("CONTROL_CAPACITY")
            self._db.execute("INSERT INTO devices VALUES (?,?,?,'ACTIVE') ON CONFLICT(device_id) DO UPDATE SET public_key=excluded.public_key, route_generation=excluded.route_generation,state='ACTIVE'",
                             (device_id, public_key, generation))
            self._db.execute("UPDATE grants SET consumed=1 WHERE grant_id=?", (grant_id,))
            return self._receipt(operation_id, "PAIR", device_id, public_key,
                                 route=generation, grant_id=grant_id, expires_ms=row["expires_ms"]), {}
        return self._admin("consume_grant", operation_id,
                           {"grant_id": grant_id, "secret_sha256": secret_digest,
                            "device_id": device_id, "public_key": public_key},
                           expected_revision, now_ms, body)

    def consume_verified_grant(self, grant_id, secret, device_id, public_key, *,
                               expected_revision, operation_id, now_ms,
                               signed_route_generation, nonce, request_sha256,
                               timestamp_ms):
        """Concrete trusted boundary used solely by the verified wire controller.

        Ed25519 verification happens outside SQLite. This method rechecks the
        exact grant/key/secret/original route and commits the signed request's
        nonce, pairing mutation and logical receipt together. Transport nonce
        and time never change the logical operation digest. There is no public
        authentication flag and no caller-provided transaction callback.
        """
        self._open()
        self._validate()
        _match(grant_id, _GRANT); _match(device_id, _DEVICE); _match(public_key, _KEY)
        _integer(expected_revision, positive=True)
        _integer(signed_route_generation)
        _text(operation_id, self.policy.max_operation_id_bytes)
        if not operation_id.startswith("nodepair:") or operation_id == "nodepair:":
            _fail("CONTROL_INVALID")
        self._nonce_inputs(nonce, request_sha256, timestamp_ms, now_ms)
        if type(secret) is not str or len(secret) != 2 * self.policy.grant_secret_bytes or re.fullmatch(r"[a-f0-9]+", secret) is None:
            _fail("CONTROL_GRANT_INVALID")
        secret_digest = hashlib.sha256(bytes.fromhex(secret)).hexdigest()
        digest = _digest({"operation": "consume_grant", "grant_id": grant_id,
                          "secret_sha256": secret_digest, "device_id": device_id,
                          "public_key": public_key, "expected_revision": expected_revision})
        self._observe_wall(now_ms)
        with self._transaction("consume_verified_grant"):
            self._ready()
            control = self._control()
            row = self._db.execute("SELECT * FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
            if row is None or row["device_id"] != device_id or row["public_key"] != public_key or not secrets.compare_digest(row["secret_sha256"], secret_digest):
                _fail("CONTROL_GRANT_INVALID")
            original_route = row["expected_route_generation"]
            if signed_route_generation != (0 if original_route is None else original_route):
                _fail("CONTROL_ROUTE_MISMATCH")
            prior = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            recovered = prior is not None
            if recovered:
                if prior["request_sha256"] != digest:
                    _fail("CONTROL_OPERATION_CONFLICT")
                receipt = json.loads(prior["receipt"])
                self._validate_receipt(receipt, control["revision"])
                if receipt["operation"] != "PAIR" or receipt["grant_id"] != grant_id or not row["consumed"]:
                    _fail("CONTROL_CORRUPT")
                # A receipt retry must not repaint revoked/rotated/re-paired
                # state. The ordinary route API supplies current authority.
                current = self._route(device_id, receipt["route_generation"])
                if current is None or current["public_key"] != public_key:
                    _fail("CONTROL_ROUTE_MISMATCH")
                if current["state"] != "ACTIVE":
                    _fail("CONTROL_REVOKED")
            else:
                self._capacity("operations")
                if expected_revision != control["revision"]:
                    _fail("CONTROL_REVISION_CONFLICT")
                if row["consumed"]:
                    _fail("CONTROL_GRANT_USED")
                if now_ms >= row["expires_ms"]:
                    _fail("CONTROL_GRANT_EXPIRED")
                current = self._route(device_id, original_route)
                if current is None:
                    self._capacity("devices")
                generation = 1 if current is None else current["route_generation"] + 1
                if generation > _MAX:
                    _fail("CONTROL_CAPACITY")
                self._db.execute("INSERT INTO devices VALUES (?,?,?,'ACTIVE') ON CONFLICT(device_id) DO UPDATE SET public_key=excluded.public_key,route_generation=excluded.route_generation,state='ACTIVE'",
                                 (device_id, public_key, generation))
                self._db.execute("UPDATE grants SET consumed=1 WHERE grant_id=?", (grant_id,))
                receipt = self._receipt(operation_id, "PAIR", device_id, public_key,
                                        route=generation, grant_id=grant_id, expires_ms=row["expires_ms"])
            revision = control["revision"] + 1
            if revision > _MAX:
                _fail("CONTROL_CAPACITY")
            nonce_receipt = self._insert_nonce(device_id, signed_route_generation,
                nonce, request_sha256, timestamp_ms, now_ms, revision, purpose="PAIR")
            if not recovered:
                self._db.execute("INSERT INTO operations VALUES (?,?,?)", (operation_id, digest, _json(receipt)))
            self._db.execute("UPDATE control SET revision=? WHERE singleton=1", (revision,))
        return {"receipt": receipt, "idempotent_recovered": recovered,
                "nonce_receipt": nonce_receipt}

    def revoke(self, device_id, *, expected_route_generation, expected_revision, operation_id, now_ms):
        _match(device_id, _DEVICE); _integer(expected_route_generation, positive=True)
        def body():
            current = self._route(device_id, expected_route_generation)
            if current is None:
                _fail("CONTROL_ROUTE_MISMATCH")
            if current["state"] == "REVOKED":
                _fail("CONTROL_REVOKED")
            generation = current["route_generation"] + 1
            if generation > _MAX:
                _fail("CONTROL_CAPACITY")
            self._db.execute("UPDATE devices SET route_generation=?,state='REVOKED' WHERE device_id=?", (generation, device_id))
            return self._receipt(operation_id, "REVOKE", device_id, current["public_key"],
                                 route=generation, state="REVOKED"), {}
        return self._admin("revoke", operation_id,
                           {"device_id": device_id, "expected_route_generation": expected_route_generation},
                           expected_revision, now_ms, body)

    def rotate_key(self, device_id, new_public_key, *, expected_public_key,
                   expected_route_generation, expected_revision, operation_id, now_ms):
        _match(device_id, _DEVICE); _match(new_public_key, _KEY); _match(expected_public_key, _KEY)
        _integer(expected_route_generation, positive=True)
        if new_public_key == expected_public_key:
            _fail("CONTROL_INVALID")
        def body():
            current = self._route(device_id, expected_route_generation)
            if current is None or current["public_key"] != expected_public_key:
                _fail("CONTROL_ROUTE_MISMATCH")
            if current["state"] != "ACTIVE":
                _fail("CONTROL_REVOKED")
            generation = current["route_generation"] + 1
            if generation > _MAX:
                _fail("CONTROL_CAPACITY")
            self._db.execute("UPDATE devices SET public_key=?,route_generation=? WHERE device_id=?", (new_public_key, generation, device_id))
            return self._receipt(operation_id, "ROTATE", device_id, new_public_key, route=generation), {}
        return self._admin("rotate_key", operation_id,
                           {"device_id": device_id, "new_public_key": new_public_key,
                            "expected_public_key": expected_public_key,
                            "expected_route_generation": expected_route_generation},
                           expected_revision, now_ms, body)

    def reserve_nonce(self, device_id, *, route_generation, nonce, request_sha256,
                      timestamp_ms, now_ms, expected_public_key=None):
        self._open()
        self._validate()
        _match(device_id, _DEVICE); _integer(route_generation, positive=True)
        if expected_public_key is not None:
            _match(expected_public_key, _KEY)
        self._nonce_inputs(nonce, request_sha256, timestamp_ms, now_ms)
        self._observe_wall(now_ms)
        with self._transaction("reserve_nonce"):
            current = self._route(device_id, route_generation)
            if current is None:
                _fail("CONTROL_ROUTE_MISMATCH")
            if expected_public_key is not None and current["public_key"] != expected_public_key:
                _fail("CONTROL_ROUTE_MISMATCH")
            if current["state"] != "ACTIVE":
                _fail("CONTROL_REVOKED")
            revision = self._control()["revision"] + 1
            if revision > _MAX:
                _fail("CONTROL_TIME_INVALID")
            receipt = self._insert_nonce(device_id, route_generation, nonce,
                request_sha256, timestamp_ms, now_ms, revision, purpose="NODE_ROUTE")
            self._db.execute("UPDATE control SET revision=? WHERE singleton=1", (revision,))
        return receipt

    def _nonce_inputs(self, nonce, request_sha256, timestamp_ms, now_ms):
        _text(nonce, self.policy.max_nonce_bytes); _match(request_sha256, _KEY)
        _integer(timestamp_ms, code="CONTROL_TIME_INVALID"); _integer(now_ms, code="CONTROL_TIME_INVALID")

    def _insert_nonce(self, device_id, route_generation, nonce, request_sha256,
                      timestamp_ms, now_ms, revision, *, purpose):
        if abs(timestamp_ms - now_ms) > self.policy.clock_skew_ms:
            _fail("CONTROL_TIME_INVALID")
        digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        if self._db.execute("SELECT 1 FROM nonces WHERE device_id=? AND route_generation=? AND nonce_sha256=?", (device_id, route_generation, digest)).fetchone():
            _fail("CONTROL_REPLAY")
        self._capacity("nonces")
        retain_until = max(now_ms + self.policy.nonce_retention_ms, timestamp_ms + self.policy.clock_skew_ms)
        if retain_until > _MAX:
            _fail("CONTROL_TIME_INVALID")
        self._db.execute("INSERT INTO nonces VALUES (?,?,?,?,?,?,?,?)",
                         (device_id, route_generation, digest, request_sha256,
                          timestamp_ms, now_ms, retain_until, purpose))
        return {"schema": "fleet.control.nonce/1", "device_id": device_id,
                "route_generation": route_generation, "request_sha256": request_sha256,
                "nonce_sha256": digest, "revision": revision, "purpose": purpose,
                "evidence": "CONTROL_STATE_ONLY", "authentication": "NOT_VERIFIED",
                "dispatch_enabled": False}

    def backup(self, destination):
        self._open()
        self._validate()
        destination = self._path(destination)
        if destination == self.path:
            _fail("CONTROL_INVALID")
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.backup")
        lock = _exclusive_file_lock(destination.with_name(destination.name + ".owner.lock"),
                                    timeout_seconds=self.policy.singleton_wait_ms / 1000)
        db = None
        try:
            with lock:
                if destination.exists():
                    _fail("CONTROL_EXISTS")
                db = self._connect(temporary, self.policy)
                self._bounded_backup(db)
                candidate = type(self)(temporary, self.policy, None, db, None)
                candidate._validate()
                db.close()
                db = None
                os.replace(temporary, destination)
        except GatewayControlError:
            raise
        except TimeoutError:
            _fail("CONTROL_BUSY")
        except (sqlite3.Error, OSError, ValueError, OverflowError):
            _fail("CONTROL_STORAGE_FAILED")
        finally:
            if db is not None:
                db.close()
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(temporary) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass
        return {"schema": "fleet.control.backup/1", "revision": self._control()["revision"],
                "evidence": "CONSISTENT_SQLITE_SNAPSHOT", "dispatch_enabled": False}

    def _bounded_backup(self, destination):
        # SQLite backup otherwise retries an unrelated writer forever, ignoring
        # the connection busy_timeout. Apply the explicit SQLite wait budget.
        deadline = time.monotonic() + self.policy.sqlite_busy_timeout_ms / 1000
        def progress(_status, _remaining, _total):
            if time.monotonic() > deadline:
                _fail("CONTROL_BUSY")
        self._db.backup(destination, pages=64, progress=progress,
                        sleep=min(0.01, self.policy.sqlite_busy_timeout_ms / 1000))

    @classmethod
    def restore(cls, backup_path, destination, *, policy, fault=None):
        # Source copy is cooperative, validated and stable while copied. All
        # destination state is fenced before its first canonical publication.
        with cls.open_existing(backup_path, policy=policy) as source:
            # Explicit supported restore records the source ledger head before
            # adding its fence/revision. Opening an old v1 store never upgrades.
            anchor = source.control_head()
            if source._control()["status"] != "READY_CONTROL_ONLY":
                _fail("CONTROL_RECONCILIATION_REQUIRED")
            path, lock = cls._acquire(destination, policy)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore")
            db = None
            published = False
            try:
                if path.exists():
                    _fail("CONTROL_EXISTS")
                db = cls._connect(temporary, policy)
                source._bounded_backup(db)
                store = cls(path, policy, lock, db, fault)
                store._validate()
                with store._transaction("restore", faults=False):
                    if store._control()["revision"] == _MAX:
                        _fail("CONTROL_CAPACITY")
                    if db.execute("PRAGMA user_version").fetchone()[0] == 1:
                        db.execute(_RECOVERY_SQL)
                        db.execute("PRAGMA user_version=2")
                    record = {"schema": "fleet.control-recovery/1", "anchor": anchor,
                              "anchor_wall_ms": source._control()["last_wall_ms"],
                              "phase": "FENCED", "coordination_sha256": None,
                              "control_commit_revision": None, "ready_revision": None}
                    db.execute("INSERT OR REPLACE INTO recovery VALUES (1,?)", (_json(record),))
                    db.execute("UPDATE control SET schema=?,status='RECONCILIATION_REQUIRED',revision=revision+1 WHERE singleton=1", (RECOVERY_SCHEMA,))
                    store._inject("restore:before_commit")
                store._validate()
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.close()
                db = None
                os.replace(temporary, path)
                published = True
                db = cls._connect(path, policy)
                store = cls(path, policy, lock, db, fault)
                store._validate()
                store._inject("restore:after_commit")
                return store
            except GatewayControlError:
                cls._dispose(db, lock)
                raise
            except (sqlite3.Error, OSError, ValueError, OverflowError):
                cls._dispose(db, lock)
                _fail("CONTROL_COMMIT_UNCERTAIN" if published else "CONTROL_STORAGE_FAILED")
            except BaseException:
                cls._dispose(db, lock)
                raise
            finally:
                for suffix in ("", "-wal", "-shm"):
                    try:
                        Path(str(temporary) + suffix).unlink(missing_ok=True)
                    except OSError:
                        pass
