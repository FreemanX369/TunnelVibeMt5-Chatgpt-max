"""Bounded tests against the exact deployed MCP entry; no trading or user writes."""
import asyncio,hashlib,json,os,sys,time,traceback,statistics
from pathlib import Path
from contextlib import AsyncExitStack
from datetime import datetime,timezone,timedelta
BASE=Path(r'C:\VibeMQL5');PILOT=BASE/'ops/windows/fleet-pilot-745147f-20261016-a'
OUT=PILOT/'deep-test-20261017';ENTRY=PILOT/'integrated116/operator-integrated-mcp.py'
sys.path.insert(0,str(BASE/'app'))
from vibemql5.adapters.mcp_client_check import _tool_payload
RESULTS=[];TIMES=[]
def write(name,value):
 p=OUT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(value,indent=2),encoding='utf-8');os.replace(t,p)
def mark(case,status='PASS',**data):
 RESULTS.append(dict(case=case,status=status,**data));write('PROGRESS.json',dict(at=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),results=RESULTS))
async def raw(c,name,args):
 t=time.perf_counter()
 try:
  r=await c.call_tool(name,args);TIMES.append(dict(tool=name,seconds=time.perf_counter()-t,error=bool(getattr(r,'is_error',False))));return r
 except Exception as e:
  TIMES.append(dict(tool=name,seconds=time.perf_counter()-t,error=True,exception=type(e).__name__));raise
async def call(c,name,args={}):
 r=await raw(c,name,args)
 if getattr(r,'is_error',False):raise RuntimeError('MCP_ERROR:'+name+':'+str(_tool_payload(r))[:256])
 return _tool_payload(r)
async def test(case,fn):
 try:
  data=await fn();mark(case,**(data or {}))
 except Exception as e:mark(case,'FAIL',error_type=type(e).__name__,reason=str(e)[:500],traceback=traceback.format_exc()[-2000:])
async def main():
 from mcp.client.client import Client
 from mcp.client.stdio import StdioServerParameters
 assert hashlib.sha256(ENTRY.read_bytes()).hexdigest()=='525bb848f40c96d953e8a3a4568f4aac5b987106aefc79fdef560f3af10a00c9'
 async with AsyncExitStack() as stack:
  clients=[]
  for label in 'ABC':
   name={'A':'vibemql5-vps','B':'vibemql5-vps-b','C':'vibemql5-vps-c'}[label]
   profile=Path(r'C:\Users\Administrator\AppData\Roaming\tunnel-client')/(name+'.yaml')
   expected=json.loads((PILOT/('integrated116/PROFILE-'+label+'-APPLY-RECEIPT.json')).read_bytes())['after_sha256']
   assert hashlib.sha256(profile.read_bytes()).hexdigest()==expected
   c=await stack.enter_async_context(Client(StdioServerParameters(command=sys.executable,args=[str(ENTRY)]),read_timeout_seconds=45));clients.append(c)
   tools=(await c.list_tools()).tools;assert len(tools)==116
   mark('DEPLOYED_PROFILE_'+label+'_EXACT_116',scope='PROFILE_HASH_AND_REAL_STDIO_NOT_SEPARATE_CHAT_ACCOUNT')
  c=clients[0];tools=(await c.list_tools()).tools
  async def exact():
   legacy=await stack.enter_async_context(Client(StdioServerParameters(command=sys.executable,args=['-m','vibemql5.adapters.mcp','--root',str(BASE),'--transport','stdio'],env={**os.environ,'PYTHONPATH':str(BASE/'app')}),read_timeout_seconds=30))
   old=(await legacy.list_tools()).tools;new={t.name:t.model_dump(mode='json',by_alias=True,exclude_none=True) for t in tools}
   assert len(old)==85 and all(new[t.name]==t.model_dump(mode='json',by_alias=True,exclude_none=True) for t in old)
  await test('LEGACY85_FULL_PROTOCOL_EXACT',exact)
  # SDK rejects a malformed typed argument before every effect-capable Fleet tool.
  for tool in tools:
   if not tool.name.startswith('fleet_') or tool.name=='fleet_server_info':continue
   async def negative(t=tool):
    schema=t.input_schema;props=schema.get('properties',{});required=schema.get('required',[])
    args={}
    for name,p in props.items():
     typ=p.get('type');args[name]= {} if typ in ('string','integer','number') else 'INVALID_TYPED_ARGUMENT'
    r=await raw(c,t.name,args);assert getattr(r,'is_error',False), 'INVALID_TYPED_ARGUMENT_ACCEPTED'
   await test('NEGATIVE_SCHEMA_'+tool.name,negative)
  for label,fn,args,expected in [
   ('ZERO_RATES','copy_rates',{'symbol':'XAUUSDm','timeframe':'M1','count':0},True),
   ('BAD_TIMEFRAME','copy_rates',{'symbol':'XAUUSDm','timeframe':'INVALID','count':1},True),
   ('UNKNOWN_SYMBOL','get_symbol_snapshot',{'symbol':'DEEPTEST_SYMBOL_ABSENT_20261017'},True),
   ('NAIVE_TICK_TIME','copy_ticks',{'symbol':'XAUUSDm','from_utc':'2026-10-17T00:00:00','count':1},True),
   ('UNKNOWN_TOOL','deep_test_tool_absent_20261017',{},True)]:
   async def negative(fn=fn,args=args):
    r=await raw(c,fn,args);assert getattr(r,'is_error',False)
   await test('NEGATIVE_'+label,negative)
  async def native_parallel():
   data=await asyncio.gather(*(call(cli,'get_symbol_snapshot',{'symbol':'XAUUSDm'}) for cli in clients))
   assert all(x['terminal']['alias']=='MT5-2' and x['symbol']['name']=='XAUUSDm' for x in data)
   return {'clients':3}
  await test('THREE_CLIENT_NATIVE_READ_SERIALIZATION',native_parallel)
  for count in [1,20,200]:
   async def rates(n=count):
    x=await call(c,'copy_rates',{'symbol':'XAUUSDm','timeframe':'M1','start_pos':0,'count':n})
    assert x['returned_count']==n and all(y['low']<=min(y['open'],y['close'])<=max(y['open'],y['close'])<=y['high'] for y in x['rates'])
    assert [y['time'] for y in x['rates']]==sorted({y['time'] for y in x['rates']})
   await test('RATES_VALID_'+str(count),rates)
  async def ticks():
   lower=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat();x=await call(c,'copy_ticks',{'symbol':'XAUUSDm','from_utc':lower,'count':10,'flags':'all'})
   assert 0<=x['returned_count']<=10 and all(datetime.fromisoformat(y['time_msc_utc'])>=datetime.fromisoformat(lower) for y in x['ticks'])
  await test('TICKS_LOWER_BOUND',ticks)
  async def load():
   errors=[];samples=[]
   async def worker(i,cli):
    for n in range(20):
     name=['server_info','health','fleet_server_info','fleet_inventory'][n%4];t=time.perf_counter()
     try:
      x=await call(cli,name)
      if name=='server_info':assert x['tool_count']==116
      if name=='fleet_inventory':assert len(x['devices'])==1
      samples.append(time.perf_counter()-t)
     except Exception as e:errors.append({'client':i,'tool':name,'error':str(e)[:180]})
   await asyncio.gather(*(worker(i,cli) for i,cli in enumerate(clients)))
   write('LOAD.json',dict(requests=60,samples=samples,errors=errors))
   assert not errors,str(errors)[:400]
   return {'requests':60,'clients':3,'p50_seconds':statistics.median(samples),'p95_seconds':sorted(samples)[int(.95*(len(samples)-1))],'max_seconds':max(samples)}
  await test('THREE_CLIENT_MIXED_LOAD60',load)
  node={'device_id':'dev_e488e5a0105847febf7ed46c9e15e9d0','route_generation':1}
  async def inventory():
   args={'node':node,'operation_id':'deep20261017-routed-same-r1'}
   submissions=await asyncio.gather(*(call(cli,'fleet_inventory',args) for cli in clients));ids={x['command_id'] for x in submissions};assert len(ids)==1
   cid=ids.pop();deadline=time.monotonic()+35
   while time.monotonic()<deadline:
    rec=await call(c,'fleet_command_status',{'command_id':cid})
    if rec['state'] in ('COMPLETED','FAILED','REJECTED','UNKNOWN'):break
    await asyncio.sleep(.3)
   assert rec['state']=='COMPLETED' and len(rec['result']['rows'])==5,str(rec.get('state'))
   write('INVENTORY.json',rec)
   return {'command_id':cid,'clients':3,'rows':5}
  await test('THREE_CLIENT_SAME_OPERATION_EXACTLY_ONE_COMMAND',inventory)
  async def deny():
   target={'schema':'fleet.target/1',**node,'terminal_id':'term_dbfaf35a2a5f4b41bd2fedd387512c3a','terminal_generation':1}
   queued=await call(c,'fleet_read_state',{'target':target,'operation_id':'deep20261017-denial-r1'});deadline=time.monotonic()+30
   while time.monotonic()<deadline:
    r=await call(c,'fleet_read_status',{'command_id':queued['command_id']})
    if r['status']!='PENDING':break
    await asyncio.sleep(.3)
   assert r['status']=='FAILED' and r['result']['reason_code']=='LIVE_ATTACH_ONLY_UNPROVEN',str(r)[:300]
   return {'reason':'LIVE_ATTACH_ONLY_UNPROVEN','command_id':queued['command_id']}
  await test('UNQUALIFIED_NATIVE_FAILS_CLOSED',deny)
  async def final():
   x=await call(c,'health');assert x['service']=='READY' and x['queue_length']==0 and x['active_job'] is None and x['concurrency']['native_lock'] is None and x['concurrency']['mutation_lock'] is None
   return {'free_memory_mb':x['memory_free_mb'],'disk_free_gb':x['disk_free_gb']}
  await test('FINAL_HEALTH_GUARDS_CLEAN',final)
 mark('ALL_MCP_CONTEXTS_CLOSED')
if __name__=='__main__':
 OUT.mkdir(exist_ok=True)
 if (OUT/'RECEIPT.json').exists():raise SystemExit('RECEIPT_EXISTS')
 start=datetime.now(timezone.utc).isoformat()
 try:asyncio.run(main())
 except BaseException as e:mark('HARNESS_COMPLETION','FAIL',reason=str(e)[:500],traceback=traceback.format_exc()[-2500:])
 write('TIMINGS.json',TIMES)
 write('RECEIPT.json',dict(start=start,end=datetime.now(timezone.utc).isoformat(),status='PASS' if all(x['status']=='PASS' for x in RESULTS) else 'FAIL',counts={s:sum(x['status']==s for x in RESULTS) for s in ['PASS','FAIL']},results=RESULTS,scope='DEPLOYED_WINDOWS_STDIO_THREE_CLIENTS_NOT_AUTHENTICATED_ACCOUNT_B_C_OR_PHYSICAL_NATIVE'))
