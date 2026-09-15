from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import xml.etree.ElementTree as ET
import zipfile
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from ..config import default_root
from ..parsers.report import parse_report
from .jobs import JobStore
from .project_sessions import ProjectSessionManager
from .revisions import RevisionManager

_TERMINAL = {"PASSED", "ANOMALY", "FAILED", "TIMEOUT", "CANCELLED", "INTERRUPTED", "RESOURCE_LIMIT"}
_REQUIRED_METRICS = ("trades", "net_profit", "profit_factor", "max_drawdown_pct")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()




def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".v-{uuid4().hex[:8]}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write_bytes(path, data)


def file_record(path: Path, *, logical_name: str = "") -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {"exists": False, "path": str(p), "logical_name": logical_name}
    return {
        "exists": True,
        "path": str(p),
        "logical_name": logical_name,
        "bytes": int(p.stat().st_size),
        "sha256": sha256_file(p),
    }


def write_normalized_report_xml(run_dir: Path, native_report: Path, metrics: dict[str, Any]) -> dict[str, Any]:
    """Create a canonical XML metrics envelope bound to the captured native MT5 report.

    MT5 single-test automation normally emits HTML. Release policy still requires a
    non-empty XML report with metrics, so this file is a deterministic *derived*
    evidence envelope, never a claim that MT5 emitted XML natively. The native report
    hash and size are embedded and revalidated by ReleaseEvidenceManager.
    """
    run_dir = Path(run_dir)
    native_report = Path(native_report)
    if not native_report.is_file() or native_report.stat().st_size <= 0:
        raise FileNotFoundError(f"Native report missing: {native_report}")
    missing = [k for k in _REQUIRED_METRICS if metrics.get(k) is None]
    if missing:
        raise ValueError("NORMALIZED_XML_REQUIRED_METRICS_MISSING:" + ",".join(missing))

    root = ET.Element(
        "vibemql5_backtest_report",
        {
            "schema_version": "2.0",
            "source_kind": "derived_from_native_mt5_report",
        },
    )
    provenance = ET.SubElement(root, "provenance")
    native = file_record(native_report, logical_name="native_mt5_report")
    ET.SubElement(
        provenance,
        "native_report",
        {
            "path": native_report.name,
            "sha256": str(native["sha256"]),
            "bytes": str(native["bytes"]),
        },
    )
    ET.SubElement(provenance, "generated_at_utc").text = utc_now()
    metrics_el = ET.SubElement(root, "metrics")
    for key in sorted(metrics):
        value = metrics.get(key)
        if value is None:
            continue
        item = ET.SubElement(metrics_el, "metric", {"name": str(key)})
        item.text = str(value)

    xml_path = run_dir / "report.xml"
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _atomic_write_bytes(xml_path, data)
    return {
        "path": str(xml_path),
        "sha256": sha256_file(xml_path),
        "bytes": int(xml_path.stat().st_size),
        "source_report": native,
    }


class ReleaseEvidenceManager:
    """Fail-closed technical release evidence pipeline.

    This pipeline may promote *release_eligible* only after exact Windows-native job
    evidence passes. It never promotes forward/live eligibility and never mutates EA,
    project-session, baseline, or workspace state.
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

    def _release_dir(self, project_id: str, job_id: str) -> Path:
        project_id = self._safe(project_id, "project id")
        job_id = self._safe(job_id, "job id")
        p = self.root / "evidence" / "release" / project_id / job_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        if not Path(path).is_file():
            return {}
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _same_json(a: Any, b: Any) -> bool:
        return json.dumps(a or {}, sort_keys=True, separators=(",", ":")) == json.dumps(
            b or {}, sort_keys=True, separators=(",", ":")
        )

    def _evaluate(self, project_id: str, job_id: str) -> dict[str, Any]:
        project_id = self._safe(project_id, "project id")
        job_id = self._safe(job_id, "job id")
        session = self.sessions.get(project_id)
        job = self.jobs.load(job_id)
        run = self.root / "runs" / job_id
        result = self._json(run / "result.json")
        compile_data = self._json(run / "compile.json")
        request = self._json(run / "request.json") or dict(job.get("request") or {})
        environment = self._json(run / "environment.json")

        gates: dict[str, str] = {}
        reasons: list[str] = []

        def gate(name: str, ok: bool, reason: str) -> None:
            gates[name] = "PASS" if ok else "FAIL"
            if not ok:
                reasons.append(reason)

        gate("job_terminal_pass", job.get("state") == "PASSED" and result.get("status") == "PASSED", "JOB_NOT_PASSED")
        tester = result.get("tester") or {}
        env_result = result.get("environment") or {}
        gate(
            "native_test",
            tester.get("execution_status") == "PASSED"
            and tester.get("report_status") == "PARSED"
            and str(result.get("platform") or "").lower() == "windows"
            and tester.get("source") == "windows_native_mt5_strategy_tester"
            and bool(tester.get("command"))
            and not bool(request.get("mock"))
            and not bool(env_result.get("mock")),
            "NATIVE_TEST_NOT_RELEASE_QUALITY",
        )
        gate(
            "native_compile",
            compile_data.get("status") == "PASSED"
            and int(compile_data.get("errors") or 0) == 0
            and int(compile_data.get("warnings") or 0) == 0
            and not bool(compile_data.get("mock"))
            and compile_data.get("source") == "windows_native_metaeditor"
            and bool(compile_data.get("command")),
            "NATIVE_COMPILE_NOT_0_ERROR_0_WARNING",
        )

        session_source = self.revisions.source_hash(str(session.get("workspace") or ""), str(session.get("ea") or ""))
        snapshot = run / "source_snapshot" / Path(str(session.get("ea") or "").replace("\\", "/"))
        snap = file_record(snapshot, logical_name="source_snapshot")
        gate(
            "source_binding",
            bool(snap.get("exists"))
            and snap.get("sha256") == str(session.get("source_sha256") or "").lower()
            and int(snap.get("bytes") or -1) == int(session.get("source_bytes") or -2)
            and session_source.get("sha256") == str(session.get("source_sha256") or "").lower()
            and int(session_source.get("bytes") or -1) == int(session.get("source_bytes") or -2),
            "SOURCE_BINDING_MISMATCH",
        )

        gate(
            "request_target",
            str(request.get("workspace") or "") == str(session.get("workspace") or "")
            and str(request.get("ea") or "").replace("\\", "/") == str(session.get("ea") or "").replace("\\", "/"),
            "REQUEST_TARGET_MISMATCH",
        )

        baseline_id = str(session.get("baseline_job_id") or "")
        baseline_request: dict[str, Any] = {}
        if baseline_id:
            try:
                baseline_request = dict(self.jobs.load(baseline_id).get("request") or {})
            except Exception:
                baseline_request = {}
        comparable_fields = ("workspace", "ea", "preset", "set_file", "overrides", "mock")
        config_ok = bool(baseline_request)
        if config_ok:
            for key in comparable_fields:
                a = request.get(key)
                b = baseline_request.get(key)
                if key == "ea":
                    a = str(a or "").replace("\\", "/")
                    b = str(b or "").replace("\\", "/")
                if key == "overrides":
                    if not self._same_json(a, b):
                        config_ok = False
                        break
                elif a != b:
                    config_ok = False
                    break
        gate("baseline_config_compatibility", config_ok, "BASELINE_TEST_CONFIG_MISMATCH")

        ex5 = run / "compiled.ex5"
        ex5_rec = file_record(ex5, logical_name="compiled_ex5")
        compile_art = compile_data.get("immutable_ex5") or {}
        gate(
            "immutable_ex5",
            bool(ex5_rec.get("exists"))
            and ex5_rec.get("sha256") == compile_art.get("sha256")
            and int(ex5_rec.get("bytes") or -1) == int(compile_art.get("bytes") or -2),
            "IMMUTABLE_RUN_BOUND_EX5_HASH_MISSING_OR_MISMATCH",
        )

        xml = run / "report.xml"
        xml_rec = file_record(xml, logical_name="normalized_xml_report")
        parsed_xml = parse_report(xml) if xml.is_file() else {"status": "MISSING", "metrics": {}}
        native_report_name = str((result.get("artifacts") or {}).get("native_report") or "report.htm")
        native_report = Path(native_report_name)
        if not native_report.is_absolute():
            native_report = run / native_report
        try:
            native_report.resolve().relative_to(run.resolve())
        except (OSError, ValueError):
            native_report = run / "__INVALID_NATIVE_REPORT_PATH__"
        if not native_report.is_file():
            for alt in (run / "report.htm", run / "report.html", run / "report.native.xml"):
                if alt.is_file():
                    native_report = alt
                    break
        native_rec = file_record(native_report, logical_name="native_mt5_report")
        xml_source = (parsed_xml.get("provenance") or {}).get("native_report") or {}
        xml_metrics = parsed_xml.get("metrics") or {}
        xml_ok = (
            bool(xml_rec.get("exists"))
            and int(xml_rec.get("bytes") or 0) > 0
            and parsed_xml.get("status") == "PARSED"
            and (parsed_xml.get("provenance") or {}).get("source_kind") == "derived_from_native_mt5_report"
            and (parsed_xml.get("provenance") or {}).get("schema_version") == "2.0"
            and all(xml_metrics.get(k) is not None for k in _REQUIRED_METRICS)
            and bool(native_rec.get("exists"))
            and xml_source.get("sha256") == native_rec.get("sha256")
            and int(xml_source.get("bytes") or -1) == int(native_rec.get("bytes") or -2)
        )
        gate("xml_report", xml_ok, "NONEMPTY_HASH_BOUND_XML_REPORT_MISSING_OR_INVALID")

        metrics = result.get("strategy") or {}
        gate("parsed_metrics", all(metrics.get(k) is not None for k in _REQUIRED_METRICS), "REQUIRED_PARSED_METRICS_MISSING")
        gate(
            "xml_metric_binding",
            all(xml_metrics.get(k) == metrics.get(k) for k in _REQUIRED_METRICS),
            "XML_METRICS_DO_NOT_MATCH_NATIVE_PARSED_RESULT",
        )
        provenance_ok = (
            all(bool(result.get(k)) for k in ("tool_version", "host", "recorded_at_utc"))
            and str(result.get("platform") or "").lower() == "windows"
            and bool(tester.get("execution_context"))
            and tester.get("source") == "windows_native_mt5_strategy_tester"
            and bool(tester.get("command"))
            and compile_data.get("source") == "windows_native_metaeditor"
            and bool(compile_data.get("command"))
        )
        gate("release_provenance", provenance_ok, "RELEASE_PROVENANCE_INCOMPLETE")

        artifacts = {
            "compiled_ex5": ex5_rec,
            "normalized_xml_report": xml_rec,
            "native_mt5_report": native_rec,
            "compile_log": file_record(run / "compile.log", logical_name="compile_log"),
            "tester_log": file_record(run / "tester.log", logical_name="tester_log"),
            "result_json": file_record(run / "result.json", logical_name="result_json"),
            "source_snapshot": snap,
        }
        all_artifacts_ok = all(bool(v.get("exists")) and int(v.get("bytes") or 0) > 0 and bool(v.get("sha256")) for v in artifacts.values())
        gate("required_artifacts", all_artifacts_ok, "REQUIRED_RELEASE_ARTIFACT_MISSING")

        return {
            "schema_version": "2.0",
            "project_id": project_id,
            "job_id": job_id,
            "status": "PASS" if not reasons else "FAIL",
            "release_eligible": not reasons,
            "forward_eligible": False,
            "live_eligible": False,
            "gates": gates,
            "reasons": reasons,
            "runtime": {"tool_version": __version__, "host": socket.gethostname()},
            "session": {
                "revision_id": session.get("revision_id"),
                "revision_sha256": session.get("revision_sha256"),
                "source_sha256": session.get("source_sha256"),
                "source_bytes": session.get("source_bytes"),
                "baseline_job_id": baseline_id,
            },
            "request": request,
            "baseline_request": baseline_request,
            "result_provenance": {
                "tool_version": result.get("tool_version"),
                "host": result.get("host"),
                "platform": result.get("platform"),
                "recorded_at_utc": result.get("recorded_at_utc"),
                "compile": {
                    "source": compile_data.get("source"),
                    "command": compile_data.get("command"),
                },
                "backtest": {
                    "source": tester.get("source"),
                    "command": tester.get("command"),
                },
            },
            "artifacts": artifacts,
            "metrics": {k: metrics.get(k) for k in _REQUIRED_METRICS},
        }

    def _persist_artifact_copies(self, evaluation: dict[str, Any], release_dir: Path) -> dict[str, Any]:
        dst_root = release_dir / "artifacts"
        dst_root.mkdir(parents=True, exist_ok=True)
        copied: dict[str, Any] = {}
        for name, rec in (evaluation.get("artifacts") or {}).items():
            src = Path(str(rec.get("path") or ""))
            if not src.is_file():
                raise FileNotFoundError(f"Release artifact missing during copy: {src}")
            suffix = src.suffix or ".bin"
            dst = dst_root / f"{name}{suffix}"
            shutil.copy2(src, dst)
            new = file_record(dst, logical_name=name)
            if new.get("sha256") != rec.get("sha256") or int(new.get("bytes") or -1) != int(rec.get("bytes") or -2):
                raise RuntimeError(f"RELEASE_ARTIFACT_COPY_HASH_MISMATCH:{name}")
            copied[name] = new
        return copied

    def check_all(self, project_id: str, job_id: str) -> dict[str, Any]:
        evaluation = self._evaluate(project_id, job_id)
        release_dir = self._release_dir(project_id, job_id)
        record = dict(evaluation)
        record["checked_at_utc"] = utc_now()
        if evaluation["status"] == "PASS":
            record["evidence_artifacts"] = self._persist_artifact_copies(evaluation, release_dir)
        path = release_dir / "check-all.json"
        _atomic_write_json(path, record)
        return {**record, "path": str(path), "sha256": sha256_file(path)}

    def _validate_saved_check(self, project_id: str, job_id: str) -> tuple[dict[str, Any], Path]:
        release_dir = self._release_dir(project_id, job_id)
        path = release_dir / "check-all.json"
        check = self._json(path)
        if check.get("status") != "PASS" or check.get("release_eligible") is not True:
            raise RuntimeError("RELEASE_CHECK_ALL_NOT_PASS")
        current = self._evaluate(project_id, job_id)
        if current.get("status") != "PASS":
            raise RuntimeError("RELEASE_EVIDENCE_NO_LONGER_VALID:" + ",".join(current.get("reasons") or []))
        for name, old in (check.get("artifacts") or {}).items():
            cur = (current.get("artifacts") or {}).get(name) or {}
            if old.get("sha256") != cur.get("sha256") or int(old.get("bytes") or -1) != int(cur.get("bytes") or -2):
                raise RuntimeError(f"RELEASE_ARTIFACT_DRIFT:{name}")
        return check, path

    def attest(self, project_id: str, job_id: str) -> dict[str, Any]:
        check, check_path = self._validate_saved_check(project_id, job_id)
        release_dir = self._release_dir(project_id, job_id)
        record = {
            "schema_version": "2.0",
            "project_id": project_id,
            "job_id": job_id,
            "status": "PASS",
            "attestation_type": "technical_hash_chain",
            "attested_at_utc": utc_now(),
            "tool_version": __version__,
            "host": socket.gethostname(),
            "check_all": {"path": str(check_path), "sha256": sha256_file(check_path)},
            "artifact_hashes": {k: v.get("sha256") for k, v in (check.get("evidence_artifacts") or {}).items()},
            "release_eligible": True,
            "forward_eligible": False,
            "live_eligible": False,
            "owner_approval": "NOT_REQUIRED_FOR_TECHNICAL_RELEASE_ELIGIBILITY",
        }
        path = release_dir / "attestation.json"
        _atomic_write_json(path, record)
        return {**record, "path": str(path), "sha256": sha256_file(path)}

    def ship(self, project_id: str, job_id: str) -> dict[str, Any]:
        check, check_path = self._validate_saved_check(project_id, job_id)
        release_dir = self._release_dir(project_id, job_id)
        attest_path = release_dir / "attestation.json"
        att = self._json(attest_path)
        if att.get("status") != "PASS" or att.get("release_eligible") is not True:
            raise RuntimeError("RELEASE_ATTESTATION_NOT_PASS")
        if (att.get("check_all") or {}).get("sha256") != sha256_file(check_path):
            raise RuntimeError("RELEASE_ATTESTATION_CHECK_HASH_MISMATCH")
        for name, expected in (att.get("artifact_hashes") or {}).items():
            rec = (check.get("evidence_artifacts") or {}).get(name) or {}
            p = Path(str(rec.get("path") or ""))
            if not p.is_file() or sha256_file(p) != expected:
                raise RuntimeError(f"RELEASE_ATTESTED_ARTIFACT_MISMATCH:{name}")

        session = self.sessions.get(project_id)
        manifest = {
            "schema_version": "2.0",
            "manifest_type": "vibemql5_release_evidence",
            "project_id": project_id,
            "job_id": job_id,
            "recorded_at_utc": utc_now(),
            "tool_version": __version__,
            "host": socket.gethostname(),
            "release_eligible": True,
            "forward_eligible": False,
            "live_eligible": False,
            "canonical": {
                "revision_id": session.get("revision_id"),
                "revision_sha256": session.get("revision_sha256"),
                "source_sha256": session.get("source_sha256"),
                "source_bytes": session.get("source_bytes"),
                "baseline_job_id": session.get("baseline_job_id"),
            },
            "check_all": {"path": str(check_path), "sha256": sha256_file(check_path)},
            "attestation": {"path": str(attest_path), "sha256": sha256_file(attest_path)},
            "artifacts": check.get("evidence_artifacts") or {},
            "metrics": check.get("metrics") or {},
            "provenance": check.get("result_provenance") or {},
            "policy": {
                "release": "PASS",
                "forward": "BLOCKED_OWNER_APPROVAL_AND_FORWARD_EVIDENCE",
                "live": "BLOCKED_OWNER_APPROVAL_AND_REAL_ENVIRONMENT_GATES",
            },
        }
        canonical = self.root / "evidence" / "manifest.json"
        manifest_candidate = release_dir / "canonical-manifest.json"
        _atomic_write_json(manifest_candidate, manifest)
        manifest_sha = sha256_file(manifest_candidate)

        ship_record = {
            "schema_version": "2.0",
            "status": "PASS",
            "project_id": project_id,
            "job_id": job_id,
            "shipped_at_utc": utc_now(),
            "release_manifest": {"path": str(canonical), "sha256": manifest_sha},
            "release_eligible": True,
            "forward_eligible": False,
            "live_eligible": False,
        }
        ship_path = release_dir / "ship.json"
        _atomic_write_json(ship_path, ship_record)

        zip_path = release_dir / f"release-evidence-{job_id}.zip"
        tmp_zip = release_dir / f".z-{uuid4().hex[:8]}.tmp"
        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for artifact_path in sorted(release_dir.rglob("*")):
                    if artifact_path.is_file() and artifact_path not in {zip_path, tmp_zip}:
                        zf.write(artifact_path, artifact_path.relative_to(release_dir))
            os.replace(tmp_zip, zip_path)
        finally:
            try:
                tmp_zip.unlink(missing_ok=True)
            except OSError:
                pass

        # The canonical release flag is the last commit point. A packaging failure
        # therefore cannot leave evidence/manifest.json claiming release_eligible=true.
        _atomic_write_bytes(canonical, manifest_candidate.read_bytes())
        if sha256_file(canonical) != manifest_sha:
            raise RuntimeError("RELEASE_CANONICAL_MANIFEST_COMMIT_HASH_MISMATCH")
        return {
            **ship_record,
            "path": str(ship_path),
            "sha256": sha256_file(ship_path),
            "package": {"path": str(zip_path), "sha256": sha256_file(zip_path), "bytes": zip_path.stat().st_size},
        }
