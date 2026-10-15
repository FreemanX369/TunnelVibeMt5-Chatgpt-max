# TIP-071 Builder Completion Report

STATUS: DONE — bounded production cleanup correction and source controls complete. No commit/publish or VPS effect. Worktree tip071-builder, parent ce621625324a3872faee5302ec27c35b684d5217/tree59a359fd2e953e0d030c8308811187cdfacc1bb0.

## Trigger and correction

An owned real SQLite exclusive transaction makes the original _db PRAGMA WAL raise SQLITE_BUSY5 within its unchanged1000ms configured wait. Holding the original exception/traceback retains the new connection and its owned database descriptor:1→2 descriptors before traceback inspection, SELECT42 still usable after the owner rolls back. Explicit close restores the prior descriptor count. Another exclusive transaction can succeed, so this probe proves open connection/file-descriptor retention, not a persistent SQLite transaction lock.

Only app/vibemql5/fleet/scoped_resources.py::_db changed in production. The two original setup statements and successful return now have setup-failure cleanup. Close runs once; the same original setup error is re-raised. If close also fails, the setup error stays primary and the exact close error is its chained cause. Connect failure happens before this cleanup block. Normal connect arguments, configured wait, WAL/FULL SQL, return/signature, guard, transaction/checkpoint order, dependencies and authorities remain unchanged.

The independent Contractor review at fix-20261007-1439/contractor/review-receipt.json additionally verifies the real builtin SQLite busy path closes the traceback-held connection without a subclass/injected failure. This report does not turn either reproduction into original Windows scoped guard timeout or live MCP-32603 root-cause evidence; those causes remain UNKNOWN.

## Files changed/frozen V2

- Production scoped_resources.py:40771B, SHA2563bac3def3188c3e2a8440eac90e9d7a5c3cc88118f9b56356f3af1a5494c8f3c.
- New tests/unit/test_tip071_scoped_db_setup_cleanup.py:7010B, SHA2560f7261eeb5f5c52df8c0eda5d9f2c94c535bc020575cd3e90f3a1be53690a34e.

216 source entries are identical before/after frozen V2 checks.214 existing parent entries remain unchanged. Whole-module AST outside _db, and the normal _db connect/SQL/return/signature, match parent. No edits followed V2 freeze. No other production/test file changed.

## Tests and retained failures

New controls cover real SQLITE_BUSY with retained traceback, real SQLite authorizer denial of each PRAGMA, successful WAL/FULL use, failed connect, unexpected setup failure, KeyboardInterrupt/SystemExit, and independent close failure with setup error identity and closure traceback/note preserved. Sixteen unique controls; maximum PYTEST_CURRENT_TEST teardown identity139 UTF16 units.

- Original production/new-test V1 baseline:13FAIL/3PASS,16 cases. Raw failure logs/JUnit retained.
- Initial fixed production/new-test V1:4FAIL/12PASS. Four new controls incorrectly required a reverse __context__ link that Python removes to avoid an exception-chain cycle. Production already preserved the setup primary and cleanup __cause__. This failed revision and exact test bytes/hash remain intact.
- Frozen V2 replaces that unsupported reverse-link assumption with the same cleanup cause identity plus retained traceback/note:16PASS/0skip,16 cases.
- Scoped/resources/gateway-capacity/native-ownership/SDK/project-target/TLS compatibility:236PASS/1platform skip,237 cases in27.60s. This includes the delayed capacity TLS case on this scratch Linux environment; it does not explain or supersede the original Windows failure.
- Every retained run's START/FINISH count, ordinal/function and outcome matches its complete JUnit:32/32/32/474 progress rows respectively.

The unchanged old CI failure stays failed. No CI rerun, old backend suite rerun, native tester, deployment/restart, account/credentials/AutoTrading effect or physical qualification occurred. Candidate needs independent exact-head8/8/artifact gates after publish; current runtime guards and old synchronous run remain UNKNOWN. This Fleet production file is not a target for the mixed legacy overlay.

## Evidence delivery

Commands, collection/control identities, logs/JUnit, V1/V2 hashes/source manifests, scope verification and summaries are saved beside this report. Pre-fix owned probe remains separate at continuation-20261007/builder-sqlite-probe-v1 with its verified four-file manifest. The compact manifest includes only top-level receipts/evidence, excluding all fixture working directories, SQLite databases, TLS material, compiled assets and caches.
