"""Gateway-issued client certificates and durable writer phase authority."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
import threading
from functools import wraps
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..core.jobs import _atomic_write_json, _exclusive_file_lock
from .job_journal import canonical, digest, target
from .wire import https_origin, verified, decode_body

PATHS = frozenset({"/fleet/v1/writers/acquire", "/fleet/v1/writers/release", "/fleet/v1/sources/write",
    "/fleet/v1/worktrees/prepare", "/fleet/v1/worktrees/commit", "/fleet/v1/worktrees/retire"})
PHASES = frozenset({"source_commit", "session_commit", "worktree_create", "worktree_commit", "worktree_retire"})
PATH_PHASES = {"/fleet/v1/sources/write": {"source_commit", "session_commit"},
    "/fleet/v1/worktrees/prepare": {"worktree_create"}, "/fleet/v1/worktrees/commit": {"worktree_commit"},
    "/fleet/v1/worktrees/retire": {"worktree_retire"}}
CERT_DOMAIN = b"fleet.principal-certificate/1\n"
ASSIGN_DOMAIN = b"fleet.writer-assignment/1\n"
COMMAND_DOMAIN = b"fleet.principal-command/1\n"
DRAIN_DOMAIN = b"fleet.writer-drain-approval/1\n"
PHASE_DOMAIN = b"fleet.writer-authorization/1\n"


class PrincipalError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def integer(value, *, minimum=0, maximum=(1 << 63) - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PrincipalError("PRINCIPAL_INVALID")
    return value


def identity(value, *, maximum=128):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1," + str(maximum) + "}", value) is None:
        raise PrincipalError("PRINCIPAL_INVALID")
    return value


def sha(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise PrincipalError("PRINCIPAL_INVALID")
    return value


def clone(value):
    return json.loads(canonical(value))


def signed(key, domain, body):
    return {"body": clone(body), "signature": key.sign(domain + canonical(body)).hex()}


def verify_envelope(envelope, public_key, domain):
    try:
        if type(envelope) is not dict or set(envelope) != {"body", "signature"} or type(public_key) is not bytes or len(public_key) != 32:
            raise ValueError()
        if re.fullmatch(r"[a-f0-9]{128}", envelope["signature"]) is None:
            raise ValueError()
        Ed25519PublicKey.from_public_bytes(public_key).verify(bytes.fromhex(envelope["signature"]), domain + canonical(envelope["body"]))
        return clone(envelope["body"])
    except Exception:
        raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID") from None


@dataclass(frozen=True)
class PrincipalPolicy:
    max_principals: int
    max_assignments: int
    max_operations: int
    max_nonces: int
    max_payload_bytes: int
    clock_skew_ms: int
    phase_ttl_ms: int
    wait_ms: int

    def __post_init__(self):
        for name, maximum in {"max_principals": 4096, "max_assignments": 4096,
                "max_operations": 65536, "max_nonces": 65536, "max_payload_bytes": 4194304,
                "clock_skew_ms": 300000, "phase_ttl_ms": 30000, "wait_ms": 60000}.items():
            integer(getattr(self, name), minimum=0 if name == "clock_skew_ms" else 1, maximum=maximum)


def _client_bytes(path, body_bytes, credential, timestamp_ms, nonce, audience):
    if path not in PATHS or type(body_bytes) is not bytes:
        raise PrincipalError("PRINCIPAL_INVALID")
    integer(timestamp_ms); identity(nonce)
    return b"fleet.principal-request/1\n" + canonical({"method": "POST", "path": path,
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(), "credential_sha256": digest(credential),
        "timestamp_ms": timestamp_ms, "nonce": nonce, "audience": https_origin(audience)})


def sign_principal_request(client_key, credential, *, path, body_bytes, timestamp_ms, nonce, audience):
    if not isinstance(client_key, Ed25519PrivateKey):
        raise PrincipalError("PRINCIPAL_INVALID")
    return {"x-vibe-principal-credential": base64.b64encode(canonical(credential)).decode("ascii"),
        "x-vibe-principal-time": str(timestamp_ms), "x-vibe-principal-nonce": nonce,
        "x-vibe-principal-signature": client_key.sign(_client_bytes(path, body_bytes, credential, timestamp_ms, nonce, audience)).hex()}


def _owned(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        self._guard()
        try:
            return method(self, *args, **kwargs)
        except BaseException as error:
            if self.path.exists(): self.state = self._read()
            if isinstance(error, PrincipalError) or not isinstance(error, Exception): raise
            raise PrincipalError("PRINCIPAL_INVALID") from None
    return call


def credential_body(body):
    fields = {"schema", "audience", "principal_id", "client_public_key", "installation_id", "session_id", "epoch", "issued_ms", "expires_ms", "scopes"}
    if type(body) is not dict or set(body) != fields or body["schema"] != "fleet.principal-certificate/1": raise PrincipalError("PRINCIPAL_STATE_INVALID")
    identity(body["principal_id"]); sha(body["client_public_key"]); identity(body["installation_id"]); identity(body["session_id"])
    integer(body["epoch"], minimum=1); integer(body["issued_ms"]); integer(body["expires_ms"], minimum=body["issued_ms"] + 1)
    if https_origin(body["audience"]) != body["audience"] or type(body["scopes"]) is not list or not body["scopes"] or body["scopes"] != sorted(set(body["scopes"])) or not set(body["scopes"]) <= PATHS: raise PrincipalError("PRINCIPAL_STATE_INVALID")
    return body


def assignment_body(body, *, fence=False):
    fields = {"schema", "audience", "project_id", "target", "principal_id", "principal_epoch", "principal_session_id", "assignment_epoch", "writer_epoch", "expires_ms"}
    if fence: fields |= {"state", "fence_epoch"}
    if type(body) is not dict or set(body) != fields or body["schema"] != ("fleet.writer-fence/1" if fence else "fleet.writer-assignment/1"): raise PrincipalError("PRINCIPAL_STATE_INVALID")
    for key in ("project_id", "principal_id", "principal_session_id"): identity(body[key])
    for key in ("principal_epoch", "assignment_epoch", "writer_epoch", "expires_ms"): integer(body[key], minimum=1)
    target(body["target"])
    if https_origin(body["audience"]) != body["audience"]: raise PrincipalError("PRINCIPAL_STATE_INVALID")
    if fence and (body["state"] != "DRAINING" or integer(body["fence_epoch"], minimum=1) != body["writer_epoch"] + 1): raise PrincipalError("PRINCIPAL_STATE_INVALID")
    return body


def command_body(body):
    fields = {"schema", "audience", "path", "operation_id", "project_id", "payload_sha256", "intent_sha256", "principal_id", "principal_epoch", "principal_session_id", "assignment_epoch", "writer_epoch", "target", "issued_ms", "expires_ms"}
    if type(body) is not dict or set(body) != fields or body["schema"] != "fleet.principal-command/1" or body["path"] not in PATHS: raise PrincipalError("PRINCIPAL_STATE_INVALID")
    for key in ("operation_id", "project_id", "principal_id", "principal_session_id"): identity(body[key])
    for key in ("principal_epoch", "assignment_epoch", "writer_epoch"): integer(body[key], minimum=1)
    integer(body["issued_ms"]); integer(body["expires_ms"], minimum=body["issued_ms"] + 1)
    sha(body["payload_sha256"]); sha(body["intent_sha256"]); target(body["target"])
    binding = {key: body[key] for key in fields - {"schema", "audience", "intent_sha256", "issued_ms", "expires_ms"}}
    if digest(binding) != body["intent_sha256"] or https_origin(body["audience"]) != body["audience"]: raise PrincipalError("PRINCIPAL_STATE_INVALID")
    return body


def validate_worktree_head(head,maximum):
    if head is None:return None
    if type(head) is not dict or set(head)!={"schema","sha256","operations","worktrees"} or head["schema"]!="fleet.node-worktree-head/1": raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
    sha(head["sha256"])
    for key in ("operations","worktrees"):
        if type(head[key]) is not list or len(head[key])>maximum: raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
    seen=set()
    for op in head["operations"]:
        if type(op) is not dict or set(op)!={"intent_sha256","operation_id","phase","worktree_id","command_sha256","request_sha256","owner_sha256","receipt_sha256","git_steps"} or op["phase"] not in {"worktree_create","worktree_commit","worktree_retire"}: raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        for key in ("intent_sha256","command_sha256","request_sha256","owner_sha256","receipt_sha256"):sha(op[key])
        identity(op["operation_id"]);identity(op["worktree_id"])
        if op["intent_sha256"] in seen: raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        seen.add(op["intent_sha256"])
        purposes={"worktree_create":["create"],"worktree_commit":["stage","write_tree","commit"],"worktree_retire":["retire"]}[op["phase"]]
        if type(op["git_steps"]) is not list or len(op["git_steps"])!=len(purposes):raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        for step,purpose in zip(op["git_steps"],purposes):
            if type(step) is not dict or set(step)!={"schema","purpose","operation_id","intent_sha256","phase","arguments_sha256","status","pid","argv_sha256","returncode","head","tree"} or step["schema"]!="fleet.git-completion/1" or step["status"]!="CLOSED" or step["purpose"]!=purpose or any(step[key]!=op[key] for key in ("operation_id","intent_sha256","phase")):raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
            integer(step["pid"],minimum=1);integer(step["returncode"],maximum=0);sha(step["arguments_sha256"]);sha(step["argv_sha256"])
            for key in ("head","tree"):
                if purpose=="retire":
                    if step[key] is not None:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
                elif type(step[key]) is not str or re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})",step[key]) is None:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
    seen=set()
    for tree in head["worktrees"]:
        if type(tree) is not dict or set(tree)!={"project_id","worktree_id","base_commit","head","state","owner_sha256"} or tree["state"] not in {"ACTIVE","RETIRED"}:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        identity(tree["project_id"]);identity(tree["worktree_id"]);sha(tree["owner_sha256"])
        if tree["worktree_id"] in seen:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        seen.add(tree["worktree_id"])
        for key in ("base_commit","head"):
            if type(tree[key]) is not str or re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})",tree[key]) is None:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
    return head


def resolution_binding(original,reconciled,public_key):
    if type(original) is not dict or type(reconciled) is not dict or original.get("path")!="/fleet/v1/sources/write" or original.get("state")!="UNKNOWN" or reconciled.get("path")!="/fleet/v1/writers/reconcile" or reconciled.get("state")!="COMPLETED" or original.get("node")!=reconciled.get("node"):
        raise PrincipalError("WRITER_RESOLUTION_INVALID")
    command=command_body(verify_envelope(original["payload"]["principal_evidence"],public_key,COMMAND_DOMAIN))
    approval=verify_envelope(reconciled["payload"]["approval"],public_key,DRAIN_DOMAIN)
    approval_fields={"schema","audience","approval_id","project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target","phase","issued_ms","expires_ms"}
    if type(approval) is not dict or set(approval)!=approval_fields or approval["audience"]!=command["audience"]: raise PrincipalError("WRITER_RESOLUTION_INVALID")
    identity(approval["approval_id"]);integer(approval["issued_ms"]);integer(approval["expires_ms"],minimum=approval["issued_ms"]+1)
    keys=("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target")
    if approval.get("schema")!="fleet.writer-drain-approval/1" or approval.get("phase")!="session_commit" or any(approval.get(k)!=command[k] for k in keys): raise PrincipalError("WRITER_RESOLUTION_INVALID")
    result=reconciled["result"]
    if result.get("schema")!="fleet.writer-reconcile.receipt/1": raise PrincipalError("WRITER_RESOLUTION_INVALID")
    receipt=result["source_receipt"]
    for key in ("project_id","principal_id","writer_epoch","operation_id","intent_sha256"):
        if receipt.get(key)!=command[key]: raise PrincipalError("WRITER_RESOLUTION_INVALID")
    request=original["payload"]["request"]
    if digest({"path":command["path"],"payload":request})!=command["payload_sha256"]: raise PrincipalError("WRITER_RESOLUTION_INVALID")
    data=base64.b64decode(request["payload"]["source_base64"],validate=True)
    source_sha=hashlib.sha256(data).hexdigest()
    if receipt.get("schema")!="fleet.source-write.receipt/1" or receipt.get("source_sha256")!=source_sha or type(receipt.get("source_bytes")) is not int or receipt["source_bytes"]!=len(data) or receipt["session"]["source_sha256"]!=source_sha or type(receipt["session"]["source_bytes"]) is not int or receipt["session"]["source_bytes"]!=len(data): raise PrincipalError("WRITER_RESOLUTION_INVALID")
    acks=result["writer_acks"]
    if type(acks) is not list or len(acks)!=2 or {a.get("phase") for a in acks}!={"source_commit","session_commit"}: raise PrincipalError("WRITER_RESOLUTION_INVALID")
    for ack in acks:
        if ack.get("outcome")!="COMMITTED" or ack.get("operation_id")!=command["operation_id"] or ack.get("intent_sha256")!=command["intent_sha256"]: raise PrincipalError("WRITER_RESOLUTION_INVALID")
        effect={"schema":"fleet.source-effect/1","source_sha256":source_sha,"source_bytes":len(data)} if ack["phase"]=="source_commit" else {"schema":"fleet.session-effect/1","revision_id":receipt["session"]["revision_id"],"revision_sha256":receipt["session"]["revision_sha256"]}
        if ack.get("receipt_sha256")!=digest(effect): raise PrincipalError("WRITER_RESOLUTION_INVALID")
    return {"schema":"fleet.writer-resolution/1","original_command_id":original["command_id"],"reconciliation_command_id":reconciled["command_id"],"intent_sha256":command["intent_sha256"],"approval_sha256":digest(reconciled["payload"]["approval"]),"source_receipt_sha256":digest(receipt)}


class GatewayPrincipalAuthority:
    """Finite authority, one lifetime OS owner; no private client key or bearer."""
    def __init__(self, path, *, signing_key, audience, policy, initialize=False, fault=None):
        if not isinstance(signing_key, Ed25519PrivateKey) or type(policy) is not PrincipalPolicy or type(initialize) is not bool:
            raise PrincipalError("PRINCIPAL_INVALID")
        policy.__post_init__()
        self.path, self.key, self.audience = Path(path).resolve(), signing_key, https_origin(audience)
        self.policy, self.fault = policy, fault
        self._thread = threading.get_ident()
        self.public_key = signing_key.public_key().public_bytes_raw()
        self._lock = _exclusive_file_lock(self.path.with_suffix(self.path.suffix + ".owner.lock"), timeout_seconds=policy.wait_ms / 1000)
        self._lock.__enter__()
        try:
            if initialize:
                if self.path.exists(): raise PrincipalError("PRINCIPAL_EXISTS")
                self.state = {"schema": "fleet.principal-authority/1", "policy": asdict(policy), "audience": self.audience,
                    "public_key": self.public_key.hex(), "revision": 1, "last_wall_ms": 0,
                    "principals": {}, "assignments": {}, "operations": {}, "nonces": {}, "phases": {}, "commands": {}, "reconciliations": {}, "recovery": None}
                self._publish("initialize")
            else:
                self.state = self._read()
                self._validate()
        except (PrincipalError, KeyboardInterrupt, SystemExit):
            self.close()
            raise
        except Exception:
            self.close()
            raise PrincipalError("PRINCIPAL_STATE_INVALID") from None

    def _guard(self):
        if threading.get_ident() != self._thread: raise PrincipalError("PRINCIPAL_WRONG_THREAD")
        if self._lock is None: raise PrincipalError("PRINCIPAL_CLOSED")

    def close(self):
        if threading.get_ident() != self._thread: raise PrincipalError("PRINCIPAL_WRONG_THREAD")
        if self._lock is not None:
            self._lock.__exit__(None, None, None); self._lock = None

    def _read(self):
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(self.policy.max_payload_bytes + 1)
            value = decode_body(raw, self.policy.max_payload_bytes)
            fingerprint = value.pop("record_sha256")
            if fingerprint != digest(value): raise ValueError()
            return value
        except Exception:
            raise PrincipalError("PRINCIPAL_STATE_INVALID") from None

    def _validate(self):
        value = self.state
        if set(value) != {"schema", "policy", "audience", "public_key", "revision", "last_wall_ms", "principals", "assignments", "operations", "nonces", "phases", "commands", "reconciliations", "recovery"} or value["schema"] != "fleet.principal-authority/1" or value["policy"] != asdict(self.policy) or value["audience"] != self.audience or value["public_key"] != self.public_key.hex():
            raise PrincipalError("PRINCIPAL_STATE_INVALID")
        integer(value["revision"], minimum=1); integer(value["last_wall_ms"])
        for field, maximum in (("principals", self.policy.max_principals), ("assignments", self.policy.max_assignments),
                               ("operations", self.policy.max_operations), ("nonces", self.policy.max_nonces), ("phases", self.policy.max_operations), ("commands", self.policy.max_operations), ("reconciliations", self.policy.max_operations)):
            if type(value[field]) is not dict or len(value[field]) > maximum: raise PrincipalError("PRINCIPAL_STATE_INVALID")
        for op, record in value["operations"].items():
            identity(op)
            if type(record) is not dict or set(record) != {"request_sha256", "receipt"}: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            sha(record["request_sha256"])
            receipt = record["receipt"]
            shapes = {"fleet.principal.issued/1": {"schema","principal_id","state","credential"}, "fleet.assignment.issued/1": {"schema","project_id","assignment"}, "fleet.writer.drain/1": {"schema","state","fences"}, "fleet.writer-reconcile/1": {"schema","approval"}}
            if type(receipt) is not dict or set(receipt) != shapes.get(receipt.get("schema"), set()): raise PrincipalError("PRINCIPAL_STATE_INVALID")
            if receipt["schema"]=="fleet.principal.issued/1":
                body=credential_body(verify_envelope(receipt["credential"],self.public_key,CERT_DOMAIN))
                if receipt["principal_id"]!=body["principal_id"] or receipt["state"]!="ACTIVE": raise PrincipalError("PRINCIPAL_STATE_INVALID")
            if receipt["schema"]=="fleet.assignment.issued/1":
                body=assignment_body(verify_envelope(receipt["assignment"],self.public_key,ASSIGN_DOMAIN))
                if receipt["project_id"]!=body["project_id"]: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            if receipt["schema"]=="fleet.writer.drain/1":
                if receipt["state"]!="DRAINING" or type(receipt["fences"]) is not list or len(receipt["fences"])>self.policy.max_assignments: raise PrincipalError("PRINCIPAL_STATE_INVALID")
                for fence in receipt["fences"]: assignment_body(verify_envelope(fence,self.public_key,ASSIGN_DOMAIN),fence=True)
            if receipt["schema"]=="fleet.writer-reconcile/1": self._drain_body(receipt["approval"])
            if type(record["receipt"]) is not dict or type(record["receipt"].get("schema")) is not str: raise PrincipalError("PRINCIPAL_STATE_INVALID")
        for key, record in value["nonces"].items():
            sha(key)
            if type(record) is not dict or set(record) != {"request_sha256", "timestamp_ms"}: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            sha(record["request_sha256"]); integer(record["timestamp_ms"])
        for pid, record in value["principals"].items():
            if type(record) is not dict or set(record) != {"state", "credential"}: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            body = credential_body(verify_envelope(record["credential"], self.public_key, CERT_DOMAIN))
            if pid != body["principal_id"] or record["state"] not in {"ACTIVE", "DRAINING", "REVOKED"} or body["schema"] != "fleet.principal-certificate/1":
                raise PrincipalError("PRINCIPAL_STATE_INVALID")
        for project, record in value["assignments"].items():
            if type(record) is not dict or set(record) != {"state", "assignment", "fence_acked"} or type(record["fence_acked"]) is not bool or (record["state"] == "RELEASED") != record["fence_acked"]: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            body = assignment_body(verify_envelope(record["assignment"], self.public_key, ASSIGN_DOMAIN))
            if project != body["project_id"] or body["principal_id"] not in value["principals"] or record["state"] not in {"ACTIVE", "DRAINING", "RELEASED"}:
                raise PrincipalError("PRINCIPAL_STATE_INVALID")
        for key, record in value["phases"].items():
            if type(record) is not dict or set(record) != {"request_sha256", "grant", "state", "receipt_sha256"}: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            sha(record["request_sha256"])
            body = verify_envelope(record["grant"], self.public_key, PHASE_DOMAIN)
            fields = {"schema", "audience", "session_id", "operation_id", "project_id", "target", "principal_id", "principal_epoch", "assignment_epoch", "writer_epoch", "phase", "intent_sha256", "challenge", "authorization_id", "issued_ms", "expires_ms"}
            if type(body) is not dict or not fields <= set(body) or set(body)-fields-{ "phase_acks", "drain_approval" } or body["schema"] != "fleet.writer-authorization/1" or body["audience"] != self.audience: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            for field in ("session_id", "operation_id", "project_id", "principal_id", "challenge", "authorization_id"): identity(body[field])
            for field in ("principal_epoch", "assignment_epoch", "writer_epoch"): integer(body[field], minimum=1)
            integer(body["issued_ms"]); integer(body["expires_ms"], minimum=body["issued_ms"] + 1); sha(body["intent_sha256"]); target(body["target"])
            command_key = self._command_key(body["principal_id"], body["operation_id"])
            command = value["commands"].get(command_key)
            if command is None or key != digest({"command_key": command_key, "phase": body["phase"]}) or any(body[k] != command["command"]["body"][k] for k in ("principal_id", "principal_epoch", "assignment_epoch", "writer_epoch", "intent_sha256", "target", "project_id")): raise PrincipalError("PRINCIPAL_STATE_INVALID")
            if (record["state"] == "ISSUED") != (record["receipt_sha256"] is None): raise PrincipalError("PRINCIPAL_STATE_INVALID")
            if record["receipt_sha256"] is not None: sha(record["receipt_sha256"])
            if body["phase"] not in PHASES or record["state"] not in {"ISSUED", "COMMITTED", "NOT_ATTEMPTED", "UNKNOWN"}:
                raise PrincipalError("PRINCIPAL_STATE_INVALID")

        for key, record in value["commands"].items():
            if type(record) is not dict or set(record) != {"binding_sha256", "command"}: raise PrincipalError("PRINCIPAL_STATE_INVALID")
            sha(record["binding_sha256"])
            body = command_body(verify_envelope(record["command"], self.public_key, COMMAND_DOMAIN))
            if record["binding_sha256"] != body["intent_sha256"] or key != self._command_key(body["principal_id"], body["operation_id"]) or body["principal_id"] not in value["principals"] or body["path"] not in PATHS:
                raise PrincipalError("PRINCIPAL_STATE_INVALID")

        for intent,envelope in value["reconciliations"].items():
            sha(intent)
            if self._drain_body(envelope)["intent_sha256"]!=intent: raise PrincipalError("PRINCIPAL_STATE_INVALID")
        recovery=value["recovery"]
        if recovery is not None and (type(recovery) is not dict or set(recovery)!={"coordination_sha256","head","phase"} or recovery["phase"] not in {"FENCED","FINALIZED"}): raise PrincipalError("PRINCIPAL_STATE_INVALID")
        if recovery is not None:
            sha(recovery["coordination_sha256"]);self._head(recovery["head"])

    def _drain_body(self,envelope):
        body=verify_envelope(envelope,self.public_key,DRAIN_DOMAIN)
        fields={"schema","audience","approval_id","project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target","phase","issued_ms","expires_ms"}
        if type(body) is not dict or set(body)!=fields or body["schema"]!="fleet.writer-drain-approval/1" or body["audience"]!=self.audience or body["phase"]!="session_commit": raise PrincipalError("PRINCIPAL_STATE_INVALID")
        for key in ("approval_id","project_id","principal_id","operation_id"): identity(body[key])
        for key in ("principal_epoch","assignment_epoch","writer_epoch"): integer(body[key],minimum=1)
        sha(body["intent_sha256"]);target(body["target"]);integer(body["issued_ms"]);integer(body["expires_ms"],minimum=body["issued_ms"]+1)
        command=self.state["commands"].get(self._command_key(body["principal_id"],body["operation_id"]))
        if command is None or command["command"]["body"]["path"]!="/fleet/v1/sources/write" or any(body[k]!=command["command"]["body"][k] for k in ("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target")): raise PrincipalError("PRINCIPAL_STATE_INVALID")
        return body

    def _publish(self, action):
        committed = False
        try:
            self._validate()
            if len(canonical(self.state)) > self.policy.max_payload_bytes: raise PrincipalError("PRINCIPAL_CAPACITY")
            if self.fault: self.fault(action + ":before_commit")
            _atomic_write_json(self.path, {**self.state, "record_sha256": digest(self.state)})
            committed = True
            if self.fault: self.fault(action + ":after_commit")
        except BaseException as error:
            if self.path.exists(): self.state = self._read()
            if isinstance(error, PrincipalError): raise
            if isinstance(error, Exception):
                raise PrincipalError("PRINCIPAL_COMMIT_UNCERTAIN" if committed else "PRINCIPAL_TRANSACTION_FAILED") from None
            raise

    def _wall(self, now_ms):
        integer(now_ms)
        if now_ms < self.state["last_wall_ms"]: raise PrincipalError("PRINCIPAL_CLOCK_ROLLBACK")
        if now_ms != self.state["last_wall_ms"]:
            self.state["last_wall_ms"] = now_ms
            self._publish("observe_wall")

    @staticmethod
    def _command_key(principal_id, operation_id):
        return digest({"principal_id": principal_id, "operation_id": operation_id})

    def _capacity(self, field, maximum):
        if len(self.state[field]) >= maximum: raise PrincipalError("PRINCIPAL_CAPACITY")

    def _principal(self, pid, *, now_ms, admission=True):
        record = self.state["principals"].get(pid)
        if record is None: raise PrincipalError("PRINCIPAL_UNAVAILABLE")
        body = credential_body(verify_envelope(record["credential"], self.public_key, CERT_DOMAIN))
        if record["state"] != "ACTIVE" and admission: raise PrincipalError("PRINCIPAL_DRAINING")
        if not body["issued_ms"] <= now_ms < body["expires_ms"]: raise PrincipalError("PRINCIPAL_EXPIRED")
        return record, body

    @_owned
    def owner_request(self, path, value, *, now_ms):
        self._ready(); integer(now_ms)
        if type(value) is not dict or len(canonical(value))>self.policy.max_payload_bytes: raise PrincipalError("PRINCIPAL_INVALID")
        operation_id = identity(value.get("operation_id"))
        request_sha = digest({"path": path, "value": value})
        old = self.state["operations"].get(operation_id)
        if old:
            if old["request_sha256"] != request_sha: raise PrincipalError("PRINCIPAL_OPERATION_CONFLICT")
            return {**clone(old["receipt"]), "idempotent_recovered": True}
        self._wall(now_ms); self._capacity("operations", self.policy.max_operations)
        if path == "/fleet/v1/principals/issue":
            if set(value) != {"operation_id", "client_public_key", "installation_id", "session_id", "expires_ms", "scopes"}: raise PrincipalError("PRINCIPAL_INVALID")
            sha(value["client_public_key"]); identity(value["installation_id"]); identity(value["session_id"])
            integer(value["expires_ms"], minimum=now_ms + 1)
            if type(value["scopes"]) is not list or not value["scopes"] or len(set(value["scopes"])) != len(value["scopes"]) or not set(value["scopes"]) <= PATHS: raise PrincipalError("PRINCIPAL_INVALID")
            self._capacity("principals", self.policy.max_principals)
            pid = "principal_" + uuid.uuid4().hex
            body = {"schema": "fleet.principal-certificate/1", "audience": self.audience, "principal_id": pid,
                "client_public_key": value["client_public_key"], "installation_id": value["installation_id"],
                "session_id": value["session_id"], "epoch": 1, "issued_ms": now_ms,
                "expires_ms": value["expires_ms"], "scopes": sorted(value["scopes"])}
            credential = signed(self.key, CERT_DOMAIN, body)
            self.state["principals"][pid] = {"state": "ACTIVE", "credential": credential}
            receipt = {"schema": "fleet.principal.issued/1", "principal_id": pid, "state": "ACTIVE", "credential": credential}
        elif path == "/fleet/v1/principals/assign":
            if set(value) != {"operation_id", "principal_id", "project_id", "target", "writer_epoch"}: raise PrincipalError("PRINCIPAL_INVALID")
            project = identity(value["project_id"]); integer(value["writer_epoch"], minimum=1)
            _, principal = self._principal(value["principal_id"], now_ms=now_ms)
            selected = target(value["target"])
            prior = self.state["assignments"].get(project)
            if prior and prior["state"] != "RELEASED": raise PrincipalError("WRITER_ALREADY_ASSIGNED")
            if prior and value["writer_epoch"] <= prior["assignment"]["body"]["writer_epoch"]: raise PrincipalError("WRITER_FENCE_MISMATCH")
            if prior is None: self._capacity("assignments", self.policy.max_assignments)
            previous_epoch = 0 if prior is None else prior["assignment"]["body"]["assignment_epoch"]
            body = {"schema": "fleet.writer-assignment/1", "audience": self.audience, "project_id": project,
                "target": selected, "principal_id": principal["principal_id"], "principal_epoch": principal["epoch"],
                "principal_session_id": principal["session_id"], "assignment_epoch": previous_epoch + 1,
                "writer_epoch": value["writer_epoch"], "expires_ms": principal["expires_ms"]}
            assignment = signed(self.key, ASSIGN_DOMAIN, body)
            self.state["assignments"][project] = {"state": "ACTIVE", "assignment": assignment, "fence_acked": False}
            receipt = {"schema": "fleet.assignment.issued/1", "project_id": project, "assignment": assignment}
        elif path=="/fleet/v1/principals/reconcile":
            fields={"operation_id","original_operation_id","principal_id","project_id","intent_sha256","expires_ms"}
            if set(value)!=fields: raise PrincipalError("PRINCIPAL_INVALID")
            original=self.state["commands"].get(self._command_key(identity(value["principal_id"]),identity(value["original_operation_id"])))
            if original is None or original["command"]["body"]["path"]!="/fleet/v1/sources/write": raise PrincipalError("WRITER_COMMAND_UNAVAILABLE")
            body=original["command"]["body"]
            if value["project_id"]!=body["project_id"] or sha(value["intent_sha256"])!=body["intent_sha256"]: raise PrincipalError("WRITER_FENCE_MISMATCH")
            integer(value["expires_ms"],minimum=now_ms+1,maximum=now_ms+self.policy.phase_ttl_ms)
            approval=signed(self.key,DRAIN_DOMAIN,{"schema":"fleet.writer-drain-approval/1","audience":self.audience,
                "approval_id":"drain_"+uuid.uuid4().hex,**{key:body[key] for key in ("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target")},
                "phase":"session_commit","issued_ms":now_ms,"expires_ms":value["expires_ms"]})
            self.state["reconciliations"][body["intent_sha256"]]=approval
            receipt={"schema":"fleet.writer-reconcile/1","approval":approval}
        elif path in {"/fleet/v1/principals/revoke", "/fleet/v1/principals/release"}:
            expected = {"operation_id", "principal_id"} if path.endswith("revoke") else {"operation_id", "project_id"}
            if set(value) != expected: raise PrincipalError("PRINCIPAL_INVALID")
            if path.endswith("revoke"):
                pid = identity(value["principal_id"])
                record = self.state["principals"].get(pid)
                if record is None: raise PrincipalError("PRINCIPAL_UNAVAILABLE")
                record["state"] = "DRAINING"
                selected = [row for row in self.state["assignments"].values() if row["assignment"]["body"]["principal_id"] == pid and row["state"] != "RELEASED"]
            else:
                project = identity(value["project_id"])
                record = self.state["assignments"].get(project)
                if record is None: raise PrincipalError("WRITER_UNASSIGNED")
                selected = [record]
            fences = []
            for record in selected:
                record["state"] = "DRAINING"; record["fence_acked"] = False
                body = {**record["assignment"]["body"], "schema": "fleet.writer-fence/1", "state": "DRAINING",
                        "fence_epoch": record["assignment"]["body"]["writer_epoch"] + 1}
                fences.append(signed(self.key, ASSIGN_DOMAIN, body))
            receipt = {"schema": "fleet.writer.drain/1", "state": "DRAINING", "fences": fences}
        else: raise PrincipalError("PRINCIPAL_OPERATION_UNAVAILABLE")
        self.state["revision"] += 1
        self.state["operations"][operation_id] = {"request_sha256": request_sha, "receipt": clone(receipt)}
        self._publish("owner_request")
        return {**clone(receipt), "idempotent_recovered": False}

    @_owned
    def admit_request(self, path, header_pairs, value, *, body_bytes, now_ms):
        self._ready()
        if path not in PATHS or type(value) is not dict or type(body_bytes) is not bytes:
            raise PrincipalError("PRINCIPAL_INVALID")
        try:
            if decode_body(body_bytes, self.policy.max_payload_bytes) != value: raise ValueError()
        except Exception:
            raise PrincipalError("PRINCIPAL_INVALID") from None
        names = {"x-vibe-principal-credential", "x-vibe-principal-time", "x-vibe-principal-nonce", "x-vibe-principal-signature"}
        headers = {}
        for key, item in header_pairs:
            key = key.lower()
            if key.startswith("x-vibe-principal-"):
                if key not in names or key in headers: raise PrincipalError("PRINCIPAL_INVALID")
                headers[key] = item
        try:
            if set(headers) != names or len(headers["x-vibe-principal-credential"]) > 16384: raise ValueError()
            credential = decode_body(base64.b64decode(headers["x-vibe-principal-credential"], validate=True),16384)
            cert = verify_envelope(credential, self.public_key, CERT_DOMAIN)
            timestamp = int(headers["x-vibe-principal-time"])
            if str(timestamp) != headers["x-vibe-principal-time"]: raise ValueError()
            nonce = identity(headers["x-vibe-principal-nonce"])
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(cert["client_public_key"])).verify(
                bytes.fromhex(headers["x-vibe-principal-signature"]), _client_bytes(path, body_bytes, credential, timestamp, nonce, self.audience))
        except Exception:
            raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID") from None
        self._wall(now_ms)
        current, stored_cert = self._principal(cert["principal_id"], now_ms=now_ms)
        if cert != stored_cert or path not in cert["scopes"] or cert["audience"] != self.audience or abs(timestamp - now_ms) > self.policy.clock_skew_ms:
            raise PrincipalError("PRINCIPAL_SCOPE_MISMATCH")
        if set(value) != {"schema", "node", "operation_id", "payload"} or value["schema"] != "fleet.domain-request/1" or type(value["payload"]) is not dict:
            raise PrincipalError("PRINCIPAL_INVALID")
        project = identity(value["payload"].get("project_id")); operation_id = identity(value.get("operation_id"))
        assignment = self.state["assignments"].get(project)
        old_command=self.state["commands"].get(self._command_key(cert["principal_id"],operation_id))
        release_retry=(path=="/fleet/v1/writers/release" and old_command is not None and old_command["command"]["body"]["path"]==path and old_command["command"]["body"]["payload_sha256"]==digest({"path":path,"payload":value}))
        if assignment is None or (assignment["state"] != "ACTIVE" and not release_retry): raise PrincipalError("WRITER_UNASSIGNED")
        fence = verify_envelope(assignment["assignment"], self.public_key, ASSIGN_DOMAIN)
        if value["node"] != {key: fence["target"][key] for key in ("device_id", "route_generation")}:
            raise PrincipalError("WRITER_FENCE_MISMATCH")
        if fence["principal_id"] != cert["principal_id"] or fence["principal_epoch"] != cert["epoch"] or fence["principal_session_id"] != cert["session_id"]:
            raise PrincipalError("WRITER_FENCE_MISMATCH")
        nonce_sha = digest({"principal_id": cert["principal_id"], "epoch": cert["epoch"], "nonce": nonce})
        if nonce_sha in self.state["nonces"]: raise PrincipalError("PRINCIPAL_REPLAY")
        self._capacity("nonces", self.policy.max_nonces)
        payload_sha = digest({"path": path, "payload": value})
        binding = {"path": path, "operation_id": operation_id, "project_id": project, "payload_sha256": payload_sha,
            "principal_id": cert["principal_id"], "principal_epoch": cert["epoch"], "principal_session_id": cert["session_id"],
            "assignment_epoch": fence["assignment_epoch"], "writer_epoch": fence["writer_epoch"], "target": fence["target"]}
        command_key = self._command_key(cert["principal_id"], operation_id)
        old_command = self.state["commands"].get(command_key)
        if old_command:
            if old_command["binding_sha256"] != digest(binding): raise PrincipalError("PRINCIPAL_OPERATION_CONFLICT")
            proof = clone(old_command["command"])
        else:
            self._capacity("commands", self.policy.max_operations)
            proof = signed(self.key, COMMAND_DOMAIN, {"schema": "fleet.principal-command/1", "audience": self.audience,
                **binding, "intent_sha256": digest(binding), "issued_ms": now_ms, "expires_ms": cert["expires_ms"]})
            self.state["commands"][command_key] = {"binding_sha256": digest(binding), "command": proof}
        if path=="/fleet/v1/writers/release" and not release_retry:
            if set(value["payload"])!={"project_id"}: raise PrincipalError("PRINCIPAL_INVALID")
            assignment["state"]="DRAINING"; assignment["fence_acked"]=False
        self.state["nonces"][nonce_sha] = {"request_sha256": hashlib.sha256(body_bytes).hexdigest(), "timestamp_ms": timestamp}
        self.state["revision"] += 1
        self._publish("admit_request")
        return {"node": {key: fence["target"][key] for key in ("device_id", "route_generation")},
            "principal_id": cert["principal_id"], "payload": {"request": clone(value), "principal_evidence": proof,
                "assignment": clone(assignment["assignment"])}}

    @_owned
    def authorize_node(self, proof, value, *, now_ms):
        self._ready()
        if not verified(proof) or proof.path != "/fleet/v1/writers/authorize": raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID")
        fields = {"schema", "session_id", "operation_id", "project_id", "target", "principal_id", "principal_epoch",
                  "assignment_epoch", "writer_epoch", "phase", "intent_sha256", "challenge"}
        if type(value) is not dict or not fields<=set(value) or set(value)-fields-{"phase_acks","drain_approval"} or value["schema"] != "fleet.writer-authorization-request/1" or value["phase"] not in PHASES:
            raise PrincipalError("PRINCIPAL_INVALID")
        if proof.body != value: raise PrincipalError("PRINCIPAL_INVALID")
        for name in ("principal_epoch", "assignment_epoch", "writer_epoch"): integer(value[name], minimum=1)
        target(value["target"])
        self._wall(now_ms)
        if "phase_acks" in value: self.acknowledge_node(proof,value["phase_acks"])
        reconciliation=None
        if "drain_approval" in value:
            reconciliation=self._drain_body(value["drain_approval"])
            if self.state["reconciliations"].get(value["intent_sha256"])!=value["drain_approval"] or not reconciliation["issued_ms"]<=now_ms<reconciliation["expires_ms"] or any(value[k]!=reconciliation[k] for k in ("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target","phase")):
                raise PrincipalError("WRITER_FENCE_MISMATCH")
            principal=self.state["principals"][value["principal_id"]]["credential"]["body"]
        else:
            _, principal = self._principal(value["principal_id"], now_ms=now_ms)
        assignment = self.state["assignments"].get(value["project_id"])
        if assignment is None or (assignment["state"] != "ACTIVE" and not (reconciliation and assignment["state"]=="DRAINING")): raise PrincipalError("WRITER_UNASSIGNED")
        fence = assignment["assignment"]["body"]
        if any(value[key] != fence[key] for key in ("project_id", "target", "principal_id", "principal_epoch", "assignment_epoch", "writer_epoch")) or value["target"]["device_id"] != proof.device_id or value["target"]["route_generation"] != proof.route_generation:
            raise PrincipalError("WRITER_FENCE_MISMATCH")
        identity(value["session_id"]); identity(value["operation_id"]); identity(value["challenge"]); sha(value["intent_sha256"])
        command_key = self._command_key(value["principal_id"], value["operation_id"])
        command = self.state["commands"].get(command_key)
        if command is None: raise PrincipalError("WRITER_COMMAND_UNAVAILABLE")
        command_body = command["command"]["body"]
        if value["phase"] not in PATH_PHASES.get(command_body["path"], set()) or any(value[k] != command_body[k] for k in ("project_id", "target", "principal_id", "principal_epoch", "assignment_epoch", "writer_epoch", "intent_sha256")):
            raise PrincipalError("WRITER_PHASE_CONFLICT")
        key = digest({"command_key": command_key, "phase": value["phase"]})
        request_sha = digest(value)
        old = self.state["phases"].get(key)
        if old:
            if old["request_sha256"] != request_sha: raise PrincipalError("WRITER_PHASE_CONFLICT")
            if old["state"] != "ISSUED" or now_ms >= old["grant"]["body"]["expires_ms"]:
                raise PrincipalError("WRITER_PHASE_UNRESOLVED")
            return clone(old["grant"])
        self._capacity("phases", self.policy.max_operations)
        body = {**clone(value), "schema": "fleet.writer-authorization/1", "audience": self.audience,
                "authorization_id": "writeauth_" + uuid.uuid4().hex, "issued_ms": now_ms,
                "expires_ms": min(principal["expires_ms"] if reconciliation is None else reconciliation["expires_ms"], now_ms + self.policy.phase_ttl_ms)}
        grant = signed(self.key, PHASE_DOMAIN, body)
        self.state["phases"][key] = {"request_sha256": request_sha, "grant": grant, "state": "ISSUED", "receipt_sha256": None}
        self.state["revision"] += 1
        self._publish("authorize_phase")
        return clone(grant)

    @_owned
    def acknowledge_node(self, proof, acks):
        if not verified(proof) or proof.path not in {"/fleet/v1/results","/fleet/v1/writers/authorize"} or type(acks) is not list or len(acks) > 5: raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID")
        source=proof.body.get("phase_acks") if proof.path=="/fleet/v1/writers/authorize" else proof.body.get("result",{}).get("writer_acks")
        if source!=acks: raise PrincipalError("PRINCIPAL_INVALID")
        for ack in acks:
            if type(ack) is not dict or set(ack) != {"authorization_id", "operation_id", "phase", "intent_sha256", "outcome", "receipt_sha256"} or ack["outcome"] not in {"COMMITTED", "NOT_ATTEMPTED", "UNKNOWN"}:
                raise PrincipalError("PRINCIPAL_INVALID")
            rows = [row for row in self.state["phases"].values() if row["grant"]["body"]["authorization_id"] == ack["authorization_id"]]
            record = None if len(rows) != 1 else rows[0]
            if record is None: raise PrincipalError("WRITER_PHASE_UNRESOLVED")
            body = record["grant"]["body"]
            if body["target"]["device_id"] != proof.device_id or body["target"]["route_generation"] != proof.route_generation or any(body[k] != ack[k] for k in ("authorization_id", "operation_id", "phase", "intent_sha256")):
                raise PrincipalError("WRITER_FENCE_MISMATCH")
            sha(ack["receipt_sha256"])
            if record["state"] != "ISSUED" and (record["state"] != ack["outcome"] or record["receipt_sha256"] != ack["receipt_sha256"]):
                raise PrincipalError("WRITER_PHASE_CONFLICT")
            record.update(state=ack["outcome"], receipt_sha256=ack["receipt_sha256"])
        self.state["revision"] += 1
        self._publish("acknowledge_phase")
        return {"schema": "fleet.writer-ack.receipt/1", "accepted": len(acks)}

    @_owned
    def acknowledge_fence(self, proof, *, project_id, fence_epoch, pending_intents):
        if not verified(proof) or proof.path!="/fleet/v1/results" or type(pending_intents) is not list: raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID")
        if len(pending_intents)>self.policy.max_operations: raise PrincipalError("PRINCIPAL_INVALID")
        for intent in pending_intents: sha(intent)
        if len(set(pending_intents))!=len(pending_intents): raise PrincipalError("PRINCIPAL_INVALID")
        record = self.state["assignments"].get(project_id)
        if record is None or record["state"] not in {"DRAINING","RELEASED"} or record["assignment"]["body"]["target"]["device_id"] != proof.device_id or record["assignment"]["body"]["target"]["route_generation"]!=proof.route_generation or fence_epoch != record["assignment"]["body"]["writer_epoch"] + 1:
            raise PrincipalError("WRITER_FENCE_MISMATCH")
        result=proof.body.get("result",{})
        actual=result.get("fence_ack") if result.get("schema")=="fleet.writer-reconcile.receipt/1" else result
        if type(actual) is not dict or any(actual.get(k)!=v for k,v in {"project_id":project_id,"fence_epoch":fence_epoch,"pending_intents":pending_intents}.items()): raise PrincipalError("PRINCIPAL_INVALID")
        if pending_intents or any(row["grant"]["body"]["project_id"] == project_id and row["state"] in {"ISSUED", "UNKNOWN"} for row in self.state["phases"].values()):
            if record["state"]!="DRAINING": raise PrincipalError("WRITER_FENCE_MISMATCH")
            return {"schema":"fleet.writer.release/1","project_id":project_id,"state":"DRAINING"}
        if record["state"]=="RELEASED":
            return {"schema":"fleet.writer.release/1","project_id":project_id,"state":"RELEASED"}
        record.update(state="RELEASED", fence_acked=True)
        pid = record["assignment"]["body"]["principal_id"]
        principal = self.state["principals"][pid]
        if principal["state"] == "DRAINING" and not any(row["assignment"]["body"]["principal_id"] == pid and row["state"] != "RELEASED" for row in self.state["assignments"].values()):
            principal["state"] = "REVOKED"
        self.state["revision"] += 1
        self._publish("fence_ack")
        return {"schema": "fleet.writer.release/1", "project_id": project_id, "state": "RELEASED"}

    def _ready(self):
        if self.state["recovery"] is not None and self.state["recovery"]["phase"] != "FINALIZED": raise PrincipalError("PRINCIPAL_RECONCILIATION_REQUIRED")

    @staticmethod
    def _head(head):
        if type(head) is not dict or set(head)!={"schema","revision","sha256"} or head["schema"]!="fleet.principal-head/1": raise PrincipalError("PRINCIPAL_STATE_INVALID")
        integer(head["revision"],minimum=1);sha(head["sha256"])

    @_owned
    def control_head(self):
        self._validate()
        body = {key: value for key, value in self.state.items() if key != "recovery"}
        return {"schema": "fleet.principal-head/1", "revision": self.state["revision"], "sha256": digest(body)}

    @_owned
    def assert_quiescent_head(self, head):
        self._head(head)
        if self.control_head() != head or any(row["state"] in {"ISSUED", "UNKNOWN"} for row in self.state["phases"].values()) or any(row["state"] == "DRAINING" for row in self.state["assignments"].values()):
            raise PrincipalError("PRINCIPAL_RECONCILIATION_REQUIRED")
        return clone(head)

    @_owned
    def prepare_restore(self, coordination_sha256, *, expected_head):
        sha(coordination_sha256); self.assert_quiescent_head(expected_head)
        scope={"coordination_sha256":coordination_sha256,"head":clone(expected_head),"phase":"FENCED"}
        old=self.state["recovery"]
        if old is not None and old!=scope: raise PrincipalError("PRINCIPAL_RESTORE_CONFLICT")
        self.state["recovery"]=scope; self._publish("prepare_restore")
        return clone(scope)

    @_owned
    def verify_recovery_witness(self, proof, *, coordination_sha256):
        if not verified(proof) or proof.path!="/fleet/v1/reconcile": raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID")
        recovery=self.state["recovery"]
        if recovery is None or recovery["coordination_sha256"]!=coordination_sha256: raise PrincipalError("PRINCIPAL_RESTORE_CONFLICT")
        self.assert_quiescent_head(recovery["head"])
        value=proof.body.get("principal_witness")
        fields={"schema","authority","coordination_sha256","device_id","route_generation","session_id","pending_intents","assignments","phase_receipts","worktree_head"}
        if type(value) is not dict or set(value)!=fields or value["schema"]!="fleet.node-writer-witness/1" or value["authority"] not in {"PERSISTED","EMPTY_ABSENCE"} or value["coordination_sha256"]!=coordination_sha256 or value["device_id"]!=proof.device_id or value["route_generation"]!=proof.route_generation or value["session_id"]!=proof.body.get("session_id") or value["pending_intents"]!=[]: raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        if value["authority"]=="EMPTY_ABSENCE":
            histories=((self.state["assignments"].values(),"assignment"),(self.state["phases"].values(),"grant"),(self.state["commands"].values(),"command"))
            if value["assignments"]!=[] or value["phase_receipts"]!=[] or value["worktree_head"] is not None or any(row[field]["body"]["target"]["device_id"]==proof.device_id for rows,field in histories for row in rows): raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
            for operation in self.state["operations"].values():
                receipt=operation["receipt"]
                envelopes=([receipt["assignment"]] if receipt["schema"]=="fleet.assignment.issued/1" else receipt["fences"] if receipt["schema"]=="fleet.writer.drain/1" else [receipt["approval"]] if receipt["schema"]=="fleet.writer-reconcile/1" else [])
                if any(envelope["body"]["target"]["device_id"]==proof.device_id for envelope in envelopes): raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        worktree=validate_worktree_head(value["worktree_head"],self.policy.max_operations)
        if worktree is not None:
            for operation in worktree["operations"]:
                matches=[row for row in self.state["phases"].values() if row["grant"]["body"]["intent_sha256"]==operation["intent_sha256"] and row["grant"]["body"]["phase"]==operation["phase"]]
                if len(matches)!=1 or matches[0]["state"]!="COMMITTED" or matches[0]["receipt_sha256"]!=operation["receipt_sha256"]:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
                grant=matches[0]["grant"]["body"]
                command=self.state["commands"][self._command_key(grant["principal_id"],grant["operation_id"])]["command"]
                if digest(command)!=operation["command_sha256"] or command["body"]["payload_sha256"]!=operation["request_sha256"] or digest({k:command["body"][k] for k in ("principal_id","principal_epoch","principal_session_id","assignment_epoch","writer_epoch","target")})!=operation["owner_sha256"]:raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        expected_assignments=[]
        for row in self.state["assignments"].values():
            body=row["assignment"]["body"]
            if body["target"]["device_id"]==proof.device_id:
                if body["target"]["route_generation"]!=proof.route_generation: raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
                expected_assignments.append({**{key:body[key] for key in ("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch")},"state":row["state"]})
        expected_phases=[{**{key:row["grant"]["body"][key] for key in ("authorization_id","operation_id","phase","intent_sha256")},"outcome":row["state"],"receipt_sha256":row["receipt_sha256"]} for row in self.state["phases"].values() if row["grant"]["body"]["target"]["device_id"]==proof.device_id]
        if type(value["assignments"]) is not list or type(value["phase_receipts"]) is not list or len(value["assignments"])>self.policy.max_assignments or len(value["phase_receipts"])>self.policy.max_operations or sorted(value["assignments"],key=canonical)!=sorted(expected_assignments,key=canonical) or sorted(value["phase_receipts"],key=canonical)!=sorted(expected_phases,key=canonical): raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        return {"device_id":proof.device_id,"witness_sha256":digest(value)}

    @_owned
    def finalize_restore(self, coordination_sha256, *, proofs):
        if type(proofs) is not list: raise PrincipalError("PRINCIPAL_SIGNATURE_INVALID")
        devices={row["assignment"]["body"]["target"]["device_id"] for row in self.state["assignments"].values()}|{row["grant"]["body"]["target"]["device_id"] for row in self.state["phases"].values()}
        witnessed={self.verify_recovery_witness(proof,coordination_sha256=coordination_sha256)["device_id"] for proof in proofs}
        if not devices<=witnessed: raise PrincipalError("PRINCIPAL_WITNESS_UNRESOLVED")
        self.state["recovery"]["phase"]="FINALIZED"; self._publish("finalize_restore")
        return clone(self.state["recovery"])

    @_owned
    def verify_domain_resolution(self,original,reconciled):
        binding=resolution_binding(original,reconciled,self.public_key)
        command=command_body(verify_envelope(original["payload"]["principal_evidence"],self.public_key,COMMAND_DOMAIN))
        for ack in reconciled["result"]["writer_acks"]:
            records=[row for row in self.state["phases"].values() if row["grant"]["body"]["authorization_id"]==ack["authorization_id"]]
            if len(records)!=1 or records[0]["state"]!="COMMITTED" or records[0]["receipt_sha256"]!=ack["receipt_sha256"]: raise PrincipalError("WRITER_RESOLUTION_INVALID")
            grant=records[0]["grant"]["body"]
            if any(grant[k]!=ack[k] for k in ("operation_id","phase","intent_sha256")) or any(grant[k]!=command[k] for k in ("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","target")): raise PrincipalError("WRITER_RESOLUTION_INVALID")
        return binding
