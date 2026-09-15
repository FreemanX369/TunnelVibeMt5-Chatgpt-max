[CmdletBinding()]
param([string]$ConfigPath = "$PSScriptRoot\vibemql5.windows.json")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$config = Get-Content -LiteralPath (Resolve-Path $ConfigPath).Path -Raw -Encoding UTF8 | ConvertFrom-Json
$sessionId = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
if ($sessionId -eq 0) { throw "MT5_INTERACTIVE_SESSION_REQUIRED: logon entry started in Session 0" }

$backgroundName = [string]$config.tasks.backgroundTunnelTaskName
if ($backgroundName) { Stop-ScheduledTask -TaskName $backgroundName -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500

$expected = [IO.Path]::GetFullPath([string]$config.tunnel.executable)
$profile = [string]$config.tunnel.profile
$profilePattern = '--profile(?:\s+|=)"?' + [regex]::Escape($profile) + '"?(?:\s|$)'
$procs = @(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected) -and $_.CommandLine -and $_.CommandLine -match $profilePattern
})
foreach ($proc in $procs) {
    & taskkill.exe /PID ([string]$proc.ProcessId) /T /F | Out-Null
}
for ($i=0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 250
    $left = @(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected) -and $_.CommandLine -and $_.CommandLine -match $profilePattern
    })
    if ($left.Count -eq 0) { break }
}
if ($left.Count -ne 0) { throw "INTERACTIVE_TAKEOVER_FAILED: stale configured tunnel remains" }

& (Join-Path $PSScriptRoot "Start-VibeMQL5TunnelSupervisor.ps1") -ConfigPath $ConfigPath -Mode interactive
exit $LASTEXITCODE
