from __future__ import annotations

import hashlib
import inspect
import json
import sys
import threading
import time
import types
from pathlib import Path

import pytest

import vibemql5
from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES
from vibemql5.core.concurrency import (
    ConcurrencyManager,
    acquire_native_execution,
    actor_from_mcp_context,
    actor_scope,
)
from vibemql5.core.facade import ToolFacade
from vibemql5.worker import acquire_lock as worker_acquire_lock

EXPECTED_CATALOG = "a0d2240862369aaf67039b34921bda2b0eeb3aba7e9dae1f4c71c44fd5c40106"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "VibeMQL5"
    (root / "workspaces" / "demo" / "Experts").mkdir(parents=True)
    (root / "config" / "presets").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(
        json.dumps({
            "resource_guard": {"disk_warning_gb": 0.001, "disk_block_gb": 0.0001, "min_free_memory_mb": 1},
            "retention": {"completed_jobs": 20},
            "jobs": {"max_concurrent": 1, "compile_timeout_seconds": 120},
            "defaults": {"terminal": "MT5-2"},
            "terminal_policy": {"alias": "MT5-2", "mode": "fixed"},
        }), encoding="utf-8"
    )
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    (root / "config" / "build-provenance.json").write_text(
        json.dumps({
            "schema_version": "1.0", "bridge_name": "VibeMQL5 Bridge",
            "bridge_version": "0.2.27", "bridge_build": "TIP-025",
            "project_session_schema": "1.0", "iteration_schema": "1.0",
            "mcp_tool_count": 42, "result_schema": "1.3",
            "multi_client_concurrency_schema": "1.0",
        }), encoding="utf-8"
    )
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5").write_bytes(
        b"#property strict\r\nvoid OnTick(){}\r\n"
    )
    return root


class _Connection:
    protocol_version = "2026-07-28"


class _RequestContext:
    request_id = "req-123"
    meta = {
        "io.modelcontextprotocol/clientInfo": {"name": "ChatGPT", "version": "test"}
    }


class _Ctx:
    request_context = _RequestContext()
    connection = _Connection()
    session_id = None


def test_tip024_identity_and_tool_catalog_are_preserved():
    assert vibemql5.__version__ == "0.2.38"
    assert MCP_TOOL_COUNT == 79
    assert MCP_TOOL_CATALOG_SHA256 == EXPECTED_CATALOG
    assert hashlib.sha256(("\n".join(MCP_TOOL_NAMES) + "\n").encode()).hexdigest() == EXPECTED_CATALOG


def test_tip024_actor_is_provenance_not_security_identity():
    actor = actor_from_mcp_context(_Ctx(), transport="stdio")
    assert actor["source"] == "mcp_request_context"
    assert actor["client_info"] == {"name": "ChatGPT", "version": "test"}
    assert actor["request_id"] == "req-123"
    assert actor["protocol_version"] == "2026-07-28"
    assert actor["session_id"] is None
    assert actor["attribution_strength"] == "REQUEST_WORKSTREAM_ONLY"
    assert actor["security_identity"] is False


def test_tip024_global_mutation_lock_serializes_threads(tmp_path: Path):
    root = _root(tmp_path)
    manager = ConcurrencyManager(root)
    active = 0
    max_active = 0
    order: list[str] = []
    guard = threading.Lock()
    first_entered = threading.Event()

    def run(name: str, hold: float):
        nonlocal active, max_active
        with manager.mutation(name, resource="demo:Experts/DemoEA.mq5", wait_seconds=3):
            with guard:
                active += 1
                max_active = max(max_active, active)
                order.append(name)
            if name == "A":
                first_entered.set()
            time.sleep(hold)
            with guard:
                active -= 1

    a = threading.Thread(target=run, args=("A", 0.15))
    b = threading.Thread(target=run, args=("B", 0.01))
    a.start(); assert first_entered.wait(1)
    b.start(); a.join(2); b.join(2)
    assert not a.is_alive() and not b.is_alive()
    assert max_active == 1
    assert order == ["A", "B"]


def test_tip024_native_fifo_serializes_direct_and_worker_lease(tmp_path: Path):
    root = _root(tmp_path)
    first = acquire_native_execution(root, "DIRECT-A", kind="direct_compile", wait_seconds=2)
    acquired: list[str] = []
    started = threading.Event()

    def worker_waiter():
        started.set()
        lease = worker_acquire_lock(root, "JOB-B", wait_seconds=2, actor={"client_key": "b"})
        try:
            acquired.append(lease.operation_id)
        finally:
            lease.unlink(missing_ok=True)

    t = threading.Thread(target=worker_waiter)
    t.start(); assert started.wait(1)
    time.sleep(0.1)
    assert acquired == []
    first.release()
    t.join(2)
    assert acquired == ["JOB-B"]
    assert not (root / "runs" / ".active.lock").exists()


def test_tip024_native_fifo_order_for_multiple_waiters(tmp_path: Path):
    root = _root(tmp_path)
    held = acquire_native_execution(root, "HOLD", kind="test", wait_seconds=2)
    order: list[str] = []

    def waiter(name: str):
        lease = acquire_native_execution(root, name, kind="test", wait_seconds=3)
        try:
            order.append(name)
            time.sleep(0.03)
        finally:
            lease.release()

    b = threading.Thread(target=waiter, args=("B",))
    c = threading.Thread(target=waiter, args=("C",))
    b.start(); time.sleep(0.04); c.start(); time.sleep(0.08)
    held.release(); b.join(2); c.join(2)
    assert order == ["B", "C"]


def test_tip024_queue_sequence_allocator_is_monotonic_across_leases(tmp_path: Path):
    root = _root(tmp_path)
    a = acquire_native_execution(root, "SEQ-A", kind="test", wait_seconds=2)
    a.release()
    b = acquire_native_execution(root, "SEQ-B", kind="test", wait_seconds=2)
    b.release()
    state = json.loads((root / "state" / "concurrency" / "native-sequence.json").read_text(encoding="utf-8"))
    assert state["namespace"] == "native"
    assert state["sequence"] == 2


def test_tip024_dead_pid_native_lock_is_recovered_fail_closed_for_live_owner(tmp_path: Path):
    root = _root(tmp_path)
    lock = root / "runs" / ".active.lock"
    lock.write_text(json.dumps({"pid": 99999999, "token": "stale", "operation_id": "old"}), encoding="utf-8")
    lease = acquire_native_execution(root, "NEW", kind="test", wait_seconds=2)
    try:
        assert json.loads(lock.read_text(encoding="utf-8"))["operation_id"] == "NEW"
    finally:
        lease.release()
    assert not lock.exists()


def test_tip024_existing_source_requires_cas_and_checkpoint(tmp_path: Path):
    root = _root(tmp_path)
    facade = ToolFacade(root)
    src = facade.get_source_hash("demo", "Experts/DemoEA.mq5")
    with pytest.raises(ValueError, match="MULTI_CLIENT_CAS_REQUIRED"):
        facade.write_source("demo", "Experts/DemoEA.mq5", "void OnTick(){}")
    with pytest.raises(ValueError, match="MULTI_CLIENT_CHECKPOINT_REQUIRED"):
        facade.write_source("demo", "Experts/DemoEA.mq5", "void OnTick(){}", src["sha256"])
    with pytest.raises(ValueError, match="MULTI_CLIENT_CAS_REQUIRED"):
        facade.apply_patch("demo", "Experts/DemoEA.mq5", [{"old": "OnTick", "new": "OnTick"}])
    with pytest.raises(ValueError, match="MULTI_CLIENT_CAS_REQUIRED"):
        facade.restore_checkpoint("demo", "CP-20260101-000000-AAAAAAAAAAAA")


def test_tip024_stale_second_client_cannot_overwrite_first_client(tmp_path: Path):
    root = _root(tmp_path)
    facade = ToolFacade(root)
    before = facade.get_source_hash("demo", "Experts/DemoEA.mq5")
    cp = facade.create_checkpoint("demo", "Experts/DemoEA.mq5", "multi-client")
    first = facade.apply_patch(
        "demo", "Experts/DemoEA.mq5",
        [{"old": "void OnTick(){}", "new": "void OnTick(){/*A*/}"}],
        before["sha256"], cp["checkpoint_id"],
    )
    assert first["sha256"] != before["sha256"]
    with pytest.raises(ValueError, match="SOURCE_VERSION_CONFLICT"):
        facade.apply_patch(
            "demo", "Experts/DemoEA.mq5",
            [{"old": "void OnTick(){}", "new": "void OnTick(){/*B*/}"}],
            before["sha256"], cp["checkpoint_id"],
        )
    assert "/*A*/" in facade.read_source("demo", "Experts/DemoEA.mq5")["content"]


def test_tip024_actor_binding_and_audit_do_not_store_source_content(tmp_path: Path):
    root = _root(tmp_path)
    manager = ConcurrencyManager(root)
    actor = actor_from_mcp_context(_Ctx(), transport="stdio")
    with actor_scope(actor):
        manager.note_project_actor("P-A")
        manager.note_iteration_actor("IT-A")
        with manager.mutation("test", resource="demo:Experts/DemoEA.mq5", project_id="P-A"):
            pass
    assert manager.iteration_actor("IT-A")["request_id"] == "req-123"
    audit = manager.audit_path.read_text(encoding="utf-8")
    assert "#property strict" not in audit
    assert "void OnTick" not in audit
    assert "req-123" in audit


def test_tip024_health_and_diagnose_publish_concurrency_contract(tmp_path: Path):
    root = _root(tmp_path)
    facade = ToolFacade(root)
    health = facade.health()
    diag = facade.diagnose()
    assert health["concurrency"]["mode"] == "MULTI_CLIENT_SERIALIZED"
    assert health["concurrency"]["native_mt5_parallelism"] == 1
    assert health["concurrency"]["source_mutation_parallelism"] == 1
    assert health["concurrency"]["attribution"]["authenticated_account_identity"] is False
    assert diag["concurrency"]["mode"] == "MULTI_CLIENT_SERIALIZED"


def test_tip024_mcp_registers_catalog_and_context_is_invisible_contract(monkeypatch, tmp_path: Path):
    class FakeContext:
        pass

    class FakeMCPServer:
        def __init__(self, name, **kwargs):
            self.name = name
            self.instructions = kwargs.get("instructions", "")
            self.tools = {}
            self.resources = {}
        def tool(self, **kwargs):
            def deco(fn):
                self.tools[fn.__name__] = fn
                return fn
            return deco
        def resource(self, uri, **kwargs):
            def deco(fn):
                self.resources[uri] = fn
                return fn
            return deco

    fake_server_mod = types.ModuleType("mcp.server.mcpserver")
    fake_server_mod.MCPServer = FakeMCPServer
    fake_server_mod.Context = FakeContext
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", fake_server_mod)
    types_mod = types.ModuleType("mcp.types")
    class _Model:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    for model_name in ("CallToolResult", "ResourceLink", "TextContent", "ToolAnnotations"):
        setattr(types_mod, model_name, _Model)
    monkeypatch.setitem(sys.modules, "mcp.types", types_mod)

    from vibemql5.adapters.mcp import create_server
    root = _root(tmp_path)
    server = create_server(root, transport="stdio")
    assert set(server.tools) == set(MCP_TOOL_NAMES)
    assert len(server.tools) == 79
    info = server.tools["server_info"]()
    assert info["version"] == "0.2.38"
    assert info["bridge_build"] == "TIP-025"
    assert info["generic_shell_exposed"] is True
    assert info["multi_client_concurrency_schema"] == "1.0"
    assert info["multi_client_mode"] == "SERIALIZED_SHARED_VPS"
    assert info["authenticated_client_identity"] is False
    blocked = server.tools["backend_run_powershell"](FakeContext(), "Get-Date")
    assert blocked["status"] == "BLOCKED"
    assert blocked["payload"]["reason_code"] == "EXPLICIT_CONFIRMATION_REQUIRED"
    for name in ("write_source", "apply_patch", "compile_ea", "launch_test", "cancel_job"):
        sig = inspect.signature(server.tools[name])
        assert "ctx" in sig.parameters
        assert sig.parameters["ctx"].annotation in {FakeContext, "Context"}
    assert "FIFO MT5 execution lease" in server.instructions


def test_tip024_direct_compile_operation_id_has_collision_resistant_suffix():
    source = (Path(__file__).parents[2] / "app" / "vibemql5" / "core" / "facade.py").read_text(encoding="utf-8")
    assert "uuid.uuid4().hex[:8].upper()" in source
    assert "direct_compile_source_guard" in source


def test_tip024_worker_lock_order_and_result_attribution_are_present():
    source = (Path(__file__).parents[2] / "app" / "vibemql5" / "worker.py").read_text(encoding="utf-8")
    mutation_pos = source.index('source_guard_cm = concurrency.mutation(')
    native_pos = source.index('lock = acquire_lock(', mutation_pos)
    compile_pos = source.index('comp = compiler.compile(', native_pos)
    release_pos = source.index('source_guard_cm.__exit__', compile_pos)
    tester_pos = source.index('tester = TesterDriver(root)', release_pos)
    assert mutation_pos < native_pos < compile_pos < release_pos < tester_pos
    assert '"orchestration": {' in source
    assert 'native_execution_wait_seconds' in source
