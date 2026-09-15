import json

import pytest

from app.vibemql5.core.inventory import TerminalInventory
from app.vibemql5.core.project_sessions import ProjectSessionManager
from app.vibemql5.runtime_forensics.service import (
    AuthorityError,
    RuntimeForensicsManager,
)


def test_terminal_inventory_labels_configured_and_observed_builds(tmp_path):
    root = tmp_path / "VibeMQL5"
    (root / "config").mkdir(parents=True)
    (root / "config" / "terminals.json").write_text(
        json.dumps({
            "terminals": [{
                "alias": "MT5-2",
                "terminal_path": str(root / "terminal64.exe"),
                "metaeditor_path": str(root / "MetaEditor64.exe"),
                "data_hash": "fixture",
                "data_root": str(root / "data"),
                "build": 6140,
                "enabled": True,
            }]
        }),
        encoding="utf-8",
    )
    run = root / "runs" / "BT-OBSERVED"
    run.mkdir(parents=True)
    (run / "result.json").write_text(
        json.dumps({
            "job_id": "BT-OBSERVED",
            "recorded_at_utc": "2026-09-14T09:35:59Z",
            "environment": {
                "terminal": "MT5-2",
                "terminal_build_at_execution": 6182,
            },
        }),
        encoding="utf-8",
    )

    item = TerminalInventory(root).describe()[0]
    assert item["configured_build"] == 6140
    assert item["observed_build"] == 6182
    assert item["build"] == 6182
    assert item["build_source"] == "LATEST_COMPLETED_NATIVE_RESULT"
    assert item["observed_job_id"] == "BT-OBSERVED"


def test_runtime_binary_authority_errors_are_not_agent_binding_errors(tmp_path):
    manager = RuntimeForensicsManager(tmp_path, jobs=object())
    job_id = "BT-BINARY-AUTHORITY"
    job = {"request": {"ea_binary_ref": "BIN-requested"}}

    with pytest.raises(AuthorityError, match="BINARY_AUTHORITY_REQUIRED"):
        manager._binary_identity(job_id, job)

    run = tmp_path / "runs" / job_id
    run.mkdir(parents=True)
    (run / "build-input-manifest.json").write_text(
        json.dumps({
            "imported_ex5": {
                "ea_binary_ref": "BIN-" + "a" * 64,
                "sha256": "b" * 64,
            }
        }),
        encoding="utf-8",
    )
    with pytest.raises(AuthorityError, match="BINARY_AUTHORITY_MISMATCH"):
        manager._binary_identity(job_id, job)


def test_project_session_list_labels_lock_only_directory_orphaned(tmp_path):
    manager = ProjectSessionManager(tmp_path)
    orphan = tmp_path / "state" / "project-sessions" / "BD-T1719"
    orphan.mkdir(parents=True)
    (orphan / ".session.lock").write_text("", encoding="utf-8")

    item = next(x for x in manager.list() if x["project_id"] == "BD-T1719")
    assert item["state"] == "ORPHANED"
    assert item["integrity"] == "ORPHANED"
    assert item["resume_safe"] is False
