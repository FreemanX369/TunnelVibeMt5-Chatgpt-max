[CmdletBinding()]
param(
    [string]$ConfigPath = "$PSScriptRoot\vibemql5.windows.json",
    [ValidateSet("interactive","background")][string]$Mode = "interactive",
    [switch]$Once
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-VibeConfig {
    param([Parameter(Mandatory)][string]$Path)
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    Get-Content -LiteralPath $resolved -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-VibeLog {
    param([Parameter(Mandatory)][string]$Path,[Parameter(Mandatory)][string]$Message)
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
    $safe = $Message -replace 'sk-[A-Za-z0-9_-]{16,}', '[REDACTED_KEY]'
    Add-Content -LiteralPath $Path -Encoding UTF8 -Value ("{0:o} {1}" -f [DateTime]::UtcNow,$safe)
}

. (Join-Path $PSScriptRoot 'VibeMQL5.AtomicFile.ps1')
function Write-AtomicJson { param([string]$Path,[object]$Value) Write-VibeAtomicJson -Path $Path -Value $Value -Depth 10 }

function Read-DpapiSecret {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Encrypted runtime key not found: $Path" }
    $secure = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertTo-SecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-HttpStatus {
    param([Parameter(Mandatory)][string]$Url)
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return [int]$r.StatusCode
    } catch {
        try { return [int]$_.Exception.Response.StatusCode.value__ } catch { return 0 }
    }
}

function Tail-Redacted {
    param([string]$Path,[int]$Count=20)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    @(Get-Content -LiteralPath $Path -Tail $Count -Encoding UTF8 | ForEach-Object { $_ -replace 'sk-[A-Za-z0-9_-]{16,}', '[REDACTED_KEY]' })
}

. (Join-Path $PSScriptRoot 'VibeMQL5.Provenance.ps1')
$config = Read-VibeConfig -Path $ConfigPath
$root = Get-VibeMQL5RootFromConfigPath -ConfigPath $ConfigPath
$bridgeProvenance = Get-VibeMQL5BuildProvenance -Root $root
$producerProvenance = Get-VibeMQL5ProducerProvenance -Path $PSCommandPath -Component 'tunnel-supervisor'
$sessionId = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
if ($Mode -eq "interactive" -and $sessionId -eq 0) {
    throw "MT5_INTERACTIVE_SESSION_REQUIRED: interactive supervisor cannot run in Session 0"
}
if (-not (Test-Path -LiteralPath $config.tunnel.executable -PathType Leaf)) { throw "tunnel-client missing: $($config.tunnel.executable)" }

$generation = [guid]::NewGuid().ToString("N")
$runtimeKey = Read-DpapiSecret -Path $config.tunnel.secretFile
$delay = [int]$config.tunnel.restartDelaySeconds
$maxDelay = [int]$config.tunnel.maxRestartDelaySeconds
$pollSeconds = [Math]::Max(1,[int]$config.supervisor.healthPollSeconds)
$heartbeatSeconds = [Math]::Max(2,[int]$config.supervisor.heartbeatSeconds)
$stableResetSeconds = [Math]::Max(30,[int]$config.supervisor.stableResetSeconds)
$maxRestarts = [Math]::Max(1,[int]$config.supervisor.maxRestartsPerHour)
$circuitSeconds = [Math]::Max(60,[int]$config.supervisor.circuitBreakSeconds)
$restartHistory = New-Object System.Collections.ArrayList
$lastExitCode = $null

function Publish-State {
    param(
        [string]$Status,
        [int]$TunnelPid = 0,
        [int]$Health = 0,
        [int]$Ready = 0,
        [int]$ConsecutiveReady = 0,
        [datetime]$ChildStarted = [datetime]::MinValue,
        [datetime]$CircuitUntil = [datetime]::MinValue
    )
    # O-01 / RETRO-A5: heartbeat counters must be evaluated at publish time.
    # The child can remain healthy in this inner loop for days, so pruning only
    # before a restart makes restart_count_last_hour stale. Keep the backing
    # history intact for circuit-breaker logic and publish a fresh 1-hour view.
    $stateNow = [DateTime]::UtcNow
    $restartWindowStart = $stateNow.AddHours(-1)
    $freshRestartHistory = @(
        $restartHistory | Where-Object { ([datetime]$_) -gt $restartWindowStart }
    )
    $state = [ordered]@{
        schema_version = "1.0"
        bridge_build = [string]$bridgeProvenance.bridge_build
        bridge_version = [string]$bridgeProvenance.bridge_version
        mcp_tool_count = [int]$bridgeProvenance.mcp_tool_count
        mcp_tool_catalog_sha256 = [string]$bridgeProvenance.mcp_tool_catalog_sha256
        mcp_tool_catalog_source = [string]$bridgeProvenance.mcp_tool_catalog_source
        producer_component = [string]$producerProvenance.producer_component
        producer_schema = [string]$producerProvenance.producer_schema
        producer_build = [string]$producerProvenance.producer_build
        producer_sha256 = [string]$producerProvenance.producer_sha256
        generation = $generation
        mode = $Mode
        status = $Status
        supervisor_pid = $PID
        supervisor_session_id = $sessionId
        tunnel_pid = $TunnelPid
        profile = [string]$config.tunnel.profile
        started_at_utc = $script:supervisorStarted.ToString("o")
        child_started_at_utc = if ($ChildStarted -eq [datetime]::MinValue) { $null } else { $ChildStarted.ToString("o") }
        last_heartbeat_utc = $stateNow.ToString("o")
        healthz_status = $Health
        readyz_status = $Ready
        consecutive_ready = $ConsecutiveReady
        restart_window_seconds = 3600
        restart_history_as_of_utc = $stateNow.ToString("o")
        restart_history_source = "tunnel-supervisor-process-memory"
        restart_count_last_hour = @($freshRestartHistory).Count
        restart_history_utc = @($freshRestartHistory | ForEach-Object { ([datetime]$_).ToString("o") })
        restart_delay_seconds = $delay
        last_exit_code = $lastExitCode
        circuit_open_until_utc = if ($CircuitUntil -eq [datetime]::MinValue) { $null } else { $CircuitUntil.ToString("o") }
    }
    Write-AtomicJson -Path $config.supervisor.stateFile -Value $state
}

$supervisorStarted = [DateTime]::UtcNow
try {
    $env:CONTROL_PLANE_API_KEY = $runtimeKey
    $env:VIBEMQL5_RUNTIME_MODE = $Mode
    $env:VIBEMQL5_SUPERVISOR_GENERATION = $generation
    $env:VIBEMQL5_SUPERVISOR_SESSION_ID = [string]$sessionId
    Publish-State -Status "STARTING"

    do {
        $now = [DateTime]::UtcNow
        for ($i=$restartHistory.Count-1; $i -ge 0; $i--) {
            if (($now - [datetime]$restartHistory[$i]).TotalHours -ge 1) { $restartHistory.RemoveAt($i) }
        }
        if ($restartHistory.Count -ge $maxRestarts) {
            $until = [DateTime]::UtcNow.AddSeconds($circuitSeconds)
            Write-VibeLog -Path $config.logs.supervisorLog -Message "Circuit open mode=$Mode restarts=$($restartHistory.Count) until=$($until.ToString('o'))"
            Publish-State -Status "CIRCUIT_OPEN" -CircuitUntil $until
            while ([DateTime]::UtcNow -lt $until) {
                Start-Sleep -Seconds ([Math]::Min($heartbeatSeconds,10))
                Publish-State -Status "CIRCUIT_OPEN" -CircuitUntil $until
            }
            [void]$restartHistory.Clear()
            $delay = [int]$config.tunnel.restartDelaySeconds
        }

        $stdoutPath = Join-Path $config.logs.directory ("tunnel-stdout.{0}.log" -f $generation)
        $stderrPath = Join-Path $config.logs.directory ("tunnel-stderr.{0}.log" -f $generation)
        Write-VibeLog -Path $config.logs.supervisorLog -Message "Starting tunnel profile=$($config.tunnel.profile) mode=$Mode generation=$generation session=$sessionId"
        $process = Start-Process -FilePath $config.tunnel.executable `
            -ArgumentList @($config.tunnel.arguments | ForEach-Object { [string]$_ }) `
            -WorkingDirectory (Split-Path -Parent $config.tunnel.executable) `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $childStarted = [DateTime]::UtcNow
        [void]$restartHistory.Add($childStarted)
        $consecutiveReady = 0
        $lastHeartbeat = [datetime]::MinValue
        $announcedReady = $false

        while (-not $process.HasExited) {
            $health = Get-HttpStatus -Url $config.supervisor.healthUrl
            $ready = Get-HttpStatus -Url $config.supervisor.readyUrl
            if ($health -eq 200 -and $ready -eq 200) { $consecutiveReady++ } else { $consecutiveReady = 0 }
            if ($consecutiveReady -ge 2 -and -not $announcedReady) {
                Write-VibeLog -Path $config.logs.supervisorLog -Message "Tunnel ready pid=$($process.Id) mode=$Mode generation=$generation"
                $announcedReady = $true
            }
            if (([DateTime]::UtcNow - $lastHeartbeat).TotalSeconds -ge $heartbeatSeconds) {
                Publish-State -Status $(if ($consecutiveReady -ge 2) { "READY" } else { "STARTING" }) -TunnelPid $process.Id -Health $health -Ready $ready -ConsecutiveReady $consecutiveReady -ChildStarted $childStarted
                $lastHeartbeat = [DateTime]::UtcNow
            }
            if (([DateTime]::UtcNow - $childStarted).TotalSeconds -ge $stableResetSeconds -and $consecutiveReady -ge 2) {
                $delay = [int]$config.tunnel.restartDelaySeconds
            }
            Start-Sleep -Seconds $pollSeconds
            $process.Refresh()
        }

        $lastExitCode = [int]$process.ExitCode
        $runtimeSeconds = ([DateTime]::UtcNow - $childStarted).TotalSeconds
        Publish-State -Status "EXITED" -Health 0 -Ready 0 -ChildStarted $childStarted
        Write-VibeLog -Path $config.logs.supervisorLog -Message "Tunnel exited pid=$($process.Id) code=$lastExitCode runtime_seconds=$([Math]::Round($runtimeSeconds,1))"
        foreach ($line in (Tail-Redacted -Path $stderrPath -Count 20)) { Write-VibeLog -Path $config.logs.supervisorLog -Message ("stderr: " + $line) }
        if ($Once) { exit $lastExitCode }
        Start-Sleep -Seconds $delay
        $delay = [Math]::Min($delay * 2,$maxDelay)
    } while ($true)
}
finally {
    try { Publish-State -Status "STOPPED" } catch { }
    Remove-Item Env:\CONTROL_PLANE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\VIBEMQL5_RUNTIME_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:\VIBEMQL5_SUPERVISOR_GENERATION -ErrorAction SilentlyContinue
    Remove-Item Env:\VIBEMQL5_SUPERVISOR_SESSION_ID -ErrorAction SilentlyContinue
    $runtimeKey = $null
}
