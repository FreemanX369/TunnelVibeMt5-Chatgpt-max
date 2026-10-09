"""Owned fixture holds release during the original bounded cleanup."""
import threading

import pytest

import test_tip064_integration as integration
from test_tip064_integration import LONG_FIXTURE_PROFILE, composed_service, project_node, tls_files
from vibemql5.fleet.job_journal import NodeJobJournal


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
def test_cleanup_releases_owned_pre_intent_holds_without_extending_drain(
        project_node, composed_service, monkeypatch, capsys):
    created, barriers, waits, gates = [], [], [], []
    make_runtime, run = integration.runtime, integration.run_long_fixture
    begin = NodeJobJournal.begin_effect

    def owned_runtime(*args, **kwargs):
        result = make_runtime(*args, **kwargs)
        created.append(result)
        return result

    def observe_run(*args, return_barrier=None, **kwargs):
        # The fallback lets this control exercise the unchanged parent too.
        barrier = threading.Event() if return_barrier is None else return_barrier
        barriers.append(barrier)
        original_wait = barrier.wait

        def wait(timeout=None):
            before = barrier.is_set()
            result = original_wait(timeout)
            if timeout == .7:
                waits.append((before, result))
            return result

        monkeypatch.setattr(barrier, 'wait', wait)
        return run(*args, return_barrier=barrier, **kwargs)

    def gated_begin(self, job, phase, event, **kwargs):
        if (created and self is created[0][4] and event == 'snapshot_prepare:0001'
                and not gates):
            gates.append(True)
            # Gate before a fresh intent; release only through original cleanup.
            assert barriers[0].wait(20), 'OWNED_PRE_INTENT_GATE_TIMEOUT'
        return begin(self, job, phase, event, **kwargs)

    monkeypatch.setattr(integration, 'runtime', owned_runtime)
    monkeypatch.setattr(integration, 'run_long_fixture', observe_run)
    monkeypatch.setattr(NodeJobJournal, 'begin_effect', gated_begin)
    integration.test_long_fixture_valid_finite_schedule_requires_aggregate_observation(
        project_node, composed_service, monkeypatch, seconds=5)

    assert gates == [True] and len(barriers) == len(created) == 1
    assert waits == [(False, False)] + [(True, True)] * 5
    dispatcher = created[0][3]
    assert dispatcher._closed and not dispatcher.has_pending_work()
    assert not dispatcher._futures and not dispatcher._native_records
    facts = integration.long_owner_output(capsys.readouterr().out)
    assert facts['milestones']['CALLBACK_COMPLETE'] >= facts['milestones']['CLEANUP_RELEASE']
    assert facts['milestones']['DRAIN_FINISH'] >= facts['milestones']['CALLBACK_COMPLETE']
    assert facts['latest']['pending_futures'] == facts['latest']['pending_native_records'] == 0
