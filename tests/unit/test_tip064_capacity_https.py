"""Actual TLS and scoped concurrency; signed claims remain synthetic, no MT5 PASS."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import threading
import time
from dataclasses import replace
from queue import Queue

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_tip058b_transport import TOKEN, control_policy, fleet_policy, positive, tls_files, FixtureHttpsClient, observe_control_posts
from fleet_gateway_fixture import preserve_fixture_failure, stop_gateway_fixture, close_dispatcher_fixture, start_gateway_fixture
from test_tip061a_057n import node as project_node, freeze, logical_fixture
from test_tip055a_runtime_forensics_identity import ref
from test_tip064_integration import domain_policy, pump
from vibemql5.adapters.fleet_client_tools import FleetClientFacade
from vibemql5.core.native_ownership import current_identity
from vibemql5.fleet.domain import DomainJournal, GatewayDomain, NodeDomainDispatcher
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal, NodeJobJournal, canonical, digest
from vibemql5.fleet.native import native_request
from vibemql5.fleet.native_authorization import GatewayNativeSigner, NativeAuthorization, NativeAuthorizationVerifier
from vibemql5.fleet.node_transport_journal import NodeTransportJournal, TransportPolicy
from vibemql5.fleet.read_broker import ReadBroker
from vibemql5.fleet.resources import physical_resources
from vibemql5.fleet.scoped_resources import CONFLICT_MATRIX, DOMAIN, ScopedResourceCoordinator, capacity_source_manifest, verify_capacity_roster
from vibemql5.fleet.transport import GatewayController, NodeClient, OutboundNode, OwnerClient
from vibemql5.fleet.wire import WireError


def signed_roster(node, owner_key):
    """Only protocol-claim signing; the private coordinator never installs this."""
    rows, requests = [], []
    raw = node['source'].read_bytes()
    for index in (0, 1):
        placement = freeze(node, 'capacity-' + str(index), operation='capacity-freeze-' + str(index),
            target={**ref(node['registry'], index), 'route_generation': 1})
        requests.append(native_request(placement, logical_fixture(), [
            {'path': 'Experts/DemoEA.mq5', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}]))
        resources = dict(placement['binding'])
        for kind in ('include_root', 'agent_root'):
            directory = node['root'] / ('capacity-' + kind + str(index)); directory.mkdir()
            resources[kind] = str(directory)
        rows.append({'terminal_id': placement['target']['terminal_id'], 'terminal_generation': 1,
            'resources': resources, 'physical_identities': physical_resources(resources)})
    body = {'schema': 'fleet.capacity-profile/1', 'device_id': node['registry']['device_id'], 'install_epoch': 'b' * 32,
        'capacity': 2, 'candidate_sha256': None, 'runtime_sha256': 'd' * 64,
        'source_manifest': capacity_source_manifest(), 'terminals': rows, 'load_receipt': None, 'closure_receipt': None,
        'max_records': 20, 'lock_wait_ms': 1000, 'conflict_matrix': CONFLICT_MATRIX}
    body['candidate_sha256'] = digest(body['source_manifest'])
    facts = {'qualification': 'PHYSICAL_WINDOWS', 'candidate_sha256': body['candidate_sha256'],
        'runtime_sha256': body['runtime_sha256'], 'device_id': body['device_id'], 'install_epoch': body['install_epoch'],
        'capacity': 2, 'terminal_roster_sha256': digest(rows), 'fixture_label': 'SYNTHETIC_SIGNED_PROTOCOL_CLAIMS_ONLY'}
    load = canonical({**facts, 'schema': 'fleet.capacity-load/1', 'duration_ms': 10000, 'completed_jobs': 2,
        'measured': {'memory_bytes': 1000, 'cpu_basis_points': 100, 'p95_phase_ms': 10},
        'limits': {'memory_bytes': 2000, 'cpu_basis_points': 1000, 'p95_phase_ms': 100}})
    closure = canonical({**facts, 'schema': 'fleet.capacity-closure/1', 'descendant_boundary': 'EXACT_DESCENDANTS_EXITED'})
    for name, value in (('load_receipt', load), ('closure_receipt', closure)):
        body[name] = {'path': 'state/fleet/' + name + '.json', 'sha256': hashlib.sha256(value).hexdigest()}
    signed = {'body': body, 'signature': owner_key.sign(DOMAIN + canonical(body)).hex()}
    return signed, load, closure, requests


@pytest.fixture
def capacity_service(tmp_path, tls_files, request):
    ca, certificate, private = tls_files
    failures = Queue()
    signer_key, owner_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    owner_public = owner_key.public_key().public_bytes_raw().hex()
    # Positive TLS/SQLite composition is not the transport deadline-negative
    # profile. Its signed grants and durable admission rules remain unchanged.
    budget = getattr(request, 'param', 5000)
    policy = replace(fleet_policy(), max_body_bytes=262144, max_response_bytes=262144,
        http_timeout_ms=budget, heartbeat_interval_ms=budget)
    def factory(address):
        origin = 'https://127.0.0.1:' + str(address[1])
        control = GatewayControlStore.initialize(tmp_path / 'capacity-control.sqlite',
            policy=replace(control_policy(), max_operations=1000, max_nonces=1000))
        jobs = GatewayJobJournal(tmp_path / 'capacity-jobs.sqlite', initialize=True,
            capacity_owner_public_key=owner_public, max_records=20, max_payload_bytes=262144, wait_ms=1000)
        journal = DomainJournal(tmp_path / 'capacity-domain.sqlite', initialize=True, role='GATEWAY', policy=domain_policy())
        domain = GatewayDomain(control, journal, jobs, native_signer=GatewayNativeSigner(signer_key, origin,
            max_authorization_ms=2000), capacity_owner_public_key=owner_public, start_authorization_ms=2000)
        return GatewayController(control, policy, audience=origin,
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(), broker=ReadBroker.for_synthetic_tests(policy), domain=domain)
    stopped, thread, address = start_gateway_fixture(('127.0.0.1', 0), certificate=certificate,
        key_file=private, controller_factory=factory, failures=failures, startup_timeout=5, stop_timeout=3)
    http = FixtureHttpsClient('https://127.0.0.1:' + str(address[1]), policy, cafile=str(ca),
        server_thread=thread, failures=failures)
    try:
        yield http, OwnerClient(http, TOKEN), signer_key, owner_key, policy
    finally:
        with preserve_fixture_failure():
            stop_gateway_fixture(stopped, thread, failures)


@pytest.mark.parametrize('observation_order', ['normal', 'delayed-release-and-completion'])
def test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued(project_node, capacity_service, observation_order):
    run_capacity_fixture(project_node, capacity_service, observation_order)


def run_capacity_fixture(project_node, capacity_service, observation_order):
    http, owner, signer_key, owner_key, policy = capacity_service
    root, device = project_node['root'], project_node['registry']['device_id']
    signed, load, closure, requests = signed_roster(project_node, owner_key)
    roster = verify_capacity_roster(signed, device_id=device, route_generation=1,
        trusted_owner_public_key=owner_key.public_key().public_bytes_raw().hex(), load_receipt=load, closure_receipt=closure)
    # These actual harmless scopes have private test provenance and no marker.
    coordinator = ScopedResourceCoordinator._for_fixture(root, signed['body'], initialize=True)
    entered, release, calls = Queue(), threading.Event(), []
    callback_failures = []
    def preserve_callback(callback):
        def captured(*args, **kwargs):
            try: return callback(*args, **kwargs)
            except BaseException as error:
                if not any(error is previous for previous in callback_failures): callback_failures.append(error)
                raise
        return captured
    def raise_callback_failure():
        if callback_failures: raise callback_failures[0]
    def checked(predicate):
        def observed():
            raise_callback_failure()
            result = predicate()
            raise_callback_failure()
            return result
        return observed
    completion, timers = threading.Event(), []
    if observation_order == 'normal': completion.set()
    class ScopedHarmlessAdapter:
        @preserve_callback
        def reserve(self, request, operation, exact_fence):
            assert type(exact_fence['authorization']) is NativeAuthorization
            return {'local_job_id': exact_fence['local_job_id']}
        @preserve_callback
        def start_reserved(self, local_job_id, request, exact_fence):
            assert type(exact_fence['authorization']) is NativeAuthorization
            selected = request['placement']['target']
            with coordinator.execution(local_job_id, kind='tester', terminal_id=selected['terminal_id'],
                    terminal_generation=selected['terminal_generation'], wait_ms=1000) as scope:
                # Capture before the context manager's durable release, which
                # can independently fail and replace the callback exception.
                @preserve_callback
                def held_scope():
                    armed = scope.arm(); calls.append(local_job_id); entered.put(local_job_id)
                    # One finite harmless hold budget includes test observations
                    # and the controlled delayed-completion regression barrier.
                    hold_deadline = time.monotonic() + 20
                    assert release.wait(max(0, hold_deadline - time.monotonic()))
                    assert completion.wait(max(0, hold_deadline - time.monotonic()))
                    scope.close_zero_attempt(armed)
                held_scope()
            return {'schema': 'fleet.native.effect/1', 'phase': 'start', 'evidence': 'SYNTHETIC_NATIVE_ONLY',
                'payload': {'execution': {'status': 'COMPLETED'}, 'process': current_identity()}}
    key = Ed25519PrivateKey.generate()
    transport = NodeTransportJournal.initialize(root / 'capacity-transport.sqlite',
        TransportPolicy(max_records=1000, max_payload_bytes=262144, wait_ms=1000),
        device_id=device, public_key=key.public_key().public_bytes_raw().hex(), audience=http.origin)
    grant = owner.admin('grant', {'device_id': device, 'public_key': key.public_key().public_bytes_raw().hex(),
        'operation_id': 'grant-capacity', 'expected_revision': 1, 'expected_route_generation': None})
    client = NodeClient(http, key, device, 0, transport_journal=transport)
    client.pair(grant_id=grant['receipt']['grant_id'], secret=grant['secret'], operation_id='pair-capacity', expected_revision=2)
    jobs = NodeJobJournal(root / 'capacity-node-jobs.sqlite', initialize=True, max_records=20, max_payload_bytes=262144, wait_ms=1000)
    domains = DomainJournal(root / 'capacity-node-domain.sqlite', initialize=True, role='NODE', policy=domain_policy())
    verifier = NativeAuthorizationVerifier(signer_key.public_key().public_bytes_raw().hex(), http.origin,
        clock_ms=lambda: int(time.time() * 1000))
    dispatcher = NodeDomainDispatcher(root, domains, jobs, ScopedHarmlessAdapter(), authorization_verifier=verifier,
        max_inventory_rows=20, capacity_roster=roster)
    agent = OutboundNode(client, root, policy, session_id='session-capacity', domain_dispatcher=dispatcher, synthetic_read_adapter=positive)
    facade = FleetClientFacade(owner)
    failures = []
    try:
        agent.step()
        payload = {'signed_profile': signed, 'load_receipt_base64': base64.b64encode(load).decode(),
            'closure_receipt_base64': base64.b64encode(closure).decode()}
        forged = copy.deepcopy(payload); forged['signed_profile']['signature'] = '0' * 128
        with pytest.raises(WireError): client.register_capacity(agent.session_id, **forged)
        registered = client.register_capacity(agent.session_id, **payload)
        assert registered['profile_sha256'] == roster.profile_sha256
        launched = [facade.launch_job('capacity-native-' + str(index), request) for index, request in enumerate(requests)]
        pump(agent, checked(lambda: entered.qsize() == 2))
        assert dispatcher.native_capacity == 2
        assert len({entered.get_nowait(), entered.get_nowait()}) == 2
        with coordinator.transaction() as db:
            from vibemql5.fleet.job_journal import _decode
            active = [_decode(row[0]) for row in db.execute('SELECT record FROM reservations')]
            assert len(active) == 2 and all(row['phase'] == 'ARMED' and row['status'] == 'ACQUIRED' for row in active)
        third = facade.launch_job('capacity-conflicting-third', requests[0])
        with observe_control_posts(http) as observed:
            began = time.monotonic()
            try:
                for _ in range(3):
                    raise_callback_failure()
                    agent.step()
                    raise_callback_failure()
                    # Each control step must return while both real workers
                    # are still held; no fast-storage performance claim.
                    assert not release.is_set() and len(calls) == 2
                    assert len(dispatcher._futures) == 2
                    assert all(not row['future'].done() for row in dispatcher._futures.values())
                # Six independent HTTP calls have six configured budgets.
                # The independent 20-second worker hold remains stricter.
                assert time.monotonic() - began < 6 * policy.http_timeout_ms / 1000
            except BaseException as error:
                facts = {**observed.summary(time.monotonic() - began), "callback_count": len(calls),
                         "release_set": release.is_set(), "completion_set": completion.is_set(),
                         "pending_worker_count": len(dispatcher._futures)}
                error.add_note('CAPACITY_CONTROL_FIXTURE ' + json.dumps(facts, sort_keys=True))
                raise
        assert len(calls) == 2 and facade.get_job(third['global_job_id'])['state'] == 'QUEUED'
        assert all(facade.get_job(row['global_job_id'])['state'] == 'STARTING' for row in launched)
        if observation_order != 'normal':
            # Force observations past the former five-second worker watchdog.
            observed = threading.Event()
            timer = threading.Timer(5.2, observed.set); timers.append(timer); timer.start()
            pump(agent, checked(observed.is_set), seconds=10)
            assert not release.is_set() and len(calls) == 2
            assert facade.get_job(third['global_job_id'])['state'] == 'QUEUED'
            assert all(facade.get_job(row['global_job_id'])['state'] == 'STARTING' for row in launched)
            # Keep actual callbacks blocked past the old aggregate three-second
            # observation budget while the control owner continues stepping.
            timer = threading.Timer(3.2, completion.set); timers.append(timer); timer.start()
        latest = []
        def summary(row):
            result = row.get('result') or {}
            nested = result.get('result') if isinstance(result, dict) else None
            reason = (nested if isinstance(nested, dict) else result).get('reason_code') if isinstance(result, dict) else None
            return {'state': row['state'], 'sequence': row.get('sequence'),
                    'reason_code': reason if isinstance(reason, str) and re.fullmatch('[A-Z0-9_]{1,80}', reason) else None}
        def completed():
            latest[:] = [summary(facade.get_job(row['global_job_id'])) for row in launched + [third]]
            if any(row['state'] in {'FAILED', 'CANCELLED', 'UNKNOWN', 'RECOVERY_REQUIRED'} for row in latest):
                pytest.fail('capacity fixture terminal outcome ' + json.dumps(latest, sort_keys=True))
            return all(row['state'] == 'SUCCEEDED' for row in latest) and not dispatcher.has_pending_work()
        def diagnostic():
            value = {'gateway_jobs': latest, 'node_jobs': [], 'callback_count': len(calls),
                     'release_set': release.is_set(), 'completion_set': completion.is_set(),
                     'pending_futures': len(dispatcher._futures), 'pending_native_records': len(dispatcher._native_records)}
            for row in launched + [third]:
                try: value['node_jobs'].append(summary(jobs.get(row['global_job_id'])))
                except Exception as error: value['node_jobs'].append({'lookup_error_type': type(error).__name__})
            try:
                with coordinator.transaction() as db:
                    value['scopes'] = [{'status': item['status'], 'phase': item['phase']} for item in
                        (_decode(row[0]) for row in db.execute('SELECT record FROM reservations'))]
            except Exception as error: value['scope_lookup_error_type'] = type(error).__name__
            return value
        release.set()
        try:
            pump(agent, checked(completed), seconds=10)
        except BaseException as error:
            error.add_note('CAPACITY_HTTPS_FIXTURE ' + json.dumps(diagnostic(), sort_keys=True))
            raise
        assert len(calls) == 3
        for row in launched + [third]:
            assert facade.get_job(row['global_job_id'])['result']['result']['evidence'] == 'SYNTHETIC_NATIVE_ONLY'
        assert not (root / 'state' / 'fleet' / 'scoped-install.json').exists()
    except BaseException as primary:
        failures.append(primary)
    finally:
        try:
            release.set(); completion.set()
            for timer in timers:
                timer.cancel(); timer.join(timeout=1)
                assert not timer.is_alive()
            close_dispatcher_fixture(agent, dispatcher, pump, seconds=10)
            jobs.close(); domains.close(); transport.close()
        except BaseException as cleanup:
            failures.append(cleanup)
    originals = []
    for failure in failures + callback_failures:
        if not any(failure is original for original in originals): originals.append(failure)
    if len(originals) == 1: raise originals[0]
    if originals: raise BaseExceptionGroup('capacity fixture observation, callback or cleanup failed', originals) from None


@pytest.mark.parametrize('capacity_service', [1000, 5000], indirect=True)
def test_capacity_positive_profile_delayed_durable_registration_has_no_retry(project_node, capacity_service, monkeypatch, tmp_path):
    import sqlite3
    original = GatewayJobJournal.install_capacity_roster
    installed, returned = [], threading.Event()
    def delayed(self, roster):
        result = original(self, roster)
        installed.append(result['profile']['device_id'])
        time.sleep(1.2)  # Already committed: a missing response is uncertainty.
        returned.set()
        return result
    monkeypatch.setattr(GatewayJobJournal, 'install_capacity_roster', delayed)
    budget = capacity_service[0].policy.http_timeout_ms
    if budget == 1000:
        with pytest.raises(WireError) as observed:
            run_capacity_fixture(project_node, capacity_service, 'normal')
        if (observed.value.code != 'HTTPS_UNAVAILABLE' or installed != [project_node['registry']['device_id']]
                or not any('TimeoutError' in note for note in getattr(observed.value, '__notes__', []))):
            raise observed.value
    else:
        run_capacity_fixture(project_node, capacity_service, 'normal')
    assert returned.wait(3)
    assert installed == [project_node['registry']['device_id']]
    db = sqlite3.connect((tmp_path / 'capacity-jobs.sqlite').as_uri() + '?mode=ro', uri=True)
    try:
        durable = json.loads(db.execute("SELECT value FROM meta WHERE name='capacity_rosters'").fetchone()[0])
    finally: db.close()
    assert list(durable) == installed and durable[installed[0]]['profile']['capacity'] == 2
    assert capacity_service[0].policy.heartbeat_interval_ms == budget


def test_capacity_control_returns_while_workers_held_past_old_aggregate(project_node, capacity_service, monkeypatch):
    from contextlib import contextmanager
    import sys
    observe, step = observe_control_posts, OutboundNode.step
    observing, delays, facts = [], [], []
    @contextmanager
    def observed_posts(http):
        observing.append(True); began = time.monotonic()
        try:
            with observe(http) as posts:
                yield posts
                facts.append(posts.summary(time.monotonic() - began))
        finally: observing.clear()
    def held_step(self, *args, **kwargs):
        if observing:
            # Scheduling before a request begins does not extend its deadline.
            time.sleep(.6); delays.append(True)
        return step(self, *args, **kwargs)
    monkeypatch.setattr(sys.modules[__name__], 'observe_control_posts', observed_posts)
    monkeypatch.setattr(OutboundNode, 'step', held_step)
    run_capacity_fixture(project_node, capacity_service, 'normal')
    assert len(delays) == 3 and facts[0]['elapsed_ms'] >= 1800
    assert facts[0]['post_count'] == 6 and not facts[0]['rows_truncated']
    assert all(row['outcome'] == 'RETURNED' for row in facts[0]['posts'])


@pytest.mark.parametrize('release_fails', [False, True])
def test_capacity_callback_original_survives_unknown_and_armed_scope(project_node, capacity_service, monkeypatch, release_fails):
    from vibemql5.fleet.scoped_resources import ScopedLease
    from vibemql5.fleet.job_journal import JournalError
    fault, cause, release_fault = RuntimeError('CALLBACK'), RuntimeError('CAUSE'), JournalError('SCOPE_RELEASE')
    fault.add_note('original callback note'); release_fault.add_note('original release note')
    close, save, outcome = ScopedLease.close_zero_attempt, ScopedResourceCoordinator._save, NodeJobJournal._outcome
    scopes, outcomes = [], []
    def failed_close(self, expected):
        if not scopes:
            scopes.append(self); raise fault from cause
        return close(self, expected)
    def failed_save(db, record):
        if release_fails and record['phase'] == 'ARMED' and record['status'] == 'UNKNOWN': raise release_fault
        return save(db, record)
    def observed_outcome(self, record, state, result):
        row = outcome(self, record, state, result)
        outcomes.append((row['state'], (row['result'] or {}).get('reason_code')))
        return row
    monkeypatch.setattr(ScopedLease, 'close_zero_attempt', failed_close)
    monkeypatch.setattr(ScopedResourceCoordinator, '_save', staticmethod(failed_save))
    monkeypatch.setattr(NodeJobJournal, '_outcome', observed_outcome)
    with pytest.raises(BaseException) as observed:
        run_capacity_fixture(project_node, capacity_service, 'normal')
    if release_fails:
        assert isinstance(observed.value, BaseExceptionGroup) and observed.value.exceptions == (fault, release_fault)
        assert release_fault.__context__ is fault and release_fault.__notes__ == ['original release note']
    else: assert observed.value is fault
    assert fault.__cause__ is cause and fault.__notes__[0] == 'original callback note'
    assert ('UNKNOWN', 'EXECUTION_OUTCOME_UNKNOWN') in outcomes
    retained = scopes[0].load()
    assert retained['phase'] == 'ARMED'
    assert retained['status'] == ('ACQUIRED' if release_fails else 'UNKNOWN')
    assert not (project_node['root'] / 'state' / 'fleet' / 'scoped-install.json').exists()


def test_capacity_primary_late_callback_and_cleanup_keep_original_union(project_node, capacity_service, monkeypatch):
    import sys
    from vibemql5.fleet.scoped_resources import ScopedLease
    primary, late, cleanup = WireError('HTTPS_UNAVAILABLE'), RuntimeError('LATE_CALLBACK'), RuntimeError('CLEANUP')
    for error, note in ((primary, 'primary note'), (late, 'callback note'), (cleanup, 'cleanup note')): error.add_note(note)
    read, close_scope, close = FleetClientFacade.get_job, ScopedLease.close_zero_attempt, close_dispatcher_fixture
    injected, scopes = [], []
    def failed_read(*args, **kwargs):
        if not injected: injected.append(True); raise primary
        return read(*args, **kwargs)
    def failed_scope(self, expected):
        if not scopes: scopes.append(self); raise late
        return close_scope(self, expected)
    def failed_cleanup(agent, dispatcher, pump, **kwargs):
        close(agent, dispatcher, pump, **kwargs)
        # Dispose only the already-drained temporary owners before injecting
        # this test's cleanup error; keep the uncertain scope record intact.
        dispatcher.native.close(); dispatcher.journal.close(); agent.client.transport_journal.close()
        raise cleanup
    monkeypatch.setattr(FleetClientFacade, 'get_job', failed_read)
    monkeypatch.setattr(ScopedLease, 'close_zero_attempt', failed_scope)
    monkeypatch.setattr(sys.modules[__name__], 'close_dispatcher_fixture', failed_cleanup)
    with pytest.raises(BaseExceptionGroup) as observed:
        run_capacity_fixture(project_node, capacity_service, 'normal')
    assert observed.value.exceptions == (primary, cleanup, late)
    assert [error.__notes__ for error in observed.value.exceptions] == [['primary note'], ['cleanup note'], ['callback note']]
    assert scopes[0].load()['phase'] == 'ARMED' and scopes[0].load()['status'] == 'UNKNOWN'
