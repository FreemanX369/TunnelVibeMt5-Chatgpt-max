"""Pinned legacy85 + Fleet31 composition for the existing A/B/C plugins.

No application file, gateway journal or native qualification is modified.
MCP SDK2.1.1 tool metadata is read through its existing manager; tools are
registered through public add_tool and compared with actual protocol schemas.
"""
import asyncio
import functools
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

BASE = Path(r'C:\VibeMQL5')
PILOT = BASE / 'ops/windows/fleet-pilot-745147f-20261016-a'
HERE = PILOT / 'integrated116'
FLEET_HEAD = 'ec3aca9558e4b1812b5a53a7498045ed7297ee27'
FLEET_ROOT = PILOT / 'releases/fix4'
LEGACY_MANIFEST_SHA = 'ae3125ef9bc6031163b47363a9799c4e6cbdd2e25c5b76760019f23e2e3749b1'
FLEET_MANIFEST_SHA = '920b5f1bf3f8aa0d3746ca023e5135bde34c277326f7949810084b0d18086bd5'
VARIANT = 'LEGACY85_FLEET31_20261017_FIX4'


def safe_legacy_call(fn):
    """Expose only a fixed safe code; keep busy and IPC failures distinguishable."""
    @functools.wraps(fn)
    def invoke(*args, **kwargs):
        from mcp.server.mcpserver.exceptions import ToolError
        try:
            return fn(*args, **kwargs)
        except (TimeoutError, RuntimeError) as error:
            prefix = str(error).split(':', 1)[0]
            codes = {'CONCURRENCY_NATIVE_WAIT_TIMEOUT':'NATIVE_BUSY',
                'CONCURRENCY_MUTATION_WAIT_TIMEOUT':'MUTATION_BUSY',
                'MT5_LIVE_IPC_INITIALIZE_FAILED':'MT5_LIVE_IPC_INITIALIZE_FAILED',
                'MT5_LIVE_AUTHORIZATION_FAILED':'MT5_LIVE_AUTHORIZATION_FAILED',
                'FIXED_TERMINAL_NOT_RUNNING':'FIXED_TERMINAL_NOT_RUNNING',
                'MT5_LIVE_TERMINAL_INFO_UNAVAILABLE':'MT5_LIVE_TERMINAL_INFO_UNAVAILABLE',
                'MT5_LIVE_TERMINAL_BINDING_MISMATCH':'MT5_LIVE_TERMINAL_BINDING_MISMATCH',
                'MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE':'MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE',
                'TERMINAL_PROCESS_OBSERVATION_UNAVAILABLE':'TERMINAL_PROCESS_OBSERVATION_UNAVAILABLE'}
            code = codes.get(prefix)
            if code is None:
                raise
            raise ToolError(json.dumps({'code':code, 'retryable':code in {'NATIVE_BUSY','MUTATION_BUSY','TERMINAL_PROCESS_OBSERVATION_UNAVAILABLE'}},sort_keys=True)) from None
    return invoke


def verified_sources():
    if importlib.metadata.version('mcp') != '2.1.1':
        raise RuntimeError('INTEGRATION_MCP_VERSION_CHANGED')
    for path, expected, count, field, allowed in (
        (HERE / 'legacy-source-baseline.json', LEGACY_MANIFEST_SHA, 89, 'path', BASE / 'app'),
        (FLEET_ROOT / 'STAGING-MANIFEST.json', FLEET_MANIFEST_SHA, 95, 'target_path', FLEET_ROOT / 'source'),
    ):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError('INTEGRATION_MANIFEST_CHANGED')
        manifest = json.loads(raw)
        if len(manifest['files']) != count:
            raise RuntimeError('INTEGRATION_SOURCE_SCOPE_CHANGED')
        for entry in manifest['files']:
            selected = BASE / entry[field]
            if not selected.resolve().is_relative_to(allowed.resolve()):
                raise RuntimeError('INTEGRATION_SOURCE_PATH_INVALID')
            data = selected.read_bytes()
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise RuntimeError('INTEGRATION_SOURCE_CHANGED:' + entry[field])


async def schema_map(server):
    return {tool.name:tool.model_dump(mode='json', by_alias=True, exclude_none=True)
            for tool in await server.list_tools()}


def stage(value):
    if os.environ.get('VIBEMQL5_ENTRY_DIAGNOSTIC') == '1':
        (FLEET_ROOT/'qa'/('entry-'+str(os.getpid())+'-stage.json')).write_text(json.dumps({'stage':value,'pid':os.getpid()}))

async def create_server():
    stage('VERIFY_SOURCE')
    verified_sources()
    # Active legacy modules keep their canonical name and all existing globals.
    sys.path.insert(0, str(BASE / 'app'))
    from vibemql5.adapters.mcp import create_server as legacy_server
    from vibemql5.contracts import MCP_TOOL_NAMES
    stage('CREATE_LEGACY')
    server = legacy_server(BASE, 'stdio')
    stage('LEGACY_SCHEMA')
    legacy = await schema_map(server)
    if set(legacy) != set(MCP_TOOL_NAMES) or len(legacy) != 85:
        raise RuntimeError('INTEGRATION_LEGACY_CATALOG_CHANGED')
    for original_tool in tuple(server._tool_manager.list_tools()):
        if original_tool.name in {'get_terminal_live_state','get_account_snapshot','get_symbol_snapshot',
                'copy_rates','copy_ticks','inspect_terminal','capture_live_chart','list_live_charts','read_terminal_journal'}:
            server.remove_tool(original_tool.name)
            server.add_tool(safe_legacy_call(original_tool.fn), name=original_tool.name, title=original_tool.title,
                description=original_tool.description, annotations=original_tool.annotations,
                icons=original_tool.icons, meta=original_tool.meta)
    # Frozen Fleet dependencies use a separate Python namespace. They cannot
    # replace an active legacy module through sys.path or sys.modules aliases.
    namespace = '_vibemql5_fleet_fix4'
    if namespace not in sys.modules:
        package = FLEET_ROOT / 'source/app/vibemql5'
        spec = importlib.util.spec_from_file_location(namespace, package / '__init__.py',
            submodule_search_locations=[str(package)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[namespace] = module
        spec.loader.exec_module(module)
    fleet_module = importlib.import_module(namespace + '.adapters.fleet_mcp')
    # The fixed read-only observer also serves the pinned legacy facade.
    process_observer = importlib.import_module(namespace + '.core.windows_process_inventory')
    legacy_inventory = importlib.import_module('vibemql5.core.inventory')
    def observed_terminal_paths(self):
        return {self._norm(path) for path in process_observer.terminal_paths()}
    legacy_inventory.TerminalInventory.running_terminal_paths = observed_terminal_paths
    stage('CREATE_FLEET_FACADE')
    facade = fleet_module.FleetClientFacade.from_config(PILOT / 'runtime/secrets/owner-client.json')
    facade.http.pin_loopback_address('127.0.0.1')
    fleet = fleet_module.create_server(client_facade=facade)
    stage('FLEET_SCHEMA')
    fleet_schemas = await schema_map(fleet)
    if len(fleet_schemas) != 31 or set(legacy) & set(fleet_schemas):
        raise RuntimeError('INTEGRATION_FLEET_CATALOG_COLLISION')
    for tool in fleet._tool_manager.list_tools():
        server.add_tool(tool.fn, name=tool.name, title=tool.title,
            description=tool.description, annotations=tool.annotations,
            icons=tool.icons, meta=tool.meta)
    names = list(MCP_TOOL_NAMES) + list(fleet_module.FLEET_TOOL_NAMES)
    catalog_sha = hashlib.sha256(('\n'.join(names) + '\n').encode()).hexdigest()
    original = server._tool_manager.get_tool('server_info')
    original_fn = original.fn

    @functools.wraps(original_fn)
    def server_info() -> dict[str, Any]:
        result = original_fn()
        result.update(tool_count=len(names), tool_names=names, tool_catalog_sha256=catalog_sha,
            legacy_tool_count=85, fleet_tool_count=31, deployment_variant=VARIANT,
            integration_provenance={'entry_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'legacy_manifest_sha256':LEGACY_MANIFEST_SHA, 'fleet_manifest_sha256':FLEET_MANIFEST_SHA,
                'fleet_source_head':FLEET_HEAD, 'legacy_source':'PINNED_ACTIVE_APP89', 'legacy_runtime_fixes':['SAFE_NATIVE_ERROR_CODES','WIN32_PROCESS_OBSERVATION'],
                'fleet_source':'ISOLATED_PINNED_NAMESPACE', 'sdk_activation':'UNCHANGED_UNQUALIFIED'})
        result['tool_visibility'] = dict(result['tool_visibility'], server_catalog_count=len(names),
            model_visible_expected_count=len(names) - len(result['tool_visibility']['app_only_tools']))
        if 'runtime_provenance' in result:
            result['runtime_provenance'] = dict(result['runtime_provenance'], legacy_mcp_tool_count=85,
                mcp_tool_count=len(names), mcp_tool_catalog_sha256=catalog_sha, deployment_variant=VARIANT)
        return result

    server.remove_tool('server_info')
    server.add_tool(server_info, name=original.name, title=original.title,
        description=original.description, annotations=original.annotations,
        icons=original.icons, meta=original.meta)
    combined = await schema_map(server)
    if len(combined) != 116 or any(combined.get(name) != value for name,value in {**legacy, **fleet_schemas}.items()):
        raise RuntimeError('INTEGRATION_SCHEMA_DRIFT')
    for name,module in tuple(sys.modules.items()):
        if name.startswith(namespace) and getattr(module, '__file__', None):
            if not Path(module.__file__).resolve().is_relative_to((FLEET_ROOT / 'source/app').resolve()):
                raise RuntimeError('INTEGRATION_NAMESPACE_ESCAPE')
    stage('SERVER_READY')
    return server


if __name__ == '__main__':
    if os.environ.get('VIBEMQL5_ENTRY_DIAGNOSTIC') == '1':
        import faulthandler
        _trace=(FLEET_ROOT/'qa'/('entry-'+str(os.getpid())+'-stack.txt')).open('a')
        faulthandler.dump_traceback_later(20, file=_trace)
    asyncio.run(create_server()).run(transport='stdio')
