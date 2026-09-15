from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .provenance import load_bridge_provenance

SCHEMA_VERSION = "1.0"
BUILD_REQUIRED = "TIP-015B"
OWNER_DECISION_REF = "DEC-TIP015B-001"
HARD_EXIT_CODE = 97

FAULT_POINTS = {
    "ACCEPT_AFTER_SESSION_UPDATE",
    "TEST_AFTER_PREPARED",
    "TEST_AFTER_RESERVED",
    "ROLLBACK_AFTER_INTENT",
    "CANCEL_AFTER_INTENT",
}

_ITERATION_ID_RE = re.compile(r"^IT-[0-9]{8}-[0-9]{6}-[A-F0-9]{8}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_write(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return _sha(raw)


def _atomic_json(path: Path, value: dict[str, Any]) -> str:
    return _atomic_write(path, _canonical(value))


def _terminate_process(exit_code: int) -> None:
    """Abruptly terminate the current bridge process.

    Unit tests monkeypatch this function. Runtime arming is local-only and one-shot,
    so no MCP surface can invoke the hard exit directly.
    """
    os._exit(exit_code)


class TIP015BFaultInjector:
    """Local-only, one-shot deterministic crash injector for TIP-015B verification.

    Safety properties:
    - no MCP tool is added;
    - arming requires the exact TIP-015B build by default;
    - a point is bound to one exact iteration id;
    - arming expires quickly and is consumed before the hard exit;
    - a durable receipt is written before process termination, preventing crash loops.
    """

    def __init__(self, root: Path, *, require_build: bool = True):
        self.root = Path(root).resolve()
        self.require_build = bool(require_build)
        self.state_root = self.root / "state" / "tip015b-fault-injection"
        self.armed_path = self.state_root / "armed.json"
        self.receipts_root = self.state_root / "receipts"

    @staticmethod
    def _point(value: str) -> str:
        point = str(value or "").strip().upper()
        if point not in FAULT_POINTS:
            raise ValueError(f"TIP015B_INVALID_FAULT_POINT: {point}")
        return point

    @staticmethod
    def _iteration_id(value: str) -> str:
        iteration_id = str(value or "").strip().upper()
        if not _ITERATION_ID_RE.fullmatch(iteration_id):
            raise ValueError("TIP015B_INVALID_ITERATION_ID")
        return iteration_id

    def _assert_build(self) -> dict[str, Any]:
        if not self.require_build:
            return {"bridge_build": BUILD_REQUIRED, "bridge_version": "TEST"}
        provenance = load_bridge_provenance(self.root)
        if provenance.get("bridge_build") != BUILD_REQUIRED:
            raise RuntimeError(
                f"TIP015B_BUILD_REQUIRED: expected {BUILD_REQUIRED}, got {provenance.get('bridge_build')}"
            )
        return provenance

    def arm(
        self,
        point: str,
        iteration_id: str,
        *,
        ttl_seconds: int = 300,
        armed_from_revision: str = "",
        armed_from_revision_sha256: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        provenance = self._assert_build()
        point = self._point(point)
        iteration_id = self._iteration_id(iteration_id)
        ttl = max(30, min(int(ttl_seconds), 900))
        revision_sha = str(armed_from_revision_sha256 or "").strip().lower()
        if revision_sha and not _SHA_RE.fullmatch(revision_sha):
            raise ValueError("TIP015B_INVALID_ARM_REVISION_SHA256")
        now = _utc_now()
        nonce = uuid.uuid4().hex
        payload = {
            "schema_version": SCHEMA_VERSION,
            "tip": "TIP-015B",
            "owner_decision_ref": OWNER_DECISION_REF,
            "bridge_build": provenance.get("bridge_build", BUILD_REQUIRED),
            "bridge_version": provenance.get("bridge_version", ""),
            "status": "ARMED",
            "point": point,
            "iteration_id": iteration_id,
            "nonce": nonce,
            "armed_at_utc": _iso(now),
            "expires_at_utc": _iso(now + timedelta(seconds=ttl)),
            "armed_from_revision": str(armed_from_revision or ""),
            "armed_from_revision_sha256": revision_sha,
            "note": str(note or "")[:500],
            "arming_pid": os.getpid(),
        }
        sha = _atomic_json(self.armed_path, payload)
        return {**payload, "record_sha256": sha}

    def status(self) -> dict[str, Any]:
        if not self.armed_path.is_file():
            return {"schema_version": SCHEMA_VERSION, "tip": "TIP-015B", "status": "DISARMED"}
        raw = self.armed_path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        return {**data, "record_sha256": _sha(raw)}

    def clear(self) -> dict[str, Any]:
        prior = self.status()
        self.armed_path.unlink(missing_ok=True)
        return {"schema_version": SCHEMA_VERSION, "tip": "TIP-015B", "status": "DISARMED", "previous": prior}

    def _expired(self, record: dict[str, Any]) -> bool:
        raw = str(record.get("expires_at_utc") or "")
        try:
            expires = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return True
        return _utc_now() >= expires.astimezone(timezone.utc)

    def hit(self, point: str, iteration_id: str, *, context: dict[str, Any] | None = None) -> bool:
        """Trigger a matching armed failpoint, consuming it before hard exit.

        Returns False when no matching armed point exists. On a true match this
        function does not return at runtime because it terminates the process.
        """
        point = self._point(point)
        iteration_id = self._iteration_id(iteration_id)
        if not self.armed_path.is_file():
            return False
        try:
            raw = self.armed_path.read_bytes()
            record = json.loads(raw.decode("utf-8"))
        except Exception:
            return False
        if record.get("schema_version") != SCHEMA_VERSION or record.get("tip") != "TIP-015B":
            return False
        if record.get("status") != "ARMED":
            return False
        if record.get("point") != point or record.get("iteration_id") != iteration_id:
            return False
        if self._expired(record):
            expired = {**record, "status": "EXPIRED", "expired_observed_at_utc": _iso()}
            _atomic_json(self.armed_path, expired)
            return False

        nonce = str(record.get("nonce") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            return False
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "tip": "TIP-015B",
            "owner_decision_ref": OWNER_DECISION_REF,
            "status": "TRIGGERED",
            "point": point,
            "iteration_id": iteration_id,
            "nonce": nonce,
            "triggered_at_utc": _iso(),
            "trigger_pid": os.getpid(),
            "exit_code": HARD_EXIT_CODE,
            "context": context or {},
        }
        receipt_path = self.receipts_root / f"{nonce}.json"
        receipt_sha = _atomic_json(receipt_path, receipt)
        consumed = {
            **record,
            "status": "TRIGGERED",
            "triggered_at_utc": receipt["triggered_at_utc"],
            "trigger_pid": os.getpid(),
            "receipt": str(receipt_path.relative_to(self.root)).replace("\\", "/"),
            "receipt_sha256": receipt_sha,
        }
        _atomic_json(self.armed_path, consumed)
        _terminate_process(HARD_EXIT_CODE)
        return True
