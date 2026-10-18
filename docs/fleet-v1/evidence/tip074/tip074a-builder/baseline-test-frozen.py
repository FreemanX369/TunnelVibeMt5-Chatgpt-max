"""Owned real TLS/SQLite failure lifetimes; no Windows or live qualification."""
import gc
import hashlib
import socket
import sys
import threading
from contextlib import ExitStack
from queue import Queue
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_tip058b_transport import tls_files, control_policy, fleet_policy, TOKEN
from test_tip061a_057n import node as project_node
from test_tip064_integration import domain_policy
from vibemql5.core.jobs import _exclusive_file_lock
from vibemql5.fleet.domain import DomainJournal, GatewayDomain
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal
from vibemql5.fleet.read_broker import ReadBroker
from vibemql5.fleet.transport import GatewayController, HttpsClient, OwnerClient, serve_gateway


def errors(error):
    pending, result, seen = [error], [], set()
    while pending:
        current = pending.pop()
        if id(current) in seen: continue
        seen.add(id(current)); result.append(current)
        if isinstance(current, BaseExceptionGroup): pending.extend(current.exceptions)
        pending.extend(value for value in (current.__context__, current.__cause__) if value is not None)
    return result


def owners(error):
    result = {}
    for current in errors(error):
        frame = current.__traceback__
        while frame is not None:
            for value in frame.tb_frame.f_locals.values():
                if type(value) in (GatewayControlStore, GatewayJobJournal, DomainJournal): result[id(value)] = value
            frame = frame.tb_next
    return result


def lease_available(resource):
    path = resource.path.with_name(resource.path.name + '.owner.lock')
    try:
        with _exclusive_file_lock(path, timeout_seconds=.05): return True
    except TimeoutError: return False


@pytest.mark.parametrize('case', ['capacity-jobs', 'capacity-domain', 'composed-principals', 'writer-domain'])
def test_partial_fixture_construction_closes_real_owners_with_traceback_retained(tmp_path, tls_files, project_node, monkeypatch, case):
    import test_tip064_capacity_https as capacity
    import test_tip064_integration as composed
    import fleet_writer_fixture as writer
    import vibemql5.fleet.principals as principals
    module, constructor, path, count = {
        'capacity-jobs': (capacity, 'GatewayJobJournal', 'capacity-jobs.sqlite', 1),
        'capacity-domain': (capacity, 'DomainJournal', 'capacity-domain.sqlite', 2),
        'composed-principals': (principals, 'GatewayPrincipalAuthority', 'composed-principals.json', 3),
        'writer-domain': (writer, 'DomainJournal', 'gateway/domains.sqlite', 1),
    }[case]
    fault = tmp_path / path; fault.parent.mkdir(parents=True, exist_ok=True); fault.write_bytes(b'OWNED_EXISTING_STORE')
    original, observations, primary = getattr(module, constructor), [], []
    def observe_real_constructor(*args, **kwargs):
        try: return original(*args, **kwargs)
        except BaseException as error:
            primary.append(error)
            frame = sys._getframe(1)
            observations.extend(value._db.execute('SELECT 1').fetchone()[0]
                for value in frame.f_locals.values() if type(value) in (GatewayControlStore, GatewayJobJournal, DomainJournal))
            raise
    monkeypatch.setattr(module, constructor, observe_real_constructor)
    if case.startswith('capacity'):
        generator = capacity.capacity_service.__wrapped__(tmp_path, tls_files, SimpleNamespace())
    elif case.startswith('composed'):
        generator = composed.composed_service.__wrapped__(tmp_path, tls_files, SimpleNamespace())
    else:
        generator = writer.writer_fixture.__wrapped__(project_node, tls_files, tmp_path)
    caught, retained = None, {}
    try:
        try: next(generator)
        except BaseException as error: caught = error
        assert caught is not None and primary[0] in errors(caught)
        assert observations == [1] * count
        retained = owners(caught)
        assert len(retained) == count
        assert all(resource._db is None and resource._lock is None and lease_available(resource) for resource in retained.values())
    finally:
        # Dispose only this owned red/control fixture after recording assertions.
        retained.clear()
        if caught is not None:
            for error in errors(caught): error.__traceback__ = None
        primary.clear(); caught = None; gc.collect()


def test_partial_factory_attempts_all_closes_and_retains_primary_and_cleanup_errors(tmp_path, tls_files, project_node, monkeypatch):
    import test_tip064_capacity_https as capacity
    fault = tmp_path / 'capacity-domain.sqlite'; fault.write_bytes(b'OWNED_EXISTING_STORE')
    attempted, failures = [], [OSError('OWNED_JOBS_CLOSE'), RuntimeError('OWNED_CONTROL_CLOSE')]
    for kind, name, secondary in ((GatewayJobJournal, 'jobs', failures[0]), (GatewayControlStore, 'control', failures[1])):
        original = kind.close
        def close(self, real=original, label=name, error=secondary):
            attempted.append(label); real(self); raise error
        monkeypatch.setattr(kind, 'close', close)
    generator = capacity.capacity_service.__wrapped__(tmp_path, tls_files, SimpleNamespace())
    caught, retained = None, {}
    try:
        try: next(generator)
        except BaseException as error: caught = error
        assert caught is not None and attempted == ['jobs', 'control']
        graph = errors(caught)
        assert all(any(error is secondary for error in graph) for secondary in failures)
        assert any(getattr(error, 'code', None) == 'DOMAIN_EXISTS' for error in graph)
        retained = owners(caught)
        assert len(retained) == 2
        assert all(resource._db is None and resource._lock is None and lease_available(resource) for resource in retained.values())
    finally:
        retained.clear()
        if caught is not None:
            for error in errors(caught): error.__traceback__ = None
        caught = None; gc.collect()


@pytest.mark.parametrize('fault', ['none', 'domain', 'store', 'both', 'before-domain'])
def test_started_failure_closes_real_controller_owners_and_preserves_error_truth(tmp_path, tls_files, fault):
    ca, certificate, private = tls_files
    stopped, release = threading.Event(), threading.Event()
    bound, finished, reports = Queue(), Queue(), Queue()
    acquired, real_close, attempted = {}, {}, []
    primary = RuntimeError('OWNED_STARTED_FAILURE')
    domain_error, store_error = OSError('OWNED_DOMAIN_CLOSE_FAILURE'), RuntimeError('OWNED_STORE_CLOSE_FAILURE')
    def factory(address):
        origin = 'https://127.0.0.1:' + str(address[1])
        with ExitStack() as closes:
            store = GatewayControlStore.initialize(tmp_path / 'control.sqlite', policy=control_policy()); closes.callback(store.close)
            jobs = GatewayJobJournal(tmp_path / 'jobs.sqlite', initialize=True, max_records=20, max_payload_bytes=262144, wait_ms=1000); closes.callback(jobs.close)
            journal = DomainJournal(tmp_path / 'domain.sqlite', initialize=True, role='GATEWAY', policy=domain_policy()); closes.callback(journal.close)
            domain = GatewayDomain(store, journal, jobs, start_authorization_ms=2000)
            controller = GatewayController(store, fleet_policy(), audience=origin,
                owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(), broker=ReadBroker.for_synthetic_tests(fleet_policy()), domain=domain)
            acquired.update(control=store, jobs=jobs, domain=journal)
            real_close.update(domain=domain.close, store=store.close)
            def close_domain():
                attempted.append('domain')
                if fault == 'before-domain': raise domain_error
                real_close['domain']()
                if fault in ('domain', 'both'): raise domain_error
            def close_store():
                attempted.append('store'); real_close['store']()
                if fault in ('store', 'both'): raise store_error
            domain.close, store.close = close_domain, close_store
            closes.pop_all(); return controller
    def started(address): bound.put(address); raise primary
    def run():
        caught = None
        try: serve_gateway(('127.0.0.1', 0), certificate=certificate, key_file=private,
            controller_factory=factory, stop_event=stopped, started=started)
        except BaseException as error: caught = error
        try:
            reports.put({name: resource._db.execute('SELECT 1').fetchone()[0] if resource._db is not None else None
                         for name, resource in acquired.items()})
            finished.put(caught)
            assert release.wait(timeout=5)
        finally:
            # Owner-thread disposal happens only after parent observes the result.
            real_close['domain'](); real_close['store']()
    thread = threading.Thread(target=run, daemon=True); thread.start()
    try:
        caught = finished.get(timeout=5); state = reports.get(timeout=1); address = bound.get(timeout=1)
        graph = errors(caught)
        assert any(error is primary for error in graph) and primary.__traceback__ is not None
        assert attempted == ['domain', 'store']
        if fault in ('domain', 'both', 'before-domain'): assert any(error is domain_error for error in graph)
        if fault in ('store', 'both'): assert any(error is store_error for error in graph)
        if fault == 'none': assert caught is primary
        if fault == 'before-domain':
            assert state == {'control': None, 'jobs': 1, 'domain': 1}
            assert lease_available(acquired['control']) and not lease_available(acquired['jobs']) and not lease_available(acquired['domain'])
        else:
            assert state == {'control': None, 'jobs': None, 'domain': None}
            assert all(lease_available(resource) for resource in acquired.values())
        with socket.socket() as probe: probe.bind(address)
    finally:
        release.set(); thread.join(timeout=3)
    assert not thread.is_alive()


def test_normal_tls_request_and_stop_transfer_owners_once(tmp_path, tls_files):
    ca, certificate, private = tls_files
    stopped, bound, failures, acquired = threading.Event(), Queue(), Queue(), []
    def factory(address):
        store = GatewayControlStore.initialize(tmp_path / 'normal.sqlite', policy=control_policy()); acquired.append(store)
        return GatewayController(store, fleet_policy(), audience='https://127.0.0.1:' + str(address[1]),
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(), broker=ReadBroker.for_synthetic_tests(fleet_policy()))
    def run():
        try: serve_gateway(('127.0.0.1', 0), certificate=certificate, key_file=private,
            controller_factory=factory, stop_event=stopped, started=bound.put)
        except BaseException as error: failures.put(error)
    thread = threading.Thread(target=run, daemon=True); thread.start()
    try:
        address = bound.get(timeout=5)
        http = HttpsClient('https://127.0.0.1:' + str(address[1]), fleet_policy(), cafile=str(ca))
        key = Ed25519PrivateKey.generate()
        response = OwnerClient(http, TOKEN).admin('grant', {'device_id': 'dev_' + 'a' * 32,
            'public_key': key.public_key().public_bytes_raw().hex(), 'operation_id': 'owned-grant',
            'expected_revision': 1, 'expected_route_generation': None})
        assert response['receipt']['revision'] == 2 and acquired[0]._db is not None
    finally:
        stopped.set(); thread.join(timeout=3)
    assert not thread.is_alive() and failures.empty()
    assert acquired[0]._db is None and acquired[0]._lock is None and lease_available(acquired[0])
