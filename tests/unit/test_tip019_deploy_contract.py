from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLY = (ROOT / "ops" / "windows" / "Apply-TIP019.ps1").read_text(encoding="utf-8")
TEST = (ROOT / "ops" / "windows" / "Test-TIP019.ps1").read_text(encoding="utf-8")
CLI = (ROOT / "app" / "vibemql5" / "adapters" / "cli.py").read_text(encoding="utf-8")
LIVE = (ROOT / "app" / "vibemql5" / "core" / "live_readiness.py").read_text(encoding="utf-8")
PROV = (ROOT / "config" / "build-provenance.json").read_text(encoding="utf-8")
INVOKE = (ROOT / "ops" / "windows" / "Invoke-TIP019ReadOnlyQualification.ps1").read_text(encoding="utf-8")


def test_tip019_version_build_tools_and_commands():
    assert '"bridge_version": "0.2.34"' in PROV
    assert '"bridge_build": "TIP-033RC1"' in PROV
    assert '"mcp_tool_count": 72' in PROV
    for command in ("live-check", "live-attest", "live-package"):
        assert f's.add_parser("{command}")' in CLI
    assert "len(REQUIRED_TOOLS)==41" in APPLY
    assert "len(REQUIRED_TOOLS)==41" in TEST


def test_tip019_apply_is_bound_to_closed_tip018_and_forward_manifest():
    for value in (
        "cf6e42bd19178bd606736a39284506d6ba69b6f4c814dff56909f9f3337a431d",
        "4d0d65e875fbcd054b3e522cdb116f207be7651565b71dff75ec620664df5793",
        "ec053a64318b9ebbbb8057871a91808c8ba81ed3a8e717ed939a1f7a72b36a89",
        "0590e1ec98d9c2e610febc30f6d09dcb9a4eef40fab8b10a28a65f2eea77ef76",
        "be308d7fd5a9891b113ecf908ba760d4856a9ed43e53064c8246110b81751b33",
    ):
        assert value in APPLY
    block = APPLY.split("$files=@(", 1)[1].split(")", 1)[0]
    assert "PROJECT_STATE.yaml" not in block
    for forbidden in ("workspaces", "state", "runs", "secrets", "evidence"):
        assert forbidden in APPLY


def test_tip019_candidate_packaging_never_promotes_canonical_live_flag():
    assert '"live_eligible": False' in LIVE
    assert '"automatic_promotion": False' in LIVE
    assert "LIVE_PACKAGE_MUTATED_CANONICAL_FORWARD_MANIFEST" in LIVE
    assert 'live_eligible"] = True' not in LIVE
    assert "_atomic_write_json(authority[\"release_path\"]" not in LIVE


def test_tip019_real_readonly_wrapper_has_no_trade_or_login_mutation():
    low = INVOKE.lower()
    for forbidden in ("mt5.order_send(", "mt5.order_check(", "login=", "password=", "toggle-autotrading"):
        assert forbidden not in low
    assert "live-check" in INVOKE and "live-attest" in INVOKE and "live-package" in INVOKE


def test_tip019_untestable_is_preserved_not_promoted():
    assert "TIP019_LIVE_CHECK=UNTESTABLE" in INVOKE
    assert "TIP019_LIVE_ATTEST=BLOCKED" in INVOKE
    assert "TIP019_LIVE_PACKAGE=BLOCKED" in INVOKE
    assert "live_eligible=false" in INVOKE
