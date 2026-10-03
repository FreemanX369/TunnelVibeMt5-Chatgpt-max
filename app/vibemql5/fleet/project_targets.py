"""Node-owned placement overlay over existing immutable project/session revisions."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import os
from pathlib import Path

from ..core.jobs import _atomic_write_json, _exclusive_file_lock
from ..core.project_sessions import ProjectSessionManager
from ..core.revisions import RevisionManager
from ..core.inventory import TerminalInventory
from .identity import IdentityRegistry, IdentityError
from .reads import _target, _inventory_rows
from .targets import validate_local_target
from .wire import encode_body, decode_body, WireError
from .identity import normalize_path


class FleetProjectError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    try:
        return encode_body(value, 262144)
    except (WireError, ValueError, TypeError, UnicodeError, RecursionError):
        raise FleetProjectError("FLEET_INPUT_INVALID") from None


def read_blob(path, maximum=262144):
    path = Path(path)
    if any(part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400) for part in (path, *path.parents)):
        raise FleetProjectError("FLEET_STATE_INVALID")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > maximum: raise FleetProjectError("FLEET_STATE_INVALID")
        body = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    metadata = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if len(body) > maximum or metadata(before) != metadata(after) or metadata(after) != metadata(path.stat()):
        raise FleetProjectError("FLEET_STATE_INVALID")
    return body


def read_record(path):
    """Bound reads before decoding; duplicate keys and malformed trees are invalid."""
    try:
        return decode_body(read_blob(path), 262144)
    except WireError:
        raise FleetProjectError("FLEET_STATE_INVALID") from None


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _relative(value):
    return (isinstance(value, str) and 0 < len(value) <= 512 and not value.startswith(("/", "\\"))
            and ":" not in value and not any(ord(c) < 32 for c in value)
            and all(part not in {"", ".", ".."} for part in value.replace("\\", "/").split("/")))


def _validate_session(session):
    if type(session) is not dict or set(session) != {"revision_id", "revision_sha256", "workspace", "ea", "checkpoint_id", "source_sha256", "source_bytes"}: raise ValueError()
    if re.fullmatch(r"REV-[0-9]{6}", session["revision_id"]) is None or not _sha(session["revision_sha256"]) or not _sha(session["source_sha256"]): raise ValueError()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", session["workspace"]) is None or not _relative(session["ea"]): raise ValueError()
    if not _relative(session["checkpoint_id"]) or "/" in session["checkpoint_id"] or "\\" in session["checkpoint_id"]: raise ValueError()
    if type(session["source_bytes"]) is not int or not 0 <= session["source_bytes"] <= (1 << 63) - 1: raise ValueError()


def validate_record(value):
    try:
        canonical(value)
        if not isinstance(value, dict): raise ValueError()
        common = {"schema", "project_id", "owner_device_id", "placement_revision", "session", "strict_baseline", "record_sha256"}
        if value.get("schema") == "fleet.project/1":
            fields = common | {"default_target", "enrollment_operation", "enrollment_request_sha256", "default_operations", "session_operations"}
            identifier(value["enrollment_operation"])
            if not _sha(value["enrollment_request_sha256"]): raise ValueError()
            operations = value["default_operations"]
            if type(operations) is not dict or len(operations) > 256: raise ValueError()
            for operation_id, operation in operations.items():
                identifier(operation_id)
                if type(operation) is not dict or set(operation) != {"request_sha256", "receipt"} or not _sha(operation["request_sha256"]): raise ValueError()
                receipt = operation["receipt"]
                if type(receipt) is not dict or set(receipt) != {"project_id", "placement_revision", "default_target"}: raise ValueError()
                if receipt["project_id"] != value["project_id"] or type(receipt["placement_revision"]) is not int or not 2 <= receipt["placement_revision"] <= value["placement_revision"]: raise ValueError()
                if receipt["default_target"] is not None: exact_target(receipt["default_target"])
            session_operations = value["session_operations"]
            if type(session_operations) is not dict or len(session_operations) > 256: raise ValueError()
            for operation_id, operation in session_operations.items():
                identifier(operation_id)
                if type(operation) is not dict or set(operation) != {"request_sha256", "receipt"} or not _sha(operation["request_sha256"]): raise ValueError()
                receipt = operation["receipt"]
                if type(receipt) is not dict or set(receipt) != {"project_id", "placement_revision", "session"} or receipt["project_id"] != value["project_id"] or type(receipt["placement_revision"]) is not int or not 2 <= receipt["placement_revision"] <= value["placement_revision"]: raise ValueError()
                _validate_session(receipt["session"])
            if value["default_target"] is not None: exact_target(value["default_target"])
        elif value.get("schema") == "fleet.placement/1":
            fields = common | {"frozen_id", "target", "binding", "writer", "request_sha256"}
            identifier(value["frozen_id"])
            target = exact_target(value["target"])
            if target["device_id"] != value["owner_device_id"] or not _sha(value["request_sha256"]): raise ValueError()
            binding, writer = value["binding"], value["writer"]
            if type(binding) is not dict or set(binding) != {"executable", "data_root"} or any(normalize_path(path) != path for path in binding.values()): raise ValueError()
            if type(writer) is not dict or set(writer) != {"writer_id", "authentication"} or writer["authentication"] != "UNVERIFIED_REFERENCE": raise ValueError()
            identifier(writer["writer_id"])
        else: raise ValueError()
        if set(value) != fields or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value["project_id"]) is None: raise ValueError()
        if re.fullmatch(r"dev_[a-f0-9]{32}", value["owner_device_id"]) is None or type(value["placement_revision"]) is not int or not 1 <= value["placement_revision"] <= (1 << 63) - 1: raise ValueError()
        _validate_session(value["session"])
        if value["strict_baseline"] is not None and type(value["strict_baseline"]) is not dict: raise ValueError()
        if not _sha(value["record_sha256"]) or value["record_sha256"] != digest({key: item for key, item in value.items() if key != "record_sha256"}): raise ValueError()
        return value
    except Exception:
        raise FleetProjectError("FLEET_STATE_INVALID") from None


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def identifier(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", value) is None:
        raise FleetProjectError("FLEET_INPUT_INVALID")
    return value


def exact_target(value):
    try:
        return _target(value)
    except (IdentityError, TypeError, ValueError):
        raise FleetProjectError("TARGET_MISMATCH") from None


def resolve_target(root, target):
    target = exact_target(target)
    # Inventory-only projection observes local identity. It never proves current
    # gateway enrollment/route; native effects independently require signed route authorization.
    local = {key: value for key, value in target.items() if key != "route_generation"}
    try:
        resolved = validate_local_target(root, _inventory_rows(root), local, capability="inventory")
    except IdentityError as error:
        raise FleetProjectError(error.code) from None
    except Exception:
        raise FleetProjectError("IDENTITY_INVALID") from None
    return {"executable": resolved["binding"]["terminal_canonical_path"],
            "data_root": resolved["binding"]["data_canonical_path"]}


class FleetProjectStore:
    """Persist placement only; session history, source and checkpoints remain node-owned."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state = self.root / "state" / "fleet" / "projects"
        self.sessions = ProjectSessionManager(self.root)
        self.revisions = RevisionManager(self.root)

    def _path(self, project_id):
        if not isinstance(project_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", project_id) is None:
            raise FleetProjectError("FLEET_INPUT_INVALID")
        return self.state / (project_id + ".json")

    def _load(self, path):
        try:
            value = validate_record(read_record(path))
            if value["schema"] == "fleet.project/1" and path != self._path(value["project_id"]): raise ValueError()
            if value["schema"] == "fleet.placement/1" and path != self._frozen_path(value["frozen_id"]): raise ValueError()
            return value
        except FileNotFoundError:
            raise FleetProjectError("FLEET_PROJECT_UNBOUND") from None
        except Exception:
            raise FleetProjectError("FLEET_STATE_INVALID") from None

    @staticmethod
    def _publish(path, record):
        record = {key: value for key, value in record.items() if key != "record_sha256"}
        record["record_sha256"] = digest(record)
        validate_record(record)
        _atomic_write_json(path, record)
        return record

    def get(self, project_id):
        return copy.deepcopy(self._load(self._path(project_id)))

    def _revision(self, project_id, revision_id, expected_sha):
        raw = read_blob(self.sessions._revision_path(project_id, revision_id))
        value = decode_body(raw, 262144)
        if hashlib.sha256(raw).hexdigest() != expected_sha or value.get("schema_version") != self.sessions.schema_version or value.get("project_id") != project_id or value.get("revision_id") != revision_id:
            raise FleetProjectError("FLEET_ARTIFACT_MISSING")
        return value

    def _checkpoint(self, session):
        checkpoint = self.revisions._checkpoint_dir(session["workspace"], session["checkpoint_id"])
        metadata = read_record(checkpoint / "metadata.json")
        raw = read_blob(checkpoint / "source.bin", 64 * 1024 * 1024)
        if metadata.get("checkpoint_id") != session["checkpoint_id"] or metadata.get("workspace") != session["workspace"] or metadata.get("path") != session["ea"] or metadata.get("sha256") != hashlib.sha256(raw).hexdigest() or metadata.get("bytes") != len(raw):
            raise FleetProjectError("FLEET_ARTIFACT_MISSING")
        return metadata

    def _session(self, project_id, revision, sha):
        try:
            pointer = read_record(self.sessions._pointer_path(project_id))
            if pointer.get("schema_version") != self.sessions.schema_version or pointer.get("project_id") != project_id or pointer.get("revision_id") != revision or pointer.get("revision_sha256") != sha:
                raise FleetProjectError("FLEET_SESSION_CONFLICT")
            session = self._revision(project_id, revision, sha)
            source = self.revisions.workspace.resolve(session["workspace"], session["ea"], must_exist=True)
            raw = read_blob(source, 64 * 1024 * 1024)
            snapshot = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            metadata = self._checkpoint(session)
            if read_record(self.sessions._pointer_path(project_id)) != pointer: raise FleetProjectError("FLEET_SESSION_CONFLICT")
            if metadata["path"] != session["ea"] or any(
                    snapshot[key] != session["source_" + key] or metadata[key] != snapshot[key]
                    for key in ("sha256", "bytes")):
                raise FleetProjectError("FLEET_SOURCE_CHANGED")
            return {"revision_id": revision, "revision_sha256": sha,
                "workspace": session["workspace"], "ea": session["ea"],
                "checkpoint_id": session["checkpoint_id"], "source_sha256": snapshot["sha256"],
                "source_bytes": snapshot["bytes"]}
        except FleetProjectError:
            raise
        except Exception:
            raise FleetProjectError("FLEET_ARTIFACT_MISSING") from None

    def _owner(self, owner):
        try:
            registry = IdentityRegistry(self.root).load()
            if registry is None or registry["device_id"] != owner:
                raise FleetProjectError("FLEET_SAME_NODE_REQUIRED")
        except FleetProjectError:
            raise
        except Exception:
            raise FleetProjectError("IDENTITY_INVALID") from None

    def enroll(self, project_id, owner_device_id, *, expected_session_revision,
               expected_session_sha256, operation_id, default_target=None, strict_baseline=None):
        path = self._path(project_id)
        operation_id = identifier(operation_id)
        target = None if default_target is None else exact_target(default_target)
        request = {"project_id": project_id, "owner_device_id": owner_device_id,
            "session_revision": expected_session_revision, "session_sha256": expected_session_sha256,
            "default_target": target, "strict_baseline": strict_baseline}
        request_sha = digest(request)
        with _exclusive_file_lock(path.with_suffix(".lock")):
            if path.exists():
                prior = self._load(path)
                if prior.get("enrollment_operation") == operation_id and prior.get("enrollment_request_sha256") == request_sha:
                    return {**prior, "idempotent_recovered": True}
                raise FleetProjectError("FLEET_OPERATION_CONFLICT")
            self._owner(owner_device_id)
            if target is not None:
                if target["device_id"] != owner_device_id:
                    raise FleetProjectError("FLEET_SAME_NODE_REQUIRED")
                resolve_target(self.root, target)
            session = self._session(project_id, expected_session_revision, expected_session_sha256)
            record = {"schema": "fleet.project/1", "project_id": project_id, "owner_device_id": owner_device_id,
                "placement_revision": 1, "session": session, "default_target": target,
                "strict_baseline": strict_baseline, "enrollment_operation": operation_id,
                "enrollment_request_sha256": request_sha, "default_operations": {}, "session_operations": {}}
            record = self._publish(path, record)
            return {**record, "idempotent_recovered": False}

    def set_default(self, project_id, target, *, expected_placement_revision, operation_id):
        target = None if target is None else exact_target(target)
        operation_id = identifier(operation_id)
        path = self._path(project_id)
        request_sha = digest({"project_id": project_id, "target": target, "expected_revision": expected_placement_revision})
        with _exclusive_file_lock(path.with_suffix(".lock")):
            record = self._load(path)
            prior = record["default_operations"].get(operation_id)
            if prior:
                if prior["request_sha256"] != request_sha:
                    raise FleetProjectError("FLEET_OPERATION_CONFLICT")
                return {**prior["receipt"], "idempotent_recovered": True}
            if len(record["default_operations"]) >= 256: raise FleetProjectError("FLEET_OPERATION_CAPACITY")
            if type(expected_placement_revision) is not int or record["placement_revision"] != expected_placement_revision:
                raise FleetProjectError("FLEET_PLACEMENT_CONFLICT")
            self._owner(record["owner_device_id"])
            if target is not None:
                if target["device_id"] != record["owner_device_id"]:
                    raise FleetProjectError("FLEET_SAME_NODE_REQUIRED")
                resolve_target(self.root, target)
            record["placement_revision"] += 1
            record["default_target"] = target
            receipt = {key: copy.deepcopy(record[key]) for key in ("project_id", "placement_revision", "default_target")}
            record["default_operations"][operation_id] = {"request_sha256": request_sha, "receipt": receipt}
            self._publish(path, record)
            return {**receipt, "idempotent_recovered": False}

    def advance_session(self, project_id, *, expected_placement_revision, expected_session_revision,
                        expected_session_sha256, new_session_revision, new_session_sha256, operation_id):
        """Advance only the placement overlay after an existing immutable session commit."""
        operation_id = identifier(operation_id)
        path = self._path(project_id)
        request_sha = digest({"project_id": project_id, "expected_placement_revision": expected_placement_revision,
            "expected_session_revision": expected_session_revision, "expected_session_sha256": expected_session_sha256,
            "new_session_revision": new_session_revision, "new_session_sha256": new_session_sha256})
        with _exclusive_file_lock(path.with_suffix(".lock")):
            record = self._load(path)
            prior = record["session_operations"].get(operation_id)
            if prior:
                if prior["request_sha256"] != request_sha: raise FleetProjectError("FLEET_OPERATION_CONFLICT")
                return {**prior["receipt"], "idempotent_recovered": True}
            if len(record["session_operations"]) >= 256: raise FleetProjectError("FLEET_OPERATION_CAPACITY")
            if type(expected_placement_revision) is not int or record["placement_revision"] != expected_placement_revision: raise FleetProjectError("FLEET_PLACEMENT_CONFLICT")
            if record["session"]["revision_id"] != expected_session_revision or record["session"]["revision_sha256"] != expected_session_sha256: raise FleetProjectError("FLEET_SESSION_CONFLICT")
            self._owner(record["owner_device_id"])
            new_session = self._session(project_id, new_session_revision, new_session_sha256)
            if (new_session["workspace"], new_session["ea"]) != (record["session"]["workspace"], record["session"]["ea"]): raise FleetProjectError("FLEET_SAME_NODE_REQUIRED")
            record["placement_revision"] += 1
            record["session"] = new_session
            receipt = {key: copy.deepcopy(record[key]) for key in ("project_id", "placement_revision", "session")}
            record["session_operations"][operation_id] = {"request_sha256": request_sha, "receipt": receipt}
            self._publish(path, record)
            return {**receipt, "idempotent_recovered": False}

    def _frozen_path(self, frozen_id):
        return self.root / "state" / "fleet" / "placements" / (hashlib.sha256(identifier(frozen_id).encode()).hexdigest() + ".json")

    def freeze(self, project_id, frozen_id, *, writer_id, expected_placement_revision,
               expected_session_revision, expected_session_sha256, operation_id, target=None):
        operation_id, writer_id = identifier(operation_id), identifier(writer_id)
        explicit = None if target is None else exact_target(target)
        request = {"project_id": project_id, "frozen_id": identifier(frozen_id), "writer_id": writer_id,
            "placement_revision": expected_placement_revision, "session_revision": expected_session_revision,
            "session_sha256": expected_session_sha256, "explicit_target": explicit, "operation_id": operation_id}
        request_sha = digest(request)
        path, project_path = self._frozen_path(frozen_id), self._path(project_id)
        with _exclusive_file_lock(project_path.with_suffix(".lock")), _exclusive_file_lock(path.with_suffix(".lock")):
            if path.exists():
                frozen = self._load(path)
                if frozen.get("request_sha256") != request_sha:
                    raise FleetProjectError("FLEET_FROZEN_CONFLICT")
                return {**frozen, "idempotent_recovered": True}
            project = self._load(project_path)
            if type(expected_placement_revision) is not int or project["placement_revision"] != expected_placement_revision:
                raise FleetProjectError("FLEET_PLACEMENT_CONFLICT")
            chosen = explicit if explicit is not None else project["default_target"]
            if chosen is None:
                raise FleetProjectError("FLEET_TARGET_REQUIRED")
            self._owner(project["owner_device_id"])
            if chosen["device_id"] != project["owner_device_id"]:
                raise FleetProjectError("FLEET_SAME_NODE_REQUIRED")
            binding = resolve_target(self.root, chosen)
            session = self._session(project_id, expected_session_revision, expected_session_sha256)
            frozen = {"schema": "fleet.placement/1", "frozen_id": frozen_id, "project_id": project_id,
                "owner_device_id": project["owner_device_id"], "target": chosen, "binding": binding,
                "placement_revision": project["placement_revision"], "session": session,
                "writer": {"writer_id": writer_id, "authentication": "UNVERIFIED_REFERENCE"},
                "strict_baseline": project["strict_baseline"], "request_sha256": request_sha}
            frozen = self._publish(path, frozen)
            return {**frozen, "idempotent_recovered": False}

    def load_frozen(self, frozen_id):
        return copy.deepcopy(self._load(self._frozen_path(frozen_id)))

    def validate_frozen(self, frozen):
        if type(frozen) is not dict: raise FleetProjectError("FLEET_STATE_INVALID")
        validate_record({key: value for key, value in frozen.items() if key != "idempotent_recovered"})
        stored = self.load_frozen(frozen["frozen_id"])
        supplied = {key: value for key, value in frozen.items() if key != "idempotent_recovered"}
        if supplied != stored:
            raise FleetProjectError("FLEET_FROZEN_CONFLICT")
        self._owner(stored["owner_device_id"])
        if resolve_target(self.root, stored["target"]) != stored["binding"]:
            raise FleetProjectError("FLEET_BINDING_DRIFT")
        session = stored["session"]
        self._session(stored["project_id"], session["revision_id"], session["revision_sha256"])
        return stored

    def _validate_frozen_history(self, frozen):
        """Internal immutable history check after the native controller pins inputs."""
        validate_record(frozen)
        stored = self.load_frozen(frozen["frozen_id"])
        if frozen != stored: raise FleetProjectError("FLEET_FROZEN_CONFLICT")
        self._owner(stored["owner_device_id"])
        if resolve_target(self.root, stored["target"]) != stored["binding"]: raise FleetProjectError("FLEET_BINDING_DRIFT")
        session = stored["session"]
        try:
            revision = self._revision(stored["project_id"], session["revision_id"], session["revision_sha256"])
            if any(revision[key] != session[key] for key in ("workspace", "ea", "checkpoint_id", "source_sha256", "source_bytes")): raise ValueError()
            metadata = self._checkpoint(session)
            if metadata["sha256"] != session["source_sha256"] or metadata["bytes"] != session["source_bytes"]: raise ValueError()
        except Exception: raise FleetProjectError("FLEET_ARTIFACT_MISSING") from None
        return stored

    def resume(self, frozen_id):
        try:
            frozen = self.load_frozen(frozen_id)
            self.validate_frozen(frozen)
            return {"status": "FROZEN_SOURCE_VERIFIED", "placement": frozen,
                    "native_qualification": "UNQUALIFIED", "execution": "UNRESOLVED"}
        except FleetProjectError as error:
            return {"status": error.code, "placement": None, "native_qualification": "UNQUALIFIED",
                    "execution": "UNRESOLVED"}

    @staticmethod
    def legacy_binding(_legacy_job):
        return {"status": "UNVERIFIED_LEGACY_UNBOUND", "target": None, "observed_binding": None}
