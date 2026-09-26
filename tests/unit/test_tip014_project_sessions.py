import json
import sys
import types
from pathlib import Path

import pytest

import vibemql5
from vibemql5.adapters.mcp import _runtime_provenance
from vibemql5.core.jobs import JobStore
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.revisions import RevisionManager


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "VibeMQL5"
    (root / "workspaces" / "demo" / "Experts").mkdir(parents=True)
    (root / "config" / "presets").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {"disk_warning_gb": 4, "disk_block_gb": 2, "min_free_memory_mb": 256},
        "retention": {"completed_jobs": 20},
        "jobs": {"max_concurrent": 1},
        "defaults": {"terminal": "MT5-2"},
        "terminal_policy": {"alias": "MT5-2", "mode": "fixed"},
    }), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    (root / "pyproject.toml").write_text("x", encoding="utf-8")
    (root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5").write_bytes(b"#property strict\r\nvoid OnTick(){}\r\n")
    return root


def _job(root: Path, state="PASSED") -> str:
    store = JobStore(root)
    job = store.create({"workspace": "demo", "ea": "Experts/DemoEA.mq5", "terminal": "MT5-2"})
    job["state"] = state
    store.save(job)
    if state == "PASSED":
        (root / "runs" / job["job_id"] / "result.json").write_text(json.dumps({"job_id": job["job_id"], "status": "PASSED"}), encoding="utf-8")
    return job["job_id"]


def test_tip014_version_and_runtime_provenance():
    assert vibemql5.__version__ == "0.2.40"
    p = _runtime_provenance()
    assert p["bridge_build"] == "TIP-044"
    assert p["bridge_version"] == "0.2.40"


def test_create_update_persist_and_revision_chain(tmp_path: Path):
    root = _root(tmp_path)
    cp = RevisionManager(root).create_checkpoint("demo", "Experts/DemoEA.mq5", "tip014")
    baseline = _job(root)
    last_job = _job(root)
    mgr = ProjectSessionManager(root)
    created = mgr.create(
        "EA-T17", "demo", "Experts/DemoEA.mq5",
        active_goal="Audit pyramid logic", decision_refs=["DEC-T17-001"], phase="BUILD",
        checkpoint_id=cp["checkpoint_id"], baseline_job_id=baseline, last_job_id=last_job,
    )
    updated = mgr.update("EA-T17", "REV-000001", active_goal="Verify pyramid logic", phase="VERIFY", decision_refs=["DEC-T17-001", "DEC-T17-002"])
    assert created["revision_id"] == "REV-000001"
    assert updated["revision_id"] == "REV-000002"
    assert updated["previous_revision_sha256"] == created["revision_sha256"]
    again = ProjectSessionManager(root).get("EA-T17")
    assert again["revision_id"] == "REV-000002"
    assert again["decision_refs"] == ["DEC-T17-001", "DEC-T17-002"]


def test_cas_conflict_and_resume_source_staleness(tmp_path: Path):
    root = _root(tmp_path)
    mgr = ProjectSessionManager(root)
    mgr.create("P1", "demo", "Experts/DemoEA.mq5", active_goal="continue")
    mgr.update("P1", "REV-000001", active_goal="new")
    with pytest.raises(ValueError, match="PROJECT_SESSION_VERSION_CONFLICT"):
        mgr.update("P1", "REV-000001", active_goal="stale writer")
    source = root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5"
    source.write_bytes(source.read_bytes() + b"// external change\r\n")
    stale = ProjectSessionManager(root).resume("P1")
    assert stale["resume_safe"] is False
    assert "SOURCE_CHANGED_SINCE_SESSION_REVISION" in stale["stale_reasons"]


def test_checkpoint_job_refs_and_revision_integrity_fail_closed(tmp_path: Path):
    root = _root(tmp_path)
    mgr = ProjectSessionManager(root)
    with pytest.raises(ValueError, match="CHECKPOINT_NOT_FOUND"):
        mgr.create("P1", "demo", "Experts/DemoEA.mq5", checkpoint_id="CP-20200101-000000-AAAAAAAAAAAA")
    with pytest.raises(ValueError, match="BASELINE_JOB_ID_NOT_FOUND"):
        mgr.create("P2", "demo", "Experts/DemoEA.mq5", baseline_job_id="BT-missing")
    mgr.create("GOOD", "demo", "Experts/DemoEA.mq5")
    rev = root / "state" / "project-sessions" / "GOOD" / "revisions" / "REV-000001.json"
    raw = json.loads(rev.read_text(encoding="utf-8"))
    raw["active_goal"] = "tampered"
    rev.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="INTEGRITY_FAILURE"):
        ProjectSessionManager(root).get("GOOD")


def test_project_id_and_decision_refs_are_path_safe(tmp_path: Path):
    root = _root(tmp_path)
    mgr = ProjectSessionManager(root)
    with pytest.raises(ValueError, match="Invalid project_id"):
        mgr.create("../escape", "demo", "Experts/DemoEA.mq5")
    with pytest.raises(ValueError, match="Invalid decision"):
        mgr.create("P1", "demo", "Experts/DemoEA.mq5", decision_refs=["../../secret"])


class FakeContext:
    pass


class FakeMCPServer:
    def __init__(self, name, **kwargs):
        self.tools = {}
        self.resources = {}
    def tool(self, **kwargs):
        def deco(fn): self.tools[fn.__name__] = fn; return fn
        return deco
    def resource(self, uri, **kwargs):
        def deco(fn): self.resources[uri] = (fn, kwargs); return fn
        return deco


def test_mcp_exposes_tip014_session_tools(monkeypatch, tmp_path: Path):
    fake = types.ModuleType("mcp.server.mcpserver")
    fake.MCPServer = FakeMCPServer
    fake.Context = FakeContext
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", fake)
    types_mod = types.ModuleType("mcp.types")
    class _Model:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    for model_name in ("CallToolResult", "ResourceLink", "TextContent", "ToolAnnotations"):
        setattr(types_mod, model_name, _Model)
    monkeypatch.setitem(sys.modules, "mcp.types", types_mod)
    from vibemql5.adapters.mcp import create_server
    server = create_server(_root(tmp_path), transport="stdio")
    for name in ("list_project_sessions", "get_project_session", "create_project_session", "update_project_session", "resume_project_session"):
        assert name in server.tools
    info = server.tools["server_info"]()
    assert info["version"] == "0.2.40"
    assert info["project_session_schema"] == "1.0"
    assert info["runtime_provenance"]["bridge_build"] == "TIP-044"


def test_current_restart_is_state_preserving_and_terminal_safe():
    root = Path(__file__).resolve().parents[2]
    restart = (root / "scripts" / "backend-admin-restart.ps1").read_text(encoding="utf-8")
    assert "Stop-ProcessTreeSafe" in restart
    assert "RESTART_TARGET_PROTECTED" in restart
    for protected in ("terminal64.exe", "metatester64.exe", "metaeditor64.exe"):
        assert protected in restart
    assert "terminal_touched = $false" in restart
    assert "state\\project-sessions" not in restart
    assert "READINESS_TIMEOUT" in restart


def test_tip014_mcp_instructions_include_resume_before_continuation():
    root = Path(__file__).resolve().parents[2]
    text = (root / "app" / "vibemql5" / "adapters" / "mcp.py").read_text(encoding="utf-8")
    assert "resume_project_session before continuing after reconnect/restart" in text
