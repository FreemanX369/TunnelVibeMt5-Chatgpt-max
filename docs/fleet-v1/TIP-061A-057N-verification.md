# TIP-061A / 057N source verification

Date: 2026-10-03. Workdir: source checkout `fleet-update-build`. Evidence classification: portable synthetic signature/driver/scoped fixtures and retained core source regressions. Actual MT5/SDK/private VM effects were deferred. Actual harmless Windows Job Object cases are present and require Windows CI.

## Related verification command

```bash
PYTHONPATH=/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages:app:tests/unit python -m pytest tests/unit/test_tip061a_057n.py tests/unit/test_tip057n_qualification.py tests/unit/test_tip057n_windows_owned_process.py tests/unit/test_tip014_project_sessions.py tests/unit/test_tip055a_runtime_forensics_identity.py tests/unit/test_tip055b_runtime_forensics_release.py tests/unit/test_tip057rg03a_native_ownership.py tests/unit/test_tip024_multiclient_concurrency.py tests/unit/test_tip052_metrics.py tests/unit/test_tip056_scoped.py tests/unit/test_tip056_resources.py tests/unit/test_tip060_authorization.py tests/unit/test_tip060_journal.py tests/unit/test_tip064_integration.py -q --tb=short
```

Prior broad source checkpoint: **340 passed, 7 skipped in 19.22s**. Current STOP-refined owned source suites: **102 passed,4 Windows skips in5.20s**, using only the three owned test files from that command. A related run during M3/064 recovery projection edits returned159 passed,4 skips,3 integration failures; those foreign-owner failures were reported and require the final integrated rerun. Owned suites comprise 78 placement/native + 24 qualifier cases; four owned Windows cases are skipped on Linux. Other three skips belong to retained native platform controls. No errors or failed tests remain in this run.

Earlier parallel fixture retries exposed a real source-guard admission race: the old zero-wait capture could deny another independently scoped job while the brief global snapshot guard was held. Native source capture now waits only the explicit installed signed `resource_wait_ms` budget. The source guard still ends before the long scoped lifecycle. Final parallel test confirms both tester callbacks overlap and a new source/session commit preserves the old running candidate's snapshot. Earlier failed source receipts are not physical qualification.

Compileall for the five fleet modules, three additive core modules and three owned tests passed. `git diff --check` passed. Existing proof files/workflows, source authentication, journal/resource coordinators and domain adapters are owned by their respective Builders; this checkpoint does not rewrite their prior evidence.

## Required actual harmless Windows cases

- Fixed Python process is suspended, observed/bound before resume, its child remains in the held Job and explicit breakaway fails; actual worker exit + ActiveProcesses zero close ownership.
- Pre-resume injected fault retains a suspended exact worker/BOUND authority until explicit exact fixture cleanup.
- Parent crash kills its held contained worker while the persisted BOUND authority remains blocked.
- Expiry after durable create-attempt blocks the actual CreateProcess call; the attempt fence remains blocked and no worker is produced.

These cases carry HARMLESS_WINDOWS_JOB_OBJECT_ONLY evidence and cannot fulfill REAL_MT5 controls or generate an installed product qualification. Final Windows workflow receipts and exact whole-build head/hash are Contractor integration work.

## Source checkpoint integrity

The completion report records the SHA256 for every owned source/test and the qualification procedure. Its bundle SHA256 is `cd2dee85cb1aeeb9a7608ee8ed79ee2fb2914bc2cc1ceaf6ef973c8ad118353f`, from canonical JSON using sorted keys and separators `(',',':')`. Recompute on the final checkout; any change requires refreshed source verification and later exact installed physical approval.

The source constructor defaults to denied when trusted qualification is missing. Portable positive signature tests validate a fictitious operator claim only. Shared runtime tests cover two exact target rows, missing target approval, duplicate physical/terminal identities, signer/candidate/runtime drift and target mismatch. Trust file mode/hardlink/path checks run before installed data can supply an operator key. Native delegates final Windows owner/DACL checks to the protected shared node_keys helper; root integration verifies its actual OS fixture.

## Retained-handle stop amendment

The adapter exposes pure `has_retained_work()`. Current owned unclosed handles keep STOP_PENDING even after futures/ACK maps finish; metadata-only or previous persisted UNKNOWN alone does not hold the current process open. No polling/termination/closure/TTL clear is performed by this query. The existing Windows pre-resume fault test asserts actual held handles and exact cleanup boundaries. The source helper fixture forbids any query-induced poll or close.

M3 historical review now requires actual process identity for real closure and finite known global/scoped authority records. Recovery-only outcome projection prevents raw rich diagnostic trees being copied into a restoration witness. Normal result/artifact data is preserved and correlated by the original canonical receipt digest. M3/064 own final projection/TLS verification.
