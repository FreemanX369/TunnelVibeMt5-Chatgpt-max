"""Owned scratch only: model the observed publication error; never patch source.

The PermissionError is an injected OS boundary result, not a physical Windows
reproduction. Process identity, owner file, FIFO, authority and release are real.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager

from ownership_fixture import install_closed
from vibemql5.core import concurrency
from vibemql5.core.jobs import _read_json_object
from vibemql5.core.native_ownership import ObservedProcess, OwnershipBlocked, _identity_valid

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "tip071-builder"
FILES = ["app/vibemql5/core/concurrency.py", "app/vibemql5/core/jobs.py",
         "app/vibemql5/core/native_ownership.py"]
FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY


def hashes():
    return {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in FILES}


def lease(root, name, namespace="native"):
    return concurrency._QueuedFileLease(root, namespace=namespace, operation_id=name,
        kind="owned-scratch", actor=None, wait_seconds=3.0, lock_path=root / "runs" / ".active.lock")


def qualified_live_native_owner(candidate, error, reader=_read_json_object):
    """Read-only proposal model. True grants nothing; it means keep waiting only."""
    if (candidate.namespace != "native" or error.errno != errno.EACCES
            or error.filename != str(candidate.lock_path)
            or candidate.lock_path != candidate.root / "runs" / ".active.lock"):
        return False
    try:
        metadata = candidate.lock_path.lstat()
        if (not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & 0x400):
            return False
        owner = reader(candidate.lock_path, attempts=1)
        token = owner.get("token")
        identity = owner.get("identity")
        pid = owner.get("pid")
        if (owner.get("schema_version") != "1.0" or owner.get("namespace") != "native"
                or not isinstance(token, str) or len(token) != 32
                or any(character not in "0123456789abcdef" for character in token)
                or token == candidate.token or type(pid) is not int or pid <= 0
                or not _identity_valid(identity) or identity["pid"] != pid):
            return False
        with ObservedProcess(pid) as process:
            return process.identity() == identity
    except (OSError, ValueError, TypeError, OwnershipBlocked):
        return False


@contextmanager
def denied_publication(candidate, error, *, selected_thread=None, callback=None):
    original = concurrency.os.open

    def boundary(path, flags, *args, **kwargs):
        if (str(path) == str(candidate.lock_path) and flags == FLAGS
                and (selected_thread is None or threading.current_thread().name == selected_thread)):
            if callback is not None:
                callback()
            raise error
        return original(path, flags, *args, **kwargs)

    concurrency.os.open = boundary
    try:
        yield
    finally:
        concurrency.os.open = original


def wait_until(predicate, seconds=1.0):
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Owned probe sequence deadline expired")
        time.sleep(0.005)


def fifo_boundary(root):
    install_closed(root)
    held, b, c = [lease(root, name) for name in ("HOLD", "B", "C")]
    held.acquire()
    owner_bytes = held.lock_path.read_bytes()
    assert b._try_acquire(first=True) is False  # real FileExistsError control
    assert held.lock_path.read_bytes() == owner_bytes
    denied = PermissionError(errno.EACCES, "modeled observed OS boundary", str(b.lock_path))
    observed, order, errors = {}, [], []

    def waiter(candidate):
        try:
            candidate.acquire()
            order.append(candidate.operation_id)
            candidate.release()
        except BaseException as error:
            errors.append((candidate.operation_id, error))
            print("RAW_WAITER_EXCEPTION", candidate.operation_id, flush=True)
            traceback.print_exception(error)

    def before_error():
        observed["ticket_existed_at_denial"] = b.ticket_path is not None and b.ticket_path.is_file()
        observed["qualified_live_owner_at_modeled_denial"] = qualified_live_native_owner(b, denied)
        observed["held_owner_bytes_unchanged_at_denial"] = b.lock_path.read_bytes() == owner_bytes

    tb = threading.Thread(target=waiter, args=(b,), name="owned-probe-B")
    tc = threading.Thread(target=waiter, args=(c,), name="owned-probe-C")
    with denied_publication(b, denied, selected_thread=tb.name, callback=before_error):
        tb.start()
        tb.join(2)
        assert not tb.is_alive()
        assert errors == [("B", denied)]
        assert b.ticket_path is None and list(b.queue_root.glob("*.json")) == []
        tc.start()
        wait_until(lambda: c.ticket_path is not None and c.ticket_path.is_file())
        assert order == [] and held.lock_path.read_bytes() == owner_bytes
        held.release()
        tc.join(2)
        assert not tc.is_alive() and order == ["C"] and errors == [("B", denied)]
    assert not held.lock_path.exists() and list(b.queue_root.glob("*.json")) == []
    with held.authority.transaction():
        held.authority.require_closed()
    assert all(observed.values())
    return {**observed, "normal_existing_owner_returned_false": True,
        "original_permission_error_identity_preserved": True,
        "B_ticket_removed_after_error": True, "order": order, "authority_stayed_closed": True}


def qualification_controls(base):
    results = []
    for case in ("missing", "corrupt", "foreign-namespace", "wrong-live-identity",
                 "blank-token", "read-denied", "wrong-error-path", "non-native"):
        root = base / case
        install_closed(root)
        candidate = lease(root, case, namespace="compile" if case == "non-native" else "native")
        candidate.lock_path.parent.mkdir(parents=True, exist_ok=True)
        publisher = lease(root, "OTHER")
        owner = publisher._owner_payload()
        if case == "foreign-namespace":
            owner["namespace"] = "compile"
        elif case == "wrong-live-identity":
            owner["identity"] = {**owner["identity"], "creation": str(int(owner["identity"]["creation"]) + 1)}
        elif case == "blank-token":
            owner["token"] = ""
        if case != "missing":
            candidate.lock_path.write_text("{" if case == "corrupt" else json.dumps(owner), encoding="utf-8")
        before = candidate.lock_path.read_bytes() if candidate.lock_path.exists() else None
        error_path = str(root / "different.lock") if case == "wrong-error-path" else str(candidate.lock_path)
        denied = PermissionError(errno.EACCES, "modeled observed OS boundary", error_path)

        def reader(path, *, attempts):
            assert attempts == 1
            if case == "read-denied":
                raise PermissionError(errno.EACCES, "modeled owner read denial", str(path))
            return _read_json_object(path, attempts=attempts)

        assert qualified_live_native_owner(candidate, denied, reader=reader) is False
        with denied_publication(candidate, denied):
            try:
                candidate._try_acquire(first=True)
            except PermissionError as actual:
                assert actual is denied
            else:
                raise AssertionError("Original source swallowed unqualified denial")
        after = candidate.lock_path.read_bytes() if candidate.lock_path.exists() else None
        assert before == after
        results.append({"case": case, "qualification": "UNQUALIFIED",
            "original_error_identity_preserved": True, "owner_bytes_or_absence_unchanged": True})
    return results


before = hashes()
with tempfile.TemporaryDirectory(prefix="tip072-owned-", dir=HERE) as directory:
    base = Path(directory)
    fifo = fifo_boundary(base / "fifo")
    controls = qualification_controls(base)
after = hashes()
assert before == after
receipt = {"source_head": "e9f668a049288eb899c580a6b8147e5caedae585",
    "source_tree": "29426b4fa2fdf0aefbcc4e0273b1f465d5b554c3", "source_sha256": after,
    "boundary": "INJECTED_OBSERVED_ERRNO13_NOT_PHYSICAL_WINDOWS_REPRODUCTION",
    "fifo": fifo, "qualification_controls": controls, "source_modified": False,
    "original_CI_owner_at_denial": "UNKNOWN", "original_CI_Windows_OS_cause": "UNKNOWN",
    "Deep_capacity_normal_cause": "UNKNOWN", "MCP_live_runtime_cause": "UNKNOWN"}
with (HERE / "receipt-v1.json").open("x", encoding="utf-8") as output:
    json.dump(receipt, output, indent=2)
    output.write("\n")
print(json.dumps(receipt, indent=2), flush=True)
