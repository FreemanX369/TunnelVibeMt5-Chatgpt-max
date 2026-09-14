# TIP-033RC1 qualification evidence

Status: **SOURCE + RUNTIME QUALIFIED; CONNECTOR REFRESH REQUIRED FOR FIVE NEW ADMIN TOOLS**

## Candidate identity

- Bridge version: `0.2.34`
- Bridge build: `TIP-033RC1`
- Server catalog: 72 tools
- Catalog SHA-256: `c3457dce5ad2e1e4461f49786a01278f45e10e411c301c447a6905b7f3eef670`
- Fixed terminal: `MT5-2`
- Latest observed MT5 build: `6182`

## Confirmed defects fixed

1. `launch_test_v2` forwards arguments through the keyword-safe legacy wrapper and preserves `operation_id`.
2. Continuity transition validation rejects illegal state jumps and duplicate assignment.
3. Continuity verification checks semantic replay and current runtime/source authority; drift forces `resume_safe=false`.
4. Backend checkpoint restore requires complete per-target current-SHA CAS and validates every target before the first write.
5. Terminal inventory distinguishes configured build from latest native observed build.
6. Runtime-forensics binary authority errors are reported as `BINARY_AUTHORITY_REQUIRED` / `BINARY_AUTHORITY_MISMATCH`.
7. Lock-only project-session directories are reported as `ORPHANED`, never resumable.
8. Backend tunnel administration is allowlisted to instances A/B and exposes no generic shell.

## Automated verification

Executed on the candidate VPS source:

- `py_compile`: PASS
- Full unit suite: **395 passed**
- Runtime-forensics focused suite: **7 passed**
- TIP-026 focused suite: **30 passed**
- Baseline-aware suite: **395 passed**, baseline failures 0, current failures 0, new failures 0

A transient HTTP 504 occurred while the runtime was refreshing; the unchanged suite passed on retry and is not an application test failure.

## Live MCP acceptance

Operation ID: `TIP033RC1-LIVE-V2-20260915-A`

- Job: `BT-20260915-003606-DEABB5`
- First launch: queued and spawned
- Exact replay: same job recovered, no second spawn
- Same operation ID with changed request: rejected `INVALID_ARGUMENT`
- Terminal state: `PASSED`
- Compile: 0 errors, 0 warnings
- Native MT5 build: 6182
- Effective terminal: MT5-2; fallback false
- Period conformance: PASS
- Cleanup: PASSED; terminal reconnected
- Result anomalies: none
- Runtime after acceptance: READY / watchdog HEALTHY / one tunnel process / zero queue / no native or mutation lock

## Continuity acceptance

Live verification of the pre-release canonical project correctly returned:

- integrity: `VERIFIED`
- semantic integrity: `VERIFIED`
- authority freshness: `DRIFT`
- `resume_safe=false`

The stored session authority predates TIP-033RC1, so the drift is expected and must not be silently rewritten before promotion.

## Connector exposure gate

The running server advertises all 72 tools, including five `tunnel_admin_*` tools. The current ChatGPT connector schema exposes the prior 66 model-visible tools and therefore cannot invoke those five tools in this already-open connection. It also retains the older `backend_restore_checkpoint(checkpoint_id, paths)` schema instead of the new required `expected_current_sha256_by_path` CAS map. Source/runtime registration is present and unit-qualified; release acceptance still requires reconnecting/refreshing the connector after promotion, confirming all 71 model-visible tools, and confirming the updated restore schema.
