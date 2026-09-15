[CmdletBinding()]
param([string]$Target='C:\VibeMQL5',[string]$ProjectId='TIP014-DEMOEA-E2E-20260830',[int]$TimeoutSeconds=600)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe';$vibe=Join-Path $Target '.venv\Scripts\vibemql5.exe';$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json';$state=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml'
if(!(Test-Path $vibe)){throw "TIP017_VIBEMQL5_CLI_MISSING=$vibe"}
$text=Get-Content $state -Raw -Encoding UTF8;foreach($n in @('active_tip: TIP-017','phase: VERIFY','bridge_target: 0.2.14','bridge_build: TIP-017','release_eligible: false','forward_eligible: false','live_eligible: false')){if($text -notmatch [regex]::Escape($n)){throw "TIP017_RELEASE_STATE_PRECONDITION_MISSING=$n"}}
$env:T17Q_ROOT=$Target;$env:T17Q_PROJECT=$ProjectId;$env:T17Q_TIMEOUT=[string]$TimeoutSeconds
Write-Host '=== Q1 FRESH NATIVE RELEASE JOB ==='
$launch=@'
import json, os, time
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.facade import ToolFacade
from vibemql5.core.jobs import JobStore
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T17Q_ROOT']); project=os.environ['T17Q_PROJECT']; timeout=int(os.environ['T17Q_TIMEOUT']); prov=load_bridge_provenance(root);assert vibemql5.__version__=='0.2.14' and prov.get('bridge_build')=='TIP-017' and len(REQUIRED_TOOLS)==41
ps=ProjectSessionManager(root);s=ps.get(project);r=ps.resume(project);assert s['revision_id']=='REV-000004' and s['revision_sha256']=='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989' and s['source_sha256']=='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c' and int(s['source_bytes'])==2026 and s['baseline_job_id']=='BT-20260831-001933-B0484B' and s['last_job_id']=='BT-20260831-001933-B0484B' and r['resume_safe'] is True
src=RevisionManager(root).source_hash(s['workspace'],s['ea']);assert src['sha256']==s['source_sha256'] and int(src['bytes'])==int(s['source_bytes']);base=JobStore(root).load(s['baseline_job_id']);req=dict(base.get('request') or {});assert not bool(req.get('mock'))
f=ToolFacade(root);h=f.health();assert h['queue_length']==0 and h['active_job'] is None
j=f.launch_test(s['workspace'],s['ea'],req.get('terminal'),req.get('preset','smoke'),req.get('set_file'),req.get('overrides') or {},False,max(30,min(timeout-30,540)));job_id=j['job_id'];deadline=time.time()+timeout
while time.time()<deadline:
    state=f.get_job(job_id).get('state')
    if state in {'PASSED','ANOMALY','FAILED','TIMEOUT','CANCELLED','INTERRUPTED','RESOURCE_LIMIT'}: break
    time.sleep(0.5)
else:
    f.cancel_job(job_id);raise SystemExit('TIP017_RELEASE_JOB_TIMEOUT:'+job_id)
job=f.get_job(job_id);result=f.read_result(job_id);assert job.get('state')=='PASSED' and result.get('status')=='PASSED',(job,result);print(json.dumps({'job_id':job_id,'state':job['state'],'result_status':result['status'],'tool_version':result.get('tool_version'),'host':result.get('host'),'recorded_at_utc':result.get('recorded_at_utc')},sort_keys=True))
'@
$raw=@($launch|& $python - 2>&1);if($LASTEXITCODE -ne 0){throw "TIP017_RELEASE_NATIVE_JOB_FAILED=$($raw -join ' ')"};$jobInfo=(($raw|Select-Object -Last 1).ToString()|ConvertFrom-Json);$jobId=[string]$jobInfo.job_id
Write-Host "TIP017_RELEASE_NATIVE_JOB=PASS job_id=$jobId"

function Run-JsonCli([string[]]$CliArgs){$items=@(& $vibe --root $Target @CliArgs 2>&1);$exit=$LASTEXITCODE;$txt=($items|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine;if($exit -ne 0){throw "TIP017_RELEASE_CLI_FAILED args=$($CliArgs -join ' ') exit=$exit output=$txt"};return ($txt|ConvertFrom-Json)}
Write-Host '=== Q2 CHECK-ALL ===';$check=Run-JsonCli @('check-all',$ProjectId,$jobId);if($check.status -ne 'PASS' -or -not [bool]$check.release_eligible){throw 'TIP017_CHECK_ALL_NOT_PASS'};Write-Host 'TIP017_CHECK_ALL=PASS'
Write-Host '=== Q3 ATTEST ===';$att=Run-JsonCli @('attest',$ProjectId,$jobId);if($att.status -ne 'PASS'){throw 'TIP017_ATTEST_NOT_PASS'};Write-Host 'TIP017_ATTEST=PASS'
Write-Host '=== Q4 SHIP ===';$ship=Run-JsonCli @('ship',$ProjectId,$jobId);if($ship.status -ne 'PASS'){throw 'TIP017_SHIP_NOT_PASS'};Write-Host 'TIP017_SHIP=PASS'

Write-Host '=== Q5 CANONICAL MANIFEST + FIVE BLOCKERS ==='
$manifestPath=Join-Path $Target 'evidence\manifest.json';$m=Get-Content $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
if([string]$m.schema_version -ne '2.0' -or -not [bool]$m.release_eligible -or [bool]$m.forward_eligible -or [bool]$m.live_eligible){throw 'TIP017_CANONICAL_MANIFEST_POLICY_FAILED'}
$run=Join-Path $Target ("runs\$jobId");$ex5=Join-Path $run 'compiled.ex5';$xml=Join-Path $run 'report.xml';if(!(Test-Path $ex5)-or (Get-Item $ex5).Length -le 0){throw 'TIP017_IMMUTABLE_EX5_MISSING'};if(!(Test-Path $xml)-or (Get-Item $xml).Length -le 0){throw 'TIP017_XML_REPORT_MISSING'}
foreach($field in @('tool_version','host','recorded_at_utc')){if(-not $jobInfo.$field){throw "TIP017_RESULT_PROVENANCE_MISSING=$field"}}
Write-Host 'TIP017_FIVE_BLOCKERS_CLOSED=PASS'

$config=Get-Content $configPath -Raw -Encoding UTF8|ConvertFrom-Json;function Http([string]$u){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3).StatusCode}catch{return 0}};$expected=[IO.Path]::GetFullPath([string]$config.tunnel.executable);$t=@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)});if((Http $config.supervisor.healthUrl)-ne 200 -or (Http $config.supervisor.readyUrl)-ne 200 -or $t.Count -ne 1){throw 'TIP017_RUNTIME_POST_QUALIFICATION_FAILED'}

$stamp=Get-Date -Format 'yyyyMMdd-HHmmss';$summaryPath=Join-Path $Target ("evidence\TIP017-RELEASE-QUALIFICATION-$stamp.json");$summary=[ordered]@{schema_version='1.0';tip='TIP-017';status='PASS';job_id=$jobId;check_all_sha256=[string]$check.sha256;attestation_sha256=[string]$att.sha256;ship_sha256=[string]$ship.sha256;release_manifest_sha256=(Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant();release_package=[string]$ship.package.path;release_package_sha256=[string]$ship.package.sha256;release_eligible=$true;forward_eligible=$false;live_eligible=$false};$summary|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $summaryPath -Encoding UTF8;$summarySha=(Get-FileHash $summaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host ''
Write-Host '=============================================='
Write-Host 'TIP017_RELEASE_QUALIFICATION=PASS'
Write-Host "JOB_ID=$jobId"
Write-Host 'IMMUTABLE_RUN_BOUND_EX5=PASS'
Write-Host 'NONEMPTY_HASH_BOUND_XML_REPORT=PASS'
Write-Host 'RELEASE_PROVENANCE=PASS'
Write-Host 'RELEASE_PIPELINE_COMMANDS=PASS check-all,attest,ship'
Write-Host 'CANONICAL_RELEASE_MANIFEST_SCHEMA2=PASS'
Write-Host "RELEASE_MANIFEST=$manifestPath"
Write-Host "RELEASE_MANIFEST_SHA256=$($summary.release_manifest_sha256)"
Write-Host "RELEASE_PACKAGE=$($summary.release_package)"
Write-Host "RELEASE_PACKAGE_SHA256=$($summary.release_package_sha256)"
Write-Host "QUALIFICATION_REPORT=$summaryPath"
Write-Host "QUALIFICATION_SHA256=$summarySha"
Write-Host 'release_eligible=true'
Write-Host 'forward_eligible=false'
Write-Host 'live_eligible=false'
Write-Host '=============================================='
