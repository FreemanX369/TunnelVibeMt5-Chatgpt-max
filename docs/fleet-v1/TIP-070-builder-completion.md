# TIP-070 Builder Completion Report

Builder implementation is frozen and focused verification PASS. Contractor independently verified the focused suite; final review/publication, exact-head CI/artifact qualification and guarded deployment remain OPEN. Current worktree parent is `7a4535b1cdaed3d7cb5d484642c099239944ab6b` / tree `96b5e4e553100655ecb304d14bf7e31ba114ffcb`; this report does not identify a new published candidate. PR65 remains Draft OPEN/unmerged; main remains `70e2112da9fe8eaa6262f2ba896b55bf3e078260`. Parent qualification remains NOT_ACCEPTED_6_OF_8.

## Result and boundaries

A future allowed synchronous `backend_run_tests` call now publishes a durable, discoverable invocation before the suite helper executes. A fixed `backend-admin/test-runs/sync-invocations.json` index exposes the newest32 generated descriptors through the existing `backend_read_evidence`. The index is RECENT discovery only. Evicted descriptors never mean their invocations are inactive or complete. Every invocation record is retained; no cleanup/reset/deletion is implemented.

The record transitions atomically from INVOCATION_STARTED to a returned, timeout or exception state, retaining the original id, suite and start timestamp. Individual revisions are not immutable. This is a single-record ledger consistent with the existing async storage style, not separate start/final files or event sourcing. Index rows contain paths/start facts, with honest total/eviction counters; they contain no status or PID authority.

Normal returned payloads and object identity are unchanged. Soak STARTED means the method returned a started/recovered soak; it does not mean the soak passed or completed. Unsupported suites retain their original BLOCKED payload without new invocation or helper effects. All original suite bodies, argv, timeout180/300, baseline framework-error denial and async tools remain unchanged; the renamed private helper is AST-identical to the parent method.

Only `subprocess.TimeoutExpired` becomes a structured business result: FAIL/TEST_RUN_TIMEOUT, returncodeNone, finite timeout metadata, bounded4096-character stdout/stderr tails and descendant_outcomeUNKNOWN. It does not dump the command or exception text. This is a business FAIL result, so the MCP protocol can return `is_error=false`; clients must inspect `status`/`reason_code`. Unexpected exceptions keep their exact original object and existing SDK masking; their durable final receipt contains exception_type without raw text/args.

Corrupt/oversized index, invalid/colliding generated path, or failed start/index publication prevents the suite helper from running. Partial start evidence remains retained. A failed terminal publication cannot return an accepted normal result. With an unexpected primary exception or TimeoutExpired plus independent publication failure, the original object remains the raised primary and explicitly chains the publication error, retaining both fault identities. Any unfinished record's completion and descendants remain UNKNOWN. These records never authorize restart or infer current process ownership.

## Frozen implementation

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `app/vibemql5/backend_admin/core.py` | 78852 | `1700bb519292cdfed4dc64452ad62c3e7a362b5407c29271bae456332bb32e18` |
| `tests/unit/test_tip070_sync_test_receipts.py` | 18252 | `f191fc73aa2f8f54781533a0356d4e7cac5c70fcf325bda9ccf9b52179cd6dbb` |

Production delta is120 added lines in core.py; one new regression module adds48 controls. No other parent source files changed. No dependency, workflow, SDK/catalog/schema, production timeout, authority, account, ownership, package, service or worker changes were made. Derived full-source MCP/facade/preflight variants are not copied onto legacy.

## Verification

Builder frozen v1:101 PASS,0 FAIL,0 ERROR,0 SKIP; JUnit14.516 seconds. This includes48 new controls plus53 existing backend contract/restore-CAS/TIP066 actual SDK controls. The new controls exercise real bounded subprocess success/exit7/timeout with flushed partial stdout/stderr, normal object identity, baseline denial/budgets, safe bytes/text/Unicode tails, malformed timeout metadata, RECENT cap/retention, malformed discovery/path/storage denial before work, independent final-publication faults, original exception identity/masking and actual MCP SDK concurrent read/discovery and distinct invocations.

The real timeout control requests the unchanged production300-second suite budget, then uses a controlled5-second real child bound to exercise subprocess.run's timeout branch. This finite fixture bound changes no production deadline. It proves the direct owned subprocess timeout behavior in this control and supplies no descendant or VPS closure proof.

Measured176 Python-source before/after manifests are identical. The215-entry supplemental source manifest matches a frozen manifest derived from exact parent bytes plus the two pre-test frozen files. The other213 parent source entries, including workflows and88 other application files, match the exact parent. The original allowed-suite body is AST-identical after renaming.

The initial command setup exited4 before test collection: relative freeze paths used the wrong cwd and an unsupported progress-plugin flag was supplied. Raw `focused-v0.log` and command metadata are retained. The corrected frozen v1 uses the existing opt-in `-p fleet_source_progress`; no test assertion or production fix was made for that setup error. External causal scan v1 and its failed annotation-envelope assertion are also retained; corrected v2 PASS is reported separately.

Contractor independently reproduced actual MCP SDK timeout normalization on the same coreSHA1700bb51 with an owned bounded real child; `deepfix-20261007/contractor/sdk-timeout-control.log` and `.json` are external Contractor evidence. Partial stdout/stderr, discovery and terminal record matched; protocol business FAIL semantics are recorded above. Contractor's independently run plugin-enabled focused suite also passed101/0skip in13.37 seconds, with `deepfix-20261007/contractor/focused.log` and `focused.junit.xml`. Those raw receipts remain independent of this Builder report.

## Legacy deployment and OPEN gates

The only proposed production overlay file is core.py. Its parent71407-byte SHA4f5b4b9b5002279d6daa1f8ad49e3d3701be719197e648fda87864bf50348573 matches the historical installed manifest. Fresh live source/hash compatibility, checkpoint/CAS, typed guards, source/artifact qualification, readback and loaded runtime verification are still required by Contractor before an update. No GitHub publication, CI rerun, runtime file write, restart, native test or other VPS effect was performed by Builder.

This change repairs the proven future synchronous test receipt/timeout defect. Current all-tool MCP-32603 cause, READY/PIDs/queue/locks, old synchronous unit outcome and MT5-2 current IPC/login/session/data-root remain UNKNOWN. It does not recover or identify the old receiptless run. Historical failed demo jobs A/B remain retained and tester execution remains NOT_RUN. Fresh feed, actual FIFO overlap, native tester result/report/cleanup/handoff/final health and demo readiness require new runtime evidence. Physical full Fleet/private VM/two-node/real SDK and production merge remain OPEN/NOT_RUN. No source or runtime acceptance is inferred from this focused PASS.
