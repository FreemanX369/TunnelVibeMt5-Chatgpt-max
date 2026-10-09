"""Independent durable node transport witness; lost ACKs never expire away."""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.jobs import _exclusive_file_lock
from .wire import WireError, encode_body, fields, https_origin, integer, logical_digest, text, verified


@dataclass(frozen=True)
class TransportPolicy:
    max_records: int
    max_payload_bytes: int
    wait_ms: int
    def __post_init__(self):
        integer(self.max_records, minimum=1, maximum=100000)
        integer(self.max_payload_bytes, minimum=1, maximum=1048576)
        integer(self.wait_ms, minimum=1, maximum=60000)


class NodeTransportJournal:
    def __init__(self, path, policy, device_id, public_key, audience, *, initialize):
        if type(policy) is not TransportPolicy:
            raise WireError("TRANSPORT_JOURNAL_INVALID")
        https_origin(audience)
        if type(device_id) is not str or re.fullmatch(r"dev_[0-9a-f]{32}",device_id) is None or type(public_key) is not str or re.fullmatch(r"[0-9a-f]{64}",public_key) is None:
            raise WireError("TRANSPORT_JOURNAL_INVALID")
        self.path, self.policy = Path(path).resolve(), policy
        self.identity = {"device_id": device_id, "public_key": public_key, "audience": audience}
        self._lock = _exclusive_file_lock(self.path.with_name(self.path.name + ".owner.lock"), timeout_seconds=policy.wait_ms/1000)
        self._db = None
        try:
            self._lock.__enter__()
            if initialize and self.path.exists():
                raise WireError("TRANSPORT_JOURNAL_EXISTS")
            if not initialize and not self.path.is_file():
                raise WireError("TRANSPORT_JOURNAL_MISSING")
            self._db = sqlite3.connect(self.path,timeout=policy.wait_ms/1000,isolation_level=None)
            self._db.row_factory=sqlite3.Row
            self._db.execute("PRAGMA synchronous=FULL")
            if initialize:
                self._db.execute("PRAGMA journal_mode=WAL")
                with self._db:
                    self._db.execute("BEGIN IMMEDIATE")
                    self._db.execute("PRAGMA user_version=1")
                    self._db.execute("CREATE TABLE metadata (singleton INTEGER PRIMARY KEY, schema TEXT NOT NULL, identity TEXT NOT NULL, policy TEXT NOT NULL)")
                    self._db.execute("CREATE TABLE requests (nonce_sha256 TEXT PRIMARY KEY, request_sha256 TEXT UNIQUE NOT NULL, intent TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('PENDING','ACKED')), ack TEXT)")
                    self._db.execute("INSERT INTO metadata VALUES (1,?,?,?)",("fleet.node.transport/1",json.dumps(self.identity,sort_keys=True),json.dumps(asdict(policy),sort_keys=True)))
            self._validate()
        except TimeoutError:
            self.close()
            raise WireError("TRANSPORT_JOURNAL_BUSY") from None
        except WireError:
            self.close()
            raise
        except (OSError,sqlite3.Error,ValueError):
            self.close()
            raise WireError("TRANSPORT_JOURNAL_INVALID") from None

    @classmethod
    def initialize(cls,path,policy,*,device_id,public_key,audience):
        return cls(path,policy,device_id,public_key,audience,initialize=True)
    @classmethod
    def open_existing(cls,path,policy,*,device_id,public_key,audience):
        return cls(path,policy,device_id,public_key,audience,initialize=False)
    def close(self):
        db,lock=self._db,getattr(self,"_lock",None)
        self._db=None;self._lock=None
        try:
            if db is not None:db.close()
        finally:
            if lock is not None:lock.__exit__(None,None,None)
    def _validate(self):
        if self._db is None:raise WireError("TRANSPORT_JOURNAL_CLOSED")
        try:
            if (self._db.execute("PRAGMA quick_check").fetchone()[0]!="ok" or
                    self._db.execute("PRAGMA user_version").fetchone()[0]!=1 or
                    self._db.execute("PRAGMA journal_mode").fetchone()[0].lower()!="wal" or
                    {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}!={"metadata","requests"}):raise ValueError()
            rows=self._db.execute("SELECT * FROM metadata").fetchall()
            if len(rows)!=1 or rows[0]["singleton"]!=1 or rows[0]["schema"]!="fleet.node.transport/1" or json.loads(rows[0]["identity"])!=self.identity or json.loads(rows[0]["policy"])!=asdict(self.policy):raise ValueError()
            if self._db.execute("SELECT count(*) FROM requests").fetchone()[0]>self.policy.max_records:raise ValueError()
            for row in self._db.execute("SELECT * FROM requests"):
                intent=json.loads(row["intent"])
                if logical_digest(intent)!=row["request_sha256"] or intent["nonce_sha256"]!=row["nonce_sha256"] or any(intent[k]!=self.identity[k] for k in self.identity):raise ValueError()
                if row["state"] not in {"PENDING","ACKED"} or (row["ack"] is None)!=(row["state"]=="PENDING"):raise ValueError()
                if row["ack"] is not None:self._head(json.loads(row["ack"])["control_head"])
        except (sqlite3.Error,ValueError,KeyError,TypeError):
            raise WireError("TRANSPORT_JOURNAL_INVALID") from None
    @staticmethod
    def _head(head):
        fields(head,{"schema","revision","sha256"})
        if head["schema"]!="fleet.control-head/1" or type(head["sha256"]) is not str or len(head["sha256"])!=64:
            raise WireError("TRANSPORT_ACK_INVALID")
        integer(head["revision"],minimum=1)
        try:bytes.fromhex(head["sha256"])
        except ValueError:raise WireError("TRANSPORT_ACK_INVALID") from None
    def begin(self,proof):
        self._validate()
        if (not verified(proof) or proof.device_id!=self.identity["device_id"] or proof.public_key!=self.identity["public_key"]
                or proof.audience!=self.identity["audience"]):
            raise WireError("TRANSPORT_JOURNAL_INVALID")
        intent={**self.identity,"schema":"fleet.transport-intent/1","path":proof.path,"route_generation":proof.route_generation,
            "timestamp_ms":proof.timestamp_ms,"nonce":proof.nonce,"nonce_sha256":hashlib.sha256(proof.nonce.encode("ascii")).hexdigest(),
            "wire_request_sha256":proof.request_sha256,"body_sha256":hashlib.sha256(proof._body_bytes).hexdigest()}
        digest=logical_digest(intent)
        encode_body(intent,self.policy.max_payload_bytes)
        try:
            with self._db:
                self._db.execute("BEGIN IMMEDIATE")
                prior=self._db.execute("SELECT * FROM requests WHERE nonce_sha256=?",(intent["nonce_sha256"],)).fetchone()
                if prior is not None:
                    if prior["request_sha256"]!=digest:raise WireError("TRANSPORT_INTENT_CONFLICT")
                    return digest
                if self._db.execute("SELECT count(*) FROM requests").fetchone()[0]>=self.policy.max_records:raise WireError("TRANSPORT_CAPACITY")
                self._db.execute("INSERT INTO requests VALUES (?,?,?,'PENDING',NULL)",(intent["nonce_sha256"],digest,json.dumps(intent,sort_keys=True)))
        except sqlite3.Error:raise WireError("TRANSPORT_JOURNAL_INVALID") from None
        return digest
    def acknowledge(self,intent_digest,proof,response):
        self._validate()
        if (not verified(proof) or proof.device_id!=self.identity["device_id"] or proof.public_key!=self.identity["public_key"]
                or proof.audience!=self.identity["audience"] or response.get("transport_request_sha256")!=proof.request_sha256):
            raise WireError("TRANSPORT_ACK_INVALID")
        head=response.get("control_head");self._head(head)
        ack={"schema":"fleet.transport-ack/1","control_head":head,"response_sha256":logical_digest(response),"wire_request_sha256":proof.request_sha256}
        encode_body(ack,self.policy.max_payload_bytes)
        try:
            with self._db:
                self._db.execute("BEGIN IMMEDIATE")
                row=self._db.execute("SELECT * FROM requests WHERE request_sha256=?",(intent_digest,)).fetchone()
                if row is None or json.loads(row["intent"])["wire_request_sha256"]!=proof.request_sha256:raise WireError("TRANSPORT_ACK_INVALID")
                serialized=json.dumps(ack,sort_keys=True)
                if row["state"]=="ACKED" and row["ack"]!=serialized:raise WireError("TRANSPORT_ACK_CONFLICT")
                self._db.execute("UPDATE requests SET state='ACKED',ack=? WHERE request_sha256=?",(serialized,intent_digest))
        except sqlite3.Error:raise WireError("TRANSPORT_JOURNAL_INVALID") from None
        return {"schema":"fleet.transport-ack-receipt/1","intent_sha256":intent_digest,"control_head":head}
    def assert_pair_replay(self,body,*,signed_route_generation):
        """Permit only an exact interrupted bootstrap; retain every old intent."""
        self._validate()
        try:
            fields(body,{"schema","grant_id","secret","operation_id","expected_revision"})
            if body["schema"]!="fleet.pair/1":raise WireError("TRANSPORT_PAIR_REPLAY_INVALID")
            integer(signed_route_generation)
            integer(body["expected_revision"],minimum=1)
            for key in ("grant_id","secret","operation_id"):text(body[key],self.policy.max_payload_bytes)
            body_sha=hashlib.sha256(encode_body(body,self.policy.max_payload_bytes)).hexdigest()
            rows=self._db.execute("SELECT intent FROM requests").fetchall()
            if not rows:raise WireError("TRANSPORT_PAIR_REPLAY_INVALID")
            for row in rows:
                intent=json.loads(row["intent"])
                if (intent.get("path")!="/fleet/v1/pair" or
                        type(intent.get("route_generation")) is not int or
                        intent["route_generation"]!=signed_route_generation or
                        intent.get("body_sha256")!=body_sha):
                    raise WireError("TRANSPORT_PAIR_REPLAY_INVALID")
        except WireError:
            raise WireError("TRANSPORT_PAIR_REPLAY_INVALID") from None
        except (sqlite3.Error,ValueError,KeyError,TypeError):
            raise WireError("TRANSPORT_JOURNAL_INVALID") from None
    def witness(self,challenge):
        self._validate();text(challenge,128)
        rows=[dict(row) for row in self._db.execute("SELECT * FROM requests ORDER BY nonce_sha256")]
        # Recovery lane ACKs prove only the fenced recovery exchange. They are
        # not a newer ordinary control ledger and cannot erase the live anchor.
        heads=[json.loads(row["ack"])["control_head"] for row in rows if row["ack"] is not None and json.loads(row["intent"])["path"]!="/fleet/v1/reconcile"]
        maximum=max((head["revision"] for head in heads),default=None)
        newest=[head for head in heads if head["revision"]==maximum]
        if len({head["sha256"] for head in newest})>1:raise WireError("TRANSPORT_ACK_CONFLICT")
        return {"schema":"fleet.transport-witness/1",**self.identity,"challenge":challenge,
            "pending_count":sum(row["state"]=="PENDING" for row in rows),"request_count":len(rows),
            "latest_control_head":newest[0] if newest else None,"journal_sha256":logical_digest(rows)}
