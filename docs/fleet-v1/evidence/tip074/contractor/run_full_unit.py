"""Contractor verification of frozen Builder output; no implementation edits."""
import hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path
import xml.etree.ElementTree as ET
worktree = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("source_freeze", worktree/"tests/proofs/fleet_v1/run_source.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
before = module.source_manifest()
(output/"source-before.json").write_text(json.dumps(before, indent=2)+"\n")
env = os.environ.copy()
env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH="app:tests/unit")
cmd = ["/workspace/scratch/b4674f0ac496/test-venv/bin/python", "-m", "pytest", "-q",
       "-p", "fleet_source_progress", "-p", "no:cacheprovider", "tests/unit",
       "--basetemp="+str(output/"owned-tmp"), "--junitxml="+str(output/"unit-junit.xml")]
started = time.monotonic()
timed_out = False
with (output/"unit.raw.log").open("wb") as log:
    try:
        result = subprocess.run(cmd, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        exit_code = 124
after = module.source_manifest()
(output/"source-after.json").write_text(json.dumps(after, indent=2)+"\n")
cases = list(ET.parse(output/"unit-junit.xml").getroot().iter("testcase")) if (output/"unit-junit.xml").exists() else []
failed = sum(x.find("failure") is not None or x.find("error") is not None for x in cases)
skipped = sum(x.find("skipped") is not None for x in cases)
receipt = dict(command=cmd, cwd=str(worktree), external_timeout_seconds=600, exit_code=exit_code,
    timed_out=timed_out, wall_seconds=time.monotonic()-started, source_count=len(before),
    source_unchanged=before==after, cases=len(cases), failed=failed, skipped=skipped, passed=len(cases)-failed-skipped,
    scope="owned local Linux; unpublished frozen source; not Windows, CI or VPS qualification")
(output/"command-receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
print(json.dumps(receipt))
sys.exit(0 if exit_code==0 and before==after and failed==0 and cases else 1)
