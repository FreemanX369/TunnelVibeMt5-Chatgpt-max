# TIP-055A — Bounded M0 deployment readiness

Status: **Drift compatibility resolved; bounded follow-up candidate ready for exact-head publication/CI before rollout. No VPS files written in this SCAN.** Owner authorized continuation on 2026-10-02. This is a concrete runbook for supported operations, not a request for another approval. Initial repository authority is merged PR #54 at `277cb56189d90ddc293d700da75c196c4140f705`; the follow-up preserves deployed CLI comments and renames one fixture module for the existing selector. Contractor records its exact final commit/tree before deployment. A reviewed repository tree is not proof that the currently deployed source matches it.

No runtime behavior change is needed for this SCAN. Existing checkpoint/CAS writes, fixed compile checks and per-instance restart operations are reusable. The shortest follow-up preserves two deployed CLI comments and renames the existing identity fixture module so the supported `runtime_forensics` selector can verify identity/provenance in isolated temporary roots. It adds no API, duplicate suite, general deployer, deletion endpoint, shell executor or hidden enrollment test.

## 1. Reviewed repository manifest

Paths are relative to the selected installation root; examples may use `C:/VibeMQL5`. Payload hashes are SHA-256 over exact UTF-8 bytes, including trailing newline. Repository-base hashes below were computed from the verified local baseline Git `HEAD` (`344d6a24a58e970004bc93fa28d1d27d8cff1855`, a synthetic snapshot of source `64a6290` plus approved Blueprint `063d6a3`); they are comparison evidence, **not automatic live CAS inputs**. Before any write, obtain the actual live hash and bytes and resolve all differences.

| Relative path | Action | Candidate bytes | Candidate SHA-256 | Repository-base bytes / SHA-256 |
|---|---|---:|---|---|
| `app/vibemql5/fleet/__init__.py` | Create only if absent | 76 | `63494dd4840ca2d7b3af78de5adb5dd12abde28534aad8611e5b955a5c4ffa3f` | ABSENT |
| `app/vibemql5/fleet/identity.py` | Create only if absent | 18,379 | `1d234b30e532dd352256010db393ff39f5f39d46d324f6c47ab6539365f459cc` | ABSENT |
| `app/vibemql5/fleet/targets.py` | Create only if absent | 2,439 | `dcbe3bd416e12cffc55b931cf19897ab31ce2559c13c9e360fabf29de53243ea` | ABSENT |
| `app/vibemql5/core/inventory.py` | Checkpoint + CAS replace | 9,382 | `3e4c168dfbe4f03a5e8268d85889e2d873e77c3d5993ee7d7a184a6e42966970` | 9,009 / `fa956d742b6c6fabb150752d31f151c55b75619b0225ebe39eecfd4459515f73` |
| `app/vibemql5/adapters/cli.py` | Checkpoint + CAS replace; deployed comments retained | 13,937 | `7b01dbdd1e7dfbc027537e09be69246a4ce0d98bfd2d67ca692ab9540ed76719` | 12,060 / `30ec1b873a59524eb9449ad73e3beb36b505089d9e7109218d68d245de79d90d` |
| `tests/unit/test_tip055a_runtime_forensics_identity.py` | Create only if absent | 29,578 | `3b1bfc035e5025263cbf91f5341bb4b97d98c04470d01fc87f432c599ddb13ac` | ABSENT |

Observed preflight: deployed inventory matched its repository base. Deployed CLI was 12,197 bytes / `cadfa50a18fb0c9638c832ba2a9119caccbfc82092c89bc30ba3293866c7aa2e`, differing only by two comments from the repository base (full AST equality PASS). The follow-up CLI retains those exact comments before the explicit timeout-cancel branch.

Deployed `core/jobs.py` was 51,100 bytes / `e1bbc44058006803f2203af916a333575cd80efcf0cef778fba55024dc902759`. Full AST differs in docstrings; statement AST equality after stripping docstrings PASS. Imports and executable statements are unchanged. The exact deployed job module was imported into an isolated verification process; identity/inventory/targets/CLI imports and temporary-root bootstrap/reload PASS. Its helper signatures remain `_atomic_write_json(path, value)`, `_exclusive_file_lock(path, timeout_seconds=15.0)`, `_read_json_object(path, *, attempts=8, retry_decode=False)`. There is no inventory import cycle. Preserve this deployed job file unchanged: it is a dependency, not a replacement target in this manifest.

Preserve both exact drift snapshots as evidence. All live hashes must be refreshed before writes; changed bytes outside the reviewed drift are a new stop/review condition.

## 2. Supported surface and technical boundaries

The current chat exposes backend file reads/hashes, checkpoint, CAS write/restore, fixed-suite checks and runtime/tunnel restart. These operate only within BackendAdmin's existing allowlist. `state/fleet` is outside that file read/write allowlist. There is no exposed identity bootstrap/show/update execution command and no deletion command.

| Requirement | Supported route / boundary |
|---|---|
| Replace existing inventory/CLI | `backend_create_checkpoint`, then `backend_write_file` using exact current SHA and covered checkpoint |
| Create new modules/test | `backend_write_file` with `expected_sha256=""`, `checkpoint_id=""` is a server-enforced absence precondition. Require PASS, empty `sha256_before` and exact reviewed after-hash; an existing collision is a stop, not an overwrite |
| Restore old integration | `backend_restore_checkpoint` with exactly selected covered files and a fresh full current-hash map |
| Remove newly created files | Unavailable. Rollback leaves modules/tests retained; modules are unreferenced by the restored legacy service, while the retained test remains collectible and may fail against that service code |
| Fresh compile verification | `backend_run_tests(suite="py_compile")`; compiles source without importing/launching MT5 |
| Fixture-only deployed identity tests | `backend_run_tests(suite="runtime_forensics")` selects the renamed module plus the existing static source-guard test; no API/suite expansion |
| Real identity enrollment/state backup | Existing local CLI can perform it, but current chat has no supported execution or state-file access route. Keep unenrolled until that route is available |
| Exact restart of B/C | Existing `tunnel_admin_restart(instance="B"/"C", confirm=true)` when actually exposed; per-instance receipt and postcheck required |
| Restart of A | Supported detached `backend_restart_runtime(components=["interactive_tunnel"])` controller targets A and checks port 8080; it does not refresh B/C |

**Do not run deployed `unit` or `baseline_aware` as a fixture-only substitute.** `tests/unit/test_tip040_live_vps.py::test_tip040_live_mt5_2_account_chart_and_png` and `::test_tip041_live_each_open_chart_16_9_and_exact_layout_rollback` automatically use `default_root()` on Windows. If MT5-2 is running and its native lock is free, they acquire a native lease, read the live terminal and capture/temporarily navigate charts. There is no explicit opt-in environment flag. That exceeds this M0 inventory/bootstrap-only verification boundary. Windows CI with no deployed running MT5 is a different environment. Do not alter tests to hide enrollment, set misleading environment roots, or use pytest as arbitrary command execution.

The selected `runtime_forensics` tests examine identity/provenance corruption, replay, binding drift, atomic persistence and inventory compatibility using `tmp_path`/temporary child processes or intercepted drivers. Actual registry fixtures are created only under those isolated roots; no deployed enrollment is performed. The pre-existing selected repository test reads source guard contracts only. Collection review selected exactly 37 repository cases (36 identity cases plus that guard) and excluded both physical chart cases; Linux run: **36 passed, 1 Windows junction skip, 300 deselected**. Full Linux unit regression after the rename: **313 passed, 24 skipped**. This naming follows the forensics/provenance scope rather than executing arbitrary code under a test name. The original `test_tip055a_identity.py` is renamed in Git, not duplicated. Check its old deployed path before first rollout and record the result: an unexpected prior file needs review; the current generic read error must not be reported as positive absence proof. The VPS retains additional legacy tests beyond this repository snapshot, so its selected counts can differ; the runtime checkpoint must identify the actual result.

Current chat also lacks `describe_capabilities`, `backend_start_test_run` and `backend_get_test_run`. A server catalog claiming those names is not sufficient to invoke them. Synchronous fixed-suite checks have their own server timeouts (compile 180s, unit 300s); transport timeout can leave an outcome unknown. Do not repeat a long test after an ambiguous timeout without a result/reconciliation route.

## 3. Preflight gates, before staging

1. Confirm the follow-up exact reviewed/published commit/tree and all six payload hashes, including the drift-preserving CLI and renamed fixture. Preserve AST/import evidence and exact drift snapshots. Dependency review is complete; publication/CI gate is pending Contractor action at this SCAN.
2. Refresh `server_info`, `health`, `tunnel_admin_status(instance="all")`: READY, queue 0, active job null, native/mutation locks null, A/B/C each exactly one process and 200/200. The prior clean sample is not a guard for later writes/restarts.
3. Read/hash all existing deployment targets. The current connector returns generic `INVALID_ARGUMENT` for the new-file reads; that error alone is not evidence of absence. A new-file write must use the supported empty expected-hash precondition: the server rejects an existing file and the successful receipt must confirm empty before-hash plus exact after-hash. Reparse allowlist escape, pre-existing collision, unexpected content or byte/hash mismatch stops the rollout. The old fixture path was not positively observed as present; retain this read limitation in the checkpoint rather than claiming a directory listing.
4. Establish a coordinated quiet deployment window; other clients must not create jobs or mutate deployment files during staging. Existing writes are atomic per file, not a six-file transaction. Their preflight CAS is not a new distributed writer fence.
5. Checkpoint the exact live inventory/CLI bytes, preserve the checkpoint receipt/coverage/hashes and the restore API route. Retain deployed extras rather than checkpointing a guessed repository copy.
6. Confirm restart/continuation route for A/B/C and supported recovery if the active chat connection drops. If B/C restart is not actually exposed, refreshing all adapters is a technical gate; do not treat an A-only restart as fleet-wide activation.

Five distinct lexical executable/data-root pairs are an inventory observation, not Windows physical-equivalence qualification. Existing identity state, if any, must be surfaced through supported inventory and reviewed; never assume its absence and never reset it.

## 4. Shortest staged rollout, after gates close

1. Create `fleet/__init__.py`, `fleet/identity.py`, `fleet/targets.py`, then the identity test fixture file. Verify each receipt/hash. Until integration changes, the modules are unreferenced by the legacy inventory/CLI; the test is already collectible and must not be run as if its integration has been installed. A failed staging step leaves an explicit retained-file record.
2. CAS-write the reviewed drift-preserving CLI, then inventory last, using the live checkpoint and exact fresh expected hashes. Do not replace `jobs.py`, native MCP adapters, config, provenance, locks or historical state.
3. Re-hash all six files against the final manifest. Run fixed `py_compile` and `runtime_forensics` once each and require unambiguous PASS receipts. Require the selected fixture module is present at the manifest hash and do not invoke broad `unit`/`baseline_aware`. CI evidence does not become a deployed test receipt. The existing synchronous forensics result reports summary counts, not named skip reasons; CI's `-rs` output identifies the Windows junction case, while deployed named junction acceptance remains a separate evidence gate if no named result is available.
4. Refresh B and C through their allowlisted per-instance restart route sequentially, verifying each returns exactly one healthy process. Refresh A last through its detached supported controller, preserving the restart ID/receipt and reconnecting through the existing connector. No terminal restart/account/AutoTrading action is part of this sequence.
5. Read `server_info`, `health`, all tunnel status and existing inventory/validation. Require catalog count/order/hash unchanged at 85 / `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef`; idle guards restored; legacy fields/build authority preserved; new identity/resource fields actually visible. Expect honest `UNENROLLED` where no registry exists, null IDs and no routed native capability. Unexpected identity state is a review stop, not a bootstrap trigger.
6. Record installed-code/isolated-fixture acceptance separately from enrollment/native qualification. On the current surface, code may be staged/activated after publication/drift gates close while real enrollment remains pending. M1 readiness must not be inferred from installed M0 files.

## 5. Guarded rollback

For staging failure before integration, retain the new files and receipts; the legacy service implementation remains selected. The staged M0 test is not inert: subsequent unit/runtime-forensics collection may select it and fail because old inventory lacks the overlay. There is no supported delete action.

For integration/compile/read acceptance failure, refresh current hashes of checkpoint-covered inventory/CLI and call `backend_restore_checkpoint` with those exact selected paths and a matching full expected-current hash map. Restore preflights every checkpoint source/current target before any copy, but each file replacement remains separate. If a target drifted unexpectedly, stop instead of forcing restore.

After restoration, verify the checkpoint hashes and refresh all changed adapter processes through the same B/C/A order. Require READY/idle/one-process guards and legacy inventory/native catalog compatibility. Keep `fleet/*`, its test and any pre-existing identity state retained for compatible recovery. Restoring the two integration files disables their service overlay/CLI connection; it does not remove newly created files. The retained test can still be collected by `unit` or `runtime_forensics` and fail against the rolled-back integration. Do not claim old suites are green or skip/tombstone those tests to hide the incomplete filesystem rollback. **This is a functional service rollback, not an exact filesystem rollback.** Exact removal is separate coordinated operator cleanup: verify each retained file still matches the recorded candidate hash before removal and preserve evidence; current chat exposes no such deletion capability.

Do not restore an old identity generation/operation index through backend file writes; those state paths are not allowlisted. Enrollment later requires explicit local state backup and coordinated CLI/API semantics from the operator guide.

## 6. Evidence and remaining gates

Save candidate/base/live manifests, drift review, checkpoint and each write/readback receipt, compile result, per-instance restart receipts, postcheck inventory and truthful unresolved statuses. Windows CI junction fixture evidence proves that isolated case on the CI host; it does not prove equivalence of the five actual VPS roots.

Remaining gates at this SCAN: exact-head follow-up publication/CI; fresh deployment guards/hashes; an actual identity CLI execution/state-backup route; Windows physical binding/enrollment acceptance and named deployed junction evidence. Drift/import compatibility and fixture-only selection are resolved by the bounded follow-up. Remaining items are capability/evidence gaps, not a need to repeat approval for already authorized supported deployment operations.
