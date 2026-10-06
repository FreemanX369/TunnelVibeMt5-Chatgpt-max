# Fleet v1 — Complete source handover

The 06/10 continuation dispatches [TIP-066](TIP-066-live-diagnostics.md), a bounded
source correction for five anticipated legacy live-read errors masked by SDK 2.1.1.
Only three existing MCP reads change their error boundary; catalog, input schemas,
target denials, actor/native ownership and successful outputs stay unchanged.
Its Builder/Contractor receipts and current Draft #65 description determine the new
candidate gate. Accepted parent fe6ef1b remains historical 8/8 source acceptance;
it cannot qualify a changed candidate. Fresh typed runtime observations remain
MCP -32603, with current guards and old synchronous unit outcome UNKNOWN.
No recovery, rerun, deployment or native test occurred in this continuation.
Full Fleet physical qualification and production merge remain OPEN/NOT_RUN.

Rejected parent `81d458ff` completed **6/8 on original attempt 1**. Its
[retained receipt](evidence/tip065/ci-81d458f/metadata/verification-receipt.json)
binds five original ZIPs, unchanged exact Git 210-entry manifests, complete JUnit,
nine harmless proofs and lossless decoded logs. Linux passed 1202/16 skips;
Windows had 1205 PASS/one setup ERROR/12 skips; Deep had 1205 PASS/one FAIL/12 skips.
All 29 earlier required Windows controls passed. The independently reviewed [ABI reuse
completion](TIP-065-windows-metadata-bindings-completion.md) removes repeated pure Windows
metadata binding setup while preserving fresh buffers, OS queries and every
file/path/hash/authority check. Historical timing causes remain unproven. The
reviewed new source needs its own full 8/8/artifact gate before the authorized
five-file legacy read-only overlay deployment. Full Fleet activation and physical
VM/MT5/SDK qualification remain OPEN/NOT_RUN. No CI rerun or overlay restart occurred.

Earlier candidate d9adc579 completed **7/8**; [original receipt](evidence/tip065/ci-d9adc57/metadata/verification-receipt.json)
retains five verified ZIPs, exact unchanged 210-file manifests, JUnit/nine proofs.
Both integrated platforms and eleven new Windows preservation controls passed.
Deep failed the blocked-native lost-ACK fixture; [the reviewed identity correction](TIP-065-lost-ack-identity-completion.md)
preserves its unexpected transport error. It cannot repair or identify historical
COMMIT latency. The reviewed new candidate still needs its own 8/8 before the
authorized read-only overlay deployment. Physical acceptance remains OPEN.

Previous candidate b9a6cb4 completed **6/8**; [original failed evidence](evidence/tip065/ci-b9a6cb4/metadata/verification-receipt.json)
includes five independently verified ZIPs, all 210 unchanged source hashes, JUnit,
nine harmless proofs and full decoded logs. Fourteen required Windows controls
passed. The independently reviewed [failure preservation](TIP-065-failure-preservation-completion.md)
repairs three concrete missing diagnostic boundaries without changing product,
assertions or budgets. It does not identify historical worker/storage causes.
No overlay deployment or restart occurred. The reviewed newly delivered candidate
requires its own complete 8/8 and original artifacts; physical qualification remains OPEN.

The [bounded fixture correction](TIP-065-CI-refinement-completion.md) passed its
Windows controls, but candidate f2b65c3 completed only 6/8. Its failed receipts
are retained. [Capacity/pending-COMMIT diagnostics](TIP-065-COMMIT-diagnostics.md)
add missing evidence while retaining all assertions/budgets and frozen product/
overlay bytes. Each newly published Draft #65 head needs its own complete 8/8
gate before the authorized diagnostic deployment; original timeout causes stay OPEN.

Current deployment direction (2026-10-05): the owner has authorized tests and
deployment. This supersedes the historical deployment deferral below, without
waiving physical qualification. Accepted source checkpoint `f25ec99` passed all
eight workflows. Thirty-one new modules were staged with create-only CAS; the live
TIP-053/0.2.42 adapter retained its original behavior and 85-tool catalog.
[TIP-065](TIP-065-deployment-preflight.md) prepares a read-only diagnostic overlay
to observe ownership and dependency blockers. Its candidate gate, exact overlay
hashes and actual live observations are recorded in the current PR description and
deployment receipt; earlier source CI cannot qualify that new candidate. Full Fleet
activation and private VM/MT5/SDK qualification remain OPEN.

Status: SOURCE BUILD COMPLETE for M1–M5 and TIP-064 under the owner's continuous authorization. The delivered source is the current head of [Draft #65](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/65); source acceptance requires all eight workflow checks on that same head, including complete Linux/Windows integrated artifacts. [Source verification](source-update-verification.md) preserves the review and historical receipts. Private VM, real MT5/SDK qualification and production deployment remain for the owner after build.

## Included update

| Milestone | Concrete output | Source evidence |
|---|---|---|
| M1 | Qualified isolated SDK implementation; singleton gateway; signed outbound HTTPS; bounded reads and partial snapshot | [SDK report](TIP-057R-SDK-completion.md), [control report](TIP-058A-completion.md), [transport report](TIP-058B-059-062A-completion.md) |
| M2 | Node-owned project/session placement, immutable inputs, STRICT baseline and prepared real dedicated native drivers | [Completion](TIP-061A-057N-completion.md), [verification](TIP-061A-057N-verification.md), [qualification](TIP-061A-057N-qualification.md) |
| M3 | Durable gateway/node jobs, fresh effect authority, exact cancellation, historical recovery, joint restore and scoped immutable artifacts | [Jobs/artifacts report](TIP-060-completion.md), [restore report](TIP-060C-completion.md) |
| M4 | Signed physical resource profile, full-set FIFO reservations and prepared scoped native/SDK paths | [Scoped capacity report](TIP-056-completion.md), [build contract](TIP-056-scoped-build.md) |
| M5 | Possession-verified principal, single project writer, both source/session commit fences and registered real Git worktrees | [Writer report](TIP-061B-completion.md), [worktree report](TIP-063-worktrees-completion.md), [worktree operator contract](TIP-063-worktrees-operator.md) |
| TIP-064 | Explicit gateway/node startup, protected client configuration, separate fleet catalog and full Linux/Windows source workflow | [Integration report](TIP-064-completion.md), [operator handbook](TIP-064-operator-handbook.md) |

The retained 85-tool catalog, legacy/null fixed MT5-2 behavior, historical schema hashes, old jobs and evidence remain the baseline. Fleet tools are an optional separate catalog. Default or absent scoped qualification preserves the global capacity-one boundary. Input transfer, account/currency totals and generic Repo Worker/pools remain deferred.

## Owner test sequence after build

1. Select the exact final Draft #65 source commit and retain a clean code snapshot, immutable histories, protected keys/configuration and consistent journal backups. Record actual node roots/device/terminal generations and Windows sessions; do not reuse another installation's private identity.
2. Configure and start one external gateway with the selected TLS identity, explicit policy limits and protected owner/signing files. Configure outbound nodes and verify signed pairing, heartbeat, current route/session, inventory, restart and stale-key/route denial. Opening a fleet MCP client does not start a gateway.
3. Verify catalog discovery in the actual client and the retained legacy schemas. Submit bounded reads/snapshots with exact target references; absence of an installed SDK qualification must return a truthful denial. Follow the [SDK qualification procedure](TIP-057R-SDK-qualification.md) on a disposable environment before permitting actual SDK observations.
4. Follow the [native qualification procedure](TIP-061A-057N-qualification.md) using an explicit dedicated idle tester. Verify candidate/input/EX5 hashes, actual source/target attribution, compile/test/capture/cancel and retained worker/descendant closure. No account or AutoTrading changes are part of this source update.
5. Exercise network loss, lost delivery/result ACK, crash windows, revocation and journal reopening. UNKNOWN, pending effect and missing closure must block another effect. Test supported coordinated restore with the independent operator checkpoint and all configured node witnesses; copying an old database alone cannot make admission ready.
6. Measure real resource independence, load/latency and fairness before installing the [capacity profile](TIP-056-completion.md). Verify the same signed full-source/runtime/target roster through HTTPS. Then test simultaneous independent terminals and native/SDK conflicts. A signed source-test fixture is not physical evidence.
7. Provision two client principal keys without distributing the owner's administrative token. Exercise assigned writer/CAS, revoke between commits, DRAINING reconciliation and real registered worktree prepare/commit/retire. Verify the main source/session stays unchanged by an isolated Git commit. Test stop-admission while existing authorized work/cancel/result ACKs drain.
8. Execute the selected migration and rollback test on the exact candidate/topology. Retain every failed or superseded receipt. Physical release acceptance is recorded separately from source/harmless CI acceptance.

## Migration and rollback anchors

Supported recovery remains conservative: an issued/UNKNOWN session phase with no confirmed commit cannot be reissued or cleared, even if the current session revision is unchanged. Same-intent drain supports a session phase never issued, or an exact already completed commit. No force-clear API is supplied. Coordinated restore requires its independently retained exact checkpoint and all configured witnesses; it does not infer missing control ledger history from an older database. Keep these limits in the later physical test expectations.

The canonical cumulative parent is Draft #64 head `e74bdee81db3db3d5ae774a99a9146d74742ea8a`, tree `8836bba9e813e0a542dcbcb6e84ca9c27fee99ef`; current base main is `70e2112da9fe8eaa6262f2ba896b55bf3e078260`. Existing M0 and Q1/G03-A/B1/C1 records remain historical proof, rather than a new physical approval.

Before rollout, stop new fleet dispatch and prove applicable ownership is closed. Initialize new stores only once on the selected fresh configured installation; reopen existing stores without initialization. Preserve node-owned ProjectSession/checkpoint/revision history and the distinct new fleet operation namespace. Keep gateway control/job/domain/principal and node transport/job/domain/writer/worktree state with their explicit backup/recovery contracts. Do not copy credentials into source repositories or clone packs.

For rollback, stop new fleet admissions first and drain or quarantine outstanding commands. Keep immutable histories, all epochs and UNKNOWN/occupied records. Revert compatible code/client configuration only after its state-readability and ownership contract is verified. Removing a marker or deleting a journal is not a safe way to release an uncertain producer or make old code accept new work. Restore uses a consistent supported snapshot plus independent signed reconciliation, never a boolean ready toggle.

## Continuation in another session

The 05/10 continuation preserves the original `8019a52` 7/8, `375e6af` 6/8 and `fe199eb` 5/8 checkpoints, adding [fixture diagnostics](TIP-064-transport-diagnostics.md) [cleanup/failure preservation](TIP-064-fixture-cleanup-refinement.md) and [startup/ordinary-backup refinement](TIP-064-startup-backup-refinement.md), with separate Builder and independent Contractor evidence. The suppressed original owner-grant failure remains `ORIGINAL_CAUSE_UNKNOWN`; no product fix is inferred from a later PASS. Use the exact delivered head and its eight checks/verified artifacts identified in Draft #65's current description and the external handover. Do not return to C1 or rebuild TIP-056. Actual VM/SDK/MT5 and physical release qualification remain OPEN.

Read this index, [continuous authorization](continuous-build-2026-10-03.md), [source verification](source-update-verification.md) and the relevant Completion Reports. Use Vibecode Kit v6: Contractor designs/delegates/reviews; Builders implement, test and report. Continue the approved source refinements without per-TIP permission requests. Preserve source/physical evidence distinctions and failed receipts. Do not infer deployment or VM/account effects from the completed source authorization.
