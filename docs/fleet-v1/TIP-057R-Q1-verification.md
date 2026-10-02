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

## Qualification boundaries

Actual SDK/MT5 compatibility and broker/uncontained launch paths remain **OPEN**. Breakaway causal denial can be qualified only if its matching unrestricted control works; ambient runner JobObject denial must remain OPEN. The fixture tests shorten a hang budget to 250 ms and report actual total/termination times; no hard 10-second deadline is certified. Simulated altered creation timestamp is identified as such, not forced PID recycling.

Q1 remains PARTIAL until applicable real Windows cases and final-head baseline CI are read and reviewed. Even a fixture PASS does not close production G03 common-acquisition/recovery integration, G04 actual SDK no-start, Q2 physical compatibility, selected-client tool exposure or M1 live-read acceptance. Keep the PR Draft. No VPS/terminal/native/account/chart/credential/AutoTrading operation, merge or deployment is part of this proof task.
