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
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FULL_UNIT_TIMEOUT_SECONDS = 600
PROOF_TIMEOUT_SECONDS = 120


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
    args = parser.parse_args(argv)
    destination = Path(args.output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
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
        ("full-unit", ["-m", "pytest", "tests/unit", "-v", "--tb=short", "--durations=20",
            "-o", "faulthandler_timeout=90", "--junitxml=" + str(destination / "unit.junit.xml")]),
        ("b1-portable", ["tests/proofs/tip057rb1/run_proof.py", "--portable", "--output", str(destination / "b1-portable")]),
    ]
    if os.name == "nt":
        cases.extend([
            ("q1-harmless", ["tests/proofs/tip057rq/run_proof.py", "--require-windows", "--output", str(destination / "q1-harmless")]),
            ("g03a-harmless", ["tests/proofs/tip057rg03a/run_windows.py", "--require-windows", "--output", str(destination / "g03a-harmless")]),
            ("b1-harmless", ["tests/proofs/tip057rb1/run_proof.py", "--require-windows", "--output", str(destination / "b1-harmless")]),
        ])
    results = []
    for name, arguments in cases:
        command = [sys.executable, *arguments]
        timeout = FULL_UNIT_TIMEOUT_SECONDS if name == "full-unit" else PROOF_TIMEOUT_SECONDS
        begun, timed_out = time.monotonic(), False
        with (destination / (name + ".log")).open("w", encoding="utf-8") as log:
            log.write(f"SOURCE_CASE_STARTED case={name} timeout_seconds={timeout}\n"); log.flush()
            try:
                result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=timeout, check=False)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code, timed_out = 124, True
            elapsed = round(time.monotonic() - begun, 3)
            log.write(f"\nSOURCE_CASE_FINISHED case={name} exit_code={code} timed_out={timed_out} elapsed_seconds={elapsed}\n")
        results.append({"case": name, "command": command, "exit_code": code,
            "timeout_seconds": timeout, "timed_out": timed_out, "elapsed_seconds": elapsed})
    after = source_manifest()
    passed = before == after and all(item["exit_code"] == 0 for item in results)
    summary = {"schema": "fleet.source-verification/1", "head_sha": head,
        "tree_sha": git_value("HEAD^{tree}"), "expected_sha": expected,
        "platform": platform.platform(), "python": platform.python_version(),
        "status": "PASS" if passed else "FAIL", "scope": "SOURCE_AND_HARMLESS_FIXTURES",
        "physical_qualification": "NOT_RUN", "source_unchanged_during_run": before == after,
        "cases": results, "source_before": before, "source_after": after}
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("schema", "head_sha", "tree_sha", "platform", "status", "physical_qualification")}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
