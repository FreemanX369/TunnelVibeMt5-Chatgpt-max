from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sqlite3
import threading
import time

from vibemql5.adapters.fleet_cli import NodeRuntime
from vibemql5.fleet.wire import WireError
from test_tip058b_transport import fleet_policy
from test_tip064_integration import composed_stop_runtime, close_composed_stop_runtime


OUT = Path(__file__).resolve().parent
results = []
for original in (True, False):
    pending, events = [True], []
    primary, cleanup = WireError('HTTPS_UNAVAILABLE'), WireError('HTTPS_UNAVAILABLE')
    primary.add_note('CONTROLLED_PRIMARY_TIMEOUT')
    cleanup.add_note('CONTROLLED_CLEANUP_PENDING')
    db = sqlite3.connect(':memory:')
    def step(**kwargs):
        events.append('step'); raise cleanup
    def reject_registration(*args, **kwargs):
        raise AssertionError('UNEXPECTED_REGISTRATION')
    resource = SimpleNamespace(close=lambda: events.append('resource-closed') or db.close())
    dispatcher = SimpleNamespace(has_pending_work=lambda: pending[0],
        close=lambda: events.append('dispatcher-closed'), principals=resource)
    agent = SimpleNamespace(step=step)
    client = SimpleNamespace(heartbeat=reject_registration, register_capacity=reject_registration)
    cancelled = threading.Event()
    namespace = dict(NodeRuntime=NodeRuntime, agent=agent, dispatcher=dispatcher, client=client,
        fleet_policy=fleet_policy, transport=resource, domains=resource, jobs=resource,
        cancelled=cancelled, time=time, WireError=WireError)
    if original:
        exec(compile((OUT/'original-fixture-initialization.py').read_text(), 'retained-fixture-initialization', 'exec'), namespace)
        stopping = namespace['stopping']
    else:
        stopping = composed_stop_runtime(agent, dispatcher, client, [resource])
    try:
        try:
            raise primary
        finally:
            if original:
                exec(compile((OUT/'original-fixture-cleanup.py').read_text(), 'retained-fixture-cleanup', 'exec'), namespace)
            else:
                close_composed_stop_runtime(stopping, cancelled)
    except BaseException as observed:
        if original:
            assert type(observed) is AttributeError and observed.__context__ is primary
            assert not hasattr(stopping, '_coordinator') and not hasattr(stopping, '_capacity_registered')
            assert events == []
        else:
            assert isinstance(observed, BaseExceptionGroup) and observed.exceptions == (primary, cleanup)
            assert stopping._coordinator is None and stopping._capacity_registered is False
            assert events == ['step']
        assert not stopping._closed and stopping._resources
        assert db.execute('SELECT 1').fetchone() == (1,)
        results.append({'original': original, 'observed_type': type(observed).__name__,
            'primary_identity_retained': observed.__context__ is primary if original else observed.exceptions[0] is primary,
            'cleanup_identity_retained': False if original else observed.exceptions[1] is cleanup,
            'runtime_closed': stopping._closed, 'resource_open': True, 'events': list(events),
            'primary_notes': primary.__notes__, 'cleanup_notes': cleanup.__notes__})
    finally:
        pending[0] = False
        assert stopping.close()['status'] == 'CLOSED'
        db.close()

receipt = {'control': 'exact-retained-fixture-versus-corrected-helper', 'results': results,
    'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'qualification': 'TEST_FIXTURE_ONLY', 'original_http_timeout_cause': 'OPEN'}
(OUT/'original-cleanup-control-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt, indent=2))
