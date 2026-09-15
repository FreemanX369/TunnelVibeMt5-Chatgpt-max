from __future__ import annotations
import argparse, json, time
from pathlib import Path
from ..config import default_root
from ..core.facade import ToolFacade
from ..core.tip015a import TIP015ABaselineMigration

FINAL = {"PASSED", "ANOMALY", "FAILED", "TIMEOUT", "CANCELLED", "INTERRUPTED", "RESOURCE_LIMIT"}


def emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def build_parser():
    p = argparse.ArgumentParser(prog="vibemql5")
    p.add_argument("--root", default=str(default_root()))
    s = p.add_subparsers(dest="cmd", required=True)
    for x in ["health", "diagnose", "list-workspaces", "list-terminals", "list-presets", "session-list", "iteration-list"]:
        s.add_parser(x)
    q = s.add_parser("session-get"); q.add_argument("project_id")
    q = s.add_parser("session-resume"); q.add_argument("project_id")
    q = s.add_parser("session-create"); q.add_argument("project_id"); q.add_argument("workspace"); q.add_argument("ea"); q.add_argument("--goal", default=""); q.add_argument("--decision", action="append", default=[]); q.add_argument("--phase", default="IDLE"); q.add_argument("--checkpoint-id", default=""); q.add_argument("--baseline-job-id", default=""); q.add_argument("--last-job-id", default="")
    q = s.add_parser("session-update"); q.add_argument("project_id"); q.add_argument("expected_revision"); q.add_argument("--goal"); q.add_argument("--decision", action="append"); q.add_argument("--phase"); q.add_argument("--checkpoint-id"); q.add_argument("--baseline-job-id"); q.add_argument("--last-job-id")
    q = s.add_parser("tip015a-migrate-baseline"); q.add_argument("project_id"); q.add_argument("expected_revision"); q.add_argument("expected_revision_sha256"); q.add_argument("accepted_job_id"); q.add_argument("expected_source_sha256"); q.add_argument("expected_source_bytes", type=int)
    q = s.add_parser("iteration-start"); q.add_argument("project_id"); q.add_argument("expected_session_revision"); q.add_argument("expected_session_revision_sha256"); q.add_argument("expected_source_sha256"); q.add_argument("expected_source_bytes", type=int); q.add_argument("--mutation-file", required=True); q.add_argument("--preset", default="smoke"); q.add_argument("--set-file", default=""); q.add_argument("--overrides-file"); q.add_argument("--timeout", type=int, default=0)
    q = s.add_parser("iteration-get"); q.add_argument("iteration_id")
    q = s.add_parser("iteration-history"); q.add_argument("iteration_id"); q.add_argument("--limit", type=int, default=100); q.add_argument("--oldest-first", action="store_true")
    q = s.add_parser("fault-receipts"); q.add_argument("--limit", type=int, default=100); q.add_argument("--oldest-first", action="store_true")
    q = s.add_parser("job-list"); q.add_argument("--limit", type=int, default=100); q.add_argument("--oldest-first", action="store_true"); q.add_argument("--workspace", default=""); q.add_argument("--state", default="")
    for name in ("iteration-resume", "iteration-accept", "iteration-reject", "iteration-cancel"):
        q=s.add_parser(name); q.add_argument("iteration_id"); q.add_argument("expected_revision"); q.add_argument("expected_revision_sha256")
    q = s.add_parser("list-eas"); q.add_argument("workspace")
    q = s.add_parser("list-sets"); q.add_argument("workspace")
    q = s.add_parser("read"); q.add_argument("workspace"); q.add_argument("path")
    q = s.add_parser("write"); q.add_argument("workspace"); q.add_argument("path"); q.add_argument("--file", required=True)
    q = s.add_parser("compile"); q.add_argument("workspace"); q.add_argument("ea"); q.add_argument("--terminal", default="MT5-2"); q.add_argument("--mock", action="store_true")
    q = s.add_parser("test"); q.add_argument("workspace"); q.add_argument("ea"); q.add_argument("--terminal", default="MT5-2"); q.add_argument("--preset", default="smoke"); q.add_argument("--set-file"); q.add_argument("--mock", action="store_true"); q.add_argument("--wait", action="store_true"); q.add_argument("--timeout", type=int, default=0)
    q = s.add_parser("job"); q.add_argument("job_id")
    q = s.add_parser("result"); q.add_argument("job_id")
    q = s.add_parser("cancel"); q.add_argument("job_id")
    q = s.add_parser("demo"); q.add_argument("--terminal", default="MT5-2"); q.add_argument("--preset", default="smoke"); q.add_argument("--mock", action="store_true", default=False); q.add_argument("--timeout", type=int, default=0)
    q = s.add_parser("check-all"); q.add_argument("project_id"); q.add_argument("job_id")
    q = s.add_parser("attest"); q.add_argument("project_id"); q.add_argument("job_id")
    q = s.add_parser("ship"); q.add_argument("project_id"); q.add_argument("job_id")
    q = s.add_parser("forward-check"); q.add_argument("project_id"); q.add_argument("--jobs-file", required=True)
    q = s.add_parser("forward-attest"); q.add_argument("project_id"); q.add_argument("qualification_id")
    q = s.add_parser("forward-promote"); q.add_argument("project_id"); q.add_argument("qualification_id")
    q = s.add_parser("live-check"); q.add_argument("project_id"); q.add_argument("--scan-evidence", required=True); q.add_argument("--capability-matrix", required=True); q.add_argument("--session-evidence")
    q = s.add_parser("live-attest"); q.add_argument("project_id"); q.add_argument("qualification_id")
    q = s.add_parser("live-package"); q.add_argument("project_id"); q.add_argument("qualification_id")
    return p


def wait_for_job(f: ToolFacade, job_id: str, timeout: int) -> dict:
    """Wait on durable job events; timeout=0 means native-finish/error driven."""
    timeout = int(timeout)
    if timeout < 0:
        raise ValueError("timeout must be 0 (event-driven) or a positive number of seconds")
    deadline = (time.monotonic() + timeout) if timeout > 0 else None
    seq = -1
    while True:
        remaining = 55.0 if deadline is None else max(0.0, deadline - time.monotonic())
        if deadline is not None and remaining <= 0:
            break
        wait = min(55.0, remaining) if deadline is not None else 55.0
        job = f.get_job(job_id, wait_seconds=wait, after_event_seq=seq)
        seq = int(job.get("event_seq") or seq)
        if job.get("state") in FINAL:
            return f.read_result(job_id)
    try:
        f.cancel_job(job_id)
    except Exception:
        pass
    return {"job_id": job_id, "status": "CLI_EXPLICIT_TIMEOUT_CANCELLED"}


def main(argv=None):
    a = build_parser().parse_args(argv)
    f = ToolFacade(Path(a.root))
    if a.cmd == "health": return emit(f.health())
    if a.cmd == "diagnose": return emit(f.diagnose())
    if a.cmd == "list-workspaces": return emit(f.list_workspaces())
    if a.cmd == "list-terminals": return emit(f.list_terminals())
    if a.cmd == "list-presets": return emit(f.list_presets())
    if a.cmd == "session-list": return emit(f.list_project_sessions())
    if a.cmd == "session-get": return emit(f.get_project_session(a.project_id))
    if a.cmd == "session-resume": return emit(f.resume_project_session(a.project_id))
    if a.cmd == "session-create": return emit(f.create_project_session(a.project_id, a.workspace, a.ea, a.goal, a.decision, a.phase, a.checkpoint_id, a.baseline_job_id, a.last_job_id))
    if a.cmd == "session-update": return emit(f.update_project_session(a.project_id, a.expected_revision, a.goal, a.decision, a.phase, a.checkpoint_id, a.baseline_job_id, a.last_job_id))
    if a.cmd == "tip015a-migrate-baseline": return emit(TIP015ABaselineMigration(Path(a.root)).migrate(a.project_id, a.expected_revision, a.expected_revision_sha256, a.accepted_job_id, a.expected_source_sha256, a.expected_source_bytes))
    if a.cmd == "iteration-list": return emit(f.list_iterations())
    if a.cmd == "iteration-get": return emit(f.get_iteration(a.iteration_id))
    if a.cmd == "iteration-history": return emit(f.read_iteration_history(a.iteration_id, a.limit, not a.oldest_first))
    if a.cmd == "fault-receipts": return emit(f.list_fault_receipts(a.limit, not a.oldest_first))
    if a.cmd == "job-list": return emit(f.list_job_history(a.limit, not a.oldest_first, a.workspace, a.state))
    if a.cmd == "iteration-start":
        mutation=json.loads(Path(a.mutation_file).read_text(encoding="utf-8"))
        overrides=json.loads(Path(a.overrides_file).read_text(encoding="utf-8")) if a.overrides_file else {}
        return emit(f.start_iteration(a.project_id, a.expected_session_revision, a.expected_session_revision_sha256, a.expected_source_sha256, a.expected_source_bytes, mutation, a.preset, a.set_file, overrides, a.timeout))
    if a.cmd == "iteration-resume": return emit(f.resume_iteration(a.iteration_id, a.expected_revision, a.expected_revision_sha256))
    if a.cmd == "iteration-accept": return emit(f.accept_iteration(a.iteration_id, a.expected_revision, a.expected_revision_sha256))
    if a.cmd == "iteration-reject": return emit(f.reject_iteration(a.iteration_id, a.expected_revision, a.expected_revision_sha256))
    if a.cmd == "iteration-cancel": return emit(f.cancel_iteration(a.iteration_id, a.expected_revision, a.expected_revision_sha256))
    if a.cmd == "list-eas": return emit(f.list_eas(a.workspace))
    if a.cmd == "list-sets": return emit(f.list_parameter_sets(a.workspace))
    if a.cmd == "read": return emit(f.read_source(a.workspace, a.path))
    if a.cmd == "write": return emit(f.write_source(a.workspace, a.path, Path(a.file).read_text(encoding="utf-8")))
    if a.cmd == "compile": return emit(f.compile_ea(a.workspace, a.ea, a.terminal, a.mock))
    if a.cmd == "test":
        if a.timeout < 0:
            raise ValueError("--timeout must be 0 (event-driven) or positive")
        j = f.launch_test(a.workspace, a.ea, a.terminal, a.preset, a.set_file, mock=a.mock, test_timeout=a.timeout)
        emit(j)
        if a.wait:
            out = wait_for_job(f, j["job_id"], a.timeout)
            emit(out)
        return
    if a.cmd == "job": return emit(f.get_job(a.job_id))
    if a.cmd == "result": return emit(f.read_result(a.job_id))
    if a.cmd == "cancel": return emit(f.cancel_job(a.job_id))
    if a.cmd == "check-all":
        out = f.release_check_all(a.project_id, a.job_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "attest":
        out = f.release_attest(a.project_id, a.job_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "ship":
        out = f.release_ship(a.project_id, a.job_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "forward-check":
        payload=json.loads(Path(a.jobs_file).read_text(encoding="utf-8-sig")); out=f.forward_check(a.project_id,payload); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "forward-attest":
        out=f.forward_attest(a.project_id,a.qualification_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "forward-promote":
        out=f.forward_promote(a.project_id,a.qualification_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "live-check":
        out=f.live_check(a.project_id,a.scan_evidence,a.capability_matrix,a.session_evidence); emit(out); return 0 if out.get("status") == "PASS" else (3 if out.get("status") == "UNTESTABLE" else 2)
    if a.cmd == "live-attest":
        out=f.live_attest(a.project_id,a.qualification_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "live-package":
        out=f.live_package(a.project_id,a.qualification_id); emit(out); return 0 if out.get("status") == "PASS" else 2
    if a.cmd == "demo":
        if a.timeout < 0:
            raise ValueError("--timeout must be 0 (event-driven) or positive")
        j = f.launch_test(
            "demo", "Experts/DemoEA.mq5", a.terminal, a.preset, "Sets/default.set",
            mock=a.mock, test_timeout=a.timeout,
        )
        out = wait_for_job(f, j["job_id"], a.timeout)
        emit(out)
        return 0 if out.get("status") in {"PASSED", "ANOMALY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
