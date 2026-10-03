"""Research controller for the harmless native stub; imports no SDK.

SDK descendant qualification is deliberately absent. The only positive closure is
an explicit known harmless-stub fixture under observed process creation restriction.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))
from vibemql5.core.concurrency import acquire_native_execution
from vibemql5.core.native_ownership import ObservedProcess, OwnershipAuthority
from read_protocol import (ProtocolError, read_bounded, result, validate_request,
                           validate_result, write_bounded)
from windows_adapter import StubBoundary


def sdk_disposition_after_exit(authority, expected):
    """No result/shutdown/exit flag grants a production descendant disposition."""
    if authority.load() != expected or expected["disposition"] != "ACTIVE":
        raise RuntimeError("STALE_SDK_AUTHORITY")
    return {"disposition": "ACTIVE", "reason": "SDK_DESCENDANTS_UNQUALIFIED",
            "activation": "UNAVAILABLE"}


class StubSession:
    def __init__(self, root, fixture_artifact=None):
        self.root, self.authority = Path(root), OwnershipAuthority(root)
        self.lease = self.process = self.observation = self.boundary = None
        self.expected = None
        self.fixture_artifact = fixture_artifact
        self.record = {"evidence": "HARMLESS_NATIVE_STUB_ONLY", "ordering": [],
                       "ownership": "NOT_ACQUIRED", "result": None,
                       "failure": None, "exact_worker_exit": False}

    def _point(self, name, fault):
        self.record["ordering"].append(name)
        if fault is not None:
            fault(name, self)

    def run(self, request, seed, *, mode="normal", wait_ms=2000, fault=None,
            boundary_factory=StubBoundary, observer_factory=ObservedProcess):
        request = validate_request(request)
        seed = validate_result(seed, request)
        if seed["evidence"] != "HARMLESS_NATIVE_STUB_ONLY" or type(wait_ms) is not int or not 1 <= wait_ms <= 10000:
            raise ProtocolError()
        request_path, output_path, seed_path = (self.root / name for name in ("request.json", "result.json", "seed.json"))
        write_bounded(request_path, request)
        write_bounded(seed_path, seed)
        try:
            self.lease = acquire_native_execution(self.root, "B1-STUB-" + request["nonce"], kind="research_leaf_stub", wait_seconds=0)
            self._point("LEASE", fault)
            self.expected = self.authority.arm(self.lease)
            self.record["ownership"] = "ACTIVE"
            self._point("ARMED", fault)
            self.boundary = boundary_factory(self.root, self.fixture_artifact)
            self.expected = self.authority.create_attempt(self.expected)
            self._point("CREATE_ATTEMPT", fault)
            self.process = self.boundary.spawn_stub(self.root / "stub.exe", request_path, output_path, seed_path, mode=mode)
            self._point("SUSPENDED_CREATE", fault)
            self.observation = observer_factory(self.process.lifetime()["pid"])
            self.process.verify_observation(self.observation)
            if output_path.exists() or output_path.with_name(output_path.name + ".entered").exists():
                raise RuntimeError("STUB_EXECUTED_BEFORE_BIND")
            self.expected = self.authority.bind_worker(self.expected, self.observation)
            self.record["worker"] = self.observation.identity()
            self.record["restrictions"] = self.process.restrictions
            self._point("BOUND", fault)
            if output_path.exists() or output_path.with_name(output_path.name + ".entered").exists():
                raise RuntimeError("STUB_EXECUTED_BEFORE_RESUME")
            self.process.allow_resume(self.authority, self.expected, self.observation)
            self._point("BEFORE_RESUME", fault)
            self.process.resume()
            self._point("RESUMED", fault)
            started = time.monotonic()
            while not self.process.exited() and (time.monotonic() - started) * 1000 < wait_ms:
                time.sleep(.005)
            if not self.process.exited():
                self.record["failure"] = "LIVE_DEADLINE_EXCEEDED"
            else:
                self.record["exit_code"] = self.process.wait(0)
                try:
                    received = validate_result(read_bounded(output_path), request)
                    if received["evidence"] != "HARMLESS_NATIVE_STUB_ONLY" or self.record["exit_code"] != 0:
                        raise ProtocolError()
                    self.record["result"] = received
                except ProtocolError:
                    self.record["failure"] = "WORKER_RESULT_INVALID"
        except Exception:
            # Exception data could contain arbitrary file/native strings; emit code only.
            self.record["failure"] = "WORKER_START_UNPROVEN"
        finally:
            # Even exact harmless termination does not clear publication/create uncertainty.
            if self.process is not None:
                try:
                    if not self.process.exited():
                        self.process.terminate_exact(self.process.identity())
                    self.record["exact_worker_exit"] = self.process.exited()
                except Exception:
                    self.record["failure"] = "LIVE_CLEANUP_UNPROVEN"
            if self.lease is not None:
                try:
                    self.lease.release()  # The independent durable authority stays ACTIVE.
                except Exception:
                    self.record["failure"] = "LIVE_CLEANUP_UNPROVEN"
            status = self.authority.status()
            self.record["ownership"] = status.get("disposition", "RECOVERY_REQUIRED")
        return self.record

    def close_harmless_fixture(self):
        """Explicit fixture-only proof, not a SDK/terminal/broker verifier."""
        if (self.record["failure"] is not None or self.record["result"] is None
                or self.record["result"]["evidence"] != "HARMLESS_NATIVE_STUB_ONLY"
                or not self.record["exact_worker_exit"] or self.observation is None
                or self.process is None or self.expected["phase"] != "BOUND"
                or not self.process.restrictions["no_child_creation"]
                or self.process.restrictions["token"]["appcontainer"] != 1):
            raise RuntimeError("HARMLESS_LEAF_PROOF_UNAVAILABLE")
        self.boundary.assert_harmless_artifact()
        self.process.verify_observation(self.observation, require_live=False)
        closed = self.authority.close_owned_worker(self.expected, self.observation,
            descendant_verifier=lambda _: "PREVENTED_BY_BOUNDARY")
        self.record["ownership"] = closed["disposition"]
        self.record["closure_scope"] = "KNOWN_HARMLESS_C_STUB_DIRECT_CHILD_PATH_ONLY_NOT_SDK"
        return closed

    def close_handles(self):
        failures = []
        for resource in (self.observation, self.process, self.boundary):
            if resource is not None:
                try: resource.close()
                except Exception as error: failures.append(type(error).__name__)
        if failures:
            raise RuntimeError("EXACT_FIXTURE_HANDLE_CLEANUP_UNPROVEN:" + ",".join(failures))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close_handles()
