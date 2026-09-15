[CmdletBinding(SupportsShouldProcess)]
param(
 [string]$ConfigPath,
 [PSCredential]$Credential,
 [switch]$EnableBootTunnel,
 [switch]$InteractiveLogon,
 [switch]$BackgroundTunnelOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if([string]::IsNullOrWhiteSpace($ConfigPath)){$ConfigPath=Join-Path $PSScriptRoot "vibemql5.windows.json"}
$configPathResolved=(Resolve-Path -LiteralPath $ConfigPath).Path
$config=Get-Content -LiteralPath $configPathResolved -Raw -Encoding UTF8|ConvertFrom-Json
$pwsh=(Get-Command powershell.exe).Source
$userId=if($env:USERDOMAIN){"{0}\{1}" -f $env:USERDOMAIN,$env:USERNAME}else{$env:USERNAME}

$interactiveEntry=Join-Path $PSScriptRoot "Start-VibeMQL5InteractiveEntry.ps1"
$supervisor=Join-Path $PSScriptRoot "Start-VibeMQL5TunnelSupervisor.ps1"
$watchdog=Join-Path $PSScriptRoot "Invoke-VibeMQL5Watchdog.ps1"
foreach($required in @($interactiveEntry,$supervisor,$watchdog)){
    if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "TIP034_BOOTSTRAP_PREREQUISITE_MISSING: $required"}
}

$action="persist non-secret deployment metadata and register VibeMQL5 scheduled tasks"
if(-not $PSCmdlet.ShouldProcess($configPathResolved,$action)){
    Write-Host 'TIP034_BOOTSTRAP_DRY_RUN=PASS'
    Write-Host "INSTALL_ROOT=$($config.installRoot)"
    Write-Host "PYTHON_EXE=$($config.pythonExe)"
    Write-Host "TUNNEL_EXECUTABLE=$($config.tunnel.executable)"
    Write-Host "TUNNEL_PROFILE=$($config.tunnel.profile)"
    Write-Host "SECRET_FILE_REFERENCE=$($config.tunnel.secretFile)"
    Write-Host 'SECRET_PROVISIONING=EXTERNAL_REQUIRED'
    Write-Host "INTERACTIVE_TASK=$($config.tasks.tunnelTaskName)"
    Write-Host "WATCHDOG_TASK=$($config.tasks.watchdogTaskName)"
    Write-Host "BACKGROUND_TASK=$($config.tasks.backgroundTunnelTaskName)"
    Write-Host "ENABLE_BOOT_TUNNEL=$([bool]$EnableBootTunnel)"
    return
}

# Persist only non-secret deployment mode metadata.
$config.tasks.interactiveUser=$userId
$config.tasks.enableBootTunnel=[bool]$EnableBootTunnel
$utf8=New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($configPathResolved,($config|ConvertTo-Json -Depth 10),$utf8)

$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$intAction=New-ScheduledTaskAction -Execute $pwsh -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`" -ConfigPath `"{1}`"" -f $interactiveEntry,$configPathResolved) -WorkingDirectory $PSScriptRoot
$intTrigger=New-ScheduledTaskTrigger -AtLogOn -User $userId
$intPrincipal=New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName) -Action $intAction -Trigger $intTrigger -Settings $settings -Principal $intPrincipal -Force|Out-Null
Write-Host "Interactive tunnel task installed: $($config.tasks.tunnelTaskName) user=$userId"

$backgroundName=[string]$config.tasks.backgroundTunnelTaskName
if($EnableBootTunnel){
    if($null -eq $Credential){ $Credential=Get-Credential -UserName $userId -Message "Windows credential for pre-logon background boot tunnel (stored by Windows Task Scheduler)" }
    $bgAction=New-ScheduledTaskAction -Execute $pwsh -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`" -ConfigPath `"{1}`" -Mode background" -f $supervisor,$configPathResolved) -WorkingDirectory $PSScriptRoot
    $bgTrigger=New-ScheduledTaskTrigger -AtStartup
    Register-ScheduledTask -TaskName $backgroundName -Action $bgAction -Trigger $bgTrigger -Settings $settings -User $Credential.UserName -Password $Credential.GetNetworkCredential().Password -RunLevel Highest -Force|Out-Null
    Write-Host "Background boot tunnel task installed: $backgroundName"
}else{
    Unregister-ScheduledTask -TaskName $backgroundName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Background boot tunnel: DISABLED"
}

$wdAction=New-ScheduledTaskAction -Execute $pwsh -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`" -ConfigPath `"{1}`"" -f $watchdog,$configPathResolved) -WorkingDirectory $PSScriptRoot
$wdStartup=New-ScheduledTaskTrigger -AtStartup
$wdRepeat=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes ([int]$config.tasks.watchdogIntervalMinutes))
$wdPrincipal=New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName ([string]$config.tasks.watchdogTaskName) -Action $wdAction -Trigger @($wdStartup,$wdRepeat) -Settings $settings -Principal $wdPrincipal -Force|Out-Null
Write-Host "Watchdog installed: $($config.tasks.watchdogTaskName)"
Write-Host "TIP012_TASK_INSTALL=PASS"
