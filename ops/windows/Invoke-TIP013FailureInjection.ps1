[CmdletBinding()]
param(
    [ValidateSet('TunnelCrash','McpCrash','NetworkIsolation','RestartStorm','LongJobTunnelCrash','All')]
    [string]$Scenario = 'TunnelCrash',
    [string]$ConfigPath = "$PSScriptRoot\vibemql5.windows.json",
    [string]$Workspace = 'demo',
    [string]$ExpertPath = 'Experts/DemoEA.mq5',
    [int]$NetworkIsolationSeconds = 0
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Administrator {
    $id=[Security.Principal.WindowsIdentity]::GetCurrent()
    $p=New-Object Security.Principal.WindowsPrincipal($id)
    if(-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){ throw 'TIP013_ADMIN_REQUIRED' }
}
function Read-JsonSafe { param([string]$Path) try{ if(Test-Path -LiteralPath $Path){ return Get-Content -LiteralPath $Path -Raw -Encoding UTF8|ConvertFrom-Json } }catch{}; return $null }
. (Join-Path $PSScriptRoot 'VibeMQL5.AtomicFile.ps1')
function Write-AtomicJson { param([string]$Path,[object]$Value) Write-VibeAtomicJson -Path $Path -Value $Value -Depth 16 }
function Get-HttpStatus { param([string]$Url) try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2).StatusCode}catch{return 0} }
function Get-ExactTunnelProcess { param([string]$Executable) $expected=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath)-ieq $expected)}) }
function Get-ExactMcpProcess {
    param([string]$PythonExe)
    $expected=[IO.Path]::GetFullPath($PythonExe)
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{
        ($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.ExecutablePath -and
        ([IO.Path]::GetFullPath([string]$_.ExecutablePath)-ieq $expected) -and
        ([string]$_.CommandLine -match 'vibemql5\.adapters\.mcp') -and
        ([string]$_.CommandLine -match '--transport\s+stdio')
    })
}
function Get-SupervisorState { Read-JsonSafe -Path ([string]$script:config.supervisor.stateFile) }
function Wait-HealthyRuntime {
    param([int]$TimeoutSeconds,[int]$OldTunnelPid=0,[int]$OldMcpPid=0,[switch]$RequireNewTunnel,[switch]$RequireNewMcp)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $staleSupervisorSnapshots=0
    do{
        $t=@(Get-ExactTunnelProcess -Executable ([string]$script:config.tunnel.executable))
        $m=@(Get-ExactMcpProcess -PythonExe ([string]$script:config.pythonExe))
        $h=Get-HttpStatus -Url ([string]$script:config.supervisor.healthUrl);$r=Get-HttpStatus -Url ([string]$script:config.supervisor.readyUrl)
        $newT=(-not $RequireNewTunnel -or ($t.Count-eq 1 -and [int]$t[0].ProcessId-ne $OldTunnelPid))
        $newM=(-not $RequireNewMcp -or ($m.Count-eq 1 -and [int]$m[0].ProcessId-ne $OldMcpPid))
        $state=Get-SupervisorState
        $stateBound=($state -and $t.Count-eq 1 -and [string]$state.status-eq 'READY' -and [int]$state.tunnel_pid-eq [int]$t[0].ProcessId -and [int]$state.healthz_status-eq 200 -and [int]$state.readyz_status-eq 200 -and [int]$state.restart_count_last_hour-ge 1)
        if($t.Count-eq 1 -and $m.Count-eq 1 -and $h-eq 200 -and $r-eq 200 -and -not $stateBound){$staleSupervisorSnapshots++}
        if($t.Count-eq 1 -and $m.Count-eq 1 -and $h-eq 200 -and $r-eq 200 -and $newT -and $newM -and $stateBound){
            return [pscustomobject]@{tunnel_pid=[int]$t[0].ProcessId;mcp_pid=if($m.Count-eq 1){[int]$m[0].ProcessId}else{0};healthz=$h;readyz=$r;supervisor=$state;supervisor_state_bound=$true;stale_supervisor_snapshots=$staleSupervisorSnapshots}
        }
        Start-Sleep -Seconds 1
    }while([DateTime]::UtcNow-lt $deadline)
    throw 'TIP013_RECOVERY_TIMEOUT'
}
function Assert-NoActiveJob {
    $active=@()
    $runs=Join-Path ([string]$script:config.installRoot) 'runs'
    if(Test-Path -LiteralPath $runs){
        foreach($p in @(Get-ChildItem -LiteralPath $runs -Filter job.json -Recurse -ErrorAction SilentlyContinue)){
            try{$j=Get-Content -LiteralPath $p.FullName -Raw -Encoding UTF8|ConvertFrom-Json;if(@('PASSED','ANOMALY','FAILED','TIMEOUT','CANCELLED','INTERRUPTED','RESOURCE_LIMIT') -notcontains [string]$j.state){$active+=[string]$j.job_id}}catch{}
        }
    }
    if($active.Count -gt 0){throw ('TIP013_ACTIVE_JOB_BLOCKS_INJECTION: '+($active -join ','))}
}
function Save-Result {
    param([string]$Name,[string]$Status,[datetime]$Started,[hashtable]$Evidence,[string]$Error='')
    $previous=Read-JsonSafe -Path $script:statePath
    $history=@()
    if($previous){
        $historyProp=$previous.PSObject.Properties['history']
        if($null -ne $historyProp -and $null -ne $historyProp.Value){
            $history=@($historyProp.Value)
        } else {
            $lastResultProp=$previous.PSObject.Properties['last_result']
            if($null -ne $lastResultProp -and $null -ne $lastResultProp.Value){$history=@($lastResultProp.Value)}
        }
    }
    $entry=[ordered]@{scenario=$Name;status=$Status;started_at_utc=$Started.ToString('o');finished_at_utc=[DateTime]::UtcNow.ToString('o');evidence=$Evidence;error=$Error}
    $history+=@($entry);if($history.Count-gt 20){$history=@($history|Select-Object -Last 20)}
    $out=[ordered]@{schema_version='1.0';bridge_build='TIP-013';last_scenario=$Name;last_status=$Status;updated_at_utc=[DateTime]::UtcNow.ToString('o');last_result=$entry;history=$history}
    Write-AtomicJson -Path $script:statePath -Value $out
    return $out
}
function Invoke-TunnelCrash {
    Assert-NoActiveJob;$started=[DateTime]::UtcNow;$pre=@(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable));if($pre.Count-ne 1){throw "TIP013_EXPECTED_ONE_TUNNEL_FOUND_$($pre.Count)"};$old=[int]$pre[0].ProcessId
    Stop-Process -Id $old -Force -ErrorAction Stop
    $after=Wait-HealthyRuntime -TimeoutSeconds $script:timeout -OldTunnelPid $old -RequireNewTunnel
    $ev=@{old_tunnel_pid=$old;new_tunnel_pid=$after.tunnel_pid;new_mcp_pid=$after.mcp_pid;healthz=$after.healthz;readyz=$after.readyz;exact_tunnel_process_count=1;generation=[string]$after.supervisor.generation}
    Save-Result -Name 'TunnelCrash' -Status 'PASS' -Started $started -Evidence $ev|Out-Null;[pscustomobject]$ev
}
function Invoke-McpCrash {
    Assert-NoActiveJob;$started=[DateTime]::UtcNow;$pre=@(Get-ExactMcpProcess ([string]$script:config.pythonExe));if($pre.Count-ne 1){throw "TIP013_EXPECTED_ONE_MCP_FOUND_$($pre.Count)"};$oldM=[int]$pre[0].ProcessId;$preT=@(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable));$oldT=if($preT.Count-eq 1){[int]$preT[0].ProcessId}else{0}
    Stop-Process -Id $oldM -Force -ErrorAction Stop
    $after=Wait-HealthyRuntime -TimeoutSeconds $script:timeout -OldMcpPid $oldM -RequireNewMcp
    $ev=@{old_mcp_pid=$oldM;new_mcp_pid=$after.mcp_pid;old_tunnel_pid=$oldT;new_tunnel_pid=$after.tunnel_pid;healthz=$after.healthz;readyz=$after.readyz;exact_tunnel_process_count=1}
    Save-Result -Name 'McpCrash' -Status 'PASS' -Started $started -Evidence $ev|Out-Null;[pscustomobject]$ev
}
function Get-GenerationLogText {
    param([string]$Generation)
    $dir=[string]$script:config.logs.directory;$text=''
    foreach($kind in @('stdout','stderr')){$p=Join-Path $dir ("tunnel-$kind.$Generation.log");if(Test-Path -LiteralPath $p){$text+="`n"+(Get-Content -LiteralPath $p -Raw -Encoding UTF8 -ErrorAction SilentlyContinue)}}
    return $text
}
function Invoke-NetworkIsolation {
    Assert-NoActiveJob;$started=[DateTime]::UtcNow;$seconds=if($NetworkIsolationSeconds-gt 0){$NetworkIsolationSeconds}else{[int]$script:config.supervisor.networkIsolationSeconds}
    $state=Get-SupervisorState;if(-not $state){throw 'TIP013_SUPERVISOR_STATE_MISSING'};$generation=[string]$state.generation;$preT=@(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable));if($preT.Count-ne 1){throw 'TIP013_TUNNEL_NOT_SINGLE'};$oldPid=[int]$preT[0].ProcessId
    $token=[guid]::NewGuid().ToString('N');$rule="VibeMQL5-TIP013-NetBlock-$token";$cleanup="VibeMQL5-TIP013-NetCleanup-$token";$cleanupScript=Join-Path ([string]$script:config.installRoot) ("state\tip013-net-cleanup-$token.ps1")
    $utf8=New-Object System.Text.UTF8Encoding($false);$cleanupBody="Remove-NetFirewallRule -DisplayName '$rule' -ErrorAction SilentlyContinue`r`nUnregister-ScheduledTask -TaskName '$cleanup' -Confirm:`$false -ErrorAction SilentlyContinue`r`nRemove-Item -LiteralPath '$cleanupScript' -Force -ErrorAction SilentlyContinue`r`n";[IO.File]::WriteAllText($cleanupScript,$cleanupBody,$utf8)
    $action=New-ScheduledTaskAction -Execute (Get-Command powershell.exe).Source -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $cleanupScript);$trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2);$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;Register-ScheduledTask -TaskName $cleanup -Action $action -Trigger $trigger -Principal $principal -Force|Out-Null
    $degraded=$false;$degradeDetail=''
    try{
        New-NetFirewallRule -DisplayName $rule -Direction Outbound -Program ([string]$script:config.tunnel.executable) -Action Block -Profile Any|Out-Null
        for($i=0;$i-lt $seconds;$i++){
            Start-Sleep -Seconds 1;$h=Get-HttpStatus ([string]$script:config.supervisor.healthUrl);$r=Get-HttpStatus ([string]$script:config.supervisor.readyUrl);$logs=Get-GenerationLogText -Generation $generation
            if($h-ne 200 -or $r-ne 200){$degraded=$true;$degradeDetail="health=$h ready=$r";break}
            if($logs -match 'poll failed|metadata fetch failed|TLS handshake timeout|controlplane.*failed|connection.*failed'){$degraded=$true;$degradeDetail='controlplane failure observed in tunnel log';break}
        }
    }finally{
        Remove-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $cleanup -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $cleanupScript -Force -ErrorAction SilentlyContinue
    }
    $after=Wait-HealthyRuntime -TimeoutSeconds ([int]$script:config.supervisor.networkRecoveryTimeoutSeconds)
    $logsAfter=Get-GenerationLogText -Generation ([string]$after.supervisor.generation);$recoveryLog=($logsAfter -match 'poller recovered|polling operational|tunnel-client started')
    if(-not $degraded){throw 'TIP013_NETWORK_DEGRADATION_NOT_OBSERVED'}
    $ev=@{firewall_rule=$rule;isolation_seconds=$seconds;degraded_observed=$degraded;degraded_detail=$degradeDetail;old_tunnel_pid=$oldPid;new_tunnel_pid=$after.tunnel_pid;healthz=$after.healthz;readyz=$after.readyz;recovery_log_observed=$recoveryLog;cleanup_failsafe_installed=$true;firewall_rule_present_after_test=[bool](Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)}
    if($ev.firewall_rule_present_after_test){throw 'TIP013_FIREWALL_CLEANUP_FAILED'}
    Save-Result -Name 'NetworkIsolation' -Status 'PASS' -Started $started -Evidence $ev|Out-Null;[pscustomobject]$ev
}
function Stop-ActiveSupervisorTaskAndReset {
    param([string]$Mode,[int]$SupervisorPid=0)
    $name=if($Mode-eq 'background'){[string]$script:config.tasks.backgroundTunnelTaskName}else{[string]$script:config.tasks.tunnelTaskName}
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue;Start-Sleep -Seconds 1
    if($SupervisorPid -gt 0){Stop-Process -Id $SupervisorPid -Force -ErrorAction SilentlyContinue}
    foreach($p in @(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable))){Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue}
    Start-Sleep -Seconds 1;Start-ScheduledTask -TaskName $name
}
function Invoke-RestartStorm {
    Assert-NoActiveJob
    $started=[DateTime]::UtcNow
    $initial=Get-SupervisorState
    if(-not $initial){throw 'TIP013_SUPERVISOR_STATE_MISSING'}
    $mode=[string]$initial.mode
    $max=[int]$script:config.supervisor.maxRestartsPerHour
    $watchdogName=[string]$script:config.tasks.watchdogTaskName
    $watchdogTask=Get-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue
    $watchdogWasEnabled=($watchdogTask -and [string]$watchdogTask.State -ne 'Disabled')
    $observed=$false
    $killed=@()
    $restartCounts=@()
    $circuit=$null
    $recovery=$null
    $stormTimeout=[Math]::Max($script:timeout,([int]$script:config.tunnel.maxRestartDelaySeconds+30))

    try {
        if($watchdogTask){
            Stop-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue
            Disable-ScheduledTask -TaskName $watchdogName -ErrorAction Stop | Out-Null
        }

        Stop-ActiveSupervisorTaskAndReset -Mode $mode -SupervisorPid ([int]$initial.supervisor_pid)
        $baseline=Wait-HealthyRuntime -TimeoutSeconds $stormTimeout
        $baselineState=$baseline.supervisor
        if(-not $baselineState){throw 'TIP013_STORM_BASELINE_STATE_MISSING'}
        $baselineGeneration=[string]$baselineState.generation
        $current=[int]$baselineState.restart_count_last_hour
        if($current -lt 1){throw "TIP013_STORM_BASELINE_RESTART_COUNT_INVALID_$current"}
        $restartCounts+=@($current)
        $kills=[Math]::Max(1,($max-$current)+1)

        for($i=0;$i-lt $kills;$i++){
            $t=@(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable))
            if($t.Count-ne 1){throw "TIP013_STORM_EXPECTED_ONE_TUNNEL_FOUND_$($t.Count)"}
            $tunnelPid=[int]$t[0].ProcessId
            $killed+=$tunnelPid
            Stop-Process -Id $tunnelPid -Force -ErrorAction Stop

            $deadline=[DateTime]::UtcNow.AddSeconds($stormTimeout)
            $nextObserved=$false
            do {
                $state=Get-SupervisorState
                if($state -and [string]$state.status -eq 'CIRCUIT_OPEN'){
                    $observed=$true
                    $circuit=$state
                    break
                }
                $nowT=@(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable))
                if($state -and $nowT.Count-eq 1 -and [int]$nowT[0].ProcessId-ne $tunnelPid -and (Get-HttpStatus ([string]$script:config.supervisor.healthUrl))-eq 200){
                    $count=[int]$state.restart_count_last_hour
                    $restartCounts+=@($count)
                    $nextObserved=$true
                    break
                }
                Start-Sleep -Seconds 1
            } while([DateTime]::UtcNow-lt $deadline)

            if($observed){break}
            if(-not $nextObserved){throw "TIP013_STORM_RESTART_NOT_OBSERVED_WITHIN_${stormTimeout}S"}
        }

        if(-not $observed){
            $deadline=[DateTime]::UtcNow.AddSeconds($stormTimeout)
            do {
                $state=Get-SupervisorState
                if($state -and [string]$state.status -eq 'CIRCUIT_OPEN'){$observed=$true;$circuit=$state;break}
                Start-Sleep -Seconds 1
            } while([DateTime]::UtcNow-lt $deadline)
        }
        if(-not $observed){throw 'TIP013_CIRCUIT_OPEN_NOT_OBSERVED'}
    }
    finally {
        $stateNow=Get-SupervisorState
        $supervisorPid=if($stateNow){[int]$stateNow.supervisor_pid}else{0}
        try {
            Stop-ActiveSupervisorTaskAndReset -Mode $mode -SupervisorPid $supervisorPid
            $recovery=Wait-HealthyRuntime -TimeoutSeconds $stormTimeout
        } catch {
            Write-Warning ("TIP013_STORM_RECOVERY_FAILED: " + $_.Exception.Message)
        }
        if($watchdogTask -and $watchdogWasEnabled){
            Enable-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue | Out-Null
            Start-ScheduledTask -TaskName $watchdogName -ErrorAction SilentlyContinue
        }
    }

    if(-not $recovery){throw 'TIP013_STORM_POST_RECOVERY_NOT_HEALTHY'}
    if(-not $circuit){throw 'TIP013_STORM_CIRCUIT_EVIDENCE_MISSING'}
    $ev=@{
        mode=$mode
        baseline_generation=$baselineGeneration
        baseline_restart_count=$current
        baseline_supervisor_state_bound=[bool]$baseline.supervisor_state_bound
        baseline_stale_supervisor_snapshots=[int]$baseline.stale_supervisor_snapshots
        baseline_tunnel_pid=[int]$baseline.tunnel_pid
        killed_tunnel_pids=$killed
        observed_restart_counts=$restartCounts
        configured_max_restarts_per_hour=$max
        observation_timeout_seconds=$stormTimeout
        watchdog_temporarily_disabled=[bool]$watchdogTask
        circuit_open_observed=$true
        circuit_restart_count=[int]$circuit.restart_count_last_hour
        circuit_open_until_utc=[string]$circuit.circuit_open_until_utc
        recovered_after_supervisor_reset=$true
        new_tunnel_pid=$recovery.tunnel_pid
        healthz=$recovery.healthz
        readyz=$recovery.readyz
        exact_tunnel_process_count=1
    }
    Save-Result -Name 'RestartStorm' -Status 'PASS' -Started $started -Evidence $ev|Out-Null
    [pscustomobject]$ev
}
function Invoke-LongJobTunnelCrash {
    $started=[DateTime]::UtcNow;$state=Get-SupervisorState;if(-not $state -or [string]$state.mode-ne 'interactive'){throw 'TIP013_LONG_JOB_REQUIRES_INTERACTIVE_MODE'};Assert-NoActiveJob
    $root=[string]$script:config.installRoot;$python=[string]$script:config.pythonExe
    $code="import json; from pathlib import Path; from vibemql5.core.facade import ToolFacade; print(json.dumps(ToolFacade(Path(r'''$root''')).launch_test('$Workspace', r'''$ExpertPath''', preset='smoke', test_timeout=570)))"
    $raw=& $python -c $code;if($LASTEXITCODE-ne 0){throw 'TIP013_JOB_LAUNCH_FAILED'};$launch=$raw|ConvertFrom-Json;$jobId=[string]$launch.job_id;$jobPath=Join-Path $root ("runs\$jobId\job.json")
    $deadline=[DateTime]::UtcNow.AddSeconds(120);$job=$null
    do{Start-Sleep -Seconds 1;$job=Read-JsonSafe $jobPath;if($job -and @('DEPLOYING','TESTING') -contains [string]$job.state){break};if($job -and @('PASSED','ANOMALY','FAILED','TIMEOUT','CANCELLED','INTERRUPTED','RESOURCE_LIMIT') -contains [string]$job.state){throw "TIP013_JOB_TERMINATED_BEFORE_INJECTION_$($job.state)"}}while([DateTime]::UtcNow-lt $deadline)
    if(-not $job -or @('DEPLOYING','TESTING') -notcontains [string]$job.state){throw 'TIP013_JOB_DID_NOT_REACH_NATIVE_PHASE'}
    $workerPid=[int]$job.worker_pid;$preT=@(Get-ExactTunnelProcess ([string]$script:config.tunnel.executable));if($preT.Count-ne 1){throw 'TIP013_TUNNEL_NOT_SINGLE'};$oldT=[int]$preT[0].ProcessId;Stop-Process -Id $oldT -Force;Start-Sleep -Seconds 1;$workerAliveAfterCrash=[bool](Get-Process -Id $workerPid -ErrorAction SilentlyContinue);if(-not $workerAliveAfterCrash){throw 'TIP013_DETACHED_WORKER_DIED_WITH_TUNNEL'}
    $after=Wait-HealthyRuntime -TimeoutSeconds $script:timeout -OldTunnelPid $oldT -RequireNewTunnel
    $deadline=[DateTime]::UtcNow.AddSeconds(720);do{Start-Sleep -Seconds 2;$job=Read-JsonSafe $jobPath;if($job -and @('PASSED','ANOMALY','FAILED','TIMEOUT','CANCELLED','INTERRUPTED','RESOURCE_LIMIT') -contains [string]$job.state){break}}while([DateTime]::UtcNow-lt $deadline)
    if(-not $job -or @('PASSED','ANOMALY','FAILED','TIMEOUT','CANCELLED','INTERRUPTED','RESOURCE_LIMIT') -notcontains [string]$job.state){throw 'TIP013_LONG_JOB_TIMEOUT'}
    $result=Read-JsonSafe (Join-Path $root ("runs\$jobId\result.json"));if(-not $result){throw 'TIP013_LONG_JOB_RESULT_MISSING'}
    if([string]$job.state-ne 'PASSED' -or [string]$result.tester.execution_status-ne 'PASSED' -or [string]$result.tester.report_status-ne 'PARSED'){throw "TIP013_LONG_JOB_NOT_PASS state=$($job.state) execution=$($result.tester.execution_status) report=$($result.tester.report_status)"}
    $ev=@{job_id=$jobId;worker_pid=$workerPid;worker_alive_after_tunnel_crash=$workerAliveAfterCrash;old_tunnel_pid=$oldT;new_tunnel_pid=$after.tunnel_pid;job_state=[string]$job.state;native_execution=[string]$result.tester.execution_status;report_status=[string]$result.tester.report_status;healthz=$after.healthz;readyz=$after.readyz}
    Save-Result -Name 'LongJobTunnelCrash' -Status 'PASS' -Started $started -Evidence $ev|Out-Null;[pscustomobject]$ev
}

Assert-Administrator
$config=Get-Content -LiteralPath (Resolve-Path $ConfigPath).Path -Raw -Encoding UTF8|ConvertFrom-Json
$statePath=[string]$config.supervisor.resilienceStateFile
$timeout=[int]$config.supervisor.failureInjectionTimeoutSeconds

$scenarios=if($Scenario-eq 'All'){@('TunnelCrash','McpCrash','NetworkIsolation','RestartStorm','LongJobTunnelCrash')}else{@($Scenario)}
$results=@()
foreach($name in $scenarios){
    try{
        switch($name){
            'TunnelCrash' {$results+=Invoke-TunnelCrash}
            'McpCrash' {$results+=Invoke-McpCrash}
            'NetworkIsolation' {$results+=Invoke-NetworkIsolation}
            'RestartStorm' {$results+=Invoke-RestartStorm}
            'LongJobTunnelCrash' {$results+=Invoke-LongJobTunnelCrash}
        }
        Write-Host ("TIP013_{0}=PASS" -f $name.ToUpperInvariant())
    }catch{
        $started=[DateTime]::UtcNow;$ev=@{exception_type=$_.Exception.GetType().FullName};Save-Result -Name $name -Status 'FAIL' -Started $started -Evidence $ev -Error $_.Exception.Message|Out-Null
        throw
    }
}
$results|ConvertTo-Json -Depth 16
