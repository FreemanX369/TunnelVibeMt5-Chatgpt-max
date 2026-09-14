Set-StrictMode -Version Latest

function Get-VibeMQL5RootFromConfigPath {
    param([Parameter(Mandatory)][string]$ConfigPath)
    $resolved=(Resolve-Path -LiteralPath $ConfigPath).Path
    $windowsDir=Split-Path -Parent $resolved
    $opsDir=Split-Path -Parent $windowsDir
    return Split-Path -Parent $opsDir
}

function Get-VibeMQL5McpCatalogAuthority {
    param([Parameter(Mandatory)][string]$Root)
    $contracts=Join-Path $Root 'app\vibemql5\contracts.py'
    if(-not(Test-Path -LiteralPath $contracts -PathType Leaf)){throw "MCP_CATALOG_CONTRACT_MISSING: $contracts"}
    $text=Get-Content -LiteralPath $contracts -Raw -Encoding UTF8
    if($text -notmatch '(?m)^MCP_TOOL_COUNT\s*=\s*(\d+)\s*$'){throw 'MCP_TOOL_COUNT_CONTRACT_MISSING'}
    $count=[int]$Matches[1]
    if($text -notmatch '(?m)^MCP_TOOL_CATALOG_SHA256\s*=\s*[''"]([0-9a-fA-F]{64})[''"]\s*$'){throw 'MCP_TOOL_CATALOG_SHA_CONTRACT_MISSING'}
    [ordered]@{
        mcp_tool_count=$count
        mcp_tool_catalog_sha256=$Matches[1].ToLowerInvariant()
        mcp_tool_catalog_source='contracts.py'
    }
}

function Get-VibeMQL5ObjectProperty {
    param([Parameter(Mandatory)][object]$Object,[Parameter(Mandatory)][string]$Name)
    $prop=$Object.PSObject.Properties[$Name]
    if($null -eq $prop){return $null}
    return $prop.Value
}

function Get-VibeMQL5BuildProvenance {
    param([Parameter(Mandatory)][string]$Root)
    $path=Join-Path $Root 'config\build-provenance.json'
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "BRIDGE_PROVENANCE_MISSING: $path"}
    $p=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if(-not $p.bridge_build -or -not $p.bridge_version){throw 'BRIDGE_PROVENANCE_INVALID'}
    $catalog=Get-VibeMQL5McpCatalogAuthority -Root $Root
    foreach($key in @('mcp_tool_count','mcp_tool_catalog_sha256','mcp_tool_catalog_source')){
        if($p.PSObject.Properties[$key]){$p.PSObject.Properties[$key].Value=$catalog[$key]}
        else{$p|Add-Member -NotePropertyName $key -NotePropertyValue $catalog[$key]}
    }
    return $p
}

function Get-VibeMQL5ProducerProvenance {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Component,
        [string]$Schema='1.0'
    )
    $resolved=(Resolve-Path -LiteralPath $Path).Path
    $sha=(Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
    [ordered]@{
        producer_component=$Component
        producer_schema=$Schema
        producer_build=('sha256:'+ $sha.Substring(0,12))
        producer_sha256=$sha
    }
}

function Test-VibeMQL5StateProvenance {
    param(
        [Parameter(Mandatory)][object]$State,
        [Parameter(Mandatory)][object]$Bridge,
        [Parameter(Mandatory)][object]$Producer
    )
    $reasons=@()
    if([string]$State.bridge_build -ne [string]$Bridge.bridge_build){$reasons+='BRIDGE_BUILD_STALE'}
    if([string]$State.bridge_version -ne [string]$Bridge.bridge_version){$reasons+='BRIDGE_VERSION_STALE'}
    $stateToolCount=Get-VibeMQL5ObjectProperty -Object $State -Name 'mcp_tool_count'
    $bridgeToolCount=Get-VibeMQL5ObjectProperty -Object $Bridge -Name 'mcp_tool_count'
    if($null -eq $stateToolCount -or $null -eq $bridgeToolCount -or [int]$stateToolCount -ne [int]$bridgeToolCount){$reasons+='MCP_TOOL_COUNT_STALE'}
    $stateCatalogSha=[string](Get-VibeMQL5ObjectProperty -Object $State -Name 'mcp_tool_catalog_sha256')
    $bridgeCatalogSha=[string](Get-VibeMQL5ObjectProperty -Object $Bridge -Name 'mcp_tool_catalog_sha256')
    if($stateCatalogSha.ToLowerInvariant() -ne $bridgeCatalogSha.ToLowerInvariant()){$reasons+='MCP_TOOL_CATALOG_SHA_STALE'}
    if([string]$State.producer_component -ne [string]$Producer.producer_component){$reasons+='PRODUCER_COMPONENT_MISMATCH'}
    if([string]$State.producer_sha256 -ne [string]$Producer.producer_sha256){$reasons+='PRODUCER_SHA_STALE'}
    if([string]$State.producer_build -ne [string]$Producer.producer_build){$reasons+='PRODUCER_BUILD_STALE'}
    [ordered]@{fresh=($reasons.Count -eq 0);reasons=@($reasons)}
}
