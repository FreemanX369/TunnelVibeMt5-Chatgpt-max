from __future__ import annotations

import ast
import base64
import inspect
import json
import threading
import time
from datetime import date
from pathlib import Path

import pytest

from vibemql5.contracts import (
    MCP_TOOL_CATALOG_SHA256,
    MCP_TOOL_COUNT,
    MCP_TOOL_NAMES,
    RESULT_SCHEMA_VERSION,
)
from vibemql5.core.artifacts import ArtifactManager
from vibemql5.core.facade import ToolFacade
from vibemql5.core.iterations import IterationManager
from vibemql5.core.jobs import JobManager, JobStore
from vibemql5.core.tester import TesterDriver as _TesterDriver
from vibemql5.core.tester_config import normalize_tester_request, render_tester_ini
from vibemql5.models.types import TerminalInfo
from vibemql5.parsers.tester_log import decode_text_bytes
from vibemql5.worker import build_result


def _preset_root(tmp_path: Path) -> Path:
    root = tmp_path
    p = root / "config" / "presets"
    p.mkdir(parents=True)
    (p / "smoke.json").write_text(
        json.dumps({
            "symbol": "EURUSD",
            "period": "M5",
            "model": 4,
            "from_date": "2026.08.01",
            "to_date": "2026.08.02",
            "deposit": 10000,
            "currency": "USD",
            "leverage": 100,
            "visual": False,
        }),
        encoding="utf-8",
    )
    return root


def test_tun01_validation_is_before_compile_and_handoff(tmp_path):
    root = _preset_root(tmp_path)
    with pytest.raises(ValueError, match="Unsupported tester overrides"):
        normalize_tester_request(root, "smoke", {"not_supported": 1})

    worker = (Path(__file__).parents[2] / "app" / "vibemql5" / "worker.py").read_text(encoding="utf-8")
    validate_at = worker.index("normalize_tester_request(")
    compile_at = worker.index("compiler.compile(")
    handoff_at = worker.index("exclusive_live_terminal_handoff(")
    assert validate_at < compile_at < handoff_at


def test_d021r01_execution_delay_maps_native_mt5_bounds(tmp_path):
    root = _preset_root(tmp_path)
    for value, mode in [(-1, "RANDOM"), (0, "NO_DELAY"), (150, "FIXED_MS"), (600000, "FIXED_MS")]:
        resolved, normalization = normalize_tester_request(root, "smoke", {"execution_delay_ms": value})
        assert resolved["execution_delay_ms"] == value
        assert normalization["execution_delay"]["execution_mode"] == value
        assert normalization["execution_delay"]["mode"] == mode
        run = root / f"run-{value}"
        run.mkdir()
        ini, _ = render_tester_ini(root, run, "EA", "smoke", resolved_config=resolved)
        assert f"ExecutionMode={value}" in ini.read_text(encoding="utf-8")

    for bad in (-2, 600001, 1.5, True):
        with pytest.raises(ValueError, match="execution_delay_ms"):
            normalize_tester_request(root, "smoke", {"execution_delay_ms": bad})


def test_d021r02_future_to_date_clamps_but_preserves_request(tmp_path):
    root = _preset_root(tmp_path)
    resolved, n = normalize_tester_request(
        root, "smoke",
        {"from_date": "2026.09.01", "to_date": "2026.09.12"},
        today=date(2026, 9, 4),
    )
    assert n["requested_period"]["to_date"] == "2026.09.12"
    assert n["effective_period"]["to_date"] == "2026.09.04"
    assert n["future_to_date_clamped"] is True
    assert resolved["to_date"] == "2026.09.04"

    with pytest.raises(ValueError, match="effective to_date"):
        normalize_tester_request(
            root, "smoke",
            {"from_date": "2026.09.05", "to_date": "2026.09.12"},
            today=date(2026, 9, 4),
        )




def test_tun01_facade_rejects_invalid_override_before_job_creation(tmp_path):
    root = _preset_root(tmp_path)
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {"disk_warning_gb": 0, "disk_block_gb": 0, "min_free_memory_mb": 0},
        "retention": {"completed_jobs": 20}, "jobs": {"max_concurrent": 1},
        "defaults": {"terminal": "MT5-2"}, "terminal_policy": {"alias": "MT5-2", "mode": "fixed"},
    }), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": [{
        "alias": "MT5-2", "terminal_path": r"C:\\Fixture\\terminal64.exe",
        "metaeditor_path": r"C:\\Fixture\\metaeditor64.exe", "data_hash": "x",
        "data_root": r"C:\\Fixture\\Data", "build": 1, "enabled": True,
    }]}), encoding="utf-8")
    facade = ToolFacade(root)
    with pytest.raises(ValueError, match="Unsupported tester overrides"):
        facade.launch_test("demo", "Experts/DemoEA.mq5", overrides={"execution_delay_typo": 150}, mock=True)
    assert list((root / "runs").glob("*/job.json")) == []

def test_tun02_phase_receipt_is_write_once_and_result_never_downgrades_compile(tmp_path):
    root = tmp_path
    store = JobStore(root)
    job = store.create({"workspace": "W", "ea": "EA.mq5", "terminal": "MT5-2", "mock": True})
    job_id = job["job_id"]
    artifacts = ArtifactManager(root)
    compile_evidence = {
        "status": "PASSED", "errors": 0, "warnings": 0,
        "immutable_ex5": {"path": "compiled.ex5", "sha256": "a" * 64, "bytes": 123},
    }
    receipt = {"schema_version": "1.0", "phase": "COMPILE", "status": "PASSED", "evidence": compile_evidence}
    artifacts.write_phase_receipt(job_id, "compile", receipt)
    artifacts.write_phase_receipt(job_id, "compile", receipt)  # idempotent replay
    with pytest.raises(RuntimeError, match="PHASE_RECEIPT_IMMUTABLE_CONFLICT"):
        artifacts.write_phase_receipt(job_id, "compile", {**receipt, "status": "FAILED"})

    result = build_result(root, job_id, None, None)
    assert result["schema_version"] == RESULT_SCHEMA_VERSION == "1.4"
    assert result["compile"]["status"] == "PASSED"
    assert result["compile"]["immutable_ex5"]["sha256"] == "a" * 64
    assert result["tester"]["status"] == "NOT_RUN"


def test_d021r04_stopped_terminal_remains_stopped(monkeypatch):
    import vibemql5.core.terminal_handoff as handoff

    terminal = TerminalInfo(
        alias="MT5-2", terminal_path=r"C:\\MT5\\terminal64.exe",
        metaeditor_path=r"C:\\MT5\\metaeditor64.exe", data_hash="x",
        data_root=r"C:\\MT5", build=1, enabled=True,
    )
    calls = []
    monkeypatch.setattr(handoff, "close_terminal_gracefully", lambda *_a, **_k: {
        "was_running": False, "closed_pids": [], "observed_pids": [],
        "respawned_pids": [], "wm_close_messages": 0,
        "taskkill_used": False, "force_kill_used": False,
        "close_elapsed_seconds": 0.0,
    })
    monkeypatch.setattr(handoff, "restart_normal_terminal", lambda *_a, **_k: calls.append("restart") or {})
    with handoff.exclusive_live_terminal_handoff(terminal, 123, "EURUSD") as meta:
        assert meta["was_running"] is False
    assert calls == []
    assert meta["restore_attempted"] is False
    assert meta["restore_skipped_reason"] == "PRE_HANDOFF_TERMINAL_WAS_STOPPED"


def test_tun07_utf16_decoder_and_live_cursor_do_not_drop_split_code_unit():
    raw = "automatic testing started 7%\r\n".encode("utf-16-le")
    raw = b"\xff\xfe" + raw
    text, meta = decode_text_bytes(raw)
    assert "7%" in text
    assert "\x00" not in text
    assert meta["replacement_characters"] == 0

    # Simulate a live read ending between UTF-16 code units.
    text1, m1 = _TesterDriver._decode_delta(raw[:-1], 0)
    assert m1["trailing_bytes_deferred"] == 1
    assert m1["consumed_bytes"] == len(raw) - 2
    text2, m2 = _TesterDriver._decode_delta(raw, m1["consumed_bytes"])
    assert m2["consumed_bytes"] == 2
    assert m2["trailing_bytes_deferred"] == 0
    assert text1 + text2 == text


def test_tun10_binary_artifact_is_job_scoped_chunked_and_hash_bound(tmp_path):
    root = tmp_path
    store = JobStore(root)
    job = store.create({"workspace": "W", "ea": "EA.mq5"})
    job_id = job["job_id"]
    payload = bytes(range(256)) * 8
    p = root / "runs" / job_id / "compiled.ex5"
    p.write_bytes(payload)

    facade = object.__new__(ToolFacade)
    facade.root = root
    facade.jobs = JobManager(root)
    manifest = facade.read_artifact(job_id, "manifest")
    compiled = next(x for x in manifest["artifacts"] if x["name"] == "compiled.ex5")
    assert compiled["exists"] is True and compiled["complete"] is True
    assert compiled["job_id"] == job_id and len(manifest["catalog_sha256"]) == 64
    first = facade.read_artifact(job_id, "compiled.ex5", 0, 100)
    assert first["kind"] == "binary"
    assert base64.b64decode(first["content_base64"]) == payload[:100]
    assert first["next_offset"] == 100
    assert first["eof"] is False
    second = facade.read_artifact(job_id, "compiled.ex5", first["next_offset"], 10000)
    assert base64.b64decode(second["content_base64"]) == payload[100:]
    assert second["eof"] is True
    assert first["sha256"] == second["sha256"]
    with pytest.raises(ValueError, match="not allowed"):
        facade.read_artifact(job_id, "../../secret")


def test_d021r03_event_stream_and_bounded_long_poll(tmp_path):
    root = tmp_path
    store = JobStore(root)
    job = store.create({"workspace": "W", "ea": "EA.mq5", "test_timeout": 0})
    job_id = job["job_id"]
    manager = JobManager(root)

    def later():
        time.sleep(0.15)
        store.publish_event(job_id, "TESTER_PROGRESS", {"progress_pct": 8})

    t = threading.Thread(target=later)
    t.start()
    before = time.monotonic()
    observed = manager.get_job(job_id, wait_seconds=2, after_event_seq=0)
    elapsed = time.monotonic() - before
    t.join()
    assert elapsed < 1.5
    assert observed["event_seq"] == 1
    assert observed["last_event"]["kind"] == "TESTER_PROGRESS"
    assert observed["request"]["test_timeout"] == 0
    assert inspect.signature(IterationManager.start).parameters["timeout_seconds"].default == 0
    from vibemql5.adapters.cli import build_parser
    parser = build_parser()
    assert parser.parse_args(["test", "W", "EA.mq5"]).timeout == 0
    assert parser.parse_args(["demo"]).timeout == 0
    assert parser.parse_args(["iteration-start", "P", "R", "a" * 64, "b" * 64, "1", "--mutation-file", "x.json"]).timeout == 0


def test_tun08_tun09_schema_and_tool_catalog_single_source_of_truth():
    assert RESULT_SCHEMA_VERSION == "1.4"
    assert MCP_TOOL_COUNT == 72 == len(MCP_TOOL_NAMES)
    assert len(set(MCP_TOOL_NAMES)) == 72
    for required in ("read_iteration_history", "list_fault_receipts", "list_job_history", "export_file"):
        assert required in MCP_TOOL_NAMES
    assert len(MCP_TOOL_CATALOG_SHA256) == 64
    from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
    assert REQUIRED_TOOLS == set(MCP_TOOL_NAMES)

    source = (Path(__file__).parents[2] / "app" / "vibemql5" / "adapters" / "mcp.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    tool_defs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr == "tool":
                    tool_defs.append(node.name)
    assert tuple(tool_defs) == MCP_TOOL_NAMES[:-16]
    assert all(name.startswith(("backend_", "tunnel_admin_")) for name in MCP_TOOL_NAMES[-16:])
    assert "register_backend_admin_tools(server" in source
    assert '"result_schema": RESULT_SCHEMA_VERSION' in source


def test_o01_supervisor_prunes_restart_window_at_publish_time():
    source = (Path(__file__).parents[2] / "ops" / "windows" / "Start-VibeMQL5TunnelSupervisor.ps1").read_text(encoding="utf-8")
    publish = source[source.index("function Publish-State"):source.index("$supervisorStarted")]
    for token in (
        "$restartWindowStart = $stateNow.AddHours(-1)",
        "$freshRestartHistory",
        "restart_window_seconds = 3600",
        "restart_history_as_of_utc",
        'restart_history_source = "tunnel-supervisor-process-memory"',
        "restart_count_last_hour = @($freshRestartHistory).Count",
    ):
        assert token in publish


def test_tip021r_mock_e2e_preserves_owner_semantics_and_phase_chain(tmp_path):
    from vibemql5.worker import run_job

    root = tmp_path / "VibeMQL5"
    (root / "config" / "presets").mkdir(parents=True)
    (root / "workspaces" / "demo" / "Experts").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {"disk_warning_gb": 0, "disk_block_gb": 0, "min_free_memory_mb": 0},
        "retention": {"completed_jobs": 20},
        "jobs": {"max_concurrent": 1},
        "defaults": {"terminal": "MT5-2"},
        "terminal_policy": {"alias": "MT5-2", "mode": "fixed"},
    }), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": [{
        "alias": "MT5-2",
        "terminal_path": r"C:\\Fixture\\terminal64.exe",
        "metaeditor_path": r"C:\\Fixture\\metaeditor64.exe",
        "data_hash": "fixture",
        "data_root": r"C:\\Fixture\\Data",
        "build": 1,
        "enabled": True,
    }]}), encoding="utf-8")
    (root / "config" / "presets" / "smoke.json").write_text(json.dumps({
        "symbol": "EURUSD", "period": "M5", "model": 4,
        "from_date": "2020.01.01", "to_date": "2099.12.31",
        "deposit": 10000, "currency": "USD", "leverage": 100, "visual": False,
    }), encoding="utf-8")
    (root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5").write_text(
        "#property strict\nvoid OnTick(){}\n", encoding="utf-8"
    )

    req = {
        "workspace": "demo", "ea": "Experts/DemoEA.mq5", "terminal": "MT5-2",
        "preset": "smoke", "set_file": None,
        "overrides": {"execution_delay_ms": 150},
        "compile_timeout": 120, "test_timeout": 0, "queue_wait_seconds": 3,
        "mock": True,
    }
    store = JobStore(root)
    job = store.create(req)
    run_job(root, job["job_id"])

    run = root / "runs" / job["job_id"]
    final_job = store.load(job["job_id"])
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    config_receipt = json.loads((run / "phase-config.json").read_text(encoding="utf-8"))
    compile_receipt = json.loads((run / "phase-compile.json").read_text(encoding="utf-8"))
    tester_receipt = json.loads((run / "phase-tester.json").read_text(encoding="utf-8"))

    assert final_job["state"] == "PASSED"
    assert result["schema_version"] == "1.4"
    assert result["compile"]["status"] == "PASSED"
    assert result["tester"]["status"] == "COMPLETED"
    assert result["tester"]["period_conformance"]["status"] == "PASS"
    assert result["anomalies"] == []
    assert config_receipt["status"] == "PASSED"
    assert config_receipt["normalization"]["future_to_date_clamped"] is True
    assert config_receipt["normalization"]["requested_period"]["to_date"] == "2099.12.31"
    assert config_receipt["resolved_config"]["to_date"] == date.today().strftime("%Y.%m.%d")
    assert config_receipt["resolved_config"]["execution_delay_ms"] == 150
    assert compile_receipt["status"] == "PASSED"
    assert tester_receipt["status"] == "COMPLETED"
    ini = (run / "tester.ini").read_text(encoding="utf-8")
    assert "ExecutionMode=150" in ini
    assert f"ToDate={date.today().strftime('%Y.%m.%d')}" in ini
    kinds = [event["kind"] for event in final_job["events"]]
    assert "TESTER_REQUEST_VALIDATED" in kinds
    assert "COMPILE_FINISHED" in kinds
    assert "TESTER_NATIVE_FINISHED" in kinds
    assert "JOB_TERMINAL" in kinds
