# TIP-055A — Actual M0 enrollment qualification

Date: 2026-10-02, Asia/Saigon. Status: **PASS — LOCAL M0 ENROLLMENT / BACKUP / RELOAD / INVENTORY RESOURCE QUALIFICATION**. This closes the real M0 identity gate retained in PR #54/#55/#57/#58. It does not enable targeted live/native operations or cryptographic node enrollment.

## Authorization and source

Owner explicitly requested: **“Dùng tool trong @TunnelVibemq5 tiến hành tự run lệnh ps trên đi”**, submitted **12:07:49+07:00**, referring to the existing identity-show/bootstrap/show commands. This supersedes the earlier no-generic-PS restriction **only for this bounded identity CLI task and necessary verified registry backup/read qualification**. Other shell/admin/native/account constraints remain intact; no new executor/API was added.

Reviewed GitHub base `4c001a2dc2dc0a61ea73071efdc5bcb6772719a3`, tree `bee38b233eacef712757f9a7ac383758276d3ebd`, contains all 178 verified blobs. Before bootstrap, deployed fleet modules, inventory, CLI and jobs/concurrency helpers exactly matched the already-reviewed hashes. [Raw evidence](evidence/2026-10-02-m0-enrollment.json) binds those hashes, original UNENROLLED sample, command receipts, actual registry, backup and postchecks.

No new product code was needed: real registration closes an existing dependency; reuse the already deployed CLI and atomic registry; execute one bootstrap, fresh show and full hash-verified backup. No hidden enrollment test, state injection or deletion/reset was used.

## Actual outputs

| Gate | Receipt / actual result |
|---|---|
| Initial show | `PSHELL-20261002-120937-48FB60E2`, PASS/exit0, UNENROLLED and registry null |
| Bootstrap | `PSHELL-20261002-121049-6A835564`, PASS/exit0, full five-row registry committed once |
| Fresh process show | `PSHELL-20261002-121156-DFA628EC`, PASS/exit0, complete record equal after canonical key comparison |
| Backup | `PSHELL-20261002-121347-2F4CBEC6`, PASS/exit0; source-before/source-after/backup SHA all equal |
| Fresh process after backup | `PSHELL-20261002-121536-9A714832`, PASS/exit0; entire registry/IDs/bindings/generations/revision/operations unchanged |
| Public inventory | Five ENROLLED / QUALIFIED rows, no resource conflicts, all routed-native false |
| Compatibility | All pre-existing inventory fields exactly equal preflight; fixed MT5-2; catalog 85 / unchanged SHA |
| Postguards | READY/queue0/active-job null; native/mutation locks and waiters clear; A/B/C each one process and healthz/readyz200 |
| Runtime refresh | None; existing generation and adapter/tunnel PIDs retained |

Device ID: `dev_e488e5a0105847febf7ed46c9e15e9d0`. Identity schema `fleet.identity/1`; identity revision **1**; every terminal generation **1**; authority `LOCAL_PERSISTED_REGISTRY`.

| Alias | Actual persisted terminal ID | Inventory qualification |
|---|---|---|
| MT5-1 | `term_aa5090f42e3b4743a4322384f2e139bf` | ENROLLED / QUALIFIED |
| MT5-2 | `term_dbfaf35a2a5f4b41bd2fedd387512c3a` | ENROLLED / QUALIFIED |
| MT5-3 | `term_e989b1b76e3f417ca98fc52f431eba55` | ENROLLED / QUALIFIED |
| MT5-4 | `term_569512a99eb646aab650428e0b8d4433` | ENROLLED / QUALIFIED |
| MT5-PROGRAM | `term_f5ef765543364591ae25a3dcb270e277` | ENROLLED / QUALIFIED |

The full registry records each real executable/data-root canonical observation. Existing M0 inspection reports distinct bindings and zero conflicts across all five rows. QUALIFIED means local observable inventory resource binding; it does not certify simultaneous tester capacity, IPC attachment, active live session or target-specific native execution. Actual target IDs are now recorded; later pilots must also freeze their running/session/operation readiness.

## Complete verified backup

Path: `C:\VibeMQL5-Backups\identity\M0-20261002-121049-6A835564\identity.json`, outside mutable installation state. Source and copy are **3225 bytes**, SHA-256 `171e310d844ea786ff2a5767d89dce132b21ec8e843b0a51d216b9bf57c1f931`. Destination was newly created; no existing backup was overwritten. Source hashes before and after copying match the complete backup. A further CLI process reload proves the live registry still matches the original full committed record.

This verifies full-copy/byte/hash/read persistence, not a performed restore drill. Keep this backup and operation receipts; do not reset IDs/generations or edit registry JSON to repair future drift.

## Diagnostics preserved

The first Contractor comparison used raw JSON.stringify and reported a difference because persisted JSON keys are sorted. Canonical full-record comparison then proved semantic equality, with no bootstrap retry or state mutation. That comparison diagnostic remains in raw evidence.

PowerShell stderr contains first-use module CLIXML progress. Every identity/backup process exited0 with PASS, no truncated output and no redactions. Prior recovered tunnel poll TIMEOUT episodes remain retained. No fresh soak, chart, live/account API, account/credential/AutoTrading operation, native job, restart or restore was performed.

## Next contract gate

The real enrollment/backup/reload/resource-binding part of M0 is now PASS. [TIP-057R readiness](TIP-057R-readiness.md) can use these actual IDs rather than placeholders. Its remaining additive schema, numeric hard-versus-soft deadline, cleanup-unproven ownership/recovery and strict attach-only/no-start contract still need concrete resolution before BUILD.

[TIP-056 readiness](TIP-056-readiness.md) remains M4 after TIP-060. Local registration supplies a prerequisite; it does not unlock native concurrency or bypass durable target/resource/journal qualification. Ed25519 pairing/route generations remain TIP-058 work.
