from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..core.jobs import _exclusive_file_lock
from .core import BackendAdmin, BackendAdminError


class MultiTunnelBackendAdmin(BackendAdmin):
    """Extend the certified A/B tunnel admin with an independent workspace-C ingress."""

    TUNNEL_INSTANCES = {
        **BackendAdmin.TUNNEL_INSTANCES,
        "C": {
            "config": "ops/windows/vibemql5.windows.c.json",
            "profile": "vibemql5-vps-c",
            "secret": "secrets/tunnel-runtime-key-c.dpapi",
            "health_port": 8082,
            "task": "VibeMQL5-OpenAI-Tunnel-C",
            "watchdog": "VibeMQL5-Watchdog-C",
            "background": "VibeMQL5-OpenAI-Tunnel-Background-C",
        },
    }

    def _prepare_secondary_tunnel_config(self, instance: str) -> Path:
        key, spec = self._tunnel_spec(instance)
        if key == "A":
            raise BackendAdminError("TUNNEL_SECONDARY_INSTANCE_REQUIRED")

        target = self.root / spec["config"]
        if target.is_file():
            current = json.loads(target.read_text(encoding="utf-8"))
            expected = {
                "profile": spec["profile"],
                "secretFile": str(self.root / spec["secret"]),
                "healthUrl": f"http://127.0.0.1:{spec['health_port']}/healthz",
                "readyUrl": f"http://127.0.0.1:{spec['health_port']}/readyz",
                "task": spec["task"],
                "watchdog": spec["watchdog"],
            }
            observed = {
                "profile": str(current.get("tunnel", {}).get("profile") or ""),
                "secretFile": str(current.get("tunnel", {}).get("secretFile") or ""),
                "healthUrl": str(current.get("supervisor", {}).get("healthUrl") or ""),
                "readyUrl": str(current.get("supervisor", {}).get("readyUrl") or ""),
                "task": str(current.get("tasks", {}).get("tunnelTaskName") or ""),
                "watchdog": str(current.get("tasks", {}).get("watchdogTaskName") or ""),
            }
            if observed != expected:
                raise BackendAdminError(f"TUNNEL_{key}_CONFIG_DRIFT")
            return target

        base_path = self.root / self.TUNNEL_INSTANCES["A"]["config"]
        if not base_path.is_file():
            raise BackendAdminError("TUNNEL_A_CONFIG_MISSING")
        config = json.loads(base_path.read_text(encoding="utf-8"))
        suffix = key.lower()
        config["tunnel"]["profile"] = spec["profile"]
        config["tunnel"]["arguments"] = ["run", "--profile", spec["profile"]]
        config["tunnel"]["secretFile"] = str(self.root / spec["secret"])
        config["tasks"]["tunnelTaskName"] = spec["task"]
        config["tasks"]["watchdogTaskName"] = spec["watchdog"]
        config["tasks"]["backgroundTunnelTaskName"] = spec["background"]
        config["tasks"]["enableBootTunnel"] = False
        config["logs"]["supervisorLog"] = str(self.root / "logs" / f"tunnel-supervisor-{suffix}.log")
        config["supervisor"]["healthUrl"] = f"http://127.0.0.1:{spec['health_port']}/healthz"
        config["supervisor"]["readyUrl"] = f"http://127.0.0.1:{spec['health_port']}/readyz"
        config["supervisor"]["stateFile"] = str(self.root / "state" / f"tunnel-supervisor-{suffix}.json")
        config["supervisor"]["watchdogStateFile"] = str(self.root / "state" / f"tunnel-watchdog-{suffix}.json")
        self._atomic_bytes(target, (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        return target

    def tunnel_admin_status(self, instance: str = "all") -> dict[str, Any]:
        value = str(instance or "all").strip().upper()
        keys = list(self.TUNNEL_INSTANCES) if value == "ALL" else [self._tunnel_spec(value)[0]]
        items = [self._tunnel_status_one(key) for key in keys]
        return {
            "status": "PASS",
            "schema_version": "1.0",
            "mode": "ALLOWLISTED_MULTI_TUNNEL_ADMIN",
            "instances": items,
            "generic_shell_exposed": False,
        }

    def tunnel_admin_install_autostart(self, instance: str = "B") -> dict[str, Any]:
        key, spec = self._tunnel_spec(instance)
        if key == "A":
            raise BackendAdminError("AUTOSTART_INSTALL_SECONDARY_ONLY")

        with _exclusive_file_lock(self.tunnel_admin_lock, timeout_seconds=30.0):
            config_path = self._prepare_secondary_tunnel_config(key)
            if json.loads(config_path.read_text(encoding="utf-8")).get("tasks", {}).get("enableBootTunnel"):
                raise BackendAdminError("BOOT_TUNNEL_REQUIRES_INTERACTIVE_CREDENTIAL_INSTALL")
            if not self._tunnel_profile_path(spec["profile"]).is_file():
                raise BackendAdminError("TUNNEL_PROFILE_MISSING")
            secret = self.root / spec["secret"]
            if not secret.is_file() or secret.stat().st_size <= 0:
                raise BackendAdminError("TUNNEL_SECRET_MISSING")
            installer = self.root / "ops" / "windows" / "Install-VibeMQL5ScheduledTasks.ps1"
            cp = self._run([
                "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(installer), "-ConfigPath", str(config_path), "-InteractiveLogon",
            ], timeout=90)
            if cp.returncode != 0:
                raise BackendAdminError("TUNNEL_AUTOSTART_INSTALL_FAILED:" + cp.stderr[-500:])
            self._task_command("Stop", [spec["task"], spec["background"]])
            time.sleep(1)
            stopped = self._kill_profile_processes(spec["profile"])
            self._task_command("Enable", [spec["task"], spec["watchdog"]])
            self._task_command("Start", [spec["task"], spec["watchdog"]])
            ready = self._wait_instance_ready(key, 45)
            return self._receipt("tunnel_admin_install_autostart", "PASS", {
                "instance": key,
                "config_path": str(config_path),
                "stopped_manual_pids": stopped,
                "ready": ready,
                "boot_mode": "INTERACTIVE_LOGON",
            })
