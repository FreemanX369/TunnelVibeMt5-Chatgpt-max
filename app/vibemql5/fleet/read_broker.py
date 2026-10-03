"""Bounded ephemeral read commands and truthful per-target snapshots."""
from __future__ import annotations

import copy
import math
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .wire import WireError, encode_body, fields, integer, logical_digest, text

OPERATIONS = frozenset({"get_terminal_live_state", "get_account_snapshot"})


@dataclass(frozen=True)
class FleetPolicy:
    max_body_bytes: int
    max_response_bytes: int
    http_timeout_ms: int
    max_pending_reads: int
    max_retained_results: int
    max_targets: int
    max_poll_commands: int
    read_deadline_ms: int
    session_timeout_ms: int
    heartbeat_interval_ms: int
    poll_interval_ms: int
    freshness_ms: int
    max_clock_future_ms: int
    max_rows: int
    max_owner_token_bytes: int
    max_operation_id_bytes: int

    def __post_init__(self):
        for name, value in asdict(self).items():
            integer(value, minimum=0 if name == "max_clock_future_ms" else 1)
        ceilings = {"max_body_bytes": 1048576, "max_response_bytes": 1048576,
            "http_timeout_ms": 60000, "max_pending_reads": 10000, "max_retained_results": 100000,
            "max_targets": 64, "max_poll_commands": 64, "read_deadline_ms": 60000,
            "session_timeout_ms": 3600000, "heartbeat_interval_ms": 60000, "poll_interval_ms": 60000,
            "freshness_ms": 3600000, "max_clock_future_ms": 60000, "max_rows": 10000,
            "max_owner_token_bytes": 4096, "max_operation_id_bytes": 512}
        if any(getattr(self, name) > maximum for name, maximum in ceilings.items()):
            raise WireError("WIRE_INVALID")
        if self.heartbeat_interval_ms >= self.session_timeout_ms or self.max_poll_commands > self.max_pending_reads or self.max_targets > self.max_rows:
            raise WireError("WIRE_INVALID")


def target(value):
    fields(value, {"schema", "device_id", "route_generation", "terminal_id", "terminal_generation"})
    if value["schema"] != "fleet.target/1" or type(value["device_id"]) is not str or type(value["terminal_id"]) is not str:
        raise WireError("TARGET_MISMATCH")
    if not re.fullmatch(r"dev_[0-9a-f]{32}", value["device_id"]) or not re.fullmatch(r"term_[0-9a-f]{32}", value["terminal_id"]):
        raise WireError("TARGET_MISMATCH")
    integer(value["route_generation"], minimum=1); integer(value["terminal_generation"], minimum=1)
    return copy.deepcopy(value)


def unavailable(command, code):
    return {"schema": "fleet.read/1", "operation": command["operation"], "status": "FAILED",
        "reason_code": code, "requested_target": command["target"], "resolved_target": None,
        "source": None, "observed_at_utc": None, "terminal": None, "account": None}


def _observed_ms(value):
    if type(value) is not str or len(value) > 40:
        raise WireError("READ_RESULT_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError()
        return int(parsed.timestamp() * 1000)
    except (ValueError, OverflowError):
        raise WireError("READ_RESULT_INVALID") from None


TERMINAL_FIELDS = {"alias", "build", "connected", "ping_last_us", "ping_ms", "trade_allowed"}
ACCOUNT_FIELDS = {"status", "present", "login_masked", "server", "currency", "trade_mode", "margin_mode",
    "leverage", "balance", "equity", "profit", "credit", "margin", "free_margin", "margin_level",
    "trade_allowed", "expert_trade_allowed", "positions_count", "orders_count"}


def _validate_live_payload(value):
    terminal, account = value["terminal"], value["account"]
    fields(terminal, TERMINAL_FIELDS); fields(account, ACCOUNT_FIELDS)
    text(terminal["alias"], 128)
    if type(terminal["connected"]) is not bool:
        raise WireError("READ_RESULT_INVALID")
    if value.get("cleanup") != {"status": "PROVEN", "reason_code": None} or value.get("ownership") != {"status": "CLOSED"}:
        raise WireError("READ_RESULT_INVALID")
    binding = value.get("observed_binding")
    fields(binding, {"executable", "data_root", "process", "alias"})
    if binding["alias"] != terminal["alias"]:
        raise WireError("READ_RESULT_MISMATCH")
    text(binding["executable"], 4096); text(binding["data_root"], 4096)
    process = fields(binding["process"], {"pid", "creation", "image"})
    integer(process["pid"], minimum=1)
    if type(process["creation"]) is not str or not re.fullmatch(r"[0-9]{1,32}", process["creation"]) or int(process["creation"]) <= 0:
        raise WireError("READ_RESULT_INVALID")
    text(process["image"], 4096)
    if process["image"] != binding["executable"]:
        raise WireError("READ_RESULT_MISMATCH")
    login = account["login_masked"]
    if login is not None and (type(login) is not str or not re.fullmatch(r"\*+[0-9]{1,4}", login) or len(login) > 64):
        raise WireError("READ_RESULT_INVALID")
    for name in ("server", "currency"):
        if account[name] is not None:
            text(account[name], 256)
    bool_fields = {"connected", "present", "trade_allowed", "expert_trade_allowed"}
    int_fields = {"build", "ping_last_us", "trade_mode", "margin_mode", "leverage", "positions_count", "orders_count"}
    for obj in (terminal, account):
        for name, number in obj.items():
            if name in {"alias", "status", "login_masked", "server", "currency"} or number is None:
                continue
            types = (bool,) if name in bool_fields else (int,) if name in int_fields else (int, float)
            if type(number) not in types:
                raise WireError("READ_RESULT_INVALID")
            if name not in bool_fields:
                try:
                    if not math.isfinite(number) or abs(number) > (1 << 63) - 1:
                        raise ValueError()
                except (ValueError, OverflowError):
                    raise WireError("READ_RESULT_INVALID") from None
    if terminal["connected"]:
        if account["status"] != "CONNECTED" or account["present"] is not True:
            raise WireError("READ_RESULT_INVALID")
    elif account["status"] != "UNAVAILABLE_DISCONNECTED" or any(account[k] is not None for k in ACCOUNT_FIELDS - {"status"}):
        raise WireError("READ_RESULT_INVALID")


class ReadBroker:
    """Single gateway event owner; restart makes unknown read IDs interrupted.

    This journal is deliberately for observations only, never effectful commands.
    Native domain delivery uses the durable TIP-060 journal.
    """
    def __init__(self, policy):
        self.policy = policy
        self._commands = {}
        self._operations = {}
        self._results = {}
        self._synthetic_fixture = False

    @classmethod
    def for_synthetic_tests(cls, policy):
        result = cls(policy)
        result._synthetic_fixture = True
        return result

    def _expire(self, monotonic_ms):
        for command_id, row in self._commands.items():
            if command_id not in self._results and monotonic_ms >= row["expires_monotonic_ms"]:
                self._results[command_id] = unavailable(row["command"], "READ_DEADLINE_EXCEEDED")

    def submit(self, operation, requested_target, *, operation_id, now_ms, monotonic_ms, current_route):
        requested_target = target(requested_target)
        if operation not in OPERATIONS:
            raise WireError("READ_OPERATION_INVALID")
        text(operation_id, self.policy.max_operation_id_bytes)
        integer(now_ms); integer(monotonic_ms)
        request = {"schema": "fleet.read-request/1", "operation": operation, "target": requested_target}
        digest = logical_digest(request)
        prior = self._operations.get(operation_id)
        if prior:
            if prior["request_sha256"] != digest:
                raise WireError("READ_OPERATION_CONFLICT")
            return copy.deepcopy(prior)
        self._expire(monotonic_ms)
        if len(self._commands) >= self.policy.max_retained_results or sum(k not in self._results for k in self._commands) >= self.policy.max_pending_reads:
            raise WireError("READ_CAPACITY")
        self._route(requested_target, current_route)
        command = {"schema": "fleet.read-command/1", "kind": "READ", "command_id": "read_" + uuid.uuid4().hex,
            "target": requested_target, "operation": operation, "request_sha256": digest,
            "deadline_ms": now_ms + self.policy.read_deadline_ms}
        row = {"command": command, "expires_monotonic_ms": monotonic_ms + self.policy.read_deadline_ms,
               "session_id": None, "delivered": False}
        self._commands[command["command_id"]] = row
        receipt = {"schema": "fleet.read-queued/1", "command_id": command["command_id"],
                   "target": requested_target, "request_sha256": digest, "deadline_ms": command["deadline_ms"]}
        self._operations[operation_id] = receipt
        return copy.deepcopy(receipt)

    @staticmethod
    def _route(requested_target, route):
        if (route["device_id"] != requested_target["device_id"] or route["route_generation"] != requested_target["route_generation"]
                or route["state"] != "ACTIVE" or route["status"] != "READY_CONTROL_ONLY"):
            raise WireError("READ_ROUTE_STALE")

    def poll(self, device_id, route_generation, session_id, *, now_ms, monotonic_ms, limit, current_route):
        integer(limit, minimum=1, maximum=self.policy.max_poll_commands)
        self._expire(monotonic_ms)
        commands = []
        for command_id, row in self._commands.items():
            command = row["command"]
            if command_id in self._results or command["target"]["device_id"] != device_id:
                continue
            try:
                self._route(command["target"], current_route)
            except WireError:
                self._results[command_id] = unavailable(command, "READ_ROUTE_STALE")
                continue
            if command["target"]["route_generation"] != route_generation:
                continue
            if row["session_id"] not in (None, session_id):
                self._results[command_id] = unavailable(command, "READ_SESSION_INTERRUPTED")
                continue
            row["session_id"], row["delivered"] = session_id, True
            commands.append(copy.deepcopy(command))
            if len(commands) == limit:
                break
        return commands

    def authorize(self, command_id, requested_target, request_sha256, *, device_id, route_generation, session_id, monotonic_ms, current_route):
        text(command_id, 64)
        requested_target = target(requested_target)
        self._expire(monotonic_ms)
        row = self._commands.get(command_id)
        if row is None:
            raise WireError("READ_INTERRUPTED")
        command = row["command"]
        self._route(command["target"], current_route)
        if (not row["delivered"] or row["session_id"] != session_id or requested_target != command["target"]
                or device_id != command["target"]["device_id"] or route_generation != command["target"]["route_generation"]
                or request_sha256 != command["request_sha256"]):
            raise WireError("READ_ADMISSION_MISMATCH")
        if command_id in self._results:
            raise WireError("READ_ADMISSION_CLOSED")
        return {"schema": "fleet.read-admission/1", "command_id": command_id, "target": copy.deepcopy(requested_target),
                "request_sha256": request_sha256, "session_id": session_id, "deadline_ms": command["deadline_ms"]}

    def commit(self, value, *, device_id, route_generation, session_id, now_ms, monotonic_ms, current_route):
        fields(value, {"schema", "session_id", "command_id", "target", "request_sha256", "result"})
        if value["schema"] != "fleet.result/1" or value["session_id"] != session_id:
            raise WireError("READ_RESULT_INVALID")
        text(value["command_id"], 64)
        row = self._commands.get(value["command_id"])
        if row is None:
            raise WireError("READ_INTERRUPTED")
        command = row["command"]
        if (not row["delivered"] or row["session_id"] != session_id or command["target"] != target(value["target"])
                or command["target"]["device_id"] != device_id or command["target"]["route_generation"] != route_generation
                or command["request_sha256"] != value["request_sha256"]):
            raise WireError("READ_RESULT_MISMATCH")
        self._route(command["target"], current_route)
        self._expire(monotonic_ms)
        result = self._validate_result(value["result"], command, now_ms)
        if value["command_id"] in self._results:
            prior = self._results[value["command_id"]]
            if prior != result:
                raise WireError("READ_RESULT_CONFLICT" if prior["reason_code"] != "READ_DEADLINE_EXCEEDED" else "READ_RESULT_LATE")
            return {"schema": "fleet.read-commit/1", "command_id": value["command_id"], "recovered": True}
        self._results[value["command_id"]] = result
        return {"schema": "fleet.read-commit/1", "command_id": value["command_id"], "recovered": False}

    def _validate_result(self, value, command, now_ms):
        required = {"schema", "operation", "status", "reason_code", "requested_target", "resolved_target", "source", "observed_at_utc", "terminal", "account"}
        optional = {"primary_reason_code", "identity", "observed_binding", "phase", "budget", "timing_ms", "cleanup", "ownership"}
        if type(value) is not dict or not required <= set(value) or set(value) - required - optional:
            raise WireError("READ_RESULT_INVALID")
        def no_arrays(item):
            if type(item) is list:
                raise WireError("READ_RESULT_INVALID")
            if type(item) is dict:
                for child in item.values():
                    no_arrays(child)
        no_arrays(value)
        encode_body(value, self.policy.max_body_bytes)
        if value["schema"] != "fleet.read/1" or value["operation"] != command["operation"] or value["requested_target"] != command["target"]:
            raise WireError("READ_RESULT_MISMATCH")
        if value["status"] not in {"SUCCEEDED", "FAILED"}:
            raise WireError("READ_RESULT_INVALID")
        if value["status"] == "FAILED":
            text(value["reason_code"], 128)
            if any(value[k] is not None for k in ("account", "terminal", "source", "observed_at_utc")):
                raise WireError("READ_RESULT_INVALID")
        else:
            if value["reason_code"] is not None or value["resolved_target"] != command["target"]:
                raise WireError("READ_RESULT_MISMATCH")
            allowed_sources = {"NODE_LIVE_QUALIFIED"} | ({"SYNTHETIC_TEST"} if self._synthetic_fixture else set())
            if value["source"] not in allowed_sources:
                raise WireError("READ_RESULT_INVALID")
            observed = _observed_ms(value["observed_at_utc"])
            if observed > now_ms + self.policy.max_clock_future_ms or now_ms - observed > self.policy.freshness_ms:
                raise WireError("READ_RESULT_STALE")
            _validate_live_payload(value)
        # Exclude internal diagnostic dictionaries from the public result. They
        # are not a channel for arbitrary node fields, credentials or paths.
        public = {key: value[key] for key in required}
        if value["status"] == "SUCCEEDED":
            public.update({key: value[key] for key in ("observed_binding", "cleanup", "ownership")})
        return copy.deepcopy(public)

    def status(self, command_id, *, monotonic_ms, current_route=None):
        text(command_id, 64)
        self._expire(monotonic_ms)
        if command_id not in self._commands:
            raise WireError("READ_INTERRUPTED")
        command = self._commands[command_id]["command"]
        if current_route is not None:
            try:
                self._route(command["target"], current_route)
            except WireError:
                return {"schema": "fleet.read-status/1", "command_id": command_id, "status": "FAILED", "result": unavailable(command, "READ_ROUTE_STALE")}
        result = self._results.get(command_id)
        return {"schema": "fleet.read-status/1", "command_id": command_id,
                "status": "PENDING" if result is None else result["status"], "result": copy.deepcopy(result)}


def snapshot_rows(requested_targets, results, *, now_ms, freshness_ms):
    """No monetary aggregation or account-key inference."""
    rows = []
    succeeded = 0
    for requested_target, result in zip(requested_targets, results, strict=True):
        requested_target = target(requested_target)
        status, reason = result.get("status", "FAILED"), result.get("reason_code", "READ_UNAVAILABLE")
        source, observed = result.get("source"), result.get("observed_at_utc")
        age = None
        if observed is not None:
            try:
                observed_ms = _observed_ms(observed)
                if observed_ms > now_ms:
                    raise WireError("READ_RESULT_INVALID")
                age = now_ms - observed_ms
            except WireError:
                status, reason, source, observed = "FAILED", "READ_RESULT_INVALID", None, None
        fresh = age is not None and age <= freshness_ms
        if status == "SUCCEEDED":
            try:
                if source not in {"NODE_LIVE_QUALIFIED", "SYNTHETIC_TEST"} or result.get("resolved_target") != requested_target:
                    raise WireError("READ_RESULT_INVALID")
                _validate_live_payload(result)
            except WireError:
                status, reason, source, observed, age, fresh = "FAILED", "READ_RESULT_INVALID", None, None, None, False
        if status == "SUCCEEDED" and not fresh:
            status, reason = "FAILED", "READ_RESULT_STALE"
        if result.get("requested_target") != requested_target:
            status, reason, source, observed, age, fresh = "FAILED", "READ_RESULT_MISMATCH", None, None, None, False
        succeeded += status == "SUCCEEDED"
        rows.append({"target": requested_target, "status": status, "reason_code": reason,
            "source": source, "observed_at_utc": observed, "age_ms": age, "fresh": fresh,
            "terminal": result.get("terminal") if status == "SUCCEEDED" else None,
            "account": result.get("account") if status == "SUCCEEDED" and result.get("terminal", {}).get("connected") else None})
    return {"schema": "fleet.snapshot/1", "atomic": False, "rows": rows,
            "coverage": {"requested": len(rows), "succeeded": succeeded, "failed": len(rows) - succeeded}}
