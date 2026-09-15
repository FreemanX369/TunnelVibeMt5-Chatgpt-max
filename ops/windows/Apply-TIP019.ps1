[CmdletBinding()]
param(
  [string]$Target='C:\VibeMQL5',
  [string]$PayloadRoot=''
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$ExpectedState='cf6e42bd19178bd606736a39284506d6ba69b6f4c814dff56909f9f3337a431d'
$ExpectedDecisions='4d0d65e875fbcd054b3e522cdb116f207be7651565b71dff75ec620664df5793'
$ExpectedClosure='ec053a64318b9ebbbb8057871a91808c8ba81ed3a8e717ed939a1f7a72b36a89'
$ExpectedForwardManifest='0590e1ec98d9c2e610febc30f6d09dcb9a4eef40fab8b10a28a65f2eea77ef76'
$ExpectedForwardPatch='be308d7fd5a9891b113ecf908ba760d4856a9ed43e53064c8246110b81751b33'
$ExpectedForwardTest='b0043d12a63a805013ff17a9723adb67d87a26130fd03ee4be59bf0ef8d909eb'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json'
$statePath=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml'
$decisionsPath=Join-Path $Target 'docs\vibecode\DECISIONS.yaml'
$closurePath=Join-Path $Target 'evidence\TIP018-CLOSURE-20260902-171306.zip'
$releasePath=Join-Path $Target 'evidence\manifest.json'
if(-not $PayloadRoot){$PayloadRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)}
$PayloadRoot=(Resolve-Path -LiteralPath $PayloadRoot).Path
function Sha([string]$p){if(!(Test-Path -LiteralPath $p -PathType Leaf)){return $null};return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Http([string]$u){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3).StatusCode}catch{return 0}}
if(!(Test-Path -LiteralPath $python -PathType Leaf)){throw 'TIP019_PYTHON_MISSING'}
if(!(Test-Path -LiteralPath $configPath -PathType Leaf)){throw 'TIP019_WINDOWS_CONFIG_MISSING'}
if((Sha $statePath) -ne $ExpectedState){throw "TIP019_PROJECT_STATE_PREHASH_MISMATCH actual=$(Sha $statePath)"}
if((Sha $decisionsPath) -ne $ExpectedDecisions){throw 'TIP019_DECISIONS_PREHASH_MISMATCH'}
if((Sha $closurePath) -ne $ExpectedClosure){throw 'TIP019_TIP018_CLOSURE_HASH_MISMATCH'}
if((Sha $releasePath) -ne $ExpectedForwardManifest){throw 'TIP019_FORWARD_MANIFEST_PREHASH_MISMATCH'}
if((Sha (Join-Path $Target 'app\vibemql5\core\forward.py')) -ne $ExpectedForwardPatch){throw 'TIP019_TIP018A_FORWARD_PATCH_MISMATCH'}
if((Sha (Join-Path $Target 'tests\unit\test_tip018_forward_pipeline.py')) -ne $ExpectedForwardTest){throw 'TIP019_TIP018A_FORWARD_TEST_MISMATCH'}
$stateText=Get-Content -LiteralPath $statePath -Raw -Encoding UTF8
foreach($n in @('active_tip: TIP-018','phase: CLOSED','bridge_target: 0.2.15','bridge_build: TIP-018','release_eligible: true','forward_eligible: true','live_eligible: false')){if($stateText -notmatch [regex]::Escape($n)){throw "TIP019_STATE_PRECONDITION_MISSING=$n"}}
Write-Host 'TIP019_PREAUTHORITY=PASS'

$files=@(
'app\vibemql5\__init__.py',
'app\vibemql5\adapters\cli.py',
'app\vibemql5\core\facade.py',
'app\vibemql5\core\live_readiness.py',
'config\build-provenance.json',
'pyproject.toml',
'docs\vibecode\TIP-019-LIVE-READINESS-BLUEPRINT.yaml',
'docs\vibecode\TIP-019-DECISION.yaml',
'docs\vibecode\TIP019-LIVE-READINESS-POLICY.json',
'docs\vibecode\OWNER_APPROVAL-TIP019-BUILD.json',
'docs\vibecode\AI-BUILD-CONTRACT-TIP019.json',
'docs\vibecode\TASK-GRAPH-TIP019.yaml',
'docs\vibecode\TIP019-LOCAL-TESTS.txt',
'docs\vibecode\TIP019-LOCAL-EVIDENCE.json',
'docs\vibecode\TIP019-RETRO-LOCAL-RESULT.json',
'docs\vibecode\TIP019-POSTEDIT-HASHES.json',
'BUILD_REPORT\TIP-019-LOCAL-COMPLETION.md',
'ops\windows\Apply-TIP019.ps1',
'ops\windows\Test-TIP019.ps1',
'ops\windows\Collect-TIP019LiveReadinessScan.ps1',
'ops\windows\Review-TIP019LiveReadinessScan.ps1',
'ops\windows\Invoke-TIP019ReadOnlyQualification.ps1',
'tests\unit\test_tip019_live_readiness.py',
'tests\unit\test_tip011b_runtime_refresh.py',
'tests\unit\test_tip012_recovery.py',
'tests\unit\test_tip013_resilience.py',
'tests\unit\test_tip014_project_sessions.py',
'tests\unit\test_tip015_provenance.py',
'tests\unit\test_tip015c_deploy_contract.py',
'tests\unit\test_tip016_deploy_contract.py',
'tests\unit\test_tip017_deploy_contract.py',
'tests\unit\test_tip018_deploy_contract.py'
)
foreach($name in @('workspaces','state','runs','secrets','evidence')){if(Test-Path -LiteralPath (Join-Path $PayloadRoot $name)){throw "TIP019_FORBIDDEN_PAYLOAD_PATH=$name"}}
foreach($rel in $files){$src=Join-Path $PayloadRoot $rel;if(!(Test-Path -LiteralPath $src -PathType Leaf)){throw "TIP019_PAYLOAD_MISSING=$rel"}}
$manifestPath=Join-Path $PayloadRoot 'TIP019-PAYLOAD-MANIFEST.sha256'
if(!(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw 'TIP019_PAYLOAD_MANIFEST_MISSING'}
$expected=@{};foreach($rel in $files){$expected[$rel.Replace('\','/').ToLowerInvariant()]=$true};$seen=@{}
foreach($line in Get-Content -LiteralPath $manifestPath -Encoding UTF8){if([string]::IsNullOrWhiteSpace($line)){continue};if($line -notmatch '^([0-9a-fA-F]{64})\s+(.+)$'){throw "TIP019_MANIFEST_INVALID_LINE=$line"};$want=$Matches[1].ToLowerInvariant();$rel=$Matches[2].Trim().Replace('\','/');$key=$rel.ToLowerInvariant();if(-not $expected.ContainsKey($key)){throw "TIP019_MANIFEST_UNEXPECTED=$rel"};$got=Sha (Join-Path $PayloadRoot $rel);if($got -ne $want){throw "TIP019_PAYLOAD_HASH_MISMATCH=$rel"};$seen[$key]=$true}
if($seen.Count -ne $expected.Count){throw "TIP019_MANIFEST_COUNT_MISMATCH expected=$($expected.Count) actual=$($seen.Count)"}
Write-Host "TIP019_PAYLOAD_GATE=PASS files=$($seen.Count)"

$env:T19_TARGET=$Target
$pre=@'
import json,os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.provenance import load_bridge_provenance
root=Path(os.environ['T19_TARGET']); p=load_bridge_provenance(root); choices=set(build_parser()._subparsers._group_actions[0].choices)
assert vibemql5.__version__=='0.2.15' and p.get('bridge_build')=='TIP-018' and len(REQUIRED_TOOLS)==41
assert {'check-all','attest','ship','forward-check','forward-attest','forward-promote'} <= choices
m=json.loads((root/'evidence/manifest.json').read_text(encoding='utf-8-sig'))
assert m.get('release_eligible') is True and m.get('forward_eligible') is True and m.get('live_eligible') is False
print('TIP019_PREDEPLOY_PYTHON=PASS')
'@
$pre|& $python -
if($LASTEXITCODE -ne 0){throw 'TIP019_PREDEPLOY_PYTHON_FAILED'}

$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Get-ExactTunnel(){ $expectedPath=[IO.Path]::GetFullPath([string]$config.tunnel.executable); return @(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expectedPath)}) }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss';$backupRoot=Join-Path $Target "logs\TIP019-backup-$stamp";New-Item -ItemType Directory -Path $backupRoot -Force|Out-Null
$existing=@{};foreach($rel in $files){$dst=Join-Path $Target $rel;$existing[$rel]=(Test-Path -LiteralPath $dst -PathType Leaf);if($existing[$rel]){$b=Join-Path $backupRoot $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $b) -Force|Out-Null;Copy-Item -LiteralPath $dst -Destination $b -Force}}
Copy-Item -LiteralPath $statePath -Destination (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Force
Write-Host "TIP019_BACKUP=$backupRoot"
try{
  try{Stop-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName) -ErrorAction SilentlyContinue}catch{}
  foreach($proc in @(Get-ExactTunnel)){& taskkill.exe /PID ([string]$proc.ProcessId) /T /F|Out-Null}
  foreach($rel in $files){$src=Join-Path $PayloadRoot $rel;$dst=Join-Path $Target $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force|Out-Null;Copy-Item -LiteralPath $src -Destination $dst -Force}
  & $python -m pip install -e $Target --no-deps
  if($LASTEXITCODE -ne 0){throw 'TIP019_PIP_INSTALL_FAILED'}
  $env:T19_STATE=$statePath;$env:T19_STATE_PRE=$ExpectedState
  $patch=@'
import hashlib,os
from pathlib import Path
p=Path(os.environ['T19_STATE']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==os.environ['T19_STATE_PRE'];nl=b'\r\n' if b'\r\n' in raw else b'\n';lines=raw.decode('utf-8-sig').splitlines()
for old,new in [('active_tip: TIP-018','active_tip: TIP-019'),('phase: CLOSED','phase: VERIFY'),('bridge_target: 0.2.15','bridge_target: 0.2.16'),('bridge_build: TIP-018','bridge_build: TIP-019')]:
 idx=[i for i,x in enumerate(lines) if x==old]
 if len(idx)!=1: raise SystemExit('TIP019_STATE_PATCH_TARGET_MISMATCH '+repr(old)+' count='+str(len(idx)))
 lines[idx[0]]=new
out=nl.join(x.encode('utf-8') for x in lines)+nl;p.write_bytes(out);print(hashlib.sha256(out).hexdigest())
'@
  $patchOut=@($patch|& $python - 2>&1);if($LASTEXITCODE -ne 0){throw "TIP019_STATE_PATCH_FAILED output=$($patchOut -join [Environment]::NewLine)"};$postState=(($patchOut|Select-Object -Last 1).ToString()).Trim();Write-Host "TIP019_PROJECT_STATE=PASS sha256=$postState"
  $post=@'
import json,os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.live_readiness import LiveReadinessManager
from vibemql5.core.provenance import load_bridge_provenance
root=Path(os.environ['T19_TARGET']);p=load_bridge_provenance(root);choices=set(build_parser()._subparsers._group_actions[0].choices)
assert vibemql5.__version__=='0.2.16' and p.get('bridge_build')=='TIP-019' and len(REQUIRED_TOOLS)==41
assert {'live-check','live-attest','live-package'} <= choices
m=json.loads((root/'evidence/manifest.json').read_text(encoding='utf-8-sig'));assert m.get('release_eligible') is True and m.get('forward_eligible') is True and m.get('live_eligible') is False
LiveReadinessManager(root)._authority('TIP014-DEMOEA-E2E-20260830')
print('TIP019_POSTDEPLOY_PYTHON=PASS')
'@
  $post|& $python -
  if($LASTEXITCODE -ne 0){throw 'TIP019_POSTDEPLOY_PYTHON_FAILED'}
  Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)
  $ok=$false;for($i=0;$i -lt 90;$i++){Start-Sleep -Seconds 1;$t=@(Get-ExactTunnel);if((Http ([string]$config.supervisor.healthUrl)) -eq 200 -and (Http ([string]$config.supervisor.readyUrl)) -eq 200 -and $t.Count -eq 1){$ok=$true;break}}
  if(-not $ok){throw 'TIP019_RUNTIME_NOT_READY'}
  $t=@(Get-ExactTunnel);Write-Host "TIP019_RUNTIME_POST_GATE=PASS health=200 ready=200 tunnel_count=1 tunnel_pid=$($t[0].ProcessId)"
}
catch{
  Write-Host 'TIP019_ROLLBACK_BEGIN'
  foreach($rel in $files){$dst=Join-Path $Target $rel;$b=Join-Path $backupRoot $rel;if($existing[$rel]){if(Test-Path -LiteralPath $b){New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force|Out-Null;Copy-Item -LiteralPath $b -Destination $dst -Force}}else{Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue}}
  Copy-Item -LiteralPath (Join-Path $backupRoot 'PROJECT_STATE.yaml') -Destination $statePath -Force
  & $python -m pip install -e $Target --no-deps|Out-Null
  try{Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}catch{}
  Write-Host 'TIP019_ROLLBACK=PASS'
  throw
}
Write-Host 'TIP019_APPLY=PASS'
Write-Host 'release_eligible=true'
Write-Host 'forward_eligible=true'
Write-Host 'live_eligible=false'
