# TIP-065 — Capacity and pending-COMMIT diagnostics

Contractor continuation, 2026-10-05. The approved Blueprint/continuous work continues. Candidate f2b65c35cb1c31e523d365c75ae4be328df19476 is rejected at 6/8 on attempt 1; no overlay deployment or restart occurred. [Its retained receipt](evidence/tip065/ci-f2b65c3/metadata/verification-receipt.json) binds all five original ZIPs, exact head/tree, unchanged 210-file manifests, JUnit, nine harmless proofs and original failures. The previous two corrected fixtures passed on actual Windows source CI.

## YAGNI-3 before implementation

1. Needed: the remaining capacity assertion has no per-call breakdown, and current owner-grant controls hold a response after COMMIT rather than model the newly observed pending-COMMIT boundary.
2. Reuse: existing real TLS client/server fixture, actual SQLite connection and control-store methods, source failure-preservation helper, finite transport notes and existing after-COMMIT control.
3. Smallest change: two existing test files, bounded capacity-phase observation and one deterministic pending-COMMIT control. No production optimization is justified by current evidence.

## Proven facts and limits

Three control steps perform at least six fresh HTTPS POSTs. Signed requests also have node begin/ACK and server observed-wall/nonce durable transactions; at least 24 logical COMMITs are included. Node begin/ACK work lies outside the HttpsClient request interval. The measurement includes actual host storage, validation and network work. Actual unfinished native futures are not joined by this control path; the harmless native hold is outside its scope transaction.

Bootstrap capacity wall time was 5.375 seconds; integrated Windows was 3.813 seconds against the retained 1.5-second assertion. The integrated cleanup error was preserved with heartbeat TimeoutError at reserve_nonce COMMIT. Bootstrap CLI initial-pair setup owner grant timed out at 1015 ms against its 1000-ms cap with server at issue_grant COMMIT. The exact storage/scheduling cause and historical commit duration remain UNKNOWN. No small equivalent product optimization is established. Observed-wall persistence before a denied operation protects crash/clock rollback; it must not be dropped or coalesced under a success-only transaction.

## Builder scope and acceptance

Only tests/unit/test_tip064_capacity_https.py and tests/unit/test_tip058b_transport.py may change. All product files, the TIP-065 observer test and exact deployment payload remain frozen.

Capacity observes exactly the existing three-step phase, with at most 32 finite POST rows. Each row contains only route class, elapsed time and finite failure type. Safe aggregate notes include observed call count/time, time outside those calls and existing harmless hold/worker facts. Attach notes to the original error and preserve its identity. No additional request, state lookup or replay is introduced. Keep the literal wall-time assertion below 1.5 seconds and every HTTP/control/SQLite/hold/cleanup budget.

The pending-COMMIT control wraps the actual SQLite connection only in the fixture. Preserve FULL durability and WAL; finish observed-wall persistence before gating entry to the real grant COMMIT. The original 1000-ms HTTPS call must fail while actual commit is held. Preserve sanitized stack/cause and original exception. Release in finally, delegate real COMMIT exactly once, prove completion/owner closure, then reopen the same temporary store and verify revision 2, one grant and one operation. No automatic retry, authority reset, generated CLOSED or secret output is allowed. Existing after-COMMIT response-loss and negative deadlines remain required.

Run meaningful local controls and affected integration tests, retain exact command/env/log/JUnit and pre/post hashes, then freeze a Builder Completion Report. Contractor reviews independently before deciding whether the missing diagnostics justify one new source candidate. A diagnostic source gate does not establish a functional repair or historical root cause. Failed original receipts remain immutable. Physical VM/MT5/SDK qualification and full Fleet activation stay OPEN/NOT_RUN; fixture PASS cannot substitute.
