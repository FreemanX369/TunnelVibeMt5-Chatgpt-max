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
    [string]$ExpectedReleaseJobId='BT-20260902-124524-9D17D6',
    [string]$ExpectedReleaseManifestSha256='b1f48ec1bd1f52bc0000dd6effd01b52a1d770a0f501daa965e4d51e083b575e',
    [string]$ExpectedProposalSha256='b9e1269848d39a6633641784f08adf7405a1677054838ca7ed7b5d0cd6de7764',
    [string]$ExpectedTip017Closure='C:\VibeMQL5\evidence\TIP017-CLOSURE-20260902-130907.zip',
    [string]$ExpectedTip017ClosureSha256='4e9008b0927eaee50939641344c26ae0c249fa0482ca8142449f480f96acdee3',
    [string]$ExpectedProjectStateSha256='5c462bf08fca55b44d4f72c54e479304fd75ba072554e0b7590cdcd272fcf05f'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json'
$projectState=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml'
$releaseManifest=Join-Path $Target 'evidence\manifest.json'
if(!(Test-Path -LiteralPath $python -PathType Leaf)){throw "TIP018_PYTHON_MISSING=$python"}
if(!(Test-Path -LiteralPath $configPath -PathType Leaf)){throw "TIP018_WINDOWS_CONFIG_MISSING=$configPath"}
if(!(Test-Path -LiteralPath $ExpectedTip017Closure -PathType Leaf)){throw 'TIP018_TIP017_CLOSURE_MISSING'}
if((Get-FileHash -LiteralPath $ExpectedTip017Closure -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedTip017ClosureSha256){throw 'TIP018_TIP017_CLOSURE_HASH_MISMATCH'}
if((Get-FileHash -LiteralPath $projectState -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedProjectStateSha256){throw 'TIP018_PROJECT_STATE_PREHASH_MISMATCH'}
if(!(Test-Path -LiteralPath $releaseManifest -PathType Leaf)){throw 'TIP018_RELEASE_MANIFEST_MISSING'}
if((Get-FileHash -LiteralPath $releaseManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedReleaseManifestSha256){throw 'TIP018_RELEASE_MANIFEST_PREHASH_MISMATCH'}
$stateText=Get-Content -LiteralPath $projectState -Raw -Encoding UTF8
foreach($needle in @('active_tip: TIP-017','phase: CLOSED','bridge_target: 0.2.14','bridge_build: TIP-017','release_eligible: true','forward_eligible: false','live_eligible: false')){if($stateText -notmatch [regex]::Escape($needle)){throw "TIP018_PROJECT_STATE_PRECONDITION_MISSING=$needle"}}

if(-not $PayloadRoot){$candidate=Join-Path $PSScriptRoot 'payload';if(Test-Path -LiteralPath $candidate){$PayloadRoot=$candidate}else{$PayloadRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)}}
$PayloadRoot=(Resolve-Path -LiteralPath $PayloadRoot).Path
foreach($name in @('workspaces','state','runs','secrets','evidence')){if(Test-Path -LiteralPath (Join-Path $PayloadRoot $name)){throw "TIP018_FORBIDDEN_PAYLOAD_PATH=$name"}}
$files=@(
'app\vibemql5\__init__.py',
'app\vibemql5\adapters\cli.py',
'app\vibemql5\core\facade.py',
'app\vibemql5\core\forward.py',
'app\vibemql5\worker.py',
'config\build-provenance.json',
'pyproject.toml',
'ops\windows\Apply-TIP018.ps1',
'ops\windows\Test-TIP018.ps1',
'ops\windows\Invoke-TIP018ForwardQualification.ps1',
'docs\vibecode\DECISIONS.yaml',
'docs\vibecode\OWNER_APPROVAL-TIP018.json',
'docs\vibecode\TIP018-FORWARD-ACCEPTANCE-PROPOSAL.yaml',
'docs\vibecode\TIP018-FORWARD-ACCEPTANCE.json',
'docs\vibecode\TIP-018-RRI.yaml',
'docs\vibecode\TIP-018-SPEC.yaml',
'docs\vibecode\TIP-018-CONTRACT.yaml',
'docs\vibecode\TASK-GRAPH-TIP018.yaml',
'docs\vibecode\AI-BUILD-CONTRACT-TIP018.md',
'docs\vibecode\AI-BUILD-CONTRACT-TIP018.json',
'docs\vibecode\TIP018-INDEPENDENT-DERIVATION.json',
'docs\vibecode\TIP018-LOCAL-TESTS.txt',
'docs\vibecode\TIP018-POSTEDIT-HASHES.json',
'docs\vibecode\TIP018-RETRO-EVIDENCE.json',
'docs\vibecode\TIP018-RETRO-LOCAL-RESULT.json',
'docs\vibecode\TIP018-LOCAL-EVIDENCE.json',
'BUILD_REPORT\TIP-018-LOCAL-COMPLETION.md',
'tests\unit\test_tip011b_runtime_refresh.py',
'tests\unit\test_tip012_recovery.py',
'tests\unit\test_tip013_resilience.py',
'tests\unit\test_tip014_project_sessions.py',
'tests\unit\test_tip015_provenance.py',
'tests\unit\test_tip015c_deploy_contract.py',
'tests\unit\test_tip016_deploy_contract.py',
'tests\unit\test_tip017_deploy_contract.py',
'tests\unit\test_tip018_forward_pipeline.py',
'tests\unit\test_tip018_deploy_contract.py'
)
foreach($rel in $files){
  $low=$rel.Replace('/','\').ToLowerInvariant();foreach($prefix in @('workspaces\','state\','runs\','secrets\','evidence\','docs\vibecode\project_state.yaml')){if($low.StartsWith($prefix)){throw "TIP018_FORBIDDEN_ALLOWLIST_ENTRY=$rel"}}
  if(!(Test-Path -LiteralPath (Join-Path $PayloadRoot $rel) -PathType Leaf)){throw "TIP018_PAYLOAD_MISSING=$rel"}
}
Write-Host ("TIP018_ALLOWLIST_GATE=PASS files={0}" -f $files.Count)
$manifestPath=Join-Path $PayloadRoot 'TIP018-PAYLOAD-MANIFEST.sha256'
if(!(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw 'TIP018_PAYLOAD_MANIFEST_MISSING'}
$expected=@{};foreach($rel in $files){$expected[$rel.Replace('\','/').ToLowerInvariant()]=$true};$seen=@{}
foreach($line in @(Get-Content -LiteralPath $manifestPath -Encoding UTF8)){
  if([string]::IsNullOrWhiteSpace([string]$line)){continue}
  if([string]$line -notmatch '^([0-9a-fA-F]{64})\s+(.+)$'){throw "TIP018_MANIFEST_INVALID_LINE=$line"}
  $want=$Matches[1].ToLowerInvariant();$rel=$Matches[2].Trim().Replace('\','/');$key=$rel.ToLowerInvariant()
  if(-not $expected.ContainsKey($key)){throw "TIP018_MANIFEST_UNEXPECTED_ENTRY=$rel"};if($seen.ContainsKey($key)){throw "TIP018_MANIFEST_DUPLICATE_ENTRY=$rel"}
  $candidate=[IO.Path]::GetFullPath((Join-Path $PayloadRoot $rel));$rootFull=[IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\')+'\';if(-not $candidate.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){throw "TIP018_MANIFEST_PATH_ESCAPE=$rel"}
  $got=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant();if($got -ne $want){throw "TIP018_PAYLOAD_HASH_MISMATCH=$rel expected=$want actual=$got"};$seen[$key]=$true
}
if($seen.Count -ne $expected.Count){throw "TIP018_MANIFEST_COUNT_MISMATCH expected=$($expected.Count) actual=$($seen.Count)"}
Write-Host ("TIP018_PAYLOAD_MANIFEST_GATE=PASS files={0}" -f $seen.Count)

$proposalInPayload=Join-Path $PayloadRoot 'docs\vibecode\TIP018-FORWARD-ACCEPTANCE-PROPOSAL.yaml'
if((Get-FileHash -LiteralPath $proposalInPayload -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedProposalSha256){throw 'TIP018_PROPOSAL_HASH_MISMATCH'}
$approvalInPayload=Get-Content -LiteralPath (Join-Path $PayloadRoot 'docs\vibecode\OWNER_APPROVAL-TIP018.json') -Raw -Encoding UTF8|ConvertFrom-Json
if([string]$approvalInPayload.status -ne 'APPROVED' -or [string]$approvalInPayload.proposal_sha256 -ne $ExpectedProposalSha256 -or [string]$approvalInPayload.release_manifest_sha256 -ne $ExpectedReleaseManifestSha256){throw 'TIP018_OWNER_APPROVAL_BINDING_FAILED'}
Write-Host 'TIP018_OWNER_APPROVAL_GATE=PASS'

$env:T18_TARGET=$Target;$env:T18_PROJECT=$ProjectId;$env:T18_REV=$ExpectedRevision;$env:T18_REV_SHA=$ExpectedRevisionSha256;$env:T18_SOURCE_SHA=$ExpectedSourceSha256;$env:T18_SOURCE_BYTES=[string]$ExpectedSourceBytes;$env:T18_BASELINE=$ExpectedBaselineJobId;$env:T18_RELEASE_JOB=$ExpectedReleaseJobId;$env:T18_RELEASE_SHA=$ExpectedReleaseManifestSha256
$pre=@'
import hashlib,json,os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.facade import ToolFacade
from vibemql5.core.iterations import IterationManager,TERMINAL_ITERATION_STATES
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T18_TARGET']);p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.14' and p.get('bridge_build')=='TIP-017' and len(REQUIRED_TOOLS)==41
choices=set(build_parser()._subparsers._group_actions[0].choices);assert {'check-all','attest','ship'}<=choices
s=ProjectSessionManager(root).get(os.environ['T18_PROJECT']);r=ProjectSessionManager(root).resume(os.environ['T18_PROJECT'])
assert s['revision_id']==os.environ['T18_REV'] and s['revision_sha256'].lower()==os.environ['T18_REV_SHA'].lower();assert s['source_sha256'].lower()==os.environ['T18_SOURCE_SHA'].lower() and int(s['source_bytes'])==int(os.environ['T18_SOURCE_BYTES']);assert s['baseline_job_id']==os.environ['T18_BASELINE'] and s['last_job_id']==os.environ['T18_BASELINE'] and r['resume_safe'] is True and r['stale_reasons']==[]
a=RevisionManager(root).source_hash(s['workspace'],s['ea']);assert a['sha256']==s['source_sha256'] and int(a['bytes'])==int(s['source_bytes'])
assert not [x for x in IterationManager(root).list() if x.get('state') not in TERMINAL_ITERATION_STATES]
h=ToolFacade(root).health();assert h['queue_length']==0 and h['active_job'] is None
mp=root/'evidence/manifest.json';assert hashlib.sha256(mp.read_bytes()).hexdigest()==os.environ['T18_RELEASE_SHA'];m=json.loads(mp.read_text(encoding='utf-8-sig'));assert m['schema_version']=='2.0' and m['job_id']==os.environ['T18_RELEASE_JOB'] and m['release_eligible'] is True and m['forward_eligible'] is False and m['live_eligible'] is False
print(json.dumps({'TIP018_PREDEPLOY_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'source':a,'baseline_job_id':s['baseline_job_id'],'release_job_id':m['job_id']},sort_keys=True))
'@
$pre|& $python -
if($LASTEXITCODE -ne 0){throw 'TIP018_PREDEPLOY_GATE_FAILED'}
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Get-ExactTunnel([string]$Executable){$expectedExe=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expectedExe)})}
function Http([string]$Url){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3).StatusCode}catch{return 0}}
if((Http $config.supervisor.healthUrl) -ne 200 -or (Http $config.supervisor.readyUrl) -ne 200 -or @(Get-ExactTunnel ([string]$config.tunnel.executable)).Count -ne 1){throw 'TIP018_RUNTIME_PRE_GATE_FAILED'}
Write-Host 'TIP018_RUNTIME_PRE_GATE=PASS healthz=200 readyz=200 tunnel_count=1'

$backupRoot=Join-Path $Target ("logs\TIP018-backup-$stamp");New-Item -ItemType Directory -Path $backupRoot -Force|Out-Null
$existing=@{};foreach($rel in $files){$dst=Join-Path $Target $rel;if(Test-Path -LiteralPath $dst -PathType Leaf){$existing[$rel]=$true;$b=Join-Path $backupRoot $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $b) -Force|Out-Null;Copy-Item -LiteralPath $dst -Destination $b -Force}else{$existing[$rel]=$false}}
Copy-Item -LiteralPath $projectState -Destination (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Force
$taskNames=@([string]$config.tasks.tunnelTaskName,[string]$config.tasks.watchdogTaskName,[string]$config.tasks.backgroundTunnelTaskName)
try{
  foreach($n in $taskNames){if($n){Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue}};Start-Sleep -Seconds 1
  foreach($proc in @(Get-ExactTunnel ([string]$config.tunnel.executable))){& taskkill.exe /PID ([string]$proc.ProcessId) /T /F|Out-Null}
  foreach($rel in $files){$src=Join-Path $PayloadRoot $rel;$dst=Join-Path $Target $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force|Out-Null;Copy-Item -LiteralPath $src -Destination $dst -Force}
  Write-Host 'TIP018_COPY_GATE=PASS'
  & $python -m pip install -e $Target --no-deps
  if($LASTEXITCODE -ne 0){throw 'TIP018_PIP_INSTALL_FAILED'}

  $env:T18_STATE=$projectState
  $statePatch=@'
import hashlib,os
from pathlib import Path
p=Path(os.environ['T18_STATE']);raw=p.read_bytes();nl=b'\r\n' if b'\r\n' in raw else b'\n';text=raw.decode('utf-8-sig');lines=text.splitlines()
pairs={'active_tip: TIP-017':'active_tip: TIP-018','phase: CLOSED':'phase: VERIFY','bridge_target: 0.2.14':'bridge_target: 0.2.15','bridge_build: TIP-017':'bridge_build: TIP-018'}
for old,new in pairs.items():
    idx=[i for i,x in enumerate(lines) if x==old]
    if len(idx)!=1: raise SystemExit('TIP018_PROJECT_STATE_TARGET_MISMATCH '+repr(old)+' count='+str(len(idx)))
    lines[idx[0]]=new
out=nl.join(x.encode('utf-8') for x in lines)+nl
p.write_bytes(out);print(hashlib.sha256(out).hexdigest())
'@
  $items=@($statePatch|& $python - 2>&1);$exit=$LASTEXITCODE;$txt=($items|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine
  if($exit -ne 0){throw "TIP018_PROJECT_STATE_PATCH_FAILED exit=$exit output=$txt"}
  $postSha=(($items|Select-Object -Last 1).ToString()).Trim();if($postSha -notmatch '^[0-9a-f]{64}$'){throw "TIP018_PROJECT_STATE_PATCH_OUTPUT_INVALID=$txt"}
  Write-Host "TIP018_PROJECT_STATE_GATE=PASS sha256=$postSha"

  $post=@'
import hashlib,json,os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T18_TARGET']);p=load_bridge_provenance(root);choices=set(build_parser()._subparsers._group_actions[0].choices)
assert vibemql5.__version__=='0.2.15' and p.get('bridge_build')=='TIP-018' and len(REQUIRED_TOOLS)==41 and {'check-all','attest','ship','forward-check','forward-attest','forward-promote'}<=choices
s=ProjectSessionManager(root).get(os.environ['T18_PROJECT']);a=RevisionManager(root).source_hash(s['workspace'],s['ea']);assert s['revision_id']==os.environ['T18_REV'] and s['revision_sha256'].lower()==os.environ['T18_REV_SHA'].lower();assert a['sha256']==os.environ['T18_SOURCE_SHA'].lower() and int(a['bytes'])==int(os.environ['T18_SOURCE_BYTES']);assert s['baseline_job_id']==os.environ['T18_BASELINE'] and s['last_job_id']==os.environ['T18_BASELINE']
mp=root/'evidence/manifest.json';assert hashlib.sha256(mp.read_bytes()).hexdigest()==os.environ['T18_RELEASE_SHA'];m=json.loads(mp.read_text(encoding='utf-8-sig'));assert m['release_eligible'] is True and m['forward_eligible'] is False and m['live_eligible'] is False
print(json.dumps({'TIP018_LOCAL_MODULE_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'commands':['forward-check','forward-attest','forward-promote'],'revision':s['revision_id'],'source':a},sort_keys=True))
'@
  $post|& $python -
  if($LASTEXITCODE -ne 0){throw 'TIP018_LOCAL_MODULE_GATE_FAILED'}
  $sid=[Diagnostics.Process]::GetCurrentProcess().SessionId;if($sid -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}else{throw 'TIP018_NO_RUNTIME_MODE_AVAILABLE'}
  $ready=$false;for($i=0;$i -lt 90;$i++){Start-Sleep -Seconds 1;if((Http $config.supervisor.healthUrl) -eq 200 -and (Http $config.supervisor.readyUrl) -eq 200 -and @(Get-ExactTunnel ([string]$config.tunnel.executable)).Count -eq 1){$ready=$true;break}};if(-not $ready){throw 'TIP018_RUNTIME_NOT_READY'}
  $t=@(Get-ExactTunnel ([string]$config.tunnel.executable));Write-Host ("TIP018_RUNTIME_POST_GATE=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
}
catch{
  Write-Host 'TIP018_ROLLBACK_BEGIN'
  foreach($rel in $files){$dst=Join-Path $Target $rel;$b=Join-Path $backupRoot $rel;if($existing[$rel]){if(Test-Path -LiteralPath $b){New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force|Out-Null;Copy-Item -LiteralPath $b -Destination $dst -Force}}else{Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue}}
  Copy-Item -LiteralPath (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Destination $projectState -Force
  & $python -m pip install -e $Target --no-deps|Out-Null
  Write-Host 'TIP018_ROLLBACK_FILES=PASS'
  try{if([Diagnostics.Process]::GetCurrentProcess().SessionId -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}}catch{}
  throw
}
Write-Host 'TIP018_APPLY=PASS'
