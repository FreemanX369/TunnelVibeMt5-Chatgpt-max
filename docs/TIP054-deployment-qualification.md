# TIP-054 — Deep-audit deployment qualification

## Verdict

**DEPLOYED HEAD VERIFIED / ALL RUNTIME QUALIFICATION PASSED / MERGE GATED BY RELEASE CI**

The nine implementation and test files from PR #52 match the reviewed code head exactly. Both final Windows suites passed 513 cases, including 20 new PowerShell regressions; runtime-forensics, binary-ingress and sampled public checks passed. The fresh 60-minute soak **PASSED with verified run binding, 120 samples, zero bad episodes, and zero tunnel-PID or generation changes**. Its script ran from **2026-09-30T05:15:44.4108878Z** to **2026-09-30T06:16:12.9390278Z**, an elapsed **60 minutes 28.529 seconds**; the finish was **13:16:12.939 Asia/Ho_Chi_Minh**. Current-runtime certification is true. Final post-soak checks found A/B/C ready and the deployed hashes unchanged. Merge follows successful CI on the exact final documentation commit; the linked PR is the authoritative merge record.

## Reviewed authority

- Repository: [TunnelVibeMt5-Chatgpt-max](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max).
- Candidate: [PR #52](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/52).
- Reviewed deployed code head: `e9e7cd296a0ee2e87cdc80dec87210974c226f78`.
- Original audited base: `6db0baf7f268e2c1c7bcdf628b19472cbf2f87f7`.
- Original six-file candidate: `903c2e4622cd4e01d9fbfaf2471b7f4853a9ee05`, superseded by the corrective head above.
- Original rollback checkpoint: `BADMCP-20260930-075242-996034B0`, covering five existing files.
- Corrective rollback checkpoint: `BADMCP-20260930-081217-EE9D8E2D`, covering the deployed soak script and original shared helper and watchdog.
- Deployment used serialized writes with exact expected hashes. Two new regression files are tracked separately for rollback.

`TIP-054` identifies this audit record. Runtime metadata remains **TIP-053 / 0.2.42**, with **85 catalog tools**: 84 model-visible and one app-only. Commit and exact file hashes establish deployment identity. No architecture change, version expansion, threshold relaxation or speculative capture-timeout adjustment was made.

## Seven corrected defects

| Defect | Corrected behavior |
|---|---|
| Source mutation accepted fabricated or unrelated checkpoints | Validate snapshot integrity, workspace, canonical path and source hash under the existing mutation lease. |
| Concurrent source creation bypassed existing-source CAS checks | Recheck existence and required guards after acquiring the lease. |
| Worker or soak launch exceptions stranded STARTING receipts | Persist terminal FAILED receipts while preserving operation-id replay. |
| Fractional tick cursors returned earlier ticks | Filter against the exact microsecond lower bound, retain duplicate ticks, and report filtered rows and honest underfill. |
| Durable soak polling accepted old or unrelated certification state | Bind the expected build, run ID and start time; recovered legacy runs bind their exact start time. |
| Transient Windows sharing violations made state appear missing | Retry only sharing/lock errors 32/33, at most three reads, with 10 ms and 20 ms waits. Missing, malformed and permanently inaccessible state still fails closed. |
| Local-time arithmetic accepted stale heartbeats and distorted watchdog limits | Parse explicit offsets as UTC DateTimeOffset values. Freshness requires nonnegative age below the unchanged limit; future restart records remain in the hourly budget and block cooldown. |

## Exact deployed file identity

All nine hashes matched the reviewed head before the soak at approximately 05:15 UTC and were reverified unchanged during final acceptance at approximately **10:55 UTC on 2026-09-30**.

| Repository path | SHA-256 |
|---|---|
| `app/vibemql5/core/facade.py` | `96aeb1392bf91c61364ac7a5631cbbb201214293f28eafc59df19f9b4cb2caa2` |
| `app/vibemql5/backend_admin/core.py` | `4f5b4b9b5002279d6daa1f8ad49e3d3701be719197e648fda87864bf50348573` |
| `app/vibemql5/core/live_terminal.py` | `786c854307b2f4f7922db80baf32a26d9c314eb364a370a8cf945fc9c13a0417` |
| `ops/windows/Invoke-TIP013Soak.ps1` | `749a5031448add18aac8c7db3899172b39cacd46e8f9b6f2f69f7d2a57b60c86` |
| `ops/windows/VibeMQL5.AtomicFile.ps1` | `655b9a458f2fd0829493f8402618301a9629dd780027324bc562724afb0adb2f` |
| `ops/windows/Invoke-VibeMQL5Watchdog.ps1` | `379bb92e43c4cd196caed51de3e8f02e4c2e390e6b0bdfd301897310ec3d709b` |
| `tests/unit/test_tip050_market_data.py` | `909d6161fd4aec6558f47d7ed902ee1655cf38e7dbb1916c0ac1ff69d4ba5e79` |
| `tests/unit/test_tip054_deep_audit_guards.py` | `998cec0577aa6221c3d190ec838081eefe4c1b8e0f8e943dafe41e70bfae0e26` |
| `tests/unit/test_tip054_windows_health_guards.py` | `ba44a9dd022b4f6015cb663919ad28a37494570e784eccf91fb1cec8af64b220` |

File hashes establish disk contents. Separate restart receipts and post-restart checks established Python process reloads for A/B/C; C's detached restart completed at 00:58:55 UTC. The three PowerShell scripts load on invocation, passed parsing, and reported the new watchdog producer hash. At the fresh-soak start, A/B/C health and readiness were 200, tunnel identities were unchanged, and watchdog observations were HEALTHY/NONE. No MT5 action was required for this continuation.

## Qualification gates

| Gate | Evidence | Status |
|---|---|---|
| Exact nine-file identity | All hashes match reviewed code head; final reverification at approximately 10:55 UTC | PASS |
| Reviewed-code and handoff CI | All four relevant workflows green on code `e9e7cd296a0ee2e87cdc80dec87210974c226f78` and documentation handoff `a99f8164006467bf1380c6fbc132046e1fc6a59d` | PASS |
| Local non-Windows regression | 278 passed, 23 skipped; 20 added PowerShell cases subsequently exercised on Windows | PASS — platform-limited |
| Python compilation | Durable run `BTEST-25A828BC6487426BD317` | PASS |
| Corrected PowerShell syntax | All three corrected scripts parsed; RunId contract present | PASS |
| Process reloads and watchdog | A/B/C ready; new producer hash, HEALTHY/NONE, health/readiness 200 | PASS |
| Final Windows unit suite | `BTEST-647F930C96B630FAAE81`: 513 passed, 153.95 s; finished 01:22:27.643 UTC | PASS |
| Final baseline-aware suite | `BTEST-4DC18C92A77DA4188A4C`: 513 passed, 147.88 s; ALL_GREEN, zero current/baseline/new failures; finished 01:27:59.832 UTC | PASS |
| Final runtime-forensics suite | `BTEST-0E84CBAF17E01159DC54`: 7 passed, 514 deselected, 0.99 s; finished 01:28:14.110 UTC | PASS |
| Final binary-ingress suite | `BTEST-F57AA08654D38328EAEA`: 31 passed, 490 deselected, 11.06 s; finished 01:28:51.217 UTC | PASS |
| Public exact tick cursor | Fractional lower bound returned 4,999 rows, filtered one earlier tick, with zero rows before the bound | PASS |
| Public source checkpoint guard | Fabricated checkpoint rejected with INVALID_ARGUMENT; original source hash unchanged | PASS |
| Public chart/export | 960×540 PNG with matching exported bytes/hash; forming-bar OHLC matched feed at the sampled instant; four chart layouts restored | PASS — sampled |
| Original candidate soak | `BTEST-34D20F952EF4BDC2F4B3`: verified binding, failed at sample 6 with heartbeat freshness false | FAIL — retained |
| Final 60-minute soak | `BTEST-27F5963BDC539470FDA0`; run `SOAK-20260930-121543-DC5BEA99`; PASSED / VERIFIED_RUN_BINDING; 120 samples, zero bad episodes or PID/generation changes; final HTTP 200/200 and heartbeat fresh; current-runtime certification true | PASS |
| Post-soak operational acceptance | Supervisor READY; watchdog HEALTHY/NONE; fresh heartbeat age approximately 9 seconds at 10:57:26 UTC; all A/B/C one process and HTTP 200/200; queue empty and no active job/native/mutation lock | PASS |
| Final release-head CI and merge | Require all four workflows successful on the exact final documentation head; then merge with an expected-head guard. The linked PR records completion. | GATED |

The final soak's operation is `TIP054-C-FINAL-SOAK-20260930-02`. Its durable receipt started at 05:15:43.712 UTC and binds the script start **2026-09-30T05:15:44.4108878Z**, run ID `SOAK-20260930-121543-DC5BEA99`, and build TIP-053. The script finished at **2026-09-30T06:16:12.9390278Z** with 120 samples and unchanged observed tunnel PID/generation. Durable state is **PASSED**, binding is **VERIFIED_RUN_BINDING**, and both the run snapshot and fresh shared resilience state certify this runtime. Durable lookup finalization is a separate timestamp from script completion; elapsed qualification uses the script's own start and finish. Final acceptance re-read all four short-suite receipts and the two preserved failed/superseded runs. The 45-second heartbeat limit, restart limits and zero-bad certification policy remain unchanged.

Final documentation updates do not alter the qualified implementation or test files. CI must succeed on that exact documentation head before the guarded merge. Post-merge PR and main-branch records establish the merge commit without another source change.

## Preserved failure and timeout evidence

The original candidate soak started at 01:01:48.4788345 UTC and recorded failure at **01:04:20.3556789 UTC**. Binding remained verified, HTTP health/readiness were both 200, and no tunnel-PID or generation change was observed, but `heartbeat_fresh=false`. Later readiness does not erase that failure. Its receipt does not identify the exact read or heartbeat condition that caused sample 6.

Subsequent probes reproduced a sharing violation on one of 77 state reads and demonstrated incorrect timezone arithmetic: the old expression gave an age approximately minus seven hours while DateTimeOffset gave approximately two seconds. These concrete defects motivated the correction and 20 deterministic PowerShell cases; both final 513-case Windows suites passed those cases without host-clock changes or scheduled-task mutations.

A separate direct fixture probe reached its 20-second tool timeout after 16 progress marks without a reported test failure. Its TIMEOUT receipt remains an incomplete probe; the completed durable unit suite provides the successful test outcome. Earlier superseded certification `BTEST-1BCA08FAFA008C282E49` remains FAILED with `SUPERSEDED_BY_PR52_DEPLOYMENT`.

Instance B retained three recovered external network-poll timeout episodes, most recently recovered at **12:03:43 local time**. Current readiness and the successful runtime soak do not establish zero external network timeouts across all clients.

## Coverage and client boundaries

All **85 registrations** matched the catalog and exposed schemas. Conservative static audit evidence mapped 13 adapter references, 21 direct core-method test calls and 16 component supports; 35 tools lacked sufficiently specific static support. This is not a claim that every tool or mutation branch was directly exercised. The deployed VPS has additional legacy tests beyond the tracked repository snapshot, so local and VPS totals differ.

Public Python tick/source/chart proofs remain applicable because those files did not change during the PowerShell refinement. Sampled image acceptance establishes that capture only; runtime viewer metadata remains `UNVERIFIED_REQUIRES_IMAGE_ACCEPTANCE`. It does not establish ongoing freshness or another ChatGPT client's tool visibility. Business A/B require their own client-local tool and viewer checks. The tick demo is a live sample replay, not an ongoing feed or order signal.

## Rollback and completion

1. Restore the three corrective existing files from their checkpoint using exact current hashes as CAS preconditions. For full rollback, then restore the five original existing files from the earlier checkpoint.
2. Remove either newly created regression file only if its hash still equals the reviewed candidate hash; verify its absence afterward.
3. Reload the affected Python processes if rolling back Python changes, and repeat readiness, exact hashes and durable qualification checks. PowerShell changes load on their next invocation.
4. Preserve failure and supersession history. An old or unrelated PASS must never certify this run.

No rollback has been required. Runtime qualification is complete. Release CI and merge completion must be read from the exact final head and the linked PR; this document does not predeclare a merge.
