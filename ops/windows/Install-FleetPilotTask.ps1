$ErrorActionPreference = 'Stop'
$pilotRoot = 'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a'
$runtime = Join-Path $pilotRoot 'runtime'
$runner = Join-Path $pilotRoot 'operator-run-pilot.py'
$taskName = 'VibeMQL5-Fleet-Pilot-745147f'
if ((Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a17897040d9a1728269096c166a2564df7cc68edde7a80955ba7dabf079c6c1e') { throw 'RUNNER_HASH_MISMATCH' }
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'PILOT_TASK_ALREADY_EXISTS' }
$closed = Get-Content -LiteralPath (Join-Path $runtime 'STOP-RECEIPT.json') -Raw | ConvertFrom-Json
if ($closed.pid -ne 2604 -or $closed.status -ne 'STOPPED') { throw 'PILOT_CLOSURE_NOT_CONFIRMED' }
if (Get-Process -Id 2604 -ErrorAction SilentlyContinue) { throw 'OLD_PILOT_PROCESS_PRESENT' }
if (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {$_.LocalPort -eq 8443}) { throw 'PILOT_PORT_IN_USE' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-ScheduledTaskPrincipal -UserId $identity.User.Value -LogonType Interactive -RunLevel Highest
$action = New-ScheduledTaskAction -Execute 'C:\VibeMQL5\.venv\Scripts\python.exe' -Argument ('-u "' + $runner + '" --resume') -WorkingDirectory $pilotRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Isolated one-VPS Fleet pilot; reopen existing journals only, native/SDK/writer qualification disabled.'
Register-ScheduledTask -TaskName $taskName -InputObject $task -ErrorAction Stop | Out-Null
Move-Item -LiteralPath (Join-Path $runtime 'STOP') -Destination (Join-Path $runtime 'STOP-INITIAL-GRACEFUL') -ErrorAction Stop
Start-ScheduledTask -TaskName $taskName
[ordered]@{task_name=$taskName;user=$identity.Name;logon_type='Interactive';trigger='AtLogOn';mode='--resume';automatic_restart=$false;state=(Get-ScheduledTask -TaskName $taskName).State.ToString();at_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'TASK-INSTALL-RECEIPT.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $runtime 'TASK-INSTALL-RECEIPT.json') -Raw
