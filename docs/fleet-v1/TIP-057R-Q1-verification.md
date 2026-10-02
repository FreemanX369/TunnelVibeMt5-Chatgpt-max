# TIP-057R-Q1 — Contractor verification

Status: **VERIFY / REFINE IN PROGRESS — fixture only**. [Draft PR #61](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/61) implements the approved [Q1 output contract](TIP-057R-Q1.md). This record preserves failed receipts before refinement. Contractor owns review/documentation/publication; Builder owns proof code, workflow and the [Completion Report](TIP-057R-Q1-completion.md).

## Reviewed scope

Real base main is `70e2112da9fe8eaa6262f2ba896b55bf3e078260`, tree `6b32f1bc2d13627eba9e915f6fa3c0011b3539e5`. First published candidate is `a93e4b9b34830926e6fa3100d54c3c8852e3fe47`, tree `2be3d098f38bcf1320eeced3e7ee264d594c83bb`. Contractor independently compared all **191 remote blob SHAs/modes** with the frozen local candidate before moving the branch and opening the PR: seven existing planning documents changed, seven isolated proof/workflow/document files added, the remaining **177 existing blobs unchanged**. No product source, dependency/packaging file, existing unit test or existing workflow changed. No runtime imports the fixture.

The first tree upload was rejected by Contractor's comparison because three entries did not match. That unpublished tree was repaired and fully rechecked; it was never published as a branch commit or used for CI. The local synthetic Git snapshot is not the remote parent or tested candidate.

## Independent review and portable evidence

Contractor repeated the frozen portable suite: **8 tests PASS, 0 failures, 0 errors, 0 skips**, Python 3.12.14/Linux. Python compile and whitespace checks passed. Portable status is explicitly `PORTABLE_PASS_WINDOWS_UNQUALIFIED`; the milliseconds measured locally are not Windows latency acceptance. Required-Windows invocation on Linux returns exit 1 / `REAL_WINDOWS_REQUIRED_NO_SKIP` rather than a green skipped test.

Read-only cross-review found the earlier create-before-bind, lost ACTIVE intent, unproven descendant wait, background-thread assertion and synthetic merge-head qualification issues substantively resolved. New generation admission checks ACTIVE/CLOSED disposition under the fixture gate; creation attempt is committed before `CreateProcessW`; exact worker identity is bound before resume; stale recovery cannot clear a successor. These are fixture protocol checks, not unchanged production common-acquisition coverage.

The review found a remaining failure-path hygiene defect: Q06 cleanup originally started after subprocess/return/read/open operations, and `tearDown` stopped after its first cleanup exception. Builder was dispatched to fix these alongside the first Windows failure. Such failures would fail the job, not manufacture a green proof.

## Retained first actual Windows receipt

| Item | Receipt |
|---|---|
| Candidate | `a93e4b9b34830926e6fa3100d54c3c8852e3fe47` |
| Dedicated run / job | [36979951811](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36979951811) / `110751975744` |
| Platform | Windows Server 2025, build 10.0.26100; Python 3.12.10 x64 |
| Actual head check | PASS; actual checkout equals expected PR head |
| Proof result | **BLOCKED / compiler invocation failed before any tests** |
| Cause | `cmd.exe` argument quoting passed escaped quotes to the path containing spaces for `vcvars64.bat` |
| Artifact | `11214762919`, 1,235 bytes; ZIP SHA256 `f945ec121b872c99b5e6be76e225cea7c41c96f35b6c1681967bc7754e5f1713` |
| Durable raw receipts | [summary.json](evidence/tip057rq/first-a93e4b9/summary.json), [compiler.log](evidence/tip057rq/first-a93e4b9/compiler.log) |

Contractor downloaded the ZIP, verified its digest and candidate/head fields, and retained its two original files. All four observed source hash differences were reproduced exactly by LF-to-CRLF conversion during Windows checkout; they were not different product or fixture revisions. Builder was dispatched to make checked-out proof bytes deterministic and comparable to the reviewed blobs, fix compiler quoting, enforce the proof-file log cap, and finish owned fixture cleanup on failed cases. No real Windows AC passed in this failed run.

All four baseline workflows passed at the first candidate: TIP-027 `36979951816`, TIP-028 `36979952026`, TIP-034 `36979951789`, TIP-053 `36979951792`. Their success does not replace Q1's failed dedicated proof.

## Retained second actual Windows receipt

The second candidate `783f9a9f7aa2bdbff62a56a1b170d0b5f363d586` has **four baseline workflow successes**, but dedicated [run 36981015785](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36981015785), job `110755305263`, ended **cancelled at the 15-minute job ceiling**. Its retained suite summary is **FAIL: 16 tests, 3 failures, 7 errors, 0 skips**, elapsed 885,344 ms. Subtest errors are included in the error count; it is not a count of ten distinct failed top-level tests. All eight portable cases passed on Windows. Actual C compilation, PR-head comparison and raw source-versus-HEAD blob comparison passed.

Artifact `11215538983` is 5,150 bytes, ZIP SHA256 `c3806c321b0431df8fb92db2bb45cc8ef87b360ca625781b43c25ab3bc487e3e`. Contractor downloaded it, verified the ZIP/candidate/head/source fields, and retained all three original files: [summary.json](evidence/tip057rq/second-783f9a9/summary.json), [proof.log](evidence/tip057rq/second-783f9a9/proof.log), [compiler.log](evidence/tip057rq/second-783f9a9/compiler.log). The proof log's original hash/size is retained and no truncation occurred.

Seven errors come from querying the executable image with `QueryFullProcessImageNameW` after the exact worker exits (`WinError 31`). Those errors affect normal reconciliation and post-termination identity checks; they are observed API lifetime behavior rather than a child restriction conclusion. Several restricted workers report AppContainer/child policy active before work and deny privileged parent opens, but the corresponding ACs remain failed because full lifecycle acceptance did not complete. Unrestricted target/control started markers are unavailable, so no launch-denial causality is qualified. Q06's nominal subprocess timeout falls into an unbounded pipe-reader join after kill; the CI ceiling interrupts it, and cleanup remains explicitly unproven.

Builder is refining same-handle live-image capture with fresh PID/creation checks after exit, bounded crash-harness/stdio ownership and control diagnostics. A newly opened recovery handle must obtain its own live image before caching; an expected ledger must never be copied into a fresh handle to bypass failed OS identity queries. Missing identity remains recovery-required. This is a routine fixture implementation refinement within approved Q1, not a change to product policy or architecture.

## Retained third actual Windows receipt

Candidate `07316a4a66301eb471112528c2c0e31f781f2bc6`, tree `ce2f4455a3d75cfd14e5940de46688da54495ed8`, completed dedicated [run 36998399463](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36998399463), job `110810267413`, with **FAIL: 16 tests, 12 failure records, 0 errors, 0 skips**, elapsed **12,391 ms**. Failure records include Q04 subtests and are not twelve distinct failed test methods. C compilation, exact candidate/head and raw source/blob checks passed; all eight portable cases passed. The four baseline workflows passed: TIP-027 `36998399394`, TIP-028 `36998399395`, TIP-034 `36998399403`, TIP-053 `36998399391`.

Artifact `11221823821` is 5,165 bytes, ZIP SHA256 `a61cec71a148fcceeeb47e92e5021e37674bbd9c7dd3ef92cfc6487eb96e6796`. Its original [summary.json](evidence/tip057rq/third-07316a4/summary.json), [proof.log](evidence/tip057rq/third-07316a4/proof.log) and [compiler.log](evidence/tip057rq/third-07316a4/compiler.log) are retained. The original 29,186-byte proof log was not truncated.

The file-backed crash harness now returns within its bounded wait rather than entering the earlier pipe-reader hang. This receipt does **not** qualify worker lifecycle identity: workers fail before the lifecycle cases can complete. Restricted workers exit `0xc0000142` before the first `entry.json` marker. Both unrestricted controls reach `wmain` and exit `95` when its first writer fails; the current writer discards the exact format/CreateFile/WriteFile error. Neither absence of a child marker nor these startup failures prove launch prevention.

The newly added `CREATE_NO_WINDOW` flag is a causal-isolation candidate, not a proven sole cause; diagnostics and the binary also changed. ACL, path and integrity inheritance remain hypotheses until actual error/token/object evidence is collected. The Microsoft wide printf `%s` convention does not itself demonstrate a formatting defect. A fresh already-dead recovery open still reports uncertainty; expected journal identity is never substituted for OS evidence.

After three failed candidates Contractor selected a focused, receipt-guided debug checkpoint rather than another speculative broad repair. Builder may compare matched console/no-console starts on fresh fixture roots and expose exact writer-stage/native-error/path, positive parent/current-token write observations and actual token/root/executable integrity/ACL evidence. Working positive controls are required before causal denial qualifies. No capability/ACL broadening, product changes or architecture change is authorized by this refinement. The optional debug reference advertised by the installed skill is absent; this checkpoint follows the available core methodology and Contractor judgment, without claiming to have read that reference.

## Retained fourth actual Windows receipt — focused checkpoint

Candidate `6b84209a0af2db23e0f64cf4aa866e1580333555`, tree `c4f3526293121fa2dd22783e738888ff604b9a2d`, has four baseline workflow successes: TIP-027 `37001271816`, TIP-028 `37001271811`, TIP-034 `37001271835`, TIP-053 `37001271815`. Dedicated [run 37001271851](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37001271851), job `110819284042`, is **failure / BLOCKED: WINDOWS_STARTUP_CHECKPOINT_BLOCKED**, elapsed **10,187 ms**. It records **tests_run=0 / full_suite_attempted=false / skips=0**. These are four actual native debug probes, not a green skipped full suite; no lifecycle/prevention AC is qualified by the checkpoint.

Compilation, expected PR-head and source/blob checks passed. Artifact `11223937630` is 4,338 bytes, ZIP SHA256 `5d466151daadecfd54db52ec3608575b08377ce3fb6276ee19ed7ac179f9cbc5`; original [summary.json](evidence/tip057rq/fourth-6b84209/summary.json), [proof.log](evidence/tip057rq/fourth-6b84209/proof.log), [compiler.log](evidence/tip057rq/fourth-6b84209/compiler.log) are retained. Contractor independently verified ZIP/head/source fields and the untruncated 9,066-byte proof log hash `76ac6d010bf29ef87617f642e0026e74c86406dec588b588cc9ac4e9baf8fe94`.

| Fresh-root probe | Actual result |
|---|---|
| Plain unrestricted console writer | PASS: marker/diagnostic match actual PID; writer complete, Win32 error 0, AppContainer 0, integrity RID 12288, child restriction 0. |
| Granted unrestricted console writer | FAIL: exit `5`, positive marker and diagnostic unavailable. Parent writes before/after pass; exact handle exit and all cleanup are proven. No actual child-token/writer-stage record is available yet. |
| Granted restricted console writer | PASS: matching marker/PID, complete write, AppContainer 1, integrity RID 4096, child restriction 1, no inherited handles, exact exit and cleanup proven. |
| Granted restricted no-console writer | Diagnostic failure: exit `0xc0000142`, no writer/marker. Exact exit and cleanup proven. It is observational and cannot qualify denial. |

All four parent before/after writes succeed and actual parent token observations remain high-integrity/AppContainer 0. The granted root/executable read-back SDDL contains `S:AI` without a visible ML ACE; this is a recorded observation, not proof of its cause or of the unrestricted child's token. The matched console/no-console observations narrow the startup failure, while the granted unrestricted control's exact permission/token cause remains unresolved. A working plain writer demonstrates the unchanged C formatter can write the expected path in that control; it does not bypass the failed granted positive control.

Before publication, cross-review found a new evidence-cap defect caused by duplicating startup rows in both checkpoint and records. Builder repaired both fields' overflow handling, retained original bytes/hashes/dispositions, rechecked final size and added a bounded minimal FAIL receipt. A local sensitivity case compacted 1,400,347 bytes to 624 bytes and unrelated oversized metadata to 439 bytes, both FAIL/nonzero; it is not Windows acceptance. Contractor reread the authoritative `tip057rq-v4-cap-frozen-manifest.json`, repeated portable 8/8/static checks and compared all **203 remote blobs** before publication. An earlier candidate tree with the cap defect remained unpublished. Builder's mutable Completion Report was excluded from this code publication.

Next authorized refinement is exact granted-control child-token/writer evidence and the smallest repairable fixture correction. No broad ACL/capability grant or policy relaxation is inferred from exit 5. Keep full lifecycle and production gates open.

## Retained fifth actual Windows receipt — child token and selected label facts

Candidate `d156c5ecfef5c1874b2babe9658810cae429db65`, tree `d76da1dc5303f8bf2d0a5e85f6678088d25a383b`, has four baseline workflow successes: TIP-027 `37003376168`, TIP-028 `37003376291`, TIP-034 `37003376178`, TIP-053 `37003376156`. Dedicated [run 37003376225](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37003376225), job `110825934332`, remains **BLOCKED / WINDOWS_STARTUP_CHECKPOINT_BLOCKED**, elapsed **10,812 ms**, **tests_run=0 / full_suite_attempted=false / skips=0**. Compile, exact head, source/blob and all owned probe cleanup checks passed. No full lifecycle/prevention AC qualified.

Artifact `11225385055` is 5,954 bytes, ZIP SHA256 `e62e5781474e0fd6879343d15830758830e244013f686dd58c1222cd4d4ba0ee`; original [summary.json](evidence/tip057rq/fifth-d156c5e/summary.json), [proof.log](evidence/tip057rq/fifth-d156c5e/proof.log) and [compiler.log](evidence/tip057rq/fifth-d156c5e/compiler.log) are retained. Contractor verified ZIP/head/source fields and untruncated proof log: 14,923 bytes, SHA256 `99011958822f31b447980ca1f48ff363ceca19fa55aad2fa481885ddcfda272c`.

Actual suspended-handle token observation now proves the granted unrestricted worker has AppContainer 0, the same user SID as its parent, elevated=1, but **Low Integrity SID `S-1-16-4096`**. Direct LABEL descriptor parsing shows the root has a low/no-write-up ACE with flags 3, and the executable has an **inherited low/no-write-up ACE with flags 16**. Each selected ACL has one validated ACE and is not truncated. Therefore the earlier `S:AI` string did not establish absence of a mandatory label; the direct native descriptor supplies the actual label evidence.

Plain writer remains PASS with High Integrity RID 12288. Granted restricted console remains PASS with actual AppContainer 1/Low Integrity/child restriction 1. Granted unrestricted writer exits `0xe5110005`, no marker/diagnostic. Its decoder preserves the raw DWORD and reports a **protocol-shaped inferred CREATE_FILE/error5 candidate**, `NOT_AUTHENTICATED_BY_EXIT_ALONE`, collision possible and qualification NONE. A full-width raw error can share this tag; local sensitivity explicitly retains that collision. It is not independent exact stage proof and cannot grant positive-control acceptance. Restricted no-console remains raw `0xc0000142`, not decoded as a writer result.

The [Microsoft MIC reference](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control) explains that executable integrity can lower the new process token. Receipt facts support executable low-label inheritance as a control-contamination hypothesis; Low Integrity alone does not establish the complete AccessDenied cause. Contractor asked Builder for the smallest causal isolation or narrower label applicability that preserves intended fixture-root worker writes, the same DACL/capability/privileged-handle boundary and a genuine unrestricted control. No broad grant is approved by this finding.

Before this iteration, Contractor repeated portable 8/8/compile/whitespace checks, checked the five-file frozen manifest and all **207 remote blobs**. Read-only cross-review cleared bounded selected-label parsing, retained suspended token queries and explicit exit-inference limitations. Builder's live report was again excluded to avoid mixing mutable content with the frozen executable candidate. All five actual Windows receipts remain unsuccessful and are preserved.

### Gates remain open

The proposed identity repair is bounded to an image independently observed while that exact handle's process is live. Q06 deliberately leaves a live worker that a restarted parent can reopen and verify before terminating. A first recovery open of an already-dead worker has no fresh live-image capture; failure to establish identity remains recovery-required. Same-handle in-memory caching does not prove durable late-dead recovery across parent restarts or product-wide liveness. Those ownership/integration cases need separate evidence and, if necessary, a reviewed mechanism.

Actual SDK/MT5 compatibility and broker/uncontained launch paths remain **OPEN**. Breakaway causal denial can be qualified only if its matching unrestricted control works; ambient runner JobObject denial must remain OPEN. The fixture tests shorten a hang budget to 250 ms and report actual total/termination times; no hard 10-second deadline is certified. Simulated altered creation timestamp is identified as such, not forced PID recycling.

Q1 remains PARTIAL until applicable real Windows cases and final-head baseline CI are read and reviewed. Even a fixture PASS does not close production G03 common-acquisition/recovery integration, G04 actual SDK no-start, Q2 physical compatibility, selected-client tool exposure or M1 live-read acceptance. Keep the PR Draft. No VPS/terminal/native/account/chart/credential/AutoTrading operation, merge or deployment is part of this proof task.
