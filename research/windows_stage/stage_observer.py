"""External, opt-in timing research. Never a production qualification gate.

No source import occurs until pytest has selected one of twelve original cases.
Timings are inclusive and overlapping; CM exit includes original durability and
cleanup and is NOT an isolated fsync/COMMIT or OS-lock ownership measurement.
"""
from collections import deque
from contextlib import contextmanager
import ast
import functools
import hashlib
import inspect
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


def finite(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def frozen_code(source, filename, code, *, rewritten=False):
    def find(container):
        for value in container.co_consts:
            if type(value) is type(code):
                if value.co_qualname == code.co_qualname:
                    return value
                found = find(value)
                if found is not None:
                    return found
    if rewritten:
        from _pytest.assertion.rewrite import rewrite_asserts
        tree = ast.parse(source, filename=filename)
        rewrite_asserts(tree, source, filename)
        source = tree
    return find(compile(source, filename, "exec", dont_inherit=True))


class TransactionRetention:
    """First8/latest8/largest16 exits per owned actor, with explicit dropped rows."""
    def __init__(self):
        self.actors = {}

    def add(self, actor, row):
        state = self.actors.setdefault(actor, {"total": 0, "incomplete": 0, "first": [],
                                               "latest": deque(maxlen=8), "largest": []})
        state["total"] = min(LIMIT, state["total"] + 1)
        state["incomplete"] = min(LIMIT, state["incomplete"] + bool(row["incomplete"]))
        if len(state["first"]) < 8:
            state["first"].append(row)
        state["latest"].append(row)
        state["largest"].append(row)
        state["largest"].sort(key=lambda item: (-(item["exit_seconds"] or 0), item["transaction"]))
        del state["largest"][16:]

    def snapshot(self, profiles=None):
        result = {}
        for actor, state in self.actors.items():
            unique = {row["transaction"]: row for rows in (state["first"], state["latest"], state["largest"]) for row in rows}
            result[actor] = {"total": state["total"], "incomplete_total": state["incomplete"],
                             "retained": len(unique), "dropped": max(0, state["total"] - len(unique)),
                             "coverage": "SAMPLED" if state["total"] > len(unique) else "COMPLETE",
                             "coverage_semantics": "RETENTION_ONLY", "record_pairing": "INCOMPLETE" if state["incomplete"] else "COMPLETE",
                             "record_pairing_semantics": "OBSERVED_CONTEXT_ROWS_ONLY",
                             "records": [unique[key] for key in sorted(unique)]}
        return {"limit_per_actor": 32, "selection": "FIRST8_LATEST8_LARGEST16_EXIT_DEDUPLICATED", "actors": result,
                "unattributed_c_calls": {actor: state["transaction_unattributed_calls"] for actor, state in (profiles or {}).items() if state["transaction_unattributed_calls"]},
                "observed_context_counts_exclude_unattributed_transactions": True}


class Observation:
    def __init__(self, case, *, clock=time.perf_counter):
        self.case, self.clock = case, clock
        self.control = threading.current_thread()
        self.workers = []  # Exact Thread objects; never thread names or recycled IDs.
        self.local = threading.local()
        self.lock = threading.RLock()
        self.enabled = True
        self.origin = self.now()
        self.monotonic_origin = self.monotonic_now()
        self.fixture_origins = []
        self.transactions = TransactionRetention()
        self.prefix, self.tail, self.stats = [], deque(maxlen=64), {}
        self.total = self.faults = 0
        self.restores, self.bound = [], set()
        self.exit_profiler = ExitProfiler(self)
        self.pump = PumpObservation(self)
        self.prerequisite = PrerequisiteObservation(self)

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

    def monotonic_now(self):
        try:
            return finite(time.monotonic())
        except BaseException:
            return None

    def interval(self, start, end, error="NONE"):
        origin = self.monotonic_origin
        return {"start_seconds": start - origin if start is not None and origin is not None else None,
                "end_seconds": end - origin if end is not None and origin is not None else None,
                "duration_seconds": end - start if start is not None and end is not None and end >= start else None,
                "error": error}

    def transaction_begin(self, coordinator):
        actor = self.actor()
        if actor is None:
            return None
        self.local.transaction_serial = min(LIMIT, getattr(self.local, "transaction_serial", 0) + 1)
        return {"case": self.case, "actor": actor, "transaction": self.local.transaction_serial,
                "coordinator": next((i + 1 for i, obj in enumerate(self.exit_profiler.coordinators) if obj is coordinator), None),
                "intervals": {}, "boundaries": [], "incomplete": False, "body_error": "NONE",
                "pump_phase_at_enter": self.pump.phase,
                "_coordinator": coordinator, "_db": None, "_cursor": None, "_file": None}

    def transaction_finish(self, row):
        if row is None or not self.enabled:
            return
        intervals = row["intervals"]
        row["incomplete"] |= any(interval["duration_seconds"] is None for interval in intervals.values())
        row["incomplete"] |= "EXIT" not in intervals or self.monotonic_origin is None
        row["exit_seconds"] = intervals.get("EXIT", {}).get("duration_seconds")
        row["executed_boundaries"] = len(row["boundaries"])
        row["stage_coverage"] = "EXECUTED" if row["boundaries"] else "UNEXECUTED"
        row["pump_phase_at_finish"] = self.pump.phase
        exit_error = intervals.get("EXIT", {}).get("error", "OTHER")
        row["route"] = "ORIGINAL_ERROR_PATH" if row["body_error"] != "NONE" or exit_error != "NONE" else "NORMAL_EXIT"
        expected = {"SCOPE_DB_CLOSE", "SCOPE_GUARD_UNLOCK", "SCOPE_GUARD_FILE_CLOSE"}
        expected |= {"SCOPE_COMMIT", "SCOPE_CHECKPOINT_EXECUTE", "SCOPE_CHECKPOINT_FETCH"} if row["route"] == "NORMAL_EXIT" else set()
        row["incomplete"] |= not expected <= {item["stage"] for item in row["boundaries"]}
        if not row["incomplete"] and row["exit_seconds"] is not None:
            summed = sum(item["duration_seconds"] for item in row["boundaries"])
            row["exit_remainder_seconds"] = max(0, row["exit_seconds"] - summed)
        else:
            row["exit_remainder_seconds"] = None
        for name in ("_coordinator", "_db", "_cursor", "_file"):
            del row[name]
        with self.lock:
            self.transactions.add(row["actor"], row)

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
                                     "missing": not getattr(self.local, "exit_profile_active", False),
                                     "record": getattr(self.local, "transaction_record", None)}
        pump_step = self.safe(self.pump.step_begin, original) if stage == "CONTROL_STEP" else None
        admission_step = self.safe(self.prerequisite.step_begin, original) if stage == "CONTROL_STEP" else None
        admission_span = self.safe(self.prerequisite.span_begin, stage) if stage != "CONTROL_STEP" else None
        try:
            return original(*args, **kwargs)
        except BaseException as error:
            category = type(error).__name__
            if category not in ERRORS:
                category = "OTHER"
            raise
        finally:
            if admission_span is not None:
                self.safe(self.prerequisite.span_end, admission_span, category)
            if admission_step is not None:
                self.safe(self.prerequisite.step_end, admission_step, category)
            if pump_step is not None:
                self.safe(self.pump.step_end, pump_step, category)
            if stage == "SCOPE_TX.EXIT":
                track, end = self.local.exit_track, self.now()
                callback = getattr(self.local, "exit_profile_callback", None)
                if callback is None or self.safe(sys.getprofile) is not callback or track["pending"]:
                    track["missing"] = True
                if track["record"] is not None:
                    track["record"]["incomplete"] |= track["missing"]
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
                    return ObservedContext(self, stage, context, entered, obj if stage == "SCOPE_TX" else None)
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
            def bind_fixture(obj):
                self.bind_coordinator(obj.coordinator)
                if len(self.fixture_origins) < 64:
                    self.fixture_origins.append(finite(obj.origin))
            self.constructor(module.ScopeFixtureObservations, bind_fixture)
        self.method(http, "post", "HTTP_POST")
        from vibemql5.fleet import native, scoped_resources, job_journal
        from vibemql5.core import jobs
        self.safe(self.exit_profiler.configure, scoped_resources, jobs)
        if self.case in PrerequisiteObservation.CAPACITY_CASES:
            self.safe(self.prerequisite.configure, module)
        if self.case == 5:
            self.safe(self.pump.configure, module)
        if self.prerequisite.configuration == "AVAILABLE" or self.pump.configuration == "AVAILABLE":
            def router(original):
                @functools.wraps(original)
                def wrapped(*args, **kwargs):
                    caller = self.safe(sys._getframe, 2)
                    if caller is None:
                        return original(*args, **kwargs)
                    selected = self.prerequisite if caller.f_code is self.prerequisite.codes.get("helper") and caller.f_lineno == 313 else self.pump
                    delegated = self.safe(lambda: selected.wrapper(original, caller=caller))
                    if delegated is None:
                        return original(*args, **kwargs)
                    return delegated(*args, **kwargs)
                return wrapped
            self.safe(self.patch, module, "pump", router)
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
                    "clocks": {"base_stats_timeline": {"domain": "time.perf_counter", "origin_absolute_seconds": self.origin},
                               "transaction_pump": {"domain": "time.monotonic", "origin_absolute_seconds": self.monotonic_origin},
                               "original_fixture": {"domain": "time.monotonic", "origins_absolute_seconds": list(self.fixture_origins),
                                                    "thread_labels_are_actor_ids": False}},
                    "transactions": self.transactions.snapshot(self.exit_profiler.states), "final_pump": self.pump.snapshot(),
                    "prerequisite_pump": self.prerequisite.snapshot(),
                    "exit_profile": {"configuration": self.exit_profiler.configuration,
                                     "threads": {key: dict(value) for key, value in self.exit_profiler.states.items()},
                                     "coverage": ("NOT_APPLICABLE" if not self.exit_profiler.coordinators else
                                                  "COMPLETE" if self.exit_profiler.configuration == "AVAILABLE"
                                                  and self.exit_profiler.states and all(state["coverage_complete"]
                                                      and not state["active"] for state in self.exit_profiler.states.values())
                                                  else "INCOMPLETE"),
                                     "semantics": "C_CALL_INCLUSIVE_SCHEDULING_NOT_PHYSICAL_IO",
                                     "stage_coverage": ("NOT_APPLICABLE" if not self.exit_profiler.coordinators else
                                                        "EXECUTED" if any(state["calls"] for state in self.exit_profiler.states.values()) else "UNEXECUTED"),
                                     "transaction_pairing": ("NOT_APPLICABLE" if not self.exit_profiler.coordinators else
                                                             "INCOMPLETE" if any(state["transaction_unattributed_calls"] or not state["coverage_complete"] for state in self.exit_profiler.states.values()) else "COMPLETE"),
                                     "not_applicable": not bool(self.exit_profiler.coordinators)},
                    "timing_semantics": "INCLUSIVE_OVERLAPPING_ORIGINAL_CALLS",
                    "physical_os_owner": "NOT_OBSERVED", "isolated_commit_fsync": "NOT_OBSERVED",
                    "tls_gateway_server": "NOT_OBSERVED", "qualification": "RESEARCH_ONLY"}


class PumpObservation:
    """Case5's original final pump only; never call its predicate or step again."""
    def __init__(self, observer):
        self.observer = observer
        self.configuration = "NOT_APPLICABLE" if observer.case != 5 else "UNCONFIGURED"
        self.phase, self.current = "BEFORE_FINAL_PUMP", None
        self.codes, self.original = {}, None
        self.prefix, self.tail = [], deque(maxlen=32)
        self.total = self.calls = self.clock_missing = 0
        self.deadline = None
        self.deadline_changed = self.failure_branch = self.predicate_true = False
        self.pytest_outcome, self.error = "NOT_OBSERVED", "NONE"

    def configure(self, module):
        self.configuration = "SOURCE_SEAM_MISMATCH"
        expected = json.loads((Path(__file__).parent / "source-manifest.json").read_text())
        helper, pump = inspect.unwrap(module.run_capacity_fixture), module.pump
        for function, name in ((helper, "tests/unit/test_tip064_capacity_https.py"),
                               (pump, "tests/unit/test_tip064_integration.py")):
            path = Path(function.__code__.co_filename)
            source = path.read_bytes()
            if hashlib.sha256(source).hexdigest() != expected[name]:
                return
            if not any(frozen_code(source, str(path), function.__code__, rewritten=rewritten) == function.__code__ for rewritten in (False, True)):
                return
        def nested(code):
            for value in code.co_consts:
                if type(value) is type(code):
                    self.codes[value.co_qualname] = value
                    nested(value)
        nested(helper.__code__)
        self.codes["helper"], self.codes["pump"] = helper.__code__, pump.__code__
        for name in ("run_capacity_fixture.<locals>.checked", "run_capacity_fixture.<locals>.checked.<locals>.observed",
                     "run_capacity_fixture.<locals>.completed", "run_capacity_fixture.<locals>.raise_callback_failure"):
            if name not in self.codes:
                return
        if not {434, 435, 439} <= {line for _, _, line in pump.__code__.co_lines()}:
            return
        self.original = pump
        self.monotonic = pump.__globals__["time"].monotonic
        self.fail_owner = pump.__globals__["pytest"].fail
        self.fail_code = getattr(self.fail_owner, "__code__", getattr(self.fail_owner.__call__, "__code__", None))
        if self.fail_code is None:
            return
        self.configuration = "AVAILABLE"

    def mark(self, stage, *, start=None, error="NONE", result=None):
        if not self.observer.enabled:
            return
        end = self.observer.monotonic_now()
        row = {"stage": stage, **self.observer.interval(end if start is None else start, end, error)}
        if result is not None:
            row["original_result"] = result
        if row["duration_seconds"] is None:
            self.clock_missing = min(LIMIT, self.clock_missing + 1)
        self.total = min(LIMIT, self.total + 1)
        if len(self.prefix) < 32:
            self.prefix.append(row)
        else:
            self.tail.append(row)

    def recognize(self, caller, agent, predicate, seconds):
        if self.configuration != "AVAILABLE" or self.observer.actor() != "CONTROL" or self.current is not None:
            return False
        if caller is None or caller.f_code is not self.codes["helper"] or caller.f_lineno != 382 or type(seconds) is not int or seconds != 10:
            return False
        values = caller.f_locals
        if values.get("agent") is not agent or getattr(predicate, "__code__", None) is not self.codes["run_capacity_fixture.<locals>.checked.<locals>.observed"]:
            return False
        closure = dict(zip(predicate.__code__.co_freevars, (cell.cell_contents for cell in predicate.__closure__)))
        completed, checked, callback = values.get("completed"), values.get("checked"), values.get("raise_callback_failure")
        return (closure.get("predicate") is completed and closure.get("raise_callback_failure") is callback
                and getattr(completed, "__code__", None) is self.codes["run_capacity_fixture.<locals>.completed"]
                and getattr(checked, "__code__", None) is self.codes["run_capacity_fixture.<locals>.checked"]
                and getattr(callback, "__code__", None) is self.codes["run_capacity_fixture.<locals>.raise_callback_failure"])

    def wrapper(self, original, *, caller=None):
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            agent = args[0] if args else kwargs.get("agent")
            predicate = args[1] if len(args) > 1 else kwargs.get("predicate")
            source_caller = caller if caller is not None else self.observer.safe(sys._getframe, 2)
            recognized = self.observer.safe(self.recognize, source_caller, agent, predicate, kwargs.get("seconds", 3))
            if not recognized:
                return original(*args, **kwargs)
            self.calls = min(LIMIT, self.calls + 1)
            self.current = {"agent": agent, "predicate": predicate, "completed": source_caller.f_locals["completed"],
                            "frame": None, "predicate_frame": None, "predicate_start": None}
            self.phase = "DURING_FINAL_PUMP"
            self.observer.safe(self.mark, "OBSERVED_ENTRY")
            try:
                result = original(*args, **kwargs)
            except BaseException as error:
                self.error = type(error).__name__ if type(error).__name__ in ERRORS | {"Failed", "BaseExceptionGroup", "ExceptionGroup"} else "OTHER"
                self.phase = "AFTER_ORIGINAL_PUMP_FAILURE"
                self.observer.safe(lambda: self.mark("ORIGINAL_EXCEPTION", error=self.error))
                raise
            else:
                self.phase = "AFTER_ORIGINAL_PUMP_RETURN"
                self.observer.safe(self.mark, "ORIGINAL_RETURN")
                return result
            finally:
                self.current = None  # Do not retain frames, closures, errors or payloads.
        return wrapped

    def step_begin(self, original):
        if self.current is not None and self.observer.actor() == "CONTROL" and getattr(original, "__self__", None) is self.current["agent"]:
            self.mark("STEP_ENTRY")
            return self.observer.monotonic_now()
        return None

    def step_end(self, start, error):
        self.mark("STEP_EXIT", start=start, error=error)

    def event(self, frame, event, arg):
        current = self.current
        if current is None or self.observer.actor() != "CONTROL":
            return
        if event == "call" and frame.f_code is self.codes["pump"] and frame.f_locals.get("predicate") is current["predicate"] and frame.f_locals.get("agent") is current["agent"]:
            current["frame"] = frame
        pump_frame = current["frame"]
        if frame is pump_frame and event == "c_call" and arg is self.monotonic and frame.f_lineno == 435:
            raw = frame.f_locals.get("deadline")
            value = raw if type(raw) is float and math.isfinite(raw) else None
            if value is None:
                self.clock_missing = min(LIMIT, self.clock_missing + 1)
            elif self.deadline is None:
                self.deadline = value
                self.mark("ORIGINAL_DEADLINE_OBSERVED")
            elif self.deadline != value:
                self.deadline_changed = True
        if event == "call" and frame.f_back is pump_frame and frame.f_code is self.fail_code and pump_frame.f_lineno == 439 and (
                hasattr(self.fail_owner, "__code__") or frame.f_locals.get("self") is self.fail_owner):
            self.failure_branch = True
            self.mark("ORIGINAL_FAILURE_BRANCH_439")
        if frame.f_code is current["predicate"].__code__:
            if event == "call" and frame.f_back is pump_frame and frame.f_locals.get("predicate") is current["completed"]:
                current["predicate_frame"], current["predicate_start"] = frame, self.observer.monotonic_now()
                self.mark("PREDICATE_ENTRY")
            elif event == "return" and frame is current["predicate_frame"]:
                result = "TRUE" if arg is True else "FALSE" if arg is False else "UNCLASSIFIED"
                self.predicate_true |= arg is True
                self.mark("PREDICATE_RETURN", start=current["predicate_start"], result=result)
                current["predicate_frame"] = None
        if frame is pump_frame and event == "return":
            # Python profile return(None) also occurs when unwinding an error.
            self.mark("PROFILE_RETURN_UNCLASSIFIED")

    def outcome(self, outcome):
        if outcome is not None:
            self.pytest_outcome = "FAILED" if outcome.excinfo is not None else "PASSED"

    def snapshot(self):
        applicable = self.observer.case == 5
        complete = self.configuration == "AVAILABLE" and self.calls == 1 and self.deadline is not None and not self.deadline_changed and not self.clock_missing and self.current is None and not self.observer.faults
        return {"configuration": self.configuration, "recognition": "RECOGNIZED" if self.calls else "UNAVAILABLE" if applicable else "NOT_APPLICABLE",
                "calls": self.calls, "original_seconds": 10 if applicable else None,
                "original_deadline_absolute_monotonic_seconds": self.deadline,
                "deadline_changed": self.deadline_changed, "clock_missing": self.clock_missing,
                "coverage": "COMPLETE" if complete else "INCOMPLETE" if applicable else "NOT_APPLICABLE",
                "coverage_semantics": "DEADLINE_IDENTITY_OUTCOME_PAIRING_NOT_MARKER_RETENTION",
                "phase": self.phase, "failure_branch_439": self.failure_branch,
                "original_exception_category": self.error, "observed_predicate_true": self.predicate_true,
                "pytest_call_outcome": self.pytest_outcome, "markers": list(self.prefix) + list(self.tail),
                "marker_total": self.total, "marker_dropped": max(0, self.total - 64), "marker_limit": 64,
                "marker_retention": "SAMPLED" if self.total > 64 else "COMPLETE",
                "entry_semantics": "OBSERVED_WRAPPER_ENTRY_NOT_RECONSTRUCTED_ORIGINAL_START",
                "profile_return_semantics": "UNCLASSIFIED_NOT_SUCCESS_PROOF"}


class LinkedRetention:
    """Finite first/latest/largest inclusive rows, without adding nested durations."""
    def __init__(self, first, latest, largest):
        self.first_limit, self.largest_limit = first, largest
        self.first, self.latest, self.largest = [], deque(maxlen=latest), []
        self.total = self.incomplete = 0

    def add(self, row):
        self.total = min(LIMIT, self.total + 1)
        self.incomplete = min(LIMIT, self.incomplete + bool(row["incomplete"]))
        if len(self.first) < self.first_limit:
            self.first.append(row)
        self.latest.append(row)
        self.largest.append(row)
        self.largest.sort(key=lambda value: (-(value["duration_seconds"] or 0), value["ordinal"]))
        del self.largest[self.largest_limit:]

    def snapshot(self):
        unique = {row["ordinal"]: row for rows in (self.first, self.latest, self.largest) for row in rows}
        return {"total": self.total, "retained": len(unique), "dropped": max(0, self.total - len(unique)),
                "incomplete_total": self.incomplete, "rows": [unique[key] for key in sorted(unique)]}


class PrerequisiteObservation(PumpObservation):
    """The original helper313/default3 admission, separate from case5 final pump."""
    CAPACITY_CASES = frozenset((0, 1, 4, 5, 6, 7, 8, 9, 10, 11))

    def __init__(self, observer):
        super().__init__(observer)
        self.applicable = observer.case in self.CAPACITY_CASES
        self.configuration = "UNCONFIGURED" if self.applicable else "NOT_APPLICABLE"
        self.phase = "BEFORE_PREREQUISITE"
        self.steps = LinkedRetention(8, 8, 16)
        self.step = None
        self.step_serial = self.span_serial = self.pending_overflow = self.unmatched = 0
        self.actual_seconds, self.default_changed = None, False

    def configure(self, module):
        super().configure(module)
        if self.configuration != "AVAILABLE":
            return
        defaults = self.original.__kwdefaults__ or {}
        if type(defaults.get("seconds")) is not int or defaults["seconds"] != 3:
            self.configuration = "SOURCE_SEAM_MISMATCH"
            return
        def find(code):
            for value in code.co_consts:
                if type(value) is type(code):
                    if value.co_name == "<lambda>" and value.co_firstlineno == 313:
                        yield value
                    yield from find(value)
        found = list(find(self.codes["helper"]))
        if len(found) != 1 or found[0].co_freevars != ("entered",):
            self.configuration = "SOURCE_SEAM_MISMATCH"
            return
        self.codes["prerequisite_predicate"] = found[0]

    def recognize(self, caller, agent, predicate, seconds):
        if (not self.applicable or self.configuration != "AVAILABLE" or self.observer.actor() != "CONTROL"
                or self.current is not None or self.calls or caller is None or caller.f_code is not self.codes["helper"]
                or caller.f_lineno != 313 or type(seconds) is not int or seconds != 3):
            return False
        values = caller.f_locals
        if values.get("agent") is not agent or getattr(predicate, "__code__", None) is not self.codes["run_capacity_fixture.<locals>.checked.<locals>.observed"]:
            return False
        closure = dict(zip(predicate.__code__.co_freevars, (cell.cell_contents for cell in predicate.__closure__)))
        target, callback, checked = closure.get("predicate"), values.get("raise_callback_failure"), values.get("checked")
        if getattr(target, "__code__", None) is not self.codes["prerequisite_predicate"]:
            return False
        inner = dict(zip(target.__code__.co_freevars, (cell.cell_contents for cell in target.__closure__)))
        if getattr(checked, "__code__", None) is not self.codes["run_capacity_fixture.<locals>.checked"]:
            return False
        checked_closure = dict(zip(checked.__code__.co_freevars, (cell.cell_contents for cell in checked.__closure__)))
        return (inner.get("entered") is values.get("entered") and inner.get("entered") is not None
                and closure.get("raise_callback_failure") is callback and checked_closure.get("raise_callback_failure") is callback
                and getattr(callback, "__code__", None) is self.codes["run_capacity_fixture.<locals>.raise_callback_failure"])

    def wrapper(self, original, *, caller=None):
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            agent = args[0] if args else None
            predicate = args[1] if len(args) == 2 else None
            source_caller = caller if caller is not None else self.observer.safe(sys._getframe, 2)
            recognized = not kwargs and self.observer.safe(self.recognize, source_caller, agent, predicate, 3)
            if not recognized:
                return original(*args, **kwargs)
            valid_default = self.observer.safe(lambda: type((self.original.__kwdefaults__ or {}).get("seconds")) is int
                                                and self.original.__kwdefaults__["seconds"] == 3)
            if not valid_default:
                self.default_changed = True
                self.configuration = "DEFAULT_MISMATCH"
                return original(*args, **kwargs)
            closure = self.observer.safe(lambda: dict(zip(predicate.__code__.co_freevars, (cell.cell_contents for cell in predicate.__closure__))))
            if closure is None:
                return original(*args, **kwargs)
            self.calls = min(LIMIT, self.calls + 1)
            self.current = {"agent": agent, "predicate": predicate, "completed": closure["predicate"],
                            "frame": None, "predicate_frame": None, "predicate_start": None}
            self.phase = "DURING_PREREQUISITE"
            self.observer.safe(self.mark, "OBSERVED_ENTRY")
            try:
                result = original(*args, **kwargs)
            except BaseException as error:
                self.error = type(error).__name__ if type(error).__name__ in ERRORS | {"Failed", "BaseExceptionGroup", "ExceptionGroup"} else "OTHER"
                self.phase = "AFTER_ORIGINAL_PREREQUISITE_FAILURE"
                self.observer.safe(lambda: self.mark("ORIGINAL_EXCEPTION", error=self.error))
                raise
            else:
                self.phase = "AFTER_ORIGINAL_PREREQUISITE_RETURN"
                self.observer.safe(self.mark, "ORIGINAL_RETURN")
                return result
            finally:
                if self.step is not None:
                    self.unmatched = min(LIMIT, self.unmatched + 1)
                    self.observer.safe(self.step_end, self.step, "OTHER")
                self.current = None
        return wrapped

    def event(self, frame, event, arg):
        current = self.current
        if (current is not None and self.observer.actor() == "CONTROL" and event == "call"
                and frame.f_code is self.codes["pump"] and frame.f_locals.get("agent") is current["agent"]
                and frame.f_locals.get("predicate") is current["predicate"]):
            seconds = frame.f_locals.get("seconds")
            self.actual_seconds = seconds if type(seconds) is int and 0 <= seconds <= LIMIT else None
            if type(seconds) is not int or seconds != 3:
                self.default_changed = True
                self.configuration = "ORIGINAL_SECONDS_MISMATCH"
        super().event(frame, event, arg)

    def step_begin(self, original):
        if self.current is None or self.observer.actor() != "CONTROL" or getattr(original, "__self__", None) is not self.current["agent"]:
            return None
        if self.step is not None:
            self.unmatched = min(LIMIT, self.unmatched + 1)
            return None
        self.step_serial = min(LIMIT, self.step_serial + 1)
        self.step = {"ordinal": self.step_serial, "start": self.observer.monotonic_now(),
                     "children": LinkedRetention(16, 16, 32), "pending": [], "incomplete": False}
        self.mark("STEP_ENTRY")
        return self.step

    def step_end(self, step, error):
        if self.step is not step:
            self.unmatched = min(LIMIT, self.unmatched + 1)
            return
        interval = self.observer.interval(step["start"], self.observer.monotonic_now(), error)
        pending = len(step["pending"])
        self.unmatched = min(LIMIT, self.unmatched + pending)
        children = step["children"].snapshot()
        ids = {row["ordinal"] for row in children["rows"]}
        missing = sum(row["parent"] is not None and row["parent"] not in ids for row in children["rows"])
        children.update({"limit": 64, "selection": "FIRST16_LATEST16_LARGEST32_DEDUPLICATED", "missing_parent_rows": missing})
        row = {"ordinal": step["ordinal"], **interval, "children": children,
               "incomplete": step["incomplete"] or bool(pending or missing or children["incomplete_total"]) or interval["duration_seconds"] is None}
        self.steps.add(row)
        self.step = None
        self.mark("STEP_EXIT", start=step["start"], error=error)

    def span_begin(self, stage):
        step = self.step
        if step is None or self.current is None or self.observer.actor() != "CONTROL" or stage not in STAGES:
            return None
        if len(step["pending"]) >= 64:
            self.pending_overflow = min(LIMIT, self.pending_overflow + 1)
            step["incomplete"] = True
            return None
        self.span_serial = min(LIMIT, self.span_serial + 1)
        row = {"ordinal": self.span_serial, "step": step["ordinal"], "stage": stage,
               "parent": step["pending"][-1]["ordinal"] if step["pending"] else None,
               "start": self.observer.monotonic_now()}
        step["pending"].append(row)
        return row

    def span_end(self, row, error):
        step = self.step
        if step is None or self.observer.actor() != "CONTROL" or not any(row is value for value in step["pending"]):
            self.unmatched = min(LIMIT, self.unmatched + 1)
            return
        if step["pending"][-1] is not row:
            step["incomplete"] = True
            self.unmatched = min(LIMIT, self.unmatched + 1)
        step["pending"].remove(row)
        interval = self.observer.interval(row["start"], self.observer.monotonic_now(), error)
        step["children"].add({key: value for key, value in row.items() if key != "start"} | interval |
                             {"incomplete": interval["duration_seconds"] is None})

    def snapshot(self):
        result = super().snapshot()
        complete = (self.configuration == "AVAILABLE" and self.calls == 1 and self.deadline is not None
                    and not self.deadline_changed and not self.clock_missing and self.current is None and self.step is None
                    and not self.observer.faults and not self.pending_overflow and not self.unmatched)
        steps = self.steps.snapshot()
        result.update({"recognition": "RECOGNIZED" if self.calls else "UNEXECUTED" if self.configuration == "AVAILABLE" else "UNAVAILABLE" if self.applicable else "NOT_APPLICABLE",
                       "original_seconds": self.actual_seconds if self.calls else 3 if self.applicable and self.configuration == "AVAILABLE" else None,
                       "expected_seconds": 3 if self.applicable else None, "default_changed": self.default_changed,
                       "coverage": "COMPLETE" if complete else "UNEXECUTED" if self.applicable and not self.calls and self.configuration == "AVAILABLE" else "INCOMPLETE" if self.applicable else "NOT_APPLICABLE",
                       "steps": steps | {"limit": 32, "selection": "FIRST8_LATEST8_LARGEST16_DEDUPLICATED",
                                           "pending_overflow": self.pending_overflow, "unmatched": self.unmatched,
                                           "linkage": "INCOMPLETE" if steps["incomplete_total"] or self.pending_overflow or self.unmatched else "COMPLETE",
                                           "semantics": "INCLUSIVE_NESTED_INTERVALS_NOT_ADDITIVE_NOT_PHYSICAL_IO"}})
        return result


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

    def boundary(self, frame, method, stage, start, end, event, row):
        if row is None:
            return False
        values, owner = frame.f_locals, getattr(method, "__self__", None)
        if frame.f_code is self.transaction_code:
            exact = values.get("self") is row["_coordinator"] and values.get("db") is row["_db"]
            if stage == "SCOPE_CHECKPOINT_FETCH":
                import sqlite3
                exact &= type(owner) is sqlite3.Cursor and owner.connection is row["_db"]
                if exact and row["_cursor"] is None:
                    row["_cursor"] = owner
                exact &= owner is row["_cursor"]
            else:
                exact &= owner is row["_db"]
        else:
            exact = values.get("path") is row["_coordinator"].guard
            if row["_file"] is None:
                row["_file"] = values.get("f")
            exact &= values.get("f") is row["_file"] and row["_file"] is not None
            if stage == "SCOPE_GUARD_FILE_CLOSE":
                exact &= owner is row["_file"]
        if not exact or len(row["boundaries"]) >= 8:
            row["incomplete"] = True
            return False
        interval = self.observer.interval(start, end, "OTHER" if event == "c_exception" else "NONE")
        if interval["duration_seconds"] is None:
            row["incomplete"] = True
        row["boundaries"].append({"stage": stage, **interval, "identity": "EXACT_ORIGINAL_TRANSACTION",
                                  "connection": 1 if frame.f_code is self.transaction_code else None,
                                  "cursor": 1 if stage == "SCOPE_CHECKPOINT_FETCH" else None,
                                  "guard_file": 1 if frame.f_code is self.guard_code else None})
        return True

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
            state.setdefault("transaction_paired_calls", 0)
            state.setdefault("transaction_unattributed_calls", 0)
            state.setdefault("transaction_unattributed_stage_phase", {})
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
                if observer.actor() != actor:
                    return
                observer.pump.event(frame, event, method)
                observer.prerequisite.event(frame, event, method)
                if event not in ("c_call", "c_return", "c_exception"):
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
                    pending[key] = (observer.now(), track, observer.monotonic_now(), getattr(method, "__self__", None))
                    if track is not None:
                        track["pending"] += 1
                    state["pending_peak"] = max(state["pending_peak"], len(pending))
                else:
                    if key not in pending:
                        with observer.lock:
                            state["unmatched"] = min(LIMIT, state["unmatched"] + 1)
                            incomplete()
                        return
                    (start, paired_track, monotonic_start, paired_owner), end = pending.pop(key), observer.now()
                    duration = end - start if start is not None and end is not None else None
                    if duration is None:
                        state["clock_missing"] = min(LIMIT, state["clock_missing"] + 1)
                        incomplete()
                    track = getattr(observer.local, "exit_track", None)
                    transaction_paired = False
                    if paired_track is not None:
                        paired_track["pending"] -= 1
                    if track is not paired_track:
                        incomplete()
                    if getattr(method, "__self__", None) is not paired_owner:
                        incomplete()
                    if track is not None:
                        if duration is None:
                            track["missing"] = True
                        else:
                            track["sum"] += max(0, duration)
                        if track is paired_track:
                            transaction_paired = self.boundary(frame, method, stage, monotonic_start, observer.monotonic_now(), event, track["record"])
                    observer.record(stage, start, "OTHER" if event == "c_exception" else "NONE", duration=duration)
                    with observer.lock:
                        state["calls"] = min(LIMIT, state["calls"] + 1)
                        state["exceptions"] = min(LIMIT, state["exceptions"] + (event == "c_exception"))
                        state["transaction_paired_calls"] = min(LIMIT, state["transaction_paired_calls"] + bool(transaction_paired))
                        state["transaction_unattributed_calls"] = min(LIMIT, state["transaction_unattributed_calls"] + (not transaction_paired))
                        if not transaction_paired:
                            phase = observer.pump.phase if observer.case == 5 else "NOT_APPLICABLE"
                            key = phase + ":" + stage
                            counts = state["transaction_unattributed_stage_phase"]
                            counts[key] = min(LIMIT, counts.get(key, 0) + 1)
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
    def __init__(self, observer, stage, context, entered=None, coordinator=None):
        self.observer, self.stage, self.context, self.entered = observer, stage, context, entered
        self.body = None
        self.coordinator, self.transaction = coordinator, None
        self.prior_transaction = None

    def __enter__(self):
        if self.coordinator is not None:
            self.transaction = self.observer.safe(self.observer.transaction_begin, self.coordinator)
            self.prior_transaction = getattr(self.observer.local, "transaction_record", None)
            self.observer.local.transaction_record = self.transaction
        start = self.observer.monotonic_now() if self.transaction is not None else None
        try:
            result = self.observer.invoke(self.stage + ".ENTER", type(self.context).__enter__, self.context)
        except BaseException as error:
            if self.transaction is not None:
                self.transaction["intervals"]["ENTER"] = self.observer.interval(start, self.observer.monotonic_now(), type(error).__name__ if type(error).__name__ in ERRORS else "OTHER")
                self.transaction["incomplete"] = True
                self.observer.safe(self.observer.transaction_finish, self.transaction)
                self.observer.local.transaction_record = self.prior_transaction
            raise
        if self.transaction is not None:
            self.transaction["_db"] = result
            self.transaction["intervals"]["ENTER"] = self.observer.interval(start, self.observer.monotonic_now())
            self.body_monotonic = self.observer.monotonic_now()
        if self.entered is not None and self.observer.actor() is not None:
            self.observer.safe(self.entered, result)
        self.body = self.observer.now()
        self.admission_body = self.observer.safe(self.observer.prerequisite.span_begin, self.stage + ".BODY")
        return result

    def __exit__(self, typ, error, traceback):
        self.observer.safe(self.observer.record, self.stage + ".BODY", self.body)
        category = type(error).__name__ if error is not None and type(error).__name__ in ERRORS else "OTHER" if error is not None else "NONE"
        if self.admission_body is not None:
            self.observer.safe(self.observer.prerequisite.span_end, self.admission_body, category)
        start = self.observer.monotonic_now() if self.transaction is not None else None
        if self.transaction is not None:
            self.transaction["body_error"] = category
            self.transaction["intervals"]["BODY"] = self.observer.interval(self.body_monotonic, start, category)
        category = "NONE"
        try:
            return self.observer.invoke(self.stage + ".EXIT", type(self.context).__exit__, self.context, typ, error, traceback)
        except BaseException as failure:
            category = type(failure).__name__ if type(failure).__name__ in ERRORS else "OTHER"
            raise
        finally:
            if self.transaction is not None:
                self.transaction["intervals"]["EXIT"] = self.observer.interval(start, self.observer.monotonic_now(), category)
                self.observer.safe(self.observer.transaction_finish, self.transaction)
                self.observer.local.transaction_record = self.prior_transaction


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
            outcome = yield
            observation.safe(observation.pump.outcome, outcome)
            observation.safe(observation.prerequisite.outcome, outcome)
    finally:
        observation.safe(observation.stop)
        def publish():
            folder = Path(item.config.getoption("--stage-observation-dir"))
            folder.mkdir(parents=True, exist_ok=True)
            payload = observation.snapshot()
            (folder / ("case-" + str(observation.case) + ".json")).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            print("WINDOWS_STAGE_RESEARCH " + json.dumps(payload, sort_keys=True), flush=True)
        observation.safe(publish)
