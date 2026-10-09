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


def test_transaction_same_identity_intervals_six_boundaries_and_remainder(tmp_path):
    coordinator, observer = scoped_capture(tmp_path)
    try:
        with observer.exit_profiler.scope():
            for _ in range(2):
                with coordinator.transaction(): pass
        result = observer.snapshot()
        actor = result['transactions']['actors']['CONTROL']
        assert actor['total'] == actor['retained'] == 2 and actor['dropped'] == 0
        assert actor['incomplete_total'] == 0
        for serial, row in enumerate(actor['records'], 1):
            assert row['case'] == 0 and row['actor'] == 'CONTROL' and row['transaction'] == serial and row['coordinator'] == 1
            assert set(row['intervals']) == {'ENTER', 'BODY', 'EXIT'}
            assert row['executed_boundaries'] == 6 and row['stage_coverage'] == 'EXECUTED'
            assert [item['stage'] for item in row['boundaries']] == [
                'SCOPE_COMMIT', 'SCOPE_CHECKPOINT_EXECUTE', 'SCOPE_CHECKPOINT_FETCH',
                'SCOPE_DB_CLOSE', 'SCOPE_GUARD_UNLOCK', 'SCOPE_GUARD_FILE_CLOSE']
            exit_interval = row['intervals']['EXIT']
            for item in row['boundaries']:
                assert item['identity'] == 'EXACT_ORIGINAL_TRANSACTION'
                assert exit_interval['start_seconds'] <= item['start_seconds'] <= item['end_seconds'] <= exit_interval['end_seconds']
            assert row['exit_remainder_seconds'] >= 0
            assert abs(row['exit_seconds'] - row['exit_remainder_seconds'] - sum(item['duration_seconds'] for item in row['boundaries'])) < 1e-8
            assert not any(name.startswith('_') for name in row)
        assert result['clocks']['transaction_pump']['domain'] == 'time.monotonic'
        assert result['clocks']['original_fixture']['thread_labels_are_actor_ids'] is False
        assert result['exit_profile']['stage_coverage'] == 'EXECUTED'
    finally:
        observer.stop()


def test_transaction_retention_first_latest_largest_deduplicated_and_dropped():
    retention = stage_observer.TransactionRetention()
    for number in range(1, 101):
        retention.add('CONTROL', {'transaction': number, 'exit_seconds': 1 if 30 <= number <= 45 else .01,
                                  'incomplete': number == 50})
    actor = retention.snapshot()['actors']['CONTROL']
    expected = set(range(1, 9)) | set(range(93, 101)) | set(range(30, 46))
    assert {row['transaction'] for row in actor['records']} == expected
    assert actor['total'] == 100 and actor['retained'] == 32 and actor['dropped'] == 68
    assert actor['incomplete_total'] == 1 and actor['coverage'] == 'SAMPLED'
    small = stage_observer.TransactionRetention()
    for number in range(1, 9): small.add('WORKER_1', {'transaction': number, 'exit_seconds': None, 'incomplete': True})
    facts = small.snapshot()['actors']['WORKER_1']
    assert facts['retained'] == 8 and facts['dropped'] == 0 and facts['incomplete_total'] == 8


@pytest.mark.parametrize('mode', ['missing_clock', 'unavailable_profile', 'original_error'])
def test_transaction_clock_unavailable_and_original_error_are_explicit(tmp_path, mode):
    coordinator, observer = scoped_capture(tmp_path)
    fault = RuntimeError('PRIVATE_BODY')
    if mode == 'missing_clock': observer.monotonic_now = lambda: None
    if mode == 'unavailable_profile': observer.exit_profiler.configuration = 'SOURCE_SEAM_MISMATCH'
    try:
        def original():
            with observer.exit_profiler.scope():
                with coordinator.transaction():
                    if mode == 'original_error': raise fault
        if mode == 'original_error':
            with pytest.raises(RuntimeError) as caught: original()
            assert caught.value is fault
        else: original()
        row = observer.snapshot()['transactions']['actors']['CONTROL']['records'][0]
        if mode == 'original_error':
            assert row['body_error'] == 'RuntimeError' and row['route'] == 'ORIGINAL_ERROR_PATH'
            assert row['intervals']['EXIT']['error'] == 'NONE'
            assert [item['stage'] for item in row['boundaries']] == [
                'SCOPE_ROLLBACK', 'SCOPE_DB_CLOSE', 'SCOPE_GUARD_UNLOCK', 'SCOPE_GUARD_FILE_CLOSE']
            assert not row['incomplete']
        else:
            assert row['incomplete'] and row['exit_remainder_seconds'] is None
        if mode == 'unavailable_profile': assert row['stage_coverage'] == 'UNEXECUTED'
        assert 'PRIVATE' not in json.dumps(observer.snapshot())
    finally:
        observer.stop()


def test_transaction_boundary_rejects_different_cursor_connection_and_guard_file(tmp_path):
    import sqlite3
    coordinator, observer = scoped_capture(tmp_path)
    try:
        with sqlite3.connect(':memory:') as owned, sqlite3.connect(':memory:') as foreign:
            row = observer.transaction_begin(coordinator); row['_db'] = owned
            cursor = foreign.cursor()
            frame = SimpleNamespace(f_code=observer.exit_profiler.transaction_code, f_locals={'self': coordinator, 'db': owned})
            observer.exit_profiler.boundary(frame, cursor.fetchone, 'SCOPE_CHECKPOINT_FETCH', 1., 2., 'c_return', row)
            assert row['incomplete'] and not row['boundaries']
            frame = SimpleNamespace(f_code=observer.exit_profiler.guard_code, f_locals={'path': coordinator.guard, 'f': object()})
            row['_file'] = object()
            observer.exit_profiler.boundary(frame, SimpleNamespace(__self__=frame.f_locals['f']), 'SCOPE_GUARD_FILE_CLOSE', 1., 2., 'c_return', row)
            assert not row['boundaries']
    finally:
        observer.stop()


def pump_control(observer, *, pending=False):
    """Execute the verified original nested predicate codes on inert control data."""
    from types import FunctionType
    import test_tip064_capacity_https as capacity
    observer.pump.configure(capacity)
    assert observer.pump.configuration == 'AVAILABLE'
    def cell(value): return (lambda: value).__closure__[0]
    def function(name, values):
        code = observer.pump.codes['run_capacity_fixture.<locals>.' + name]
        return FunctionType(code, capacity.__dict__, closure=tuple(cell(values[key]) for key in code.co_freevars))
    callback = function('raise_callback_failure', {'callback_failures': []})
    completed = function('completed', {'latest': [], 'launched': [], 'third': {'global_job_id': 'CONTROL_ONLY'},
        'summary': lambda row: row, 'facade': SimpleNamespace(get_job=lambda key: {'state': 'SUCCEEDED'}),
        'dispatcher': SimpleNamespace(has_pending_work=lambda: pending)})
    checked = function('checked', {'raise_callback_failure': callback})
    return capacity, completed, checked, callback


@pytest.mark.parametrize('wrong', ['none', 'caller_code', 'caller_line', 'closure', 'agent', 'seconds'])
def test_final_pump_recognition_requires_exact_original_codes_frame_and_closure(wrong):
    observer = Observation(5)
    capacity, completed, checked, callback = pump_control(observer)
    agent, foreign = object(), object()
    predicate = checked(completed)
    frame = SimpleNamespace(f_code=observer.pump.codes['helper'], f_lineno=382,
                            f_locals={'agent': agent, 'completed': completed, 'checked': checked, 'raise_callback_failure': callback})
    if wrong == 'caller_code': frame.f_code = checked.__code__
    if wrong == 'caller_line': frame.f_lineno = 347
    if wrong == 'closure': predicate = checked(lambda: True)
    assert observer.pump.recognize(frame, foreign if wrong == 'agent' else agent, predicate,
                                   3 if wrong == 'seconds' else 10) is (wrong == 'none')
    assert observer.pump.snapshot()['recognition'] == 'UNAVAILABLE'
    observer.stop()


@pytest.mark.parametrize('mode', ['return', 'exception', 'deadline_failure'])
def test_original_pump_deadline_outcome_identity_and_profile_return_not_success(tmp_path, monkeypatch, mode):
    import sys
    from vibemql5.fleet import scoped_resources
    from vibemql5.core import jobs
    observer = Observation(5)
    capacity, completed, checked, callback = pump_control(observer, pending=mode == 'deadline_failure')
    observer.exit_profiler.configure(scoped_resources, jobs)
    fault, cause = RuntimeError('PRIVATE_ORIGINAL'), ValueError('PRIVATE_CAUSE')
    fault.add_note('PRIVATE_NOTE')
    calls = []
    class Agent:
        def step(self):
            calls.append('step')
            if mode == 'exception': raise fault from cause
    agent = Agent()
    observer.method(agent, 'step', 'CONTROL_STEP')
    # Frame recognition is tested above and on the separate real case5 smoke.
    monkeypatch.setattr(observer.pump, 'recognize', lambda *args: True)
    wrapped = observer.pump.wrapper(observer.pump.original)
    try:
        with observer.exit_profiler.scope():
            if mode == 'return': assert wrapped(agent, checked(completed), seconds=10) is None
            else:
                with pytest.raises(BaseException) as caught: wrapped(agent, checked(completed), seconds=10)
                if mode == 'exception':
                    assert caught.value is fault and fault.__cause__ is cause and fault.__notes__ == ['PRIVATE_NOTE']
                    assert any(frame.name == 'pump' for frame in __import__('traceback').extract_tb(fault.__traceback__))
        facts = observer.pump.snapshot()
        assert sys.getprofile() is None and facts['calls'] == 1 and facts['coverage'] == 'COMPLETE'
        assert facts['original_deadline_absolute_monotonic_seconds'] is not None and not facts['deadline_changed']
        assert facts['phase'] == ('AFTER_ORIGINAL_PUMP_RETURN' if mode == 'return' else 'AFTER_ORIGINAL_PUMP_FAILURE')
        assert any(row['stage'] == 'PROFILE_RETURN_UNCLASSIFIED' for row in facts['markers'])
        assert facts['failure_branch_439'] is (mode == 'deadline_failure')
        assert facts['observed_predicate_true'] is (mode == 'return')
        assert facts['pytest_call_outcome'] == 'NOT_OBSERVED'
        assert 'PRIVATE' not in json.dumps(observer.snapshot())
        assert len(calls) == 1 if mode != 'deadline_failure' else len(calls) > 1
        if mode == 'deadline_failure': assert facts['marker_dropped'] > 0 and len(facts['markers']) <= 64
    finally:
        observer.stop()
    assert 'step' not in agent.__dict__ and observer.pump.current is None


@pytest.mark.parametrize('seam', ['helper', 'pump'])
def test_final_pump_seam_mismatch_and_missing_clock_are_unavailable(monkeypatch, seam):
    import test_tip064_capacity_https as capacity
    observer = Observation(5)
    name = 'run_capacity_fixture' if seam == 'helper' else 'pump'
    original = getattr(capacity, name)
    monkeypatch.setattr(capacity, name, lambda *args, **kwargs: None)
    observer.safe(observer.pump.configure, capacity)
    assert observer.pump.configuration == 'SOURCE_SEAM_MISMATCH'
    assert observer.pump.snapshot()['coverage'] == 'INCOMPLETE'
    monkeypatch.setattr(capacity, name, original)
    observer.pump.configure(capacity)
    observer.monotonic_now = lambda: None
    observer.pump.mark('OBSERVED_ENTRY')
    assert observer.pump.clock_missing == 1 and observer.pump.snapshot()['coverage'] == 'INCOMPLETE'
    assert observer.interval(2., 1.)['duration_seconds'] is None
    observer.stop()


@pytest.mark.parametrize('deadline', [1, True, float('nan'), float('inf'), None])
def test_final_pump_deadline_requires_original_finite_float(deadline):
    observer = Observation(5)
    _, completed, checked, _ = pump_control(observer)
    predicate, agent = checked(completed), object()
    frame = SimpleNamespace(f_code=observer.pump.codes['pump'], f_lineno=435,
                            f_locals={'deadline': deadline, 'agent': agent, 'predicate': predicate})
    observer.pump.current = {'agent': agent, 'predicate': predicate, 'completed': completed, 'frame': frame,
                             'predicate_frame': None, 'predicate_start': None}
    observer.pump.event(frame, 'c_call', observer.pump.monotonic)
    assert observer.pump.deadline is None and observer.pump.clock_missing == 1
    assert observer.pump.snapshot()['coverage'] == 'INCOMPLETE'
    observer.pump.current = None
    observer.stop()


@pytest.mark.parametrize('exception', [False, True])
def test_pump_introspection_fault_delegates_original_once_and_preserves_exception(monkeypatch, exception):
    import sys
    observer = Observation(5)
    calls, fault = [], RuntimeError('PRIVATE_ORIGINAL')
    fault.add_note('PRIVATE_NOTE')
    def original(*args, **kwargs):
        calls.append((args, kwargs))
        if exception: raise fault
        return 42
    def unavailable(*args): raise RuntimeError('PRIVATE_AUDIT_DENIAL')
    wrapped = observer.pump.wrapper(original)
    monkeypatch.setattr(sys, '_getframe', unavailable)
    token = object()
    if exception:
        with pytest.raises(RuntimeError) as caught: wrapped(token, token, seconds=10)
        assert caught.value is fault and fault.__notes__ == ['PRIVATE_NOTE']
    else: assert wrapped(token, token, seconds=10) == 42
    assert calls == [((token, token), {'seconds': 10})]
    assert observer.faults == 1 and observer.pump.calls == 0
    assert observer.pump.snapshot()['recognition'] == 'UNAVAILABLE'
    assert 'PRIVATE' not in json.dumps(observer.snapshot())
    observer.stop()


@pytest.mark.parametrize('mode', ['source_hash', 'loaded_code'])
@pytest.mark.parametrize('seam', ['helper', 'pump'])
def test_pump_fixed_source_and_loaded_codes_reject_modification(monkeypatch, mode, seam):
    from types import FunctionType
    import test_tip064_capacity_https as capacity
    observer = Observation(5)
    name = 'run_capacity_fixture' if seam == 'helper' else 'pump'
    original = getattr(capacity, name)
    if mode == 'source_hash':
        read = Path.read_bytes
        def changed(path):
            data = read(path)
            return data + b'\n' if path == Path(original.__code__.co_filename) else data
        monkeypatch.setattr(Path, 'read_bytes', changed)
    else:
        changed = FunctionType(original.__code__.replace(co_firstlineno=original.__code__.co_firstlineno + 1), original.__globals__)
        monkeypatch.setattr(capacity, name, changed)
    observer.pump.configure(capacity)
    assert observer.pump.configuration == 'SOURCE_SEAM_MISMATCH'
    assert observer.pump.original is None and observer.pump.snapshot()['recognition'] == 'UNAVAILABLE'
    observer.stop()


@pytest.mark.parametrize('foreign', ['self', 'code'])
def test_pump_failure_branch_requires_original_fail_callable_identity(foreign):
    observer = Observation(5)
    _, completed, checked, _ = pump_control(observer)
    pump_frame = SimpleNamespace(f_code=observer.pump.codes['pump'], f_lineno=439, f_locals={})
    observer.pump.current = {'agent': object(), 'predicate': checked(completed), 'completed': completed,
                             'frame': pump_frame, 'predicate_frame': None, 'predicate_start': None}
    child = SimpleNamespace(f_code=observer.pump.fail_code, f_back=pump_frame, f_locals={'self': observer.pump.fail_owner})
    if foreign == 'self': child.f_locals['self'] = object()
    else: child.f_code = (lambda: None).__code__
    observer.pump.event(child, 'call', None)
    assert not observer.pump.failure_branch
    child.f_code, child.f_locals['self'] = observer.pump.fail_code, observer.pump.fail_owner
    observer.pump.event(child, 'call', None)
    assert observer.pump.failure_branch and observer.pump.total == 1
    observer.pump.current = None
    observer.stop()


def test_pump_marker_fault_preserves_original_exception_notes_traceback_and_restores(monkeypatch):
    import sys
    from vibemql5.fleet import scoped_resources
    from vibemql5.core import jobs
    observer = Observation(5)
    _, completed, checked, _ = pump_control(observer)
    observer.exit_profiler.configure(scoped_resources, jobs)
    fault, cause = RuntimeError('PRIVATE_ERROR'), ValueError('PRIVATE_CAUSE')
    fault.add_note('PRIVATE_NOTE')
    calls = []
    class Agent:
        def step(self):
            calls.append('step')
            raise fault from cause
    agent = Agent()
    observer.method(agent, 'step', 'CONTROL_STEP')
    monkeypatch.setattr(observer.pump, 'recognize', lambda *args: True)
    def broken(*args, **kwargs): raise SystemExit('PRIVATE_MARKER')
    monkeypatch.setattr(observer.pump, 'mark', broken)
    wrapped = observer.pump.wrapper(observer.pump.original)
    try:
        with observer.exit_profiler.scope():
            with pytest.raises(RuntimeError) as caught: wrapped(agent, checked(completed), seconds=10)
        assert caught.value is fault and fault.__cause__ is cause and fault.__notes__ == ['PRIVATE_NOTE']
        frames = __import__('traceback').extract_tb(fault.__traceback__)
        assert any(frame.name == 'pump' and frame.lineno == 436 for frame in frames)
        assert calls == ['step'] and sys.getprofile() is None
        assert observer.faults > 0 and observer.pump.snapshot()['coverage'] == 'INCOMPLETE'
        assert 'PRIVATE' not in json.dumps(observer.snapshot())
    finally:
        observer.stop()
    assert observer.pump.current is None and 'step' not in agent.__dict__


def test_cached_original_transaction_is_explicitly_unattributed_not_complete(tmp_path):
    coordinator, observer = scoped_capture(tmp_path)
    original = coordinator.transaction.__wrapped__
    try:
        with observer.exit_profiler.scope():
            with original(): pass  # Original fixture caches can bypass the outer research CM.
            with coordinator.transaction(): pass
        facts = observer.snapshot()
        assert facts['observation_faults'] == 0 and facts['exit_profile']['coverage'] == 'COMPLETE'
        assert facts['exit_profile']['transaction_pairing'] == 'INCOMPLETE'
        state = facts['exit_profile']['threads']['CONTROL']
        assert state['calls'] == 12 and state['transaction_paired_calls'] == state['transaction_unattributed_calls'] == 6
        assert state['transaction_unattributed_stage_phase'] == {
            'NOT_APPLICABLE:' + stage: 1 for stage in ('SCOPE_COMMIT', 'SCOPE_CHECKPOINT_EXECUTE', 'SCOPE_CHECKPOINT_FETCH',
                'SCOPE_DB_CLOSE', 'SCOPE_GUARD_UNLOCK', 'SCOPE_GUARD_FILE_CLOSE')}
        assert facts['transactions']['unattributed_c_calls'] == {'CONTROL': 6}
        actor = facts['transactions']['actors']['CONTROL']
        assert actor['total'] == 1 and actor['record_pairing'] == 'COMPLETE'
        assert actor['record_pairing_semantics'] == 'OBSERVED_CONTEXT_ROWS_ONLY'
        assert facts['transactions']['observed_context_counts_exclude_unattributed_transactions']
    finally:
        observer.stop()
