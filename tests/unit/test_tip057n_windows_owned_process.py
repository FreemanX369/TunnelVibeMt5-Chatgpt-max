"""Real harmless Windows lifecycle evidence; never MT5/operator qualification."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ownership_fixture import install_closed
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.core.native_ownership import OwnershipAuthority, ObservedProcess, OwnershipBlocked
from vibemql5.fleet.native_process import OwnedWindowsLaunch
from vibemql5.fleet.native import RoutedNativeAdapter

pytestmark = pytest.mark.skipif(os.name != "nt", reason="HARmless_WINDOWS_JOB_OBJECT_ONLY")


# Fixed harmless executable/commands. No terminal, SDK, arbitrary image or MT5 roots.
_CHILD = "import time; time.sleep(0.25)"
_WORKER = '''import json, subprocess, sys
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.25)'])
child.wait(timeout=10)
blocked = False
try:
    escaped = subprocess.Popen([sys.executable, '-c', 'pass'], creationflags=0x01000000)
    escaped.wait(timeout=10)
except OSError:
    blocked = True
with open(sys.argv[1], 'w', encoding='utf-8') as stream:
    json.dump({'evidence':'HARMLESS_WINDOWS_JOB_OBJECT_ONLY','breakaway_blocked':blocked}, stream)
'''


def test_actual_suspended_bind_resume_descendant_boundary_and_exact_exit(tmp_path):
    install_closed(tmp_path)
    authority = OwnershipAuthority(tmp_path)
    events = []
    receipt = tmp_path / "harmless.json"
    with ConcurrencyManager(tmp_path).native_execution("harmless-job", kind="harmless_windows", wait_seconds=0) as lease:
        armed = authority.arm(lease)
        def guard(event):
            events.append((event, authority.load()["phase"]))
        launch = OwnedWindowsLaunch(authority, armed, guard,
            on_bound=lambda process: events.append(("bound_before_resume", authority.load()["phase"])))
        try:
            launch([sys.executable, "-c", _WORKER, str(receipt)], cwd=str(tmp_path))
            identity = launch.observed.identity()
            assert authority.load()["worker"] == identity
            assert launch.wait(timeout=15) == 0
            assert launch._descendants(launch.observed) == "EXACT_DESCENDANTS_EXITED"
            closed = launch.finish()
            assert closed["disposition"] == "CLOSED"
            assert events == [("process_create", "ARMED"), ("bound_before_resume", "BOUND"), ("process_resume", "BOUND")]
            assert json.loads(receipt.read_text())["breakaway_blocked"] is True
        finally:
            if launch.process is not None and launch.poll() is None:
                launch.terminate(); launch.wait(timeout=10)
            launch.close_handles()
    assert authority.status()["admission"] == "AVAILABLE"


def test_fault_before_resume_keeps_bound_authority_until_exact_owned_cleanup(tmp_path):
    install_closed(tmp_path)
    authority = OwnershipAuthority(tmp_path)
    def deny_resume(event):
        if event == "process_resume": raise RuntimeError("SYNTHETIC_FAULT_BEFORE_RESUME")
    with ConcurrencyManager(tmp_path).native_execution("fault-before-resume", kind="harmless_windows", wait_seconds=0) as lease:
        launch = OwnedWindowsLaunch(authority, authority.arm(lease), deny_resume)
        adapter = RoutedNativeAdapter(tmp_path)
        adapter._active["harmless-retained"] = {"launch": launch}
        try:
            with pytest.raises(RuntimeError, match="SYNTHETIC_FAULT"):
                launch([sys.executable, "-c", "pass"], cwd=str(tmp_path))
            assert authority.load()["phase"] == "BOUND"
            assert launch.poll() is None  # Still suspended, no user payload executes.
            assert adapter.has_retained_work() is True  # Owner stop must keep actual handles alive.
            with pytest.raises(OwnershipBlocked): launch.finish()
            assert authority.status()["admission"] == "BLOCKED"
            launch.terminate(); launch.wait(timeout=10)
            assert launch.finish()["disposition"] == "CLOSED"
        finally: launch.close_handles()
        assert adapter.has_retained_work() is False  # Durable metadata alone is not a current handle.


_PARENT = '''import json, os, sys, time
from pathlib import Path
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.core.native_ownership import OwnershipAuthority
from vibemql5.fleet.native_process import OwnedWindowsLaunch
root=Path(sys.argv[1]); authority=OwnershipAuthority(root)
with ConcurrencyManager(root).native_execution('parent-crash', kind='harmless_windows', wait_seconds=0) as lease:
    launch=OwnedWindowsLaunch(authority, authority.arm(lease), lambda event: None)
    launch([sys.executable, '-c', 'import time; time.sleep(60)'], cwd=str(root))
    (root/'worker.json').write_text(json.dumps(launch.observed.identity()))
    deadline=time.monotonic()+20
    while not (root/'crash-now').exists() and time.monotonic()<deadline: time.sleep(0.02)
    os._exit(77)
'''


def test_actual_parent_crash_contains_worker_but_never_claims_durable_closure(tmp_path):
    install_closed(tmp_path)
    parent = subprocess.Popen([sys.executable, "-c", _PARENT, str(tmp_path)], cwd=str(tmp_path))
    observed = None
    try:
        deadline = time.monotonic() + 15
        while not (tmp_path / "worker.json").exists() and time.monotonic() < deadline:
            if parent.poll() is not None: pytest.fail("harmless parent failed before binding")
            time.sleep(0.02)
        identity = json.loads((tmp_path / "worker.json").read_text())
        observed = ObservedProcess(identity["pid"])
        assert observed.identity() == identity
        (tmp_path / "crash-now").write_text("crash")
        assert parent.wait(timeout=10) == 77
        deadline = time.monotonic() + 10
        while not observed.exited() and time.monotonic() < deadline: time.sleep(0.02)
        assert observed.exited()  # Actual held Job KILL_ON_JOB_CLOSE contained it.
        authority = OwnershipAuthority(tmp_path)
        assert authority.load()["phase"] == "BOUND" and authority.status()["admission"] == "BLOCKED"
        with pytest.raises(OwnershipBlocked): authority.require_closed()
    finally:
        if observed is not None: observed.close()
        if parent.poll() is None: parent.kill(); parent.wait(timeout=10)


def test_expiry_during_durable_create_attempt_blocks_actual_create_and_retains_fence(tmp_path,monkeypatch):
    """Actual empty Windows Job Object; no fixture worker runs after lost admission."""
    install_closed(tmp_path);authority=OwnershipAuthority(tmp_path)
    consumed=[False]
    original=authority.create_attempt
    def durable_attempt(expected):
        updated=original(expected);consumed[0]=True;return updated
    monkeypatch.setattr(authority,"create_attempt",durable_attempt)
    def require_current(event):
        assert event=="process_create" and consumed[0]
        raise RuntimeError("SYNTHETIC_EXPIRED_AFTER_DURABLE_ATTEMPT")
    with ConcurrencyManager(tmp_path).native_execution("expiry-before-create",kind="harmless_windows",wait_seconds=0) as lease:
        launch=OwnedWindowsLaunch(authority,authority.arm(lease),lambda event:None,require_current=require_current)
        try:
            with pytest.raises(RuntimeError,match="SYNTHETIC_EXPIRED"):
                launch([sys.executable,"-c","pass"],cwd=str(tmp_path))
            assert launch.process is None and launch.observed is None
            assert authority.load()["phase"]=="CREATE_ATTEMPT" and authority.status()["admission"]=="BLOCKED"
            with pytest.raises(OwnershipBlocked):launch.finish()
        finally:launch.close_handles()
    with pytest.raises(OwnershipBlocked):authority.require_closed()
