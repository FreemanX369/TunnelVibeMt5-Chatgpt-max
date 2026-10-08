"""Finite, fail-open timings of original owned fixture operations only."""
from contextlib import contextmanager
import http.client as http_client
import json
import ssl
import threading
from time import perf_counter

import pytest

from vibemql5.fleet.wire import WireError

CASES = frozenset({
    'test_actual_tls_blocked_native_keeps_heartbeat_status_cancel_and_lost_ack_durable',
    'test_actual_tls_inventory_discovery_read_project_and_production_native_denial',
    'test_actual_tls_client_possession_to_async_guarded_source_two_commits_and_phase_ack',
    'test_actual_node_startup_replacement_session_preserves_inactive_writer_and_recovers_only_history',
})
ROUTES = {'/fleet/v1/heartbeat': 'HEARTBEAT', '/fleet/v1/poll': 'POLL',
          '/fleet/v1/native/start': 'AUTHORIZE', '/fleet/v1/results': 'RESULT',
          '/fleet/v1/writers/authorize': 'WRITER'}
STAGES = ('STEP', 'HEARTBEAT', 'POLL', 'POLL_CANCEL', 'RPC', 'DRAIN', 'POST',
          'CONNECT_INCL_TLS', 'TLS_WRAP', 'VALIDATE', 'BEGIN', 'ACK', 'HANDLE',
          'TX_ENTER', 'TX_BODY', 'TX_EXIT', 'ATOMIC', 'CLOSE', 'PUMP', 'ROUND', 'PREDICATE')
PHASES = ('GENERAL', 'PUMP', 'ROUND', 'CLEANUP')
ACTORS = ('CONTROL', 'GATEWAY')
OUTCOMES = ('RETURNED', 'WIRE_ERROR', 'ASSERTION', 'OTHER_ERROR', 'BASE_EXCEPTION')


def category(error):
    if error is None: return 'RETURNED'
    if isinstance(error, WireError): return 'WIRE_ERROR'
    if isinstance(error, AssertionError): return 'ASSERTION'
    return 'OTHER_ERROR' if isinstance(error, Exception) else 'BASE_EXCEPTION'


def error_categories(error):
    """Copy fixed categories only; retain no exception, traceback or user text."""
    result, seen = [], set()
    try:
        while error is not None and len(result) < 4 and id(error) not in seen:
            seen.add(id(error)); result.append(category(error))
            error = error.__cause__ if error.__cause__ is not None else (
                None if error.__suppress_context__ else error.__context__)
    except BaseException:
        pass
    return tuple(result)


def route(value):
    return ROUTES.get(value, 'OTHER') if type(value) is str else 'OTHER'


class TimedContext:
    """Forward the original context protocol including suppression and throw."""
    def __init__(self, observer, original, actor):
        self.observer, self.original, self.actor = observer, original, actor

    def __enter__(self):
        self.active = self.observer.owned(self.actor)
        if not self.active: return self.original.__enter__()
        result = self.observer.call(self.actor, 'TX_ENTER', self.original.__enter__)
        self.phase = self.observer.phase
        self.began = self.observer.now()
        return result

    def __exit__(self, kind, error, traceback):
        if not self.active or not self.observer.owned(self.actor):
            return self.original.__exit__(kind, error, traceback)
        self.observer.safe_record(self.actor, 'TX_BODY', self.phase, self.began, category(error), chain=error_categories(error))
        return self.observer.call(self.actor, 'TX_EXIT', self.original.__exit__, kind, error, traceback)


class PipelineObservation:
    def __init__(self, enabled=True, clock=perf_counter):
        self.enabled, self.clock, self.phase = enabled, clock, 'GENERAL'
        self.threads = {'CONTROL': threading.current_thread(), 'GATEWAY': None}
        self.local, self.restores = threading.local(), []
        self.observer_error = False
        self.rows = {actor: [] for actor in ACTORS}
        self.row_priority = {actor: -1 for actor in ACTORS}
        self.row_counts = {actor: 0 for actor in ACTORS}
        # Keys are fixed before any actor starts: snapshots cannot change size.
        self.counters = {actor: {(phase, stage, name): [0, 0, 0, 0]
            for phase in PHASES for stage in STAGES
            for name in ('OTHER', 'HEARTBEAT', 'POLL', 'AUTHORIZE', 'RESULT', 'WRITER')}
            for actor in ACTORS}
        self.origin = self.now() if enabled else None

    def owned(self, actor):
        return self.enabled and self.threads[actor] is threading.current_thread()

    def now(self):
        try: return self.clock()
        except BaseException:
            self.observer_error = True
            return None

    def safe_record(self, *args, **kwargs):
        try: self.record(*args, **kwargs)
        except BaseException: self.observer_error = True

    def record(self, actor, stage, phase, began, outcome, name='OTHER', *, chain=()):
        if not self.owned(actor): return
        try:
            ended = self.now()
            if began is None or ended is None or self.origin is None: return
            elapsed = max(0, round((ended - began) * 1000000))
            count = self.counters[actor][phase, stage, name]
            count[0] = min(2147483647, count[0] + 1)
            count[1] = min(9007199254740991, count[1] + elapsed)
            count[2] = max(count[2], min(9007199254740991, elapsed))
            count[3] = min(2147483647, count[3] + (outcome != 'RETURNED'))
            self.row_counts[actor] = min(2147483647, self.row_counts[actor] + 1)
            row = {'actor': actor, 'stage': stage, 'phase': phase, 'route': name,
                   'sequence': self.row_counts[actor], 'outcome': outcome,
                   'start_us': max(0, round((began - self.origin) * 1000000)),
                   'elapsed_us': elapsed, 'error_categories': list(chain)}
            # Keep the failing round/pump visible after original cleanup.
            priority = 4 if outcome != 'RETURNED' else {'GENERAL': 0, 'CLEANUP': 1, 'PUMP': 2, 'ROUND': 3}[phase]
            if priority < self.row_priority[actor]: return
            if priority > self.row_priority[actor]:
                self.rows[actor].clear(); self.row_priority[actor] = priority
            self.rows[actor].append(row)
            if len(self.rows[actor]) > 16: del self.rows[actor][0]
        except BaseException:
            self.observer_error = True

    def call(self, actor, stage, original, *args, _route='OTHER', _phase=None, **kwargs):
        if not self.owned(actor): return original(*args, **kwargs)
        began, phase, outcome, chain = self.now(), _phase or self.phase, 'RETURNED', ()
        try:
            return original(*args, **kwargs)
        except BaseException as error:
            outcome, chain = category(error), error_categories(error)
            raise
        finally:
            self.safe_record(actor, stage, phase, began, outcome, _route, chain=chain)

    @contextmanager
    def span(self, phase):
        if not self.owned('CONTROL'):
            yield
            return
        prior, self.phase = self.phase, phase
        began, outcome, chain = self.now(), 'RETURNED', ()
        try:
            yield
        except BaseException as error:
            outcome, chain = category(error), error_categories(error)
            raise
        finally:
            self.safe_record('CONTROL', phase, phase, began, outcome, chain=chain)
            self.phase = prior

    def patch(self, target, name, replacement):
        present, prior = name in vars(target), vars(target).get(name)
        def restore():
            if present: setattr(target, name, prior)
            else: delattr(target, name)
        self.restores.append(restore)
        setattr(target, name, replacement)

    def wrap(self, target, name, actor, stage, *, context=False):
        original = getattr(target, name)
        def observed(*args, **kwargs):
            if not self.owned(actor): return original(*args, **kwargs)
            if context:
                return TimedContext(self, original(*args, **kwargs), actor)
            return self.call(actor, stage, original, *args,
                             _phase='CLEANUP' if stage == 'CLOSE' else None, **kwargs)
        self.patch(target, name, observed)

    def install(self, action):
        if not self.enabled: return
        checkpoint = len(self.restores)
        try: action()
        except BaseException:
            self.observer_error = True
            self.restore(checkpoint)

    def restore(self, checkpoint=0):
        while len(self.restores) > checkpoint:
            restore = self.restores.pop()
            try: restore()
            except BaseException: self.observer_error = True

    def bind_gateway(self, controller):
        def install():
            self.threads['GATEWAY'] = threading.current_thread()
            original = controller.handle
            def handle(*args, **kwargs):
                name = route(args[1] if len(args) > 1 else kwargs.get('path'))
                return self.call('GATEWAY', 'HANDLE', original, *args, _route=name, **kwargs)
            self.patch(controller, 'handle', handle)
            self.wrap(controller.store, '_validate', 'GATEWAY', 'VALIDATE')
            self.wrap(controller.store, '_transaction', 'GATEWAY', 'TX_ENTER', context=True)
            self.wrap(controller.store, 'close', 'GATEWAY', 'CLOSE')
            if controller.domain is not None:
                self.wrap(controller.domain.journal, '_validate', 'GATEWAY', 'VALIDATE')
                self.wrap(controller.domain.journal, '_atomic', 'GATEWAY', 'ATOMIC')
        self.install(install)

    def bind_http(self, http):
        def install():
            original, context = http.post, http.context
            def post(*args, **kwargs):
                if not self.owned('CONTROL'): return original(*args, **kwargs)
                prior = getattr(self.local, 'context', None)
                self.local.context = context
                try:
                    name = route(args[0] if args else kwargs.get('path'))
                    return self.call('CONTROL', 'POST', original, *args, _route=name, **kwargs)
                finally:
                    self.local.context = prior
            self.patch(http, 'post', post)
            # The stdlib seams are observed only inside this exact owned POST.
            original_connect = http_client.HTTPSConnection.connect
            connection_type = http_client.HTTPSConnection
            def connect(connection, *args, **kwargs):
                if self.owned('CONTROL') and getattr(self.local, 'context', None) is context and getattr(connection, '_context', None) is context:
                    return self.call('CONTROL', 'CONNECT_INCL_TLS', original_connect, connection, *args, **kwargs)
                return original_connect(connection, *args, **kwargs)
            self.patch(connection_type, 'connect', connect)
            original_wrap = ssl.SSLContext.wrap_socket
            def wrap_socket(selected_context, *args, **kwargs):
                if self.owned('CONTROL') and getattr(self.local, 'context', None) is context and selected_context is context:
                    return self.call('CONTROL', 'TLS_WRAP', original_wrap, selected_context, *args, **kwargs)
                return original_wrap(selected_context, *args, **kwargs)
            self.patch(ssl.SSLContext, 'wrap_socket', wrap_socket)
        self.install(install)

    def bind_runtime(self, client, agent, dispatcher, jobs, domains, transport):
        def install():
            for target, method, stage in ((agent, 'step', 'STEP'), (agent, '_service_rpc', 'RPC'),
                (client, 'heartbeat', 'HEARTBEAT'), (client, 'poll', 'POLL'),
                (client, 'poll_cancel_only', 'POLL_CANCEL'), (dispatcher, 'drain', 'DRAIN'),
                (transport, '_validate', 'VALIDATE'), (transport, 'begin', 'BEGIN'),
                (transport, 'acknowledge', 'ACK'), (domains, '_atomic', 'ATOMIC')):
                self.wrap(target, method, 'CONTROL', stage)
            self.wrap(jobs, 'transaction', 'CONTROL', 'TX_ENTER', context=True)
            for target in (dispatcher, dispatcher.principals, jobs, domains, transport):
                self.wrap(target, 'close', 'CONTROL', 'CLOSE')
        self.install(install)

    def bind_pump(self, module, agent):
        def install():
            original = module.pump
            def pump(selected_agent, *args, **kwargs):
                if selected_agent is not agent or not self.owned('CONTROL'):
                    return original(selected_agent, *args, **kwargs)
                with self.span('PUMP'):
                    return original(selected_agent, *args, **kwargs)
            self.patch(module, 'pump', pump)
        self.install(install)

    def bind_predicates(self, facade):
        def install():
            for name in ('get_job', 'command_status'):
                self.wrap(facade, name, 'CONTROL', 'PREDICATE')
        self.install(install)

    def summary(self):
        rows, counters = [], []
        for actor in ACTORS:
            rows.extend(list(self.rows[actor]))
            for (phase, stage, name), values in self.counters[actor].items():
                count, total, maximum, errors = values
                if count:
                    counters.append({'actor': actor, 'phase': phase, 'stage': stage, 'route': name,
                                     'count': count, 'total_us': total, 'max_us': maximum, 'errors': errors})
        return {'schema': 'fleet.fixture.pipeline/1', 'rows': rows, 'counters': counters,
                'rows_truncated': any(self.row_counts[a] > len(self.rows[a]) for a in ACTORS),
                'observer_error': self.observer_error,
                'scope': 'OWNED_CONTROL_GATEWAY_ONLY', 'durations': 'INCLUSIVE_ENTER_BODY_EXIT'}


def pipeline_for_request(request):
    """Shared fixture has no diagnostic dependency for foreign/manual users."""
    try:
        node = request.node
        name = getattr(node, 'originalname', None) or node.name
        if name not in CASES or 'pipeline_diagnostics' not in request.fixturenames:
            return None
        observer = request.getfixturevalue('pipeline_diagnostics')
        return observer if isinstance(observer, PipelineObservation) and observer.enabled else None
    except BaseException:
        return None


@pytest.fixture
def pipeline_diagnostics(request):
    observer = PipelineObservation(getattr(request.node, 'originalname', request.node.name) in CASES)
    try:
        yield observer
    finally:
        report_enabled = observer.enabled
        # A retained/in-flight wrapper must stop collecting after teardown even
        # if original gateway cleanup could not confirm thread termination.
        observer.enabled = False
        observer.restore()
        if report_enabled:
            # Capture/report happens after dependent composed fixture teardown.
            try: print('PIPELINE_FIXTURE ' + json.dumps(observer.summary(), sort_keys=True))
            except BaseException: observer.observer_error = True
