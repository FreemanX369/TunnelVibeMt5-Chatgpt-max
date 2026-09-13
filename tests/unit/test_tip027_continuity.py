import json
from pathlib import Path

import pytest

from app.vibemql5.core.continuity import ContinuityManager, _json_bytes


def append(manager, project="P1", operation="op-1", expected_revision=0, expected_sha="", payload=None):
    return manager.append_event(
        project,
        "WORKFLOW_SET",
        payload or {"projection": {"workflow": {"phase": "BUILD", "state": "ACTIVE"}}},
        operation,
        expected_revision,
        expected_sha,
        {"source": "test", "security_identity": True},
    )


def test_genesis_projection_read_and_verify(tmp_path):
    manager = ContinuityManager(tmp_path)
    result = append(manager)

    assert result["manifest_id"] == "CM-000001"
    assert result["event"]["event_id"] == "EV-00000001"
    assert result["workflow"] == {"phase": "BUILD", "state": "ACTIVE"}
    assert result["event"]["actor_provenance"]["security_identity"] is False
    assert manager.get("P1")["manifest_sha256"] == result["manifest_sha256"]
    assert manager.read_events("P1")["count"] == 1
    verified = manager.verify("P1")
    assert verified["integrity"] == "VERIFIED"
    assert verified["resume_safe"] is True
    assert verified["read_only_proof"]["unchanged"] is True


def test_idempotency_and_payload_conflict(tmp_path):
    manager = ContinuityManager(tmp_path)
    first = append(manager)
    retry = append(manager)
    assert retry["manifest_sha256"] == first["manifest_sha256"]
    assert retry["idempotent_recovered"] is True

    with pytest.raises(ValueError, match="CONTINUITY_OPERATION_CONFLICT"):
        append(manager, payload={"projection": {"workflow": {"phase": "VERIFY"}}})


def test_stale_head_cas_rejected(tmp_path):
    manager = ContinuityManager(tmp_path)
    first = append(manager)
    second = append(
        manager,
        operation="op-2",
        expected_revision=1,
        expected_sha=first["manifest_sha256"],
    )
    assert second["manifest_revision"] == 2
    with pytest.raises(ValueError, match="CONTINUITY_CAS_CONFLICT"):
        append(manager, operation="op-stale", expected_revision=1, expected_sha=first["manifest_sha256"])


def test_checkpoint_is_idempotent_and_bound_to_head(tmp_path):
    manager = ContinuityManager(tmp_path)
    head = append(manager)
    first = manager.create_checkpoint("P1", "before next phase", "checkpoint-1", 1, head["manifest_sha256"])
    retry = manager.create_checkpoint("P1", "before next phase", "checkpoint-1", 1, head["manifest_sha256"])
    assert retry["checkpoint_id"] == first["checkpoint_id"]
    assert retry["checkpoint_sha256"] == first["checkpoint_sha256"]
    assert retry["idempotent_recovered"] is True


def test_verify_detects_chain_tamper_without_mutation(tmp_path):
    manager = ContinuityManager(tmp_path)
    append(manager)
    event_path = tmp_path / "state" / "continuity" / "P1" / "events" / "EV-00000001.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["payload"]["projection"]["workflow"]["phase"] = "TAMPERED"
    event_path.write_bytes(_json_bytes(event))
    before = event_path.read_bytes()
    result = manager.verify("P1")
    assert result["integrity"] == "INVALID"
    assert result["resume_safe"] is False
    assert event_path.read_bytes() == before


def test_reconcile_repairs_pointer_lag_and_missing_operation_index(tmp_path):
    manager = ContinuityManager(tmp_path)
    first = append(manager)
    second = append(manager, operation="op-2", expected_revision=1, expected_sha=first["manifest_sha256"])
    project_dir = tmp_path / "state" / "continuity" / "P1"
    old_manifest = json.loads((project_dir / "revisions" / "CM-000001.json").read_text(encoding="utf-8"))
    old_pointer = {
        "schema_version": "1.0",
        "project_id": "P1",
        "manifest_id": "CM-000001",
        "manifest_revision": 1,
        "manifest_sha256": first["manifest_sha256"],
        "updated_at_utc": old_manifest["updated_at_utc"],
    }
    (project_dir / "current.json").write_bytes(_json_bytes(old_pointer))
    operation_path = manager._operation_path("P1", "op-2")
    operation_path.unlink()

    drift = manager.verify("P1")
    assert drift["integrity"] == "DRIFT"
    fixed = manager.reconcile("P1", "reconcile-1", 1, first["manifest_sha256"])
    assert fixed["state"] == "RECONCILED"
    assert fixed["manifest_sha256"] == second["manifest_sha256"]
    assert manager.verify("P1")["integrity"] == "VERIFIED"


def test_same_reconcile_operation_converges(tmp_path):
    manager = ContinuityManager(tmp_path)
    head = append(manager)
    first = manager.reconcile("P1", "reconcile-1", 1, head["manifest_sha256"])
    retry = manager.reconcile("P1", "reconcile-1", 1, head["manifest_sha256"])
    assert first["manifest_sha256"] == retry["manifest_sha256"]
    assert retry["idempotent_recovered"] is True
