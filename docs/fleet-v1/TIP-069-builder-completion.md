# TIP-069 Builder completion — fixture owner and phase observations

Uncommitted review bytes from exact parent
`d9254cd82c996b646ec38d74d2c5467d653f4c84`, tree
`6e3f7d406dd9652e0932155857a18c4530fcc80f`, on isolated
`feat/tip069-fixture-owner-phase-20261006`. Contractor owns publication and the new
candidate gate. Parent original attempt1 remains NOT_ACCEPTED_5_OF8; its failures
are preserved. This change supplies diagnostics, not a behavioral repair.

## YAGNI-3 delivered before code

1. Needed now: preserved capacity guard acquisition/release timeouts lack an owner
phase; Deep correctly denied capture REQUIRE11ms after1000ms expiry; Bootstrap
retained an aggregate10s observation failure alongside its expected wrapper fault.
No causal fixture or production defect was proved. TIP-068 Windows completed
485.578s with full JUnit; that does not explain the older TIP-067 timeout.
2. Reuse: the two existing TIP-064 fixture files, real scoped coordinator/dispatcher,
original calls and observations. No extra RPC/SQL or authority clock is needed.
3. Smallest implementation: finite fixture-local owner/phase/timing observations
with original identity/error retention. No production worker/pool or generic
diagnostic infrastructure is introduced.

## Changes and observation limits

Only `tests/unit/test_tip064_capacity_https.py` and
`tests/unit/test_tip064_integration.py` change source. All original cases and
assertions remain; seven meaningful controls were added.

The capacity observer instruments one initialized coordinator instance and
delegates its original transaction, `_db` and `_validate` once. It records REQUEST,
DB_CONNECT, VALIDATE, BODY, EXIT and FINISH with finite fixture thread ordinals.
DB_CONNECT is observed after the original guard acquisition. EXIT combines the
original commit/checkpoint/close/release region; it does not identify a SQL
statement. No original calls run inside the short data-only observation mutex.
No extra authority guard acquisition, retry, SQL read or connection proxy is added.

Failure capture excludes the failing original context, whose guard has already
exited. Remaining rows are explicitly LAST_OBSERVED_TRANSACTION phases, not a fresh
OS lock-holder query. `since_guard_entry_ms` measures elapsed time since the recorded
entry; particularly for EXIT, it does not prove continuous current OS lock ownership.
If no remaining transaction is observed, the status is UNKNOWN. The latest failure
snapshot survives timeline truncation and is captured before observation cleanup
where possible. A separate owner count and dropped count disclose any owner slice.

The long observer uses the existing native callback/result, `agent.step`, facade
job state read, ACK release, cleanup release, return and drain milestones. It adds
no native proof clock/RPC/SQL read. Its latest safe state/counters and milestone
times survive the32-row latest ring. Both timelines report total/dropped/limit
honestly. Parameter values, raw thread/PID/job/token IDs, paths, SQL, grants,
exception bodies and locals are excluded. Malformed values are omitted.

Observation errors are captured separately so they cannot prevent delegation or
mask an original callback/worker failure. Publication occurs once at the fixture
boundary. Publication/restoration errors join the original identity union; controlled
fault notes remain unchanged. Coordinator methods and the original agent step are
restored after the bounded cleanup/drain attempt. If that attempt raises while
work is still pending, restoration removes observation hooks only; it proves no
drain, closed owner or safe cleanup. Pending work/guards remain UNKNOWN and its
original cleanup error is retained. Existing authorization restoration behavior
is unchanged. Uncertain durable scopes/jobs are retained.

All real positive1000ms lock waits, signed1000ms TTLs,3s worker-return/10s aggregate
and original HTTP/control/hold/SQLite/cleanup/90/600/120 proof bounds are unchanged.
No production, dependency, workflow, clock, guard, ownership or runtime change is
included. Legitimate expiry, lock or deadline denial remains FAIL.

## Meaningful controls and retained development failures

An actual scoped guarded transaction contests itself under a separate controlled
negative100ms wait profile. It proves the BODY transaction observation and timeout
while the holder is still inside its original guard, even after80 timeline rows;
delegation counts, a second untouched instance and restoration are checked. This
does not increase or qualify the real positive1000ms profile. Another actual
validation failure proves that the released failing context is excluded and reports
UNKNOWN rather than a fabricated current owner.

Actual TLS capacity controls combine an original same-callback database fault with
broken record/failure capture and restoration. They retain the exact original cause,
diagnostic/restoration identity union, durable UNKNOWN and ARMED/UNKNOWN scope.
The existing TIP-067 controls continue to cover independent release failure and
the primary/late callback/cleanup union. Long controls verify finite/capped late
milestones, malformed/secret omission, original worker UNKNOWN despite a broken
observer/publisher, one publication and exact step restoration. Existing actual
positive, ACK-before-return and cleanup-release tests now also check these facts.
They consume captured output only after the expected original identity/outcome
checks, preserving raw fixture observations for unexpected fixture failures.

Frozen v1 exposed a bug only in the new control's shared injection flag: another
callback could consume the database fault, leaving the first selected scope CLOSED.
Builder v1 retained **21 PASS / 2 FAIL / 35.77s**; Contractor v1 independently
retained **113 PASS / 1 FAIL / 62.255s**. Neither assertion was weakened. The v2
control pins the flag with `threading.local()` to the exact close callback, so its
fault occurs before that scope's transition and successful finally only changes
its status to UNKNOWN while retaining ARMED. This is a control correction, not an
explanation or fix for the historical Windows failures. Both v1 raw FAIL receipts,
JUnit and exact unchanged source manifests remain preserved.

## Final frozen validation and handoff

Builder v2 passed **23 tests / 0 failures/errors/skips / 31.83s**, with64 deselected.
Contractor independently ran both complete affected files plus source-progress/
runner compatibility with the actual plugin: **114 PASS / 0 skips / 64.100s JUnit**.
The final214-entry source manifests were identical before and after both checks;
the other212 source entries and all89 `app/` entries match exact parent. Both final
source SHA256 values match frozen v2. `git diff --check` passed. These are overlapping
focused checks, not additive coverage or exact-head CI acceptance.

Builder commands, constrained environment, frozen v1/v2 source hashes, raw logs,
JUnit, retained FAIL/PASS receipts, before/after manifests and source diff are in
`docs/fleet-v1/evidence/tip069/builder/`, with a bytes/SHA256 manifest. No fixture
working data is included. Separate Contractor evidence remains in
`resume-20261006/tip069-contractor/v1/` and `/v2/` and is packaged by Contractor.
The Contractor dispatch was copied byte-identically to
`docs/fleet-v1/TIP-069-fixture-phase-observations.md`.

Builder did not run a full source suite, Windows/physical qualification, CI rerun,
commit/push or VPS action. Any new published candidate needs its own original
exact-head8/8 and artifact/head/tree/manifests/JUnit/proof verification. If timing
denials persist without a causal fix, hand over NOT_ACCEPTED with concrete observed
phases and OPEN qualification; do not relax clocks, deadlines or guards.

Historical owner-grant8019, COMMIT/storage/scheduling and old synchronous unit
outcome remain UNKNOWN. Runtime typed reads still fail with raw MCP-32603; current
READY/PIDs/queue/locks/MT5 session remain UNKNOWN. The mixed legacy overlay and old
failed native jobs are preserved. Full Fleet/private VM/two-node/real SDK physical
qualification and production merge remain OPEN/NOT_RUN. Fixture PASS cannot close
those gates.
