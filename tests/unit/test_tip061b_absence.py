"""Absence is signed evidence with no existing or historical authority."""
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fleet_writer_fixture import project_node, writer_policy, principal_policy
from vibemql5.fleet.principals import GatewayPrincipalAuthority, PrincipalError, PATHS
from vibemql5.fleet.writers import NodePrincipalRuntime, WriterError, empty_writer_witness
from vibemql5.fleet.wire import encode_body, sign_request, verify_request


def absence(node):
    return empty_writer_witness(node['root'],device_id=node['registry']['device_id'],
        route_generation=1,session_id='node-session',coordination_sha256='a'*64,expected_worktree_head=None)


def proof(key, device, path, body):
    raw=encode_body(body,1048576)
    headers=sign_request(key,device_id=device,route_generation=1,timestamp_ms=1500,
        nonce='b'*32,path=path,body=raw,audience='https://localhost')
    return verify_request('POST',path,list(headers.items()),raw,audience='https://localhost',max_body_bytes=1048576)


def test_empty_absence_does_not_create_authority(project_node):
    fleet=project_node['root']/'state'/'fleet'
    existed=fleet.exists();before=sorted(p.name for p in fleet.iterdir()) if existed else []
    value=absence(project_node)
    assert value['authority']=='EMPTY_ABSENCE'
    assert value['assignments']==value['phase_receipts']==value['pending_intents']==[]
    assert value['worktree_head'] is None
    assert fleet.exists()==existed
    assert (sorted(p.name for p in fleet.iterdir()) if existed else [])==before


@pytest.mark.parametrize('marker',['writers.json','writers.owner.lock','worktrees.json','worktrees.owner.lock',
    '.writers.json.pending.tmp','.worktrees.json.pending.tmp','writers.unknown','disabled-git-hooks'])
def test_existing_unknown_or_inactive_marker_denies_absence(project_node,marker):
    path=project_node['root']/'state'/'fleet'/marker;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b'unknown inactive authority')
    with pytest.raises(WriterError,match='WRITER_ABSENCE_UNPROVEN'):absence(project_node)
    assert path.read_bytes()==b'unknown inactive authority'


def test_actual_closed_empty_writer_remains_authority(project_node):
    key=Ed25519PrivateKey.generate()
    runtime=NodePrincipalRuntime(project_node['root'],gateway_public_key=key.public_key().public_bytes_raw(),
        audience='https://localhost',device_id=project_node['registry']['device_id'],route_generation=1,
        session_id='node-session',policy=writer_policy(),initialize=True)
    runtime.close();before=runtime.path.read_bytes()
    with pytest.raises(WriterError,match='WRITER_ABSENCE_UNPROVEN'):absence(project_node)
    assert runtime.path.read_bytes()==before


def test_nonnull_worktree_checkpoint_cannot_use_absence(project_node):
    with pytest.raises(WriterError,match='WRITER_ABSENCE_UNPROVEN'):
        empty_writer_witness(project_node['root'],device_id=project_node['registry']['device_id'],
            route_generation=1,session_id='node-session',coordination_sha256='a'*64,expected_worktree_head={})


def test_historical_replaced_assignment_denies_signed_absence(tmp_path):
    gateway,nodekey,client=(Ed25519PrivateKey.generate() for _ in range(3))
    device='dev_'+'a'*32
    authority=GatewayPrincipalAuthority(tmp_path/'authority.json',signing_key=gateway,
        audience='https://localhost',policy=principal_policy(),initialize=True)
    try:
        issued=authority.owner_request('/fleet/v1/principals/issue',{'operation_id':'issue','client_public_key':client.public_key().public_bytes_raw().hex(),
            'installation_id':'client','session_id':'client-session','expires_ms':2000,'scopes':sorted(PATHS)},now_ms=1000)
        pid=issued['principal_id']
        target={'schema':'fleet.target/1','device_id':device,'route_generation':1,'terminal_id':'term_'+'b'*32,'terminal_generation':1}
        authority.owner_request('/fleet/v1/principals/assign',{'operation_id':'original-assign','principal_id':pid,'project_id':'P','target':target,'writer_epoch':1},now_ms=1100)
        authority.owner_request('/fleet/v1/principals/release',{'operation_id':'release','project_id':'P'},now_ms=1200)
        result={'schema':'fleet.writer-fence.receipt/1','project_id':'P','fence_epoch':2,'pending_intents':[],'writer_acks':[]}
        authority.acknowledge_fence(proof(nodekey,device,'/fleet/v1/results',{'result':result}),project_id='P',fence_epoch=2,pending_intents=[])
        authority.owner_request('/fleet/v1/principals/assign',{'operation_id':'new-assign','principal_id':pid,'project_id':'P',
            'target':{**target,'device_id':'dev_'+'c'*32},'writer_epoch':2},now_ms=1300)
        authority.prepare_restore('a'*64,expected_head=authority.control_head())
        value={'schema':'fleet.node-writer-witness/1','authority':'EMPTY_ABSENCE','coordination_sha256':'a'*64,
            'device_id':device,'route_generation':1,'session_id':'node-session','pending_intents':[],
            'assignments':[],'phase_receipts':[],'worktree_head':None}
        before=authority.path.read_bytes()
        with pytest.raises(PrincipalError,match='PRINCIPAL_WITNESS_UNRESOLVED'):
            authority.verify_recovery_witness(proof(nodekey,device,'/fleet/v1/reconcile',{'session_id':'node-session','principal_witness':value}),coordination_sha256='a'*64)
        assert authority.path.read_bytes()==before
    finally:authority.close()
