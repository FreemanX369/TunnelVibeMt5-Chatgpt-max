"""Durable transport/native source fixtures; no physical MT5 qualification."""
import copy
import hashlib
import multiprocessing

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from test_tip061a_057n import node, freeze, logical_fixture
from test_tip055a_runtime_forensics_identity import ref
from vibemql5.core.native_ownership import current_identity
from vibemql5.fleet.native import native_request, RoutedNativeAdapter, SyntheticNativeAdapter
from vibemql5.fleet.job_journal import GatewayJobJournal, NodeJobJournal, JournalError, digest
from vibemql5.fleet.native_authorization import GatewayNativeSigner, NativeAuthorizationVerifier

POLICY = dict(max_records=30, max_payload_bytes=262144, wait_ms=100)


def req(node):
    placement = freeze(node, target={**ref(node["registry"]), "route_generation": 1})
    raw = node["source"].read_bytes()
    return native_request(placement, logical_fixture(), [{"path": "Experts/DemoEA.mq5", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}])


def command(gateway, request, op="op-a"):
    row = gateway.submit(op, request)
    commands = gateway.poll_for_node(request["placement"]["target"]["device_id"], route_generation=1, session_id="session-a")
    return row, commands[0]


def verifier(gateway, clock=None):
    if not hasattr(gateway, "_test_signer"):
        key = Ed25519PrivateKey.generate()
        gateway._test_signer = GatewayNativeSigner(key, "fixture-gateway", max_authorization_ms=1000)
        gateway._test_public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return NativeAuthorizationVerifier(gateway._test_public, "fixture-gateway", clock_ms=clock or (lambda: 1001))


def authorize(gateway):
    verifier(gateway)
    def call(row):
        return gateway.authorize_start(row["target"]["device_id"], route_generation=1,
            session_id="session-a", global_job_id=row["global_job_id"], node_operation_id=row["node_operation_id"],
            request_sha256=row["request_sha256"], frozen_target=row["target"], now_ms=1000, ttl_ms=1000, signer=gateway._test_signer,
            local_job_id=row["local_job_id"], phase=row["authorization_phase"], sequence=row["authorization_sequence"],
            challenge=row["authorization_challenge"], event=row.get("authorization_event", "phase_admission"),
            predecessor=row.get("authorization_predecessor"), process_sha256=row.get("authorization_process_sha256"))
    return call


def received(node, tmp_path):
    request = req(node)
    gateway = GatewayJobJournal(tmp_path / "gateway.sqlite", initialize=True, **POLICY)
    journal = NodeJobJournal(tmp_path / "node.sqlite", initialize=True, **POLICY)
    row, cmd = command(gateway, request)
    journal.receive(cmd, device_id=row["target"]["device_id"], route_generation=1, session_id="session-a")
    return gateway, journal, row, request


def fixture(node, events):
    return SyntheticNativeAdapter(node["root"], callbacks={
        "start": lambda *_: events.append("start") or {"process": current_identity()},
        "result": lambda *_: events.append("result") or {"state": "SUCCEEDED"},
        "cancel": lambda *_: events.append("cancel") or {"status": "SYNTHETIC_STOPPED"}})


def test_mapping_collision_restart_and_original_frozen_binding(node, tmp_path):
    request = req(node)
    with GatewayJobJournal(tmp_path / "g.sqlite", initialize=True, **POLICY) as gateway:
        original = gateway.submit("op", request)
        other = copy.deepcopy(request); other["logical_config"]["config"]["symbol"] = "OTHER"
        with pytest.raises(JournalError, match="IDEMPOTENCY_CONFLICT"):
            gateway.submit("op", other)
        assert gateway.submit("op", request) == original
    with GatewayJobJournal(tmp_path / "g.sqlite", **POLICY) as reopened:
        assert reopened.submit("op", request) == original
        assert reopened.get(original["global_job_id"])["target"] == request["placement"]["target"]


def test_signed_transport_to_synthetic_native_roundtrip_lost_ack_never_double_starts(node, tmp_path):
    gateway, journal, row, request = received(node, tmp_path)
    events = []; adapter = fixture(node, events)
    result = journal.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    assert result["state"] == "RUNNING"
    assert result["result"]["evidence"] == "SYNTHETIC_NATIVE_ONLY" and events == ["start"]
    # Lost ACK permits delivery repetition, not native repetition.
    repeated = gateway.poll_for_node(row["target"]["device_id"], route_generation=1, session_id="session-a")[0]
    assert journal.receive(repeated, device_id=row["target"]["device_id"], route_generation=1, session_id="session-a")["state"] == "RUNNING"
    journal.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=authorize(gateway))
    assert events == ["start"]
    payload = journal.result_payload(row["global_job_id"])
    committed = gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=payload)
    assert committed["state"] == "RUNNING"
    journal.observe_result(row["global_job_id"], adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway))
    assert events == ["start", "result"]
    terminal = journal.result_payload(row["global_job_id"])
    final = gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=terminal)
    assert final["state"] == "SUCCEEDED"
    assert gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=terminal) == final
    journal.close(); gateway.close()
    with NodeJobJournal(tmp_path / "node.sqlite", **POLICY) as reopened:
        assert reopened.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=lambda _: pytest.fail("no auth replay"))["state"] == "SUCCEEDED"
    assert events == ["start", "result"]


@pytest.mark.parametrize("phase", ["before_reserve", "after_reserve", "before_start", "after_start"])
def test_process_interruption_every_callback_boundary_remains_unknown(node, tmp_path, phase):
    gateway, journal, row, _ = received(node, tmp_path)
    events = []; adapter = fixture(node, events)
    def interrupted(point):
        if point == phase: raise SystemExit("synthetic process interruption")
    journal.fault = interrupted
    with pytest.raises(SystemExit):
        journal.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    journal.close(); gateway.close()
    with NodeJobJournal(tmp_path / "node.sqlite", **POLICY) as restarted:
        assert restarted.get(row["global_job_id"])["state"] == "UNKNOWN"
        restarted.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=lambda _: pytest.fail("no restart authorization"))
    assert events == (["start"] if phase == "after_start" else [])


def test_default_production_native_boundary_has_zero_effect(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    result = journal.execute(row["global_job_id"], RoutedNativeAdapter(node["root"]),
        authorization_verifier=verifier(gateway), start_authorize=authorize(gateway))
    assert result["state"] == "FAILED" and result["result"]["reason_code"] == "NATIVE_QUALIFICATION_UNAVAILABLE"
    assert not list((node["root"] / "runs").glob("*/job.json"))
    gateway.close(); journal.close()


def test_bounded_expiring_exact_start_authorization_never_reissues_after_timeout(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    verifier(gateway)
    args = dict(route_generation=1, session_id="session-a", global_job_id=row["global_job_id"],
        node_operation_id=row["node_operation_id"], request_sha256=row["request_sha256"],
        frozen_target=row["target"], ttl_ms=1000, signer=gateway._test_signer,
        local_job_id="BT-20261003-010000-ABC123", phase="reserve", sequence=2, challenge="a" * 32)
    first = gateway.authorize_start(row["target"]["device_id"], now_ms=1000, **args)
    assert gateway.authorize_start(row["target"]["device_id"], now_ms=1001, **args) == first
    with pytest.raises(JournalError, match="START_AUTHORIZATION_UNRESOLVED"):
        gateway.authorize_start(row["target"]["device_id"], now_ms=2000, **args)
    with pytest.raises(JournalError, match="JOB_BINDING_MISMATCH"):
        gateway.authorize_start(row["target"]["device_id"], now_ms=1001, **{**args, "route_generation": 2})
    gateway.close(); journal.close()


def test_one_active_job_per_device_blocks_second_dispatch_even_across_route_change(node, tmp_path):
    gateway, journal, row, request = received(node, tmp_path)
    journal.execute(row["global_job_id"], fixture(node, []), authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=journal.result_payload(row["global_job_id"]))
    gateway.submit("op-b", request)
    assert gateway.poll_for_node(row["target"]["device_id"], route_generation=1, session_id="session-a") == []
    assert gateway.poll_for_node(row["target"]["device_id"], route_generation=2, session_id="session-b") == []
    gateway.close(); journal.close()


def test_late_revoked_evidence_is_quarantined_not_promoted(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    journal.execute(row["global_job_id"], fixture(node, []), authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    payload = journal.result_payload(row["global_job_id"])
    result = gateway.commit_node_result(row["target"]["device_id"], route_generation=2, session_id="session-a", payload=payload)
    assert result["status"] == "QUARANTINED"
    assert gateway.get(row["global_job_id"])["state"] == "DELIVERED"
    assert len(gateway.get(row["global_job_id"])["quarantined_evidence"]) == 1
    gateway.close(); journal.close()


def test_bound_cancel_once_and_process_identity_mismatch(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path); events = []; adapter = fixture(node, events)
    result = journal.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    process = result["result"]["process_identity"]
    gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=journal.result_payload(row["global_job_id"]))
    with pytest.raises(JournalError, match="PROCESS_IDENTITY_UNPROVEN"):
        journal.cancel("cancel-a", row["global_job_id"], process_identity={**process, "creation": "999999"}, adapter=adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway))
    one = journal.cancel("cancel-a", row["global_job_id"], process_identity=process, adapter=adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway))
    assert journal.cancel("cancel-a", row["global_job_id"], process_identity=process, adapter=adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway)) == one
    assert events == ["start", "cancel"] and one["evidence"] == "SYNTHETIC_NATIVE_ONLY"
    gateway.close(); journal.close()


def test_cancel_authority_requires_committed_exact_process_and_rejects_reused_pid(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    result = journal.execute(row["global_job_id"], fixture(node, []), authorization_verifier=verifier(gateway), start_authorize=authorize(gateway))
    process = result["result"]["process_identity"]
    args = dict(route_generation=1, session_id="session-a", global_job_id=row["global_job_id"],
        node_operation_id=row["node_operation_id"], request_sha256=row["request_sha256"], frozen_target=row["target"],
        now_ms=1000, ttl_ms=1000, signer=gateway._test_signer, local_job_id=result["local_job_id"], phase="cancel",
        sequence=20, challenge="a" * 32, event="owned_terminate:0001", process_sha256=digest(process))
    with pytest.raises(JournalError, match="PROCESS_IDENTITY_UNPROVEN"):
        gateway.authorize_start(row["target"]["device_id"], **args)
    payload = journal.result_payload(row["global_job_id"])
    gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=payload)
    first = gateway.authorize_start(row["target"]["device_id"], **args)
    assert first["body"]["process_sha256"] == digest(process)
    reused = {**process, "creation": process["creation"] + "-reused"}
    changed = copy.deepcopy(payload); changed["sequence"] += 1; changed["result"]["process_identity"] = reused
    gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=changed)
    with pytest.raises(JournalError, match="PROCESS_IDENTITY_UNPROVEN"):
        gateway.authorize_start(row["target"]["device_id"], **args)
    gateway.close(); journal.close()


def test_supported_old_backup_restore_requires_signed_challenge_and_reconciles_old_outcome(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    gateway.backup(tmp_path / "backup.sqlite")
    adapter = fixture(node, []); journal.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    journal.observe_result(row["global_job_id"], adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway))
    gateway.close()
    restored = GatewayJobJournal.restore_backup(tmp_path / "backup.sqlite", tmp_path / "restored.sqlite",
        devices=[row["target"]["device_id"]], export_generation=1, **POLICY)
    with pytest.raises(JournalError, match="RECONCILIATION_REQUIRED"):
        restored.poll_for_node(row["target"]["device_id"], route_generation=1, session_id="session-a")
    scope = restored._meta("restore")
    key = Ed25519PrivateKey.generate(); public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    proof = journal.witness(scope, device_id=row["target"]["device_id"], route_generation=1, session_id="session-a", private_key=key)
    tampered = copy.deepcopy(proof); tampered["body"]["challenge"] = "0" * 32
    with pytest.raises(JournalError, match="WITNESS_INVALID"):
        restored.reconcile_node(tampered, registered_public_key=public, current_route_generation=1, current_session_id="session-a")
    assert restored.reconcile_node(proof, registered_public_key=public, current_route_generation=1, current_session_id="session-a")["status"] == "RECONCILED"
    assert restored.get(row["global_job_id"])["state"] == "SUCCEEDED"
    assert restored.poll_for_node(row["target"]["device_id"], route_generation=1, session_id="session-a") == []
    restored.close(); journal.close()


def _owner_probe(path, output):
    try:
        with GatewayJobJournal(path, **POLICY): pass
        output.put("OPENED")
    except Exception as error:
        output.put(type(error).__name__)


def test_real_concurrent_os_writer_is_denied_and_reopen_after_close_works(tmp_path):
    with GatewayJobJournal(tmp_path / "g.sqlite", initialize=True, **POLICY):
        ctx = multiprocessing.get_context("spawn"); output = ctx.Queue()
        process = ctx.Process(target=_owner_probe, args=(tmp_path / "g.sqlite", output))
        process.start(); process.join(10)
        assert process.exitcode == 0 and output.get(timeout=2) == "TimeoutError"
    with GatewayJobJournal(tmp_path / "g.sqlite", **POLICY): pass


def test_initialize_fault_never_publishes_partial_canonical_store(tmp_path):
    def fail(phase):
        if phase == "before_commit": raise RuntimeError("fixture fault")
    with pytest.raises(RuntimeError):
        GatewayJobJournal(tmp_path / "g.sqlite", initialize=True, fault=fail, **POLICY)
    assert not (tmp_path / "g.sqlite").exists()
    with pytest.raises(JournalError, match="JOURNAL_MISSING"):
        GatewayJobJournal(tmp_path / "g.sqlite", **POLICY)


class _StepFixture:
    """Harmless source protocol producer; no compiler, SDK or process creation."""
    def __init__(self, callback): self.callback = callback
    def reserve(self, request, operation, *, exact_fence):
        return {"local_job_id": exact_fence["local_job_id"]}
    def start_reserved(self, local_job_id, request, fence):
        self.callback(fence)
        return {"state": "SUCCEEDED", "evidence": "SYNTHETIC_NATIVE_STEP_PROTOCOL_ONLY"}


def _clock_authorize(gateway, clock):
    verifier(gateway)
    def call(row):
        return gateway.authorize_start(row["target"]["device_id"], route_generation=1,
            session_id="session-a", global_job_id=row["global_job_id"], node_operation_id=row["node_operation_id"],
            request_sha256=row["request_sha256"], frozen_target=row["target"], now_ms=clock[0], ttl_ms=1000,
            signer=gateway._test_signer, local_job_id=row["local_job_id"], phase=row["authorization_phase"],
            sequence=row["authorization_sequence"], challenge=row["authorization_challenge"],
            event=row["authorization_event"], predecessor=row["authorization_predecessor"],
            process_sha256=row["authorization_process_sha256"])
    return call


def test_consumed_long_step_completes_after_expiry_then_distinct_capture_has_fresh_proof(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path); clock = [1000]; effects = []; proofs = []
    def harmless(fence):
        for phase, event in [("deploy", "snapshot_prepare:0001"), ("deploy", "process_create:0001"),
                             ("deploy", "process_resume:0001"), ("capture", "compile_log_capture:0001"),
                             ("result", "result_promote:0001")]:
            proof = fence["begin_effect"](phase, event); proof.require(**proof.binding)
            effects.append(event); proofs.append(proof)
            if event == "process_resume:0001": clock[0] += 5000
            # Completion records a returned actual call, without admitting a new call.
            fence["complete_effect"](phase, event, proof)
    final = journal.execute(row["global_job_id"], _StepFixture(harmless), start_authorize=_clock_authorize(gateway, clock),
                            authorization_verifier=verifier(gateway, clock=lambda: clock[0]))
    assert final["state"] == "SUCCEEDED" and len(effects) == 5
    assert proofs[3].require(**proofs[3].binding)["issued_ms"] == 6000
    with pytest.raises(JournalError, match="NATIVE_AUTHORIZATION_EXPIRED"):
        proofs[2].require(**proofs[2].binding)
    payload = journal.result_payload(row["global_job_id"])
    committed = gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=payload)
    assert committed["state"] == "SUCCEEDED"
    assert gateway._effect_history(row["global_job_id"])[-1]["state"] == "COMPLETED"
    assert gateway.commit_node_result(row["target"]["device_id"], route_generation=1, session_id="session-a", payload=payload) == committed
    journal.close(); gateway.close()


@pytest.mark.parametrize("fault", ["before_effect_authorization", "after_effect_consumption", "after_effect_completion"])
def test_step_process_loss_never_repeats_effect_or_advances_unknown(node, tmp_path, fault):
    gateway, journal, row, _ = received(node, tmp_path); clock = [1000]; effects = []
    def interrupt(point):
        if point == fault: raise SystemExit("harmless step interruption")
    journal.fault = interrupt
    def harmless(fence):
        proof = fence["begin_effect"]("deploy", "snapshot_prepare:0001")
        effects.append("snapshot")
        fence["complete_effect"]("deploy", "snapshot_prepare:0001", proof)
    with pytest.raises(SystemExit):
        journal.execute(row["global_job_id"], _StepFixture(harmless), start_authorize=_clock_authorize(gateway, clock),
                        authorization_verifier=verifier(gateway, clock=lambda: clock[0]))
    journal.close(); gateway.close()
    with NodeJobJournal(tmp_path / "node.sqlite", **POLICY) as reopened:
        assert reopened.get(row["global_job_id"])["state"] == "UNKNOWN"
        reopened.execute(row["global_job_id"], _StepFixture(harmless), start_authorize=lambda _: pytest.fail("no repeat"),
                         authorization_verifier=verifier(gateway))
        with pytest.raises(JournalError):
            reopened.begin_effect(row["global_job_id"], "deploy", "compile_run_prepare:0001",
                start_authorize=lambda _: pytest.fail("no successor"), authorization_verifier=verifier(gateway))
    assert effects == (["snapshot"] if fault == "after_effect_completion" else [])


def test_step_predecessor_tamper_and_duplicate_effect_are_denied(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path); clock = [1000]
    normal = _clock_authorize(gateway, clock)
    def changed(row):
        if row["authorization_predecessor"] is not None:
            row = copy.deepcopy(row); row["authorization_predecessor"]["challenge"] = "0" * 32
        return normal(row)
    def harmless(fence):
        proof = fence["begin_effect"]("deploy", "snapshot_prepare:0001")
        fence["complete_effect"]("deploy", "snapshot_prepare:0001", proof)
        with pytest.raises(JournalError, match="NATIVE_EFFECT_GRAPH_INVALID"):
            fence["begin_effect"]("deploy", "snapshot_prepare:0001")
        fence["begin_effect"]("deploy", "compile_run_prepare:0001")
    final = journal.execute(row["global_job_id"], _StepFixture(harmless), start_authorize=changed,
                            authorization_verifier=verifier(gateway, clock=lambda: clock[0]))
    assert final["state"] == "UNKNOWN"
    assert len(gateway._effect_history(row["global_job_id"])) == 1
    journal.close(); gateway.close()


@pytest.mark.parametrize("phase,expected_count", [("before_commit", 0), ("after_commit", 1)])
def test_gateway_commit_fault_retains_none_or_whole_immutable_mapping(node, tmp_path, phase, expected_count):
    request = req(node)
    with GatewayJobJournal(tmp_path / "g.sqlite", initialize=True, **POLICY) as gateway:
        def fail(point):
            if point == phase: raise RuntimeError("fixture fault")
        gateway.fault = fail
        with pytest.raises(RuntimeError): gateway.submit("op", request)
        gateway.fault = None
        assert gateway._db.execute("SELECT count(*) FROM jobs").fetchone()[0] == expected_count
        receipt = gateway.submit("op", request)
        assert gateway.submit("op", request) == receipt


def test_corrupt_unknown_schema_policy_mismatch_and_capacity_do_not_bootstrap_or_evict(node, tmp_path):
    import sqlite3
    request = req(node)
    policy = {**POLICY, "max_records": 1}
    with GatewayJobJournal(tmp_path / "g.sqlite", initialize=True, **policy) as gateway:
        original = gateway.submit("op-a", request)
        with pytest.raises(JournalError, match="JOURNAL_CAPACITY"): gateway.submit("op-b", request)
        assert gateway.submit("op-a", request) == original
    with pytest.raises(JournalError, match="JOURNAL_INVALID"): GatewayJobJournal(tmp_path / "g.sqlite", **POLICY)
    connection = sqlite3.connect(tmp_path / "g.sqlite")
    connection.execute("UPDATE meta SET value='\"future/99\"' WHERE name='schema'"); connection.commit(); connection.close()
    with pytest.raises(JournalError, match="JOURNAL_INVALID"): GatewayJobJournal(tmp_path / "g.sqlite", **policy)
    (tmp_path / "corrupt.sqlite").write_bytes(b"corrupt")
    with pytest.raises(JournalError, match="JOURNAL_INVALID"): GatewayJobJournal(tmp_path / "corrupt.sqlite", **POLICY)


@pytest.mark.parametrize("change", ["empty", "unknown", "unmapped", "wrong_route", "wrong_highwater"])
def test_signed_but_incomplete_restore_witness_never_unlocks(node, tmp_path, change):
    from vibemql5.fleet.job_journal import canonical
    gateway, journal, row, _ = received(node, tmp_path)
    adapter = fixture(node, [])
    journal.execute(row["global_job_id"], adapter, authorization_verifier=verifier(gateway), start_authorize=authorize(gateway), now_ms=lambda: 1001)
    journal.observe_result(row["global_job_id"], adapter, start_authorize=authorize(gateway), authorization_verifier=verifier(gateway))
    scope = gateway.begin_restore(devices=[row["target"]["device_id"]], export_generation=1)
    key = Ed25519PrivateKey.generate(); public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    proof = journal.witness(scope, device_id=row["target"]["device_id"], route_generation=1, session_id="session-a", private_key=key)
    body = proof["body"]
    if change == "empty": body["records"] = []
    if change == "unknown": body["records"][0]["state"] = "UNKNOWN"
    if change == "unmapped": body["records"][0]["global_job_id"] = "fjob_" + "f" * 32
    if change == "wrong_route": body["route_generation"] = 2
    if change == "wrong_highwater": body["high_water"] = 1
    proof["signature"] = key.sign(b"fleet.node-journal-witness/1\n" + canonical(body)).hex()
    with pytest.raises(JournalError): gateway.reconcile_node(proof, registered_public_key=public, current_route_generation=1, current_session_id="session-a")
    with pytest.raises(JournalError, match="RECONCILIATION_REQUIRED"):
        gateway.poll_for_node(row["target"]["device_id"], route_generation=1, session_id="session-a")
    gateway.close(); journal.close()
