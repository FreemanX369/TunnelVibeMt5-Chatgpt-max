[CmdletBinding()]
param(
    [string]$Target='C:\VibeMQL5',
    [string]$PayloadRoot='',
    [string]$ProjectId='TIP014-DEMOEA-E2E-20260830',
    [string]$ExpectedRevision='REV-000004',
    [string]$ExpectedRevisionSha256='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989',
    [string]$ExpectedSourceSha256='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c',
    [Int64]$ExpectedSourceBytes=2026,
    [string]$ExpectedBaselineJobId='BT-20260831-001933-B0484B',
    [string]$ExpectedTip015CClosure='C:\VibeMQL5\evidence\TIP015C-CLOSURE-20260902-000114.zip',
    [string]$ExpectedTip015CClosureSha256='12c8bd59ab54512aaf6fe32c857af93aa4346d9885b3d91f5e25f9a245ec13d5',
    [string]$ExpectedProjectStateSha256='f1b6773363d082e5530d126d0f7585e1552be22f2aabfaff5c691657f10090fb'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json'
$projectState=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml'
if(-not(Test-Path -LiteralPath $python -PathType Leaf)){throw "TIP016_PYTHON_MISSING: $python"}
if(-not(Test-Path -LiteralPath $configPath -PathType Leaf)){throw "TIP016_WINDOWS_CONFIG_MISSING: $configPath"}
if(-not(Test-Path -LiteralPath $projectState -PathType Leaf)){throw "TIP016_PROJECT_STATE_MISSING: $projectState"}
if(-not(Test-Path -LiteralPath $ExpectedTip015CClosure -PathType Leaf)){throw 'TIP016_TIP015C_CLOSURE_MISSING'}
if((Get-FileHash -LiteralPath $ExpectedTip015CClosure -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedTip015CClosureSha256){throw 'TIP016_TIP015C_CLOSURE_HASH_MISMATCH'}
if((Get-FileHash -LiteralPath $projectState -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedProjectStateSha256){throw 'TIP016_PROJECT_STATE_PREHASH_MISMATCH'}
$stateText=Get-Content -LiteralPath $projectState -Raw -Encoding UTF8
foreach($needle in @('active_tip: TIP-015C','phase: CLOSED','release_eligible: false','forward_eligible: false','live_eligible: false')){if($stateText -notmatch [regex]::Escape($needle)){throw "TIP016_PROJECT_STATE_PRECONDITION_MISSING=$needle"}}

if(-not $PayloadRoot){$candidate=Join-Path $PSScriptRoot 'payload';if(Test-Path -LiteralPath $candidate){$PayloadRoot=$candidate}else{$PayloadRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)}}
$PayloadRoot=(Resolve-Path -LiteralPath $PayloadRoot).Path
foreach($name in @('workspaces','state','runs','secrets')){if(Test-Path -LiteralPath (Join-Path $PayloadRoot $name)){throw "TIP016_FORBIDDEN_PAYLOAD_PATH: $name/**"}}
$files=@(
'app\vibemql5\__init__.py',
'config\build-provenance.json',
'pyproject.toml',
'ops\windows\VibeMQL5.AtomicFile.ps1',
'ops\windows\Start-VibeMQL5TunnelSupervisor.ps1',
'ops\windows\Invoke-VibeMQL5Watchdog.ps1',
'ops\windows\Invoke-TIP013Soak.ps1',
'ops\windows\Invoke-TIP013FailureInjection.ps1',
'ops\windows\Apply-TIP016.ps1',
'ops\windows\Test-TIP016.ps1',
'docs\vibecode\DECISIONS.yaml',
'docs\vibecode\TIP-016-RRI.yaml',
'docs\vibecode\TIP-016-SPEC.yaml',
'docs\vibecode\TIP-016-CONTRACT.yaml',
'docs\vibecode\TASK-GRAPH-TIP016.yaml',
'docs\vibecode\AI-BUILD-CONTRACT-TIP016.md',
'docs\vibecode\AI-BUILD-CONTRACT-TIP016.json',
'docs\vibecode\TIP016-LOCAL-TESTS.txt',
'docs\vibecode\TIP016-POSTEDIT-HASHES.json',
'docs\vibecode\TIP016-RETRO-EVIDENCE.json',
'docs\vibecode\TIP016-RETRO-LOCAL-RESULT.json',
'docs\vibecode\TIP016-LOCAL-EVIDENCE.json',
'BUILD_REPORT\TIP-016-LOCAL-COMPLETION.md',
'tests\unit\test_tip011b_runtime_refresh.py',
'tests\unit\test_tip012_recovery.py',
'tests\unit\test_tip013_resilience.py',
'tests\unit\test_tip014_project_sessions.py',
'tests\unit\test_tip015_provenance.py',
'tests\unit\test_tip015c_deploy_contract.py',
'tests\unit\test_tip016_atomic_file.py',
'tests\unit\test_tip016_deploy_contract.py'
)
foreach($rel in $files){
    $low=$rel.Replace('/','\').ToLowerInvariant();foreach($prefix in @('workspaces\','state\','runs\','secrets\','docs\vibecode\project_state.yaml')){if($low.StartsWith($prefix)){throw "TIP016_FORBIDDEN_ALLOWLIST_ENTRY: $rel"}}
    if(-not(Test-Path -LiteralPath (Join-Path $PayloadRoot $rel) -PathType Leaf)){throw "TIP016_PAYLOAD_MISSING: $rel"}
}
Write-Host ("TIP016_ALLOWLIST_GATE=PASS files={0}" -f $files.Count)
$manifestPath=Join-Path $PayloadRoot 'TIP016-PAYLOAD-MANIFEST.sha256'
if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw 'TIP016_PAYLOAD_MANIFEST_MISSING'}
$expected=@{};foreach($rel in $files){$expected[$rel.Replace('\','/').ToLowerInvariant()]=$true};$seen=@{}
foreach($line in @(Get-Content -LiteralPath $manifestPath -Encoding UTF8)){
    if([string]::IsNullOrWhiteSpace([string]$line)){continue}
    if([string]$line -notmatch '^([0-9a-fA-F]{64})\s+(.+)$'){throw "TIP016_MANIFEST_INVALID_LINE: $line"}
    $want=$Matches[1].ToLowerInvariant();$rel=$Matches[2].Trim().Replace('\','/');$key=$rel.ToLowerInvariant()
    if(-not $expected.ContainsKey($key)){throw "TIP016_MANIFEST_UNEXPECTED_ENTRY: $rel"};if($seen.ContainsKey($key)){throw "TIP016_MANIFEST_DUPLICATE_ENTRY: $rel"}
    $candidate=[IO.Path]::GetFullPath((Join-Path $PayloadRoot $rel));$rootFull=[IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\')+'\';if(-not $candidate.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){throw "TIP016_MANIFEST_PATH_ESCAPE: $rel"}
    $got=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant();if($got -ne $want){throw "TIP016_PAYLOAD_HASH_MISMATCH: $rel expected=$want actual=$got"};$seen[$key]=$true
}
if($seen.Count -ne $expected.Count){throw "TIP016_MANIFEST_COUNT_MISMATCH expected=$($expected.Count) actual=$($seen.Count)"}
Write-Host ("TIP016_PAYLOAD_MANIFEST_GATE=PASS files={0}" -f $seen.Count)

$env:T16_TARGET=$Target;$env:T16_PROJECT=$ProjectId;$env:T16_REV=$ExpectedRevision;$env:T16_REV_SHA=$ExpectedRevisionSha256;$env:T16_SOURCE_SHA=$ExpectedSourceSha256;$env:T16_SOURCE_BYTES=[string]$ExpectedSourceBytes;$env:T16_BASELINE=$ExpectedBaselineJobId
$pre=@'
import json, os
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.fault_injection import TIP015BFaultInjector
from vibemql5.core.iterations import IterationManager, TERMINAL_ITERATION_STATES
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
from vibemql5.core.facade import ToolFacade
root=Path(os.environ['T16_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.12' and p.get('bridge_build')=='TIP-015C' and len(REQUIRED_TOOLS)==41
ps=ProjectSessionManager(root); s=ps.get(os.environ['T16_PROJECT']); r=ps.resume(os.environ['T16_PROJECT'])
assert s['revision_id']==os.environ['T16_REV'] and s['revision_sha256'].lower()==os.environ['T16_REV_SHA'].lower()
assert s['source_sha256'].lower()==os.environ['T16_SOURCE_SHA'].lower() and int(s['source_bytes'])==int(os.environ['T16_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T16_BASELINE'] and s['last_job_id']==os.environ['T16_BASELINE']; assert r['integrity']=='VERIFIED' and r['resume_safe'] is True and r['stale_reasons']==[]
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==s['source_sha256'] and int(a['bytes'])==int(s['source_bytes'])
active=[x for x in IterationManager(root).list() if x.get('state') not in TERMINAL_ITERATION_STATES]; assert not active, active
h=ToolFacade(root).health(); assert h['queue_length']==0 and h['active_job'] is None, h
assert TIP015BFaultInjector(root).status().get('status')!='ARMED'
print(json.dumps({'TIP016_PREDEPLOY_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'revision_sha256':s['revision_sha256'],'source':a,'baseline_job_id':s['baseline_job_id'],'resume_safe':r['resume_safe']},sort_keys=True))
'@
$pre | & $python -
if($LASTEXITCODE -ne 0){throw 'TIP016_PREDEPLOY_GATE_FAILED'}
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Get-ExactTunnelProcess([string]$Executable){$expected=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})}
$preHealth=0;$preReady=0;try{$preHealth=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.healthUrl -TimeoutSec 3).StatusCode}catch{};try{$preReady=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.readyUrl -TimeoutSec 3).StatusCode}catch{};$preTunnels=@(Get-ExactTunnelProcess ([string]$config.tunnel.executable));if($preHealth -ne 200 -or $preReady -ne 200 -or $preTunnels.Count -ne 1){throw "TIP016_RUNTIME_PRE_GATE_FAILED health=$preHealth ready=$preReady tunnels=$($preTunnels.Count)"}
Write-Host 'TIP016_RUNTIME_PRE_GATE=PASS healthz=200 readyz=200 tunnel_count=1'

$backupRoot=Join-Path $Target ("logs\TIP016-backup-$stamp")
New-Item -ItemType Directory -Path $backupRoot -Force|Out-Null
$existing=@{};foreach($rel in $files){$dst=Join-Path $Target $rel;if(Test-Path -LiteralPath $dst -PathType Leaf){$existing[$rel]=$true;$b=Join-Path $backupRoot $rel;$d=Split-Path -Parent $b;New-Item -ItemType Directory -Path $d -Force|Out-Null;Copy-Item -LiteralPath $dst -Destination $b -Force}else{$existing[$rel]=$false}}
Copy-Item -LiteralPath $projectState -Destination (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Force
$taskNames=@([string]$config.tasks.tunnelTaskName,[string]$config.tasks.watchdogTaskName,[string]$config.tasks.backgroundTunnelTaskName)
$committed=$false
try{
    foreach($n in $taskNames){if($n){Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue}};Start-Sleep -Seconds 1
    foreach($proc in @(Get-ExactTunnelProcess ([string]$config.tunnel.executable))){& taskkill.exe /PID ([string]$proc.ProcessId) /T /F | Out-Null}
    for($i=0;$i -lt 20;$i++){Start-Sleep -Milliseconds 250;if(@(Get-ExactTunnelProcess ([string]$config.tunnel.executable)).Count -eq 0){break}};if(@(Get-ExactTunnelProcess ([string]$config.tunnel.executable)).Count -ne 0){throw 'TIP016_STALE_TUNNEL_REMAINS'}
    foreach($rel in $files){$src=Join-Path $PayloadRoot $rel;$dst=Join-Path $Target $rel;$parent=Split-Path -Parent $dst;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent -Force|Out-Null};Copy-Item -LiteralPath $src -Destination $dst -Force}
    Write-Host 'TIP016_COPY_GATE=PASS'
    & $python -m pip install -e $Target --no-deps
    if($LASTEXITCODE -ne 0){throw 'TIP016_PIP_REFRESH_FAILED'}

    $env:T16_STATE=$projectState;$env:T16_PRESTATE=$ExpectedProjectStateSha256
    $statePatch=@'
import hashlib, os, time
from pathlib import Path
p=Path(os.environ['T16_STATE']); raw=p.read_bytes(); actual=hashlib.sha256(raw).hexdigest(); expected=os.environ['T16_PRESTATE']
if actual!=expected: raise SystemExit(f'TIP016_PROJECT_STATE_CAS_MISMATCH actual={actual}')
t=raw.decode('utf-8')
eol='\r\n' if '\r\n' in t else '\n'
lines=t.splitlines(keepends=True)
for old,new in [('active_tip: TIP-015C','active_tip: TIP-016'),('phase: CLOSED','phase: VERIFY'),('bridge_target: 0.2.12','bridge_target: 0.2.13'),('bridge_build: TIP-015C','bridge_build: TIP-016')]:
    hits=[i for i,line in enumerate(lines) if line.rstrip('\r\n')==old]
    if len(hits)!=1: raise SystemExit(f'TIP016_PROJECT_STATE_TARGET_MISMATCH {old!r} count={len(hits)}')
    i=hits[0]; suffix=lines[i][len(lines[i].rstrip('\r\n')):]; lines[i]=new+suffix
t=''.join(lines)
if any(line.rstrip('\r\n')=='tip016:' for line in t.splitlines(keepends=True)): raise SystemExit('TIP016_PROJECT_STATE_ALREADY_PATCHED')
append=eol+eol.join(['tip016:','  status: VERIFY','  predecessor: TIP-015C','  predecessor_closure_sha256: 12c8bd59ab54512aaf6fe32c857af93aa4346d9885b3d91f5e25f9a245ec13d5','  windows_verification: PENDING','  release_qualification: PENDING'])+eol
t=t.rstrip('\r\n')+append
new=t.encode('utf-8'); tmp=p.with_name(p.name+'.tip016.tmp')
with tmp.open('wb') as f: f.write(new); f.flush(); os.fsync(f.fileno())
for i in range(8):
    try: os.replace(tmp,p); break
    except OSError:
        if i==7: raise
        time.sleep(0.02*(2**i))
print(hashlib.sha256(new).hexdigest())
'@
    $statePatchItems=@($statePatch|& $python - 2>&1);$statePatchExit=$LASTEXITCODE
    $statePatchText=(($statePatchItems|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine).Trim()
    if($statePatchExit -ne 0){throw "TIP016_PROJECT_STATE_PATCH_FAILED exit=$statePatchExit output=$statePatchText"}
    $postStateSha='';if($statePatchText){$postStateSha=(($statePatchText -split "`r?`n")[-1]).Trim()}
    if($postStateSha -notmatch '^[0-9a-f]{64}$'){throw "TIP016_PROJECT_STATE_PATCH_INVALID_OUTPUT output=$statePatchText"}
    Write-Host "TIP016_PROJECT_STATE_GATE=PASS sha256=$postStateSha"

    $post=@'
import json, os, sys
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.fault_injection import TIP015BFaultInjector
from vibemql5.core.iterations import IterationManager, TERMINAL_ITERATION_STATES
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T16_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.13' and p.get('bridge_build')=='TIP-016' and len(REQUIRED_TOOLS)==41
ps=ProjectSessionManager(root); s=ps.get(os.environ['T16_PROJECT']); r=ps.resume(os.environ['T16_PROJECT'])
assert s['revision_id']==os.environ['T16_REV'] and s['revision_sha256'].lower()==os.environ['T16_REV_SHA'].lower()
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==os.environ['T16_SOURCE_SHA'].lower() and int(a['bytes'])==int(os.environ['T16_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T16_BASELINE'] and s['last_job_id']==os.environ['T16_BASELINE']; assert r['resume_safe'] is True and r['stale_reasons']==[]
assert not [x for x in IterationManager(root).list() if x.get('state') not in TERMINAL_ITERATION_STATES]
assert TIP015BFaultInjector(root).status().get('status')!='ARMED'
assert (root/'ops/windows/VibeMQL5.AtomicFile.ps1').is_file()
print(json.dumps({'TIP016_LOCAL_MODULE_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'source':a},sort_keys=True))
'@
    $post | & $python -
    if($LASTEXITCODE -ne 0){throw 'TIP016_LOCAL_MODULE_GATE_FAILED'}
    $sessionId=[Diagnostics.Process]::GetCurrentProcess().SessionId;if($sessionId -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}else{throw 'TIP016_NO_RUNTIME_MODE_AVAILABLE'}
    $ready=$false;for($i=0;$i -lt 90;$i++){Start-Sleep -Seconds 1;try{$h=Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.healthUrl -TimeoutSec 2;$r=Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.readyUrl -TimeoutSec 2;if($h.StatusCode -eq 200 -and $r.StatusCode -eq 200){$ready=$true;break}}catch{}};if(-not $ready){throw 'TIP016_RUNTIME_NOT_READY'}
    $t=@(Get-ExactTunnelProcess ([string]$config.tunnel.executable));if($t.Count -ne 1){throw "TIP016_TUNNEL_COUNT_FAILED count=$($t.Count)"}
    Write-Host ("TIP016_RUNTIME_POST_GATE=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
    $committed=$true
}
catch{
    Write-Host 'TIP016_ROLLBACK_BEGIN'
    foreach($rel in $files){$dst=Join-Path $Target $rel;$b=Join-Path $backupRoot $rel;if($existing[$rel]){if(Test-Path -LiteralPath $b){$d=Split-Path -Parent $dst;if(-not(Test-Path -LiteralPath $d)){New-Item -ItemType Directory -Path $d -Force|Out-Null};Copy-Item -LiteralPath $b -Destination $dst -Force}}else{Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue}}
    Copy-Item -LiteralPath (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Destination $projectState -Force
    & $python -m pip install -e $Target --no-deps | Out-Null
    Write-Host 'TIP016_ROLLBACK_FILES=PASS'
    try{if([Diagnostics.Process]::GetCurrentProcess().SessionId -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}}catch{}
    throw
}
if(-not $committed){throw 'TIP016_APPLY_NOT_COMMITTED'}
Write-Host 'TIP016_APPLY=PASS'
