"""External, opt-in timing research. Never a production qualification gate.

No source import occurs until pytest has selected one of twelve original cases.
Timings are inclusive and overlapping; CM exit includes original durability and
cleanup and is NOT an isolated fsync/COMMIT or OS-lock ownership measurement.
"""
from collections import deque
from contextlib import contextmanager
import functools
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import sys

import pytest

CASES = (
    "tests/unit/test_tip064_capacity_https.py::test_scope_broken_diagnostic_and_restore_keep_original_unknown_and_armed[record]",
    "tests/unit/test_tip064_capacity_https.py::test_scope_broken_diagnostic_and_restore_keep_original_unknown_and_armed[capture_failure]",
    "tests/unit/test_tip064_integration.py::test_long_fixture_valid_finite_schedule_requires_aggregate_observation[5-1000]",
    "tests/unit/test_tip064_integration.py::test_long_fixture_valid_finite_schedule_requires_aggregate_observation[10-1000]",
    "tests/unit/test_tip064_capacity_https.py::test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued[normal]",
    "tests/unit/test_tip064_capacity_https.py::test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued[delayed-release-and-completion]",
    "tests/unit/test_tip064_capacity_https.py::test_capacity_positive_profile_delayed_durable_registration_has_no_retry[1000]",
    "tests/unit/test_tip064_capacity_https.py::test_capacity_positive_profile_delayed_durable_registration_has_no_retry[5000]",
    "tests/unit/test_tip064_capacity_https.py::test_capacity_control_returns_while_workers_held_past_old_aggregate",
    "tests/unit/test_tip064_capacity_https.py::test_capacity_callback_original_survives_unknown_and_armed_scope[False]",
    "tests/unit/test_tip064_capacity_https.py::test_capacity_callback_original_survives_unknown_and_armed_scope[True]",
    "tests/unit/test_tip064_capacity_https.py::test_capacity_primary_late_callback_and_cleanup_keep_original_union",
)
BASE_STAGES = frozenset((
    "WORKER", "DISPATCH", "NATIVE_EXECUTE", "NATIVE_RESULT", "NATIVE_RECEIVE",
    "JOURNAL_VALIDATE", "JOURNAL_SAVE", "JOURNAL_GET", "JOURNAL_BEGIN", "JOURNAL_COMPLETE",
    "JOURNAL_FENCE", "JOURNAL_OUTCOME", "RESERVE", "START_RESERVED", "ADMIT",
    "MATERIALIZE", "SYNTHETIC_EFFECT", "CALLBACK", "RPC_WAIT", "RPC_SERVICE", "CONTROL_STEP",
    "HTTP_POST", "NODE_POST", "TRANSPORT_ATOMIC", "TRANSPORT_VALIDATE", "DOMAIN_ATOMIC",
    "DOMAIN_VALIDATE", "AUTH_VERIFY", "AUTH_BEGIN", "AUTH_COMPLETE", "SCOPE_DB", "SCOPE_VALIDATE",
    "LEASE_ARM", "LEASE_CLOSE", "CANONICAL", "DECODE", "METADATA_CREATE", "METADATA_UPDATE",
    "METADATA_READ", "AUTHORITY_INIT", "AUTHORITY_ARM", "AUTHORITY_VALIDATE", "AUTH_VERIFY",
))
CM_STAGES = frozenset(("JOURNAL_TX", "SCOPE_TX", "SCOPE_EXECUTION", "NATIVE_LEASE",
                      "NATIVE_FILE_LOCK", "SCOPE_FILE_LOCK", "JOB_FILE_LOCK", "AUTHORITY_TX", "MUTATION_LEASE"))
EXIT_STAGES = frozenset(("SCOPE_COMMIT", "SCOPE_CHECKPOINT_EXECUTE", "SCOPE_CHECKPOINT_FETCH",
                        "SCOPE_DB_CLOSE", "SCOPE_ROLLBACK", "SCOPE_GUARD_UNLOCK", "SCOPE_GUARD_FILE_CLOSE",
                        "SCOPE_EXIT_REMAINDER"))
STAGES = BASE_STAGES | EXIT_STAGES | frozenset(base + suffix for base in CM_STAGES for suffix in (".ENTER", ".BODY", ".EXIT"))
ERRORS = frozenset(("NONE", "TimeoutError", "RuntimeError", "AssertionError", "KeyboardInterrupt", "SystemExit", "OSError", "OTHER"))
LIMIT = 2 ** 31 - 1


class Observation:
    def __init__(self, case, *, clock=time.perf_counter):
        self.case, self.clock = case, clock
        self.control = threading.current_thread()
        self.workers = []  # Exact Thread objects; never thread names or recycled IDs.
        self.local = threading.local()
        self.lock = threading.RLock()
        self.enabled = True
        self.origin = self.now()
        self.prefix, self.tail, self.stats = [], deque(maxlen=64), {}
        self.total = self.faults = 0
        self.restores, self.bound = [], set()
        self.exit_profiler = ExitProfiler(self)

    def safe(self, function, *args):
        try:
            return function(*args)
        except BaseException:
            # Only a bounded count, no exception/traceback/cause retained.
            self.faults = min(LIMIT, self.faults + 1)
            return None

    def now(self):
        try:
            value = self.clock()
            return value if type(value) in (int, float) and math.isfinite(value) else None
        except BaseException:
            return None

    def actor(self):
        if not self.enabled:
            return None
        thread = threading.current_thread()
        if thread is self.control:
            return "CONTROL"
        for index, worker in enumerate(self.workers):
            if thread is worker:
                return "WORKER_" + str(index + 1)
        return None

    def register_worker(self):
        thread = threading.current_thread()
        with self.lock:
            if self.enabled and thread is not self.control and not any(thread is old for old in self.workers) and len(self.workers) < 2:
                self.workers.append(thread)

    def record(self, stage, start, error="NONE", *, duration=None):
        actor, end = self.actor(), self.now()
        if actor is None or stage not in STAGES or error not in ERRORS:
            return
        def milliseconds(value):
            return None if value is None else min(LIMIT, max(0, int(value * 1000)))
        elapsed = milliseconds(duration) if duration is not None else (milliseconds(end - start) if end is not None and start is not None else None)
        offset = milliseconds(start - self.origin) if start is not None and self.origin is not None else None
        with self.lock:
            if not self.enabled:
                return
            key = actor + ":" + stage
            stat = self.stats.setdefault(key, {"count": 0, "total_ms": 0, "max_ms": 0, "clock_missing": 0,
                                               "errors": 0, "first_start_ms": offset, "last_start_ms": offset})
            stat["count"] = min(LIMIT, stat["count"] + 1)
            stat["last_start_ms"] = offset
            stat["errors"] = min(LIMIT, stat["errors"] + (error != "NONE"))
            if elapsed is None:
                stat["clock_missing"] = min(LIMIT, stat["clock_missing"] + 1)
            else:
                stat["total_ms"] = min(LIMIT, stat["total_ms"] + elapsed)
                stat["max_ms"] = max(stat["max_ms"], elapsed)
            self.total = min(LIMIT, self.total + 1)
            row = {"actor": actor, "stage": stage, "start_ms": offset, "duration_ms": elapsed, "error": error}
            if len(self.prefix) < 64:
                self.prefix.append(row)
            else:
                self.tail.append(row)

    def invoke(self, stage, original, *args, **kwargs):
        if self.actor() is None:
            return original(*args, **kwargs)
        prior = getattr(self.local, "depth", 0)
        self.local.depth = prior + 1
        start, category = self.now(), "NONE"
        previous_exit = getattr(self.local, "exit_track", None)
        if stage == "SCOPE_TX.EXIT":
            self.local.exit_serial = min(LIMIT, getattr(self.local, "exit_serial", 0) + 1)
            self.local.exit_track = {"transaction": self.local.exit_serial, "pending": 0, "sum": 0,
                                     "missing": not getattr(self.local, "exit_profile_active", False)}
        try:
            return original(*args, **kwargs)
        except BaseException as error:
            category = type(error).__name__
            if category not in ERRORS:
                category = "OTHER"
            raise
        finally:
            if stage == "SCOPE_TX.EXIT":
                track, end = self.local.exit_track, self.now()
                callback = getattr(self.local, "exit_profile_callback", None)
                if callback is None or self.safe(sys.getprofile) is not callback or track["pending"]:
                    track["missing"] = True
                if not track["missing"] and start is not None and end is not None:
                    self.safe(lambda: self.record("SCOPE_EXIT_REMAINDER", start, category,
                                                 duration=max(0, end - start - track["sum"])))
                self.local.exit_track = previous_exit
            self.safe(self.record, stage, start, category)
            self.local.depth = prior

    def patch(self, obj, name, wrapper):
        if len(self.restores) >= 512:
            self.faults = min(LIMIT, self.faults + 1)
            return
        original = getattr(obj, name)
        had, raw = name in vars(obj), vars(obj).get(name)
        replacement = wrapper(original)
        # Register restoration BEFORE attempting a potentially partial setter.
        self.restores.append((obj, name, had, raw, replacement))
        setattr(obj, name, replacement)

    def method(self, obj, name, stage, *, nested=False, worker=False, cm=False, entered=None):
        def make(original):
            @functools.wraps(original)
            def wrapped(*args, **kwargs):
                if worker:
                    self.safe(self.register_worker)
                if self.actor() is None or (nested and not getattr(self.local, "depth", 0)):
                    return original(*args, **kwargs)
                if cm:
                    context = original(*args, **kwargs)
                    return ObservedContext(self, stage, context, entered)
                if worker:
                    with self.exit_profiler.scope():
                        return self.invoke(stage, original, *args, **kwargs)
                return self.invoke(stage, original, *args, **kwargs)
            return wrapped
        self.safe(self.patch, obj, name, make)

    def once(self, obj):
        # Strong references in restores prevent ID reuse during this bounded call.
        key = id(obj)
        if key in self.bound:
            return False
        if len(self.bound) >= 64:
            self.faults = min(LIMIT, self.faults + 1)
            return False
        self.bound.add(key)
        return True

    def bind_lease(self, lease):
        if self.once(lease):
            self.method(lease, "arm", "LEASE_ARM")
            self.method(lease, "close_zero_attempt", "LEASE_CLOSE")

    def bind_coordinator(self, coordinator):
        if not self.once(coordinator):
            return
        self.exit_profiler.coordinators.append(coordinator)
        self.method(coordinator, "_db", "SCOPE_DB")
        self.method(coordinator, "_validate", "SCOPE_VALIDATE")
        self.method(coordinator, "transaction", "SCOPE_TX", cm=True)
        self.method(coordinator, "execution", "SCOPE_EXECUTION", cm=True, entered=self.bind_lease)

    def bind_dispatcher(self, dispatcher):
        if not self.once(dispatcher):
            return
        self.method(dispatcher, "_native_work", "WORKER", worker=True)
        self.method(dispatcher, "dispatch_async", "DISPATCH")
        journal = dispatcher.native
        for name, stage in (("execute", "NATIVE_EXECUTE"), ("observe_result", "NATIVE_RESULT"),
                            ("receive", "NATIVE_RECEIVE"), ("_validate", "JOURNAL_VALIDATE"),
                            ("_save", "JOURNAL_SAVE"), ("get", "JOURNAL_GET"),
                            ("begin_effect", "JOURNAL_BEGIN"), ("complete_effect", "JOURNAL_COMPLETE"),
                            ("_effect_fence", "JOURNAL_FENCE"), ("_outcome", "JOURNAL_OUTCOME")):
            self.method(journal, name, stage)
        self.method(journal, "transaction", "JOURNAL_TX", cm=True)
        for name, stage in (("_atomic", "DOMAIN_ATOMIC"), ("_validate", "DOMAIN_VALIDATE")):
            if hasattr(dispatcher.journal, name):
                self.method(dispatcher.journal, name, stage)
        adapter = dispatcher.native_adapter
        for name, stage in (("reserve", "RESERVE"), ("start_reserved", "START_RESERVED"),
                            ("_admit", "ADMIT"), ("_materialize", "MATERIALIZE"),
                            ("_synthetic_effect", "SYNTHETIC_EFFECT")):
            if hasattr(adapter, name):
                self.method(adapter, name, stage)
        if hasattr(adapter, "concurrency"):
            self.method(adapter.concurrency, "native_execution", "NATIVE_LEASE", cm=True)
            self.method(adapter.concurrency, "mutation", "MUTATION_LEASE", cm=True)
        if dispatcher.authorization_verifier is not None:
            self.method(dispatcher.authorization_verifier, "verify", "AUTH_VERIFY")
        if hasattr(adapter, "jobs"):
            for name, stage in (("create_reserved", "METADATA_CREATE"), ("update_fields", "METADATA_UPDATE"), ("get", "METADATA_READ")):
                if hasattr(adapter.jobs, name):
                    self.method(adapter.jobs, name, stage)
        # Callback dictionary belongs to this synthetic adapter; wrap only the
        # existing start entry, restoring exact original callable after capture.
        callbacks = getattr(adapter, "callbacks", None)
        if type(callbacks) is dict and callable(callbacks.get("start")):
            original = callbacks["start"]
            def wrapped(*args, **kwargs):
                return self.invoke("CALLBACK", original, *args, **kwargs)
            callbacks["start"] = wrapped
            self.restores.append((callbacks, "start", True, original, wrapped))

    def bind_agent(self, agent):
        if not self.once(agent):
            return
        self.method(agent, "step", "CONTROL_STEP")
        self.method(agent, "_service_rpc", "RPC_SERVICE")
        self.method(agent.rpc_proxy, "_request", "RPC_WAIT")
        self.method(agent.client, "_post", "NODE_POST")
        transport = agent.client.transport_journal
        for name, stage in (("_atomic", "TRANSPORT_ATOMIC"), ("_validate", "TRANSPORT_VALIDATE")):
            if hasattr(transport, name):
                self.method(transport, name, stage)

    def constructor(self, cls, bind, *, nested_stage=None):
        def make(original):
            @functools.wraps(original)
            def wrapped(obj, *args, **kwargs):
                owned = (self.actor() is not None and getattr(self.local, "depth", 0)) if nested_stage else (
                    threading.current_thread() is self.control and self.enabled and getattr(self.local, "build", 0))
                result = self.invoke(nested_stage, original, obj, *args, **kwargs) if owned and nested_stage else original(obj, *args, **kwargs)
                if owned:
                    self.safe(bind, obj)
                return result
            return wrapped
        self.safe(self.patch, cls, "__init__", make)

    def bind_authority(self, authority):
        if self.once(authority):
            self.method(authority, "arm", "AUTHORITY_ARM")
            self.method(authority, "transaction", "AUTHORITY_TX", cm=True)
            if hasattr(authority, "_validate"):
                self.method(authority, "_validate", "AUTHORITY_VALIDATE")

    def install(self, module, http):
        # Constructor seams only bind within the selected original helper's
        # synchronous object construction. Other constructors remain untouched.
        def make_builder(original):
            @functools.wraps(original)
            def wrapped(*args, **kwargs):
                if threading.current_thread() is not self.control or not self.enabled:
                    return original(*args, **kwargs)
                prior = getattr(self.local, "build", 0)
                self.local.build = prior + 1
                try:
                    return original(*args, **kwargs)
                finally:
                    self.local.build = prior
            return wrapped
        helper = "run_capacity_fixture" if hasattr(module, "ScopeFixtureObservations") else "runtime"
        self.safe(self.patch, module, helper, make_builder)
        self.constructor(module.NodeDomainDispatcher, self.bind_dispatcher)
        self.constructor(module.OutboundNode, self.bind_agent)
        if hasattr(module, "ScopeFixtureObservations"):
            self.constructor(module.ScopeFixtureObservations, lambda obj: self.bind_coordinator(obj.coordinator))
        self.method(http, "post", "HTTP_POST")
        from vibemql5.fleet import native, scoped_resources, job_journal
        from vibemql5.core import jobs
        self.safe(self.exit_profiler.configure, scoped_resources, jobs)
        from vibemql5.core.native_ownership import OwnershipAuthority
        self.constructor(OwnershipAuthority, self.bind_authority, nested_stage="AUTHORITY_INIT")
        for obj, stage in ((native, "NATIVE_FILE_LOCK"), (scoped_resources, "SCOPE_FILE_LOCK"), (jobs, "JOB_FILE_LOCK")):
            self.method(obj, "_exclusive_file_lock", stage, nested=True, cm=True)
        for name, stage in (("canonical", "CANONICAL"), ("_decode", "DECODE")):
            self.method(job_journal, name, stage, nested=True)

    def stop(self):
        self.enabled = False  # Late/in-flight callbacks cannot capture teardown.
        for obj, name, had, raw, replacement in reversed(self.restores):
            def restore():
                if type(obj) is dict:
                    if obj.get(name) is replacement:
                        obj[name] = raw
                elif getattr(obj, name, None) is replacement:
                    if had:
                        setattr(obj, name, raw)
                    else:
                        delattr(obj, name)
            self.safe(restore)
        self.restores.clear()

    def snapshot(self):
        with self.lock:
            return {"schema": "windows-stage-research/1", "case": self.case,
                    "capture_enabled": self.enabled, "observation_faults": self.faults,
                    "worker_threads_bound": len(self.workers), "stats": {key: dict(value) for key, value in self.stats.items()},
                    "timeline": list(self.prefix) + list(self.tail), "timeline_total": self.total,
                    "timeline_dropped": max(0, self.total - 128), "timeline_limit": 128,
                    "exit_profile": {"configuration": self.exit_profiler.configuration,
                                     "threads": {key: dict(value) for key, value in self.exit_profiler.states.items()},
                                     "coverage": ("NOT_APPLICABLE" if not self.exit_profiler.coordinators else
                                                  "COMPLETE" if self.exit_profiler.configuration == "AVAILABLE"
                                                  and self.exit_profiler.states and all(state["coverage_complete"]
                                                      and not state["active"] for state in self.exit_profiler.states.values())
                                                  else "INCOMPLETE"),
                                     "semantics": "C_CALL_INCLUSIVE_SCHEDULING_NOT_PHYSICAL_IO",
                                     "not_applicable": not bool(self.exit_profiler.coordinators)},
                    "timing_semantics": "INCLUSIVE_OVERLAPPING_ORIGINAL_CALLS",
                    "physical_os_owner": "NOT_OBSERVED", "isolated_commit_fsync": "NOT_OBSERVED",
                    "tls_gateway_server": "NOT_OBSERVED", "qualification": "RESEARCH_ONLY"}


class ExitProfiler:
    """Only the original owned SQLite/file C boundaries; no proxy or extra read."""
    def __init__(self, observer):
        self.observer = observer
        self.coordinators, self.states = [], {}
        self.configuration = "UNCONFIGURED"
        self.transaction_code = self.guard_code = None

    def configure(self, scoped, jobs):
        expected = json.loads((Path(__file__).parent / "source-manifest.json").read_text())
        self.transaction_code = self.guard_code = None
        codes = []
        for module, name, function, sites in (
                (scoped, "app/vibemql5/fleet/scoped_resources.py", scoped.ScopedResourceCoordinator.transaction,
                 {371, 374, 377, 379}),
                (jobs, "app/vibemql5/core/jobs.py", jobs._exclusive_file_lock, {187, 201, 203})):
            source = Path(module.__file__).read_bytes()
            if hashlib.sha256(source).hexdigest() != expected[name]:
                self.configuration = "SOURCE_SEAM_MISMATCH"
                return
            code = function.__wrapped__.__code__
            def frozen_code(container):
                for value in container.co_consts:
                    if type(value) is type(code):
                        if value.co_qualname == code.co_qualname:
                            return value
                        found = frozen_code(value)
                        if found is not None:
                            return found
            frozen = frozen_code(compile(source, str(module.__file__), "exec", dont_inherit=True))
            if frozen != code or not sites <= {line for _, _, line in code.co_lines()}:
                self.configuration = "SOURCE_SEAM_MISMATCH"
                return
            codes.append(code)
        self.transaction_code, self.guard_code = codes
        self.configuration = "AVAILABLE"

    def stage(self, frame, method):
        code, line, values = frame.f_code, frame.f_lineno, frame.f_locals
        name, owner = getattr(method, "__name__", None), getattr(method, "__self__", None)
        if code is self.transaction_code and any(values.get("self") is obj for obj in self.coordinators):
            if owner is values.get("db"):
                return {(371, "execute"): "SCOPE_COMMIT", (374, "execute"): "SCOPE_CHECKPOINT_EXECUTE",
                        (379, "close"): "SCOPE_DB_CLOSE", (377, "execute"): "SCOPE_ROLLBACK"}.get((line, name))
            if line == 374 and name == "fetchone":
                # No result/SQL inspection; exact C cursor method and original site.
                import sqlite3
                if type(owner) is sqlite3.Cursor:
                    return "SCOPE_CHECKPOINT_FETCH"
        if code is self.guard_code and any(values.get("path") is obj.guard for obj in self.coordinators):
            if (line, name) in ((187, "locking"), (201, "flock")):
                return "SCOPE_GUARD_UNLOCK"
            if line == 203 and name == "close" and owner is values.get("f"):
                return "SCOPE_GUARD_FILE_CLOSE"
        return None

    @contextmanager
    def scope(self):
        observer, actor = self.observer, self.observer.actor()
        if actor is None:
            yield
            return
        with observer.lock:
            state = self.states.setdefault(actor, {"status": "UNAVAILABLE", "active": False, "calls": 0,
                                                    "exceptions": 0, "unmatched": 0, "faults": 0,
                                                    "scopes": 0, "skipped_existing": 0, "clock_missing": 0,
                                                    "pending_peak": 0, "coverage_complete": True})
            state["scopes"] = min(LIMIT, state["scopes"] + 1)
        pending, installed, prior = {}, False, None

        def incomplete():
            state["coverage_complete"] = False
            observer.local.exit_profile_active = False
            track = getattr(observer.local, "exit_track", None)
            if track is not None:
                track["missing"] = True

        def callback(frame, event, method):
            if not observer.enabled or state["status"] != "AVAILABLE":
                return
            try:
                if observer.actor() != actor or event not in ("c_call", "c_return", "c_exception"):
                    return
                if frame.f_code is not self.transaction_code and frame.f_code is not self.guard_code:
                    return
                stage = self.stage(frame, method)
                if stage is None:
                    return
                key = (frame, stage)
                if event == "c_call":
                    if len(pending) >= 64 or key in pending:
                        raise RuntimeError()
                    track = getattr(observer.local, "exit_track", None)
                    pending[key] = (observer.now(), track)
                    if track is not None:
                        track["pending"] += 1
                    state["pending_peak"] = max(state["pending_peak"], len(pending))
                else:
                    if key not in pending:
                        with observer.lock:
                            state["unmatched"] = min(LIMIT, state["unmatched"] + 1)
                            incomplete()
                        return
                    (start, paired_track), end = pending.pop(key), observer.now()
                    duration = end - start if start is not None and end is not None else None
                    if duration is None:
                        state["clock_missing"] = min(LIMIT, state["clock_missing"] + 1)
                        incomplete()
                    track = getattr(observer.local, "exit_track", None)
                    if paired_track is not None:
                        paired_track["pending"] -= 1
                    if track is not paired_track:
                        incomplete()
                    if track is not None:
                        if duration is None:
                            track["missing"] = True
                        else:
                            track["sum"] += max(0, duration)
                    observer.record(stage, start, "OTHER" if event == "c_exception" else "NONE", duration=duration)
                    with observer.lock:
                        state["calls"] = min(LIMIT, state["calls"] + 1)
                        state["exceptions"] = min(LIMIT, state["exceptions"] + (event == "c_exception"))
            except BaseException:
                with observer.lock:
                    state["status"] = "OBSERVATION_FAULT"
                    state["faults"] = min(LIMIT, state["faults"] + 1)
                    observer.faults = min(LIMIT, observer.faults + 1)
                    incomplete()

        try:
            try:
                if self.configuration != "AVAILABLE":
                    state["status"] = self.configuration
                    incomplete()
                elif (prior := sys.getprofile()) is not None:
                    state["status"] = "UNSUPPORTED_EXISTING_PROFILE"
                    state["skipped_existing"] = min(LIMIT, state["skipped_existing"] + 1)
                    incomplete()
                else:
                    state["status"] = "AVAILABLE"
                    # Set installed first: a partial setter must still restore.
                    installed = True
                    sys.setprofile(callback)
                    state["active"] = True
                    observer.local.exit_profile_active = state["coverage_complete"]
                    observer.local.exit_profile_callback = callback
            except BaseException:
                state["status"] = "INSTALL_FAULT"
                state["faults"] = min(LIMIT, state["faults"] + 1)
                observer.faults = min(LIMIT, observer.faults + 1)
                incomplete()
            yield
        finally:
            observer.local.exit_profile_active = False
            observer.local.exit_profile_callback = None
            try:
                if installed:
                    current = sys.getprofile()
                    if current is callback:
                        sys.setprofile(prior)
                    elif current is not prior or state["status"] != "INSTALL_FAULT":
                        state["status"] = "REPLACED_BY_OTHER_OWNER"
                        incomplete()
            except BaseException:
                state["status"] = "RESTORE_FAULT"
                state["faults"] = min(LIMIT, state["faults"] + 1)
                observer.faults = min(LIMIT, observer.faults + 1)
                incomplete()
            with observer.lock:
                # Presence differs from recording: a faulty setter can leave
                # our already-disabled callback installed in this thread.
                state["active"] = installed and observer.safe(sys.getprofile) is callback
                state["unmatched"] = min(LIMIT, state["unmatched"] + len(pending))
                if pending:
                    incomplete()
            pending.clear()


class ObservedContext:
    def __init__(self, observer, stage, context, entered=None):
        self.observer, self.stage, self.context, self.entered = observer, stage, context, entered
        self.body = None

    def __enter__(self):
        result = self.observer.invoke(self.stage + ".ENTER", type(self.context).__enter__, self.context)
        if self.entered is not None and self.observer.actor() is not None:
            self.observer.safe(self.entered, result)
        self.body = self.observer.now()
        return result

    def __exit__(self, typ, error, traceback):
        self.observer.safe(self.observer.record, self.stage + ".BODY", self.body)
        return self.observer.invoke(self.stage + ".EXIT", type(self.context).__exit__, self.context, typ, error, traceback)


def pytest_addoption(parser):
    parser.addoption("--stage-observation-dir", default=None)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    # Exact node ID allowlist. All fixture setup is untouched and not observed.
    if item.nodeid not in CASES or not item.config.getoption("--stage-observation-dir"):
        yield
        return
    try:
        observation = Observation(CASES.index(item.nodeid))
    except BaseException:
        # Research initialization cannot replace an original test outcome.
        yield
        return
    def install():
        service = item.funcargs.get("capacity_service", item.funcargs.get("composed_service"))
        observation.install(item.module, service[0])
    observation.safe(install)
    try:
        with observation.exit_profiler.scope():
            yield
    finally:
        observation.safe(observation.stop)
        def publish():
            folder = Path(item.config.getoption("--stage-observation-dir"))
            folder.mkdir(parents=True, exist_ok=True)
            payload = observation.snapshot()
            (folder / ("case-" + str(observation.case) + ".json")).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            print("WINDOWS_STAGE_RESEARCH " + json.dumps(payload, sort_keys=True), flush=True)
        observation.safe(publish)
