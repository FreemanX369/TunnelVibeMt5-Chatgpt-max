"""Finite actual-owned TLS cost observation; no injected delays or new reads."""
import json
import os
from pathlib import Path
import threading
import time

import pytest

AGGREGATES = {}
LOCAL = threading.local()
LOCK = threading.Lock()
ROWS = []
ROUTES = {'/fleet/v1/native/start': 'NATIVE_START', '/fleet/v1/heartbeat': 'HEARTBEAT',
          '/fleet/v1/poll': 'POLL', '/fleet/v1/results': 'RESULT',
          '/fleet/v1/pair': 'PAIR'}

def aggregate(kind, elapsed):
    key = (kind, getattr(LOCAL, 'route', 'OTHER'))
    with LOCK:
        row = AGGREGATES.setdefault(key, {'calls': 0, 'inclusive_seconds': 0.0, 'maximum_seconds': 0.0})
        row['calls'] += 1
        row['inclusive_seconds'] += elapsed
        row['maximum_seconds'] = max(row['maximum_seconds'], elapsed)

@pytest.fixture(autouse=True)
def profile_actual_owned_case(monkeypatch):
    from vibemql5.fleet.gateway_control import GatewayControlStore
    from vibemql5.fleet.node_transport_journal import NodeTransportJournal
    from vibemql5.fleet import transport
    from vibemql5.fleet.native_authorization import GatewayNativeSigner, NativeAuthorizationVerifier

    def timed(owner, name, label):
        original = getattr(owner, name)
        def measured(*args, **kwargs):
            begun = time.monotonic()
            try:
                return original(*args, **kwargs)
            finally:
                aggregate(label, max(0, time.monotonic() - begun))
        monkeypatch.setattr(owner, name, measured)

    handle, post = transport.GatewayController.handle, transport.NodeClient._post
    def gateway(self, method, path, *args, **kwargs):
        previous = getattr(LOCAL, 'route', 'OTHER')
        LOCAL.route = 'GW_' + ROUTES.get(path, 'OTHER')
        begun = time.monotonic()
        try:
            return handle(self, method, path, *args, **kwargs)
        finally:
            aggregate('GATEWAY_HANDLE', max(0, time.monotonic() - begun))
            LOCAL.route = previous
    def client(self, path, *args, **kwargs):
        previous = getattr(LOCAL, 'route', 'OTHER')
        LOCAL.route = 'NODE_' + ROUTES.get(path, 'OTHER')
        begun = time.monotonic()
        try:
            return post(self, path, *args, **kwargs)
        finally:
            aggregate('NODE_POST', max(0, time.monotonic() - begun))
            LOCAL.route = previous
    monkeypatch.setattr(transport.GatewayController, 'handle', gateway)
    monkeypatch.setattr(transport.NodeClient, '_post', client)
    for owner, name, label in [(GatewayControlStore, '_validate', 'GW_FULL_VALIDATE'),
                               (GatewayControlStore, 'get_route', 'GW_GET_ROUTE'),
                               (GatewayControlStore, 'control_head', 'GW_CONTROL_HEAD'),
                               (NodeTransportJournal, '_validate', 'NODE_FULL_VALIDATE'),
                               (NodeTransportJournal, 'begin', 'NODE_INTENT'),
                               (NodeTransportJournal, 'acknowledge', 'NODE_ACK'),
                               (transport, 'verify_request', 'SIGNED_REQUEST_VERIFY'),
                               (GatewayNativeSigner, 'issue', 'NATIVE_SIGN'),
                               (NativeAuthorizationVerifier, 'verify', 'NATIVE_VERIFY')]:
        timed(owner, name, label)
    rpc = transport.NodeRpcProxy._request
    def request(self, kind, payload):
        begun = time.monotonic()
        try:
            return rpc(self, kind, payload)
        finally:
            elapsed = max(0, time.monotonic() - begun)
            aggregate('WORKER_RPC_WAIT', elapsed)
            command = payload.get('command', {}) if isinstance(payload, dict) else {}
            event = command.get('authorization_event') if isinstance(command, dict) else None
            if event not in ('phase_admission', 'snapshot_prepare:0001', 'compile_run_prepare:0001', 'compile_log_capture:0001'):
                event = 'OTHER'
            if len(ROWS) < 16:
                ROWS.append({'kind': kind if kind == 'START_AUTHORIZE' else 'OTHER',
                             'event': event, 'elapsed_ms': elapsed * 1000})
    monkeypatch.setattr(transport.NodeRpcProxy, '_request', request)
    yield

def pytest_sessionfinish(session, exitstatus):
    rows = [{'kind': kind, 'route': route, **value} for (kind, route), value in sorted(AGGREGATES.items())]
    Path(os.environ['OWNED_COST_RECEIPT']).write_text(json.dumps({
        'schema': 'owned-runtime-cost/1', 'host_platform': os.name,
        'windows_causal_qualification': 'NOT_RUN', 'exit_status': exitstatus,
        'inclusive_times_overlap': True, 'aggregates': rows, 'RPC_rows': ROWS}, indent=2) + '\n')
