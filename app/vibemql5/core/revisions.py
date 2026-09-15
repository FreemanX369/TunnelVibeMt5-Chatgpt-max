from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workspace import WorkspaceManager

_CHECKPOINT_RE = re.compile(r"^CP-[0-9]{8}-[0-9]{6}-[A-F0-9]{12}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.vibemql5-{uuid.uuid4().hex}.tmp")
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


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    _atomic_write_bytes(path, data)


class RevisionManager:
    """Persistent, workspace-scoped source checkpoints.

    Checkpoints are stored outside user workspaces under ``state/checkpoints`` and
    contain the exact source bytes plus immutable metadata. Restore is byte-for-byte
    and verified by SHA-256 after the atomic replace.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.workspace = WorkspaceManager(self.root)
        self.state_root = (self.root / "state" / "checkpoints").resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256_path(path: Path) -> str:
        return _sha256_bytes(path.read_bytes())

    def source_hash(self, workspace: str, relative_path: str) -> dict[str, Any]:
        path = self.workspace.resolve(workspace, relative_path, must_exist=True)
        data = path.read_bytes()
        st = path.stat()
        return {
            "workspace": workspace,
            "path": relative_path.replace("\\", "/"),
            "sha256": _sha256_bytes(data),
            "bytes": len(data),
            "mtime_ns": int(st.st_mtime_ns),
        }

    def _workspace_state(self, workspace: str) -> Path:
        self.workspace.workspace_root(workspace)
        base = (self.state_root / workspace).resolve()
        if base.parent != self.state_root:
            raise ValueError("Checkpoint workspace escapes state root")
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _checkpoint_dir(self, workspace: str, checkpoint_id: str) -> Path:
        if not _CHECKPOINT_RE.fullmatch(checkpoint_id or ""):
            raise ValueError("Invalid checkpoint_id")
        base = self._workspace_state(workspace)
        target = (base / checkpoint_id).resolve()
        if target.parent != base:
            raise ValueError("Checkpoint path escapes state root")
        return target

    def create_checkpoint(
        self,
        workspace: str,
        relative_path: str,
        label: str = "",
        checkpoint_id: str = "",
    ) -> dict[str, Any]:
        source = self.workspace.resolve(workspace, relative_path, must_exist=True)
        data = source.read_bytes()
        sha = _sha256_bytes(data)
        cid = str(checkpoint_id or "").strip()
        if cid:
            if not _CHECKPOINT_RE.fullmatch(cid):
                raise ValueError("Invalid checkpoint_id")
        else:
            cid = "CP-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12].upper()
        target = self._checkpoint_dir(workspace, cid)
        if target.exists():
            snapshot, metadata = self._load_metadata(workspace, cid)
            if metadata.get("path") != relative_path.replace("\\", "/"):
                raise ValueError("CHECKPOINT_OPERATION_CONFLICT: path mismatch")
            if metadata.get("sha256") != sha or int(metadata.get("bytes", -1)) != len(data):
                raise ValueError("CHECKPOINT_OPERATION_CONFLICT: source mismatch")
            return {**metadata, "idempotent_recovered": True}
        target.mkdir(parents=True, exist_ok=False)
        snapshot = target / "source.bin"
        metadata_path = target / "metadata.json"
        _atomic_write_bytes(snapshot, data)
        metadata = {
            "schema_version": "1.0",
            "checkpoint_id": cid,
            "workspace": workspace,
            "path": relative_path.replace("\\", "/"),
            "created_at": _now_iso(),
            "label": str(label or "")[:200],
            "sha256": sha,
            "bytes": len(data),
            "source_mtime_ns": int(source.stat().st_mtime_ns),
        }
        _atomic_write_json(metadata_path, metadata)
        return {**metadata, "idempotent_recovered": False}

    def _load_metadata(self, workspace: str, checkpoint_id: str) -> tuple[Path, dict[str, Any]]:
        target = self._checkpoint_dir(workspace, checkpoint_id)
        metadata_path = target / "metadata.json"
        snapshot = target / "source.bin"
        if not metadata_path.is_file() or not snapshot.is_file():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("checkpoint_id") != checkpoint_id or metadata.get("workspace") != workspace:
            raise ValueError("Checkpoint metadata mismatch")
        actual_snapshot_sha = _sha256_bytes(snapshot.read_bytes())
        if actual_snapshot_sha != metadata.get("sha256"):
            raise ValueError("Checkpoint snapshot integrity failure")
        return snapshot, metadata

    def list_checkpoints(self, workspace: str, relative_path: str = "") -> list[dict[str, Any]]:
        base = self._workspace_state(workspace)
        wanted = relative_path.replace("\\", "/") if relative_path else ""
        out: list[dict[str, Any]] = []
        for child in base.iterdir():
            if not child.is_dir() or not _CHECKPOINT_RE.fullmatch(child.name):
                continue
            try:
                _, meta = self._load_metadata(workspace, child.name)
            except Exception:
                continue
            if wanted and meta.get("path") != wanted:
                continue
            out.append(meta)
        out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return out

    def diff_checkpoint(self, workspace: str, checkpoint_id: str, context_lines: int = 3) -> dict[str, Any]:
        snapshot, metadata = self._load_metadata(workspace, checkpoint_id)
        source = self.workspace.resolve(workspace, metadata["path"], must_exist=True)
        before = snapshot.read_bytes().decode("utf-8-sig", errors="replace").splitlines(keepends=True)
        after = source.read_bytes().decode("utf-8-sig", errors="replace").splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            before,
            after,
            fromfile=f"checkpoint/{metadata['path']}",
            tofile=f"current/{metadata['path']}",
            n=max(0, min(int(context_lines), 20)),
        ))
        current_sha = self.sha256_path(source)
        return {
            "checkpoint_id": checkpoint_id,
            "workspace": workspace,
            "path": metadata["path"],
            "checkpoint_sha256": metadata["sha256"],
            "current_sha256": current_sha,
            "changed": current_sha != metadata["sha256"],
            "diff": diff,
        }

    def restore_checkpoint(
        self,
        workspace: str,
        checkpoint_id: str,
        expected_current_sha256: str = "",
    ) -> dict[str, Any]:
        snapshot, metadata = self._load_metadata(workspace, checkpoint_id)
        source = self.workspace.resolve(workspace, metadata["path"])
        current_exists = source.is_file()
        current_sha = self.sha256_path(source) if current_exists else None
        if expected_current_sha256:
            expected = expected_current_sha256.strip().lower()
            if current_sha != expected:
                raise ValueError(
                    f"SOURCE_VERSION_CONFLICT: expected {expected}, current {current_sha or 'MISSING'}"
                )
        data = snapshot.read_bytes()
        _atomic_write_bytes(source, data)
        restored_sha = self.sha256_path(source)
        if restored_sha != metadata["sha256"]:
            raise IOError("Checkpoint restore verification failed")
        return {
            "checkpoint_id": checkpoint_id,
            "workspace": workspace,
            "path": metadata["path"],
            "before_sha256": current_sha,
            "restored_sha256": restored_sha,
            "expected_sha256": metadata["sha256"],
            "match": True,
            "bytes": len(data),
            "restored_at": _now_iso(),
        }
