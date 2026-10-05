# Fleet v1 — Continuous source verification

Current continuation: the [two-file CI refinement](TIP-065-CI-refinement-completion.md)
has independent 163 PASS/5 platform skips and unchanged product/overlay bytes.
The new canonical head in Draft #65 requires eight successful workflows and exact
artifacts before deployment. The rejected checkpoint below remains retained.

TIP-065 candidate `ec9180e`, tree `66022a510d6d59285c9250d75aa83e038cad24b0`,
completed seven of eight workflows on attempt 1. Bootstrap failed two fixtures
with 1178 passed/12 skips; Deep and integrated Windows passed 1180/12 and Linux
1176/16. [The retained receipt](evidence/tip065/ci-ec9180e/metadata/verification-receipt.json)
preserves the five original ZIPs, exact 210-file verification, JUnit/proofs and full
Bootstrap log. Both required TIP-065 Windows metadata controls executed PASS.
[The bounded refinement](TIP-065-CI-refinement.md) corrects a positive fixture's
ACTIVE overlap assumption and a manually constructed runtime's missing sentinel/
masked cleanup error. Product denial and all budgets remain unchanged. The primary
result-delivery TimeoutError's underlying mechanism remains OPEN; no overlay was
deployed and the next candidate requires its own eight successful checks.

2026-10-05 continuation: accepted head `f25ec99` completed all eight workflows
on attempt 1; original five ZIP digests, 207 source hashes, JUnit and harmless
proofs were independently verified. The owner's later instruction authorizes tests
and deployment. The resulting 31-module staging did not activate the Fleet source
adapter. [TIP-065](TIP-065-deployment-preflight.md) continues with bounded read-only
preflight observations and a separate legacy MCP overlay; every new source head
requires its own complete eight-workflow gate. Physical qualification stays OPEN,
and the original masked owner-grant incident remains UNKNOWN. The current exact-head
and deployment receipts in Draft #65 supersede historical deferral/status text below.

Status: **M1–M5 AND TIP-064 SOURCE IMPLEMENTED**. This is the cumulative Contractor review under the [continuous authorization](continuous-build-2026-10-03.md). All included source tasks have Builder reports and reviewed tests. Acceptance of the delivered [Draft #65](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/65) head requires all eight workflow checks to succeed on that same head. Its integrated Linux/Windows artifacts must contain matching head/tree, unchanged source manifests and complete unit/proof results. Historical checkpoint evidence below does not substitute for those checks. Physical MT5, SDK, private VM, deployment and actual client acceptance remain deferred.

## Requirement coverage

| Requirement | Concrete source boundary | Reviewed evidence |
|---|---|---|
| REQ-F01 | Retained identity registry and node inventory overlay | Stable IDs/generation conflict cases; authenticated HTTPS inventory discovery |
| REQ-F02 | Retained legacy facade/catalog/jobs; opt-in fleet catalog | All legacy unit tests and exact 85-tool schema hash; no installed scope means original global ownership |
| REQ-F03 | `gateway_control`, `wire`, `transport`, node keys | Singleton lock, durable replay, pairing/revoke/rotation, real temporary-CA HTTPS, restart and audience/body tamper |
| REQ-F04 | `reads`, `read_broker`, qualified SDK controller/worker | Exact local/remote target admission, current read authorization, deadline/cleanup failures, no SDK call on stale legacy route |
| REQ-F05 | Read broker and partial snapshot client | Missing/offline/stale/deadline coverage, per-target provenance and bounded fan-out; no totals |
| REQ-F06 | `project_targets`, `native`, native qualification/process | Frozen node-owned source/target, immutable compiled bytes, fresh phase proofs, denied unqualified production route |
| REQ-F07 | Gateway/node job journals and node transport journal | Logical replay/collision, lost ACK, intent-before-effect, restart UNKNOWN and no automatic second effect |
| REQ-F08 | Native cancellation and artifact proxy | Exact retained process identity, fresh cancel proof, immutable artifact scope/hash/chunk checks and no restoration side effect |
| REQ-F09 | Existing project/session revisions plus STRICT baseline | Complete environment matrix, source checkpoint/CAS, target/build/input drift, valid effective periods and missing evidence |
| REQ-F10 | Native/SDK signed operator qualification | Actual executable source prepared behind exact runtime/session/restriction gates; harmless Windows lifecycle fixtures |
| REQ-F11 | Serialized resources plus signed scoped coordinator | Full-resource FIFO reservation, common legacy veto, actual producer lifecycle/descendant closure, capacity roster validation |
| REQ-F12 | Verified principal and node guarded writer | Both commit fences, source/session CAS, original-epoch reconciliation, revocation/release DRAINING; [43 focused cases](TIP-061B-completion.md) |
| REQ-F13 | Verified assignments and node Git worktrees | Real temporary repositories/worktrees, isolation, stale owner, dirty/base drift, exact replay/closed-process recovery; [47 focused cases](TIP-063-worktrees-completion.md) |
| REQ-F14 | Separate fleet MCP/client surface | Finite schemas/catalog, authenticated client domain operations, no gateway startup by MCP, real HTTPS integration |
| REQ-F15 | Coordinated restore and TIP-064 source workflow | All authority journal heads, independent node witnesses, staged fenced recovery, exact-head Linux/Windows artifacts, migration/rollback handover |

Deferred REQ-D01/D02/D03 retain their approved scope: input transfer, currency/account totals and generic worker/pool capabilities are not part of this update.

## Retained checkpoint evidence

Draft [#65](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/65) is based on parent Draft #64 head `e74bdee81db3db3d5ae774a99a9146d74742ea8a`, tree `8836bba9e813e0a542dcbcb6e84ca9c27fee99ef`. The complete 299-file parent tree was independently reconstructed before publishing the cumulative update.

TIP-058A source `df0e0c1d62fe22704e51a3c46a8caab1ddbb0368` retains its Linux verification and [first Windows failures](evidence/tip058a/windows-source-df0e0c1/receipt.json). The later test-only source `55b2a12234f858125880f783d81de52feae10bdf` has six successful workflows and one failed Deep Update run. [Its receipt](evidence/tip058a/windows-source-55b2a12/receipt.json) preserves both decoded raw job logs and source-versus-checkout merge equivalence. Bootstrap passed 605 tests with five skips; Deep Update passed 602 with three failed normal backup fixtures and five skips. These are superseded checkpoint results, not final integrated Windows acceptance.

Earlier Linux counts of 833/30, 844/30 and 999/31 are superseded diagnostics, rather than final candidate acceptance. Final evidence must bind a frozen manifest, exact Git head/tree, unchanged source before/after and the complete Linux/Windows workflow. The latest owned source reports are [indexed in the handover](source-handover.md); overlapping focused test counts are not summed into a unique total.

The isolated final-source Linux run passed **1076 tests with 33 explicit platform skips**, and B1 portable passed **39/39**. [Logs, JUnit, source manifests and catalog receipt](evidence/tip064/linux-full-source/summary.json) are retained. Local synthetic head `0390f6c7ce3a710ecfd776f18033cda41f7d4579` attests frozen tree `e16184c4aad9176029a700fe7da5fe74ada6aed5`; it is not the canonical repository head. Source before/after was identical. Subsequent report/hash/evidence documentation changes do not alter the workflow source manifest. This retained local run is superseded by canonical integrated source checks.

## Completed Contractor refinements

Canonical candidate `3b955d6121bcc1758740e97989fb69754ae8f51f` matched tree `4e4f35675d2d71c5ee5db3573ace3a6c10d93abb`, but integrated CI failed. [The retained receipt](evidence/tip064/ci-3b955d6/receipt.json) records five successful workflows and three failed workflows, original artifact ZIP hashes, exact source manifests and lossless raw logs. Linux executed PowerShell cases absent locally: 1091 passed, 5 failed, 13 skipped. Windows full source had 945 passed, 63 failed, 93 setup errors and 9 skips; many setup errors shared the same early transport or metadata failure. Q1 16/16, G03-A 8/8, B1 10/10 and portable B1 39/39 passed. These failed results are superseded checkpoints, not source acceptance.

Concrete follow-up corrections preserve existing authority and qualification requirements: [PowerShell JSON timestamp strings](TIP-054-PowerShell-CI-refinement.md), native Win32 retained file identity instead of Python fd/path stat aliases, numeric retained ACL facts, an expired-connect fence before sending an HTTP body, [numeric temporary listener origins](TIP-064-CI-refinement.md), host-canonical STRICT fixtures, normal recovery fixture budgets and bounded malformed Git output errors. Current report hashes are recomputed after the corrections.

The next checkpoint `ebbb56c67d8948b8b8c633b5fdd9739e235073c7`, tree `e7b2c2d068bae5e08f6fa6948120f85bb3cdce86`, passed five workflows and failed three. [Its retained receipt](evidence/tip064/ci-ebbb56c/receipt.json) verifies both original artifact ZIP digests and all 204 source hashes against the frozen candidate. Linux passed 1112 tests with 14 explicit skips and zero failures/errors. Windows integrated full-unit exceeded the original 300-second harness budget; all four independent portable/Q1/G03-A/B1 cases passed. Complete Deep/Bootstrap Windows suites passed 1110 tests, but retained fixture failures/setup errors at 455.50/420.99 seconds. Their lossless raw logs remain alongside the receipt. Follow-up source keeps the strict negative assertions, uses short oversized-record IDs and host-canonical fixture paths, waits for real monotonic stop expiry/async owner closure, and budgets the complete unit harness at 600 seconds with each independent proof bounded at 120 seconds under the unchanged 20-minute workflow. These changes require the delivered head's own successful checks.

* Normal backup fixtures now use a 1000 ms test deadline; independent 100 ms contention/timeout cases and product deadline policy remain preserved.
* Native phase/effect authorization and immutable predecessor receipts pass through the heartbeat owner. STOP_PENDING keeps current RPC, progress, exact cancel and final ACK drainage alive, including retained native handles.
* Reads revalidate the exact current command before SDK observation. Installed SDK/native implementations require sealed exact physical qualification; synthetic or legacy-positive routes cannot select them.
* Persisted domain, profile, recovery and worktree evidence has bounded exact schemas and is reverified against current configured trust. Nested recovery evidence is validated before persistence.
* Native inputs/EX5 are immutable snapshots; short source-capture and M5 mutation share the existing guard. All resource sets/worker slots are reserved together; UNKNOWN never frees capacity.
* Joint restore binds transport/job/domain/principal/writer/configured Git heads to the independent checkpoint. Never-writer read-only nodes use EMPTY_ABSENCE only with no authority files/markers or gateway assignment/phase/command history.
* Protected startup pins retained file identity, key ownership, CA bytes and TLS staging. Explicit pairing persists intent before HTTPS; lost ACK retries exact input only in the narrowly compatible transport-only state. Mixed initialization remains quarantined.
* Principal-only client configuration distributes no owner bearer. Real registered worktree mutation records ATTEMPTED before Git and CLOSED after retained process/pipe closure; matching HEAD alone cannot recover a lost closure.

Checkpoint `3e402db86b9e6f9cc53489a6b0b88f97cdb516e5`, tree `baadc33d2cbfe40428c5f564f011f763200c929d`, passed seven workflows, including Bootstrap and the integrated Linux/Windows source workflow. [Its retained receipt](evidence/tip064/ci-3e402db/receipt.json) verifies both original ZIP digests, all 205 source hashes and unchanged before/after source. Integrated Linux passed **1118 tests / 14 explicit skips**; Windows passed **1122 / 10 explicit skips**, with no failures/errors. Required actual harmless Windows Q1 16/16, G03-A 8/8 and B1 10/10 passed; portable B1 passed 39/39. Protected ACL/staging and retained native process/descendant cases ran without skips. Deep Update nevertheless failed two fixtures, with 1120 passed and 10 skipped: a positive admission's `TimeoutError` after 1016 ms against a 1000 ms fixture budget, and startup readiness unobserved within five seconds. The full lossless Deep log is retained. Integrated success does not replace the delivered head's eight-workflow acceptance requirement.

Checkpoint `154e954aa631c63c39db639aa93a529e9807f42c`, tree `2d29bc02cb7fc13dabeb32c886f3fa8e3a705561`, passed seven workflows, including both Deep and Bootstrap after the [bounded startup/admission fixture refinement](TIP-064-startup-CI-refinement.md). [Its receipt](evidence/tip064/ci-154e954/receipt.json) preserves both original integrated ZIPs and all 206 source hashes. Linux passed **1121 / 14 skips**. Integrated Windows completed with **1124 passed, one failure, 10 skips**, no setup errors or harness timeout; all independent required proofs passed. The remaining two-slot capacity fixture did not observe all three jobs at `SUCCEEDED` during the shared pump's three-second window. Its actual terminal states were not recorded, so a product cause or specific slow stage is not inferred. The original JUnit and lossless unit log remain retained; the next candidate must pass this boundary and all eight checks.

## Continuation from 8019a52

Head `8019a52b136d0aae71c1a0235e224557d0e9a1a9`, tree `55985ff5f11af083a1c00780f0196eea50c25cfb`, passed seven of eight workflows. [Fresh metadata and retained original logs/ZIPs](evidence/tip064/ci-8019a52/receipt.json) preserve Deep Update's 1125 passed / one failed / ten skipped owner-grant `HTTPS_UNAVAILABLE`; integrated Linux 1122 / fourteen skips and Windows 1126 / ten skips passed. Both ZIP digests and all 206 source hashes were independently compared with the exact Git blobs, with unchanged before/after manifests and zero JUnit failures/errors. These successes do not substitute for the failed eighth gate.

The [bounded diagnostic continuation](TIP-064-transport-diagnostics.md) changes only the transport fixture. It preserves suppressed cause/timing/lifecycle facts, verifies distinct controlled faults and proves a timed-out response can follow an already committed grant without replay. The original incident cause remains OPEN/UNKNOWN; neither a controlled mechanism nor a green new candidate is described as its root-cause fix. Production transport, policies and all authority/UNKNOWN semantics remain unchanged. The newly delivered candidate still requires all eight checks and its own complete integrated artifacts. Draft #65's current description and the external handover identify the final exact-head receipt; no later source change inherits a previous head's gate.

The diagnostic candidate `375e6af790e695aa4f1293268d80cd9a1f111487`, tree `d8072b5217de7855e9925811d9bf6487cb673dcc`, completed **6/8**, with integrated Linux **1127/14 skips** and Windows **1131/10 skips** passing. [All eight workflow identities, five verified ZIPs and complete raw failures](evidence/tip064/ci-375e6af/metadata/verification-receipt.json) are retained. Deep failed the capacity fixture's unconditional cleanup heartbeat; Bootstrap had a server-thread teardown error despite all test assertions passing. Their suppressed transport cause/actual shutdown stage are not inferred. The [follow-up fixture correction](TIP-064-fixture-cleanup-refinement.md) removes an unnecessary control call after proven drain, preserves primary and cleanup failures together, and adds live-stack shutdown diagnostics without changing the normal three-second observation or any product budget. Controlled faults and independent review verify those concrete boundaries; the newly delivered head still needs its own 8/8 gate.

## Legacy compatibility evidence


The independently generated actual MCP schema still has 85 tools. Canonical SHA-256 values: names `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef`; all schemas `64337437115a20a8555cc1214706a503b985195dbdbd219de2adfa35e2c8134d`; the other 83 unchanged schemas `16ceef873678e7d7598874c6e612393e23de35c934f18ab6a31b09ad15bd7541`. The optional fleet client exposes a separate finite 31-tool catalog. Legacy/null native behavior and historical jobs/evidence remain retained.

SDK, native/project and worktree current report file/hash rows were independently recomputed after CI and Windows fixture refinements. Their current source bundles are `75e7ca4e2263159615d90f898b0cfc042e9e42bd451479f40d2670c60235d836`, `992a97f4ea4d86c3ac5159413d3315c30d4d4823a02b6f761832a6b61047855c` and `340c9664d8044df140099d90737d62e2e0b95799804b6d6e495b3d9d7ea71c7c` respectively. The fixture-only follow-up normalizes signed-roster path separators, bounds oversized-record pytest IDs and writes valid worktree Git include paths while preserving the negative assertions; its separate focused Linux receipt is 141 passed, zero skips, recorded with the M3 evidence. Historical counts, bundles and receipts are retained with their original meanings. Final full-source workflow manifests cover shared modules, tests, dependencies, workflows, operator templates and the 21 PowerShell runtime scripts together. Acceptance uses the delivered head's complete Windows CI, rather than these overlapping diagnostics.

## Remaining physical qualification

The owner will test after the complete source handover. Exact deployment endpoint/certificates, node identities/roots/sessions, SDK wheel/DLL and no-start Q2 matrix, dedicated native tester, two-node attribution, loaded capacity/latency/fairness, actual client catalog/artifact delivery, migration/rollback and release topology remain physical acceptance. Temporary keys/certificates, synthetic adapters and harmless process fixtures cannot install or certify these capabilities.

The [handover](source-handover.md) records supported migration/rollback and conservative limitations. An issued/UNKNOWN session phase without confirmed commit cannot be reissued or cleared; joint restore cannot invent control history absent from an old backup. No merge, deployment or real account/AutoTrading action is included.

## 05/10 startup and ordinary-backup refinement

Candidate `fe199eb110cbba83a26491d90ddc14830cdc9e17`, tree `b6717bdfcb32ac31c91438b2934830fb708e5fd6`, completed attempt 1 with five successful and three failed workflows. [Its receipt](evidence/tip064/ci-fe199eb/metadata/verification-receipt.json) keeps all five original ZIPs, exact-head 207-file checks, Linux 1132/14 skips, failed Windows JUnit and raw Deep/Bootstrap/integrated job logs. The failures exposed positive backup progress exceeding the imported 100 ms SQLite budget, unowned startup waits hiding server outcomes and a diagnosed capacity `/poll` response TimeoutError at the unchanged HTTP 1000 ms budget. [The bounded follow-up](TIP-064-startup-backup-refinement.md) requires controls and the next delivered head's own eight successful checks. These observations do not reconstruct the original masked incident or certify physical capabilities.
