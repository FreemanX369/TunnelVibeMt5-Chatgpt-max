"""Local attribution and an explicit trusted installed SDK integration.

Inventory resolution supplies attribution. With no installed qualification, the
C1 admission remains unavailable. Positive gateway routes use the separately
authenticated outbound-node adapter.
"""
from __future__ import annotations

import re
import time
import uuid

from ..core.inventory import TerminalInventory
from .identity import IdentityError
from .targets import validate_local_target

IDENTITY_CODES = {"IDENTITY_UNENROLLED", "IDENTITY_INVALID", "RESOURCE_CONFLICT",
                  "TARGET_UNKNOWN", "TARGET_MISMATCH", "ROUTED_NATIVE_NOT_ENABLED"}


def _target(value):
    required = {"schema", "device_id", "terminal_id", "terminal_generation"}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - {"route_generation"} or value["schema"] != "fleet.target/1"
            or not isinstance(value["device_id"], str)
            or re.fullmatch(r"dev_[a-f0-9]{32}", value["device_id"]) is None
            or not isinstance(value["terminal_id"], str)
            or re.fullmatch(r"term_[a-f0-9]{32}", value["terminal_id"]) is None
            or type(value["terminal_generation"]) is not int or value["terminal_generation"] <= 0
            or (value.get("route_generation") is not None and
                (type(value["route_generation"]) is not int or value["route_generation"] <= 0))):
        raise IdentityError("TARGET_MISMATCH", "Invalid target reference")
    return {key: value[key] for key in required | ({"route_generation"} if "route_generation" in value else set())}


def _inventory_rows(root):
    # list() deduplicates aliases through _items and can hide config conflicts.
    rows = TerminalInventory(root)._identity_items
    seen = set()
    for row in rows:
        if (type(row.enabled) is not bool or not isinstance(row.alias, str)
                or not row.alias.strip() or row.alias != row.alias.strip()):
            raise IdentityError("IDENTITY_INVALID", "Invalid configured alias/enabled state")
        alias = row.alias.upper()
        if alias in seen:
            raise IdentityError("RESOURCE_CONFLICT", "Duplicate configured alias")
        seen.add(alias)
    return rows


def targeted_read(root, concurrency, operation, target, *, clock=None, sdk_installation=None):
    if operation not in ("get_terminal_live_state", "get_account_snapshot"):
        raise ValueError("UNSUPPORTED_READ_OPERATION")
    if sdk_installation is not None:
        # Only a trusted local operator loader can construct the sealed installed
        # qualification. Dispatch before the C1 lease: read_local owns one common
        # native lease covering validation, worker lifetime and exact closure.
        from .sdk_controller import read_local
        from .sdk_qualification import QualifiedSdkInstallation, QualificationError
        if type(sdk_installation) is not QualifiedSdkInstallation:
            raise QualificationError()
        try:
            selected = _target(target)
        except IdentityError:
            selected = None
        # Legacy/local callers have no authenticated current gateway route. A
        # positive route can only reach the separate signed outbound-node path.
        if selected is not None and selected.get("route_generation") is None:
            return read_local(root, concurrency, operation, target, sdk_installation)
    clock = clock or time.monotonic
    started = clock()
    answer = {"schema": "fleet.read/1", "operation": operation, "status": "FAILED",
        "reason_code": None, "primary_reason_code": None, "requested_target": None,
        "resolved_target": None, "identity": None, "observed_binding": None, "source": None,
        "observed_at_utc": None, "terminal": None, "account": None, "phase": "validation",
        "budget": {"mode": "SOFT_SUCCESS", "observation_ms": 10000, "lease_wait_ms": 2000,
                   "initialize_max_ms": 2000, "process_probe_max_ms": 2000, "expired": False},
        "timing_ms": {"total": 0.0, "lease": None, "process": None, "initialize": None,
                      "observe": None, "revalidate": None, "cleanup": None, "release": None},
        "cleanup": {"status": "NOT_ATTEMPTED", "reason_code": None},
        "ownership": {"status": "NOT_ACQUIRED"}}

    def finish():
        elapsed = max(0.0, (clock() - started) * 1000)
        answer["timing_ms"]["total"] = elapsed
        answer["budget"]["expired"] = elapsed >= 10000
        if answer["reason_code"] is None:
            answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED" if elapsed >= 10000 else "LIVE_ATTACH_ONLY_UNPROVEN"
        return answer

    try:
        requested = _target(target)
        answer["requested_target"] = requested
    except IdentityError:
        answer["reason_code"] = "TARGET_MISMATCH"
        return finish()
    if requested.get("route_generation") is not None:
        answer["reason_code"] = "ROUTED_NATIVE_NOT_ENABLED"
        return finish()

    before_lease = clock()
    remaining = 10.0 - (before_lease - started)
    if remaining <= 0:
        answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
        return finish()
    acquired, release_started = False, None
    answer["phase"] = "lease"
    try:
        with concurrency.native_execution("LIVE-" + uuid.uuid4().hex[:16].upper(),
                                           kind=operation, wait_seconds=min(2.0, remaining)):
            acquired = True
            entered = clock()
            answer["timing_ms"]["lease"] = max(0.0, (entered - before_lease) * 1000)
            answer["phase"] = "validation"
            if entered - started >= 10.0:
                answer["reason_code"] = "LIVE_DEADLINE_EXCEEDED"
            else:
                try:
                    resolved = validate_local_target(root, _inventory_rows(root), requested,
                                                     capability="inventory")
                    answer["resolved_target"] = {"schema": "fleet.target/1",
                        **{key: resolved[key] for key in ("device_id", "terminal_id", "terminal_generation")}}
                    if "route_generation" in requested:
                        answer["resolved_target"]["route_generation"] = None
                    binding = resolved["binding"]
                    answer["identity"] = {"identity_source": resolved["identity_source"],
                        "identity_revision": resolved["identity_revision"], "alias": resolved["alias"],
                        "binding": {"executable": binding["terminal_canonical_path"],
                                    "data_root": binding["data_canonical_path"]}}
                    # This is a permanently unavailable live_read admission. M0
                    # inventory validation above never grants SDK or native effects.
                    answer["reason_code"] = ("LIVE_DEADLINE_EXCEEDED" if clock() - started >= 10.0
                                             else "LIVE_ATTACH_ONLY_UNPROVEN")
                except IdentityError as error:
                    answer["reason_code"] = error.code if error.code in IDENTITY_CODES else "IDENTITY_INVALID"
                except Exception:
                    answer["reason_code"] = "IDENTITY_INVALID"
            # No early return: exact common-lease release precedes every receipt.
            release_started = clock()
        answer["timing_ms"]["release"] = max(0.0, (clock() - release_started) * 1000)
        answer["ownership"]["status"] = "RELEASED"
    except Exception as error:
        if acquired:
            if release_started is not None:
                answer["timing_ms"]["release"] = max(0.0, (clock() - release_started) * 1000)
            answer["primary_reason_code"] = answer["reason_code"]
            answer["reason_code"] = "LIVE_CLEANUP_UNPROVEN"
            answer["phase"] = "release"
            answer["ownership"]["status"] = "RECOVERY_REQUIRED"
            answer["cleanup"]["reason_code"] = "LIVE_CLEANUP_UNPROVEN"
        else:
            answer["timing_ms"]["lease"] = max(0.0, (clock() - before_lease) * 1000)
            answer["reason_code"] = "LIVE_LEASE_UNAVAILABLE" if isinstance(error, TimeoutError) else "LIVE_RECOVERY_REQUIRED"
    return finish()
