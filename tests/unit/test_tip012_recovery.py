from __future__ import annotations

import json
from pathlib import Path

import pytest

import vibemql5
from vibemql5.adapters.mcp import _runtime_provenance
from vibemql5.core.facade import ToolFacade

ROOT = Path(__file__).parents[2]
OPS = ROOT / "ops" / "windows"


def test_tip012_version_and_runtime_provenance(monkeypatch):
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "interactive")
    monkeypatch.setenv("VIBEMQL5_SUPERVISOR_GENERATION", "gen-123")
    monkeypatch.setenv("VIBEMQL5_SUPERVISOR_SESSION_ID", "2")
    p = _runtime_provenance()
    assert vibemql5.__version__ == "0.2.33"
    assert p["bridge_build"] == "TIP-032R1"
    assert p["runtime_mode"] == "interactive"
    assert p["supervisor_generation"] == "gen-123"
    assert p["supervisor_session_id"] == "2"
    assert p["workspace_module_sha256"]
    assert p["mcp_module_sha256"]


def test_runtime_status_reads_atomic_state(tmp_path: Path, monkeypatch):
    root = tmp_path / "VibeMQL5"
    state = root / "state"
    state.mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({"terminal_policy": {"alias": "MT5-2"}}), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    (state / "tunnel-supervisor.json").write_text(json.dumps({"mode": "interactive", "status": "READY"}), encoding="utf-8")
    (state / "tunnel-watchdog.json").write_text(json.dumps({"status": "HEALTHY", "action": "NONE"}), encoding="utf-8")
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "interactive")
    f = ToolFacade(root)
    out = f.runtime_status()
    assert out["runtime_mode"] == "interactive"
    assert out["supervisor"]["status"] == "READY"
    assert out["watchdog"]["status"] == "HEALTHY"


def test_background_runtime_blocks_native_compile_and_test(tmp_path: Path, monkeypatch):
    root = tmp_path / "VibeMQL5"
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({"terminal_policy": {"alias": "MT5-2"}}), encoding="utf-8")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    monkeypatch.setenv("VIBEMQL5_RUNTIME_MODE", "background")
    f = ToolFacade(root)
    with pytest.raises(RuntimeError, match="MT5_INTERACTIVE_SESSION_REQUIRED"):
        f.compile_ea("demo", "Experts/DemoEA.mq5")
    with pytest.raises(RuntimeError, match="MT5_INTERACTIVE_SESSION_REQUIRED"):
        f.launch_test("demo", "Experts/DemoEA.mq5")


def test_supervisor_uses_health_heartbeat_not_waited_child():
    s = (OPS / "Start-VibeMQL5TunnelSupervisor.ps1").read_text(encoding="utf-8")
    assert "VIBEMQL5_RUNTIME_MODE" in s
    assert "healthUrl" in s and "readyUrl" in s
    assert "last_heartbeat_utc" in s
    assert "CIRCUIT_OPEN" in s
    assert "maxRestartsPerHour" in s
    assert "-RedirectStandardOutput" in s and "-RedirectStandardError" in s
    start_line = next(line for line in s.splitlines() if "$process = Start-Process" in line)
    assert "-Wait" not in start_line


def test_watchdog_uses_runtime_health_and_bounded_recovery():
    s = (OPS / "Invoke-VibeMQL5Watchdog.ps1").read_text(encoding="utf-8")
    assert "LastWriteTime" not in s
    assert "healthUrl" in s and "readyUrl" in s
    assert "heartbeatStaleSeconds" in s
    assert "watchdogRestartCooldownSeconds" in s
    assert "maxRestartsPerHour" in s
    assert "WAITING_FOR_INTERACTIVE_LOGON" in s
    assert "CIRCUIT_OPEN" in s
    assert "ExecutablePath" in s and "Win32_Process" in s


def test_install_contract_has_boot_background_and_interactive_takeover():
    install = (OPS / "Install-VibeMQL5ScheduledTasks.ps1").read_text(encoding="utf-8")
    entry = (OPS / "Start-VibeMQL5InteractiveEntry.ps1").read_text(encoding="utf-8")
    assert "EnableBootTunnel" in install
    assert "New-ScheduledTaskTrigger -AtStartup" in install
    assert "New-ScheduledTaskTrigger -AtLogOn" in install
    assert 'New-ScheduledTaskPrincipal -UserId "SYSTEM"' in install
    assert "backgroundTunnelTaskName" in install
    assert "Stop-ScheduledTask" in entry
    assert "taskkill.exe" in entry and "/T /F" in entry
    assert "ExecutablePath" in entry


def test_mcp_catalog_includes_runtime_status():
    from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
    from vibemql5.contracts import MCP_TOOL_NAMES

    assert "runtime_status" in MCP_TOOL_NAMES
    assert REQUIRED_TOOLS == set(MCP_TOOL_NAMES)
    s = (ROOT / "app" / "vibemql5" / "adapters" / "mcp_client_check.py").read_text(encoding="utf-8")
    assert "MCP_TOOL_NAMES" in s
