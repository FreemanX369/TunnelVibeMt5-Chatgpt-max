from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from vibemql5 import __version__
from vibemql5.contracts import MCP_TOOL_COUNT, MCP_TOOL_NAMES
from vibemql5.core.file_export import EXPORT_SCHEMA_VERSION, MAX_EXPORT_BYTES, FileExportManager
from vibemql5.core.jobs import JobStore


def test_tip022f_job_ex5_export_is_byte_exact_hash_bound_and_path_hidden(tmp_path: Path):
    root = tmp_path
    store = JobStore(root)
    job = store.create({"workspace": "BD", "ea": "Experts/EA.mq5", "terminal": "MT5-2"})
    job_id = job["job_id"]
    raw = bytes(range(256)) * 1024
    ex5 = root / "runs" / job_id / "compiled.ex5"
    ex5.write_bytes(raw)

    mgr = FileExportManager(root)
    meta = mgr.prepare("job", job_id, "compiled.ex5")
    assert meta["schema_version"] == EXPORT_SCHEMA_VERSION == "1.0"
    assert meta["delivery"] == "mcp_resource_link"
    assert meta["file_name"] == "compiled.ex5"
    assert meta["bytes"] == len(raw)
    assert meta["sha256"] == hashlib.sha256(raw).hexdigest()
    assert meta["mime_type"] == "application/octet-stream"
    assert str(root) not in json.dumps(meta)
    assert meta["uri"].startswith("vibemql5-export://artifact/")

    token = meta["uri"].rsplit("/", 1)[1]
    returned, rmeta = mgr.read_token(token)
    assert returned == raw
    assert rmeta["sha256"] == meta["sha256"]
    assert rmeta["bytes"] == meta["bytes"]


def test_tip022f_expected_hash_and_stale_link_fail_closed(tmp_path: Path):
    root = tmp_path
    store = JobStore(root)
    job = store.create({"workspace": "BD", "ea": "EA.mq5", "terminal": "MT5-2"})
    job_id = job["job_id"]
    p = root / "runs" / job_id / "compiled.ex5"
    p.write_bytes(b"candidate-v1")
    mgr = FileExportManager(root)

    with pytest.raises(ValueError, match="SHA-256 precondition mismatch"):
        mgr.prepare("job", job_id, "compiled.ex5", expected_sha256="0" * 64)

    meta = mgr.prepare("job", job_id, "compiled.ex5")
    token = meta["uri"].rsplit("/", 1)[1]
    p.write_bytes(b"candidate-v2")
    with pytest.raises(ValueError, match="changed after link creation"):
        mgr.read_token(token)


def test_tip022f_nonimmutable_job_file_requires_terminal_state(tmp_path: Path):
    root = tmp_path
    store = JobStore(root)
    job = store.create({"workspace": "BD", "ea": "EA.mq5", "terminal": "MT5-2"})
    job_id = job["job_id"]
    run = root / "runs" / job_id
    (run / "result.json").write_text('{"status":"partial"}', encoding="utf-8")
    mgr = FileExportManager(root)

    with pytest.raises(ValueError, match="not complete yet"):
        mgr.prepare("job", job_id, "result.json")


def test_tip022f_scoped_evidence_and_exports_accept_only_safe_relative_paths(tmp_path: Path):
    root = tmp_path
    evidence = root / "evidence" / "tip021"
    evidence.mkdir(parents=True)
    good = evidence / "qualification.json"
    good.write_text('{"status":"PASS"}', encoding="utf-8")
    exports = root / "exports"
    exports.mkdir()
    handover = exports / "BD-EA-v1501-T1724-Deep-Audit.md"
    handover.write_text("# audit\n", encoding="utf-8")
    mgr = FileExportManager(root)

    e = mgr.prepare("evidence", "tip021/qualification.json")
    h = mgr.prepare("exports", "BD-EA-v1501-T1724-Deep-Audit.md")
    assert e["mime_type"] == "application/json"
    assert h["mime_type"] == "text/markdown"

    for bad in ("../secret.json", "C:/secret.json", "/secret.json"):
        with pytest.raises((ValueError, FileNotFoundError)):
            mgr.prepare("evidence", bad)


def test_tip022f_symlink_escape_and_sensitive_extension_are_blocked(tmp_path: Path):
    root = tmp_path
    evidence = root / "evidence"
    evidence.mkdir()
    outside = root / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = evidence / "link.json"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    mgr = FileExportManager(root)
    with pytest.raises(ValueError, match="escapes the allowed root"):
        mgr.prepare("evidence", "link.json")

    badext = evidence / "source.mq5"
    badext.write_text("// strategy", encoding="utf-8")
    with pytest.raises(ValueError, match="not exportable"):
        mgr.prepare("evidence", "source.mq5")

    secret = evidence / "api-secret.json"
    secret.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Sensitive-looking filename"):
        mgr.prepare("evidence", "api-secret.json")


def test_tip022f_size_limit_is_fail_closed_without_reading_large_file(tmp_path: Path):
    root = tmp_path
    evidence = root / "evidence"
    evidence.mkdir()
    p = evidence / "large.zip"
    with p.open("wb") as fh:
        fh.truncate(MAX_EXPORT_BYTES + 1)
    with pytest.raises(ValueError, match=str(MAX_EXPORT_BYTES)):
        FileExportManager(root).prepare("evidence", "large.zip")


def test_tip022f_catalog_and_build_version():
    assert __version__ == "0.2.41"
    assert MCP_TOOL_COUNT == 79
    assert MCP_TOOL_NAMES.count("export_file") == 1
    assert MCP_TOOL_NAMES.count("compare_baseline") == 1


def test_tip022f_mcp_adapter_returns_resource_link_and_registers_resource_template():
    source = (Path(__file__).parents[2] / "app" / "vibemql5" / "adapters" / "mcp.py").read_text(encoding="utf-8")
    assert '@server.resource("vibemql5-export://artifact/{token}"' in source
    assert "ResourceLink(" in source
    assert "CallToolResult(" in source
    assert "read_only_hint=True" in source
    assert "open_world_hint=False" in source


def test_tip022f_mcp_sdk_postponed_annotation_types_are_published_before_tool_registration():
    source = (Path(__file__).parents[2] / "app" / "vibemql5" / "adapters" / "mcp.py").read_text(encoding="utf-8")
    publish = source.index('globals().update({')
    registration = source.index('@server.tool(', publish)
    export_signature = source.index(') -> CallToolResult:', registration)
    assert publish < registration < export_signature
    assert '"CallToolResult": CallToolResult' in source[publish:registration]
