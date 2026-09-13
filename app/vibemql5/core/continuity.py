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


_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_EVENT_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROJECTION_FIELDS = (
    "project_session_binding",
    "source_binding",
    "workflow",
    "requirements",
    "decisions",
    "constraints",
    "evidence_refs",
    "recovery",
    "runtime_authority",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.vibemql5-{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _write_json(path: Path, value: dict[str, Any]) -> str:
    raw = _json_bytes(value)
    _atomic_write(path, raw)
    return _sha256(raw)


def _write_immutable_json(path: Path, value: dict[str, Any]) -> str:
    raw = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError(f"CONTINUITY_IMMUTABLE_CONFLICT: {path.name}")
    return _sha256(raw)


class _ContinuityLock:
    def __init__(self, path: Path, timeout_seconds: float = 5.0, stale_seconds: float = 60.0):
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self.acquired = False

    def __enter__(self):
        deadline = time.monotonic() + self.timeout_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, _json_bytes({"pid": os.getpid(), "created_at_utc": _utc_now()}))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale_seconds:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError("CONTINUITY_BUSY")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.acquired:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


class ContinuityManager:
    """File-backed semantic project authority with immutable SHA-linked history."""

    schema_version = "1.0"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.state_root = (self.root / "state" / "continuity").resolve()

    @staticmethod
    def _project_id(value: str) -> str:
        project_id = str(value or "").strip()
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("Invalid project_id")
        return project_id

    @staticmethod
    def _operation_id(value: str) -> str:
        operation_id = str(value or "").strip()
        if not _OPERATION_ID_RE.fullmatch(operation_id):
            raise ValueError("operation_id is required and invalid")
        return operation_id

    @staticmethod
    def _expected_sha(value: str, *, allow_empty: bool) -> str:
        digest = str(value or "").strip().lower()
        if not digest and allow_empty:
            return ""
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("expected_manifest_sha256 must be a SHA-256 digest")
        return digest

    def _project_dir(self, project_id: str) -> Path:
        pid = self._project_id(project_id)
        path = (self.state_root / pid).resolve()
        if path.parent != self.state_root:
            raise ValueError("Continuity path escapes state root")
        return path

    def _pointer_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "current.json"

    def _manifest_path(self, project_id: str, revision: int) -> Path:
        return self._project_dir(project_id) / "revisions" / f"CM-{revision:06d}.json"

    def _event_path(self, project_id: str, seq: int) -> Path:
        return self._project_dir(project_id) / "events" / f"EV-{seq:08d}.json"

    def _operation_path(self, project_id: str, operation_id: str) -> Path:
        name = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return self._project_dir(project_id) / "operations" / f"{name}.json"

    @staticmethod
    def _load_json(path: Path) -> tuple[dict[str, Any], str]:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"CONTINUITY_JSON_OBJECT_REQUIRED: {path.name}")
        return value, _sha256(raw)

    def _load_current_optional(self, project_id: str) -> tuple[dict[str, Any], str] | None:
        pointer_path = self._pointer_path(project_id)
        if not pointer_path.is_file():
            return None
        pointer, _ = self._load_json(pointer_path)
        revision = int(pointer.get("manifest_revision", -1))
        manifest, manifest_sha = self._load_json(self._manifest_path(project_id, revision))
        if (
            pointer.get("schema_version") != self.schema_version
            or pointer.get("project_id") != project_id
            or pointer.get("manifest_id") != manifest.get("manifest_id")
            or pointer.get("manifest_sha256") != manifest_sha
        ):
            raise ValueError("CONTINUITY_POINTER_INTEGRITY_FAILURE")
        return manifest, manifest_sha

    @staticmethod
    def _request_hash(kind: str, body: dict[str, Any]) -> str:
        return _sha256(_json_bytes({"kind": kind, "body": body}))

    def _load_operation(
        self, project_id: str, operation_id: str, kind: str, request_sha: str
    ) -> dict[str, Any] | None:
        path = self._operation_path(project_id, operation_id)
        if not path.is_file():
            return None
        operation, _ = self._load_json(path)
        if operation.get("operation_id") != operation_id or operation.get("kind") != kind:
            raise ValueError("CONTINUITY_OPERATION_INTEGRITY_FAILURE")
        if operation.get("request_sha256") != request_sha:
            raise ValueError("CONTINUITY_OPERATION_CONFLICT")
        result = dict(operation.get("result") or {})
        result["idempotent_recovered"] = True
        return result

    def _write_operation(
        self,
        project_id: str,
        operation_id: str,
        kind: str,
        request_sha: str,
        result: dict[str, Any],
    ) -> None:
        _write_immutable_json(
            self._operation_path(project_id, operation_id),
            {
                "schema_version": self.schema_version,
                "project_id": project_id,
                "operation_id": operation_id,
                "kind": kind,
                "request_sha256": request_sha,
                "state": "COMPLETE",
                "result": result,
                "completed_at_utc": _utc_now(),
            },
        )

    def _assert_cas(
        self,
        current: tuple[dict[str, Any], str] | None,
        expected_revision: int,
        expected_sha: str,
    ) -> None:
        if current is None:
            if int(expected_revision) != 0 or expected_sha:
                raise ValueError("CONTINUITY_CAS_CONFLICT: expected empty head")
            return
        manifest, actual_sha = current
        if int(expected_revision) != int(manifest["manifest_revision"]) or expected_sha != actual_sha:
            raise ValueError(
                f"CONTINUITY_CAS_CONFLICT: current {manifest['manifest_id']} {actual_sha}"
            )

    @staticmethod
    def _new_manifest(
        project_id: str,
        previous: dict[str, Any] | None,
        previous_sha: str,
        event: dict[str, Any],
        event_sha: str,
    ) -> dict[str, Any]:
        revision = int(event["event_seq"])
        manifest = {
            "schema_version": "1.0",
            "project_id": project_id,
            "manifest_id": f"CM-{revision:06d}",
            "manifest_revision": revision,
            "previous_manifest_sha256": previous_sha,
            "event_head": {"seq": revision, "sha256": event_sha},
            "project_session_binding": None,
            "source_binding": None,
            "workflow": {"phase": "IDLE", "state": "READY", "active_operation_id": None},
            "requirements": {"active": []},
            "decisions": {"active": []},
            "constraints": {"active": []},
            "delegations": {"active": [], "awaiting_parent_verification": []},
            "evidence_refs": [],
            "recovery": {"unresolved": []},
            "runtime_authority": None,
            "updated_at_utc": event["created_at_utc"],
        }
        if previous:
            for key in _PROJECTION_FIELDS:
                manifest[key] = previous.get(key)
        projection = event["payload"].get("projection")
        if projection is None:
            projection = event["payload"]
        if isinstance(projection, dict):
            for key in _PROJECTION_FIELDS:
                if key in projection:
                    manifest[key] = projection[key]
        manifest["last_event"] = {
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "operation_id": event["operation_id"],
        }
        return manifest

    def _read_events(self, project_id: str) -> list[tuple[dict[str, Any], str]]:
        directory = self._project_dir(project_id) / "events"
        paths = sorted(directory.glob("EV-*.json")) if directory.is_dir() else []
        out: list[tuple[dict[str, Any], str]] = []
        previous_sha = ""
        for expected_seq, path in enumerate(paths, start=1):
            event, event_sha = self._load_json(path)
            if (
                event.get("schema_version") != self.schema_version
                or event.get("project_id") != project_id
                or event.get("event_id") != f"EV-{expected_seq:08d}"
                or int(event.get("event_seq", -1)) != expected_seq
                or event.get("previous_event_sha256", "") != previous_sha
                or event.get("payload_sha256") != _sha256(_json_bytes(event.get("payload")))
            ):
                raise ValueError(f"CONTINUITY_EVENT_CHAIN_INTEGRITY_FAILURE: {path.name}")
            out.append((event, event_sha))
            previous_sha = event_sha
        return out

    def _read_manifests(self, project_id: str) -> list[tuple[dict[str, Any], str]]:
        directory = self._project_dir(project_id) / "revisions"
        paths = sorted(directory.glob("CM-*.json")) if directory.is_dir() else []
        out: list[tuple[dict[str, Any], str]] = []
        previous_sha = ""
        for expected_revision, path in enumerate(paths, start=1):
            manifest, manifest_sha = self._load_json(path)
            if (
                manifest.get("schema_version") != self.schema_version
                or manifest.get("project_id") != project_id
                or manifest.get("manifest_id") != f"CM-{expected_revision:06d}"
                or int(manifest.get("manifest_revision", -1)) != expected_revision
                or manifest.get("previous_manifest_sha256", "") != previous_sha
            ):
                raise ValueError(f"CONTINUITY_MANIFEST_CHAIN_INTEGRITY_FAILURE: {path.name}")
            out.append((manifest, manifest_sha))
            previous_sha = manifest_sha
        return out

    def _ensure_manifests(
        self, project_id: str, events: list[tuple[dict[str, Any], str]]
    ) -> list[tuple[dict[str, Any], str]]:
        out: list[tuple[dict[str, Any], str]] = []
        previous: dict[str, Any] | None = None
        previous_sha = ""
        for event, event_sha in events:
            manifest = self._new_manifest(project_id, previous, previous_sha, event, event_sha)
            manifest_sha = _write_immutable_json(
                self._manifest_path(project_id, int(event["event_seq"])), manifest
            )
            out.append((manifest, manifest_sha))
            previous, previous_sha = manifest, manifest_sha
        existing = self._read_manifests(project_id)
        if len(existing) != len(out):
            raise ValueError("CONTINUITY_MANIFEST_EVENT_COUNT_CONFLICT")
        return out

    def _advance_pointer(self, project_id: str, manifest: dict[str, Any], manifest_sha: str) -> None:
        _write_json(
            self._pointer_path(project_id),
            {
                "schema_version": self.schema_version,
                "project_id": project_id,
                "manifest_id": manifest["manifest_id"],
                "manifest_revision": manifest["manifest_revision"],
                "manifest_sha256": manifest_sha,
                "updated_at_utc": manifest["updated_at_utc"],
            },
        )

    def get(self, project_id: str) -> dict[str, Any]:
        pid = self._project_id(project_id)
        current = self._load_current_optional(pid)
        if current is None:
            raise FileNotFoundError(f"CONTINUITY_NOT_FOUND: {pid}")
        manifest, manifest_sha = current
        return {**manifest, "manifest_sha256": manifest_sha, "integrity": "VERIFIED"}

    def read_events(self, project_id: str, after_seq: int = 0, limit: int = 100) -> dict[str, Any]:
        pid = self._project_id(project_id)
        start = max(0, int(after_seq))
        bounded = max(1, min(int(limit), 1000))
        events = self._read_events(pid)
        selected = [event for event, _ in events if int(event["event_seq"]) > start][:bounded]
        return {
            "schema_version": self.schema_version,
            "project_id": pid,
            "after_seq": start,
            "count": len(selected),
            "events": selected,
            "next_after_seq": selected[-1]["event_seq"] if selected else start,
        }

    def append_event(
        self,
        project_id: str,
        event_type: str,
        payload: dict[str, Any],
        operation_id: str,
        expected_manifest_revision: int,
        expected_manifest_sha256: str,
        actor_provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pid = self._project_id(project_id)
        kind = str(event_type or "").strip().upper()
        if not _EVENT_TYPE_RE.fullmatch(kind):
            raise ValueError("Invalid event_type")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if len(_json_bytes(payload)) > 1024 * 1024:
            raise ValueError("CONTINUITY_PAYLOAD_TOO_LARGE")
        operation = self._operation_id(operation_id)
        body = {"project_id": pid, "event_type": kind, "payload": payload}
        request_sha = self._request_hash("append_event", body)
        expected_sha = self._expected_sha(
            expected_manifest_sha256, allow_empty=int(expected_manifest_revision) == 0
        )

        with _ContinuityLock(self._project_dir(pid) / ".continuity.lock"):
            prior = self._load_operation(pid, operation, "append_event", request_sha)
            if prior is not None:
                return prior

            events = self._read_events(pid)
            for event, _ in events:
                if event.get("operation_id") != operation:
                    continue
                if event.get("operation_payload_sha256") != request_sha:
                    raise ValueError("CONTINUITY_OPERATION_CONFLICT")
                manifests = self._ensure_manifests(pid, events)
                head, head_sha = manifests[-1]
                self._advance_pointer(pid, head, head_sha)
                target, target_sha = manifests[int(event["event_seq"]) - 1]
                result = {
                    **target,
                    "manifest_sha256": target_sha,
                    "event": event,
                    "idempotent_recovered": True,
                }
                self._write_operation(pid, operation, "append_event", request_sha, result)
                return result

            current = self._load_current_optional(pid)
            self._assert_cas(current, int(expected_manifest_revision), expected_sha)
            previous, previous_manifest_sha = current or (None, "")
            next_seq = int(previous["event_head"]["seq"]) + 1 if previous else 1
            if len(events) != next_seq - 1:
                raise ValueError("CONTINUITY_HEAD_EVENT_DRIFT: reconcile required")
            previous_event_sha = events[-1][1] if events else ""
            actor = dict(actor_provenance or {})
            actor["security_identity"] = False
            event = {
                "schema_version": self.schema_version,
                "project_id": pid,
                "event_id": f"EV-{next_seq:08d}",
                "event_seq": next_seq,
                "event_type": kind,
                "operation_id": operation,
                "operation_payload_sha256": request_sha,
                "payload_sha256": _sha256(_json_bytes(payload)),
                "payload": payload,
                "previous_event_sha256": previous_event_sha,
                "created_at_utc": _utc_now(),
                "actor_provenance": actor,
            }
            event_sha = _write_immutable_json(self._event_path(pid, next_seq), event)
            manifest = self._new_manifest(pid, previous, previous_manifest_sha, event, event_sha)
            manifest_sha = _write_immutable_json(self._manifest_path(pid, next_seq), manifest)
            self._advance_pointer(pid, manifest, manifest_sha)
            result = {
                **manifest,
                "manifest_sha256": manifest_sha,
                "event": event,
                "idempotent_recovered": False,
            }
            self._write_operation(pid, operation, "append_event", request_sha, result)
            return result

    def create_checkpoint(
        self,
        project_id: str,
        label: str,
        operation_id: str,
        expected_manifest_revision: int,
        expected_manifest_sha256: str,
    ) -> dict[str, Any]:
        pid = self._project_id(project_id)
        operation = self._operation_id(operation_id)
        clean_label = str(label or "").strip()
        if len(clean_label) > 200:
            raise ValueError("label exceeds 200 characters")
        body = {"project_id": pid, "label": clean_label}
        request_sha = self._request_hash("create_checkpoint", body)
        expected_sha = self._expected_sha(expected_manifest_sha256, allow_empty=False)
        with _ContinuityLock(self._project_dir(pid) / ".continuity.lock"):
            prior = self._load_operation(pid, operation, "create_checkpoint", request_sha)
            if prior is not None:
                return prior
            current = self._load_current_optional(pid)
            self._assert_cas(current, int(expected_manifest_revision), expected_sha)
            if current is None:
                raise FileNotFoundError(f"CONTINUITY_NOT_FOUND: {pid}")
            manifest, manifest_sha = current
            checkpoint_id = f"CCP-{int(manifest['manifest_revision']):06d}-{request_sha[:12].upper()}"
            checkpoint_path = self._project_dir(pid) / "checkpoints" / f"{checkpoint_id}.json"
            if checkpoint_path.is_file():
                checkpoint, checkpoint_sha = self._load_json(checkpoint_path)
            else:
                checkpoint = {
                    "schema_version": self.schema_version,
                    "checkpoint_id": checkpoint_id,
                    "project_id": pid,
                    "manifest_revision": manifest["manifest_revision"],
                    "manifest_sha256": manifest_sha,
                    "event_head_seq": manifest["event_head"]["seq"],
                    "event_head_sha256": manifest["event_head"]["sha256"],
                    "project_session_binding": manifest.get("project_session_binding"),
                    "source_binding": manifest.get("source_binding"),
                    "label": clean_label,
                    "created_at_utc": _utc_now(),
                }
                checkpoint_sha = _write_immutable_json(checkpoint_path, checkpoint)
            result = {
                **checkpoint,
                "checkpoint_sha256": checkpoint_sha,
                "idempotent_recovered": False,
            }
            self._write_operation(pid, operation, "create_checkpoint", request_sha, result)
            return result

    def verify(self, project_id: str) -> dict[str, Any]:
        pid = self._project_id(project_id)
        before = []
        project_dir = self._project_dir(pid)
        if project_dir.exists():
            before = sorted(str(path.relative_to(project_dir)) for path in project_dir.rglob("*") if path.is_file())
        if not project_dir.is_dir():
            return {
                "schema_version": self.schema_version,
                "project_id": pid,
                "integrity": "NOT_FOUND",
                "resume_safe": False,
                "recommended_recovery_actions": ["append initial continuity event"],
            }
        try:
            events = self._read_events(pid)
            manifests = self._read_manifests(pid)
            current = self._load_current_optional(pid)
            issues: list[str] = []
            if len(events) != len(manifests):
                issues.append("MANIFEST_EVENT_COUNT_DRIFT")
            for index, ((event, event_sha), (manifest, _)) in enumerate(zip(events, manifests), start=1):
                if manifest.get("event_head") != {"seq": index, "sha256": event_sha}:
                    issues.append(f"MANIFEST_EVENT_HEAD_MISMATCH:{index}")
            if not current and events:
                issues.append("CURRENT_POINTER_MISSING")
            elif current and manifests and current[1] != manifests[-1][1]:
                issues.append("CURRENT_POINTER_BEHIND_HEAD")
            missing_operations = [
                event["operation_id"]
                for event, _ in events
                if not self._operation_path(pid, event["operation_id"]).is_file()
            ]
            if missing_operations:
                issues.append("OPERATION_INDEX_INCOMPLETE")
            integrity = "VERIFIED" if not issues else "DRIFT"
            actions = [] if not issues else ["call reconcile_continuity with exact current head CAS"]
            after = sorted(str(path.relative_to(project_dir)) for path in project_dir.rglob("*") if path.is_file())
            return {
                "schema_version": self.schema_version,
                "project_id": pid,
                "integrity": integrity,
                "resume_safe": not issues,
                "manifest_chain": {
                    "count": len(manifests),
                    "head": manifests[-1][0]["manifest_id"] if manifests else None,
                    "head_sha256": manifests[-1][1] if manifests else None,
                },
                "event_chain": {
                    "count": len(events),
                    "head": events[-1][0]["event_id"] if events else None,
                    "head_sha256": events[-1][1] if events else None,
                },
                "operations": {
                    "complete": not missing_operations,
                    "missing_operation_ids": missing_operations,
                },
                "issues": issues,
                "recommended_recovery_actions": actions,
                "read_only_proof": {"files_before": before, "files_after": after, "unchanged": before == after},
            }
        except Exception as exc:
            return {
                "schema_version": self.schema_version,
                "project_id": pid,
                "integrity": "INVALID",
                "resume_safe": False,
                "issues": [str(exc)],
                "recommended_recovery_actions": ["restore a verified continuity checkpoint or repair manually"],
            }

    def reconcile(
        self,
        project_id: str,
        operation_id: str,
        expected_manifest_revision: int,
        expected_manifest_sha256: str,
    ) -> dict[str, Any]:
        pid = self._project_id(project_id)
        operation = self._operation_id(operation_id)
        body = {"project_id": pid}
        request_sha = self._request_hash("reconcile", body)
        expected_sha = self._expected_sha(
            expected_manifest_sha256, allow_empty=int(expected_manifest_revision) == 0
        )
        with _ContinuityLock(self._project_dir(pid) / ".continuity.lock"):
            prior = self._load_operation(pid, operation, "reconcile", request_sha)
            if prior is not None:
                return prior
            current = self._load_current_optional(pid)
            self._assert_cas(current, int(expected_manifest_revision), expected_sha)
            events = self._read_events(pid)
            if not events:
                raise FileNotFoundError(f"CONTINUITY_NOT_FOUND: {pid}")
            manifests = self._ensure_manifests(pid, events)
            head, head_sha = manifests[-1]
            self._advance_pointer(pid, head, head_sha)
            for event, _ in events:
                op_path = self._operation_path(pid, event["operation_id"])
                if op_path.is_file():
                    continue
                target, target_sha = manifests[int(event["event_seq"]) - 1]
                recovered = {
                    **target,
                    "manifest_sha256": target_sha,
                    "event": event,
                    "idempotent_recovered": True,
                }
                self._write_operation(
                    pid,
                    event["operation_id"],
                    "append_event",
                    event["operation_payload_sha256"],
                    recovered,
                )
            result = {
                "schema_version": self.schema_version,
                "project_id": pid,
                "state": "RECONCILED",
                "manifest_id": head["manifest_id"],
                "manifest_revision": head["manifest_revision"],
                "manifest_sha256": head_sha,
                "event_head": head["event_head"],
                "idempotent_recovered": False,
            }
            self._write_operation(pid, operation, "reconcile", request_sha, result)
            return result
