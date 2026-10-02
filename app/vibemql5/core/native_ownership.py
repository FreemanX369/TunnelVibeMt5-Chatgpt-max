"""Internal native ownership barrier; no installer, helper or public recovery API.

The installation marker is published only by a separately qualified migration. A native
lease does not close durable ownership. Future producers must arm, commit the create
attempt, bind an independently observed suspended process, then resume it in that order.
"""
from __future__ import annotations

import ctypes
import os
import select
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .jobs import _atomic_write_json, _exclusive_file_lock, _process_identity, _read_json_object

SCHEMA = "native.ownership/1"
INSTALL_SCHEMA = "native.ownership.install/1"


class OwnershipBlocked(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"LIVE_RECOVERY_REQUIRED: native_ownership:{reason}")


def _positive(value: Any) -> bool:
    return type(value) is int and value > 0


def _identity_valid(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {"pid", "creation", "image"}
            and _positive(value["pid"]) and isinstance(value["creation"], str)
            and 0 < len(value["creation"]) <= 32 and value["creation"].isascii() and value["creation"].isdigit()
            and int(value["creation"]) > 0 and isinstance(value["image"], str)
            and len(value["image"]) <= 32768 and os.path.isabs(value["image"]))


class ObservedProcess:
    """Read-only OS observation with a retained process lifetime handle.

    An expected journal image is never used to fill missing OS evidence. A fresh open
    of an already dead process refuses identity even if process times remain available.
    On Windows the image must be observed while the same kernel handle is live.
    """
    def __init__(self, pid: int):
        if not _positive(pid):
            raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        self.pid = pid
        self._live_identity: dict[str, Any] | None = None
        self._identity_handle = None
        self.handle = None
        if os.name == "nt":
            from ctypes import wintypes as W
            self._W = W
            k = self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
            k.OpenProcess.restype = W.HANDLE
            k.CloseHandle.argtypes = [W.HANDLE]
            k.CloseHandle.restype = W.BOOL
            k.GetProcessId.argtypes = [W.HANDLE]
            k.GetProcessId.restype = W.DWORD
            k.GetProcessTimes.argtypes = [W.HANDLE, *([ctypes.POINTER(W.FILETIME)] * 4)]
            k.GetProcessTimes.restype = W.BOOL
            k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
            k.QueryFullProcessImageNameW.restype = W.BOOL
            k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
            k.WaitForSingleObject.restype = W.DWORD
            self.handle = k.OpenProcess(0x1000 | 0x100000, False, pid)
            if not self.handle:
                raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        else:
            # pidfd is a lifetime handle, so an exited/reused PID cannot supply proof.
            try:
                self.handle = os.pidfd_open(pid)
            except (AttributeError, OSError) as exc:
                raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN") from exc

    def exited(self) -> bool:
        if self.handle is None:
            raise OwnershipBlocked("PROCESS_HANDLE_CLOSED")
        if os.name == "nt":
            wait = self.kernel.WaitForSingleObject(self.handle, 0)
            if wait not in (0, 0x102):
                raise OwnershipBlocked("PROCESS_EXIT_UNPROVEN")
            return wait == 0
        return bool(select.select([self.handle], [], [], 0)[0])

    def _windows_lifetime(self) -> dict[str, Any]:
        W = self._W
        times = [W.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(self.handle, *(ctypes.byref(t) for t in times)):
            raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        return {"pid": int(self.kernel.GetProcessId(self.handle)),
                "creation": str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)}

    def identity(self) -> dict[str, Any]:
        if self._live_identity is not None:
            if self.handle is None:
                raise OwnershipBlocked("PROCESS_HANDLE_CLOSED")
            if self.handle != self._identity_handle:
                raise OwnershipBlocked("PROCESS_HANDLE_CHANGED")
            if os.name == "nt" and any(self._live_identity[key] != value
                                      for key, value in self._windows_lifetime().items()):
                raise OwnershipBlocked("PROCESS_LIFETIME_CHANGED")
            return dict(self._live_identity)
        if self.exited():
            raise OwnershipBlocked("LIVE_IMAGE_NOT_CAPTURED_BEFORE_EXIT")
        if os.name == "nt":
            W = self._W
            lifetime = self._windows_lifetime()
            image = ctypes.create_unicode_buffer(32768)
            length = W.DWORD(len(image))
            if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, image, ctypes.byref(length)):
                raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
            if not image.value or not length.value or not os.path.isabs(image.value):
                raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
            observed = {**lifetime, "image": os.path.normcase(os.path.realpath(image.value))}
        else:
            try:
                namespace_matches = int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) == os.getpid()
            except (OSError, ValueError):
                namespace_matches = False
            if not namespace_matches and self.pid != os.getpid():
                raise OwnershipBlocked("PROCESS_NAMESPACE_UNQUALIFIED")
            actual = _process_identity(self.pid) if namespace_matches else None
            if actual is None and self.pid == os.getpid():
                # /proc/self remains an independent observation in PID namespaces
                # where /proc/<getpid> is unavailable or mounted from another namespace.
                try:
                    stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
                    actual = {"pid": self.pid, "start_ticks": stat[19],
                              "executable": os.readlink("/proc/self/exe")}
                except (OSError, IndexError):
                    pass
            if not actual:
                raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
            try:
                proc = Path("/proc/self") if self.pid == os.getpid() else Path("/proc") / str(self.pid)
                # A permissive Path.resolve fallback is not executable observation.
                image = os.readlink(proc / "exe")
                stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
                if not image or not os.path.isabs(image):
                    raise ValueError("missing independently observed image")
                observed = {"pid": actual["pid"], "creation": stat[19], "image": os.path.realpath(image)}
            except (OSError, IndexError, ValueError) as exc:
                raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN") from exc

        if self.exited():
            raise OwnershipBlocked("LIVE_IMAGE_CAPTURE_RACED_EXIT")
        if not _identity_valid(observed):
            raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        self._live_identity = observed
        self._identity_handle = self.handle
        return dict(observed)

    def close(self) -> None:
        if self.handle is not None:
            if os.name == "nt":
                self.kernel.CloseHandle(self.handle)
            else:
                os.close(self.handle)
            self.handle = None
            self._live_identity = None
            self._identity_handle = None

    def __enter__(self) -> "ObservedProcess":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def current_identity() -> dict[str, Any]:
    with ObservedProcess(os.getpid()) as process:
        return process.identity()


class OwnershipAuthority:
    def __init__(self, root: Path):
        self.root = Path(root)
        state = self.root / "state" / "concurrency"
        self.marker_path = state / "native-ownership-install.json"
        self.path = state / "native-ownership.json"
        self.lock_path = state / ".native-ownership.lock"

    @contextmanager
    def transaction(self) -> Iterator[None]:
        # Never hold this guard over FIFO waiting, process waits or native callbacks.
        guard = _exclusive_file_lock(self.lock_path, timeout_seconds=2.0)
        try:
            guard.__enter__()
        except (OSError, TimeoutError) as exc:
            raise OwnershipBlocked("AUTHORITY_GUARD_UNAVAILABLE") from exc
        try:
            yield
        except BaseException:
            # Preserve body's release sharing errors for the existing bounded retry.
            try:
                guard.__exit__(*sys.exc_info())
            except OSError:
                pass
            raise
        else:
            try:
                guard.__exit__(None, None, None)
            except OSError as exc:
                raise OwnershipBlocked("AUTHORITY_GUARD_UNAVAILABLE") from exc

    def load(self) -> dict[str, Any]:
        try:
            marker = _read_json_object(self.marker_path, attempts=1)
        except FileNotFoundError as exc:
            raise OwnershipBlocked("INSTALL_MISSING") from exc
        except (OSError, ValueError, TypeError) as exc:
            raise OwnershipBlocked("INSTALL_INVALID") from exc
        if (marker.get("schema") != INSTALL_SCHEMA or not isinstance(marker.get("epoch"), str)
                or not marker["epoch"].strip() or marker.get("disposition") not in ("MIGRATING", "READY")):
            raise OwnershipBlocked("INSTALL_INVALID")
        if marker["disposition"] != "READY":
            raise OwnershipBlocked("INSTALL_MIGRATING")
        try:
            state = _read_json_object(self.path, attempts=1)
        except FileNotFoundError as exc:
            raise OwnershipBlocked("AUTHORITY_MISSING") from exc
        except (OSError, ValueError, TypeError) as exc:
            raise OwnershipBlocked("AUTHORITY_INVALID") from exc
        try:
            valid = (state.get("schema") == SCHEMA and _positive(state.get("generation"))
                     and isinstance(state.get("epoch"), str) and bool(state["epoch"].strip())
                     and state.get("disposition") in {"CLOSED", "ACTIVE"})
            if state.get("disposition") == "CLOSED":
                valid &= (state.get("phase") == "CLOSED" and state.get("token") == ""
                          and state.get("operation_id") == "" and state.get("kind") == ""
                          and state.get("parent") is None and state.get("worker") is None
                          and state.get("descendants") == "NONE")
            else:
                valid &= (all(isinstance(state.get(k), str) and bool(state[k].strip())
                              for k in ("token", "operation_id", "kind"))
                          and _identity_valid(state.get("parent"))
                          and state.get("descendants") == "UNKNOWN"
                          and state.get("phase") in {"ARMED", "CREATE_ATTEMPT", "BOUND"})
                valid &= (_identity_valid(state.get("worker")) if state.get("phase") == "BOUND"
                          else state.get("worker") is None)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise OwnershipBlocked("AUTHORITY_INVALID")
        if state["epoch"] != marker["epoch"]:
            raise OwnershipBlocked("EPOCH_MISMATCH")
        return state

    def require_closed(self) -> dict[str, Any]:
        state = self.load()
        if state["disposition"] != "CLOSED":
            raise OwnershipBlocked("ACTIVE_RECOVERY_REQUIRED")
        return state

    def status(self) -> dict[str, Any]:
        try:
            with self.transaction():
                state = self.load()
            return {"schema": SCHEMA, "disposition": state["disposition"],
                    "phase": state["phase"], "generation": state["generation"],
                    "admission": "AVAILABLE" if state["disposition"] == "CLOSED" else "BLOCKED",
                    "reason": None if state["disposition"] == "CLOSED" else "ACTIVE_RECOVERY_REQUIRED"}
        except OwnershipBlocked as exc:
            return {"schema": SCHEMA, "admission": "BLOCKED", "reason": exc.reason}

    def _publish(self, state: dict[str, Any]) -> dict[str, Any]:
        try:
            _atomic_write_json(self.path, state)
        except (OSError, ValueError) as exc:
            # No guessed success or rollback: disk retains ACTIVE or invalid uncertainty.
            raise OwnershipBlocked("AUTHORITY_PUBLICATION_UNCERTAIN") from exc
        if self.load() != state:
            raise OwnershipBlocked("AUTHORITY_PUBLICATION_UNCERTAIN")
        return state

    def _expected(self, expected: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        if current["disposition"] != "ACTIVE" or current != expected:
            raise OwnershipBlocked("STALE_AUTHORITY_CAS")
        return current

    def arm(self, lease) -> dict[str, Any]:
        parent = current_identity()  # OS observation outside the short transaction.
        with self.transaction():
            state = self.require_closed()
            try:
                owner = _read_json_object(self.root / "runs" / ".active.lock", attempts=1)
            except (OSError, ValueError) as exc:
                raise OwnershipBlocked("OWNED_NATIVE_LEASE_REQUIRED") from exc
            if (getattr(lease, "namespace", None) != "native" or getattr(lease, "released", True)
                    or owner.get("token") != lease.token or owner.get("pid") != parent["pid"]
                    or owner.get("identity") != parent or Path(lease.root).resolve() != self.root.resolve()
                    or owner.get("operation_id") != lease.operation_id or owner.get("kind") != lease.kind):
                raise OwnershipBlocked("OWNED_NATIVE_LEASE_REQUIRED")
            return self._publish({"schema": SCHEMA, "epoch": state["epoch"],
                "generation": state["generation"] + 1, "disposition": "ACTIVE", "phase": "ARMED",
                "token": lease.token, "operation_id": lease.operation_id, "kind": lease.kind,
                "parent": parent, "worker": None, "descendants": "UNKNOWN"})

    def _require_producer(self, state: dict[str, Any], parent: dict[str, Any]) -> None:
        try:
            owner = _read_json_object(self.root / "runs" / ".active.lock", attempts=1)
        except (OSError, ValueError) as exc:
            raise OwnershipBlocked("OWNED_NATIVE_LEASE_REQUIRED") from exc
        if (state["parent"] != parent or owner.get("identity") != parent
                or owner.get("pid") != parent["pid"] or owner.get("token") != state["token"]
                or owner.get("operation_id") != state["operation_id"] or owner.get("kind") != state["kind"]):
            raise OwnershipBlocked("OWNED_NATIVE_LEASE_REQUIRED")

    def create_attempt(self, expected: dict[str, Any]) -> dict[str, Any]:
        parent = current_identity()
        with self.transaction():
            state = self._expected(expected)
            self._require_producer(state, parent)
            if state["phase"] != "ARMED":
                raise OwnershipBlocked("CREATE_ORDER_INVALID")
            return self._publish({**state, "phase": "CREATE_ATTEMPT"})

    def bind_worker(self, expected: dict[str, Any], process: ObservedProcess) -> dict[str, Any]:
        if not isinstance(process, ObservedProcess):
            raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        actual = process.identity()
        parent = current_identity()
        if process.exited():
            raise OwnershipBlocked("WORKER_NOT_LIVE_AT_BIND")
        with self.transaction():
            state = self._expected(expected)
            self._require_producer(state, parent)
            if state["phase"] != "CREATE_ATTEMPT":
                raise OwnershipBlocked("BIND_ORDER_INVALID")
            return self._publish({**state, "phase": "BOUND", "worker": actual})

    def _closed(self, state: dict[str, Any]) -> dict[str, Any]:
        closed = {**state, "disposition": "CLOSED", "phase": "CLOSED",
            "token": "", "operation_id": "", "kind": "", "parent": None,
            "worker": None, "descendants": "NONE"}
        try:
            return self._publish(closed)
        except OwnershipBlocked:
            # While still holding the CAS guard, retain the prior barrier on a caught
            # publication/readback failure. If the storage itself cannot accept this
            # write, exact closure was already proven before CLOSED publication but
            # power-loss/rollback guarantees cannot be manufactured by JSON fixtures.
            try:
                _atomic_write_json(self.path, state)
            except (OSError, ValueError):
                pass
            raise

    def close_zero_attempt(self, expected: dict[str, Any]) -> dict[str, Any]:
        with self.transaction():
            state = self._expected(expected)
            if state["phase"] != "ARMED" or state["worker"] is not None:
                raise OwnershipBlocked("CREATION_OUTCOME_UNKNOWN")
            return self._closed(state)

    def close_owned_worker(self, expected: dict[str, Any], process: ObservedProcess, *,
                           descendant_verifier: Callable[[ObservedProcess], str]) -> dict[str, Any]:
        """Future trusted boundary verifier, deliberately absent from production callers.

        The verifier must independently qualify descendant prevention/exits. UNKNOWN,
        booleans and unqualified dispositions never close. No SDK or helper uses this
        interface in G03-A; harmless fixtures provide their own qualified leaf boundary.
        """
        if not isinstance(process, ObservedProcess):
            raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        actual = process.identity()
        if not process.exited() or actual != expected.get("worker"):
            raise OwnershipBlocked("EXACT_WORKER_EXIT_UNPROVEN")
        try:
            disposition = descendant_verifier(process)  # no effect or wait under guard.
        except Exception as exc:
            raise OwnershipBlocked("DESCENDANTS_UNPROVEN") from exc
        if disposition not in ("PREVENTED_BY_BOUNDARY", "EXACT_DESCENDANTS_EXITED"):
            raise OwnershipBlocked("DESCENDANTS_UNPROVEN")
        with self.transaction():
            state = self._expected(expected)
            if state["phase"] != "BOUND" or state["worker"] != actual:
                raise OwnershipBlocked("EXACT_WORKER_EXIT_UNPROVEN")
            return self._closed(state)
