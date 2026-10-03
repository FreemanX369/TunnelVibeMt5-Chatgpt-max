"""Singleton HTTPS event owner and outbound node/client transport.

No service is spawned by a client. Default node reads have no SDK/process branch.
"""
from __future__ import annotations

import copy
import hashlib
import http.client
import io
import re
import secrets
import ssl
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future, wait
from queue import Queue, Empty, Full
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .gateway_control import GatewayControlError
from .identity import IdentityError, IdentityRegistry
from .read_broker import FleetPolicy, ReadBroker, OPERATIONS, snapshot_rows, target, unavailable
from .reads import _inventory_rows
from .wire import (PATHS, WireError, decode_body, encode_body, fields, https_origin, integer,
                   sign_request, text, verified, verify_request, logical_digest)

OWNER_PATHS = frozenset({"/fleet/v1/reads", "/fleet/v1/read-status", "/fleet/v1/admin/grant",
                         "/fleet/v1/admin/revoke", "/fleet/v1/admin/rotate"})

DOMAIN_OWNER_PATHS = frozenset("/fleet/v1/" + path for path in (
    "info", "inventory", "commands/status", "projects/create", "projects/enroll", "projects/get",
    "projects/default-target", "projects/freeze", "projects/resume", "projects/baseline", "jobs/launch",
    "jobs/status", "jobs/cancel", "jobs/recover", "artifacts/manifest", "artifacts/chunk", "principals/issue",
    "principals/revoke", "principals/assign", "principals/release", "principals/reconcile"))
DOMAIN_PRINCIPAL_PATHS = frozenset("/fleet/v1/" + path for path in (
    "writers/acquire", "writers/release", "sources/write", "worktrees/prepare", "worktrees/commit", "worktrees/retire"))
DOMAIN_NODE_PATHS = frozenset({"/fleet/v1/native/start", "/fleet/v1/reconcile", "/fleet/v1/writers/authorize", "/fleet/v1/capacity/register", "/fleet/v1/jobs/recovery-witness"})
ALL_PATHS = PATHS | OWNER_PATHS | DOMAIN_OWNER_PATHS | DOMAIN_PRINCIPAL_PATHS


class GatewayController:
    def __init__(self, store, policy, *, audience, owner_token_sha256, broker=None,
                 wall_clock=None, monotonic_clock=None, native_journal=None, domain=None):
        if type(policy) is not FleetPolicy:
            raise WireError("WIRE_INVALID")
        https_origin(audience)
        if type(owner_token_sha256) is not str or len(owner_token_sha256) != 64:
            raise WireError("OWNER_CONFIG_INVALID")
        try:
            bytes.fromhex(owner_token_sha256)
        except ValueError:
            raise WireError("OWNER_CONFIG_INVALID") from None
        self.store, self.policy, self._audience = store, policy, audience
        self.owner_token_sha256 = owner_token_sha256
        self.broker = broker or ReadBroker(policy)
        self.wall_clock, self.monotonic_clock = wall_clock or time.time, monotonic_clock or time.monotonic
        self.native_journal, self.domain = native_journal, domain
        self.sessions = {}
        self._owner_thread = threading.get_ident()

    @property
    def audience(self):
        return self._audience

    def _times(self):
        return int(self.wall_clock() * 1000), int(self.monotonic_clock() * 1000)

    def _owner(self, header_pairs):
        auth = [value for name, value in header_pairs if name.lower() == "authorization"]
        if len(auth) != 1 or not auth[0].startswith("Bearer "):
            raise WireError("OWNER_UNAUTHORIZED")
        token = auth[0][7:]
        text(token, self.policy.max_owner_token_bytes)
        if len(token) < 32 or not secrets.compare_digest(hashlib.sha256(token.encode("utf-8")).hexdigest(), self.owner_token_sha256):
            raise WireError("OWNER_UNAUTHORIZED")

    def _session(self, proof, session_id, now_ms, monotonic_ms, *, heartbeat=False):
        text(session_id, 64)
        prior = self.sessions.get(proof.device_id)
        same = prior is not None and prior["session_id"] == session_id and prior["route_generation"] == proof.route_generation
        active = prior is not None and monotonic_ms < prior["expires_monotonic_ms"]
        if active and prior["route_generation"] == proof.route_generation and not same:
            raise WireError("NODE_SESSION_CONFLICT")
        if not heartbeat and (not same or not active):
            raise WireError("NODE_SESSION_REQUIRED")
        if heartbeat:
            if prior is None and len(self.sessions) >= self.store.policy.max_devices:
                raise WireError("NODE_SESSION_CAPACITY")
            self.sessions[proof.device_id] = {"device_id": proof.device_id,
                "route_generation": proof.route_generation, "session_id": session_id,
                "last_seen_ms": now_ms, "expires_monotonic_ms": monotonic_ms + self.policy.session_timeout_ms,
                "transport": "ONLINE", "sdk_status": "UNQUALIFIED"}

    def handle(self, method, path, header_pairs, body):
        header_pairs = list(header_pairs)
        response = self._handle(method, path, header_pairs, body)
        if path in PATHS:
            proof = verify_request(method, path, header_pairs, body, audience=self.audience,
                                   max_body_bytes=self.policy.max_body_bytes)
            response = {**response, "control_head": self.store.control_head(),
                        "transport_request_sha256": proof.request_sha256}
        return response

    def _handle(self, method, path, header_pairs, body):
        if threading.get_ident() != self._owner_thread:
            raise WireError("GATEWAY_OWNER_THREAD_REQUIRED")
        if method != "POST" or path not in ALL_PATHS:
            raise WireError("WIRE_INVALID")
        now_ms, monotonic_ms = self._times()
        header_pairs = list(header_pairs)
        if path in DOMAIN_PRINCIPAL_PATHS:
            if self.domain is None:
                raise WireError("DOMAIN_NOT_CONFIGURED")
            value = decode_body(body, self.policy.max_body_bytes)
            return self.domain.handle_principal(path, header_pairs, value, body_bytes=body, now_ms=now_ms, monotonic_ms=monotonic_ms)
        if path in OWNER_PATHS | DOMAIN_OWNER_PATHS:
            self._owner(header_pairs)
            value = decode_body(body, self.policy.max_body_bytes)
            if path in DOMAIN_OWNER_PATHS:
                if self.domain is None:
                    raise WireError("DOMAIN_NOT_CONFIGURED")
                return self.domain.handle_owner(path, value, now_ms=now_ms, monotonic_ms=monotonic_ms)
            return self._owner_request(path, value, now_ms, monotonic_ms)
        proof = verify_request(method, path, header_pairs, body, audience=self.audience,
                               max_body_bytes=self.policy.max_body_bytes)
        if not verified(proof):
            raise WireError("WIRE_UNVERIFIED")
        value = proof.body
        if path == "/fleet/v1/pair":
            fields(value, {"schema", "grant_id", "secret", "operation_id", "expected_revision"})
            if value["schema"] != "fleet.pair/1":
                raise WireError("WIRE_INVALID")
            text(value["operation_id"], self.policy.max_operation_id_bytes)
            return self.store.consume_verified_grant(value["grant_id"], value["secret"], proof.device_id, proof.public_key,
                expected_revision=value["expected_revision"], operation_id="nodepair:" + value["operation_id"],
                now_ms=now_ms, signed_route_generation=proof.route_generation, nonce=proof.nonce,
                request_sha256=proof.request_sha256, timestamp_ms=proof.timestamp_ms)
        if path == "/fleet/v1/reconcile":
            if self.domain is None:
                raise WireError("DOMAIN_NOT_CONFIGURED")
            # This finite recovery lane remains fenced; it admits only exact
            # signed independent journal witnesses through the recovery store.
            return self.domain.handle_node(proof, value, now_ms=now_ms, monotonic_ms=monotonic_ms)
        # The sole event owner cannot revoke/rotate between this atomic current
        # key/route/nonce admission and the following ephemeral read mutation.
        self.store.reserve_nonce(proof.device_id, route_generation=proof.route_generation,
            expected_public_key=proof.public_key, nonce=proof.nonce,
            request_sha256=proof.request_sha256, timestamp_ms=proof.timestamp_ms, now_ms=now_ms)
        route = self.store.get_route(proof.device_id)
        if path == "/fleet/v1/heartbeat":
            fields(value, {"schema", "session_id"})
            if value["schema"] != "fleet.heartbeat/1":
                raise WireError("WIRE_INVALID")
            self._session(proof, value["session_id"], now_ms, monotonic_ms, heartbeat=True)
            return {"schema": "fleet.heartbeat-receipt/1", "device_id": proof.device_id,
                    "route_generation": proof.route_generation, "session_id": value["session_id"],
                    "transport": "ONLINE", "sdk_status": "UNQUALIFIED"}
        if path == "/fleet/v1/poll":
            fields(value, {"schema", "session_id", "max_commands", "mode"})
            if value["schema"] != "fleet.poll/1" or value["mode"] not in {"WORKLOAD", "CANCEL_ONLY"}:
                raise WireError("WIRE_INVALID")
            self._session(proof, value["session_id"], now_ms, monotonic_ms)
            integer(value["max_commands"], minimum=1, maximum=self.policy.max_poll_commands)
            if value["mode"] == "CANCEL_ONLY":
                commands = [] if self.domain is None else self.domain.poll_cancel_for_node(proof, value["session_id"],
                    value["max_commands"], now_ms=now_ms)
                return {"schema": "fleet.poll-receipt/1", "mode": "CANCEL_ONLY", "commands": commands}
            commands = self.broker.poll(proof.device_id, proof.route_generation, value["session_id"],
                now_ms=now_ms, monotonic_ms=monotonic_ms, limit=value["max_commands"], current_route=route)
            if self.domain is not None and len(commands) < value["max_commands"]:
                commands.extend(self.domain.poll_for_node(proof, value["session_id"],
                    value["max_commands"] - len(commands), now_ms=now_ms))
            return {"schema": "fleet.poll-receipt/1", "mode": "WORKLOAD", "commands": commands}
        self._session(proof, value.get("session_id"), now_ms, monotonic_ms)
        if path == "/fleet/v1/read-authorize":
            fields(value, {"schema", "session_id", "command_id", "target", "request_sha256"})
            if value["schema"] != "fleet.read-authorize/1":
                raise WireError("WIRE_INVALID")
            return self.broker.authorize(value["command_id"], value["target"], value["request_sha256"],
                device_id=proof.device_id, route_generation=proof.route_generation, session_id=value["session_id"],
                monotonic_ms=monotonic_ms, current_route=route)
        if path in DOMAIN_NODE_PATHS or value.get("schema") != "fleet.result/1":
            if self.domain is None:
                raise WireError("DOMAIN_NOT_CONFIGURED")
            return self.domain.handle_node(proof, value, now_ms=now_ms, monotonic_ms=monotonic_ms)
        return self.broker.commit(value, device_id=proof.device_id, route_generation=proof.route_generation,
            session_id=value["session_id"], now_ms=now_ms, monotonic_ms=monotonic_ms, current_route=route)

    def _owner_request(self, path, value, now_ms, monotonic_ms):
        if path == "/fleet/v1/reads":
            fields(value, {"schema", "operation", "target", "operation_id"})
            if value["schema"] != "fleet.read-request/1":
                raise WireError("WIRE_INVALID")
            requested = target(value["target"])
            return self.broker.submit(value["operation"], requested, operation_id=value["operation_id"],
                now_ms=now_ms, monotonic_ms=monotonic_ms, current_route=self.store.get_route(requested["device_id"]))
        if path == "/fleet/v1/read-status":
            fields(value, {"schema", "command_id"})
            if value["schema"] != "fleet.read-status-request/1":
                raise WireError("WIRE_INVALID")
            status = self.broker.status(value["command_id"], monotonic_ms=monotonic_ms)
            command = self.broker._commands[value["command_id"]]["command"]
            return self.broker.status(value["command_id"], monotonic_ms=monotonic_ms,
                                     current_route=self.store.get_route(command["target"]["device_id"]))
        common = {"schema", "device_id", "operation_id", "expected_revision", "expected_route_generation"}
        extra = {"public_key"} if path.endswith("/grant") else {"new_public_key", "expected_public_key"} if path.endswith("/rotate") else set()
        fields(value, common | extra)
        if value["schema"] != "fleet.admin/1":
            raise WireError("WIRE_INVALID")
        text(value["operation_id"], self.policy.max_operation_id_bytes)
        args = {key: value[key] for key in common - {"schema", "device_id", "operation_id"}}
        args.update(operation_id="admin:" + value["operation_id"], now_ms=now_ms)
        if path.endswith("/grant"):
            return self.store.issue_grant(value["device_id"], value["public_key"], **args)
        if path.endswith("/rotate"):
            return self.store.rotate_key(value["device_id"], value["new_public_key"], expected_public_key=value["expected_public_key"], **args)
        return self.store.revoke(value["device_id"], **args)


def serve_gateway(address, *, certificate=None, key_file=None, ssl_context=None, controller_factory, stop_event=None, started=None):
    """Run only on explicit operator invocation; factory executes in event thread."""
    if ssl_context is None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(certificate), str(key_file))
    else:
        if (type(ssl_context) is not ssl.SSLContext or ssl_context.protocol != ssl.PROTOCOL_TLS_SERVER
                or ssl_context.minimum_version < ssl.TLSVersion.TLSv1_2):
            raise WireError("TLS_SERVER_CONTEXT_INVALID")
        context = ssl_context
    holder = {}
    class DeadlineInput(io.RawIOBase):
        def __init__(self, connection, started, limit):
            self.connection, self.started, self.limit = connection, started, limit
        def readable(self):
            return True
        def readinto(self, buffer):
            remaining = self.limit - (time.monotonic() - self.started)
            if remaining <= 0:
                raise TimeoutError("HTTP_DEADLINE_EXCEEDED")
            self.connection.settimeout(remaining)
            return self.connection.recv_into(buffer)
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        def setup(self):
            super().setup()
            self.rfile.close()
            self.rfile = io.BufferedReader(DeadlineInput(self.connection,
                self.connection._fleet_started, holder["controller"].policy.http_timeout_ms / 1000))
        def log_message(self, *_):
            pass  # Do not log URLs/headers/grant bodies or TLS key paths.
        def do_POST(self):
            controller = holder["controller"]
            begun = self.connection._fleet_started
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or self.headers.get_all("Transfer-Encoding") or re.fullmatch(r"0|[1-9][0-9]{0,9}", lengths[0]) is None:
                    raise WireError("WIRE_INVALID")
                length = int(lengths[0])
                if length > controller.policy.max_body_bytes:
                    raise WireError("WIRE_TOO_LARGE")
                content = bytearray()
                while len(content) < length:
                    remaining = controller.policy.http_timeout_ms / 1000 - (time.monotonic() - begun)
                    if remaining <= 0:
                        raise WireError("HTTP_DEADLINE_EXCEEDED")
                    self.connection.settimeout(remaining)
                    chunk = self.rfile.read1(min(65536, length - len(content)))
                    if not chunk:
                        raise WireError("WIRE_INVALID")
                    content.extend(chunk)
                result = controller.handle("POST", self.path, self.headers.raw_items(), bytes(content))
                response = encode_body(result, controller.policy.max_response_bytes)
                status = 200
            except (WireError, GatewayControlError) as exc:
                status, response = 409, encode_body({"schema": "fleet.error/1", "code": exc.code}, controller.policy.max_response_bytes)
            except Exception:
                status, response = 500, b'{"schema":"fleet.error/1","code":"GATEWAY_REQUEST_FAILED"}'
            try:
                remaining = controller.policy.http_timeout_ms / 1000 - (time.monotonic() - begun)
                if remaining <= 0:
                    raise TimeoutError()
                self.connection.settimeout(remaining)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.send_header("Connection", "close")
                self.end_headers(); self.wfile.write(response)
            except OSError:
                pass
    class Server(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            begun = time.monotonic()
            connection.settimeout(holder["controller"].policy.http_timeout_ms / 1000)
            try:
                protected = context.wrap_socket(connection, server_side=True)
                protected._fleet_started = begun
                return protected, address
            except Exception:
                connection.close()
                raise
    with Server(address, Handler) as server:
        controller = controller_factory(server.server_address)
        holder["controller"] = controller
        server.timeout = min(0.2, controller.policy.poll_interval_ms / 1000)
        if started:
            started(server.server_address)
        try:
            while stop_event is None or not stop_event.is_set():
                server.handle_request()
        finally:
            try:
                if controller.domain is not None and hasattr(controller.domain, "close"):
                    controller.domain.close()
                elif controller.native_journal is not None:
                    controller.native_journal.close()
            finally:
                controller.store.close()


class HttpsClient:
    def __init__(self, origin, policy, *, cafile=None, ssl_context=None):
        self._origin, self.policy = https_origin(origin), policy
        self.context = ssl_context or ssl.create_default_context(cafile=cafile)
        self._tls()
        self._parsed = urlsplit(origin)
    @property
    def origin(self):
        return self._origin
    def _tls(self):
        if not isinstance(self.context, ssl.SSLContext) or self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise WireError("TLS_VERIFICATION_REQUIRED")
        self.context.minimum_version = max(self.context.minimum_version, ssl.TLSVersion.TLSv1_2)
    def post(self, path, value, headers=None, *, deadline_monotonic=None):
        self._tls()
        if path not in ALL_PATHS:
            raise WireError("WIRE_INVALID")
        body = encode_body(value, self.policy.max_body_bytes)
        supplied = dict(headers or {})
        if any(k.lower() in {"host", "content-length", "transfer-encoding"} for k in supplied):
            raise WireError("WIRE_INVALID")
        begun = time.monotonic()
        deadline = min(begun + self.policy.http_timeout_ms / 1000, deadline_monotonic) if deadline_monotonic is not None else begun + self.policy.http_timeout_ms / 1000
        if deadline <= begun:
            raise WireError("HTTP_DEADLINE_EXCEEDED")
        connection = http.client.HTTPSConnection(self._parsed.hostname, self._parsed.port or 443,
            timeout=deadline - begun, context=self.context)
        class DeadlineResponseInput(io.RawIOBase):
            def __init__(self, original, protected):
                self.original, self.protected = original, protected
            def readable(self):
                return True
            def readinto(self, buffer):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("HTTP_DEADLINE_EXCEEDED")
                self.protected.settimeout(remaining)
                return self.original.raw.readinto(buffer)
            def close(self):
                self.original.close()
                super().close()
        class DeadlineResponse(http.client.HTTPResponse):
            def __init__(self, protected, *args, **kwargs):
                super().__init__(protected, *args, **kwargs)
                self.fp = io.BufferedReader(DeadlineResponseInput(self.fp, protected))
        connection.response_class = DeadlineResponse
        try:
            connection.request("POST", path, body=body, headers={"Content-Type": "application/json", **supplied})
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WireError("HTTP_DEADLINE_EXCEEDED")
            if connection.sock:
                connection.sock.settimeout(remaining)
            response = connection.getresponse()
            lengths = response.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or re.fullmatch(r"0|[1-9][0-9]{0,9}", lengths[0]) is None or response.headers.get_all("Transfer-Encoding"):
                raise WireError("HTTP_RESPONSE_INVALID")
            length = int(lengths[0])
            if length > self.policy.max_response_bytes:
                raise WireError("WIRE_TOO_LARGE")
            content = bytearray()
            while len(content) < length:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WireError("HTTP_DEADLINE_EXCEEDED")
                response_socket = connection.sock or getattr(getattr(response.fp, "raw", None), "_sock", None)
                if response_socket is not None:
                    response_socket.settimeout(remaining)
                chunk = response.read1(min(65536, length - len(content)))
                if not chunk:
                    raise WireError("HTTP_RESPONSE_INVALID")
                content.extend(chunk)
            result = decode_body(bytes(content), self.policy.max_response_bytes)
            if response.status != 200:
                if result.get("schema") == "fleet.error/1" and type(result.get("code")) is str:
                    raise WireError(text(result["code"], 128))
                raise WireError("HTTP_RESPONSE_INVALID")
            return result
        except (OSError, http.client.HTTPException):
            raise WireError("HTTPS_UNAVAILABLE") from None
        finally:
            connection.close()


_READ_ADMISSION_SEAL = object()


class NodeReadAdmission:
    """One SDK-entry capability issued by this trusted outbound node runtime.

    A caller-supplied HTTP dictionary cannot construct this type. The process
    running the installed node/client/controller remains the trust boundary.
    """
    __slots__ = ("_seal", "_client", "_session", "_command_bytes", "_claimed")
    def __init__(self, client, session_id, command, *, _seal):
        if _seal is not _READ_ADMISSION_SEAL:
            raise WireError("READ_ADMISSION_UNVERIFIED")
        self._seal, self._client, self._session = _seal, client, session_id
        self._command_bytes = encode_body(command, client.http.policy.max_body_bytes)
        self._claimed = False
    def assert_current(self, command):
        if self._seal is not _READ_ADMISSION_SEAL or encode_body(command, self._client.http.policy.max_body_bytes) != self._command_bytes:
            raise WireError("READ_ADMISSION_MISMATCH")
        self._client._check_read_delivery(self._session, command)
        self._client.read_authorize(self._session, command)
        self._client._check_read_delivery(self._session, command)
    def claim(self, command):
        if self._claimed:
            raise WireError("READ_ADMISSION_USED")
        self.assert_current(command)
        self._claimed = True


class NodeClient:
    def __init__(self, http, key, device_id, route_generation, transport_journal=None):
        self.http, self.key, self.device_id, self.route_generation = http, key, device_id, route_generation
        self._pair_routes = {}
        self.transport_journal = transport_journal
        self._read_deliveries, self._read_admissions = {}, set()
    def _post(self, path, value, *, signed_route_generation=None, deadline_monotonic=None):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise WireError("HTTP_DEADLINE_EXCEEDED")
        body = encode_body(value, self.http.policy.max_body_bytes)
        headers = sign_request(self.key, device_id=self.device_id, route_generation=self.route_generation if signed_route_generation is None else signed_route_generation,
            timestamp_ms=int(time.time() * 1000), nonce=secrets.token_hex(24), path=path, body=body, audience=self.http.origin)
        proof = verify_request("POST", path, headers.items(), body, audience=self.http.origin,
                               max_body_bytes=self.http.policy.max_body_bytes)
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise WireError("HTTP_DEADLINE_EXCEEDED")
        intent = self.transport_journal.begin(proof) if self.transport_journal is not None else None
        result = self.http.post(path, value, headers, deadline_monotonic=deadline_monotonic)
        if self.transport_journal is not None:
            self.transport_journal.acknowledge(intent, proof, result)
        return result
    def pair(self, *, grant_id, secret, operation_id, expected_revision):
        if operation_id not in self._pair_routes and len(self._pair_routes) >= self.http.policy.max_retained_results:
            raise WireError("READ_CAPACITY")
        self._pair_routes.setdefault(operation_id, self.route_generation)
        result = self._post("/fleet/v1/pair", {"schema": "fleet.pair/1", "grant_id": grant_id,
            "secret": secret, "operation_id": operation_id, "expected_revision": expected_revision}, signed_route_generation=self._pair_routes[operation_id])
        self.route_generation = result["receipt"]["route_generation"]
        return result
    def heartbeat(self, session_id):
        result = self._post("/fleet/v1/heartbeat", {"schema": "fleet.heartbeat/1", "session_id": session_id})
        if (result.get("schema") != "fleet.heartbeat-receipt/1" or result.get("device_id") != self.device_id
                or result.get("route_generation") != self.route_generation or result.get("session_id") != session_id
                or result.get("transport") != "ONLINE"):
            raise WireError("NODE_RESPONSE_INVALID")
        return result
    def poll(self, session_id, max_commands):
        return self._poll(session_id, max_commands, "WORKLOAD")
    def poll_cancel_only(self, session_id, max_commands):
        return self._poll(session_id, max_commands, "CANCEL_ONLY")
    def _poll(self, session_id, max_commands, mode):
        integer(max_commands, minimum=1, maximum=self.http.policy.max_poll_commands)
        result = self._post("/fleet/v1/poll", {"schema": "fleet.poll/1", "session_id": session_id, "max_commands": max_commands, "mode": mode})
        if (result.get("schema") != "fleet.poll-receipt/1" or result.get("mode") != mode
                or type(result.get("commands")) is not list or len(result["commands"]) > max_commands):
            raise WireError("NODE_RESPONSE_INVALID")
        for command in result["commands"]:
            if type(command) is not dict:
                raise WireError("READ_COMMAND_INVALID")
            if mode == "CANCEL_ONLY" and command.get("kind") != "CANCEL":
                raise WireError("NODE_CONTROL_INVALID")
            if command.get("kind") == "READ":
                self._validate_read_command(command)
                prior = self._read_deliveries.get(command["command_id"])
                if prior is not None and prior != {"session_id": session_id, "command": command}:
                    raise WireError("READ_COMMAND_CONFLICT")
                if prior is None and len(self._read_deliveries) >= self.http.policy.max_retained_results:
                    raise WireError("READ_CAPACITY")
                self._read_deliveries[command["command_id"]] = {"session_id": session_id, "command": copy.deepcopy(command)}
        return result
    def _validate_read_command(self, command):
        fields(command, {"schema", "kind", "command_id", "target", "operation", "request_sha256", "deadline_ms"})
        requested = target(command["target"])
        if (command["schema"] != "fleet.read-command/1" or command["kind"] != "READ" or command["operation"] not in OPERATIONS
                or requested["device_id"] != self.device_id or requested["route_generation"] != self.route_generation
                or command["request_sha256"] != logical_digest({"schema": "fleet.read-request/1", "operation": command["operation"], "target": requested})):
            raise WireError("READ_COMMAND_MISMATCH")
        text(command["command_id"], 64); integer(command["deadline_ms"])
        if command["deadline_ms"] > int(time.time() * 1000) + self.http.policy.read_deadline_ms + self.http.policy.max_clock_future_ms:
            raise WireError("READ_COMMAND_INVALID")
    def _check_read_delivery(self, session_id, command):
        self._validate_read_command(command)
        prior = self._read_deliveries.get(command["command_id"])
        if prior != {"session_id": session_id, "command": command}:
            raise WireError("READ_ADMISSION_UNVERIFIED")
        if int(time.time() * 1000) >= command["deadline_ms"]:
            raise WireError("READ_DEADLINE_EXCEEDED")
    def read_authorize(self, session_id, command):
        self._check_read_delivery(session_id, command)
        result = self._post("/fleet/v1/read-authorize", {"schema": "fleet.read-authorize/1", "session_id": session_id,
            "command_id": command["command_id"], "target": command["target"], "request_sha256": command["request_sha256"]})
        if any(result.get(key) != value for key, value in {"schema": "fleet.read-admission/1", "session_id": session_id,
                "command_id": command["command_id"], "target": command["target"], "request_sha256": command["request_sha256"],
                "deadline_ms": command["deadline_ms"]}.items()):
            raise WireError("READ_ADMISSION_UNVERIFIED")
        return result
    def admit_read(self, session_id, command):
        self._check_read_delivery(session_id, command)
        if command["command_id"] in self._read_admissions:
            raise WireError("READ_ADMISSION_USED")
        proof = NodeReadAdmission(self, session_id, command, _seal=_READ_ADMISSION_SEAL)
        proof.assert_current(command)
        self._read_admissions.add(command["command_id"])
        return proof
    def reconcile(self, value):
        return self._post("/fleet/v1/reconcile", value)
    def terminal_recovery_witness(self, session_id, witness):
        return self._post("/fleet/v1/jobs/recovery-witness", {"schema": "fleet.native-recovery-envelope/1",
            "session_id": session_id, "witness": witness})
    def start_authorize(self, session_id, command, *, deadline_monotonic=None):
        response = self._post("/fleet/v1/native/start", {"schema": "fleet.start-authorize/1",
            "session_id": session_id, "global_job_id": command["global_job_id"],
            "node_operation_id": command["node_operation_id"], "request_sha256": command["request_sha256"],
            "target": command["target"], "phase": command["authorization_phase"],
            "local_job_id": command["local_job_id"], "sequence": command["authorization_sequence"],
            "challenge": command["authorization_challenge"], "event": command["authorization_event"],
            "predecessor": command["authorization_predecessor"], "process_sha256": command["authorization_process_sha256"]},
            deadline_monotonic=deadline_monotonic)
        fields({k: response[k] for k in ("body", "signature") if k in response}, {"body", "signature"})
        return {k: response[k] for k in ("body", "signature")}
    def register_capacity(self, session_id, *, signed_profile, load_receipt_base64, closure_receipt_base64):
        return self._post("/fleet/v1/capacity/register", {"schema": "fleet.capacity-register/1", "session_id": session_id,
            "signed_profile": signed_profile, "load_receipt_base64": load_receipt_base64,
            "closure_receipt_base64": closure_receipt_base64})
    def writers_authorize(self, *, deadline_monotonic=None, **binding):
        required = {"session_id", "operation_id", "project_id", "target", "principal_id", "principal_epoch",
            "assignment_epoch", "writer_epoch", "phase", "intent_sha256", "challenge"}
        if not required <= set(binding) or set(binding) - required - {"phase_acks", "drain_approval"}:
            raise WireError("WIRE_INVALID")
        if "phase_acks" in binding and (type(binding["phase_acks"]) is not list or len(binding["phase_acks"]) > 5):
            raise WireError("WIRE_INVALID")
        if "drain_approval" in binding:
            fields(binding["drain_approval"], {"body", "signature"})
        response = self._post("/fleet/v1/writers/authorize", {"schema": "fleet.writer-authorization-request/1", **binding},
            deadline_monotonic=deadline_monotonic)
        fields({k: response[k] for k in ("body", "signature") if k in response}, {"body", "signature"})
        return {k: response[k] for k in ("body", "signature")}
    def domain_result(self, value, *, deadline_monotonic=None):
        return self._post("/fleet/v1/results", value, deadline_monotonic=deadline_monotonic)
    def result(self, session_id, command, result):
        return self._post("/fleet/v1/results", {"schema": "fleet.result/1", "session_id": session_id,
            "command_id": command["command_id"], "target": command["target"],
            "request_sha256": command["request_sha256"], "result": result})


class OwnerClient:
    def __init__(self, http, token):
        text(token, http.policy.max_owner_token_bytes)
        if len(token) < 32:
            raise WireError("OWNER_UNAUTHORIZED")
        self.http, self._token = http, token
    def _post(self, path, value, *, deadline_monotonic=None):
        return self.http.post(path, value, {"Authorization": "Bearer " + self._token}, deadline_monotonic=deadline_monotonic)
    def read(self, operation, requested_target, operation_id, *, deadline_monotonic=None):
        return self._post("/fleet/v1/reads", {"schema": "fleet.read-request/1", "operation": operation,
            "target": requested_target, "operation_id": operation_id}, deadline_monotonic=deadline_monotonic)
    def read_status(self, command_id, *, deadline_monotonic=None):
        return self._post("/fleet/v1/read-status", {"schema": "fleet.read-status-request/1", "command_id": command_id}, deadline_monotonic=deadline_monotonic)
    def admin(self, operation, request):
        if operation not in {"grant", "revoke", "rotate"}:
            raise WireError("WIRE_INVALID")
        return self._post("/fleet/v1/admin/" + operation, {"schema": "fleet.admin/1", **request})
    def domain_request(self, path, value):
        if path not in DOMAIN_OWNER_PATHS:
            raise WireError("WIRE_INVALID")
        return self._post(path, value)
    def snapshot(self, requested_targets, *, operation="get_account_snapshot"):
        policy = self.http.policy
        if type(requested_targets) is not list or not 1 <= len(requested_targets) <= policy.max_targets or operation not in OPERATIONS:
            raise WireError("WIRE_INVALID")
        requested_targets = [target(t) for t in requested_targets]
        started = time.monotonic()
        deadline = started + policy.read_deadline_ms / 1000
        def observe(requested):
            command = {"operation": operation, "target": requested}
            try:
                queued = self.read(operation, requested, "snapshot-" + uuid.uuid4().hex, deadline_monotonic=deadline)
                while time.monotonic() - started < policy.read_deadline_ms / 1000:
                    status = self.read_status(queued["command_id"], deadline_monotonic=deadline)
                    fields(status, {"schema", "command_id", "status", "result"})
                    if status["schema"] != "fleet.read-status/1" or status["command_id"] != queued["command_id"] or status["status"] not in {"PENDING", "SUCCEEDED", "FAILED"}:
                        raise WireError("READ_RESULT_INVALID")
                    if status["status"] != "PENDING":
                        if type(status["result"]) is not dict:
                            raise WireError("READ_RESULT_INVALID")
                        return status["result"]
                    remaining = policy.read_deadline_ms / 1000 - (time.monotonic() - started)
                    if remaining > 0:
                        time.sleep(min(policy.poll_interval_ms / 1000, remaining))
                return unavailable(command, "READ_DEADLINE_EXCEEDED")
            except WireError as exc:
                return unavailable(command, exc.code)
            except Exception:
                return unavailable(command, "READ_RESULT_INVALID")
        # Bounded concurrency and one total deadline; adapters use no shared
        # connection/socket. Workers have finite HTTP budgets on every request.
        executor = ThreadPoolExecutor(max_workers=min(policy.max_targets, len(requested_targets)))
        futures = [executor.submit(observe, t) for t in requested_targets]
        done, _ = wait(futures, timeout=max(0, deadline - time.monotonic()))
        results = [f.result() if f in done else unavailable({"operation": operation, "target": t}, "READ_DEADLINE_EXCEEDED") for t, f in zip(requested_targets, futures)]
        executor.shutdown(wait=False, cancel_futures=True)
        return snapshot_rows(requested_targets, results, now_ms=int(time.time() * 1000), freshness_ms=policy.freshness_ms)


def denied_local_read(root, command, *, device_id, route_generation):
    """Validate the complete routed reference without projecting away its route."""
    requested = target(command["target"])
    code = "LIVE_ATTACH_ONLY_UNPROVEN"
    try:
        if requested["device_id"] != device_id or requested["route_generation"] != route_generation:
            raise WireError("TARGET_MISMATCH")
        registry = IdentityRegistry(Path(root)); record = registry.load()
        if record is None:
            raise IdentityError("IDENTITY_UNENROLLED", "")
        if record["device_id"] != device_id:
            raise IdentityError("TARGET_UNKNOWN", "")
        row = next((r for r in record["terminals"] if r["terminal_id"] == requested["terminal_id"]), None)
        if row is None:
            raise IdentityError("TARGET_UNKNOWN", "")
        overlay = registry.overlay(_inventory_rows(Path(root))).get(row["alias"].upper())
        if (overlay is None or overlay["identity_revision"] != record["identity_revision"]
                or any(overlay[k] != requested[k] for k in ("device_id", "terminal_id", "terminal_generation"))
                or overlay["identity_status"] != "ENROLLED" or overlay["resource_qualification"] != "QUALIFIED"):
            raise IdentityError("TARGET_MISMATCH", "")
    except (IdentityError, WireError) as exc:
        code = exc.code
    except Exception:
        code = "IDENTITY_INVALID"
    return unavailable(command, code)


class NodeRpcProxy:
    """Trusted effect workers request finite authority through the control owner."""
    def __init__(self, client, requests):
        self._client, self._requests = client, requests
    @property
    def device_id(self):
        return self._client.device_id
    @property
    def route_generation(self):
        return self._client.route_generation
    def _request(self, kind, payload):
        future = Future()
        deadline = time.monotonic() + self._client.http.policy.http_timeout_ms / 1000
        try:
            self._requests.put_nowait((kind, copy.deepcopy(payload), deadline, future))
        except Full:
            raise WireError("NODE_RPC_CAPACITY") from None
        try:
            return future.result(timeout=max(0, deadline - time.monotonic()))
        except TimeoutError:
            future.cancel()
            raise WireError("NODE_RPC_DEADLINE_EXCEEDED") from None
    def start_authorize(self, session_id, command):
        return self._request("START_AUTHORIZE", {"session_id": session_id, "command": command})
    def writers_authorize(self, **binding):
        return self._request("WRITERS_AUTHORIZE", binding)
    def domain_result(self, value):
        return self._request("DOMAIN_RESULT", value)


class OutboundNode:
    def __init__(self, client, root, policy, *, session_id=None, synthetic_read_adapter=None, qualified_read_adapter=None, domain_dispatcher=None):
        self.client, self.root, self.policy = client, Path(root), policy
        self.session_id = session_id or "session_" + uuid.uuid4().hex
        if synthetic_read_adapter is not None and qualified_read_adapter is not None:
            raise WireError("READ_ADAPTER_INVALID")
        if qualified_read_adapter is not None:
            from .sdk_controller import QualifiedReadAdapter
            if not isinstance(qualified_read_adapter, QualifiedReadAdapter):
                raise WireError("READ_ADAPTER_INVALID")
        self._adapter, self._qualified_adapter, self._domain_dispatcher = synthetic_read_adapter, qualified_read_adapter, domain_dispatcher
        self._results = {}
        self._lock = threading.Lock()
        self._rpc = Queue(maxsize=policy.max_pending_reads)
        self.rpc_proxy = NodeRpcProxy(client, self._rpc)
        if domain_dispatcher is not None and hasattr(domain_dispatcher, "bind_control_transport"):
            domain_dispatcher.bind_control_transport(self.rpc_proxy)
    def _service_rpc(self):
        # One authority burst cannot consume a full timeout for every queued
        # worker. Queue uncertainty retains its original absolute deadline;
        # each admitted HTTPS request also borrows this control-round budget.
        round_deadline = time.monotonic() + self.policy.heartbeat_interval_ms / 1000
        for _ in range(self.policy.max_poll_commands):
            if time.monotonic() >= round_deadline:
                break
            try:
                kind, value, deadline, future = self._rpc.get_nowait()
            except Empty:
                break
            if not future.set_running_or_notify_cancel():
                continue
            try:
                if time.monotonic() >= deadline:
                    raise WireError("NODE_RPC_DEADLINE_EXCEEDED")
                request_deadline = min(deadline, round_deadline)
                if kind == "START_AUTHORIZE":
                    if value["command"].get("authorization_process_sha256") is not None:
                        if self._domain_dispatcher is None or not hasattr(self._domain_dispatcher, "flush_native_progress"):
                            raise WireError("NATIVE_PROGRESS_UNAVAILABLE")
                        self._domain_dispatcher.flush_native_progress(self.client, value["session_id"],
                            value["command"]["global_job_id"], deadline_monotonic=request_deadline)
                        if time.monotonic() >= request_deadline:
                            raise WireError("NODE_RPC_DEADLINE_EXCEEDED")
                    result = self.client.start_authorize(value["session_id"], value["command"], deadline_monotonic=request_deadline)
                elif kind == "WRITERS_AUTHORIZE":
                    result = self.client.writers_authorize(deadline_monotonic=request_deadline, **value)
                elif kind == "DOMAIN_RESULT":
                    result = self.client.domain_result(value, deadline_monotonic=request_deadline)
                else:
                    raise WireError("NODE_RPC_INVALID")
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)
    def step(self, *, poll_commands=True):
        if type(poll_commands) is not bool:
            raise WireError("NODE_CONTROL_INVALID")
        # Includes the entire initialize/observe/shutdown lifecycle of an adapter.
        # No second caller can turn a timeout into overlapping IPC on this node.
        with self._lock:
            self.client.heartbeat(self.session_id)
            committed = []
            commands = (self.client.poll(self.session_id, self.policy.max_poll_commands) if poll_commands
                else self.client.poll_cancel_only(self.session_id, self.policy.max_poll_commands))["commands"]
            if type(commands) is not list or len(commands) > self.policy.max_poll_commands:
                raise WireError("READ_COMMAND_INVALID")
            for command in commands:
                if type(command) is not dict:
                    raise WireError("READ_COMMAND_INVALID")
                if not poll_commands and command.get("kind") != "CANCEL":
                    raise WireError("NODE_CONTROL_INVALID")
                if command.get("kind") != "READ":
                    if command.get("kind") not in {"NATIVE", "NATIVE_RECOVERY", "CANCEL", "INVENTORY", "PROJECT", "ARTIFACT", "SOURCE", "WORKTREE"} or self._domain_dispatcher is None:
                        raise WireError("DOMAIN_COMMAND_NOT_CONFIGURED")
                    if command["kind"] in {"NATIVE", "CANCEL", "SOURCE", "WORKTREE"} and hasattr(self._domain_dispatcher, "dispatch_async"):
                        committed.append(self._domain_dispatcher.dispatch_async(command, self.rpc_proxy, self.session_id))
                    else:
                        committed.append(self._domain_dispatcher.dispatch(command, self.client, self.session_id))
                    continue
                fields(command, {"schema", "kind", "command_id", "target", "operation", "request_sha256", "deadline_ms"})
                if command["schema"] != "fleet.read-command/1" or command["kind"] != "READ" or command["operation"] not in OPERATIONS:
                    raise WireError("READ_COMMAND_INVALID")
                requested = target(command["target"])
                if requested["device_id"] != self.client.device_id or requested["route_generation"] != self.client.route_generation:
                    raise WireError("READ_COMMAND_MISMATCH")
                integer(command["deadline_ms"])
                prior = self._results.get(command["command_id"])
                if prior is not None and prior["command"] != command:
                    raise WireError("READ_COMMAND_CONFLICT")
                if prior is None:
                    if len(self._results) >= self.policy.max_retained_results:
                        raise WireError("READ_CAPACITY")
                    if int(time.time() * 1000) >= command["deadline_ms"]:
                        result = unavailable(command, "READ_DEADLINE_EXCEEDED")
                    elif self._qualified_adapter is not None:
                        # Recheck current authenticated route/session immediately
                        # before the sealed local SDK entry; no cached heartbeat
                        # invents a production read qualification.
                        admission = self.client.admit_read(self.session_id, command)
                        result = self._qualified_adapter.read(copy.deepcopy(command), admission)
                    elif self._adapter is None:
                        result = denied_local_read(self.root, command, device_id=self.client.device_id, route_generation=self.client.route_generation)
                    else:
                        result = self._adapter(copy.deepcopy(command))
                        if result.get("status") == "SUCCEEDED" and result.get("source") != "SYNTHETIC_TEST":
                            raise WireError("SYNTHETIC_ADAPTER_REQUIRED")
                    prior = {"command": copy.deepcopy(command), "result": result}
                    self._results[command["command_id"]] = prior
                committed.append(self.client.result(self.session_id, command, prior["result"]))
            self._service_rpc()
            if self._domain_dispatcher is not None and hasattr(self._domain_dispatcher, "drain"):
                committed.extend(self._domain_dispatcher.drain(self.client, self.session_id))
            return {"schema": "fleet.node-step/1", "read_commits": committed, "sdk_status": "UNQUALIFIED"}
