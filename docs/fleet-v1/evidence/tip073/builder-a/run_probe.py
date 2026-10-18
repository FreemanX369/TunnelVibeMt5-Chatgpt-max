"""Freeze bounded owned red/green fixture evidence; no source edits."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

BASE = Path(__file__).parent
KEYS = json.loads((BASE / 'parent-source-manifest.json').read_text())
NAME, ROOT = sys.argv[1], Path(sys.argv[2])

def manifest():
    return {key: hashlib.sha256((ROOT / key).read_bytes()).hexdigest() for key in KEYS}

before = manifest()
(BASE / f'{NAME}-source-before.json').write_text(json.dumps(before, indent=2) + '\n')
argv = ['/workspace/scratch/b4674f0ac496/test-venv/bin/python', '-m', 'pytest', '-vv',
        '-p', 'fleet_source_progress', '-p', 'causal_gate_plugin_v2', '-p', 'no:cacheprovider',
        'tests/unit/test_tip064_integration.py::test_long_fixture_valid_finite_schedule_requires_aggregate_observation',
        '--junitxml=' + str(BASE / f'{NAME}.junit.xml'), '--basetemp=' + str(BASE / f'{NAME}-tmp')]
overrides = {'PYTHONPATH': 'app:tests/unit:' + str(BASE), 'PYTHONDONTWRITEBYTECODE': '1',
             'OWNED_CAUSAL_RECEIPT': str(BASE / f'{NAME}.json')}
start = time.monotonic()
with (BASE / f'{NAME}.log').open('wb') as output:
    completed = subprocess.run(argv, cwd=ROOT, env=dict(os.environ, **overrides), stdout=output,
                               stderr=subprocess.STDOUT, timeout=45)
after = manifest()
assert after == before
(BASE / f'{NAME}-source-after.json').write_text(json.dumps(after, indent=2) + '\n')
cases = ET.parse(BASE / f'{NAME}.junit.xml').getroot().findall('.//testcase')
receipt = {'argv': argv, 'cwd': str(ROOT), 'env_override': overrides, 'timeout_s': 45,
           'exit_code': completed.returncode, 'wall_s': time.monotonic() - start,
           'cases': len(cases), 'passed': sum(c.find('failure') is None and c.find('error') is None for c in cases),
           'failed': sum(c.find('failure') is not None or c.find('error') is not None for c in cases),
           'source_entries': len(before), 'source_unchanged': True}
(BASE / f'{NAME}-command.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt), flush=True)
