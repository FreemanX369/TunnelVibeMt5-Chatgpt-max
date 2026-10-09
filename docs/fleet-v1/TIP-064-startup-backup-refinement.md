# TIP-064 — Preserve startup ownership and ordinary backup budget

Status: **BOUNDED FIXTURE REFINEMENT; EXACT-CANDIDATE GATE REQUIRED**. Candidate `fe199eb110cbba83a26491d90ddc14830cdc9e17`, tree `b6717bdfcb32ac31c91438b2934830fb708e5fd6`, completed all eight workflows on attempt 1: five success, three failure. The [checkpoint receipt](evidence/tip064/ci-fe199eb/metadata/verification-receipt.json) retains the original logs and all five artifact ZIPs. Their bytes/digests were checked; both integrated source manifests match all 207 exact Git source files.

Deep run `37264596406`, job `111618614404`, reports 1134 passed/two failed/ten skipped. The full-journal restore positive hits `CONTROL_BUSY` during `_bounded_backup.progress` under its imported 100 ms SQLite profile. The delayed capacity positive retains `TimeoutError` at `/poll` response status observation, 1000 ms elapsed, server alive and failure count zero. Its retained capacity note shows two STARTING jobs, a third QUEUED, two pending futures/native records and scope observation timeout. This proves the client response deadline was exhausted; it does not establish the server's actual blocked stage.

Bootstrap run `37264596433`, job `111618614586`, reports 1135 passed/one failed/ten skipped: restore startup hides its server outcome behind `ready.get(timeout=5)` / `Queue.Empty`. Integrated run `37264596452` passes Linux 1132/14 skips; Windows reports 1131 passed/three failed/two setup errors/ten skips. Windows failures are two ordinary backups with `CONTROL_BUSY`, one restore startup wait, and two composed startup waits. Windows proof commands still exit zero. Neither the Linux result nor the harmless proof results replace these failed gates.

## YAGNI-3 before implementation

1. Startup raises before returning the stop/thread handles, bypassing fixture ownership cleanup and hiding the original server exception or live stage. Ordinary full-journal backups reuse a short transport-control SQLite budget, despite existing normal backup/restore fixtures using 1000 ms. These are bounded fixture defects, separate from an inferred production cause.
2. Reuse `wait_gateway_started`, `preserve_fixture_failure`, `stop_gateway_fixture`, the existing ordinary-operation SQLite profile, actual temporary-CA HTTPS and sanitized basename/function/line frames.
3. Add a small test-only startup owner; apply it to the implicated restore/composed/capacity fixtures. Prove exact original factory exception, live startup/cleanup uncertainty and healthy backup progress separately. Record server live frames for the existing transport note. Production modules, TLS, request HTTP 1000 ms, authority/UNKNOWN rules and zero automatic replay stay unchanged. Normal startup remains five seconds; each fixture retains its existing stop observation.

## Acceptance and open facts

Frozen Builder and independent Contractor verification must bind the final source files and retain positive and negative controls. A new delivered head requires its own eight successful workflows plus ZIP digest/head/tree/manifests/JUnit/proof verification. This document does not claim a future candidate's CI result.

The original first-grant transport cause, the earlier unrecorded shutdown stage and the current unrecorded startup/server stages remain OPEN unless direct evidence identifies them. A later green candidate cannot reconstruct those missing observations. Physical VM/MT5/SDK/no-start/two-node/native/session/load/client/migration/rollback qualification and production merge/deployment remain OPEN and unperformed.

## Frozen review evidence

Builder and independent Contractor each pass **248 tests with three explicit Windows skips**, zero failures/errors. Their frozen six-file hashes are unchanged before/after; all 88 production Python files match the original `8019a52` source. [Logs, JUnit, dependency identity and receipts](evidence/tip064/startup-backup-v3/receipt.json) are versioned separately from preliminary control runs. The five focused controls prove actual factory error identity/closed thread, live startup plus cleanup uncertainty, real SQLite DONE progress under controlled 150 ms elapsed observation (100 ms denied / normal 1000 ms snapshot accepted), independent owner reopening, and the actual held response handler's bounded server stack. The existing explicit 100 ms SQLite contention and negative TLS/request-deadline cases remain in the matrix.

Checkpoint stores now close through existing context managers even when backup fails. Startup observation stays five seconds, restore stop stays five seconds and composed/capacity stop stays three seconds. No source test grants production qualification. Final exact-head receipt and handover will record the next candidate's own gate; no result is inferred in advance.
