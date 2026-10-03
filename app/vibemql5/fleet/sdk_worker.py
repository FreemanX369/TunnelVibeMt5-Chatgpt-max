"""Real SDK observation prepared for an operator-qualified isolated worker only."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# Fixed verified worker path determines the package root, never caller PYTHONPATH.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from vibemql5.core.live_terminal import LiveTerminal
from vibemql5.core.native_ownership import ObservedProcess
from vibemql5.fleet.sdk_protocol import ProtocolError, canonical, read_bounded, result, validate_request, validate_result, write_bounded


class ReadFailure(RuntimeError):
    pass


class ReadBudget:
    def __init__(self, milliseconds, clock):
        self.clock, self.started, self.limit = clock, clock(), milliseconds / 1000

    def expired(self):
        return self.clock() - self.started >= self.limit

    def check(self):
        if self.expired():
            raise ReadFailure("LIVE_DEADLINE_EXCEEDED")

    def initialize_timeout(self):
        remaining = int((self.limit - (self.clock() - self.started)) * 1000)
        if remaining <= 0:
            raise ReadFailure("LIVE_DEADLINE_EXCEEDED")
        return min(2000, remaining)


def observe_once(request, *, installation=None, sdk_loader=None, process_observer=None,
                               evidence="REAL_SDK_UNQUALIFIED", clock=time.monotonic):
    """Actual SDK implementation; injected adapters always carry synthetic evidence."""
    if sdk_loader is not None or process_observer is not None:
        evidence = "SYNTHETIC_SDK_ONLY"
    request = json.loads(canonical(validate_request(request)))  # Frozen before the loader or observer can run.
    if sdk_loader is None and process_observer is None:
        from vibemql5.fleet.sdk_qualification import QualifiedSdkInstallation, QualificationError
        if type(installation) is not QualifiedSdkInstallation:
            raise QualificationError()
        installation.assert_worker(request)
        from vibemql5.core.isolated_sdk import current_restrictions
        installation.assert_restrictions(current_restrictions())
        evidence = "REAL_SDK_OPERATOR_APPROVED"
    elif sdk_loader is None or process_observer is None:
        raise ProtocolError()  # A synthetic test never falls through to a real SDK/probe.
    answer = result(request, evidence=evidence)
    budget = ReadBudget(request["budget_ms"], clock)
    binding = request["binding"]
    observed_handle = None
    attempted, sdk, primary, cleanup_reason, payload = False, None, None, None, None
    try:
        budget.check()
        if process_observer is None:
            observed_handle = ObservedProcess(binding["process"]["pid"])
            def process_observer():
                if observed_handle.exited():
                    raise ReadFailure("TERMINAL_NOT_RUNNING")
                return observed_handle.identity()

        def verify_process():
            budget.check()
            try:
                actual = process_observer()
            except ReadFailure:
                raise
            except Exception as error:
                raise ReadFailure("LIVE_PROCESS_UNAVAILABLE") from error
            if actual != binding["process"]:
                raise ReadFailure("LIVE_BINDING_MISMATCH")
            return actual

        verify_process()
        sdk = sdk_loader() if sdk_loader is not None else _load_approved_sdk(installation)
        budget.check()

        class Inventory:
            @staticmethod
            def _norm(value):
                return os.path.normcase(os.path.realpath(value))

            @staticmethod
            def get(_alias):
                return SimpleNamespace(terminal_path=binding["executable"], data_root=binding["data_root"])

            @staticmethod
            def is_running(_alias):
                verify_process()
                return True

        class SDK:
            def initialize(self, path, *, timeout):
                nonlocal attempted
                if path != binding["executable"]:
                    raise ReadFailure("LIVE_BINDING_MISMATCH")
                timeout = budget.initialize_timeout()
                attempted = True  # A raised/false initialize still enters shutdown scope.
                try:
                    initialized = sdk.initialize(path, timeout=timeout)
                except Exception as error:
                    raise ReadFailure("LIVE_IPC_INITIALIZE_FAILED") from error
                if not initialized:
                    raise ReadFailure("LIVE_IPC_INITIALIZE_FAILED")
                budget.check()
                return initialized

            def __getattr__(self, method):
                if method not in {"terminal_info", "account_info", "positions_total", "orders_total"}:
                    raise ReadFailure("LIVE_OBSERVATION_UNAVAILABLE")
                def call():
                    budget.check()
                    try:
                        value = getattr(sdk, method)()
                    except Exception as error:
                        raise ReadFailure("LIVE_OBSERVATION_UNAVAILABLE") from error
                    budget.check()
                    return value
                return call

            def shutdown(self):
                # LiveTerminal owns a finally, but outer finally owns actual shutdown
                # including initialize false/raise. Never execute shutdown twice.
                pass

        payload = LiveTerminal(Inventory(), binding["alias"], mt5=SDK()).state()
        verify_process()
        answer["observed_binding"] = {**binding, "process": verify_process()}
    except ReadFailure as error:
        primary = str(error)
    except Exception as error:
        # Never echo SDK native diagnostics, credentials or exception text.
        old = str(error)
        primary = {"MT5_LIVE_IPC_INITIALIZE_FAILED": "LIVE_IPC_INITIALIZE_FAILED",
                   "MT5_LIVE_TERMINAL_BINDING_MISMATCH": "LIVE_BINDING_MISMATCH",
                   "FIXED_TERMINAL_NOT_RUNNING": "TERMINAL_NOT_RUNNING"}.get(old, "LIVE_OBSERVATION_UNAVAILABLE")
    finally:
        if attempted:
            try:
                sdk.shutdown()  # Normal documented return None is allowed.
                # RETURNED proves only this call returned; no IPC/descendant closure.
                answer["cleanup"] = {"status": "RETURNED", "reason_code": None}
            except Exception:
                cleanup_reason = "LIVE_CLEANUP_UNPROVEN"
                answer["cleanup"] = {"status": "UNPROVEN", "reason_code": cleanup_reason}
        if observed_handle is not None:
            try:
                observed_handle.close()
            except Exception:
                cleanup_reason = "LIVE_CLEANUP_UNPROVEN"
                answer["cleanup"] = {"status": "UNPROVEN", "reason_code": cleanup_reason}
        elapsed_ms = max(0.0, (clock() - budget.started) * 1000)
        expired = elapsed_ms >= request["budget_ms"]
        if expired and primary is None:
            primary = "LIVE_DEADLINE_EXCEEDED"
        answer["timing_ms"] = {"total": elapsed_ms, "expired": expired}
    if cleanup_reason:
        answer.update(reason_code=cleanup_reason, primary_reason_code=primary)
    elif primary:
        answer["reason_code"] = primary
    elif payload is not None:
        # Keep the legacy suffix; add a mask for its <=4-digit login corner.
        login = payload["account"]["login_masked"]
        if login and "*" not in login:
            payload["account"]["login_masked"] = None
        answer.update(status="SUCCEEDED", reason_code=None, terminal=payload["terminal"],
                      account=payload["account"], observed_at_utc=payload["observed_at_utc"])
    try:
        return validate_result(answer, request)
    except ProtocolError:
        # Bad SDK fields are discarded rather than leaking raw/native data.
        failed = result(request, evidence=evidence, reason="LIVE_OBSERVATION_UNAVAILABLE")
        if cleanup_reason:
            failed.update(reason_code=cleanup_reason, primary_reason_code=primary)
        elif primary:
            failed["reason_code"] = primary
        failed.update(cleanup=answer["cleanup"], timing_ms=answer["timing_ms"])
        return validate_result(failed, request)


def _load_approved_sdk(installation):
    """Check import resolution before package code and exact loaded DLL before IPC."""
    import importlib.util
    from vibemql5.fleet.sdk_qualification import file_hash, canonical_path
    approved = installation.installation
    spec = importlib.util.find_spec("MetaTrader5")
    if spec is None or type(spec.origin) is not str:
        raise ReadFailure("LIVE_ATTACH_ONLY_UNPROVEN")
    origin = Path(spec.origin).resolve()
    files = approved["runtime_files"]
    if canonical_path(origin) not in files or file_hash(origin) != files[canonical_path(origin)]:
        raise ReadFailure("LIVE_ATTACH_ONLY_UNPROVEN")
    dll = Path(approved["sdk_dll"]).resolve()
    if canonical_path(dll) not in files or file_hash(dll) != files[canonical_path(dll)]:
        raise ReadFailure("LIVE_ATTACH_ONLY_UNPROVEN")
    sdk = importlib.import_module("MetaTrader5")
    actual_origin = Path(getattr(sdk, "__file__", "")).resolve()
    loaded = [Path(getattr(module, "__file__", "")).resolve() for module in tuple(sys.modules.values())
              if type(getattr(module, "__file__", None)) is str]
    if (actual_origin != origin or file_hash(actual_origin) != files[canonical_path(origin)] or dll not in loaded
            or file_hash(dll) != files[canonical_path(dll)]):
        raise ReadFailure("LIVE_ATTACH_ONLY_UNPROVEN")
    return sdk

def main():
    parser = argparse.ArgumentParser(description="Fixed isolated SDK state/account worker")
    parser.add_argument("request", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("approval", type=Path)
    parser.add_argument("operator_public_key", type=Path)
    args = parser.parse_args()
    try:
        from vibemql5.fleet.sdk_qualification import QualifiedSdkInstallation, payload_manifest
        with args.operator_public_key.open("rb") as stream:
            public_key = stream.read(33)
        if len(public_key) != 32:
            return 3
        installation = QualifiedSdkInstallation.from_operator_manifest(
            args.approval, public_key, payload_manifest())
        request = validate_request(read_bounded(args.request))
        installation.assert_request(request)
        # Direct invocation is not an alternate launch path. The child independently
        # observes its current restricted token and no-child policy before SDK import.
        from vibemql5.core.isolated_sdk import current_restrictions
        installation.assert_restrictions(current_restrictions())
        observed = observe_once(request, installation=installation)
        write_bounded(args.result, observed)
        return 0
    except Exception:
        return 3  # Fixed diagnostics only; no raw path/native/credential output.


if __name__ == "__main__":
    raise SystemExit(main())
