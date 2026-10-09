# TIP-065 — Preserve unexpected transport identity at lost-ACK boundary

Continuous Contractor contract, 2026-10-05. Exact d9adc57904c57c7446028e1d7d9b97eb5d2f84cf,
tree fd3edac1de610b821ca64044acd4fdfa1cc03192, completed 7/8 on attempt 1. Deep
run 37291278924/job 111701994729 recorded 1201 PASS, one FAIL, 12 skips. All other
workflows passed; integrated Linux 1198/16 skips and Windows 1202/12 passed. The
[retained receipt](evidence/tip065/ci-d9adc57/metadata/verification-receipt.json)
binds five original ZIP digests/sizes, exact unchanged 210-entry manifests, complete
JUnit and nine harmless proofs. Eleven new preservation controls executed PASS on
Windows. No overlay deployment/restart or workflow rerun occurred.

## YAGNI-3 before code

1. Necessary: the actual Deep trace proves an unexpected WireError is replaced by
   an expected-code AssertionError, violating the original-primary identity contract.
2. Reuse: the existing lost-ACK branch and stop/cleanup fixtures. No equivalent
   production latency optimization is established by current facts.
3. Smallest scope: one existing test file, a shared single-run_once fixture handler
   and meaningful error/return/call-count controls. No product or budget changes.

The primary /results timeout arose at domain-record completion (domain.py1028);
cleanup separately timed out at native result/progress completion (1012). Both
server snapshots were reserve_nonce COMMIT. Observed 766/906 ms are consistent with
the remaining shared 1000-ms drain-round budget, which includes earlier local work.
They do not demonstrate a misconfigured HTTP cap or identify underlying storage/
scheduling latency. Original WireError and notes survive in context, but the fixture's
assertion made its primary an AssertionError. This correction restores identity;
it cannot be described as fixing COMMIT latency or a historical incident.

Builder may change only tests/unit/test_tip064_integration.py. At the existing
try/catch position call the shared handler exactly once. Return a normal run_once
response unchanged. For an unexpected WireError use bare re-raise; for the deliberate
FIXTURE_LOST_ACK preserve the identical close/STOP_PENDING assertion. Keep the actual
three-second cancellation loop, five-second harmless hold, two-second cleanup,
run_once/close call counts, all predicates, TLS, durability and every
HTTP/round/SQLite/hold/cleanup budget. No extra HTTP/DB lookup, retry, cache, reset or
authority change. The frozen legacy overlay payload and all application files remain
unchanged.

Controls prove original normal response identity and one call/no close; unexpected
error identity/notes and one call/no close; intentional lost-ACK one call/one close;
wrong close status still fails the required STOP_PENDING assertion. Run the original
actual TLS blocked-native case and existing primary/cleanup controls once in focused
verification, retain full 210-file pre/post manifests, command/env/log/JUnit and freeze
a Builder report. Contractor independently reviews and verifies before a new exact
candidate. No passing fixture substitutes for 8/8 or physical qualification; no
green candidate proves a functional/root-cause timeout repair.

Migration, protected configuration/process/connector registration and private
VM/MT5/SDK qualification stay OPEN/NOT_RUN. Deployment remains the already-authorized
five-file read-only diagnostic overlay after the delivered head's own complete
eight-workflow/artifact gate. No main merge, account/credentials/AutoTrading action,
authority/UNKNOWN reset or generic PowerShell.
