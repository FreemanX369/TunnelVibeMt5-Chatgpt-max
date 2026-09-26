"""TIP-043: capture still returns MCP ImageContent and advertises its inline viewer."""

from __future__ import annotations

import base64
import json

from vibemql5.adapters.live_chart_widget import (
    LIVE_CHART_WIDGET_HTML,
    LIVE_CHART_WIDGET_URI,
)
from vibemql5.adapters.mcp import create_server
from vibemql5.core.facade import ToolFacade
from vibemql5.core.live_terminal_windows import _png_rgb


def test_capture_wires_downloadable_inline_png_to_the_same_image_content(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    png = _png_rgb(32, 32, bytes([0, 1, 2, 0]) * 1024)
    monkeypatch.setattr(ToolFacade, "reconcile_cancelled_jobs", lambda self, **_kw: {})
    def fake_live_capture(self, operation, fn):
        from types import SimpleNamespace
        return fn(SimpleNamespace(capture=lambda chart_id, aspect_ratio: (
            {"alias": "MT5-2", "chart": {"chart_id": chart_id, "symbol": "XAUUSDm", "timeframe": "M1"},
             "mime_type": "image/png", "bytes": len(png), "image_width": 32, "image_height": 32,
             "aspect_ratio": aspect_ratio}, png,
        )))
    monkeypatch.setattr(ToolFacade, "_observe_live", fake_live_capture)
    server = create_server(tmp_path, transport="stdio")
    assert len(server._tool_manager._tools) == 79
    tool = server._tool_manager._tools["capture_live_chart"]
    assert tool.meta["ui"]["resourceUri"] == LIVE_CHART_WIDGET_URI
    assert tool.meta["openai/outputTemplate"] == LIVE_CHART_WIDGET_URI
    assert tool.parameters["properties"]["aspect_ratio"]["default"] == "16:9"

    widget = server._resource_manager._resources[LIVE_CHART_WIDGET_URI]
    assert widget.mime_type == "text/html;profile=mcp-app"
    assert widget.fn() == LIVE_CHART_WIDGET_HTML

    result = tool.fn(ctx=object(), chart_id=67328)
    assert result.is_error is False
    assert [block.type for block in result.content] == ["text", "image", "resource_link"]
    assert result.content[1].mime_type == "image/png"
    assert base64.b64decode(result.content[1].data) == png
    assert result.structured_content["aspect_ratio"] == "16:9"
    assert result.content[2].uri == result.structured_content["file_export"]["uri"]
    assert "iVBOR" not in result.content[0].text


def test_viewer_does_not_fetch_or_persist_chart_bytes():
    html = LIVE_CHART_WIDGET_HTML
    assert "ui/notifications/tool-result" in html
    assert "toolResponseMetadata" in html
    assert "mcp_tool_result" in html
    assert "data:image/png;base64," in html
    assert '$("download").download = name' in html
    for forbidden in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "console."):
        assert forbidden not in html
