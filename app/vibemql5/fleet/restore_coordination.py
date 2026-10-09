"""Explicit coordinated-checkpoint recovery; no database-only latestness claim."""
from __future__ import annotations

import hashlib
import base64
import json
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..core.jobs import _atomic_write_json, _exclusive_file_lock
from .gateway_control import GatewayControlStore
from .job_journal import GatewayJobJournal, canonical, digest
from .wire import VerifiedNodeRequest, https_origin, verify_request, decode_body

_SEAL = object()
DOMAIN = b"fleet.restore.operator-approval/1\n"


class RestoreError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def integer(value, minimum=0, maximum=(1 << 63) - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise RestoreError("RESTORE_INVALID")
    return value


def sha(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise RestoreError("RESTORE_INVALID")
    return value


def copy(value):
    return json.loads(canonical(value))


@dataclass(frozen=True)
class RestorePolicy:
    max_devices: int
    max_payload_bytes: int
    max_nonces: int
    clock_skew_ms: int
    wait_ms: int

    def __post_init__(self):
        for key, bound in {"max_devices": 4096, "max_payload_bytes": 1048576,
                           "max_nonces": 65536, "clock_skew_ms": 300000,
                           "wait_ms": 60000}.items():
            integer(getattr(self, key), 0 if key == "clock_skew_ms" else 1, bound)


class ControlRestoreCommit:
    """In-process proof minted from persisted coordinator/control/job state."""
    __slots__ = ("_coordinator", "_scope_sha", "_seal")

    def __init__(self, coordinator, scope_sha, *, _seal=None):
        if _seal is not _SEAL:
            raise RestoreError("RESTORE_PROOF_INVALID")
        self._coordinator, self._scope_sha, self._seal = coordinator, scope_sha, _seal

    def assert_for(self, journal):
        coordinator = self._coordinator
        if self._seal is not _SEAL or journal is not coordinator.jobs:
            raise RestoreError("RESTORE_PROOF_INVALID")
        coordinator._check_common()
        value = coordinator.control.recovery_state()
        if value["phase"] not in {"CONTROL_RECONCILIATION_COMMITTED", "CONTROL_READY"} or value["coordination_sha256"] != self._scope_sha:
            raise RestoreError("RESTORE_PROOF_INVALID")
        receipt = coordinator.jobs.coordinated_restore_receipt()
        if receipt["coordination_sha256"] != self._scope_sha or receipt["phase"] not in {"PREPARED", "FINALIZED"}:
            raise RestoreError("RESTORE_PROOF_INVALID")
        return coordinator.commit_payload()


class RestoreCoordinator:
    """One durable finite recovery, with control READY as the final store change."""
    def __init__(self, path, control, jobs, *, audience, operator_public_key,
                 policy, now_ms, initialize=False, approval=None,
                 checkpoint_path=None, fault=None, reapproval=None, domain_journal=None, principal_authority=None):
        if type(control) is not GatewayControlStore or type(jobs) is not GatewayJobJournal or type(policy) is not RestorePolicy:
            raise RestoreError("RESTORE_INVALID")
        policy.__post_init__()
        if type(operator_public_key) is not bytes or len(operator_public_key) != 32:
            raise RestoreError("RESTORE_INVALID")
        integer(now_ms)
        from .domain import DomainJournal
        from .principals import GatewayPrincipalAuthority
        if domain_journal is not None and (type(domain_journal) is not DomainJournal or domain_journal.role!="GATEWAY"): raise RestoreError("RESTORE_INVALID")
        if principal_authority is not None and type(principal_authority) is not GatewayPrincipalAuthority: raise RestoreError("RESTORE_INVALID")
        self.domain,self.principals=domain_journal,principal_authority
        self._thread=threading.get_ident()
        self.path, self.control, self.jobs = Path(path).resolve(), control, jobs
        self.policy, self.audience, self.key, self.fault = policy, https_origin(audience), operator_public_key, fault
        self._lock = _exclusive_file_lock(self.path.with_suffix(self.path.suffix + ".owner.lock"),
                                         timeout_seconds=policy.wait_ms / 1000)
        self._lock.__enter__()
        try:
            if initialize:
                if self.path.exists():
                    raise RestoreError("RESTORE_EXISTS")
                if Path(checkpoint_path).is_symlink(): raise RestoreError("RESTORE_CHECKPOINT_INVALID")
                checkpoint = Path(checkpoint_path).resolve()
                if checkpoint.is_relative_to(control.path.parent) or checkpoint.is_relative_to(jobs.path.parent):
                    raise RestoreError("RESTORE_CHECKPOINT_NOT_INDEPENDENT")
                if checkpoint.is_symlink() or not checkpoint.is_file() or checkpoint.stat().st_size > policy.max_payload_bytes:
                    raise RestoreError("RESTORE_CHECKPOINT_INVALID")
                with checkpoint.open("rb") as stream: raw=stream.read(policy.max_payload_bytes+1)
                facts = decode_body(raw,policy.max_payload_bytes)
                if canonical(facts) != raw or facts.get("schema") != "fleet.quiescent-checkpoint/1":
                    raise RestoreError("RESTORE_CHECKPOINT_INVALID")
                self._verify_approval(approval, now_ms, hashlib.sha256(raw).hexdigest())
                required = {"schema", "audience", "control_head", "control_wall_ms", "devices", "job_export_generation", "job_mapping_sha256"}
                required |= self._head_fields()
                if type(facts) is not dict or set(facts) != required or facts["audience"] != self.audience:
                    raise RestoreError("RESTORE_CHECKPOINT_INVALID")
                scope = {key: copy(value) for key, value in facts.items() if key != "schema"}
                scope.update(schema="fleet.joint-restore/1", challenge=approval["approval"]["challenge"],
                             operator_checkpoint_sha256=hashlib.sha256(raw).hexdigest())
                self.record = {"schema": "fleet.restore-coordinator/1", "policy": asdict(policy),
                    "scope": scope, "coordination_sha256": digest(scope), "approval": copy(approval),
                    "phase": "PREPARED", "witnesses": {}, "nonces": {}, "completed_ms": None,"approval_history":[],"journal_head":None}
                self._validate_record()
                self._check_common()
                self.jobs.prepare_coordinated_restore(self.record["coordination_sha256"], scope)
                if self.domain is not None: self.domain.prepare_restore(self.record["coordination_sha256"],expected_head=scope["domain_head"])
                if self.principals is not None: self.principals.prepare_restore(self.record["coordination_sha256"],expected_head=scope["principal_head"])
                self._publish("initialize")
            else:
                if not self.path.is_file():
                    raise RestoreError("RESTORE_MISSING")
                self.record = self._read()
                self._validate_record()
                if reapproval is not None: self.reapprove(reapproval,now_ms=now_ms)
                approved_time = self.record["completed_ms"] if self.record["phase"] == "CONTROL_READY" else now_ms
                self._verify_approval(self.record["approval"], approved_time,
                                      self.record["scope"]["operator_checkpoint_sha256"])
                self._check_common()
        except BaseException:
            self.close()
            raise

    def _guard(self):
        if threading.get_ident()!=self._thread: raise RestoreError("RESTORE_WRONG_THREAD")
        if self._lock is None: raise RestoreError("RESTORE_CLOSED")

    def close(self):
        if threading.get_ident()!=self._thread: raise RestoreError("RESTORE_WRONG_THREAD")
        if self._lock is not None:
            self._lock.__exit__(None, None, None)
            self._lock = None

    def _head_fields(self):
        return ({"domain_head"} if self.domain is not None else set())|({"principal_head"} if self.principals is not None else set())

    def _witness_fields(self):
        return ({"domain_witness"} if self.domain is not None else set())|({"principal_witness"} if self.principals is not None else set())

    def _read(self):
        try:
            with self.path.open("rb") as stream: raw=stream.read(self.policy.max_payload_bytes+1)
            value = decode_body(raw,self.policy.max_payload_bytes)
            actual = value.pop("record_sha256")
            if actual != digest(value):
                raise ValueError()
            return value
        except Exception:
            raise RestoreError("RESTORE_STATE_INVALID") from None

    def _publish(self, phase):
        committed=False
        try:
            if self.fault:
                self.fault(phase + ":before_commit")
            self._validate_record()
            if len(canonical(self.record)) > self.policy.max_payload_bytes:
                raise RestoreError("RESTORE_CAPACITY")
            _atomic_write_json(self.path, {**self.record, "record_sha256": digest(self.record)})
            committed=True
            if self.fault:
                self.fault(phase + ":after_commit")
        except BaseException as error:
            if self.path.exists(): self.record=self._read()
            if isinstance(error,RestoreError) or not isinstance(error,Exception): raise
            raise RestoreError("RESTORE_COMMIT_UNCERTAIN" if committed else "RESTORE_TRANSACTION_FAILED") from None

    def reapprove(self,envelope,*,now_ms):
        self._guard()
        integer(now_ms)
        if self.record["phase"]=="CONTROL_READY" or self.record["approval"]["approval"]["expires_ms"]>now_ms: raise RestoreError("RESTORE_REAPPROVAL_UNAVAILABLE")
        self._check_common()
        self._verify_approval(envelope,now_ms,self.record["scope"]["operator_checkpoint_sha256"])
        if envelope["approval"]["challenge"]!=self.record["scope"]["challenge"] or envelope["approval"]["issued_ms"]<self.record["approval"]["approval"]["issued_ms"] or now_ms<self.record["scope"]["control_wall_ms"]: raise RestoreError("RESTORE_OPERATOR_APPROVAL_INVALID")
        if len(self.record["approval_history"])>=self.policy.max_nonces: raise RestoreError("RESTORE_CAPACITY")
        old=copy(self.record["approval"])
        self.record["approval_history"].append({"approval":old,"sha256":digest(old)})
        self.record["approval"]=copy(envelope);self._publish("reapprove")
        return self.status()

    def _verify_approval(self, envelope, now_ms, checkpoint_sha):
        try:
            if type(envelope) is not dict or set(envelope) != {"approval", "signature"}:
                raise ValueError()
            value = envelope["approval"]
            if type(value) is not dict or set(value) != {"schema", "audience", "challenge", "issued_ms", "expires_ms", "checkpoint_sha256"}:
                raise ValueError()
            if value["schema"] != "fleet.restore.operator-approval/1" or value["audience"] != self.audience or value["checkpoint_sha256"] != checkpoint_sha:
                raise ValueError()
            if re.fullmatch(r"[a-f0-9]{32}", value["challenge"]) is None:
                raise ValueError()
            integer(value["issued_ms"]); integer(value["expires_ms"])
            if not value["issued_ms"] <= now_ms < value["expires_ms"]:
                raise ValueError()
            Ed25519PublicKey.from_public_bytes(self.key).verify(bytes.fromhex(envelope["signature"]), DOMAIN + canonical(value))
        except Exception:
            raise RestoreError("RESTORE_OPERATOR_APPROVAL_INVALID") from None

    def _validate_record(self):
        value = self.record
        if set(value) != {"schema", "policy", "scope", "coordination_sha256", "approval", "phase", "witnesses", "nonces", "completed_ms", "approval_history", "journal_head"} or value["schema"] != "fleet.restore-coordinator/1" or value["policy"] != asdict(self.policy):
            raise RestoreError("RESTORE_STATE_INVALID")
        scope = value["scope"]
        required = {"schema", "audience", "challenge", "control_head", "control_wall_ms", "devices", "job_export_generation", "job_mapping_sha256", "operator_checkpoint_sha256"}
        required |= self._head_fields()
        if set(scope) != required or scope["schema"] != "fleet.joint-restore/1" or scope["audience"] != self.audience or digest(scope) != value["coordination_sha256"]:
            raise RestoreError("RESTORE_STATE_INVALID")
        if type(value["approval_history"]) is not list or len(value["approval_history"])>self.policy.max_nonces: raise RestoreError("RESTORE_STATE_INVALID")
        for history in value["approval_history"]:
            if type(history) is not dict or set(history)!={"approval","sha256"} or digest(history["approval"])!=history["sha256"]: raise RestoreError("RESTORE_STATE_INVALID")
            self._verify_approval(history["approval"],history["approval"]["approval"]["issued_ms"],scope["operator_checkpoint_sha256"])
            if history["approval"]["approval"]["challenge"]!=scope["challenge"]: raise RestoreError("RESTORE_STATE_INVALID")
        if value["approval"]["approval"]["challenge"]!=scope["challenge"]: raise RestoreError("RESTORE_STATE_INVALID")
        head=scope["control_head"]
        if type(head) is not dict or set(head)!={"schema","revision","sha256"} or head["schema"]!="fleet.control-head/1": raise RestoreError("RESTORE_STATE_INVALID")
        integer(head["revision"],1);sha(head["sha256"])
        head=value["journal_head"]
        if head is not None:
            if type(head) is not dict or set(head)!={"schema","sha256"} or head["schema"]!="fleet.job-recovery-head/1": raise RestoreError("RESTORE_STATE_INVALID")
            sha(head["sha256"])
        sha(scope["job_mapping_sha256"]); sha(scope["operator_checkpoint_sha256"])
        integer(scope["control_wall_ms"]); integer(scope["job_export_generation"], 1)
        if type(scope["devices"]) is not list or not 1 <= len(scope["devices"]) <= self.policy.max_devices:
            raise RestoreError("RESTORE_SCOPE_INVALID")
        seen = set()
        for node in scope["devices"]:
            node_fields={"device_id", "public_key", "route_generation", "state", "registry_sha256", "session_id"}|({"worktree_head"} if self.principals is not None else set())
            if set(node) != node_fields or re.fullmatch(r"dev_[a-f0-9]{32}", node["device_id"]) is None or node["device_id"] in seen:
                raise RestoreError("RESTORE_SCOPE_INVALID")
            if self.principals is not None:
                from .principals import validate_worktree_head
                validate_worktree_head(node["worktree_head"],self.principals.policy.max_operations)
            seen.add(node["device_id"]); sha(node["public_key"]); sha(node["registry_sha256"])
            integer(node["route_generation"], 1)
            if node["state"] not in {"ACTIVE", "REVOKED"} or type(node["session_id"]) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", node["session_id"]) is None:
                raise RestoreError("RESTORE_SCOPE_INVALID")
        if value["phase"] not in {"PREPARED", "CONTROL_RECONCILIATION_COMMITTED", "JOB_FINALIZED", "CONTROL_READY"} or not set(value["witnesses"]) <= seen or len(value["nonces"]) > self.policy.max_nonces:
            raise RestoreError("RESTORE_STATE_INVALID")
        if value["phase"] == "CONTROL_READY":
            integer(value["completed_ms"])
        elif value["completed_ms"] is not None:
            raise RestoreError("RESTORE_STATE_INVALID")
        for device_id, witness in value["witnesses"].items():
            if type(witness) is not dict or set(witness) != {"sha256", "body", "reconciled", "signed_envelope"} or type(witness["reconciled"]) is not bool or digest(witness["body"]) != witness["sha256"]:
                raise RestoreError("RESTORE_STATE_INVALID")
            evidence = witness["signed_envelope"]
            if type(evidence) is not dict or set(evidence) != {"method", "path", "header_pairs", "body_base64", "audience"} or evidence["audience"] != self.audience or evidence["path"] != "/fleet/v1/reconcile":
                raise RestoreError("RESTORE_STATE_INVALID")
            node = next(node for node in scope["devices"] if node["device_id"] == device_id)
            proof = verify_request(evidence["method"], evidence["path"], evidence["header_pairs"],
                base64.b64decode(evidence["body_base64"], validate=True), audience=self.audience,
                max_body_bytes=self.policy.max_payload_bytes, expected_public_key=node["public_key"])
            if proof.body != witness["body"] or proof.device_id != device_id or proof.route_generation != node["route_generation"]:
                raise RestoreError("RESTORE_STATE_INVALID")
        for nonce, receipt in value["nonces"].items():
            sha(nonce)
            if type(receipt) is not dict or set(receipt) != {"request_sha256", "witness_sha256"}:
                raise RestoreError("RESTORE_STATE_INVALID")
            sha(receipt["request_sha256"]); sha(receipt["witness_sha256"])

    def _check_common(self):
        scope = self.record["scope"]
        recovery = self.control.recovery_state()
        if self.record["phase"] == "CONTROL_READY":
            if recovery["phase"] != "CONTROL_READY" or recovery["coordination_sha256"] != self.record["coordination_sha256"]:
                raise RestoreError("RESTORE_PROOF_INVALID")
            return
        if self.control.assert_restored_ledger() != scope["control_head"]:
            raise RestoreError("RESTORE_CONTROL_HEAD_MISMATCH")
        state = self.control.snapshot()
        actual = [{key: row[key] for key in ("device_id", "public_key", "route_generation", "state")} for row in state["devices"]]
        expected = [{key: row[key] for key in ("device_id", "public_key", "route_generation", "state")} for row in scope["devices"]]
        if sorted(actual, key=lambda node: node["device_id"]) != sorted(expected, key=lambda node: node["device_id"]):
            raise RestoreError("RESTORE_ROUTE_KEY_DRIFT")
        if self.jobs.mapping_sha256() != scope["job_mapping_sha256"]: raise RestoreError("RESTORE_JOB_MAPPING_MISMATCH")
        if self.record["journal_head"] is not None and self.jobs.recovery_head()!=self.record["journal_head"]: raise RestoreError("RESTORE_JOB_HEAD_MISMATCH")
        if self.domain is not None: self.domain.assert_quiescent_head(scope["domain_head"])
        if self.principals is not None: self.principals.assert_quiescent_head(scope["principal_head"])

    def scope(self):
        self._guard()
        return copy(self.record["scope"])

    def accept_witness(self, proof, *, now_ms):
        self._guard()
        if type(proof) is not VerifiedNodeRequest or proof.path != "/fleet/v1/reconcile":
            raise RestoreError("RESTORE_PROOF_INVALID")
        integer(now_ms)
        self._check_common()
        self._verify_approval(self.record["approval"], now_ms, self.record["scope"]["operator_checkpoint_sha256"])
        value, scope = proof.body, self.record["scope"]
        if type(value) is not dict or set(value) != ({"schema", "coordination_sha256", "registry_sha256", "session_id", "transport_witness", "job_witness"}|self._witness_fields()) or value["schema"] != "fleet.reconcile/1" or value["coordination_sha256"] != self.record["coordination_sha256"]:
            raise RestoreError("RESTORE_WITNESS_INVALID")
        node = next((item for item in scope["devices"] if item["device_id"] == proof.device_id), None)
        if node is None or proof.public_key != node["public_key"] or proof.route_generation != node["route_generation"] or value["registry_sha256"] != node["registry_sha256"] or value["session_id"] != node["session_id"]:
            raise RestoreError("RESTORE_ROUTE_KEY_DRIFT")
        if now_ms < scope["control_wall_ms"] or abs(proof.timestamp_ms - now_ms) > self.policy.clock_skew_ms:
            raise RestoreError("RESTORE_TIME_INVALID")
        transport = value["transport_witness"]
        fields = {"schema", "device_id", "public_key", "audience", "challenge", "pending_count", "request_count", "latest_control_head", "journal_sha256"}
        if type(transport) is not dict or set(transport) != fields or transport["schema"] != "fleet.transport-witness/1" or transport["device_id"] != proof.device_id or transport["public_key"] != proof.public_key or transport["audience"] != self.audience or transport["challenge"] != scope["challenge"] or type(transport["pending_count"]) is not int or transport["pending_count"] != 0:
            raise RestoreError("RESTORE_TRANSPORT_UNRESOLVED")
        integer(transport["request_count"], 1); sha(transport["journal_sha256"])
        head = transport["latest_control_head"]
        if type(head) is not dict or set(head) != {"schema", "revision", "sha256"} or head["schema"] != "fleet.control-head/1":
            raise RestoreError("RESTORE_TRANSPORT_UNRESOLVED")
        integer(head["revision"], 1); sha(head["sha256"])
        if head["revision"] > scope["control_head"]["revision"] or (head["revision"] == scope["control_head"]["revision"] and head != scope["control_head"]):
            raise RestoreError("RESTORE_LEDGER_DELTA_UNAVAILABLE")
        if self.domain is not None: self.domain.verify_recovery_witness(proof,coordination_sha256=self.record["coordination_sha256"])
        if self.principals is not None: self.principals.verify_recovery_witness(proof,coordination_sha256=self.record["coordination_sha256"])
        if self.principals is not None and value["principal_witness"]["worktree_head"]!=node["worktree_head"]:
            raise RestoreError("RESTORE_WORKTREE_HEAD_MISMATCH")
        self.jobs.validate_recovery_witness(value["job_witness"],registered_public_key=proof.public_key,
            current_route_generation=proof.route_generation,current_session_id=value["session_id"])
        nonce_sha = digest({"device_id": proof.device_id, "route_generation": proof.route_generation, "nonce": proof.nonce})
        if nonce_sha in self.record["nonces"]:
            raise RestoreError("RESTORE_REPLAY")
        if len(self.record["nonces"]) >= self.policy.max_nonces:
            raise RestoreError("RESTORE_CAPACITY")
        witness_sha = digest(value)
        old = self.record["witnesses"].get(proof.device_id)
        if old is not None and old["sha256"] != witness_sha:
            raise RestoreError("RESTORE_WITNESS_CONFLICT")
        self.record["nonces"][nonce_sha] = {"request_sha256": proof.request_sha256, "witness_sha256": witness_sha}
        if old is None:
            self.record["witnesses"][proof.device_id] = {"sha256": witness_sha, "body": copy(value),
                "reconciled": False, "signed_envelope": proof.recovery_evidence()}
        self._publish("witness_intent")
        if not self.record["witnesses"][proof.device_id]["reconciled"]:
            self.jobs.reconcile_node(value["job_witness"], registered_public_key=proof.public_key,
                                     current_route_generation=proof.route_generation, current_session_id=value["session_id"])
            self.record["witnesses"][proof.device_id]["reconciled"] = True
            self._publish("witness_reconciled")
        return {"schema": "fleet.reconcile.receipt/1", "coordination_sha256": self.record["coordination_sha256"],
                "device_id": proof.device_id, "witness_sha256": witness_sha, "dispatch_enabled": False}

    def _proofs(self):
        proofs=[]
        for witness in self.record["witnesses"].values():
            e=witness["signed_envelope"]
            proofs.append(verify_request(e["method"],e["path"],e["header_pairs"],base64.b64decode(e["body_base64"],validate=True),audience=self.audience,max_body_bytes=self.policy.max_payload_bytes))
        return proofs

    def _all_witnesses(self):
        if set(self.record["witnesses"]) != {node["device_id"] for node in self.record["scope"]["devices"]} or not all(item["reconciled"] is True for item in self.record["witnesses"].values()):
            raise RestoreError("RESTORE_WITNESSES_INCOMPLETE")

    def assert_control_commit(self, control):
        self._guard()
        if control is not self.control:
            raise RestoreError("RESTORE_PROOF_INVALID")
        self._check_common(); self._all_witnesses()
        receipt = self.jobs.coordinated_restore_receipt()
        if receipt["phase"] not in {"PREPARED", "FINALIZED"} or receipt["coordination_sha256"] != self.record["coordination_sha256"]:
            raise RestoreError("RESTORE_PROOF_INVALID")
        return self.record["coordination_sha256"]

    def assert_control_ready(self, control):
        self._guard()
        value = self.assert_control_commit(control)
        if self.jobs.coordinated_restore_receipt()["phase"] != "FINALIZED":
            raise RestoreError("RESTORE_PROOF_INVALID")
        return value

    def commit_payload(self):
        self._guard()
        return {"schema": "fleet.control-restore-commit/1", "coordination_sha256": self.record["coordination_sha256"],
                "scope_sha256": digest(self.record["scope"]), "control": self.control.recovery_state(),
                "jobs": self.jobs.coordinated_restore_receipt()}

    def control_commit_receipt(self):
        self._guard()
        self.assert_control_commit(self.control)
        return ControlRestoreCommit(self, self.record["coordination_sha256"], _seal=_SEAL)

    def finalize(self, *, now_ms):
        self._guard()
        integer(now_ms)
        if self.record["phase"] == "CONTROL_READY":
            return self.status()
        self._check_common(); self._all_witnesses()
        self._verify_approval(self.record["approval"], now_ms, self.record["scope"]["operator_checkpoint_sha256"])
        if self.record["journal_head"] is None:
            self.record["journal_head"]=self.jobs.recovery_head();self._publish("prepared_head")
        self.control.commit_coordinated_recovery(self)
        self.record["phase"] = "CONTROL_RECONCILIATION_COMMITTED"
        self._publish("control_commit")
        self.jobs.finalize_coordinated_restore(self.control_commit_receipt())
        proofs=self._proofs()
        if self.domain is not None: self.domain.finalize_restore(self.record["coordination_sha256"],proofs=proofs)
        if self.principals is not None: self.principals.finalize_restore(self.record["coordination_sha256"],proofs=proofs)
        self.record["journal_head"]=self.jobs.recovery_head()
        self.record["phase"] = "JOB_FINALIZED"
        self._publish("job_finalized")
        self.control.complete_coordinated_recovery(self)
        self.record.update(phase="CONTROL_READY", completed_ms=now_ms)
        self._publish("control_ready")
        return self.status()

    def status(self):
        self._guard()
        self._check_common()
        ready = self.record["phase"] == "CONTROL_READY" and self.control.recovery_state()["phase"] == "CONTROL_READY" and self.jobs.coordinated_restore_receipt()["phase"] == "FINALIZED"
        return {"schema": "fleet.joint-restore.status/1", "phase": self.record["phase"],
                "coordination_sha256": self.record["coordination_sha256"], "ready": ready,
                "dispatch_enabled": ready}
