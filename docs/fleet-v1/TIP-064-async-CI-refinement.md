# TIP-064 asynchronous Windows CI fixture refinement

STATUS: DONE for bounded source/test refinement; exact canonical full Linux/Windows CI remains pending. Builder: windows_async_refinement, Vibecode Kit v6. No product runtime code was changed by this refinement.

## YAGNI-3

1. The `ebbb56c` Windows logs identify two fixture ordering defects and a full-suite harness deadline below the observed suite duration. These need portable evidence and complete logs before source handover.
2. Reuse `NodeRuntime.stop_status()`, its existing monotonic deadline, the normal outbound agent owner drain, `dispatcher.has_pending_work()`, pytest fault diagnostics and the existing before/after source manifest.
3. Wait for the actual asserted conditions, retain sanitized HTTPS failure context and increase only the proof harness full-unit deadline. No transport retry, product timeout, phase TTL, UNKNOWN recovery or native authority change is needed.

## Findings and resulting behavior

The retained [Deep Update and Bootstrap logs](evidence/tip064/ci-ebbb56c/log-hashes.json) both fail the blocked-native fixture at `stop_status()['deadline_elapsed']` after `time.sleep(.002)`. The test now polls the actual monotonic deadline for at most 0.5 seconds and still requires STOP_PENDING with the native fixture blocked and no cancellation effect.

Deep Update's 1000 ms long-step fixture completed the expired-entry-proof check, received a fresh next-phase grant and reached SUCCEEDED before its final assertion failed on a retained `_native_records` entry. A terminal ACK may be published while the worker future is returning. The refined test forces that ordering on every platform, then waits for both SUCCEEDED and the existing normal owner drain to finish. Cleanup also uses the owner drain. It does not clear records, manufacture closure, reissue an expired proof or resolve UNKNOWN.

The traversal HTTPS failure appears only in Deep Update. Neither retained raw log contains a captured server traceback or underlying transport exception for it, so its cause remains unproven. The shared writer fixture now attaches only the error code, low-level exception type, elapsed milliseconds, configured HTTP timeout, server-thread liveness and server-failure queue count to admission errors. Headers, credentials and payloads are omitted. Its 1000 ms positive timeout remains unchanged; failures are neither retried nor ignored. The next Windows run can distinguish a deadline from a socket/TLS/server failure.

Windows full-unit runs took 420.99 and 455.50 seconds; the integrated source runner stopped its unit child at 300 seconds without JUnit. The runner now allows 600 seconds for the full suite and 120 seconds for each existing required proof. The five Windows case budgets total 1080 seconds within the unchanged 20-minute workflow. Unit logs show verbose test IDs, the 20 slowest cases and a fault dump after 90 seconds in one test. Each case log and summary records its finite budget, elapsed time and whether it timed out. The full suite, portable B1 and Windows Q1/G03-A/B1 cases remain required, and before/after source differences still fail verification.

## Current source hashes

| Source | SHA-256 |
| --- | --- |
| `tests/unit/test_tip064_integration.py` | `42112366299d0ad9bbdd02f1ee4f2804980e12221b514541575f4a4490be39c3` |
| `tests/unit/fleet_writer_fixture.py` | `d299dbd073c47d599af60bacc2b25bdaed2a50fbe366dc3feedc6ac49448c79d` |
| `tests/proofs/fleet_v1/run_source.py` | `507b0eaa92a5ca5ca832461b195ba88a372e3ed34e4306dfb9800632cd3f9748` |
| `tests/unit/test_fleet_source_runner.py` | `f1b00d64f6301430852318d6a83275b667445e2830d4c388576de095e5882a38` |

The canonical JSON map of these four hashes has SHA-256 `fd0e5930a6a0465fe346b447e519d305e6bfdda731c9d28c4e68a154516fdbc6`. Earlier loopback-refinement and frozen receipts retain their original source identity.

## Verification and remaining gate

The final local Linux dependency matrix passed **159 tests with 3 explicit platform skips, zero failures/errors, 25.61 seconds**. It covers the integrated TLS/native/source fixtures, shared writer/worktree/recovery/capacity fixtures, transport positives and negative deadlines, plus six orchestration cases for Linux/Windows success, unit timeout and source drift. The orchestration cases are mocks and do not certify Windows execution.

[Receipt](evidence/tip064/async-ci-refinement-v1/receipt.json), [JUnit](evidence/tip064/async-ci-refinement-v1/focused.junit.xml), [raw log](evidence/tip064/async-ci-refinement-v1/focused.log) and the before/after hash maps bind the frozen owned files and retained unchanged runtime references. This is a focused local worktree diagnostic; full source and actual Windows acceptance require the Contractor's next frozen candidate CI. Private VM, MT5, real SDK, merge and deployment were not run.

SOURCE_FREEZE: the four code/test files above are frozen after the final focused run. Report/hash/evidence updates do not modify their bytes. No deviation from the approved source refinement scope; the unproven traversal transport cause remains an explicitly open diagnostic for Windows CI.
