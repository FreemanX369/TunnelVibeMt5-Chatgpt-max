"""Bounded startup observation; no runtime authority or physical qualification."""
import hashlib
import ast
import socket
import threading
import time
from queue import Queue
from types import SimpleNamespace

import pytest

from fleet_writer_fixture import wait_gateway_started
from fleet_gateway_fixture import preserve_fixture_failure, stop_gateway_fixture, close_dispatcher_fixture, start_gateway_fixture
from test_tip058b_transport import TOKEN, control_policy, fleet_policy, tls_files
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.transport import GatewayController, HttpsClient, OwnerClient, serve_gateway
from vibemql5.fleet.wire import WireError


def test_observer_waits_for_delayed_real_bind_and_preserves_actual_tls(tmp_path, tls_files, monkeypatch):
    ca, certificate, private = tls_files
    stopped, ready, failures = threading.Event(), Queue(), Queue()
    observed = []
    def delayed_name(host):
        observed.append(host)
        time.sleep(.15)
        return 'localhost'
    monkeypatch.setattr(socket, 'getfqdn', delayed_name)
    def factory(address):
        store = GatewayControlStore.initialize(tmp_path / 'control.sqlite', policy=control_policy())
        return GatewayController(store, fleet_policy(), audience='https://127.0.0.1:' + str(address[1]),
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest())
    def run():
        try:
            serve_gateway(('127.0.0.1', 0), certificate=certificate, key_file=private,
                controller_factory=factory, stop_event=stopped, started=ready.put)
        except BaseException as error:
            failures.put(error)
    thread = threading.Thread(target=run, daemon=True); thread.start()
    try:
        address = wait_gateway_started(ready, failures, thread, timeout=5)
        assert observed == ['127.0.0.1'] and address[0] == '127.0.0.1'
        owner = OwnerClient(HttpsClient('https://127.0.0.1:' + str(address[1]), fleet_policy(), cafile=str(ca)), TOKEN)
        with pytest.raises(WireError, match='READ_INTERRUPTED'):
            owner.read_status('read_absent_fixture')
    finally:
        stopped.set(); thread.join(timeout=3)
        assert not thread.is_alive()
        if not failures.empty(): raise failures.get()


def test_observer_surfaces_actual_startup_exception_before_waiting_for_ready():
    ready, failures = Queue(), Queue()
    error = ValueError('GATEWAY_STARTUP_REJECTED')
    failures.put(error)
    with pytest.raises(ValueError, match='GATEWAY_STARTUP_REJECTED') as caught:
        wait_gateway_started(ready, failures, threading.current_thread(), timeout=10)
    assert caught.value is error and ready.empty()


def test_observer_timeout_reports_sanitized_live_stage_and_does_not_claim_closure():
    release, entered = threading.Event(), threading.Event()
    def blocked_startup():
        entered.set(); release.wait(timeout=5)
    thread = threading.Thread(target=blocked_startup, daemon=True); thread.start()
    try:
        assert entered.wait(timeout=1)
        with pytest.raises(TimeoutError, match='GATEWAY_STARTUP_FIXTURE_TIMEOUT') as caught:
            wait_gateway_started(Queue(), Queue(), thread, timeout=.05)
        note = caught.value.__notes__[0]
        assert 'blocked_startup' in note and "'server_thread_alive': True" in note
        assert thread.is_alive()
    finally:
        release.set(); thread.join(timeout=1)
        assert not thread.is_alive()


def test_cleanup_preserves_primary_notes_and_cleanup_failure():
    primary = pytest.fail.Exception('controlled-primary')
    primary.add_note('CAPACITY_HTTPS_FIXTURE {"state": "UNKNOWN"}')
    cleanup = WireError('HTTPS_UNAVAILABLE')
    with pytest.raises(BaseExceptionGroup) as caught:
        try:
            raise primary
        finally:
            with preserve_fixture_failure():
                raise cleanup
    assert caught.value.exceptions == (primary, cleanup)
    assert primary.__notes__ == ['CAPACITY_HTTPS_FIXTURE {"state": "UNKNOWN"}']
    print('CONTROLLED_PRIMARY_AND_CLEANUP_PRESERVED')


def test_cleanup_only_error_is_not_suppressed():
    error = WireError('DOMAIN_WORKERS_ACTIVE')
    with pytest.raises(WireError, match='DOMAIN_WORKERS_ACTIVE') as caught:
        with preserve_fixture_failure():
            raise error
    assert caught.value is error


def test_proven_idle_cleanup_closes_without_new_control_call():
    events = []
    dispatcher = SimpleNamespace(has_pending_work=lambda: False, close=lambda: events.append('closed'))
    def unexpected_control(*args, **kwargs):
        raise AssertionError('idle cleanup emitted new HTTPS authority')
    close_dispatcher_fixture(None, dispatcher, unexpected_control)
    assert events == ['closed']
    print('CONTROLLED_IDLE_CLEANUP_NO_HTTPS_CALL')


def test_uncertain_drain_failure_does_not_close_or_claim_idle():
    events = []
    dispatcher = SimpleNamespace(has_pending_work=lambda: True, close=lambda: events.append('closed'))
    error = WireError('HTTPS_UNAVAILABLE')
    def failed_control(*args, **kwargs):
        events.append('drain-attempted')
        raise error
    with pytest.raises(WireError, match='HTTPS_UNAVAILABLE') as caught:
        close_dispatcher_fixture(None, dispatcher, failed_control)
    assert caught.value is error and events == ['drain-attempted']
    assert dispatcher.has_pending_work()


def test_stop_observer_records_real_gateway_close_stage_and_retains_uncertainty(tmp_path, tls_files, monkeypatch):
    import test_tip064_integration as integration
    from vibemql5.fleet.domain import GatewayDomain
    entered, release = threading.Event(), threading.Event()
    original_close = GatewayDomain.close
    def held_close(domain):
        entered.set()
        assert release.wait(timeout=10)
        original_close(domain)
    def bounded_stop(stopped, thread, failures):
        stopped.set()
        assert entered.wait(timeout=3)
        stop_gateway_fixture(stopped, thread, failures, timeout=.1)
    monkeypatch.setattr(GatewayDomain, 'close', held_close)
    monkeypatch.setattr(integration, 'stop_gateway_fixture', bounded_stop)
    service = integration.composed_service.__wrapped__(tmp_path, tls_files, SimpleNamespace())
    http, owner, _ = next(service)
    try:
        with pytest.raises(WireError, match='READ_INTERRUPTED'):
            owner.read_status('controlled-absent-command')
        with pytest.raises(TimeoutError, match='GATEWAY_STOP_FIXTURE_TIMEOUT') as caught:
            next(service)
        assert entered.is_set() and http.server_thread.is_alive()
        note = caught.value.__notes__[0]
        diagnostic = ast.literal_eval(note)
        assert diagnostic['server_thread_alive'] is True and diagnostic['timeout_seconds'] == .1
        assert 1 <= len(diagnostic['stack']) <= 12
        assert any(frame['function'] == 'held_close' for frame in diagnostic['stack'])
        assert all('/' not in frame['file'] and '\\' not in frame['file'] for frame in diagnostic['stack'])
        assert 'controlled-absent-command' not in note and TOKEN not in note
        print('CONTROLLED_GATEWAY_STOP ' + note)
    finally:
        release.set(); http.server_thread.join(timeout=3)
        assert not http.server_thread.is_alive() and http.failures.empty()


def test_start_observer_preserves_actual_factory_failure_and_closes_thread(tls_files):
    _, certificate, private = tls_files
    failures, calls, threads = Queue(), [], []
    error = ValueError('CONTROLLED_STARTUP_FACTORY_ERROR')
    def failed_factory(address):
        calls.append(address)
        threads.append(threading.current_thread())
        raise error
    with pytest.raises(ValueError, match='CONTROLLED_STARTUP_FACTORY_ERROR') as caught:
        start_gateway_fixture(('127.0.0.1', 0), certificate=certificate, key_file=private,
            controller_factory=failed_factory, failures=failures)
    assert caught.value is error and len(calls) == 1
    assert not threads[0].is_alive() and failures.empty()
    print('CONTROLLED_FACTORY_EXCEPTION_PRESERVED_THREAD_CLOSED_NO_RETRY')


def test_start_timeout_preserves_live_factory_stage_and_cleanup_uncertainty(tmp_path, tls_files, monkeypatch):
    import fleet_writer_fixture
    _, certificate, private = tls_files
    entered, release, failures, threads = threading.Event(), threading.Event(), Queue(), []
    observer = fleet_writer_fixture.wait_gateway_started
    def held_factory(address):
        threads.append(threading.current_thread())
        entered.set()
        assert release.wait(timeout=10)
        store = GatewayControlStore.initialize(tmp_path / 'controlled-start.sqlite', policy=control_policy())
        return GatewayController(store, fleet_policy(), audience='https://127.0.0.1:' + str(address[1]),
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest())
    def established_observer(ready, failures, thread, *, timeout):
        assert entered.wait(timeout=5)
        return observer(ready, failures, thread, timeout=timeout)
    monkeypatch.setattr(fleet_writer_fixture, 'wait_gateway_started', established_observer)
    try:
        with pytest.raises(BaseExceptionGroup) as caught:
            start_gateway_fixture(('127.0.0.1', 0), certificate=certificate, key_file=private,
                controller_factory=held_factory, failures=failures, startup_timeout=.05, stop_timeout=.05)
        primary, cleanup = caught.value.exceptions
        assert isinstance(primary, TimeoutError) and str(primary) == 'GATEWAY_STARTUP_FIXTURE_TIMEOUT'
        assert isinstance(cleanup, TimeoutError) and str(cleanup) == 'GATEWAY_STOP_FIXTURE_TIMEOUT'
        assert threads[0].is_alive() and failures.empty()
        for error in (primary, cleanup):
            note = error.__notes__[0]
            diagnostic = ast.literal_eval(note)
            assert diagnostic['server_thread_alive'] is True
            assert 1 <= len(diagnostic['stack']) <= 12
            assert any(frame['function'] == 'held_factory' for frame in diagnostic['stack'])
            assert all('/' not in frame['file'] and '\\' not in frame['file'] for frame in diagnostic['stack'])
            assert TOKEN not in note and str(tmp_path) not in note
            print('CONTROLLED_START_AND_STOP_UNCERTAINTY ' + note)
    finally:
        release.set()
        if threads:
            threads[0].join(timeout=5)
            assert not threads[0].is_alive() and failures.empty()
