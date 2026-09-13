from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jobs import JobStore
from .revisions import RevisionManager
from .workspace import WorkspaceManager

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_REVISION_ID_RE = re.compile(r"^REV-[0-9]{6}$")
_DECISION_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_PHASES = {
    "IDLE", "SCAN", "RRI", "SPECIFY", "DECIDE", "CONTRACT", "PLAN",
    "BUILD", "VERIFY", "EVIDENCE", "RETRO",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.vibemql5-{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> str:
    data = _canonical_json_bytes(payload)
    _atomic_write_bytes(path, data)
    return _sha256_bytes(data)


class _ProjectLock:
    def __init__(self, path: Path, timeout_seconds: float = 3.0, stale_seconds: float = 30.0):
        self.path = path
        self.timeout_seconds = float(timeout_seconds)
        self.stale_seconds = float(stale_seconds)
        self.acquired = False

    def __enter__(self):
        deadline = time.monotonic() + self.timeout_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    payload = json.dumps({"pid": os.getpid(), "created_at_utc": _utc_now()}).encode("utf-8")
                    os.write(fd, payload)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                    if age > self.stale_seconds:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError("PROJECT_SESSION_BUSY: concurrent session mutation in progress")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.acquired:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


class ProjectSessionManager:
    """Durable project-development context with immutable revisions and CAS updates.

    The manager deliberately stores references/metadata only. It never copies EA source,
    credentials, account data, or raw tester reports into project-session state.
    """

    schema_version = "1.0"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.state_root = (self.root / "state" / "project-sessions").resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.workspace = WorkspaceManager(self.root)
        self.revisions = RevisionManager(self.root)
        self.jobs = JobStore(self.root)

    @staticmethod
    def _validate_project_id(project_id: str) -> str:
        project_id = str(project_id or "").strip()
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("Invalid project_id; use 1-64 letters, digits, dot, underscore or hyphen")
        return project_id

    @staticmethod
    def _validate_phase(phase: str) -> str:
        value = str(phase or "IDLE").strip().upper()
        if value not in _PHASES:
            raise ValueError(f"Invalid phase: {value}")
        return value

    @staticmethod
    def _validate_goal(goal: str) -> str:
        value = str(goal or "").strip()
        if len(value) > 500:
            raise ValueError("active_goal exceeds 500 characters")
        return value

    @staticmethod
    def _validate_decisions(refs: list[str] | None) -> list[str]:
        if refs is None:
            return []
        if len(refs) > 50:
            raise ValueError("decision_refs exceeds 50 entries")
        out: list[str] = []
        for raw in refs:
            ref = str(raw or "").strip()
            if not _DECISION_REF_RE.fullmatch(ref):
                raise ValueError(f"Invalid decision reference: {ref!r}")
            if ref not in out:
                out.append(ref)
        return out

    def _project_dir(self, project_id: str) -> Path:
        pid = self._validate_project_id(project_id)
        p = (self.state_root / pid).resolve()
        if p.parent != self.state_root:
            raise ValueError("Project session path escapes state root")
        return p

    def _revision_path(self, project_id: str, revision_id: str) -> Path:
        if not _REVISION_ID_RE.fullmatch(str(revision_id or "")):
            raise ValueError("Invalid revision_id")
        return self._project_dir(project_id) / "revisions" / f"{revision_id}.json"

    def _pointer_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "current.json"

    def _lock_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / ".session.lock"

    def _load_pointer(self, project_id: str) -> dict[str, Any]:
        p = self._pointer_path(project_id)
        if not p.is_file():
            raise FileNotFoundError(f"PROJECT_SESSION_NOT_FOUND: {project_id}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schema_version") != self.schema_version or data.get("project_id") != project_id:
            raise ValueError("PROJECT_SESSION_POINTER_INTEGRITY_FAILURE")
        return data

    def _load_revision(self, project_id: str, revision_id: str, expected_sha256: str = "") -> tuple[dict[str, Any], str]:
        p = self._revision_path(project_id, revision_id)
        if not p.is_file():
            raise FileNotFoundError(f"PROJECT_SESSION_REVISION_NOT_FOUND: {revision_id}")
        raw = p.read_bytes()
        actual_sha = _sha256_bytes(raw)
        if expected_sha256 and actual_sha != str(expected_sha256).lower():
            raise ValueError("PROJECT_SESSION_REVISION_INTEGRITY_FAILURE")
        data = json.loads(raw.decode("utf-8"))
        if data.get("schema_version") != self.schema_version:
            raise ValueError("PROJECT_SESSION_SCHEMA_MISMATCH")
        if data.get("project_id") != project_id or data.get("revision_id") != revision_id:
            raise ValueError("PROJECT_SESSION_REVISION_METADATA_MISMATCH")
        return data, actual_sha

    def _load_current(self, project_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        pid = self._validate_project_id(project_id)
        pointer = self._load_pointer(pid)
        revision, actual_sha = self._load_revision(pid, pointer["revision_id"], pointer.get("revision_sha256", ""))
        if actual_sha != pointer.get("revision_sha256"):
            raise ValueError("PROJECT_SESSION_REVISION_INTEGRITY_FAILURE")
        return revision, pointer

    def _job_snapshot(self, job_id: str) -> dict[str, Any]:
        if not job_id:
            return {"job_id": "", "exists": False}
        if any(x in job_id for x in ("/", "\\", "..")):
            return {"job_id": job_id, "exists": False}
        runs_root = (self.root / "runs").resolve()
        job_path = (runs_root / job_id / "job.json").resolve()
        try:
            job_path.relative_to(runs_root)
        except ValueError:
            return {"job_id": job_id, "exists": False}
        if not job_path.is_file():
            return {"job_id": job_id, "exists": False}
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except Exception:
            return {"job_id": job_id, "exists": False}
        result_path = runs_root / job_id / "result.json"
        result_status = "NOT_READY"
        if result_path.is_file():
            try:
                result_status = str(json.loads(result_path.read_text(encoding="utf-8")).get("status", "UNKNOWN"))
            except Exception:
                result_status = "INVALID"
        return {
            "job_id": job_id,
            "exists": True,
            "state": str(job.get("state", "UNKNOWN")),
            "result_status": result_status,
            "updated_at": job.get("updated_at", ""),
        }

    def _validate_job_ref(self, job_id: str, field_name: str) -> str:
        value = str(job_id or "").strip()
        if not value:
            return ""
        snap = self._job_snapshot(value)
        if not snap["exists"]:
            raise ValueError(f"{field_name.upper()}_NOT_FOUND: {value}")
        return value

    def _validate_checkpoint_ref(self, workspace: str, ea: str, checkpoint_id: str) -> str:
        value = str(checkpoint_id or "").strip()
        if not value:
            return ""
        matches = [x for x in self.revisions.list_checkpoints(workspace, ea) if x.get("checkpoint_id") == value]
        if not matches:
            raise ValueError(f"CHECKPOINT_NOT_FOUND_OR_PATH_MISMATCH: {value}")
        return value

    def _source_snapshot(self, workspace: str, ea: str) -> dict[str, Any]:
        # WorkspaceManager/RevisionManager provide path allow-listing and byte-accurate hash.
        return self.revisions.source_hash(workspace, ea)

    @staticmethod
    def _validate_operation_id(operation_id: str) -> str:
        value = str(operation_id or "").strip()
        if value and not _OPERATION_ID_RE.fullmatch(value):
            raise ValueError("Invalid session update operation_id")
        return value

    def _find_operation_revision(self, project_id: str, operation_id: str) -> tuple[dict[str, Any], str] | None:
        if not operation_id:
            return None
        revisions = self._project_dir(project_id) / "revisions"
        if not revisions.is_dir():
            return None
        for path in sorted(revisions.glob("REV-*.json")):
            try:
                raw = path.read_bytes()
                sha = _sha256_bytes(raw)
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if data.get("session_update_operation_id") != operation_id:
                continue
            if data.get("project_id") != project_id or data.get("revision_id") != path.stem:
                raise ValueError("PROJECT_SESSION_OPERATION_REVISION_INTEGRITY_FAILURE")
            return data, sha
        return None

    def _repair_pointer_to_revision(self, project_id: str, revision: dict[str, Any], revision_sha: str) -> None:
        pointer = {
            "schema_version": self.schema_version,
            "project_id": project_id,
            "revision_id": revision["revision_id"],
            "revision_sha256": revision_sha,
            "updated_at_utc": revision["updated_at_utc"],
        }
        _atomic_write_json(self._pointer_path(project_id), pointer)

    def _write_revision(self, project_id: str, payload: dict[str, Any]) -> tuple[str, str]:
        revision_id = str(payload["revision_id"])
        revision_path = self._revision_path(project_id, revision_id)
        if revision_path.exists():
            raise FileExistsError(f"PROJECT_SESSION_REVISION_ALREADY_EXISTS: {revision_id}")
        revision_sha = _atomic_write_json(revision_path, payload)
        pointer = {
            "schema_version": self.schema_version,
            "project_id": project_id,
            "revision_id": revision_id,
            "revision_sha256": revision_sha,
            "updated_at_utc": payload["updated_at_utc"],
        }
        _atomic_write_json(self._pointer_path(project_id), pointer)
        return revision_id, revision_sha

    def create(
        self,
        project_id: str,
        workspace: str,
        ea: str,
        active_goal: str = "",
        decision_refs: list[str] | None = None,
        phase: str = "IDLE",
        checkpoint_id: str = "",
        baseline_job_id: str = "",
        last_job_id: str = "",
    ) -> dict[str, Any]:
        pid = self._validate_project_id(project_id)
        with _ProjectLock(self._lock_path(pid)):
            if self._pointer_path(pid).exists():
                raise FileExistsError(f"PROJECT_SESSION_ALREADY_EXISTS: {pid}")
            source = self._source_snapshot(workspace, ea)
            checkpoint = self._validate_checkpoint_ref(workspace, ea, checkpoint_id)
            baseline = self._validate_job_ref(baseline_job_id, "baseline_job_id")
            last_job = self._validate_job_ref(last_job_id, "last_job_id")
            now = _utc_now()
            payload = {
                "schema_version": self.schema_version,
                "project_id": pid,
                "revision_id": "REV-000001",
                "revision_number": 1,
                "previous_revision_sha256": "",
                "workspace": workspace,
                "ea": ea.replace("\\", "/"),
                "source_sha256": source["sha256"],
                "source_bytes": source["bytes"],
                "checkpoint_id": checkpoint,
                "baseline_job_id": baseline,
                "last_job_id": last_job,
                "decision_refs": self._validate_decisions(decision_refs),
                "active_goal": self._validate_goal(active_goal),
                "phase": self._validate_phase(phase),
                "created_at_utc": now,
                "updated_at_utc": now,
            }
            _, sha = self._write_revision(pid, payload)
            return {**payload, "revision_sha256": sha}

    def get(self, project_id: str) -> dict[str, Any]:
        session, pointer = self._load_current(project_id)
        return {**session, "revision_sha256": pointer["revision_sha256"]}

    def list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.state_root.exists():
            return out
        for child in sorted(self.state_root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or not _PROJECT_ID_RE.fullmatch(child.name):
                continue
            try:
                current = self.get(child.name)
                out.append({
                    "project_id": current["project_id"],
                    "revision_id": current["revision_id"],
                    "workspace": current["workspace"],
                    "ea": current["ea"],
                    "phase": current["phase"],
                    "active_goal": current["active_goal"],
                    "updated_at_utc": current["updated_at_utc"],
                    "integrity": "VERIFIED",
                })
            except Exception as exc:
                out.append({"project_id": child.name, "integrity": "INVALID", "error": str(exc)})
        return out

    def update(
        self,
        project_id: str,
        expected_revision: str,
        *,
        active_goal: str | None = None,
        decision_refs: list[str] | None = None,
        phase: str | None = None,
        checkpoint_id: str | None = None,
        baseline_job_id: str | None = None,
        last_job_id: str | None = None,
        operation_id: str = "",
        expected_revision_sha256: str = "",
    ) -> dict[str, Any]:
        pid = self._validate_project_id(project_id)
        expected = str(expected_revision or "").strip()
        if not _REVISION_ID_RE.fullmatch(expected):
            raise ValueError("expected_revision must be REV-######")
        operation = self._validate_operation_id(operation_id)
        expected_sha = str(expected_revision_sha256 or "").strip().lower()
        if expected_sha and not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError("expected_revision_sha256 must be a SHA-256 hex digest")
        request_sha = ""
        if operation:
            request_sha = _sha256_bytes(_canonical_json_bytes({
                "project_id": pid,
                "expected_revision": expected,
                "active_goal": active_goal,
                "decision_refs": decision_refs,
                "phase": phase,
                "checkpoint_id": checkpoint_id,
                "baseline_job_id": baseline_job_id,
                "last_job_id": last_job_id,
            }))

        with _ProjectLock(self._lock_path(pid)):
            existing = self._find_operation_revision(pid, operation) if operation else None
            if existing:
                revision, sha = existing
                if revision.get("session_update_expected_revision_id") != expected:
                    raise ValueError("PROJECT_SESSION_OPERATION_CONFLICT: expected revision mismatch")
                recorded_expected_sha = str(revision.get("session_update_expected_revision_sha256") or "").lower()
                if expected_sha and recorded_expected_sha != expected_sha:
                    raise ValueError("PROJECT_SESSION_OPERATION_CONFLICT: expected revision SHA mismatch")
                recorded_request_sha = str(revision.get("session_update_request_sha256") or "").lower()
                if recorded_request_sha and recorded_request_sha != request_sha:
                    raise ValueError("PROJECT_SESSION_OPERATION_CONFLICT: same operation_id has a different request")
                pointer = self._load_pointer(pid)
                if pointer.get("revision_id") == revision["revision_id"]:
                    if pointer.get("revision_sha256") != sha:
                        raise ValueError("PROJECT_SESSION_REVISION_INTEGRITY_FAILURE")
                elif pointer.get("revision_id") == expected:
                    self._repair_pointer_to_revision(pid, revision, sha)
                else:
                    raise ValueError(
                        f"PROJECT_SESSION_VERSION_CONFLICT: correlated operation exists at {revision['revision_id']} "
                        f"but current is {pointer.get('revision_id')}"
                    )
                return {**revision, "revision_sha256": sha, "idempotent_recovered": True}

            current, pointer = self._load_current(pid)
            if current["revision_id"] != expected:
                raise ValueError(
                    f"PROJECT_SESSION_VERSION_CONFLICT: expected {expected}, current {current['revision_id']}"
                )
            if expected_sha and pointer["revision_sha256"].lower() != expected_sha:
                raise ValueError("PROJECT_SESSION_VERSION_CONFLICT: expected revision SHA does not match current pointer")
            number = int(current["revision_number"]) + 1
            source = self._source_snapshot(current["workspace"], current["ea"])
            new_checkpoint = current["checkpoint_id"] if checkpoint_id is None else self._validate_checkpoint_ref(
                current["workspace"], current["ea"], checkpoint_id
            )
            new_baseline = current["baseline_job_id"] if baseline_job_id is None else self._validate_job_ref(
                baseline_job_id, "baseline_job_id"
            )
            new_last_job = current["last_job_id"] if last_job_id is None else self._validate_job_ref(
                last_job_id, "last_job_id"
            )
            now = _utc_now()
            payload = {
                **current,
                "revision_id": f"REV-{number:06d}",
                "revision_number": number,
                "previous_revision_sha256": pointer["revision_sha256"],
                "source_sha256": source["sha256"],
                "source_bytes": source["bytes"],
                "checkpoint_id": new_checkpoint,
                "baseline_job_id": new_baseline,
                "last_job_id": new_last_job,
                "active_goal": current["active_goal"] if active_goal is None else self._validate_goal(active_goal),
                "decision_refs": current["decision_refs"] if decision_refs is None else self._validate_decisions(decision_refs),
                "phase": current["phase"] if phase is None else self._validate_phase(phase),
                "updated_at_utc": now,
            }
            if operation:
                payload["session_update_operation_id"] = operation
                payload["session_update_expected_revision_id"] = expected
                payload["session_update_expected_revision_sha256"] = pointer["revision_sha256"]
                payload["session_update_request_sha256"] = request_sha
            _, sha = self._write_revision(pid, payload)
            return {**payload, "revision_sha256": sha, "idempotent_recovered": False}

    def resume(self, project_id: str) -> dict[str, Any]:
        session, pointer = self._load_current(project_id)
        stale: list[str] = []

        try:
            source = self._source_snapshot(session["workspace"], session["ea"])
            source_match = source["sha256"] == session["source_sha256"] and source["bytes"] == session["source_bytes"]
            if not source_match:
                stale.append("SOURCE_CHANGED_SINCE_SESSION_REVISION")
        except Exception as exc:
            source = {"exists": False, "error": str(exc)}
            source_match = False
            stale.append("SOURCE_MISSING_OR_UNREADABLE")

        checkpoint = {"checkpoint_id": session["checkpoint_id"], "exists": False}
        if session["checkpoint_id"]:
            matches = [
                x for x in self.revisions.list_checkpoints(session["workspace"], session["ea"])
                if x.get("checkpoint_id") == session["checkpoint_id"]
            ]
            checkpoint = {"checkpoint_id": session["checkpoint_id"], "exists": bool(matches)}
            if matches:
                checkpoint.update({
                    "sha256": matches[0].get("sha256", ""),
                    "bytes": matches[0].get("bytes", 0),
                    "created_at": matches[0].get("created_at", ""),
                })
            else:
                stale.append("CHECKPOINT_REFERENCE_MISSING")

        baseline = self._job_snapshot(session["baseline_job_id"])
        if session["baseline_job_id"] and not baseline["exists"]:
            stale.append("BASELINE_JOB_REFERENCE_MISSING")
        last_job = self._job_snapshot(session["last_job_id"])
        if session["last_job_id"] and not last_job["exists"]:
            stale.append("LAST_JOB_REFERENCE_MISSING")

        return {
            "project_id": session["project_id"],
            "revision_id": session["revision_id"],
            "revision_sha256": pointer["revision_sha256"],
            "integrity": "VERIFIED",
            "resume_safe": not stale,
            "stale_reasons": stale,
            "session": session,
            "source": {**source, "match_session_revision": source_match},
            "checkpoint": checkpoint,
            "baseline_job": baseline,
            "last_job": last_job,
        }
