"""Composed startup observation; the original five-second negative stays bounded."""
from pathlib import Path
from types import SimpleNamespace
import ast
import time

import pytest

import fleet_gateway_fixture as gateway
import test_tip064_integration as integration
from test_tip064_integration import project_node, tls_files
from vibemql5.fleet.domain import DomainJournal
from vibemql5.fleet.gateway_control import GatewayControlStore


def pad_owned_component(resource, began, minimum_seconds):
    """Own a returned constructor value until factory ExitStack registration."""
    try:
        time.sleep(max(0, minimum_seconds - (time.monotonic() - began)))
    except BaseException as original:
        try: resource.close()
        except BaseException as cleanup:
            raise BaseExceptionGroup('padding and owned close failed', [original, cleanup]) from None
        raise


def controlled_startup(tmp_path, tls_files, project_node, monkeypatch, *, original_five=False, minimum_seconds=2.7):
    state = {'components': [], 'resources': [], 'stops': [], 'invalid': [],
             'thread': None, 'startup_error': None, 'yielded': False,
             'original_assertions_completed': False, 'factory_calls': 0}
    control_init, domain_init = GatewayControlStore.initialize, DomainJournal.__init__
    start, stop = integration.start_gateway_fixture, gateway.stop_gateway_fixture

    def control_initialize(cls, *args, **kwargs):
        selected = Path(args[0]) == tmp_path / 'composed-control.sqlite'
        began = time.monotonic()
        result = control_init(*args, **kwargs)
        if selected:
            pad_owned_component(result, began, minimum_seconds)
        if selected:
            state['resources'].append(result)
            elapsed = time.monotonic() - began
            state['components'].append(elapsed)
            if elapsed >= 5:
                state['invalid'].append('CONTROL_COMPONENT_EXCEEDED_5S')
        return result

    def domain_initialize(self, *args, **kwargs):
        selected = (Path(args[0]) == tmp_path / 'composed-domain.sqlite'
                    and kwargs.get('role') == 'GATEWAY')
        began = time.monotonic()
        result = domain_init(self, *args, **kwargs)
        if selected:
            pad_owned_component(self, began, minimum_seconds)
        if selected:
            state['resources'].append(self)
            elapsed = time.monotonic() - began
            state['components'].append(elapsed)
            if elapsed >= 5:
                state['invalid'].append('DOMAIN_COMPONENT_EXCEEDED_5S')
        return result

    def observed_stop(stopped, thread, failures, **kwargs):
        state['thread'] = thread
        began = time.monotonic()
        try:
            return stop(stopped, thread, failures, **kwargs)
        finally:
            state['stops'].append((kwargs.get('timeout', 3), time.monotonic() - began,
                                   not thread.is_alive()))

    def observed_start(*args, **kwargs):
        original_factory = kwargs['controller_factory']
        state['requested_startup_seconds'] = kwargs['startup_timeout']
        assert kwargs['stop_timeout'] == 3
        def factory(address):
            state['factory_calls'] += 1
            result = original_factory(address)
            state['resources'].extend([result.domain.native, result.domain.principals])
            return result
        kwargs['controller_factory'] = factory
        if original_five:
            # Retain the unchanged generic gateway wrapper's original default.
            assert start.__kwdefaults__['startup_timeout'] == 5
            del kwargs['startup_timeout']
        state['actual_startup_seconds'] = kwargs.get('startup_timeout', 5)
        try:
            result = start(*args, **kwargs)
            state['thread'] = result[1]
            return result
        except BaseException as error:
            state['startup_error'] = error
            raise

    monkeypatch.setattr(GatewayControlStore, 'initialize', classmethod(control_initialize))
    monkeypatch.setattr(DomainJournal, '__init__', domain_initialize)
    monkeypatch.setattr(gateway, 'stop_gateway_fixture', observed_stop)
    monkeypatch.setattr(integration, 'stop_gateway_fixture', observed_stop)
    monkeypatch.setattr(integration, 'start_gateway_fixture', observed_start)
    request = SimpleNamespace(param=integration.LONG_FIXTURE_PROFILE.values[0],
        node=SimpleNamespace(name='test_long_fixture_preserves_callback_error_identity_and_cleanup'),
        fixturenames=[])
    fixture = integration.composed_service.__wrapped__(tmp_path, tls_files, request)
    outer, cleanup = None, None
    try:
        service = next(fixture)
        state['yielded'] = True
        assert service[0].policy.http_timeout_ms == service[0].policy.heartbeat_interval_ms == 5000
        integration.test_long_fixture_preserves_callback_error_identity_and_cleanup(
            project_node, service, monkeypatch, cleanup_fails=False)
        state['original_assertions_completed'] = True
    except BaseException as error:
        outer = error
    finally:
        try:
            fixture.close()
        except BaseException as error:
            cleanup = error
    if cleanup is not None:
        if outer is not None:
            raise BaseExceptionGroup('original fixture and cleanup errors', [outer, cleanup]) from None
        raise cleanup
    if outer is not None and not (original_five and isinstance(outer, TimeoutError)
                                  and str(outer) == 'GATEWAY_STARTUP_FIXTURE_TIMEOUT'):
        raise outer

    assert not state['invalid'] and state['factory_calls'] == 1
    assert len(state['components']) == 2 and all(minimum_seconds <= elapsed < 5 for elapsed in state['components'])
    resources = state['resources']
    assert sorted(type(resource).__name__ for resource in resources) == sorted(
        ['GatewayControlStore', 'DomainJournal', 'GatewayJobJournal', 'GatewayPrincipalAuthority'])
    for resource in resources:
        assert hasattr(resource, '_lock') and resource._lock is None
        if type(resource).__name__ == 'GatewayPrincipalAuthority':
            assert not hasattr(resource, '_db')
        else:
            assert hasattr(resource, '_db') and resource._db is None
    assert state['thread'] is not None and not state['thread'].is_alive()
    assert len(state['stops']) == 1
    stop_seconds, stop_elapsed, joined = state['stops'][0]
    assert stop_seconds == 3 and stop_elapsed < 3 and joined
    state['outer_error'] = outer
    return state


def test_positive_composed_startup_runs_original_callback_assertions_after_finite_factory_schedule(
        tmp_path, tls_files, project_node, monkeypatch):
    state = controlled_startup(tmp_path, tls_files, project_node, monkeypatch)
    assert state['requested_startup_seconds'] == state['actual_startup_seconds'] == 10
    assert state['startup_error'] is None and state['original_assertions_completed']


def test_original_five_second_composed_startup_remains_bounded_negative_with_owned_cleanup(
        tmp_path, tls_files, project_node, monkeypatch):
    state = controlled_startup(tmp_path, tls_files, project_node, monkeypatch, original_five=True)
    error = state['outer_error']
    assert error is state['startup_error'] and isinstance(error, TimeoutError)
    assert str(error) == 'GATEWAY_STARTUP_FIXTURE_TIMEOUT'
    facts = ast.literal_eval(error.__notes__[0])
    assert facts['timeout_seconds'] == 5 and facts['server_thread_alive']
    assert facts['server_failure_count'] == 0
    assert not state['yielded'] and not state['original_assertions_completed']


def test_zero_schedule_runs_original_callback_assertions_with_original_startup_five(
        tmp_path, tls_files, project_node, monkeypatch):
    state = controlled_startup(tmp_path, tls_files, project_node, monkeypatch,
                               original_five=True, minimum_seconds=0)
    assert state['requested_startup_seconds'] == 10 and state['actual_startup_seconds'] == 5
    assert state['startup_error'] is None and state['original_assertions_completed']


@pytest.mark.parametrize('kind', ['control', 'domain'])
@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_padding_interruption_closes_unregistered_real_constructor_and_preserves_errors(
        tmp_path, monkeypatch, kind, cleanup_fails):
    resource = (GatewayControlStore.initialize(tmp_path / 'control.sqlite', policy=integration.control_policy())
        if kind == 'control' else DomainJournal(tmp_path / 'domain.sqlite', initialize=True,
                                               role='GATEWAY', policy=integration.domain_policy()))
    original, cleanup = RuntimeError('PADDING_INTERRUPTION'), RuntimeError('OWNED_CLOSE_FAILURE')
    original.add_note('original padding note'); cleanup.add_note('original close note')
    close = resource.close
    def interrupted_sleep(seconds): raise original
    def failed_close():
        close(); raise cleanup
    monkeypatch.setattr(time, 'sleep', interrupted_sleep)
    if cleanup_fails: monkeypatch.setattr(resource, 'close', failed_close)
    with pytest.raises(BaseException) as observed:
        pad_owned_component(resource, time.monotonic(), 2.7)
    if cleanup_fails:
        assert isinstance(observed.value, BaseExceptionGroup)
        assert observed.value.exceptions == (original, cleanup)
    else: assert observed.value is original
    assert original.__notes__ == ['original padding note'] and cleanup.__notes__ == ['original close note']
    assert resource._db is None and resource._lock is None
