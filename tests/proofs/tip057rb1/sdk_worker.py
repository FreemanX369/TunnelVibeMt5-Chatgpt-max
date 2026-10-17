"""Prepared state worker; CLI deliberately refuses real SDK effects pending Q2.

The private observation function is tested with synthetic adapters. A later reviewed
VM harness must supply actual SDK/environment/no-start evidence before invoking it.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))
from vibemql5.core.live_terminal import LiveTerminal
from vibemql5.core.native_ownership import ObservedProcess
from read_protocol import ProtocolError, read_bounded, result, validate_request, validate_result, write_bounded


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


def _observe_once_for_later_q2(request, *, sdk_loader=None, process_observer=None,
                               evidence="REAL_SDK_UNQUALIFIED", clock=time.monotonic):
    """No current execution entrypoint calls this with a real SDK.

    `process_observer` is an independently observed retained handle in the actual path;
    injected portable callbacks are explicitly synthetic evidence only.
    """
    request = validate_request(request)  # Before the loader or observer can run.
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
        sdk = (sdk_loader or (lambda: importlib.import_module("MetaTrader5")))()
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

        payload = LiveTerminal(Inventory(), "Q2-RESEARCH", mt5=SDK()).state()
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
            payload["account"]["login_masked"] = "*" + login
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    try:
        request = validate_request(read_bounded(args.request))
        denied = result(request, evidence="REAL_SDK_UNQUALIFIED")
        write_bounded(args.result, denied)
        return 2  # No SDK import or attempt. This is not a Q2 qualification runner.
    except ProtocolError:
        return 3  # No untrusted raw input in diagnostics or result.


if __name__ == "__main__":
    raise SystemExit(main())
