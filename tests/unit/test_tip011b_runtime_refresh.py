from __future__ import annotations

import hashlib
from pathlib import Path

from vibemql5.adapters.mcp import _runtime_provenance
from vibemql5.core.workspace import WorkspaceManager


def test_runtime_provenance_hashes_loaded_modules():
    p = _runtime_provenance()
    assert p["bridge_build"] == "TIP-041"
    assert p["bridge_version"] == "0.2.37"
    assert isinstance(p["pid"], int) and p["pid"] > 0
    for path_key, sha_key in (
        ("workspace_module_path", "workspace_module_sha256"),
        ("mcp_module_path", "mcp_module_sha256"),
    ):
        path = Path(p[path_key])
        assert path.is_file()
        assert p[sha_key] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_crlf_patch_is_byte_minimal_and_reports_format(tmp_path: Path):
    root = tmp_path / "VibeMQL5"
    src = root / "workspaces" / "demo" / "Experts" / "DemoEA.mq5"
    src.parent.mkdir(parents=True)
    lines = [b"#property strict"] + [f"// line {i:02d}".encode() for i in range(1, 66)]
    original = b"\r\n".join(lines) + b"\r\n"
    src.write_bytes(original)
    w = WorkspaceManager(root)
    before = w._current_sha(src)
    out = w.apply_patch(
        "demo", "Experts/DemoEA.mq5",
        [{"old": "#property strict", "new": "// TIP011A_BYTE_PRESERVE\n#property strict"}],
        expected_sha256=before,
    )
    expected = b"// TIP011A_BYTE_PRESERVE\r\n" + original
    assert src.read_bytes() == expected
    assert len(expected) == len(original) + 26
    assert out["bytes"] == len(original) + 26
    assert out["newline_style"] == "CRLF"
    assert out["utf8_bom"] is False
    assert out["format_preserved"] is True


def test_restart_controller_stops_only_exact_control_plane_trees_and_protects_mt5():
    script = (Path(__file__).parents[2] / "scripts" / "backend-admin-restart.ps1").read_text(encoding="utf-8")
    assert "Get-CimInstance Win32_Process" in script
    assert "run-mcp-task\\.ps1" in script
    assert "Start-VibeMQL5InteractiveEntry\\.ps1" in script
    assert "Stop-ProcessTreeSafe" in script
    for protected in ("terminal64.exe", "metatester64.exe", "metaeditor64.exe"):
        assert protected in script
    assert "terminal_touched = $false" in script
    assert "RESTART_TARGET_PROTECTED" in script
