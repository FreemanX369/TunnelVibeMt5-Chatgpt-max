# TIP-057R-G03-A Builder Completion Report

**Status: PARTIAL / LINUX FOUNDATION PASS / ACTUAL WINDOWS PENDING.** The approved bounded product source and harmless fixtures are implemented. A08 and A14 cannot be marked PASS until Contractor publishes an exact candidate head and obtains the required Windows receipts. This report does not close G03-B producer integration, late-dead recovery liveness, physical migration, G04 or Q2.

Approved parent: `0ee42c9cdc677926e3f27d02592c1ad9fc498c8d`, tree `1522511f8f33cdcd2269f561dc4a0f15acadaa80`. Owner decision: “Duyệt tiêp tục theo plan”, 2026-10-02T21:21:49+07:00. Working copy: `/workspace/scratch/250985b4823e/tip057rg03a-work`. Local HEAD `0233b1ce537d7730efc147981aa6ce0b56f1574b` is a **synthetic baseline**, not the remote implementation head. Builder has not committed, published, merged or activated anything. Contractor approval/design document edits are separate from this Builder delta.

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

That receipt is **396 passed, zero failures/errors, 26 existing platform skips, 12.70 seconds**. It is labeled before-refinement and is not presented as an exact final-source full run. The final changed paths were rerun in the affected scoped suite; Contractor requested no redundant full rerun. Full exact-head Windows CI remains pending. Platform skips concern existing PowerShell/VPS, Windows junction and actual deny-delete fixtures; the new required Windows runner cannot skip them into a PASS.

`compileall` over product/new/Q1 surfaces and `git diff --check` passed on final source. Q1 portable on final source: **8/8, zero failures/errors/skips**, explicitly Windows-unqualified. Its first attempt had **7 INSTALL_MISSING errors out of 8** before explicit test-root migration; the original failure log/summary is retained, not relabeled. The required G03-A Windows invocation on Linux correctly exited **1 / BLOCKED / REAL_WINDOWS_REQUIRED_NO_SKIP**, with zero executed cases and zero skips.

Raw receipts and exact file/platform hashes are in `evidence/tip057rg03a/README.md` and `local-source-manifest.json`. Scratch originals are under `/tmp/tip057rg03a-final/`: final `scoped-publish-final.log`, historical `full-final.log`, final `q1-portable-publish.log`/summary and `windows-required-publish-negative.log`/summary. The source manifest, not the synthetic local commit, identifies this candidate's bytes. No exact remote-head or actual Windows PASS is claimed.

## Acceptance matrix

| AC | Builder result | Evidence / remaining condition |
|---|---|---|
| A01 | Linux PASS; Windows baseline pending | Separate native-only two-process FIFO/capacity test plus mutation→native contention; original TIP-024 dead-PID CLOSED recovery and FIFO/sequence assertions; TIP-021R mock successful job/provenance full receipt. |
| A02 | Linux PASS | Actual facade live/account/market/chart, direct/iteration compile, worker/tester acquire and existing backend PowerShell admission; all mocked native effect callbacks remain exactly zero under ACTIVE. |
| A03 | Linux PASS | Central `cancel_job`, `get_job`, actual MCP startup/read/health registration; ACTIVE/guard/queue damage leaves cancel pending and sanitized receipts. CLOSED probe/restart fixtures assert real native owner and reentrant status access during effects. |
| A04 | Linux PASS; actual Windows pending | ACTIVE/invalid dead-owner stale-deletion refusal and malformed live-owner protection. Required Windows case independently observes a real PID, preserves ACTIVE lock and permits valid CLOSED schema-valid reused-identity cleanup. |
| A05 | Linux PASS; Windows bind/worker-close pending | Missing single/both files, corruption, unsupported schema, malformed shape, epoch mismatch, MIGRATING windows. Arm/create/zero-close before/after/readback faults; Windows bind before/after and worker-close before/after/readback cases retain ACTIVE. Simultaneous storage failure/power loss limit below. |
| A06 | Linux contract PASS; actual Windows pending | Owned lease/parent ordering and released-lease refusal, zero-attempt vs unknown creation. Required Windows actual `CreateProcessW(CREATE_SUSPENDED)` demonstrates durable attempt, actual bind and marker absence before resume, then exact exit. Create-before-bind interruption never guesses worker. Positive descendant callback is contract fixture evidence only. |
| A07 | Linux multiprocess PASS; Windows live-orphan pending | Two racing recoverers and acquire: one close, one stale reject, one successor generation; stale snapshot cannot clear successor. Required Windows fresh-live/retained-exit and identity-mismatch closure cases. |
| A08 | PENDING ACTUAL WINDOWS | Dedicated fresh already-dead handle case requires refusal despite expected journal image; retained live-observed handle remains separate. Linux missing OS-image test refuses permissive path fallback. No late-dead liveness claim. |
| A09 | Linux PASS within snapshot boundary | Interrupted MIGRATING/authority publication and old-epoch marker restore preserve denial/generation. Same-epoch valid old CLOSED backup replay, mixed binaries and physical rollback fencing remain OPEN. |
| A10 | Source/legacy PASS | Catalog/dependency/schema/public entry sources byte-identical; no runtime proof import, helper, installer, public recovery tool or target/live_read activation. Historical successful output behavior retained on valid CLOSED installations. |
| A11 | Linux PASS | Exact owned-job stop mock executes separately; stopped proof plus ACTIVE restore stays TESTING/cancel pending. Original cancellation/provenance regressions retained. Already-complete historical restore proof can settle without changing ownership. |
| A12 | Linux PASS | Context finally, worker unlink and failed unlink leave actual persisted ACTIVE readback unchanged and successors blocked; release never closes authority. Existing TIP-055B successor-token and sharing retry assertions pass. |
| A13 | Linux PASS; Windows runtime pending | Authority guard encloses only bounded read/CAS/atomic publication/O_EXCL/stale decisions. FIFO sleeps, effects, descendant verifier and process waits occur outside it; status during native contention/effect is reentrant. Actual fixture elapsed values above. |
| A14 | PENDING EXACT-HEAD WINDOWS | Dedicated eight-case no-skip Windows source/blob runner and retained baseline/Q1 workflows prepared. Contractor must publish and obtain exact-head source/hash/log/artifact receipts and full baseline outcomes. |

## Limits, deviations and suggestions

No architecture deviation. Routine bounded refinements cover independent process evidence, conservative malformed owner handling, short guard failures, pending restore on metadata failures and cleanup of no-effect acquisition attempts.

- Future producer methods are **not integrated into existing LiveTerminal/MT5Preflight/handoff callbacks**. CLOSED allows their existing behavior; this foundation proves exclusion when durable authority is unresolved. G03-B must integrate all intent/cleanup producers before full activation.
- No production descendant verifier is qualified. Returning a recognized string from the harmless fixture callback only tests the internal contract; it is not OS descendant proof, SDK compatibility or G04 evidence. UNKNOWN, booleans, unqualified values and verifier exceptions retain ACTIVE.
- Atomic file fsync/replace/readback does not establish directory/power-loss durability or administrator tamper resistance. Closure attempts prove zero creation or exact worker exit/qualified fixture disposition **before** writing CLOSED. Caught close write/readback errors attempt to republish the prior ACTIVE under the same guard; writable-storage fixtures preserve exact epoch/generation/token. Simultaneous write/rollback failure or power loss cannot guarantee persisted ACTIVE. Unproven/unknown cleanup never reaches CLOSED.
- If filesystem deletion itself remains unavailable, exact ticket/owner cleanup is conservative and may leave an owner file blocking admission; no broad reset or guessed cleanup is added. Fault→healthy acquisition fixtures cover writable cleanup after the injected admission failure.
- This Linux host exposes `/proc/self` in a different PID namespace from `getpid()`. Current-process identity uses independent self observation with a pidfd. Other-PID observation refuses namespace mismatch instead of comparing an unrelated host image. Actual Windows external-process identity is pending; Linux contention still exercises real file leases/processes.
- Epoch mismatch and interrupted publication are tested. Valid same-epoch old CLOSED snapshot replay, old binaries that ignore the protocol, physical migration/rollback and unavailable storage cannot be fenced by this JSON foundation. No production settings/state were migrated.

Contractor next: publish reviewed bytes, obtain the eight required Windows cases without skips plus retained workflow/full regression outcomes, then record output verification. Keep G03-B/physical migration/G04/Q2 OPEN and make their next concrete producer/boundary decision separately. No deployment, MT5/VPS/account/credential/AutoTrading action is implied by this source result.
