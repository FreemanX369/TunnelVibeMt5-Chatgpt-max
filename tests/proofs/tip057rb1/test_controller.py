"""Synthetic portable fault adapters; not actual Windows/process qualification."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "tests/unit")]
from ownership_fixture import install_closed
from vibemql5.core.concurrency import acquire_native_execution
from vibemql5.core.native_ownership import ObservedProcess, OwnershipAuthority, OwnershipBlocked
from vibemql5.core import native_ownership
from controller import StubSession, sdk_disposition_after_exit
from read_protocol import REQUEST_SCHEMA, ProtocolError, read_bounded, result, write_bounded


class SyntheticObservation(ObservedProcess):
    def __init__(self, pid):
        self.pid = pid
    def identity(self):
        return {"pid": self.pid, "creation": "100", "image": str(Path(tempfile.gettempdir()) / "synthetic-stub.exe")}
    def exited(self):
        return True
    def close(self):
        pass


class SyntheticProcess:
    restrictions = {"no_child_creation": True, "token": {"appcontainer": 1},
                    "source": "SYNTHETIC_CONTROLLER_FAULT_ONLY"}
    resumed = False
    def __init__(self, root, output, seed):
        self.root, self.output, self.seed = root, output, seed
    def lifetime(self):
        return {"pid": 101, "creation_100ns": 100}
    def identity(self):
        return {**self.lifetime(), "image": str(Path(tempfile.gettempdir()) / "synthetic-stub.exe")}
    def verify_observation(self, observation, **kwargs):
        pass
    def allow_resume(self, *args):
        pass
    def resume(self):
        self.resumed = True
        write_bounded(self.output, read_bounded(self.seed))
    def exited(self):
        return self.resumed
    def wait(self, *_args):
        return 0
    def terminate_exact(self, expected):
        self.resumed = True
    def close(self):
        pass


class SyntheticBoundary:
    def __init__(self, root, _artifact):
        self.root = root
    def spawn_stub(self, executable, request, output, seed, **kwargs):
        return SyntheticProcess(self.root, output, seed)
    def assert_harmless_artifact(self):
        raise RuntimeError("SYNTHETIC_ADAPTER_CANNOT_QUALIFY_LEAF")
    def close(self):
        pass


class ControllerFaultCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b1-synthetic-fault-")
        self.root = Path(self.temp.name)
        self.authority = install_closed(self.root)
        executable = str(self.root / "terminal64.exe")
        self.request = {"schema": REQUEST_SCHEMA, "operation": "state", "nonce": "a" * 32,
            "budget_ms": 1000, "binding": {"executable": executable, "data_root": str(self.root / "data"),
                                         "process": {"pid": 202, "creation": "2", "image": executable}}}
        self.seed = result(self.request, evidence="HARMLESS_NATIVE_STUB_ONLY")
    def tearDown(self):
        self.temp.cleanup()

    def run_stub(self, session, **kwargs):
        # Synthetic liveness is True only until bind so production API order can run.
        class BindableObservation(SyntheticObservation):
            def exited(self):
                return False
        return session.run(self.request, self.seed, boundary_factory=SyntheticBoundary,
                           observer_factory=BindableObservation, **kwargs)

    def successor_blocked(self):
        with self.assertRaises(OwnershipBlocked):
            acquire_native_execution(self.root, "synthetic-successor", kind="fixture", wait_seconds=0)

    def test_arm_publication_refusal_has_zero_create_and_retains_uncertainty(self):
        with patch.object(native_ownership, "_atomic_write_json", side_effect=OSError("synthetic")):
            with StubSession(self.root) as session:
                answer = self.run_stub(session)
                self.assertIsNone(session.process)
        self.assertEqual(answer["failure"], "WORKER_START_UNPROVEN")
        self.assertEqual(answer["ordering"], ["LEASE"])
        self.assertEqual(self.authority.load()["disposition"], "CLOSED")

    def test_attempt_publication_fault_before_and_after_retains_active_zero_resume(self):
        for point in ("before", "after"):
            with self.subTest(point=point):
                temp = tempfile.TemporaryDirectory()
                root = Path(temp.name)
                install_closed(root)
                real = native_ownership._atomic_write_json
                def fail(path, value):
                    if value["phase"] == "CREATE_ATTEMPT":
                        if point == "after": real(path, value)
                        raise OSError("synthetic publication")
                    return real(path, value)
                with patch.object(native_ownership, "_atomic_write_json", side_effect=fail):
                    with StubSession(root) as session:
                        self.run_stub(session)
                        self.assertIsNone(session.process)
                self.assertEqual(OwnershipAuthority(root).load()["disposition"], "ACTIVE")
                temp.cleanup()

    def test_interruption_after_each_durable_boundary_survives_new_authority(self):
        for point in ("ARMED", "CREATE_ATTEMPT", "SUSPENDED_CREATE", "BOUND", "BEFORE_RESUME", "RESUMED"):
            with self.subTest(point=point):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    install_closed(root)
                    def fail(name, _session):
                        if name == point: raise OSError("synthetic interruption")
                    with StubSession(root) as session:
                        answer = self.run_stub(session, fault=fail)
                    self.assertEqual(answer["ownership"], "ACTIVE")
                    self.assertEqual(OwnershipAuthority(root).load()["disposition"], "ACTIVE")
                    with self.assertRaises(OwnershipBlocked):
                        acquire_native_execution(root, "restart", kind="fixture", wait_seconds=0)

    def test_bind_publication_fault_keeps_active_and_never_resumes(self):
        real = native_ownership._atomic_write_json
        def fail(path, value):
            if value["phase"] == "BOUND": raise OSError("synthetic bind")
            return real(path, value)
        with patch.object(native_ownership, "_atomic_write_json", side_effect=fail):
            with StubSession(self.root) as session:
                answer = self.run_stub(session)
                self.assertNotIn("RESUMED", answer["ordering"])
        self.assertEqual(self.authority.load()["phase"], "CREATE_ATTEMPT")
        self.successor_blocked()

    def test_sdk_result_label_cannot_select_leaf_closure(self):
        self.seed["evidence"] = "REAL_SDK_UNQUALIFIED"
        with StubSession(self.root) as session:
            with self.assertRaises(ProtocolError): self.run_stub(session)
            self.assertIsNone(session.process)
        self.assertEqual(self.authority.load()["disposition"], "CLOSED")

    def test_worker_exit_and_shutdown_result_do_not_qualify_sdk(self):
        with StubSession(self.root) as session:
            self.run_stub(session)
            outcome = sdk_disposition_after_exit(self.authority, session.expected)
            self.assertEqual(outcome["disposition"], "ACTIVE")
            self.assertEqual(outcome["activation"], "UNAVAILABLE")
            with self.assertRaisesRegex(RuntimeError, "SYNTHETIC_ADAPTER"):
                session.close_harmless_fixture()
        self.successor_blocked()

    def test_stale_cas_cannot_be_sdk_disposition(self):
        with StubSession(self.root) as session:
            self.run_stub(session)
            stale = copy.deepcopy(session.expected)
            stale["generation"] += 1
            with self.assertRaisesRegex(RuntimeError, "STALE_SDK_AUTHORITY"):
                sdk_disposition_after_exit(self.authority, stale)
        self.successor_blocked()

    def test_invalid_request_is_zero_effect_and_no_files(self):
        self.request["budget_ms"] = True
        with StubSession(self.root) as session:
            with self.assertRaises(ProtocolError): self.run_stub(session)
        self.assertFalse((self.root / "request.json").exists())
        self.assertEqual(self.authority.load()["disposition"], "CLOSED")
