"""Observe existing pilot without logging payloads, keys, headers or account data."""
import functools,importlib.util,json,os,sys,threading,time,traceback
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a');OUT=ROOT/'deep-test-20261017'
sys.path.insert(0,str(ROOT/'source/app'))
from vibemql5.fleet.node_transport_journal import NodeTransportJournal
from vibemql5.fleet.transport import NodeClient,HttpsClient,GatewayController
import http.client
lock=threading.Lock()
def event(phase,elapsed,error=None,**more):
 if elapsed<.20 and error is None:return
 record=dict(at=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),phase=phase,seconds=round(elapsed,6),error=error,**more)
 with lock:
  with (OUT/'DIAGNOSTICS.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
def wrap(cls,name):
 old=getattr(cls,name)
 @functools.wraps(old)
 def observed(*args,**kwargs):
  t=time.perf_counter();error=None
  try:return old(*args,**kwargs)
  except BaseException as e:error=getattr(e,'code',type(e).__name__);raise
  finally:event(cls.__name__+'.'+name,time.perf_counter()-t,error)
 setattr(cls,name,observed)
for cls,names in [(NodeTransportJournal,['_validate','begin','acknowledge']),(NodeClient,['_post']),(HttpsClient,['post']),(GatewayController,['handle']),(http.client.HTTPSConnection,['connect','getresponse'])]:
 for name in names:wrap(cls,name)
spec=importlib.util.spec_from_file_location('original_pilot',ROOT/'operator-run-pilot.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
sys.argv=[str(ROOT/'operator-run-pilot.py'),'--resume']
try:
 module.main()
except BaseException as e:
 event('PILOT_EXIT',1,getattr(e,'code',type(e).__name__),reason=str(e)[:128],frames=[{'file':Path(x.filename).name,'line':x.lineno,'function':x.name} for x in traceback.extract_tb(e.__traceback__)])
 (OUT/'DIAGNOSTIC-EXIT.json').write_text(json.dumps(dict(status='FAIL',error_type=type(e).__name__,reason=str(e)[:128],at=datetime.now(timezone.utc).isoformat()),indent=2))
 raise
