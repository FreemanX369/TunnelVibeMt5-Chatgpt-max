import copy
import hashlib
import json
import threading
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fleet_writer_fixture import principal_policy, writer_fixture, project_node, tls_files
from vibemql5.fleet.principals import GatewayPrincipalAuthority, PrincipalError, PrincipalPolicy, PATHS, sign_principal_request
from vibemql5.fleet.job_journal import canonical,digest
from vibemql5.fleet.wire import WireError,encode_body


@pytest.fixture
def authority(tmp_path):
    key=Ed25519PrivateKey.generate();client=Ed25519PrivateKey.generate()
    a=GatewayPrincipalAuthority(tmp_path/'authority.json',signing_key=key,audience='https://localhost',policy=principal_policy(),initialize=True)
    issued=a.owner_request('/fleet/v1/principals/issue',{'operation_id':'issue','client_public_key':client.public_key().public_bytes_raw().hex(),'installation_id':'fixture','session_id':'s','expires_ms':2000,'scopes':sorted(PATHS)},now_ms=1000)
    yield a,key,client,issued
    a.close()


def test_closed_and_wrong_thread_do_not_bypass_singleton(authority):
    a,key,_,_=authority;errors=[]
    def run():
        try:a.control_head()
        except PrincipalError as error:errors.append(error.code)
    t=threading.Thread(target=run);t.start();t.join()
    assert errors==['PRINCIPAL_WRONG_THREAD']
    a.close()
    for fn in (a.control_head,lambda:a.owner_request('/fleet/v1/principals/revoke',{'operation_id':'r','principal_id':'p'},now_ms=1001)):
        with pytest.raises(PrincipalError,match='PRINCIPAL_CLOSED'):fn()
    reopened=GatewayPrincipalAuthority(a.path,signing_key=key,audience=a.audience,policy=a.policy)
    reopened.close()


@pytest.mark.parametrize('field',['max_principals','max_assignments','max_operations','max_nonces','max_payload_bytes','clock_skew_ms','phase_ttl_ms','wait_ms'])
def test_policy_rejects_boolean_and_unbounded_allocations(field):
    for value in (True,10**50):
        with pytest.raises(PrincipalError):replace(principal_policy(),**{field:value})


@pytest.mark.parametrize('mutation',['extra','credential','assignment','operation','nonce'])
def test_corrupt_nested_state_is_not_accepted(authority,mutation):
    a,key,_,issued=authority;a.close()
    value=json.loads(a.path.read_bytes());value.pop('record_sha256')
    if mutation=='extra':value['arbitrary_callback']=True
    elif mutation=='credential':value['principals'][issued['principal_id']]['caller_verified']=True
    elif mutation=='assignment':value['assignments']['P']={'state':'ACTIVE','assignment':{},'fence_acked':False}
    elif mutation=='operation':value['operations']['issue']['receipt']['secret']='forbidden'
    else:value['nonces']['a'*64]={'request_sha256':'b'*64,'timestamp_ms':True}
    value['record_sha256']=digest(value);a.path.write_bytes(canonical(value))
    with pytest.raises(PrincipalError):GatewayPrincipalAuthority(a.path,signing_key=key,audience=a.audience,policy=a.policy)


def test_denied_expiry_observation_is_durable_clock_high_water(authority):
    a,key,_,issued=authority
    with pytest.raises(PrincipalError,match='PRINCIPAL_EXPIRED'):
        a.owner_request('/fleet/v1/principals/assign',{'operation_id':'assign','principal_id':issued['principal_id'],'project_id':'P','target':{'schema':'fleet.target/1','device_id':'dev_'+'a'*32,'terminal_id':'term_'+'b'*32,'route_generation':1,'terminal_generation':1},'writer_epoch':1},now_ms=2000)
    a.close();a=GatewayPrincipalAuthority(a.path,signing_key=key,audience=a.audience,policy=a.policy)
    with pytest.raises(PrincipalError,match='PRINCIPAL_CLOCK_ROLLBACK'):
        a.owner_request('/fleet/v1/principals/revoke',{'operation_id':'r','principal_id':issued['principal_id']},now_ms=1999)
    a.close()


def test_real_https_node_cannot_invent_unadmitted_writer_operation(writer_fixture):
    f=writer_fixture;b=f['assignment']['body']
    with pytest.raises(WireError):
        f['node'].writers_authorize(session_id='node-session',operation_id='invented',project_id='P',target=b['target'],principal_id=f['principal'],principal_epoch=1,assignment_epoch=1,writer_epoch=1,phase='source_commit',intent_sha256='a'*64,challenge='newchallenge')
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


def test_actual_client_proof_logical_replay_is_stable_and_changed_request_conflicts(writer_fixture):
    f=writer_fixture;path='/fleet/v1/writers/acquire';payload={'project_id':'P'}
    first=f['admit'](path,payload,'same')
    assert f['admit'](path,payload,'same')==first
    with pytest.raises(WireError):f['admit'](path,{'project_id':'P','extra':'different'},'same')
    assert f['runtime'].apply_command(first['path'],first['payload'],operation_id='same')['principal_id']==f['principal']
