from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import BUILD_INPUT_MANIFEST_NAME, BUILD_OUTPUT_MANIFEST_NAME, SNAPSHOT_MANIFEST_NAME
from .workspace import WorkspaceManager
from ..errors import PathViolation

EXPORT_SCHEMA_VERSION = "1.0"
EXPORT_URI_SCHEME = "vibemql5-export"
MAX_EXPORT_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_INPUT_BYTES = 64 * 1024 * 1024

_TERMINAL_STATES = {
    "PASSED", "ANOMALY", "FAILED", "TIMEOUT", "CANCELLED", "INTERRUPTED", "RESOURCE_LIMIT"
}

_ALLOWED_SUFFIXES = {
    ".ex5", ".zip", ".json", ".md", ".txt", ".html", ".htm", ".xml", ".csv"
}
_SOURCE_SUFFIXES = {".mq5", ".mqh"}
_PARAMETER_SUFFIXES = {".set"}
_DENIED_NAME = re.compile(r"(?:^|[._-])(password|passwd|credential|credentials|secret|secrets|token|tokens|private[-_]?key|id_rsa)(?:[._-]|$)", re.I)
_JOB_ID = re.compile(r"^(?:BT|COMPILE)-[A-Za-z0-9._-]+$")
_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RAW_LOG = re.compile(r"^rawlog:([0-9a-fA-F]{16})$")
_RUNTIME_CAPTURE_ID = re.compile(r"^RTC-[A-Za-z0-9-]+$")

_JOB_TEXT_ARTIFACTS = {
    "job.json", "request.json", "environment.json", "compile.json", "result.json", "summary.md",
    "report.htm", "report.html", "report.native.xml", "report.xml",
    "phase-config.json", "phase-compile.json", "phase-handoff.json", "phase-tester.json", "phase-cleanup.json",
    BUILD_INPUT_MANIFEST_NAME, BUILD_OUTPUT_MANIFEST_NAME,
}
_JOB_IMMUTABLE = {
    "compiled.ex5", "phase-config.json", "phase-compile.json", "phase-handoff.json", "phase-tester.json", "phase-cleanup.json",
    BUILD_INPUT_MANIFEST_NAME, BUILD_OUTPUT_MANIFEST_NAME,
}

_MIME_OVERRIDES = {
    ".ex5": "application/octet-stream",
    ".zip": "application/zip",
    ".md": "text/markdown",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".xml": "application/xml",
    ".csv": "text/csv",
    ".mq5": "text/plain",
    ".mqh": "text/plain",
    ".set": "text/plain",
}

_RELEASE_EVIDENCE_NAMES = (
    "job.json", "request.json", "environment.json", "compile.log", "compile.json", "tester.log",
    "result.json", "summary.md", "report.htm", "report.html", "report.native.xml", "report.xml",
    "phase-config.json", "phase-compile.json", "phase-handoff.json", "phase-tester.json", "phase-cleanup.json",
)

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _b64url_decode(token: str) -> bytes:
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid export token")
    padded = token + "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise ValueError("Invalid export token") from exc

def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[suffix]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

def _safe_existing_file(base: Path, relative_path: str) -> Path:
    rel = Path(str(relative_path or "").replace("\\", "/"))
    if not str(relative_path or "").strip() or rel.is_absolute() or rel.drive:
        raise ValueError("Export path must be a non-empty relative path")
    if any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError("Export path traversal is not allowed")
    base_resolved = base.resolve(strict=True)
    candidate = (base_resolved / rel).resolve(strict=True)
    try:
        common = Path(os.path.commonpath([str(base_resolved), str(candidate)]))
    except ValueError as exc:
        raise ValueError("Export path escapes the allowed root") from exc
    if common != base_resolved or not candidate.is_file():
        raise ValueError("Export path escapes the allowed root")
    return candidate

def _check_name_and_size(path: Path) -> None:
    if _DENIED_NAME.search(path.name):
        raise ValueError("Sensitive-looking filename is not exportable")
    size = path.stat().st_size
    if size < 0 or size > MAX_EXPORT_BYTES:
        raise ValueError(f"Export file exceeds {MAX_EXPORT_BYTES} bytes")

def _check_exportable_path(path: Path, allowed_suffixes: set[str] | None = None) -> None:
    allowed = allowed_suffixes or _ALLOWED_SUFFIXES
    if path.suffix.lower() not in allowed:
        raise ValueError(f"File type is not exportable: {path.suffix or '<none>'}")
    _check_name_and_size(path)

def _json_load(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(code) from exc
    if not isinstance(value, dict):
        raise ValueError(code)
    return value

def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info

@dataclass(frozen=True)
class ExportDescriptor:
    scope: str
    source_id: str
    logical_name: str
    file_name: str
    path: Path
    bytes: int
    sha256: str
    mime_type: str
    uri: str
    complete: bool
    source_relation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "scope": self.scope,
            "source_id": self.source_id,
            "logical_name": self.logical_name,
            "file_name": self.file_name,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "mime_type": self.mime_type,
            "uri": self.uri,
            "complete": self.complete,
            "delivery": "mcp_resource_link",
            "max_export_bytes": MAX_EXPORT_BYTES,
            "source_relation": self.source_relation,
        }

class FileExportManager:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.workspace = WorkspaceManager(self.root)

    def _run_dir(self, operation_id: str) -> Path:
        if not _JOB_ID.fullmatch(str(operation_id or "")):
            raise ValueError("Invalid job id")
        run_dir = self.root / "runs" / operation_id
        if not run_dir.is_dir():
            raise ValueError("Unknown job id")
        return run_dir

    def _run_state(self, operation_id: str) -> tuple[str, bool]:
        run_dir = self._run_dir(operation_id)
        job_file = run_dir / "job.json"
        if job_file.is_file():
            job = _json_load(job_file, "Invalid job record")
            state = str(job.get("state") or "")
            return state, state in _TERMINAL_STATES
        if operation_id.startswith("COMPILE-"):
            output = run_dir / BUILD_OUTPUT_MANIFEST_NAME
            if output.is_file():
                record = _json_load(output, "Invalid build output manifest")
                status = str((record.get("compile") or {}).get("status") or "")
                return status, status in {"PASSED", "FAILED"}
        raise ValueError("Unknown job id")

    def _job_artifact(self, job_id: str, name: str) -> tuple[Path, bool, str]:
        run_dir = self._run_dir(job_id)
        state, terminal = self._run_state(job_id)
        if name == "compiled.ex5":
            path = run_dir / "compiled.ex5"
        elif name in _JOB_TEXT_ARTIFACTS:
            path = run_dir / name
        else:
            raw = _RAW_LOG.fullmatch(str(name or ""))
            if not raw:
                raise ValueError("Job artifact is not exportable")
            raise ValueError("Raw tester logs are not exportable")
        if not path.is_file():
            raise ValueError("Export source file is missing")
        _check_exportable_path(path)
        complete = name in _JOB_IMMUTABLE or terminal
        if not complete:
            raise ValueError("Job artifact is not complete yet")
        return path, True, "job_scoped_run_artifact"

    def _scoped_file(self, scope: str, relative_path: str) -> tuple[Path, bool, str]:
        bases = {"evidence": self.root / "evidence", "exports": self.root / "exports"}
        if scope not in bases:
            raise ValueError("Unsupported export scope")
        base = bases[scope]
        if not base.is_dir():
            raise ValueError(f"Export scope root is missing: {scope}")
        path = _safe_existing_file(base, relative_path)
        _check_exportable_path(path)
        return path, True, f"{scope}_scoped_file"

    def _workspace_file(self, workspace: str, name: str, *, parameter: bool) -> tuple[Path, bool, str]:
        if not _WORKSPACE_ID.fullmatch(str(workspace or "")):
            raise ValueError("Invalid workspace id")
        try:
            path = self.workspace.resolve(workspace, name, must_exist=True)
        except PathViolation as exc:
            raise ValueError("Export path escapes the allowed workspace root") from exc
        _check_exportable_path(path, _PARAMETER_SUFFIXES if parameter else _SOURCE_SUFFIXES)
        return path, True, "current_workspace_nonhistorical"

    def _load_snapshot_authority(self, job_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        run_dir = self._run_dir(job_id)
        input_path = run_dir / BUILD_INPUT_MANIFEST_NAME
        snapshot = run_dir / "source_snapshot"
        marker = snapshot / SNAPSHOT_MANIFEST_NAME
        if not input_path.is_file() or not marker.is_file():
            raise ValueError("Immutable build input snapshot is unavailable")
        build_input = _json_load(input_path, "Invalid build input manifest")
        snap_manifest = _json_load(marker, "Invalid source snapshot manifest")
        entries = snap_manifest.get("files") or []
        if not isinstance(entries, list):
            raise ValueError("Invalid source snapshot manifest")
        canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        catalog = _sha256_bytes(canonical)
        declared = (build_input.get("source_snapshot") or {}).get("catalog_sha256")
        if catalog != snap_manifest.get("catalog_sha256") or catalog != declared:
            raise ValueError("Immutable source snapshot catalog mismatch")
        entry_map = self._entry_map(snap_manifest)
        ea_path = str(build_input.get("ea_path") or "")
        main_source = build_input.get("main_source")
        if not ea_path or not isinstance(main_source, dict) or entry_map.get(ea_path) != main_source:
            raise ValueError("Build input main source is not bound to immutable snapshot")
        dependencies = build_input.get("source_dependencies") or []
        if not isinstance(dependencies, list):
            raise ValueError("Build input source dependency list is invalid")
        seen_dependencies: set[str] = set()
        for dep in dependencies:
            if not isinstance(dep, dict) or not dep.get("path"):
                raise ValueError("Build input source dependency is invalid")
            rel = str(dep.get("path"))
            if rel in seen_dependencies or Path(rel).suffix.lower() != ".mqh" or entry_map.get(rel) != dep:
                raise ValueError("Build input source dependency is not bound to immutable snapshot")
            seen_dependencies.add(rel)
        selected = build_input.get("parameter_set")
        if selected is not None:
            if not isinstance(selected, dict) or not selected.get("path") or entry_map.get(str(selected.get("path"))) != selected:
                raise ValueError("Build input parameter set is not bound to immutable snapshot")
        return snapshot, build_input, snap_manifest

    @staticmethod
    def _entry_map(snapshot_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(x.get("path") or ""): dict(x) for x in snapshot_manifest.get("files") or [] if isinstance(x, dict)}

    def _immutable_job_source(self, job_id: str, name: str) -> tuple[Path, bool, str]:
        _, terminal = self._run_state(job_id)
        if terminal:
            self._validate_build_output(job_id)
        snapshot, build_input, manifest = self._load_snapshot_authority(job_id)
        path = _safe_existing_file(snapshot, name)
        _check_exportable_path(path, _SOURCE_SUFFIXES)
        rel = path.relative_to(snapshot.resolve(strict=True)).as_posix()
        allowed = {str(build_input.get("ea_path") or "")} | {str(x.get("path") or "") for x in (build_input.get("source_dependencies") or []) if isinstance(x, dict)}
        if rel not in allowed:
            raise ValueError("Requested source is not bound to the job build dependency closure")
        entry = self._entry_map(manifest).get(rel)
        raw = path.read_bytes()
        if not entry or int(entry.get("bytes") or -1) != len(raw) or str(entry.get("sha256") or "") != _sha256_bytes(raw):
            raise ValueError("Immutable job source snapshot integrity mismatch")
        return path, True, "immutable_job_source_snapshot"

    def _immutable_job_parameter_set(self, job_id: str, name: str) -> tuple[Path, bool, str]:
        _, terminal = self._run_state(job_id)
        if terminal:
            self._validate_build_output(job_id)
        snapshot, build_input, manifest = self._load_snapshot_authority(job_id)
        selected = build_input.get("parameter_set")
        if not isinstance(selected, dict) or not selected.get("path"):
            raise ValueError("Job has no bound parameter set")
        selected_name = str(selected["path"])
        if name and str(name).replace("\\", "/") != selected_name:
            raise ValueError("Requested parameter set is not the job-bound parameter set")
        path = _safe_existing_file(snapshot, selected_name)
        _check_exportable_path(path, _PARAMETER_SUFFIXES)
        entry = self._entry_map(manifest).get(selected_name)
        raw = path.read_bytes()
        if not entry or entry != selected or int(entry.get("bytes") or -1) != len(raw) or str(entry.get("sha256") or "") != _sha256_bytes(raw):
            raise ValueError("Immutable job parameter-set integrity mismatch")
        return path, True, "immutable_job_parameter_set_snapshot"

    def _validate_build_output(self, job_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        run_dir = self._run_dir(job_id)
        input_path = run_dir / BUILD_INPUT_MANIFEST_NAME
        output_path = run_dir / BUILD_OUTPUT_MANIFEST_NAME
        if not input_path.is_file() or not output_path.is_file():
            raise ValueError("Build provenance manifests are incomplete")
        build_input = _json_load(input_path, "Invalid build input manifest")
        build_output = _json_load(output_path, "Invalid build output manifest")
        input_raw = input_path.read_bytes()
        declared_input = build_output.get("input_manifest") or {}
        if declared_input.get("sha256") != _sha256_bytes(input_raw) or int(declared_input.get("bytes") or -1) != len(input_raw):
            raise ValueError("Build output is not bound to the immutable input manifest")
        if str((build_output.get("compile") or {}).get("status") or "") != "PASSED":
            raise ValueError("Release bundle requires a successful compile")
        ex5 = run_dir / "compiled.ex5"
        meta = build_output.get("compiled_ex5") or {}
        if not ex5.is_file():
            raise ValueError("Compiled EX5 is missing")
        raw = ex5.read_bytes()
        if not meta.get("exists") or int(meta.get("bytes") or -1) != len(raw) or meta.get("sha256") != _sha256_bytes(raw):
            raise ValueError("Compiled EX5 does not match build provenance")
        return run_dir, build_input, build_output

    def _release_bundle_path(self, job_id: str) -> Path:
        return self.root / "exports" / "releases" / job_id / f"VibeMQL5-{job_id}-release.zip"

    def _validate_release_bundle(self, bundle: Path, job_id: str, run_dir: Path, build_input: dict[str, Any], build_output: dict[str, Any]) -> None:
        _check_exportable_path(bundle)
        try:
            with zipfile.ZipFile(bundle, "r") as zf:
                names = zf.namelist()
                if len(names) != len(set(names)) or "MANIFEST.json" not in names or "SHA256SUMS.txt" not in names:
                    raise ValueError("Release bundle structure is invalid")
                manifest_raw = zf.read("MANIFEST.json")
                manifest = json.loads(manifest_raw.decode("utf-8"))
                if not isinstance(manifest, dict) or manifest.get("kind") != "VIBEMQL5_RELEASE_BUNDLE" or manifest.get("operation_id") != job_id:
                    raise ValueError("Release bundle manifest identity mismatch")
                input_sha = _sha256_bytes((run_dir / BUILD_INPUT_MANIFEST_NAME).read_bytes())
                output_sha = _sha256_bytes((run_dir / BUILD_OUTPUT_MANIFEST_NAME).read_bytes())
                if manifest.get("build_input_manifest_sha256") != input_sha or manifest.get("build_output_manifest_sha256") != output_sha:
                    raise ValueError("Release bundle provenance hash mismatch")
                if manifest.get("source_snapshot_catalog_sha256") != (build_input.get("source_snapshot") or {}).get("catalog_sha256"):
                    raise ValueError("Release bundle source catalog mismatch")
                if manifest.get("compiled_ex5_sha256") != (build_output.get("compiled_ex5") or {}).get("sha256"):
                    raise ValueError("Release bundle EX5 provenance mismatch")
                declared = manifest.get("files")
                if not isinstance(declared, list):
                    raise ValueError("Release bundle file manifest is invalid")
                declared_names: set[str] = set()
                for item in declared:
                    if not isinstance(item, dict) or not item.get("path"):
                        raise ValueError("Release bundle file manifest is invalid")
                    name = str(item["path"])
                    if name in declared_names or name not in names or name in {"MANIFEST.json", "SHA256SUMS.txt"}:
                        raise ValueError("Release bundle file manifest is invalid")
                    raw = zf.read(name)
                    if len(raw) != int(item.get("bytes") or -1) or _sha256_bytes(raw) != str(item.get("sha256") or ""):
                        raise ValueError("Release bundle payload hash mismatch")
                    declared_names.add(name)
                if declared_names != (set(names) - {"MANIFEST.json", "SHA256SUMS.txt"}):
                    raise ValueError("Release bundle contains undeclared payloads")
                expected_sums = "".join(f"{_sha256_bytes(zf.read(name))}  {name}\n" for name in sorted(declared_names | {"MANIFEST.json"})).encode("utf-8")
                if zf.read("SHA256SUMS.txt") != expected_sums:
                    raise ValueError("Release bundle SHA256SUMS mismatch")
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Release bundle integrity validation failed") from exc

    def _build_release_bundle(self, job_id: str) -> Path:
        _, terminal = self._run_state(job_id)
        if not terminal:
            raise ValueError("Release bundle requires a completed run")
        run_dir, build_input, build_output = self._validate_build_output(job_id)
        snapshot, _, snap_manifest = self._load_snapshot_authority(job_id)
        bundle = self._release_bundle_path(job_id)
        if bundle.is_file():
            self._validate_release_bundle(bundle, job_id, run_dir, build_input, build_output)
            return bundle
        payloads: dict[str, bytes] = {}
        entry_map = self._entry_map(snap_manifest)
        source_paths = [str(build_input.get("ea_path") or "")] + [str(x.get("path") or "") for x in (build_input.get("source_dependencies") or []) if isinstance(x, dict)]
        if not source_paths[0]:
            raise ValueError("Release bundle main source binding is missing")
        for rel in source_paths:
            entry = entry_map.get(rel)
            if not entry or Path(rel).suffix.lower() not in _SOURCE_SUFFIXES:
                raise ValueError("Release bundle source dependency is not bound to snapshot")
            path = _safe_existing_file(snapshot, rel)
            raw = path.read_bytes()
            if len(raw) != int(entry.get("bytes") or -1) or _sha256_bytes(raw) != entry.get("sha256"):
                raise ValueError("Immutable source snapshot changed before bundle creation")
            payloads[f"Source/{rel}"] = raw
        selected = build_input.get("parameter_set")
        if isinstance(selected, dict) and selected.get("path"):
            rel = str(selected["path"])
            path = _safe_existing_file(snapshot, rel)
            raw = path.read_bytes()
            if len(raw) != int(selected.get("bytes") or -1) or _sha256_bytes(raw) != selected.get("sha256"):
                raise ValueError("Immutable parameter set changed before bundle creation")
            payloads[f"Sets/{rel[5:] if rel.lower().startswith('sets/') else rel}"] = raw
        ex5 = run_dir / "compiled.ex5"
        payloads[f"Bin/{Path(str(build_input.get('ea_path') or 'EA.mq5')).stem}.ex5"] = ex5.read_bytes()
        payloads[f"Evidence/{BUILD_INPUT_MANIFEST_NAME}"] = (run_dir / BUILD_INPUT_MANIFEST_NAME).read_bytes()
        payloads[f"Evidence/{BUILD_OUTPUT_MANIFEST_NAME}"] = (run_dir / BUILD_OUTPUT_MANIFEST_NAME).read_bytes()
        for name in _RELEASE_EVIDENCE_NAMES:
            path = run_dir / name
            if path.is_file():
                raw = path.read_bytes()
                if len(raw) <= MAX_EXPORT_BYTES:
                    payloads[f"Evidence/{name}"] = raw
        total = sum(len(raw) for raw in payloads.values())
        if total > MAX_BUNDLE_INPUT_BYTES:
            raise ValueError(f"Release bundle inputs exceed {MAX_BUNDLE_INPUT_BYTES} bytes")
        manifest_files = [{"path": name, "bytes": len(raw), "sha256": _sha256_bytes(raw)} for name, raw in sorted(payloads.items())]
        release_manifest = {
            "schema_version": "1.0",
            "kind": "VIBEMQL5_RELEASE_BUNDLE",
            "operation_id": job_id,
            "workspace": build_input.get("workspace"),
            "ea_path": build_input.get("ea_path"),
            "source_snapshot_catalog_sha256": (build_input.get("source_snapshot") or {}).get("catalog_sha256"),
            "source_dependency_count": len(build_input.get("source_dependencies") or []),
            "unresolved_includes": build_input.get("unresolved_includes") or [],
            "build_input_manifest_sha256": _sha256_bytes((run_dir / BUILD_INPUT_MANIFEST_NAME).read_bytes()),
            "build_output_manifest_sha256": _sha256_bytes((run_dir / BUILD_OUTPUT_MANIFEST_NAME).read_bytes()),
            "compiled_ex5_sha256": (build_output.get("compiled_ex5") or {}).get("sha256"),
            "files": manifest_files,
        }
        manifest_raw = (json.dumps(release_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        payloads["MANIFEST.json"] = manifest_raw
        sums = "".join(f"{_sha256_bytes(raw)}  {name}\n" for name, raw in sorted(payloads.items()))
        payloads["SHA256SUMS.txt"] = sums.encode("utf-8")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".tip025-release-", suffix=".zip.tmp", dir=str(bundle.parent))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                for name, raw in sorted(payloads.items()):
                    zf.writestr(_zip_info(name), raw)
            if tmp.stat().st_size > MAX_EXPORT_BYTES:
                raise ValueError(f"Export file exceeds {MAX_EXPORT_BYTES} bytes")
            try:
                os.replace(tmp, bundle)
            except FileExistsError:
                tmp.unlink(missing_ok=True)
            self._validate_release_bundle(bundle, job_id, run_dir, build_input, build_output)
            return bundle
        finally:
            tmp.unlink(missing_ok=True)

    def _runtime_capture_artifact(self, capture_id: str, name: str) -> tuple[Path, bool, str]:
        if not _RUNTIME_CAPTURE_ID.fullmatch(str(capture_id or "")):
            raise ValueError("Invalid runtime capture id")
        base = self.root / "evidence" / "runtime" / capture_id
        if not base.is_dir():
            raise ValueError("Runtime capture is missing")
        logical = str(name or "capture-manifest.json").replace("\\", "/")
        path = _safe_existing_file(base, logical)
        _check_exportable_path(path, {".json", ".jsonl", ".txt"})
        manifest = _json_load(base / "capture-manifest.json", "Invalid runtime capture manifest")
        complete = bool(manifest.get("complete") is True and manifest.get("capture_id") == capture_id)
        if not complete:
            raise ValueError("Runtime capture is incomplete")
        return path, True, "immutable_runtime_capture"

    def _resolve(self, scope: str, source_id: str, name: str, *, for_prepare: bool) -> tuple[Path, bool, str, str, str]:
        if scope == "runtime_capture":
            path, complete, relation = self._runtime_capture_artifact(source_id, name)
            logical = str(name or "capture-manifest.json").replace("\\", "/")
            return path, complete, relation, source_id, logical
        if scope == "job":
            path, complete, relation = self._job_artifact(source_id, name)
            return path, complete, relation, source_id, name
        if scope == "job_source":
            path, complete, relation = self._immutable_job_source(source_id, name)
            return path, complete, relation, source_id, name.replace("\\", "/")
        if scope == "job_parameter_set":
            path, complete, relation = self._immutable_job_parameter_set(source_id, name)
            build_input = _json_load(self._run_dir(source_id) / BUILD_INPUT_MANIFEST_NAME, "Invalid build input manifest")
            logical = str(name or "") or str(((build_input.get("parameter_set") or {}).get("path")) or "")
            return path, complete, relation, source_id, logical.replace("\\", "/")
        if scope == "workspace_source":
            path, complete, relation = self._workspace_file(source_id, name, parameter=False)
            return path, complete, relation, source_id, name.replace("\\", "/")
        if scope == "parameter_set":
            path, complete, relation = self._workspace_file(source_id, name, parameter=True)
            return path, complete, relation, source_id, name.replace("\\", "/")
        if scope == "release_bundle":
            if name not in ("", f"VibeMQL5-{source_id}-release.zip"):
                raise ValueError("Release bundle name is server-defined")
            path = self._build_release_bundle(source_id) if for_prepare else self._release_bundle_path(source_id)
            if not path.is_file():
                raise ValueError("Release bundle is missing")
            _check_exportable_path(path)
            return path, True, "immutable_release_bundle", source_id, path.name
        path, complete, relation = self._scoped_file(scope, source_id)
        logical = source_id.replace("\\", "/")
        return path, complete, relation, logical, logical

    def prepare(self, scope: str, source_id: str, name: str = "", expected_sha256: str = "") -> dict[str, Any]:
        scope = str(scope or "").strip().lower()
        path, complete, relation, source_key, logical_name = self._resolve(scope, source_id, name, for_prepare=True)
        raw = path.read_bytes()
        digest = _sha256_bytes(raw)
        if expected_sha256 and str(expected_sha256).lower() != digest:
            raise ValueError("Export SHA-256 precondition mismatch")
        payload = {"v": EXPORT_SCHEMA_VERSION, "scope": scope, "source_id": source_key, "name": logical_name, "bytes": len(raw), "sha256": digest}
        token = _b64url_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        uri = f"{EXPORT_URI_SCHEME}://artifact/{token}"
        return ExportDescriptor(scope=scope, source_id=source_key, logical_name=logical_name, file_name=path.name, path=path, bytes=len(raw), sha256=digest, mime_type=_mime_for(path), uri=uri, complete=complete, source_relation=relation).to_dict()

    def read_token(self, token: str) -> tuple[bytes, dict[str, Any]]:
        try:
            payload = json.loads(_b64url_decode(token).decode("utf-8"))
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError("Invalid export token") from exc
        if not isinstance(payload, dict) or payload.get("v") != EXPORT_SCHEMA_VERSION:
            raise ValueError("Unsupported export token version")
        scope = str(payload.get("scope") or "")
        source_id = str(payload.get("source_id") or "")
        logical_name = str(payload.get("name") or "")
        expected_bytes = int(payload.get("bytes") or -1)
        expected_sha = str(payload.get("sha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError("Invalid export token SHA-256")
        path, complete, relation, _, _ = self._resolve(scope, source_id, logical_name, for_prepare=False)
        raw = path.read_bytes()
        actual_sha = _sha256_bytes(raw)
        if len(raw) != expected_bytes or actual_sha != expected_sha:
            raise ValueError("Export resource changed after link creation")
        return raw, {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "scope": scope,
            "source_id": source_id,
            "logical_name": logical_name,
            "file_name": path.name,
            "bytes": len(raw),
            "sha256": actual_sha,
            "mime_type": _mime_for(path),
            "complete": complete,
            "source_relation": relation,
        }
