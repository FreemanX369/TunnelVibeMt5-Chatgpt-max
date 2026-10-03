"""B1 research build verification; SDK/MT5/Q2 are always NOT RUN here."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "tests/unit"), str(HERE)]
from ownership_fixture import install_closed
from vibemql5.core.concurrency import acquire_native_execution
from vibemql5.core.native_ownership import ObservedProcess, OwnershipAuthority, OwnershipBlocked
from vibemql5.core import native_ownership
from controller import StubSession, sdk_disposition_after_exit
from read_protocol import REQUEST_SCHEMA, read_bounded, result, write_bounded
from windows_adapter import BoundReadProcess, StubBoundary, compile_stub, STUB_SOURCE_SHA256
from windows_boundary import Windows, Process

ARTIFACT = None
RECORDS = []


def request_for(root):
    executable = str(Path(root).resolve() / "terminal64.exe")
    return {"schema": REQUEST_SCHEMA, "operation": "state", "nonce": os.urandom(16).hex(),
            "budget_ms": 1000, "binding": {"executable": executable,
                "data_root": str(Path(root).resolve() / "clean-data"),
                "process": {"pid": 202, "creation": "100", "image": executable}}}


class WindowsStubCases(unittest.TestCase):
    def setUp(self):
        if os.name != "nt":
            self.fail("REAL_WINDOWS_REQUIRED_NO_SKIP")
        self.temp = tempfile.TemporaryDirectory(prefix="tip057rb1-")
        self.root = Path(self.temp.name)
        self.authority = install_closed(self.root)
        self.request = request_for(self.root)
        self.seed = result(self.request, evidence="HARMLESS_NATIVE_STUB_ONLY")
        self.sessions = []

    def tearDown(self):
        failures = []
        for session in self.sessions:
            try: session.close_handles()
            except Exception as error: failures.append(type(error).__name__)
        try: self.temp.cleanup()
        except Exception as error: failures.append(type(error).__name__)
        if failures: self.fail("EXACT_FIXTURE_CLEANUP_UNPROVEN:" + ",".join(failures))

    def session(self, root=None):
        session = StubSession(root or self.root, ARTIFACT)
        self.sessions.append(session)
        return session

    def blocked(self, root=None):
        with self.assertRaises(OwnershipBlocked):
            acquire_native_execution(root or self.root, "B1-SUCCESSOR", kind="fixture", wait_seconds=0)

    def marker(self, root=None):
        return read_bounded((root or self.root) / "result.json.entered")

    def test_w01_matched_unrestricted_control_writes_protocol_and_native_token(self):
        for name, value in (("request.json", self.request), ("seed.json", self.seed)):
            write_bounded(self.root / name, value)
        boundary, process, observation, lease = None, None, None, None
        try:
            boundary = StubBoundary(self.root, ARTIFACT)
            parent = boundary.windows.token_observation()
            lease = acquire_native_execution(self.root, "B1-CONTROL", kind="fixture", wait_seconds=0)
            armed = self.authority.arm(lease)
            attempted = self.authority.create_attempt(armed)
            process = boundary.spawn_stub(self.root / "stub.exe", self.root / "request.json",
                self.root / "result.json", self.root / "seed.json", restricted=False)
            observation = ObservedProcess(process.lifetime()["pid"])
            process.verify_observation(observation)
            self.assertFalse((self.root / "result.json.entered").exists())
            bound = self.authority.bind_worker(attempted, observation)
            process.allow_resume(self.authority, bound, observation)
            self.assertEqual(process.restrictions["token"], parent)
            self.assertFalse(process.restrictions["no_child_creation"])
            process.resume()
            self.assertEqual(process.wait(5000), 0)
            self.assertEqual(read_bounded(self.root / "result.json"), self.seed)
            native = self.marker()
            self.assertEqual(native["pid"], observation.pid)
            self.assertEqual(native["appcontainer"], 0)
            self.assertEqual(native["child_policy_flags"], process.restrictions["child_policy_flags"])
            RECORDS.append({"case": self.id(), "control": "WORKING", "worker": observation.identity(),
                            "native": native, "restrictions": process.restrictions})
        finally:
            if process is not None:
                if not process.exited(): process.terminate_exact(process.identity())
                process.close()
            if observation is not None: observation.close()
            if lease is not None: lease.release()
            if boundary is not None: boundary.close()
        self.blocked()  # Unrestricted control cannot supply leaf boundary closure.

    def test_w02_restricted_roundtrip_binds_before_execution_and_fixture_only_closes(self):
        session = self.session()
        absent = []
        def observe(point, _session):
            if point in ("SUSPENDED_CREATE", "BOUND", "BEFORE_RESUME"):
                absent.append(not (self.root / "result.json.entered").exists())
        answer = session.run(self.request, self.seed, fault=observe)
        self.assertIsNone(answer["failure"])
        self.assertEqual(answer["result"], self.seed)
        self.assertEqual(absent, [True, True, True])
        self.assertEqual(answer["ordering"], ["LEASE", "ARMED", "CREATE_ATTEMPT", "SUSPENDED_CREATE", "BOUND", "BEFORE_RESUME", "RESUMED"])
        native = self.marker()
        self.assertEqual(native["pid"], answer["worker"]["pid"])
        self.assertEqual(native["appcontainer"], 1)
        self.assertEqual(native["child_policy_flags"], answer["restrictions"]["child_policy_flags"])
        self.assertTrue(native["child_policy_flags"] & 1)
        self.blocked()
        self.assertEqual(sdk_disposition_after_exit(self.authority, session.expected)["disposition"], "ACTIVE")
        session.close_harmless_fixture()
        successor = acquire_native_execution(self.root, "FIXTURE-CLEAN-SUCCESSOR", kind="fixture", wait_seconds=0)
        successor.release()
        RECORDS.append({"case": self.id(), "native": native, **answer})

    def test_w03_timeout_exact_termination_keeps_shared_authority_active(self):
        session = self.session()
        answer = session.run(self.request, self.seed, mode="hang", wait_ms=250)
        self.assertEqual(answer["failure"], "LIVE_DEADLINE_EXCEEDED")
        self.assertTrue(answer["exact_worker_exit"])
        self.assertEqual(answer["ownership"], "ACTIVE")
        self.assertTrue(session.observation.exited())
        self.assertEqual(self.marker()["pid"], session.observation.pid)
        self.blocked()
        with self.assertRaises(RuntimeError): session.close_harmless_fixture()
        RECORDS.append({"case": self.id(), **answer})

    def test_w04_missing_or_wrong_nonce_result_is_no_success_and_retains_active(self):
        for mode in ("noresult", "tampered_nonce"):
            with self.subTest(mode=mode):
                root = self.root / mode
                install_closed(root)
                session = self.session(root)
                def corrupt(point, _session):
                    if mode == "tampered_nonce" and point == "BEFORE_RESUME":
                        changed = {**self.seed, "nonce": "b" * 32}
                        (root / "seed.json").write_text(json.dumps(changed), encoding="utf-8")
                answer = session.run(self.request, self.seed,
                    mode="normal" if mode == "tampered_nonce" else "noresult", fault=corrupt)
                self.assertEqual(answer["failure"], "WORKER_RESULT_INVALID")
                self.assertIsNone(answer["result"])
                self.blocked(root)
                RECORDS.append({"case": self.id(), "mode": mode, **answer})

    def test_w05_bind_publication_fault_before_after_never_executes_and_retains_active(self):
        real = native_ownership._atomic_write_json
        for point in ("before", "after"):
            with self.subTest(point=point):
                root = self.root / point
                install_closed(root)
                session = self.session(root)
                def fail(path, value):
                    if value["phase"] == "BOUND":
                        if point == "after": real(path, value)
                        raise OSError("harmless Windows bind fault")
                    return real(path, value)
                with patch.object(native_ownership, "_atomic_write_json", side_effect=fail):
                    answer = session.run(self.request, self.seed)
                self.assertEqual(answer["failure"], "WORKER_START_UNPROVEN")
                self.assertTrue(answer["exact_worker_exit"])
                self.assertNotIn("RESUMED", answer["ordering"])
                self.assertFalse((root / "result.json.entered").exists())
                self.blocked(root)
                RECORDS.append({"case": self.id(), "fault": point, **answer})

    def test_w06_restriction_readback_failure_terminates_owned_creation_handle(self):
        captured = []
        def fail(_boundary, process):
            observation = ObservedProcess(process.lifetime()["pid"])
            observation.identity()
            captured.append(observation)
            raise OSError("harmless readback fault")
        try:
            with patch.object(StubBoundary, "_restriction_observation", side_effect=fail, autospec=True):
                answer = self.session().run(self.request, self.seed)
            self.assertEqual(len(captured), 1)
            self.assertTrue(captured[0].exited())
            self.assertFalse((self.root / "result.json.entered").exists())
            self.assertEqual(self.authority.load()["phase"], "CREATE_ATTEMPT")
            self.blocked()
            RECORDS.append({"case": self.id(), "cleanup": "EXACT_CREATE_RETURNED_HANDLE_EXIT", **answer})
        finally:
            for observation in captured: observation.close()

    def test_w07_wrong_creation_identity_cannot_bind_or_resume(self):
        class WrongIdentity(ObservedProcess):
            def identity(self):
                actual = super().identity()
                return {**actual, "creation": str(int(actual["creation"]) + 1)}
        answer = self.session().run(self.request, self.seed, observer_factory=WrongIdentity)
        self.assertEqual(answer["failure"], "WORKER_START_UNPROVEN")
        self.assertEqual(self.authority.load()["phase"], "CREATE_ATTEMPT")
        self.assertFalse((self.root / "result.json.entered").exists())
        self.assertTrue(answer["exact_worker_exit"])
        self.blocked()
        RECORDS.append({"case": self.id(), **answer})

    def test_w08_stub_bytes_changed_cannot_receive_leaf_closure(self):
        session = self.session()
        answer = session.run(self.request, self.seed)
        self.assertIsNone(answer["failure"])
        with (self.root / "stub.exe").open("ab") as stream: stream.write(b"changed fixture bytes")
        with self.assertRaisesRegex(RuntimeError, "HARMLESS_STUB_BYTES_CHANGED"):
            session.close_harmless_fixture()
        self.blocked()
        RECORDS.append({"case": self.id(), "changed_bytes": "REFUSED", **answer})

    def test_w09_actual_parent_crash_keeps_restarted_controller_blocked(self):
        # Subprocess has file-backed output and no pipe-reader join or inherited worker handles.
        root = self.root / "parent-crash"
        root.mkdir()
        with (self.root / "parent.log").open("wb") as log:
            parent = subprocess.Popen([sys.executable, str(HERE / "run_proof.py"), "--crash-parent", str(root)],
                                      stdout=log, stderr=log, stdin=subprocess.DEVNULL)
            try:
                self.assertEqual(parent.wait(timeout=55), 73)
            finally:
                if parent.poll() is None:
                    parent.kill(); parent.wait(timeout=10)
        receipt = read_bounded(root / "crash.json")
        observed = process = None
        try:
            restarted = OwnershipAuthority(root)
            self.assertEqual(restarted.load(), receipt["authority"])
            self.blocked(root)
            observed = ObservedProcess(receipt["authority"]["worker"]["pid"])
            self.assertEqual(observed.identity(), receipt["authority"]["worker"])
            self.assertFalse(observed.exited())
            windows = Windows()
            process = Process.open_expected(windows, receipt["created"])
            process.terminate_exact(process.identity())
            self.assertTrue(observed.exited())
            self.assertEqual(sdk_disposition_after_exit(restarted, receipt["authority"])["activation"], "UNAVAILABLE")
            self.blocked(root)
            RECORDS.append({"case": self.id(), "parent_exit": 73, "orphan_exact_exit": True,
                            "source_sha256": receipt["source_sha256"], "artifact_sha256": receipt["artifact_sha256"],
                            "authority": receipt["authority"]})
        finally:
            try:
                if process is None:
                    # Failed assertions still stop the known live fixture. Fresh
                    # already-dead refusal remains unqualified, never CLOSED.
                    process = Process.open_expected(Windows(), receipt["created"])
                try:
                    if not process.exited(): process.terminate_exact(process.identity())
                finally:
                    process.close()
            finally:
                try:
                    if observed is not None: observed.close()
                finally:
                    code = Windows().userenv.DeleteAppContainerProfile(receipt["profile"])
                    self.assertGreaterEqual(code, 0, "EXACT_CRASH_FIXTURE_PROFILE_CLEANUP_FAILED")

    def test_w10_resume_failure_before_and_after_effect_keeps_active(self):
        real_resume = BoundReadProcess.resume
        for point in ("before", "after"):
            with self.subTest(point=point):
                root = self.root / ("resume-" + point)
                install_closed(root)
                session = self.session(root)
                def fail(process):
                    if point == "after":
                        real_resume(process)
                        deadline = time.monotonic() + 2
                        while not (root / "result.json.entered").exists():
                            if time.monotonic() >= deadline: raise RuntimeError("NATIVE_STUB_ENTRY_UNAVAILABLE")
                            time.sleep(.005)
                    raise OSError("harmless resume uncertainty")
                with patch.object(BoundReadProcess, "resume", side_effect=fail, autospec=True):
                    answer = session.run(self.request, self.seed, mode="hang")
                self.assertEqual(answer["failure"], "WORKER_START_UNPROVEN")
                self.assertTrue(answer["exact_worker_exit"])
                self.assertEqual(OwnershipAuthority(root).load()["phase"], "BOUND")
                self.assertEqual((root / "result.json.entered").exists(), point == "after")
                self.blocked(root)
                RECORDS.append({"case": self.id(), "resume_fault": point, **answer})


def crash_parent(root):
    install_closed(root)
    compile_root = root / "compile"
    compile_root.mkdir()
    artifact = compile_stub(compile_root)
    request = request_for(root)
    seed = result(request, evidence="HARMLESS_NATIVE_STUB_ONLY")
    session = StubSession(root, artifact)
    def crash(point, current):
        if point == "RESUMED":
            write_bounded(root / "crash.json", {"authority": current.expected,
                "created": current.process.identity(), "profile": current.boundary.name,
                "source_sha256": artifact.source_sha256, "artifact_sha256": artifact.sha256})
            os._exit(73)
    session.run(request, seed, mode="hang", fault=crash)
    session.close_handles()
    return 3


def source_receipt():
    paths = [str(path.relative_to(ROOT)).replace("\\", "/") for path in HERE.glob("*") if path.is_file()]
    paths += ["app/vibemql5/core/native_ownership.py", "app/vibemql5/core/concurrency.py",
              "app/vibemql5/core/live_terminal.py", "tests/proofs/tip057rq/windows_boundary.py",
              "tests/proofs/tip057rq/run_proof.py", "tests/proofs/tip057rq/fixture_worker.c",
              ".github/workflows/verify-tip057rb1.yml"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    expected = os.environ.get("TIP057RB1_EXPECTED_SHA")
    if expected is not None and head != expected:
        raise RuntimeError("EXACT_HEAD_MISMATCH")
    hashes = {}
    for relative in sorted(paths):
        path = ROOT / relative
        raw = path.read_bytes()
        actual_blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if expected is not None:
            committed = subprocess.check_output(["git", "rev-parse", f"HEAD:{relative}"], cwd=ROOT, text=True).strip()
            if actual_blob != committed: raise RuntimeError("EXECUTED_SOURCE_BLOB_MISMATCH")
        hashes[relative] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "git_blob": actual_blob}
    return {"head": head, "exact_head_required": expected is not None, "files": hashes}


def main():
    global ARTIFACT
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--require-windows", action="store_true")
    parser.add_argument("--crash-parent", type=Path)
    parser.add_argument("--output", type=Path, default=Path("tip057rb1-evidence"))
    args = parser.parse_args()
    if args.crash_parent is not None:
        if os.name != "nt": return 2
        return crash_parent(args.crash_parent.resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {"scope": "B1_RESEARCH_SOURCE_HARMLESS_STUB_ONLY", "sdk": "NOT_RUN_Q2_OPEN",
               "python_appcontainer_dll_ipc": "NOT_RUN", "production_activation": "UNAVAILABLE",
               "platform": platform.platform(), "python": sys.version, "records": RECORDS,
               "executed": 0, "failures": 0, "errors": 0, "skipped": 0}
    code = 1
    try:
        summary["source"] = source_receipt()
        if args.require_windows and os.name != "nt":
            summary["status"] = "BLOCKED_REAL_WINDOWS_REQUIRED_NO_SKIP"
            code = 2
        else:
            suite = unittest.TestSuite()
            if args.portable or not args.require_windows:
                for name in ("test_portable", "test_controller"):
                    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
            if args.require_windows:
                ARTIFACT = compile_stub(output)
                summary["artifact"] = {"source_sha256": STUB_SOURCE_SHA256, "sha256": ARTIFACT.sha256}
                suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(WindowsStubCases))
            with (output / "proof.log").open("w", encoding="utf-8") as stream:
                tested = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            summary.update(executed=tested.testsRun, failures=len(tested.failures), errors=len(tested.errors), skipped=len(tested.skipped))
            required_count = 10 if args.require_windows else 39
            summary["required_count"] = required_count
            passed = tested.wasSuccessful() and not tested.skipped and tested.testsRun == required_count
            summary["status"] = "PASS_HARMLESS_WINDOWS_STUB_ONLY" if args.require_windows and passed else "PASS_SYNTHETIC_PORTABLE_ONLY" if passed else "FAIL"
            code = 0 if passed else 1
    except Exception as error:
        summary.update(status="BLOCKED", diagnostic_code=type(error).__name__)
    log_path = output / "proof.log"
    if log_path.exists():
        raw_log = log_path.read_bytes()
        summary["proof_log"] = {"bytes": len(raw_log), "sha256": hashlib.sha256(raw_log).hexdigest(),
                                "cap": 65536, "truncated": len(raw_log) > 65536}
        if len(raw_log) > 65536:
            log_path.write_bytes(raw_log[-65536:])
            summary["status"] = "FAIL_EVIDENCE_CAP"
            code = 1
    raw = json.dumps(summary, indent=2).encode("utf-8")
    if len(raw) > 131072:
        summary["status"] = "FAIL_EVIDENCE_CAP"
        raw = json.dumps({"status": "FAIL_EVIDENCE_CAP", "sdk": "NOT_RUN_Q2_OPEN"}).encode()
        code = 1
    (output / "summary.json").write_bytes(raw)
    print(json.dumps({key: summary.get(key) for key in ("status", "executed", "failures", "errors", "skipped", "sdk")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
