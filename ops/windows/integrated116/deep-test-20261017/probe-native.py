"""Diagnostic same legacy code with exception-code-only observation; no trading."""
import asyncio,functools,importlib.util,json,os,sys,time,threading
from pathlib import Path
from contextlib import AsyncExitStack
ROOT=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a');OUT=ROOT/'deep-test-20261017'
sys.path.insert(0,r'C:\VibeMQL5\app')
if '--server' in sys.argv:
 from vibemql5.core.facade import ToolFacade
 original=ToolFacade._observe_live
 @functools.wraps(original)
 def observed(self,operation,fn):
  try:return original(self,operation,fn)
  except BaseException as e:
   with (OUT/('NATIVE-ERROR-'+str(os.getpid())+'.json')).open('w') as f:json.dump({'operation':operation,'type':type(e).__name__,'reason':str(e)[:300]},f)
   raise
 ToolFacade._observe_live=observed
 spec=importlib.util.spec_from_file_location('deployed_entry',ROOT/'integrated116/operator-integrated-mcp.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 asyncio.run(m.create_server()).run(transport='stdio')
else:
 from vibemql5.adapters.mcp_client_check import _tool_payload
 async def main():
  from mcp.client.client import Client
  from mcp.client.stdio import StdioServerParameters
  results=[]
  async def call(c,label,name,args):
   start=time.perf_counter();r=await c.call_tool(name,args);p=_tool_payload(r)
   results.append({'case':label,'status':'FAIL' if getattr(r,'is_error',False) else 'PASS','seconds':time.perf_counter()-start,'summary':p if getattr(r,'is_error',False) else {'terminal':p.get('terminal'),'count':p.get('returned_count')}})
  async with AsyncExitStack() as s:
   clients=[await s.enter_async_context(Client(StdioServerParameters(command=sys.executable,args=[__file__,'--server']),read_timeout_seconds=45)) for _ in range(3)]
   await call(clients[0],'SERIAL_QUOTE_BEFORE','get_symbol_snapshot',{'symbol':'XAUUSDm'})
   await asyncio.gather(*(call(c,'PARALLEL_QUOTE_'+str(i),'get_symbol_snapshot',{'symbol':'XAUUSDm'}) for i,c in enumerate(clients)))
   # Await every parallel call before following serial controls.
   await call(clients[0],'SERIAL_RATES_AFTER','copy_rates',{'symbol':'XAUUSDm','timeframe':'M1','count':20})
   await call(clients[0],'SERIAL_QUOTE_AFTER','get_symbol_snapshot',{'symbol':'XAUUSDm'})
  (OUT/'NATIVE-ISOLATION.json').write_text(json.dumps({'scope':'INSTRUMENTED_SAME_ENTRY_NO_GATEWAY_LOAD','results':results},indent=2))
 asyncio.run(main())
