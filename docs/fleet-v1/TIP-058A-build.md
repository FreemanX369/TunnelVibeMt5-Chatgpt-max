# TIP-058A — Durable singleton gateway control state

Date: 2026-10-03, Asia/Saigon. Status: DISPATCHED. Parent #64 `e74bdee81db3db3d5ae774a99a9146d74742ea8a`. REQ-F03/F15; approved Blueprint D01/D02/D03/D09. [Continuous source authorization](continuous-build-2026-10-03.md) permits this independent M1 foundation while actual SDK/VM tests remain deferred.

## YAGNI-3 and scope

Gateway enrollment/routing/replay needs durable transactional control state before transport. Reuse stdlib SQLite WAL/backup and the existing OS `_exclusive_file_lock` for one canonical control resource throughout writer lifetime. Implement one concrete internal control store and focused tests. No service framework, native/SDK effect, public admin MCP, caller-provided authenticated flag, private-key storage or claim of cryptographic enrollment from IDs/key equality.

This slice accepts trusted internal control operations. Subsequent TIP-058B verifies Ed25519/TLS/admin scope before exposing them to requests. Public-key references are shape-checked persisted data, not verified key-possession evidence. All limits/times used by the store must be explicit required Policy inputs with strict primitive types; no production numeric profile is selected here. Fixture policy is synthetic. Reject mismatched policy on reopen instead of changing retention/authority silently.

## Acceptance criteria

| AC | Required output |
|---|---|
| A01 | Explicit initialize/open-existing/close/snapshot. Missing/corrupt/unknown schema never auto-bootstrap. Canonical control path, lifetime reused OS lock and bounded explicit SQLite/lock waits; second cooperative writer denied, process crash releases OS lock without PID/TTL guessing. |
| A02 | Transactional versioned SQLite WAL state with device/public-key control records, grants, route generations, nonces and operation receipts. Initialization all-or-none; strict IDs/generations/key reference/input sizes. Node terminal_generation is not owned or rewritten by gateway. |
| A03 | Explicit validated policy, safe bounded capacities for devices/grants/nonces/operation receipts and waits/timestamps. Missing/bool/nonfinite/invalid relationships rejected. Policy mismatch/corrupt state fails closed. |
| A04 | Issue expiring grant bound to exact device/key/current route expectation. Only secret digest persists; plaintext secret returned only on initial issue, never in public receipts/diagnostics. Consume and route update commit atomically; expired/used/wrong-device/key/stale-CAS grant fails without partial state. Lost secret is not fabricated from digest on replay. |
| A05 | Administrative operation/request identity is durable: identical retry returns committed public receipt after reopen, changed request conflicts. Replay lookup precedes mutable current-CAS checks. Capacity cannot evict a committed operation to authorize duplicate effects. |
| A06 | Initial pairing route_generation=1. Re-pair/revoke/key-reference rotation fence prior generation by increment; query/reopen retains it. Rotation requires expected current key and route CAS, identity retained. Reconnect/key possession/physical clone uniqueness are not proved by the store. |
| A07 | Atomic durable nonce uniqueness bound to device/route and request digest; stale/revoked/generation/time/repeated nonce denied. Replay rejection is separate from operation idempotency. No eviction of still-acceptable replay proof; if safe pruning is not implemented, bounded-capacity exhaustion denies further admission. Wall-clock rollback fails closed rather than resurrecting expired evidence. |
| A08 | Before/after commit and process-interruption faults produce either original or fully committed state/receipt; no half-consumed grant, generation or nonce. Public errors are bounded/allowlisted and contain no raw caller/SQL/path/secret diagnostic. |
| A09 | Consistent backup uses SQLite backup API and validates snapshot. Supported restore enters durable RECONCILIATION_REQUIRED before any control admission and offers no unconditional mark-ready/force-clear. Do not claim SQLite-only detection of an out-of-band old valid backup or an implemented node-journal reconciliation protocol. |
| A10 | Focused actual Linux/Windows cooperative singleton/transactions/reopen/backup/CAS/fault tests plus retained regressions. Preserve all 85 MCP schemas, native signatures/paths, M0/C1 and historical evidence. No network, private VM/VPS, SDK/process launch or provisioning. |

Full 058 crypto/transport/endpoint/pilot and physical restore/anti-rollback qualification remain open until their own source and physical outputs exist. Builder supplies Completion Report, changed paths, YAGNI answers, AC tests/results, source hashes, deviations and suggested follow-up. Contractor independently verifies and publishes Draft checkpoint, then immediately continues the authorized plan.
