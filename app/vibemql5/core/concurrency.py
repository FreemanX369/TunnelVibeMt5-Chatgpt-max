from __future__ import annotations

import contextvars
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .jobs import _exclusive_file_lock, _pid_exists

_SCHEMA_VERSION = "1.0"
_CURRENT_ACTOR: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "vibemql5_current_actor", default=None
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".v-{uuid.uuid4().hex[:8]}.tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_client_info(value: Any) -> dict[str, str]:
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            value = None
    if not isinstance(value, dict):
        return {"name": "", "version": ""}
    return {
        "name": str(value.get("name") or "")[:120],
        "version": str(value.get("version") or "")[:80],
    }


def actor_from_mcp_context(ctx: Any, transport: str = "unknown") -> dict[str, Any]:
    """Return non-security request provenance from MCP Context.

    MCP stdio does not provide an authenticated ChatGPT account identity. We record only
    SDK-managed/request provenance that is safe for diagnostics and explicitly mark the
    attribution strength. Project/iteration ids provide the durable logical-workstream key.
    """
    request_context = getattr(ctx, "request_context", None)
    meta = getattr(request_context, "meta", None) or {}
    client_info = _safe_client_info(meta.get("io.modelcontextprotocol/clientInfo") if isinstance(meta, dict) else None)
    request_id = str(getattr(request_context, "request_id", "") or "")[:160]
    connection = getattr(ctx, "connection", None)
    protocol_version = str(
        getattr(connection, "protocol_version", "")
        or getattr(request_context, "protocol_version", "")
        or ""
    )[:80]
    session_id = str(getattr(ctx, "session_id", "") or "")[:160]
    seed = json.dumps(
        {
            "client": client_info,
            "session_id": session_id,
            "transport": str(transport or "unknown"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    client_key = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "mcp_request_context",
        "client_key": client_key,
        "client_info": client_info,
        "request_id": request_id,
        "session_id": session_id or None,
        "protocol_version": protocol_version,
        "transport": str(transport or "unknown"),
        "attribution_strength": "CONNECTION" if session_id else "REQUEST_WORKSTREAM_ONLY",
        "security_identity": False,
    }


def current_actor() -> dict[str, Any]:
    value = _CURRENT_ACTOR.get()
    if not value:
        return {
            "schema_version": _SCHEMA_VERSION,
            "source": "local_or_unattributed",
            "client_key": "local",
            "client_info": {"name": "", "version": ""},
            "request_id": "",
            "session_id": None,
            "protocol_version": "",
            "transport": "local",
            "attribution_strength": "LOCAL_ONLY",
            "security_identity": False,
        }
    return dict(value)


@contextmanager
def actor_scope(actor: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
    normalized = dict(actor or current_actor())
    token = _CURRENT_ACTOR.set(normalized)
    try:
        yield normalized
    finally:
        _CURRENT_ACTOR.reset(token)


class _QueuedFileLease:
    def __init__(
        self,
        root: Path,
        *,
        namespace: str,
        operation_id: str,
        kind: str,
        actor: dict[str, Any] | None,
        wait_seconds: float,
        lock_path: Path,
    ) -> None:
        self.root = Path(root)
        self.namespace = namespace
        self.operation_id = str(operation_id or "")
        self.kind = str(kind or namespace)
        self.actor = dict(actor or current_actor())
        self.wait_seconds = max(0.0, float(wait_seconds))
        self.lock_path = Path(lock_path)
        self.state_root = self.root / "state" / "concurrency"
        self.queue_root = self.state_root / f"{namespace}-waiters"
        self.sequence_path = self.state_root / f"{namespace}-sequence.json"
        self.sequence_lock = self.state_root / f".{namespace}-sequence.lock"
        self.token = uuid.uuid4().hex
        self.ticket_path: Path | None = None
        self.acquired_at = ""
        self.wait_elapsed_seconds = 0.0
        self.released = False

    def _owner_payload(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "namespace": self.namespace,
            "token": self.token,
            "pid": os.getpid(),
            "operation_id": self.operation_id,
            "kind": self.kind,
            "actor": self.actor,
            "acquired_at": self.acquired_at,
        }

    def _next_sequence(self) -> int:
        self.state_root.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(self.sequence_lock, timeout_seconds=max(2.0, min(self.wait_seconds, 30.0))):
            current = 0
            if self.sequence_path.is_file():
                try:
                    data = json.loads(self.sequence_path.read_text(encoding="utf-8"))
                    current = int(data.get("sequence") or 0)
                except Exception as exc:
                    raise RuntimeError(f"CONCURRENCY_{self.namespace.upper()}_SEQUENCE_CORRUPT") from exc
            nxt = current + 1
            _atomic_json(self.sequence_path, {
                "schema_version": _SCHEMA_VERSION,
                "namespace": self.namespace,
                "sequence": nxt,
                "updated_at": _now_iso(),
            })
            return nxt

    def _new_ticket(self) -> Path:
        self.queue_root.mkdir(parents=True, exist_ok=True)
        sequence = self._next_sequence()
        stamp = f"{sequence:020d}-{uuid.uuid4().hex}.json"
        path = self.queue_root / stamp
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "namespace": self.namespace,
            "ticket": stamp,
            "sequence": sequence,
            "token": self.token,
            "pid": os.getpid(),
            "operation_id": self.operation_id,
            "kind": self.kind,
            "actor": self.actor,
            "queued_at": _now_iso(),
        }
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, _json_bytes(payload))
            os.fsync(fd)
        finally:
            os.close(fd)
        return path

    def _cleanup_dead_waiters(self) -> None:
        if not self.queue_root.is_dir():
            return
        for path in self.queue_root.glob("*.json"):
            if self.ticket_path is not None and path == self.ticket_path:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                pid = int(data.get("pid") or 0)
            except Exception:
                continue
            if pid > 0 and not _pid_exists(pid):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _first_ticket(self) -> Path | None:
        self._cleanup_dead_waiters()
        items = sorted(self.queue_root.glob("*.json")) if self.queue_root.is_dir() else []
        return items[0] if items else None

    def _cleanup_stale_lock(self) -> bool:
        if not self.lock_path.exists():
            return True
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
        except Exception:
            return False
        if pid > 0 and not _pid_exists(pid):
            try:
                self.lock_path.unlink(missing_ok=True)
                return True
            except OSError:
                return False
        return False

    def acquire(self) -> "_QueuedFileLease":
        start = time.monotonic()
        deadline = start + self.wait_seconds
        self.ticket_path = self._new_ticket()
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            while True:
                first = self._first_ticket()
                if first == self.ticket_path:
                    try:
                        fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    except FileExistsError:
                        self._cleanup_stale_lock()
                    else:
                        self.acquired_at = _now_iso()
                        payload = _json_bytes(self._owner_payload())
                        try:
                            os.write(fd, payload)
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                        self.wait_elapsed_seconds = round(time.monotonic() - start, 6)
                        try:
                            self.ticket_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                        self.ticket_path = None
                        return self
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"CONCURRENCY_{self.namespace.upper()}_WAIT_TIMEOUT: operation={self.operation_id}"
                    )
                time.sleep(0.05)
        except Exception:
            if self.ticket_path is not None:
                try:
                    self.ticket_path.unlink(missing_ok=True)
                except OSError:
                    pass
                self.ticket_path = None
            raise

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        try:
            if self.lock_path.is_file():
                try:
                    data = json.loads(self.lock_path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
                if data.get("token") == self.token:
                    self.lock_path.unlink(missing_ok=True)
        finally:
            if self.ticket_path is not None:
                try:
                    self.ticket_path.unlink(missing_ok=True)
                except OSError:
                    pass
                self.ticket_path = None

    def unlink(self, missing_ok: bool = True) -> None:
        self.release()

    def exists(self) -> bool:
        return self.lock_path.exists()

    def __fspath__(self) -> str:
        return os.fspath(self.lock_path)

    def __enter__(self) -> "_QueuedFileLease":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "namespace": self.namespace,
            "operation_id": self.operation_id,
            "kind": self.kind,
            "token": self.token,
            "pid": os.getpid(),
            "acquired_at": self.acquired_at,
            "wait_elapsed_seconds": self.wait_elapsed_seconds,
            "actor": self.actor,
        }


def acquire_native_execution(
    root: Path,
    operation_id: str,
    *,
    kind: str,
    actor: dict[str, Any] | None = None,
    wait_seconds: float = 300.0,
) -> _QueuedFileLease:
    return _QueuedFileLease(
        Path(root),
        namespace="native",
        operation_id=operation_id,
        kind=kind,
        actor=actor,
        wait_seconds=wait_seconds,
        lock_path=Path(root) / "runs" / ".active.lock",
    ).acquire()


class ConcurrencyManager:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.state_root = self.root / "state" / "concurrency"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.state_root / "audit.jsonl"
        self.audit_lock = self.state_root / ".audit.lock"
        self.project_actor_root = self.state_root / "project-actors"
        self.iteration_actor_root = self.state_root / "iteration-actors"

    def _audit(self, event: str, **payload: Any) -> None:
        record = {
            "schema_version": _SCHEMA_VERSION,
            "at": _now_iso(),
            "event": str(event),
            **payload,
        }
        try:
            with _exclusive_file_lock(self.audit_lock, timeout_seconds=2.0):
                self.audit_path.parent.mkdir(parents=True, exist_ok=True)
                with self.audit_path.open("ab") as fh:
                    fh.write(_json_bytes(record))
                    fh.flush()
                    os.fsync(fh.fileno())
        except Exception:
            pass

    @contextmanager
    def mutation(
        self,
        operation: str,
        *,
        resource: str = "",
        project_id: str = "",
        wait_seconds: float = 30.0,
    ) -> Iterator[_QueuedFileLease]:
        actor = current_actor()
        op_id = f"MUT-{uuid.uuid4().hex[:16].upper()}"
        lease = _QueuedFileLease(
            self.root,
            namespace="mutation",
            operation_id=op_id,
            kind=operation,
            actor=actor,
            wait_seconds=wait_seconds,
            lock_path=self.state_root / "mutation.lock",
        )
        self._audit("MUTATION_WAIT", operation=operation, operation_id=op_id, resource=resource, project_id=project_id, actor=actor)
        try:
            lease.acquire()
            self._audit("MUTATION_ACQUIRED", operation=operation, operation_id=op_id, resource=resource, project_id=project_id, lease=lease.to_dict())
            yield lease
        except Exception as exc:
            self._audit("MUTATION_FAILED", operation=operation, operation_id=op_id, resource=resource, project_id=project_id, error_code=type(exc).__name__, error=str(exc)[:500], actor=actor)
            raise
        else:
            self._audit("MUTATION_COMPLETED", operation=operation, operation_id=op_id, resource=resource, project_id=project_id, actor=actor)
        finally:
            lease.release()

    @contextmanager
    def native_execution(
        self,
        operation_id: str,
        *,
        kind: str,
        wait_seconds: float = 300.0,
    ) -> Iterator[_QueuedFileLease]:
        actor = current_actor()
        self._audit("NATIVE_WAIT", operation_id=operation_id, kind=kind, actor=actor)
        lease = acquire_native_execution(
            self.root, operation_id, kind=kind, actor=actor, wait_seconds=wait_seconds
        )
        try:
            self._audit("NATIVE_ACQUIRED", operation_id=operation_id, kind=kind, lease=lease.to_dict())
            yield lease
        except Exception as exc:
            self._audit("NATIVE_FAILED", operation_id=operation_id, kind=kind, error_code=type(exc).__name__, error=str(exc)[:500], actor=actor)
            raise
        else:
            self._audit("NATIVE_COMPLETED", operation_id=operation_id, kind=kind, actor=actor)
        finally:
            lease.release()

    @staticmethod
    def _binding_name(value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest() + ".json"

    def note_project_actor(self, project_id: str, actor: dict[str, Any] | None = None) -> None:
        if not project_id:
            return
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "project_id": project_id,
            "actor": dict(actor or current_actor()),
            "observed_at": _now_iso(),
        }
        _atomic_json(self.project_actor_root / self._binding_name(project_id), payload)

    def note_iteration_actor(self, iteration_id: str, actor: dict[str, Any] | None = None) -> None:
        if not iteration_id:
            return
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "iteration_id": iteration_id,
            "actor": dict(actor or current_actor()),
            "observed_at": _now_iso(),
        }
        _atomic_json(self.iteration_actor_root / self._binding_name(iteration_id), payload)

    def iteration_actor(self, iteration_id: str) -> dict[str, Any] | None:
        path = self.iteration_actor_root / self._binding_name(iteration_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            actor = value.get("actor")
            return dict(actor) if isinstance(actor, dict) else None
        except Exception:
            return None

    @staticmethod
    def _read_lock(path: Path) -> dict[str, Any] | None:
        try:
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            return {**data, "pid_alive": bool(pid > 0 and _pid_exists(pid))}
        except Exception as exc:
            return {"status": "INVALID", "path": str(path), "error": str(exc)[:300]}

    @staticmethod
    def _waiter_count(path: Path) -> int:
        try:
            return sum(1 for p in path.glob("*.json") if p.is_file()) if path.is_dir() else 0
        except Exception:
            return 0

    def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            if not self.audit_path.is_file():
                return []
            lines = self.audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
            out = []
            for line in lines[-max(1, min(int(limit), 100)):]:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        out.append(item)
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def status(self, *, include_recent: bool = False) -> dict[str, Any]:
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "mode": "MULTI_CLIENT_SERIALIZED",
            "tool_surface_preserved": True,
            "source_mutation_parallelism": 1,
            "native_mt5_parallelism": 1,
            "mutation_lock": self._read_lock(self.state_root / "mutation.lock"),
            "mutation_waiters": self._waiter_count(self.state_root / "mutation-waiters"),
            "native_lock": self._read_lock(self.root / "runs" / ".active.lock"),
            "native_waiters": self._waiter_count(self.state_root / "native-waiters"),
            "attribution": {
                "model": "MCP_REQUEST_PLUS_PROJECT_ITERATION_WORKSTREAM",
                "authenticated_account_identity": False,
                "note": "stdio tunnel does not expose a security-grade ChatGPT account id",
            },
        }
        if include_recent:
            payload["recent_events"] = self.recent_events(20)
        return payload
