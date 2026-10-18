"""Read-only immutable fleet evidence, with no local job restoration side effects."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

from ..core.artifacts import ArtifactManager
from ..core.jobs import _JOB_ID_RE
from .job_journal import JournalError, _id, _integer, _decode, canonical, digest, target


class ArtifactProxy:
    def __init__(self, root, *, node_id, installation_id, max_artifact_bytes,
                 max_chunk_bytes):
        self.root = Path(root).resolve()
        self.node_id = _id(node_id, "dev_")
        self.installation_id = _id(installation_id)
        _integer(max_artifact_bytes); _integer(max_chunk_bytes)
        if max_chunk_bytes > max_artifact_bytes:
            raise JournalError("ARTIFACT_POLICY_INVALID")
        self.max_artifact_bytes, self.max_chunk_bytes = max_artifact_bytes, max_chunk_bytes
        self.artifacts = ArtifactManager(self.root)

    def _manifest_path(self, local_job_id, artifact_id):
        if not isinstance(local_job_id, str) or _JOB_ID_RE.fullmatch(local_job_id) is None:
            raise JournalError("ARTIFACT_SCOPE_MISMATCH")
        if not isinstance(artifact_id, str) or re.fullmatch(r"art_[a-f0-9]{32}", artifact_id) is None:
            raise JournalError("ARTIFACT_ID_INVALID")
        # Existing artifact primitive owns the local run directory/name checks.
        return self.root / "runs" / local_job_id / (artifact_id + ".json")

    def register(self, *, artifact_id, global_job_id, local_job_id, frozen_target,
                 relative_path, media_type="application/octet-stream"):
        self._manifest_path(local_job_id, artifact_id); _id(global_job_id)
        exact = target(frozen_target)
        if exact["device_id"] != self.node_id:
            raise JournalError("ARTIFACT_SCOPE_MISMATCH")
        if (not isinstance(relative_path, str) or len(relative_path) > 1024 or not relative_path
                or "\\" in relative_path or Path(relative_path).is_absolute()
                or any(part in {"", ".", ".."} for part in relative_path.split("/"))):
            raise JournalError("ARTIFACT_PATH_INVALID")
        path = self._path(local_job_id, relative_path)
        raw = self._read(path)
        if media_type not in {"application/octet-stream", "application/json", "text/plain", "image/png", "image/jpeg"}:
            raise JournalError("ARTIFACT_MEDIA_INVALID")
        manifest = {"schema": "fleet.artifact/1", "artifact_id": artifact_id,
            "node_id": self.node_id, "installation_id": self.installation_id,
            "global_job_id": global_job_id, "local_job_id": local_job_id, "target": exact,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "media_type": media_type,
            "relative_path": relative_path}
        self.artifacts.write_json_immutable(local_job_id, artifact_id + ".json", manifest)
        # Clients receive an opaque registered ID, never an OS path/download URL.
        return self._public(manifest)

    def _path(self, local_job_id, relative_path):
        base = (self.root / "runs" / local_job_id).resolve()
        candidate = base / relative_path
        try:
            # Refuse symlink/reparse path changes rather than making them authority.
            if any(p.is_symlink() for p in [candidate, *candidate.parents] if p != base.parent):
                raise OSError()
            path = candidate.resolve(strict=True)
            path.relative_to(base)
            if not path.is_file():
                raise OSError()
        except (OSError, ValueError):
            raise JournalError("ARTIFACT_PATH_INVALID") from None
        return path

    def _read(self, path):
        try:
            with path.open("rb") as stream:
                before = os.fstat(stream.fileno())
                if before.st_size > self.max_artifact_bytes:
                    raise JournalError("ARTIFACT_LIMIT")
                raw = stream.read(self.max_artifact_bytes + 1)
                after = os.fstat(stream.fileno())
            if len(raw) != before.st_size or len(raw) > self.max_artifact_bytes or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise JournalError("ARTIFACT_CHANGED")
            return raw
        except OSError:
            raise JournalError("ARTIFACT_UNAVAILABLE") from None

    @staticmethod
    def _public(manifest):
        return {**{key: value for key, value in manifest.items() if key != "relative_path"},
                "manifest_sha256": digest(manifest)}

    def chunk(self, *, artifact_id, global_job_id, local_job_id, frozen_target,
              expected_sha256, offset, length):
        _integer(offset, positive=False); _integer(length)
        if length > self.max_chunk_bytes:
            raise JournalError("ARTIFACT_CHUNK_LIMIT")
        manifest = self._manifest(artifact_id=artifact_id, global_job_id=global_job_id,
            local_job_id=local_job_id, frozen_target=frozen_target, expected_sha256=expected_sha256)
        raw = self._read(self._path(local_job_id, manifest["relative_path"]))
        if len(raw) != manifest["bytes"] or hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
            raise JournalError("ARTIFACT_QUARANTINED")
        if offset >= len(raw) or offset + length > len(raw):
            raise JournalError("ARTIFACT_RANGE_INVALID")
        chunk = raw[offset:offset + length]
        return {"schema": "fleet.artifact-chunk/1", "manifest": self._public(manifest),
            "offset": offset, "bytes": len(chunk), "chunk_sha256": hashlib.sha256(chunk).hexdigest(),
            "data_base64": base64.b64encode(chunk).decode("ascii"), "total_sha256": manifest["sha256"]}

    def _manifest(self, *, artifact_id, global_job_id, local_job_id, frozen_target, expected_sha256=None):
        manifest_path = self._manifest_path(local_job_id, artifact_id)
        try:
            if manifest_path.is_symlink():
                raise ValueError()
            with manifest_path.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            manifest = _decode(raw)
            if (not isinstance(manifest, dict) or set(manifest) != {"schema", "artifact_id", "node_id",
                    "installation_id", "global_job_id", "local_job_id", "target", "sha256", "bytes", "media_type", "relative_path"}
                    or type(manifest["bytes"]) is not int or not 0 <= manifest["bytes"] <= self.max_artifact_bytes
                    or not isinstance(manifest["sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", manifest["sha256"]) is None):
                raise ValueError()
        except Exception:
            raise JournalError("ARTIFACT_MANIFEST_INVALID") from None
        if (manifest.get("schema") != "fleet.artifact/1" or manifest.get("node_id") != self.node_id
                or manifest.get("installation_id") != self.installation_id
                or manifest.get("global_job_id") != global_job_id or manifest.get("local_job_id") != local_job_id
                or manifest.get("target") != target(frozen_target)
                or (expected_sha256 is not None and manifest.get("sha256") != expected_sha256)
                or manifest.get("artifact_id") != artifact_id):
            raise JournalError("ARTIFACT_SCOPE_MISMATCH")
        return manifest

    def manifest(self, **scope):
        return self._public(self._manifest(**scope))


def validate_chunk(receipt, *, manifest, offset, length):
    """Verify a remote chunk against the frozen registered manifest and range."""
    try:
        _integer(offset, positive=False); _integer(length)
        raw = base64.b64decode(receipt["data_base64"], validate=True)
        if (receipt["schema"] != "fleet.artifact-chunk/1" or receipt["manifest"] != manifest
                or type(receipt["offset"]) is not int or type(receipt["bytes"]) is not int
                or receipt["offset"] != offset or receipt["bytes"] != length or len(raw) != length
                or hashlib.sha256(raw).hexdigest() != receipt["chunk_sha256"]
                or receipt["total_sha256"] != manifest["sha256"]
                or offset < 0 or offset + length > manifest["bytes"]):
            raise ValueError()
        return raw
    except (ValueError, KeyError, TypeError):
        raise JournalError("ARTIFACT_CHUNK_INVALID") from None


def validate_complete(raw, manifest):
    if (not isinstance(manifest, dict) or type(manifest.get("bytes")) is not int
            or not isinstance(raw, bytes) or len(raw) != manifest["bytes"]
            or hashlib.sha256(raw).hexdigest() != manifest.get("sha256")):
        raise JournalError("ARTIFACT_QUARANTINED")
    return raw
