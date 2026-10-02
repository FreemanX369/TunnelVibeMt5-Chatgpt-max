# Fleet v1 — Revised Task Graph

Status: **ACTIVE / M0 PASS**; TIP-055A code, fixture/read acceptance and actual local enrollment/backup/reload/inventory resource qualification verified. Dependencies express capability gates, not a requirement to change all files in one PR. See the [approval record](approval-2026-10-02.md), [Completion Report](TIP-055A-completion.md) and [actual enrollment checkpoint](TIP-055A-enrollment-qualification.md).

## TIP scopes and dependencies

| TIP | Output | Dependencies | Unlock / acceptance gate |
|---|---|---|---|
| TIP-055A | Local identity registry, inventory overlay, target vocabulary | Approved Blueprint | DONE for M0: code/read installation, actual stable IDs, verified backup/reload and five inventory QUALIFIED bindings |
| TIP-055B | Bounded existing lease-release liveness correction | Verified 055A source / issue #56 | DONE: actual Windows CI and guarded VPS compile/fixtures/refresh/readback PASS; no native routing |
| TIP-057R | Local targeted read path | 055A | Contract prepared; product BUILD blocked by shared cleanup ownership and strict no-start; later two-binding/client acceptance |
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

The owner approved the concrete [boundary amendment](TIP-057R-boundary-amendment.md) and [G03-A source/tests foundation](TIP-057R-G03A.md) at21:21:49, binding PR #61 head0ee42c9. Contractor dispatches Builder, verifies A01–A14 and publishes a separate Draft implementation PR stacked on #61. Common acquisition alone is insufficient: cancel restore, startup reconciliation and get_job reach IPC/restart, so the central effect boundary is included. G03-A does not activate SDK/helper/live_read or close full producer/migration G03. [Q2 readiness](TIP-057R-Q2-readiness.md) retains missing exact disposable environment/SDK/two-binding facts. Actual migration/deployment and Q2 remain separately reviewed gates.

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
