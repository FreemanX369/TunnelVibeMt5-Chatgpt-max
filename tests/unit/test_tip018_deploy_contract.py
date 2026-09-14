from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLY = (ROOT / "ops" / "windows" / "Apply-TIP018.ps1").read_text(encoding="utf-8")
TEST = (ROOT / "ops" / "windows" / "Test-TIP018.ps1").read_text(encoding="utf-8")
QUALIFY = (ROOT / "ops" / "windows" / "Invoke-TIP018ForwardQualification.ps1").read_text(encoding="utf-8")
CLI = (ROOT / "app" / "vibemql5" / "adapters" / "cli.py").read_text(encoding="utf-8")
FORWARD = (ROOT / "app" / "vibemql5" / "core" / "forward.py").read_text(encoding="utf-8")
PROV = (ROOT / "config" / "build-provenance.json").read_text(encoding="utf-8")


def test_tip018_version_build_tool_count_and_public_commands():
    assert '"bridge_version": "0.2.33"' in PROV
    assert '"bridge_build": "TIP-032R1"' in PROV
    assert '"mcp_tool_count": 67' in PROV
    for command in ("forward-check", "forward-attest", "forward-promote"):
        assert f's.add_parser("{command}")' in CLI
    assert "len(REQUIRED_TOOLS)==41" in APPLY
    assert "len(REQUIRED_TOOLS)==41" in TEST


def test_tip018_apply_is_bound_to_tip017_closure_release_and_owner_approval():
    for value in (
        "4e9008b0927eaee50939641344c26ae0c249fa0482ca8142449f480f96acdee3",
        "5c462bf08fca55b44d4f72c54e479304fd75ba072554e0b7590cdcd272fcf05f",
        "b1f48ec1bd1f52bc0000dd6effd01b52a1d770a0f501daa965e4d51e083b575e",
        "b9e1269848d39a6633641784f08adf7405a1677054838ca7ed7b5d0cd6de7764",
        "REV-000004",
        "a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989",
        "a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c",
        "BT-20260831-001933-B0484B",
        "BT-20260902-124524-9D17D6",
    ):
        assert value in APPLY
    assert "TIP018_OWNER_APPROVAL_GATE=PASS" in APPLY
    assert "PROJECT_STATE.yaml" not in APPLY.split("$files=@(", 1)[1].split(")", 1)[0]
    for forbidden in ("workspaces", "state", "runs", "secrets", "evidence"):
        assert forbidden in APPLY


def test_tip018_forward_pipeline_is_package_before_canonical_commit_and_live_false():
    package_pos = FORWARD.index("with zipfile.ZipFile")
    commit_pos = FORWARD.index("_atomic_write_bytes(canonical_path")
    assert package_pos < commit_pos
    assert 'canonical["forward_eligible"] = True' in FORWARD
    assert 'canonical["live_eligible"] = False' in FORWARD
    assert "FORWARD_CANONICAL_RELEASE_MANIFEST_DRIFT_BEFORE_COMMIT" in FORWARD


def test_tip018_qualification_runs_exact_approved_matrix_and_no_profitability_threshold():
    for role in ("FWD-SMOKE-CURRENT", "FWD-VALIDATION-L100-A", "FWD-VALIDATION-L100-B", "FWD-VALIDATION-L50", "FWD-VALIDATION-L200"):
        assert role in QUALIFY
    assert "STRESS_MATRIX=5/5_PASS" in QUALIFY
    assert "DETERMINISTIC_REPEAT=PASS" in QUALIFY
    assert "OWNER_APPROVAL_BINDING=PASS" in QUALIFY
    assert "forward_eligible=true" in QUALIFY
    assert "live_eligible=false" in QUALIFY
    for forbidden in ("profit_factor >", "net_profit >", "sharpe_ratio >", "max_drawdown_pct <"):
        assert forbidden not in QUALIFY


def test_tip018_apply_and_qualification_never_mutate_canonical_session_or_baseline():
    for script in (APPLY, QUALIFY):
        lower = script.lower()
        assert "session-update" not in lower
        assert "iteration-accept" not in lower
        assert "baseline_job_id=" not in lower
    assert "last_job_id']=='BT-20260831-001933-B0484B'" in QUALIFY


def test_tip018_verify_keeps_forward_false_until_real_qualification():
    for marker in (
        "TIP018_PYTHON_VERIFY",
        "TIP018_PROJECT_STATE_VERIFY=PASS",
        "TIP018_OWNER_APPROVAL_VERIFY=PASS",
        "TIP018_RELEASE_PRECONDITION_VERIFY=PASS",
        "TIP018_RUNTIME_VERIFY=PASS",
        "TIP018_VERIFY=PASS",
    ):
        assert marker in TEST
    assert "forward_eligible: false" in TEST
