from __future__ import annotations

import hashlib
import json
import threading
import sys
import types
from pathlib import Path

import pytest

from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES
from vibemql5.core.binary_ingress import BinaryIngressManager, EX5_IMPORT_MAX_BYTES, _safe_relative_ex5, _trusted_download_host
from vibemql5.core.facade import ToolFacade
from vibemql5.core.provenance import load_bridge_provenance, producer_identity, validate_state_provenance
from vibemql5.core.jobs import JobStore
from vibemql5.worker import run_job


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "VibeMQL5"
    (root / "config" / "presets").mkdir(parents=True)
    (root / "workspaces" / "BD" / "Experts").mkdir(parents=True)
    (root / "workspaces" / "BD" / "Sets").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    data_root = root / "fake-terminal-data"
    (data_root / "MQL5" / "Experts").mkdir(parents=True)
    terminal = root / "fake-terminal" / "terminal64.exe"
    meta = root / "fake-terminal" / "MetaEditor64.exe"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"")
    meta.write_bytes(b"")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": [{
        "alias": "MT5-2", "terminal_path": str(terminal), "metaeditor_path": str(meta),
        "data_hash": "TEST", "data_root": str(data_root), "build": 6140, "enabled": True,
    }]}), encoding="utf-8")
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {"disk_warning_gb": 0, "disk_block_gb": 0, "min_free_memory_mb": 0},
        "retention": {"completed_jobs": 20}, "jobs": {"max_concurrent": 1, "compile_timeout_seconds": 120},
        "defaults": {"terminal": "MT5-2"},
        "terminal_policy": {"mode": "fixed", "alias": "MT5-2", "allow_fallback": False,
                            "graceful_close_seconds": 1, "reconnect_timeout_seconds": 1},
    }), encoding="utf-8")
    (root / "config" / "presets" / "smoke.json").write_text(json.dumps({
        "symbol": "XAUUSDm", "period": "M1", "model": 4, "deposit": 10000,
        "currency": "USD", "leverage": 1000, "visual": False,
    }), encoding="utf-8")
    (root / "workspaces" / "BD" / "Sets" / "default.set").write_text("A=1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    return root


def _ex5(tmp_path: Path, name: str, payload: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(payload)
    return p


def _write_build_provenance(
    root: Path,
    count: int = 59,
    catalog_sha256: str = "0" * 64,
) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "build-provenance.json").write_text(json.dumps({
        "schema_version": "1.0",
        "bridge_name": "VibeMQL5 Bridge",
        "bridge_version": "0.2.32",
        "bridge_build": "TIP-026R3",
        "result_schema": "1.4",
        "mcp_tool_count": count,
        "mcp_tool_catalog_sha256": catalog_sha256,
    }), encoding="utf-8")


def _producer_state(root: Path, component: str = "watchdog") -> tuple[Path, dict]:
    producer_path = root / f"{component}.ps1"
    producer_path.write_text("Write-Output 'ok'\n", encoding="utf-8")
    producer = producer_identity(producer_path, component)
    return producer_path, {
        "schema_version": "1.0",
        "bridge_build": "TIP-026R3",
        "bridge_version": "0.2.32",
        **producer,
    }


def test_tip026_catalog_is_43_and_contains_import_ex5():
    assert MCP_TOOL_COUNT == 67
    assert "import_ex5" in MCP_TOOL_NAMES
    assert MCP_TOOL_CATALOG_SHA256 == "835e5dfb8b86649bfafdc616a440f108a78389404e062bd76ba430865025d7fe"


def test_tip031_bridge_provenance_catalog_comes_from_contract(tmp_path: Path):
    root = _root(tmp_path)
    _write_build_provenance(root)
    provenance = load_bridge_provenance(root)
    assert provenance["mcp_tool_count"] == MCP_TOOL_COUNT == 67
    assert provenance["mcp_tool_catalog_sha256"] == MCP_TOOL_CATALOG_SHA256
    assert provenance["mcp_tool_catalog_source"] == "contracts.py"


def test_tip031_state_provenance_rejects_stale_catalog_metadata(tmp_path: Path):
    root = _root(tmp_path)
    _write_build_provenance(root)
    producer_path, state = _producer_state(root)
    state["mcp_tool_count"] = 59
    state["mcp_tool_catalog_sha256"] = "0" * 64
    result = validate_state_provenance(root, state, producer_path, "watchdog")
    assert result["fresh"] is False
    assert "MCP_TOOL_COUNT_STALE" in result["reasons"]
    assert "MCP_TOOL_CATALOG_SHA_STALE" in result["reasons"]
    assert result["expected_catalog"]["mcp_tool_count"] == MCP_TOOL_COUNT


def test_tip031_state_provenance_accepts_contract_catalog_metadata(tmp_path: Path):
    root = _root(tmp_path)
    _write_build_provenance(root)
    producer_path, state = _producer_state(root, "tunnel-supervisor")
    state["mcp_tool_count"] = MCP_TOOL_COUNT
    state["mcp_tool_catalog_sha256"] = MCP_TOOL_CATALOG_SHA256
    result = validate_state_provenance(root, state, producer_path, "tunnel-supervisor")
    assert result["fresh"] is True
    assert result["reasons"] == []


def test_tip026_import_exact_hash_and_idempotent_reuse(tmp_path: Path):
    root = _root(tmp_path)
    data = b"EX5-PROBE\x00" + bytes(range(256)) * 8
    source = _ex5(tmp_path, "WSLOW public v1.12.ex5", data)
    sha = hashlib.sha256(data).hexdigest()
    manager = BinaryIngressManager(root)
    first = manager.import_local_file("BD", source, "Experts/WSLOW public v1.12.ex5", sha)
    second = manager.import_local_file("BD", source, "Experts/WSLOW public v1.12.ex5", sha)
    assert first["status"] == "IMPORTED"
    assert second["status"] == "ALREADY_PRESENT"
    assert first["ea_binary_ref"] == second["ea_binary_ref"]
    assert first["sha256"] == sha
    assert first["bytes"] == len(data)
    binding = manager.resolve_for_launch("BD", "Experts/WSLOW public v1.12.ex5", first["ea_binary_ref"])
    assert binding["sha256"] == sha
    assert Path(binding["object_path"]).read_bytes() == data
    assert (root / "workspaces" / "BD" / "Experts" / "WSLOW public v1.12.ex5").read_bytes() == data
    provenance = manager.import_provenance(first["ea_binary_ref"])
    assert provenance["source"] == "LOCAL_QUALIFICATION_FILE"
    assert provenance["receipt_count"] == 2


def test_tip026_wrong_sha_fails_before_object_binding(tmp_path: Path):
    root = _root(tmp_path)
    source = _ex5(tmp_path, "a.ex5", b"abc")
    manager = BinaryIngressManager(root)
    with pytest.raises(ValueError, match="EXPECTED_SHA256_MISMATCH"):
        manager.import_local_file("BD", source, "Experts/a.ex5", "0" * 64)
    assert not list((root / "binary_store" / "ex5" / "objects").rglob("*.ex5"))
    assert not list((root / "binary_store" / "ex5" / "bindings").glob("*.json"))
    assert not (root / "workspaces" / "BD" / "Experts" / "a.ex5").exists()


@pytest.mark.parametrize("bad", [
    "../../evil.ex5", "C:/temp/evil.ex5", "//server/share/evil.ex5", "Sets/evil.ex5", "Experts/evil.mq5",
])
def test_tip026_path_and_extension_fail_closed(bad: str):
    with pytest.raises(ValueError):
        _safe_relative_ex5(bad)


def test_tip026_empty_and_oversize_rejected(tmp_path: Path):
    root = _root(tmp_path)
    manager = BinaryIngressManager(root)
    empty = _ex5(tmp_path, "empty.ex5", b"")
    with pytest.raises(ValueError, match="IMPORT_EMPTY_FILE"):
        manager.import_local_file("BD", empty)
    large = tmp_path / "large.ex5"
    with large.open("wb") as f:
        f.seek(EX5_IMPORT_MAX_BYTES)
        f.write(b"x")
    with pytest.raises(ValueError, match="IMPORT_FILE_TOO_LARGE"):
        manager.import_local_file("BD", large)


def test_tip026_same_path_different_binary_conflict_and_safe_overwrite(tmp_path: Path):
    root = _root(tmp_path)
    manager = BinaryIngressManager(root)
    a = _ex5(tmp_path, "a.ex5", b"A" * 4096)
    b = _ex5(tmp_path, "b.ex5", b"B" * 4096)
    aa = manager.import_local_file("BD", a, "Experts/shared.ex5")
    with pytest.raises(ValueError, match="DESTINATION_CONFLICT"):
        manager.import_local_file("BD", b, "Experts/shared.ex5")
    bb = manager.import_local_file("BD", b, "Experts/shared.ex5", overwrite=True)
    assert aa["ea_binary_ref"] != bb["ea_binary_ref"]
    assert manager.resolve_for_launch("BD", "Experts/shared.ex5", aa["ea_binary_ref"])["sha256"] == hashlib.sha256(a.read_bytes()).hexdigest()
    assert manager.resolve_for_launch("BD", "Experts/shared.ex5", bb["ea_binary_ref"])["sha256"] == hashlib.sha256(b.read_bytes()).hexdigest()
    assert (root / "workspaces" / "BD" / "Experts" / "shared.ex5").read_bytes() == b.read_bytes()
    # The old immutable ref remains executable even though the mutable workspace path now points at B.
    req = {"workspace":"BD","ea":"Experts/shared.ex5","ea_binary_ref":aa["ea_binary_ref"],"terminal":"MT5-2","preset":"smoke","set_file":"Sets/default.set","overrides":{"from_date":"2026.08.26","to_date":"2026.08.27"},"mock":True,"test_timeout":0}
    job = JobStore(root).create(req)
    run_job(root, job["job_id"])
    result = json.loads((root / "runs" / job["job_id"] / "result.json").read_text(encoding="utf-8"))
    assert (root / "runs" / job["job_id"] / "compiled.ex5").read_bytes() == a.read_bytes()
    assert result["build_input"]["sha256"] == hashlib.sha256(a.read_bytes()).hexdigest()
    manifest = json.loads((root / "runs" / job["job_id"] / "build-input-manifest.json").read_text(encoding="utf-8"))
    assert manifest["workspace_binary_conformance"] == "DIVERGED"


def test_tip026_concurrent_same_destination_is_serialized(tmp_path: Path):
    root = _root(tmp_path)
    a = _ex5(tmp_path, "a.ex5", b"A" * 1000)
    b = _ex5(tmp_path, "b.ex5", b"B" * 1000)
    barrier = threading.Barrier(2)
    outputs, errors = [], []
    guard = threading.Lock()

    def go(path: Path):
        try:
            barrier.wait(timeout=2)
            out = ToolFacade(root)._import_ex5_local_for_qualification("BD", path, "Experts/race.ex5")
            with guard: outputs.append(out)
        except Exception as exc:
            with guard: errors.append(exc)

    threads = [threading.Thread(target=go, args=(a,)), threading.Thread(target=go, args=(b,))]
    for t in threads: t.start()
    for t in threads: t.join(5)
    assert len(outputs) == 1
    assert len(errors) == 1
    assert "DESTINATION_CONFLICT" in str(errors[0])
    dest = root / "workspaces" / "BD" / "Experts" / "race.ex5"
    assert dest.read_bytes() in {a.read_bytes(), b.read_bytes()}


def test_tip026_binary_ref_workspace_path_binding_is_strict(tmp_path: Path):
    root = _root(tmp_path)
    source = _ex5(tmp_path, "a.ex5", b"abc123")
    manager = BinaryIngressManager(root)
    out = manager.import_local_file("BD", source, "Experts/a.ex5")
    with pytest.raises(ValueError, match="BUILD_INPUT_REFERENCE_INVALID"):
        manager.resolve_for_launch("BD", "Experts/other.ex5", out["ea_binary_ref"])


def test_tip026_imported_ex5_mock_job_bypasses_compile_and_keeps_provenance(tmp_path: Path):
    root = _root(tmp_path)
    payload = b"EX5-BINARY-ONLY" * 100
    source = _ex5(tmp_path, "binary.ex5", payload)
    facade = ToolFacade(root)
    imported = facade._import_ex5_local_for_qualification("BD", source, "Experts/binary.ex5")
    request = {
        "workspace": "BD", "ea": "Experts/binary.ex5", "ea_binary_ref": imported["ea_binary_ref"],
        "terminal": "MT5-2", "preset": "smoke", "set_file": "Sets/default.set",
        "overrides": {"from_date": "2026.08.26", "to_date": "2026.08.27"},
        "mock": True, "test_timeout": 0,
    }
    job = JobStore(root).create(request)
    run_job(root, job["job_id"])
    result = json.loads((root / "runs" / job["job_id"] / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "PASSED"
    assert result["compile"]["status"] == "NOT_REQUIRED"
    assert result["compile"]["source"] == "imported_ex5"
    assert result["build_input"]["type"] == "IMPORTED_EX5"
    assert result["build_input"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["strategy"]["build_input_type"] == "IMPORTED_EX5"
    assert result["strategy"]["binary_sha256"] == hashlib.sha256(payload).hexdigest()
    assert (root / "runs" / job["job_id"] / "compiled.ex5").read_bytes() == payload
    manifest = json.loads((root / "runs" / job["job_id"] / "build-input-manifest.json").read_text(encoding="utf-8"))
    assert manifest["main_source"] is None
    assert manifest["build_input_source"] == "IMPORTED_EX5"
    assert manifest["imported_ex5"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["imported_ex5"]["source"] == "WINDOWS_NATIVE_QUALIFICATION_FILE"


def test_tip026_terminal_stage_byte_identity(tmp_path: Path):
    root = _root(tmp_path)
    payload = b"EX5-EXECUTION" * 100
    source = _ex5(tmp_path, "execution.ex5", payload)
    manager = BinaryIngressManager(root)
    imported = manager.import_local_file("BD", source, "Experts/sub/execution.ex5")
    binding = manager.resolve_for_launch("BD", "Experts/sub/execution.ex5", imported["ea_binary_ref"])
    deployed = manager.stage_for_terminal(binding, "MT5-2", terminal_build_at_execution=6182)
    assert deployed["terminal_inventory_build"] == 6140
    assert deployed["terminal_build_at_execution"] == 6182
    assert deployed["ea_sha256_at_execution"] == imported["sha256"]
    assert deployed["ea_bytes_at_execution"] == len(payload)
    assert Path(deployed["deployed_path"]).read_bytes() == payload
    assert manager.verify_terminal_stage(deployed)["post_verify_sha256"] == imported["sha256"]


def test_tip026_download_host_policy_is_narrow():
    assert _trusted_download_host("files.oaiusercontent.com")
    assert _trusted_download_host("api.openai.com")
    assert _trusted_download_host("oaisdmntprus.blob.core.windows.net")
    assert not _trusted_download_host("example.com")
    assert not _trusted_download_host("attacker.blob.core.windows.net")


def test_tip026_mcp_surface_has_file_param_metadata_and_hidden_context(monkeypatch, tmp_path: Path):
    class FakeContext:
        pass

    class FakeModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeMCPServer:
        def __init__(self, name, **kwargs):
            self.name = name
            self.tools = {}
            self.tool_meta = {}
        def tool(self, **kwargs):
            def deco(fn):
                self.tools[fn.__name__] = fn
                self.tool_meta[fn.__name__] = kwargs
                return fn
            return deco
        def resource(self, uri, **kwargs):
            def deco(fn): return fn
            return deco

    server_mod = types.ModuleType("mcp.server.mcpserver")
    server_mod.MCPServer = FakeMCPServer
    server_mod.Context = FakeContext
    types_mod = types.ModuleType("mcp.types")
    for name in ("CallToolResult", "ResourceLink", "TextContent", "ToolAnnotations"):
        setattr(types_mod, name, FakeModel)
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", server_mod)
    monkeypatch.setitem(sys.modules, "mcp.types", types_mod)

    from vibemql5.adapters.mcp import create_server
    root = _root(tmp_path)
    server = create_server(root, transport="stdio")
    assert len(server.tools) == 67
    assert set(server.tools) == set(MCP_TOOL_NAMES)
    assert server.tool_meta["import_ex5"]["meta"] == {"openai/fileParams": ["file"]}
    ann = server.tool_meta["import_ex5"]["annotations"]
    assert ann.read_only_hint is False
    assert ann.idempotent_hint is True
    assert ann.open_world_hint is True
    import_sig = __import__("inspect").signature(server.tools["import_ex5"])
    launch_sig = __import__("inspect").signature(server.tools["launch_test"])
    assert "ctx" in import_sig.parameters
    assert "file" in import_sig.parameters
    assert "ea_binary_ref" in launch_sig.parameters

def test_tip026_mcp_receipt_is_truthful_and_does_not_change_binding_identity(tmp_path: Path):
    root = _root(tmp_path)
    payload = b"MCP-FILE-PARAM-EX5" * 100
    source = _ex5(tmp_path, "mcp.ex5", payload)
    manager = BinaryIngressManager(root)
    local = manager.import_local_file("BD", source, "Experts/mcp.ex5")
    mcp = manager._import_temp(
        "BD", source, "Experts/mcp.ex5", local["sha256"], False,
        source="MCP_FILE_IMPORT", source_file_id="file_live_connector_123",
        source_file_name="mcp.ex5", mime_type="application/octet-stream",
        mutation_operation_id="MUT-" + "A" * 16,
    )
    assert mcp["ea_binary_ref"] == local["ea_binary_ref"]
    provenance = manager.import_provenance(mcp["ea_binary_ref"])
    assert provenance["source"] == "MCP_FILE_IMPORT"
    assert provenance["source_file_id"] == "file_live_connector_123"
    assert provenance["receipt_count"] == 2

    req = {
        "workspace":"BD", "ea":"Experts/mcp.ex5", "ea_binary_ref":mcp["ea_binary_ref"],
        "terminal":"MT5-2", "preset":"smoke", "set_file":"Sets/default.set",
        "overrides":{"from_date":"2026.08.26","to_date":"2026.08.27"}, "mock":True, "test_timeout":0,
    }
    job = JobStore(root).create(req)
    run_job(root, job["job_id"])
    manifest = json.loads((root / "runs" / job["job_id"] / "build-input-manifest.json").read_text(encoding="utf-8"))
    assert manifest["imported_ex5"]["source"] == "MCP_FILE_IMPORT"
    assert manifest["imported_ex5"]["ingress_provenance"]["source_file_id"] == "file_live_connector_123"
