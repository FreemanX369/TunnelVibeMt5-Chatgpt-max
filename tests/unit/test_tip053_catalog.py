from __future__ import annotations

import hashlib

from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES


def test_tip053_tool_catalog_is_self_consistent():
    assert MCP_TOOL_COUNT == len(MCP_TOOL_NAMES) == 85
    expected = hashlib.sha256(("\n".join(MCP_TOOL_NAMES) + "\n").encode("utf-8")).hexdigest()
    assert MCP_TOOL_CATALOG_SHA256 == expected
    assert len(set(MCP_TOOL_NAMES)) == len(MCP_TOOL_NAMES)


def test_tip053_required_new_tools_are_catalogued():
    assert {
        "describe_capabilities",
        "backend_start_test_run",
        "backend_get_test_run",
        "get_symbol_snapshot",
        "copy_rates",
        "copy_ticks",
    } <= set(MCP_TOOL_NAMES)
