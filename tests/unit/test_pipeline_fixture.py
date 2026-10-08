"""Finite observer controls and shared-fixture compatibility regressions."""
from contextlib import contextmanager
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

import fleet_pipeline_fixture as module
from fleet_pipeline_fixture import PipelineObservation, TimedContext, pipeline_for_request


@pytest.mark.parametrize('name', sorted(module.CASES))
def test_optin_looks_up_exact_fixture_once(name):
    observer, calls = PipelineObservation(), []
    request = SimpleNamespace(node=SimpleNamespace(originalname=name, name=name + '[x]'),
        fixturenames=['composed_service', 'pipeline_diagnostics'],
        getfixturevalue=lambda name: calls.append(name) or observer)
    assert pipeline_for_request(request) is observer
    assert calls == ['pipeline_diagnostics']


@pytest.mark.parametrize('fake_request', [SimpleNamespace(),
    SimpleNamespace(node=SimpleNamespace(name='foreign'), fixturenames=['pipeline_diagnostics']),
    SimpleNamespace(node=SimpleNamespace(name=next(iter(module.CASES))), fixturenames=[]),
    SimpleNamespace(node=SimpleNamespace(originalname='foreign', name=next(iter(module.CASES))), fixturenames=['pipeline_diagnostics'])])
def test_foreign_manual_or_undeclared_request_never_looks_up_or_allocates(fake_request, monkeypatch):
    request = fake_request
    def forbidden(*args): raise AssertionError('unexpected observer allocation/lookup')
    request.getfixturevalue = forbidden
    monkeypatch.setattr(module, 'PipelineObservation', forbidden)
    assert pipeline_for_request(request) is None


@pytest.mark.parametrize('value', [None, object(), PipelineObservation(False)])
def test_lookup_rejects_invalid_or_disabled_observer(value):
    request = SimpleNamespace(node=SimpleNamespace(name=next(iter(module.CASES))),
        fixturenames=['pipeline_diagnostics'], getfixturevalue=lambda name: value)
    assert pipeline_for_request(request) is None


@pytest.mark.parametrize('kind', [RuntimeError, KeyboardInterrupt, SystemExit])
def test_fixture_lookup_failopen(kind):
    def lookup(name): raise kind('private')
    request = SimpleNamespace(node=SimpleNamespace(name=next(iter(module.CASES))),
        fixturenames=['pipeline_diagnostics'], getfixturevalue=lookup)
    assert pipeline_for_request(request) is None


def test_shared_fixture_keeps_three_arg_manual_factory_failure(tmp_path, monkeypatch):
    import test_tip064_integration as integration
    assert list(inspect.signature(integration.composed_service.__wrapped__).parameters) == ['tmp_path', 'tls_files', 'request']
    sentinel = RuntimeError('factory reached')
    calls = []
    def start(*args, **kwargs):
        calls.append(kwargs['startup_timeout'])
        raise sentinel
    monkeypatch.setattr(integration, 'start_gateway_fixture', start)
    generator = integration.composed_service.__wrapped__(tmp_path, ('ca', 'cert', 'key'), SimpleNamespace())
    with pytest.raises(RuntimeError) as caught: next(generator)
    assert caught.value is sentinel and calls == [5]


@pytest.mark.parametrize('kind', [RuntimeError, KeyboardInterrupt, SystemExit])
def test_call_preserves_original_exception_and_identity(kind):
    observer, error, calls = PipelineObservation(), kind('private text'), []
    def original(): calls.append(1); raise error
    with pytest.raises(kind) as caught: observer.call('CONTROL', 'STEP', original)
    assert caught.value is error and calls == [1]
    encoded = json.dumps(observer.summary())
    assert 'private text' not in encoded
    assert observer.rows['CONTROL'][-1]['outcome'] == module.category(error)


@pytest.mark.parametrize('fault', ['clock', 'record'])
@pytest.mark.parametrize('raises', [False, True])
def test_reporting_fault_preserves_call_return_or_exception(fault, raises):
    observer, token, error = PipelineObservation(), object(), ValueError('primary')
    def broken(*args, **kwargs): raise SystemExit('observer')
    setattr(observer, fault, broken)
    def original():
        if raises: raise error
        return token
    if raises:
        with pytest.raises(ValueError) as caught: observer.call('CONTROL', 'RPC', original)
        assert caught.value is error
    else: assert observer.call('CONTROL', 'RPC', original) is token
    assert observer.observer_error


@pytest.mark.parametrize('suppress', [False, True])
def test_context_protocol_passes_exact_error_and_suppression(suppress):
    observer, token, primary, events = PipelineObservation(), object(), ValueError('primary'), []
    class Original:
        def __enter__(self): events.append('enter'); return token
        def __exit__(self, kind, error, traceback):
            events.append((kind, error, traceback)); return suppress
    context = TimedContext(observer, Original(), 'CONTROL')
    assert context.__enter__() is token
    tb = object()
    assert context.__exit__(ValueError, primary, tb) is suppress
    assert events == ['enter', (ValueError, primary, tb)]


@pytest.mark.parametrize('stage', ['enter', 'exit'])
def test_context_original_error_identity(stage):
    observer, error = PipelineObservation(), RuntimeError('primary')
    class Original:
        def __enter__(self):
            if stage == 'enter': raise error
        def __exit__(self, *args): raise error
    context = TimedContext(observer, Original(), 'CONTROL')
    with pytest.raises(RuntimeError) as caught:
        with context: pass
    assert caught.value is error


def test_context_body_reporting_fault_does_not_mask_exit():
    observer, calls = PipelineObservation(), []
    def broken(*args, **kwargs): raise ValueError('observer')
    observer.record = broken
    class Original:
        def __enter__(self): return 42
        def __exit__(self, *args): calls.append(args); return True
    with TimedContext(observer, Original(), 'CONTROL') as value:
        assert value == 42
        raise RuntimeError('primary')
    assert len(calls) == 1 and calls[0][0] is RuntimeError and observer.observer_error


def test_span_restores_phase_on_body_and_reporting_failure():
    observer, error = PipelineObservation(), ValueError('primary')
    observer.record = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('observer'))
    with pytest.raises(ValueError) as caught:
        with observer.span('ROUND'): raise error
    assert caught.value is error and observer.phase == 'GENERAL' and observer.observer_error


def test_thread_identity_foreign_calls_delegate_without_recording():
    observer, token, results = PipelineObservation(), object(), []
    owned = observer.threads['CONTROL']
    assert owned is threading.current_thread()
    worker = threading.Thread(target=lambda: results.append(observer.call('CONTROL', 'RPC', lambda: token)))
    worker.start(); worker.join(timeout=1)
    assert not worker.is_alive() and results == [token]
    assert observer.rows['CONTROL'] == []
    observer.threads['CONTROL'] = SimpleNamespace(ident=owned.ident)
    assert not observer.owned('CONTROL')


def test_rows_finite_errors_outrank_round_and_cleanup():
    observer = PipelineObservation()
    error = RuntimeError('private')
    error.__cause__ = ValueError('private cause')
    chain = module.error_categories(error)
    for _ in range(20): observer.record('CONTROL', 'RPC', 'GENERAL', observer.now(), 'OTHER_ERROR', chain=chain)
    for _ in range(25): observer.record('CONTROL', 'ROUND', 'ROUND', observer.now(), 'RETURNED')
    for _ in range(25): observer.record('CONTROL', 'CLOSE', 'CLEANUP', observer.now(), 'RETURNED')
    observer.threads['GATEWAY'] = threading.current_thread()
    for _ in range(20): observer.record('GATEWAY', 'HANDLE', 'GENERAL', observer.now(), 'RETURNED')
    summary = observer.summary()
    assert len(summary['rows']) == 32 and summary['rows_truncated']
    assert all(row['outcome'] == 'OTHER_ERROR' and row['error_categories'] == ['OTHER_ERROR', 'OTHER_ERROR'] for row in observer.rows['CONTROL'])
    assert 'private' not in json.dumps(summary)
    assert not any(isinstance(value, BaseException) for value in vars(observer).values())


def test_exception_chain_bounded_cycles_and_suppression():
    errors = [ValueError(str(index)) for index in range(8)]
    for a, b in zip(errors, errors[1:]): a.__cause__ = b
    assert module.error_categories(errors[0]) == ('OTHER_ERROR',) * 4
    errors[0].__cause__ = errors[0]
    assert module.error_categories(errors[0]) == ('OTHER_ERROR',)
    errors[0].__cause__ = None; errors[0].__context__ = errors[1]; errors[0].__suppress_context__ = True
    assert module.error_categories(errors[0]) == ('OTHER_ERROR',)


def test_partial_setter_failure_restores_before_propagation():
    class Target:
        def __init__(self): object.__setattr__(self, 'value', 'original')
        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if value == 'replacement': raise ValueError('partial assignment')
    observer, target = PipelineObservation(), Target()
    observer.install(lambda: observer.patch(target, 'value', 'replacement'))
    assert target.value == 'original' and observer.restores == [] and observer.observer_error


def test_patch_restores_inherited_and_original_attributes():
    class Target:
        inherited = 'old'
    target, observer = Target(), PipelineObservation()
    target.own = 'old-own'
    observer.patch(target, 'inherited', 'new'); observer.patch(target, 'own', 'new')
    observer.restore()
    assert 'inherited' not in vars(target) and target.inherited == 'old' and target.own == 'old-own'


def test_original_pump_predicate_default_and_error_identity():
    observer, agent, calls, error = PipelineObservation(), object(), [], ValueError('primary')
    predicate = lambda: True
    def pump(selected, callback, seconds=3):
        calls.append((selected, callback, seconds)); raise error
    target = SimpleNamespace(pump=pump)
    observer.bind_pump(target, agent)
    try:
        with pytest.raises(ValueError) as caught: target.pump(agent, predicate)
        assert caught.value is error and calls == [(agent, predicate, 3)]
    finally: observer.restore()
    assert target.pump is pump


def test_http_context_and_owned_post_scope(monkeypatch):
    observer, expected, foreign, events = PipelineObservation(), object(), object(), []
    def connect(connection): events.append(('connect', connection._context)); return 'connected'
    def wrap(context, *args, **kwargs): events.append(('wrap', context)); return 'wrapped'
    monkeypatch.setattr(module.http_client.HTTPSConnection, 'connect', connect)
    monkeypatch.setattr(module.ssl.SSLContext, 'wrap_socket', wrap)
    owned_conn = SimpleNamespace(_context=expected)
    foreign_conn = SimpleNamespace(_context=foreign)
    def post(path):
        assert module.http_client.HTTPSConnection.connect(owned_conn) == 'connected'
        module.http_client.HTTPSConnection.connect(foreign_conn)
        module.ssl.SSLContext.wrap_socket(expected)
        module.ssl.SSLContext.wrap_socket(foreign)
        return 'response'
    http = SimpleNamespace(context=expected, post=post)
    observer.bind_http(http)
    try:
        module.http_client.HTTPSConnection.connect(owned_conn)
        module.ssl.SSLContext.wrap_socket(expected)
        assert not observer.rows['CONTROL']
        assert http.post('/fleet/v1/poll') == 'response'
        counts = {(row['stage'], row['route']): row['count'] for row in observer.summary()['counters']}
        assert counts[('CONNECT_INCL_TLS', 'OTHER')] == 1
        assert counts[('TLS_WRAP', 'OTHER')] == 1
        assert counts[('POST', 'POLL')] == 1
        assert getattr(observer.local, 'context', None) is None
    finally: observer.restore()
    assert http.post is post and module.http_client.HTTPSConnection.connect is connect
    assert module.ssl.SSLContext.wrap_socket is wrap


def test_gateway_owner_is_actual_thread_and_foreign_call_delegates():
    observer, calls = PipelineObservation(), []
    class Store:
        def _validate(self): calls.append('validate')
        @contextmanager
        def _transaction(self): yield 42
        def close(self): calls.append('close')
    controller = SimpleNamespace(store=Store(), domain=None, handle=lambda method, path: calls.append('handle') or 42)
    observer.bind_gateway(controller)
    try:
        assert observer.threads['GATEWAY'] is threading.current_thread()
        assert controller.handle('POST', '/fleet/v1/poll') == 42
        worker = threading.Thread(target=lambda: controller.handle('POST', '/fleet/v1/poll'))
        worker.start(); worker.join(timeout=1)
        assert not worker.is_alive() and calls == ['handle', 'handle']
        counts = [row['count'] for row in observer.summary()['counters'] if row['stage'] == 'HANDLE']
        assert counts == [1]
    finally: observer.restore()


def test_disabled_observer_does_not_read_clock_or_patch():
    def forbidden(): raise AssertionError('disabled clock read')
    observer = PipelineObservation(False, clock=forbidden)
    observer.install(forbidden)
    token = object()
    assert observer.call('CONTROL', 'RPC', lambda: token) is token
    assert not observer.observer_error and observer.restores == [] and observer.summary()['rows'] == []


def test_fixture_print_failure_is_failopen_and_restores(monkeypatch):
    request = SimpleNamespace(node=SimpleNamespace(name=next(iter(module.CASES))))
    fixture = module.pipeline_diagnostics.__wrapped__(request)
    observer = next(fixture)
    target = SimpleNamespace(value='original')
    observer.patch(target, 'value', 'new')
    def print_fault(*args, **kwargs): raise SystemExit('reporting failed')
    monkeypatch.setattr('builtins.print', print_fault)
    with pytest.raises(StopIteration): next(fixture)
    assert target.value == 'original' and observer.observer_error


def test_wrap_forwards_exact_args_return_and_restores():
    observer, token, calls = PipelineObservation(), object(), []
    def original(*args, **kwargs): calls.append((args, kwargs)); return token
    target = SimpleNamespace(action=original)
    observer.wrap(target, 'action', 'CONTROL', 'STEP')
    try:
        assert target.action(1, selected=token) is token
        assert calls == [((1,), {'selected': token})]
    finally: observer.restore()
    assert target.action is original


@pytest.mark.parametrize('raises', [False, True])
def test_inflight_gateway_call_after_fixture_teardown_preserves_result_without_recording(raises):
    request = SimpleNamespace(node=SimpleNamespace(name=next(iter(module.CASES))))
    fixture = module.pipeline_diagnostics.__wrapped__(request)
    observer = next(fixture)
    entered, release = threading.Event(), threading.Event()
    token, primary, results = object(), ValueError('original'), []
    def original():
        entered.set()
        if not release.wait(2): raise AssertionError('control release missing')
        if raises: raise primary
        return token
    def worker():
        observer.threads['GATEWAY'] = threading.current_thread()
        try: results.append(observer.call('GATEWAY', 'HANDLE', original))
        except BaseException as error: results.append(error)
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(1)
        with pytest.raises(StopIteration): next(fixture)
        assert not observer.enabled
        frozen = json.dumps(observer.summary(), sort_keys=True)
    finally:
        release.set(); thread.join(timeout=2)
        fixture.close()
    assert not thread.is_alive() and len(results) == 1
    assert results[0] is (primary if raises else token)
    assert json.dumps(observer.summary(), sort_keys=True) == frozen


def test_retained_wrapper_after_teardown_delegates_without_clock_read():
    request = SimpleNamespace(node=SimpleNamespace(name=next(iter(module.CASES))))
    fixture = module.pipeline_diagnostics.__wrapped__(request)
    observer = next(fixture)
    token, calls = object(), []
    def original(value): calls.append(value); return token
    target = SimpleNamespace(action=original)
    observer.wrap(target, 'action', 'CONTROL', 'RPC')
    retained = target.action
    with pytest.raises(StopIteration): next(fixture)
    def forbidden(): raise AssertionError('late clock read')
    observer.clock = forbidden
    assert target.action is original
    assert retained(token) is token and calls == [token]
    assert not observer.observer_error and observer.summary()['rows'] == []


def test_pytest_dynamic_observer_outlives_original_shared_fixture_cleanup(tmp_path):
    # Exercise real pytest dynamic dependency ordering with the actual shared
    # fixture. The fake gateway avoids sockets/native work; stop is unchanged.
    child = tmp_path / 'test_owned_order.py'
    child.write_text('''import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import fleet_pipeline_fixture as observer_module
import test_tip064_integration as integration
from fleet_pipeline_fixture import pipeline_diagnostics
from test_tip064_integration import composed_service

events = []

@pytest.fixture(autouse=True)
def owned_gateway(monkeypatch):
    original_restore = observer_module.PipelineObservation.restore
    def restore(self, checkpoint=0):
        if not self.enabled:
            events.append('restore:disabled')
            assert events == ['stop:enabled', 'restore:disabled']
            Path(__file__).with_suffix('.json').write_text(json.dumps(events))
        return original_restore(self, checkpoint)
    monkeypatch.setattr(observer_module.PipelineObservation, 'restore', restore)
    monkeypatch.setattr(integration, 'start_gateway_fixture', lambda *a, **k: (None, None, ('127.0.0.1', 1)))
    monkeypatch.setattr(integration, 'FixtureHttpsClient', lambda *a, **k: SimpleNamespace(context=object(), post=lambda *a, **k: None))
    monkeypatch.setattr(integration, 'OwnerClient', lambda *a, **k: object())
    def stop(*args):
        assert observed[0].enabled
        events.append('stop:enabled')
    monkeypatch.setattr(integration, 'stop_gateway_fixture', stop)

@pytest.fixture
def tls_files():
    return ('ca', 'cert', 'key')

observed = []
def test_actual_tls_inventory_discovery_read_project_and_production_native_denial(composed_service, pipeline_diagnostics):
    observed.append(pipeline_diagnostics)
    assert pipeline_diagnostics.enabled
''', encoding='utf-8')
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root / 'app'), str(root / 'tests/unit'))),
               PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(child)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(child.with_suffix('.json').read_text()) == ['stop:enabled', 'restore:disabled']
