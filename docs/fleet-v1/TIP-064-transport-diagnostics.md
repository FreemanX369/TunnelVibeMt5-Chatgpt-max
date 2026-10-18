# TIP-064 — Bounded transport fixture diagnostics

Status: **DIAGNOSTIC REFINEMENT; ORIGINAL INCIDENT CAUSE OPEN**. This continuation starts from Draft #65 head `8019a52b136d0aae71c1a0235e224557d0e9a1a9`, tree `55985ff5f11af083a1c00780f0196eea50c25cfb`. The original Deep Update run `37114953892`, job `111179854980`, failed the first owner grant during enrollment in `test_read_admission_completed_and_revoked_are_rechecked`: 1125 passed, one failed, ten skipped. The [original receipt/logs/ZIPs](evidence/tip064/ci-8019a52/receipt.json) remain retained.

## YAGNI-3 and scope

1. A transport wrapper suppressed the original exception, leaving no evidence to distinguish connect, TLS, HTTP parsing, response delay or listener failure. A safe diagnostic fixture is needed before any product correction can be justified.
2. Reuse `WireError.__context__`, `Exception.add_note`, the monotonic clock and existing service thread/failure queue. Reuse genuine temporary-CA HTTPS and the current durable control revision for fault controls.
3. Add a fixture-only `HttpsClient` subclass and five bounded controls in the existing transport test module. Production source, policy budgets, TLS verification, authority and retry behavior remain byte-identical to the starting head.

## Findings and limits

The original failure occurs before read-admission assertions. The listener reports ready only after controller initialization and listening; the numeric IPv4 origin already matches its verified IP SAN. The old log contains neither the suppressed exception nor timing, so it does **not** establish a readiness race, socket timeout or TLS failure. The original incident is `ORIGINAL_CAUSE_UNKNOWN`, not a fixed product defect.

Controlled pre-connect `TimeoutError`, `SSLCertVerificationError` and `BadStatusLine` each produce the same public `HTTPS_UNAVAILABLE`. Each records its distinct cause, exactly one connect attempt and no mutation: the next independent operation succeeds at revision 2. The fixture preserves `OWNER_UNAUTHORIZED` and never includes exception text, tokens, public-key values, full paths, headers or request bodies in its note.

A genuine HTTPS control withholds the response after grant revision 2 commits. The unchanged 1000 ms budget expires with `TimeoutError` while the server is alive. No automatic replay occurs; an independent operation still carrying expected revision 1 is rejected with `CONTROL_REVISION_CONFLICT`. Thus `HTTPS_UNAVAILABLE` is not evidence that an effect was absent. The bounded response hold is released in `finally`; normal fixture teardown proves the service owner closes.

The diagnostic note reports the finite error code, cause type, elapsed milliseconds, unchanged HTTP budget, server-thread state, failure count and at most eight source basename/function/line frames. It excludes traceback locals and exception messages. These are diagnostic observations, not authority or closure evidence.

## Verification and delivery rule

Builder and independent Contractor focused logs/JUnit and frozen source receipts are retained under [transport diagnostics evidence](evidence/tip064/transport-diagnostics-v1/). All production Python files remain unchanged. The original failure is retained; no workflow rerun is used to reinterpret it as fixed.

This new diagnostic candidate must receive its own eight successful workflows, matching integrated Linux/Windows head/tree, complete source manifests, JUnit and harmless proofs. Those checks establish exact-candidate source verification only. A successful candidate does not retrospectively identify or fix the original incident. The final external exact-head receipt is linked from Draft #65's current description and the continuation handover; this document does not claim a future CI result.

Physical endpoint/two-node/SDK/no-start/native/session/resource/load/client/migration/rollback qualification remains OPEN. No private VM, production merge, deployment, account/credentials/AutoTrading change or generic PowerShell operation is included.
