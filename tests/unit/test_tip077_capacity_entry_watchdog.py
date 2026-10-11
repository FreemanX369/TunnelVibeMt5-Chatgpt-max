"""Positive entry observation and the retained original three-second boundary."""
import threading
import time

import pytest

import test_tip064_capacity_https as capacity
from test_tip064_capacity_https import capacity_service, project_node, tls_files
from vibemql5.fleet.domain import NodeDomainDispatcher
from vibemql5.fleet.transport import OutboundNode
from vibemql5.fleet.wire import WireError


def controlled_entry(project_node, capacity_service, monkeypatch, *, original_three=False):
    http = capacity_service[0]
    assert http.policy.http_timeout_ms == http.policy.heartbeat_interval_ms == 5000
    state = {'agent': None, 'dispatcher': None, 'initial': False, 'entry_calls': 0,
             'components': [], 'workers': [], 'predicates': [], 'denials': [],
             'invalid': [], 'fixture_error': None, 'initial_error': None}
    gate = threading.Event()
    init, native_work, pump, run, post = (OutboundNode.__init__, NodeDomainDispatcher._native_work,
                                         capacity.pump, capacity.run_capacity_fixture, http.post)
    state['original_pump_code'] = pump.__code__
    routes = ['/fleet/v1/heartbeat', '/fleet/v1/poll']

    def initialized(self, *args, **kwargs):
        result = init(self, *args, **kwargs)
        if self.client.http is http:
            state['agent'], state['dispatcher'] = self, self._domain_dispatcher
        return result

    def held_worker(self, *args, **kwargs):
        if self is state['dispatcher'] and len(state['workers']) < 2:
            state['workers'].append(threading.current_thread())
            # Scheduling precedes the original worker body and any request/proof.
            if not gate.wait(5):
                state['invalid'].append('PRE_REQUEST_GATE_TIMEOUT')
        return native_work(self, *args, **kwargs)

    def scheduled_post(*args, **kwargs):
        path = args[0] if args else kwargs.get('path')
        selected = state['initial'] and routes and path == routes[0]
        began = time.monotonic()
        if selected:
            routes.pop(0)
            time.sleep(1.6)
        try:
            result = post(*args, **kwargs)
        except BaseException as error:
            state['denials'].append((path, error))
            raise  # Preserve any unexpected original transport error unchanged.
        elapsed = time.monotonic() - began
        if elapsed >= 5:
            state['invalid'].append('ORIGINAL_POST_COMPONENT_EXCEEDED_5S')
        if selected:
            state['components'].append(elapsed)
        return result

    def entry_pump(agent, predicate, **kwargs):
        if agent is not state['agent'] or state['entry_calls']:
            return pump(agent, predicate, **kwargs)
        state['entry_calls'] += 1
        state['initial'] = True
        state['entry_seconds'] = 3 if original_three else kwargs.get('seconds', 3)
        began = time.monotonic()
        def observed_predicate():
            value = predicate()  # Exactly once; no extra qsize/SQL/HTTP read.
            state['predicates'].append(value)
            if not value:
                gate.set()  # Only after the original False has been obtained.
            return value
        try:
            if original_three:
                assert pump.__kwdefaults__ == {'seconds': 3}
                return pump(agent, observed_predicate)
            return pump(agent, observed_predicate, **kwargs)
        except BaseException as error:
            state['initial_error'] = error
            raise
        finally:
            state['entry_elapsed'] = time.monotonic() - began
            state['initial'] = False
            gate.set()

    def captured_run(*args, **kwargs):
        try:
            return run(*args, **kwargs)
        except BaseException as error:
            state['fixture_error'] = error
            raise

    monkeypatch.setattr(OutboundNode, '__init__', initialized)
    monkeypatch.setattr(NodeDomainDispatcher, '_native_work', held_worker)
    monkeypatch.setattr(http, 'post', scheduled_post)
    monkeypatch.setattr(capacity, 'pump', entry_pump)
    monkeypatch.setattr(capacity, 'run_capacity_fixture', captured_run)
    try:
        capacity.test_capacity_callback_original_survives_unknown_and_armed_scope(
            project_node, capacity_service, monkeypatch, release_fails=True)
    except BaseException as error:
        state['outer_error'] = error
    else:
        state['outer_error'] = None
    finally:
        gate.set()

    for path, error in state['denials']:
        if not (path == '/fleet/v1/capacity/register' and isinstance(error, WireError)
                and error.code == 'SCOPED_ROSTER_UNVERIFIED'):
            raise error
    assert not state['invalid'] and state['entry_calls'] == 1
    assert len(state['components']) == len(state['workers']) == 2
    assert all(1.6 <= elapsed < 5 for elapsed in state['components'])
    assert state['entry_elapsed'] > 3 and state['predicates'][0] is False
    assert all(not worker.is_alive() for worker in state['workers'])
    assert state['dispatcher']._closed and not state['dispatcher'].has_pending_work()
    assert len(state['denials']) == 1
    path, denial = state['denials'][0]
    assert path == '/fleet/v1/capacity/register'
    assert isinstance(denial, WireError) and denial.code == 'SCOPED_ROSTER_UNVERIFIED'
    return state


def test_positive_capacity_entry_observation_preserves_callback_union_under_finite_schedule(
        project_node, capacity_service, monkeypatch):
    state = controlled_entry(project_node, capacity_service, monkeypatch)
    if state['outer_error'] is not None:
        raise state['outer_error']
    assert state['entry_seconds'] == 10 and state['initial_error'] is None
    # The unchanged original case has checked its exact errors, notes, causes,
    # UNKNOWN result, retained ARMED/ACQUIRED scope and absent install marker.
    assert len(state['fixture_error'].exceptions) == 2


def test_original_three_second_capacity_entry_observation_remains_bounded_negative(
        project_node, capacity_service, monkeypatch):
    state = controlled_entry(project_node, capacity_service, monkeypatch, original_three=True)
    assert state['entry_seconds'] == 3 and isinstance(state['outer_error'], AssertionError)
    primary = state['initial_error']
    assert isinstance(primary, pytest.fail.Exception)
    assert str(primary) == 'bounded fixture did not reach expected state'
    members = state['fixture_error'].exceptions
    assert len(members) == 3 and members[0] is primary
    callback, release = members[1:]
    assert isinstance(callback, RuntimeError) and getattr(release, 'code', None) == 'SCOPE_RELEASE'
    assert callback.__notes__ == ['original callback note']
    assert release.__notes__ == ['original release note'] and release.__context__ is callback
    assert isinstance(callback.__cause__, RuntimeError) and str(callback.__cause__) == 'CAUSE'
    frame, original_failure = primary.__traceback__, False
    while frame is not None:
        original_failure |= frame.tb_frame.f_code is state['original_pump_code']
        frame = frame.tb_next
    assert original_failure
