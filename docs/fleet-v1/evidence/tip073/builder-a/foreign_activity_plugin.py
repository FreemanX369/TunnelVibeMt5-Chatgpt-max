"""Actual foreign journal/proxy calls; existing owned assertions stay exact."""
import json
import os
from pathlib import Path
from queue import Queue
import threading
import time

import pytest

ROWS = []

@pytest.fixture(autouse=True)
def foreign_activity(request, monkeypatch):
    if 'test_long_fixture_valid_finite_schedule_requires_aggregate_observation' not in request.node.name:
        yield
        return
    import test_tip064_integration as module
    from vibemql5.fleet.job_journal import NodeJobJournal, JournalError
    from vibemql5.fleet.transport import NodeRpcProxy
    run = module.run_long_fixture

    def with_foreign_activity(*args, **kwargs):
        create = module.runtime
        def owned_runtime(*runtime_args, **runtime_kwargs):
            value = create(*runtime_args, **runtime_kwargs)
            foreign = NodeJobJournal(value[2].root / 'owned-foreign-control.sqlite', initialize=True,
                                     max_records=20, max_payload_bytes=262144, wait_ms=1000)
            missing = 'fjob_' + 'f' * 32
            def observed(kind, callback, expected):
                begun = time.monotonic()
                try:
                    callback()
                except JournalError as error:
                    assert error.code == expected
                    ROWS.append({'stage': kind, 'code': error.code,
                                 'elapsed_ms': int((time.monotonic() - begun) * 1000)})
                else:
                    pytest.fail('foreign invalid callback unexpectedly succeeded')
            try:
                observed('FOREIGN_BEGIN', lambda: foreign.begin_effect(missing, 'deploy', 'snapshot_prepare:0001',
                    start_authorize=None, authorization_verifier=None), 'JOB_UNKNOWN')
                observed('FOREIGN_COMPLETE', lambda: foreign.complete_effect(missing, 'deploy', 'snapshot_prepare:0001',
                    None), 'NATIVE_AUTHORIZATION_UNVERIFIED')
                observed('FOREIGN_OUTCOME', lambda: foreign._outcome({'global_job_id': missing}, 'UNKNOWN',
                    {'reason_code': 'OWNED_FOREIGN_CONTROL'}), 'JOB_UNKNOWN')
            finally:
                foreign.close()
            queue = Queue(maxsize=1)
            proxy = NodeRpcProxy(value[1], queue)
            errors = []
            def answer():
                try:
                    kind, payload, deadline, future = queue.get(timeout=1)
                    assert kind == 'DOMAIN_RESULT' and payload == {'owned_control': True}
                    assert future.set_running_or_notify_cancel()
                    future.set_result({'status': 'HARMLESS_QUEUE_CONTROL'})
                except BaseException as error:
                    errors.append(error)
            worker = threading.Thread(target=answer, daemon=True)
            worker.start()
            result = proxy._request('DOMAIN_RESULT', {'owned_control': True})
            worker.join(timeout=1)
            assert not worker.is_alive() and not errors
            assert result == {'status': 'HARMLESS_QUEUE_CONTROL'}
            ROWS.append({'stage': 'FOREIGN_RPC', 'kind': 'DOMAIN_RESULT', 'result': result['status']})
            return value
        monkeypatch.setattr(module, 'runtime', owned_runtime)
        return run(*args, **kwargs)
    monkeypatch.setattr(module, 'run_long_fixture', with_foreign_activity)
    yield

def pytest_sessionfinish(session, exitstatus):
    Path(os.environ['OWNED_FOREIGN_RECEIPT']).write_text(json.dumps({
        'schema': 'owned-foreign-activity/1', 'exit_status': exitstatus, 'rows': ROWS}, indent=2) + '\n')
