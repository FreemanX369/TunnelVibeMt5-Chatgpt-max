import copy
import threading
import time
import multiprocessing
import os

import pytest

from ownership_fixture import install_closed
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.core.native_ownership import OwnershipBlocked
from vibemql5.fleet.job_journal import JournalError
from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator, CONFLICT_MATRIX
from vibemql5.fleet.resources import physical_resources


def profile(root):
    rows = []
    for n in (1, 2):
        folder = root / str(n); folder.mkdir()
        physical = {}
        for field in ("executable", "data_root", "include_root", "agent_root"):
            path = folder / field
            if field == "executable": path.write_bytes(b"harmless-source-fixture")
            else: path.mkdir()
            physical[field] = str(path)
        rows.append({"terminal_id": "term_" + str(n) * 32, "terminal_generation": 1, "resources": physical, "physical_identities": physical_resources(physical)})
    return {"schema": "fleet.capacity-profile/1", "device_id": "dev_" + "a" * 32, "install_epoch": "b" * 32,
        "capacity": 2, "candidate_sha256": "c" * 64, "runtime_sha256": "d" * 64,
        "source_manifest": [], "terminals": rows, "load_receipt": None, "closure_receipt": None,
        "max_records": 20, "lock_wait_ms": 1000, "conflict_matrix": CONFLICT_MATRIX}


def test_parallel_harmless_scopes_and_exact_zero_attempt_closure_without_installation(tmp_path):
    candidate = profile(tmp_path)
    coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    barrier = threading.Barrier(2); phases = []
    def run(n):
        with coordinator.execution("op-" + str(n), kind="tester", terminal_id="term_" + str(n) * 32,
                terminal_generation=1, wait_ms=1000) as scope:
            armed = scope.arm(); barrier.wait(timeout=3)
            phases.append(scope.load()["phase"])
            assert scope.authority is scope and scope.root == tmp_path
            scope.close_zero_attempt(armed)
    threads = [threading.Thread(target=run, args=(n,)) for n in (1, 2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(5); assert not thread.is_alive()
    assert phases == ["ARMED", "ARMED"]
    assert not (tmp_path / "state" / "fleet" / "scoped-install.json").exists()


def test_shared_resources_and_ipc_per_device_cannot_parallelize(tmp_path):
    candidate = profile(tmp_path); candidate["terminals"][1]["resources"]["include_root"] = candidate["terminals"][0]["resources"]["include_root"]
    candidate["terminals"][1]["physical_identities"] = physical_resources(candidate["terminals"][1]["resources"])
    coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    with coordinator.execution("first", kind="tester", terminal_id="term_" + "1" * 32, terminal_generation=1, wait_ms=0):
        with pytest.raises(JournalError, match="SCOPED_LEASE_UNAVAILABLE"):
            with coordinator.execution("second", kind="tester", terminal_id="term_" + "2" * 32, terminal_generation=1, wait_ms=0): pass
    # A disjoint profile still serializes all IPC on this node.
    other = tmp_path / "other"; other.mkdir(); second_profile = profile(other)
    ipc = ScopedResourceCoordinator._for_fixture(other, second_profile, initialize=True)
    with ipc.execution("ipc-one", kind="ipc", terminal_id="term_" + "1" * 32, terminal_generation=1, wait_ms=0):
        with pytest.raises(JournalError, match="SCOPED_LEASE_UNAVAILABLE"):
            with ipc.execution("ipc-two", kind="ipc", terminal_id="term_" + "2" * 32, terminal_generation=1, wait_ms=0): pass


def test_uncertain_scoped_producer_survives_restart_and_blocks_overlapping_resource(tmp_path):
    candidate = profile(tmp_path); candidate["terminals"][1]["physical_identities"] = physical_resources(candidate["terminals"][1]["resources"])
    coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    with coordinator.execution("first", kind="tester", terminal_id="term_" + "1" * 32, terminal_generation=1, wait_ms=0) as scope:
        reference = scope.reference; scope.arm()
    reopened = ScopedResourceCoordinator._for_fixture(tmp_path, candidate)
    assert reopened.read_scope(reference)["status"] == "UNKNOWN"
    with pytest.raises(JournalError, match="SCOPED_LEASE_UNAVAILABLE"):
        with reopened.execution("second", kind="tester", terminal_id="term_" + "1" * 32, terminal_generation=1, wait_ms=0): pass
    with pytest.raises(JournalError, match="SCOPED_OPERATION_RECOVERY_REQUIRED"):
        with reopened.execution("first", kind="tester", terminal_id="term_" + "1" * 32, terminal_generation=1, wait_ms=0): pass


def test_malformed_installed_marker_blocks_unsupported_legacy_without_bootstrap(tmp_path):
    install_closed(tmp_path); marker = tmp_path / "state" / "fleet" / "scoped-install.json"
    marker.parent.mkdir(parents=True, exist_ok=True); marker.write_bytes(b"malformed")
    with pytest.raises(OwnershipBlocked, match="SCOPED_OWNERSHIP_REQUIRED"):
        with ConcurrencyManager(tmp_path).native_execution("legacy", kind="fixture", wait_seconds=0): pass
    with pytest.raises(JournalError):
        ScopedResourceCoordinator.open_installed(tmp_path, device_id="dev_" + "a" * 32,
            trusted_owner_public_key="b" * 64, candidate_sha256="c" * 64, runtime_sha256="d" * 64)
    assert not (tmp_path / "state" / "fleet" / "scoped-resources.sqlite").exists()


def _parallel_worker(root, candidate, number, entered, resume, output):
    try:
        coordinator = ScopedResourceCoordinator._for_fixture(root, candidate)
        with coordinator.execution("process-" + str(number), kind="tester", terminal_id="term_" + str(number) * 32,
                terminal_generation=1, wait_ms=3000) as scope:
            armed = scope.arm(); entered.put(number)
            if not resume.wait(5): raise RuntimeError("fixture barrier")
            scope.close_zero_attempt(armed)
            output.put("CLOSED")
    except Exception as error: output.put(type(error).__name__ + ":" + str(error))


def test_actual_two_os_producers_hold_distinct_scopes_concurrently_and_close(tmp_path):
    candidate = profile(tmp_path); coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    ctx = multiprocessing.get_context("spawn"); entered = ctx.Queue(); output = ctx.Queue(); resume = ctx.Event()
    producers = [ctx.Process(target=_parallel_worker, args=(tmp_path, candidate, n, entered, resume, output)) for n in (1, 2)]
    for process in producers: process.start()
    assert {entered.get(timeout=5), entered.get(timeout=5)} == {1, 2}
    with coordinator.transaction() as db:
        from vibemql5.fleet.job_journal import _decode
        active = [_decode(r[0]) for r in db.execute("SELECT record FROM reservations")]
        assert len(active) == 2 and all(r["phase"] == "ARMED" and r["status"] == "ACQUIRED" for r in active)
    resume.set()
    for process in producers: process.join(10); assert process.exitcode == 0
    assert [output.get(timeout=2), output.get(timeout=2)] == ["CLOSED", "CLOSED"]


def test_scoped_exact_owned_process_handle_closure_and_create_fault(tmp_path):
    import subprocess
    import sys
    from vibemql5.core.native_ownership import ObservedProcess
    from vibemql5.core.native_ownership import OwnershipBlocked
    candidate = profile(tmp_path); coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    with coordinator.execution("real-harmless-child", kind="tester", terminal_id="term_" + "1" * 32,
            terminal_generation=1, wait_ms=0) as scope:
        armed = scope.arm(); attempted = scope.create_attempt(armed)
        process = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"], stdin=subprocess.PIPE)
        observation = ObservedProcess(process.pid)
        try:
            try:
                bound = scope.bind_worker(attempted, observation)
            except OwnershipBlocked as error:
                assert error.reason == "PROCESS_NAMESPACE_UNQUALIFIED"
                assert scope.load()["phase"] == "CREATE_ATTEMPT"
                with pytest.raises(JournalError, match="SCOPED_CREATION_OUTCOME_UNKNOWN"):
                    scope.close_zero_attempt(attempted)
                return  # Exact live image is intentionally unavailable in this container.
            with pytest.raises(JournalError, match="SCOPED_EXACT_EXIT_UNPROVEN"):
                scope.close_owned_worker(bound, observation, descendant_verifier=lambda _: "PREVENTED_BY_BOUNDARY")
            process.communicate(b"x", timeout=5)
            scope.close_owned_worker(bound, observation, descendant_verifier=lambda _: "EXACT_DESCENDANTS_EXITED")
            assert scope.load()["phase"] == "CLOSED"
        finally:
            observation.close()
            if process.poll() is None: process.kill(); process.wait(5)
    with coordinator.execution("ambiguous-create", kind="tester", terminal_id="term_" + "1" * 32,
            terminal_generation=1, wait_ms=0) as scope:
        attempted = scope.create_attempt(scope.arm())
        reference = scope.reference
        with pytest.raises(JournalError, match="SCOPED_CREATION_OUTCOME_UNKNOWN"):
            scope.close_zero_attempt(attempted)
    assert coordinator.read_scope(reference)["status"] == "UNKNOWN"


@pytest.mark.parametrize("field,value", [("token", "not-a-token"), ("epoch", "wrong"), ("generation", True),
    ("worker", {"pid": 1}), ("status", "READY"), ("descendants", "GUESSED")])
def test_malformed_persisted_scope_is_denied_without_successor_admission(tmp_path, field, value):
    import sqlite3
    from vibemql5.fleet.job_journal import canonical, _decode
    candidate = profile(tmp_path); coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    with coordinator.execution("one", kind="tester", terminal_id="term_" + "1" * 32, terminal_generation=1, wait_ms=0): pass
    connection = sqlite3.connect(coordinator.path)
    record = _decode(connection.execute("SELECT record FROM reservations").fetchone()[0])
    record[field] = value
    connection.execute("UPDATE reservations SET record=?", (canonical(record).decode(),)); connection.commit(); connection.close()
    with pytest.raises(JournalError, match="SCOPED_STORE_INVALID"):
        ScopedResourceCoordinator._for_fixture(tmp_path, candidate)


def test_scoped_resource_identity_drift_and_missing_source_candidate_fail_closed(tmp_path):
    candidate = profile(tmp_path); coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, candidate, initialize=True)
    executable = candidate["terminals"][0]["resources"]["executable"]
    import pathlib
    replacement = pathlib.Path(executable + ".new"); replacement.write_bytes(b"replacement"); replacement.replace(executable)
    with pytest.raises(JournalError, match="SCOPED_PHYSICAL_BINDING_CHANGED"):
        ScopedResourceCoordinator._for_fixture(tmp_path, candidate)
    from vibemql5.fleet.scoped_resources import _profile
    with pytest.raises(JournalError): _profile(candidate, tmp_path, physical=True)
