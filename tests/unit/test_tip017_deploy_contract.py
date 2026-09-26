from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLY = (ROOT / "ops" / "windows" / "Apply-TIP017.ps1").read_text(encoding="utf-8")
TEST = (ROOT / "ops" / "windows" / "Test-TIP017.ps1").read_text(encoding="utf-8")
QUALIFY = (ROOT / "ops" / "windows" / "Invoke-TIP017ReleaseQualification.ps1").read_text(encoding="utf-8")
CLI = (ROOT / "app" / "vibemql5" / "adapters" / "cli.py").read_text(encoding="utf-8")
COMPILER = (ROOT / "app" / "vibemql5" / "core" / "compiler.py").read_text(encoding="utf-8")
RELEASE = (ROOT / "app" / "vibemql5" / "core" / "release.py").read_text(encoding="utf-8")
PROV = (ROOT / "config" / "build-provenance.json").read_text(encoding="utf-8")


def test_tip017_version_build_tool_count_and_commands():
    assert '"bridge_version": "0.2.41"' in PROV
    assert '"bridge_build": "TIP-045"' in PROV
    assert '"mcp_tool_count": 79' in PROV
    for command in ("check-all", "attest", "ship"):
        assert f's.add_parser("{command}")' in CLI
    assert "len(REQUIRED_TOOLS)==41" in APPLY
    assert "len(REQUIRED_TOOLS)==41" in TEST


def test_tip017_apply_is_bound_to_tip016_closure_and_canonical_authority():
    for value in (
        "607375eccbdb6d86272c2854e83d5f6343f54b7042ab6f0731e42bf140bcf43c",
        "d70da9e3c3b9f4eaaf144ede6bc87240cf7f444aabc4f6172cbcddb774cd9c45",
        "REV-000004",
        "a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989",
        "a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c",
        "BT-20260831-001933-B0484B",
    ):
        assert value in APPLY
    for forbidden in ("workspaces", "state", "runs", "secrets", "evidence"):
        assert forbidden in APPLY
    assert "PROJECT_STATE.yaml" not in APPLY.split("$files=@(", 1)[1].split(")", 1)[0]


def test_tip017_immutable_ex5_and_xml_are_hash_bound_not_presence_only():
    assert 'run_dir / "compiled.ex5"' in COMPILER
    assert '"sha256": hashlib.sha256(raw).hexdigest()' in COMPILER
    assert '"source_kind": "derived_from_native_mt5_report"' in RELEASE
    assert 'xml_source.get("sha256") == native_rec.get("sha256")' in RELEASE
    assert 'xml_source.get("bytes")' in RELEASE


def test_tip017_qualification_closes_exact_audit_gaps_and_never_promotes_forward_live():
    for marker in (
        "IMMUTABLE_RUN_BOUND_EX5=PASS",
        "NONEMPTY_HASH_BOUND_XML_REPORT=PASS",
        "RELEASE_PROVENANCE=PASS",
        "RELEASE_PIPELINE_COMMANDS=PASS check-all,attest,ship",
        "CANONICAL_RELEASE_MANIFEST_SCHEMA2=PASS",
        "release_eligible=true",
        "forward_eligible=false",
        "live_eligible=false",
    ):
        assert marker in QUALIFY
    assert "baseline_job_id=" not in QUALIFY.lower()
    assert "session-update" not in QUALIFY.lower()
    assert "iteration-accept" not in QUALIFY.lower()
