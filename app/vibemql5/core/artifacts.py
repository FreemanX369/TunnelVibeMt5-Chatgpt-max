from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from ..config import load_settings, default_root

SNAPSHOT_MANIFEST_NAME = ".vibemql5-snapshot-manifest.json"
BUILD_INPUT_MANIFEST_NAME = "build-input-manifest.json"
BUILD_OUTPUT_MANIFEST_NAME = "build-output-manifest.json"


class ArtifactManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.runs = self.root / "runs"
        self.runs.mkdir(parents=True, exist_ok=True)

    def run_dir(self, job_id: str) -> Path:
        if not job_id or any(x in job_id for x in ("/", "\\", "..")):
            raise ValueError("Invalid job id")
        p = self.runs / job_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def _json_bytes(data: Any) -> bytes:
        return (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".v-{uuid.uuid4().hex[:8]}.tmp")
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

    def write_json(self, job_id: str, name: str, data: dict) -> Path:
        p = self.run_dir(job_id) / name
        self._atomic_write(p, self._json_bytes(data))
        return p

    def write_json_immutable(self, job_id: str, name: str, data: dict) -> Path:
        """Publish one immutable JSON record atomically; identical retries converge.

        The complete bytes are fsynced to a same-directory temporary file first.
        ``os.link(tmp, final)`` then publishes them with exclusive-create semantics:
        it never replaces an existing final path, so divergent racing writers cannot
        overwrite each other and readers never observe a partially-written record.
        """
        if not name or Path(name).name != name or not name.lower().endswith(".json"):
            raise ValueError("Immutable JSON name must be a simple .json filename")
        path = self.run_dir(job_id) / name
        raw = self._json_bytes(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != raw:
                raise RuntimeError(f"IMMUTABLE_ARTIFACT_CONFLICT: {name}")
            return path
        tmp = path.with_name(f".v-{uuid.uuid4().hex[:8]}.immutable.tmp")
        try:
            with tmp.open("xb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise RuntimeError(f"IMMUTABLE_ARTIFACT_CONFLICT: {name}")
            return path
        finally:
            tmp.unlink(missing_ok=True)

    def write_phase_receipt(self, job_id: str, phase: str, data: dict) -> Path:
        """Write-once durable phase evidence.

        A repeated identical write is idempotent. A divergent rewrite is rejected so
        a later failure cannot downgrade an earlier PASS receipt.
        """
        safe = str(phase).strip().lower().replace("_", "-")
        if not safe or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in safe):
            raise ValueError("Invalid phase receipt name")
        path = self.run_dir(job_id) / f"phase-{safe}.json"
        raw = self._json_bytes(data)
        if path.exists():
            existing = path.read_bytes()
            if existing != raw:
                raise RuntimeError(f"PHASE_RECEIPT_IMMUTABLE_CONFLICT: {phase}")
            return path
        self._atomic_write(path, raw)
        return path

    def read_phase_receipt(self, job_id: str, phase: str) -> dict | None:
        safe = str(phase).strip().lower().replace("_", "-")
        path = self.run_dir(job_id) / f"phase-{safe}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def file_metadata(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"exists": False, "bytes": 0, "sha256": None}
        raw = path.read_bytes()
        return {
            "exists": True,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    @staticmethod
    def _tree_inventory(root: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not root.is_dir():
            return entries
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix().lower()):
            if not path.is_file() or path.name == SNAPSHOT_MANIFEST_NAME:
                continue
            rel = path.relative_to(root).as_posix()
            raw = path.read_bytes()
            entries.append({"path": rel, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        return entries

    @staticmethod
    def _inventory_catalog_sha256(entries: list[dict[str, Any]]) -> str:
        canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _snapshot_manifest(self, snapshot_root: Path) -> dict[str, Any]:
        marker = snapshot_root / SNAPSHOT_MANIFEST_NAME
        if not marker.is_file():
            raise RuntimeError("SOURCE_SNAPSHOT_MANIFEST_MISSING")
        try:
            manifest = json.loads(marker.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("SOURCE_SNAPSHOT_MANIFEST_INVALID") from exc
        entries = self._tree_inventory(snapshot_root)
        actual_catalog = self._inventory_catalog_sha256(entries)
        if entries != manifest.get("files") or actual_catalog != manifest.get("catalog_sha256"):
            raise RuntimeError("SOURCE_SNAPSHOT_INTEGRITY_MISMATCH")
        return manifest

    def snapshot_source(self, job_id: str, workspace_root: Path) -> Path:
        """Capture a byte-exact workspace snapshot exactly once.

        The old implementation deleted and recopied an existing snapshot, which could
        silently bind a historical job to a newer mutable workspace revision. TIP-025
        makes the directory write-once. Re-entry validates the embedded manifest and
        returns the original snapshot without consulting current workspace bytes.
        """
        run = self.run_dir(job_id)
        dst = run / "source_snapshot"
        if dst.exists():
            self._snapshot_manifest(dst)
            return dst
        workspace_root = Path(workspace_root).resolve(strict=True)
        if not workspace_root.is_dir():
            raise ValueError("Workspace root is missing")
        tmp = run / f".source_snapshot.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copytree(
                workspace_root,
                tmp,
                ignore=shutil.ignore_patterns("Baselines", SNAPSHOT_MANIFEST_NAME),
            )
            entries = self._tree_inventory(tmp)
            manifest = {
                "schema_version": "1.0",
                "kind": "VIBEMQL5_IMMUTABLE_WORKSPACE_SNAPSHOT",
                "files": entries,
                "file_count": len(entries),
                "total_bytes": sum(int(x["bytes"]) for x in entries),
                "catalog_sha256": self._inventory_catalog_sha256(entries),
            }
            self._atomic_write(tmp / SNAPSHOT_MANIFEST_NAME, self._json_bytes(manifest))
            try:
                os.replace(tmp, dst)
            except OSError:
                if dst.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
                    self._snapshot_manifest(dst)
                    return dst
                raise
            self._snapshot_manifest(dst)
            return dst
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _normalize_rel(relative_path: str) -> str:
        raw = str(relative_path or "").replace("\\", "/").strip()
        rel = Path(raw)
        if not raw or rel.is_absolute() or rel.drive or any(part in {"", ".", ".."} for part in rel.parts):
            raise ValueError("Build input path must be a safe relative path")
        return rel.as_posix()

    def _snapshot_entry(self, snapshot: Path, relative_path: str) -> dict[str, Any]:
        rel = self._normalize_rel(relative_path)
        manifest = self._snapshot_manifest(snapshot)
        by_path = {str(x.get("path") or ""): x for x in manifest.get("files") or []}
        if rel not in by_path:
            raise ValueError(f"Build input was not captured in immutable snapshot: {rel}")
        return dict(by_path[rel])

    @staticmethod
    def _decode_include_text(raw: bytes) -> str:
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig")
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            return raw.decode("utf-16")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")

    def _source_dependency_closure(
        self,
        snapshot: Path,
        snapshot_manifest: dict[str, Any],
        workspace: str,
        ea_path: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Resolve workspace-owned #include dependencies without exporting unrelated files."""
        entries = {str(x.get("path") or ""): dict(x) for x in snapshot_manifest.get("files") or []}
        include_re = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', re.I | re.M)
        queue = [self._normalize_rel(ea_path)]
        visited: set[str] = set()
        deps: dict[str, dict[str, Any]] = {}
        unresolved: list[dict[str, str]] = []
        prefix = f"vibemql5/{workspace}/".lower()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            path = snapshot / Path(current)
            if not path.is_file():
                raise RuntimeError(f"SOURCE_DEPENDENCY_SOURCE_MISSING: {current}")
            text = self._decode_include_text(path.read_bytes())
            for match in include_re.finditer(text):
                opener, raw_token = match.group(1), match.group(2).strip()
                token = raw_token.replace("\\", "/").strip()
                candidates: list[str] = []
                lower = token.lower()
                if lower.startswith(prefix):
                    rest = token[len(f"VibeMQL5/{workspace}/"):]
                    if rest:
                        candidates.append(f"Include/{rest}")
                if opener == '"':
                    parent = Path(current).parent
                    candidates.append((parent / Path(token)).as_posix())
                candidates.append(f"Include/{token}")

                resolved = None
                for candidate in candidates:
                    try:
                        safe = self._normalize_rel(candidate)
                    except ValueError:
                        continue
                    if safe in entries and Path(safe).suffix.lower() == ".mqh":
                        resolved = safe
                        break
                if resolved is None:
                    unresolved.append({"from": current, "include": raw_token})
                    continue
                if resolved not in deps:
                    deps[resolved] = entries[resolved]
                    queue.append(resolved)
        return [deps[k] for k in sorted(deps)], unresolved

    def capture_build_inputs(
        self,
        job_id: str,
        workspace: str,
        workspace_root: Path,
        ea_path: str,
        set_file: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.snapshot_source(job_id, workspace_root)
        snapshot_manifest = self._snapshot_manifest(snapshot)
        source_entry = self._snapshot_entry(snapshot, ea_path)
        parameter_entry = self._snapshot_entry(snapshot, set_file) if str(set_file or "").strip() else None
        dependencies, unresolved_includes = self._source_dependency_closure(
            snapshot, snapshot_manifest, str(workspace), ea_path
        )
        record = {
            "schema_version": "1.0",
            "kind": "VIBEMQL5_BUILD_INPUTS",
            "build_input_source": "COMPILED_SOURCE",
            "operation_id": job_id,
            "workspace": str(workspace),
            "ea_path": self._normalize_rel(ea_path),
            "source_snapshot": {
                "logical_root": "source_snapshot",
                "manifest_name": SNAPSHOT_MANIFEST_NAME,
                "catalog_sha256": snapshot_manifest["catalog_sha256"],
                "file_count": snapshot_manifest["file_count"],
                "total_bytes": snapshot_manifest["total_bytes"],
            },
            "main_source": source_entry,
            "source_dependencies": dependencies,
            "unresolved_includes": unresolved_includes,
            "parameter_set": parameter_entry,
        }
        path = self.write_json_immutable(job_id, BUILD_INPUT_MANIFEST_NAME, record)
        return {**record, "manifest_sha256": self.file_metadata(path)["sha256"]}

    def capture_imported_build_inputs(
        self,
        job_id: str,
        workspace: str,
        workspace_root: Path,
        ea_path: str,
        binding: dict[str, Any],
        immutable_ex5: dict[str, Any],
        set_file: str | None = None,
        ingress_provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.snapshot_source(job_id, workspace_root)
        snapshot_manifest = self._snapshot_manifest(snapshot)
        try:
            workspace_binary_entry = self._snapshot_entry(snapshot, ea_path)
        except ValueError:
            workspace_binary_entry = None
        parameter_entry = self._snapshot_entry(snapshot, set_file) if str(set_file or "").strip() else None
        expected_sha = str(binding.get("sha256") or "")
        expected_bytes = int(binding.get("bytes") or 0)
        workspace_binary_conformance = "MISSING"
        if workspace_binary_entry is not None:
            workspace_binary_conformance = (
                "MATCH" if workspace_binary_entry.get("sha256") == expected_sha
                and int(workspace_binary_entry.get("bytes") or 0) == expected_bytes else "DIVERGED"
            )
        if immutable_ex5.get("sha256") != expected_sha or int(immutable_ex5.get("bytes") or 0) != expected_bytes:
            raise RuntimeError("IMPORTED_EX5_JOB_CAPTURE_MISMATCH")
        record = {
            "schema_version": "1.0",
            "kind": "VIBEMQL5_BUILD_INPUTS",
            "build_input_source": "IMPORTED_EX5",
            "operation_id": job_id,
            "workspace": str(workspace),
            "ea_path": self._normalize_rel(ea_path),
            "source_snapshot": {
                "logical_root": "source_snapshot",
                "manifest_name": SNAPSHOT_MANIFEST_NAME,
                "catalog_sha256": snapshot_manifest["catalog_sha256"],
                "file_count": snapshot_manifest["file_count"],
                "total_bytes": snapshot_manifest["total_bytes"],
            },
            "main_source": None,
            "source_dependencies": [],
            "unresolved_includes": [],
            "parameter_set": parameter_entry,
            "workspace_binary": workspace_binary_entry,
            "workspace_binary_conformance": workspace_binary_conformance,
            "imported_ex5": {
                "input_type": "IMPORTED_EX5",
                "source": (ingress_provenance or {}).get("source") or "CONTROLLED_EX5_IMPORT",
                "ingress_provenance": dict(ingress_provenance or {}),
                "logical_path": self._normalize_rel(ea_path),
                "sha256": expected_sha,
                "bytes": expected_bytes,
                "immutable_object_id": binding.get("object_id"),
                "ea_binary_ref": binding.get("ea_binary_ref"),
                "snapshot_id": binding.get("snapshot_id"),
                "job_artifact": {
                    "path": "compiled.ex5",
                    "sha256": immutable_ex5.get("sha256"),
                    "bytes": immutable_ex5.get("bytes"),
                },
            },
        }
        path = self.write_json_immutable(job_id, BUILD_INPUT_MANIFEST_NAME, record)
        return {**record, "manifest_sha256": self.file_metadata(path)["sha256"]}

    def write_build_output_manifest(self, job_id: str, compile_result: dict[str, Any]) -> dict[str, Any]:
        input_path = self.run_dir(job_id) / BUILD_INPUT_MANIFEST_NAME
        if not input_path.is_file():
            raise RuntimeError("BUILD_INPUT_MANIFEST_MISSING")
        input_meta = self.file_metadata(input_path)
        ex5 = self.run_dir(job_id) / "compiled.ex5"
        ex5_meta = self.file_metadata(ex5)
        if not ex5_meta["exists"]:
            ex5_meta = {"exists": False, "bytes": 0, "sha256": None}
        record = {
            "schema_version": "1.0",
            "kind": "VIBEMQL5_BUILD_OUTPUTS",
            "operation_id": job_id,
            "input_manifest": {
                "name": BUILD_INPUT_MANIFEST_NAME,
                "bytes": input_meta["bytes"],
                "sha256": input_meta["sha256"],
            },
            "compile": {
                "status": str(compile_result.get("status") or "UNKNOWN"),
                "errors": int(compile_result.get("errors") or 0),
                "warnings": int(compile_result.get("warnings") or 0),
                "source": compile_result.get("source"),
                "expert_name": compile_result.get("expert_name"),
            },
            "compiled_ex5": ex5_meta,
        }
        path = self.write_json_immutable(job_id, BUILD_OUTPUT_MANIFEST_NAME, record)
        return {**record, "manifest_sha256": self.file_metadata(path)["sha256"]}

    def retain(self) -> dict:
        keep = int(load_settings(self.root)["retention"].get("completed_jobs", 20))
        dirs = [p for p in self.runs.iterdir() if p.is_dir()]
        completed = []
        for p in dirs:
            jobf = p / "job.json"
            if not jobf.exists():
                continue
            try:
                j = json.loads(jobf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if j.get("pinned") or j.get("state") not in {"PASSED","ANOMALY","FAILED","TIMEOUT","CANCELLED","INTERRUPTED","RESOURCE_LIMIT"}:
                continue
            completed.append((j.get("updated_at", ""), p))
        completed.sort(reverse=True)
        removed = []
        for _, p in completed[keep:]:
            shutil.rmtree(p, ignore_errors=True)
            removed.append(p.name)
        return {"kept": min(len(completed), keep), "removed": removed}
