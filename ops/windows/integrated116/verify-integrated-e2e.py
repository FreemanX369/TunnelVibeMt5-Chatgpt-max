"""Bounded actual stdio e2e for the exact integrated deployment command."""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

PILOT = Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a')
HERE = PILOT / 'integrated116'
sys.path.insert(0, r'C:\VibeMQL5\app')
from vibemql5.adapters.mcp_client_check import _tool_payload


async def verify(label):
    from mcp.client.client import Client
    from mcp.client.stdio import StdioServerParameters
    checks = []
    def mark(name):
        checks.append(name)
        (HERE / ('E2E-'+label+'-PROGRESS.json')).write_text(json.dumps({
            'status':'RUNNING','label':label,'pid':os.getpid(),'checks':checks,
            'at_utc':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf-8')
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(HERE / 'operator-integrated-mcp.py')])
    async with Client(parameters, read_timeout_seconds=30) as client:
        async def call(name, values):
            result = await client.call_tool(name, values)
            if getattr(result, 'is_error', False):
                raise RuntimeError('MCP_ERROR:' + name + ':' + str(_tool_payload(result)))
            return _tool_payload(result)
        tools = (await client.list_tools()).tools
        by_name = {tool.name:tool.model_dump(mode='json', by_alias=True, exclude_none=True) for tool in tools}
        assert len(by_name) == 116
        mark('ACTUAL_MCP116')
        # Compare with one fresh legacy MCP process. This covers all85 original
        # input/output schemas, descriptions, annotations, widgets and metadata.
        legacy_parameters = StdioServerParameters(command=sys.executable,
            args=['-m','vibemql5.adapters.mcp','--root',r'C:\VibeMQL5','--transport','stdio'],
            env={**os.environ,'PYTHONPATH':r'C:\VibeMQL5\app'})
        async with Client(legacy_parameters, read_timeout_seconds=30) as legacy:
            baseline = (await legacy.list_tools()).tools
            assert len(baseline)==85
            assert all(by_name[t.name] == t.model_dump(mode='json', by_alias=True, exclude_none=True) for t in baseline)
            mark('LEGACY85_PROTOCOL_SCHEMAS_EXACT')
        info = await call('server_info', {})
        assert info['tool_count']==116 and info['fleet_tool_count']==31 and info['fixed_terminal']=='MT5-2'
        assert info['integration_provenance']['entry_sha256']==hashlib.sha256((HERE/'operator-integrated-mcp.py').read_bytes()).hexdigest()
        mark('LOADED_RELEASE_AND_HASH')
        health = await call('health', {})
        assert health['service']=='READY' and health['queue_length']==0 and health['active_job'] is None
        assert health['concurrency']['native_lock'] is None and health['concurrency']['mutation_lock'] is None
        mark('LEGACY_GUARDS_CLEAN')
        capabilities = await call('describe_capabilities', {})
        mark('LEGACY_CAPABILITIES_CALL')
        terminals = await call('list_terminals', {})
        if isinstance(terminals,dict) and set(terminals)=={'result'}:
            terminals=terminals['result']
        assert isinstance(terminals,list) and len(terminals)==5
        mark('LEGACY_TERMINALS5')
        quote = await call('get_symbol_snapshot', {'symbol':'XAUUSDm'})
        assert quote['symbol']['name']=='XAUUSDm' and quote['terminal']['alias']=='MT5-2'
        mark('LEGACY_EXACT_SYMBOL_MT5_2')
        rates = await call('copy_rates', {'symbol':'XAUUSDm','timeframe':'M1','start_pos':0,'count':5})
        assert rates['returned_count']==5 and rates['current_bar_requested'] is True
        assert all(r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in rates['rates'])
        assert [r['time'] for r in rates['rates']]==sorted({r['time'] for r in rates['rates']})
        mark('LEGACY_OHLC5_ORDER_VALID')
        lower = (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        ticks = await call('copy_ticks', {'symbol':'XAUUSDm','from_utc':lower,'count':10,'flags':'all'})
        assert 0<=ticks['returned_count']<=10
        assert all(datetime.fromisoformat(r['time_msc_utc'])>=datetime.fromisoformat(lower) for r in ticks['ticks'])
        mark('LEGACY_TICK_LOWER_BOUND')
        fleet_info = await call('fleet_server_info', {})
        assert fleet_info['tool_count']==31
        cached = await call('fleet_inventory', {})
        node={'device_id':'dev_e488e5a0105847febf7ed46c9e15e9d0','route_generation':1}
        assert cached['devices'][0]['device_id']==node['device_id']
        mark('FLEET_CACHE_ATTRIBUTED')
        operation = 'integrated116-' + label + '-inventory-20261016-r1'
        queued = await call('fleet_inventory', {'node':node,'operation_id':operation})
        replay = await call('fleet_inventory', {'node':node,'operation_id':operation})
        assert queued['command_id']==replay['command_id']
        mark('FLEET_IDEMPOTENT_COMMAND')
        deadline=time.monotonic()+20
        while True:
            record=await call('fleet_command_status', {'command_id':queued['command_id']})
            if record['state'] in ('COMPLETED','FAILED','UNKNOWN','REJECTED'):break
            if time.monotonic()>deadline:raise RuntimeError('FLEET_INVENTORY_TIMEOUT')
            await asyncio.sleep(.25)
        assert record['state']=='COMPLETED' and len(record['result']['rows'])==5
        mark('FLEET_ROUTED_INVENTORY5_COMPLETED')
        selected=next(r['target'] for r in record['result']['rows'] if r['alias']=='MT5-2')
        read=await call('fleet_read_state', {'target':selected,'operation_id':'integrated116-'+label+'-denial-20261016-r1'})
        deadline=time.monotonic()+20
        while True:
            denied=await call('fleet_read_status', {'command_id':read['command_id']})
            if denied['status']!='PENDING':break
            if time.monotonic()>deadline:raise RuntimeError('FLEET_DENIAL_TIMEOUT')
            await asyncio.sleep(.25)
        assert denied['status']=='FAILED' and denied['result']['reason_code']=='LIVE_ATTACH_ONLY_UNPROVEN'
        mark('FLEET_UNQUALIFIED_NATIVE_DENIED')
        after=await call('health', {})
        assert after['queue_length']==0 and after['active_job'] is None
        assert after['concurrency']['native_lock'] is None and after['concurrency']['mutation_lock'] is None
        mark('POST_GUARDS_CLEAN')
    mark('MCP_CONTEXTS_CLOSED')
    return {'status':'PASS','label':label,'checks':checks,'check_count':len(checks),
        'tool_count':116,'model_visible_expected':115,'entry_sha256':info['integration_provenance']['entry_sha256'],
        'tool_catalog_sha256':info['tool_catalog_sha256'],'fleet_command_id':record['command_id'],
        'denial_command_id':read['command_id'],'denial_reason':denied['result']['reason_code'],
        'source_head':info['integration_provenance']['fleet_source_head'],
        'scope':'REAL_STDIO_LEGACY_READS_AND_FLEET_CONTROL_NOT_PHYSICAL_NATIVE_OR_CHAT_ACCOUNT_AUTH',
        'at_utc':datetime.now(timezone.utc).isoformat()}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--label',required=True,choices=['predeploy','A','B','C'])
    parser.add_argument('--attempt',type=int,default=1,choices=range(1,10))
    args=parser.parse_args()
    label=args.label+'-a'+str(args.attempt)
    output=HERE / ('E2E-'+label+'-RECEIPT.json')
    if output.exists():raise SystemExit('RECEIPT_EXISTS_NO_AUTOMATIC_RETRY')
    try:
        (HERE / ('E2E-'+label+'-PROGRESS.json')).write_text(json.dumps({'status':'STARTING',
            'label':label,'pid':os.getpid(),'at_utc':datetime.now(timezone.utc).isoformat()}),encoding='utf-8')
        result=asyncio.run(verify(label))
    except BaseException as error:
        result={'status':'FAIL','label':label,'error_type':type(error).__name__,'reason':str(error),
            'traceback':traceback.format_exception(error),
            'at_utc':datetime.now(timezone.utc).isoformat()}
        output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result));raise
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
