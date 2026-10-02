# TIP-057R-Q — Proposed Windows IPC boundary proof

Date: 2026-10-02. Status: **Q1 ISOLATED PROOF APPROVED / DISPATCHED; PRODUCT AND Q2 UNAPPROVED**. Owner approved the concrete preceding Q1 proposal at13:59:50+07:00; see [Q1 Builder TIP](TIP-057R-Q1.md) and [approval ledger](approval-2026-10-02.md). This is a concrete response to the [contract](TIP-057R-contract.md)'s G03-ownership/G04 blockers, not a production helper implementation or permission to operate current MT5 installations. The original decision alternatives below remain the historical proposal; Q1's bounded fixture investigation is now authorized.

## Selected direction

Retain strict no-start. Investigate a short-lived local IPC worker with a preventive process-creation restriction, exact worker ownership and parent-controlled termination/reconciliation. Reuse the existing global native lease in the parent; do not add another scheduler, gateway, native lock namespace or permanent worker service.

A helper by itself is insufficient: the same initialize call can still start a terminal. Windows child-process restrictions are a **candidate**, not a proved MetaTrader5 attach-only API. The experiment must establish whether the actual library's launch path is contained, including any brokered/out-of-process launch, inherited/breakaway behavior and assignment-before-library-load race. If the restriction cannot prevent every relevant path, the hypothesis fails and targeted IPC remains disabled. Do not patch/inject into MetaTrader DLLs, change terminal executable ACLs or install global process interception as a shortcut.

Microsoft's [UpdateProcThreadAttribute reference](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute) describes PROC_THREAD_ATTRIBUTE_CHILD_PROCESS_POLICY / PROCESS_CREATION_CHILD_PROCESS_RESTRICTED and requires a sandbox boundary preventing privileged process handles. Therefore adding the flag to an unrestricted administrator helper is insufficient. Q1 must examine a restricted token/privilege and handle boundary; no claim that a JobObject process-count limit alone prevents launch is accepted. Process discovery cannot rely on launching PowerShell inside a child-process-restricted helper. Mechanism feasibility and compatible IPC access are open research outcomes, not approved defaults.

## Bounded spike output

Stage Q1 may run only in isolated Windows CI with harmless fixture executables. Build the smallest fixture worker/boundary needed to test: launch denied before library-like initialization, no assignment race, exact worker PID/creation ownership, timeout/hang, initialize/shutdown faults, parent crash, inherited handles and stale/PID-reused ownership. Define the proposed restriction using primary Windows documentation before choosing a mechanism. Limit to one worker and synthetic state/account-shaped data; no trading SDK dependency is required for Q1.

Q1 code lives in isolated proof/fixture scope; production native acquisition, deployment configuration and runtime state are unchanged. Existing shared-lease fixtures may be reused in a temporary root. Any recovery/blocker prototype has fixture authority only. Demonstrating simulated conflicting callers cannot qualify unchanged production entry paths; common-acquisition integration and its actual legacy/native regression remain a later reviewed product change.

The parent holds the shared lease through worker completion or verified exact termination. A killed worker is not automatically cleanup proof for any separately launched process; record descendants/escape uncertainty and keep recovery-required if uncertain. A durable unresolved-ownership blocker must gate common legacy/native acquisition after parent death or ambiguous cleanup. Specify its schema, atomic persistence, exact owner creation identity, generation/CAS recovery authority and compatible rollback before product integration. Q1 tests must show that removing/restarting only the parent cannot bypass that blocker.

Cover the crash-before-blocker window explicitly: commit durable intent, or demonstrate an equivalent common-acquisition fail-closed authority, before worker/native attachment begins. Simulate parent death before it can record a cleanup failure and show that fixture callers cannot treat missing failure state or a dead parent PID as authorization. A failure marker written only after detecting an exception is insufficient.

Report measured response/termination/recovery timings. Candidate budget: 10,000 ms observation, maximum2,000 ms lease wait and2,000 ms initialize/probe. A hard response deadline is not certified merely by terminating a synthetic worker; the entire parent lifecycle, remaining ownership and caller return path must be accounted for.

Stage Q2 is a separate physical qualification gate: exact Windows/MetaTrader5 library/build, two qualified disposable/non-live terminal bindings, deterministic exit-before-attach races, zero new terminal processes, exact root attribution and unchanged account/AutoTrading. Q1 approval does **not** authorize creating this environment, stopping current terminals, accessing credentials or running Q2 on current live installations. Q2 requires a concrete reviewed environment and execution scope before any effect.

## Acceptance and stop conditions

| Output | Pass condition | Failure disposition |
|---|---|---|
| Q1 prevention | Fixture child/escape launch is denied before any side effect | Reject this restriction; do not claim SDK coverage |
| Ownership | Worker/parent fault cannot admit overlapping simulated conflicting callers in the fixture boundary | Keep G03 open for production until common-acquisition integration is separately reviewed/tested |
| Recovery | Ambiguous worker/descendant outcome persists across restart and requires exact generation/owner reconciliation | No automatic stale-PID or TTL clear |
| Budget | Actual end-to-end timings and overruns are reported; no worker survives released ownership | No hard-deadline claim |
| Q2 actual SDK | Actual launch paths/races produce zero starts and exact binding receipts on reviewed disposable scope | Keep G04 open; retain failed evidence |
| Compatibility | Existing fixed/native/core behavior remains compatible except explicitly reviewed unresolved-ownership denial | Return deviations before merge/deploy |

## Owner decision and delivery boundary

Recommended decision: approve **Q1 isolated Windows fixture proof plus ownership/recovery design**, preserving strict no-start, with a Draft PR and Builder Completion Report. This permits investigating a new local process boundary; it does not approve a production helper, a durable-state migration, VPS rollout or Q2 native terminal effects. Contractor reviews the actual result before proposing an amendment to the product Blueprint.

Alternative: explicitly relax no-start to best-effort precheck, accepting that terminal exit during the race may trigger initialize's restart behavior. This is a product-policy change and is **not recommended or inferred from continuation approval**. Existing policy remains in force until an explicit owner decision.

YAGNI-3 for Q1: the proof must exist because the approved policy has no supported attach-only API; reuse Windows CI, shared-lease fixtures and existing target/state conversion; write only an isolated worker/restriction/ownership proof that can falsify the hypothesis. Do not build full fleet transport or maintain a parallel account-observation implementation.

Evidence: [MetaQuotes initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py) documents optional launch and no attach-only parameter; [shutdown](https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py) documents connection closure, not cancellation of an unrelated stuck call. Retrieved2026-10-02. A preventive Windows mechanism remains a research hypothesis, not a sourced implementation guarantee.
