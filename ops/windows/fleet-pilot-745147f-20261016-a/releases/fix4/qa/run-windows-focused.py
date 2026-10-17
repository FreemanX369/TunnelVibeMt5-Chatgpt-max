import hashlib,json,os,sys,subprocess,traceback
from pathlib import Path
R=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\releases\fix4');Q=R.parent/'fix1/qa';O=R/'qa/focused';O.mkdir(exist_ok=True)
def save(name,v):(O/name).write_text(json.dumps(v,indent=2))
try:
 m=json.loads((R/'STAGING-MANIFEST.json').read_bytes());assert m['source_head']=='ec3aca9558e4b1812b5a53a7498045ed7297ee27'
 for row in m['files']:
  b=(Path(r'C:\VibeMQL5')/row['target_path']).read_bytes();assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
 env={**os.environ,'PYTHONPATH':str(R/'source/app')+os.pathsep+str(Q)+os.pathsep+str(Q/'tests/unit'),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
 save('PROGRESS.json',{'stage':'REGRESSIONS_52'})
 with (O/'regressions.log').open('w') as log:a=subprocess.run([sys.executable,'-m','pytest','-q',str(R/'qa/test_tip081_pilot_reliability.py'),str(R/'qa/test_tip082_windows_process_observation.py'),str(R/'qa/test_tip085_native_issuance_clock.py'),str(R/'qa/test_tip083_gateway_network_isolation.py'),'--junitxml='+str(O/'regressions.xml')],env=env,cwd=Q,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 save('PROGRESS.json',{'stage':'MATURE_BENCHMARK'})
 with (O/'benchmark.log').open('w') as log:b=subprocess.run([sys.executable,str(Q/'benchmark-mature.py'),str(O/'benchmark-windows.json')],env=env,cwd=Q,stdout=log,stderr=subprocess.STDOUT,timeout=120)
 save('RECEIPT.json',{'status':'PASS' if a.returncode==0 and b.returncode==0 else 'FAIL','regression_returncode':a.returncode,'benchmark_returncode':b.returncode,'source_head':m['source_head'],'source_files_verified':len(m['files'])})
except BaseException as e:save('RECEIPT.json',{'status':'FAIL','reason':str(e),'traceback':traceback.format_exc()[-2000:]});raise
