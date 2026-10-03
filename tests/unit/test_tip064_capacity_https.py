"""Actual TLS and scoped concurrency; signed claims remain synthetic, no MT5 PASS."""
from __future__ import annotations

import base64
import copy
import hashlib
import threading
import time
from dataclasses import replace
from queue import Queue

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_tip058b_transport import TOKEN, control_policy, fleet_policy, positive, tls_files
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
from vibemql5.fleet.transport import GatewayController, HttpsClient, NodeClient, OutboundNode, OwnerClient, serve_gateway
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
def capacity_service(tmp_path, tls_files):
    ca, certificate, private = tls_files
    stopped, ready, failures = threading.Event(), Queue(), Queue()
    signer_key, owner_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    owner_public = owner_key.public_key().public_bytes_raw().hex()
    policy = replace(fleet_policy(), max_body_bytes=262144, max_response_bytes=262144)
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
    def run():
        try:
            serve_gateway(('127.0.0.1', 0), certificate=certificate, key_file=private,
                controller_factory=factory, stop_event=stopped, started=ready.put)
        except BaseException as error: failures.put(error)
    thread = threading.Thread(target=run, daemon=True); thread.start()
    address = ready.get(timeout=5)
    http = HttpsClient('https://127.0.0.1:' + str(address[1]), policy, cafile=str(ca))
    yield http, OwnerClient(http, TOKEN), signer_key, owner_key, policy
    stopped.set(); thread.join(timeout=3)
    assert not thread.is_alive()
    if not failures.empty(): raise failures.get()


def test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued(project_node, capacity_service):
    http, owner, signer_key, owner_key, policy = capacity_service
    root, device = project_node['root'], project_node['registry']['device_id']
    signed, load, closure, requests = signed_roster(project_node, owner_key)
    roster = verify_capacity_roster(signed, device_id=device, route_generation=1,
        trusted_owner_public_key=owner_key.public_key().public_bytes_raw().hex(), load_receipt=load, closure_receipt=closure)
    # These actual harmless scopes have private test provenance and no marker.
    coordinator = ScopedResourceCoordinator._for_fixture(root, signed['body'], initialize=True)
    entered, release, calls = Queue(), threading.Event(), []
    class ScopedHarmlessAdapter:
        def reserve(self, request, operation, exact_fence):
            assert type(exact_fence['authorization']) is NativeAuthorization
            return {'local_job_id': exact_fence['local_job_id']}
        def start_reserved(self, local_job_id, request, exact_fence):
            assert type(exact_fence['authorization']) is NativeAuthorization
            selected = request['placement']['target']
            with coordinator.execution(local_job_id, kind='tester', terminal_id=selected['terminal_id'],
                    terminal_generation=selected['terminal_generation'], wait_ms=1000) as scope:
                armed = scope.arm(); calls.append(local_job_id); entered.put(local_job_id)
                assert release.wait(5)
                scope.close_zero_attempt(armed)
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
    try:
        agent.step()
        payload = {'signed_profile': signed, 'load_receipt_base64': base64.b64encode(load).decode(),
            'closure_receipt_base64': base64.b64encode(closure).decode()}
        forged = copy.deepcopy(payload); forged['signed_profile']['signature'] = '0' * 128
        with pytest.raises(WireError): client.register_capacity(agent.session_id, **forged)
        registered = client.register_capacity(agent.session_id, **payload)
        assert registered['profile_sha256'] == roster.profile_sha256
        launched = [facade.launch_job('capacity-native-' + str(index), request) for index, request in enumerate(requests)]
        pump(agent, lambda: entered.qsize() == 2)
        assert dispatcher.native_capacity == 2
        assert len({entered.get_nowait(), entered.get_nowait()}) == 2
        with coordinator.transaction() as db:
            from vibemql5.fleet.job_journal import _decode
            active = [_decode(row[0]) for row in db.execute('SELECT record FROM reservations')]
            assert len(active) == 2 and all(row['phase'] == 'ARMED' and row['status'] == 'ACQUIRED' for row in active)
        third = facade.launch_job('capacity-conflicting-third', requests[0])
        began = time.monotonic()
        for _ in range(3): agent.step()
        assert time.monotonic() - began < 1.5
        assert len(calls) == 2 and facade.get_job(third['global_job_id'])['state'] == 'QUEUED'
        assert all(facade.get_job(row['global_job_id'])['state'] == 'STARTING' for row in launched)
        release.set()
        pump(agent, lambda: all(facade.get_job(row['global_job_id'])['state'] == 'SUCCEEDED' for row in launched + [third]))
        assert len(calls) == 3
        for row in launched + [third]:
            assert facade.get_job(row['global_job_id'])['result']['result']['evidence'] == 'SYNTHETIC_NATIVE_ONLY'
        assert not (root / 'state' / 'fleet' / 'scoped-install.json').exists()
    finally:
        release.set()
        pump(agent, lambda: not dispatcher.has_pending_work())
        dispatcher.close(); jobs.close(); domains.close(); transport.close()
