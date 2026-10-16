# Bounded Windows storage-path crossover

TIP input parent: d73833cffe72d2d3d3eae2d88613a30181d347b3,
tree27b1f990e83e839321459a26a7ea30a4e48910c6. That full Windows run is
terminalFAIL1623PASS/2FAIL/12SKIP,674.329s/no timeout, while focused14 and
Linux full passed. The failures changed from the parent revision.

The long wrapper failure contains one original control step9250ms, callback
completion7297ms, initial aggregate10 pump failure11719ms, then cleanup release
and nativeSUCCEEDED11937ms without ACK_RELEASE. The other case has an
unexpectedHTTPS_UNAVAILABLE whose traceback is hidden by an error-union assert.
These observations do not prove a defective disk, antivirus cause or deadlock.

YAGNI: test the concrete storage-path hypothesis before another product/fixture
patch. Reuse the exact existing runner, receipts, source manifest and original
test cases. This is a one-off research script, not a new scheduling service.

Run one fresh disposable Windows CI VM with three sequential arms:

1. C1: private directory under the original default temp root.
2. D: private directory under RUNNER_TEMP, required to be a different observed
   st_dev. This identifies a distinct filesystem volume, not physical hardware.
3. C2: another private directory under the original temp root.

Each arm first runs eight harmless SQLite DELETE/FULL commits in an owned child
cap30, then the same four original tests in a fresh pytest child cap120. The
selected cases are scope_broken[record], long_wrapper[timeout-1000], guarded
source positive and TIP077 positive. The second C arm is a declared crossover
replicate for order effects, never an automatic retry or replacement outcome.

All application/test/runner/dependency bytes stay at d738. Only this workflow,
script and contract are added. Original HTTP1/5, TTL1000/max2000, pump10,
worker-return3, sleeps, assertions and original scheduling remain unchanged.
Set TMP/TEMP/TMPDIR only for the new children; keep original inherited Windows
ACLs and guard checks. No ACL changes, basetemp override or security exclusion.
No physical Fleet, SDK, MT5, account, credential or authority mutation.

AC: exact head/tree, expected source235/APP89, pre-dispatch source/input records,
all three arm receipts and4-case JUnits, no hidden retries; preserve every FAIL.
Continue after pytest failure only with exit0/1 and direct-childEXITED; abort on
timeout/unknown closure, malformed JUnit, evidence error or source drift.
Direct-child receipts never attest descendants. Source acceptance is not granted
even if all12 arm cases pass; this does not replace full suite or eight CI gates.

A C1-fail/D-pass/C2-fail pattern with latency differences supports a path
association but does not establish an internal storage cause. All-pass means
NOT_REPRODUCED; mixed results retain uncertainty/order confounds. No automatic
fixture-contract amendment or timeout increase follows any outcome.

Publish as a separate research PR targeting research/release-resume-20261014-r1.
The old full-context and diagnostic workflows target the implementation branch,
so this experiment must not silently launch another full suite. Freeze inputs
and save the contract before creating the PR. Main/PR65/runtime remain unchanged.

## Parser correction, distinct frozen revision

Attempt38700825701/a0e861a is retained as HARNESS_ERROR/JSONDecodeError.
Its C1 IO child exited0, but run_case appends SOURCE_CASE_FINISHED after the
JSON payload; reading the last line was incorrect. No original tests or D/C2
arms were dispatched. Artifact11955513590 and source/research before-after are
verified. It is not a C-versus-D result or a product failure.

The corrected child emits one STORAGE_IO_OBSERVATION-tagged JSON record.
Parsing selects exactly one tagged record and validates schema/sample count,
ignoring the real runner footer. Pure-data framing controls use the recovered
log and cover footer, missing, duplicate, malformed and schema-invalid records.
All experiment arms, product bytes, windows and caps remain unchanged. Publish
only after saving this new freeze; use a fresh run_id, not a rerun of a0e861a.
