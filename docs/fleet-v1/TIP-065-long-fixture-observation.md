# TIP-065 — Bound the complete positive phase fixture and preserve failures

Continuous Contractor contract, 2026-10-05. Parent `30bcc584953b29a8564bff717b3b4d5819a02798`, tree `b84c1f196461f49e852bb4cc9230a4b4da663bb3`, remains rejected at 7/8, attempt 1. Bootstrap run 37297936583/job 111723528091 records 1219 PASS, one FAIL, 12 skips: the long synthetic phase fixture exhausted its five-second aggregate observation. The original trace contains no callback stage or terminal state; its historical cause stays UNKNOWN.

## YAGNI-3 before code

1. Necessary: four discriminating experiments on the unchanged 211-entry parent source demonstrate a real positive harness boundary and loss of callback exception identity. Six bounded harmless worker scheduling holds, without extending a queued request or proof, make the original five-second fixture fail; actual cleanup still observes durable SUCCEEDED. A ten-second observation runs all original assertions successfully. All five authorization RPCs returned below 135 ms under unchanged HTTP/TTL 1000 ms.
2. Reuse: the actual TLS fixture, signed phases, durable journals, owner drain and existing primary/cleanup failure preservation. Production UNKNOWN semantics and heartbeat-first control ordering are correct conservative boundaries for this task.
3. Smallest correction: one existing test file, `tests/unit/test_tip064_integration.py`. Change only the affected positive aggregate observation from five to ten seconds and propagate original callback/wrapper failures to the test owner, retaining identity and notes. Add controls against the same shared fixture implementation.

The prior bounded ABI contract froze all budgets for that implementation. This new contract supersedes that restriction only for this positive aggregate fixture watchdog, on the controlled evidence above. It does not change product deadlines or authority. This is not a measured historical latency fix, retry policy, or physical qualification.

## Acceptance and boundaries

Keep the original test name and all original expired-proof, fresh grant digest/sequence, synthetic evidence, terminal-ACK-before-future-return and final empty-record assertions. A shared helper may expose explicit test-only scheduling hooks or observation budget for controlled tests. Prove old aggregate failure versus corrected aggregate success under a finite valid schedule. Prove original callback and delayed-return wrapper exception identity/notes survive, including pytest failure types and primary-plus-cleanup combinations when relevant.

Keep every production file unchanged, including all 89 app files. Preserve HTTP 1000 ms, authorization TTL 1000 ms, SQLite and shared control-round budgets, the original 1.2-second producer, three-second delayed-return and three-second cleanup. Do not catch an error and call it successful completion. Do not reorder production control, retry a request, resolve UNKNOWN, clear retained records, relax source/authority checks, mutate live runtime or rerun failed CI.

Builder delivers exact diff, full focused command/environment/log/JUnit, before/after source manifests and completion report. Contractor reviews independently, verifies the frozen candidate, retains original failed receipts, then publishes one reviewed candidate to Draft #65. Its own eight successful workflows, five official ZIP digests, exact Git head/tree/source manifests, complete JUnit and harmless proofs are required before deployment. The already selected five-file legacy observation overlay remains byte-frozen. Full Fleet activation and private VM/MT5/SDK qualification stay OPEN/NOT_RUN.
