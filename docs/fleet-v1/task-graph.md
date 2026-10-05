# Fleet v1 — Revised Task Graph

## Deployment continuation — 2026-10-05

[TIP-065 fixture refinement](TIP-065-CI-refinement-completion.md): Builder and
independent verification DONE; candidate publication/8-workflow gate precede the
legacy overlay deployment. Original timeout causes and physical acceptance stay OPEN.

The owner now authorizes tests and deployment, superseding the earlier deployment
deferral. The accepted `f25ec99` source checkpoint passed eight workflows; 31 new
modules were staged with create-only CAS while the live TIP-053 adapter remained
unchanged. [TIP-065](TIP-065-deployment-preflight.md) adds narrowly necessary
read-only ownership/dependency observations through existing interfaces. Its own
delivered candidate still requires eight successful checks and independent artifacts.
The bounded legacy diagnostic overlay is a separate deployment slice. Full Fleet
activation remains gated by actual migration, protected configuration, process and
connector registration, and deferred physical MT5/SDK qualification.

## Continuous source execution — 2026-10-03

The latest owner direction authorizes all source tasks through M5 and 064 handover without per-TIP approval pauses; see [continuous authorization](continuous-build-2026-10-03.md). Private VM/real SDK tests remain deferred. This section supersedes historical source-dispatch timing gates below, while retaining their receipts and physical capability gates.

| Slice | Source output | Physical acceptance |
|---|---|---|
| 058A / 060C | DONE: [control](TIP-058A-completion.md), [all-head restore](TIP-060C-completion.md) | Actual singleton deployment/restore topology deferred |
| 057R / 058B / 059 / 062A | DONE: [SDK](TIP-057R-SDK-completion.md), [signed HTTPS/read fleet](TIP-058B-059-062A-completion.md) | Actual endpoint/two nodes/SDK reads deferred |
| 061A / 057N | DONE: [frozen project/STRICT/real native drivers](TIP-061A-057N-completion.md) | Dedicated tester/process/session qualification deferred |
| 060 / 056 | DONE: [jobs/artifacts](TIP-060-completion.md), [signed scoped resources](TIP-056-completion.md) | Physical restart/concurrency/load qualification deferred |
| 061B / 063 | DONE: [guarded writer](TIP-061B-completion.md), [real Git worktrees](TIP-063-worktrees-completion.md) | Physical multi-client/worktree execution deferred |
| 064 | DONE source: [composition/startup](TIP-064-completion.md), complete Linux/Windows workflow and [handover](source-handover.md); delivered head requires eight successful checks | User tests after source build |

Concrete source and Builder tests are complete. [Contractor verification](source-update-verification.md) records the delivered-head acceptance criteria and retained checkpoint receipts. New native/SDK effects remain gated by exact trusted physical evidence; source fixtures do not authorize them. The following status/history records earlier milestones and does not supersede this current source table.

Status: **ACTIVE / M0 PASS**; TIP-055A code, fixture/read acceptance and actual local enrollment/backup/reload/inventory resource qualification verified. Dependencies express capability gates, not a requirement to change all files in one PR. See the [approval record](approval-2026-10-02.md), [Completion Report](TIP-055A-completion.md) and [actual enrollment checkpoint](TIP-055A-enrollment-qualification.md).

## TIP scopes and dependencies

| TIP | Output | Dependencies | Unlock / acceptance gate |
|---|---|---|---|
| TIP-055A | Local identity registry, inventory overlay, target vocabulary | Approved Blueprint | DONE for M0: code/read installation, actual stable IDs, verified backup/reload and five inventory QUALIFIED bindings |
| TIP-055B | Bounded existing lease-release liveness correction | Verified 055A source / issue #56 | DONE: actual Windows CI and guarded VPS compile/fixtures/refresh/readback PASS; no native routing |
| TIP-057R | Local targeted read path | 055A | B1 research build PASS; C1 request/validation source PASS with permanent targeted IPC denial; shared cleanup integration/no-start and later two-binding/client acceptance remain OPEN |
| TIP-058 | Singleton gateway + outbound node enrollment | 055A; 057R before targeted-read acceptance | TLS/enrollment/replay/revoke/restart; actual endpoint and worker capability contract |
| TIP-059 | Remote targeted read fleet | 057R + 058 | Exact node/terminal attribution, scoped failures, bounded deadlines and restart/reconnect |
| TIP-062A | Minimal fleet snapshot | 059 | Partial coverage/freshness; per-target account values; no totals or heavy auto-captures |
| TIP-061A | Project/iteration target contract and STRICT baseline | 055A + 058 | Frozen target and writer authority before managed routed jobs; native remains fixed until 057N |
| TIP-057N | Local native routing and end-to-end provenance | 057R + 061A | Serialized dedicated tester; worker/result/baseline/cancel/capture boundaries qualified |
| TIP-060 | Durable remote native jobs and artifact proxy | 059 + 057N + 061A | Same-node inputs; capacity 1 per node; operation collision/replay/start/ACK/commit/recovery gates |
| TIP-056 | Qualified terminal-scoped native concurrency | 060 | [Readiness review complete](TIP-056-readiness.md); BUILD gated by target/journal/resource reservations and measured loaded Windows qualification |
| TIP-061B | Remote guarded source mutation | 060 | Single project writer, exact checkpoint/source CAS, operation transport and recovery fencing |
| TIP-063 | Multi-agent task isolation | 061B + 060 | Verified principal ownership and Git worktree; no duplicate Continuity system |
| TIP-064 | Final fleet release qualification | Every capability included in the selected release | Scope-bound fault/load/soak/migration/restore evidence on exact candidate |

Current execution checkpoint: PR #54/#55/#57/#58/#59 merged; M0 installation and bounded lease correction qualified; issue #56 closed. Explicit 12:07 PowerShell authorization now has [actual enrollment receipts](TIP-055A-enrollment-qualification.md): all five rows ENROLLED/QUALIFIED, stable generation/revision1, verified backup/reload and native routing false. [TIP-056 readiness](TIP-056-readiness.md) remains M4 after TIP-060. The 13:36 continuation completes [TIP-057R contract](TIP-057R-contract.md) preparation and [Builder feasibility](TIP-057R-feasibility.md); shared recovery and strict no-start still block usable target IPC. The historical next proposal was [TIP-057R-Q isolated Windows boundary proof](TIP-057R-boundary-proposal.md); its later bounded Q1 approval and scoped result are recorded below. No roadmap ordering or capability unlock changed.

The original numbering is retained with R/N or A/B subdivisions where scope was ambiguous. TIP-056 is deliberately moved after remote serialized jobs. The original TIP-061 is split so target/baseline correctness precedes jobs while remote source writes remain later. TIP-062 advanced totals/filtering are not implied by 062A and need their own approved requirement.

At 13:59:50 the owner approved the concrete [TIP-057R-Q1 isolated Windows proof](TIP-057R-Q1.md). The current scoped result in [Draft PR #61](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/61) is **PARTIAL / FIXTURE_PASS_Q03_OPEN**: seventh source candidate `bd3007a360abfc9e3b273f2988b8b4e251d12041` passes all 16 real Windows tests without failures/errors/skips and all four baseline workflows. Six unsuccessful receipts and the successful source receipt are preserved in [Contractor verification](TIP-057R-Q1-verification.md). Applicable fixture restriction, direct launch control/denial, all five faults and ownership/recovery cases are verified. Final documentation-head CI will be checked and confirmed in the PR before task return. SDK/broker/uncontained paths, breakaway causality, no-console startup, fresh already-dead recovery, production G03/G04 and Q2 remain OPEN. Q1 evidence prepares the next reviewed product boundary decision; M1 capability, TIP-056 after TIP-060 and delivery order are unchanged.

## Delivery order

The owner approved the concrete [boundary amendment](TIP-057R-boundary-amendment.md) and [G03-A source/tests foundation](TIP-057R-G03A.md) at 21:21:49, binding PR #61 head `0ee42c9`. Builder implementation and Contractor A01–A14 verification now give **G03-A FOUNDATION PASS** in separate [Draft PR #62](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/62), source `bc916796`: six workflows PASS, G03-A Windows 8/8 and Q1 16/16 without skips, full Windows 424 PASS/4 existing skips. See [Completion Report](TIP-057R-G03A-completion.md) and [verification](TIP-057R-G03A-verification.md). Common acquisition and central cancel/get_job/startup restore exclusion are implemented. Full producer/cleanup integration and migration remain OPEN; G03-A does not activate SDK/helper/live_read. [Q2 readiness](TIP-057R-Q2-readiness.md) retains missing exact disposable environment/SDK/two-binding facts. Actual migration/deployment and Q2 remain separately reviewed gates.

The owner continues the stated next **G03-B contract step** at 22:56:16 against verified docs head `08835894`. [Producer scan](TIP-057R-G03B-source-scan.md), [feasibility](TIP-057R-G03B-feasibility.md) and [decision contract](TIP-057R-G03B.md) complete B0 preparation: proposed owned isolated SDK worker, exact Q2 manifest and compatibility research before broad supported producer integration, then separately qualified physical migration. Q2 may use frozen isolated fixtures before product integration; this avoids a dependency cycle and does not unlock targeted reads. All new G03-B ACs are PLANNED, not executed. The next decision is architecture/preparation direction; no product/helper BUILD or unknown Q2 effects are dispatched.

M0 = 055A. M1 = 057R + 058 + 059 + 062A. M2 = 061A + 057N. M3 = 060. M4 = 056. M5 = 061B + 063. Release = 064 for the capabilities selected for shipping.

058 transport work may proceed once 055A is verified and its own spec is approved; end-to-end targeted-read acceptance waits for 057R. 061A design may proceed after its dependencies; it must be verified before opening managed native routing. Delivery remains incremental, and each TIP returns a separate Completion Report.

Read-fleet pilot can be delivered before native or multi-agent work. Such delivery is certified only as read fleet. If the owner selects a smaller release scope, document it in the ledger and Blueprint; do not pretend unbuilt roadmap capabilities passed 064. The full big-update completion requires all included requirements and the final chosen physical topology.

## GitHub workflow

- The Blueprint documentation was approved at `063d6a3` and merged through PR #53. The [approval record](approval-2026-10-02.md) records its exact scope.
- After explicit approval, record exact Blueprint commit/owner statement and implement 055A in an implementation branch/PR based on the latest compatible main. No direct commit to main.
- Later implementation PRs reference their approved TIP, REQ/AC IDs and exact base. Dependency PRs are merged only after verification and the owner's authorized scope supports it.
- Update the planning index with actual status/receipts; future task outlines are not marked DONE merely because their docs exist.
- Preserve failed/superseded evidence. Deployment requires an exact reviewed head, rollback anchors and applicable local/Windows/client gates.

## Builder report for every TIP

Report `DONE | PARTIAL | BLOCKED`, files changed, each AC's PASS/FAIL/evidence, issues with severity, deviations and suggested follow-up. Distinguish mock/Linux CI, Windows fixtures and physical MT5 acceptance. Contractor validates requirement coverage before capability unlock. Architecture changes are suggestions until approved; no unreviewed rewrite of gateway, project authority or target semantics.


## 2026-10-03 B1 source-build sequencing continuation

At 00:12:01+07:00 the owner deferred private VM testing and directed source build first. This supersedes the earlier Q2-before-source order for [bounded B1](TIP-057R-B1-build.md) only. The proof-only isolated SDK state/account worker, protocol and harmless Windows stub are built under [the B1 report](TIP-057R-B1-completion.md); original environment slots stay unfilled, SDK/Q2/no-start/production descendants, G03-B integration, migration and activation remain OPEN. The SDK CLI denies effects; no product/native legacy behavior is changed. Source/stub CI is separate from the later actual private VM qualification.

## 2026-10-03 C1 product source continuation

The owner's next continuation approves [bounded C1](TIP-057R-C1-build.md) after verified B1 Draft #63 head `5583204f698dcbf664ad20ddae8106d96019c8d2`. C1 is PRODUCT SOURCE PASS in Draft #64 source `9ec22fec`: the two selected reads gain optional target and strict fresh local identity validation with a fleet.read/1 failure receipt. [Completion](TIP-057R-C1-completion.md) and [Contractor verification](TIP-057R-C1-verification.md) record 62 focused cases, Linux 464/26 platform skips, Windows 486/4 existing skips and seven successful source workflows. Inventory resolution is not live_read authorization; resolved targets permanently deny LIVE_ATTACH_ONLY_UNPROVEN before process/SDK access. Legacy/null and other native contracts are retained. This source step needs no private VM effects and does not change the selected isolated-worker architecture or authorize transport policy invention. Q2, actual client/schema exposure, positive targeted IPC, producer integration/migration, no-start and M1 remain OPEN.
