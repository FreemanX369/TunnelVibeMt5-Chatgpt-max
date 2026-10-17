"""Regressions for deployed D01-D05; no live authority or MT5 qualification."""
import asyncio, hashlib, importlib.util, json, sqlite3, time
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_tip058b_transport import service,tls_files,enrolled,DEVICE,TARGET,fleet_policy,positive
from test_tip060c_node_transport import journal,request,response
from test_tip058b_transport import control_policy
from vibemql5.fleet.node_transport_journal import NodeTransportJournal,TransportPolicy
from vibemql5.fleet.gateway_control import GatewayControlStore,GatewayControlError
from vibemql5.fleet.transport import OutboundNode
from vibemql5.fleet.wire import WireError
from vibemql5.fleet.pilot_runtime import PilotRoundGuard

def test_full_validation_precedes_fresh_signature_real_tls(service,tmp_path,monkeypatch):
 node,_,_=enrolled(service)
 j=NodeTransportJournal.initialize(tmp_path/'witness.sqlite',TransportPolicy(max_records=20,max_payload_bytes=32768,wait_ms=100),device_id=DEVICE,public_key=node.key.public_key().public_bytes_raw().hex(),audience=node.http.origin)
 node.transport_journal=j
 try:
  validate=j._validate;delayed=[]
  def slow_once():
   if not delayed:delayed.append(True);time.sleep(5.15)
   validate()
  monkeypatch.setattr(j,'_validate',slow_once)
  assert node.heartbeat('fresh-session')['transport']=='ONLINE'
  assert j.witness('fresh')['pending_count']==0
 finally:j.close()

def test_expired_deadline_mints_no_new_intent(service,tmp_path,monkeypatch):
 node,_,_=enrolled(service)
 j=NodeTransportJournal.initialize(tmp_path/'witness.sqlite',TransportPolicy(max_records=20,max_payload_bytes=32768,wait_ms=100),device_id=DEVICE,public_key=node.key.public_key().public_bytes_raw().hex(),audience=node.http.origin)
 node.transport_journal=j
 validate=j._validate
 def slow():time.sleep(.2);validate()
 monkeypatch.setattr(j,'_validate',slow)
 try:
  with pytest.raises(WireError,match='HTTP_DEADLINE_EXCEEDED'):
   node._post('/fleet/v1/heartbeat',{'schema':'fleet.heartbeat/1','session_id':'s'},deadline_monotonic=time.monotonic()+.1)
  monkeypatch.setattr(j,'_validate',validate)
  assert j.witness('empty')['request_count']==0
 finally:j.close()

@pytest.mark.parametrize('external',[False,True])
def test_cached_transport_validation_detects_sqlite_tamper(tmp_path,external):
 key=Ed25519PrivateKey.generate();path=tmp_path/'witness.sqlite';j=journal(path,key);proof=request(key);j.begin(proof)
 try:
  assert j.witness('before')['pending_count']==1
  connection=sqlite3.connect(path) if external else j._db
  connection.execute("UPDATE requests SET intent='{}'")
  if external:connection.commit();connection.close()
  with pytest.raises(WireError,match='TRANSPORT_JOURNAL_INVALID'):j.witness('after')
 finally:j.close()

def test_validated_owned_commits_do_not_rescan_retained_transport_history(tmp_path):
 key=Ed25519PrivateKey.generate();j=journal(tmp_path/'witness.sqlite',key);statements=[];j._db.set_trace_callback(statements.append)
 try:
  for n in range(8):
   proof=request(key,format(n,'048x'));digest=j.begin(proof);j.acknowledge(digest,proof,response(proof,n+3))
  assert not any(q=='SELECT * FROM requests' or q=='PRAGMA quick_check' for q in statements)
  assert j.witness('all')['request_count']==8
 finally:j.close()

@pytest.mark.parametrize('external',[False,True])
def test_cached_control_validation_detects_sqlite_tamper(tmp_path,external):
 path=tmp_path/'control.sqlite';store=GatewayControlStore.initialize(path,policy=control_policy())
 try:
  store.snapshot()
  connection=sqlite3.connect(path) if external else store._db
  connection.execute("UPDATE control SET status='INVALID'")
  if external:connection.commit();connection.close()
  with pytest.raises(GatewayControlError,match='CONTROL_CORRUPT'):store.snapshot()
 finally:store.close()

def test_late_read_does_not_terminate_node_control_or_replace_deadline(service,tmp_path):
 http,owner,*_=service;node,_,_=enrolled(service)
 def delayed(command):time.sleep(1.3);return positive(command)
 agent=OutboundNode(node,tmp_path,fleet_policy(),session_id='late-session',synthetic_read_adapter=delayed)
 node.heartbeat('late-session');queued=owner.read('get_account_snapshot',TARGET,'late-op')
 result=agent.step()
 assert result['read_commits'][0]['reason_code']=='READ_RESULT_LATE'
 status=owner.read_status(queued['command_id'])
 assert status['result']['reason_code']=='READ_DEADLINE_EXCEEDED'
 assert node.heartbeat('late-session')['transport']=='ONLINE'

@pytest.mark.parametrize('code',['HTTPS_UNAVAILABLE','HTTP_DEADLINE_EXCEEDED','CONTROL_TIME_INVALID'])
def test_pilot_retries_bounded_then_fences_without_reset(code):
 guard=PilotRoundGuard();calls=[]
 def fail():calls.append(True);raise WireError(code)
 assert guard.run(fail)['status']=='CONTROL_RETRY'
 assert guard.run(fail)['retry_after_seconds']==2
 assert guard.run(fail)['status']=='NODE_FENCED'
 assert guard.run(fail)['status']=='NODE_FENCED' and len(calls)==3

def test_pilot_success_resets_consecutive_failures_and_permanent_error_never_retries():
 guard=PilotRoundGuard();fail=lambda:(_ for _ in ()).throw(WireError('HTTPS_UNAVAILABLE'))
 guard.run(fail);assert guard.run(lambda:None)['status']=='RUNNING'
 assert guard.run(fail)['consecutive_failures']==1
 result=guard.run(lambda:(_ for _ in ()).throw(WireError('CONTROL_CORRUPT')))
 assert result['status']=='NODE_FENCED' and result['reason_code']=='NODE_REQUIRES_OPERATOR'

@pytest.mark.parametrize('code,expected',[('HTTPS_UNAVAILABLE','HTTPS_UNAVAILABLE'),('secret-credential-marker','FLEET_REQUEST_FAILED')])
def test_fleet_mcp_returns_safe_actionable_error_without_secret(code,expected):
 from mcp.client.client import Client
 from vibemql5.adapters.fleet_mcp import create_server
 class Facade:
  def inventory(self,*args):raise WireError(code)
 async def run():
  async with Client(create_server(client_facade=Facade())) as c:
   r=await c.call_tool('fleet_inventory',{})
   assert r.is_error
   text=''.join(x.text for x in r.content if hasattr(x,'text'))
   assert expected in text and (code==expected or code not in text)
 asyncio.run(run())

def test_transport_history_digest_keeps_old_canonical_form_and_supports_over_10k(tmp_path):
 key=Ed25519PrivateKey.generate();j=journal(tmp_path/'witness.sqlite',key)
 try:
  proof=request(key);digest=j.begin(proof);j.acknowledge(digest,proof,response(proof))
  rows=[dict(r) for r in j._db.execute('SELECT * FROM requests ORDER BY nonce_sha256')]
  from vibemql5.fleet.wire import logical_digest
  assert j._history_digest(rows)==logical_digest(rows)
  many=rows*10001
  expected=hashlib.sha256(json.dumps(many,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  assert j._history_digest(many)==expected
 finally:j.close()

def test_cached_journal_detects_path_replacement(tmp_path):
 key=Ed25519PrivateKey.generate();path=tmp_path/'witness.sqlite';j=journal(path,key)
 try:
  try:path.rename(tmp_path/'old.sqlite');path.write_bytes(b'replaced')
  except PermissionError:pytest.skip('OS denies replacement while SQLite owns the file')
  with pytest.raises(WireError,match='TRANSPORT_JOURNAL_INVALID'):j.witness('replaced')
 finally:j.close()
