"""Run the original fixed source unit suite with external bounded observation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

HEAD = "f5ee95360acd732e3ccb81730e8a288adb94e4e1"
TREE = "010e0e6ed046bc632e737a1d72cc5334d3ea3739"
TIMEOUT = 600


def load_source(source):
    spec = importlib.util.spec_from_file_location("fixed_source_manifest", source / "tests/proofs/fleet_v1/run_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source, output = Path(args.source).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    original = load_source(source)
    head, tree = original.git_value("HEAD"), original.git_value("HEAD^{tree}")
    before = original.source_manifest()
    expected = json.loads((Path(__file__).parent / "source-manifest.json").read_text(encoding="utf-8"))
    identity = head == HEAD and tree == TREE and before == expected and len(before) == 223
    facts = {"schema": "windows-stage-research-run/1", "head_sha": head, "tree_sha": tree,
             "expected_head_sha": HEAD, "expected_tree_sha": TREE, "source_before": before,
             "source_identity_valid": identity, "platform": platform.platform(),
             "python": platform.python_version(), "physical_qualification": "NOT_RUN",
             "scope": "RESEARCH_ONLY", "timeout_seconds": TIMEOUT, "retries": 0}
    facts["research_file_hashes"] = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                      for name in ("stage_observer.py", "run_research.py", "source-manifest.json")}
    facts["research_head_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip()
    if not identity or os.name != "nt":
        facts.update(status="SOURCE_OR_PLATFORM_MISMATCH", source_after=original.source_manifest())
        (output / "summary.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
        return 2
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(source / "app"), str(source / "tests/unit"), str(Path(__file__).parent)))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "pytest", "-p", "fleet_source_progress", "-p", "stage_observer",
               "tests/unit", "-v", "--tb=short", "--durations=20", "-o", "faulthandler_timeout=90",
               "--junitxml=" + str(output / "unit.junit.xml"), "--stage-observation-dir=" + str(output / "observations")]
    started, timed_out = time.monotonic(), False
    with (output / "full-unit.log").open("w", encoding="utf-8") as log:
        log.write("SOURCE_CASE_STARTED case=full-unit timeout_seconds=600\n"); log.flush()
        try:
            result = subprocess.run(command, cwd=source, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=TIMEOUT, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
        elapsed = round(time.monotonic() - started, 3)
        log.write(f"\nSOURCE_CASE_FINISHED case=full-unit exit_code={code} timed_out={timed_out} elapsed_seconds={elapsed}\n")
    after = original.source_manifest()
    unchanged = before == after == expected
    facts.update(source_after=after, source_unchanged_during_run=unchanged, command=command,
                 exit_code=code, timed_out=timed_out, elapsed_seconds=elapsed,
                 status="PASS" if code == 0 and unchanged else "FAIL")
    (output / "summary.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: facts[key] for key in ("status", "scope", "exit_code", "timed_out", "source_identity_valid", "source_unchanged_during_run")}))
    return code if code else (0 if unchanged else 2)


if __name__ == "__main__":
    raise SystemExit(main())
