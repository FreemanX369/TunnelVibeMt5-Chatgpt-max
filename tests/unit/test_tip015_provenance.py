import json
from pathlib import Path

from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT
from vibemql5.core.provenance import load_bridge_provenance, producer_identity, validate_state_provenance

ROOT=Path(__file__).resolve().parents[2]
OPS=ROOT/'ops'/'windows'


def test_canonical_bridge_provenance_is_single_source():
    p=load_bridge_provenance(ROOT)
    assert p['bridge_version'] == '0.2.39'
    assert p['bridge_build'] == 'TIP-043'
    assert p['mcp_tool_count'] == MCP_TOOL_COUNT == 79
    assert p['mcp_tool_catalog_sha256'] == MCP_TOOL_CATALOG_SHA256
    assert p['mcp_tool_catalog_source'] == 'contracts.py'
    mcp=(ROOT/'app'/'vibemql5'/'adapters'/'mcp.py').read_text(encoding='utf-8')
    assert '"bridge_build": "TIP-015"' not in mcp
    assert 'load_bridge_provenance' in mcp


def test_supervisor_watchdog_do_not_hardcode_current_tip():
    for name in ('Start-VibeMQL5TunnelSupervisor.ps1','Invoke-VibeMQL5Watchdog.ps1'):
        s=(OPS/name).read_text(encoding='utf-8')
        assert 'bridge_build="TIP-013"' not in s
        assert 'bridge_build = "TIP-013"' not in s
        assert 'Get-VibeMQL5BuildProvenance' in s
        assert 'producer_sha256' in s and 'producer_build' in s
    helper=(OPS/'VibeMQL5.Provenance.ps1').read_text(encoding='utf-8')
    assert "producer_build=('sha256:'" in helper
    assert 'Get-VibeMQL5McpCatalogAuthority' in helper
    assert 'MCP_TOOL_COUNT_STALE' in helper
    assert 'MCP_TOOL_CATALOG_SHA_STALE' in helper


def test_runtime_state_provenance_rejects_stale_producer_sha():
    bridge=load_bridge_provenance(ROOT)
    producer_path=OPS/'Start-VibeMQL5TunnelSupervisor.ps1'
    prod=producer_identity(producer_path,'tunnel-supervisor')
    state={
        'bridge_build':bridge['bridge_build'],'bridge_version':bridge['bridge_version'],
        'mcp_tool_count': bridge['mcp_tool_count'],
        'mcp_tool_catalog_sha256': bridge['mcp_tool_catalog_sha256'],
        **prod,
    }
    good=validate_state_provenance(ROOT,state,producer_path,'tunnel-supervisor')
    assert good['fresh'] is True and good['reasons']==[]
    state['producer_sha256']='0'*64
    stale=validate_state_provenance(ROOT,state,producer_path,'tunnel-supervisor')
    assert stale['fresh'] is False
    assert 'PRODUCER_SHA_STALE' in stale['reasons']
