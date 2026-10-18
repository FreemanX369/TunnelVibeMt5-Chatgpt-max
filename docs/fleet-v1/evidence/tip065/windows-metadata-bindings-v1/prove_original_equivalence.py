"""Synthetic original81d versus proposed ABI reuse; no product source edit."""
import hashlib,importlib.util,json,os,stat,sys
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path('/workspace/scratch/1818a0d45fa0/repo')
OUT=ROOT.parent/'tip065-windows-metadata-bindings-20261005'
spec=importlib.util.spec_from_file_location('abi_controls',ROOT/'tests/unit/test_tip065_windows_metadata_bindings.py')
controls=importlib.util.module_from_spec(spec);spec.loader.exec_module(controls)
original=(OUT/'original-retained-file-metadata.py').read_text()
proposed=(OUT/'proposed-windows-metadata.py').read_text()
product=ROOT/'app/vibemql5/fleet/scoped_resources.py'
before=hashlib.sha256(product.read_bytes()).hexdigest()
rows=[]
cases=[('ordinary',{},None,7),('different-handle',{},None,19),('changed',{'volume':8,'identifier':b'Z'*16,'size':900,'write':44,'change':55,'creation':66,'attributes':0x80},None,7)]
cases += [('query-failure-'+str(kind),{},kind,7) for kind in (18,0,1)]
cases += [('invalid-'+str(index),changed,None,7) for index,changed in enumerate([{'attributes':0x10},{'attributes':0x400},{'directory':1},{'delete_pending':1},{'size':-1}])]
cases += [('invalid-descriptor',{},None,-1)]
def outcome(function,fd):
    try: return ('RETURNED',function(fd))
    except BaseException as error: return ('RAISED',type(error).__name__,error.args)
for name,changed,failed,fd in cases:
    boundary=controls.FakeWindowsMetadata();boundary.rows[fd+100]=changed;boundary.failed_class=failed
    oldns={'os':SimpleNamespace(name='nt'),'stat':stat};newns=dict(oldns)
    exec(compile(original,'<original81d-retained-metadata>','exec'),oldns)
    exec(compile(proposed,'<proposed-constant-abi-reuse>','exec'),newns)
    with pytest.MonkeyPatch.context() as patch:
        boundary.install(patch)
        old=outcome(oldns['retained_file_metadata'],fd);oldtrace=list(boundary.trace);boundary.trace.clear()
        new=outcome(newns['retained_file_metadata'],fd);newtrace=list(boundary.trace)
        assert old==new and oldtrace==newtrace,(name,old,new,oldtrace,newtrace)
        assert boundary.query.argtypes==[controls.W.HANDLE,controls.C.c_int,controls.C.c_void_p,controls.W.DWORD]
        assert boundary.query.restype is controls.W.BOOL
        rows.append({'case':name,'status':'PASS','outcome':old[0],'query_classes':[entry[2] for entry in newtrace if entry[0]=='query'],'trace_equivalent':True,'field_types_sizes_offsets_equivalent':True,'last_error_behavior_equivalent':True})
        newns['_windows_metadata_bindings'].cache_clear()
# Warm binding must not serve prior metadata, failure, or a previous handle.
boundary=controls.FakeWindowsMetadata();oldns={'os':SimpleNamespace(name='nt'),'stat':stat};newns=dict(oldns)
exec(compile(original,'<original81d-retained-metadata>','exec'),oldns)
exec(compile(proposed,'<proposed-constant-abi-reuse>','exec'),newns)
with pytest.MonkeyPatch.context() as patch:
    boundary.install(patch)
    for index,(fd,changed,failed) in enumerate([(1,{},None),(1,{'size':999,'write':77},None),(2,{},None),(1,{},0)]):
        boundary.rows[fd+100]=changed;boundary.failed_class=failed;boundary.trace.clear()
        old=outcome(oldns['retained_file_metadata'],fd);oldtrace=list(boundary.trace);oldloads=boundary.loads
        boundary.trace.clear();new=outcome(newns['retained_file_metadata'],fd);newtrace=list(boundary.trace)
        assert old==new and oldtrace==newtrace
        assert boundary.loads-oldloads==(1 if index==0 else 0)
        rows.append({'case':'warm-sequence-'+str(index),'status':'PASS','outcome':new[0],'trace_equivalent':True,'new_binding_loads':boundary.loads-oldloads})
    assert any(reference() is not None for reference in boundary.libraries)
    newns['_windows_metadata_bindings'].cache_clear()
after=hashlib.sha256(product.read_bytes()).hexdigest();assert before==after
receipt={'schema':'fleet.synthetic-abi-original-equivalence/1','scope':'SYNTHETIC_WINDOWS_ABI_NOT_PHYSICAL','original_function_sha256':hashlib.sha256(original.encode()).hexdigest(),'proposed_prototype_sha256':hashlib.sha256(proposed.encode()).hexdigest(),'product_before_sha256':before,'product_after_sha256':after,'product_unchanged':True,'cases':rows,'case_count':len(rows),'status':'PASS','timing_effect':'UNMEASURED','historical_causes':'OPEN'}
(OUT/'prototype-equivalence-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'status':receipt['status'],'case_count':len(rows),'product_unchanged':True,'scope':receipt['scope']}))
