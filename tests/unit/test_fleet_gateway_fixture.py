"""Bounded startup observation; no runtime authority or physical qualification."""
import hashlib
import socket
import threading
import time
from queue import Queue

import pytest

from fleet_writer_fixture import wait_gateway_started
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
