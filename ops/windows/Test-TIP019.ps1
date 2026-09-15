[CmdletBinding()]
param([string]$Target='C:\VibeMQL5',[string]$ProjectId='TIP014-DEMOEA-E2E-20260830')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe';$state=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml';$release=Join-Path $Target 'evidence\manifest.json';$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json'
function Sha([string]$p){return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
$env:T19V_TARGET=$Target;$env:T19V_PROJECT=$ProjectId
$code=@'
import hashlib,json,os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.live_readiness import LiveReadinessManager
from vibemql5.core.provenance import load_bridge_provenance
root=Path(os.environ['T19V_TARGET']);p=load_bridge_provenance(root);choices=set(build_parser()._subparsers._group_actions[0].choices)
assert vibemql5.__version__=='0.2.16' and p.get('bridge_build')=='TIP-019' and len(REQUIRED_TOOLS)==41
assert {'live-check','live-attest','live-package','forward-check','forward-attest','forward-promote'} <= choices
m_path=root/'evidence/manifest.json';m=json.loads(m_path.read_text(encoding='utf-8-sig'));assert hashlib.sha256(m_path.read_bytes()).hexdigest()=='0590e1ec98d9c2e610febc30f6d09dcb9a4eef40fab8b10a28a65f2eea77ef76';assert m.get('release_eligible') is True and m.get('forward_eligible') is True and m.get('live_eligible') is False
LiveReadinessManager(root)._authority(os.environ['T19V_PROJECT'])
print(json.dumps({'TIP019_PYTHON_VERIFY':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'commands':['live-check','live-attest','live-package']},sort_keys=True))
'@
$code|& $python -
if($LASTEXITCODE -ne 0){throw 'TIP019_PYTHON_VERIFY_FAILED'}
$text=Get-Content -LiteralPath $state -Raw -Encoding UTF8;foreach($n in @('active_tip: TIP-019','phase: VERIFY','bridge_target: 0.2.16','bridge_build: TIP-019','release_eligible: true','forward_eligible: true','live_eligible: false')){if($text -notmatch [regex]::Escape($n)){throw "TIP019_STATE_VERIFY_MISSING=$n"}}
Write-Host 'TIP019_PROJECT_STATE_VERIFY=PASS'
if((Sha (Join-Path $Target 'docs\vibecode\OWNER_APPROVAL-TIP019-BUILD.json')) -ne 'd192aec9b6ec744eaf4309897d19927537f11fe06dde35cef66f25bf88102cc1'){throw 'TIP019_OWNER_APPROVAL_HASH_MISMATCH'}
Write-Host 'TIP019_OWNER_APPROVAL_VERIFY=PASS'
$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Http([string]$u){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3).StatusCode}catch{return 0}}
$expected=[IO.Path]::GetFullPath([string]$config.tunnel.executable);$t=@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})
$h=Http ([string]$config.supervisor.healthUrl);$r=Http ([string]$config.supervisor.readyUrl);if($h -ne 200 -or $r -ne 200 -or $t.Count -ne 1){throw "TIP019_RUNTIME_VERIFY_FAILED health=$h ready=$r tunnels=$($t.Count)"}
Write-Host "TIP019_RUNTIME_VERIFY=PASS health=200 ready=200 tunnel_count=1 tunnel_pid=$($t[0].ProcessId)"
Write-Host 'TIP019_VERIFY=PASS'
Write-Host 'release_eligible=true'
Write-Host 'forward_eligible=true'
Write-Host 'live_eligible=false'
