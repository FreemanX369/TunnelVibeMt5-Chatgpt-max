"""Product common-admission regressions using disposable roots and harmless effects."""
from __future__ import annotations

import copy
import json
import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from ownership_fixture import install_closed
from vibemql5.core import native_ownership as module
from vibemql5.core.concurrency import ConcurrencyManager, _QueuedFileLease, acquire_native_execution
from vibemql5.core.jobs import JobManager, _atomic_write_json
from vibemql5.core.native_ownership import ObservedProcess, OwnershipAuthority, OwnershipBlocked
from vibemql5.core.facade import ToolFacade
from vibemql5.core.artifacts import ArtifactManager
from vibemql5.worker import acquire_lock


def active_root(root):
    authority = install_closed(root)
    lease = acquire_native_execution(root, "INTENT", kind="fixture", wait_seconds=0)
    expected = authority.arm(lease)
    lease.release()
    return authority, expected


@pytest.mark.parametrize("fault,reason", [
    ("both_missing", "INSTALL_MISSING"), ("marker_missing", "INSTALL_MISSING"),
    ("state_missing", "AUTHORITY_MISSING"), ("marker_corrupt", "INSTALL_INVALID"),
    ("state_corrupt", "AUTHORITY_INVALID"), ("marker_version", "INSTALL_INVALID"),
    ("state_version", "AUTHORITY_INVALID"), ("epoch", "EPOCH_MISMATCH"),
    ("generation", "AUTHORITY_INVALID"), ("active_shape", "AUTHORITY_INVALID"),
    ("marker_shape", "INSTALL_INVALID"), ("state_shape", "AUTHORITY_INVALID"),
])
def test_installation_denies_without_lazy_reset(tmp_path, fault, reason):
    authority = install_closed(tmp_path)
    if fault in {"both_missing", "marker_missing"}: authority.marker_path.unlink()
    if fault in {"both_missing", "state_missing"}: authority.path.unlink()
    if fault.endswith("corrupt"):
        (authority.marker_path if fault.startswith("marker") else authority.path).write_bytes(b'{"secret":"DO_NOT_LEAK"')
    if fault in {"marker_version", "marker_shape"}:
        marker = json.loads(authority.marker_path.read_text())
        marker["schema" if fault.endswith("version") else "disposition"] = "future/2" if fault.endswith("version") else []
        _atomic_write_json(authority.marker_path, marker)
    if fault in {"state_version", "epoch", "generation", "active_shape", "state_shape"}:
        state = json.loads(authority.path.read_text())
        key, value = {"state_version": ("schema", "future/2"), "epoch": ("epoch", "old-backup"),
                      "generation": ("generation", 0), "active_shape": ("disposition", "ACTIVE"),
                      "state_shape": ("phase", [])}[fault]
        state[key] = value
        _atomic_write_json(authority.path, state)
    before = {p: p.read_bytes() if p.exists() else None for p in (authority.marker_path, authority.path)}
    with pytest.raises(OwnershipBlocked, match=reason):
        acquire_native_execution(tmp_path, "DENIED", kind="test", wait_seconds=0)
    assert authority.status() == {"schema": module.SCHEMA, "admission": "BLOCKED", "reason": reason}
    assert before == {p: p.read_bytes() if p.exists() else None for p in before}
    assert not (tmp_path / "runs" / ".active.lock").exists()
    assert "DO_NOT_LEAK" not in str(authority.status())


@pytest.mark.parametrize("window", [1, 2])
def test_interrupted_installation_stays_blocked_on_fresh_object(tmp_path, window):
    authority = install_closed(tmp_path, stop_after=window)
    original = authority.marker_path.read_bytes()
    with pytest.raises(OwnershipBlocked, match="INSTALL_MIGRATING"):
        acquire_native_execution(tmp_path, "AFTER-CRASH", kind="test", wait_seconds=0)
    assert OwnershipAuthority(tmp_path).status()["reason"] == "INSTALL_MIGRATING"
    assert authority.marker_path.read_bytes() == original


def test_epoch_restore_never_resets_active_generation(tmp_path):
    authority, expected = active_root(tmp_path)
    marker = json.loads(authority.marker_path.read_text())
    _atomic_write_json(authority.marker_path, {**marker, "epoch": "restored-old-epoch"})
    with pytest.raises(OwnershipBlocked, match="EPOCH_MISMATCH"):
        authority.close_zero_attempt(expected)
    assert json.loads(authority.path.read_text())["generation"] == expected["generation"]
    assert json.loads(authority.path.read_text())["disposition"] == "ACTIVE"


def test_owned_intent_create_order_and_unknown_creation_survive_restart(tmp_path):
    authority = install_closed(tmp_path)
    with pytest.raises(OwnershipBlocked, match="OWNED_NATIVE_LEASE_REQUIRED"):
        authority.arm(SimpleNamespace())
    lease = acquire_native_execution(tmp_path, "ORDER", kind="fixture", wait_seconds=0)
    armed = authority.arm(lease)
    with pytest.raises(OwnershipBlocked, match="BIND_ORDER_INVALID"):
        with ObservedProcess(os.getpid()) as process:
            authority.bind_worker(armed, process)
    closed = authority.close_zero_attempt(armed)
    assert closed["generation"] == armed["generation"]
    second = authority.arm(lease)
    assert second["generation"] == armed["generation"] + 1
    attempted = authority.create_attempt(second)  # create API would be next, never inferred.
    lease.release()
    with pytest.raises(OwnershipBlocked, match="CREATION_OUTCOME_UNKNOWN"):
        OwnershipAuthority(tmp_path).close_zero_attempt(attempted)
    assert authority.load()["worker"] is None
    with pytest.raises(OwnershipBlocked, match="ACTIVE_RECOVERY_REQUIRED"):
        acquire_native_execution(tmp_path, "UNKNOWN-CREATE", kind="test", wait_seconds=0)


@pytest.mark.parametrize("point", ["before", "after"])
def test_create_attempt_publication_fault_leaves_recovery_required(tmp_path, monkeypatch, point):
    authority = install_closed(tmp_path)
    lease = acquire_native_execution(tmp_path, "PUBLISH", kind="fixture", wait_seconds=0)
    armed = authority.arm(lease)
    write = module._atomic_write_json
    def fail(path, state):
        if point == "after": write(path, state)
        raise OSError("injected bounded persistence fault")
    monkeypatch.setattr(module, "_atomic_write_json", fail)
    with pytest.raises(OwnershipBlocked, match="PUBLICATION_UNCERTAIN"):
        authority.create_attempt(armed)
    state = OwnershipAuthority(tmp_path).load()
    assert state["disposition"] == "ACTIVE"
    assert state["phase"] == ("ARMED" if point == "before" else "CREATE_ATTEMPT")
    lease.release()
    with pytest.raises(OwnershipBlocked):
        acquire_native_execution(tmp_path, "NO-EFFECT", kind="test", wait_seconds=0)


@pytest.mark.parametrize("corrupt", [False, True])
def test_active_or_invalid_authority_keeps_dead_owner_lock(tmp_path, corrupt):
    authority, expected = active_root(tmp_path)
    lock = tmp_path / "runs" / ".active.lock"
    original = json.dumps({"pid": 99999999, "token": "stale", "operation_id": "dead"}).encode()
    lock.write_bytes(original)
    if corrupt: authority.path.write_bytes(b'{')
    lease = _QueuedFileLease(tmp_path, namespace="native", operation_id="NEXT", kind="test",
        actor=None, wait_seconds=0, lock_path=lock)
    with pytest.raises(OwnershipBlocked): lease._cleanup_stale_lock()
    with pytest.raises(OwnershipBlocked): lease.acquire()
    assert lock.read_bytes() == original
    if not corrupt: assert authority.load() == expected


def test_queued_waiter_checks_winning_admission_and_release_preserves_active(tmp_path):
    authority = install_closed(tmp_path)
    held = acquire_native_execution(tmp_path, "OWNER", kind="fixture", wait_seconds=0)
    outcomes = queue.Queue()
    def wait():
        try:
            lease = acquire_native_execution(tmp_path, "WAITER", kind="fixture", wait_seconds=3)
        except BaseException as exc: outcomes.put(exc)
        else:
            lease.release(); outcomes.put("ADMITTED")
    thread = threading.Thread(target=wait)
    thread.start()
    deadline = time.monotonic() + 2
    while not list((tmp_path / "state" / "concurrency" / "native-waiters").glob("*.json")):
        assert time.monotonic() < deadline
        time.sleep(.01)
    expected = authority.arm(held)
    held.unlink()
    thread.join(3)
    assert not thread.is_alive()
    outcome = outcomes.get_nowait()
    assert isinstance(outcome, OwnershipBlocked), repr(outcome)
    assert authority.load() == expected
    with pytest.raises(OwnershipBlocked): acquire_lock(tmp_path, "WORKER", wait_seconds=0)
    # Actual stale snapshot CAS cannot close its later successor.
    authority.close_zero_attempt(expected)
    successor_lease = acquire_lock(tmp_path, "SUCCESSOR", wait_seconds=0)
    successor = authority.arm(successor_lease)
    with pytest.raises(OwnershipBlocked, match="STALE_AUTHORITY_CAS"):
        authority.close_zero_attempt(expected)
    assert authority.load() == successor
    successor_lease.release()


def test_finally_and_failed_worker_unlink_do_not_close_authority(tmp_path, monkeypatch):
    authority = install_closed(tmp_path)
    with pytest.raises(ValueError, match="effect failed"):
        with ConcurrencyManager(tmp_path).native_execution("FINALLY", kind="fixture", wait_seconds=0) as lease:
            expected = authority.arm(lease)
            raise ValueError("effect failed")
    assert authority.load() == expected
    authority.close_zero_attempt(expected)
    lease = acquire_lock(tmp_path, "WORKER-RELEASE", wait_seconds=0)
    expected = authority.arm(lease)
    original = Path.unlink
    def fail(path, **kwargs):
        if path == lease.lock_path: raise PermissionError("injected unlink refusal")
        return original(path, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail)
        with pytest.raises(PermissionError): lease.unlink()
    assert authority.load() == expected and lease.lock_path.exists()
    lease.unlink()
    assert authority.load() == expected


def test_authority_guard_unavailable_is_sanitized_status_and_restore_pending(tmp_path, monkeypatch):
    install_closed(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    authority = OwnershipAuthority(tmp_path)
    original = Path.open
    def denied(path, *args, **kwargs):
        if path == authority.lock_path: raise PermissionError("PRIVATE_HOST_PATH")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", denied)
    assert authority.status()["reason"] == "AUTHORITY_GUARD_UNAVAILABLE"
    out = manager.get_job(job_id)
    assert out["state"] == "TESTING" and out["cancel_requested"]
    assert out["cancel_terminal_restore_requirement"]["ownership_reason"] == "AUTHORITY_GUARD_UNAVAILABLE"
    assert "PRIVATE_HOST_PATH" not in str(authority.status())


def configure_root(root):
    (root / "config").mkdir(exist_ok=True)
    _atomic_write_json(root / "config" / "terminals.json", {"terminals": []})
    _atomic_write_json(root / "config" / "settings.json", {
        "resource_guard": {}, "retention": {}, "jobs": {"max_concurrent": 1},
        "defaults": {"terminal": "MT5-2"}})


def restore_job(root, monkeypatch):
    import vibemql5.core.jobs as jobs
    manager = JobManager(root)
    job = manager.store.create({"workspace": "demo", "ea": "Experts/Demo.mq5", "terminal": "MT5-2"})
    job.update(state="TESTING", cancel_requested=True)
    manager.store.save(job)
    ArtifactManager(root).write_phase_receipt(job["job_id"], "handoff", {
        "schema_version": "1.0", "phase": "HANDOFF", "status": "PASSED", "evidence": {
            "was_running": True, "login": 123, "terminal": "MT5-2", "terminal_path": "fixture-terminal"}})
    monkeypatch.setattr(jobs, "_discover_worker_pids", lambda _job: [])
    return manager, job["job_id"]


@pytest.mark.parametrize("entry", ["cancel", "get_job", "startup"])
def test_actual_cancel_read_startup_chain_keeps_restore_pending(tmp_path, monkeypatch, entry):
    authority, expected = active_root(tmp_path)
    configure_root(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    from vibemql5.core.mt5_preflight import MT5Preflight
    import vibemql5.core.terminal_handoff as handoff
    effects = []
    monkeypatch.setattr(MT5Preflight, "probe", lambda *a, **k: effects.append("IPC"))
    monkeypatch.setattr(handoff, "restart_normal_terminal", lambda *a, **k: effects.append("RESTART"))
    if entry == "cancel": out = manager.cancel_job(job_id, wait_seconds=0)
    elif entry == "get_job": out = manager.get_job(job_id)
    else:
        from vibemql5.adapters.mcp import create_server
        server = create_server(tmp_path)
        assert len(server._tool_manager._tools) == 85
        assert server._tool_manager._tools["health"].fn()["concurrency"]["native_ownership"]["reason"] == "ACTIVE_RECOVERY_REQUIRED"
        assert server._tool_manager._tools["get_job"].fn(job_id=job_id)["state"] == "TESTING"
        out = manager.store.load(job_id)
    assert effects == []
    assert out["state"] == "TESTING" and out["cancel_requested"] is True
    assert out["cancel_stop_proof"]["stopped"] is True
    restore = out["cancel_terminal_restore_requirement"]
    assert restore["complete"] is False and restore["error"] == "LIVE_RECOVERY_REQUIRED"
    assert restore["ownership_reason"] == "ACTIVE_RECOVERY_REQUIRED"
    assert authority.load() == expected
    assert not any(event["kind"] == "JOB_TERMINAL" for event in out.get("events", []))


def test_cancel_restore_does_not_wait_on_its_own_native_lease(tmp_path, monkeypatch):
    install_closed(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    held = acquire_lock(tmp_path, job_id, wait_seconds=0)
    started = time.monotonic()
    out = manager.get_job(job_id)
    elapsed = time.monotonic() - started
    assert out["cancel_terminal_restore_requirement"]["ownership_reason"] == "NATIVE_LEASE_BUSY"
    assert out["state"] == "TESTING" and held.exists()
    held.release()
    assert elapsed < 2  # bounded fixture observation, not a production latency guarantee.


def test_existing_complete_cancel_proof_is_separate_from_ownership(tmp_path, monkeypatch):
    authority, expected = active_root(tmp_path)
    configure_root(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    ArtifactManager(tmp_path).write_phase_receipt(job_id, "cleanup", {
        "schema_version": "1.0", "phase": "CLEANUP", "status": "PASSED",
        "evidence": {"was_running": True, "reconnected": True}})
    out = manager.get_job(job_id)
    assert out["state"] == "CANCELLED"
    assert out["cancel_terminal_restore_requirement"]["reason"] == "WORKER_CLEANUP_RECONNECTED"
    assert authority.load() == expected  # a historical exact proof never clears ownership.


def test_all_actual_common_entry_paths_deny_callbacks(tmp_path, monkeypatch):
    authority, expected = active_root(tmp_path)
    (tmp_path / "workspaces" / "demo" / "Experts").mkdir(parents=True)
    (tmp_path / "workspaces" / "demo" / "Experts" / "Demo.mq5").write_text("void OnTick(){}")
    configure_root(tmp_path)
    facade = ToolFacade(tmp_path)
    import vibemql5.core.facade as facade_module
    from vibemql5.backend_admin.core import BackendAdmin
    effects = []
    monkeypatch.setattr(facade, "_require_mt5_capable_runtime", lambda: None)
    class Live:
        def __init__(self, *args): effects.append("SDK")
    monkeypatch.setattr(facade_module, "LiveTerminal", Live)
    monkeypatch.setattr(facade_module.CompilerDriver, "compile", lambda *a, **k: effects.append("COMPILER"))
    monkeypatch.setattr(facade.iterations, "get", lambda *a: {"state": "MUTATED", "project_id": "p"})
    monkeypatch.setattr(facade.iterations, "resume", lambda *a: effects.append("ITERATION-COMPILER"))
    admin = BackendAdmin(tmp_path)
    monkeypatch.setattr(admin, "_execute_powershell", lambda *a: effects.append("POWERSHELL"))
    calls = [facade.get_terminal_live_state, facade.get_account_snapshot, facade.list_live_charts,
             lambda: facade.get_symbol_snapshot("EURUSD"), lambda: facade.copy_rates("EURUSD"),
             lambda: facade.copy_ticks("EURUSD", "2026-10-02T00:00:00Z"),
             lambda: facade.capture_live_chart(1), lambda: facade.compile_ea("demo", "Experts/Demo.mq5", mock=True),
             lambda: facade.resume_iteration("I", 1, "digest"),
             lambda: admin.run_powershell("harmless fixture", confirm=True)]
    for call in calls:
        with pytest.raises(OwnershipBlocked, match="ACTIVE_RECOVERY_REQUIRED"): call()
    with pytest.raises(OwnershipBlocked): acquire_lock(tmp_path, "DIRECT-TESTER", wait_seconds=0)
    assert effects == [] and authority.load() == expected


def _contender(root, name, events, gate, use_mutation=True):
    try:
        events.put(("queued", name))
        manager = ConcurrencyManager(Path(root))
        with manager.mutation("fixture", wait_seconds=5) if use_mutation else nullcontext():
            lease = acquire_native_execution(Path(root), name, kind="fixture", wait_seconds=5)
            try:
                events.put(("enter", name, time.monotonic()))
                if name == "A": gate.wait(4)
                time.sleep(.03)
                events.put(("leave", name, time.monotonic()))
            finally: lease.release()
    except BaseException as exc: events.put(("failure", name, repr(exc))); raise


def test_two_process_mutation_native_capacity_one_and_order(tmp_path):
    install_closed(tmp_path)
    context = multiprocessing.get_context("spawn")
    events, gate = context.Queue(), context.Event()
    a = context.Process(target=_contender, args=(str(tmp_path), "A", events, gate))
    b = context.Process(target=_contender, args=(str(tmp_path), "B", events, gate))
    a.start()
    seen = [events.get(timeout=5), events.get(timeout=5)]
    assert seen[-1][0:2] == ("enter", "A"), seen
    b.start(); seen.append(events.get(timeout=5)); gate.set()
    for process in (a, b): process.join(7); assert process.exitcode == 0
    while True:
        try: seen.append(events.get(timeout=.2))
        except queue.Empty: break
    assert not [event for event in seen if event[0] == "failure"], seen
    effects = [event[:2] for event in seen if event[0] in {"enter", "leave"}]
    assert effects == [("enter", "A"), ("leave", "A"), ("enter", "B"), ("leave", "B")]
    assert not (tmp_path / "runs" / ".active.lock").exists()


@pytest.mark.parametrize("invalid_identity", ["unexpected", [], {"pid": 1}, {"pid": 1, "creation": "nonnumeric", "image": "/fixture"},
    {"pid": 1, "creation": "1", "image": sys.executable},
    {"pid": 1, "creation": "1" * 5000, "image": sys.executable}])
def test_closed_corrupt_identity_never_deletes_live_owner(tmp_path, invalid_identity):
    install_closed(tmp_path)
    lock = tmp_path / "runs/.active.lock"
    _atomic_write_json(lock, {"pid": os.getpid(), "token": "live-owner", "identity": invalid_identity})
    before = lock.read_bytes()
    with pytest.raises(TimeoutError):
        acquire_native_execution(tmp_path, "NO-DELETE", kind="fixture", wait_seconds=0)
    assert lock.read_bytes() == before


def _recover_or_acquire(root, expected, name, gate, events):
    try:
        gate.wait(5)
        authority = OwnershipAuthority(Path(root))
        if name.startswith("recover"):
            try: authority.close_zero_attempt(expected)
            except OwnershipBlocked as exc: events.put((name, "blocked", exc.reason))
            else: events.put((name, "closed"))
        else:
            deadline = time.monotonic() + 4
            while True:
                try: lease = acquire_native_execution(Path(root), name, kind="fixture", wait_seconds=0)
                except OwnershipBlocked:
                    if time.monotonic() > deadline: raise
                    time.sleep(.01)
                else: break
            successor = authority.arm(lease)
            events.put((name, "successor", successor["generation"]))
            time.sleep(.03)
            lease.release()
    except BaseException as exc: events.put((name, "failure", repr(exc))); raise


def test_multiprocess_recovery_acquire_race_rejects_stale_successor_cas(tmp_path):
    authority, expected = active_root(tmp_path)
    context = multiprocessing.get_context("spawn")
    gate, events = context.Event(), context.Queue()
    processes = [context.Process(target=_recover_or_acquire, args=(str(tmp_path), expected, name, gate, events))
                 for name in ("recover-A", "recover-B", "acquire-C")]
    started = time.monotonic()
    for process in processes: process.start()
    gate.set()
    for process in processes: process.join(8); assert process.exitcode == 0
    outcomes = [events.get(timeout=2) for _ in processes]
    assert sum(row[1] == "closed" for row in outcomes) == 1, outcomes
    assert sum(row[1] == "blocked" for row in outcomes) == 1, outcomes
    assert sum(row[1] == "successor" for row in outcomes) == 1, outcomes
    successor = authority.load()
    assert successor["generation"] == expected["generation"] + 1
    with pytest.raises(OwnershipBlocked, match="STALE_AUTHORITY_CAS"):
        authority.close_zero_attempt(expected)
    assert authority.load() == successor
    elapsed = time.monotonic() - started
    assert elapsed < 10  # observation only, no hard runtime deadline claim.


def test_native_fifo_wait_and_effect_do_not_hold_authority_guard(tmp_path):
    authority = install_closed(tmp_path)
    held = acquire_native_execution(tmp_path, "HOLD", kind="fixture", wait_seconds=0)
    outcomes = queue.Queue()
    def contender():
        try:
            lease = acquire_native_execution(tmp_path, "WAIT", kind="fixture", wait_seconds=3)
            # This status transaction would deadlock if admission retained its guard.
            outcomes.put(("effect", authority.status()["admission"]))
            lease.release()
        except BaseException as exc: outcomes.put(("failure", repr(exc)))
    thread = threading.Thread(target=contender); thread.start()
    deadline = time.monotonic() + 2
    while not list((tmp_path / "state/concurrency/native-waiters").glob("*.json")):
        assert time.monotonic() < deadline; time.sleep(.01)
    started = time.monotonic()
    assert authority.status()["admission"] == "AVAILABLE"
    assert time.monotonic() - started < 2
    held.release(); thread.join(4)
    assert not thread.is_alive()
    assert outcomes.get_nowait() == ("effect", "AVAILABLE")


def test_released_native_lease_cannot_progress_future_producer(tmp_path):
    authority, expected = active_root(tmp_path)
    with pytest.raises(OwnershipBlocked, match="OWNED_NATIVE_LEASE_REQUIRED"):
        authority.create_attempt(expected)
    assert authority.load() == expected


@pytest.mark.parametrize("method", ["existing", "restart"])
def test_closed_cancel_restore_effect_runs_under_real_lease(tmp_path, monkeypatch, method):
    authority = install_closed(tmp_path)
    configure_root(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    from vibemql5.core.inventory import TerminalInventory
    from vibemql5.core.mt5_preflight import MT5Preflight
    import vibemql5.core.terminal_handoff as handoff
    monkeypatch.setattr(TerminalInventory, "get", lambda *a: SimpleNamespace(terminal_path="fixture-terminal"))
    monkeypatch.setattr(handoff, "running_pids_for_executable", lambda *a: [12345] if method == "existing" else [])
    calls = []
    def effect(kind):
        lock = json.loads((tmp_path / "runs/.active.lock").read_text())
        assert lock["kind"] == "cancel_terminal_restore"
        # Reentrant authority read during effect must be possible.
        assert authority.status()["admission"] == "AVAILABLE"
        calls.append(kind)
        return {"ok": True, "_login": 123} if kind == "IPC" else {"reconnected": True, "restart_pid": 23456}
    monkeypatch.setattr(MT5Preflight, "probe", lambda *a, **k: effect("IPC"))
    monkeypatch.setattr(handoff, "restart_normal_terminal", lambda *a, **k: effect("RESTART"))
    out = manager.get_job(job_id)
    assert out["state"] == "CANCELLED"
    assert calls == ["IPC" if method == "existing" else "RESTART"]
    assert out["cancel_terminal_restore_requirement"]["complete"] is True
    assert not (tmp_path / "runs/.active.lock").exists()


def test_exact_owned_job_stop_can_complete_while_restore_remains_pending(tmp_path, monkeypatch):
    authority, expected = active_root(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    import vibemql5.core.jobs as jobs
    live = [True]
    ref = {"pid": 456789, "start_ticks": "100", "creation_date": "100",
           "executable": "/harmless/fixture", "command_line": "fixture --job-id " + job_id}
    manager.store.update_fields(job_id, processes={"metaeditor": {"pid": ref["pid"], "identity": ref}})
    monkeypatch.setattr(jobs, "_process_identity", lambda pid: dict(ref) if live[0] and pid == ref["pid"] else None)
    monkeypatch.setattr(jobs, "_pid_exists", lambda pid: live[0] and pid == ref["pid"])
    stops = []
    def exact_stop(pid, signal):
        assert pid == ref["pid"]
        stops.append(pid); live[0] = False
    monkeypatch.setattr(jobs.os, "kill", exact_stop)
    out = manager.cancel_job(job_id, wait_seconds=0)
    assert stops == [ref["pid"]]
    assert out["cancel_orphan_role_stop"][0]["stopped"] is True
    assert out["cancel_stop_proof"]["stopped"] is True
    assert out["state"] == "TESTING" and out["cancel_requested"]
    assert out["cancel_terminal_restore_requirement"]["ownership_reason"] == "ACTIVE_RECOVERY_REQUIRED"
    assert authority.load() == expected


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("fault", ["sequence", "ticket"])
def test_restore_queue_damage_stays_sanitized_and_readonly_startup_alive(tmp_path, monkeypatch, active, fault):
    if active: authority, expected = active_root(tmp_path)
    else: authority = install_closed(tmp_path)
    configure_root(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    if fault == "sequence":
        (tmp_path / "state/concurrency/native-sequence.json").write_bytes(b'{"private":"PRIVATE_QUEUE_PATH"')
    else:
        original = os.open
        def deny(path, flags, *args, **kwargs):
            if "native-waiters" in str(path): raise PermissionError("PRIVATE_QUEUE_PATH")
            return original(path, flags, *args, **kwargs)
        monkeypatch.setattr(os, "open", deny)
    out = manager.get_job(job_id)
    assert out["state"] == "TESTING" and out["cancel_requested"]
    restore = out["cancel_terminal_restore_requirement"]
    assert restore["complete"] is False and restore["recovery_attempted"] is False
    assert restore["ownership_reason"] == ("ACTIVE_RECOVERY_REQUIRED" if active else "NATIVE_LEASE_UNAVAILABLE")
    assert "PRIVATE_QUEUE_PATH" not in str(restore)
    from vibemql5.adapters.mcp import create_server
    server = create_server(tmp_path)
    assert len(server._tool_manager._tools) == 85
    assert server._tool_manager._tools["get_job"].fn(job_id=job_id)["state"] == "TESTING"


@pytest.mark.parametrize("point", ["before", "after"])
def test_arm_publication_window_has_no_effect_before_committed_intent(tmp_path, monkeypatch, point):
    authority = install_closed(tmp_path)
    lease = acquire_native_execution(tmp_path, "ARM-FAULT", kind="fixture", wait_seconds=0)
    write = module._atomic_write_json
    calls = []
    def fault(path, state):
        if point == "after": write(path, state)
        raise OSError("controlled arm publication failure")
    monkeypatch.setattr(module, "_atomic_write_json", fault)
    with pytest.raises(OwnershipBlocked, match="PUBLICATION_UNCERTAIN"):
        expected = authority.arm(lease)
        calls.append("CREATE-API")
    assert calls == []
    state = authority.load()
    assert state["disposition"] == ("CLOSED" if point == "before" else "ACTIVE")
    assert state["generation"] == (1 if point == "before" else 2)
    lease.release()
    if point == "after":
        with pytest.raises(OwnershipBlocked): acquire_lock(tmp_path, "NO-SUCCESSOR", wait_seconds=0)


@pytest.mark.parametrize("point", ["before", "after", "readback"])
def test_zero_attempt_closure_publication_failure_reinstates_active_barrier(tmp_path, monkeypatch, point):
    authority, expected = active_root(tmp_path)
    write, load = module._atomic_write_json, OwnershipAuthority.load
    read_fault = [True]
    def fault(path, state):
        if state["disposition"] == "CLOSED":
            if point == "after": write(path, state)
            if point != "readback": raise OSError("controlled closure publication failure")
        write(path, state)
    def readback(self):
        state = load(self)
        if point == "readback" and state["disposition"] == "CLOSED" and read_fault[0]:
            read_fault[0] = False
            raise OwnershipBlocked("AUTHORITY_INVALID")
        return state
    monkeypatch.setattr(module, "_atomic_write_json", fault)
    monkeypatch.setattr(OwnershipAuthority, "load", readback)
    with pytest.raises(OwnershipBlocked): authority.close_zero_attempt(expected)
    assert authority.load() == expected
    with pytest.raises(OwnershipBlocked): acquire_lock(tmp_path, "NO-SUCCESSOR", wait_seconds=0)


def test_missing_independent_os_image_never_becomes_current_directory_evidence(monkeypatch):
    with ObservedProcess(os.getpid()) as process:
        if os.name == "nt":
            # Inject an unavailable image result while retaining actual live handle/times.
            monkeypatch.setattr(process.kernel, "QueryFullProcessImageNameW", lambda *args: True)
        else:
            original = os.readlink
            def missing(path, *args, **kwargs):
                if str(path).endswith("/exe"): raise PermissionError("image unavailable")
                return original(path, *args, **kwargs)
            monkeypatch.setattr(os, "readlink", missing)
        with pytest.raises(OwnershipBlocked, match="PROCESS_IDENTITY_UNPROVEN"):
            process.identity()
        assert process._live_identity is None


@pytest.mark.parametrize("fault", ["runs_mkdir", "ticket_write", "ticket_fsync", "owner_write", "owner_fsync"])
def test_restore_admission_fault_cleans_exact_ticket_then_healthy_acquire(tmp_path, monkeypatch, fault):
    install_closed(tmp_path)
    manager, job_id = restore_job(tmp_path, monkeypatch)
    with monkeypatch.context() as patch:
        if fault == "runs_mkdir":
            original = Path.mkdir
            def unavailable(path, *args, **kwargs):
                if path == tmp_path / "runs" and list((tmp_path / "state/concurrency/native-waiters").glob("*.json")):
                    raise PermissionError("controlled native directory failure after queue publication")
                return original(path, *args, **kwargs)
            patch.setattr(Path, "mkdir", unavailable)
        elif fault.endswith("_write"):
            original = os.write
            def unavailable(fd, payload):
                is_owner = b'"acquired_at":' in payload
                if b'"namespace":"native"' in payload and is_owner == (fault == "owner_write"):
                    raise OSError("controlled native admission write failure")
                return original(fd, payload)
            patch.setattr(os, "write", unavailable)
        else:
            original = os.fsync
            # Sequence, ticket and owner each fsync in that order before admission.
            calls = [0]
            def unavailable(fd):
                calls[0] += 1
                if calls[0] == (2 if fault == "ticket_fsync" else 3):
                    raise OSError("controlled native admission fsync failure")
                return original(fd)
            patch.setattr(os, "fsync", unavailable)
        out = manager.get_job(job_id)
        assert out["state"] == "TESTING" and out["cancel_requested"]
        assert out["cancel_terminal_restore_requirement"]["ownership_reason"] == "NATIVE_LEASE_UNAVAILABLE"
    waiters = tmp_path / "state/concurrency/native-waiters"
    assert not list(waiters.glob("*.json")), "live controller abandoned its owned FIFO ticket"
    assert not (tmp_path / "runs/.active.lock").exists(), "no-effect attempt abandoned native owner"
    lease = acquire_native_execution(tmp_path, "AFTER-FAULT", kind="fixture", wait_seconds=0)
    assert lease.operation_id == "AFTER-FAULT"
    lease.release()
    assert not list(waiters.glob("*.json"))


def test_two_process_native_only_contention_preserves_fifo_capacity(tmp_path):
    install_closed(tmp_path)
    context = multiprocessing.get_context("spawn")
    events, gate = context.Queue(), context.Event()
    a = context.Process(target=_contender, args=(str(tmp_path), "A", events, gate, False))
    b = context.Process(target=_contender, args=(str(tmp_path), "B", events, gate, False))
    a.start()
    seen = [events.get(timeout=5), events.get(timeout=5)]
    assert seen[-1][:2] == ("enter", "A"), seen
    b.start(); seen.append(events.get(timeout=5))
    deadline = time.monotonic() + 3
    waiters = tmp_path / "state/concurrency/native-waiters"
    while not list(waiters.glob("*.json")):
        assert time.monotonic() < deadline; time.sleep(.01)
    assert json.loads((tmp_path / "runs/.active.lock").read_text())["operation_id"] == "A"
    assert not (tmp_path / "state/concurrency/mutation.lock").exists()
    gate.set()
    for process in (a, b): process.join(7); assert process.exitcode == 0
    while True:
        try: seen.append(events.get(timeout=.2))
        except queue.Empty: break
    assert not [row for row in seen if row[0] == "failure"], seen
    effects = [row for row in seen if row[0] in {"enter", "leave"}]
    assert [row[:2] for row in effects] == [("enter", "A"), ("leave", "A"), ("enter", "B"), ("leave", "B")]
    assert effects[2][2] >= effects[1][2]
    assert not (tmp_path / "runs/.active.lock").exists()
