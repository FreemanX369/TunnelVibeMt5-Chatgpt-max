"""Owned diagnostic only: gate one fresh-intent boundary; retain real deadlines."""
import json
import os
from pathlib import Path
import threading
import time

import pytest

GATE = threading.Event()
ROWS = []
RUNTIMES = []
ORIGIN = time.monotonic()


def record(stage, **facts):
    ROWS.append({'elapsed_ms': int((time.monotonic() - ORIGIN) * 1000), 'stage': stage, **facts})


@pytest.fixture(autouse=True)
def bounded_boundary_gate(request, monkeypatch):
    if 'test_long_fixture_valid_finite_schedule_requires_aggregate_observation' not in request.node.name:
        yield
        return
    import test_tip064_integration as module
    from vibemql5.fleet.job_journal import NodeJobJournal
    run, runtime = module.run_long_fixture, module.runtime
    index = 0 if request.node.callspec.params['seconds'] == 5 else 1

    def owned_runtime(*args, **kwargs):
        value = runtime(*args, **kwargs)
        RUNTIMES.append((index, value))
        record('RUNTIME', test_index=index)
        return value

    def gated_run(*args, **kwargs):
        begin, outcome = NodeJobJournal.begin_effect, NodeJobJournal._outcome
        gated = []

        def held_begin(journal, job, phase, event, **binding):
            if index == 0 and not gated:
                gated.append(True)
                record('MODELED_GATE_ENTER', test_index=index, job_id=job, event=event)
                assert GATE.wait(20), 'OWNED_CAUSAL_GATE_TIMEOUT'
                record('MODELED_GATE_EXIT', test_index=index, job_id=job)
            return begin(journal, job, phase, event, **binding)

        def observed_outcome(journal, job, state, result):
            runtime_owner = next((selected for selected, value in RUNTIMES if value[4] is journal), None)
            record('OUTCOME_ENTER', test_index=index, runtime_owner=runtime_owner,
                   job_id=job['global_job_id'], state=state,
                   reason_code=result.get('reason_code') if isinstance(result, dict) else None,
                   evidence=result.get('evidence') if isinstance(result, dict) else None)
            return outcome(journal, job, state, result)

        monkeypatch.setattr(NodeJobJournal, '_outcome', observed_outcome)
        if index == 0:
            monkeypatch.setattr(NodeJobJournal, 'begin_effect', held_begin)
        else:
            record('NEXT_OBSERVER_INSTALLED', test_index=index)
            GATE.set()
        try:
            return run(*args, **kwargs)
        finally:
            record('CASE_RETURN', test_index=index)

    monkeypatch.setattr(module, 'runtime', owned_runtime)
    monkeypatch.setattr(module, 'run_long_fixture', gated_run)
    yield
    record('CASE_TEARDOWN', test_index=index)


def pytest_sessionfinish(session, exitstatus):
    GATE.set()
    deadline = time.monotonic() + 6
    for index, value in RUNTIMES:
        dispatcher = value[3]
        for row in list(dispatcher._futures.values()):
            try:
                row['future'].result(timeout=max(0, deadline - time.monotonic()))
            except BaseException as error:
                record('FINAL_WORKER_ERROR', test_index=index, error_type=type(error).__name__)
        record('FINAL_RETAINED', test_index=index,
               futures=len(dispatcher._futures), pending_records=len(dispatcher._native_records),
               futures_done=all(row['future'].done() for row in dispatcher._futures.values()))
    target = Path(os.environ['OWNED_CAUSAL_RECEIPT'])
    target.write_text(json.dumps({'schema': 'owned-causal-gate/1', 'modeled_boundary': True,
                                  'original_windows_cause': 'UNKNOWN', 'pytest_exit': exitstatus,
                                  'rows': ROWS}, indent=2) + '\n')
