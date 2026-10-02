"""Fixture-only durable authority. No runtime entry point imports this module."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from vibemql5.core.concurrency import _QueuedFileLease, acquire_native_execution
from vibemql5.core.jobs import _exclusive_file_lock


class RecoveryRequired(RuntimeError):
    pass


def atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class FixtureAuthority:
    def __init__(self, root):
        self.root = Path(root)
        self.state = self.root / "state" / "tip057rq"
        self.intent_path = self.state / "intent.json"
        self.generation_path = self.state / "generation.json"
        self.guard = self.state / ".fixture-authority.lock"

    def read(self):
        try:
            ledger = json.loads(self.generation_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            ledger = None
        if ledger is not None and (not isinstance(ledger, dict) or ledger.get("status") not in {"ACTIVE", "CLOSED"}
                                   or type(ledger.get("generation")) is not int or ledger["generation"] <= 0):
            raise RecoveryRequired("INVALID_FIXTURE_LEDGER")
        try:
            value = json.loads(self.intent_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if ledger is not None and ledger["status"] == "ACTIVE":
                raise RecoveryRequired("LOST_ACTIVE_INTENT")
            return None
        def process_ref(ref):
            return (isinstance(ref, dict) and set(ref) == {"pid", "creation_100ns", "image"}
                    and type(ref["pid"]) is int and ref["pid"] > 0
                    and type(ref["creation_100ns"]) is int and ref["creation_100ns"] > 0
                    and isinstance(ref["image"], str) and os.path.isabs(ref["image"]))
        if (not isinstance(value, dict) or value.get("schema") != "tip057rq.intent/1"
                or ledger is None or ledger["status"] != "ACTIVE"
                or value.get("generation") != ledger["generation"]
                or not isinstance(value.get("lease_token"), str) or not value["lease_token"].strip()
                or value.get("lease_token") != ledger.get("lease_token")
                or not process_ref(value.get("parent"))
                or (value.get("worker") is not None and not process_ref(value["worker"]))
                or value.get("phase") not in {"ARMED_BEFORE_CREATE", "CREATE_ATTEMPT_COMMITTED", "BOUND_BEFORE_RESUME"}
                or value.get("descendants") not in {"UNRESOLVED", "NONE_FOR_FIXTURE_PATH"}):
            raise RecoveryRequired("INVALID_FIXTURE_INTENT")
        return value

    def _expected(self, expected):
        current = self.read()
        if current is None or any(current.get(key) != expected.get(key)
                                  for key in ("generation", "lease_token", "parent", "worker")):
            raise RecoveryRequired("STALE_FIXTURE_AUTHORITY")
        return current

    def arm(self, parent):
        with _exclusive_file_lock(self.guard, timeout_seconds=2):
            if self.read() is not None:
                raise RecoveryRequired("LIVE_RECOVERY_REQUIRED")
            lease = acquire_native_execution(self.root, "Q1-FIXTURE", kind="proof", wait_seconds=2)
            try:
                generation = 1
                if self.generation_path.exists():
                    generation += json.loads(self.generation_path.read_text(encoding="utf-8"))["generation"]
                atomic(self.generation_path, {"generation": generation, "status": "ACTIVE", "lease_token": lease.token})
                intent = {"schema": "tip057rq.intent/1", "generation": generation,
                          "lease_token": lease.token, "parent": parent, "worker": None,
                          "phase": "ARMED_BEFORE_CREATE", "descendants": "UNRESOLVED"}
                atomic(self.intent_path, intent)
                return lease, intent
            except BaseException:
                # No worker creation/observation has been attempted by this arm method.
                lease.release()
                if self.generation_path.exists():
                    atomic(self.generation_path, {"generation": generation, "status": "CLOSED"})
                raise

    def bind_worker(self, expected, worker, *, descendants="NONE_FOR_FIXTURE_PATH"):
        with _exclusive_file_lock(self.guard, timeout_seconds=2):
            current = self._expected(expected)
            if current["phase"] != "CREATE_ATTEMPT_COMMITTED" or current["worker"] is not None:
                raise RecoveryRequired("CREATE_PHASE_UNPROVEN")
            current.update(worker=worker, phase="BOUND_BEFORE_RESUME", descendants=descendants)
            atomic(self.intent_path, current)
            return current

    def begin_create(self, expected):
        with _exclusive_file_lock(self.guard, timeout_seconds=2):
            current = self._expected(expected)
            if current["worker"] is not None or current["phase"] != "ARMED_BEFORE_CREATE":
                raise RecoveryRequired("CREATE_PHASE_UNPROVEN")
            current["phase"] = "CREATE_ATTEMPT_COMMITTED"
            atomic(self.intent_path, current)
            return current

    def descendants_proven(self, expected):
        with _exclusive_file_lock(self.guard, timeout_seconds=2):
            current = self._expected(expected)
            current["descendants"] = "NONE_FOR_FIXTURE_PATH"
            atomic(self.intent_path, current)
            return current

    def no_start_release(self, expected):
        with _exclusive_file_lock(self.guard, timeout_seconds=2):
            current = self._expected(expected)
            if current["worker"] is not None or current["phase"] != "ARMED_BEFORE_CREATE":
                raise RecoveryRequired("ATTEMPT_STATUS_UNPROVEN")
            self._release_native(current)
            atomic(self.generation_path, {"generation": current["generation"], "status": "CLOSED"})
            self.intent_path.unlink()
            return {"cleanup": "NOT_ATTEMPTED", "ownership": "RELEASED"}

    def reconcile(self, expected, process):
        with _exclusive_file_lock(self.guard, timeout_seconds=2):
            current = self._expected(expected)
            if current["descendants"] != "NONE_FOR_FIXTURE_PATH":
                raise RecoveryRequired("DESCENDANT_OUTCOME_UNRESOLVED")
            if current["worker"] is None or process.identity() != current["worker"]:
                raise RecoveryRequired("WORKER_CREATION_IDENTITY_MISMATCH")
            if not process.exited():
                raise RecoveryRequired("EXACT_WORKER_STILL_RUNNING")
            self._release_native(current)
            atomic(self.generation_path, {"generation": current["generation"], "status": "CLOSED"})
            self.intent_path.unlink()
            return {"cleanup": "PROVEN", "ownership": "RELEASED"}

    def _release_native(self, current):
        lock = self.root / "runs" / ".active.lock"
        try:
            token = json.loads(lock.read_text(encoding="utf-8"))["token"]
        except FileNotFoundError:
            token = None
        if token is not None and token != current["lease_token"]:
            raise RecoveryRequired("SUCCESSOR_NATIVE_OWNER")
        lease = _QueuedFileLease(self.root, namespace="native", operation_id="Q1-RECOVERY",
                                 kind="proof", actor=None, wait_seconds=2, lock_path=lock)
        lease.token = current["lease_token"]
        lease.release()


def outcome(primary=None, cleanup="PROVEN", *, expired=False, qualified=False):
    reason = "LIVE_CLEANUP_UNPROVEN" if cleanup == "UNPROVEN" else primary
    if reason is None and expired:
        reason = "LIVE_DEADLINE_EXCEEDED"
    return {"reason_code": reason,
            "primary_reason_code": primary if cleanup == "UNPROVEN" else None,
            "cleanup": cleanup, "expired": expired,
            "account": {"synthetic": True} if qualified and reason is None else None}
