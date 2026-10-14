"""Logical worker provenance on one actually reused disposable executor thread."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_tip077_capacity_entry_watchdog import AuthorizationScopeProbe


@pytest.mark.parametrize('fails', [False, True])
def test_reused_thread_clears_logical_marker_and_preserves_original_verifier(fails):
    probe, result, verifier = AuthorizationScopeProbe(), object(), object()
    error, cause = RuntimeError('ORIGINAL_VERIFY'), RuntimeError('ORIGINAL_CAUSE')
    error.add_note('original note')
    calls = []
    def original(actual_verifier, grant, **binding):
        calls.append((actual_verifier, grant, binding))
        if grant == 'error': raise error from cause
        return result
    def first():
        with probe.native_entry(1, 'first'):
            assert probe.verify(original, verifier, 'grant', phase='reserve', global_job_id='first') is result
        with probe.native_entry(2, 'second'):
            if fails:
                with pytest.raises(RuntimeError) as raised:
                    with probe.native_entry(3, 'third'):
                        probe.verify(original, verifier, 'error', phase='start', global_job_id='third')
                assert raised.value is error and error.__cause__ is cause and error.__notes__ == ['original note']
            else:
                with probe.native_entry(3, 'third'):
                    assert probe.verify(original, verifier, 'grant', phase='start', global_job_id='third') is result
            assert probe.verify(original, verifier, 'grant', phase='start', global_job_id='second') is result
    def reused():
        assert probe.verify(original, verifier, 'grant', phase='reserve', global_job_id='third') is result
    def reentered_first():
        with probe.native_entry(3, 'first'):
            assert probe.verify(original, verifier, 'grant', phase='reserve', global_job_id='first') is result
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(first).result(timeout=5)
        executor.submit(reentered_first).result(timeout=5)
        executor.submit(reused).result(timeout=5)
    assert len(calls) == 5 and all(call[0] is verifier for call in calls)
    assert [row['entry'] for row in probe.rows] == ([1, 2, 3, 0] if fails else [1, 3, 2, 3, 0])
    assert [row['cohort_binding'] for row in probe.rows] == (
        ['FIRST', 'SECOND', 'FIRST', 'UNKNOWN'] if fails else ['FIRST', 'OUTSIDE', 'SECOND', 'FIRST', 'UNKNOWN'])
    assert all(row['binding_match'] is True for row in probe.rows[:-1])
    assert probe.rows[-1] == {'entry': 0, 'phase': 'reserve', 'binding_match': None, 'cohort_binding': 'UNKNOWN'}
    assert probe.dropped == 0


def test_broken_probe_record_and_publish_preserve_original_result_and_error():
    probe, result, verifier, calls = AuthorizationScopeProbe(), object(), object(), []
    class BrokenRows(list):
        def append(self, row): pytest.fail('CONTROLLED_DIAGNOSTIC_RECORD')
    probe.rows = BrokenRows()
    def original(actual_verifier, grant, **binding):
        calls.append((actual_verifier, grant, binding))
        return result
    with probe.native_entry(1, 'first'):
        assert probe.verify(original, verifier, 'grant', phase='reserve', global_job_id='first') is result
    assert len(calls) == 1 and calls[0][0] is verifier and probe.observation_errors == 1
    primary, cause = RuntimeError('ORIGINAL_TEST'), RuntimeError('ORIGINAL_CAUSE')
    primary.add_note('original note')
    def broken_printer(*args, **kwargs): pytest.fail('CONTROLLED_DIAGNOSTIC_PUBLISH')
    with pytest.raises(RuntimeError) as raised:
        try: raise primary from cause
        finally: probe.publish(printer=broken_printer)
    assert raised.value is primary and primary.__cause__ is cause and primary.__notes__ == ['original note']
    assert probe.observation_errors == 2
