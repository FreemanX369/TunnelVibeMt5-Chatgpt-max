"""Finite owned local checks only. Never calls Git, CI or a target runtime."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / "tip072-builder"
PYTHON = HERE.parents[1] / "test-venv/bin/python"
spec = importlib.util.spec_from_file_location("owned_source_manifest", ROOT / "tests/proofs/fleet_v1/run_source.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

stage = sys.argv[1]
assert stage in {"baseline", "baseline-v2", "focused", "compatibility", "collection"}
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH":
    str(ROOT / "app") + os.pathsep + str(ROOT / "tests/unit")}
tests = ["tests/unit/test_tip072_native_denied_publication.py"]
limit = 90
if stage == "compatibility":
    tests = ["tests/unit/test_tip024_multiclient_concurrency.py",
        "tests/unit/test_tip057rg03a_native_ownership.py", "tests/unit/test_tip057r_sdk.py",
        "tests/unit/test_tip061a_057n.py", "tests/unit/test_tip071_scoped_db_setup_cleanup.py"]
    limit = 180
argv = [str(PYTHON), "-m", "pytest", "-vv", "-p", "fleet_source_progress",
    "-o", "faulthandler_timeout=30", f"--junitxml={HERE / (stage + '.junit.xml')}",
    f"--basetemp={HERE / (stage + '_tmp')}"] + tests
if stage == "collection":
    argv = [str(PYTHON), "-m", "pytest", "--collect-only", "-q"] + tests
    limit = 30
for path in [HERE / (stage + '.log'), HERE / (stage + '-source-before.json'), HERE / (stage + '-source-after.json')]:
    assert not path.exists(), f"Preserve previous attempt: {path}"
before = runner.source_manifest()
with (HERE / (stage + '-source-before.json')).open('x') as output:
    json.dump(before, output, indent=2); output.write('\n')
start = time.monotonic()
with (HERE / (stage + '.log')).open('xb') as output:
    try:
        result = subprocess.run(argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=limit)
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = 124
after = runner.source_manifest()
with (HERE / (stage + '-source-after.json')).open('x') as output:
    json.dump(after, output, indent=2); output.write('\n')
assert before == after, "Source changed while owned check ran"
commands_path = HERE / 'commands.json'
commands = json.loads(commands_path.read_text()) if commands_path.exists() else {'cwd': str(ROOT), 'environment':
    {key: env[key] for key in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPATH')}, 'commands': []}
commands['commands'].append({'name': stage, 'argv': argv, 'owned_process_limit_seconds': limit,
    'stdout_stderr': stage + '.log', 'exit_code': code, 'wall_time_seconds': time.monotonic() - start,
    'source_manifest_entries': len(before), 'source_unchanged': True})
commands_path.write_text(json.dumps(commands, indent=2) + '\n')
print(json.dumps(commands['commands'][-1], indent=2))
sys.exit(code)
