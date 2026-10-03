"""Full configured journals over genuine local TLS; no physical MT5 claim."""
import hashlib
import base64
import copy
import shutil
from pathlib import Path
import pytest
import threading
import time
from queue import Queue

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fleet_writer_fixture import project_node,tls_files,principal_policy,writer_policy
from test_tip058b_transport import TOKEN,control_policy,fleet_policy
from vibemql5.fleet.domain import DomainJournal,DomainPolicy,GatewayDomain,NodeDomainDispatcher
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal,NodeJobJournal,canonical,digest
from vibemql5.fleet.node_transport_journal import NodeTransportJournal,TransportPolicy
from vibemql5.fleet.principals import GatewayPrincipalAuthority,PATHS,sign_principal_request
from vibemql5.fleet.wire import encode_body, sign_request, WireError
from vibemql5.fleet.restore_coordination import RestoreCoordinator,RestorePolicy,DOMAIN
from vibemql5.fleet.transport import GatewayController,HttpsClient,OwnerClient,NodeClient,serve_gateway
from vibemql5.fleet.writers import NodePrincipalRuntime, WriterError, empty_writer_witness
from vibemql5.fleet.worktrees import NodeWorktrees
from test_tip063_worktrees import git, policy as worktree_policy
from vibemql5.adapters.fleet_cli import NodeRuntime
from vibemql5.fleet.transport import OutboundNode


@pytest.mark.parametrize("nonempty",[False,True,"worktree","readonly","readonly-inactive"])
def test_actual_https_full_journal_checkpoint_and_signed_witness_clear_together(project_node,tls_files,tmp_path,nonempty):
    ca,certificate,private=tls_files
    nodekey,gatewaykey,operator=(Ed25519PrivateKey.generate() for _ in range(3))
    device=project_node['registry']['device_id'];session='recovery-session'
    registrysha=digest(project_node['registry'])
    original=tmp_path/'gateway-original';original.mkdir();restored=tmp_path/'gateway-restored';restored.mkdir()
    retained=tmp_path/'retained';retained.mkdir()
    dp=DomainPolicy(max_records=20,max_payload_bytes=32768,wait_ms=50,max_commands=4,start_authorization_ms=2000)
    jp=dict(max_records=20,max_payload_bytes=32768,wait_ms=50)
    failures=Queue()
    def start(factory,address=('127.0.0.1',0)):
        stop,ready=threading.Event(),Queue()
        def run():
            try:serve_gateway(address,certificate=certificate,key_file=private,controller_factory=factory,stop_event=stop,started=ready.put)
            except BaseException as error:failures.put(error)
        thread=threading.Thread(target=run,daemon=True);thread.start();bound=ready.get(timeout=5)
        return stop,thread,bound
    def controller(control,domains,jobs,principals,origin,recovery=None):
        return GatewayController(control,fleet_policy(),audience=origin,owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),domain=GatewayDomain(control,domains,jobs,principal_authority=principals,recovery=recovery,start_authorization_ms=2000))
    def initial(address):
        origin='https://127.0.0.1:'+str(address[1])
        return controller(GatewayControlStore.initialize(original/'control.db',policy=control_policy()),DomainJournal(original/'domains.db',policy=dp,role='GATEWAY',initialize=True),GatewayJobJournal(original/'jobs.db',initialize=True,**jp),GatewayPrincipalAuthority(original/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy(),initialize=True),origin)
    stop,thread,address=start(initial);origin='https://127.0.0.1:'+str(address[1]);http=HttpsClient(origin,fleet_policy(),cafile=str(ca));owner=OwnerClient(http,TOKEN)
    transport=NodeTransportJournal.initialize(tmp_path/'node-transport.db',TransportPolicy(max_records=20,max_payload_bytes=32768,wait_ms=50),device_id=device,public_key=nodekey.public_key().public_bytes_raw().hex(),audience=origin)
    node=NodeClient(http,nodekey,device,0,transport)
    nodejobs=NodeJobJournal(tmp_path/'node-jobs.db',initialize=True,**jp)
    nodedomains=DomainJournal(tmp_path/'node-domains.db',policy=dp,role='NODE',initialize=True)
    has_writers=nonempty not in {'readonly','readonly-inactive'}
    writers=None if not has_writers else NodePrincipalRuntime(project_node['root'],gateway_public_key=gatewaykey.public_key().public_bytes_raw(),audience=origin,device_id=device,route_generation=1,session_id=session,policy=writer_policy(),initialize=True)
    worktrees, worktree_args, worktree_head = None, None, None
    try:
        grant=owner.admin('grant',{'device_id':device,'public_key':nodekey.public_key().public_bytes_raw().hex(),'operation_id':'grant','expected_revision':1,'expected_route_generation':None})
        node.pair(grant_id=grant['receipt']['grant_id'],secret=grant['secret'],operation_id='pair',expected_revision=2)
        node.heartbeat(session)
        if writers is not None:writers.bind_control_transport(node)
        if nonempty and has_writers:
            clientkey=Ed25519PrivateKey.generate()
            credential=owner.domain_request('/fleet/v1/principals/issue',{'operation_id':'issue','client_public_key':clientkey.public_key().public_bytes_raw().hex(),'installation_id':'client','session_id':'client-session','expires_ms':int(time.time()*1000)+600000,'scopes':sorted(PATHS)})['credential']
            target={**project_node['project']['default_target'],'route_generation':1}
            owner.domain_request('/fleet/v1/principals/assign',{'operation_id':'assign','principal_id':credential['body']['principal_id'],'project_id':'P','target':target,'writer_epoch':1})
            if nonempty == "worktree":
                repo=project_node['root']/'workspaces'/'demo'
                git(repo,'init','--initial-branch=main');git(repo,'add','Experts/DemoEA.mq5');git(repo,'commit','-m','retained baseline')
                base=git(repo,'rev-parse','HEAD')
                worktree_args={'repositories':{'P':{'repository':str(repo),'base_commit':base,'source_paths':['Experts/DemoEA.mq5']}},
                    'worktree_root':project_node['root']/'isolated-worktrees','git_executable':Path(shutil.which('git')).resolve(),'policy':worktree_policy()}
                worktrees=NodeWorktrees(project_node['root'],principals=writers,initialize=True,**worktree_args)
                writers.bind_worktrees(worktrees)
                path='/fleet/v1/worktrees/prepare';operation='prepare-worktree'
                payload={'project_id':'P','worktree_id':'retained-task','base_commit':base}
            else:
                old=project_node['session']
                frozen=project_node['projects'].freeze('P','original-write',writer_id=credential['body']['principal_id'],target=target,expected_placement_revision=1,expected_session_revision=old['revision_id'],expected_session_sha256=old['revision_sha256'],operation_id='freeze')
                path='/fleet/v1/sources/write';operation='write'
                payload={'project_id':'P','frozen_id':frozen['frozen_id'],'source_base64':base64.b64encode(b'void OnTick(){ /* verified */ }\n').decode()}
            value={'schema':'fleet.domain-request/1','node':{'device_id':device,'route_generation':1},'operation_id':operation,'payload':payload}
            raw=encode_body(value,32768)
            http.post(path,value,sign_principal_request(clientkey,credential,path=path,body_bytes=raw,timestamp_ms=int(time.time()*1000),nonce='client-write',audience=origin))
            command=node.poll(session,4)['commands'][0]
            dispatcher=NodeDomainDispatcher(project_node['root'],nodedomains,nodejobs,None,principal_runtime=writers)
            dispatcher.dispatch(command,node,session);dispatcher.close()
            if worktrees is not None:
                worktree_head=worktrees.recovery_head()
                assert worktree_head['operations'][0]['git_steps'][0]['status']=='CLOSED'
                assert writers.witness('a'*64)['pending_intents']==[]
                assert project_node['projects'].sessions.get('P')['revision_id']=='REV-000001'
            else:assert project_node['projects'].sessions.get('P')['revision_id']=='REV-000002'
    finally:
        if worktrees is not None:worktrees.close()
        if writers is not None:writers.close()
        nodedomains.close();stop.set();thread.join(timeout=5)
    assert not thread.is_alive()
    if not failures.empty():raise failures.get()
    control=GatewayControlStore.open_existing(original/'control.db',policy=control_policy())
    snapshot=control.snapshot();head=control.control_head();control.backup(retained/'control-backup.db');control.close()
    jobs=GatewayJobJournal(original/'jobs.db',**jp);mapping=jobs.mapping_sha256();jobs.backup(retained/'jobs-backup.db');jobs.close()
    domains=DomainJournal(original/'domains.db',policy=dp,role='GATEWAY');domainhead=domains.control_head();domains.close()
    principals=GatewayPrincipalAuthority(original/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy());principalhead=principals.control_head();principals.close()
    facts={'schema':'fleet.quiescent-checkpoint/1','audience':origin,'control_head':head,'control_wall_ms':snapshot['last_wall_ms'],'devices':[{'device_id':device,'public_key':nodekey.public_key().public_bytes_raw().hex(),'route_generation':1,'state':'ACTIVE','registry_sha256':registrysha,'session_id':session,'worktree_head':worktree_head}],'job_export_generation':1,'job_mapping_sha256':mapping,'domain_head':domainhead,'principal_head':principalhead}
    checkpoint=retained/'checkpoint.json';checkpoint.write_bytes(canonical(facts));scopequeue=Queue()
    def recovery_service(address):
        control=GatewayControlStore.restore(retained/'control-backup.db',restored/'control.db',policy=control_policy())
        jobs=GatewayJobJournal.restore_backup(retained/'jobs-backup.db',restored/'jobs.db',devices=[device],export_generation=1,**jp)
        domains=DomainJournal(original/'domains.db',policy=dp,role='GATEWAY')
        principals=GatewayPrincipalAuthority(original/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy())
        now=int(time.time()*1000);body={'schema':'fleet.restore.operator-approval/1','audience':origin,'challenge':jobs.restore_state()['challenge'],'issued_ms':now,'expires_ms':now+30000,'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
        approval={'approval':body,'signature':operator.sign(DOMAIN+canonical(body)).hex()}
        recovery=RestoreCoordinator(restored/'coordination.json',control,jobs,audience=origin,operator_public_key=operator.public_key().public_bytes_raw(),policy=RestorePolicy(max_devices=20,max_payload_bytes=1048576,max_nonces=20,clock_skew_ms=5000,wait_ms=50),now_ms=now,initialize=True,approval=approval,checkpoint_path=checkpoint,domain_journal=domains,principal_authority=principals)
        scopequeue.put((recovery.scope(),jobs.restore_state(),recovery.record['coordination_sha256']))
        return controller(control,domains,jobs,principals,origin,recovery)
    stop,thread,_=start(recovery_service,address)
    nodedomains=DomainJournal(tmp_path/'node-domains.db',policy=dp,role='NODE')
    writers=None if not has_writers else NodePrincipalRuntime(project_node['root'],gateway_public_key=gatewaykey.public_key().public_bytes_raw(),audience=origin,device_id=device,route_generation=1,session_id=session,policy=writer_policy())
    if writers is not None:nodedomains.bind_principal_authority(writers)
    worktrees=None
    if worktree_args is not None:
        worktrees=NodeWorktrees(project_node['root'],principals=writers,**worktree_args);writers.bind_worktrees(worktrees)
    recovery_dispatcher=None
    try:
        scope,jobscope,coordination=scopequeue.get(timeout=3)
        if nonempty=='readonly-inactive':
            inactive=NodePrincipalRuntime(project_node['root'],gateway_public_key=gatewaykey.public_key().public_bytes_raw(),audience=origin,device_id=device,route_generation=1,session_id=session,policy=writer_policy(),initialize=True)
            inactive.close()
        value={'schema':'fleet.reconcile/1','coordination_sha256':coordination,'registry_sha256':registrysha,'session_id':session,
            'transport_witness':transport.witness(scope['challenge']),
            'job_witness':nodejobs.witness({**jobscope,'coordination_sha256':coordination,'joint_scope':scope},device_id=device,route_generation=1,session_id=session,private_key=nodekey),
            'domain_witness':nodedomains.witness(coordination,device_id=device,route_generation=1,session_id=session),
            'principal_witness':writers.witness(coordination) if writers is not None else None if nonempty=='readonly-inactive' else empty_writer_witness(project_node['root'],device_id=device,route_generation=1,session_id=session,coordination_sha256=coordination,expected_worktree_head=worktree_head)}
        if value['principal_witness'] is not None:assert value["principal_witness"]["worktree_head"]==worktree_head
        if nonempty is True:
            changed=copy.deepcopy(value)
            changed['principal_witness'].update(authority='EMPTY_ABSENCE',assignments=[],phase_receipts=[])
            before=(restored/'coordination.json').read_bytes()
            raw=encode_body(changed,32768)
            headers=sign_request(nodekey,device_id=device,route_generation=1,timestamp_ms=int(time.time()*1000),
                nonce='c'*32,path='/fleet/v1/reconcile',body=raw,audience=origin)
            # Deliberately invalid but genuinely signed TLS request: empty
            # local evidence cannot erase existing gateway writer history.
            with pytest.raises(WireError,match='PRINCIPAL_WITNESS_UNRESOLVED'):
                http.post('/fleet/v1/reconcile',changed,headers)
            assert (restored/'coordination.json').read_bytes()==before
        if nonempty=='readonly':
            assert value['principal_witness']['authority']=='EMPTY_ABSENCE'
            assert not (project_node['root']/'state'/'fleet'/'writers.json').exists()
            assert not (project_node['root']/'state'/'fleet'/'writers.owner.lock').exists()
        if nonempty in {'worktree','readonly','readonly-inactive'}:
            recovery_dispatcher=NodeDomainDispatcher(project_node['root'],nodedomains,nodejobs,None,principal_runtime=writers)
            agent=OutboundNode(node,project_node['root'],fleet_policy(),session_id=session,domain_dispatcher=recovery_dispatcher)
            # Exercise the actual CLI helper over the already-open genuine
            # client/agent/journals, without a second lifetime journal owner.
            runtime=object.__new__(NodeRuntime)
            runtime.config={'root':str(project_node['root'])};runtime.client=node
            runtime.agent=agent;runtime.dispatcher=recovery_dispatcher
            recovery_input={'schema':'fleet.node-recovery-input/1','coordination_sha256':coordination,'joint_scope':scope,'job_scope':jobscope}
            if nonempty=='readonly-inactive':
                before=(restored/'coordination.json').read_bytes();transport_before=transport.witness(scope['challenge'])
                with pytest.raises(WriterError,match='WRITER_ABSENCE_UNPROVEN'):runtime.reconcile(recovery_input)
                assert (restored/'coordination.json').read_bytes()==before
                assert transport.witness(scope['challenge'])==transport_before
                assert inactive.path.exists() and inactive.path.with_suffix('.owner.lock').exists()
                result=None
            else:result=runtime.reconcile(recovery_input)
        else:result=node.reconcile(value)
        if result is not None:
            assert result['status']['ready'] and result['status']['dispatch_enabled']
            assert transport.witness(scope['challenge'])['pending_count']==0
            assert node.heartbeat(session)['transport']=='ONLINE'
    finally:
        if recovery_dispatcher is not None:recovery_dispatcher.close()
        if worktrees is not None:worktrees.close()
        if writers is not None:writers.close()
        nodejobs.close();nodedomains.close();transport.close();stop.set();thread.join(timeout=5)
    assert not thread.is_alive()
    if not failures.empty():raise failures.get()
