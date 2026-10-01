# TIP-055B — Guarded corrective rollout

Status: READY FOR EXACT-HEAD CI/CONTRACTOR QUALIFICATION; deployment not yet claimed in this initial package. Owner scope: [02:12:19 continuation](approval-2026-10-02.md). The [TIP](TIP-055B.md) and Completion Report determine source/fixture evidence; later runtime receipts determine deployed acceptance.

## Payload and source authority

| File | Bytes | Candidate SHA-256 | Current live SHA-256 / action |
|---|---:|---|---|
| app/vibemql5/core/concurrency.py | 21,029 | `94a8b2a82e2a55914d37a42516e893ef508536dd2c5106c378a4ee9b6342dbcc` | `bf7603ce7b2566eb13b3596944253dcee7005b22442b77dc3a2f9edc55c32c2e`, checkpoint + fresh exact CAS |
| tests/unit/test_tip055b_runtime_forensics_release.py | 15,316 | `e5807e389b7b8f6064fe77ad522beaf1f85ce1931c3df95235334f3b236e586a` | create only with server-enforced empty expected hash; collision stops |

Base main `db9a12895c1b908fb6b0e61f89f9d76db1b04415`, tree `ac094ada3c0817515aec49062556843d5c0ba076`; all 160 base blobs verified in the isolated checkout. Candidate source head/tree and four CI links are bound by the implementation PR and runtime checkpoint. A local synthetic snapshot is not a GitHub parent.

Main concurrency SHA is `74700aa7db7ee5279dd1166bbcb5465ce939b1da06858cbbd6123fb1eaa365f4`; live differs by three comments only, full AST equal. The payload keeps those comments. Live jobs helper remains `e1bbc44058006803f2203af916a333575cd80efcf0cef778fba55024dc902759`, reviewed statement-AST compatible; backend core is unchanged `4f5b4b9b5002279d6daa1f8ad49e3d3701be719197e648fda87864bf50348573`. Neither dependency is part of this payload.

The fix adds a private per-lease release mutex, fresh token checks and a one-second sharing-error retry budget at the existing 50ms cadence. Only WinError32/33 is retryable. Unresolved release stays retryable; corrupt/general permission failures remain explicit. Mutex wait/OS calls are not claimed as a hard total wall-clock deadline. Global lock paths, FIFO/capacity, acquisition and public API/schema/catalog remain unchanged.

## Readiness and exact evidence

1. Review exact source/test delta and all four exact-head CI workflows. Require both actual Windows deny-delete tests executed successfully, with no mechanism-unavailable skip. Preserve original issue #56 failure and no-lock regression sensitivity proof.
2. Refresh server_info, health, tunnel_admin_status(all): catalog 85 / `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef`, fixed MT5-2; READY, queue 0, active job null, mutation/native locks and waiters clear; A/B/C each one process, 200/200.
3. Fresh hash the existing concurrency target/dependencies and compare approved live values. Any unexplained source drift stops review; do not overwrite to make Git match.
4. A generic read error for the new fixture is not absence proof. Use supported backend_write_file with expected_sha256="", checkpoint_id=""; server rejects an existing file. Require successful empty before-hash and exact after-hash.

## Controlled write, fixtures and refresh

1. Checkpoint exact live concurrency bytes with backend_create_checkpoint; record coverage/hash/receipt.
2. Create the reviewed isolated fixture with the empty-hash precondition. Write concurrency using that checkpoint and fresh live expected SHA. No config, identities, native drivers, jobs, accounts or credentials change.
3. Hash both files against this manifest. Run supported py_compile and runtime_forensics once each; require unambiguous PASS, return code 0 and retained summary. The new module uses temporary roots only, including real Windows deny-delete handles. The existing selector also verifies M0 identity fixtures/static forensics; no real enrollment.
4. Do not run deployed unit/baseline_aware: their existing live VPS tests can operate charts. Do not use a generic PowerShell MCP, hidden enrollment test, new suite or API.
5. Refresh B then C using supported per-instance restart; verify each one process and 200/200. Refresh A last through detached backend_restart_runtime(interactive_tunnel), retain scheduled receipt and retrieve the completion receipt through backend_read_evidence using backend-admin/<receipt filename>, already relative to evidence/runtime. A transient connection timeout is not permission to send another restart.
6. Read health, server_info, all tunnel status, runtime status and list_terminals; verify idle/catalog/fixed-native compatibility and exactly retained old inventory/identity values. Require current heartbeat and changed runtime generation/adapter PID. Read-back hashes identify current installed source; unchanged TIP-053/0.2.42 metadata alone does not.

A successful actual VPS Windows-handle fixture certifies isolated sharing-error release recovery on that host. It does not certify a new native job, physical M0 identity binding, targeted IPC or concurrent native execution. Synchronous fixed-suite summaries do not expose named skip rows: bind source/hash/selector/platform/count evidence and preserve any unresolved named-result limitation separately.

## Recovery

If source/compile/fixture/public-read acceptance fails, fresh-hash concurrency and restore only the checkpoint-covered target with exact expected_current_sha256_by_path. Reject unexpected drift. Re-hash old payload and refresh B/C/A; require READY/idle/catalog/legacy fields. No restore is needed when acceptance passes; a planned recovery route is not a performed rollback test.

The created fixture remains after a functional service rollback. It can fail against old release behavior and must not be skipped/tombstoned to conceal that fact. Current API has no exact new-file deletion; separate operator cleanup requires verifying its recorded candidate hash before removal and retaining evidence. This is functional service rollback, not exact filesystem rollback.

## Completion boundary

Keep CI, Windows mechanism, guarded write/readback/checkpoint, compile/selector, refresh and public-read receipts separately. Close issue #56 only after the reviewed fix and deployed qualification receipts exist. Real M0 identity enrollment/show/reload/backup/root qualification remains OPEN and uses the concrete CLI steps in [the M0 runtime checkpoint](TIP-055A-runtime-qualification.md). TIP-057R remains [readiness refinement](TIP-057R-readiness.md).

