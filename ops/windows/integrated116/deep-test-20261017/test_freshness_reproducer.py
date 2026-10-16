"""Isolated actual-TLS reproducer; no production store, credential or endpoint."""
import time
import pytest
from test_tip058b_transport import service,tls_files,enrolled,DEVICE
from vibemql5.fleet.node_transport_journal import NodeTransportJournal,TransportPolicy
from vibemql5.fleet.wire import WireError

def test_durable_begin_delay_ages_signed_request_past_skew(service,tmp_path,monkeypatch):
 node,_,_=enrolled(service)
 j=NodeTransportJournal.initialize(tmp_path/'transport.sqlite',TransportPolicy(max_records=20,max_payload_bytes=32768,wait_ms=100),device_id=DEVICE,public_key=node.key.public_key().public_bytes_raw().hex(),audience=node.http.origin)
 node.transport_journal=j
 try:
  node.heartbeat('session1')
  validate=j._validate
  def slow_validate():
   time.sleep(5.15);validate()
  monkeypatch.setattr(j,'_validate',slow_validate)
  started=time.perf_counter()
  with pytest.raises(WireError,match='CONTROL_TIME_INVALID'):
   node.heartbeat('session1')
  elapsed=time.perf_counter()-started
  monkeypatch.setattr(j,'_validate',validate)
  assert j.witness('after-delay')['pending_count']==1
  node.heartbeat('session1')
  assert j.witness('after-retry')['pending_count']==1
  print('REPRO_STALE_SIGNATURE_REAL_TLS delay_seconds='+str(round(elapsed,3))+' pending_preserved=1 fresh_next_request=PASS')
 finally:j.close()

def test_absolute_deadline_still_blocks_http_after_local_journal_delay(service,tmp_path,monkeypatch):
 node,_,_=enrolled(service)
 j=NodeTransportJournal.initialize(tmp_path/'transport.sqlite',TransportPolicy(max_records=20,max_payload_bytes=32768,wait_ms=100),device_id=DEVICE,public_key=node.key.public_key().public_bytes_raw().hex(),audience=node.http.origin);node.transport_journal=j
 validate=j._validate
 def delay():time.sleep(.2);validate()
 monkeypatch.setattr(j,'_validate',delay)
 try:
  with pytest.raises(WireError,match='HTTP_DEADLINE_EXCEEDED'):
   node._post('/fleet/v1/heartbeat',{'schema':'fleet.heartbeat/1','session_id':'session1'},deadline_monotonic=time.monotonic()+.1)
  monkeypatch.setattr(j,'_validate',validate)
  assert j.witness('deadline')['pending_count']==1
 finally:j.close()
