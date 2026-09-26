from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from vibemql5.adapters.mcp import create_server
from vibemql5.core.facade import ToolFacade
from vibemql5.core.file_export import FileExportManager
from vibemql5.core.live_chart_archive import archive_chart_png
from vibemql5.core.live_terminal_windows import _png_rgb


def test_one_capture_returns_byte_exact_png_and_reopenable_export(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    png = _png_rgb(32, 32, bytes([0, 1, 2, 0]) * 1024)
    calls = []

    def observe(self, operation, fn):
        def capture(chart_id, aspect_ratio):
            calls.append((chart_id, aspect_ratio))
            return ({"alias": "MT5-2", "chart": {"chart_id": chart_id, "symbol": "XAUUSDm", "timeframe": "M1"},
                     "mime_type": "image/png", "bytes": len(png), "image_width": 32, "image_height": 32,
                     "aspect_ratio": aspect_ratio}, png)
        return fn(SimpleNamespace(capture=capture))

    monkeypatch.setattr(ToolFacade, "reconcile_cancelled_jobs", lambda self, **_kw: {})
    monkeypatch.setattr(ToolFacade, "_observe_live", observe)
    server = create_server(tmp_path, transport="stdio")
    result = server._tool_manager._tools["capture_live_chart"].fn(ctx=object(), chart_id=67352)

    assert calls == [(67352, "16:9")]
    assert [block.type for block in result.content] == ["text", "image", "resource_link"]
    assert base64.b64decode(result.content[1].data) == png
    exported = result.structured_content["file_export"]
    assert exported["mime_type"] == "image/png"
    assert exported["bytes"] == len(png)
    assert exported["sha256"] == hashlib.sha256(png).hexdigest()
    assert result.content[2].uri == exported["uri"]
    assert result.content[2].size == len(png)
    assert (tmp_path / "exports" / exported["source_id"]).read_bytes() == png

    token = exported["uri"].rsplit("/", 1)[1]
    again, proof = FileExportManager(tmp_path).read_token(token)
    assert again == png and proof["sha256"] == exported["sha256"]
    resource = server._resource_manager._templates["vibemql5-export://artifact/{token}"]
    assert resource.fn(token) == png
    later = server._tool_manager._tools["export_file"].fn(
        scope="exports", source_id=exported["source_id"], expected_sha256=exported["sha256"])
    assert later.content[1].uri == exported["uri"]
    assert calls == [(67352, "16:9")]


def test_png_export_is_limited_to_chart_archive_and_stale_links_fail(tmp_path):
    png = _png_rgb(32, 32, bytes([0, 1, 2, 0]) * 1024)
    meta = {"chart": {"chart_id": 67352, "symbol": "XAUUSDm", "timeframe": "M1"}}
    source_id = archive_chart_png(tmp_path, meta, png)
    manager = FileExportManager(tmp_path)
    link = manager.prepare("exports", source_id)
    (tmp_path / "exports" / source_id).write_bytes(png + b"changed")
    with pytest.raises(ValueError, match="changed after link creation"):
        manager.read_token(link["uri"].rsplit("/", 1)[1])

    outside = tmp_path / "exports" / "unrelated.png"
    outside.write_bytes(png)
    with pytest.raises(ValueError, match="not exportable"):
        manager.prepare("exports", "unrelated.png")


def test_archive_is_bounded_and_invalid_png_does_not_create_file(tmp_path, monkeypatch):
    import vibemql5.core.live_chart_archive as archive

    monkeypatch.setattr(archive, "MAX_CHART_FILES", 2)
    png = _png_rgb(32, 32, bytes([0, 1, 2, 0]) * 1024)
    meta = {"chart": {"chart_id": 67352, "symbol": "XAUUSDm", "timeframe": "M1"}}
    first = tmp_path / "exports" / archive_chart_png(tmp_path, meta, png)
    os.utime(first, ns=(1, 1))
    archive_chart_png(tmp_path, meta, png)
    newest = tmp_path / "exports" / archive_chart_png(tmp_path, meta, png)
    assert not first.exists() and newest.read_bytes() == png
    assert len(list((tmp_path / "exports" / "live-charts").glob("*.png"))) == 2
    with pytest.raises(ValueError, match="INVALID_PNG"):
        archive_chart_png(tmp_path, meta, b"not a PNG")
    assert len(list((tmp_path / "exports" / "live-charts").glob("*.png"))) == 2


def test_export_name_collision_preserves_original_bytes(tmp_path, monkeypatch):
    import vibemql5.core.live_chart_archive as archive

    png = _png_rgb(32, 32, bytes([0, 1, 2, 0]) * 1024)
    meta = {"chart": {"chart_id": 67352, "symbol": "XAUUSDm", "timeframe": "M1"}}
    monkeypatch.setattr(archive.uuid, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    path = tmp_path / "exports" / archive_chart_png(tmp_path, meta, png)
    with pytest.raises(FileExistsError):
        archive_chart_png(tmp_path, meta, png)
    assert path.read_bytes() == png
