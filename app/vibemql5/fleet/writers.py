"""Node-owned verified writer fences and two-commit source reconciliation."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from functools import wraps

from ..core.concurrency import ConcurrencyManager
from ..core.jobs import _atomic_write_json, _exclusive_file_lock
from ..core.revisions import _atomic_write_bytes
from .job_journal import canonical, digest
from .project_targets import FleetProjectStore, FleetProjectError
from .principals import (PrincipalError, verify_envelope, assignment_body, command_body,
    identity, integer, sha, clone, ASSIGN_DOMAIN, COMMAND_DOMAIN, PHASE_DOMAIN, DRAIN_DOMAIN, PATH_PHASES, resolution_binding)
from .wire import decode_body, https_origin

_SEAL = object()

def _safe(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        try:
            return method(self,*args,**kwargs)
        except (WriterError,PrincipalError,FleetProjectError):
            raise
        except Exception as error:
            from .wire import WireError
            if isinstance(error,WireError): raise
            raise WriterError("WRITER_OUTCOME_UNKNOWN") from None
    return call


class WriterError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def empty_writer_witness(root, *, device_id, route_generation, session_id,
                         coordination_sha256, expected_worktree_head):
    """Signed-node evidence of absent authority, never a replacement owner."""
    from .identity import IdentityRegistry
    identity(device_id);integer(route_generation,minimum=1);identity(session_id);sha(coordination_sha256)
    if expected_worktree_head is not None: raise WriterError("WRITER_ABSENCE_UNPROVEN")
    try:
        root=Path(root).resolve(strict=True)
        registry=IdentityRegistry(root).load()
        if registry is None or registry["device_id"]!=device_id: raise WriterError("WRITER_ABSENCE_UNPROVEN")
        for parent in (root/"state",root/"state"/"fleet"):
            if parent.is_symlink(): raise WriterError("WRITER_ABSENCE_UNPROVEN")
            if parent.exists() and (not parent.is_dir() or getattr(parent.stat(),"st_file_attributes",0)&0x400): raise WriterError("WRITER_ABSENCE_UNPROVEN")
        fleet=root/"state"/"fleet"
        if fleet.exists():
            with os.scandir(fleet) as entries:
                for count,entry in enumerate(entries,1):
                    name=entry.name.casefold().lstrip(".")
                    if count>4096 or name.startswith(("writers","worktrees")) or name=="disabled-git-hooks": raise WriterError("WRITER_ABSENCE_UNPROVEN")
    except WriterError: raise
    except Exception: raise WriterError("WRITER_ABSENCE_UNPROVEN") from None
    return {"schema":"fleet.node-writer-witness/1","authority":"EMPTY_ABSENCE",
        "coordination_sha256":coordination_sha256,"device_id":device_id,"route_generation":route_generation,
        "session_id":session_id,"pending_intents":[],"assignments":[],"phase_receipts":[],"worktree_head":None}


@dataclass(frozen=True)
class WriterPolicy:
    max_operations: int
    max_projects: int
    max_payload_bytes: int
    max_source_bytes: int
    wait_ms: int
    def __post_init__(self):
        for name, bound in {"max_operations":65536,"max_projects":4096,"max_payload_bytes":4194304,
                            "max_source_bytes":1048576,"wait_ms":60000}.items():
            integer(getattr(self,name),minimum=1,maximum=bound)


class NodeCommand:
    __slots__ = ("_runtime", "_body", "_request", "_seal", "_approval")
    def __init__(self, runtime, body, request, *, approval=None, _seal=None):
        if _seal is not _SEAL: raise WriterError("WRITER_PROOF_INVALID")
        for name,value in {"_runtime":runtime,"_body":canonical(body),"_request":canonical(request),"_seal":_seal,"_approval":None if approval is None else canonical(approval)}.items():
            object.__setattr__(self,name,value)
    def __setattr__(self,name,value): raise WriterError("WRITER_PROOF_IMMUTABLE")
    @property
    def body(self): return json.loads(self._body)["body"]
    @property
    def request(self): return json.loads(self._request)


class PhaseFence:
    __slots__ = ("_runtime", "_command", "_key", "_grant", "_seal", "_completed", "_recovery")
    def __init__(self, runtime, command, key, grant, *, recovery=False, _seal=None):
        if _seal is not _SEAL: raise WriterError("WRITER_PROOF_INVALID")
        for name,value in {"_runtime":runtime,"_command":command,"_key":key,"_grant":canonical(grant),"_seal":_seal,"_completed":False,"_recovery":recovery}.items():object.__setattr__(self,name,value)
    def __setattr__(self,name,value):
        if name!="_completed": raise WriterError("WRITER_PROOF_IMMUTABLE")
        object.__setattr__(self,name,value)
    @property
    def recovery(self):return self._recovery
    @property
    def body(self): return json.loads(self._grant)["body"]


class NodePrincipalRuntime:
    def __init__(self, root, *, gateway_public_key, audience, device_id, route_generation,
                 session_id, policy, initialize=False, fault=None):
        if type(gateway_public_key) is not bytes or len(gateway_public_key)!=32 or type(policy) is not WriterPolicy or type(initialize) is not bool:
            raise WriterError("WRITER_INVALID")
        policy.__post_init__(); identity(device_id); integer(route_generation,minimum=1); identity(session_id)
        self.root,self.key,self.audience = Path(root).resolve(),gateway_public_key,https_origin(audience)
        self.device_id,self.route_generation,self.session_id,self.policy,self.fault = device_id,route_generation,session_id,policy,fault
        self.projects = FleetProjectStore(self.root)
        self.path = self.root / "state" / "fleet" / "writers.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._mutex,self._transport,self.worktrees = threading.RLock(),None,None
        self._lock = _exclusive_file_lock(self.path.with_suffix(".owner.lock"),timeout_seconds=policy.wait_ms/1000)
        self._lock.__enter__()
        try:
            if initialize:
                if self.path.exists(): raise WriterError("WRITER_EXISTS")
                self.state={"schema":"fleet.node-writers/1","policy":asdict(policy),"device_id":device_id,
                    "route_generation":route_generation,"session_id":session_id,"gateway_public_key":gateway_public_key.hex(),
                    "audience":self.audience,"last_wall_ms":0,"assignments":{},"operations":{},"phases":{}}
                self._publish("initialize")
            else:
                self.state=self._read(); self._validate()
        except (WriterError, PrincipalError, KeyboardInterrupt, SystemExit):
            self.close(); raise
        except Exception:
            self.close(); raise WriterError("WRITER_STATE_INVALID") from None

    def _guard(self):
        if self._lock is None: raise WriterError("WRITER_CLOSED")

    def close(self):
        with self._mutex:
            if self._lock is not None: self._lock.__exit__(None,None,None); self._lock=None

    def bind_control_transport(self, transport):
        from .transport import NodeRpcProxy, NodeClient
        with self._mutex:
            self._guard()
            if type(transport) not in {NodeRpcProxy,NodeClient} or transport.device_id!=self.device_id or transport.route_generation!=self.route_generation:
                raise WriterError("WRITER_TRANSPORT_INVALID")
            self._transport=transport

    def bind_worktrees(self, worktrees):
        from .worktrees import NodeWorktrees
        with self._mutex:
            self._guard()
            if type(worktrees) is not NodeWorktrees or worktrees.principals is not self: raise WriterError("WRITER_INVALID")
            self.worktrees=worktrees

    def _read(self):
        try:
            with self.path.open("rb") as stream: raw=stream.read(self.policy.max_payload_bytes+1)
            value=decode_body(raw,self.policy.max_payload_bytes)
            if value.pop("record_sha256")!=digest(value): raise ValueError()
            return value
        except Exception: raise WriterError("WRITER_STATE_INVALID") from None

    def _validate(self):
        value=self.state
        if set(value)!={"schema","policy","device_id","route_generation","session_id","gateway_public_key","audience","last_wall_ms","assignments","operations","phases"} or value["schema"]!="fleet.node-writers/1" or value["policy"]!=asdict(self.policy) or any(value[k]!=getattr(self,k if k!="gateway_public_key" else "key").hex() if k=="gateway_public_key" else value[k]!=getattr(self,k) for k in ("device_id","route_generation","session_id","audience","gateway_public_key")):
            raise WriterError("WRITER_STATE_INVALID")
        integer(value["last_wall_ms"])
        for name,maximum in (("assignments",self.policy.max_projects),("operations",self.policy.max_operations),("phases",self.policy.max_operations*5)):
            if type(value[name]) is not dict or len(value[name])>maximum: raise WriterError("WRITER_STATE_INVALID")
        for project,row in value["assignments"].items():
            if set(row)!={"assignment","state","fence_epoch"} or row["state"] not in {"ACTIVE","DRAINING","RELEASED"}: raise WriterError("WRITER_STATE_INVALID")
            body=verify_envelope(row["assignment"],self.key,ASSIGN_DOMAIN)
            assignment_body(body,fence=body.get("schema")=="fleet.writer-fence/1")
            if project!=body["project_id"] or body["target"]["device_id"]!=self.device_id or body["target"]["route_generation"]!=self.route_generation: raise WriterError("WRITER_STATE_INVALID")
            integer(row["fence_epoch"],minimum=body["writer_epoch"])
        for key,row in value["phases"].items():
            if set(row)!={"command","grant","state","receipt","ack"} or row["state"] not in {"INTENT","UNKNOWN","COMMITTED","NOT_ATTEMPTED"}: raise WriterError("WRITER_STATE_INVALID")
            command=command_body(verify_envelope(row["command"],self.key,COMMAND_DOMAIN)); grant=verify_envelope(row["grant"],self.key,PHASE_DOMAIN)
            if key!=digest({"intent_sha256":command["intent_sha256"],"phase":grant["phase"]}) or any(grant[k]!=command[k] for k in ("operation_id","project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","intent_sha256","target")) or grant["phase"] not in PATH_PHASES.get(command["path"],set()): raise WriterError("WRITER_STATE_INVALID")
            if row["state"] in {"INTENT","UNKNOWN"} and (row["receipt"] is not None or row["ack"] is not None): raise WriterError("WRITER_STATE_INVALID")
            if row["state"] in {"COMMITTED","NOT_ATTEMPTED"} and (type(row["receipt"]) is not dict or row["ack"]!=self._ack(grant,row["state"],row["receipt"])): raise WriterError("WRITER_STATE_INVALID")
        for op,row in value["operations"].items():
            sha(op)
            if set(row)!={"command","frozen_id","intent_sha256","state","checkpoint_id","source_sha256","source_bytes","receipt"} or row["intent_sha256"]!=op or row["state"] not in {"PREPARED","SOURCE_COMMITTED","SESSION_COMMITTED","COMMITTED"}: raise WriterError("WRITER_STATE_INVALID")
            command=command_body(verify_envelope(row["command"],self.key,COMMAND_DOMAIN))
            if command["intent_sha256"]!=op: raise WriterError("WRITER_STATE_INVALID")
            sha(row["source_sha256"]); integer(row["source_bytes"]); identity(row["checkpoint_id"])

    def _publish(self, action):
        committed=False
        try:
            self._validate()
            if len(canonical(self.state))>self.policy.max_payload_bytes: raise WriterError("WRITER_CAPACITY")
            if self.fault: self.fault(action+":before_commit")
            _atomic_write_json(self.path,{**self.state,"record_sha256":digest(self.state)}); committed=True
            if self.fault: self.fault(action+":after_commit")
        except BaseException as error:
            if self.path.exists(): self.state=self._read()
            if isinstance(error,(WriterError,PrincipalError)) or not isinstance(error,Exception): raise
            raise WriterError("WRITER_COMMIT_UNCERTAIN" if committed else "WRITER_TRANSACTION_FAILED") from None

    def _now(self):
        now=int(time.time()*1000)
        if now<self.state["last_wall_ms"]: raise WriterError("WRITER_CLOCK_ROLLBACK")
        if now!=self.state["last_wall_ms"]:
            self.state["last_wall_ms"]=now; self._publish("observe_wall")
        return now

    def verify_command(self, path, payload, operation_id):
        with self._mutex:
            self._guard()
            if type(payload) is not dict or set(payload)!={"request","principal_evidence","assignment"}: raise WriterError("WRITER_PROOF_INVALID")
            body=command_body(verify_envelope(payload["principal_evidence"],self.key,COMMAND_DOMAIN))
            assignment=assignment_body(verify_envelope(payload["assignment"],self.key,ASSIGN_DOMAIN))
            request=payload["request"]
            if type(request) is not dict or set(request)!={"schema","node","operation_id","payload"} or request["schema"]!="fleet.domain-request/1" or type(request["payload"]) is not dict: raise WriterError("WRITER_PROOF_INVALID")
            if body["path"]!=path or body["operation_id"]!=operation_id or request["operation_id"]!=operation_id or body["payload_sha256"]!=digest({"path":path,"payload":request}) or body["project_id"]!=request["payload"].get("project_id") or body["audience"]!=self.audience:
                raise WriterError("WRITER_PROOF_INVALID")
            for key in ("project_id","principal_id","principal_epoch","principal_session_id","assignment_epoch","writer_epoch","target"):
                if body[key]!=assignment[key]: raise WriterError("WRITER_FENCE_MISMATCH")
            if body["target"]["device_id"]!=self.device_id or body["target"]["route_generation"]!=self.route_generation or request["node"]!={"device_id":self.device_id,"route_generation":self.route_generation}: raise WriterError("WRITER_FENCE_MISMATCH")
            now=self._now()
            if not body["issued_ms"]<=now<body["expires_ms"]: raise WriterError("WRITER_EXPIRED")
            old=self.state["assignments"].get(body["project_id"])
            if old is None:
                if len(self.state["assignments"])>=self.policy.max_projects: raise WriterError("WRITER_CAPACITY")
                self.state["assignments"][body["project_id"]]={"assignment":clone(payload["assignment"]),"state":"ACTIVE","fence_epoch":body["writer_epoch"]}
                self._publish("install_assignment")
            elif old["assignment"]!=payload["assignment"]:
                prior=old["assignment"]["body"]
                if old["state"]!="RELEASED" or self._pending(body["project_id"]) or body["assignment_epoch"]<=prior["assignment_epoch"] or body["writer_epoch"]<old["fence_epoch"]: raise WriterError("WRITER_FENCE_MISMATCH")
                self.state["assignments"][body["project_id"]]={"assignment":clone(payload["assignment"]),"state":"ACTIVE","fence_epoch":body["writer_epoch"]}
                self._publish("install_successor")
            if not (path=="/fleet/v1/writers/release" and old is not None and old["state"] in {"DRAINING","RELEASED"} and old["assignment"]==payload["assignment"]): self._current(body)
            return NodeCommand(self,payload["principal_evidence"],request["payload"],_seal=_SEAL)

    def _current(self, body, approval=None):
        row=self.state["assignments"].get(body["project_id"])
        drained=False
        if approval is not None:
            evidence=verify_envelope(json.loads(approval),self.key,DRAIN_DOMAIN)
            drained=(evidence.get("schema")=="fleet.writer-drain-approval/1" and evidence.get("audience")==self.audience and evidence.get("phase")=="session_commit" and all(evidence.get(k)==body[k] for k in ("project_id","principal_id","principal_epoch","assignment_epoch","writer_epoch","operation_id","intent_sha256","target")) and type(evidence.get("issued_ms")) is int and type(evidence.get("expires_ms")) is int and evidence["issued_ms"]<=self._now()<evidence["expires_ms"])
        if row is None or (row["state"]!="ACTIVE" and not (drained and row["state"]=="DRAINING")) or (row["fence_epoch"]!=body["writer_epoch"] and not (drained and row["fence_epoch"]==body["writer_epoch"]+1)) or any(row["assignment"]["body"][k]!=body[k] for k in ("principal_id","principal_epoch","principal_session_id","assignment_epoch","writer_epoch","target")):
            raise WriterError("WRITER_FENCE_MISMATCH")

    def _command(self, command):
        self._guard()
        if type(command) is not NodeCommand or command._runtime is not self or command._seal is not _SEAL: raise WriterError("WRITER_PROOF_INVALID")
        return command.body

    def _pending(self, project):
        phases=[row["grant"]["body"]["intent_sha256"] for row in self.state["phases"].values() if row["grant"]["body"]["project_id"]==project and row["state"] in {"INTENT","UNKNOWN"}]
        operations=[row["intent_sha256"] for row in self.state["operations"].values() if row["command"]["body"]["project_id"]==project and row["state"]!="COMMITTED"]
        return sorted(set(phases+operations))

    @staticmethod
    def _ack(body,outcome,receipt):
        return {**{k:body[k] for k in ("authorization_id","operation_id","phase","intent_sha256")},"outcome":outcome,"receipt_sha256":digest(receipt)}

    @contextmanager
    def phase_guard(self, command, phase, intent_sha256):
        with self._mutex:
            body=self._command(command); self._current(body,command._approval)
            if phase not in PATH_PHASES.get(body["path"],set()) or intent_sha256!=body["intent_sha256"]: raise WriterError("WRITER_PHASE_CONFLICT")
            key=digest({"intent_sha256":intent_sha256,"phase":phase})
            if key in self.state["phases"]: raise WriterError("WRITER_PHASE_UNRESOLVED")
            if any(x!=intent_sha256 for x in self._pending(body["project_id"])): raise WriterError("WRITER_UNRESOLVED")
            if self._transport is None: raise WriterError("WRITER_TRANSPORT_INVALID")
            project=self.projects.get(body["project_id"])
            if project["owner_device_id"]!=self.device_id: raise WriterError("WRITER_FENCE_MISMATCH")
            resource=project["session"]["workspace"]+":"+project["session"]["ea"]
            with ConcurrencyManager(self.root).mutation("fleet_source_guard",resource=resource,wait_seconds=0):
                self._current(body,command._approval); now=self._now()
                binding={**{k:body[k] for k in ("operation_id","project_id","target","principal_id","principal_epoch","assignment_epoch","writer_epoch","intent_sha256")},"session_id":self.session_id,"phase":phase,"challenge":secrets.token_hex(16)}
                acks=self.writer_acks(command)
                if acks: binding["phase_acks"]=acks
                if command._approval is not None:
                    if phase!="session_commit": raise WriterError("WRITER_PHASE_CONFLICT")
                    binding["drain_approval"]=json.loads(command._approval)
                envelope=self._transport.writers_authorize(**binding)
                grant=verify_envelope(envelope,self.key,PHASE_DOMAIN)
                if any(grant.get(k)!=v for k,v in binding.items()) or grant.get("schema")!="fleet.writer-authorization/1" or grant.get("audience")!=self.audience or type(grant.get("issued_ms")) is not int or type(grant.get("expires_ms")) is not int or not grant["issued_ms"]<=self._now()<grant["expires_ms"]: raise WriterError("WRITER_PROOF_INVALID")
                self._current(body,command._approval)
                if len(self.state["phases"])>=self.policy.max_operations*5: raise WriterError("WRITER_CAPACITY")
                self.state["phases"][key]={"command":json.loads(command._body),"grant":clone(envelope),"state":"INTENT","receipt":None,"ack":None}
                self._publish("phase_intent")
                fence=PhaseFence(self,command,key,envelope,_seal=_SEAL)
                try:
                    yield fence
                except Exception as error:
                    from .wire import WireError
                    if isinstance(error,(WriterError,PrincipalError,FleetProjectError,WireError)): raise
                    raise WriterError("WRITER_OUTCOME_UNKNOWN") from None
                finally:
                    if not fence._completed and self.state["phases"][key]["state"]=="INTENT":
                        self.state["phases"][key]["state"]="UNKNOWN"
                        self._publish("phase_unknown")

    def complete_phase(self, fence, receipt):
        with self._mutex:
            self._guard()
            if type(fence) is not PhaseFence or fence._runtime is not self or fence._seal is not _SEAL or fence._completed or type(receipt) is not dict: raise WriterError("WRITER_PROOF_INVALID")
            body=fence._command.body
            if not fence.recovery: self._current(body,fence._command._approval)
            row=self.state["phases"].get(fence._key)
            if row is None or row["state"] not in {"INTENT","UNKNOWN"}: raise WriterError("WRITER_PHASE_UNRESOLVED")
            row.update(state="COMMITTED",receipt=clone(receipt),ack=self._ack(fence.body,"COMMITTED",receipt))
            self._publish("phase_committed"); fence._completed=True
            return clone(row["ack"])

    def recheck_phase(self, fence):
        """Fresh gateway admission for the same issued phase, never a new effect."""
        with self._mutex:
            self._guard()
            if type(fence) is not PhaseFence or fence._runtime is not self or fence._seal is not _SEAL or fence._completed or fence.recovery:
                raise WriterError("WRITER_PROOF_INVALID")
            self._current(fence._command.body, fence._command._approval)
            grant=json.loads(fence._grant)
            fields={"session_id","operation_id","project_id","target","principal_id","principal_epoch","assignment_epoch","writer_epoch","phase","intent_sha256","challenge","phase_acks","drain_approval"}
            binding={key:value for key,value in grant["body"].items() if key in fields}
            observed=self._transport.writers_authorize(**binding)
            verify_envelope(observed,self.key,PHASE_DOMAIN)
            if observed!=grant or not grant["body"]["issued_ms"]<=self._now()<grant["body"]["expires_ms"]:
                raise WriterError("WRITER_PROOF_INVALID")
            self._current(fence._command.body, fence._command._approval)

    def recover_phase(self, command, phase, receipt):
        with self._mutex:
            body=self._command(command); self._current(body,command._approval)
            key=digest({"intent_sha256":body["intent_sha256"],"phase":phase}); row=self.state["phases"].get(key)
            if row is None: raise WriterError("WRITER_PHASE_UNRESOLVED")
            if row["state"]=="COMMITTED":
                if row["receipt"]!=receipt: raise WriterError("WRITER_PHASE_CONFLICT")
                return clone(row["ack"])
            fence=PhaseFence(self,command,key,row["grant"],recovery=True,_seal=_SEAL)
            return self.complete_phase(fence,receipt)

    def writer_acks(self, command):
        with self._mutex:
            body=self._command(command)
            return [clone(row["ack"]) for row in self.state["phases"].values() if row["grant"]["body"]["intent_sha256"]==body["intent_sha256"] and row["ack"] is not None]

    def drain_fence(self, envelope):
        with self._mutex:
            self._guard(); body=assignment_body(verify_envelope(envelope,self.key,ASSIGN_DOMAIN),fence=True)
            row=self.state["assignments"].get(body["project_id"])
            if row is None:
                if len(self.state["assignments"])>=self.policy.max_projects: raise WriterError("WRITER_CAPACITY")
                row={"assignment":clone(envelope),"state":"DRAINING","fence_epoch":body["fence_epoch"]}
                self.state["assignments"][body["project_id"]]=row
            if any(row["assignment"]["body"][k]!=body[k] for k in row["assignment"]["body"] if k not in {"schema","state","fence_epoch"}) or body["target"]["device_id"]!=self.device_id: raise WriterError("WRITER_FENCE_MISMATCH")
            row.update(state="DRAINING",fence_epoch=body["fence_epoch"]); self._publish("drain_fence")
            pending=self._pending(body["project_id"])
            if not pending:
                row["state"]="RELEASED"; self._publish("fence_released")
            return {"schema":"fleet.writer-fence.receipt/1","project_id":body["project_id"],"fence_epoch":body["fence_epoch"],"pending_intents":sorted(set(pending)),"writer_acks":[]}

    @_safe
    def apply_command(self,path,payload,*,operation_id):
        with self._mutex:
            self._guard()
            if path=="/fleet/v1/writers/reconcile":
                if type(payload) is not dict or set(payload)!={"approval"}: raise WriterError("WRITER_INVALID")
                return self.reconcile_original(payload["approval"])
            if path=="/fleet/v1/writers/fence":
                if type(payload) is not dict or set(payload)!={"fence"}: raise WriterError("WRITER_INVALID")
                return self.drain_fence(payload["fence"])
            command=self.verify_command(path,payload,operation_id)
            if path=="/fleet/v1/writers/acquire": return {"schema":"fleet.writer-acquired/1","project_id":command.body["project_id"],"principal_id":command.body["principal_id"],"writer_epoch":command.body["writer_epoch"],"writer_acks":[]}
            if path=="/fleet/v1/writers/release":
                body=command.body
                if set(command.request)!={"project_id"}: raise WriterError("WRITER_INVALID")
                row=self.state["assignments"][body["project_id"]]
                row.update(state="DRAINING",fence_epoch=body["writer_epoch"]+1);self._publish("voluntary_drain")
                pending=self._pending(body["project_id"])
                if not pending: row["state"]="RELEASED";self._publish("voluntary_release")
                return {"schema":"fleet.writer-fence.receipt/1","project_id":body["project_id"],"fence_epoch":body["writer_epoch"]+1,"pending_intents":pending,"writer_acks":[]}
            if path=="/fleet/v1/sources/write": return self._source(command)
            if path.startswith("/fleet/v1/worktrees/") and self.worktrees is not None: return self.worktrees.apply_command(path,command,operation_id=operation_id)
            raise WriterError("WRITER_OPERATION_UNAVAILABLE")

    def _source(self,command):
        body,request=command.body,command.request
        required={"project_id","frozen_id","source_base64"}
        if set(request)!=required or request["project_id"]!=body["project_id"] or type(request["source_base64"]) is not str or len(request["source_base64"])>4*((self.policy.max_source_bytes+2)//3): raise WriterError("WRITER_INVALID")
        try: data=base64.b64decode(request["source_base64"],validate=True)
        except Exception: raise WriterError("WRITER_INVALID") from None
        if len(data)>self.policy.max_source_bytes: raise WriterError("WRITER_CAPACITY")
        frozen=self.projects.load_frozen(request["frozen_id"])
        if frozen["project_id"]!=body["project_id"] or frozen["target"]!=body["target"] or frozen["writer"]["writer_id"]!=body["principal_id"]: raise WriterError("WRITER_FENCE_MISMATCH")
        intent=body["intent_sha256"]; source_sha=hashlib.sha256(data).hexdigest(); row=self.state["operations"].get(intent)
        if row and row["state"]=="COMMITTED": return {**clone(row["receipt"]),"idempotent_recovered":True}
        if row is None:
            if len(self.state["operations"])>=self.policy.max_operations: raise WriterError("WRITER_CAPACITY")
            self.projects.validate_frozen(frozen)
            row={"command":json.loads(command._body),"frozen_id":request["frozen_id"],"intent_sha256":intent,"state":"PREPARED","checkpoint_id":"CP-"+time.strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(6).upper(),"source_sha256":source_sha,"source_bytes":len(data),"receipt":None}
            self.state["operations"][intent]=row; self._publish("source_prepare")
        if row["source_sha256"]!=source_sha or row["source_bytes"]!=len(data): raise WriterError("WRITER_OPERATION_CONFLICT")
        session=frozen["session"]
        source=self.projects.revisions.workspace.resolve(session["workspace"],session["ea"],must_exist=True)
        source_key=digest({"intent_sha256":intent,"phase":"source_commit"})
        if source_key not in self.state["phases"]:
            if command._approval is not None: raise WriterError("WRITER_RECONCILIATION_REQUIRED")
            with self.phase_guard(command,"source_commit",intent) as fence:
                self.projects.validate_frozen(frozen)
                if self.fault: self.fault("source_write:before_effect")
                _atomic_write_bytes(source,data)
                if self.fault: self.fault("source_write:after_effect")
                self.complete_phase(fence,{"schema":"fleet.source-effect/1","source_sha256":source_sha,"source_bytes":len(data)})
        else:
            with ConcurrencyManager(self.root).mutation("fleet_source_guard",resource=session["workspace"]+":"+session["ea"],wait_seconds=0):
                if hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha: raise WriterError("WRITER_RECONCILIATION_REQUIRED")
                self.recover_phase(command,"source_commit",{"schema":"fleet.source-effect/1","source_sha256":source_sha,"source_bytes":len(data)})
        row=self.state["operations"][intent]; row["state"]="SOURCE_COMMITTED"; self._publish("source_record")
        session_key=digest({"intent_sha256":intent,"phase":"session_commit"})
        if session_key not in self.state["phases"]:
            with self.phase_guard(command,"session_commit",intent) as fence:
                if hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha: raise WriterError("WRITER_RECONCILIATION_REQUIRED")
                self.projects.revisions.create_checkpoint(session["workspace"],session["ea"],checkpoint_id=row["checkpoint_id"])
                if self.fault: self.fault("session_write:before_effect")
                updated=self.projects.sessions.update(body["project_id"],session["revision_id"],expected_revision_sha256=session["revision_sha256"],checkpoint_id=row["checkpoint_id"],operation_id="fleet-"+intent[:48])
                if self.fault: self.fault("session_write:after_effect")
                self.complete_phase(fence,{"schema":"fleet.session-effect/1","revision_id":updated["revision_id"],"revision_sha256":updated["revision_sha256"]})
        else:
            with ConcurrencyManager(self.root).mutation("fleet_source_guard",resource=session["workspace"]+":"+session["ea"],wait_seconds=0):
                updated=self.projects.sessions.get(body["project_id"])
                if updated.get("session_update_operation_id")!="fleet-"+intent[:48] or updated["source_sha256"]!=source_sha or updated["checkpoint_id"]!=row["checkpoint_id"]: raise WriterError("WRITER_RECONCILIATION_REQUIRED")
                self.recover_phase(command,"session_commit",{"schema":"fleet.session-effect/1","revision_id":updated["revision_id"],"revision_sha256":updated["revision_sha256"]})
        updated=self.projects.sessions.get(body["project_id"])
        placement=self.projects.advance_session(body["project_id"],expected_placement_revision=frozen["placement_revision"],expected_session_revision=session["revision_id"],expected_session_sha256=session["revision_sha256"],new_session_revision=updated["revision_id"],new_session_sha256=updated["revision_sha256"],operation_id="fleet-"+intent[:48])
        receipt={"schema":"fleet.source-write.receipt/1","project_id":body["project_id"],"operation_id":body["operation_id"],"intent_sha256":intent,"principal_id":body["principal_id"],"writer_epoch":body["writer_epoch"],"source_sha256":source_sha,"source_bytes":len(data),"session":placement["session"],"placement_revision":placement["placement_revision"],"writer_acks":self.writer_acks(command)}
        row=self.state["operations"][intent]; row.update(state="COMMITTED",receipt=receipt); self._publish("source_complete")
        return {**clone(receipt),"idempotent_recovered":False}

    @_safe
    def reconcile_original(self, approval):
        with self._mutex:
            self._guard(); evidence=verify_envelope(approval,self.key,DRAIN_DOMAIN)
            intent=sha(evidence.get("intent_sha256")); row=self.state["operations"].get(intent)
            if row is None: raise WriterError("WRITER_RECONCILIATION_REQUIRED")
            body=command_body(verify_envelope(row["command"],self.key,COMMAND_DOMAIN))
            self._current(body,canonical(approval))
            frozen=self.projects.load_frozen(row["frozen_id"]); session=frozen["session"]
            source=self.projects.revisions.workspace.resolve(session["workspace"],session["ea"],must_exist=True)
            with source.open("rb") as stream: data=stream.read(self.policy.max_source_bytes+1)
            if len(data)!=row["source_bytes"] or hashlib.sha256(data).hexdigest()!=row["source_sha256"]: raise WriterError("WRITER_RECONCILIATION_REQUIRED")
            request={"project_id":body["project_id"],"frozen_id":row["frozen_id"],"source_base64":base64.b64encode(data).decode("ascii")}
            wrapper={"schema":"fleet.domain-request/1","node":{"device_id":self.device_id,"route_generation":self.route_generation},"operation_id":body["operation_id"],"payload":request}
            if digest({"path":body["path"],"payload":wrapper})!=body["payload_sha256"]: raise WriterError("WRITER_OPERATION_CONFLICT")
            command=NodeCommand(self,row["command"],request,approval=approval,_seal=_SEAL)
            result=self._source(command)
            assignment=self.state["assignments"][body["project_id"]]
            pending=self._pending(body["project_id"])
            fence_ack=None
            if assignment["state"]=="DRAINING" and not pending:
                assignment["state"]="RELEASED"; self._publish("drain_reconciled")
                fence_ack={"project_id":body["project_id"],"fence_epoch":assignment["fence_epoch"],"pending_intents":[]}
            return {"schema":"fleet.writer-reconcile.receipt/1","source_receipt":result,"writer_acks":result["writer_acks"],"fence_ack":fence_ack}

    def witness(self, coordination_sha256):
        with self._mutex:
            self._guard(); sha(coordination_sha256)
            pending=sorted(set(x for project in self.state['assignments'] for x in self._pending(project)))
            assignments=[{**{key:row['assignment']['body'][key] for key in ('project_id','principal_id','principal_epoch','assignment_epoch','writer_epoch')},'state':row['state']} for row in self.state['assignments'].values()]
            receipts=[clone(row['ack']) for row in self.state['phases'].values() if row['ack'] is not None]
            return {'schema':'fleet.node-writer-witness/1','authority':'PERSISTED','coordination_sha256':coordination_sha256,'device_id':self.device_id,'route_generation':self.route_generation,'session_id':self.session_id,'pending_intents':pending,'assignments':sorted(assignments,key=canonical),'phase_receipts':sorted(receipts,key=canonical),'worktree_head':None if self.worktrees is None else self.worktrees.recovery_head()}

    def verify_domain_resolution(self,original,reconciled):
        with self._mutex:
            self._guard()
            binding=resolution_binding(original,reconciled,self.key)
            row=self.state["operations"].get(binding["intent_sha256"])
            receipt={k:v for k,v in reconciled["result"]["source_receipt"].items() if k!="idempotent_recovered"}
            if row is None or row["state"]!="COMMITTED" or row["receipt"]!=receipt: raise WriterError("WRITER_RESOLUTION_INVALID")
            return binding
