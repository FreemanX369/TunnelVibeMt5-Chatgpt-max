"""Placement/baseline/routed boundary source tests; native success is harmless synthetic."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from ownership_fixture import install_closed
from test_tip055a_runtime_forensics_identity import make_terminal, ref, write_config
from vibemql5.core.jobs import _sha256_json
from vibemql5.core.native_ownership import current_identity
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.revisions import RevisionManager
from vibemql5.fleet.identity import IdentityRegistry, normalize_path
from vibemql5.fleet.project_targets import FleetProjectError, FleetProjectStore
from vibemql5.fleet.strict_baseline import FIELDS, strict_compare
from vibemql5.fleet.native import NativeRouteError, RoutedNativeAdapter, SyntheticNativeAdapter, native_request, native_request_hash
from fleet_gateway_fixture import preserve_fixture_failure


SCOPED_FIXTURE_STAGES = frozenset({"NOT_ENTERED", "START_RESERVED_ENTERED", "COMPILER_DRIVER_ENTERED",
    "COMPILER_LAUNCHED", "TESTER_DRIVER_ENTERED", "TESTER_LAUNCHED", "BARRIER_ENTERED",
    "BARRIER_PASSED", "RELEASE_OBSERVED", "DRIVER_RETURNED"})


def scoped_fixture_stages(stages):
    return [stage if type(stage) is str and stage in SCOPED_FIXTURE_STAGES else "UNOBSERVED"
            for stage in stages[:2]]


def collect_scoped_fixture_futures(futures, stages, *, timeout=10):
    """Observe both original outcomes, even when the parent barrier failed."""
    results, errors = [], []
    for index, future in enumerate(futures):
        try:
            result = future.result(timeout=timeout)
            results.append(result)
            try:
                status = result["payload"]["execution"]["status"]
            except (KeyError, TypeError):
                status = None
            if status != "COMPLETED":
                error = AssertionError("SCOPED_FIXTURE_WORKER_NOT_COMPLETED")
                safe_status = status if type(status) is str and status in {"FAILED", "CANCELLED", "PASSED", "NOT_RUN"} else "OTHER"
                error.add_note(str({"worker_index": index, "returned_status": safe_status,
                                    "stages": scoped_fixture_stages(stages)}))
                errors.append(error)
        except BaseException as error:
            error.add_note(str({"worker_index": index, "outcome": "RAISED",
                                "stages": scoped_fixture_stages(stages)}))
            errors.append(error)
    if len(errors) == 1: raise errors[0]
    if errors: raise BaseExceptionGroup("scoped fixture workers failed", errors)
    return results


def test_scoped_future_collection_retains_parent_barrier_and_original_worker_failure():
    import concurrent.futures
    import threading
    reached, released, worker_completed = threading.Barrier(2), threading.Event(), threading.Event()
    worker_error = RuntimeError("controlled worker fault")
    worker_error.add_note("retained original note")
    def failed_worker():
        raise worker_error
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(failed_worker)
        future.add_done_callback(lambda completed: worker_completed.set())
        with pytest.raises(BaseExceptionGroup) as caught:
            try:
                assert worker_completed.wait(10) and future.done()
                reached.wait(timeout=.02)
            finally:
                parent_error = sys.exception()
                released.set()
                with preserve_fixture_failure():
                    collect_scoped_fixture_futures([future], ["START_RESERVED_ENTERED"], timeout=.1)
    parent, worker = caught.value.exceptions
    assert parent is parent_error and isinstance(parent, threading.BrokenBarrierError)
    assert worker is worker_error and worker.__notes__[0] == "retained original note"
    assert released.is_set() and future.done()


@pytest.mark.parametrize("returned_status", ["FAILED", "NOT_RUN", "CANCELLED"])
def test_scoped_future_collection_observes_both_errors_and_returned_failed_receipt(returned_status):
    from concurrent.futures import Future
    parent, first, second = (RuntimeError(name) for name in ("parent", "first", "second"))
    futures = [Future(), Future()]
    futures[0].set_exception(first); futures[1].set_exception(second)
    with pytest.raises(BaseExceptionGroup) as caught:
        try: raise parent
        finally:
            with preserve_fixture_failure():
                collect_scoped_fixture_futures(futures, ["NOT_ENTERED", "NOT_ENTERED"])
    assert caught.value.exceptions[0] is parent
    assert caught.value.exceptions[1].exceptions == (first, second)
    marker = "sensitive-path-token-worker-value"
    failed, completed = Future(), Future()
    failed.set_result({"payload": {"execution": {"status": returned_status, "detail": marker}}})
    receipt = {"payload": {"execution": {"status": "COMPLETED"}}}
    completed.set_result(receipt)
    with pytest.raises(AssertionError, match="SCOPED_FIXTURE_WORKER_NOT_COMPLETED") as failed_outcome:
        collect_scoped_fixture_futures([failed, completed], [marker, {"unhashable": marker}])
    assert "'returned_status': '" + returned_status + "'" in str(failed_outcome.value.__notes__)
    assert marker not in str(failed_outcome.value.__notes__)
    assert collect_scoped_fixture_futures([completed, completed], ["DRIVER_RETURNED"] * 2) == [receipt, receipt]
    assert collect_scoped_fixture_futures([completed], ["DRIVER_RETURNED"])[0] is receipt


@pytest.fixture
def node(tmp_path):
    terminals = [make_terminal(tmp_path), make_terminal(tmp_path, "MT5-3", "b")]
    write_config(tmp_path, terminals)
    registry = IdentityRegistry(tmp_path).bootstrap(terminals)
    install_closed(tmp_path)
    source = tmp_path / "workspaces" / "demo" / "Experts" / "DemoEA.mq5"
    source.parent.mkdir(parents=True); source.write_bytes(b"void OnTick(){}\r\n")
    checkpoint = RevisionManager(tmp_path).create_checkpoint("demo", "Experts/DemoEA.mq5")
    session = ProjectSessionManager(tmp_path).create("P", "demo", "Experts/DemoEA.mq5", checkpoint_id=checkpoint["checkpoint_id"])
    projects = FleetProjectStore(tmp_path)
    project = projects.enroll("P", registry["device_id"], expected_session_revision=session["revision_id"],
        expected_session_sha256=session["revision_sha256"], operation_id="enroll", default_target=ref(registry))
    return {"root": tmp_path, "terminals": terminals, "registry": registry, "source": source,
            "session": session, "projects": projects, "project": project}


def freeze(node, frozen_id="iteration-a", *, target=None, revision=1, operation="freeze-a"):
    session = node["session"]
    return node["projects"].freeze("P", frozen_id, writer_id="writer-local", target=target,
        expected_placement_revision=revision, expected_session_revision=session["revision_id"],
        expected_session_sha256=session["revision_sha256"], operation_id=operation)


def logical_fixture():
    config = {"model": 4, "symbol": "EURUSD", "period": "M5", "from_date": "2026.09.01", "to_date": "2026.09.30",
              "deposit": 10000, "currency": "USD", "leverage": 100, "visual": False}
    period = {"from_date": config["from_date"], "to_date": config["to_date"]}
    logical = {"config": config, "normalization": {"requested_period": period, "effective_period": period,
        "current_date": "2026.10.03", "future_to_date_clamped": False,
        "execution_delay": {"specified": False, "execution_mode": None, "mode": "TERMINAL_DEFAULT"}}}
    return logical


def request(node, **kwargs):
    raw = node["source"].read_bytes()
    return native_request(freeze(node), logical_fixture(), [{"path": "Experts/DemoEA.mq5", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}], **kwargs)


def fence(req, process=None):
    value = {"target": req["placement"]["target"], "session_sha256": req["placement"]["session"]["revision_sha256"]}
    if process is not None: value["process"] = process
    return value


def denied(code, fn):
    with pytest.raises((FleetProjectError, NativeRouteError)) as caught:
        fn()
    assert caught.value.code == code
    assert str(caught.value) == code


def test_default_change_affects_only_new_freezes_and_replay_uses_frozen_binding(node):
    original = freeze(node)
    other = ref(node["registry"], 1)
    receipt = node["projects"].set_default("P", other, expected_placement_revision=1, operation_id="new-default")
    assert receipt["placement_revision"] == 2
    reopened = FleetProjectStore(node["root"])
    replay = freeze(node)
    assert replay["idempotent_recovered"]
    assert replay["target"] == original["target"]
    assert reopened.load_frozen("iteration-a")["target"] == original["target"]
    new = freeze(node, "iteration-b", revision=2, operation="freeze-b")
    assert new["target"] == other
    denied("FLEET_FROZEN_CONFLICT", lambda: freeze(node, target=other))
    assert reopened.set_default("P", other, expected_placement_revision=1, operation_id="new-default")["idempotent_recovered"]
    denied("FLEET_OPERATION_CONFLICT", lambda: reopened.set_default("P", None,
        expected_placement_revision=1, operation_id="new-default"))


def test_same_node_source_executor_and_frozen_session_checkpoint_integrity(node):
    remote = {**ref(node["registry"]), "device_id": "dev_" + "f" * 32}
    denied("FLEET_SAME_NODE_REQUIRED", lambda: freeze(node, target=remote))
    frozen = freeze(node)
    assert frozen["session"]["source_sha256"] == hashlib.sha256(node["source"].read_bytes()).hexdigest()
    assert frozen["writer"]["authentication"] == "UNVERIFIED_REFERENCE"
    node["source"].write_bytes(b"changed")
    denied("FLEET_SOURCE_CHANGED", lambda: node["projects"].validate_frozen(frozen))
    assert node["projects"].resume("iteration-a")["status"] == "FLEET_SOURCE_CHANGED"
    assert FleetProjectStore.legacy_binding({"terminal": "MT5-2"})["target"] is None


def fingerprint():
    value = {"target": {"schema": "fleet.target/1", "device_id": "dev_" + "1" * 32,
                        "terminal_id": "term_" + "2" * 32, "terminal_generation": 1},
        "binding": {"executable": normalize_path(str(Path.cwd() / "fixture/terminal64.exe")), "data_root": normalize_path(str(Path.cwd() / "fixture/data"))},
        "logical_config": logical_fixture(), "effective_period": {"from_date": "2026.09.01", "to_date": "2026.09.30"},
        "history_evidence": {"status": "AVAILABLE", "sha256": "f" * 64}}
    value.update(source_sha256="a" * 64, terminal_build=6230, compiler_build=6230, tester_model=4,
        set_sha256="b" * 64, include_sha256="c" * 64, input_manifest_sha256="d" * 64,
        broker_server="Fixture-Server")
    return value


def test_strict_candidate_source_difference_is_evidence_not_equivalence_failure():
    base, candidate = fingerprint(), fingerprint()
    candidate["source_sha256"] = "e" * 64
    comparison = strict_compare(candidate, base)
    assert comparison["status"] == "COMPATIBLE"
    assert comparison["candidate_source_sha256"] != comparison["baseline_source_sha256"]
    assert comparison["auto_promote"] is False


@pytest.mark.parametrize("field", FIELDS)
def test_strict_matrix_reports_each_missing_and_mismatched_field(field):
    baseline, candidate = fingerprint(), fingerprint()
    candidate.pop(field)
    result = strict_compare(candidate, baseline)
    assert result["status"] == "UNVERIFIED" and field in result["missing_fields"]
    candidate = fingerprint()
    if field == "target": candidate[field]["terminal_generation"] = 2
    elif field == "binding": candidate[field]["data_root"] = normalize_path(str(Path.cwd() / "fixture/other"))
    elif field == "logical_config": candidate[field]["config"]["symbol"] = "XAUUSD"
    elif field == "effective_period": candidate[field]["from_date"] = "2026.08.01"
    elif field == "history_evidence": candidate[field]["sha256"] = "0" * 64
    elif type(candidate[field]) is int: candidate[field] = 3 if field == "tester_model" else candidate[field] + 1
    elif field.endswith("sha256"): candidate[field] = "0" * 64
    else: candidate[field] += "-other"
    result = strict_compare(candidate, baseline, explicit_cross_target=True)
    assert result["status"] == "INCOMPATIBLE" and field in result["mismatched_fields"]
    assert result["auto_promote"] is False


@pytest.mark.parametrize("field,value", [("target", {}), ("binding", {}), ("terminal_build", True),
    ("compiler_build", 0), ("tester_model", "4"), ("logical_config", {}), ("set_sha256", "bad"),
    ("history_evidence", {"status": "UNVERIFIED"}), ("broker_server", "")])
def test_invalid_environment_evidence_never_counts_as_compatible(field, value):
    candidate, baseline = fingerprint(), fingerprint()
    candidate[field] = baseline[field] = value
    result = strict_compare(candidate, baseline)
    assert result["status"] == "UNVERIFIED" and field in result["missing_fields"]


def test_new_native_hash_namespace_preserves_legacy_request_bytes(node):
    legacy = {"workspace": "demo", "ea": "Experts/DemoEA.mq5", "terminal": "MT5-2", "model": 4}
    before = _sha256_json(legacy)
    req = request(node)
    assert req["schema"] == "fleet.native/1"
    assert native_request_hash(req) != before
    assert _sha256_json(legacy) == before
    assert not list((node["root"] / "state" / "job-operations").glob("*.json"))


@pytest.mark.parametrize("phase", ["reserve", "deploy", "start", "test", "capture", "cancel", "result"])
def test_production_factory_denies_every_native_effect_before_job_or_callback(node, phase):
    req = request(node)
    adapter = RoutedNativeAdapter(node["root"])
    if phase == "reserve":
        denied("NATIVE_QUALIFICATION_UNAVAILABLE", lambda: adapter.reserve(req, "op-a"))
    else:
        denied("NATIVE_QUALIFICATION_UNAVAILABLE", lambda: adapter.effect("missing-job", phase, req, fence(req)))
    assert not list((node["root"] / "runs").glob("*/job.json"))
    assert not list((node["root"] / "state" / "fleet" / "native-operations").glob("*.json"))
    with pytest.raises(TypeError): RoutedNativeAdapter(node["root"], qualified=True)


def test_synthetic_reservation_reopen_replay_and_exact_process_cancellation(node):
    req = request(node)
    events = []
    process = current_identity()  # Harmless current Python process identity; no MT5.
    callbacks = {"start": lambda *_: events.append("start") or {"process": process},
                 "cancel": lambda *_: events.append("cancel") or {"status": "SYNTHETIC_STOPPED"}}
    adapter = SyntheticNativeAdapter(node["root"], callbacks=callbacks)
    reservation = adapter.reserve(req, "node-op-a")
    assert reservation["evidence"] == "SYNTHETIC_NATIVE_ONLY"
    replay = SyntheticNativeAdapter(node["root"], callbacks=callbacks).reserve(req, "node-op-a")
    assert replay["local_job_id"] == reservation["local_job_id"] and replay["idempotent_recovered"]
    job = reservation["local_job_id"]
    started = adapter.start_reserved(job, req, fence(req))
    assert started["evidence"] == "SYNTHETIC_NATIVE_ONLY" and events == ["start"]
    adapter.start_reserved(job, req, fence(req))
    assert events == ["start"]
    wrong = {**process, "creation": "99999999999"}
    denied("NATIVE_PROCESS_MISMATCH", lambda: adapter.effect(job, "cancel", req, fence(req, wrong)))
    assert events == ["start"]
    adapter.effect(job, "cancel", req, fence(req, process))
    assert events == ["start", "cancel"]
    assert not list((node["root"] / "state" / "job-operations").glob("*.json"))


def test_synthetic_callback_uncertainty_keeps_common_ownership_and_never_repeats(node):
    req = request(node)
    events = []
    def interrupted(*_):
        events.append("start")
        raise OSError("do not echo raw SDK credentials")
    adapter = SyntheticNativeAdapter(node["root"], callbacks={"start": interrupted})
    job = adapter.reserve(req, "node-op-a")["local_job_id"]
    denied("NATIVE_RECOVERY_REQUIRED", lambda: adapter.start_reserved(job, req, fence(req)))
    assert events == ["start"]
    from vibemql5.core.native_ownership import OwnershipAuthority, OwnershipBlocked
    assert OwnershipAuthority(node["root"]).status()["admission"] == "BLOCKED"
    denied("NATIVE_RECOVERY_REQUIRED", lambda: adapter.start_reserved(job, req, fence(req)))
    assert events == ["start"]


@pytest.mark.parametrize("phase", ["deploy", "start", "test", "capture", "cancel", "result"])
def test_source_drift_denies_all_synthetic_effect_boundaries_with_zero_callbacks(node, phase):
    req = request(node)
    calls = []
    adapter = SyntheticNativeAdapter(node["root"], callbacks={phase: lambda *_: calls.append(phase)})
    job = adapter.reserve(req, "op-a")["local_job_id"]
    node["source"].write_bytes(b"external edit")
    denied("FLEET_SOURCE_CHANGED", lambda: adapter.effect(job, phase, req, fence(req)))
    assert calls == []


@pytest.mark.parametrize("period", [{"from_date": "2026.02.30", "to_date": "2026.03.01"},
    {"from_date": "2026.10.02", "to_date": "2026.10.01"}])
def test_strict_impossible_or_reversed_period_is_unverified(period):
    candidate = fingerprint(); candidate["effective_period"] = period
    assert strict_compare(candidate, candidate)["status"] == "UNVERIFIED"


@pytest.mark.parametrize("mutation", [lambda record: record.update(project_id="../outside"),
    lambda record: record["session"].update(ea="../secret"),
    lambda record: record["session"].update(source_bytes=True),
    lambda record: record["writer"].update(authentication="AUTHENTICATED"),
    lambda record: record.update(unexpected="secret")])
def test_frozen_corruption_is_denied_even_with_recomputed_integrity(node, mutation):
    from vibemql5.fleet.project_targets import digest
    original = freeze(node)
    path = node["projects"]._frozen_path(original["frozen_id"])
    record = json.loads(path.read_bytes()); mutation(record)
    record["record_sha256"] = digest({key: value for key, value in record.items() if key != "record_sha256"})
    path.write_text(json.dumps(record))
    denied("FLEET_STATE_INVALID", lambda: node["projects"].load_frozen(original["frozen_id"]))


@pytest.mark.parametrize("body", [b'{"schema":"fleet.project/1","schema":"fleet.project/1"}', b" " * 262145],
    ids=["duplicate-schema", "oversize"])
def test_project_read_rejects_duplicates_and_bounds_before_decode(node, body):
    node["projects"]._path("P").write_bytes(body)
    denied("FLEET_STATE_INVALID", lambda: node["projects"].get("P"))


@pytest.mark.parametrize("mutation", [lambda op: op.update(local_job_id="../../secret"),
    lambda op: op.update(request_sha256="wrong"), lambda op: op.update(node_operation_id="other-op"),
    lambda op: op.update(target={}), lambda op: op.update(extra="secret")])
def test_native_operation_corruption_never_restores_arbitrary_job_or_repeats_callback(node, mutation):
    req = request(node); calls = []
    adapter = SyntheticNativeAdapter(node["root"], callbacks={"start": lambda *_: calls.append(1)})
    adapter.reserve(req, "original-op")
    path = adapter._operation_path("original-op")
    operation = json.loads(path.read_bytes()); mutation(operation); path.write_text(json.dumps(operation))
    denied("NATIVE_JOURNAL_INVALID", lambda: adapter.reserve(req, "original-op"))
    assert calls == []


def test_native_reservation_publication_gap_repairs_exact_original_job_only(node, monkeypatch):
    req = request(node); adapter = SyntheticNativeAdapter(node["root"], callbacks={})
    original = adapter.jobs.update_fields
    monkeypatch.setattr(adapter.jobs, "update_fields", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("SYNTHETIC_STORAGE_INTERRUPTION")))
    denied("NATIVE_RESERVATION_UNCERTAIN", lambda: adapter.reserve(req, "original-op"))
    operation = json.loads(adapter._operation_path("original-op").read_bytes())
    monkeypatch.setattr(adapter.jobs, "update_fields", original)
    replay = adapter.reserve(req, "original-op")
    assert replay["local_job_id"] == operation["local_job_id"] and replay["idempotent_recovered"]
    assert adapter._load_job(replay["local_job_id"])["request_hash"] == native_request_hash(req)


def test_scoped_marker_presence_denies_legacy_even_when_malformed(node):
    from vibemql5.core.native_ownership import OwnershipAuthority, OwnershipBlocked
    marker = node["root"] / "state" / "fleet" / "scoped-install.json"
    marker.write_bytes(b"partial")
    with pytest.raises(OwnershipBlocked, match="SCOPED_OWNERSHIP_REQUIRED"):
        OwnershipAuthority(node["root"]).require_closed()


@pytest.mark.parametrize("mutation", [lambda logical: logical["config"].update(symbol="EURUSD\nLogin=secret"),
    lambda logical: logical["config"].update(model=True),
    lambda logical: logical["normalization"].update(effective_period={"from_date":"2026.02.30","to_date":"2026.03.01"}),
    lambda logical: logical["normalization"]["execution_delay"].update(execution_mode=0),
    lambda logical: logical.update(untrusted_qualified=True)])
def test_native_normalized_config_rejects_malformed_or_ini_injection(node, mutation):
    req = request(node); mutation(req["logical_config"])
    denied("NATIVE_REQUEST_INVALID", lambda: native_request_hash(req))


def test_input_set_and_include_drift_denied_before_loading_qualification(node, monkeypatch):
    import vibemql5.fleet.native as native
    req = request(node); calls = []
    monkeypatch.setattr(native, "load_installation", lambda *_: calls.append("qualification"))
    include = node["root"] / "workspaces/demo/Include/new.mqh"
    include.parent.mkdir(); include.write_bytes(b"new include")
    denied("NATIVE_INPUT_CHANGED", lambda: RoutedNativeAdapter(node["root"]).reserve(req, "op"))
    assert calls == []


@pytest.fixture
def routed_source_fixture(node, monkeypatch):
    """SYNTHETIC_DRIVER_AND_TRUST_SEAM_ONLY; never physical qualification."""
    from types import SimpleNamespace
    import vibemql5.fleet.native as native
    from vibemql5.fleet.identity import normalize_path
    from vibemql5.fleet.resources import ResourceAuthority
    from vibemql5.fleet.native_authorization import GatewayNativeSigner, NativeAuthorizationVerifier
    from vibemql5.core.jobs import new_job_id
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    placement = freeze(node, "qualified-source-fixture", target={**ref(node["registry"]), "route_generation": 1}, operation="qualified-freeze")
    raw = node["source"].read_bytes()
    req = native_request(placement, logical_fixture(), [{"path":"Experts/DemoEA.mq5","sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}])
    key = Ed25519PrivateKey.generate(); public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    audience = "synthetic-driver-gateway"
    now = [1000]
    signer = GatewayNativeSigner(key, audience, max_authorization_ms=1000)
    verifier = NativeAuthorizationVerifier(public, audience, clock_ms=lambda: now[0])
    base = {**fence(req), "global_job_id":"global-fixture", "node_operation_id":"node-fixture",
        "local_job_id":new_job_id(), "session_id":"session-fixture"}
    sequence = [0]; grants = []
    def provide(phase, prior, event="phase_admission"):
        sequence[0] += 1
        binding = {"audience":audience,"request_sha256":native_request_hash(req),"target":req["placement"]["target"],
            "phase":phase,"event":event, **{k:prior[k] for k in ("node_operation_id","global_job_id","local_job_id","session_id")},
            "sequence":sequence[0],"challenge":f"{sequence[0]:032x}"}
        grant = signer.issue(issued_ms=now[0],expires_ms=now[0]+1000,authorization_id="grant-"+str(sequence[0]),**binding)
        grants.append(phase)
        return {**prior,"phase":phase,"sequence":binding["sequence"],"challenge":binding["challenge"],
                "authorization":verifier.verify(grant, **binding),"event":event}
    pending_steps=[]; completed_steps=[]; lost_events=set()
    def begin_effect(phase,event):
        if event in lost_events: raise OSError("SYNTHETIC_GRANT_LOST")
        proof=provide(phase,base,event)["authorization"]
        pending_steps.append((phase,event,proof))
        return proof
    def complete_effect(phase,event,proof,**kwargs):
        assert pending_steps and pending_steps[0]==(phase,event,proof)
        pending_steps.pop(0); completed_steps.append((phase,event))
        return {"evidence":"SYNTHETIC_DURABLE_STEP_ONLY"}
    base.update(begin_effect=begin_effect,complete_effect=complete_effect)
    install = {"binding":req["placement"]["binding"],"metaeditor":normalize_path(node["terminals"][0].metaeditor_path),
        "gateway_public_key":public,"gateway_audience":audience,
        "include_root":str(Path(req["placement"]["binding"]["data_root"])/"MQL5/Include"),
        "agent_root":str(Path(req["placement"]["binding"]["data_root"])/"Tester")}
    for name in ("include_root","agent_root"): Path(install[name]).mkdir(parents=True)
    policy = {"resource_max_records":32,"resource_wait_ms":25,"compile_timeout_seconds":2,"test_timeout_seconds":2}
    ResourceAuthority(node["root"],initialize=True,max_records=32,wait_ms=25)
    monkeypatch.setattr(native,"load_installation",lambda *_: SimpleNamespace(installation=install,policy=policy,operator_public_key=public,candidate_sha256="c"*64,runtime_sha256="d"*64))
    idle = []
    monkeypatch.setattr(native,"assert_installation_idle",lambda *_args,**_kwargs:idle.append(True))
    calls = []
    class HarmlessLaunch:
        def __init__(self,authority,armed,revalidate,on_bound=None,should_cancel=None,complete=None,require_current=None):
            self.authority,self.expected,self.guard,self.bound = authority,armed,revalidate,on_bound
            self.process,self.observed = None,None
            self.complete=complete
            self.require_current=require_current
        def __call__(self,command,**kwargs):
            self.guard("process_create"); self.require_current("process_create"); self.observed=SimpleNamespace(identity=current_identity)
            self.process=object(); self.bound(current_identity()); self.complete("process_create"); self.guard("process_resume"); self.complete("process_resume")
            calls.append("harmless_launch")
            return self
        def finish(self): return self.authority.close_zero_attempt(self.expected)
        def close_handles(self): calls.append("close_fixture_handles")
    monkeypatch.setattr(native,"OwnedWindowsLaunch",HarmlessLaunch)
    def compile_fixture(self,workspace,ea,alias,run_dir,**kwargs):
        assert kwargs["owned_launch"] and kwargs["before_effect"]
        kwargs["before_effect"]("deploy_source_copy")
        kwargs["after_effect"]("deploy_source_copy")
        kwargs["owned_launch"]([node["terminals"][0].metaeditor_path],cwd=str(node["root"]))
        output=Path(req["placement"]["binding"]["data_root"])/"MQL5/Experts/VibeMQL5/demo/DemoEA.ex5"
        output.parent.mkdir(parents=True); output.write_bytes(b"SYNTHETIC_COMPILED_BYTES")
        captured=run_dir/"compiled.ex5"; captured.write_bytes(output.read_bytes())
        calls.append("compile_fixture")
        return {"status":"PASSED","expert_name":"VibeMQL5\\demo\\DemoEA","ex5_path":str(output),
            "immutable_ex5":{"path":str(captured),"sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"bytes":output.stat().st_size}}
    def tester_fixture(self,*args,**kwargs):
        kwargs["before_effect"]("tester_set_copy")
        kwargs["after_effect"]("tester_set_copy")
        kwargs["owned_launch"]([node["terminals"][0].terminal_path],cwd=str(node["root"]))
        kwargs["before_effect"]("tester_capture")
        kwargs["after_effect"]("tester_capture")
        calls.append("tester_fixture")
        return {"status":"COMPLETED","execution_status":"PASSED","evidence":"SYNTHETIC_DRIVER_ONLY"}
    monkeypatch.setattr(native.CompilerDriver,"compile",compile_fixture)
    monkeypatch.setattr(native.TesterDriver,"run",tester_fixture)
    adapter = RoutedNativeAdapter(node["root"],authorization_provider=provide)
    reserve_fence = provide("reserve",base)
    return SimpleNamespace(adapter=adapter,req=req,base=base,provide=provide,calls=calls,grants=grants,
        reserve_fence=reserve_fence,now=now,policy=policy,node=node,native=native,install=install,signer=signer,verifier=verifier,pending_steps=pending_steps,completed_steps=completed_steps,lost_events=lost_events)


def test_concrete_production_driver_composes_owned_phases_and_common_resources(routed_source_fixture):
    fixture = routed_source_fixture
    reservation = fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)
    assert reservation["local_job_id"] == fixture.base["local_job_id"]
    from vibemql5.core.native_ownership import OwnershipAuthority
    before_generation=OwnershipAuthority(fixture.node["root"]).load()["generation"]
    started = fixture.adapter.start_reserved(reservation["local_job_id"],fixture.req,fixture.provide("start",fixture.base))
    assert started["payload"]["execution"]["status"] == "COMPLETED"
    assert fixture.calls == ["harmless_launch","compile_fixture","close_fixture_handles","harmless_launch","tester_fixture","close_fixture_handles"]
    assert {"reserve","start","deploy","test","capture","result"} <= set(fixture.grants)
    from vibemql5.core.native_ownership import OwnershipAuthority
    from vibemql5.fleet.resources import ResourceAuthority
    assert OwnershipAuthority(fixture.node["root"]).load()["generation"] == before_generation+2
    assert OwnershipAuthority(fixture.node["root"]).status()["admission"] == "AVAILABLE"
    resources = ResourceAuthority(fixture.node["root"],max_records=32,wait_ms=25).snapshot()
    assert all(row["status"] == "RELEASED" for row in resources)
    fixture.adapter.start_reserved(reservation["local_job_id"],fixture.req,fixture.provide("start",fixture.base))
    assert fixture.calls.count("compile_fixture") == fixture.calls.count("tester_fixture") == 1


def test_real_path_rejects_self_asserted_and_expired_authorization_before_owned_launch(routed_source_fixture):
    fixture=routed_source_fixture
    forged={**fixture.reserve_fence,"authorization":{"verified":True}}
    denied("NATIVE_AUTHORIZATION_UNVERIFIED",lambda:fixture.adapter.reserve(fixture.req,"node-fixture",forged))
    fixture.now[0]=2001
    denied("NATIVE_AUTHORIZATION_UNVERIFIED",lambda:fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence))
    assert fixture.calls==[]


def test_gate_loss_between_compile_copy_and_create_never_launches_fixture(routed_source_fixture,monkeypatch):
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    def interrupted_compile(self,workspace,ea,alias,run_dir,**kwargs):
        kwargs["before_effect"]("deploy_source_copy")
        fixture.node["source"].write_bytes(b"SYNTHETIC_WRITER_DRIFT")
        kwargs["owned_launch"]([fixture.node["terminals"][0].metaeditor_path],cwd=str(fixture.node["root"]))
    monkeypatch.setattr(fixture.native.CompilerDriver,"compile",interrupted_compile)
    denied("NATIVE_RECOVERY_REQUIRED",lambda:fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base)))
    assert "harmless_launch" not in fixture.calls
    assert fixture.adapter._load_job(job)["fleet_effects"]["start"]["status"]=="PENDING"


def test_driver_copy_seams_use_verified_bytes_even_if_file_changes_at_copy_window(node):
    from vibemql5.core.compiler import CompilerDriver
    from vibemql5.core.tester import TesterDriver
    source_bytes=node["source"].read_bytes()
    include=node["root"] / "workspaces/demo/Include/helper.mqh"; include.parent.mkdir(); include.write_bytes(b"original include")
    frozen={"Experts/DemoEA.mq5":source_bytes,"Include/helper.mqh":include.read_bytes()}
    def mutate_after_gate(event):
        if event=="deploy_source_copy":node["source"].write_bytes(b"changed after gate")
        if event=="deploy_include_copy":include.write_bytes(b"changed include after gate")
    deployed,_=CompilerDriver(node["root"])._deploy("demo","Experts/DemoEA.mq5","MT5-2",before_effect=mutate_after_gate,frozen_inputs=frozen)
    assert deployed.read_bytes()==source_bytes
    target=Path(node["terminals"][0].data_root)/"MQL5/Include/VibeMQL5/demo/helper.mqh"
    assert target.read_bytes()==b"original include"
    source_set=node["root"] / "workspaces/demo/fixture.set"; source_set.write_bytes(b"original set")
    def set_gate(event):
        if event=="tester_set_copy":source_set.write_bytes(b"changed after set gate")
    name=TesterDriver(node["root"])._copy_set("demo","fixture.set","MT5-2","fixed-fixture",before_effect=set_gate,frozen_set_bytes=b"original set")
    for root in (Path(node["terminals"][0].terminal_path).parent,Path(node["terminals"][0].data_root)):
        assert (root/"MQL5/Profiles/Tester"/name).read_bytes()==b"original set"


def test_native_manifest_mechanism_limits_deny_before_large_reads(node):
    import vibemql5.fleet.native as native
    req=request(node)
    req["input_manifest"][0]["bytes"]=native.MAX_FILE_BYTES+1
    denied("NATIVE_REQUEST_INVALID",lambda:native_request_hash(req))
    req=request(node); item=req["input_manifest"][0]
    req["input_manifest"]=[{**item,"path":f"Include/file{index}.mqh","bytes":native.MAX_FILE_BYTES} for index in range(3)]
    denied("NATIVE_REQUEST_INVALID",lambda:native_request_hash(req))


def test_node_journal_sealed_phase_provider_is_consumed_without_caller_fence_booleans(routed_source_fixture):
    fixture=routed_source_fixture
    fixture.adapter.authorization_provider=None
    def node_provider(phase): return fixture.provide(phase,fixture.base)["authorization"]
    reserve={**fixture.reserve_fence,"authorization_provider":node_provider}
    job=fixture.adapter.reserve(fixture.req,"node-fixture",reserve)["local_job_id"]
    start={**fixture.provide("start",fixture.base),"authorization_provider":node_provider}
    receipt=fixture.adapter.start_reserved(job,fixture.req,start)
    assert receipt["payload"]["execution"]["status"]=="COMPLETED"


def test_authorization_expiry_after_live_launch_retains_handles_and_does_not_terminate(routed_source_fixture,monkeypatch):
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    def expire_after_launch(self,*args,**kwargs):
        kwargs["owned_launch"]([fixture.node["terminals"][0].terminal_path],cwd=str(fixture.node["root"]))
        fixture.now[0]+=1001
        # A deliberately lost/expired grant at the next boundary cannot cause kill or retry.
        fixture.lost_events.add("tester_set_copy:0001")
        kwargs["before_effect"]("tester_set_copy")
    monkeypatch.setattr(fixture.native.TesterDriver,"run",expire_after_launch)
    denied("NATIVE_RECOVERY_REQUIRED",lambda:fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base)))
    assert fixture.calls.count("close_fixture_handles")==1  # Compiler only; live tester retained.
    assert fixture.adapter._active[job]["launch"].process is not None
    from vibemql5.core.native_ownership import OwnershipAuthority
    assert OwnershipAuthority(fixture.node["root"]).status()["admission"]=="BLOCKED"
    assert fixture.adapter._load_job(job)["fleet_effects"]["start"]["status"]=="PENDING"



def test_started_step_completes_after_ttl_then_next_effect_uses_new_grant(routed_source_fixture,monkeypatch):
    """SYNTHETIC_CLOCK_AND_DRIVER_ONLY: expiry never renews an old effect grant."""
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    consumed=[]
    def long_returning_effect(self,*args,**kwargs):
        kwargs["owned_launch"]([fixture.node["terminals"][0].terminal_path],cwd=str(fixture.node["root"]))
        kwargs["before_effect"]("tester_capture")
        consumed.append(fixture.pending_steps[0][2])
        fixture.now[0]+=1001
        kwargs["after_effect"]("tester_capture")
        kwargs["before_effect"]("tester_capture")
        consumed.append(fixture.pending_steps[0][2])
        kwargs["after_effect"]("tester_capture")
        return {"status":"COMPLETED","execution_status":"PASSED","evidence":"SYNTHETIC_RETURN_AFTER_TTL_ONLY"}
    monkeypatch.setattr(fixture.native.TesterDriver,"run",long_returning_effect)
    receipt=fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base))
    assert receipt["payload"]["execution"]["status"]=="COMPLETED"
    assert consumed[0].binding["event"]=="tester_capture:0001"
    assert consumed[1].binding["event"]=="tester_capture:0002"
    assert consumed[0].grant_sha256!=consumed[1].grant_sha256
    assert consumed[0].binding["sequence"]<consumed[1].binding["sequence"]
    assert not fixture.pending_steps and fixture.completed_steps[-1]==("result","result_promote:0001")
    assert job not in fixture.adapter._active

def test_native_installed_scope_path_uses_scoped_phase_authority_and_never_legacy_lane(routed_source_fixture,monkeypatch):
    """Explicit private fixture coordinator, not a signed capacity qualification."""
    fixture=routed_source_fixture
    from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator,CONFLICT_MATRIX
    from vibemql5.fleet.resources import physical_resources,ResourceAuthority
    from vibemql5.core.native_ownership import OwnershipAuthority,OwnershipBlocked
    rows=[]
    for index,terminal in enumerate(fixture.node["terminals"]):
        binding=fixture.node["registry"]["terminals"][index]["binding"]
        resources={"executable":binding["terminal_canonical_path"],"data_root":binding["data_canonical_path"],
            "include_root":str(Path(binding["data_canonical_path"])/"MQL5/Include"),"agent_root":str(Path(binding["data_canonical_path"])/"Tester")}
        for name in ("include_root","agent_root"):Path(resources[name]).mkdir(parents=True,exist_ok=True)
        identity=fixture.node["registry"]["terminals"][index]
        rows.append({"terminal_id":identity["terminal_id"],"terminal_generation":identity["terminal_generation"],
            "resources":resources,"physical_identities":physical_resources(resources)})
    profile={"schema":"fleet.capacity-profile/1","device_id":fixture.req["placement"]["owner_device_id"],"install_epoch":"b"*32,
        "capacity":2,"candidate_sha256":"c"*64,"runtime_sha256":"d"*64,"source_manifest":[],"terminals":rows,
        "load_receipt":None,"closure_receipt":None,"max_records":20,"lock_wait_ms":1000,"conflict_matrix":CONFLICT_MATRIX}
    coordinator=ScopedResourceCoordinator._for_fixture(fixture.node["root"],profile,initialize=True)
    marker=fixture.node["root"] / "state/fleet/scoped-install.json"; marker.write_bytes(b"PRIVATE_TEST_SEAM_ONLY")
    monkeypatch.setattr(ScopedResourceCoordinator,"open_installed",classmethod(lambda cls,*args,**kwargs:coordinator))
    with pytest.raises(OwnershipBlocked):OwnershipAuthority(fixture.node["root"]).require_closed()
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    receipt=fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base))
    assert receipt["payload"]["execution"]["status"]=="COMPLETED"
    assert ResourceAuthority(fixture.node["root"],max_records=32,wait_ms=25).snapshot()==[]
    with coordinator.transaction() as db:
        records=[json.loads(row[0]) for row in db.execute("SELECT record FROM reservations")]
    assert len(records)==2 and all(record["status"]=="RELEASED" and record["phase"]=="CLOSED" for record in records)
    assert records[-1]["generation"]==2  # Compiler close then tester arm under one held scoped lease.


def test_two_prepared_scoped_producers_overlap_and_pinned_old_candidate_survives_new_revision(routed_source_fixture,monkeypatch):
    """Private qualification/OS driver fixtures; exercises the production orchestration path."""
    import concurrent.futures
    import threading
    from types import SimpleNamespace
    from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator,CONFLICT_MATRIX
    from vibemql5.fleet.resources import physical_resources
    from vibemql5.fleet.identity import normalize_path
    from vibemql5.core.jobs import new_job_id
    fixture=routed_source_fixture; node=fixture.node; root=node["root"]
    fixture.policy["resource_wait_ms"]=1000
    source2=root/"workspaces/other/Experts/OtherEA.mq5"; source2.parent.mkdir(parents=True); source2.write_bytes(b"void OnTick(){/*second*/}\n")
    checkpoint2=RevisionManager(root).create_checkpoint("other","Experts/OtherEA.mq5")
    session2=ProjectSessionManager(root).create("P2","other","Experts/OtherEA.mq5",checkpoint_id=checkpoint2["checkpoint_id"])
    target2={**ref(node["registry"],1),"route_generation":1}
    node["projects"].enroll("P2",node["registry"]["device_id"],expected_session_revision=session2["revision_id"],expected_session_sha256=session2["revision_sha256"],operation_id="enroll-2",default_target=target2)
    placement2=node["projects"].freeze("P2","second-frozen",writer_id="fixture-writer",expected_placement_revision=1,expected_session_revision=session2["revision_id"],expected_session_sha256=session2["revision_sha256"],operation_id="freeze-2")
    req2=native_request(placement2,logical_fixture(),[{"path":"Experts/OtherEA.mq5","sha256":hashlib.sha256(source2.read_bytes()).hexdigest(),"bytes":source2.stat().st_size}])
    rows=[]; installs={fixture.req["placement"]["target"]["terminal_id"]:fixture.install}
    for index,terminal in enumerate(node["terminals"]):
        identity=node["registry"]["terminals"][index]; binding=identity["binding"]
        resources={"executable":binding["terminal_canonical_path"],"data_root":binding["data_canonical_path"],"include_root":str(Path(binding["data_canonical_path"])/"MQL5/Include"),"agent_root":str(Path(binding["data_canonical_path"])/"Tester")}
        for name in ("include_root","agent_root"):Path(resources[name]).mkdir(parents=True,exist_ok=True)
        rows.append({"terminal_id":identity["terminal_id"],"terminal_generation":identity["terminal_generation"],"resources":resources,"physical_identities":physical_resources(resources)})
        installs.setdefault(identity["terminal_id"],{**resources,"binding":{"executable":resources["executable"],"data_root":resources["data_root"]},"metaeditor":normalize_path(terminal.metaeditor_path),"gateway_public_key":fixture.install["gateway_public_key"],"gateway_audience":fixture.install["gateway_audience"]})
    profile={"schema":"fleet.capacity-profile/1","device_id":node["registry"]["device_id"],"install_epoch":"b"*32,"capacity":2,"candidate_sha256":"c"*64,"runtime_sha256":"d"*64,"source_manifest":[],"terminals":rows,"load_receipt":None,"closure_receipt":None,"max_records":20,"lock_wait_ms":1000,"conflict_matrix":CONFLICT_MATRIX}
    coordinator=ScopedResourceCoordinator._for_fixture(root,profile,initialize=True)
    (root/"state/fleet/scoped-install.json").write_bytes(b"PRIVATE_TEST_SEAM_ONLY")
    monkeypatch.setattr(ScopedResourceCoordinator,"open_installed",classmethod(lambda cls,*args,**kwargs:coordinator))
    monkeypatch.setattr(fixture.native,"load_installation",lambda _root,req:SimpleNamespace(installation=installs[req["placement"]["target"]["terminal_id"]],policy=fixture.policy,operator_public_key=fixture.install["gateway_public_key"],candidate_sha256="c"*64,runtime_sha256="d"*64))
    base2={**fence(req2),"global_job_id":"global-2","node_operation_id":"node-2","local_job_id":new_job_id(),"session_id":"session-fixture"}
    seq2=[0]; pending2=[]
    def provide2(phase,prior,event="phase_admission"):
        seq2[0]+=1
        binding={"audience":fixture.install["gateway_audience"],"request_sha256":native_request_hash(req2),"target":target2,"phase":phase,"event":event,**{k:prior[k] for k in ("node_operation_id","global_job_id","local_job_id","session_id")},"sequence":seq2[0],"challenge":f"{seq2[0]:032x}"}
        grant=fixture.signer.issue(issued_ms=fixture.now[0],expires_ms=fixture.now[0]+1000,authorization_id="second-"+str(seq2[0]),**binding)
        return {**prior,"phase":phase,"event":event,"sequence":binding["sequence"],"challenge":binding["challenge"],"authorization":fixture.verifier.verify(grant,**binding)}
    def begin2(phase,event):
        proof=provide2(phase,base2,event)["authorization"]; pending2.append((phase,event,proof));return proof
    def finish2(phase,event,proof,**kwargs):
        assert pending2.pop(0)==(phase,event,proof)
    base2.update(begin_effect=begin2,complete_effect=finish2)
    adapter2=RoutedNativeAdapter(root,authorization_provider=provide2)
    job1=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    job2=adapter2.reserve(req2,"node-2",provide2("reserve",base2))["local_job_id"]
    requests={job1:fixture.req,job2:req2}; captured={}; reached=threading.Barrier(3); released=threading.Event()
    worker_index={job1:0,job2:1};stages=["NOT_ENTERED","NOT_ENTERED"]
    def compile_exact(self,workspace,ea,alias,run_dir,**kwargs):
        index=worker_index[run_dir.name];stages[index]="COMPILER_DRIVER_ENTERED"
        req=requests[run_dir.name];captured[run_dir.name]=dict(kwargs["frozen_inputs"])
        kwargs["before_effect"]("deploy_source_copy");kwargs["after_effect"]("deploy_source_copy")
        terminal=self.inventory.get(alias);kwargs["owned_launch"]([terminal.metaeditor_path],cwd=str(root))
        stages[index]="COMPILER_LAUNCHED"
        output=(Path(terminal.data_root)/"MQL5/Experts/VibeMQL5"/workspace/Path(ea).relative_to("Experts")).with_suffix(".ex5")
        output.parent.mkdir(parents=True);output.write_bytes(b"SYNTHETIC_COMPILED_BYTES")
        immutable=run_dir/"compiled.ex5";immutable.write_bytes(output.read_bytes())
        return {"status":"PASSED","expert_name":"VibeMQL5\\"+workspace+"\\"+Path(ea).stem,"ex5_path":str(output),"immutable_ex5":{"path":str(immutable),"sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"bytes":output.stat().st_size}}
    def simultaneous_test(self,job_id,workspace,ea,alias,*args,**kwargs):
        index=worker_index[job_id];stages[index]="TESTER_DRIVER_ENTERED"
        kwargs["owned_launch"]([self.inventory.get(alias).terminal_path],cwd=str(root))
        stages[index]="TESTER_LAUNCHED"
        stages[index]="BARRIER_ENTERED";reached.wait(timeout=10);stages[index]="BARRIER_PASSED"
        assert released.wait(10);stages[index]="RELEASE_OBSERVED"
        kwargs["before_effect"]("tester_capture");kwargs["after_effect"]("tester_capture")
        stages[index]="DRIVER_RETURNED"
        return {"status":"COMPLETED","evidence":"SYNTHETIC_CONCURRENT_DRIVER_ONLY"}
    monkeypatch.setattr(fixture.native.CompilerDriver,"compile",compile_exact);monkeypatch.setattr(fixture.native.TesterDriver,"run",simultaneous_test)
    old_source=node["source"].read_bytes();old_frozen=copy.deepcopy(fixture.req["placement"])
    def start_scoped(index,adapter,job,request,proof):
        stages[index]="START_RESERVED_ENTERED"
        return adapter.start_reserved(job,request,proof)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future1=pool.submit(start_scoped,0,fixture.adapter,job1,fixture.req,fixture.provide("start",fixture.base))
        future2=pool.submit(start_scoped,1,adapter2,job2,req2,provide2("start",base2))
        try:
            reached.wait(timeout=10)  # Both long producers hold distinct scoped leases simultaneously.
            with fixture.adapter.concurrency.mutation("fleet_source_guard",resource="demo:Experts/DemoEA.mq5",wait_seconds=0):
                node["source"].write_bytes(b"void OnTick(){/*new candidate*/}\n")
                checkpoint=RevisionManager(root).create_checkpoint("demo","Experts/DemoEA.mq5")
                session=ProjectSessionManager(root).update("P",node["session"]["revision_id"],expected_revision_sha256=node["session"]["revision_sha256"],checkpoint_id=checkpoint["checkpoint_id"],operation_id="write-while-old-running")
                args=dict(expected_placement_revision=1,expected_session_revision=node["session"]["revision_id"],expected_session_sha256=node["session"]["revision_sha256"],new_session_revision=session["revision_id"],new_session_sha256=session["revision_sha256"],operation_id="advance-session")
                updated=node["projects"].advance_session("P",**args)
                assert updated["placement_revision"]==2
                assert node["projects"].advance_session("P",**args)["idempotent_recovered"]
        finally:
            primary=sys.exception()
            if primary is not None:
                primary.add_note("SCOPED_OVERLAP_FIXTURE "+str({"stages":scoped_fixture_stages(stages)}))
            released.set()
            with preserve_fixture_failure():
                results=collect_scoped_fixture_futures([future1,future2],stages,timeout=10)
        assert results[0]["payload"]["execution"]["status"]=="COMPLETED"
        assert results[1]["payload"]["execution"]["status"]=="COMPLETED"
    assert captured[job1]["Experts/DemoEA.mq5"]==old_source
    assert (root/"runs"/job1/"source_snapshot/Experts/DemoEA.mq5").read_bytes()==old_source
    assert node["projects"].load_frozen(old_frozen["frozen_id"])==old_frozen
    assert node["projects"].resume(old_frozen["frozen_id"])["status"]=="FLEET_SESSION_CONFLICT"
    assert not fixture.pending_steps and not pending2
    with coordinator.transaction() as db:
        records=[json.loads(row[0]) for row in db.execute("SELECT record FROM reservations")]
    assert len(records)==4 and all(row["status"]=="RELEASED" and row["phase"]=="CLOSED" for row in records)


def test_cancelled_owned_compile_cannot_start_tester_even_if_ex5_was_published(routed_source_fixture,monkeypatch):
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    original=fixture.native.CompilerDriver.compile
    def cancelled_compile(*args,**kwargs):
        result=original(*args,**kwargs);result["cancelled"]=True;return result
    monkeypatch.setattr(fixture.native.CompilerDriver,"compile",cancelled_compile)
    receipt=fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base))
    assert receipt["payload"]["execution"]=={"status":"CANCELLED","completion_reason":"CANCEL_REQUESTED_DURING_COMPILE"}
    assert fixture.calls.count("harmless_launch")==1 and "tester_fixture" not in fixture.calls
    assert fixture.completed_steps[-1]==("result","result_promote:0001")


def test_deployed_ex5_drift_after_tester_preparation_denies_process_creation(routed_source_fixture,monkeypatch):
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    def tamper_before_launch(self,*args,**kwargs):
        kwargs["before_effect"]("tester_set_copy");kwargs["after_effect"]("tester_set_copy")
        deployed=Path(fixture.install["binding"]["data_root"])/"MQL5/Experts/VibeMQL5/demo/DemoEA.ex5"
        deployed.write_bytes(b"SYNTHETIC_EX5_TAMPER_AFTER_PREPARATION")
        kwargs["owned_launch"]([fixture.node["terminals"][0].terminal_path],cwd=str(fixture.node["root"]))
    monkeypatch.setattr(fixture.native.TesterDriver,"run",tamper_before_launch)
    denied("NATIVE_RECOVERY_REQUIRED",lambda:fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base)))
    assert fixture.calls.count("harmless_launch")==1  # No tester create action passed its final boundary.
    assert fixture.adapter._load_job(job)["fleet_effects"]["start"]["status"]=="PENDING"


@pytest.mark.parametrize("field",["creation","image"])
def test_signed_cancel_for_other_process_cannot_touch_owned_job(routed_source_fixture,field):
    from vibemql5.fleet.project_targets import digest
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    process=current_identity();other={**process,field:process[field]+"-other"}
    prior=fixture.provide("start",fixture.base)
    binding={**prior["authorization"].binding,"phase":"cancel","process_sha256":digest(other)}
    grant=fixture.signer.issue(issued_ms=fixture.now[0],expires_ms=fixture.now[0]+1000,authorization_id="wrong-process-grant",**binding)
    cancel={**prior,"phase":"cancel","authorization":fixture.verifier.verify(grant,**binding),"process":process}
    denied("NATIVE_AUTHORIZATION_UNVERIFIED",lambda:fixture.adapter.effect(job,"cancel",fixture.req,cancel))
    assert fixture.calls==[] and not fixture.adapter._active
    assert fixture.adapter._load_job(job)["fleet_effects"]=={}


def test_terminal_closure_is_historical_bound_and_read_only_after_normal_lease_return(routed_source_fixture):
    fixture=routed_source_fixture
    job=fixture.adapter.reserve(fixture.req,"node-fixture",fixture.reserve_fence)["local_job_id"]
    denied("NATIVE_CLOSURE_UNAVAILABLE",lambda:fixture.adapter.terminal_closure(job,fixture.req))
    fixture.adapter.start_reserved(job,fixture.req,fixture.provide("start",fixture.base))
    closure=fixture.adapter.terminal_closure(job,fixture.req)
    assert closure["schema"]=="fleet.native.closure/1" and closure["lease_release"]=="RETURNED"
    assert closure["request_sha256"]==native_request_hash(fixture.req) and closure["target"]==fixture.req["placement"]["target"]
    assert [row["phase"] for row in closure["phases"]]==["deploy","test"]
    assert all(row["ownership_record"]["phase"]=="CLOSED" and row["ownership_record"]["worker"] is None and row["descendants"]=="EXACT_DESCENDANTS_EXITED" for row in closure["phases"])
    fixture.now[0]+=1001  # Historical truth does not reacquire or renew a phase proof.
    reopened=RoutedNativeAdapter(fixture.node["root"])
    assert reopened.terminal_closure(job,fixture.req)==closure
    other=copy.deepcopy(fixture.req);other["logical_config"]["config"]["symbol"]="GBPUSD"
    denied("NATIVE_CLOSURE_UNAVAILABLE",lambda:reopened.terminal_closure(job,other))
    stored=fixture.adapter._load_job(job)["fleet_terminal_closure"]
    stored["receipt"]["phases"][0]["ownership_record"]["phase"]="BOUND"
    fixture.adapter.jobs.update_fields(job,fleet_terminal_closure=stored)
    denied("NATIVE_CLOSURE_UNAVAILABLE",lambda:reopened.terminal_closure(job,fixture.req))


def test_retained_current_handles_keep_stop_pending_but_persisted_unknown_alone_does_not(node):
    from types import SimpleNamespace
    adapter=RoutedNativeAdapter(node["root"])
    assert adapter.has_retained_work() is False
    # Explicit fixture shapes stand for retained OS references; the query never polls/closes them.
    no_handles=SimpleNamespace(process=None,thread=None,job=None,observed=None)
    adapter._active["fixture-unknown"]={"launch":no_handles}
    assert adapter.has_retained_work() is False
    def forbidden():pytest.fail("retention query must not poll or close")
    held=SimpleNamespace(process=None,thread=None,job=object(),observed=None,poll=forbidden,close_handles=forbidden)
    adapter._active["fixture-owned"]={"launch":held}
    assert adapter.has_retained_work() is True
    held.job=None;held.observed=SimpleNamespace(handle=object())
    assert adapter.has_retained_work() is True
    held.observed=None;held.process=object()
    assert adapter.has_retained_work() is True
    adapter._active.clear()
    assert adapter.has_retained_work() is False
