from __future__ import annotations

import inspect
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

from vibemql5.core.artifacts import ArtifactManager
from vibemql5.core.facade import ToolFacade
from vibemql5.core.jobs import JobStore
from vibemql5.core.project_sessions import ProjectSessionManager


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "VibeMQL5"
    (root / "workspaces" / "demo" / "Experts").mkdir(parents=True)
    (root / "config" / "presets").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {"disk_warning_gb": 0.001, "disk_block_gb": 0.0001, "min_free_memory_mb": 1},
        "retention": {"completed_jobs": 0},
        "jobs": {"max_concurrent": 1},
        "defaults": {"terminal": "MT5-2"},
        "terminal_policy": {"alias": "MT5-2", "mode": "fixed"},
    }), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(
        json.dumps({"terminals": []}), encoding="utf-8"
    )
    (root / "pyproject.toml").write_text("x", encoding="utf-8")
    (root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5").write_bytes(
        b"#property strict\r\nvoid OnTick(){}\r\n"
    )
    return root


def test_tip028_project_session_operation_retry_conflict_and_sha_cas(tmp_path: Path):
    root = _root(tmp_path)
    manager = ProjectSessionManager(root)
    created = manager.create("TIP028", "demo", "Experts/DemoEA.mq5", active_goal="bind")

    first = manager.update(
        "TIP028",
        "REV-000001",
        active_goal="verify",
        operation_id="TIP028-SESSION-UPDATE-1",
        expected_revision_sha256=created["revision_sha256"],
    )
    retry = manager.update(
        "TIP028",
        "REV-000001",
        active_goal="verify",
        operation_id="TIP028-SESSION-UPDATE-1",
        expected_revision_sha256=created["revision_sha256"],
    )
    assert first["revision_id"] == retry["revision_id"] == "REV-000002"
    assert retry["revision_sha256"] == first["revision_sha256"]
    assert retry["idempotent_recovered"] is True
    assert first["session_update_request_sha256"]

    with pytest.raises(ValueError, match="PROJECT_SESSION_OPERATION_CONFLICT"):
        manager.update(
            "TIP028",
            "REV-000001",
            active_goal="different-request",
            operation_id="TIP028-SESSION-UPDATE-1",
            expected_revision_sha256=created["revision_sha256"],
        )

    with pytest.raises(ValueError, match="PROJECT_SESSION_VERSION_CONFLICT"):
        manager.update(
            "TIP028",
            "REV-000002",
            active_goal="stale-sha",
            operation_id="TIP028-SESSION-UPDATE-2",
            expected_revision_sha256="0" * 64,
        )


def test_tip028_facade_forwards_session_and_launch_idempotency(monkeypatch, tmp_path: Path):
    from vibemql5.core import facade as facade_module

    root = _root(tmp_path)
    facade = ToolFacade(root)
    seen: dict[str, object] = {}

    def fake_update(project_id, expected_revision, **kwargs):
        seen["session"] = (project_id, expected_revision, kwargs)
        return {"revision_id": "REV-000002"}

    monkeypatch.setattr(facade.project_sessions, "update", fake_update)
    facade.update_project_session(
        "TIP028",
        "REV-000001",
        active_goal="verify",
        operation_id="TIP028-SESSION-UPDATE-1",
        expected_revision_sha256="a" * 64,
    )
    assert seen["session"] == (
        "TIP028",
        "REV-000001",
        {
            "active_goal": "verify",
            "decision_refs": None,
            "phase": None,
            "checkpoint_id": None,
            "baseline_job_id": None,
            "last_job_id": None,
            "operation_id": "TIP028-SESSION-UPDATE-1",
            "expected_revision_sha256": "a" * 64,
        },
    )

    calls: list[tuple[dict, str]] = []

    def fake_launch(request, operation_id=""):
        calls.append((request, operation_id))
        return {"job_id": "BT-TEST", "state": "QUEUED"}

    monkeypatch.setattr(facade_module, "normalize_tester_request", lambda *args, **kwargs: {})
    monkeypatch.setattr(facade.jobs, "launch_test", fake_launch)
    facade.launch_test(
        "demo",
        "Experts/DemoEA.mq5",
        operation_id="TIP028-LAUNCH-1",
    )
    facade.launch_test("demo", "Experts/DemoEA.mq5")
    assert calls[0][1] == "TIP028-LAUNCH-1"
    assert calls[1][1] == ""
    assert calls[0][0]["terminal"] == "MT5-2"


def test_tip028_job_reservation_survives_retry_conflict_and_materialization_gap(tmp_path: Path):
    root = _root(tmp_path)
    store = JobStore(root)
    request = {
        "workspace": "demo",
        "ea": "Experts/DemoEA.mq5",
        "terminal": "MT5-2",
        "preset": "smoke",
    }

    first = store.reserve(request, "TIP028-JOB-1")
    retry = store.reserve(request, "TIP028-JOB-1")
    assert retry["job"]["job_id"] == first["job"]["job_id"]
    assert retry["recovered"] is True

    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_CONFLICT"):
        store.reserve({**request, "preset": "validation"}, "TIP028-JOB-1")

    job_id = first["job"]["job_id"]
    shutil.rmtree(root / "runs" / job_id)
    recovered = store.reserve(request, "TIP028-JOB-1")
    assert recovered["job"]["job_id"] == job_id
    assert (root / "runs" / job_id / "job.json").is_file()
    assert (root / "runs" / job_id / "request.json").is_file()


def test_tip028_retention_preserves_pinned_evidence_anchor(tmp_path: Path):
    root = _root(tmp_path)
    for job_id, pinned in (("BT-PINNED", True), ("BT-UNPINNED", False)):
        run = root / "runs" / job_id
        run.mkdir()
        (run / "job.json").write_text(json.dumps({
            "job_id": job_id,
            "state": "PASSED",
            "updated_at": "2026-09-13T00:00:00Z",
            "pinned": pinned,
        }), encoding="utf-8")

    result = ArtifactManager(root).retain()
    assert (root / "runs" / "BT-PINNED").is_dir()
    assert not (root / "runs" / "BT-UNPINNED").exists()
    assert result["removed"] == ["BT-UNPINNED"]


def test_tip028_mcp_exposes_optional_binding_parameters(monkeypatch, tmp_path: Path):
    class FakeContext:
        pass

    class FakeModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeMCPServer:
        def __init__(self, name, **kwargs):
            self.tools = {}
            self.resources = {}

        def tool(self, **kwargs):
            def decorator(fn):
                inspect.signature(fn, eval_str=True)
                self.tools[fn.__name__] = fn
                return fn
            return decorator

        def resource(self, uri, **kwargs):
            def decorator(fn):
                self.resources[uri] = fn
                return fn
            return decorator

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

    server = create_server(_root(tmp_path), transport="stdio")
    update = inspect.signature(server.tools["update_project_session"]).parameters
    launch = inspect.signature(server.tools["launch_test"]).parameters
    assert update["operation_id"].default == ""
    assert update["expected_revision_sha256"].default == ""
    assert launch["operation_id"].default == ""
    assert len(server.tools) == 67



def test_tip032_mcp_sdk_publishes_binding_parameters(tmp_path: Path):
    from vibemql5.adapters.mcp import create_server

    server = create_server(_root(tmp_path), transport="stdio")
    tools = server._tool_manager._tools
    update_schema = tools["update_project_session"].parameters
    launch_schema = tools["launch_test"].parameters
    update_v2_schema = tools["update_project_session_v2"].parameters
    launch_v2_schema = tools["launch_test_v2"].parameters

    assert {"operation_id", "expected_revision_sha256"} <= set(
        update_schema["properties"]
    )
    assert "operation_id" in launch_schema["properties"]
    assert {"operation_id", "expected_revision_sha256"} <= set(
        update_v2_schema["required"]
    )
    assert "operation_id" in launch_v2_schema["required"]

def test_tip032_project_session_resume_detects_source_drift(tmp_path: Path):
    root = _root(tmp_path)
    manager = ProjectSessionManager(root)
    created = manager.create(
        "TIP032",
        "demo",
        "Experts/DemoEA.mq5",
        active_goal="full qualification",
        phase="VERIFY",
    )

    source_path = root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5"
    source_path.write_bytes(b"#property strict\r\nvoid OnTick(){/*drift*/}\r\n")

    resumed = manager.resume("TIP032")
    assert resumed["resume_safe"] is False
    assert "SOURCE_CHANGED_SINCE_SESSION_REVISION" in resumed["stale_reasons"]
    assert resumed["source"]["match_session_revision"] is False
    assert resumed["session"]["source_sha256"] == created["source_sha256"]
