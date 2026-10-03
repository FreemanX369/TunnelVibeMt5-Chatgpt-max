# TIP-060 / 056 — Durable remote job and resource authority

Status: DISPATCHED for source build, dependencies 059/057N/061A then 060. Physical concurrency qualification stays open. Continuous source authorization removes per-TIP approval stops.

YAGNI-3: remote effects need crash-stable identity and scoped evidence; reuse SQLite WAL/OS lock, existing local JobStore and artifact hashes; add finite gateway/node journals and one atomic resource reservation rather than generic scheduling.

## 060 acceptance

* Gateway persists global operation -> immutable target -> node operation/job mapping before delivery; node persists intent/reservation before native effects. Canonical `fleet.native/1` request is separate from unchanged legacy index. Same logical operation/request returns original mapping, changed input/target/config conflicts after restart. No newly resolved default on retry.
* Explicit versioned transitions QUEUED/DELIVERED/RESERVED/STARTING/RUNNING/RESULT_PENDING/terminal plus UNKNOWN/RECOVERY_REQUIRED; CAS sequence and route/session fences. ACK proves delivery only. Crash/lost ACK/start/result/commit windows never permit another native start on timeout; recorded node intent prevents duplicates and blocks uncertain repeat. Revoke blocks new start; late evidence is retained/quarantined. Agent/heartbeat loss does not kill existing native workload.
* Supported restore fences dispatch until signed node journal/high-water witnesses reconcile mappings; never DB-only claim old-backup detection or a boolean mark-ready. No unconditional clear/force-reset. Unknown journal outcomes remain unknown. Old logical receipt capacity is not evicted to allow duplicates.
* Cancellation is an idempotent bound command requiring exact job/process creation identity/executable through node core; transport cannot infer stop from ACK or fabricate process authority.
* Immutable artifact manifest/chunk read is scoped to node/global job/local job/target/hash/size and safe registered artifact ID; no arbitrary Windows-path URL. Validate chunks/ranges/total hash, traversal/cross-node/wrong job/changed bytes quarantine. Reading evidence must not call get_job restoration or native handoff. Reuse core immutable primitives where safe.
* Tests: gateway+node durable restart, operation collision, failure before/after every irreversible boundary, lost ACK/outcome UNKNOWN, no double callback, restore journal reconciliation, late revoked result, cross-node artifacts and hash corruption. Synthetic native adapter success explicitly labeled.

## 056 acceptance

* Conflict matrix includes compiler deploy, tester, IPC, capture, executable/data/include roots, local agent resources. Atomically reserve device capacity and normalized full physical-resource set in one transaction, deterministic ordering and fair bounded queue. Capacity remains 1 by default production profile until measured physical qualification.
* Alias/canonical-root equivalence cannot be certified from string difference. Unproven independence blocks parallel admission; legacy and routed MT5-2 share common native authority. No independent resource namespace double-booking. Release requires actual exact closure receipt, never heartbeat/TTL/free-RAM check. Uncertain ownership survives restart and blocks reuse.
* Source tests exercise capacity/overlap/order/concurrent writers/fault/uncertain closure without physical qualification claims. Supply a measured Windows qualification plan for later user test.

Builder owns new journal/artifact/resource modules and their tests/reports; coordinate A store, B transport and M2 request/native adapter. No remote Git mutations or actual MT5 effects.

Independent review clarification: node requires a fresh bounded gateway start authorization for the exact route/session/request immediately before durable start intent/effect, and checks local generation/binding again under common authority. Revoke linearizes against gateway authorization; an already authorized in-flight start on a subsequently disconnected node is an unresolved revocation window, not a guarantee of instantaneous remote physical prevention. Retain UNKNOWN/quarantine evidence rather than pretending the node observed an unavailable route update. No timeout grants a new effect.
