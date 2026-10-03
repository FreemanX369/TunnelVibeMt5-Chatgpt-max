"""Frozen routed native jobs behind installed signed physical qualification.

Harmless fixtures use an explicit separate adapter; they never install qualification.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import math
import threading
import os
from types import MappingProxyType
from contextlib import contextmanager
from functools import wraps
from datetime import datetime
from pathlib import Path

from ..core.concurrency import ConcurrencyManager
from ..core.jobs import JobStore, _atomic_write_json, _exclusive_file_lock, new_job_id, _JOB_ID_RE
from ..core.native_ownership import OwnershipAuthority, _identity_valid
from ..core.tester_config import normalize_tester_request
from .project_targets import FleetProjectError, FleetProjectStore, canonical, digest, identifier, read_record, read_blob, validate_record
from .native_qualification import load_installation, QualificationError
from .native_authorization import NativeAuthorization
from .resources import ResourceAuthority
from .scoped_resources import ScopedResourceCoordinator, ScopedLease
from .identity import IdentityRegistry, normalize_path
from ..core.inventory import TerminalInventory
from ..core.compiler import CompilerDriver
from ..core.tester import TesterDriver
from .native_process import OwnedWindowsLaunch, assert_installation_idle

MAX_INPUT_FILES = 1024
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024

PHASES = {"deploy", "start", "test", "capture", "cancel", "result"}


class NativeRouteError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


_INPUT_SEAL = object()


class _PinnedInputs:
    def __init__(self, request_sha256, placement_sha256, values, seal):
        if seal is not _INPUT_SEAL: raise NativeRouteError("NATIVE_INPUT_CHANGED")
        self.request_sha256, self.placement_sha256 = request_sha256, placement_sha256
        self.values = MappingProxyType(dict(values))


def _bounded_native(function):
    @wraps(function)
    def bounded(*args, **kwargs):
        try: return function(*args, **kwargs)
        except (NativeRouteError, FleetProjectError): raise
        except TimeoutError: raise NativeRouteError("NATIVE_LEASE_UNAVAILABLE") from None
        except Exception: raise NativeRouteError("NATIVE_RECOVERY_REQUIRED") from None
    return bounded


def _logical(value):
    try:
        if type(value) is not dict or set(value) != {"config", "normalization"}: raise ValueError()
        config, norm = value["config"], value["normalization"]
        fields = {"symbol", "period", "model", "from_date", "to_date", "deposit", "currency", "leverage", "visual"}
        if type(config) is not dict or set(config) not in (fields, fields | {"execution_delay_ms"}): raise ValueError()
        for key in ("symbol", "period", "currency"):
            if type(config[key]) is not str or not config[key] or config[key] != config[key].strip() or len(config[key]) > 64 or any(ord(c) < 32 or c in "[]=;" for c in config[key]): raise ValueError()
        if type(config["model"]) is not int or config["model"] not in range(5) or type(config["visual"]) is not bool: raise ValueError()
        if type(config["deposit"]) not in (int, float) or not math.isfinite(config["deposit"]) or config["deposit"] <= 0: raise ValueError()
        leverage = config["leverage"]
        if type(leverage) not in (int, str) or re.fullmatch(r"[1-9][0-9]{0,8}(?::[1-9][0-9]{0,8})?", str(leverage)) is None: raise ValueError()
        if "execution_delay_ms" in config and (type(config["execution_delay_ms"]) is not int or not -1 <= config["execution_delay_ms"] <= 600000): raise ValueError()
        if type(norm) is not dict or set(norm) != {"requested_period", "effective_period", "current_date", "future_to_date_clamped", "execution_delay"}: raise ValueError()
        dates = {}
        for key in ("requested_period", "effective_period"):
            period = norm[key]
            if type(period) is not dict or set(period) != {"from_date", "to_date"}: raise ValueError()
            dates[key] = [datetime.strptime(period[k], "%Y.%m.%d").date() for k in ("from_date", "to_date")]
            if dates[key][0] > dates[key][1] or any(re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", v) is None for v in period.values()): raise ValueError()
        current = datetime.strptime(norm["current_date"], "%Y.%m.%d").date()
        if norm["effective_period"] != {"from_date": config["from_date"], "to_date": config["to_date"]} or dates["effective_period"] != [dates["requested_period"][0], min(dates["requested_period"][1], current)]: raise ValueError()
        if type(norm["future_to_date_clamped"]) is not bool or norm["future_to_date_clamped"] != (dates["requested_period"][1] > current): raise ValueError()
        delay = config.get("execution_delay_ms")
        expected = {"specified": "execution_delay_ms" in config, "execution_mode": delay,
            "mode": "RANDOM" if delay == -1 else "NO_DELAY" if delay == 0 else "FIXED_MS" if delay is not None else "TERMINAL_DEFAULT"}
        if norm["execution_delay"] != expected: raise ValueError()
        canonical(value)
        return value
    except Exception:
        raise NativeRouteError("NATIVE_REQUEST_INVALID") from None


def native_request(placement, logical_config, input_manifest, build_policy="STRICT"):
    if type(placement) is not dict or placement.get("schema") != "fleet.placement/1" or build_policy != "STRICT":
        raise NativeRouteError("NATIVE_REQUEST_INVALID")
    _logical(logical_config)
    if not isinstance(input_manifest, list) or not 1 <= len(input_manifest) <= MAX_INPUT_FILES:
        raise NativeRouteError("NATIVE_REQUEST_INVALID")
    manifests = []
    for item in input_manifest:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}
                or not isinstance(item["path"], str) or not item["path"] or item["path"].startswith(("/", "\\"))
                or any(part in {"", ".", ".."} for part in item["path"].replace("\\", "/").split("/"))
                or ":" in item["path"] or "\0" in item["path"]
                or not isinstance(item["sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) is None
                or type(item["bytes"]) is not int or not 0 <= item["bytes"] <= MAX_FILE_BYTES):
            raise NativeRouteError("NATIVE_REQUEST_INVALID")
        normalized_item = copy.deepcopy(item)
        normalized_item["path"] = normalized_item["path"].replace("\\", "/")
        manifests.append(normalized_item)
    if sum(item["bytes"] for item in manifests) > MAX_INPUT_BYTES: raise NativeRouteError("NATIVE_REQUEST_INVALID")
    if len({item["path"].replace("\\", "/").casefold() for item in manifests}) != len(manifests):
        raise NativeRouteError("NATIVE_REQUEST_INVALID")
    manifests.sort(key=lambda item: item["path"].casefold())
    frozen = {key: copy.deepcopy(value) for key, value in placement.items() if key != "idempotent_recovered"}
    request = {"schema": "fleet.native/1", "placement": frozen,
               "logical_config": copy.deepcopy(logical_config), "input_manifest": manifests, "build_policy": build_policy}
    validate_record(frozen)
    canonical(request)
    return request


def native_request_hash(request):
    if not isinstance(request, dict) or set(request) != {"schema", "placement", "logical_config", "input_manifest", "build_policy"}:
        raise NativeRouteError("NATIVE_REQUEST_INVALID")
    if request["schema"] != "fleet.native/1":
        raise NativeRouteError("NATIVE_REQUEST_INVALID")
    normalized = native_request(request["placement"], request["logical_config"], request["input_manifest"], request["build_policy"])
    if normalized != request:
        raise NativeRouteError("NATIVE_REQUEST_INVALID")
    return digest(request)


def request_from_preset(root, placement, preset, input_manifest, *, overrides=None, today=None):
    try:
        config, normalization = normalize_tester_request(Path(root), preset, overrides, today=today)
        return native_request(placement, {"config": config, "normalization": normalization}, input_manifest)
    except (NativeRouteError, FleetProjectError):
        raise
    except Exception:
        raise NativeRouteError("NATIVE_REQUEST_INVALID") from None


class RoutedNativeAdapter:
    """Executable dedicated compiler/tester path, denied until trusted installation.

    The installed operator approval binds actual runtime, source, target roots,
    observed Windows builds and interactive session. Every routed native phase
    independently requires a fresh cryptographically verified gateway grant.
    """
    evidence = "OPERATOR_APPROVED_REAL_NATIVE"

    def __init__(self, root, *, authorization_provider=None):
        self.authorization_provider = authorization_provider
        self._active = {}
        self._pinned = {}
        self._phase_closures = {}
        self._active_guard = threading.RLock()
        self.root = Path(root).resolve()
        self.projects = FleetProjectStore(self.root)
        self.concurrency = ConcurrencyManager(self.root)
        self.jobs = JobStore(self.root)
        self.operations = self.root / "state" / "fleet" / "native-operations"

    def has_retained_work(self):
        """Current owned handles keep the owner loop alive; durable history alone does not."""
        with self._active_guard:
            for active in self._active.values():
                launch = active.get("launch")
                if launch is None: continue
                if any(getattr(launch, field, None) is not None for field in ("process", "thread", "job")):
                    return True
                observed = getattr(launch, "observed", None)
                if observed is not None and getattr(observed, "handle", None) is not None:
                    return True
            return False

    def _admit(self, request, phase, exact_fence=None):
        request_sha = native_request_hash(request)
        pin = self._pinned.get(exact_fence.get("local_job_id")) if type(exact_fence) is dict else None
        if type(pin) is _PinnedInputs:
            if pin.request_sha256 != request_sha or pin.placement_sha256 != request["placement"]["record_sha256"]: raise NativeRouteError("NATIVE_INPUT_CHANGED")
            self.projects._validate_frozen_history(request["placement"])
            self._verify_snapshot(request, exact_fence["local_job_id"], pin)
        else:
            self.projects.validate_frozen(request["placement"])
            self._verify_inputs(request)
        try:
            installation = load_installation(self.root, request)
            if type(exact_fence) is not dict or exact_fence.get("target") != request["placement"]["target"] or exact_fence.get("session_sha256") != request["placement"]["session"]["revision_sha256"]:
                raise NativeRouteError("NATIVE_FENCE_MISMATCH")
            proof = exact_fence.get("authorization")
            trusted = installation.installation
            if type(proof) is not NativeAuthorization or proof.signer_public_key != trusted["gateway_public_key"] or proof.audience != trusted["gateway_audience"]:
                raise NativeRouteError("NATIVE_AUTHORIZATION_UNVERIFIED")
            expected = dict(audience=trusted["gateway_audience"], request_sha256=request_sha, target=request["placement"]["target"],
                phase=phase, node_operation_id=exact_fence["node_operation_id"], global_job_id=exact_fence["global_job_id"],
                local_job_id=exact_fence["local_job_id"], session_id=exact_fence["session_id"],
                sequence=exact_fence["sequence"], challenge=exact_fence["challenge"], event=exact_fence.get("event", "phase_admission"),
                process_sha256=digest(exact_fence["process"]) if phase == "cancel" and _identity_valid(exact_fence.get("process")) else None)
            proof.require(**expected)
            rows = IdentityRegistry(self.root).overlay(TerminalInventory(self.root)._identity_items)
            matches = [alias for alias, row in rows.items() if row.get("terminal_id") == request["placement"]["target"]["terminal_id"]]
            if len(matches) != 1: raise NativeRouteError("NATIVE_BINDING_DRIFT")
            terminal = TerminalInventory(self.root).get(matches[0])
            if normalize_path(terminal.metaeditor_path) != trusted["metaeditor"]:
                raise NativeRouteError("NATIVE_BINDING_DRIFT")
            self._scoped(request, installation)  # Malformed installed scope blocks every effect.
            proof.require(**expected)  # Clock recheck after all file/identity reads.
            return installation, terminal.alias
        except NativeRouteError: raise
        except QualificationError:
            raise NativeRouteError("NATIVE_QUALIFICATION_UNAVAILABLE") from None
        except Exception:
            raise NativeRouteError("NATIVE_AUTHORIZATION_UNVERIFIED") from None

    def _verify_inputs(self, request):
        session = request["placement"]["session"]
        workspace = (self.root / "workspaces" / session["workspace"]).resolve()
        expected = {session["ea"].replace("\\", "/")}
        include = workspace / "Include"
        if include.exists():
            expected.update(path.relative_to(workspace).as_posix() for path in include.rglob("*") if path.is_file())
        supplied = {item["path"].replace("\\", "/"): item for item in request["input_manifest"]}
        sets = [path for path in supplied if path.lower().endswith(".set")]
        if len(sets) > 1 or set(supplied) != expected | set(sets): raise NativeRouteError("NATIVE_INPUT_CHANGED")
        for relative, item in supplied.items():
            try:
                path = workspace / relative
                path.resolve(strict=True).relative_to(workspace)
                if any(part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400) for part in (path, *path.parents)) or not path.is_file() or path.stat().st_size != item["bytes"] or item["bytes"] > MAX_FILE_BYTES: raise ValueError()
                if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]: raise ValueError()
            except Exception:
                raise NativeRouteError("NATIVE_INPUT_CHANGED") from None
        return sets[0] if sets else None

    def _frozen_input_bytes(self, request):
        self._verify_inputs(request)
        root = self.root / "workspaces" / request["placement"]["session"]["workspace"]
        verified = {}
        for item in request["input_manifest"]:
            relative = item["path"].replace("\\", "/")
            path = root / relative
            before = path.stat(follow_symlinks=False)
            if path.is_symlink() or getattr(before, "st_file_attributes", 0) & 0x400: raise NativeRouteError("NATIVE_INPUT_CHANGED")
            with path.open("rb") as stream:
                held_before = os.fstat(stream.fileno())
                raw = stream.read(MAX_FILE_BYTES + 1)
                held_after = os.fstat(stream.fileno())
            after = path.stat(follow_symlinks=False)
            metadata = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
            if metadata(before) != metadata(held_before) or metadata(held_before) != metadata(held_after) or metadata(held_after) != metadata(after) or path.is_symlink(): raise NativeRouteError("NATIVE_INPUT_CHANGED")
            path.resolve(strict=True).relative_to(root.resolve())
            if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise NativeRouteError("NATIVE_INPUT_CHANGED")
            verified[relative] = raw
        return verified

    def _snapshot_receipt(self, request):
        return {"schema": "fleet.native.inputs/1", "request_sha256": native_request_hash(request),
            "placement_sha256": request["placement"]["record_sha256"], "session_sha256": request["placement"]["session"]["revision_sha256"],
            "input_manifest": request["input_manifest"], "input_manifest_sha256": digest(request["input_manifest"])}

    def _publish_snapshot(self, request, local_job_id, values):
        from ..core.workspace import _atomic_write_bytes
        run_dir = self.root / "runs" / local_job_id
        for relative, raw in values.items():
            snapshot = run_dir / "source_snapshot" / relative
            if any(part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400) for part in (snapshot, *snapshot.parents)): raise NativeRouteError("NATIVE_INPUT_CHANGED")
            if snapshot.exists() and (snapshot.stat().st_size != len(raw) or snapshot.read_bytes() != raw): raise NativeRouteError("NATIVE_INPUT_CHANGED")
            if not snapshot.exists(): _atomic_write_bytes(snapshot, raw)
        receipt = self._snapshot_receipt(request)
        _atomic_write_json(run_dir / "input-snapshot.json", receipt)
        if read_record(run_dir / "input-snapshot.json") != receipt: raise NativeRouteError("NATIVE_INPUT_CHANGED")

    def _verify_snapshot(self, request, local_job_id, pin):
        try:
            run_dir = self.root / "runs" / local_job_id
            if read_record(run_dir / "input-snapshot.json") != self._snapshot_receipt(request): raise ValueError()
            for relative, raw in pin.values.items():
                path = run_dir / "source_snapshot" / relative
                if any(part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400) for part in (path, *path.parents)): raise ValueError()
                with path.open("rb") as stream:
                    before = os.fstat(stream.fileno()); observed = stream.read(MAX_FILE_BYTES + 1); after = os.fstat(stream.fileno())
                metadata = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
                if observed != raw or metadata(before) != metadata(after) or metadata(after) != metadata(path.stat()): raise ValueError()
        except Exception: raise NativeRouteError("NATIVE_INPUT_CHANGED") from None

    @contextmanager
    def _source_handoff(self, request, local_job_id, phase, exact_fence):
        session = request["placement"]["session"]
        installation, _alias = self._admit(request, phase, exact_fence)
        with self.concurrency.mutation("fleet_source_guard", resource=session["workspace"] + ":" + session["ea"], wait_seconds=installation.policy["resource_wait_ms"] / 1000):
            installation, _alias = self._admit(request, phase, exact_fence)
            scoped = self._scoped(request, installation)
            if scoped is None:
                yield
                return
            values = self._frozen_input_bytes(request)
            self._publish_snapshot(request, local_job_id, values)
            self._pinned[local_job_id] = _PinnedInputs(native_request_hash(request), request["placement"]["record_sha256"], values, _INPUT_SEAL)
        # The global source guard covers capture only. Immutable bytes and exact
        # original session/checkpoint history remain the candidate after a new writer commits.
        yield

    def _phase_fence(self, phase, request, exact_fence):
        if phase == exact_fence.get("phase", "start"):
            return exact_fence
        provider = self.authorization_provider or exact_fence.get("authorization_provider")
        if not callable(provider): raise NativeRouteError("NATIVE_AUTHORIZATION_UNAVAILABLE")
        if self.authorization_provider is not None:
            updated = provider(phase, {key: value for key, value in exact_fence.items() if key != "authorization"})
        else:
            proof = provider(phase)
            if type(proof) is not NativeAuthorization: raise NativeRouteError("NATIVE_AUTHORIZATION_UNVERIFIED")
            binding = proof.binding
            updated = {**exact_fence, "authorization": proof, "sequence": binding["sequence"], "challenge": binding["challenge"], "event": binding["event"]}
        if type(updated) is not dict: raise NativeRouteError("NATIVE_AUTHORIZATION_UNVERIFIED")
        for field in ("target", "session_sha256", "node_operation_id", "global_job_id", "local_job_id", "session_id"):
            if updated.get(field) != exact_fence.get(field): raise NativeRouteError("NATIVE_FENCE_MISMATCH")
        updated = {**updated, "phase": phase}
        self._admit(request, phase, updated)
        return updated

    def _scoped(self, request, installation):
        marker = self.root / "state" / "fleet" / "scoped-install.json"
        if not marker.exists() and not marker.is_symlink(): return None
        try:
            coordinator = ScopedResourceCoordinator.open_installed(self.root,
                device_id=request["placement"]["owner_device_id"], trusted_owner_public_key=installation.operator_public_key,
                candidate_sha256=installation.candidate_sha256, runtime_sha256=installation.runtime_sha256)
            target = request["placement"]["target"]
            row = next(row for row in coordinator.profile["terminals"] if row["terminal_id"] == target["terminal_id"] and row["terminal_generation"] == target["terminal_generation"])
            expected = {**installation.installation["binding"], "include_root": installation.installation["include_root"], "agent_root": installation.installation["agent_root"]}
            if row["resources"] != expected: raise ValueError()
            return coordinator
        except Exception:
            raise NativeRouteError("NATIVE_SCOPED_QUALIFICATION_UNAVAILABLE") from None

    @contextmanager
    def _execution_lease(self, request, operation_id, phase, exact_fence):
        installation, _alias = self._admit(request, phase, exact_fence)
        scoped = self._scoped(request, installation)
        if scoped is None:
            with self.concurrency.native_execution(operation_id, kind="fleet_" + phase, wait_seconds=0) as lease: yield lease
        else:
            target = request["placement"]["target"]
            with scoped.execution(operation_id, kind="compiler_deploy" if phase in {"reserve", "deploy"} else "capture" if phase in {"capture", "result"} else "tester",
                    terminal_id=target["terminal_id"], terminal_generation=target["terminal_generation"],
                    wait_ms=installation.policy["resource_wait_ms"]) as lease: yield lease

    def _operation_path(self, operation_id):
        return self.operations / (hashlib.sha256(identifier(operation_id).encode()).hexdigest() + ".json")

    @_bounded_native
    def reserve(self, request, node_operation_id, exact_fence=None):
        request_sha = native_request_hash(request)
        path = self._operation_path(node_operation_id)
        # Logical replay is a read of an earlier mapping, never permission to start.
        with _exclusive_file_lock(path.with_suffix(".lock")):
            if path.exists():
                operation = self._read_operation(path)
                if operation["node_operation_id"] != node_operation_id or operation["target"] != request["placement"]["target"] or operation["request_sha256"] != request_sha:
                    raise NativeRouteError("NATIVE_OPERATION_CONFLICT")
                self._materialize(operation, request)
                return {**operation, "idempotent_recovered": True}
            self._admit(request, "reserve", exact_fence)
            with (self.concurrency.native_execution(node_operation_id, kind="fleet_reserve", wait_seconds=0) if isinstance(self, SyntheticNativeAdapter) else self._execution_lease(request, "RESERVE-" + hashlib.sha256(node_operation_id.encode()).hexdigest()[:32], "reserve", exact_fence)):
                self._admit(request, "reserve", exact_fence)
                operation = {"schema": "fleet.native.operation/1", "node_operation_id": node_operation_id,
                    "request_sha256": request_sha, "local_job_id": exact_fence["local_job_id"] if exact_fence is not None else new_job_id(), "target": request["placement"]["target"],
                    "evidence": self.evidence}
                if not _JOB_ID_RE.fullmatch(operation["local_job_id"]): raise NativeRouteError("NATIVE_FENCE_MISMATCH")
                _atomic_write_json(path, operation)  # Mapping before job publication; restart repairs exact same ID.
                self._materialize(operation, request)
                return {**operation, "idempotent_recovered": False}

    def _read_operation(self, path):
        try:
            operation = read_record(path)
            if set(operation) != {"schema", "node_operation_id", "request_sha256", "local_job_id", "target", "evidence"} or operation["schema"] != "fleet.native.operation/1": raise ValueError()
            identifier(operation["node_operation_id"])
            if path != self._operation_path(operation["node_operation_id"]): raise ValueError()
            if re.fullmatch(r"[a-f0-9]{64}", operation["request_sha256"]) is None or _JOB_ID_RE.fullmatch(operation["local_job_id"]) is None: raise ValueError()
            from .project_targets import exact_target
            exact_target(operation["target"])
            if operation["evidence"] != self.evidence: raise ValueError()
            return operation
        except Exception:
            raise NativeRouteError("NATIVE_JOURNAL_INVALID") from None

    def _load_job(self, job_id):
        try:
            if type(job_id) is not str or _JOB_ID_RE.fullmatch(job_id) is None: raise ValueError()
            job = read_record(self.jobs.path(job_id))
            if job.get("job_id") != job_id or job.get("fleet_evidence") != self.evidence or native_request_hash(job["request"]) != job["request_hash"]: raise ValueError()
            identifier(job["operation_id"])
            effects = job.get("fleet_effects")
            if type(effects) is not dict or not set(effects) <= PHASES: raise ValueError()
            for phase, effect in effects.items():
                if effect.get("status") == "PENDING":
                    if set(effect) != {"status", "request_sha256"} or effect["request_sha256"] != job["request_hash"]: raise ValueError()
                elif effect.get("status") == "COMPLETED":
                    if set(effect) != {"status", "receipt"}: raise ValueError()
                    receipt = effect["receipt"]
                    if set(receipt) != {"schema", "local_job_id", "phase", "target", "evidence", "payload"} or receipt["schema"] != "fleet.native.effect/1" or receipt["local_job_id"] != job_id or receipt["phase"] != phase or receipt["target"] != job["request"]["placement"]["target"] or receipt["evidence"] != self.evidence: raise ValueError()
                else: raise ValueError()
            if "fleet_process" in job and not _identity_valid(job["fleet_process"]): raise ValueError()
            return job
        except Exception:
            raise NativeRouteError("NATIVE_JOURNAL_INVALID") from None

    def _materialize(self, operation, request):
        job_id = operation["local_job_id"]
        try:
            if self.jobs.path(job_id).exists():
                raw = read_record(self.jobs.path(job_id))
                if "fleet_evidence" not in raw and "fleet_effects" not in raw and raw.get("request") == request and raw.get("request_hash") == operation["request_sha256"] and raw.get("operation_id") == operation["node_operation_id"]:
                    self.jobs.update_fields(job_id, fleet_evidence=self.evidence, fleet_effects={})
                job = self._load_job(job_id)
                if job["request"] != request or job["request_hash"] != operation["request_sha256"]:
                    raise NativeRouteError("NATIVE_JOURNAL_INVALID")
            else:
                self.jobs.create_reserved(job_id, request, operation["node_operation_id"], operation["request_sha256"])
                self.jobs.update_fields(job_id, fleet_evidence=self.evidence, fleet_effects={})
        except NativeRouteError:
            raise
        except Exception:
            raise NativeRouteError("NATIVE_RESERVATION_UNCERTAIN") from None

    def start_reserved(self, local_job_id, request, exact_fence):
        return self.effect(local_job_id, "start", request, exact_fence)

    @_bounded_native
    def effect(self, local_job_id, phase, request, exact_fence):
        if type(phase) is not str or phase not in PHASES:
            raise NativeRouteError("NATIVE_REQUEST_INVALID")
        self._admit(request, phase, exact_fence)  # Production denies before callback/job restoration/IPC.
        if isinstance(self, SyntheticNativeAdapter):
            result = self._synthetic_effect(local_job_id, phase, request, exact_fence)
        else:
            result = self._qualified_effect(local_job_id, phase, request, exact_fence)
        # The native/source context managers have returned successfully here.
        # This historical receipt is not permission to enter a current authority.
        rows = self._phase_closures.pop(local_job_id, None)
        if rows and phase in {"deploy", "start", "test", "result"}:
            receipt = {"schema": "fleet.native.closure/1", "local_job_id": local_job_id,
                "request_sha256": native_request_hash(request), "target": request["placement"]["target"],
                "evidence": self.evidence, "phases": rows, "lease_release": "RETURNED"}
            self.jobs.update_fields(local_job_id, fleet_terminal_closure={"receipt": receipt, "sha256": digest(receipt)})
        return result

    def terminal_closure(self, local_job_id, request):
        """Read an exact completed historical closure; never acquire/clear ownership."""
        try:
            job = self._load_job(local_job_id)
            if job["request"] != request or job["request_hash"] != native_request_hash(request): raise ValueError()
            with self._active_guard:
                if local_job_id in self._active: raise ValueError()
            effects = job["fleet_effects"]
            if any(row["status"] != "COMPLETED" for row in effects.values()) or not effects: raise ValueError()
            stored = job["fleet_terminal_closure"]
            if type(stored) is not dict or set(stored) != {"receipt", "sha256"} or stored["sha256"] != digest(stored["receipt"]): raise ValueError()
            receipt = stored["receipt"]
            if type(receipt) is not dict or set(receipt) != {"schema", "local_job_id", "request_sha256", "target", "evidence", "phases", "lease_release"}: raise ValueError()
            if receipt["schema"] != "fleet.native.closure/1" or receipt["local_job_id"] != local_job_id or receipt["request_sha256"] != job["request_hash"] or receipt["target"] != request["placement"]["target"] or receipt["evidence"] != self.evidence or receipt["lease_release"] != "RETURNED": raise ValueError()
            if type(receipt["phases"]) is not list or not 1 <= len(receipt["phases"]) <= 2: raise ValueError()
            for row in receipt["phases"]:
                if type(row) is not dict or set(row) != {"phase", "ownership_record", "process", "descendants"} or row["phase"] not in PHASES: raise ValueError()
                authority = row["ownership_record"]
                if type(authority) is not dict or authority.get("phase") != "CLOSED" or authority.get("worker") is not None or authority.get("descendants") != "NONE" or type(authority.get("generation")) is not int or authority["generation"] < 1 or type(authority.get("epoch")) is not str or not authority["epoch"].strip(): raise ValueError()
                if authority.get("schema") == "native.ownership/1":
                    if authority.get("disposition") != "CLOSED" or any(authority.get(field) != "" for field in ("token", "operation_id", "kind")) or authority.get("parent") is not None: raise ValueError()
                elif authority.get("schema") == "fleet.scoped-ownership/1":
                    scoped = authority.get("request")
                    if authority.get("status") not in {"ACQUIRED", "RELEASED"} or type(scoped) is not dict or scoped.get("terminal_id") != receipt["target"]["terminal_id"] or scoped.get("terminal_generation") != receipt["target"]["terminal_generation"] or not _identity_valid(authority.get("parent")): raise ValueError()
                else: raise ValueError()
                if row["process"] is None:
                    if row["descendants"] != "NONE" or self.evidence != "SYNTHETIC_NATIVE_ONLY": raise ValueError()
                elif not _identity_valid(row["process"]) or row["descendants"] != "EXACT_DESCENDANTS_EXITED": raise ValueError()
            canonical(receipt)
            return copy.deepcopy(receipt)
        except Exception: raise NativeRouteError("NATIVE_CLOSURE_UNAVAILABLE") from None

    def _qualified_effect(self, local_job_id, phase, request, exact_fence):
        """Synchronous owned phases; no persistent terminal/SDK handoff is permitted."""
        try:
            job = self._load_job(local_job_id)
            if job["request"] != request or job["request_hash"] != native_request_hash(request) or exact_fence.get("local_job_id") != local_job_id or exact_fence.get("node_operation_id") != job["operation_id"]:
                raise NativeRouteError("NATIVE_JOB_MISMATCH")
            if phase == "cancel":
                process = job.get("fleet_process")
                if not _identity_valid(process) or exact_fence.get("process") != process: raise NativeRouteError("NATIVE_PROCESS_MISMATCH")
                with self._active_guard:
                    active = self._active.get(local_job_id)
                    if active is None or active["launch"].observed is None or active["launch"].observed.identity() != process: raise NativeRouteError("NATIVE_EXECUTION_UNRESOLVED")
                    active["cancel_fence"] = exact_fence
                return {"schema": "fleet.native.effect/1", "phase": "cancel", "local_job_id": local_job_id,
                    "target": request["placement"]["target"], "evidence": self.evidence,
                    "payload": {"status": "CANCEL_REQUESTED", "process": process}, "idempotent_recovered": False}
            session = request["placement"]["session"]
            with self._source_handoff(request, local_job_id, phase, exact_fence):
                with self._execution_lease(request, "FLEET-" + local_job_id + ":" + phase, phase, exact_fence) as lease:
                    installation, alias = self._admit(request, phase, exact_fence)
                    current = self._load_job(local_job_id)
                    previous = (current.get("fleet_effects") or {}).get(phase)
                    if previous:
                        if previous["status"] == "COMPLETED": return {**previous["receipt"], "idempotent_recovered": True}
                        raise NativeRouteError("NATIVE_RECOVERY_REQUIRED")
                    if phase in {"capture", "result"}:
                        process = current.get("fleet_process")
                        if not _identity_valid(process) or exact_fence.get("process") != process: raise NativeRouteError("NATIVE_PROCESS_MISMATCH")
                        start = (current.get("fleet_effects") or {}).get("start")
                        if not start or start.get("status") != "COMPLETED": raise NativeRouteError("NATIVE_EXECUTION_UNRESOLVED")
                        # Read existing qualified captured result; no IPC/window/PID reopen.
                        return {**start["receipt"], "phase": phase, "idempotent_recovered": True}
                    if phase not in {"deploy", "start", "test"}: raise NativeRouteError("NATIVE_REQUEST_INVALID")
                    effects = current.get("fleet_effects") or {}
                    effects[phase] = {"status": "PENDING", "request_sha256": native_request_hash(request)}
                    self.jobs.update_fields(local_job_id, fleet_effects=effects)
                    compile_result = None
                    deployed = effects.get("deploy")
                    if phase in {"deploy", "start"}:
                        compile_fence = exact_fence if phase == "deploy" else self._phase_fence("deploy", request, exact_fence)
                        compile_result = self._owned_driver(local_job_id, request, compile_fence, lease, installation, alias, "compile")
                    elif deployed and deployed.get("status") == "COMPLETED":
                        compile_result = deployed["receipt"]["payload"]["compilation"]
                    else: raise NativeRouteError("NATIVE_COMPILE_REQUIRED")
                    execution = {"status": "CANCELLED", "completion_reason": "CANCEL_REQUESTED_DURING_COMPILE"} if compile_result.get("cancelled") else {"status": "NOT_RUN"}
                    if phase != "deploy" and compile_result.get("status") == "PASSED" and not compile_result.get("cancelled"):
                        test_fence = self._phase_fence("test", request, exact_fence)
                        execution = self._owned_driver(local_job_id, request, test_fence, lease, installation, alias, "test", compile_result)
                    result_fence = self._phase_fence("result", request, exact_fence)
                    begin_result, complete_result = exact_fence.get("begin_effect"), exact_fence.get("complete_effect")
                    if not callable(begin_result) or not callable(complete_result): raise NativeRouteError("NATIVE_AUTHORIZATION_UNAVAILABLE")
                    result_proof = begin_result("result", "result_promote:0001")
                    if type(result_proof) is not NativeAuthorization: raise NativeRouteError("NATIVE_AUTHORIZATION_UNVERIFIED")
                    result_binding = result_proof.binding
                    result_fence = {**result_fence, "authorization": result_proof, "sequence": result_binding["sequence"], "challenge": result_binding["challenge"], "event": "result_promote:0001"}
                    self._admit(request, "result", result_fence)
                    receipt = {"schema": "fleet.native.effect/1", "phase": phase, "local_job_id": local_job_id,
                        "target": request["placement"]["target"], "evidence": self.evidence,
                        "payload": {"compilation": compile_result, "execution": execution, "process": self._load_job(local_job_id).get("fleet_process")}}
                    canonical(receipt)
                    effects[phase] = {"status": "COMPLETED", "receipt": receipt}
                    self.jobs.update_fields(local_job_id, fleet_effects=effects)
                    complete_result("result", "result_promote:0001", result_proof, outcome="COMPLETED", evidence={"kind":"PRODUCER_RETURNED","sha256":digest(receipt)})
                    return {**receipt, "idempotent_recovered": False}
        except (NativeRouteError, FleetProjectError): raise
        except Exception:
            raise NativeRouteError("NATIVE_RECOVERY_REQUIRED") from None

    def _verify_compiled(self, request, local_job_id, installation, compile_result):
        """The exact captured EX5 remains the tester input at every new boundary."""
        try:
            session = request["placement"]["session"]
            immutable = compile_result["immutable_ex5"]
            deployed, captured = Path(compile_result["ex5_path"]), Path(immutable["path"])
            expected = (Path(installation.installation["binding"]["data_root"]) / "MQL5/Experts/VibeMQL5" / session["workspace"] / Path(session["ea"]).relative_to("Experts")).with_suffix(".ex5")
            if deployed.resolve() != expected.resolve() or captured.resolve() != (self.root / "runs" / local_job_id / "compiled.ex5").resolve(): raise ValueError()
            if type(immutable["bytes"]) is not int or not 0 < immutable["bytes"] <= MAX_INPUT_BYTES or type(immutable["sha256"]) is not str or re.fullmatch(r"[a-f0-9]{64}", immutable["sha256"]) is None: raise ValueError()
            for path in (deployed, captured):
                raw = read_blob(path, MAX_INPUT_BYTES)
                if len(raw) != immutable["bytes"] or hashlib.sha256(raw).hexdigest() != immutable["sha256"]: raise ValueError()
        except Exception: raise NativeRouteError("NATIVE_COMPILED_INPUT_CHANGED") from None

    def _owned_driver(self, local_job_id, request, exact_fence, lease, installation, alias, kind, compile_result=None):
        phase = "deploy" if kind == "compile" else "test"
        if not callable(exact_fence.get("begin_effect")) or not callable(exact_fence.get("complete_effect")): raise NativeRouteError("NATIVE_AUTHORIZATION_UNAVAILABLE")
        installation, alias = self._admit(request, phase, exact_fence)
        install, policy = installation.installation, installation.policy
        scoped = type(lease) is ScopedLease
        resources = None if scoped else ResourceAuthority(self.root, max_records=policy["resource_max_records"], wait_ms=policy["resource_wait_ms"])
        authority = lease if scoped else OwnershipAuthority(self.root)
        assert_installation_idle(install["binding"]["executable"], install["metaeditor"])
        armed = authority.arm(lease)
        resource = None
        launch = None
        ownership_closed = False
        begin = exact_fence.get("begin_effect")
        finish = exact_fence.get("complete_effect")
        if not callable(begin) or not callable(finish): raise NativeRouteError("NATIVE_AUTHORIZATION_UNAVAILABLE")
        ordinal, pending = {}, [None]
        def revalidate(event):
            if pending[0] is not None: raise NativeRouteError("NATIVE_EFFECT_UNKNOWN")
            mapped = "cancel" if event.endswith("terminate") else "capture" if "capture" in event else phase
            ordinal[event] = ordinal.get(event, 0) + 1
            if sum(ordinal.values()) > 100000: raise NativeRouteError("NATIVE_EFFECT_CAPACITY")
            label = event + ":" + str(ordinal[event]).zfill(4)
            proof = begin(mapped, label)
            if type(proof) is not NativeAuthorization: raise NativeRouteError("NATIVE_AUTHORIZATION_UNVERIFIED")
            binding = proof.binding
            if binding.get("event") != label: raise NativeRouteError("NATIVE_FENCE_MISMATCH")
            current_fence = {**exact_fence, "authorization": proof, "sequence": binding["sequence"], "challenge": binding["challenge"], "event": label, "phase": mapped}
            if mapped == "cancel":
                if launch is None or launch.observed is None: raise NativeRouteError("NATIVE_PROCESS_MISMATCH")
                current_fence["process"] = launch.observed.identity()
                if binding.get("process_sha256") != digest(current_fence["process"]): raise NativeRouteError("NATIVE_PROCESS_MISMATCH")
            self._admit(request, mapped, current_fence)
            if kind == "test": self._verify_compiled(request, local_job_id, installation, compile_result)
            if event == "compile_ex5_capture":
                session = request["placement"]["session"]
                output = (Path(install["binding"]["data_root"]) / "MQL5/Experts/VibeMQL5" / session["workspace"] / Path(session["ea"]).relative_to("Experts")).with_suffix(".ex5")
                if output.is_symlink() or output.stat().st_size > MAX_INPUT_BYTES: raise NativeRouteError("NATIVE_OUTPUT_TOO_LARGE")
            observed = launch.observed.identity() if launch is not None and launch.observed is not None else None
            assert_installation_idle(install["binding"]["executable"], install["metaeditor"], owned_identity=observed)
            proof.require(**binding)  # Immediately before the concrete producer action.
            pending[0] = (event, mapped, label, proof)
        def require_current(event):
            item = pending[0]
            if item is None or item[0] != event: raise NativeRouteError("NATIVE_EFFECT_UNKNOWN")
            # Durable create-attempt I/O cannot extend an effect grant's lifetime.
            item[3].require(**item[3].binding)
        def complete_boundary(event):
            item = pending[0]
            if item is None or item[0] != event: raise NativeRouteError("NATIVE_EFFECT_UNKNOWN")
            descriptor = {"request_sha256": native_request_hash(request), "placement_sha256": request["placement"]["record_sha256"],
                "input_manifest_sha256": digest(request["input_manifest"]), "local_job_id": local_job_id, "phase": item[1], "event": item[2]}
            if launch is not None and launch.observed is not None: descriptor["process"] = launch.observed.identity()
            # Completion is proof of a returned producer call; an already consumed
            # effect can return after grant expiry. It cannot authorize another action.
            finish(item[1], item[2], item[3], outcome="COMPLETED", evidence={"kind": "PRODUCER_RETURNED", "sha256": digest(descriptor)})
            pending[0] = None
        def on_bound(process):
            self.jobs.update_fields(local_job_id, fleet_process=process)
            publisher = exact_fence.get("publish_process")
            if publisher is not None:
                if not callable(publisher): raise NativeRouteError("NATIVE_FENCE_MISMATCH")
                publisher(launch.observed, kind)
        def should_cancel():
            with self._active_guard: active = self._active.get(local_job_id)
            current_fence = active.get("cancel_fence") if active else None
            if current_fence is None: return False
            self._admit(request, "cancel", current_fence)
            return True
        try:
            if resources is not None:
                resource = resources.reserve(local_job_id + ":" + kind, kind="compiler_deploy" if kind == "compile" else "tester",
                    resources={**install["binding"], "include_root": install["include_root"], "agent_root": install["agent_root"]}, lease=lease, armed_ownership=armed)
            launch = OwnedWindowsLaunch(authority, armed, revalidate, on_bound=on_bound, should_cancel=should_cancel if kind == "compile" else None, complete=complete_boundary, require_current=require_current)
            with self._active_guard: self._active[local_job_id] = {"launch": launch, "cancel_fence": None}
            session = request["placement"]["session"]
            run_dir = self.root / "runs" / local_job_id
            pin = self._pinned.get(local_job_id)
            frozen_inputs = dict(pin.values) if type(pin) is _PinnedInputs else self._frozen_input_bytes(request)
            if kind == "compile":
                revalidate("snapshot_prepare")
                self._publish_snapshot(request, local_job_id, frozen_inputs)
                complete_boundary("snapshot_prepare")
                result = CompilerDriver(self.root).compile(session["workspace"], session["ea"], alias, run_dir,
                    timeout=policy["compile_timeout_seconds"], owned_launch=launch, before_effect=revalidate, frozen_inputs=frozen_inputs, after_effect=complete_boundary)
            else:
                self._verify_compiled(request, local_job_id, installation, compile_result)
                result = TesterDriver(self.root).run(local_job_id, session["workspace"], session["ea"], alias,
                    compile_result["expert_name"], "fleet_frozen", run_dir, set_rel=next((relative for relative in frozen_inputs if relative.lower().endswith(".set")), None),
                    timeout=policy["test_timeout_seconds"], resolved_config=request["logical_config"]["config"],
                    frozen_set_bytes=next((raw for relative, raw in frozen_inputs.items() if relative.lower().endswith(".set")), None),
                    request_normalization=request["logical_config"]["normalization"], should_cancel=should_cancel,
                    owned_launch=launch, before_effect=revalidate, after_effect=complete_boundary)
            if pending[0] is not None: raise NativeRouteError("NATIVE_EFFECT_UNKNOWN")
            process = launch.observed.identity() if launch.observed is not None else None
            closed = launch.finish()
            if resources is not None: resources.release(resource["reservation_id"])
            self._phase_closures.setdefault(local_job_id, []).append({"phase": phase, "ownership_record": closed,
                "process": process, "descendants": "EXACT_DESCENDANTS_EXITED" if process is not None else "NONE"})
            ownership_closed = True
            with self._active_guard:
                active = self._active.pop(local_job_id, None)
                if kind == "compile" and active and active.get("cancel_fence") is not None:
                    result = {**result, "cancelled": True}
            return result
        except Exception:
            if scoped:
                try: lease.uncertain(launch.expected if launch is not None else armed)
                except Exception: pass
            if resource is not None:
                try: resources.uncertain(resource["reservation_id"])
                except Exception: pass
            # Uncertain process creation/binding or expired authorization retains
            # handles and ACTIVE authority; expiry alone never kills a live worker.
            if not scoped and launch is not None and launch.process is None and launch.expected["phase"] == "ARMED":
                try:
                    launch.finish()
                    if resource is not None: resources.release(resource["reservation_id"])
                    ownership_closed = True
                except Exception: pass
            raise NativeRouteError("NATIVE_RECOVERY_REQUIRED") from None
        finally:
            if ownership_closed:
                with self._active_guard: self._active.pop(local_job_id, None)
                if launch is not None: launch.close_handles()

    def _synthetic_effect(self, local_job_id, phase, request, exact_fence):
        job = self._load_job(local_job_id)
        if job["request"] != request or job["request_hash"] != native_request_hash(request):
            raise NativeRouteError("NATIVE_JOB_MISMATCH")
        session = request["placement"]["session"]
        with self.concurrency.mutation("fleet_source_guard", resource=session["workspace"] + ":" + session["ea"], wait_seconds=0):
            with self.concurrency.native_execution("FLEET-" + local_job_id, kind="fleet_" + phase, wait_seconds=0) as lease:
                self._admit(request, phase, exact_fence)
                current = self._load_job(local_job_id)
                previous = (current.get("fleet_effects") or {}).get(phase)
                if previous:
                    if previous["status"] == "COMPLETED":
                        return {**previous["receipt"], "idempotent_recovered": True}
                    raise NativeRouteError("NATIVE_RECOVERY_REQUIRED")
                if phase in {"capture", "cancel", "result"}:
                    process = current.get("fleet_process")
                    if not _identity_valid(process) or exact_fence.get("process") != process:
                        raise NativeRouteError("NATIVE_PROCESS_MISMATCH")
                authority = OwnershipAuthority(self.root)
                armed = authority.arm(lease)
                effects = current.get("fleet_effects") or {}
                effects[phase] = {"status": "PENDING", "request_sha256": native_request_hash(request)}
                try:
                    self.jobs.update_fields(local_job_id, fleet_effects=effects)
                    payload = self._fixture_callback(phase, request, exact_fence)
                    self._admit(request, phase, exact_fence)  # Result/target fence after the harmless callback.
                    receipt = {"schema": "fleet.native.effect/1", "local_job_id": local_job_id, "phase": phase,
                        "target": request["placement"]["target"], "evidence": self.evidence, "payload": payload}
                    canonical(receipt)
                    if phase == "start":
                        process = payload.get("process") if isinstance(payload, dict) else None
                        if not _identity_valid(process): raise NativeRouteError("NATIVE_PROCESS_MISMATCH")
                        self.jobs.update_fields(local_job_id, fleet_process=process)
                    effects[phase] = {"status": "COMPLETED", "receipt": receipt}
                    self.jobs.update_fields(local_job_id, fleet_effects=effects)
                    # Harmless fixture makes no process-create attempt. This exact
                    # zero-attempt close does not certify real IPC/descendants.
                    closed = authority.close_zero_attempt(armed)
                    self._phase_closures[local_job_id] = [{"phase": phase, "ownership_record": closed, "process": None, "descendants": "NONE"}]
                    return {**receipt, "idempotent_recovered": False}
                except Exception:
                    # ARMED/PENDING survives callback/publication failure. Common
                    # admission denies every successor, with no TTL/force reset.
                    raise NativeRouteError("NATIVE_RECOVERY_REQUIRED") from None


class SyntheticNativeAdapter(RoutedNativeAdapter):
    """Explicit harmless fixture hooks; never produced by the production factory."""
    evidence = "SYNTHETIC_NATIVE_ONLY"

    def __init__(self, root, *, callbacks, gate=None):
        super().__init__(root)
        self.callbacks = dict(callbacks)
        self.gate = gate

    def _admit(self, request, phase, exact_fence=None):
        native_request_hash(request)
        self.projects.validate_frozen(request["placement"])
        if exact_fence is not None:
            if (not isinstance(exact_fence, dict) or exact_fence.get("target") != request["placement"]["target"]
                    or exact_fence.get("session_sha256") != request["placement"]["session"]["revision_sha256"]):
                raise NativeRouteError("NATIVE_FENCE_MISMATCH")
        if self.gate is not None:
            self.gate(request, phase, exact_fence)

    def _fixture_callback(self, phase, request, exact_fence):
        callback = self.callbacks.get(phase)
        if callback is None:
            raise NativeRouteError("NATIVE_QUALIFICATION_UNAVAILABLE")
        return callback(copy.deepcopy(request), copy.deepcopy(exact_fence))
