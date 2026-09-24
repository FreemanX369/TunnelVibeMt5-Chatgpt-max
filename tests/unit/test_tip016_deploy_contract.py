from pathlib import Path
import hashlib
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
APPLY = (ROOT / "ops" / "windows" / "Apply-TIP016.ps1").read_text(encoding="utf-8")
TEST = (ROOT / "ops" / "windows" / "Test-TIP016.ps1").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
PROVENANCE = (ROOT / "config" / "build-provenance.json").read_text(encoding="utf-8")


def test_tip016_version_build_and_tool_count():
    assert "__version__ = '0.2.37'" in (ROOT / "app" / "vibemql5" / "__init__.py").read_text(encoding="utf-8")
    assert '"bridge_version": "0.2.37"' in PROVENANCE
    assert '"bridge_build": "TIP-041"' in PROVENANCE
    assert '"mcp_tool_count": 79' in PROVENANCE
    assert "len(REQUIRED_TOOLS)==41" in APPLY
    assert "len(REQUIRED_TOOLS)==41" in TEST


def test_tip016_payload_preserves_canonical_and_forbids_runtime_state():
    for value in (
        "TIP014-DEMOEA-E2E-20260830",
        "REV-000004",
        "a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989",
        "a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c",
        "BT-20260831-001933-B0484B",
        "12c8bd59ab54512aaf6fe32c857af93aa4346d9885b3d91f5e25f9a245ec13d5",
    ):
        assert value in APPLY
        assert value in TEST
    for forbidden in ("workspaces", "state", "runs", "secrets"):
        assert forbidden in APPLY
    assert "PROJECT_STATE.yaml" not in APPLY.split("$files=@(", 1)[1].split(")", 1)[0]


def test_tip016_hotfix2_locks_windows_powershell51_compatibility():
    helper = (ROOT / "ops" / "windows" / "VibeMQL5.AtomicFile.ps1").read_text(encoding="utf-8")
    assert "[IO.File]::Replace($tmp,$full,$backup,$true)" in helper
    assert "[IO.File]::Replace($tmp,$full,$null,$true)" not in helper
    assert "$current = $current.InnerException" in helper


def test_tip016_windows_verify_exercises_locked_destination_retry():
    for token in (
        "TIP016_WINDOWS_LOCKED_DESTINATION_RETRY=PASS",
        "FileShare]::None",
        "TIP016_ATOMIC_TEMP_CLEANUP=PASS",
        "TIP016_RUNTIME_VERIFY=PASS",
        "TIP016_VERIFY=PASS",
    ):
        assert token in TEST


def test_tip016_apply_has_transactional_program_file_rollback():
    for token in (
        "TIP016_ROLLBACK_BEGIN",
        "TIP016_ROLLBACK_FILES=PASS",
        "pip install -e",
        "TIP016_APPLY=PASS",
    ):
        assert token in APPLY


def _state_patch_code() -> str:
    marker = "$statePatch=@'\n"
    assert marker in APPLY
    return APPLY.split(marker, 1)[1].split("\n'@", 1)[0]


def test_tip016_project_state_patch_accepts_lf_and_crlf(tmp_path):
    state_patch = _state_patch_code()
    base_lines = [
        "schema_version: '1.0'",
        "project: VibeMQL5",
        "active_tip: TIP-015C",
        "phase: CLOSED",
        "bridge_target: 0.2.12",
        "bridge_build: TIP-015C",
        "release_eligible: false",
        "forward_eligible: false",
        "live_eligible: false",
    ]
    for newline in ("\n", "\r\n"):
        state = tmp_path / ("state-crlf.yaml" if newline == "\r\n" else "state-lf.yaml")
        raw = (newline.join(base_lines) + newline).encode("utf-8")
        state.write_bytes(raw)
        env = os.environ.copy()
        env["T16_STATE"] = str(state)
        env["T16_PRESTATE"] = hashlib.sha256(raw).hexdigest()
        run = subprocess.run(
            [sys.executable, "-c", state_patch],
            env=env,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stderr or run.stdout
        out = state.read_bytes()
        text = out.decode("utf-8")
        assert "active_tip: TIP-016" in text
        assert "phase: VERIFY" in text
        assert "bridge_target: 0.2.13" in text
        assert "bridge_build: TIP-016" in text
        assert "tip016:" in text
        if newline == "\r\n":
            assert b"\n" not in out.replace(b"\r\n", b"")


def test_tip016_project_state_patch_captures_native_error_before_trim():
    assert "$statePatchItems=@($statePatch|& $python - 2>&1)" in APPLY
    assert "$statePatchExit=$LASTEXITCODE" in APPLY
    assert "TIP016_PROJECT_STATE_PATCH_FAILED exit=$statePatchExit output=$statePatchText" in APPLY
    assert "TIP016_PROJECT_STATE_PATCH_INVALID_OUTPUT" in APPLY
