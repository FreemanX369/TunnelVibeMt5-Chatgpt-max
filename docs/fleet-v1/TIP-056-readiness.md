# TIP-056 — Terminal-scoped native concurrency readiness

Date: 2026-10-02, Asia/Saigon. Status: **READINESS REVIEW COMPLETE / BUILD BLOCKED BY DEPENDENCIES**. This is a planning checkpoint, not a dispatched TIP or concurrency certificate. User request: “Check task tip-056 theo plan & tiếp tục”, 11:27:00+07:00.

## Approved placement and current evidence

The [approved task graph](task-graph.md) places TIP-056 at **M4 after TIP-060**, not immediately after TIP-055B. Blueprint section 9 preserves node native capacity 1 through M3 and requires resource conflict qualification before same-node parallelism. REQ-F11 is the primary requirement; REQ-F02/F06/F07/F08/F10/F15 supply compatibility, target, replay, cancellation, session and release constraints.

Fresh GitHub main remains `c9657aeee23960b59218abc641a8757af55bed7c`, tree `e8a0823e924c31c4f7bd1f817216633534d65b12`; all 175 snapshot blobs were verified. PR #57 is merged and issue #56 closed. The read-only [checkpoint evidence](evidence/2026-10-02-tip056-readiness.json) records READY/idle, clear locks/waiters, A/B/C one process each and 200/200, catalog 85, fixed MT5-2 and exact installed TIP-055B concurrency hash. All five inventory rows remain UNENROLLED/UNQUALIFIED. Observed native parallelism is 1.

A and C retain one recovered poll TIMEOUT episode each, at 05:35 and 07:51 respectively. Their current endpoints pass; these recovered failures remain evidence and are not erased or recertified as a new soak. No restart, native job, account observation, identity write or configuration change occurred during this review.

| Dependency | Current result | Needed to dispatch TIP-056 |
|---|---|---|
| TIP-055A / M0 | Code/read installation PASS; actual identity qualification OPEN | Stable real IDs, complete verified backup/reload, physically independent resources |
| TIP-057R | Readiness and [source scan](TIP-057R-source-scan.md); no implementation | Qualified exact local reads and serialized IPC lifecycle |
| TIP-058/059 | Roadmap only | Enrolled node transport and exact remote read bindings |
| TIP-061A / TIP-057N | Roadmap only | Frozen project/job targets and exact local native worker/result/cancel provenance |
| TIP-060 | Roadmap only; direct required predecessor | Durable remote serialized jobs, reservation/start/ACK/commit journal and UNKNOWN reconciliation |
| TIP-056 physical scope | No capacity/load pilot exists | Frozen conflict matrix, actual installation/session/agent resources and measured load limits |

## YAGNI-3 before implementation

1. **Must it exist?** Only to run multiple qualified native workloads on the same node after serialized remote jobs work. Five registrations and a free-RAM sample do not establish a present need or safe capacity.
2. **What can be reused?** Existing token/FIFO native lease, mutation ordering, JobStore atomic operation index/request hash, process creation identity/stop proof, M0 resource inspection and deployed TIP-055B release recovery.
3. **Shortest sufficient change?** Extend existing ownership/admission with frozen physical resource sets and one atomic device capacity reservation. Preserve source/global serialization where required. Add no independent scheduler, alias-derived lock namespace or duplicate job journal.

## Source reuse and limits

References below bind to the reviewed base above.

| Reuse | Evidence | Limit |
|---|---|---|
| Native serialization/FIFO | `core/concurrency.py`:131–290,366–383 | One `runs/.active.lock`; not terminal-scoped capacity |
| Release ownership | `core/concurrency.py`:297–362 | Token + private mutex + WinError32/33 recovery; no new cross-process atomic compare-unlink fencing |
| Status | `core/concurrency.py`:541–551 | `native_mt5_parallelism=1` |
| Mutation/native ordering | `core/facade.py`:365 onward; `worker.py`:106 onward | Legacy compile/worker share the global protocol; future routed work must share physical ownership |
| ResourceGuard | `core/resources.py`:34 onward | RAM/disk observation, not an atomic reservation |
| Job identity/replay | `core/jobs.py`:374 onward | Local operation→job reservation; no fleet target/resource/capacity journal yet |
| Exact cancellation | `core/jobs.py`:214 onward,877 onward | PID+creation identity/executable and stop proof; not an authority to free a running reservation after timeout |
| Resource conflict inspection | `fleet/identity.py`:48–105,302–343 | Observable canonical/file identity; real M0 bindings still absent |
| Worker target | `worker.py`:181 onward | Existing fixed MT5-2 policy; explicit targeted execution awaits TIP-057N |

Existing lock stale-owner recovery checks PID existence; PID reuse conservatively blocks and is not a reservation fencing certificate. Job cancellation already has stronger process identity. Reuse that evidence where applicable rather than treating a reused PID or lost heartbeat as proof an old native workload ended.

Reuse regression modules `test_tip024_multiclient_concurrency.py`, TIP-023 cancellation, TIP-028 idempotency and `test_tip055b_runtime_forensics_release.py`. Their historical PASS proves their original scopes; this review runs no new tests and does not relabel them as M4 acceptance.

## Required conflict contract

Before BUILD, freeze resource keys from qualified physical observations and define compatibility for every operation pair: compiler/deployment, tester, IPC account/market read, chart capture, installation/data-root changes and local agent use. Include executable/data-root equivalence, tester/agent/session resources and source mutation where shared.

Unknown or unobservable equivalence remains unqualified and serialized. Different aliases alone cannot prove independent resources. IPC lifecycle remains node-serialized until a separate reviewed boundary proves isolation; terminal-scoped tester capacity cannot silently relax IPC or capture restrictions.

Legacy and routed use of one physical resource must compete in one ownership protocol. Define one acquisition order covering existing mutation/global ownership, device capacity and resource sets; preserve all-or-none reservation on failure. No specified future ordering here overrides current mutation→native behavior.

Numeric native capacity, memory/disk veto, queue wait/fairness, recovery and throughput thresholds remain **OPEN**, to be selected from the actual pilot before qualification. Admission checks must atomically count reservations; two simultaneous successful free-RAM checks are insufficient.

## Draft Gherkin acceptance map

These are output requirements to refine into the dispatched TIP after prerequisites exist. They are not implemented tests.

| AC | Given / When / Then | Evidence |
|---|---|---|
| 056-A01 | Given exact qualified TIP-060/TIP-057N and pilot bindings, when dispatch readiness is checked, then source/config/catalog/target/journal receipts are present and compatible | Dependency manifests and real qualification |
| 056-A02 | Given shared canonical paths/file IDs/agent resources or unobservable equivalence, when bindings are evaluated, then conflicting capacity is denied or serialized | Frozen pairwise conflict matrix and negative aliases/junctions |
| 056-A03 | Given simultaneous legacy and routed work on one physical resource, when either acquires ownership, then the conflicting workload never overlaps | Actual mixed-client loaded Windows trace |
| 056-A04 | Given competing capacity requests or partial acquisition failure, when reservations commit, then admitted count never exceeds selected capacity and failed requests leave no partial reservation | Barrier-driven contention and fault receipts |
| 056-A05 | Given crash, PID reuse, missing ACK or uncertain process stop, when recovery reconciles, then exact process/journal evidence determines release and unprovable outcomes remain UNKNOWN | Crash/replay/creation-identity matrix |
| 056-A06 | Given sustained contenders, when queued work is served, then selected fairness/starvation thresholds hold and abandoned tickets do not block successors | Frozen numeric workload and queue trace |
| 056-A07 | Given two actually independent qualified Windows installations/sessions/agents, when approved parallel workloads run, then requested targets equal executed targets, resource vetoes hold and no cross-job cancellation occurs | Actual loaded native result/provenance |
| 056-A08 | Given dispatch disable or rollback, when reconciliation/restoration runs, then active ownership/journals/IDs and retained evidence survive; no ambiguous workload is replayed | Reviewed recovery run and retained receipts |

## Next authorized work

Continue the nearest unmet dependency: real M0 enrollment, then freeze the [TIP-057R contract](TIP-057R-readiness.md) using its source scan. The existing [operator CLI handoff](TIP-055A-runtime-qualification.md#concrete-operator-step-to-close-enrollment) is concrete: identity-show → coordinated identity-bootstrap → fresh-process identity-show, verified complete backup, then public inventory proving two distinct physical QUALIFIED bindings.

The connector exposes no specialized identity CLI executor and guarded files exclude `state/fleet`. Generic PowerShell MCP remains outside the approved scope. Approval is not enrollment evidence; no hidden fixture or JSON injection substitutes for it.

Build dispatch for TIP-056 must reference the exact future dependency heads, chosen pilot target IDs/resource sets, numeric admission/fairness policy and actual recovery/Windows plan. This readiness document changes no approved dependency order or product capability.
