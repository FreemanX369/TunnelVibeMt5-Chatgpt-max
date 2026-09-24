from __future__ import annotations

import base64
import hashlib
import io
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

from ..core.concurrency import ConcurrencyManager, current_actor
from ..core.jobs import _exclusive_file_lock
from .models import FileMeta, Receipt, new_id, sha256_file, write_json_atomic

class BackendAdminError(RuntimeError):
    pass


_SHELL_ENV_SECRET = re.compile(r"(?i)(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)")
_SHELL_OUTPUT_REDACTIONS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(
        r'''(?i)\b(?:control_plane_)?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)'''
        r'''\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)'''
    ),
    re.compile(
        r"(?s)-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----.*?-----END \1-----"
    ),
)


def _redact_shell_output(value: str) -> tuple[str, int]:
    redactions = 0
    result = str(value or "")
    for pattern in _SHELL_OUTPUT_REDACTIONS:
        result, count = pattern.subn("[REDACTED]", result)
        redactions += count
    return result, redactions


def _capture_bounded_stream(stream, limit: int, result: dict[str, Any]) -> None:
    captured = bytearray()
    total = 0
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            total += len(chunk)
            remaining = limit - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
    finally:
        try:
            stream.close()
        except OSError:
            pass
    result["data"] = bytes(captured)
    result["total_bytes"] = total
    result["truncated"] = total > len(captured)

class BackendAdmin:
    ALLOWED_EXTENSIONS = {
        ".py", ".ps1", ".psm1", ".json", ".md", ".txt", ".toml", ".yaml", ".yml",
        ".diff", ".patch", ".ini", ".cfg", ".xml", ".html"
    }
    HOTFIX_EXTENSIONS = {".zip", ".json", ".patch", ".diff", ".py", ".ps1"}
    MAX_FILE_BYTES = 16 * 1024 * 1024
    MAX_HOTFIX_BYTES = 16 * 1024 * 1024
    MAX_POWERSHELL_SCRIPT_CHARS = 32_768
    MAX_POWERSHELL_TIMEOUT_SECONDS = 300
    MAX_POWERSHELL_OUTPUT_BYTES = 32_768

    TEST_SUITES = {
        "py_compile",
        "unit",
        "runtime_forensics",
        "tip026",
        "baseline_aware",
        "tip033_soak",
    }

    TUNNEL_INSTANCES = {
        "A": {
            "config": "ops/windows/vibemql5.windows.json",
            "profile": "vibemql5-vps",
            "secret": "secrets/tunnel-runtime-key.dpapi",
            "health_port": 8080,
            "task": "VibeMQL5-OpenAI-Tunnel",
            "watchdog": "VibeMQL5-Watchdog",
            "background": "VibeMQL5-OpenAI-Tunnel-Background",
        },
        "B": {
            "config": "ops/windows/vibemql5.windows.b.json",
            "profile": "vibemql5-vps-b",
            "secret": "secrets/tunnel-runtime-key-b.dpapi",
            "health_port": 8081,
            "task": "VibeMQL5-OpenAI-Tunnel-B",
            "watchdog": "VibeMQL5-Watchdog-B",
            "background": "VibeMQL5-OpenAI-Tunnel-Background-B",
        },
    }

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.concurrency = ConcurrencyManager(self.root)
        self.allowed_roots = [
            self.root / "app" / "vibemql5",
            self.root / "tests",
            self.root / "scripts",
            self.root / "ops" / "windows",
            self.root / "evidence" / "runtime",
            self.root / "config" / "build-provenance.json",
        ]
        self.mutable_roots = [
            self.root / "app" / "vibemql5",
            self.root / "tests",
            self.root / "scripts",
            self.root / "ops" / "windows",
            self.root / "config" / "build-provenance.json",
        ]
        self.backup_root = self.root / "backups" / "backend-admin"
        self.inbox_root = self.root / "maintenance" / "inbox"
        self.receipt_root = self.root / "evidence" / "runtime" / "backend-admin"
        self.python = self.root / ".venv" / "Scripts" / "python.exe"
        self.tunnel_admin_lock = self.root / "state" / "concurrency" / "tunnel-admin.lock"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.inbox_root.mkdir(parents=True, exist_ok=True)
        self.receipt_root.mkdir(parents=True, exist_ok=True)

    def _tunnel_spec(self, instance: str) -> tuple[str, dict[str, Any]]:
        key = str(instance or "").strip().upper()
        if key not in self.TUNNEL_INSTANCES:
            raise BackendAdminError("TUNNEL_INSTANCE_NOT_ALLOWED")
        return key, dict(self.TUNNEL_INSTANCES[key])

    def _tunnel_profile_path(self, profile: str) -> Path:
        appdata = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return appdata / "tunnel-client" / f"{profile}.yaml"

    def _prepare_tunnel_b_config(self) -> Path:
        _, spec = self._tunnel_spec("B")
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
                raise BackendAdminError("TUNNEL_B_CONFIG_DRIFT")
            return target

        base_path = self.root / self.TUNNEL_INSTANCES["A"]["config"]
        if not base_path.is_file():
            raise BackendAdminError("TUNNEL_A_CONFIG_MISSING")
        config = json.loads(base_path.read_text(encoding="utf-8"))
        config["tunnel"]["profile"] = spec["profile"]
        config["tunnel"]["arguments"] = ["run", "--profile", spec["profile"]]
        config["tunnel"]["secretFile"] = str(self.root / spec["secret"])
        config["tasks"]["tunnelTaskName"] = spec["task"]
        config["tasks"]["watchdogTaskName"] = spec["watchdog"]
        config["tasks"]["backgroundTunnelTaskName"] = spec["background"]
        config["tasks"]["enableBootTunnel"] = False
        config["logs"]["supervisorLog"] = str(self.root / "logs" / "tunnel-supervisor-b.log")
        config["supervisor"]["healthUrl"] = f"http://127.0.0.1:{spec['health_port']}/healthz"
        config["supervisor"]["readyUrl"] = f"http://127.0.0.1:{spec['health_port']}/readyz"
        config["supervisor"]["stateFile"] = str(self.root / "state" / "tunnel-supervisor-b.json")
        config["supervisor"]["watchdogStateFile"] = str(self.root / "state" / "tunnel-watchdog-b.json")
        self._atomic_bytes(target, (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        return target

    def _run_ps(self, script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return self._run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-Command", script,
        ], timeout=timeout)

    @staticmethod
    def _safe_task_name(name: str) -> str:
        value = str(name or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise BackendAdminError("TUNNEL_TASK_NAME_INVALID")
        return value

    def _profile_pids(self, profile: str) -> list[int]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
            raise BackendAdminError("TUNNEL_PROFILE_INVALID")
        exe = str(self.root / "tunnel" / "tunnel-client.exe").replace("'", "''")
        profile_ps = profile.replace("'", "''")
        script = (
            f"$exe=[IO.Path]::GetFullPath('{exe}');$profile='{profile_ps}';"
            "$pattern='--profile(?:\\s+|=)\"?'+[regex]::Escape($profile)+'\"?(?:\\s|$)';"
            "@(Get-CimInstance Win32_Process -Filter \"Name='tunnel-client.exe'\" -ErrorAction SilentlyContinue|"
            "Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $exe) -and $_.CommandLine -and $_.CommandLine -match $pattern}|"
            "ForEach-Object{[string]$_.ProcessId}) -join \"`n\""
        )
        cp = self._run_ps(script, timeout=20)
        if cp.returncode != 0:
            raise BackendAdminError("TUNNEL_PROCESS_QUERY_FAILED")
        out = []
        for line in cp.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                out.append(int(line))
        return out

    def _task_state(self, task_name: str) -> str:
        name = self._safe_task_name(task_name)
        script = (
            f"$t=Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue;"
            "if($null -eq $t){'MISSING'}else{[string]$t.State}"
        )
        cp = self._run_ps(script, timeout=20)
        return cp.stdout.strip() if cp.returncode == 0 and cp.stdout.strip() else "UNKNOWN"

    @staticmethod
    def _http_status(url: str) -> int:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except Exception:
            return 0

    @staticmethod
    def _poll_error_kind(error: str, status_code: Any) -> str:
        if type(status_code) is int and 100 <= status_code <= 599:
            return f"HTTP_{status_code}"
        value = str(error or "").lower()
        if "awaiting headers" in value:
            return "AWAITING_HEADERS_TIMEOUT"
        if "proxy" in value:
            return "PROXY"
        if "no such host" in value or "name resolution" in value:
            return "DNS"
        if "tls" in value or "certificate" in value:
            return "TLS"
        if "connection reset" in value:
            return "CONNECTION_RESET"
        if "connection refused" in value:
            return "CONNECTION_REFUSED"
        if "timeout" in value or "deadline exceeded" in value:
            return "TIMEOUT"
        return "OTHER"

    def _poll_diagnostics_one(self, instance: str) -> dict[str, Any]:
        """Summarize bounded loopback poll logs without returning URLs or log text."""
        _, spec = self._tunnel_spec(instance)
        port = int(spec["health_port"])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        try:
            connection.request("GET", "/api/logs?limit=5000")
            response = connection.getresponse()
            if response.status != 200:
                return {"status": "UNAVAILABLE", "reason_code": f"LOGS_HTTP_{response.status}"}
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                return {"status": "UNAVAILABLE", "reason_code": "LOGS_TOO_LARGE"}
            events = json.loads(raw).get("events")
            if not isinstance(events, list):
                return {"status": "UNAVAILABLE", "reason_code": "LOGS_INVALID_RESPONSE"}
        except (OSError, http.client.HTTPException, ValueError, AttributeError):
            return {"status": "UNAVAILABLE", "reason_code": "LOGS_UNREACHABLE_OR_INVALID"}
        finally:
            connection.close()

        episodes: list[dict[str, Any]] = []
        active: dict[str, Any] | None = None
        failures = 0
        for event in events:
            if not isinstance(event, dict):
                continue
            message = event.get("message")
            stamp = event.get("time")
            stamp = stamp[:64] if isinstance(stamp, str) else None
            if message in {"poll failed; backing off", "poll timed out; backing off"}:
                attrs = event.get("attrs")
                attrs = attrs if isinstance(attrs, dict) else {}
                kind = self._poll_error_kind(attrs.get("error"), attrs.get("status_code"))
                if active is None:
                    active = {
                        "first_failure_at": stamp,
                        "first_error_kind": kind,
                        "failure_count": 0,
                        "recovered_at": None,
                    }
                active["failure_count"] += 1
                active["last_failure_at"] = stamp
                active["last_error_kind"] = kind
                for name in ("poll_timeout_ms", "poll_deadline_ms", "retry_in_ms"):
                    value = attrs.get(name)
                    if type(value) is int and 0 <= value <= 600_000:
                        active[name] = value
                failures += 1
            elif message == "poller recovered; polling operational" and active is not None:
                active["recovered_at"] = stamp
                episodes.append(active)
                active = None
        if active is not None:
            episodes.append(active)

        def timestamp(event: Any) -> str | None:
            value = event.get("time") if isinstance(event, dict) else None
            return value[:64] if isinstance(value, str) else None

        return {
            "status": "PASS",
            "schema_version": "1.0",
            "events_retained": len(events),
            "oldest_event_at": timestamp(events[0]) if events else None,
            "newest_event_at": timestamp(events[-1]) if events else None,
            "poll_failures_retained": failures,
            "episodes_retained": len(episodes),
            "episodes": episodes[-32:],
        }

    def _tunnel_status_one(self, instance: str) -> dict[str, Any]:
        key, spec = self._tunnel_spec(instance)
        config_path = self.root / spec["config"]
        profile_path = self._tunnel_profile_path(spec["profile"])
        secret_path = self.root / spec["secret"]
        port = int(spec["health_port"])
        pids = self._profile_pids(spec["profile"])
        return {
            "instance": key,
            "profile": spec["profile"],
            "config_path": str(config_path),
            "config_exists": config_path.is_file(),
            "profile_path": str(profile_path),
            "profile_exists": profile_path.is_file(),
            "secret_present": secret_path.is_file() and secret_path.stat().st_size > 0,
            "health_port": port,
            "healthz_status": self._http_status(f"http://127.0.0.1:{port}/healthz"),
            "readyz_status": self._http_status(f"http://127.0.0.1:{port}/readyz"),
            "pids": pids,
            "process_count": len(pids),
            "tasks": {
                "interactive": {"name": spec["task"], "state": self._task_state(spec["task"])},
                "watchdog": {"name": spec["watchdog"], "state": self._task_state(spec["watchdog"])},
                "background": {"name": spec["background"], "state": self._task_state(spec["background"])},
            },
        }

    def tunnel_admin_status(self, instance: str = "all") -> dict[str, Any]:
        value = str(instance or "all").strip().upper()
        keys = ["A", "B"] if value == "ALL" else [self._tunnel_spec(value)[0]]
        items = [self._tunnel_status_one(key) for key in keys]
        return {
            "status": "PASS",
            "schema_version": "1.0",
            "mode": "ALLOWLISTED_MULTI_TUNNEL_ADMIN",
            "instances": items,
            "generic_shell_exposed": True,
        }

    def _task_command(self, action: str, names: list[str]) -> None:
        if action not in {"Start", "Stop", "Enable", "Disable"}:
            raise BackendAdminError("TUNNEL_TASK_ACTION_INVALID")
        safe = [self._safe_task_name(x) for x in names]
        body = ";".join(
            f"{action}-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue"
            for name in safe
        )
        cp = self._run_ps(body, timeout=30)
        if cp.returncode != 0:
            raise BackendAdminError(f"TUNNEL_TASK_{action.upper()}_FAILED")

    def _kill_profile_processes(self, profile: str) -> list[int]:
        pids = self._profile_pids(profile)
        stopped = []
        for pid in pids:
            cp = self._run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], timeout=20)
            if cp.returncode == 0 or not self._profile_pids(profile):
                stopped.append(pid)
        return stopped

    def _wait_instance_ready(self, instance: str, seconds: int = 45) -> dict[str, Any]:
        deadline = time.monotonic() + max(5, min(int(seconds), 60))
        last = self._tunnel_status_one(instance)
        while time.monotonic() < deadline:
            if last["healthz_status"] == 200 and last["readyz_status"] == 200 and last["process_count"] == 1:
                return last
            time.sleep(1)
            last = self._tunnel_status_one(instance)
        raise BackendAdminError("TUNNEL_INSTANCE_READINESS_TIMEOUT")

    def tunnel_admin_install_autostart(self, instance: str = "B") -> dict[str, Any]:
        key, spec = self._tunnel_spec(instance)
        if key != "B":
            raise BackendAdminError("AUTOSTART_INSTALL_CURRENTLY_ALLOWED_FOR_B_ONLY")
        with _exclusive_file_lock(self.tunnel_admin_lock, timeout_seconds=30.0):
            config_path = self._prepare_tunnel_b_config()
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

    def tunnel_admin_start(self, instance: str) -> dict[str, Any]:
        key, spec = self._tunnel_spec(instance)
        with _exclusive_file_lock(self.tunnel_admin_lock, timeout_seconds=30.0):
            if self._task_state(spec["task"]) == "MISSING":
                raise BackendAdminError("TUNNEL_AUTOSTART_TASK_MISSING")
            self._task_command("Enable", [spec["task"], spec["watchdog"]])
            if not self._profile_pids(spec["profile"]):
                self._task_command("Start", [spec["task"]])
            self._task_command("Start", [spec["watchdog"]])
            ready = self._wait_instance_ready(key, 45)
            return self._receipt("tunnel_admin_start", "PASS", {"instance": key, "ready": ready})

    def tunnel_admin_stop(self, instance: str, confirm: bool = False) -> dict[str, Any]:
        key, spec = self._tunnel_spec(instance)
        if not bool(confirm):
            raise BackendAdminError("TUNNEL_STOP_CONFIRM_REQUIRED")
        with _exclusive_file_lock(self.tunnel_admin_lock, timeout_seconds=30.0):
            self._task_command("Stop", [spec["watchdog"], spec["task"], spec["background"]])
            self._task_command("Disable", [spec["watchdog"], spec["task"], spec["background"]])
            time.sleep(1)
            stopped = self._kill_profile_processes(spec["profile"])
            return self._receipt("tunnel_admin_stop", "PASS", {
                "instance": key, "stopped_pids": stopped, "status": self._tunnel_status_one(key),
            })

    def tunnel_admin_restart(self, instance: str, confirm: bool = False) -> dict[str, Any]:
        key, spec = self._tunnel_spec(instance)
        if not bool(confirm):
            raise BackendAdminError("TUNNEL_RESTART_CONFIRM_REQUIRED")
        with _exclusive_file_lock(self.tunnel_admin_lock, timeout_seconds=30.0):
            if self._task_state(spec["task"]) == "MISSING":
                raise BackendAdminError("TUNNEL_AUTOSTART_TASK_MISSING")
            self._task_command("Stop", [spec["task"], spec["background"]])
            time.sleep(1)
            stopped = self._kill_profile_processes(spec["profile"])
            self._task_command("Enable", [spec["task"], spec["watchdog"]])
            self._task_command("Start", [spec["task"], spec["watchdog"]])
            ready = self._wait_instance_ready(key, 45)
            return self._receipt("tunnel_admin_restart", "PASS", {
                "instance": key, "stopped_pids": stopped, "ready": ready,
            })

    @staticmethod
    def _casefold_path(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    def _under(self, path: Path, roots: Iterable[Path]) -> bool:
        rp = self._casefold_path(path)
        for root in roots:
            rr = self._casefold_path(root)
            if rp == rr or rp.startswith(rr + os.sep):
                return True
        return False

    def _reject_unsafe_string(self, raw: str) -> None:
        if not raw or "\x00" in raw:
            raise BackendAdminError("INVALID_PATH")
        if raw.startswith("\\\\") or raw.startswith("\\\\?\\"):
            raise BackendAdminError("UNC_OR_DEVICE_PATH_FORBIDDEN")
        if ":" in raw[2:]:
            raise BackendAdminError("NTFS_ADS_FORBIDDEN")
        parts = PureWindowsPath(raw).parts
        if ".." in parts:
            raise BackendAdminError("PATH_TRAVERSAL_FORBIDDEN")

    def resolve_allowed(self, raw: str, *, mutable: bool = False, must_exist: bool = False) -> Path:
        self._reject_unsafe_string(raw)
        p = Path(raw)
        if not p.is_absolute():
            p = self.root / p
        # strict=False permits new files while still normalizing traversal.
        p = p.resolve(strict=False)
        roots = self.mutable_roots if mutable else self.allowed_roots
        if not self._under(p, roots):
            raise BackendAdminError("PATH_OUTSIDE_ALLOWLIST")
        # Parent symlink/junction escapes are caught by resolved path comparison.
        if must_exist and not p.exists():
            raise BackendAdminError("FILE_NOT_FOUND")
        if p.exists() and p.is_dir():
            raise BackendAdminError("DIRECTORY_NOT_ALLOWED")
        if p.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            raise BackendAdminError("FILE_EXTENSION_NOT_ALLOWED")
        return p

    def _receipt(self, operation: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
        op = new_id("BADMIN")
        rec = Receipt(op, operation, status, payload)
        path = self.receipt_root / f"{op}.json"
        write_json_atomic(path, rec.as_dict())
        out = rec.as_dict()
        out["receipt_path"] = str(path)
        return out

    def read_file(self, path: str, max_bytes: int = 262144) -> dict[str, Any]:
        p = self.resolve_allowed(path, must_exist=True)
        size = p.stat().st_size
        if size > min(max_bytes, self.MAX_FILE_BYTES):
            raise BackendAdminError("FILE_TOO_LARGE")
        data = p.read_bytes()
        try:
            text = data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = data.decode("utf-8-sig")
            encoding = "utf-8-sig"
        return {
            "status": "PASS",
            "path": str(p),
            "bytes": len(data),
            "sha256": sha256_file(p),
            "encoding": encoding,
            "content": text,
        }

    def get_file_hash(self, path: str) -> dict[str, Any]:
        p = self.resolve_allowed(path, must_exist=True)
        m = FileMeta.from_path(p)
        return {"status": "PASS", **m.__dict__}

    def create_checkpoint(self, paths: list[str], label: str = "") -> dict[str, Any]:
        if not paths:
            raise BackendAdminError("CHECKPOINT_PATHS_REQUIRED")
        cid = new_id("BADMCP")
        dst = self.backup_root / cid
        files = []
        dst.mkdir(parents=True, exist_ok=False)
        for raw in paths:
            src = self.resolve_allowed(raw, must_exist=True)
            rel = src.relative_to(self.root)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            files.append({
                "path": str(src),
                "relative_path": str(rel).replace("\\", "/"),
                "sha256": sha256_file(src),
                "bytes": src.stat().st_size,
            })
        manifest = {
            "schema_version": "1.0",
            "checkpoint_id": cid,
            "label": label,
            "root": str(self.root),
            "files": files,
        }
        write_json_atomic(dst / "manifest.json", manifest)
        return self._receipt("backend_create_checkpoint", "PASS", manifest)

    def _load_checkpoint(self, checkpoint_id: str) -> tuple[Path, dict[str, Any]]:
        if not re.fullmatch(r"BADMCP-[A-Za-z0-9-]+", checkpoint_id):
            raise BackendAdminError("INVALID_CHECKPOINT_ID")
        d = (self.backup_root / checkpoint_id).resolve()
        if not self._under(d, [self.backup_root]) or not d.is_dir():
            raise BackendAdminError("CHECKPOINT_NOT_FOUND")
        mf = d / "manifest.json"
        if not mf.is_file():
            raise BackendAdminError("CHECKPOINT_MANIFEST_MISSING")
        return d, json.loads(mf.read_text(encoding="utf-8"))

    def restore_checkpoint(
        self,
        checkpoint_id: str,
        paths: list[str] | None = None,
        expected_current_sha256_by_path: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        d, manifest = self._load_checkpoint(checkpoint_id)
        if not isinstance(expected_current_sha256_by_path, dict):
            raise BackendAdminError("RESTORE_EXPECTED_HASHES_REQUIRED")

        wanted = None
        if paths:
            wanted = {str(self.resolve_allowed(x, mutable=True, must_exist=False)) for x in paths}

        expected: dict[str, str] = {}
        for raw_path, raw_sha in expected_current_sha256_by_path.items():
            target = self.resolve_allowed(raw_path, mutable=True, must_exist=False)
            key = str(target)
            value = str(raw_sha or "").strip().lower()
            if value and not re.fullmatch(r"[0-9a-f]{64}", value):
                raise BackendAdminError("RESTORE_EXPECTED_HASH_INVALID")
            if key in expected and expected[key] != value:
                raise BackendAdminError("RESTORE_EXPECTED_HASH_CONFLICT")
            expected[key] = value

        candidates: list[tuple[Path, Path, str, str]] = []
        for entry in manifest["files"]:
            target = self.resolve_allowed(entry["path"], mutable=True, must_exist=False)
            key = str(target)
            if wanted is not None and key not in wanted:
                continue
            src = d / entry["relative_path"]
            candidates.append((src, target, str(entry["sha256"]).lower(), key))

        selected = {key for _, _, _, key in candidates}
        if wanted is not None and selected != wanted:
            raise BackendAdminError("CHECKPOINT_DOES_NOT_COVER_FILE")
        if not selected:
            raise BackendAdminError("CHECKPOINT_RESTORE_PATHS_REQUIRED")
        if set(expected) != selected:
            raise BackendAdminError("RESTORE_EXPECTED_HASH_TARGET_MISMATCH")

        # Preflight every source and target before the first write. A stale target
        # therefore cannot produce a partially restored multi-file checkpoint.
        before: dict[str, str] = {}
        for src, target, checkpoint_sha, key in candidates:
            if not src.is_file() or sha256_file(src).lower() != checkpoint_sha:
                raise BackendAdminError("CHECKPOINT_FILE_INTEGRITY_FAILED")
            current = sha256_file(target).lower() if target.is_file() else ""
            if current != expected[key]:
                raise BackendAdminError(f"CAS_MISMATCH:{key}:{current or 'MISSING'}")
            before[key] = current

        restored = []
        for src, target, _, key in candidates:
            self._atomic_copy(src, target)
            restored.append({
                "path": key,
                "sha256_before": before[key],
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
            })
        return self._receipt("backend_restore_checkpoint", "PASS", {
            "checkpoint_id": checkpoint_id,
            "restored": restored,
        })

    def _checkpoint_has(self, checkpoint_id: str, target: Path) -> bool:
        _, manifest = self._load_checkpoint(checkpoint_id)
        t = str(target)
        return any(str(self.resolve_allowed(x["path"], must_exist=False)) == t for x in manifest["files"])

    def _require_cas(self, target: Path, expected_sha256: str, checkpoint_id: str) -> str:
        if not target.exists():
            if expected_sha256:
                raise BackendAdminError("EXPECTED_HASH_FOR_MISSING_FILE")
            return ""
        current = sha256_file(target)
        if not expected_sha256 or current.lower() != expected_sha256.lower():
            raise BackendAdminError(f"CAS_MISMATCH:{current}")
        if not checkpoint_id or not self._checkpoint_has(checkpoint_id, target):
            raise BackendAdminError("CHECKPOINT_DOES_NOT_COVER_FILE")
        return current

    def _atomic_bytes(self, target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=target.name+".", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _atomic_copy(self, src: Path, target: Path) -> None:
        self._atomic_bytes(target, src.read_bytes())

    def write_file(self, path: str, content: str, expected_sha256: str, checkpoint_id: str) -> dict[str, Any]:
        target = self.resolve_allowed(path, mutable=True, must_exist=False)
        before = self._require_cas(target, expected_sha256, checkpoint_id)
        data = content.encode("utf-8")
        if len(data) > self.MAX_FILE_BYTES:
            raise BackendAdminError("FILE_TOO_LARGE")
        self._atomic_bytes(target, data)
        return self._receipt("backend_write_file", "PASS", {
            "path": str(target),
            "checkpoint_id": checkpoint_id,
            "sha256_before": before,
            "sha256_after": sha256_file(target),
            "bytes_after": target.stat().st_size,
        })

    def apply_patch(self, path: str, expected_sha256: str, checkpoint_id: str, patch: str) -> dict[str, Any]:
        target = self.resolve_allowed(path, mutable=True, must_exist=True)
        before = self._require_cas(target, expected_sha256, checkpoint_id)
        old = target.read_text(encoding="utf-8")
        new = self._apply_unified_patch_single_file(old, patch)
        self._atomic_bytes(target, new.encode("utf-8"))
        return self._receipt("backend_apply_patch", "PASS", {
            "path": str(target),
            "checkpoint_id": checkpoint_id,
            "sha256_before": before,
            "sha256_after": sha256_file(target),
            "bytes_after": target.stat().st_size,
        })

    @staticmethod
    def _apply_unified_patch_single_file(original: str, patch: str) -> str:
        # Minimal deterministic unified-diff applicator; exact context required.
        src = original.splitlines(keepends=True)
        lines = patch.splitlines(keepends=True)
        hunks = []
        i = 0
        hdr = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        while i < len(lines):
            m = hdr.match(lines[i])
            if not m:
                i += 1
                continue
            old_start = int(m.group(1))
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("@@ "):
                if lines[i].startswith(("--- ", "+++ ")):
                    break
                body.append(lines[i])
                i += 1
            hunks.append((old_start, body))
        if not hunks:
            raise BackendAdminError("PATCH_HAS_NO_HUNKS")
        out = []
        src_idx = 0
        for old_start, body in hunks:
            target_idx = old_start - 1
            if target_idx < src_idx or target_idx > len(src):
                raise BackendAdminError("PATCH_HUNK_RANGE_INVALID")
            out.extend(src[src_idx:target_idx])
            src_idx = target_idx
            for line in body:
                if not line:
                    continue
                tag = line[0]
                payload = line[1:]
                if tag == " ":
                    if src_idx >= len(src) or src[src_idx] != payload:
                        raise BackendAdminError("PATCH_CONTEXT_MISMATCH")
                    out.append(src[src_idx]); src_idx += 1
                elif tag == "-":
                    if src_idx >= len(src) or src[src_idx] != payload:
                        raise BackendAdminError("PATCH_DELETE_MISMATCH")
                    src_idx += 1
                elif tag == "+":
                    out.append(payload)
                elif tag == "\\":
                    continue
                else:
                    raise BackendAdminError("PATCH_FORMAT_INVALID")
        out.extend(src[src_idx:])
        return "".join(out)

    def import_hotfix(self, uploaded_path: str, expected_sha256: str) -> dict[str, Any]:
        src = Path(uploaded_path)
        if not src.is_file():
            raise BackendAdminError("HOTFIX_FILE_NOT_FOUND")
        if src.suffix.lower() not in self.HOTFIX_EXTENSIONS:
            raise BackendAdminError("HOTFIX_EXTENSION_NOT_ALLOWED")
        if src.stat().st_size > self.MAX_HOTFIX_BYTES:
            raise BackendAdminError("HOTFIX_TOO_LARGE")
        actual = sha256_file(src)
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise BackendAdminError("HOTFIX_SHA256_MISMATCH")
        ref = f"HOTFIX-{actual[:24]}"
        dst_dir = self.inbox_root / actual
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if dst.exists() and sha256_file(dst) != actual:
            raise BackendAdminError("HOTFIX_OBJECT_COLLISION")
        if not dst.exists():
            shutil.copy2(src, dst)
        return self._receipt("backend_import_hotfix", "PASS", {
            "bundle_ref": ref,
            "path": str(dst),
            "sha256": actual,
            "bytes": dst.stat().st_size,
        })

    def _safe_zip_members(self, z: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        infos = z.infolist()
        total = 0
        for info in infos:
            name = info.filename.replace("\\", "/")
            pp = Path(name)
            if name.startswith("/") or ".." in pp.parts or ":" in name:
                raise BackendAdminError("HOTFIX_ZIP_TRAVERSAL")
            if info.is_dir():
                continue
            # Unix symlink type.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise BackendAdminError("HOTFIX_ZIP_SYMLINK_FORBIDDEN")
            total += info.file_size
            if total > self.MAX_HOTFIX_BYTES:
                raise BackendAdminError("HOTFIX_ZIP_EXPANDED_TOO_LARGE")
        return infos

    def apply_hotfix_bundle(self, bundle_path: str) -> dict[str, Any]:
        bundle = Path(bundle_path)
        if not bundle.is_file() or bundle.suffix.lower() != ".zip":
            raise BackendAdminError("HOTFIX_ZIP_REQUIRED")
        with zipfile.ZipFile(bundle, "r") as z:
            self._safe_zip_members(z)
            try:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            except KeyError:
                raise BackendAdminError("HOTFIX_MANIFEST_MISSING")
            if manifest.get("schema_version") != "1.0":
                raise BackendAdminError("HOTFIX_MANIFEST_SCHEMA_UNSUPPORTED")
            mutations = manifest.get("mutations") or []
            if not mutations:
                raise BackendAdminError("HOTFIX_MUTATIONS_REQUIRED")
            paths = [m["path"] for m in mutations]
            cp = self.create_checkpoint(paths, label=manifest.get("name","hotfix"))
            cid = cp["payload"]["checkpoint_id"]
            applied = []
            try:
                for m in mutations:
                    action = m.get("action")
                    path = m["path"]
                    expected = m.get("expected_sha256","")
                    if action == "write":
                        member = m["member"]
                        data = z.read(member).decode("utf-8")
                        applied.append(self.write_file(path, data, expected, cid))
                    elif action == "patch":
                        member = m["member"]
                        diff = z.read(member).decode("utf-8")
                        applied.append(self.apply_patch(path, expected, cid, diff))
                    else:
                        raise BackendAdminError("HOTFIX_ACTION_NOT_ALLOWED")
                tests = []
                for suite in manifest.get("tests", []):
                    tests.append(self.run_tests(suite))
                    if tests[-1]["status"] != "PASS":
                        raise BackendAdminError(f"HOTFIX_TEST_FAILED:{suite}")
                return self._receipt("backend_apply_hotfix_bundle", "PASS", {
                    "checkpoint_id": cid,
                    "bundle_sha256": sha256_file(bundle),
                    "applied_count": len(applied),
                    "tests": tests,
                })
            except Exception:
                # The outer backend mutation request owns the serialized mutation
                # lease. Roll back only files whose exact post-write hash we hold.
                rollback_expected = {
                    item["payload"]["path"]: item["payload"]["sha256_after"]
                    for item in applied
                }
                if rollback_expected:
                    self.restore_checkpoint(
                        cid,
                        paths=list(rollback_expected),
                        expected_current_sha256_by_path=rollback_expected,
                    )
                raise

    def _run(self, argv: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv, cwd=str(self.root), capture_output=True, text=True,
            timeout=timeout, check=False
        )

    def _append_powershell_audit(self, record: dict[str, Any]) -> None:
        path = self.root / "state" / "powershell-audit.jsonl"
        lock_path = self.root / "state" / "concurrency" / "powershell-audit.lock"
        line = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        with _exclusive_file_lock(lock_path, timeout_seconds=5.0):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())

    @staticmethod
    def _shell_child_environment() -> dict[str, str]:
        return {
            key: value
            for key, value in os.environ.items()
            if not _SHELL_ENV_SECRET.search(key)
        }

    def _execute_powershell(self, script: str, timeout_seconds: int) -> dict[str, Any]:
        wrapped_script = (
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding = [Console]::OutputEncoding;\n" + script
        )
        script_payload = base64.b64encode(wrapped_script.encode("utf-16le")).decode("ascii")
        bootstrap = (
            "$payload=[Console]::In.ReadToEnd();"
            "$scriptText=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($payload));"
            "$ErrorActionPreference='Stop';"
            "try { Invoke-Expression -Command $scriptText; "
            "if ($null -ne $global:LASTEXITCODE) { exit [int]$global:LASTEXITCODE }; exit 0 } "
            "catch { [Console]::Error.WriteLine($_.ToString()); exit 1 }"
        )
        encoded_bootstrap = base64.b64encode(bootstrap.encode("utf-16le")).decode("ascii")
        env = self._shell_child_environment()
        argv = [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-EncodedCommand", encoded_bootstrap,
        ]
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(self.root),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError:
            return {
                "status": "FAILED",
                "reason_code": "POWERSHELL_START_FAILED",
                "process_exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "output_truncated": False,
                "output_redactions": 0,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }

        stdout_capture: dict[str, Any] = {}
        stderr_capture: dict[str, Any] = {}
        readers = [
            threading.Thread(
                target=_capture_bounded_stream,
                args=(process.stdout, self.MAX_POWERSHELL_OUTPUT_BYTES, stdout_capture),
                daemon=True,
            ),
            threading.Thread(
                target=_capture_bounded_stream,
                args=(process.stderr, self.MAX_POWERSHELL_OUTPUT_BYTES, stderr_capture),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()

        input_failed = False
        try:
            process.stdin.write(script_payload.encode("ascii"))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            input_failed = True
            try:
                process.stdin.close()
            except OSError:
                pass

        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        env=env,
                        timeout=10,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        for reader in readers:
            reader.join(timeout=10)

        stdout_raw = stdout_capture.get("data", b"").decode("utf-8", errors="replace")
        stderr_raw = stderr_capture.get("data", b"").decode("utf-8", errors="replace")
        stdout, stdout_redactions = _redact_shell_output(stdout_raw)
        stderr, stderr_redactions = _redact_shell_output(stderr_raw)
        exit_code = process.returncode
        reason_code = (
            "POWERSHELL_TIMEOUT" if timed_out
            else "POWERSHELL_INPUT_FAILED" if input_failed
            else None
        )
        return {
            "status": "TIMEOUT" if timed_out else ("FAILED" if input_failed or exit_code != 0 else "PASS"),
            "reason_code": reason_code,
            "process_exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_bytes": int(stdout_capture.get("total_bytes", 0)),
            "stderr_bytes": int(stderr_capture.get("total_bytes", 0)),
            "output_truncated": bool(
                stdout_capture.get("truncated") or stderr_capture.get("truncated")
            ),
            "output_redactions": stdout_redactions + stderr_redactions,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    def run_powershell(
        self,
        script: str,
        confirm: bool = False,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        operation_id = new_id("PSHELL")
        if confirm is not True:
            return {
                "operation_id": operation_id,
                "operation": "backend_run_powershell",
                "status": "BLOCKED",
                "payload": {"reason_code": "EXPLICIT_CONFIRMATION_REQUIRED"},
            }
        if not isinstance(script, str) or not script.strip():
            raise BackendAdminError("POWERSHELL_SCRIPT_REQUIRED")
        if len(script) > self.MAX_POWERSHELL_SCRIPT_CHARS:
            raise BackendAdminError("POWERSHELL_SCRIPT_TOO_LARGE")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= self.MAX_POWERSHELL_TIMEOUT_SECONDS:
            raise BackendAdminError("POWERSHELL_TIMEOUT_OUT_OF_RANGE")

        script_sha256 = hashlib.sha256(script.encode("utf-8")).hexdigest()
        actor = current_actor()
        audit_base = {
            "schema_version": "1.0",
            "operation_id": operation_id,
            "command_sha256": script_sha256,
            "timeout_seconds": timeout_seconds,
            "client_key": actor.get("client_key", ""),
            "attribution_strength": actor.get("attribution_strength", "LOCAL_ONLY"),
            "security_identity": False,
        }
        started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self.concurrency.mutation(
            "backend_run_powershell", resource=script_sha256, wait_seconds=30.0
        ):
            with self.concurrency.native_execution(
                operation_id, kind="generic_powershell", wait_seconds=30.0
            ):
                self._append_powershell_audit({
                    **audit_base, "event": "STARTED", "at_utc": started_at,
                })
                try:
                    result = self._execute_powershell(script, timeout_seconds)
                except Exception:
                    result = {
                        "status": "FAILED",
                        "reason_code": "POWERSHELL_EXECUTION_FAILED",
                        "process_exit_code": None,
                        "stdout": "",
                        "stderr": "",
                        "stdout_bytes": 0,
                        "stderr_bytes": 0,
                        "output_truncated": False,
                        "output_redactions": 0,
                        "duration_ms": 0,
                    }
                finished_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                final_audit_ok = True
                try:
                    self._append_powershell_audit({
                        **audit_base,
                        "event": "FINISHED",
                        "at_utc": finished_at,
                        "status": result["status"],
                        "process_exit_code": result["process_exit_code"],
                        "stdout_bytes": result["stdout_bytes"],
                        "stderr_bytes": result["stderr_bytes"],
                        "output_truncated": result["output_truncated"],
                    })
                except Exception:
                    final_audit_ok = False

        powershell_status = result["status"]
        result.update({
            "powershell_status": powershell_status,
            "status": powershell_status if final_audit_ok else "AUDIT_INCOMPLETE",
            "reason_code": result.get("reason_code") or (
                None if final_audit_ok else "POWERSHELL_FINAL_AUDIT_FAILED"
            ),
            "command_sha256": script_sha256,
            "started_at_utc": started_at,
            "finished_at_utc": finished_at,
            "audit_status": "COMPLETE" if final_audit_ok else "FINAL_RECORD_FAILED",
        })
        return {
            "operation_id": operation_id,
            "operation": "backend_run_powershell",
            "status": result["status"],
            "payload": result,
        }

    def run_tests(self, suite: str) -> dict[str, Any]:
        if suite not in self.TEST_SUITES:
            raise BackendAdminError("TEST_SUITE_NOT_ALLOWED")
        py = str(self.python)
        if suite == "py_compile":
            targets = [str(p) for p in (self.root/"app"/"vibemql5").rglob("*.py")]
            cp = self._run([py, "-m", "py_compile", *targets], timeout=180)
        elif suite == "unit":
            cp = self._run([py, "-m", "pytest", "-q", str(self.root/"tests"/"unit")], timeout=300)
        elif suite == "runtime_forensics":
            cp = self._run([py, "-m", "pytest", "-q", "-k", "runtime_forensics", str(self.root/"tests")], timeout=300)
        elif suite == "tip026":
            cp = self._run([py, "-m", "pytest", "-q", "-k", "tip026", str(self.root/"tests")], timeout=300)
        elif suite == "tip033_soak":
            provenance_path = self.root / "config" / "build-provenance.json"
            if not provenance_path.is_file():
                raise BackendAdminError("TIP033_SOAK_PROVENANCE_MISSING")
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            bridge_build = str(provenance.get("bridge_build") or "").strip()
            if not bridge_build:
                raise BackendAdminError("TIP033_SOAK_BRIDGE_BUILD_MISSING")
            config_path = self.root / "ops" / "windows" / "vibemql5.windows.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            raw_state = str((config.get("supervisor") or {}).get("resilienceStateFile") or "").strip()
            if not raw_state:
                raise BackendAdminError("TIP033_SOAK_STATE_PATH_MISSING")
            state_path = Path(raw_state)
            if not state_path.is_absolute():
                state_path = self.root / state_path
            if state_path.is_file():
                try:
                    current = json.loads(state_path.read_text(encoding="utf-8-sig"))
                    updated = str(current.get("updated_at_utc") or "").strip()
                    if current.get("last_status") == "RUNNING" and str(current.get("bridge_build") or "") == bridge_build and updated:
                        stamp = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
                        if age < 90:
                            return {"status":"STARTED","suite":suite,"recovered":True,"bridge_build":bridge_build,"state_path":str(state_path)}
                except Exception:
                    pass
            script = self.root / "ops" / "windows" / "Invoke-TIP013Soak.ps1"
            if not script.is_file():
                raise BackendAdminError("TIP033_SOAK_SCRIPT_MISSING")
            rid = new_id("SOAK")
            stdout_path = self.receipt_root / f"{rid}.stdout.log"
            stderr_path = self.receipt_root / f"{rid}.stderr.log"
            args = [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-ConfigPath", str(config_path),
                "-DurationMinutes", "60", "-SampleSeconds", "30", "-MaxConsecutiveBad", "0",
                "-BridgeBuild", bridge_build, "-CertifyCurrentRuntime",
            ]
            flags = (0x00000200 | 0x08000000) if os.name == "nt" else 0
            out = stdout_path.open("ab", buffering=0); err = stderr_path.open("ab", buffering=0)
            try:
                proc = subprocess.Popen(args, cwd=str(self.root), close_fds=True, creationflags=flags, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            finally:
                out.close(); err.close()
            return {"status":"STARTED","suite":suite,"recovered":False,"bridge_build":bridge_build,"controller_pid":proc.pid,"state_path":str(state_path),"stdout":str(stdout_path),"stderr":str(stderr_path)}
        else:
            # Standalone baseline-aware gate uses an on-disk approved baseline list.
            baseline = self.receipt_root / "approved-unit-failures.json"
            baseline_state = "PRESENT" if baseline.is_file() else "MISSING"
            expected = set(json.loads(baseline.read_text(encoding="utf-8"))) if baseline.is_file() else set()
            xml = self.receipt_root / f"pytest-{new_id('RUN')}.xml"
            cp = self._run([py, "-m", "pytest", "-q", str(self.root/"tests"/"unit"), f"--junitxml={xml}"], timeout=300)
            current = self._failure_ids(xml)
            new = sorted(current - expected)
            return {
                "status": "PASS" if not new else "FAIL",
                "suite": suite,
                "returncode": cp.returncode,
                "baseline_failures": len(expected),
                "current_failures": len(current),
                "new_failures": new,
                "stdout_tail": cp.stdout[-4096:],
                "stderr_tail": cp.stderr[-4096:],
            }
        return {
            "status": "PASS" if cp.returncode == 0 else "FAIL",
            "suite": suite,
            "returncode": cp.returncode,
            "stdout_tail": cp.stdout[-4096:],
            "stderr_tail": cp.stderr[-4096:],
        }

    @staticmethod
    def _failure_ids(xml_path: Path) -> set[str]:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        out = set()
        for tc in root.iter("testcase"):
            if tc.find("failure") is not None or tc.find("error") is not None:
                out.add(f"{tc.get('classname','')}::{tc.get('name','')}")
        return out

    def read_evidence(self, relative_path: str, max_bytes: int = 262144) -> dict[str, Any]:
        if relative_path.startswith("\\") or ".." in Path(relative_path).parts:
            raise BackendAdminError("EVIDENCE_PATH_INVALID")
        p = (self.root / "evidence" / "runtime" / relative_path).resolve(strict=False)
        if not self._under(p, [self.root/"evidence"/"runtime"]) or not p.is_file():
            raise BackendAdminError("EVIDENCE_NOT_FOUND")
        if p.stat().st_size > max_bytes:
            raise BackendAdminError("EVIDENCE_TOO_LARGE")
        raw = p.read_bytes()
        return {
            "status": "PASS",
            "path": str(p),
            "bytes": len(raw),
            "sha256": sha256_file(p),
            "content": raw.decode("utf-8", errors="replace"),
        }

    def schedule_restart(self, components: list[str], wait_ready_seconds: int = 15) -> dict[str, Any]:
        allowed = {"http_mcp", "interactive_tunnel"}
        if not components or any(x not in allowed for x in components):
            raise BackendAdminError("RESTART_COMPONENT_NOT_ALLOWED")
        controller = self.root / "scripts" / "backend-admin-restart.ps1"
        if not controller.is_file():
            raise BackendAdminError("RESTART_CONTROLLER_MISSING")
        rid = new_id("BRESTART")
        receipt = self.receipt_root / f"{rid}.json"
        args = [
            "powershell.exe", "-NoProfile", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(controller),
            "-Root", str(self.root),
            "-ReceiptPath", str(receipt),
            "-Components", ",".join(components),
            "-WaitReadySeconds", str(max(5, min(wait_ready_seconds, 60))),
        ]
        stdout_path = self.receipt_root / f"{rid}.stdout.log"
        stderr_path = self.receipt_root / f"{rid}.stderr.log"

        def spawn_with_flags(flags: int) -> subprocess.Popen:
            out = stdout_path.open("ab", buffering=0)
            err = stderr_path.open("ab", buffering=0)
            try:
                return subprocess.Popen(
                    args,
                    cwd=str(self.root),
                    close_fds=True,
                    creationflags=flags,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                )
            finally:
                out.close()
                err.close()

        # Windows:
        # CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        # Breakaway prevents the restart controller from being killed with the
        # MCP process tree it is responsible for restarting.
        if os.name == "nt":
            preferred_flags = 0x01000000 | 0x00000200 | 0x08000000
            fallback_flags = 0x00000200 | 0x08000000
        else:
            preferred_flags = 0
            fallback_flags = 0

        launcher_mode = "BREAKAWAY"
        launch_error = ""
        try:
            proc = spawn_with_flags(preferred_flags)
        except OSError as exc:
            launch_error = f"{type(exc).__name__}:{exc}"
            launcher_mode = "FALLBACK_NO_BREAKAWAY"
            proc = spawn_with_flags(fallback_flags)

        return self._receipt("backend_restart_runtime", "RESTART_SCHEDULED", {
            "restart_id": rid,
            "components": components,
            "restart_receipt": str(receipt),
            "controller_pid": proc.pid,
            "launcher_mode": launcher_mode,
            "preferred_launch_error": launch_error,
            "controller_stdout": str(stdout_path),
            "controller_stderr": str(stderr_path),
            "terminal_touched": False,
        })
