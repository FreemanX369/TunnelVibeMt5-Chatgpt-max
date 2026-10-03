# Fleet v1 — Continuous source verification

Status: **M1–M5 SOURCE IMPLEMENTED; FINAL CANDIDATE CI PENDING**. This is the cumulative Contractor review under the [continuous authorization](continuous-build-2026-10-03.md). All included source tasks have Builder reports and reviewed tests. Exact published-candidate Linux/Windows verification is the remaining source handover check. Physical MT5, SDK, private VM, deployment and actual client acceptance remain deferred.

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

The isolated final-source Linux run passed **1076 tests with 33 explicit platform skips**, and B1 portable passed **39/39**. [Logs, JUnit, source manifests and catalog receipt](evidence/tip064/linux-full-source/summary.json) are retained. Local synthetic head `0390f6c7ce3a710ecfd776f18033cda41f7d4579` attests frozen tree `e16184c4aad9176029a700fe7da5fe74ada6aed5`; it is not the canonical repository head. Source before/after was identical. Subsequent report/hash/evidence documentation changes do not alter the workflow source manifest. The canonical published candidate still requires exact-head Linux/Windows CI.

## Completed Contractor refinements

* Normal backup fixtures now use a 1000 ms test deadline; independent 100 ms contention/timeout cases and product deadline policy remain preserved.
* Native phase/effect authorization and immutable predecessor receipts pass through the heartbeat owner. STOP_PENDING keeps current RPC, progress, exact cancel and final ACK drainage alive, including retained native handles.
* Reads revalidate the exact current command before SDK observation. Installed SDK/native implementations require sealed exact physical qualification; synthetic or legacy-positive routes cannot select them.
* Persisted domain, profile, recovery and worktree evidence has bounded exact schemas and is reverified against current configured trust. Nested recovery evidence is validated before persistence.
* Native inputs/EX5 are immutable snapshots; short source-capture and M5 mutation share the existing guard. All resource sets/worker slots are reserved together; UNKNOWN never frees capacity.
* Joint restore binds transport/job/domain/principal/writer/configured Git heads to the independent checkpoint. Never-writer read-only nodes use EMPTY_ABSENCE only with no authority files/markers or gateway assignment/phase/command history.
* Protected startup pins retained file identity, key ownership, CA bytes and TLS staging. Explicit pairing persists intent before HTTPS; lost ACK retries exact input only in the narrowly compatible transport-only state. Mixed initialization remains quarantined.
* Principal-only client configuration distributes no owner bearer. Real registered worktree mutation records ATTEMPTED before Git and CLOSED after retained process/pipe closure; matching HEAD alone cannot recover a lost closure.

## Legacy compatibility evidence

The independently generated actual MCP schema still has 85 tools. Canonical SHA-256 values: names `915a87d829983cbb26125cc26350876e1ece5cdde95e77c76c98881e4b74fdef`; all schemas `64337437115a20a8555cc1214706a503b985195dbdbd219de2adfa35e2c8134d`; the other 83 unchanged schemas `16ceef873678e7d7598874c6e612393e23de35c934f18ab6a31b09ad15bd7541`. The optional fleet client exposes a separate finite 31-tool catalog. Legacy/null native behavior and historical jobs/evidence remain retained.

SDK, native/project and worktree report file/hash rows were independently recomputed. Their source bundles matched `773b3201489dff7327a4065956f40428ff0d052bad8349044efcba6e9a212e12`, `cd2dee85cb1aeeb9a7608ee8ed79ee2fb2914bc2cc1ceaf6ef973c8ad118353f` and `264017150d8cacb9fda95d70ea7aac8bd3310586243a8eec10dff82d7d06a9d3` respectively. The worktree bundle refresh includes the authority Builder's two additional read-only restore cases; its historical three-case receipt is retained. Final full-source workflow manifests cover shared modules, tests, dependencies, workflows and operator templates together.

## Remaining physical qualification

The owner will test after the complete source handover. Exact deployment endpoint/certificates, node identities/roots/sessions, SDK wheel/DLL and no-start Q2 matrix, dedicated native tester, two-node attribution, loaded capacity/latency/fairness, actual client catalog/artifact delivery, migration/rollback and release topology remain physical acceptance. Temporary keys/certificates, synthetic adapters and harmless process fixtures cannot install or certify these capabilities.

The [handover](source-handover.md) records supported migration/rollback and conservative limitations. An issued/UNKNOWN session phase without confirmed commit cannot be reissued or cleared; joint restore cannot invent control history absent from an old backup. No merge, deployment or real account/AutoTrading action is included.
