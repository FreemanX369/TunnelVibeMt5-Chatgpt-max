[CmdletBinding()]
param([string]$Target='C:\VibeMQL5',[string]$ProjectId='TIP014-DEMOEA-E2E-20260830')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe';$configPath=Join-Path $Target 'ops\windows\vibemql5.windows.json';$state=Join-Path $Target 'docs\vibecode\PROJECT_STATE.yaml'
$env:T17_TARGET=$Target;$env:T17_PROJECT=$ProjectId
$verify=@'
import json, os
from pathlib import Path
import vibemql5
from vibemql5.adapters.cli import build_parser
from vibemql5.adapters.mcp_client_check import REQUIRED_TOOLS
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.provenance import load_bridge_provenance
from vibemql5.core.revisions import RevisionManager
root=Path(os.environ['T17_TARGET']); p=load_bridge_provenance(root); s=ProjectSessionManager(root).get(os.environ['T17_PROJECT']); a=RevisionManager(root).source_hash(s['workspace'],s['ea'])
choices=set(build_parser()._subparsers._group_actions[0].choices)
assert vibemql5.__version__=='0.2.14' and p.get('bridge_build')=='TIP-017' and len(REQUIRED_TOOLS)==41 and {'check-all','attest','ship'}<=choices
assert s['revision_id']=='REV-000004' and s['revision_sha256']=='a5a18086034d7ea601e223534306e26a8873a293d399890192c4742816870989'; assert a['sha256']=='a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c' and int(a['bytes'])==2026; assert s['baseline_job_id']=='BT-20260831-001933-B0484B' and s['last_job_id']=='BT-20260831-001933-B0484B'
print(json.dumps({'TIP017_PYTHON_VERIFY':'PASS','version':vibemql5.__version__,'bridge_build':p['bridge_build'],'tools':len(REQUIRED_TOOLS),'commands':['check-all','attest','ship'],'revision':s['revision_id'],'source':a,'baseline_job_id':s['baseline_job_id']},sort_keys=True))
'@
$verify | & $python -;if($LASTEXITCODE -ne 0){throw 'TIP017_PYTHON_VERIFY_FAILED'}
$text=Get-Content -LiteralPath $state -Raw -Encoding UTF8;foreach($n in @('active_tip: TIP-017','phase: VERIFY','bridge_target: 0.2.14','bridge_build: TIP-017','release_eligible: false','forward_eligible: false','live_eligible: false')){if($text -notmatch [regex]::Escape($n)){throw "TIP017_PROJECT_STATE_VERIFY_MISSING=$n"}}
Write-Host 'TIP017_PROJECT_STATE_VERIFY=PASS'

$scratch=Join-Path $env:TEMP ('TIP017-release-scratch-'+[Guid]::NewGuid().ToString('N'));$env:T17_SCRATCH=$scratch
try{
$smoke=@'
import json, os
from pathlib import Path
from vibemql5 import __version__
from vibemql5.core.jobs import JobStore
from vibemql5.core.project_sessions import ProjectSessionManager
from vibemql5.core.release import ReleaseEvidenceManager, file_record, write_normalized_report_xml
from vibemql5.parsers.report import parse_report
root=Path(os.environ['T17_SCRATCH']); ea=root/'workspaces/demo/Experts/DemoEA.mq5'; ea.parent.mkdir(parents=True,exist_ok=True); ea.write_text('// scratch\n',encoding='utf-8'); (root/'workspaces/demo/Sets').mkdir(parents=True,exist_ok=True); (root/'workspaces/demo/Sets/default.set').write_text('x=1\n',encoding='utf-8')
req={'workspace':'demo','ea':'Experts/DemoEA.mq5','terminal':'MT5-2','preset':'smoke','set_file':'Sets/default.set','overrides':{},'mock':False}; store=JobStore(root); b=store.create(req);store.force_terminal(b['job_id'],'PASSED'); ProjectSessionManager(root).create('SCRATCH','demo','Experts/DemoEA.mq5',phase='VERIFY',baseline_job_id=b['job_id'],last_job_id=b['job_id']); j=store.create(req);store.force_terminal(j['job_id'],'PASSED'); rd=root/'runs'/j['job_id']; (rd/'source_snapshot/Experts').mkdir(parents=True,exist_ok=True);(rd/'source_snapshot/Experts/DemoEA.mq5').write_bytes(ea.read_bytes()); ex5=rd/'compiled.ex5';ex5.write_bytes(b'EX5'); er=file_record(ex5); comp={'status':'PASSED','errors':0,'warnings':0,'mock':False,'command':['metaeditor','/compile:x','/log'],'source':'windows_native_metaeditor','immutable_ex5':{'path':str(ex5),'sha256':er['sha256'],'bytes':er['bytes']}};(rd/'compile.json').write_text(json.dumps(comp),encoding='utf-8');(rd/'compile.log').write_text('Result: 0 errors, 0 warnings\n',encoding='utf-8');(rd/'tester.log').write_text('pass\n',encoding='utf-8');native=rd/'report.htm';native.write_text('<table><tr><td>Total Trades:</td><td>1</td></tr><tr><td>Total Net Profit:</td><td>1</td></tr><tr><td>Profit Factor:</td><td>1</td></tr><tr><td>Balance Drawdown Maximal:</td><td>1 (1%)</td></tr></table>',encoding='utf-8');metrics=parse_report(native)['metrics'];write_normalized_report_xml(rd,native,metrics);result={'schema_version':'1.2','job_id':j['job_id'],'status':'PASSED','tool_version':__version__,'host':'scratch','platform':'Windows','recorded_at_utc':'2026-09-02T00:00:00Z','tester':{'execution_status':'PASSED','report_status':'PARSED','execution_context':{'session_id':2},'source':'windows_native_mt5_strategy_tester','command':['terminal64.exe','/config:tester.ini']},'strategy':metrics,'environment':{'terminal':'MT5-2','mock':False},'artifacts':{'native_report':str(native)}};(rd/'result.json').write_text(json.dumps(result),encoding='utf-8');(rd/'environment.json').write_text('{}',encoding='utf-8');m=ReleaseEvidenceManager(root);c=m.check_all('SCRATCH',j['job_id']);a=m.attest('SCRATCH',j['job_id']);s=m.ship('SCRATCH',j['job_id']);assert c['status']==a['status']==s['status']=='PASS';manifest=json.loads((root/'evidence/manifest.json').read_text());assert manifest['release_eligible'] is True and manifest['forward_eligible'] is False and manifest['live_eligible'] is False;print('TIP017_RELEASE_PIPELINE_SCRATCH=PASS')
'@
$smoke | & $python -;if($LASTEXITCODE -ne 0){throw 'TIP017_RELEASE_PIPELINE_SCRATCH_FAILED'}
}finally{Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue}
if(Test-Path -LiteralPath $scratch){throw 'TIP017_SCRATCH_RESET_FAILED'}
Write-Host 'TIP017_SCRATCH_RESET=PASS'

$config=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8|ConvertFrom-Json
function Http([string]$u){try{return [int](Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 3).StatusCode}catch{return 0}}
$expected=[IO.Path]::GetFullPath([string]$config.tunnel.executable);$t=@(Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $expected)})
$h=Http $config.supervisor.healthUrl;$r=Http $config.supervisor.readyUrl;if($h -ne 200 -or $r -ne 200 -or $t.Count -ne 1){throw "TIP017_RUNTIME_VERIFY_FAILED health=$h ready=$r tunnels=$($t.Count)"}
Write-Host ("TIP017_RUNTIME_VERIFY=PASS healthz=200 readyz=200 tunnel_count=1 tunnel_pid={0}" -f $t[0].ProcessId)
Write-Host 'TIP017_VERIFY=PASS'
