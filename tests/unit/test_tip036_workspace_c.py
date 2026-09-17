from __future__ import annotations

import json
import subprocess

import pytest

from app.vibemql5.backend_admin import multitunnel
from app.vibemql5.backend_admin.core import BackendAdminError
from app.vibemql5.backend_admin.multitunnel import MultiTunnelBackendAdmin
from app.vibemql5.backend_admin.tools import register_backend_admin_tools


def _root(tmp_path):
    root = tmp_path / "VibeMQL5"
    (root / "ops" / "windows").mkdir(parents=True)
    base = {
        "tunnel": {
            "profile": "vibemql5-vps",
            "arguments": ["run", "--profile", "vibemql5-vps"],
            "secretFile": str(root / "secrets" / "tunnel-runtime-key.dpapi"),
        },
        "tasks": {
            "tunnelTaskName": "VibeMQL5-OpenAI-Tunnel",
            "watchdogTaskName": "VibeMQL5-Watchdog",
            "backgroundTunnelTaskName": "VibeMQL5-OpenAI-Tunnel-Background",
            "enableBootTunnel": True,
        },
        "logs": {"supervisorLog": str(root / "logs" / "tunnel-supervisor.log")},
        "supervisor": {
            "healthUrl": "http://127.0.0.1:8080/healthz",
            "readyUrl": "http://127.0.0.1:8080/readyz",
            "stateFile": str(root / "state" / "tunnel-supervisor.json"),
            "watchdogStateFile": str(root / "state" / "tunnel-watchdog.json"),
        },
    }
    (root / "ops" / "windows" / "vibemql5.windows.json").write_text(
        json.dumps(base), encoding="utf-8"
    )
    return root


def test_tip036_c_instance_is_independent_ingress(tmp_path):
    admin = MultiTunnelBackendAdmin(_root(tmp_path))
    spec = admin.TUNNEL_INSTANCES["C"]
    assert spec == {
        "config": "ops/windows/vibemql5.windows.c.json",
        "profile": "vibemql5-vps-c",
        "secret": "secrets/tunnel-runtime-key-c.dpapi",
        "health_port": 8082,
        "task": "VibeMQL5-OpenAI-Tunnel-C",
        "watchdog": "VibeMQL5-Watchdog-C",
        "background": "VibeMQL5-OpenAI-Tunnel-Background-C",
    }


def test_tip036_c_config_is_derived_from_a_without_secret_material(tmp_path):
    root = _root(tmp_path)
    admin = MultiTunnelBackendAdmin(root)
    path = admin._prepare_secondary_tunnel_config("C")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["tunnel"]["profile"] == "vibemql5-vps-c"
    assert data["tunnel"]["arguments"] == ["run", "--profile", "vibemql5-vps-c"]
    assert data["tunnel"]["secretFile"] == str(root / "secrets" / "tunnel-runtime-key-c.dpapi")
    assert data["tasks"]["tunnelTaskName"] == "VibeMQL5-OpenAI-Tunnel-C"
    assert data["tasks"]["watchdogTaskName"] == "VibeMQL5-Watchdog-C"
    assert data["tasks"]["backgroundTunnelTaskName"] == "VibeMQL5-OpenAI-Tunnel-Background-C"
    assert data["tasks"]["enableBootTunnel"] is False
    assert data["supervisor"]["healthUrl"] == "http://127.0.0.1:8082/healthz"
    assert data["supervisor"]["readyUrl"] == "http://127.0.0.1:8082/readyz"
    assert data["logs"]["supervisorLog"].endswith("tunnel-supervisor-c.log")
    assert data["supervisor"]["stateFile"].endswith("tunnel-supervisor-c.json")
    assert data["supervisor"]["watchdogStateFile"].endswith("tunnel-watchdog-c.json")
    assert "runtime-key" not in path.read_text(encoding="utf-8").split("secretFile", 1)[0]


def test_tip036_status_all_includes_a_b_c(tmp_path, monkeypatch):
    admin = MultiTunnelBackendAdmin(_root(tmp_path))
    monkeypatch.setattr(admin, "_tunnel_status_one", lambda key: {"instance": key})
    status = admin.tunnel_admin_status("all")
    assert [item["instance"] for item in status["instances"]] == ["A", "B", "C"]
    assert status["generic_shell_exposed"] is False


def test_tip036_c_autostart_reuses_certified_installer(tmp_path, monkeypatch):
    root = _root(tmp_path)
    admin = MultiTunnelBackendAdmin(root)
    profile = root / "vibemql5-vps-c.yaml"
    profile.write_text("profile: fixture\n", encoding="utf-8")
    secret = root / admin.TUNNEL_INSTANCES["C"]["secret"]
    secret.parent.mkdir(parents=True)
    secret.write_bytes(b"fixture-dpapi")

    calls = []
    monkeypatch.setattr(admin, "_tunnel_profile_path", lambda _profile: profile)
    monkeypatch.setattr(
        admin,
        "_run",
        lambda argv, timeout=180: calls.append((argv, timeout)) or subprocess.CompletedProcess(argv, 0, "", ""),
    )
    monkeypatch.setattr(admin, "_task_command", lambda _action, _names: None)
    monkeypatch.setattr(admin, "_kill_profile_processes", lambda _profile: [])
    monkeypatch.setattr(
        admin,
        "_wait_instance_ready",
        lambda key, _seconds=45: {
            "instance": key,
            "process_count": 1,
            "healthz_status": 200,
            "readyz_status": 200,
        },
    )
    monkeypatch.setattr(multitunnel.time, "sleep", lambda _seconds: None)

    receipt = admin.tunnel_admin_install_autostart("C")
    assert receipt["status"] == "PASS"
    assert receipt["payload"]["instance"] == "C"
    assert receipt["payload"]["ready"]["healthz_status"] == 200
    argv = calls[0][0]
    assert "Install-VibeMQL5ScheduledTasks.ps1" in " ".join(str(x) for x in argv)
    assert "vibemql5.windows.c.json" in " ".join(str(x) for x in argv)


def test_tip036_primary_a_cannot_be_reinstalled_through_secondary_onboarding(tmp_path):
    admin = MultiTunnelBackendAdmin(_root(tmp_path))
    with pytest.raises(BackendAdminError, match="AUTOSTART_INSTALL_SECONDARY_ONLY"):
        admin.tunnel_admin_install_autostart("A")


def test_tip036_public_tools_use_multi_tunnel_backend(tmp_path):
    class FakeMCP:
        def tool(self, **_kwargs):
            return lambda fn: fn

    admin = register_backend_admin_tools(FakeMCP(), _root(tmp_path))
    assert isinstance(admin, MultiTunnelBackendAdmin)
    assert set(admin.TUNNEL_INSTANCES) == {"A", "B", "C"}
