"""Ten-minute bounded control-plane soak; no native jobs or authority changes."""
import json,sys,time,os,traceback
from pathlib import Path
from datetime import datetime,timezone
R=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\releases\fix4r2');P=R.parents[1];O=R/'qa/soak';O.mkdir(exist_ok=True)
sys.path.insert(0,str(R/'source/app'))
from vibemql5.adapters.fleet_client_tools import FleetClientFacade
HEAD='b34d28fd9f6c71eb8c6870039aec77a75284e469';rows=[]
def write(name,obj):
 p=O/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(obj,indent=2));os.replace(t,p)
if (O/'RECEIPT.json').exists() or (O/'PROGRESS.json').exists():raise RuntimeError('RECEIPT_EXISTS')
began=time.monotonic();start=datetime.now(timezone.utc).isoformat();pid=None;revision=0
try:
 client=FleetClientFacade.from_config(P/'runtime/secrets/owner-client.json')
 client.http.pin_loopback_address('127.0.0.1')
 while time.monotonic()-began<600:
  t=time.monotonic();row={'at':datetime.now(timezone.utc).isoformat()}
  try:
   live=json.loads((P/'runtime/LIVE.json').read_bytes());at=datetime.fromisoformat(live['at_utc']);age=(datetime.now(timezone.utc)-at).total_seconds()
   row.update(live_status=live.get('status'),node_status=live.get('node',{}),live_age_seconds=age)
   assert live['source_head']==HEAD,'LIVE_SOURCE_MISMATCH'
   assert live['status']=='RUNNING' and live['node']['status']=='RUNNING','LIVE_NOT_RUNNING'
   assert age<20, 'LIVE_STALE'
   if pid is None:pid=live['pid']
   assert live['pid']==pid,'PILOT_PID_CHANGED'
   x=client.inventory();assert len(x['devices'])==1 and x['status']=='READY_CONTROL_ONLY' and x['sdk_qualification']=='UNQUALIFIED'
   assert x['revision']>=revision;revision=x['revision']
   row.update(status='PASS',seconds=time.monotonic()-t,pilot_pid=pid,revision=revision,live_age_seconds=age)
  except Exception as e:row.update(status='FAIL',error_type=type(e).__name__,code=getattr(e,'code',str(e)[:60]))
  rows.append(row);write('PROGRESS.json',{'start':start,'elapsed_seconds':time.monotonic()-began,'samples':len(rows),'failures':sum(x['status']=='FAIL' for x in rows),'last':row,'failure_samples':[x for x in rows if x['status']=='FAIL']})
  time.sleep(max(0,10-(time.monotonic()-t)))
 write('RECEIPT.json',{'status':'PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL','start':start,'end':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-began,'source_head':HEAD,'pilot_pid':pid,'samples':rows,'scope':'ONE_VPS_CONTROL_PLANE_NO_PHYSICAL_NATIVE_QUALIFICATION'})
except BaseException as e:write('RECEIPT.json',{'status':'FAIL','reason':str(e),'traceback':traceback.format_exc()[-1800:]});raise
