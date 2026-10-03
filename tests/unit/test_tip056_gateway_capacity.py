"""Complete synthetic gateway/node/scoped fixture; no production marker/MT5."""
import hashlib
import threading

import pytest

from test_tip061a_057n import node, freeze, logical_fixture
from test_tip055a_runtime_forensics_identity import ref
from test_tip060_journal import POLICY, verifier, authorize
from vibemql5.core.native_ownership import current_identity
from vibemql5.fleet.native import native_request
from vibemql5.fleet.resources import physical_resources
from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator, VerifiedCapacityRoster, CONFLICT_MATRIX
from vibemql5.fleet.job_journal import GatewayJobJournal, NodeJobJournal, JournalError


def test_gateway_verified_roster_dispatch_and_two_node_threads_hold_actual_scopes(node, tmp_path):
    requests, terminals = [], []
    raw = node["source"].read_bytes()
    for i in (0, 1):
        placement = freeze(node, "iteration-" + str(i), target={**ref(node["registry"], i), "route_generation": 1}, operation="freeze-" + str(i))
        requests.append(native_request(placement, logical_fixture(), [{"path": "Experts/DemoEA.mq5", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}]))
        resources = dict(placement["binding"])
        for kind in ("include_root", "agent_root"):
            folder = tmp_path / (kind + str(i)); folder.mkdir(); resources[kind] = str(folder)
        terminals.append({"terminal_id": placement["target"]["terminal_id"], "terminal_generation": 1,
            "resources": resources, "physical_identities": physical_resources(resources)})
    profile = {"schema": "fleet.capacity-profile/1", "device_id": node["registry"]["device_id"], "install_epoch": "b" * 32,
        "capacity": 2, "candidate_sha256": "c" * 64, "runtime_sha256": "d" * 64, "source_manifest": [],
        "terminals": terminals, "load_receipt": None, "closure_receipt": None,
        "max_records": 20, "lock_wait_ms": 1000, "conflict_matrix": CONFLICT_MATRIX}
    coordinator = ScopedResourceCoordinator._for_fixture(node["root"], profile, initialize=True)
    gateway = GatewayJobJournal._for_fixture(tmp_path / "g.sqlite", initialize=True, **POLICY)
    journal = NodeJobJournal(tmp_path / "n.sqlite", initialize=True, **POLICY)
    for i, request in enumerate(requests): gateway.submit("op-" + str(i), request)
    with pytest.raises(JournalError, match="NATIVE_CAPACITY_UNQUALIFIED"):
        gateway.poll_for_node(node["registry"]["device_id"], route_generation=1, session_id="session-a", max_commands=2)
    gateway.install_capacity_roster(VerifiedCapacityRoster._for_fixture(profile, 1))
    commands = gateway.poll_for_node(node["registry"]["device_id"], route_generation=1, session_id="session-a", max_commands=2)
    assert len(commands) == 2 and gateway.capacity_for_node(node["registry"]["device_id"], 2) == 1
    barrier = threading.Barrier(2); effects = []
    class ScopedFixtureAdapter:
        def reserve(self, request, operation, exact_fence): return {"local_job_id": exact_fence["local_job_id"]}
        def start_reserved(self, job, request, exact_fence):
            frozen = request["placement"]["target"]
            with coordinator.execution(job, kind="tester", terminal_id=frozen["terminal_id"], terminal_generation=1, wait_ms=1000) as scope:
                armed = scope.arm(); barrier.wait(timeout=3); effects.append(job)
                scope.close_zero_attempt(armed)
            return {"schema": "fleet.native.effect/1", "phase": "start", "evidence": "SYNTHETIC_NATIVE_ONLY",
                "payload": {"process": current_identity()}}
    adapter = ScopedFixtureAdapter(); results = []
    def run(cmd):
        journal.receive(cmd, device_id=node["registry"]["device_id"], route_generation=1, session_id="session-a")
        results.append(journal.execute(cmd["global_job_id"], adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway)))
    # Configure synthetic signing trust before worker starts; no key bootstrap side effect.
    verifier(gateway)
    threads = [threading.Thread(target=run, args=(cmd,)) for cmd in commands]
    for thread in threads: thread.start()
    for thread in threads: thread.join(5); assert not thread.is_alive()
    assert len(effects) == 2 and all(result["state"] == "RUNNING" for result in results)
    for cmd in commands:
        gateway.commit_node_result(node["registry"]["device_id"], route_generation=1, session_id="session-a",
            payload=journal.result_payload(cmd["global_job_id"]))
    assert gateway.poll_for_node(node["registry"]["device_id"], route_generation=1, session_id="session-a", max_commands=2) == []
    assert not (node["root"] / "state" / "fleet" / "scoped-install.json").exists()
    gateway.close(); journal.close()
