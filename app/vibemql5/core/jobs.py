from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import default_root
from ..errors import InvalidStateTransition
from ..models.types import TERMINAL_STATES
from .artifacts import ArtifactManager

_WORKER_PROCS: list[subprocess.Popen] = []
_JOB_ID_RE = re.compile(r"^BT-[0-9]{8}-[0-9]{6}-[A-F0-9]{6}$")

_ALLOWED = {
    "QUEUED": {"RESOURCE_CHECK", "CANCELLED"},
    "RESOURCE_CHECK": {"COMPILING", "RESOURCE_LIMIT", "CANCELLED"},
    "COMPILING": {"DEPLOYING", "FAILED", "CANCELLED"},
    "DEPLOYING": {"TESTING", "FAILED", "CANCELLED"},
    "TESTING": {"PARSING", "FAILED", "TIMEOUT", "CANCELLED", "INTERRUPTED"},
    "PARSING": {"EVALUATING", "FAILED"},
    "EVALUATING": {"PASSED", "ANOMALY", "FAILED"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_job_id() -> str:
    return "BT-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    data = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(8):
            try:
                os.replace(tmp, path)
                break
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if winerror not in {5, 32} or attempt == 7:
                    raise
                time.sleep(0.01 * (2 ** attempt))
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _read_json_object(path: Path, *, attempts: int = 8, retry_decode: bool = False) -> dict[str, Any]:
    count = max(1, int(attempts))
    for attempt in range(count):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object: {path}")
            return value
        except json.JSONDecodeError:
            if not retry_decode or attempt == count - 1:
                raise
        except PermissionError:
            if attempt == count - 1:
                raise
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if winerror not in {5, 32} or attempt == count - 1:
                raise
        time.sleep(0.01 * (2 ** attempt))
    raise RuntimeError(f"JSON_READ_RETRY_EXHAUSTED: {path}")


def _publish_json_exclusive(path: Path, value: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.publish.tmp")
    data = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    try:
        with tmp.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(8):
            try:
                os.link(tmp, path)
                return True
            except FileExistsError:
                return False
            except OSError as exc:
                winerror = getattr(exc, "winerror", None)
                if winerror not in {5, 32} or attempt == 7:
                    raise
                time.sleep(0.01 * (2 ** attempt))
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def _exclusive_file_lock(path: Path, timeout_seconds: float = 15.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open("a+b")
    try:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"\0")
            f.flush()
        f.seek(0)
        deadline = time.monotonic() + float(timeout_seconds)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"JOB_METADATA_LOCK_TIMEOUT: {path}")
                    time.sleep(0.01)
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            while True:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"JOB_METADATA_LOCK_TIMEOUT: {path}")
                    time.sleep(0.01)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()


def _pid_exists(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_bool
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            WAIT_OBJECT_0 = 0x00000000
            WAIT_TIMEOUT = 0x00000102
            ERROR_INVALID_PARAMETER = 87
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, int(pid)
            )
            if not handle:
                return ctypes.get_last_error() != ERROR_INVALID_PARAMETER
            try:
                wait = int(kernel32.WaitForSingleObject(handle, 0))
                if wait == WAIT_OBJECT_0:
                    return False
                if wait == WAIT_TIMEOUT:
                    return True
                return True
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _process_identity(pid: int) -> dict[str, Any] | None:
    if not _pid_exists(pid):
        return None
    if os.name == "nt":
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\";"
            "if($p){[pscustomobject]@{pid=[int]$p.ProcessId;creation_date=[string]$p.CreationDate;"
            "executable=[string]$p.ExecutablePath;command_line=[string]$p.CommandLine}|ConvertTo-Json -Compress}"
        )
        try:
            cp = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=5, check=False,
            )
            raw = cp.stdout.strip()
            if raw:
                value = json.loads(raw)
                if isinstance(value, dict):
                    return value
        except Exception:
            return None
        return None
    proc = Path("/proc") / str(int(pid))
    try:
        stat = (proc / "stat").read_text(encoding="utf-8", errors="replace").split()
        start_ticks = stat[21] if len(stat) > 21 else ""
        cmdline = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        executable = str((proc / "exe").resolve())
        return {"pid": int(pid), "start_ticks": start_ticks, "executable": executable, "command_line": cmdline}
    except Exception:
        return None


def _same_process_identity(expected: dict[str, Any] | None, current: dict[str, Any] | None) -> bool:
    if not expected or not current:
        return False
    try:
        if int(expected.get("pid") or 0) != int(current.get("pid") or 0):
            return False
    except Exception:
        return False
    if os.name == "nt":
        ecd = str(expected.get("creation_date") or "")
        ccd = str(current.get("creation_date") or "")
        if not ecd or not ccd or ecd != ccd:
            return False
    else:
        est = str(expected.get("start_ticks") or "")
        cst = str(current.get("start_ticks") or "")
        if not est or not cst or est != cst:
            return False
    eexe = str(expected.get("executable") or "").lower()
    cexe = str(current.get("executable") or "").lower()
    if eexe and cexe and eexe != cexe:
        return False
    return True


def _command_binds_job(identity: dict[str, Any] | None, job_id: str, role: str) -> bool:
    if not identity:
        return False
    cmd = str(identity.get("command_line") or "")
    exe = Path(str(identity.get("executable") or "")).name.lower()
    if role == "worker":
        return job_id in cmd and "vibemql5.worker" in cmd
    if role == "terminal":
        return job_id in cmd and exe in {"terminal64.exe", "terminal.exe"}
    return False


def _discover_worker_pids(job_id: str) -> list[int]:
    if not _JOB_ID_RE.fullmatch(job_id or ""):
        return []
    found: set[int] = set()
    if os.name == "nt":
        ps = (
            "$ErrorActionPreference='SilentlyContinue';"
            "Get-CimInstance Win32_Process | Where-Object {"
            "($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and "
            "$_.CommandLine -and $_.CommandLine -match 'vibemql5\\.worker' -and "
            f"$_.CommandLine -match '--job-id\\s+{job_id}'"
            "} | Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress"
        )
        try:
            cp = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=5, check=False,
            )
            raw = cp.stdout.strip()
            if raw:
                value = json.loads(raw)
                items = value if isinstance(value, list) else [value]
                for item in items:
                    try:
                        found.add(int(item))
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        proc_root = Path("/proc")
        if proc_root.is_dir():
            for child in proc_root.iterdir():
                if not child.name.isdigit():
                    continue
                try:
                    cmdline = (child / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
                    if "vibemql5.worker" in cmdline and "--job-id" in cmdline and job_id in cmdline:
                        found.add(int(child.name))
                except Exception:
                    continue
    return sorted(pid for pid in found if _pid_exists(pid))


class JobStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.artifacts = ArtifactManager(self.root)
        self.operation_root = self.root / "state" / "job-operations"
        self.operation_root.mkdir(parents=True, exist_ok=True)

    def path(self, job_id: str) -> Path:
        return self.artifacts.run_dir(job_id) / "job.json"

    def _operation_path(self, operation_id: str) -> Path:
        digest = hashlib.sha256(str(operation_id).encode("utf-8")).hexdigest()
        return self.operation_root / f"{digest}.json"

    def create(self, request: dict) -> dict:
        job_id = new_job_id()
        return self.create_reserved(job_id, request)

    def _reserved_record(self, job_id: str, request: dict, operation_id: str = "", request_hash: str = "") -> dict:
        if not _JOB_ID_RE.fullmatch(job_id or ""):
            raise ValueError("Invalid job id")
        now = now_iso()
        return {
            "job_id": job_id,
            "state": "QUEUED",
            "created_at": now,
            "updated_at": now,
            "retry_count": 0,
            "pinned": False,
            "request": request,
            "request_hash": request_hash or _sha256_json(request),
            "operation_id": operation_id or "",
            "processes": {},
            "cancel_requested": False,
            "spawn_requested": False,
            "event_seq": 0,
            "events": [],
        }

    def create_reserved(self, job_id: str, request: dict, operation_id: str = "", request_hash: str = "") -> dict:
        job = self._reserved_record(job_id, request, operation_id, request_hash)
        self.save(job)
        self.artifacts.write_json(job_id, "request.json", request)
        return job

    def reserve(self, request: dict, operation_id: str) -> dict:
        operation = str(operation_id or "").strip()
        if not operation:
            raise ValueError("operation_id is required for idempotent job reservation")
        request_hash = _sha256_json(request)
        op_path = self._operation_path(operation)

        def materialize(record: dict[str, Any], *, reserved: bool, recovered: bool) -> dict:
            if record.get("operation_id") != operation:
                raise ValueError("JOB_OPERATION_INDEX_INTEGRITY_FAILURE")
            if record.get("request_hash") != request_hash:
                raise ValueError("IDEMPOTENCY_KEY_CONFLICT: same operation_id has a different request")
            job_id = str(record.get("job_id") or "")
            if not _JOB_ID_RE.fullmatch(job_id):
                raise ValueError("JOB_OPERATION_INDEX_INTEGRITY_FAILURE")
            job_path = self.path(job_id)
            with _exclusive_file_lock(self._lock_path(job_id)):
                if job_path.is_file():
                    job = self._load_unlocked(job_id)
                    if job.get("operation_id") != operation or job.get("request_hash") != request_hash:
                        raise ValueError("JOB_OPERATION_BINDING_INTEGRITY_FAILURE")
                else:
                    job = self._reserved_record(job_id, request, operation, request_hash)
                    self._save_unlocked(job)
                    self.artifacts.write_json(job_id, "request.json", request)
            return {"job": job, "reserved": reserved, "recovered": recovered, "operation": record}

        if op_path.is_file():
            try:
                record = _read_json_object(op_path, retry_decode=True)
            except Exception as exc:
                raise ValueError("JOB_OPERATION_INDEX_INTEGRITY_FAILURE") from exc
            return materialize(record, reserved=False, recovered=True)

        job_id = new_job_id()
        record = {
            "schema_version": "1.0",
            "operation_id": operation,
            "request_hash": request_hash,
            "job_id": job_id,
            "reserved_at": now_iso(),
        }
        try:
            won = _publish_json_exclusive(op_path, record)
        except Exception as exc:
            raise ValueError("JOB_OPERATION_INDEX_PUBLISH_FAILURE") from exc
        if not won:
            try:
                winner = _read_json_object(op_path, retry_decode=True)
            except Exception as exc:
                raise ValueError("JOB_OPERATION_INDEX_INTEGRITY_FAILURE") from exc
            return materialize(winner, reserved=False, recovered=True)
        return materialize(record, reserved=True, recovered=False)

    def _lock_path(self, job_id: str) -> Path:
        return self.artifacts.run_dir(job_id) / ".job.lock"

    def _load_unlocked(self, job_id: str) -> dict:
        return _read_json_object(self.path(job_id))

    def _save_unlocked(self, job: dict) -> dict:
        job["updated_at"] = now_iso()
        _atomic_write_json(self.path(job["job_id"]), job)
        return job

    def load(self, job_id: str) -> dict:
        with _exclusive_file_lock(self._lock_path(job_id)):
            return self._load_unlocked(job_id)

    def save(self, job: dict) -> None:
        with _exclusive_file_lock(self._lock_path(job["job_id"])):
            self._save_unlocked(job)

    def mutate(self, job_id: str, fn) -> dict:
        with _exclusive_file_lock(self._lock_path(job_id)):
            job = self._load_unlocked(job_id)
            fn(job)
            return self._save_unlocked(job)

    def update_fields(self, job_id: str, **fields: Any) -> dict:
        if "state" in fields:
            raise ValueError("state updates must use transition/force_terminal")
        return self.mutate(job_id, lambda job: job.update(fields))

    def publish_event(self, job_id: str, kind: str, payload: dict[str, Any] | None = None) -> dict:
        kind = str(kind or "").strip().upper()
        if not kind:
            raise ValueError("event kind is required")
        payload = dict(payload or {})
        def apply(job: dict) -> None:
            seq = int(job.get("event_seq") or 0) + 1
            event = {"seq": seq, "kind": kind, "at": now_iso(), "payload": payload}
            events = list(job.get("events") or [])
            events.append(event)
            job["event_seq"] = seq
            job["last_event"] = event
            job["events"] = events[-200:]
        return self.mutate(job_id, apply)

    def transition(self, job: dict, state: str) -> dict:
        job_id = str(job["job_id"])
        with _exclusive_file_lock(self._lock_path(job_id)):
            current = self._load_unlocked(job_id)
            old = current["state"]
            if old in TERMINAL_STATES:
                raise InvalidStateTransition(f"Terminal job cannot transition: {old} -> {state}")
            if state not in _ALLOWED.get(old, set()):
                raise InvalidStateTransition(f"Invalid transition: {old} -> {state}")
            current["state"] = state
            self._save_unlocked(current)
        job.clear()
        job.update(current)
        return job

    def force_terminal(self, job_id: str, state: str, **fields: Any) -> dict:
        if state not in TERMINAL_STATES:
            raise ValueError(f"Not a terminal job state: {state}")
        def apply(job: dict) -> None:
            if job.get("state") not in TERMINAL_STATES:
                job["state"] = state
            job.update(fields)
        return self.mutate(job_id, apply)

    def set_process(self, job: dict, name: str, pid: int | None) -> None:
        job_id = str(job["job_id"])
        def apply(current: dict) -> None:
            processes = current.setdefault("processes", {})
            if pid is None:
                processes.pop(name, None)
            else:
                processes[name] = {
                    "pid": pid,
                    "set_at": now_iso(),
                    "identity": _process_identity(int(pid)),
                }
        updated = self.mutate(job_id, apply)
        job.clear()
        job.update(updated)


class JobManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.store = JobStore(self.root)

    def reserve_test(self, request: dict, operation_id: str) -> dict:
        outcome = self.store.reserve(request, operation_id)
        job = outcome["job"]
        return {
            "job_id": job["job_id"],
            "state": job["state"],
            "operation_id": operation_id,
            "request_hash": job.get("request_hash"),
            "reserved": outcome["reserved"],
            "recovered": outcome["recovered"],
        }

    def _spawn_worker(self, job: dict) -> dict:
        cmd = [sys.executable, "-m", "vibemql5.worker", "--root", str(self.root), "--job-id", job["job_id"]]
        env = os.environ.copy()
        app_dir = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = app_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        kwargs: dict[str, Any] = {
            "cwd": str(self.root),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        global _WORKER_PROCS
        _WORKER_PROCS[:] = [p for p in _WORKER_PROCS if p.poll() is None]
        proc = subprocess.Popen(cmd, **kwargs)
        _WORKER_PROCS.append(proc)
        return {"pid": proc.pid}

    def start_reserved_test(self, job_id: str) -> dict:
        job = self.store.load(job_id)
        if job["state"] in TERMINAL_STATES or job["state"] != "QUEUED":
            return {
                "job_id": job_id,
                "state": job["state"],
                "worker_pid": job.get("worker_pid"),
                "recovered": True,
                "spawned": False,
            }

        known_pid = int(job.get("worker_pid") or 0)
        if known_pid and _pid_exists(known_pid):
            current_identity = _process_identity(known_pid)
            expected_identity = job.get("worker_identity")
            exact_known = False
            if expected_identity:
                exact_known = _same_process_identity(expected_identity, current_identity) and _command_binds_job(current_identity, job_id, "worker")
            else:
                exact_known = _command_binds_job(current_identity, job_id, "worker")
            if exact_known:
                return {"job_id": job_id, "state": job["state"], "worker_pid": known_pid, "recovered": True, "spawned": False}

        discovered = _discover_worker_pids(job_id)
        if len(discovered) > 1:
            self.store.update_fields(job_id, worker_reconciliation_error={"code": "DUPLICATE_WORKERS_DETECTED", "pids": discovered})
            raise RuntimeError(f"DUPLICATE_WORKERS_DETECTED: {job_id}: {discovered}")
        if len(discovered) == 1:
            self.store.update_fields(job_id, worker_pid=discovered[0], spawn_recovered_at=now_iso())
            return {"job_id": job_id, "state": job["state"], "worker_pid": discovered[0], "recovered": True, "spawned": False}

        if job.get("spawn_requested"):
            raise RuntimeError("JOB_SPAWN_RECONCILIATION_REQUIRED: spawn intent exists but exact worker is not observable")

        claim_nonce = uuid.uuid4().hex
        def claim_spawn(current: dict) -> None:
            if current.get("state") != "QUEUED":
                raise RuntimeError(f"JOB_NOT_SPAWNABLE: {current.get('state')}")
            if current.get("spawn_requested"):
                raise RuntimeError("JOB_SPAWN_RECONCILIATION_REQUIRED: spawn intent already exists")
            current["spawn_requested"] = True
            current["spawn_requested_at"] = now_iso()
            current["spawn_nonce"] = claim_nonce
        job = self.store.mutate(job_id, claim_spawn)
        spawned = self._spawn_worker(job)
        self.store.update_fields(
            job_id,
            worker_pid=int(spawned["pid"]),
            worker_identity=_process_identity(int(spawned["pid"])),
            spawn_ack_at=now_iso(),
        )
        return {"job_id": job_id, "state": job["state"], "worker_pid": spawned["pid"], "recovered": False, "spawned": True}

    def launch_test(self, request: dict, operation_id: str = "") -> dict:
        if operation_id:
            reserved = self.reserve_test(request, operation_id)
            started = self.start_reserved_test(reserved["job_id"])
            return {**reserved, **started}
        job = self.store.create(request)
        started = self.start_reserved_test(job["job_id"])
        return started

    def get_job(self, job_id: str, wait_seconds: float = 0, after_event_seq: int = -1) -> dict:
        wait = max(0.0, min(float(wait_seconds or 0), 55.0))
        baseline = int(after_event_seq)
        deadline = time.monotonic() + wait
        while True:
            job = self._settle_cancel_if_stopped(job_id)
            seq = int(job.get("event_seq") or 0)
            if job.get("state") in TERMINAL_STATES or (baseline >= 0 and seq > baseline) or wait <= 0:
                return job
            if baseline < 0:
                baseline = seq
            if time.monotonic() >= deadline:
                return job
            time.sleep(0.25)

    def terminate_role_process(self, job_id: str, role: str, wait_seconds: float = 10.0) -> dict[str, Any]:
        job = self.store.load(job_id)
        data = dict((job.get("processes") or {}).get(role) or {})
        try:
            pid = int(data.get("pid") or 0)
        except Exception:
            pid = 0
        if pid <= 0:
            return {"role": role, "attempted": False, "stopped": True, "reason": "NO_PID"}
        current = _process_identity(pid)
        expected = data.get("identity")
        identity_ok = bool(expected and _same_process_identity(expected, current))
        binding_ok = _command_binds_job(current, job_id, role)
        if not identity_ok and not binding_ok:
            return {"role": role, "pid": pid, "attempted": False, "stopped": current is None, "reason": "PID_NOT_BOUND_TO_JOB"}
        attempted = False
        if current is not None:
            attempted = True
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + max(0.5, float(wait_seconds))
        while time.monotonic() < deadline and _pid_exists(pid):
            time.sleep(0.1)
        stopped = not _pid_exists(pid)
        if stopped:
            try:
                self.store.set_process(self.store.load(job_id), role, None)
            except Exception:
                pass
        return {"role": role, "pid": pid, "attempted": attempted, "stopped": stopped, "reason": "STOPPED" if stopped else "STILL_RUNNING"}

    def _process_reconciliation(self, job_id: str, job: dict) -> dict[str, Any]:
        exact_live: set[int] = set()
        exact_roles: dict[int, set[str]] = {}
        unverified_live: list[dict[str, Any]] = []
        stale_or_reused: list[dict[str, Any]] = []

        def add_exact(role: str, pid: int) -> None:
            exact_live.add(int(pid))
            exact_roles.setdefault(int(pid), set()).add(str(role))

        discovered_workers = set(_discover_worker_pids(job_id))
        for pid in discovered_workers:
            add_exact("worker", pid)

        try:
            worker_pid = int(job.get("worker_pid") or 0)
        except Exception:
            worker_pid = 0
        if worker_pid > 0 and worker_pid not in discovered_workers:
            current = _process_identity(worker_pid)
            if current is not None:
                expected = job.get("worker_identity")
                if _same_process_identity(expected, current) and _command_binds_job(current, job_id, "worker"):
                    add_exact("worker", worker_pid)
                else:
                    stale_or_reused.append({"role": "worker", "pid": worker_pid, "reason": "PID_NOT_BOUND_TO_JOB"})
            elif _pid_exists(worker_pid):
                unverified_live.append({"role": "worker", "pid": worker_pid, "reason": "PROCESS_IDENTITY_UNAVAILABLE"})

        for role, data in dict(job.get("processes") or {}).items():
            try:
                pid = int((data or {}).get("pid") or 0)
            except Exception:
                continue
            if pid <= 0:
                continue
            current = _process_identity(pid)
            if current is None:
                if _pid_exists(pid):
                    unverified_live.append({"role": str(role), "pid": pid, "reason": "PROCESS_IDENTITY_UNAVAILABLE"})
                continue
            expected = (data or {}).get("identity")
            if expected:
                if _same_process_identity(expected, current):
                    add_exact(str(role), pid)
                else:
                    stale_or_reused.append({"role": str(role), "pid": pid, "reason": "PID_IDENTITY_CHANGED"})
                continue
            if _command_binds_job(current, job_id, str(role)):
                add_exact(str(role), pid)
            elif str(role) == "terminal":
                stale_or_reused.append({"role": str(role), "pid": pid, "reason": "PID_NOT_BOUND_TO_JOB"})
            else:
                unverified_live.append({"role": str(role), "pid": pid, "reason": "LEGACY_PROCESS_IDENTITY_UNAVAILABLE"})

        return {
            "exact_live_pids": sorted(exact_live),
            "exact_live_processes": [
                {"pid": pid, "roles": sorted(exact_roles.get(pid) or [])}
                for pid in sorted(exact_live)
            ],
            "unverified_live_processes": unverified_live,
            "stale_or_reused_pids": stale_or_reused,
        }

    def _cancel_restore_requirement(self, job_id: str) -> dict[str, Any]:
        artifacts = ArtifactManager(self.root)
        handoff = artifacts.read_phase_receipt(job_id, "handoff")
        if not handoff:
            return {"required": False, "complete": True, "reason": "NO_HANDOFF"}
        evidence = dict(handoff.get("evidence") or {})
        if not evidence.get("was_running"):
            return {"required": False, "complete": True, "reason": "PRIOR_TERMINAL_STOPPED", "handoff": evidence}
        cleanup = artifacts.read_phase_receipt(job_id, "cleanup")
        cleanup_evidence = dict((cleanup or {}).get("evidence") or {})
        if (cleanup or {}).get("status") == "PASSED" and cleanup_evidence.get("reconnected"):
            return {
                "required": True, "complete": True, "reason": "WORKER_CLEANUP_RECONNECTED",
                "handoff": evidence, "cleanup": cleanup_evidence,
            }
        job = self.store.load(job_id)
        recovered = dict(job.get("cancel_terminal_restore_recovery") or {})
        if recovered.get("reconnected") is True:
            return {
                "required": True, "complete": True, "reason": "CONTROLLER_RECOVERY_RECONNECTED",
                "handoff": evidence, "cleanup": cleanup_evidence, "recovery": recovered,
            }
        return {
            "required": True, "complete": False, "reason": "PRIOR_TERMINAL_RESTORE_REQUIRED",
            "handoff": evidence, "cleanup": cleanup_evidence, "recovery": recovered,
        }

    def _recover_cancel_terminal_state(self, job_id: str) -> dict[str, Any]:
        requirement = self._cancel_restore_requirement(job_id)
        if requirement.get("complete"):
            return requirement
        handoff = dict(requirement.get("handoff") or {})
        job = self.store.load(job_id)
        try:
            login = int(handoff.get("login") or 0)
        except Exception:
            login = 0
        alias = str(handoff.get("terminal") or (job.get("request") or {}).get("terminal") or "")
        expected_path = str(handoff.get("terminal_path") or "")
        selection = dict(job.get("execution_terminal") or {})
        request = dict(job.get("request") or {})
        overrides = dict(request.get("overrides") or {})
        symbol = str(selection.get("resolved_symbol") or selection.get("requested_symbol") or overrides.get("symbol") or "EURUSD")
        if not alias or not expected_path or login <= 0:
            return {**requirement, "recovery_attempted": False, "error": "RESTORE_PROVENANCE_INCOMPLETE"}

        from .inventory import TerminalInventory
        from .mt5_preflight import MT5Preflight, public_preflight
        from .terminal_handoff import restart_normal_terminal, running_pids_for_executable

        terminal = TerminalInventory(self.root).get(alias)
        norm = lambda value: str(value).replace("/", "\\").rstrip("\\").lower()
        if norm(terminal.terminal_path) != norm(expected_path):
            return {**requirement, "recovery_attempted": False, "error": "RESTORE_TERMINAL_PATH_MISMATCH"}

        existing = running_pids_for_executable(terminal.terminal_path)
        if existing:
            probe = MT5Preflight(terminal.terminal_path).probe(symbol, timeout_ms=8000)
            same_login = bool(probe.get("ok")) and int(probe.get("_login") or 0) == login
            recovery = {
                "at": now_iso(), "method": "OBSERVED_EXISTING_EXACT_TERMINAL",
                "terminal": alias, "terminal_path": terminal.terminal_path, "login": login,
                "observed_pids": existing, "reconnected": same_login,
                "preflight": public_preflight(probe),
            }
            self.store.update_fields(job_id, cancel_terminal_restore_recovery=recovery)
            if same_login:
                self.store.publish_event(job_id, "CANCEL_TERMINAL_RESTORE_RECOVERED", {"method": recovery["method"], "pids": existing})
                return {**requirement, "complete": True, "reason": "CONTROLLER_RECOVERY_RECONNECTED", "recovery": recovery}
            return {**requirement, "complete": False, "reason": "EXACT_TERMINAL_RUNNING_SESSION_UNVERIFIED", "recovery": recovery}

        restored = restart_normal_terminal(terminal, login, symbol, 60)
        recovery = {
            "at": now_iso(), "method": "RESTART_EXACT_PRIOR_TERMINAL",
            "terminal": alias, "terminal_path": terminal.terminal_path, "login": login,
            **dict(restored or {}),
        }
        self.store.update_fields(job_id, cancel_terminal_restore_recovery=recovery)
        if recovery.get("reconnected"):
            self.store.publish_event(job_id, "CANCEL_TERMINAL_RESTORE_RECOVERED", {
                "method": recovery["method"], "restart_pid": recovery.get("restart_pid"),
            })
            return {**requirement, "complete": True, "reason": "CONTROLLER_RECOVERY_RECONNECTED", "recovery": recovery}
        return {**requirement, "complete": False, "reason": "CONTROLLER_RECOVERY_FAILED", "recovery": recovery}

    def cancel_job(self, job_id: str, wait_seconds: float = 1.0) -> dict:
        job = self.store.load(job_id)
        if job["state"] in TERMINAL_STATES:
            return job

        requested_at = now_iso()
        def mark_cancel(current: dict) -> None:
            current["cancel_requested"] = True
            current.setdefault("cancel_requested_at", requested_at)
        self.store.mutate(job_id, mark_cancel)

        deadline = time.monotonic() + max(0.0, min(float(wait_seconds or 0), 10.0))
        while True:
            current = self.store.load(job_id)
            if current.get("state") in TERMINAL_STATES:
                return current
            reconciliation = self._process_reconciliation(job_id, current)
            self.store.update_fields(job_id, cancel_process_reconciliation=reconciliation)
            proof = self.execution_stopped(job_id)
            if proof.get("stopped"):
                try:
                    return self.settle_cancelled(job_id, proof)
                except RuntimeError as exc:
                    if str(exc) != "CANCEL_TERMINAL_RESTORE_UNPROVEN":
                        raise
                    self.store.update_fields(job_id, cancel_pending_at=now_iso(), cancel_stop_proof=proof)
                    return self.store.load(job_id)
            if proof.get("unverified_live_processes"):
                self.store.update_fields(job_id, cancel_pending_at=now_iso(), cancel_stop_proof=proof)
                return self.store.load(job_id)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)

        reconciliation = self._process_reconciliation(job_id, self.store.load(job_id))
        exact_processes = list(reconciliation.get("exact_live_processes") or [])
        worker_live = any("worker" in (item.get("roles") or []) for item in exact_processes)
        if not worker_live:
            roles = []
            for role, data in dict((self.store.load(job_id).get("processes") or {})).items():
                try:
                    pid = int((data or {}).get("pid") or 0)
                except Exception:
                    pid = 0
                if pid > 0 and pid in set(reconciliation.get("exact_live_pids") or []):
                    roles.append(str(role))
            stop_results = []
            for role in sorted(set(roles)):
                if role == "worker":
                    continue
                stop_results.append(self.terminate_role_process(job_id, role, wait_seconds=3.0))
            if stop_results:
                self.store.update_fields(job_id, cancel_orphan_role_stop=stop_results)
            proof = self.execution_stopped(job_id)
            if proof.get("stopped"):
                try:
                    return self.settle_cancelled(job_id, proof)
                except RuntimeError as exc:
                    if str(exc) != "CANCEL_TERMINAL_RESTORE_UNPROVEN":
                        raise

        proof = self.execution_stopped(job_id)
        self.store.update_fields(job_id, cancel_pending_at=now_iso(), cancel_stop_proof=proof)
        return self.store.load(job_id)

    def execution_stopped(self, job_id: str) -> dict:
        job = self.store.load(job_id)
        reconciliation = self._process_reconciliation(job_id, job)
        live = reconciliation["exact_live_pids"]
        unverified = list(reconciliation["unverified_live_processes"])

        if (
            job.get("spawn_requested")
            and not job.get("spawn_ack_at")
            and not live
            and not any(x.get("reason") == "SPAWN_INTENT_UNACKNOWLEDGED" for x in unverified)
        ):
            unverified.append({"role": "worker", "pid": 0, "reason": "SPAWN_INTENT_UNACKNOWLEDGED"})

        terminal = job.get("state") in TERMINAL_STATES
        return {
            "job_id": job_id,
            "state": job.get("state"),
            "terminal": terminal,
            "live_pids": live,
            "unverified_live_processes": unverified,
            "stale_or_reused_pids": reconciliation["stale_or_reused_pids"],
            "stopped": not live and not unverified,
        }

    def settle_cancelled(self, job_id: str, stop_proof: dict[str, Any]) -> dict:
        proof = dict(stop_proof or {})
        if proof.get("job_id") not in (None, "", job_id):
            raise RuntimeError("CANCEL_STOP_PROOF_JOB_MISMATCH")
        if not bool(proof.get("stopped")) or proof.get("live_pids") or proof.get("unverified_live_processes"):
            raise RuntimeError("CANCEL_STOP_UNPROVEN")

        restore = self._recover_cancel_terminal_state(job_id)
        if not restore.get("complete"):
            self.store.update_fields(job_id, cancel_terminal_restore_requirement=restore)
            raise RuntimeError("CANCEL_TERMINAL_RESTORE_UNPROVEN")

        completed_at = now_iso()
        def apply(job: dict) -> None:
            if job.get("state") in TERMINAL_STATES:
                return
            if not job.get("cancel_requested"):
                raise RuntimeError("CANCEL_INTENT_REQUIRED")
            job["state"] = "CANCELLED"
            job["cancel_completed_at"] = completed_at
            job["cancel_stop_proof"] = proof
            job["cancel_terminal_restore_requirement"] = restore
            job.pop("cancel_pending_at", None)
            seq = int(job.get("event_seq") or 0) + 1
            event = {"seq": seq, "kind": "JOB_TERMINAL", "at": completed_at, "payload": {"state": "CANCELLED", "reason": "CANCEL_STOP_PROVEN"}}
            events = list(job.get("events") or [])
            events.append(event)
            job["event_seq"] = seq
            job["last_event"] = event
            job["events"] = events[-200:]

        return self.store.mutate(job_id, apply)

    def _settle_cancel_if_stopped(self, job_id: str) -> dict:
        job = self.store.load(job_id)
        if job.get("state") in TERMINAL_STATES or not job.get("cancel_requested"):
            return job
        proof = self.execution_stopped(job_id)
        if proof.get("stopped"):
            try:
                return self.settle_cancelled(job_id, proof)
            except RuntimeError as exc:
                if str(exc) == "CANCEL_TERMINAL_RESTORE_UNPROVEN":
                    self.store.update_fields(job_id, cancel_pending_at=now_iso(), cancel_stop_proof=proof)
                    return self.store.load(job_id)
                raise
        return job

    def reconcile_cancelled_jobs(self, wait_seconds: float = 0.5) -> dict[str, Any]:
        candidates: list[str] = []
        scan_errors: list[dict[str, str]] = []
        runs = self.root / "runs"
        if runs.is_dir():
            for p in sorted(runs.glob("*/job.json")):
                job_id = p.parent.name
                if not _JOB_ID_RE.fullmatch(job_id):
                    continue
                try:
                    job = self.store.load(job_id)
                except Exception as exc:
                    scan_errors.append({"job_id": job_id, "error": type(exc).__name__, "message": str(exc)})
                    continue
                if job.get("state") not in TERMINAL_STATES and job.get("cancel_requested"):
                    candidates.append(job_id)

        settled: list[str] = []
        unresolved: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = list(scan_errors)
        for job_id in candidates:
            try:
                out = self.cancel_job(job_id, wait_seconds=wait_seconds)
                if out.get("state") == "CANCELLED":
                    settled.append(job_id)
                else:
                    proof = self.execution_stopped(job_id)
                    unresolved.append({"job_id": job_id, "state": out.get("state"), "proof": proof})
            except Exception as exc:
                errors.append({"job_id": job_id, "error": type(exc).__name__, "message": str(exc)})

        return {
            "schema_version": "1.0",
            "candidates": len(candidates),
            "settled": len(settled),
            "settled_job_ids": settled,
            "unresolved": unresolved,
            "errors": errors,
            "complete": not unresolved and not errors,
        }

    def read_result(self, job_id: str) -> dict:
        p = self.store.path(job_id).parent / "result.json"
        if not p.exists():
            return {"job_id": job_id, "status": "NOT_READY"}
        return _read_json_object(p)
