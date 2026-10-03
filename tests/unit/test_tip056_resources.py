from pathlib import Path
import multiprocessing
import time

import pytest

from ownership_fixture import install_closed
from vibemql5.core.concurrency import ConcurrencyManager
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


def _fifo_worker(root, operation_id, physical, output):
    try:
        authority = OwnershipAuthority(Path(root))
        resources = ResourceAuthority(root, max_records=10, wait_ms=1000)
        with ConcurrencyManager(Path(root)).native_execution(operation_id, kind="fixture", wait_seconds=5) as lease:
            armed = authority.arm(lease)
            row = resources.reserve(operation_id, kind="tester", resources=physical, lease=lease, armed_ownership=armed)
            output.put(operation_id)
            authority.close_zero_attempt(armed); resources.release(row["reservation_id"])
    except Exception as error:
        output.put(type(error).__name__ + ":" + str(error))


def test_real_process_fifo_and_atomic_resource_writers_share_legacy_lease(tmp_path):
    install_closed(tmp_path); ResourceAuthority(tmp_path, initialize=True, max_records=10, wait_ms=1000)
    physical = bindings(tmp_path); ctx = multiprocessing.get_context("spawn"); output = ctx.Queue()
    with ConcurrencyManager(tmp_path).native_execution("legacy-held", kind="fixture", wait_seconds=0):
        first = ctx.Process(target=_fifo_worker, args=(tmp_path, "first", physical, output)); first.start()
        deadline = time.monotonic() + 5
        while len(list((tmp_path / "state" / "concurrency" / "native-waiters").glob("*.json"))) < 1:
            assert time.monotonic() < deadline
            time.sleep(.01)
        second = ctx.Process(target=_fifo_worker, args=(tmp_path, "second", physical, output)); second.start()
        while len(list((tmp_path / "state" / "concurrency" / "native-waiters").glob("*.json"))) < 2:
            assert time.monotonic() < deadline
            time.sleep(.01)
    first.join(10); second.join(10)
    assert first.exitcode == second.exitcode == 0
    assert [output.get(timeout=2), output.get(timeout=2)] == ["first", "second"]
    rows = ResourceAuthority(tmp_path, max_records=10, wait_ms=1000).snapshot()
    assert len(rows) == 2 and all(row["status"] == "RELEASED" for row in rows)
