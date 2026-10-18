"""Controlled schedules against unchanged source; not historical diagnosis."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time

import pytest
import test_tip064_integration as integration
import test_tip064_capacity_https as capacity
from test_tip064_integration import project_node, composed_service
from test_tip064_capacity_https import capacity_service
from test_tip058b_transport import tls_files
from vibemql5.adapters.fleet_client_tools import FleetClientFacade
from vibemql5.fleet.transport import OutboundNode
from vibemql5.fleet.wire import WireError


OUT = Path(__file__).parent


@pytest.mark.parametrize('composed_service', [1000], indirect=True)
def test_late_wrapper_failure_after_primary_is_discarded(project_node, composed_service, monkeypatch):
    primary, late = WireError('HTTPS_UNAVAILABLE'), pytest.fail.Exception('CONTROLLED_LATE_WRAPPER')
    primary.add_note('original transport note'); late.add_note('original late worker note')
    waiting, raised = threading.Event(), threading.Event()
    barrier = threading.Event()
    read = FleetClientFacade.get_job
    waits, injected = [], []
    class ReturnBarrier:
        def is_set(self): return barrier.is_set()
        def set(self): barrier.set()
        def wait(self, timeout=None):
            waits.append(timeout); waiting.set()
            assert barrier.wait(timeout)
            raised.set(); raise late
    def interrupted_read(self, *args, **kwargs):
        if waiting.is_set() and not barrier.is_set() and not injected:
            injected.append(True); raise primary
        return read(self, *args, **kwargs)
    monkeypatch.setattr(FleetClientFacade, 'get_job', interrupted_read)
    with pytest.raises(WireError) as observed:
        integration.run_long_fixture(project_node, composed_service, monkeypatch, return_barrier=ReturnBarrier())
    assert observed.value is primary
    assert raised.is_set() and injected == [True] and waits == [3]
    assert primary.__notes__ == ['original transport note']
    assert late.__notes__ == ['original late worker note']
    (OUT / 'late-worker.json').write_text(json.dumps({'classification': 'CONTROLLED_MECHANISM_NOT_HISTORICAL_CAUSE',
        'primary_identity_preserved': True, 'late_worker_raised': True, 'late_worker_in_outer_exception': False,
        'wait_seconds': waits, 'real_owner_cleanup_returned': True}, indent=2)+'\n')


def test_capacity_aggregate_can_exceed_limit_with_no_inflight_deadline_extended(project_node, capacity_service, monkeypatch):
    original_observe, original_step = capacity.observe_control_posts, OutboundNode.step
    observing, delays = [], []
    @contextmanager
    def observe(http):
        observing.append(True)
        try:
            with original_observe(http) as values: yield values
        finally: observing.clear()
    def step(self, *args, **kwargs):
        if observing:
            start = time.monotonic(); time.sleep(.6)
            delays.append(time.monotonic() - start)
        return original_step(self, *args, **kwargs)
    monkeypatch.setattr(capacity, 'observe_control_posts', observe)
    monkeypatch.setattr(OutboundNode, 'step', step)
    with pytest.raises(AssertionError) as observed:
        capacity.test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued(
            project_node, capacity_service, 'normal')
    notes = observed.value.__notes__
    facts = json.loads(next(note.removeprefix('CAPACITY_CONTROL_FIXTURE ') for note in notes if note.startswith('CAPACITY_CONTROL_FIXTURE ')))
    assert len(delays) == 3 and facts['elapsed_ms'] >= 1800
    assert facts['post_count'] == 6 and all(row['outcome'] == 'RETURNED' and row['elapsed_ms'] < 1000 for row in facts['posts'])
    assert facts['callback_count'] == facts['pending_worker_count'] == 2
    assert facts['release_set'] is False
    (OUT / 'capacity-aggregate.json').write_text(json.dumps({'classification': 'CONTROLLED_SCHEDULING_NOT_HISTORICAL_CAUSE',
        'delays_before_steps': delays, 'facts': facts, 'real_owner_cleanup_returned': True},indent=2)+'\n')
