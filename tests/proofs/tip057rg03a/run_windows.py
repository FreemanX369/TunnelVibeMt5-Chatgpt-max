"""Required real Windows product identity/lifecycle evidence, never skipped PASS.

Uses only disposable Python leaf processes and source-only Q1 Win32 declarations.
No terminal, SDK, helper, AppContainer, account or production state is touched.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "tests/unit"), str(ROOT / "tests/proofs/tip057rq")]
from ownership_fixture import install_closed
from vibemql5.core.concurrency import acquire_native_execution
from vibemql5.core.jobs import _atomic_write_json
from vibemql5.core.native_ownership import ObservedProcess, OwnershipAuthority, OwnershipBlocked
from vibemql5.core import native_ownership as module
from windows_boundary import Windows, Process, STARTUPINFO, PROCESS_INFORMATION, require

RECORDS = []


class WindowsAuthorityCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tip057rg03a-")
        self.root = Path(self.temp.name)
        self.authority = install_closed(self.root)
        self.windows = Windows()
        self.processes, self.observations, self.leases = [], [], []

    def tearDown(self):
        failures = []
        for process in self.processes:
            try:
                if not process.exited(): process.terminate_exact(process.identity())
            except BaseException as error: failures.append(str(error))
            finally: process.close()
        for observation in self.observations: observation.close()
        for lease in self.leases:
            try: lease.release()
            except BaseException as error: failures.append(str(error))
        self.temp.cleanup()
        if failures: self.fail("OWNED_FIXTURE_CLEANUP_UNPROVEN:" + ";".join(failures))

    def intent(self):
        lease = acquire_native_execution(self.root, "WINDOWS-FIXTURE", kind="future_producer_fixture", wait_seconds=0)
        self.leases.append(lease)
        return lease, self.authority.arm(lease)

    def spawn_suspended(self, marker="entered.txt"):
        path = self.root / marker
        script = f"from pathlib import Path; import time; Path({str(path)!r}).write_text('entered'); time.sleep(30)"
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([sys.executable, "-c", script]))
        startup, info = STARTUPINFO(), PROCESS_INFORMATION()
        startup.cb = ctypes.sizeof(startup)
        require(self.windows.kernel.CreateProcessW(sys.executable, command, None, None, False,
            0x4, None, str(self.root), ctypes.byref(startup), ctypes.byref(info)))
        process = Process(self.windows, info.process, info.thread)
        # Observe with the independent product handle, never a journal reference.
        observation = ObservedProcess(int(info.pid))
        self.processes.append(process); self.observations.append(observation)
        return process, observation, path

    def test_a06_durable_arm_attempt_actual_suspended_bind_before_resume(self):
        lease, armed = self.intent()
        self.assertEqual(self.authority.load(), armed)
        attempted = self.authority.create_attempt(armed)
        self.assertEqual(self.authority.load()["phase"], "CREATE_ATTEMPT")
        process, observation, marker = self.spawn_suspended()
        self.assertFalse(marker.exists())
        expected = self.authority.bind_worker(attempted, observation)
        self.assertEqual(self.authority.load(), expected)
        self.assertFalse(marker.exists(), "actual suspended worker entered before durable bind")
        actual = observation.identity()
        self.assertEqual(actual["pid"], process.lifetime()["pid"])
        self.assertEqual(actual["creation"], str(process.lifetime()["creation_100ns"]))
        self.assertTrue(os.path.samefile(actual["image"], sys.executable))
        process.resume()
        deadline = time.monotonic() + 5
        while not marker.exists():
            self.assertLess(time.monotonic(), deadline, "fixture resume never entered")
            time.sleep(.01)
        with self.assertRaisesRegex(OwnershipBlocked, "EXACT_WORKER_EXIT_UNPROVEN"):
            self.authority.close_owned_worker(expected, observation,
                descendant_verifier=lambda _p: "PREVENTED_BY_BOUNDARY")
        process.terminate_exact(process.identity())
        self.assertTrue(observation.exited())
        self.assertEqual(observation.identity(), actual)
        # Positive callback is interface-contract fixture evidence only; it does not
        # qualify a production descendant boundary. No production verifier exists.
        closed = self.authority.close_owned_worker(expected, observation,
            descendant_verifier=lambda _p: "EXACT_DESCENDANTS_EXITED")
        self.assertEqual(closed["generation"], expected["generation"])
        lease.release()
        RECORDS.append({"case": self.id(), "worker": actual,
            "ordering": ["ARMED", "CREATE_ATTEMPT", "ACTUAL_SUSPENDED_CREATE", "BOUND", "RESUME", "EXACT_EXIT"],
            "descendant_evidence": "CONTRACT_FIXTURE_CALLBACK_ONLY_PRODUCTION_UNQUALIFIED"})

    def test_a06_actual_create_before_bind_interruption_stays_unknown(self):
        lease, armed = self.intent()
        attempted = self.authority.create_attempt(armed)
        process, observation, marker = self.spawn_suspended()
        # Simulates controller restart after actual create and before bind. No guessed
        # reference is written; even exact fixture cleanup does not clear unknown create.
        restarted = OwnershipAuthority(self.root)
        self.assertEqual(restarted.load(), attempted)
        self.assertIsNone(restarted.load()["worker"])
        with self.assertRaisesRegex(OwnershipBlocked, "CREATION_OUTCOME_UNKNOWN"):
            restarted.close_zero_attempt(attempted)
        process.terminate_exact(process.identity())
        lease.release()
        with self.assertRaisesRegex(OwnershipBlocked, "ACTIVE_RECOVERY_REQUIRED"):
            acquire_native_execution(self.root, "NO-SUCCESSOR", kind="fixture", wait_seconds=0)
        self.assertFalse(marker.exists())
        RECORDS.append({"case": self.id(), "unknown_create": "ACTIVE_WITHOUT_GUESSED_WORKER"})

    def test_a08_fresh_already_dead_handle_never_uses_expected_journal_image(self):
        lease, armed = self.intent()
        attempted = self.authority.create_attempt(armed)
        process, observation, _ = self.spawn_suspended()
        expected = self.authority.bind_worker(attempted, observation)
        observed_live = observation.identity()
        process.terminate_exact(process.identity())
        self.assertTrue(observation.exited())
        self.assertEqual(observation.identity(), observed_live)
        # The creation handle remains open, so a real already-dead open is possible.
        fresh = ObservedProcess(expected["worker"]["pid"])
        self.observations.append(fresh)
        self.assertTrue(fresh.exited())
        with self.assertRaisesRegex(OwnershipBlocked, "LIVE_IMAGE_NOT_CAPTURED_BEFORE_EXIT"):
            self.authority.close_owned_worker(expected, fresh,
                descendant_verifier=lambda _p: "EXACT_DESCENDANTS_EXITED")
        self.assertEqual(self.authority.load(), expected)
        lease.release()
        with self.assertRaises(OwnershipBlocked):
            acquire_native_execution(self.root, "AFTER-DEAD", kind="fixture", wait_seconds=0)
        RECORDS.append({"case": self.id(), "fresh_dead": "REFUSED_WITHOUT_INDEPENDENT_LIVE_IMAGE",
                        "retained_same_handle_exit": "PROVEN", "worker": observed_live})

    def test_a07_live_orphan_fresh_observation_and_stale_cas(self):
        lease, armed = self.intent()
        attempted = self.authority.create_attempt(armed)
        process, original, _ = self.spawn_suspended()
        expected = self.authority.bind_worker(attempted, original)
        original.close()
        fresh = ObservedProcess(expected["worker"]["pid"])
        self.observations.append(fresh)
        self.assertEqual(fresh.identity(), expected["worker"])
        process.terminate_exact(process.identity())
        changed = {**expected, "worker": {**expected["worker"], "creation": str(int(expected["worker"]["creation"]) + 1)}}
        with self.assertRaises(OwnershipBlocked):
            self.authority.close_owned_worker(changed, fresh,
                descendant_verifier=lambda _p: "EXACT_DESCENDANTS_EXITED")
        self.assertEqual(self.authority.load(), expected)
        self.authority.close_owned_worker(expected, fresh,
            descendant_verifier=lambda _p: "EXACT_DESCENDANTS_EXITED")
        lease.release()
        successor_lease, successor = self.intent()
        with self.assertRaisesRegex(OwnershipBlocked, "STALE_AUTHORITY_CAS"):
            self.authority.close_owned_worker(expected, fresh,
                descendant_verifier=lambda _p: "EXACT_DESCENDANTS_EXITED")
        self.assertEqual(self.authority.load(), successor)
        successor_lease.release()
        RECORDS.append({"case": self.id(), "fresh_live_identity": "INDEPENDENT_OS_OBSERVATION",
                        "stale_cas": "REJECTED", "successor_generation": successor["generation"]})

    def test_a06_descendant_unknown_boolean_unqualified_and_exception_stay_active(self):
        lease, armed = self.intent()
        attempted = self.authority.create_attempt(armed)
        process, observation, _ = self.spawn_suspended()
        expected = self.authority.bind_worker(attempted, observation)
        process.terminate_exact(process.identity())
        for disposition in ("UNKNOWN", True, False, "NONE", None, []):
            with self.subTest(disposition=disposition):
                with self.assertRaises(OwnershipBlocked):
                    self.authority.close_owned_worker(expected, observation,
                        descendant_verifier=lambda _p, result=disposition: result)
                self.assertEqual(self.authority.load(), expected)
        def unavailable(_process): raise OSError("fixture boundary proof unavailable")
        with self.assertRaises(OwnershipBlocked):
            self.authority.close_owned_worker(expected, observation, descendant_verifier=unavailable)
        self.assertEqual(self.authority.load(), expected)
        lease.release()
        RECORDS.append({"case": self.id(), "unqualified_descendants": "ALL_RETAIN_ACTIVE"})

    def test_a04_actual_live_reused_identity_active_lock_is_not_deleted(self):
        lease, expected = self.intent()
        lease.release()
        lock = self.root / "runs/.active.lock"
        owner = {"pid": os.getpid(), "token": "reused", "identity": {
            **expected["parent"], "creation": str(int(expected["parent"]["creation"]) + 1)}}
        _atomic_write_json(lock, owner)
        before = lock.read_bytes()
        with self.assertRaises(OwnershipBlocked):
            acquire_native_execution(self.root, "NO-DELETE", kind="fixture", wait_seconds=0)
        self.assertEqual(lock.read_bytes(), before)
        self.assertEqual(self.authority.load(), expected)
        # Valid CLOSED permits compatibility stale/PID-reused cleanup.
        self.authority.close_zero_attempt(expected)
        successor = acquire_native_execution(self.root, "CLOSED-REUSE", kind="fixture", wait_seconds=1)
        self.leases.append(successor)
        self.assertEqual(json.loads(lock.read_text())["token"], successor.token)
        RECORDS.append({"case": self.id(), "active_reused_owner": "LOCK_PRESERVED",
                        "closed_reused_owner": "COMPATIBLE_RECOVERY"})

    def test_a05_bind_publication_before_after_fault_stays_active(self):
        for index, point in enumerate(("before", "after")):
            with self.subTest(point=point):
                root = self.root / f"bind-{index}"
                authority = install_closed(root)
                lease = acquire_native_execution(root, "BIND-FAULT", kind="fixture", wait_seconds=0)
                self.leases.append(lease)
                attempted = authority.create_attempt(authority.arm(lease))
                process, observation, marker = self.spawn_suspended(f"bind-{index}-entered.txt")
                write = module._atomic_write_json
                def fault(path, state):
                    if point == "after": write(path, state)
                    raise OSError("controlled bind publication failure")
                with patch.object(module, "_atomic_write_json", fault):
                    with self.assertRaises(OwnershipBlocked): authority.bind_worker(attempted, observation)
                self.assertFalse(marker.exists())
                state = authority.load()
                self.assertEqual(state["disposition"], "ACTIVE")
                self.assertEqual(state["phase"], "CREATE_ATTEMPT" if point == "before" else "BOUND")
                process.terminate_exact(process.identity())
                lease.release()
                with self.assertRaises(OwnershipBlocked):
                    acquire_native_execution(root, "NO-SUCCESSOR", kind="fixture", wait_seconds=0)
                RECORDS.append({"case": self.id(), "window": point, "persistent_phase": state["phase"]})

    def test_a05_worker_closure_publication_fault_retains_barrier(self):
        for index, point in enumerate(("before", "after", "readback")):
            with self.subTest(point=point):
                root = self.root / f"close-{index}"
                authority = install_closed(root)
                lease = acquire_native_execution(root, "CLOSE-FAULT", kind="fixture", wait_seconds=0)
                self.leases.append(lease)
                attempted = authority.create_attempt(authority.arm(lease))
                process, observation, _ = self.spawn_suspended(f"close-{index}-entered.txt")
                expected = authority.bind_worker(attempted, observation)
                process.terminate_exact(process.identity())
                write, load = module._atomic_write_json, OwnershipAuthority.load
                pending = [True]
                def fault(path, state):
                    if state["disposition"] == "CLOSED":
                        if point == "after": write(path, state)
                        if point != "readback": raise OSError("controlled close publication failure")
                    write(path, state)
                def readback(instance):
                    state = load(instance)
                    if point == "readback" and state["disposition"] == "CLOSED" and pending[0]:
                        pending[0] = False
                        raise OwnershipBlocked("AUTHORITY_INVALID")
                    return state
                with patch.object(module, "_atomic_write_json", fault), patch.object(OwnershipAuthority, "load", readback):
                    with self.assertRaises(OwnershipBlocked):
                        authority.close_owned_worker(expected, observation,
                            descendant_verifier=lambda _p: "EXACT_DESCENDANTS_EXITED")
                self.assertEqual(authority.load(), expected)
                lease.release()
                with self.assertRaises(OwnershipBlocked):
                    acquire_native_execution(root, "NO-SUCCESSOR", kind="fixture", wait_seconds=0)
                RECORDS.append({"case": self.id(), "window": point, "persistent_phase": "ACTIVE_BOUND",
                                "descendant_evidence": "CONTRACT_FIXTURE_CALLBACK_ONLY_PRODUCTION_UNQUALIFIED"})


class NoSkipResult(unittest.TextTestResult):
    def addSkip(self, test, reason):
        self.addFailure(test, (AssertionError, AssertionError("REQUIRED_WINDOWS_CASE_SKIPPED:" + reason), None))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-windows", action="store_true", required=True)
    parser.add_argument("--output", default="tip057rg03a-evidence")
    options = parser.parse_args()
    output = Path(options.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    sources = [Path("app/vibemql5/core/native_ownership.py"), Path("app/vibemql5/core/concurrency.py"),
        Path("app/vibemql5/core/jobs.py"), Path("tests/unit/ownership_fixture.py"),
        Path("tests/unit/test_tip057rg03a_native_ownership.py"), Path("tests/proofs/tip057rg03a/run_windows.py"),
        Path("tests/proofs/tip057rq/windows_boundary.py"), Path(".github/workflows/verify-tip057rg03a.yml")]
    expected = os.environ.get("TIP057RG03A_EXPECTED_SHA")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    summary = {"schema": "tip057rg03a.windows/1", "status": "BLOCKED", "candidate_sha": head,
        "expected_head_sha": expected, "exact_head_verified": False, "os": platform.platform(),
        "python": sys.version, "tests_run": 0, "failures": 0, "errors": 0, "skips": 0,
        "sources": {p.as_posix(): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
        "sdk_helper": "ABSENT", "production_descendant_verifier": "OPEN", "records": RECORDS}
    code = 1
    try:
        if os.name != "nt": raise RuntimeError("REAL_WINDOWS_REQUIRED_NO_SKIP")
        if expected is None or head != expected: raise RuntimeError("REVIEWED_EXACT_HEAD_REQUIRED")
        blobs = {p.as_posix(): hashlib.sha256(subprocess.check_output(["git", "show", f"HEAD:{p.as_posix()}"], cwd=ROOT)).hexdigest() for p in sources}
        if blobs != summary["sources"]: raise RuntimeError("CHECKOUT_SOURCE_BYTES_MISMATCH")
        summary.update(exact_head_verified=True, source_blob_verified=True, git_blob_sources=blobs)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(WindowsAuthorityCases)
        with (output / "proof.log").open("w", encoding="utf-8") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=NoSkipResult).run(suite)
        summary.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped))
        if result.wasSuccessful() and result.testsRun == 8 and not result.skipped:
            code = 0; summary["status"] = "G03A_WINDOWS_FOUNDATION_PASS_PRODUCER_OPEN"
        else: summary["status"] = "FAIL"
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error=str(error)[-2000:])
        (output / "proof.log").write_text(summary["error"], encoding="utf-8")
    summary["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))
    print((output / "proof.log").read_text()[-16000:])
    return code


if __name__ == "__main__": raise SystemExit(main())
