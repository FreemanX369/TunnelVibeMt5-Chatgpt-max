"""Finite instance-owned facts from the long fixture's original native calls."""
from collections import deque
import json
import threading
import time


class LongFixtureNativeObservations:
    METHODS = (('reserve', 'RESERVE'), ('start_reserved', 'START_RESERVED'),
        ('_admit', 'ADMIT'), ('_load_job', 'LOAD_JOB'),
        ('_synthetic_effect', 'SYNTHETIC_EFFECT'), ('_fixture_callback', 'FIXTURE_CALLBACK'))
    STAGES = frozenset(stage for _, stage in METHODS) | {'EXECUTE'}
    TYPES = frozenset(('RuntimeError', 'AssertionError', 'TimeoutError', 'JournalError',
        'WireError', 'NativeRouteError', 'FleetProjectError', 'OwnershipError',
        'ConcurrencyError', 'KeyboardInterrupt', 'SystemExit', 'Failed'))
    CODES = frozenset(('NATIVE_RECOVERY_REQUIRED', 'NATIVE_LEASE_UNAVAILABLE',
        'NATIVE_AUTHORIZATION_EXPIRED', 'NATIVE_AUTHORIZATION_MISMATCH',
        'NATIVE_FENCE_MISMATCH', 'NATIVE_JOB_MISMATCH', 'NATIVE_JOURNAL_INVALID',
        'NATIVE_OPERATION_CONFLICT', 'NATIVE_QUALIFICATION_UNAVAILABLE',
        'EXECUTION_OUTCOME_UNKNOWN', 'HTTPS_UNAVAILABLE'))
    STATES = frozenset(('DELIVERED', 'RESERVED', 'STARTING', 'RUNNING', 'SUCCEEDED',
        'FAILED', 'UNKNOWN', 'RECOVERY_REQUIRED', 'RESULT_PENDING'))

    def __init__(self):
        self.rows, self.error_rows = deque(maxlen=32), deque(maxlen=32)
        self.errors, self.originals, self.observation_errors = [], [], []
        self.counts, self.total, self.error_total, self.errors_dropped = {}, 0, 0, 0
        self.lock = threading.Lock()

    def observe(self, callback, *args):
        try: return callback(*args)
        except BaseException as error:
            with self.lock:
                if len(self.observation_errors) < 32 and not any(error is prior for prior in self.observation_errors):
                    self.observation_errors.append(error)

    def error_index(self, error):
        for index, prior in enumerate(self.errors):
            if error is prior: return index
        if len(self.errors) == 32:
            self.errors_dropped += 1
            return None
        self.errors.append(error)
        return len(self.errors)-1

    def record(self, stage, outcome, began, error=None, result=None):
        if type(stage) is not str or stage not in self.STAGES or type(outcome) is not str or outcome not in {'RETURNED', 'ERROR'}: return
        row = {'stage': stage, 'outcome': outcome, 'elapsed_ms': max(0, int((time.monotonic()-began)*1000))}
        with self.lock:
            counts = self.counts.setdefault(stage, {'calls': 0, 'returns': 0, 'errors': 0})
            counts['calls'] += 1
            counts['returns' if outcome == 'RETURNED' else 'errors'] += 1
            if stage == 'EXECUTE' and type(result) is dict and type(result.get('state')) is str and result['state'] in self.STATES:
                row['native_state'] = result['state']
            current, seen = error, []
            for depth in range(4):
                if current is None or any(current is prior for prior in seen): break
                seen.append(current)
                name = type(current).__name__
                safe = {'stage': stage, 'depth': depth,
                    'error_type': name if name in self.TYPES else 'OTHER',
                    'error_index': self.error_index(current)}
                code = getattr(current, 'code', None)
                if type(code) is str and code in self.CODES: safe['code'] = code
                self.error_total += 1; self.error_rows.append(safe)
                if depth == 0: row.update({key:value for key,value in safe.items() if key not in {'stage','depth'}})
                current = current.__cause__ if current.__cause__ is not None else current.__context__
            self.total += 1; self.rows.append(row)

    def call(self, stage, callback, *args, **kwargs):
        began = time.monotonic()
        try:
            result = callback(*args, **kwargs)
        except BaseException as error:
            self.observe(self.record, stage, 'ERROR', began, error)
            raise
        self.observe(self.record, stage, 'RETURNED', began, None, result)
        return result

    def install(self, owner, name, stage):
        original, had, prior = getattr(owner, name), name in owner.__dict__, owner.__dict__.get(name)
        def observed(*args, **kwargs): return self.call(stage, original, *args, **kwargs)
        self.originals.append((owner, name, had, prior))
        setattr(owner, name, observed)

    def bind(self, dispatcher):
        self.install(dispatcher.native, 'execute', 'EXECUTE')
        for name, stage in self.METHODS: self.install(dispatcher.native_adapter, name, stage)

    def restore(self):
        failures = []
        for owner, name, had, prior in self.originals:
            try:
                if had: setattr(owner, name, prior)
                else: delattr(owner, name)
            except BaseException as error: failures.append(error)
        self.originals.clear()
        if len(failures) == 1: raise failures[0]
        if failures: raise BaseExceptionGroup('native fixture observation restoration failed', failures)

    def snapshot(self):
        with self.lock:
            return {'rows': list(self.rows), 'row_total': self.total, 'row_limit': 32,
                'rows_dropped': max(0,self.total-32), 'error_rows': list(self.error_rows),
                'error_row_total': self.error_total, 'error_row_limit': 32,
                'error_rows_dropped': max(0,self.error_total-32),
                'error_identity_count': len(self.errors), 'error_identity_limit': 32,
                'error_identities_dropped': self.errors_dropped,
                'delegate_counts': {stage:dict(counts) for stage,counts in self.counts.items()}}

    def publish(self):
        print('LONG_NATIVE_FIXTURE ' + json.dumps(self.snapshot(), sort_keys=True), flush=True)
