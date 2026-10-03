"""Optional fleet client surface. Constructing it never starts a gateway/node."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import ssl
import time
from pathlib import Path

from ..fleet.domain import DOMAIN_OWNER_PATHS, DOMAIN_PRINCIPAL_PATHS, node_reference
from ..fleet.node_keys import _check, _path, load_node_key
from ..fleet.read_broker import FleetPolicy, target
from ..fleet.transport import HttpsClient, OwnerClient
from ..fleet.wire import WireError, decode_body, encode_body, fields, integer, text

FLEET_TOOL_NAMES = (
    "fleet_server_info", "fleet_inventory", "fleet_read_state", "fleet_read_account",
    "fleet_read_status", "fleet_snapshot", "fleet_command_status", "fleet_project_create",
    "fleet_project_enroll", "fleet_project_get", "fleet_project_default_target", "fleet_project_freeze",
    "fleet_project_resume", "fleet_compare_baseline", "fleet_launch_job", "fleet_get_job", "fleet_recover_job", "fleet_cancel_job",
    "fleet_artifact_manifest", "fleet_artifact_chunk", "fleet_principal_issue", "fleet_principal_revoke",
    "fleet_principal_assign", "fleet_principal_release", "fleet_principal_reconcile", "fleet_writer_acquire", "fleet_writer_release",
    "fleet_write_source", "fleet_worktree_prepare", "fleet_worktree_commit", "fleet_worktree_retire",
)
FLEET_TOOL_CATALOG_SHA256 = hashlib.sha256(("\n".join(FLEET_TOOL_NAMES) + "\n").encode()).hexdigest()


def configuration(path, *, maximum=1048576):
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(maximum + 1)
        return decode_body(content, maximum)
    except (OSError, ValueError, TypeError):
        raise WireError("FLEET_CONFIG_INVALID") from None


def private_bytes(path, maximum):
    """Read one protected operator input from the checked retained descriptor."""
    descriptor = None
    try:
        selected = _path(path)
        descriptor = os.open(selected, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOINHERIT", 0))
        _check(descriptor)
        if os.fstat(descriptor).st_size > maximum:
            raise WireError("FLEET_CREDENTIAL_INVALID")
        chunks, count = [], 0
        while count <= maximum:
            chunk = os.read(descriptor, min(65536, maximum + 1 - count))
            if not chunk: return b"".join(chunks)
            chunks.append(chunk); count += len(chunk)
        raise WireError("FLEET_CREDENTIAL_INVALID")
    except (OSError, ValueError, UnicodeError, TypeError):
        raise WireError("FLEET_CREDENTIAL_INVALID") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def private_text(path, maximum):
    try:
        value = private_bytes(path, maximum).decode("utf-8").strip()
        text(value, maximum)
        return value
    except UnicodeError:
        raise WireError("FLEET_CREDENTIAL_INVALID") from None


def operator_configuration(path, *, maximum=1048576):
    """Startup origin, CA and operator key selection are protected authority."""
    try:
        return decode_body(private_bytes(path, maximum), maximum)
    except WireError:
        raise WireError("FLEET_OPERATOR_CONFIG_UNTRUSTED") from None


def operator_ssl_context(ca_file):
    """Pin the validated CA bytes instead of reopening their selected path."""
    if ca_file is None:
        return ssl.create_default_context()
    try:
        return ssl.create_default_context(cadata=private_bytes(ca_file, 1048576).decode("ascii"))
    except (ValueError, UnicodeError, ssl.SSLError):
        raise WireError("FLEET_CONFIG_INVALID") from None


class FleetClientFacade:
    def __init__(self, owner=None, *, http=None, principal_key=None, principal_credential=None):
        if (principal_key is None) != (principal_credential is None):
            raise WireError("FLEET_CREDENTIAL_INVALID")
        if owner is None and http is None:
            raise WireError("FLEET_CONFIG_INVALID")
        self.owner, self.http = owner, http if http is not None else owner.http
        self.principal_key, self.principal_credential = principal_key, principal_credential

    def _owner(self):
        if self.owner is None:
            raise WireError("OWNER_CREDENTIAL_REQUIRED")
        return self.owner

    @classmethod
    def from_config(cls, path):
        value = operator_configuration(path)
        fields(value, {"schema", "origin", "ca_file", "fleet_policy", "owner_token_file", "principal_key_file", "principal_credential_file"})
        if value["schema"] != "fleet.client-config/1":
            raise WireError("FLEET_CONFIG_INVALID")
        try:
            policy = FleetPolicy(**value["fleet_policy"])
            http = HttpsClient(value["origin"], policy, ssl_context=operator_ssl_context(value["ca_file"]))
            owner = None if value["owner_token_file"] is None else OwnerClient(http, private_text(value["owner_token_file"], policy.max_owner_token_bytes))
            key = None if value["principal_key_file"] is None else load_node_key(value["principal_key_file"])
            credential = None if value["principal_credential_file"] is None else configuration(
                value["principal_credential_file"], maximum=16384)
        except (TypeError, OSError, ValueError):
            raise WireError("FLEET_CONFIG_INVALID") from None
        return cls(owner, http=http, principal_key=key, principal_credential=credential)

    def server_info(self):
        return {"schema": "fleet.client-info/1", "name": "VibeMQL5 optional fleet client",
            "gateway_mode": "EXTERNAL_SINGLETON", "transport": "HTTPS_VERIFY_CA_AND_HOSTNAME",
            "tool_names": list(FLEET_TOOL_NAMES), "tool_count": len(FLEET_TOOL_NAMES),
            "tool_catalog_sha256": FLEET_TOOL_CATALOG_SHA256, "legacy_tool_count": 85,
            "authority_modes": (["OWNER"] if self.owner is not None else []) + (["PRINCIPAL"] if self.principal_key is not None else []),
            "authentication": "GATEWAY_VALIDATES_EACH_REQUEST", "caller_metadata_authentication": False, "qualification": "OPERATOR_INSTALLED_EVIDENCE_REQUIRED"}

    def inventory(self, node=None, operation_id=None):
        if node is not None:
            text(operation_id, 160)
            return self.domain("/fleet/v1/inventory", node, operation_id, {})
        return self._owner().domain_request("/fleet/v1/inventory", {"schema": "fleet.domain-query/1"})

    def read(self, operation, requested_target, operation_id):
        return self._owner().read(operation, target(requested_target), operation_id)

    def read_status(self, command_id):
        return self._owner().read_status(command_id)

    def snapshot(self, requested_targets, operation="get_account_snapshot"):
        return self._owner().snapshot(requested_targets, operation=operation)

    def command_status(self, command_id):
        return self._owner().domain_request("/fleet/v1/commands/status",
            {"schema": "fleet.domain-status-request/1", "command_id": command_id})

    def domain(self, path, node, operation_id, payload):
        if path not in DOMAIN_OWNER_PATHS | DOMAIN_PRINCIPAL_PATHS:
            raise WireError("DOMAIN_OPERATION_INVALID")
        value = {"schema": "fleet.domain-request/1", "node": node_reference(node),
                 "operation_id": operation_id, "payload": payload}
        if path in DOMAIN_PRINCIPAL_PATHS:
            if self.principal_key is None:
                raise WireError("PRINCIPAL_UNVERIFIED")
            from ..fleet.principals import sign_principal_request
            headers = sign_principal_request(self.principal_key, self.principal_credential,
                path=path, body_bytes=encode_body(value, self.http.policy.max_body_bytes),
                timestamp_ms=int(time.time() * 1000), nonce=secrets.token_hex(24), audience=self.http.origin)
            return self.http.post(path, value, headers)
        return self._owner().domain_request(path, value)

    def launch_job(self, operation_id, request):
        return self._owner().domain_request("/fleet/v1/jobs/launch",
            {"schema": "fleet.job-launch/1", "operation_id": operation_id, "request": request})

    def get_job(self, global_job_id):
        return self._owner().domain_request("/fleet/v1/jobs/status",
            {"schema": "fleet.job-query/1", "global_job_id": global_job_id})

    def recover_job(self, operation_id, global_job_id, node, session_id):
        return self._owner().domain_request("/fleet/v1/jobs/recover", {"schema": "fleet.job-recovery-request/1",
            "operation_id": operation_id, "global_job_id": global_job_id, "node": node_reference(node), "session_id": session_id})

    def principal(self, operation, payload):
        if operation not in {"issue", "revoke", "assign", "release", "reconcile"}:
            raise WireError("DOMAIN_OPERATION_INVALID")
        return self._owner().domain_request("/fleet/v1/principals/" + operation, payload)

    def admin(self, operation, request):
        return self._owner().admin(operation, request)
