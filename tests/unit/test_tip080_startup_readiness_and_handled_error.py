"""Original handled execute errors remain evidence, with original budgets."""
from types import SimpleNamespace
import json
import time

import pytest
import test_tip064_integration as integration
from test_tip064_integration import project_node, composed_service, tls_files
from long_native_fixture_observations import LongFixtureNativeObservations
from vibemql5.fleet.native_authorization import NativeAuthorizationVerifier
from vibemql5.fleet.job_journal import NodeJobJournal


@pytest.mark.parametrize('composed_service', [integration.LONG_FIXTURE_PROFILE], indirect=True)
@pytest.mark.parametrize('mode', ['controlled-verify-error', 'real-signed-start-expiry'])
def test_handled_execute_error_before_start_keeps_identity_unknown_and_original_return_three(
        project_node, composed_service, monkeypatch, mode, capsys):
    created, runtimes, true_authorization_attrs, verification_calls, outcome_calls, expired = [], [], [], [], [], []
    init, runtime, verify, outcome = LongFixtureNativeObservations.__init__, integration.runtime, NativeAuthorizationVerifier.verify, NodeJobJournal._outcome
    fault, cause = RuntimeError('CONTROLLED_VERIFY_ERROR'), RuntimeError('ORIGINAL_CAUSE')
    fault.add_note('original verify note')
    def observed_init(self):
        init(self); created.append(self)
    def observed_verify(self, signed, **expected):
        verification_calls.append(expected['phase'])
        try: result = verify(self, signed, **expected)
        except BaseException as error:
            if mode == 'real-signed-start-expiry' and expected['phase'] == 'start': expired.append(error)
            raise
        if mode == 'controlled-verify-error' and expected['phase'] == 'start': raise fault from cause
        return result
    def observed_outcome(self, record, state, result):
        outcome_calls.append(state)
        return outcome(self, record, state, result)
    def owned_runtime(*args, **kwargs):
        result = runtime(*args, **kwargs); runtimes.append(result)
        true_authorization_attrs.extend(kwargs['authorization_diagnostics']._restores)
        if mode == 'real-signed-start-expiry':
            proxy, request = result[2].rpc_proxy, result[2].rpc_proxy._request
            def held_request(kind, payload):
                signed = request(kind, payload)
                if kind == 'START_AUTHORIZE' and payload['command']['authorization_phase'] == 'start':
                    assert signed['body']['expires_ms'] - signed['body']['issued_ms'] == 1000
                    # Named negative: hold an already signed response until real expiry.
                    time.sleep(1.05)
                return signed
            monkeypatch.setattr(proxy, '_request', held_request)
        return result
    monkeypatch.setattr(LongFixtureNativeObservations, '__init__', observed_init)
    monkeypatch.setattr(NativeAuthorizationVerifier, 'verify', observed_verify)
    monkeypatch.setattr(NodeJobJournal, '_outcome', observed_outcome)
    monkeypatch.setattr(integration, 'runtime', owned_runtime)
    callback = RuntimeError('CONTROLLED_CALLBACK_FAILURE'); callback.add_note('original callback note')
    monkeypatch.setattr(NodeJobJournal, 'begin_effect', lambda *args, **kwargs: (_ for _ in ()).throw(callback))
    with pytest.raises(AssertionError) as observed:
        integration.run_long_fixture(project_node, composed_service, monkeypatch)
    assert 'LONG_FIXTURE_WORKER_RETURN_TIMEOUT' in str(observed.value)
    assert verification_calls == ['reserve', 'start'] and outcome_calls == ['UNKNOWN']
    observer, result = created[0], runtimes[0]
    assert len(created) == len(runtimes) == len(true_authorization_attrs) == 1
    assert not observer.originals and not observer.observation_errors
    facts = observer.snapshot()
    assert facts['handled_signal_total'] == 1 and len(facts['handled_signals']) == 1
    assert 'EXECUTE_HANDLED_ERROR' not in facts['delegate_counts']
    assert facts['delegate_counts']['EXECUTE'] == {'calls': 1, 'returns': 1, 'errors': 0}
    assert 'START_RESERVED' not in facts['delegate_counts'] and 'FIXTURE_CALLBACK' not in facts['delegate_counts']
    error = observer.errors[facts['handled_signals'][0]['error_index']]
    if mode == 'controlled-verify-error':
        assert error is fault and fault.__cause__ is cause and fault.__notes__ == ['original verify note']
    else:
        assert len(expired) == 1 and error is expired[0] and error.code == 'NATIVE_AUTHORIZATION_EXPIRED'
        assert facts['handled_signals'][0]['code'] == 'NATIVE_AUTHORIZATION_EXPIRED'
    verifier, true_clock, prior_verify = true_authorization_attrs[0]
    assert verifier.clock is true_clock
    if prior_verify is None: assert 'verify' not in verifier.__dict__
    else: assert verifier.verify is prior_verify
    assert '_outcome' not in result[4].__dict__ and not result[3].has_pending_work()
    assert 'step' not in result[2].__dict__
    for owner in (result[3].principals, *result[4:]):
        assert owner._lock is None
        if type(owner).__name__ == 'NodePrincipalRuntime': assert not hasattr(owner, '_db')
        else: assert hasattr(owner, '_db') and owner._db is None
    output = capsys.readouterr().out
    rows = [json.loads(line.removeprefix('LONG_NATIVE_FIXTURE ')) for line in output.splitlines()
            if line.startswith('LONG_NATIVE_FIXTURE ')]
    assert rows == [facts]


def test_handled_signal_is_bounded_distinct_from_delegates_and_restores_both_outcome_forms(monkeypatch):
    original, cause, diagnostic = RuntimeError('PRIVATE_PATH_TOKEN'), RuntimeError('PRIVATE_CAUSE'), RuntimeError('DIAGNOSTIC')
    original.add_note('original note'); diagnostic.add_note('diagnostic note')
    for existing in (False, True):
        calls, observer = [], LongFixtureNativeObservations()
        class Journal:
            def execute(self): return None
            def _outcome(self, record, state, result):
                calls.append(state); return {'state': state, 'result': result}
        journal = Journal()
        prior = None
        if existing:
            def prior(record, state, result):
                calls.append(state); return {'state': state, 'result': result}
            journal._outcome = prior
        adapter = SimpleNamespace(**{name:(lambda *args, **kwargs: None) for name,_ in observer.METHODS})
        observer.bind(SimpleNamespace(native=journal, native_adapter=adapter))
        try: raise original from cause
        except RuntimeError:
            assert journal._outcome({}, 'SUCCEEDED', {'reason_code': 'EXECUTION_OUTCOME_UNKNOWN'})['state'] == 'SUCCEEDED'
            assert journal._outcome({}, 'UNKNOWN', {'reason_code': 'OTHER'})['state'] == 'UNKNOWN'
            assert observer.handled_signal_total == 0
            assert journal._outcome({}, 'UNKNOWN', {'reason_code': 'EXECUTION_OUTCOME_UNKNOWN'})['state'] == 'UNKNOWN'
            assert observer.handled_signal_total == 1
            def broken_signal(error): raise diagnostic
            monkeypatch.setattr(observer, 'record_handled', broken_signal)
            assert journal._outcome({}, 'UNKNOWN', {'reason_code': 'EXECUTION_OUTCOME_UNKNOWN'})['state'] == 'UNKNOWN'
        assert observer.observation_errors == [diagnostic]
        assert calls == ['SUCCEEDED', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN'] and observer.counts == {}
        assert any(error is original for error in observer.errors) and any(error is cause for error in observer.errors)
        observer.restore()
        if existing: assert journal._outcome is prior
        else: assert '_outcome' not in journal.__dict__
        assert 'execute' not in journal.__dict__ and not observer.originals
        # The real signal recorder remains finite with malformed or cyclic input.
        monkeypatch.undo()
        for _ in range(40):
            error = RuntimeError('PRIVATE_PATH_TOKEN'); error.__context__ = error
            observer.record_handled(error)
        for malformed in (None, [], {}, 'PRIVATE_PATH_TOKEN'): observer.record_handled(malformed)
        facts = observer.snapshot()
        assert len(facts['handled_signals']) == len(facts['error_rows']) == len(observer.errors) == 32
        assert facts['handled_signal_total'] == 41 and facts['handled_signals_dropped'] == 9
        assert facts['delegate_counts'] == {} and facts['row_total'] == 0
        assert 'PRIVATE' not in json.dumps(facts)
        assert original.__cause__ is cause and original.__notes__ == ['original note']
        assert diagnostic.__notes__ == ['diagnostic note']
