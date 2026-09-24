from __future__ import annotations

import base64
import io
import json
import os
import subprocess

import pytest

from vibemql5.backend_admin import core
from vibemql5.backend_admin.core import BackendAdmin, BackendAdminError


class _FakeProcess:
    pid = 4321
    returncode = 0

    def __init__(self, stdout: bytes = b"ok\n", stderr: bytes = b""):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.stdin = _InputBuffer()
        self.wait_calls = []

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode

    def kill(self):
        self.returncode = -9


class _InputBuffer:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)
        return len(data)

    def close(self):
        self.closed = True


def test_tip039_shell_requires_per_call_confirmation(tmp_path, monkeypatch):
    admin = BackendAdmin(tmp_path)
    monkeypatch.setattr(
        admin,
        "_execute_powershell",
        lambda *_args: pytest.fail("PowerShell must not start without confirmation"),
    )

    result = admin.run_powershell("Get-Date")

    assert result["status"] == "BLOCKED"
    assert result["payload"]["reason_code"] == "EXPLICIT_CONFIRMATION_REQUIRED"
    assert not (tmp_path / "state" / "powershell-audit.jsonl").exists()


def test_tip039_shell_redaction_covers_quoted_values_with_spaces():
    text = 'password="secret value with spaces" api_key=sk-livefixture123456'

    redacted, count = core._redact_shell_output(text)

    assert "secret value with spaces" not in redacted
    assert "sk-livefixture123456" not in redacted
    assert redacted == "[REDACTED] [REDACTED]"
    assert count == 3


def test_tip039_shell_uses_encoded_command_scrubs_env_and_audits_metadata(tmp_path, monkeypatch):
    admin = BackendAdmin(tmp_path)
    script = "Write-Output 'café'"
    captured = {}
    monkeypatch.setenv("CONTROL_PLANE_API_KEY", "sk-secret-fixture")
    monkeypatch.setenv("SAFE_FIXTURE", "kept")

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        process = _FakeProcess("café sk-secret-fixture\n".encode(), b"Bearer abcdefghijklmnop\n")
        captured["process"] = process
        return process

    monkeypatch.setattr(core.subprocess, "Popen", fake_popen)
    result = admin.run_powershell(script, confirm=True, timeout_seconds=15)

    assert result["status"] == "PASS"
    assert result["payload"]["stdout"].startswith("café [REDACTED]")
    assert "Bearer abcdefghijklmnop" not in result["payload"]["stderr"]
    assert result["payload"]["output_redactions"] == 2
    assert result["payload"]["audit_status"] == "COMPLETE"
    argv = captured["argv"]
    encoded_bootstrap = argv[argv.index("-EncodedCommand") + 1]
    bootstrap = base64.b64decode(encoded_bootstrap).decode("utf-16le")
    assert "Console]::In.ReadToEnd()" in bootstrap
    assert script not in bootstrap
    payload = bytes(captured["process"].stdin.data).decode("ascii")
    assert base64.b64decode(payload).decode("utf-16le").endswith("\n" + script)
    assert captured["process"].stdin.closed is True
    assert captured["cwd"] == str(tmp_path.resolve())
    assert "CONTROL_PLANE_API_KEY" not in captured["env"]
    assert captured["env"]["SAFE_FIXTURE"] == "kept"

    audit = (tmp_path / "state" / "powershell-audit.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in audit.splitlines()]
    assert [event["event"] for event in events] == ["STARTED", "FINISHED"]
    assert all(event["command_sha256"] == result["payload"]["command_sha256"] for event in events)
    assert script not in audit
    assert "sk-secret-fixture" not in audit
    assert list((tmp_path / "evidence" / "runtime" / "backend-admin").glob("*.json")) == []


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_tip039_shell_executes_powershell_and_cmd_on_windows(tmp_path):
    admin = BackendAdmin(tmp_path)
    script = (
        "$version = $PSVersionTable.PSVersion.ToString()\n"
        "Write-Output \"TIP039_PS_OK:$version\"\n"
        "cmd.exe /c echo TIP039_CMD_OK"
    )

    result = admin.run_powershell(script, confirm=True, timeout_seconds=30)

    assert result["status"] == "PASS", result["payload"]
    assert result["payload"]["process_exit_code"] == 0
    assert "TIP039_PS_OK:" in result["payload"]["stdout"]
    assert "TIP039_CMD_OK" in result["payload"]["stdout"]
    assert result["payload"]["audit_status"] == "COMPLETE"


def test_tip039_shell_bounds_script_timeout_and_output(tmp_path, monkeypatch):
    admin = BackendAdmin(tmp_path)
    with pytest.raises(BackendAdminError, match="POWERSHELL_SCRIPT_TOO_LARGE"):
        admin.run_powershell("x" * (admin.MAX_POWERSHELL_SCRIPT_CHARS + 1), confirm=True)
    with pytest.raises(BackendAdminError, match="POWERSHELL_TIMEOUT_OUT_OF_RANGE"):
        admin.run_powershell("Get-Date", confirm=True, timeout_seconds=301)
    with pytest.raises(BackendAdminError, match="POWERSHELL_TIMEOUT_OUT_OF_RANGE"):
        admin.run_powershell("Get-Date", confirm=True, timeout_seconds=True)

    monkeypatch.setattr(
        core.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _FakeProcess(b"x" * 40_000),
    )
    result = admin.run_powershell("Write-Output x", confirm=True)
    assert result["payload"]["stdout_bytes"] == 40_000
    assert len(result["payload"]["stdout"].encode("utf-8")) == admin.MAX_POWERSHELL_OUTPUT_BYTES
    assert result["payload"]["output_truncated"] is True


def test_tip039_shell_timeout_kills_process_and_reports_structured_failure(tmp_path, monkeypatch):
    admin = BackendAdmin(tmp_path)
    process = _FakeProcess()
    calls = []

    def wait(timeout=None):
        calls.append(timeout)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("powershell.exe", timeout)
        process.returncode = -9
        return process.returncode

    process.wait = wait
    monkeypatch.setattr(core.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        core.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0),
    )

    result = admin.run_powershell("Start-Sleep 20", confirm=True, timeout_seconds=1)

    assert result["status"] == "TIMEOUT"
    assert result["payload"]["reason_code"] == "POWERSHELL_TIMEOUT"
    assert process.returncode == -9
    assert calls == [1, 10]
