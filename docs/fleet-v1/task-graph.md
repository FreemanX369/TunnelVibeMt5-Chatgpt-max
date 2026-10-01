# Fleet v1 — Revised Task Graph

Status: planning draft, activated only by explicit Blueprint approval. Dependencies express capability gates, not a requirement to change all files in one PR.

## TIP scopes and dependencies

| TIP | Output | Dependencies | Unlock / acceptance gate |
|---|---|---|---|
| TIP-055A | Local identity registry, inventory overlay, target vocabulary | Approved Blueprint | M0 IDs stable; legacy behavior intact; only executable TIP in this package |
| TIP-057R | Local targeted read path | 055A | Two distinct physical bindings, exact IPC roots, serialize lifecycle; no native routing |
| TIP-058 | Singleton gateway + outbound node enrollment | 055A; 057R before targeted-read acceptance | TLS/enrollment/replay/revoke/restart; actual endpoint and worker capability contract |
| TIP-059 | Remote targeted read fleet | 057R + 058 | Exact node/terminal attribution, scoped failures, bounded deadlines and restart/reconnect |
| TIP-062A | Minimal fleet snapshot | 059 | Partial coverage/freshness; per-target account values; no totals or heavy auto-captures |
| TIP-061A | Project/iteration target contract and STRICT baseline | 055A + 058 | Frozen target and writer authority before managed routed jobs; native remains fixed until 057N |
| TIP-057N | Local native routing and end-to-end provenance | 057R + 061A | Serialized dedicated tester; worker/result/baseline/cancel/capture boundaries qualified |
| TIP-060 | Durable remote native jobs and artifact proxy | 059 + 057N + 061A | Same-node inputs; capacity 1 per node; operation collision/replay/start/ACK/commit/recovery gates |
| TIP-056 | Qualified terminal-scoped native concurrency | 060 | Resource conflicts/capacity reservations/shared legacy locks; measured loaded Windows qualification |
| TIP-061B | Remote guarded source mutation | 060 | Single project writer, exact checkpoint/source CAS, operation transport and recovery fencing |
| TIP-063 | Multi-agent task isolation | 061B + 060 | Verified principal ownership and Git worktree; no duplicate Continuity system |
| TIP-064 | Final fleet release qualification | Every capability included in the selected release | Scope-bound fault/load/soak/migration/restore evidence on exact candidate |

The original numbering is retained with R/N or A/B subdivisions where scope was ambiguous. TIP-056 is deliberately moved after remote serialized jobs. The original TIP-061 is split so target/baseline correctness precedes jobs while remote source writes remain later. TIP-062 advanced totals/filtering are not implied by 062A and need their own approved requirement.

## Delivery order

M0 = 055A. M1 = 057R + 058 + 059 + 062A. M2 = 061A + 057N. M3 = 060. M4 = 056. M5 = 061B + 063. Release = 064 for the capabilities selected for shipping.

058 transport work may proceed once 055A is verified and its own spec is approved; end-to-end targeted-read acceptance waits for 057R. 061A design may proceed after its dependencies; it must be verified before opening managed native routing. Delivery remains incremental, and each TIP returns a separate Completion Report.

Read-fleet pilot can be delivered before native or multi-agent work. Such delivery is certified only as read fleet. If the owner selects a smaller release scope, document it in the ledger and Blueprint; do not pretend unbuilt roadmap capabilities passed 064. The full big-update completion requires all included requirements and the final chosen physical topology.

## GitHub workflow

- This first PR contains Blueprint documentation only and remains Draft until reviewed.
- After explicit approval, record exact Blueprint commit/owner statement and implement 055A in an implementation branch/PR based on the latest compatible main. No direct commit to main.
- Later implementation PRs reference their approved TIP, REQ/AC IDs and exact base. Dependency PRs are merged only after verification and the owner's authorized scope supports it.
- Update the planning index with actual status/receipts; future task outlines are not marked DONE merely because their docs exist.
- Preserve failed/superseded evidence. Deployment requires an exact reviewed head, rollback anchors and applicable local/Windows/client gates.

## Builder report for every TIP

Report `DONE | PARTIAL | BLOCKED`, files changed, each AC's PASS/FAIL/evidence, issues with severity, deviations and suggested follow-up. Distinguish mock/Linux CI, Windows fixtures and physical MT5 acceptance. Contractor validates requirement coverage before capability unlock. Architecture changes are suggestions until approved; no unreviewed rewrite of gateway, project authority or target semantics.
