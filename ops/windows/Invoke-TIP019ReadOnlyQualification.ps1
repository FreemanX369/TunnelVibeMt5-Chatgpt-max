[CmdletBinding()]
param(
  [string]$Target='C:\VibeMQL5',
  [string]$ProjectId='TIP014-DEMOEA-E2E-20260830',
  [string]$TerminalAlias='MT5-2',
  [string]$RequestedSymbol='EURUSD'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python=Join-Path $Target '.venv\Scripts\python.exe'
$evidenceRoot=Join-Path $Target 'evidence\tip019'
$scanScript=Join-Path $Target 'ops\windows\Collect-TIP019LiveReadinessScan.ps1'
$reviewScript=Join-Path $Target 'ops\windows\Review-TIP019LiveReadinessScan.ps1'
if(!(Test-Path -LiteralPath $python -PathType Leaf)){throw 'TIP019_QUALIFY_PYTHON_MISSING'}
if(!(Test-Path -LiteralPath $scanScript -PathType Leaf)){throw 'TIP019_QUALIFY_SCAN_SCRIPT_MISSING'}
if(!(Test-Path -LiteralPath $reviewScript -PathType Leaf)){throw 'TIP019_QUALIFY_REVIEW_SCRIPT_MISSING'}
$started=Get-Date
Write-Host '=== TIP019 Q1 FRESH READ-ONLY SCAN ==='
& $scanScript -Target $Target -TerminalAlias $TerminalAlias -RequestedSymbol $RequestedSymbol
if($LASTEXITCODE -ne 0){throw 'TIP019_QUALIFY_SCAN_FAILED'}
$scan=Get-ChildItem -LiteralPath $evidenceRoot -Filter 'TIP019-LIVE-READINESS-SCAN-*.json' -File | Where-Object{$_.LastWriteTime -ge $started.AddSeconds(-2)} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if($null -eq $scan){throw 'TIP019_QUALIFY_SCAN_OUTPUT_NOT_FOUND'}
Write-Host "TIP019_QUALIFY_SCAN=$($scan.FullName)"
Write-Host "TIP019_QUALIFY_SCAN_SHA256=$((Get-FileHash -LiteralPath $scan.FullName -Algorithm SHA256).Hash.ToLowerInvariant())"

Write-Host '=== TIP019 Q2 CAPABILITY MATRIX ==='
& $reviewScript -Target $Target -ScanEvidence $scan.FullName
if($LASTEXITCODE -ne 0){throw 'TIP019_QUALIFY_REVIEW_FAILED'}
$matrix=Get-ChildItem -LiteralPath $evidenceRoot -Filter 'TIP019-CAPABILITY-MATRIX-*.json' -File | Where-Object{$_.LastWriteTime -ge $started.AddSeconds(-2)} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if($null -eq $matrix){throw 'TIP019_QUALIFY_MATRIX_OUTPUT_NOT_FOUND'}
Write-Host "TIP019_QUALIFY_MATRIX=$($matrix.FullName)"
Write-Host "TIP019_QUALIFY_MATRIX_SHA256=$((Get-FileHash -LiteralPath $matrix.FullName -Algorithm SHA256).Hash.ToLowerInvariant())"

Write-Host '=== TIP019 Q3 LIVE-CHECK ==='
$raw=@(& $python -m vibemql5.adapters.cli --root $Target live-check $ProjectId --scan-evidence $scan.FullName --capability-matrix $matrix.FullName 2>&1)
$code=$LASTEXITCODE
$text=($raw|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine
try{$check=$text|ConvertFrom-Json}catch{throw "TIP019_LIVE_CHECK_JSON_INVALID exit=$code output=$text"}
if([string]$check.status -eq 'FAIL' -or $code -eq 2){Write-Host $text;throw 'TIP019_LIVE_CHECK=FAIL'}
if([string]$check.status -eq 'UNTESTABLE'){
  Write-Host $text
  Write-Host 'TIP019_LIVE_CHECK=UNTESTABLE'
  Write-Host ("TIP019_LIVE_CHECK_REASONS={0}" -f ((@($check.reasons)) -join ','))
  Write-Host 'TIP019_LIVE_ATTEST=BLOCKED'
  Write-Host 'TIP019_LIVE_PACKAGE=BLOCKED'
  Write-Host 'release_eligible=true'
  Write-Host 'forward_eligible=true'
  Write-Host 'live_eligible=false'
  Write-Host 'TIP019_NEXT=RESOLVE_EXTERNAL_ACCOUNT_OR_SESSION_GATES_AND_RERUN_FRESH_QUALIFICATION'
  return
}
if([string]$check.status -ne 'PASS' -or $code -ne 0){Write-Host $text;throw "TIP019_LIVE_CHECK_UNEXPECTED status=$($check.status) exit=$code"}
Write-Host "TIP019_LIVE_CHECK=PASS qualification_id=$($check.qualification_id) sha256=$($check.sha256)"

Write-Host '=== TIP019 Q4 LIVE-ATTEST ==='
$attRaw=@(& $python -m vibemql5.adapters.cli --root $Target live-attest $ProjectId ([string]$check.qualification_id) 2>&1)
$attCode=$LASTEXITCODE;$attText=($attRaw|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine
if($attCode -ne 0){Write-Host $attText;throw 'TIP019_LIVE_ATTEST_FAILED'}
$att=$attText|ConvertFrom-Json
Write-Host "TIP019_LIVE_ATTEST=PASS sha256=$($att.sha256)"

Write-Host '=== TIP019 Q5 LIVE CANDIDATE PACKAGE ==='
$pkgRaw=@(& $python -m vibemql5.adapters.cli --root $Target live-package $ProjectId ([string]$check.qualification_id) 2>&1)
$pkgCode=$LASTEXITCODE;$pkgText=($pkgRaw|ForEach-Object{$_.ToString()}) -join [Environment]::NewLine
if($pkgCode -ne 0){Write-Host $pkgText;throw 'TIP019_LIVE_PACKAGE_FAILED'}
$pkg=$pkgText|ConvertFrom-Json
Write-Host "TIP019_LIVE_PACKAGE=PASS package=$($pkg.package.path) sha256=$($pkg.package.sha256)"
Write-Host "TIP019_FINAL_OWNER_PROPOSAL=$($pkg.final_owner_proposal.path) sha256=$($pkg.final_owner_proposal.sha256)"
Write-Host 'TIP019_CANDIDATE_READY=true'
Write-Host 'release_eligible=true'
Write-Host 'forward_eligible=true'
Write-Host 'live_eligible=false'
Write-Host 'TIP019_NEXT=SEPARATE_FINAL_HASH_BOUND_OWNER_APPROVAL_REQUIRED'
