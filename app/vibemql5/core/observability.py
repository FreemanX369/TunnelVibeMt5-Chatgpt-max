from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_ITERATION_ID_RE = re.compile(r"^IT-[0-9]{8}-[0-9]{6}-[A-F0-9]{8}$")
_ITERATION_REV_RE = re.compile(r"^IR-[0-9]{6}$")
_JOB_ID_RE = re.compile(r"^BT-[0-9]{8}-[0-9]{6}-[A-F0-9]{6}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FAULT_POINTS = {"ACCEPT_AFTER_SESSION_UPDATE", "TEST_AFTER_PREPARED", "TEST_AFTER_RESERVED", "ROLLBACK_AFTER_INTENT", "CANCEL_AFTER_INTENT"}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _limit(value: int) -> int:
    limit = int(value)
    if limit < 1 or limit > 1000:
        raise ValueError("history limit must be between 1 and 1000")
    return limit


def _read_json(path: Path, error_code: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{error_code}: {path.name}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{error_code}: {path.name}")
    return data, raw


class ObservabilityManager:
    """Read-only, direct durable-history inspection for TIP-015C."""

    schema_version = "1.0"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.iteration_root = (self.root / "state" / "iterations").resolve()
        self.receipt_root = (self.root / "state" / "tip015b-fault-injection" / "receipts").resolve()
        self.runs_root = (self.root / "runs").resolve()

    def iteration_history(self, iteration_id: str, limit: int = 100, newest_first: bool = True) -> dict[str, Any]:
        iteration_id = str(iteration_id or "").strip().upper()
        if not _ITERATION_ID_RE.fullmatch(iteration_id):
            raise ValueError("Invalid iteration_id")
        limit = _limit(limit)
        iteration_dir = (self.iteration_root / iteration_id).resolve()
        if iteration_dir.parent != self.iteration_root:
            raise ValueError("ITERATION_HISTORY_PATH_ESCAPE")
        pointer_path = iteration_dir / "current.json"
        revisions_dir = iteration_dir / "revisions"
        if not pointer_path.is_file() or not revisions_dir.is_dir():
            raise FileNotFoundError(f"ITERATION_NOT_FOUND: {iteration_id}")
        pointer, pointer_raw = _read_json(pointer_path, "ITERATION_POINTER_INTEGRITY_FAILURE")
        if pointer.get("schema_version") != self.schema_version or pointer.get("iteration_id") != iteration_id or not _ITERATION_REV_RE.fullmatch(str(pointer.get("revision_id") or "")) or not _SHA_RE.fullmatch(str(pointer.get("revision_sha256") or "")):
            raise ValueError("ITERATION_POINTER_INTEGRITY_FAILURE")
        files = sorted(revisions_dir.glob("IR-*.json"), key=lambda p: p.name)
        if not files:
            raise ValueError("ITERATION_HISTORY_EMPTY")
        chronological: list[dict[str, Any]] = []
        previous_sha = ""
        expected_number = 1
        pointer_index = -1
        for path in files:
            revision_id = path.stem
            if not _ITERATION_REV_RE.fullmatch(revision_id):
                raise ValueError(f"ITERATION_HISTORY_INVALID_REVISION_NAME: {path.name}")
            number = int(revision_id.split("-")[1])
            if number != expected_number:
                raise ValueError(f"ITERATION_HISTORY_GAP: expected IR-{expected_number:06d}, got {revision_id}")
            data, raw = _read_json(path, "ITERATION_HISTORY_REVISION_UNREADABLE")
            actual_sha = _sha256(raw)
            if data.get("schema_version") != self.schema_version or data.get("iteration_id") != iteration_id or data.get("iteration_revision") != revision_id or int(data.get("iteration_revision_number") or 0) != number:
                raise ValueError(f"ITERATION_HISTORY_METADATA_MISMATCH: {revision_id}")
            expected_previous = "" if number == 1 else previous_sha
            if str(data.get("previous_iteration_revision_sha256") or "") != expected_previous:
                raise ValueError(f"ITERATION_HISTORY_CHAIN_FAILURE: {revision_id}")
            record = {**data, "iteration_revision_sha256": actual_sha}
            chronological.append(record)
            if revision_id == pointer["revision_id"]:
                pointer_index = len(chronological) - 1
                if actual_sha != pointer["revision_sha256"]:
                    raise ValueError("ITERATION_POINTER_INTEGRITY_FAILURE")
            previous_sha = actual_sha
            expected_number += 1
        if pointer_index < 0:
            raise ValueError("ITERATION_HISTORY_POINTER_REVISION_MISSING")
        unpointed = len(chronological) - pointer_index - 1
        pointer_status = "CURRENT" if unpointed == 0 else "LAGGING_DURABLE_REVISIONS"
        ordered = list(reversed(chronological)) if newest_first else chronological
        selected = ordered[:limit]
        return {"schema_version": self.schema_version, "iteration_id": iteration_id, "source": "direct_durable_read", "newest_first": bool(newest_first), "limit": limit, "count_total": len(chronological), "count_returned": len(selected), "current_revision": pointer["revision_id"], "current_revision_sha256": pointer["revision_sha256"], "current_pointer_sha256": _sha256(pointer_raw), "pointer_status": pointer_status, "unpointed_revision_count": unpointed, "history": selected}

    def fault_receipts(self, limit: int = 100, newest_first: bool = True) -> dict[str, Any]:
        limit = _limit(limit)
        if not self.receipt_root.exists():
            return {"schema_version": self.schema_version, "source": "direct_durable_read", "newest_first": bool(newest_first), "limit": limit, "count_total": 0, "count_returned": 0, "receipts": []}
        if not self.receipt_root.is_dir():
            raise ValueError("FAULT_RECEIPT_ROOT_INVALID")
        records: list[dict[str, Any]] = []
        for path in sorted(self.receipt_root.glob("*.json"), key=lambda p: p.name):
            nonce = path.stem
            if not _NONCE_RE.fullmatch(nonce):
                raise ValueError(f"FAULT_RECEIPT_INVALID_NAME: {path.name}")
            data, raw = _read_json(path, "FAULT_RECEIPT_UNREADABLE")
            if data.get("schema_version") != "1.0" or data.get("tip") != "TIP-015B" or data.get("status") != "TRIGGERED" or data.get("nonce") != nonce or str(data.get("point") or "") not in _FAULT_POINTS or not _ITERATION_ID_RE.fullmatch(str(data.get("iteration_id") or "")) or int(data.get("exit_code") or 0) != 97:
                raise ValueError(f"FAULT_RECEIPT_METADATA_MISMATCH: {path.name}")
            records.append({**data, "receipt_sha256": _sha256(raw)})
        records.sort(key=lambda r: (str(r.get("triggered_at_utc") or ""), str(r.get("nonce") or "")), reverse=bool(newest_first))
        selected = records[:limit]
        return {"schema_version": self.schema_version, "source": "direct_durable_read", "newest_first": bool(newest_first), "limit": limit, "count_total": len(records), "count_returned": len(selected), "receipts": selected}

    def job_history(self, limit: int = 100, newest_first: bool = True, workspace: str = "", state: str = "") -> dict[str, Any]:
        limit = _limit(limit)
        workspace_filter = str(workspace or "").strip()
        state_filter = str(state or "").strip().upper()
        if not self.runs_root.exists():
            records: list[dict[str, Any]] = []
        elif not self.runs_root.is_dir():
            raise ValueError("JOB_HISTORY_ROOT_INVALID")
        else:
            records = []
            for path in sorted(self.runs_root.glob("*/job.json"), key=lambda p: p.parent.name):
                directory_job_id = path.parent.name
                if not _JOB_ID_RE.fullmatch(directory_job_id):
                    raise ValueError(f"JOB_HISTORY_INVALID_DIRECTORY: {directory_job_id}")
                data, raw = _read_json(path, "JOB_HISTORY_UNREADABLE")
                if data.get("job_id") != directory_job_id:
                    raise ValueError(f"JOB_HISTORY_METADATA_MISMATCH: {directory_job_id}")
                request = data.get("request")
                if not isinstance(request, dict):
                    raise ValueError(f"JOB_HISTORY_REQUEST_INVALID: {directory_job_id}")
                if workspace_filter and str(request.get("workspace") or "") != workspace_filter:
                    continue
                if state_filter and str(data.get("state") or "").upper() != state_filter:
                    continue
                records.append({"job_id": directory_job_id, "state": data.get("state"), "created_at": data.get("created_at"), "updated_at": data.get("updated_at"), "operation_id": data.get("operation_id", ""), "request_hash": data.get("request_hash", ""), "retry_count": data.get("retry_count", 0), "cancel_requested": bool(data.get("cancel_requested", False)), "spawn_requested": bool(data.get("spawn_requested", False)), "request": request, "job_record_sha256": _sha256(raw)})
        records.sort(key=lambda r: (str(r.get("created_at") or ""), str(r.get("job_id") or "")), reverse=bool(newest_first))
        selected = records[:limit]
        return {"schema_version": self.schema_version, "source": "direct_durable_read", "newest_first": bool(newest_first), "limit": limit, "workspace_filter": workspace_filter, "state_filter": state_filter, "count_total": len(records), "count_returned": len(selected), "jobs": selected}
