# TIP-068 — source runner test timing observability

Contractor dispatch, 2026-10-06, within the authorized continuous source build.
Parent candidate 806ca44e238cc1384441234d9699cb2dbf3336e8, tree
8ff9579347109eafd214eb98637b0db182490108. Draft PR65 remains OPEN/unmerged;
main remains 70e2112da9fe8eaa6262f2ba896b55bf3e078260.

## YAGNI-3 and evidence

1. Needed now: TIP-067 original attempt1 has seven successful workflows and one
failed integrated workflow. Its Windows full-unit subprocess timed out at600.046s,
exit124, with no JUnit. The log's last test is the new release-failure control[True],
but it has no per-test timestamps. Neither a hang nor aggregate suite exhaustion
is established by that last line. Old failures and raw receipts remain intact.
2. Reuse: the existing exact-source runner, pytest9.1.1 hooks, original log,
faulthandler90s and600s subprocess bound. A bounded scratch probe retained the
raw dump under both existing fd capture and tee-sys. Capture loss was not proven;
there is no justification for changing capture.
3. Smallest change: an opt-in pytest observer enabled only by the source runner
writes finite, flushed test START/FINISH rows with monotonic suite/test elapsed.
No runtime worker or generic pool is introduced.

## Contract and gates

Builder owns implementation and meaningful tests in an isolated worktree from
the exact parent after the above YAGNI response. Contractor reviews independently.
Observer rows contain safe relative source file/function identifiers and timing;
parameter values, local variables, exception bodies, arbitrary paths and secrets
are excluded. Field/row bounds must report truncation honestly. Existing capture,
all unit tests and required harmless proofs remain enabled. Budgets90/600/120,
HTTP/control/hold/cleanup/SQLite deadlines, signed TTLs and guards are unchanged.
No production, dependency, workflow, runtime deployment, account, ownership or
service change is included. No CI rerun substitutes for a new candidate gate.

Validate real pytest child behavior for normal finish, unexpected failure,
controlled timeout preserving unfinished START and the raw faulthandler dump;
also default isolation and finite observation. Preserve raw commands, environment,
logs/JUnit and identical before/after source manifests at frozen bytes. Independent
review and checks precede publication. Any new candidate needs its own exact-head
eight workflows and artifact/head/tree/manifest/JUnit/proof verification.

## Limits and retained blockers

This improves observability; it does not prove or repair the historical Windows
cause, owner-grant8019, COMMIT/storage/scheduling, MCP outage or MT5 IPC.
Runtime read-only MCP errors persist; READY/PID/queue/locks/current session and
the old synchronous unit outcome remain UNKNOWN. No blind suite rerun/restart.
Installed legacy mixed overlay and old failed native jobs are preserved.
Full Fleet/private VM/two-node/real SDK physical qualification and production merge
remain OPEN/NOT_RUN. Fixture PASS cannot qualify those physical gates.
