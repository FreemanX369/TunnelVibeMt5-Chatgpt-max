# Fleet v1 — Verification, migration and release contract

Status: approved verification contract, per the [owner record](approval-2026-10-02.md). This document specifies evidence to collect; it contains no new fleet PASS receipt.

Latest checkpoint at13:36: [TIP-057R contract](TIP-057R-contract.md) and [Builder feasibility](TIP-057R-feasibility.md) are prepared from main `146c72ad37a5daa5f1f64ee4aba7f0d2f84ef809`. All14 read ACs remain PLANNED. G03 shared uncertain-cleanup recovery and G04 strict no-start block product IPC BUILD; the [isolated Q1 proof proposal](TIP-057R-boundary-proposal.md) awaits a concrete architecture decision. Documentation CI validates the unchanged code baseline and does not certify a new helper, deadline, schema exposure or account read. [Fresh read-only receipts](evidence/2026-10-02-tip057r-contract.json) preserve current runtime and recovered B poll timeout.

## Evidence and non-regression matrix

| Behavior | Required checks | Gate |
|---|---|---|
| Local stable IDs / config overlay | 055A AC-01–14 | M0 |
| Source guard/checkpoint/CAS/atomic restore | Existing source/revision and TIP-054 tests; exact bytes/hash preservation | Every touching TIP |
| Job idempotency and process ownership | Existing TIP-028/recovery tests plus routed operation/start/ACK/commit windows | M2/M3 |
| Project/Iteration/Continuity | Existing revision/CAS/delegation tests plus frozen target/drift/single-writer cases | 061A/061B/063 |
| Live/account/market reads | Exact executable/data-root binding, IPC interleavings, account/AutoTrading unchanged | 057R/059 |
| Chart/file/widget | Same capture bytes/hash, target-scoped reference and actual viewer/download; layout restored | Chart/artifact capability |
| Native tester | Actual Windows session, dedicated installation, requested=executed, build/input/process evidence | 057N/060 |
| Runtime capture | Existing job-bound binary/agent identity; routed unsupported response or new exact authority | M2/M3 capture scope |
| Resource locks/capacity | Legacy+routed contention, reservation race, dead owner/PID reuse, fairness | 056 |
| Auth/admin/dispatch | TLS/node identity, replay, clone/revoke, caller principal; no generic admin auto-routing | 058/063 |
| Backup/migration/rollback | Consistent snapshot, stale restore reconciliation, schema/version rollback and retained receipts | 058/060/064 |
| Tool surface | Catalog/schema and actual selected-client visibility/receipt | Each tool/schema change |

Map new REQs/ACs to test names and receipts in each Completion Report. Existing test counts are baseline context, not proof of a new target or platform. A public-read PASS, fixture PASS and native physical PASS are distinct.

## Migration and rollback

1. M0 adds an independent identity overlay; legacy configuration and native request/index/history bytes remain intact. Do not edit signed/hash-bound historical records in place.
2. Future schema migrations write versioned records/revisions with explicit legacy provenance; no inference of historical stable identity from today's alias. Keep readable legacy operation IDs and recorded hashes.
3. New native routing must share resource ownership with legacy operations. Feature-gated routed paths remain disabled until exact-target and rollback gates pass.
4. Deployment is an exact reviewed head with affected-file hashes, checkpoints for existing files and expected-hash removal/restore procedure for new files. Reuse the supported backend deployment workflow; do not introduce generic PowerShell MCP as an alternative.
5. Rollback disables new dispatch first, preserves node/gateway journals and registry epochs, then restores compatible code/settings. If old code cannot read new queued commands/schema, drain/quarantine rather than replay under an older generation.
6. Back up gateway SQLite using a consistent database snapshot method and test restore. Do not assume copying only an active WAL database file is sufficient. Identity revisions, generations, operations and node journals are reconciled before dispatch after restore.
7. Retain failed, timed-out, superseded and unresolved outcomes. New good health never erases a previous failure or certifies a different run.

## Physical/failure matrix by milestone

M1: two enrolled nodes, distinct target bindings, read attribution, unavailable terminal, node offline/reconnect, gateway restart, node restart, replay/revoke, cached-versus-live freshness and request deadline. Record actual pilot target IDs; no illustrative VPS/build is treated as inventory.

M2/M3: native target and input/provenance; queued cancel; exact process kill/PID reuse; terminal restart; node restart before reservation, after reservation, during start and after start before ACK; gateway restart and result commit interruption; duplicated commands; old-generation requests; node/gateway backup restore. UNKNOWN outcomes are a correct fail-closed result until reconcile proves status.

M4/M5: independent installation/data-root resources; simultaneous native jobs within capacity; shared resource conflicts; source mutation during immutable tester execution; capacity race, fairness and resource veto; stale agent/session/epoch before and during recovery; source checkpoint/CAS conflicts; worktree isolation and parent verification. Loss of agent heartbeat alone never cancels a native job.

Full release topology proposed from the original plan: three VPS with at least two distinct MT5 bindings per VPS. Availability of these machines/builds is an open qualification gate. A two-node pilot can be delivered as a two-node pilot; it does not prove the full topology. Generic Repo Worker and input transfer remain outside release until separately scoped.

## PASS thresholds

Invariant thresholds are zero wrong-target attribution/execution, zero conflicting operation identity silently accepted, zero unauthorized stale-authority writes, zero cross-job process cancellation, and zero substituted/unverified artifacts accepted as the requested evidence. Duplicate native starts for one operation are zero within the defined replay/crash matrix; unprovable outcomes remain UNKNOWN rather than automatically retried.

Numeric latency/resource/recovery thresholds and load must be selected before each physical run using a recorded baseline on actual machines. Include devices/terminals, request/job count, concurrency, input datasets/config, peak RAM/CPU/disk, queue wait/fairness, p95 read latency, restart/recovery times and expected outcomes. Do not infer max_native_jobs from five registrations or a single free-RAM sample.

A 60-minute final soak records sample count, workload, exact code/config/tool-catalog/target identities, start/end time and zero-bad policy where appropriate. The existing 120-sample Tunnel soak may be retained as historical baseline; it cannot certify new fleet behavior. Fault matrix success is required in addition to soak duration.

## Completion checkpoint and next-chat protocol

Contractor records approved Blueprint revision, active TIP/base/head, actual implementation/CI/physical receipts, outstanding gates, deviations and the next authorized action. Repository documents become the handover authority; no fresh chat needs to reconstruct the brainstorm. Read only relevant drift and retained reports before continuing. Never reset the baseline evidence or announce release completion from documentation alone.

Current checkpoint: Blueprint PR #53 and M0/lease/planning PR #54/#55/#57/#58 merged. The [M0 deployment checkpoint](TIP-055A-runtime-qualification.md) records six-file installation and fixture/read acceptance; [actual enrollment receipts](TIP-055A-enrollment-qualification.md) now close local bootstrap/verified backup/fresh-process reload/inventory resource qualification for all five rows. [TIP-055B runtime checkpoint](TIP-055B-runtime-qualification.md) records four CI PASS, actual Windows handles and guarded deployed qualification PASS. [TIP-057R readiness](TIP-057R-readiness.md) still retains additive schema/deadline/cleanup/no-start contract and actual live-read gates before BUILD.

The 11:27 continuation added [TIP-056 readiness](TIP-056-readiness.md) and [TIP-057R source scan](TIP-057R-source-scan.md). The later 12:07 explicitly authorized PowerShell CLI/backup transition closes M0 for its approved scope; M1/M2/M3 implementation and physical live/native acceptance remain OPEN. Preserve both the historical readiness sample and [new enrollment evidence](evidence/2026-10-02-m0-enrollment.json), including recovered tunnel poll failures and the JSON-key-order comparison diagnostic. No new native/capacity/latency/soak or restore acceptance is claimed.
