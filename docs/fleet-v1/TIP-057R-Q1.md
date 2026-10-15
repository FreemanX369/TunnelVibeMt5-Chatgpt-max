# TIP-057R-Q1 — Isolated Windows boundary proof

Status: **APPROVED / DISPATCHED FOR FIXTURE PROOF ONLY**. Owner: “Duyệt run plan auto tiến hành đúng vai trò theo methodology @vibecode kit v6”, submitted2026-10-02T13:59:50+07:00, approving the immediately preceding concrete Q1 proposal. Base main `70e2112da9fe8eaa6262f2ba896b55bf3e078260`, tree `6b32f1bc2d13627eba9e915f6fa3c0011b3539e5`. Dependencies: actual M0 PASS, TIP-057R contract/feasibility and Q1 boundary proposal. Requirement mapping: REQ-F10/F11/F15, preparatory F04. Priority: current M1 blocker investigation.

## Task and roles

Contractor writes this output contract, coordinates and verifies; Builder implements/tests the isolated proof and returns a Completion Report. Reuse the focused scan and selected contract rather than re-audit the project. This approval permits investigating the proposed local process boundary; it does not certify or authorize product IPC integration, common-acquisition migration, deployment, Q2 SDK/MT5 effects or weakened strict no-start.

Working directory: `/workspace/scratch/250985b4823e/tip057rq-work`, verified184-blob snapshot of main. Local git parent is synthetic; published GitHub commits must use the exact real main parent above.

Before any Builder code, record YAGNI-3: required to determine if the approved no-start/recovery guarantees can be met; reuse Windows CI, standard Windows primitives and existing native-lease fixtures; write the smallest fixture worker/restriction/ownership proof that can falsify the hypothesis. Implementation choices belong to Builder, with unsupported mechanism assumptions reported rather than claimed as guarantees.

Permitted implementation scope: one dedicated read-only GitHub Actions Windows workflow and isolated `tests/proofs/tip057rq/` proof/fixture files (or an equivalent clearly non-production proof namespace), plus planning/evidence docs. No edits to `app/`, production packaging/dependencies, existing unit tests/workflows or VPS state. No SDK dependency or terminal is needed for Q1. Existing product source/catalog/native signatures remain unchanged.

## Required outputs and Gherkin acceptance

All tests use harmless fixture executables/data and a temporary root. The prevention claim is limited to the paths tested; SDK/broker launch, actual terminal IPC compatibility and production all-entry recovery remain open even if fixture tests pass.

| AC | Given / When / Then |
|---|---|
| Q01 | Given a Windows worker, when native-like fixture work starts, then the preventive restriction is already active; failed setup starts no observation |
| Q02 | Given a stopped/racing fixture target, when the restricted worker attempts child launch, then child never executes or writes its side-effect marker; include unrestricted control so a broken launcher cannot masquerade as success |
| Q03 | Given inheritable privileged handles, broker/breakaway or an uncontained launch path, when boundary assessed, then deny/remove dangerous inheritance where supported or report the exact unsupported path as OPEN; unrestricted administrator flag alone is not strict proof |
| Q04 | Given one observation/initialization false/raise/shutdown fault, when handled, then primary/cleanup outcomes and exact worker ownership remain distinct; zero observed account values returned on unqualified success |
| Q05 | Given a hung fixture worker and observation budget expiry, when terminated/reconciled, then shared fixture ownership is not released before exact worker termination proof; report actual total/termination elapsed, not assumed hard10s |
| Q06 | Given durable intent committed before worker start, when parent crashes before writing failure state, then a fresh fixture caller remains blocked; no dead-PID/absent-failure-marker auto-clear |
| Q07 | Given stale generation, PID reuse/creation-identity mismatch or unresolved descendant outcome, when recovery attempted, then exact expected authority rejects the clear and keeps fixture recovery-required |
| Q08 | Given two simulated conflicting callers and parent restart, when acquire/reconcile races, then no overlapping worker lifecycle and no stale recovery clears a successor; reuse shared native lease in a temporary fixture root |
| Q09 | Given observation never attempted, when an acquired validation/setup phase fails, then exact lease can release with cleanup NOT_ATTEMPTED; failure precedence remains deterministic |
| Q10 | Given Windows CI, when the dedicated job runs, then the relevant real process tests execute (no silent skip-as-PASS), record OS/Python/source SHA, test cases, timing, restriction setup/worker process outcomes and bounded evidence artifact/logs |
| Q11 | Given exact base and candidate, when reviewed, then every production blob and existing workflow/test matches base; proof code is not imported by runtime tools |

If Q03 cannot be established for real broker/library paths in fixtures, return a scoped PARTIAL result with that gate OPEN; do not invent a broad guarantee or provision another environment. A finding that falsifies a candidate mechanism is a useful Q1 output, not permission to relax the policy. If a fixture exposes a repairable implementation defect, refine within this approved scope until its applicable ACs pass, preserving failed CI receipts.

## Delivery and verification

Builder returns DONE/PARTIAL/BLOCKED, file list, YAGNI answers, named AC→test results, primary-source mechanism references, limitations/deviations and suggestions. Run focused local portable checks (Windows-only tests explicitly unqualified locally), then a Draft GitHub PR with a dedicated Windows proof workflow. Contractor checks source/diff and independently reads exact-head CI logs/receipts; all four existing baseline CI workflows must also pass. Keep the PR Draft for review; this task requests a proof report, not production shipping.

No current VPS/MT5/tool call is needed by this fixture-only build. No chart/native/account/credential/AutoTrading/terminal start/stop, runtime PowerShell or deployment occurs. Physical Q2 environment and actual SDK compatibility remain separate reviewed scope. Finish Q1 proof/evidence before presenting any necessary next architecture/pilot decision; do not ask again for the work already approved here.
