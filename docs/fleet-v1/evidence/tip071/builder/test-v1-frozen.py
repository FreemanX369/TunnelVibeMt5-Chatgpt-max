"""Owned SQLite setup failures close their connection without hiding the cause."""
import sqlite3

import pytest

from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator

SQL = {'wal': 'PRAGMA journal_mode=WAL', 'full': 'PRAGMA synchronous=FULL'}


@pytest.fixture
def coordinator(tmp_path):
    instance = object.__new__(ScopedResourceCoordinator)
    instance.path, instance.profile = tmp_path / 'owned.sqlite', {'lock_wait_ms': 1000}
    return instance


class RecordedConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.statements, self.close_calls, self.setup_error = [], 0, None
        self.setup_fault, self.close_fault = None, None

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)
        try:
            if self.setup_fault is not None and sql == self.setup_fault[0]:
                raise self.setup_fault[1]
            return super().execute(sql, *args, **kwargs)
        except BaseException as error:
            self.setup_error = error
            raise

    def close(self):
        self.close_calls += 1
        if self.close_fault is not None:
            raise self.close_fault
        super().close()


@pytest.fixture
def connections(monkeypatch):
    original = sqlite3.connect
    options, created, calls = {}, [], []

    def connect(*args, **kwargs):
        calls.append((args, kwargs.copy()))
        db = original(*args, **kwargs, factory=RecordedConnection)
        created.append(db)
        db.setup_fault, db.close_fault = options.get('setup_fault'), options.get('close_fault')
        denied = options.get('deny_pragma')
        if denied is not None:
            db.set_authorizer(lambda action, first, *_:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_PRAGMA and first == denied else sqlite3.SQLITE_OK)
        return db

    monkeypatch.setattr(sqlite3, 'connect', connect)
    try:
        yield options, created, calls
    finally:
        # The test owns these connections, including deliberate close failures.
        for db in created:
            sqlite3.Connection.close(db)


def test_success_returns_usable_wal_full_connection(coordinator, connections):
    _, created, calls = connections
    db = coordinator._db()
    assert db is created[0] and db.close_calls == 0
    assert db.statements == [SQL['wal'], SQL['full']]
    assert calls == [((str(coordinator.path),), {'timeout': 1.0, 'isolation_level': None})]
    assert db.execute('PRAGMA journal_mode').fetchone() == ('wal',)
    assert db.execute('PRAGMA synchronous').fetchone() == (2,)
    assert db.execute('SELECT 42').fetchone() == (42,)
    db.close()


def test_real_busy_retained_traceback_holds_a_closed_connection(coordinator, connections):
    _, created, _ = connections
    owner = sqlite3.Connection(coordinator.path, isolation_level=None)
    try:
        owner.execute('CREATE TABLE owned (value INTEGER)')
        owner.execute('INSERT INTO owned VALUES (42)')
        owner.execute('BEGIN')
        assert owner.execute('SELECT value FROM owned').fetchone() == (42,)
        with pytest.raises(sqlite3.OperationalError) as caught:
            coordinator._db()
        error, db = caught.value, created[0]
        assert error is db.setup_error
        assert error.sqlite_errorcode == sqlite3.SQLITE_BUSY and error.sqlite_errorname == 'SQLITE_BUSY'
        frame = error.__traceback__
        while frame and frame.tb_frame.f_code is not ScopedResourceCoordinator._db.__code__:
            frame = frame.tb_next
        assert frame is not None and frame.tb_frame.f_locals['db'] is db
        assert db.close_calls == 1
        with pytest.raises(sqlite3.ProgrammingError):
            db.execute('SELECT 42')
    finally:
        owner.close()
    restored = coordinator._db()
    assert restored.execute('SELECT value FROM owned').fetchone() == (42,)
    restored.close()


@pytest.mark.parametrize('stage', ['wal', 'full'])
def test_each_real_sqlite_pragma_denial_closes_once_and_keeps_identity(coordinator, connections, stage):
    options, created, _ = connections
    options['deny_pragma'] = 'journal_mode' if stage == 'wal' else 'synchronous'
    with pytest.raises(sqlite3.DatabaseError) as caught:
        coordinator._db()
    db = created[0]
    assert caught.value is db.setup_error
    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_AUTH and caught.value.sqlite_errorname == 'SQLITE_AUTH'
    assert db.statements == ([SQL['wal']] if stage == 'wal' else [SQL['wal'], SQL['full']])
    assert db.close_calls == 1
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute('SELECT 42')


@pytest.mark.parametrize('stage', ['wal', 'full'])
@pytest.mark.parametrize('error_type', [RuntimeError, KeyboardInterrupt, SystemExit], ids=['unexpected', 'interrupt', 'exit'])
def test_setup_interruption_closes_once_and_keeps_original_chain(coordinator, connections, stage, error_type):
    options, created, _ = connections
    primary, cause = error_type('owned setup fault'), RuntimeError('owned prior cause')
    primary.__cause__ = cause
    options['setup_fault'] = (SQL[stage], primary)
    with pytest.raises(error_type) as caught:
        coordinator._db()
    db = created[0]
    assert caught.value is primary and primary.__cause__ is cause
    assert db.close_calls == 1
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute('SELECT 42')


@pytest.mark.parametrize('error_type', [RuntimeError, KeyboardInterrupt], ids=['unexpected', 'interrupt'])
def test_connect_failure_retains_original_without_inventing_cleanup(coordinator, monkeypatch, error_type):
    primary, calls = error_type('owned connect fault'), []

    def failed_connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise primary

    monkeypatch.setattr(sqlite3, 'connect', failed_connect)
    with pytest.raises(error_type) as caught:
        coordinator._db()
    assert caught.value is primary
    assert calls == [((str(coordinator.path),), {'timeout': 1.0, 'isolation_level': None})]


@pytest.mark.parametrize('stage', ['wal', 'full'])
@pytest.mark.parametrize('error_type', [RuntimeError, KeyboardInterrupt], ids=['unexpected', 'interrupt'])
def test_close_failure_retains_real_setup_error_as_primary(coordinator, connections, stage, error_type):
    options, created, _ = connections
    cleanup = error_type('owned close fault')
    options.update(deny_pragma='journal_mode' if stage == 'wal' else 'synchronous', close_fault=cleanup)
    with pytest.raises(sqlite3.DatabaseError) as caught:
        coordinator._db()
    db = created[0]
    assert caught.value is db.setup_error
    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_AUTH and caught.value.sqlite_errorname == 'SQLITE_AUTH'
    assert caught.value.__cause__ is cleanup and cleanup.__context__ is caught.value
    assert db.close_calls == 1
