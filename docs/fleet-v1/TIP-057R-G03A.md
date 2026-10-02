# TIP-057R-G03A — Common ownership foundation

Status: **PROPOSED / NOT DISPATCHED**. Requires owner approval of the [boundary amendment](TIP-057R-boundary-amendment.md), retained Q1 evidence and compatible source at main `70e2112da9fe8eaa6262f2ba896b55bf3e078260` / Draft PR #61 `9fcb86fc7bf061ba9fceb1eb2948e6290cbf8701`. Priority: next G03 prerequisite. Maps REQ-F10/F11/F15 and preparatory F04. Proposed deliverable: source/test implementation in a separate Draft PR, without production activation. Planning approval is not implementation authorization until the concrete amendment is accepted.

## Context and task

Working checkout: `/workspace/scratch/250985b4823e/tip057rq-work`. Contractor owns design, dispatch and output review; Builder owns implementation, meaningful tests and Completion Report.

Key reuse: `core/concurrency.py`, `core/jobs.py`, `worker.py`, `core/facade.py`, `adapters/mcp.py`, existing concurrency/cancellation/runtime-forensics unit fixtures and Q1's harmless Windows proof. Current source has no real IPC helper. Do not import a proof/test module from runtime or copy Q1's two-file generation/intent protocol unchanged into product.

Implement the smallest product authority and common admission/recovery exclusion in the amendment. A valid CLOSED installation permits ordinary existing effects under the shared native lease. ACTIVE, incomplete, invalid or uninstalled authority prevents new conflicting effects, including stale lock removal and central cancel-restore IPC/restart. Actual producer callbacks/helper/SDK initialization are not introduced by this TIP. The future producer state-machine interface is tested only with harmless fixtures.

YAGNI-3 is recorded in the amendment: required common exclusion, existing locking/persistence/process/job reuse, one authority module and minimal integration points. Builder must repeat the answers against the final implementation before writing code.

## Acceptance criteria

These are **PLANNED / NOT RUN**. Test names below describe required results, not existing files.

| AC | Given / When / Then | Required evidence |
|---|---|---|
| A01 | Given an explicitly installed READY/CLOSED test root, when ordinary callers acquire/release, then FIFO, capacity 1, mutation→native ordering and historical successful outputs remain compatible | Product concurrency methods, two-process contention and named legacy regression receipts |
| A02 | Given ACTIVE/unresolved authority, when facade live/market/chart, direct/iteration compile, direct Strategy Tester acquire or existing backend native acquire is attempted, then no effect callback runs | Production entry-path tests; mock SDK/compiler/tester/PowerShell callback counts exactly zero |
| A03 | Given unresolved authority and a cancel job requiring restore, when cancel, get_job or MCP startup reconcile reaches restore, then no MT5Preflight/restart runs, cancel intent remains pending and read/status/server registration remain usable | Tests against JobManager central restore and actual startup/read call chain, not only a facade wrapper |
| A04 | Given dead/PID-reused lease owner and ACTIVE authority, when stale cleanup runs, then it cannot delete the unresolved authority or native lock or admit a successor | Common acquisition/stale-removal transaction tests and harmless actual process identity |
| A05 | Given missing/corrupt/unsupported marker or authority, epoch mismatch or interrupted migration, when native admission runs, then it denies without lazy reset while diagnostics remain bounded | Fault injection at every publication window; explicit single/both-file loss and unsupported version cases |
| A06 | Given future-producer intent, when no attempt fails versus committed create-attempt crashes before binding, then zero-attempt closure is distinct from unknown creation; no guessed worker reference | Product authority interface with harmless worker/create controls; actual arm/create/bind/resume ordering |
| A07 | Given racing recovery/acquire and a successor generation, when stale expected epoch/token/owner attempts close, then stale CAS rejects and no two callers overlap | Multiprocess admission and recovery race; assert child/thread failures propagate to the test |
| A08 | Given a fresh already-dead process without independently captured live image, when recovery checks identity, then blocker remains; expected journal image cannot supply missing OS evidence | Real Windows refusal plus source/path review; live-orphan case remains separate |
| A09 | Given installation/migration publication crash or an old-epoch restore simulation, when restarted, then uncertainty persists and generation is not reset | Durable snapshot tests with MIGRATING/READY and matching/mismatching epochs |
| A10 | Given no new helper or qualified SDK path, when source/tool surface is inspected, then target/live_read remain unavailable; native signatures, request hashes, catalog and dependencies are unchanged | Diff/import/catalog/schema assertions; no new public recovery/force-clear API |
| A11 | Given an existing job's exact stop proof, when ownership blocks restoration, then exact job termination and cancel intent are not mistaken for successful restoration or full ownership closure | Existing cancellation/provenance regressions and explicit pending restore reason |
| A12 | Given ordinary finally-release or unlink while authority is ACTIVE, when release completes/fails, then unresolved durable state survives and another caller remains blocked | Product context manager and worker release paths; fault/readback proof rather than a synthetic success flag |
| A13 | Given short authority transaction guard and existing native/mutation locks, when contention/recovery occurs, then no FIFO/native wait or SDK effect is performed under the authority guard | Lock-order review and bounded process/race tests; record actual elapsed, no hard deadline claim |
| A14 | Given exact reviewed source candidate, when verified, then required Windows authority/process tests execute without skip-as-PASS, baseline/Q1 evidence remains retained and every changed contract is reported | Exact-head Windows source/hash/log/artifact receipt plus existing CI and meaningful named regressions |

Keep the old dead-PID auto-recovery test's valid CLOSED/no-unresolved case, and add strict ACTIVE/invalid cases. Existing fixtures and Q1 may need explicit test-root installation setup under the new source; declare such changes and preserve their original behavioral assertions/failed historical receipts. Do not add an absent-marker fallback, skip a required Windows case or silently disable a test to make CI pass.

## Boundaries and report

Allowed after amendment approval: product authority/admission/cancel-restore source, narrowly necessary diagnostics, meaningful tests/fixture initialization and dedicated Windows verification if existing CI cannot enforce the required no-skip cases. Builder reports exact files and preserves unrelated source behavior.

No runtime SDK/helper, optional target activation, public recovery API, gateway, remote routing, concurrency increase, terminal ACL alteration, package version/dependency change, production settings/state migration, deployment, MT5/VPS/account/chart/credential/AutoTrading action, generic PowerShell call, merge or old-evidence reset. Keep native capacity 1. Runtime-forensics job capture is a separate existing authority; do not take another native lease around active-job snapshots and create a deadlock.

The default native denial on uninstalled guard-capable source is an intentional compatibility/migration change, not a hidden startup side effect. Tests initialize only disposable roots. Production migration, all-participant upgrade fencing and rollback must be reviewed separately before activation; old binaries cannot be fenced by this new JSON protocol.

Return a Completion Report with DONE/PARTIAL/BLOCKED for this bounded TIP, YAGNI answers, files, A01–A14 results, exact source/head/platform hashes, test/skip counts, limitations, deviations and suggestions. A successful result may be labeled **G03-A FOUNDATION PASS**. G03 full producer/cleanup integration, late-dead recovery liveness, physical migration and G04/Q2 stay OPEN. Contractor verifies each AC and the legacy denial exception before considering the next slice.
