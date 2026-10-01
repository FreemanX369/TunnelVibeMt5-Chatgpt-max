# TIP-055B — Deployed lease recovery checkpoint

Date: 2026-10-02, Asia/Saigon. Status: **DONE for the bounded lease-release correction**. Real M0 identity enrollment/resource qualification remains **OPEN**. This is the Contractor qualification of [PR #57](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/57), after the Builder's local [Completion Report](TIP-055B-completion.md).

## Exact authority

Owner continuation “Duyệt tiếp tục theo plan” at 02:12:19+07:00 is recorded in [the approval ledger](approval-2026-10-02.md). Reviewed source head `954e2e7bcaaec062484e47c3c32605558fea83d4`, tree `ef091532815cbe1aac07ba5380f8c0ad2e6d3789`, derives from main `db9a12895c1b908fb6b0e61f89f9d76db1b04415`. All 171 candidate blobs were verified. The following checkpoint commit changes documents/evidence only; runtime and regression bytes remain those reviewed and deployed.

[Machine-readable evidence](evidence/2026-10-02-tip055b-runtime.json) retains preflight, checkpoint, guarded writes, suites, refresh and public-read outputs, including the first post-refresh HTTP 504. The [deployment manifest/recovery protocol](TIP-055B-deployment.md) remains the affected-file authority.

## Verified outputs

| Gate | Actual evidence | Result |
|---|---|---|
| Exact-head CI | TIP-027 [36916153516](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36916153516); TIP-028 [36916153402](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36916153402); TIP-034 [36916153339](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36916153339); TIP-053 [36916153161](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36916153161) | All four PASS |
| Actual Windows handle cases | Bootstrap CI **366 passed, 4 skipped in 27.25s**; Deep Update **366 passed, 4 skipped in 37.20s**. All 33 TIP-055B cases execute; the four skips are two absent deployed MT5 roots and two POSIX M0 cases | PASS on CI Windows |
| Before write | READY/idle; native/mutation locks and waiters clear; all tunnels one process, 200/200; exact reviewed dependency hashes | PASS |
| Checkpoint | `BADMCP-20261002-024846-1A6304B5`, concurrency before-hash `bf7603ce7b2566eb13b3596944253dcee7005b22442b77dc3a2f9edc55c32c2e`, 19,896 bytes | PASS |
| New fixture | `BADMIN-20261002-024853-B744DD12`, server-enforced empty before-hash; 15,316 bytes; SHA `e5807e389b7b8f6064fe77ad522beaf1f85ce1931c3df95235334f3b236e586a` | PASS |
| Concurrency CAS write | `BADMIN-20261002-024903-6FD89124`, covered checkpoint and exact old-hash CAS; 21,029 bytes; SHA `94a8b2a82e2a55914d37a42516e893ef508536dd2c5106c378a4ee9b6342dbcc` | PASS |
| VPS compile / isolated selector | `py_compile` return code 0; `runtime_forensics` **74 passed, 2 skipped, 514 deselected in 13.92s**, return code 0 | PASS |
| B/C refresh | `BADMIN-20261002-025013-8A350956` / `BADMIN-20261002-025045-A6D445B0`; new B PID 4412 / C PID 5740; one process, 200/200 | PASS |
| Detached A refresh | `BRESTART-20261002-025051-5D067112`; completed 02:51:00.9406705+07:00; phase restart_complete, readyz ready, `terminal_touched=false` | PASS |
| Current runtime | Generation `38f74e08b4c1418c8695e4698b203a31`; supervisor 4600, tunnel A 4392, adapter 3804; fresh READY heartbeat and HEALTHY watchdog | PASS |
| After refresh | Exact two-file hashes; catalog 85 / `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef`; fixed MT5-2; public inventory exactly equals the preflight sample | PASS |
| Actual M0 identities | Five UNENROLLED/UNQUALIFIED rows, null IDs/generations/revisions, no detected conflicts, routed-native false | OPEN |

The VPS fixed suite includes all 33 new temporary-root cases, including actual Windows handles. Its synchronous output exposes counts rather than named skip rows; the frozen selector/source/platform and exact counts are bound here. CI logs retain named skip reasons: [Bootstrap](evidence/tip055b-runtime/windows-bootstrap-ci.log), [Deep Update](evidence/tip055b-runtime/windows-deep-update-ci.log), normalized to LF for repository text. This certifies isolated sharing-error behavior on Windows; it is not new native-job or physical target acceptance.

The private mutex prevents simultaneous callers on one lease deleting a successor. Fresh token checks and bounded retries preserve unresolved release for a later attempt. This does not introduce atomic cross-process compare-unlink fencing or a hard total wall-clock deadline; mutex wait/OS I/O remain outside the one-second retry budget. Global acquisition, FIFO, capacities and native policy remain unchanged.

## Failures retained and recovery boundary

The first health call after detached A refresh timed out with HTTP 504. The controller receipt then returned PASS; the subsequent public-read batch returned READY and the new generation. No second restart was sent. The completion receipt is 596 bytes, SHA `00a42a79e5200a1d90d088abb505d26c7b4ff77e2bf34cf30f096e99f4e10016`; read it through `backend_read_evidence(relative_path="backend-admin/BRESTART-20261002-025051-5D067112.json")`.

Original issue #56 CI failure and both local negative controls remain retained. No rollback was required or exercised. The checkpoint covers concurrency only; the new regression file remains if functional service rollback is used. The recovery runbook does not claim exact new-file removal.

The historical Soak PASS belongs to generation `58cd0f1bcb3346439b81afe2116226eb`, not this generation. No fresh soak or native tester job was run. MT5-2's observed build 6230 still comes from the September 29 job; it is retained history.

## Next authorized action

TIP-055B output gates are closed by these receipts; issue #56 can close after exact reviewed PR merge. M0 remains PARTIAL. Use the existing [concrete local CLI enrollment steps](TIP-055A-runtime-qualification.md#concrete-operator-step-to-close-enrollment), retain bootstrap/show/reload and a hash-verified complete registry backup, and require at least two distinct physically QUALIFIED bindings.

The connector has no identity CLI executor and cannot access `state/fleet` through guarded file operations. This is the current execution boundary, not a new permission question. No generic PowerShell MCP, JSON injection, native job, live chart or account/credential/AutoTrading operation was used. [TIP-057R readiness](TIP-057R-readiness.md) marks release recovery evidence closed while enrollment and frozen schema/deadline ACs remain open; its build is not dispatched.

