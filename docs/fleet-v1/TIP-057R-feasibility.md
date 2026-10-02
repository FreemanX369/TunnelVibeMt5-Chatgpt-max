# TIP-057R — Builder feasibility and Contractor verification

Date: 2026-10-02, Asia/Saigon. Base `146c72ad37a5daa5f1f64ee4aba7f0d2f84ef809`; tree `efd3d54d8db7c1c981a0fc24acae0ae56bb54716`. Builder: resumed `scan_tip057r`; role READ-ONLY feasibility. Status: **DONE FOR CONTRACT REVIEW / BLOCKED FOR PRODUCT IPC BUILD**.

## Builder report

Files changed by Builder: none. Product/test code executed: none. No VPS PowerShell/native/account/chart/deployment operation. The existing code, real M0 qualification and fresh read-only health/inventory receipts supply the evidence; no new mock or physical targeted-read PASS is claimed.

YAGNI-3: selected-terminal reads are required; reuse registry, inventory, state/account conversion, facade and the global native lease; the smallest useful change is optional target plus exact attribution and scoped lifecycle/budget. A helper is considered only because existing API behavior does not meet the approved no-start guarantee.

| Review item | Finding | Disposition |
|---|---|---|
| Optional schema | Two selected methods can accept local target without changing legacy successful shape or other tool/native contracts | Feasible contract; actual client exposure is a later acceptance gate |
| Target authority | Existing validator is inventory-only; cached facade inventory cannot prove current binding | Explicit live_read capability and fresh resolution required |
| State conversion | Existing financial/null/masked-login conversion can be reused | No duplicate account model or totals |
| Budget | 10,000ms monotonic success budget and2,000ms lease/init/probe caps can suppress late success | Soft only; blocking native/audit/OS phases can overrun |
| Cleanup | initialize false/raise precedes current shutdown finally; shutdown raises into unconditional lease release | Shared ownership mechanism still required |
| Restart/recovery | In-memory target quarantine disappears on restart; legacy/native acquisition can bypass it; stale cleanup checks only PID | Durable shared barrier/exact recovery requires review |
| No-start | Documented initialize has no attach-only flag and can launch terminal after running precheck race | G04 genuinely blocks usable target IPC |
| Helper | A helper using the same initialize does not remove launch behavior | Preventive restriction and exact cleanup proof required |

Source anchors: `core/facade.py` construction and selected read methods; `core/live_terminal.py` state lifecycle; `core/inventory.py` two process probes/current8s subprocess timeout; `core/concurrency.py` native_execution finally-release/common acquisition/PID-only stale lock; `fleet/targets.py` inventory-only guard. These findings agree with the retained [source scan](TIP-057R-source-scan.md); product source is unchanged at this contract checkpoint.

First-party references were opened2026-10-02: [MetaQuotes initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py), [shutdown](https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py), and [Microsoft UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute). Vendor launch/connection-timeout behavior is documented, not a new physical test. The preventive Windows boundary is a hypothesis; administrator privileges, inherited handles, brokered launch and restriction assignment races require proof.

Tests/results: zero new tests run. The proposed AC/test matrix in the [contract](TIP-057R-contract.md) is PLANNED, including legacy shape, no-fallback rejects, fresh pre/post generation, binding-before-account, disconnected nulls, full lifecycle serialization, initialize/shutdown faults, late/stuck IPC ownership, restart blocker, actual no-start race and exact-client receipts. Names are specifications, not already implemented tests.

Issues: HIGH — G03 uncertain cleanup can admit conflicting work; HIGH — G04 strict no-start is unsupported by current API. No deviations to product policy/architecture were made. Suggestion: a separately approved [isolated Windows proof spike](TIP-057R-boundary-proposal.md), not immediate production helper integration.

## Contractor verification

Contractor independently checked the selected source, official references, fresh main and runtime receipts. All180 base blobs were verified before creating the isolated documentation checkout. Actual local inventory still has five stable ENROLLED/QUALIFIED generation1/revision1 bindings, routed-native false. Runtime remains TIP-053/0.2.42, catalog85, fixedMT5-2, READY/idle with clear locks/waiters; A/B/C each one process and200/200. The new B poll timeout at12:21:29 recovered12:22:00 is retained alongside earlier A/C episodes; current endpoints do not erase it or establish new soak certification.

Schema contract and planned acceptance are now concrete; source/CI/deployed/physical gates are separated. No selected tool currently exposes target based on this document. No total caller deadline or attach-only proof was manufactured. G02-schema preparation is complete; G02 actual client/pilot acceptance, G03-ownership and G04 remain open. The10s selection applies only to the local soft-success proposal, not TIP-059 fleet hard response behavior.

Next authorized action after this planning continuation is review of the concrete Q1 boundary proposal. Owner approval of a new process boundary is needed before that architecture is implemented; successful Q1 fixtures still do not authorize Q2 on current MT5 or unlock a production capability. Product BUILD is blocked by technical guarantees, not by missing formatting or repeated generic approval.

Builder's second documentation cross-review identified five refinements, now incorporated: release with NOT_ATTEMPTED cleanup when no attachment was attempted; bounded registry-compatible ID projection and SDK-versus-domain errors; deterministic primary/deadline/cleanup precedence; durable intent covering parent crash before a failure marker; and the explicit separately reviewed legacy shared-recovery denial exception. Q1 fixture authority remains distinct from production integration. No blocker was converted into a fabricated PASS.
