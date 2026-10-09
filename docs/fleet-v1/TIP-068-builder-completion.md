# TIP-068 Builder completion — bounded source test progress

Builder implementation from exact parent
`806ca44e238cc1384441234d9699cb2dbf3336e8`, tree
`8ff9579347109eafd214eb98637b0db182490108`, on the isolated
`feat/tip068-source-progress-20261006` worktree. These are uncommitted review
bytes, not a published or accepted candidate. Contractor owns independent review,
publication and a new exact-head gate.

## YAGNI-3 before implementation

1. Needed now: the original TIP-067 integrated Windows unit run exited124 after
600.046s without JUnit. Its final unfinished test line has no elapsed timing.
The original cause remains UNKNOWN; that line proves neither a fixture deadlock
nor aggregate suite exhaustion.
2. Reuse: the existing source runner, pytest hooks, original capture/log and
90/600/120 second bounds. The bounded scratch capture probe preserved the raw
faulthandler dump with both fd and tee-sys. Capture loss was not established, so
capture stays unchanged.
3. Smallest change: an opt-in source test progress plugin with flushed START and
FINISH rows, monotonic elapsed time, safe identifiers and a finite row limit.
There is no production worker, pool or runtime change.

## Implementation and retained behavior

`tests/proofs/fleet_v1/run_source.py` enables `fleet_source_progress` only for its
existing full-unit subprocess. The four portable/Windows harmless proof commands,
all original assertions, cases, capture and timeout bounds remain unchanged.
The existing runner regression test checks this opt-in scope and unchanged capture.

`tests/unit/fleet_source_progress.py` emits ordinal, suite/test elapsed milliseconds,
literal relative `tests/unit/*.py` file and `test_*` function names. Parameter data,
class names, arbitrary paths, locals and exception bodies are omitted. Input IDs
are bounded at4096 characters; accepted file/function components are bounded at96
characters. At4096 progress rows, one finite TRUNCATED marker is flushed and later
rows are omitted honestly. FINISH starts UNKNOWN until an actual passing call
report; setup, call or teardown failures retain FAILED. An interrupted test retains
its START without an invented FINISH. Terminal flush exceptions propagate through
pytest rather than yielding a false unit PASS.

`tests/unit/test_fleet_source_progress.py` runs disposable real pytest children for
PASS, FAIL, SKIP and setup/teardown errors, verifies their actual exit codes and
JUnit, and checks default plugin isolation. A controlled sleeping child must emit
a complete flushed START within20s before the parent's0.5s controlled timeout;
its unchanged raw faulthandler dump is retained. Cleanup kills only that owned
child and waits at most5s. Its30s sleep is a disposable test control, not a change
to source/runtime budgets. Live readiness ignores only an incomplete final row;
malformed complete rows still fail. Further controls cover malformed/oversized
identifiers, parameter omission, row cap/flush, and honest UNKNOWN without a call
report. Child subprocesses use isolated fixture cwd/PYTHONPATH, disable ambient
plugin autoload and omit ambient pytest options/plugin/current-test variables.

## Frozen validation

Final v3 source bytes were frozen before the focused run. It passed **27 tests,
0 failures/errors/skips, 4.56s**, using the existing constrained Python3.12.14 /
pytest9.1.1 environment. The 214-entry source manifest was identical before and
after this run. Relative to the212-entry parent, only the existing runner and its
test changed; the plugin and its test are two new entries. All89 `app/` entries
remain byte-identical. `git diff --check` passed. The six existing runner cases
remain present; the new progress module supplies21 controls.

Earlier retained focused receipts are v1 **23 PASS / 2.81s** and v2 **26 PASS /
4.42s**. These are overlapping development checks, not additive coverage. v3 is
the final frozen validation. v2 post-run manifest equality was not separately
captured before the readiness-parser refinement; no such claim is made.

Contractor subsequently verified the same frozen four source hashes independently:
the plugin-enabled focused selection plus both existing TIP-067 capacity release
controls passed **29 tests / 7.31s**, with214 identical before/after manifest entries
and58 flushed outer START/FINISH rows. The eight child JUnit files retained their
expected controlled failures/errors/skips, and the interrupted child retained one
unfinished START plus the raw dump. This is focused source review acceptance only;
the new candidate's exact-head CI gate remains pending. Contractor retains its
separate commands/log/JUnit/manifests in `resume-20261006/tip068-contractor/`.

Exact commands, lock environment, final hashes, raw focused log/JUnit, before/after
manifests, source diff, nine real child command/log fixture receipts (eight completed
child JUnit files; the deliberately interrupted child has none) and the negative
capture probe are preserved in
`docs/fleet-v1/evidence/tip068/builder/`. All v1/v2/v3 scratch receipts remain in
`resume-20261006/tip068-builder/`; original failed CI receipts remain untouched.

## Limits and handoff

No full source suite, Windows qualification, CI rerun, commit/push, production
edit, dependency/workflow change or VPS action was performed by this Builder.
The historical TIP-067 candidate remains NOT_ACCEPTED_7_OF8, and its Windows
timeout cause remains UNKNOWN. This change adds observability; it does not repair
or prove that cause. Contractor must review frozen bytes independently and any
new published candidate needs its own eight exact-head workflows plus artifact,
head/tree, unchanged manifest, JUnit and harmless proof verification.

Runtime typed reads remain blocked by MCP-32603. The old synchronous unit run has
no receipt; READY/PIDs/queue/locks and current MT5 session remain UNKNOWN. The mixed
legacy overlay and two old pre-tester IPC-failed native jobs remain preserved.
Full Fleet/private VM/two-node/real SDK physical qualification and production merge
remain OPEN/NOT_RUN. Disposable fixture PASS does not qualify those physical gates.
