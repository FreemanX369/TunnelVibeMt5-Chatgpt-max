param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string]$ReceiptPath,
  [Parameter(Mandatory=$true)][string]$Components,
  [int]$WaitReadySeconds = 15
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Receipt([string]$Status, [hashtable]$Extra) {
    $obj = [ordered]@{
        schema_version = "1.2"
        status = $Status
        at = (Get-Date).ToString("o")
        controller_pid = $PID
        components = $Components
        terminal_touched = $false
    }
    foreach($k in $Extra.Keys){ $obj[$k] = $Extra[$k] }
    $dir = Split-Path $ReceiptPath -Parent
    New-Item -ItemType Directory -Force $dir | Out-Null
    $tmp = "$ReceiptPath.tmp-$PID"
    $json = $obj | ConvertTo-Json -Depth 8
    $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$json)
    [System.IO.File]::WriteAllBytes([string]$tmp, $bytes)
    Move-Item -LiteralPath $tmp -Destination $ReceiptPath -Force
}

function New-ProcessMap($Rows) {
    $map = @{}
    foreach($r in $Rows) {
        $map[[int]$r.ProcessId] = $r
    }
    return $map
}

function New-ProtectedPidSet($Rows) {
    $protected = @{}
    $protected[[int]$PID] = $true

    foreach($r in $Rows) {
        $name = ([string]$r.Name).ToLowerInvariant()
        if($name -in @('terminal64.exe','metatester64.exe','metaeditor64.exe')) {
            $protected[[int]$r.ProcessId] = $true
        }
    }

    $changed = $true
    while($changed) {
        $changed = $false
        foreach($r in $Rows) {
            $pid0 = [int]$r.ProcessId
            $ppid0 = [int]$r.ParentProcessId
            if((-not $protected.ContainsKey($pid0)) -and $protected.ContainsKey($ppid0)) {
                $protected[$pid0] = $true
                $changed = $true
            }
        }
    }
    return $protected
}

function Stop-ProcessTreeSafe([int]$TargetPid, $Rows, $Protected) {
    if($TargetPid -le 0) { return @() }
    if($Protected.ContainsKey($TargetPid)) {
        throw "RESTART_TARGET_PROTECTED:$TargetPid"
    }

    $depth = @{}
    $depth[$TargetPid] = 0
    $changed = $true
    while($changed) {
        $changed = $false
        foreach($r in $Rows) {
            $pid0 = [int]$r.ProcessId
            $ppid0 = [int]$r.ParentProcessId
            if((-not $depth.ContainsKey($pid0)) -and $depth.ContainsKey($ppid0)) {
                $depth[$pid0] = [int]$depth[$ppid0] + 1
                $changed = $true
            }
        }
    }

    $stopped = @()
    $ordered = @($depth.GetEnumerator() | Sort-Object Value -Descending)
    foreach($entry in $ordered) {
        $pid0 = [int]$entry.Key
        if($Protected.ContainsKey($pid0)) { continue }
        try {
            Stop-Process -Id $pid0 -Force -ErrorAction Stop
            $stopped += $pid0
        } catch {
            if((Get-Process -Id $pid0 -ErrorAction SilentlyContinue) -ne $null) {
                throw
            }
        }
    }
    return $stopped
}

Write-Receipt "STARTED" @{ phase = "controller_started" }
Start-Sleep -Seconds 2

try {
    $wanted = @($Components.Split(",") | Where-Object { $_ })
    foreach($c in $wanted) {
        if($c -notin @("http_mcp","interactive_tunnel")) {
            throw "RESTART_COMPONENT_NOT_ALLOWED:$c"
        }
    }

    $interactiveConfigPath = Join-Path $Root "ops\windows\vibemql5.windows.json"
    $interactiveTaskName = ""
    if($wanted -contains "interactive_tunnel") {
        if(-not (Test-Path -LiteralPath $interactiveConfigPath -PathType Leaf)) {
            throw "INTERACTIVE_CONFIG_MISSING:$interactiveConfigPath"
        }
        $interactiveConfig = Get-Content -LiteralPath $interactiveConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $interactiveTaskName = [string]$interactiveConfig.tasks.tunnelTaskName
        if([string]::IsNullOrWhiteSpace($interactiveTaskName)) {
            throw "INTERACTIVE_TASK_NAME_MISSING"
        }
        Get-ScheduledTask -TaskName $interactiveTaskName -ErrorAction Stop | Out-Null
        Stop-ScheduledTask -TaskName $interactiveTaskName -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }

    $rows = @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine)
    $protected = New-ProtectedPidSet $rows

    $httpTargets = @()
    $interactiveTargets = @()

    if($wanted -contains "http_mcp") {
        $httpTargets = @($rows | Where-Object {
            $_.CommandLine -and $_.CommandLine -match 'run-mcp-task\.ps1' -and [int]$_.ProcessId -ne [int]$PID
        })
    }
    if($wanted -contains "interactive_tunnel") {
        $interactiveTargets = @($rows | Where-Object {
            $_.CommandLine -and $_.CommandLine -match 'Start-VibeMQL5InteractiveEntry\.ps1' -and
            $_.CommandLine -match 'vibemql5\.windows\.json' -and [int]$_.ProcessId -ne [int]$PID
        })
    }

    $stopped = @()
    foreach($p in $httpTargets) {
        $stopped += @(Stop-ProcessTreeSafe ([int]$p.ProcessId) $rows $protected)
    }
    foreach($p in $interactiveTargets) {
        $stopped += @(Stop-ProcessTreeSafe ([int]$p.ProcessId) $rows $protected)
    }

    Start-Sleep -Milliseconds 500

    if($wanted -contains "http_mcp") {
        Start-Process powershell.exe -ArgumentList @(
            '-NoProfile','-ExecutionPolicy','Bypass','-File',
            "$Root\scripts\run-mcp-task.ps1",
            '-Root',$Root,'-HostAddress','127.0.0.1','-Port','8765'
        ) -WindowStyle Hidden
    }

    if($wanted -contains "interactive_tunnel") {
        Start-ScheduledTask -TaskName $interactiveTaskName -ErrorAction Stop
    }

    $deadline = (Get-Date).AddSeconds([Math]::Max(5,[Math]::Min($WaitReadySeconds,60)))
    $ready = $false
    do {
        Start-Sleep -Milliseconds 500
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:8080/readyz" -TimeoutSec 2
            if("$r" -eq "ready") { $ready = $true; break }
        } catch {}
    } while((Get-Date) -lt $deadline)

    if(-not $ready) { throw "READINESS_TIMEOUT" }

    Write-Receipt "PASS" @{
        phase = "restart_complete"
        readyz = "ready"
        stopped_pids = @($stopped | Sort-Object -Unique)
        http_target_pids = @($httpTargets | ForEach-Object { [int]$_.ProcessId })
        interactive_target_pids = @($interactiveTargets | ForEach-Object { [int]$_.ProcessId })
        interactive_task_name = $interactiveTaskName
        interactive_start_method = if($wanted -contains "interactive_tunnel") { "scheduled_task" } else { "not_requested" }
        protected_pid_count = [int]$protected.Count
    }
} catch {
    Write-Receipt "FAIL" @{
        phase = "restart_failed"
        error = $_.Exception.Message
    }
    exit 1
}
