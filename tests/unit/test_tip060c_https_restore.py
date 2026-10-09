"""Full configured journals over genuine local TLS; no physical MT5 claim."""
import hashlib
import base64
import copy
import shutil
import sys
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import pytest
import time
from queue import Queue

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fleet_writer_fixture import project_node,tls_files,principal_policy,writer_policy
from fleet_gateway_fixture import start_gateway_fixture,preserve_fixture_failure,stop_gateway_fixture
from test_tip058b_transport import TOKEN,control_policy,fleet_policy,FixtureHttpsClient
from vibemql5.fleet.domain import DomainJournal,DomainPolicy,GatewayDomain,NodeDomainDispatcher
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal,NodeJobJournal,canonical,digest
from vibemql5.fleet.node_transport_journal import NodeTransportJournal,TransportPolicy
from vibemql5.fleet.principals import GatewayPrincipalAuthority,PATHS,sign_principal_request
from vibemql5.fleet.wire import encode_body, sign_request, WireError
from vibemql5.fleet.restore_coordination import RestoreCoordinator,RestorePolicy,DOMAIN
from vibemql5.fleet.transport import GatewayController,OwnerClient,NodeClient
from vibemql5.fleet.writers import NodePrincipalRuntime, WriterError, empty_writer_witness
from vibemql5.fleet.worktrees import NodeWorktrees
from test_tip063_worktrees import git, policy as worktree_policy
from vibemql5.adapters.fleet_cli import NodeRuntime
from vibemql5.fleet.transport import OutboundNode


def restore_control_policy():
    # Ordinary consistent backup/restore, like the existing TIP-058A/060C
    # healthy-backup fixtures; deliberate transport/contention budgets stay.
    return replace(control_policy(), sqlite_busy_timeout_ms=1000)


def close_restore_fixture(resources, stopped, thread, failures, *, retained_resources=()):
    """Keep every cleanup failure and always observe the original server stop."""
    primary_present = sys.exception() is not None
    with preserve_fixture_failure():
        errors = []
        for resource in resources:
            if resource is None: continue
            try: resource.close()
            except BaseException as error: errors.append(error)
        try: stop_gateway_fixture(stopped, thread, failures, timeout=5)
        except BaseException as error: errors.append(error)
        if primary_present or errors:
            # Only a successful first-phase handoff transfers these open owners.
            for resource in retained_resources:
                try: resource.close()
                except BaseException as error: errors.append(error)
        if len(errors) == 1: raise errors[0]
        if errors: raise BaseExceptionGroup("restore fixture cleanup failed", errors)


@pytest.mark.parametrize("primary_present", [False, True])
def test_restore_cleanup_preserves_all_failures_and_closes_actual_resources(primary_present):
    import sqlite3
    import threading
    from types import SimpleNamespace
    primary = WireError("HTTPS_UNAVAILABLE"); primary.add_note("retained original note")
    first, second, server, retained = (RuntimeError(name) for name in ("first", "second", "server", "retained"))
    databases = [sqlite3.connect(":memory:") for _ in range(3)]
    calls, stopped, failures = [], threading.Event(), Queue()
    thread = threading.Thread(target=lambda: stopped.wait(5))
    failures.put(server); thread.start()
    def close(index, error):
        calls.append(index); databases[index].close(); raise error
    resources = [SimpleNamespace(close=lambda: close(0, first)), None,
                 SimpleNamespace(close=lambda: close(1, second))]
    retained_resources = [SimpleNamespace(close=lambda: close(2, retained))]
    try:
        with pytest.raises(BaseExceptionGroup) as caught:
            if primary_present:
                try: raise primary
                finally: close_restore_fixture(resources, stopped, thread, failures, retained_resources=retained_resources)
            else: close_restore_fixture(resources, stopped, thread, failures, retained_resources=retained_resources)
        cleanup = caught.value
        if primary_present:
            assert cleanup.exceptions[0] is primary
            cleanup = cleanup.exceptions[1]
        assert cleanup.exceptions == (first, second, server, retained)
        assert primary.__notes__ == ["retained original note"]
        assert calls == [0, 1, 2] and stopped.is_set() and not thread.is_alive()
        assert failures.empty()
        for db in databases:
            with pytest.raises(sqlite3.ProgrammingError): db.execute("SELECT 1")
    finally:
        stopped.set(); thread.join(timeout=5)
        for db in databases: db.close()


@pytest.mark.parametrize("primary_present", [False, True])
def test_restore_handoff_retains_owners_only_after_success(primary_present, monkeypatch):
    import sqlite3
    primary = WireError("HTTPS_UNAVAILABLE")
    db, calls = sqlite3.connect(":memory:"), []
    monkeypatch.setitem(close_restore_fixture.__globals__, "stop_gateway_fixture",
        lambda stopped, thread, failures, *, timeout: calls.append(timeout))
    try:
        if primary_present:
            with pytest.raises(WireError) as caught:
                try: raise primary
                finally: close_restore_fixture([], None, None, None, retained_resources=[db])
            assert caught.value is primary
            with pytest.raises(sqlite3.ProgrammingError): db.execute("SELECT 1")
        else:
            close_restore_fixture([], None, None, None, retained_resources=[db])
            assert db.execute("SELECT 1").fetchone() == (1,)
        assert calls == [5]  # Exactly one unchanged stop observation per phase.
    finally: db.close()


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
    cp=restore_control_policy()
    failures=Queue()
    def start(factory,address=('127.0.0.1',0)):
        return start_gateway_fixture(address,certificate=certificate,key_file=private,
            controller_factory=factory,failures=failures,startup_timeout=5,stop_timeout=5)
    def controller(control,domains,jobs,principals,origin,recovery=None):
        return GatewayController(control,fleet_policy(),audience=origin,owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),domain=GatewayDomain(control,domains,jobs,principal_authority=principals,recovery=recovery,start_authorization_ms=2000))
    def initial(address):
        origin='https://127.0.0.1:'+str(address[1])
        return controller(GatewayControlStore.initialize(original/'control.db',policy=cp),DomainJournal(original/'domains.db',policy=dp,role='GATEWAY',initialize=True),GatewayJobJournal(original/'jobs.db',initialize=True,**jp),GatewayPrincipalAuthority(original/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy(),initialize=True),origin)
    stop,thread,address=start(initial);origin='https://127.0.0.1:'+str(address[1]);http=FixtureHttpsClient(origin,fleet_policy(),cafile=str(ca),server_thread=thread,failures=failures);owner=OwnerClient(http,TOKEN)
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
        close_restore_fixture([worktrees,writers,nodedomains],stop,thread,failures,retained_resources=[nodejobs,transport])

    with GatewayControlStore.open_existing(original/'control.db',policy=cp) as control:
        snapshot=control.snapshot();head=control.control_head();control.backup(retained/'control-backup.db')
    with GatewayJobJournal(original/'jobs.db',**jp) as jobs:
        mapping=jobs.mapping_sha256();jobs.backup(retained/'jobs-backup.db')
    with closing(DomainJournal(original/'domains.db',policy=dp,role='GATEWAY')) as domains:
        domainhead=domains.control_head()
    with closing(GatewayPrincipalAuthority(original/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy())) as principals:
        principalhead=principals.control_head()
    facts={'schema':'fleet.quiescent-checkpoint/1','audience':origin,'control_head':head,'control_wall_ms':snapshot['last_wall_ms'],'devices':[{'device_id':device,'public_key':nodekey.public_key().public_bytes_raw().hex(),'route_generation':1,'state':'ACTIVE','registry_sha256':registrysha,'session_id':session,'worktree_head':worktree_head}],'job_export_generation':1,'job_mapping_sha256':mapping,'domain_head':domainhead,'principal_head':principalhead}
    checkpoint=retained/'checkpoint.json';checkpoint.write_bytes(canonical(facts));scopequeue=Queue()
    def recovery_service(address):
        control=GatewayControlStore.restore(retained/'control-backup.db',restored/'control.db',policy=cp)
        jobs=GatewayJobJournal.restore_backup(retained/'jobs-backup.db',restored/'jobs.db',devices=[device],export_generation=1,**jp)
        domains=DomainJournal(original/'domains.db',policy=dp,role='GATEWAY')
        principals=GatewayPrincipalAuthority(original/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy())
        now=int(time.time()*1000);body={'schema':'fleet.restore.operator-approval/1','audience':origin,'challenge':jobs.restore_state()['challenge'],'issued_ms':now,'expires_ms':now+30000,'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
        approval={'approval':body,'signature':operator.sign(DOMAIN+canonical(body)).hex()}
        recovery=RestoreCoordinator(restored/'coordination.json',control,jobs,audience=origin,operator_public_key=operator.public_key().public_bytes_raw(),policy=RestorePolicy(max_devices=20,max_payload_bytes=1048576,max_nonces=20,clock_skew_ms=5000,wait_ms=50),now_ms=now,initialize=True,approval=approval,checkpoint_path=checkpoint,domain_journal=domains,principal_authority=principals)
        scopequeue.put((recovery.scope(),jobs.restore_state(),recovery.record['coordination_sha256']))
        return controller(control,domains,jobs,principals,origin,recovery)
    stop,thread,_=start(recovery_service,address)
    http.server_thread=thread  # The same TLS client now observes the actual replacement server.
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
        close_restore_fixture([recovery_dispatcher,worktrees,writers,nodejobs,nodedomains,transport],stop,thread,failures)


@pytest.mark.parametrize('sqlite_budget_ms', [100, 1000])
def test_healthy_backup_progress_deadline_is_explicit_and_has_no_sqlite_contention(tmp_path, monkeypatch, sqlite_budget_ms):
    import sqlite3
    from types import SimpleNamespace
    import vibemql5.fleet.gateway_control as control_module
    events, clock = [], [0.0]
    policy = control_policy() if sqlite_budget_ms == 100 else restore_control_policy()
    assert policy.sqlite_busy_timeout_ms == sqlite_budget_ms
    with GatewayControlStore.initialize(tmp_path / 'control.db', policy=policy) as store:
        source = store._db
        class ObservedBackup:
            def __getattr__(self, name):
                return getattr(source, name)
            def backup(self, destination, *, pages, progress, sleep):
                def observed(status, remaining, total):
                    events.append({'status': status, 'remaining': remaining})
                    progress(status, remaining, total)
                source.backup(destination, pages=pages, progress=observed, sleep=sleep)
        def delayed_clock():
            clock[0] += .15
            return clock[0]
        destination = tmp_path / 'backup.db'
        with monkeypatch.context() as fault:
            fault.setattr(store, '_db', ObservedBackup())
            fault.setattr(control_module, 'time', SimpleNamespace(monotonic=delayed_clock))
            if sqlite_budget_ms == 100:
                with pytest.raises(control_module.GatewayControlError, match='CONTROL_BUSY'):
                    store.backup(destination)
                assert not destination.exists()
            else:
                assert store.backup(destination)['evidence'] == 'CONSISTENT_SQLITE_SNAPSHOT'
                assert destination.exists()
        assert events and all(row == {'status': sqlite3.SQLITE_DONE, 'remaining': 0} for row in events)
        assert store.snapshot()['revision'] == 1
        print('CONTROLLED_HEALTHY_BACKUP_PROGRESS ' + str({'sqlite_budget_ms': sqlite_budget_ms,
            'elapsed_between_clock_reads_ms': 150, 'sqlite_progress': events}))
    # Independent ownership observation after closure; do not replay backup.
    with GatewayControlStore.open_existing(tmp_path / 'control.db', policy=policy) as reopened:
        assert reopened.snapshot()['revision'] == 1
