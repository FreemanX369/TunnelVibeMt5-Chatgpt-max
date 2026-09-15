[CmdletBinding()]
param(
  [string]$Target='C:\VibeMQL5',
  [string]$ProjectId='TIP014-DEMOEA-E2E-20260830',
  [int]$PerJobTimeoutSeconds=600,
  [int]$TotalTimeoutSeconds=3600
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe';$vibe=Join-Path $Target '.venv\Scripts\vibemql5.exe';$state=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml';$release=Join-Path $Target 'evidence\manifest.json';$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json'
if(!(Test-Path -LiteralPath $vibe)){throw "TIP018_VIBEMQL5_CLI_MISSING=$vibe"}
$stateText=Get-Content -LiteralPath $state -Raw -Encoding UTF8;foreach($n in @('active_tip: TIP-018','phase: VERIFY','bridge_target: 0.2.15','bridge_build: TIP-018','release_eligible: true','forward_eligible: false','live_eligible: false')){if($stateText -notmatch [regex]::Escape($n)){throw "TIP018_FORWARD_STATE_PRECONDITION_MISSING=$n"}}
if((Get-FileHash -LiteralPath $release -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'b1f48ec1bd1f52bc0000dd6effd01b52a1d770a0f501daa965e4d51e083b575e'){throw 'TIP018_RELEASE_MANIFEST_PREHASH_MISMATCH'}
$env:T18Q_ROOT=$Target;$env:T18Q_PROJECT=$ProjectId;$env:T18Q_PER_JOB=[string]$PerJobTimeoutSeconds;$env:T18Q_TOTAL=[string]$TotalTimeoutSeconds
Write-Host '=== Q1 FIVE-RUN WINDOWS NATIVE STRESS MATRIX ==='
$launch=@'
import json,os,time
from pathlib import Path
import vibemql5
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.facade import ToolFacade
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T18Q_ROOT']);project=os.environ['T18Q_PROJECT'];per_job=max(120,int(os.environ['T18Q_PER_JOB']));total=max(per_job*5,int(os.environ['T18Q_TOTAL']));p=load_bridge_provenance(root)
assert vibemql5.__version__=='0.2.15' and p.get('bridge_build')=='TIP-018' and len(REQUIRED_TOOLS)==41
s=ProjectSessionManager(root).get(project);r=ProjectSessionManager(root).resume(project);assert s['revision_id']=='REV-000004' and s['revision_sha256']=='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989' and s['source_sha256']=='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c' and int(s['source_bytes'])==2026 and s['baseline_job_id']=='BT-20260831-001933-B0484B' and s['last_job_id']=='BT-20260831-001933-B0484B' and r['resume_safe'] is True
src=RevisionManager(root).source_hash(s['workspace'],s['ea']);assert src['sha256']==s['source_sha256'] and int(src['bytes'])==int(s['source_bytes'])
f=ToolFacade(root);h=f.health();assert h['queue_length']==0 and h['active_job'] is None
matrix=[
 ('FWD-SMOKE-CURRENT','smoke',{}),
 ('FWD-VALIDATION-L100-A','validation',{}),
 ('FWD-VALIDATION-L100-B','validation',{}),
 ('FWD-VALIDATION-L50','validation',{'leverage':50}),
 ('FWD-VALIDATION-L200','validation',{'leverage':200}),
]
jobs={};summaries={};global_deadline=time.time()+total
for role,preset,overrides in matrix:
    if time.time()>=global_deadline: raise SystemExit('TIP018_FORWARD_MATRIX_TOTAL_TIMEOUT')
    j=f.launch_test(s['workspace'],s['ea'],'MT5-2',preset,None,overrides,False,max(90,per_job-30));jid=j['job_id'];jobs[role]=jid;deadline=min(global_deadline,time.time()+per_job)
    while time.time()<deadline:
        state=f.get_job(jid).get('state')
        if state in {'PASSED','ANOMALY','FAILED','TIMEOUT','CANCELLED','INTERRUPTED','RESOURCE_LIMIT'}: break
        time.sleep(0.5)
    else:
        f.cancel_job(jid);raise SystemExit('TIP018_FORWARD_JOB_TIMEOUT:'+role+':'+jid)
    job=f.get_job(jid);result=f.read_result(jid)
    if job.get('state')!='PASSED' or result.get('status')!='PASSED':
        diagnostics=[str(x.get('code') or '') for x in ((result.get('tester') or {}).get('diagnostics') or []) if isinstance(x,dict)]
        raise SystemExit('TIP018_FORWARD_JOB_NOT_PASS:'+role+':'+str(job.get('state'))+':'+','.join(diagnostics))
    summaries[role]={'job_id':jid,'preset':preset,'overrides':overrides,'metrics':result.get('strategy') or {},'resolved_preset':result.get('resolved_preset') or {}}
print(json.dumps({'status':'PASS','jobs':jobs,'summaries':summaries},sort_keys=True))
'@
$raw=@($launch|& $python - 2>&1);$launchExit=$LASTEXITCODE;$launchText=($raw|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine;if($launchExit -ne 0){throw "TIP018_FORWARD_NATIVE_MATRIX_FAILED exit=$launchExit output=$launchText"};$matrixInfo=(($raw|Select-Object -Last 1).ToString()|ConvertFrom-Json)
if([string]$matrixInfo.status -ne 'PASS'){throw 'TIP018_FORWARD_NATIVE_MATRIX_NOT_PASS'}
Write-Host 'TIP018_FORWARD_NATIVE_MATRIX=PASS runs=5'
$matrixInfo.jobs.PSObject.Properties|ForEach-Object{Write-Host ("{0}={1}" -f $_.Name,$_.Value)}

$stamp=Get-Date -Format 'yyyyMMdd-HHmmss';$jobsFile=Join-Path $Target ("evidence\TIP018-FORWARD-JOBS-$stamp.json");[ordered]@{schema_version='1.0';project_id=$ProjectId;jobs=$matrixInfo.jobs;summaries=$matrixInfo.summaries}|ConvertTo-Json -Depth 30|Set-Content -LiteralPath $jobsFile -Encoding UTF8
function Run-JsonCli([string[]]$CliArgs){$items=@(& $vibe --root $Target @CliArgs 2>&1);$exit=$LASTEXITCODE;$txt=($items|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine;if($exit -ne 0){throw "TIP018_FORWARD_CLI_FAILED args=$($CliArgs -join ' ') exit=$exit output=$txt"};return ($txt|ConvertFrom-Json)}
Write-Host '=== Q2 FORWARD-CHECK ===';$check=Run-JsonCli @('forward-check',$ProjectId,'--jobs-file',$jobsFile);if($check.status -ne 'PASS' -or -not [bool]$check.forward_eligible){throw 'TIP018_FORWARD_CHECK_NOT_PASS'};$qid=[string]$check.qualification_id;Write-Host "TIP018_FORWARD_CHECK=PASS qualification_id=$qid"
Write-Host '=== Q3 FORWARD-ATTEST ===';$att=Run-JsonCli @('forward-attest',$ProjectId,$qid);if($att.status -ne 'PASS'){throw 'TIP018_FORWARD_ATTEST_NOT_PASS'};Write-Host 'TIP018_FORWARD_ATTEST=PASS'
Write-Host '=== Q4 FORWARD-PROMOTE ===';$promote=Run-JsonCli @('forward-promote',$ProjectId,$qid);if($promote.status -ne 'PASS' -or -not [bool]$promote.forward_eligible){throw 'TIP018_FORWARD_PROMOTE_NOT_PASS'};Write-Host 'TIP018_FORWARD_PROMOTE=PASS'
Write-Host '=== Q5 CANONICAL FORWARD MANIFEST ==='
$m=Get-Content -LiteralPath $release -Raw -Encoding UTF8|ConvertFrom-Json;if([string]$m.schema_version -ne '2.0' -or -not [bool]$m.release_eligible -or -not [bool]$m.forward_eligible -or [bool]$m.live_eligible){throw 'TIP018_CANONICAL_FORWARD_MANIFEST_POLICY_FAILED'}
if([string]$m.forward_qualification.qualification_id -ne $qid){throw 'TIP018_CANONICAL_FORWARD_QUALIFICATION_ID_MISMATCH'}
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json;function Http([string]$u){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3).StatusCode}catch{return 0}};$expected=[IO.Path]::GetFullPath([string]$config.tunnel.executable);$t=@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)});if((Http $config.supervisor.healthUrl)-ne 200 -or (Http $config.supervisor.readyUrl)-ne 200 -or $t.Count -ne 1){throw 'TIP018_RUNTIME_POST_QUALIFICATION_FAILED'}
$summaryPath=Join-Path $Target ("evidence\TIP018-FORWARD-QUALIFICATION-$stamp.json");$summary=[ordered]@{schema_version='1.0';tip='TIP-018';status='PASS';qualification_id=$qid;jobs=$matrixInfo.jobs;forward_check_sha256=[string]$check.sha256;attestation_sha256=[string]$att.sha256;promote_sha256=[string]$promote.sha256;forward_package=[string]$promote.package.path;forward_package_sha256=[string]$promote.package.sha256;canonical_manifest_sha256=[string]$promote.canonical_manifest.sha256;release_eligible=$true;forward_eligible=$true;live_eligible=$false};$summary|ConvertTo-Json -Depth 30|Set-Content -LiteralPath $summaryPath -Encoding UTF8;$summarySha=(Get-FileHash -LiteralPath $summaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host ''
Write-Host '=============================================='
Write-Host 'TIP018_FORWARD_QUALIFICATION=PASS'
Write-Host "QUALIFICATION_ID=$qid"
Write-Host 'STRESS_MATRIX=5/5_PASS'
Write-Host 'DETERMINISTIC_REPEAT=PASS'
Write-Host 'OWNER_APPROVAL_BINDING=PASS'
Write-Host 'HASH_BOUND_FORWARD_EVIDENCE=PASS'
Write-Host "FORWARD_PACKAGE=$($promote.package.path)"
Write-Host "FORWARD_PACKAGE_SHA256=$($promote.package.sha256)"
Write-Host "CANONICAL_MANIFEST_SHA256=$($promote.canonical_manifest.sha256)"
Write-Host "QUALIFICATION_REPORT=$summaryPath"
Write-Host "QUALIFICATION_SHA256=$summarySha"
Write-Host 'release_eligible=true'
Write-Host 'forward_eligible=true'
Write-Host 'live_eligible=false'
Write-Host 'PROJECT_STATE_FORWARD_FLAG=false_PENDING_FINAL_CLOSE'
Write-Host '=============================================='
