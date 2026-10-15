"""C1 local inventory attribution and denial; no SDK or live qualification evidence."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ownership_fixture import install_closed
from test_tip055a_runtime_forensics_identity import make_terminal, ref, write_config
from vibemql5.adapters.mcp import create_server
from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES
from vibemql5.core.concurrency import ConcurrencyManager, acquire_native_execution
from vibemql5.core.facade import ToolFacade
from vibemql5.core.inventory import TerminalInventory
from vibemql5.core.native_ownership import OwnershipAuthority, OwnershipBlocked
from vibemql5.fleet.identity import IdentityRegistry
from vibemql5.fleet import reads

OPERATIONS = ("get_terminal_live_state", "get_account_snapshot")
SECRET = "C1_CALLER_SECRET_MUST_NOT_APPEAR"
ENVELOPE = {"schema", "operation", "status", "reason_code", "primary_reason_code", "requested_target",
    "resolved_target", "identity", "observed_binding", "source", "observed_at_utc", "terminal", "account",
    "phase", "budget", "timing_ms", "cleanup", "ownership"}
# Actual generated MCP 2.1.1 schemas at parent #63 before the selected additive edits.
UNCHANGED_SCHEMAS_SHA256 = "16ceef873678e7d7598874c6e612393e23de35c934f18ab6a31b09ad15bd7541"


class Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class SyntheticAdmission:
    """Finite fault adapter for domain timing; real common-gate tests are separate."""
    def __init__(self, clock, *, acquire_error=None, release_error=None, acquire_seconds=0, release_seconds=0):
        self.clock, self.acquire_error, self.release_error = clock, acquire_error, release_error
        self.acquire_seconds, self.release_seconds = acquire_seconds, release_seconds
        self.active, self.events, self.arguments = False, [], []

    @contextmanager
    def native_execution(self, operation_id, **kwargs):
        self.arguments.append((operation_id, kwargs))
        self.events.append("acquire")
        self.clock.advance(self.acquire_seconds)
        if self.acquire_error:
            raise self.acquire_error
        self.active = True
        try:
            yield SimpleNamespace()
        finally:
            self.events.append("release")
            self.clock.advance(self.release_seconds)
            self.active = False
            if self.release_error:
                raise self.release_error


@pytest.fixture
def fixture(tmp_path):
    terminals = [make_terminal(tmp_path), make_terminal(tmp_path, "MT5-3", "b")]
    write_config(tmp_path, terminals)
    record = IdentityRegistry(tmp_path).bootstrap(terminals)
    authority = install_closed(tmp_path)
    return SimpleNamespace(root=tmp_path, terminals=terminals, record=record, target=ref(record),
                           authority=authority, manager=ConcurrencyManager(tmp_path))


@pytest.fixture(autouse=True)
def no_live_effects(monkeypatch):
    attempts = []
    def forbidden(*_args, **_kwargs):
        attempts.append("target process/SDK/launch")
        raise AssertionError("C1 must not perform process discovery, live SDK or launch effects")
    monkeypatch.setattr(TerminalInventory, "running_terminal_paths", forbidden)
    monkeypatch.setattr(TerminalInventory, "is_running", forbidden)
    monkeypatch.setattr(subprocess.Popen, "__init__", forbidden)
    import vibemql5.core.live_terminal as live_module
    monkeypatch.setattr(live_module.LiveTerminal, "state", forbidden)
    class ForbiddenImport:
        def find_spec(self, fullname, *_args):
            if fullname == "MetaTrader5" or "tip057rb1" in fullname or "tip057rq" in fullname:
                attempts.append(fullname)
                raise AssertionError("C1 must not import SDK/research proof modules")
    guard = ForbiddenImport()
    sys.meta_path.insert(0, guard)
    yield
    sys.meta_path.remove(guard)
    assert attempts == [], "A caught error must not hide a forbidden native attempt"


def read(fixture, *, target=None, operation=OPERATIONS[0], manager=None, clock=None):
    kwargs = {} if clock is None else {"clock": clock}
    return reads.targeted_read(fixture.root, manager or fixture.manager, operation,
        fixture.target if target is None else target, **kwargs)


def assert_failure(value, operation, code, *, ownership="RELEASED", primary=None):
    assert set(value) == ENVELOPE
    assert value["schema"] == "fleet.read/1"
    assert value["operation"] == operation
    assert value["status"] == "FAILED"
    assert value["reason_code"] == code
    assert value["primary_reason_code"] == primary
    assert value["ownership"] == {"status": ownership}
    assert value["cleanup"]["status"] == "NOT_ATTEMPTED"
    for field in ("observed_binding", "source", "observed_at_utc", "terminal", "account"):
        assert value[field] is None
    assert value["phase"] in {"validation", "lease", "process", "initialize", "observe", "revalidate",
                              "cleanup", "release", "complete"}
    assert value["budget"] == {"mode": "SOFT_SUCCESS", "observation_ms": 10000, "lease_wait_ms": 2000,
        "initialize_max_ms": 2000, "process_probe_max_ms": 2000, "expired": value["budget"]["expired"]}
    assert type(value["budget"]["expired"]) is bool
    assert set(value["timing_ms"]) == {"total", "lease", "process", "initialize", "observe", "revalidate", "cleanup", "release"}
    assert value["timing_ms"]["total"] >= 0
    assert all(value["timing_ms"][field] is None for field in ("process", "initialize", "observe", "revalidate", "cleanup"))
    assert SECRET not in json.dumps(value)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_resolved_target_is_inventory_attribution_only_and_authority_unchanged(fixture, operation):
    before = {path: path.read_bytes() for path in (fixture.authority.path, fixture.authority.marker_path,
              IdentityRegistry(fixture.root).path, fixture.root / "config" / "terminals.json")}
    value = read(fixture, operation=operation)
    assert_failure(value, operation, "LIVE_ATTACH_ONLY_UNPROVEN")
    assert value["requested_target"] == value["resolved_target"] == fixture.target
    binding = fixture.record["terminals"][0]["binding"]
    assert value["identity"] == {"identity_source": "LOCAL_PERSISTED_REGISTRY", "identity_revision": 1,
        "alias": "MT5-2", "binding": {"executable": binding["terminal_canonical_path"],
                                        "data_root": binding["data_canonical_path"]}}
    assert value["cleanup"] == {"status": "NOT_ATTEMPTED", "reason_code": None}
    assert value["timing_ms"]["lease"] >= 0
    assert value["timing_ms"]["release"] >= 0
    assert not (fixture.root / "runs" / ".active.lock").exists()
    assert before == {path: path.read_bytes() for path in before}
    audit = [json.loads(line) for line in fixture.manager.audit_path.read_text().splitlines()]
    assert [row["event"] for row in audit] == ["NATIVE_WAIT", "NATIVE_ACQUIRED", "NATIVE_COMPLETED"]


@pytest.mark.parametrize("mutation", [
    ("schema", "fleet.target/2"), ("schema", []), ("device_id", "dev_" + "a" * 31),
    ("device_id", "dev_" + "a" * 32 + "\n"), ("terminal_id", "term_" + "A" * 32),
    ("terminal_id", "term_" + "b" * 40000), ("terminal_id", []),
    ("terminal_generation", True), ("terminal_generation", 0), ("terminal_generation", -1),
    ("terminal_generation", "1"), ("terminal_generation", 1.0),
    ("route_generation", True), ("route_generation", 0), ("route_generation", "1"),
    ("route_generation", []), ("password", SECRET),
])
def test_malformed_target_is_not_echoed_or_admitted(fixture, mutation):
    target = {**fixture.target, mutation[0]: mutation[1]}
    clock = Clock()
    manager = SyntheticAdmission(clock)
    value = read(fixture, target=target, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], "TARGET_MISMATCH", ownership="NOT_ACQUIRED")
    assert value["requested_target"] is value["resolved_target"] is value["identity"] is None
    assert value["timing_ms"]["lease"] is value["timing_ms"]["release"] is None
    assert manager.events == []


@pytest.mark.parametrize("target", [{}, {"schema": "fleet.target/1"}, [], SECRET, 123])
def test_domain_scalar_or_missing_fields_remain_sanitized(fixture, target):
    value = read(fixture, target=target)
    assert_failure(value, OPERATIONS[0], "TARGET_MISMATCH", ownership="NOT_ACQUIRED")
    assert value["requested_target"] is None


def test_route_generation_is_validated_before_projection_and_denied_before_lease(fixture):
    clock = Clock()
    manager = SyntheticAdmission(clock)
    target = {**fixture.target, "route_generation": 2}
    value = read(fixture, target=target, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], "ROUTED_NATIVE_NOT_ENABLED", ownership="NOT_ACQUIRED")
    assert value["requested_target"] == target
    assert value["resolved_target"] is None
    assert manager.events == []
    local = read(fixture, target={**fixture.target, "route_generation": None})
    assert_failure(local, OPERATIONS[0], "LIVE_ATTACH_ONLY_UNPROVEN")
    assert local["requested_target"].get("route_generation") is None


@pytest.mark.parametrize("field,value,code", [
    ("device_id", "dev_" + "0" * 32, "TARGET_UNKNOWN"),
    ("terminal_id", "term_" + "0" * 32, "TARGET_UNKNOWN"),
    ("terminal_generation", 2, "TARGET_MISMATCH"),
])
def test_unknown_remote_or_stale_targets_never_fallback(fixture, field, value, code):
    receipt = read(fixture, target={**fixture.target, field: value})
    assert_failure(receipt, OPERATIONS[0], code)
    assert receipt["resolved_target"] is None


@pytest.mark.parametrize("fault,code", [
    ("unenrolled", "IDENTITY_UNENROLLED"), ("corrupt", "IDENTITY_INVALID"),
    ("missing_config", "IDENTITY_INVALID"), ("corrupt_config", "IDENTITY_INVALID"),
    ("disabled_config", "TARGET_MISMATCH"), ("disabled_registry", "TARGET_MISMATCH"),
    ("unqualified", "TARGET_MISMATCH"), ("changed_binding", "TARGET_MISMATCH"),
    ("duplicate_alias", "RESOURCE_CONFLICT"), ("shared_data", "RESOURCE_CONFLICT"),
    ("invalid_enabled_string", "IDENTITY_INVALID"), ("invalid_enabled_number", "IDENTITY_INVALID"),
])
def test_fresh_config_and_registry_faults_beat_cached_facade(fixture, monkeypatch, fault, code):
    facade = ToolFacade(fixture.root)  # Construct before all mutations.
    registry = IdentityRegistry(fixture.root)
    terminals = fixture.terminals
    if fault == "unenrolled": registry.path.unlink()
    elif fault == "corrupt": registry.path.write_text('{"password":"' + SECRET + '"')
    elif fault == "missing_config": (fixture.root / "config" / "terminals.json").unlink()
    elif fault == "corrupt_config": (fixture.root / "config" / "terminals.json").write_text(SECRET)
    elif fault == "disabled_registry":
        registry.update(fixture.target["terminal_id"], expected_revision=1, operation_id="fixture-disable", enabled=False)
    elif fault == "disabled_config": terminals = [replace(terminals[0], enabled=False), terminals[1]]
    elif fault == "unqualified":
        Path(terminals[0].terminal_path).unlink()
    elif fault == "changed_binding": terminals = [make_terminal(fixture.root, name="replacement"), terminals[1]]
    elif fault == "duplicate_alias": terminals = [*terminals, replace(terminals[1], alias="mt5-2")]
    elif fault == "shared_data": terminals = [terminals[0], replace(terminals[1], data_root=terminals[0].data_root)]
    elif fault.startswith("invalid_enabled"):
        rows = [item.to_dict() for item in terminals]
        rows[0]["enabled"] = "false" if fault.endswith("string") else 0
        (fixture.root / "config" / "terminals.json").write_text(json.dumps({"terminals": rows}))
    if fault not in {"unenrolled", "corrupt", "missing_config", "corrupt_config", "disabled_registry", "unqualified"} and not fault.startswith("invalid_enabled"):
        write_config(fixture.root, terminals)
    def no_legacy(*_args): raise AssertionError("Explicit target must never use cached/legacy observation")
    monkeypatch.setattr(facade, "_observe_live", no_legacy)
    value = facade.get_terminal_live_state(fixture.target)
    assert_failure(value, OPERATIONS[0], code)
    assert value["resolved_target"] is None


def test_fresh_registry_revision_and_generation_are_resolved_without_fixed_fallback(fixture):
    facade = ToolFacade(fixture.root)
    registry = IdentityRegistry(fixture.root)
    replacement = make_terminal(fixture.root, alias="FRESH-ALIAS", name="replacement")
    registry.update(fixture.target["terminal_id"], expected_revision=1, operation_id="fixture-rebind",
        alias=replacement.alias, terminal_path=replacement.terminal_path, data_root=replacement.data_root)
    write_config(fixture.root, [replacement, fixture.terminals[1]])
    assert_failure(facade.get_terminal_live_state(fixture.target), OPERATIONS[0], "TARGET_MISMATCH")
    current = ref(registry.load())
    assert current["terminal_generation"] == 2
    value = facade.get_account_snapshot(current)
    assert_failure(value, OPERATIONS[1], "LIVE_ATTACH_ONLY_UNPROVEN")
    assert value["resolved_target"] == current
    assert value["identity"]["alias"] == "FRESH-ALIAS"
    assert value["identity"]["identity_revision"] == 2
    assert value["identity"]["binding"]["executable"] == registry.load()["terminals"][0]["binding"]["terminal_canonical_path"]
    second = facade.get_account_snapshot(ref(registry.load(), 1))
    assert_failure(second, OPERATIONS[1], "LIVE_ATTACH_ONLY_UNPROVEN")
    assert second["identity"]["alias"] == "MT5-3"
    assert second["resolved_target"]["terminal_id"] != value["resolved_target"]["terminal_id"]


def test_registry_revision_drift_during_resolution_fails_without_observation(fixture, monkeypatch):
    original = IdentityRegistry.load
    calls = []
    def load(self):
        current = original(self)
        calls.append(current["identity_revision"])
        if len(calls) == 1:
            changed = copy.deepcopy(current)
            changed["identity_revision"] += 1
            self.path.write_text(json.dumps(changed))
        return current
    monkeypatch.setattr(IdentityRegistry, "load", load)
    value = read(fixture)
    assert_failure(value, OPERATIONS[0], "TARGET_MISMATCH")
    assert calls == [1, 2]
    assert value["identity"] is value["resolved_target"] is None
    assert original(IdentityRegistry(fixture.root))["identity_revision"] == 2


def test_config_and_registry_resolution_execute_only_under_admission(fixture, monkeypatch):
    clock = Clock()
    manager = SyntheticAdmission(clock)
    original_load = IdentityRegistry.load
    original_inventory = reads.TerminalInventory
    checked = []
    def load(self):
        assert manager.active
        checked.append("registry")
        return original_load(self)
    def inventory(root):
        assert manager.active
        checked.append("config")
        return original_inventory(root)
    monkeypatch.setattr(IdentityRegistry, "load", load)
    monkeypatch.setattr(reads, "TerminalInventory", inventory)
    value = read(fixture, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], "LIVE_ATTACH_ONLY_UNPROVEN")
    assert checked[0] == "config" and "registry" in checked
    assert manager.events == ["acquire", "release"]
    assert 0 < manager.arguments[0][1]["wait_seconds"] <= 2


@pytest.mark.parametrize("fault", ["missing_marker", "corrupt_authority", "active"])
def test_real_shared_ownership_denies_without_mutating_authority(fixture, fault):
    if fault == "missing_marker": fixture.authority.marker_path.unlink()
    elif fault == "corrupt_authority": fixture.authority.path.write_text(SECRET)
    else:
        lease = acquire_native_execution(fixture.root, "C1-ACTIVE-FIXTURE", kind="fixture", wait_seconds=0)
        fixture.authority.arm(lease)
        lease.release()
    before = fixture.authority.path.read_bytes()
    value = read(fixture)
    assert_failure(value, OPERATIONS[0], "LIVE_RECOVERY_REQUIRED", ownership="NOT_ACQUIRED")
    assert fixture.authority.path.read_bytes() == before
    assert value["timing_ms"]["release"] is None
    assert not (fixture.root / "runs" / ".active.lock").exists()


def test_genuine_common_fifo_gate_does_not_acquire_a_target_specific_lock(fixture, monkeypatch):
    lease = acquire_native_execution(fixture.root, "LEGACY-HOLD-FIXTURE", kind="fixture", wait_seconds=0)
    try:
        owner_before = (fixture.root / "runs" / ".active.lock").read_bytes()
        clock = Clock()
        manager = fixture.manager
        original_native = manager.native_execution
        def bounded(operation_id, **kwargs):
            assert kwargs["wait_seconds"] <= 2
            return original_native(operation_id, **{**kwargs, "wait_seconds": 0})
        monkeypatch.setattr(manager, "native_execution", bounded)
        value = read(fixture, manager=manager, clock=clock)
        assert_failure(value, OPERATIONS[0], "LIVE_LEASE_UNAVAILABLE", ownership="NOT_ACQUIRED")
        assert (fixture.root / "runs" / ".active.lock").read_bytes() == owner_before
        assert not (fixture.root / "state" / "fleet" / "native-locks").exists()
        assert not list((fixture.root / "state" / "concurrency" / "native-waiters").glob("*.json"))
    finally:
        lease.release()


@pytest.mark.parametrize("error,code", [(OwnershipBlocked("FIXTURE_" + SECRET), "LIVE_RECOVERY_REQUIRED"),
    (TimeoutError("CONCURRENCY_NATIVE_WAIT_TIMEOUT: " + SECRET), "LIVE_LEASE_UNAVAILABLE"),
    (OSError(SECRET), "LIVE_RECOVERY_REQUIRED"), (RuntimeError(SECRET), "LIVE_RECOVERY_REQUIRED")])
def test_preacquisition_faults_are_sanitized_and_do_not_release(fixture, error, code):
    clock = Clock()
    manager = SyntheticAdmission(clock, acquire_error=error, acquire_seconds=.005)
    value = read(fixture, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], code, ownership="NOT_ACQUIRED")
    assert manager.events == ["acquire"]
    assert value["timing_ms"]["lease"] == pytest.approx(5)
    assert value["timing_ms"]["release"] is None


def test_real_corrupt_fifo_sequence_is_recovery_failure_not_wait_timeout(fixture):
    sequence = fixture.root / "state" / "concurrency" / "native-sequence.json"
    sequence.write_text(SECRET)
    value = read(fixture)
    assert_failure(value, OPERATIONS[0], "LIVE_RECOVERY_REQUIRED", ownership="NOT_ACQUIRED")
    assert sequence.read_text() == SECRET
    assert not (fixture.root / "runs" / ".active.lock").exists()


def test_normal_release_measured_before_return(fixture):
    clock = Clock()
    manager = SyntheticAdmission(clock, acquire_seconds=.003, release_seconds=.005)
    value = read(fixture, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], "LIVE_ATTACH_ONLY_UNPROVEN")
    assert manager.events == ["acquire", "release"] and not manager.active
    assert value["timing_ms"]["lease"] == pytest.approx(3)
    assert value["timing_ms"]["release"] == pytest.approx(5)
    assert value["timing_ms"]["total"] == pytest.approx(8)


@pytest.mark.parametrize("unknown", [False, True])
def test_release_uncertainty_wins_and_preserves_primary(fixture, unknown):
    clock = Clock()
    manager = SyntheticAdmission(clock, release_error=OSError(SECRET), release_seconds=.007)
    target = {**fixture.target, "terminal_id": "term_" + "0" * 32} if unknown else fixture.target
    value = read(fixture, target=target, manager=manager, clock=clock)
    first = "TARGET_UNKNOWN" if unknown else "LIVE_ATTACH_ONLY_UNPROVEN"
    assert_failure(value, OPERATIONS[0], "LIVE_CLEANUP_UNPROVEN", ownership="RECOVERY_REQUIRED", primary=first)
    assert value["cleanup"] == {"status": "NOT_ATTEMPTED", "reason_code": "LIVE_CLEANUP_UNPROVEN"}
    assert value["timing_ms"]["release"] == pytest.approx(7)
    assert manager.events == ["acquire", "release"]


def test_release_overrun_records_expiry_without_replacing_first_denial(fixture):
    clock = Clock()
    manager = SyntheticAdmission(clock, release_seconds=11)
    value = read(fixture, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], "LIVE_ATTACH_ONLY_UNPROVEN")
    assert value["budget"]["expired"] is True
    assert value["timing_ms"]["release"] == value["timing_ms"]["total"] == 11000


def test_acquisition_expiry_skips_inventory_and_releases(fixture, monkeypatch):
    clock = Clock()
    manager = SyntheticAdmission(clock, acquire_seconds=10)
    def forbidden(*_args): raise AssertionError("Budget expired before config resolution")
    monkeypatch.setattr(reads, "TerminalInventory", forbidden)
    value = read(fixture, manager=manager, clock=clock)
    assert_failure(value, OPERATIONS[0], "LIVE_DEADLINE_EXCEEDED")
    assert value["budget"]["expired"] is True
    assert value["resolved_target"] is None
    assert manager.events == ["acquire", "release"]


@pytest.mark.parametrize("validation_seconds", [9, 10])
def test_remaining_budget_bounds_acquisition_or_skips_it(fixture, validation_seconds):
    class ValidationClock(Clock):
        def __init__(self):
            super().__init__()
            self.samples = 0
        def __call__(self):
            self.samples += 1
            return 0 if self.samples == 1 else validation_seconds
    clock = ValidationClock()
    manager = SyntheticAdmission(clock)
    value = read(fixture, manager=manager, clock=clock)
    if validation_seconds == 10:
        assert_failure(value, OPERATIONS[0], "LIVE_DEADLINE_EXCEEDED", ownership="NOT_ACQUIRED")
        assert manager.events == []
        assert value["timing_ms"]["lease"] is None
    else:
        assert_failure(value, OPERATIONS[0], "LIVE_ATTACH_ONLY_UNPROVEN")
        assert manager.arguments[0][1]["wait_seconds"] == 1


@pytest.mark.parametrize("operation", OPERATIONS)
def test_legacy_none_and_explicit_null_keep_fixed_calls_output_and_errors(fixture, monkeypatch, operation):
    import vibemql5.core.facade as module
    (fixture.root / "config" / "settings.json").write_text(json.dumps({"resource_guard": {}, "retention": {},
        "jobs": {}, "terminal_policy": {"alias": "MT5-2"}}))
    facade = ToolFacade(fixture.root)
    observed = []
    payload = {"source": "LEGACY_FIXTURE", "observed_at_utc": "fixture", "terminal": {}, "account": {}}
    class LegacyFixture:
        def __init__(self, inventory, alias): observed.append((inventory, alias))
        def state(self): return payload
    monkeypatch.setattr(module, "LiveTerminal", LegacyFixture)
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "manual")
    call = getattr(facade, operation)
    assert call() is payload
    assert call(None) is payload
    assert observed == [(facade.inv, "MT5-2"), (facade.inv, "MT5-2")]
    def state(self): raise RuntimeError("HISTORICAL_LEGACY_FAILURE")
    monkeypatch.setattr(LegacyFixture, "state", state)
    with pytest.raises(RuntimeError, match="^HISTORICAL_LEGACY_FAILURE$"): call(None)
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "background")
    with pytest.raises(RuntimeError, match="^MT5_INTERACTIVE_SESSION_REQUIRED:"): call()
    assert_failure(call(fixture.target), operation, "LIVE_ATTACH_ONLY_UNPROVEN")


def test_actual_generated_mcp_schema_adds_only_two_optional_objects(fixture, monkeypatch):
    monkeypatch.setattr(ToolFacade, "reconcile_cancelled_jobs", lambda *_args, **_kwargs: {})
    server = create_server(fixture.root, transport="stdio")
    tools = server._tool_manager._tools
    assert tuple(tools) == MCP_TOOL_NAMES
    assert len(tools) == MCP_TOOL_COUNT == 85
    assert hashlib.sha256(("\n".join(tools) + "\n").encode()).hexdigest() == MCP_TOOL_CATALOG_SHA256
    others = {name: tool.parameters for name, tool in tools.items() if name not in OPERATIONS}
    digest = hashlib.sha256(json.dumps(others, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == UNCHANGED_SCHEMAS_SHA256
    for name in OPERATIONS:
        tool = tools[name]
        schema = tool.parameters
        assert set(schema["properties"]) == {"target"}
        assert schema.get("required", []) == []
        assert schema["properties"]["target"]["default"] is None
        assert {branch["type"] for branch in schema["properties"]["target"]["anyOf"]} == {"object", "null"}
        args = tool.fn_metadata.arg_model
        assert args.model_validate({}).model_dump()["target"] is None
        assert args.model_validate({"target": None}).model_dump()["target"] is None
        with pytest.raises(ValidationError): args.model_validate({"target": SECRET})
        receipt = tool.fn(ctx=object(), target=fixture.target)
        assert_failure(receipt, name, "LIVE_ATTACH_ONLY_UNPROVEN")
    for name in ("compile_ea", "launch_test", "capture_live_chart", "get_symbol_snapshot"):
        assert "target" not in inspect.signature(tools[name].fn).parameters
