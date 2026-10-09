"""Product SDK source tests. Synthetic adapters never qualify SDK or a host."""
from __future__ import annotations

import copy
import importlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from vibemql5.fleet import sdk_protocol as protocol
from vibemql5.fleet.sdk_worker import observe_once
from vibemql5.fleet.sdk_qualification import (DOMAIN, QualificationError, QualifiedSdkInstallation,
                                             payload_manifest, validate_operator_approval)
from vibemql5.fleet.sdk_controller import _run_owned, observe_under_owned_lease, read_local, QualifiedReadAdapter


@pytest.fixture
def sdk_request(tmp_path):
    executable = str((tmp_path / "terminal64.exe").resolve())
    return {"schema": protocol.REQUEST_SCHEMA, "operation": "state", "nonce": "a" * 32,
        "target": {"schema": "fleet.target/1", "device_id": "dev_" + "a" * 32,
                   "terminal_id": "term_" + "b" * 32, "terminal_generation": 1},
        "qualification_sha256": "c" * 64, "budget_ms": 10000, "scope": None,
        "binding": {"executable": executable, "data_root": str((tmp_path / "data").resolve()),
                    "alias": "MT5-A", "process": {"pid": 1234, "creation": "123456789", "image": executable}},
        "owner": {"epoch": "fixture", "generation": 2, "token": "fixture-token",
            "operation_id": "fixture-sdk", "kind": "fixture-read",
            "parent": {"pid": 2222, "creation": "2", "image": str(Path(sys.executable).resolve())}}}


class SDK:
    """A pure Python fixture; no method can import or attach SDK."""
    def __init__(self, sdk_request):
        self.events, self.effects = [], {}
        self.info = SimpleNamespace(path=str(Path(sdk_request["binding"]["executable"]).parent),
            data_path=sdk_request["binding"]["data_root"], connected=True, build=6182, ping_last=20000, trade_allowed=True)
        self.account = SimpleNamespace(login=987654321, server="Fixture-Server", currency="USD", balance=10.0,
            equity=11.0, margin=1.0, margin_free=10.0, profit=1.0, trade_allowed=False, trade_expert=False)

    def call(self, name, answer=None):
        self.events.append(name)
        if name in self.effects:
            effect = self.effects[name]
            if isinstance(effect, BaseException):
                raise effect
            return effect()
        return answer

    def initialize(self, path, *, timeout): return self.call("initialize", True)
    def terminal_info(self): return self.call("terminal_info", self.info)
    def account_info(self): return self.call("account_info", self.account)
    def positions_total(self): return self.call("positions_total", 2)
    def orders_total(self): return self.call("orders_total", 3)
    def shutdown(self): return self.call("shutdown")


def synthetic(sdk_request, sdk=None, **kwargs):
    sdk = sdk or SDK(sdk_request)
    return observe_once(sdk_request, sdk_loader=lambda: sdk,
                        process_observer=lambda: copy.deepcopy(sdk_request["binding"]["process"]), **kwargs)


def test_real_worker_call_requires_installed_gate_before_any_sdk_or_probe(sdk_request, monkeypatch):
    calls = []
    monkeypatch.setattr(importlib, "import_module", lambda name: calls.append(name))
    with pytest.raises(QualificationError): observe_once(sdk_request)
    assert calls == []
    with pytest.raises(protocol.ProtocolError): observe_once(sdk_request, sdk_loader=lambda: SDK(sdk_request))
    assert calls == []


def test_worker_freezes_request_before_injected_loader_can_mutate_caller_data(sdk_request):
    frozen = copy.deepcopy(sdk_request)
    sdk = SDK(sdk_request)
    def loader():
        sdk_request["nonce"] = "d" * 32
        sdk_request["target"]["terminal_generation"] = 2
        return sdk
    answer = observe_once(sdk_request, sdk_loader=loader,
        process_observer=lambda: copy.deepcopy(frozen["binding"]["process"]))
    assert answer["status"] == "SUCCEEDED" and answer["nonce"] == frozen["nonce"]
    protocol.validate_result(answer, frozen)
    with pytest.raises(protocol.ProtocolError): protocol.validate_result(answer, sdk_request)


@pytest.mark.parametrize("operation", ["state", "account"])
def test_actual_observation_source_synthetic_projection_mask_and_shutdown(sdk_request, operation):
    sdk_request["operation"] = operation
    sdk = SDK(sdk_request)
    answer = synthetic(sdk_request, sdk, evidence="REAL_SDK_OPERATOR_APPROVED")
    assert answer["status"] == "SUCCEEDED" and answer["operation"] == operation
    assert answer["evidence"] == "SYNTHETIC_SDK_ONLY"
    assert answer["account"]["login_masked"] == "*****4321"
    assert answer["terminal"]["alias"] == "MT5-A"
    assert answer["observed_binding"] == sdk_request["binding"]
    assert sdk.events.count("shutdown") == 1
    assert "987654321" not in json.dumps(answer)
    assert protocol.validate_result(answer, sdk_request) == answer


@pytest.mark.parametrize("login", [1, 1234, None])
def test_short_account_identifier_is_never_exposed_in_full(sdk_request, login):
    sdk = SDK(sdk_request)
    sdk.account.login = login
    assert synthetic(sdk_request, sdk)["account"]["login_masked"] is None


def test_disconnected_account_is_null_and_not_queried(sdk_request):
    sdk = SDK(sdk_request)
    sdk.info.connected = False
    answer = synthetic(sdk_request, sdk)
    assert answer["status"] == "SUCCEEDED"
    assert answer["account"]["status"] == "UNAVAILABLE_DISCONNECTED"
    assert all(v is None for k, v in answer["account"].items() if k != "status")
    assert "account_info" not in sdk.events


@pytest.mark.parametrize("failure", [False, RuntimeError("fixture-secret-must-not-leak")])
def test_false_or_raised_initialize_still_shutdown_once_and_sanitizes(sdk_request, failure):
    sdk = SDK(sdk_request)
    sdk.effects["initialize"] = failure if isinstance(failure, Exception) else lambda: False
    answer = synthetic(sdk_request, sdk)
    assert answer["reason_code"] == "LIVE_IPC_INITIALIZE_FAILED"
    assert answer["cleanup"] == {"status": "RETURNED", "reason_code": None}
    assert sdk.events == ["initialize", "shutdown"]
    assert "fixture-secret" not in json.dumps(answer)


def test_cleanup_failure_preserves_first_observation_error(sdk_request):
    sdk = SDK(sdk_request)
    sdk.effects["account_info"] = RuntimeError("private-diagnostic")
    sdk.effects["shutdown"] = RuntimeError("private-cleanup")
    answer = synthetic(sdk_request, sdk)
    assert answer["reason_code"] == "LIVE_CLEANUP_UNPROVEN"
    assert answer["primary_reason_code"] == "LIVE_OBSERVATION_UNAVAILABLE"
    assert answer["terminal"] is answer["account"] is None
    assert "private" not in json.dumps(answer)


def test_process_binding_rechecked_after_sdk_and_overrun_does_not_succeed(sdk_request):
    sdk = SDK(sdk_request)
    sdk.info.data_path = str(Path(sdk_request["binding"]["data_root"]) / "different")
    assert synthetic(sdk_request, sdk)["reason_code"] == "LIVE_BINDING_MISMATCH"
    now = [0.0]
    sdk = SDK(sdk_request)
    sdk.effects["shutdown"] = lambda: now.__setitem__(0, 11.0)
    answer = synthetic(sdk_request, sdk, clock=lambda: now[0])
    assert answer["reason_code"] == "LIVE_DEADLINE_EXCEEDED"
    assert answer["timing_ms"] == {"total": 11000.0, "expired": True}
    assert answer["account"] is None


@pytest.mark.parametrize("key,value", [("budget_ms", True), ("budget_ms", 10001),
    ("operation", "login"), ("nonce", []), ("qualification_sha256", "bad")])
def test_protocol_bad_request_denies_before_adapter_calls(sdk_request, key, value):
    sdk_request[key] = value
    events = []
    with pytest.raises(protocol.ProtocolError):
        observe_once(sdk_request, sdk_loader=lambda: events.append("sdk"), process_observer=lambda: events.append("probe"))
    assert events == []


@pytest.mark.parametrize("mutation", ["target", "owner", "binding", "nonce", "operation"])
def test_full_result_binding_and_request_digest_reject_tamper(sdk_request, mutation):
    answer = synthetic(sdk_request)
    changed = copy.deepcopy(sdk_request)
    if mutation == "target": changed[mutation]["terminal_generation"] = 2
    elif mutation == "owner": changed[mutation]["token"] = "other"
    elif mutation == "binding": changed[mutation]["alias"] = "OTHER"
    elif mutation == "nonce": changed[mutation] = "b" * 32
    else: changed[mutation] = "account"
    with pytest.raises(protocol.ProtocolError): protocol.validate_result(answer, changed)


def test_result_strict_fields_booleans_counts_time_and_no_unknown_data(sdk_request):
    original = synthetic(sdk_request)
    for section, field, value in [("account", "positions_count", True), ("account", "positions_count", -1),
                                   ("account", "positions_count", 1 << 63), ("terminal", "connected", None),
                                   ("account", "login_masked", "987654321"), ("timing_ms", "expired", True)]:
        changed = copy.deepcopy(original)
        changed[section][field] = value
        with pytest.raises(protocol.ProtocolError): protocol.validate_result(changed, sdk_request)
    changed = copy.deepcopy(original)
    changed["account"]["password"] = "secret"
    with pytest.raises(protocol.ProtocolError): protocol.validate_result(changed, sdk_request)


def test_bounded_json_duplicate_keys_invalid_utf8_and_nonfinite(tmp_path):
    path = tmp_path / "raw.json"
    for raw in [b'{"nonce":1,"nonce":2}', b'{"v":NaN}', b'\xff', b"x" * (protocol.MAX_BYTES + 1)]:
        path.write_bytes(raw)
        with pytest.raises(protocol.ProtocolError): protocol.read_bounded(path)


def test_fixture_signed_operator_approval_is_categorically_refused(tmp_path):
    key = Ed25519PrivateKey.generate()  # Disposable test key, never installation authority.
    body = {"schema": "fleet.sdk.operator-approval/1", "scope": "SYNTHETIC_SDK_ONLY"}
    envelope = {"approval": body, "signature": key.sign(DOMAIN + protocol.canonical(body)).hex()}
    path = tmp_path / "approval.json"
    protocol.write_bounded(path, envelope)
    with pytest.raises(QualificationError):
        validate_operator_approval(path, key.public_key().public_bytes_raw(), payload_manifest(), now_ms=1)
    envelope["approval"]["scope"] = "REAL_Q2_NO_START_STATE_ACCOUNT"
    path.unlink()
    protocol.write_bounded(path, envelope)
    with pytest.raises(QualificationError):
        validate_operator_approval(path, key.public_key().public_bytes_raw(), payload_manifest(), now_ms=1)


def test_public_factory_and_adapter_do_not_accept_caller_qualification_flags(sdk_request, tmp_path):
    with pytest.raises(QualificationError): QualifiedSdkInstallation({}, tmp_path, b"x" * 32)
    with pytest.raises(QualificationError): QualifiedReadAdapter(tmp_path, object(), {"qualified": True})
    with pytest.raises(QualificationError): observe_under_owned_lease(tmp_path, object(), sdk_request, {"qualified": True})
    answer = read_local(tmp_path, object(), "get_terminal_live_state", sdk_request["target"], {"qualified": True})
    assert answer["reason_code"] == "LIVE_ATTACH_ONLY_UNPROVEN"
    assert answer["ownership"]["status"] == "NOT_ACQUIRED"


class FixtureAuthority:
    """Finite test model; never creates a product qualification or native closure."""
    def __init__(self, sdk_request, events):
        self.sdk_request, self.events = sdk_request, events
        self.state = {"disposition": "CLOSED", "phase": "CLOSED", "worker": None}

    def arm(self, lease):
        self.events.append("arm")
        self.state = {**self.sdk_request["owner"], "disposition": "ACTIVE", "phase": "ARMED", "worker": None}
        return copy.deepcopy(self.state)

    def create_attempt(self, expected):
        self.events.append("create_attempt")
        self.state["phase"] = "CREATE_ATTEMPT"
        return copy.deepcopy(self.state)

    def bind_worker(self, expected, observed):
        self.events.append("bind")
        self.state.update(phase="BOUND", worker=observed.identity())
        return copy.deepcopy(self.state)

    def close_zero_attempt(self, expected):
        self.events.append("close_zero")
        assert self.state == expected and self.state["phase"] == "ARMED"
        self.state.update(disposition="CLOSED", phase="CLOSED")

    def close_owned_worker(self, expected, observed, *, descendant_verifier):
        self.events.append("close_owned")
        assert self.state == expected and observed.exited()
        assert descendant_verifier(observed) == "PREVENTED_BY_BOUNDARY"
        self.state.update(disposition="CLOSED", phase="CLOSED")

    def status(self): return copy.deepcopy(self.state)
    def load(self): return copy.deepcopy(self.state)


class FixtureObservation:
    def __init__(self, process): self.process = process
    def identity(self): return {"pid": 4444, "creation": "44", "image": str(Path(sys.executable).resolve())}
    def exited(self): return self.process.finished
    def close(self): pass


class FixtureProcess:
    def __init__(self, events, on_resume): self.events, self.finished, self.restrictions, self.on_resume = events, False, {"fixture": True}, on_resume
    def lifetime(self): return {"pid": 4444}
    def verify_observation(self, observed, **kwargs): self.events.append("verify")
    def allow_resume(self, authority, expected, observed):
        assert authority.load() == expected and expected["phase"] == "BOUND"
        self.events.append("allow_resume")
    def resume(self): self.events.append("resume"); self.on_resume(); self.finished = True
    def exited(self): return self.finished
    def wait(self, timeout): assert self.finished; return 0
    def identity(self): return FixtureObservation(self).identity()
    def terminate_exact(self, expected):
        assert expected == self.identity()
        self.events.append("terminate_exact")
        self.finished = True
    def close(self): self.events.append("handles_close")


def orchestration(tmp_path, sdk_request, *, stage=None, early_result=False):
    (tmp_path / "runs").mkdir(exist_ok=True)
    events, holder = [], {}
    authority = FixtureAuthority(sdk_request, events)
    installation = SimpleNamespace(operator_public_key=b"p" * 32,
        assert_request=lambda _: None, assert_current=lambda: None, assert_restrictions=lambda _: None)
    class Boundary:
        def __init__(self, root, approved): self.root = root; events.append("boundary")
        def spawn(self, request_path, output_path, key_path):
            events.append("spawn")
            holder["process"] = FixtureProcess(events, lambda: protocol.write_bounded(output_path, synthetic(sdk_request)))
            if early_result:
                protocol.write_bounded(output_path, synthetic(sdk_request))
            return holder["process"]
        def prove_closure(self, process, observed):
            assert process.finished and observed.exited()
            events.append("qualified_fixture_closure")
            return "PREVENTED_BY_BOUNDARY"
        def close(self): events.append("boundary_close")
    def fault(name):
        if name == stage:
            raise RuntimeError("fixture secret must not leak")
    answer = _run_owned(tmp_path, object(), sdk_request, installation, authority=authority,
        boundary_factory=Boundary, observer_factory=lambda _: FixtureObservation(holder["process"]),
        expected_evidence="SYNTHETIC_SDK_ONLY", fault=fault)
    return answer, authority, events


def test_controller_arm_create_bind_resume_qualified_close_order(tmp_path, sdk_request):
    answer, authority, events = orchestration(tmp_path, sdk_request)
    assert events.index("arm") < events.index("create_attempt") < events.index("spawn") < events.index("bind") < events.index("resume") < events.index("close_owned")
    assert answer["status"] == "SUCCEEDED" and authority.state["disposition"] == "CLOSED"
    assert answer["evidence"] == "SYNTHETIC_SDK_ONLY" and answer["qualified_closure"]
    assert "qualified_fixture_closure" in events


def test_controller_result_published_before_bind_is_refused(tmp_path, sdk_request):
    answer, authority, events = orchestration(tmp_path, sdk_request, early_result=True)
    assert "bind" not in events and "resume" not in events
    assert answer["status"] == "FAILED" and authority.state["disposition"] == "ACTIVE"
    assert "terminate_exact" in events and "close_owned" not in events


@pytest.mark.parametrize("stage,closed", [("ARMED", True), ("CREATE_ATTEMPT", False), ("SUSPENDED_CREATE", False), ("BOUND", True), ("BEFORE_RESUME", True), ("RESUMED", True)])
def test_controller_fault_windows_do_not_fabricate_zero_attempt_or_exit_proof(tmp_path, sdk_request, stage, closed):
    answer, authority, events = orchestration(tmp_path, sdk_request, stage=stage)
    assert (authority.state["disposition"] == "CLOSED") is closed
    assert ("close_zero" in events) is (stage == "ARMED")
    assert ("resume" in events) is (stage == "RESUMED") and answer["status"] == "FAILED"
    assert "fixture secret" not in json.dumps(answer)
    if not closed:
        assert answer["reason_code"] == "LIVE_CLEANUP_UNPROVEN"


def test_product_modules_never_import_proof_or_sdk_controller_import(tmp_path):
    package = Path(__file__).resolve().parents[2] / "app" / "vibemql5"
    for path in [*package.joinpath("fleet").glob("sdk_*.py"), package / "core" / "isolated_sdk.py"]:
        text = path.read_text()
        assert "tests.proofs" not in text and "from read_protocol" not in text
    assert "MetaTrader5" not in (package / "fleet" / "sdk_controller.py").read_text()


@pytest.mark.skipif(os.name != "nt", reason="Actual Win32 API construction requires Windows; no SDK")
def test_harmless_windows_api_and_structure_construction():
    from vibemql5.core.isolated_sdk import Windows, STARTUPINFOEX, SECURITY_CAPABILITIES
    windows = Windows()
    assert windows.kernel.CreateProcessW.argtypes
    assert STARTUPINFOEX().startup.cb == 0 and SECURITY_CAPABILITIES().count == 0


def test_runtime_acl_refuses_signed_worker_and_broad_write_grants():
    from vibemql5.fleet.sdk_qualification import validate_runtime_acl
    app, user = "S-1-15-2-1-2-3-4-5-6-7", "S-1-5-21-1"
    readonly = f"D:(A;;FA;;;{user})(A;;FA;;;SY)(A;;GRGX;;;{app})S:(ML;;NW;;;LW)"
    validate_runtime_acl(readonly, profile_sid=app, trusted_user_sid=user)
    for sddl in [readonly.replace("GRGX", "FA"), readonly.replace("S:", "(A;;GW;;;WD)S:"),
                 readonly.replace("GRGX", "0x1201bf"), "D:NO_ACCESS_CONTROL", readonly.replace("GRGX", "XY")]:
        with pytest.raises(QualificationError): validate_runtime_acl(sddl, profile_sid=app, trusted_user_sid=user)


def test_sdk_import_resolution_refuses_unpinned_module_before_code(tmp_path, monkeypatch):
    from vibemql5.fleet.sdk_worker import _load_approved_sdk, ReadFailure
    calls = []
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: SimpleNamespace(origin=str(tmp_path / "untrusted.py")))
    monkeypatch.setattr(importlib, "import_module", lambda name: calls.append(name))
    approved = SimpleNamespace(installation={"runtime_files": {}, "sdk_dll": str(tmp_path / "sdk.pyd")})
    with pytest.raises(ReadFailure, match="LIVE_ATTACH_ONLY_UNPROVEN"): _load_approved_sdk(approved)
    assert calls == []


def test_file_hash_rejects_allocation_cap_and_path_change(tmp_path):
    from vibemql5.fleet.sdk_qualification import file_hash
    path = tmp_path / "payload"
    path.write_bytes(b"12345")
    with pytest.raises(QualificationError): file_hash(path, max_bytes=4)
    assert file_hash(path, max_bytes=5) == __import__("hashlib").sha256(b"12345").hexdigest()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(path)
    except OSError:
        return  # Windows restricted symlink creation is not required by this case.
    with pytest.raises(QualificationError): file_hash(alias)


def test_routed_adapter_uses_remaining_absolute_deadline_once(sdk_request, monkeypatch):
    from vibemql5.fleet import sdk_controller as controller
    # Construct no installation authority: only test adapter budgeting on a private
    # object before the real read_local exact-type qualification gate.
    adapter = object.__new__(controller.QualifiedReadAdapter)
    adapter.root, adapter.concurrency, adapter.installation = Path("."), object(), object()
    adapter._select = lambda target: (target, adapter.installation)
    monkeypatch.setattr(controller.time, "time", lambda: 100.0)
    calls = []
    monkeypatch.setattr(controller, "_read_bound", lambda *args, **kwargs: calls.append(kwargs["budget_ms"]) or {})
    from vibemql5.fleet import transport
    class FixtureAdmission:
        def claim(self, command): pass
    monkeypatch.setattr(transport, "NodeReadAdmission", FixtureAdmission)
    admission = FixtureAdmission()
    command = {"operation": "get_terminal_live_state", "target": sdk_request["target"], "deadline_ms": 100750}
    adapter.read(command, admission)
    assert calls == [750]
    command["deadline_ms"] = 120000
    adapter.read(command, admission)
    assert calls == [750, 10000]
    command["deadline_ms"] = 100000
    assert adapter.read(command, admission)["reason_code"] == "LIVE_DEADLINE_EXCEEDED"
    assert calls == [750, 10000]


@pytest.mark.parametrize("bad", [True, {}, {"profile_sha256": "a" * 64, "reservation_id": "scope_" + "1" * 32, "token": "2" * 32}])
def test_request_scope_reference_is_exact_and_bound_to_owner(sdk_request, bad):
    sdk_request["scope"] = bad
    with pytest.raises(protocol.ProtocolError): protocol.validate_request(sdk_request)


def _scope_fixture_profile(root):
    """Harmless durable scope fixture; no signed installed marker or native effect."""
    from vibemql5.fleet.resources import physical_resources
    from vibemql5.fleet.scoped_resources import CONFLICT_MATRIX
    terminals = []
    for digit in ("1", "2"):
        directory = root / digit
        directory.mkdir()
        resources = {}
        for name in ("executable", "data_root", "include_root", "agent_root"):
            path = directory / name
            if name == "executable": path.write_bytes(b"inert-SDK-resource-fixture")
            else: path.mkdir()
            resources[name] = str(path.resolve())
        terminals.append({"terminal_id": "term_" + digit * 32, "terminal_generation": 1, "resources": resources,
                          "physical_identities": physical_resources(resources)})
    return {"schema": "fleet.capacity-profile/1", "device_id": "dev_" + "a" * 32,
        "install_epoch": "b" * 32, "capacity": 2, "candidate_sha256": "c" * 64, "runtime_sha256": "d" * 64,
        "source_manifest": [], "terminals": terminals, "load_receipt": None, "closure_receipt": None,
        "max_records": 20, "lock_wait_ms": 1000, "conflict_matrix": CONFLICT_MATRIX}


@pytest.mark.parametrize("stage,closed", [("ARMED", True), ("CREATE_ATTEMPT", False)])
def test_controller_uses_durable_scoped_lease_and_retains_uncertain_creation(tmp_path, sdk_request, stage, closed):
    from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator
    from vibemql5.fleet.job_journal import JournalError
    from vibemql5.fleet import sdk_controller as controller
    profile = _scope_fixture_profile(tmp_path)
    coordinator = ScopedResourceCoordinator._for_fixture(tmp_path, profile, initialize=True)
    (tmp_path / "runs").mkdir()
    events = []
    installation = SimpleNamespace(operator_public_key=b"p" * 32,
        assert_request=lambda _: None, assert_current=lambda: None, assert_restrictions=lambda _: None)
    with coordinator.execution("scope-sdk", kind="ipc", terminal_id="term_" + "1" * 32,
            terminal_generation=1, wait_ms=0) as lease:
        state = lease.load()
        sdk_request["scope"] = lease.reference
        sdk_request["owner"] = controller._owner(state, lease)
        sdk_request["owner"]["generation"] += 1
        def fault(name):
            if name == stage: raise RuntimeError("scoped fixture failure")
        class Boundary:
            def __init__(self, *_): events.append("boundary")
            def close(self): events.append("boundary_close")
        answer = _run_owned(tmp_path, lease, sdk_request, installation, authority=lease.authority,
            boundary_factory=Boundary, expected_evidence="SYNTHETIC_SDK_ONLY", fault=fault)
        assert answer["status"] == "FAILED"
        assert answer["qualified_closure"] is closed
        assert answer["ownership"]["status"] == ("CLOSED" if closed else "ACTIVE")
        reference = lease.reference
    reopened = ScopedResourceCoordinator._for_fixture(tmp_path, profile)
    assert reopened.read_scope(reference)["status"] == ("RELEASED" if closed else "UNKNOWN")
    assert not (tmp_path / "state" / "fleet" / "scoped-install.json").exists()
    if not closed:
        assert answer["reason_code"] == "LIVE_CLEANUP_UNPROVEN"
        with pytest.raises(JournalError, match="SCOPED_LEASE_UNAVAILABLE"):
            with reopened.execution("successor-sdk", kind="ipc", terminal_id="term_" + "2" * 32,
                    terminal_generation=1, wait_ms=0): pass


def test_unapproved_scoped_marker_cannot_change_sdk_namespace(tmp_path):
    # This deliberately incomplete private object exercises only denial paths;
    # it never passes the real signed installation factory or performs a read.
    installation = object.__new__(QualifiedSdkInstallation)
    fixed = {"authority_root": str(tmp_path), "scope_authority": None}
    installation._approval = json.dumps({"installation": fixed})
    assert installation.scope_coordinator() is None
    marker = tmp_path / "state" / "fleet" / "scoped-install.json"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"malformed fixture")
    with pytest.raises(QualificationError): installation.scope_coordinator()
    fixed["scope_authority"] = {"profile_sha256": "a" * 64, "owner_public_key": "b" * 64,
                                "candidate_sha256": "c" * 64, "runtime_sha256": "d" * 64}
    installation._approval = json.dumps({"installation": fixed})
    with pytest.raises(QualificationError): installation.scope_coordinator()
    marker.unlink()
    with pytest.raises(QualificationError): installation.scope_coordinator()


@pytest.mark.parametrize("release_error", [False, True])
@pytest.mark.parametrize("failure_phase", ["worker", "admission"])
def test_read_receipt_preserves_worker_first_error_and_actual_lease_release(tmp_path, monkeypatch, release_error, failure_phase):
    """Instrument private receipt flow; no qualification, SDK or process is created."""
    from ownership_fixture import install_closed
    from test_tip055a_runtime_forensics_identity import make_terminal, ref, write_config
    from vibemql5.core.concurrency import ConcurrencyManager
    from vibemql5.fleet.identity import IdentityRegistry
    from vibemql5.fleet import sdk_controller as controller
    terminals = [make_terminal(tmp_path)]
    write_config(tmp_path, terminals)
    registry = IdentityRegistry(tmp_path).bootstrap(terminals)
    authority = install_closed(tmp_path)
    actual_manager = ConcurrencyManager(tmp_path)
    class FixtureInstallation:
        sha256 = "c" * 64
        installation = {"authority_root": str(tmp_path)}
        def assert_current(self): pass
        def scope_coordinator(self): return None
    monkeypatch.setattr(controller, "QualifiedSdkInstallation", FixtureInstallation)
    image = registry["terminals"][0]["binding"]["terminal_canonical_path"]
    process = SimpleNamespace(identity=lambda: {"pid": 1234, "creation": "123456789", "image": image},
                              exited=lambda: False, close=lambda: None)
    monkeypatch.setattr(controller, "probe_terminal", lambda *_args, **_kwargs: process)
    def failed_worker(_root, _lease, request, *_args, **_kwargs):
        if failure_phase == "admission":
            answer = synthetic(request)
            answer.update(qualified_closure=True, ownership={"status": "CLOSED"}, sdk_attempted=True)
            return answer
        return {"status": "FAILED", "reason_code": "LIVE_CLEANUP_UNPROVEN",
            "primary_reason_code": "LIVE_IPC_INITIALIZE_FAILED", "qualified_closure": True,
            "ownership": {"status": "CLOSED"}}
    monkeypatch.setattr(controller, "observe_under_owned_lease", failed_worker)
    class FixtureAdmission:
        checks = 0
        def assert_current(self, _command):
            self.checks += 1
            if failure_phase == "admission" and self.checks == 2:
                from vibemql5.fleet.wire import WireError
                raise WireError("READ_ADMISSION_CLOSED")
    class Manager:
        @contextmanager
        def native_execution(self, *args, **kwargs):
            with actual_manager.native_execution(*args, **kwargs) as lease: yield lease
            if release_error: raise RuntimeError("private-release-diagnostic")
    answer = controller._read_bound(tmp_path, Manager(), "get_terminal_live_state", ref(registry), FixtureInstallation(),
        node_admission=FixtureAdmission(), command={"synthetic_fixture_only": True})
    assert answer["status"] == "FAILED"
    first = "LIVE_IPC_INITIALIZE_FAILED" if failure_phase == "worker" else "READ_ADMISSION_CLOSED"
    assert answer["reason_code"] == ("LIVE_CLEANUP_UNPROVEN" if release_error or failure_phase == "worker" else first)
    assert answer["primary_reason_code"] == (first if release_error or failure_phase == "worker" else None)
    assert answer["ownership"] == {"status": "CLOSED"}
    assert answer["cleanup"]["status"] == ("UNPROVEN" if release_error else "PROVEN")
    assert all(answer[k] is None for k in ("terminal", "account", "source", "observed_binding", "observed_at_utc"))
    assert answer["timing_ms"]["release"] >= 0
    assert authority.load()["disposition"] == "CLOSED"
    assert not (tmp_path / "runs" / ".active.lock").exists()
    assert "private-release-diagnostic" not in json.dumps(answer)


def _selection_only_installation(root, target, *, session=1):
    """Read-only catalog metadata; incomplete object cannot activate the real factory."""
    installation = object.__new__(QualifiedSdkInstallation)
    fixed = {"target": target, "executable": str(root / (target["terminal_id"] + ".exe")),
        "authority_root": str(root), "platform": "Windows", "os_build": "22631", "session_id": session,
        "python": str(root / "python.exe"), "python_dll": str(root / "python312.dll"),
        "sdk_wheel": str(root / "sdk.whl"), "sdk_dll": str(root / "sdk.pyd"), "worker": str(root / "sdk_worker.py"),
        "profile_name": "vibemql5.sdk." + "f" * 32, "profile_sid": "S-1-15-2-1-2-3-4-5-6-7",
        "restrictions": {}, "scope_authority": None, "runtime_files": {str(root / "sdk.pyd"): "a" * 64}}
    installation._approval = json.dumps({"installation": fixed})
    return installation


def test_one_node_adapter_selects_two_exact_qualified_catalog_bindings_without_fallback(tmp_path, sdk_request, monkeypatch):
    from vibemql5.fleet import sdk_controller as controller, transport
    first = copy.deepcopy(sdk_request["target"])
    second = {**first, "terminal_id": "term_" + "d" * 32}
    a, b = (_selection_only_installation(tmp_path, target) for target in (first, second))
    adapter = QualifiedReadAdapter(tmp_path, object(), (a, b))
    attempts = []
    monkeypatch.setattr(controller, "_read_bound", lambda _root, _manager, _op, target, installed, **kwargs:
                        attempts.append((copy.deepcopy(target), installed)) or {})
    class FixtureAdmission:
        def claim(self, _command): pass
    monkeypatch.setattr(transport, "NodeReadAdmission", FixtureAdmission)
    for target, expected in ((first, a), (second, b)):
        routed = {**target, "route_generation": 3}
        adapter.read({"operation": "get_terminal_live_state", "target": routed,
                      "deadline_ms": int(__import__("time").time() * 1000) + 10000}, FixtureAdmission())
        assert attempts[-1] == (routed, expected)
    unknown = {**second, "terminal_generation": 2, "route_generation": 3}
    answer = adapter.read({"operation": "get_terminal_live_state", "target": unknown,
        "deadline_ms": int(__import__("time").time() * 1000) + 10000}, FixtureAdmission())
    assert answer["reason_code"] == "SDK_TARGET_UNQUALIFIED" and answer["ownership"]["status"] == "NOT_ACQUIRED"
    assert len(attempts) == 2 and answer["requested_target"] == unknown
    assert adapter.installation is None
    assert QualifiedReadAdapter(tmp_path, object(), a).installation is a
    # The metadata objects have no approval file/key/source evidence and never
    # pass actual qualification, even though catalog selection is executable.
    with pytest.raises(Exception): a.assert_current()


@pytest.mark.parametrize("mutation", ["duplicate", "session", "device", "runtime", "too_many"])
def test_multi_target_catalog_rejects_duplicate_or_different_authority_family(tmp_path, sdk_request, mutation):
    first = copy.deepcopy(sdk_request["target"])
    second = {**first, "terminal_id": "term_" + "d" * 32}
    a, b = (_selection_only_installation(tmp_path, target) for target in (first, second))
    candidates = (a, b)
    fixed = json.loads(b._approval)
    if mutation == "duplicate": candidates = (a, a)
    elif mutation == "too_many": candidates = (a,) * 17
    elif mutation == "session": fixed["installation"]["session_id"] = 2
    elif mutation == "device": fixed["installation"]["target"]["device_id"] = "dev_" + "f" * 32
    elif mutation == "runtime": fixed["installation"]["runtime_files"] = {str(tmp_path / "different.pyd"): "a" * 64}
    b._approval = json.dumps(fixed)
    with pytest.raises(QualificationError): QualifiedReadAdapter(tmp_path, object(), candidates)


def test_evidence_bound_can_hold_source_acl_closure_without_widening_worker_messages(tmp_path):
    value = {"source_evidence_fixture": "x" * (protocol.MAX_BYTES + 1)}
    path = tmp_path / "evidence.json"
    protocol.write_bounded(path, value, max_bytes=protocol.MAX_EVIDENCE_BYTES)
    with pytest.raises(protocol.ProtocolError): protocol.read_bounded(path)
    assert protocol.read_bounded(path, max_bytes=protocol.MAX_EVIDENCE_BYTES) == value
    with pytest.raises(protocol.ProtocolError): protocol.read_bounded(path, max_bytes=True)


def test_scoped_worker_bound_snapshot_uses_only_read_only_files_and_memory_sqlite(tmp_path, monkeypatch):
    """Signed protocol claims exercise snapshot I/O, never physical SDK qualification."""
    from vibemql5.fleet import scoped_resources as scoped
    from vibemql5.core.native_ownership import current_identity
    profile = _scope_fixture_profile(tmp_path)
    coordinator = scoped.ScopedResourceCoordinator._for_fixture(tmp_path, profile, initialize=True)
    identity = current_identity()
    with coordinator.execution("read-only-sdk-snapshot", kind="ipc", terminal_id="term_" + "1" * 32,
            terminal_generation=1, wait_ms=0) as lease:
        attempted = lease.create_attempt(lease.arm())
        with coordinator.transaction() as db:
            bound = {**attempted, "phase": "BOUND", "worker": identity}
            coordinator._save(db, bound)
        marker = tmp_path / "state" / "fleet" / "scoped-install.json"
        protocol.write_bounded(marker, {"body": profile, "signature": "0" * 128})
        before = coordinator.path.read_bytes()
        connect = scoped.sqlite3.connect
        connections = []
        with monkeypatch.context() as patch:
            patch.setattr(scoped, "assert_installed_sdk_scope_profile", lambda *_args, **_kwargs: profile)
            def memory_only(path, *args, **kwargs):
                connections.append(path)
                assert path == ":memory:"
                return connect(path, *args, **kwargs)
            patch.setattr(scoped.sqlite3, "connect", memory_only)
            patch.setattr(scoped, "_exclusive_file_lock", lambda *_args, **_kwargs:
                          (_ for _ in ()).throw(AssertionError("worker must not acquire writable control guard")))
            with pytest.raises(scoped.JournalError, match="SCOPED_STORE_INVALID"):
                scoped.observe_bound_sdk_scope(tmp_path, lease.reference, identity, identity,
                    trusted_owner_public_key="e" * 64, expected_profile_sha256=coordinator.profile_sha256,
                    expected_candidate_sha256=profile["candidate_sha256"], expected_runtime_sha256=profile["runtime_sha256"])
        assert coordinator.path.read_bytes() == before and connections == [":memory:"]
        # Explicit disposable signed-profile *claim* data. The actual installation
        # verifier remains denied for this fixture; only its snapshot I/O seam is
        # substituted below. No native/SDK worker or physical profile is enabled.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        claim_key = Ed25519PrivateKey.generate()
        marker.unlink()
        protocol.write_bounded(marker, {"body": profile,
            "signature": claim_key.sign(scoped.DOMAIN + scoped.canonical(profile)).hex()})
        with coordinator.transaction() as db:
            bound = {**bound, "evidence": "SIGNED_PHYSICAL_CAPACITY_PROFILE"}
            coordinator._save(db, bound)
        coordinator.evidence = "SIGNED_PHYSICAL_CAPACITY_PROFILE"
        before = coordinator.path.read_bytes()
        connections.clear()
        with monkeypatch.context() as patch:
            patch.setattr(scoped, "assert_installed_sdk_scope_profile", lambda *_args, **_kwargs: profile)
            patch.setattr(scoped.sqlite3, "connect", memory_only)
            patch.setattr(scoped, "_exclusive_file_lock", lambda *_args, **_kwargs:
                          (_ for _ in ()).throw(AssertionError("worker must not acquire writable control guard")))
            observed = scoped.observe_bound_sdk_scope(tmp_path, lease.reference, identity, identity,
                trusted_owner_public_key="e" * 64, expected_profile_sha256=coordinator.profile_sha256,
                expected_candidate_sha256=profile["candidate_sha256"], expected_runtime_sha256=profile["runtime_sha256"])
        assert observed == bound and connections == [":memory:"]
        assert coordinator.path.read_bytes() == before
        marker.unlink()  # Remove only this deliberately unsigned disposable fixture.


def test_sdk_hash_rejects_or_prevents_actual_path_replacement(tmp_path, monkeypatch):
    """Real temporary filesystem race; no SDK/qualification installation."""
    import os
    import hashlib
    from vibemql5.fleet import scoped_resources as scoped
    from vibemql5.fleet.sdk_qualification import file_hash
    path, replacement = tmp_path / 'runtime.bin', tmp_path / 'replacement.bin'
    path.write_bytes(b'original'); replacement.write_bytes(b'changed!')
    original_check, prevented = scoped.assert_retained_path, []
    def race(value, fd, expected):
        try: replacement.replace(path)
        except OSError:
            assert os.name == 'nt'  # The retained Windows read denies delete sharing.
            prevented.append(True)
        original_check(value, fd, expected)
    monkeypatch.setattr(scoped, 'assert_retained_path', race)
    if os.name == 'nt':
        assert file_hash(path) == hashlib.sha256(b'original').hexdigest()
        assert prevented and path.read_bytes() == b'original'
    else:
        with pytest.raises(QualificationError): file_hash(path)
        assert path.read_bytes() == b'changed!'


def test_sdk_hash_cumulative_cap_rejects_or_prevents_actual_growth(tmp_path, monkeypatch):
    """Growth happens after the first read; initial size alone cannot pass it."""
    import os
    import hashlib
    from vibemql5.fleet.sdk_qualification import file_hash
    path = tmp_path / 'runtime.bin'; path.write_bytes(b'12345')
    original_fdopen, prevented = os.fdopen, []
    class GrowingStream:
        def __init__(self, stream): self.stream, self.first = stream, True
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def fileno(self): return self.stream.fileno()
        def read(self, maximum):
            value = self.stream.read(maximum)
            if self.first:
                self.first = False
                try:
                    with path.open('ab') as writer: writer.write(b'6')
                except OSError:
                    assert os.name == 'nt'  # FILE_SHARE_READ refuses this writer.
                    prevented.append(True)
            return value
    monkeypatch.setattr(os, 'fdopen', lambda *args, **kwargs: GrowingStream(original_fdopen(*args, **kwargs)))
    if os.name == 'nt':
        assert file_hash(path, max_bytes=5) == hashlib.sha256(b'12345').hexdigest()
        assert prevented and path.read_bytes() == b'12345'
    else:
        with pytest.raises(QualificationError): file_hash(path, max_bytes=5)
        assert path.read_bytes() == b'123456'
