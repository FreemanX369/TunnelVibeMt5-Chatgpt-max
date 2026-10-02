# TIP-055A — Deployed M0 checkpoint

Date: 2026-10-02, Asia/Saigon. Original deployed-code checkpoint: **PASS**. Latest M0 enrollment/backup/reload/inventory qualification: **PASS at the 12:07 authorized continuation**, with [actual receipts](TIP-055A-enrollment-qualification.md). The UNENROLLED samples, operator boundary and pending labels below are the retained original deployment observations, not current identity state.

## Authority and result

Owner continuation approval is recorded in [the approval ledger](approval-2026-10-02.md). Implementation [PR #54](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/54) merged exact reviewed head `47a887de4ff206cb976969050dcff40055069cd2` at `277cb56189d90ddc293d700da75c196c4140f705`. The bounded drift/fixture follow-up is [PR #55](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/55).

The six deployed files match source head `8d492dec5d29cdd6f458bf90afb8046e7fbbb91b` and the [deployment manifest](TIP-055A-deployment.md). Its four required CI workflows passed before deployment. Later checkpoint-document commits do not change this deployed source. [Machine-readable evidence](evidence/2026-10-02-m0-deployment.json) records operation IDs, exact hashes, receipt paths, checks, restart results and the actual inventory sample.

No real registry was bootstrapped/updated. No native job, live chart, account, credential or AutoTrading operation was requested. The deployed `unit`/`baseline_aware` suites were deliberately excluded because their existing live VPS cases can operate charts automatically.

## Verified outputs

| Gate | Actual evidence | Result |
|---|---|---|
| Before mutation | READY; queue 0; active job null; native/mutation locks null; A/B/C one process each, 200/200 | PASS |
| Live rollback anchor | `BADMCP-20261002-011554-4060BC9F`, exact old CLI/inventory bytes | PASS |
| New files | Four create writes used the server-enforced empty expected-hash precondition; each receipt confirms empty before-hash | PASS, absence at write time |
| Integration writes | CLI then inventory, exact live SHA CAS and covered checkpoint | PASS |
| Six-file readback | All exact SHA-256 hashes and byte counts match manifest | PASS |
| Fixed compile | `py_compile`, return code 0 | PASS |
| Fixed fixture suite | `runtime_forensics`, return code 0; **41 passed, 2 skipped, 514 deselected in 20.89s** | PASS for isolated fixtures |
| B/C refresh | Supported per-instance restarts; B PID 3572, C PID 1776, each one process, 200/200 | PASS |
| A refresh | Detached `BRESTART-20261002-012319-49A13A10`; completion at `2026-10-02T01:23:30.4416282+07:00`, PASS, `terminal_touched=false` | PASS |
| Current A runtime | Tunnel PID 4924; supervisor 5368; MCP 5112; generation `345c2471c6954197af261655f2ece107`; fresh heartbeat and HEALTHY watchdog | PASS |
| Public inventory | All five aliases and every pre-existing inventory field exactly equal the pre-deployment sample; new M0 fields visible | PASS |
| Compatibility | Fixed MT5-2; 85 tools; unchanged catalog SHA `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef` | PASS |
| Real identities | Five `UNENROLLED` rows, null IDs/generations/revisions, `UNQUALIFIED`, no detected conflicts, routed-native false | OPEN, no enrolled physical targets |
| Backup/reload/real root qualification | No real registry exists yet; operator receipts not available | OPEN |

The VPS contains additional legacy tests beyond the repository snapshot, explaining the deployed fixture count. The synchronous check returns counts, not named skip reasons. Windows CI on the deployed source ran **333 passed, 4 skipped**; its skip log lists two absent deployed MT5-root cases and two POSIX identity cases, so the Windows junction fixture executed there. This is CI-host evidence, not a physical VPS-root certificate. See [run 36905070117](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/36905070117).

MT5-2 still reports configured build 6140, observed build 6230 from `BT-20260929-143719-805BD7`, observed at `2026-09-29T07:38:11Z`. This is retained historical authority, not a newly run test. Other build values remain configured metadata. TIP-053 / 0.2.42 metadata is unchanged because M0 adds no catalog/version contract; payload hashes and the actual overlay establish what was installed.

## Receipt and recovery boundaries

Checkpoint and write receipts are under `C:\VibeMQL5\evidence\runtime\backend-admin`; the JSON evidence includes each full path. The A completion receipt SHA-256 is `ae207d6c6f6b6aaa199014e32d1fe4178565d47604d368adf231b310c033c002`. Read it with `backend_read_evidence(relative_path="backend-admin/BRESTART-20261002-012319-49A13A10.json")`: this API is already relative to `evidence/runtime`.

The first receipt request during reconnect timed out with HTTP 504. A subsequent health request returned READY; a corrected relative-path read retrieved completion PASS. The initial incorrectly prefixed `runtime/` read returned generic `INVALID_ARGUMENT`; neither error proves the receipt was absent. No duplicate restart was issued.

The public resilience record still exposes its historical Soak PASS for generation `58cd0f1bcb3346439b81afe2116226eb`, before this refresh. That record is retained; it does not certify the new generation. No fresh soak was run or claimed for this bounded M0 checkpoint.

`jobs.py` remains the exact reviewed deployed drift file, SHA `e1bbc44058006803f2203af916a333575cd80efcf0cef778fba55024dc902759`. Its comments/docstrings differ from Git but its statement AST/imports were verified compatible; it was not overwritten. The rollback procedure restores the checkpoint-covered integration only and retains new modules/test. No restore was needed; recovery execution and exact new-file removal are not claimed as tested outcomes.

## Concrete operator step to close enrollment

This chat exposes guarded backend source operations, but **no identity CLI executor**; `state/fleet` is outside its file allowlist. Generic PowerShell MCP remains excluded. Fixtures cannot stand in for real enrollment. Use the existing local CLI in an authorized interactive VPS session:

```powershell
Set-Location C:\VibeMQL5
$env:PYTHONPATH = 'C:\VibeMQL5\app'
& 'C:\VibeMQL5\.venv\Scripts\python.exe' -m vibemql5.adapters.cli --root C:\VibeMQL5 identity-show
```

Require `UNENROLLED` before the initial command below. If state is `INVALID`, stop and retain evidence; never delete/recreate it. If already `ENROLLED`, review the existing IDs/revision and preserve a verified backup instead of assuming initial state. Coordinate identity writers and retain command JSON/exit status.

```powershell
& 'C:\VibeMQL5\.venv\Scripts\python.exe' -m vibemql5.adapters.cli --root C:\VibeMQL5 identity-bootstrap
& 'C:\VibeMQL5\.venv\Scripts\python.exe' -m vibemql5.adapters.cli --root C:\VibeMQL5 identity-show
```

Bootstrap enrolls all configured rows atomically; resource conflict/config mismatch/invalid state must stop qualification. A successful write alone is insufficient: review canonical executable/data-root observations, keep a hash-verified complete backup outside mutable working state, and repeat `identity-show` in a fresh process. Device ID, terminal IDs/generations/revision must remain unchanged. Do not edit JSON or reset IDs to resolve a failure. The [operator guide](TIP-055A-operator.md) defines CAS/update/replay/recovery.

Then refresh public `list_terminals` through the existing MCP read path. Require the same device ID, distinct stable terminal IDs, positive generations and `QUALIFIED` for at least two physically independent pilot bindings, retained legacy fields and routed-native false. Null canonical observations or merely different lexical paths do not close this gate. Retain the backup hash, CLI receipts and public inventory result against the exact source manifest. This identity work does not require a native run or another service restart.

## Next capability gate

The later [actual enrollment checkpoint](TIP-055A-enrollment-qualification.md) now closes real local enrollment, backup/reload and inventory resource qualification for all five rows. M0 is PASS for its approved scope. TIP-057R may use these actual IDs while retaining its unresolved additive schema/deadline/cleanup/no-start contract and physical live-read acceptance gates. Gateway, remote nodes, native routing and concurrency remain subsequent TIPs.
