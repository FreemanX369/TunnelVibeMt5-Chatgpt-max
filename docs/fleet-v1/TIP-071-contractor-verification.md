# TIP-071 — independent Contractor verification

Status PASS_INDEPENDENT_FROZEN_SOURCE_REVIEW. Parent ce621625324a3872faee5302ec27c35b684d5217, tree59a359fd2e953e0d030c8308811187cdfacc1bb0. Candidate CI/artifacts still PENDING; source acceptance is not inferred from local tests.

A real owned scratch SQLite read transaction caused the exact-parent _db WAL setup to fail with SQLITE_BUSY5. Retaining the original exception/traceback left its connection open and SELECT42 succeeded. Builder independently reproduced the same error and one extra owned DB descriptor; closing the connection returned to baseline. Independent exclusive access succeeded in that probe, so no persistent SQLite lock or causal link to original Windows guard timeout is claimed.

Production diff is seven added/two removed lines, only ScopedResourceCoordinator._db: close a just-created connection when either setup statement fails, re-raise the exact setup exception; a separate cleanup error stays chained. Signature, initial connect/timeout/isolation args and normal two PRAGMA statements/return match parent AST. Every other module statement/method matches parent AST. Of216 frozen source entries, other214 existing entries match exact parent Git; only scoped_resources.py changed and one regression module was added.

Contractor ran46 cases independently (16 new controls plus scoped/TLS/capacity compatibility):46 PASS/0 skip in21.780 seconds. All92 START/FINISH rows match JUnit identities/outcomes;216 hashes unchanged before/after. These cases overlap some Builder runs and must not be added together as distinct coverage. Builder reports separate focus16 PASS and compatibility236 PASS/1 skip.

The Contractor separately repeated the actual SQLITE_BUSY trigger with the built-in sqlite3.Connection, without a subclass or injected error: the retained helper connection is now closed, original SQLITE_BUSY5 preserved, and reopening returns usable WAL/FULL plus original data. This isolates the cleanup correction from instrumentation behavior.

Retain baseline regression13FAIL/3PASS and BuilderV1 new-control12PASS/4FAIL. Four new-control failures asserted an incorrect Python __context__ back-link; V2 checks the actual independent cleanup cause identity, traceback and original note, while production bytes and all older assertions stay unchanged.

Frozen production40771B SHA2563bac3def3188c3e2a8440eac90e9d7a5c3cc88118f9b56356f3af1a5494c8f3c; regression7010B SHA2560f7261eeb5f5c52df8c0eda5d9f2c94c535bc020575cd3e90f3a1be53690a34e. No budget/TTL/dependency/workflow/schema/catalog/ownership/writer/native/architecture change.

Original Windows scoped guard failure and current live MCP-32603 still have causesUNKNOWN. Fresh typed reads07:40UTC/14:40ICT all failed before backend result; current PIDs/queue/locks/old sync/MT5 session remainUNKNOWN. No VPS effect/restart/old suite or CI rerun. Physical qualification and production merge stayOPEN/NOT_RUN.

After publish, require own exact-head8/8 and artifact checks. Full-Fleet scoped_resources.py is not an eligible legacy overlay target. Previously reviewed legacy core.pySHA1700bb51 remains the sole candidate update, after fresh installed hash/guards/checkpoint/CAS/readback/loaded verification. No blind restart, full-source copy, account/credentials/AutoTrading changes or evidence reset.
