# TIP-071 — close scoped SQLite connection when setup fails

Parent head ce621625324a3872faee5302ec27c35b684d5217, tree59a359fd2e953e0d030c8308811187cdfacc1bb0. Branchline PR65, main70e2112 unchanged. User authorized continuous source deepfix/deploy legacy; no per-TIP approval needed. Contractor/Builder boundary applies.

## Proven trigger and scope

Contractor independently called exact-parent ScopedResourceCoordinator._db against an owned scratch SQLite DB while another connection retained a real read transaction. Original PRAGMA journal_mode=WAL failed with SQLITE_BUSY5. Holding the original exception/traceback kept its _db-local connection reachable and SELECT42 succeeded. The helper creates its connection before its setup PRAGMA statements, but its callers enter close-finally only after successful _db return.

This is a reproducible cleanup defect riêng. It does NOT establish cause of the original Windows scoped guard timeout, MCP-32603 or MT5 IPC. Preserve all old failures and UNKNOWN. No diagnostic-only successor; the candidate must contain the actual production cleanup correction.

## YAGNI-3 before implementation

1. Needed: deterministically close a newly created scoped SQLite connection when its setup fails, including while the original exception is retained.
2. Reuse: existing _db/SQLite connection.close and exception propagation; existing scoped tests/owned temporary DB, no new service/pool/utility.
3. Shortest: wrap only the two original PRAGMA statements and successful return in try/except; close exactly once on setup error and re-raise the same original exception. If close itself fails, retain both errors through existing Python exception chaining, keeping setup error primary.

## Acceptance

- With a real owned SQLite setup SQLITE_BUSY and retained original traceback, the created connection is closed; the original error object and SQLite errorcode/name remain unchanged.
- Both first and second setup statement failures close the newly created connection; unexpected/interruption error semantics remain preserved.
- Failed connect does not invent a connection or cleanup action.
- Successful _db returns a usable open connection configured WAL/FULL; existing original argv/signature/SQL/timeout/guard/durability and transaction order unchanged.
- Independent close failure retains original setup exception identity and separate closure error; never a successful result.
- Existing scoped ownership/STRICT/capacity denial/UNKNOWN and TLS delivery controls continue to pass in source tests.
- New tests have finite portable short IDs, unchanged tests outside scope, no source/process effect outside owned scratch.

## Boundaries and delivery

Only production app/vibemql5/fleet/scoped_resources.py _db and bounded regression tests. No budgets/TTLs/dependencies/workflows/SDK/schema/catalog/authority/architecture change, no generic workers/pools/input transfer/FX/financial totals. Separate worktree at exact parent. Builder report/frozen hashes/command/log/JUnit/source manifests; Contractor independent verification before publish. Preserve probe setup errors and earlier CI failures; no CI rerun to replace original attempt.

Candidate requires its own exact-head8/8 and exact artifacts. Production scoped_resources.py is full-Fleet source only and is NOT eligible to overwrite mixed legacy runtime. The previously proposed legacy update target remains one core.py file and its checkpoint/CAS/readback/loaded-instance gates. Current runtime MCP-32603/current guards and old syncUNKNOWN block deployment/restart/native tests; do not relax them.
