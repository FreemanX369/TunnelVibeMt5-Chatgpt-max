# TIP-057R-C1 — Explicit local read validation source

Date: 2026-10-03, Asia/Saigon. Status: C1 PRODUCT SOURCE PASS; real SDK and private VM qualification remain deferred. Parent Draft #63, head `5583204f698dcbf664ad20ddae8106d96019c8d2`, tree `9d8dbd8e6799ce9372e8f039d357dff88e2944ca`. Source and acceptance receipts: [Contractor verification](TIP-057R-C1-verification.md).

The owner's continued approval authorizes the next bounded product source step. The earlier instruction to build before private VM testing remains in force. This TIP implements the additive request and failure contract from TIP-057R without enabling targeted IPC. It does not close G03-B producer integration, G04 strict no-start, Q2, connector pilot or M1.

## YAGNI-3 and scope

1. Explicit terminal selection needs a strict input surface and attributable, sanitized failure receipt independently of future SDK activation.
2. Reuse TerminalInventory, IdentityRegistry, existing inventory-only target resolution, common native admission and the fleet.read/1 contract. Inventory validation resolves identity only; it never grants live_read capability.
3. Extend only the state/account facade and MCP reads with target=None and a narrow product helper. No process probe, SDK/proof import, worker launch, success branch, enable switch, transport or new durable transfer schema.

No target/null follows the existing fixed MT5-2 path, preserving historical output/errors. Explicit targets use fresh config/identity under the same native lease. A fully resolved local target always fails with LIVE_ATTACH_ONLY_UNPROVEN before native observation. Existing M0 validators and native signatures remain unchanged.

## C1 acceptance criteria

| AC | Required source behavior and evidence |
|---|---|
| C01 | Only the two selected facade/MCP reads gain optional target. No target and null retain their legacy calls/output/errors, including runtime policy. Catalog count, all other tool schemas, native request signatures and hashes remain unchanged. |
| C02 | Exact schema/fields, full-match persisted ID formats and positive integer generations without bool/coercion. Malformed/extra/oversized IDs produce TARGET_MISMATCH and requested_target=null; arbitrary caller content never appears in output. Non-null route generation must itself be a positive integer before projection, then ROUTED_NATIVE_NOT_ENABLED. Absent/null route is local. Handler-rejected scalar remains SDK protocol failure. |
| C03 | After strict input validation, use shared native admission with bounded wait <=2000ms and remaining soft budget. Resolve current config/registry under that lease, preserving duplicate alias evidence and disabled rows. Unknown/remote/stale/disabled/unqualified/conflicting/corrupt/drifted binding produces its sanitized contract failure with no legacy fallback or process/SDK access. Cached facade inventory is not authority. |
| C04 | A resolved local target records exact target, registry revision/source, alias and canonical binding as inventory attribution only. It fails LIVE_ATTACH_ONLY_UNPROVEN with source/observed_at_utc/observed_binding/terminal/account=null. No inventory validation is labeled live_read authorization, observed process or successful attachment. |
| C05 | Fixed fleet.read/1 envelope, allowlisted codes/phases, no raw exception strings. Common ownership missing/invalid/ACTIVE denies as LIVE_RECOVERY_REQUIRED; FIFO wait timeout as LIVE_LEASE_UNAVAILABLE. An acquired zero-effect lease is RELEASED only after normal release. No native arm/create attempt/authority mutation. |
| C06 | Release uncertainty overrides with LIVE_CLEANUP_UNPROVEN and preserves first earlier code as primary_reason_code. Ownership RECOVERY_REQUIRED, cleanup remains NOT_ATTEMPTED because native attachment was never attempted. No return precedes release; preacquisition errors report NOT_ACQUIRED. |
| C07 | Monotonic actual nonnegative total and executed lease/release durations, unexecuted process/initialize/observe/revalidate/cleanup=null. Fixed SOFT_SUCCESS budget values from TIP-057R; final expiry sample includes release overruns. Expiry stops subsequent phases, first failure preserved, expiry as first failure -> LIVE_DEADLINE_EXCEEDED. No hard deadline or physical latency claim. |
| C08 | Focused domain/facade and actual generated MCP-schema tests prove C01-C07, zero native observation, fresh config/registry, ownership and faults. Retained unit suite/Q1/G03-A/B1 checks pass with skips explicitly explained. Exact candidate/final-head CI and Builder Completion Report are independently verified. |

The original fourteen-AC contract remains the full-feature acceptance map. C1 covers only its source/schema/validation/denial subset. Observation, post-observation revalidation, SDK cleanup, process discovery/race and physical client/two-binding success are not executed or claimed.

## Delivery

Builder supplies a Completion Report with changed files, YAGNI answers, per-AC tests, hashes and remaining gates. Contractor reviews and verifies independently, then opens a separate Draft PR stacked on #63 and retains exact-head CI evidence. No merge, deploy, VPS/MT5 operation, SDK install/import, enrollment mutation, account/AutoTrading change or real-environment test in this slice.
