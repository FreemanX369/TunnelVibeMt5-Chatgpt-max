[CmdletBinding()]
param(
    [string]$Target='C:\VibeMQL5',
    [string]$ProjectId='TIP014-DEMOEA-E2E-20260830',
    [string]$ExpectedRevision='REV-000004',
    [string]$ExpectedRevisionSha256='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989',
    [string]$ExpectedSourceSha256='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c',
    [Int64]$ExpectedSourceBytes=2026,
    [string]$ExpectedBaselineJobId='BT-20260831-001933-B0484B'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$config=Get-Content -LiteralPath (Join-Path $Target 'ops\windows\vibemql5.windows.json') -Raw -Encoding UTF8|ConvertFrom-Json
$env:T15C_TARGET=$Target;$env:T15C_PROJECT=$ProjectId;$env:T15C_REV=$ExpectedRevision;$env:T15C_REV_SHA=$ExpectedRevisionSha256;$env:T15C_SOURCE_SHA=$ExpectedSourceSha256;$env:T15C_SOURCE_BYTES=[string]$ExpectedSourceBytes;$env:T15C_BASELINE=$ExpectedBaselineJobId
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
root=Path(os.environ['T15C_TARGET']); p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.12' and p.get('bridge_build')=='TIP-015C' and len(REQUIRED_TOOLS)==41
ps=ProjectSessionManager(root); s=ps.get(os.environ['T15C_PROJECT']); r=ps.resume(os.environ['T15C_PROJECT'])
assert s['revision_id']==os.environ['T15C_REV'] and s['revision_sha256'].lower()==os.environ['T15C_REV_SHA'].lower()
assert s['source_sha256'].lower()==os.environ['T15C_SOURCE_SHA'].lower() and int(s['source_bytes'])==int(os.environ['T15C_SOURCE_BYTES'])
assert s['baseline_job_id']==os.environ['T15C_BASELINE'] and s['last_job_id']==os.environ['T15C_BASELINE']; assert r['integrity']=='VERIFIED' and r['resume_safe'] is True and r['stale_reasons']==[]
a=RevisionManager(root).source_hash(s['workspace'],s['ea']); assert a['sha256']==s['source_sha256'] and int(a['bytes'])==int(s['source_bytes'])
iterations=[x for x in IterationManager(root).list() if x.get('project_id')==s['project_id']]; assert iterations and not [x for x in iterations if x.get('state') not in TERMINAL_ITERATION_STATES]
obs=ObservabilityManager(root)
ih=obs.iteration_history(iterations[-1]['iteration_id'],limit=1000); assert ih['count_total']>=1 and ih['source']=='direct_durable_read'; assert ih['pointer_status'] in {'CURRENT','LAGGING_DURABLE_REVISIONS'}
fr=obs.fault_receipts(limit=1000); points={x['point'] for x in fr['receipts']}; assert {'ACCEPT_AFTER_SESSION_UPDATE','TEST_AFTER_PREPARED','TEST_AFTER_RESERVED','ROLLBACK_AFTER_INTENT','CANCEL_AFTER_INTENT'} <= points
jh=obs.job_history(limit=1000); assert os.environ['T15C_BASELINE'] in {x['job_id'] for x in jh['jobs']}
assert TIP015BFaultInjector(root).status().get('status')!='ARMED'
h=ToolFacade(root).health(); assert h['queue_length']==0 and h['active_job'] is None, h
print(json.dumps({'TIP015C_PYTHON_VERIFY':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'revision':s['revision_id'],'revision_sha256':s['revision_sha256'],'source':a,'baseline_job_id':s['baseline_job_id'],'resume_safe':r['resume_safe'],'iteration_history':ih['count_total'],'fault_receipts':fr['count_total'],'job_history':jh['count_total']},sort_keys=True))
'@
$probe | & $python -
if($LASTEXITCODE -ne 0){throw 'TIP015C_PYTHON_VERIFY_FAILED'}

$scriptDir=Join-Path $Target '.venv\Scripts'
$retroInit=Join-Path $scriptDir 'mql5-retro-init.exe';if(-not(Test-Path -LiteralPath $retroInit)){$retroInit=Join-Path $scriptDir 'mql5-retro-init'}
$retroCheck=Join-Path $scriptDir 'vkmql-check.exe';if(-not(Test-Path -LiteralPath $retroCheck)){$retroCheck=Join-Path $scriptDir 'vkmql-check'}
if(-not(Test-Path -LiteralPath $retroInit)){throw 'TIP015C_RETRO_INIT_ENTRYPOINT_MISSING'}
if(-not(Test-Path -LiteralPath $retroCheck)){throw 'TIP015C_VKMQL_CHECK_ENTRYPOINT_MISSING'}
$scratch=Join-Path $Target ('logs\TIP015C-retro-smoke-'+[guid]::NewGuid().ToString('N'))
try{
    New-Item -ItemType Directory -Path (Join-Path $scratch 'docs\vibecode') -Force|Out-Null
    $contract=@{
        schema_version='1.0';tip='TIP-015C-SMOKE';guards=@(@{
            id='RETRO-A1';severity='P1';class='hard';checker='retro.count_order_state';required_evidence=@('numeric_examples','boundary_tests');waiver_allowed=$false
        })
    }|ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText((Join-Path $scratch 'docs\vibecode\AI-BUILD-CONTRACT.json'),$contract+[Environment]::NewLine,(New-Object Text.UTF8Encoding($false)))
    $initOut=& $retroInit --root $scratch 'TIP015C-SMOKE' 2>&1|Out-String
    if($LASTEXITCODE -ne 0){throw "TIP015C_RETRO_INIT_SMOKE_FAILED: $initOut"}
    $initObj=$initOut|ConvertFrom-Json;if($initObj.records[0].status -ne 'UNTESTABLE'){throw 'TIP015C_RETRO_INIT_NOT_UNTESTABLE'}
    $checkOut=& $retroCheck --root $scratch retro 'TIP015C-SMOKE' 2>&1|Out-String
    $checkExit=$LASTEXITCODE
    if($checkExit -ne 3){throw "TIP015C_RETRO_UNTESTABLE_EXIT_MISMATCH exit=$checkExit output=$checkOut"}
    $checkObj=$checkOut|ConvertFrom-Json;if($checkObj.status -ne 'UNTESTABLE'){throw 'TIP015C_RETRO_CHECK_DID_NOT_PRESERVE_UNTESTABLE'}
    Write-Host 'TIP015C_RETRO_ENTRYPOINT_VERIFY=PASS init=UNTESTABLE check=UNTESTABLE exit=3'
}
finally{Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue}

function Get-ExactTunnelProcess([string]$Executable){$expected=[IO.Path]::GetFullPath($Executable);@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})}
$h=0;$r=0;try{$h=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.healthUrl -TimeoutSec 3).StatusCode}catch{};try{$r=[int](Invoke-WebRequest -UseBasicParsing -Uri $config.supervisor.readyUrl -TimeoutSec 3).StatusCode}catch{};$t=@(Get-ExactTunnelProcess ([string]$config.tunnel.executable));if($h -ne 200 -or $r -ne 200 -or $t.Count -ne 1){throw "TIP015C_RUNTIME_VERIFY_FAILED health=$h ready=$r tunnels=$($t.Count)"}
Write-Host ("TIP015C_RUNTIME_VERIFY=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
Write-Host 'TIP015C_VERIFY=PASS'
