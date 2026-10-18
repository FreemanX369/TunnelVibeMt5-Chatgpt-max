# TIP-069 — bounded fixture owner and phase observations

Authorized continuous source refinement, 2026-10-06. Parent exact
d9254cd82c996b646ec38d74d2c5467d653f4c84/tree6e3f7d406dd9652e0932155857a18c4530fcc80f,
original attempt1 NOT_ACCEPTED_5_OF8. PR65 Draft OPEN/unmerged, main70e2112 unchanged.
Builder read the complete three failure sections and delivered YAGNI-3 before code.
Contractor read the full Builder proposal and approves this diagnostic scope only.

## Evidence and YAGNI-3

1. Needed now: preserved capacity callback/release guard timeouts lack holder/phase;
deep REQUIRE denies11ms after1000ms expiry; bootstrap aggregate pump fails alongside
the original controlled wrapper fault. No causal fixture or production bug is
proved. TIP068 Windows completed485.578s with complete JUnit, not a600s timeout;
both release controls pass, without explaining the retained TIP067 timeout.
2. Reuse the two current TIP064 fixture files, actual coordinator/dispatcher,
original transaction/database/validation calls, callbacks and existing state reads.
3. Add finite fixture-local owner/phase/timing observations. No production fix,
generic worker/pool, SQL proxy, extra RPC/SQL/authority calls or changed guard.

## Implementation contract

Builder owns implementation/tests in a new worktree from exact parent. Only
test_tip064_capacity_https.py and test_tip064_integration.py change source.
Instrument the actual coordinator instance after initialization, delegate original
transaction/_db/_validate exactly once; observe wait/hold and REQUEST/DB_CONNECT/
VALIDATE/BODY/EXIT/FINISH. EXIT is the combined commit/checkpoint/close/release
region, not evidence of an individual SQL statement. Use bounded fixture ordinals,
never emit thread/PID/job/token IDs, paths, SQL, grants or locals. Preserve a latest
owner/phase snapshot and counters even if the32-row timeline is truncated. Unknown
owner stays UNKNOWN. No acquisition/retry/read is added.

Long observations use the existing native result, agent.step, facade state read,
ACK release/cleanup release/return milestones and pending counts. No extra state
read or native proof clock. Publish finite safe observation once at the fixture
boundary; do not alter controlled fault notes. Diagnostic/restore failure cannot
mask original errors and joins their exact identity union as appropriate. Restore
only after the actual bounded owner drain; leave pending/UNKNOWN evidence intact.

Clocks/1000ms signed TTL/1000ms real positive lock/3s return/10s aggregate and
HTTP/control/hold/SQLite/cleanup/90s dump/600s full-unit/120s proof are unchanged.
All existing cases/assertions and failure groups remain. No behavioral repair,
expiry reclassification or source/runtime stability acceptance is claimed.

## Checks and handoff

Meaningful controls include actual guarded contention with finite controlled wait
profile, owner/phase observation, exact failure/group/ARMED+UNKNOWN retention,
per-instance delegation/isolation/restoration, safe capped output and actual long
ACK/return/cleanup ordering. Freeze source before focused checks; preserve complete
commands/environment/log/JUnit and identical source manifests. Contractor reviews
and verifies independently before publication. New candidate needs own exact-head
8/8 and artifact/head/tree/manifests/JUnit/proof/control gates. No same-head rerun.

If further legitimate timing denials remain without a causal fix, hand over
NOT_ACCEPTED with concrete receipts and OPEN qualification; do not relax clocks,
budgets or guards to close the gate. Retain every original failure. Runtime typed
reads remain raw-32603, old synchronous unit and current guards UNKNOWN; no effects.
Mixed legacy overlay/old failed jobs persist. Full Fleet physical/private VM/
two-node/real SDK and production merge remain OPEN/NOT_RUN.
