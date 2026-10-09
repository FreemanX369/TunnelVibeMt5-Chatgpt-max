"""Denied publication is only a wait barrier after real live-owner proof.

Errno13/stat uncertainty is modeled at the OS boundary. Files, FIFO tickets,
authority, process lifetime observations and the ordinary FileExists path are real.
"""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ownership_fixture import install_closed
from vibemql5.core import concurrency
from vibemql5.core.native_ownership import ObservedProcess, OwnershipBlocked

FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY


def _lease(root, name, *, namespace="native", wait=3, path=None):
    return concurrency._QueuedFileLease(root, namespace=namespace, operation_id=name,
        kind="owned-test", actor=None, wait_seconds=wait,
        lock_path=path or root / "runs" / ".active.lock")


@pytest.fixture
def held(tmp_path):
    install_closed(tmp_path)
    owner = _lease(tmp_path, "HOLD").acquire()
    original = owner.lock_path.read_bytes()
    try:
        yield owner
    finally:
        # Negative controls own deliberate metadata changes; restore only this root.
        if not owner.released:
            owner.lock_path.write_bytes(original)
            owner.release()


def _deny(monkeypatch, candidate, error, *, condition=lambda: True):
    original = concurrency.os.open
    calls = []

    def boundary(path, flags, *args, **kwargs):
        if str(path) == str(candidate.lock_path) and flags == FLAGS and condition():
            calls.append((str(path), flags))
            raise error
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(concurrency.os, "open", boundary)
    return calls


def _never_reclaim():
    raise AssertionError("Denied publication must not reclaim any owner")


def _wait(predicate):
    deadline = time.monotonic() + 1
    while not predicate():
        assert time.monotonic() < deadline, "Owned test sequence did not advance"
        time.sleep(0.005)


def test_live_owner_denial_keeps_ticket_and_owner_as_barrier(held, monkeypatch):
    candidate = _lease(held.root, "B")
    candidate.ticket_path = candidate._new_ticket()
    ticket = candidate.ticket_path
    before = held.lock_path.read_bytes()
    error = PermissionError(errno.EACCES, "modeled publication denial", str(candidate.lock_path))
    calls = _deny(monkeypatch, candidate, error)
    monkeypatch.setattr(candidate, "_remove_dead_owner", _never_reclaim)
    original_reader, reads = concurrency._read_json_object, []

    def read(path, **kwargs):
        reads.append((path, kwargs))
        return original_reader(path, **kwargs)

    monkeypatch.setattr(concurrency, "_read_json_object", read)
    try:
        assert candidate._try_acquire(first=True) is False
        assert calls == [(str(candidate.lock_path), FLAGS)]
        assert reads == [(candidate.lock_path, {"attempts": 1})]
        assert candidate.ticket_path == ticket and ticket.is_file()
        assert candidate.acquired_at == "" and not candidate.released
        assert held.lock_path.read_bytes() == before
        with ObservedProcess(os.getpid()) as process:
            assert process.identity() == json.loads(before)["identity"]
        with held.authority.transaction():
            held.authority.require_closed()
    finally:
        ticket.unlink(missing_ok=True)
        candidate.ticket_path = None


def test_qualified_denial_preserves_fifo_until_owner_releases(held, monkeypatch):
    b, c = _lease(held.root, "B"), _lease(held.root, "C")
    before = held.lock_path.read_bytes()
    error = PermissionError(errno.EACCES, "modeled publication denial", str(b.lock_path))
    decision, errors, order = threading.Event(), [], []
    original_attempt = b._try_acquire

    def attempt(*, first):
        try:
            return original_attempt(first=first)
        finally:
            decision.set()

    monkeypatch.setattr(b, "_try_acquire", attempt)
    calls = _deny(monkeypatch, b, error, condition=lambda:
        threading.current_thread().name == "tip072-B" and not calls)

    def waiter(candidate):
        try:
            candidate.acquire()
            try:
                order.append(candidate.operation_id)
            finally:
                candidate.release()
        except BaseException as failed:
            errors.append(failed)

    threads = [threading.Thread(target=waiter, args=(b,), name="tip072-B"),
               threading.Thread(target=waiter, args=(c,), name="tip072-C")]
    try:
        threads[0].start()
        assert decision.wait(1)
        assert errors == []
        assert b.ticket_path is not None and b.ticket_path.is_file()
        threads[1].start()
        _wait(lambda: c.ticket_path is not None and c.ticket_path.is_file())
        assert b._first_ticket() == b.ticket_path
        assert order == [] and held.lock_path.read_bytes() == before and calls
        held.release()
        for thread in threads:
            thread.join(2)
        assert not any(thread.is_alive() for thread in threads)
        assert errors == [] and order == ["B", "C"]
        assert not held.lock_path.exists() and list(b.queue_root.glob("*.json")) == []
        with held.authority.transaction():
            held.authority.require_closed()
    finally:
        held.release()
        for thread in threads:
            if thread.ident is not None:
                thread.join(2)


def test_qualified_denial_keeps_original_zero_wait_deadline(held, monkeypatch):
    candidate = _lease(held.root, "B", wait=0)
    before = held.lock_path.read_bytes()
    error = PermissionError(errno.EACCES, "modeled publication denial", str(candidate.lock_path))
    _deny(monkeypatch, candidate, error)
    monkeypatch.setattr(candidate, "_remove_dead_owner", _never_reclaim)
    with pytest.raises(TimeoutError, match="CONCURRENCY_NATIVE_WAIT_TIMEOUT"):
        candidate.acquire()
    assert held.lock_path.read_bytes() == before
    assert candidate.ticket_path is None and list(candidate.queue_root.glob("*.json")) == []


def test_real_existing_owner_and_successful_release_are_unchanged(held):
    candidate = _lease(held.root, "B")
    before = held.lock_path.read_bytes()
    assert candidate._try_acquire(first=True) is False
    assert held.lock_path.read_bytes() == before and candidate.acquired_at == ""
    held.release()
    assert candidate.acquire() is candidate
    owner = json.loads(candidate.lock_path.read_bytes())
    assert owner["token"] == candidate.token and owner["identity"] == candidate.identity
    assert owner["namespace"] == "native" and owner["operation_id"] == "B"
    candidate.release()
    assert candidate.released and not candidate.lock_path.exists()


NEGATIVE_CASES = ["missing", "corrupt", "foreign", "schema", "wrong-id", "blank-token",
    "invalid-token", "own-token", "pid-text", "pid-bool", "pid-zero", "pid-mismatch",
    "invalid-id", "read-denied", "stat-denied", "unobserved", "dead-owner", "wrong-error",
    "wrong-root", "non-native", "symlink-stat", "reparse-stat", "ancestor-alias", "other-errno"]


@pytest.mark.parametrize("case", NEGATIVE_CASES)
def test_unqualified_denial_keeps_original_error_and_owner(held, monkeypatch, case):
    candidate = _lease(held.root, "B", namespace="mutation" if case == "non-native" else "native")
    if case == "wrong-root":
        candidate.lock_path = held.root / "runs" / "other.lock"
        candidate.lock_path.write_bytes(held.lock_path.read_bytes())
    path = candidate.lock_path
    owner = json.loads(path.read_bytes())
    if case == "foreign": owner["namespace"] = "mutation"
    if case == "schema": owner["schema_version"] = "future"
    if case == "wrong-id": owner["identity"]["creation"] = str(int(owner["identity"]["creation"]) + 1)
    if case == "blank-token": owner["token"] = ""
    if case == "invalid-token": owner["token"] = "g" * 32
    if case == "own-token": owner["token"] = candidate.token
    if case == "pid-text": owner["pid"] = str(owner["pid"])
    if case == "pid-bool": owner["pid"] = True
    if case == "pid-zero": owner["pid"] = 0
    if case == "pid-mismatch": owner["pid"] += 1
    if case == "invalid-id": owner["identity"] = {"pid": owner["pid"]}
    if case == "dead-owner":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with ObservedProcess(child.pid) as process:
                owner["identity"] = process.identity()
            owner["pid"] = child.pid
        finally:
            child.terminate()
            child.wait(timeout=3)
    path.write_text("{" if case == "corrupt" else json.dumps(owner), encoding="utf-8")
    if case == "missing": path.unlink()
    before = path.read_bytes() if path.exists() else None
    error_path = str(held.root / "different.lock") if case == "wrong-error" else str(path)
    error = PermissionError(errno.EPERM if case == "other-errno" else errno.EACCES,
        "modeled publication denial", error_path)
    cause = RuntimeError("owned prior error cause")
    error.__cause__ = cause
    _deny(monkeypatch, candidate, error)
    monkeypatch.setattr(candidate, "_remove_dead_owner", _never_reclaim)
    if case == "read-denied":
        def read(*args, **kwargs):
            raise PermissionError(errno.EACCES, "modeled owner read denial", str(path))
        monkeypatch.setattr(concurrency, "_read_json_object", read)
    if case == "unobserved":
        def observe(pid):
            raise OwnershipBlocked("PROCESS_IDENTITY_UNPROVEN")
        monkeypatch.setattr(concurrency, "ObservedProcess", observe)
    if case in {"stat-denied", "symlink-stat", "reparse-stat"}:
        original_stat = Path.lstat
        metadata = original_stat(path)
        def lstat(actual):
            if actual != path:
                return original_stat(actual)
            if case == "stat-denied":
                raise PermissionError(errno.EACCES, "modeled owner stat denial", str(path))
            return SimpleNamespace(st_mode=(stat.S_IFLNK | 0o777) if case == "symlink-stat" else metadata.st_mode,
                st_file_attributes=0x400 if case == "reparse-stat" else 0)
        monkeypatch.setattr(Path, "lstat", lstat)
    if case == "ancestor-alias":
        original_resolve = Path.resolve
        def resolve(actual, *args, **kwargs):
            return held.root / "aliased" / ".active.lock" if actual == path else original_resolve(actual, *args, **kwargs)
        monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(PermissionError) as caught:
        candidate._try_acquire(first=True)
    assert caught.value is error and caught.value.__cause__ is cause
    assert candidate.acquired_at == "" and candidate.ticket_path is None
    # Read denial/stat uncertainty affects qualification, not this owned byte check.
    assert (path.read_bytes() if path.exists() else None) == before


def test_actual_bad_path_does_not_become_owner_wait(tmp_path):
    install_closed(tmp_path)
    (tmp_path / "runs").write_bytes(b"owned ordinary file blocks the parent directory")
    candidate = _lease(tmp_path, "BAD", wait=0)
    with pytest.raises(OSError) as caught:
        candidate._try_acquire(first=True)
    assert caught.value.filename == str(candidate.lock_path)
    assert (tmp_path / "runs").read_bytes() == b"owned ordinary file blocks the parent directory"
    assert candidate.acquired_at == "" and candidate.ticket_path is None


@pytest.mark.parametrize("case", ["active", "unknown"])
def test_authority_blocks_before_denied_publication(held, monkeypatch, case):
    candidate = _lease(held.root, "B", wait=0)
    if case == "active":
        held.authority.arm(held)
    else:
        held.authority.path.write_bytes(b"{")
    original_state = held.authority.path.read_bytes()
    owner = held.lock_path.read_bytes()
    error = PermissionError(errno.EACCES, "modeled publication denial", str(candidate.lock_path))
    calls = _deny(monkeypatch, candidate, error)
    with pytest.raises(OwnershipBlocked):
        candidate.acquire()
    assert calls == [] and candidate.ticket_path is None
    assert held.lock_path.read_bytes() == owner and held.authority.path.read_bytes() == original_state
