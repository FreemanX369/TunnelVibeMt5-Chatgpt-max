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
HEAD = '745147f525caefbec66505e5cdb6a4fb7013c2d7'
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
    if sys.argv[1:] not in (['--initialize'], ['--resume']):
        raise RuntimeError('EXPLICIT_MODE_REQUIRED')
    initialize = sys.argv[1] == '--initialize'
    raw = (ROOT / 'STAGING-MANIFEST.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != '5ae7d19d5a7019936c0b21611a8c0825374dc96527d69b6cb37eac69a2e7758a':
        raise RuntimeError('MANIFEST_CHANGED')
    for entry in json.loads(raw)['files']:
        content = (BASE / entry['target_path']).read_bytes()
        if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise RuntimeError('SOURCE_CHANGED')
    sys.path.insert(0, str(ROOT / 'source/app'))
    from vibemql5.adapters.fleet_cli import NodeRuntime, gateway_factory, operator_server_context
    from vibemql5.adapters.fleet_client_tools import FleetClientFacade, operator_configuration
    from vibemql5.fleet.transport import serve_gateway
    from vibemql5.fleet import node_keys as keys
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
    ready, failures = queue.Queue(), queue.Queue()
    stopped = threading.Event()
    def gateway():
        try:
            serve_gateway(('127.0.0.1', 8443),
                ssl_context=operator_server_context(gateway_config['certificate_file'], gateway_config['tls_key_file']),
                controller_factory=gateway_factory(gateway_config, initialize=initialize),
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
        node.run_once()
        inventory = facade.inventory()
        receipt('STARTUP-RECEIPT.json', {'status': 'RUNNING', 'mode': sys.argv[1], 'origin': gateway_config['origin'],
            'inventory': inventory, 'sdk_qualifications': [], 'native_capacity': 'NOT_QUALIFIED'})
        last = 0
        while not (RUNTIME / 'STOP').exists():
            if not thread.is_alive():
                raise RuntimeError(failures.get_nowait() if not failures.empty() else 'GATEWAY_EXITED')
            node.run_once()
            if time.monotonic() - last >= 5:
                receipt('LIVE.json', {'status': 'RUNNING', 'inventory': facade.inventory()})
                last = time.monotonic()
            stopped.wait(node.policy.poll_interval_ms / 1000)
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
