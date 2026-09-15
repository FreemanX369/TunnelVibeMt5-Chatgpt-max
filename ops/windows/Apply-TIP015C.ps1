[CmdletBinding()]
param(
    [string]$Target='C:\VibeMQL5',
    [string]$PayloadRoot='',
    [string]$ProjectId='TIP014-DEMOEA-E2E-20260830',
    [string]$ExpectedRevision='REV-000004',
    [string]$ExpectedRevisionSha256='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989',
    [string]$ExpectedSourceSha256='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c',
    [Int64]$ExpectedSourceBytes=2026,
    [string]$ExpectedBaselineJobId='BT-20260831-001933-B0484B'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$ops=Join-Path $Target 'ops\windows'
$configPath=Join-Path $ops 'vibemql5.windows.json'
if(-not(Test-Path -LiteralPath $python)){throw "TIP015C_PYTHON_MISSING: $python"}
if(-not(Test-Path -LiteralPath $configPath)){throw "TIP015C_WINDOWS_CONFIG_MISSING: $configPath"}
if(-not $PayloadRoot){$candidate=Join-Path $PSScriptRoot 'payload';if(Test-Path -LiteralPath $candidate){$PayloadRoot=$candidate}else{$PayloadRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)}}
$PayloadRoot=(Resolve-Path -LiteralPath $PayloadRoot).Path
foreach($name in @('workspaces','state','runs','secrets')){if(Test-Path -LiteralPath (Join-Path $PayloadRoot $name)){throw "TIP015C_FORBIDDEN_PAYLOAD_PATH: $name/**"}}
$files=@(
'app\vibemql5\__init__.py',
'app\vibemql5\adapters\cli.py',
'app\vibemql5\adapters\mcp.py',
'app\vibemql5\adapters\mcp_client_check.py',
'app\vibemql5\adapters\retro_cli.py',
'app\vibemql5\core\facade.py',
'app\vibemql5\core\observability.py',
'app\vibemql5\core\retro.py',
'config\build-provenance.json',
'pyproject.toml',
'ops\windows\Apply-TIP015C.ps1',
'ops\windows\Test-TIP015C.ps1',
'docs\vibecode\DECISIONS.yaml',
'docs\vibecode\PROJECT_STATE.yaml',
'docs\vibecode\TIP-015C-RRI.yaml',
'docs\vibecode\TIP-015C-SPEC.yaml',
'docs\vibecode\TIP-015C-CONTRACT.yaml',
'docs\vibecode\TASK-GRAPH-TIP015C.yaml',
'docs\vibecode\AI-BUILD-CONTRACT.json',
'docs\vibecode\AI-BUILD-CONTRACT-TIP015C.md',
'docs\vibecode\AI-BUILD-CONTRACT-TIP015C.json',
'docs\vibecode\OWNER_APPROVAL-TIP015C.json',
'docs\vibecode\TIP015C-WINDOWS-RUNBOOK.md',
'docs\vibecode\TIP015C-LOCAL-TESTS.txt',
'docs\vibecode\TIP015C-POSTEDIT-HASHES.json',
'docs\vibecode\TIP015C-RETRO-EVIDENCE.json',
'docs\vibecode\TIP015C-RETRO-LOCAL-RESULT.json',
'docs\vibecode\TIP015C-LOCAL-EVIDENCE.json',
'BUILD_REPORT\TIP-015C-LOCAL-COMPLETION.md',
'tests\unit\test_rc6_mcp_contract.py',
'tests\unit\test_tip011b_runtime_refresh.py',
'tests\unit\test_tip012_recovery.py',
'tests\unit\test_tip013_resilience.py',
'tests\unit\test_tip014_project_sessions.py',
'tests\unit\test_tip015_provenance.py',
'tests\unit\test_tip015c_observability.py',
'tests\unit\test_tip015c_retro.py',
'tests\unit\test_tip015c_deploy_contract.py'
)
foreach($rel in $files){
    $low=$rel.Replace('/','\').ToLowerInvariant();foreach($prefix in @('workspaces\','state\','runs\','secrets\')){if($low.StartsWith($prefix)){throw "TIP015C_FORBIDDEN_ALLOWLIST_ENTRY: $rel"}}
    if(-not(Test-Path -LiteralPath (Join-Path $PayloadRoot $rel) -PathType Leaf)){throw "TIP015C_PAYLOAD_MISSING: $rel"}
}
Write-Host ("TIP015C_ALLOWLIST_GATE=PASS files={0}" -f $files.Count)
$manifestPath=Join-Path $PayloadRoot 'TIP015C-PAYLOAD-MANIFEST.sha256'
if(-not(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw 'TIP015C_PAYLOAD_MANIFEST_MISSING'}
$expected=@{};foreach($rel in $files){$expected[$rel.Replace('\','/').ToLowerInvariant()]=$true};$seen=@{}
foreach($line in @(Get-Content -LiteralPath $manifestPath -Encoding UTF8)){
    if([string]::IsNullOrWhiteSpace([string]$line)){continue}
    if([string]$line -notmatch '^([0-9a-fA-F]{64})\s+(.+)$'){throw "TIP015C_MANIFEST_INVALID_LINE: $line"}
    $want=$Matches[1].ToLowerInvariant();$rel=$Matches[2].Trim().Replace('\','/');$key=$rel.ToLowerInvariant()
    if(-not $expected.ContainsKey($key)){throw "TIP015C_MANIFEST_UNEXPECTED_ENTRY: $rel"};if($seen.ContainsKey($key)){throw "TIP015C_MANIFEST_DUPLICATE_ENTRY: $rel"}
    $candidate=[IO.Path]::GetFullPath((Join-Path $PayloadRoot $rel));$rootFull=[IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\')+'\';if(-not $candidate.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){throw "TIP015C_MANIFEST_PATH_ESCAPE: $rel"}
    $got=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant();if($got -ne $want){throw "TIP015C_PAYLOAD_HASH_MISMATCH: $rel expected=$want actual=$got"};$seen[$key]=$true
}
if($seen.Count -ne $expected.Count){throw "TIP015C_MANIFEST_COUNT_MISMATCH expected=$($expected.Count) actual=$($seen.Count)"}
Write-Host ("TIP015C_PAYLOAD_MANIFEST_GATE=PASS files={0}" -f $seen.Count)
$env:T15C_TARGET=$Target;$env:T15C_PROJECT=$ProjectId;$env:T15C_REV=$ExpectedRevision;$env:T15C_REV_SHA=$ExpectedRevisionSha256;$env:T15C_SOURCE_SHA=$ExpectedSourceSha256;$env:T15C_SOURCE_BYTES=[string]$ExpectedSourceBytes;$env:T15C_BASELINE=$ExpectedBaselineJobId
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
root=Path(os.environ['T15C_TARGET']); p=load_bridge_provenance(root); version=vibemql5.__version__; build=p.get('bridge_build')
assert (version,build,len(REQUIRED_TOOLS)) in {('0.2.11','TIP-015B',38),('0.2.12','TIP-015C',41)}, (version,build,len(REQUIRED_TOOLS))
ps=ProjectSessionManager(root); s=ps.get(os.environ['T15C_PROJECT']); r=ps.resume(os.environ['T15C_PROJECT'])
assert s['revision_id']==os.environ['T15C_REV'] and s['revision_sha256'].lower()==os.environ['T15C_REV_SHA'].lower()
assert s['source_sha256'].lower()==os.environ['T15C_SOURCE_SHA'].lower() and int(s['source_bytes'])==int(os.environ['T15C_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T15C_BASELINE'] and s['last_job_id']==os.environ['T15C_BASELINE']
assert r['integrity']=='VERIFIED' and r['resume_safe'] is True and r['stale_reasons']==[]
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==s['source_sha256'] and int(a['bytes'])==int(s['source_bytes'])
active=[x for x in IterationManager(root).list() if x.get('state') not in TERMINAL_ITERATION_STATES]; assert not active, active
h=ToolFacade(root).health(); assert h['queue_length']==0 and h['active_job'] is None, h
assert TIP015BFaultInjector(root).status().get('status')!='ARMED'
print(json.dumps({'TIP015C_PREDEPLOY_GATE':'PASS','version':version,'bridge_build':build,'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'revision_sha256':s['revision_sha256'],'source':a,'baseline_job_id':s['baseline_job_id'],'resume_safe':r['resume_safe']},sort_keys=True))
'@
$pre | & $python -
if($LASTEXITCODE -ne 0){throw 'TIP015C_PREDEPLOY_GATE_FAILED'}
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Get-ExactTunnelProcess([string]$Executable){$expected=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})}
$preHealth=0;$preReady=0;try{$preHealth=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.healthUrl -TimeoutSec 3).StatusCode}catch{};try{$preReady=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.readyUrl -TimeoutSec 3).StatusCode}catch{};$preTunnels=@(Get-ExactTunnelProcess ([string]$config.tunnel.executable));if($preHealth -ne 200 -or $preReady -ne 200 -or $preTunnels.Count -ne 1){throw "TIP015C_RUNTIME_PRE_GATE_FAILED health=$preHealth ready=$preReady tunnels=$($preTunnels.Count)"}
Write-Host ("TIP015C_RUNTIME_PRE_GATE=PASS healthz={0} readyz={1} tunnel_count=1" -f $preHealth,$preReady)
$taskNames=@([string]$config.tasks.tunnelTaskName,[string]$config.tasks.watchdogTaskName,[string]$config.tasks.backgroundTunnelTaskName);foreach($n in $taskNames){if($n){Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue}};Start-Sleep -Seconds 1
foreach($proc in @(Get-ExactTunnelProcess ([string]$config.tunnel.executable))){& taskkill.exe /PID ([string]$proc.ProcessId) /T /F | Out-Null}
for($i=0;$i -lt 20;$i++){Start-Sleep -Milliseconds 250;if(@(Get-ExactTunnelProcess ([string]$config.tunnel.executable)).Count -eq 0){break}};if(@(Get-ExactTunnelProcess ([string]$config.tunnel.executable)).Count -ne 0){throw 'TIP015C_STALE_TUNNEL_REMAINS'}
foreach($rel in $files){$src=Join-Path $PayloadRoot $rel;$dst=Join-Path $Target $rel;$parent=Split-Path -Parent $dst;if(-not(Test-Path -LiteralPath $parent)){New-Item -ItemType Directory -Path $parent -Force|Out-Null};if(Test-Path -LiteralPath $dst){Copy-Item -LiteralPath $dst -Destination ($dst+'.pre-tip015c.'+$stamp+'.bak') -Force};Copy-Item -LiteralPath $src -Destination $dst -Force}
Write-Host 'TIP015C_COPY_GATE=PASS'
& $python -m pip install -e $Target --no-deps
if($LASTEXITCODE -ne 0){throw 'TIP015C_PIP_REFRESH_FAILED'}
$post=@'
import json, os, sys
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.fault_injection import TIP015BFaultInjector
from vibemql5.core.iterations import IterationManager, TERMINAL_ITERATION_STATES
from vibemql5.core.observability import ObservabilityManager
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T15C_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.12' and p.get('bridge_build')=='TIP-015C' and len(REQUIRED_TOOLS)==41
ps=ProjectSessionManager(root); s=ps.get(os.environ['T15C_PROJECT']); r=ps.resume(os.environ['T15C_PROJECT'])
assert s['revision_id']==os.environ['T15C_REV'] and s['revision_sha256'].lower()==os.environ['T15C_REV_SHA'].lower()
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==os.environ['T15C_SOURCE_SHA'].lower() and int(a['bytes'])==int(os.environ['T15C_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T15C_BASELINE'] and s['last_job_id']==os.environ['T15C_BASELINE']; assert r['resume_safe'] is True and r['stale_reasons']==[]
iterations=[x for x in IterationManager(root).list() if x.get('project_id')==os.environ['T15C_PROJECT']]; assert iterations and not [x for x in iterations if x.get('state') not in TERMINAL_ITERATION_STATES]
obs=ObservabilityManager(root); ih=obs.iteration_history(iterations[-1]['iteration_id'],limit=1000); assert ih['count_total']>=1 and ih['source']=='direct_durable_read'
fr=obs.fault_receipts(limit=1000); assert fr['count_total']>=5 and fr['source']=='direct_durable_read'
jh=obs.job_history(limit=1000); assert os.environ['T15C_BASELINE'] in {x['job_id'] for x in jh['jobs']}
assert TIP015BFaultInjector(root).status().get('status')!='ARMED'
scripts=Path(sys.executable).parent
assert (scripts/'mql5-retro-init.exe').is_file() or (scripts/'mql5-retro-init').is_file()
assert (scripts/'vkmql-check.exe').is_file() or (scripts/'vkmql-check').is_file()
print(json.dumps({'TIP015C_LOCAL_MODULE_GATE':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'source':a,'iteration_history_count':ih['count_total'],'fault_receipt_count':fr['count_total'],'job_history_count':jh['count_total']},sort_keys=True))
'@
$post | & $python -
if($LASTEXITCODE -ne 0){throw 'TIP015C_LOCAL_MODULE_GATE_FAILED'}
$sessionId=[Diagnostics.Process]::GetCurrentProcess().SessionId;if($sessionId -ne 0){Start-ScheduledTask -TaskName ([string]$config.tasks.tunnelTaskName)}elseif([bool]$config.tasks.enableBootTunnel){Start-ScheduledTask -TaskName ([string]$config.tasks.backgroundTunnelTaskName)}else{throw 'TIP015C_NO_RUNTIME_MODE_AVAILABLE'}
$ready=$false;for($i=0;$i -lt 90;$i++){Start-Sleep -Seconds 1;try{$h=Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.healthUrl -TimeoutSec 2;$r=Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.readyUrl -TimeoutSec 2;if($h.StatusCode -eq 200 -and $r.StatusCode -eq 200){$ready=$true;break}}catch{}};if(-not $ready){throw 'TIP015C_RUNTIME_NOT_READY'}
$t=@(Get-ExactTunnelProcess ([string]$config.tunnel.executable));if($t.Count -ne 1){throw "TIP015C_TUNNEL_COUNT_FAILED count=$($t.Count)"}
Write-Host ("TIP015C_RUNTIME_POST_GATE=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
Write-Host 'TIP015C_APPLY=PASS'
