import copy
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from vibemql5.fleet.read_broker import ReadBroker,snapshot_rows,unavailable
from vibemql5.fleet.wire import WireError
from test_tip058b_transport import DEVICE,TARGET,fleet_policy,positive

ROUTE={"device_id":DEVICE,"route_generation":1,"state":"ACTIVE","status":"READY_CONTROL_ONLY"}

def command(broker):
    receipt=broker.submit("get_account_snapshot",TARGET,operation_id="read1",now_ms=1000,monotonic_ms=1000,current_route=ROUTE)
    return broker.poll(DEVICE,1,"session1",now_ms=1000,monotonic_ms=1000,limit=1,current_route=ROUTE)[0]

def payload(c):
    r=positive(c);r["observed_at_utc"]=datetime.fromtimestamp(1,timezone.utc).isoformat()
    return {"schema":"fleet.result/1","session_id":"session1","command_id":c["command_id"],"target":c["target"],"request_sha256":c["request_sha256"],"result":r}

def commit(broker,p,**overrides):
    args=dict(device_id=DEVICE,route_generation=1,session_id="session1",now_ms=1000,monotonic_ms=1000,current_route=ROUTE);args.update(overrides)
    return broker.commit(p,**args)

def test_production_rejects_synthetic_evidence():
    broker=ReadBroker(fleet_policy());c=command(broker)
    with pytest.raises(WireError):commit(broker,payload(c))

def test_replay_conflicts_and_target_mismatch():
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker);p=payload(c)
    assert not commit(broker,p)["recovered"] and commit(broker,p)["recovered"]
    p["result"]["account"]["balance"]=200
    with pytest.raises(WireError,match="READ_RESULT_CONFLICT"):commit(broker,p)
    p=payload(c);p["target"]["terminal_generation"]=2
    with pytest.raises(WireError,match="READ_RESULT_MISMATCH"):commit(broker,p)
    with pytest.raises(WireError,match="READ_OPERATION_CONFLICT"):
        broker.submit("get_terminal_live_state",TARGET,operation_id="read1",now_ms=1000,monotonic_ms=1000,current_route=ROUTE)

@pytest.mark.parametrize("edit",[
    lambda r:r["account"].update(login_masked="12345678"),
    lambda r:r["account"].update(password="secret"),
    lambda r:r["account"].update(balance=True),
    lambda r:r["account"].update(balance=float("nan")),
    lambda r:r["terminal"].update(connected="yes"),
    lambda r:r.update(cleanup={"status":"RETURNED","reason_code":None}),
    lambda r:r.update(ownership={"status":"ACTIVE"}),
    lambda r:r["observed_binding"]["process"].update(image="/other/terminal"),
    lambda r:r.update(observed_at_utc="2030-01-01T00:00:00Z"),
])
def test_malformed_secret_unproven_future_results(edit):
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker);p=payload(c);edit(p["result"])
    with pytest.raises(WireError):commit(broker,p)
    assert broker.status(c["command_id"],monotonic_ms=1000)["status"]=="PENDING"

def test_current_route_revalidation_after_delivery():
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker)
    with pytest.raises(WireError,match="READ_ROUTE_STALE"):commit(broker,payload(c),current_route={**ROUTE,"route_generation":2})
    assert broker.status(c["command_id"],monotonic_ms=1000,current_route={**ROUTE,"route_generation":2})["result"]["account"] is None

def test_deadline_late_and_session_restart_no_positive_result():
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker)
    with pytest.raises(WireError,match="READ_RESULT_LATE"):commit(broker,payload(c),monotonic_ms=2200)
    assert broker.status(c["command_id"],monotonic_ms=2200)["status"]=="FAILED"
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker)
    assert not broker.poll(DEVICE,1,"new-session",now_ms=1000,monotonic_ms=1000,limit=1,current_route=ROUTE)
    assert broker.status(c["command_id"],monotonic_ms=1000)["result"]["reason_code"]=="READ_SESSION_INTERRUPTED"
    with pytest.raises(WireError,match="READ_INTERRUPTED"):ReadBroker(fleet_policy()).status(c["command_id"],monotonic_ms=1000)

def test_capacity_fails_without_eviction():
    broker=ReadBroker(replace(fleet_policy(),max_pending_reads=4,max_retained_results=4))
    c=command(broker)
    for index in range(3):broker.submit("get_account_snapshot",TARGET,operation_id="read"+str(index+2),now_ms=1000,monotonic_ms=1000,current_route=ROUTE)
    with pytest.raises(WireError,match="READ_CAPACITY"):broker.submit("get_account_snapshot",TARGET,operation_id="read5",now_ms=1000,monotonic_ms=1000,current_route=ROUTE)
    assert broker.status(c["command_id"],monotonic_ms=1000)["status"]=="PENDING"

def test_snapshot_unknown_and_future_time_not_zero_or_fresh():
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker);p=payload(c)
    p["result"]["observed_at_utc"]="2030-01-01T00:00:00Z"
    snapshot=snapshot_rows([TARGET],[p["result"]],now_ms=1000,freshness_ms=5000)
    assert snapshot["coverage"]=={"requested":1,"succeeded":0,"failed":1}
    assert not snapshot["rows"][0]["fresh"] and snapshot["rows"][0]["account"] is None

def test_authorization_requires_still_pending_exact_delivered_command():
    broker=ReadBroker.for_synthetic_tests(fleet_policy());c=command(broker)
    kwargs=dict(device_id=DEVICE,route_generation=1,session_id="session1",monotonic_ms=1000,current_route=ROUTE)
    result=broker.authorize(c["command_id"],TARGET,c["request_sha256"],**kwargs)
    assert result["target"]==TARGET and result["session_id"]=="session1"
    with pytest.raises(WireError,match="READ_ADMISSION_MISMATCH"):
        broker.authorize(c["command_id"],TARGET,c["request_sha256"],**{**kwargs,"session_id":"other"})
    with pytest.raises(WireError,match="READ_INTERRUPTED"):
        ReadBroker(fleet_policy()).authorize(c["command_id"],TARGET,c["request_sha256"],**kwargs)
    commit(broker,payload(c))
    with pytest.raises(WireError,match="READ_ADMISSION_CLOSED"):
        broker.authorize(c["command_id"],TARGET,c["request_sha256"],**kwargs)
