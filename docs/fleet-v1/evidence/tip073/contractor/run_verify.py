"""Contractor: execute frozen output; never modify implementation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path('/workspace/scratch/b4674f0ac496')
OUT = ROOT / 'fix-20261007-1748/contractor'
WT = ROOT / 'tip073-candidate'

def source():
    p = WT / 'tests/proofs/fleet_v1/run_source.py'
    spec = importlib.util.spec_from_file_location('contractor_source', p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_manifest()

def main(name):
    global WT
    if name == 'owned-red-v2': WT = ROOT/'tip072-builder'
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = 'app:tests/unit'
    cmd = [str(ROOT/'test-venv/bin/python'), '-m', 'pytest', '-q', '-p', 'fleet_source_progress', '-p', 'no:cacheprovider']
    bound = 180
    if name == 'combined':
        cmd += ['tests/unit/' + n for n in ('test_tip064_integration.py', 'test_fleet_source_progress.py', 'test_fleet_source_runner.py', 'test_tip060c_restore.py', 'test_tip024_multiclient_concurrency.py', 'test_tip072_native_denied_publication.py')]
    elif name in ('owned-green', 'owned-red-v2'):
        plugin = ROOT/'fix-20261007-1748/tip073a-builder'
        env['PYTHONPATH'] += ':' + str(plugin)
        env['OWNED_CAUSAL_RECEIPT'] = str(OUT/(name+'.json'))
        cmd += ['-p', 'causal_gate_plugin_v2', 'tests/unit/test_tip064_integration.py::test_long_fixture_valid_finite_schedule_requires_aggregate_observation']
        bound = 45
    elif name == 'foreign-green':
        plugin = ROOT/'fix-20261007-1748/tip073a-builder'
        env['PYTHONPATH'] += ':' + str(plugin)
        env['OWNED_FOREIGN_RECEIPT'] = str(OUT/'foreign-green.json')
        cmd += ['-p', 'foreign_activity_plugin', 'tests/unit/test_tip064_integration.py::test_long_fixture_valid_finite_schedule_requires_aggregate_observation[10-1000]']
        bound = 30
    else:
        raise ValueError('unknown check')
    junit = OUT/(name+'.junit.xml')
    cmd += ['--junitxml='+str(junit), '--basetemp='+str(OUT/(name+'-tmp'))]
    before = source()
    (OUT/(name+'-source-before.json')).write_text(json.dumps(before, indent=2)+'\n')
    t = time.monotonic()
    with (OUT/(name+'.raw.log')).open('wb') as f:
        result = subprocess.run(cmd, cwd=WT, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=bound)
    after = source()
    (OUT/(name+'-source-after.json')).write_text(json.dumps(after, indent=2)+'\n')
    cases = list(ET.parse(junit).getroot().iter('testcase'))
    receipt = {'argv':cmd, 'cwd':str(WT), 'timeout_s':bound, 'exit_code':result.returncode,
               'wall_s':time.monotonic()-t, 'source_count':len(before), 'source_unchanged':before==after,
               'cases':len(cases), 'failed':sum(x.find('failure') is not None or x.find('error') is not None for x in cases),
               'skipped':sum(x.find('skipped') is not None for x in cases)}
    receipt['passed'] = receipt['cases']-receipt['failed']-receipt['skipped']
    (OUT/(name+'-command.json')).write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))

if __name__ == '__main__':
    main(sys.argv[1])
