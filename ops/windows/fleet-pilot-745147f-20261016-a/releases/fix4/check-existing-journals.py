"""Read-only compatibility/timing proof against retained operator journals."""
import hashlib,json,sys,time
from pathlib import Path
R=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\releases\fix4');P=R.parents[1];S=P/'runtime/secrets'
sys.path.insert(0,str(R/'source/app'))
from vibemql5.adapters.fleet_client_tools import operator_configuration
from vibemql5.fleet.node_transport_journal import NodeTransportJournal,TransportPolicy
from vibemql5.fleet.node_keys import load_node_key
from vibemql5.fleet.identity import IdentityRegistry
from vibemql5.fleet.gateway_control import GatewayControlStore,Policy
n=operator_configuration(S/'node.json');g=operator_configuration(S/'gateway.json')
assert n['sdk_qualifications']==[] and n['writer_policy'] is None and n['worktree_policy'] is None
beg=time.perf_counter();j=NodeTransportJournal.open_existing(n['transport_path'],TransportPolicy(**n['transport_policy']),device_id=IdentityRegistry(n['root']).load()['device_id'],public_key=load_node_key(n['node_key_file']).public_key().public_bytes_raw().hex(),audience=n['origin']);cold=time.perf_counter()-beg
try:
 before=j.witness('readonly-fix1');changes=j._db.total_changes;samples=[]
 for _ in range(100):
  start=time.perf_counter();j._validate();samples.append(time.perf_counter()-start)
 after=j.witness('readonly-fix1');assert before==after and j._db.total_changes==changes==0
finally:j.close()
store=GatewayControlStore.open_existing(g['control_path'],policy=Policy(**g['control_policy']))
try:
 head=store.control_head();assert head==store.control_head() and store._db.total_changes==0
finally:store.close()
result={'status':'PASS','read_only':True,'transport_cold_seconds':cold,'transport_warm_p95_seconds':sorted(samples)[94],'witness':after,'control_head':head,'sdk_qualifications':[],'native_capacity':'NOT_QUALIFIED'}
(R/'EXISTING-JOURNAL-CHECK.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
