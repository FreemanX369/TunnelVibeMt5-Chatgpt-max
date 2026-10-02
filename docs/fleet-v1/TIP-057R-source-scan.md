# TIP-057R — Focused source scan and contract inputs

Date: 2026-10-02, Asia/Saigon. Status: **SCAN COMPLETE / CONTRACT INPUTS / BUILD NOT DISPATCHED**. Base main `c9657aeee23960b59218abc641a8757af55bed7c`, tree `e8a0823e924c31c4f7bd1f817216633534d65b12`. Builder scan was read-only; Contractor independently checked selected signatures, validation, initializer/cleanup and vendor documentation. No code/tests/deployment changed.

An earlier scan at 03:07 was interrupted by an explicit usage-limit error; it was not completion. The resumed scan at the 11:27 continuation supplied the missing findings. No automatic 30-minute run receipt or numeric usage-percent reading exists in this checkpoint.

## Research brief and source authority

Question: what existing local state/account path can safely accept an explicit local target, and which lifecycle/deadline constraints prevent dispatch? Scope: this exact source and the current Windows VPS, 2026-10-02; no financial totals, chart/native action or new transport. External evidence is limited to first-party API documentation; forum/blog claims and assumed native cancellation are excluded.

Source log:
- S01: reviewed repository base above; exact local source observations, verified against Git blobs.
- S02: [MetaQuotes initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py), retrieved 2026-10-02; vendor API reference, Tier 2 / probable as documented API statement, not physical runtime evidence.
- S03: [MetaQuotes shutdown](https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py), retrieved 2026-10-02; same authority/qualification boundary.
- S04: [fresh checkpoint](evidence/2026-10-02-tip056-readiness.json); verified tool receipts for current inventory/runtime observations.

## Fact cards

| Fact | Statement and source | Authority |
|---|---|---|
| R01 | `get_terminal_live_state(self)` and `get_account_snapshot(self)` both call `LiveTerminal.state()`; MCP public args absent except injected ctx (`core/facade.py`:223–233; `adapters/mcp.py`:173–182) | Verified source |
| R02 | Existing native lease wait is 2s, with fixed MT5-2; inventory is cached at facade construction (`core/facade.py`:31–33,223–233) | Verified source |
| R03 | M0 local target validation accepts inventory only; other capability or non-null route_generation returns ROUTED_NATIVE_NOT_ENABLED (`fleet/targets.py`:6–42) | Verified source |
| R04 | Running-process discovery invokes a subprocess with timeout 8s; state checks running both before and after initialize (`core/inventory.py`:95–131; `core/live_terminal.py`:63–82) | Verified source |
| R05 | Initialize timeout is 2000ms; false/raising initialize precedes shutdown finally, and shutdown exception can propagate into context lease release (`core/live_terminal.py`:66–68,120–121; `core/concurrency.py`:448–470) | Verified source |
| R06 | Returned shape is source/observed_at_utc/terminal/account; disconnected account/counts and ping_ms are null and account_info is skipped (`core/live_terminal.py`:83–119) | Verified source |
| R07 | Exact post-IPC executable-directory/data-root checks happen before account_info; current process discovery provides paths rather than a frozen process-creation identity (`core/live_terminal.py`:70–82; `core/inventory.py`:95–131) | Verified source |
| R08 | Vendor documents initialize timeout as connection timeout and states initialize can launch the terminal if needed (S02) | Probable documented statement; not total-call or attach-only proof |
| R09 | Vendor documents shutdown as closing the established connection; it supplies no cancellation/deadline guarantee for other calls (S03) | Probable documented statement; absence of guarantee is a contract gap |
| R10 | Actual inventory remains five UNENROLLED/UNQUALIFIED rows, null identities and routed-native false (S04) | Verified point-in-time runtime observation |

Duplicate language mirrors/search results were excluded. Conflict queue: none between these source statements; the implementation-versus-required guarantees below are gaps, not conflicting facts.

## Proposed minimal selected surface

YAGNI-3: selected-terminal inspection is required by REQ-F04; reuse IdentityRegistry/TerminalInventory/LiveTerminal.state/facade/shared native lease and state conversion; add only explicit local target resolution/attribution, scoped lifecycle hardening and the selected budget. Gateway, chart/market data and native routing stay in their later TIPs.

Propose optional `target: dict[str, Any] | None = None` only on the two selected MCP/facade read methods. No target retains fixed MT5-2 and existing return/error authority. Explicit local fleet.target/1 uses schema/device_id/terminal_id/terminal_generation; route_generation absent/null. No fallback or fabricated route generation.

Resolve fresh config and registry under the existing global native lease, not cached `self.inv`. Validate a real `live_read` capability rather than relabel a live operation as inventory. Freeze IDs/generation/revision/canonical binding; validate before IPC and compare after observation before an attributed success. Wrong IPC roots must fail before account access. Fresh process identity proof must not assume live processes carry native job IDs.

Propose targeted `fleet.read/1` receipt with requested/resolved/observed binding, identity source/revision, UTC observation, phase timings and cleanup status. Preserve existing state/account conversion and unavailable/null behavior. Explicit failure carries status FAILED, reason_code, bounded phase/diagnostic, available attribution and null terminal/account; disconnected can succeed as an unavailable-account observation.

Reuse identity reason codes. Draft read-specific mapping: TERMINAL_NOT_RUNNING, LIVE_IPC_INITIALIZE_FAILED, LIVE_BINDING_MISMATCH, LIVE_OBSERVATION_UNAVAILABLE, LIVE_DEADLINE_EXCEEDED and LIVE_CLEANUP_UNPROVEN. These names are proposals, not implemented public codes. Legacy RuntimeError tokens remain historical compatibility authority: FIXED_TERMINAL_NOT_RUNNING, MT5_LIVE_IPC_INITIALIZE_FAILED, MT5_LIVE_TERMINAL_INFO_UNAVAILABLE, MT5_LIVE_TERMINAL_BINDING_MISMATCH, MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE.

## Numeric budget proposal and limits

Draft only, to freeze against the pilot before BUILD: monotonic **10,000ms observation budget**, maximum **2,000ms lease wait**, initialize `min(2000, remaining_ms)`, each process enumeration maximum `min(2000, remaining_ms)`. Record actual elapsed phases, including acquisition/audit/OS overhead. This is a soft success deadline, not a certified total response deadline or latency measurement.

Check budget before/after every blocking phase and after cleanup/release. Expiry prevents additional observation and successful response; cleanup/reconciliation remains required before relinquishing ownership. Existing two 8s process-discovery calls cannot be left unchanged while claiming this budget.

A timer check cannot interrupt an uninterruptible native call. No thread timeout may return while releasing the lease under continuing IPC. A helper boundary for a hard caller deadline requires review and Windows qualification; this draft does not authorize one.

Cleanup must encompass initialize attempts that return false or raise. Preserve primary and cleanup failures separately. Cleanup-unproven requires a fail-closed shared-ownership/quarantine and controlled recovery policy; current unconditional context release is insufficient to claim it. Freeze that policy before code dispatch.

The running-precheck→initialize window remains a race: the process may exit before initialize, and the documented API can start it. Post-root validation proves binding, not strict attach-only behavior. Strict no-start in that race requires actual Windows/library evidence or a separately reviewed boundary. Keep the approved account/credential/AutoTrading and terminal-start policy intact while resolving this gap.

## Gap register and draft acceptance

| Gap | Needed before dispatch / actual acceptance |
|---|---|
| G01 | Real M0 bootstrap/show/fresh-process reload, verified complete registry backup and two distinct physical QUALIFIED bindings; operator handoff already exists |
| G02 | Frozen additive target/receipt/error schemas, actual selected-client exposure and real pilot IDs |
| G03 | Numeric budget selected from pilot; choose honest hard-vs-soft contract, unfinished IPC/cleanup ownership and controlled recovery |
| G04 | Prove strict no-start/attach-only policy in the running-process race, or review a concrete compatible boundary; no policy relaxation inferred |

Draft AC map: legacy fixed shape/error compatibility; strict target rejection/no fallback; fresh config and generation pre/post; wrong IPC binding rejected before account access; disconnected/null semantics; mixed two-target calls serialized across lifecycle; initialize false/raise/observe/shutdown faults; budget expiry retaining ownership until proven cleanup; actual two-binding Windows/client exposure. Map each AC to a named test and real receipt in the dispatched TIP.

Source scan closes the information-gathering step. It does not close G01–G04, dispatch BUILD or certify a native account observation. [TIP-057R readiness](TIP-057R-readiness.md) remains the governing gate list; [TIP-056 readiness](TIP-056-readiness.md) remains later M4 planning.
