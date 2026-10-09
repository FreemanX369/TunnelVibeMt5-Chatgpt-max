"""FIFO admission preserves the existing OS lock protocol and one timeout budget."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from vibemql5.core import jobs


def run_thread(call):
    errors = []
    def target():
        try:
            call()
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, errors


def joined(pair):
    pair[0].join(4)
    assert not pair[0].is_alive(), "owned thread did not finish"
    return pair[1]


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def queue_size(path):
    with jobs._FILE_LOCK_CONDITION:
        return len(jobs._FILE_LOCK_QUEUES.get(key(path), ()))


def await_queue(path, size):
    deadline = time.monotonic() + 2
    while queue_size(path) != size and time.monotonic() < deadline:
        time.sleep(.001)
    assert queue_size(path) == size


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    assert not getattr(jobs, '_FILE_LOCK_QUEUES', {})


def observe_attempt(monkeypatch, observed, thread_name):
    if os.name == 'nt':
        import msvcrt
        original = msvcrt.locking
        def locking(fd, mode, count):
            if mode == msvcrt.LK_NBLCK and threading.current_thread().name == thread_name:
                observed.set()
            return original(fd, mode, count)
        monkeypatch.setattr(msvcrt, 'locking', locking)
    else:
        import fcntl
        original = fcntl.flock
        def flock(fd, mode):
            if mode != fcntl.LOCK_UN and threading.current_thread().name == thread_name:
                observed.set()
            return original(fd, mode)
        monkeypatch.setattr(fcntl, 'flock', flock)
    condition = getattr(jobs, '_FILE_LOCK_CONDITION', None)
    if condition is not None:
        wait = condition.wait
        def waiting(timeout=None):
            if threading.current_thread().name == thread_name:
                observed.set()
            return wait(timeout)
        monkeypatch.setattr(condition, 'wait', waiting)


@pytest.mark.parametrize('trial', range(3))
def test_queued_waiter_precedes_immediate_reacquisition(tmp_path, monkeypatch, trial):
    path = tmp_path / 'guard'
    order, observed = [], threading.Event()
    observe_attempt(monkeypatch, observed, 'fifo-B')
    def waiter():
        threading.current_thread().name = 'fifo-B'
        with jobs._exclusive_file_lock(path, 2):
            order.append('B')
    with jobs._exclusive_file_lock(path):
        worker = run_thread(waiter)
        assert observed.wait(2)
    with jobs._exclusive_file_lock(path, 2):
        order.append('A2')
    assert not joined(worker)
    assert order == ['B', 'A2']


def test_unrelated_paths_run_concurrently(tmp_path):
    entered = threading.Event()
    with jobs._exclusive_file_lock(tmp_path / 'a'):
        def other():
            with jobs._exclusive_file_lock(tmp_path / 'b'):
                entered.set()
        worker = run_thread(other)
        assert entered.wait(1)
    assert not joined(worker)


@pytest.mark.parametrize('position', ['middle', 'last'])
def test_timeout_abandons_only_own_ticket(tmp_path, position):
    path = tmp_path / 'guard'; order = []
    def wait_for(name, timeout):
        with jobs._exclusive_file_lock(path, timeout):
            order.append(name)
    with jobs._exclusive_file_lock(path):
        first = run_thread(lambda: wait_for('first', .08 if position == 'middle' else 2))
        await_queue(path, 2)
        second = run_thread(lambda: wait_for('second', 2 if position == 'middle' else .08))
        await_queue(path, 3)
        expired, survivor = (first, second) if position == 'middle' else (second, first)
        errors = joined(expired)
        assert len(errors) == 1 and isinstance(errors[0], TimeoutError)
        assert str(errors[0]) == f'JOB_METADATA_LOCK_TIMEOUT: {path}'
        assert queue_size(path) == 2
    assert not joined(survivor)
    assert order == (['second'] if position == 'middle' else ['first'])


@pytest.mark.parametrize('error_type', [RuntimeError, KeyboardInterrupt, SystemExit])
def test_wait_exception_identity_and_ticket_cleanup(tmp_path, monkeypatch, error_type):
    path = tmp_path / 'guard'; error = error_type('owned sentinel')
    condition = getattr(jobs, '_FILE_LOCK_CONDITION', threading.Condition())
    def fail(timeout=None):
        raise error
    monkeypatch.setattr(condition, 'wait', fail)
    with jobs._exclusive_file_lock(path):
        def waiter():
            with jobs._exclusive_file_lock(path, .08):
                pytest.fail('unexpected entry')
        worker = run_thread(waiter)
        errors = joined(worker)
        assert errors == [error]
        assert queue_size(path) == 1


class FileProxy:
    def __init__(self, file, stage, error, close_started=None, close_release=None):
        self.file, self.stage, self.error = file, stage, error
        self.close_started, self.close_release = close_started, close_release
    def __getattr__(self, name):
        original = getattr(self.file, name)
        if name == self.stage:
            def fail(*args, **kwargs):
                raise self.error
            return fail
        return original
    def close(self):
        if self.close_started is not None:
            self.close_started.set()
            assert self.close_release.wait(2)
        self.file.close()
        if self.stage == 'close':
            raise self.error


def patch_file(monkeypatch, path, stage, error, **kwargs):
    original = Path.open
    def opening(self, *args, **kw):
        file = original(self, *args, **kw)
        if self == path:
            return FileProxy(file, stage, error, **kwargs)
        return file
    monkeypatch.setattr(Path, 'open', opening)


def patch_os_error(monkeypatch, stage, error):
    if os.name == 'nt':
        import msvcrt
        original = msvcrt.locking
        def locking(fd, mode, count):
            if (mode == msvcrt.LK_UNLCK) == (stage == 'unlock'):
                raise error
            return original(fd, mode, count)
        monkeypatch.setattr(msvcrt, 'locking', locking)
    else:
        import fcntl
        original = fcntl.flock
        def flock(fd, mode):
            if (mode == fcntl.LOCK_UN) == (stage == 'unlock'):
                raise error
            return original(fd, mode)
        monkeypatch.setattr(fcntl, 'flock', flock)


@pytest.mark.parametrize('stage', ['mkdir', 'open', 'seek', 'write', 'flush', 'acquire', 'unlock', 'close'])
def test_setup_and_os_errors_release_ticket_with_identity(tmp_path, monkeypatch, stage):
    path = tmp_path / 'guard'; error = RuntimeError(stage)
    with monkeypatch.context() as patch:
        if stage in ('mkdir', 'open'):
            original = getattr(Path, stage)
            def fail(self, *args, **kwargs):
                if self == (path.parent if stage == 'mkdir' else path):
                    raise error
                return original(self, *args, **kwargs)
            patch.setattr(Path, stage, fail)
        elif stage in ('acquire', 'unlock'):
            patch_os_error(patch, stage, error)
        else:
            patch_file(patch, path, stage, error)
        with pytest.raises(RuntimeError) as caught:
            with jobs._exclusive_file_lock(path):
                pass
        assert caught.value is error
        assert not jobs._FILE_LOCK_QUEUES
    with jobs._exclusive_file_lock(path):
        pass


@pytest.mark.parametrize('cleanup', ['none', 'unlock', 'close'])
def test_body_and_cleanup_error_precedence(tmp_path, monkeypatch, cleanup):
    path = tmp_path / 'guard'; body = ValueError('body'); last = RuntimeError(cleanup)
    if cleanup == 'unlock':
        patch_os_error(monkeypatch, 'unlock', last)
    elif cleanup == 'close':
        patch_file(monkeypatch, path, 'close', last)
    with pytest.raises((ValueError, RuntimeError)) as caught:
        with jobs._exclusive_file_lock(path):
            raise body
    assert caught.value is (body if cleanup == 'none' else last)
    assert not jobs._FILE_LOCK_QUEUES


def test_close_overrides_unlock_error_as_before(tmp_path, monkeypatch):
    path = tmp_path / 'guard'; unlock = RuntimeError('unlock'); close = ValueError('close')
    patch_os_error(monkeypatch, 'unlock', unlock)
    patch_file(monkeypatch, path, 'close', close)
    with pytest.raises(ValueError) as caught:
        with jobs._exclusive_file_lock(path):
            pass
    assert caught.value is close and caught.value.__context__ is unlock


def test_zero_timeout_still_attempts_uncontended_os_lock(tmp_path):
    with jobs._exclusive_file_lock(tmp_path / 'guard', 0):
        pass


def test_relative_alias_shares_turn_and_preserves_supplied_error_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = Path('guard')
    with jobs._exclusive_file_lock(tmp_path / '.' / 'guard'):
        def waiter():
            with jobs._exclusive_file_lock(relative, .04):
                pytest.fail('alias admitted concurrently')
        errors = joined(run_thread(waiter))
        assert len(errors) == 1
        assert str(errors[0]) == 'JOB_METADATA_LOCK_TIMEOUT: guard'
        assert queue_size(relative) == 1


def test_turn_retained_through_file_close(tmp_path, monkeypatch):
    path = tmp_path / 'guard'; close_started = threading.Event(); release = threading.Event()
    entered = threading.Event()
    patch_file(monkeypatch, path, None, None, close_started=close_started, close_release=release)
    def owner():
        with jobs._exclusive_file_lock(path):
            pass
    first = run_thread(owner)
    assert close_started.wait(2)
    def waiter():
        with jobs._exclusive_file_lock(path):
            entered.set()
    second = run_thread(waiter)
    try:
        assert not entered.wait(.06), 'ticket released before original file.close completed'
    finally:
        release.set()
    assert not joined(first)
    assert not joined(second)
    assert entered.is_set()


def test_nonreentrant_and_no_historical_registry_growth(tmp_path):
    path = tmp_path / 'same'
    with jobs._exclusive_file_lock(path):
        with pytest.raises(TimeoutError):
            with jobs._exclusive_file_lock(path, .02):
                pytest.fail('recursive admission')
    for index in range(30):
        with jobs._exclusive_file_lock(tmp_path / str(index)):
            pass
        assert not jobs._FILE_LOCK_QUEUES


CHILD = r'''
import os, pathlib, sys, time
path, ready, release = map(pathlib.Path, sys.argv[1:])
with path.open('a+b') as f:
    f.write(b'\0'); f.flush(); f.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    ready.write_text('ready')
    deadline = time.monotonic() + 6
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(.005)
    if os.name == 'nt':
        f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
'''


def test_local_wait_and_real_external_os_deny_share_one_deadline(tmp_path):
    path = tmp_path / 'guard'; ready = tmp_path / 'ready'; release = tmp_path / 'release'
    child = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', CHILD, str(path), str(ready), str(release)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    worker = None
    try:
        deadline = time.monotonic() + 3
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.005)
        assert ready.exists()
        elapsed = []
        def waiter():
            start = time.monotonic()
            try:
                with jobs._exclusive_file_lock(path, 1):
                    pytest.fail('external OS owner bypassed')
            finally:
                elapsed.append(time.monotonic() - start)
        # Hold only local admission while a real isolated child owns the OS lock.
        with jobs._local_file_lock_turn(path, time.monotonic() + 3):
            worker = run_thread(waiter)
            await_queue(path, 2)
            time.sleep(.6)
        errors = joined(worker)
        assert len(errors) == 1 and isinstance(errors[0], TimeoutError)
        assert .95 <= elapsed[0] < 1.4, elapsed
        release.write_text('release')
        stdout, stderr = child.communicate(timeout=3)
        assert child.returncode == 0, (stdout, stderr)
        with jobs._exclusive_file_lock(path, .2):
            pass
    finally:
        release.write_text('release')
        if child.poll() is None:
            child.communicate(timeout=7)
        if worker is not None:
            joined(worker)
        for owned in (path, ready, release):
            owned.unlink(missing_ok=True)
    assert child.poll() == 0
    assert not any(owned.exists() for owned in (path, ready, release))
