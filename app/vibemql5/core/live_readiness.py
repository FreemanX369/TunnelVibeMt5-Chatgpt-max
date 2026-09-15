from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .. import __version__
from ..config import default_root
from .release import _atomic_write_json, file_record, sha256_file, utc_now


REQUIRED_MATRIX_GATES = (
    "runtime",
    "terminal",
    "permissions",
    "symbol_identity",
    "symbol_geometry",
    "volume_capability",
    "order_capability",
    "sessions",
    "privacy",
    "read_only_safety",
)


def _json_file(path: Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def _iso_age_seconds(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _finite_positive(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value)) and float(value) > 0


class LiveReadinessManager:
    """Fail-closed technical live-readiness evidence pipeline.

    TIP-019 never activates trading and never promotes the canonical manifest to
    live_eligible=true. It only checks read-only evidence, attests a PASS result,
    and packages an immutable candidate for a later, separately approved metadata
    promotion transaction.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())

    @staticmethod
    def _safe(value: str, label: str) -> str:
        raw = str(value or "").strip()
        if not raw or any(x in raw for x in ("/", "\\", "..")):
            raise ValueError(f"Invalid {label}")
        return raw

    def _blueprint_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "TIP-019-LIVE-READINESS-BLUEPRINT.yaml"

    def _approval_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "OWNER_APPROVAL-TIP019-BUILD.json"

    def _policy_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "TIP019-LIVE-READINESS-POLICY.json"

    def _tip020_blueprint_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "TIP-020-FINAL-ACCOUNT-BLUEPRINT.yaml"

    def _tip020_approval_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "OWNER_APPROVAL-TIP020-BUILD.json"

    def _tip020_policy_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "TIP020-FINAL-ACCOUNT-POLICY.json"

    def _release_manifest_path(self) -> Path:
        return self.root / "evidence" / "manifest.json"

    def _project_state_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "PROJECT_STATE.yaml"

    def _decisions_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "DECISIONS.yaml"

    def _authority(self, project_id: str) -> dict[str, Any]:
        blueprint_path = self._blueprint_path()
        approval_path = self._approval_path()
        policy_path = self._policy_path()
        tip020_blueprint_path = self._tip020_blueprint_path()
        tip020_approval_path = self._tip020_approval_path()
        tip020_policy_path = self._tip020_policy_path()
        release_path = self._release_manifest_path()
        for p, code in (
            (blueprint_path, "TIP019_BLUEPRINT_MISSING"),
            (approval_path, "TIP019_BUILD_APPROVAL_MISSING"),
            (policy_path, "TIP019_LIVE_POLICY_MISSING"),
            (tip020_blueprint_path, "TIP020_BLUEPRINT_MISSING"),
            (tip020_approval_path, "TIP020_BUILD_APPROVAL_MISSING"),
            (tip020_policy_path, "TIP020_FINAL_ACCOUNT_POLICY_MISSING"),
            (release_path, "TIP019_FORWARD_MANIFEST_MISSING"),
            (self._project_state_path(), "TIP019_PROJECT_STATE_MISSING"),
            (self._decisions_path(), "TIP019_DECISIONS_MISSING"),
        ):
            if not p.is_file():
                raise FileNotFoundError(code)

        approval = _json_file(approval_path)
        policy = _json_file(policy_path)
        tip020_approval = _json_file(tip020_approval_path)
        tip020_policy = _json_file(tip020_policy_path)
        release = _json_file(release_path)
        blueprint_sha = sha256_file(blueprint_path)
        tip020_blueprint_sha = sha256_file(tip020_blueprint_path)
        tip020_approval_sha = sha256_file(tip020_approval_path)
        release_sha = sha256_file(release_path)

        if approval.get("schema_version") != "1.0" or approval.get("status") != "APPROVED":
            raise RuntimeError("TIP019_BUILD_APPROVAL_NOT_APPROVED")
        if approval.get("approval_scope") != "build_live_readiness_pipeline_real_read_only":
            raise RuntimeError("TIP019_BUILD_APPROVAL_SCOPE_MISMATCH")
        if approval.get("project_id") != project_id:
            raise RuntimeError("TIP019_BUILD_APPROVAL_PROJECT_MISMATCH")
        if str(approval.get("blueprint_sha256") or "").lower() != blueprint_sha:
            raise RuntimeError("TIP019_BUILD_APPROVAL_BLUEPRINT_HASH_MISMATCH")

        if tip020_approval.get("schema_version") != "1.0" or tip020_approval.get("status") != "APPROVED":
            raise RuntimeError("TIP020_BUILD_APPROVAL_NOT_APPROVED")
        if tip020_approval.get("approval_scope") != "build_tip020_native_session_and_final_account_hardening":
            raise RuntimeError("TIP020_BUILD_APPROVAL_SCOPE_MISMATCH")
        if tip020_approval.get("project_id") != project_id:
            raise RuntimeError("TIP020_BUILD_APPROVAL_PROJECT_MISMATCH")
        if str(tip020_approval.get("blueprint_sha256") or "").lower() != tip020_blueprint_sha:
            raise RuntimeError("TIP020_BUILD_APPROVAL_BLUEPRINT_HASH_MISMATCH")

        if tip020_policy.get("schema_version") != "1.0" or tip020_policy.get("tip") != "TIP-020":
            raise RuntimeError("TIP020_FINAL_ACCOUNT_POLICY_INVALID")
        if tip020_policy.get("project_id") != project_id:
            raise RuntimeError("TIP020_FINAL_ACCOUNT_POLICY_PROJECT_MISMATCH")
        if str(tip020_policy.get("blueprint_sha256") or "").lower() != tip020_blueprint_sha:
            raise RuntimeError("TIP020_FINAL_ACCOUNT_POLICY_BLUEPRINT_HASH_MISMATCH")
        if str(tip020_policy.get("build_approval_sha256") or "").lower() != tip020_approval_sha:
            raise RuntimeError("TIP020_FINAL_ACCOUNT_POLICY_APPROVAL_HASH_MISMATCH")

        if policy.get("schema_version") != "1.0" or policy.get("tip") != "TIP-019":
            raise RuntimeError("TIP019_LIVE_POLICY_INVALID")
        if policy.get("project_id") != project_id:
            raise RuntimeError("TIP019_LIVE_POLICY_PROJECT_MISMATCH")
        if str(policy.get("blueprint_sha256") or "").lower() != blueprint_sha:
            raise RuntimeError("TIP019_LIVE_POLICY_BLUEPRINT_HASH_MISMATCH")
        expected_baseline = str(policy.get("baseline_forward_manifest_sha256") or "").lower()
        if expected_baseline and release_sha != expected_baseline:
            raise RuntimeError("TIP019_FORWARD_MANIFEST_BASELINE_DRIFT")
        tip020_baseline = str(tip020_policy.get("baseline_forward_manifest_sha256") or "").lower()
        if tip020_baseline and release_sha != tip020_baseline:
            raise RuntimeError("TIP020_FORWARD_MANIFEST_BASELINE_DRIFT")
        checkpoint_path = self.root / "evidence" / "tip019" / "TIP019-EXTERNAL-DEPENDENCY-CHECKPOINT-20260902-195735.zip"
        checkpoint_sha = str(tip020_policy.get("baseline_tip019_checkpoint_package_sha256") or "").lower()
        if not checkpoint_path.is_file() or sha256_file(checkpoint_path) != checkpoint_sha:
            raise RuntimeError("TIP020_TIP019_CHECKPOINT_AUTHORITY_MISMATCH")

        if str(release.get("schema_version")) != "2.0":
            raise RuntimeError("TIP019_FORWARD_MANIFEST_SCHEMA_INVALID")
        if release.get("project_id") != project_id:
            raise RuntimeError("TIP019_FORWARD_MANIFEST_PROJECT_MISMATCH")
        if release.get("release_eligible") is not True or release.get("forward_eligible") is not True:
            raise RuntimeError("TIP019_FORWARD_ELIGIBILITY_REQUIRED")
        if release.get("live_eligible") is not False:
            raise RuntimeError("TIP019_LIVE_PRECONDITION_MUST_BE_FALSE")

        fwd = release.get("forward_qualification") or {}
        package = fwd.get("package") or {}
        package_path = Path(str(package.get("path") or ""))
        if not package_path.is_file():
            raise RuntimeError("TIP019_INHERITED_FORWARD_PACKAGE_MISSING")
        if sha256_file(package_path) != str(package.get("sha256") or "").lower():
            raise RuntimeError("TIP019_INHERITED_FORWARD_PACKAGE_HASH_MISMATCH")

        closure_path = self.root / str(policy.get("tip018_closure_relative_path") or "")
        closure_sha = str(policy.get("tip018_closure_sha256") or "").lower()
        if not closure_path.is_file() or sha256_file(closure_path) != closure_sha:
            raise RuntimeError("TIP019_TIP018_CLOSURE_AUTHORITY_MISMATCH")

        return {
            "blueprint_path": blueprint_path,
            "blueprint_sha256": blueprint_sha,
            "approval_path": approval_path,
            "approval_sha256": sha256_file(approval_path),
            "approval": approval,
            "policy_path": policy_path,
            "policy_sha256": sha256_file(policy_path),
            "policy": policy,
            "tip020_blueprint_path": tip020_blueprint_path,
            "tip020_blueprint_sha256": tip020_blueprint_sha,
            "tip020_approval_path": tip020_approval_path,
            "tip020_approval_sha256": tip020_approval_sha,
            "tip020_approval": tip020_approval,
            "tip020_policy_path": tip020_policy_path,
            "tip020_policy_sha256": sha256_file(tip020_policy_path),
            "tip020_policy": tip020_policy,
            "tip019_checkpoint_path": checkpoint_path,
            "tip019_checkpoint_sha256": checkpoint_sha,
            "release_path": release_path,
            "release_sha256": release_sha,
            "release": release,
            "project_state_sha256": sha256_file(self._project_state_path()),
            "decisions_sha256": sha256_file(self._decisions_path()),
            "closure_path": closure_path,
            "closure_sha256": closure_sha,
            "forward_package": file_record(package_path, logical_name="tip018_forward_package"),
        }

    def _dir(self, project_id: str, qualification_id: str) -> Path:
        p = self.root / "evidence" / "live" / self._safe(project_id, "project id") / self._safe(qualification_id, "qualification id")
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _qualification_id(self, project_id: str, scan_sha: str, matrix_sha: str, session_sha: str, authority: dict[str, Any]) -> str:
        payload = {
            "project_id": project_id,
            "scan_sha256": scan_sha,
            "capability_matrix_sha256": matrix_sha,
            "native_session_evidence_sha256": session_sha,
            "blueprint_sha256": authority["blueprint_sha256"],
            "tip020_blueprint_sha256": authority["tip020_blueprint_sha256"],
            "forward_manifest_sha256": authority["release_sha256"],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return "LQ-" + digest[:20].upper()

    def _native_session_result(self, project_id: str, path: Path | None, authority: dict[str, Any], matrix: dict[str, Any], max_age: int) -> dict[str, Any]:
        if path is None:
            return {"status": "UNTESTABLE", "reason": "TIP020_NATIVE_SESSION_EVIDENCE_NOT_PROVIDED", "path": None, "sha256": "", "age_seconds": None}
        p = Path(path)
        if not p.is_file():
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_EVIDENCE_MISSING", "path": str(p), "sha256": "", "age_seconds": None}
        try:
            data = _json_file(p)
            digest = sha256_file(p)
        except Exception:
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_EVIDENCE_PARSE_FAILED", "path": str(p), "sha256": "", "age_seconds": None}
        age = _iso_age_seconds(data.get("recorded_at_utc"))
        if not data or data.get("schema_version") != "1.0" or data.get("tip") != "TIP-020" or data.get("phase") != "NATIVE_SESSION_EVIDENCE" or data.get("project_id") != project_id:
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_IDENTITY_MISMATCH", "path": str(p), "sha256": digest, "age_seconds": age}
        if data.get("status") != "PASS":
            return {"status": "UNTESTABLE" if data.get("status") == "UNTESTABLE" else "FAIL", "reason": str(data.get("reason") or "TIP020_NATIVE_SESSION_NOT_PASS"), "path": str(p), "sha256": digest, "age_seconds": age}
        auth = data.get("authority") or {}
        if not (
            str(auth.get("project_state_sha256") or "").lower() == authority["project_state_sha256"]
            and str(auth.get("decisions_sha256") or "").lower() == authority["decisions_sha256"]
            and str(auth.get("forward_manifest_sha256") or "").lower() == authority["release_sha256"]
            and str(auth.get("tip019_checkpoint_package_sha256") or "").lower() == authority["tip019_checkpoint_sha256"]
        ):
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_AUTHORITY_MISMATCH", "path": str(p), "sha256": digest, "age_seconds": age}
        if max_age <= 0 or age is None or age > max_age:
            return {"status": "UNTESTABLE", "reason": "TIP020_NATIVE_SESSION_EVIDENCE_STALE_OR_UNDATED", "path": str(p), "sha256": digest, "age_seconds": age}
        symbol = matrix.get("symbol") or {}
        if str(data.get("requested_symbol") or "") != str(symbol.get("requested") or "") or str(data.get("resolved_symbol") or "") != str(symbol.get("resolved") or ""):
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_SYMBOL_MISMATCH", "path": str(p), "sha256": digest, "age_seconds": age}
        source = data.get("source") or {}
        if not (
            source.get("kind") == "windows_native_mql5_startup_script"
            and source.get("compile_status") == "PASS"
            and source.get("compile_errors") is not None and int(source.get("compile_errors")) == 0
            and source.get("compile_warnings") is not None and int(source.get("compile_warnings")) == 0
            and len(str(source.get("template_sha256") or "")) == 64
            and len(str(source.get("generated_source_sha256") or "")) == 64
            and len(str(source.get("ex5_sha256") or "")) == 64
            and len(str(source.get("compile_log_sha256") or "")) == 64
        ):
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_PROVENANCE_INVALID", "path": str(p), "sha256": digest, "age_seconds": age}
        sessions = data.get("sessions") or []
        try:
            valid_sessions = all(
                isinstance(x, dict)
                and 0 <= int(x.get("day_of_week")) <= 6
                and int(x.get("index")) >= 0
                and 0 <= int(x.get("from_seconds")) <= 86400
                and 0 <= int(x.get("to_seconds")) <= 86400
                for x in sessions
            )
        except Exception:
            valid_sessions = False
        min_count = int((authority.get("tip020_policy") or {}).get("native_session_min_count") or 1)
        if not valid_sessions or len(sessions) < min_count or int(data.get("session_count") or 0) != len(sessions):
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_PAYLOAD_INVALID", "path": str(p), "sha256": digest, "age_seconds": age}
        safety = data.get("safety") or {}
        if not (
            safety.get("order_send_called") is False
            and safety.get("positions_or_orders_modified") is False
            and safety.get("autotrading_toggled") is False
            and safety.get("account_login_mutated") is False
            and safety.get("running_requested_terminal_closed") is False
        ):
            return {"status": "FAIL", "reason": "TIP020_NATIVE_SESSION_SAFETY_INVALID", "path": str(p), "sha256": digest, "age_seconds": age}
        return {"status": "PASS", "reason": "PASS", "path": str(p), "sha256": digest, "age_seconds": age, "session_count": len(sessions)}

    def _evaluate(self, project_id: str, scan_path: Path, matrix_path: Path, session_path: Path | None = None) -> dict[str, Any]:
        project_id = self._safe(project_id, "project id")
        authority = self._authority(project_id)
        scan_path = Path(scan_path)
        matrix_path = Path(matrix_path)
        scan = _json_file(scan_path)
        matrix = _json_file(matrix_path)
        scan_sha = sha256_file(scan_path) if scan_path.is_file() else ""
        matrix_sha = sha256_file(matrix_path) if matrix_path.is_file() else ""
        reasons: list[str] = []
        gates: dict[str, str] = {}

        def gate(name: str, status: str, reason: str | None = None) -> None:
            normalized = status if status in {"PASS", "FAIL", "UNTESTABLE"} else "FAIL"
            gates[name] = normalized
            if normalized != "PASS" and reason:
                reasons.append(reason)

        scan_tip = str(scan.get("tip") or "")
        matrix_tip = str(matrix.get("tip") or "")
        scan_identity = bool(scan) and scan.get("schema_version") == "1.0" and scan_tip in {"TIP-019", "TIP-020"} and scan.get("project_id") == project_id
        if scan_tip == "TIP-020":
            scan_identity = scan_identity and scan.get("phase") == "FINAL_ACCOUNT_SCAN"
        gate("scan_identity", "PASS" if scan_identity else "FAIL", "TIP019_SCAN_IDENTITY_MISMATCH")
        matrix_identity = bool(matrix) and matrix.get("schema_version") == "1.0" and matrix_tip in {"TIP-019", "TIP-020"}
        if matrix_tip == "TIP-020":
            matrix_identity = matrix_identity and matrix.get("phase") == "FINAL_ACCOUNT_REVIEW"
        gate("matrix_identity", "PASS" if matrix_identity else "FAIL", "TIP019_MATRIX_IDENTITY_MISMATCH")

        src = matrix.get("source_scan") or {}
        gate(
            "scan_matrix_hash_binding",
            "PASS" if str(src.get("sha256") or "").lower() == scan_sha and scan_sha else "FAIL",
            "TIP019_SCAN_MATRIX_HASH_MISMATCH",
        )

        scan_auth = scan.get("authority") or {}
        matrix_auth = matrix.get("authority") or {}
        state_hash = authority["project_state_sha256"]
        decision_hash = authority["decisions_sha256"]
        closure_hash = authority["closure_sha256"]
        if scan_tip == "TIP-020" and matrix_tip == "TIP-020":
            authority_ok = (
                str(scan_auth.get("project_state_sha256") or "").lower() == state_hash
                and str(scan_auth.get("decisions_sha256") or "").lower() == decision_hash
                and str(scan_auth.get("tip019_checkpoint_package_sha256") or "").lower() == authority["tip019_checkpoint_sha256"]
                and str(matrix_auth.get("project_state_sha256") or "").lower() == state_hash
                and str(matrix_auth.get("decisions_sha256") or "").lower() == decision_hash
                and str(matrix_auth.get("tip019_checkpoint_package_sha256") or "").lower() == authority["tip019_checkpoint_sha256"]
            )
        else:
            authority_ok = (
                str(scan_auth.get("project_state_sha256") or "").lower() == state_hash
                and str(scan_auth.get("decisions_sha256") or "").lower() == decision_hash
                and str(scan_auth.get("tip018_closure_package_sha256") or "").lower() == closure_hash
                and str(matrix_auth.get("project_state_sha256") or "").lower() == state_hash
                and str(matrix_auth.get("decisions_sha256") or "").lower() == decision_hash
                and str(matrix_auth.get("tip018_closure_package_sha256") or "").lower() == closure_hash
            )
        gate("authority_binding", "PASS" if authority_ok else "FAIL", "TIP019_EVIDENCE_AUTHORITY_MISMATCH")

        policy = authority["policy"]
        tip020_policy = authority["tip020_policy"]
        max_age_values = [int(x) for x in (policy.get("max_evidence_age_seconds") or 0, tip020_policy.get("max_evidence_age_seconds") or 0) if int(x) > 0]
        max_age = min(max_age_values) if max_age_values else 0
        scan_age = _iso_age_seconds(scan.get("recorded_at_utc"))
        matrix_age = _iso_age_seconds(matrix.get("recorded_at_utc"))
        fresh = max_age > 0 and scan_age is not None and matrix_age is not None and scan_age <= max_age and matrix_age <= max_age
        gate("evidence_freshness", "PASS" if fresh else "UNTESTABLE", "TIP019_EVIDENCE_STALE_OR_UNDATED")

        lane = str(matrix.get("selected_lane") or "")
        gate("real_read_only_lane", "PASS" if lane == "REAL_READ_ONLY_LANE" else "FAIL", "TIP019_REAL_READ_ONLY_LANE_REQUIRED")
        account = matrix.get("account") or {}
        gate("account_mode_real", "PASS" if str(account.get("trade_mode") or "").upper() == "REAL" else "FAIL", "TIP019_REAL_ACCOUNT_REQUIRED")

        native_session = self._native_session_result(project_id, session_path, authority, matrix, max_age)
        mg = matrix.get("gates") or {}
        for name in REQUIRED_MATRIX_GATES:
            raw = str(mg.get(name) or "FAIL").upper()
            if name == "permissions" and raw != "PASS":
                gate(name, "UNTESTABLE", "TIP019_TRADING_PERMISSIONS_DEFERRED_EXTERNAL_DEPENDENCY")
            elif name == "sessions" and raw != "PASS":
                if native_session.get("status") == "PASS":
                    gate(name, "PASS")
                elif native_session.get("status") == "FAIL":
                    gate(name, "FAIL", str(native_session.get("reason") or "TIP020_NATIVE_SESSION_EVIDENCE_INVALID"))
                else:
                    gate(name, "UNTESTABLE", str(native_session.get("reason") or "TIP020_NATIVE_SESSION_EVIDENCE_UNTESTABLE"))
            else:
                gate(name, raw, f"TIP019_{name.upper()}_GATE_NOT_PASS")
        if session_path is not None or str(mg.get("sessions") or "FAIL").upper() != "PASS":
            gate("native_session_provenance", "PASS" if native_session.get("status") == "PASS" else ("FAIL" if native_session.get("status") == "FAIL" else "UNTESTABLE"), None if native_session.get("status") == "PASS" else str(native_session.get("reason") or "TIP020_NATIVE_SESSION_EVIDENCE_UNTESTABLE"))

        symbol = matrix.get("symbol") or {}
        symbol_ok = (
            str(symbol.get("requested") or "") == "EURUSD"
            and bool(str(symbol.get("resolved") or "").strip())
            and isinstance(symbol.get("digits"), int)
            and _finite_positive(symbol.get("point"))
        )
        gate("broker_symbol_provenance", "PASS" if symbol_ok else "FAIL", "TIP019_BROKER_SYMBOL_PROVENANCE_INVALID")

        scan_safety = scan.get("safety") or {}
        mt5_privacy = ((scan.get("mt5") or {}).get("privacy") or {})
        no_side_effects = (
            scan_safety.get("read_only") is True
            and scan_safety.get("mt5_restarted") is False
            and scan_safety.get("windows_rebooted") is False
            and scan_safety.get("autotrading_toggled") is False
            and scan_safety.get("order_send_called") is False
            and scan_safety.get("positions_or_orders_modified") is False
            and mt5_privacy.get("order_send_called") is False
            and mt5_privacy.get("trade_history_read") is False
            and mt5_privacy.get("positions_read") is False
            and mt5_privacy.get("orders_read") is False
        )
        gate("no_trading_side_effects", "PASS" if no_side_effects else "FAIL", "TIP019_READ_ONLY_SIDE_EFFECT_GUARD_FAILED")

        inherited = authority["forward_package"]
        inherited_ok = bool(inherited.get("exists")) and bool(inherited.get("sha256")) and int(inherited.get("bytes") or 0) > 0
        gate("inherited_forward_evidence", "PASS" if inherited_ok else "FAIL", "TIP019_INHERITED_FORWARD_EVIDENCE_INVALID")

        any_fail = any(v == "FAIL" for v in gates.values())
        any_untestable = any(v == "UNTESTABLE" for v in gates.values())
        status = "FAIL" if any_fail else ("UNTESTABLE" if any_untestable else "PASS")
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "status": status,
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
            "candidate_ready": status == "PASS",
            "gates": gates,
            "reasons": reasons,
            "selected_lane": lane,
            "account": account,
            "terminal": matrix.get("terminal") or {},
            "symbol": symbol,
            "evidence_age_seconds": {"scan": scan_age, "capability_matrix": matrix_age, "native_session": native_session.get("age_seconds"), "max_allowed": max_age},
            "inputs": {
                "scan": {"path": str(scan_path), "sha256": scan_sha},
                "capability_matrix": {"path": str(matrix_path), "sha256": matrix_sha},
                "native_session_evidence": {"path": native_session.get("path"), "sha256": native_session.get("sha256") or "", "status": native_session.get("status")},
                "tip018_closure": {"path": str(authority["closure_path"]), "sha256": closure_hash},
                "tip019_checkpoint": {"path": str(authority["tip019_checkpoint_path"]), "sha256": authority["tip019_checkpoint_sha256"]},
                "forward_manifest": {"path": str(authority["release_path"]), "sha256": authority["release_sha256"]},
                "forward_package": inherited,
                "project_state_sha256": state_hash,
                "decisions_sha256": decision_hash,
                "blueprint_sha256": authority["blueprint_sha256"],
                "build_approval_sha256": authority["approval_sha256"],
                "policy_sha256": authority["policy_sha256"],
                "tip020_blueprint_sha256": authority["tip020_blueprint_sha256"],
                "tip020_build_approval_sha256": authority["tip020_approval_sha256"],
                "tip020_policy_sha256": authority["tip020_policy_sha256"],
            },
            "policy": {
                "no_order_send": True,
                "no_autotrading_toggle": True,
                "no_account_login_mutation": True,
                "no_automatic_live_promotion": True,
                "no_automatic_close_of_running_requested_terminal": True,
                "final_hash_bound_owner_approval_required": True,
            },
        }

    def check(self, project_id: str, scan_evidence: str | Path, capability_matrix: str | Path, session_evidence: str | Path | None = None) -> dict[str, Any]:
        session_path = Path(session_evidence) if session_evidence else None
        evaluation = self._evaluate(project_id, Path(scan_evidence), Path(capability_matrix), session_path)
        authority = self._authority(project_id)
        scan_sha = str((evaluation.get("inputs") or {}).get("scan", {}).get("sha256") or "")
        matrix_sha = str((evaluation.get("inputs") or {}).get("capability_matrix", {}).get("sha256") or "")
        session_sha = str((evaluation.get("inputs") or {}).get("native_session_evidence", {}).get("sha256") or "")
        qid = self._qualification_id(project_id, scan_sha, matrix_sha, session_sha, authority)
        out = dict(evaluation)
        out["qualification_id"] = qid
        out["checked_at_utc"] = utc_now()
        out["tool_version"] = __version__
        out["host"] = socket.gethostname()
        d = self._dir(project_id, qid)
        path = d / "live-check.json"
        _atomic_write_json(path, out)
        return {**out, "path": str(path), "sha256": sha256_file(path)}

    def _validate_saved_check(self, project_id: str, qualification_id: str) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        authority = self._authority(project_id)
        d = self._dir(project_id, qualification_id)
        path = d / "live-check.json"
        check = _json_file(path)
        if check.get("status") != "PASS" or check.get("candidate_ready") is not True:
            raise RuntimeError("LIVE_CHECK_NOT_PASS")
        if check.get("qualification_id") != qualification_id:
            raise RuntimeError("LIVE_CHECK_QUALIFICATION_ID_MISMATCH")
        inputs = check.get("inputs") or {}
        scan = inputs.get("scan") or {}
        matrix = inputs.get("capability_matrix") or {}
        scan_path = Path(str(scan.get("path") or ""))
        matrix_path = Path(str(matrix.get("path") or ""))
        if not scan_path.is_file() or sha256_file(scan_path) != str(scan.get("sha256") or ""):
            raise RuntimeError("LIVE_SCAN_EVIDENCE_DRIFT")
        if not matrix_path.is_file() or sha256_file(matrix_path) != str(matrix.get("sha256") or ""):
            raise RuntimeError("LIVE_CAPABILITY_MATRIX_DRIFT")
        sess = inputs.get("native_session_evidence") or {}
        session_path = Path(str(sess.get("path") or "")) if str(sess.get("path") or "").strip() else None
        if session_path is not None and (not session_path.is_file() or sha256_file(session_path) != str(sess.get("sha256") or "")):
            raise RuntimeError("LIVE_NATIVE_SESSION_EVIDENCE_DRIFT")
        current = self._evaluate(project_id, scan_path, matrix_path, session_path)
        if current.get("status") != "PASS":
            raise RuntimeError("LIVE_EVIDENCE_NO_LONGER_VALID:" + ",".join(current.get("reasons") or []))
        return check, path, authority

    def attest(self, project_id: str, qualification_id: str) -> dict[str, Any]:
        check, check_path, authority = self._validate_saved_check(project_id, qualification_id)
        d = self._dir(project_id, qualification_id)
        record = {
            "schema_version": "1.0",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "status": "PASS",
            "attestation_type": "tip020_final_account_live_readiness_candidate",
            "attested_at_utc": utc_now(),
            "tool_version": __version__,
            "host": socket.gethostname(),
            "live_check": {"path": str(check_path), "sha256": sha256_file(check_path)},
            "blueprint_sha256": authority["blueprint_sha256"],
            "build_approval": {"path": str(authority["approval_path"]), "sha256": authority["approval_sha256"]},
            "tip020_build_approval": {"path": str(authority["tip020_approval_path"]), "sha256": authority["tip020_approval_sha256"]},
            "tip020_blueprint_sha256": authority["tip020_blueprint_sha256"],
            "tip020_policy_sha256": authority["tip020_policy_sha256"],
            "forward_manifest_sha256": authority["release_sha256"],
            "project_state_sha256": authority["project_state_sha256"],
            "decisions_sha256": authority["decisions_sha256"],
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
            "final_owner_approval_required": True,
        }
        path = d / "live-attestation.json"
        _atomic_write_json(path, record)
        return {**record, "path": str(path), "sha256": sha256_file(path)}

    def package(self, project_id: str, qualification_id: str) -> dict[str, Any]:
        check, check_path, authority = self._validate_saved_check(project_id, qualification_id)
        d = self._dir(project_id, qualification_id)
        att_path = d / "live-attestation.json"
        att = _json_file(att_path)
        if att.get("status") != "PASS":
            raise RuntimeError("LIVE_ATTESTATION_NOT_PASS")
        if (att.get("live_check") or {}).get("sha256") != sha256_file(check_path):
            raise RuntimeError("LIVE_ATTESTATION_CHECK_HASH_MISMATCH")
        if str((att.get("build_approval") or {}).get("sha256") or "") != authority["approval_sha256"]:
            raise RuntimeError("LIVE_ATTESTATION_APPROVAL_HASH_MISMATCH")
        if str((att.get("tip020_build_approval") or {}).get("sha256") or "") != authority["tip020_approval_sha256"]:
            raise RuntimeError("LIVE_ATTESTATION_TIP020_APPROVAL_HASH_MISMATCH")
        if att.get("forward_manifest_sha256") != authority["release_sha256"]:
            raise RuntimeError("LIVE_ATTESTATION_FORWARD_HASH_MISMATCH")

        candidate = {
            "schema_version": "1.0",
            "manifest_type": "vibemql5_live_readiness_candidate",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "status": "PASS",
            "candidate_ready": True,
            "recorded_at_utc": utc_now(),
            "tool_version": __version__,
            "host": socket.gethostname(),
            "live_check": {"path": str(check_path), "sha256": sha256_file(check_path)},
            "attestation": {"path": str(att_path), "sha256": sha256_file(att_path)},
            "blueprint_sha256": authority["blueprint_sha256"],
            "build_approval_sha256": authority["approval_sha256"],
            "tip020_build_approval_sha256": authority["tip020_approval_sha256"],
            "tip020_blueprint_sha256": authority["tip020_blueprint_sha256"],
            "tip020_policy_sha256": authority["tip020_policy_sha256"],
            "forward_manifest_sha256": authority["release_sha256"],
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
            "final_owner_approval_required": True,
            "automatic_promotion": False,
            "residual_policy": [
                "Candidate package does not activate trading.",
                "Candidate package does not modify the canonical release manifest.",
                "A separate hash-bound owner approval and metadata-only promotion transaction are required for live_eligible=true.",
            ],
        }
        manifest_path = d / "live-candidate-manifest.json"
        _atomic_write_json(manifest_path, candidate)

        proposal = {
            "schema_version": "1.0",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "status": "PENDING_FINAL_OWNER_APPROVAL",
            "candidate_manifest_sha256": sha256_file(manifest_path),
            "live_check_sha256": sha256_file(check_path),
            "attestation_sha256": sha256_file(att_path),
            "canonical_forward_manifest_sha256": authority["release_sha256"],
            "requested_future_action": "metadata_only_live_eligibility_promotion",
            "forbidden_action": "activate_or_place_live_trades",
        }
        proposal_path = d / "FINAL-LIVE-ELIGIBILITY-PROPOSAL.json"
        _atomic_write_json(proposal_path, proposal)

        zip_path = d / f"live-readiness-candidate-{qualification_id}.zip"
        tmp_zip = d / f".{zip_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in sorted(d.rglob("*")):
                    if p.is_file() and p not in {zip_path, tmp_zip}:
                        zf.write(p, p.relative_to(d))
            os.replace(tmp_zip, zip_path)
        finally:
            try:
                tmp_zip.unlink(missing_ok=True)
            except OSError:
                pass

        if sha256_file(authority["release_path"]) != authority["release_sha256"]:
            raise RuntimeError("LIVE_PACKAGE_MUTATED_CANONICAL_FORWARD_MANIFEST")

        record = {
            "schema_version": "1.0",
            "status": "PASS",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "candidate_ready": True,
            "package": {"path": str(zip_path), "sha256": sha256_file(zip_path), "bytes": int(zip_path.stat().st_size)},
            "candidate_manifest": {"path": str(manifest_path), "sha256": sha256_file(manifest_path)},
            "final_owner_proposal": {"path": str(proposal_path), "sha256": sha256_file(proposal_path)},
            "canonical_forward_manifest": {"path": str(authority["release_path"]), "sha256": authority["release_sha256"]},
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
            "final_owner_approval_required": True,
        }
        record_path = d / "live-package.json"
        _atomic_write_json(record_path, record)
        return {**record, "path": str(record_path), "sha256": sha256_file(record_path)}
