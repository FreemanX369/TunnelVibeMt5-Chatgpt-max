[CmdletBinding()]
param(
    [string]$ConfigPath = "$PSScriptRoot\vibemql5.windows.json",
    [int]$DurationMinutes = 60,
    [int]$SampleSeconds = 30,
    [int]$MaxConsecutiveBad = 4
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if($DurationMinutes-lt 5){throw 'TIP013_SOAK_MINIMUM_5_MINUTES'};if($SampleSeconds-lt 5){throw 'TIP013_SOAK_SAMPLE_TOO_FAST'}
function Read-JsonSafe{param([string]$Path)try{if(Test-Path -LiteralPath $Path){return Get-Content -LiteralPath $Path -Raw -Encoding UTF8|ConvertFrom-Json}}catch{};return $null}
. (Join-Path $PSScriptRoot 'VibeMQL5.AtomicFile.ps1')
function Write-AtomicJson{param([string]$Path,[object]$Value) Write-VibeAtomicJson -Path $Path -Value $Value -Depth 16}
function Get-HttpStatus{param([string]$Url)try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2).StatusCode}catch{return 0}}
function Get-ExactTunnel{param([string]$Exe)$expected=[IO.Path]::GetFullPath($Exe);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath)-ieq $expected)})}
function Get-ExactMcp{param([string]$Python)$expected=[IO.Path]::GetFullPath($Python);@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{($_.Name -ieq 'python.exe' -or $_.Name -ieq 'pythonw.exe') -and $_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath)-ieq $expected) -and ([string]$_.CommandLine -match 'vibemql5\.adapters\.mcp') -and ([string]$_.CommandLine -match '--transport\s+stdio')})}
$config=Get-Content -LiteralPath (Resolve-Path $ConfigPath).Path -Raw -Encoding UTF8|ConvertFrom-Json
$statePath=[string]$config.supervisor.resilienceStateFile
$previous=Read-JsonSafe -Path $statePath
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
$started=[DateTime]::UtcNow;$deadline=$started.AddMinutes($DurationMinutes);$samples=0;$bad=0;$maxBad=0;$badEpisodes=0;$pidChanges=0;$generationChanges=0;$lastTunnel=0;$lastGen='';$observedTunnel=@();$observedGen=@()
while([DateTime]::UtcNow-lt $deadline){
    $samples++;$t=@(Get-ExactTunnel ([string]$config.tunnel.executable));$m=@(Get-ExactMcp ([string]$config.pythonExe));$h=Get-HttpStatus ([string]$config.supervisor.healthUrl);$r=Get-HttpStatus ([string]$config.supervisor.readyUrl);$sup=Read-JsonSafe ([string]$config.supervisor.stateFile);$fresh=$false;if($sup -and $sup.last_heartbeat_utc){try{$fresh=(([DateTime]::UtcNow-[datetime]::Parse([string]$sup.last_heartbeat_utc)).TotalSeconds-lt [int]$config.supervisor.heartbeatStaleSeconds)}catch{}}
    $healthy=($t.Count-eq 1 -and $m.Count-eq 1 -and $h-eq 200 -and $r-eq 200 -and $fresh)
    if($t.Count-eq 1){$tunnelPid=[int]$t[0].ProcessId;if($lastTunnel-ne 0 -and $tunnelPid-ne $lastTunnel){$pidChanges++};$lastTunnel=$tunnelPid;if($observedTunnel -notcontains $tunnelPid){$observedTunnel+=$tunnelPid}}
    $gen=if($sup){[string]$sup.generation}else{''};if($lastGen -and $gen -and $gen-ne $lastGen){$generationChanges++};if($gen){$lastGen=$gen;if($observedGen -notcontains $gen){$observedGen+=$gen}}
    if($healthy){$bad=0}else{if($bad-eq 0){$badEpisodes++};$bad++;$maxBad=[Math]::Max($maxBad,$bad)}
    $out=[ordered]@{schema_version='1.0';bridge_build='TIP-013';last_scenario='Soak';last_status=if($bad-gt $MaxConsecutiveBad){'FAIL'}else{'RUNNING'};updated_at_utc=[DateTime]::UtcNow.ToString('o');last_result=[ordered]@{scenario='Soak';status=if($bad-gt $MaxConsecutiveBad){'FAIL'}else{'RUNNING'};started_at_utc=$started.ToString('o');evidence=[ordered]@{duration_minutes=$DurationMinutes;sample_seconds=$SampleSeconds;samples=$samples;current_healthy=$healthy;consecutive_bad=$bad;max_consecutive_bad=$maxBad;bad_episodes=$badEpisodes;tunnel_pid_changes=$pidChanges;generation_changes=$generationChanges;observed_tunnel_pids=$observedTunnel;observed_generations=$observedGen;healthz=$h;readyz=$r;heartbeat_fresh=$fresh}};history=$history}
    Write-AtomicJson -Path $statePath -Value $out
    if($bad-gt $MaxConsecutiveBad){throw "TIP013_SOAK_SUSTAINED_DEGRADATION consecutive_bad=$bad"}
    Start-Sleep -Seconds $SampleSeconds
}
$t=@(Get-ExactTunnel ([string]$config.tunnel.executable));$m=@(Get-ExactMcp ([string]$config.pythonExe));$h=Get-HttpStatus ([string]$config.supervisor.healthUrl);$r=Get-HttpStatus ([string]$config.supervisor.readyUrl);$sup=Read-JsonSafe ([string]$config.supervisor.stateFile);$fresh=$false;if($sup -and $sup.last_heartbeat_utc){try{$fresh=(([DateTime]::UtcNow-[datetime]::Parse([string]$sup.last_heartbeat_utc)).TotalSeconds-lt [int]$config.supervisor.heartbeatStaleSeconds)}catch{}};$healthy=($t.Count-eq 1 -and $m.Count-eq 1 -and $h-eq 200 -and $r-eq 200 -and $fresh);if(-not $healthy){throw 'TIP013_SOAK_FINAL_HEALTH_FAILED'}
$finalEntry=[ordered]@{scenario='Soak';status='PASS';started_at_utc=$started.ToString('o');finished_at_utc=[DateTime]::UtcNow.ToString('o');evidence=[ordered]@{duration_minutes=$DurationMinutes;sample_seconds=$SampleSeconds;samples=$samples;max_consecutive_bad=$maxBad;bad_episodes=$badEpisodes;tunnel_pid_changes=$pidChanges;generation_changes=$generationChanges;observed_tunnel_pids=$observedTunnel;observed_generations=$observedGen;final_healthz=$h;final_readyz=$r;final_heartbeat_fresh=$fresh}}
$history+=@($finalEntry);if($history.Count-gt 20){$history=@($history|Select-Object -Last 20)}
$final=[ordered]@{schema_version='1.0';bridge_build='TIP-013';last_scenario='Soak';last_status='PASS';updated_at_utc=[DateTime]::UtcNow.ToString('o');last_result=$finalEntry;history=$history}
Write-AtomicJson -Path $statePath -Value $final;$final|ConvertTo-Json -Depth 16;Write-Host 'TIP013_SOAK=PASS'
