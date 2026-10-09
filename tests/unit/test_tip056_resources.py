from pathlib import Path
import json
import multiprocessing
import time

import pytest

from ownership_fixture import install_closed
from fleet_gateway_fixture import preserve_fixture_failure
from vibemql5.core.concurrency import ConcurrencyManager, _QueuedFileLease
from vibemql5.core.native_ownership import OwnershipAuthority, OwnershipBlocked
from vibemql5.fleet.resources import ResourceAuthority, physical_resources
from vibemql5.fleet.job_journal import JournalError


def bindings(root):
    result = {}
    for name in ("executable", "data_root", "include_root", "agent_root"):
        path = root / name
        if name == "executable": path.write_bytes(b"harmless-fixture")
        else: path.mkdir(exist_ok=True)
        result[name] = str(path)
    return result


def test_resource_grant_requires_real_common_lease_and_exact_closed_generation(tmp_path):
    authority = install_closed(tmp_path)
    resources = ResourceAuthority(tmp_path, initialize=True, max_records=10, wait_ms=100)
    physical = bindings(tmp_path)
    with ConcurrencyManager(tmp_path).native_execution("op-a", kind="fixture", wait_seconds=0) as lease:
        armed = authority.arm(lease)
        row = resources.reserve("op-a", kind="tester", resources=physical, lease=lease, armed_ownership=armed)
        assert row["queue_authority"] == "COMMON_NATIVE_FIFO" and row["capacity"] == 1
        with pytest.raises(JournalError, match="EXACT_CLOSURE_UNPROVEN"): resources.release(row["reservation_id"])
        with pytest.raises(OwnershipBlocked):
            with ConcurrencyManager(tmp_path).native_execution("legacy", kind="legacy", wait_seconds=0): pass
        assert resources.reserve("op-a", kind="tester", resources=physical, lease=lease, armed_ownership=armed) == row
        authority.close_zero_attempt(armed)
        assert resources.release(row["reservation_id"])["status"] == "RELEASED"
    assert ResourceAuthority(tmp_path, max_records=10, wait_ms=100).snapshot()[0]["status"] == "RELEASED"


def test_uncertain_ownership_survives_restart_and_never_ttl_closes(tmp_path):
    authority = install_closed(tmp_path); resources = ResourceAuthority(tmp_path, initialize=True, max_records=10, wait_ms=100)
    with ConcurrencyManager(tmp_path).native_execution("op-a", kind="fixture", wait_seconds=0) as lease:
        armed = authority.arm(lease)
        row = resources.reserve("op-a", kind="capture", resources=bindings(tmp_path), lease=lease, armed_ownership=armed)
        resources.uncertain(row["reservation_id"])
    assert ResourceAuthority(tmp_path, max_records=10, wait_ms=100).snapshot()[0]["status"] == "UNKNOWN"
    with pytest.raises(OwnershipBlocked):
        with ConcurrencyManager(tmp_path).native_execution("op-b", kind="fixture", wait_seconds=0): pass
    with pytest.raises(JournalError, match="EXACT_CLOSURE_UNPROVEN"): resources.release(row["reservation_id"])


def test_capacity_above_one_unqualified_and_alias_inode_equivalence(tmp_path):
    with pytest.raises(JournalError, match="NATIVE_CAPACITY_UNQUALIFIED"):
        ResourceAuthority(tmp_path, initialize=True, capacity=2, max_records=10, wait_ms=100)
    paths = bindings(tmp_path)
    alias = tmp_path / "exe-alias"; alias.hardlink_to(paths["executable"])
    one = physical_resources(paths)
    two = physical_resources({**paths, "executable": str(alias)})
    assert next(r for r in one if r["kind"] == "executable")["physical_key"] == next(r for r in two if r["kind"] == "executable")["physical_key"]
    with pytest.raises(JournalError, match="RESOURCE_INDEPENDENCE_UNPROVEN"):
        physical_resources({**paths, "executable": str(tmp_path / "missing")})


@pytest.mark.parametrize("phase,status", [("before_commit", None), ("after_commit", "ACTIVE")])
def test_atomic_full_resource_set_commit_fault_keeps_core_barrier(tmp_path, phase, status):
    authority = install_closed(tmp_path)
    resources = ResourceAuthority(tmp_path, initialize=True, max_records=10, wait_ms=100)
    with ConcurrencyManager(tmp_path).native_execution("op-a", kind="fixture", wait_seconds=0) as lease:
        armed = authority.arm(lease)
        def fault(point):
            if point == phase: raise RuntimeError("fixture fault")
        resources.fault = fault
        with pytest.raises(RuntimeError): resources.reserve("op-a", kind="tester", resources=bindings(tmp_path), lease=lease, armed_ownership=armed)
        resources.fault = None
        rows = resources.snapshot()
        assert bool(rows) == (status is not None)
        if rows:
            assert rows[0]["status"] == status and len(rows[0]["request"]["resources"]) == 4
        assert authority.load()["disposition"] == "ACTIVE"
        authority.close_zero_attempt(armed)
        if rows: resources.release(rows[0]["reservation_id"])


def _fifo_worker(root, operation_id, physical, output, *, queued=None, probe=None, armed=None, close=None):
    original_probe = _QueuedFileLease._try_acquire
    first_probe = [True]
    def controlled_probe(lease, *, first):
        if first_probe[0]:
            first_probe[0] = False
            if queued is not None: queued.set()
            # The real ticket is assigned; observation waits outside the
            # authority transaction before the original admission probe.
            if probe is not None and not probe.wait(timeout=5):
                raise TimeoutError("FIFO_PROBE_CONTROL_TIMEOUT")
        return original_probe(lease, first=first)
    _QueuedFileLease._try_acquire = controlled_probe
    try:
        authority = OwnershipAuthority(Path(root))
        resources = ResourceAuthority(root, max_records=10, wait_ms=1000)
        with ConcurrencyManager(Path(root)).native_execution(operation_id, kind="fixture", wait_seconds=5) as lease:
            ownership = authority.arm(lease)
            row = resources.reserve(operation_id, kind="tester", resources=physical, lease=lease, armed_ownership=ownership)
            if armed is not None: armed.set()
            if close is not None and not close.wait(timeout=5):
                raise TimeoutError("FIFO_CLOSURE_CONTROL_TIMEOUT")
            authority.close_zero_attempt(ownership); resources.release(row["reservation_id"])
        # Success proves actual CLOSED, resource release and native lease release.
        output.put(operation_id)
    except Exception as error:
        output.put(type(error).__name__ + ":" + str(error))
    finally:
        _QueuedFileLease._try_acquire = original_probe


def _join_fifo_workers(*workers):
    for worker in workers:
        worker.join(10)
        assert not worker.is_alive() and worker.exitcode == 0


def test_real_process_fifo_and_atomic_resource_writers_share_legacy_lease(tmp_path):
    authority = install_closed(tmp_path); ResourceAuthority(tmp_path, initialize=True, max_records=10, wait_ms=1000)
    physical = bindings(tmp_path); ctx = multiprocessing.get_context("spawn"); output = ctx.Queue()
    first_queued, second_queued, second_probe = ctx.Event(), ctx.Event(), ctx.Event()
    first = ctx.Process(target=_fifo_worker, args=(tmp_path, "first", physical, output), kwargs={"queued": first_queued})
    second = ctx.Process(target=_fifo_worker, args=(tmp_path, "second", physical, output),
        kwargs={"queued": second_queued, "probe": second_probe})
    try:
        with ConcurrencyManager(tmp_path).native_execution("legacy-held", kind="fixture", wait_seconds=0):
            deadline = time.monotonic() + 5
            first.start(); assert first_queued.wait(timeout=max(0, deadline - time.monotonic()))
            second.start(); assert second_queued.wait(timeout=max(0, deadline - time.monotonic()))
            tickets = sorted((tmp_path / "state" / "concurrency" / "native-waiters").glob("*.json"))
            assert [json.loads(path.read_text())["operation_id"] for path in tickets] == ["first", "second"]
        first.join(10); assert not first.is_alive() and first.exitcode == 0
        assert output.get(timeout=2) == "first"
        assert authority.load()["disposition"] == "CLOSED"
        assert not (tmp_path / "runs" / ".active.lock").exists()
        rows = ResourceAuthority(tmp_path, max_records=10, wait_ms=1000).snapshot()
        assert len(rows) == 1 and rows[0]["status"] == "RELEASED"
        second_probe.set(); second.join(10)
        assert not second.is_alive() and second.exitcode == 0
        assert output.get(timeout=2) == "second"
    finally:
        with preserve_fixture_failure():
            second_probe.set()
            _join_fifo_workers(*(worker for worker in (first, second) if worker.pid is not None))
    rows = ResourceAuthority(tmp_path, max_records=10, wait_ms=1000).snapshot()
    assert len(rows) == 2 and all(row["status"] == "RELEASED" for row in rows)


def test_real_queued_resource_writer_observing_active_is_denied_without_reservation(tmp_path):
    authority = install_closed(tmp_path); ResourceAuthority(tmp_path, initialize=True, max_records=10, wait_ms=1000)
    physical = bindings(tmp_path); ctx = multiprocessing.get_context("spawn"); output = ctx.Queue()
    first_queued, second_queued, second_probe, first_armed, first_close = (ctx.Event() for _ in range(5))
    first = ctx.Process(target=_fifo_worker, args=(tmp_path, "first", physical, output),
        kwargs={"queued": first_queued, "armed": first_armed, "close": first_close})
    second = ctx.Process(target=_fifo_worker, args=(tmp_path, "second", physical, output),
        kwargs={"queued": second_queued, "probe": second_probe})
    try:
        with ConcurrencyManager(tmp_path).native_execution("legacy-held", kind="fixture", wait_seconds=0):
            deadline = time.monotonic() + 5
            first.start(); assert first_queued.wait(timeout=max(0, deadline - time.monotonic()))
            second.start(); assert second_queued.wait(timeout=max(0, deadline - time.monotonic()))
        assert first_armed.wait(timeout=5)
        active = authority.load(); assert active["disposition"] == "ACTIVE"
        second_probe.set(); second.join(10)
        assert not second.is_alive() and second.exitcode == 0
        assert output.get(timeout=2) == "OwnershipBlocked:LIVE_RECOVERY_REQUIRED: native_ownership:ACTIVE_RECOVERY_REQUIRED"
        assert authority.load() == active
        rows = ResourceAuthority(tmp_path, max_records=10, wait_ms=1000).snapshot()
        assert len(rows) == 1 and rows[0]["operation_id"] == "first" and rows[0]["status"] == "ACTIVE"
        assert first.is_alive() and (tmp_path / "runs" / ".active.lock").is_file()
    finally:
        with preserve_fixture_failure():
            second_probe.set(); first_close.set()
            _join_fifo_workers(*(worker for worker in (first, second) if worker.pid is not None))
    assert output.get(timeout=2) == "first"
    assert authority.load()["disposition"] == "CLOSED"
    assert ResourceAuthority(tmp_path, max_records=10, wait_ms=1000).snapshot()[0]["status"] == "RELEASED"
    print("CONTROLLED_QUEUED_ACTIVE_DENIAL_NO_SECOND_RESERVATION")
