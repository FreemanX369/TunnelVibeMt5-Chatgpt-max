# TIP-073 read-only restore and budget diagnosis

Parent: `ab8ce9891ae8fbb871d5de231a33d05dbb585f90`. Production, tests, workflows and policies were not changed. The four relevant inspected files equal both Git HEAD bytes and the official Windows source manifest. Local source snapshots before and after bounded verification are equal.

## What the Windows artifact proves

The exact completed error is `tests/unit/test_tip060c_restore.py::test_uncertain_or_changed_witness_cannot_clear_recovery[challenge]`, ordinal 960. Pytest prints **ERROR**, while the existing progress plugin reduces failures in setup, call or teardown to outcome FAILED. This therefore does not establish a failed challenge assertion. Its duration is 4875 ms, ending at suite elapsed 171406 ms. The other five parameters pass. No traceback or phase survives because the whole suite is killed before its final pytest summary and JUnit write.

The suite makes progress until ordinal 1204 finishes at 597250 ms, then starts ordinal 1205. The outer unchanged budget terminates it at 600.047 s. A deadlock is not established. Completed outcomes are 1193 PASSED, 10 SKIPPED and one FAILED; 228 cases have not completed. There is no complete Windows JUnit result.

The original FIFO control passed (separate Contractor observation); that is not proof of the underlying original Windows OS denial cause. The restore error is separate from FIFO and the earlier capacity timeout.

## Owned local verification

Using the existing Python test virtual environment, the exact unmodified restore module completes **20 PASS, zero skip** in pytest 0.70 s, wall 0.968 s, under a 30 s bound. An initial invocation using the default artifact runtime failed immediately because pytest was absent; its log and receipt are preserved separately, not counted as test execution or a source failure.

An additional actual owned fixture probe constructs the original control/jobs/node/coordinator resources, signs the original proof, and changes only the challenge. The real implementation rejects it with `RestoreError: RESTORE_TRANSPORT_UNRESOLVED`. Coordinator bytes remain unchanged, ready remains false, control remains RECONCILIATION_REQUIRED, and witness/nonce counts remain zero. Cleanup completes. No production mocking or file edits are used. This is local Linux evidence, not Windows or live VPS qualification.

Source reading confirms `accept_witness` checks challenge before publishing witness intent or inserting any nonce. A restore-source fix is not justified by the available Windows ERROR alone. Journal/restore fixtures do use 25 ms lease/disk policies; whether one of those fails during setup, or a teardown operation fails, is UNKNOWN without the actual exception.

## Timing comparison

All counts below come from original progress logs and include fixture setup/call/teardown. They are not CPU profiles or OS attribution.

| Original artifact | Finished | Sum of completed per-case time | Median | p95 |
|---|---:|---:|---:|---:|
| TIP-072 Windows | 1204 | 591.396 s | 77 ms | 2531 ms |
| TIP-071 Windows | 1401 | 460.031 s | 77 ms | 1484 ms |
| TIP-072 Linux | 1432 | 156.181 s | 9 ms | 497 ms |
| TIP-071 Linux | 1401 | 118.770 s | 6 ms | 350 ms |

The **same first 1204 case identities** sum to 591.396 s in current Windows versus 363.026 s in prior Windows, an increase of 228.370 s. New TIP-072 controls have not been reached at the current timeout; their added count does not explain this already-consumed time. Changing native-owner logic might affect some existing paths, but the timing differences alone do not prove that causality. Current Linux also takes longer than prior Linux. Runner scheduling, disk/antivirus and specific file-operation ownership remain unmeasured.

The largest current module totals are worktrees 158.499 s, capacity HTTPS 103.198 s, legacy principal/native preparation 46.678 s, composed integration 45.439 s and restore 43.133 s. These identify investigation priorities, not permission to remove checks. From ordinals 1101 through 1204, 104 cases consume 294.512 s versus 167.653 s previously.

Examples of exact existing controls: symlink worktree rejection is 15.390 s versus 2.750 s previously; restore replay is 9.125 s versus 0.358 s; restore reapproval challenge is 8.922 s versus 0.389 s; actual TLS two-slot normal is 12.093 s versus 5.000 s. The existing 600 s suite budget, all case assertions, policies, TTL and 90 s faulthandler setting remain unchanged.

## Proposed next bounded step / YAGNI-3

1. **Need now:** retain an immediate bounded pytest error record with stage and traceback so the next new candidate cannot lose the first failure when a later budget expires. A challenge bypass or policy increase is not justified.
2. **Reuse:** existing `pytest_runtest_logreport` progress hook, finite literal identifiers, original artifact log and existing outer budget. Preserve the prior raw artifact and complete case set. Record first failing phase without fixture locals, credential values or parameter payloads.
3. **Shortest approach:** after Contractor contract, add narrowly bounded phase/error evidence and diagnostic controls. Isolate the identified module paths on owned fixtures and profile actual operations before changing production. New commit evidence is required; do not re-run the failed workflow, widen budgets, skip cases, delete assertions, weaken authority, or copy full-source files into the mixed live runtime.

No VPS operation, MT5 request, physical Fleet or private VM qualification occurred. Actual Windows restore exception, timing OS attribution and current live MCP root cause remain UNKNOWN. All raw receipts, excerpts, timing mapping, source hashes and owned probe are included in the accompanying manifest.
