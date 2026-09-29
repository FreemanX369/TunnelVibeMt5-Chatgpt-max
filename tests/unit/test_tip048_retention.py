from __future__ import annotations

import json

from vibemql5.core.artifacts import ArtifactManager


def _settings(root):
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {},
        "retention": {"completed_jobs": 0},
        "jobs": {},
    }), encoding="utf-8")


def _job(root, job_id, updated):
    run = root / "runs" / job_id
    run.mkdir(parents=True)
    (run / "job.json").write_text(json.dumps({
        "job_id": job_id,
        "state": "PASSED",
        "updated_at": updated,
        "pinned": False,
    }), encoding="utf-8")
    return run


def test_retention_dry_run_protects_referenced_job(tmp_path):
    _settings(tmp_path)
    referenced = "BT-20260929-000001-ABCDEF"
    disposable = "BT-20260929-000002-123ABC"
    _job(tmp_path, referenced, "2026-09-29T00:00:01Z")
    _job(tmp_path, disposable, "2026-09-29T00:00:02Z")

    state = tmp_path / "state" / "project-sessions" / "P1"
    state.mkdir(parents=True)
    (state / "current.json").write_text(json.dumps({
        "baseline_job_id": referenced,
        "last_job_id": referenced,
    }), encoding="utf-8")

    out = ArtifactManager(tmp_path).retain(dry_run=True)
    assert referenced in out["protected_jobs"]
    assert disposable in out["candidates"]
    assert out["removed"] == []
    assert (tmp_path / "runs" / disposable).is_dir()


def test_retention_delete_never_removes_referenced_job(tmp_path):
    _settings(tmp_path)
    referenced = "BT-20260929-000003-FEDCBA"
    disposable = "BT-20260929-000004-654321"
    _job(tmp_path, referenced, "2026-09-29T00:00:01Z")
    _job(tmp_path, disposable, "2026-09-29T00:00:02Z")

    state = tmp_path / "state" / "iterations" / "IT-X"
    state.mkdir(parents=True)
    (state / "current.json").write_text(json.dumps({"last_job_id": referenced}), encoding="utf-8")

    out = ArtifactManager(tmp_path).retain(dry_run=False)
    assert referenced in out["protected_jobs"]
    assert (tmp_path / "runs" / referenced).is_dir()
    assert not (tmp_path / "runs" / disposable).exists()


def test_retention_reference_scan_failure_blocks_without_deleting(tmp_path):
    _settings(tmp_path)
    disposable = "BT-20260929-000005-AAAAAA"
    _job(tmp_path, disposable, "2026-09-29T00:00:02Z")
    state = tmp_path / "state" / "project-sessions" / "P2"
    state.mkdir(parents=True)
    (state / "current.json").write_text("{not-json", encoding="utf-8")

    out = ArtifactManager(tmp_path).retain(dry_run=False)
    assert out["status"] == "BLOCKED"
    assert out["reason_code"] == "RETENTION_REFERENCE_SCAN_FAILED"
    assert out["removed"] == []
    assert (tmp_path / "runs" / disposable).is_dir()
