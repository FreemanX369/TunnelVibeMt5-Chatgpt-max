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
    def __init__(self, path: Path, timeout: float = 5.0, stale: float = 60.0):
        self.path = path; self.timeout = timeout; self.stale = stale; self.owned = False
    def __enter__(self):
        deadline = time.monotonic() + self.timeout; self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, json.dumps({"pid": os.getpid(), "at": _now()}).encode("utf-8")); os.fsync(fd)
                finally: os.close(fd)
                self.owned = True; return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink(missing_ok=True); continue
                except FileNotFoundError: continue
                if time.monotonic() >= deadline: raise RuntimeError("ITERATION_METADATA_BUSY")
                time.sleep(0.05)
    def __exit__(self, exc_type, exc, tb):
        if self.owned:
            try: self.path.unlink(missing_ok=True)
            except OSError: pass
        return False


class IterationStore:
    schema_version = "1.0"
    def __init__(self, root: Path):
        self.root = Path(root).resolve(); self.state_root = self.root / "state" / "iterations"; self.lock_root = self.state_root / "locks"; self.state_root.mkdir(parents=True, exist_ok=True); self.lock_root.mkdir(parents=True, exist_ok=True)
    @staticmethod
    def normalize_target(workspace: str, ea: str) -> str: return f"{str(workspace).strip().lower()}::{str(ea).replace('\\', '/').strip().lower()}"
    def _dir(self, iteration_id: str) -> Path:
        if not _ITERATION_ID_RE.fullmatch(str(iteration_id or "")): raise ValueError("Invalid iteration_id")
        p = (self.state_root / iteration_id).resolve()
        if p.parent != self.state_root: raise ValueError("Iteration path escapes state root")
        return p
    def _rev_path(self, iteration_id: str, revision_id: str) -> Path:
        if not _ITERATION_REV_RE.fullmatch(str(revision_id or "")): raise ValueError("Invalid iteration revision")
        return self._dir(iteration_id) / "revisions" / f"{revision_id}.json"
    def _pointer(self, iteration_id: str) -> Path: return self._dir(iteration_id) / "current.json"
    def _mutex(self, iteration_id: str) -> Path: return self._dir(iteration_id) / ".metadata.lock"
    def _target_lock(self, target: str) -> Path: return self.lock_root / f"{hashlib.sha256(target.encode('utf-8')).hexdigest()}.json"
    def load(self, iteration_id: str) -> dict[str, Any]:
        pointer = json.loads(self._pointer(iteration_id).read_text(encoding="utf-8")); revision_id = str(pointer.get("revision_id") or ""); path = self._rev_path(iteration_id, revision_id); raw = path.read_bytes(); actual = _sha(raw)
        if actual != pointer.get("revision_sha256"): raise ValueError("ITERATION_REVISION_INTEGRITY_FAILURE")
        data = json.loads(raw.decode("utf-8"))
        if data.get("schema_version") != self.schema_version or data.get("iteration_id") != iteration_id: raise ValueError("ITERATION_REVISION_METADATA_MISMATCH")
        return {**data, "iteration_revision_sha256": actual}
    def list(self) -> list[dict[str, Any]]:
        out=[]
        for p in sorted(self.state_root.glob("IT-*")):
            if not p.is_dir(): continue
            try:
                it=self.load(p.name); out.append({"iteration_id":it["iteration_id"],"project_id":it["project_id"],"workspace":it["workspace"],"ea":it["ea"],"state":it["state"],"iteration_revision":it["iteration_revision"],"iteration_revision_sha256":it["iteration_revision_sha256"],"updated_at_utc":it["updated_at_utc"]})
            except Exception as exc: out.append({"iteration_id":p.name,"state":"INVALID","error":str(exc)})
        return out
    def _owner_terminal(self, iteration_id: str) -> bool:
        try: return self.load(iteration_id).get("state") in TERMINAL_ITERATION_STATES
        except Exception: raise RuntimeError(f"ITERATION_LOCK_RECOVERY_REQUIRED: owner {iteration_id} cannot be verified")
    def acquire_target(self, iteration_id: str, workspace: str, ea: str) -> dict[str, Any]:
        target=self.normalize_target(workspace,ea); path=self._target_lock(target); record={"schema_version":"1.0","target":target,"iteration_id":iteration_id,"created_at_utc":_now()}
        while True:
            try: fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            except FileExistsError:
                try: existing=json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc: raise RuntimeError("ITERATION_LOCK_RECOVERY_REQUIRED: corrupt active lock") from exc
                owner=str(existing.get("iteration_id") or "")
                if existing.get("target") != target or not _ITERATION_ID_RE.fullmatch(owner): raise RuntimeError("ITERATION_LOCK_RECOVERY_REQUIRED: invalid active lock")
                if owner==iteration_id: return {**existing,"reused":True}
                if self._owner_terminal(owner): path.unlink(missing_ok=True); continue
                raise RuntimeError(f"ITERATION_ALREADY_ACTIVE: {owner}")
            else:
                try:
                    raw=(json.dumps(record,indent=2,sort_keys=True)+"\n").encode("utf-8"); os.write(fd,raw); os.fsync(fd)
                finally: os.close(fd)
                return {**record,"reused":False}
    def release_target(self, iteration_id: str, workspace: str, ea: str) -> dict[str, Any]:
        target=self.normalize_target(workspace,ea); path=self._target_lock(target)
        if not path.exists(): return {"released":False,"already_absent":True}
        try: existing=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: raise RuntimeError("ITERATION_LOCK_RECOVERY_REQUIRED: corrupt active lock") from exc
        if existing.get("iteration_id") != iteration_id: raise RuntimeError("ITERATION_LOCK_OWNERSHIP_CONFLICT")
        path.unlink(missing_ok=True); return {"released":True,"already_absent":False}
    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        iteration_id=payload["iteration_id"]; d=self._dir(iteration_id)
        if d.exists(): raise FileExistsError("ITERATION_ALREADY_EXISTS")
        d.mkdir(parents=True,exist_ok=False); (d/"revisions").mkdir(); now=_now(); revision={**payload,"schema_version":self.schema_version,"iteration_revision":"IR-000001","iteration_revision_number":1,"previous_iteration_revision_sha256":"","created_at_utc":now,"updated_at_utc":now}; sha=_atomic_json(self._rev_path(iteration_id,"IR-000001"),revision); _atomic_json(self._pointer(iteration_id),{"schema_version":self.schema_version,"iteration_id":iteration_id,"revision_id":"IR-000001","revision_sha256":sha,"updated_at_utc":now}); return {**revision,"iteration_revision_sha256":sha}
    def mutate(self, iteration_id: str, expected_revision: str, expected_sha256: str, changes: dict[str, Any]) -> dict[str, Any]:
        with _MutationMutex(self._mutex(iteration_id)):
            current=self.load(iteration_id)
            if current["iteration_revision"] != expected_revision or current["iteration_revision_sha256"] != expected_sha256: raise ValueError(f"ITERATION_VERSION_CONFLICT: expected {expected_revision}/{expected_sha256}, current {current['iteration_revision']}/{current['iteration_revision_sha256']}")
            number=int(current["iteration_revision_number"])+1; now=_now(); payload={k:v for k,v in current.items() if k!="iteration_revision_sha256"}; payload.update(changes); payload.update({"iteration_revision":f"IR-{number:06d}","iteration_revision_number":number,"previous_iteration_revision_sha256":current["iteration_revision_sha256"],"updated_at_utc":now}); next_path=self._rev_path(iteration_id,payload["iteration_revision"]); idempotent_recovered=False
            if next_path.exists():
                raw=next_path.read_bytes(); sha=_sha(raw)
                try: existing=json.loads(raw.decode("utf-8"))
                except Exception as exc: raise RuntimeError("ITERATION_REVISION_RECOVERY_REQUIRED: unreadable next revision") from exc
                comparable=dict(payload); comparable["updated_at_utc"]=existing.get("updated_at_utc")
                if existing != comparable: raise RuntimeError("ITERATION_REVISION_RECOVERY_REQUIRED: divergent immutable next revision")
                payload=existing; idempotent_recovered=True
            else: sha=_atomic_json(next_path,payload)
            _atomic_json(self._pointer(iteration_id),{"schema_version":self.schema_version,"iteration_id":iteration_id,"revision_id":payload["iteration_revision"],"revision_sha256":sha,"updated_at_utc":payload["updated_at_utc"]}); return {**payload,"iteration_revision_sha256":sha,"idempotent_recovered":idempotent_recovered}


class IterationManager:
    schema_version = "1.0"
    def __init__(self, root: Path):
        self.root=Path(root).resolve(); self.store=IterationStore(self.root); self.sessions=ProjectSessionManager(self.root); self.revisions=RevisionManager(self.root); self.workspace=WorkspaceManager(self.root); self.jobs=JobManager(self.root); self.baselines=BaselineJobValidator(self.root); self.faults=TIP015BFaultInjector(self.root)
    def _fixed_terminal(self) -> str:
        settings=load_settings(self.root); return str((settings.get("terminal_policy") or {}).get("alias") or "MT5-2")
    @staticmethod
    def _require_sha(value: str, field: str) -> str:
        v=str(value or "").strip().lower()
        if not _SHA_RE.fullmatch(v): raise ValueError(f"{field} must be exact SHA-256")
        return v
    @staticmethod
    def _cas(it: dict[str, Any]) -> tuple[str,str]: return it["iteration_revision"],it["iteration_revision_sha256"]
    def _transition(self,it:dict[str,Any],state:str,**extra:Any)->dict[str,Any]:
        rev,sha=self._cas(it); return self.store.mutate(it["iteration_id"],rev,sha,{"state":state,**extra})
    def _assert_cas(self,it,expected_revision,expected_sha):
        if it.get("state") in TERMINAL_ITERATION_STATES: return
        if it["iteration_revision"] != expected_revision or it["iteration_revision_sha256"] != expected_sha: raise ValueError(f"ITERATION_VERSION_CONFLICT: expected {expected_revision}/{expected_sha}, current {it['iteration_revision']}/{it['iteration_revision_sha256']}")
    def start(self, project_id: str, expected_session_revision: str, expected_session_revision_sha256: str, expected_source_sha256: str, expected_source_bytes: int, mutation: dict[str, Any], *, preset: str="smoke", set_file: str="", overrides: dict[str,Any]|None=None, timeout_seconds:int=0)->dict[str,Any]:
        session=self.sessions.get(project_id); session_sha=self._require_sha(expected_session_revision_sha256,"expected_session_revision_sha256"); source_sha=self._require_sha(expected_source_sha256,"expected_source_sha256")
        if session["revision_id"] != expected_session_revision or session["revision_sha256"] != session_sha: raise ValueError("PROJECT_SESSION_VERSION_CONFLICT: iteration binding is stale")
        resumed=self.sessions.resume(project_id)
        if not resumed.get("resume_safe"): raise RuntimeError(f"PROJECT_SESSION_NOT_RESUME_SAFE: {resumed.get('stale_reasons')}")
        if session["source_sha256"] != source_sha or int(session["source_bytes"]) != int(expected_source_bytes): raise ValueError("SOURCE_VERSION_CONFLICT: iteration source binding differs from project session")
        current=self.revisions.source_hash(session["workspace"],session["ea"])
        if current["sha256"] != source_sha or int(current["bytes"]) != int(expected_source_bytes): raise ValueError("SOURCE_VERSION_CONFLICT: runtime source differs from requested iteration base")
        kind=str((mutation or {}).get("kind") or "apply_patch")
        if kind not in {"apply_patch","write_source"}: raise ValueError("Unsupported mutation kind")
        if kind=="apply_patch" and not isinstance(mutation.get("replacements"),list): raise ValueError("apply_patch mutation requires replacements list")
        if kind=="write_source" and not isinstance(mutation.get("content"),str): raise ValueError("write_source mutation requires content string")
        timeout_seconds=int(timeout_seconds)
        if timeout_seconds<0: raise ValueError("timeout_seconds must be 0 (event-driven) or a positive number of seconds")
        if timeout_seconds>86400: raise ValueError("timeout_seconds cannot exceed 86400 when explicitly set")
        iteration_id=_new_iteration_id(); self.store.acquire_target(iteration_id,session["workspace"],session["ea"]); payload={"iteration_id":iteration_id,"project_id":project_id,"session_revision_id":session["revision_id"],"session_revision_sha256":session["revision_sha256"],"workspace":session["workspace"],"ea":session["ea"],"base_source_sha256":source_sha,"base_source_bytes":int(expected_source_bytes),"baseline_job_id":session.get("baseline_job_id",""),"state":"SESSION_BOUND","mutation":mutation,"preset":str(preset or "smoke"),"set_file":str(set_file or ""),"overrides":overrides or {},"timeout_seconds":timeout_seconds,"checkpoint_id":"","candidate_source_sha256":"","candidate_source_bytes":0,"compile_evidence":{},"test_operation_id":"","job_id":"","baseline_validation":{},"baseline_comparison":{},"policy_result":"NOT_EVALUATED","accept_operation_id":"","rollback":{},"failure":{}}
        try: return self.store.create(payload)
        except Exception:
            try: self.store.release_target(iteration_id,session["workspace"],session["ea"])
            except Exception: pass
            raise
    def get(self,iteration_id:str)->dict[str,Any]: return self.store.load(iteration_id)
    def list(self)->list[dict[str,Any]]: return self.store.list()
    def resume(self,iteration_id:str,expected_revision:str,expected_revision_sha256:str)->dict[str,Any]:
        it=self.store.load(iteration_id)
        if it["state"] in TERMINAL_ITERATION_STATES: return {**it,"idempotent_terminal":True}
        self._assert_cas(it,expected_revision,self._require_sha(expected_revision_sha256,"expected_iteration_revision_sha256")); return it
    def accept(self,iteration_id:str,expected_revision:str,expected_revision_sha256:str)->dict[str,Any]:
        it=self.store.load(iteration_id)
        if it["state"]=="ACCEPTED": return {**it,"idempotent_terminal":True}
        self._assert_cas(it,expected_revision,self._require_sha(expected_revision_sha256,"expected_iteration_revision_sha256")); raise RuntimeError(f"ITERATION_NOT_ACCEPTABLE: {it['state']}")
    def reject(self,iteration_id:str,expected_revision:str,expected_revision_sha256:str)->dict[str,Any]:
        it=self.store.load(iteration_id)
        if it["state"]=="REJECTED_ROLLED_BACK": return {**it,"idempotent_terminal":True}
        self._assert_cas(it,expected_revision,self._require_sha(expected_revision_sha256,"expected_iteration_revision_sha256")); raise RuntimeError(f"ITERATION_NOT_REJECTABLE: {it['state']}")
    def cancel(self,iteration_id:str,expected_revision:str,expected_revision_sha256:str)->dict[str,Any]:
        it=self.store.load(iteration_id)
        if it["state"]=="CANCELLED_ROLLED_BACK": return {**it,"idempotent_terminal":True}
        self._assert_cas(it,expected_revision,self._require_sha(expected_revision_sha256,"expected_iteration_revision_sha256")); raise RuntimeError(f"ITERATION_NOT_CANCELLABLE: {it['state']}")
