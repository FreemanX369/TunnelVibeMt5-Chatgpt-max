import hashlib
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from vibemql5.fleet.node_transport_journal import NodeTransportJournal,TransportPolicy
from vibemql5.fleet.wire import WireError,verify_request
from test_tip058b_transport import DEVICE,signed,service,tls_files

POLICY=TransportPolicy(max_records=10,max_payload_bytes=32768,wait_ms=10)

def request(key,nonce="a"*48):
    raw,headers=signed(key,{"schema":"fleet.heartbeat/1","session_id":"session1"},nonce=nonce)
    return verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)

def journal(path,key,policy=POLICY,initialize=True):
    method=NodeTransportJournal.initialize if initialize else NodeTransportJournal.open_existing
    return method(path,policy,device_id=DEVICE,public_key=key.public_key().public_bytes_raw().hex(),audience="https://localhost")

def response(proof,revision=3):
    return {"schema":"fleet.heartbeat-receipt/1","transport_request_sha256":proof.request_sha256,"control_head":{"schema":"fleet.control-head/1","revision":revision,"sha256":"b"*64}}

def pair_body():
    return {"schema":"fleet.pair/1","grant_id":"grant_"+"c"*32,"secret":"fixture-pair-secret",
        "operation_id":"pair-fixture","expected_revision":2}

def pair_request(key,body,*,nonce="a"*48,route=0):
    raw,headers=signed(key,body,nonce=nonce,route=route,path="/fleet/v1/pair")
    return verify_request("POST","/fleet/v1/pair",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)

def test_pair_replay_readonly_exact_body_and_pre_route(tmp_path):
    key=Ed25519PrivateKey.generate();body=pair_body();path=tmp_path/"transport.sqlite";j=journal(path,key)
    with pytest.raises(WireError,match="TRANSPORT_PAIR_REPLAY_INVALID"):
        j.assert_pair_replay(body,signed_route_generation=0)
    first=pair_request(key,body);j.begin(first)
    second=pair_request(key,body,nonce="b"*48);digest=j.begin(second);j.acknowledge(digest,second,response(second))
    j.close();j=journal(path,key,initialize=False)
    before=j.witness("challenge")
    j.assert_pair_replay(body,signed_route_generation=0)
    assert j.witness("challenge")==before and before["pending_count"]==1 and before["request_count"]==2
    for changed in ({**body,"grant_id":"grant_"+"d"*32},{**body,"operation_id":"other"},
                    {**body,"secret":"different"},{**body,"expected_revision":3},{**body,"extra":True}):
        with pytest.raises(WireError,match="TRANSPORT_PAIR_REPLAY_INVALID"):
            j.assert_pair_replay(changed,signed_route_generation=0)
    for route in (1,True,-1):
        with pytest.raises(WireError,match="TRANSPORT_PAIR_REPLAY_INVALID"):
            j.assert_pair_replay(body,signed_route_generation=route)
    assert j.witness("challenge")==before
    j.close()
    with pytest.raises(WireError,match="TRANSPORT_JOURNAL_INVALID"):
        journal(path,Ed25519PrivateKey.generate(),initialize=False)
    with pytest.raises(WireError,match="TRANSPORT_JOURNAL_INVALID"):
        NodeTransportJournal.open_existing(path,POLICY,device_id=DEVICE,
            public_key=key.public_key().public_bytes_raw().hex(),audience="https://other.example")

def test_pair_replay_denies_mixed_authority_or_pair_intents(tmp_path):
    key=Ed25519PrivateKey.generate();body=pair_body();j=journal(tmp_path/"transport.sqlite",key)
    j.begin(pair_request(key,body))
    j.begin(pair_request(key,{**body,"operation_id":"second"},nonce="b"*48))
    before=j.witness("challenge")
    with pytest.raises(WireError,match="TRANSPORT_PAIR_REPLAY_INVALID"):
        j.assert_pair_replay(body,signed_route_generation=0)
    assert j.witness("challenge")==before
    j.close()
    j=journal(tmp_path/"mixed.sqlite",key);j.begin(pair_request(key,body));j.begin(request(key,"b"*48))
    before=j.witness("challenge")
    with pytest.raises(WireError,match="TRANSPORT_PAIR_REPLAY_INVALID"):
        j.assert_pair_replay(body,signed_route_generation=0)
    assert j.witness("challenge")==before
    j.close()

def test_durable_intent_pending_never_timeout_clear_and_exact_ack(tmp_path):
    key=Ed25519PrivateKey.generate();proof=request(key);path=tmp_path/"transport.sqlite";j=journal(path,key)
    digest=j.begin(proof)
    assert j.witness("challenge")["pending_count"]==1
    j.close();j=journal(path,key,initialize=False)
    assert j.witness("newchallenge")["pending_count"]==1
    j.acknowledge(digest,proof,response(proof))
    witness=j.witness("challenge")
    assert witness["pending_count"]==0 and witness["latest_control_head"]["revision"]==3
    assert set(witness)=={"schema","device_id","public_key","audience","challenge","pending_count","request_count","latest_control_head","journal_sha256"}
    j.close()

def test_missing_or_replaced_journal_no_bootstrap(tmp_path):
    key=Ed25519PrivateKey.generate();path=tmp_path/"missing.sqlite"
    with pytest.raises(WireError,match="TRANSPORT_JOURNAL_MISSING"):journal(path,key,initialize=False)
    j=journal(path,key);j.close()
    with pytest.raises(WireError,match="TRANSPORT_JOURNAL_EXISTS"):journal(path,key)
    with pytest.raises(WireError,match="TRANSPORT_JOURNAL_INVALID"):journal(path,Ed25519PrivateKey.generate(),initialize=False)

def test_ack_wrongrequest_no_pending_clear(tmp_path):
    key=Ed25519PrivateKey.generate();j=journal(tmp_path/"transport.sqlite",key);proof=request(key);digest=j.begin(proof)
    wrong=response(proof);wrong["transport_request_sha256"]="c"*64
    with pytest.raises(WireError,match="TRANSPORT_ACK_INVALID"):j.acknowledge(digest,proof,wrong)
    assert j.witness("challenge")["pending_count"]==1
    j.close()

def test_journal_rejects_other_audience_before_intent(tmp_path):
    key=Ed25519PrivateKey.generate();j=journal(tmp_path/"transport.sqlite",key)
    raw,headers=signed(key,{"schema":"fleet.heartbeat/1","session_id":"session1"},origin="https://other.example")
    proof=verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://other.example",max_body_bytes=32768)
    with pytest.raises(WireError,match="TRANSPORT_JOURNAL_INVALID"):j.begin(proof)
    assert j.witness("challenge")["request_count"]==0
    j.close()

def test_no_grantsecret_in_persisted_request(tmp_path):
    key=Ed25519PrivateKey.generate();secret="secret-fixture-not-persisted"
    raw,headers=signed(key,{"grant_id":"grant_"+"a"*32,"secret":secret},route=0,path="/fleet/v1/pair")
    proof=verify_request("POST","/fleet/v1/pair",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)
    path=tmp_path/"transport.sqlite";j=journal(path,key);j.begin(proof);j.close()
    for file in tmp_path.iterdir():assert secret.encode() not in file.read_bytes()

def test_capacity_does_not_evict_pending(tmp_path):
    key=Ed25519PrivateKey.generate();j=journal(tmp_path/"transport.sqlite",key,replace(POLICY,max_records=1));j.begin(request(key))
    with pytest.raises(WireError,match="TRANSPORT_CAPACITY"):j.begin(request(key,"b"*48))
    assert j.witness("challenge")["pending_count"]==1
    j.close()

def test_duplicate_changed_nonce_conflict_and_identical_retry(tmp_path):
    key=Ed25519PrivateKey.generate();j=journal(tmp_path/"transport.sqlite",key);proof=request(key);digest=j.begin(proof)
    assert j.begin(proof)==digest
    raw,headers=signed(key,{"schema":"fleet.heartbeat/1","session_id":"other"},nonce="a"*48)
    changed=verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)
    with pytest.raises(WireError,match="TRANSPORT_INTENT_CONFLICT"):j.begin(changed)
    j.close()

def test_real_tls_intent_ack_and_lost_ack_remains_pending(service,tmp_path,monkeypatch):
    from test_tip058b_transport import enrolled
    from vibemql5.fleet.transport import NodeClient
    http,owner,*_=service;existing,_,_=enrolled(service)
    j=NodeTransportJournal.initialize(tmp_path/"outbound.sqlite",POLICY,device_id=DEVICE,
        public_key=existing.key.public_key().public_bytes_raw().hex(),audience=http.origin)
    node=NodeClient(http,existing.key,DEVICE,1,transport_journal=j)
    node.heartbeat("durable-session")
    witnessed=j.witness("challenge")
    assert witnessed["pending_count"]==0 and witnessed["latest_control_head"]["revision"]>2
    original=http.post
    def lost(*args,**kwargs):
        original(*args,**kwargs)
        raise WireError("fixture_lost_ack")
    monkeypatch.setattr(http,"post",lost)
    with pytest.raises(WireError,match="fixture_lost_ack"):node.heartbeat("durable-session")
    assert j.witness("challenge")["pending_count"]==1
    monkeypatch.setattr(http,"post",original)
    node.heartbeat("durable-session")
    assert j.witness("challenge")["pending_count"]==1
    j.close()

def test_real_tls_pair_replay_after_lost_ack_reuses_receipt_and_keeps_pending(service,tmp_path,monkeypatch):
    from vibemql5.fleet.transport import NodeClient
    http,owner,*_=service;key=Ed25519PrivateKey.generate()
    grant=owner.admin("grant",{"device_id":DEVICE,"public_key":key.public_key().public_bytes_raw().hex(),
        "operation_id":"grant-durable-pair","expected_revision":1,"expected_route_generation":None})
    body={"schema":"fleet.pair/1","grant_id":grant["receipt"]["grant_id"],"secret":grant["secret"],
        "operation_id":"pair-durable","expected_revision":2}
    path=tmp_path/"pair.sqlite"
    j=NodeTransportJournal.initialize(path,POLICY,device_id=DEVICE,
        public_key=key.public_key().public_bytes_raw().hex(),audience=http.origin)
    node=NodeClient(http,key,DEVICE,0,transport_journal=j);original=http.post;accepted=[]
    def lost(*args,**kwargs):
        accepted.append(original(*args,**kwargs))
        raise WireError("fixture_lost_pair_ack")
    monkeypatch.setattr(http,"post",lost)
    with pytest.raises(WireError,match="fixture_lost_pair_ack"):
        node.pair(**{name:body[name] for name in ("grant_id","secret","operation_id","expected_revision")})
    before=j.witness("challenge");j.close()
    j=NodeTransportJournal.open_existing(path,POLICY,device_id=DEVICE,
        public_key=key.public_key().public_bytes_raw().hex(),audience=http.origin)
    j.assert_pair_replay(body,signed_route_generation=0)
    assert j.witness("challenge")==before and before["pending_count"]==1
    monkeypatch.setattr(http,"post",original)
    node=NodeClient(http,key,DEVICE,0,transport_journal=j)
    receipt=node.pair(**{name:body[name] for name in ("grant_id","secret","operation_id","expected_revision")})
    assert receipt["idempotent_recovered"] and receipt["receipt"]==accepted[0]["receipt"]
    assert node.route_generation==1 and receipt["receipt"]["revision"]==3
    assert j.witness("challenge")["pending_count"]==1 and j.witness("challenge")["request_count"]==2
    j.assert_pair_replay(body,signed_route_generation=0)
    node.heartbeat("after-pair")
    with pytest.raises(WireError,match="TRANSPORT_PAIR_REPLAY_INVALID"):
        j.assert_pair_replay(body,signed_route_generation=0)
    assert j.witness("challenge")["pending_count"]==1
    j.close()
