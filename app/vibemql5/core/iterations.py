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

from ..config import load_settings
from .artifacts import ArtifactManager
from .baseline import BaselineJobValidator
from .compiler import CompilerDriver
from .fault_injection import TIP015BFaultInjector
from .jobs import JobManager
from .project_sessions import ProjectSessionManager
from .revisions import RevisionManager
from .workspace import (
    WorkspaceManager,
    _UTF8_BOM,
    _decode_utf8_preserve_newlines,
    _encode_preserving_format,
    _newline_profile,
    _normalize_newlines,
)

_ITERATION_ID_RE = re.compile(r"^IT-[0-9]{8}-[0-9]{6}-[A-F0-9]{8}$")
_ITERATION_REV_RE = re.compile(r"^IR-[0-9]{6}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

TERMINAL_ITERATION_STATES = {
    "ACCEPTED",
    "REJECTED_ROLLED_BACK",
    "FAILED_ROLLED_BACK",
    "CANCELLED_ROLLED_BACK",
}
JOB_FAILURE_STATES = {"FAILED", "TIMEOUT", "CANCELLED", "INTERRUPTED", "RESOURCE_LIMIT"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
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


def _atomic_json(path: Path, value: dict[str, Any]) -> str:
    raw = _canonical_bytes(value)
    _atomic_write(path, raw)
    return _sha(raw)


def _new_iteration_id() -> str:
    return "IT-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8].upper()


class _MutationMutex:
    """Short-lived filesystem mutex for atomic iteration metadata updates.

    This is not the persistent active-iteration ownership lock. It may remove an
    abandoned metadata mutex after a bounded age; active iteration ownership never
    uses PID/time stealing.
    """

    def __init__(self, path: Path, timeout: float = 5.0, stale: float = 60.0):
        self.path = path
        self.timeout = timeout
        self.stale = stale
        self.owned = False

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, json.dumps({"pid": os.getpid(), "at": _now()}).encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self.owned = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError("ITERATION_METADATA_BUSY")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.owned:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


class IterationStore:
    schema_version = "1.0"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.state_root = self.root / "state" / "iterations"
        self.lock_root = self.state_root / "locks"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.lock_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_target(workspace: str, ea: str) -> str:
        return f"{str(workspace).strip().lower()}::{str(ea).replace('\\', '/').strip().lower()}"

    def _dir(self, iteration_id: str) -> Path:
        if not _ITERATION_ID_RE.fullmatch(str(iteration_id or "")):
            raise ValueError("Invalid iteration_id")
        p = (self.state_root / iteration_id).resolve()
        if p.parent != self.state_root:
            raise ValueError("Iteration path escapes state root")
        return p

    def _rev_path(self, iteration_id: str, revision_id: str) -> Path:
        if not _ITERATION_REV_RE.fullmatch(str(revision_id or "")):
            raise ValueError("Invalid iteration revision")
        return self._dir(iteration_id) / "revisions" / f"{revision_id}.json"

    def _pointer(self, iteration_id: str) -> Path:
        return self._dir(iteration_id) / "current.json"

    def _mutex(self, iteration_id: str) -> Path:
        return self._dir(iteration_id) / ".metadata.lock"

    def _target_lock(self, target: str) -> Path:
        return self.lock_root / f"{hashlib.sha256(target.encode('utf-8')).hexdigest()}.json"

    def load(self, iteration_id: str) -> dict[str, Any]:
        pointer = json.loads(self._pointer(iteration_id).read_text(encoding="utf-8"))
        revision_id = str(pointer.get("revision_id") or "")
        path = self._rev_path(iteration_id, revision_id)
        raw = path.read_bytes()
        actual = _sha(raw)
        if actual != pointer.get("revision_sha256"):
            raise ValueError("ITERATION_REVISION_INTEGRITY_FAILURE")
        data = json.loads(raw.decode("utf-8"))
        if data.get("schema_version") != self.schema_version or data.get("iteration_id") != iteration_id:
            raise ValueError("ITERATION_REVISION_METADATA_MISMATCH")
        return {**data, "iteration_revision_sha256": actual}

    def list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in sorted(self.state_root.glob("IT-*")):
            if not p.is_dir():
                continue
            try:
                it = self.load(p.name)
                out.append({
                    "iteration_id": it["iteration_id"],
                    "project_id": it["project_id"],
                    "workspace": it["workspace"],
                    "ea": it["ea"],
                    "state": it["state"],
                    "iteration_revision": it["iteration_revision"],
                    "iteration_revision_sha256": it["iteration_revision_sha256"],
                    "updated_at_utc": it["updated_at_utc"],
                })
            except Exception as exc:
                out.append({"iteration_id": p.name, "state": "INVALID", "error": str(exc)})
        return out

    def _owner_terminal(self, iteration_id: str) -> bool:
        try:
            return self.load(iteration_id).get("state") in TERMINAL_ITERATION_STATES
        except Exception:
            raise RuntimeError(f"ITERATION_LOCK_RECOVERY_REQUIRED: owner {iteration_id} cannot be verified")

    def acquire_target(self, iteration_id: str, workspace: str, ea: str) -> dict[str, Any]:
        target = self.normalize_target(workspace, ea)
        path = self._target_lock(target)
        record = {
            "schema_version": "1.0",
            "target": target,
            "iteration_id": iteration_id,
            "created_at_utc": _now(),
        }
        while True:
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise RuntimeError("ITERATION_LOCK_RECOVERY_REQUIRED: corrupt active lock") from exc
                owner = str(existing.get("iteration_id") or "")
                if existing.get("target") != target or not _ITERATION_ID_RE.fullmatch(owner):
                    raise RuntimeError("ITERATION_LOCK_RECOVERY_REQUIRED: invalid active lock")
                if owner == iteration_id:
                    return {**existing, "reused": True}
                if self._owner_terminal(owner):
                    path.unlink(missing_ok=True)
                    continue
                raise RuntimeError(f"ITERATION_ALREADY_ACTIVE: {owner}")
            else:
                try:
                    raw = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
                    os.write(fd, raw)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                return {**record, "reused": False}

    def release_target(self, iteration_id: str, workspace: str, ea: str) -> dict[str, Any]:
        target = self.normalize_target(workspace, ea)
        path = self._target_lock(target)
        if not path.exists():
            return {"released": False, "already_absent": True}
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("ITERATION_LOCK_RECOVERY_REQUIRED: corrupt active lock") from exc
        if existing.get("iteration_id") != iteration_id:
            raise RuntimeError("ITERATION_LOCK_OWNERSHIP_CONFLICT")
        path.unlink(missing_ok=True)
        return {"released": True, "already_absent": False}

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        iteration_id = payload["iteration_id"]
        d = self._dir(iteration_id)
        if d.exists():
            raise FileExistsError("ITERATION_ALREADY_EXISTS")
        d.mkdir(parents=True, exist_ok=False)
        (d / "revisions").mkdir()
        now = _now()
        revision = {
            **payload,
            "schema_version": self.schema_version,
            "iteration_revision": "IR-000001",
            "iteration_revision_number": 1,
            "previous_iteration_revision_sha256": "",
            "created_at_utc": now,
            "updated_at_utc": now,
        }
        sha = _atomic_json(self._rev_path(iteration_id, "IR-000001"), revision)
        _atomic_json(self._pointer(iteration_id), {
            "schema_version": self.schema_version,
            "iteration_id": iteration_id,
            "revision_id": "IR-000001",
            "revision_sha256": sha,
            "updated_at_utc": now,
        })
        return {**revision, "iteration_revision_sha256": sha}

    def mutate(self, iteration_id: str, expected_revision: str, expected_sha256: str, changes: dict[str, Any]) -> dict[str, Any]:
        with _MutationMutex(self._mutex(iteration_id)):
            current = self.load(iteration_id)
            if current["iteration_revision"] != expected_revision or current["iteration_revision_sha256"] != expected_sha256:
                raise ValueError(
                    f"ITERATION_VERSION_CONFLICT: expected {expected_revision}/{expected_sha256}, "
                    f"current {current['iteration_revision']}/{current['iteration_revision_sha256']}"
                )
            number = int(current["iteration_revision_number"]) + 1
            now = _now()
            payload = {k: v for k, v in current.items() if k != "iteration_revision_sha256"}
            payload.update(changes)
            payload.update({
                "iteration_revision": f"IR-{number:06d}",
                "iteration_revision_number": number,
                "previous_iteration_revision_sha256": current["iteration_revision_sha256"],
                "updated_at_utc": now,
            })
            next_path = self._rev_path(iteration_id, payload["iteration_revision"])
            idempotent_recovered = False
            if next_path.exists():
                raw = next_path.read_bytes()
                sha = _sha(raw)
                try:
                    existing = json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    raise RuntimeError("ITERATION_REVISION_RECOVERY_REQUIRED: unreadable next revision") from exc
                comparable = dict(payload)
                comparable["updated_at_utc"] = existing.get("updated_at_utc")
                if existing != comparable:
                    raise RuntimeError("ITERATION_REVISION_RECOVERY_REQUIRED: divergent immutable next revision")
                payload = existing
                idempotent_recovered = True
            else:
                sha = _atomic_json(next_path, payload)
            _atomic_json(self._pointer(iteration_id), {
                "schema_version": self.schema_version,
                "iteration_id": iteration_id,
                "revision_id": payload["iteration_revision"],
                "revision_sha256": sha,
                "updated_at_utc": payload["updated_at_utc"],
            })
            return {**payload, "iteration_revision_sha256": sha, "idempotent_recovered": idempotent_recovered}


class IterationManager:
    schema_version = "1.0"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.store = IterationStore(self.root)
        self.sessions = ProjectSessionManager(self.root)
        self.revisions = RevisionManager(self.root)
        self.workspace = WorkspaceManager(self.root)
        self.jobs = JobManager(self.root)
        self.baselines = BaselineJobValidator(self.root)
        self.faults = TIP015BFaultInjector(self.root)

    def _fixed_terminal(self) -> str:
        settings = load_settings(self.root)
        return str((settings.get("terminal_policy") or {}).get("alias") or "MT5-2")

    @staticmethod
    def _require_sha(value: str, field: str) -> str:
        v = str(value or "").strip().lower()
        if not _SHA_RE.fullmatch(v):
            raise ValueError(f"{field} must be exact SHA-256")
        return v

    @staticmethod
    def _cas(it: dict[str, Any]) -> tuple[str, str]:
        return it["iteration_revision"], it["iteration_revision_sha256"]

    def _transition(self, it: dict[str, Any], state: str, **extra: Any) -> dict[str, Any]:
        rev, sha = self._cas(it)
        return self.store.mutate(it["iteration_id"], rev, sha, {"state": state, **extra})

    def _assert_cas(self, it: dict[str, Any], expected_revision: str, expected_sha: str) -> None:
        if it.get("state") in TERMINAL_ITERATION_STATES:
            return
        if it["iteration_revision"] != expected_revision or it["iteration_revision_sha256"] != expected_sha:
            raise ValueError(
                f"ITERATION_VERSION_CONFLICT: expected {expected_revision}/{expected_sha}, "
                f"current {it['iteration_revision']}/{it['iteration_revision_sha256']}"
            )

    def start(self, project_id: str, expected_session_revision: str, expected_session_revision_sha256: str, expected_source_sha256: str, expected_source_bytes: int, mutation: dict[str, Any], *, preset: str = "smoke", set_file: str = "", overrides: dict[str, Any] | None = None, timeout_seconds: int = 0) -> dict[str, Any]:
        session = self.sessions.get(project_id)
        session_sha = self._require_sha(expected_session_revision_sha256, "expected_session_revision_sha256")
        source_sha = self._require_sha(expected_source_sha256, "expected_source_sha256")
        if session["revision_id"] != expected_session_revision or session["revision_sha256"] != session_sha:
            raise ValueError("PROJECT_SESSION_VERSION_CONFLICT: iteration binding is stale")
        resumed = self.sessions.resume(project_id)
        if not resumed.get("resume_safe"):
            raise RuntimeError(f"PROJECT_SESSION_NOT_RESUME_SAFE: {resumed.get('stale_reasons')}")
        if session["source_sha256"] != source_sha or int(session["source_bytes"]) != int(expected_source_bytes):
            raise ValueError("SOURCE_VERSION_CONFLICT: iteration source binding differs from project session")
        current = self.revisions.source_hash(session["workspace"], session["ea"])
        if current["sha256"] != source_sha or int(current["bytes"]) != int(expected_source_bytes):
            raise ValueError("SOURCE_VERSION_CONFLICT: runtime source differs from requested iteration base")
        kind = str((mutation or {}).get("kind") or "apply_patch")
        if kind not in {"apply_patch", "write_source"}:
            raise ValueError("Unsupported mutation kind")
        if kind == "apply_patch" and not isinstance(mutation.get("replacements"), list):
            raise ValueError("apply_patch mutation requires replacements list")
        if kind == "write_source" and not isinstance(mutation.get("content"), str):
            raise ValueError("write_source mutation requires content string")
        timeout_seconds = int(timeout_seconds)
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be 0 (event-driven) or a positive number of seconds")
        if timeout_seconds > 86400:
            raise ValueError("timeout_seconds cannot exceed 86400 when explicitly set")
        iteration_id = _new_iteration_id()
        self.store.acquire_target(iteration_id, session["workspace"], session["ea"])
        payload = {
            "iteration_id": iteration_id,
            "project_id": project_id,
            "session_revision_id": session["revision_id"],
            "session_revision_sha256": session["revision_sha256"],
            "workspace": session["workspace"],
            "ea": session["ea"],
            "base_source_sha256": source_sha,
            "base_source_bytes": int(expected_source_bytes),
            "baseline_job_id": session.get("baseline_job_id", ""),
            "state": "SESSION_BOUND",
            "mutation": mutation,
            "preset": str(preset or "smoke"),
            "set_file": str(set_file or ""),
            "overrides": overrides or {},
            "timeout_seconds": timeout_seconds,
            "checkpoint_id": "",
            "candidate_source_sha256": "",
            "candidate_source_bytes": 0,
            "compile_evidence": {},
            "test_operation_id": "",
            "job_id": "",
            "baseline_validation": {},
            "baseline_comparison": {},
            "policy_result": "NOT_EVALUATED",
            "accept_operation_id": "",
            "rollback": {},
            "failure": {},
        }
        try:
            return self.store.create(payload)
        except Exception:
            try:
                self.store.release_target(iteration_id, session["workspace"], session["ea"])
            except Exception:
                pass
            raise

    def get(self, iteration_id: str) -> dict[str, Any]:
        return self.store.load(iteration_id)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def _precheck_session(self, it: dict[str, Any]) -> None:
        current = self.sessions.get(it["project_id"])
        if current["revision_id"] != it["session_revision_id"] or current["revision_sha256"] != it["session_revision_sha256"]:
            raise RuntimeError("PROJECT_SESSION_VERSION_CONFLICT: project session advanced before iteration mutation")
        source = self.revisions.source_hash(it["workspace"], it["ea"])
        if source["sha256"] != it["base_source_sha256"] or int(source["bytes"]) != int(it["base_source_bytes"]):
            raise RuntimeError("SOURCE_VERSION_CONFLICT: source changed before checkpoint")

    @staticmethod
    def _checkpoint_operation_id(iteration_id: str) -> str:
        parts = str(iteration_id).split("-")
        if len(parts) != 4 or parts[0] != "IT":
            raise ValueError("Invalid iteration_id for checkpoint operation")
        suffix = hashlib.sha256(iteration_id.encode("utf-8")).hexdigest()[:12].upper()
        return f"CP-{parts[1]}-{parts[2]}-{suffix}"

    def _plan_candidate(self, it: dict[str, Any]) -> dict[str, Any]:
        path = self.workspace.resolve(it["workspace"], it["ea"], must_exist=True)
        original = path.read_bytes()
        if _sha(original) != it["base_source_sha256"] or len(original) != int(it["base_source_bytes"]):
            raise RuntimeError("SOURCE_VERSION_CONFLICT: candidate plan base changed")
        mutation = it["mutation"]
        if mutation["kind"] == "write_source":
            data, newline_style, has_bom = _encode_preserving_format(str(mutation["content"]), original)
            replacements = None
        else:
            text, has_bom = _decode_utf8_preserve_newlines(original)
            newline, newline_style = _newline_profile(text)
            replacements = 0
            for repl in mutation["replacements"]:
                old = repl.get("old")
                new = repl.get("new", "")
                count = int(repl.get("count", 1))
                if not old:
                    raise ValueError("Patch replacement requires non-empty 'old'")
                old = _normalize_newlines(str(old), newline)
                new = _normalize_newlines(str(new), newline)
                found = text.count(old)
                if found == 0:
                    raise ValueError("Patch anchor not found")
                if count > 0 and found < count:
                    raise ValueError(f"Patch requested {count} replacements but only {found} anchors found")
                text, n = text.replace(old, new, count), min(found, count if count > 0 else found)
                replacements += n
            data = text.encode("utf-8")
            if has_bom:
                data = _UTF8_BOM + data
        return {
            "sha256": _sha(data),
            "bytes": len(data),
            "replacements": replacements,
            "newline_style": newline_style,
            "utf8_bom": has_bom,
        }

    def _mutate_source(self, it: dict[str, Any]) -> dict[str, Any]:
        planned_sha = str(it.get("planned_candidate_sha256") or "")
        planned_bytes = int(it.get("planned_candidate_bytes") or 0)
        current = self.revisions.source_hash(it["workspace"], it["ea"])
        if current["sha256"] == planned_sha and int(current["bytes"]) == planned_bytes:
            return {
                "before_sha256": it["base_source_sha256"],
                "sha256": planned_sha,
                "bytes": planned_bytes,
                "replacements": (it.get("planned_mutation_evidence") or {}).get("replacements"),
                "atomic": True,
                "format_preserved": True,
                "newline_style": (it.get("planned_mutation_evidence") or {}).get("newline_style"),
                "utf8_bom": (it.get("planned_mutation_evidence") or {}).get("utf8_bom"),
                "idempotent_recovered": True,
            }
        if current["sha256"] != it["base_source_sha256"] or int(current["bytes"]) != int(it["base_source_bytes"]):
            raise RuntimeError("MUTATION_RECONCILIATION_REQUIRED: source is neither base nor planned candidate")
        mutation = it["mutation"]
        if mutation["kind"] == "write_source":
            out = self.workspace.write_text(
                it["workspace"], it["ea"], mutation["content"],
                expected_sha256=it["base_source_sha256"], checkpoint_id=it["checkpoint_id"],
            )
        else:
            out = self.workspace.apply_patch(
                it["workspace"], it["ea"], mutation["replacements"],
                expected_sha256=it["base_source_sha256"], checkpoint_id=it["checkpoint_id"],
            )
        if out.get("sha256") != planned_sha or int(out.get("bytes") or -1) != planned_bytes:
            raise RuntimeError("MUTATION_RESULT_MISMATCH: actual candidate differs from persisted plan")
        return {**out, "idempotent_recovered": False}

    def _compile_candidate(self, it: dict[str, Any]) -> dict[str, Any]:
        source = self.revisions.source_hash(it["workspace"], it["ea"])
        if source["sha256"] != it["candidate_source_sha256"] or int(source["bytes"]) != int(it["candidate_source_bytes"]):
            raise RuntimeError("CANDIDATE_SOURCE_DRIFT: source changed before compile")
        if os.environ.get("VIBEMQL5_RUNTIME_MODE", "manual").strip().lower() == "background":
            raise RuntimeError("MT5_INTERACTIVE_SESSION_REQUIRED")
        compile_id = "ITC-" + it["iteration_id"][3:]
        run_dir = ArtifactManager(self.root).run_dir(compile_id)
        result = CompilerDriver(self.root).compile(
            it["workspace"], it["ea"], self._fixed_terminal(), run_dir,
            timeout=int(load_settings(self.root).get("jobs", {}).get("compile_timeout_seconds", 120)),
            mock=False,
        )
        return {"compile_run_id": compile_id, **result}

    def _candidate_request(self, it: dict[str, Any]) -> dict[str, Any]:
        return {
            "workspace": it["workspace"],
            "ea": it["ea"],
            "terminal": self._fixed_terminal(),
            "preset": it["preset"],
            "set_file": it["set_file"] or None,
            "overrides": it["overrides"],
            "mock": False,
            "test_timeout": int(it["timeout_seconds"]),
            "expected_source_sha256": it["candidate_source_sha256"],
            "expected_source_bytes": int(it["candidate_source_bytes"]),
            "iteration_id": it["iteration_id"],
        }

    def _verify_rollback(self, it: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        matches = [x for x in self.revisions.list_checkpoints(it["workspace"], it["ea"]) if x.get("checkpoint_id") == it["checkpoint_id"]]
        if not matches:
            return False, {"status": "RECOVERY_REQUIRED", "reason": "CHECKPOINT_MISSING"}
        cp = matches[0]
        current = self.revisions.source_hash(it["workspace"], it["ea"])
        if current["sha256"] == cp["sha256"] and int(current["bytes"]) == int(cp["bytes"]):
            diff = self.revisions.diff_checkpoint(it["workspace"], it["checkpoint_id"])
            ok = not diff["changed"] and diff["diff"] == ""
            return ok, {"status": "ALREADY_RESTORED" if ok else "RECOVERY_REQUIRED", "checkpoint_sha256": cp["sha256"], "source_sha256": current["sha256"], "bytes": current["bytes"], "diff_empty": diff["diff"] == ""}
        if current["sha256"] == it.get("candidate_source_sha256") and int(current["bytes"]) == int(it.get("candidate_source_bytes") or -1):
            restored = self.revisions.restore_checkpoint(it["workspace"], it["checkpoint_id"], expected_current_sha256=it["candidate_source_sha256"])
            diff = self.revisions.diff_checkpoint(it["workspace"], it["checkpoint_id"])
            after = self.revisions.source_hash(it["workspace"], it["ea"])
            ok = restored.get("match") is True and after["sha256"] == cp["sha256"] and int(after["bytes"]) == int(cp["bytes"]) and not diff["changed"] and diff["diff"] == ""
            return ok, {"status": "RESTORED" if ok else "RECOVERY_REQUIRED", "restore": restored, "checkpoint_sha256": cp["sha256"], "source_sha256": after["sha256"], "bytes": after["bytes"], "diff_empty": diff["diff"] == ""}
        return False, {"status": "RECOVERY_REQUIRED", "reason": "UNEXPECTED_SOURCE_STATE", "current_sha256": current["sha256"], "current_bytes": current["bytes"], "candidate_sha256": it.get("candidate_source_sha256"), "checkpoint_sha256": cp["sha256"]}

    def _rollback(self, it: dict[str, Any], final_state: str, reason: str) -> dict[str, Any]:
        if it["state"] != "ROLLBACK_INTENT":
            it = self._transition(it, "ROLLBACK_INTENT", rollback={"status": "INTENT", "reason": reason, "target_state": final_state, "operation_id": f"{it['iteration_id']}:ROLLBACK"})
            self.faults.hit("ROLLBACK_AFTER_INTENT", it["iteration_id"], context={"iteration_revision": it["iteration_revision"], "target_state": final_state, "reason": reason})
        ok, evidence = self._verify_rollback(it)
        evidence = {**evidence, "requested_reason": reason, "target_state": final_state, "operation_id": f"{it['iteration_id']}:ROLLBACK"}
        evidence.setdefault("reason", reason)
        if not ok:
            return self._transition(it, "RECOVERY_REQUIRED", rollback=evidence)
        it = self._transition(it, final_state, rollback=evidence)
        self.store.release_target(it["iteration_id"], it["workspace"], it["ea"])
        return it

    def _accept_reconcile(self, it: dict[str, Any]) -> dict[str, Any]:
        source = self.revisions.source_hash(it["workspace"], it["ea"])
        if source["sha256"] != it["candidate_source_sha256"] or int(source["bytes"]) != int(it["candidate_source_bytes"]):
            return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "CANDIDATE_SOURCE_CHANGED_BEFORE_ACCEPT"})
        bound = self.sessions.get(it["project_id"])
        refs = list(bound.get("decision_refs") or [])
        if "TIP-015" not in refs:
            refs.append("TIP-015")
        promotion_session = {"workspace": it["workspace"], "ea": it["ea"], "source_sha256": it["candidate_source_sha256"], "source_bytes": int(it["candidate_source_bytes"]), "baseline_job_id": it["job_id"]}
        promotion = self.baselines.validate(promotion_session, self._candidate_request(it))
        if promotion.get("status") != "VALID":
            return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "ACCEPT_BASELINE_PROMOTION_INVALID", "baseline_validation": {k: v for k, v in promotion.items() if k not in {"result", "request"}}})
        try:
            updated = self.sessions.update(it["project_id"], it["session_revision_id"], active_goal=bound.get("active_goal"), decision_refs=refs, phase="EVIDENCE", checkpoint_id=it["checkpoint_id"], baseline_job_id=it["job_id"], last_job_id=it["job_id"], operation_id=it["accept_operation_id"], expected_revision_sha256=it["session_revision_sha256"])
        except Exception as exc:
            return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "ACCEPT_SESSION_UPDATE_FAILED", "message": str(exc)})
        self.faults.hit("ACCEPT_AFTER_SESSION_UPDATE", it["iteration_id"], context={"iteration_revision": it["iteration_revision"], "accept_operation_id": it["accept_operation_id"], "accepted_session_revision_id": updated["revision_id"], "accepted_session_revision_sha256": updated["revision_sha256"]})
        it = self._transition(it, "ACCEPTED", accepted_session_revision={"revision_id": updated["revision_id"], "revision_sha256": updated["revision_sha256"], "baseline_job_id": updated.get("baseline_job_id"), "last_job_id": updated.get("last_job_id"), "idempotent_recovered": bool(updated.get("idempotent_recovered"))})
        self.store.release_target(it["iteration_id"], it["workspace"], it["ea"])
        return it

    def resume(self, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        it = self.store.load(iteration_id)
        if it["state"] in TERMINAL_ITERATION_STATES:
            return {**it, "idempotent_terminal": True}
        self._assert_cas(it, expected_revision, self._require_sha(expected_revision_sha256, "expected_iteration_revision_sha256"))
        for _ in range(20):
            state = it["state"]
            if state == "SESSION_BOUND":
                try:
                    self._precheck_session(it)
                except Exception as exc:
                    return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "PRECHECK_FAILED", "message": str(exc)})
                it = self._transition(it, "PRECHECK"); continue
            if state == "PRECHECK":
                try:
                    planned = self._plan_candidate(it)
                    checkpoint_id = self._checkpoint_operation_id(it["iteration_id"])
                    cp = self.revisions.create_checkpoint(it["workspace"], it["ea"], f"TIP-015 {it['iteration_id']}", checkpoint_id=checkpoint_id)
                except Exception as exc:
                    return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "CHECKPOINT_OR_PLAN_FAILED", "message": str(exc)})
                if cp["sha256"] != it["base_source_sha256"] or int(cp["bytes"]) != int(it["base_source_bytes"]):
                    return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "CHECKPOINT_BASE_MISMATCH"})
                it = self._transition(it, "CHECKPOINTED", checkpoint_id=cp["checkpoint_id"], planned_candidate_sha256=planned["sha256"], planned_candidate_bytes=int(planned["bytes"]), planned_mutation_evidence={"replacements": planned.get("replacements"), "newline_style": planned.get("newline_style"), "utf8_bom": planned.get("utf8_bom"), "checkpoint_idempotent_recovered": bool(cp.get("idempotent_recovered"))}); continue
            if state == "CHECKPOINTED":
                try:
                    mutated = self._mutate_source(it)
                except Exception as exc:
                    return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "MUTATION_FAILED", "message": str(exc)})
                it = self._transition(it, "MUTATED", candidate_source_sha256=mutated["sha256"], candidate_source_bytes=int(mutated["bytes"]), mutation_evidence={**{k: mutated.get(k) for k in ("before_sha256", "sha256", "bytes", "replacements", "atomic", "format_preserved", "newline_style", "utf8_bom")}, "idempotent_recovered": bool(mutated.get("idempotent_recovered"))}); continue
            if state == "MUTATED":
                try:
                    comp = self._compile_candidate(it)
                except Exception as exc:
                    it = self._transition(it, "COMPILE_FAILED", failure={"code": "COMPILE_EXCEPTION", "message": str(exc)})
                    return self._rollback(it, "FAILED_ROLLED_BACK", "COMPILE_EXCEPTION")
                if comp.get("status") != "PASSED":
                    it = self._transition(it, "COMPILE_FAILED", compile_evidence=comp, failure={"code": "COMPILE_FAILED"})
                    return self._rollback(it, "FAILED_ROLLED_BACK", "COMPILE_FAILED")
                it = self._transition(it, "COMPILED", compile_evidence=comp); continue
            if state == "COMPILED":
                operation_id = f"{it['iteration_id']}:TEST"
                it = self._transition(it, "TEST_PREPARED", test_operation_id=operation_id)
                self.faults.hit("TEST_AFTER_PREPARED", it["iteration_id"], context={"iteration_revision": it["iteration_revision"], "test_operation_id": operation_id}); continue
            if state == "TEST_PREPARED":
                req = self._candidate_request(it)
                try:
                    reserved = self.jobs.reserve_test(req, it["test_operation_id"])
                except Exception as exc:
                    return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "TEST_RESERVATION_FAILED", "message": str(exc)})
                it = self._transition(it, "TEST_RESERVED", job_id=reserved["job_id"], test_request_hash=reserved["request_hash"])
                self.faults.hit("TEST_AFTER_RESERVED", it["iteration_id"], context={"iteration_revision": it["iteration_revision"], "test_operation_id": it["test_operation_id"], "job_id": reserved["job_id"], "request_hash": reserved["request_hash"]}); continue
            if state == "TEST_RESERVED":
                try:
                    started = self.jobs.start_reserved_test(it["job_id"])
                except Exception as exc:
                    return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "TEST_SPAWN_RECONCILIATION_FAILED", "message": str(exc)})
                it = self._transition(it, "TEST_RUNNING", worker_pid=started.get("worker_pid")); return {**it, "job": self.jobs.get_job(it["job_id"])}
            if state == "TEST_RUNNING":
                job = self.jobs.get_job(it["job_id"])
                if job.get("state") not in JOB_FAILURE_STATES | {"PASSED", "ANOMALY"}:
                    return {**it, "job": job}
                if job.get("state") in JOB_FAILURE_STATES:
                    it = self._transition(it, "NATIVE_TEST_FAILED", failure={"code": "NATIVE_TEST_FAILED", "job_state": job.get("state")})
                    return self._rollback(it, "FAILED_ROLLED_BACK", "NATIVE_TEST_FAILED")
                result = self.jobs.read_result(it["job_id"])
                if result.get("status") not in {"PASSED", "ANOMALY"}:
                    it = self._transition(it, "NATIVE_TEST_FAILED", failure={"code": "RESULT_NOT_USABLE", "result_status": result.get("status")})
                    return self._rollback(it, "FAILED_ROLLED_BACK", "RESULT_NOT_USABLE")
                it = self._transition(it, "NATIVE_TESTED", candidate_result_status=result.get("status")); continue
            if state == "NATIVE_TESTED":
                req = self._candidate_request(it); validation = self.baselines.validate(self.sessions.get(it["project_id"]), req)
                if validation["status"] != "VALID":
                    return self._transition(it, "BASELINE_UNAVAILABLE", baseline_validation=validation, policy_result="FAIL_CLOSED")
                it = self._transition(it, "BASELINE_VALIDATED", baseline_validation={k: v for k, v in validation.items() if k not in {"result", "request"}}); continue
            if state == "BASELINE_VALIDATED":
                req = self._candidate_request(it); candidate = self.jobs.read_result(it["job_id"]); comparison = self.baselines.compare_candidate(self.sessions.get(it["project_id"]), req, candidate)
                if comparison.get("status") != "COMPARED":
                    return self._transition(it, "BASELINE_UNAVAILABLE", baseline_validation=comparison, policy_result="FAIL_CLOSED")
                it = self._transition(it, "BASELINE_COMPARED", baseline_comparison=comparison); continue
            if state == "BASELINE_COMPARED":
                return self._transition(it, "DECISION_PENDING", policy_result="NO_THRESHOLD_DEFINED_EXPLICIT_ACCEPT_REQUIRED")
            if state == "COMPILE_FAILED":
                return self._rollback(it, "FAILED_ROLLED_BACK", str((it.get("failure") or {}).get("code") or "COMPILE_FAILED"))
            if state == "NATIVE_TEST_FAILED":
                return self._rollback(it, "FAILED_ROLLED_BACK", str((it.get("failure") or {}).get("code") or "NATIVE_TEST_FAILED"))
            if state == "CANCEL_STOPPED":
                return self._rollback(it, "CANCELLED_ROLLED_BACK", "OWNER_CANCEL")
            if state == "ACCEPT_INTENT":
                return self._accept_reconcile(it)
            if state == "ROLLBACK_INTENT":
                rb = it.get("rollback") or {}; return self._rollback(it, str(rb.get("target_state") or "REJECTED_ROLLED_BACK"), str(rb.get("reason") or "REJECT"))
            if state == "CANCEL_INTENT":
                return self._cancel_reconcile(it)
            return it
        return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "ITERATION_TRANSITION_BUDGET_EXCEEDED"})

    def accept(self, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        it = self.store.load(iteration_id)
        if it["state"] == "ACCEPTED":
            return {**it, "idempotent_terminal": True}
        self._assert_cas(it, expected_revision, self._require_sha(expected_revision_sha256, "expected_iteration_revision_sha256"))
        if it["state"] == "ACCEPT_INTENT":
            return self._accept_reconcile(it)
        if it["state"] != "DECISION_PENDING":
            raise RuntimeError(f"ITERATION_NOT_ACCEPTABLE: {it['state']}")
        if (it.get("baseline_validation") or {}).get("status") not in {"VALID", None}:
            raise RuntimeError("BASELINE_UNAVAILABLE: acceptance forbidden")
        op = it.get("accept_operation_id") or f"{it['iteration_id']}:ACCEPT"
        it = self._transition(it, "ACCEPT_INTENT", accept_operation_id=op)
        return self._accept_reconcile(it)

    def reject(self, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        it = self.store.load(iteration_id)
        if it["state"] == "REJECTED_ROLLED_BACK":
            return {**it, "idempotent_terminal": True}
        self._assert_cas(it, expected_revision, self._require_sha(expected_revision_sha256, "expected_iteration_revision_sha256"))
        if it["state"] == "ROLLBACK_INTENT":
            rb = it.get("rollback") or {}
            if rb.get("target_state") != "REJECTED_ROLLED_BACK":
                raise RuntimeError(f"ITERATION_NOT_REJECTABLE: rollback target {rb.get('target_state')}")
            return self._rollback(it, "REJECTED_ROLLED_BACK", str(rb.get("reason") or "OWNER_REJECT"))
        if it["state"] not in {"DECISION_PENDING", "BASELINE_UNAVAILABLE", "POLICY_BLOCKED"}:
            raise RuntimeError(f"ITERATION_NOT_REJECTABLE: {it['state']}")
        return self._rollback(it, "REJECTED_ROLLED_BACK", "OWNER_REJECT")

    def _ensure_cancel_checkpoint(self, it: dict[str, Any]) -> dict[str, Any]:
        if it.get("checkpoint_id"):
            return it
        try:
            self._precheck_session(it)
            checkpoint_id = self._checkpoint_operation_id(it["iteration_id"])
            cp = self.revisions.create_checkpoint(it["workspace"], it["ea"], f"TIP-015 cancel {it['iteration_id']}", checkpoint_id=checkpoint_id)
        except Exception as exc:
            return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "CANCEL_CHECKPOINT_FAILED", "message": str(exc)})
        if cp["sha256"] != it["base_source_sha256"] or int(cp["bytes"]) != int(it["base_source_bytes"]):
            return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "CANCEL_CHECKPOINT_BASE_MISMATCH"})
        return self._transition(it, "CANCEL_INTENT", checkpoint_id=cp["checkpoint_id"], cancel_checkpoint={"sha256": cp["sha256"], "bytes": cp["bytes"], "idempotent_recovered": bool(cp.get("idempotent_recovered"))})

    def _cancel_reconcile(self, it: dict[str, Any]) -> dict[str, Any]:
        it = self._ensure_cancel_checkpoint(it)
        if it["state"] == "RECOVERY_REQUIRED":
            return it
        if it.get("job_id"):
            self.jobs.cancel_job(it["job_id"])
            proof = self.jobs.execution_stopped(it["job_id"])
            if not proof.get("stopped"):
                return self._transition(it, "RECOVERY_REQUIRED", failure={"code": "CANCEL_STOP_UNPROVEN", "proof": proof})
            settled = self.jobs.settle_cancelled(it["job_id"], proof)
            it = self._transition(it, "CANCEL_STOPPED", cancel_stop_proof={**proof, "settled_job_state": settled.get("state")})
        return self._rollback(it, "CANCELLED_ROLLED_BACK", "OWNER_CANCEL")

    def cancel(self, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        it = self.store.load(iteration_id)
        if it["state"] == "CANCELLED_ROLLED_BACK":
            return {**it, "idempotent_terminal": True}
        self._assert_cas(it, expected_revision, self._require_sha(expected_revision_sha256, "expected_iteration_revision_sha256"))
        if it["state"] in {"ACCEPTED", "REJECTED_ROLLED_BACK", "FAILED_ROLLED_BACK", "ACCEPT_INTENT", "ROLLBACK_INTENT"}:
            raise RuntimeError(f"ITERATION_NOT_CANCELLABLE: {it['state']}")
        if it["state"] == "RECOVERY_REQUIRED" and it.get("accept_operation_id"):
            raise RuntimeError("ITERATION_ACCEPT_RECONCILIATION_REQUIRED")
        if it["state"] != "CANCEL_INTENT":
            it = self._transition(it, "CANCEL_INTENT", cancel_operation_id=f"{it['iteration_id']}:CANCEL")
            self.faults.hit("CANCEL_AFTER_INTENT", it["iteration_id"], context={"iteration_revision": it["iteration_revision"], "cancel_operation_id": it["cancel_operation_id"], "job_id": it.get("job_id", "")})
        return self._cancel_reconcile(it)
