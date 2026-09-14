from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLY = (ROOT / "ops" / "windows" / "Apply-TIP015C.ps1").read_text(encoding="utf-8")
TEST = (ROOT / "ops" / "windows" / "Test-TIP015C.ps1").read_text(encoding="utf-8")
MCP = (ROOT / "app" / "vibemql5" / "adapters" / "mcp.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_tip015c_version_tools_and_console_entrypoints():
    assert "__version__ = '0.2.34'" in (ROOT / "app" / "vibemql5" / "__init__.py").read_text(encoding="utf-8")
    assert 'mql5-retro-init = "vibemql5.adapters.retro_cli:retro_init_main"' in PYPROJECT
    assert 'vkmql-check = "vibemql5.adapters.retro_cli:vkmql_check_main"' in PYPROJECT
    assert "len(REQUIRED_TOOLS)==41" in APPLY
    assert "TIP-015C" in APPLY


def test_tip015c_only_adds_three_read_only_mcp_history_tools():
    for name in ("read_iteration_history", "list_fault_receipts", "list_job_history"):
        assert f"def {name}" in MCP
    # No fault-control/mutation history API is exposed.
    for forbidden in ("arm_fault", "clear_fault", "delete_history", "restore_history"):
        assert forbidden not in MCP.lower()


def test_tip015c_payload_forbids_runtime_workspace_and_secret_state():
    for forbidden in ("workspaces", "state", "runs", "secrets"):
        assert forbidden in APPLY
    assert "TIP015C_FORBIDDEN_PAYLOAD_PATH" in APPLY
    assert "TIP015C-PAYLOAD-MANIFEST.sha256" in APPLY


def test_tip015c_windows_gate_preserves_canonical_authority():
    for value in (
        "TIP014-DEMOEA-E2E-20260830",
        "REV-000004",
        "a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989",
        "a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c",
        "BT-20260831-001933-B0484B",
    ):
        assert value in APPLY
        assert value in TEST
    assert "queue_length" in TEST and "active_job" in TEST


def test_tip015c_windows_gate_exercises_observability_and_retro_packaging():
    for token in (
        "iteration_history",
        "fault_receipts",
        "job_history",
        "mql5-retro-init",
        "vkmql-check",
        "UNTESTABLE",
    ):
        assert token in TEST
