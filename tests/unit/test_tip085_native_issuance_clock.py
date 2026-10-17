"""Native issuance clock regressions using actual production classes and real clocks.

The parent-only latency counter remains in the external qualification evidence.
Deliberately invalid clock inputs are confined to negative guard tests.
"""
from pathlib import Path
import json,sys,time
import pytest
import test_tip064_integration as integration
from test_tip064_integration import project_node,tls_files
from vibemql5.fleet import job_journal as job, domain, transport
original_job = job
from vibemql5.fleet.native_authorization import GatewayNativeSigner
from long_native_fixture_observations import LongFixtureNativeObservations

_evidence_dir = None

@pytest.fixture(autouse=True)
def evidence_directory(tmp_path, monkeypatch):
    # Each test owns its evidence, including independent pytest invocations.
    monkeypatch.setattr(sys.modules[__name__], "_evidence_dir", tmp_path)

def record(name, data):
    (_evidence_dir / (name + ".json")).write_text(json.dumps(data, indent=2) + "\n")

@pytest.fixture
def stats():
    return {'signs':[],'gateway_clocks':[],'native_clocks':[],'verify_rows':[],'verify_errors':[],
        'ack_rows':[],'commit_rows':[],'holds':[],'delegates':0,'observers':[],'controllers':[],'resources':[],
        'authorization_active':False,'gateway_hook_installed':False}

@pytest.fixture
def composed_service(tmp_path,tls_files,request,monkeypatch,stats):
    config=request.param
    journal=integration.GatewayJobJournal
    authorize=journal.authorize_start
    def observed_authorize(self,*args,**kwargs):
        stats['delegates']+=1
        if not stats['gateway_hook_installed']:
            original_hit=self._hit
            def observed_hit(phase):
                active=stats['authorization_active']
                row={'stage':phase,'delegate_entry_monotonic':time.monotonic()}
                try:return original_hit(phase)
                finally:
                    row['delegate_return_monotonic']=time.monotonic()
                    if active and phase in ('before_commit','after_commit'):
                        row['delegate_once']=True;stats['commit_rows'].append(row)
            monkeypatch.setattr(self,'_hit',observed_hit)
            stats['gateway_hook_installed']=True
        stats['authorization_active']=True
        try:
            if config.get('hold_before') and kwargs['phase']=='reserve' and not stats['holds']:
                assert not stats['signs']
                before=time.monotonic()
                while time.monotonic()-before < 1.2:
                    time.sleep(max(0,1.2-(time.monotonic()-before)))
                stats['holds'].append({'kind':'BEFORE_SIGN','seconds':time.monotonic()-before,'signed_before_hold':0})
            return authorize(self,*args,**kwargs)
        finally:stats['authorization_active']=False
    monkeypatch.setattr(journal,'authorize_start',observed_authorize)
    signer_issue=GatewayNativeSigner.issue
    def observed_issue(self,**kwargs):
        before=time.monotonic();signed=signer_issue(self,**kwargs)
        stats['signs'].append({'issued_ms':signed['body']['issued_ms'],'expires_ms':signed['body']['expires_ms'],
            'phase':signed['body']['phase'],'event':signed['body']['event'],'sign_start_monotonic':before,'sign_return_monotonic':time.monotonic()})
        if config.get('hold_after') and len(stats['signs'])==1:
            began=time.monotonic()
            while time.monotonic()-began < 1.05:
                time.sleep(max(0,1.05-(time.monotonic()-began)))
            stats['holds'].append({'kind':'AFTER_ORIGINAL_SIGN','seconds':time.monotonic()-began})
        return signed
    monkeypatch.setattr(GatewayNativeSigner,'issue',observed_issue)
    controller=integration.GatewayController
    init=controller.__init__
    def observed_init(self,*args,**kwargs):
        init(self,*args,**kwargs);stats['controllers'].append(self)
        clock=self._times
        def observed_times():
            value=clock()
            stats['gateway_clocks'].append({'wall_ms':value[0],'monotonic_ms':value[1],'delegate_once':True})
            return value
        monkeypatch.setattr(self,'_times',observed_times)
    monkeypatch.setattr(controller,'__init__',observed_init)
    native_init=LongFixtureNativeObservations.__init__
    def observed_native_init(self):native_init(self);stats['observers'].append(self)
    monkeypatch.setattr(LongFixtureNativeObservations,'__init__',observed_native_init)
    make_runtime=integration.runtime
    def runtime(*args,**kwargs):
        result=make_runtime(*args,**kwargs)
        stats['resources'].append(result)
        verifier=result[3].authorization_verifier
        verify,clock=verifier.verify,verifier.clock
        def observed_clock():
            value=clock();stats['native_clocks'].append(value);return value
        def observed_verify(signed,**binding):
            began=time.monotonic()
            row={'phase':binding['phase'],'event':binding['event'],'issued_ms':signed['body']['issued_ms'],'expires_ms':signed['body']['expires_ms']}
            try:
                value=verify(signed,**binding);row['outcome']='RETURNED';return value
            except BaseException as error:
                stats['verify_errors'].append(error);row.update(outcome='ERROR',code=getattr(error,'code',None));raise
            finally:
                row['current_ms']=stats['native_clocks'][-1];row['whole_verify_seconds']=time.monotonic()-began
                stats['verify_rows'].append(row)
        monkeypatch.setattr(verifier,'clock',observed_clock)
        monkeypatch.setattr(verifier,'verify',observed_verify)
        node_transport=result[6];ack=node_transport.acknowledge
        def observed_ack(intent,proof,response):
            began=time.monotonic();value=ack(intent,proof,response)
            body=response.get('body',{})
            stats['ack_rows'].append({'phase':body.get('phase'),'event':body.get('event'),'issued_ms':body.get('issued_ms'),
                'start_monotonic':began,'return_monotonic':time.monotonic()})
            return value
        monkeypatch.setattr(node_transport,'acknowledge',observed_ack)
        return result
    monkeypatch.setattr(integration,'runtime',runtime)
    generator=integration.composed_service.__wrapped__(tmp_path,tls_files,request)
    service=next(generator)
    try:yield service
    finally:
        try:next(generator)
        except StopIteration:pass

def sanitized(stats):
    assert all(row['expires_ms']-row['issued_ms']==1000 for row in stats['signs'])
    assert len(stats['commit_rows'])==2*len(stats['signs'])
    for first,second in zip(stats['commit_rows'][::2],stats['commit_rows'][1::2]):
        assert first['stage']=='before_commit' and second['stage']=='after_commit'
        assert second['delegate_entry_monotonic']>=first['delegate_return_monotonic']
    return {k:v for k,v in stats.items() if k not in ('verify_errors','observers','controllers','resources')}

@pytest.mark.parametrize('composed_service',[
    pytest.param({'authorization_ms':1000,'positive_transport':True,'hold_before':True},id='pre-sign')],indirect=True)
def test_actual_presign_hold_uses_original_clocks_and_exact_signature(project_node,composed_service,monkeypatch,stats):
    integration.run_long_fixture(project_node,composed_service,monkeypatch)
    assert len(stats['signs'])==5 and stats['delegates']==5
    assert all(row['outcome']=='RETURNED' for row in stats['verify_rows'])
    assert all(row['current_ms']-row['issued_ms']<1000 for row in stats['verify_rows'])
    assert len(stats['holds'])==1 and stats['holds'][0]['seconds']>=1.2
    record('candidate-presign',dict(sanitized(stats),all_original_assertions_completed=True,paired_real_clock=True))

@pytest.mark.parametrize('composed_service',[{'authorization_ms':1000,'positive_transport':True,'hold_after':True}],indirect=True)
def test_actual_postsign_hold_still_denies_original_expired_proof(project_node,composed_service,monkeypatch,stats):
    with pytest.raises(AssertionError) as caught:
        integration.run_long_fixture(project_node,composed_service,monkeypatch,
            expected_handled_error=lambda error: any(error is original for original in stats['verify_errors']))
    assert 'LONG_FIXTURE_WORKER_RETURN_TIMEOUT' in str(caught.value)
    assert len(stats['verify_errors'])==1 and stats['verify_errors'][0].code=='NATIVE_AUTHORIZATION_EXPIRED'
    assert stats['verify_rows'][0]['current_ms']-stats['verify_rows'][0]['issued_ms']>=1050
    assert stats['holds'][0]['kind']=='AFTER_ORIGINAL_SIGN'
    record('candidate-postsign',sanitized(stats))

@pytest.mark.parametrize('composed_service',[{'authorization_ms':1000,'positive_transport':True}],indirect=True)
def test_actual_original_long_compile_expiry_and_fresh_successor_unchanged(project_node,composed_service,monkeypatch,stats):
    integration.run_long_fixture(project_node,composed_service,monkeypatch)
    assert len(stats['signs'])==5
    record('candidate-original-long',dict(sanitized(stats),original_compile_1_2_expiry_assertions_completed=True))


from pathlib import Path
from dataclasses import replace
import hashlib,json,secrets,threading,time
import pytest
import test_tip060_journal as direct
import test_tip064_integration as integration
from test_tip064_integration import project_node
from test_tip058b_transport import control_policy,fleet_policy
from vibemql5.fleet import job_journal as original_job
from vibemql5.fleet.gateway_control import GatewayControlStore,GatewayControlError
from vibemql5.fleet.native_authorization import GatewayNativeSigner,FIELDS
from vibemql5.fleet.wire import WireError,sign_request,verify_request,encode_body
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

@pytest.fixture
def direct_case(project_node,tmp_path,monkeypatch):
    monkeypatch.setattr(direct,'GatewayJobJournal',job.GatewayJobJournal)
    gateway,node,row,_=direct.received(project_node,tmp_path)
    signer_key=Ed25519PrivateKey.generate()
    signer=GatewayNativeSigner(signer_key,'https://fixture.example',max_authorization_ms=1000)
    store=GatewayControlStore.initialize(tmp_path/'control.sqlite',policy=control_policy())
    d=integration.DomainJournal(tmp_path/'domain.sqlite',initialize=True,role='GATEWAY',policy=integration.domain_policy())
    gdomain=domain.GatewayDomain(store,d,gateway,native_signer=signer,start_authorization_ms=1000)
    controller=transport.GatewayController(store,replace(fleet_policy(),http_timeout_ms=5000,heartbeat_interval_ms=5000),
        audience=signer.audience,owner_token_sha256=hashlib.sha256(integration.TOKEN.encode()).hexdigest(),domain=gdomain)
    key=Ed25519PrivateKey.generate();device=row['target']['device_id'];public=key.public_key().public_bytes_raw().hex()
    now=int(time.time()*1000)
    issued=store.issue_grant(device,public,expected_route_generation=None,expected_revision=1,operation_id='grant',now_ms=now)
    store.consume_grant(issued['receipt']['grant_id'],issued['secret'],device,public,expected_revision=2,operation_id='pair',now_ms=int(time.time()*1000))
    session='session-a'
    def signed(path,value):
        body=encode_body(value,controller.policy.max_body_bytes)
        headers=sign_request(key,device_id=device,route_generation=1,timestamp_ms=int(time.time()*1000),
            nonce=secrets.token_hex(24),path=path,body=body,audience=signer.audience)
        return headers,body
    headers,body=signed('/fleet/v1/heartbeat',{'schema':'fleet.heartbeat/1','session_id':session})
    controller.handle('POST','/fleet/v1/heartbeat',headers.items(),body)
    value={'schema':'fleet.start-authorize/1','session_id':session,'global_job_id':row['global_job_id'],
        'node_operation_id':row['node_operation_id'],'request_sha256':row['request_sha256'],'target':row['target'],
        'local_job_id':'BT-20261003-010000-ABC123','phase':'reserve','sequence':2,'challenge':'a'*32,
        'event':'phase_admission','predecessor':None,'process_sha256':None}
    state={'signs':0,'observations':[],'clock_calls':[]}
    issue=signer.issue
    def counted_issue(**kwargs):state['signs']+=1;return issue(**kwargs)
    monkeypatch.setattr(signer,'issue',counted_issue)
    observation=store._observe_wall
    def counted_observation(ms):state['observations'].append(ms);return observation(ms)
    monkeypatch.setattr(store,'_observe_wall',counted_observation)
    args=dict(route_generation=1,session_id=session,global_job_id=row['global_job_id'],node_operation_id=row['node_operation_id'],
        request_sha256=row['request_sha256'],frozen_target=row['target'],ttl_ms=1000,signer=signer,
        local_job_id=value['local_job_id'],phase='reserve',sequence=2,challenge='a'*32)
    def context():
        headers,body=signed('/fleet/v1/native/start',value)
        proof=verify_request('POST','/fleet/v1/native/start',headers.items(),body,audience=signer.audience,max_body_bytes=controller.policy.max_body_bytes)
        admitted=int(time.time()*1000)
        sample,retain=controller._native_issuance_context(proof,session,admitted)
        def counted_sample():
            ms=sample();state['clock_calls'].append(ms);return ms
        return admitted,dict(args,issuance_clock=counted_sample,retain_observed_time=retain)
    def endpoint(extra=None):
        payload=dict(value,**(extra or {}));headers,body=signed('/fleet/v1/native/start',payload)
        return controller.handle('POST','/fleet/v1/native/start',headers.items(),body)
    resources=[node]
    try:yield gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources
    finally:
        gdomain.close();store.close()
        for resource in resources:resource.close()

def call_new(case):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=case
    admitted,kwargs=context()
    return gateway.authorize_start(args['frozen_target']['device_id'],now_ms=admitted,**kwargs)

def test_exact_live_replay_never_resigns(direct_case):
    original=call_new(direct_case);replay=call_new(direct_case)
    state=direct_case[7]
    assert replay==original and state['signs']==1
    assert original['body']['expires_ms']-original['body']['issued_ms']==1000
    record('exact-live-replay',dict(state,exact_original_signed_receipt=True))

def test_expired_replay_durable_denial_blocks_restart_rollback(direct_case):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    original=call_new(direct_case);time.sleep(1.05)
    with pytest.raises(original_job.JournalError) as denied:call_new(direct_case)
    assert denied.value.code=='START_AUTHORIZATION_UNRESOLVED' and state['signs']==1
    retained=store._control()['last_wall_ms'];assert retained>=original['body']['expires_ms']
    gp,sp=gateway.path,store.path
    gdomain.close();store.close()
    reopened=GatewayControlStore.open_existing(sp,policy=control_policy());resources.append(reopened)
    reopened_gateway=job.GatewayJobJournal(gp,**direct.POLICY);resources.append(reopened_gateway)
    rollback=original['body']['expires_ms']-1
    with pytest.raises(GatewayControlError) as caught:reopened._observe_wall(rollback)
    assert caught.value.code=='CONTROL_CLOCK_ROLLBACK'
    assert reopened._control()['last_wall_ms']==retained
    assert json.loads(reopened_gateway._db.execute('SELECT receipt FROM starts').fetchone()[0])==original
    record('expired-replay-reopen',dict(state,retained_wall=retained,rollback_input=rollback,rollback_denied=True,original_receipt_preserved=True))

@pytest.mark.parametrize('kind',['sign','commit'])
def test_failure_retains_final_time_and_original_exception(direct_case,monkeypatch,kind):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    primary,cause=RuntimeError('ORIGINAL_AUTHORIZATION_FAILURE'),RuntimeError('ORIGINAL_CAUSE');primary.add_note('original note')
    if kind=='sign':
        def fail(**kwargs):raise primary from cause
        monkeypatch.setattr(args['signer'],'issue',fail)
    else:
        def fail(phase):
            if phase=='before_commit':raise primary from cause
        gateway.fault=fail
    with pytest.raises(RuntimeError) as caught:call_new(direct_case)
    assert caught.value is primary and primary.__cause__ is cause and primary.__notes__==['original note']
    assert gateway._db.execute('SELECT count(*) FROM starts').fetchone()[0]==0
    assert store._control()['last_wall_ms']>=state['clock_calls'][-1]
    record(kind+'-failure',dict(state,original_error_identity_cause_notes=True,receipt_count=0))

def test_sign_and_retention_failure_preserves_both_originals_once(direct_case,monkeypatch):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    primary,secondary=RuntimeError('ORIGINAL_SIGN'),RuntimeError('ORIGINAL_RETENTION')
    primary.add_note('sign note');secondary.add_note('retention note')
    def fail_sign(**kwargs):raise primary
    monkeypatch.setattr(args['signer'],'issue',fail_sign)
    admitted,kwargs=context();calls=[]
    def fail_observe(ms):calls.append(ms);raise secondary
    kwargs['retain_observed_time']=fail_observe
    with pytest.raises(BaseExceptionGroup) as caught:gateway.authorize_start(value['target']['device_id'],now_ms=admitted,**kwargs)
    assert caught.value.exceptions==(primary,secondary) and len(calls)==1
    assert primary.__notes__==['sign note'] and secondary.__notes__==['retention note']
    record('sign-plus-retention-failure',{'same_original_pair':True,'retention_attempts':1,'receipt_count':gateway._db.execute('SELECT count(*) FROM starts').fetchone()[0]})

def test_old_retention_failure_is_attempted_only_once(direct_case):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    original=call_new(direct_case);admitted,kwargs=context();fault=RuntimeError('ORIGINAL_REPLAY_RETENTION');calls=[]
    def fail(ms):calls.append(ms);raise fault
    kwargs['retain_observed_time']=fail
    with pytest.raises(RuntimeError) as caught:gateway.authorize_start(value['target']['device_id'],now_ms=admitted,**kwargs)
    assert caught.value is fault and len(calls)==1 and state['signs']==1
    assert json.loads(gateway._db.execute('SELECT receipt FROM starts').fetchone()[0])==original
    record('old-retention-single-attempt',{'same_original_fault':True,'retention_attempts':1,'sign_calls':1})

@pytest.mark.parametrize('mode',['one-missing','invalid-clock','invalid-retain','failing-clock','bool-clock'])
def test_supplied_clock_pair_never_falls_back(direct_case,mode):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    admitted,kwargs=context();fault=RuntimeError('ORIGINAL_CLOCK_FAILURE')
    if mode=='one-missing':kwargs.pop('retain_observed_time')
    elif mode=='invalid-clock':kwargs['issuance_clock']=123
    elif mode=='invalid-retain':kwargs['retain_observed_time']=123
    elif mode=='failing-clock':
        def fail():raise fault
        kwargs['issuance_clock']=fail
    else:kwargs['issuance_clock']=lambda:True
    with pytest.raises(BaseException) as caught:gateway.authorize_start(value['target']['device_id'],now_ms=admitted,**kwargs)
    if mode=='failing-clock':assert caught.value is fault
    elif mode=='bool-clock':assert getattr(caught.value,'code',None)=='INVALID_JOURNAL_INPUT'
    else:assert getattr(caught.value,'code',None)=='NATIVE_AUTHORIZATION_TRUST_INVALID'
    assert state['signs']==0 and gateway._db.execute('SELECT count(*) FROM starts').fetchone()[0]==0
    record('invalid-pair-'+mode,{'denied':True,'sign_calls':0,'fallback_used':False})

@pytest.mark.parametrize('floor',['request','control','receipt'])
def test_late_rollback_guard_uses_existing_durable_floors(direct_case,floor):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    admitted,kwargs=context()
    if floor=='receipt':
        existing=gateway.authorize_start(value['target']['device_id'],now_ms=admitted+2000,**args)
        kwargs['challenge']='b'*32;kwargs['sequence']=3
        target=existing['body']['issued_ms']-1
    elif floor=='control':
        store._observe_wall(admitted+2000);target=admitted+1999
        # Genuine original owner clock now is below the persisted head.
    else:
        target=admitted-1;kwargs['issuance_clock']=lambda:target
    with pytest.raises(BaseException) as caught:gateway.authorize_start(value['target']['device_id'],now_ms=admitted,**kwargs)
    errors=caught.value.exceptions if isinstance(caught.value,BaseExceptionGroup) else [caught.value]
    assert any(getattr(e,'code',None) in ('CLOCK_ROLLBACK','CONTROL_CLOCK_ROLLBACK') for e in errors)
    assert state['signs']==(1 if floor=='receipt' else 0)
    record('rollback-'+floor,{'denied':True,'negative_clock_or_head_control_only':True,'sign_calls':state['signs']})

@pytest.mark.parametrize('guard',['route','key','readiness','session','skew','control-head','missing-clock'])
def test_native_endpoint_revalidates_late_admission_and_fails_closed(direct_case,monkeypatch,guard):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    authorize=gateway.authorize_start;injected=[]
    def late(*a,**kw):
        if not injected:
            injected.append(True);device=value['target']['device_id'];now=int(time.time()*1000)
            if guard in ('route','key'):
                route=store.get_route(device);revision=store._control()['revision']
                if guard=='route':store.revoke(device,expected_route_generation=1,expected_revision=revision,operation_id='late-revoke',now_ms=now)
                else:
                    newkey=Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
                    store.rotate_key(device,newkey,expected_public_key=route['public_key'],expected_route_generation=1,
                        expected_revision=revision,operation_id='late-rotate',now_ms=now)
            elif guard=='readiness':gateway.begin_restore(devices=[device],export_generation=1)
            elif guard=='session':controller.sessions[device]['expires_monotonic_ms']=int(time.monotonic()*1000)-1
            elif guard=='skew':time.sleep(store.policy.clock_skew_ms/1000+.05)
            elif guard=='control-head':store._observe_wall(now+2000)
        return authorize(*a,**kw)
    if guard=='missing-clock':
        handle=gdomain.handle_node
        def missing(*a,**kw):
            kw.pop('native_authorization_clock',None);kw.pop('retain_authorization_time',None)
            return handle(*a,**kw)
        monkeypatch.setattr(gdomain,'handle_node',missing)
    else:monkeypatch.setattr(gateway,'authorize_start',late)
    with pytest.raises((WireError,GatewayControlError)) as caught:endpoint()
    expected={'route':'DOMAIN_ROUTE_STALE','key':'DOMAIN_ROUTE_STALE','readiness':'RECONCILIATION_REQUIRED',
        'session':'NODE_SESSION_REQUIRED','skew':'CONTROL_TIME_INVALID','control-head':'CONTROL_CLOCK_ROLLBACK',
        'missing-clock':'NATIVE_AUTHORIZATION_TRUST_INVALID'}[guard]
    assert caught.value.code==expected and state['signs']==0
    assert gateway._db.execute('SELECT count(*) FROM starts').fetchone()[0]==0
    record('endpoint-'+guard,{'denied_code':caught.value.code,'sign_calls':0,'original_clock_unchanged':True})

def test_trusted_retainer_rejects_nonowner_thread(direct_case):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    admitted,kwargs=context();errors=[]
    before=store._control()['last_wall_ms']
    def foreign():
        try:kwargs['retain_observed_time'](admitted)
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=foreign);thread.start();thread.join(3)
    assert not thread.is_alive() and len(errors)==1 and errors[0].code=='GATEWAY_OWNER_THREAD_REQUIRED'
    assert store._control()['last_wall_ms']==before and state['signs']==0
    record('retainer-owner-thread',{'foreign_owner_denied':True,'no_clock_metadata_mutation':True})

def test_direct_deterministic_api_compatibility_is_explicit(direct_case):
    gateway,node,store,controller,gdomain,args,value,state,context,endpoint,resources=direct_case
    first=gateway.authorize_start(value['target']['device_id'],now_ms=1000,**args)
    replay=gateway.authorize_start(value['target']['device_id'],now_ms=1001,**args)
    assert first==replay and first['body']['issued_ms']==1000 and first['body']['expires_ms']==2000 and state['signs']==1
    with pytest.raises(original_job.JournalError) as expired:gateway.authorize_start(value['target']['device_id'],now_ms=2000,**args)
    assert expired.value.code=='START_AUTHORIZATION_UNRESOLVED'
    record('explicit-direct-compatibility',{'documented_deterministic_mode':True,'production_domain_requires_pair':True,'replay_unchanged':True})

