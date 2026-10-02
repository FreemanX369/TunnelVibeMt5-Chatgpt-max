"""Dedicated Q1 runner. Windows requirements cannot turn into skipped PASS."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "app"))
from authority import FixtureAuthority, RecoveryRequired, atomic, outcome
from windows_boundary import Boundary, Process, Windows

EVIDENCE = []
EXECUTABLE = None
PHASE_FILES = ("entry.json", "started.json", "result.json", "initialize-attempted.json", "cleanup-attempted.json",
               "observation-attempted.json", "observation.json", "direct-child.json", "breakaway-child.json", "go.txt",
               "fixture-diagnostic.json", "positive-marker.json")


def record(case, **values):
    EVIDENCE.append({"case": case, **values})


def wait_json(path, seconds=5, *, process=None, case="fixture-output"):
    path = Path(path)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            if process is not None and process.exited():
                code = process.wait(0)
                record(case, missing_output=path.name, exit_code=code,
                       exit_code_hex=f"0x{code:08x}",
                       phase_markers={name: (path.parent / name).exists() for name in PHASE_FILES},
                       lifetime=process.lifetime(),
                       writer_diagnostic=diagnostic_tail(path.parent / "fixture-diagnostic.json"))
                raise AssertionError(f"FIXTURE_EXIT_BEFORE_OUTPUT:{path.name}:0x{code:08x}")
            time.sleep(0.005)
    record(case, missing_output=path.name, output_timeout_seconds=seconds,
           process_signaled=None if process is None else process.exited(),
           phase_markers={name: (path.parent / name).exists() for name in PHASE_FILES})
    raise AssertionError(f"FIXTURE_OUTPUT_UNAVAILABLE:{path.name}")


def log_tail(path, limit=4000):
    with Path(path).open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - limit))
        return stream.read(limit).decode("utf-8", errors="replace")


def diagnostic_tail(path):
    try:
        return log_tail(path)
    except OSError as error:
        return f"DIAGNOSTIC_UNAVAILABLE:{type(error).__name__}:{str(error)[:500]}"


def writer_probe_exit(code, mode):
    raw = {"raw_exit": code, "raw_exit_hex": f"0x{code:08x}",
           "disposition": "FULL_RAW_DWORD_PRESERVED_STAGE_UNAVAILABLE"}
    stages = {1: "CREATE_FILE", 2: "WRITE_FILE", 3: "FLUSH_FILE", 4: "CLOSE_FILE"}
    stage = (code >> 16) & 0xF
    if mode == "write_probe" and code & 0xFFF00000 == 0xE5100000 and stage in stages:
        raw.update(protocol="tip057rq.writer-exit/1", inferred_writer_stage=stages[stage],
                   inferred_win32_error_low16=code & 0xFFFF, error_payload_bits=16,
                   emitter_rule="KNOWN_STAGE_AND_NATIVE_ERROR_FITS_16_BITS",
                   provenance="NOT_AUTHENTICATED_BY_EXIT_ALONE", tag_collision_possible=True,
                   qualification="NONE",
                   disposition="PARTIAL_PROTOCOL_SHAPED_DIAGNOSTIC_CANDIDATE_KNOWN_PROBE_ONLY")
    return raw


def directory_label_isolation(root_security, executable_before, executable_after):
    """Read-back gate for a low directory without altering its binary label."""
    observed = (root_security, executable_before, executable_after)
    readable = all("sddl" in value and isinstance(value.get("selected_label_descriptor"), dict)
                   and not value["selected_label_descriptor"].get("truncated", False)
                   for value in observed)
    if not readable:
        return {"passed": False, "disposition": "LABEL_READBACK_UNQUALIFIED"}
    root_label = root_security["selected_label_descriptor"]
    before = executable_before["selected_label_descriptor"]
    after = executable_after["selected_label_descriptor"]
    directory_only = (root_label.get("ace_count") == 1 and root_label.get("label_aces") ==
                      [{"index": 0, "flags": 0, "mask": 1, "sid": "S-1-16-4096"}])
    # The LABEL-only reader emits SYSTEM_MANDATORY_LABEL_ACEs after complete
    # parsing. Empty SACL/autoinherit metadata can change without an image label.
    def mandatory_aces(label):
        return [("SYSTEM_MANDATORY_LABEL_ACE", ace["flags"], ace["mask"], ace["sid"])
                for ace in label["label_aces"]]
    binary_unchanged = mandatory_aces(before) == mandatory_aces(after)
    return {"passed": directory_only and binary_unchanged,
            "root_directory_only_low_label": directory_only,
            "executable_label_matches_before_boundary": binary_unchanged,
            "binary_comparison": "COMPLETE_MANDATORY_ACE_TYPE_FLAGS_MASK_SID_SEMANTICS",
            "disposition": "ACTUAL_LABEL_APPLICABILITY_READBACK_ONLY"}


def stop_controller(caller):
    if caller.poll() is None:
        # On Windows Popen.kill uses its owned process handle, not a PID lookup.
        caller.kill()
    try:
        return caller.wait(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("OWNED_CONTROLLER_STOP_UNPROVEN") from error


def wait_controller(caller, seconds):
    try:
        return caller.wait(timeout=seconds)
    except subprocess.TimeoutExpired as error:
        code = stop_controller(caller)
        raise AssertionError(f"FIXTURE_CONTROLLER_TIMEOUT:{seconds}:STOP_PROVEN:{code}") from error


class ModelProcess:
    def __init__(self, identity=None, exited=True):
        self.ref = identity or {"pid": os.getpid(), "creation_100ns": 1, "image": "/harmless/fixture"}
        self.dead = exited

    def identity(self):
        return self.ref

    def exited(self):
        return self.dead


class PortableCases(unittest.TestCase):
    """Authority/precedence checks, explicitly not Windows preventive proof."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tip057rq-portable-")
        self.root = Path(self.temporary.name)
        self.authority = FixtureAuthority(self.root)
        self.parent = ModelProcess().identity()

    def tearDown(self):
        self.temporary.cleanup()

    def bound(self, descendants="NONE_FOR_FIXTURE_PATH"):
        lease, expected = self.authority.arm(self.parent)
        expected = self.authority.begin_create(expected)
        process = ModelProcess()
        expected = self.authority.bind_worker(expected, process.identity(), descendants=descendants)
        return lease, expected, process

    def test_no_attempt_release(self):
        lease, expected = self.authority.arm(self.parent)
        self.assertEqual(self.authority.no_start_release(expected), {"cleanup": "NOT_ATTEMPTED", "ownership": "RELEASED"})
        self.assertFalse(lease.exists())

    def test_create_attempt_without_binding_cannot_release(self):
        lease, expected = self.authority.arm(self.parent)
        self.authority.begin_create(expected)
        with self.assertRaises(RecoveryRequired):
            self.authority.no_start_release(expected)
        with self.assertRaises(RecoveryRequired):
            FixtureAuthority(self.root).arm(self.parent)
        self.assertTrue(lease.exists())

    def test_lost_active_intent_cannot_admit_after_dead_parent(self):
        parent = {**self.parent, "pid": 99999999}
        lease, _ = self.authority.arm(parent)
        self.authority.intent_path.unlink()
        # The native owner looks dead; loss of intent is still an active generation.
        lock = json.loads(lease.lock_path.read_text())
        lock["pid"] = parent["pid"]
        atomic(lease.lock_path, lock)
        with self.assertRaisesRegex(RecoveryRequired, "LOST_ACTIVE_INTENT"):
            FixtureAuthority(self.root).arm(self.parent)
        self.assertTrue(lease.exists())

    def test_partial_intent_is_fail_closed(self):
        lease, _ = self.authority.arm(self.parent)
        self.authority.intent_path.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            FixtureAuthority(self.root).arm(self.parent)
        self.assertTrue(lease.exists())

    def test_live_exact_worker_and_identity_mismatch_reject_clear(self):
        lease, expected, process = self.bound()
        process.dead = False
        with self.assertRaisesRegex(RecoveryRequired, "STILL_RUNNING"):
            self.authority.reconcile(expected, process)
        process.dead = True
        process.ref = {**process.ref, "creation_100ns": 2}
        with self.assertRaisesRegex(RecoveryRequired, "IDENTITY_MISMATCH"):
            self.authority.reconcile(expected, process)
        self.assertTrue(lease.exists())

    def test_unresolved_descendant_rejects_clear(self):
        lease, expected, process = self.bound(descendants="UNRESOLVED")
        with self.assertRaisesRegex(RecoveryRequired, "DESCENDANT"):
            self.authority.reconcile(expected, process)
        self.assertTrue(lease.exists())

    def test_stale_recovery_cannot_clear_successor(self):
        _, old, process = self.bound()
        self.authority.reconcile(old, process)
        successor, new = FixtureAuthority(self.root).arm(self.parent)
        with self.assertRaisesRegex(RecoveryRequired, "STALE"):
            self.authority.reconcile(old, process)
        self.assertGreater(new["generation"], old["generation"])
        self.assertEqual(json.loads(successor.lock_path.read_text())["token"], successor.token)

    def test_primary_cleanup_deadline_precedence_has_no_unqualified_values(self):
        for primary in (None, "LIVE_IPC_INITIALIZE_FAILED", "LIVE_OBSERVATION_UNAVAILABLE"):
            response = outcome(primary, "UNPROVEN", expired=True, qualified=True)
            self.assertEqual(response["reason_code"], "LIVE_CLEANUP_UNPROVEN")
            self.assertEqual(response["primary_reason_code"], primary)
            self.assertIsNone(response["account"])
        self.assertEqual(outcome("LIVE_OBSERVATION_UNAVAILABLE", expired=True)["reason_code"], "LIVE_OBSERVATION_UNAVAILABLE")
        self.assertEqual(outcome(expired=True)["reason_code"], "LIVE_DEADLINE_EXCEEDED")


class WindowsCases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="tip057rq-windows-")
        self.root = Path(self.temporary.name)
        self.executable = self.root / "fixture.exe"
        shutil.copy2(EXECUTABLE, self.executable)
        self.boundary = Boundary(self.root)
        self.windows = self.boundary.windows
        self.processes = []
        self.handles = []
        self.authority = FixtureAuthority(self.root / "authority")
        self.parent = Process(self.windows, self.windows.kernel.GetCurrentProcess()).identity()

    def tearDown(self):
        errors = []
        for process in self.processes:
            if process.handle:
                try:
                    if not process.exited():
                        process.terminate_exact(process.identity())
                except BaseException as error:
                    errors.append(f"OWNED_WORKER_STOP_UNPROVEN:{type(error).__name__}")
                finally:
                    try:
                        process.close()
                    except BaseException as error:
                        errors.append(f"OWNED_HANDLE_CLOSE_FAILED:{type(error).__name__}")
        for handle in self.handles:
            if not self.windows.kernel.CloseHandle(handle):
                errors.append("OWNED_PRIVILEGED_HANDLE_CLOSE_FAILED")
        try:
            self.boundary.close()
        except BaseException as error:
            errors.append(f"OWNED_PROFILE_CLEANUP_FAILED:{type(error).__name__}")
        try:
            self.temporary.cleanup()
        except BaseException as error:
            errors.append(f"TEMP_ROOT_CLEANUP_FAILED:{type(error).__name__}")
        if errors:
            record(self.id(), cleanup_errors=errors)
            self.fail(";".join(errors))

    def start(self, mode="observe", restricted=True, inherit=False, handle=0, descendants="NONE_FOR_FIXTURE_PATH"):
        lease, expected = self.authority.arm(self.parent)
        for name in PHASE_FILES:
            (self.root / name).unlink(missing_ok=True)
        process = self.boundary.spawn(self.executable, mode, self.parent["pid"], handle,
                                      restricted=restricted, inherit=inherit,
                                      before_create=lambda: self.authority.begin_create(expected))
        self.processes.append(process)
        expected = self.authority.bind_worker(expected, process.identity(),
                                              descendants="UNRESOLVED" if mode in {"launch", "launch_race"} else descendants)
        self.assertFalse((self.root / "entry.json").exists(), "suspended worker entered early")
        self.assertFalse((self.root / "started.json").exists(), "suspended worker executed early")
        process.resume()
        started = wait_json(self.root / "started.json", process=process, case=self.id())
        self.assertEqual(started["pid"], expected["worker"]["pid"])
        record(self.id(), restriction=started, worker=process.identity(), intent=expected)
        return lease, expected, process, started

    def finish(self, expected, process):
        self.assertEqual(process.wait(), 0)
        result = wait_json(self.root / "result.json")
        self.assertTrue((self.root / "cleanup-attempted.json").exists())
        if expected["descendants"] == "UNRESOLVED":
            for prefix in ("direct", "breakaway"):
                self.assertFalse(result[prefix + "_created"] and not result[prefix + "_terminated"],
                                 "descendant termination remains unknown; intent retained")
            expected = self.authority.descendants_proven(expected)
        response = outcome(result["primary_reason_code"], result["cleanup"], qualified=result["observed"])
        if result["cleanup"] == "PROVEN":
            released = self.authority.reconcile(expected, process)
            self.assertEqual(released["ownership"], "RELEASED")
        else:
            with self.assertRaises(RecoveryRequired):
                FixtureAuthority(self.authority.root).arm(self.parent)
        record(self.id(), result=result, response=response, exact_exit=process.exited(),
               exited_identity=process.identity(), identity_basis="SAME_HANDLE_LIVE_IMAGE_PLUS_PID_CREATION_AND_SIGNAL")
        return result, response

    def test_q01_restriction_active_before_work_and_setup_failure_no_attempt(self):
        lease, expected = self.authority.arm(self.parent)
        with self.assertRaises(OSError):
            self.boundary.spawn(self.executable, "observe", self.parent["pid"], setup_fault=True,
                                before_create=lambda: self.authority.begin_create(expected))
        self.assertFalse((self.root / "started.json").exists())
        self.assertEqual(self.authority.no_start_release(expected)["cleanup"], "NOT_ATTEMPTED")
        self.assertFalse(lease.exists())
        _, expected, process, started = self.start()
        self.assertEqual(started["appcontainer"], 1)
        self.assertEqual(started["policy_query_ok"], 1)
        self.assertEqual(started["child_restricted"], 1)
        self.assertTrue(started["before_work"])
        self.finish(expected, process)

    def test_q02_q03_unrestricted_control_and_restricted_stopped_launch(self):
        privileged = self.windows.privileged_inheritable_parent()
        self.handles.append(privileged)
        _, expected, control, started = self.start("launch", restricted=False, inherit=True, handle=privileged)
        result, _ = self.finish(expected, control)
        self.assertEqual(result["direct_error"], 0)
        self.assertEqual(result["direct_created"], 1)
        self.assertEqual(result["direct_terminated"], 1)
        self.assertTrue((self.root / "direct-child.json").exists())
        self.assertEqual(started["inherited_parent_pid"], self.parent["pid"])
        breakaway_control = (result["breakaway_error"] == 0 and result["breakaway_created"] == 1
                             and result["breakaway_terminated"] == 1 and (self.root / "breakaway-child.json").exists())
        control_breakaway_error = result["breakaway_error"]
        _, expected, restricted, started = self.start("launch", handle=privileged)
        result, _ = self.finish(expected, restricted)
        self.assertEqual(started["appcontainer"], 1)
        self.assertEqual(started["child_restricted"], 1)
        self.assertEqual(started["parent_create_error"], 5)
        self.assertEqual(started["parent_vm_write_error"], 5)
        self.assertNotEqual(started["inherited_parent_pid"], self.parent["pid"])
        self.assertNotEqual(result["direct_error"], 0)
        self.assertNotEqual(result["breakaway_error"], 0)
        self.assertEqual(result["direct_created"], 0)
        self.assertEqual(result["breakaway_created"], 0)
        self.assertFalse((self.root / "direct-child.json").exists())
        self.assertFalse((self.root / "breakaway-child.json").exists())
        record(self.id(), broker_sdk="OPEN", scope="CreateProcessW fixture paths only",
               breakaway_control_error=control_breakaway_error,
               breakaway_causal_qualification="QUALIFIED_FIXTURE_DENIAL" if breakaway_control else "OPEN_CONTROL_NOT_QUALIFIED_HOST_JOB_MAY_DENY")

    def test_q02_exit_between_discovery_and_launch(self):
        target_root = self.root / "target"
        target_root.mkdir()
        # This harmless target is controlled by its exact handle and never owns authority.
        target_boundary = Boundary(target_root)
        try:
            target_executable = target_root / "fixture.exe"
            shutil.copy2(EXECUTABLE, target_executable)
            target_boundary._grant_fixture_root()
            target = target_boundary.spawn(target_executable, "hang", self.parent["pid"], restricted=False)
            self.processes.append(target)
            target_ref = target.identity()
            target.resume()
            wait_json(target_root / "started.json", process=target, case=self.id())
            _, expected, worker, started = self.start("launch_race")
            self.assertEqual(started["child_restricted"], 1)
            elapsed = target.terminate_exact(target_ref)
            (self.root / "go.txt").write_text("exit-before-attempt", encoding="utf-8")
            result, _ = self.finish(expected, worker)
            self.assertNotEqual(result["direct_error"], 0)
            self.assertEqual(result["direct_created"], 0)
            self.assertFalse((self.root / "direct-child.json").exists())
            record(self.id(), target_exit_ms=elapsed, exact_target=target_ref)
            target.close()
        finally:
            target_boundary.close()

    def test_q04_primary_and_real_fixture_cleanup_faults(self):
        cases = [("init_false", "LIVE_IPC_INITIALIZE_FAILED", "PROVEN", 0),
                 ("init_raise", "LIVE_IPC_INITIALIZE_FAILED", "PROVEN", 1),
                 ("observe_raise", "LIVE_OBSERVATION_UNAVAILABLE", "PROVEN", 1),
                 ("shutdown_raise", None, "UNPROVEN", 1),
                 ("init_raise_shutdown_raise", "LIVE_IPC_INITIALIZE_FAILED", "UNPROVEN", 2)]
        for mode, primary, cleanup, caught in cases:
            with self.subTest(mode=mode):
                # Each fault uses an independent temporary root/authority.
                nested = WindowsCases("test_q01_restriction_active_before_work_and_setup_failure_no_attempt")
                nested.setUp()
                try:
                    _, expected, worker, _ = nested.start(mode)
                    result, response = nested.finish(expected, worker)
                    self.assertEqual(result["primary_reason_code"], primary)
                    self.assertEqual(result["cleanup"], cleanup)
                    self.assertTrue(result["cleanup_attempted"])
                    self.assertEqual(result["cleanup_completed"], cleanup == "PROVEN")
                    self.assertEqual(result["caught_exceptions"], caught)
                    self.assertIsNone(result["account"])
                    self.assertIsNone(response["account"])
                    record(self.id(), mode=mode, result=result, response=response)
                finally:
                    nested.tearDown()

    def test_q05_hang_does_not_release_before_exact_termination(self):
        total_start = time.monotonic()
        lease, expected, worker, _ = self.start("hang")
        budget_start = time.monotonic()
        while (time.monotonic() - budget_start) < 0.25:
            self.assertFalse(worker.exited())
            time.sleep(0.01)
        with self.assertRaisesRegex(RecoveryRequired, "STILL_RUNNING"):
            self.authority.reconcile(expected, worker)
        self.assertTrue(lease.exists())
        with self.assertRaises(RecoveryRequired):
            FixtureAuthority(self.authority.root).arm(self.parent)
        termination_ms = worker.terminate_exact(expected["worker"])
        self.authority.reconcile(expected, worker)
        self.assertFalse(lease.exists())
        record(self.id(), observation_budget_ms=250, actual_total_ms=(time.monotonic()-total_start)*1000,
               termination_ms=termination_ms, hard_10s_claim=False,
               post_exit_lifetime=worker.lifetime(), post_exit_identity=worker.identity())

    def test_q06_real_parent_crash_before_failure_marker(self):
        crash_root = self.root / "crash-parent"
        crash_root.mkdir()
        fresh = FixtureAuthority(crash_root / "authority")
        worker = None
        expected = None
        controller = None
        stdout_path, stderr_path = crash_root / "controller.stdout.log", crash_root / "controller.stderr.log"
        cleanup_errors = []
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                controller = subprocess.Popen([sys.executable, "-u", str(HERE / "run_proof.py"),
                                               "--crash-parent", str(crash_root), "--executable", str(EXECUTABLE)],
                                              stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
                code = wait_controller(controller, 15)
            self.assertEqual(code, 73, log_tail(stderr_path))
            expected = fresh.read()
            self.assertEqual(expected["parent"]["pid"], controller.pid)
            self.assertFalse((crash_root / "failure.json").exists())
            with self.assertRaises(RecoveryRequired):
                fresh.arm(self.parent)
            worker = Process.open_expected(self.windows, expected["worker"])
            self.processes.append(worker)
            self.assertFalse(worker.exited())
            termination_ms = worker.terminate_exact(expected["worker"])
            fresh.reconcile(expected, worker)
            successor, new = fresh.arm(self.parent)
            with self.assertRaisesRegex(RecoveryRequired, "STALE"):
                fresh.reconcile(expected, worker)
            self.assertEqual(json.loads(successor.lock_path.read_text())["token"], new["lease_token"])
            fresh.no_start_release(new)
            record(self.id(), crashed_parent=expected["parent"], worker=expected["worker"],
                   failure_marker_absent=True, termination_ms=termination_ms)
        finally:
            if controller is not None:
                try:
                    stop_controller(controller)
                except BaseException as error:
                    cleanup_errors.append(f"CRASH_CONTROLLER_STOP_UNPROVEN:{type(error).__name__}:{str(error)[:500]}")
                record(self.id(), controller_pid=controller.pid, controller_exit_code=controller.returncode,
                       stdout_tail=diagnostic_tail(stdout_path), stderr_tail=diagnostic_tail(stderr_path),
                       controller_phase_tail=diagnostic_tail(crash_root / "controller-phase.json")
                       if (crash_root / "controller-phase.json").exists() else None)
            # Recover only a persisted exact fixture identity. An unknown create outcome
            # stays visibly unresolved; never guess a PID or enumerate/kill strangers.
            try:
                if worker is None:
                    retained = fresh.read()
                    if retained is not None and retained.get("worker") is not None:
                        known = retained["worker"]
                        # Windows may return a long image path while the temp root uses
                        # its 8.3 alias. Compare the actual file, then verify live identity.
                        if not os.path.samefile(known["image"], crash_root / "fixture.exe"):
                            raise RuntimeError("UNOWNED_CRASH_IMAGE")
                        worker = Process.open_expected(self.windows, known)
                        self.processes.append(worker)
                    elif retained is not None and retained["phase"] != "ARMED_BEFORE_CREATE":
                        raise RuntimeError("CRASH_WORKER_IDENTITY_UNKNOWN")
                if worker is not None and worker.handle:
                    if not worker.exited():
                        worker.terminate_exact(worker.identity())
                    worker.close()
            except BaseException as error:
                cleanup_errors.append(f"CRASH_OWNED_WORKER_CLEANUP_UNPROVEN:{type(error).__name__}:{str(error)[:500]}")
            try:
                profile_path = crash_root / "profile.json"
                if profile_path.exists():
                    receipt = json.loads(profile_path.read_text(encoding="utf-8"))
                    profile = receipt["name"]
                    suffix = profile.removeprefix("tip057rq.")
                    if not profile.startswith("tip057rq.") or len(suffix) != 32 or any(c not in "0123456789abcdef" for c in suffix):
                        raise RuntimeError("UNOWNED_CRASH_PROFILE")
                    if receipt.get("status") != "DELETED":
                        result = self.windows.userenv.DeleteAppContainerProfile(profile)
                        if result < 0:
                            raise RuntimeError(f"OWNED_CRASH_PROFILE_CLEANUP_FAILED:{result}")
            except BaseException as error:
                cleanup_errors.append(f"CRASH_OWNED_PROFILE_CLEANUP_FAILED:{type(error).__name__}")
            if cleanup_errors:
                record(self.id(), cleanup_errors=cleanup_errors)
                self.fail(";".join(cleanup_errors))

    def test_q07_real_creation_identity_stale_generation_and_descendants(self):
        lease, expected, worker, _ = self.start("hang", descendants="UNRESOLVED")
        mismatch = {**expected["worker"], "creation_100ns": expected["worker"]["creation_100ns"] + 1}
        with self.assertRaisesRegex(RuntimeError, "IDENTITY_MISMATCH"):
            Process.open_expected(self.windows, mismatch)
        stale = {**expected, "generation": expected["generation"] + 1}
        with self.assertRaisesRegex(RecoveryRequired, "STALE"):
            self.authority.reconcile(stale, worker)
        worker.terminate_exact(expected["worker"])
        try:
            fresh_dead = Process.open_expected(self.windows, expected["worker"])
        except (OSError, RuntimeError) as error:
            record(self.id(), fresh_dead_identity="UNPROVEN_NO_LIVE_IMAGE_CACHE",
                   fresh_dead_error=f"{type(error).__name__}:{str(error)[:500]}")
        else:
            fresh_dead.close()
            self.fail("fresh dead-process handle qualified identity without a live image query")
        with self.assertRaisesRegex(RecoveryRequired, "DESCENDANT"):
            self.authority.reconcile(expected, worker)
        self.assertTrue(lease.exists())
        record(self.id(), pid_reuse="simulated creation-time mismatch against a real process",
               descendant_disposition="RECOVERY_REQUIRED")

    def test_q08_conflicting_callers_restart_and_recovery_race(self):
        lease, old, worker, _ = self.start("hang")
        results = []
        errors = []
        def conflict():
            try:
                FixtureAuthority(self.authority.root).arm(self.parent)
                results.append("UNSAFE_ACQUIRE")
            except RecoveryRequired:
                results.append("BLOCKED")
            except BaseException as error:
                errors.append(error)
        # These two acquisitions are independent processes using the common fixture gate.
        callers = []
        caller_receipts = []
        try:
            for index in range(2):
                stdout_path = self.root / f"caller-{index}.stdout.log"
                stderr_path = self.root / f"caller-{index}.stderr.log"
                with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    caller = subprocess.Popen([sys.executable, "-u", str(HERE / "run_proof.py"),
                                               "--attempt-arm", str(self.authority.root)],
                                              stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
                callers.append((caller, stdout_path, stderr_path))
            for caller, stdout_path, stderr_path in callers:
                self.assertEqual(wait_controller(caller, 10), 0, log_tail(stderr_path))
                caller_receipts.append(json.loads(log_tail(stdout_path)))
        finally:
            stop_errors = []
            for caller, stdout_path, stderr_path in callers:
                try:
                    stop_controller(caller)
                except BaseException as error:
                    stop_errors.append(f"CALLER_STOP_UNPROVEN:{caller.pid}:{type(error).__name__}")
                record(self.id(), caller_pid=caller.pid, caller_exit_code=caller.returncode,
                       stdout_tail=diagnostic_tail(stdout_path), stderr_tail=diagnostic_tail(stderr_path))
            self.assertEqual(stop_errors, [])
        self.assertTrue(all(row["status"] == "BLOCKED" for row in caller_receipts))
        self.assertEqual(len({row["parent"]["pid"] for row in caller_receipts}), 2)
        self.assertFalse(worker.exited())
        worker.terminate_exact(old["worker"])
        self.authority.reconcile(old, worker)
        successor, new = FixtureAuthority(self.authority.root).arm(self.parent)
        def stale_clear():
            try:
                FixtureAuthority(self.authority.root).reconcile(old, worker)
                results.append("UNSAFE_CLEAR")
            except RecoveryRequired:
                results.append("STALE_REJECTED")
            except BaseException as error:
                errors.append(error)
        stale = threading.Thread(target=stale_clear)
        contender = threading.Thread(target=conflict)
        stale.start(); contender.start(); stale.join(3); contender.join(3)
        self.assertFalse(stale.is_alive() or contender.is_alive())
        self.assertEqual(errors, [])
        self.assertCountEqual(results, ["STALE_REJECTED", "BLOCKED"])
        self.assertTrue(successor.exists())
        self.assertEqual(self.authority.read(), new)
        self.assertEqual(json.loads(successor.lock_path.read_text())["token"], new["lease_token"])
        self.assertGreater(new["generation"], old["generation"])
        self.authority.no_start_release(new)
        record(self.id(), process_callers=caller_receipts, recovery_thread_race=results,
               generations=[old["generation"], new["generation"]])


class RecordedResult(unittest.TextTestResult):
    def startTest(self, test):
        self.start_clock = time.monotonic()
        super().startTest(test)

    def addSuccess(self, test):
        record(test.id(), status="PASS", elapsed_ms=(time.monotonic()-self.start_clock)*1000)
        super().addSuccess(test)

    def addFailure(self, test, error):
        record(test.id(), status="FAIL", error_type=error[0].__name__)
        super().addFailure(test, error)

    def addError(self, test, error):
        record(test.id(), status="ERROR", error_type=error[0].__name__)
        super().addError(test, error)

    def addSkip(self, test, reason):
        # Required proof cases may not disappear as green skips.
        self.addFailure(test, (AssertionError, AssertionError("REQUIRED_CASE_SKIPPED:" + reason), None))


def compile_fixture(output):
    installer = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    found = subprocess.check_output([str(installer), "-latest", "-products", "*", "-requires",
                                     "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip()
    if not found:
        raise RuntimeError("REQUIRED_WINDOWS_C_COMPILER_UNAVAILABLE")
    vcvars = Path(found) / "VC/Auxiliary/Build/vcvars64.bat"
    executable = output / "fixture.exe"
    batch = output / "compile-fixture.cmd"
    batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                     f'cl /nologo /W4 /WX /MT /O2 /Fe:"{executable}" /Fo:"{output / "fixture.obj"}" "{HERE / "fixture_worker.c"}" advapi32.lib\n'
                     'exit /b %errorlevel%\n', encoding="utf-8")
    # Raw command line keeps cmd's outer quote pair intact. Passing the nested
    # quoted vcvars command through list2cmdline produced the retained first CI failure.
    built = subprocess.run(f'cmd.exe /d /s /c ""{batch}""', capture_output=True, text=True, timeout=120)
    (output / "compiler.log").write_text((built.stdout+built.stderr)[-64000:], encoding="utf-8")
    if built.returncode:
        raise RuntimeError("FIXTURE_COMPILATION_FAILED:" + (built.stdout+built.stderr)[-4000:])
    return executable


def startup_checkpoint():
    """Matched debug controls; failure blocks qualification, never becomes a skip."""
    rows = []
    variants = (("plain_unrestricted_console", False, False, False, True),
                ("granted_unrestricted_console", True, False, False, True),
                ("granted_restricted_console", True, True, False, True),
                ("granted_restricted_no_console", True, True, True, False))
    for name, granted, restricted, no_console, required in variants:
        row = {"variant": name, "restricted": restricted, "no_console": no_console,
               "required_positive_control": required, "control_passed": False,
               "inherited_handles": False if granted else "file-backed stdio only"}
        temporary = tempfile.TemporaryDirectory(prefix="tip057rq-checkpoint-")
        root = Path(temporary.name)
        executable = root / "fixture.exe"
        boundary = process = controller = None
        cleanup_errors = []
        try:
            shutil.copy2(EXECUTABLE, executable)
            windows = Windows()
            row["executable_security_before_boundary"] = windows.security_observation(executable)
            if granted:
                boundary = Boundary(root)
                windows = boundary.windows
            row["parent_token_before"] = windows.token_observation()
            row["root_security"] = windows.security_observation(root)
            row["executable_security"] = windows.security_observation(executable)
            if granted:
                row["label_applicability"] = directory_label_isolation(
                    row["root_security"], row["executable_security_before_boundary"], row["executable_security"])
            row["parent_write_before"] = windows.write_observation(root / "parent-before.json")
            if granted:
                process = boundary.spawn(executable, "write_probe", os.getpid(), restricted=restricted,
                                         no_console=no_console, inherit=False)
                ref = process.identity()
                row["worker"] = ref
                row["child_token_before_resume"] = windows.token_observation(process.handle)
                if not restricted:
                    row["unrestricted_token_matches_parent"] = row["child_token_before_resume"] == row["parent_token_before"]
                row["suspended_token_matches_fixture_role"] = (
                    row["child_token_before_resume"]["appcontainer"] == 1
                    and row["child_token_before_resume"]["integrity_sid"] == "S-1-16-4096"
                    if restricted else row["unrestricted_token_matches_parent"])
                process.resume()
                code = process.wait(5000)
                pid = ref["pid"]
            else:
                stdout_path, stderr_path = root / "stdout.log", root / "stderr.log"
                with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    controller = subprocess.Popen([str(executable), str(root), "write_probe", str(os.getpid()), "0"],
                                                  cwd=root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                                  close_fds=True)
                    code = wait_controller(controller, 5)
                pid = controller.pid
                row["stderr_tail"] = diagnostic_tail(stderr_path)
            row.update(exit_code=code, exit_code_hex=f"0x{code:08x}")
            row["writer_exit_diagnostic"] = writer_probe_exit(code, "write_probe")
            row["parent_token_after"] = windows.token_observation()
            row["parent_write_after"] = windows.write_observation(root / "parent-after.json")
            for filename, key in (("positive-marker.json", "marker"), ("fixture-diagnostic.json", "writer")):
                path = root / filename
                if path.exists():
                    if path.stat().st_size > 8192:
                        raise RuntimeError("CHECKPOINT_DIAGNOSTIC_LIMIT_EXCEEDED")
                    row[key] = json.loads(path.read_text(encoding="utf-8"))
            writer, marker = row.get("writer", {}), row.get("marker", {})
            parent_writes = all(value.get("create_error") == 0 and value.get("write_error") == 0
                                and value.get("written_bytes") == 3 and value.get("flush_error") == 0
                                for value in (row["parent_write_before"], row["parent_write_after"]))
            observed_token = row["child_token_before_resume"] if granted else row["parent_token_before"]
            integrity_matches_control = writer.get("integrity_rid") == int(observed_token["integrity_sid"].rsplit("-", 1)[1])
            row["control_passed"] = bool(code == 0 and marker.get("positive_marker") is True
                and marker.get("pid") == pid and writer.get("pid") == pid and writer.get("write_success") is True
                and writer.get("win32_error") == 0 and writer.get("token_error") == 0
                and writer.get("appcontainer") == int(restricted) and writer.get("policy_query_ok") == 1
                and writer.get("child_restricted") == int(restricted) and parent_writes and integrity_matches_control
                and (not granted or row["label_applicability"]["passed"])
                and (not granted or row["suspended_token_matches_fixture_role"])
                and "sddl" in row["root_security"] and "sddl" in row["executable_security"]
                and not row["root_security"]["selected_label_descriptor"].get("truncated", False)
                and not row["executable_security"]["selected_label_descriptor"].get("truncated", False))
        except BaseException as error:
            row["error"] = f"{type(error).__name__}:{str(error)[:2000]}"
        finally:
            if controller is not None:
                try:
                    stop_controller(controller)
                except BaseException as error:
                    cleanup_errors.append(f"CONTROLLER_STOP_UNPROVEN:{type(error).__name__}")
            if process is not None:
                try:
                    if not process.exited():
                        process.terminate_exact(process.identity())
                    row["exact_handle_exit"] = process.exited()
                except BaseException as error:
                    cleanup_errors.append(f"WORKER_STOP_UNPROVEN:{type(error).__name__}")
                finally:
                    try:
                        process.close()
                    except BaseException as error:
                        cleanup_errors.append(f"HANDLE_CLOSE_FAILED:{type(error).__name__}")
            if boundary is not None:
                try:
                    boundary.close()
                except BaseException as error:
                    cleanup_errors.append(f"PROFILE_CLEANUP_FAILED:{type(error).__name__}")
            try:
                temporary.cleanup()
            except BaseException as error:
                cleanup_errors.append(f"ROOT_CLEANUP_FAILED:{type(error).__name__}")
            row["cleanup_errors"] = cleanup_errors
            rows.append(row)
            record("startup_checkpoint", **row)
    passed = all(row["control_passed"] for row in rows if row["required_positive_control"])
    passed = passed and all(not row["cleanup_errors"] for row in rows)
    return {"required_controls_passed": passed, "variants": rows,
            "qualification": "STARTUP_AND_MARKER_ONLY_NO_CHILD_DENIAL_CLAIM"}


def crash_parent(root, executable):
    root = Path(root)
    atomic(root / "controller-phase.json", {"phase": "ENTERED", "pid": os.getpid()})
    copied = root / "fixture.exe"
    shutil.copy2(executable, copied)
    atomic(root / "controller-phase.json", {"phase": "BEFORE_BOUNDARY_SETUP", "pid": os.getpid()})
    boundary = Boundary(root)
    worker = None
    try:
        atomic(root / "profile.json", {"name": boundary.name})
        parent = Process(boundary.windows, boundary.windows.kernel.GetCurrentProcess()).identity()
        authority = FixtureAuthority(root / "authority")
        _, expected = authority.arm(parent)
        atomic(root / "controller-phase.json", {"phase": "BEFORE_CREATE", "pid": os.getpid()})
        worker = boundary.spawn(copied, "hang", parent["pid"],
                                before_create=lambda: authority.begin_create(expected))
        atomic(root / "controller-phase.json", {"phase": "BEFORE_LIVE_IDENTITY", "pid": os.getpid()})
        expected = authority.bind_worker(expected, worker.identity())
        atomic(root / "controller-phase.json", {"phase": "BOUND_BEFORE_RESUME", "pid": os.getpid(),
                                                "worker": expected["worker"]})
        worker.resume()
        wait_json(root / "started.json", process=worker, case="crash-parent-helper")
        atomic(root / "controller-phase.json", {"phase": "ABOUT_TO_CRASH", "pid": os.getpid(),
                                                "worker": expected["worker"]})
        # No shutdown/failure marker is recorded: intent survives this intentional crash.
        os._exit(73)
    except BaseException:
        cleanup_errors = []
        if worker is not None:
            try:
                worker.terminate_exact(worker.identity())
            except BaseException as error:
                cleanup_errors.append(f"OWNED_WORKER_UNPROVEN:{type(error).__name__}")
            finally:
                try:
                    worker.close()
                except BaseException as error:
                    cleanup_errors.append(f"OWNED_HANDLE_CLOSE_FAILED:{type(error).__name__}")
        try:
            boundary.close()
            atomic(root / "profile.json", {"name": boundary.name, "status": "DELETED"})
        except BaseException as error:
            cleanup_errors.append(f"OWNED_PROFILE_UNPROVEN:{type(error).__name__}")
        print(json.dumps({"crash_fixture_cleanup_errors": cleanup_errors}), file=sys.stderr)
        raise


def cap_proof_log(path, limit=64000):
    data = path.read_bytes()
    metadata = {"original_bytes": len(data), "original_sha256": hashlib.sha256(data).hexdigest(),
                "truncated": len(data) > limit}
    if len(data) > limit:
        header = b"[truncated; original size/hash retained in summary.json]\n"
        tail = data[-(limit-len(header)):]
        # Drop the first partial line so the retained UTF-8 tail remains valid.
        tail = tail.partition(b"\n")[2]
        path.write_bytes(header + tail)
    metadata["retained_bytes"] = path.stat().st_size
    return metadata


def bounded_summary(summary, limit=262144):
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    original = serialized.encode("utf-8")
    if len(original) <= limit:
        return serialized, False
    omitted = {"bytes": len(original), "sha256": hashlib.sha256(original).hexdigest(),
               "disposition": "OMITTED_OVERSIZE_EVIDENCE"}
    summary.update(status="FAIL", error="EVIDENCE_LIMIT_EXCEEDED", discarded_evidence=omitted, records=[])
    checkpoint = summary.get("startup_checkpoint")
    if checkpoint is not None:
        raw = json.dumps(checkpoint, indent=2, sort_keys=True).encode("utf-8")
        summary["startup_checkpoint"] = {"required_controls_passed": checkpoint.get("required_controls_passed"),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "disposition": "OMITTED_OVERSIZE_CHECKPOINT_NO_QUALIFICATION"}
    serialized = json.dumps(summary, indent=2, sort_keys=True)
    if len(serialized.encode("utf-8")) > limit:
        # Preserve bounded provenance even if unrelated metadata is unexpectedly huge.
        summary = {"schema": "tip057rq.proof/1", "status": "FAIL", "error": "EVIDENCE_LIMIT_EXCEEDED",
                   "candidate_sha": summary.get("candidate_sha", "")[:64],
                   "expected_head_sha": (summary.get("expected_head_sha") or "")[:64],
                   "exact_head_verified": summary.get("exact_head_verified") is True,
                   "discarded_evidence": omitted, "disposition": "MINIMAL_FAILURE_RECEIPT"}
        serialized = json.dumps(summary, indent=2, sort_keys=True)
    if len(serialized.encode("utf-8")) > limit:
        raise RuntimeError("FINAL_EVIDENCE_CAP_NOT_ENFORCED")
    return serialized, True


def attempt_arm(root):
    windows = Windows()
    parent = Process(windows, windows.kernel.GetCurrentProcess()).identity()
    try:
        FixtureAuthority(root).arm(parent)
        print(json.dumps({"status": "UNSAFE_ACQUIRE", "parent": parent}))
        return 1
    except RecoveryRequired:
        print(json.dumps({"status": "BLOCKED", "parent": parent}))
        return 0


def main():
    global EXECUTABLE
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--require-windows", action="store_true")
    parser.add_argument("--output", default="tip057rq-evidence")
    parser.add_argument("--crash-parent")
    parser.add_argument("--attempt-arm")
    parser.add_argument("--executable")
    options = parser.parse_args()
    if options.crash_parent:
        crash_parent(options.crash_parent, options.executable)
    if options.attempt_arm:
        return attempt_arm(options.attempt_arm)
    output = Path(options.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    expected_head = os.environ.get("TIP057RQ_EXPECTED_SHA")
    summary = {"schema": "tip057rq.proof/1", "os": platform.platform(), "python": sys.version,
               "candidate_sha": actual_head, "expected_head_sha": expected_head,
               "exact_head_verified": expected_head is not None and actual_head == expected_head,
               "github_event_sha": os.environ.get("GITHUB_SHA"),
               "base_sha": "70e2112da9fe8eaa6262f2ba896b55bf3e078260",
               "mode": "PORTABLE_UNQUALIFIED" if options.portable else "REAL_WINDOWS_REQUIRED",
               "broker_sdk": "OPEN", "scope": "isolated harmless fixture paths only",
               "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.glob("*")) if p.is_file()}}
    exit_code = 1
    try:
        if not options.portable and os.name != "nt":
            raise RuntimeError("REAL_WINDOWS_REQUIRED_NO_SKIP")
        if expected_head is not None and actual_head != expected_head:
            raise RuntimeError("REVIEWED_HEAD_MISMATCH")
        if os.environ.get("GITHUB_ACTIONS") == "true" and expected_head is None:
            raise RuntimeError("REVIEWED_HEAD_REQUIRED")
        if expected_head is not None:
            blob_sources = {}
            for source in sorted(HERE.glob("*")):
                if source.is_file():
                    blob = subprocess.check_output(["git", "show", f"HEAD:{source.relative_to(ROOT).as_posix()}"], cwd=ROOT)
                    blob_sources[source.name] = hashlib.sha256(blob).hexdigest()
            summary["git_blob_sources"] = blob_sources
            if blob_sources != summary["sources"]:
                raise RuntimeError("CHECKOUT_SOURCE_BYTES_MISMATCH")
            summary["source_blob_verified"] = True
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PortableCases)
        if not options.portable:
            EXECUTABLE = compile_fixture(output)
            summary["fixture_exe_sha256"] = hashlib.sha256(EXECUTABLE.read_bytes()).hexdigest()
            summary["startup_checkpoint"] = startup_checkpoint()
            (output / "proof.log").write_text(json.dumps(summary["startup_checkpoint"], indent=2), encoding="utf-8")
            summary["proof_log"] = cap_proof_log(output / "proof.log")
            if not summary["startup_checkpoint"]["required_controls_passed"]:
                summary.update(tests_run=0, failures=0, errors=0, skips=0, full_suite_attempted=False)
                raise RuntimeError("WINDOWS_STARTUP_CHECKPOINT_BLOCKED")
            summary["full_suite_attempted"] = True
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(WindowsCases))
        with (output / "proof.log").open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
        summary["proof_log"] = cap_proof_log(output / "proof.log")
        summary.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped))
        exit_code = 0 if result.wasSuccessful() and not result.skipped else 1
        summary["status"] = "PORTABLE_PASS_WINDOWS_UNQUALIFIED" if options.portable and not exit_code else "FIXTURE_PASS_Q03_OPEN" if not exit_code else "FAIL"
    except BaseException as error:
        summary.update(status="BLOCKED", error_type=type(error).__name__, error=str(error)[-4000:])
    finally:
        summary["elapsed_ms"] = (time.monotonic()-started)*1000
        summary["records"] = EVIDENCE
        serialized, overflow = bounded_summary(summary)
        if overflow:
            exit_code = 1
        # Write exact capped UTF-8 bytes; Windows newline translation cannot add bytes.
        (output / "summary.json").write_bytes(serialized.encode("utf-8"))
        print(json.dumps({key: value for key, value in json.loads(serialized).items() if key != "records"}, indent=2))
        if (output / "proof.log").exists():
            print((output / "proof.log").read_text(encoding="utf-8")[-64000:])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
