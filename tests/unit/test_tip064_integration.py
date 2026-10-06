"""Finite source composition. Positive fixtures never qualify MT5 or a host."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from test_tip057rc1 import fixture as local_identity
from test_tip058b_transport import control_policy, fleet_policy, tls_files, positive, TOKEN, FixtureHttpsClient
from fleet_gateway_fixture import preserve_fixture_failure, stop_gateway_fixture, close_dispatcher_fixture, start_gateway_fixture
from vibemql5.adapters.fleet_client_tools import FleetClientFacade, FLEET_TOOL_NAMES
from vibemql5.adapters.fleet_mcp import create_server
from vibemql5.core.facade import ToolFacade
from vibemql5.fleet.domain import DomainJournal, DomainPolicy, GatewayDomain, NodeDomainDispatcher
from vibemql5.fleet.sdk_qualification import QualificationError, QualifiedSdkInstallation
from vibemql5.fleet.wire import WireError
from vibemql5.fleet.job_journal import STATES


def domain_policy():
    return DomainPolicy(max_records=20, max_payload_bytes=32768, wait_ms=50,
                        max_commands=4, start_authorization_ms=2000)


def protected_file(path, content):
    """Exercise the same protected creation handle on both source CI platforms."""
    from vibemql5.fleet.node_keys import _windows_create, _windows_acl, _check
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != 'nt': path.parent.chmod(0o700)
    descriptor = _windows_create(path) if os.name == 'nt' else os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        if os.name == 'nt': _windows_acl(descriptor, set_restrictive=True)
        _check(descriptor)
        os.write(descriptor, content); os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def test_protected_principal_only_startup_pins_ca_and_never_reads_owner_secret(tmp_path, tls_files, monkeypatch):
    from dataclasses import asdict
    from cryptography.hazmat.primitives import serialization
    from vibemql5.adapters import fleet_client_tools
    secrets_dir = tmp_path / 'secrets'
    key = Ed25519PrivateKey.generate()
    protected_file(secrets_dir / 'principal.pem', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ca = protected_file(secrets_dir / 'ca.pem', tls_files[0].read_bytes())
    credential = tmp_path / 'credential.json'; credential.write_text('{}')
    config = {'schema': 'fleet.client-config/1', 'origin': 'https://localhost:8443', 'ca_file': str(ca),
        'fleet_policy': asdict(fleet_policy()), 'owner_token_file': None,
        'principal_key_file': str(secrets_dir / 'principal.pem'), 'principal_credential_file': str(credential)}
    path = protected_file(secrets_dir / 'client.json', json.dumps(config).encode())
    opened = []; original = fleet_client_tools.private_bytes
    def read(selected, maximum):
        opened.append(str(selected)); return original(selected, maximum)
    monkeypatch.setattr(fleet_client_tools, 'private_bytes', read)
    # The configured CA path is never reopened by HTTPS after this retained read.
    facade = FleetClientFacade.from_config(path)
    assert facade.owner is None and opened == [str(path), str(ca)]
    assert facade.server_info()['authority_modes'] == ['PRINCIPAL']
    attempts = []
    monkeypatch.setattr(facade.http, 'post', lambda *args, **kwargs: attempts.append(args) or {})
    for action in (lambda: facade.inventory(), lambda: facade.get_job('x'), lambda: facade.read_status('x'),
                   lambda: facade.principal('issue', {}), lambda: facade.admin('grant', {})):
        with pytest.raises(WireError, match='OWNER_CREDENTIAL_REQUIRED'): action()
    assert attempts == []


def test_operator_tls_context_pins_validated_bytes_and_cleans_private_staging(tmp_path, tls_files, monkeypatch):
    from vibemql5.adapters import fleet_cli
    certificate = protected_file(tmp_path / 'secrets' / 'certificate.pem', tls_files[1].read_bytes())
    key = protected_file(tmp_path / 'secrets' / 'key.pem', tls_files[2].read_bytes())
    staged = []; original = fleet_cli.tempfile.mkdtemp
    def directory(**kwargs):
        location = original(**kwargs); staged.append(Path(location)); return location
    monkeypatch.setattr(fleet_cli.tempfile, 'mkdtemp', directory)
    context = fleet_cli.operator_server_context(certificate, key)
    assert context.minimum_version >= __import__('ssl').TLSVersion.TLSv1_2
    assert len(staged) == 1 and not staged[0].exists()
    # SSL owns the loaded key; the original operator file is never reopened.
    key.unlink()
    assert context.protocol == __import__('ssl').PROTOCOL_TLS_SERVER


def test_actual_protected_gateway_factory_and_owner_client_startup(tmp_path, tls_files):
    import socket
    from dataclasses import asdict
    from cryptography.hazmat.primitives import serialization
    from fleet_writer_fixture import principal_policy, wait_gateway_started
    from vibemql5.adapters.fleet_cli import gateway_factory, operator_server_context
    from vibemql5.adapters.fleet_client_tools import operator_configuration
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    origin = 'https://127.0.0.1:' + str(port)
    private_dir = tmp_path / 'secrets'
    authority = Ed25519PrivateKey.generate()
    protected_file(private_dir / 'authority.pem', authority.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    protected_file(private_dir / 'owner.txt', TOKEN.encode())
    protected_file(private_dir / 'ca.pem', tls_files[0].read_bytes())
    protected_file(private_dir / 'certificate.pem', tls_files[1].read_bytes())
    protected_file(private_dir / 'tls-key.pem', tls_files[2].read_bytes())
    config = {'schema': 'fleet.gateway-config/1', 'origin': origin, 'listen_host': '127.0.0.1', 'listen_port': port,
        'certificate_file': str(private_dir / 'certificate.pem'), 'tls_key_file': str(private_dir / 'tls-key.pem'),
        'owner_token_file': str(private_dir / 'owner.txt'), 'control_path': str(tmp_path / 'control.sqlite'),
        'control_policy': asdict(control_policy()), 'fleet_policy': asdict(fleet_policy()),
        'domain_path': str(tmp_path / 'domains.sqlite'), 'domain_policy': asdict(domain_policy()),
        'jobs_path': str(tmp_path / 'jobs.sqlite'), 'journal_policy': {'max_records': 20, 'max_payload_bytes': 262144, 'wait_ms': 1000},
        'authority_key_file': str(private_dir / 'authority.pem'), 'principal_path': str(tmp_path / 'principals.json'),
        'principal_policy': asdict(principal_policy()), 'capacity_owner_public_key': None, 'recovery': None}
    path = protected_file(private_dir / 'gateway.json', json.dumps(config).encode())
    checked = operator_configuration(path)
    factory = gateway_factory(checked, initialize=True)
    context = operator_server_context(checked['certificate_file'], checked['tls_key_file'])
    stopped, ready, failures = threading.Event(), Queue(), Queue()
    def run():
        try:
            serve_gateway(('127.0.0.1', port), ssl_context=context, controller_factory=factory,
                stop_event=stopped, started=ready.put)
        except BaseException as error: failures.put(error)
    thread = threading.Thread(target=run, daemon=True); thread.start()
    try:
        assert wait_gateway_started(ready, failures, thread)[1] == port
        client_config = {'schema': 'fleet.client-config/1', 'origin': origin, 'ca_file': str(private_dir / 'ca.pem'),
            'fleet_policy': asdict(fleet_policy()), 'owner_token_file': str(private_dir / 'owner.txt'),
            'principal_key_file': None, 'principal_credential_file': None}
        selected = protected_file(private_dir / 'client.json', json.dumps(client_config).encode())
        owner = FleetClientFacade.from_config(selected)
        assert owner.server_info()['authority_modes'] == ['OWNER']
        assert owner.inventory()['status'] == 'READY_CONTROL_ONLY'
        with pytest.raises(WireError, match='FLEET_INITIALIZATION_EXISTS'):
            gateway_factory(checked, initialize=True)
    finally:
        stopped.set(); thread.join(timeout=3)
        assert not thread.is_alive()
        if not failures.empty(): raise failures.get()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX writable-mode rejection; Windows protected-owner/ACL positive is tested separately')
def test_operator_config_writable_or_symlink_rejected_before_https(tmp_path, monkeypatch):
    from vibemql5.adapters import fleet_client_tools
    attempts = []
    monkeypatch.setattr(fleet_client_tools, 'HttpsClient', lambda *args, **kwargs: attempts.append(args))
    path = protected_file(tmp_path / 'secrets' / 'config.json', b'{}')
    path.chmod(0o666)
    with pytest.raises(WireError, match='FLEET_OPERATOR_CONFIG_UNTRUSTED'): FleetClientFacade.from_config(path)
    path.chmod(0o600)
    link = path.parent / 'symlink.json'; link.symlink_to(path)
    with pytest.raises(WireError, match='FLEET_OPERATOR_CONFIG_UNTRUSTED'): FleetClientFacade.from_config(link)
    assert attempts == []


@pytest.mark.parametrize("operation", ["get_terminal_live_state", "get_account_snapshot"])
def test_legacy_positive_route_cannot_use_installed_local_sdk_capability(local_identity, monkeypatch, operation):
    from vibemql5.fleet import sdk_controller
    attempts = []
    # Type-only routing fixture. It cannot pass actual manifest/host validation.
    installation = object.__new__(QualifiedSdkInstallation)
    monkeypatch.setattr(sdk_controller, "read_local", lambda *args, **kwargs: attempts.append("SDK") or {})
    facade = ToolFacade(local_identity.root, sdk_installation=installation)
    routed = {**local_identity.target, "route_generation": 1}
    result = getattr(facade, operation)(routed)
    assert result["reason_code"] == "ROUTED_NATIVE_NOT_ENABLED"
    assert result["source"] is result["account"] is None
    assert attempts == []
    assert not facade.concurrency.audit_path.exists()


@pytest.mark.parametrize("operation", ["get_terminal_live_state", "get_account_snapshot"])
def test_local_trusted_sdk_dispatch_happens_before_any_c1_lease(local_identity, monkeypatch, operation):
    from vibemql5.fleet import sdk_controller
    installation = object.__new__(QualifiedSdkInstallation)
    calls = []
    def routed(root, concurrency, selected_operation, selected, installed):
        assert root == local_identity.root and installed is installation
        assert not concurrency.audit_path.exists()
        calls.append((selected_operation, selected))
        return {"status": "ROUTING_FIXTURE_ONLY"}
    monkeypatch.setattr(sdk_controller, "read_local", routed)
    facade = ToolFacade(local_identity.root, sdk_installation=installation)
    assert getattr(facade, operation)(local_identity.target) == {"status": "ROUTING_FIXTURE_ONLY"}
    assert calls == [(operation, local_identity.target)]


def test_caller_dict_or_boolean_cannot_install_sdk(local_identity):
    for value in ({"qualified": True}, True, object()):
        with pytest.raises(QualificationError):
            ToolFacade(local_identity.root, sdk_installation=value)


def test_finite_domain_replay_conflict_restart_and_unknown_effect(tmp_path):
    policy = domain_policy()
    node = {"device_id": "dev_" + "a" * 32, "route_generation": 1}
    gateway = DomainJournal(tmp_path / "gateway.sqlite", policy=policy, role="GATEWAY", initialize=True)
    worker = DomainJournal(tmp_path / "node.sqlite", policy=policy, role="NODE", initialize=True)
    payload = {"project_id": "P"}
    first = gateway.submit("/fleet/v1/projects/get", node, payload, "op1")
    assert gateway.submit("/fleet/v1/projects/get", node, payload, "op1") == first
    with pytest.raises(WireError, match="DOMAIN_OPERATION_CONFLICT"):
        gateway.submit("/fleet/v1/projects/get", node, {"project_id": "other"}, "op1")
    command = gateway.poll(node["device_id"], 1, "session-a", 1)[0]
    worker.receive(command, node["device_id"], 1, "session-a")
    calls = []
    class Interrupted:
        def apply(self, record):
            calls.append(record["command_id"])
            raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        worker.execute(first["command_id"], Interrupted())
    worker.close()
    worker = DomainJournal(tmp_path / "node.sqlite", policy=policy, role="NODE")
    assert worker.get(first["command_id"])["state"] == "UNKNOWN"
    worker.execute(first["command_id"], Interrupted())
    assert len(calls) == 1
    worker.close(); gateway.close()


def test_domain_dispatch_duplicate_delivery_commits_same_node_result(tmp_path):
    policy = domain_policy()
    node = {"device_id": "dev_" + "a" * 32, "route_generation": 1}
    gateway = DomainJournal(tmp_path / "gateway.sqlite", policy=policy, role="GATEWAY", initialize=True)
    worker = DomainJournal(tmp_path / "node.sqlite", policy=policy, role="NODE", initialize=True)
    record = gateway.submit("/fleet/v1/projects/get", node, {"project_id": "P"}, "op1")
    command = gateway.poll(node["device_id"], 1, "session-a", 1)[0]
    calls = []
    class Fixture:
        def apply(self, value):
            calls.append(value["command_id"])
            return {"source": "SYNTHETIC_TEST", "project_id": "P"}
    received = worker.receive(command, node["device_id"], 1, "session-a")
    completed = worker.execute(received["command_id"], Fixture())
    repeated = worker.execute(received["command_id"], Fixture())
    assert repeated == completed and len(calls) == 1
    result = {"schema": "fleet.domain-result/1", "session_id": "session-a",
        **{key: completed[key] for key in ("command_id", "node", "request_sha256", "state", "sequence", "result")}}
    assert not gateway.commit(result, node["device_id"], 1, "session-a")["recovered"]
    assert gateway.commit(result, node["device_id"], 1, "session-a")["recovered"]
    with pytest.raises(WireError, match="DOMAIN_RESULT_MISMATCH"):
        gateway.commit(result, "dev_" + "b" * 32, 1, "session-a")
    worker.close(); gateway.close()


class ClientFixture:
    def server_info(self):
        return {"source": "CATALOG_FIXTURE"}


def test_optional_catalog_is_separate_and_does_not_start_service(monkeypatch):
    from vibemql5.fleet.gateway_control import GatewayControlStore
    monkeypatch.setattr(GatewayControlStore, "initialize", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("client spawned gateway")))
    server = create_server(client_facade=ClientFixture())
    assert tuple(server._tool_manager._tools) == FLEET_TOOL_NAMES
    assert len(FLEET_TOOL_NAMES) == 31
    from vibemql5.contracts import MCP_TOOL_COUNT
    assert MCP_TOOL_COUNT == 85


@pytest.mark.parametrize("corruption", ["extra_table", "trigger", "column", "record_field", "id_mapping", "sequence", "result", "noncanonical", "oversize", "capacity"])
def test_domain_corruption_is_bounded_and_rejected_on_reopen(tmp_path, corruption, monkeypatch):
    path = tmp_path / "domain.sqlite"
    policy = domain_policy()
    node = {"device_id": "dev_" + "a" * 32, "route_generation": 1}
    journal = DomainJournal(path, policy=policy, role="GATEWAY", initialize=True)
    row = journal.submit("/fleet/v1/projects/get", node, {"project_id": "P"}, "op1")
    journal.close()
    connection = sqlite3.connect(path)
    if corruption == "extra_table":
        connection.execute("CREATE TABLE intrusion(value)")
    elif corruption == "trigger":
        connection.execute("CREATE TRIGGER intrusion AFTER UPDATE ON commands BEGIN SELECT 1; END")
    elif corruption == "column":
        connection.execute("ALTER TABLE commands ADD COLUMN extra TEXT")
    elif corruption == "id_mapping":
        connection.execute("UPDATE commands SET operation_id='changed'")
    elif corruption == "capacity":
        for index in range(policy.max_records):
            changed = {**row, "operation_id": "op" + str(index + 2), "command_id": "dcmd_" + f"{index + 1:032x}"}
            connection.execute("INSERT INTO commands VALUES (?,?,?)", (changed["operation_id"], changed["command_id"], __import__('vibemql5.fleet.wire', fromlist=['encode_body']).encode_body(changed, policy.max_payload_bytes).decode()))
    else:
        if corruption == "record_field": row["extra"] = True
        elif corruption == "sequence": row["sequence"] = True
        elif corruption == "result": row["result"] = {"fake": True}
        raw = json.dumps(row, sort_keys=True, separators=(",", ":"))
        if corruption == "noncanonical": raw += " "
        elif corruption == "oversize": raw = " " * (policy.max_payload_bytes + 1)
        connection.execute("UPDATE commands SET record=?", (raw,))
    connection.commit(); connection.close()
    decoded = []
    if corruption in {"oversize", "capacity"}:
        from vibemql5.fleet import domain
        original = domain.decode_body
        monkeypatch.setattr(domain, "decode_body", lambda raw, maximum: decoded.append(len(raw)) or original(raw, maximum))
    with pytest.raises(WireError, match="DOMAIN_STORAGE_INVALID"):
        DomainJournal(path, policy=policy, role="GATEWAY")
    # Meta may be decoded; no oversized record or over-capacity row set is parsed.
    assert all(size < policy.max_payload_bytes for size in decoded)


@pytest.mark.parametrize("change", [{"sequence": True}, {"sequence": 3}, {"state": "COMPLETED", "result": {}}, {"result": {}}, {"extra": 1}, {"command_id": "caller-path"}])
def test_domain_malformed_delivery_rejected_before_any_durable_intent(tmp_path, change):
    policy = domain_policy()
    node = {"device_id": "dev_" + "a" * 32, "route_generation": 1}
    gateway = DomainJournal(tmp_path / "gateway.sqlite", policy=policy, role="GATEWAY", initialize=True)
    worker = DomainJournal(tmp_path / "node.sqlite", policy=policy, role="NODE", initialize=True)
    gateway.submit("/fleet/v1/projects/get", node, {"project_id": "P"}, "op1")
    command = gateway.poll(node["device_id"], 1, "session-a", 1)[0]
    with pytest.raises(WireError):
        worker.receive({**command, **change}, node["device_id"], 1, "session-a")
    assert worker.control_head()["record_count"] == 0
    worker.close(); gateway.close()


def test_domain_initialization_and_transaction_interruption_leave_complete_or_absent_state(tmp_path):
    path = tmp_path / "domain.sqlite"
    with pytest.raises(WireError):
        DomainJournal(path, policy=replace(domain_policy(), max_payload_bytes=1), role="GATEWAY", initialize=True)
    assert not path.exists()
    journal = DomainJournal(path, policy=domain_policy(), role="GATEWAY", initialize=True)
    original = journal.control_head()
    def interrupted():
        journal._db.execute("DELETE FROM meta")
        raise SystemExit("fixture interruption")
    with pytest.raises(SystemExit): journal._atomic(interrupted)
    assert journal.control_head() == original
    journal.close()

# Full composition fixtures use ephemeral TLS keys and harmless callbacks only.
from test_tip061a_057n import node as project_node, freeze, logical_fixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from vibemql5.fleet.transport import GatewayController, HttpsClient, NodeClient, OutboundNode, OwnerClient, serve_gateway
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal, NodeJobJournal
from vibemql5.fleet.native import RoutedNativeAdapter, SyntheticNativeAdapter, native_request
from vibemql5.fleet.native_authorization import GatewayNativeSigner, NativeAuthorization, NativeAuthorizationVerifier
from vibemql5.fleet.node_transport_journal import NodeTransportJournal, TransportPolicy
from vibemql5.fleet.read_broker import ReadBroker
from vibemql5.core.native_ownership import current_identity
import threading
import time
from queue import Queue

LONG_FIXTURE_PROFILE = pytest.param({'authorization_ms': 1000, 'positive_transport': True}, id='1000')


@pytest.fixture
def composed_service(tmp_path, tls_files, request):
    ca, certificate, private = tls_files
    failures = Queue()
    signing_key = Ed25519PrivateKey.generate()
    selected = getattr(request, "param", 2000)
    authorization_ms = selected['authorization_ms'] if isinstance(selected, dict) else selected
    # Only the long-phase positives opt in. Signed grant TTL is independent.
    http_policy = (replace(fleet_policy(), http_timeout_ms=5000, heartbeat_interval_ms=5000)
        if isinstance(selected, dict) and selected.get('positive_transport') else fleet_policy())
    def factory(address):
        origin = 'https://127.0.0.1:' + str(address[1])
        policy = replace(control_policy(), max_operations=1000, max_nonces=1000)
        store = GatewayControlStore.initialize(tmp_path / 'composed-control.sqlite', policy=policy)
        jobs = GatewayJobJournal(tmp_path / 'composed-jobs.sqlite', initialize=True,
            max_records=20, max_payload_bytes=262144, wait_ms=1000)
        domains = DomainJournal(tmp_path / 'composed-domain.sqlite', initialize=True, role='GATEWAY', policy=domain_policy())
        signer = GatewayNativeSigner(signing_key, origin, max_authorization_ms=authorization_ms)
        from fleet_writer_fixture import principal_policy
        from vibemql5.fleet.principals import GatewayPrincipalAuthority
        principals = GatewayPrincipalAuthority(tmp_path / 'composed-principals.json', signing_key=signing_key,
            audience=origin, policy=principal_policy(), initialize=True)
        domain = GatewayDomain(store, domains, jobs, native_signer=signer, start_authorization_ms=authorization_ms,
            principal_authority=principals)
        return GatewayController(store, http_policy, audience=origin,
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
            broker=ReadBroker.for_synthetic_tests(http_policy), domain=domain)
    stopped, thread, address = start_gateway_fixture(('127.0.0.1', 0), certificate=certificate,
        key_file=private, controller_factory=factory, failures=failures, startup_timeout=5, stop_timeout=3)
    http = FixtureHttpsClient('https://127.0.0.1:' + str(address[1]), http_policy, cafile=str(ca),
        server_thread=thread, failures=failures)
    try:
        yield http, OwnerClient(http, TOKEN), signing_key
    finally:
        with preserve_fixture_failure():
            stop_gateway_fixture(stopped, thread, failures)


def runtime(project_node, composed_service, *, adapter=None, authorization_diagnostics=None):
    root, device = project_node['root'], project_node['registry']['device_id']
    http, owner, signing_key = composed_service
    key = Ed25519PrivateKey.generate()
    transport = NodeTransportJournal.initialize(root / 'node-transport.sqlite',
        TransportPolicy(max_records=1000, max_payload_bytes=262144, wait_ms=1000),
        device_id=device, public_key=key.public_key().public_bytes_raw().hex(), audience=http.origin)
    grant = owner.admin('grant', {'device_id': device, 'public_key': key.public_key().public_bytes_raw().hex(),
        'operation_id': 'grant-composed', 'expected_revision': 1, 'expected_route_generation': None})
    client = NodeClient(http, key, device, 0, transport_journal=transport)
    client.pair(grant_id=grant['receipt']['grant_id'], secret=grant['secret'], operation_id='pair-composed', expected_revision=2)
    jobs = NodeJobJournal(root / 'node-jobs.sqlite', initialize=True, max_records=20, max_payload_bytes=262144, wait_ms=1000)
    domains = DomainJournal(root / 'node-domain.sqlite', initialize=True, role='NODE', policy=domain_policy())
    verifier = NativeAuthorizationVerifier(signing_key.public_key().public_bytes_raw().hex(), http.origin,
        clock_ms=lambda: int(time.time() * 1000))
    if authorization_diagnostics is not None: authorization_diagnostics.instrument(verifier)
    from fleet_writer_fixture import writer_policy
    from vibemql5.fleet.writers import NodePrincipalRuntime
    writers = NodePrincipalRuntime(root, gateway_public_key=signing_key.public_key().public_bytes_raw(), audience=http.origin,
        device_id=device, route_generation=1, session_id='session-composed', policy=writer_policy(), initialize=True)
    dispatcher = NodeDomainDispatcher(root, domains, jobs, adapter or RoutedNativeAdapter(root),
        principal_runtime=writers, authorization_verifier=verifier, max_inventory_rows=20)
    agent = OutboundNode(client, root, http.policy, session_id='session-composed',
        domain_dispatcher=dispatcher, synthetic_read_adapter=positive)
    return FleetClientFacade(owner), client, agent, dispatcher, jobs, domains, transport


def pump(agent, predicate, *, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        agent.step()
        if predicate(): return
        time.sleep(.005)
    pytest.fail('bounded fixture did not reach expected state')


class NativeDenialObservation:
    """Keep finite facts from the original predicate reads; issue no new reads."""
    def __init__(self, read):
        self.read, self.count, self.last = read, 0, None

    def __call__(self):
        row = self.read()
        self.count = min(self.count + 1, 2147483647)
        if type(row) is dict:
            state, sequence = row.get('state'), row.get('sequence')
            result = row.get('result')
            nested = result.get('result') if type(result) is dict else None
            reason = nested.get('reason_code') if type(nested) is dict else None
            self.last = {
                'state': state if type(state) is str and state in STATES else 'OTHER',
                'sequence': sequence if type(sequence) is int and 0 <= sequence <= 2147483647 else None,
                'reason_code': reason if type(reason) is str and reason in {
                    'NATIVE_QUALIFICATION_UNAVAILABLE', 'NATIVE_RECOVERY_REQUIRED'} else None if reason is None else 'OTHER'}
        else:
            self.last = {'state': 'OTHER', 'sequence': None, 'reason_code': 'OTHER'}
        return row['state'] == 'FAILED'

    def snapshot(self):
        return {'predicate_reads': self.count, 'last_returned_job': self.last}


def pump_native_denial_fixture(agent, observation):
    try: pump(agent, observation)  # Keep the original three-second pump budget.
    except BaseException as error:
        error.add_note('NATIVE_DENIAL_FIXTURE ' + json.dumps(observation.snapshot(), sort_keys=True))
        raise


def close_native_denial_fixture(resources):
    with preserve_fixture_failure():
        errors = []
        for resource in resources:
            try: resource.close()
            except BaseException as error: errors.append(error)
        if len(errors) == 1: raise errors[0]
        if errors: raise BaseExceptionGroup('native denial fixture cleanup failed', errors)


def test_native_denial_observation_retains_only_original_reads_and_safe_last_state():
    marker = 'sensitive-job-id-path-body-reason'
    rows = [
        {'state': 'STARTING', 'sequence': 4, 'result': None, 'global_job_id': marker},
        {'state': 'FAILED', 'sequence': 5, 'result': {'result': {'reason_code': 'NATIVE_QUALIFICATION_UNAVAILABLE'}}},
        {'state': marker, 'sequence': True, 'result': {'result': {'reason_code': marker}}}]
    calls = []
    def read():
        calls.append('read'); return rows[len(calls) - 1]
    observation = NativeDenialObservation(read)
    assert observation() is False and observation.snapshot() == {
        'predicate_reads': 1, 'last_returned_job': {'state': 'STARTING', 'sequence': 4, 'reason_code': None}}
    assert observation() is True and observation.snapshot()['last_returned_job']['reason_code'] == 'NATIVE_QUALIFICATION_UNAVAILABLE'
    assert observation() is False
    assert calls == ['read'] * 3 and marker not in json.dumps(observation.snapshot())
    assert observation.snapshot()['last_returned_job'] == {'state': 'OTHER', 'sequence': None, 'reason_code': 'OTHER'}


def test_native_denial_original_predicate_failure_and_cleanup_identity_are_preserved(monkeypatch):
    from types import SimpleNamespace
    primary = WireError('HTTPS_UNAVAILABLE'); primary.add_note('retained original note')
    first, second = RuntimeError('first cleanup'), RuntimeError('second cleanup')
    calls, databases = [], [sqlite3.connect(':memory:'), sqlite3.connect(':memory:')]
    def read():
        calls.append('read'); raise primary
    observation = NativeDenialObservation(read)
    monkeypatch.setitem(pump_native_denial_fixture.__globals__, 'pump', lambda agent, predicate: predicate())
    def close(index, error):
        calls.append(index); databases[index].close(); raise error
    try:
        with pytest.raises(BaseExceptionGroup) as caught:
            try: pump_native_denial_fixture(None, observation)
            finally:
                close_native_denial_fixture([SimpleNamespace(close=lambda: close(0, first)),
                                            SimpleNamespace(close=lambda: close(1, second))])
        assert caught.value.exceptions[0] is primary
        assert caught.value.exceptions[1].exceptions == (first, second)
        assert primary.__notes__[0] == 'retained original note'
        assert observation.snapshot() == {'predicate_reads': 0, 'last_returned_job': None}
        assert calls == ['read', 0, 1]
        for db in databases:
            with pytest.raises(sqlite3.ProgrammingError): db.execute('SELECT 1')
    finally:
        for db in databases: db.close()


def test_native_denial_timeout_retains_last_predicate_state_without_additional_read(monkeypatch):
    primary = AssertionError('controlled bounded timeout')
    calls = []
    observation = NativeDenialObservation(lambda: calls.append('read') or {'state': 'STARTING', 'sequence': 4, 'result': None})
    def timed_pump(agent, predicate):
        assert not predicate(); raise primary
    monkeypatch.setitem(pump_native_denial_fixture.__globals__, 'pump', timed_pump)
    with pytest.raises(AssertionError) as caught: pump_native_denial_fixture(None, observation)
    assert caught.value is primary and calls == ['read']
    assert json.loads(primary.__notes__[0].split(' ', 1)[1]) == {
        'predicate_reads': 1, 'last_returned_job': {'state': 'STARTING', 'sequence': 4, 'reason_code': None}}


def discover(facade, client, agent):
    node = {'device_id': client.device_id, 'route_generation': client.route_generation}
    admitted = facade.inventory(node, 'inventory-composed')
    agent.step()
    observed = facade.command_status(admitted['command_id'])
    assert observed['state'] == 'COMPLETED'
    inventory = observed['result']
    assert inventory['source'] == 'NODE_CONFIG_AND_LOCAL_PERSISTED_REGISTRY'
    assert inventory['terminal_runtime_observed'] is False
    selected = inventory['rows'][0]
    assert selected['running'] is selected['connected'] is None
    assert selected['sdk_readiness'] == 'NOT_OBSERVED'
    return node, selected['target']


def test_actual_tls_inventory_discovery_read_project_and_production_native_denial(project_node, composed_service, monkeypatch):
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service)
    try:
        node, selected = discover(facade, client, agent)
        assert selected['terminal_id'] == project_node['registry']['terminals'][0]['terminal_id']
        read = facade.read('get_account_snapshot', selected, 'read-discovered')
        agent.step()
        observed = facade.read_status(read['command_id'])['result']
        assert observed['resolved_target'] == selected and observed['source'] == 'SYNTHETIC_TEST'
        queued = facade.domain('/fleet/v1/projects/get', node, 'get-project', {'project_id': 'P'})
        agent.step()
        assert facade.command_status(queued['command_id'])['result']['project_id'] == 'P'
        frozen = freeze(project_node, target=selected)
        source = project_node['source'].read_bytes()
        request = native_request(frozen, logical_fixture(), [{'path': 'Experts/DemoEA.mq5',
            'sha256': hashlib.sha256(source).hexdigest(), 'bytes': len(source)}])
        queued = facade.launch_job('native-denial', request)
        observation = NativeDenialObservation(lambda: facade.get_job(queued['global_job_id']))
        pump_native_denial_fixture(agent, observation)
        denied = facade.get_job(queued['global_job_id'])
        assert denied['result']['result']['reason_code'] == 'NATIVE_QUALIFICATION_UNAVAILABLE'
        assert not list((project_node['root'] / 'runs').glob('*/job.json'))
        assert facade.launch_job('native-denial', request)['global_job_id'] == queued['global_job_id']
        from vibemql5.fleet.artifact_proxy import ArtifactProxy, validate_chunk, validate_complete
        proxy = ArtifactProxy(project_node['root'], node_id=client.device_id, installation_id='fixture-only',
            max_artifact_bytes=100, max_chunk_bytes=4)
        local_job_id = denied['local_job_id']
        directory = project_node['root'] / 'runs' / local_job_id
        directory.mkdir(parents=True)
        (directory / 'fixture.bin').write_bytes(b'12345678')
        scope = {'artifact_id': 'art_' + 'c' * 32, 'global_job_id': denied['global_job_id'],
            'local_job_id': local_job_id, 'frozen_target': selected}
        manifest = proxy.register(**scope, relative_path='fixture.bin')
        dispatcher.artifacts = proxy
        monkeypatch.setattr('vibemql5.core.jobs.JobManager.get_job', lambda *_: pytest.fail('artifact HTTP read restored job'))
        admitted = facade.domain('/fleet/v1/artifacts/manifest', node, 'artifact-manifest',
            {**scope, 'expected_sha256': manifest['sha256']})
        agent.step()
        assert facade.command_status(admitted['command_id'])['result'] == manifest
        chunks = []
        for offset in (0, 4):
            admitted = facade.domain('/fleet/v1/artifacts/chunk', node, 'artifact-chunk-' + str(offset),
                {**scope, 'expected_sha256': manifest['sha256'], 'offset': offset, 'length': 4})
            agent.step()
            receipt = facade.command_status(admitted['command_id'])['result']
            chunks.append(validate_chunk(receipt, manifest=manifest, offset=offset, length=4))
        assert validate_complete(b''.join(chunks), manifest) == b'12345678'
        with pytest.raises(WireError, match='DOMAIN_JOB_SCOPE_MISMATCH'):
            facade.domain('/fleet/v1/artifacts/manifest', node, 'artifact-wrong-scope',
                {**scope, 'local_job_id': 'BT-20261003-010000-ABC123', 'expected_sha256': manifest['sha256']})

    finally:
        close_native_denial_fixture([dispatcher,dispatcher.principals,jobs,domains,transport])


def composed_stop_runtime(agent, dispatcher, client, resources):
    """Actual stop methods around the already composed harmless node fixture."""
    from vibemql5.adapters.fleet_cli import NodeRuntime
    stopping = object.__new__(NodeRuntime)
    stopping.agent, stopping.dispatcher, stopping.client = agent, dispatcher, client
    stopping.policy, stopping.config = fleet_policy(), {'drain_timeout_ms': 1}
    stopping._resources = resources
    stopping._closed, stopping._stopping, stopping._drain_deadline = False, False, None
    stopping._coordinator, stopping._capacity_registered = None, False
    return stopping


def close_composed_stop_runtime(stopping, cancelled):
    with preserve_fixture_failure():
        cancelled.set()
        deadline = time.monotonic() + 2
        while stopping.dispatcher.has_pending_work() and time.monotonic() < deadline:
            try: stopping.run_once()
            except WireError as error:
                if error.code != 'FIXTURE_LOST_ACK': raise
            time.sleep(.005)
        assert stopping.close()['status'] == 'CLOSED'
        assert stopping.close()['status'] == 'CLOSED'


def test_composed_stop_fixture_initializes_normal_sentinels_and_closes_actual_resources():
    from types import SimpleNamespace
    events = []; cancelled = threading.Event(); db = sqlite3.connect(':memory:')
    def no_registration(*args, **kwargs):
        raise AssertionError('fixture must not register capacity or claim authority')
    agent = SimpleNamespace(step=lambda **kwargs: events.append(('step', kwargs)) or {'fixture': True})
    dispatcher = SimpleNamespace(has_pending_work=lambda: False, close=lambda: events.append('dispatcher-closed'))
    resource = SimpleNamespace(close=lambda: events.append('resource-closed') or db.close())
    stopping = composed_stop_runtime(agent, dispatcher,
        SimpleNamespace(heartbeat=no_registration, register_capacity=no_registration), [resource])
    try:
        assert stopping._coordinator is None and stopping._capacity_registered is False
        assert stopping.run_once() == {'fixture': True}
        close_composed_stop_runtime(stopping, cancelled)
        assert cancelled.is_set() and stopping._closed and stopping._resources == []
        assert events == [('step', {}), 'dispatcher-closed', 'resource-closed']
        with pytest.raises(sqlite3.ProgrammingError): db.execute('SELECT 1')
    finally:
        db.close()
    print('CONTROLLED_STOP_FIXTURE_NO_REGISTRATION_AND_ACTUAL_RESOURCE_CLOSURE')


@pytest.mark.parametrize('primary_present', [False, True])
def test_composed_stop_cleanup_retains_exact_failure_and_uncertain_resources(primary_present):
    from types import SimpleNamespace
    primary, cleanup = WireError('HTTPS_UNAVAILABLE'), WireError('HTTPS_UNAVAILABLE')
    primary.add_note('CONTROLLED_PRIMARY_TIMEOUT'); cleanup.add_note('CONTROLLED_CLEANUP_PENDING')
    events = []; pending = [True]; cancelled = threading.Event(); db = sqlite3.connect(':memory:')
    def failed_step(**kwargs):
        events.append(('step', kwargs)); raise cleanup
    def no_registration(*args, **kwargs):
        raise AssertionError('fixture must not register capacity or claim authority')
    dispatcher = SimpleNamespace(has_pending_work=lambda: pending[0], close=lambda: events.append('dispatcher-closed'))
    resource = SimpleNamespace(close=lambda: events.append('resource-closed') or db.close())
    stopping = composed_stop_runtime(SimpleNamespace(step=failed_step), dispatcher,
        SimpleNamespace(heartbeat=no_registration, register_capacity=no_registration), [resource])
    try:
        if primary_present:
            with pytest.raises(BaseExceptionGroup) as caught:
                try: raise primary
                finally: close_composed_stop_runtime(stopping, cancelled)
            assert caught.value.exceptions == (primary, cleanup)
        else:
            with pytest.raises(WireError) as caught: close_composed_stop_runtime(stopping, cancelled)
            assert caught.value is cleanup
        assert primary.__notes__ == ['CONTROLLED_PRIMARY_TIMEOUT']
        assert cleanup.__notes__ == ['CONTROLLED_CLEANUP_PENDING']
        assert cancelled.is_set() and events == [('step', {})]
        assert not stopping._closed and stopping._resources == [resource]
        assert db.execute('SELECT 1').fetchone() == (1,)
        assert stopping.close()['status'] == 'STOP_PENDING'
        assert stopping._coordinator is None and stopping._capacity_registered is False
    finally:
        # Only this controlled dispatcher proves its work is actually gone.
        pending[0] = False
        assert stopping.close()['status'] == 'CLOSED'
        db.close()
    assert events == [('step', {}), 'dispatcher-closed', 'resource-closed']
    print('CONTROLLED_STOP_PRIMARY_AND_CLEANUP_UNCERTAINTY_RETAINED')


def run_composed_lost_ack_once(stopping):
    try: return stopping.run_once()
    except WireError as error:
        if error.code != 'FIXTURE_LOST_ACK': raise
        assert stopping.close()['status'] == 'STOP_PENDING'


@pytest.mark.parametrize('outcome', ['RETURNED', 'HTTPS_UNAVAILABLE', 'FIXTURE_LOST_ACK', 'CLOSE_WRONG_STATUS'])
def test_composed_lost_ack_once_preserves_original_call_return_and_failure(outcome):
    from types import SimpleNamespace
    response = {'fixture': 'original response'}
    error = WireError('HTTPS_UNAVAILABLE' if outcome == 'HTTPS_UNAVAILABLE' else 'FIXTURE_LOST_ACK')
    error.add_note('retained original note')
    calls = []
    def run_once():
        calls.append('run_once')
        if outcome != 'RETURNED': raise error
        return response
    def close():
        calls.append('close')
        return {'status': 'CLOSED' if outcome == 'CLOSE_WRONG_STATUS' else 'STOP_PENDING'}
    stopping = SimpleNamespace(run_once=run_once, close=close)
    if outcome == 'RETURNED':
        assert run_composed_lost_ack_once(stopping) is response
    elif outcome == 'HTTPS_UNAVAILABLE':
        with pytest.raises(WireError) as caught: run_composed_lost_ack_once(stopping)
        assert caught.value is error
    elif outcome == 'CLOSE_WRONG_STATUS':
        with pytest.raises(AssertionError): run_composed_lost_ack_once(stopping)
    else:
        assert run_composed_lost_ack_once(stopping) is None
    assert error.__notes__ == ['retained original note']
    assert calls == (['run_once'] if outcome in {'RETURNED', 'HTTPS_UNAVAILABLE'} else ['run_once', 'close'])


def test_actual_tls_blocked_native_keeps_heartbeat_status_cancel_and_lost_ack_durable(project_node, composed_service, monkeypatch):
    entered, cancelled = threading.Event(), threading.Event()
    calls = []
    class HarmlessBlockedAdapter:
        """Only test injection. No SDK, child process, or host qualification."""
        def __init__(self):
            self.delegate = SyntheticNativeAdapter(project_node['root'], callbacks={
                'start': lambda *_: calls.append('start') or {'process': current_identity()}})
        def reserve(self, *args, **kwargs): return self.delegate.reserve(*args, **kwargs)
        def start_reserved(self, *args, **kwargs): return self.delegate.start_reserved(*args, **kwargs)
        def effect(self, local_job_id, phase, request, fence):
            assert type(fence['authorization']) is NativeAuthorization
            assert fence['authorization'].binding['phase'] == phase
            if phase == 'result':
                calls.append('result'); entered.set()
                assert cancelled.wait(timeout=5)
                return {'schema': 'fleet.native.effect/1', 'phase': phase, 'evidence': 'SYNTHETIC_NATIVE_ONLY',
                    'payload': {'state': 'CANCELLED'}, 'local_job_id': local_job_id, 'target': request['placement']['target']}
            assert phase == 'cancel'
            calls.append('cancel'); cancelled.set()
            return {'schema': 'fleet.native.effect/1', 'phase': phase, 'evidence': 'SYNTHETIC_NATIVE_ONLY',
                'payload': {'status': 'SYNTHETIC_STOPPED'}, 'local_job_id': local_job_id, 'target': request['placement']['target']}
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service, adapter=HarmlessBlockedAdapter())
    stopping = composed_stop_runtime(agent, dispatcher, client, [transport, domains, jobs, dispatcher.principals])
    try:
        node, selected = discover(facade, client, agent)
        frozen = freeze(project_node, target=selected)
        source = project_node['source'].read_bytes()
        request = native_request(frozen, logical_fixture(), [{'path': 'Experts/DemoEA.mq5',
            'sha256': hashlib.sha256(source).hexdigest(), 'bytes': len(source)}])
        queued = facade.launch_job('native-blocked', request); global_id = queued['global_job_id']
        pump(agent, entered.is_set)
        assert calls == ['start', 'result']
        began = time.monotonic()
        for _ in range(3): agent.step()
        assert time.monotonic() - began < 1.5 and not cancelled.is_set()
        status = facade.get_job(global_id)
        assert status['state'] == 'RESULT_PENDING'
        assert status['result']['result']['evidence'] == 'SYNTHETIC_NATIVE_ONLY'
        assert stopping.request_stop()['status'] == 'STOP_PENDING'
        # Observe the real monotonic deadline; a 2 ms sleep can return before
        # the Windows monotonic clock advances to the next timer tick.
        deadline = time.monotonic() + .5
        while not stopping.stop_status()['deadline_elapsed'] and time.monotonic() < deadline:
            time.sleep(.005)
        assert stopping.stop_status()['deadline_elapsed']
        assert stopping.stop_status()['status'] == 'STOP_PENDING' and not cancelled.is_set()
        withheld = facade.inventory(node, 'inventory-withheld-during-stop')
        process = jobs.get(global_id)['result']['process_identity']
        cancel = facade.domain('/fleet/v1/jobs/cancel', node, 'cancel-blocked',
            {'global_job_id': global_id, 'process_identity': process})
        original = client.http.post; lost = []
        def lost_after_commit(path, value, headers=None, **kwargs):
            response = original(path, value, headers, **kwargs)
            if path == '/fleet/v1/results' and value.get('schema') == 'fleet.native-result-envelope/1' and value['payload']['state'] == 'CANCELLED' and not lost:
                lost.append(True)
                raise WireError('FIXTURE_LOST_ACK')
            return response
        monkeypatch.setattr(client.http, 'post', lost_after_commit)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            run_composed_lost_ack_once(stopping)
            if facade.get_job(global_id)['state'] == 'CANCELLED' and facade.command_status(cancel['command_id'])['state'] == 'COMPLETED': break
            time.sleep(.005)
        else: pytest.fail('cancel/result did not complete')
        assert calls == ['start', 'result', 'cancel'] and lost == [True]
        stopping.run_once()
        assert calls == ['start', 'result', 'cancel']
        assert facade.command_status(withheld['command_id'])['state'] == 'QUEUED'
        assert stopping.stop_status()['status'] == 'DRAINED'
        assert transport._db.execute("SELECT count(*) FROM requests WHERE state='PENDING'").fetchone()[0] == 1
    finally:
        close_composed_stop_runtime(stopping, cancelled)


def test_actual_tls_client_possession_to_async_guarded_source_two_commits_and_phase_ack(project_node, composed_service):
    from vibemql5.fleet.principals import PATHS
    import base64
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service)
    try:
        node, selected = discover(facade, client, agent)
        private = Ed25519PrivateKey.generate()
        issued = facade.principal('issue', {'operation_id': 'issue-composed',
            'client_public_key': private.public_key().public_bytes_raw().hex(), 'installation_id': 'fixture-client',
            'session_id': 'fixture-client-session', 'expires_ms': int(time.time() * 1000) + 600000, 'scopes': sorted(PATHS)})
        credential = issued['credential']; principal = credential['body']['principal_id']
        facade.principal('assign', {'operation_id': 'assign-composed', 'principal_id': principal,
            'project_id': 'P', 'target': selected, 'writer_epoch': 1})
        trusted = FleetClientFacade(http=facade.owner.http, principal_key=private, principal_credential=credential)
        assert trusted.owner is None and trusted.server_info()['authority_modes'] == ['PRINCIPAL']
        denied_calls = [lambda: trusted.inventory(), lambda: trusted.read('get_account_snapshot', selected, 'forbidden'),
            lambda: trusted.read_status('unknown'), lambda: trusted.snapshot([selected]), lambda: trusted.command_status('unknown'),
            lambda: trusted.launch_job('forbidden', {}), lambda: trusted.get_job('unknown'),
            lambda: trusted.admin('grant', {}), lambda: trusted.principal('issue', {}),
            lambda: trusted.principal('revoke', {}), lambda: trusted.domain('/fleet/v1/projects/get', node, 'forbidden', {'project_id': 'P'})]
        for denied_call in denied_calls:
            with pytest.raises(WireError, match='OWNER_CREDENTIAL_REQUIRED'): denied_call()
        session = project_node['session']
        frozen = project_node['projects'].freeze('P', 'writer-frozen', writer_id=principal, target=selected,
            expected_placement_revision=1, expected_session_revision=session['revision_id'],
            expected_session_sha256=session['revision_sha256'], operation_id='writer-freeze')
        data = b'void OnTick(){ /* guarded source fixture */ }\n'
        queued = trusted.domain('/fleet/v1/sources/write', node, 'write-composed',
            {'project_id': 'P', 'frozen_id': frozen['frozen_id'], 'source_base64': base64.b64encode(data).decode()})
        pump(agent, lambda: facade.command_status(queued['command_id'])['state'] == 'COMPLETED')
        result = facade.command_status(queued['command_id'])['result']
        assert project_node['source'].read_bytes() == data
        assert result['session']['revision_id'] == 'REV-000002' and result['placement_revision'] == 2
        assert len(result['writer_acks']) == 2
        assert {ack['phase'] for ack in result['writer_acks']} == {'source_commit', 'session_commit'}
        assert not dispatcher._domain_records and not dispatcher._acked
        replay = trusted.domain('/fleet/v1/sources/write', node, 'write-composed',
            {'project_id': 'P', 'frozen_id': frozen['frozen_id'], 'source_base64': base64.b64encode(data).decode()})
        assert replay['command_id'] == queued['command_id']
        agent.step()
        assert project_node['projects'].sessions.get('P')['revision_id'] == 'REV-000002'
        assert transport._db.execute("SELECT count(*) FROM requests WHERE state='PENDING'").fetchone()[0] == 0
    finally:
        dispatcher.close(); dispatcher.principals.close(); jobs.close(); domains.close(); transport.close()


def test_actual_node_startup_replacement_session_preserves_inactive_writer_and_recovers_only_history(project_node, composed_service, tls_files):
    from dataclasses import asdict
    from cryptography.hazmat.primitives import serialization
    from vibemql5.adapters.fleet_cli import NodeRuntime
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service)
    node, selected = discover(facade, client, agent)
    frozen = freeze(project_node, target=selected)
    raw = project_node['source'].read_bytes()
    request = native_request(frozen, logical_fixture(), [{'path': 'Experts/DemoEA.mq5',
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}])
    global_id = facade.launch_job('historical-default-denial', request)['global_job_id']
    pump(agent, lambda: facade.get_job(global_id)['state'] == 'FAILED')
    original = facade.get_job(global_id)
    assert original['result']['result']['reason_code'] == 'NATIVE_QUALIFICATION_UNAVAILABLE'
    writer_path = project_node['root'] / 'state' / 'fleet' / 'writers.json'
    writer_bytes = writer_path.read_bytes()
    while dispatcher.has_pending_work(): agent.step()
    dispatcher.close(); dispatcher.principals.close(); jobs.close(); domains.close(); transport.close()
    key = client.key
    current = facade.inventory()['revision']
    grant = facade.admin('grant', {'device_id': client.device_id, 'public_key': key.public_key().public_bytes_raw().hex(),
        'operation_id': 'replacement-grant', 'expected_revision': current, 'expected_route_generation': 1})
    replacement = NodeClient(client.http, key, client.device_id, 1)
    replacement.pair(grant_id=grant['receipt']['grant_id'], secret=grant['secret'], operation_id='replacement-pair', expected_revision=current + 1)
    assert replacement.route_generation == 2
    root = project_node['root']
    secrets_dir = root / 'secrets'
    private = protected_file(secrets_dir / 'replacement-node.pem', key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ca = protected_file(secrets_dir / 'replacement-ca.pem', tls_files[0].read_bytes())
    config = {'schema': 'fleet.node-config/1', 'root': str(root), 'origin': client.http.origin, 'ca_file': str(ca),
        'fleet_policy': asdict(fleet_policy()), 'node_key_file': str(private), 'route_generation': 2,
        'session_id': 'replacement-readonly', 'jobs_path': str(root / 'node-jobs.sqlite'),
        'journal_policy': {'max_records': 20, 'max_payload_bytes': 262144, 'wait_ms': 1000},
        'domain_path': str(root / 'node-domain.sqlite'), 'domain_policy': asdict(domain_policy()),
        'transport_path': str(root / 'node-transport.sqlite'),
        'transport_policy': {'max_records': 1000, 'max_payload_bytes': 262144, 'wait_ms': 1000},
        'gateway_public_key': composed_service[2].public_key().public_bytes_raw().hex(),
        'writer_policy': None, 'worktree_policy': None, 'worktree_config': None, 'drain_timeout_ms': 1000,
        'artifact_policy': {'installation_id': 'installation-fixture', 'max_artifact_bytes': 1024, 'max_chunk_bytes': 128},
        'max_inventory_rows': 20, 'sdk_qualifications': [], 'capacity_trust': None}
    malformed = {**config, 'writer_policy': {}}
    with pytest.raises(TypeError): NodeRuntime(malformed)
    # Constructor failure closes the already-opened transport/job/domain owners.
    reopened = NodeRuntime(config)
    try:
        assert reopened.dispatcher.principals is None and writer_path.read_bytes() == writer_bytes
        admitted = facade.recover_job('recover-historical', global_id,
            {'device_id': client.device_id, 'route_generation': 2}, 'replacement-readonly')
        assert admitted['state'] == 'ISSUED'
        reopened.run_once()
        historical = facade.recover_job('recover-historical', global_id,
            {'device_id': client.device_id, 'route_generation': 2}, 'replacement-readonly')
        assert historical['state'] == 'COMPLETED'
        assert historical['result']['classification'] == 'HISTORICAL_QUARANTINED'
        assert facade.get_job(global_id) == original
        assert reopened.dispatcher.native.get(global_id)['target']['route_generation'] == 1
        assert writer_path.read_bytes() == writer_bytes
        new_inventory = facade.inventory({'device_id': client.device_id, 'route_generation': 2}, 'readonly-inventory')
        reopened.run_once()
        result = facade.command_status(new_inventory['command_id'])
        assert result['state'] == 'COMPLETED' and result['result']['rows'][0]['target']['route_generation'] == 2
    finally:
        assert reopened.close()['status'] == 'CLOSED'


@pytest.mark.parametrize('fault_case', ['none', 'bad_pair', 'lost_ack', 'after_pair'])
def test_actual_cli_initial_pair_and_node_once_never_prints_pair_secret(project_node, composed_service, tls_files, capsys, monkeypatch, fault_case):
    from dataclasses import asdict
    from cryptography.hazmat.primitives import serialization
    from vibemql5.adapters.fleet_cli import main, NodeRuntime
    http, owner, signing_key = composed_service
    root, device = project_node['root'], project_node['registry']['device_id']
    key = Ed25519PrivateKey.generate()
    private = protected_file(root / 'secrets' / 'bootstrap-node.pem', key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ca = protected_file(root / 'secrets' / 'bootstrap-ca.pem', tls_files[0].read_bytes())
    grant = owner.admin('grant', {'device_id': device, 'public_key': key.public_key().public_bytes_raw().hex(),
        'operation_id': 'cli-bootstrap-grant', 'expected_revision': 1, 'expected_route_generation': None})
    pair = {'schema': 'fleet.pair/1', 'grant_id': grant['receipt']['grant_id'], 'secret': grant['secret'],
        'operation_id': 'cli-bootstrap-pair', 'expected_revision': 2}
    pair_path = protected_file(root / 'secrets' / 'pair.json', json.dumps(pair).encode())
    config = {'schema': 'fleet.node-config/1', 'root': str(root), 'origin': http.origin, 'ca_file': str(ca),
        'fleet_policy': asdict(fleet_policy()), 'node_key_file': str(private), 'route_generation': 1,
        'session_id': 'cli-node-session', 'jobs_path': str(root / 'bootstrap-jobs.sqlite'),
        'journal_policy': {'max_records': 20, 'max_payload_bytes': 262144, 'wait_ms': 1000},
        'domain_path': str(root / 'bootstrap-domain.sqlite'), 'domain_policy': asdict(domain_policy()),
        'transport_path': str(root / 'bootstrap-transport.sqlite'),
        'transport_policy': {'max_records': 1000, 'max_payload_bytes': 262144, 'wait_ms': 1000},
        'gateway_public_key': signing_key.public_key().public_bytes_raw().hex(), 'writer_policy': None,
        'worktree_policy': None, 'worktree_config': None, 'drain_timeout_ms': 1000,
        'artifact_policy': {'installation_id': 'installation-fixture', 'max_artifact_bytes': 1024, 'max_chunk_bytes': 128},
        'max_inventory_rows': 20, 'sdk_qualifications': [], 'capacity_trust': None}
    config_path = protected_file(root / 'secrets' / 'bootstrap-config.json', json.dumps(config).encode())
    arguments = ['--config', str(config_path), 'node', '--initialize', '--pair-file', str(pair_path), '--once']
    if fault_case == 'none':
        assert main(arguments) == 0
    else:
        with monkeypatch.context() as fault:
            if fault_case == 'bad_pair':
                bad = protected_file(root / 'secrets' / 'bad-pair.json', json.dumps({**pair, 'secret': 'incorrect-protected-secret'}).encode())
                selected = [str(bad) if item == str(pair_path) else item for item in arguments]
            else:
                selected = arguments
            if fault_case == 'lost_ack':
                original = HttpsClient.post; lost = []
                def missing_ack(self, path, value, headers=None, **kwargs):
                    result = original(self, path, value, headers, **kwargs)
                    if path == '/fleet/v1/pair' and not lost:
                        lost.append(True); raise WireError('FIXTURE_LOST_PAIR_ACK')
                    return result
                fault.setattr(HttpsClient, 'post', missing_ack)
            if fault_case == 'after_pair':
                fault.setattr(DomainJournal, '__init__', lambda *args, **kwargs: (_ for _ in ()).throw(WireError('FIXTURE_AFTER_PAIR')))
            assert main(selected) == 1
        assert Path(config['transport_path']).is_file()
        if fault_case == 'after_pair':
            assert Path(config['jobs_path']).is_file() and not Path(config['domain_path']).exists()
            with pytest.raises(WireError, match='FLEET_INITIALIZATION_PARTIAL'): NodeRuntime(config, initialize=True, pairing=pair)
            assert owner.domain_request('/fleet/v1/inventory', {'schema': 'fleet.domain-query/1'})['devices'][0]['route_generation'] == 1
            return
        assert not Path(config['jobs_path']).exists() and not Path(config['domain_path']).exists()
        if fault_case == 'bad_pair':
            with pytest.raises(WireError, match='TRANSPORT_PAIR_REPLAY_INVALID'): NodeRuntime(config, initialize=True, pairing=pair)
            return
        changed = {**pair, 'operation_id': 'different-logical-pair'}
        with pytest.raises(WireError, match='TRANSPORT_PAIR_REPLAY_INVALID'): NodeRuntime(config, initialize=True, pairing=changed)
        assert main(arguments) == 0
    output = capsys.readouterr().out
    assert pair['secret'] not in output and 'PRIVATE KEY' not in output
    node = NodeRuntime(config)
    try:
        assert node.client.route_generation == 1
        pending = node.client.transport_journal._db.execute("SELECT count(*) FROM requests WHERE state='PENDING'").fetchone()[0]
        assert pending == (1 if fault_case == 'lost_ack' else 0)
        node.run_once()
        with pytest.raises(WireError, match='FLEET_PAIRING_INITIALIZATION_REQUIRED'): NodeRuntime(config, pairing=pair)
    finally:
        assert node.close()['status'] == 'CLOSED'


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
def test_actual_tls_long_fixture_step_completes_then_receives_fresh_next_phase_grant(project_node, composed_service, monkeypatch):
    run_long_fixture(project_node, composed_service, monkeypatch)


class FixtureAuthorizationDiagnostics:
    """Observe one fixture verifier; never call or replace an authority clock globally."""
    def __init__(self):
        self.rows, self._restores, self._local = [], [], threading.local()
        self._active, self._lock = True, threading.Lock()

    @staticmethod
    def times(row, body):
        if type(body) is dict:
            for field in ('issued_ms', 'expires_ms'):
                value = body.get(field)
                if type(value) is int and 0 <= value < 2 ** 63: row[field] = value

    def instrument(self, verifier):
        clock, verify = verifier.clock, verifier.verify
        prior = verifier.__dict__.get('verify')
        def observed_clock():
            value = clock()
            row = getattr(self._local, 'row', None)
            if self._active and row is not None and type(value) is int and 0 <= value < 2 ** 63:
                row['current_ms'] = value
            return value
        def observed_verify(grant, **expected):
            row = getattr(self._local, 'row', None)
            try:
                if self._active and row is not None and type(grant) is dict: self.times(row, grant.get('body'))
            except Exception: pass
            return verify(grant, **expected)
        verifier.clock, verifier.verify = observed_clock, observed_verify
        self._restores.append((verifier, clock, prior))

    def restore(self):
        self._active = False
        for verifier, clock, prior in self._restores:
            verifier.clock = clock
            if prior is None: del verifier.verify
            else: verifier.verify = prior
        self._restores.clear()

    def call(self, stage, phase, event, callback, *args, proof=None):
        row = {'stage': stage if type(stage) is str and stage in ('BEGIN', 'REQUIRE') else 'OTHER',
               'phase': phase if type(phase) is str and phase in ('deploy', 'capture') else 'OTHER',
               'event': event if type(event) is str and event in ('snapshot_prepare:0001', 'compile_run_prepare:0001',
                                           'compile_log_capture:0001') else 'OTHER'}
        try:
            if type(proof) is NativeAuthorization: self.times(row, proof._body)
        except Exception: pass
        prior, began = getattr(self._local, 'row', None), time.monotonic()
        self._local.row = row
        with self._lock:
            if len(self.rows) < 32: self.rows.append(row)
        try:
            result = callback(*args)
            try:
                if type(result) is NativeAuthorization: self.times(row, result._body)
            except Exception: pass
            row['outcome'] = 'RETURNED'
            return result
        except BaseException as error:
            row['outcome'] = 'ERROR'
            row['elapsed_ms'] = max(0, int((time.monotonic() - began) * 1000))
            try:
                args = error.args
                if type(args) is tuple and len(args) == 1 and type(args[0]) is str and args[0] == 'NATIVE_AUTHORIZATION_EXPIRED':
                    error.add_note('LONG_AUTHORIZATION_FIXTURE ' + json.dumps(self.rows, sort_keys=True))
            except Exception: pass
            raise
        finally:
            row['elapsed_ms'] = max(0, int((time.monotonic() - began) * 1000))
            self._local.row = prior


@pytest.mark.parametrize('stage', ['BEGIN', 'REQUIRE'])
def test_authorization_diagnostic_keeps_real_expiry_and_exact_clock_calls(stage):
    from test_tip060_authorization import grant
    from vibemql5.fleet.job_journal import JournalError
    signed, binding, public = grant()
    calls, now = [], [1001 if stage == 'REQUIRE' else 2000]
    def clock():
        calls.append(now[0]); return now[0]
    verifier = NativeAuthorizationVerifier(public, binding['audience'], clock_ms=clock)
    diagnostics = FixtureAuthorizationDiagnostics(); diagnostics.instrument(verifier)
    proof = verifier.verify(signed, **binding) if stage == 'REQUIRE' else None
    now[0] = 2000
    callback = (lambda: proof.require(**binding)) if proof is not None else (lambda: verifier.verify(signed, **binding))
    try:
        with pytest.raises(JournalError, match='NATIVE_AUTHORIZATION_EXPIRED') as observed:
            diagnostics.call(stage, binding['phase'], 'phase_admission', callback, proof=proof)
        assert calls == ([1001, 2000] if stage == 'REQUIRE' else [2000])
        assert diagnostics.rows[0]['issued_ms'] == 1000 and diagnostics.rows[0]['expires_ms'] == 2000
        assert diagnostics.rows[0]['current_ms'] == 2000 and diagnostics.rows[0]['outcome'] == 'ERROR'
        note = observed.value.__notes__[0]
        assert 'LONG_AUTHORIZATION_FIXTURE' in note
        assert binding['global_job_id'] not in note and signed['signature'] not in note
    finally: diagnostics.restore()
    assert verifier.clock is clock and 'verify' not in verifier.__dict__
    if proof is not None:
        before = copy.deepcopy(diagnostics.rows)
        now[0] = 1001
        assert proof.require(**binding)['issued_ms'] == 1000
        assert calls == [1001, 2000, 1001] and diagnostics.rows == before


@pytest.mark.parametrize('invalid', ['SECRET_PATH_TOKEN', [], {}, True, -1, 2 ** 63])
def test_authorization_diagnostic_omits_malformed_fields_and_caps_rows(invalid):
    calls, sentinel = [], object()
    class Verifier:
        def __init__(self): self.clock = lambda: invalid
        def verify(self, grant, **expected):
            calls.append((grant, expected)); self.clock(); return sentinel
    verifier = Verifier(); clock = verifier.clock
    diagnostics = FixtureAuthorizationDiagnostics(); diagnostics.instrument(verifier)
    signed = {'body': {'issued_ms': invalid, 'expires_ms': invalid,
                      'token': 'SECRET_PATH_TOKEN', 'authorization_id': 'SECRET_PATH_TOKEN'},
              'signature': 'SECRET_PATH_TOKEN'}
    try:
        for _ in range(40):
            assert diagnostics.call(invalid, invalid, invalid, lambda: verifier.verify(signed, secret='SECRET_PATH_TOKEN')) is sentinel
        assert len(calls) == 40 and all(value is signed for value, _ in calls)
        assert len(diagnostics.rows) == 32
        assert all(row['stage'] == row['phase'] == row['event'] == 'OTHER' for row in diagnostics.rows)
        assert all(set(row) == {'stage', 'phase', 'event', 'outcome', 'elapsed_ms'} for row in diagnostics.rows)
        assert 'SECRET_PATH_TOKEN' not in json.dumps(diagnostics.rows)
    finally: diagnostics.restore()
    assert verifier.clock is clock and 'verify' not in verifier.__dict__


def test_authorization_diagnostic_preserves_error_with_malformed_args_and_broken_annotation(monkeypatch):
    from test_tip060_authorization import grant
    signed, binding, public = grant()
    fault = RuntimeError(['SECRET_PATH_TOKEN']); fault.add_note('original note')
    diagnostics = FixtureAuthorizationDiagnostics()
    def broken_times(*args): raise RuntimeError('CONTROLLED_DIAGNOSTIC_FAILURE')
    monkeypatch.setattr(diagnostics, 'times', broken_times)
    verifier = NativeAuthorizationVerifier(public, binding['audience'], clock_ms=lambda: 1001)
    diagnostics.instrument(verifier)
    try:
        proof = diagnostics.call('BEGIN', 'deploy', 'snapshot_prepare:0001', lambda: verifier.verify(signed, **binding))
        with pytest.raises(RuntimeError) as observed:
            diagnostics.call('REQUIRE', 'deploy', 'snapshot_prepare:0001', lambda: (_ for _ in ()).throw(fault), proof=proof)
        assert observed.value is fault and fault.__notes__ == ['original note']
        assert 'SECRET_PATH_TOKEN' not in json.dumps(diagnostics.rows)
    finally: diagnostics.restore()


def test_authorization_diagnostic_keeps_concurrent_fixture_clocks_separate():
    diagnostics, barrier, clocks = FixtureAuthorizationDiagnostics(), threading.Barrier(2), []
    class Verifier:
        def __init__(self, value): self.clock = lambda: value
        def verify(self, grant, **expected):
            barrier.wait(3); clocks.append(self.clock()); return grant
    verifiers = [Verifier(1001), Verifier(2001)]
    for verifier in verifiers: diagnostics.instrument(verifier)
    failures = []
    def observe(index):
        try:
            signed = {'body': {'issued_ms': index * 1000, 'expires_ms': (index + 2) * 1000}}
            assert diagnostics.call('BEGIN', ('deploy', 'capture')[index], 'snapshot_prepare:0001',
                lambda: verifiers[index].verify(signed)) is signed
        except BaseException as error: failures.append(error)
    threads = [threading.Thread(target=observe, args=(index,)) for index in range(2)]
    try:
        for thread in threads: thread.start()
        for thread in threads: thread.join(3)
        assert not failures and all(not thread.is_alive() for thread in threads)
        assert sorted(clocks) == [1001, 2001]
        rows = {row['phase']: row for row in diagnostics.rows}
        assert rows['deploy']['issued_ms'] == 0 and rows['deploy']['current_ms'] == 1001
        assert rows['capture']['issued_ms'] == 1000 and rows['capture']['current_ms'] == 2001
    finally: diagnostics.restore()


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
def test_long_callback_signed_expiry_keeps_exact_finite_observation(project_node, composed_service, monkeypatch):
    from vibemql5.fleet.transport import NodeRpcProxy
    from vibemql5.fleet.job_journal import JournalError
    request, outcome = NodeRpcProxy._request, NodeJobJournal._outcome
    holds, outcomes = [], []
    def held_response(self, kind, payload):
        result = request(self, kind, payload)
        if kind == 'START_AUTHORIZE' and payload['command'].get('authorization_event') == 'snapshot_prepare:0001':
            holds.append(True)
            # Negative scheduling control: the original response is already
            # signed, and its unchanged 1000-ms TTL must expire before verify.
            time.sleep(1.05)
        return result
    def observed_outcome(self, record, state, result):
        row = outcome(self, record, state, result)
        outcomes.append((row['state'], (row['result'] or {}).get('reason_code')))
        return row
    monkeypatch.setattr(NodeRpcProxy, '_request', held_response)
    monkeypatch.setattr(NodeJobJournal, '_outcome', observed_outcome)
    with pytest.raises(JournalError, match='NATIVE_AUTHORIZATION_EXPIRED') as observed:
        run_long_fixture(project_node, composed_service, monkeypatch)
    notes = [note for note in observed.value.__notes__ if note.startswith('LONG_AUTHORIZATION_FIXTURE ')]
    rows = json.loads(notes[0].removeprefix('LONG_AUTHORIZATION_FIXTURE '))
    assert holds == [True] and outcomes == [('UNKNOWN', 'EXECUTION_OUTCOME_UNKNOWN')]
    assert len(rows) == 1 and rows[0]['stage'] == 'BEGIN' and rows[0]['event'] == 'snapshot_prepare:0001'
    assert rows[0]['expires_ms'] - rows[0]['issued_ms'] == 1000
    assert rows[0]['current_ms'] >= rows[0]['expires_ms'] and rows[0]['outcome'] == 'ERROR'


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
def test_long_fixture_restore_failure_cannot_mask_original_callback(project_node, composed_service, monkeypatch):
    fault, restoration = RuntimeError('CALLBACK'), RuntimeError('RESTORATION')
    fault.add_note('callback note'); restoration.add_note('restoration note')
    restore = FixtureAuthorizationDiagnostics.restore
    def broken_restore(self):
        restore(self); assert not self._restores; raise restoration
    monkeypatch.setattr(NodeJobJournal, 'begin_effect', lambda *args, **kwargs: (_ for _ in ()).throw(fault))
    monkeypatch.setattr(FixtureAuthorizationDiagnostics, 'restore', broken_restore)
    with pytest.raises(BaseExceptionGroup) as observed:
        run_long_fixture(project_node, composed_service, monkeypatch)
    assert observed.value.exceptions == (fault, restoration)
    assert fault.__notes__ == ['callback note'] and restoration.__notes__ == ['restoration note']


def run_long_fixture(project_node, composed_service, monkeypatch, *, seconds=10, return_barrier=None):
    grants, events = [], []
    authorization_diagnostics = FixtureAuthorizationDiagnostics()
    worker_failures = []
    def preserve_worker_call(callback, *args):
        try: return callback(*args)
        except BaseException as error:
            if not any(error is previous for previous in worker_failures):
                worker_failures.append(error)
            raise
    def raise_worker_failure():
        if worker_failures: raise worker_failures[0]
    def start_fixture(request, fence):
        def begin(phase, event):
            return authorization_diagnostics.call('BEGIN', phase, event, fence['begin_effect'], phase, event)
        def require(proof, phase, event):
            return authorization_diagnostics.call('REQUIRE', phase, event,
                lambda: proof.require(**proof.binding), proof=proof)
        snapshot = begin('deploy', 'snapshot_prepare:0001')
        require(snapshot, 'deploy', 'snapshot_prepare:0001')
        fence['complete_effect']('deploy', 'snapshot_prepare:0001', snapshot,
            outcome='NOT_ATTEMPTED', evidence={'source': 'SYNTHETIC_NO_NATIVE_ATTEMPT'})
        compile_step = begin('deploy', 'compile_run_prepare:0001')
        require(compile_step, 'deploy', 'compile_run_prepare:0001')
        grants.append(compile_step); events.append('long-step-entered')
        # This harmless producer return lasts longer than its entry proof TTL.
        time.sleep(1.2)
        fence['complete_effect']('deploy', 'compile_run_prepare:0001', compile_step,
            outcome='NOT_ATTEMPTED', evidence={'source': 'SYNTHETIC_NO_NATIVE_ATTEMPT'})
        from vibemql5.fleet.job_journal import JournalError
        with pytest.raises(JournalError, match='NATIVE_AUTHORIZATION_EXPIRED'):
            require(compile_step, 'deploy', 'compile_run_prepare:0001')
        capture = begin('capture', 'compile_log_capture:0001')
        require(capture, 'capture', 'compile_log_capture:0001'); grants.append(capture)
        fence['complete_effect']('capture', 'compile_log_capture:0001', capture,
            outcome='NOT_ATTEMPTED', evidence={'source': 'SYNTHETIC_NO_NATIVE_ATTEMPT'})
        events.append('fresh-next-phase')
        return {'process': current_identity(), 'execution': {'status': 'COMPLETED'}}
    adapter = SyntheticNativeAdapter(project_node['root'], callbacks={
        'start': lambda *args: preserve_worker_call(start_fixture, *args)})
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service,
        adapter=adapter, authorization_diagnostics=authorization_diagnostics)
    release_return = threading.Event() if return_barrier is None else return_barrier
    observed_return_race = []
    native_work = dispatcher._native_work
    def delayed_return(*args):
        result = native_work(*args)
        assert release_return.wait(timeout=3), 'LONG_FIXTURE_WORKER_RETURN_TIMEOUT'
        return result
    monkeypatch.setattr(dispatcher, '_native_work', lambda *args: preserve_worker_call(delayed_return, *args))
    def succeeded_and_drained(global_job_id):
        raise_worker_failure()
        succeeded = facade.get_job(global_job_id)['state'] == 'SUCCEEDED'
        if succeeded and not release_return.is_set():
            # Force the Windows-observed ordering on every platform: gateway
            # sees the terminal ACK before the worker future has returned.
            assert dispatcher._futures and dispatcher.has_pending_work()
            observed_return_race.append(True); release_return.set()
        drained = not dispatcher.has_pending_work()
        raise_worker_failure()
        return succeeded and drained
    failures = []
    try:
        node, selected = discover(facade, client, agent)
        frozen = freeze(project_node, target=selected); raw = project_node['source'].read_bytes()
        request = native_request(frozen, logical_fixture(), [{'path': 'Experts/DemoEA.mq5', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}])
        row = facade.launch_job('long-step-fixture', request)
        # A terminal journal ACK can arrive while the worker is returning.
        # Its future must finish and pass through the normal owner drain too.
        # This aggregate observation spans all phases; each authorization/RPC,
        # producer, worker-return and cleanup bound remains independent.
        pump(agent, lambda: succeeded_and_drained(row['global_job_id']), seconds=seconds)
        raise_worker_failure()
        assert observed_return_race == [True]
        assert events == ['long-step-entered', 'fresh-next-phase']
        assert grants[1].grant_sha256 != grants[0].grant_sha256
        assert grants[1].binding['sequence'] > grants[0].binding['sequence']
        assert facade.get_job(row['global_job_id'])['result']['result']['evidence'] == 'SYNTHETIC_NATIVE_ONLY'
        assert not dispatcher._native_records and not dispatcher._acked
    except BaseException as primary:
        failures.append(primary)
    finally:
        try:
            release_return.set()
            close_dispatcher_fixture(agent, dispatcher, pump, seconds=3)
            dispatcher.principals.close(); jobs.close(); domains.close(); transport.close()
        except BaseException as cleanup:
            failures.append(cleanup)
        finally:
            try: authorization_diagnostics.restore()
            except BaseException as restoration: failures.append(restoration)
    # Cleanup may release the wrapper and expose another original failure.
    # Collect only after the normal bounded owner drain has finished.
    originals = []
    for failure in failures + worker_failures:
        if not any(failure is original for original in originals): originals.append(failure)
    if len(originals) == 1: raise originals[0]
    if originals: raise BaseExceptionGroup('long fixture observation, worker or cleanup failed', originals) from None


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
@pytest.mark.parametrize('seconds', [5, 10])
def test_long_fixture_valid_finite_schedule_requires_aggregate_observation(project_node, composed_service, monkeypatch, seconds):
    from vibemql5.fleet.job_journal import NodeJobJournal
    from vibemql5.fleet.transport import NodeRpcProxy
    begin, complete = NodeJobJournal.begin_effect, NodeJobJournal.complete_effect
    outcome, request = NodeJobJournal._outcome, NodeRpcProxy._request
    holds, outcomes, requests = [], [], []
    def held_begin(self, job, phase, event, **kwargs):
        # Delay before a fresh intent, never an in-flight grant or request.
        time.sleep(.7); holds.append(('BEGIN', event))
        return begin(self, job, phase, event, **kwargs)
    def held_complete(self, job, phase, event, proof, **kwargs):
        # Delay publication of already-observed harmless completion.
        time.sleep(.7); holds.append(('COMPLETE', event))
        return complete(self, job, phase, event, proof, **kwargs)
    def observed_outcome(self, record, state, result):
        row = outcome(self, record, state, result)
        outcomes.append((row['state'], (row['result'] or {}).get('evidence')))
        return row
    def observed_request(self, kind, payload):
        started = time.monotonic()
        result = request(self, kind, payload)
        requests.append((kind, time.monotonic() - started))
        return result
    monkeypatch.setattr(NodeJobJournal, 'begin_effect', held_begin)
    monkeypatch.setattr(NodeJobJournal, 'complete_effect', held_complete)
    monkeypatch.setattr(NodeJobJournal, '_outcome', observed_outcome)
    monkeypatch.setattr(NodeRpcProxy, '_request', observed_request)
    if seconds == 5:
        with pytest.raises(pytest.fail.Exception, match='^bounded fixture did not reach expected state$'):
            run_long_fixture(project_node, composed_service, monkeypatch, seconds=seconds)
    else:
        # Runs every original proof-expiry, fresh-phase, ACK-before-return and
        # final empty-record assertion, through the same actual TLS helper.
        run_long_fixture(project_node, composed_service, monkeypatch, seconds=seconds)
    assert len(holds) == 6
    assert len(requests) == 5
    assert all(kind == 'START_AUTHORIZE' and elapsed < composed_service[0].policy.http_timeout_ms / 1000
        for kind, elapsed in requests)
    assert outcomes == [('SUCCEEDED', 'SYNTHETIC_NATIVE_ONLY')]
    assert composed_service[0].policy.http_timeout_ms == 5000
    assert composed_service[0].policy.heartbeat_interval_ms == 5000


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_long_fixture_preserves_callback_error_identity_and_cleanup(project_node, composed_service, monkeypatch, cleanup_fails):
    from vibemql5.fleet.job_journal import NodeJobJournal
    import sys
    fault, cleanup = RuntimeError('CONTROLLED_CALLBACK_FAILURE'), RuntimeError('CONTROLLED_CLEANUP_FAILURE')
    fault.add_note('original callback note'); cleanup.add_note('original cleanup note')
    outcome, close, make_runtime = NodeJobJournal._outcome, close_dispatcher_fixture, runtime
    outcomes, resources = [], []
    def owned_runtime(*args, **kwargs):
        result = make_runtime(*args, **kwargs)
        resources.extend([result[3].principals, *result[4:]])
        return result
    def failed_begin(*args, **kwargs): raise fault
    def observed_outcome(self, record, state, result):
        row = outcome(self, record, state, result)
        outcomes.append((row['state'], (row['result'] or {}).get('reason_code')))
        return row
    def failed_cleanup(*args, **kwargs):
        close(*args, **kwargs)
        # The real owner drain has closed the idle dispatcher. Dispose its
        # journals before this control deliberately interrupts normal cleanup.
        for resource in resources: resource.close()
        raise cleanup
    monkeypatch.setattr(NodeJobJournal, 'begin_effect', failed_begin)
    monkeypatch.setattr(NodeJobJournal, '_outcome', observed_outcome)
    if cleanup_fails:
        monkeypatch.setattr(sys.modules[__name__], 'runtime', owned_runtime)
        monkeypatch.setattr(sys.modules[__name__], 'close_dispatcher_fixture', failed_cleanup)
    with pytest.raises(BaseException) as observed:
        run_long_fixture(project_node, composed_service, monkeypatch)
    if cleanup_fails:
        if not isinstance(observed.value, BaseExceptionGroup) or observed.value.exceptions != (fault, cleanup):
            raise observed.value
    else:
        if observed.value is not fault: raise observed.value
    assert fault.__notes__ == ['original callback note']
    assert cleanup.__notes__ == ['original cleanup note']
    assert outcomes == [('UNKNOWN', 'EXECUTION_OUTCOME_UNKNOWN')]


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
@pytest.mark.parametrize('failure', ['error', 'pytest_failure', 'timeout'])
def test_long_fixture_preserves_wrapper_failure_after_terminal_ack(project_node, composed_service, monkeypatch, failure):
    fault = pytest.fail.Exception('CONTROLLED_WRAPPER_FAILURE') if failure == 'pytest_failure' else RuntimeError('CONTROLLED_WRAPPER_FAILURE')
    fault.add_note('original wrapper note')
    waits = []
    class ReturnBarrier(threading.Event):
        def wait(self, timeout=None):
            waits.append(timeout)
            assert super().wait(timeout), 'CONTROLLED_ACK_NOT_OBSERVED'
            if failure == 'timeout': return False
            raise fault
    with pytest.raises(BaseException) as observed:
        run_long_fixture(project_node, composed_service, monkeypatch, return_barrier=ReturnBarrier())
    if failure == 'timeout':
        if not isinstance(observed.value, AssertionError) or 'LONG_FIXTURE_WORKER_RETURN_TIMEOUT' not in str(observed.value):
            raise observed.value
    else:
        if observed.value is not fault: raise observed.value
        assert fault.__notes__ == ['original wrapper note']
    assert waits == [3]


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_long_fixture_preserves_worker_failure_released_by_cleanup(project_node, composed_service, monkeypatch, cleanup_fails):
    import sys
    primary, late, cleanup = WireError('HTTPS_UNAVAILABLE'), pytest.fail.Exception('LATE_WRAPPER'), RuntimeError('CLEANUP')
    for error, note in ((primary, 'transport note'), (late, 'worker note'), (cleanup, 'cleanup note')):
        error.add_note(note)
    waiting, released, raised = threading.Event(), threading.Event(), threading.Event()
    read, close, make_runtime = FleetClientFacade.get_job, close_dispatcher_fixture, runtime
    resources, injected = [], []
    class ReturnBarrier:
        def is_set(self): return released.is_set()
        def set(self): released.set()
        def wait(self, timeout=None):
            assert timeout == 3
            waiting.set()
            assert released.wait(timeout)
            raised.set(); raise late
    def interrupted_read(self, *args, **kwargs):
        if waiting.is_set() and not released.is_set() and not injected:
            injected.append(True); raise primary
        return read(self, *args, **kwargs)
    def owned_runtime(*args, **kwargs):
        result = make_runtime(*args, **kwargs)
        resources.extend([result[3].principals, *result[4:]])
        return result
    def failed_cleanup(*args, **kwargs):
        close(*args, **kwargs)
        for resource in resources: resource.close()
        raise cleanup
    monkeypatch.setattr(FleetClientFacade, 'get_job', interrupted_read)
    if cleanup_fails:
        monkeypatch.setattr(sys.modules[__name__], 'runtime', owned_runtime)
        monkeypatch.setattr(sys.modules[__name__], 'close_dispatcher_fixture', failed_cleanup)
    with pytest.raises(BaseExceptionGroup) as observed:
        run_long_fixture(project_node, composed_service, monkeypatch, return_barrier=ReturnBarrier())
    expected = (primary, cleanup, late) if cleanup_fails else (primary, late)
    if observed.value.exceptions != expected: raise observed.value
    assert raised.is_set() and injected == [True]
    assert [error.__notes__ for error in expected] == [['transport note'], *([['cleanup note']] if cleanup_fails else []), ['worker note']]


@pytest.mark.parametrize('control', ['callback', 'wrapper'])
def test_long_fixture_negative_controls_preserve_unexpected_transport_error(monkeypatch, control):
    import sys
    fault = WireError('HTTPS_UNAVAILABLE'); fault.add_note('original transport diagnostic')
    def failed_run(*args, **kwargs): raise fault
    monkeypatch.setattr(sys.modules[__name__], 'run_long_fixture', failed_run)
    with pytest.raises(WireError) as observed:
        if control == 'callback':
            test_long_fixture_preserves_callback_error_identity_and_cleanup(None, None, monkeypatch, False)
        else:
            test_long_fixture_preserves_wrapper_failure_after_terminal_ack(None, None, monkeypatch, 'pytest_failure')
    assert observed.value is fault and fault.__notes__ == ['original transport diagnostic']


@pytest.mark.parametrize('composed_service', [LONG_FIXTURE_PROFILE], indirect=True)
def test_long_positive_profile_keeps_actual_nonce_replay_denied(project_node, composed_service):
    from vibemql5.fleet.wire import encode_body, sign_request
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service)
    try:
        body = {'schema': 'fleet.heartbeat/1', 'session_id': agent.session_id}
        raw = encode_body(body, client.http.policy.max_body_bytes)
        headers = sign_request(client.key, device_id=client.device_id, route_generation=client.route_generation,
            timestamp_ms=int(time.time() * 1000), nonce='1' * 48, path='/fleet/v1/heartbeat', body=raw, audience=client.http.origin)
        assert client.http.post('/fleet/v1/heartbeat', body, headers)['transport'] == 'ONLINE'
        with pytest.raises(WireError) as observed: client.http.post('/fleet/v1/heartbeat', body, headers)
        if observed.value.code != 'CONTROL_REPLAY': raise observed.value
        assert client.http.policy.http_timeout_ms == agent.policy.heartbeat_interval_ms == 5000
        assert not dispatcher.has_pending_work()
    finally:
        with preserve_fixture_failure():
            close_dispatcher_fixture(agent, dispatcher, pump, seconds=3)
            dispatcher.principals.close(); jobs.close(); domains.close(); transport.close()
