"""Exact-checkout source evidence. No private VM, SDK or MT5 test is run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FULL_UNIT_TIMEOUT_SECONDS = 900
PROOF_TIMEOUT_SECONDS = 120
HEARTBEAT_SECONDS = 10
CHILD_CLEANUP_SECONDS = 5


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def checkpoint(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def child_identity(child):
    identity = {"pid": child.pid, "creation_identity": "UNKNOWN"}
    try:
        if sys.platform == "linux" and Path("/proc/self/stat").read_text().split()[0] == str(os.getpid()):
            stat = Path(f"/proc/{child.pid}/stat").read_text()
            identity["creation_identity"] = "linux-start-ticks:" + stat.rsplit(")", 1)[1].split()[19]
        elif os.name == "nt":
            import ctypes
            from ctypes import wintypes
            times = [wintypes.FILETIME() for _ in range(4)]
            get_times = ctypes.WinDLL("kernel32", use_last_error=True).GetProcessTimes
            get_times.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
            get_times.restype = wintypes.BOOL
            if get_times(child._handle, *(ctypes.byref(value) for value in times)):
                identity["creation_identity"] = "windows-filetime:" + str(
                    (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
    except (OSError, IndexError, AttributeError):
        pass
    return identity


def run_case(name, command, destination, environment, timeout):
    begun = time.monotonic()
    receipt = {"case": name, "command": command, "status": "RUNNING", "started_utc": utc_now(),
        "timeout_seconds": timeout, "cleanup_timeout_seconds": CHILD_CLEANUP_SECONDS,
        "timed_out": False, "exit_code": None, "child": None,
        "direct_child_closure": "NOT_DISPATCHED", "descendant_closure": "UNKNOWN",
        "closure_scope": "DIRECT_CHILD_ONLY", "semantic_checkpoint": str(destination / (name + ".progress.json"))}
    receipt_path = destination / (name + ".receipt.json")
    checkpoint(receipt_path, receipt)  # Evidence exists before any dispatch.
    child, primary_error = None, None
    log = None
    try:
        try:
            log = (destination / (name + ".log")).open("w", encoding="utf-8")
            log.write(f"SOURCE_CASE_STARTED case={name} timeout_seconds={timeout}\n"); log.flush()
            child = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
            receipt.update(child=child_identity(child), direct_child_closure="UNKNOWN",
                semantic_checkpoint=str(destination / f"{name}.progress.{child.pid}.json"))
            checkpoint(receipt_path, receipt)
            while True:
                remaining = timeout - (time.monotonic() - begun)
                if remaining <= 0:
                    receipt.update(status="TIMED_OUT", timed_out=True, exit_code=124)
                    break
                try:
                    code = child.wait(timeout=min(HEARTBEAT_SECONDS, remaining))
                    receipt.update(status="PASS" if code == 0 else "FAIL", exit_code=code,
                                   direct_child_closure="EXITED", child_exit_code=code)
                    break
                except subprocess.TimeoutExpired:
                    receipt["heartbeat_utc"] = utc_now()
                    receipt["elapsed_seconds"] = round(time.monotonic() - begun, 3)
                    checkpoint(receipt_path, receipt)
                    print("SOURCE_RUNNER_HEARTBEAT " + json.dumps({
                        "case": name, "heartbeat_utc": receipt["heartbeat_utc"],
                        "elapsed_seconds": receipt["elapsed_seconds"], "semantic_progress": "SEE_SEPARATE_CHECKPOINT"}), flush=True)
        except BaseException as error:
            primary_error = error
            receipt.update(status="INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "ERROR",
                           error_type=type(error).__name__)
            raise
        finally:
            # The retained Popen handle identifies only our direct child. It does not certify descendants.
            if child is not None and receipt["direct_child_closure"] != "EXITED":
                try:
                    if child.poll() is None:
                        child.kill()
                    receipt.update(child_exit_code=child.wait(timeout=CHILD_CLEANUP_SECONDS), direct_child_closure="EXITED")
                except BaseException as error:
                    receipt.update(direct_child_closure="UNKNOWN", cleanup_error_type=type(error).__name__)
            receipt.update(elapsed_seconds=round(time.monotonic() - begun, 3), finished_utc=utc_now())
            evidence_error = None
            try:
                if log is None:
                    receipt['log_evidence'] = 'UNKNOWN'
                else:
                    log.write(f"\nSOURCE_CASE_FINISHED case={name} status={receipt['status']} exit_code={receipt['exit_code']} timed_out={receipt['timed_out']} elapsed_seconds={receipt['elapsed_seconds']}\n")
                    log.flush()
                    log.close()
            except Exception as error:
                evidence_error = error
                receipt.update(log_evidence="UNKNOWN", log_error_type=type(error).__name__)
            try:
                checkpoint(receipt_path, receipt)
            except Exception as error:
                evidence_error = error
            if evidence_error is not None:
                if primary_error is not None:
                    primary_error.add_note("SOURCE_CASE_FINAL_EVIDENCE_FAILED:" + type(evidence_error).__name__)
                else:
                    raise RuntimeError("SOURCE_CASE_FINAL_EVIDENCE_FAILED") from evidence_error
    finally:
        if log is not None and not log.closed:
            pending_error = primary_error or sys.exception()
            try: log.close()
            except Exception as error:
                if pending_error is not None and pending_error is not error:
                    pending_error.add_note("SOURCE_LOG_CLOSE_FAILED:" + type(error).__name__)
                else:
                    raise

    return receipt


def git_value(argument):
    return subprocess.check_output(["git", "rev-parse", argument], cwd=ROOT, text=True).strip()


def source_manifest():
    paths = []
    for prefix in ("app", "tests/unit", "tests/proofs"):
        paths.extend((ROOT / prefix).rglob("*.py"))
    paths.extend((ROOT / ".github/workflows").glob("*.yml"))
    paths.extend((ROOT / "ops/windows").rglob("*.ps1"))
    # Build and operator inputs are part of the source qualification candidate.
    paths.extend(ROOT.glob("pyproject.toml"))
    paths.extend(ROOT.glob("requirements*"))
    paths.extend(ROOT.glob("*lock*"))
    for prefix in ("configs", "config", "docs/fleet-v1/config"):
        if (ROOT / prefix).is_dir():
            paths.extend(path for path in (ROOT / prefix).rglob("*") if path.suffix in {".json", ".toml", ".yaml", ".yml"})
    return {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths)) if path.is_file()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-windows", action="store_true")
    parser.add_argument("--unit-only", action="store_true", help="Run the bounded unit suite without harmless proof cases")
    args = parser.parse_args(argv)
    destination = Path(args.output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise SystemExit("SOURCE_OUTPUT_ALREADY_HAS_RECEIPT")
    head = git_value("HEAD")
    expected = os.environ.get("FLEET_V1_EXPECTED_SHA", head)
    if head != expected or (args.require_windows and os.name != "nt"):
        raise SystemExit("SOURCE_CHECKOUT_OR_PLATFORM_MISMATCH")
    before = source_manifest()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT / "app"), str(ROOT / "tests/unit"), environment.get("PYTHONPATH", "")])
    for name in ("TIP057RQ_EXPECTED_SHA", "TIP057RG03A_EXPECTED_SHA", "TIP057RB1_EXPECTED_SHA"):
        environment[name] = head
    cases = [
        ("full-unit", ["-m", "pytest", "-p", "fleet_source_progress", "tests/unit", "-v", "--tb=short", "--durations=20",
            "-o", "faulthandler_timeout=90", "--junitxml=" + str(destination / "unit.junit.xml")]),
        ("b1-portable", ["tests/proofs/tip057rb1/run_proof.py", "--portable", "--output", str(destination / "b1-portable")]),
    ]
    if args.unit_only:
        cases = cases[:1]
    elif os.name == "nt":
        cases.extend([
            ("q1-harmless", ["tests/proofs/tip057rq/run_proof.py", "--require-windows", "--output", str(destination / "q1-harmless")]),
            ("g03a-harmless", ["tests/proofs/tip057rg03a/run_windows.py", "--require-windows", "--output", str(destination / "g03a-harmless")]),
            ("b1-harmless", ["tests/proofs/tip057rb1/run_proof.py", "--require-windows", "--output", str(destination / "b1-harmless")]),
        ])
    summary = {"schema": "fleet.source-verification/1", "head_sha": head,
        "tree_sha": git_value("HEAD^{tree}"), "expected_sha": expected,
        "platform": platform.platform(), "python": platform.python_version(),
        "status": "RUNNING", "started_utc": utc_now(), "unit_only": args.unit_only,
        "scope": "SOURCE_UNITS" if args.unit_only else "SOURCE_AND_HARMLESS_FIXTURES",
        "physical_qualification": "NOT_RUN", "source_before": before, "cases": [],
        "planned_cases": [{"case": name, "command": [sys.executable, *arguments],
            "timeout_seconds": FULL_UNIT_TIMEOUT_SECONDS if name == "full-unit" else PROOF_TIMEOUT_SECONDS}
            for name, arguments in cases]}
    checkpoint(destination / "summary.json", summary)
    results = summary["cases"]
    try:
        for name, arguments in cases:
            command = [sys.executable, *arguments]
            timeout = FULL_UNIT_TIMEOUT_SECONDS if name == "full-unit" else PROOF_TIMEOUT_SECONDS
            case_environment = dict(environment)
            case_environment["FLEET_SOURCE_PROGRESS_PATH"] = str(destination / (name + ".progress.json"))
            summary["active_case"] = {"case": name, "receipt": str(destination / (name + ".receipt.json")),
                "log": str(destination / (name + ".log"))}
            checkpoint(destination / "summary.json", summary)
            results.append(run_case(name, command, destination, case_environment, timeout))
            checkpoint(destination / "summary.json", summary)
        after = source_manifest()
        passed = before == after and all(item["exit_code"] == 0 for item in results)
        summary.update(status="PASS" if passed else "FAIL", active_case=None, finished_utc=utc_now(),
            source_unchanged_during_run=before == after, source_after=after)
        checkpoint(destination / "summary.json", summary)
    except BaseException as error:
        summary.update(status="INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "ERROR",
                       error_type=type(error).__name__, finished_utc=utc_now())
        try:
            checkpoint(destination / "summary.json", summary)
        except Exception as checkpoint_error:
            error.add_note("SOURCE_SUMMARY_EVIDENCE_FAILED:" + type(checkpoint_error).__name__)
        raise

    print(json.dumps({key: summary[key] for key in ("schema", "head_sha", "tree_sha", "platform", "status", "physical_qualification")}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
