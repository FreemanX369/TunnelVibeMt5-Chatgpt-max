[CmdletBinding()]
param(
    [string]$ConfigPath = "$PSScriptRoot\vibemql5.windows.json",
    [switch]$ObserveOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'VibeMQL5.AtomicFile.ps1')
function Write-AtomicJson { param([string]$Path,[object]$Value) Write-VibeAtomicJson -Path $Path -Value $Value -Depth 10 }
function Read-JsonSafe { param([string]$Path) try { if(Test-Path -LiteralPath $Path){ return Get-Content -LiteralPath $Path -Raw -Encoding UTF8|ConvertFrom-Json } } catch{}; return $null }
function Get-HttpStatus { param([string]$Url) try { return [int](Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2).StatusCode } catch { return 0 } }
function Get-ExactTunnelProcess {
    param([string]$Executable,[string]$Profile)
    $expected=[IO.Path]::GetFullPath($Executable)
    $pattern='--profile(?:\s+|=)"?'+[regex]::Escape($Profile)+'"?(?:\s|$)'
    @(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{
        $_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected) -and $_.CommandLine -and $_.CommandLine -match $pattern
    })
}
function Test-InteractiveUserSession {
    param([string]$UserId)
    if (-not $UserId) { return $false }
    $parts=$UserId.Split('\\',2); $domain=if($parts.Count -eq 2){$parts[0]}else{$env:USERDOMAIN}; $name=if($parts.Count -eq 2){$parts[1]}else{$parts[0]}
    foreach($proc in @(Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" -ErrorAction SilentlyContinue)){
        try { $owner=Invoke-CimMethod -InputObject $proc -MethodName GetOwner -ErrorAction Stop; if($owner.User -ieq $name -and (($owner.Domain -ieq $domain) -or -not $domain) -and [int]$proc.SessionId -ne 0){ return $true } } catch{}
    }
    return $false
}

. (Join-Path $PSScriptRoot 'VibeMQL5.Provenance.ps1')
$config=Get-Content -LiteralPath (Resolve-Path $ConfigPath).Path -Raw -Encoding UTF8|ConvertFrom-Json
$root=Get-VibeMQL5RootFromConfigPath -ConfigPath $ConfigPath
$bridgeProvenance=Get-VibeMQL5BuildProvenance -Root $root
$producerProvenance=Get-VibeMQL5ProducerProvenance -Path $PSCommandPath -Component 'watchdog'
$super=Read-JsonSafe -Path $config.supervisor.stateFile
$previous=Read-JsonSafe -Path $config.supervisor.watchdogStateFile
$health=Get-HttpStatus -Url $config.supervisor.healthUrl
$ready=Get-HttpStatus -Url $config.supervisor.readyUrl
$exact=@(Get-ExactTunnelProcess -Executable $config.tunnel.executable -Profile ([string]$config.tunnel.profile))
$heartbeatFresh=$false
if($super -and $super.last_heartbeat_utc){ try{$heartbeatFresh=(([DateTime]::UtcNow-[datetime]::Parse([string]$super.last_heartbeat_utc)).TotalSeconds -lt [int]$config.supervisor.heartbeatStaleSeconds)}catch{} }
$interactiveAvailable=Test-InteractiveUserSession -UserId ([string]$config.tasks.interactiveUser)
$bootEnabled=[bool]$config.tasks.enableBootTunnel
$desired=if($interactiveAvailable){"interactive"}elseif($bootEnabled){"background"}else{"waiting"}
$healthy=($exact.Count -eq 1 -and $health -eq 200 -and $ready -eq 200 -and $heartbeatFresh -and $super -and [string]$super.mode -eq $desired)

$history=@()
if($previous -and $previous.restart_history_utc){ $history=@($previous.restart_history_utc) }
$cutoff=[DateTime]::UtcNow.AddHours(-1)
$history=@($history|Where-Object{ try{ [datetime]::Parse([string]$_) -gt $cutoff }catch{$false} })
$lastRestart=$null
if($history.Count -gt 0){ try{$lastRestart=[datetime]::Parse([string]$history[-1])}catch{} }
$cooldownOk=($null -eq $lastRestart -or ([DateTime]::UtcNow-$lastRestart).TotalSeconds -ge [int]$config.supervisor.watchdogRestartCooldownSeconds)
$budgetOk=($history.Count -lt [int]$config.supervisor.maxRestartsPerHour)
$action="NONE"; $status=if($healthy){"HEALTHY"}else{"DEGRADED"}

if(-not $healthy){
    if($desired -eq "waiting"){
        $status="WAITING_FOR_INTERACTIVE_LOGON"; $action="DEFER"
    } elseif(-not $budgetOk){
        $status="CIRCUIT_OPEN"; $action="DEFER_RESTART_BUDGET"
    } elseif(-not $cooldownOk){
        $status="RESTART_COOLDOWN"; $action="DEFER_COOLDOWN"
    } elseif($ObserveOnly){
        $action="WOULD_RESTART_$($desired.ToUpperInvariant())"
    } else {
        if($desired -eq "interactive"){
            Stop-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName) -ErrorAction SilentlyContinue
            Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)
            $action="START_INTERACTIVE"
        } else {
            Stop-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName) -ErrorAction SilentlyContinue
            Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)
            $action="START_BACKGROUND"
        }
        $history += [DateTime]::UtcNow.ToString("o")
        $status="RECOVERY_TRIGGERED"
    }
}

$superGeneration=if($super){[string]$super.generation}else{""}
$superMode=if($super){[string]$super.mode}else{""}
$out=[ordered]@{
 schema_version="1.0"; bridge_build=[string]$bridgeProvenance.bridge_build; bridge_version=[string]$bridgeProvenance.bridge_version;
 mcp_tool_count=[int]$bridgeProvenance.mcp_tool_count; mcp_tool_catalog_sha256=[string]$bridgeProvenance.mcp_tool_catalog_sha256; mcp_tool_catalog_source=[string]$bridgeProvenance.mcp_tool_catalog_source;
 producer_component=[string]$producerProvenance.producer_component; producer_schema=[string]$producerProvenance.producer_schema;
 producer_build=[string]$producerProvenance.producer_build; producer_sha256=[string]$producerProvenance.producer_sha256;
 observed_at_utc=[DateTime]::UtcNow.ToString("o"); status=$status; action=$action;
 desired_mode=$desired; interactive_session_available=$interactiveAvailable; boot_tunnel_enabled=$bootEnabled;
 exact_tunnel_process_count=$exact.Count; exact_tunnel_pids=@($exact|ForEach-Object{[int]$_.ProcessId}); healthz_status=$health; readyz_status=$ready;
 supervisor_heartbeat_fresh=$heartbeatFresh; supervisor_generation=$superGeneration; supervisor_mode=$superMode;
 restart_history_utc=@($history); restart_count_last_hour=@($history).Count
}
Write-AtomicJson -Path $config.supervisor.watchdogStateFile -Value $out
$out | ConvertTo-Json -Depth 10
if($ObserveOnly){ Write-Host "TIP012_WATCHDOG_OBSERVE=PASS" }
