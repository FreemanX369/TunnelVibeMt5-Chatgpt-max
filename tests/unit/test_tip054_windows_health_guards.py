from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import subprocess

import pytest


OPS = Path(__file__).parents[2] / "ops" / "windows"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="PowerShell runtime required")


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_ps(body: str) -> dict:
    script = (
        "$ErrorActionPreference='Stop'\n"
        f". {ps_quote(str(OPS / 'VibeMQL5.AtomicFile.ps1'))}\n"
        + body
        + "\n$result | ConvertTo-Json -Depth 10 -Compress\n"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip())


@pytest.mark.parametrize(
    "code,failures,wrapped,nonterminating,expected_reads,expected_value",
    [
        (32, 1, False, False, 2, 7),
        (33, 1, True, False, 2, 7),
        (32, 1, False, True, 2, 7),
        (32, 10, False, False, 3, None),
        (5, 1, False, False, 1, None),
        (80, 1, False, False, 1, None),
    ],
)
def test_json_reader_retries_only_bounded_sharing_errors(
    tmp_path, code, failures, wrapped, nonterminating, expected_reads, expected_value
):
    path = tmp_path / "state.json"
    path.write_text('{"value":7}', encoding="utf-8")
    out = run_ps(
        f"$script:reads=0; $script:failures={failures}; $script:code={code}\n"
        f"$script:wrapped=${str(wrapped).lower()}; $script:nonterminating=${str(nonterminating).lower()}\n"
        "function Get-Content {\n"
        " [CmdletBinding()] param([string]$LiteralPath,[switch]$Raw,[string]$Encoding)\n"
        " $script:reads++\n"
        " if($script:reads -le $script:failures){\n"
        "  $exception=[IO.IOException]::new('fixture read conflict',(-2147024896 + $script:code))\n"
        "  if($script:wrapped){$exception=[Exception]::new('fixture wrapper',$exception)}\n"
        "  if($script:nonterminating){Write-Error -Exception $exception -Message 'fixture read conflict'; return}\n"
        "  throw $exception\n"
        " }\n"
        " Microsoft.PowerShell.Management\\Get-Content -LiteralPath $LiteralPath -Raw -Encoding $Encoding\n"
        "}\n"
        f"$value=Read-VibeJsonSafe -Path {ps_quote(str(path))}\n"
        "$result=@{reads=$script:reads;value=if($null -eq $value){$null}else{$value.value}}"
    )
    assert out == {"reads": expected_reads, "value": expected_value}


def test_json_reader_missing_and_malformed_fail_closed(tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{broken", encoding="utf-8")
    out = run_ps(
        f"$missing=Read-VibeJsonSafe -Path {ps_quote(str(tmp_path / 'missing.json'))}\n"
        f"$malformed=Read-VibeJsonSafe -Path {ps_quote(str(malformed))}\n"
        "$result=@{missing=($null -eq $missing);malformed=($null -eq $malformed)}"
    )
    assert out == {"missing": True, "malformed": True}


@pytest.mark.parametrize(
    "timestamp,expected_fresh",
    [
        ("2026-09-30T01:00:00Z", True),
        ("2026-09-30T08:00:00+07:00", True),
        ("2026-09-30T01:00:00", False),
    ],
)
def test_json_reader_preserves_timestamp_text_without_inventing_an_offset(tmp_path, timestamp, expected_fresh):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"heartbeat_utc": timestamp}), encoding="utf-8")
    out = run_ps(
        f"$state=Read-VibeJsonSafe -Path {ps_quote(str(path))}\n"
        "$now=[DateTimeOffset]::Parse('2026-09-30T01:00:10Z')\n"
        "$result=@{timestamp=$state.heartbeat_utc;is_string=($state.heartbeat_utc -is [string]);"
        "fresh=(Test-VibeHeartbeatFresh -Timestamp $state.heartbeat_utc -StaleSeconds 45 -Now $now)}"
    )
    assert out == {"timestamp": timestamp, "is_string": True, "fresh": expected_fresh}


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2026-09-30T01:00:00Z", True),
        ("2026-09-30T08:00:00+07:00", True),
        ("2026-09-30T00:59:25Z", False),  # Exactly the unchanged 45-second limit.
        ("2026-09-30T00:59:24Z", False),
        ("2026-09-30T01:00:11Z", False),  # A future clock never looks fresh.
        ("2026-09-30T01:00:00", False),
        ("invalid", False),
    ],
)
def test_heartbeat_uses_explicit_offsets_and_rejects_stale_or_future(timestamp, expected):
    out = run_ps(
        "$now=[DateTimeOffset]::Parse('2026-09-30T01:00:10Z')\n"
        f"$fresh=Test-VibeHeartbeatFresh -Timestamp {ps_quote(timestamp)} -StaleSeconds 45 -Now $now\n"
        "$result=@{fresh=$fresh}"
    )
    assert out["fresh"] is expected


@pytest.mark.parametrize(
    "history,expected_count,expected_cooldown,expected_budget",
    [
        (["2026-09-30T00:00:09Z"], 0, True, True),
        (["2026-09-30T01:00:00Z"], 1, False, True),
        (["2026-09-30T08:00:00+07:00"], 1, False, True),
        (["2026-09-30T00:58:09Z"], 1, True, True),
        (["2026-09-30T01:00:11Z", "2026-09-30T00:58:00Z"], 2, False, True),
        (["2026-09-30T01:00:11Z"] * 3, 3, False, False),
    ],
)
def test_watchdog_actual_history_block_uses_utc_and_conservative_future_budget(
    tmp_path, history, expected_count, expected_cooldown, expected_budget
):
    source = (OPS / "Invoke-VibeMQL5Watchdog.ps1").read_text(encoding="utf-8")
    # Execute the real budget/cooldown block, without running scheduled tasks,
    # HTTP probes, CIM calls, or changing the host clock.
    start = source.index("$history=@()")
    end = source.index('$action="NONE"', start)
    block = source[start:end]
    state = tmp_path / "watchdog-state.json"
    state.write_text(json.dumps({"restart_history_utc": history}), encoding="utf-8")
    out = run_ps(
        "$watchdogNow=[DateTimeOffset]::Parse('2026-09-30T01:00:10Z')\n"
        "$config=[pscustomobject]@{supervisor=[pscustomobject]@{watchdogRestartCooldownSeconds=120;maxRestartsPerHour=3}}\n"
        f"$previous=Read-VibeJsonSafe -Path {ps_quote(str(state))}\n"
        + block
        + "$result=@{count=$history.Count;cooldown=$cooldownOk;budget=$budgetOk}"
    )
    assert out == {
        "count": expected_count, "cooldown": expected_cooldown, "budget": expected_budget,
    }
