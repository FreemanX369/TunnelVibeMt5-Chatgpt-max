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
