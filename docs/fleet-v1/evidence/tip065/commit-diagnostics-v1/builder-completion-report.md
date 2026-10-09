# TIP-065 COMMIT diagnostics — Builder Completion Report

STATUS: DONE for the approved bounded diagnostics and controls. Historical performance/timeout cause and exact next-candidate source acceptance remain OPEN. No publication, live write, restart, deployment, merge, credentials/account/AutoTrading action or physical MT5/SDK action occurred.

Base HEAD: `f2b65c35cb1c31e523d365c75ae4be328df19476`; tree: `825af88b97eca3b1a8f32749c4614f140e167d96`. Contractor retains the rejected 6/8 checkpoint, five exact-source ZIPs and its full logs. Bootstrap run `37282913896`, job `111674932726` recorded 1182 PASS / 2 FAIL / 12 skip. Integrated Windows artifact `11332984886` recorded 1183 PASS / 1 FAIL / 12 skip. Those failed receipts remain unchanged.

## YAGNI-3 before code

1. Necessary: the failing three-step wall assertion lacks a request breakdown; the previous controlled timeout delayed the response only after COMMIT and did not prove pending-COMMIT uncertainty.
2. Reuse: existing FixtureHttpsClient, bounded server stack observations, actual TLS service and stop/closure helpers, actual FULL/WAL SQLite connection, read-only snapshot and supported store reopen.
3. Shortest change: two existing test files only. Add finite safe POST observations around the original phase and one selectively held real grant COMMIT invocation. Keep literal `<1.5`, HTTP 1000 ms, RPC rounds, SQLite and fixture hold/closure budgets. No production optimization, retry, authority reset or weaker qualification.

## Files and behavior

| Modified file | Behavior |
|---|---|
| `tests/unit/test_tip058b_transport.py` | Finite ControlPostObservation plus restoration/error-identity/redaction/32-row controls; new pending grant COMMIT control alongside the retained after-COMMIT response-drop control. |
| `tests/unit/test_tip064_capacity_https.py` | Observes exactly the existing three-step phase. The original literal `assert time.monotonic() - began < 1.5` remains. On failure, appends a safe breakdown to the original error and re-raises the same error. |

The observer forwards original positional/keyword arguments exactly once and returns the original result object or raises the original exception object with its original notes intact. It restores inherited or instance-overridden post methods on success and failure. Route classification accepts only exact strings from a finite map; other/invalid/unhashable input becomes OTHER without hashing or stringifying it. Rows contain only route class, elapsed milliseconds and RETURNED/WIRE_ERROR/OTHER_ERROR, capped at 32. Total POST count and truncation remain explicit. No request body, headers, URLs, IDs, credential, key or exception text is emitted. Controlled sensitive markers are absent from observations.

Capacity failure notes include total elapsed, observed POST count/time, time outside those observed POST calls, truncation/rows, callback count, release/completion flags and pending-worker count. The remainder is **outside observed POST time**, not a claim that it was disk or journal latency. Observation makes no additional HTTPS request or state lookup, changes no deadline and adds no retry. The context restores post before existing cleanup runs.

## Pending COMMIT evidence

The test-only proxy delegates to the same actual SQLite connection. The first commit persists observed wall time; only the second commit invocation, for grant publication, is held before delegation. It does not replace SQLite, alter pragmas or claim a measured OS fsync delay.

At the held boundary, server-thread evidence proves actual `synchronous=2` (FULL), WAL and an active transaction with pending revision 2. A separate read-only SQLite view, opened/closed on that server thread using the existing 100 ms busy profile, sees committed revision 1, no grant/operation and the already persisted observed wall time. The owner POST is called once. Client receives actual HTTPS_UNAVAILABLE with TimeoutError under the unchanged HTTP 1000 ms cap; the safe server stack contains the held proxy commit invocation. Before finally release, grant delegation count is zero and the actual grant has not committed.

Finally releases the finite hold, delegates the actual grant COMMIT once and uses the existing three-second stop helper to reap the actual event owner. The real store handle is closed before reopen. Reopening that same temporary store confirms revision 2, exactly one grant and one operation, no device/nonce, and an unconsumed grant. No grant/CLI retry, recovery, reset or speculative absence claim occurs. Existing after-COMMIT response-loss behavior remains independently tested.

Retained first-run stdout:

```text
PENDING_COMMIT_FIXTURE: grant_delegations=0; FULL=2; WAL; transaction_pending=true;
pending_revision=2; committed_revision_before=1; wall_persisted=true;
committed_grants_before=0; committed_operations_before=0.
CONTROLLED_PENDING_GRANT_COMMIT_EXACTLY_ONE_DURABLE_EFFECT:
grant_delegations=1; commit_calls=2; transaction_pending_after=false;
same_connection=true; owner_thread_matches=true.
```

The control demonstrates the **pending COMMIT call → client timeout → later durable one-effect outcome** mechanism. It does not identify the historical CI COMMIT duration, device/storage behavior or scheduling cause.

## Tests and frozen identity

```bash
PYTHONPATH=app:tests/unit /workspace/scratch/1818a0d45fa0/deploy-20261005/source-venv/bin/python -m pytest -q -s \
  tests/unit/test_tip058b_transport.py \
  tests/unit/test_tip064_capacity_https.py \
  tests/unit/test_tip064_integration.py \
  tests/unit/test_fleet_gateway_fixture.py \
  --junitxml=/workspace/scratch/1818a0d45fa0/tip065-commit-diagnostics-20261005/focused-v1.xml
```

Working directory: `/workspace/scratch/1818a0d45fa0/repo`. Isolated locked environment: Python 3.12.14, pytest 9.1.1, MCP 2.1.1, cryptography 50.0.1.

First focused run: **111 PASS / 3 explicit Windows skips / 0 FAIL / 0 ERROR**, pytest 21.95 seconds; exit 0. Both capacity ordering modes, normal CLI grant/pair cases, actual stop/error preservation, existing negative transport deadlines and both COMMIT-boundary controls passed. All **210 canonical source hashes** match before/after the run. No failed first run was discarded, no second run was needed, and no source edit followed this freeze. `git diff --check` passes.

Captured stderr retains expected diagnostics from the existing intentional TLS-disconnect/response-drop controls. JUnit contains no teardown error; actual server closure and failure-queue checks pass. Three skips are existing actual-Windows key/ACL/staging controls and are not Windows qualification.

| Frozen Builder file | SHA-256 |
|---|---|
| `tests/unit/test_tip058b_transport.py` | `a78695dab5c7361d83ca00a545ade66f7097423a700b1f74d7d875d401d8665a` |
| `tests/unit/test_tip064_capacity_https.py` | `a0d8587242a617007a034113075c7ed3d30ee0d142ebbb670e2f6b782b776a6c` |

All tracked app/product bytes, TIP-065 observer/validator/provenance/CLI/MCP integration and preflight test, dependencies, workflow/operator inputs and deployment overlay provenance are unchanged from the base HEAD. Only the two approved test sources differ in the canonical source manifest. Contractor-owned Markdown/evidence work is separate.

Evidence: `focused-v1-source.json`, `focused-v1-receipt.json`, complete log/JUnit, baseline two-file bytes, `builder-two-file.diff` and `frozen-source-manifest.json`. They bind exact commands, selected environment, hashes and incident-log provenance. This is local test-only diagnostic evidence, not full exact-head CI or physical qualification.

## Issues, deviations and suggestions

Historical Bootstrap grant timeout and integrated cleanup nonce timeout were observed at COMMIT; the capacity wall values were 5.375 and 3.813 seconds. Why those historical commits/steps exceeded their bounds remains **OPEN/UNKNOWN**. At least six signed HTTPS calls plus node begin/ACK and gateway observed-wall/nonce commits contribute to the three-step wall time; the new notes can establish their actual breakdown on the next failure. The existing negative/positive timing assertions and actual owner failure remain required.

No equivalent product optimization was implemented. Separate observed-wall durability preserves clock/crash defense. Diagnostics are not a historical root fix; eventual 8/8 can qualify only the new exact source/artifacts. Physical performance, migration, MT5/SDK qualification, optional Fleet process registration and whole source activation remain separate; preflight activation remains NOT_QUALIFIED and physical qualification NOT_RUN.

DEVIATIONS: none. SUGGESTION: independently review these frozen two-file changes and controls, then decide whether a single evidence-driven diagnostic source candidate is justified. Do not publish documentation alone or rerun the failed checkpoint to infer a functional fix.
