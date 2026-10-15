"""Qualification of external observer contracts; no production/native execution."""
import json
from types import SimpleNamespace

import pytest
from observer import Observer, error_facts, facts, pytest_runtest_call


def test_default_plugin_has_no_application_import_or_mutation():
    item = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: None),
                           module=SimpleNamespace(__name__='test_tip064_capacity_https'), nodeid='PRIVATE_NODEID')
    hook = pytest_runtest_call(item)
    assert next(hook) is None
    with pytest.raises(StopIteration): next(hook)


def test_observer_preserves_original_return_and_single_predicate_read():
    observer = Observer()
    result, calls = object(), []
    assert observer.observe('EXECUTE', lambda: result)() is result
    predicate = observer.predicate(lambda: calls.append(True) or True)
    assert predicate() is True and calls == [True]
    assert [row['stage'] for row in observer.rows] == ['EXECUTE', 'EXECUTE', 'PREDICATE']


@pytest.mark.parametrize('kind', [RuntimeError, KeyboardInterrupt])
def test_observer_preserves_exception_identity_cause_context_notes(kind):
    observer = Observer()
    cause, context, fault = RuntimeError('SECRET_CAUSE'), RuntimeError('SECRET_CONTEXT'), kind('SECRET_FAULT')
    fault.__cause__, fault.__context__ = cause, context
    fault.add_note('SECRET_NOTE')
    def original(): raise fault
    with pytest.raises(kind) as caught: observer.observe('EXECUTE', original)()
    assert caught.value is fault and fault.__cause__ is cause and fault.__context__ is context
    assert fault.__notes__ == ['SECRET_NOTE']
    assert 'SECRET' not in json.dumps(observer.snapshot())


def test_privacy_caps_and_original_grant_fields_only():
    observer = Observer(limit=3)
    payload = {'body': {'issued_ms': 10, 'expires_ms': 20, 'phase': 'start',
                       'secret': 'SECRET', 'state': 'UNKNOWN', 'reason_code': 'PRIVATE_TOKEN'}}
    assert facts(payload) == {'issued_ms': 10, 'expires_ms': 20, 'phase': 'start', 'state': 'UNKNOWN', 'code': 'OTHER'}
    for _ in range(20): observer.record('EXECUTE', 'RETURN', **facts(payload), arbitrary='SECRET')
    summary = observer.snapshot()
    assert len(summary['rows']) == 3 and summary['rows_dropped'] == 17
    assert 'SECRET' not in json.dumps(summary) and 'PRIVATE_TOKEN' not in json.dumps(summary)
    assert summary['observer_errors'] == 0


def test_diagnostic_record_failure_does_not_replace_original_outcome():
    observer, fault = Observer(), RuntimeError('ORIGINAL')
    # Fault only the observer's private clock, never stdlib/product clocks.
    observer.clock = lambda: (_ for _ in ()).throw(RuntimeError('DIAGNOSTIC'))
    assert observer.observe('EXECUTE', lambda: 7)() == 7
    def failed(): raise fault
    with pytest.raises(RuntimeError) as caught: observer.observe('EXECUTE', failed)()
    assert caught.value is fault
    assert observer.observer_errors == 4


def test_unknown_code_and_error_strings_are_not_rendered():
    fault = RuntimeError('SECRET')
    fault.code = 'PRIVATE_TOKEN'
    assert error_facts(fault) == {'exception_type': 'RuntimeError', 'code': 'OTHER'}
    assert facts({'issued_ms': True, 'phase': 'PRIVATE', 'now_ms': -1}) == {'phase': 'OTHER'}


def test_broken_exception_attributes_do_not_mask_original():
    class BrokenFault(RuntimeError):
        def __getattribute__(self, name):
            if name == '__dict__': raise RuntimeError('PRIVATE_DIAGNOSTIC')
            return super().__getattribute__(name)
    observer, fault = Observer(), BrokenFault('PRIVATE_PRIMARY')
    def original(): raise fault
    with pytest.raises(BrokenFault) as caught: observer.observe('EXECUTE', original)()
    assert caught.value is fault and observer.observer_errors == 1
    assert 'PRIVATE' not in json.dumps(observer.snapshot())


def test_selected_hook_output_write_failure_restores_binding_and_original_calls(monkeypatch, tmp_path):
    import observer as module
    original_calls, holder = [], SimpleNamespace()
    def original():
        original_calls.append(True)
        return 7
    holder.call = original
    def fake_bind(observed, stack, selected_module):
        stack.enter_context(module.patch.object(holder, 'call', observed.observe('EXECUTE', holder.call)))
    monkeypatch.setattr(module, 'bind', fake_bind)
    item = SimpleNamespace(nodeid=next(iter(module.CASE_IDS)), module=SimpleNamespace(),
        config=SimpleNamespace(getoption=lambda _: str(tmp_path / 'missing-parent' / 'observations.jsonl'),
                               pluginmanager=SimpleNamespace(get_plugin=lambda _: None)))
    hook = module.pytest_runtest_call(item)
    assert next(hook) is None
    assert holder.call() == 7 and original_calls == [True]
    with pytest.raises(StopIteration): next(hook)
    assert holder.call is original
    assert not (tmp_path / 'missing-parent').exists()


def test_binding_failure_blocks_original_and_restores_partial_patch(monkeypatch, tmp_path):
    import observer as module
    holder, calls = SimpleNamespace(), []
    def original(): calls.append(True)
    holder.call = original
    def failed_bind(observed, stack, selected_module):
        stack.enter_context(module.patch.object(holder, 'call', lambda: 9))
        raise RuntimeError('PRIVATE_BINDING_FAULT')
    monkeypatch.setattr(module, 'bind', failed_bind)
    item = SimpleNamespace(nodeid=next(iter(module.CASE_IDS)), module=SimpleNamespace(),
        config=SimpleNamespace(getoption=lambda _: str(tmp_path / 'observations.jsonl')))
    hook = module.pytest_runtest_call(item)
    with pytest.raises(pytest.fail.Exception) as caught: next(hook)
    assert str(caught.value) == 'TIP088_DIAGNOSTIC_BINDING_BLOCKED'
    assert holder.call is original and calls == []
    assert not (tmp_path / 'observations.jsonl').exists()
