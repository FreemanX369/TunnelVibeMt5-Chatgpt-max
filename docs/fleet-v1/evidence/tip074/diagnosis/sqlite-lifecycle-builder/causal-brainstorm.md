# V6 deep lifecycle SCAN — exact ef31

Parent `ef31be719b090c14effa96e69c08d405ac0ceceb`; clean `tip073-candidate`; canonical217 source entries unchanged before/after every probe. No source implementation, CI rerun, policy/TTL/budget/assertion change or VPS/MT5 operation.

YAGNI-3 before diagnostics: ownership leakage must be checked because fixture factories acquire several stores before later construction can fail, and serve_gateway places post-factory initialization/started callback before its cleanup scope. Reuse actual TLS server, original SQLite stores/policies and exact lease observer. Shortest finite controls compare the original failure seams with owned explicit cleanup; no fake database or mocked owner admission is used.

## Ranked measured defects and limits

| Rank | Defect/trigger | Original actual evidence | Owned correction control | Attribution limit |
|---|---|---|---|---|
| 1 | Test fixture factory fails after control/jobs acquisition | Owned existing domain file triggers real `DOMAIN_EXISTS`. TLS server thread exits/socket closes, but both databases remain open, both leases remain held and FD count rises4→12 while original traceback is retained. SELECT1 succeeds in owner thread. | Register each acquired store with ExitStack before the next construction. Both DBs are closed, both leases reacquire and FD count stays4 even with original exception retained. | Proved fixture lifecycle defect; not production gateway_factory or the original checkpoint timeout cause. |
| 2 | Production serve_gateway started callback raises after successful factory | Actual TLS/GatewayController/domain/control/jobs construction, then controlled callback raises. Thread exits/socket closes, but all three DBs remain open, all leases remain held and FD count rises4→16 with original traceback retained. | Owner-scoped cleanup around callback closes all three stores, all leases reacquire and FD count stays4 with the exact original exception retained. | Proved runtime API exception-safety seam; default CLI passes started=None, while test ready callbacks are normally nonthrowing. Historical trigger remains unproved. |
| 3 | Cleanup failure can obscure primary or prevent later closes | Current production gateway_factory has reverse cleanup, but no per-resource catch; serve_gateway's current nested finally can replace a primary with a close failure. | Diagnostic third control closes real resources then models two secondary close errors. ExceptionGroup retains exact primary plus both secondary objects/types; all leases free and FDs4. | Secondary faults are explicitly modeled after real close; no observed Windows close failure is claimed. Require meaningful implementation controls before extending scope. |
| 4 | Domain validation cursor/transaction interferes with checkpoint | Prior actual owned exact-parent probe finds no retained cursor or transaction; checkpoint completes0.052ms, init3.320ms. | Not a correction candidate. | Deterministic own-cursor leak is falsified locally; Windows checkpoint disk/scheduling/owner cause UNKNOWN. |

Both real leak controls release their owned traceback references and run GC only after recording measurements, purely to clean the disposable probe. Original historical evidence is not altered. The socket is closed in both original failure cases, so a stopped thread or closed port alone is insufficient proof that SQLite owners closed. Repeated retained exceptions could accumulate open database/lease handles, but no cumulative cause for the original broad Windows timing increase is established.

## Production versus fixture scope

`app/vibemql5/adapters/fleet_cli.py::gateway_factory` already records acquired resources in `opened` and attempts reverse close on a constructor exception. Do not label its normal partial-construction path as the proved fixture leak. Its secondary-close behavior needs separate controls if included later.

The matching unguarded fixture factory pattern appears in capacity/composed/writer fixtures and the basic transport service. Their acquired stores are placed before the yield or final successful controller return, and server cleanup does not own an incomplete factory. Restore recovery fixture also owns several stores before its yield; that is a candidate requiring a separate measured trigger, not a proven correction in this report.

`app/vibemql5/fleet/transport.py::serve_gateway` obtains the completed controller, sets holder/timeout and calls started before entering its existing try/finally. The measured callback fault therefore bypasses domain/store close. TLS/socket closure still happens via the enclosing Server context manager.

## Minimal proposed next TIP / source boundaries

1. Runtime path: `app/vibemql5/fleet/transport.py` only. Enclose post-factory setup, started callback and serve loop in the controller's lifetime scope immediately after successful acquisition. Close domain/native and store in the owning server thread. Preserve an original error and any cleanup errors; retain all intended existing success/stop behavior.
2. Proved fixture pattern: existing local ExitStack ownership in `tests/unit/test_tip064_capacity_https.py`, `tests/unit/test_tip064_integration.py`, `tests/unit/fleet_writer_fixture.py`, and optionally basic `tests/unit/test_tip058b_transport.py` with acceptance covering actual resource transfer. Register each resource immediately; detach callbacks only after successful controller transfer. Close all acquired owners if any later construction fails.
3. Meaningful new owned controls, preferably in existing `tests/unit/test_fleet_gateway_fixture.py`: early/intermediate/last factory failure, post-factory started failure, unchanged positive serving/stop, retained primary traceback, failure of multiple cleanup callbacks after actual resource close, exact lease reacquisition and no child thread/socket leaks. If a shared fixture helper is used, limit it to existing `fleet_gateway_fixture.py`; no generic owner framework, retries or policy changes.

The primary actual tests use existing control/journal/domain policies. Each diagnostic process has a20-second external bound; measured walls are0.881s,0.681s and0.730s. No constructor or server deadline is widened. The correction controls emulate owner cleanup in disposable diagnostic code only; no implementation is yet authorized/executed.

These defects justify narrow exception-safety corrections. They do not explain the historical Windows restore ERROR, Bootstrap startup snapshot, long-phase HTTP failure, source aggregate IO, live MCP -32603, mixed installed runtime, or permit deploy. Those remain separate gates with their original evidence.
