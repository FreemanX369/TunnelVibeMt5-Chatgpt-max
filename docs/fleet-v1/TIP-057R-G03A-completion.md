# TIP-057R-G03-A Builder Completion Report

**Status: DONE / G03-A FOUNDATION PASS.** All fourteen acceptance criteria pass for the approved bounded source/test foundation at immutable source head `bc9167969d67d288c37a4ce9aa5854a0bf2db14d`. Actual Windows product identity/lifecycle proof, retained Q1 proof and all six workflows passed; artifact bytes, source/blob hashes and raw case results were checked. This result does not close G03-B producer integration, late-dead recovery liveness, physical migration, G04 or Q2.

Approved parent: `0ee42c9cdc677926e3f27d02592c1ad9fc498c8d`, tree `1522511f8f33cdcd2269f561dc4a0f15acadaa80`. Owner decision: “Duyệt tiêp tục theo plan”, 2026-10-02T21:21:49+07:00. Working copy: `/workspace/scratch/250985b4823e/tip057rg03a-work`. Local HEAD `0233b1ce537d7730efc147981aa6ce0b56f1574b` is a **synthetic baseline**, not the remote implementation head. Builder has not committed, published, merged or activated anything. Contractor published the frozen source in [Draft PR #62](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/62); the reviewed [source tree](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/tree/bc9167969d67d288c37a4ce9aa5854a0bf2db14d) remains immutable. This follow-up changes this report only. Contractor approval/design document edits are separate from the Builder delta.

## YAGNI-3 before implementation

1. **Required:** existing `concurrency._cleanup_stale_lock` treated a dead PID as sufficient recovery, while `JobManager._recover_cancel_terminal_state` could probe IPC or restart outside the native lease. Durable unresolved ownership therefore needed a product exclusion point.
2. **Reuse:** existing FIFO `_QueuedFileLease`, `_exclusive_file_lock`, atomic JSON/read helpers, job cancellation/stop receipts and process identity code. Windows retained-handle identity belongs in product; runtime never imports Q1 or a test proof. Linux supplements legacy identity with mandatory independent `/proc` image/times observation and refuses unqualified PID namespaces.
3. **Shortest sufficient change:** one `core/native_ownership.py`, common winning acquisition/stale-removal integration, one central restore wrapper and additive sanitized diagnostics. No scheduler, installer, public recovery/force-clear tool, helper, SDK activation or new terminal job state.

## Implemented behavior and contract changes

Native admission requires a supported READY installation marker and matching valid CLOSED authority. Missing/corrupt/unsupported files, MIGRATING, epoch mismatch and ACTIVE deny with `LIVE_RECOVERY_REQUIRED`. Acquisition performs both an early bounded check and the **winning O_EXCL/stale-delete check under the same authority transaction**. Native capacity remains one; mutation retains its separate namespace and mutation→native order. Ordinary release/unlink is unchanged and cannot alter the ownership snapshot.

The internal producer contract requires an actually owned native token and independently observed current parent at arm, create-attempt and bind. It persists ARMED → CREATE_ATTEMPT → BOUND; an interrupted create never invents a worker. Zero-attempt closure differs from unknown creation. Worker closure requires an independently observed retained lifetime handle, exact exit, a trusted future descendant verifier, and full expected epoch/generation/token/parent/worker CAS. A fresh first observation after exit refuses identity; expected journal images never supply OS evidence. No production caller or qualified descendant verifier exists in this slice.

Both central cancel restore effects require the real native lease with `wait_seconds=0`. Authority/lease/queue unavailability returns a durable pending restore receipt; `cancel_requested`, exact stop proof, reads and MCP startup registration remain usable. The restore receipt adds `NATIVE_OWNERSHIP_RESTORE_PENDING`, `error=LIVE_RECOVERY_REQUIRED` and a sanitized `ownership_reason`. An existing complete/no-handoff/worker-cleanup receipt retains historical settlement semantics and does not close ownership. Same-job/self-held native leases are never borrowed or waited on recursively.

Private persisted native owner records add exact `identity`. `ConcurrencyManager.status()` adds sanitized `native_ownership` diagnostics. Native signatures, successful lease output shapes, public catalog, request-hash source, package/dependency files and terminal-state schema are unchanged; source byte comparisons are retained in the manifest. This source intentionally denies native work on an uninstalled root. There is **no production installation/migration route** here.

Acquisition errors before a lease/effect is returned clean the exact newly created ticket and owner path, including mkdir/write/fsync failures. No broad owner/authority reset is used. Ordinary release retains the existing same-object serialization, successor-token protection and Windows sharing retry behavior.

## Builder files

Runtime:

- `app/vibemql5/core/native_ownership.py` (new)
- `app/vibemql5/core/concurrency.py`
- `app/vibemql5/core/jobs.py`

New fixtures/tests/required CI:

- `tests/unit/ownership_fixture.py`
- `tests/unit/test_tip057rg03a_native_ownership.py` — 60 portable product cases, no new skips
- `tests/proofs/tip057rg03a/run_windows.py` — eight required Windows cases, no skipped gate
- `.github/workflows/verify-tip057rg03a.yml` — exact PR head/source blobs, Windows log/artifact receipt

Explicit disposable-root initialization only; original assertions preserved:

- `tests/unit/test_tip021r_remediation.py`
- `tests/unit/test_tip024_multiclient_concurrency.py`
- `tests/unit/test_tip026_binary_ingress.py`
- `tests/unit/test_tip026r1_widget_ingress.py`
- `tests/unit/test_tip039_generic_powershell.py`
- `tests/unit/test_tip055a_runtime_forensics_identity.py`
- `tests/unit/test_tip055b_runtime_forensics_release.py`
- `tests/proofs/tip057rq/run_proof.py` — Portable/Windows setUp and owned crash-parent fresh roots; read/arm/recovery never installs

Report/receipts: this file and `evidence/tip057rg03a/*`. The seven historical Q1 CI metadata receipts and their retained artifacts remain byte-identical: all 27 files under `docs/fleet-v1/evidence/tip057rq` checked against the verified baseline. The retained Q1 workflow itself is unchanged.

## Validation and raw receipts

Linux platform: `Linux-6.18.44-x86_64-with-glibc2.39`; Python 3.12.14. Existing test dependencies were reused from `/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages`; no repository dependency changes. Run from the working copy with:

```sh
PYTHONPATH=app:/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages python -m pytest -q -rs --durations=5 tests/unit/test_tip057rg03a_native_ownership.py tests/unit/test_tip024_multiclient_concurrency.py tests/unit/test_tip023_cancel_recovery.py tests/unit/test_tip055b_runtime_forensics_release.py --tb=short
```

Final refined source: **121 passed, zero failures/errors, two existing Windows-only skips, 6.68 seconds**. New G03-A cases have zero skips. Native-only two-process contention took 1.04 s, mutation→native contention 0.87 s, recovery/acquire race 0.44 s in this fixture run. These are observations, not production deadline guarantees. Child/thread failures propagate to parent assertions.

Before the final ticket/owner cleanup refinements and native-only additions, the relevant full suite ran with the same PYTHONPATH:

```sh
python -m pytest -q -rs tests/unit --tb=short
```

That receipt is **396 passed, zero failures/errors, 26 existing platform skips, 12.70 seconds**. It is labeled before-refinement and is not presented as an exact final-source full run. The final changed paths were rerun in the affected scoped suite; Contractor requested no redundant full rerun. The subsequent actual Windows results below complete source verification. These historical Linux platform skips concern existing PowerShell/VPS, Windows junction and actual deny-delete fixtures; they remain recorded and are not relabeled. The new required Windows runner has zero skipped cases.

`compileall` over product/new/Q1 surfaces and `git diff --check` passed on final source. Q1 portable on final source: **8/8, zero failures/errors/skips**, explicitly Windows-unqualified. Its first attempt had **7 INSTALL_MISSING errors out of 8** before explicit test-root migration; the original failure log/summary is retained, not relabeled. The required G03-A Windows invocation on Linux correctly exited **1 / BLOCKED / REAL_WINDOWS_REQUIRED_NO_SKIP**, with zero executed cases and zero skips.

Raw receipts and exact file/platform hashes are in `evidence/tip057rg03a/README.md` and `local-source-manifest.json`. Scratch originals are under `/tmp/tip057rg03a-final/`: final `scoped-publish-final.log`, historical `full-final.log`, final `q1-portable-publish.log`/summary and `windows-required-publish-negative.log`/summary. The local manifest identifies the frozen source bytes and preserves its earlier Windows-pending stage. The subsequent [CI metadata](../../evidence/tip057rg03a/ci-source-bc916796.json) and raw Windows receipts below bind those bytes to published immutable head `bc9167969d67d288c37a4ce9aa5854a0bf2db14d`; the synthetic local commit is not source authority.

### Actual Windows verification of the immutable source

Both proof workflows explicitly checked out and verified `bc9167969d67d288c37a4ce9aa5854a0bf2db14d`, with `exact_head_verified=true`, `source_blob_verified=true` and matching checked-out/Git blob source hashes. Platform: **Windows-2025Server-10.0.26100-SP0**, Python **3.12.10**, MSC v.1943, 64-bit AMD64.

| Evidence | Actual result | Run/job and retained receipt |
|---|---|---|
| G03-A product identity/lifecycle | **8 PASS**, zero failures/errors/skips; 1,390 ms runner elapsed; `G03A_WINDOWS_FOUNDATION_PASS_PRODUCER_OPEN` | [Run 37025462023 / job 110898837898](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462023/job/110898837898); [raw summary](../../evidence/tip057rg03a/windows-source-bc916796/summary.json), [proof log](../../evidence/tip057rg03a/windows-source-bc916796/proof.log) |
| Retained Q1 isolated Windows proof | **16 PASS**, zero failures/errors/skips; full suite attempted; 15,250 ms runner elapsed; `FIXTURE_PASS_Q03_OPEN` | [Run 37025462247 / job 110898838876](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462247/job/110898838876); [raw summary](../../evidence/tip057rg03a/q1-source-bc916796/summary.json), [proof log](../../evidence/tip057rg03a/q1-source-bc916796/proof.log), [compiler log](../../evidence/tip057rg03a/q1-source-bc916796/compiler.log) |
| TIP-053 full Windows units | **424 passed, 4 existing skips**, 36.46 s; no G03 skips | [Run 37025462241](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462241); [raw job log](../../evidence/tip057rg03a/baseline-source-bc916796/37025462241-job.log) |
| TIP-034 fresh-checkout full Windows units | **424 passed, 4 existing skips**, 40.49 s; no G03 skips | [Run 37025462208](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462208); [raw job log](../../evidence/tip057rg03a/baseline-source-bc916796/37025462208-job.log) |

The full-unit baseline workflows used GitHub's PR merge checkout `12f6b67d7a10af0aca1e2bd2bc5709457da8c8fd` (candidate `bc916796…` into main `70e2112…`), as recorded in their raw logs. Contractor independently verified that its tree is **identical** to the frozen source candidate tree: `e9bd991b173d3c05581ac4c9aad3dd2e2eebd745`, recorded in `baseline_checkout` in the CI metadata. Their workflow event head is the immutable candidate; the explicit exact-head/source-blob evidence comes from the two proof workflows above. The four full-unit skips are the two existing unavailable deployed VPS-root cases and two existing platform-specific identity fixtures. They do not skip any G03-A requirement.

All six workflow statuses/conclusions for candidate `bc916796…` are independently recorded as completed/success in the CI metadata: the four runs above plus [TIP-028 bindings run 37025461890](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025461890) and [TIP-027 continuity run 37025462009](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462009). Final workflow and completed job snapshots plus retained raw logs establish outcomes.

Original downloaded artifacts were checked, without reconstructing archive bytes:

- G03-A artifact **11234742196**, 2,317 bytes, SHA-256 `170d84f95b4ed29716835ebef4f6a883a8f4facf6ac9c1e1a3929d3112ec3b24`.
- Q1 artifact **11234907133**, 8,870 bytes, SHA-256 `b6b5719cad63b25f3495a2d9398777e0021b9370d6faca987593a90d3d2720fd`.

The raw G03-A proof contains all eight named cases and eleven bounded records: real suspended create/bind-before-resume, create-before-bind interruption, descendant refusals, live-orphan/stale CAS, fresh-dead refusal, valid CLOSED reused-identity compatibility, bind publication faults and worker-closure publication faults. Production helper/SDK remains ABSENT and the production descendant verifier remains OPEN in the receipt.

Product source SHA-256 verified against both local frozen bytes and recorded exact-head Git blobs:

| Source | SHA-256 |
|---|---|
| `core/native_ownership.py` | `dded1e6f922d58575f5e79199823825fa5587ed285512cc6e63813c0d3e5c039` |
| `core/concurrency.py` | `af7fb5cc3817a460491d8710d77deacae66d0ba2c93e249d738b602fe1a264da` |
| `core/jobs.py` | `096d32b968dd54cbaeb5374f17a1855d1fdd523ff54b256a3083d0bae634bcd4` |


## Acceptance matrix

| AC | Builder result | Scoped evidence and limits |
|---|---|---|
| A01 | PASS | Separate native-only two-process FIFO/capacity and mutation→native contention tests passed locally and in the 424-pass Windows full suites. Original TIP-024 valid CLOSED dead-PID/FIFO/sequence and TIP-021R successful mock job/provenance assertions remain. |
| A02 | PASS | Actual facade live/account/market/chart, direct/iteration compile, worker/tester acquire and existing backend PowerShell entry-path tests passed on Windows; mocked native callbacks are exactly zero under ACTIVE. No real SDK/native product effect was activated. |
| A03 | PASS | Windows full-suite central `cancel_job`, `get_job`, actual MCP startup/read/health cases retain pending cancellation under ACTIVE/guard/queue failures. CLOSED probe/restart fixtures assert the actual common native owner and reentrant status access during mocked effects. |
| A04 | PASS | Linux/Windows stale cleanup regressions plus actual Windows `test_a04_actual_live_reused_identity_active_lock_is_not_deleted`: ACTIVE preserves the native lock, while valid CLOSED permits schema-valid independently observed reused-identity cleanup. Corrupt live-owner identities remain conservative. |
| A05 | PASS within persistence boundary | Missing single/both files, corruption, unsupported schema, malformed shape, epoch mismatch and MIGRATING cases pass in Windows full units. Actual Windows bind before/after and worker-close before/after/readback fault records retain ACTIVE. Arm/create/zero-close faults and no-effect ticket/owner publication cleanup pass. Simultaneous unavailable storage/power-loss limits remain below. |
| A06 | PASS for future-producer interface | Windows actual `CreateProcessW(CREATE_SUSPENDED)` case records ARMED → CREATE_ATTEMPT → actual suspended create → BOUND → RESUME → exact exit. Actual create-before-bind interruption stays ACTIVE without a guessed worker. Owned parent/lease order, released-lease refusal and zero-attempt distinction pass. Positive descendant callback remains contract fixture evidence only. |
| A07 | PASS | Multiprocess recovery/acquire race passes in Linux and Windows full units: one close, one stale reject, one successor generation. Actual Windows live-orphan fresh observation, identity mismatch and stale CAS case independently observes the real process and preserves successor generation 3. |
| A08 | PASS for refusal requirement | Actual Windows `test_a08_fresh_already_dead_handle_never_uses_expected_journal_image` records `REFUSED_WITHOUT_INDEPENDENT_LIVE_IMAGE`; retained same-handle exit is separately proven. Missing OS-image regression passes. Late-dead recovery liveness remains OPEN. |
| A09 | PASS within snapshot boundary | Interrupted MIGRATING/authority publication and mismatching old-epoch restoration preserve denial/generation in Windows full units. Valid same-epoch old CLOSED backup replay, mixed binaries and physical rollback fencing remain OPEN. |
| A10 | PASS | Exact-head source/blob and catalog/bootstrap/binding workflows verify the bounded source; public entry, dependency and terminal-state sources remain unchanged. No runtime proof import, helper, installer, public recovery/force-clear tool or target/live_read activation. |
| A11 | PASS | Windows full-suite exact owned-job stop mock remains separate: stopped proof plus ACTIVE restore stays TESTING/cancel pending. Original cancellation/provenance regressions pass. Already-complete historical restore proof may settle the job without changing ownership. |
| A12 | PASS | Windows full units preserve actual persisted ACTIVE through context finally, worker unlink and failed unlink; successors stay blocked. Existing TIP-055B real Windows deny-delete, successor-token and sharing retry regressions execute on Windows and pass. Release never closes authority. |
| A13 | PASS within measured fixture scope | Source lock-order review and Windows/Linux contention tests keep FIFO sleeps, effects, descendant verifier and process waits outside the short authority guard; status during contention/effect is reentrant. Windows product proof runner elapsed is 1,390 ms; Linux measured races remain historical observations, not production deadlines. |
| A14 | PASS | Immutable `bc916796…` exact-head/source-blob Windows G03-A 8/8 and Q1 16/16 proofs have zero failures/errors/skips, verified raw artifacts and case logs. All six workflows are completed/success; two retained full Windows baseline suites pass 424/4 with no G03 skips on a PR merge tree independently verified identical to the frozen source tree. Historical receipts/failures and all changed contracts remain reported. |

## Limits, deviations and suggestions

No architecture deviation. Routine bounded refinements cover independent process evidence, conservative malformed owner handling, short guard failures, pending restore on metadata failures and cleanup of no-effect acquisition attempts.

- Future producer methods are **not integrated into existing LiveTerminal/MT5Preflight/handoff callbacks**. CLOSED allows their existing behavior; this foundation proves exclusion when durable authority is unresolved. G03-B must integrate all intent/cleanup producers before full activation.
- No production descendant verifier is qualified. Returning a recognized string from the harmless fixture callback only tests the internal contract; it is not OS descendant proof, SDK compatibility or G04 evidence. UNKNOWN, booleans, unqualified values and verifier exceptions retain ACTIVE.
- Atomic file fsync/replace/readback does not establish directory/power-loss durability or administrator tamper resistance. Closure attempts prove zero creation or exact worker exit/qualified fixture disposition **before** writing CLOSED. Caught close write/readback errors attempt to republish the prior ACTIVE under the same guard; writable-storage fixtures preserve exact epoch/generation/token. Simultaneous write/rollback failure or power loss cannot guarantee persisted ACTIVE. Unproven/unknown cleanup never reaches CLOSED.
- If filesystem deletion itself remains unavailable, exact ticket/owner cleanup is conservative and may leave an owner file blocking admission; no broad reset or guessed cleanup is added. Fault→healthy acquisition fixtures cover writable cleanup after the injected admission failure.
- This Linux host exposes `/proc/self` in a different PID namespace from `getpid()`. Current-process identity uses independent self observation with a pidfd. Other-PID observation refuses namespace mismatch instead of comparing an unrelated host image. Actual Windows external-process retained/fresh identity and refusal requirements are verified for the harmless Python fixtures; Linux contention still exercises real file leases/processes and its namespace limitation remains unchanged.
- Epoch mismatch and interrupted publication are tested. Valid same-epoch old CLOSED snapshot replay, old binaries that ignore the protocol, physical migration/rollback and unavailable storage cannot be fenced by this JSON foundation. No production settings/state were migrated.

Contractor next: record final output verification and publish the report/status evidence without changing the verified source. Keep G03-B/physical migration/G04/Q2 OPEN and make their next concrete producer/boundary decision separately. No deployment, MT5/VPS/account/credential/AutoTrading action is implied by this source result.
