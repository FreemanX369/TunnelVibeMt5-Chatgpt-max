"""Bounded research protocol. No execution permissions or production qualification."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

REQUEST_SCHEMA = "sdk.read.request/1"
RESULT_SCHEMA = "sdk.read.result/1"
MAX_BYTES = 32768
EVIDENCE = {"SYNTHETIC_SDK_ONLY", "REAL_SDK_UNQUALIFIED", "HARMLESS_NATIVE_STUB_ONLY"}
REASONS = {None, "LIVE_ATTACH_ONLY_UNPROVEN", "LIVE_PROCESS_UNAVAILABLE", "TERMINAL_NOT_RUNNING",
           "LIVE_IPC_INITIALIZE_FAILED", "LIVE_BINDING_MISMATCH", "LIVE_OBSERVATION_UNAVAILABLE",
           "LIVE_DEADLINE_EXCEEDED", "LIVE_CLEANUP_UNPROVEN", "WORKER_RESULT_INVALID",
           "WORKER_START_UNPROVEN", "PROTOCOL_INVALID"}
TERMINAL_FIELDS = {"alias", "build", "connected", "ping_last_us", "ping_ms", "trade_allowed"}
ACCOUNT_FIELDS = {"status", "present", "login_masked", "server", "currency", "trade_mode",
                  "margin_mode", "leverage", "balance", "equity", "profit", "credit", "margin",
                  "free_margin", "margin_level", "trade_allowed", "expert_trade_allowed",
                  "positions_count", "orders_count"}


class ProtocolError(ValueError):
    def __init__(self):
        super().__init__("PROTOCOL_INVALID")


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ProtocolError() from error


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _finite(number):
    try:
        return math.isfinite(number)
    except (ValueError, TypeError, OverflowError):
        return False


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProtocolError()
        result[key] = value
    return result


def read_bounded(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ProtocolError()
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError()))
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise ProtocolError() from error


def write_bounded(path, value):
    raw = canonical(value)
    if len(raw) > MAX_BYTES:
        raise ProtocolError()
    # Unique disposable paths are owned by the research controller; no state overwrite.
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _path(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 4096
            or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value) or not os.path.isabs(value)
            or os.path.normpath(value) != value):
        raise ProtocolError()
    return os.path.normcase(os.path.realpath(value))


def validate_request(value):
    if (not isinstance(value, dict) or set(value) != {"schema", "operation", "nonce", "binding", "budget_ms"}
            or value["schema"] != REQUEST_SCHEMA or value["operation"] != "state"
            or not isinstance(value["nonce"], str) or re.fullmatch(r"[a-f0-9]{32}", value["nonce"]) is None
            or type(value["budget_ms"]) is not int or not 1 <= value["budget_ms"] <= 10000):
        raise ProtocolError()
    binding = value["binding"]
    if not isinstance(binding, dict) or set(binding) != {"executable", "data_root", "process"}:
        raise ProtocolError()
    executable = _path(binding["executable"])
    _path(binding["data_root"])
    process = binding["process"]
    if (not isinstance(process, dict) or set(process) != {"pid", "creation", "image"}
            or type(process["pid"]) is not int or not 1 <= process["pid"] <= 0xFFFFFFFF
            or not isinstance(process["creation"], str)
            or re.fullmatch(r"[0-9]{1,32}", process["creation"]) is None
            or int(process["creation"]) <= 0 or _path(process["image"]) != executable):
        raise ProtocolError()
    if len(canonical(value)) > MAX_BYTES:
        raise ProtocolError()
    return value


def result(request, *, evidence, reason="LIVE_ATTACH_ONLY_UNPROVEN"):
    validate_request(request)
    if not isinstance(evidence, str) or evidence not in EVIDENCE or not isinstance(reason, str) or reason not in REASONS:
        raise ProtocolError()
    return {"schema": RESULT_SCHEMA, "operation": "state", "nonce": request["nonce"],
            "request_sha256": digest(request), "evidence": evidence, "status": "FAILED",
            "reason_code": reason, "primary_reason_code": None, "observed_binding": None,
            "observed_at_utc": None, "terminal": None, "account": None,
            "cleanup": {"status": "NOT_ATTEMPTED", "reason_code": None},
            "timing_ms": {"total": 0.0, "expired": False}}


def validate_result(value, request):
    expected_fields = set(result(request, evidence="REAL_SDK_UNQUALIFIED"))
    if (not isinstance(value, dict) or set(value) != expected_fields
            or value["schema"] != RESULT_SCHEMA or value["operation"] != "state"
            or value["nonce"] != request["nonce"] or value["request_sha256"] != digest(request)
            or not isinstance(value["evidence"], str) or value["evidence"] not in EVIDENCE
            or not isinstance(value["status"], str) or value["status"] not in {"SUCCEEDED", "FAILED"}
            or (value["reason_code"] is not None and (not isinstance(value["reason_code"], str) or value["reason_code"] not in REASONS))
            or (value["primary_reason_code"] is not None and (not isinstance(value["primary_reason_code"], str) or value["primary_reason_code"] not in REASONS))):
        raise ProtocolError()
    cleanup, timing = value["cleanup"], value["timing_ms"]
    if (not isinstance(cleanup, dict) or set(cleanup) != {"status", "reason_code"}
            or not isinstance(cleanup["status"], str) or cleanup["status"] not in {"NOT_ATTEMPTED", "RETURNED", "UNPROVEN"}
            or (cleanup["reason_code"] is not None and cleanup["reason_code"] != "LIVE_CLEANUP_UNPROVEN")
            or (cleanup["status"] == "UNPROVEN") != (cleanup["reason_code"] == "LIVE_CLEANUP_UNPROVEN")
            or not isinstance(timing, dict) or set(timing) != {"total", "expired"}
            or type(timing["total"]) not in (int, float) or not _finite(timing["total"])
            or timing["total"] < 0 or type(timing["expired"]) is not bool
            or timing["expired"] != (timing["total"] >= request["budget_ms"])):
        raise ProtocolError()
    if value["status"] == "FAILED":
        if value["reason_code"] is None or any(value[k] is not None for k in ("terminal", "account", "observed_at_utc")):
            raise ProtocolError()
    else:
        terminal, account = value["terminal"], value["account"]
        if (value["reason_code"] is not None or value["primary_reason_code"] is not None
                or cleanup != {"status": "RETURNED", "reason_code": None} or timing["expired"]
                or not isinstance(terminal, dict) or set(terminal) != TERMINAL_FIELDS
                or not isinstance(account, dict) or set(account) != ACCOUNT_FIELDS
                or not isinstance(value["observed_at_utc"], str) or not 1 <= len(value["observed_at_utc"]) <= 64
                or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value["observed_at_utc"])):
            raise ProtocolError()
        if terminal["alias"] != "Q2-RESEARCH" or account["status"] not in ("CONNECTED", "UNAVAILABLE_DISCONNECTED"):
            raise ProtocolError()
        login = account["login_masked"]
        # Legacy conversion shows at most the last four digits; never accept a raw login.
        if login is not None and (not isinstance(login, str) or re.fullmatch(r"\*+[0-9]{1,4}", login) is None):
            raise ProtocolError()
        for field in ("server", "currency"):
            if account[field] is not None and (not isinstance(account[field], str) or len(account[field]) > 256
                    or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in account[field])):
                raise ProtocolError()
        bool_fields = {"connected", "present", "trade_allowed", "expert_trade_allowed"}
        int_fields = {"build", "ping_last_us", "trade_mode", "margin_mode", "leverage", "positions_count", "orders_count"}
        for obj in (terminal, account):
            for field, number in obj.items():
                if field in {"alias", "status", "login_masked", "server", "currency"} or number is None:
                    continue
                allowed = (bool,) if field in bool_fields else (int,) if field in int_fields else (int, float)
                if type(number) not in allowed or not _finite(number):
                    raise ProtocolError()
        if (terminal["connected"] is True and (account["status"] != "CONNECTED" or account["present"] is not True)):
            raise ProtocolError()
        if terminal["connected"] is not True and account["status"] != "UNAVAILABLE_DISCONNECTED":
            raise ProtocolError()
        if account["status"] == "UNAVAILABLE_DISCONNECTED" and any(
                account[field] is not None for field in ACCOUNT_FIELDS - {"status"}):
            raise ProtocolError()
    observed = value["observed_binding"]
    if observed is not None:
        if observed != request["binding"]:
            raise ProtocolError()
    if value["status"] == "SUCCEEDED" and observed is None:
        raise ProtocolError()
    if len(canonical(value)) > MAX_BYTES:
        raise ProtocolError()
    return value
