from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..config import default_root
from .jobs import JobStore
from .workspace import WorkspaceManager


def compare_results(candidate: dict, baseline: dict) -> dict:
    keys = ["trades", "net_profit", "profit_factor", "max_drawdown_pct"]
    c = candidate.get("strategy", {})
    b = baseline.get("strategy", {})
    metrics = {}
    for k in keys:
        cv, bv = c.get(k), b.get(k)
        delta = None
        if isinstance(cv, (int, float)) and isinstance(bv, (int, float)):
            delta = cv - bv
        metrics[k] = {"candidate": cv, "baseline": bv, "delta": delta}
    return {
        "candidate_status": candidate.get("status"),
        "baseline_status": baseline.get("status"),
        "metrics": metrics,
    }


class BaselineManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.ws = WorkspaceManager(self.root)

    def save(self, workspace: str, name: str, result: dict) -> Path:
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid baseline name")
        p = self.ws.workspace_root(workspace) / "Baselines" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return p

    def compare(self, workspace: str, name: str, candidate: dict) -> dict:
        p = self.ws.workspace_root(workspace) / "Baselines" / f"{name}.json"
        return compare_results(candidate, json.loads(p.read_text(encoding="utf-8")))


class BaselineJobValidator:
    """Strict TIP-015 validator for a project-session bound baseline job.

    Missing, stale, mock, non-native, incompatible, or source-mismatched evidence is
    reported as BASELINE_UNAVAILABLE. No profitability threshold is invented here.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.jobs = JobStore(self.root)

    @staticmethod
    def _norm_path(value: Any) -> str:
        return str(value or "").replace("\\", "/")

    @staticmethod
    def _same_json(a: Any, b: Any) -> bool:
        return json.dumps(a or {}, sort_keys=True, separators=(",", ":")) == json.dumps(
            b or {}, sort_keys=True, separators=(",", ":")
        )

    def _result(self, job_id: str) -> dict[str, Any] | None:
        p = self.root / "runs" / job_id / "result.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _snapshot(self, job_id: str, ea: str) -> dict[str, Any] | None:
        p = self.root / "runs" / job_id / "source_snapshot" / Path(self._norm_path(ea))
        if not p.is_file():
            return None
        raw = p.read_bytes()
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "path": str(p)}

    def validate(
        self,
        session: dict[str, Any],
        candidate_request: dict[str, Any],
    ) -> dict[str, Any]:
        job_id = str(session.get("baseline_job_id") or "").strip()
        reasons: list[str] = []
        if not job_id:
            return {"status": "BASELINE_UNAVAILABLE", "job_id": "", "reasons": ["BASELINE_JOB_ID_MISSING"]}
        try:
            job = self.jobs.load(job_id)
        except Exception:
            return {"status": "BASELINE_UNAVAILABLE", "job_id": job_id, "reasons": ["BASELINE_JOB_MISSING"]}
        result = self._result(job_id)
        if job.get("state") != "PASSED":
            reasons.append("BASELINE_JOB_NOT_PASSED")
        if not result or result.get("status") != "PASSED":
            reasons.append("BASELINE_RESULT_NOT_PASSED")

        tester = (result or {}).get("tester") or {}
        if tester.get("execution_status") != "PASSED":
            reasons.append("BASELINE_NATIVE_EXECUTION_NOT_PASSED")
        if tester.get("report_status") != "PARSED":
            reasons.append("BASELINE_REPORT_NOT_PARSED")

        env = (result or {}).get("environment") or {}
        req = job.get("request") or {}
        if bool(req.get("mock")) or bool(env.get("mock")):
            reasons.append("BASELINE_MOCK_NOT_ALLOWED")
        if str(env.get("terminal") or req.get("terminal") or "").upper() != "MT5-2":
            reasons.append("BASELINE_TERMINAL_NOT_MT5_2")

        if str(req.get("workspace") or "") != str(session.get("workspace") or ""):
            reasons.append("BASELINE_WORKSPACE_MISMATCH")
        if self._norm_path(req.get("ea")) != self._norm_path(session.get("ea")):
            reasons.append("BASELINE_EA_MISMATCH")
        if str(candidate_request.get("workspace") or "") != str(session.get("workspace") or ""):
            reasons.append("CANDIDATE_WORKSPACE_MISMATCH")
        if self._norm_path(candidate_request.get("ea")) != self._norm_path(session.get("ea")):
            reasons.append("CANDIDATE_EA_MISMATCH")

        if str(req.get("preset") or "smoke") != str(candidate_request.get("preset") or "smoke"):
            reasons.append("BASELINE_PRESET_MISMATCH")
        if self._norm_path(req.get("set_file")) != self._norm_path(candidate_request.get("set_file")):
            reasons.append("BASELINE_SET_FILE_MISMATCH")
        if not self._same_json(req.get("overrides"), candidate_request.get("overrides")):
            reasons.append("BASELINE_OVERRIDES_MISMATCH")

        snapshot = self._snapshot(job_id, str(session.get("ea") or ""))
        if not snapshot:
            reasons.append("BASELINE_SOURCE_SNAPSHOT_MISSING")
        else:
            if snapshot["sha256"] != str(session.get("source_sha256") or "").lower():
                reasons.append("BASELINE_SOURCE_SHA_MISMATCH")
            if int(snapshot["bytes"]) != int(session.get("source_bytes") or -1):
                reasons.append("BASELINE_SOURCE_BYTES_MISMATCH")

        if reasons:
            return {
                "status": "BASELINE_UNAVAILABLE",
                "job_id": job_id,
                "reasons": reasons,
                "job_state": job.get("state"),
                "result_status": (result or {}).get("status", "MISSING"),
                "source_snapshot": snapshot,
            }
        return {
            "status": "VALID",
            "job_id": job_id,
            "reasons": [],
            "job_state": job.get("state"),
            "result_status": result.get("status"),
            "source_snapshot": snapshot,
            "result": result,
            "request": req,
        }

    def compare_candidate(
        self,
        session: dict[str, Any],
        candidate_request: dict[str, Any],
        candidate_result: dict[str, Any],
    ) -> dict[str, Any]:
        validation = self.validate(session, candidate_request)
        if validation["status"] != "VALID":
            return validation
        return {
            "status": "COMPARED",
            "baseline_job_id": validation["job_id"],
            "comparison": compare_results(candidate_result, validation["result"]),
            "baseline_validation": {k: v for k, v in validation.items() if k not in {"result", "request"}},
        }
