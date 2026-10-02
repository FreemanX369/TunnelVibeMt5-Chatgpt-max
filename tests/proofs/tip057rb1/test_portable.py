"""S01-S04/S09 synthetic evidence only; no SDK, IPC or Windows qualification."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROOF = Path(__file__).resolve().parent
sys.path.insert(0, str(PROOF))
import read_protocol as protocol
from sdk_worker import _observe_once_for_later_q2

SYNTHETIC = "SYNTHETIC_SDK_ONLY"
SECRET = "fixture-secret-should-never-be-output"


def request(root, budget=10000):
    executable = str((root / "terminal64.exe").resolve())
    return {"schema": protocol.REQUEST_SCHEMA, "operation": "state", "nonce": "a" * 32,
            "budget_ms": budget, "binding": {"executable": executable,
                "data_root": str((root / "data").resolve()),
                "process": {"pid": 1234, "creation": "123456789", "image": executable}}}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, milliseconds):
        self.now += milliseconds / 1000


class SyntheticSDK:
    """A harmless Python object; methods cannot attach to a terminal."""
    def __init__(self, req, events):
        self.events, self.effects = events, {}
        self.terminal = SimpleNamespace(path=str(Path(req["binding"]["executable"]).parent),
            data_path=req["binding"]["data_root"], connected=True, build=6182,
            ping_last=24500, trade_allowed=True)
        self.account = SimpleNamespace(login=987654321, server="Fixture-Server", currency="USD",
            balance=100.0, equity=101.0, margin_free=101.0, trade_allowed=False,
            trade_expert=False, leverage=100)
        self.initialized = True
        self.initialize_args = None
        self.positions, self.orders = 2, 3

    def call(self, name, value=None):
        self.events.append(name)
        effect = self.effects.get(name)
        if isinstance(effect, BaseException):
            raise effect
        if effect:
            effect()
        return value

    def initialize(self, path, *, timeout):
        self.initialize_args = (path, timeout)
        return self.call("initialize", self.initialized)

    def terminal_info(self):
        return self.call("terminal_info", self.terminal)

    def account_info(self):
        return self.call("account_info", self.account)

    def positions_total(self):
        return self.call("positions_total", self.positions)

    def orders_total(self):
        return self.call("orders_total", self.orders)

    def shutdown(self):
        return self.call("shutdown")


class PortableSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.req = request(self.root)
        self.events, self.clock = [], Clock()
        self.sdk = SyntheticSDK(self.req, self.events)

    def observer(self):
        self.events.append("process")
        return copy.deepcopy(self.req["binding"]["process"])

    def load(self):
        self.events.append("loader")
        return self.sdk

    def observe(self, req=None, observer=None, loader=None):
        return _observe_once_for_later_q2(req if req is not None else self.req,
            sdk_loader=loader or self.load, process_observer=observer or self.observer,
            evidence=SYNTHETIC, clock=self.clock)

    def failed(self, value, reason, primary=None, cleanup="RETURNED"):
        self.assertEqual(value["status"], "FAILED")
        self.assertEqual(value["evidence"], SYNTHETIC)
        self.assertEqual(value["reason_code"], reason)
        self.assertEqual(value["primary_reason_code"], primary)
        self.assertEqual(value["cleanup"]["status"], cleanup)
        for key in ("terminal", "account", "observed_at_utc"):
            self.assertIsNone(value[key])
        self.assertNotIn(SECRET, protocol.canonical(value).decode())
        self.assertEqual(protocol.validate_result(value, self.req), value)

    def test_exact_request_rejects_credentials_before_loader_or_observer(self):
        for location in ("request", "binding", "process"):
            with self.subTest(location=location):
                bad = copy.deepcopy(self.req)
                target = bad if location == "request" else bad["binding"]
                if location == "process":
                    target = target["process"]
                target["password"] = SECRET
                with self.assertRaisesRegex(protocol.ProtocolError, "^PROTOCOL_INVALID$"):
                    self.observe(bad)
                self.assertEqual(self.events, [])

    def test_request_rejects_bad_version_operation_nonce_and_budget(self):
        cases = [("schema", []), ("schema", "sdk.read.request/2"), ("operation", {}),
                 ("operation", "order_send"), ("nonce", "A" * 32), ("nonce", []),
                 ("budget_ms", True), ("budget_ms", 0), ("budget_ms", 10001),
                 ("budget_ms", 1.0), ("budget_ms", "100")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(self.req)
                bad[field] = value
                with self.assertRaises(protocol.ProtocolError):
                    self.observe(bad)
                self.assertEqual(self.events, [])
        for budget in (1, 10000):
            self.assertEqual(protocol.validate_request(request(self.root, budget))["budget_ms"], budget)

    def test_request_rejects_unbound_paths_and_process_identity(self):
        for field, value in (("executable", "relative.exe"), ("data_root", "relative"),
                             ("data_root", str(self.root / "x" / "..")),
                             ("data_root", str(self.root) + "\n"), ("executable", []),
                             ("data_root", str(self.root / "\ud800")),
                             ("data_root", str(self.root / "\udcff"))):
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(self.req)
                bad["binding"][field] = value
                with self.assertRaises(protocol.ProtocolError):
                    self.observe(bad)
        for field, value in (("pid", True), ("pid", 0), ("pid", "1234"), ("creation", "0"),
                             ("creation", []), ("creation", "1" * 33),
                             ("image", str((self.root / "other.exe").resolve()))):
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(self.req)
                bad["binding"]["process"][field] = value
                with self.assertRaises(protocol.ProtocolError):
                    self.observe(bad)
        self.assertEqual(self.events, [])

    def test_bounded_reader_rejects_duplicate_json_nonfinite_and_bad_encoding(self):
        inputs = [b'{"budget_ms":1,"budget_ms":2}',
                  b'{"binding":{"process":{"pid":1,"pid":2}}}', b'{"x":NaN}',
                  b'{"x":Infinity}', b'\xff', b'{']
        for index, raw in enumerate(inputs):
            with self.subTest(raw=raw):
                source = self.root / str(index)
                source.write_bytes(raw)
                with self.assertRaisesRegex(protocol.ProtocolError, "^PROTOCOL_INVALID$"):
                    protocol.read_bounded(source)

    def test_bounded_reader_reads_only_limit_plus_one_and_rejects_oversize(self):
        source = self.root / "oversized.json"
        source.write_bytes(b" " * (protocol.MAX_BYTES + 100))
        original = Path.open
        sizes = []
        class Tracked:
            def __enter__(self):
                self.stream = original(source, "rb")
                return self
            def __exit__(self, *_):
                self.stream.close()
            def read(self, size):
                sizes.append(size)
                return self.stream.read(size)
        with patch.object(Path, "open", return_value=Tracked()):
            with self.assertRaises(protocol.ProtocolError):
                protocol.read_bounded(source)
        self.assertEqual(sizes, [protocol.MAX_BYTES + 1])

    def test_bounded_reader_normalizes_recursion_fault(self):
        source = self.root / "recursive.json"
        source.write_bytes(b"[" * 12000 + b"0" + b"]" * 12000)
        with self.assertRaises(protocol.ProtocolError):
            protocol.read_bounded(source)

    def test_bounded_writer_round_trip_and_no_overwrite(self):
        target = self.root / "request.json"
        protocol.write_bounded(target, self.req)
        self.assertEqual(protocol.read_bounded(target), self.req)
        before = target.read_bytes()
        with self.assertRaises(FileExistsError):
            protocol.write_bounded(target, {})
        self.assertEqual(target.read_bytes(), before)
        with self.assertRaises(protocol.ProtocolError):
            protocol.write_bounded(self.root / "too-big", {"x": "x" * protocol.MAX_BYTES})
        self.assertFalse((self.root / "too-big").exists())

    def test_success_uses_exact_initialize_path_and_reads_binding_before_account(self):
        value = self.observe()
        self.assertEqual(value["status"], "SUCCEEDED")
        self.assertEqual(value["evidence"], SYNTHETIC)
        self.assertEqual(self.sdk.initialize_args, (self.req["binding"]["executable"], 2000))
        self.assertEqual(self.events[:3], ["process", "loader", "process"])
        self.assertLess(self.events.index("terminal_info"), self.events.index("account_info"))
        self.assertIn("process", self.events[self.events.index("terminal_info") + 1:self.events.index("account_info")])
        self.assertEqual(self.events.count("initialize"), 1)
        self.assertEqual(self.events.count("shutdown"), 1)
        self.assertEqual(value["observed_binding"], self.req["binding"])
        self.assertEqual(value["account"]["login_masked"], "*****4321")
        self.assertEqual(value["terminal"]["ping_ms"], 24.5)
        self.assertEqual(value["account"]["positions_count"], 2)
        self.assertEqual(value["account"]["orders_count"], 3)

    def test_terminal_root_mismatch_never_reads_account_or_counts(self):
        for field in ("path", "data_path"):
            with self.subTest(field=field):
                setattr(self.sdk.terminal, field, str(self.root / "wrong"))
                self.failed(self.observe(), "LIVE_BINDING_MISMATCH")
                self.assertNotIn("account_info", self.events)
                self.assertNotIn("positions_total", self.events)
                self.assertNotIn("orders_total", self.events)
                self.assertEqual(self.events.count("shutdown"), 1)
                self.events.clear()
                self.sdk = SyntheticSDK(self.req, self.events)

    def test_process_mismatch_and_observer_fault_never_load_sdk(self):
        for observer, reason in ((lambda: {"pid": 999}, "LIVE_BINDING_MISMATCH"),
                                 (lambda: (_ for _ in ()).throw(OSError(SECRET)), "LIVE_PROCESS_UNAVAILABLE")):
            with self.subTest(reason=reason):
                self.failed(self.observe(observer=observer), reason, cleanup="NOT_ATTEMPTED")
                self.assertEqual(self.events, [])

    def test_process_change_after_observation_discards_account(self):
        def observer():
            actual = self.observer()
            if "orders_total" in self.events:
                actual["creation"] = "99999"
            return actual
        self.failed(self.observe(observer=observer), "LIVE_BINDING_MISMATCH")
        self.assertIn("account_info", self.events)
        self.assertEqual(self.events.count("shutdown"), 1)

    def test_disconnected_accounts_are_null_without_account_or_count_reads(self):
        for connected in (False, None):
            with self.subTest(connected=connected):
                self.sdk.terminal.connected = connected
                value = self.observe()
                self.assertEqual(value["status"], "SUCCEEDED")
                self.assertEqual(value["account"]["status"], "UNAVAILABLE_DISCONNECTED")
                self.assertTrue(all(v is None for k, v in value["account"].items() if k != "status"))
                self.assertIsNone(value["terminal"]["ping_ms"])
                self.assertNotIn("account_info", self.events)
                self.assertNotIn("positions_total", self.events)
                self.assertNotIn("orders_total", self.events)
                self.events.clear()

    def test_legacy_null_numeric_and_short_login_conversion(self):
        self.sdk.account.login = 7
        self.sdk.account.balance = float("nan")
        self.sdk.account.equity = float("inf")
        self.sdk.account.leverage = "invalid"
        self.sdk.terminal.ping_last = -1
        self.sdk.positions, self.sdk.orders = -1, None
        value = self.observe()
        self.assertEqual(value["status"], "SUCCEEDED")
        self.assertEqual(value["account"]["login_masked"], "*7")
        for field in ("balance", "equity", "leverage"):
            self.assertIsNone(value["account"][field])
        self.assertIsNone(value["terminal"]["ping_last_us"])
        self.assertIsNone(value["terminal"]["ping_ms"])
        self.assertIsNone(value["account"]["positions_count"])
        self.assertIsNone(value["account"]["orders_count"])

    def test_initialize_false_and_raised_always_shutdown_once(self):
        for raised in (False, True):
            with self.subTest(raised=raised):
                self.sdk.initialized = False
                if raised:
                    self.sdk.effects["initialize"] = RuntimeError(SECRET)
                self.failed(self.observe(), "LIVE_IPC_INITIALIZE_FAILED")
                self.assertEqual(self.events.count("initialize"), 1)
                self.assertEqual(self.events.count("shutdown"), 1)
                self.assertNotIn("terminal_info", self.events)
                self.events.clear()

    def test_each_observation_fault_is_sanitized_and_shutdown_once(self):
        for method in ("terminal_info", "account_info", "positions_total", "orders_total"):
            with self.subTest(method=method):
                self.sdk.effects = {method: RuntimeError(SECRET)}
                self.failed(self.observe(), "LIVE_OBSERVATION_UNAVAILABLE")
                self.assertEqual(self.events.count("shutdown"), 1)
                self.events.clear()

    def test_missing_terminal_or_connected_account_fail_without_account_output(self):
        self.sdk.terminal = None
        self.failed(self.observe(), "LIVE_OBSERVATION_UNAVAILABLE")
        self.sdk = SyntheticSDK(self.req, self.events)
        self.sdk.account = None
        self.failed(self.observe(), "LIVE_OBSERVATION_UNAVAILABLE")

    def test_shutdown_fault_overrides_success_and_preserves_observation_failure(self):
        for observation_fails in (False, True):
            with self.subTest(observation_fails=observation_fails):
                self.sdk.effects = {"shutdown": RuntimeError(SECRET)}
                if observation_fails:
                    self.sdk.effects["account_info"] = RuntimeError(SECRET)
                value = self.observe()
                primary = "LIVE_OBSERVATION_UNAVAILABLE" if observation_fails else None
                self.failed(value, "LIVE_CLEANUP_UNPROVEN", primary, cleanup="UNPROVEN")
                self.assertEqual(value["cleanup"]["reason_code"], "LIVE_CLEANUP_UNPROVEN")
                self.assertEqual(self.events.count("shutdown"), 1)
                self.events.clear()

    def test_loader_fault_has_no_shutdown_or_native_diagnostics(self):
        def loader():
            raise ImportError(SECRET)
        self.failed(self.observe(loader=loader), "LIVE_OBSERVATION_UNAVAILABLE", cleanup="NOT_ATTEMPTED")
        self.assertNotIn("shutdown", self.events)

    def test_initialize_and_shutdown_faults_preserve_first_failure(self):
        self.sdk.effects = {"initialize": RuntimeError(SECRET), "shutdown": OSError(SECRET)}
        self.failed(self.observe(), "LIVE_CLEANUP_UNPROVEN", "LIVE_IPC_INITIALIZE_FAILED", cleanup="UNPROVEN")
        self.assertEqual(self.events.count("initialize"), 1)
        self.assertEqual(self.events.count("shutdown"), 1)

    def test_false_initialize_overrun_preserves_first_failure(self):
        self.req["budget_ms"] = 100
        self.sdk.initialized = False
        self.sdk.effects["initialize"] = lambda: self.clock.advance(150)
        value = self.observe()
        self.failed(value, "LIVE_IPC_INITIALIZE_FAILED")
        self.assertTrue(value["timing_ms"]["expired"])
        self.assertAlmostEqual(value["timing_ms"]["total"], 150)
        self.assertEqual(self.sdk.initialize_args[1], 100)

    def test_successful_initialize_overrun_is_deadline_failure_with_cleanup(self):
        self.req["budget_ms"] = 100
        self.sdk.effects["initialize"] = lambda: self.clock.advance(150)
        value = self.observe()
        self.failed(value, "LIVE_DEADLINE_EXCEEDED")
        self.assertNotIn("terminal_info", self.events)
        self.assertTrue(value["timing_ms"]["expired"])

    def test_late_shutdown_expires_soft_budget_and_discards_output(self):
        self.req["budget_ms"] = 100
        self.sdk.effects["shutdown"] = lambda: self.clock.advance(150)
        value = self.observe()
        self.failed(value, "LIVE_DEADLINE_EXCEEDED")
        self.assertTrue(value["timing_ms"]["expired"])
        self.assertEqual(self.events.count("shutdown"), 1)

    def test_exact_budget_boundary_expires_and_observation_overrun_stops_counts(self):
        self.req["budget_ms"] = 100
        self.sdk.effects["account_info"] = lambda: self.clock.advance(100)
        value = self.observe()
        self.failed(value, "LIVE_DEADLINE_EXCEEDED")
        self.assertTrue(value["timing_ms"]["expired"])
        self.assertEqual(value["timing_ms"]["total"], 100)
        self.assertNotIn("positions_total", self.events)
        self.assertNotIn("orders_total", self.events)

    def test_loader_overrun_never_attempts_initialize(self):
        self.req["budget_ms"] = 100
        def loader():
            self.clock.advance(150)
            return self.load()
        value = self.observe(loader=loader)
        self.failed(value, "LIVE_DEADLINE_EXCEEDED", cleanup="NOT_ATTEMPTED")
        self.assertNotIn("initialize", self.events)
        self.assertNotIn("shutdown", self.events)

    def test_shutdown_exception_after_expiry_retains_deadline_primary(self):
        self.req["budget_ms"] = 100
        def late_fault():
            self.clock.advance(150)
            raise RuntimeError(SECRET)
        self.sdk.effects["shutdown"] = late_fault
        self.failed(self.observe(), "LIVE_CLEANUP_UNPROVEN", "LIVE_DEADLINE_EXCEEDED", cleanup="UNPROVEN")

    def test_malformed_sdk_fields_are_discarded_without_raw_account_data(self):
        for field, value in (("server", {"password": SECRET}), ("server", SECRET + "\n"),
                             ("currency", "x" * 257), ("login", "raw-login-" + SECRET)):
            with self.subTest(field=field):
                setattr(self.sdk.account, field, value)
                self.failed(self.observe(), "LIVE_OBSERVATION_UNAVAILABLE")
                self.sdk = SyntheticSDK(self.req, self.events)

    def test_result_rejects_wrong_binding_nonce_hash_fields_and_unhashable_enums(self):
        original = self.observe()
        cases = [("nonce", "b" * 32), ("request_sha256", "0" * 64), ("evidence", []),
                 ("status", {}), ("reason_code", []), ("primary_reason_code", {}),
                 ("operation", "login"), ("observed_binding", {}), ("observed_at_utc", []),
                 ("account", None), ("terminal", None)]
        for field, value in cases:
            with self.subTest(field=field):
                bad = copy.deepcopy(original)
                bad[field] = value
                with self.assertRaises(protocol.ProtocolError):
                    protocol.validate_result(bad, self.req)
        for operation in ("extra", "missing"):
            bad = copy.deepcopy(original)
            if operation == "extra":
                bad["password"] = SECRET
            else:
                del bad["cleanup"]
            with self.assertRaises(protocol.ProtocolError):
                protocol.validate_result(bad, self.req)

    def test_result_rejects_invalid_types_raw_login_and_nonfinite_numbers(self):
        original = self.observe()
        cases = [("terminal", "build", True), ("terminal", "connected", 1),
                 ("terminal", "ping_ms", "2"), ("terminal", "ping_ms", float("nan")),
                 ("account", "balance", True), ("account", "leverage", 1.0),
                 ("account", "login_masked", "987654321"), ("account", "server", {}),
                 ("account", "currency", "USD\n"), ("cleanup", "status", []),
                 ("terminal", "build", 10 ** 1000), ("account", "balance", 10 ** 1000),
                 ("timing_ms", "total", 10 ** 1000),
                 ("timing_ms", "total", float("inf")), ("timing_ms", "total", -1),
                 ("timing_ms", "expired", 0), ("timing_ms", "expired", True)]
        for group, field, value in cases:
            with self.subTest(group=group, field=field, value=value):
                bad = copy.deepcopy(original)
                bad[group][field] = value
                with self.assertRaises(protocol.ProtocolError):
                    protocol.validate_result(bad, self.req)
        failed = protocol.result(self.req, evidence=SYNTHETIC)
        failed["account"] = original["account"]
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_result(failed, self.req)

    def test_result_connected_state_cannot_claim_missing_or_disconnected_account(self):
        original = self.observe()
        for field, value in (("status", "UNAVAILABLE_DISCONNECTED"), ("present", False)):
            with self.subTest(field=field):
                bad = copy.deepcopy(original)
                bad["account"][field] = value
                with self.assertRaises(protocol.ProtocolError):
                    protocol.validate_result(bad, self.req)
        disconnected = copy.deepcopy(original)
        disconnected["terminal"]["connected"] = False
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_result(disconnected, self.req)

    def test_result_constructor_rejects_unhashable_reason_and_evidence(self):
        for evidence, reason in (([], "PROTOCOL_INVALID"), (SYNTHETIC, {}),
                                ("UNSUPPORTED", "PROTOCOL_INVALID"), (SYNTHETIC, SECRET)):
            with self.subTest(evidence=evidence, reason=reason):
                with self.assertRaisesRegex(protocol.ProtocolError, "^PROTOCOL_INVALID$"):
                    protocol.result(self.req, evidence=evidence, reason=reason)

    def test_actual_cli_denies_valid_and_invalid_requests_without_importing_sdk(self):
        sentinel = self.root / "sdk-imported"
        (self.root / "MetaTrader5.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(sentinel)) + ").touch()\n"
            "raise RuntimeError('SDK_IMPORT_MUST_NOT_HAPPEN')\n", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(self.root), PYTHONDONTWRITEBYTECODE="1")
        for case in ("valid", "credentials", "surrogate"):
            with self.subTest(case=case):
                valid = case == "valid"
                req = copy.deepcopy(self.req)
                if case == "credentials":
                    req["credentials"] = SECRET
                if case == "surrogate":
                    req["binding"]["data_root"] = str(self.root / "\ud800")
                source, target = self.root / f"input-{case}.json", self.root / f"output-{case}.json"
                source.write_text(json.dumps(req), encoding="utf-8")
                completed = subprocess.run([sys.executable, str(PROOF / "sdk_worker.py"), str(source), str(target)],
                    env=env, text=True, capture_output=True, timeout=10)
                self.assertEqual(completed.returncode, 2 if valid else 3, completed.stderr)
                self.assertEqual(completed.stdout + completed.stderr, "")
                self.assertFalse(sentinel.exists())
                if valid:
                    value = protocol.validate_result(protocol.read_bounded(target), self.req)
                    self.assertEqual(value["reason_code"], "LIVE_ATTACH_ONLY_UNPROVEN")
                    self.assertEqual(value["evidence"], "REAL_SDK_UNQUALIFIED")
                    self.assertEqual(value["cleanup"]["status"], "NOT_ATTEMPTED")
                else:
                    self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
