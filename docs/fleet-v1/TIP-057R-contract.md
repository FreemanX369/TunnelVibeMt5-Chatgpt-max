# TIP-057R — Local target read contract

Date: 2026-10-02, Asia/Saigon. Base main: `146c72ad37a5daa5f1f64ee4aba7f0d2f84ef809`; tree `efd3d54d8db7c1c981a0fc24acae0ae56bb54716`. Status: **CONTRACT PREPARED / LIVE BUILD BLOCKED**. The 13:36 owner continuation authorizes this next contract step; it does not approve a changed IPC architecture or weaken strict no-start. This document specifies future outputs, not implemented APIs or actual account observations.

Later13:59 owner decision explicitly approves [Q1 isolated fixture investigation](TIP-057R-Q1.md) of the proposed process/ownership boundary. Product integration, common-acquisition migration, Q2 native environment/effects and strict no-start relaxation remain unapproved/unqualified. The historical pending-decision wording below does not override this bounded Q1 approval or turn its future findings into product capability.

Dependencies: actual [M0 qualification](TIP-055A-enrollment-qualification.md), approved Blueprint section 6, [focused source scan](TIP-057R-source-scan.md), and the ownership/no-start proof below. Priority: next M1 dependency. Requirements: REQ-F04/F10/F14/F15; REQ-F11 shared ownership compatibility.

## YAGNI-3 and scope

1. Required: inspecting a selected enrolled terminal needs exact identity, attribution and failure semantics; an alias or fixed-terminal response cannot represent another terminal.
2. Reuse: IdentityRegistry, TerminalInventory, local target validation, LiveTerminal state/account conversion, ToolFacade, existing MCP read methods and the one shared native lease. Existing fixtures remain the legacy behavior authority.
3. Shortest sufficient change: extend only the two state/account methods with an optional local target; add fresh resolution, attribution and lifecycle checks. No gateway, remote route, extra scheduler, market/chart payload, financial total or new public admin API. A helper or durable ownership barrier is a reviewed proposal until its separate boundary is approved and proved.

## Input and compatibility contract

Proposed facade signatures: `get_terminal_live_state(target=None)` and `get_account_snapshot(target=None)`. MCP exposes the same optional object alongside its injected Context. No timeout, alias-selection or credential parameter is added.

No target, including explicit null, keeps existing fixed MT5-2 behavior and historical errors. Successful legacy output stays exactly `source`, `observed_at_utc`, `terminal`, `account`; do not add identity fields or wrap it in a fleet receipt. Native compile/test/capture/market signatures and request hashes are untouched. The only proposed new legacy failure outcome is a shared unresolved-ownership denial, requiring its separate boundary review; it applies to every conflicting entry path and is not hidden as a targeted-only lock.

An explicit object must have schema `fleet.target/1`, string device_id/terminal_id, positive integer terminal_generation (bool is invalid), and only these fields plus optional route_generation. Missing/extra fields and an empty object fail. Route generation must be absent/null for this local slice. Non-local devices, unknown IDs, disabled bindings, stale generation, invalid/unenrolled registry, changed roots and unqualified/conflicting resources fail without alias or MT5-2 fallback. Do not fabricate a route generation or an authenticated principal.

Reuse the current persisted registry's exact full-match formats: device_id `dev_[a-f0-9]{32}` (36 ASCII characters), terminal_id `term_[a-f0-9]{32}` (37 ASCII characters). No whitespace/control characters or new alternate opaque-ID format. Reject malformed/oversize IDs before producing requested_target. For a request rejected by MCP/SDK type validation before the handler (for example a scalar instead of target object), retain the SDK's protocol error; the fleet envelope contract applies to domain-handled objects, not to requests that never reach the domain.

Fresh config and registry are read under the shared native lease; cached facade inventory is insufficient. Live capability validation must explicitly authorize `live_read`, while existing inventory validation and routed-native denial remain intact. Freeze identity revision, IDs, generation and canonical binding; revalidate config/registry after observation and cleanup. A revision/binding change rejects qualified success even if returned numbers look plausible.

## Explicit-target receipt: fleet.read/1

Both selected tools return the same envelope for explicit targets. Its fields are fixed for the contract review:

| Field | Type / meaning |
|---|---|
| schema | Literal `fleet.read/1` |
| operation | `get_terminal_live_state` or `get_account_snapshot` |
| status | `SUCCEEDED` or `FAILED` |
| reason_code | null on success; stable code on failure |
| primary_reason_code | Earlier failure preserved separately when cleanup/release uncertainty takes precedence; otherwise null |
| requested_target | Validated fleet.target/1 projection, or null when malformed; never echo arbitrary caller fields |
| resolved_target | Exact local target projection, or null until resolved; no generated route epoch |
| identity | null until known; otherwise identity_source, identity_revision, alias, canonical executable/data_root binding |
| observed_binding | null before verified observation; otherwise observed installation/data roots and verified process reference (PID plus creation identity and executable). Missing process authority cannot be fabricated from today's registry |
| source | Actual observation source; validation-only failures must not claim live IPC |
| observed_at_utc | Actual observation timestamp, otherwise null; it is not request time or cached inventory time |
| terminal / account | Existing state conversion objects only on qualified success; both null on failure |
| phase | Validation, lease, process, initialize, observe, revalidate, cleanup, release, or complete |
| budget | mode=`SOFT_SUCCESS`, observation_ms=10000, lease_wait_ms=2000, initialize_max_ms=2000, process_probe_max_ms=2000, expired boolean |
| timing_ms | Nonnegative measured total plus lease/process/initialize/observe/revalidate/cleanup/release durations; unexecuted phases null, UTC is not the timing clock |
| cleanup | status=`NOT_ATTEMPTED`, `PROVEN`, or `UNPROVEN`; bounded cleanup reason separate from primary reason |
| ownership | status=`NOT_ACQUIRED`, `RELEASED`, `RETAINED`, or `RECOVERY_REQUIRED`; actual authority only |

On disconnected success, existing financial/account/count values stay unavailable/null; do not convert them to zero. Existing masked-login conversion remains; no raw login, credentials, account changes, totals or deduction of distinct accounts from masks.

Malformed/unknown target errors occur before IPC. Diagnostics use an allowlisted phase and sanitized code, not raw exception strings containing credentials, arbitrary target payloads or unbounded native output. A not-yet-executed phase cannot be reported as completed cleanup. Acquired ownership becomes RELEASED after exact lease release and either proved cleanup or proved zero native-attachment attempts. An acquired validation/process failure before initialize can therefore release with cleanup=NOT_ATTEMPTED. If shutdown or release fails, success is forbidden and ownership is retained or explicitly recovery-required.

## Error contract

Reuse `IDENTITY_UNENROLLED`, `IDENTITY_INVALID`, `RESOURCE_CONFLICT`, `TARGET_UNKNOWN`, `TARGET_MISMATCH`, `ROUTED_NATIVE_NOT_ENABLED` from the identity contract. For this slice freeze the following read codes, without renaming historical legacy errors:

| Code | Trigger |
|---|---|
| LIVE_LEASE_UNAVAILABLE | Shared lease wait expires before acquisition |
| LIVE_PROCESS_UNAVAILABLE | Process enumeration fails, is ambiguous or lacks required authority; cannot claim terminal stopped |
| TERMINAL_NOT_RUNNING | Successful fresh discovery proves selected installation has no running process |
| LIVE_ATTACH_ONLY_UNPROVEN | Current boundary cannot guarantee no-start; deny before initialize |
| LIVE_IPC_INITIALIZE_FAILED | Initialize returns false or raises |
| LIVE_BINDING_MISMATCH | Observed executable/data root/process binding does not match frozen target; no account access |
| LIVE_OBSERVATION_UNAVAILABLE | Required terminal/account observation is unavailable or raises |
| LIVE_DEADLINE_EXCEEDED | Soft success budget expires; no further observation or successful response |
| LIVE_CLEANUP_UNPROVEN | Cleanup or lease release fails or remains uncertain; separate primary_reason_code is retained |
| LIVE_RECOVERY_REQUIRED | A shared unresolved-ownership blocker denies a subsequent conflicting request |

Error precedence is deterministic: cleanup/release uncertainty wins, with the first earlier failure retained in primary_reason_code. Otherwise keep the first domain/observation failure, even if budget expires during cleanup; set budget.expired=true without replacing that failure. Use LIVE_DEADLINE_EXCEEDED only when expiry is the first failure. Validation and lease failures have no native cleanup to claim. No automatic retry can attach to another target after an uncertain result.

## Budget and lifecycle requirements

For the bounded local design/fixtures select a monotonic **10,000 ms soft success budget**, including lease acquisition, audits and cleanup/release. Maximum lease wait is 2,000 ms; initialize and each process probe use `min(2000, remaining_ms)` and are skipped if no positive budget remains. Record real elapsed time, including overruns. This is not a hard caller-response deadline, measured pilot SLO, or replacement for TIP-059's total-deadline contract.

Check expiry before/after each blocking phase and after cleanup/release. An expired request stops further observation and returns no account values. Cleanup continues despite expiry. A native library call can overrun; returning from a timer while its worker still runs is not cancellation. Retain shared ownership until the call completes and cleanup is proved. No background thread may outlive released ownership. Hard caller deadlines require a qualified interruptible boundary and remain open.

Initialization false/raise is inside cleanup scope, not before finally. Shutdown's normal documented return is None, not a boolean success indicator. Preserve primary and cleanup failures separately. A shutdown exception, stuck call, adapter crash or unresolved exact lease release enters fail-closed recovery. The existing unconditional `native_execution` finally-release and PID-only stale-owner removal do not implement this requirement.

Required ownership outcome: every A/B/C adapter, legacy/native worker and conflicting read denies new attachment/work while old IPC might continue. An in-memory flag or target-only lock is insufficient. A durable blocker, if selected, must be committed before releasing ambiguous ownership, survive restart, and be checked at the common acquisition boundary. A durable intent or equivalent fail-closed authority must exist before worker/IPC start, so parent crash before a failure blocker can be written cannot authorize another owner. If committing required state fails, do not start IPC or release ambiguous ownership. Owner PID death alone cannot prove cleanup; PID reuse must be distinguished. Recovery must reconcile the exact old worker/IPC authority and clear an expected blocker generation atomically. No automatic TTL, hostname inference, terminal restart or broad process kill constitutes recovery. **Mechanism/recovery authority is not yet approved or implemented; G03-ownership remains OPEN.**

## Strict no-start and pilot gates

The running check is required but does not close the race between discovery and initialize. MetaQuotes documents that initialize can launch the terminal if needed and lists no attach-only parameter. Post-IPC root checks detect wrong binding after an effect; they cannot prevent a new process. A helper using the same call alone also cannot satisfy this policy. An unproved boundary must deny before initialize with LIVE_ATTACH_ONLY_UNPROVEN.

Candidate local bindings for later two-target proof are actual MT5-1 `term_aa5090f42e3b4743a4322384f2e139bf` and MT5-2 `term_dbfaf35a2a5f4b41bd2fedd387512c3a`, both generation1 on `dev_e488e5a0105847febf7ed46c9e15e9d0`. These are registered inventory candidates, not verified running/connected/session-qualified pilots. Later preflight verifies readiness and exact current process identity without starting/stopping either installation. Do not use examples or historical tester build evidence as live account proof.

G04 requires a preventive attach-only mechanism and exact Windows/library/version evidence, or an explicitly approved policy amendment. The [boundary proposal](TIP-057R-boundary-proposal.md) keeps strict no-start and proposes an isolated proof spike; it is not approval to add a helper, install a probe, provision a terminal or operate current MT5.

## Acceptance map for a later implementation TIP

All rows below are **PLANNED / NOT RUN**. Test identifiers describe required outcomes; they are not claims that files exist.

| AC | Given / When / Then | Planned test / physical receipt | REQ |
|---|---|---|---|
| 01 | Given no target/null, when either method is called, then fixed MT5-2 output and historical errors remain compatible | test_tip057r_legacy_state_account_contract | F04/F14 |
| 02 | Given malformed, unknown, disabled, stale, remote or conflicting target, when resolved, then explicit error with zero IPC and no fallback | test_tip057r_target_rejections_before_ipc | F04/F10 |
| 03 | Given changed config after facade construction, when targeted read acquires lease, then fresh binding is checked | test_tip057r_fresh_inventory_under_lease | F04 |
| 04 | Given registry/config changes during observation, when returning, then no qualified success or account values | test_tip057r_identity_revision_pre_post | F04/F15 |
| 05 | Given mismatched observed roots/process, when initialize returns, then account_info/count calls are never made | test_tip057r_binding_before_account_access | F04/F10 |
| 06 | Given disconnected correct terminal, when observed, then unavailable financial/count fields remain null | test_tip057r_disconnected_null_semantics | F04 |
| 07 | Given two target/client requests plus legacy native contention, when executed, then one lifecycle owner covers resolve through cleanup/release | test_tip057r_shared_lifecycle_serialization | F10/F11 |
| 08 | Given initialize false/raise, observation raise, or shutdown raise, when handled, then primary/cleanup outcomes remain distinct and no uncertain release | test_tip057r_initialize_observe_shutdown_faults | F10/F15 |
| 09 | Given expiry at any phase or a stuck native call, when timeout fires, then no late success/background IPC under released ownership | test_tip057r_soft_budget_preserves_ownership | F10/F15 |
| 10 | Given unproved attach boundary, failed/ambiguous discovery or stopped terminal, when read requested, then no initialize and truthful reason | test_tip057r_unproven_attach_and_process_denials | F10 |
| 11 | Given process exits between discovery and attachment, when boundary attempts observation, then zero new terminal processes and explicit failure | exact Windows boundary/library/race receipt, not a mock PASS | F10 |
| 12 | Given unresolved cleanup and A/B/C restart or legacy/native acquire, when new work arrives, then shared blocker persists and exact authorized reconciliation is required | test_tip057r_shared_recovery_across_restart plus Windows receipt | F10/F11/F15 |
| 13 | Given reviewed optional schema, when deployed to actual client, then both tools accept target and preserve all other schemas/catalog entries | test_tip057r_selected_mcp_schema plus actual connector receipt | F14 |
| 14 | Given two fresh qualified running bindings, when mixed requests observe them, then requested/resolved/observed IDs match with zero account/AutoTrading/start changes | actual guarded two-binding Windows/client receipts | F04/F10/F15 |

Contractor verifies every implemented REQ/AC against Builder Completion Report; fixture PASS does not close physical AC11/14. Native routing remains disabled and node capacity remains1. No code or deployment can be marked DONE from this contract alone.

## Gate disposition and next action

| Gate | Current disposition |
|---|---|
| G01 | CLOSED: real local M0 enrollment/backup/reload/inventory qualification |
| G02-schema | Contract prepared for additive inputs, envelope, codes and ACs; no implementation |
| G02-client/pilot | OPEN: actual connector schema exposure and two running binding/session receipts |
| G03-budget | Local soft-success selection documented; hard caller deadline and measured latency OPEN |
| G03-ownership | OPEN: shared durable recovery mechanism must be reviewed and proved |
| G04 | OPEN: existing initialize cannot prove strict attach-only; new boundary/policy requires a concrete review |

Next: review [TIP-057R-Q boundary spike proposal](TIP-057R-boundary-proposal.md) and [Builder feasibility report](TIP-057R-feasibility.md). Do not dispatch product IPC implementation, alter the original Blueprint, or mark M1 qualified while G03-ownership/G04 remain unresolved. Source fixture preparation after boundary approval remains separate from deployment/physical acceptance.

## Later C1 source disposition — 2026-10-03

The owner's source-first continuation after B1 authorizes bounded [C1](TIP-057R-C1-build.md), now PRODUCT SOURCE PASS in Draft #64. Optional inputs, strict fresh local inventory resolution and fleet.read/1 failure receipts are implemented and source-tested for the two selected tools. Legacy/null remains compatible; every resolved explicit target permanently denies LIVE_ATTACH_ONLY_UNPROVEN before process/SDK access. [Verification](TIP-057R-C1-verification.md) records the source/schema/validation/denial subset of AC01–03/07/09/10/13. This later scoped result supersedes historical no-implementation wording for that subset only. It does not turn inventory resolution into live_read authorization or execute observation, physical client/two-binding success, SDK cleanup, preventive no-start or post-observation revalidation. The full original acceptance map, Q2/G03-B/G04 and M1 remain OPEN.
