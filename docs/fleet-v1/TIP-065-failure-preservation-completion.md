# TIP-065 — Independent failure-preservation review

Status: bounded fixture evidence/lifecycle repair PASS; new exact source gate
PENDING 8/8. Historical timeout/worker causes OPEN/UNKNOWN. Deployment/restart
NOT_RUN; physical VM/MT5/SDK qualification NOT_RUN. Contractor review under the
[approved contract](TIP-065-failure-preservation.md), 2026-10-05.

The [Builder report](evidence/tip065/failure-preservation-v1/builder-completion-report.md)
and [frozen manifest](evidence/tip065/failure-preservation-v1/frozen-source-manifest.json)
bind exactly three changed source files against b9a6cb4. All 89 application files
and the other 207 source entries, including workflows, dependency locks, config,
TIP-065 observer and previous COMMIT/capacity controls, remain identical. The exact
five-file legacy overlay payload remains SHA256
`0efadd3d855b602e6bd8d58cd7033f092395026b633bceb28629e75fe4003182`.

| File | Final SHA256 |
|---|---|
| test_tip060c_https_restore.py | 1e444c1f5f8f0f9f7920a73dcd08c2efa7b871529de9f5e9ebf27045e087b26c |
| test_tip061a_057n.py | bdfe5fcdf81213f4998547ac6f47dad906c12681b4b2b2e9d4564f0d39de9f2e |
| test_tip064_integration.py | 9f80d8f325bbb67001f7ce0b595257ae8510ce97421d462afc3b167b02382358 |

Independent review confirms both futures are observed after the existing event is
released, including on parent failure. Original parent/worker errors retain identity
and notes; failed/NOT_RUN/CANCELLED receipts cannot pass either mandatory COMPLETED
assertion. Only two finite actual callback stages/statuses enter diagnostic notes.
The three-party barrier, pinned predecessor/source mutation assertions and final
actual resource CLOSED/RELEASED checks remain required.

Restore observes the actual replacement server through the existing diagnostic TLS
client. Every already-owned cleanup resource is attempted and every error survives
with the original primary. Node job/transport owners are retained only for successful
first-phase handoff; an aborted handoff now closes them. Actual SQLite/thread controls
prove closure, multiple original exception identities, one unchanged stop observation,
and an open retained handle on the successful path. Native-denial observation reads
exactly the original get_job callback, preserves its FAILED predicate, and retains
only finite state/reason/sequence. Original predicate and all cleanup errors survive.

Builder's full focused run was **197 PASS / 3 platform skips**, zero failures/errors.
Contractor independently ran the three changed files plus transport, capacity,
gateway-fixture and frozen preflight controls: **247 PASS / 5 platform skips**,
zero failures/errors. All 210 hashes were unchanged during each run. Those receipts
are explicitly **PRE_CONTROL_COMPLETION_ORDERING**. One new negative control was then
ordered on actual Future completion before its deliberate short barrier fault;
Builder and Contractor each verified the final control **1 PASS / zero skips/errors**.
The final manifest matches Contractor disk exactly. Full exact-candidate source/CI
verification remains required; counts from these overlapping runs are not added.

The locked Python 3.12.14 environment uses pytest 9.1.1, MCP 2.1.1 and cryptography
50.0.1. Complete argv/environment, logs, JUnit and manifest hashes are retained in
[focused receipt](evidence/tip065/failure-preservation-v1/focused-v1-receipt.json),
[final Builder control](evidence/tip065/failure-preservation-v1/control-final-receipt.json),
[Contractor focused](evidence/tip065/failure-preservation-v1/contractor-focused-v1-receipt.json)
and [final source review](evidence/tip065/failure-preservation-v1/contractor-final-source-receipt.json).

All existing positive and product barrier/future/predicate/server/HTTP/SQLite/control/
hold/cleanup budgets, the literal capacity <1.5s assertion, TLS and FULL/WAL durability
remain unchanged. The new fault control's setup observes actual completion using the
normal 10-second observation before forcing its intentional .02-second barrier fault;
its .1-second collection receives an already-done future. No workflow was rerun.

The [b9a6cb4 failed gate](evidence/tip065/ci-b9a6cb4/metadata/verification-receipt.json)
remains immutable. A later green head does not identify historical OS/storage or
worker causes. Pending-future observation does not terminate/reset/qualify that worker;
existing executor shutdown still depends on actual return. Setup failures outside
these bounded ownership phases remain outside this repair. Full Fleet migration,
protected configuration/process/connector registration and physical qualification
stay OPEN. The reviewed source must pass its own 8/8 and original artifact gate before
the already-authorized read-only diagnostic overlay is deployed. No main merge,
credentials/AutoTrading action, authority/UNKNOWN reset or generic PowerShell.
