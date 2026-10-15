"""Owned ephemeral SDK controller. No SDK is imported by the controller."""
from __future__ import annotations

import os
import json
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType

from ..core.native_ownership import ObservedProcess, OwnershipAuthority, current_identity
from ..core.isolated_sdk import SdkBoundary, probe_terminal
from .sdk_protocol import (REQUEST_SCHEMA, ProtocolError, canonical, read_bounded, result,
                           validate_request, validate_result, write_bounded)
from .sdk_qualification import QualifiedSdkInstallation, QualificationError

OPERATIONS = {"get_terminal_live_state": "state", "get_account_snapshot": "account"}
ADMISSION_CODES = {"READ_ADMISSION_UNVERIFIED", "READ_ADMISSION_MISMATCH", "READ_ADMISSION_USED",
                   "READ_ADMISSION_CLOSED", "READ_INTERRUPTED", "READ_SESSION_INTERRUPTED",
                   "READ_ADMISSION_UNAVAILABLE"}


class ReadAdmissionError(RuntimeError):
    pass


def _assert_admission(admission, command):
    from .wire import WireError
    try:
        admission.assert_current(command)
    except WireError as error:
        code = ("LIVE_DEADLINE_EXCEEDED" if error.code in {"READ_DEADLINE_EXCEEDED", "HTTP_DEADLINE_EXCEEDED"}
                else error.code if error.code in ADMISSION_CODES else "READ_ADMISSION_UNAVAILABLE")
        raise ReadAdmissionError(code) from None


def _scoped_lease(lease):
    from .scoped_resources import ScopedLease
    return type(lease) is ScopedLease


def _owner(state, lease):
    fields = {key: state[key] for key in ("epoch", "generation", "token", "parent", "operation_id")}
    fields["kind"] = state["request"]["kind"] if _scoped_lease(lease) else state["kind"]
    return fields


def _ownership_status(authority):
    state = authority.load()
    if state.get("schema") == "fleet.scoped-ownership/1":
        if state.get("status") == "UNKNOWN":
            return "RECOVERY_REQUIRED"
        if state.get("phase") == "CLOSED" and state.get("status") in {"ACQUIRED", "RELEASED"}:
            return "CLOSED"
        return "ACTIVE" if state.get("status") == "ACQUIRED" else "RECOVERY_REQUIRED"
    return authority.status().get("disposition", "RECOVERY_REQUIRED")


@contextmanager
def _owned_execution(manager, lifecycle):
    """Observe actual release separately from an observation's first failure."""
    body_error = None
    with manager as lease:
        lifecycle["acquired"] = True
        try:
            yield lease
        except Exception as error:
            body_error = error
            lifecycle["body_error"] = error
        lifecycle["release_started"] = time.monotonic()
    lifecycle["released"] = True
    if body_error is not None:
        raise body_error


def _owned_request(root, lease, request, installation):
    if type(installation) is not QualifiedSdkInstallation:
        raise QualificationError()
    installation.assert_request(request)
    if Path(root).resolve() != Path(installation.installation["authority_root"]).resolve():
        raise QualificationError()
    if (getattr(lease, "namespace", None) not in {"native", "scoped_native"} or getattr(lease, "released", True)
            or Path(lease.root).resolve() != Path(root).resolve()):
        raise QualificationError()
    if _scoped_lease(lease):
        coordinator = installation.scope_coordinator()
        if (coordinator is None or request["scope"] != lease.reference
                or lease.coordinator.evidence != "SIGNED_PHYSICAL_CAPACITY_PROFILE"
                or coordinator.read_scope(lease.reference) != lease.load()):
            raise QualificationError()
    elif (lease.namespace != "native" or request["scope"] is not None
            or installation.installation["scope_authority"] is not None):
        raise QualificationError()


def observe_under_owned_lease(root, lease, request, installation, *, node_admission=None, command=None):
    """Use one already-owned common lease; never recursively acquire another."""
    _owned_request(root, lease, request, installation)
    if request["target"].get("route_generation") is not None:
        from .transport import NodeReadAdmission
        if type(node_admission) is not NodeReadAdmission or type(command) is not dict or command.get("target") != request["target"]:
            raise QualificationError()
        _assert_admission(node_admission, command)
    return _run_owned(root, lease, request, installation,
        authority=lease.authority if _scoped_lease(lease) else None,
        node_admission=node_admission, command=command)


def _run_owned(root, lease, request, installation, *, boundary_factory=SdkBoundary,
               observer_factory=ObservedProcess, authority=None, clock=time.monotonic,
               expected_evidence="REAL_SDK_OPERATOR_APPROVED", fault=None, node_admission=None, command=None):
    """Private orchestration; injected fixture adapters cannot activate public API."""
    request = json.loads(canonical(validate_request(request)))
    authority = authority or OwnershipAuthority(Path(root))
    started, expected, boundary, process, observation, attempt = clock(), None, None, None, None, False
    answer = result(request, evidence=expected_evidence, reason="WORKER_START_UNPROVEN")
    answer["ownership"] = {"status": "NOT_ACQUIRED"}
    directory = None

    def point(name):
        if fault is not None:
            fault(name)

    try:
        installation.assert_request(request)
        if node_admission is not None:
            _assert_admission(node_admission, command)
        expected = authority.arm(lease)
        owner = _owner(expected, lease)
        if request["owner"] != owner:
            raise ProtocolError()
        point("ARMED")
        directory = Path(tempfile.mkdtemp(prefix="sdk-", dir=Path(root) / "runs"))
        boundary = boundary_factory(directory, installation)
        request_path, output_path, key_path = (directory / name for name in
                                              ("request.json", "result.json", "operator-public.key"))
        write_bounded(request_path, request)
        with key_path.open("xb") as stream:
            stream.write(installation.operator_public_key)
            stream.flush()
            os.fsync(stream.fileno())
        if clock() - started >= request["budget_ms"] / 1000:
            answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
            raise TimeoutError()
        installation.assert_current()
        if node_admission is not None:
            _assert_admission(node_admission, command)
        expected = authority.create_attempt(expected)
        attempt = True
        point("CREATE_ATTEMPT")
        process = boundary.spawn(request_path, output_path, key_path)
        point("SUSPENDED_CREATE")
        observation = observer_factory(process.lifetime()["pid"])
        process.verify_observation(observation)
        installation.assert_restrictions(process.restrictions)
        if output_path.exists():
            raise ProtocolError()
        expected = authority.bind_worker(expected, observation)
        point("BOUND")
        process.allow_resume(authority, expected, observation)
        point("BEFORE_RESUME")
        if clock() - started >= request["budget_ms"] / 1000:
            answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
            raise TimeoutError()
        if node_admission is not None:
            _assert_admission(node_admission, command)
        process.resume()
        point("RESUMED")
        while not process.exited() and clock() - started < request["budget_ms"] / 1000:
            time.sleep(.005)
        if not process.exited():
            answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
        elif process.wait(0) != 0:
            answer["reason_code"] = "WORKER_RESULT_INVALID"
        else:
            received = validate_result(read_bounded(output_path), request)
            if received["evidence"] != expected_evidence:
                raise ProtocolError()
            answer = received
    except TimeoutError:
        answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
    except ReadAdmissionError as error:
        answer["reason_code"] = str(error)
    except Exception:
        if answer["reason_code"] == "LIVE_ATTACH_ONLY_UNPROVEN":
            answer["reason_code"] = "WORKER_START_UNPROVEN"
    finally:
        cleanup_error, closed = False, False
        if process is not None:
            try:
                if not process.exited():
                    process.terminate_exact(process.identity())
            except Exception:
                cleanup_error = True
        try:
            if expected is not None and not attempt and expected["phase"] == "ARMED":
                authority.close_zero_attempt(expected)
                closed = True
            elif (not cleanup_error and expected is not None and expected["phase"] == "BOUND"
                  and process is not None and observation is not None):
                authority.close_owned_worker(expected, observation,
                    descendant_verifier=lambda observed: boundary.prove_closure(process, observed))
                closed = True
        except Exception:
            cleanup_error = True
        try:
            ownership = _ownership_status(authority)
        except Exception:
            ownership = "RECOVERY_REQUIRED"
        if not closed and (attempt or expected is not None or ownership != "CLOSED"):
            cleanup_error = True
        for resource in (observation, process, boundary):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    cleanup_error = True
        if directory is not None:
            try:
                shutil.rmtree(directory)
            except OSError:
                cleanup_error = True
        elapsed = max(0.0, (clock() - started) * 1000)
        expired = elapsed >= request["budget_ms"]
        primary = answer["reason_code"]
        if expired and primary is None:
            primary = "LIVE_DEADLINE_EXCEEDED"
        if cleanup_error:
            first = answer["primary_reason_code"] or primary
            answer.update(status="FAILED", reason_code="LIVE_CLEANUP_UNPROVEN", primary_reason_code=first,
                          terminal=None, account=None, observed_at_utc=None,
                          cleanup={"status": "UNPROVEN", "reason_code": "LIVE_CLEANUP_UNPROVEN"})
        elif primary:
            answer.update(status="FAILED", reason_code=primary, terminal=None, account=None, observed_at_utc=None)
        answer["timing_ms"] = {"total": elapsed, "expired": expired}
        answer["ownership"] = {"status": ownership}
        # Parent proof is separate from the worker's shutdown-return evidence.
        answer["qualified_closure"] = (closed or (expected is None and not attempt and ownership == "CLOSED")) and not cleanup_error
        answer["sdk_attempted"] = attempt
    return answer


def _receipt(operation, target, budget_ms):
    return {"schema": "fleet.read/1", "operation": operation, "status": "FAILED",
        "reason_code": "LIVE_ATTACH_ONLY_UNPROVEN", "primary_reason_code": None,
        "requested_target": target, "resolved_target": None, "identity": None,
        "observed_binding": None, "source": None, "observed_at_utc": None,
        "terminal": None, "account": None, "phase": "qualification",
        "budget": {"mode": "SOFT_SUCCESS", "observation_ms": budget_ms, "lease_wait_ms": 2000,
                   "initialize_max_ms": 2000, "process_probe_max_ms": 2000, "expired": False},
        "timing_ms": {"total": 0.0, "lease": None, "process": None, "initialize": None,
                      "observe": None, "revalidate": None, "cleanup": None, "release": None},
        "cleanup": {"status": "NOT_ATTEMPTED", "reason_code": None},
        "ownership": {"status": "NOT_ACQUIRED"}}


def read_local(root, concurrency, operation, target, installation, *, budget_ms=10000):
    """Local installation qualification cannot grant gateway route authority."""
    if type(operation) is not str or operation not in OPERATIONS or type(budget_ms) is not int or not 1 <= budget_ms <= 10000:
        raise ProtocolError()
    if isinstance(target, dict) and target.get("route_generation") is not None:
        answer = _receipt(operation, None, budget_ms)
        answer["reason_code"] = "ROUTED_NATIVE_NOT_ENABLED"
        return answer
    return _read_bound(root, concurrency, operation, target, installation, budget_ms=budget_ms)


def _read_bound(root, concurrency, operation, target, installation, *, budget_ms=10000, node_admission=None, command=None):
    """Trusted local/node adapter only. Routing authority remains the node protocol's.

    Full routed attribution is retained through request/result. The inventory-only
    projection below compares local identity; it never authorizes a gateway route.
    """
    from .reads import _target, _inventory_rows
    from .targets import validate_local_target
    from .identity import IdentityError
    started, acquired, release_started = time.monotonic(), False, None
    lifecycle = {"acquired": False, "released": False, "release_started": None, "body_error": None}
    if type(operation) is not str or operation not in OPERATIONS or type(budget_ms) is not int or not 1 <= budget_ms <= 10000:
        raise ProtocolError()
    answer = _receipt(operation, None, budget_ms)
    terminal_process, entered_sdk, authority = None, False, None
    try:
        frozen = _target(target)
        answer["requested_target"] = frozen
        if type(installation) is not QualifiedSdkInstallation:
            raise QualificationError()
        installation.assert_current()
        if Path(root).resolve() != Path(installation.installation["authority_root"]).resolve():
            raise QualificationError()
        remaining = budget_ms / 1000 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError()
        answer["phase"] = "lease"
        before = time.monotonic()
        coordinator = installation.scope_coordinator()
        operation_id = "SDK-" + uuid.uuid4().hex
        execution = (coordinator.execution(operation_id, kind="ipc", terminal_id=frozen["terminal_id"],
            terminal_generation=frozen["terminal_generation"], wait_ms=int(min(2000, remaining * 1000)))
            if coordinator is not None else concurrency.native_execution(operation_id, kind=operation,
                wait_seconds=min(2.0, remaining)))
        with _owned_execution(execution, lifecycle) as lease:
            acquired = True
            authority = lease.authority if _scoped_lease(lease) else OwnershipAuthority(Path(root))
            answer["ownership"] = {"status": "HELD"}
            answer["timing_ms"]["lease"] = (time.monotonic() - before) * 1000
            answer["phase"] = "validation"
            if node_admission is not None:
                _assert_admission(node_admission, command)
            local = {key: value for key, value in frozen.items() if key != "route_generation"}
            resolved = validate_local_target(root, _inventory_rows(root), local, capability="inventory")
            answer["resolved_target"] = dict(frozen)
            binding = {"executable": resolved["binding"]["terminal_canonical_path"],
                       "data_root": resolved["binding"]["data_canonical_path"], "alias": resolved["alias"]}
            answer["identity"] = {"identity_source": resolved["identity_source"],
                "identity_revision": resolved["identity_revision"], "alias": resolved["alias"],
                "binding": {k: binding[k] for k in ("executable", "data_root")}}
            answer["phase"] = "process"
            before = time.monotonic()
            terminal_process = probe_terminal(binding["executable"],
                deadline=min(started + budget_ms / 1000, before + 2.0))
            binding["process"] = terminal_process.identity()
            answer["timing_ms"]["process"] = (time.monotonic() - before) * 1000
            if _scoped_lease(lease):
                state = authority.load()
                if state["phase"] != "CLOSED" or state["status"] != "ACQUIRED":
                    raise QualificationError()
            else:
                state = authority.require_closed()
            remaining_ms = int(budget_ms - (time.monotonic() - started) * 1000)
            if remaining_ms <= 0:
                raise TimeoutError()
            request = {"schema": REQUEST_SCHEMA, "operation": OPERATIONS[operation], "nonce": uuid.uuid4().hex,
                "target": frozen, "qualification_sha256": installation.sha256, "budget_ms": remaining_ms,
                "scope": lease.reference if _scoped_lease(lease) else None,
                "binding": binding, "owner": {"epoch": state["epoch"], "generation": state["generation"] + 1,
                    "token": lease.token, "parent": current_identity(), "operation_id": lease.operation_id,
                    "kind": state["request"]["kind"] if _scoped_lease(lease) else lease.kind}}
            answer["phase"] = "observe"
            before = time.monotonic()
            entered_sdk = True
            observed = observe_under_owned_lease(root, lease, request, installation, node_admission=node_admission, command=command)
            entered_sdk = observed.get("sdk_attempted", True)
            answer["timing_ms"]["observe"] = (time.monotonic() - before) * 1000
            answer["reason_code"] = observed["reason_code"]
            answer["primary_reason_code"] = observed["primary_reason_code"]
            answer["ownership"] = observed["ownership"]
            if observed["qualified_closure"] and not entered_sdk:
                answer["cleanup"] = {"status": "NOT_ATTEMPTED", "reason_code": None}
            elif observed["qualified_closure"]:
                answer["cleanup"] = {"status": "PROVEN", "reason_code": None}
            else:
                answer["cleanup"] = {"status": "UNPROVEN", "reason_code": "LIVE_CLEANUP_UNPROVEN"}
            # Revalidate registry AND retained actual terminal lifetime after cleanup.
            if observed["status"] == "SUCCEEDED" and observed["qualified_closure"]:
                answer["phase"] = "revalidate"
                current = validate_local_target(root, _inventory_rows(root), local, capability="inventory")
                if (current["identity_revision"] != resolved["identity_revision"] or current["binding"] != resolved["binding"]
                        or terminal_process.exited() or terminal_process.identity() != binding["process"]):
                    answer["reason_code"] = "LIVE_BINDING_MISMATCH"
                else:
                    if node_admission is not None:
                        _assert_admission(node_admission, command)
                    answer.update(status="SUCCEEDED", reason_code=None,
                        observed_binding=observed["observed_binding"], source="NODE_LIVE_QUALIFIED",
                        observed_at_utc=observed["observed_at_utc"], terminal=observed["terminal"], account=observed["account"])
            release_started = time.monotonic()
        answer["timing_ms"]["release"] = (time.monotonic() - release_started) * 1000
        if _scoped_lease(lease):
            answer["ownership"] = {"status": _ownership_status(authority)}
    except QualificationError:
        answer["reason_code"] = "LIVE_ATTACH_ONLY_UNPROVEN"
        if acquired and not entered_sdk:
            answer["ownership"] = {"status": "RELEASED"}
    except IdentityError as error:
        if entered_sdk and answer["reason_code"] is not None:
            answer["primary_reason_code"] = answer["reason_code"]
        answer["reason_code"] = error.code
        if acquired and not entered_sdk:
            answer["ownership"] = {"status": "RELEASED"}
    except TimeoutError:
        answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED" if acquired or answer["phase"] == "qualification" else "LIVE_LEASE_UNAVAILABLE"
    except ReadAdmissionError as error:
        answer["reason_code"] = str(error)
    except Exception as error:
        first_error = lifecycle["body_error"] or error
        primary = first_error.code if isinstance(first_error, IdentityError) else str(first_error) if isinstance(first_error, ReadAdmissionError) else (
            str(first_error) if str(first_error) in {"LIVE_PROCESS_UNAVAILABLE", "TERMINAL_NOT_RUNNING", "LIVE_BINDING_MISMATCH", "LIVE_DEADLINE_EXCEEDED"}
            else "LIVE_OBSERVATION_UNAVAILABLE")
        primary = answer["primary_reason_code"] or (
            answer["reason_code"] if entered_sdk and answer["reason_code"] not in {None, "LIVE_ATTACH_ONLY_UNPROVEN"}
            else primary)
        try:
            state = _ownership_status(authority) if acquired and authority is not None else "NOT_ACQUIRED"
        except Exception:
            state = "RECOVERY_REQUIRED"
        if acquired and state == "CLOSED" and lifecycle["released"]:
            answer.update(reason_code=primary, ownership={"status": "CLOSED" if entered_sdk else "RELEASED"})
        else:
            answer.update(status="FAILED", reason_code="LIVE_CLEANUP_UNPROVEN" if acquired else "LIVE_RECOVERY_REQUIRED",
                          primary_reason_code=primary, terminal=None, account=None, observed_at_utc=None, observed_binding=None, source=None)
            if acquired:
                answer["cleanup"] = {"status": "UNPROVEN", "reason_code": "LIVE_CLEANUP_UNPROVEN"}
                answer["ownership"] = {"status": state}
    finally:
        if lifecycle["release_started"] is not None:
            answer["timing_ms"]["release"] = (time.monotonic() - lifecycle["release_started"]) * 1000
        if acquired:
            try:
                disposition = _ownership_status(authority)
            except Exception:
                disposition = "RECOVERY_REQUIRED"
            if not lifecycle["released"] or disposition != "CLOSED":
                first = answer["primary_reason_code"] or answer["reason_code"]
                if first is None:
                    first = "LIVE_OBSERVATION_UNAVAILABLE"
                answer.update(reason_code="LIVE_CLEANUP_UNPROVEN", primary_reason_code=first,
                    cleanup={"status": "UNPROVEN", "reason_code": "LIVE_CLEANUP_UNPROVEN"},
                    ownership={"status": disposition})
            else:
                answer["ownership"] = {"status": "CLOSED" if entered_sdk else "RELEASED"}
        if terminal_process is not None:
            try:
                terminal_process.close()
            except Exception:
                answer.update(status="FAILED", primary_reason_code=answer["primary_reason_code"] or answer["reason_code"],
                              reason_code="LIVE_CLEANUP_UNPROVEN", cleanup={"status": "UNPROVEN", "reason_code": "LIVE_CLEANUP_UNPROVEN"}, terminal=None, account=None,
                              observed_at_utc=None, observed_binding=None, source=None)
        total = max(0.0, (time.monotonic() - started) * 1000)
        answer["timing_ms"]["total"] = total
        answer["budget"]["expired"] = total >= budget_ms
        if total >= budget_ms and answer["reason_code"] is None:
            answer.update(status="FAILED", reason_code="LIVE_DEADLINE_EXCEEDED", terminal=None, account=None,
                          observed_at_utc=None, observed_binding=None, source=None)
        if answer["reason_code"] is not None:
            answer.update(status="FAILED", terminal=None, account=None, observed_at_utc=None,
                          observed_binding=None, source=None)
    return answer


class QualifiedReadAdapter:
    """Configured trusted node adapter; HTTP cannot construct installation authority."""
    def __init__(self, root, concurrency, installation):
        candidates = (installation,) if type(installation) is QualifiedSdkInstallation else installation
        if type(candidates) not in (tuple, list) or not 1 <= len(candidates) <= 16:
            raise QualificationError()
        selected, family = {}, None
        terminal_executables = {item.installation["executable"] for item in candidates
                                if type(item) is QualifiedSdkInstallation}
        shared = ("authority_root", "platform", "os_build", "session_id", "python", "python_dll", "sdk_wheel",
                  "sdk_dll", "worker", "profile_name", "profile_sid", "restrictions", "scope_authority")
        for candidate in candidates:
            if type(candidate) is not QualifiedSdkInstallation:
                raise QualificationError()
            fixed = candidate.installation
            key = (fixed["target"]["device_id"], fixed["target"]["terminal_id"], fixed["target"]["terminal_generation"])
            current_family = {name: fixed[name] for name in shared}
            current_family["device_id"] = key[0]
            current_family["runtime_files"] = {path: sha for path, sha in fixed["runtime_files"].items()
                                               if path not in terminal_executables}
            if (Path(fixed["authority_root"]).resolve() != Path(root).resolve() or key in selected
                    or (family is not None and family != current_family)):
                raise QualificationError()
            family, selected[key] = current_family, candidate
        self.root, self.concurrency = Path(root), concurrency
        self._installations = MappingProxyType(selected)
        self.installation = candidates[0] if len(candidates) == 1 else None

    def _select(self, target):
        from .reads import _target
        frozen = _target(target)
        return frozen, self._installations.get((frozen["device_id"], frozen["terminal_id"], frozen["terminal_generation"]))

    def read(self, command, admission=None):
        from .transport import NodeReadAdmission
        if type(admission) is not NodeReadAdmission:
            raise QualificationError()
        if type(command) is not dict or type(command.get("operation")) is not str or command["operation"] not in OPERATIONS:
            raise ProtocolError()
        admission.claim(command)
        deadline = command.get("deadline_ms")
        if type(deadline) is not int or not 0 < deadline <= (1 << 63) - 1:
            raise ProtocolError()
        remaining = min(10000, deadline - int(time.time() * 1000))
        if remaining <= 0:
            answer = _receipt(command["operation"], command.get("target"), 0)
            answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
            answer["budget"]["expired"] = True
            return answer
        target, installation = self._select(command["target"])
        if installation is None:
            answer = _receipt(command["operation"], target, remaining)
            answer["reason_code"] = "SDK_TARGET_UNQUALIFIED"
            return answer
        return _read_bound(self.root, self.concurrency, command["operation"], target,
                          installation, budget_ms=remaining, node_admission=admission, command=command)
