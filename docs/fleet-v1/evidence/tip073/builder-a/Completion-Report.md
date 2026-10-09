# TIP-073A Completion Report

STATUS: DONE for the bounded fixture-instrumentation contract. Full source release, original Windows timing/cleanup root cause and runtime deploy remain OPEN.

Parent `ab8ce9891ae8fbb871d5de231a33d05dbb585f90`; isolated worktree `/workspace/scratch/b4674f0ac496/tip073a-builder`, branch `fix/tip073a-owned-fixture-instrumentation`. No commit/publication was made.

## Change

Only `tests/unit/test_tip064_integration.py`, inside `test_long_fixture_valid_finite_schedule_requires_aggregate_observation`, changed. Its four existing begin/complete/outcome/RPC wrappers now bind to the created fixture's journal and rpc_proxy through an owned runtime wrapper. Their callback bodies, all six assertions, decorators, arguments and original test control-flow tail remain AST-identical. The whole module AST outside that function is unchanged. No new collected tests were added, so canonical source remains 217 entries and full suite case count remains unchanged.

YAGNI-3: ownership isolation is needed because retained foreign workers can enter class-global instrumentation; existing runtime instances and callback functions suffice; binding those functions to the owned objects is the shortest correction. No service, API or journal behavior changed.

Frozen changed source is 97,723 bytes, SHA256 `dc406d668c092d168094614cfe88e6a5849d36ac8f026ef124fa56792d93f6be`. `frozen-test_tip064_integration.py` contains those exact bytes; `implementation.diff` is the exact parent delta; `candidate-source-manifest.json` contains all canonical 217 source hashes.

## Verification

| Check | Result | Limit / scope |
|---|---|---|
| Unmodeled existing two cases after correction | 2 PASS | 45-second local process bound; original case observations 5/10 s and cleanup 3 s |
| Same external retained-worker probe on parent | 2 diagnostic FAIL | 14.86 s; original first primary+cleanup group; second foreign UNKNOWN + owned SUCCEEDED |
| Same external retained-worker probe after correction | 1 diagnostic FAIL / 1 PASS | 15.42 s; first original primary+cleanup failure remains; second exact own-outcome assertion passes |
| Foreign actual-Journal and actual-RPC control on parent | 1 diagnostic FAIL | 7.94 s; foreign BEGIN/COMPLETE each incorrectly incur current 700-ms hold |
| Same foreign activity control after correction | 1 PASS | 7.14 s; foreign calls preserve exact JournalErrors without current holds; successful harmless foreign RPC does not enter current request list |
| Whole existing TIP-064 module | 75 PASS, 0 skip, 0 fail | 30.97 s; 180-second local process bound; source before/after unchanged |
| Canonical source scope | PASS | 217 source entries; exactly one test file changed; production/workflow/dependencies unchanged |
| AST and diff check | PASS | Original six asserts, four callbacks, args, decorators, control-flow tail, outside-function AST unchanged |

These counts overlap; the whole-module 75 cases include the same existing two controls. Diagnostic failures are expected probe observations, not source-gate PASS claims. No old CI job was rerun.

`causal-green.json` still records the first fixture's real `UNKNOWN / EXECUTION_OUTCOME_UNKNOWN`, attributed to owner 0 and a different job from owner 1's SUCCEEDED. Both remain visible in independent evidence. First fixture still retains a done future and one native record; the probe neither erases that record nor labels it closed. Its synthetic boundary gate is finite and explicitly modeled. Original Windows scheduling cause remains UNKNOWN.

Actual foreign begin, complete and outcome controls preserve `JOB_UNKNOWN`, `NATIVE_AUTHORIZATION_UNVERIFIED`, and `JOB_UNKNOWN`, respectively. The foreign RPC uses a real NodeRpcProxy queue and a harmless finite consumer response, with no network authority issuance. The main test's exact own hold count 6, RPC count 5, sole SUCCEEDED outcome and original protocol/TTL/ACK assertions remain unchanged and pass after isolation.

## Evidence / issues / deviations

Raw logs, JUnit, exact command/environment/timeout receipts, ownership JSON, full 217-file before/after manifests, frozen source and scope AST receipt are top-level evidence payloads. Ephemeral fixture TLS certificates/keys, journals and temp folders are not selected for publication. No credentials or principal keys are exported.

No implementation deviation from the contract. External V2 gate instrumentation was adapted to operate after runtime creation because the correction intentionally removes class-global hooks; the same V2 script was then executed on both exact parent and candidate. The original V1 causal evidence remains untouched in the diagnosis folder.

Remaining issue: TIP-073A fixes proven cross-fixture instrumentation contamination only. It does not fix or conceal the original first-case cleanup failure under Windows scheduling pressure, the separate capacity failure, or live MCP `-32603`. Further corrections require their own causal evidence. All original .7-second holds, 5/10-second aggregate limits, 3-second cleanup, 5000-ms RPC/profile policy, 1000-ms grant TTL, outcomes, authority and evidence semantics are preserved.

SUGGESTION: Contractor independently replay the unchanged external V2 probe against parent and frozen candidate, inspect foreign activity receipt and source AST scope, then combine only accepted test refinements with separately verified finite timing observations. Do not label the full Windows gate solved from this bounded result.
