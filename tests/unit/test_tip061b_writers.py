import base64
import copy
import hashlib
import json

import pytest
from fleet_writer_fixture import writer_fixture, project_node, tls_files
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.fleet.principals import PrincipalError
from vibemql5.fleet.writers import WriterError,NodePrincipalRuntime
from vibemql5.fleet.wire import WireError


def source_command(f,op='write',data=b'void OnTick(){ /* changed */ }\n'):
    session=f['session']
    frozen=f['projects'].freeze('P','frozen-'+op,writer_id=f['principal'],target=f['assignment']['body']['target'],expected_placement_revision=1,expected_session_revision=session['revision_id'],expected_session_sha256=session['revision_sha256'],operation_id='freeze-'+op)
    rec=f['admit']('/fleet/v1/sources/write',{'project_id':'P','frozen_id':frozen['frozen_id'],'source_base64':base64.b64encode(data).decode()},op)
    return rec,frozen,data


def test_real_https_verified_source_two_commits_and_placement(writer_fixture):
    f=writer_fixture;rec,frozen,data=source_command(f)
    receipt=f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    assert f['source'].read_bytes()==data
    assert receipt['session']['revision_id']=='REV-000002'
    assert receipt['placement_revision']==2
    assert len(receipt['writer_acks'])==2
    assert {a['phase'] for a in receipt['writer_acks']}=={'source_commit','session_commit'}
    assert f['projects'].resume(frozen['frozen_id'])['status']=='FLEET_SESSION_CONFLICT'
    nextfreeze=f['projects'].freeze('P','new-freeze',writer_id=f['principal'],expected_placement_revision=2,expected_session_revision=receipt['session']['revision_id'],expected_session_sha256=receipt['session']['revision_sha256'],operation_id='new-freeze')
    assert nextfreeze['session']['source_sha256']==hashlib.sha256(data).hexdigest()
    assert f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')['idempotent_recovered']
    assert f['projects'].sessions.get('P')['revision_id']=='REV-000002'


def test_labels_and_changed_payload_do_not_authenticate(writer_fixture):
    f=writer_fixture;rec,_,_=source_command(f)
    for payload in ({'agent_id':f['principal']},True,{'verified':True},copy.deepcopy(rec['payload'])):
        if isinstance(payload,dict) and 'request' in payload: payload['request']['payload']['source_base64']=base64.b64encode(b'attack').decode()
        with pytest.raises((WriterError,PrincipalError)):
            f['runtime'].apply_command('/fleet/v1/sources/write',payload,operation_id='write')
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


def test_native_writer_shared_mutation_exclusion(writer_fixture):
    f=writer_fixture;rec,_,_=source_command(f)
    with ConcurrencyManager(f['root']).mutation('fleet_source_guard',resource='demo:Experts/DemoEA.mq5',wait_seconds=0):
        with pytest.raises(Exception): f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


@pytest.mark.parametrize('point',['source_write:after_effect','session_write:after_effect'])
def test_crash_reopen_exact_original_effect_recovery(writer_fixture,point):
    f=writer_fixture;rec,_,data=source_command(f)
    def fail(stage):
        if stage==point: raise OSError('secret source/path must not be diagnosed')
    runtime=f['runtime'];runtime.fault=fail
    with pytest.raises(WriterError,match="WRITER_OUTCOME_UNKNOWN"):runtime.apply_command(rec['path'],rec['payload'],operation_id='write')
    runtime.close()
    reopened=NodePrincipalRuntime(f['root'],gateway_public_key=runtime.key,audience=runtime.audience,device_id=runtime.device_id,route_generation=1,session_id=runtime.session_id,policy=runtime.policy)
    f['runtime']=reopened;reopened.bind_control_transport(f['node'])
    result=reopened.apply_command(rec['path'],rec['payload'],operation_id='write')
    assert f['source'].read_bytes()==data
    assert result['session']['revision_id']=='REV-000002'
    assert len(list((f['root']/'state'/'project-sessions'/'P'/'revisions').glob('REV-*.json')))==2
    reopened.close()


def test_gateway_revocation_before_commit_and_drain_retains_incomplete(writer_fixture):
    f=writer_fixture;rec,_,_=source_command(f)
    f['runtime'].verify_command(rec['path'],rec['payload'],'write')
    response=f['owner'].domain_request('/fleet/v1/principals/revoke',{'operation_id':'revoke','principal_id':f['principal']})
    with pytest.raises(WireError):f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    fence=response['fences'][0]
    result=f['runtime'].drain_fence(fence)
    assert result['pending_intents'] # PREPARED original write remains blocked for recovery
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


def test_closed_runtime_cannot_write(writer_fixture):
    f=writer_fixture;rec,_,_=source_command(f);f['runtime'].close()
    with pytest.raises(WriterError,match='WRITER_CLOSED'):f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')


@pytest.mark.parametrize('point',['source_record:after_commit','session_write:after_effect'])
def test_revoked_after_source_only_exact_owner_drain_completes_session(writer_fixture,point):
    import time
    f=writer_fixture;rec,_,data=source_command(f)
    def fail(stage):
        if stage==point: raise OSError('interrupt between commits')
    f['runtime'].fault=fail
    with pytest.raises(WriterError):f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    f['runtime'].fault=None
    expected='REV-000001' if point=='source_record:after_commit' else 'REV-000002'
    assert f['source'].read_bytes()==data and f['projects'].sessions.get('P')['revision_id']==expected
    revoked=f['owner'].domain_request('/fleet/v1/principals/revoke',{'operation_id':'revoke','principal_id':f['principal']})
    assert f['runtime'].drain_fence(revoked['fences'][0])['pending_intents']
    intent=rec['payload']['principal_evidence']['body']['intent_sha256']
    response=f['owner'].domain_request('/fleet/v1/principals/reconcile',{'operation_id':'reconcile','original_operation_id':'write','principal_id':f['principal'],'project_id':'P','intent_sha256':intent,'expires_ms':int(time.time()*1000)+5000})
    result=f['runtime'].apply_command('/fleet/v1/writers/reconcile',{'approval':response['approval']},operation_id='reconcile')
    assert result['source_receipt']['session']['revision_id']=='REV-000002'
    assert f['source'].read_bytes()==data
    assert result['fence_ack']['pending_intents']==[]
    assert f['runtime'].state['assignments']['P']['state']=='RELEASED'
    assert len(result['writer_acks'])==2


def test_unknown_original_bytes_cannot_drain(writer_fixture):
    import time
    f=writer_fixture;rec,_,_=source_command(f)
    def fail(stage):
        if stage=='source_write:after_effect': raise OSError('interrupt')
    f['runtime'].fault=fail
    with pytest.raises(WriterError,match="WRITER_OUTCOME_UNKNOWN"):f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    f['runtime'].fault=None
    revoke=f['owner'].domain_request('/fleet/v1/principals/revoke',{'operation_id':'revoke','principal_id':f['principal']})
    assert f['runtime'].drain_fence(revoke['fences'][0])['pending_intents']
    f['source'].write_bytes(b'unknown later writer')
    intent=rec['payload']['principal_evidence']['body']['intent_sha256']
    approve=f['owner'].domain_request('/fleet/v1/principals/reconcile',{'operation_id':'rec','original_operation_id':'write','principal_id':f['principal'],'project_id':'P','intent_sha256':intent,'expires_ms':int(time.time()*1000)+5000})
    with pytest.raises(WriterError,match='WRITER_RECONCILIATION_REQUIRED'):
        f['runtime'].reconcile_original(approve['approval'])
    assert f['runtime'].state['assignments']['P']['state']=='DRAINING'
    assert f['projects'].sessions.get('P')['revision_id']=='REV-000001'


def test_real_tls_principal_voluntary_release_replay_and_new_source_denial(writer_fixture):
    from vibemql5.fleet.domain import DomainJournal,DomainPolicy,NodeDomainDispatcher
    from vibemql5.fleet.job_journal import NodeJobJournal
    f=writer_fixture
    rec=f['admit']('/fleet/v1/writers/release',{'project_id':'P'},'release')
    assert f['admit']('/fleet/v1/writers/release',{'project_id':'P'},'release')==rec
    command=f['node'].poll('node-session',4)['commands'][0]
    dp=DomainPolicy(max_records=20,max_payload_bytes=32768,wait_ms=50,max_commands=4,start_authorization_ms=2000)
    journal=DomainJournal(f['root']/'local-domain.db',policy=dp,role='NODE',initialize=True)
    native=NodeJobJournal(f['root']/'local-native.db',initialize=True,max_records=20,max_payload_bytes=32768,wait_ms=50)
    dispatcher=NodeDomainDispatcher(f['root'],journal,native,None,principal_runtime=f['runtime'])
    try:
        response=dispatcher.dispatch(command,f['node'],'node-session')
        assert not response['recovered']
        row=journal.get(command['command_id'])
        assert row['result']['schema']=='fleet.writer-fence.receipt/1' and row['result']['pending_intents']==[]
        again=f['node'].domain_result(dispatcher._domain_result(row))
        assert again['recovered']
        with pytest.raises(WireError):f['admit']('/fleet/v1/sources/write',{'project_id':'P','frozen_id':'old','source_base64':''},'later-write')
        assert f['runtime'].state['assignments']['P']['state']=='RELEASED'
    finally:dispatcher.close();journal.close();native.close()


def test_source_cas_drift_denies_before_any_phase_effect(writer_fixture):
    from vibemql5.fleet.project_targets import FleetProjectError
    f=writer_fixture;rec,_,_=source_command(f)
    f['source'].write_bytes(b'changed independently after freeze')
    with pytest.raises(FleetProjectError,match='FLEET_SOURCE_CHANGED'):
        f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    assert f['source'].read_bytes()==b'changed independently after freeze'
    assert f['runtime'].state['phases']=={}
    assert f['projects'].sessions.get('P')['revision_id']=='REV-000001'


def test_issued_uncertain_session_without_commit_stays_fenced_on_owner_drain(writer_fixture):
    import time
    f=writer_fixture;rec,_,data=source_command(f)
    def fail(stage):
        if stage=='session_write:before_effect': raise OSError('old session worker interrupted')
    f['runtime'].fault=fail
    with pytest.raises(WriterError,match='WRITER_OUTCOME_UNKNOWN'):
        f['runtime'].apply_command(rec['path'],rec['payload'],operation_id='write')
    f['runtime'].fault=None
    assert f['source'].read_bytes()==data
    assert f['projects'].sessions.get('P')['revision_id']=='REV-000001'
    session_phases=[p for p in f['runtime'].state['phases'].values() if p['grant']['body']['phase']=='session_commit']
    assert len(session_phases)==1 and session_phases[0]['state']=='UNKNOWN'
    old_phase=copy.deepcopy(session_phases[0])
    revoked=f['owner'].domain_request('/fleet/v1/principals/revoke',{'operation_id':'revoke','principal_id':f['principal']})
    assert f['runtime'].drain_fence(revoked['fences'][0])['pending_intents']
    intent=rec['payload']['principal_evidence']['body']['intent_sha256']
    approved=f['owner'].domain_request('/fleet/v1/principals/reconcile',{'operation_id':'reconcile','original_operation_id':'write','principal_id':f['principal'],'project_id':'P','intent_sha256':intent,'expires_ms':int(time.time()*1000)+5000})
    with pytest.raises(WriterError,match='WRITER_RECONCILIATION_REQUIRED'):
        f['runtime'].reconcile_original(approved['approval'])
    assert f['runtime'].state['assignments']['P']['state']=='DRAINING'
    assert f['projects'].sessions.get('P')['revision_id']=='REV-000001'
    assert f['source'].read_bytes()==data
    assert session_phases[0]==old_phase
