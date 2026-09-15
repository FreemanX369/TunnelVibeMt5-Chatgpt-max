import json
from pathlib import Path

import pytest

import vibemql5.core.jobs as jobs_mod
from vibemql5.core.jobs import JobManager, JobStore


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "VibeMQL5"
    (root / "runs").mkdir(parents=True)
    return root


def _job(root: Path, *, state: str = "TESTING", cancel_requested: bool = False) -> tuple[JobManager, str]:
    mgr = JobManager(root)
    job = mgr.store.create({"workspace": "demo", "ea": "Experts/Demo.mq5", "terminal": "MT5-2", "preset": "smoke"})
    job["state"] = state
    job["cancel_requested"] = cancel_requested
    mgr.store.save(job)
    return mgr, job["job_id"]


def _terminal_events(job: dict) -> list[dict]:
    return [e for e in job.get("events", []) if e.get("kind") == "JOB_TERMINAL"]


def test_tun11_cancel_without_live_process_settles_atomically(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    out = mgr.cancel_job(job_id, wait_seconds=0)
    assert out["state"] == "CANCELLED"
    assert out["cancel_requested"] is True
    assert out["cancel_stop_proof"]["stopped"] is True
    assert out["last_event"]["kind"] == "JOB_TERMINAL"
    assert out["last_event"]["payload"]["state"] == "CANCELLED"
    assert len(_terminal_events(out)) == 1
    assert not (root / "runs" / job_id / "result.json").exists()


def test_tun11_double_cancel_is_idempotent_no_duplicate_terminal_event(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    first = mgr.cancel_job(job_id, wait_seconds=0)
    second = mgr.cancel_job(job_id, wait_seconds=0)
    assert first["state"] == second["state"] == "CANCELLED"
    assert second["event_seq"] == first["event_seq"]
    assert len(_terminal_events(second)) == 1


def test_tun11_live_worker_is_never_signalled_by_controller_cancel(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    job = mgr.store.load(job_id)
    job["worker_pid"] = 4242
    mgr.store.save(job)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [4242])
    monkeypatch.setattr(jobs_mod, "_process_identity", lambda _pid: None)
    killed = []
    monkeypatch.setattr(jobs_mod.os, "kill", lambda pid, _sig: killed.append(pid))
    out = mgr.cancel_job(job_id, wait_seconds=0)
    assert killed == []
    assert out["state"] == "TESTING"
    assert out["cancel_requested"] is True
    assert out["cancel_stop_proof"]["stopped"] is False
    assert out["cancel_stop_proof"]["live_pids"] == [4242]


def test_tun11_process_disappears_during_bounded_wait_then_settles(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    job = mgr.store.load(job_id)
    job["worker_pid"] = 5151
    mgr.store.save(job)
    calls = {"n": 0}
    def discover(_jid):
        calls["n"] += 1
        return [5151] if calls["n"] <= 2 else []
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", discover)
    monkeypatch.setattr(jobs_mod, "_process_identity", lambda _pid: None)
    monkeypatch.setattr(jobs_mod, "_pid_exists", lambda pid: bool(discover(job_id)) if pid == 5151 else False)
    monkeypatch.setattr(jobs_mod.os, "kill", lambda _pid, _sig: None)
    monkeypatch.setattr(jobs_mod.time, "sleep", lambda _s: None)
    # Advance monotonic so the loop remains bounded while allowing one recheck.
    ticks = iter([0.0, 0.0, 0.01, 0.02, 0.03, 0.04])
    monkeypatch.setattr(jobs_mod.time, "monotonic", lambda: next(ticks, 0.05))
    out = mgr.cancel_job(job_id, wait_seconds=1)
    assert out["state"] == "CANCELLED"
    assert out["cancel_stop_proof"]["live_pids"] == []


def test_tun11_unverified_process_fails_closed_no_settle_no_kill(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    job = mgr.store.load(job_id)
    job["processes"] = {"metaeditor": {"pid": 2222, "set_at": "old"}}
    mgr.store.save(job)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    monkeypatch.setattr(jobs_mod, "_process_identity", lambda pid: {"pid": pid, "creation_date": "X", "executable": "C:/MetaEditor64.exe", "command_line": "MetaEditor64.exe /compile:x"})
    killed = []
    monkeypatch.setattr(jobs_mod.os, "kill", lambda pid, _sig: killed.append(pid))
    out = mgr.cancel_job(job_id, wait_seconds=0)
    assert killed == []
    assert out["state"] == "TESTING"
    assert out["cancel_requested"] is True
    assert out["cancel_stop_proof"]["unverified_live_processes"][0]["role"] == "metaeditor"


def test_tun11_pid_reuse_is_not_killed_and_does_not_block_settlement(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    job = mgr.store.load(job_id)
    job["worker_pid"] = 6262
    job["worker_identity"] = {"pid": 6262, "creation_date": "OLD", "executable": "C:/python.exe", "command_line": "python -m vibemql5.worker --job-id " + job_id}
    mgr.store.save(job)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    monkeypatch.setattr(jobs_mod, "_process_identity", lambda pid: {"pid": pid, "creation_date": "NEW", "executable": "C:/other.exe", "command_line": "other.exe"})
    killed = []
    monkeypatch.setattr(jobs_mod.os, "kill", lambda pid, _sig: killed.append(pid))
    out = mgr.cancel_job(job_id, wait_seconds=0)
    assert killed == []
    assert out["state"] == "CANCELLED"
    assert out["cancel_stop_proof"]["stale_or_reused_pids"][0]["reason"] == "PID_NOT_BOUND_TO_JOB"


def test_tun11_unacknowledged_spawn_intent_is_not_stop_proof(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root, state="QUEUED", cancel_requested=True)
    job = mgr.store.load(job_id)
    job["spawn_requested"] = True
    job["spawn_requested_at"] = "2026-09-08T00:00:00Z"
    job.pop("spawn_ack_at", None)
    mgr.store.save(job)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    proof = mgr.execution_stopped(job_id)
    assert proof["stopped"] is False
    assert proof["unverified_live_processes"] == [{"role": "worker", "pid": 0, "reason": "SPAWN_INTENT_UNACKNOWLEDGED"}]
    out = mgr.cancel_job(job_id, wait_seconds=0)
    assert out["state"] == "QUEUED"


def test_tun11_get_job_opportunistically_converges_orphaned_cancel(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=True)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    out = mgr.get_job(job_id)
    assert out["state"] == "CANCELLED"
    assert len(_terminal_events(out)) == 1


def test_tun11_startup_reconcile_settles_orphaned_cancel_without_result(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    _mgr, a = _job(root, cancel_requested=True)
    _mgr, b = _job(root, cancel_requested=True)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    out = JobManager(root).reconcile_cancelled_jobs(wait_seconds=0)
    assert out["complete"] is True
    assert out["candidates"] == 2
    assert out["settled"] == 2
    assert set(out["settled_job_ids"]) == {a, b}
    assert JobStore(root).load(a)["state"] == "CANCELLED"
    assert JobStore(root).load(b)["state"] == "CANCELLED"
    assert not (root / "runs" / a / "result.json").exists()
    assert not (root / "runs" / b / "result.json").exists()


def test_tun11_startup_reconcile_reports_unverified_as_unresolved(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=True)
    job = mgr.store.load(job_id)
    job["processes"] = {"metaeditor": {"pid": 3131, "set_at": "old"}}
    mgr.store.save(job)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    monkeypatch.setattr(jobs_mod, "_process_identity", lambda pid: {"pid": pid, "creation_date": "X", "executable": "C:/MetaEditor64.exe", "command_line": "MetaEditor64.exe /compile:x"})
    out = JobManager(root).reconcile_cancelled_jobs(wait_seconds=0)
    assert out["complete"] is False
    assert out["settled"] == 0
    assert out["unresolved"][0]["job_id"] == job_id
    assert JobStore(root).load(job_id)["state"] == "TESTING"


def test_tun11_native_finished_history_is_preserved_then_cancel_terminal_appended(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=True)
    mgr.store.publish_event(job_id, "TESTER_NATIVE_FINISHED", {"progress_pct": 100})
    before = mgr.store.load(job_id)["event_seq"]
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    out = mgr.get_job(job_id)
    assert out["state"] == "CANCELLED"
    assert out["event_seq"] == before + 1
    assert out["events"][-2]["kind"] == "TESTER_NATIVE_FINISHED"
    assert out["events"][-1]["kind"] == "JOB_TERMINAL"
    assert out["events"][-1]["payload"]["state"] == "CANCELLED"


def test_tun11_settle_requires_cancel_intent(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=False)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    proof = mgr.execution_stopped(job_id)
    with pytest.raises(RuntimeError, match="CANCEL_INTENT_REQUIRED"):
        mgr.settle_cancelled(job_id, proof)


def test_tun11_settle_rejects_mismatched_or_unverified_proof(tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=True)
    with pytest.raises(RuntimeError, match="CANCEL_STOP_PROOF_JOB_MISMATCH"):
        mgr.settle_cancelled(job_id, {"job_id": "BT-20260908-000000-AAAAAA", "stopped": True, "live_pids": [], "unverified_live_processes": []})
    with pytest.raises(RuntimeError, match="CANCEL_STOP_UNPROVEN"):
        mgr.settle_cancelled(job_id, {"job_id": job_id, "stopped": True, "live_pids": [], "unverified_live_processes": [{"role": "x"}]})


def test_tip023r1_prior_running_handoff_blocks_settlement_without_restore(monkeypatch, tmp_path: Path):
    from vibemql5.core.artifacts import ArtifactManager
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=True)
    ArtifactManager(root).write_phase_receipt(job_id, "handoff", {
        "schema_version":"1.0", "phase":"HANDOFF", "status":"PASSED",
        "evidence": {
            "was_running": True, "terminal":"MT5-2",
            "terminal_path":"C:/MT5-2/terminal64.exe", "login":123,
        },
    })
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    proof = mgr.execution_stopped(job_id)
    monkeypatch.setattr(mgr, "_recover_cancel_terminal_state", lambda _jid: {"required":True,"complete":False,"reason":"PRIOR_TERMINAL_RESTORE_REQUIRED"})
    with pytest.raises(RuntimeError, match="CANCEL_TERMINAL_RESTORE_UNPROVEN"):
        mgr.settle_cancelled(job_id, proof)
    assert mgr.store.load(job_id)["state"] == "TESTING"


def test_tip023r1_cleanup_reconnected_satisfies_prior_terminal_restore(tmp_path: Path):
    from vibemql5.core.artifacts import ArtifactManager
    root = _root(tmp_path)
    mgr, job_id = _job(root, cancel_requested=True)
    artifacts = ArtifactManager(root)
    artifacts.write_phase_receipt(job_id, "handoff", {
        "schema_version":"1.0", "phase":"HANDOFF", "status":"PASSED",
        "evidence": {"was_running":True,"terminal":"MT5-2","terminal_path":"C:/MT5-2/terminal64.exe","login":123},
    })
    artifacts.write_phase_receipt(job_id, "cleanup", {
        "schema_version":"1.0", "phase":"CLEANUP", "status":"PASSED",
        "evidence": {"was_running":True,"restore_attempted":True,"reconnected":True},
    })
    req = mgr._cancel_restore_requirement(job_id)
    assert req["required"] is True and req["complete"] is True
    assert req["reason"] == "WORKER_CLEANUP_RECONNECTED"


def test_tip023r1_windows_pid_probe_is_non_destructive(monkeypatch):
    class Fn:
        def __init__(self, result): self.result = result
        def __call__(self, *args): return self.result
    class Kernel32:
        def __init__(self):
            self.OpenProcess = Fn(123)
            self.WaitForSingleObject = Fn(0x102)
            self.CloseHandle = Fn(True)
    killed=[]
    monkeypatch.setattr(jobs_mod.os, "name", "nt")
    monkeypatch.setattr(jobs_mod.ctypes, "WinDLL", lambda *a, **k: Kernel32(), raising=False)
    monkeypatch.setattr(jobs_mod.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    assert jobs_mod._pid_exists(7777) is True
    assert killed == []


def test_tip023r1_identity_unavailable_live_pid_is_unverified(monkeypatch, tmp_path: Path):
    root = _root(tmp_path)
    mgr, job_id = _job(root)
    job = mgr.store.load(job_id)
    job["processes"] = {"metaeditor": {"pid": 8181, "identity": None, "set_at": "old"}}
    mgr.store.save(job)
    monkeypatch.setattr(jobs_mod, "_discover_worker_pids", lambda _jid: [])
    monkeypatch.setattr(jobs_mod, "_process_identity", lambda _pid: None)
    monkeypatch.setattr(jobs_mod, "_pid_exists", lambda pid: pid == 8181)
    proof = mgr.execution_stopped(job_id)
    assert proof["stopped"] is False
    assert proof["unverified_live_processes"] == [{"role":"metaeditor","pid":8181,"reason":"PROCESS_IDENTITY_UNAVAILABLE"}]


def test_tip023_exact_build_identity_and_tool_count():
    from vibemql5 import __version__
    from vibemql5.contracts import MCP_TOOL_COUNT
    root = Path(__file__).parents[2]
    provenance = json.loads((root / "config" / "build-provenance.json").read_text(encoding="utf-8"))
    assert __version__ == "0.2.34"
    assert provenance["bridge_version"] == "0.2.34"
    assert provenance["bridge_build"] == "TIP-033RC1"
    assert provenance["mcp_tool_count"] == 72
    assert MCP_TOOL_COUNT == 72
