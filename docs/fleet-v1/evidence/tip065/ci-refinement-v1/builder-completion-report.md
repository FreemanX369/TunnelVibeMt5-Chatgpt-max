# TIP-065 CI refinement — Builder Completion Report

STATUS: DONE for the two bounded fixture corrections and their controls. New candidate 8/8 CI acceptance remains OPEN; Contractor owns independent verification/publication. No live write, deployment, merge, account, credentials, AutoTrading or physical MT5/SDK action occurred.

Base HEAD is `ec9180e15e840a7d4a3af18f78ce9bee1f4db582`, tree `66022a510d6d59285c9250d75aa83e038cad24b0`. Retained failure is Bootstrap run `37279566868`, job `111664200582`: 1178 PASS, 2 FAIL, 12 skip. Its complete decoded log remains at `../final-evidence-ec9180e/metadata/bootstrap-failed-job-decoded.log`, SHA-256 `b0b6cfe751ce482cebebf0f378aa0bb8b448c9cbd2ada24d0df2ff7279554b46` (63697 bytes). Contractor separately retains the final eight workflow receipts and five verified source ZIPs under `docs/fleet-v1/evidence/tip065/ci-ec9180e`.

## YAGNI-3 before code

1. Necessary: the current candidate fails its 8/8 gate, the resource fixture assumes an unsafe scheduling order, and an incompletely initialized manual NodeRuntime fixture masks the primary HTTPS failure during cleanup.
2. Reuse: keep real queued native leases and OwnershipAuthority/ResourceAuthority validation, actual NodeRuntime stop methods, existing `preserve_fixture_failure`, and the existing independent FIFO and shared RPC deadline tests.
3. Shortest correction: change only the two implicated test files. Use finite event controls outside the authority transaction, emit resource success after actual closure/release, initialize normal absent-capacity sentinels, and preserve primary plus cleanup uncertainty. No production correction, new transport retries or larger budgets.

## Findings and changes

| File | Proven issue | Correction and retained negative boundary |
|---|---|---|
| `tests/unit/test_tip056_resources.py` | Original worker publishes success before CLOSED/resource release/native lease release. Every real queued probe, including a non-first ticket, must recheck CLOSED; seeing the earlier worker ACTIVE correctly produces `ACTIVE_RECOVERY_REQUIRED`. | Success now follows actual CLOSED, resource RELEASED and native lease release. The positive composed resource test uses real ordered tickets and an event-controlled second probe after proven first closure. A separate real-process control forces the second queued probe to observe ACTIVE and requires exact denial, unchanged ACTIVE snapshot, no second reservation and no reset. The first worker then performs its actual zero-attempt closure/release. |
| `tests/unit/test_tip064_integration.py` | Manual NodeRuntime fixture lacks `_coordinator` and `_capacity_registered`; its finally body then raises AttributeError and masks the primary HTTPS failure. Its assertion also replaces unexpected cleanup WireError. | A local fixture helper initializes the normal `None`/`False` capacity sentinels. Existing cleanup runs under `preserve_fixture_failure`; unexpected cleanup WireError is raised unchanged. Controls use actual runtime methods and a real SQLite resource: no capacity registration, exact primary/cleanup identities and notes retained, resource remains open and status remains STOP_PENDING on uncertainty, then actual controlled completion closes it exactly once. |

The child probe gate executes before the original `_try_acquire` authority guard, after the actual ticket assignment. No FIFO sleep or event wait occurs under that guard. Existing child acquisition/control observation is 5 seconds, common queued observation remains one 5-second window, child joins remain 10 seconds, output observation remains 2 seconds. Integration drain deadline remains 1 ms, cleanup observation 2 seconds. HTTP, TLS, product RPC, SQLite, startup and stop budgets are unchanged.

The event-controlled positive resource composition proves its declared ordering; it does not prove every FIFO interleaving. The separate `test_tip024_multiclient_concurrency.py` suite still exercises independent FIFO behavior.

## Deterministic evidence

- `focused-v1.xml` and `focused-v1.log` retain the actual ACTIVE-overlap rejection and exact failure/closure controls. New controls assert no second reservation, no automatic authority closure, no capacity registration, no retry after the unexpected cleanup failure and no CLOSED claim while pending.
- `original-fixture-extraction.json`, `original-fixture-initialization.py` and `original-fixture-cleanup.py` retain exact AST-extracted initialization/finally statements from the named original fixture at the base HEAD.
- `original-cleanup-control.py`, its log and `original-cleanup-control-receipt.json` deterministically execute that retained fixture code around the actual NodeRuntime methods. Original result is AttributeError before agent.step, with the original primary exception only in context. Corrected result is the exact primary plus cleanup ExceptionGroup. Both controls preserve resource uncertainty; cleanup closes only after the controlled dispatcher proves pending work gone. This is fixture evidence, not host/native qualification.
- `pre-test-source-manifest.json` is retained preliminary evidence from the earlier `_new_ticket` control variant before Contractor review. The final candidate uses `_try_acquire`; `focused-v1-source.json`, `focused-v1-receipt.json` and `frozen-source-manifest.json` bind the tested/frozen bytes. Preliminary evidence is not overwritten or presented as final.

## Tests

Working directory: `/workspace/scratch/1818a0d45fa0/repo`.

```bash
PYTHONPATH=app:tests/unit /workspace/scratch/1818a0d45fa0/deploy-20261005/source-venv/bin/python -m pytest -q -s \
  tests/unit/test_tip056_resources.py \
  tests/unit/test_tip064_integration.py \
  tests/unit/test_tip024_multiclient_concurrency.py \
  tests/unit/test_fleet_gateway_fixture.py \
  tests/unit/test_tip058b_transport.py \
  --junitxml=/workspace/scratch/1818a0d45fa0/tip065-ci-refinement-20261005/focused-v1.xml
```

Result: **123 PASS / 3 explicit Windows skips / 0 FAIL / 0 ERROR**, pytest 11.96 seconds; exit 0. Receipt elapsed 12.402 seconds includes process startup. Python 3.12 isolated locked source environment: pytest 9.1.1, MCP 2.1.1, cryptography 50.0.1. Pre/post source hashes match. `git diff --check` passes.

Captured stderr includes the existing intentional HTTPS response-drop/TLS-disconnect controls' BrokenPipe diagnostics. Those fixtures preserve failed transport notes, prove non-replay/finite closure and produce no JUnit error or escaped teardown failure. The raw output is retained. Three skips are existing actual-Windows concurrency release controls; Linux skips do not qualify that platform.

## Frozen source

| Modified fixture | SHA-256 |
|---|---|
| `tests/unit/test_tip056_resources.py` | `23be54918913aae8d17a31ba2cf69f6639e05fe7f76314bca7da523110f6feea` |
| `tests/unit/test_tip064_integration.py` | `a38106e8a773547605f0512a49db551abfd660d8576c9656f0c0e4dd31ef73ab` |

All tracked app bytes match the base HEAD. TIP-065 observer, validator, provenance, CLI/MCP integration and deployment overlay payload are unchanged. No dependency, workflow, catalog, input schema, installation marker, journal/evidence state or authority policy change is included. Contractor-owned report/evidence documentation changes are outside this Builder patch.

## Issues, deviations and suggestions

The ec9180e primary `/fleet/v1/results` HTTPS failure remains **OPEN beyond observed evidence**: TimeoutError awaiting a response; safe thread snapshot shows `job_journal.transaction` COMMIT in `commit_node_result`, with server alive and failure count zero. HTTP policy 1000 ms is a cap; `_service_rpc` also supplies the earlier worker/control-round absolute deadline. Existing `test_rpc_burst_keeps_one_heartbeat_round_budget` proves that deadline rule and its uncertain futures; it does not establish the historical effective deadline or why COMMIT took too long. No budget increase, retry, contention assertion or original functional fix is claimed.

Earlier transport incidents remain OPEN/UNKNOWN as recorded in their retained receipts. Eventual new-head 8/8 can qualify the exact source candidate and artifact proofs; it cannot retrospectively identify those incident causes. Physical migration, SDK/native qualification, Fleet optional process registration and whole Fleet source activation remain separate. Deployment preflight activation remains NOT_QUALIFIED and physical qualification NOT_RUN.

DEVIATIONS: none from Contractor's two-file bounded fixture contract. SUGGESTION: independently verify these frozen bytes, retain test024 FIFO and negative transport coverage, publish one new candidate, and evaluate all eight workflows at its exact head. Do not rerun the failed original checkpoint to infer a fix.
