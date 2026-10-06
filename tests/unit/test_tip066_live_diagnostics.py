"""Finite legacy diagnostics at the actual MCP SDK invocation boundary."""
from __future__ import annotations

import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.types import CallToolRequestParams

from vibemql5.adapters.mcp import create_server
from vibemql5.contracts import MCP_TOOL_NAMES
from vibemql5.core.concurrency import actor_scope, current_actor
from vibemql5.core.facade import ToolFacade
from vibemql5.core.native_ownership import OwnershipBlocked

OPERATIONS = ("get_terminal_live_state", "get_account_snapshot", "inspect_terminal")
REASONS = (
    "FIXED_TERMINAL_NOT_RUNNING",
    "MT5_LIVE_IPC_INITIALIZE_FAILED",
    "MT5_LIVE_TERMINAL_INFO_UNAVAILABLE",
    "MT5_LIVE_TERMINAL_BINDING_MISMATCH",
    "MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE",
)
SECRET = "password=DO_NOT_EXPOSE_ACCOUNT_OR_PATH"


@pytest.fixture
def server(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/terminals.json").write_text('{"terminals": []}')
    monkeypatch.setattr(ToolFacade, "reconcile_cancelled_jobs", lambda *_args, **_kw: {})
    return create_server(tmp_path, transport="stdio")


def call(server, operation, arguments=None):
    return asyncio.run(server.call_tool(operation, arguments or {}, context=SimpleNamespace()))


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("reason", REASONS)
def test_finite_live_failure_survives_actual_sdk(server, monkeypatch, operation, reason):
    original = RuntimeError(reason)
    seen = []

    def fail(*_args, **_kwargs):
        seen.append(current_actor())
        raise original

    monkeypatch.setattr(ToolFacade, operation, fail)
    before = current_actor()
    with pytest.raises(ToolError) as direct:
        server._tool_manager._tools[operation].fn(ctx=SimpleNamespace())
    assert direct.value.__cause__ is original
    assert str(direct.value) == reason
    assert current_actor() == before
    with pytest.raises(ToolError) as dispatched:
        call(server, operation)
    assert type(dispatched.value) is ToolError
    assert str(dispatched.value) == f"Error executing tool {operation}: {reason}"
    assert seen and all(actor["operation"] == operation and not actor["security_identity"] for actor in seen)
    assert current_actor() == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("error", [
    RuntimeError(SECRET),
    RuntimeError("MT5_LIVE_IPC_INITIALIZE_FAILED:" + SECRET),
    ValueError(SECRET),
    TimeoutError("NATIVE_BUSY:" + SECRET),
    OwnershipBlocked("UNKNOWN"),
    RuntimeError("MT5_CAPABLE_RUNTIME_REQUIRED"),
])
def test_other_failures_remain_original_and_sdk_masked(server, monkeypatch, operation, error):
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(ToolFacade, operation, fail)
    with actor_scope({"operation": "PARENT", "security_identity": False}) as parent:
        with pytest.raises(type(error)) as direct:
            server._tool_manager._tools[operation].fn(ctx=SimpleNamespace())
        assert direct.value is error
        assert current_actor() == parent
        with pytest.raises(UnexpectedToolError) as dispatched:
            call(server, operation)
        assert dispatched.value.__cause__ is error
        assert str(dispatched.value) == f"Error executing tool {operation}"
        assert SECRET not in str(dispatched.value)
        assert current_actor() == parent


@pytest.mark.parametrize("operation", ["list_live_charts", "read_terminal_journal"])
def test_known_reason_outside_selected_reads_is_not_converted(server, monkeypatch, operation):
    original = RuntimeError("MT5_LIVE_IPC_INITIALIZE_FAILED")

    def fail(*_args, **_kwargs):
        raise original

    monkeypatch.setattr(ToolFacade, operation, fail)
    with pytest.raises(RuntimeError) as direct:
        server._tool_manager._tools[operation].fn(ctx=SimpleNamespace())
    assert direct.value is original
    with pytest.raises(UnexpectedToolError) as dispatched:
        call(server, operation)
    assert dispatched.value.__cause__ is original


@pytest.mark.parametrize("operation,arguments", [
    ("get_terminal_live_state", {"target": 7}),
    ("get_account_snapshot", {"target": ["bad"]}),
    ("inspect_terminal", {"include_logs": {"bad": "argument"}}),
])
def test_invalid_arguments_still_fail_sdk_validation(server, monkeypatch, operation, arguments):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Facade must not run for an invalid SDK argument")

    monkeypatch.setattr(ToolFacade, operation, unexpected)
    with pytest.raises(ToolError) as dispatched:
        call(server, operation, arguments)
    assert type(dispatched.value) is ToolError
    assert "validation error" in str(dispatched.value)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_success_preserves_payload_and_restores_actor(server, monkeypatch, operation):
    payload = {"terminal": {"alias": "MT5-2", "connected": False}, "account": None}

    def success(*_args, **_kwargs):
        assert current_actor()["operation"] == operation
        return payload

    monkeypatch.setattr(ToolFacade, operation, success)
    with actor_scope({"operation": "PARENT", "security_identity": False}) as parent:
        assert server._tool_manager._tools[operation].fn(ctx=SimpleNamespace()) is payload
        result = call(server, operation)
        assert not result.is_error and result.structured_content == payload
        assert current_actor() == parent


@pytest.mark.parametrize("operation", OPERATIONS[:2])
def test_routed_target_stays_denied_without_legacy_or_native_call(server, monkeypatch, operation):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Routed denial must not observe the legacy terminal or start native work")

    monkeypatch.setattr(ToolFacade, "_observe_live", unexpected)
    target = {"schema": "fleet.target/1", "device_id": "dev_" + "a" * 32,
              "terminal_id": "term_" + "b" * 32, "terminal_generation": 1, "route_generation": 1}
    result = call(server, operation, {"target": target})
    answer = result.structured_content
    assert answer["schema"] == "fleet.read/1" and answer["status"] == "FAILED"
    assert answer["reason_code"] == "ROUTED_NATIVE_NOT_ENABLED"
    assert answer["ownership"]["status"] == "NOT_ACQUIRED"
    assert answer["terminal"] is None and answer["account"] is None


def test_catalog_and_all_input_output_schemas_match_accepted_parent(server):
    tools = server._tool_manager._tools
    assert len(tools) == 85 and set(tools) == set(MCP_TOOL_NAMES)
    schemas = {name: {"input": tool.parameters, "output": tool.output_schema} for name, tool in tools.items()}
    digest = hashlib.sha256(json.dumps(schemas, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == "3e17166f81acf897aa3de3c55964e117923897c5658391de37d528c40d234f06"


@pytest.mark.parametrize("kind", ["anticipated", "unexpected", "invalid_arguments"])
def test_protocol_handler_returns_safe_error_result(server, monkeypatch, kind):
    operation = "get_terminal_live_state"
    reason = "MT5_LIVE_IPC_INITIALIZE_FAILED"

    def fail(*_args, **_kwargs):
        if kind == "invalid_arguments":
            pytest.fail("Invalid arguments must not reach the facade")
        raise RuntimeError(reason if kind == "anticipated" else SECRET)

    monkeypatch.setattr(ToolFacade, operation, fail)
    ctx = ServerRequestContext(session=SimpleNamespace(), lifespan_context={},
                               protocol_version="2025-11-25", method="tools/call", request_id=66)
    params = CallToolRequestParams(name=operation, arguments={"target": 7} if kind == "invalid_arguments" else {})
    result = asyncio.run(server._handle_call_tool(ctx, params))
    assert result.is_error and result.structured_content is None
    assert len(result.content) == 1 and result.content[0].type == "text"
    text = result.content[0].text
    assert SECRET not in text
    if kind == "anticipated":
        assert text == f"Error executing tool {operation}: {reason}"
    elif kind == "unexpected":
        assert text == f"Error executing tool {operation}"
    else:
        assert "validation error" in text
