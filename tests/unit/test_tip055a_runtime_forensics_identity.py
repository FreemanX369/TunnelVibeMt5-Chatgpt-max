"""Isolated identity/provenance forensics selected by the supported runtime_forensics suite."""
from __future__ import annotations

from ownership_fixture import install_closed

import copy
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
from dataclasses import replace
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path

import pytest

from vibemql5.adapters.cli import main
from vibemql5.core.inventory import TerminalInventory
from vibemql5.fleet.identity import IdentityError, IdentityRegistry, normalize_path
from vibemql5.fleet.targets import validate_local_target
from vibemql5.models.types import TerminalInfo


def make_terminal(root: Path, alias="MT5-2", name="a", **updates):
    installation = root / "installations" / name
    data = root / "terminal-data" / name
    installation.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    terminal = installation / "terminal64.exe"
    editor = installation / "metaeditor64.exe"
    terminal.write_bytes(b"fixture terminal")
    editor.write_bytes(b"fixture editor")
    return TerminalInfo.from_dict({"alias": alias, "terminal_path": str(terminal),
        "metaeditor_path": str(editor), "data_hash": name, "data_root": str(data),
        "build": 6230, "enabled": True, **updates})


def write_config(root, terminals):
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": [row.to_dict() for row in terminals]}))


def ref(record, index=0):
    row = record["terminals"][index]
    return {"schema": "fleet.target/1", "device_id": record["device_id"],
        "terminal_id": row["terminal_id"], "terminal_generation": row["terminal_generation"]}


def bootstrap_process(root, barrier, queue):
    try:
        inventory = TerminalInventory(Path(root))
        barrier.wait(timeout=15)
        queue.put(IdentityRegistry(Path(root)).bootstrap(inventory.list(enabled_only=False)))
    except BaseException as exc:
        queue.put({"error": repr(exc)})


def interrupted_update(root, terminal_id):
    from vibemql5.core import jobs
    jobs.os.replace = lambda *args, **kwargs: os._exit(71)
    IdentityRegistry(Path(root)).update(terminal_id, expected_revision=1,
        operation_id="crash-rename", alias="renamed")


def file_hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file() and "fleet" not in path.parts}


def test_ac01_legacy_read_does_not_create_registry_or_state(tmp_path):
    terminal = make_terminal(tmp_path)
    write_config(tmp_path, [terminal])
    before = file_hashes(tmp_path)
    inventory = TerminalInventory(tmp_path)
    described = inventory.describe()[0]
    for key, value in terminal.to_dict().items():
        assert described[key] == value
    assert described["identity_status"] == "UNENROLLED"
    assert described["device_id"] is described["terminal_id"] is described["terminal_generation"] is None
    assert not (tmp_path / "state").exists()
    validation = inventory.validate()[0]
    assert validation["ok"] is True
    assert validation["identity_status"] == "UNENROLLED"
    assert file_hashes(tmp_path) == before


def test_ac02_ac03_ids_survive_process_reload_observation_and_binary_updates(tmp_path, monkeypatch):
    terminals = [make_terminal(tmp_path), make_terminal(tmp_path, "MT5-3", "b")]
    write_config(tmp_path, terminals)
    registry = IdentityRegistry(tmp_path)
    initial = registry.bootstrap(terminals)
    command = [sys.executable, "-c", "import json,sys; from pathlib import Path; from vibemql5.fleet.identity import IdentityRegistry; print(json.dumps(IdentityRegistry(Path(sys.argv[1])).load()))", str(tmp_path)]
    loaded = json.loads(subprocess.check_output(command, text=True))
    assert loaded == initial
    assert len({row["terminal_id"] for row in loaded["terminals"]}) == 2
    terminals[0] = replace(terminals[0], build=6500)
    Path(terminals[0].terminal_path).write_bytes(b"different build bytes")
    monkeypatch.setenv("COMPUTERNAME", "new-host-label")
    assert registry.bootstrap(terminals) == initial
    write_config(tmp_path, terminals)
    described = TerminalInventory(tmp_path).describe()[0]
    assert described["configured_build"] == 6500
    assert described["terminal_generation"] == 1
    assert described["terminal_id"] == initial["terminals"][0]["terminal_id"]


def test_ac04_rename_keeps_identity_but_requires_config_alignment(tmp_path):
    terminal = make_terminal(tmp_path)
    registry = IdentityRegistry(tmp_path)
    initial = registry.bootstrap([terminal])
    receipt = registry.update(initial["terminals"][0]["terminal_id"], expected_revision=1,
        operation_id="rename-1", alias="renamed")
    assert receipt["terminal"]["terminal_id"] == initial["terminals"][0]["terminal_id"]
    assert receipt["terminal"]["terminal_generation"] == 1
    with pytest.raises(IdentityError, match="TARGET_MISMATCH"):
        validate_local_target(tmp_path, [terminal], ref(registry.load()))
    terminal = replace(terminal, alias="renamed")
    result = validate_local_target(tmp_path, [terminal], ref(registry.load()))
    assert result["alias"] == "renamed"
    assert "MT5-2" not in registry.overlay([terminal])
    with pytest.raises(IdentityError, match="IDENTITY_INVALID"):
        registry.update(receipt["terminal"]["terminal_id"], expected_revision=2,
            operation_id="bad-alias", alias=" ")


def test_ac05_binding_replace_cas_replay_and_operation_conflict(tmp_path):
    terminal = make_terminal(tmp_path)
    replacement = make_terminal(tmp_path, name="replacement")
    registry = IdentityRegistry(tmp_path)
    initial = registry.bootstrap([terminal])
    terminal_id = initial["terminals"][0]["terminal_id"]
    params = dict(expected_revision=1, operation_id="replace-1",
        terminal_path=replacement.terminal_path, data_root=replacement.data_root)
    receipt = registry.update(terminal_id, **params)
    assert receipt["identity_revision"] == 2
    assert receipt["terminal"]["terminal_generation"] == 2
    committed = registry.path.read_bytes()
    replay = IdentityRegistry(tmp_path).update(terminal_id, **params)
    assert replay["idempotent_recovered"] is True
    assert replay["terminal"] == receipt["terminal"]
    assert registry.path.read_bytes() == committed
    with pytest.raises(IdentityError, match="IDENTITY_OPERATION_CONFLICT"):
        registry.update(terminal_id, **{**params, "enabled": False})
    with pytest.raises(IdentityError, match="IDENTITY_REVISION_CONFLICT"):
        registry.update(terminal_id, **{**params, "operation_id": "stale-identical"})
    next_receipt = registry.update(terminal_id, expected_revision=2, operation_id="disable", enabled=False)
    assert next_receipt["identity_revision"] == 3
    # A later commit must not erase the exact original operation receipt.
    assert registry.update(terminal_id, **params)["identity_revision"] == 2
    assert registry.load()["identity_revision"] == 3


def test_ac05_replay_uses_explicit_inputs_after_binding_disappears(tmp_path):
    terminal = make_terminal(tmp_path)
    replacement = make_terminal(tmp_path, name="replacement")
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap([terminal])
    parameters = dict(expected_revision=1, operation_id="replace-replay",
        terminal_path=replacement.terminal_path, data_root=replacement.data_root)
    receipt = registry.update(record["terminals"][0]["terminal_id"], **parameters)
    committed = registry.path.read_bytes()
    Path(replacement.terminal_path).unlink()
    Path(replacement.data_root).rmdir()
    recovered = IdentityRegistry(tmp_path).update(record["terminals"][0]["terminal_id"], **parameters)
    assert recovered["idempotent_recovered"] is True
    assert recovered["terminal"] == receipt["terminal"]
    assert recovered["identity_revision"] == receipt["identity_revision"]
    assert registry.path.read_bytes() == committed


def test_ac07_existing_compile_and_live_use_fixed_target_and_global_lease(tmp_path, monkeypatch):
    import vibemql5.core.facade as facade_module
    from vibemql5.core.concurrency import ConcurrencyManager
    terminal = make_terminal(tmp_path)
    other = make_terminal(tmp_path, "MT5-3", "b")
    write_config(tmp_path, [terminal, other])
    (tmp_path / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {}, "retention": {}, "jobs": {"max_concurrent": 1},
        "terminal_policy": {"mode": "fixed", "alias": "MT5-2"}}))
    IdentityRegistry(tmp_path).bootstrap([terminal, other])
    source = tmp_path / "workspaces" / "demo" / "Experts" / "DemoEA.mq5"
    source.parent.mkdir(parents=True); source.write_text("void OnTick(){}")
    facade = facade_module.ToolFacade(tmp_path)
    monkeypatch.setattr(facade, "_require_mt5_capable_runtime", lambda: None)
    calls, leases = [], []
    @contextmanager
    def native(operation_id, **kwargs):
        leases.append(kwargs["kind"])
        yield SimpleNamespace(to_dict=lambda: {"fixture": True})
    monkeypatch.setattr(facade.concurrency, "native_execution", native)
    def compile_fixture(self, workspace, ea, alias, run_dir, **kwargs):
        calls.append(("compile", alias))
        (run_dir / "compiled.ex5").write_bytes(b"fixture binary")
        return {"status": "COMPILED", "errors": 0, "warnings": 0}
    monkeypatch.setattr(facade_module.CompilerDriver, "compile", compile_fixture)
    facade.compile_ea("demo", "Experts/DemoEA.mq5", terminal="MT5-3", mock=True)
    monkeypatch.setattr(facade_module, "normalize_tester_request", lambda *args, **kwargs: {})
    def launch_fixture(request, **kwargs):
        calls.append(("test", request["terminal"]))
        return {"request": request}
    monkeypatch.setattr(facade.jobs, "launch_test", launch_fixture)
    assert facade.launch_test("demo", "Experts/DemoEA.mq5", terminal="MT5-3", mock=True)["request"]["terminal"] == "MT5-2"
    class LiveFixture:
        def __init__(self, inventory, alias): calls.append(("live", alias))
        def state(self): return {"fixture": True}
    monkeypatch.setattr(facade_module, "LiveTerminal", LiveFixture)
    assert facade.get_terminal_live_state()["fixture"] is True
    assert calls == [("compile", "MT5-2"), ("test", "MT5-2"), ("live", "MT5-2")]
    assert leases == ["direct_compile", "live_terminal_state"]
    # Acquire the real untouched manager to prove its historical lock location.
    install_closed(tmp_path)
    manager = ConcurrencyManager(tmp_path)
    with manager.native_execution("LOCAL-FIXTURE", kind="fixture", wait_seconds=0.1):
        assert (tmp_path / "runs" / ".active.lock").exists()
        assert not (tmp_path / "state" / "fleet" / "native-locks").exists()


def test_ac06_disable_reenable_new_binding_requires_explicit_enrollment(tmp_path):
    terminal = make_terminal(tmp_path)
    registry = IdentityRegistry(tmp_path)
    initial = registry.bootstrap([terminal])
    terminal_id = initial["terminals"][0]["terminal_id"]
    registry.update(terminal_id, expected_revision=1, operation_id="disable", enabled=False)
    assert registry.overlay([terminal])[terminal.alias]["identity_status"] == "DISABLED"
    with pytest.raises(IdentityError, match="TARGET_MISMATCH"):
        validate_local_target(tmp_path, [terminal], ref(registry.load()))
    registry.update(terminal_id, expected_revision=2, operation_id="enable", enabled=True)
    assert registry.load()["terminals"][0]["terminal_id"] == terminal_id
    assert registry.load()["terminals"][0]["terminal_generation"] == 1
    new_terminal = make_terminal(tmp_path, "MT5-3", "b")
    assert registry.overlay([terminal, new_terminal])["MT5-3"]["identity_status"] == "UNENROLLED"
    with pytest.raises(IdentityError, match="IDENTITY_REVISION_CONFLICT"):
        registry.bootstrap([terminal, new_terminal])
    enrolled = registry.bootstrap([terminal, new_terminal], expected_revision=3)
    assert enrolled["identity_revision"] == 4
    assert enrolled["terminals"][0]["terminal_id"] == terminal_id
    assert enrolled["terminals"][1]["terminal_id"] != terminal_id
    with pytest.raises(IdentityError, match="IDENTITY_REVISION_CONFLICT"):
        registry.bootstrap([terminal, new_terminal], expected_revision=3)


@pytest.mark.parametrize("field", ["terminal_path", "data_root"])
def test_ac08_windows_case_separator_duplicates_and_unobservable_paths(tmp_path, field):
    first = TerminalInfo("MT5-2", r"C:\MT5-A\terminal64.exe", r"C:\MT5-A\metaeditor64.exe", "A", r"C:\Data-A", 6230)
    second = TerminalInfo("MT5-3", r"C:\MT5-B\terminal64.exe", r"C:\MT5-B\metaeditor64.exe", "B", r"C:\Data-B", 6230)
    second = replace(second, **{field: getattr(first, field).upper().replace("\\", "/") + ("/" if field == "data_root" else "")})
    registry = IdentityRegistry(tmp_path)
    with pytest.raises(IdentityError, match="RESOURCE_CONFLICT"):
        registry.bootstrap([first, second])
    assert not registry.path.exists()
    write_config(tmp_path, [first, second])
    rows = TerminalInventory(tmp_path).describe()
    assert all(row["identity_status"] == "RESOURCE_CONFLICT" for row in rows)
    assert all(row["resource_qualification"] == "UNQUALIFIED" and not row["routed_native_enabled"] for row in rows)
    assert normalize_path(r"C:/MT5-A/./terminal64.exe") == normalize_path(first.terminal_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink fixture; Windows junction evidence is a separate gate")
def test_ac08_observable_symlink_hardlink_and_symlink_retarget(tmp_path):
    first = make_terminal(tmp_path)
    second = make_terminal(tmp_path, "MT5-3", "b")
    linked = tmp_path / "data-link"
    linked.symlink_to(first.data_root, target_is_directory=True)
    second = replace(second, data_root=str(linked))
    registry = IdentityRegistry(tmp_path)
    with pytest.raises(IdentityError, match="RESOURCE_CONFLICT"):
        registry.bootstrap([first, second])
    second = make_terminal(tmp_path, "MT5-3", "b")
    Path(second.terminal_path).unlink()
    os.link(first.terminal_path, second.terminal_path)
    with pytest.raises(IdentityError, match="RESOURCE_CONFLICT"):
        registry.bootstrap([first, second])
    first = replace(first, data_root=str(linked))
    record = registry.bootstrap([first])
    linked.unlink()
    alternate = tmp_path / "alternate-data"
    alternate.mkdir()
    linked.symlink_to(alternate, target_is_directory=True)
    assert registry.overlay([first])["MT5-2"]["identity_status"] == "TARGET_MISMATCH"
    with pytest.raises(IdentityError, match="TARGET_MISMATCH"):
        validate_local_target(tmp_path, [first], ref(record))


def test_ac08_duplicate_alias_not_hidden_by_legacy_dictionary(tmp_path):
    first = make_terminal(tmp_path)
    second = make_terminal(tmp_path, "mt5-2", "b")
    write_config(tmp_path, [first, second])
    inventory = TerminalInventory(tmp_path)
    row = inventory.describe()[0]
    assert row["identity_status"] == "RESOURCE_CONFLICT"
    assert row["resource_qualification"] == "UNQUALIFIED"
    with pytest.raises(IdentityError, match="RESOURCE_CONFLICT"):
        IdentityRegistry(tmp_path).bootstrap(inventory._identity_items)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction fixture requires Windows")
def test_ac08_windows_junction_duplicate_and_retarget(tmp_path):
    first = make_terminal(tmp_path)
    second = make_terminal(tmp_path, "MT5-3", "b")
    junction = tmp_path / "junction-data"
    create = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), first.data_root], capture_output=True, text=True)
    if create.returncode:
        pytest.skip("Junction creation unavailable in Windows fixture: " + create.stderr)
    second = replace(second, data_root=str(junction))
    registry = IdentityRegistry(tmp_path)
    with pytest.raises(IdentityError, match="RESOURCE_CONFLICT"):
        registry.bootstrap([first, second])
    first = replace(first, data_root=str(junction))
    record = registry.bootstrap([first])
    os.rmdir(junction)
    alternate = tmp_path / "alternate-data"
    alternate.mkdir()
    create = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(alternate)], capture_output=True, text=True)
    assert create.returncode == 0, create.stderr
    try:
        assert registry.overlay([first])["MT5-2"]["identity_status"] == "TARGET_MISMATCH"
        with pytest.raises(IdentityError, match="TARGET_MISMATCH"):
            validate_local_target(tmp_path, [first], ref(record))
    finally:
        os.rmdir(junction)


def test_ac09_spawned_process_bootstraps_commit_one_complete_identity(tmp_path):
    terminals = [make_terminal(tmp_path), make_terminal(tmp_path, "MT5-3", "b")]
    write_config(tmp_path, terminals)
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(3), context.Queue()
    processes = [context.Process(target=bootstrap_process, args=(str(tmp_path), barrier, queue)) for _ in range(3)]
    for process in processes:
        process.start()
    results = [queue.get(timeout=25) for _ in processes]
    for process in processes:
        process.join(timeout=25)
        assert process.exitcode == 0
    assert all("error" not in result for result in results), [result["error"] for result in results if "error" in result]
    assert results[0] == results[1] == results[2]
    assert IdentityRegistry(tmp_path).load() == results[0]
    assert len(results[0]["terminals"]) == 2


def test_ac10_killed_writer_before_replace_retains_committed_registry(tmp_path):
    terminal = make_terminal(tmp_path)
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap([terminal])
    committed = registry.path.read_bytes()
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=interrupted_update, args=(str(tmp_path), record["terminals"][0]["terminal_id"]))
    process.start(); process.join(timeout=20)
    assert process.exitcode == 71
    assert registry.path.read_bytes() == committed
    assert registry.load() == record
    # Complete abandoned temporary files are ignored, not treated as committed state.
    assert list(registry.path.parent.glob(".identity.json.*.tmp"))
    assert registry.bootstrap([terminal]) == record
    assert registry.update(record["terminals"][0]["terminal_id"], expected_revision=1,
        operation_id="after-crash", alias="renamed")["identity_revision"] == 2


@pytest.mark.parametrize("corrupt", ["{", "[]", None, "schema", "revision", "generation", "id", "binding", "operation"])
def test_ac10_corrupt_registry_is_invalid_and_never_regenerated(tmp_path, corrupt):
    terminal = make_terminal(tmp_path)
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap([terminal])
    if corrupt == "schema": record["schema"] = "fleet.identity/99"
    elif corrupt == "revision": record["identity_revision"] = True
    elif corrupt == "generation": record["terminals"][0]["terminal_generation"] = True
    elif corrupt == "id": record["terminals"].append(copy.deepcopy(record["terminals"][0]))
    elif corrupt == "binding": record["terminals"][0]["binding"]["data_root"] = "relative"
    elif corrupt == "operation": record["operations"] = {"op": {"request_sha256": "oops"}}
    raw = corrupt if corrupt in ("{", "[]") else json.dumps(None if corrupt is None else record)
    registry.path.write_text(raw)
    with pytest.raises(IdentityError, match="IDENTITY_INVALID"):
        registry.load()
    assert registry.overlay([terminal])["MT5-2"]["identity_status"] == "INVALID"
    assert registry.overlay([terminal])["MT5-2"]["terminal_id"] is None
    with pytest.raises(IdentityError, match="IDENTITY_INVALID"):
        registry.bootstrap([terminal])
    assert registry.path.read_text() == raw


@pytest.mark.parametrize("field,value", [("terminal_generation", True), ("enabled", 1), ("alias", ""), ("binding", {})])
def test_ac10_malformed_durable_receipt_cannot_replay(tmp_path, field, value):
    terminal = make_terminal(tmp_path)
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap([terminal])
    terminal_id = record["terminals"][0]["terminal_id"]
    registry.update(terminal_id, expected_revision=1, operation_id="disable", enabled=False)
    record = registry.load()
    record["operations"]["disable"]["receipt"]["terminal"][field] = value
    registry.path.write_text(json.dumps(record))
    with pytest.raises(IdentityError, match="IDENTITY_INVALID"):
        registry.update(terminal_id, expected_revision=1, operation_id="disable", enabled=False)


def test_ac10_duplicate_persisted_binding_is_invalid(tmp_path):
    terminals = [make_terminal(tmp_path), make_terminal(tmp_path, "MT5-3", "b")]
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap(terminals)
    record["terminals"][1]["binding"] = copy.deepcopy(record["terminals"][0]["binding"])
    registry.path.write_text(json.dumps(record))
    with pytest.raises(IdentityError, match="IDENTITY_INVALID.*Duplicate persisted"):
        registry.load()


def test_ac11_target_validation_fails_without_fallback_or_native_calls(tmp_path, monkeypatch):
    from vibemql5.core.compiler import CompilerDriver
    def forbidden(*args, **kwargs):
        pytest.fail("target validation dispatched a native side effect or fallback")
    monkeypatch.setattr(TerminalInventory, "select_execution_terminal", forbidden)
    monkeypatch.setattr(CompilerDriver, "compile", forbidden)
    terminal = make_terminal(tmp_path)
    registry = IdentityRegistry(tmp_path)
    with pytest.raises(IdentityError, match="IDENTITY_UNENROLLED"):
        validate_local_target(tmp_path, [terminal], {"schema": "fleet.target/1"})
    record = registry.bootstrap([terminal])
    target = ref(record)
    assert validate_local_target(tmp_path, [terminal], target)["terminal_id"] == target["terminal_id"]
    cases = [("TARGET_UNKNOWN", {**target, "device_id": "dev_unknown"}),
        ("TARGET_UNKNOWN", {**target, "terminal_id": "term_unknown"}),
        ("TARGET_MISMATCH", {**target, "terminal_generation": 2}),
        ("TARGET_MISMATCH", {**target, "terminal_generation": True}),
        ("TARGET_MISMATCH", {**target, "unexpected": True}),
        ("ROUTED_NATIVE_NOT_ENABLED", {**target, "route_generation": 1})]
    for code, value in cases:
        with pytest.raises(IdentityError, match=code):
            validate_local_target(tmp_path, [terminal], value)
    with pytest.raises(IdentityError, match="ROUTED_NATIVE_NOT_ENABLED"):
        validate_local_target(tmp_path, [terminal], target, capability="compile")
    replacement = make_terminal(tmp_path, name="other")
    terminal = replace(terminal, terminal_path=replacement.terminal_path)
    with pytest.raises(IdentityError, match="TARGET_MISMATCH"):
        validate_local_target(tmp_path, [terminal], target)


def test_ac11_concurrent_binding_update_cannot_return_mixed_target(tmp_path, monkeypatch):
    terminal = make_terminal(tmp_path)
    replacement = make_terminal(tmp_path, name="replacement")
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap([terminal])
    overlay = IdentityRegistry.overlay
    def changed_after_first_load(self, terminals):
        registry.update(record["terminals"][0]["terminal_id"], expected_revision=1,
            operation_id="interleaved-update", terminal_path=replacement.terminal_path,
            data_root=replacement.data_root)
        return overlay(self, [replace(terminal, terminal_path=replacement.terminal_path, data_root=replacement.data_root)])
    monkeypatch.setattr(IdentityRegistry, "overlay", changed_after_first_load)
    with pytest.raises(IdentityError, match="TARGET_MISMATCH.*changed during"):
        validate_local_target(tmp_path, [terminal], ref(record))


@pytest.mark.skipif(os.name == "nt", reason="Windows paths are observable only in the Windows deployment gate")
def test_ac11_nonobservable_windows_roots_never_claim_qualification(tmp_path):
    terminal = TerminalInfo("MT5-2", r"C:\MT5-A\terminal64.exe", r"C:\MT5-A\metaeditor64.exe", "A", r"C:\Data-A", 6230)
    registry = IdentityRegistry(tmp_path)
    record = registry.bootstrap([terminal])
    overlay = registry.overlay([terminal])["MT5-2"]
    assert overlay["identity_status"] == "ENROLLED"
    assert overlay["resource_qualification"] == "UNQUALIFIED"
    with pytest.raises(IdentityError, match="TARGET_MISMATCH.*UNQUALIFIED"):
        validate_local_target(tmp_path, [terminal], ref(record))


def test_ac12_build_authority_and_legacy_config_unchanged(tmp_path):
    terminal = make_terminal(tmp_path)
    write_config(tmp_path, [terminal])
    run = tmp_path / "runs" / "BT-fixture"
    run.mkdir(parents=True)
    result = {"job_id": "BT-fixture", "environment": {"terminal": "MT5-2", "terminal_build_at_execution": 6500}}
    (run / "result.json").write_text(json.dumps(result))
    config_bytes = (tmp_path / "config" / "terminals.json").read_bytes()
    IdentityRegistry(tmp_path).bootstrap([terminal])
    row = TerminalInventory(tmp_path).describe()[0]
    assert row["configured_build"] == 6230
    assert row["observed_build"] == row["build"] == 6500
    assert row["build_source"] == "LATEST_COMPLETED_NATIVE_RESULT"
    assert TerminalInfo.from_dict(terminal.to_dict()) == terminal
    assert (tmp_path / "config" / "terminals.json").read_bytes() == config_bytes


def test_ac12_imported_mcp_catalog_order_count_and_native_signatures_unchanged(tmp_path):
    import inspect
    from vibemql5.adapters.mcp import create_server
    from vibemql5.contracts import MCP_TOOL_NAMES, MCP_TOOL_COUNT, MCP_TOOL_CATALOG_SHA256
    terminal = make_terminal(tmp_path)
    write_config(tmp_path, [terminal])
    IdentityRegistry(tmp_path).bootstrap([terminal])
    server = create_server(tmp_path, transport="stdio")
    tools = server._tool_manager._tools
    assert tuple(tools) == MCP_TOOL_NAMES
    assert len(tools) == MCP_TOOL_COUNT == 85
    assert hashlib.sha256(("\n".join(tools) + "\n").encode()).hexdigest() == MCP_TOOL_CATALOG_SHA256
    for name in ("compile_ea", "launch_test", "capture_live_chart"):
        assert "target" not in inspect.signature(tools[name].fn).parameters
    assert not any(name.startswith("identity_") for name in tools)


def test_ac13_ac14_enroll_overlay_rollback_does_not_touch_history(tmp_path, monkeypatch):
    terminal = make_terminal(tmp_path)
    write_config(tmp_path, [terminal])
    historical = {"runs/BT-fixture/job.json": b'{"state":"PASSED"}\n',
        "runs/BT-fixture/result.json": b'{"schema_version":"1.3"}\n',
        "state/project-sessions/example.json": b'{"revision":"REV-1"}\r\n',
        "state/iterations/example.json": b'{"state":"ACCEPTED"}\n',
        "state/continuity/example.json": b'{"revision":2}\n',
        "state/revisions/example.json": b'{"hash":"fixture"}\n',
        "state/operations/example.json": b'{"operation_id":"old-operation"}\n'}
    for path, raw in historical.items():
        fixture = tmp_path / path
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(raw)
    hashes = file_hashes(tmp_path)
    registry = IdentityRegistry(tmp_path)
    registry.bootstrap([terminal])
    inventory = TerminalInventory(tmp_path)
    assert inventory.describe()[0]["identity_status"] == "ENROLLED"
    identity_bytes = registry.path.read_bytes()
    # Simulate rolling back only the overlay while retaining its durable state.
    monkeypatch.setattr(IdentityRegistry, "overlay", lambda self, rows: {row.alias.upper(): {} for row in rows})
    legacy_row = inventory.describe()[0]
    assert "identity_status" not in legacy_row
    assert legacy_row["alias"] == "MT5-2"
    assert file_hashes(tmp_path) == hashes
    assert registry.path.read_bytes() == identity_bytes


def test_cli_identity_avoids_facade_side_effects_and_reports_error(tmp_path, monkeypatch, capsys):
    import vibemql5.adapters.cli as cli
    monkeypatch.setattr(cli, "ToolFacade", lambda *args, **kwargs: pytest.fail("identity CLI constructed native facade"))
    terminal = make_terminal(tmp_path)
    write_config(tmp_path, [terminal])
    main(["--root", str(tmp_path), "identity-show"])
    assert json.loads(capsys.readouterr().out)["identity_status"] == "UNENROLLED"
    assert not (tmp_path / "state").exists()
    main(["--root", str(tmp_path), "identity-bootstrap"])
    record = json.loads(capsys.readouterr().out)
    assert record["identity_revision"] == 1
    main(["--root", str(tmp_path), "identity-update", record["terminals"][0]["terminal_id"],
        "--expected-revision", "1", "--operation-id", "cli-disable", "--enabled", "false"])
    assert json.loads(capsys.readouterr().out)["terminal"]["enabled"] is False
    exitcode = main(["--root", str(tmp_path), "identity-update", record["terminals"][0]["terminal_id"],
        "--expected-revision", "1", "--operation-id", "cli-stale", "--enabled", "true"])
    assert exitcode == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "IDENTITY_REVISION_CONFLICT"
    assert not (tmp_path / "runs").exists()


def test_cli_invalid_config_does_not_enroll(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "identity-bootstrap"]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "IDENTITY_INVALID"
    assert not (tmp_path / "state").exists()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "terminals.json").write_text("{")
    assert main(["--root", str(tmp_path), "identity-bootstrap"]) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == "IDENTITY_INVALID"
    assert not (tmp_path / "state").exists()
