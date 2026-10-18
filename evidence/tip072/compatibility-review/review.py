"""Owned bounded parent/current probes; no edits to repository sources."""
from pathlib import Path
import hashlib, io, json, os, subprocess, tarfile, time, xml.etree.ElementTree as ET

ROOT = Path('/workspace/scratch/b4674f0ac496')
OUT = Path(__file__).parent
CURRENT = ROOT / 'tip072-builder'
PARENT = OUT / 'parent-source'
HEAD = 'e9f668a049288eb899c580a6b8147e5caedae585'
PYTHON = ROOT / 'test-venv/bin/python'
KEYS = json.loads((ROOT / 'fix-20261007-1439/tip072-builder/compatibility-source-before.json').read_text())
MODULES = json.loads((ROOT / 'fix-20261007-1439/tip072-builder/commands.json').read_text())['commands'][-1]['argv'][-5:]

def manifest(root):
    return {key: hashlib.sha256((root/key).read_bytes()).hexdigest() for key in KEYS if (root/key).is_file()}

def run(name, source, arguments):
    before = manifest(source)
    (OUT/f'{name}-source-before.json').write_text(json.dumps(before, indent=2)+'\n')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=f'{source}/app:{source}/tests/unit')
    argv = [str(PYTHON), '-m', 'pytest', '-vv', '-p', 'fleet_source_progress', '-o', 'faulthandler_timeout=30', f'--junitxml={OUT/name}.junit.xml', f'--basetemp={OUT/name}_tmp', *arguments]
    started=time.monotonic()
    with (OUT/f'{name}.log').open('wb') as log:
        process = subprocess.run(argv, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    after = manifest(source)
    (OUT/f'{name}-source-after.json').write_text(json.dumps(after, indent=2)+'\n')
    cases = ET.parse(OUT/f'{name}.junit.xml').getroot().findall('.//testcase')
    failures = [{'classname':c.attrib['classname'], 'name':c.attrib['name'], 'message':c.find('failure').attrib.get('message'), 'text':c.find('failure').text} for c in cases if c.find('failure') is not None]
    receipt = {'name':name, 'argv':argv, 'cwd':str(source), 'env':{'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':env['PYTHONPATH']}, 'limit_seconds':180, 'exit_code':process.returncode, 'wall_time_seconds':time.monotonic()-started, 'case_count':len(cases), 'passed':sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases), 'skipped':sum(c.find('skipped') is not None for c in cases), 'failures':failures, 'source_unchanged':before==after, 'source_manifest_entries':len(before)}
    (OUT/f'{name}-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('failures','env','argv')}) , flush=True)
    return receipt

if __name__ == '__main__':
    assert not PARENT.exists()
    current_before=manifest(CURRENT)
    assert current_before==KEYS
    archive=subprocess.run(['git','-C',str(CURRENT),'archive',HEAD,'app','tests','pyproject.toml','.github'],capture_output=True,check=True).stdout
    PARENT.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(PARENT, filter='data')
    (OUT/'parent-archive-sha256.txt').write_text(hashlib.sha256(archive).hexdigest()+'\n')
    parent_manifest=manifest(PARENT)
    expected={key:hashlib.sha256(subprocess.run(['git','-C',str(CURRENT),'show',f'{HEAD}:{key}'],capture_output=True,check=True).stdout).hexdigest() for key in parent_manifest}
    assert parent_manifest==expected
    run('parent-bounded-compatibility',PARENT,MODULES)
    node='tests/unit/test_tip024_multiclient_concurrency.py::test_tip024_mcp_registers_catalog_and_context_is_invisible_contract'
    run('parent-isolated-tip024',PARENT,[node])
    run('current-isolated-tip024',CURRENT,[node])
    # Collection imports the real exception submodule before the old fake test runs.
    run('parent-with-real-sdk-module-collected',PARENT,[node,'tests/unit/test_tip066_live_diagnostics.py'])
    current_after=manifest(CURRENT)
    scope={'head':HEAD,'current_source_before':current_before,'current_source_after':current_after,'current_unchanged':current_before==current_after,'parent_matches_exact_git':parent_manifest==expected,'parent_manifest_entries':len(parent_manifest),'changed_vs_parent':[key for key in current_before if key not in parent_manifest or current_before[key]!=parent_manifest[key]]}
    (OUT/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
    assert current_before==current_after
