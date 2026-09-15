from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import default_root
from .baseline import BaselineJobValidator
from .project_sessions import ProjectSessionManager
from .revisions import RevisionManager


class TIP015ABaselineMigration:
    """One-time evidence-bound correction for a TIP-015 accepted session.

    It never edits revision JSON directly. The existing ProjectSessionManager CAS +
    correlated-operation journal creates exactly one immutable corrective revision.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.sessions = ProjectSessionManager(self.root)
        self.revisions = RevisionManager(self.root)
        self.validator = BaselineJobValidator(self.root)

    def migrate(
        self,
        project_id: str,
        expected_revision: str,
        expected_revision_sha256: str,
        accepted_job_id: str,
        expected_source_sha256: str,
        expected_source_bytes: int,
    ) -> dict[str, Any]:
        source_sha = str(expected_source_sha256 or "").lower()
        source_bytes = int(expected_source_bytes)
        operation_id = f"TIP-015A:BASELINE-MIGRATION:{project_id}:{expected_revision}"
        current = self.sessions.get(project_id)
        source = self.revisions.source_hash(current["workspace"], current["ea"])
        if source["sha256"] != source_sha or int(source["bytes"]) != source_bytes:
            raise RuntimeError("TIP015A_SOURCE_AUTHORITY_MISMATCH")

        # Idempotent replay after the corrective revision is already current.
        if current.get("session_update_operation_id") == operation_id:
            if current.get("session_update_expected_revision_id") != expected_revision:
                raise RuntimeError("TIP015A_MIGRATION_OPERATION_CONFLICT")
            if str(current.get("session_update_expected_revision_sha256") or "").lower() != str(expected_revision_sha256 or "").lower():
                raise RuntimeError("TIP015A_MIGRATION_OPERATION_CONFLICT")
            if current.get("baseline_job_id") != accepted_job_id or current.get("last_job_id") != accepted_job_id:
                raise RuntimeError("TIP015A_MIGRATION_RESULT_CONFLICT")
            return {**current, "migration_status": "ALREADY_MIGRATED", "idempotent_recovered": True}

        if current["revision_id"] != expected_revision:
            raise RuntimeError(f"TIP015A_SESSION_VERSION_CONFLICT: expected {expected_revision}, current {current['revision_id']}")
        if str(current.get("revision_sha256") or "").lower() != str(expected_revision_sha256 or "").lower():
            raise RuntimeError("TIP015A_SESSION_REVISION_SHA_MISMATCH")
        if current.get("last_job_id") != accepted_job_id:
            raise RuntimeError("TIP015A_ACCEPTED_JOB_NOT_CURRENT_LAST_JOB")

        try:
            job = self.validator.jobs.load(accepted_job_id)
        except Exception as exc:
            raise RuntimeError("TIP015A_ACCEPTED_JOB_MISSING") from exc
        candidate_request = dict(job.get("request") or {})
        synthetic = {
            "workspace": current["workspace"],
            "ea": current["ea"],
            "source_sha256": source_sha,
            "source_bytes": source_bytes,
            "baseline_job_id": accepted_job_id,
        }
        validation = self.validator.validate(synthetic, candidate_request)
        if validation.get("status") != "VALID":
            reasons = ",".join(validation.get("reasons") or [])
            raise RuntimeError(f"TIP015A_ACCEPTED_JOB_NOT_BASELINE_ELIGIBLE:{reasons}")

        refs = list(current.get("decision_refs") or [])
        if "TIP-015A" not in refs:
            refs.append("TIP-015A")
        updated = self.sessions.update(
            project_id,
            expected_revision,
            active_goal=current.get("active_goal"),
            decision_refs=refs,
            phase="EVIDENCE",
            checkpoint_id=current.get("checkpoint_id"),
            baseline_job_id=accepted_job_id,
            last_job_id=accepted_job_id,
            operation_id=operation_id,
            expected_revision_sha256=expected_revision_sha256,
        )
        after = self.revisions.source_hash(current["workspace"], current["ea"])
        if after["sha256"] != source_sha or int(after["bytes"]) != source_bytes:
            raise RuntimeError("TIP015A_SOURCE_CHANGED_DURING_MIGRATION")
        return {
            **updated,
            "migration_status": "MIGRATED",
            "accepted_job_validation": {k: v for k, v in validation.items() if k not in {"result", "request"}},
        }
