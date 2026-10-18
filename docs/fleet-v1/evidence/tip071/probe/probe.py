"""Finite owned SQLite/guard controls; exact product source stays unchanged."""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from vibemql5.core.jobs import _exclusive_file_lock
from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator

SOURCE = Path('/workspace/scratch/b4674f0ac496/tip070-v2-builder')
OUT = Path(__file__).resolve().parent
EXPECTED = {
    'app/vibemql5/core/jobs.py': '096d32b968dd54cbaeb5374f17a1855d1fdd523ff54b256a3083d0bae634bcd4',
    'app/vibemql5/fleet/scoped_resources.py': '66b37c4ed06ec896e2c4792cf9d2e72db3a9867eeadcd09cba1e921d04d19f9e',
}
before = {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in EXPECTED}
assert before == EXPECTED
assert Path(sys.modules[ScopedResourceCoordinator.__module__].__file__).resolve() == SOURCE / 'app/vibemql5/fleet/scoped_resources.py'
observations = []


def record(value):
    observations.append(value)
    print(json.dumps(value, sort_keys=True), flush=True)


def descriptors(path):
    assert os.name == 'posix' and Path('/proc/self/fd').is_dir()
    observed = []
    for fd in Path('/proc/self/fd').iterdir():
        try:
            if os.readlink(fd) == str(path):
                observed.append(int(fd.name))
        except FileNotFoundError:
            pass
    return sorted(observed)


with tempfile.TemporaryDirectory(prefix='builder-sqlite-owned-') as temporary:
    root = Path(temporary)
    path = root / 'setup.sqlite'
    coordinator = object.__new__(ScopedResourceCoordinator)
    coordinator.path, coordinator.profile = path, {'lock_wait_ms': 1000}
    owner, leaked = sqlite3.connect(path, isolation_level=None), None
    owner.execute('CREATE TABLE owned (value INTEGER)')
    owner.execute('INSERT INTO owned VALUES (42)')
    owner.execute('BEGIN EXCLUSIVE')
    initial = descriptors(path)
    assert len(initial) == 1
    failure = None
    began = time.monotonic()
    try:
        try:
            unexpected = coordinator._db()
        except sqlite3.OperationalError as original:
            failure = original
        else:
            unexpected.close()
            raise AssertionError('actual exclusive owner did not deny setup')
        assert failure is not None and failure.sqlite_errorcode == sqlite3.SQLITE_BUSY
        # Observe descriptors before reading the traceback-held local connection.
        after_failure = descriptors(path)
        assert len(after_failure) == len(initial) + 1
        record({'case': 'real_busy_setup', 'exception_type': type(failure).__name__,
                'sqlite_errorcode': failure.sqlite_errorcode, 'sqlite_errorname': failure.sqlite_errorname,
                'elapsed_ms': int((time.monotonic() - began) * 1000),
                'configured_lock_wait_ms': 1000, 'db_descriptors_before': len(initial),
                'db_descriptors_after_failure_before_traceback_read': len(after_failure)})
        traceback.print_exception(failure, file=sys.stdout)
        frame = failure.__traceback__
        while frame and frame.tb_frame.f_code is not ScopedResourceCoordinator._db.__code__:
            frame = frame.tb_next
        assert frame is not None
        leaked = frame.tb_frame.f_locals['db']
        assert type(leaked) is sqlite3.Connection
        owner.execute('ROLLBACK')
        assert leaked.execute('SELECT value FROM owned').fetchone() == (42,)
        assert not leaked.in_transaction
        other = sqlite3.connect(path, timeout=1, isolation_level=None)
        try:
            other.execute('BEGIN EXCLUSIVE')
            assert other.execute('SELECT value FROM owned').fetchone() == (42,)
            other.execute('ROLLBACK')
        finally:
            other.close()
        record({'case': 'traceback_retains_open_db', 'same_original_exception_retained': failure.sqlite_errorcode == sqlite3.SQLITE_BUSY,
                'retained_db_select42_succeeded': True, 'retained_db_in_transaction': False,
                'independent_exclusive_transaction_succeeded': True,
                'proven_retention': 'OPEN_SQLITE_CONNECTION_AND_OWNED_DB_FILE_DESCRIPTOR',
                'persistent_sqlite_lock_in_this_control': False})
        leaked.close()
        try:
            leaked.execute('SELECT 42')
        except sqlite3.ProgrammingError:
            pass
        else:
            raise AssertionError('closed connection stayed usable')
        assert descriptors(path) == initial
        record({'case': 'explicit_close_control', 'closed_db_programming_error': True,
                'owned_db_descriptors_restored_to_before_failure': True})
        owner.close()
        assert descriptors(path) == []
        normal = coordinator._db()
        try:
            assert normal.execute('PRAGMA journal_mode').fetchone() == ('wal',)
            assert normal.execute('PRAGMA synchronous').fetchone() == (2,)
            assert normal.execute('SELECT value FROM owned').fetchone() == (42,)
            record({'case': 'normal_return_control', 'actual_sqlite_connection': type(normal) is sqlite3.Connection,
                    'journal_mode': 'wal', 'synchronous': 'FULL', 'select42_succeeded': True})
        finally:
            normal.close()
        assert descriptors(path) == []
    finally:
        if leaked is not None:
            leaked.close()
        owner.close()

    guard = root / 'owned.guard.lock'
    entered, release = threading.Event(), threading.Event()
    worker_errors = []

    def holding_owner():
        try:
            with _exclusive_file_lock(guard, timeout_seconds=1):
                entered.set()
                assert release.wait(2)
        except BaseException as error:
            worker_errors.append(error)

    worker = threading.Thread(target=holding_owner)
    worker.start()
    try:
        assert entered.wait(1)
        try:
            with _exclusive_file_lock(guard, timeout_seconds=.2):
                raise AssertionError('guard acquired during actual owned hold')
        except TimeoutError as guarded:
            assert str(guarded).startswith('JOB_METADATA_LOCK_TIMEOUT:')
            record({'case': 'guard_finite_busy_control', 'timeout_preserved': True,
                    'configured_control_timeout_ms': 200, 'physical_windows_qualification': False})
    finally:
        release.set()
        worker.join(timeout=1)
    assert not worker.is_alive() and not worker_errors
    with _exclusive_file_lock(guard, timeout_seconds=.2):
        record({'case': 'guard_release_control', 'original_guard_reacquired_after_owned_release': True})

after = {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in EXPECTED}
assert after == before
receipt = {'status': 'PROVEN_SETUP_EXCEPTION_RETAINS_OPEN_CONNECTION',
           'source_head': 'ce621625324a3872faee5302ec27c35b684d5217',
           'source_tree': '59a359fd2e953e0d030c8308811187cdfacc1bb0',
           'sqlite_version': sqlite3.sqlite_version, 'python_version': sys.version,
           'original_windows_guard_timeout_cause': 'UNKNOWN', 'live_MCP_outage_cause': 'UNKNOWN',
           'source_modified': False, 'VPS_or_native_effects': False, 'source_hashes_before': before,
           'source_hashes_after': after, 'observations': observations}
with (OUT / 'receipt.json').open('x', encoding='utf-8') as output:
    json.dump(receipt, output, indent=2)
    output.write('\n')
print('FINITE_OWNED_SQLITE_AND_GUARD_CONTROLS_PASS', flush=True)
