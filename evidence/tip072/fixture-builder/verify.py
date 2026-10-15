"""Finite TIP072F verification; no repository source writes."""
from pathlib import Path
import ast, hashlib, importlib.util, json, os, subprocess, sys, time

ROOT=Path('/workspace/scratch/b4674f0ac496')
OUT=Path(__file__).parent
SOURCE=ROOT/'tip072-builder'
spec=importlib.util.spec_from_file_location('review',ROOT/'fix-20261007-1644/compatibility-review-builder/review.py')
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
review.OUT=OUT
TIP024='tests/unit/test_tip024_multiclient_concurrency.py'
NAME='test_tip024_mcp_registers_catalog_and_context_is_invisible_contract'

def structure(text):
    return ast.parse(text)

old=structure((OUT/'test-tip024-before.py').read_text())
new=structure((SOURCE/TIP024).read_text())
old_fn=next(node for node in old.body if isinstance(node,ast.FunctionDef) and node.name==NAME)
new_fn=next(node for node in new.body if isinstance(node,ast.FunctionDef) and node.name==NAME)
old_body=[ast.dump(node,include_attributes=False) for node in old_fn.body]
new_body=[ast.dump(node,include_attributes=False) for node in new_fn.body]
insertion=next(index for index,node in enumerate(new_fn.body) if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='exceptions_mod')
assert old_body==new_body[:insertion]+new_body[insertion+3:]
old_fn.body=[];new_fn.body=[]
assert ast.dump(old,include_attributes=False)==ast.dump(new,include_attributes=False)
before=json.loads((OUT/'source-before-fixture-correction.json').read_text())
frozen=review.manifest(SOURCE)
assert [path for path in before if before[path]!=frozen[path]]==[TIP024]
scope={'only_changed_since_tip072_frozen':[TIP024],'source_entries':len(frozen),'ast_identical_outside_named_fixture':True,'original_body_nodes_preserved_in_order':True,'added_fixture_nodes':3,'tip072_production_sha256':frozen['app/vibemql5/core/concurrency.py'],'tip072_test_sha256':frozen['tests/unit/test_tip072_native_denied_publication.py'],'tip024_before_sha256':before[TIP024],'tip024_after_sha256':frozen[TIP024]}
(OUT/'source-after-fixture-correction.json').write_text(json.dumps(frozen,indent=2)+'\n')

review.run('isolated-corrected-tip024',SOURCE,[f'{TIP024}::{NAME}'])
review.run('original-five-module-compatibility',SOURCE,review.MODULES)
review.run('tip072-focused',SOURCE,['tests/unit/test_tip072_native_denied_publication.py'])

# A fresh process creates the same explicitly incomplete stub as the original red case.
# It must preserve the adapter's strict SDK import error, without SDK child-module cache.
probe='''from pathlib import Path
import json, sys, types
assert not any(name.startswith("mcp") for name in sys.modules)
fake=types.ModuleType("mcp.server.mcpserver")
fake.MCPServer=type("MCPServer",(),{})
fake.Context=type("Context",(),{})
for name,module in (("mcp",types.ModuleType("mcp")),("mcp.server",types.ModuleType("mcp.server")),("mcp.server.mcpserver",fake)):
    sys.modules[name]=module
from vibemql5.adapters.mcp import create_server
try:
    create_server(Path("owned-unused-root"), transport="stdio")
except RuntimeError as error:
    assert str(error)=='MCP SDK v2 is required. Run: pip install -e ".[mcp]"'
    assert type(error.__cause__) is ModuleNotFoundError
    assert error.__cause__.name=="mcp.server.mcpserver.exceptions"
    print(json.dumps({"scope":"incomplete-stub-strict-import-control","strict_sdk_error_preserved":True,"error":str(error),"cause":str(error.__cause__),"exception_module_loaded":"mcp.server.mcpserver.exceptions" in sys.modules}))
else:
    raise AssertionError("Strict SDK import must fail")
'''
(OUT/'missing-required-exception-probe.py').write_text(probe)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=f'{SOURCE}/app:{SOURCE}/tests/unit')
argv=[str(review.PYTHON),str(OUT/'missing-required-exception-probe.py')]
started=time.monotonic()
with (OUT/'missing-required-exception.log').open('wb') as log:
    result=subprocess.run(argv,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
after=review.manifest(SOURCE)
assert result.returncode==0 and after==frozen
receipt={'argv':argv,'cwd':str(SOURCE),'limit_seconds':30,'exit_code':result.returncode,'wall_time_seconds':time.monotonic()-started,'expected_sdk_failure_observed':True,'source_unchanged':after==frozen,'source_manifest_entries':len(after),'scope':'incomplete stub control; not real SDK qualification'}
(OUT/'missing-required-exception-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(OUT/'missing-required-exception-source-before.json').write_text(json.dumps(frozen,indent=2)+'\n')
(OUT/'missing-required-exception-source-after.json').write_text(json.dumps(after,indent=2)+'\n')
(OUT/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
print(json.dumps(scope),flush=True)
