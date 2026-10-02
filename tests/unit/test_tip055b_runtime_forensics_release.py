"""Isolated release regressions selected by the supported runtime_forensics suite."""
from __future__ import annotations

from ownership_fixture import install_closed

import ctypes
import errno
import json
import os
import threading
from pathlib import Path

import pytest

from vibemql5.core import concurrency
from vibemql5.core.concurrency import ConcurrencyManager, acquire_native_execution


@pytest.fixture
def lease(tmp_path):
    install_closed(tmp_path / "bridge")
    return acquire_native_execution(tmp_path / "bridge", "RELEASE-FIXTURE", kind="fixture", wait_seconds=2)


def sharing_error(code=32):
    error = PermissionError(errno.EACCES, "injected Windows sharing/lock denial")
    error.winerror = code
    return error


class Clock:
    def __init__(self, on_sleep=None):
        self.now = 0.0
        self.sleeps = []
        self.on_sleep = on_sleep

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep()


@pytest.mark.parametrize("code", [32, 33])
@pytest.mark.parametrize("operation", ["read_text", "unlink"])
def test_transient_windows_denial_retries_and_completes_once(lease, monkeypatch, code, operation):
    original = getattr(Path, operation)
    attempts = []
    clock = Clock()
    monkeypatch.setattr(concurrency, "time", clock)

    def deny_once(path, *args, **kwargs):
        if path == lease.lock_path:
            attempts.append(path)
            if len(attempts) == 1:
                assert not lease.released
                raise sharing_error(code)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, deny_once)
    lease.release()
    assert lease.released and not lease.lock_path.exists()
    assert len(attempts) == 2 and len(clock.sleeps) == 1
    lease.release()
    assert len(attempts) == 2


@pytest.mark.parametrize("code", [32, 33])
def test_persistent_denial_expires_explicitly_and_later_release_succeeds(lease, monkeypatch, code):
    original = Path.unlink
    committed = lease.lock_path.read_bytes()
    clock = Clock()
    monkeypatch.setattr(concurrency, "time", clock)
    attempts = []
    denied = True

    def unlink(path, *args, **kwargs):
        if path == lease.lock_path:
            attempts.append(clock.now)
            if denied:
                raise sharing_error(code)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError) as failure:
        lease.release()
    assert failure.value.winerror == code
    assert not lease.released and lease.lock_path.read_bytes() == committed
    assert clock.now == pytest.approx(1.0)
    assert 1 < len(attempts) <= 22
    assert max(attempts) < 1.0
    denied = False
    lease.release()
    assert lease.released and not lease.lock_path.exists()
    completed_attempts = len(attempts)
    lease.release()
    assert len(attempts) == completed_attempts


@pytest.mark.parametrize("code", [None, 5, 13])
@pytest.mark.parametrize("operation", ["read_text", "unlink"])
def test_general_permission_or_other_errors_are_not_retried(lease, monkeypatch, code, operation):
    original = getattr(Path, operation)
    committed = lease.lock_path.read_bytes()
    clock = Clock()
    monkeypatch.setattr(concurrency, "time", clock)
    attempts = []

    def deny(path, *args, **kwargs):
        if path == lease.lock_path:
            attempts.append(path)
            error = PermissionError(errno.EACCES, "nonretryable permission denial")
            if code is not None:
                error.winerror = code
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, deny)
    with pytest.raises(PermissionError):
        lease.release()
    assert len(attempts) == 1 and clock.sleeps == []
    assert not lease.released and lease.lock_path.read_bytes() == committed


@pytest.mark.parametrize("raw", [b"{", b"[]", b"null", b"{}", b'{"token":null}', b'{"token":4}', b'{"token":""}', b'{"token":"   "}', b"\xff"])
def test_corrupt_ownership_is_explicit_and_never_deleted(lease, monkeypatch, raw):
    lease.lock_path.write_bytes(raw)
    ticket = lease.queue_root / "unfinished-ticket.json"
    ticket.write_text("{}", encoding="utf-8")
    lease.ticket_path = ticket
    original = Path.unlink

    def never_delete_owner(path, *args, **kwargs):
        if path == lease.lock_path:
            pytest.fail("corrupt ownership was blindly deleted")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", never_delete_owner)
    with pytest.raises((ValueError, UnicodeError)):
        lease.release()
    assert not lease.released and lease.lock_path.read_bytes() == raw
    assert lease.ticket_path is None and not ticket.exists()


def test_non_file_owner_path_is_an_explicit_failure(lease):
    lease.lock_path.unlink()
    lease.lock_path.mkdir()
    with pytest.raises(OSError):
        lease.release()
    assert not lease.released and lease.lock_path.is_dir()


def test_failed_read_is_not_absence_when_owner_path_still_exists(lease, monkeypatch):
    original = Path.read_text
    committed = lease.lock_path.read_bytes()

    def unreadable_existing_path(path, *args, **kwargs):
        if path == lease.lock_path:
            raise FileNotFoundError(errno.ENOENT, "target absent but owner path still exists")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable_existing_path)
    with pytest.raises(FileNotFoundError):
        lease.release()
    assert not lease.released and lease.lock_path.read_bytes() == committed


@pytest.mark.parametrize("change", ["successor", "corrupt", "absent"])
def test_each_retry_rechecks_ownership_without_blind_deletion(lease, monkeypatch, change):
    original = Path.unlink
    attempts = []
    successor = {**lease._owner_payload(), "token": "successor-token", "operation_id": "SUCCESSOR"}

    def replace_owner():
        if change == "successor":
            lease.lock_path.write_text(json.dumps(successor), encoding="utf-8")
        elif change == "corrupt":
            lease.lock_path.write_text("{", encoding="utf-8")
        else:
            original(lease.lock_path)

    monkeypatch.setattr(concurrency, "time", Clock(on_sleep=replace_owner))

    def deny_first_delete(path, *args, **kwargs):
        if path == lease.lock_path:
            attempts.append(path)
            if len(attempts) == 1:
                raise sharing_error()
            pytest.fail("release deleted ownership without rechecking after denial")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_first_delete)
    if change == "corrupt":
        with pytest.raises(ValueError):
            lease.release()
        assert not lease.released and lease.lock_path.read_text(encoding="utf-8") == "{"
    else:
        lease.release()
        assert lease.released
        if change == "successor":
            assert json.loads(lease.lock_path.read_text(encoding="utf-8")) == successor
        else:
            assert not lease.lock_path.exists()
    assert len(attempts) == 1


@pytest.mark.parametrize("absent", [False, True])
def test_normal_absent_and_path_compatible_completed_release(lease, absent):
    assert os.fspath(lease) == str(lease.lock_path)
    assert lease.exists()
    if absent:
        lease.lock_path.unlink()
    lease.unlink(missing_ok=True)
    assert lease.released and not lease.exists()
    lease.release()
    lease.__exit__(None, None, None)


def test_same_lease_concurrent_release_preserves_an_acquired_successor(lease, monkeypatch):
    original_read = Path.read_text
    original_unlink = Path.unlink
    first_at_delete = threading.Event()
    permit_first_delete = threading.Event()
    second_started = threading.Event()
    second_read_owner = threading.Event()
    successor_installed = threading.Event()
    delete_attempts = []
    errors = []
    successors = []

    def read_owner(path, *args, **kwargs):
        raw = original_read(path, *args, **kwargs)
        if path == lease.lock_path and threading.current_thread().name == "second-release":
            if json.loads(raw).get("token") == lease.token:
                second_read_owner.set()
                assert successor_installed.wait(2), "successor was not installed between read and delete"
        return raw

    def delete_owner(path, *args, **kwargs):
        if path != lease.lock_path:
            return original_unlink(path, *args, **kwargs)
        caller = threading.current_thread().name
        delete_attempts.append(caller)
        if caller == "first-release":
            first_at_delete.set()
            assert permit_first_delete.wait(2), "first release was not permitted to complete"
            original_unlink(path, *args, **kwargs)
            successors.append(acquire_native_execution(lease.root, "SUCCESSOR", kind="fixture", wait_seconds=2))
            successor_installed.set()
            return None
        return original_unlink(path, *args, **kwargs)

    def release_same_object(second=False):
        if second:
            second_started.set()
        try:
            lease.release()
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(Path, "read_text", read_owner)
    monkeypatch.setattr(Path, "unlink", delete_owner)
    first = threading.Thread(target=release_same_object, name="first-release")
    second = threading.Thread(target=release_same_object, args=(True,), name="second-release")
    try:
        first.start()
        assert first_at_delete.wait(2)
        second.start()
        assert second_started.wait(2)
        # An unsynchronized second release is held with its old owner read until a real
        # successor acquires. A serialized release cannot perform that duplicate read.
        second_read_owner.wait(0.2)
        permit_first_delete.set()
        first.join(2)
        second.join(2)
        assert not first.is_alive() and not second.is_alive() and errors == []
        assert lease.released and not second_read_owner.is_set()
        assert delete_attempts == ["first-release"]
        assert len(successors) == 1
        assert json.loads(lease.lock_path.read_text(encoding="utf-8"))["token"] == successors[0].token
    finally:
        permit_first_delete.set()
        first.join(2)
        if second.ident is not None:
            second.join(2)
        for successor in successors:
            successor.release()


@pytest.mark.parametrize("namespace", ["native", "mutation"])
def test_native_and_mutation_context_cleanup_recover_transient_release(tmp_path, monkeypatch, namespace):
    install_closed(tmp_path / "bridge")
    manager = ConcurrencyManager(tmp_path / "bridge")
    lock = manager.state_root / "mutation.lock" if namespace == "mutation" else manager.root / "runs" / ".active.lock"
    original = Path.unlink
    denied = []

    def deny_once(path, *args, **kwargs):
        if path == lock and not denied:
            denied.append(path)
            raise sharing_error()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_once)
    context = manager.mutation("fixture", wait_seconds=2) if namespace == "mutation" else manager.native_execution("FIXTURE", kind="fixture", wait_seconds=2)
    with context as held:
        assert held.lock_path == lock and held.exists() and not held.released
    assert held.released and not lock.exists() and denied == [lock]
    assert manager.status()["native_mt5_parallelism"] == 1
    assert manager.status()["source_mutation_parallelism"] == 1
    assert not list(held.queue_root.glob("*.json"))


class WindowsDenyDeleteHandle:
    """Open a real Windows sharing handle that permits reads but refuses deletion."""
    def __init__(self, path):
        from ctypes import wintypes
        self._close_lock = threading.Lock()
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel32.CreateFileW(str(path), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
        if self.handle == ctypes.c_void_p(-1).value:
            pytest.fail(f"Windows deny-delete mechanism unavailable: {ctypes.WinError(ctypes.get_last_error())}")

    def close(self):
        with self._close_lock:
            if self.handle is not None:
                if not self.kernel32.CloseHandle(self.handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handle = None


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows deny-delete handle gate requires Windows; injected faults are separate evidence")
def test_actual_windows_deny_delete_handle_recovers_within_release_bound(lease, monkeypatch):
    handle = WindowsDenyDeleteHandle(lease.lock_path)
    original = Path.unlink
    denied = threading.Event()
    close_errors = []
    attempts = []

    def close_after_real_denial():
        try:
            assert denied.wait(2), "release never observed a real Windows sharing denial"
            handle.close()
        except BaseException as exc:
            close_errors.append(exc)

    def observe_real_delete(path, *args, **kwargs):
        if path != lease.lock_path:
            return original(path, *args, **kwargs)
        attempts.append(path)
        try:
            return original(path, *args, **kwargs)
        except OSError as exc:
            assert exc.winerror in {32, 33}, "deny-delete handle produced an unexpected failure"
            denied.set()
            raise

    closer = None
    try:
        with pytest.raises(OSError) as proof:
            original(lease.lock_path)
        assert proof.value.winerror in {32, 33}
        assert lease.lock_path.exists() and not lease.released
        monkeypatch.setattr(Path, "unlink", observe_real_delete)
        closer = threading.Thread(target=close_after_real_denial)
        closer.start()
        lease.release()
        closer.join(2)
        assert not closer.is_alive() and close_errors == []
        assert denied.is_set() and len(attempts) >= 2
        assert lease.released and not lease.lock_path.exists()
        completed_attempts = len(attempts)
        lease.release()
        assert len(attempts) == completed_attempts
    finally:
        handle.close()
        if closer is not None:
            closer.join(2)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows persistent deny-delete gate requires Windows")
def test_actual_windows_persistent_deny_delete_stays_retryable(lease):
    handle = WindowsDenyDeleteHandle(lease.lock_path)
    committed = lease.lock_path.read_bytes()
    try:
        with pytest.raises(OSError) as failure:
            lease.release()
        assert failure.value.winerror in {32, 33}
        assert not lease.released and lease.lock_path.read_bytes() == committed
    finally:
        handle.close()
    lease.release()
    assert lease.released and not lease.lock_path.exists()
