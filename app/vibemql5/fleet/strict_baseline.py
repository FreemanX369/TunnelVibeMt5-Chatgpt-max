"""STRICT environment comparison; source candidate identity is evidence, not equality."""
from __future__ import annotations

import re
from datetime import datetime
from .project_targets import canonical, exact_target, FleetProjectError
from .identity import normalize_path
from ..core.baseline import compare_results

FIELDS = ("target", "binding", "terminal_build", "compiler_build", "tester_model", "logical_config",
          "effective_period", "set_sha256", "include_sha256", "input_manifest_sha256",
          "broker_server", "history_evidence")


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _complete(field, value):
    try:
        canonical(value)
        if field == "target":
            exact_target(value)
            return True
        if field == "binding":
            return (isinstance(value, dict) and set(value) == {"executable", "data_root"}
                and all(normalize_path(path) == path for path in value.values()))
        if field in {"terminal_build", "compiler_build"}:
            return type(value) is int and value > 0
        if field == "tester_model":
            return type(value) is int and value in range(5)
        if field.endswith("sha256"):
            return _sha(value)
        if field == "effective_period":
            if type(value) is not dict or set(value) != {"from_date", "to_date"}: return False
            dates = [datetime.strptime(value[key], "%Y.%m.%d").date() for key in ("from_date", "to_date")]
            return dates[0] <= dates[1] and all(re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", item) for item in value.values())
        if field == "logical_config":
            from .native import _logical
            _logical(value)
            return True
        if field == "broker_server":
            return (isinstance(value, str) and bool(value.strip()) and len(value) <= 256
                    and not any(ord(char) < 32 for char in value))
        if field == "history_evidence":
            return isinstance(value, dict) and value.get("status") == "AVAILABLE" and _sha(value.get("sha256"))
    except Exception:
        return False
    return False


def strict_compare(candidate, baseline, *, explicit_cross_target=False):
    if not isinstance(candidate, dict) or not isinstance(baseline, dict) or type(explicit_cross_target) is not bool:
        raise FleetProjectError("FLEET_INPUT_INVALID")
    missing, mismatches = [], []
    for field in FIELDS:
        left, right = candidate.get(field), baseline.get(field)
        if not _complete(field, left) or not _complete(field, right):
            missing.append(field)
        elif canonical(left) != canonical(right):
            mismatches.append(field)
    missing.extend("source_sha256:" + side for side, obj in (("candidate", candidate), ("baseline", baseline))
                   if not _sha(obj.get("source_sha256")))
    status = "UNVERIFIED" if missing else "INCOMPATIBLE" if mismatches else "COMPATIBLE"
    return {"schema": "fleet.baseline/1", "policy": "STRICT", "status": status,
            "missing_fields": missing, "mismatched_fields": mismatches,
            "candidate_source_sha256": candidate.get("source_sha256") if _sha(candidate.get("source_sha256")) else None,
            "baseline_source_sha256": baseline.get("source_sha256") if _sha(baseline.get("source_sha256")) else None,
            "explicit_cross_target": explicit_cross_target, "auto_promote": False,
            "metrics": compare_results(candidate.get("result") or {}, baseline.get("result") or {})}
