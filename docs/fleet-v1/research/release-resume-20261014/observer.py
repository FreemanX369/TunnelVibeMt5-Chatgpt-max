"""External, opt-in observations of original temporary pytest fixture calls."""
from contextlib import ExitStack
from functools import wraps
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

import pytest

STAGES = frozenset(('NATIVE_WORK', 'DISPATCH', 'EXECUTE', 'RESULT', 'OUTCOME',
    'AUTHORIZE', 'VERIFY', 'GATEWAY_AUTHORIZE', 'WRITER_RECHECK', 'CALLBACK_RESERVE',
    'CALLBACK_START', 'CALLBACK_EFFECT', 'DISPATCHER_CLOSE', 'PUMP', 'PREDICATE', 'CASE'))
PHASES = frozenset(('reserve', 'deploy', 'start', 'test', 'capture', 'cancel', 'result',
    'worktree_create', 'worktree_commit', 'worktree_retire', 'source_commit', 'session_commit'))
STATES = frozenset(('DELIVERED', 'RESERVED', 'STARTING', 'RUNNING', 'RESULT_PENDING',
    'FAILED', 'CANCELLED', 'SUCCEEDED', 'UNKNOWN', 'RECOVERY_REQUIRED', 'ISSUED', 'COMMITTED'))
CODES = frozenset(('HTTPS_UNAVAILABLE', 'HTTP_DEADLINE_EXCEEDED', 'HTTP_RESPONSE_INVALID',
    'NATIVE_AUTHORIZATION_EXPIRED', 'NATIVE_AUTHORIZATION_UNVERIFIED', 'NATIVE_AUTHORIZATION_MISMATCH',
    'NATIVE_QUALIFICATION_UNAVAILABLE', 'EXECUTION_OUTCOME_UNKNOWN', 'RESULT_OUTCOME_UNKNOWN',
    'WRITER_PHASE_UNRESOLVED', 'WRITER_PHASE_CONFLICT', 'WRITER_PROOF_INVALID', 'WRITER_EXPIRED',
    'WRITER_UNASSIGNED', 'WRITER_FENCE_MISMATCH', 'WRITER_COMMAND_UNAVAILABLE', 'WRITER_OUTCOME_UNKNOWN',
    'PRINCIPAL_INVALID', 'PRINCIPAL_SIGNATURE_INVALID', 'PRINCIPAL_EXPIRED', 'PRINCIPAL_REVOKED',
    'DOMAIN_WORKERS_ACTIVE', 'SCOPED_ROSTER_UNVERIFIED', 'SCOPE_RELEASE'))
CASE_IDS = {
    'tests/unit/test_tip064_capacity_https.py::test_capacity_positive_profile_delayed_durable_registration_has_no_retry[5000]': (1, 'CAPACITY_POSITIVE_5000'),
    'tests/unit/test_tip077_capacity_entry_watchdog.py::test_original_three_second_capacity_entry_observation_remains_bounded_negative': (2, 'CAPACITY_NEGATIVE_ORIGINAL3'),
    'tests/unit/test_tip063_worktrees.py::test_exact_crash_reopen_recovers_without_duplicate_git_effect[commit:after_effect]': (3, 'WORKTREE_COMMIT_CRASH'),
    'tests/unit/test_tip064_integration.py::test_actual_tls_blocked_native_keeps_heartbeat_status_cancel_and_lost_ack_durable': (4, 'BLOCKED_NATIVE_ENTRY'),
}


def facts(value):
    """Read only plain return/input dictionaries; never render arbitrary values."""
    if type(value) is not dict:
        return {}
    body = value.get('body')
    body = body if type(body) is dict else value
    result = {}
    for key in ('issued_ms', 'expires_ms', 'now_ms', 'seconds'):
        number = body.get(key)
        if type(number) is int and 0 <= number < 10**16:
            result[key] = number
    for key, allowed in (('phase', PHASES), ('state', STATES)):
        field = body.get(key)
        if type(field) is str:
            result[key] = field if field in allowed else 'OTHER'
    reason = body.get('reason_code')
    if type(reason) is str:
        result['code'] = reason if reason in CODES else 'OTHER'
    return result


def error_facts(error):
    # No str/repr, attributes via properties, exception notes or frame locals.
    kind = type(error)
    known = {'WireError', 'JournalError', 'WriterError', 'PrincipalError', 'AssertionError',
             'Failed', 'RuntimeError', 'OSError', 'TimeoutError', 'KeyboardInterrupt', 'BaseExceptionGroup'}
    result = {'exception_type': kind.__name__ if kind.__name__ in known else 'OTHER'}
    code = vars(error).get('code')
    if type(code) is str:
        result['code'] = code if code in CODES else 'OTHER'
    return result


class Observer:
    def __init__(self, limit=192):
        self.limit = max(1, min(limit, 512))
        self.rows, self.errors, self.counters, self.dropped, self.observer_errors = [], [], {}, 0, 0
        self.clock = time.monotonic
        self.origin = self.clock()
        self.lock, self.workers, self.dispatchers = threading.Lock(), [], []

    def record(self, stage, outcome, **data):
        try:
            row = {'stage': stage if stage in STAGES else 'OTHER',
                   'outcome': outcome if outcome in ('ENTRY', 'RETURN', 'ERROR', 'SNAPSHOT') else 'OTHER',
                   'elapsed_ms': max(0, int((self.clock() - self.origin) * 1000))}
            for key in ('issued_ms', 'expires_ms', 'now_ms', 'pending_futures', 'pending_native',
                        'pending_domain', 'worker_count', 'alive_workers', 'seconds'):
                number = data.get(key)
                if type(number) is int and 0 <= number < 10**16:
                    row[key] = number
            for key in ('predicate', 'dispatcher_closed'):
                if type(data.get(key)) is bool:
                    row[key] = data[key]
            for key, allowed in (('phase', PHASES), ('state', STATES), ('code', CODES)):
                if type(data.get(key)) is str:
                    row[key] = data[key] if data[key] in allowed else 'OTHER'
            if type(data.get('exception_type')) is str:
                name = data['exception_type']
                row['exception_type'] = name if name in {'WireError', 'JournalError', 'WriterError',
                    'PrincipalError', 'AssertionError', 'Failed', 'RuntimeError', 'OSError', 'TimeoutError',
                    'KeyboardInterrupt', 'BaseExceptionGroup'} else 'OTHER'
            # Observation itself never waits for another observer owner.
            if not self.lock.acquire(blocking=False):
                self.dropped += 1
                return
            try:
                key = row['stage'] + ':' + row['outcome']
                self.counters[key] = min(self.counters.get(key, 0) + 1, 2147483647)
                if row['outcome'] == 'ERROR' and len(self.errors) < 16:
                    self.errors.append(row)
                if len(self.rows) == self.limit:
                    self.rows.pop(0)
                    self.dropped += 1
                self.rows.append(row)
            finally:
                self.lock.release()
        except BaseException:
            self.observer_errors += 1

    def observe(self, stage, original, *, worker=False, before=None):
        @wraps(original)
        def call(*args, **kwargs):
            if worker:
                current = threading.current_thread()
                if not any(current is prior for prior in self.workers):
                    self.workers.append(current)
            details = {}
            try:
                for value in (*args, kwargs):
                    details.update(facts(value))
                if before is not None:
                    details.update(before(*args, **kwargs))
            except BaseException:
                self.observer_errors += 1
            self.record(stage, 'ENTRY', **details)
            try:
                result = original(*args, **kwargs)
            except BaseException as error:
                try:
                    safe_error = error_facts(error)
                except BaseException:
                    self.observer_errors += 1
                    safe_error = {'exception_type': 'OTHER'}
                self.record(stage, 'ERROR', **safe_error)
                raise
            else:
                self.record(stage, 'RETURN', **facts(result))
                return result
        return call

    def predicate(self, original):
        @wraps(original)
        def read():
            value = original()  # Original predicate exactly once; no extra reads.
            self.record('PREDICATE', 'RETURN', predicate=value if type(value) is bool else None)
            return value
        return read

    def closure(self, dispatcher):
        return {'dispatcher_closed': dispatcher._closed,
                'pending_futures': len(dispatcher._futures),
                'pending_native': len(dispatcher._native_records),
                'pending_domain': len(dispatcher._domain_records),
                'worker_count': len(self.workers),
                'alive_workers': sum(worker.is_alive() for worker in self.workers)}

    def snapshot(self):
        for dispatcher in self.dispatchers:
            try:
                self.record('DISPATCHER_CLOSE', 'SNAPSHOT', **self.closure(dispatcher))
            except BaseException:
                self.observer_errors += 1
        return {'schema': 'tip088.external-observation/1', 'rows': list(self.rows),
                'first_errors': list(self.errors), 'counters': dict(self.counters),
                'rows_dropped': self.dropped, 'observer_errors': self.observer_errors,
                'scope': 'TEMPORARY_FIXTURES_ONLY', 'physical_qualification': 'NOT_RUN'}


def bind(observer, stack, module):
    from vibemql5.fleet.domain import NodeDomainDispatcher
    from vibemql5.fleet.job_journal import NodeJobJournal
    from vibemql5.fleet.native_authorization import NativeAuthorizationVerifier
    from vibemql5.fleet.principals import GatewayPrincipalAuthority
    from vibemql5.fleet.transport import NodeRpcProxy, NodeClient
    from vibemql5.fleet.writers import NodePrincipalRuntime

    def wrapped(owner, name, stage, **options):
        stack.enter_context(patch.object(owner, name, observer.observe(stage, getattr(owner, name), **options)))

    for owner, name, stage in ((NodeDomainDispatcher, 'dispatch_async', 'DISPATCH'),
        (NodeDomainDispatcher, '_native_work', 'NATIVE_WORK'),
        (NodeJobJournal, 'execute', 'EXECUTE'), (NodeJobJournal, 'observe_result', 'RESULT'),
        (NodeJobJournal, '_outcome', 'OUTCOME'), (NodeJobJournal, 'begin_effect', 'AUTHORIZE'),
        (NativeAuthorizationVerifier, 'verify', 'VERIFY'),
        (NodeRpcProxy, 'start_authorize', 'AUTHORIZE'), (NodeRpcProxy, 'writers_authorize', 'AUTHORIZE'),
        (NodeClient, 'start_authorize', 'AUTHORIZE'),
        (NodeClient, 'writers_authorize', 'AUTHORIZE'),
        (GatewayPrincipalAuthority, 'authorize_node', 'GATEWAY_AUTHORIZE'),
        (NodePrincipalRuntime, 'recheck_phase', 'WRITER_RECHECK')):
        wrapped(owner, name, stage, worker=name == '_native_work')

    original_init = NodeDomainDispatcher.__init__
    @wraps(original_init)
    def initialized(dispatcher, *args, **kwargs):
        result = original_init(dispatcher, *args, **kwargs)
        observer.dispatchers.append(dispatcher)
        adapter = dispatcher.native_adapter
        for name, stage in (('reserve', 'CALLBACK_RESERVE'), ('start_reserved', 'CALLBACK_START'),
                            ('effect', 'CALLBACK_EFFECT')):
            if callable(getattr(adapter, name, None)):
                wrapped(adapter, name, stage)
        return result
    stack.enter_context(patch.object(NodeDomainDispatcher, '__init__', initialized))
    wrapped(NodeDomainDispatcher, 'close', 'DISPATCHER_CLOSE', before=observer.closure)
    import sys
    def bind_pump(selected_module):
        original_pump = selected_module.pump
        @wraps(original_pump)
        def pump(agent, predicate, *, seconds=3):
            return observer.observe('PUMP', original_pump)(agent, observer.predicate(predicate), seconds=seconds)
        stack.enter_context(patch.object(selected_module, 'pump', pump))
    for name in ('test_tip064_integration', 'test_tip064_capacity_https'):
        selected_module = sys.modules.get(name)
        if selected_module is not None and hasattr(selected_module, 'pump'):
            bind_pump(selected_module)


def pytest_addoption(parser):
    parser.addoption('--tip088-diag-output', default=None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    output = item.config.getoption('--tip088-diag-output')
    module = item.module
    selected = CASE_IDS.get(item.nodeid) if output else None
    if selected is None:
        yield
        return
    observer = Observer()
    with ExitStack() as stack:
        try:
            bind(observer, stack, module)
        except BaseException:
            pytest.fail('TIP088_DIAGNOSTIC_BINDING_BLOCKED', pytrace=False)
        try:
            yield
        finally:
            payload = observer.snapshot()
            payload.update(case_ordinal=selected[0], case_id=selected[1])
            # A write failure is diagnostic loss, never an altered test result.
            try:
                with Path(output).open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(payload, sort_keys=True) + '\n')
                reporter = item.config.pluginmanager.get_plugin('terminalreporter')
                if reporter is not None:
                    reporter.write_line('TIP088_EXTERNAL_OBSERVATION ' + json.dumps(payload, sort_keys=True))
                    reporter.flush()
            except BaseException:
                pass
