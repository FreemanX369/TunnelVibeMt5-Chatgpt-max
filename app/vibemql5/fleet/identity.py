from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

from ..core.jobs import _atomic_write_json, _exclusive_file_lock, _read_json_object
from ..errors import VibeMQL5Error

SCHEMA = "fleet.identity/1"
SOURCE = "LOCAL_PERSISTED_REGISTRY"


class IdentityError(VibeMQL5Error):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _positive(value) -> bool:
    return type(value) is int and value > 0


def normalize_path(raw: str) -> str:
    """Normalize absolute paths without interpreting Windows paths on POSIX."""
    if not isinstance(raw, str) or not raw.strip() or "\0" in raw:
        raise IdentityError("IDENTITY_INVALID", "Binding path must be nonempty")
    if raw.startswith("\\\\?\\"):
        raw = raw[4:]
        if raw.upper().startswith("UNC\\"):
            raw = "\\\\" + raw[4:]
    drive, tail = ntpath.splitdrive(raw)
    if drive:
        if not tail.startswith(("/", "\\")) and not (drive.startswith("\\\\") and not tail):
            raise IdentityError("IDENTITY_INVALID", "Binding must be absolute")
        return ntpath.normpath(raw.replace("/", "\\")).lower()
    if not raw.startswith("/") or "\\" in raw:
        raise IdentityError("IDENTITY_INVALID", "Binding must be absolute")
    return os.path.normpath(raw)


def _observation(raw: str, *, directory: bool) -> dict:
    normalized = normalize_path(raw)
    result = {"path": normalized, "canonical_path": None, "file_id": None}
    # A Windows binding is not physically observable in a POSIX fixture.
    if ntpath.splitdrive(normalized)[0] and os.name != "nt":
        return result
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
        if not (resolved.is_dir() if directory else resolved.is_file()):
            return result
        stat = resolved.stat()
        result["canonical_path"] = normalize_path(str(resolved))
        if stat.st_ino:
            result["file_id"] = (stat.st_dev, stat.st_ino)
    except (OSError, RuntimeError):
        pass
    return result


def binding_for(terminal) -> dict:
    exe = _observation(terminal.terminal_path, directory=False)
    data = _observation(terminal.data_root, directory=True)
    return {"terminal_path": exe["path"], "data_root": data["path"],
            "terminal_canonical_path": exe["canonical_path"],
            "data_canonical_path": data["canonical_path"]}


def inspect_resources(terminals) -> dict[str, dict]:
    observations = {}
    aliases = []
    for terminal in terminals:
        if not isinstance(terminal.alias, str) or not terminal.alias.strip() or terminal.alias != terminal.alias.strip():
            raise IdentityError("IDENTITY_INVALID", "Invalid terminal alias")
        key = terminal.alias.upper()
        if key in observations:
            raise IdentityError("RESOURCE_CONFLICT", "Duplicate case-insensitive terminal alias")
        aliases.append(key)
        observations[key] = {
            "terminal": _observation(terminal.terminal_path, directory=False),
            "data": _observation(terminal.data_root, directory=True),
        }
    out = {key: {"conflicts": [], "qualified": all(
        value["canonical_path"] is not None for value in observations[key].values()
    )} for key in aliases}
    for index, left in enumerate(aliases):
        for right in aliases[index + 1:]:
            conflict = False
            for resource in ("terminal", "data"):
                a, b = observations[left][resource], observations[right][resource]
                conflict |= a["path"] == b["path"]
                conflict |= a["canonical_path"] is not None and a["canonical_path"] == b["canonical_path"]
                conflict |= a["file_id"] is not None and a["file_id"] == b["file_id"]
            if conflict:
                out[left]["conflicts"].append(right)
                out[right]["conflicts"].append(left)
    return out


def _validate_terminal(terminal: dict) -> None:
    def invalid(message):
        raise IdentityError("IDENTITY_INVALID", message)
    if not isinstance(terminal, dict):
        invalid("Invalid terminal record")
    terminal_id, alias = terminal.get("terminal_id"), terminal.get("alias")
    if not isinstance(terminal_id, str) or not re.fullmatch(r"term_[a-f0-9]{32}", terminal_id):
        invalid("Invalid terminal ID")
    if not isinstance(alias, str) or not alias.strip() or alias != alias.strip():
        invalid("Invalid terminal alias")
    if not _positive(terminal.get("terminal_generation")) or type(terminal.get("enabled")) is not bool:
        invalid("Invalid terminal generation/enabled state")
    binding = terminal.get("binding")
    if not isinstance(binding, dict) or set(binding) != {"terminal_path", "data_root", "terminal_canonical_path", "data_canonical_path"}:
        invalid("Malformed terminal binding")
    for field, path in binding.items():
        if path is None and field.endswith("canonical_path"):
            continue
        if normalize_path(path) != path:
            invalid("Noncanonical binding path")


def _static_resource_conflict(rows) -> bool:
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            for fields in (("terminal_path", "terminal_canonical_path"), ("data_root", "data_canonical_path")):
                a = {left["binding"][field] for field in fields} - {None}
                b = {right["binding"][field] for field in fields} - {None}
                if a & b:
                    return True
    return False


def _validate_registry(record: dict) -> None:
    def invalid(message):
        raise IdentityError("IDENTITY_INVALID", message)
    if record.get("schema") != SCHEMA or not re.fullmatch(r"dev_[a-f0-9]{32}", str(record.get("device_id", ""))):
        invalid("Unsupported schema or device ID")
    if not _positive(record.get("identity_revision")) or not isinstance(record.get("terminals"), list):
        invalid("Invalid identity revision/terminal list")
    ids, aliases = set(), set()
    for terminal in record["terminals"]:
        _validate_terminal(terminal)
        terminal_id, alias = terminal.get("terminal_id"), terminal.get("alias")
        if alias.upper() in aliases or terminal_id in ids:
            invalid("Duplicate or invalid terminal ID/alias")
        ids.add(terminal_id); aliases.add(alias.upper())
    if _static_resource_conflict(record["terminals"]):
        invalid("Duplicate persisted native-resource bindings")
    operations = record.get("operations")
    if not isinstance(operations, dict):
        invalid("Invalid operation index")
    for operation_id, entry in operations.items():
        if not isinstance(operation_id, str) or not operation_id or not isinstance(entry, dict):
            invalid("Invalid operation receipt")
        if not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("request_sha256", ""))):
            invalid("Invalid operation request hash")
        receipt = entry.get("receipt")
        if not isinstance(receipt, dict) or not _positive(receipt.get("identity_revision")) or receipt["identity_revision"] > record["identity_revision"]:
            invalid("Invalid operation receipt revision")
        _validate_terminal(receipt.get("terminal"))
        if receipt.get("device_id") != record["device_id"] or receipt["terminal"]["terminal_id"] not in ids:
            invalid("Invalid operation receipt binding")
        current = next(row for row in record["terminals"] if row["terminal_id"] == receipt["terminal"]["terminal_id"])
        if receipt["terminal"]["terminal_generation"] > current["terminal_generation"]:
            invalid("Receipt generation exceeds current binding")


class IdentityRegistry:
    def __init__(self, root: Path):
        self.path = Path(root) / "state" / "fleet" / "identity.json"
        self.lock = self.path.with_suffix(".lock")

    def load(self) -> dict | None:
        try:
            record = _read_json_object(self.path)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as exc:
            raise IdentityError("IDENTITY_INVALID", "Registry is unreadable; restore it explicitly") from exc
        try:
            _validate_registry(record)
        except (ValueError, TypeError, AttributeError) as exc:
            raise IdentityError("IDENTITY_INVALID", "Malformed registry") from exc
        return record

    def bootstrap(self, terminals, *, expected_revision: int | None = None) -> dict:
        terminals = list(terminals)
        resources = inspect_resources(terminals)
        if any(row["conflicts"] for row in resources.values()):
            raise IdentityError("RESOURCE_CONFLICT", "Proposed bindings share native resources")
        if not terminals:
            raise IdentityError("IDENTITY_INVALID", "Enrollment needs at least one terminal")
        for terminal in terminals:
            if not isinstance(terminal.alias, str) or not terminal.alias.strip() or terminal.alias != terminal.alias.strip() or type(terminal.enabled) is not bool:
                raise IdentityError("IDENTITY_INVALID", "Invalid alias/enabled observation")
        with _exclusive_file_lock(self.lock):
            record = self.load()
            if record is None:
                if expected_revision is not None and (type(expected_revision) is not int or expected_revision != 0):
                    raise IdentityError("IDENTITY_REVISION_CONFLICT", "Registry is not enrolled")
                record = {"schema": SCHEMA, "device_id": "dev_" + uuid.uuid4().hex,
                          "identity_revision": 1, "terminals": [], "operations": {}}
            else:
                if expected_revision is not None and (not _positive(expected_revision) or expected_revision != record["identity_revision"]):
                    raise IdentityError("IDENTITY_REVISION_CONFLICT", "Stale identity revision")
                pending = []
                by_alias = {row["alias"].upper(): row for row in record["terminals"]}
                for terminal in terminals:
                    current = by_alias.get(terminal.alias.upper())
                    if current is not None:
                        if current["binding"] != binding_for(terminal) or current["enabled"] != terminal.enabled:
                            raise IdentityError("TARGET_MISMATCH", "Explicit binding/enabled update required")
                    else:
                        pending.append(terminal)
                if not pending:
                    return record
                if not _positive(expected_revision) or expected_revision != record["identity_revision"]:
                    raise IdentityError("IDENTITY_REVISION_CONFLICT", "New enrollment requires current identity revision")
                terminals = pending
                record["identity_revision"] += 1
            for terminal in terminals:
                record["terminals"].append({"terminal_id": "term_" + uuid.uuid4().hex,
                    "alias": terminal.alias, "binding": binding_for(terminal),
                    "terminal_generation": 1, "enabled": terminal.enabled})
            self._check_record_resources(record)
            _validate_registry(record)
            _atomic_write_json(self.path, record)
            return record

    @staticmethod
    def _check_record_resources(record):
        observed = inspect_resources(SimpleNamespace(alias=row["alias"],
            terminal_path=row["binding"]["terminal_path"], data_root=row["binding"]["data_root"])
            for row in record["terminals"])
        if any(row["conflicts"] for row in observed.values()):
            raise IdentityError("RESOURCE_CONFLICT", "Enrolled bindings share native resources")
        if _static_resource_conflict(record["terminals"]):
            raise IdentityError("RESOURCE_CONFLICT", "Enrolled bindings share native resources")

    def update(self, terminal_id: str, *, expected_revision: int, operation_id: str,
               alias: str | None = None, terminal_path: str | None = None,
               data_root: str | None = None, enabled: bool | None = None) -> dict:
        if not _positive(expected_revision) or not isinstance(operation_id, str) or not operation_id.strip():
            raise IdentityError("IDENTITY_INVALID", "Update requires positive revision and operation ID")
        if alias is not None and (not isinstance(alias, str) or not alias.strip() or alias != alias.strip()):
            raise IdentityError("IDENTITY_INVALID", "Invalid alias")
        if enabled is not None and type(enabled) is not bool:
            raise IdentityError("IDENTITY_INVALID", "Enabled must be boolean")
        if (terminal_path is None) != (data_root is None):
            raise IdentityError("IDENTITY_INVALID", "Replacement needs executable and data root together")
        requested_binding = None
        if terminal_path is not None:
            requested_binding = {"terminal_path": normalize_path(terminal_path), "data_root": normalize_path(data_root)}
        request = {"terminal_id": terminal_id, "expected_revision": expected_revision,
                   "alias": alias, "binding": requested_binding, "enabled": enabled}
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with _exclusive_file_lock(self.lock):
            record = self.load()
            if record is None:
                raise IdentityError("IDENTITY_UNENROLLED", "Bootstrap identity first")
            prior = record["operations"].get(operation_id)
            if prior:
                if prior["request_sha256"] != digest:
                    raise IdentityError("IDENTITY_OPERATION_CONFLICT", "Operation ID has different inputs")
                return {**prior["receipt"], "idempotent_recovered": True}
            if expected_revision != record["identity_revision"]:
                raise IdentityError("IDENTITY_REVISION_CONFLICT", "Stale identity revision")
            row = next((row for row in record["terminals"] if row["terminal_id"] == terminal_id), None)
            if row is None:
                raise IdentityError("TARGET_UNKNOWN", "Unknown enrolled terminal ID")
            before = copy.deepcopy(row)
            proposed_binding = None
            if requested_binding is not None:
                exe = _observation(terminal_path, directory=False)
                data = _observation(data_root, directory=True)
                proposed_binding = {**requested_binding, "terminal_canonical_path": exe["canonical_path"],
                    "data_canonical_path": data["canonical_path"]}
            if alias is not None:
                row["alias"] = alias
            if proposed_binding is not None and proposed_binding != row["binding"]:
                row["binding"] = proposed_binding
                row["terminal_generation"] += 1
            if enabled is not None:
                row["enabled"] = enabled
            if row == before and all(value is None for value in (alias, proposed_binding, enabled)):
                raise IdentityError("IDENTITY_INVALID", "Empty update")
            record["identity_revision"] += 1
            self._check_record_resources(record)
            receipt = {"device_id": record["device_id"], "identity_revision": record["identity_revision"], "terminal": copy.deepcopy(row)}
            record["operations"][operation_id] = {"request_sha256": digest, "receipt": receipt}
            _validate_registry(record)
            _atomic_write_json(self.path, record)
            return {**receipt, "idempotent_recovered": False}

    def overlay(self, terminals) -> dict[str, dict]:
        terminals = list(terminals)
        try:
            resources = inspect_resources(terminals)
            resource_error = None
        except IdentityError as exc:
            resources = {terminal.alias.upper(): {"conflicts": [], "qualified": False} for terminal in terminals}
            resource_error = "RESOURCE_CONFLICT" if exc.code == "RESOURCE_CONFLICT" else "INVALID"
        try:
            record = self.load()
            status = "ENROLLED" if record else "UNENROLLED"
        except IdentityError:
            record, status = None, "INVALID"
        by_alias = {row["alias"].upper(): row for row in record["terminals"]} if record else {}
        out = {}
        for terminal in terminals:
            key = terminal.alias.upper()
            row = by_alias.get(key)
            row_status = status if record is None else "UNENROLLED"
            if row and not resource_error:
                actual = binding_for(terminal)
                binding = row["binding"]
                mismatch = any(binding[field] != actual[field] for field in ("terminal_path", "data_root"))
                mismatch |= any(binding[field] is not None and binding[field] != actual[field]
                                for field in ("terminal_canonical_path", "data_canonical_path"))
                row_status = "TARGET_MISMATCH" if mismatch else "ENROLLED"
                if row_status == "ENROLLED" and (not row["enabled"] or not terminal.enabled):
                    row_status = "DISABLED"
            resource = resources[key]
            if resource["conflicts"]:
                row_status = "RESOURCE_CONFLICT"
            if resource_error:
                row_status = resource_error
                row = None
            qualified = resource["qualified"] and row is not None and all(
                row["binding"][field] is not None for field in ("terminal_canonical_path", "data_canonical_path"))
            out[key] = {"device_id": record["device_id"] if row else None,
                "terminal_id": row["terminal_id"] if row else None,
                "terminal_generation": row["terminal_generation"] if row else None,
                "identity_revision": record["identity_revision"] if record else None,
                "identity_status": row_status, "identity_source": SOURCE if row else None,
                "resource_qualification": "QUALIFIED" if qualified and not resource["conflicts"] and row_status == "ENROLLED" else "UNQUALIFIED",
                "resource_conflicts": resource["conflicts"], "routed_native_enabled": False}
        return out
