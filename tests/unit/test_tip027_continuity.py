import hashlib
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


def append_lifecycle(manager, event_type, payload, operation, head=None, project="P1"):
    return manager.append_event(
        project,
        event_type,
        payload,
        operation,
        int(head["manifest_revision"]) if head else 0,
        head["manifest_sha256"] if head else "",
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


def test_tip029_lifecycle_set_events_project_active_state(tmp_path):
    manager = ContinuityManager(tmp_path)
    requirement = append_lifecycle(
        manager,
        "REQUIREMENT_SET",
        {"id": "REQ-TIP029-1", "text": "typed lifecycle events are validated"},
        "tip029-requirement-set",
    )
    decision = append_lifecycle(
        manager,
        "DECISION_SET",
        {"decision": {"id": "DEC-TIP029-1", "summary": "use existing continuity store"}},
        "tip029-decision-set",
        requirement,
    )
    constraint = append_lifecycle(
        manager,
        "CONSTRAINT_SET",
        {"constraint": "NO_BLIND_REPLAY"},
        "tip029-constraint-set",
        decision,
    )

    assert constraint["requirements"]["active"] == [
        {"id": "REQ-TIP029-1", "text": "typed lifecycle events are validated"}
    ]
    assert constraint["decisions"]["active"] == [
        {"id": "DEC-TIP029-1", "summary": "use existing continuity store", "state": "APPROVED"}
    ]
    assert constraint["constraints"]["active"] == ["NO_BLIND_REPLAY"]
    assert manager.verify("P1")["integrity"] == "VERIFIED"


def test_tip029_supersede_and_revoke_are_explicit_not_chronological(tmp_path):
    manager = ContinuityManager(tmp_path)
    head = append_lifecycle(
        manager,
        "REQUIREMENT_SET",
        {"id": "REQ-A", "text": "original requirement"},
        "tip029-req-a",
    )
    head = append_lifecycle(
        manager,
        "REQUIREMENT_SET",
        {"id": "REQ-B", "text": "independent later requirement"},
        "tip029-req-b",
        head,
    )
    assert [item["id"] for item in head["requirements"]["active"]] == ["REQ-A", "REQ-B"]

    head = append_lifecycle(
        manager,
        "REQUIREMENT_SUPERSEDED",
        {
            "requirement_id": "REQ-A",
            "replacement": {"id": "REQ-C", "text": "replacement requirement"},
        },
        "tip029-req-a-superseded",
        head,
    )
    assert [item["id"] for item in head["requirements"]["active"]] == ["REQ-B", "REQ-C"]

    head = append_lifecycle(
        manager,
        "DECISION_SET",
        {"id": "DEC-A", "summary": "decision to supersede"},
        "tip029-dec-a",
        head,
    )
    head = append_lifecycle(
        manager,
        "DECISION_SET",
        {"id": "DEC-B", "summary": "independent decision"},
        "tip029-dec-b",
        head,
    )
    head = append_lifecycle(
        manager,
        "DECISION_SUPERSEDED",
        {
            "decision_id": "DEC-A",
            "replacement": {"id": "DEC-C", "summary": "replacement decision"},
        },
        "tip029-dec-a-superseded",
        head,
    )
    assert [item["id"] for item in head["decisions"]["active"]] == ["DEC-B", "DEC-C"]

    head = append_lifecycle(
        manager,
        "CONSTRAINT_SET",
        {"constraint": "NO_PHASE1_REAUDIT_UNLESS_AUTHORITY_DRIFT"},
        "tip029-constraint-phase1",
        head,
    )
    head = append_lifecycle(
        manager,
        "CONSTRAINT_REVOKED",
        {"constraint_id": "NO_PHASE1_REAUDIT_UNLESS_AUTHORITY_DRIFT"},
        "tip029-constraint-phase1-revoked",
        head,
    )
    assert head["constraints"]["active"] == []


def test_tip029_typed_events_reject_projection_spoof_and_missing_id(tmp_path):
    manager = ContinuityManager(tmp_path)
    with pytest.raises(ValueError, match="CONTINUITY_TYPED_EVENT_REJECTS_PROJECTION"):
        append_lifecycle(
            manager,
            "DECISION_SET",
            {"id": "DEC-SPOOF", "projection": {"decisions": {"active": []}}},
            "tip029-spoof",
        )

    with pytest.raises(ValueError, match="CONTINUITY_DECISION_ID_INVALID"):
        append_lifecycle(manager, "DECISION_REVOKED", {"reason": "missing id"}, "tip029-missing-id")


def test_tip029_lifecycle_idempotency_and_payload_conflict(tmp_path):
    manager = ContinuityManager(tmp_path)
    first = append_lifecycle(
        manager,
        "CONSTRAINT_SET",
        {"constraint": "GITHUB_PERSISTENCE_REQUIRED"},
        "tip029-idempotent-constraint",
    )
    retry = append_lifecycle(
        manager,
        "CONSTRAINT_SET",
        {"constraint": "GITHUB_PERSISTENCE_REQUIRED"},
        "tip029-idempotent-constraint",
    )
    assert retry["manifest_sha256"] == first["manifest_sha256"]
    assert retry["idempotent_recovered"] is True

    with pytest.raises(ValueError, match="CONTINUITY_OPERATION_CONFLICT"):
        append_lifecycle(
            manager,
            "CONSTRAINT_SET",
            {"constraint": "NO_EA_TRADING_LOGIC_CHANGE"},
            "tip029-idempotent-constraint",
        )


def test_tip029_verify_detects_manifest_projection_tamper(tmp_path):
    manager = ContinuityManager(tmp_path)
    append_lifecycle(
        manager,
        "CONSTRAINT_SET",
        {"constraint": "CHECKPOINT_CAS_BEFORE_BACKEND_MUTATION"},
        "tip029-verify-projection",
    )
    project_dir = tmp_path / "state" / "continuity" / "P1"
    manifest_path = project_dir / "revisions" / "CM-000001.json"
    pointer_path = project_dir / "current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["constraints"]["active"] = []
    manifest_path.write_bytes(_json_bytes(manifest))
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest_sha
    pointer_path.write_bytes(_json_bytes(pointer))

    result = manager.verify("P1")
    assert result["integrity"] == "DRIFT"
    assert "MANIFEST_PROJECTION_MISMATCH:1" in result["issues"]


def test_tip030_delegation_lifecycle_requires_parent_verification(tmp_path):
    manager = ContinuityManager(tmp_path)
    head = append_lifecycle(
        manager,
        "DELEGATION_ASSIGNED",
        {
            "delegation": {
                "id": "DEL-TIP030-1",
                "assignee": "builder-a",
                "task": "implement bounded sub-agent lifecycle",
            }
        },
        "tip030-delegation-assigned",
    )
    assert head["delegations"]["active"] == [
        {
            "id": "DEL-TIP030-1",
            "assignee": "builder-a",
            "task": "implement bounded sub-agent lifecycle",
            "state": "ASSIGNED",
        }
    ]
    assert head["delegations"]["awaiting_parent_verification"] == []

    head = append_lifecycle(
        manager,
        "DELEGATION_STARTED",
        {"delegation_id": "DEL-TIP030-1", "summary": "builder accepted work"},
        "tip030-delegation-started",
        head,
    )
    assert head["delegations"]["active"][0]["state"] == "STARTED"
    assert head["delegations"]["active"][0]["summary"] == "builder accepted work"

    head = append_lifecycle(
        manager,
        "DELEGATION_COMPLETED",
        {
            "delegation_id": "DEL-TIP030-1",
            "report": {"status": "DONE", "checks": ["unit"]},
        },
        "tip030-delegation-completed",
        head,
    )
    assert head["delegations"]["active"] == []
    assert head["delegations"]["awaiting_parent_verification"] == [
        {
            "id": "DEL-TIP030-1",
            "assignee": "builder-a",
            "task": "implement bounded sub-agent lifecycle",
            "state": "AWAITING_PARENT_VERIFICATION",
            "summary": "builder accepted work",
            "report": {"status": "DONE", "checks": ["unit"]},
            "report_authority": "PENDING_PARENT_VERIFICATION",
        }
    ]

    head = append_lifecycle(
        manager,
        "DELEGATION_PARENT_VERIFIED",
        {"delegation_id": "DEL-TIP030-1", "verification": {"status": "ACCEPTED"}},
        "tip030-delegation-parent-verified",
        head,
    )
    assert head["delegations"] == {"active": [], "awaiting_parent_verification": []}
    assert manager.verify("P1")["integrity"] == "VERIFIED"


def test_tip030_delegation_state_transitions_are_guarded(tmp_path):
    manager = ContinuityManager(tmp_path)
    with pytest.raises(ValueError, match="CONTINUITY_DELEGATION_NOT_ACTIVE"):
        append_lifecycle(
            manager,
            "DELEGATION_COMPLETED",
            {"delegation_id": "DEL-MISSING", "report": {"status": "DONE"}},
            "tip030-complete-missing",
        )

    head = append_lifecycle(
        manager,
        "DELEGATION_ASSIGNED",
        {"id": "DEL-TIP030-2", "task": "guard terminal transitions"},
        "tip030-delegation-assigned-2",
    )
    with pytest.raises(
        ValueError, match="CONTINUITY_DELEGATION_NOT_AWAITING_PARENT_VERIFICATION"
    ):
        append_lifecycle(
            manager,
            "DELEGATION_PARENT_VERIFIED",
            {"delegation_id": "DEL-TIP030-2"},
            "tip030-verify-before-complete",
            head,
        )

    head = append_lifecycle(
        manager,
        "DELEGATION_CANCELLED",
        {"delegation_id": "DEL-TIP030-2", "reason": "superseded by parent"},
        "tip030-cancel-active",
        head,
    )
    assert head["delegations"] == {"active": [], "awaiting_parent_verification": []}
    with pytest.raises(ValueError, match="CONTINUITY_DELEGATION_NOT_FOUND"):
        append_lifecycle(
            manager,
            "DELEGATION_CANCELLED",
            {"delegation_id": "DEL-TIP030-2"},
            "tip030-cancel-missing",
            head,
        )


def test_tip030_delegations_survive_unrelated_projection_events(tmp_path):
    manager = ContinuityManager(tmp_path)
    head = append_lifecycle(
        manager,
        "DELEGATION_ASSIGNED",
        {"id": "DEL-TIP030-3", "task": "stay visible while workflow changes"},
        "tip030-delegation-assigned-3",
    )
    head = append(
        manager,
        operation="tip030-workflow-update",
        expected_revision=head["manifest_revision"],
        expected_sha=head["manifest_sha256"],
        payload={"projection": {"workflow": {"phase": "TIP-030", "state": "BUILD"}}},
    )

    assert head["delegations"]["active"] == [
        {
            "id": "DEL-TIP030-3",
            "task": "stay visible while workflow changes",
            "state": "ASSIGNED",
        }
    ]
    assert manager.verify("P1")["integrity"] == "VERIFIED"


def test_tip030_delegation_payload_idempotency_and_spoof_rejection(tmp_path):
    manager = ContinuityManager(tmp_path)
    first = append_lifecycle(
        manager,
        "DELEGATION_ASSIGNED",
        {"id": "DEL-TIP030-4", "task": "idempotent delegation append"},
        "tip030-idempotent-delegation",
    )
    retry = append_lifecycle(
        manager,
        "DELEGATION_ASSIGNED",
        {"id": "DEL-TIP030-4", "task": "idempotent delegation append"},
        "tip030-idempotent-delegation",
    )
    assert retry["manifest_sha256"] == first["manifest_sha256"]
    assert retry["idempotent_recovered"] is True

    with pytest.raises(ValueError, match="CONTINUITY_OPERATION_CONFLICT"):
        append_lifecycle(
            manager,
            "DELEGATION_ASSIGNED",
            {"id": "DEL-TIP030-5", "task": "conflicting reuse"},
            "tip030-idempotent-delegation",
        )

    with pytest.raises(ValueError, match="CONTINUITY_TYPED_EVENT_REJECTS_PROJECTION"):
        append_lifecycle(
            manager,
            "DELEGATION_ASSIGNED",
            {
                "id": "DEL-SPOOF",
                "projection": {"delegations": {"active": [], "awaiting_parent_verification": []}},
            },
            "tip030-delegation-spoof",
        )


def test_tip030_verify_detects_delegation_projection_tamper(tmp_path):
    manager = ContinuityManager(tmp_path)
    append_lifecycle(
        manager,
        "DELEGATION_ASSIGNED",
        {"id": "DEL-TIP030-6", "task": "detect delegation projection tamper"},
        "tip030-verify-delegation-projection",
    )
    project_dir = tmp_path / "state" / "continuity" / "P1"
    manifest_path = project_dir / "revisions" / "CM-000001.json"
    pointer_path = project_dir / "current.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["delegations"]["active"] = []
    manifest_path.write_bytes(_json_bytes(manifest))
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest_sha
    pointer_path.write_bytes(_json_bytes(pointer))

    result = manager.verify("P1")
    assert result["integrity"] == "DRIFT"
    assert "MANIFEST_PROJECTION_MISMATCH:1" in result["issues"]
