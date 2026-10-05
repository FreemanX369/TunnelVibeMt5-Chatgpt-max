"""Independent preservation of a rejected candidate; never grants acceptance."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

folder = Path(__file__).resolve().parent
head = '81d458ffce7a856a94aae3fb2166d0a9943fba7e'
tree = 'e1ed18128f047baab88f0c5efa2bc0159289de83'
runs = json.loads((folder/'metadata/eight-workflows-final.json').read_text())
assert len(runs) == len({r['workflow_id'] for r in runs}) == 8
assert all(r['head_sha'] == head and r['run_attempt'] == 1 and r['status'] == 'completed' for r in runs)
assert sum(r['conclusion'] == 'success' for r in runs) == 6
assert {r['id'] for r in runs if r['conclusion'] == 'failure'} == {37293992261,37293992217}
artifacts = json.loads((folder/'metadata/all-artifacts-independent-failed-verification.json').read_text())
assert artifacts['head'] == head and artifacts['tree'] == tree
assert len(artifacts['artifacts']) == 5
assert sum(len(r['proofs']) for r in artifacts['artifacts']) == 9
windows = next(r for r in artifacts['artifacts'] if r.get('source_status') == 'FAIL')
assert windows['passed'] == 1205 and windows['source_entries'] == 210
required = []
prefixes = ('test_control_post_observation_', 'test_transport_timeout_during_pending_grant_commit_',
 'test_windows_retained_identity_positive_', 'test_windows_retained_handle_rejects_fresh_',
 'test_real_process_fifo_and_atomic_resource_', 'test_real_queued_resource_writer_',
 'test_actual_tls_blocked_native_', 'test_actual_tls_verified_two_slot_delivery_',
 'test_scoped_future_collection_', 'test_restore_cleanup_preserves_', 'test_restore_handoff_retains_',
 'test_native_denial_observation_', 'test_native_denial_original_', 'test_native_denial_timeout_',
 'test_composed_lost_ack_once_')
with zipfile.ZipFile(folder/'artifacts'/windows['archive']) as z:
    cases = list(ET.fromstring(z.read('unit.junit.xml')).iter('testcase'))
    for c in cases:
        if c.get('name','').startswith(prefixes):
            assert not list(c), c.attrib
            required.append({'class':c.get('classname'),'name':c.get('name'),'status':'PASS',
                             'time':c.get('time'),'scope':'SOURCE_FIXTURE_ONLY'})
    errors = [{'class':c.get('classname'),'name':c.get('name'),'message':t.get('message'),'trace':t.text}
              for c in cases for t in c if t.tag == 'error']
    assert len(errors) == 1
    assert errors[0]['class'] == 'tests.unit.test_tip060c_restore'
    assert errors[0]['name'] == 'test_uncertain_or_changed_witness_cannot_clear_recovery[route]'
    assert 'CONTROL_BUSY' in errors[0]['trace']
assert len(required) == 29, len(required)
logs = {}
for path in sorted((folder/'logs').glob('*.log')):
    data = path.read_bytes()
    logs[path.name] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
       'truncated':False,'bom':data.startswith(b'\xef\xbb\xbf'),'crlf_lines':data.count(b'\r\n')}
deep = (folder/'logs/job-111710798184.log').read_text(encoding='utf-8-sig')
assert '1 failed, 1205 passed, 12 skipped' in deep
assert 'retained_file_metadata' in deep and "'function': 'transaction', 'line': 330" in deep
runtime = json.loads((folder/'metadata/runtime-final-read-only.json').read_text())
runtime_values = {r['k']:r['result']['structuredContent'] for r in runtime}
assert runtime_values['server_info']['version'] == '0.2.42'
assert runtime_values['server_info']['tool_count'] == len(runtime_values['server_info']['tool_names']) == 85
assert 'deployment_preflight' not in runtime_values['server_info']
assert runtime_values['health']['state'] == 'READY'
assert runtime_values['health']['active_job'] is None and runtime_values['health']['queue_length'] == 0
control_checks = runtime_values['health']['concurrency']
assert control_checks['mutation_lock'] is None and control_checks['native_lock'] is None
assert control_checks['mutation_waiters'] == control_checks['native_waiters'] == 0
assert all(r['healthz_status'] == r['readyz_status'] == 200 and r['process_count'] == 1
           for r in runtime_values['tunnels']['instances'])
receipt = {'schema':'tip065.failed-candidate-receipt/1','status':'SOURCE_GATE_REJECTED_6_OF_8',
  'head':head,'tree':tree,'main':'70e2112da9fe8eaa6262f2ba896b55bf3e078260','run_attempt':1,
  'workflows':[{k:r[k] for k in ('name','id','workflow_id','html_url','status','conclusion','head_sha','run_attempt')} for r in runs],
  'deep':{'run':37293992261,'job':111710798184,'passed':1205,'failed':1,'errors':0,'skipped':12,
      'failed_case':'test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued[delayed-release-and-completion]',
      'primary':'poll response-status TimeoutError at1000ms; sampled fresh source metadata ctypes binding',
      'cleanup':'results response-status TimeoutError at734ms; sampled GatewayJobJournal COMMIT'},
  'windows_errors':errors,'artifacts':artifacts,'decoded_logs':logs,'required_windows_controls':required,
  'runtime_read_only':{'version':'0.2.42','tool_count':85,'deployment_preflight_loaded':False,
      'health':'READY_IDLE','tunnels':'A_B_C_READYZ200_ONE_PROCESS_EACH'},
  'overlay_deployment':'NOT_RUN','restart':'NOT_RUN','physical_qualification':'NOT_RUN',
  'incidents':'OPEN_UNKNOWN_NO_ROOT_CAUSE_OR_FUNCTIONAL_FIX_CLAIM','workflow_reruns':0}
(folder/'metadata/verification-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'head':head,'gate':'6/8 REJECTED','artifacts':5,'source_entries':210,'proofs':9,
    'required_windows_controls':len(required),'logs':logs,'deploy':'NOT_RUN'},indent=2))
