"""Discriminating controlled schedules against frozen 30bcc source; no deployment."""
import json
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import threading
import time

import pytest

import test_tip064_integration as integration
from test_tip064_integration import project_node, composed_service
from test_tip058b_transport import tls_files, fleet_policy
from vibemql5.fleet.transport import OutboundNode, NodeRpcProxy
from vibemql5.fleet.job_journal import NodeJobJournal
from vibemql5.fleet.native import SyntheticNativeAdapter
from vibemql5.fleet.wire import WireError


EVIDENCE = Path(__file__).parent


def save(name, values):
    (EVIDENCE / (name + '.json')).write_text(json.dumps(values, indent=2, sort_keys=True) + '\n')


def test_h2_rpc_absolute_deadline_includes_two_prior_subdeadline_calls(tmp_path):
    queued = threading.Event()
    class ObservedQueue(Queue):
        def put_nowait(self, value):
            result = super().put_nowait(value)
            queued.set()
            return result
    rows, errors = [], []
    policy = fleet_policy()
    class Client:
        http = SimpleNamespace(policy=policy)
        def heartbeat(self, session):
            before = time.monotonic(); time.sleep(.55)
            rows.append({'route': 'HEARTBEAT', 'elapsed': time.monotonic() - before})
        def poll(self, session, maximum):
            before = time.monotonic(); time.sleep(.55)
            rows.append({'route': 'POLL', 'elapsed': time.monotonic() - before})
            return {'commands': []}
        def start_authorize(self, *args, **kwargs):
            rows.append({'route': 'START_AUTHORIZE'})
            return {'controlled': True}
    node = OutboundNode(Client(), tmp_path, policy, session_id='controlled')
    node._rpc = ObservedQueue(maxsize=policy.max_pending_reads)
    node.rpc_proxy = NodeRpcProxy(node.client, node._rpc)
    def worker():
        try: node.rpc_proxy.start_authorize('controlled', {})
        except BaseException as error: errors.append(error)
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert queued.wait(timeout=3)
        before = time.monotonic(); result = node.step(); elapsed = time.monotonic() - before
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], WireError)
        assert errors[0].code == 'NODE_RPC_DEADLINE_EXCEEDED'
        assert [row['route'] for row in rows] == ['HEARTBEAT', 'POLL']
        assert all(row['elapsed'] < 1 for row in rows)
        save('h2', {'classification': 'CONTROLLED_MECHANISM_NOT_ORIGINAL_CAUSE',
                    'rows': rows, 'step_elapsed': elapsed, 'error_code': errors[0].code,
                    'http_timeout_ms': policy.http_timeout_ms, 'step_returned': result['schema']})
    finally:
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize('composed_service', [1000], indirect=True)
def test_h1_callback_exception_becomes_unknown_and_generic_pump_failure(project_node, composed_service, monkeypatch):
    original_callback, original_outcome = SyntheticNativeAdapter._fixture_callback, NodeJobJournal._outcome
    fault = RuntimeError('CONTROLLED_FIXTURE_CALLBACK_ERROR')
    fault.add_note('CONTROLLED_ORIGINAL_NOTE')
    calls, outcomes = [], []
    def callback(self, phase, request, fence):
        if phase == 'start':
            calls.append('START'); raise fault
        return original_callback(self, phase, request, fence)
    def outcome(self, record, state, result):
        row = original_outcome(self, record, state, result)
        outcomes.append({'state': row['state'], 'reason_code': (row['result'] or {}).get('reason_code')})
        return row
    monkeypatch.setattr(SyntheticNativeAdapter, '_fixture_callback', callback)
    monkeypatch.setattr(NodeJobJournal, '_outcome', outcome)
    with pytest.raises(pytest.fail.Exception) as observed:
        integration.test_actual_tls_long_fixture_step_completes_then_receives_fresh_next_phase_grant(project_node, composed_service, monkeypatch)
    assert observed.value is not fault
    assert str(observed.value) == 'bounded fixture did not reach expected state'
    assert calls == ['START']
    assert outcomes == [{'state': 'UNKNOWN', 'reason_code': 'EXECUTION_OUTCOME_UNKNOWN'}]
    assert fault.__notes__ == ['CONTROLLED_ORIGINAL_NOTE']
    save('h1', {'classification': 'CONTROLLED_FIXTURE_FAILURE_MASKING_NOT_ORIGINAL_CAUSE',
                'original_identity_propagated': False, 'callback_calls': len(calls),
                'terminal_outcomes': outcomes, 'outer_failure_type': type(observed.value).__name__})


@pytest.mark.parametrize('composed_service', [1000], indirect=True)
@pytest.mark.parametrize('aggregate_budget', [5, 10])
def test_h3_finite_valid_phase_schedule_exceeds_aggregate_only(project_node, composed_service, monkeypatch, aggregate_budget):
    original_begin, original_complete = NodeJobJournal.begin_effect, NodeJobJournal.complete_effect
    original_outcome, original_rpc, original_pump = NodeJobJournal._outcome, NodeRpcProxy._request, integration.pump
    holds, rpc_rows, outcomes, pump_rows = [], [], [], []
    # No queued request/proof is extended. Delay only before beginning a fresh
    # intent, or before reporting already-observed harmless producer completion.
    def hold(kind, event):
        before = time.monotonic(); time.sleep(.7)
        holds.append({'kind': kind, 'event': event, 'elapsed': time.monotonic() - before})
    def begin(self, job, phase, event, **kwargs):
        hold('BEFORE_FRESH_INTENT', event)
        return original_begin(self, job, phase, event, **kwargs)
    def complete(self, job, phase, event, proof, **kwargs):
        hold('BEFORE_TRUTH_PUBLICATION', event)
        return original_complete(self, job, phase, event, proof, **kwargs)
    def outcome(self, record, state, result):
        row = original_outcome(self, record, state, result)
        outcomes.append({'state': row['state'], 'evidence': (row['result'] or {}).get('evidence')})
        return row
    def rpc(self, kind, payload):
        before = time.monotonic()
        try:
            result = original_rpc(self, kind, payload)
        except BaseException:
            rpc_rows.append({'kind': kind, 'elapsed': time.monotonic() - before, 'outcome': 'ERROR'}); raise
        rpc_rows.append({'kind': kind, 'elapsed': time.monotonic() - before, 'outcome': 'RETURNED'})
        return result
    def pump(agent, predicate, *, seconds=3):
        selected = aggregate_budget if seconds == 5 else seconds
        before = time.monotonic()
        try: return original_pump(agent, predicate, seconds=selected)
        finally: pump_rows.append({'requested': seconds, 'selected': selected, 'elapsed': time.monotonic() - before})
    monkeypatch.setattr(NodeJobJournal, 'begin_effect', begin)
    monkeypatch.setattr(NodeJobJournal, 'complete_effect', complete)
    monkeypatch.setattr(NodeJobJournal, '_outcome', outcome)
    monkeypatch.setattr(NodeRpcProxy, '_request', rpc)
    monkeypatch.setattr(integration, 'pump', pump)
    if aggregate_budget == 5:
        with pytest.raises(pytest.fail.Exception) as observed:
            integration.test_actual_tls_long_fixture_step_completes_then_receives_fresh_next_phase_grant(project_node, composed_service, monkeypatch)
        assert str(observed.value) == 'bounded fixture did not reach expected state'
    else:
        integration.test_actual_tls_long_fixture_step_completes_then_receives_fresh_next_phase_grant(project_node, composed_service, monkeypatch)
    assert len(holds) == 6
    assert all(row['elapsed'] < 1 for row in holds)
    assert len(rpc_rows) == 5 and all(row['kind'] == 'START_AUTHORIZE' and row['outcome'] == 'RETURNED' and row['elapsed'] < 1 for row in rpc_rows)
    assert outcomes == [{'state': 'SUCCEEDED', 'evidence': 'SYNTHETIC_NATIVE_ONLY'}]
    assert pump_rows[0]['elapsed'] >= 5
    save('h3-' + str(aggregate_budget), {'classification': 'CONTROLLED_VALID_SCHEDULE_NOT_ORIGINAL_CAUSE',
        'aggregate_budget': aggregate_budget, 'grant_ttl_ms': 1000, 'http_timeout_ms': composed_service[0].policy.http_timeout_ms,
        'producer_sleep_seconds_unchanged': 1.2, 'holds': holds, 'rpc_rows': rpc_rows,
        'terminal_outcomes': outcomes, 'pumps': pump_rows, 'original_test_passed': aggregate_budget == 10})
