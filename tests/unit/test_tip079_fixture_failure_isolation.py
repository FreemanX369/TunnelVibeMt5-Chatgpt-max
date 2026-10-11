"""Fixture schedule isolation and original pre-callback evidence; no physical PASS."""
from types import SimpleNamespace
import json
import threading
import time

import pytest
import test_tip064_capacity_https as capacity
import test_tip064_integration as integration
from test_tip064_integration import project_node, composed_service, tls_files
from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from vibemql5.fleet.native import SyntheticNativeAdapter
from vibemql5.fleet.job_journal import NodeJobJournal
from long_native_fixture_observations import LongFixtureNativeObservations


def test_actual_one_second_guard_timeout_with_broken_record_keeps_unknown_armed(project_node, monkeypatch):
    signed, *_ = capacity.signed_roster(project_node, Ed25519PrivateKey.generate())
    coordinator = ScopedResourceCoordinator._for_fixture(project_node['root'], signed['body'], initialize=True)
    observer = capacity.ScopeFixtureObservations(coordinator)
    diagnostic, restoration = RuntimeError('DIAGNOSTIC'), RuntimeError('RESTORATION')
    diagnostic.add_note('diagnostic note'); restoration.add_note('restoration note')
    restore = observer.restore
    monkeypatch.setattr(observer, 'record', lambda *args, **kwargs: (_ for _ in ()).throw(diagnostic))
    def broken_restore():
        restore(); raise restoration
    monkeypatch.setattr(observer, 'restore', broken_restore)
    acquired, release = threading.Event(), threading.Event()
    owner_errors, faults = [], []
    def owner():
        try:
            with coordinator.transaction():
                acquired.set()
                assert release.wait(3), 'CONTROLLED_OWNER_RELEASE_NOT_OBSERVED'
        except BaseException as error: owner_errors.append(error)
    terminal = signed['body']['terminals'][0]
    thread = None
    try:
        with coordinator.execution('controlled-guard', kind='tester', terminal_id=terminal['terminal_id'],
                terminal_generation=terminal['terminal_generation'], wait_ms=1000) as scope:
            armed = scope.arm()
            thread = threading.Thread(target=owner)
            thread.start(); assert acquired.wait(3)
            began = time.monotonic()
            try: scope.close_zero_attempt(armed)
            except BaseException as error:
                faults.append(error)
                wait = time.monotonic()-began
                assert isinstance(error, TimeoutError) and str(error).startswith('JOB_METADATA_LOCK_TIMEOUT: ')
                release.set(); thread.join(3); assert not thread.is_alive()
                raise
            else: pytest.fail('actual contested guard unexpectedly acquired')
    except BaseException as error:
        assert faults and error is faults[0]
    finally:
        release.set()
        if thread is not None: thread.join(3)
        try: observer.restore()
        except BaseException as error: faults.append(error)
    for error in observer.observation_errors:
        if not any(error is prior for prior in faults): faults.append(error)
    assert not owner_errors and thread is not None and not thread.is_alive()
    assert tuple(faults) == (faults[0], restoration, diagnostic)
    assert 0.9 <= wait < 3
    retained = scope.load()
    assert retained['phase'] == 'ARMED' and retained['status'] == 'UNKNOWN'
    assert not {'transaction', '_db', '_validate'} & coordinator.__dict__.keys()
    failure = observer.snapshot()['last_failure']
    assert failure['owner_count'] == 0 and failure['owner_status'] == 'UNKNOWN'


def native_output(output):
    values = [json.loads(line.removeprefix('LONG_NATIVE_FIXTURE ')) for line in output.splitlines()
              if line.startswith('LONG_NATIVE_FIXTURE ')]
    assert len(values) == 1
    return values[0]


@pytest.mark.parametrize('composed_service', [integration.LONG_FIXTURE_PROFILE], indirect=True)
@pytest.mark.parametrize('mode', ['original-callback', 'controlled-precallback'])
def test_long_native_observation_preserves_original_callback_and_precallback_uncertainty(
        project_node, composed_service, monkeypatch, mode, capsys):
    created, resources = [], []
    observer_init, runtime = LongFixtureNativeObservations.__init__, integration.runtime
    def observed_init(self):
        observer_init(self); created.append(self)
    def owned_runtime(*args, **kwargs):
        result = runtime(*args, **kwargs)
        resources.extend([result[3].principals, *result[4:]])
        return result
    monkeypatch.setattr(LongFixtureNativeObservations, '__init__', observed_init)
    monkeypatch.setattr(integration, 'runtime', owned_runtime)
    fault, cause = RuntimeError('CONTROLLED_PRE_CALLBACK'), RuntimeError('ORIGINAL_CAUSE')
    fault.add_note('original pre-callback note')
    injected = []
    if mode == 'original-callback':
        integration.test_long_fixture_restore_failure_cannot_mask_original_callback(
            project_node, composed_service, monkeypatch)
    else:
        admit = SyntheticNativeAdapter._admit
        def failed_admit(self, request, phase, exact_fence=None):
            result = admit(self, request, phase, exact_fence)
            if phase == 'start' and not injected:
                injected.append(True); raise fault from cause
            return result
        callback, restoration = RuntimeError('CALLBACK'), RuntimeError('RESTORATION')
        callback.add_note('callback note'); restoration.add_note('restoration note')
        restore = integration.FixtureAuthorizationDiagnostics.restore
        def broken_restore(self):
            restore(self); assert not self._restores; raise restoration
        monkeypatch.setattr(SyntheticNativeAdapter, '_admit', failed_admit)
        monkeypatch.setattr(NodeJobJournal, 'begin_effect', lambda *args, **kwargs: (_ for _ in ()).throw(callback))
        monkeypatch.setattr(integration.FixtureAuthorizationDiagnostics, 'restore', broken_restore)
        with pytest.raises(BaseExceptionGroup) as observed:
            integration.run_long_fixture(project_node, composed_service, monkeypatch)
        timeout, restored = observed.value.exceptions
        assert isinstance(timeout, AssertionError) and 'LONG_FIXTURE_WORKER_RETURN_TIMEOUT' in str(timeout)
        assert restored is restoration and restoration.__notes__ == ['restoration note']
        assert injected == [True] and fault.__cause__ is cause and fault.__notes__ == ['original pre-callback note']
    observer = created[0]
    assert len(created) == 1 and not observer.originals and not observer.observation_errors
    facts = native_output(capsys.readouterr().out)
    assert any(row.get('native_state') == 'UNKNOWN' for row in facts['rows'])
    assert all(row['calls'] == row['returns']+row['errors'] for row in facts['delegate_counts'].values())
    if mode == 'controlled-precallback':
        assert any(error is fault for error in observer.errors) and any(error is cause for error in observer.errors)
        assert 'FIXTURE_CALLBACK' not in facts['delegate_counts']
    else:
        original = [error for error in observer.errors if type(error) is RuntimeError and str(error) == 'CALLBACK']
        assert len(original) == 1 and original[0].__notes__ == ['callback note']
    for resource in resources:
        assert resource._lock is None
        if type(resource).__name__ == 'NodePrincipalRuntime': assert not hasattr(resource, '_db')
        else: assert hasattr(resource, '_db') and resource._db is None


def test_native_observer_caps_safe_rows_identities_and_cyclic_contexts():
    observer = LongFixtureNativeObservations()
    for _ in range(40):
        error = RuntimeError('PRIVATE_PATH_TOKEN'); error.__context__ = error
        observer.record('ADMIT', 'ERROR', time.monotonic(), error)
    for malformed in (None, [], {}, 'PRIVATE_PATH_TOKEN'):
        observer.record(malformed, 'ERROR', time.monotonic(), RuntimeError('PRIVATE_PATH_TOKEN'))
    observer.record('EXECUTE', 'RETURNED', time.monotonic(), result={'state': []})
    facts = observer.snapshot()
    assert len(facts['rows']) == len(facts['error_rows']) == len(observer.errors) == 32
    assert facts['row_total'] == 41 and facts['rows_dropped'] == 9
    assert facts['error_row_total'] == 40 and facts['error_rows_dropped'] == 8
    assert facts['error_identities_dropped'] == 8 and not observer.observation_errors
    assert all(row['depth'] == 0 for row in facts['error_rows'])
    assert 'PRIVATE_PATH_TOKEN' not in json.dumps(facts) and 'native_state' not in facts['rows'][-1]


def test_native_observer_restores_instance_attributes_and_keeps_broken_record_error(monkeypatch):
    observer = LongFixtureNativeObservations()
    original, diagnostic = RuntimeError('ORIGINAL'), RuntimeError('DIAGNOSTIC')
    original.add_note('original note'); diagnostic.add_note('diagnostic note')
    class Owner:
        def inherited(self): return 7
    owner = Owner()
    def prior(): raise original
    owner.existing = prior
    observer.install(owner, 'existing', 'ADMIT')
    observer.install(owner, 'inherited', 'LOAD_JOB')
    def broken_record(*args): raise diagnostic
    monkeypatch.setattr(observer, 'record', broken_record)
    with pytest.raises(RuntimeError) as observed: owner.existing()
    assert observed.value is original and original.__notes__ == ['original note']
    assert owner.inherited() == 7 and observer.observation_errors == [diagnostic]
    observer.restore()
    assert owner.existing is prior and 'inherited' not in owner.__dict__ and not observer.originals
    assert diagnostic.__notes__ == ['diagnostic note']
