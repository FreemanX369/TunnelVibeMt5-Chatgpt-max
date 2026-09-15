from __future__ import annotations

import hashlib
import ipaddress
import json
import ntpath
import os
import re
import shutil
import socket
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..config import default_root
from .inventory import TerminalInventory
from .workspace import WorkspaceManager

EX5_IMPORT_SCHEMA_VERSION = "1.0"
EX5_IMPORT_RECEIPT_SCHEMA_VERSION = "1.0"
EX5_COMPILE_REQUIREMENT = "NOT_REQUIRED"
EX5_IMPORT_MAX_BYTES = 16_777_216
_ALLOWED_SUFFIX = ".ex5"
_TRUSTED_SUFFIXES = (".oaiusercontent.com", ".openai.com", ".chatgpt.com")
_OPENAI_AZURE_RE = re.compile(r"^oaisdmntpr[a-z0-9-]*\.blob\.core\.windows\.net$", re.I)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_bytes(obj: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_json_exclusive(path: Path, obj: Mapping[str, Any]) -> None:
    data = _canonical_json_bytes(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise RuntimeError(f"IMMUTABLE_SNAPSHOT_FAILED: existing immutable record differs: {path.name}")
        return
    fd, tmp_name = tempfile.mkstemp(prefix=".v-", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if path.read_bytes() != data:
            raise RuntimeError(f"IMMUTABLE_SNAPSHOT_FAILED: immutable record verify failed: {path.name}")
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_write_json(path: Path, obj: Mapping[str, Any]) -> None:
    data = _canonical_json_bytes(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".v-", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if path.read_bytes() != data:
            raise RuntimeError(f"IMPORT_RECEIPT_INDEX_VERIFY_FAILED: {path.name}")
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.vibemql5-{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as src, tmp.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _publish_content_addressed(temp_path: Path, target: Path, expected_sha: str, expected_bytes: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.stat().st_size != expected_bytes or _sha256_file(target) != expected_sha:
            raise RuntimeError("IMMUTABLE_SNAPSHOT_FAILED: content-addressed object identity mismatch")
        return
    try:
        with temp_path.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
    except FileExistsError:
        if not target.is_file() or target.stat().st_size != expected_bytes or _sha256_file(target) != expected_sha:
            raise RuntimeError("IMMUTABLE_SNAPSHOT_FAILED: raced object identity mismatch")
    if target.stat().st_size != expected_bytes or _sha256_file(target) != expected_sha:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError("IMMUTABLE_SNAPSHOT_FAILED: persisted object hash mismatch")


def _safe_relative_ex5(destination_path: str) -> str:
    raw = str(destination_path or "").strip().replace("\\", "/")
    drive, _ = ntpath.splitdrive(raw)
    if not raw or drive or raw.startswith("/") or raw.startswith("//"):
        raise ValueError("IMPORT_INVALID_DESTINATION")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("IMPORT_PATH_TRAVERSAL")
    if parts[0].lower() != "experts":
        raise ValueError("IMPORT_INVALID_DESTINATION: EX5 must be below workspace/Experts")
    if Path(parts[-1]).suffix.lower() != _ALLOWED_SUFFIX:
        raise ValueError("IMPORT_EXTENSION_NOT_ALLOWED")
    return "/".join(parts)


def _trusted_download_host(host: str) -> bool:
    h = str(host or "").strip().rstrip(".").lower()
    if not h:
        return False
    if any(h == s[1:] or h.endswith(s) for s in _TRUSTED_SUFFIXES):
        return True
    return bool(_OPENAI_AZURE_RE.fullmatch(h))


def _validate_download_url(url: str) -> urllib.parse.ParseResult:
    try:
        parsed = urllib.parse.urlparse(str(url or ""))
    except Exception as exc:
        raise ValueError("IMPORT_FILE_NOT_FOUND: invalid download URL") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("IMPORT_DOWNLOAD_URL_REJECTED")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("IMPORT_DOWNLOAD_URL_REJECTED") from exc
    if port not in (None, 443):
        raise ValueError("IMPORT_DOWNLOAD_URL_REJECTED")
    if not _trusted_download_host(parsed.hostname):
        raise ValueError("IMPORT_DOWNLOAD_HOST_NOT_TRUSTED")
    try:
        addrs = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("IMPORT_DOWNLOAD_HOST_UNRESOLVED") from exc
    ips = {item[4][0] for item in addrs if item and item[4]}
    if not ips:
        raise ValueError("IMPORT_DOWNLOAD_HOST_UNRESOLVED")
    for value in ips:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("IMPORT_DOWNLOAD_HOST_UNSAFE") from exc
        if not ip.is_global:
            raise ValueError("IMPORT_DOWNLOAD_HOST_UNSAFE")
    return parsed


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class BinaryIngressManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root()).resolve()
        self.workspace = WorkspaceManager(self.root)
        self.inventory = TerminalInventory(self.root)
        self.store = self.root / "binary_store" / "ex5"
        self.objects = self.store / "objects"
        self.bindings = self.store / "bindings"
        self.imports = self.store / "imports"
        self.receipt_indexes = self.store / "receipt_indexes"
        self.receipt_index_mutation = self.receipt_indexes / "mutation"
        self.receipt_index_import = self.receipt_indexes / "import"
        self.receipt_index_binary = self.receipt_indexes / "binary"
        self.tmp = self.store / "tmp"
        for p in (self.objects, self.bindings, self.imports, self.receipt_index_mutation, self.receipt_index_import, self.receipt_index_binary, self.tmp):
            p.mkdir(parents=True, exist_ok=True)

    def _workspace_destination(self, workspace: str, logical_path: str) -> Path:
        ws = self.workspace.workspace_root(workspace)
        if not ws.is_dir():
            raise ValueError("IMPORT_WORKSPACE_NOT_FOUND")
        rel = _safe_relative_ex5(logical_path)
        target = ws / Path(*rel.split("/"))
        cursor = ws
        for part in Path(*rel.split("/")[:-1]).parts:
            cursor = cursor / part
            if cursor.exists():
                if cursor.is_symlink() or bool(getattr(cursor, "is_junction", lambda: False)()):
                    raise ValueError("IMPORT_PATH_TRAVERSAL")
        try:
            target.resolve(strict=False).relative_to(ws.resolve(strict=True))
        except ValueError as exc:
            raise ValueError("IMPORT_PATH_TRAVERSAL") from exc
        if target.exists() and (target.is_symlink() or bool(getattr(target, "is_junction", lambda: False)())):
            raise ValueError("IMPORT_PATH_TRAVERSAL")
        return target

    def _download_file_param(self, file_param: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
        if not isinstance(file_param, Mapping):
            raise ValueError("IMPORT_FILE_NOT_FOUND: file parameter must be an authorized file reference")
        url = str(file_param.get("download_url") or "").strip()
        file_id = str(file_param.get("file_id") or "").strip()
        if not url or not file_id:
            raise ValueError("IMPORT_FILE_NOT_FOUND: download_url and file_id are required")
        _validate_download_url(url)
        name = str(file_param.get("file_name") or "external.ex5").strip() or "external.ex5"
        if Path(name).suffix.lower() != ".ex5":
            raise ValueError("IMPORT_EXTENSION_NOT_ALLOWED")
        mime = str(file_param.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"
        fd, temp_name = tempfile.mkstemp(prefix="download-", suffix=".ex5.tmp", dir=str(self.tmp))
        os.close(fd)
        temp = Path(temp_name)
        total = 0
        try:
            opener = urllib.request.build_opener(_ValidatedRedirectHandler())
            req = urllib.request.Request(url, headers={"User-Agent": "VibeMQL5-TIP026R2/0.2.31", "Accept-Encoding": "identity"})
            with opener.open(req, timeout=60) as response, temp.open("wb") as out:
                final_url = str(getattr(response, "geturl", lambda: url)())
                _validate_download_url(final_url)
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > EX5_IMPORT_MAX_BYTES:
                            raise ValueError("IMPORT_FILE_TOO_LARGE")
                    except ValueError as exc:
                        if str(exc) == "IMPORT_FILE_TOO_LARGE":
                            raise
                while True:
                    chunk = response.read(min(1024 * 1024, EX5_IMPORT_MAX_BYTES + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > EX5_IMPORT_MAX_BYTES:
                        raise ValueError("IMPORT_FILE_TOO_LARGE")
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if total == 0:
                raise ValueError("IMPORT_EMPTY_FILE")
            return temp, {"file_id": file_id, "file_name": name, "mime_type": mime, "bytes": total}
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def import_file_param(self, workspace: str, file_param: Mapping[str, Any], destination_path: str = "", expected_sha256: str = "", overwrite: bool = False, *, mutation_operation_id: str = "") -> dict[str, Any]:
        temp, incoming = self._download_file_param(file_param)
        try:
            return self._import_temp(workspace, temp, destination_path or f"Experts/{Path(str(incoming['file_name'])).name}", expected_sha256, overwrite, source="MCP_FILE_IMPORT", source_file_id=str(incoming.get("file_id") or ""), source_file_name=str(incoming.get("file_name") or ""), mime_type=str(incoming.get("mime_type") or "application/octet-stream"), mutation_operation_id=mutation_operation_id)
        finally:
            temp.unlink(missing_ok=True)

    def import_authorized_file(self, workspace: str, *, file_id: str, download_url: str, file_name: str, mime_type: str = "application/octet-stream", destination_path: str = "", expected_sha256: str = "", overwrite: bool = False, mutation_operation_id: str = "") -> dict[str, Any]:
        descriptor = {"file_id": str(file_id or "").strip(), "download_url": str(download_url or "").strip(), "file_name": str(file_name or "").strip(), "mime_type": str(mime_type or "application/octet-stream").strip() or "application/octet-stream"}
        temp, incoming = self._download_file_param(descriptor)
        try:
            return self._import_temp(workspace, temp, destination_path or f"Experts/{Path(str(incoming['file_name'])).name}", expected_sha256, overwrite, source="CHATGPT_WIDGET_FILE_IMPORT", source_file_id=str(incoming.get("file_id") or ""), source_file_name=str(incoming.get("file_name") or ""), mime_type=str(incoming.get("mime_type") or "application/octet-stream"), mutation_operation_id=mutation_operation_id)
        finally:
            temp.unlink(missing_ok=True)

    def import_local_file(self, workspace: str, source_path: Path, destination_path: str = "", expected_sha256: str = "", overwrite: bool = False, *, source: str = "LOCAL_QUALIFICATION_FILE", mutation_operation_id: str = "") -> dict[str, Any]:
        source_path = Path(source_path).resolve(strict=True)
        if not source_path.is_file(): raise ValueError("IMPORT_FILE_NOT_FOUND")
        size = source_path.stat().st_size
        if size <= 0: raise ValueError("IMPORT_EMPTY_FILE")
        if size > EX5_IMPORT_MAX_BYTES: raise ValueError("IMPORT_FILE_TOO_LARGE")
        if source_path.suffix.lower() != ".ex5": raise ValueError("IMPORT_EXTENSION_NOT_ALLOWED")
        return self._import_temp(workspace, source_path, destination_path or f"Experts/{source_path.name}", expected_sha256, overwrite, source=source, source_file_id="", source_file_name=source_path.name, mime_type="application/octet-stream", mutation_operation_id=mutation_operation_id)

    def _import_temp(self, workspace: str, source_path: Path, destination_path: str, expected_sha256: str, overwrite: bool, *, source: str, source_file_id: str, source_file_name: str, mime_type: str, mutation_operation_id: str) -> dict[str, Any]:
        logical = _safe_relative_ex5(destination_path)
        target = self._workspace_destination(workspace, logical)
        size = source_path.stat().st_size
        if size <= 0: raise ValueError("IMPORT_EMPTY_FILE")
        if size > EX5_IMPORT_MAX_BYTES: raise ValueError("IMPORT_FILE_TOO_LARGE")
        sha = _sha256_file(source_path)
        expected = str(expected_sha256 or "").strip().lower()
        if expected:
            if not _SHA_RE.fullmatch(expected): raise ValueError("EXPECTED_SHA256_INVALID")
            if sha != expected: raise ValueError("EXPECTED_SHA256_MISMATCH")
        object_id = f"OBJ-SHA256-{sha}"
        object_path = self.objects / sha[:2] / f"{sha}.ex5"
        binding_body = {"schema_version": EX5_IMPORT_SCHEMA_VERSION, "kind": "VIBEMQL5_IMPORTED_EX5_BINDING", "workspace": str(workspace), "logical_path": logical, "object_id": object_id, "sha256": sha, "bytes": int(size), "build_input_type": "IMPORTED_EX5"}
        binding_sha = hashlib.sha256(_canonical_json_bytes(binding_body)).hexdigest()
        binary_ref = f"BIN-{binding_sha}"
        snapshot_id = f"BSNAP-{binding_sha}"
        binding_path = self.bindings / f"{binding_sha}.json"
        existing_sha = _sha256_file(target) if target.is_file() else None
        if target.exists() and not target.is_file(): raise ValueError("DESTINATION_CONFLICT")
        if existing_sha and existing_sha != sha and not overwrite: raise ValueError("DESTINATION_CONFLICT")
        _publish_content_addressed(source_path, object_path, sha, size)
        _write_json_exclusive(binding_path, binding_body)
        status = "ALREADY_PRESENT" if existing_sha == sha else "IMPORTED"
        if existing_sha != sha: _atomic_copy(object_path, target)
        if target.stat().st_size != size or _sha256_file(target) != sha: raise RuntimeError("IMPORT_COPY_FAILED: workspace binding byte identity mismatch")
        mutation_id = str(mutation_operation_id or "").strip() or f"MUT-{uuid.uuid4().hex[:16].upper()}"
        if not re.fullmatch(r"MUT-[A-F0-9]{16}", mutation_id): raise RuntimeError("IMPORT_RECEIPT_MUTATION_ID_INVALID")
        import_id = f"IMPORT-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:8].upper()}"
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        receipt_id = f"EX5RCP-{import_id[7:]}"
        receipt_body = {"schema_version": EX5_IMPORT_RECEIPT_SCHEMA_VERSION, "kind": "VIBEMQL5_EX5_IMPORT_RECEIPT", "receipt_id": receipt_id, "import_id": import_id, "ea_binary_ref": binary_ref, "workspace": str(workspace), "destination_path": logical, "actual_sha256": sha, "bytes": int(size), "binary_object_id": object_id, "provenance_source": source, "source_file_id": source_file_id or None, "imported_at": imported_at, "mutation_operation_id": mutation_id, "already_present": status == "ALREADY_PRESENT", "idempotent": status == "ALREADY_PRESENT", "compile_requirement": EX5_COMPILE_REQUIREMENT, "download_url_persisted": False, "imported_at_utc": imported_at, "status": status, "source": source, "logical_path": logical, "sha256": sha, "object_id": object_id, "source_file_name": source_file_name or None, "mime_type": mime_type or "application/octet-stream"}
        receipt_sha256 = hashlib.sha256(_canonical_json_bytes(receipt_body)).hexdigest()
        receipt = {**receipt_body, "receipt_sha256": receipt_sha256}
        receipt_path = self.imports / f"{import_id}.json"
        _write_json_exclusive(receipt_path, receipt)
        self._persist_receipt_indexes(receipt)
        verified = self._verify_canonical_receipt(receipt, require_binary_index_current=True)
        return {"schema_version": EX5_IMPORT_SCHEMA_VERSION, "status": status, "workspace": str(workspace), "path": logical, "file_name": Path(logical).name, "bytes": int(size), "sha256": sha, "media_type": mime_type or "application/octet-stream", "immutable_object_id": object_id, "immutable_binary_ref": binary_ref, "ea_binary_ref": binary_ref, "snapshot_id": snapshot_id, "import_id": import_id, "receipt_id": receipt_id, "receipt_sha256": receipt_sha256, "mutation_operation_id": mutation_id, "provenance_source": source, "source_file_id": source_file_id or None, "compile_requirement": EX5_COMPILE_REQUIREMENT, "download_url_persisted": False, "already_present": status == "ALREADY_PRESENT", "idempotent": status == "ALREADY_PRESENT", "build_input_type": "IMPORTED_EX5", "complete": bool(verified)}

    @staticmethod
    def _selector_index_name(value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest() + ".json"

    def _index_path(self, selector_type: str, selector: str) -> Path:
        roots = {"mutation_operation_id": self.receipt_index_mutation, "import_id": self.receipt_index_import, "ea_binary_ref": self.receipt_index_binary}
        if selector_type not in roots: raise ValueError("EX5_IMPORT_RECEIPT_SELECTOR_INVALID")
        return roots[selector_type] / self._selector_index_name(selector)

    def _receipt_index_record(self, selector_type: str, selector: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
        return {"schema_version": EX5_IMPORT_RECEIPT_SCHEMA_VERSION, "kind": "VIBEMQL5_EX5_IMPORT_RECEIPT_INDEX", "selector_type": selector_type, "selector": selector, "receipt_id": receipt.get("receipt_id"), "import_id": receipt.get("import_id"), "ea_binary_ref": receipt.get("ea_binary_ref"), "receipt_sha256": receipt.get("receipt_sha256")}

    def _persist_receipt_indexes(self, receipt: Mapping[str, Any]) -> None:
        selectors = (("mutation_operation_id", str(receipt.get("mutation_operation_id") or "")), ("import_id", str(receipt.get("import_id") or "")), ("ea_binary_ref", str(receipt.get("ea_binary_ref") or "")))
        for selector_type, selector in selectors:
            if not selector: raise RuntimeError("IMPORT_RECEIPT_INDEX_SELECTOR_MISSING")
            record = self._receipt_index_record(selector_type, selector, receipt)
            path = self._index_path(selector_type, selector)
            if selector_type == "ea_binary_ref": _atomic_write_json(path, record)
            else: _write_json_exclusive(path, record)

    def _load_receipt_path(self, import_id: str) -> Path:
        if not re.fullmatch(r"IMPORT-\d{8}-\d{6}-[A-F0-9]{8}", str(import_id or "")): raise ValueError("EX5_IMPORT_RECEIPT_SELECTOR_INVALID")
        return self.imports / f"{import_id}.json"

    @staticmethod
    def _receipt_hash_body(receipt: Mapping[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in dict(receipt).items() if k != "receipt_sha256"}

    def _verify_canonical_receipt(self, expected: Mapping[str, Any], *, require_binary_index_current: bool = False) -> bool:
        import_id = str(expected.get("import_id") or "")
        path = self._load_receipt_path(import_id)
        try: persisted = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: raise RuntimeError("IMPORT_RECEIPT_VERIFY_FAILED") from exc
        if not isinstance(persisted, dict) or persisted != dict(expected): raise RuntimeError("IMPORT_RECEIPT_VERIFY_FAILED")
        body = self._receipt_hash_body(persisted)
        actual_receipt_sha = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
        if actual_receipt_sha != str(persisted.get("receipt_sha256") or ""): raise RuntimeError("IMPORT_RECEIPT_SHA_MISMATCH")
        if persisted.get("compile_requirement") != EX5_COMPILE_REQUIREMENT: raise RuntimeError("IMPORT_RECEIPT_COMPILE_REQUIREMENT_INVALID")
        if persisted.get("download_url_persisted") is not False: raise RuntimeError("IMPORT_RECEIPT_URL_POLICY_INVALID")
        if "download_url" in persisted or "authorization" in persisted: raise RuntimeError("IMPORT_RECEIPT_SECRET_PERSISTENCE_INVALID")
        if str(persisted.get("actual_sha256") or "") != str(persisted.get("sha256") or ""): raise RuntimeError("IMPORT_RECEIPT_BINARY_BINDING_INVALID")
        if str(persisted.get("binary_object_id") or "") != str(persisted.get("object_id") or ""): raise RuntimeError("IMPORT_RECEIPT_BINARY_BINDING_INVALID")
        selector_types = ["mutation_operation_id", "import_id"]
        if require_binary_index_current: selector_types.append("ea_binary_ref")
        for selector_type in selector_types:
            selector = str(persisted.get(selector_type) or "")
            index_path = self._index_path(selector_type, selector)
            try: index = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception as exc: raise RuntimeError("IMPORT_RECEIPT_INDEX_VERIFY_FAILED") from exc
            expected_index = self._receipt_index_record(selector_type, selector, persisted)
            if index != expected_index: raise RuntimeError("IMPORT_RECEIPT_INDEX_VERIFY_FAILED")
        return True

    def _known_legacy_mutation(self, mutation_operation_id: str) -> bool:
        audit = self.root / "state" / "concurrency" / "audit.jsonl"
        if not audit.is_file(): return False
        try:
            for line in audit.read_text(encoding="utf-8", errors="replace").splitlines():
                try: item = json.loads(line)
                except Exception: continue
                if isinstance(item, dict) and item.get("event") == "MUTATION_COMPLETED" and item.get("operation") in {"import_ex5", "import_ex5_authorized_file"} and item.get("operation_id") == mutation_operation_id:
                    return True
        except Exception: return False
        return False

    def get_import_receipt(self, *, mutation_operation_id: str = "", import_id: str = "", ea_binary_ref: str = "") -> dict[str, Any]:
        selectors = [("mutation_operation_id", str(mutation_operation_id or "").strip()), ("import_id", str(import_id or "").strip()), ("ea_binary_ref", str(ea_binary_ref or "").strip())]
        selected = [(kind, value) for kind, value in selectors if value]
        if len(selected) != 1: raise ValueError("EX5_IMPORT_RECEIPT_SELECTOR_INVALID: exactly one selector is required")
        selector_type, selector = selected[0]
        if selector_type == "mutation_operation_id" and not re.fullmatch(r"MUT-[A-F0-9]{16}", selector): raise ValueError("EX5_IMPORT_RECEIPT_SELECTOR_INVALID")
        if selector_type == "import_id" and not re.fullmatch(r"IMPORT-\d{8}-\d{6}-[A-F0-9]{8}", selector): raise ValueError("EX5_IMPORT_RECEIPT_SELECTOR_INVALID")
        if selector_type == "ea_binary_ref" and (not selector.startswith("BIN-") or not _SHA_RE.fullmatch(selector[4:].lower())): raise ValueError("EX5_IMPORT_RECEIPT_SELECTOR_INVALID")
        index_path = self._index_path(selector_type, selector)
        if not index_path.is_file():
            legacy = self._known_legacy_mutation(selector) if selector_type == "mutation_operation_id" else (self._load_receipt_path(selector).is_file() if selector_type == "import_id" else (self.bindings / f"{selector[4:].lower()}.json").is_file())
            if legacy: return {"schema_version": EX5_IMPORT_RECEIPT_SCHEMA_VERSION, "state": "LEGACY_RECEIPT_UNRESOLVABLE", "selector_type": selector_type, "selector": selector}
            raise ValueError("EX5_IMPORT_RECEIPT_NOT_FOUND")
        try: index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as exc: raise ValueError("EX5_IMPORT_RECEIPT_INDEX_INVALID") from exc
        if not isinstance(index, dict) or index.get("selector_type") != selector_type or index.get("selector") != selector: raise ValueError("EX5_IMPORT_RECEIPT_INDEX_INVALID")
        persisted_path = self._load_receipt_path(str(index.get("import_id") or ""))
        try: receipt = json.loads(persisted_path.read_text(encoding="utf-8"))
        except Exception as exc: raise ValueError("EX5_IMPORT_RECEIPT_NOT_FOUND") from exc
        if not isinstance(receipt, dict) or receipt.get("kind") != "VIBEMQL5_EX5_IMPORT_RECEIPT": raise ValueError("EX5_IMPORT_RECEIPT_INVALID")
        self._verify_canonical_receipt(receipt)
        if index != self._receipt_index_record(selector_type, selector, receipt): raise ValueError("EX5_IMPORT_RECEIPT_INDEX_INVALID")
        return {"schema_version": receipt["schema_version"], "import_id": receipt["import_id"], "ea_binary_ref": receipt["ea_binary_ref"], "workspace": receipt["workspace"], "destination_path": receipt["destination_path"], "actual_sha256": receipt["actual_sha256"], "bytes": receipt["bytes"], "binary_object_id": receipt["binary_object_id"], "receipt_id": receipt["receipt_id"], "receipt_sha256": receipt["receipt_sha256"], "provenance_source": receipt["provenance_source"], "source_file_id": receipt.get("source_file_id"), "imported_at": receipt["imported_at"], "mutation_operation_id": receipt["mutation_operation_id"], "already_present": bool(receipt["already_present"]), "idempotent": bool(receipt["idempotent"]), "compile_requirement": receipt["compile_requirement"], "download_url_persisted": bool(receipt["download_url_persisted"])}

    def import_provenance(self, binary_ref: str) -> dict[str, Any]:
        ref = str(binary_ref or "").strip()
        receipts: list[dict[str, Any]] = []
        for path in sorted(self.imports.glob("IMPORT-*.json")):
            try: value = json.loads(path.read_text(encoding="utf-8"))
            except Exception: continue
            if isinstance(value, dict) and str(value.get("ea_binary_ref") or "") == ref: receipts.append(value)
        def _receipt_sort_key(item: Mapping[str, Any]) -> tuple[float, str]:
            raw = str(item.get("imported_at_utc") or "").strip()
            try: instant = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError): instant = 0.0
            return instant, str(item.get("import_id") or "")
        receipts.sort(key=_receipt_sort_key)
        selected = None
        secure_sources = {"MCP_FILE_IMPORT", "CHATGPT_WIDGET_FILE_IMPORT"}
        for item in receipts:
            if item.get("source") in secure_sources and item.get("source_file_id"): selected = item
        if selected is None and receipts: selected = receipts[-1]
        return {"source": (selected or {}).get("source") or "CONTROLLED_EX5_IMPORT", "import_id": (selected or {}).get("import_id"), "source_file_id": (selected or {}).get("source_file_id"), "source_file_name": (selected or {}).get("source_file_name"), "mime_type": (selected or {}).get("mime_type"), "receipt_count": len(receipts), "sources": sorted({str(x.get("source") or "") for x in receipts if x.get("source")})}

    def resolve_for_launch(self, workspace: str, logical_path: str, binary_ref: str) -> dict[str, Any]:
        ref = str(binary_ref or "").strip()
        if not ref.startswith("BIN-") or not _SHA_RE.fullmatch(ref[4:].lower()): raise ValueError("BUILD_INPUT_REFERENCE_INVALID")
        binding_hash = ref[4:].lower()
        path = self.bindings / f"{binding_hash}.json"
        if not path.is_file(): raise ValueError("BUILD_INPUT_REFERENCE_INVALID")
        try: record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc: raise ValueError("BUILD_INPUT_REFERENCE_INVALID") from exc
        stable = {"schema_version": record.get("schema_version"), "kind": record.get("kind"), "workspace": record.get("workspace"), "logical_path": record.get("logical_path"), "object_id": record.get("object_id"), "sha256": record.get("sha256"), "bytes": record.get("bytes"), "build_input_type": record.get("build_input_type")}
        if hashlib.sha256(_canonical_json_bytes(stable)).hexdigest() != binding_hash: raise ValueError("BUILD_INPUT_REFERENCE_INVALID")
        logical = _safe_relative_ex5(logical_path)
        if record.get("workspace") != str(workspace) or record.get("logical_path") != logical: raise ValueError("BUILD_INPUT_REFERENCE_INVALID: workspace/path binding mismatch")
        sha = str(record.get("sha256") or "")
        size = int(record.get("bytes") or 0)
        obj = self.objects / sha[:2] / f"{sha}.ex5"
        if not obj.is_file() or obj.stat().st_size != size or _sha256_file(obj) != sha: raise ValueError("BUILD_INPUT_NOT_READY")
        return {**record, "ea_binary_ref": ref, "snapshot_id": f"BSNAP-{binding_hash}", "object_path": str(obj)}

    @staticmethod
    def expert_name(workspace: str, logical_path: str) -> str:
        rel = Path(*_safe_relative_ex5(logical_path).split("/"))
        sub = Path(*rel.parts[1:])
        return str(Path("VibeMQL5") / str(workspace) / sub.with_suffix("")).replace("/", "\\")

    def capture_for_job(self, binding: Mapping[str, Any], run_dir: Path) -> dict[str, Any]:
        sha = str(binding.get("sha256") or "")
        size = int(binding.get("bytes") or 0)
        source = Path(str(binding.get("object_path") or ""))
        if not source.is_file() or source.stat().st_size != size or _sha256_file(source) != sha: raise ValueError("BUILD_INPUT_NOT_READY")
        target = Path(run_dir) / "compiled.ex5"
        if target.exists():
            if not target.is_file() or target.stat().st_size != size or _sha256_file(target) != sha: raise RuntimeError("IMMUTABLE_SNAPSHOT_FAILED: job EX5 already differs")
        else: _atomic_copy(source, target)
        if _sha256_file(target) != sha: raise RuntimeError("IMMUTABLE_SNAPSHOT_FAILED: job EX5 hash mismatch")
        return {"path": str(target), "sha256": sha, "bytes": size, "source_path": str(source), "ea_binary_ref": binding.get("ea_binary_ref"), "build_input_type": "IMPORTED_EX5"}

    def stage_for_terminal(self, binding: Mapping[str, Any], terminal_alias: str, terminal_build_at_execution: int | None = None) -> dict[str, Any]:
        t = self.inventory.get(terminal_alias)
        workspace = str(binding.get("workspace") or "")
        logical = _safe_relative_ex5(str(binding.get("logical_path") or ""))
        rel = Path(*logical.split("/"))
        sub = Path(*rel.parts[1:])
        source = Path(str(binding.get("object_path") or ""))
        sha = str(binding.get("sha256") or "")
        size = int(binding.get("bytes") or 0)
        if not source.is_file() or source.stat().st_size != size or _sha256_file(source) != sha: raise ValueError("BUILD_INPUT_NOT_READY")
        deploy_root = Path(t.data_root) / "MQL5" / "Experts" / "VibeMQL5" / workspace
        target = deploy_root / sub
        _atomic_copy(source, target)
        actual = _sha256_file(target) if target.is_file() else None
        if actual != sha or target.stat().st_size != size: raise RuntimeError("MT5_DEPLOY_HASH_MISMATCH")
        return {"status": "PASSED", "requested_terminal": terminal_alias, "effective_terminal": terminal_alias, "terminal_build_at_execution": int(terminal_build_at_execution or t.build), "terminal_inventory_build": int(t.build), "logical_path": logical, "deployed_path": str(target), "ea_sha256_at_execution": actual, "ea_bytes_at_execution": int(target.stat().st_size), "ea_binary_ref": binding.get("ea_binary_ref"), "expert_name": self.expert_name(workspace, logical), "build_input_type": "IMPORTED_EX5"}

    def verify_terminal_stage(self, deployment: Mapping[str, Any]) -> dict[str, Any]:
        path = Path(str(deployment.get("deployed_path") or ""))
        expected_sha = str(deployment.get("ea_sha256_at_execution") or "")
        expected_bytes = int(deployment.get("ea_bytes_at_execution") or 0)
        if not path.is_file(): raise RuntimeError("MT5_DEPLOY_FAILED")
        actual_sha = _sha256_file(path)
        actual_bytes = int(path.stat().st_size)
        if actual_sha != expected_sha or actual_bytes != expected_bytes: raise RuntimeError("MT5_DEPLOY_HASH_MISMATCH")
        return {**dict(deployment), "post_verify_sha256": actual_sha, "post_verify_bytes": actual_bytes}
