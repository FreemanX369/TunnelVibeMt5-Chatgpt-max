"""Explicit operator gateway/node startup and finite client commands.

Client construction never opens authority databases or launches a service. All
limits and trust inputs come from the validated operator configuration.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import signal
import shutil
import ssl
import stat
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .fleet_client_tools import FleetClientFacade, configuration, operator_configuration, operator_ssl_context, private_bytes, private_text
from ..fleet.wire import WireError, fields, https_origin, integer, logical_digest, text


_GATEWAY_FIELDS = {'schema', 'origin', 'listen_host', 'listen_port', 'certificate_file', 'tls_key_file',
    'owner_token_file', 'control_path', 'control_policy', 'fleet_policy', 'domain_path', 'domain_policy',
    'jobs_path', 'journal_policy', 'authority_key_file', 'principal_path', 'principal_policy',
    'capacity_owner_public_key', 'recovery'}
_NODE_FIELDS = {'schema', 'root', 'origin', 'ca_file', 'fleet_policy', 'node_key_file', 'route_generation',
    'session_id', 'worktree_policy', 'worktree_config', 'drain_timeout_ms', 'jobs_path', 'journal_policy', 'domain_path', 'domain_policy', 'transport_path',
    'transport_policy', 'gateway_public_key', 'writer_policy', 'artifact_policy', 'max_inventory_rows',
    'sdk_qualifications', 'capacity_trust'}


def _public_key(value):
    import re
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise WireError('FLEET_CONFIG_INVALID')
    return bytes.fromhex(value)


def _journal_policy(value):
    fields(value, {'max_records', 'max_payload_bytes', 'wait_ms'})
    integer(value['max_records'], minimum=1, maximum=65536)
    integer(value['max_payload_bytes'], minimum=1, maximum=4194304)
    integer(value['wait_ms'], minimum=1, maximum=60000)
    return value


def _paths(value, names):
    selected = []
    for name in names:
        text(value[name], 32768)
        path = Path(value[name])
        if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
            raise WireError('FLEET_CONFIG_INVALID')
        selected.append(path.resolve())
    if len(set(selected)) != len(selected):
        raise WireError('FLEET_CONFIG_INVALID')


def operator_server_context(certificate_file, key_file):
    """Load TLS from checked bytes in a fresh protected, retained staging scope."""
    from ..fleet.node_keys import _check, _windows_acl, _windows_create, _windows_hold_private_directory
    certificate, key = private_bytes(certificate_file, 1048576), private_bytes(key_file, 16384)
    # The Unix temporary directory must not allow another identity to replace
    # this user's newly created staging directory. A sticky system tmp is safe.
    if os.name != 'nt':
        for ancestor in (Path(tempfile.gettempdir()), *Path(tempfile.gettempdir()).parents):
            info = ancestor.stat()
            if ancestor.is_symlink() or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
                raise WireError('FLEET_TLS_STORAGE_UNTRUSTED')
    directory_fd, directory = None, None
    try:
        directory = Path(tempfile.mkdtemp(prefix='vibemql5-tls-'))
        if os.name == 'nt':
            directory_fd = _windows_hold_private_directory(directory)
        else:
            directory.chmod(0o700)
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0))
        for name, content in (('certificate.pem', certificate), ('key.pem', key)):
            selected = directory / name
            descriptor = _windows_create(selected) if os.name == 'nt' else os.open(selected, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            try:
                if os.name == 'nt': _windows_acl(descriptor, set_restrictive=True)
                _check(descriptor)
                remaining = memoryview(content)
                while remaining:
                    remaining = remaining[os.write(descriptor, remaining):]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(directory / 'certificate.pem'), str(directory / 'key.pem'))
        return context
    except (OSError, ValueError, ssl.SSLError):
        raise WireError('FLEET_TLS_CONFIG_INVALID') from None
    finally:
        if directory_fd is not None: os.close(directory_fd)
        if directory is not None: shutil.rmtree(directory)


def gateway_factory(config, *, initialize=False):
    from ..fleet.domain import DomainJournal, DomainPolicy, GatewayDomain
    from ..fleet.gateway_control import GatewayControlStore, Policy
    from ..fleet.job_journal import GatewayJobJournal
    from ..fleet.native_authorization import GatewayNativeSigner
    from ..fleet.node_keys import load_node_key
    from ..fleet.principals import GatewayPrincipalAuthority, PrincipalPolicy
    from ..fleet.read_broker import FleetPolicy
    from ..fleet.transport import GatewayController
    fields(config, _GATEWAY_FIELDS)
    if config['schema'] != 'fleet.gateway-config/1' or type(initialize) is not bool:
        raise WireError('FLEET_CONFIG_INVALID')
    origin = https_origin(config['origin'])
    text(config['listen_host'], 255); integer(config['listen_port'], minimum=1, maximum=65535)
    if (urlsplit(origin).port or 443) != config['listen_port']:
        raise WireError('FLEET_CONFIG_INVALID')
    _paths(config, ('control_path', 'domain_path', 'jobs_path', 'principal_path'))
    control_policy = Policy(**config['control_policy'])
    fleet_policy = FleetPolicy(**config['fleet_policy'])
    domain_policy = DomainPolicy(**config['domain_policy'])
    principal_policy = PrincipalPolicy(**config['principal_policy'])
    journal_policy = _journal_policy(config['journal_policy'])
    signing_key = load_node_key(config['authority_key_file'])
    token = private_text(config['owner_token_file'], fleet_policy.max_owner_token_bytes)
    if len(token) < 32:
        raise WireError('OWNER_CONFIG_INVALID')
    private_bytes(config['tls_key_file'], 16384)
    private_bytes(config['certificate_file'], 1048576)
    if config['capacity_owner_public_key'] is not None:
        _public_key(config['capacity_owner_public_key'])
    if initialize and any(Path(config[name]).exists() for name in ('control_path', 'domain_path', 'jobs_path', 'principal_path')):
        raise WireError('FLEET_INITIALIZATION_EXISTS')
    def create(address):
        if address[1] != config['listen_port']:
            raise WireError('FLEET_CONFIG_INVALID')
        opened = []
        try:
            opener = GatewayControlStore.initialize if initialize else GatewayControlStore.open_existing
            store = opener(config['control_path'], policy=control_policy); opened.append(store)
            jobs = GatewayJobJournal(config['jobs_path'], initialize=initialize,
                capacity_owner_public_key=config['capacity_owner_public_key'], **journal_policy); opened.append(jobs)
            domains = DomainJournal(config['domain_path'], initialize=initialize, role='GATEWAY', policy=domain_policy); opened.append(domains)
            principals = GatewayPrincipalAuthority(config['principal_path'], signing_key=signing_key,
                audience=origin, policy=principal_policy, initialize=initialize); opened.append(principals)
            domains.bind_principal_authority(principals)
            recovery = None
            if config['recovery'] is not None:
                from ..fleet.restore_coordination import RestoreCoordinator, RestorePolicy
                rc = config['recovery']
                fields(rc, {'path', 'policy', 'operator_public_key', 'initialize', 'approval_file', 'checkpoint_file'})
                recovery = RestoreCoordinator(rc['path'], store, jobs, audience=origin,
                    operator_public_key=_public_key(rc['operator_public_key']), policy=RestorePolicy(**rc['policy']),
                    now_ms=int(time.time() * 1000), initialize=rc['initialize'],
                    approval=None if rc['approval_file'] is None else configuration(rc['approval_file']),
                    checkpoint_path=rc['checkpoint_file'], domain_journal=domains, principal_authority=principals)
                opened.append(recovery)
            signer = GatewayNativeSigner(signing_key, origin, max_authorization_ms=domain_policy.start_authorization_ms)
            domain = GatewayDomain(store, domains, jobs, principal_authority=principals, recovery=recovery,
                native_signer=signer, start_authorization_ms=domain_policy.start_authorization_ms,
                capacity_owner_public_key=config['capacity_owner_public_key'])
            return GatewayController(store, fleet_policy, audience=origin,
                owner_token_sha256=hashlib.sha256(token.encode()).hexdigest(), domain=domain)
        except BaseException:
            for resource in reversed(opened): resource.close()
            raise
    return create


class NodeRuntime:
    def __init__(self, config, *, initialize=False, pairing=None):
        from ..core.concurrency import ConcurrencyManager
        from ..fleet.artifact_proxy import ArtifactProxy
        from ..fleet.domain import DomainJournal, DomainPolicy, NodeDomainDispatcher
        from ..fleet.identity import IdentityRegistry
        from ..fleet.job_journal import NodeJobJournal
        from ..fleet.native import RoutedNativeAdapter
        from ..fleet.native_authorization import NativeAuthorizationVerifier
        from ..fleet.node_keys import load_node_key
        from ..fleet.node_transport_journal import NodeTransportJournal, TransportPolicy
        from ..fleet.read_broker import FleetPolicy
        from ..fleet.transport import HttpsClient, NodeClient, OutboundNode
        from ..fleet.writers import NodePrincipalRuntime, WriterPolicy
        fields(config, _NODE_FIELDS)
        if config['schema'] != 'fleet.node-config/1' or type(initialize) is not bool:
            raise WireError('FLEET_CONFIG_INVALID')
        if pairing is not None:
            if not initialize:
                raise WireError('FLEET_PAIRING_INITIALIZATION_REQUIRED')
            fields(pairing, {'schema', 'grant_id', 'secret', 'operation_id', 'expected_revision'})
            if pairing['schema'] != 'fleet.pair/1': raise WireError('FLEET_CONFIG_INVALID')
        root = Path(config['root']).resolve(strict=True)
        if not root.is_dir(): raise WireError('FLEET_CONFIG_INVALID')
        _paths(config, ('jobs_path', 'domain_path', 'transport_path'))
        record = IdentityRegistry(root).load()
        if record is None: raise WireError('IDENTITY_UNENROLLED')
        policy = FleetPolicy(**config['fleet_policy'])
        domain_policy = DomainPolicy(**config['domain_policy'])
        journal_policy = _journal_policy(config['journal_policy'])
        integer(config['route_generation'], minimum=1); text(config['session_id'], 64)
        integer(config['max_inventory_rows'], minimum=1, maximum=4096)
        integer(config['drain_timeout_ms'], minimum=1, maximum=60000)
        key = load_node_key(config['node_key_file'])
        gateway_key = _public_key(config['gateway_public_key'])
        http = HttpsClient(config['origin'], policy, ssl_context=operator_ssl_context(config['ca_file']))
        existing = {name for name in ('jobs_path', 'domain_path', 'transport_path') if Path(config[name]).exists()}
        authority_exists = any((root / 'state' / 'fleet' / name).exists() for name in ('writers.json', 'worktrees.json'))
        replay_pair = initialize and pairing is not None and existing == {'transport_path'} and not authority_exists
        if initialize and (existing or authority_exists) and not replay_pair:
            code = 'FLEET_INITIALIZATION_EXISTS' if existing == {'jobs_path', 'domain_path', 'transport_path'} else 'FLEET_INITIALIZATION_PARTIAL'
            raise WireError(code)
        self._resources = []
        self.dispatcher = None
        self._closed, self._stopping, self._drain_deadline = False, False, None
        try:
            transport_opener = NodeTransportJournal.initialize if initialize and not replay_pair else NodeTransportJournal.open_existing
            transport = transport_opener(config['transport_path'], TransportPolicy(**config['transport_policy']),
                device_id=record['device_id'], public_key=key.public_key().public_bytes_raw().hex(), audience=http.origin)
            self._resources.append(transport)
            if replay_pair:
                transport.assert_pair_replay(pairing, signed_route_generation=config['route_generation'] - 1)
            client = NodeClient(http, key, record['device_id'], config['route_generation'], transport_journal=transport)
            if pairing is not None:
                client.route_generation = config['route_generation'] - 1
                client.pair(**{name: pairing[name] for name in ('grant_id', 'secret', 'operation_id', 'expected_revision')})
                if client.route_generation != config['route_generation']:
                    raise WireError('FLEET_PAIRING_ROUTE_MISMATCH')
            jobs = NodeJobJournal(config['jobs_path'], initialize=initialize, **journal_policy); self._resources.append(jobs)
            domains = DomainJournal(config['domain_path'], initialize=initialize, role='NODE', policy=domain_policy); self._resources.append(domains)
            writers = None
            if config['writer_policy'] is not None:
                writers = NodePrincipalRuntime(root, gateway_public_key=gateway_key, audience=http.origin,
                    device_id=record['device_id'], route_generation=config['route_generation'], session_id=config['session_id'],
                    policy=WriterPolicy(**config['writer_policy']), initialize=initialize)
                self._resources.append(writers)
            if config['worktree_policy'] is not None:
                if writers is None or config['worktree_config'] is None:
                    raise WireError('FLEET_CONFIG_INVALID')
                from ..fleet.worktrees import NodeWorktrees, WorktreePolicy
                fields(config['worktree_config'], {'repositories', 'worktree_root', 'git_executable'})
                worktrees = NodeWorktrees(root, principals=writers, **config['worktree_config'],
                    policy=WorktreePolicy(**config['worktree_policy']), initialize=initialize)
                self._resources.append(worktrees)
                writers.bind_worktrees(worktrees)
            elif config['worktree_config'] is not None:
                raise WireError('FLEET_CONFIG_INVALID')
            installations = []
            if type(config['sdk_qualifications']) is not list or len(config['sdk_qualifications']) > 16:
                raise WireError('FLEET_CONFIG_INVALID')
            from ..fleet.sdk_qualification import QualifiedSdkInstallation
            for item in config['sdk_qualifications']:
                fields(item, {'manifest_file', 'operator_public_key', 'payload_manifest_file'})
                installations.append(QualifiedSdkInstallation.from_operator_manifest(item['manifest_file'],
                    _public_key(item['operator_public_key']), configuration(item['payload_manifest_file'])))
            read_adapter = None
            if installations:
                from ..fleet.sdk_controller import QualifiedReadAdapter
                read_adapter = QualifiedReadAdapter(root, ConcurrencyManager(root), tuple(installations))
            capacity = None
            self._coordinator, self._capacity_registered = None, False
            if config['capacity_trust'] is not None:
                from ..fleet.scoped_resources import ScopedResourceCoordinator
                trust = config['capacity_trust']
                fields(trust, {'trusted_owner_public_key', 'candidate_sha256', 'runtime_sha256'})
                for name in trust: _public_key(trust[name])
                coordinator = ScopedResourceCoordinator.open_installed(root, device_id=record['device_id'], **trust)
                if coordinator is None: raise WireError('NATIVE_CAPACITY_UNQUALIFIED')
                capacity = coordinator.verified_capacity_roster(config['route_generation'])
                self._coordinator = coordinator
            fields(config['artifact_policy'], {'installation_id', 'max_artifact_bytes', 'max_chunk_bytes'})
            artifacts = ArtifactProxy(root, node_id=record['device_id'], **config['artifact_policy'])
            verifier = NativeAuthorizationVerifier(config['gateway_public_key'], http.origin, clock_ms=lambda: int(time.time() * 1000))
            self.dispatcher = NodeDomainDispatcher(root, domains, jobs, RoutedNativeAdapter(root), artifacts=artifacts,
                principal_runtime=writers, authorization_verifier=verifier, max_inventory_rows=config['max_inventory_rows'], capacity_roster=capacity)
            self.agent = OutboundNode(client, root, policy, session_id=config['session_id'],
                qualified_read_adapter=read_adapter, domain_dispatcher=self.dispatcher)
            self.policy, self.config, self.client = policy, config, client
        except BaseException:
            self.close()
            raise

    def request_stop(self):
        if not self._stopping:
            self._stopping = True
            self._drain_deadline = time.monotonic() + self.config['drain_timeout_ms'] / 1000
        return self.stop_status()

    def reconcile(self, value):
        """Build scoped recovery evidence from local journals before new intent."""
        from ..fleet.identity import IdentityRegistry
        from ..fleet.job_journal import canonical
        fields(value, {'schema', 'coordination_sha256', 'joint_scope', 'job_scope'})
        if value['schema'] != 'fleet.node-recovery-input/1': raise WireError('FLEET_RECOVERY_INPUT_INVALID')
        scope, job_scope = value['joint_scope'], value['job_scope']
        _public_key(value['coordination_sha256'])
        if (type(scope) is not dict or logical_digest(scope) != value['coordination_sha256']
                or scope.get('audience') != self.client.http.origin or scope.get('schema') != 'fleet.joint-restore/1'):
            raise WireError('FLEET_RECOVERY_INPUT_INVALID')
        fields(job_scope, {'schema', 'challenge', 'export_generation', 'devices', 'reconciled'})
        if (job_scope['schema'] != 'fleet.restore/1' or job_scope['challenge'] != scope.get('challenge')
                or job_scope['export_generation'] != scope.get('job_export_generation')
                or sorted(job_scope['devices']) != sorted(item['device_id'] for item in scope['devices'])):
            raise WireError('FLEET_RECOVERY_INPUT_INVALID')
        registry = IdentityRegistry(Path(self.config['root'])).load()
        registry_sha = hashlib.sha256(canonical(registry)).hexdigest()
        enrolled = next((item for item in scope['devices'] if item['device_id'] == self.client.device_id), None)
        if (enrolled is None or enrolled['public_key'] != self.client.key.public_key().public_bytes_raw().hex()
                or enrolled['route_generation'] != self.client.route_generation or enrolled['session_id'] != self.agent.session_id
                or enrolled['registry_sha256'] != registry_sha or enrolled['state'] != 'ACTIVE'):
            raise WireError('FLEET_RECOVERY_SCOPE_MISMATCH')
        packet = {'schema': 'fleet.reconcile/1', 'coordination_sha256': value['coordination_sha256'],
            'registry_sha256': registry_sha, 'session_id': self.agent.session_id,
            'transport_witness': self.client.transport_journal.witness(scope['challenge']),
            'job_witness': self.dispatcher.native.witness({**job_scope, 'coordination_sha256': value['coordination_sha256'],
                'joint_scope': scope}, device_id=self.client.device_id, route_generation=self.client.route_generation,
                session_id=self.agent.session_id, private_key=self.client.key)}
        if 'domain_head' in scope:
            packet['domain_witness'] = self.dispatcher.journal.witness(value['coordination_sha256'],
                device_id=self.client.device_id, route_generation=self.client.route_generation, session_id=self.agent.session_id)
        if 'principal_head' in scope:
            if self.dispatcher.principals is None:
                from ..fleet.writers import empty_writer_witness
                packet['principal_witness'] = empty_writer_witness(self.config['root'], device_id=self.client.device_id,
                    route_generation=self.client.route_generation, session_id=self.agent.session_id,
                    coordination_sha256=value['coordination_sha256'], expected_worktree_head=enrolled['worktree_head'])
            else:
                packet['principal_witness'] = self.dispatcher.principals.witness(value['coordination_sha256'])
        return self.client.reconcile(packet)

    def stop_status(self):
        active = self.dispatcher is not None and self.dispatcher.has_pending_work()
        return {'schema': 'fleet.node-stop/1', 'status': 'STOP_PENDING' if active else 'DRAINED',
            'deadline_elapsed': self._drain_deadline is not None and time.monotonic() >= self._drain_deadline}

    def run_once(self):
        if self._closed:
            raise WireError('NODE_RUNTIME_CLOSED')
        if self._stopping:
            response = self.agent.step(poll_commands=False)
            return {'schema': 'fleet.node-drain/1', 'responses': response, 'stop': self.stop_status()}
        if self._coordinator is not None and not self._capacity_registered:
            self.client.heartbeat(self.agent.session_id)
            self.client.register_capacity(self.agent.session_id, **self._coordinator.registration_payload())
            self._capacity_registered = True
        return self.agent.step()

    def close(self):
        if self._closed:
            return {'schema': 'fleet.node-stop/1', 'status': 'CLOSED'}
        if self.dispatcher is not None and self.dispatcher.has_pending_work():
            self.request_stop()
            return self.stop_status()
        error = None
        if self.dispatcher is not None:
            try: self.dispatcher.close()
            except BaseException as caught: error = caught
        for resource in reversed(self._resources):
            try: resource.close()
            except BaseException as caught: error = error or caught
        if error is not None:
            raise error
        self._resources.clear(); self._closed = True
        return {'schema': 'fleet.node-stop/1', 'status': 'CLOSED'}


_CLIENT_DOMAIN = {name: '/fleet/v1/' + name for name in (
    'projects/create', 'projects/enroll', 'projects/get', 'projects/default-target', 'projects/freeze',
    'projects/resume', 'projects/baseline', 'jobs/cancel', 'artifacts/manifest', 'artifacts/chunk',
    'writers/acquire', 'writers/release', 'sources/write', 'worktrees/prepare', 'worktrees/commit', 'worktrees/retire')}
CLIENT_OPERATIONS = tuple(['info', 'inventory', 'read-state', 'read-account', 'read-status', 'snapshot', 'command-status',
    'jobs/launch', 'jobs/status', 'jobs/recover', 'admin/grant', 'admin/revoke', 'admin/rotate', 'principals/issue',
    'principals/revoke', 'principals/assign', 'principals/release', 'principals/reconcile', *_CLIENT_DOMAIN])


def client_request(client, operation, value):
    if operation == 'info': fields(value, set()); return client.server_info()
    if operation == 'inventory':
        if value == {}: return client.inventory()
        fields(value, {'node', 'operation_id'}); return client.inventory(**value)
    if operation in {'read-state', 'read-account'}:
        fields(value, {'target', 'operation_id'})
        return client.read('get_terminal_live_state' if operation == 'read-state' else 'get_account_snapshot', value['target'], value['operation_id'])
    if operation == 'read-status': fields(value, {'command_id'}); return client.read_status(**value)
    if operation == 'snapshot': fields(value, {'targets', 'operation'}); return client.snapshot(value['targets'], value['operation'])
    if operation == 'command-status': fields(value, {'command_id'}); return client.command_status(**value)
    if operation == 'jobs/launch': fields(value, {'operation_id', 'request'}); return client.launch_job(**value)
    if operation == 'jobs/status': fields(value, {'global_job_id'}); return client.get_job(**value)
    if operation == 'jobs/recover': fields(value, {'operation_id', 'global_job_id', 'node', 'session_id'}); return client.recover_job(**value)
    if operation.startswith('admin/') and operation in CLIENT_OPERATIONS: return client.admin(operation.split('/')[1], value)
    if operation.startswith('principals/') and operation in CLIENT_OPERATIONS: return client.principal(operation.split('/')[1], value)
    if operation in _CLIENT_DOMAIN:
        fields(value, {'node', 'operation_id', 'payload'})
        return client.domain(_CLIENT_DOMAIN[operation], value['node'], value['operation_id'], value['payload'])
    raise WireError('DOMAIN_OPERATION_INVALID')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='vibemql5-fleet')
    parser.add_argument('--config', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    gateway = commands.add_parser('gateway'); gateway.add_argument('--initialize', action='store_true')
    node = commands.add_parser('node'); node.add_argument('--initialize', action='store_true'); node.add_argument('--once', action='store_true'); node.add_argument('--pair-file'); node.add_argument('--reconcile-file')
    client = commands.add_parser('client'); client.add_argument('operation', choices=CLIENT_OPERATIONS); client.add_argument('--request-file', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'client':
            result = client_request(FleetClientFacade.from_config(args.config), args.operation, configuration(args.request_file))
            print(json.dumps(result, ensure_ascii=True, sort_keys=True)); return 0
        config = operator_configuration(args.config)
        stopped = threading.Event()
        for name in ('SIGINT', 'SIGTERM'):
            if hasattr(signal, name): signal.signal(getattr(signal, name), lambda *_: stopped.set())
        if args.command == 'gateway':
            from ..fleet.transport import serve_gateway
            factory = gateway_factory(config, initialize=args.initialize)
            context = operator_server_context(config['certificate_file'], config['tls_key_file'])
            serve_gateway((config['listen_host'], config['listen_port']), ssl_context=context,
                controller_factory=factory, stop_event=stopped)
            return 0
        pairing = None if args.pair_file is None else operator_configuration(args.pair_file, maximum=16384)
        runtime = NodeRuntime(config, initialize=args.initialize, pairing=pairing)
        try:
            if args.reconcile_file is not None:
                if args.initialize: raise WireError('FLEET_RECOVERY_REOPEN_REQUIRED')
                result = runtime.reconcile(operator_configuration(args.reconcile_file, maximum=config['domain_policy']['max_payload_bytes']))
                print(json.dumps(result, ensure_ascii=True, sort_keys=True))
            first, reported_stop = True, False
            while True:
                if stopped.is_set() or (args.once and not first): runtime.request_stop()
                try:
                    result = runtime.run_once()
                    if args.once and first: print(json.dumps(result, ensure_ascii=True, sort_keys=True))
                    if runtime._stopping and runtime.stop_status()['deadline_elapsed'] and not reported_stop:
                        print(json.dumps(runtime.stop_status()), flush=True)
                        reported_stop = True
                except WireError as error:
                    print(json.dumps({'schema': 'fleet.node-status/1', 'code': error.code}), flush=True)
                first = False
                if runtime._stopping and runtime.close()['status'] == 'CLOSED': break
                # An elapsed drain deadline reports uncertainty; the owner loop
                # continues servicing RPC and never force-terminates native work.
                threading.Event().wait(runtime.policy.poll_interval_ms / 1000)
        finally:
            runtime.close()
        return 0
    except Exception as error:
        code = getattr(error, 'code', 'FLEET_STARTUP_FAILED')
        if type(code) is not str or not code.isascii() or not code.replace('_', '').isalnum(): code = 'FLEET_STARTUP_FAILED'
        print(json.dumps({'schema': 'fleet.error/1', 'code': code})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
