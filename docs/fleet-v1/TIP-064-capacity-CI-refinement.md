# TIP-064 capacity TLS fixture observation refinement

STATUS: DONE for fixture refinement. Builder: `windows_fixture_final`, Vibecode Kit v6. Exact next-candidate full Linux/Windows CI remains required. No product runtime source changed.

## YAGNI-3

1. Canonical `154e954aa631c63c39db639aa93a529e9807f42c` passes seven workflows, including Deep and Bootstrap. Integrated Windows fails only the capacity TLS fixture's final three-job SUCCEEDED observation. Its three-second observation budget and five-second harmless worker watchdog overlap multiple actual TLS/SQLite observations, but the original failure captures no final states.
2. Reuse the existing events, monotonic clock, owner stepping/drain, public job status and scoped coordinator transaction. Keep strict profile/signature validation, grants, current source hashes and all negative assertions.
3. Give the positive fixture one absolute twenty-second harmless callback watchdog and ten-second aggregate completion/drain observation. Add controlled ordering and bounded state diagnostics; never retry, clear UNKNOWN or resubmit work.

## Diagnosis and controlled reproduction

The original Windows log proves the final pump did not observe all three SUCCEEDED states within three seconds. It does not establish whether a harmless hold expired or successful aggregate completion needed longer. The source path converts a callback assertion failure to durable `UNKNOWN`; normal owner drain publishes that state. Scope uncertainty then blocks a conflicting successor. These are preserved runtime behaviors.

A separate scratch fault probe forces at least one original five-second callback hold to expire before explicit release. Actual Gateway and node states become `UNKNOWN, SUCCEEDED`; the third stays `QUEUED`, calls remain two, and scopes are `UNKNOWN/ARMED, RELEASED/CLOSED`. Normal drain finishes without retained worker futures or node records. Late release does not clear UNKNOWN or admit the third. The expected-fault probe passes **1 test in 8.93 seconds**. Its first version incorrectly expected both workers to expire simultaneously; that failed diagnostic assertion and its source/log/JUnit remain under `first-*`. Worker entry times differ, so the corrected probe requires at least one expiry.

The refined negative probe forces the same hold expiry and sees the new terminal diagnostic after **0.101 seconds**, with reason `EXECUTION_OUTCOME_UNKNOWN`; it passes **1 test in 5.79 seconds**. The twenty-second positive watchdog cannot hide a terminal failure: FAILED, CANCELLED, UNKNOWN or RECOVERY_REQUIRED fail the final predicate immediately. These controlled probes establish reachable ordering and diagnostics; they do not prove which ordering caused the original Windows failure.

The shipped positive fixture now runs both normal ordering and an event-controlled delayed ordering. The second holds release for 5.2 seconds while the control owner keeps stepping, then holds actual callback completion another 3.2 seconds. This crosses both former fixture budgets. One absolute twenty-second callback watchdog spans both waits, so the second barrier cannot renew it. The final ten-second aggregate observation requires all three jobs SUCCEEDED and the existing normal owner drain complete.

The original three control steps under 1.5 seconds, two distinct native admissions, exact ARMED scopes, third QUEUED before release, first two STARTING, exactly three calls, exact synthetic results and absence of a physical install marker remain required. Gateway grant TTL stays 2000 ms; the capacity HTTP policy stays 1000 ms; explicit request deadlines and negative transport budgets are unchanged. Timer/event barriers have finite cleanup and produce no native process effects.

## Evidence and verification

The affected local Linux matrix passed **118 tests, 3 actual Windows-handle skips, zero failures/errors, 20.28 seconds**. It covers capacity normal/delayed ordering, scoped resources, signed rosters, Gateway capacity, integration and the transport deadline negatives. **39** source hashes match before/after; all **88** production Python files match the prior canonical snapshot byte-for-byte. This is a cached-dependency source diagnostic, not exact Windows acceptance or physical qualification.

[Receipt](evidence/tip064/capacity-ci-refinement-v1/receipt.json), [JUnit](evidence/tip064/capacity-ci-refinement-v1/focused.junit.xml), [log](evidence/tip064/capacity-ci-refinement-v1/focused.log), [before](evidence/tip064/capacity-ci-refinement-v1/source-before.json) and [after](evidence/tip064/capacity-ci-refinement-v1/source-after.json) maps bind the focused run. The [original ordering observation](evidence/tip064/capacity-ci-refinement-v1/ordering-probe/observed.json) and [refined terminal observation](evidence/tip064/capacity-ci-refinement-v1/ordering-probe/refined-observed.json) retain sanitized state facts, with exact probe source/log/JUnit and identities alongside them. Probe scripts retain their original scratch paths as execution provenance.

| Frozen source | SHA-256 |
| --- | --- |
| `tests/unit/test_tip064_capacity_https.py` | `5bf28290d7a9e203dfdbd23b6ab03781aebebd7a974ec35c8fe659d4988366da` |

Current M3 owned-source and A shared-fixture pointers now identify these bytes and this receipt. Their preceding manifests are preserved under distinct `before-capacity-ci-refinement` names. Earlier CI and refinement receipts retain their original identities and meanings.

SOURCE_FREEZE: the capacity fixture is frozen after the focused run. No product edit, runtime architecture change, authority TTL change, UNKNOWN clearing, lease reclaim, effect retry, resubmission or qualification marker was introduced. Private VM, MT5, actual SDK qualification, merge and deployment remain deferred under the approved plan.
