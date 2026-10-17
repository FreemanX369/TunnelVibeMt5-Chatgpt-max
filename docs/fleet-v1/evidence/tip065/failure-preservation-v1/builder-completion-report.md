Builder Completion Report — bounded fixture failure preservation

Base source is b9a6cb402cc969d3ac618f9eeb2de678c6837e17, tree 653ab3c2d4460d9b76bfc94f683c7786c0fac30a. Contractor approved exactly three existing test files after YAGNI-3. This work repairs demonstrated fixture evidence loss and aborted handoff cleanup. It does not establish or repair the historical transport/performance causes. Historical CI cause OPEN; new source gate OPEN pending independent review/publication/8-of-8 CI; physical qualification NOT_RUN; activation NOT_QUALIFIED.

YAGNI-3: necessary because parent barrier failure skipped all worker results, restore lacked existing sanitized transport observations, and native-denial timeout retained no result from its already-performed predicate reads. Reuse existing preserve_fixture_failure, stop_gateway_fixture and FixtureHttpsClient. The shortest scope is three test files; no new producer, authority, endpoint, retry, package, workflow or product behavior.

Observed historical evidence at exact b9a6cb4:

| Failure | Proven observation | Still unknown |
|---|---|---|
| Windows two prepared scoped producers | Parent reached.wait(timeout=10) raised BrokenBarrierError. Source finally released workers but skipped both future.result calls. | Whether a worker failed or arrived late, its actual stage/error/outcome. |
| Bootstrap restore worktree | runtime.reconcile reached a real POST and bare HttpsClient raised HTTPS_UNAVAILABLE. | Original inner exception type/server stage and transport failure cause. |
| Bootstrap delayed capacity | Failure was final post-release pump, after the retained three-step <1.5 assertion passed. Snapshot at timeout showed capacity_source_manifest/verify_capacity_roster; cleanup separately showed COMMIT reserve_nonce. Existing group retained both. | Time contribution/latency cause beyond sampled stacks. No capacity/product optimization is justified. |
| Bootstrap inventory native denial | Original three-second pump exhausted without reaching expected FAILED state. | Last actual gateway state/reason and worker progress; no evidence of unexpected native execution. |

The original raw logs remain intact under final-evidence-b9a6cb4. This local run is not a reproduction of those historical causes.

Changes frozen:

- test_tip061a_057n.py always collects both original futures after releasing the event, even if parent failed. Existing COMPLETED assertions remain mandatory. Original parent plus all raised worker errors are retained by identity; returned FAILED, NOT_RUN, CANCELLED or malformed/noncompleted results fail with a finite sanitized status note. Two finite actual callback stages survive returned receipts; source mutation/pinned-old-candidate and actual CLOSED/RELEASED assertions remain. Controls prove worker failure before broken parent barrier, two original worker errors retained with parent, noncompleted receipts rejected, original completed receipt identity retained, and secret/unhashable diagnostic stage values excluded.
- test_tip060c_https_restore.py reuses FixtureHttpsClient at the same HTTP1000 cap and TLS identity. After real server restart, the client observes the actual replacement thread. Cleanup always attempts all already-owned resources and the original stop observation, retaining every cleanup exception with the original primary. The first-phase retained nodejobs/transport stay open only on successful handoff; primary or cleanup failure closes them. Controls prove real SQLite handles closed, actual owned thread stopped, all four cleanup errors and original notes retained, and successful handoff leaves the retained handle open. The helper calls stop once at the original5s.
- test_tip064_integration.py captures only finite state/reason/sequence from original get_job predicate calls and annotates the original pump exception. It issues no new HTTP/DB lookups, preserves the literal FAILED predicate, and retains all resource cleanup errors with primary identity. Controls prove one callback per call, safe last STARTING state on timeout, no fabricated state after callback failure, finite redaction/types, original error/notes retained, and actual SQLite resource closure.

Budgets and assertions preserved: real three-party overlap barrier, reached10/released10/future10; native-denial pump3; restore start5/stop5; HTTP1000, TLS, SQLite, round, hold and cleanup budgets; capacity literal <1.5. All89 app files, observer/provenance/validator/MCP product bytes and workflow/lock/config manifests match the baseline. No live write/restart, commit/push/deploy, physical SDK/MT5 execution, account/credential/AutoTrading change or journal/evidence reset.

Verification:

1. focused-v1:197PASS/3skip/0FAIL/0ERROR,200cases,25.296s JUnit. Full210 source hashes were unchanged pre/post. This receipt is PRE_CONTROL_COMPLETION_ORDERING, preserved rather than overwritten. Includes all three original affected files, transport negative/security/COMMIT controls, both real capacity modes, normal grant/start/stop paths. Contractor separately recorded247PASS/5skip on these pre-ordering bytes.
2. After review, only one new negative control changed: completion Event is set by actual Future.add_done_callback, observed with normal10s before the deliberately shortened .02 barrier fault; .1 collection observes an already-done future. This avoids attributing host scheduling to the controlled worker fault. control-final:1PASS/0skip/0FAIL/0ERROR,0.163s JUnit. All210 source hashes unchanged pre/post. No unrelated source edit or repeated whole-suite run.

Exact cwd is /workspace/scratch/1818a0d45fa0/repo. Python is /workspace/scratch/1818a0d45fa0/deploy-20261005/source-venv/bin/python; environment override PYTHONPATH=app:tests/unit. Locked versions: Python3.12.14,pytest9.1.1,mcp2.1.1,cryptography50.0.1. Exact argv, harness watchdogs, timings and log/JUnit SHA256 are retained in focused-v1-receipt.json and control-final-receipt.json. The harness watchdog does not change product deadlines.

Evidence is in /workspace/scratch/1818a0d45fa0/tip065-failure-preservation-20261005: baseline copies/all-source-before; frozen copies; builder-three-file.diff; focused-v1 and control-final full logs/JUnit/receipts; frozen-source-manifest.json. Manifest binds all210 sources, each changed before/frozen SHA and verification artifact hashes. Only the three approved source files differ from baseline. Contractor-owned docs are outside this Builder change.

Remaining limits: local Linux fixtures do not qualify Windows/MT5/SDK or prove historical causes. Existing ThreadPoolExecutor shutdown still depends on actual workers returning; collecting a pending future reports failure/uncertainty and does not terminate, reset or qualify that worker. Setup/checkpoint failures outside the affected try/finally ownership phases are not newly generalized here. Full canonical source acceptance and all8 workflows remain for Contractor at a published exact candidate. A later green gate cannot retroactively prove these historical failures fixed.

Product/test bytes are frozen. Builder stopped editing and handed off for independent Contractor verification.
