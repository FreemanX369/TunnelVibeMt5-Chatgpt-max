# TIP-057R — Proposed boundary amendment after Q1

Date: 2026-10-02, Asia/Saigon. Status: **PROPOSED / SOURCE BUILD NOT YET AUTHORIZED**. This is the concrete next decision package prepared under the owner's 19:40:29 continuation, “Tiếp tục triển khai theo plan”. It preserves the approved fleet Blueprint and strict no-start policy while proposing the product ownership boundary that Q1 deliberately did not authorize. Contractor owns this design; Builder's focused read-only SCAN supplies source feasibility. No product code, SDK, terminal, migration or runtime operation is performed by this planning step.

## Evidence and selected next slice

Main remains `70e2112da9fe8eaa6262f2ba896b55bf3e078260`. Draft PR #61 source/report head `9fcb86fc7bf061ba9fceb1eb2948e6290cbf8701` passes all five workflows, including actual Windows 16/16 with zero failures/errors/skips. [Q1 verification](TIP-057R-Q1-verification.md) and its original receipts are retained. The report is PARTIAL / FIXTURE_PASS_Q03_OPEN: matched direct fixture launch prevention and live-orphan ownership work; actual SDK/broker, breakaway causality, no-console startup, late-dead recovery and production integration remain OPEN.

Recommended next build is [TIP-057R-G03A](TIP-057R-G03A.md): **source/tests-only common admission and recovery foundation**. It may be implemented and tested after this amendment is approved, while actual helper creation, targeted live IPC, SDK initialization, migration, deployment and physical Q2 remain separately gated. A foundation PASS does not close G03 producer integration or G04.

YAGNI-3:

1. Required: unresolved IPC must prevent conflicting native effects after controller death; a fixture-only gate cannot protect product callers.
2. Reuse: the existing FIFO native lease, OS-held metadata lock, atomic JSON helpers, exact process identity and JobManager cancellation receipts. Reuse Q1's falsifiable ordering and native fixture evidence; runtime must not import a test module.
3. Shortest sufficient change: one product ownership authority, checks at actual common admission/stale removal and the central cancel-restore effect boundary, plus meaningful product-path fixtures. No scheduler, daemon, public recovery tool, remote transport or working IPC helper in this slice.

## Source facts that change the design

| Entry / evidence | Required foundation behavior |
|---|---|
| `core/concurrency.py`: `acquire_native_execution`, `_QueuedFileLease.acquire`, `_cleanup_stale_lock` | Check the durable authority at the winning acquisition decision and before native stale-lock deletion. A dead PID is not permission when unresolved ownership exists. Mutation namespace semantics stay separate. |
| `core/facade.py`: live/market/chart reads, direct compile and iteration compile use `native_execution` | Inherit the same denial before their effect; no target-only or adapter-local namespace. |
| `worker.py`: `acquire_lock` uses the same native lease; `finally` calls lease unlink | An ordinary release cannot erase unresolved durable authority or claim its cleanup complete. Existing worker/job provenance remains authoritative. |
| `core/jobs.py`: `_recover_cancel_terminal_state` probes MT5 at lines 782–785 or restarts at 798 | Gate both effects centrally. Preserve cancel intent/pending outcome when blocked. Existing exact process termination remains distinct from IPC/restart. |
| `core/jobs.py`: `get_job` invokes `_settle_cancel_if_stopped`; settle invokes restore | A nominal read can reach effectful recovery. Protect that internal boundary rather than relying on the public method's name. |
| `adapters/mcp.py`: startup reconciles cancellation before server registration | Unresolved recovery must stay observable; do not make the whole read-only MCP surface disappear at startup. |
| `backend_admin/core.py`: generic PowerShell uses the native lease; state/concurrency is outside restore/write allowlists | Admission inherits the barrier, but arbitrary administrative code is not a tamper boundary. Keep allowlists unchanged; do not introduce a remote force-clear route. |
| `test_tip024_multiclient_concurrency.py`: dead-owner lock currently auto-recovers | Preserve the valid CLOSED/no-unresolved compatibility case and add ACTIVE/invalid authority denials. Tests require explicit fresh-root migration setup; do not weaken the guard to keep old fixtures green. |

Ordinary caller admission is not the whole producer lifecycle. Existing in-process LiveTerminal/MT5Preflight/terminal-handoff callbacks still need a later reviewed durable-intent/cleanup integration before claiming full G03. This foundation must state that limitation explicitly.

## Proposed authority and installation contract

Use one small atomic authority snapshot, proposed schema `native.ownership/1`, under `state/concurrency`, plus a separate durable installation epoch marker, proposed schema `native.ownership.install/1`. Builder may use an equivalent existing module/path and report it; the outputs below are mandatory.

The marker contains a nonempty installation epoch, supported schema and migration disposition MIGRATING or READY. The authority binds that epoch, monotonically increasing positive generation, disposition CLOSED or ACTIVE, exact lease token and operation/kind, independently observed parent identity, optional independently observed worker identity, phase and descendant disposition. PID identity contains PID, creation identity and canonical executable. Arbitrary caller booleans or expected journal fields are not OS evidence.

**New guard-capable source requires a valid READY marker and matching valid authority before native admission.** Missing/invalid marker, missing/corrupt authority, epoch mismatch, unsupported version or interrupted migration denies native work. Reads/status remain usable and report a sanitized stable reason. Do not treat missing files as proof of an unused installation, lazily initialize from a read/acquire, or reset a generation.

This intentionally changes freshly installed/unmigrated source behavior: native work is unavailable until explicit migration. The currently deployed source is unchanged by source-only development. Existing successful native/legacy behavior after valid CLOSED installation remains compatible, apart from the separately approved unresolved-ownership denial.

Proposed controlled installation order under a quiet migration window: publish MIGRATING marker; publish matching CLOSED initial authority; validate both; publish READY marker. Every interrupted step remains blocked. Production migration must prove no old adapters/workers or effects can enter during this sequence; creating a marker cannot fence an old binary. **G03-A tests use explicitly initialized disposable roots only. The actual maintenance/CLI/deployment route is not authorized or implemented by this slice.**

## Ordering, closure and recovery

The existing mutation → native lock order remains. The new authority transaction guard is held only for short read/compare/publication/acquisition decisions; do not wait on a FIFO lease or run SDK/process waits while holding it. Winning native acquisition and native stale-lock removal must consult the same authority under that guard. A precheck before a long queue wait is insufficient. Reuse bounded lock waits; no new scheduler.

The internal future-producer interface must support:

1. With a valid owned native lease and CLOSED authority, commit ACTIVE intent and actual parent identity before any helper/native effect.
2. Commit CREATE_ATTEMPT immediately before the create API. Failure or crash before a worker is bound leaves unknown creation recovery-required.
3. Bind actual suspended worker PID/creation/image before resume; never reconstruct an image from expected journal fields.
4. Close with expected epoch/generation/token/parent/worker only after proven zero attempts, or exact owned-worker exit and qualified descendant disposition. Normal cleanup, native lease release and recovery closure are separate facts.
5. Any failed/ambiguous persistence, identity, wait, descendant or cleanup leaves ACTIVE/RECOVERY_REQUIRED. A finally-release may not erase this barrier.

Recovery is an internal exact expected-authority compare-and-swap operation. A stale generation/token cannot clear its successor. No PID-death, age, TTL, hostname, absent failure marker, broad kill or terminal restart clears uncertainty. Live-orphan identity may be observed on a fresh live handle as in Q1. A first already-dead recovery open lacking an independently observed live image remains blocked; late-dead liveness stays OPEN. There is no public/manual “force clear” in G03-A.

Cancellation may retain exact existing-job stop proof and cancel intent. It must not probe IPC, restart a terminal, declare restoration complete or settle the job as CANCELLED merely because a native worker PID is dead while admission/authority is unresolved. The central restore boundary must obtain compatible native admission before an effect; bounded unavailability returns an unresolved restore receipt. Read/status and MCP registration continue.

## Failure semantics, migration and rollback boundary

Reuse `LIVE_RECOVERY_REQUIRED` for this ownership denial and a sanitized phase/detail distinguishing marker/epoch/authority corruption, active unresolved ownership and normal lease contention. Successful historical output shapes, native request hashes and operation replay remain unchanged. A denied effect never claims terminal stopped, cleanup proven, a successful native run or account values. Existing job state schemas stay compatible; do not silently add a new terminal job state.

All guard-capable participants must use the same root/epoch and source version before activation. Old binaries ignore the new protocol. Deployment therefore requires coordinated quiescence, actual payload/version readback for A/B/C/controllers/workers, native idle evidence, verified state backup and an explicit migration route. Restoring an old payload/old epoch while ACTIVE is unsafe; retain barrier-aware code/state until exact reconciliation. A general backend checkpoint restore cannot migrate ownership state and its allowlist must not be expanded.

Power-loss durability, administrator tampering, arbitrary shell bypass and old-backup rollback protection are not established by atomic-replace fixtures. Record actual persistence limits and tested fault windows. Full product activation needs its own reviewed migration/rollback contract and physical evidence; G03-A may return a source foundation PASS with those gates OPEN.

## G04 and Q2 remain separate

Freshly checked first-party references still document that [MetaQuotes initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py) may start a terminal and expose no attach-only parameter. [Microsoft child-process attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute) require the corresponding sandbox/privileged-handle boundary. [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation) covers files and other processes' kernel objects. **Inference:** that isolation may also block the real SDK's IPC; fixture child denial alone cannot prove compatibility. These sources were reopened 2026-10-02.

The dependency `MetaTrader5>=5.0.6147` is a minimum, not an exact qualified SDK/wheel/DLL. [Q2 readiness](TIP-057R-Q2-readiness.md) specifies the next evidence package. No concrete disposable VM or pinned SDK/two-terminal manifest has been selected, so Q2 effects are not part of this approval. If compatible IPC cannot coexist with the preventive boundary, keep target IPC disabled and return to a product decision; do not broaden privileged handles/capabilities or weaken no-start to force a PASS.

## Proposed approval and task graph

| Slice | Proposed scope | Required before BUILD / activation |
|---|---|---|
| G03-A | Source/tests common authority, admission/stale removal and cancel-restore checks; exact internal recovery; helper/live_read disabled | Owner approves this specific amendment and its Builder TIP; source branch/PR only |
| G03-B | All relevant producer intent/cleanup integration and actual migration/rollback contract | Reviewed G03-A output plus concrete producer/boundary amendment; no implied deployment |
| Q2 | Disposable Python/SDK/MT5 compatibility and actual launch/race qualification | Exact reviewed VM/session/dependency/two-binding/effect manifest and separate execution decision |
| TIP-057R product read | Optional target, fleet.read/1 and qualified local observation | G03 producer/migration and G04 actual SDK proof; 14 contract ACs; client/two-binding physical gates |

The G03-A decision requested is **build source/tests and open a Draft implementation PR only**. It does not merge/ship, mutate current VPS/state, provision Q2, start/stop an MT5 installation or unlock M1/TIP-056. TIP-056 remains after TIP-060/M4; gateway and read-fleet ordering are unchanged. Contractor verifies G03-A outputs before any next concrete product/Q2 decision.
