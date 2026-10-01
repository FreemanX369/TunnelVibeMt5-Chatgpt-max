# TIP-055A — Local Target Identity Foundation

**Status:** SPEC DRAFT — dispatch after owner Blueprint approval. **Priority:** first implementation. **Dependency:** approved Fleet v1 Blueprint at an exact commit. Date: 2026-10-01. Impact: medium; reversible code, persisted identity requires careful rollback. No product code is delivered by this file.

## Intent, why and smallest change

Create a durable local device/terminal identity overlay and target vocabulary so later fleet routing can distinguish physical bindings without removing fixed MT5-2 protection. The output is enriched inventory with honest identity status and a reusable resolver/validator for the enrolled local binding, not working remote or multi-terminal native execution.

YAGNI answers: this must exist to address alias/build ambiguity; reuse TerminalInventory, config loading, atomic write/lock patterns and existing inventory tests; implement a small local registry/overlay without gateway, broker, keys, extra public tools or native state-machine changes.

## Context and integration boundaries

Repository: `FreemanX369/TunnelVibeMt5-Chatgpt-max`. Audited baseline `64a62906b4e62274732f0cbc375bfb3687af9e42`. Builder uses its implementation checkout/branch, reads current instructions, compares relevant source drift and preserves unrelated changes. No absolute scratch path is a project dependency.

Primary reuse/context:

- `app/vibemql5/core/inventory.py`: config-based TerminalInfo, describe/build-source semantics and validation.
- `app/vibemql5/models/types.py`: strict from_dict compatibility with legacy configuration.
- `app/vibemql5/core/facade.py`: inventory surface; native/live execution remains fixed.
- `app/vibemql5/core/concurrency.py`, `core/jobs.py`, `core/revisions.py`: existing cross-process/atomic-write patterns; reuse without changing their scopes or request hashing.
- `app/vibemql5/adapters/mcp.py`, `contracts.py`, `adapters/cli.py`: current tool/catalog and bootstrap interface.
- Existing `tests/unit/test_tip053_catalog.py`, TIP-024 concurrency tests, TIP-028 idempotency, TIP-054 guard tests and inventory selection tests are regression anchors. Locate their exact files at dispatch rather than guessing names.

Proposed modules: `app/vibemql5/fleet/identity.py` and `targets.py` if existing modules cannot express the small contract cleanly. Proposed new tests `tests/unit/test_tip055a_identity.py`. Builder may choose an equivalent shorter organization and reports it. No generic repository abstraction or transport is added.

## Task

1. Add explicit, cross-process-safe local identity bootstrap/update, storing schema `fleet.identity/1` at `state/fleet/identity.json`. Use one lock, atomic replacement, monotonic identity revision and validation. Return the existing record on repeated identical enrollment. Do not create a fresh identity on corruption or a read-only inventory call.
2. Persist opaque device/terminal IDs. Normalize and record executable/data-root bindings and terminal_generation. Enrollment of a new installation differs from an explicit rename/binding replacement. Build and hostname are observations/labels.
3. Expose identity enrichment through existing terminal inventory/validation; old fields and their build authority are preserved. UNENROLLED/INVALID status is explicit. Keep legacy inventory useful without registry; any new consumer requiring identity fails closed.
4. Validate local target references and unsupported routed capability. New target-aware validation has no authority to launch native work. Wrong/unknown/ambiguous bindings fail before dispatch; do not use fallback helpers for these references.
5. Detect duplicate/conflicting native resources. Two aliases sharing normalized executable or data root receive RESOURCE_CONFLICT/unqualified status, not separate capacity. Cover Windows path casing/separators and observable reparse aliases.
6. Document bootstrap, read-only behavior, rename/replacement/disable semantics and rollback. Keep private-key/pairing lifecycle out of this TIP.

M0 changes no native public tool signatures, 85-tool names/catalog order, JobStore request hash/reservation, results/history schemas, Project Session/Continuity state machines, runtime-capture signed authority, lock paths or terminal policy. Enrichment is local registry provenance, not proof that a native job ran there.

## Acceptance criteria — Gherkin and required proof

Each AC is verified against real implementation, not an assertion duplicating constant output. Use isolated filesystem/process fixtures; do not initialize registry on the deployed VPS in this task.

| AC | Given / When / Then | Evidence |
|---|---|---|
| AC-01 | Given valid legacy terminal config and no registry, when read-only inventory runs, then old rows remain readable, identity is UNENROLLED and no state file is created | Before/after fixture filesystem and field compatibility |
| AC-02 | Given two independent bindings, when explicit bootstrap runs and a new process reloads it, then device/terminal IDs persist and terminal IDs differ | Registry round-trip across process reload |
| AC-03 | Given an enrolled binding, when build/hostname observations change or process restarts, then IDs and terminal generation remain unchanged | Observation/reload comparison |
| AC-04 | Given an enrolled terminal, when explicit alias rename is committed, then same terminal ID/generation remains and old alias no longer resolves ambiguously | Rename and resolution receipts |
| AC-05 | Given an enrolled terminal, when explicit binding replacement retains its ID, then generation increments once; replay of identical update is idempotent; a stale revision fails | CAS/revision fixture and replay |
| AC-06 | Given disabled terminal, when re-enabled with the same enrolled binding, then its ID/generation persists; unknown/new binding requires enrollment | Disable/re-enable/new-binding cases |
| AC-07 | Given legacy compile/test/live interfaces, when identity support is present, then their default remains fixed MT5-2 with original global locks; no routed execution is opened | Relevant existing regressions and call interception; no physical test |
| AC-08 | Given duplicate normalized executable OR data-root bindings, when registration/inventory validation runs, then conflict is explicit and independent execution capability is not advertised | Case/separator/shared-root negative tests; Windows reparse fixture where available |
| AC-09 | Given simultaneous bootstraps in distinct processes, when both target one empty registry, then only one device identity and one ID per binding are committed; no partial JSON is readable | Cross-process race with synchronized start |
| AC-10 | Given malformed registry or interrupted atomic write, when loading/recovery occurs, then old committed registry survives or status is INVALID; no identity is silently regenerated | Corruption/pre-replace fault fixtures |
| AC-11 | Given an unsupported/unknown or mismatched local target reference, when new validation runs, then it fails before dispatch/fallback/native side effects | Spy/fake drivers proving zero side-effect calls |
| AC-12 | Given the enriched inventory response, when catalog/import compatibility checks run, then existing tool names/order/count remain 85 and legacy config parsing/fields still work | Catalog and response-shape tests |
| AC-13 | Given old job/result/session/revision and operation-index fixtures, when enrollment/inventory/rollback is exercised, then their bytes/hashes remain unchanged and operation replay semantics are preserved | Hash-before/after and existing idempotency/CAS regression |
| AC-14 | Given a fully enrolled registry, when the identity overlay code is disabled/rolled back, then legacy config/inventory remains usable and identity state is retained for compatible recovery | Reversible fixture + operator procedure |

AC-08 physical reparse equivalence not observable in a platform fixture is reported as UNQUALIFIED, never a PASS proving executor independence. Windows-specific evidence is required before Windows identity deployment qualification, but does not block submitting an implementation PR with honest PARTIAL status.

## Verification and completion

Run new identity tests plus relevant existing inventory/catalog, concurrency/idempotency and source-guard regressions. Run the repository's required CI checks on the exact PR head. Broad reruns follow only if implementation touches broader behavior or checks uncover concerns. M0 physical verification is inventory/bootstrap-only in an explicitly authorized deployment; no tester/account/AutoTrading action.

Submit Completion Report with each AC, tested platform, actual receipts, unresolved Windows/client gates, changed files and deviations. `DONE` means all TIP-required outputs have evidence; code complete but missing required platform acceptance is `PARTIAL`. Contractor verifies before M1 readiness.

## Constraints and escalation

No direct main commit, deployment/restart, MT5 native test, account/credentials/AutoTrading change, generic shell/PowerShell MCP, secret export, evidence reset, scope expansion or new fleet transport in this task. Ordinary isolated development commands and tests are permitted after approval. A need to alter native policy, history format, ownership scope or request hashing is an architecture deviation and returns to Contractor before implementation.
