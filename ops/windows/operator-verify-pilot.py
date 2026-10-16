"""Bounded real stdio MCP discovery and single-VPS routed inventory smoke."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a')
sys.path.insert(0, str(ROOT / 'source/app'))
from vibemql5.adapters.mcp_client_check import _tool_payload
from vibemql5.adapters.fleet_client_tools import FLEET_TOOL_NAMES


async def verify():
    from mcp.client.client import Client
    from mcp.client.stdio import StdioServerParameters
    parameters = StdioServerParameters(command=sys.executable,
        args=['-m', 'vibemql5.adapters.fleet_mcp', '--config', str(ROOT / 'runtime/secrets/owner-client.json')],
        env={**os.environ, 'PYTHONPATH':str(ROOT / 'source/app')})
    async with Client(parameters, read_timeout_seconds=20) as client:
        listed = await client.list_tools()
        names = sorted(tool.name for tool in listed.tools)
        if names != sorted(FLEET_TOOL_NAMES):
            raise RuntimeError('ACTUAL_TOOL_CATALOG_MISMATCH')
        async def call(name, arguments):
            result = await client.call_tool(name, arguments)
            if getattr(result, 'is_error', False):
                raise RuntimeError('MCP_TOOL_ERROR:' + name)
            return _tool_payload(result)
        info = await call('fleet_server_info', {})
        cached = await call('fleet_inventory', {})
        node = {'device_id':'dev_e488e5a0105847febf7ed46c9e15e9d0', 'route_generation':1}
        operation = 'pilot-inventory-745147f-20261016-a'
        submitted = await call('fleet_inventory', {'node':node, 'operation_id':operation})
        recovered = await call('fleet_inventory', {'node':node, 'operation_id':operation})
        if submitted['command_id'] != recovered['command_id']:
            raise RuntimeError('IDEMPOTENCY_FAILED')
        deadline = time.monotonic() + 20
        while True:
            status = await call('fleet_command_status', {'command_id':submitted['command_id']})
            if status['state'] in ('COMPLETED','FAILED','UNKNOWN','REJECTED','EXPIRED'):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('INVENTORY_TIMEOUT')
            await asyncio.sleep(.25)
        rows = status.get('result', {}).get('rows', [])
        if status['state'] != 'COMPLETED' or len(rows) != 5:
            raise RuntimeError('INVENTORY_NOT_COMPLETED')
        return {'status':'PASS', 'transport':'ACTUAL_STDIO_MCP', 'tool_count':len(names), 'tools':names,
            'server_info':info, 'cached_inventory':cached, 'submission':submitted,
            'idempotent_same_command':True, 'routed_inventory':status,
            'scope':'SINGLE_VPS_CONTROL_AND_TERMINAL_IDENTITY_ONLY', 'native_capacity':'NOT_QUALIFIED'}


if __name__ == '__main__':
    result = asyncio.run(verify())
    (ROOT / 'runtime/MCP-VERIFY-RECEIPT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
