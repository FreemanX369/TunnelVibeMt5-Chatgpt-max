"""One explicitly provisioned single-VPS pilot; preserves all runtime journals."""
import hashlib
import json
import os
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r'C:\VibeMQL5')
ROOT = BASE / 'ops/windows/fleet-pilot-745147f-20261016-a'
RUNTIME = ROOT / 'runtime'
SECRETS = RUNTIME / 'secrets'
HEAD = '9d2f53764cf1a1dac5f3de1835484eede58db03e'
DEVICE = 'dev_e488e5a0105847febf7ed46c9e15e9d0'


def receipt(name, value):
    value = dict(value, at_utc=datetime.now(timezone.utc).isoformat(), pid=os.getpid(), source_head=HEAD)
    path = RUNTIME / name
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return value


def main():
    if sys.argv[1:] not in (['--initialize'], ['--resume'], ['--recover-empty-bootstrap']):
        raise RuntimeError('EXPLICIT_MODE_REQUIRED')
    if sys.argv[1] != '--resume':
        raise RuntimeError('FIX_RELEASE_RESUME_ONLY')
    recover = sys.argv[1] == '--recover-empty-bootstrap'
    initialize = sys.argv[1] != '--resume'
    raw = (ROOT / 'releases/fix2/STAGING-MANIFEST.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '3dcc83da712ed6b4c6155791496b47e359bbd46b8ec8b85a190ded9149d1175a':
        raise RuntimeError('MANIFEST_CHANGED')
    for entry in json.loads(raw)['files']:
        content = (BASE / entry['target_path']).read_bytes()
        if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise RuntimeError('SOURCE_CHANGED')
    sys.path.insert(0, str(ROOT / 'releases/fix2/source/app'))
    from vibemql5.adapters.fleet_cli import NodeRuntime, gateway_factory, operator_server_context
    from vibemql5.adapters.fleet_client_tools import FleetClientFacade, operator_configuration
    from vibemql5.fleet.transport import serve_gateway
    from vibemql5.fleet import node_keys as keys
    from vibemql5.fleet.pilot_runtime import PilotRoundGuard
    gateway_config = operator_configuration(SECRETS / 'gateway.json')
    node_config = operator_configuration(SECRETS / 'node.json')
    if node_config['sdk_qualifications'] or node_config['writer_policy'] or node_config['worktree_policy']:
        raise RuntimeError('PILOT_SCOPE_CHANGED')
    if (RUNTIME / 'STOP').exists():
        raise RuntimeError('STOP_FILE_PRESENT')
    # Exclusive lease prevents parallel pilot processes; retain journal state on exit.
    import msvcrt
    lease = (RUNTIME / 'process.lock').open('a+b')
    lease.seek(0)
    if not lease.read(1):
        lease.write(b'1'); lease.flush()
    lease.seek(0)
    msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
    if recover:
        # The first startup created ONLY an empty control store before rejecting
        # the example's journal limit. Never reset or replace this store.
        from vibemql5.fleet.gateway_control import GatewayControlStore, Policy
        from vibemql5.fleet.job_journal import GatewayJobJournal
        from vibemql5.fleet.domain import DomainJournal, DomainPolicy
        from vibemql5.fleet.principals import GatewayPrincipalAuthority, PrincipalPolicy
        from vibemql5.fleet.node_keys import load_node_key
        control = GatewayControlStore.open_existing(gateway_config['control_path'], policy=Policy(**gateway_config['control_policy']))
        try:
            snapshot = control.snapshot()
            if snapshot['revision'] != 1 or any(snapshot[field] for field in ('devices','grants','nonces','operations')):
                raise RuntimeError('BOOTSTRAP_NOT_EMPTY')
        finally:
            control.close()
        if any(Path(config[field]).exists() for config, fields in (
            (gateway_config, ('jobs_path','domain_path','principal_path')),
            (node_config, ('jobs_path','domain_path','transport_path'))) for field in fields):
            raise RuntimeError('BOOTSTRAP_UNEXPECTED_JOURNALS')
        for name, config in (('gateway.json', gateway_config), ('node.json', node_config)):
            original = (SECRETS / name).read_bytes()
            descriptor = keys._windows_create(keys._path(SECRETS / (name + '.before-journal-limit')))
            try:
                keys._windows_acl(descriptor, set_restrictive=True); keys._check(descriptor)
                with os.fdopen(descriptor, 'wb', closefd=False) as stream:
                    stream.write(original); stream.flush(); os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if config['journal_policy']['max_payload_bytes'] != 1048576:
                raise RuntimeError('BOOTSTRAP_CONFIG_CHANGED')
            config['journal_policy']['max_payload_bytes'] = 262144
            with (SECRETS / name).open('r+b') as stream:
                keys._check(stream.fileno())
                if stream.read() != original:
                    raise RuntimeError('BOOTSTRAP_CONFIG_CAS')
                stream.seek(0); stream.write(json.dumps(config, indent=2).encode()); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
        resource = GatewayJobJournal(gateway_config['jobs_path'], initialize=True,
            capacity_owner_public_key=None, **gateway_config['journal_policy']); resource.close()
        resource = DomainJournal(gateway_config['domain_path'], initialize=True, role='GATEWAY',
            policy=DomainPolicy(**gateway_config['domain_policy'])); resource.close()
        resource = GatewayPrincipalAuthority(gateway_config['principal_path'],
            signing_key=load_node_key(gateway_config['authority_key_file']), audience=gateway_config['origin'],
            policy=PrincipalPolicy(**gateway_config['principal_policy']), initialize=True); resource.close()
        receipt('BOOTSTRAP-REPAIR-RECEIPT.json', {'status':'EMPTY_CONTROL_PRESERVED', 'revision':snapshot['revision'],
            'journal_max_payload_bytes':262144})
    ready, failures = queue.Queue(), queue.Queue()
    stopped = threading.Event()
    def gateway():
        try:
            serve_gateway(('127.0.0.1', 8443),
                ssl_context=operator_server_context(gateway_config['certificate_file'], gateway_config['tls_key_file']),
                controller_factory=gateway_factory(gateway_config, initialize=initialize and not recover),
                stop_event=stopped, started=ready.put)
        except BaseException as error:
            failures.put(type(error).__name__ + ':' + str(error))
    thread = threading.Thread(target=gateway, name='pilot-gateway', daemon=True)
    node = None
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while ready.empty():
            if not failures.empty():
                raise RuntimeError(failures.get())
            if time.monotonic() >= deadline:
                raise RuntimeError('GATEWAY_START_TIMEOUT')
            stopped.wait(.1)
        facade = FleetClientFacade.from_config(SECRETS / 'owner-client.json')
        facade.http.pin_loopback_address('127.0.0.1')
        pairing = None
        if initialize:
            provision = json.loads((RUNTIME / 'PROVISION-RECEIPT.json').read_bytes())
            grant = facade.admin('grant', {'device_id': DEVICE, 'public_key': provision['node_public_key'],
                'operation_id': 'pilot-745147f-grant-20261016-a', 'expected_revision': 1,
                'expected_route_generation': None})
            pairing = {'schema': 'fleet.pair/1', 'grant_id': grant['receipt']['grant_id'],
                'secret': grant['secret'], 'operation_id': 'pilot-745147f-pair-20261016-a', 'expected_revision': 2}
            descriptor = keys._windows_create(keys._path(SECRETS / 'pair.json'))
            try:
                keys._windows_acl(descriptor, set_restrictive=True); keys._check(descriptor)
                with os.fdopen(descriptor, 'wb', closefd=False) as stream:
                    stream.write(json.dumps(pairing).encode()); stream.flush(); os.fsync(descriptor)
            finally:
                os.close(descriptor)
        node = NodeRuntime(node_config, initialize=initialize, pairing=pairing)
        node.client.http.pin_loopback_address('127.0.0.1')
        def observed_step():
            began = time.monotonic()
            try:
                return node.run_once()
            except Exception as error:
                cause = error.__context__
                stack = []
                frame = cause.__traceback__ if cause is not None else None
                while frame is not None and len(stack) < 12:
                    stack.append({'file':Path(frame.tb_frame.f_code.co_filename).name, 'function':frame.tb_frame.f_code.co_name,'line':frame.tb_lineno})
                    frame = frame.tb_next
                receipt('CONTROL-ERROR-LAST.json', {'status':'NODE_ROUND_FAILED','code':getattr(error,'code',type(error).__name__),'elapsed_seconds':time.monotonic()-began,'cause_type':type(cause).__name__,'cause_errno':getattr(cause,'errno',None),'cause_stack':stack})
                raise
        round_guard = PilotRoundGuard()
        node_status = round_guard.run(observed_step)
        try:
            inventory = facade.inventory()
        except Exception:
            inventory = {'status':'UNAVAILABLE', 'reason_code':'CONTROL_OBSERVATION_FAILED'}
        receipt('STARTUP-RECEIPT.json', {'status': 'RUNNING', 'mode': sys.argv[1], 'origin': gateway_config['origin'],
            'inventory': inventory, 'sdk_qualifications': [], 'native_capacity': 'NOT_QUALIFIED'})
        last = 0
        while not (RUNTIME / 'STOP').exists():
            if not thread.is_alive():
                raise RuntimeError(failures.get_nowait() if not failures.empty() else 'GATEWAY_EXITED')
            node_status = round_guard.run(observed_step)
            if node_status['status'] != 'RUNNING':
                receipt('CONTROL-ROUND-RECEIPT.json', node_status)
            if time.monotonic() - last >= 5:
                try:
                    inventory = facade.inventory()
                except Exception:
                    inventory = {'status':'UNAVAILABLE', 'reason_code':'CONTROL_OBSERVATION_FAILED'}
                receipt('LIVE.json', {'status': node_status['status'], 'node':node_status, 'inventory': inventory})
                last = time.monotonic()
            stopped.wait(max(node.policy.poll_interval_ms / 1000, node_status['retry_after_seconds'], 1 if round_guard.fenced else 0))
    finally:
        if node is not None:
            node.request_stop()
            while node.close()['status'] != 'CLOSED':
                node.run_once(); stopped.wait(.1)
        stopped.set(); thread.join(10)
        receipt('STOP-RECEIPT.json', {'status': 'STOPPED' if not thread.is_alive() else 'GATEWAY_STOP_PENDING'})
        lease.close()


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        receipt('FAILURE-RECEIPT.json', {'status': 'FAILED_PRESERVE_JOURNALS',
            'error_type': type(error).__name__, 'reason': str(error)})
        raise
