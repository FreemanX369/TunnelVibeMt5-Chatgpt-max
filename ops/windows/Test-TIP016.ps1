[CmdletBinding()]
param(
    [string]$Target='C:\VibeMQL5',
    [string]$ProjectId='TIP014-DEMOEA-E2E-20260830',
    [string]$ExpectedRevision='REV-000004',
    [string]$ExpectedRevisionSha256='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989',
    [string]$ExpectedSourceSha256='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c',
    [Int64]$ExpectedSourceBytes=2026,
    [string]$ExpectedBaselineJobId='BT-20260831-001933-B0484B',
    [string]$ExpectedTip015CClosure='C:\VibeMQL5\evidence\TIP015C-CLOSURE-20260902-000114.zip',
    [string]$ExpectedTip015CClosureSha256='12c8bd59ab54512aaf6fe32c857af93aa4346d9885b3d91f5e25f9a245ec13d5'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$config=Get-Content -LiteralPath (Join-Path $Target 'ops\windows\vibemql5.windows.json') -Raw -Encoding UTF8|ConvertFrom-Json
if((Get-FileHash -LiteralPath $ExpectedTip015CClosure -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedTip015CClosureSha256){throw 'TIP016_TIP015C_CLOSURE_HASH_MISMATCH'}
$env:T16_TARGET=$Target;$env:T16_PROJECT=$ProjectId;$env:T16_REV=$ExpectedRevision;$env:T16_REV_SHA=$ExpectedRevisionSha256;$env:T16_SOURCE_SHA=$ExpectedSourceSha256;$env:T16_SOURCE_BYTES=[string]$ExpectedSourceBytes;$env:T16_BASELINE=$ExpectedBaselineJobId
$probe=@'
import json, os
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.fault_injection import TIP015BFaultInjector
from vibemql5.core.iterations import IterationManager, TERMINAL_ITERATION_STATES
from vibemql5.core.observability import ObservabilityManager
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
from vibemql5.core.facade import ToolFacade
root=Path(os.environ['T16_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.13' and p.get('bridge_build')=='TIP-016' and len(REQUIRED_TOOLS)==41
ps=ProjectSessionManager(root); s=ps.get(os.environ['T16_PROJECT']); r=ps.resume(os.environ['T16_PROJECT'])
assert s['revision_id']==os.environ['T16_REV'] and s['revision_sha256'].lower()==os.environ['T16_REV_SHA'].lower(); assert r['integrity']=='VERIFIED' and r['resume_safe'] is True and r['stale_reasons']==[]
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==os.environ['T16_SOURCE_SHA'].lower() and int(a['bytes'])==int(os.environ['T16_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T16_BASELINE'] and s['last_job_id']==os.environ['T16_BASELINE']
all_it=IterationManager(root).list(); assert not [x for x in all_it if x.get('state') not in TERMINAL_ITERATION_STATES]
obs=ObservabilityManager(root); jobs=obs.job_history(limit=1000); assert os.environ['T16_BASELINE'] in {x['job_id'] for x in jobs['jobs']}
assert TIP015BFaultInjector(root).status().get('status')!='ARMED'
h=ToolFacade(root).health(); assert h['queue_length']==0 and h['active_job'] is None
print(json.dumps({'TIP016_PYTHON_VERIFY':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'revision_sha256':s['revision_sha256'],'source':a,'baseline_job_id':s['baseline_job_id'],'resume_safe':r['resume_safe'],'job_history':jobs['count_total']},sort_keys=True))
'@
$probe|& $python -
if($LASTEXITCODE -ne 0){throw 'TIP016_PYTHON_VERIFY_FAILED'}

$projectState=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml';$state=Get-Content -LiteralPath $projectState -Raw -Encoding UTF8
foreach($needle in @('active_tip: TIP-016','phase: VERIFY','bridge_target: 0.2.13','bridge_build: TIP-016','release_eligible: false','forward_eligible: false','live_eligible: false','predecessor_closure_sha256: 12c8bd59ab54512aaf6fe32c857af93aa4346d9885b3d91f5e25f9a245ec13d5')){if($state -notmatch [regex]::Escape($needle)){throw "TIP016_PROJECT_STATE_VERIFY_MISSING=$needle"}}
Write-Host 'TIP016_PROJECT_STATE_VERIFY=PASS'

$helper=Join-Path $Target 'ops\windows\VibeMQL5.AtomicFile.ps1';. $helper
$scratch=Join-Path $Target ('logs\TIP016-atomic-smoke-'+[guid]::NewGuid().ToString('N'));New-Item -ItemType Directory -Path $scratch -Force|Out-Null
try{
    $dest=Join-Path $scratch 'state.json';$ready=Join-Path $scratch 'locked.ready';[IO.File]::WriteAllText($dest,'{"generation":0}',(New-Object Text.UTF8Encoding($false)))
    $destQ=$dest.Replace("'","''");$readyQ=$ready.Replace("'","''")
    $lockScript=@"
`$fs=[IO.File]::Open('$destQ',[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
[IO.File]::WriteAllText('$readyQ','ready')
Start-Sleep -Milliseconds 450
`$fs.Dispose()
"@
    $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($lockScript))
    $blocker=Start-Process -FilePath (Get-Command powershell.exe).Source -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$encoded) -PassThru -WindowStyle Hidden
    for($i=0;$i -lt 50 -and -not(Test-Path -LiteralPath $ready);$i++){Start-Sleep -Milliseconds 20}
    if(-not(Test-Path -LiteralPath $ready)){throw 'TIP016_LOCK_HELPER_DID_NOT_SIGNAL'}
    $sw=[Diagnostics.Stopwatch]::StartNew();Write-VibeAtomicJson -Path $dest -Value ([ordered]@{generation=1;status='PASS'}) -Depth 8;$sw.Stop();$blocker.WaitForExit()
    $obj=Get-Content -LiteralPath $dest -Raw -Encoding UTF8|ConvertFrom-Json;if([int]$obj.generation-ne 1 -or [string]$obj.status-ne 'PASS'){throw 'TIP016_ATOMIC_FINAL_CONTENT_MISMATCH'}
    if($sw.ElapsedMilliseconds -lt 200){throw "TIP016_LOCKED_DESTINATION_DID_NOT_EXERCISE_RETRY elapsed_ms=$($sw.ElapsedMilliseconds)"}
    Write-Host ("TIP016_WINDOWS_LOCKED_DESTINATION_RETRY=PASS elapsed_ms={0}" -f $sw.ElapsedMilliseconds)
    for($i=2;$i -le 101;$i++){Write-VibeAtomicJson -Path $dest -Value ([ordered]@{generation=$i;status='PASS'}) -Depth 8}
    $obj=Get-Content -LiteralPath $dest -Raw -Encoding UTF8|ConvertFrom-Json;if([int]$obj.generation-ne 101){throw 'TIP016_ATOMIC_STRESS_FINAL_MISMATCH'}
    $tmp=@(Get-ChildItem -LiteralPath $scratch -File -Filter '*.tmp' -ErrorAction SilentlyContinue);if($tmp.Count-ne 0){throw "TIP016_ATOMIC_TEMP_LEAK count=$($tmp.Count)"}
    Write-Host 'TIP016_ATOMIC_TEMP_CLEANUP=PASS writes=101'
}
finally{Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue}

foreach($name in @('Start-VibeMQL5TunnelSupervisor.ps1','Invoke-VibeMQL5Watchdog.ps1','Invoke-TIP013Soak.ps1','Invoke-TIP013FailureInjection.ps1')){$text=Get-Content -LiteralPath (Join-Path $Target ('ops\windows\'+$name)) -Raw -Encoding UTF8;if($text -notmatch 'VibeMQL5\.AtomicFile\.ps1' -or $text -notmatch 'Write-VibeAtomicJson'){throw "TIP016_ATOMIC_CONSUMER_MISSING=$name"};if($text -match 'Move-Item\s+-LiteralPath\s+\$tmp\s+-Destination\s+\$Path\s+-Force'){throw "TIP016_FRAGILE_MOVE_REMAINS=$name"}}
Write-Host 'TIP016_ATOMIC_CONSUMERS=PASS count=4'

function Get-ExactTunnelProcess([string]$Executable){$expected=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})}
$h=0;$r=0;try{$h=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.healthUrl -TimeoutSec 3).StatusCode}catch{};try{$r=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.readyUrl -TimeoutSec 3).StatusCode}catch{};$t=@(Get-ExactTunnelProcess ([string]$config.tunnel.executable));if($h-ne 200 -or $r-ne 200 -or $t.Count-ne 1){throw "TIP016_RUNTIME_VERIFY_FAILED health=$h ready=$r tunnels=$($t.Count)"}
Write-Host ("TIP016_RUNTIME_VERIFY=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
Write-Host 'TIP016_VERIFY=PASS'
