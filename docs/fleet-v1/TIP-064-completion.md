# TIP-064 Builder completion report

Builder: gateway_tests_review. Methodology: Vibecode Kit v6, Builder implementation with Contractor review. Continuous owner authorization covers the approved source plan; private VM/actual SDK acceptance remains deferred. This report is source evidence and does not claim deployment, merge or physical qualification.

## YAGNI-3

1. Concrete need: the accepted gateway/native/project/principal modules needed an actual owner/client/node composition, usable protected startup, durable finite command references and end-to-end HTTPS evidence. An import-only catalog would not satisfy the plan.
2. Reuse checked: existing HTTPS/Ed25519/SQLite/OS locks, local project sessions/checkpoints/Continuity, common native leases, qualified SDK admission, M3 job/artifact journals, M5 principal/writer/worktree authority and joint restore APIs.
3. Minimal change: one finite domain module, separate optional client/MCP/CLI modules, explicit policy/config templates and a source workflow. No arbitrary shell, repository, URL, worker callback, caller qualification or mutable gateway project replica was added.

## Implemented composition

| Source | Concrete behavior |
| --- | --- |
| `fleet/domain.py` | Bounded exact-schema durable gateway/node command references; immutable replay/conflicts; pre-effect intent; interrupted callbacks UNKNOWN; signed terminal result correlation |
| `GatewayDomain` | Node-owned inventory/project/STRICT/artifact/writer/worktree routes, M3 native and capacity registration, current route/session fences, verified same-journal writer resolution and all-head restore delegation |
| `NodeDomainDispatcher` | Finite dispatch; bounded native/cancel/writer executors; owner-thread RPC/ACK drain; active progress flush before process-bound cancel authorization; no all-history in-memory scan |
| `adapters/fleet_client_tools.py` and `fleet_mcp.py` | Separate optional 31-tool catalog; owner and principal-only clients; private principal-key possession signing; clients never start a gateway |
| `adapters/fleet_cli.py` | Explicit owning-thread gateway factory, outbound node factory, protected config/CA/key/TLS startup, finite client commands, explicit pairing and scoped recovery witness entrypoints |
| `fleet/reads.py`, `core/facade.py` | Typed trusted SDK local branch before one common lease; positive legacy route retains denial and cannot invoke the installed local SDK branch |
| `tests/proofs/fleet_v1/run_source.py`, `verify-fleet-v1.yml` | Exact checkout/platform source manifest, complete unit logs/JUnit, retained harmless Q1/G03A/B1 proofs, Linux/Windows workflow |
| `docs/fleet-v1/config/`, `TIP-064-operator-handbook.md` | Required policy examples, separated owner/principal/read-only/writer configuration, startup/pair/stop/history/backup/restore/physical test guidance |

Startup trust is read through retained descriptors with owner/mode/ACL/no-link checks. CA bytes are pinned in the verified SSL context. TLS certificate/key bytes are loaded through a fresh protected staging directory; Windows holds directory identity against deletion/rename while loading. Production windows semantics must pass the actual Windows candidate run.

The native control loop sends heartbeat before bounded RPC/drain rounds. STOP_PENDING denies new workload while accepting only exact cancels for an already admitted active job. Pending final result ACKs and actual retained native handles keep the owner loop alive. The configured deadline reports truthful uncertainty and performs no automatic kill, lease reset or TTL reassignment.

Read-only replacement startup can disable writer/worktree authority explicitly while retaining its files. Signed native historical recovery returns only a quarantined immutable reference after complete terminal/closure evidence. The original target/session/job and UNKNOWN capacity exclusion are not repainted. Native qualification remains denied without installed evidence.

Principal ACKs are applied only when actually present in the signed result; raw UNKNOWN failures commit without invented ACKs. Exact completed result replay returns the retained receipt before reapplying mutable authority, so later assignment replacement does not destroy receipt replay. Voluntary release and owner fences remain DRAINING until exact phase/fence evidence resolves them. A matching typed completed reconciliation in the same journal can resolve original source UNKNOWN for quiescent heads; original failure bytes remain unchanged.

Complete recovery also supports a node that never had writer authority: a typed EMPTY_ABSENCE witness requires actual writer/worktree data and marker absence, null checkpoint worktree head and zero gateway assignment/phase/command history, including historical admin receipts. Disabled stale files refuse that path. Configured writers supply PERSISTED evidence from their actual journals. Both are bound to the exact current signed node route/session/coordination and never initialize a writer during recovery.

## Verification

Concrete tests cover protected owner and principal-only startup, forbidden config mode/link before HTTP, TLS staging cleanup, initial CLI pairing and safe partial failures, real read-only NodeRuntime replacement startup, inventory discovery before reads, node project references, production native denial, immutable artifact chunk assembly, bounded long native heartbeat/status/cancel/lost ACK, short-TTL fresh effect sequence, principal possession through asynchronous two source/session commits, all configured recovery heads and two signed scoped slots.

Independent owning Builders contribute `test_tip064_writer_resolution_https.py`, `test_tip064_capacity_https.py`, `test_tip060c_https_restore.py` and the actual worktree/SDK/native suites. Their source fixture successes remain explicitly synthetic or harmless; no fixture installs a physical qualification marker.

Earlier diagnostics: 110 PASS across the 064/M5/worktree/060C suite; 39 PASS across 064 plus actual writer-resolution and all-head HTTPS restore. The retained `evidence/tip064/linux-source-v1/` diagnostic is 43 PASS before EMPTY_ABSENCE refinement, without a pre-run source attestation. The final frozen focused log/JUnit and complete before/after source hashes are under `evidence/tip064/linux-source-v2/`. The Contractor's exact candidate/head Windows/full-source run is authoritative. Preserve failed/superseded receipts rather than replacing them.

Final frozen focus: **45 PASS, 0 failures, 0 skips, 10.04 seconds**. The complete before/after source manifest is unchanged; its canonical SHA-256 is `7c48fe66b96505da90b140765ae5cfe315650864edcd9f0c0502a7753052b49b`. The receipt explicitly identifies this as a frozen worktree diagnostic, not a Git base-head qualification. Product/test/workflow/template bytes are frozen for the Contractor's exact candidate snapshot; subsequent defects require new versioned receipts.

A POSIX-only mode/symlink startup rejection is an explicit Windows skip; protected owner/ACL/key/TLS startup positives run on both platforms. Other inherited platform skips must retain their original reason. New actual-Windows fixtures from other Builders are separate from private MT5/SDK testing.

## Remaining qualification gates

Builder source implementation is complete: pairing replay/fault tests and the all-head read-only absence refinement are included in the frozen focus receipt. Exact full-source Linux/Windows checks and Contractor acceptance are required before final source handover. VM/MT5/SDK/broker/account/capacity deployment qualification, actual host credentials, service installation, merge and deployment are outside this source completion claim and remain unperformed.

Do not recover by clearing PENDING, resetting writer epochs, rewriting UNKNOWN, bootstrapping over corruption or restoring an old database without its independent checkpoint and complete node witnesses. The operator handbook states the retained-evidence and quarantine process for partial startup and incomplete restore.

Post-candidate fixture refinement is recorded in `TIP-064-CI-refinement.md`: nine actual HTTPS origins now name their IPv4 listeners, with valid certificate IP SAN and exact audience. The new 107-PASS Linux diagnostic does not replace earlier frozen receipts or qualify the next exact Linux/Windows candidate. PowerShell reader/source-manifest compatibility refinement is separately documented in `TIP-054-PowerShell-CI-refinement.md`.

The later [asynchronous Windows CI refinement](TIP-064-async-CI-refinement.md) waits for actual stop-deadline and worker-return/drain conditions, adds sanitized transport diagnostics and gives the source full-suite harness a finite 600-second budget. Its current four-file bundle is `fd0e5930a6a0465fe346b447e519d305e6bfdda731c9d28c4e68a154516fdbc6`; focused Linux evidence is 159 PASS/3 explicit skips. The original frozen receipts remain historical; exact canonical full Linux/Windows CI is still required.
