"""Signed coordinated-checkpoint fixtures; no real node/MT5 qualification."""
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from vibemql5.fleet.gateway_control import GatewayControlStore, GatewayControlError, Policy
from vibemql5.fleet.job_journal import GatewayJobJournal, NodeJobJournal, canonical
from vibemql5.fleet.restore_coordination import RestoreCoordinator, RestorePolicy, RestoreError, DOMAIN
from vibemql5.fleet.wire import encode_body, sign_request, verify_request

DEVICE = "dev_" + "a" * 32
AUDIENCE = "https://fixture.invalid"


@pytest.fixture
def recovery(tmp_path):
    key, operator = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    policy = Policy(singleton_wait_ms=25, sqlite_busy_timeout_ms=25, grant_ttl_ms=1000,
        clock_skew_ms=100, nonce_retention_ms=300, grant_secret_bytes=32,
        max_devices=8, max_grants=16, max_nonces=16, max_operations=32,
        max_nonce_bytes=128, max_operation_id_bytes=128)
    jp = dict(max_records=32, max_payload_bytes=262144, wait_ms=25)
    original = tmp_path / "original"
    original.mkdir()
    with GatewayControlStore.initialize(original / "control.db", policy=policy) as store:
        grant = store.issue_grant(DEVICE, key.public_key().public_bytes_raw().hex(),
            expected_route_generation=None, expected_revision=1, operation_id="admin:grant", now_ms=1000)
        store.consume_grant(grant["receipt"]["grant_id"], grant["secret"], DEVICE,
            key.public_key().public_bytes_raw().hex(), expected_revision=2,
            operation_id="admin:pair", now_ms=1001)
        head = store.control_head()
        store.backup(original / "backup-control.db")
    with GatewayJobJournal(original / "jobs.db", initialize=True, **jp) as jobs:
        mapping = jobs.mapping_sha256()
        jobs.backup(original / "backup-jobs.db")
    restored = tmp_path / "restored"
    restored.mkdir()
    control = GatewayControlStore.restore(original / "backup-control.db", restored / "control.db", policy=policy)
    jobs = GatewayJobJournal.restore_backup(original / "backup-jobs.db", restored / "jobs.db",
        devices=[DEVICE], export_generation=1, **jp)
    node = NodeJobJournal(tmp_path / "node.db", initialize=True, **jp)
    retained = tmp_path / "retained"
    retained.mkdir()
    checkpoint = retained / "checkpoint.json"
    facts = {"schema": "fleet.quiescent-checkpoint/1", "audience": AUDIENCE,
        "control_head": head, "control_wall_ms": 1001,
        "devices": [{"device_id": DEVICE, "public_key": key.public_key().public_bytes_raw().hex(),
                     "route_generation": 1, "state": "ACTIVE", "registry_sha256": "c" * 64,
                     "session_id": "fixture-session"}], "job_export_generation": 1,
        "job_mapping_sha256": mapping}
    checkpoint.write_bytes(canonical(facts))
    body = {"schema": "fleet.restore.operator-approval/1", "audience": AUDIENCE,
        "challenge": jobs.restore_state()["challenge"], "issued_ms": 1001, "expires_ms": 5000,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
    approval = {"approval": body, "signature": operator.sign(DOMAIN + canonical(body)).hex()}
    rp = RestorePolicy(max_devices=8, max_payload_bytes=1048576, max_nonces=32, clock_skew_ms=100, wait_ms=25)
    args = dict(audience=AUDIENCE, operator_public_key=operator.public_key().public_bytes_raw(), policy=rp, now_ms=1002)
    value = RestoreCoordinator(restored / "coordinator.json", control, jobs, initialize=True,
        approval=approval, checkpoint_path=checkpoint, **args)
    yield dict(coordinator=value, control=control, jobs=jobs, node=node, key=key, head=head,
               args=args, approval=approval, checkpoint=checkpoint, operator=operator)
    value.close(); node.close(); jobs.close(); control.close()


def proof(r, *, nonce="1" * 32, value=None):
    coordinator = r["coordinator"]
    scope = coordinator.scope()
    if value is None:
        job_scope = {**r["jobs"].restore_state(), "coordination_sha256": coordinator.record["coordination_sha256"], "joint_scope": scope}
        value = {"schema": "fleet.reconcile/1", "coordination_sha256": coordinator.record["coordination_sha256"],
            "registry_sha256": "c" * 64, "session_id": "fixture-session",
            "transport_witness": {"schema": "fleet.transport-witness/1", "device_id": DEVICE,
                "public_key": r["key"].public_key().public_bytes_raw().hex(), "audience": AUDIENCE,
                "challenge": scope["challenge"], "pending_count": 0, "request_count": 1,
                "latest_control_head": r["head"], "journal_sha256": "d" * 64},
            "job_witness": r["node"].witness(job_scope, device_id=DEVICE, route_generation=1,
                session_id="fixture-session", private_key=r["key"])}
    raw = encode_body(value, 1048576)
    headers = sign_request(r["key"], device_id=DEVICE, route_generation=1, timestamp_ms=1002,
                           nonce=nonce, path="/fleet/v1/reconcile", body=raw, audience=AUDIENCE)
    return verify_request("POST", "/fleet/v1/reconcile", headers.items(), raw,
                          audience=AUDIENCE, max_body_bytes=1048576)


def test_complete_signed_checkpoint_restores_both_and_remains_ready_after_new_admission(recovery):
    r = recovery
    with pytest.raises(GatewayControlError):
        r["control"].reserve_nonce(DEVICE, route_generation=1, nonce="ordinary-before",
            request_sha256="e" * 64, timestamp_ms=1002, now_ms=1002)
    r["coordinator"].accept_witness(proof(r), now_ms=1002)
    assert not r["coordinator"].status()["ready"]
    assert r["coordinator"].finalize(now_ms=1003)["ready"]
    r["control"].reserve_nonce(DEVICE, route_generation=1, nonce="ordinary-after",
        request_sha256="e" * 64, timestamp_ms=1003, now_ms=1003)
    assert r["coordinator"].status()["ready"]
    path = r["coordinator"].path
    r["coordinator"].close()
    reopened = RestoreCoordinator(path, r["control"], r["jobs"], **r["args"])
    assert reopened.status()["ready"]
    reopened.close()


@pytest.mark.parametrize("kind", ["newer", "missing", "pending", "registry", "route", "challenge"])
def test_uncertain_or_changed_witness_cannot_clear_recovery(recovery, kind):
    r = recovery
    packet = proof(r).body
    if kind == "newer": packet["transport_witness"]["latest_control_head"]["revision"] += 1
    elif kind == "missing": packet["transport_witness"]["latest_control_head"] = None
    elif kind == "pending": packet["transport_witness"]["pending_count"] = 1
    elif kind == "registry": packet["registry_sha256"] = "e" * 64
    elif kind == "route": packet["job_witness"]["body"]["route_generation"] = 2
    else: packet["transport_witness"]["challenge"] = "f" * 32
    with pytest.raises(Exception): r["coordinator"].accept_witness(proof(r, value=packet), now_ms=1002)
    assert not r["coordinator"].status()["ready"]
    assert r["control"].snapshot()["status"] == "RECONCILIATION_REQUIRED"


def test_transport_replay_denied_and_full_signed_bundle_reverified_on_reopen(recovery):
    r = recovery
    p = proof(r)
    r["coordinator"].accept_witness(p, now_ms=1002)
    with pytest.raises(RestoreError, match="RESTORE_REPLAY"):
        r["coordinator"].accept_witness(p, now_ms=1002)
    path = r["coordinator"].path
    r["coordinator"].close()
    value = json.loads(path.read_bytes())
    value["witnesses"][DEVICE]["signed_envelope"]["header_pairs"][-1][1] = "0" * 128
    from vibemql5.fleet.job_journal import digest
    value.pop("record_sha256")
    value["record_sha256"] = digest(value)
    path.write_bytes(canonical(value))
    with pytest.raises(Exception): RestoreCoordinator(path, r["control"], r["jobs"], **r["args"])


@pytest.mark.parametrize("stage", ["control_commit:before_commit", "control_commit:after_commit",
    "job_finalized:before_commit", "job_finalized:after_commit", "control_ready:before_commit", "control_ready:after_commit"])
def test_phase_crash_reopen_is_fenced_or_complete_and_resume_exact_scope(recovery, stage):
    r = recovery
    r["coordinator"].accept_witness(proof(r), now_ms=1002)
    def fault(point):
        if point == stage:
            raise OSError("secret diagnostic must never be a public receipt")
    r["coordinator"].fault = fault
    with pytest.raises(Exception): r["coordinator"].finalize(now_ms=1003)
    path = r["coordinator"].path
    r["coordinator"].close()
    reopened = RestoreCoordinator(path, r["control"], r["jobs"], **r["args"])
    assert reopened.finalize(now_ms=1003)["ready"]
    reopened.close()


@pytest.mark.parametrize('stage',['control_commit:after_commit','job_finalized:after_commit'])
def test_expired_pending_approval_requires_same_scope_signed_reapproval(recovery,stage):
    r=recovery;c=r['coordinator'];c.accept_witness(proof(r),now_ms=1002)
    def fault(point):
        if point==stage:raise OSError('interrupted')
    c.fault=fault
    with pytest.raises(RestoreError):c.finalize(now_ms=1003)
    path=c.path;c.close()
    args={**r['args'],'now_ms':6000}
    with pytest.raises(RestoreError,match='RESTORE_OPERATOR_APPROVAL_INVALID'):
        RestoreCoordinator(path,r['control'],r['jobs'],**args)
    body={**r['approval']['approval'],'issued_ms':6000,'expires_ms':9000}
    envelope={'approval':body,'signature':r['operator'].sign(DOMAIN+canonical(body)).hex()}
    resumed=RestoreCoordinator(path,r['control'],r['jobs'],reapproval=envelope,**args)
    assert resumed.record['approval_history'][0]['approval']==r['approval']
    assert resumed.finalize(now_ms=6001)['ready']
    assert resumed.record['scope']==json.loads(path.read_bytes())['scope']
    resumed.close()


@pytest.mark.parametrize('kind',['challenge','checkpoint','key'])
def test_reapproval_cannot_change_scope_or_trusted_key(recovery,kind):
    r=recovery;c=r['coordinator'];path=c.path;c.close()
    body={**r['approval']['approval'],'issued_ms':6000,'expires_ms':9000}
    if kind=='challenge':body['challenge']='f'*32
    if kind=='checkpoint':body['checkpoint_sha256']='e'*64
    signer=Ed25519PrivateKey.generate() if kind=='key' else r['operator']
    envelope={'approval':body,'signature':signer.sign(DOMAIN+canonical(body)).hex()}
    with pytest.raises(RestoreError,match='RESTORE_OPERATOR_APPROVAL_INVALID'):
        RestoreCoordinator(path,r['control'],r['jobs'],reapproval=envelope,**{**r['args'],'now_ms':6000})
    assert r['control'].snapshot()['status']=='RECONCILIATION_REQUIRED'


def test_unknown_nested_job_field_is_denied_before_durable_envelope(recovery):
    r=recovery;value=proof(r).body
    value['job_witness']['body']['secret']='must-not-persist'
    body=value['job_witness']['body']
    value['job_witness']['signature']=r['key'].sign(b'fleet.node-journal-witness/1\n'+canonical(body)).hex()
    before=r['coordinator'].path.read_bytes()
    with pytest.raises(Exception):r['coordinator'].accept_witness(proof(r,value=value),now_ms=1002)
    assert r['coordinator'].path.read_bytes()==before
    assert b'must-not-persist' not in before
