"""Independent bounded source review and semantic regression verification."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path('/workspace/scratch/1818a0d45fa0/repo')
OUT = ROOT.parent/'tip065-windows-metadata-bindings-20261005'
BASE = '81d458ffce7a856a94aae3fb2166d0a9943fba7e'
PRODUCT = 'app/vibemql5/fleet/scoped_resources.py'
TEST = 'tests/unit/test_tip065_windows_metadata_bindings.py'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
spec = importlib.util.spec_from_file_location('source_proof', ROOT/'tests/proofs/fleet_v1/run_source.py')
proof = importlib.util.module_from_spec(spec); spec.loader.exec_module(proof)
before = proof.source_manifest()
assert len(before) == 211
assert before == json.loads((OUT/'focused-v1-source-after.json').read_text())
original = subprocess.check_output(['git','show',BASE+':'+PRODUCT],cwd=ROOT)
old = ast.parse(original); new = ast.parse((ROOT/PRODUCT).read_bytes())
def unchanged_ast(tree):
    return ast.dump(ast.Module(body=[n for n in tree.body if
        not (isinstance(n,ast.FunctionDef) and n.name in {'retained_file_metadata','_windows_metadata_bindings'})
        and not (isinstance(n,ast.ImportFrom) and n.module=='functools')],type_ignores=[]), include_attributes=False)
assert unchanged_ast(old) == unchanged_ast(new)
classes = lambda t: [ast.dump(n,include_attributes=False) for n in ast.walk(t) if isinstance(n,ast.ClassDef)]
assert classes(old) == classes(new)
old_metadata = next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='retained_file_metadata')
new_metadata = next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='retained_file_metadata')
assert ast.dump(old_metadata.body[1],include_attributes=False) == ast.dump(new_metadata.body[1],include_attributes=False)
app_count = 0
for path,digest in before.items():
    if path == TEST: continue
    base_raw = subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
    if path != PRODUCT: assert sha(base_raw) == digest,path
    if path.startswith('app/'): app_count += 1
assert app_count == 89
payload_path = ROOT.parent/'tip065-20261005/live-overlay-payload.json'
payload_sha = sha(payload_path.read_bytes())
assert payload_sha == '0efadd3d855b602e6bd8d58cd7033f092395026b633bceb28629e75fe4003182'
command = [sys.executable,'-m','pytest',TEST,'tests/unit/test_tip056_scoped.py',
    'tests/unit/test_tip056_signed_roster.py','tests/unit/test_tip058b_transport.py',
    'tests/unit/test_tip065_deployment_preflight.py','-v','--tb=short','--durations=12',
    '-o','faulthandler_timeout=90','--junitxml='+str(OUT/'contractor-focused.xml')]
environment = dict(os.environ);environment['PYTHONPATH']='app:tests/unit'
(OUT/'contractor-source-before.json').write_text(json.dumps(before,indent=2)+'\n')
start=time.monotonic()
with (OUT/'contractor-focused.log').open('wb') as log:
    result = subprocess.run(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=240)
elapsed = time.monotonic()-start
after=proof.source_manifest(); assert before == after
(OUT/'contractor-source-after.json').write_text(json.dumps(after,indent=2)+'\n')
suite = next(ET.parse(OUT/'contractor-focused.xml').getroot().iter('testsuite'))
assert result.returncode == int(suite.get('failures')) == int(suite.get('errors')) == 0
assert sha(payload_path.read_bytes()) == payload_sha
receipt = {'schema':'tip065.windows-metadata-contractor-review/1','base_head':BASE,
 'changed_source':[PRODUCT,TEST], 'source_entries':len(before),'source_unchanged_during_run':True,
 'app_files':app_count,'unchanged_app_files':app_count-1,'other_209_base_sources_unchanged':True,
 'all_other_product_ast_unchanged':True,'ctypes_classes_exact_original_ast':True,'posix_branch_exact_original_ast':True,
 'overlay_payload_unchanged':True,'overlay_payload_sha256':payload_sha,'command':command,
 'environment_overrides':{'PYTHONPATH':'app:tests/unit'},'harness_timeout_seconds':240,
 'exit_code':result.returncode,'elapsed_seconds':round(elapsed,3),'junit':suite.attrib,
 'files':{p:{'bytes':(ROOT/p).stat().st_size,'sha256':before[p]} for p in (PRODUCT,TEST)},
 'log_sha256':sha((OUT/'contractor-focused.log').read_bytes()),'junit_sha256':sha((OUT/'contractor-focused.xml').read_bytes()),
 'timing_effect':'UNMEASURED','historical_storage_backup_commit_causes':'OPEN','physical_qualification':'NOT_RUN'}
(OUT/'contractor-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
