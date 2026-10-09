"""External, opt-in timing research. Never a production qualification gate.

No source import occurs until pytest has selected one of twelve original cases.
Timings are inclusive and overlapping; CM exit includes original durability and
cleanup and is NOT an isolated fsync/COMMIT or OS-lock ownership measurement.
"""
from collections import deque
import functools
import json
import math
from pathlib import Path
import threading
import time

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
STAGES = BASE_STAGES | frozenset(base + suffix for base in CM_STAGES for suffix in (".ENTER", ".BODY", ".EXIT"))
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

    def record(self, stage, start, error="NONE"):
        actor, end = self.actor(), self.now()
        if actor is None or stage not in STAGES or error not in ERRORS:
            return
        def milliseconds(value):
            return None if value is None else min(LIMIT, max(0, int(value * 1000)))
        elapsed = milliseconds(end - start) if end is not None and start is not None else None
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
        try:
            return original(*args, **kwargs)
        except BaseException as error:
            category = type(error).__name__
            if category not in ERRORS:
                category = "OTHER"
            raise
        finally:
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
                    "timing_semantics": "INCLUSIVE_OVERLAPPING_ORIGINAL_CALLS",
                    "physical_os_owner": "NOT_OBSERVED", "isolated_commit_fsync": "NOT_OBSERVED",
                    "tls_gateway_server": "NOT_OBSERVED", "qualification": "RESEARCH_ONLY"}


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
