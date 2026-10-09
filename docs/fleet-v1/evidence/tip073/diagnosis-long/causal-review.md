# TIP-073 long fixture bounded diagnosis

STATUS: PARTIAL. One source-test ownership defect is causally proved. The original Windows delay that caused the first cleanup failure is UNKNOWN. No production or existing-test implementation was changed.

Parent: `ab8ce9891ae8fbb871d5de231a33d05dbb585f90`. Worktree: `/workspace/scratch/b4674f0ac496/tip072-builder`. Diagnosis uses ephemeral owned TLS, synthetic callbacks and fixture journals only. No VPS, MT5, credentials, AutoTrading, main, commit, CI rerun or publication actions.

## Evidence and limits

Original Deep job 112737434903 failed `[5-1000]` with a BaseExceptionGroup retaining both the original aggregate pump failure and cleanup's original 3-second pump failure. Its final observer has a STARTING job, one future and one retained native record. Callback entered at 3484 ms; a control step lasted 5750 ms; cleanup ended at 10452 ms without a completed callback milestone. This establishes unfinished owner work at fixture exit, but does not identify the original slow OS/TLS/SQLite/request boundary.

The immediately following `[10-1000]` completes its own callback and normal owner drain at 8702 ms, yet its test-wide `outcomes` list contains UNKNOWN followed by SUCCEEDED. The original log does not label the UNKNOWN with a job ID, so attribution in that original run remains UNKNOWN.

Unchanged local baseline of the two existing cases: **2 PASS in 12.82 s**. Initial invocation using the default Python could not start pytest; its separate bootstrap-unavailable log/command is retained. The actual baseline uses the existing test-venv.

An external owned pytest plugin gates only the first case's first fresh-intent entry before its original `begin_effect` call. The gate is released after the next case has installed its original outcome observer. Gate maximum is 20 seconds, the subprocess maximum is 45 seconds; the original cases' 5/10-second aggregate observations, 3-second cleanup, 5-second RPC policy and 1000-ms signed TTL remain unchanged. No intent is retried, proof TTL extended, unknown relabeled, retained record removed or error hidden.

Modeled causal run: **2 expected diagnostic FAIL in 14.60 s**, reproducing both original failure shapes. Its exact ownership receipt is:

| Stage | Observer | Journal owner | Job | Outcome |
|---|---:|---:|---|---|
| First fixture returns and teardown follows | 0 | 0 | `fjob_31220d7d74574515a28f18701c640c09` | Worker still unfinished |
| Next outcome observer installed; gate released | 1 | 0 | Same first job | Original worker continues |
| Next test observes original first worker | 1 | **0** | Same first job | **UNKNOWN / EXECUTION_OUTCOME_UNKNOWN** |
| Next test observes its own worker | 1 | **1** | `fjob_046b20e9c96f432fadd1260f61e62b24` | **SUCCEEDED / SYNTHETIC_NATIVE_ONLY** |

The first journal's UNKNOWN is valid and was preserved. The defect proved is the next test's class-global observer incorrectly collecting a different fixture's valid outcome. The next test's own job succeeded and drained. At final observation the first dispatcher still retains one native record and one already-done future; neither is erased or reported as closed.

This models a specific unfinished-worker ordering and proves the cross-fixture mechanism. It does **not** prove that this exact boundary caused the original Windows slowdown, that the original Windows UNKNOWN belonged to the same prior job, or that fixing observation ownership alone repairs the first case's cleanup.

## Smallest proposed correction and YAGNI-3

1. Does it need to exist? Yes: class-global `NodeJobJournal.begin_effect`, `complete_effect`, `_outcome` and `NodeRpcProxy._request` fixtures can be observed by a worker retained from a previous failed fixture. The owned probe proves an invalid cross-case outcome assertion.
2. Can existing code be reused? Yes: retain `runtime`, `run_long_fixture`, the same NodeJobJournal and per-agent rpc_proxy, all existing callbacks, finite diagnostics, owner drain and exact assertions. Bind callback instrumentation to those owned instances instead of classes shared by all workers.
3. Shortest implementation? Add one small instance instrumentation seam in this test helper, bind the existing held begin/complete/outcome/request wrappers to the created job journal and rpc_proxy, and add a finite control showing a foreign journal cannot enter the current fixture's observed outcomes. Preserve the foreign journal's valid UNKNOWN. Do not change production logic, expected outcomes, wait budgets, grant TTL, protected evidence or authority.

That bounded test-instrumentation correction requires Contractor authorization. First-case cleanup needs a separate causal step: retain finite queue-entry/service-entry/RPC-return and phase BEGIN/REQUIRE/completion timestamps, with actual journal/fixture ownership, before choosing a timing or production correction. The original ring lacks those request-level facts. Raising budgets or changing the expected exception group to make CI green would not resolve the unknown cause.

## Frozen files and verification

`baseline-command.json` and `modeled-causal-command.json` retain the exact commands, cwd, PYTHONPATH override, process timeout, exit and wall duration. Raw logs and JUnit preserve both results. `modeled-causal.json` identifies job ownership and event order without retaining keys, tokens or certificates. `source-before.json` and `source-after.json` cover 188 non-cache files under app/tests/.github and are byte-identical. This scoped file count is not the canonical full-source manifest count. Git remains clean at the exact parent head. No implementation delta or new candidate was produced.
