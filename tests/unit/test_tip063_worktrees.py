"""Actual temporary Git + real TLS principal admission; no external repository."""
import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fleet_writer_fixture import writer_fixture, project_node, tls_files
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.fleet.job_journal import digest
from vibemql5.fleet.principals import PrincipalError
from vibemql5.fleet.wire import WireError
from vibemql5.fleet.worktrees import NodeWorktrees, WorktreeError, WorktreePolicy
from vibemql5.fleet.writers import NodePrincipalRuntime, WriterError

PREPARE='/fleet/v1/worktrees/prepare'
COMMIT='/fleet/v1/worktrees/commit'
RETIRE='/fleet/v1/worktrees/retire'
EA='Experts/DemoEA.mq5'


def git(repo,*args):
    env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
    return subprocess.check_output([shutil.which('git'),'-c','user.name=Fixture','-c','user.email=fixture@localhost','-c','core.autocrlf=false','-c','commit.gpgsign=false','-C',str(repo),*args],env=env,stderr=subprocess.STDOUT).decode().strip()


def policy():
    return WorktreePolicy(max_worktrees=10,max_operations=50,max_changes=8,max_change_bytes=32768,
        max_payload_bytes=1048576,max_git_output_bytes=131072,git_timeout_ms=5000,wait_ms=50)


@pytest.fixture
def worktrees(writer_fixture):
    f=writer_fixture;repo=f['root']/'workspaces'/'demo'
    git(repo,'init','--initial-branch=main');git(repo,'add','--',EA);git(repo,'commit','-m','baseline')
    baseline=git(repo,'rev-parse','HEAD')
    args=dict(principals=f['runtime'],repositories={'P':{'repository':str(repo),'base_commit':baseline,'source_paths':[EA]}},
        worktree_root=f['root']/'isolated-worktrees',git_executable=Path(shutil.which('git')).resolve(),policy=policy())
    store=NodeWorktrees(f['root'],initialize=True,**args);f['runtime'].bind_worktrees(store)
    value={**f,'repo':repo,'base':baseline,'worktrees':store,'args':args}
    yield value
    value['worktrees'].close()


def admitted(f,path,payload,op):
    record=f['admit'](path,payload,op)
    command=f['runtime'].verify_command(record['path'],record['payload'],op)
    return record,command


def run(f,path,payload,op):
    rec,command=admitted(f,path,payload,op)
    return f['worktrees'].apply_command(path,command,operation_id=op),rec,command


def prepare(f,identifier='task',op='prepare'):
    return run(f,PREPARE,{'project_id':'P','worktree_id':identifier,'base_commit':f['base']},op)


def commit_payload(f,head=None,data=b'void OnTick(){ /* isolated */ }\n',reference=None):
    target=f['worktrees'].local_path('task')
    old=target.joinpath(EA).read_bytes()
    return {'project_id':'P','worktree_id':'task','expected_head':head or git(target,'rev-parse','HEAD'),
        'changes':[{'path':EA,'expected_sha256':hashlib.sha256(old).hexdigest(),'sha256':hashlib.sha256(data).hexdigest(),
                    'source_base64':base64.b64encode(data).decode()}], 'message':'Isolated source update',
        'source_ref':copy.deepcopy(f['projects'].get('P')['session']),'result_ref':reference}


def test_real_git_prepare_commit_retire_preserves_main_and_session(worktrees):
    f=worktrees;main=f['source'].read_bytes();session=copy.deepcopy(f['projects'].get('P')['session'])
    created,_,create_command=prepare(f)
    assert created['head']==f['base'] and len(created['writer_acks'])==1
    target=f['worktrees'].local_path('task');assert target!=f['repo']
    reference={'reference':'task-result','sha256':'a'*64}
    committed,record,command=run(f,COMMIT,commit_payload(f,reference=reference),'commit')
    assert committed['head']!=f['base'] and committed['tree']==git(target,'rev-parse','HEAD^{tree}')
    assert committed['result_reference_status']=='UNVERIFIED_REFERENCE_ONLY'
    assert f['source'].read_bytes()==main and git(f['repo'],'rev-parse','HEAD')==f['base']
    assert f['projects'].get('P')['session']==session
    assert len(list((f['root']/'state'/'project-sessions'/'P'/'revisions').glob('REV-*.json')))==1
    assert f['worktrees'].apply_command(COMMIT,command,operation_id='commit')['idempotent_recovered']
    retired,_,_=run(f,RETIRE,{'project_id':'P','worktree_id':'task','expected_head':committed['head']},'retire')
    assert retired['state']=='RETIRED' and not target.exists()
    # Historical completed replay is immutable even after later commits/retirement.
    assert f['worktrees'].apply_command(PREPARE,create_command,operation_id='prepare')['head']==f['base']
    assert f['worktrees'].apply_command(COMMIT,command,operation_id='commit')['head']==committed['head']
    assert 'source_base64' not in json.dumps(committed)


@pytest.mark.parametrize('mutation,code',[
    ('wrong-base','WORKTREE_BASE_MISMATCH'),('dirty-main','WORKTREE_DIRTY'),('main-head','WORKTREE_HEAD_DRIFT'),
    ('traversal','WORKTREE_INPUT_INVALID'),('unknown-project','WORKTREE_AUTHORITY_INVALID')])
def test_prepare_rejects_before_git_effect(worktrees,mutation,code):
    f=worktrees;payload={'project_id':'P','worktree_id':'task','base_commit':f['base']}
    if mutation=='wrong-base':payload['base_commit']='f'*40
    elif mutation=='dirty-main':f['source'].write_bytes(b'dirty')
    elif mutation=='main-head':git(f['repo'],'commit','--allow-empty','-m','drift')
    elif mutation=='traversal':payload['worktree_id']='../outside'
    else:
        # A authenticated evidence is only for registered P; caller labels cannot override it.
        rec,command=admitted(f,PREPARE,payload,'prepare')
        with pytest.raises(WriterError,match="WRITER_PROOF_IMMUTABLE"):
            command._request=b"changed caller project"
        assert not (f['args']['worktree_root']/'P'/'task').exists();return
    rec,command=admitted(f,PREPARE,payload,'prepare')
    with pytest.raises(WorktreeError,match=code):f['worktrees'].apply_command(PREPARE,command,operation_id='prepare')
    assert not (f['args']['worktree_root']/'P'/'task').exists()


@pytest.mark.parametrize('mutation,code',[
    ('head','WORKTREE_HEAD_DRIFT'),('dirty','WORKTREE_DIRTY'),('source-cas','WORKTREE_SOURCE_CHANGED'),
    ('path','WORKTREE_PATH_INVALID'),('unregistered','WORKTREE_SOURCE_UNREGISTERED'),('session','WORKTREE_SOURCE_REF_MISMATCH'),
    ('no-change','WORKTREE_NO_CHANGES')])
def test_commit_boundaries_do_not_mutate(worktrees,mutation,code):
    f=worktrees;prepare(f);target=f['worktrees'].local_path('task');payload=commit_payload(f);before=target.joinpath(EA).read_bytes()
    if mutation=='head':git(target,'commit','--allow-empty','-m','drift')
    elif mutation=='dirty':target.joinpath(EA).write_bytes(b'dirty')
    elif mutation=='source-cas':payload['changes'][0]['expected_sha256']='0'*64
    elif mutation=='path':payload['changes'][0]['path']='../../state/secret'
    elif mutation=='unregistered':payload['changes'][0]['path']='Experts/Other.mq5'
    elif mutation=='session':payload['source_ref']['source_sha256']='0'*64
    else:
        payload['changes'][0].update(sha256=hashlib.sha256(before).hexdigest(),source_base64=base64.b64encode(before).decode())
    _,command=admitted(f,COMMIT,payload,'commit')
    with pytest.raises(WorktreeError,match=code):f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    assert target.joinpath(EA).read_bytes()==(b'dirty' if mutation=='dirty' else before)
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


def test_common_source_guard_and_forged_command_denied(worktrees):
    f=worktrees;_,command=admitted(f,PREPARE,{'project_id':'P','worktree_id':'task','base_commit':f['base']},'prepare')
    with pytest.raises(WorktreeError,match='WORKTREE_AUTHORITY_INVALID'):
        f['worktrees'].apply_command(PREPARE,{'verified':True},operation_id='prepare')
    with ConcurrencyManager(f['root']).mutation('fleet_source_guard',resource='demo:'+EA,wait_seconds=0):
        with pytest.raises(Exception):f['worktrees'].apply_command(PREPARE,command,operation_id='prepare')
    assert not (f['args']['worktree_root']/'P'/'task').exists()
    assert next(iter(f['worktrees'].state['operations'].values()))['state']=='UNKNOWN'


@pytest.mark.parametrize('point',['create:after_effect','commit:after_effect','retire:after_effect'])
def test_exact_crash_reopen_recovers_without_duplicate_git_effect(worktrees,point):
    f=worktrees
    if point.startswith('create'):path,payload,op=PREPARE,{'project_id':'P','worktree_id':'task','base_commit':f['base']},'prepare'
    else:
        prepare(f)
        if point.startswith('commit'):path,payload,op=COMMIT,commit_payload(f),'commit'
        else:path,payload,op=RETIRE,{'project_id':'P','worktree_id':'task','expected_head':f['base']},'retire'
    record,command=admitted(f,path,payload,op)
    def fail(stage):
        if stage==point:raise OSError('private diagnostic must remain hidden')
    f['worktrees'].fault=fail
    with pytest.raises(WriterError,match='WRITER_OUTCOME_UNKNOWN'):f['worktrees'].apply_command(path,command,operation_id=op)
    old=f['runtime'];f['worktrees'].close();old.close()
    runtime=NodePrincipalRuntime(f['root'],gateway_public_key=old.key,audience=old.audience,device_id=old.device_id,
        route_generation=1,session_id=old.session_id,policy=old.policy)
    runtime.bind_control_transport(f['node']);f['runtime']=runtime;f['args']['principals']=runtime
    f['worktrees']=NodeWorktrees(f['root'],**f['args']);runtime.bind_worktrees(f['worktrees'])
    try:
        command=runtime.verify_command(record['path'],record['payload'],op)
        receipt=f['worktrees'].apply_command(path,command,operation_id=op)
        assert receipt['idempotent_recovered'] and len(receipt['writer_acks'])==1
        if point.startswith('commit'):
            target=f['worktrees'].local_path('task');assert git(target,'rev-list','--count','HEAD')=='2'
            assert receipt['head']==git(target,'rev-parse','HEAD')
        if point.startswith('retire'):assert not (f['args']['worktree_root']/'P'/'task').exists()
        assert f['source'].read_bytes()==b'void OnTick(){}\r\n'
    finally:runtime.close()


def test_incomplete_source_effect_never_reruns_or_allows_successor(worktrees):
    f=worktrees;prepare(f);payload=commit_payload(f);record,command=admitted(f,COMMIT,payload,'commit')
    def fail(stage):
        if stage=='source:after_effect':raise OSError('crash')
    f['worktrees'].fault=fail
    with pytest.raises(WriterError):f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    f['worktrees'].fault=None;target=f['worktrees'].local_path('task');changed=target.joinpath(EA).read_bytes()
    with pytest.raises(WorktreeError,match='WORKTREE_GIT_CLOSURE_UNPROVEN'):f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    assert target.joinpath(EA).read_bytes()==changed and git(target,'rev-parse','HEAD')==f['base']
    _,nextcommand=admitted(f,PREPARE,{'project_id':'P','worktree_id':'other','base_commit':f['base']},'other')
    with pytest.raises(WorktreeError,match='WORKTREE_RECONCILIATION_REQUIRED'):f['worktrees'].apply_command(PREPARE,nextcommand,operation_id='other')


def test_gateway_revokes_between_file_write_and_git_commit(worktrees):
    f=worktrees;prepare(f);payload=commit_payload(f);_,command=admitted(f,COMMIT,payload,'commit')
    def revoke(stage):
        if stage=='source:after_effect':
            f['owner'].domain_request('/fleet/v1/principals/revoke',{'operation_id':'revoke','principal_id':f['principal']})
    f['worktrees'].fault=revoke
    with pytest.raises(WireError):f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    target=f['worktrees'].local_path('task');assert git(target,'rev-parse','HEAD')==f['base']
    assert any(x['state']=='UNKNOWN' for x in f['worktrees'].state['operations'].values())
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


@pytest.mark.parametrize('seam',['disabled-hook','included-filter','worktree-config','direct-filter','info-attributes'])
def test_hooks_and_external_config_are_denied_without_execution(worktrees,seam,tmp_path):
    f=worktrees;sentinel=tmp_path/'EXECUTED';script=tmp_path/'effect.sh'
    script.write_text('#!/bin/sh\nprintf executed > '+str(sentinel)+'\n');script.chmod(0o755)
    if seam=='disabled-hook':shutil.copy(script,f['worktrees'].hooks/'post-checkout')
    elif seam=='included-filter':
        config=tmp_path/'included.config';config.write_text('[filter "bad"]\n clean = '+script.as_posix()+'\n smudge = '+script.as_posix()+'\n')
        git(f['repo'],'config','include.path',config.as_posix())
        assert git(f['repo'],'config','--get','filter.bad.clean')==script.as_posix()
    elif seam=='worktree-config':git(f['repo'],'config','extensions.worktreeConfig','true')
    elif seam=='direct-filter':git(f['repo'],'config','filter.bad.smudge',str(script))
    else:(f['repo']/'.git'/'info'/'attributes').write_text(EA+' filter=bad\n')
    _,command=admitted(f,PREPARE,{'project_id':'P','worktree_id':'task','base_commit':f['base']},'prepare')
    with pytest.raises(WorktreeError,match='GIT_(HOOKS|CONFIG|FILTER)_UNSUPPORTED'):
        f['worktrees'].apply_command(PREPARE,command,operation_id='prepare')
    assert not sentinel.exists() and not (f['args']['worktree_root']/'P'/'task').exists()


def test_repository_hooks_overridden_by_empty_directory(worktrees,tmp_path):
    f=worktrees;sentinel=tmp_path/'EXECUTED';hook=f['repo']/'.git'/'hooks'/'post-checkout'
    hook.write_text('#!/bin/sh\nprintf executed > '+str(sentinel)+'\n');hook.chmod(0o755)
    prepare(f);assert not sentinel.exists()


def test_symlink_worktree_destination_and_source_denied(worktrees,tmp_path):
    f=worktrees;project=f['args']['worktree_root']/'P';project.mkdir()
    try:project.joinpath('task').symlink_to(tmp_path,target_is_directory=True)
    except OSError:pytest.skip('symlink privilege unavailable')
    _,command=admitted(f,PREPARE,{'project_id':'P','worktree_id':'task','base_commit':f['base']},'prepare')
    with pytest.raises(WorktreeError,match='WORKTREE_PATH_INVALID'):f['worktrees'].apply_command(PREPARE,command,operation_id='prepare')
    project.joinpath('task').unlink();prepare(f,op='prepare-valid');payload=commit_payload(f)
    target=f['worktrees'].local_path('task');target.joinpath(EA).unlink();target.joinpath(EA).symlink_to(f['source'])
    # status catches the altered source before any write.
    _,command=admitted(f,COMMIT,payload,'commit')
    with pytest.raises(WorktreeError):f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


@pytest.mark.parametrize('corruption',['owner','body','request','receipt','signed-request'])
def test_malformed_or_cross_record_journal_fails_finitely(worktrees,corruption):
    f=worktrees;prepare(f);store=f['worktrees'];store.close()
    value=json.loads(store.path.read_text());value.pop('record_sha256');op=next(iter(value['operations'].values()))
    if corruption=='owner':value['worktrees']['task']['owner']=True
    elif corruption=='body':op['body']=[]
    elif corruption=='request':op['request']={'worktree_id':[]}
    elif corruption=='receipt':op['receipt']['writer_epoch']=True
    else:op['request']['base_commit']='a'*40
    value['record_sha256']=digest(value);store.path.write_text(json.dumps(value))
    with pytest.raises(WorktreeError):NodeWorktrees(f['root'],**f['args'])


def test_explicit_numeric_policy_rejects_bool():
    values=policy().__dict__;values['max_changes']=True
    with pytest.raises(WorktreeError,match='WORKTREE_POLICY_INVALID'):WorktreePolicy(**values)


@pytest.mark.parametrize('entry',['submodule','attributes','symlink'])
def test_unsupported_baseline_entries_cannot_activate_worktrees(worktrees,entry):
    f=worktrees;f['worktrees'].close()
    if entry=='submodule':
        git(f['repo'],'update-index','--add','--cacheinfo','160000,'+f['base']+',module')
    elif entry=='attributes':
        (f['repo']/'.gitattributes').write_text(EA+' text eol=lf\n');git(f['repo'],'add','.gitattributes')
    else:
        link=f['repo']/'link'
        try:link.symlink_to('Experts/DemoEA.mq5')
        except OSError:pytest.skip('symlink privilege unavailable')
        git(f['repo'],'add','link')
    git(f['repo'],'commit','-m','unsupported baseline')
    args=copy.copy(f['args']);args['repositories']=copy.deepcopy(args['repositories'])
    args['repositories']['P']['base_commit']=git(f['repo'],'rev-parse','HEAD')
    with pytest.raises(WorktreeError,match='GIT_(SUBMODULE|ATTRIBUTES)_UNSUPPORTED'):
        NodeWorktrees(f['root'],**args)
    assert not (f['args']['worktree_root']/'P'/'task').exists()


def test_valid_shaped_changed_receipt_cannot_disagree_with_writer_ack(worktrees):
    f=worktrees;prepare(f);store=f['worktrees'];store.close()
    value=json.loads(store.path.read_text());value.pop('record_sha256')
    next(iter(value['operations'].values()))['receipt']['head']='a'*40
    value['record_sha256']=digest(value);store.path.write_text(json.dumps(value))
    with pytest.raises(WorktreeError):NodeWorktrees(f['root'],**f['args'])


def test_ignored_untracked_bytes_block_retirement(worktrees):
    f=worktrees;prepare(f);target=f['worktrees'].local_path('task')
    (f['repo']/'.git'/'info'/'exclude').write_text('private.tmp\n')
    secret=target/'private.tmp';secret.write_bytes(b'preserve ignored user data')
    _,command=admitted(f,RETIRE,{'project_id':'P','worktree_id':'task','expected_head':f['base']},'retire')
    with pytest.raises(WorktreeError,match='WORKTREE_DIRTY'):
        f['worktrees'].apply_command(RETIRE,command,operation_id='retire')
    assert secret.read_bytes()==b'preserve ignored user data'


def test_actual_git_output_is_bounded_without_source_effect(worktrees):
    f=worktrees;f['worktrees'].close();args=copy.copy(f['args'])
    values=policy().__dict__;values['max_git_output_bytes']=1;args['policy']=WorktreePolicy(**values)
    with pytest.raises(WorktreeError,match='GIT_OUTPUT_UNPROVEN'):NodeWorktrees(f['root'],**args)
    assert f['source'].read_bytes()==b'void OnTick(){}\r\n'


def test_matching_git_head_without_durable_closure_remains_unknown(worktrees):
    f=worktrees;prepare(f);payload=commit_payload(f);_,command=admitted(f,COMMIT,payload,'commit')
    def fail(stage):
        # stage and write-tree completion are stored; commit exits but its closure
        # publication is interrupted. Exact resulting HEAD cannot replace it.
        op=f['worktrees'].state['operations'].get(command.body['intent_sha256'])
        if stage=='git_closed:before_commit' and op and op['git_steps'][-1]['purpose']=='commit':raise OSError('lost closure publication')
    f['worktrees'].fault=fail
    with pytest.raises(WriterError):f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    f['worktrees'].fault=None;target=f['worktrees'].local_path('task')
    assert git(target,'rev-parse','HEAD')!=f['base'] and git(target,'status','--porcelain')==''
    assert f['worktrees'].state['operations'][command.body['intent_sha256']]['git_steps'][-1]['status']=='ATTEMPTED'
    f['worktrees'].close();f['worktrees']=NodeWorktrees(f['root'],**f['args']);f['runtime'].bind_worktrees(f['worktrees'])
    with pytest.raises(WorktreeError,match='WORKTREE_GIT_CLOSURE_UNPROVEN'):
        f['worktrees'].apply_command(COMMIT,command,operation_id='commit')
    assert git(target,'rev-list','--count','HEAD')=='2'


def test_control_state_cannot_be_selected_as_worktree_root(worktrees):
    f=worktrees;f['worktrees'].close();args=copy.copy(f['args']);args['worktree_root']=f['root']/'state'/'unsafe-worktrees'
    with pytest.raises(WorktreeError,match='WORKTREE_CONFIG_INVALID'):NodeWorktrees(f['root'],**args)
    assert not args['worktree_root'].exists()


def test_read_only_recovery_head_binds_closed_steps_and_clean_git(worktrees):
    f=worktrees;prepare(f);run(f,COMMIT,commit_payload(f),'commit')
    journal=f['worktrees'].path.read_bytes();source=f['source'].read_bytes()
    one=f['worktrees'].recovery_head();two=f['worktrees'].recovery_head()
    assert one==two and one['schema']=='fleet.node-worktree-head/1'
    assert len(one['operations'])==2 and len(one['worktrees'])==1
    assert [step['purpose'] for op in one['operations'] if op['phase']=='worktree_commit' for step in op['git_steps']]==['stage','write_tree','commit']
    assert f['worktrees'].path.read_bytes()==journal and f['source'].read_bytes()==source
    assert 'source_base64' not in json.dumps(one)
    target=f['worktrees'].local_path('task');target.joinpath(EA).write_bytes(b'external dirty bytes')
    with pytest.raises(WorktreeError,match='WORKTREE_DIRTY'):f['worktrees'].recovery_head()


def test_recovery_head_refuses_unknown_even_if_git_looks_complete(worktrees):
    f=worktrees
    def fail(stage):
        if stage=='create:after_effect':raise OSError('lost acknowledgment')
    f['worktrees'].fault=fail
    with pytest.raises(WriterError):prepare(f)
    with pytest.raises(WorktreeError,match='WORKTREE_RECONCILIATION_REQUIRED'):f['worktrees'].recovery_head()
    assert git(f['args']['worktree_root']/'P'/'task','rev-parse','HEAD')==f['base']


def test_git_windows_path_separators_and_drive_case_parse_as_same_root(monkeypatch):
    # Portable lexical fixture only. The native full prepare/commit/retire suite
    # separately exercises real filesystem canonicalization on Windows CI.
    from pathlib import PureWindowsPath
    import vibemql5.fleet.worktrees as module
    def canonical(value, *, must_exist=True):
        assert not must_exist
        return PureWindowsPath(value)
    monkeypatch.setattr(module, '_path', canonical)
    observed=NodeWorktrees._listed_worktree_paths(b'worktree c:/Node/Isolated/P/task\0HEAD '+b'a'*40+b'\0\0')
    assert observed==[PureWindowsPath(r'C:\Node\Isolated\P\task')]
    assert PureWindowsPath(r'C:\other\task') not in observed


def test_native_git_path_variants_use_canonical_filesystem_comparison(worktrees):
    import vibemql5.fleet.worktrees as module
    f=worktrees;prepare(f);target=f['worktrees'].local_path('task')
    observed=git(target,'rev-parse','--show-toplevel')
    assert module._path(observed)==target
    variant=str(target).replace('\\','/')
    if target.drive:variant=variant[0].swapcase()+variant[1:]
    assert module._path(variant)==target
    assert target in f['worktrees']._listed_worktree_paths(('worktree '+variant+'\0HEAD '+f['base']+'\0\0').encode())


@pytest.mark.parametrize('raw',[b'',b'warning: hidden stale worktree\nworktree /tmp/a\0HEAD '+b'a'*40+b'\0\0',b'worktree /tmp/a\0unknown-field\0\0',b'worktree relative/path\0HEAD '+b'a'*40+b'\0\0',b'worktree /tmp/a\0HEAD invalid\0\0'])
def test_malformed_git_listing_cannot_prove_retired_absence(raw):
    with pytest.raises(WorktreeError,match='GIT_OUTPUT_UNPROVEN'):NodeWorktrees._listed_worktree_paths(raw)
