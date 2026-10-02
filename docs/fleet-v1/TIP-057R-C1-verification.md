# TIP-057R-C1 — Contractor verification

Date: 2026-10-03, Asia/Saigon. **C1 PRODUCT SOURCE PASS / TARGETED IPC UNAVAILABLE.** Separate Draft [PR #64](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/64) depends on #63 head `5583204f698dcbf664ad20ddae8106d96019c8d2`. Qualified source `9ec22fec63c64bcaf2aae0df85f1d10d70dfd1e0`, tree `3eea6cf2c47abdbacbc2d6dcf80ee8922eae335b`. This is the bounded [C1 TIP](TIP-057R-C1-build.md), not the completed fourteen-AC live-read feature or M1. The owner's VM/SDK deferral remains in force.

## Scope and independent review

Only the selected state/account facade and MCP methods gain an optional target; null/omitted calls retain legacy MT5-2 observation, output and errors. The new helper strictly projects IDs/generations/fields and resolves fresh config/registry under the existing shared native lease. Duplicate aliases and invalid enabled types are rejected without weakening M0. Inventory attribution never authorizes live_read. Resolved targets always fail LIVE_ATTACH_ONLY_UNPROVEN; observed source/time/binding, account and terminal stay null.

Independent read-only source review is CLEAR. Generic admission faults were corrected to LIVE_RECOVERY_REQUIRED; only TimeoutError maps to LIVE_LEASE_UNAVAILABLE. Release uncertainty wins with the first earlier failure preserved. Cleanup stays NOT_ATTEMPTED; normal RELEASED means this zero-effect request no longer owns its common lease, not SDK/descendant qualification or deletion of a successor lease. Unexecuted timings remain null and final soft-budget time includes release overruns. There is no SDK/process/proof import, native attempt, worker/success branch or activation switch.

## Acceptance evidence

| C1 AC | Contractor disposition |
|---|---|
| C01 | PASS: exact parent-vs-current generated MCP comparison finds only two changed input schemas. All other 83 schemas digest `16ceef873678e7d7598874c6e612393e23de35c934f18ab6a31b09ad15bd7541`; catalog order/count/hash remain 85. Legacy/null/runtime and native signatures retain their contracts. |
| C02 | PASS: malformed/oversized IDs, extra fields, bool/string/float generations and unsafe route values are rejected before projection/admission; SDK argument model rejects scalar targets. |
| C03 | PASS: fresh config/registry, disabled/duplicate/shared resource, corrupt/missing config/registry, registry revision/generation/drift and unknown/stale targets; no cached fallback. |
| C04 | PASS: both operations return inventory attribution only, permanent no-start denial, null observation/account data and unchanged authority/config/registry bytes. |
| C05 | PASS: genuine shared ownership/FIFO/corrupt-sequence admission plus bounded fault cases and no target-specific lock. |
| C06 | PASS: normal release measured before return; release error preserves primary and reports recovery-required without claiming native cleanup. |
| C07 | PASS: remaining wait, expiry, skipped resolution and release overrun disclose the measured soft budget and preserve the first failure. |
| C08 | PASS for source: 62 C1 cases, full retained suites, exact published bytes and seven candidate workflows verified. Physical client/SDK gates stay open. |

Builder's [Completion Report](TIP-057R-C1-completion.md) maps named tests and frozen hashes. Contractor independently compiled and ran the frozen full unit suite: **464 PASS / 26 existing Linux platform skips**, no failures/errors. JUnit has 490 cases, including **62 C1 cases with zero failures/skips**. Retained local portable Q1 8/8 and B1 39/39 PASS. Whitespace PASS. The focused forbidden-effect guard records attempts and asserts zero even if a domain handler catches an exception.

Actual Windows TIP-053 unit run [37054091718](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37054091718), job `110994378031`: **486 PASS / 4 pre-existing skips in 38.05s**. It checks out merge commit `b91c87a5a956d24e91fd431237c78afcce78bd55`; independent source-to-merge comparison has zero changed files, so its tree is exactly the qualified source tree. The full suite includes all C1 cases; this is Windows source/fixture evidence, not an actual MT5 or connector pilot. Original decoded unit log and local JUnit are retained separately.

## Candidate CI and original artifacts

All seven source workflows completed/success: TIP-027 `37054091594`, TIP-028 `37054091766`, TIP-034 `37054091602`, TIP-053 `37054091718`, Q1 `37054091586`, G03-A `37054091676`, B1 `37054091785`.

| Artifact | ZIP bytes | Original ZIP SHA256 | Scoped result |
|---|---|---|---|
| B1 `11247374319` | 8058 | `e3edc6bb250791161f10c2bc8a63446a56e21287030e302737a2db2d47f0ce0f` | 39 portable + 10 harmless Windows stub; zero failure/error/skip |
| G03-A `11248140572` | 2315 | `d66fc1eaebec0f1fb7a3b4baffadc86930023f2d76baf10419aba1d63eec7f9d` | 8 harmless actual Windows identity cases; zero failure/error/skip |
| Q1 `11247578729` | 8882 | `aee2567bc3bc8d629490980db805f976160e324b0e0fe4f8fc5824c81d059641` | 16 Windows fixture cases; zero failure/error/skip, Q03 still open |

Contractor downloaded original ZIP bytes, matched advertised digest/size and exact candidate head, checked executed source/content hashes, raw unique PASS names and nontruncated logs. Original textual members are retained byte-for-byte under [source receipts](../../evidence/tip057rc1/source-9ec22fec). Publication fetch independently matches all four product/test Git blob IDs recorded in verification.json. Source compare against #63 contains only the four implementation/test files, C1 TIP and task graph; no older proof/evidence/dependency/native producer changed.

## Qualification limits and final head

C1 closes its request/validation/failure-receipt source acceptance. SDK initialization/observation/cleanup, post-observation revalidation, preventive attach-only and physical race/broker/two-binding/client acceptance remain unexecuted. Q2, full G03-B producer integration/migration, actual connector exposure, usable positive targeted reads and M1 remain OPEN. No merge, deployment, private VM/VPS or MT5 account/AutoTrading operation occurred.

The final documentation/evidence commit leaves frozen product/test/proof/workflow bytes unchanged. Its exact head, merge-tree comparison and all seven final checks are verified and recorded in PR #64 before return, without recursively rewriting the qualified evidence.
