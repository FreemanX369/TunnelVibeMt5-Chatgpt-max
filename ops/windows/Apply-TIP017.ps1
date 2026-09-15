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
    [string]$ExpectedTip016Closure='C:\VibeMQL5\evidence\TIP016-CLOSURE-20260902-115639.zip',
    [string]$ExpectedTip016ClosureSha256='607375eccbdb6d86272c2854e83d5f6343f54b7042ab6f0731e42bf140bcf43c',
    [string]$ExpectedProjectStateSha256='d70da9e3c3b9f4eaaf144ede6bc87240cf7f444aabc4f6172cbcddb774cd9c45'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json'
$projectState=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml'
if(-not(Test-Path -LiteralPath $python -PathType Leaf)){throw "TIP017_PYTHON_MISSING=$python"}
if(-not(Test-Path -LiteralPath $configPath -PathType Leaf)){throw "TIP017_WINDOWS_CONFIG_MISSING=$configPath"}
if(-not(Test-Path -LiteralPath $ExpectedTip016Closure -PathType Leaf)){throw 'TIP017_TIP016_CLOSURE_MISSING'}
if((Get-FileHash -LiteralPath $ExpectedTip016Closure -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedTip016ClosureSha256){throw 'TIP017_TIP016_CLOSURE_HASH_MISMATCH'}
if((Get-FileHash -LiteralPath $projectState -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedProjectStateSha256){throw 'TIP017_PROJECT_STATE_PREHASH_MISMATCH'}
$stateText=Get-Content -LiteralPath $projectState -Raw -Encoding UTF8
foreach($needle in @('active_tip: TIP-016','phase: CLOSED','bridge_target: 0.2.13','bridge_build: TIP-016','release_eligible: false','forward_eligible: false','live_eligible: false')){if($stateText -notmatch [regex]::Escape($needle)){throw "TIP017_PROJECT_STATE_PRECONDITION_MISSING=$needle"}}

if(-not $PayloadRoot){$candidate=Join-Path $PSScriptRoot 'payload';if(Test-Path -LiteralPath $candidate){$PayloadRoot=$candidate}else{$PayloadRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)}}
$PayloadRoot=(Resolve-Path -LiteralPath $PayloadRoot).Path
foreach($name in @('workspaces','state','runs','secrets','evidence')){if(Test-Path -LiteralPath (Join-Path $PayloadRoot $name)){throw "TIP017_FORBIDDEN_PAYLOAD_PATH=$name"}}
$files=@(
'app\vibemql5\__init__.py',
'app\vibemql5\adapters\cli.py',
'app\vibemql5\core\compiler.py',
'app\vibemql5\core\facade.py',
'app\vibemql5\core\release.py',
'app\vibemql5\core\retro.py',
'app\vibemql5\core\tester.py',
'app\vibemql5\parsers\report.py',
'app\vibemql5\worker.py',
'config\build-provenance.json',
'pyproject.toml',
'ops\windows\Apply-TIP017.ps1',
'ops\windows\Test-TIP017.ps1',
'ops\windows\Invoke-TIP017ReleaseQualification.ps1',
'docs\vibecode\DECISIONS.yaml',
'docs\vibecode\OWNER_APPROVAL-TIP017.json',
'docs\vibecode\TIP-017-RRI.yaml',
'docs\vibecode\TIP-017-SPEC.yaml',
'docs\vibecode\TIP-017-CONTRACT.yaml',
'docs\vibecode\TASK-GRAPH-TIP017.yaml',
'docs\vibecode\AI-BUILD-CONTRACT-TIP017.md',
'docs\vibecode\AI-BUILD-CONTRACT-TIP017.json',
'docs\vibecode\TIP017-INDEPENDENT-DERIVATION.json',
'docs\vibecode\TIP017-LOCAL-TESTS.txt',
'docs\vibecode\TIP017-POSTEDIT-HASHES.json',
'docs\vibecode\TIP017-RETRO-EVIDENCE.json',
'docs\vibecode\TIP017-RETRO-LOCAL-RESULT.json',
'docs\vibecode\TIP017-LOCAL-EVIDENCE.json',
'BUILD_REPORT\TIP-017-LOCAL-COMPLETION.md',
'tests\unit\test_tip011_checkpoint_provenance.py',
'tests\unit\test_tip011b_runtime_refresh.py',
'tests\unit\test_tip012_recovery.py',
'tests\unit\test_tip013_resilience.py',
'tests\unit\test_tip014_project_sessions.py',
'tests\unit\test_tip015_provenance.py',
'tests\unit\test_tip015c_deploy_contract.py',
'tests\unit\test_tip016_deploy_contract.py',
'tests\unit\test_tip017_release_pipeline.py',
'tests\unit\test_tip017_deploy_contract.py'
)
foreach($rel in $files){
  $low=$rel.Replace('/','\').ToLowerInvariant();foreach($prefix in @('workspaces\','state\','runs\','secrets\','evidence\','docs\vibecode\project_state.yaml')){if($low.StartsWith($prefix)){throw "TIP017_FORBIDDEN_ALLOWLIST_ENTRY=$rel"}}
  if(-not(Test-Path -LiteralPath (Join-Path $PayloadRoot $rel) -PathType Leaf)){throw "TIP017_PAYLOAD_MISSING=$rel"}
}
Write-Host ("TIP017_ALLOWLIST_GATE=PASS files={0}" -f $files.Count)
$manifestPath=Join-Path $PayloadRoot 'TIP017-PAYLOAD-MANIFEST.sha256'
if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw 'TIP017_PAYLOAD_MANIFEST_MISSING'}
$expected=@{};foreach($rel in $files){$expected[$rel.Replace('\','/').ToLowerInvariant()]=$true};$seen=@{}
foreach($line in @(Get-Content -LiteralPath $manifestPath -Encoding UTF8)){
  if([string]::IsNullOrWhiteSpace([string]$line)){continue}
  if([string]$line -notmatch '^([0-9a-fA-F]{64})\s+(.+)$'){throw "TIP017_MANIFEST_INVALID_LINE=$line"}
  $want=$Matches[1].ToLowerInvariant();$rel=$Matches[2].Trim().Replace('\','/');$key=$rel.ToLowerInvariant()
  if(-not $expected.ContainsKey($key)){throw "TIP017_MANIFEST_UNEXPECTED_ENTRY=$rel"};if($seen.ContainsKey($key)){throw "TIP017_MANIFEST_DUPLICATE_ENTRY=$rel"}
  $candidate=[IO.Path]::GetFullPath((Join-Path $PayloadRoot $rel));$rootFull=[IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\')+'\';if(-not $candidate.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){throw "TIP017_MANIFEST_PATH_ESCAPE=$rel"}
  $got=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant();if($got -ne $want){throw "TIP017_PAYLOAD_HASH_MISMATCH=$rel expected=$want actual=$got"};$seen[$key]=$true
}
if($seen.Count -ne $expected.Count){throw "TIP017_MANIFEST_COUNT_MISMATCH expected=$($expected.Count) actual=$($seen.Count)"}
Write-Host ("TIP017_PAYLOAD_MANIFEST_GATE=PASS files={0}" -f $seen.Count)

$env:T17_TARGET=$Target;$env:T17_PROJECT=$ProjectId;$env:T17_REV=$ExpectedRevision;$env:T17_REV_SHA=$ExpectedRevisionSha256;$env:T17_SOURCE_SHA=$ExpectedSourceSha256;$env:T17_SOURCE_BYTES=[string]$ExpectedSourceBytes;$env:T17_BASELINE=$ExpectedBaselineJobId
$pre=@'
import json, os
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.facade import ToolFacade
from vibemql5.core.iterations import IterationManager, TERMINAL_ITERATION_STATES
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T17_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.13' and p.get('bridge_build')=='TIP-016' and len(REQUIRED_TOOLS)==41
s=ProjectSessionManager(root).get(os.environ['T17_PROJECT']); r=ProjectSessionManager(root).resume(os.environ['T17_PROJECT'])
assert s['revision_id']==os.environ['T17_REV'] and s['revision_sha256'].lower()==os.environ['T17_REV_SHA'].lower()
assert s['source_sha256'].lower()==os.environ['T17_SOURCE_SHA'].lower() and int(s['source_bytes'])==int(os.environ['T17_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T17_BASELINE'] and s['last_job_id']==os.environ['T17_BASELINE'] and r['resume_safe'] is True and r['stale_reasons']==[]
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==s['source_sha256'] and int(a['bytes'])==int(s['source_bytes'])
assert not [x for x in IterationManager(root).list() if x.get('state') not in TERMINAL_ITERATION_STATES]
h=ToolFacade(root).health(); assert h['queue_length']==0 and h['active_job'] is None
print(json.dumps({'TIP017_PREDEPLOY_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'source':a,'baseline_job_id':s['baseline_job_id']},sort_keys=True))
'@
$pre | & $python -
if($LASTEXITCODE -ne 0){throw 'TIP017_PREDEPLOY_GATE_FAILED'}
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Get-ExactTunnel([string]$Executable){$expectedExe=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expectedExe)})}
function Http([string]$Url){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3).StatusCode}catch{return 0}}
if((Http $config.supervisor.healthUrl) -ne 200 -or (Http $config.supervisor.readyUrl) -ne 200 -or @(Get-ExactTunnel ([string]$config.tunnel.executable)).Count -ne 1){throw 'TIP017_RUNTIME_PRE_GATE_FAILED'}
Write-Host 'TIP017_RUNTIME_PRE_GATE=PASS healthz=200 readyz=200 tunnel_count=1'

$backupRoot=Join-Path $Target ("logs\TIP017-backup-$stamp");New-Item -ItemType Directory -Path $backupRoot -Force|Out-Null
$existing=@{};foreach($rel in $files){$dst=Join-Path $Target $rel;if(Test-Path -LiteralPath $dst -PathType Leaf){$existing[$rel]=$true;$b=Join-Path $backupRoot $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $b) -Force|Out-Null;Copy-Item -LiteralPath $dst -Destination $b -Force}else{$existing[$rel]=$false}}
Copy-Item -LiteralPath $projectState -Destination (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Force
$taskNames=@([string]$config.tasks.tunnelTaskName,[string]$config.tasks.watchdogTaskName,[string]$config.tasks.backgroundTunnelTaskName)
try{
  foreach($n in $taskNames){if($n){Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue}};Start-Sleep -Seconds 1
  foreach($proc in @(Get-ExactTunnel ([string]$config.tunnel.executable))){& taskkill.exe /PID ([string]$proc.ProcessId) /T /F | Out-Null}
  foreach($rel in $files){$src=Join-Path $PayloadRoot $rel;$dst=Join-Path $Target $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force|Out-Null;Copy-Item -LiteralPath $src -Destination $dst -Force}
  Write-Host 'TIP017_COPY_GATE=PASS'
  & $python -m pip install -e $Target --no-deps
  if($LASTEXITCODE -ne 0){throw 'TIP017_PIP_REFRESH_FAILED'}

  $env:T17_STATE=$projectState;$env:T17_PRESTATE=$ExpectedProjectStateSha256
  $patch=@'
import hashlib, os, time
from pathlib import Path
p=Path(os.environ['T17_STATE']); raw=p.read_bytes(); actual=hashlib.sha256(raw).hexdigest(); expected=os.environ['T17_PRESTATE']
if actual!=expected: raise SystemExit(f'TIP017_PROJECT_STATE_CAS_MISMATCH actual={actual}')
t=raw.decode('utf-8'); lines=t.splitlines(keepends=True); eol='\r\n' if '\r\n' in t else '\n'
for old,new in [('active_tip: TIP-016','active_tip: TIP-017'),('phase: CLOSED','phase: VERIFY'),('bridge_target: 0.2.13','bridge_target: 0.2.14'),('bridge_build: TIP-016','bridge_build: TIP-017')]:
    hits=[i for i,line in enumerate(lines) if line.rstrip('\r\n')==old]
    if len(hits)!=1: raise SystemExit(f'TIP017_PROJECT_STATE_TARGET_MISMATCH {old!r} count={len(hits)}')
    i=hits[0]; suffix=lines[i][len(lines[i].rstrip('\r\n')):]; lines[i]=new+suffix
t=''.join(lines)
if any(line.rstrip('\r\n')=='tip017:' for line in t.splitlines(keepends=True)): raise SystemExit('TIP017_PROJECT_STATE_ALREADY_PATCHED')
append=eol+eol.join(['tip017:','  status: VERIFY','  predecessor: TIP-016','  predecessor_closure_sha256: 607375eccbdb6d86272c2854e83d5f6343f54b7042ab6f0731e42bf140bcf43c','  release_pipeline: PENDING_WINDOWS_NATIVE','  release_eligible: false','  forward_eligible: false','  live_eligible: false'])+eol
new=(t.rstrip('\r\n')+append).encode('utf-8'); tmp=p.with_name(p.name+'.tip017.tmp')
with tmp.open('wb') as f: f.write(new); f.flush(); os.fsync(f.fileno())
for i in range(8):
    try: os.replace(tmp,p); break
    except OSError:
        if i==7: raise
        time.sleep(0.02*(2**i))
print(hashlib.sha256(new).hexdigest())
'@
  $items=@($patch|& $python - 2>&1);$code=$LASTEXITCODE;$text=(($items|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine).Trim();if($code -ne 0){throw "TIP017_PROJECT_STATE_PATCH_FAILED output=$text"};$postSha=(($text -split "`r?`n")[-1]).Trim();if($postSha -notmatch '^[0-9a-f]{64}$'){throw "TIP017_PROJECT_STATE_PATCH_OUTPUT_INVALID=$text"}
  Write-Host "TIP017_PROJECT_STATE_GATE=PASS sha256=$postSha"

  $post=@'
import json, os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T17_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.14' and p.get('bridge_build')=='TIP-017' and len(REQUIRED_TOOLS)==41
choices=set(build_parser()._subparsers._group_actions[0].choices); assert {'check-all','attest','ship'} <= choices
s=ProjectSessionManager(root).get(os.environ['T17_PROJECT']); a=RevisionManager(root).source_hash(s['workspace'],s['ea'])
assert s['revision_id']==os.environ['T17_REV'] and s['revision_sha256'].lower()==os.environ['T17_REV_SHA'].lower(); assert a['sha256']==os.environ['T17_SOURCE_SHA'].lower() and int(a['bytes'])==int(os.environ['T17_SOURCE_BYTES']); assert s['baseline_job_id']==os.environ['T17_BASELINE'] and s['last_job_id']==os.environ['T17_BASELINE']
print(json.dumps({'TIP017_LOCAL_MODULE_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'commands':sorted({'check-all','attest','ship'}),'revision':s['revision_id'],'source':a},sort_keys=True))
'@
  $post | & $python -
  if($LASTEXITCODE -ne 0){throw 'TIP017_LOCAL_MODULE_GATE_FAILED'}
  $sid=[Diagnostics.Process]::GetCurrentProcess().SessionId;if($sid -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}else{throw 'TIP017_NO_RUNTIME_MODE_AVAILABLE'}
  $ready=$false;for($i=0;$i -lt 90;$i++){Start-Sleep -Seconds 1;if((Http $config.supervisor.healthUrl) -eq 200 -and (Http $config.supervisor.readyUrl) -eq 200 -and @(Get-ExactTunnel ([string]$config.tunnel.executable)).Count -eq 1){$ready=$true;break}};if(-not $ready){throw 'TIP017_RUNTIME_NOT_READY'}
  $t=@(Get-ExactTunnel ([string]$config.tunnel.executable));Write-Host ("TIP017_RUNTIME_POST_GATE=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
}
catch{
  Write-Host 'TIP017_ROLLBACK_BEGIN'
  foreach($rel in $files){$dst=Join-Path $Target $rel;$b=Join-Path $backupRoot $rel;if($existing[$rel]){if(Test-Path -LiteralPath $b){New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force|Out-Null;Copy-Item -LiteralPath $b -Destination $dst -Force}}else{Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue}}
  Copy-Item -LiteralPath (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Destination $projectState -Force
  & $python -m pip install -e $Target --no-deps | Out-Null
  Write-Host 'TIP017_ROLLBACK_FILES=PASS'
  try{if([Diagnostics.Process]::GetCurrentProcess().SessionId -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}}catch{}
  throw
}
Write-Host 'TIP017_APPLY=PASS'
