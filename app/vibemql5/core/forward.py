from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import socket
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from .. import __version__
from ..config import default_root
from ..parsers.report import parse_report
from .jobs import JobStore
from .project_sessions import ProjectSessionManager
from .release import _atomic_write_bytes, _atomic_write_json, file_record, sha256_file, utc_now
from .revisions import RevisionManager


_REQUIRED_RELEASE_METRICS = ("trades", "net_profit", "profit_factor", "max_drawdown_pct")
_DEFAULT_DETERMINISTIC_FIELDS = (
    "bars",
    "ticks",
    "trades",
    "deals",
    "expected_payoff",
    "gross_loss",
    "gross_profit",
    "max_drawdown_pct",
    "net_profit",
    "profit_factor",
    "recovery_factor",
    "sharpe_ratio",
    "history_quality_pct",
)


def _json_file(path: Path) -> dict[str, Any]:
    if not Path(path).is_file():
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def _same_json(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, separators=(",", ":"), ensure_ascii=False) == json.dumps(
        b, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


class ForwardQualificationManager:
    """Owner-bound technical forward-readiness evidence pipeline.

    The pipeline intentionally does not certify profitability. It validates the exact
    owner-approved stress matrix, Windows-native evidence, deterministic repeat, and
    hash bindings. A successful promote operation may set forward_eligible=true in
    the canonical evidence manifest while live_eligible remains false.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.jobs = JobStore(self.root)
        self.sessions = ProjectSessionManager(self.root)
        self.revisions = RevisionManager(self.root)

    @staticmethod
    def _safe(value: str, label: str) -> str:
        raw = str(value or "").strip()
        if not raw or any(x in raw for x in ("/", "\\", "..")):
            raise ValueError(f"Invalid {label}")
        return raw

    def _proposal_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "TIP018-FORWARD-ACCEPTANCE-PROPOSAL.yaml"

    def _envelope_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "TIP018-FORWARD-ACCEPTANCE.json"

    def _approval_path(self) -> Path:
        return self.root / "docs" / "vibecode" / "OWNER_APPROVAL-TIP018.json"

    def _release_manifest_path(self) -> Path:
        return self.root / "evidence" / "manifest.json"

    def _authority(self, project_id: str) -> dict[str, Any]:
        proposal_path = self._proposal_path()
        envelope_path = self._envelope_path()
        approval_path = self._approval_path()
        release_path = self._release_manifest_path()
        if not proposal_path.is_file():
            raise FileNotFoundError("TIP018_FORWARD_PROPOSAL_MISSING")
        if not envelope_path.is_file():
            raise FileNotFoundError("TIP018_FORWARD_ENVELOPE_MISSING")
        if not approval_path.is_file():
            raise FileNotFoundError("TIP018_FORWARD_OWNER_APPROVAL_MISSING")
        if not release_path.is_file():
            raise FileNotFoundError("TIP018_RELEASE_MANIFEST_MISSING")

        proposal_sha = sha256_file(proposal_path)
        envelope = _json_file(envelope_path)
        approval = _json_file(approval_path)
        release = _json_file(release_path)
        release_sha = sha256_file(release_path)
        session = self.sessions.get(project_id)
        source = self.revisions.source_hash(str(session.get("workspace") or ""), str(session.get("ea") or ""))

        authority = envelope.get("authority_binding") or {}
        if envelope.get("schema_version") != "1.0" or envelope.get("status") != "APPROVED":
            raise RuntimeError("TIP018_FORWARD_ENVELOPE_NOT_APPROVED")
        if envelope.get("proposal_sha256") != proposal_sha:
            raise RuntimeError("TIP018_FORWARD_PROPOSAL_HASH_MISMATCH")
        if envelope.get("project_id") != project_id:
            raise RuntimeError("TIP018_FORWARD_ENVELOPE_PROJECT_MISMATCH")

        if approval.get("schema_version") != "1.0" or approval.get("status") != "APPROVED":
            raise RuntimeError("TIP018_FORWARD_OWNER_APPROVAL_NOT_APPROVED")
        if approval.get("project_id") != project_id:
            raise RuntimeError("TIP018_FORWARD_OWNER_APPROVAL_PROJECT_MISMATCH")
        if approval.get("proposal_sha256") != proposal_sha:
            raise RuntimeError("TIP018_FORWARD_OWNER_APPROVAL_PROPOSAL_HASH_MISMATCH")
        if approval.get("release_manifest_sha256") != release_sha:
            raise RuntimeError("TIP018_FORWARD_OWNER_APPROVAL_RELEASE_HASH_MISMATCH")
        if approval.get("approval_scope") != "forward_qualification":
            raise RuntimeError("TIP018_FORWARD_OWNER_APPROVAL_SCOPE_MISMATCH")

        if str(release.get("schema_version")) != "2.0" or release.get("release_eligible") is not True:
            raise RuntimeError("TIP018_RELEASE_AUTHORITY_NOT_RELEASE_ELIGIBLE")
        if release.get("forward_eligible") is not False or release.get("live_eligible") is not False:
            raise RuntimeError("TIP018_RELEASE_AUTHORITY_PRECONDITION_INVALID")
        if release.get("project_id") != project_id:
            raise RuntimeError("TIP018_RELEASE_AUTHORITY_PROJECT_MISMATCH")

        canonical = release.get("canonical") or {}
        expected = {
            "revision_id": authority.get("revision_id"),
            "revision_sha256": authority.get("revision_sha256"),
            "source_sha256": authority.get("source_sha256"),
            "source_bytes": authority.get("source_bytes"),
            "release_job_id": authority.get("release_job_id"),
            "release_manifest_sha256": authority.get("release_manifest_sha256"),
        }
        if expected["release_manifest_sha256"] != release_sha:
            raise RuntimeError("TIP018_FORWARD_ENVELOPE_RELEASE_HASH_MISMATCH")
        if release.get("job_id") != expected["release_job_id"]:
            raise RuntimeError("TIP018_FORWARD_RELEASE_JOB_MISMATCH")
        if canonical.get("revision_id") != expected["revision_id"]:
            raise RuntimeError("TIP018_FORWARD_REVISION_ID_MISMATCH")
        if str(canonical.get("revision_sha256") or "").lower() != str(expected["revision_sha256"] or "").lower():
            raise RuntimeError("TIP018_FORWARD_REVISION_HASH_MISMATCH")
        if str(canonical.get("source_sha256") or "").lower() != str(expected["source_sha256"] or "").lower():
            raise RuntimeError("TIP018_FORWARD_SOURCE_HASH_MISMATCH")
        if int(canonical.get("source_bytes") or -1) != int(expected["source_bytes"] or -2):
            raise RuntimeError("TIP018_FORWARD_SOURCE_BYTES_MISMATCH")
        if session.get("revision_id") != expected["revision_id"]:
            raise RuntimeError("TIP018_FORWARD_SESSION_REVISION_ID_MISMATCH")
        if str(session.get("revision_sha256") or "").lower() != str(expected["revision_sha256"] or "").lower():
            raise RuntimeError("TIP018_FORWARD_SESSION_REVISION_HASH_MISMATCH")
        if str(session.get("source_sha256") or "").lower() != str(expected["source_sha256"] or "").lower():
            raise RuntimeError("TIP018_FORWARD_SESSION_SOURCE_HASH_MISMATCH")
        if int(session.get("source_bytes") or -1) != int(expected["source_bytes"] or -2):
            raise RuntimeError("TIP018_FORWARD_SESSION_SOURCE_BYTES_MISMATCH")
        if source.get("sha256") != str(expected["source_sha256"] or "").lower() or int(source.get("bytes") or -1) != int(expected["source_bytes"] or -2):
            raise RuntimeError("TIP018_FORWARD_WORKSPACE_SOURCE_DRIFT")

        return {
            "proposal_path": proposal_path,
            "proposal_sha256": proposal_sha,
            "envelope_path": envelope_path,
            "envelope_sha256": sha256_file(envelope_path),
            "envelope": envelope,
            "approval_path": approval_path,
            "approval_sha256": sha256_file(approval_path),
            "approval": approval,
            "release_path": release_path,
            "release_sha256": release_sha,
            "release": release,
            "session": session,
            "source": source,
        }

    def _forward_dir(self, project_id: str, qualification_id: str) -> Path:
        project_id = self._safe(project_id, "project id")
        qualification_id = self._safe(qualification_id, "qualification id")
        p = self.root / "evidence" / "forward" / project_id / qualification_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _qualification_id(self, project_id: str, jobs: dict[str, str], authority: dict[str, Any]) -> str:
        payload = {
            "project_id": project_id,
            "jobs": jobs,
            "proposal_sha256": authority["proposal_sha256"],
            "release_manifest_sha256": authority["release_sha256"],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return "FQ-" + digest[:20].upper()

    @staticmethod
    def _expected_effective_config(spec: dict[str, Any]) -> dict[str, Any]:
        keys = ("symbol", "period", "model", "deposit", "currency", "leverage")
        out = {k: spec.get(k) for k in keys}
        if spec.get("from_date") is not None:
            out["from_date"] = spec.get("from_date")
        if spec.get("to_date") is not None:
            out["to_date"] = spec.get("to_date")
        return out

    def _evaluate_job(self, project_id: str, run_spec: dict[str, Any], job_id: str, authority: dict[str, Any]) -> dict[str, Any]:
        session = authority["session"]
        job = self.jobs.load(job_id)
        run_dir = self.root / "runs" / job_id
        result = _json_file(run_dir / "result.json")
        compile_data = _json_file(run_dir / "compile.json")
        request = _json_file(run_dir / "request.json") or dict(job.get("request") or {})
        gates: dict[str, str] = {}
        reasons: list[str] = []

        def gate(name: str, ok: bool, reason: str) -> None:
            gates[name] = "PASS" if ok else "FAIL"
            if not ok:
                reasons.append(reason)

        gate("job_terminal_pass", job.get("state") == "PASSED" and result.get("status") == "PASSED", "FORWARD_JOB_NOT_PASSED")
        tester = result.get("tester") or {}
        gate(
            "windows_native_test",
            tester.get("execution_status") == "PASSED"
            and tester.get("report_status") == "PARSED"
            and tester.get("source") == "windows_native_mt5_strategy_tester"
            and bool(tester.get("command"))
            and str(result.get("platform") or "").lower() == "windows"
            and not bool(request.get("mock"))
            and not bool((result.get("environment") or {}).get("mock")),
            "FORWARD_NATIVE_TEST_REQUIRED",
        )
        gate(
            "native_compile",
            compile_data.get("status") == "PASSED"
            and int(compile_data.get("errors") or 0) == 0
            and int(compile_data.get("warnings") or 0) == 0
            and compile_data.get("source") == "windows_native_metaeditor"
            and bool(compile_data.get("command"))
            and not bool(compile_data.get("mock")),
            "FORWARD_NATIVE_COMPILE_REQUIRED",
        )
        gate(
            "target_binding",
            str(request.get("workspace") or "") == str(session.get("workspace") or "")
            and str(request.get("ea") or "").replace("\\", "/") == str(session.get("ea") or "").replace("\\", "/")
            and str(request.get("terminal") or "") == str(run_spec.get("terminal") or ""),
            "FORWARD_REQUEST_TARGET_MISMATCH",
        )
        gate(
            "preset_binding",
            str(request.get("preset") or "") == str(run_spec.get("base_preset") or ""),
            "FORWARD_PRESET_MISMATCH",
        )

        resolved = result.get("resolved_preset") or {}
        expected_effective = self._expected_effective_config(run_spec)
        environment = result.get("environment") or {}
        environment_record = _json_file(run_dir / "environment.json")
        effective_ok = bool(resolved)
        if effective_ok:
            for key, expected in expected_effective.items():
                actual = resolved.get(key)
                if key == "symbol" and actual != expected:
                    requested_symbol = environment_record.get("requested_symbol") or environment.get("requested_symbol")
                    resolved_symbol = environment_record.get("resolved_symbol") or environment.get("resolved_symbol")
                    result_requested_symbol = environment.get("requested_symbol")
                    result_resolved_symbol = environment.get("resolved_symbol")
                    preflight = environment_record.get("requested_terminal_preflight") or {}
                    symbol_provenance_ok = (
                        requested_symbol == expected
                        and resolved_symbol == actual
                        and (result_requested_symbol in (None, requested_symbol))
                        and (result_resolved_symbol in (None, resolved_symbol))
                        and preflight.get("ok") is True
                        and preflight.get("code") == "READY"
                        and preflight.get("resolved_symbol") == actual
                    )
                    if not symbol_provenance_ok:
                        effective_ok = False
                        break
                elif actual != expected:
                    effective_ok = False
                    break
        gate("effective_config_binding", effective_ok, "FORWARD_EFFECTIVE_CONFIG_MISMATCH")

        snapshot = run_dir / "source_snapshot" / Path(str(session.get("ea") or "").replace("\\", "/"))
        snap = file_record(snapshot, logical_name="source_snapshot")
        gate(
            "source_binding",
            bool(snap.get("exists"))
            and snap.get("sha256") == str(session.get("source_sha256") or "").lower()
            and int(snap.get("bytes") or -1) == int(session.get("source_bytes") or -2),
            "FORWARD_SOURCE_SNAPSHOT_MISMATCH",
        )

        ex5 = run_dir / "compiled.ex5"
        ex5_rec = file_record(ex5, logical_name="compiled_ex5")
        immutable = compile_data.get("immutable_ex5") or {}
        gate(
            "immutable_ex5",
            bool(ex5_rec.get("exists"))
            and ex5_rec.get("sha256") == immutable.get("sha256")
            and int(ex5_rec.get("bytes") or -1) == int(immutable.get("bytes") or -2),
            "FORWARD_IMMUTABLE_EX5_HASH_MISMATCH",
        )

        xml = run_dir / "report.xml"
        xml_rec = file_record(xml, logical_name="normalized_xml_report")
        parsed_xml = parse_report(xml) if xml.is_file() else {"status": "MISSING", "metrics": {}}
        native_report_name = str((result.get("artifacts") or {}).get("native_report") or "report.htm")
        native_report = Path(native_report_name)
        if not native_report.is_absolute():
            native_report = run_dir / native_report
        try:
            native_report.resolve().relative_to(run_dir.resolve())
        except (OSError, ValueError):
            native_report = run_dir / "__INVALID_NATIVE_REPORT_PATH__"
        if not native_report.is_file():
            for alt in (run_dir / "report.htm", run_dir / "report.html", run_dir / "report.native.xml"):
                if alt.is_file():
                    native_report = alt
                    break
        native_rec = file_record(native_report, logical_name="native_mt5_report")
        xml_prov = parsed_xml.get("provenance") or {}
        xml_source = xml_prov.get("native_report") or {}
        xml_metrics = parsed_xml.get("metrics") or {}
        gate(
            "xml_report",
            bool(xml_rec.get("exists"))
            and int(xml_rec.get("bytes") or 0) > 0
            and parsed_xml.get("status") == "PARSED"
            and xml_prov.get("source_kind") == "derived_from_native_mt5_report"
            and xml_prov.get("schema_version") == "2.0"
            and bool(native_rec.get("exists"))
            and xml_source.get("sha256") == native_rec.get("sha256")
            and int(xml_source.get("bytes") or -1) == int(native_rec.get("bytes") or -2),
            "FORWARD_HASH_BOUND_XML_REPORT_INVALID",
        )

        metrics = result.get("strategy") or {}
        gate(
            "required_release_metrics",
            all(metrics.get(k) is not None for k in _REQUIRED_RELEASE_METRICS),
            "FORWARD_REQUIRED_METRICS_MISSING",
        )
        gate(
            "xml_metric_binding",
            all(xml_metrics.get(k) == metrics.get(k) for k in _REQUIRED_RELEASE_METRICS),
            "FORWARD_XML_METRIC_MISMATCH",
        )
        finite_ok = all(_finite_number(v) for v in metrics.values() if isinstance(v, (int, float)) and not isinstance(v, bool))
        gate("finite_metrics", bool(metrics) and finite_ok, "FORWARD_NONFINITE_METRIC")
        gate("history_quality", metrics.get("history_quality_pct") == 100.0, "FORWARD_HISTORY_QUALITY_NOT_100")
        trades = metrics.get("trades")
        gate("minimum_trades", _finite_number(trades) and float(trades) >= 1.0, "FORWARD_ZERO_TRADE_RUN")
        gate(
            "provenance",
            all(bool(result.get(k)) for k in ("tool_version", "host", "recorded_at_utc"))
            and bool(tester.get("execution_context"))
            and bool(tester.get("command"))
            and bool(compile_data.get("command")),
            "FORWARD_PROVENANCE_INCOMPLETE",
        )
        gate("tester_runtime_errors", not bool(tester.get("fatal_errors")), "FORWARD_TESTER_RUNTIME_ERROR")

        artifacts = {
            "compiled_ex5": ex5_rec,
            "normalized_xml_report": xml_rec,
            "native_mt5_report": native_rec,
            "compile_log": file_record(run_dir / "compile.log", logical_name="compile_log"),
            "tester_log": file_record(run_dir / "tester.log", logical_name="tester_log"),
            "result_json": file_record(run_dir / "result.json", logical_name="result_json"),
            "request_json": file_record(run_dir / "request.json", logical_name="request_json"),
            "source_snapshot": snap,
        }
        gate(
            "required_artifacts",
            all(bool(v.get("exists")) and int(v.get("bytes") or 0) > 0 and bool(v.get("sha256")) for v in artifacts.values()),
            "FORWARD_REQUIRED_ARTIFACT_MISSING",
        )

        return {
            "run_id": str(run_spec.get("id") or ""),
            "job_id": job_id,
            "status": "PASS" if not reasons else "FAIL",
            "gates": gates,
            "reasons": reasons,
            "request": request,
            "effective_config": resolved,
            "metrics": metrics,
            "artifacts": artifacts,
            "result_provenance": {
                "tool_version": result.get("tool_version"),
                "host": result.get("host"),
                "platform": result.get("platform"),
                "recorded_at_utc": result.get("recorded_at_utc"),
                "compile": {"source": compile_data.get("source"), "command": compile_data.get("command")},
                "backtest": {"source": tester.get("source"), "command": tester.get("command")},
            },
        }

    @staticmethod
    def _matrix_jobs(jobs_payload: dict[str, Any]) -> dict[str, str]:
        raw = jobs_payload.get("jobs") or {}
        if not isinstance(raw, dict):
            raise ValueError("TIP018_FORWARD_JOBS_INVALID")
        return {str(k): str(v) for k, v in raw.items() if str(k).strip() and str(v).strip()}

    def _evaluate(self, project_id: str, jobs_payload: dict[str, Any]) -> dict[str, Any]:
        project_id = self._safe(project_id, "project id")
        authority = self._authority(project_id)
        envelope = authority["envelope"]
        specs = list((envelope.get("stress_matrix") or {}).get("runs") or [])
        expected_count = int((envelope.get("stress_matrix") or {}).get("run_count") or 0)
        jobs = self._matrix_jobs(jobs_payload)
        run_ids = [str(x.get("id") or "") for x in specs]
        reasons: list[str] = []
        gates: dict[str, str] = {}

        def gate(name: str, ok: bool, reason: str) -> None:
            gates[name] = "PASS" if ok else "FAIL"
            if not ok:
                reasons.append(reason)

        gate("matrix_count", expected_count == len(specs) == len(jobs), "FORWARD_MATRIX_COUNT_MISMATCH")
        gate("matrix_ids", set(run_ids) == set(jobs), "FORWARD_MATRIX_JOB_IDS_MISMATCH")
        gate("matrix_unique_jobs", len(set(jobs.values())) == len(jobs), "FORWARD_MATRIX_JOB_REUSE_FORBIDDEN")

        runs: dict[str, Any] = {}
        if gates["matrix_ids"] == "PASS":
            for spec in specs:
                run_id = str(spec.get("id") or "")
                try:
                    result = self._evaluate_job(project_id, spec, jobs[run_id], authority)
                except Exception as exc:
                    result = {"run_id": run_id, "job_id": jobs.get(run_id), "status": "FAIL", "gates": {}, "reasons": [f"FORWARD_JOB_EVALUATION_ERROR:{type(exc).__name__}:{exc}"]}
                runs[run_id] = result
                if result.get("status") != "PASS":
                    reasons.extend([f"{run_id}:{x}" for x in (result.get("reasons") or ["FORWARD_RUN_FAILED"])])

        repeat_gate = "PASS"
        repeat_details: dict[str, Any] = {}
        for spec in specs:
            other = str(spec.get("compare_exact_metrics_with") or "")
            if not other:
                continue
            run_id = str(spec.get("id") or "")
            fields = tuple(((envelope.get("acceptance_gates") or {}).get("deterministic_repeat") or {}).get("fields") or _DEFAULT_DETERMINISTIC_FIELDS)
            left = (runs.get(run_id) or {}).get("metrics") or {}
            right = (runs.get(other) or {}).get("metrics") or {}
            missing = [k for k in fields if k not in left or k not in right]
            mismatches = {k: {"a": right.get(k), "b": left.get(k)} for k in fields if k in left and k in right and left.get(k) != right.get(k)}
            ok = not missing and not mismatches
            repeat_details[f"{other}=={run_id}"] = {"status": "PASS" if ok else "FAIL", "fields": list(fields), "missing": missing, "mismatches": mismatches}
            if not ok:
                repeat_gate = "FAIL"
                reasons.append("FORWARD_DETERMINISTIC_REPEAT_MISMATCH")
        gates["deterministic_repeat"] = repeat_gate

        overall = "PASS" if not reasons and runs and all(x.get("status") == "PASS" for x in runs.values()) else "FAIL"
        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "status": overall,
            "release_eligible": True,
            "forward_eligible": overall == "PASS",
            "live_eligible": False,
            "gates": gates,
            "reasons": reasons,
            "authority": {
                "proposal_sha256": authority["proposal_sha256"],
                "envelope_sha256": authority["envelope_sha256"],
                "owner_approval_sha256": authority["approval_sha256"],
                "release_manifest_sha256": authority["release_sha256"],
                "revision_id": authority["session"].get("revision_id"),
                "revision_sha256": authority["session"].get("revision_sha256"),
                "source_sha256": authority["session"].get("source_sha256"),
                "source_bytes": authority["session"].get("source_bytes"),
                "baseline_job_id": authority["session"].get("baseline_job_id"),
            },
            "jobs": jobs,
            "runs": runs,
            "deterministic_repeat": repeat_details,
            "performance_policy": (envelope.get("acceptance_gates") or {}).get("performance_policy") or {},
            "runtime": {"tool_version": __version__, "host": socket.gethostname()},
        }

    def _persist_artifacts(self, evaluation: dict[str, Any], forward_dir: Path) -> dict[str, Any]:
        copied: dict[str, Any] = {}
        for run_id, run in (evaluation.get("runs") or {}).items():
            dst_root = forward_dir / "artifacts" / run_id
            dst_root.mkdir(parents=True, exist_ok=True)
            copied[run_id] = {}
            for name, rec in (run.get("artifacts") or {}).items():
                src = Path(str(rec.get("path") or ""))
                if not src.is_file():
                    raise FileNotFoundError(f"FORWARD_ARTIFACT_MISSING_DURING_COPY:{run_id}:{name}")
                suffix = src.suffix or ".bin"
                dst = dst_root / f"{name}{suffix}"
                shutil.copy2(src, dst)
                new = file_record(dst, logical_name=f"{run_id}:{name}")
                if new.get("sha256") != rec.get("sha256") or int(new.get("bytes") or -1) != int(rec.get("bytes") or -2):
                    raise RuntimeError(f"FORWARD_ARTIFACT_COPY_HASH_MISMATCH:{run_id}:{name}")
                copied[run_id][name] = new
        return copied

    def check(self, project_id: str, jobs_payload: dict[str, Any]) -> dict[str, Any]:
        evaluation = self._evaluate(project_id, jobs_payload)
        authority = self._authority(project_id)
        jobs = self._matrix_jobs(jobs_payload)
        qid = self._qualification_id(project_id, jobs, authority)
        forward_dir = self._forward_dir(project_id, qid)
        record = dict(evaluation)
        record["qualification_id"] = qid
        record["checked_at_utc"] = utc_now()
        if evaluation.get("status") == "PASS":
            record["evidence_artifacts"] = self._persist_artifacts(evaluation, forward_dir)
        path = forward_dir / "forward-check.json"
        _atomic_write_json(path, record)
        return {**record, "path": str(path), "sha256": sha256_file(path)}

    def _validate_saved_check(self, project_id: str, qualification_id: str) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        authority = self._authority(project_id)
        forward_dir = self._forward_dir(project_id, qualification_id)
        path = forward_dir / "forward-check.json"
        check = _json_file(path)
        if check.get("status") != "PASS" or check.get("forward_eligible") is not True:
            raise RuntimeError("FORWARD_CHECK_NOT_PASS")
        if check.get("qualification_id") != qualification_id:
            raise RuntimeError("FORWARD_CHECK_QUALIFICATION_ID_MISMATCH")
        current = self._evaluate(project_id, {"jobs": check.get("jobs") or {}})
        if current.get("status") != "PASS":
            raise RuntimeError("FORWARD_EVIDENCE_NO_LONGER_VALID:" + ",".join(current.get("reasons") or []))
        for run_id, run in (check.get("runs") or {}).items():
            cur = (current.get("runs") or {}).get(run_id) or {}
            for name, old in (run.get("artifacts") or {}).items():
                now = (cur.get("artifacts") or {}).get(name) or {}
                if old.get("sha256") != now.get("sha256") or int(old.get("bytes") or -1) != int(now.get("bytes") or -2):
                    raise RuntimeError(f"FORWARD_ARTIFACT_DRIFT:{run_id}:{name}")
        return check, path, authority

    def attest(self, project_id: str, qualification_id: str) -> dict[str, Any]:
        check, check_path, authority = self._validate_saved_check(project_id, qualification_id)
        forward_dir = self._forward_dir(project_id, qualification_id)
        artifact_hashes: dict[str, Any] = {}
        for run_id, artifacts in (check.get("evidence_artifacts") or {}).items():
            artifact_hashes[run_id] = {name: rec.get("sha256") for name, rec in artifacts.items()}
        record = {
            "schema_version": "1.0",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "status": "PASS",
            "attestation_type": "owner_bound_forward_technical_hash_chain",
            "attested_at_utc": utc_now(),
            "tool_version": __version__,
            "host": socket.gethostname(),
            "forward_check": {"path": str(check_path), "sha256": sha256_file(check_path)},
            "proposal_sha256": authority["proposal_sha256"],
            "envelope_sha256": authority["envelope_sha256"],
            "owner_approval": {"path": str(authority["approval_path"]), "sha256": authority["approval_sha256"]},
            "release_manifest_sha256": authority["release_sha256"],
            "artifact_hashes": artifact_hashes,
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
        }
        path = forward_dir / "forward-attestation.json"
        _atomic_write_json(path, record)
        return {**record, "path": str(path), "sha256": sha256_file(path)}

    def promote(self, project_id: str, qualification_id: str) -> dict[str, Any]:
        canonical_path = self._release_manifest_path()
        existing = _json_file(canonical_path)
        if existing.get("forward_eligible") is True:
            fwd = existing.get("forward_qualification") or {}
            if fwd.get("qualification_id") == qualification_id:
                return {
                    "schema_version": "1.0",
                    "status": "PASS",
                    "idempotent": True,
                    "project_id": project_id,
                    "qualification_id": qualification_id,
                    "release_eligible": True,
                    "forward_eligible": True,
                    "live_eligible": False,
                    "canonical_manifest": {"path": str(canonical_path), "sha256": sha256_file(canonical_path)},
                }
            raise RuntimeError("FORWARD_ALREADY_PROMOTED_BY_DIFFERENT_QUALIFICATION")

        check, check_path, authority = self._validate_saved_check(project_id, qualification_id)
        forward_dir = self._forward_dir(project_id, qualification_id)
        att_path = forward_dir / "forward-attestation.json"
        att = _json_file(att_path)
        if att.get("status") != "PASS" or att.get("forward_eligible") is not True:
            raise RuntimeError("FORWARD_ATTESTATION_NOT_PASS")
        if (att.get("forward_check") or {}).get("sha256") != sha256_file(check_path):
            raise RuntimeError("FORWARD_ATTESTATION_CHECK_HASH_MISMATCH")
        if att.get("owner_approval", {}).get("sha256") != authority["approval_sha256"]:
            raise RuntimeError("FORWARD_ATTESTATION_OWNER_APPROVAL_HASH_MISMATCH")
        if att.get("release_manifest_sha256") != authority["release_sha256"]:
            raise RuntimeError("FORWARD_ATTESTATION_RELEASE_HASH_MISMATCH")

        for run_id, hashes in (att.get("artifact_hashes") or {}).items():
            copied = (check.get("evidence_artifacts") or {}).get(run_id) or {}
            for name, expected in hashes.items():
                rec = copied.get(name) or {}
                p = Path(str(rec.get("path") or ""))
                if not p.is_file() or sha256_file(p) != expected:
                    raise RuntimeError(f"FORWARD_ATTESTED_ARTIFACT_MISMATCH:{run_id}:{name}")

        forward_manifest = {
            "schema_version": "2.0",
            "manifest_type": "vibemql5_forward_evidence",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "recorded_at_utc": utc_now(),
            "tool_version": __version__,
            "host": socket.gethostname(),
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
            "source_release_manifest_sha256": authority["release_sha256"],
            "proposal_sha256": authority["proposal_sha256"],
            "envelope_sha256": authority["envelope_sha256"],
            "owner_approval": {"path": str(authority["approval_path"]), "sha256": authority["approval_sha256"]},
            "forward_check": {"path": str(check_path), "sha256": sha256_file(check_path)},
            "attestation": {"path": str(att_path), "sha256": sha256_file(att_path)},
            "jobs": check.get("jobs") or {},
            "matrix_metrics": {run_id: (run.get("metrics") or {}) for run_id, run in (check.get("runs") or {}).items()},
            "deterministic_repeat": check.get("deterministic_repeat") or {},
            "performance_policy": check.get("performance_policy") or {},
            "policy": {
                "release": "PASS",
                "forward": "PASS_OWNER_APPROVAL_AND_FORWARD_STRESS_EVIDENCE",
                "live": "BLOCKED_OWNER_APPROVAL_AND_REAL_ENVIRONMENT_GATES",
            },
        }
        manifest_candidate = forward_dir / "forward-manifest.json"
        _atomic_write_json(manifest_candidate, forward_manifest)
        forward_manifest_sha = sha256_file(manifest_candidate)

        promote_record = {
            "schema_version": "1.0",
            "status": "PASS",
            "project_id": project_id,
            "qualification_id": qualification_id,
            "promoted_at_utc": utc_now(),
            "release_eligible": True,
            "forward_eligible": True,
            "live_eligible": False,
            "forward_manifest": {"path": str(manifest_candidate), "sha256": forward_manifest_sha},
        }
        promote_path = forward_dir / "forward-promote.json"
        _atomic_write_json(promote_path, promote_record)

        zip_path = forward_dir / f"forward-evidence-{qualification_id}.zip"
        tmp_zip = forward_dir / f".{zip_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for artifact_path in sorted(forward_dir.rglob("*")):
                    if artifact_path.is_file() and artifact_path not in {zip_path, tmp_zip}:
                        zf.write(artifact_path, artifact_path.relative_to(forward_dir))
            os.replace(tmp_zip, zip_path)
        finally:
            try:
                tmp_zip.unlink(missing_ok=True)
            except OSError:
                pass

        # Canonical forward promotion is the final commit point. Never modify the
        # release manifest until the forward package exists and all bound hashes pass.
        if sha256_file(canonical_path) != authority["release_sha256"]:
            raise RuntimeError("FORWARD_CANONICAL_RELEASE_MANIFEST_DRIFT_BEFORE_COMMIT")
        canonical = deepcopy(authority["release"])
        canonical["recorded_at_utc"] = utc_now()
        canonical["tool_version"] = __version__
        canonical["host"] = socket.gethostname()
        canonical["release_eligible"] = True
        canonical["forward_eligible"] = True
        canonical["live_eligible"] = False
        policy = dict(canonical.get("policy") or {})
        policy["release"] = "PASS"
        policy["forward"] = "PASS_OWNER_APPROVAL_AND_FORWARD_STRESS_EVIDENCE"
        policy["live"] = "BLOCKED_OWNER_APPROVAL_AND_REAL_ENVIRONMENT_GATES"
        canonical["policy"] = policy
        canonical["forward_qualification"] = {
            "qualification_id": qualification_id,
            "forward_manifest": {"path": str(manifest_candidate), "sha256": forward_manifest_sha},
            "package": {"path": str(zip_path), "sha256": sha256_file(zip_path), "bytes": int(zip_path.stat().st_size)},
            "owner_approval_sha256": authority["approval_sha256"],
            "envelope_sha256": authority["envelope_sha256"],
            "proposal_sha256": authority["proposal_sha256"],
            "source_release_manifest_sha256": authority["release_sha256"],
            "jobs": check.get("jobs") or {},
        }
        canonical_candidate = forward_dir / "canonical-manifest-forward.json"
        _atomic_write_json(canonical_candidate, canonical)
        canonical_sha = sha256_file(canonical_candidate)
        _atomic_write_bytes(canonical_path, canonical_candidate.read_bytes())
        if sha256_file(canonical_path) != canonical_sha:
            raise RuntimeError("FORWARD_CANONICAL_MANIFEST_COMMIT_HASH_MISMATCH")

        return {
            **promote_record,
            "path": str(promote_path),
            "sha256": sha256_file(promote_path),
            "package": {"path": str(zip_path), "sha256": sha256_file(zip_path), "bytes": int(zip_path.stat().st_size)},
            "canonical_manifest": {"path": str(canonical_path), "sha256": canonical_sha},
        }
