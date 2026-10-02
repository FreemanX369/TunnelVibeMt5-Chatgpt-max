# Fleet v1 — Requirements, RRI synthesis and decision ledger

Status: **APPROVED DIRECTION / M0 QUALIFIED / TIP-057R CONTRACT PREPARED**, per the [owner approval record](approval-2026-10-02.md), [Completion Report](TIP-055A-completion.md) and [actual enrollment receipts](TIP-055A-enrollment-qualification.md). TIP-055B has [actual Windows CI and guarded deployed qualification PASS](TIP-055B-runtime-qualification.md). [Selected read contract](TIP-057R-contract.md) specifies schema/ACs and local soft budget; shared recovery and strict attach-only remain unresolved. No answer below is attributed to an interview that did not occur.

## Five-persona RRI synthesis

| Persona | Need already present in the plan/discussion | Contractor proposal |
|---|---|---|
| End user | Inspect all VPS/MT5 and choose exact execution machine | Read fleet first, one domain catalog, explicit target/freshness |
| Business analyst | Incremental value without rewriting the existing MT5 product | M0/M1 bounded delivery; generic infrastructure deferred |
| QA | Prove correct target, replay/recovery and retained evidence | REQ-to-AC mapping, negative cases and physical gates per milestone |
| Developer | Reuse domain core without copying unsafe RemoteMCP assumptions | Add identity overlay; keep legacy execution; version later routing contracts |
| Operator | Reboot/reconnect, resource control, live account continuity | Singleton gateway; session capabilities; dedicated tester; exact rollback |

This compressed RRI reuses the supplied requirements rather than repeating a large interview. Strategic proposals are submitted together with the Blueprint. Unknown physical inventory and service endpoint are left as explicit gates, not guessed answers.

## Requirements matrix

| REQ | Required output | Delivery / verification reference |
|---|---|---|
| REQ-F01 | Durable IDs separate from alias/hostname/build; binding generations explicit | 055A AC-01–06, AC-08–09 |
| REQ-F02 | Fixed MT5-2 compatibility until routed native qualification; old evidence readable | 055A AC-07, AC-10–13; release migration |
| REQ-F03 | One gateway authority and outbound enrolled nodes | 058; duplicate gateway/enrollment and TLS/replay gates |
| REQ-F04 | Exact targeted live reads with per-node IPC protection | 057R/059; binding mismatch and concurrent observation gates |
| REQ-F05 | Partial, bounded fleet snapshot with honest freshness/coverage | 059/062A; offline, deadline and stale-cache tests |
| REQ-F06 | Frozen target and no fallback for native jobs | 061A/057N/060; requested=executed and stale generation gates |
| REQ-F07 | Global/node operation identity survives retries/restarts | 060; start/ACK/commit crash and conflicting request tests |
| REQ-F08 | Exact job/process cancellation and hash-bound artifact routes | 057N/060; PID reuse, cross-job and artifact substitution tests |
| REQ-F09 | Target-aware project resume, baseline and single-writer Continuity | 061A; drift/missing evidence/revision CAS tests |
| REQ-F10 | Safe Windows session and tester role; no implicit account/AutoTrading changes | 057R/057N; readiness, handoff and recovery gates |
| REQ-F11 | Capacity/locks follow real resources without double-booking legacy path | 056; conflict matrix and reserved-capacity/fairness tests |
| REQ-F12 | Remote guarded writes preserve checkpoint/CAS and fencing | 061B; original authority at normal/recovery writes |
| REQ-F13 | Multi-agent isolation without forged caller ownership | 063; verified principal/session/epoch and worktree tests |
| REQ-F14 | Additive catalog/contracts visible to the actual client | 055A AC-12; each new tool/client acceptance gate |
| REQ-F15 | Migration, rollback, backup/restore and qualification bound to exact head | All TIPs / 064; verification-and-release contract |
| REQ-D01 | Cross-device immutable input transfer | DEFERRED; requires a separate bundle/receipt TIP |
| REQ-D02 | Account-deduplicated currency totals | DEFERRED; minimal snapshot is per-target only |
| REQ-D03 | Generic Repo Worker / pool / non-Git leases | DEFERRED; new scope after measured need |

## Proposed decisions linked to the original D-01 → D-12

D entries establish the approved direction and choices within the recorded approval scope; O entries list details still required at the affected milestone. The approval record binds the original package to its exact reviewed commit. Future milestone details remain gated rather than invented.

| ID | Proposed choice | Reason and boundary | Affects |
|---|---|---|---|
| D-01 | Singleton persistent gateway; separate A/B/C MCP adapter clients | Preserve current connector topology; one scheduling/registry authority | M1+ |
| D-02 | Local persisted opaque device ID in M0; authenticated Ed25519 enrollment in 058 | Separate stable identity from key ownership and labels | 055A/058 |
| D-03 | Gateway route_generation + node terminal_generation; no synonyms | Explicit fencing authorities; no M0 fake route epoch | All routing |
| D-04 | Immutable placement after reservation/commit; no fallback | Preserve target meaning and replay identity | 061A/057N/060 |
| D-05 | Native capacity 1 per node through M3; scoped concurrency after qualification | Fleet value does not require same-node parallelism | 056 later |
| D-06 | MVP repo/executor same node; bundle transfer deferred | No implicit source/config sync or duplicate writer | 061A/060 |
| D-07 | One STRICT baseline policy first; explicit compatibility analysis separate | Close equivalence before multiplying policies | 061A |
| D-08 | Per-target partial reads, source/time/coverage; no equity totals initially | Avoid duplicate/cross-currency arithmetic | 059/062A |
| D-09 | Local atomic M0 identity registry; SQLite WAL gateway with consistent backup | Use the smallest persistence needed at each scope | 055A/058/060/064 |
| D-10 | Continuity retained; Git worktree + verified ownership after jobs | Fencing supplements semantic history | 063 |
| D-11 | Two-node pilot; actual target IDs and readiness must be registered | Example VPS/build labels are not real inventory | M1–M3 |
| D-12 | Gates at each milestone; final physical scope/load-bound qualification | A 60-minute duration is not an acceptance definition | All / 064 |
| D-13 | Project writer remains on owner node; gateway only routes/references it | Avoid split-brain project state | 061A/061B |
| D-14 | Native worker/session capability distinct from gateway/node online status | Current tester rejects Session 0 | 058/057N |
| D-15 | Dedicated tester role by default; live handoff separately authorized/qualified | Avoid silently interrupting live EA | 057N |
| D-16 | Node operation journal + UNKNOWN outcome; no unconditional native retry | Preserve evidence when start/ACK outcome is ambiguous | 060 |
| D-17 | M0 inventory-only identity enrichment; no job/hash/result rewrite | Isolate the first change and preserve idempotency/history | 055A |
| D-18 | Prepare optional local target on only state/account; preserve legacy successful shape | Concrete [contract](TIP-057R-contract.md), not implemented or client-qualified | 057R |
| D-19 | Local10s soft-success budget; do not claim hard response/cancellation | Exact overrun/cleanup ownership is recorded; TIP-059 total deadline stays separate | 057R contract |
| D-20 | Strict no-start retained; restricted helper is pending proof/owner review | Existing initialize has no supported attach-only guarantee; [Q1 proposal](TIP-057R-boundary-proposal.md) is not approved architecture | 057R G03/G04 |

## Open gate register

No open item below blocks writing/reviewing this package. Only items for the TIP being dispatched block its implementation or deployment.

| Open ID | Concrete information/specification needed | Required before |
|---|---|---|
| O-01 | CLOSED: owner approved revision 063d6a3; future amendments require their own record | 055A authorized |
| O-02 | Public gateway host/provider, TLS identity, singleton service owner and provisioning/backup location | 058 deployment |
| O-03 | Exact pairing, canonical signing, clock skew/nonce retention, key rotation and clone/revoke tests | 058 build |
| O-04 | Actual two pilot nodes, distinct roots, Windows sessions and tool visibility | M1 physical acceptance |
| O-05 | Snapshot deadlines, freshness policy, row/payload/fan-out limits | 059 build |
| O-06 | Project target migration, baseline/environment fields and native build drift policy | 061A/057N build |
| O-07 | Durable command state transitions, legacy/new request-hash versioning, journal retention and backup restore | 060 build |
| O-08 | Artifact/BIN/capture mapping and gateway resource/widget delivery spec | 060 build |
| O-09 | Conflict matrix, capacity reservation, lock ordering and measured resource/latency/fairness thresholds | 056 build |
| O-10 | Remote source-guard transport, recovery fencing and verified caller principal model | 061B/063 build |
| O-11 | Physical topology, test workload, soak/performance/recovery thresholds and release/deploy scope | 064 qualification |
| O-12 | Shared uncertain-IPC ownership/recovery mechanism and preventive attach-only boundary; review concrete Q1 proposal | 057R product BUILD; Q1 itself awaits architecture decision |

TIP-057R G02-schema preparation is complete; G02 actual client/pilot remains a later acceptance gate. Local soft-budget selection does not imply hard deadline qualification. G03-ownership/G04 remain OPEN, not paperwork gates or reasons to manufacture successful account reads. The original Blueprint architecture and product policy are unchanged.

Builder resolves implementation choices within an approved contract. Missing architecture/authority/policy is escalated to Contractor; a scope/security/product-policy change returns to the owner with a concrete proposal.
