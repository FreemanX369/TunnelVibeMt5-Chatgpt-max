[CmdletBinding()]
param([string]$Target='C:\VibeMQL5',[string]$ProjectId='TIP014-DEMOEA-E2E-20260830')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe';$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json';$state=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml';$release=Join-Path $Target 'evidence\manifest.json'
$env:T18V_TARGET=$Target;$env:T18V_PROJECT=$ProjectId
$verify=@'
import hashlib,json,os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.forward import ForwardQualificationManager
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T18V_TARGET']);p=load_bridge_provenance(root);s=ProjectSessionManager(root).get(os.environ['T18V_PROJECT']);a=RevisionManager(root).source_hash(s['workspace'],s['ea']);choices=set(build_parser()._subparsers._group_actions[0].choices)
assert vibemql5.__version__=='0.2.15' and p.get('bridge_build')=='TIP-018' and len(REQUIRED_TOOLS)==41 and {'forward-check','forward-attest','forward-promote'}<=choices
assert s['revision_id']=='REV-000004' and s['revision_sha256']=='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989';assert a['sha256']=='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c' and int(a['bytes'])==2026;assert s['baseline_job_id']=='BT-20260831-001933-B0484B' and s['last_job_id']=='BT-20260831-001933-B0484B'
proposal=root/'docs/vibecode/TIP018-FORWARD-ACCEPTANCE-PROPOSAL.yaml';assert hashlib.sha256(proposal.read_bytes()).hexdigest()=='b9e1269848d39a6633641784f08adf7405a1677054838ca7ed7b5d0cd6de7764';approval=json.loads((root/'docs/vibecode/OWNER_APPROVAL-TIP018.json').read_text(encoding='utf-8'));assert approval['status']=='APPROVED' and approval['proposal_sha256']=='b9e1269848d39a6633641784f08adf7405a1677054838ca7ed7b5d0cd6de7764' and approval['release_manifest_sha256']=='b1f48ec1bd1f52bc0000dd6effd01b52a1d770a0f501daa965e4d51e083b575e'
mp=root/'evidence/manifest.json';assert hashlib.sha256(mp.read_bytes()).hexdigest()=='b1f48ec1bd1f52bc0000dd6effd01b52a1d770a0f501daa965e4d51e083b575e';m=json.loads(mp.read_text(encoding='utf-8-sig'));assert m['release_eligible'] is True and m['forward_eligible'] is False and m['live_eligible'] is False
print(json.dumps({'TIP018_PYTHON_VERIFY':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'commands':['forward-check','forward-attest','forward-promote'],'revision':s['revision_id'],'source':a,'release_manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest()},sort_keys=True))
'@
$verify|& $python -;if($LASTEXITCODE -ne 0){throw 'TIP018_PYTHON_VERIFY_FAILED'}
$text=Get-Content -LiteralPath $state -Raw -Encoding UTF8;foreach($n in @('active_tip: TIP-018','phase: VERIFY','bridge_target: 0.2.15','bridge_build: TIP-018','release_eligible: true','forward_eligible: false','live_eligible: false')){if($text -notmatch [regex]::Escape($n)){throw "TIP018_PROJECT_STATE_VERIFY_MISSING=$n"}}
Write-Host 'TIP018_PROJECT_STATE_VERIFY=PASS'
Write-Host 'TIP018_OWNER_APPROVAL_VERIFY=PASS'
Write-Host 'TIP018_RELEASE_PRECONDITION_VERIFY=PASS'
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Http([string]$u){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3).StatusCode}catch{return 0}}
$expected=[IO.Path]::GetFullPath([string]$config.tunnel.executable);$t=@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})
$h=Http $config.supervisor.healthUrl;$r=Http $config.supervisor.readyUrl;if($h -ne 200 -or $r -ne 200 -or $t.Count -ne 1){throw "TIP018_RUNTIME_VERIFY_FAILED health=$h ready=$r tunnels=$($t.Count)"}
Write-Host ("TIP018_RUNTIME_VERIFY=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
Write-Host 'TIP018_VERIFY=PASS'
