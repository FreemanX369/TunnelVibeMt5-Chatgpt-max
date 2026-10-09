"""Research-observer controls; never part of the fixed production unit tree."""
from contextlib import contextmanager
import ast
import gc
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import weakref

import pytest

import stage_observer
from stage_observer import Observation, ObservedContext, STAGES


def test_instance_routing_exact_arguments_result_and_foreign_objects_threads():
    calls, token, result = [], object(), object()
    class Target:
        def run(self, *args, **kwargs):
            calls.append((self, args, kwargs)); return result
    owned, foreign = Target(), Target()
    observer = Observation(0)
    observer.method(owned, "run", "RESERVE")
    try:
        assert owned.run(token, named=token) is result
        assert foreign.run(token) is result
        thread = threading.Thread(target=lambda: owned.run(token, named=token))
        thread.start(); thread.join(2)
        assert not thread.is_alive()
        assert observer.total == 1 and len(calls) == 3
        assert calls[0][1][0] is calls[0][2]["named"] is token
        assert calls[2][1][0] is calls[2][2]["named"] is token
        assert "run" not in foreign.__dict__
    finally:
        observer.stop()
    assert "run" not in owned.__dict__


@pytest.mark.parametrize("error_type", [RuntimeError, AssertionError, TimeoutError, KeyboardInterrupt, SystemExit])
def test_error_identity_cause_notes_and_traceback_are_original(error_type):
    fault, cause = error_type("PRIVATE_ARGUMENT"), ValueError("PRIVATE_CAUSE")
    fault.add_note("PRIVATE_NOTE")
    def original():
        raise fault from cause
    observer = Observation(0)
    with pytest.raises(BaseException) as captured:
        observer.invoke("RESERVE", original)
    assert captured.value is fault and fault.__cause__ is cause and fault.__notes__ == ["PRIVATE_NOTE"]
    assert "PRIVATE" not in json.dumps(observer.snapshot())
    observer.stop()


@pytest.mark.parametrize("suppress", [False, True])
def test_nested_generator_context_protocol_and_error_identity(suppress):
    seen, value, fault = [], object(), RuntimeError("PRIVATE_ERROR")
    @contextmanager
    def original():
        seen.append("enter")
        try:
            yield value
        except RuntimeError as error:
            assert error is fault
            seen.append("throw")
            if not suppress:
                raise
        finally:
            seen.append("exit")
    observer = Observation(0)
    def call():
        with ObservedContext(observer, "JOURNAL_TX", original()) as yielded:
            assert yielded is value
            with ObservedContext(observer, "SCOPE_TX", original()) as inner:
                assert inner is value
                raise fault
    if suppress:
        call()
        assert seen == ["enter", "enter", "throw", "exit", "exit"]
    else:
        with pytest.raises(RuntimeError) as captured:
            call()
        assert captured.value is fault
        assert seen == ["enter", "enter", "throw", "exit", "throw", "exit"]
    assert all(observer.stats["CONTROL:" + stage]["count"] == 1 for stage in
               ("JOURNAL_TX.ENTER", "JOURNAL_TX.BODY", "JOURNAL_TX.EXIT", "SCOPE_TX.ENTER", "SCOPE_TX.BODY", "SCOPE_TX.EXIT"))
    observer.stop()


@pytest.mark.parametrize("fail_at", ["enter", "body", "exit"])
def test_contextmanager_original_failures_not_reordered(fail_at):
    fault, exit_fault = RuntimeError("PRIVATE_ORIGINAL"), LookupError("PRIVATE_EXIT")
    calls = []
    class Context:
        def __enter__(self):
            calls.append("enter")
            if fail_at == "enter":
                raise fault
            return self
        def __exit__(self, typ, value, tb):
            calls.append((typ, value, tb))
            if fail_at == "exit":
                raise exit_fault
            return False
    observer = Observation(0)
    with pytest.raises(BaseException) as captured:
        with ObservedContext(observer, "SCOPE_TX", Context()):
            raise fault
    assert captured.value is (exit_fault if fail_at == "exit" else fault)
    assert len(calls) == (1 if fail_at == "enter" else 2)
    if fail_at != "enter":
        assert calls[1][0] is RuntimeError and calls[1][1] is fault and calls[1][2] is not None
    observer.stop()


@pytest.mark.parametrize("broken", ["record", "clock", "binder"])
def test_observation_faults_fail_open_without_extra_callback(broken):
    calls, value = [], object()
    observer = Observation(0)
    def fault(*args):
        raise SystemExit("PRIVATE_DIAGNOSTIC")
    if broken == "record":
        observer.record = fault
    if broken == "clock":
        observer.clock = fault
    @contextmanager
    def original():
        calls.append("enter")
        yield value
        calls.append("exit")
    with ObservedContext(observer, "JOURNAL_TX", original(), fault if broken == "binder" else None) as seen:
        assert seen is value
        calls.append("body")
    assert calls == ["enter", "body", "exit"]
    observer.stop()


def test_partial_setter_failure_is_unwound_and_late_calls_are_disabled():
    sentinel, returned = object(), object()
    class Target:
        break_once = False
        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if name == "run" and self.break_once:
                object.__setattr__(self, "break_once", False)
                raise RuntimeError("PRIVATE_INSTALL")
        def run(self, value):
            assert value is sentinel
            return returned
    target, observer = Target(), Observation(0)
    target.break_once = True
    observer.method(target, "run", "RESERVE")
    captured_wrapper = target.run
    assert target.run(sentinel) is returned
    count = observer.total
    observer.stop()
    assert "run" not in target.__dict__
    assert captured_wrapper(sentinel) is returned and observer.total == count
    assert observer.faults == 1


def test_restoration_failure_cannot_mask_callback_result_and_capture_stays_off():
    class Target:
        break_delete = False
        def run(self): return 42
        def __delattr__(self, name):
            if self.break_delete: raise KeyboardInterrupt("PRIVATE_RESTORE")
            object.__delattr__(self, name)
    target, observer = Target(), Observation(0)
    observer.method(target, "run", "RESERVE")
    target.break_delete = True
    observer.stop()
    assert observer.faults == 1 and not observer.enabled
    assert target.run() == 42 and observer.total == 0
    target.break_delete = False
    del target.run


def test_worker_identity_registration_and_unregistered_same_name_thread():
    observer, counts = Observation(0), []
    target = SimpleNamespace(work=lambda: observer.invoke("RESERVE", lambda: None))
    observer.method(target, "work", "WORKER", worker=True)
    owned = threading.Thread(target=target.work, name="same")
    owned.start(); owned.join(2)
    foreign = threading.Thread(target=lambda: counts.append(observer.actor()), name="same")
    foreign.start(); foreign.join(2)
    assert not owned.is_alive() and not foreign.is_alive()
    assert counts == [None] and observer.workers == [owned]
    assert observer.stats["WORKER_1:RESERVE"]["count"] == 1
    assert observer.stats["WORKER_1:WORKER"]["count"] == 1
    observer.stop()


def test_constructor_gating_and_nested_global_seam_no_foreign_capture():
    bound = []
    class Target:
        def __init__(self, marker): self.marker = marker
    observer = Observation(0)
    original = Target.__init__
    observer.constructor(Target, bound.append)
    foreign = Target("PRIVATE_FOREIGN")
    observer.local.build = 1
    owned = Target("PRIVATE_OWNED")
    observer.local.build = 0
    assert bound == [owned] and foreign.marker == "PRIVATE_FOREIGN"
    module = SimpleNamespace(convert=lambda marker: marker)
    observer.method(module, "convert", "CANONICAL", nested=True)
    sentinel = object()
    assert module.convert(sentinel) is sentinel and observer.total == 0
    assert observer.invoke("RESERVE", module.convert, sentinel) is sentinel
    assert observer.stats["CONTROL:CANONICAL"]["count"] == 1
    observer.stop()
    assert Target.__init__ is original


def test_bounded_schema_prefix_tail_and_finite_categories_no_error_retention():
    observer = Observation(0)
    for _ in range(400): observer.invoke("RESERVE", lambda: None)
    class PrivateError(RuntimeError): pass
    fault = PrivateError("PRIVATE_DATA")
    reference = weakref.ref(fault)
    try:
        raise fault
    except PrivateError as error:
        try:
            observer.invoke("RESERVE", lambda: (_ for _ in ()).throw(error))
        except PrivateError:
            pass
    del fault
    gc.collect()
    facts = observer.snapshot()
    assert reference() is None
    assert facts["timeline_total"] == 401 and facts["timeline_dropped"] == 273
    assert len(facts["timeline"]) == 128 and facts["timeline"][-1]["error"] == "OTHER"
    assert all(row["stage"] in STAGES for row in facts["timeline"])
    assert "PRIVATE" not in json.dumps(facts)
    observer.stop()


def test_patching_does_not_override_subsequent_original_cleanup_replacement():
    original = lambda: 1
    changed = lambda: 2
    target, observer = SimpleNamespace(run=original), Observation(0)
    observer.method(target, "run", "RESERVE")
    target.run = changed
    observer.stop()
    assert target.run is changed


def test_context_body_after_stop_is_not_captured_and_exit_delegates_once():
    calls, observer = [], Observation(0)
    @contextmanager
    def original():
        calls.append("enter")
        try: yield
        finally: calls.append("exit")
    with ObservedContext(observer, "SCOPE_TX", original()):
        observer.stop()
    assert calls == ["enter", "exit"]
    assert observer.total == 1


@pytest.mark.parametrize("broken", ["constructor", "service"])
def test_hook_initialization_and_missing_service_are_fail_open(monkeypatch, tmp_path, broken):
    item = SimpleNamespace(nodeid=stage_observer.CASES[0], funcargs={}, module=SimpleNamespace(),
                           config=SimpleNamespace(getoption=lambda name: str(tmp_path)))
    if broken == "constructor":
        def fail(*args): raise SystemExit("PRIVATE_SETUP")
        monkeypatch.setattr(stage_observer, "Observation", fail)
    hook = stage_observer.pytest_runtest_call(item)
    assert next(hook) is None
    with pytest.raises(StopIteration): next(hook)
    if broken == "service":
        facts = json.loads((tmp_path / "case-0.json").read_text())
        assert facts["observation_faults"] == 1 and not facts["capture_enabled"]


def test_inflight_owned_worker_after_stop_keeps_result_without_late_record():
    entered, release = threading.Event(), threading.Event()
    result, returns, observer = object(), [], Observation(0)
    def work():
        entered.set()
        assert release.wait(2)
        return result
    target = SimpleNamespace(work=work)
    observer.method(target, "work", "WORKER", worker=True)
    worker = threading.Thread(target=lambda: returns.append(target.work()))
    worker.start()
    assert entered.wait(2)
    observer.stop()
    release.set(); worker.join(2)
    assert not worker.is_alive() and returns == [result] and observer.total == 0


def test_allowlist_covers_capacity_helper_callers_and_excludes_other_scope_tests():
    original = Path(__file__).resolve().parents[2] / "tests/unit/test_tip064_capacity_https.py"
    tree = ast.parse(original.read_text(encoding="utf-8"))
    helper_callers = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name.startswith("test_") and any(isinstance(call, ast.Call)
                      and isinstance(call.func, ast.Name) and call.func.id == "run_capacity_fixture"
                      for call in ast.walk(node))}
    capacity = [case.split("::")[1].split("[")[0] for case in stage_observer.CASES
                if case.startswith("tests/unit/test_tip064_capacity_https.py::")]
    assert set(capacity) == helper_callers and len(capacity) == 10
    assert len(stage_observer.CASES) == len(set(stage_observer.CASES)) == 12


@pytest.mark.parametrize("name", ["test_scope_observation_actual_guard_contention_keeps_late_owner_and_delegates_once",
                                  "test_scope_observation_excludes_released_failing_context_from_owner"])
def test_unrelated_scope_test_does_not_initialize_plugin(monkeypatch, name):
    constructed = []
    monkeypatch.setattr(stage_observer, "Observation", lambda *args: constructed.append(args))
    item = SimpleNamespace(nodeid="tests/unit/test_tip064_capacity_https.py::" + name,
                           config=SimpleNamespace(getoption=lambda option: "unused"))
    hook = stage_observer.pytest_runtest_call(item)
    assert next(hook) is None
    with pytest.raises(StopIteration): next(hook)
    assert not constructed


def scoped_capture(tmp_path):
    from test_tip056_scoped import profile
    from vibemql5.fleet import scoped_resources
    from vibemql5.core import jobs
    coordinator = scoped_resources.ScopedResourceCoordinator._for_fixture(tmp_path, profile(tmp_path), initialize=True)
    observer = Observation(0)
    observer.exit_profiler.configure(scoped_resources, jobs)
    assert observer.exit_profiler.configuration == 'AVAILABLE'
    observer.bind_coordinator(coordinator)
    return coordinator, observer


def test_exit_profiler_original_connection_cursor_guard_and_no_extra_sql(tmp_path):
    import sqlite3
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    main_snapshot = coordinator.path.read_bytes()
    seen, stage = [], observer.exit_profiler.stage
    def capture(frame, method):
        result = stage(frame, method)
        if result:
            seen.append((result, method.__self__ if hasattr(method, '__self__') else None,
                         frame.f_locals.get('db'), frame.f_locals.get('f')))
        return result
    observer.exit_profiler.stage = capture
    try:
        with observer.exit_profiler.scope():
            with coordinator.transaction() as db:
                assert type(db) is sqlite3.Connection
                identity = db
        assert sys.getprofile() is None
        assert coordinator.path.read_bytes() == main_snapshot
        with sqlite3.connect(coordinator.path.as_uri() + '?mode=ro', uri=True) as snapshot:
            assert snapshot.execute('SELECT schema, profile_sha256 FROM meta').fetchall() == [
                ('fleet.scoped-authority/1', coordinator.profile_sha256)]
            assert snapshot.execute('SELECT COUNT(*) FROM reservations').fetchone() == (0,)
        expected = {'SCOPE_COMMIT', 'SCOPE_CHECKPOINT_EXECUTE', 'SCOPE_CHECKPOINT_FETCH',
                    'SCOPE_DB_CLOSE', 'SCOPE_GUARD_UNLOCK', 'SCOPE_GUARD_FILE_CLOSE', 'SCOPE_EXIT_REMAINDER'}
        assert {key.split(':')[1] for key in observer.stats} >= expected
        for result, owner, original_db, original_file in seen:
            if result in {'SCOPE_COMMIT', 'SCOPE_CHECKPOINT_EXECUTE', 'SCOPE_DB_CLOSE'}:
                assert owner is original_db is identity
            if result == 'SCOPE_CHECKPOINT_FETCH': assert type(owner) is sqlite3.Cursor
            if result == 'SCOPE_GUARD_FILE_CLOSE': assert owner is original_file
        assert observer.faults == 0
        facts = observer.snapshot()['exit_profile']
        assert facts['threads']['CONTROL']['calls'] == 6 and not facts['threads']['CONTROL']['active']
        assert facts['threads']['CONTROL']['unmatched'] == 0 and not facts['not_applicable']
        assert facts['coverage'] == 'COMPLETE'
        # No executable DB/OS operation added by this profiler.
        tree = ast.parse(Path(stage_observer.__file__).read_text())
        implementation = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ExitProfiler')
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr in {'execute', 'fetchone', 'close', 'locking', 'flock', 'open'}
                       for n in ast.walk(implementation))
    finally:
        observer.stop()


def test_exit_profiler_original_body_error_and_c_exception(tmp_path):
    import sqlite3
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    fault, cause = RuntimeError('PRIVATE_FAULT'), ValueError('PRIVATE_CAUSE')
    fault.add_note('PRIVATE_NOTE')
    try:
        with pytest.raises(RuntimeError) as captured:
            with observer.exit_profiler.scope():
                with coordinator.transaction():
                    raise fault from cause
        assert captured.value is fault and fault.__cause__ is cause and fault.__notes__ == ['PRIVATE_NOTE']
        assert observer.stats['CONTROL:SCOPE_ROLLBACK']['count'] == 1
        assert 'CONTROL:SCOPE_COMMIT' not in observer.stats
        with pytest.raises(sqlite3.OperationalError):
            with observer.exit_profiler.scope():
                with coordinator.transaction() as db:
                    db.execute('ROLLBACK')  # Force original COMMIT's genuine C exception.
        assert observer.stats['CONTROL:SCOPE_COMMIT']['errors'] == 1
        assert observer.exit_profiler.states['CONTROL']['exceptions'] == 1
        assert observer.exit_profiler.states['CONTROL']['scopes'] == 2
        assert sys.getprofile() is None and observer.faults == 0
        assert 'PRIVATE' not in json.dumps(observer.snapshot())
    finally:
        observer.stop()


def test_exit_profiler_ignores_foreign_coordinator_frames_and_thread(tmp_path):
    from test_tip056_scoped import profile
    from vibemql5.fleet.scoped_resources import ScopedResourceCoordinator
    coordinator, observer = scoped_capture(tmp_path)
    other = tmp_path / 'other'; other.mkdir()
    foreign = ScopedResourceCoordinator._for_fixture(other, profile(other), initialize=True)
    returns = []
    def unrelated():
        with observer.exit_profiler.scope():
            with coordinator.transaction(): pass
        returns.append(True)
    try:
        with observer.exit_profiler.scope():
            with foreign.transaction(): pass
            # Same C method names at unrelated code sites are ignored.
            import sqlite3
            db = sqlite3.connect(':memory:'); db.execute('CREATE TABLE x(a)'); db.close()
        assert not observer.stats
        thread = threading.Thread(target=unrelated); thread.start(); thread.join(2)
        assert not thread.is_alive() and returns == [True] and not observer.stats
        assert set(observer.exit_profiler.states) == {'CONTROL'}
    finally:
        observer.stop()


def test_exit_profiler_prior_profile_skipped_and_intervening_owner_preserved(tmp_path):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    prior = lambda *args: None
    try:
        sys.setprofile(prior)
        with observer.exit_profiler.scope():
            with coordinator.transaction(): pass
        assert sys.getprofile() is prior
        assert observer.exit_profiler.states['CONTROL']['status'] == 'UNSUPPORTED_EXISTING_PROFILE'
        assert not any(key.split(':')[1] in stage_observer.EXIT_STAGES for key in observer.stats)
        sys.setprofile(None)
        with observer.exit_profiler.scope():
            sys.setprofile(prior)
        assert sys.getprofile() is prior
        assert observer.exit_profiler.states['CONTROL']['status'] == 'REPLACED_BY_OTHER_OWNER'
        assert observer.exit_profiler.states['CONTROL']['skipped_existing'] == 1
    finally:
        sys.setprofile(None); observer.stop()


@pytest.mark.parametrize('mode', ['record', 'partial_install', 'before_install', 'seam'])
def test_exit_profiler_faults_fail_open_and_partial_install_restores(tmp_path, monkeypatch, mode):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    setter, record = sys.setprofile, observer.record
    calls = []
    if mode == 'record':
        def faulty_record(stage, *args, **kwargs):
            if stage in stage_observer.EXIT_STAGES: raise SystemExit('PRIVATE_DIAGNOSTIC')
            return record(stage, *args, **kwargs)
        monkeypatch.setattr(observer, 'record', faulty_record)
    elif mode in {'partial_install', 'before_install'}:
        def partial(callback):
            if mode == 'before_install' and callback is not None:
                raise SystemExit('PRIVATE_INSTALL')
            setter(callback)
            if callback is not None: raise SystemExit('PRIVATE_INSTALL')
        monkeypatch.setattr(sys, 'setprofile', partial)
    else:
        observer.exit_profiler.configuration = 'SOURCE_SEAM_MISMATCH'
    try:
        with observer.exit_profiler.scope():
            with coordinator.transaction() as db:
                calls.append(type(db).__name__)
        assert calls == ['Connection'] and sys.getprofile() is None
        assert observer.exit_profiler.states['CONTROL']['status'] == {
            'record': 'OBSERVATION_FAULT', 'partial_install': 'INSTALL_FAULT',
            'before_install': 'INSTALL_FAULT', 'seam': 'SOURCE_SEAM_MISMATCH'}[mode]
        assert not observer.exit_profiler.states['CONTROL']['coverage_complete']
        assert 'CONTROL:SCOPE_EXIT_REMAINDER' not in observer.stats
        assert 'PRIVATE' not in json.dumps(observer.snapshot())
    finally:
        setter(None); observer.stop()


def test_exit_profiler_exact_owned_worker_disabled_late_cleanup(tmp_path):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    entered, release, restored = threading.Event(), threading.Event(), []
    def work():
        with coordinator.transaction(): pass
        entered.set()
        assert release.wait(2)
        with coordinator.transaction(): pass
        return 'original'
    target = SimpleNamespace(work=work)
    observer.method(target, 'work', 'WORKER', worker=True)
    def run():
        result = target.work(); restored.append((result, sys.getprofile()))
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(2)
        before = observer.total
        assert observer.exit_profiler.states['WORKER_1']['active']
        observer.stop(); release.set(); thread.join(2)
        assert not thread.is_alive() and restored == [('original', None)]
        assert observer.total == before and not observer.exit_profiler.states['WORKER_1']['active']
        assert observer.exit_profiler.states['WORKER_1']['calls'] == 6
    finally:
        release.set(); thread.join(2); observer.stop()


def test_exit_profile_output_and_state_are_bounded_with_overhead_receipt(tmp_path):
    import time
    coordinator, observer = scoped_capture(tmp_path)
    # Original finite transactions before/with observation. Local wall-time only;
    # this does not establish Windows profile overhead or physical performance.
    started = time.perf_counter()
    for _ in range(24):
        with coordinator.transaction(): pass
    baseline = time.perf_counter() - started
    started = time.perf_counter()
    with observer.exit_profiler.scope():
        for _ in range(24):
            with coordinator.transaction(): pass
    observed = time.perf_counter() - started
    facts = observer.snapshot()
    assert len(facts['timeline']) <= 128 and facts['timeline_dropped'] > 0
    assert observer.exit_profiler.states['CONTROL']['calls'] == 24 * 6
    assert observer.exit_profiler.states['CONTROL']['unmatched'] == 0 and observer.faults == 0
    print('EXIT_PROFILE_OVERHEAD ' + json.dumps({'transactions_each': 24, 'baseline_seconds': baseline,
                                              'profiled_seconds': observed, 'platform': 'LOCAL_ONLY'}))
    observer.stop()


def test_exit_profiler_original_fifo_contention_preserves_order_and_budget(tmp_path):
    from test_tip075_metadata_lock_fifo import await_queue, queue_size
    from vibemql5.core import jobs
    coordinator, observer = scoped_capture(tmp_path)
    calls, errors, threads = [], [], []
    def work():
        try:
            observer.register_worker()
            with observer.exit_profiler.scope():
                with coordinator.transaction(): calls.append('waiter')
        except BaseException as error: errors.append(error)
    try:
        with observer.exit_profiler.scope():
            with coordinator.transaction():
                calls.append('owner')
                worker = threading.Thread(target=work); threads.append(worker); worker.start()
                await_queue(coordinator.guard, 2)
                assert queue_size(coordinator.guard) == 2
            worker.join(2)
        assert not worker.is_alive() and not errors and calls == ['owner', 'waiter']
        assert coordinator.profile['lock_wait_ms'] == 1000 and not jobs._FILE_LOCK_QUEUES
        assert all(state['calls'] == 6 and state['unmatched'] == 0 for state in observer.exit_profiler.states.values())
    finally:
        for worker in threads: worker.join(2)
        observer.stop()


@pytest.mark.parametrize('mode', ['source_hash', 'loaded_code'])
@pytest.mark.parametrize('seam', ['transaction', 'guard'])
def test_exit_profiler_rejects_changed_source_or_loaded_generator(tmp_path, monkeypatch, mode, seam):
    from types import FunctionType
    from vibemql5.fleet import scoped_resources
    from vibemql5.core import jobs
    coordinator, observer = scoped_capture(tmp_path)
    module = scoped_resources if seam == 'transaction' else jobs
    if mode == 'source_hash':
        read = Path.read_bytes
        def changed(path):
            original = read(path)
            return original + b'\n' if path == Path(module.__file__) else original
        monkeypatch.setattr(Path, 'read_bytes', changed)
    else:
        owner, name = (scoped_resources.ScopedResourceCoordinator, 'transaction') if seam == 'transaction' else (jobs, '_exclusive_file_lock')
        original = getattr(owner, name).__wrapped__
        changed = FunctionType(original.__code__.replace(co_firstlineno=original.__code__.co_firstlineno + 1),
                               original.__globals__)
        monkeypatch.setattr(owner, name, contextmanager(changed))
    try:
        observer.exit_profiler.configure(scoped_resources, jobs)
        assert observer.exit_profiler.configuration == 'SOURCE_SEAM_MISMATCH'
        assert observer.exit_profiler.transaction_code is None and observer.exit_profiler.guard_code is None
        with observer.exit_profiler.scope():
            with coordinator.transaction(): pass
        state = observer.exit_profiler.states['CONTROL']
        assert state['calls'] == 0 and not state['coverage_complete']
        assert 'CONTROL:SCOPE_EXIT_REMAINDER' not in observer.stats
    finally:
        observer.stop()


@pytest.mark.parametrize('mode', ['unmatched_return', 'unmatched_call', 'pending_cap', 'clock_missing'])
def test_exit_profiler_incomplete_pairs_caps_and_clock_do_not_emit_residual(tmp_path, mode):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    db = object()
    method = SimpleNamespace(__name__='execute', __self__=db)
    class BoundaryFrame:
        f_code = observer.exit_profiler.transaction_code
        f_lineno = 371
        f_locals = {'self': coordinator, 'db': db}
    try:
        with observer.exit_profiler.scope():
            callback = sys.getprofile()
            if mode == 'unmatched_return':
                callback(BoundaryFrame(), 'c_return', method)
            elif mode in {'unmatched_call', 'pending_cap'}:
                def missing_returns():
                    for _ in range(1 if mode == 'unmatched_call' else 65):
                        callback(BoundaryFrame(), 'c_call', method)
                observer.invoke('SCOPE_TX.EXIT', missing_returns)
            else:
                clock = observer.clock
                observer.clock = lambda: None
                frame = BoundaryFrame()
                callback(frame, 'c_call', method); callback(frame, 'c_return', method)
                observer.clock = clock
            if mode != 'unmatched_call':
                with coordinator.transaction(): pass
        state = observer.exit_profiler.states['CONTROL']
        assert sys.getprofile() is None and not state['active'] and not state['coverage_complete']
        assert state['pending_peak'] <= 64
        assert state['unmatched'] == {'unmatched_return': 1, 'unmatched_call': 1, 'pending_cap': 64, 'clock_missing': 0}[mode]
        if mode == 'pending_cap':
            assert state['faults'] == observer.faults == 1 and state['status'] == 'OBSERVATION_FAULT'
            assert state['calls'] == 0 and state['pending_peak'] == 64
        if mode == 'clock_missing': assert state['clock_missing'] == 1
        assert 'CONTROL:SCOPE_EXIT_REMAINDER' not in observer.stats
    finally:
        observer.stop()


def test_exit_profiler_reused_owned_thread_keeps_cumulative_counts_and_transaction_ids(tmp_path):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    ids, returned, original_stage = [], [], observer.exit_profiler.stage
    def stage(frame, method):
        found = original_stage(frame, method)
        if found:
            ids.append(observer.local.exit_track['transaction'])
        return found
    observer.exit_profiler.stage = stage
    def work():
        for _ in range(2):
            with observer.exit_profiler.scope():
                with coordinator.transaction(): pass
            assert sys.getprofile() is None
        returned.append(True)
    worker = threading.Thread(target=lambda: (observer.register_worker(), work()))
    worker.start(); worker.join(2)
    try:
        assert not worker.is_alive() and returned == [True]
        state = observer.exit_profiler.states['WORKER_1']
        assert state['scopes'] == 2 and state['calls'] == 12 and state['unmatched'] == 0
        assert state['coverage_complete'] and not state['active'] and observer.faults == 0
        assert ids == [1] * 12 + [2] * 12
        assert observer.stats['WORKER_1:SCOPE_EXIT_REMAINDER']['count'] == 2
    finally:
        observer.stop()


@pytest.mark.parametrize('replacement', ['other', 'none'])
def test_exit_profiler_intervening_owner_during_exit_prevents_false_residual(tmp_path, replacement):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    other = (lambda *args: None) if replacement == 'other' else None
    original_stage = observer.exit_profiler.stage
    def stage(frame, method):
        found = original_stage(frame, method)
        if found == 'SCOPE_COMMIT': sys.setprofile(other)
        return found
    observer.exit_profiler.stage = stage
    try:
        with observer.exit_profiler.scope():
            with coordinator.transaction(): pass
        assert sys.getprofile() is other
        state = observer.exit_profiler.states['CONTROL']
        assert state['status'] == 'REPLACED_BY_OTHER_OWNER' and not state['coverage_complete']
        assert state['unmatched'] == 1 and not state['active']
        assert 'CONTROL:SCOPE_EXIT_REMAINDER' not in observer.stats
    finally:
        sys.setprofile(None); observer.stop()


def test_exit_profiler_restoration_failure_keeps_original_outcome_and_disabled_callback(tmp_path, monkeypatch):
    import sys
    coordinator, observer = scoped_capture(tmp_path)
    setter, returned = sys.setprofile, []
    def fail_restore(callback):
        if callback is None: raise SystemExit('PRIVATE_RESTORE')
        setter(callback)
    monkeypatch.setattr(sys, 'setprofile', fail_restore)
    try:
        with observer.exit_profiler.scope():
            with coordinator.transaction(): returned.append('original')
        state = observer.exit_profiler.states['CONTROL']
        assert returned == ['original'] and state['status'] == 'RESTORE_FAULT'
        assert state['faults'] == observer.faults == 1 and not state['coverage_complete']
        assert state['active']  # Installed but disabled; removal is not falsely reported.
        before = {key: dict(value) for key, value in observer.stats.items()
                  if key.split(':')[1] in stage_observer.EXIT_STAGES}
        with coordinator.transaction(): pass
        assert {key: dict(value) for key, value in observer.stats.items()
                if key.split(':')[1] in stage_observer.EXIT_STAGES} == before
        assert 'PRIVATE' not in json.dumps(observer.snapshot())
    finally:
        setter(None); observer.stop()
