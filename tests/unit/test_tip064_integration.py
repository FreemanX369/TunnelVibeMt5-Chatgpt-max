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
from test_tip058b_transport import control_policy, fleet_policy, tls_files, positive, TOKEN
from vibemql5.adapters.fleet_client_tools import FleetClientFacade, FLEET_TOOL_NAMES
from vibemql5.adapters.fleet_mcp import create_server
from vibemql5.core.facade import ToolFacade
from vibemql5.fleet.domain import DomainJournal, DomainPolicy, GatewayDomain, NodeDomainDispatcher
from vibemql5.fleet.sdk_qualification import QualificationError, QualifiedSdkInstallation
from vibemql5.fleet.wire import WireError


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
    from fleet_writer_fixture import principal_policy
    from vibemql5.adapters.fleet_cli import gateway_factory, operator_server_context
    from vibemql5.adapters.fleet_client_tools import operator_configuration
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    origin = 'https://localhost:' + str(port)
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
        assert ready.get(timeout=5)[1] == port
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


@pytest.fixture
def composed_service(tmp_path, tls_files, request):
    ca, certificate, private = tls_files
    stopped, ready, failures = threading.Event(), Queue(), Queue()
    signing_key = Ed25519PrivateKey.generate()
    authorization_ms = getattr(request, "param", 2000)
    def factory(address):
        origin = 'https://localhost:' + str(address[1])
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
        return GatewayController(store, fleet_policy(), audience=origin,
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
            broker=ReadBroker.for_synthetic_tests(fleet_policy()), domain=domain)
    def run():
        try:
            serve_gateway(('127.0.0.1', 0), certificate=certificate, key_file=private,
                controller_factory=factory, stop_event=stopped, started=ready.put)
        except BaseException as error: failures.put(error)
    thread = threading.Thread(target=run, daemon=True); thread.start()
    address = ready.get(timeout=5)
    http = HttpsClient('https://localhost:' + str(address[1]), fleet_policy(), cafile=str(ca))
    yield http, OwnerClient(http, TOKEN), signing_key
    stopped.set(); thread.join(timeout=3)
    assert not thread.is_alive()
    if not failures.empty(): raise failures.get()


def runtime(project_node, composed_service, *, adapter=None):
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
    from fleet_writer_fixture import writer_policy
    from vibemql5.fleet.writers import NodePrincipalRuntime
    writers = NodePrincipalRuntime(root, gateway_public_key=signing_key.public_key().public_bytes_raw(), audience=http.origin,
        device_id=device, route_generation=1, session_id='session-composed', policy=writer_policy(), initialize=True)
    dispatcher = NodeDomainDispatcher(root, domains, jobs, adapter or RoutedNativeAdapter(root),
        principal_runtime=writers, authorization_verifier=verifier, max_inventory_rows=20)
    agent = OutboundNode(client, root, fleet_policy(), session_id='session-composed',
        domain_dispatcher=dispatcher, synthetic_read_adapter=positive)
    return FleetClientFacade(owner), client, agent, dispatcher, jobs, domains, transport


def pump(agent, predicate, *, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        agent.step()
        if predicate(): return
        time.sleep(.005)
    pytest.fail('bounded fixture did not reach expected state')


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
        pump(agent, lambda: facade.get_job(queued['global_job_id'])['state'] == 'FAILED')
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
        dispatcher.close(); dispatcher.principals.close(); jobs.close(); domains.close(); transport.close()


def test_actual_tls_blocked_native_keeps_heartbeat_status_cancel_and_lost_ack_durable(project_node, composed_service, monkeypatch):
    from vibemql5.adapters.fleet_cli import NodeRuntime
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
    # Use the actual stop lifecycle around the already composed harmless node.
    stopping = object.__new__(NodeRuntime)
    stopping.agent, stopping.dispatcher, stopping.client = agent, dispatcher, client
    stopping.policy, stopping.config = fleet_policy(), {'drain_timeout_ms': 1}
    stopping._resources = [transport, domains, jobs, dispatcher.principals]
    stopping._closed, stopping._stopping, stopping._drain_deadline = False, False, None
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
        time.sleep(.002)
        assert stopping.stop_status()['deadline_elapsed']
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
            try: stopping.run_once()
            except WireError as error:
                assert error.code == 'FIXTURE_LOST_ACK'
                assert stopping.close()['status'] == 'STOP_PENDING'
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
        cancelled.set()
        deadline = time.monotonic() + 2
        while dispatcher.has_pending_work() and time.monotonic() < deadline:
            try: stopping.run_once()
            except WireError as error: assert error.code == 'FIXTURE_LOST_ACK'
            time.sleep(.005)
        assert stopping.close()['status'] == 'CLOSED'
        assert stopping.close()['status'] == 'CLOSED'


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


@pytest.mark.parametrize('composed_service', [1000], indirect=True)
def test_actual_tls_long_fixture_step_completes_then_receives_fresh_next_phase_grant(project_node, composed_service):
    grants, events = [], []
    def start_fixture(request, fence):
        snapshot = fence['begin_effect']('deploy', 'snapshot_prepare:0001')
        snapshot.require(**snapshot.binding)
        fence['complete_effect']('deploy', 'snapshot_prepare:0001', snapshot,
            outcome='NOT_ATTEMPTED', evidence={'source': 'SYNTHETIC_NO_NATIVE_ATTEMPT'})
        compile_step = fence['begin_effect']('deploy', 'compile_run_prepare:0001')
        compile_step.require(**compile_step.binding)
        grants.append(compile_step); events.append('long-step-entered')
        # This harmless producer return lasts longer than its entry proof TTL.
        time.sleep(1.2)
        fence['complete_effect']('deploy', 'compile_run_prepare:0001', compile_step,
            outcome='NOT_ATTEMPTED', evidence={'source': 'SYNTHETIC_NO_NATIVE_ATTEMPT'})
        from vibemql5.fleet.job_journal import JournalError
        with pytest.raises(JournalError, match='NATIVE_AUTHORIZATION_EXPIRED'):
            compile_step.require(**compile_step.binding)
        capture = fence['begin_effect']('capture', 'compile_log_capture:0001')
        capture.require(**capture.binding); grants.append(capture)
        fence['complete_effect']('capture', 'compile_log_capture:0001', capture,
            outcome='NOT_ATTEMPTED', evidence={'source': 'SYNTHETIC_NO_NATIVE_ATTEMPT'})
        events.append('fresh-next-phase')
        return {'process': current_identity(), 'execution': {'status': 'COMPLETED'}}
    adapter = SyntheticNativeAdapter(project_node['root'], callbacks={'start': start_fixture})
    facade, client, agent, dispatcher, jobs, domains, transport = runtime(project_node, composed_service, adapter=adapter)
    try:
        node, selected = discover(facade, client, agent)
        frozen = freeze(project_node, target=selected); raw = project_node['source'].read_bytes()
        request = native_request(frozen, logical_fixture(), [{'path': 'Experts/DemoEA.mq5', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}])
        row = facade.launch_job('long-step-fixture', request)
        pump(agent, lambda: facade.get_job(row['global_job_id'])['state'] == 'SUCCEEDED', seconds=5)
        assert events == ['long-step-entered', 'fresh-next-phase']
        assert grants[1].grant_sha256 != grants[0].grant_sha256
        assert grants[1].binding['sequence'] > grants[0].binding['sequence']
        assert facade.get_job(row['global_job_id'])['result']['result']['evidence'] == 'SYNTHETIC_NATIVE_ONLY'
        assert not dispatcher._native_records and not dispatcher._acked
    finally:
        dispatcher.close(); dispatcher.principals.close(); jobs.close(); domains.close(); transport.close()
