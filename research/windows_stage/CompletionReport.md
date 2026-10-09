# Scoped exit research v3 — Builder Completion Report

STATUS: DONE — local research implementation and bounded verification. NOT_PUBLISHED; no Windows research run, production fix, deployment or release acceptance.

YAGNI3 before code: (1) 2015 ms exit versus 1000 ms FIFO wait needs attribution before a production change. (2) Reuse v2 observer, original SQLite and guard calls, exact owned thread identities, original three modules. (3) Add only per-thread profile C-call timing to the existing research file, plus meaningful controls; no DB wrapper or extra SQL.

Contract: source 4757afbdd5c8fa399b41ff897c5baaa7a2ed1dfd / tree ce437da748d2eadc16b1221ad516f4104214f404 / 224 hashes; twelve unchanged observation IDs; three modules once, original 600 s subprocess, 90 s faulthandler, 20 minute job. Long cases have no bound scoped coordinator and must report new exit capture NOT_APPLICABLE. No full-suite research run or deployment acceptance.

## Files and measurement boundary

The publication consists of exactly seven research files: this report, `stage_observer.py`, `test_stage_observer.py`, `run_research.py`, `test_run_research.py`, `source-manifest.json`, and `.github/workflows/research-tip075-windows-stage.yml`. No original application, unit test, proof, dependency, configuration or source workflow changes. The runner checks out fixed source4757 independently of the research branch; its exact original224-entry manifest is unchanged.

The v2 observer's original twelve case IDs and exact CONTROL/at most two owned native Thread objects remain. Each owned thread installs/restores its own `sys.setprofile`; no global profiler, unknown profile chaining, remote-thread mutation or service thread. Loaded generator code must equal code compiled without execution from the SHA-verified canonical file, and the frozen original sites must remain executable. C-call filtering uses that exact code object, coordinator identity, guard path object and Connection/Cursor/file identity. No DB/Cursor proxy, SQL/pragma/read, call-argument change, extra OS operation or premature guard release is added by the profiler.

The seven original boundaries are COMMIT371, checkpoint execute/fetch374, rollback377, DB close379, guard unlock187/201 and file close203. C-return/C-exception events pair by exact frame/stage in the current owned thread. Each transaction exit receives a bounded internal per-thread serial and a temporary pending/sum track; the exact generator frame keeps different transactions distinct. No transaction values, arguments, SQL, DB paths, exception values, thread IDs or tokens are serialized. Existing capped64-prefix/64-tail timeline format remains; outstanding pairs cap64, all counters saturate at2^31-1, and cumulative state survives repeated scopes on the same exact Thread.

Unmatched boundaries, a full pending cap, callback/clock faults, unsupported source/profile seams and intervening ownership produce incomplete coverage. An unresolved or incomplete exit does not emit a supposedly complete residual. Callback recording stops before observation teardown. Cleanup only restores while the current profile is the callback; an intervening owner stays intact. `active` reports callback presence, including a disabled callback left installed by a faulty restore setter; `RESTORE_FAULT` keeps recording disabled and the original application outcome. Late original workers use a disabled constant-time callback until their own finally; original fixture join/cleanup bounds remain.

## Fresh verification

Builder evidence is in `scoped-exit-v3-builder-evidence`, separate from immutable prior44-control/3-smoke receipts. Those old receipts do not verify these bytes.

- Final controls: **57PASS,0FAIL,0ERROR,0SKIP**,0.81s pytest summary. Controls cover original Connection/Cursor/file identity and unchanged stable main-DB snapshot; rollback and genuine COMMIT C-error/original exception object, cause and notes; original FIFO ordering and1000ms deadline; foreign coordinator/frame/thread exclusion; existing profile, before/partial installation faults, callback faults, both source/hash and loaded code mismatches, pending/unmatched/clock limits, cumulative reused exact Thread state, finite internal transaction serials, disabled late workers, intervening owner and restoration failure. Harness controls preserve exact three original modules,600s subprocess,90s faulthandler, original failure/timeout/drift status and zero retries.
- Selected smoke: **3PASS,0FAIL,0ERROR,0SKIP**,10.612s subprocess wall time. Exact original control-return capacity case, callback-original `[False]` negative capacity case, and long `[5-1000]` case; no full suite or expanded allowlist. The original1s RPC/FIFO and3s/10s pumps/assertions remain untouched.
- Capacity case8: CONTROL6calls, WORKER_1=60calls/2scopes, WORKER_2=30calls; case9: CONTROL18calls, WORKER_1=30calls, WORKER_2=24calls. Both capture all six normal C-boundaries and residuals, coverageCOMPLETE, faults/unmatched/clock_missing0, callbacks no longer installed. Long case2: coverageNOT_APPLICABLE, C-calls0 on CONTROL and WORKER_1, faults0.
- Original224 source hashes match the manifest before/after, in the clean fixed-source checkout and the draft source worktree; head4757/treece437da unchanged. Research workflow is external to the fixed source. Publication and evidence manifests freeze current payload bytes separately.
- Local-only overhead receipt:24 original transactions each, baseline0.00924s/profiled0.01918s. This includes host scheduling and observation overhead and is not a Windows performance proof.

The first fresh controls attempt retained54PASS/1FAIL: a new restore-fault control incorrectly assumed only three existing outer envelope records, while original `_db`/`_validate` add two more. The corrected control directly compares all added exit-profile stage statistics before/after a surviving disabled callback. Attempt2 retained55PASS; the final57 controls additionally cover both original generator seams. No original assertion was weakened and no failed original Windows job was retried.

## Limits and next action

These C-call durations include descheduling and profiler overhead. Residuals identify unmeasured execution/scheduling, not physical fsync, a particular COMMIT cause or an OS owner. Windows historical failure cause remains UNKNOWN; current source CI remains6/8, NOT_ACCEPTED/NOT_DEPLOYED. Original durability, FULL checkpoint, DB/guard close order, FIFO ownership,1s/3s/10s/600s deadlines, cancellation, exception semantics and UNKNOWN outcomes remain. Physical VM/real SDK qualification remains deferred.

Contractor must independently verify frozen seven files and fresh controls/smoke before CAS publication of a separate research candidate atop PR66head1da02d5e3d1a49db5102088fb233d2a04ab12000, force=false. That publication may launch one new fixed-source Windows research attempt under the existing contract; it cannot clear release CI or authorize a speculative production fix.

ISSUES: no implementation blocker; historical Windows causeUNKNOWN. DEVIATIONS: none in production, scope or deadline. SUGGESTION: inspect fresh Windows substage/pairing/fault/source receipts before selecting any production fix.
