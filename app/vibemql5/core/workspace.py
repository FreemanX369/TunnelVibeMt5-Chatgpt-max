from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from ..config import default_root
from ..errors import PathViolation

_ALLOWED_SUFFIXES = {".mq5", ".mqh", ".set", ".json", ".txt", ".md"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_UTF8_BOM = b"\xef\xbb\xbf"


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


def _decode_utf8_preserve_newlines(data: bytes) -> tuple[str, bool]:
    has_bom = data.startswith(_UTF8_BOM)
    body = data[len(_UTF8_BOM):] if has_bom else data
    return body.decode("utf-8"), has_bom


def _newline_profile(text: str) -> tuple[str, str]:
    crlf = text.count("\r\n")
    without_crlf = text.replace("\r\n", "")
    lf = without_crlf.count("\n")
    cr = without_crlf.count("\r")
    counts = [(crlf, "\r\n", "CRLF"), (lf, "\n", "LF"), (cr, "\r", "CR")]
    present = [item for item in counts if item[0] > 0]
    if not present:
        return "\n", "NONE"
    dominant = max(present, key=lambda item: item[0])
    label = dominant[2] if len(present) == 1 else f"MIXED_{dominant[2]}"
    return dominant[1], label


def _normalize_newlines(text: str, newline: str) -> str:
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return canonical if newline == "\n" else canonical.replace("\n", newline)


def _encode_preserving_format(content: str, original: bytes | None = None) -> tuple[bytes, str, bool]:
    if original is None:
        return content.encode("utf-8"), "NEW", False
    original_text, has_bom = _decode_utf8_preserve_newlines(original)
    newline, newline_style = _newline_profile(original_text)
    normalized = _normalize_newlines(content, newline)
    payload = normalized.encode("utf-8")
    if has_bom:
        payload = _UTF8_BOM + payload
    return payload, newline_style, has_bom


class WorkspaceManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root()).resolve()
        self.workspaces_root = (self.root / "workspaces").resolve()
        self.workspaces_root.mkdir(parents=True, exist_ok=True)

    def list_workspaces(self) -> list[str]:
        return sorted(p.name for p in self.workspaces_root.iterdir() if p.is_dir())

    def workspace_root(self, workspace: str) -> Path:
        if not workspace or workspace in {".", ".."} or any(x in workspace for x in ("/", "\\")):
            raise PathViolation("Invalid workspace name")
        p = (self.workspaces_root / workspace).resolve()
        if p.parent != self.workspaces_root:
            raise PathViolation("Workspace escapes root")
        return p

    def resolve(self, workspace: str, relative_path: str, must_exist: bool = False) -> Path:
        ws = self.workspace_root(workspace)
        p = (ws / relative_path).resolve()
        try:
            p.relative_to(ws)
        except ValueError as exc:
            raise PathViolation(f"Path escapes workspace: {relative_path}") from exc
        if p.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise PathViolation(f"File type not allowed: {p.suffix}")
        if must_exist and not p.is_file():
            raise FileNotFoundError(p)
        return p

    def list_eas(self, workspace: str) -> list[str]:
        ws = self.workspace_root(workspace)
        base = ws / "Experts"
        if not base.exists():
            return []
        return sorted(str(p.relative_to(ws)).replace("\\", "/") for p in base.rglob("*.mq5") if p.is_file())

    def list_parameter_sets(self, workspace: str) -> list[str]:
        ws = self.workspace_root(workspace)
        base = ws / "Sets"
        if not base.exists():
            return []
        return sorted(str(p.relative_to(ws)).replace("\\", "/") for p in base.rglob("*.set") if p.is_file())

    def read_text(self, workspace: str, relative_path: str) -> str:
        data = self.resolve(workspace, relative_path, must_exist=True).read_bytes()
        text, _ = _decode_utf8_preserve_newlines(data)
        return text

    @staticmethod
    def _current_sha(path: Path) -> str | None:
        if not path.is_file():
            return None
        return _sha256_bytes(path.read_bytes())

    @classmethod
    def _assert_expected_sha(cls, path: Path, expected_sha256: str = "") -> str | None:
        current = cls._current_sha(path)
        if expected_sha256:
            expected = expected_sha256.strip().lower()
            if current != expected:
                raise ValueError(
                    f"SOURCE_VERSION_CONFLICT: expected {expected}, current {current or 'MISSING'}"
                )
        return current

    def write_text(
        self,
        workspace: str,
        relative_path: str,
        content: str,
        expected_sha256: str = "",
        checkpoint_id: str = "",
    ) -> dict:
        p = self.resolve(workspace, relative_path)
        before_sha = self._assert_expected_sha(p, expected_sha256)
        original = p.read_bytes() if p.is_file() else None
        data, newline_style, has_bom = _encode_preserving_format(content, original)
        _atomic_write_bytes(p, data)
        after_sha = self._current_sha(p)
        return {
            "path": str(p),
            "bytes": p.stat().st_size,
            "before_sha256": before_sha,
            "sha256": after_sha,
            "checkpoint_id": checkpoint_id or None,
            "atomic": True,
            "format_preserved": original is not None,
            "newline_style": newline_style,
            "utf8_bom": has_bom,
        }

    def apply_patch(
        self,
        workspace: str,
        relative_path: str,
        replacements: list[dict],
        expected_sha256: str = "",
        checkpoint_id: str = "",
    ) -> dict:
        p = self.resolve(workspace, relative_path, must_exist=True)
        before_sha = self._assert_expected_sha(p, expected_sha256)
        original = p.read_bytes()
        text, has_bom = _decode_utf8_preserve_newlines(original)
        newline, newline_style = _newline_profile(text)
        changes = 0
        for repl in replacements:
            old = repl.get("old")
            new = repl.get("new", "")
            count = int(repl.get("count", 1))
            if not old:
                raise ValueError("Patch replacement requires non-empty 'old'")
            old = _normalize_newlines(str(old), newline)
            new = _normalize_newlines(str(new), newline)
            found = text.count(old)
            if found == 0:
                raise ValueError("Patch anchor not found")
            if count > 0 and found < count:
                raise ValueError(f"Patch requested {count} replacements but only {found} anchors found")
            text, n = text.replace(old, new, count), min(found, count if count > 0 else found)
            changes += n
        data = text.encode("utf-8")
        if has_bom:
            data = _UTF8_BOM + data
        _atomic_write_bytes(p, data)
        after_sha = self._current_sha(p)
        return {
            "path": str(p),
            "replacements": changes,
            "bytes": p.stat().st_size,
            "before_sha256": before_sha,
            "sha256": after_sha,
            "checkpoint_id": checkpoint_id or None,
            "atomic": True,
            "format_preserved": True,
            "newline_style": newline_style,
            "utf8_bom": has_bom,
        }
