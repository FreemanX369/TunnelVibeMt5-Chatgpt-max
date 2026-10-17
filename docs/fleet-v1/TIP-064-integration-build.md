# TIP-064 — Integrated source verification and handover

Status: DISPATCHED for preparation; completion depends on all M1-M5 source outputs and refinements. Continuous owner authorization includes source build/test/review and Draft Git checkpoint, with actual VM/SDK testing after handover.

YAGNI-3: reusable source needs concrete startup/domain entry points and integrated acceptance; reuse current CLI/MCP patterns, HTTPS client and fixtures; add a separate opt-in fleet catalog/service configuration and Windows/Linux verification workflow while preserving the legacy 85-tool catalog.

* Singleton gateway starts only via explicit operator service command. MCP adapters remain gateway clients; opening a client never initializes or spawns gateway control authority. Node loop is outbound-only. Validate required policy/certificate/key/origin/root configuration and graceful bounded stop; no actual service installation/provider selection now.
* Expose a finite useful domain surface for fleet inventory/reads/snapshot, node-owned frozen projects/STRICT baseline, durable jobs/cancel/scoped artifacts and guarded writer/worktree operations as interfaces are accepted. Separate optional fleet MCP catalog from immutable legacy catalog, with precise schemas/result provenance and explicit owner/principal credential boundary. No generic shell/admin secret command routes.
* Integrate real HTTPS ephemeral node fixture -> exact command -> local synthetic adapter -> signed result -> snapshot, then durable journal -> gated native adapter -> immutable artifact, and verified principal -> guarded write/worktree. Verify routed denial with absent exact physical qualification; fixture positives remain labeled.
* Add a source workflow running complete relevant unit suites on Linux and Windows with locked dependencies, retained Q1/G03A/B1 proofs, source manifest and JUnit/log receipts. Contractor checks exact candidate/head/tree and failed/superseded receipts. No VM/MT5 private test is implied by CI.
* Handover covers config/start commands, key protection/clone exclusion, migration preserving legacy hashes/history, backups/fenced restore/reconciliation, exact test order after build, expected safe failures and rollback anchors. Map every planned TIP/requirement to concrete source/tests and identify honest physical gates. No source module may be marked DONE solely from a document or import test.

Contractor independently reviews and refines before final Draft handover. No per-TIP owner confirmation interrupts this source execution.
