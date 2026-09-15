from __future__ import annotations

import json
import re
from pathlib import Path

import vibemql5
from vibemql5.adapters.mcp import _runtime_provenance
from vibemql5.core.facade import ToolFacade

ROOT = Path(__file__).parents[2]
OPS = ROOT / "ops" / "windows"


def test_tip013_version_and_runtime_provenance(monkeypatch):
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "interactive")
    p = _runtime_provenance()
    assert vibemql5.__version__ == "0.2.34"
    assert p["bridge_build"] == "TIP-033RC1"
    assert p["workspace_module_sha256"]
    assert p["mcp_module_sha256"]


def test_runtime_status_includes_atomic_resilience_evidence(tmp_path: Path, monkeypatch):
    root = tmp_path / "VibeMQL5"
    (root / "config").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({"terminal_policy": {"alias": "MT5-2"}}), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    (root / "state" / "tip013-resilience.json").write_text(json.dumps({"last_scenario": "TunnelCrash", "last_status": "PASS"}), encoding="utf-8")
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "interactive")
    out = ToolFacade(root).runtime_status()
    assert out["resilience"]["last_scenario"] == "TunnelCrash"
    assert out["resilience"]["last_status"] == "PASS"
    assert out["resilience"]["current_runtime_certification"] is False


def test_tip013_powershell_never_assigns_readonly_pid_automatic_variable():
    for name in ("Invoke-TIP013FailureInjection.ps1", "Invoke-TIP013Soak.ps1"):
        text = (OPS / name).read_text(encoding="utf-8")
        assert re.search(r"\$pid\s*=", text, flags=re.IGNORECASE) is None


def test_failure_injection_scopes_exact_control_plane_and_never_terminal64():
    s = (OPS / "Invoke-TIP013FailureInjection.ps1").read_text(encoding="utf-8")
    assert "Get-ExactTunnelProcess" in s
    assert "ExecutablePath" in s
    assert "Get-ExactMcpProcess" in s
    assert "vibemql5\\.adapters\\.mcp" in s
    assert "terminal64.exe" not in s
    assert "finally" in s


def test_supervisor_watchdog_publish_bounded_recovery_and_provenance():
    sup = (OPS / "Start-VibeMQL5TunnelSupervisor.ps1").read_text(encoding="utf-8")
    watch = (OPS / "Invoke-VibeMQL5Watchdog.ps1").read_text(encoding="utf-8")
    assert 'bridge_build = [string]$bridgeProvenance.bridge_build' in sup
    assert 'producer_sha256 = [string]$producerProvenance.producer_sha256' in sup
    assert "restart_history_utc" in sup and "CIRCUIT_OPEN" in sup
    assert "healthUrl" in watch and "readyUrl" in watch
    assert "WAITING_FOR_INTERACTIVE_LOGON" in watch
    assert "CIRCUIT_OPEN" in watch


def test_current_restart_controller_is_fail_closed_and_protects_mt5():
    s = (ROOT / "scripts" / "backend-admin-restart.ps1").read_text(encoding="utf-8")
    assert "Get-CimInstance Win32_Process" in s
    assert "Stop-ProcessTreeSafe" in s
    assert "run-mcp-task\\.ps1" in s
    assert "Start-VibeMQL5InteractiveEntry\\.ps1" in s
    assert "RESTART_TARGET_PROTECTED" in s
    for protected in ("terminal64.exe", "metatester64.exe", "metaeditor64.exe"):
        assert protected in s
    assert "terminal_touched = $false" in s
    assert "READINESS_TIMEOUT" in s


def test_config_schema_has_tip013_resilience_controls():
    cfg = json.loads((OPS / "vibemql5.windows.json").read_text(encoding="utf-8"))
    schema = json.loads((OPS / "vibemql5.windows.schema.json").read_text(encoding="utf-8"))
    sup = cfg["supervisor"]
    assert sup["resilienceStateFile"].endswith("tip013-resilience.json")
    assert sup["failureInjectionTimeoutSeconds"] >= 30
    assert sup["networkIsolationSeconds"] >= 10
    assert sup["networkRecoveryTimeoutSeconds"] >= 30
    props = schema["properties"]["supervisor"]["properties"]
    for name in ("resilienceStateFile", "failureInjectionTimeoutSeconds", "networkIsolationSeconds", "networkRecoveryTimeoutSeconds"):
        assert name in props


def test_current_backend_guards_mutation_restart_and_job_bound_runtime_forensics():
    core = (ROOT / "app" / "vibemql5" / "backend_admin" / "core.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app" / "vibemql5" / "runtime_forensics" / "service.py").read_text(encoding="utf-8")
    assert "mutable_roots" in core
    assert "CHECKPOINT_DOES_NOT_COVER_FILE" in core
    assert "RESTART_COMPONENT_NOT_ALLOWED" in core
    assert "job_id" in runtime
    for forbidden in ("caller_pid", "arbitrary_pid", "shell_command"):
        assert forbidden not in runtime


def test_soak_monitor_is_bounded_and_persists_evidence():
    s = (OPS / "Invoke-TIP013Soak.ps1").read_text(encoding="utf-8")
    assert "DurationMinutes" in s and "SampleSeconds" in s
    assert "MaxConsecutiveBad" in s
    assert "BridgeBuild" in s and "CertifyCurrentRuntime" in s
    assert "current_runtime_certification" in s
    assert "TIP013_SOAK_CURRENT_CERT_REQUIRES_ZERO_BAD_TOLERANCE" in s
    assert "heartbeatStaleSeconds" in s
    assert "TIP013_SOAK=PASS" in s


def test_tip034e_current_runtime_certification_is_build_bound(tmp_path: Path, monkeypatch):
    root = tmp_path / "VibeMQL5"
    (root / "config").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({"terminal_policy": {"alias": "MT5-2"}}), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    (root / "config" / "build-provenance.json").write_text(json.dumps({"bridge_build": "TIP-033RC1"}), encoding="utf-8")
    state_path = root / "state" / "tip013-resilience.json"
    state_path.write_text(json.dumps({"bridge_build": "TIP-033RC1", "last_status": "PASS", "current_runtime_certification": True}), encoding="utf-8")
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "interactive")
    out = ToolFacade(root).runtime_status()["resilience"]
    assert out["current_runtime_certification"] is True
    assert out["evidence_role"] == "CURRENT_RUNTIME_CERTIFICATION"

    state_path.write_text(json.dumps({"bridge_build": "TIP-013", "last_status": "PASS", "current_runtime_certification": True}), encoding="utf-8")
    out = ToolFacade(root).runtime_status()["resilience"]
    assert out["current_runtime_certification"] is False
    assert out["evidence_role"] == "HISTORICAL_QUALIFICATION"


def test_tip034e_backend_exposes_only_fixed_soak_suite():
    core = (ROOT / "app" / "vibemql5" / "backend_admin" / "core.py").read_text(encoding="utf-8")
    assert '"tip033_soak"' in core
    assert "Invoke-TIP013Soak.ps1" in core
    assert '"-DurationMinutes", "60"' in core
    assert '"-SampleSeconds", "30"' in core
    assert '"-MaxConsecutiveBad", "0"' in core
    assert '"-CertifyCurrentRuntime"' in core


def test_tip013f_legacy_state_migration_oracle_keeps_last_result():
    legacy = {
        "schema_version": "1.0",
        "bridge_build": "TIP-013",
        "last_scenario": "Soak",
        "last_status": "PASS",
        "last_result": {"scenario": "Soak", "status": "PASS"},
    }
    history = list(legacy.get("history") or [])
    if not history and legacy.get("last_result") is not None:
        history = [legacy["last_result"]]
    current = {"scenario": "TunnelCrash", "status": "PASS"}
    history.append(current)
    assert history == [
        {"scenario": "Soak", "status": "PASS"},
        {"scenario": "TunnelCrash", "status": "PASS"},
    ]
