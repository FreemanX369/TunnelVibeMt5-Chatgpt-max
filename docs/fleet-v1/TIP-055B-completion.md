# TIP-055B Completion Report — Windows lease release liveness

**Implementation status: DONE. Qualification status: PARTIAL.** The bounded correction and isolated regressions are implemented and all final local checks passed. Actual Windows CI deny-delete handle execution and any guarded deployed qualification remain Contractor gates. This report makes no Windows-platform or deployed-fix claim from POSIX results.

Owner authorization: continuation “Duyệt tiếp tục theo plan”, 2026-10-02T02:12:19+07:00. Contract: [TIP-055B](TIP-055B.md). The worktree was supplied as the verified 160-blob snapshot of main `db9a12895c1b908fb6b0e61f89f9d76db1b04415`, tree `ac094ada3c0817515aec49062556843d5c0ba076`; its synthetic local snapshot commit is not a remote GitHub parent. No applicable `AGENTS.md` was found.

## YAGNI-3 and reuse decisions

1. Necessary: the real Windows release failure in issue #56 leaves the current owner file present while the old implementation sets `released=True`. Later releases then return without cleanup, stranding the serialized lease while its owner process remains alive.
2. Reuse: retain `_QueuedFileLease`, existing token/PID/FIFO paths, Path-compatible methods and existing ticket cleanup. Reuse `jobs._read_json_object(..., attempts=1)` to reject malformed/non-object JSON. The helper's default retries accept general `PermissionError`/WinError5; deliberately disable those retries and apply only the narrower Windows sharing/lock policy at release.
3. Smallest sufficient output: one bounded release loop plus a private per-lease mutex. The mutex was added after Contractor review identified a concrete duplicate-release race: two callers on the same object can read the old token before one deletes the owner file, then the second can delete a successor. It serializes only calls on that object; no global lock path, acquisition order or capacity changes.

The retry budget is one monotonic second, using the existing 50 ms lease polling cadence and shortening the last sleep to the remaining budget. Only diagnosed `winerror` 32 and 33 are retried. A check after sleep prevents another attempt beginning when the deadline has expired. General permission errors, WinError5/other error codes, bad JSON, bad token types, empty/whitespace-only tokens and path errors remain explicit. Tokens remain opaque strings; no UUID format/schema restriction was introduced.

## Files changed by Builder

| File | Change |
|---|---|
| `app/vibemql5/core/concurrency.py` | Import the existing JSON reader and `threading`; add one local release mutex; validate and re-read ownership on each release attempt; confirm true path absence with `lstat`; delay completion until deletion, confirmed absence or known non-ownership; preserve retryability on unresolved failure; retain the three observed VPS comments exactly. |
| `tests/unit/test_tip055b_runtime_forensics_release.py` | Add 31 portable temporary-root cases and two actual Windows deny-delete handle gates; selected automatically by the existing `runtime_forensics` filename selector. |
| `docs/fleet-v1/TIP-055B-completion.md` | This report. |

Contractor-owned TIP/index/approval/requirements/runtime documents were not edited by Builder. No workflow, catalog, suite, MCP API, acquisition, native routing, physical terminal configuration or package-version change was made.

## Behavior and acceptance results

The completed flag is checked under the per-lease mutex. Every attempt reads a JSON object and validates its token before any owner deletion. A matching token permits unlink; a valid different token completes this object's release without deleting the current file. A missing read is considered completed absence only when `lstat` also confirms there is no path: an existing dangling/unreadable path is not falsely classified as absent. Any unresolved failure leaves `released=False`. Existing best-effort waiter cleanup remains in `finally`, including on failure.

| AC | Result | Evidence |
|---|---|---|
| B01 | Local PASS; actual Windows gate pending | Injected WinError32/33 at both ownership read and unlink recover on retry; release completes and repeated completed release performs no further attempt. Native and mutation context-manager cleanup both recover from injected sharing denial. |
| B02 | Local PASS; actual Windows gate pending | Persistent injected WinError32/33 exhaust the exact one-second retry budget, raise the original error, preserve owner bytes and `released=False`; a later allowed release removes the file. All attempted retries begin before the deadline. A separate real Windows persistent-handle case enforces the same failure/retryability behavior. |
| B03 | PASS locally | General permission errors and WinError5/other codes receive one attempt with no retry sleep; malformed JSON, non-objects, missing/non-string/empty/whitespace token, invalid UTF-8, non-file path and an existing path whose read raises FileNotFound all fail explicitly without blind deletion or false completion. Ticket cleanup is exercised on malformed ownership failure. |
| B04 | PASS locally | A successor token installed before retry is retained byte-for-byte; corrupt replacement remains explicit/retryable; confirmed disappearance completes release. The synchronized concurrent-release regression installs an actual successor lease between first deletion and completion; only the first caller attempts owner deletion and the successor survives. |
| B05 | PASS locally | Normal deletion, initial absence and repeated `release`/Path-compatible `unlink`/`__exit__` are compatible. Existing FIFO, sequence, dead/live-owner-related concurrency, native and mutation checks passed, followed by the full unit suite. Existing FIFO wait timeouts were not lengthened. |
| B06 | PENDING actual Windows CI | Two `os.name == "nt"` fixtures use `CreateFileW` with read/write sharing and without `FILE_SHARE_DELETE`, prove actual WinError32/33 from unlink, then verify transient recovery or persistent failure followed by later successful release. Failure to create/use the Windows mechanism fails the test; Windows fixture setup does not skip. POSIX execution explicitly skips these two platform gates and is not Windows proof. |
| B07 | PASS locally | Existing registered-catalog checks pass; count remains 85 and catalog SHA-256 remains `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef`. Capacity remains one for native and mutation work. The fixed MT5-2 policy, global lease paths and existing acquisition/lock order are unchanged. |
| B08 | PASS locally | All three observed comment lines occur exactly once. Existing fixed compile traversal passed. Existing `pytest -q -k runtime_forensics tests` selects the new isolated module with no selector/suite/API change. No broad unit/live-chart execution is required to select the new module during supported runtime qualification. |
| B09 | PASS for evidence preservation; platform/deployed evidence pending | Retained the injected baseline-failure and no-mutex sensitivity failures in separate logs; retained final successful candidate logs separately. Existing issue #56 CI failures were not changed or erased. The evidence classes are separated below. |
| B10 | PASS for Builder scope | No VPS operation, identity bootstrap, physical enrollment, native job, live chart, account/credential/AutoTrading operation, generic PowerShell MCP call, GitHub publication, merge or direct-main write was performed. |

## Exact final local results

Runtime: Python **3.12.14**, `/workspace/scratch/250985b4823e/audit/tunnel-venv/bin/python`, working directory `/workspace/scratch/250985b4823e/tip055b-work`, with `PYTHONPATH=app`.

| Check | Exact result |
|---|---|
| New regression module | `31 passed, 2 skipped in 0.51s` |
| Supported selector: `python -m pytest -q -k runtime_forensics tests` | `67 passed, 3 skipped, 300 deselected in 3.13s` |
| Regression plus existing concurrency/FIFO/catalog: `python -m pytest -q tests/unit/test_tip055b_runtime_forensics_release.py tests/unit/test_tip024_multiclient_concurrency.py` | `45 passed, 2 skipped in 1.14s` |
| Final full local suite: `python -m pytest -q tests/unit` | `344 passed, 26 skipped in 8.90s` |
| Fixed compile traversal | All 57 `app/vibemql5/**/*.py` files plus the new regression module compiled with `py_compile.compile(..., doraise=True)`: **58 passed**. |
| Diff whitespace | `git diff --check`: PASS. |
| Catalog and drift manifest | Count/order/hash verified; baseline and observed drift full AST equal; exact observed comments retained once each. |

The selector's third skip is the existing Windows junction identity fixture. The two new Windows handle skips are platform gates. Broader unit skips retain their existing fixture/platform conditions. None of these skipped checks is reported as executed Windows proof.

Expected negative controls were run in separate Python processes without changing candidate files:

| Negative control | Result and meaning |
|---|---|
| Execute the verified-main concurrency source in the isolated module process; select `persistent_denial_expires` | **2 failed, 30 deselected**, exit 1, in 0.12s. Both WinError32 and WinError33 cases fail because old `released=True` remains after denied owner deletion. |
| Replace only the candidate's private release mutex with `nullcontext`; select `same_lease_concurrent` | **1 failed, 32 deselected**, exit 1, in 0.07s. The second caller reads the old token while the first is pending and reaches the successor window. The candidate with its mutex passes that synchronized behavior test. |

## Runtime and comment manifest

| Payload | Bytes | SHA-256 |
|---|---:|---|
| Verified-main concurrency source | 19,649 | `74700aa7db7ee5279dd1166bbcb5465ce939b1da06858cbbd6123fb1eaa365f4` |
| Observed VPS concurrency drift snapshot | 19,896 | `bf7603ce7b2566eb13b3596944253dcee7005b22442b77dc3a2f9edc55c32c2e` |
| **Frozen candidate** `app/vibemql5/core/concurrency.py` | **21,029** | **`94a8b2a82e2a55914d37a42516e893ef508536dd2c5106c378a4ee9b6342dbcc`** |
| **Frozen regression** `tests/unit/test_tip055b_runtime_forensics_release.py` | **15,316** | **`e5807e389b7b8f6064fe77ad522beaf1f85ce1931c3df95235334f3b236e586a`** |

The deployed-comment payload retains these exact observed lines:

```python
    # Compatibility with the historical worker lock Path contract.
            # Audit is diagnostic provenance, not the safety primitive. Lock/CAS failures
            # remain fail-closed independently and must not be hidden by audit I/O noise.
```

Code and tests are **FROZEN** at the hashes above for Contractor review/publication. No further Builder edits to them are planned unless review identifies a concrete issue.

## Retained local evidence paths

Contractor preserved the raw local logs in [the repository evidence directory](evidence/tip055b-local/) and bound their hashes/results in [the local evidence record](evidence/2026-10-02-tip055b-local.json). The baseline fault control preceded addition of the same-lease concurrent case, explaining its earlier 30 deselections; that historical failure is retained as captured. Contractor independently reran persistent failure/recovery, fresh-owner checks and same-lease concurrent release: **6 passed, 27 deselected in 0.26s**, against the frozen final hashes.

These absolute paths identify retained scratch evidence for Contractor condensation; they are not external CI or deployment receipts:

- `/workspace/scratch/250985b4823e/audit/tip055b-baseline-release-regression.log`
- `/workspace/scratch/250985b4823e/audit/tip055b-unserialized-release-regression.log`
- `/workspace/scratch/250985b4823e/audit/tip055b-candidate-runtime-forensics.log`
- `/workspace/scratch/250985b4823e/audit/tip055b-candidate-concurrency.log`
- `/workspace/scratch/250985b4823e/audit/tip055b-candidate-unit.log`

Evidence classes remain distinct: original issue #56 real Windows CI failure (pre-existing, retained by Contractor); this report's injected POSIX faults and sensitivity controls; pending exact-head actual Windows handle CI results; pending later guarded deployed temporary-root fixture evidence. Passing a rerun of old CI or these POSIX fault controls does not qualify a deployed Windows fix.

## Issues, deviations and remaining gates

No unresolved local test failure remains. The only implementation addition identified during review is the private same-object release mutex, explicitly requested and accepted by Contractor as bounded ownership preservation. No architecture deviation was made.

The retry bound is a one-second retry budget after this call acquires its local release mutex; normal OS I/O and another caller's ongoing release can add elapsed wall time. The existing cross-process ownership protocol is unchanged; no atomic compare-and-unlink fencing protocol was introduced. Known successor tokens are checked before deletion on every attempt, and concurrent callers on the same lease object are serialized.

Contractor still needs to bind the reviewed candidate to a real remote-parent PR, verify all four exact-head workflows including both actual Windows handle results, then apply the already-authorized guarded rollout protocol before any deployed-fix claim. Enrollment/physical target bindings remain independent and OPEN; this correction produces no enrollment receipt. The existing integration backup/new-file recovery limitation also remains a Contractor rollout consideration.
